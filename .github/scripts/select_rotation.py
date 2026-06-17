"""
ローテーション対象記事の選定

選定ロジック:
  1. last_promoted が null を最優先、その次に最も古いもの（昇順）
  2. 同条件内では priority: high > normal > low
  3. 同priority内では post_path 昇順（安定ソート）

使い方:
    python select_rotation.py
    出力: JSON { "post_path": "content/posts/xxx.md", "index": 3 }

環境変数:
    （なし）
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    import yaml
except ImportError:
    print(json.dumps({"error": "PyYAML not installed"}))
    sys.exit(1)

PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}

# 直近 N 日以内に紹介した記事は候補から除外（おすすめ内の短期重複回避）。
# 全記事が除外対象になった場合は除外せず通常選定にフォールバックする。
EXCLUDE_DAYS = int(os.environ.get("ROTATION_EXCLUDE_DAYS", "3"))


def parse_ts(value):
    """last_promoted を比較用キーに変換。null/None は最古扱い（常にタイムゾーンあり）。"""
    _epoch = datetime.min.replace(tzinfo=timezone.utc)
    if value is None:
        return _epoch
    if isinstance(value, datetime):
        # YAML が timezone-naive で返す場合は UTC として扱う
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return _epoch


def main():
    repo_root = Path(__file__).resolve().parents[2]
    yaml_path = repo_root / "data" / "x-rotation.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    rotation = doc.get("rotation", [])
    if not rotation:
        print(json.dumps({"error": "rotation empty"}))
        sys.exit(1)

    def sort_key(item):
        ts = parse_ts(item.get("last_promoted"))
        prio = PRIORITY_ORDER.get(item.get("priority", "normal"), 1)
        return (ts, prio, item.get("post_path", ""))

    now = datetime.now(timezone.utc)
    cutoff = timedelta(days=EXCLUDE_DAYS)

    def recently_promoted(item):
        return (now - parse_ts(item.get("last_promoted"))) < cutoff

    # exclude: true の記事は恒久除外（SNS再掲に不向きなもの）。
    base = [(i, it) for i, it in enumerate(rotation) if not it.get("exclude")]
    if not base:
        print(json.dumps({"error": "all entries excluded"}))
        sys.exit(1)

    # 直近 EXCLUDE_DAYS 日以内に紹介した記事を除外。全除外なら base にフォールバック。
    eligible = [(i, it) for i, it in base if not recently_promoted(it)]
    pool = eligible if eligible else base

    sorted_items = sorted(pool, key=lambda x: sort_key(x[1]))
    index, chosen = sorted_items[0]

    print(json.dumps({
        "post_path": chosen["post_path"],
        "index": index,
        "last_promoted": str(chosen.get("last_promoted")),
        "priority": chosen.get("priority", "normal"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
