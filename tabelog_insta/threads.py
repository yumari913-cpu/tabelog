import json
import random
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .config import DATA_DIR, ensure_dirs
from .storage import gcs_bucket, load_reviews, now_iso


THREADS_DB_PATH = DATA_DIR / "threads_posts.json"
THREADS_DB_BLOB_NAME = "data/threads_posts.json"
DEFAULT_SCHEDULE_HOURS = [8, 10, 11, 12, 14, 16, 18, 19, 20, 22]
JST = ZoneInfo("Asia/Tokyo")


class ThreadsClient:
    def __init__(self, config):
        threads = config.get("threads", {})
        self.graph_base_url = threads.get("graph_base_url", "https://graph.threads.net/v1.0").rstrip("/")
        self.user_id = threads.get("user_id", "")
        self.access_token = threads.get("access_token", "")

    @property
    def ready(self):
        return bool(self.user_id and self.access_token)

    @property
    def token_ready(self):
        return bool(self.access_token)

    def _request(self, method, path, params=None):
        if not self.ready:
            raise RuntimeError("Threads credentials are not configured.")
        params = dict(params or {})
        params["access_token"] = self.access_token
        url = f"{self.graph_base_url}/{path.lstrip('/')}"
        data = None
        if method == "GET":
            url = f"{url}?{urlencode(params)}"
        else:
            data = urlencode(params).encode("utf-8")
        req = Request(url, data=data, method=method)
        try:
            with urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Threads API error {exc.code}: {body}") from exc

    def me(self):
        if not self.token_ready:
            raise RuntimeError("Threads access token is not configured.")
        params = {"fields": "id,username", "access_token": self.access_token}
        url = f"{self.graph_base_url}/me?{urlencode(params)}"
        req = Request(url, method="GET")
        try:
            with urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Threads API error {exc.code}: {body}") from exc

    def create_container(self, text, media_type="TEXT", image_url=None, reply_to_id=None):
        params = {"media_type": media_type, "text": text}
        if image_url:
            params["image_url"] = image_url
        if reply_to_id:
            params["reply_to_id"] = reply_to_id
        return self._request("POST", f"{self.user_id}/threads", params)

    def publish_container(self, creation_id):
        return self._request("POST", f"{self.user_id}/threads_publish", {"creation_id": creation_id})

    def publish_text(self, text):
        container = self.create_container(text=text)
        return self.publish_container(container["id"])

    def reply(self, post_id, text):
        container = self.create_container(text=text, reply_to_id=post_id)
        return self.publish_container(container["id"])

    def replies(self, post_id):
        return self._request("GET", f"{post_id}/replies", {"fields": "id,text,username,timestamp"})


