import argparse
import json
from pathlib import Path

from tabelog_insta.config import load_config
from tabelog_insta.instagram import InstagramClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--raw-base-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cover_url = f"{args.raw_base_url.rstrip('/')}/{manifest['cover_path']}"
    image_urls = [cover_url] + manifest.get("image_urls", [])[:9]

    if args.dry_run:
        print("DRY RUN")
        print(f"restaurant={manifest.get('restaurant_name')}")
        print(f"cover_url={cover_url}")
        print(f"images={len(image_urls)}")
        print(manifest.get("caption", ""))
        return

    client = InstagramClient(load_config())
    if not client.ready:
        raise SystemExit("IG_USER_ID and IG_ACCESS_TOKEN are required.")

    result = client.publish_carousel(image_urls, manifest.get("caption", ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
