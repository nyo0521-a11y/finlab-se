"""data/x-topic-pick.yaml を決定論的に書き換える。

スケジュールタスク（前夜22:00 / 当日6:30）が手書きで YAML を編集すると、
コメント例の消し損ね・二重 pick 追記などで YAML が壊れ、朝の morning_post.py が
クラッシュして朝枠が丸ごと無投稿になる事故が起きた（2026-06-20）。
そのため pick の書き込みは必ずこのスクリプト経由にし、
「正規ヘッダー＋ pick を1つだけ」の形でファイル全体を再生成する。

使い方:
  # pick を設定（投稿文 text は stdin から渡す）
  printf '%s' "<投稿文>" | python .github/scripts/set_topic_pick.py \
      --post-path content/posts/foo.md \
      --image-path /images/thumb-foo.jpg \
      --target-date 2026-06-20 \
      --topic "選定根拠にした話題の要約" \
      --prepared-at "2026-06-20T06:38:00+09:00"

  # pick をクリア（pick: null にする）
  python .github/scripts/set_topic_pick.py --clear
"""
import argparse
import json
import sys
from pathlib import Path

PICK_PATH = Path(__file__).resolve().parents[1].parent / "data" / "x-topic-pick.yaml"

HEADER = """\
# X 朝投稿「話題連動おすすめ」の準備置き場
#
# 仕組み（2026-06-14 設計）:
#   - 前夜22:00 / 当日朝6:30 のスケジュールタスク（Claude Code 起動中のみ動作）が
#     経済・金融ニュースを収集→関連記事を1本選定→投稿文を生成し、ここに書き込む。
#   - 6:30 が動いた場合は前夜22:00 の内容を上書きする（最新の判断を優先）。
#   - 朝7:05 の morning_post.py が pick を最優先で投稿し、投稿後に pick を null へ戻す。
#   - pick が null（＝準備されなかった）の朝は、通常の rotation（おすすめ）が投稿される。
#
# target_date は「この pick が投稿されるべき朝（JST）の日付」。
#   morning_post.py は target_date が当日でない pick を無視してクリアする（古い pick の誤投稿防止）。
#
# ⚠️ このファイルは手書きで編集せず、必ず .github/scripts/set_topic_pick.py 経由で書き換える。
#   手書き編集はコメント消し損ね・二重 pick で YAML を壊し、朝枠を無投稿にする事故の原因になる。
#
# 記入例:
# pick:
#   post_path: content/posts/foo.md
#   text: |-
#     【○○が話題】〜というニュースが注目されています。参考になるのがこの記事です。
#     https://finlab-se.com/posts/foo/
#     #ハッシュタグ
#   image_path: /images/thumb-foo.jpg
#   target_date: "2026-06-20"
#   topic: "選定根拠にした話題の要約"
#   prepared_at: "2026-06-20T06:38:00+09:00"
"""


def render(pick: dict | None) -> str:
    """正規形（ヘッダー＋ pick を1つだけ）の YAML 文字列を組み立てる。"""
    out = HEADER + "\n"
    if not pick:
        return out + "pick: null\n"
    # text は任意の文字列を安全に表現するためリテラルブロック |- を使う。
    # 他のスカラーは json.dumps でクォート＆エスケープ（JSON文字列は有効な YAML フロースカラー）。
    text = pick.get("text", "") or ""
    text_lines = text.split("\n")
    indented = "\n".join(("    " + ln) if ln else "" for ln in text_lines)
    out += "pick:\n"
    out += f"  post_path: {json.dumps(pick['post_path'], ensure_ascii=False)}\n"
    out += "  text: |-\n"
    out += indented + "\n"
    out += f"  image_path: {json.dumps(pick.get('image_path', '') or '', ensure_ascii=False)}\n"
    out += f"  target_date: {json.dumps(pick['target_date'], ensure_ascii=False)}\n"
    out += f"  topic: {json.dumps(pick.get('topic', '') or '', ensure_ascii=False)}\n"
    out += f"  prepared_at: {json.dumps(pick['prepared_at'], ensure_ascii=False)}\n"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear", action="store_true", help="pick を null にする")
    ap.add_argument("--post-path")
    ap.add_argument("--image-path", default="")
    ap.add_argument("--target-date")
    ap.add_argument("--topic", default="")
    ap.add_argument("--prepared-at")
    args = ap.parse_args()

    if args.clear:
        content = render(None)
    else:
        missing = [n for n in ("post_path", "target_date", "prepared_at")
                   if not getattr(args, n)]
        if missing:
            sys.stderr.write(f"missing required args: {', '.join('--' + m.replace('_', '-') for m in missing)}\n")
            return 2
        # stdin は環境ロケールに依存せず必ず UTF-8 として読む
        # （Windows のスケジュールタスクで cp932 誤デコードによる文字化けを防ぐ）。
        text = sys.stdin.buffer.read().decode("utf-8")
        if not text.strip():
            sys.stderr.write("投稿文（text）が stdin から渡されていません\n")
            return 2
        content = render({
            "post_path": args.post_path,
            "text": text.rstrip("\n"),
            "image_path": args.image_path,
            "target_date": args.target_date,
            "topic": args.topic,
            "prepared_at": args.prepared_at,
        })

    # 自己検証：生成した内容が必ず有効な YAML としてパースできることを確認してから書き出す。
    # パーサは morning_post.py と同じ ruamel を優先し、無ければ PyYAML、どちらも無ければ
    # 構造を決定論的に生成しているためスキップする（リテラルブロック |- は任意の本文を許容する）。
    parsed = None
    try:
        import io
        from ruamel.yaml import YAML
        parsed = YAML(typ="safe").load(io.StringIO(content))
    except ImportError:
        try:
            import yaml  # PyYAML
            parsed = yaml.safe_load(content)
        except ImportError:
            parsed = {"pick": True}  # パーサ未導入の環境では検証スキップ
    except Exception as e:  # noqa: BLE001 - パース失敗（=不正YAML）は書き込み中止
        sys.stderr.write(f"生成内容が不正な YAML です。書き込み中止: {e}\n")
        return 1
    if not (isinstance(parsed, dict) and "pick" in parsed):
        sys.stderr.write("生成内容に pick キーがありません。書き込み中止\n")
        return 1

    PICK_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {PICK_PATH} (pick={'null' if args.clear else args.post_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
