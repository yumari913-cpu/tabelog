import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def read_rows(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--posted-path", default="posted_review_urls.csv")
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--posting-start-hour", type=int, default=18)
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    now = datetime.now(tz)
    today = now.date()
    posted_today = False

    if now.hour < args.posting_start_hour:
        print("posted_today=false")
        print("should_post=false")
        print(f"reason=before_posting_window_{args.posting_start_hour}")
        return

    for row in read_rows(Path(args.posted_path)):
        value = row.get("投稿日時UTC", "").strip()
        if not value:
            continue
        try:
            posted_at = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        local_posted_at = posted_at.astimezone(tz)
        if local_posted_at.date() == today:
            posted_today = True
            break

    print(f"posted_today={str(posted_today).lower()}")
    print(f"should_post={str(not posted_today).lower()}")


if __name__ == "__main__":
    main()
