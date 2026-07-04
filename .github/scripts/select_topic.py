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
import json
import os
import re as _re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None

from generate_post_text import parse_frontmatter, build_url

_URL_RE = _re.compile(r"https?://\S+")
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


def _extract_categories(md_text: str) -> list:
    """frontmatter から categories リストを抽出。"""
    m = _re.search(r"^categories:\s*\[(.*?)\]\s*$", md_text, _re.MULTILINE)
    if not m:
        return []
    return [c.strip().strip('"').strip("'") for c in m.group(1).split(",") if c.strip()]


def build_article_catalog(repo_root: Path, exclude_paths: set, permanently_excluded: set) -> list:
    """content/posts/*.md を走査して記事一覧を作る。除外対象は含めない。"""
    catalog = []
    posts_dir = repo_root / "content" / "posts"
    for md_path in sorted(posts_dir.glob("*.md")):
        post_path = f"content/posts/{md_path.name}"
        if post_path in exclude_paths or post_path in permanently_excluded:
            continue
        md = md_path.read_text(encoding="utf-8")
        try:
            fm = parse_frontmatter(md)
        except ValueError:
            continue
        catalog.append({
            "post_path": post_path,
            "title": fm.get("title", "").strip(),
            "url": build_url(post_path, fm.get("slug")),
            "categories": _extract_categories(md),
            "tags": fm.get("tags", []),
            "description": fm.get("description", "").strip(),
        })
    return catalog


def load_permanently_excluded(repo_root: Path) -> set:
    """x-rotation.yaml の exclude: true の post_path 集合。"""
    rot = _load_yaml(repo_root / "data" / "x-rotation.yaml") or {}
    return {
        it.get("post_path")
        for it in (rot.get("rotation") or [])
        if it.get("exclude") and it.get("post_path")
    }


MODEL = "claude-opus-4-8"
MAX_LEN = 280

_SELECT_TOOL = {
    "name": "select_article",
    "description": "選定結果を返す。マッチする記事が無ければ selected_post_path を null にする。",
    "input_schema": {
        "type": "object",
        "properties": {
            "selected_post_path": {"type": ["string", "null"]},
            "text": {"type": ["string", "null"]},
            "topic_reason": {"type": "string"},
            "candidates": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["selected_post_path", "topic_reason"],
    },
}

_SYSTEM = (
    "あなたは金融ブログ finlab-se.com のSNS運用担当です。"
    "今日のホットな経済ニュースに自然にマッチする既存記事を1本選び、X投稿文を作ります。\n"
    "ルール:\n"
    "- ホットさは渡された順位データを根拠に判断する（自分でキーワードを作らない）。"
    "複数ソースに跨って上位に出る話題ほど優先。\n"
    "- trends は日本全体の検索急上昇ワード（分野を問わない一般ランキング。"
    "traffic は概算検索数）。金融・経済に関するワードが含まれる場合のみ強い加点材料とし、"
    "スポーツ・芸能など金融と無関係なワードは無視する。\n"
    "- 手順: (1)ホットな話題を上位5件ランク付け (2)各話題に自然にマッチする記事候補を挙げる"
    "(3)マッチが成立した話題をホットな順に見て最上位の記事を採用。\n"
    "- こじつけ禁止。自然に合う記事が無ければ selected_post_path を null にする。\n"
    "- 投稿文は250字以内を目標に短く作る（上限はX換算280字。全角2字・半角1字・URL23字換算）、1段落推奨、"
    "煽り表現（爆益・億り人・必ず儲かる・○○一択）禁止、丁寧で論理的。ハッシュタグ1〜3個。\n"
    "- 投稿文には選んだ記事のURLを必ず含める。\n"
    "- candidates には検討した話題と候補記事を記録する。"
)


def build_messages(news: dict, catalog: list) -> tuple:
    user = json.dumps({"news": news, "articles": catalog}, ensure_ascii=False)
    return _SYSTEM, user


def _call_claude(system: str, user: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[_SELECT_TOOL],
        tool_choice={"type": "tool", "name": "select_article"},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return block.input
    raise RuntimeError("no tool_use block in Claude response")


def select(news: dict, repo_root: Path, now: datetime, call=_call_claude) -> dict:
    days = int(os.environ.get("ROTATION_EXCLUDE_DAYS", "7"))
    recent = load_recent_post_paths(repo_root, days=days, now=now)
    banned = load_permanently_excluded(repo_root)
    catalog = build_article_catalog(repo_root, exclude_paths=recent, permanently_excluded=banned)
    if not catalog:
        return {"selected_post_path": None, "reason": "no eligible articles", "candidates": []}

    system, user = build_messages(news, catalog)
    valid_paths = {c["post_path"] for c in catalog}

    result = call(system, user)
    for attempt in range(3):  # 初回 + 短縮再依頼2回
        sel = result.get("selected_post_path")
        if not sel:
            return {"selected_post_path": None,
                    "reason": result.get("reason", "no match"),
                    "candidates": result.get("candidates", [])}
        if sel not in valid_paths:
            return {"selected_post_path": None, "reason": f"invalid path {sel}",
                    "candidates": result.get("candidates", [])}
        text = result.get("text") or ""
        if count_x_length(text) <= MAX_LEN:
            return {"selected_post_path": sel, "text": text,
                    "topic_reason": result.get("topic_reason", ""),
                    "candidates": result.get("candidates", [])}
        if attempt < 2:
            over_by = count_x_length(text) - MAX_LEN
            retry_user = (
                user
                + "\n\n直前に生成したこの投稿文はX換算で280字を"
                + f"{over_by}字超過しました（全角2字・半角1字・URL23字換算）。\n"
                + f"直前の投稿文:\n{text}\n\n"
                + "同じ記事のまま、上記の文章を実際に削って280字以内に収めて作り直してください。"
                + "新しい文章を考え直すのではなく、上の文章から不要な語句を削る形にしてください。"
            )
            result = call(system, retry_user)
    return {"selected_post_path": None, "reason": "text too long after retry",
            "candidates": result.get("candidates", [])}


def main():
    raw = sys.stdin.buffer.read().decode("utf-8")
    news = json.loads(raw) if raw.strip() else {"yahoo": [], "google": []}
    repo_root = Path(__file__).resolve().parents[2]
    now = datetime.now(timezone(timedelta(hours=9)))
    print(json.dumps(select(news, repo_root, now=now), ensure_ascii=False))


if __name__ == "__main__":
    main()
