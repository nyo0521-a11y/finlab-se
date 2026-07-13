import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from select_topic import (
    count_x_length,
    load_recent_post_paths,
    build_article_catalog,
    load_permanently_excluded,
)

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


def test_catalog_builds_and_excludes(tmp_path):
    posts = tmp_path / "content/posts"
    posts.mkdir(parents=True)
    (posts / "keep.md").write_text(
        '---\ntitle: "残す記事"\ndescription: "説明A"\n'
        'categories: ["資産形成"]\ntags: ["日銀", "金利"]\n'
        'cover:\n  image: "/images/keep.png"\n---\n本文\n',
        encoding="utf-8",
    )
    (posts / "recent.md").write_text(
        '---\ntitle: "直近に出した"\ndescription: "説明B"\ntags: ["X"]\n---\n本文\n',
        encoding="utf-8",
    )
    (posts / "banned.md").write_text(
        '---\ntitle: "恒久除外"\ndescription: "説明C"\ntags: ["Y"]\n---\n本文\n',
        encoding="utf-8",
    )
    catalog = build_article_catalog(
        tmp_path,
        exclude_paths={"content/posts/recent.md"},
        permanently_excluded={"content/posts/banned.md"},
    )
    paths = [c["post_path"] for c in catalog]
    assert paths == ["content/posts/keep.md"]
    entry = catalog[0]
    assert entry["url"] == "https://finlab-se.com/posts/keep/"
    assert entry["categories"] == ["資産形成"]
    assert entry["tags"] == ["日銀", "金利"]
    assert entry["description"] == "説明A"


def test_load_permanently_excluded_with_present_file(tmp_path):
    """Given x-rotation.yaml with exclude: true entries, only those post_paths are returned."""
    _write(tmp_path / "data/x-rotation.yaml", """
        rotation:
          - post_path: content/posts/exclude-this.md
            exclude: true
          - post_path: content/posts/keep-this.md
            exclude: false
          - post_path: content/posts/no-exclude-key.md
    """)
    got = load_permanently_excluded(tmp_path)
    assert got == {"content/posts/exclude-this.md"}


def test_load_permanently_excluded_with_missing_file(tmp_path):
    """Given a missing x-rotation.yaml, return empty set."""
    got = load_permanently_excluded(tmp_path)
    assert got == set()


from datetime import datetime
from select_topic import select, MAX_LEN


def _make_repo(tmp_path):
    posts = tmp_path / "content/posts"
    posts.mkdir(parents=True)
    (posts / "loan.md").write_text(
        '---\ntitle: "住宅ローンは変動か固定か"\ndescription: "金利上昇局面の判断軸"\n'
        'categories: ["資産形成"]\ntags: ["住宅ローン", "金利"]\n'
        'cover:\n  image: "/images/loan.png"\n---\n本文\n',
        encoding="utf-8",
    )
    return tmp_path


NEWS = {"yahoo": [{"rank": 1, "title": "日銀が追加利上げ、住宅ローン金利上昇へ", "url": "u"}],
        "google": [{"title": "変動金利上昇", "url": "g"}]}


def test_select_returns_article_from_call(tmp_path):
    repo = _make_repo(tmp_path)
    now = datetime(2026, 6, 30, 7, 30, tzinfo=JST)

    def fake_call(system, user):
        return {
            "selected_post_path": "content/posts/loan.md",
            "text": "【日銀利上げ】住宅ローン金利が上昇。判断軸を解説します。\nhttps://finlab-se.com/posts/loan/\n#住宅ローン",
            "topic_reason": "日銀利上げ",
            "candidates": [],
        }

    out = select(NEWS, repo, now=now, call=fake_call)
    assert out["selected_post_path"] == "content/posts/loan.md"


def test_select_null_when_no_match(tmp_path):
    repo = _make_repo(tmp_path)
    now = datetime(2026, 6, 30, 7, 30, tzinfo=JST)

    def fake_call(system, user):
        return {"selected_post_path": None, "reason": "該当なし", "candidates": []}

    out = select(NEWS, repo, now=now, call=fake_call)
    assert out["selected_post_path"] is None


def test_select_retries_twice_on_overflow_then_nulls(tmp_path):
    repo = _make_repo(tmp_path)
    now = datetime(2026, 6, 30, 7, 30, tzinfo=JST)
    long_text = "あ" * 200 + "\nhttps://finlab-se.com/posts/loan/"  # 400+23 字 → 超過
    calls = {"n": 0}

    def fake_call(system, user):
        calls["n"] += 1
        return {
            "selected_post_path": "content/posts/loan.md",
            "text": long_text,
            "topic_reason": "x",
            "candidates": [],
        }

    out = select(NEWS, repo, now=now, call=fake_call)
    assert calls["n"] == 3          # 初回＋短縮再依頼2回
    assert out["selected_post_path"] is None
    # 診断用: 3回とも超過した実際の文章と文字数がattemptsに残る
    assert len(out["attempts"]) == 3
    assert all(a["text"] == long_text for a in out["attempts"])
    assert all(a["length"] == count_x_length(long_text) for a in out["attempts"])


def test_select_returns_success_on_retry(tmp_path):
    """初回が280字超 → 再依頼で短い文が返ったとき成功を返す。"""
    repo = _make_repo(tmp_path)
    now = datetime(2026, 6, 30, 7, 30, tzinfo=JST)
    long_text = "あ" * 200 + " https://finlab-se.com/posts/loan/"  # 超過
    short_text = "本文 https://finlab-se.com/posts/loan/"            # 23+3 字 → 範囲内
    calls = {"n": 0}

    def fake_call(system, user):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "selected_post_path": "content/posts/loan.md",
                "text": long_text,
                "topic_reason": "日銀利上げ",
                "candidates": [],
            }
        return {
            "selected_post_path": "content/posts/loan.md",
            "text": short_text,
            "topic_reason": "日銀利上げ",
            "candidates": [],
        }

    out = select(NEWS, repo, now=now, call=fake_call)
    assert calls["n"] == 2
    assert out["selected_post_path"] == "content/posts/loan.md"
    # 成功時も、直前に超過した1回目の試行はattemptsに残る
    assert len(out["attempts"]) == 1
    assert out["attempts"][0]["text"] == long_text


def test_select_retry_message_includes_previous_text_and_overflow(tmp_path):
    """再依頼時、直前に生成された実際のテキストと超過文字数をClaudeに見せる。"""
    repo = _make_repo(tmp_path)
    now = datetime(2026, 6, 30, 7, 30, tzinfo=JST)
    long_text = "あ" * 200 + " https://finlab-se.com/posts/loan/"
    seen_users = []

    def fake_call(system, user):
        seen_users.append(user)
        return {"selected_post_path": "content/posts/loan.md", "text": long_text,
                "topic_reason": "x", "candidates": []}

    select(NEWS, repo, now=now, call=fake_call)
    assert len(seen_users) == 3
    retry_user = seen_users[1]
    assert long_text in retry_user
    over_by = count_x_length(long_text) - MAX_LEN
    assert str(over_by) in retry_user
