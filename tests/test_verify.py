# -*- coding: utf-8 -*-
"""콜 검증 레이어 테스트 — 순수 함수는 네트워크 없이 전량 검증한다."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "chat_kb_mini.json")


def _mini():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_extract_drops_neutral_bot_asset_and_tickerless():
    from hublib.verify import extract_calls
    calls, stats = extract_calls(_mini())

    assert stats["population"] == 7, "neutral·무티커는 모집단에서 빠져야 함"
    assert stats["bot"] == 2
    assert stats["asset"] == 2
    assert stats["bot_and_asset"] == 1
    assert stats["core"] == 4
    assert all(c["stock"] == "삼성전자" for c in calls), "봇·ASSET 콜이 남아있음"


def test_extract_merges_same_stock_date_stance():
    from hublib.verify import extract_calls
    calls, stats = extract_calls(_mini())

    assert stats["duplicate"] == 1
    assert len(calls) == 3
    merged = [c for c in calls if c["date"] == "2026-05-04"]
    assert len(merged) == 1
    assert [s["snippet"] for s in merged[0]["sources"]] == ["A", "B"], "원 발화가 모두 보존돼야 함"


def test_extract_flags_same_day_conflict():
    from hublib.verify import extract_calls
    calls, stats = extract_calls(_mini())

    assert stats["conflict"] == 2
    day = [c for c in calls if c["date"] == "2026-05-11"]
    assert len(day) == 2
    assert all(c["conflict"] for c in day)
    assert not [c for c in calls if c["date"] == "2026-05-04"][0]["conflict"]


def test_extract_is_deterministic():
    from hublib.verify import extract_calls
    a, _ = extract_calls(_mini())
    b, _ = extract_calls(_mini())
    assert json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)
