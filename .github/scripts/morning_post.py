"""
朝7:05のX投稿（既存記事のおすすめ専用・新着は扱わない）

処理:
  1. data/x-topic-pick.yaml に「当日朝向け」の有効な話題連動pickがあれば、それを投稿
     - pick.target_date が今日（JST）と一致し、post_path のファイルが存在することが条件
     - 投稿成功後: pick をクリア、該当記事の rotation last_promoted を更新（直近3日除外に乗せる）、
       履歴に type=topic で追記、x-post-state の morning_last_posted を更新
  2. 有効な pick がなければ rotation_post.py を実行（通常のおすすめ・直近3日除外込み）
  3. 当日すでに朝投稿済み（morning_last_posted == today）なら何もしない（多重起動防止）

新着記事は朝では投稿しない（夜21:05の night スロットが担当する）。

使い方:
    python morning_post.py

環境変数:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
"""
import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    from ruamel.yaml import YAML
except ImportError:
    print(json.dumps({"status": "error", "error": "ruamel.yaml not installed"}))
    sys.exit(1)

JST = timezone(timedelta(hours=9))
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
PICK_PATH = REPO_ROOT / "data" / "x-topic-pick.yaml"
STATE_PATH = REPO_ROOT / "data" / "x-post-state.yaml"
ROTATION_PATH = REPO_ROOT / "data" / "x-rotation.yaml"


def _yaml():
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=2, offset=0)
    return y


def today_jst() -> str:
    return datetime.now(JST).date().isoformat()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    with STATE_PATH.open(encoding="utf-8") as f:
        return _yaml().load(f) or {}


def save_state(state: dict) -> None:
    with STATE_PATH.open("w", encoding="utf-8") as f:
        _yaml().dump(state, f)


def clear_pick() -> None:
    """x-topic-pick.yaml の pick を null に戻す（コメントは保持）。"""
    y = _yaml()
    if PICK_PATH.exists():
        with PICK_PATH.open(encoding="utf-8") as f:
            doc = y.load(f) or {}
    else:
        doc = {}
    doc["pick"] = None
    with PICK_PATH.open("w", encoding="utf-8") as f:
        y.dump(doc, f)


def call_post_to_x(text: str, image_path: str) -> dict:
    payload = {"text": text, "image_path": image_path or "", "image_url": ""}
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
    json.dump(payload, tmp, ensure_ascii=False)
    tmp.close()
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "post_to_x.py"), tmp.name],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {"ok": False, "error": f"non-json: {result.stdout} / {result.stderr}"}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def append_history(text, tweet_id, tweet_url, post_path, post_type):
    payload = json.dumps({
        "text": text, "tweet_id": tweet_id, "tweet_url": tweet_url,
        "type": post_type, "post_path": post_path,
    }, ensure_ascii=False)
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "append_post_history.py")],
        input=payload, text=True, encoding="utf-8", capture_output=True, check=False,
    )


def mark_rotation_dedup(post_path: str) -> None:
    """rotation.yaml の該当記事の last_promoted を更新（直近3日除外に乗せる）。
    未登録なら upsert で新規追記する（全記事の自動同期台帳化に伴い・2026-06-18）。"""
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "update_rotation.py"), "--post-path", post_path],
        check=False,
    )


def get_valid_pick():
    """当日朝向けの有効な pick を返す。無効・古い場合は None（古ければクリア）。"""
    if not PICK_PATH.exists():
        return None
    with PICK_PATH.open(encoding="utf-8") as f:
        doc = _yaml().load(f) or {}
    pick = doc.get("pick")
    if not pick:
        return None
    # 当日朝向けでなければ無効（古い pick が残っていたらクリアする）
    if str(pick.get("target_date", "")) != today_jst():
        clear_pick()
        return None
    post_path = pick.get("post_path", "")
    if not post_path or not (REPO_ROOT / post_path).exists():
        clear_pick()
        return None
    return pick


def post_topic(pick) -> dict:
    text = pick["text"]
    image_path = pick.get("image_path", "") or ""
    result = call_post_to_x(text, image_path)
    if not result.get("ok"):
        return {"status": "failed", "type": "topic", "post_path": pick["post_path"],
                "error": result.get("error", "unknown")}
    tweet_id = result.get("tweet_id", "")
    tweet_url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else ""
    append_history(text, tweet_id, tweet_url, pick["post_path"], "topic")
    mark_rotation_dedup(pick["post_path"])
    clear_pick()
    state = load_state()
    state["morning_last_posted"] = today_jst()
    save_state(state)
    return {"status": "posted", "type": "topic", "post_path": pick["post_path"], "tweet_url": tweet_url}


def post_rotation() -> dict:
    """通常おすすめ（rotation_post.py）を実行し、成功時に morning_last_posted を更新。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "rotation_post.py")],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    out = result.stdout.strip()
    try:
        data = json.loads(out.splitlines()[-1]) if out else {"status": "error"}
    except (json.JSONDecodeError, IndexError):
        data = {"status": "error", "error": f"non-json: {out} / {result.stderr}"}
    if data.get("status") == "posted":
        state = load_state()
        state["morning_last_posted"] = today_jst()
        save_state(state)
    return data


def main():
    # 多重起動防止：当日すでに朝投稿済みなら何もしない
    if load_state().get("morning_last_posted") == today_jst():
        print(json.dumps({"status": "skipped", "reason": "already posted this morning"}, ensure_ascii=False))
        return

    pick = get_valid_pick()
    if pick:
        result = post_topic(pick)
        # 話題連動の投稿に失敗したら通常おすすめにフォールバック
        if result.get("status") != "posted":
            sys.stderr.write(f"topic post failed, fallback to rotation: {result.get('error')}\n")
            result = post_rotation()
    else:
        result = post_rotation()

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
