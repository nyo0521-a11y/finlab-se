# Google Trends 話題ソース追加＋自動処理エラー検知 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 朝のX話題選定に Google Trends（検索急上昇ワード）を3本目のソースとして追加し、時間実行の自動処理のエラー（ジョブ失敗＋ニュースソースのサイレント故障）を GitHub Issues に記録して Claude 起動時に検知する仕組みを作る。

**Architecture:** `collect_news.py` に Trends RSS パーサを追加して出力を3キー化。エラー報告は新設の `report_automation_error.py` に集約し、ワークフローから `if: always()` / `if: failure()` で呼ぶ。ローカルは SessionStart フック（.mjs）が Open な `automation-error` Issue を検知して Claude に指示を出す。

**Tech Stack:** Python 3.11（requests＋標準ライブラリのみ）/ pytest / GitHub Actions / gh CLI / Node.js（フックスクリプト）

## Global Constraints

- `collect_news.py` の依存は **requests と標準ライブラリのみ**（pytrends 等の外部ライブラリ禁止）
- Trends RSS URL: `https://trends.google.co.jp/trending/rss?geo=JP`（キー不要・2026-07-02 実地検証済み）
- Trends の XML 名前空間: `https://trends.google.com/trending/rss`（**URLは .co.jp でも名前空間は .com**。実地確認済み）
- ソース単位の graceful degradation: 1ソースの失敗で他ソース・処理全体を落とさない
- エラーログは GitHub Issues、ラベル `automation-error`、**同一タイトルの Open Issue があれば作成しない**（重複防止）
- ソフトエラー検査は morning スロットのみ。rotation へのフォールバック自体はエラー扱いしない
- Issue タイトル形式: `[automation-error] <ワークフロー>/<スロット>: <要約>`
- フックは Open Issue が 0 件なら**何も出力しない**。gh 失敗時も静かにスキップ
- コミットメッセージに矢印記号（→ 等）・特殊記号を入れない
- 出力に「おんじ」を含めない
- リポジトリルート: `C:\Users\oui_k\OneDrive\finlab-se`。テストは `python -m pytest .github/scripts/tests/ -v`

## File Structure

| 区分 | パス | 責務 |
|---|---|---|
| Modify | `.gitignore` | `__pycache__/` を除外（掃除） |
| Modify | `.github/scripts/collect_news.py` | Trends RSS パーサ追加・collect() 3キー化 |
| Modify | `.github/scripts/select_topic.py` | `_SYSTEM` に trends の扱いを追記 |
| Modify | `.github/scripts/morning_post.py` | 件数ログ行に trends を追加 |
| Create | `.github/scripts/report_automation_error.py` | Issue 作成（ハード/ソフト判定・重複防止） |
| Create | `.github/scripts/tests/test_report_automation_error.py` | 上記の単体テスト |
| Modify | `.github/scripts/tests/test_collect_news.py` | Trends のテスト追加 |
| Modify | `.github/scripts/tests/test_morning_post.py` | ログ行のテスト強化 |
| Modify | `.github/workflows/x-post-scheduled.yml` | permissions・stderr捕捉・報告ステップ |
| Modify | `.github/workflows/deploy.yml` | permissions・failure報告ステップ（production ジョブ） |
| Create | `C:/Users/oui_k/.claude/scripts/check-automation-errors.mjs` | 起動時チェックフック |
| Modify | `C:/Users/oui_k/.claude/settings.json` | SessionStart フック追記 |

---

### Task 1: `__pycache__` を git 管理から外す

**Files:**
- Modify: `.gitignore`
- Delete(cached): `.github/scripts/__pycache__/`

- [ ] **Step 1: .gitignore に追記**

`.gitignore` の末尾に以下を追加（ファイルが無ければ作成）:

```
__pycache__/
*.pyc
```

- [ ] **Step 2: キャッシュから外す**

```bash
git rm -r --cached .github/scripts/__pycache__/
```

- [ ] **Step 3: 動作確認**

```bash
python -m pytest .github/scripts/tests/ -q && git status --short
```

