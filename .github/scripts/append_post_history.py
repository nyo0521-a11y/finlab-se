"""
X 投稿履歴を data/x-post-history.yaml に追記するスクリプト。

投稿成功後に dequeue_and_post.py / rotation_post.py から呼ばれる。
stdin に JSON を渡す:
    {
        "text":      "投稿テキスト",
        "tweet_id":  "1234567890",
        "tweet_url": "https://x.com/i/web/status/1234567890",
        "type":      "new" | "rotation" | "adhoc",
        "post_path": "content/posts/some-article.md"  # 任意
    }

保存先: data/x-post-history.yaml
最大保持件数: MAX_HISTORY（デフォルト 50）
"""

import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ruamel.yaml import YAML

HISTORY_PATH = Path("data/x-post-history.yaml")
MAX_HISTORY  = 50
JST          = timezone(timedelta(hours=9))


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    yaml = YAML()
    with HISTORY_PATH.open(encoding="utf-8") as f:
        data = yaml.load(f) or {}
    return data.get("history") or []


def save_history(entries: list) -> None:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8") as f:
        yaml.dump({"history": entries}, f)


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print("no input", file=sys.stderr)
        sys.exit(1)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    now_jst = datetime.now(JST).isoformat(timespec="seconds")

    entry = {
        "posted_at": now_jst,
        "text":      payload.get("text", ""),
        "tweet_id":  payload.get("tweet_id", ""),
        "tweet_url": payload.get("tweet_url", ""),
        "type":      payload.get("type", "unknown"),
    }
    if payload.get("post_path"):
        entry["post_path"] = payload["post_path"]

    history = load_history()
    history.insert(0, entry)       # 新しい順（先頭に追加）
    history = history[:MAX_HISTORY]  # 上限件数で切り詰め
    save_history(history)

    print(json.dumps({"ok": True, "total": len(history)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
