import json
import types
import morning_post


def test_inline_returns_pick_on_selection(monkeypatch, tmp_path):
    # 記事ファイルを用意
    posts = tmp_path / "content/posts"
    posts.mkdir(parents=True)
    (posts / "loan.md").write_text(
        '---\ntitle: "T"\ndescription: "D"\ntags: ["x"]\n'
        'cover:\n  image: "/images/loan.png"\n---\n本文\n', encoding="utf-8")
    monkeypatch.setattr(morning_post, "REPO_ROOT", tmp_path)

    # collect_news / select_topic の subprocess をスタブ
    # select_topic.py に渡された input= を captured に保存してアサートする
    captured = {}
    news_json = json.dumps({"yahoo": [], "google": []})

    def fake_run(cmd, **kwargs):
        out = ""
        if "collect_news.py" in cmd[1]:
            out = news_json
        elif "select_topic.py" in cmd[1]:
            captured["select_stdin"] = kwargs.get("input")
            out = json.dumps({"selected_post_path": "content/posts/loan.md",
                              "text": "本文 https://finlab-se.com/posts/loan/",
                              "topic_reason": "r", "candidates": []})
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(morning_post.subprocess, "run", fake_run)
    pick = morning_post.select_topic_inline()
    assert pick["post_path"] == "content/posts/loan.md"
    assert pick["image_path"] == "/images/loan.png"
    # ニュースJSONが select_topic.py の stdin に渡されていることを確認
    assert captured.get("select_stdin") == news_json


def test_inline_returns_none_when_no_match(monkeypatch, tmp_path):
    monkeypatch.setattr(morning_post, "REPO_ROOT", tmp_path)

    def fake_run(cmd, **kwargs):
        out = json.dumps({"yahoo": [], "google": []}) if "collect_news.py" in cmd[1] \
            else json.dumps({"selected_post_path": None, "reason": "none", "candidates": []})
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(morning_post.subprocess, "run", fake_run)
    assert morning_post.select_topic_inline() is None


def test_inline_returns_none_on_subprocess_spawn_error(monkeypatch, tmp_path):
    """subprocess.run がOSErrorを送出しても select_topic_inline は None を返す（例外を伝播させない）。"""
    monkeypatch.setattr(morning_post, "REPO_ROOT", tmp_path)

    def raise_oserror(cmd, **kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(morning_post.subprocess, "run", raise_oserror)
    assert morning_post.select_topic_inline() is None