Expected: テスト全PASS、`git status` に `__pycache__` 配下が**現れない**（.gitignore 行と削除のみステージされている）。

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: stop tracking __pycache__ build artifacts"
```

---

### Task 2: Google Trends RSS を3本目のソースに追加

**Files:**
- Modify: `.github/scripts/collect_news.py`
- Test: `.github/scripts/tests/test_collect_news.py`

**Interfaces:**
- Produces: `parse_google_trends_rss(xml_text: str) -> list[dict]`（各要素 `{title: str, traffic: str}`、traffic欠落時は空文字）。`collect(fetch)` の戻り値が `{"yahoo": [...], "google": [...], "trends": [...]}` の3キーになる。

- [ ] **Step 1: Write the failing tests**

`tests/test_collect_news.py` に追記:

```python
from collect_news import parse_google_trends_rss


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
```

- [ ] **Step 2: Run to verify FAIL**

Run: `python -m pytest .github/scripts/tests/test_collect_news.py -v`
Expected: FAIL（`cannot import name 'parse_google_trends_rss'`）

- [ ] **Step 3: Implement**

`collect_news.py` — モジュール docstring の3ソース化に加え、定数と関数を追加:

```python
TRENDS_RSS = "https://trends.google.co.jp/trending/rss?geo=JP"
_HT_NS = "{https://trends.google.com/trending/rss}"


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
```

`collect()` を3ソース化（既存の yahoo/google ブロックはそのまま、trends ブロックを追加し、戻り値に `"trends": trends` を追加）:

```python
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
```

- [ ] **Step 4: Run to verify PASS**

Run: `python -m pytest .github/scripts/tests/test_collect_news.py -v`
Expected: 全PASS（既存4件＋新規3件）

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/collect_news.py .github/scripts/tests/test_collect_news.py
git commit -m "feat(x-news): add Google Trends RSS as third news source"
```

---

### Task 3: 選定プロンプトとログ行の trends 対応

**Files:**
- Modify: `.github/scripts/select_topic.py`（`_SYSTEM`）
- Modify: `.github/scripts/morning_post.py`（件数ログ行）
- Test: `.github/scripts/tests/test_morning_post.py`

**Interfaces:**
- Consumes: Task 2 の `collect()` 3キー出力
- Produces: stderr ログ行フォーマット `collect_news: yahoo=N google=N trends=N`（Task 4 のソフトエラー判定がこの形式に依存する）

- [ ] **Step 1: Write the failing test**

`tests/test_morning_post.py` の `test_inline_returns_pick_on_selection` を強化。`fake_run` の collect_news 出力に trends を含め、stderr のログ行を検証する（関数シグネチャに `capsys` を追加）:

```python
def test_inline_returns_pick_on_selection(monkeypatch, tmp_path, capsys):
```

`fake_run` の collect_news 分岐を差し替え:

```python
        if "collect_news.py" in cmd[1]:
            out = json.dumps({"yahoo": [{"rank": 1, "title": "t", "url": "u"}],
                              "google": [], "trends": [{"title": "日銀", "traffic": "1000+"}]})
```

既存アサーションの後に追加:

```python
    err = capsys.readouterr().err
    assert "collect_news: yahoo=1 google=0 trends=1" in err
```

- [ ] **Step 2: Run to verify FAIL**

Run: `python -m pytest .github/scripts/tests/test_morning_post.py -v`
Expected: FAIL（ログ行に `trends=` が無い）

- [ ] **Step 3: Implement**

(a) `morning_post.py` の件数ログを差し替え:

```python
            sys.stderr.write(
                f"collect_news: yahoo={len(_nd.get('yahoo', []))} "
                f"google={len(_nd.get('google', []))} "
                f"trends={len(_nd.get('trends', []))}\n"
            )
```

（現在の同ブロックは trends 無しの2ソース版。`google=...` の後に trends を挿入する形で置換。）

(b) `select_topic.py` の `_SYSTEM` に trends ルールを追加。現在の行:

```python
    "- ホットさは渡された順位データを根拠に判断する（自分でキーワードを作らない）。"
    "2ソース両方に上位で出る話題ほど優先。\n"
```

を以下に置換:

```python
    "- ホットさは渡された順位データを根拠に判断する（自分でキーワードを作らない）。"
    "複数ソースに跨って上位に出る話題ほど優先。\n"
    "- trends は日本全体の検索急上昇ワード（分野を問わない一般ランキング。"
    "traffic は概算検索数）。金融・経済に関するワードが含まれる場合のみ強い加点材料とし、"
    "スポーツ・芸能など金融と無関係なワードは無視する。\n"
```

