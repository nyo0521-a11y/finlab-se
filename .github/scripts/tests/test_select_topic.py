import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from select_topic import count_x_length, load_recent_post_paths

JST = timezone(timedelta(hours=9))


def _write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")


def test_halfwidth_counts_one():
    assert count_x_length("abcde") == 5


def test_fullwidth_counts_two():
    # 全角5文字 = 10
    assert count_x_length("あいうえお") == 10


def test_url_counts_23_regardless_of_length():
    url = "https://finlab-se.com/posts/housing-loan-variable-fixed-simulation/"
    # URLのみ → 23
    assert count_x_length(url) == 23


def test_mixed_text_with_url():
    # 全角3(=6) + 改行1(=1) + URL(=23) = 30
    text = "あいう\nhttps://example.com/x"
    assert count_x_length(text) == 6 + 1 + 23


def test_excludes_recent_from_both_sources(tmp_path):
    now = datetime(2026, 6, 30, 7, 30, tzinfo=JST)
    _write(tmp_path / "data/x-rotation.yaml", """
        rotation:
          - post_path: content/posts/recent-rotation.md
            last_promoted: '2026-06-28T07:30:00+09:00'
          - post_path: content/posts/old-rotation.md
            last_promoted: '2026-06-01T07:30:00+09:00'
          - post_path: content/posts/never.md
            last_promoted: null
    """)
    _write(tmp_path / "data/x-post-history.yaml", """
        history:
          - posted_at: '2026-06-27T21:05:00+09:00'
            post_path: content/posts/recent-history.md
          - posted_at: '2026-06-10T21:05:00+09:00'
            post_path: content/posts/old-history.md
    """)
    got = load_recent_post_paths(tmp_path, days=7, now=now)
    assert got == {
        "content/posts/recent-rotation.md",
        "content/posts/recent-history.md",
    }


def test_missing_files_return_empty(tmp_path):
    now = datetime(2026, 6, 30, 7, 30, tzinfo=JST)
    assert load_recent_post_paths(tmp_path, days=7, now=now) == set()
