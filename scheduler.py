import argparse
import time
from datetime import datetime

from cli import cmd_sync


class Args:
    limit = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-minutes", type=int, default=60)
    args = parser.parse_args()
    interval = max(args.interval_minutes, 15) * 60
    print(f"新規投稿チェックを開始しました。間隔: {interval // 60}分")
    while True:
        print(f"[{datetime.now().isoformat(timespec='seconds')}] チェック開始")
        try:
            cmd_sync(Args())
        except Exception as exc:
            print(f"チェック中にエラー: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
