import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabelog_insta.config import load_config
from tabelog_insta.media import (
    generate_feed_cover_image,
    generate_story_image,
    prepare_feed_photo,
    select_best_image_urls,
)
from tabelog_insta.scraper import build_caption, parse_detail
from tabelog_insta.scraper import extract_review_id


def validate_review_url(review_url):
    parsed = urlparse(review_url)
    if parsed.netloc != "tabelog.com" or "/rvwdtl/B" not in parsed.path:
        raise SystemExit(
            "食べログの口コミ詳細URLを入力してください。例: "
            "https://tabelog.com/rvwr/018712231/rvwdtl/B527303939/"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-url", required=True)
    parser.add_argument("--output-dir", default="generated")
    parser.add_argument("--caption-style", default="story", choices=["story", "short", "review"])
    args = parser.parse_args()

    validate_review_url(args.review_url)

    config = load_config()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    review_id = extract_review_id(args.review_url)
    manifest_path = output_dir / f"{review_id}_post.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_paths = [
            manifest.get("cover_path"),
            manifest.get("story_path"),
            manifest.get("caption"),
            *manifest.get("image_paths", []),
        ]
        local_paths = [
            path
            for path in expected_paths
            if isinstance(path, str) and path and (path.endswith(".jpg") or path.endswith(".jpeg") or path.endswith(".png"))
        ]
        if local_paths and all(Path(path).exists() for path in local_paths):
            print(f"review_id={review_id}")
            print(f"manifest={manifest_path}")
            print(f"cover={manifest.get('cover_path', '')}")
            print(f"story={manifest.get('story_path', '')}")
            return

    review = parse_detail(args.review_url)
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
        style=args.caption_style,
        business_hours=review.get("business_hours", ""),
        regular_holiday=review.get("regular_holiday", ""),
    )

    cover_path = generate_feed_cover_image(review)
    public_cover = output_dir / f"{review['review_id']}_feed_cover.jpg"
    shutil.copyfile(cover_path, public_cover)

    story_path = generate_story_image(review)
    public_story = output_dir / f"{review['review_id']}_story.jpg"
    shutil.copyfile(story_path, public_story)

    caption_path = output_dir / f"{review['review_id']}_caption.txt"
    caption_path.write_text(review["caption"], encoding="utf-8")

    prepared_image_paths = []
    for index, image_url in enumerate(review.get("image_urls", [])[:6], start=1):
        photo_path = prepare_feed_photo(image_url, review["review_id"], index)
        public_photo = output_dir / f"{review['review_id']}_photo_{index:02d}.jpg"
        shutil.copyfile(photo_path, public_photo)
        prepared_image_paths.append(str(public_photo))

    manifest = {
        "review_id": review["review_id"],
        "review_url": review["review_url"],
        "restaurant_name": review.get("restaurant_name", ""),
        "caption": review["caption"],
        "cover_path": str(public_cover),
        "story_path": str(public_story),
        "image_paths": prepared_image_paths,
        "image_urls": review.get("image_urls", [])[:6],
    }
    manifest_path = output_dir / f"{review['review_id']}_post.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"review_id={review['review_id']}")
    print(f"manifest={manifest_path}")
    print(f"cover={public_cover}")
    print(f"story={public_story}")


if __name__ == "__main__":
    main()
