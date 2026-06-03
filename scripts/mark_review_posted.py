import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path


FIELDS = ["投稿日時UTC", "店名", "レビューURL", "GitHub Run"]


def read_rows(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--posted-path", default="posted_review_urls.csv")
    parser.add_argument("--review-url", required=True)
    parser.add_argument("--restaurant-name", default="")
    parser.add_argument("--github-run", default="")
    args = parser.parse_args()

    path = Path(args.posted_path)
    rows = read_rows(path)
    review_url = args.review_url.strip()
    if any(row.get("レビューURL", "").strip() == review_url for row in rows):
        print("already_marked=true")
        return

    rows.append(
        {
            "投稿日時UTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "店名": args.restaurant_name,
            "レビューURL": review_url,
            "GitHub Run": args.github_run,
        }
    )

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

    print("already_marked=false")
    print(f"marked={review_url}")


if __name__ == "__main__":
    main()
