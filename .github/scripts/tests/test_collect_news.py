from collect_news import parse_yahoo_ranking, parse_google_news_rss, parse_google_trends_rss, collect


def test_parse_yahoo_extracts_titles_in_order():
    html = """
    <ol>
      <li><a href="https://news.yahoo.co.jp/articles/aaa">日銀が追加利上げ</a></li>
      <li><a href="https://news.yahoo.co.jp/articles/bbb">新NISA拡充案</a></li>
    </ol>
    """
    got = parse_yahoo_ranking(html)
    assert got[0]["rank"] == 1
    assert got[0]["title"] == "日銀が追加利上げ"
    assert got[1]["rank"] == 2
    assert got[1]["title"] == "新NISA拡充案"


def test_parse_google_rss_extracts_titles():
    xml = """<?xml version="1.0"?><rss><channel>
      <item><title>住宅ローン金利上昇</title><link>https://news.google.com/x</link></item>
      <item><title>円安進行</title><link>https://news.google.com/y</link></item>
    </channel></rss>"""
    got = parse_google_news_rss(xml)
    assert [g["title"] for g in got] == ["住宅ローン金利上昇", "円安進行"]


def test_collect_tolerates_one_source_failure():
    def fake_fetch(url):
        if "yahoo" in url:
            raise RuntimeError("yahoo down")
        return """<?xml version="1.0"?><rss><channel>
          <item><title>円安進行</title><link>https://g/y</link></item>
        </channel></rss>"""
    out = collect(fetch=fake_fetch)
    assert out["yahoo"] == []
    assert out["google"][0]["title"] == "円安進行"


def test_parse_yahoo_returns_empty_on_no_matching_anchors():
    """Yahoo!がページ構造を変えて news.yahoo.co.jp/articles/* リンクが消えた場合、[] を返す。"""
    html = "<div>no article anchors here</div>"
    assert parse_yahoo_ranking(html) == []


TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <item><title>日銀 利上げ</title><ht:approx_traffic>20,000+</ht:approx_traffic></item>
    <item><title>サッカー日本代表</title></item>
  </channel>
</rss>"""


def test_parse_trends_extracts_title_and_traffic():
    got = parse_google_trends_rss(TRENDS_XML)
    assert got[0] == {"title": "日銀 利上げ", "traffic": "20,000+"}
    assert got[1] == {"title": "サッカー日本代表", "traffic": ""}


def test_collect_includes_trends_key():
    def fake_fetch(url):
        if "yahoo" in url:
            raise RuntimeError("down")
        if "trends" in url:
            return TRENDS_XML
        return """<?xml version="1.0"?><rss><channel>
          <item><title>円安進行</title><link>https://g/y</link></item>
        </channel></rss>"""
    out = collect(fetch=fake_fetch)
    assert out["yahoo"] == []
    assert out["google"][0]["title"] == "円安進行"
    assert out["trends"][0]["title"] == "日銀 利上げ"


def test_collect_tolerates_trends_failure():
    def fake_fetch(url):
        if "trends" in url:
            raise RuntimeError("trends down")
        if "yahoo" in url:
            return '<a href="https://news.yahoo.co.jp/articles/aaa">日銀が追加利上げ</a>'
        return """<?xml version="1.0"?><rss><channel>
          <item><title>円安進行</title><link>https://g/y</link></item>
        </channel></rss>"""
    out = collect(fetch=fake_fetch)
    assert out["trends"] == []
    assert out["yahoo"][0]["title"] == "日銀が追加利上げ"
    assert out["google"][0]["title"] == "円安進行"
