"""
data/x-queue.yaml に新記事告知エントリを追記する。

使い方:
    python enqueue_post.py <post_path> <issue_number>

同じ post_path が既に存在していれば issue_number のみ更新（重複追加しない）。
"""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ruamel.yaml import YAML

QUEUE_PATH = Path("data/x-queue.yaml")
JST = timezone(timedelta(hours=9))


def main():
    if len(sys.argv) < 3:
        print("usage: enqueue_post.py <post_path> <issue_number>", file=sys.stderr)
        sys.exit(2)

    post_path = sys.argv[1]
    issue_number = int(sys.argv[2])

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    if QUEUE_PATH.exists():
        with QUEUE_PATH.open(encoding="utf-8") as f:
            data = yaml.load(f) or {}
    else:
        data = {}
    queue = data.get("queue") or []

    # 既存エントリの更新
    for entry in queue:
        if entry.get("post_path") == post_path:
            entry["issue_number"] = issue_number
            break
    else:
        queue.append({
            "post_path": post_path,
            "issue_number": issue_number,
            "added_at": datetime.now(JST).isoformat(timespec="seconds"),
        })
    data["queue"] = queue

    with QUEUE_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    print(f"enqueued: {post_path} (issue #{issue_number})")


if __name__ == "__main__":
    main()
