"""
data/x-queue.yaml の先頭エントリを拾って X に投稿するスクリプト。

処理の流れ:
  1. data/x-queue.yaml を読む
  2. queue が空なら skip（exit 0, 出力 {"status":"empty"}）
  3. slot == "night" かつ len(queue) < 2 なら skip（rotation に譲る）
  4. 先頭エントリの issue_number を取得
     - issue_number が null なら skip（x-queue-init 未実行、出力 {"status":"no_issue"}）
     - Issue が open でない → skip
     - check_approval.py が approved=False → skip
  5. Issue 本文から投稿文と image_path を抽出
  6. post_to_x.py を呼んで投稿
  7. 成功時:
     - Issue にコメント＋label 付け替え＋close
     - queue から先頭エントリを削除
     - （呼び出し側で commit & push）
     - 出力: {"status":"posted", "tweet_url": "...", "issue_number": N, "post_path": "..."}
  8. 失敗時: Issue に error コメント、label x-post-failed 追加

使い方:
    python dequeue_and_post.py <slot>   # slot = "morning" | "night" | "manual"

環境変数:
    GITHUB_TOKEN, GITHUB_REPOSITORY, X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
"""
import os
import sys
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ruamel.yaml import YAML

QUEUE_PATH = Path("data/x-queue.yaml")
SCRIPT_DIR = Path(__file__).resolve().parent


def gh_api(path: str) -> dict | list:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_queue() -> tuple[dict, list]:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    with QUEUE_PATH.open(encoding="utf-8") as f:
        data = yaml.load(f) or {}
    queue = data.get("queue") or []
    return data, queue


def save_queue(data: dict) -> None:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    with QUEUE_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)


def extract_text_and_meta(body: str) -> tuple[str, dict]:
    """Issue 本文から最初の ```...``` と x-post-meta JSON を抽出。"""
    text_match = re.search(r"```\n(.*?)\n```", body, re.DOTALL)
    text = text_match.group(1) if text_match else ""
    meta_match = re.search(r"x-post-meta:\s*(\{.*?\})", body)
    meta = json.loads(meta_match.group(1)) if meta_match else {}
    return text, meta


def run_gh_cli(args: list[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"gh cli failed: {' '.join(args)}")
    return result.stdout.strip()


def check_approval(issue_number: int) -> bool:
    """check_approval.py を呼び出して approved を返す。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_approval.py"), str(issue_number)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return False
    payload = json.loads(result.stdout)
    return bool(payload.get("approved"))


def call_post_to_x(text: str, image_path: str, image_url: str) -> dict:
    payload = {"text": text, "image_path": image_path, "image_url": image_url}
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
    json.dump(payload, tmp, ensure_ascii=False)
    tmp.close()
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "post_to_x.py"), tmp.name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        stdout = result.stdout.strip()
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"non-json output: {stdout} / stderr: {result.stderr}"}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def main():
    if len(sys.argv) < 2:
        print("usage: dequeue_and_post.py <slot>", file=sys.stderr)
        sys.exit(2)
    slot = sys.argv[1]

    if not QUEUE_PATH.exists():
        print(json.dumps({"status": "empty", "reason": "queue file missing"}))
        return

    data, queue = load_queue()
    if not queue:
        print(json.dumps({"status": "empty", "reason": "queue is empty"}))
        return

    # 夜枠は残2件未満ならrotationに譲る
    if slot == "night" and len(queue) < 2:
        print(json.dumps({"status": "skip_night", "reason": f"queue size {len(queue)} < 2"}))
        return

    head = queue[0]
    post_path = head.get("post_path")
    issue_number = head.get("issue_number")

    if issue_number is None:
        print(json.dumps({"status": "no_issue", "reason": "head entry has no issue_number", "post_path": post_path}))
        return

    issue_number = int(issue_number)

    # Issue 状態チェック
    try:
        issue = gh_api(f"/issues/{issue_number}")
    except Exception as e:
        print(json.dumps({"status": "error", "reason": f"failed to fetch issue: {e}"}))
        sys.exit(1)

    if issue.get("state") != "open":
        # closed されているならキューから除外してスキップ（次回に先送り）
        queue.pop(0)
        data["queue"] = queue
        save_queue(data)
        print(json.dumps({"status": "skip_closed", "issue_number": issue_number, "post_path": post_path}))
        return

    if not check_approval(issue_number):
        print(json.dumps({"status": "not_approved", "issue_number": issue_number, "post_path": post_path}))
        return

    body = issue.get("body") or ""
    text, meta = extract_text_and_meta(body)
    if not text:
        print(json.dumps({"status": "error", "reason": "post text not found in issue body", "issue_number": issue_number}))
        sys.exit(1)

    image_path = meta.get("image_path", "") or ""
    image_url = meta.get("image_url", "") or ""

    # 投稿実行
    result = call_post_to_x(text, image_path, image_url)
    if not result.get("ok"):
        err = result.get("error", "unknown")
        run_gh_cli(["issue", "comment", str(issue_number), "--body", f"投稿失敗: `{err}`"])
        run_gh_cli(["issue", "edit", str(issue_number), "--add-label", "x-post-failed"])
        print(json.dumps({"status": "failed", "issue_number": issue_number, "error": err}))
        sys.exit(1)

    tweet_id = result.get("tweet_id", "")
    tweet_url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else ""

    run_gh_cli(["issue", "comment", str(issue_number), "--body", f"投稿しました: {tweet_url}"])
    run_gh_cli(["issue", "edit", str(issue_number), "--remove-label", "x-post-pending", "--add-label", "x-post-posted"])
    run_gh_cli(["issue", "close", str(issue_number)])

    # queue から削除
    queue.pop(0)
    data["queue"] = queue
    save_queue(data)

    print(json.dumps({
        "status": "posted",
        "issue_number": issue_number,
        "post_path": post_path,
        "tweet_url": tweet_url,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
