import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabelog_insta.config import load_config
from tabelog_insta.media import generate_feed_cover_image, prepare_feed_photo, select_best_image_urls
from tabelog_insta.scraper import build_caption, parse_detail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-url", required=True)
    parser.add_argument("--output-dir", default="generated")
    parser.add_argument("--caption-style", default="story", choices=["story", "short", "review"])
    args = parser.parse_args()

    config = load_config()
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
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    cover_path = generate_feed_cover_image(review)
    public_cover = output_dir / f"{review['review_id']}_feed_cover.jpg"
    shutil.copyfile(cover_path, public_cover)

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
        "image_paths": prepared_image_paths,
        "image_urls": review.get("image_urls", [])[:6],
    }
    manifest_path = output_dir / f"{review['review_id']}_post.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"review_id={review['review_id']}")
    print(f"manifest={manifest_path}")
    print(f"cover={public_cover}")


if __name__ == "__main__":
    main()
