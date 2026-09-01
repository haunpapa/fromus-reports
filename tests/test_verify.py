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


# ── 집계 ─────────────────────────────────────────────────────────
def _judged(stock, hit, excess, conflict=False, error=None, h20=True):
    c = {"stock": stock, "market": "KR", "ticker": "000000", "stance": "bullish",
         "conflict": conflict, "error": error, "h20": None}
    if h20 and not error:
        c["h20"] = {"exit_date": "2026-06-01", "ret": excess, "bench": 0.0,
                    "excess": excess, "hit": hit}
    return c


def test_aggregate_excludes_conflict_pending_and_failed():
    from hublib.verify import aggregate_calls
    calls = [
        _judged("A", True, 5.0),
        _judged("A", False, -2.0),
        _judged("A", True, 1.0, conflict=True),       # 충돌 — 제외
        _judged("A", True, 0.0, h20=False),           # 판정 대기 — 분모 제외
        _judged("A", True, 0.0, error="no_price"),    # 수집 실패 — 분모 제외
    ]
    s = aggregate_calls(calls, horizons=(20,))["summary"]["h20"]
    assert s["judged"] == 2 and s["hit"] == 1
    assert s["hit_rate"] == 50.0
    assert s["pending"] == 1 and s["failed"] == 1


def test_aggregate_marks_low_sample_stocks():
    from hublib.verify import aggregate_calls
    calls = [_judged("많음", True, 1.0) for _ in range(5)] + [_judged("적음", True, 9.0)]
    rows = {r["name"]: r for r in aggregate_calls(calls, horizons=(20,))["stocks"]}
    assert rows["많음"]["low_sample"] is False
    assert rows["적음"]["low_sample"] is True, "5건 미만은 표본 부족"


def test_aggregate_sorts_low_sample_last_regardless_of_score():
    from hublib.verify import aggregate_calls
    calls = [_judged("많음", False, -9.0) for _ in range(5)] + [_judged("적음", True, 99.0)]
    names = [r["name"] for r in aggregate_calls(calls, horizons=(20,))["stocks"]]
    assert names == ["많음", "적음"], "표본 부족 종목이 상위로 올라오면 안 됨"


def test_aggregate_empty_input_is_safe():
    from hublib.verify import aggregate_calls
    out = aggregate_calls([], horizons=(20,))
    assert out["summary"]["h20"]["judged"] == 0
    assert out["summary"]["h20"]["hit_rate"] is None      # 0.0 이 아니라 None
    assert out["stocks"] == []


# ── 캐시 ─────────────────────────────────────────────────────────
def test_merge_points_dedupes_and_sorts():
    from hublib.verify import merge_points
    old = [("2026-05-04", 100.0), ("2026-05-05", 101.0)]
    new = [("2026-05-05", 999.0), ("2026-05-06", 102.0)]
    assert merge_points(old, new) == [
        ("2026-05-04", 100.0), ("2026-05-05", 999.0), ("2026-05-06", 102.0)
    ], "겹치는 날짜는 새 값이 이겨야 함"


def test_price_cache_roundtrip_and_incremental(tmp_path):
    from hublib.verify import PriceCache
    p = str(tmp_path / "price_cache.json")
    c = PriceCache(p)
    assert c.get("KR:000660") == []
    c.put("KR:000660", [("2026-05-04", 100.0)])
    c.save()

    c2 = PriceCache(p)
    assert c2.get("KR:000660") == [("2026-05-04", 100.0)]
    assert c2.last("KR:000660") == "2026-05-04"


def test_price_cache_version_bump_invalidates(tmp_path):
    import json as _json
    from hublib.verify import PriceCache, CACHE_VERSION
    p = tmp_path / "price_cache.json"
    p.write_text(_json.dumps({"v": CACHE_VERSION + 1,
                              "series": {"KR:000660": {"last": "x", "points": [["d", 1]]}}}),
                 encoding="utf-8")
    assert PriceCache(str(p)).get("KR:000660") == [], "버전이 다르면 전량 무효화"


def test_price_cache_corrupt_file_falls_back(tmp_path):
    from hublib.verify import PriceCache
    p = tmp_path / "price_cache.json"
    p.write_text("{ not json", encoding="utf-8")
    assert PriceCache(str(p)).get("anything") == []