def load_threads_posts():
    ensure_dirs()
    bucket = gcs_bucket()
    if bucket:
        blob = bucket.blob(THREADS_DB_BLOB_NAME)
        if not blob.exists():
            return []
        return json.loads(blob.download_as_text(encoding="utf-8"))
    if not THREADS_DB_PATH.exists():
        return []
    with THREADS_DB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_threads_posts(posts):
    ensure_dirs()
    bucket = gcs_bucket()
    if bucket:
        blob = bucket.blob(THREADS_DB_BLOB_NAME)
        blob.upload_from_string(
            json.dumps(posts, ensure_ascii=False, indent=2),
            content_type="application/json; charset=utf-8",
        )
        return
    with THREADS_DB_PATH.open("w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def compact(value, limit=90):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def area_name(review):
    return (review.get("area_category") or "").split("/")[0].replace("、", "・")


def review_seed(review):
    return {
        "restaurant": review.get("restaurant_name", "気になるお店"),
        "area": area_name(review) or "東京",
        "title": compact(review.get("review_title"), 80),
        "rating": review.get("rating", ""),
    }


def build_post_text(template_index, seed, profile_url):
    restaurant = seed["restaurant"]
    area = seed["area"]
    title = seed["title"]
    rating = seed["rating"]
    profile = profile_url.rstrip("/")
    templates = [
        f"{area}でお店探し中なら「{restaurant}」をメモ。\n{title}\n\n詳しい写真と感想はInstagramにまとめています。\n{profile}",
        f"今日の保存候補。\n\n店名: {restaurant}\nエリア: {area}\n食べログ評価: {rating or '-'}\n\n次の外食で迷った時に見返せるよう、Instagram側に写真つきで残しています。\n{profile}",
        f"外さないお店探しのコツは、料理だけでなく「誰と・何時に・どんな気分で行くか」まで決めて探すこと。\n\n{area}なら、まずは{restaurant}みたいな候補を保存しておくと便利です。",
        f"{area}グルメメモ。\n{restaurant}は「{title}」という印象でした。\n\n行ったことある方、推しメニューがあれば教えてください。",
        f"食べログを見る時は、点数だけでなく直近口コミと写真の新しさも見る派です。\n\n今回の候補: {restaurant}\nエリア: {area}\n\n写真はInstagramに載せています。\n{profile}",
        f"週末のごはん候補を探すなら、先にエリアを絞るのがおすすめ。\n\n今日は{area}の{restaurant}をピックアップ。\n{title}",
        f"「あとで行きたい店」は、見つけた瞬間に保存しておくのが一番強いです。\n\n今日の保存候補は{restaurant}。\n{area}でごはんを探す時にぜひ。",
        f"{area}で飲み・ごはんの候補を増やしたい人へ。\n\n{restaurant}の写真と感想をInstagramにまとめました。\n気になるお店探しに使ってください。\n{profile}",
        f"お店選びで見ているポイント。\n1. 駅からの行きやすさ\n2. 写真の雰囲気\n3. 直近口コミ\n4. 誰と行くか\n\n今回のメモは{area}の{restaurant}です。",
        f"今日のグルメメモ: {restaurant}\n\n{title}\n\n東京近辺の外食記録をInstagramに蓄積中です。\n{profile}",
    ]
    return templates[template_index % len(templates)][:500]


def planned_post_key(date_text, slot_index):
    return f"{date_text}-{slot_index:02d}"


def ensure_daily_plan(config, date_text=None):
    date_text = date_text or datetime.now(JST).date().isoformat()
    threads_config = config.get("threads", {})
    posts_per_day = int(threads_config.get("posts_per_day", 10))
    profile_url = threads_config.get("instagram_profile_url", "https://www.instagram.com/mogmogtro112233/")
    schedule_hours = threads_config.get("schedule_hours") or DEFAULT_SCHEDULE_HOURS
    reviews = [review for review in load_reviews() if review.get("restaurant_name")]
    if not reviews:
        raise RuntimeError("No reviews are available. Run sync first.")

    posts = load_threads_posts()
    existing_keys = {post.get("key") for post in posts}
    rng = random.Random(date_text)
    ordered_reviews = list(reviews)
    rng.shuffle(ordered_reviews)

    created = []
    for index in range(posts_per_day):
        key = planned_post_key(date_text, index)
        if key in existing_keys:
            continue
        review = ordered_reviews[index % len(ordered_reviews)]
        seed = review_seed(review)
        post = {
            "key": key,
            "date": date_text,
            "slot_index": index,
            "scheduled_hour": schedule_hours[index % len(schedule_hours)],
            "status": "planned",
            "review_id": review.get("review_id"),
            "restaurant_name": review.get("restaurant_name"),
            "text": build_post_text(index, seed, profile_url),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        posts.append(post)
        created.append(post)
    if created:
        posts.sort(key=lambda item: (item.get("date", ""), item.get("slot_index", 0)))
        save_threads_posts(posts)
    return created, [post for post in posts if post.get("date") == date_text]


def publish_due_post(config, dry_run=False, now=None):
    now = now or datetime.now(JST)
    date_text = now.date().isoformat()
    ensure_daily_plan(config, date_text)
    posts = load_threads_posts()
    due = [
        post
        for post in posts
        if post.get("date") == date_text
        and post.get("status") == "planned"
        and int(post.get("scheduled_hour", 24)) <= now.hour
    ]
    due.sort(key=lambda item: item.get("slot_index", 0))
    if not due:
        return None

    post = due[0]
    if dry_run:
        return post

    client = ThreadsClient(config)
    result = client.publish_text(post["text"])
    post["status"] = "posted"
    post["posted_at"] = now_iso()
    post["threads_response"] = result
    post["threads_post_id"] = result.get("id")
    post["updated_at"] = now_iso()
    save_threads_posts(posts)
    return post


def build_reply_text(reply_text, profile_url):
    text = str(reply_text or "")
    if any(word in text for word in ["場所", "どこ", "住所", "駅", "アクセス"]):
        return f"コメントありがとうございます！場所や写真はInstagram側にまとめています。よければお店選びに使ってください。\n{profile_url.rstrip('/')}"[:500]
    if any(word in text for word in ["おすすめ", "メニュー", "何", "なに"]):
        return "コメントありがとうございます！詳しい感想と写真を見返しながら、推しポイントもまた投稿でまとめます。"
    return "コメントありがとうございます！行ったことがあるお店や気になるエリアがあれば、ぜひ教えてください。"


def engage_with_replies(config, limit=3, dry_run=False):
    posts = load_threads_posts()
    client = ThreadsClient(config)
    profile_url = config.get("threads", {}).get("instagram_profile_url", "https://www.instagram.com/mogmogtro112233/")
    handled = []
    for post in posts:
        post_id = post.get("threads_post_id")
        if not post_id:
            continue
        replied_ids = set(post.get("replied_to_reply_ids", []))
        try:
            replies = client.replies(post_id).get("data", [])
        except Exception as exc:
            post["replies_error"] = str(exc)
            continue
        for reply in replies:
            reply_id = reply.get("id")
            if not reply_id or reply_id in replied_ids:
                continue
            reply_text = build_reply_text(reply.get("text", ""), profile_url)
            if dry_run:
                handled.append({"reply_id": reply_id, "text": reply_text})
            else:
                result = client.reply(reply_id, reply_text)
                post.setdefault("reply_results", []).append({"reply_id": reply_id, "replied_at": now_iso(), "text": reply_text, "response": result})
                post.setdefault("replied_to_reply_ids", []).append(reply_id)
                post["updated_at"] = now_iso()
                handled.append({"reply_id": reply_id, "response": result})
            if len(handled) >= limit:
                save_threads_posts(posts)
                return handled
    save_threads_posts(posts)
    return handled