- [ ] **Step 4: Run full suite**

Run: `python -m pytest .github/scripts/tests/ -v`
Expected: 全PASS

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/select_topic.py .github/scripts/morning_post.py .github/scripts/tests/test_morning_post.py
git commit -m "feat(x-select): weigh Google Trends signal and log trends count"
```

---

### Task 4: エラー報告スクリプト `report_automation_error.py`

**Files:**
- Create: `.github/scripts/report_automation_error.py`
- Test: `.github/scripts/tests/test_report_automation_error.py`

**Interfaces:**
- Produces:
  - `find_soft_error(stderr_text: str) -> str | None` — morning の stderr からソフトエラー要約を返す（正常なら None）。`collect_news: yahoo=N google=N trends=N` 行を探し、行が無ければ `"ニュース収集失敗 (collect_news行なし)"`、0件ソースがあれば `"ニュースソース0件 (trends)"` のように返す
  - `report(title: str, body: str, run) -> str` — 同一タイトルの Open Issue があれば `"skipped"`、無ければ作成して `"created"`。`run(args: list[str]) -> str` は gh CLI 実行の注入ポイント
  - CLI: `--workflow --slot --job-status --run-url [--stderr-file]`

- [ ] **Step 1: Write the failing tests**

`.github/scripts/tests/test_report_automation_error.py`:

```python
import json
from report_automation_error import find_soft_error, report, build_title


def test_find_soft_error_none_when_healthy():
    err = "collect_news: yahoo=15 google=69 trends=10\nselect_topic: selected=None reason=x\n"
    assert find_soft_error(err) is None


def test_find_soft_error_detects_zero_sources():
    err = "collect_news: yahoo=15 google=0 trends=0\n"
    got = find_soft_error(err)
    assert "google" in got and "trends" in got and "0件" in got


def test_find_soft_error_detects_missing_line():
    err = "collect_news returned empty output; fallback to rotation\n"
    got = find_soft_error(err)
    assert "collect_news行なし" in got


def test_build_title():
    assert build_title("x-post-scheduled", "morning", "ニュースソース0件 (trends)") == \
        "[automation-error] x-post-scheduled/morning: ニュースソース0件 (trends)"


def test_report_skips_when_same_open_title_exists():
    calls = []
    def fake_run(args):
        calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"title": "[automation-error] w/s: x"}])
        raise AssertionError("create should not be called")
    assert report("[automation-error] w/s: x", "body", run=fake_run) == "skipped"


def test_report_creates_when_new():
    calls = []
    def fake_run(args):
        calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([])
        return "https://github.com/o/r/issues/99"
    assert report("[automation-error] w/s: new", "body", run=fake_run) == "created"
    assert any(args[:2] == ["issue", "create"] for args in calls)
```

- [ ] **Step 2: Run to verify FAIL**

Run: `python -m pytest .github/scripts/tests/test_report_automation_error.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: Implement**

`.github/scripts/report_automation_error.py`:

