import hashlib
import io
import math
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from .config import MEDIA_DIR, ensure_dirs


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) TabelogInstagramBot/1.0"


def safe_name(value):
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return digest


def download_image(url, review_id, index=0):
    ensure_dirs()
    ext = ".jpg"
    path = MEDIA_DIR / f"{review_id}_{index}{ext}"
    if path.exists():
        return path
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as res:
        path.write_bytes(res.read())
    return path


def font(size, bold=False):
    try:
        from PIL import ImageFont
    except Exception:
        return None
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc" if bold else "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def wrap_text(draw, text, text_font, max_width):
    lines = []
    current = ""
    for char in text:
        test = current + char
        box = draw.textbbox((0, 0), test, font=text_font)
        if box[2] - box[0] <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def draw_centered(draw, text, y, text_font, fill, max_width, line_gap=12, max_lines=3):
    lines = wrap_text(draw, text, text_font, max_width)[:max_lines]
    for line in lines:
        box = draw.textbbox((0, 0), line, font=text_font)
        draw.text(((1080 - (box[2] - box[0])) / 2, y), line, fill=fill, font=text_font)
        y += (box[3] - box[1]) + line_gap
    return y


def cover_area(review):
    raw = review.get("area_category", "")
    area = raw.split("/")[0].replace("（", "").replace("）", "").strip()
    return area or "TOKYO"


def normalize_image_url(url):
    return url.split("?", 1)[0].replace("640x640_rect_", "").replace("320x320_rect_", "")


def average_hash(image, size=8):
    image = image.convert("L").resize((size, size))
    pixels = list(image.getdata())
    avg = sum(pixels) / len(pixels)
    return "".join("1" if pixel >= avg else "0" for pixel in pixels)


def hash_distance(left, right):
    return sum(1 for a, b in zip(left, right) if a != b)


def image_quality_score(image):
    try:
        from PIL import ImageStat, ImageFilter
    except Exception:
        return 0

    width, height = image.size
    pixels = width * height
    aspect = width / height if height else 1
    aspect_score = 1.0 - min(abs(aspect - 1.0), 0.65) / 0.65

    gray = image.convert("L")
    brightness = ImageStat.Stat(gray).mean[0]
    brightness_score = 1.0 - min(abs(brightness - 145), 120) / 120

    edges = gray.filter(ImageFilter.FIND_EDGES)
    sharpness = ImageStat.Stat(edges).stddev[0]
    sharpness_score = min(sharpness / 42, 1.0)

    resolution_score = min(math.sqrt(pixels) / 1200, 1.0)
    return resolution_score * 0.35 + sharpness_score * 0.3 + brightness_score * 0.2 + aspect_score * 0.15


def select_best_image_urls(image_urls, review_id, limit=6):
    try:
        from PIL import Image
    except Exception:
        return image_urls[:limit]

    candidates = []
    seen_urls = set()
    seen_hashes = []

    for index, image_url in enumerate(image_urls):
        normalized = normalize_image_url(image_url)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)

        try:
            image_path = download_image(image_url, review_id, index + 100)
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                ahash = average_hash(image)
                if any(hash_distance(ahash, seen) <= 4 for seen in seen_hashes):
                    continue
                seen_hashes.append(ahash)
                candidates.append((image_quality_score(image), index, image_url))
        except Exception:
            continue

    if not candidates:
        return image_urls[:limit]

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [image_url for _, _, image_url in candidates[:limit]]


def generate_feed_cover_image(review):
    ensure_dirs()
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception as exc:
        raise RuntimeError("Pillow is required to generate feed cover images.") from exc

    width = height = 1080
    bg = Image.new("RGB", (width, height), "#111111")
    image_urls = review.get("image_urls") or []
    if image_urls:
        photo_path = download_image(image_urls[0], review["review_id"], 0)
        photo = Image.open(photo_path).convert("RGB")
        photo_ratio = photo.width / photo.height
        target_ratio = width / height
        if photo_ratio > target_ratio:
            new_height = height
            new_width = int(height * photo_ratio)
        else:
            new_width = width
            new_height = int(width / photo_ratio)
        photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - width) // 2
        top = (new_height - height) // 2
        bg = photo.crop((left, top, left + width, top + height)).filter(ImageFilter.GaussianBlur(7))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 130))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(bg)
    area_text = cover_area(review)
    restaurant_name = review.get("restaurant_name", "")

    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.rounded_rectangle((96, 296, 984, 784), radius=26, fill=(255, 255, 255, 226))
    panel_draw.rounded_rectangle((116, 316, 964, 764), radius=22, outline=(255, 255, 255, 150), width=3)
    bg = Image.alpha_composite(bg.convert("RGBA"), panel)
    draw = ImageDraw.Draw(bg)

    area_font = font(46, bold=True)
    area_box = draw.textbbox((0, 0), area_text, font=area_font)
    pill_w = area_box[2] - area_box[0] + 74
    pill_x = (width - pill_w) / 2
    draw.rounded_rectangle((pill_x, 238, pill_x + pill_w, 308), radius=35, fill="#111111")
    draw.text((pill_x + 37, 249), area_text, fill="#ffffff", font=area_font)

    draw_centered(draw, restaurant_name, 440, font(80, bold=True), "#111111", 760, line_gap=18, max_lines=3)
    draw.line((254, 706, 826, 706), fill="#111111", width=3)
    draw.ellipse((526, 695, 554, 723), fill="#111111")

    output = MEDIA_DIR / f"{review['review_id']}_feed_cover.jpg"
    bg.convert("RGB").save(output, quality=94)
    return output


