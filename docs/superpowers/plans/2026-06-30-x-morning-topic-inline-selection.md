# 朝のX話題連動投稿のサーバー化（インライン選定方式）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 朝7:30のX投稿ワークフロー内で「客観ニュース取得 → Claude(Opus)で記事選定 → 即投稿」をインライン実行し、PC依存の記事選定と中間ファイル `x-topic-pick.yaml` を廃止する。

**Architecture:** 既存の `morning_post.py` の「pickファイルを読む」処理を「その場で選定する」処理に差し替える。ニュース取得（`collect_news.py`）と Claude 選定（`select_topic.py`）を独立スクリプトに分け、`morning_post.py` が subprocess で順に呼ぶ。投稿・履歴・rotation台帳・フォールバックは既存実装をそのまま流用する。

**Tech Stack:** Python 3.11 / `requests`（HTTP）/ 標準ライブラリ `xml.etree`（RSS）/ `anthropic` Python SDK（Claude）/ `ruamel.yaml`・`PyYAML`（既存）/ pytest（新規・純ロジックの単体テスト用）。

## Global Constraints

以下は全タスク共通の制約。各タスクの要件に暗黙的に含まれる。

- 使用モデル: **Claude Opus**（`claude-opus-4-8`）。Sonnet等に切り替えない。
- APIキー: 環境変数 `ANTHROPIC_API_KEY`（GitHub Secrets 由来）。**コードに直書きしない**。
- 文字数カウント: **全角2字・半角1字・URL23字換算**で **280以内**。
- 直近重複除外: **全投稿タイプ横断（new/rotation/topic）・直近7日**。環境変数 `ROTATION_EXCLUDE_DAYS=7`。
- `collect_news.py` の依存は **`requests` と標準ライブラリのみ**（pytrends 等は入れない）。
- 投稿時刻: **JST 07:30**（CF Workers cron `"30 22 * * *"`）。
- コミットメッセージに**矢印記号（→ 等）や特殊記号を入れない**（CF Pages のデプロイAPIが弾くため）。
- 出力に「おんじ」という語を含めない。
- 煽り表現（爆益・億り人・必ず儲かる・○○一択）を投稿文に使わない。
- リポジトリルート: `C:\Users\oui_k\OneDrive\finlab-se`。スクリプトは `.github/scripts/`。

## File Structure

| 区分 | パス | 責務 |
|---|---|---|
| Create | `.github/scripts/collect_news.py` | Yahoo!経済ランキング＋Google News RSS を取得し順位つきで出力 |
| Create | `.github/scripts/select_topic.py` | ニュース＋記事一覧＋除外リストから Claude(Opus) で1記事選定し投稿文を作る |
| Create | `.github/scripts/tests/conftest.py` | pytest 共通フィクスチャ（sys.path 通し） |
| Create | `.github/scripts/tests/test_select_topic.py` | 文字数・除外・記事一覧・選定パースの単体テスト |
| Create | `.github/scripts/tests/test_collect_news.py` | ニュース抽出・フォールバックの単体テスト |
| Create | `.github/scripts/tests/test_morning_post.py` | 選定あり/該当なし/失敗時の分岐テスト |
| Modify | `.github/scripts/morning_post.py` | `get_valid_pick()`→`select_topic_inline()` に置換。pick関連削除 |
| Modify | `.github/workflows/x-post-scheduled.yml` | deps に `anthropic`、env に APIキーと `ROTATION_EXCLUDE_DAYS`、commitステップから pick 行削除 |
| Modify | `workers/x-post-trigger/wrangler.toml` | cron `5 22`→`30 22` |
| Modify | `workers/x-post-trigger/src/index.js` | case `5 22`→`30 22` |
| Delete | `data/x-topic-pick.yaml` | 中間ファイル廃止 |
| Delete | `.github/scripts/set_topic_pick.py` | pickライター廃止 |
| 手動 | `~/.claude/scheduled-tasks/x-morning-topic-pick-{2200,0630}/` | ローカルタスク廃止 |

