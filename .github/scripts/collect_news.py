"""
ニュース収集（サーバー版）。

news-collect スキルの思想（主観検索でなく客観ランキング起点）を HTTP 取得で再現する。
  - Yahoo!ニュース経済アクセスランキング（実際に読まれた順位つき見出し）
  - Google News RSS（ビジネス・当日新着ヘッドライン）
  - Google Trends RSS（検索急上昇ワード）
ホットさの判定はここではせず、順位という生データだけ集めて select_topic.py に渡す。

依存: requests と標準ライブラリのみ。

使い方:
    python collect_news.py
    出力: {"yahoo": [{"rank":1,"title":"...","url":"..."}, ...],
           "google": [{"title":"...","url":"..."}, ...],
           "trends": [{"title":"...","traffic":"..."}, ...]}
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
TRENDS_RSS = "https://trends.google.co.jp/trending/rss?geo=JP"
_HT_NS = "{https://trends.google.com/trending/rss}"
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


def parse_google_trends_rss(xml_text: str) -> list[dict]:
    """検索急上昇ワードを {title, traffic} で抽出。traffic は概算検索数（無ければ空文字）。"""
    out = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        title_el = item.find("title")
        if title_el is None or not title_el.text:
            continue
        traffic_el = item.find(f"{_HT_NS}approx_traffic")
        traffic = (traffic_el.text or "").strip() if traffic_el is not None else ""
        out.append({"title": title_el.text.strip(), "traffic": traffic})
    return out


def collect(fetch: Callable[[str], str] = http_fetch) -> dict:
    """3ソースを取得。一部が失敗しても取れたものだけで続行。"""
    yahoo = []
    google = []
    trends = []
    try:
        yahoo = parse_yahoo_ranking(fetch(YAHOO_RANKING_URL))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"yahoo ranking fetch/parse failed: {e}\n")
    try:
        google = parse_google_news_rss(fetch(GOOGLE_NEWS_RSS))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"google news fetch/parse failed: {e}\n")
    try:
        trends = parse_google_trends_rss(fetch(TRENDS_RSS))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"google trends fetch/parse failed: {e}\n")
    return {"yahoo": yahoo, "google": google, "trends": trends}


def main() -> None:
    print(json.dumps(collect(), ensure_ascii=False))


if __name__ == "__main__":
    main()
