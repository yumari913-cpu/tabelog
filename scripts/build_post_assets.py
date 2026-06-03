import argparse
import json
import shutil
from pathlib import Path

from tabelog_insta.config import load_config
from tabelog_insta.media import generate_feed_cover_image
from tabelog_insta.scraper import build_caption, parse_detail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-url", required=True)
    parser.add_argument("--output-dir", default="generated")
    args = parser.parse_args()

    config = load_config()
    review = parse_detail(args.review_url)
    review["caption"] = build_caption(
        review.get("restaurant_name", ""),
        review.get("area_category", ""),
        review.get("review_title", ""),
        review.get("body", ""),
        review.get("rating", ""),
        review.get("review_url", ""),
        config.get("hashtags", []),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    cover_path = generate_feed_cover_image(review)
    public_cover = output_dir / f"{review['review_id']}_feed_cover.jpg"
    shutil.copyfile(cover_path, public_cover)

    caption_path = output_dir / f"{review['review_id']}_caption.txt"
    caption_path.write_text(review["caption"], encoding="utf-8")

    manifest = {
        "review_id": review["review_id"],
        "review_url": review["review_url"],
        "restaurant_name": review.get("restaurant_name", ""),
        "caption": review["caption"],
        "cover_path": str(public_cover),
        "image_urls": review.get("image_urls", [])[:9],
    }
    manifest_path = output_dir / f"{review['review_id']}_post.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"review_id={review['review_id']}")
    print(f"manifest={manifest_path}")
    print(f"cover={public_cover}")


if __name__ == "__main__":
    main()