**再利用**: `generate_post_text.py` の `parse_frontmatter()` と `build_url()` を import して使う（DRY）。

---

### Task 1: 文字数カウント関数 `count_x_length()`

**Files:**
- Create: `.github/scripts/select_topic.py`
- Create: `.github/scripts/tests/conftest.py`
- Test: `.github/scripts/tests/test_select_topic.py`

**Interfaces:**
- Produces: `count_x_length(text: str) -> int` — 文中の `https?://…` を23字換算、その他は全角2・半角1で合計した整数を返す。

- [ ] **Step 1: pytest 導入とフィクスチャ作成**

`.github/scripts/tests/conftest.py`:
```python
import sys
from pathlib import Path

# .github/scripts をインポートパスに通す（テストから各スクリプトを import するため）
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
```

- [ ] **Step 2: Write the failing test**

`.github/scripts/tests/test_select_topic.py`:
```python
from select_topic import count_x_length


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -v`
Expected: FAIL（`ImportError: cannot import name 'count_x_length'` または `ModuleNotFoundError`）。pytest 未導入なら `pip install pytest` を先に実行。

- [ ] **Step 4: Write minimal implementation**

`.github/scripts/select_topic.py`（新規・冒頭）:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -v`
Expected: PASS（4件）。

- [ ] **Step 6: Commit**

```bash
git add .github/scripts/select_topic.py .github/scripts/tests/conftest.py .github/scripts/tests/test_select_topic.py
git commit -m "feat(x-select): add X-weighted character counter with tests"
```

---

### Task 2: 直近7日の除外集合 `load_recent_post_paths()`

**Files:**
- Modify: `.github/scripts/select_topic.py`
- Test: `.github/scripts/tests/test_select_topic.py`

**Interfaces:**
- Consumes: なし（ファイルを直接読む）。
- Produces: `load_recent_post_paths(repo_root: Path, days: int, now: datetime) -> set[str]` — `x-rotation.yaml` の `last_promoted` が直近 `days` 日以内の `post_path`、および `x-post-history.yaml` の `posted_at` が直近 `days` 日以内の `post_path` を合わせた集合を返す。

- [ ] **Step 1: Write the failing test**

`tests/test_select_topic.py` に追記:
```python
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from select_topic import load_recent_post_paths

JST = timezone(timedelta(hours=9))


def _write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -k recent -v`
Expected: FAIL（`cannot import name 'load_recent_post_paths'`）。

- [ ] **Step 3: Write minimal implementation**

`select_topic.py` に追記:
```python
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -k recent -v`
Expected: PASS（2件）。

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/select_topic.py .github/scripts/tests/test_select_topic.py
git commit -m "feat(x-select): add recent-post exclusion across rotation and history"
```

---

### Task 3: 記事一覧の構築 `build_article_catalog()`

**Files:**
- Modify: `.github/scripts/select_topic.py`
- Test: `.github/scripts/tests/test_select_topic.py`

**Interfaces:**
- Consumes: `generate_post_text.parse_frontmatter(md_text) -> dict`（既存・キー: title/description/slug/tags/cover_image）、`generate_post_text.build_url(post_path, slug) -> str`（既存）、`load_recent_post_paths`（Task 2）。
- Produces: `build_article_catalog(repo_root: Path, exclude_paths: set[str], permanently_excluded: set[str]) -> list[dict]` — 各要素 `{post_path, title, url, categories, tags, description}`。`exclude_paths`（直近7日）と `permanently_excluded`（`x-rotation.yaml` の `exclude: true`）の記事は含めない。

- [ ] **Step 1: Write the failing test**

`tests/test_select_topic.py` に追記:
```python
from select_topic import build_article_catalog


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -k catalog -v`
Expected: FAIL（`cannot import name 'build_article_catalog'`）。

- [ ] **Step 3: Write minimal implementation**

