import json
from datetime import datetime

from .config import DATA_DIR, ensure_dirs, load_config


DB_PATH = DATA_DIR / "reviews.json"
DB_BLOB_NAME = "data/reviews.json"
_CLIENT = None


def gcs_bucket():
    bucket_name = load_config().get("storage_bucket")
    if not bucket_name:
        return None
    try:
        from google.cloud import storage
    except Exception as exc:
        raise RuntimeError("google-cloud-storage is required when storage_bucket is configured.") from exc
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = storage.Client()
    return _CLIENT.bucket(bucket_name)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def load_reviews():
    ensure_dirs()
    bucket = gcs_bucket()
    if bucket:
        blob = bucket.blob(DB_BLOB_NAME)
        if not blob.exists():
            return []
        return json.loads(blob.download_as_text(encoding="utf-8"))
    if not DB_PATH.exists():
        return []
    with DB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_reviews(reviews):
    ensure_dirs()
    bucket = gcs_bucket()
    if bucket:
        blob = bucket.blob(DB_BLOB_NAME)
        blob.upload_from_string(
            json.dumps(reviews, ensure_ascii=False, indent=2),
            content_type="application/json; charset=utf-8",
        )
        return
    with DB_PATH.open("w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)


def upsert_reviews(incoming):
    reviews = load_reviews()
    by_id = {review["review_id"]: review for review in reviews}
    added = []
    updated = []

    for review in incoming:
        existing = by_id.get(review["review_id"])
        if existing:
            status = existing.get("status", "pending")
            post_results = existing.get("post_results", {})
            existing.update(review)
            existing["status"] = status
            existing["post_results"] = post_results
            existing["updated_at"] = now_iso()
            updated.append(existing)
        else:
            review.setdefault("status", "pending")
            review.setdefault("post_results", {})
            review["created_at"] = now_iso()
            review["updated_at"] = now_iso()
            reviews.append(review)
            by_id[review["review_id"]] = review
            added.append(review)

    reviews.sort(key=lambda item: item.get("visited_date") or "", reverse=True)
    save_reviews(reviews)
    return added, updated


def get_review(review_id):
    for review in load_reviews():
        if review["review_id"] == review_id:
            return review
    return None


def update_review(review_id, changes):
    reviews = load_reviews()
    for review in reviews:
        if review["review_id"] == review_id:
            review.update(changes)
            review["updated_at"] = now_iso()
            save_reviews(reviews)
            return review
    return None


def mark_posted(review_id, target, response):
    reviews = load_reviews()
    for review in reviews:
        if review["review_id"] == review_id:
            results = review.setdefault("post_results", {})
            results[target] = {
                "posted_at": now_iso(),
                "response": response,
            }
            if results.get("feed"):
                review["status"] = "posted"
            review["updated_at"] = now_iso()
            save_reviews(reviews)
            return review
    return None