def test_price_cache_save_is_noop_when_clean(tmp_path):
    from hublib.verify import PriceCache
    p = tmp_path / "price_cache.json"
    PriceCache(str(p)).save()
    assert not p.exists()


# ── 수집 ─────────────────────────────────────────────────────────
def test_fetch_prices_uses_cache_and_only_requests_the_gap(tmp_path):
    from hublib.verify import PriceCache, fetch_prices
    cache = PriceCache(str(tmp_path / "c.json"))
    cache.put("KR:000660", [("2026-05-04", 100.0), ("2026-05-05", 101.0)])
    seen = {}

    def loader(ticker, start):
        seen[ticker] = start
        return [("2026-05-06", 102.0)]

    calls = [{"stock": "S", "market": "KR", "ticker": "000660", "date": "2026-05-04"}]
    out = fetch_prices(calls, cache, loaders={"KR": loader})
    assert seen["000660"] == "2026-05-05", "캐시 마지막 날부터만 요청해야 함"
    assert out["KR:000660"][-1] == ("2026-05-06", 102.0)
    assert len(out["KR:000660"]) == 3


def test_fetch_prices_cold_start_reaches_back_before_first_call(tmp_path):
    from hublib.verify import PriceCache, fetch_prices
    seen = {}

    def loader(ticker, start):
        seen[ticker] = start
        return [("2026-03-01", 100.0)]

    calls = [{"stock": "S", "market": "US", "ticker": "NVDA", "date": "2026-03-05"}]
    fetch_prices(calls, PriceCache(str(tmp_path / "c.json")), loaders={"US": loader})
    assert seen["NVDA"] < "2026-03-05", "첫 콜 이전부터 받아야 진입일을 찾는다"


def test_fetch_prices_isolates_a_failing_ticker(tmp_path):
    from hublib.verify import PriceCache, fetch_prices

    def loader(ticker, start):
        if ticker == "BAD":
            raise RuntimeError("boom")
        return [("2026-05-04", 100.0)]

    calls = [{"stock": "A", "market": "KR", "ticker": "BAD", "date": "2026-05-04"},
             {"stock": "B", "market": "KR", "ticker": "OK", "date": "2026-05-04"}]
    out = fetch_prices(calls, PriceCache(str(tmp_path / "c.json")), loaders={"KR": loader})
    assert out["KR:BAD"] == [], "실패한 종목은 빈 시계열 — 나머지는 살아야 함"
    assert out["KR:OK"] == [("2026-05-04", 100.0)]


def test_fetch_prices_requests_each_ticker_once(tmp_path):
    from hublib.verify import PriceCache, fetch_prices
    hits = []

    def loader(ticker, start):
        hits.append(ticker)
        return [("2026-05-04", 100.0)]

    calls = [{"stock": "S", "market": "KR", "ticker": "000660", "date": d}
             for d in ("2026-05-04", "2026-05-11", "2026-06-01")]
    fetch_prices(calls, PriceCache(str(tmp_path / "c.json")), loaders={"KR": loader})
    assert hits == ["000660"], "같은 종목을 콜 수만큼 반복 요청하면 안 됨"


def test_fetch_prices_parallel_isolates_failures(tmp_path):
    """병렬화 후에도 한 종목 실패가 다른 종목·캐시를 오염시키지 않는다."""
    from hublib.verify import PriceCache, fetch_prices
    cache = PriceCache(str(tmp_path / "p.json"))
    calls = [{"market": "KR", "ticker": t, "date": "2026-08-01"} for t in ("A", "B", "C", "D")]

    def loader(ticker, start):
        if ticker == "B":
            raise RuntimeError("boom")
        return [("2026-08-01", 100.0), ("2026-08-04", 101.0)]

    out = fetch_prices(calls, cache, loaders={"KR": loader})
    assert out["KR:B"] == []                       # 실패는 빈 시계열로 격리
    for t in ("A", "C", "D"):
        assert len(out[f"KR:{t}"]) == 2            # 나머지는 정상
        assert cache.last(f"KR:{t}") == "2026-08-04"  # 캐시도 갱신됨
    assert cache.last("KR:B") is None