```python
"""自動処理のエラーを GitHub Issues（ラベル automation-error）に記録する。

2種類のエラーを扱う:
  - ハードエラー: ジョブ失敗（--job-status failure）
  - ソフトエラー: morning スロットでニュースソースが0件 / 件数行が無い
同一タイトルの Open Issue が既にあれば作成しない（故障継続で毎日増えない）。
gh CLI（ランナー標準搭載・GH_TOKEN）で操作する。

使い方（ワークフローの if: always() ステップから）:
    python report_automation_error.py \
        --workflow x-post-scheduled --slot morning --job-status success \
        --run-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" \
        --stderr-file stderr.log
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

LABEL = "automation-error"
_COUNTS_RE = re.compile(r"collect_news: (\w+=\d+(?: \w+=\d+)*)")


def find_soft_error(stderr_text: str) -> str | None:
    """morning の stderr からソフトエラー要約を返す。正常なら None。"""
    m = _COUNTS_RE.search(stderr_text)
    if not m:
        return "ニュース収集失敗 (collect_news行なし)"
    zero = [pair.split("=")[0] for pair in m.group(1).split() if pair.endswith("=0")]
    if zero:
        return f"ニュースソース0件 ({', '.join(zero)})"
    return None


def build_title(workflow: str, slot: str, summary: str) -> str:
    return f"[automation-error] {workflow}/{slot}: {summary}"


def _run_gh(args: list[str]) -> str:
    proc = subprocess.run(["gh"] + args, capture_output=True, text=True,
                          encoding="utf-8", check=True)
    return proc.stdout


def report(title: str, body: str, run=_run_gh) -> str:
    """同一タイトルの Open Issue が無ければ作成する。"""
    out = run(["issue", "list", "--state", "open", "--label", LABEL,
               "--json", "title", "--limit", "100"])
    existing = {item["title"] for item in json.loads(out or "[]")}
    if title in existing:
        print(f"skip (open issue exists): {title}")
        return "skipped"
    run(["issue", "create", "--title", title, "--body", body, "--label", LABEL])
    print(f"created issue: {title}")
    return "created"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--slot", required=True)
    ap.add_argument("--job-status", required=True)
    ap.add_argument("--run-url", required=True)
    ap.add_argument("--stderr-file", default="")
    args = ap.parse_args()

    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")
    issues = []  # (summary, kind)
    if args.job_status == "failure":
        issues.append(("ジョブ失敗", "ハードエラー"))
    elif args.slot == "morning":
        stderr_text = ""
        p = Path(args.stderr_file) if args.stderr_file else None
        if p and p.exists():
            stderr_text = p.read_text(encoding="utf-8", errors="replace")
        summary = find_soft_error(stderr_text)
        if summary:
            issues.append((summary, "ソフトエラー"))

    for summary, kind in issues:
        title = build_title(args.workflow, args.slot, summary)
        body = (
            f"- 発生日時: {now}\n"
            f"- 種類: {kind}\n"
            f"- ワークフロー: {args.workflow} / スロット: {args.slot}\n"
            f"- 実行ログ: {args.run_url}\n\n"
            "確認手順: 実行ログを開き、ソフトエラーの場合は collect_news の各ソース"
            "（Yahoo!経済ランキング / Google News RSS / Google Trends RSS）の取得可否を確認する。"
            "対応後、このIssueに対応内容をコメントしてCloseする。"
        )
        report(title, body)

    if not issues:
        print("no errors detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify PASS**

Run: `python -m pytest .github/scripts/tests/ -v`
Expected: 全PASS

- [ ] **Step 5: Commit**

```bash
git add .github/scripts/report_automation_error.py .github/scripts/tests/test_report_automation_error.py
git commit -m "feat(ops): add automation error reporter with GitHub Issues dedup"
```

---

### Task 5: ワークフロー配線（x-post-scheduled.yml / deploy.yml）

**Files:**
- Modify: `.github/workflows/x-post-scheduled.yml`
- Modify: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: Task 4 の CLI（`--workflow --slot --job-status --run-url --stderr-file`）と、Task 3 のログ行フォーマット

- [ ] **Step 1: x-post-scheduled.yml の permissions に issues を追加**

現在:

```yaml
permissions:
  contents: write
```

を以下に置換:

```yaml
permissions:
  contents: write
  issues: write
```

- [ ] **Step 2: morning ステップで stderr をファイルに捕捉**

`Morning post (recommendation only)` ステップの run 部分。現在:

```yaml
        run: |
          set +e
          RESULT=$(python .github/scripts/morning_post.py)
          EXIT_CODE=$?
          set -e
          echo "Morning result: $RESULT"
```

を以下に置換（stderr を `stderr.log` に落としつつ、従来どおり実行ログにも表示する）:

```yaml
        run: |
          set +e
          RESULT=$(python .github/scripts/morning_post.py 2>stderr.log)
          EXIT_CODE=$?
          set -e
          cat stderr.log >&2 || true
          echo "Morning result: $RESULT"
```

- [ ] **Step 3: ジョブ末尾に報告ステップを追加**

ジョブ `post` の最後（既存の最終ステップの後）に追加:

```yaml
      # =========================================
      # エラー報告：ジョブ失敗（ハード）と、morning のニュースソース0件（ソフト）を
      # GitHub Issues（ラベル automation-error）に記録する。同一タイトルのOpenがあれば作らない。
      # 報告処理自体の失敗でジョブを落とさないよう || true を付ける。
      # =========================================
      - name: Report automation errors
        if: always()
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: |
          python .github/scripts/report_automation_error.py \
            --workflow x-post-scheduled \
            --slot "${{ steps.slot.outputs.slot }}" \
            --job-status "${{ job.status }}" \
            --run-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" \
            --stderr-file stderr.log || true
