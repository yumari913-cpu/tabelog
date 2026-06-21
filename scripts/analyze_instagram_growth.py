import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabelog_insta.config import load_config
from tabelog_insta.instagram import InstagramClient


DEFAULT_METRICS = [
    "reach",
    "saved",
    "likes",
    "comments",
    "shares",
    "total_interactions",
    "profile_activity",
    "profile_visits",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def extract_area_genre(caption):
    caption = caption or ""
    title_match = re.search(r"【([^】]+)】", caption)
    area = ""
    genre = ""
    if title_match:
        title = title_match.group(1)
        if "×" in title:
            area, genre = [part.strip() for part in title.split("×", 1)]
        else:
            area = title.strip()

    hashtags = re.findall(r"#([^\s#]+)", caption)
    return area, genre, hashtags


def flatten_insights(response):
    values = {}
    for item in response.get("data", []):
        name = item.get("name")
        metric_values = item.get("values") or []
        if name and metric_values:
            values[name] = metric_values[0].get("value", "")
    return values


def fetch_metric_safely(client, media_id, metric):
    try:
        return flatten_insights(client.media_insights(media_id, [metric])).get(metric, "")
    except Exception as exc:
        return f"unsupported: {exc}"


def fetch_insights(client, media_id, metrics):
    insights = {}
    for metric in metrics:
        value = fetch_metric_safely(client, media_id, metric)
        insights[metric] = value
    return insights


def numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def score_candidate(comment_count, like_total):
    return (comment_count * 10) + like_total


def is_relevant_hashtag(tag):
    if not tag:
        return False
    keywords = ["グルメ", "ランチ", "ディナー", "カフェ", "中華", "焼肉", "寿司", "ラーメン", "居酒屋"]
    return any(keyword in tag for keyword in keywords)


def add_candidate(candidate_map, username, reason, permalink="", area="", genre="", text="", comment_likes=0, score=0):
    username = clean(username)
    if not username:
        return
    current = candidate_map.setdefault(
        username,
        {
            "created_at": now_iso(),
            "username": username,
            "reason": reason,
            "comment_count": 0,
            "comment_like_total": 0,
            "latest_comment": "",
            "latest_post_permalink": "",
            "latest_post_area": "",
            "latest_post_genre": "",
            "score": 0,
        },
    )
    if reason not in current.get("reason", ""):
        current["reason"] = f"{current.get('reason', '')} / {reason}".strip(" /")
    current["comment_count"] += 1 if text else 0
    current["comment_like_total"] += int(numeric(comment_likes))
    current["latest_comment"] = clean(text) or current.get("latest_comment", "")
    current["latest_post_permalink"] = permalink or current.get("latest_post_permalink", "")
    current["latest_post_area"] = area or current.get("latest_post_area", "")
    current["latest_post_genre"] = genre or current.get("latest_post_genre", "")
    current["score"] = max(int(numeric(current.get("score"))), int(numeric(score)))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def append_candidates(path, candidates):
    fieldnames = [
        "created_at",
        "username",
        "reason",
        "score",
        "comment_count",
        "comment_like_total",
        "latest_comment",
        "latest_post_permalink",
        "latest_post_area",
        "latest_post_genre",
        "status",
    ]
    existing = []
    seen = set()
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                existing.append(row)
                if row.get("username"):
                    seen.add(row["username"])

    new_rows = []
    for candidate in candidates:
        username = candidate.get("username", "")
        if username and username not in seen:
            candidate["status"] = "未確認"
            new_rows.append(candidate)
            seen.add(username)

    rows = existing + sorted(new_rows, key=lambda row: numeric(row.get("score")), reverse=True)
    write_csv(path, rows, fieldnames)
    return len(new_rows)


def build_summary(insight_rows, summary_path):
    ranked_by_reach = sorted(insight_rows, key=lambda row: numeric(row.get("reach")), reverse=True)
    ranked_by_saved = sorted(insight_rows, key=lambda row: numeric(row.get("saved")), reverse=True)

    by_area = defaultdict(lambda: {"posts": 0, "reach": 0.0, "saved": 0.0})
    by_genre = defaultdict(lambda: {"posts": 0, "reach": 0.0, "saved": 0.0})
    for row in insight_rows:
        for bucket, key in [(by_area, row.get("area") or "未分類"), (by_genre, row.get("genre") or "未分類")]:
            bucket[key]["posts"] += 1
            bucket[key]["reach"] += numeric(row.get("reach"))
            bucket[key]["saved"] += numeric(row.get("saved"))

    def lines_for(label, ranking):
        lines = [f"## {label}"]
        for row in ranking[:5]:
            lines.append(
                f"- {row.get('restaurant_name') or '投稿'} / "
                f"{row.get('area') or 'エリア不明'} / reach={row.get('reach', '')} / "
                f"saved={row.get('saved', '')} / {row.get('permalink', '')}"
            )
        return lines

    def bucket_lines(label, bucket):
        lines = [f"## {label}"]
        ranked = sorted(
            bucket.items(),
            key=lambda item: (item[1]["saved"], item[1]["reach"]),
            reverse=True,
        )
        for name, values in ranked[:8]:
            avg_reach = values["reach"] / values["posts"] if values["posts"] else 0
            avg_saved = values["saved"] / values["posts"] if values["posts"] else 0
            lines.append(
                f"- {name}: posts={values['posts']}, "
                f"avg_reach={avg_reach:.1f}, avg_saved={avg_saved:.1f}"
            )
        return lines

    content = [
        "# Instagram Growth Analysis",
        "",
        f"Generated at: {now_iso()}",
        "",
        *lines_for("Reach Top Posts", ranked_by_reach),
        "",
        *lines_for("Saved Top Posts", ranked_by_saved),
        "",
        *bucket_lines("Areas To Lean Into", by_area),
        "",
        *bucket_lines("Genres To Lean Into", by_genre),
        "",
        "## Next Actions",
        "- 保存数とリーチが高いエリア・ジャンルを次の投稿で優先する。",
        "- follow_candidates.csv の status が未確認の人を手動で確認する。",
        "- 明らかな営業・スパム・無関係アカウントはフォローしない。",
    ]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(content) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--comments-limit", type=int, default=50)
    parser.add_argument("--hashtag-limit", type=int, default=8)
    parser.add_argument("--hashtag-media-limit", type=int, default=8)
    parser.add_argument("--output-dir", default="analytics")
    args = parser.parse_args()

    client = InstagramClient(load_config())
    if not client.ready:
        raise SystemExit("IG_USER_ID and IG_ACCESS_TOKEN are required.")

    output_dir = Path(args.output_dir)
    media_items = client.user_media(limit=args.limit).get("data", [])
    insight_rows = []
    candidate_map = {}
    relevant_hashtags = []

    for media in media_items:
        media_id = media.get("id", "")
        caption = media.get("caption", "")
        area, genre, hashtags = extract_area_genre(caption)
        for tag in hashtags:
            if is_relevant_hashtag(tag) and tag not in relevant_hashtags:
                relevant_hashtags.append(tag)
        insights = fetch_insights(client, media_id, DEFAULT_METRICS)

        comments = []
        try:
            comments = client.media_comments(media_id, limit=args.comments_limit).get("data", [])
        except Exception as exc:
            comments = [{"username": "", "text": f"comments unsupported: {exc}", "like_count": 0}]

        for comment in comments:
            add_candidate(
                candidate_map,
                comment.get("username", ""),
                "コメントしてくれた人",
                permalink=media.get("permalink", ""),
                area=area,
                genre=genre,
                text=comment.get("text", ""),
                comment_likes=comment.get("like_count", 0),
            )

        restaurant_name = ""
        title_match = re.search(r"・店舗名：([^\n\r]+)", caption)
        if title_match:
            restaurant_name = clean(title_match.group(1))

        row = {
            "collected_at": now_iso(),
            "media_id": media_id,
            "timestamp": media.get("timestamp", ""),
            "media_type": media.get("media_type", ""),
            "permalink": media.get("permalink", ""),
            "restaurant_name": restaurant_name,
            "area": area,
            "genre": genre,
            "hashtags": " ".join(f"#{tag}" for tag in hashtags),
            "like_count": media.get("like_count", ""),
            "comments_count": media.get("comments_count", ""),
        }
        row.update(insights)
        insight_rows.append(row)

    for tag in relevant_hashtags[: args.hashtag_limit]:
        try:
            hashtag_data = client.hashtag_search(tag).get("data", [])
            if not hashtag_data:
                continue
            hashtag_id = hashtag_data[0].get("id")
            recent_posts = client.hashtag_recent_media(
                hashtag_id,
                limit=args.hashtag_media_limit,
            ).get("data", [])
        except Exception:
            continue

        for post in recent_posts:
            username = post.get("username", "")
            post_caption = post.get("caption", "")
            post_area, post_genre, _ = extract_area_genre(post_caption)
            engagement_score = int(numeric(post.get("like_count"))) + int(numeric(post.get("comments_count"))) * 5
            add_candidate(
                candidate_map,
                username,
                f"関連ハッシュタグ投稿者 #{tag}",
                permalink=post.get("permalink", ""),
                area=post_area,
                genre=post_genre,
                text=post_caption[:120],
                score=engagement_score,
            )

    for candidate in candidate_map.values():
        comment_score = score_candidate(
            int(numeric(candidate.get("comment_count"))),
            int(numeric(candidate.get("comment_like_total"))),
        )
        candidate["score"] = max(comment_score, int(numeric(candidate.get("score"))))

    insight_fields = [
        "collected_at",
        "media_id",
        "timestamp",
        "media_type",
        "permalink",
        "restaurant_name",
        "area",
        "genre",
        "hashtags",
        "like_count",
        "comments_count",
        *DEFAULT_METRICS,
    ]
    write_csv(output_dir / "instagram_post_insights.csv", insight_rows, insight_fields)
    added = append_candidates(output_dir / "follow_candidates.csv", list(candidate_map.values()))
    build_summary(insight_rows, output_dir / "instagram_growth_summary.md")

    print(json.dumps({
        "posts_analyzed": len(insight_rows),
        "follow_candidates_added": added,
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
