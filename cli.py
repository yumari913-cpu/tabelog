import argparse
import sys

from tabelog_insta.config import load_config
from tabelog_insta.instagram import InstagramClient, public_url_for
from tabelog_insta.media import export_instagram_package, generate_feed_cover_image, generate_reel_video, generate_story_image, upload_media
from tabelog_insta.scraper import build_caption, scrape_reviews
from tabelog_insta.storage import get_review, load_reviews, mark_posted, update_review, upsert_reviews
from tabelog_insta.threads import ThreadsClient, engage_with_replies, ensure_daily_plan, publish_due_post


def enrich_caption(review, config):
    caption = build_caption(
        review.get("restaurant_name", ""),
        review.get("area_category", ""),
        review.get("review_title", ""),
        review.get("body", ""),
        review.get("rating", ""),
        review.get("review_url", ""),
        config.get("hashtags", []),
    )
    review["caption"] = caption
    return review


def cmd_backfill(args):
    config = load_config()
    reviews = scrape_reviews(config["tabelog_reviewer_url"], max_pages=args.pages, limit=args.limit)
    reviews = [enrich_caption(review, config) for review in reviews]
    added, updated = upsert_reviews(reviews)
    print(f"取り込み完了: 追加 {len(added)}件 / 更新 {len(updated)}件")


def cmd_sync(args):
    config = load_config()
    reviews = scrape_reviews(config["tabelog_reviewer_url"], max_pages=1, limit=args.limit)
    reviews = [enrich_caption(review, config) for review in reviews]
    added, updated = upsert_reviews(reviews)
    print(f"新規チェック完了: 追加 {len(added)}件 / 更新 {len(updated)}件")
    publish_new_reviews_if_enabled(added, config)


def cmd_list(args):
    reviews = load_reviews()
    for review in reviews:
        print(f"{review['review_id']} [{review.get('status')}] {review.get('restaurant_name')} - {review.get('review_title')}")


def cmd_refresh_captions(args):
    config = load_config()
    reviews = [enrich_caption(review, config) for review in load_reviews()]
    from tabelog_insta.storage import save_reviews

    save_reviews(reviews)
    print(f"キャプションを更新しました: {len(reviews)}件")


def cmd_story(args):
    review = get_review(args.review_id)
    if not review:
        raise SystemExit("指定したレビューが見つかりません。")
    path = generate_story_image(review)
    update_review(args.review_id, {"story_image": str(path)})
    print(f"ストーリーズ画像を作成しました: {path}")


def cmd_cover(args):
    review = get_review(args.review_id)
    if not review:
        raise SystemExit("指定したレビューが見つかりません。")
    path = generate_feed_cover_image(review)
    update_review(args.review_id, {"feed_cover_image": str(path)})
    print(f"フィード1枚目画像を作成しました: {path}")


def cmd_export(args):
    review = get_review(args.review_id)
    if not review:
        raise SystemExit("指定したレビューが見つかりません。")
    path = export_instagram_package(review)
    update_review(args.review_id, {"instagram_package": str(path)})
    print(f"Instagram投稿パッケージを作成しました: {path}")


def cmd_reel(args):
    review = get_review(args.review_id)
    if not review:
        raise SystemExit("指定したレビューが見つかりません。")
    path = generate_reel_video(review)
    update_review(args.review_id, {"reel_video": str(path)})
    print(f"リール動画を作成しました: {path}")


def cmd_publish(args):
    config = load_config()
    review = get_review(args.review_id)
    if not review:
        raise SystemExit("指定したレビューが見つかりません。")
    publish_review(review, args.targets.split(","), config)


def cmd_threads_plan(args):
    config = load_config()
    created, planned = ensure_daily_plan(config, args.date)
    print(f"Threads投稿計画: 作成 {len(created)}件 / 当日合計 {len(planned)}件")
    for post in planned:
        print(f"[{post['slot_index'] + 1:02d}] {post['scheduled_hour']:02d}:00 {post['restaurant_name']}")
        print(post["text"])
        print()


def cmd_threads_tick(args):
    config = load_config()
    if not args.dry_run and not config.get("threads", {}).get("auto_publish", False):
        raise SystemExit("THREADS_AUTO_PUBLISH=true または config.json の threads.auto_publish=true が必要です。")
    if not args.dry_run and not ThreadsClient(config).ready:
        raise SystemExit("THREADS_USER_ID と THREADS_ACCESS_TOKEN が必要です。")
    post = publish_due_post(config, dry_run=args.dry_run)
    if not post:
        print("Threads投稿枠はまだありません。")
        return
    if args.dry_run:
        print("DRY RUN: 次に投稿される予定の本文です。")
        print(post["text"])
    else:
        print(f"Threads投稿完了: {post.get('threads_post_id') or post.get('threads_response')}")


