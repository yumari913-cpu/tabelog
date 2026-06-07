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


def fit_text_lines(draw, text, max_width, max_lines, max_total_height, start_size, min_size):
    for size in range(start_size, min_size - 1, -4):
        text_font = font(size, bold=True)
        lines = wrap_text(draw, text, text_font, max_width)
        if len(lines) > max_lines:
            continue
        line_boxes = [draw.textbbox((0, 0), line, font=text_font) for line in lines]
        line_heights = [box[3] - box[1] for box in line_boxes]
        total_height = sum(line_heights) + max(0, len(lines) - 1) * int(size * 0.2)
        widest = max((box[2] - box[0] for box in line_boxes), default=0)
        if widest <= max_width and total_height <= max_total_height:
            return text_font, lines, total_height, int(size * 0.2)

    text_font = font(min_size, bold=True)
    lines = wrap_text(draw, text, text_font, max_width)[:max_lines]
    if lines:
        overflow = wrap_text(draw, lines[-1], text_font, max_width - 60)
        if overflow:
            lines[-1] = overflow[0].rstrip("、,。") + "…"
    line_boxes = [draw.textbbox((0, 0), line, font=text_font) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    total_height = sum(line_heights) + max(0, len(lines) - 1) * int(min_size * 0.2)
    return text_font, lines, total_height, int(min_size * 0.2)


def cover_crop(image, width=1080, height=1350):
    from PIL import Image

    photo_ratio = image.width / image.height
    target_ratio = width / height
    if photo_ratio > target_ratio:
        new_height = height
        new_width = int(height * photo_ratio)
    else:
        new_width = width
        new_height = int(width / photo_ratio)
    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    return image.crop((left, top, left + width, top + height))


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


def fit_image_to_canvas(image, width=1080, height=1350, background="#fffaf0"):
    from PIL import Image

    image = image.convert("RGB")
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), background)
    x = (width - image.width) // 2
    y = (height - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def generate_feed_cover_image(review):
    ensure_dirs()
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise RuntimeError("Pillow is required to generate feed cover images.") from exc

    width, height = 1080, 1920
    bg = Image.new("RGB", (width, height), "#171717")
    image_urls = review.get("image_urls") or []
    if image_urls:
        photo_path = download_image(image_urls[0], review["review_id"], 0)
        photo = Image.open(photo_path).convert("RGB")
        bg = cover_crop(photo, width, height)

    area_text = cover_area(review)
    restaurant_name = review.get("restaurant_name", "")

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle((0, 0, width, 620), fill=(0, 0, 0, 54))
    overlay_draw.rectangle((0, 900, width, 1580), fill=(0, 0, 0, 84))
    card = (52, 920, 1028, 1498)
    overlay_draw.rounded_rectangle(card, radius=46, fill=(255, 252, 245, 246))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(bg)

    area_font = font(44, bold=True)
    area_label = area_text.split("、")[0].strip() or area_text
    area_label = f"{area_label}グルメ"
    area_box = draw.textbbox((0, 0), area_label, font=area_font)
    pill_w = min(area_box[2] - area_box[0] + 70, 860)
    pill = (88, 870, 88 + pill_w, 948)
    draw.rounded_rectangle(pill, radius=39, fill="#111111")
    draw.text((123, 886), area_label, fill="#ffffff", font=area_font)

    name_font, name_lines, total_height, line_gap = fit_text_lines(
        draw,
        restaurant_name,
        max_width=850,
        max_lines=3,
        max_total_height=350,
        start_size=92,
        min_size=52,
    )
    y = card[1] + ((card[3] - card[1]) - total_height) / 2 + 22
    for line in name_lines:
        box = draw.textbbox((0, 0), line, font=name_font)
        draw.text(
            ((width - (box[2] - box[0])) / 2, y),
            line,
            fill="#111111",
            font=name_font,
        )
        y += (box[3] - box[1]) + line_gap

    output = MEDIA_DIR / f"{review['review_id']}_feed_cover.jpg"
    bg.convert("RGB").save(output, quality=94)
    return output


def prepare_feed_photo(image_url, review_id, index, width=1080, height=1350):
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("Pillow is required to prepare feed images.") from exc

    source = download_image(image_url, review_id, index + 200)
    with Image.open(source) as image:
        canvas = cover_crop(image.convert("RGB"), width, height)
    output = MEDIA_DIR / f"{review_id}_feed_photo_{index:02d}.jpg"
    canvas.save(output, quality=94)
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
        from PIL import Image, ImageDraw, ImageFilter
    except Exception as exc:
        raise RuntimeError("Pillow is required to generate story images.") from exc

    width, height = 1080, 1920
    bg = Image.new("RGB", (width, height), "#151515")
    image_urls = review.get("image_urls") or []
    if image_urls:
        photo_path = download_image(image_urls[0], review["review_id"], 0)
        photo = Image.open(photo_path).convert("RGB")
        bg = cover_crop(photo, width, height)
        bg = bg.filter(ImageFilter.GaussianBlur(10))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 74))
    overlay_draw.rectangle((0, 0, width, 410), fill=(0, 0, 0, 58))
    overlay_draw.rectangle((0, 1510, width, height), fill=(0, 0, 0, 132))

    if image_urls:
        photo_path = download_image(image_urls[0], review["review_id"], 0)
        photo = Image.open(photo_path).convert("RGB")
        main_photo = cover_crop(photo, 900, 1120)
        photo_shadow = Image.new("RGBA", (940, 1160), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(photo_shadow)
        shadow_draw.rounded_rectangle((20, 20, 920, 1140), radius=46, fill=(0, 0, 0, 95))
        photo_shadow = photo_shadow.filter(ImageFilter.GaussianBlur(18))
        overlay.alpha_composite(photo_shadow, (70, 310))
        mask = Image.new("L", (900, 1120), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 900, 1120), radius=42, fill=255)
        overlay.paste(main_photo.convert("RGBA"), (90, 330), mask)

    bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(bg)

    area_text = cover_area(review)
    restaurant_name = review.get("restaurant_name", "")

    label_font = font(42, bold=True)
    title_font = font(76, bold=True)
    small_font = font(34, bold=True)

    area_label = f"{area_text.split('、')[0].strip() or area_text}グルメ"
    area_box = draw.textbbox((0, 0), area_label, font=label_font)
    pill_w = min(area_box[2] - area_box[0] + 72, 920)
    draw.rounded_rectangle((78, 104, 78 + pill_w, 178), radius=37, fill="#ffffff")
    draw.text((114, 119), area_label, fill="#151515", font=label_font)

    name_lines = wrap_text(draw, restaurant_name, title_font, 950)[:3]
    line_height = 92
    y = 1588
    for line in name_lines:
        box = draw.textbbox((0, 0), line, font=title_font)
        draw.text(((width - (box[2] - box[0])) / 2, y), line, fill="#ffffff", font=title_font)
        y += line_height

    draw.line((160, 1844, 920, 1844), fill="#ffffff", width=4)
    draw.text((320, 1868), "詳しくはフィード投稿へ", fill="#ffffff", font=small_font)

    output = MEDIA_DIR / f"{review['review_id']}_story.jpg"
    bg.convert("RGB").save(output, quality=94)
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
