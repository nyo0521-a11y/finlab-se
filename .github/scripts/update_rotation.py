"""
ローテーションYAML更新（投稿成功時）

2通りの呼び出し方：
  1. index 指定（後方互換）:
       python update_rotation.py <index>
     指定 index の last_promoted を現在時刻（JST）に更新し、promote_count を +1。
  2. post_path 指定（upsert・2026-06-18 追加）:
       python update_rotation.py --post-path content/posts/xxx.md
     post_path 一致があれば last_promoted=今・promote_count+1。
     無ければ末尾に新規追記（last_promoted=今・promote_count=1・priority=normal）。

全記事の自動同期台帳化（②）に伴い、新着(dequeue_and_post.py)・話題連動(morning_post.py)
からは post_path 指定で呼ぶ。rotation_post.py は従来どおり index 指定。

YAMLのコメント・順序を保持したいため ruamel.yaml を使う（要 pip install ruamel.yaml）。
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    from ruamel.yaml import YAML
except ImportError:
    print("ruamel.yaml not installed", file=sys.stderr)
    sys.exit(1)

JST = timezone(timedelta(hours=9))


def _load(yaml_path):
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=2, offset=0)
    with open(yaml_path, encoding="utf-8") as f:
        doc = yaml.load(f)
    return yaml, doc


def main():
    if len(sys.argv) < 2:
        print("usage: update_rotation.py <index> | --post-path <content/posts/xxx.md>", file=sys.stderr)
        sys.exit(2)

    repo_root = Path(__file__).resolve().parents[2]
    yaml_path = repo_root / "data" / "x-rotation.yaml"
    now_jst = datetime.now(JST).isoformat(timespec="seconds")

    yaml, doc = _load(yaml_path)
    rotation = doc["rotation"]

    # --- post_path 指定（upsert） ---
    if sys.argv[1] == "--post-path":
        if len(sys.argv) < 3:
            print("usage: update_rotation.py --post-path <content/posts/xxx.md>", file=sys.stderr)
            sys.exit(2)
        post_path = sys.argv[2]
        for entry in rotation:
            if entry.get("post_path") == post_path:
                entry["last_promoted"] = now_jst
                entry["promote_count"] = int(entry.get("promote_count", 0)) + 1
                with open(yaml_path, "w", encoding="utf-8") as f:
                    yaml.dump(doc, f)
                print(f"updated post_path={post_path} last_promoted={now_jst}")
                return
        # 未登録 → 末尾に新規追記
        rotation.append({
            "post_path": post_path,
            "last_promoted": now_jst,
            "promote_count": 1,
            "priority": "normal",
        })
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(doc, f)
        print(f"appended post_path={post_path} last_promoted={now_jst}")
        return

    # --- index 指定（後方互換） ---
    index = int(sys.argv[1])
    if index < 0 or index >= len(rotation):
        print(f"index out of range: {index}", file=sys.stderr)
        sys.exit(1)

    rotation[index]["last_promoted"] = now_jst
    rotation[index]["promote_count"] = int(rotation[index].get("promote_count", 0)) + 1

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f)

    print(f"updated index={index} last_promoted={now_jst}")


if __name__ == "__main__":
    main()
