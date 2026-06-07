import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_image(path):
    try:
        from PIL import Image, ImageStat
    except Exception as exc:
        raise RuntimeError("Pillow is required to validate generated images.") from exc

    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    return image, stat


def validate_image_exists(path, label):
    if not path.exists():
        raise ValueError(f"{label} does not exist: {path}")
    if path.stat().st_size < 10_000:
        raise ValueError(f"{label} is unexpectedly small: {path}")


def validate_not_blank(image, stat, label):
    channel_ranges = [max_value - min_value for min_value, max_value in stat.extrema]
    if max(channel_ranges) < 20:
        raise ValueError(f"{label} appears to be blank or nearly flat.")


def detect_legacy_horizontal_line(image):
    width, height = image.size
    pixels = image.load()
    min_run = int(width * 0.55)
    y_start = int(height * 0.64)
    y_end = int(height * 0.90)

    def darkest_run_at(y):
        run = 0
        longest = 0
        for x in range(int(width * 0.10), int(width * 0.90)):
            r, g, b = pixels[x, y]
            if r < 35 and g < 35 and b < 35:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        return longest

    for y in range(y_start, y_end):
        if darkest_run_at(y) < min_run:
            continue
        nearby_runs = [
            darkest_run_at(max(0, y - 12)),
            darkest_run_at(min(height - 1, y + 12)),
        ]
        if max(nearby_runs) < int(width * 0.25):
            return y
    return None


def validate_cover_text_block_position(image):
    pixels = image.load()
    width, height = image.size
    xs = []
    ys = []

    for y in range(int(height * 0.40), int(height * 0.84)):
        for x in range(int(width * 0.04), int(width * 0.96)):
            r, g, b = pixels[x, y]
            if r > 225 and g > 215 and b > 190:
                xs.append(x)
                ys.append(y)

    if not ys:
        raise ValueError("cover image text card was not detected.")

    top = min(ys)
    bottom = max(ys)
    center = (top + bottom) / 2
    if top > 720 or bottom > 1220 or center > 980:
        raise ValueError(
            "cover image text card is too low for Instagram grid preview "
            f"(top={top}, bottom={bottom}, center={center:.1f})."
        )


def validate_cover(path):
    validate_image_exists(path, "cover image")
    image, stat = load_image(path)
    if image.size != (1080, 1350):
        raise ValueError(f"cover image must be 1080x1350, got {image.size}: {path}")
    validate_not_blank(image, stat, "cover image")
    legacy_line_y = detect_legacy_horizontal_line(image)
    if legacy_line_y is not None:
        raise ValueError(f"cover image has a long horizontal line near y={legacy_line_y}: {path}")
    validate_cover_text_block_position(image)


def validate_story(path):
    validate_image_exists(path, "story image")
    image, stat = load_image(path)
    if image.size != (1080, 1920):
        raise ValueError(f"story image must be 1080x1920, got {image.size}: {path}")
    validate_not_blank(image, stat, "story image")


def validate_feed_photo(path):
    validate_image_exists(path, "feed photo")
    image, stat = load_image(path)
    if image.size != (1080, 1350):
        raise ValueError(f"feed photo must be 1080x1350, got {image.size}: {path}")
    validate_not_blank(image, stat, "feed photo")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_cover(Path(manifest["cover_path"]))

    story_path = manifest.get("story_path")
    if story_path:
        validate_story(Path(story_path))

    for image_path in manifest.get("image_paths", []):
        validate_feed_photo(Path(image_path))

    print("asset_validation=passed")


if __name__ == "__main__":
    main()