```

- [ ] **Step 4: deploy.yml の production ジョブに failure 報告を追加**

`production` ジョブの permissions。現在:

```yaml
    permissions:
      contents: write   # cron 時に x-queue.yaml をコミット・プッシュするため write が必要
      deployments: write
```

を以下に置換:

```yaml
    permissions:
      contents: write   # cron 時に x-queue.yaml をコミット・プッシュするため write が必要
      deployments: write
      issues: write     # 失敗時の automation-error Issue 作成用
```

`production` ジョブの最終ステップ（`Commit newly-enqueued posts` の後）に追加:

```yaml
      - name: Report job failure
        if: failure()
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: |
          python3 .github/scripts/report_automation_error.py \
            --workflow deploy \
            --slot production \
            --job-status failure \
            --run-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" || true
```

（draft-preview ジョブは push 時に人が見ている操作なので対象外＝spec §2.4 のとおり時間実行の production 経路のみ。）

- [ ] **Step 5: YAML 構文検証**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/x-post-scheduled.yml', encoding='utf-8')); yaml.safe_load(open('.github/workflows/deploy.yml', encoding='utf-8')); print('yaml ok')"
```

Expected: `yaml ok`

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/x-post-scheduled.yml .github/workflows/deploy.yml
git commit -m "feat(ops): report job failures and silent news-source failures as issues"
```

---

### Task 6: 起動時チェックフック（ローカル）

**Files:**
- Create: `C:/Users/oui_k/.claude/scripts/check-automation-errors.mjs`
- Modify: `C:/Users/oui_k/.claude/settings.json`（SessionStart フック配列に1エントリ追加）

**Interfaces:**
- Consumes: GitHub Issues（ラベル `automation-error`、リポジトリ `nyo0521-a11y/finlab-se`）、ローカルの gh CLI（認証済み）

- [ ] **Step 1: フックスクリプト作成**

`C:/Users/oui_k/.claude/scripts/check-automation-errors.mjs`:

```javascript
#!/usr/bin/env node
/**
 * check-automation-errors.mjs
 * SessionStart フックから呼ばれる。
 * finlab-se の自動処理エラー（ラベル automation-error の Open Issue）を確認し、
 * あれば Claude に報告・調査・対応を促すメッセージを出力する。
 * 0件・gh失敗時は何も出力しない（起動を汚さない）。
 */

import { execFileSync } from 'child_process';

const REPO = 'nyo0521-a11y/finlab-se';

try {
  const out = execFileSync(
    'gh',
    ['issue', 'list', '-R', REPO, '--label', 'automation-error',
     '--state', 'open', '--json', 'number,title,createdAt,url'],
    { encoding: 'utf8', timeout: 15000, windowsHide: true },
  );
  const issues = JSON.parse(out || '[]');
  if (issues.length === 0) process.exit(0);

  const lines = issues.map(
    (i) => `- #${i.number} ${i.title}（${new Date(i.createdAt).toLocaleString('ja-JP')}） ${i.url}`,
  );
  console.log(
    `【自動アラート】finlab-se の自動処理で未対応のエラーが ${issues.length} 件あります。\n` +
    lines.join('\n') + '\n' +
    `対応手順: (1)ユーザーにこのエラーを報告する (2)Issue本文の実行ログURLと ` +
    `gh run view で原因を調査する (3)修正する (4)対応内容をIssueにコメントして ` +
    `gh issue close で閉じる（閉じると次回起動から通知されない）。`,
  );
} catch (_) {
  // gh未認証・オフライン等では静かにスキップ
}
```

- [ ] **Step 2: settings.json にフック追加**

`C:/Users/oui_k/.claude/settings.json` の SessionStart フック配列内、`check-news-collection.mjs` のエントリの直後に追加（JSON構文に注意・カンマ）:

```json
          {
            "type": "command",
            "command": "node 'C:/Users/oui_k/.claude/scripts/check-automation-errors.mjs' 2>/dev/null || true",
            "statusMessage": "自動処理エラーの有無を確認中..."
          }
