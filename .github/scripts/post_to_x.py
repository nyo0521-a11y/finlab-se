"""
X (Twitter) API 投稿スクリプト（OAuth 1.0a User Context + 画像添付）

前提:
- X API Free tier（月500 post write）
- 認証4値は環境変数 X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET
- 画像アップロードは v1.1 media/upload、投稿は v2 /2/tweets

使い方:
    python post_to_x.py <text_json_file>
      text_json_file は generate_post_text.py の出力をそのまま渡せる想定
      必須キー: text
      画像指定（任意）: image_url （http/https のURL）または image_path（リポジトリ内ローカルパス）
      両方ある場合は image_url を優先。どちらも空なら画像なしで投稿。

    出力: JSON { "ok": true/false, "tweet_id": "...", "error": "..." }

注意:
- OAuth 1.0a 署名は requests_oauthlib に任せる（tweepyより依存が軽い）
- GitHub Actions 側で pip install requests requests-oauthlib が必要
"""
import os
import sys
import json
import urllib.request
import tempfile

try:
    import requests
    from requests_oauthlib import OAuth1
except ImportError:
    print(json.dumps({"ok": False, "error": "requests / requests-oauthlib not installed"}))
    sys.exit(1)

UPLOAD_URL = "https://api.x.com/2/media/upload"
TWEET_URL = "https://api.x.com/2/tweets"


def get_oauth() -> OAuth1:
    return OAuth1(
        os.environ["X_API_KEY"],
        client_secret=os.environ["X_API_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        signature_type="AUTH_HEADER",
    )


def download_image(url: str) -> str:
    """画像をダウンロードして一時ファイルパスを返す。"""
    suffix = os.path.splitext(url.split("?")[0])[1] or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with urllib.request.urlopen(url) as resp:
        tmp.write(resp.read())
    tmp.close()
    return tmp.name


def resolve_image_source(image_ref: str) -> tuple[str, bool]:
    """画像の指定を解決。

    引数:
      image_ref: URL（http/https）またはリポジトリ内のローカルパス。

    返り値:
      (実ファイルパス, is_tmp)
      is_tmp が True の場合、呼び出し側で削除する。
    """
    if image_ref.startswith(("http://", "https://")):
        return download_image(image_ref), True
    # ローカルパス扱い。先頭 "/" は相対化する（リポジトリルート起点）。
    local = image_ref.lstrip("/")
    if not os.path.exists(local):
        raise FileNotFoundError(f"local image not found: {local}")
    return local, False


def upload_media(image_path: str, oauth: OAuth1) -> str:
    """v2 /2/media/upload（simple upload）。返り値 media_id（string）。"""
    with open(image_path, "rb") as f:
        files = {"media": f}
        data = {"media_category": "tweet_image"}
        r = requests.post(UPLOAD_URL, files=files, data=data, auth=oauth, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"media upload failed: {r.status_code} {r.text}")
    body = r.json()
    # v2 レスポンス: {"data": {"id": "..."}}  / 旧互換: {"media_id_string": "..."} も一応
    if "data" in body and "id" in body["data"]:
        return body["data"]["id"]
    if "id" in body:
        return body["id"]
    if "media_id_string" in body:
        return body["media_id_string"]
    raise RuntimeError(f"unexpected media upload response: {body}")


def post_tweet(text: str, media_id: str | None, oauth: OAuth1) -> dict:
    """v2 /2/tweets で投稿。"""
    payload: dict = {"text": text}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    r = requests.post(
        TWEET_URL,
        json=payload,
        auth=oauth,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"tweet failed: {r.status_code} {r.text}")
    return r.json()


def main():
    if len(sys.argv) < 2:
        print("usage: post_to_x.py <text_json_file>", file=sys.stderr)
        sys.exit(2)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    text = data["text"]
    image_url = data.get("image_url", "")
    image_path = data.get("image_path", "")
    # 優先順位: image_url (http/https) > image_path (ローカル) > なし
    image_ref = image_url if image_url else image_path

    try:
        oauth = get_oauth()
        media_id = None
        if image_ref:
            img_path, is_tmp = resolve_image_source(image_ref)
            media_id = upload_media(img_path, oauth)
            if is_tmp:
                try:
                    os.unlink(img_path)
                except OSError:
                    pass
        result = post_tweet(text, media_id, oauth)
        tweet_id = result.get("data", {}).get("id", "")
        print(json.dumps({"ok": True, "tweet_id": tweet_id}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
