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


# ── 판정 ─────────────────────────────────────────────────────────
# 거래일 20개(주말 제외 4주). 종목은 매일 +1%, 지수는 매일 +0.5% 로 단조 상승.
def _series(n, start=100.0, step=0.01, first="2026-05-04"):
    import datetime
    d = datetime.date.fromisoformat(first)
    out, v = [], start
    while len(out) < n:
        if d.weekday() < 5:                      # 월~금만 거래일
            out.append((d.isoformat(), round(v, 4)))
            v *= (1 + step)
        d += datetime.timedelta(days=1)
    return out


def _call(date="2026-05-04", stance="bullish"):
    return {"stock": "T", "market": "KR", "ticker": "000000",
            "date": date, "stance": stance, "type": "view",
            "conflict": False, "sources": []}


def test_entry_is_next_trading_day_not_same_day():
    from hublib.verify import judge_call
    s = _series(30)
    r = judge_call(_call("2026-05-04"), s, [], horizons=(5,))
    assert r["entry_date"] == "2026-05-05", "발화일 종가로 진입하면 look-ahead"


def test_entry_skips_weekend():
    from hublib.verify import judge_call
    s = _series(30)                              # 2026-05-08 이 금요일
    r = judge_call(_call("2026-05-08"), s, [], horizons=(5,))
    assert r["entry_date"] == "2026-05-11", "금요일 발화는 월요일 진입"


def test_entry_skips_gap_of_any_length():
    from hublib.verify import judge_call
    s = [("2026-05-04", 100.0), ("2026-05-20", 110.0), ("2026-05-21", 111.0)]
    r = judge_call(_call("2026-05-05"), s, [], horizons=(1,))
    assert r["entry_date"] == "2026-05-20", "연휴가 길어도 다음 거래일을 잡아야 함"


def test_horizon_counts_trading_days_not_calendar_days():
    from hublib.verify import judge_call
    s = _series(40)
    r = judge_call(_call("2026-05-04"), s, [], horizons=(20,))
    # 진입 2026-05-05(인덱스 1) + 거래일 20 = 인덱스 21
    assert r["h20"]["exit_date"] == s[21][0]


def test_immature_horizon_is_none_not_zero():
    from hublib.verify import judge_call
    s = _series(10)
    r = judge_call(_call("2026-05-04"), s, [], horizons=(5, 20))
    assert r["h5"] is not None
    assert r["h20"] is None, "미성숙 구간을 0으로 채우면 적중률이 오염된다"


def test_excess_is_stock_return_minus_benchmark():
    from hublib.verify import judge_call
    s = _series(30, step=0.01)                   # 종목 +1%/일
    b = _series(30, step=0.005)                  # 지수 +0.5%/일
    r = judge_call(_call(), s, b, horizons=(5,))["h5"]
    assert r["ret"] > r["bench"] > 0
    assert abs(r["excess"] - (r["ret"] - r["bench"])) < 0.011
    assert r["hit"] is True


def test_bullish_loses_when_it_lags_the_benchmark():
    from hublib.verify import judge_call
    s = _series(30, step=0.002)                  # 종목이 지수보다 부진
    b = _series(30, step=0.01)
    r = judge_call(_call(stance="bullish"), s, b, horizons=(5,))["h5"]
    assert r["excess"] < 0 and r["hit"] is False, "올랐어도 지수에 지면 미적중"


def test_bearish_hit_is_sign_flipped():
    from hublib.verify import judge_call
    s = _series(30, step=0.002)
    b = _series(30, step=0.01)
    r = judge_call(_call(stance="bearish"), s, b, horizons=(5,))["h5"]
    assert r["excess"] < 0 and r["hit"] is True


def test_benchmark_uses_asof_when_exact_date_missing():
    from hublib.verify import judge_call
    s = _series(30)
    b = [(d, v) for d, v in _series(30) if d not in (s[1][0], s[6][0])]  # 진입·청산일 결측
    r = judge_call(_call(), s, b, horizons=(5,))["h5"]
    assert r["bench"] is not None, "직전 거래일 값으로 대체돼야 함"


def test_missing_benchmark_falls_back_to_absolute_return():
    from hublib.verify import judge_call
    r = judge_call(_call(), _series(30), [], horizons=(5,))["h5"]
    assert r["bench"] is None and r["excess"] is None
    assert r["hit"] is True, "벤치마크가 없으면 절대수익 부호로 판정"


def test_no_price_series_returns_error_not_crash():
    from hublib.verify import judge_call
    r = judge_call(_call(), [], [], horizons=(5,))
    assert r["error"] == "no_price" and r["h5"] is None


def test_call_after_last_trading_day_is_pending():
    from hublib.verify import judge_call
    s = _series(10)
    r = judge_call(_call("2026-12-31"), s, [], horizons=(5,))
    assert r["error"] == "no_entry" and r["entry_date"] is None
