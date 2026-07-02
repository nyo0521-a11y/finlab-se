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
