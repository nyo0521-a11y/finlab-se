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

_URL_RE = re.compile(r"https?://\S+")


def count_x_length(text: str) -> int:
    """X換算の文字数。URLは23字、全角2・半角1で数える。"""
    urls = _URL_RE.findall(text)
    stripped = _URL_RE.sub("", text)
    body = sum(2 if ord(c) > 0x7E else 1 for c in stripped)
    return body + 23 * len(urls)
