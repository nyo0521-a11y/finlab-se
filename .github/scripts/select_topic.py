"""
朝のX投稿の「話題連動おすすめ」をその場で選定するスクリプト。

stdin で collect_news.py の出力（JSON）を受け取り、記事一覧・除外リストと
合わせて Claude(Opus) に渡し、最適な1記事と投稿文を選定して stdout に JSON を返す。
投稿はしない（morning_post.py が行う）。

使い方:
    python collect_news.py | python select_topic.py
    出力: {"selected_post_path": "content/posts/xxx.md", "text": "...",
           "topic_reason": "...", "candidates": [...]}
      または {"selected_post_path": null, "reason": "...", "candidates": [...]}

環境変数:
    ANTHROPIC_API_KEY
    ROTATION_EXCLUDE_DAYS（既定 7）
"""
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None

_URL_RE = re.compile(r"https?://\S+")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def count_x_length(text: str) -> int:
    """X換算の文字数。URLは23字、全角2・半角1で数える。"""
    urls = _URL_RE.findall(text)
    stripped = _URL_RE.sub("", text)
    body = sum(2 if ord(c) > 0x7E else 1 for c in stripped)
    return body + 23 * len(urls)


def _parse_ts(value):
    if value is None:
        return _EPOCH
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return _EPOCH


def _load_yaml(path: Path):
    if not path.exists() or yaml is None:
        return None
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_recent_post_paths(repo_root: Path, days: int, now: datetime) -> set:
    """直近 days 日以内に投稿した post_path の集合（rotation + history の2ソース）。"""
    cutoff = timedelta(days=days)
    recent = set()

    rot = _load_yaml(repo_root / "data" / "x-rotation.yaml") or {}
    for item in (rot.get("rotation") or []):
        if (now - _parse_ts(item.get("last_promoted"))) < cutoff:
            pp = item.get("post_path")
            if pp:
                recent.add(pp)

    hist = _load_yaml(repo_root / "data" / "x-post-history.yaml") or {}
    for item in (hist.get("history") or []):
        if (now - _parse_ts(item.get("posted_at"))) < cutoff:
            pp = item.get("post_path")
            if pp:
                recent.add(pp)

    return recent
