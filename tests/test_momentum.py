# -*- coding: utf-8 -*-
"""시장 모멘텀 — 타임아웃·병렬 히스토리 보강 (2026-09 후속)."""
import time


def test_stock_history_timeout_does_not_hang(monkeypatch):
    """느린 데이터 소스는 타임아웃으로 격리된다 — SIGALRM 없이(워커 스레드에서도 동작)."""
    import hublib.momentum as mom

    class _SlowFdr:
        @staticmethod
        def DataReader(code, start):
            time.sleep(5)
            return None

    monkeypatch.setattr(mom, "_ensure_finance_datareader", lambda: _SlowFdr)
    monkeypatch.setenv("MARKET_MOMENTUM_STOCK_TIMEOUT", "1")
    t0 = time.monotonic()
    mm, err = mom._stock_market_momentum("테스트", {"code": "000000", "market": "KOSPI"}, {}, "2026-06-01")
    assert mm is None and err
    assert time.monotonic() - t0 < 3, "타임아웃이 1초 부근에서 끊어야 한다"


def test_history_enrich_runs_in_parallel_and_isolates_failures(monkeypatch):
    """히스토리 보강은 병렬로 돌고, 한 종목 실패가 나머지를 막지 않는다."""
    import hublib.momentum as mom
    calls = []

    def fake_history(name, meta, index_series, start):
        calls.append(name)
        if name == "B":
            raise RuntimeError("boom")
        return ({"state": "flat", "label": "· 시장 유지", "score": 50.0, "reason": "t",
                 "ticker": meta["code"], "market": "KOSPI"}, None)

    monkeypatch.setattr(mom, "_stock_market_momentum", fake_history)
    pairs = [({"name": n}, {"code": f"00000{i}", "market": "KOSPI"}) for i, n in enumerate("ABC")]
    done, failures = mom._enrich_history(pairs, {}, "2026-06-01", workers=2)
    assert done == 2
    assert any("B" in f for f in failures)
    assert sorted(calls) == ["A", "B", "C"]
