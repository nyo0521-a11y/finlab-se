"""
ローテーション（既存記事リマインダー）の即時投稿スクリプト

処理:
  1. select_rotation.py 相当のロジックで対象記事を選定
  2. generate_post_text.py 相当で投稿文生成（mode=rotation）
  3. post_to_x.py で X API に投稿
  4. data/x-rotation.yaml の last_promoted / promote_count を更新

使い方:
    python rotation_post.py

環境変数:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
"""
import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(script: str, *args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"{script} failed: {result.stderr}")
    return json.loads(result.stdout.strip())


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
            return {"ok": False, "error": f"non-json: {stdout} / stderr: {result.stderr}"}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def main():
    # 1. 対象選定
    picked = run_script("select_rotation.py")
    post_path = picked["post_path"]
    index = picked["index"]

    # 2. 投稿文生成
    meta = run_script("generate_post_text.py", post_path, "rotation")
    text = meta["text"]
    image_path = meta.get("image_path", "") or ""
    # GitHub Actions 内はリポジトリがチェックアウト済みなので image_path を直接使う。
    # image_url 経由のダウンロードは CF Pages の Bot 制限で 403 になるため使わない。
    image_url = ""

    # 3. 投稿
    result = call_post_to_x(text, image_path, image_url)
    if not result.get("ok"):
        print(json.dumps({
            "status": "failed",
            "post_path": post_path,
            "error": result.get("error", "unknown"),
        }, ensure_ascii=False))
        sys.exit(1)

    tweet_id = result.get("tweet_id", "")
    tweet_url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else ""

    # 4. rotation.yaml 更新
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "update_rotation.py"), str(index)],
        check=True,
    )

    print(json.dumps({
        "status": "posted",
        "post_path": post_path,
        "index": index,
        "tweet_url": tweet_url,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
