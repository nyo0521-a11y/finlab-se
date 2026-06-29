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
    def fake_run(cmd, **kwargs):
        out = ""
        if "collect_news.py" in cmd[1]:
            out = json.dumps({"yahoo": [], "google": []})
        elif "select_topic.py" in cmd[1]:
            out = json.dumps({"selected_post_path": "content/posts/loan.md",
                              "text": "本文 https://finlab-se.com/posts/loan/",
                              "topic_reason": "r", "candidates": []})
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(morning_post.subprocess, "run", fake_run)
    pick = morning_post.select_topic_inline()
    assert pick["post_path"] == "content/posts/loan.md"
    assert pick["image_path"] == "/images/loan.png"


def test_inline_returns_none_when_no_match(monkeypatch, tmp_path):
    monkeypatch.setattr(morning_post, "REPO_ROOT", tmp_path)

    def fake_run(cmd, **kwargs):
        out = json.dumps({"yahoo": [], "google": []}) if "collect_news.py" in cmd[1] \
            else json.dumps({"selected_post_path": None, "reason": "none", "candidates": []})
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)

    monkeypatch.setattr(morning_post.subprocess, "run", fake_run)
    assert morning_post.select_topic_inline() is None
