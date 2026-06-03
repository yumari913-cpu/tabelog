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
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_base = args.raw_base_url.rstrip("/")
    cover_url = f"{raw_base}/{manifest['cover_path']}"
    image_paths = manifest.get("image_paths", [])
    if image_paths:
        image_urls = [cover_url] + [f"{raw_base}/{path}" for path in image_paths[:9]]
    else:
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
