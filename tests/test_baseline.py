# -*- coding: utf-8 -*-
"""리팩토링 안전망: 현재 파서·집계 출력을 고정하는 특성화(characterization) 테스트.

값이 바뀌면 파서/집계 동작이 바뀐 것 — 의도된 변경일 때만 이 파일을 갱신한다.
Phase 3에서 build_hub → hublib 로 이동해도 이 테스트가 통과해야 한다
(그때 _parse_report/_aggregate import 경로만 수정)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures", "reports")
FIXTURE_DAILY = os.path.join(FIXDIR, "daily", "2026-05-04.html")
FIXTURE_WEEKLY = os.path.join(FIXDIR, "weekly", "2026-W15.html")

# 파서/집계 진입점 — Phase 3 리팩토링 후 여기만 바꾼다
def _parse_report(path):
    from build_hub import parse_report
    return parse_report(path)

def _aggregate(reports):
    from build_hub import aggregate
    return aggregate(reports)

# parse_report 가 반드시 포함해야 하는 안정 키(부분집합 — 부수 키 추가에 견고)
CORE_KEYS = {
    "type", "date", "id", "sort_date", "sectors", "insights",
    "strategy", "glossary", "headline", "actions",
}


def test_daily_report_shape():
    r = _parse_report(FIXTURE_DAILY)
    assert r["type"] == "daily"
    assert r["date"] == "2026-05-04"
    assert CORE_KEYS.issubset(set(r.keys())), (
        "누락된 코어 키: " + str(CORE_KEYS - set(r.keys()))
    )
    # 이 리포트는 8개 섹터 카드를 담는다 (파서 회귀 감지용)
    assert len(r["sectors"]) == 8


def test_weekly_report_shape():
    r = _parse_report(FIXTURE_WEEKLY)
    assert r["type"] == "weekly"
    assert r["id"] == "2026-W15"


def test_aggregate_extracts_expected_counts():
    r = _parse_report(FIXTURE_DAILY)
    r["file"] = "daily/2026-05-04.html"
    agg = _aggregate([r])
    assert isinstance(agg.get("stocks"), list)
    assert isinstance(agg.get("sectors"), list)
    # 2026-05-04 단일 리포트 집계 결과 — 종목 27, 섹터테마 8
    assert len(agg["stocks"]) == 27, f"종목 수 변동: {len(agg['stocks'])}"
    assert len(agg["sectors"]) == 8, f"섹터 수 변동: {len(agg['sectors'])}"
    # 각 종목은 최소 name·count 를 가진다
    for s in agg["stocks"]:
        assert s.get("name") and isinstance(s.get("count"), int)
