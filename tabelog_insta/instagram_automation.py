import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .instagram import InstagramClient
from .media import (
    generate_feed_cover_image,
    generate_story_image,
    prepare_feed_photo,
    select_best_image_urls,
    upload_media,
)
from .scraper import build_caption, list_review_urls, parse_detail


REVIEW_URL_FIELDS = ["No.", "店名", "訪問日", "レビューURL"]
POSTED_FIELDS = ["投稿日時UTC", "店名", "レビューURL", "GitHub Run", "Instagram結果"]
REVIEW_URLS_BLOB = "data/review_urls.csv"
POSTED_URLS_BLOB = "data/posted_review_urls.csv"


def _bucket(config):
    bucket_name = config.get("storage_bucket")
    if not bucket_name:
        return None
    try:
        from google.cloud import storage
    except Exception as exc:
        raise RuntimeError("google-cloud-storage is required when storage_bucket is configured.") from exc
    return storage.Client().bucket(bucket_name)


def _read_csv_text(text):
    if not text:
        return []
    return list(csv.DictReader(io.StringIO(text)))


def _read_csv(config, blob_name, local_name):
    bucket = _bucket(config)
    if bucket:
        blob = bucket.blob(blob_name)
        if blob.exists():
            return _read_csv_text(blob.download_as_text(encoding="utf-8-sig"))

    local_path = ROOT / local_name
    if not local_path.exists():
        return []
    return _read_csv_text(local_path.read_text(encoding="utf-8-sig"))


def _write_csv(config, blob_name, local_name, rows, fieldnames):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

    bucket = _bucket(config)
    if bucket:
        bucket.blob(blob_name).upload_from_string(
            output.getvalue(),
            content_type="text/csv; charset=utf-8",
        )
        return

    (ROOT / local_name).write_text(output.getvalue(), encoding="utf-8")


def load_review_url_rows(config):
    return _read_csv(config, REVIEW_URLS_BLOB, "review_urls.csv")


def load_posted_rows(config):
    return _read_csv(config, POSTED_URLS_BLOB, "posted_review_urls.csv")


def save_review_url_rows(config, rows):
    for index, row in enumerate(rows, start=1):
        row["No."] = str(index)
    _write_csv(config, REVIEW_URLS_BLOB, "review_urls.csv", rows, REVIEW_URL_FIELDS)


def save_posted_rows(config, rows):
    _write_csv(config, POSTED_URLS_BLOB, "posted_review_urls.csv", rows, POSTED_FIELDS)


def sync_review_urls_to_state(config, max_pages=10):
    existing_rows = load_review_url_rows(config)
    existing_urls = {row.get("レビューURL", "").strip() for row in existing_rows}
    reviewer_url = config.get("tabelog_reviewer_url", "")

    new_rows = []
    for review_url in list_review_urls(reviewer_url, max_pages=max_pages):
        if review_url in existing_urls:
            continue
        review = parse_detail(review_url)
        new_rows.append(
            {
                "No.": "",
                "店名": review.get("restaurant_name", ""),
                "訪問日": review.get("visited_date", ""),
                "レビューURL": review.get("review_url", review_url),
            }
        )

    if new_rows:
        save_review_url_rows(config, new_rows + existing_rows)

    return {"new_count": len(new_rows), "added": [row["レビューURL"] for row in new_rows]}


def select_next_review_row(config):
    review_rows = load_review_url_rows(config)
    posted_rows = load_posted_rows(config)
    posted_urls = {row.get("レビューURL", "").strip() for row in posted_rows}

    for row in review_rows:
        review_url = row.get("レビューURL", "").strip()
        if review_url and review_url not in posted_urls:
            return row
    return None


def build_review_manifest(config, review_url):
    review = parse_detail(review_url)
    review["image_urls"] = select_best_image_urls(
        review.get("image_urls", []),
        review["review_id"],
        limit=6,
    )
    review["caption"] = build_caption(
        review.get("restaurant_name", ""),
        review.get("area_category", ""),
        review.get("review_title", ""),
        review.get("body", ""),
        review.get("rating", ""),
        review.get("review_url", ""),
        config.get("hashtags", []),
        style="story",
        business_hours=review.get("business_hours", ""),
        regular_holiday=review.get("regular_holiday", ""),
    )

    cover_path = generate_feed_cover_image(review)
    story_path = generate_story_image(review)
    image_paths = [
        prepare_feed_photo(image_url, review["review_id"], index)
        for index, image_url in enumerate(review.get("image_urls", [])[:6], start=1)
    ]
    return {
        "review": review,
        "cover_path": cover_path,
        "story_path": story_path,
        "image_paths": image_paths,
    }


def validate_manifest_assets(manifest):
    from scripts.validate_generated_assets import validate_cover, validate_feed_photo, validate_story

    validate_cover(Path(manifest["cover_path"]))
    validate_story(Path(manifest["story_path"]))
    for image_path in manifest["image_paths"]:
        validate_feed_photo(Path(image_path))


def mark_review_posted(config, review_row, result):
    rows = load_posted_rows(config)
    review_url = review_row.get("レビューURL", "").strip()
    if any(row.get("レビューURL", "").strip() == review_url for row in rows):
        return False

    rows.append(
        {
            "投稿日時UTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "店名": review_row.get("店名", ""),
            "レビューURL": review_url,
            "GitHub Run": "",
            "Instagram結果": json.dumps(result, ensure_ascii=False),
        }
    )
    save_posted_rows(config, rows)
    return True


def publish_next_instagram_review(config, dry_run=False, publish_story=True):
    review_row = select_next_review_row(config)
    if not review_row:
        return {"has_next": False}

    manifest = build_review_manifest(config, review_row["レビューURL"])
    validate_manifest_assets(manifest)

    cover_url = upload_media(config, manifest["cover_path"])
    image_urls = [cover_url] + [upload_media(config, path) for path in manifest["image_paths"]]
    story_url = upload_media(config, manifest["story_path"])

    review = manifest["review"]
    preview = {
        "has_next": True,
        "review_id": review["review_id"],
        "restaurant_name": review.get("restaurant_name", ""),
        "review_url": review.get("review_url", ""),
        "image_count": len(image_urls),
        "story": bool(story_url and publish_story),
    }
    if dry_run:
        preview["caption"] = review.get("caption", "")
        return preview

    client = InstagramClient(config)
    if not client.ready:
        raise RuntimeError("IG_USER_ID and IG_ACCESS_TOKEN are required.")

    result = {"feed": client.publish_carousel(image_urls, review.get("caption", ""))}
    if publish_story and story_url:
        try:
            result["story"] = client.publish_story(story_url)
        except Exception as exc:
            result["story_error"] = str(exc)

    mark_review_posted(config, review_row, result)
    return {**preview, "result": result}
