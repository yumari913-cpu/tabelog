import argparse
import csv
from pathlib import Path


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", default="review_urls.csv")
    parser.add_argument("--posted-path", default="posted_review_urls.csv")
    args = parser.parse_args()

    review_rows = read_csv(Path(args.csv_path))
    posted_rows = read_csv(Path(args.posted_path))
    posted_urls = {row.get("レビューURL", "").strip() for row in posted_rows}

    next_row = None
    for row in review_rows:
        review_url = row.get("レビューURL", "").strip()
        if review_url and review_url not in posted_urls:
            next_row = row
            break

    if not next_row:
        print("has_next=false")
        return

    print("has_next=true")
    print(f"review_url={next_row.get('レビューURL', '').strip()}")
    print(f"restaurant_name={next_row.get('店名', '').strip()}")


if __name__ == "__main__":
    main()
