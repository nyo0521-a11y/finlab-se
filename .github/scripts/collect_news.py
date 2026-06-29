"""
ニュース収集（サーバー版）。

news-collect スキルの思想（主観検索でなく客観ランキング起点）を HTTP 取得で再現する。
  - Yahoo!ニュース経済アクセスランキング（実際に読まれた順位つき見出し）
  - Google News RSS（ビジネス・当日新着ヘッドライン）
ホットさの判定はここではせず、順位という生データだけ集めて select_topic.py に渡す。

依存: requests と標準ライブラリのみ。

使い方:
    python collect_news.py
    出力: {"yahoo": [{"rank":1,"title":"...","url":"..."}, ...],
           "google": [{"title":"...","url":"..."}, ...]}
"""
import sys
import json
import re
import xml.etree.ElementTree as ET
from typing import Callable

import requests

YAHOO_RANKING_URL = "https://news.yahoo.co.jp/ranking/access/news/business"
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/headlines/section/topic/BUSINESS"
    "?hl=ja&gl=JP&ceid=JP:ja"
)
HEADERS = {"User-Agent": "finlab-se-news-collector/1.0"}
_ANCHOR_RE = re.compile(r'<a[^>]+href="(https://news\.yahoo\.co\.jp/[^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def http_fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_yahoo_ranking(html: str) -> list[dict]:
    """記事リンクのアンカーから見出しを順位つきで抽出（上位15件）。"""
    out = []
    seen = set()
    for url, inner in _ANCHOR_RE.findall(html):
        title = _TAG_RE.sub("", inner).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append({"rank": len(out) + 1, "title": title, "url": url})
        if len(out) >= 15:
            break
    return out


def parse_google_news_rss(xml_text: str) -> list[dict]:
    out = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        if title_el is not None and title_el.text:
            out.append({
                "title": title_el.text.strip(),
                "url": (link_el.text or "").strip() if link_el is not None else "",
            })
    return out


def collect(fetch: Callable[[str], str] = http_fetch) -> dict:
    """両ソースを取得。片方が失敗しても取れた方だけで続行。"""
    yahoo = []
    google = []
    try:
        yahoo = parse_yahoo_ranking(fetch(YAHOO_RANKING_URL))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"yahoo ranking fetch/parse failed: {e}\n")
    try:
        google = parse_google_news_rss(fetch(GOOGLE_NEWS_RSS))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"google news fetch/parse failed: {e}\n")
    return {"yahoo": yahoo, "google": google}


def main() -> None:
    print(json.dumps(collect(), ensure_ascii=False))


if __name__ == "__main__":
    main()
