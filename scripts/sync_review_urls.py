import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tabelog_insta.scraper import list_review_urls, parse_detail


FIELDS = ["No.", "店名", "訪問日", "レビューURL"]


def read_rows(csv_path):
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_rows(csv_path, rows):
    for index, row in enumerate(rows, start=1):
        row["No."] = str(index)
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-url", required=True)
    parser.add_argument("--csv-path", default="review_urls.csv")
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    existing_rows = read_rows(csv_path)
    existing_urls = {row.get("レビューURL", "").strip() for row in existing_rows}

    review_urls = list_review_urls(args.reviewer_url, max_pages=args.max_pages)
    new_urls = [url for url in review_urls if url not in existing_urls]

    new_rows = []
    for review_url in new_urls:
        review = parse_detail(review_url)
        new_rows.append(
            {
                "No.": "",
                "店名": review.get("restaurant_name", ""),
                "訪問日": review.get("visited_date", ""),
                "レビューURL": review.get("review_url", review_url),
            }
        )

    if new_rows:
        write_rows(csv_path, new_rows + existing_rows)

    print(f"new_count={len(new_rows)}")
    for row in new_rows:
        print(f"added={row['レビューURL']}")


if __name__ == "__main__":
    main()