```

- [ ] **Step 3: 動作確認（エラー0件＝無出力）**

```bash
node "C:/Users/oui_k/.claude/scripts/check-automation-errors.mjs"; echo "exit=$?"
```

Expected: 何も出力されず `exit=0`（現時点で Open Issue が無いため）

- [ ] **Step 4: settings.json の構文確認**

```bash
python -c "import json; json.load(open('C:/Users/oui_k/.claude/settings.json', encoding='utf-8')); print('json ok')"
```

Expected: `json ok`

- [ ] **Step 5: Commit（finlab-se 側の変更のみ・ローカル設定はリポジトリ外）**

このタスクはリポジトリ外ファイルのみのためコミットなし。次タスクへ。

---

### Task 7: ラベル作成・プッシュ・結合検証（オペレーション）

**Files:** なし（gh CLI とプッシュ操作）

- [ ] **Step 1: ラベル作成（冪等）**

```bash
cd /c/Users/oui_k/OneDrive/finlab-se
gh label create automation-error --color D93F0B \
  --description "時間実行の自動処理のエラー（Claude起動時に検知・対応）" 2>&1 || echo "label exists"
```

- [ ] **Step 2: プッシュ**

```bash
git push
```

- [ ] **Step 3: 結合検証（Issue作成から検知・Closeまでの一巡）**

```bash
# (a) テストIssueをスクリプト経由で作成（ソフトエラーを擬似再現）
cd /c/Users/oui_k/OneDrive/finlab-se
printf 'collect_news: yahoo=15 google=69 trends=0\n' > /tmp/fake_stderr.log
GH_TOKEN=$(gh auth token) python .github/scripts/report_automation_error.py \
  --workflow x-post-scheduled --slot morning --job-status success \
  --run-url "https://example.com/test-run" --stderr-file /tmp/fake_stderr.log
# Expected: "created issue: [automation-error] x-post-scheduled/morning: ニュースソース0件 (trends)"

# (b) 同じコマンドを再実行 → 重複防止でスキップされること
# Expected: "skip (open issue exists): ..."

# (c) フックが検知すること
node "C:/Users/oui_k/.claude/scripts/check-automation-errors.mjs"
# Expected: 【自動アラート】... #N ... の出力

# (d) テストIssueをClose → フックが無出力に戻ること
gh issue close $(gh issue list --label automation-error --state open --json number --jq '.[0].number') \
  --comment "結合検証用のテストIssue。仕組みの動作確認完了につきClose"
node "C:/Users/oui_k/.claude/scripts/check-automation-errors.mjs"
# Expected: 無出力
```

- [ ] **Step 4: 実運用の初回確認（翌朝）**

翌朝7:30の実行後に `gh run view <run_id> --log | grep "collect_news:"` で `trends=` が10前後であること、`Report automation errors` ステップが "no errors detected" であることを確認する。

---

## Self-Review

**1. Spec coverage**

| spec項目 | タスク |
|---|---|
| Trends RSS 追加・graceful degradation（§3.1） | Task 2 |
| プロンプトの trends ルール（§3.2） | Task 3 |
| ログ行3ソース化（§3.3） | Task 3 |
| ハード/ソフトエラー定義と検知（§4.1） | Task 4・5 |
| 件数行なし＝ソフトエラー（§4.1） | Task 4（`find_soft_error`） |
| Issue形式・ラベル・重複防止（§4.2） | Task 4・7（ラベル） |
| ワークフロー配線（§4.3） | Task 5 |
| 起動時フック（§4.4） | Task 6 |
| 対応フロー運用（§4.5） | Task 6（フック出力の指示文）・7(c)(d) |
| `__pycache__` 掃除（§5） | Task 1 |
| テスト方針（§6） | 各タスクのTDD＋Task 7 結合検証 |

ギャップなし。

**2. Placeholder scan**: 全ステップに実コード・実コマンド・期待結果あり。

**3. Type consistency**: `find_soft_error(str)->str|None`・`build_title(w,s,summary)->str`・`report(title,body,run)->str` は Task 4 定義と Task 5 のCLI呼び出し・Task 7 の検証コマンドで一貫。ログ行 `collect_news: yahoo=N google=N trends=N` は Task 3 の出力と Task 4 の `_COUNTS_RE`・Task 7 の擬似stderrで一致。
