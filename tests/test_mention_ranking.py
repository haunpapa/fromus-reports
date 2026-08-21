"""언급 총량 기반 테마 랭킹 (2026-08-21 개편) — 수급·시황 카드의 키워드 언급도 집계."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest


def _report(cards):
    return {
        "type": "daily", "id": "2026-08-21", "date": "2026-08-21",
        "sort_date": "2026-08-21", "weekday": "목",
        "headline": "", "subhead": "", "quote": {},
        "insights": [], "timeline": [], "actions": [], "glossary": [],
        "indicators": [], "next": [], "readings": [], "strategy": [],
        "sectors": [{"name": n, "sub": sub, "note": note, "stocks": st}
                    for n, sub, note, st in cards],
    }


def _sector(agg, theme):
    return next((s for s in agg["sectors"] if s["theme"] == theme), None)


def test_supply_card_note_keyword_adds_indirect_mention():
    from hublib.aggregate import aggregate
    agg = aggregate([_report([
        ("외국인 순매수 TOP", "", "반도체 대형주로 자금 쏠림", ["SK하이닉스"]),
    ])])
    S = _sector(agg, "반도체·메모리")
    assert S and S["count"] == 1 and S["direct"] == 0 and S["indirect"] == 1
    assert S["mentions"][0]["kind"] == "수급"


def test_market_card_note_keyword_adds_indirect_mention():
    from hublib.aggregate import aggregate
    agg = aggregate([_report([
        ("오늘의 특징주", "", "2차전지 강세가 두드러진 하루", ["에코프로"]),
    ])])
    S = _sector(agg, "2차전지")
    assert S and S["count"] == 1 and S["indirect"] == 1
    assert S["mentions"][0]["kind"] == "시황"


def test_direct_card_counts_once_not_double():
    """직접 테마 카드는 자기 테마에 1회만 — 이름 키워드로 간접 중복 금지."""
    from hublib.aggregate import aggregate
    agg = aggregate([_report([
        ("반도체 — 오늘의 주도", "", "HBM 랠리 지속", ["SK하이닉스"]),
    ])])
    S = _sector(agg, "반도체·메모리")
    assert S["count"] == 1 and S["direct"] == 1 and S["indirect"] == 0
    assert S["mentions"][0]["kind"] == "코너"


def test_direct_card_note_can_add_indirect_to_other_theme():
    from hublib.aggregate import aggregate
    agg = aggregate([_report([
        ("반도체 — 오늘의 주도", "", "2차전지에서 자금이 넘어왔다", ["SK하이닉스"]),
    ])])
    assert _sector(agg, "반도체·메모리")["count"] == 1
    other = _sector(agg, "2차전지")
    assert other and other["indirect"] == 1 and other["direct"] == 0


def test_stocks_come_from_direct_cards_only():
    from hublib.aggregate import aggregate
    agg = aggregate([_report([
        ("외국인 순매수 TOP", "", "반도체 쏠림", ["SK하이닉스"]),
        ("반도체 코너", "", "", ["삼성전자"]),
    ])])
    S = _sector(agg, "반도체·메모리")
    assert S["stocks"] == ["삼성전자"]


def test_ascii_keyword_needs_word_boundary():
    """'business' 의 ess, 'answer' 의 sw 같은 오탐 금지."""
    from hublib.aggregate import aggregate
    agg = aggregate([_report([
        ("오늘의 특징주", "", "business as usual, answer is no", ["삼성전자"]),
    ])])
    assert _sector(agg, "AI 전력·원전·ESS") is None
    assert _sector(agg, "소프트웨어·AI") is None
    agg2 = aggregate([_report([
        ("오늘의 특징주", "", "ESS 수주 급증", ["LG에너지솔루션"]),
    ])])
    assert _sector(agg2, "AI 전력·원전·ESS")["indirect"] == 1


def test_ranking_sorted_by_total_mentions():
    from hublib.aggregate import aggregate
    agg = aggregate([_report([
        ("바이오 코너", "", "", ["알테오젠"]),                       # 바이오 direct 1
        ("오늘의 특징주", "", "반도체 강세", ["삼성전자"]),            # 반도체 indirect 1
        ("외국인 순매수 TOP", "", "반도체 쏠림", ["SK하이닉스"]),      # 반도체 indirect 1
    ])])
    themes = [s["theme"] for s in agg["sectors"]]
    assert themes.index("반도체·메모리") < themes.index("바이오·제약")


def test_fallback_raw_theme_still_direct_only():
    from hublib.aggregate import aggregate
    agg = aggregate([_report([("엔터·미디어", "", "", ["하이브"])])])
    S = _sector(agg, "엔터·미디어")
    assert S and S["direct"] == 1 and S["count"] == 1