`select_topic.py` に追記（`parse_frontmatter` の categories 抽出は既存に無いため、ここで補助関数を足す）:
```python
import re as _re
from generate_post_text import parse_frontmatter, build_url


def _extract_categories(md_text: str) -> list:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -k catalog -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/select_topic.py .github/scripts/tests/test_select_topic.py
git commit -m "feat(x-select): build article catalog with exclusions reusing frontmatter parser"
```

---

### Task 4: ニュース取得 `collect_news.py`

**Files:**
- Create: `.github/scripts/collect_news.py`
- Test: `.github/scripts/tests/test_collect_news.py`

**Interfaces:**
- Produces:
  - `parse_yahoo_ranking(html: str) -> list[dict]` — `{rank, title, url}` のリスト（上位順）。
  - `parse_google_news_rss(xml_text: str) -> list[dict]` — `{title, url}` のリスト。
  - `collect(fetch=<callable>) -> dict` — `{"yahoo": [...], "google": [...]}`。`fetch(url)->str` は差し替え可能（テスト用）。取得失敗側は空リスト。
  - `main()` — `collect()` を実行して JSON を stdout に出す。

- [ ] **Step 1: Write the failing test**

`.github/scripts/tests/test_collect_news.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .github/scripts && python -m pytest tests/test_collect_news.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'collect_news'`）。

- [ ] **Step 3: Write minimal implementation**

`.github/scripts/collect_news.py`:
```python
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


def parse_yahoo_ranking(html: str) -> list:
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


def parse_google_news_rss(xml_text: str) -> list:
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


def collect(fetch=http_fetch) -> dict:
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


def main():
    print(json.dumps(collect(), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .github/scripts && python -m pytest tests/test_collect_news.py -v`
Expected: PASS（3件）。

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/collect_news.py .github/scripts/tests/test_collect_news.py
git commit -m "feat(x-news): add server-side news collector for Yahoo ranking and Google News"
```

---

### Task 5: Claude選定本体 `select_topic.py`（プロンプト・API・280検証・main）

**Files:**
- Modify: `.github/scripts/select_topic.py`
- Test: `.github/scripts/tests/test_select_topic.py`

**Interfaces:**
- Consumes: `count_x_length`（T1）、`load_recent_post_paths`/`load_permanently_excluded`（T2/T3）、`build_article_catalog`（T3）。
- Produces:
  - `build_messages(news: dict, catalog: list) -> tuple[str, str]` — `(system, user)` プロンプト文字列。
  - `select(news: dict, repo_root: Path, now: datetime, call=<callable>) -> dict` — 選定結果。`call(system, user) -> dict` は Claude 呼び出しを差し替え可能にしたフック（テスト用）。280字超なら1回だけ短縮再依頼し、なお超過なら `selected_post_path: null`。
  - `main()` — stdin から news(JSON) を読み、`select()` を実行して stdout に JSON。

- [ ] **Step 1: Write the failing test**

`tests/test_select_topic.py` に追記:
```python
from datetime import datetime
from select_topic import select


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