def cmd_threads_me(args):
    config = load_config()
    client = ThreadsClient(config)
    print(client.me())


def cmd_threads_engage(args):
    config = load_config()
    if not args.dry_run and not config.get("threads", {}).get("auto_reply", False):
        raise SystemExit("THREADS_AUTO_REPLY=true または config.json の threads.auto_reply=true が必要です。")
    if not args.dry_run and not ThreadsClient(config).ready:
        raise SystemExit("THREADS_USER_ID と THREADS_ACCESS_TOKEN が必要です。")
    handled = engage_with_replies(config, limit=args.limit, dry_run=args.dry_run)
    print(f"Threads返信処理: {len(handled)}件")
    if args.dry_run:
        for item in handled:
            print(f"{item['reply_id']}: {item['text']}")


def publish_new_reviews_if_enabled(reviews, config):
    targets = [name for name, enabled in config.get("auto_publish", {}).items() if enabled]
    if not targets:
        return
    for review in reviews:
        publish_review(review, targets, config)


def publish_review(review, targets, config):
    client = InstagramClient(config)
    if not client.ready:
        raise SystemExit("Instagram認証情報が未設定です。config.jsonを設定してください。")

    for target in targets:
        target = target.strip()
        if not target:
            continue
        if target == "feed":
            cover_path = generate_feed_cover_image(review)
            cover_url = upload_media(config, cover_path)
            if not cover_url:
                raise SystemExit("storage_bucketが未設定のため、フィードカバー画像を公開できません。")
            image_urls = [cover_url] + (review.get("image_urls") or [])[:9]
            result = client.publish_carousel(image_urls, review.get("caption", ""))
        elif target == "story":
            story_path = generate_story_image(review)
            image_url = public_url_for(config, story_path)
            if not image_url:
                raise SystemExit("public_base_urlが未設定です。")
            result = client.publish_story(image_url)
        elif target == "reel":
            reel_path = generate_reel_video(review)
            video_url = public_url_for(config, reel_path)
            if not video_url:
                raise SystemExit("public_base_urlが未設定です。")
            result = client.publish_reel(video_url, review.get("caption", ""))
        else:
            raise SystemExit(f"未対応の投稿先です: {target}")
        mark_posted(review["review_id"], target, result)
        print(f"{target} 投稿完了: {result}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)

    backfill = sub.add_parser("backfill")
    backfill.add_argument("--pages", type=int, default=10)
    backfill.add_argument("--limit", type=int)
    backfill.set_defaults(func=cmd_backfill)

    sync = sub.add_parser("sync")
    sync.add_argument("--limit", type=int)
    sync.set_defaults(func=cmd_sync)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=cmd_list)

    refresh = sub.add_parser("refresh-captions")
    refresh.set_defaults(func=cmd_refresh_captions)

    story = sub.add_parser("story")
    story.add_argument("review_id")
    story.set_defaults(func=cmd_story)

    cover = sub.add_parser("cover")
    cover.add_argument("review_id")
    cover.set_defaults(func=cmd_cover)

    export = sub.add_parser("export")
    export.add_argument("review_id")
    export.set_defaults(func=cmd_export)

    reel = sub.add_parser("reel")
    reel.add_argument("review_id")
    reel.set_defaults(func=cmd_reel)

    publish = sub.add_parser("publish")
    publish.add_argument("review_id")
    publish.add_argument("--targets", default="feed")
    publish.set_defaults(func=cmd_publish)

    threads_plan = sub.add_parser("threads-plan")
    threads_plan.add_argument("--date")
    threads_plan.set_defaults(func=cmd_threads_plan)

    threads_tick = sub.add_parser("threads-tick")
    threads_tick.add_argument("--dry-run", action="store_true")
    threads_tick.set_defaults(func=cmd_threads_tick)

    threads_me = sub.add_parser("threads-me")
    threads_me.set_defaults(func=cmd_threads_me)

    threads_engage = sub.add_parser("threads-engage")
    threads_engage.add_argument("--limit", type=int, default=3)
    threads_engage.add_argument("--dry-run", action="store_true")
    threads_engage.set_defaults(func=cmd_threads_engage)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
