import argparse
import csv
import subprocess
import sys
from pathlib import Path


REVIEWER_URL = "https://tabelog.com/rvwr/018712231/"


def read_rows(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def run(command, cwd):
    print("+", " ".join(str(part) for part in command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--prepare-count", type=int, default=10)
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).resolve()
    python = sys.executable
    run(["git", "pull", "--ff-only", "origin", "main"], repo_dir)
    run(
        [
            python,
            "scripts/sync_review_urls.py",
            "--reviewer-url",
            REVIEWER_URL,
            "--csv-path",
            "review_urls.csv",
            "--max-pages",
            "10",
        ],
        repo_dir,
    )

    review_rows = read_rows(repo_dir / "review_urls.csv")
    posted_rows = read_rows(repo_dir / "posted_review_urls.csv")
    posted_urls = {row.get("レビューURL", "").strip() for row in posted_rows}
    pending_urls = [
        row.get("レビューURL", "").strip()
        for row in review_rows
        if row.get("レビューURL", "").strip()
        and row.get("レビューURL", "").strip() not in posted_urls
    ][: args.prepare_count]

    for review_url in pending_urls:
        review_id = review_url.rstrip("/").split("/")[-1]
        manifest = f"generated/{review_id}_post.json"
        run(
            [
                python,
                "scripts/build_post_assets.py",
                "--review-url",
                review_url,
                "--caption-style",
                "story",
            ],
            repo_dir,
        )
        run([python, "scripts/validate_generated_assets.py", "--manifest", manifest], repo_dir)

    run(["git", "add", "review_urls.csv", "generated"], repo_dir)
    changed = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False
    ).returncode
    if changed == 0:
        print("No review URL or generated asset changes.")
        return

    run(["git", "commit", "-m", "Prepare weekly Instagram posts on Mac"], repo_dir)
    run(["git", "push", "origin", "main"], repo_dir)


if __name__ == "__main__":
    main()
