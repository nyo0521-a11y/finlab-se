"""
data/x-queue.yaml の先頭エントリを拾って X に投稿するスクリプト（承認フロー廃止版）。

処理の流れ:
  1. data/x-queue.yaml を読む
  2. queue が空なら skip（{"status":"empty"}）
  3. slot の条件判定:
     - morning : queue>=1 なら投稿
     - night   : 月水金(1,3,5)は queue>=2 のときのみ（rotationに譲る）
                 それ以外は queue>=1 で投稿
     - manual  : 常に投稿（queue>=1）
  4. 先頭 post_path から投稿文を生成（generate_post_text.py）
  5. post_to_x.py で投稿
  6. queue から先頭を除去 → 呼び出し側で commit & push
  7. 出力: {"status":"posted", "tweet_url": "...", "post_path": "..."}

使い方:
    python dequeue_and_post.py <slot>   # slot = "morning" | "night" | "manual"

環境変数:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
"""
import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ruamel.yaml import YAML

QUEUE_PATH = Path("data/x-queue.yaml")
SCRIPT_DIR = Path(__file__).resolve().parent
JST = timezone(timedelta(hours=9))


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
            return {"ok": False, "error": f"non-json output: {stdout} / stderr: {result.stderr}"}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def should_post_in_slot(slot: str, queue_size: int) -> tuple[bool, str]:
    """slot と queue size・曜日から投稿するか判定。"""
    if queue_size <= 0:
        return False, "queue is empty"

    if slot == "morning":
        return True, "morning slot always posts when queue>=1"

    if slot == "manual":
        return True, "manual dispatch"

    if slot == "night":
        weekday = datetime.now(JST).isoweekday()  # 1=月, 7=日
        is_mwf = weekday in (1, 3, 5)
        if is_mwf:
            if queue_size >= 2:
                return True, f"night MWF with queue={queue_size}>=2"
            return False, f"night MWF with queue={queue_size}<2, yield to rotation"
        # 火木土日
        return True, f"night non-MWF with queue={queue_size}>=1"

    return False, f"unknown slot: {slot}"


def main():
    if len(sys.argv) < 2:
        print("usage: dequeue_and_post.py <slot>", file=sys.stderr)
        sys.exit(2)
    slot = sys.argv[1]

    if not QUEUE_PATH.exists():
        print(json.dumps({"status": "empty", "reason": "queue file missing"}))
        return

    data, queue = load_queue()
    queue_size = len(queue)

    ok, reason = should_post_in_slot(slot, queue_size)
    if not ok:
        status = "empty" if queue_size == 0 else "skip"
        print(json.dumps({"status": status, "reason": reason, "queue_size": queue_size}))
        return

    head = queue[0]
    post_path = head.get("post_path")
    if not post_path:
        print(json.dumps({"status": "error", "reason": "head has no post_path"}))
        sys.exit(1)

    # 投稿文生成
    try:
        meta = run_script("generate_post_text.py", post_path, "new")
    except Exception as e:
        print(json.dumps({"status": "error", "reason": f"generate_post_text failed: {e}"}))
        sys.exit(1)

    text = meta["text"]
    image_path = meta.get("image_path", "") or ""
    image_url = meta.get("image_url", "") or ""

    # 投稿実行
    result = call_post_to_x(text, image_path, image_url)
    if not result.get("ok"):
        err = result.get("error", "unknown")
        print(json.dumps({"status": "failed", "post_path": post_path, "error": err}))
        sys.exit(1)

    tweet_id = result.get("tweet_id", "")
    tweet_url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else ""

    # queue から削除
    queue.pop(0)
    data["queue"] = queue
    save_queue(data)

    print(json.dumps({
        "status": "posted",
        "post_path": post_path,
        "tweet_url": tweet_url,
        "slot": slot,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
