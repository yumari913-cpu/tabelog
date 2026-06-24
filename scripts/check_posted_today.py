import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def read_rows(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def row_target_date(row, tz):
    explicit = row.get("投稿対象日JST", "").strip()
    if explicit:
        try:
            return date.fromisoformat(explicit)
        except ValueError:
            pass

    value = row.get("投稿日時UTC", "").strip()
    if not value:
        return None
    try:
        posted_at = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return posted_at.astimezone(tz).date()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--posted-path", default="posted_review_urls.csv")
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--posting-start-hour", type=int, default=18)
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    now = datetime.now(tz)
    today = now.date()
    target_date = today if now.hour >= args.posting_start_hour else today - timedelta(days=1)
    posted_target_date = False

    for row in read_rows(Path(args.posted_path)):
        if row_target_date(row, tz) == target_date:
            posted_target_date = True
            break

    print(f"target_date_jst={target_date.isoformat()}")
    print(f"posted_today={str(posted_target_date).lower()}")
    print(f"posted_target_date={str(posted_target_date).lower()}")
    print(f"should_post={str(not posted_target_date).lower()}")


if __name__ == "__main__":
    main()
