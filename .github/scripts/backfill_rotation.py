"""
rotation台帳バックフィル（一度きり・2026-06-18）

content/posts/*.md のうち data/x-rotation.yaml に未登録の記事を台帳へ追加する。
全記事の自動同期台帳化（②）に伴う初期移行スクリプト。

各未登録記事の last_promoted:
  - data/x-post-history.yaml にその post_path の投稿があれば「最新 posted_at」
  - 無ければ null（＝最優先で選ばれる・未紹介記事を先に出す）
priority は一律 normal。promote_count は history出現回数。

使い方:
    python backfill_rotation.py            # dry-run（追加予定を表示するだけ）
    python backfill_rotation.py --apply    # 実際に x-rotation.yaml へ追記

ruamel で round-trip（既存コメント・インデント保持）。
"""
import sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
    import yaml as pyyaml
except ImportError:
    print("ruamel.yaml / PyYAML not installed", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]
ROTATION_PATH = REPO_ROOT / "data" / "x-rotation.yaml"
HISTORY_PATH = REPO_ROOT / "data" / "x-post-history.yaml"
POSTS_DIR = REPO_ROOT / "content" / "posts"


def main():
    apply = "--apply" in sys.argv[1:]

    # 1. 既存台帳の post_path 集合
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=2, offset=0)
    with ROTATION_PATH.open(encoding="utf-8") as f:
        doc = yaml.load(f)
    rotation = doc["rotation"]
    registered = {e.get("post_path") for e in rotation}

    # 2. history から post_path ごとの最新 posted_at と回数
    hist_latest = {}
    hist_count = {}
    if HISTORY_PATH.exists():
        with HISTORY_PATH.open(encoding="utf-8") as f:
            hist = pyyaml.safe_load(f) or {}
        for entry in (hist.get("history") or []):
            pp = entry.get("post_path")
            ts = entry.get("posted_at")
            if not pp:
                continue
            hist_count[pp] = hist_count.get(pp, 0) + 1
            if ts and (pp not in hist_latest or str(ts) > str(hist_latest[pp])):
                hist_latest[pp] = ts

    # 3. content/posts の全記事のうち未登録を抽出
    all_posts = sorted(f"content/posts/{p.name}" for p in POSTS_DIR.glob("*.md"))
    missing = [pp for pp in all_posts if pp not in registered]

    print(f"posts総数: {len(all_posts)} / 登録済み: {len(registered)} / 未登録: {len(missing)}")
    print("--- 追加予定 ---")
    new_entries = []
    for pp in missing:
        last = hist_latest.get(pp)  # None なら null
        cnt = hist_count.get(pp, 0)
        new_entries.append({
            "post_path": pp,
            "last_promoted": last,
            "promote_count": cnt,
            "priority": "normal",
        })
        print(f"  {pp}  last_promoted={last or 'null'}  promote_count={cnt}")

    if not apply:
        print("\n(dry-run。実際に追記するには --apply を付けて再実行)")
        return

    rotation.extend(new_entries)
    with ROTATION_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f)
    print(f"\napplied: {len(new_entries)} 件を追記しました（合計 {len(rotation)} 件）")


if __name__ == "__main__":
    main()
