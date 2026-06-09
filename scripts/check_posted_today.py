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
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    today = datetime.now(tz).date()
    posted_today = False

    for row in read_rows(Path(args.posted_path)):
        value = row.get("投稿日時UTC", "").strip()
        if not value:
            continue
        try:
            posted_at = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if posted_at.astimezone(tz).date() == today:
            posted_today = True
            break

    print(f"posted_today={str(posted_today).lower()}")
    print(f"should_post={str(not posted_today).lower()}")


if __name__ == "__main__":
    main()
