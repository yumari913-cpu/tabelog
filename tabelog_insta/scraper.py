import html
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://tabelog.com"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) TabelogInstagramBot/1.0"


def fetch(url):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="replace")


def clean_text(value):
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"\r", "", value)
    value = re.sub(r"\n\s*\n+", "\n\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def meta_content(source, prop):
    pattern = rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, source, re.I)
    return html.unescape(match.group(1)) if match else ""


def extract_review_id(url):
    match = re.search(r"/rvwdtl/(B\d+)/", url)
    return match.group(1) if match else url.rstrip("/").split("/")[-1]


def extract_review_links(source, page_url):
    urls = set()
    for match in re.finditer(r'data-detail-url=["\']([^"\']*/rvwdtl/B\d+/)["\']', source):
        urls.add(urljoin(page_url, html.unescape(match.group(1))))
    for match in re.finditer(r'href=["\']([^"\']*/rvwdtl/B\d+/)["\']', source):
        urls.add(urljoin(page_url, html.unescape(match.group(1))))
    return sorted(urls)


def extract_next_page(source):
    match = re.search(r'<a[^>]+rel=["\']next["\'][^>]+href=["\']([^"\']+)["\']', source)
    if match:
        return html.unescape(match.group(1))
    match = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']next["\']', source)
    if match:
        return html.unescape(match.group(1))
    match = re.search(r'<link[^>]+rel=["\']next["\'][^>]+href=["\']([^"\']+)["\']', source)
    if match:
        return html.unescape(match.group(1))
    match = re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']next["\']', source)
    return html.unescape(match.group(1)) if match else None


def list_review_urls(reviewer_url, max_pages=10, sleep_seconds=1.0):
    base = reviewer_url.rstrip("/") + "/reviewed_restaurants/list/?SrtT=ud&Srt=D&review_content_exist=0"
    url = base
    seen_pages = set()
    review_urls = []
    seen_reviews = set()

    for _ in range(max_pages):
        if not url or url in seen_pages:
            break
        seen_pages.add(url)
        source = fetch(url)
        for review_url in extract_review_links(source, url):
            if review_url not in seen_reviews:
                seen_reviews.add(review_url)
                review_urls.append(review_url)
        url = extract_next_page(source)
        if url:
            time.sleep(sleep_seconds)

    return review_urls


def parse_detail(review_url):
    source = fetch(review_url)
    review_id = extract_review_id(review_url)

    restaurant_match = re.search(
        r'<a class=["\']rvw-item__rst-name["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
        r'\s*<span class=["\']rvw-item__rst-area-catg["\']>(.*?)</span>',
        source,
        re.S,
    )
    restaurant_name = clean_text(restaurant_match.group(2)) if restaurant_match else meta_content(source, "og:title")
    restaurant_url = html.unescape(restaurant_match.group(1)) if restaurant_match else ""
    area_category = clean_text(restaurant_match.group(3)) if restaurant_match else ""

    title_match = re.search(r'<p class=["\']rvw-item__title["\'][^>]*>\s*(?:<[^>]+>)*\s*(.*?)\s*</p>', source, re.S)
    if not title_match:
        title_match = re.search(r'<p class=["\']rvw-item__title[^"\']*["\'][^>]*>.*?<strong>(.*?)</strong>', source, re.S)
    review_title = clean_text(title_match.group(1)) if title_match else ""

    comment_match = re.search(
        r'<div class=["\']rvw-item__rvw-comment["\'][^>]*property=["\']v:description["\'][^>]*>(.*?)</div>',
        source,
        re.S,
    )
    if not comment_match:
        comment_match = re.search(r'<div class=["\']rvw-item__rvw-comment[^"\']*["\'][^>]*>(.*?)</div>', source, re.S)
    body = clean_text(comment_match.group(1)) if comment_match else ""

    rating_match = re.search(r'<b class=["\'][^"\']*c-rating-v2__val[^"\']*["\'][^>]*>([\d.]+)</b>', source)
    rating = rating_match.group(1) if rating_match else ""

    visited_match = re.search(r'<span class=["\']rvw-item__visited-date["\']>(.*?)</span>', source, re.S)
    visited_date = clean_text(visited_match.group(1)).replace("\xa0", " ") if visited_match else ""

    image_urls = []
    for image_match in re.finditer(r'<a[^>]+class=["\'][^"\']*js-imagebox-trigger[^"\']*["\'][^>]+href=["\']([^"\']+)["\']', source):
        image_url = html.unescape(image_match.group(1))
        if image_url not in image_urls:
            image_urls.append(image_url)
    og_image = meta_content(source, "og:image")
    if og_image and og_image not in image_urls:
        image_urls.insert(0, og_image)

    return {
        "review_id": review_id,
        "review_url": review_url,
        "restaurant_name": restaurant_name,
        "restaurant_url": restaurant_url,
        "area_category": area_category,
        "review_title": review_title,
        "body": body,
        "rating": rating,
        "visited_date": visited_date,
        "image_urls": image_urls[:20],
        "caption": build_caption(restaurant_name, area_category, review_title, body, rating, review_url, []),
    }


