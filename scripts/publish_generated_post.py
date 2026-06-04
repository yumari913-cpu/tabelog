import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabelog_insta.config import load_config
from tabelog_insta.instagram import InstagramClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--raw-base-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-story", action="store_true")
    parser.add_argument("--story-only", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_base = args.raw_base_url.rstrip("/")
    cover_url = f"{raw_base}/{manifest['cover_path']}"
    story_path = manifest.get("story_path")
    story_url = f"{raw_base}/{story_path}" if story_path else ""
    image_paths = manifest.get("image_paths", [])
    if image_paths:
        image_urls = [cover_url] + [f"{raw_base}/{path}" for path in image_paths[:9]]
    else:
        image_urls = [cover_url] + manifest.get("image_urls", [])[:9]

    if args.dry_run:
        print("DRY RUN")
        print(f"restaurant={manifest.get('restaurant_name')}")
        print(f"cover_url={cover_url}")
        if story_url:
            print(f"story_url={story_url}")
        print(f"images={len(image_urls)}")
        print(manifest.get("caption", ""))
        return

    client = InstagramClient(load_config())
    if not client.ready:
        raise SystemExit("IG_USER_ID and IG_ACCESS_TOKEN are required.")

    results = {}
    if args.story_only:
        if not story_url:
            raise SystemExit("story_path is required for story-only publishing.")
        results["story"] = client.publish_story(story_url)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    results["feed"] = client.publish_carousel(image_urls, manifest.get("caption", ""))
    if story_url and not args.skip_story:
        try:
            results["story"] = client.publish_story(story_url)
        except Exception as exc:
            results["story_error"] = str(exc)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
