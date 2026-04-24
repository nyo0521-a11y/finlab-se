"""
Issue承認状態チェック

承認条件（いずれか）:
  - リポジトリ owner が ✅ (white_check_mark / heavy_check_mark) リアクションを付けた
  - リポジトリ owner が "/approve" で始まるコメントを付けた

使い方:
    python check_approval.py <issue_number>
    出力: JSON { "approved": true/false, "reason": "..." }

環境変数:
    GITHUB_TOKEN : GitHub API トークン
    GITHUB_REPOSITORY : "owner/repo"
"""
import os
import sys
import json
import urllib.request
import urllib.error

APPROVE_REACTIONS = {"+1", "hooray", "heart", "rocket"}  # 👍❤️🎉🚀
APPROVE_EMOJI_CHECK = {"+1"}  # ✅はGitHub APIで "+1" とは別。後述


def gh_request(path: str) -> dict | list:
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


def get_owner_login() -> str:
    repo = os.environ["GITHUB_REPOSITORY"]
    return repo.split("/")[0]


def check(issue_number: int) -> dict:
    owner = get_owner_login()

    # リアクション確認
    # ✅はGitHub REST APIの reactions content としては存在せず、対応する content は "+1" (👍) のみ。
    # そのため「承認 = 👍 / ❤️ / 🎉 / 🚀 のいずれかを owner が付ける」か、"/approve" コメントで判定する。
    reactions = gh_request(f"/issues/{issue_number}/reactions")
    for r in reactions:
        if r.get("user", {}).get("login") == owner and r.get("content") in APPROVE_REACTIONS:
            return {"approved": True, "reason": f"owner reaction: {r['content']}"}

    # コメント確認
    comments = gh_request(f"/issues/{issue_number}/comments")
    for c in comments:
        if c.get("user", {}).get("login") != owner:
            continue
        body = (c.get("body") or "").strip()
        if body.startswith("/approve"):
            return {"approved": True, "reason": "owner /approve comment"}

    return {"approved": False, "reason": "no approval from owner"}


def main():
    if len(sys.argv) < 2:
        print("usage: check_approval.py <issue_number>", file=sys.stderr)
        sys.exit(2)
    issue_number = int(sys.argv[1])
    result = check(issue_number)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
