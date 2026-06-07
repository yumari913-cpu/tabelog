import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from cli import cmd_sync, cmd_threads_engage, cmd_threads_tick
from tabelog_insta.config import load_config
from tabelog_insta.media import export_instagram_package, generate_feed_cover_image, generate_story_image
from tabelog_insta.storage import get_review, load_reviews, update_review


HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))


def esc(value):
    return html.escape(str(value or ""))


def layout(title, body):
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", sans-serif; color: #24140e; background: #fffaf3; }}
    header {{ padding: 20px 28px; background: #ea580c; color: white; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 28px; }}
    a {{ color: #c2410c; text-decoration: none; }}
    .toolbar {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
    .btn {{ display: inline-block; border: 0; border-radius: 8px; padding: 10px 14px; background: #ea580c; color: white; cursor: pointer; }}
    .btn.secondary {{ background: #7c2d12; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }}
    .card {{ background: white; border: 1px solid #fed7aa; border-radius: 8px; padding: 16px; }}
    .meta {{ color: #7c2d12; font-size: 13px; }}
    .status {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #ffedd5; color: #9a3412; font-size: 12px; }}
    textarea {{ width: 100%; min-height: 280px; box-sizing: border-box; border: 1px solid #fed7aa; border-radius: 8px; padding: 12px; font: inherit; }}
    img.preview {{ width: 100%; max-height: 260px; object-fit: cover; border-radius: 8px; background: #ffedd5; }}
  </style>
</head>
<body>
  <header><h1>{esc(title)}</h1></header>
  <main>{body}</main>
</body>
</html>"""


def index_page():
    reviews = load_reviews()
    cards = []
    for review in reviews:
        image = ""
        if review.get("image_urls"):
            image = f'<img class="preview" src="{esc(review["image_urls"][0])}" alt="">'
        cards.append(f"""
        <article class="card">
          {image}
          <p><span class="status">{esc(review.get("status"))}</span></p>
          <h2>{esc(review.get("restaurant_name"))}</h2>
          <p class="meta">{esc(review.get("area_category"))}</p>
          <p>{esc(review.get("review_title"))}</p>
          <p class="meta">{esc(review.get("visited_date"))} / 評価 {esc(review.get("rating"))}</p>
          <p><a class="btn" href="/review?id={esc(review["review_id"])}">下書きを確認</a></p>
        </article>
        """)
    body = f"""
    <div class="toolbar">
      <a class="btn" href="/howto">運用手順</a>
    </div>
    <p>取り込み済み: {len(reviews)}件</p>
    <div class="grid">{''.join(cards) if cards else '<p>まだ取り込みがありません。まずCLIで backfill を実行してください。</p>'}</div>
    """
    return layout("食べログ to Instagram", body)


def review_page(review_id):
    review = get_review(review_id)
    if not review:
        return layout("レビューが見つかりません", "<p>指定したレビューが見つかりません。</p>")
    images = "".join(f'<img class="preview" src="{esc(url)}" alt="">' for url in review.get("image_urls", [])[:3])
    body = f"""
    <p><a href="/">一覧へ戻る</a></p>
    <h2>{esc(review.get("restaurant_name"))}</h2>
    <p class="meta">{esc(review.get("area_category"))}</p>
    <p><a href="{esc(review.get("review_url"))}" target="_blank">食べログ投稿を見る</a></p>
    <div class="grid">{images}</div>
    <form method="post" action="/save">
      <input type="hidden" name="review_id" value="{esc(review_id)}">
      <h3>Instagramフィード用キャプション</h3>
      <textarea name="caption">{esc(review.get("caption"))}</textarea>
      <p>
        <button class="btn" type="submit">保存</button>
        <button class="btn secondary" name="make_cover" value="1" type="submit">フィード1枚目画像を作成</button>
        <button class="btn secondary" name="make_story" value="1" type="submit">ストーリーズ画像を作成</button>
        <button class="btn secondary" name="make_package" value="1" type="submit">投稿パッケージを作成</button>
      </p>
    </form>
    """
    return layout(review.get("restaurant_name", "レビュー"), body)


def howto_page():
    config = load_config()
    ready = bool(config.get("instagram", {}).get("ig_user_id") and config.get("instagram", {}).get("access_token"))
    threads_ready = bool(config.get("threads", {}).get("user_id") and config.get("threads", {}).get("access_token"))
    body = f"""
    <p><a href="/">一覧へ戻る</a></p>
    <h2>運用手順</h2>
    <ol>
      <li>新規投稿確認は Cloud Scheduler の /sync で実行します。</li>
      <li>Threads投稿は /threads/tick で、JSTの投稿枠に到達していれば1本投稿します。</li>
      <li>Threads返信は /threads/engage で、自投稿への返信だけを処理します。</li>
    </ol>
    <p>Instagram認証情報: {'設定済み' if ready else '未設定'}</p>
    <p>Threads認証情報: {'設定済み' if threads_ready else '未設定'}</p>
    """
    return layout("運用手順", body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.respond(index_page())
        elif parsed.path == "/healthz":
            self.respond("ok", content_type="text/plain; charset=utf-8")
        elif parsed.path == "/review":
            review_id = parse_qs(parsed.query).get("id", [""])[0]
            self.respond(review_page(review_id))
        elif parsed.path == "/howto":
            self.respond(howto_page())
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/save":
            if parsed.path == "/sync":
                self.handle_sync()
                return
            if parsed.path == "/threads/tick":
                self.handle_threads_tick()
                return
            if parsed.path == "/threads/engage":
                self.handle_threads_engage()
                return
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        data = parse_qs(self.rfile.read(length).decode("utf-8"))
        review_id = data.get("review_id", [""])[0]
        caption = data.get("caption", [""])[0]
        changes = {"caption": caption}
        if data.get("make_story"):
            review = get_review(review_id)
            if review:
                path = generate_story_image(review)
                changes["story_image"] = str(path)
        if data.get("make_cover"):
            review = get_review(review_id)
            if review:
                path = generate_feed_cover_image(review)
                changes["feed_cover_image"] = str(path)
        if data.get("make_package"):
            review = get_review(review_id)
            if review:
                path = export_instagram_package(review)
                changes["instagram_package"] = str(path)
        update_review(review_id, changes)
        self.send_response(303)
        self.send_header("Location", f"/review?id={review_id}")
        self.end_headers()

    def respond(self, html_body, content_type="text/html; charset=utf-8"):
        encoded = html_body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def handle_sync(self):
        config = load_config()
        expected = config.get("sync_token")
        provided = self.headers.get("X-Sync-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
        if not expected or provided != expected:
            self.send_error(403)
            return

        class Args:
            limit = None

        cmd_sync(Args())
        self.respond("synced", content_type="text/plain; charset=utf-8")

    def handle_threads_tick(self):
        config = load_config()
        expected = config.get("sync_token")
        provided = self.headers.get("X-Sync-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
        if not expected or provided != expected:
            self.send_error(403)
            return

        class Args:
            dry_run = False

        cmd_threads_tick(Args())
        self.respond("threads ticked", content_type="text/plain; charset=utf-8")

    def handle_threads_engage(self):
        config = load_config()
        expected = config.get("sync_token")
        provided = self.headers.get("X-Sync-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
        if not expected or provided != expected:
            self.send_error(403)
            return

        class Args:
            dry_run = False
            limit = 3

        cmd_threads_engage(Args())
        self.respond("threads engaged", content_type="text/plain; charset=utf-8")


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"管理画面: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