def upload_media(config, local_path, content_type="image/jpeg"):
    bucket_name = config.get("storage_bucket")
    if not bucket_name:
        return ""
    try:
        from google.cloud import storage
    except Exception as exc:
        raise RuntimeError("google-cloud-storage is required when storage_bucket is configured.") from exc
    client = storage.Client()
    blob_name = f"media/{Path(local_path).name}"
    blob = client.bucket(bucket_name).blob(blob_name)
    blob.upload_from_filename(str(local_path), content_type=content_type)
    public_base = config.get("public_base_url", "").rstrip("/")
    if public_base:
        return f"{public_base}/{blob_name}"
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"


def export_instagram_package(review):
    ensure_dirs()
    cover_path = generate_feed_cover_image(review)
    package_dir = MEDIA_DIR / f"{review['review_id']}_instagram_package"
    package_dir.mkdir(exist_ok=True)

    package_cover = package_dir / "01_feed_cover.jpg"
    shutil.copyfile(cover_path, package_cover)

    for index, image_url in enumerate((review.get("image_urls") or [])[:9], start=2):
        image_path = download_image(image_url, review["review_id"], index)
        shutil.copyfile(image_path, package_dir / f"{index:02d}_photo.jpg")

    (package_dir / "caption.txt").write_text(review.get("caption", ""), encoding="utf-8")
    (package_dir / "README.txt").write_text(
        "Instagram投稿用パッケージです。\n"
        "01_feed_cover.jpgを1枚目にして、02_photo.jpg以降をカルーセルに追加してください。\n"
        "caption.txtの内容をキャプション欄に貼り付けます。\n",
        encoding="utf-8",
    )

    zip_path = MEDIA_DIR / f"{review['review_id']}_instagram_package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package_dir.iterdir()):
            zf.write(path, arcname=path.name)
    return zip_path


def generate_story_image(review):
    ensure_dirs()
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        raise RuntimeError("Pillow is required to generate story images.") from exc

    width, height = 1080, 1920
    bg = Image.new("RGB", (width, height), "#fff7ed")
    draw = ImageDraw.Draw(bg)

    try:
        font_title = font(68, bold=True)
        font_body = font(42)
        font_small = font(34)
    except Exception:
        font_title = font_body = font_small = ImageFont.load_default()

    image_urls = review.get("image_urls") or []
    if image_urls:
        photo_path = download_image(image_urls[0], review["review_id"], 0)
        photo = Image.open(photo_path).convert("RGB")
        photo.thumbnail((980, 980))
        px = (width - photo.width) // 2
        bg.paste(photo, (px, 120))

    y = 1120
    draw.text((64, y), review.get("restaurant_name", ""), fill="#22110a", font=font_title)
    y += 96
    area = review.get("area_category", "")
    if area:
        draw.text((64, y), area[:36], fill="#7c2d12", font=font_small)
        y += 70
    rating = review.get("rating", "")
    if rating:
        draw.text((64, y), f"Tabelog rating: {rating}", fill="#ea580c", font=font_body)
        y += 72
    title = review.get("review_title", "")
    if title:
        draw.text((64, y), title[:24], fill="#22110a", font=font_body)

    draw.rectangle((64, 1760, 1016, 1810), fill="#ea580c")
    draw.text((64, 1830), "詳しくは食べログ投稿へ", fill="#7c2d12", font=font_small)

    output = MEDIA_DIR / f"{review['review_id']}_story.jpg"
    bg.save(output, quality=92)
    return output


def generate_reel_video(review):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed. Install ffmpeg to generate reels.")

    image_urls = review.get("image_urls") or []
    if not image_urls:
        raise RuntimeError("No images available for reel generation.")

    frame_paths = []
    for index, image_url in enumerate(image_urls[:5]):
        frame_paths.append(download_image(image_url, review["review_id"], index))

    list_path = MEDIA_DIR / f"{review['review_id']}_reel_frames.txt"
    with list_path.open("w", encoding="utf-8") as f:
        for path in frame_paths:
            f.write(f"file '{path.resolve()}'\n")
            f.write("duration 2\n")
        f.write(f"file '{frame_paths[-1].resolve()}'\n")

    output = MEDIA_DIR / f"{review['review_id']}_reel.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=white",
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ],
        check=True,
    )
    return output