def test_select_retries_once_on_overflow_then_nulls(tmp_path):
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
    assert calls["n"] == 2          # 初回＋短縮再依頼の2回
    assert out["selected_post_path"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -k select -v`
Expected: FAIL（`cannot import name 'select'`）。

- [ ] **Step 3: Write minimal implementation**

`select_topic.py` に追記:
```python
import json
import os

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
    "2ソース両方に上位で出る話題ほど優先。\n"
    "- 手順: (1)ホットな話題を上位5件ランク付け (2)各話題に自然にマッチする記事候補を挙げる"
    "(3)マッチが成立した話題をホットな順に見て最上位の記事を採用。\n"
    "- こじつけ禁止。自然に合う記事が無ければ selected_post_path を null にする。\n"
    "- 投稿文は280字以内（全角2字・半角1字・URL23字換算）、1段落推奨、"
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
    for attempt in range(2):  # 初回 + 短縮再依頼1回
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
        if attempt == 0:
            retry_user = user + "\n\n直前の投稿文は280字を超えました。280字以内に短くして同じ記事で作り直してください。"
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .github/scripts && python -m pytest tests/test_select_topic.py -v`
Expected: PASS（全件。selectの3件含む）。

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/select_topic.py .github/scripts/tests/test_select_topic.py
git commit -m "feat(x-select): add Claude topic selection with length check and fallback"
```

---

### Task 6: `morning_post.py` をインライン選定に改修

**Files:**
- Modify: `.github/scripts/morning_post.py`
- Test: `.github/scripts/tests/test_morning_post.py`

**Interfaces:**
- Consumes: `collect_news.py`・`select_topic.py`（subprocess 経由）、選定記事の frontmatter（`cover.image`）。
- Produces: `select_topic_inline() -> dict | None` — 成功時 `{post_path, text, image_path}`、選定なし/失敗時 `None`。`post_topic()` は既存（`pick["text"]`・`pick["image_path"]` を使う）をそのまま利用。

- [ ] **Step 1: Write the failing test**

`.github/scripts/tests/test_morning_post.py`:
```python
import json
import types
import morning_post


def test_inline_returns_pick_on_selection(monkeypatch, tmp_path):
    # 記事ファイルを用意
    posts = tmp_path / "content/posts"
    posts.mkdir(parents=True)
    (posts / "loan.md").write_text(
        '---\ntitle: "T"\ndescription: "D"\ntags: ["x"]\n'
        'cover:\n  image: "/images/loan.png"\n---\n本文\n', encoding="utf-8")
    monkeypatch.setattr(morning_post, "REPO_ROOT", tmp_path)

    # collect_news / select_topic の subprocess をスタブ
    def fake_run(cmd, **kwargs):
        out = ""
        if "collect_news.py" in cmd[1]:
            out = json.dumps({"yahoo": [], "google": []})
        elif "select_topic.py" in cmd[1]:
            out = json.dumps({"selected_post_path": "content/posts/loan.md",
                              "text": "本文 https://finlab-se.com/posts/loan/",
                              "topic_reason": "r", "candidates": []})
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(morning_post.subprocess, "run", fake_run)
    pick = morning_post.select_topic_inline()
    assert pick["post_path"] == "content/posts/loan.md"
    assert pick["image_path"] == "/images/loan.png"


def test_inline_returns_none_when_no_match(monkeypatch, tmp_path):
    monkeypatch.setattr(morning_post, "REPO_ROOT", tmp_path)

    def fake_run(cmd, **kwargs):
        out = json.dumps({"yahoo": [], "google": []}) if "collect_news.py" in cmd[1] \
            else json.dumps({"selected_post_path": None, "reason": "none", "candidates": []})
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(morning_post.subprocess, "run", fake_run)
    assert morning_post.select_topic_inline() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd .github/scripts && python -m pytest tests/test_morning_post.py -v`
Expected: FAIL（`module 'morning_post' has no attribute 'select_topic_inline'`）。

- [ ] **Step 3: Write minimal implementation**

`morning_post.py` を編集:

(a) `get_valid_pick()` と `clear_pick()` を削除し、`PICK_PATH` 定義も削除。

(b) 次の関数を追加（`_read_cover_image` で frontmatter から画像取得）:
```python
def _run_capture(script: str, stdin_text: str | None = None) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script)],
        input=stdin_text, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(f"{script} failed: {proc.stderr}\n")
        return ""
    return proc.stdout.strip()


def _read_cover_image(post_path: str) -> str:
    import re
    md = (REPO_ROOT / post_path).read_text(encoding="utf-8")
    m = re.search(r'cover:\s*\n\s*image:\s*"(.*?)"', md)
    return m.group(1) if m else ""


def select_topic_inline():
    """ニュース取得→Claude選定をその場で行う。成功時 pick dict、なければ None。"""
    news = _run_capture("collect_news.py")
    if not news:
        return None
    result_raw = _run_capture("select_topic.py", stdin_text=news)
    if not result_raw:
        return None
    try:
        result = json.loads(result_raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"select_topic.py output not JSON: {e}\n")
        return None
    post_path = result.get("selected_post_path")
    if not post_path or not (REPO_ROOT / post_path).exists():
        return None
    return {
        "post_path": post_path,
        "text": result.get("text", ""),
        "image_path": _read_cover_image(post_path),
    }
```

(c) `main()` の `pick = get_valid_pick()` を `pick = select_topic_inline()` に変更（以降の `if pick:` 分岐はそのまま）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd .github/scripts && python -m pytest tests/test_morning_post.py -v`
Expected: PASS（2件）。

- [ ] **Step 5: 全テスト通し**

Run: `cd .github/scripts && python -m pytest tests/ -v`
Expected: PASS（全件）。

- [ ] **Step 6: Commit**

```bash
git add .github/scripts/morning_post.py .github/scripts/tests/test_morning_post.py
git commit -m "feat(x-morning): select topic inline at post time, drop pick file dependency"
```

---

### Task 7: ワークフロー改修と廃止ファイル削除

**Files:**
- Modify: `.github/workflows/x-post-scheduled.yml`
- Delete: `data/x-topic-pick.yaml`, `.github/scripts/set_topic_pick.py`

**Interfaces:**
- Consumes: `morning_post.py`（T6）、`ANTHROPIC_API_KEY`（GitHub Secrets）。

- [ ] **Step 1: deps に anthropic を追加**

`x-post-scheduled.yml` の Install deps を変更:
```yaml
      - name: Install deps
        run: pip install requests requests-oauthlib ruamel.yaml PyYAML anthropic
```

- [ ] **Step 2: Morning post ステップに env を追加**

`Morning post (recommendation only)` ステップの `env:` に追記:
```yaml
        env:
          X_API_KEY: ${{ secrets.X_API_KEY }}
          X_API_SECRET: ${{ secrets.X_API_SECRET }}
          X_ACCESS_TOKEN: ${{ secrets.X_ACCESS_TOKEN }}
          X_ACCESS_TOKEN_SECRET: ${{ secrets.X_ACCESS_TOKEN_SECRET }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          ROTATION_EXCLUDE_DAYS: "7"
```

- [ ] **Step 3: Commit morning changes ステップから pick 行を削除**

`Commit morning changes` ステップ内の次の行を**削除**する:
```
          [ -f data/x-topic-pick.yaml ] && git add data/x-topic-pick.yaml
```
（`x-rotation.yaml`・`x-post-state.yaml`・`x-post-history.yaml` の add 行は残す。）

- [ ] **Step 4: 廃止ファイルを削除**

```bash
git rm data/x-topic-pick.yaml .github/scripts/set_topic_pick.py
```

- [ ] **Step 5: ワークフロー構文の確認**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/x-post-scheduled.yml',encoding='utf-8')); print('yaml ok')"`
Expected: `yaml ok`

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/x-post-scheduled.yml
git commit -m "chore(x-morning): wire anthropic deps and 7-day exclusion, retire pick file"
```

---

### Task 8: CF Workers の投稿時刻を 7:30 に変更

**Files:**
- Modify: `workers/x-post-trigger/wrangler.toml`
- Modify: `workers/x-post-trigger/src/index.js`

- [ ] **Step 1: wrangler.toml の cron を変更**

`crons` 配列の `"5 22 * * *"` を `"30 22 * * *"` に変更し、コメントの「JST 07:05」を「JST 07:30」に直す:
```toml
crons = [
  "35 20 * * *",
  "35 21 * * *",
  "30 22 * * *",
  "5 12 * * *",
]
```

- [ ] **Step 2: index.js の case を変更**

`dispatchParamsFromCron` の `case "5 22 * * *":` を `case "30 22 * * *":` に変更:
```javascript
    case "30 22 * * *":
      return { workflow: "x-post-scheduled.yml", inputs: { slot: "morning" } };
```
（コメント中の `JST 07:05` 表記も `JST 07:30` に直す。）

- [ ] **Step 3: Commit**

```bash
git add workers/x-post-trigger/wrangler.toml workers/x-post-trigger/src/index.js
git commit -m "chore(x-trigger): move morning post from 07:05 to 07:30 JST"
```

> デプロイ（`wrangler deploy`）は Task 9 の手動手順で行う。

---

### Task 9: 手動セットアップと本番切替（リポジトリ外・要オペレーター作業）

これはコードでなく運用手順。実装エージェントは**チェックリストとして提示**し、オペレーター（人間）が実行する。

- [ ] **Step 1: ANTHROPIC_API_KEY を GitHub Secrets に登録**

GitHub リポジトリ `nyo0521-a11y/finlab-se` の Settings → Secrets and variables → Actions → New repository secret。
Name: `ANTHROPIC_API_KEY` / Value: Anthropic コンソールで発行した API キー。
（コード・YAML には絶対に書かない。）

- [ ] **Step 2: dry-run で選定結果だけ確認（実投稿しない）**

ローカルで:
```bash
cd /c/Users/oui_k/OneDrive/finlab-se
ANTHROPIC_API_KEY=<キー> ROTATION_EXCLUDE_DAYS=7 \
  python .github/scripts/collect_news.py | \
  ANTHROPIC_API_KEY=<キー> ROTATION_EXCLUDE_DAYS=7 \
  python .github/scripts/select_topic.py
```
出力 JSON の `selected_post_path`・`text`・`candidates` を目視確認。`text` が280字以内・煽り表現なし・URL入りであること。

- [ ] **Step 3: CF Worker をデプロイ**

```bash
cd /c/Users/oui_k/OneDrive/finlab-se/workers/x-post-trigger
wrangler deploy
```
デプロイ後、Cloudflare ダッシュボードで cron が `30 22 * * *` になっていることを確認。

- [ ] **Step 4: ローカルスケジュールタスクを廃止**

不要になったローカルタスク2本を削除（PCのファイル操作）:
- `C:\Users\oui_k\.claude\scheduled-tasks\x-morning-topic-pick-2200\`
- `C:\Users\oui_k\.claude\scheduled-tasks\x-morning-topic-pick-0630\`

- [ ] **Step 5: 翌朝の本番確認**

翌朝7:30台に `gh run list --workflow=x-post-scheduled.yml --limit 3` で morning run が success か確認。
ログに選定結果（`Morning result:`）が出ていること、X に投稿されていることを確認。
万一失敗していても通常おすすめにフォールバックして投稿される設計（無投稿にはならない）。

---

## Self-Review

**1. Spec coverage**

| spec項目 | 対応タスク |
|---|---|
| 7:30インライン選定・即投稿 | T6・T8 |
| 中間ファイル廃止 | T7（削除）・T6（依存除去） |
| 客観ニュース取得（Yahoo+Google） | T4 |
| 候補を広げて絞る2段階・こじつけ禁止 | T5（プロンプト） |
| 全タイプ横断・直近7日除外 | T2・T7（env） |
| 280字検証（全角2・半角1・URL23）・1回再依頼 | T1・T5 |
| 画像はframtmatterから取得（パス化け防止） | T6（`_read_cover_image`） |
| フォールバック（無投稿にしない） | T5・T6（None→既存rotation） |
| Claude Opus・APIキーはSecrets | T5・T7・T9 |
| ローカルタスク廃止 | T9 |
| cron 7:30 | T8 |

ギャップなし。

**2. Placeholder scan**: 各ステップに実コード・実コマンド・期待結果を記載済み。「TBD/適宜」等なし。

**3. Type consistency**: `count_x_length(text)`・`load_recent_post_paths(repo_root, days, now)`・`build_article_catalog(repo_root, exclude_paths, permanently_excluded)`・`load_permanently_excluded(repo_root)`・`select(news, repo_root, now, call)`・`select_topic_inline()` の戻り値 `{post_path, text, image_path}` は T1〜T6 で一貫。`post_topic(pick)` は既存の `pick["text"]`／`pick["image_path"]` 参照と一致。
