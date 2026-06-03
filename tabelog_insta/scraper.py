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
        "image_urls": image_urls[:10],
        "caption": build_caption(restaurant_name, area_category, review_title, body, rating, review_url, []),
    }


def build_caption(restaurant_name, area_category, review_title, body, rating, review_url, hashtags):
    area = area_category.split("/")[0].replace("（", "").replace("）", "").strip()
    genre = area_category.split("/")[-1].strip() if "/" in area_category else ""
    summary_source = body or review_title
    summary = re.sub(r"\s+", " ", summary_source).strip()
    if len(summary) > 170:
        summary = summary[:170].rstrip() + "..."

    parts = []
    heading = f"【{restaurant_name}】"
    if rating:
        heading += f"\n食べログ評価: {rating}"
    parts.append(heading)

    if area:
        parts.append(f"場所: {area}")
    if genre:
        parts.append(f"ジャンル: {genre}")

    if review_title:
        parts.append(f"今回のひとこと\n{review_title}")

    if summary:
        parts.append(f"推しポイント\n{summary}")

    parts.append("こんな時におすすめ\n・近くでごはんを探している時\n・外さないお店を保存しておきたい時")
    parts.append("気になったら保存して、次のお店選びにどうぞ。")

    if hashtags:
        tag_text = " ".join(hashtags[:25])
        parts.append(tag_text)

    parts.append(f"食べログ詳細: {review_url}")
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