def area_hashtags(area_category):
    area = area_category.split("/")[0].replace("（", "").replace("）", "").strip()
    tags = []
    for value in re.split(r"[、,\s]+", area):
        value = re.sub(r"[^\wぁ-んァ-ヶ一-龠ー]", "", value)
        if value and f"#{value}" not in tags:
            tags.append(f"#{value}")
    return tags


def compact_summary(text, limit=170):
    summary = re.sub(r"\s+", " ", text or "").strip()
    if len(summary) > limit:
        summary = summary[:limit].rstrip() + "..."
    return summary


def first_area(area_category):
    area = area_category.split("/")[0].replace("（", "").replace("）", "").strip()
    values = [value for value in re.split(r"[、,\s]+", area) if value]
    return values[0] if values else area


def caption_genre(area_category):
    if "/" in area_category:
        genre = area_category.split("/")[-1].strip()
        return genre or "グルメ"
    return "グルメ"


def build_hashtags(area_category, genre, hashtags):
    base_tags = area_hashtags(area_category)
    genre_tags = []
    for value in re.split(r"[、,\s]+", genre):
        value = re.sub(r"[^\wぁ-んァ-ヶ一-龠ー]", "", value)
        if value:
            genre_tags.append(f"#{value}")

    defaults = [
        "#食べログ",
        "#グルメ",
        "#東京グルメ",
        "#東京ランチ",
        "#東京ディナー",
        "#外食記録",
        "#グルメ好きな人と繋がりたい",
        "#グルメ巡り",
        "#ランチ巡り",
        "#ディナー巡り",
        "#保存推奨",
        "#正直グルメ",
        "#コスパグルメ",
        "#デートごはん",
        "#ひとりごはん",
        "#居酒屋巡り",
        "#食べ歩き",
        "#おいしいもの好きな人と繋がりたい",
    ]

    tags = []
    for tag in base_tags + genre_tags + list(hashtags) + defaults:
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:20]


def build_caption(restaurant_name, area_category, review_title, body, rating, review_url, hashtags, style="story"):
    area = area_category.split("/")[0].replace("（", "").replace("）", "").strip()
    lead_area = first_area(area_category)
    genre = caption_genre(area_category)
    title_source = review_title or f"{restaurant_name}で楽しむ{genre}"
    title = compact_summary(title_source, 34)
    report = compact_summary(body or review_title, 230)

    if lead_area and genre:
        catch = f"【{lead_area}×{genre}】保存して行きたい、{title}"
    elif lead_area:
        catch = f"【{lead_area}グルメ】保存して行きたい、{title}"
    else:
        catch = f"【保存推奨グルメ】{title}"

    intro_area = lead_area or "このエリア"
    parts = [
        f"{catch} 🍽️",
        f"【導入】\nここ知らなきゃ損。{intro_area}で次のごはん候補に入れたい一軒です。",
    ]

    if report:
        parts.append(
            "【料理のレポ】\n見た目から食欲をそそられて、ひと口目でしっかり満足感。 "
            f"{report}"
        )
    else:
        parts.append("【料理のレポ】\n料理の詳しい内容は（※要確認）。気になるメニューがあれば、投稿前に追記するとより保存されやすくなります。")

    scene_lines = [
        "【お店の雰囲気・利用シーン】",
        "気取らず楽しめる雰囲気で、友達とのごはんや仕事帰りの一軒にも使いやすそう。✨",
        "ひとりでサクッと寄りたい日にも、誰かとゆっくり話したい日にも候補に入れておきたいお店です。",
    ]
    parts.append("\n".join(scene_lines))

    parts.append("【保存の促し】\n後で見返せるように【保存】がおすすめです。次のお店選びに使ってください。")

    parts.append(
        "\n".join(
            [
                "【店舗情報】",
                f"・店舗名：{restaurant_name or '（※要確認）'}",
                f"・アクセス：{area or '（※要確認）'}",
                "・営業時間：（※要確認）",
                "・定休日：（※要確認）",
                "・客層・混雑状況：（※要確認）",
                f"・食べログ詳細：{review_url}",
            ]
        )
    )

    tag_line = " ".join(build_hashtags(area_category, genre, hashtags))
    if tag_line:
        parts.append("【ハッシュタグ】\n" + tag_line)
    return "\n\n".join(parts)


def scrape_reviews(reviewer_url, max_pages=10, limit=None):
    urls = list_review_urls(reviewer_url, max_pages=max_pages)
    if limit:
        urls = urls[:limit]
    reviews = []
    for url in urls:
        reviews.append(parse_detail(url))
        time.sleep(1.0)
    return reviews
