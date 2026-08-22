# -*- coding: utf-8 -*-
"""전일 요약 대비 diff (스펙 C5)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _data(to="2026-08-22"):
    return {
        "build": {"to": to, "generated": f"{to} 07:30"},
        "reports": [{"id": "2026-08-21", "type": "daily"}, {"id": to, "type": "daily"}],
        "stocks": [{"name": "삼성전자", "count": 10, "mentions": [{"date": "2026-08-22"}]},
                   {"name": "신규주", "count": 2, "mentions": [{"date": "2026-08-22"}]},
                   {"name": "조용한주", "count": 3, "mentions": [{"date": "2026-07-01"}]}],
        "chat": {"targets": [{"stock": "구글", "value": "300", "unit": "달러", "date": "2026-08-22"}]},
        "verify": {"enabled": True, "calls": [{"stock": "삼성전자", "date": "2026-08-22", "stance": "bullish"}]},
    }


def test_summarize_shape():
    from hublib.whatsnew import summarize
    s = summarize(_data())
    assert s["to"] == "2026-08-22"
    assert s["stocks"]["삼성전자"] == {"count": 10, "last": "2026-08-22"}
    assert s["calls"] == ["삼성전자|2026-08-22|bullish"]
    assert s["targets"] == ["구글|300|달러|2026-08-22"]
    assert s["reports"] == ["2026-08-21", "2026-08-22"]


def test_diff_detects_new_surging_calls_targets_reports():
    from hublib.whatsnew import summarize, diff
    prev = summarize({**_data("2026-08-21"), "stocks": [{"name": "삼성전자", "count": 6, "mentions": []},
                                                        {"name": "조용한주", "count": 3, "mentions": []}],
                      "chat": {"targets": []}, "verify": {"enabled": True, "calls": []},
                      "reports": [{"id": "2026-08-21", "type": "daily"}]})
    cur = _data()
    out = diff(prev, cur)
    assert out["since"] == "2026-08-21"
    assert out["new_stocks"] == [{"name": "신규주", "count": 2}]
    assert out["surging"] == [{"name": "삼성전자", "recent": 10, "prev": 6}]   # +3 이상
    assert out["new_calls"] == [{"stock": "삼성전자", "stance": "bullish", "date": "2026-08-22"}]
    assert out["new_targets"] == [{"stock": "구글", "value": "300", "unit": "달러", "date": "2026-08-22"}]
    assert out["new_reports"] == ["2026-08-22"]


def test_diff_without_prev_is_none():
    from hublib.whatsnew import diff
    assert diff(None, _data()) is None


def test_diff_same_day_is_none():
    from hublib.whatsnew import summarize, diff
    assert diff(summarize(_data()), _data()) is None, "같은 빌드 기준일이면 diff 없음 (하루 2회 빌드 방지)"


def test_load_save_roundtrip(tmp_path):
    from hublib.whatsnew import summarize, save_summary, load_summary
    p = tmp_path / "kb_summary.json"
    s = summarize(_data()); save_summary(str(p), s)
    assert load_summary(str(p)) == s
    assert load_summary(str(tmp_path / "none.json")) is None


def test_summarize_dedupes_identical_calls_and_targets():
    """원본 chat.targets 에는 같은 사람이 같은 날 올린 완전 중복 레코드가 있다(실데이터 206건 중 69건).
    그대로 두면 홈 '오늘 달라진 것' 카드가 같은 목표가를 3번 표시한다."""
    from hublib.whatsnew import summarize
    data = {
        "build": {"to": "2026-08-21", "generated": "2026-08-21 07:30"},
        "stocks": [], "reports": [],
        "verify": {"enabled": True, "calls": [
            {"stock": "효성중공업", "date": "2026-05-05", "stance": "bullish"},
            {"stock": "효성중공업", "date": "2026-05-05", "stance": "bullish"},
        ]},
        "chat": {"targets": [
            {"stock": "효성중공업", "value": "500", "unit": "만원", "date": "2026-08-03", "sharer": "A"},
            {"stock": "효성중공업", "value": "500", "unit": "만원", "date": "2026-08-03", "sharer": "A"},
            {"stock": "효성중공업", "value": "500", "unit": "만원", "date": "2026-08-03", "sharer": "A"},
            {"stock": "한화오션", "value": "9", "unit": "만원", "date": "2026-08-03", "sharer": "B"},
        ]},
    }
    cur = summarize(data)
    assert cur["targets"] == ["한화오션|9|만원|2026-08-03", "효성중공업|500|만원|2026-08-03"]
    assert cur["calls"] == ["효성중공업|2026-05-05|bullish"]


def test_diff_emits_each_new_target_once():
    from hublib.whatsnew import diff
    prev = {"to": "2026-08-20", "stocks": {}, "calls": [], "targets": [], "reports": []}
    data = {
        "build": {"to": "2026-08-21", "generated": "2026-08-21 07:30"},
        "stocks": [], "reports": [], "verify": {"enabled": False},
        "chat": {"targets": [{"stock": "효성중공업", "value": "500", "unit": "만원", "date": "2026-08-03"}] * 3},
    }
    out = diff(prev, data)
    assert out["new_targets"] == [{"stock": "효성중공업", "value": "500", "unit": "만원", "date": "2026-08-03"}]
