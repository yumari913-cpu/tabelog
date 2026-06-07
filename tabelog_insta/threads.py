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
DEFAULT_SCHEDULE_HOURS = [7, 8, 10, 12, 13, 15, 18, 19, 20, 22]
DEFAULT_SCHEDULE_MINUTES = [2, 7, 13, 18, 24, 31, 37, 43, 49, 55]
POST_STYLE_VERSION = "salaryman-shimbashi-v1"
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
        "instagram_url": review.get("instagram_url") or review.get("instagram_post_url") or "",
    }


def build_post_text(template_index, seed, profile_url):
    restaurant = seed["restaurant"]
    area = seed["area"]
    title = seed["title"]
    rating = seed["rating"]
    instagram_url = (seed.get("instagram_url") or profile_url).rstrip("/")
    templates = [
        f"新橋勤務の昼メシ候補メモ。\n{area}で「今日は外したくない」時に、{restaurant}は覚えておきたい店。\n\n{title}\n\n写真付きの実食メモはこちら。\n{instagram_url}",
        f"サラリーマンの店選び、結局大事なのは「駅から近い・うまい・財布が痛すぎない」だと思ってます。\n\n今日の候補: {restaurant}\nエリア: {area}\n食べログ評価: {rating or '-'}\n\n実際の写真はこのメモにまとめています。\n{instagram_url}",
        f"新橋で働いていると、昼も夜も店選びの失敗が地味に効く。\n\n{area}なら、まず{restaurant}を候補に入れておくと安心。\n会食というより、ちゃんと腹を満たしたい日のメモです。",
        f"{area}グルメメモ。\n{restaurant}は「{title}」という印象。\n\n仕事終わりに寄るならこういう店の選択肢を何個か持っておきたい。",
        f"食べログを見る時、点数だけで決めるとたまに外すので、直近写真と口コミの熱量も見る派です。\n\n今回見てきた店: {restaurant}\nエリア: {area}\n\n写真付きメモはこちら。\n{instagram_url}",
        f"午後の仕事を乗り切るには、昼メシ選びがかなり大事。\n\n今日は{area}の{restaurant}をメモ。\n{title}\n\n新橋・上野あたりで働く人の店選びに使えるはず。",
        f"「あとで行く店」は、見つけた瞬間に保存しないとだいたい忘れます。\n\n今日の保存候補は{restaurant}。\n{area}で飲み・ごはんを探す時の引き出しにどうぞ。",
        f"新橋勤務目線の都内グルメメモ。\n\n{area}で飲み・ごはん候補を増やしたい人は、{restaurant}をチェックしてみてください。\n実食写真はこちらに置いてます。\n{instagram_url}",
        f"お店選びで見ているポイント。\n1. 駅から近い\n2. 写真がちゃんとうまそう\n3. 直近口コミが荒れてない\n4. 仕事終わりでも入りやすい\n\n今回のメモは{area}の{restaurant}です。",
        f"今日のサラリーマングルメメモ: {restaurant}\n\n{title}\n\n新橋・上野・都内中心に、実際に行った店を写真付きで残しています。\n{instagram_url}",
    ]
    return templates[template_index % len(templates)][:500]


def planned_post_key(date_text, slot_index):
    return f"{date_text}-{slot_index:02d}"


def scheduled_minute_for(rng, schedule_minutes, index):
    base_minute = schedule_minutes[index % len(schedule_minutes)]
    minute = (base_minute + rng.randrange(0, 4) * 2) % 60
    return 2 if minute == 0 else minute


def ensure_daily_plan(config, date_text=None):
    date_text = date_text or datetime.now(JST).date().isoformat()
    threads_config = config.get("threads", {})
    posts_per_day = int(threads_config.get("posts_per_day", 10))
    profile_url = threads_config.get("instagram_profile_url", "https://www.instagram.com/mogmogtro112233/")
    schedule_hours = threads_config.get("schedule_hours") or DEFAULT_SCHEDULE_HOURS
    schedule_minutes = threads_config.get("schedule_minutes") or DEFAULT_SCHEDULE_MINUTES
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
        review = ordered_reviews[index % len(ordered_reviews)]
        seed = review_seed(review)
        scheduled_hour = schedule_hours[index % len(schedule_hours)]
        minute_rng = random.Random(f"{date_text}-{index}-minute")
        scheduled_minute = scheduled_minute_for(minute_rng, schedule_minutes, index)
        text = build_post_text(index, seed, profile_url)
        if key in existing_keys:
            for post in posts:
                if post.get("key") != key or post.get("status") != "planned":
                    continue
                if post.get("style_version") == POST_STYLE_VERSION and post.get("scheduled_minute") is not None:
                    break
                post["scheduled_hour"] = scheduled_hour
                post["scheduled_minute"] = scheduled_minute
                post["text"] = text
                post["style_version"] = POST_STYLE_VERSION
                post["updated_at"] = now_iso()
                break
            continue
        post = {
            "key": key,
            "date": date_text,
            "slot_index": index,
            "scheduled_hour": scheduled_hour,
            "scheduled_minute": scheduled_minute,
            "status": "planned",
            "review_id": review.get("review_id"),
            "restaurant_name": review.get("restaurant_name"),
            "text": text,
            "style_version": POST_STYLE_VERSION,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        posts.append(post)
        created.append(post)
    if created or any(post.get("date") == date_text and post.get("style_version") == POST_STYLE_VERSION for post in posts):
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
        and (int(post.get("scheduled_hour", 24)), int(post.get("scheduled_minute", 0))) <= (now.hour, now.minute)
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
