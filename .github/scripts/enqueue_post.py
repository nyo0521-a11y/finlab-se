"""
data/x-queue.yaml に新記事告知エントリを追記する（承認フロー廃止版）。

使い方:
    python enqueue_post.py <post_path>

同じ post_path が既に存在していれば追加しない（冪等）。
"""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ruamel.yaml import YAML

QUEUE_PATH = Path("data/x-queue.yaml")
HISTORY_PATH = Path("data/x-post-history.yaml")
JST = timezone(timedelta(hours=9))


def main():
    if len(sys.argv) < 2:
        print("usage: enqueue_post.py <post_path>", file=sys.stderr)
        sys.exit(2)

    post_path = sys.argv[1]

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    # 投稿済みチェック（x-post-history.yaml）: 既に X に投稿済みなら再エンキューしない
    if HISTORY_PATH.exists():
        with HISTORY_PATH.open(encoding="utf-8") as f:
            history_data = yaml.load(f) or {}
        for entry in (history_data.get("history") or []):
            if entry.get("post_path") == post_path:
                print(f"already posted to X: {post_path}")
                return

    if QUEUE_PATH.exists():
        with QUEUE_PATH.open(encoding="utf-8") as f:
            data = yaml.load(f) or {}
    else:
        data = {}
    queue = data.get("queue") or []

    # 重複チェック（冪等）: キューに既に存在する場合はスキップ
    for entry in queue:
        if entry.get("post_path") == post_path:
            print(f"already enqueued: {post_path}")
            return

    queue.append({
        "post_path": post_path,
        "added_at": datetime.now(JST).isoformat(timespec="seconds"),
    })
    data["queue"] = queue

    with QUEUE_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    print(f"enqueued: {post_path}")


if __name__ == "__main__":
    main()
