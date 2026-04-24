"""
ローテーションYAML更新（投稿成功時）

指定 index の last_promoted を現在時刻（JST）に更新し、promote_count を +1。

YAMLのコメント・順序を保持したいため、単純な yaml.dump ではなく ruamel.yaml を使う。
GitHub Actions 側で pip install ruamel.yaml が必要。

使い方:
    python update_rotation.py <index>
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


def main():
    if len(sys.argv) < 2:
        print("usage: update_rotation.py <index>", file=sys.stderr)
        sys.exit(2)

    index = int(sys.argv[1])
    repo_root = Path(__file__).resolve().parents[2]
    yaml_path = repo_root / "data" / "x-rotation.yaml"

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=2, offset=0)

    with open(yaml_path, encoding="utf-8") as f:
        doc = yaml.load(f)

    rotation = doc["rotation"]
    if index < 0 or index >= len(rotation):
        print(f"index out of range: {index}", file=sys.stderr)
        sys.exit(1)

    now_jst = datetime.now(JST).isoformat(timespec="seconds")
    rotation[index]["last_promoted"] = now_jst
    rotation[index]["promote_count"] = int(rotation[index].get("promote_count", 0)) + 1

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f)

    print(f"updated index={index} last_promoted={now_jst}")


if __name__ == "__main__":
    main()