# ── 조립 ─────────────────────────────────────────────────────────
def test_build_verify_end_to_end_with_fake_loaders(tmp_path):
    from hublib.verify import build_verify
    def loader(ticker, start):
        return _series(40)
    out = build_verify(chat_kb=_mini(), cache_path=str(tmp_path / "c.json"),
                       loaders={"KR": loader, "US": loader},
                       market_of=lambda code: "KOSPI")
    assert out["enabled"] is True
    assert out["meta"]["calls"] == 1            # 3콜 중 충돌 2 제외
    assert out["meta"]["excluded"]["conflict"] == 2
    assert out["summary"]["h20"]["judged"] >= 0
    assert len(out["calls"]) == 3, "충돌 콜도 근거 화면용으로 남긴다"


def test_build_verify_survives_total_collection_failure(tmp_path):
    from hublib.verify import build_verify
    def boom(ticker, start):
        raise RuntimeError("network down")
    out = build_verify(chat_kb=_mini(), cache_path=str(tmp_path / "c.json"),
                       loaders={"KR": boom, "US": boom},
                       market_of=lambda code: "KOSPI")
    assert out["enabled"] is True, "종목별 실패는 격리 — 레이어 자체는 살아있다"
    assert out["summary"]["h20"]["failed"] >= 1


def test_build_verify_returns_disabled_on_unexpected_error(tmp_path):
    from hublib.verify import build_verify
    out = build_verify(chat_kb={"stocks": "not-a-dict"}, cache_path=str(tmp_path / "c.json"))
    assert out["enabled"] is False and out["reason"]


def test_build_verify_returns_none_without_chat_data(tmp_path):
    from hublib.verify import build_verify
    assert build_verify(chat_kb=None, cache_path=str(tmp_path / "c.json")) is None


def test_aggregate_counts_too_recent_calls_as_pending_not_failed():
    """며칠 전 콜은 아직 진입할 거래일이 없다 — 수집 실패가 아니라 판정 대기다."""
    from hublib.verify import aggregate_calls
    calls = [
        _judged("A", True, 5.0),
        _judged("A", True, 0.0, error="no_entry"),    # 콜 이후 거래일 없음 → 대기
        _judged("A", True, 0.0, error="no_price"),    # 시계열 자체가 없음 → 실패
    ]
    s = aggregate_calls(calls, horizons=(20,))["summary"]["h20"]
    assert s["failed"] == 1, "no_entry 를 실패로 세면 없는 장애를 보고하게 된다"
    assert s["pending"] == 1


# ── 리포트 수급 코호트 ───────────────────────────────────────────
def _report_stocks():
    return [
        {"name": "삼성전자", "count": 5, "themes": ["반도체·메모리"], "mentions": [
            {"date": "2026-05-04", "id": "2026-05-04", "source": "수급", "label": "기관 순매수 · 코스피", "annotation": "1,000억"},
            {"date": "2026-05-04", "id": "2026-05-04", "source": "테마", "label": "반도체"},
            {"date": "2026-05-11", "id": "2026-05-11", "source": "수급", "label": "외국인 순매수 · 코스피", "annotation": ""}]},
        {"name": "엔비디아", "count": 9, "themes": ["소프트웨어·AI"], "mentions": [
            {"date": "2026-05-04", "id": "2026-05-04", "source": "수급", "label": "기관 순매수"}]},
        {"name": "조용한주", "count": 1, "themes": [], "mentions": [{"date": "2026-05-04", "source": "테마"}]},
    ]


TICKER_MAP = {"삼성전자": {"code": "005930", "market": "KOSPI"}, "조용한주": {"code": "000001", "market": "KOSDAQ"}}


def test_extract_report_calls_supply_only_with_ticker():
    from hublib.verify import extract_report_calls
    calls, stats = extract_report_calls(_report_stocks(), TICKER_MAP)
    assert [c["date"] for c in calls] == ["2026-05-04", "2026-05-11"]
    c = calls[0]
    assert c["stock"] == "삼성전자" and c["ticker"] == "005930" and c["market"] == "KR"
    assert c["stance"] == "bullish" and c["type"] == "supply" and c["bench_label"] == "KOSPI" and c["conflict"] is False
    assert c["sources"] == [{"sharer": "리포트", "snippet": "기관 순매수 · 코스피 · 1,000억", "id": "2026-05-04"}]
    assert stats == {"population": 3, "no_ticker": 1, "stocks": 1, "merged_from": 2, "duplicate": 0}


