"""
投稿文生成スクリプト

Hugo記事の frontmatter を読み、X投稿用の140字以内テキストを生成する。

前提:
- タイトル・description・tags から整形テンプレートを組み立てる
- URLは固定23.5字換算（t.co短縮後）ではなく、実URL長をそのままカウントする簡易版
  （Xは実際には全URLを23字換算するが、安全側に実測で計算）
- 140字超過時は description を1文字ずつ末尾から削る

使い方:
    python generate_post_text.py <post_path> <mode>
      mode = "new" | "rotation"

    出力: JSON { "text": "...", "image_url": "...", "title": "...", "url": "..." }
"""
import sys
import json
import re
from pathlib import Path

BASE_URL = "https://finlab-se.com"
MAX_LEN = 140
# X は全URLを t.co で 23字換算する
URL_WEIGHT = 23

PREFIX_NEW = "【新着📝】"
PREFIX_ROTATION = "【おすすめ📖】"


def parse_frontmatter(md_text: str) -> dict:
    """Hugo frontmatter (---...---) を超簡易パース。title/description は文字列、tagsは配列。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", md_text, re.DOTALL)
    if not m:
        raise ValueError("frontmatter not found")
    body = m.group(1)
    fm: dict = {}
    # title / description / cover.image は "..." の文字列抽出
    for key in ("title", "description"):
        km = re.search(rf'^{key}:\s*"(.*?)"\s*$', body, re.MULTILINE)
        if km:
            fm[key] = km.group(1)
    # slug（hugo側のpermalink override用）
    sm = re.search(r'^slug:\s*"(.*?)"\s*$', body, re.MULTILINE)
    if sm:
        fm["slug"] = sm.group(1)
    # tags: [...] または tags: ["a", "b"]
    tm = re.search(r"^tags:\s*\[(.*?)\]\s*$", body, re.MULTILINE)
    if tm:
        tag_raw = tm.group(1)
        fm["tags"] = [t.strip().strip('"').strip("'") for t in tag_raw.split(",") if t.strip()]
    else:
        fm["tags"] = []
    # cover image
    cm = re.search(r'cover:\s*\n\s*image:\s*"(.*?)"', body)
    if cm:
        fm["cover_image"] = cm.group(1)
    return fm


def sanitize_hashtag(tag: str) -> str:
    """ハッシュタグ化：空白・記号を除去。Xは英数字・日本語・_ を受け付ける。"""
    # スペース・ハイフン・中点を削除
    return "#" + re.sub(r"[\s\-・／/]+", "", tag)


def pick_hashtags(tags: list, max_n: int = 3) -> list:
    """先頭から max_n 個を採用。重複排除。"""
    seen = set()
    result = []
    for t in tags:
        h = sanitize_hashtag(t)
        if h in seen:
            continue
        seen.add(h)
        result.append(h)
        if len(result) >= max_n:
            break
    return result


def build_url(post_path: str, slug: str | None) -> str:
    """content/posts/foo.md → https://finlab-se.com/posts/foo/ """
    # slug 指定があれば優先
    stem = slug if slug else Path(post_path).stem
    return f"{BASE_URL}/posts/{stem}/"


def truncate_description(desc: str, budget: int) -> str:
    """description を budget 字以内に収める。句読点で自然に切れる場合は「…」を付けない。"""
    if len(desc) <= budget:
        return desc
    if budget <= 1:
        return ""
    # 予算内で最後に現れる 。 または 、 を探し、そこで自然に切る
    head = desc[:budget]
    for mark in ("。", "！", "？"):
        idx = head.rfind(mark)
        if idx >= budget * 0.5:  # あまり短すぎる位置では切らない
            return head[: idx + 1]
    idx = head.rfind("、")
    if idx >= budget * 0.5:
        return head[: idx + 1] + "…"
    # それでも区切りが見つからなければ素直に末尾…
    return desc[: budget - 1] + "…"


def build_text(title: str, description: str, url: str, hashtags: list, prefix: str) -> str:
    """
    構造:
        {prefix}
        {description}

        {url}

        {#tag1 #tag2 #tag3}

    タイトルは X の URL カードで自動表示されるため、本文からは除外する（重複回避＋description 優先）。
    description が長すぎる場合は句読点で自然に切る。
    """
    hashtag_line = " ".join(hashtags)
    url_bonus = len(url) - URL_WEIGHT
    # 実際のテキスト: prefix\n {desc}\n\n {url}\n\n {hashtags}
    skeleton = f"{prefix}\n\n\n{url}\n\n{hashtag_line}"
    budget = MAX_LEN - len(skeleton) + url_bonus

    desc_part = truncate_description(description, budget)

    # ハッシュタグを削っても全文を優先したい場合の救済
    if len(desc_part) < len(description) and hashtags:
        # ハッシュタグなしで全文入るか再計算
        skeleton_no_tag = f"{prefix}\n\n\n{url}"
        budget_no_tag = MAX_LEN - len(skeleton_no_tag) + url_bonus
        if len(description) <= budget_no_tag:
            return f"{prefix}\n{description}\n\n{url}".strip()

    return f"{prefix}\n{desc_part}\n\n{url}\n\n{hashtag_line}".strip()


def main():
    if len(sys.argv) < 3:
        print("usage: generate_post_text.py <post_path> <mode:new|rotation>", file=sys.stderr)
        sys.exit(2)

    post_path = sys.argv[1]
    mode = sys.argv[2]

    repo_root = Path(__file__).resolve().parents[2]
    md_path = repo_root / post_path
    md = md_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(md)

    title = fm.get("title", "").strip()
    description = fm.get("description", "").strip()
    tags = fm.get("tags", [])
    slug = fm.get("slug")
    cover = fm.get("cover_image", "")

    url = build_url(post_path, slug)
    hashtags = pick_hashtags(tags, 3)
    prefix = PREFIX_ROTATION if mode == "rotation" else PREFIX_NEW
    text = build_text(title, description, url, hashtags, prefix)

    image_url = f"{BASE_URL}{cover}" if cover.startswith("/") else cover

    # X換算の長さ（URLは23字固定）
    x_length = len(text) - len(url) + URL_WEIGHT

    print(json.dumps({
        "text": text,
        "image_url": image_url,
        "image_path": cover,
        "title": title,
        "url": url,
        "length": x_length,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
