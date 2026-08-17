# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 채팅 방향성 발화(콜)의 사후 성과 검증.

설계: docs/superpowers/specs/2026-08-17-call-verification-design.md

순수 함수(extract_calls·judge_call·aggregate_calls)와 네트워크(fetch_prices)를 분리한다.
순수 함수는 네트워크 없이 전량 테스트되고, 어떤 실패도 허브 빌드를 깨뜨리지 않는다.
"""

BOT_SHARER = "김병철(봇)"
BENCHED_MARKETS = ("KR", "US")     # 대응 벤치마크 지수가 있는 시장
SNIPPET_MAX = 140


def extract_calls(chat_kb):
    """chat_kb → (calls, stats). 네트워크·파일 IO 없음.

    봇 발화와 무벤치마크(ASSET·미상) 종목을 뺀 뒤, 같은 (종목,날짜,방향)을 한 콜로
    병합하고, 같은 (종목,날짜)에 양방향이 공존하면 conflict 로 표시한다.
    conflict 콜도 반환한다 — 통계 제외는 aggregate_calls 의 책임이다.
    """
    raw = []
    for name, s in (chat_kb.get("stocks") or {}).items():
        market = s.get("market") or ""
        ticker = s.get("ticker") or ""
        if not ticker:
            continue                    # 티커 없으면 가격 대조 자체가 불가
        for m in s.get("mentions") or []:
            if m.get("stance") not in ("bullish", "bearish"):
                continue
            raw.append({
                "stock": name, "market": market, "ticker": ticker,
                "date": m.get("date") or "", "stance": m["stance"],
                "type": m.get("type") or "", "sharer": m.get("sharer") or "",
                "snippet": (m.get("snippet") or "")[:SNIPPET_MAX],
                "is_bot": m.get("sharer") == BOT_SHARER,
                "is_asset": market not in BENCHED_MARKETS,
            })

    core = [c for c in raw if not c["is_bot"] and not c["is_asset"]]

    # 정렬 후 병합 — set/dict 순서에 의존하지 않아 빌드마다 같은 바이트가 나온다
    merged = {}
    for c in sorted(core, key=lambda x: (x["date"], x["stock"], x["stance"], x["sharer"])):
        key = (c["stock"], c["date"], c["stance"])
        if key in merged:
            merged[key]["sources"].append({"sharer": c["sharer"], "snippet": c["snippet"]})
            continue
        merged[key] = {
            "stock": c["stock"], "market": c["market"], "ticker": c["ticker"],
            "date": c["date"], "stance": c["stance"], "type": c["type"],
            "conflict": False,
            "sources": [{"sharer": c["sharer"], "snippet": c["snippet"]}],
        }

    stance_by_day = {}
    for stock, date, stance in merged:
        stance_by_day.setdefault((stock, date), set()).add(stance)
    for call in merged.values():
        call["conflict"] = len(stance_by_day[(call["stock"], call["date"])]) > 1

    calls = sorted(merged.values(), key=lambda c: (c["date"], c["stock"], c["stance"]))
    stats = {
        "population": len(raw),
        "bot": sum(1 for c in raw if c["is_bot"]),
        "asset": sum(1 for c in raw if c["is_asset"]),
        "bot_and_asset": sum(1 for c in raw if c["is_bot"] and c["is_asset"]),
        "core": len(core),
        "duplicate": len(core) - len(merged),
        "conflict": sum(1 for c in calls if c["conflict"]),
    }
    return calls, stats


HORIZONS = (5, 20, 60)
PRIMARY_HORIZON = 20


def _entry_index(series, mention_date):
    """발화일보다 뒤인 첫 거래일 인덱스. 장 마감 후 발화의 look-ahead 를 막는다."""
    for i, (d, _v) in enumerate(series):
        if d > mention_date:
            return i
    return None


def _asof(series, date):
    """date 이하 최근 거래일의 값. 거래일 달력이 어긋나도 안전하게 맞춘다."""
    val = None
    for d, v in series:
        if d > date:
            break
        val = v
    return val


def judge_call(call, series, bench, horizons=HORIZONS):
    """콜 1건을 가격 시계열과 대조한다. 네트워크 없음.

    series/bench: [(YYYY-MM-DD, close)] 오름차순.
    미성숙 구간은 None 으로 남긴다 — 0으로 채우면 적중률 분모가 오염된다.
    """
    out = {"entry_date": None, "entry": None, "error": None}
    for h in horizons:
        out[f"h{h}"] = None

    if not series:
        out["error"] = "no_price"
        return out
    ei = _entry_index(series, call["date"])
    if ei is None:
        out["error"] = "no_entry"
        return out
    entry_date, entry_price = series[ei]
    if not entry_price or entry_price <= 0:
        out["error"] = "bad_entry"
        return out

    out["entry_date"] = entry_date
    out["entry"] = round(entry_price, 4)
    bench_entry = _asof(bench, entry_date) if bench else None

    for h in horizons:
        xi = ei + h
        if xi > len(series) - 1:
            continue                             # 판정 대기 — None 유지
        exit_date, exit_price = series[xi]
        if not exit_price or exit_price <= 0:
            continue
        ret = exit_price / entry_price - 1.0

        bench_ret = None
        bench_exit = _asof(bench, exit_date) if bench else None
        if bench_entry and bench_exit and bench_entry > 0:
            bench_ret = bench_exit / bench_entry - 1.0
        excess = (ret - bench_ret) if bench_ret is not None else None

        basis = excess if excess is not None else ret
        hit = (basis > 0) if call["stance"] == "bullish" else (basis < 0)
        out[f"h{h}"] = {
            "exit_date": exit_date,
            "ret": round(ret * 100, 2),
            "bench": round(bench_ret * 100, 2) if bench_ret is not None else None,
            "excess": round(excess * 100, 2) if excess is not None else None,
            "hit": hit,
        }
    return out


LOW_SAMPLE_MIN = 5


def _roll(rows):
    """판정된 구간 결과 목록 → 적중·적중률·초과수익 통계."""
    hits = sum(1 for r in rows if r["hit"])
    ex = sorted(r["excess"] for r in rows if r["excess"] is not None)
    return {
        "judged": len(rows),
        "hit": hits,
        "hit_rate": round(hits / len(rows) * 100, 1) if rows else None,
        "avg_excess": round(sum(ex) / len(ex), 2) if ex else None,
        "median_excess": ex[len(ex) // 2] if ex else None,
    }


def aggregate_calls(judged_calls, horizons=HORIZONS):
    """판정된 콜 → {summary, stocks}. 충돌 콜은 통계에서 제외한다.

    이름이 aggregate 가 아닌 이유는 hublib/aggregate.py 에 리포트 집계용
    aggregate() 가 이미 있어서다 — 같은 이름이 둘이면 import 마다 확인해야 한다.
    """
    scored = [c for c in judged_calls if not c.get("conflict")]

    summary = {}
    for h in horizons:
        key = f"h{h}"
        rows = [c[key] for c in scored if isinstance(c.get(key), dict)]
        stat = _roll(rows)
        stat["pending"] = sum(1 for c in scored
                              if c.get(key) is None and not c.get("error"))
        stat["failed"] = sum(1 for c in scored if c.get("error"))
        stat["bullish"] = sum(1 for c in scored if c.get("stance") == "bullish")
        stat["bearish"] = sum(1 for c in scored if c.get("stance") == "bearish")
        summary[key] = stat

    by_stock = {}
    for c in scored:
        by_stock.setdefault(c["stock"], []).append(c)

    stocks = []
    for name, cs in sorted(by_stock.items()):
        row = {"name": name, "market": cs[0].get("market", ""),
               "ticker": cs[0].get("ticker", ""), "bench": cs[0].get("bench_label", ""),
               "calls": len(cs), "low_sample": len(cs) < LOW_SAMPLE_MIN}
        for h in horizons:
            key = f"h{h}"
            row[key] = _roll([c[key] for c in cs if isinstance(c.get(key), dict)])
        stocks.append(row)
    # 표본 부족은 어떤 점수여도 하단 고정 — 얇은 표본이 랭킹 상위를 차지하지 못하게 한다
    stocks.sort(key=lambda s: (s["low_sample"], -s["calls"], s["name"]))

    return {"summary": summary, "stocks": stocks}