def test_extract_report_calls_merges_same_day_and_caps_stocks():
    from hublib.verify import extract_report_calls
    stocks = _report_stocks()
    stocks[0]["mentions"].append({"date": "2026-05-04", "source": "수급", "label": "투신 순매수", "id": "2026-05-04"})
    calls, stats = extract_report_calls(stocks, TICKER_MAP)
    assert len([c for c in calls if c["date"] == "2026-05-04" and c["stock"] == "삼성전자"]) == 1
    assert stats["duplicate"] == 1
    calls2, _ = extract_report_calls(stocks, TICKER_MAP, max_stocks=0)
    assert calls2 == []


def test_downsample_series_every_5th_plus_last():
    from hublib.verify import downsample_series
    pts = [(f"2026-05-{i:02d}", float(i)) for i in range(1, 24)]
    out = downsample_series(pts, step=5, max_points=80)
    assert out[0] == ["2026-05-01", 1.0] and out[-1] == ["2026-05-23", 23.0]
    assert [d for d, _ in out] == ["2026-05-01", "2026-05-06", "2026-05-11", "2026-05-16", "2026-05-21", "2026-05-23"]
    assert len(downsample_series(pts, step=1, max_points=4)) <= 4
    assert downsample_series([], step=5) == []


def test_aggregate_themes_rolls_calls_by_stock_theme():
    from hublib.verify import aggregate_themes
    judged = [
        {"stock": "A", "conflict": False, "h20": {"hit": True, "excess": 4.0}},
        {"stock": "A", "conflict": False, "h20": {"hit": False, "excess": -2.0}},
        {"stock": "B", "conflict": False, "h20": {"hit": True, "excess": 1.0}},
        {"stock": "C", "conflict": True,  "h20": {"hit": True, "excess": 9.0}},
    ]
    themes = {"A": ["반도체·메모리", "삼성그룹"], "B": ["반도체·메모리"], "C": ["반도체·메모리"]}
    out = aggregate_themes(judged, themes, horizons=(20,))
    semi = next(t for t in out if t["theme"] == "반도체·메모리")
    assert semi["calls"] == 3 and semi["h20"]["judged"] == 3 and semi["h20"]["hit"] == 2
    assert semi["h20"]["avg_excess"] == 1.0
    assert next(t for t in out if t["theme"] == "삼성그룹")["calls"] == 2
    assert out[0]["theme"] == "반도체·메모리", "콜 수 내림차순"


def test_build_verify_report_cohort_with_fake_loaders(tmp_path):
    from hublib.verify import build_verify
    ser = _series(40)

    def loader(ticker, start):
        return ser
    out = build_verify(chat_kb=_mini(), report_stocks=_report_stocks(), ticker_map=TICKER_MAP,
                       cache_path=str(tmp_path / "c.json"), loaders={"KR": loader, "US": loader},
                       market_of=lambda code: "KOSPI")
    assert out["enabled"] and out["meta"]["cohort"] == "core"
    rep = out["report"]
    assert rep["enabled"] and rep["meta"]["cohort"] == "report" and rep["meta"]["calls"] == 2
    assert rep["meta"]["excluded"]["no_ticker"] == 1
    assert rep["stocks"][0]["name"] == "삼성전자" and rep["stocks"][0]["series"][0][0] <= "2026-05-04"
    assert out["stocks"][0]["series"], "채팅 코호트 종목에도 시계열"
    assert out["themes"] and out["themes"][0]["cohort"] == "report"
    assert all(c["stock"] != "삼성전자" or c["type"] == "supply" for c in rep["calls"])


def test_krx_listing_downloads_once_per_build(monkeypatch):
    """_load_krx_listing 은 lru_cache 로 빌드당 1회만 실행된다 (2026-09 진단)"""
    import hublib.momentum as mom
    calls = {"n": 0}

    class _FakeFdr:
        @staticmethod
        def StockListing(_):
            calls["n"] += 1
            import pandas as pd
            return pd.DataFrame([{"Name": "삼성전자", "Code": "005930", "Market": "KOSPI",
                                  "Close": 70000, "Amount": 1.0, "Marcap": 1.0, "Volume": 1.0}])

    mom._load_krx_listing.cache_clear()
    monkeypatch.setattr(mom, "_ensure_finance_datareader", lambda: _FakeFdr)
    try:
        mom._load_krx_listing()
        mom._load_krx_listing()
        assert calls["n"] == 1
    finally:
        mom._load_krx_listing.cache_clear()   # 다른 테스트에 가짜 목록이 새지 않게
        mom._build_ticker_map.cache_clear()
