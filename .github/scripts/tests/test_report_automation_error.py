import json
from report_automation_error import find_soft_error, report, build_title


def test_find_soft_error_none_when_healthy():
    err = "collect_news: yahoo=15 google=69 trends=10\nselect_topic: selected=None reason=x\n"
    assert find_soft_error(err) is None


def test_find_soft_error_detects_zero_sources():
    err = "collect_news: yahoo=15 google=0 trends=0\n"
    got = find_soft_error(err)
    assert "google" in got and "trends" in got and "0件" in got


def test_find_soft_error_detects_missing_line():
    err = "collect_news returned empty output; fallback to rotation\n"
    got = find_soft_error(err)
    assert "collect_news行なし" in got


def test_build_title():
    assert build_title("x-post-scheduled", "morning", "ニュースソース0件 (trends)") == \
        "[automation-error] x-post-scheduled/morning: ニュースソース0件 (trends)"


def test_report_skips_when_same_open_title_exists():
    calls = []
    def fake_run(args):
        calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"title": "[automation-error] w/s: x"}])
        raise AssertionError("create should not be called")
    assert report("[automation-error] w/s: x", "body", run=fake_run) == "skipped"


def test_report_creates_when_new():
    calls = []
    def fake_run(args):
        calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([])
        return "https://github.com/o/r/issues/99"
    assert report("[automation-error] w/s: new", "body", run=fake_run) == "created"
    assert any(args[:2] == ["issue", "create"] for args in calls)
