from collect_news import parse_yahoo_ranking, parse_google_news_rss, collect


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
