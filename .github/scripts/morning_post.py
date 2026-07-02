"""
朝7:05のX投稿（既存記事のおすすめ専用・新着は扱わない）

処理:
  1. collect_news.py + select_topic.py を実行して話題連動pick をその場で選定
     - 選定成功（ファイルが存在する記事が返る）なら post_topic() で投稿
     - 選定失敗・None の場合は rotation_post.py にフォールバック
  2. 当日すでに朝投稿済み（morning_last_posted == today）なら何もしない（多重起動防止）

新着記事は朝では投稿しない（夜21:05の night スロットが担当する）。

使い方:
    python morning_post.py

環境変数:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
"""
import os
import re
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
    md = (REPO_ROOT / post_path).read_text(encoding="utf-8")
    m = re.search(r'cover:\s*\n\s*image:\s*"(.*?)"', md)
    return m.group(1) if m else ""


def select_topic_inline():
    """ニュース取得->Claude選定をその場で行う。成功時 pick dict、なければ None。
    いかなる例外が発生しても None を返して rotation にフォールバックさせる。"""
    try:
        news = _run_capture("collect_news.py")
        if not news:
            sys.stderr.write("collect_news returned empty output; fallback to rotation\n")
            return None
        try:
            _nd = json.loads(news)
            sys.stderr.write(
                f"collect_news: yahoo={len(_nd.get('yahoo', []))} "
                f"google={len(_nd.get('google', []))} "
                f"trends={len(_nd.get('trends', []))}\n"
            )
        except (json.JSONDecodeError, AttributeError):
            sys.stderr.write("collect_news output not JSON (continuing)\n")
        result_raw = _run_capture("select_topic.py", stdin_text=news)
        if not result_raw:
            sys.stderr.write("select_topic returned empty output; fallback to rotation\n")
            return None
        try:
            result = json.loads(result_raw)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"select_topic.py output not JSON: {e}\n")
            return None
        post_path = result.get("selected_post_path")
        sys.stderr.write(
            f"select_topic: selected={post_path} "
            f"reason={result.get('topic_reason') or result.get('reason') or ''}\n"
        )
        if not post_path or not (REPO_ROOT / post_path).exists():
            return None
        return {
            "post_path": post_path,
            "text": result.get("text", ""),
            "image_path": _read_cover_image(post_path),
        }
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"select_topic_inline failed, fallback to rotation: {e}\n")
        return None


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

    pick = select_topic_inline()
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
