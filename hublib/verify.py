# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 채팅 방향성 발화(콜)의 사후 성과 검증.

설계: docs/superpowers/specs/2026-08-17-call-verification-design.md

순수 함수(extract_calls·judge_call·aggregate_calls)와 네트워크(fetch_prices)를 분리한다.
순수 함수는 네트워크 없이 전량 테스트되고, 어떤 실패도 허브 빌드를 깨뜨리지 않는다.
"""
import datetime
import json
import os

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


CACHE_VERSION = 1          # 수집·저장 형식이 바뀌면 올린다 (전량 무효화)


def merge_points(old, new):
    """날짜 기준 병합 — 겹치면 새 값 채택, 오름차순 정렬."""
    m = dict(old)
    m.update(dict(new))
    return sorted(m.items())


class PriceCache:
    """종목별 일봉 증분 캐시. 손상·버전불일치 시 조용히 전량 재수집으로 폴백한다."""

    def __init__(self, path="build/price_cache.json"):
        self.path = path
        self.data = {}
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if raw.get("v") == CACHE_VERSION:
                self.data = raw.get("series") or {}
        except Exception:
            self.data = {}
        self.dirty = False

    def get(self, key):
        entry = self.data.get(key)
        return [(d, v) for d, v in entry["points"]] if entry else []

    def last(self, key):
        entry = self.data.get(key)
        return entry.get("last") if entry else None

    def put(self, key, points):
        self.data[key] = {"last": points[-1][0] if points else "",
                          "points": [[d, v] for d, v in points]}
        self.dirty = True

    def save(self):
        if not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"v": CACHE_VERSION, "series": self.data}, f, ensure_ascii=False)


COLD_START_PAD_DAYS = 14       # 첫 콜 이전 여유 — 연휴가 껴도 진입일을 찾는다
BENCH_TICKERS = {"KOSPI": ("KR", "KS11"), "KOSDAQ": ("KR", "KQ11"),
                 "US": ("US", "^IXIC")}


def _load_kr(ticker, start):
    """FinanceDataReader — KR 종목·지수. momentum.py 의 준비 함수를 재사용한다."""
    from hublib.momentum import _ensure_finance_datareader
    fdr = _ensure_finance_datareader()
    df = fdr.DataReader(ticker, start)
    if df is None or "Close" not in df:
        return []
    return [(i.date().isoformat(), float(v))
            for i, v in df["Close"].dropna().items() if float(v) > 0]


def _load_us(ticker, start):
    """yfinance — US 종목·나스닥 지수."""
    import yfinance as yf
    h = yf.Ticker(ticker).history(start=start, interval="1d")
    if h is None or "Close" not in h:
        return []
    return [(i.date().isoformat(), float(v))
            for i, v in h["Close"].dropna().items() if float(v) > 0]


DEFAULT_LOADERS = {"KR": _load_kr, "US": _load_us}


def _start_for(cache_last, first_call_date):
    if cache_last:
        return cache_last                      # 마지막 저장일부터 이어받는다
    d = datetime.date.fromisoformat(first_call_date) - datetime.timedelta(days=COLD_START_PAD_DAYS)
    return d.isoformat()


def fetch_prices(calls, cache, loaders=None):
    """콜 목록 → {'<market>:<ticker>': [(date, close)]}.

    종목당 1회만 요청하고, 캐시가 있으면 마지막 날부터 증분만 받는다.
    한 종목이 실패해도 빈 시계열로 격리하고 나머지는 계속한다.
    """
    loaders = loaders or DEFAULT_LOADERS
    wanted = {}
    for c in calls:
        key = f"{c['market']}:{c['ticker']}"
        prev = wanted.get(key)
        if prev is None or c["date"] < prev["first"]:
            wanted[key] = {"market": c["market"], "ticker": c["ticker"], "first": c["date"]}

    out = {}
    for key in sorted(wanted):
        w = wanted[key]
        loader = loaders.get(w["market"])
        old = cache.get(key)
        if loader is None:
            out[key] = old
            continue
        start = _start_for(cache.last(key), w["first"])
        try:
            fresh = loader(w["ticker"], start)
        except Exception as e:
            print(f"  ✗ 검증 가격 {key} 실패: {repr(e)[:100]}")
            out[key] = old
            continue
        points = merge_points(old, fresh)
        if points:
            cache.put(key, points)
        out[key] = points
    return out


def fetch_benchmarks(labels, first_date, cache, loaders=None):
    """{'KOSPI'|'KOSDAQ'|'US': [(date, close)]}. 종목과 같은 소스·같은 달력을 쓴다."""
    loaders = loaders or DEFAULT_LOADERS
    out = {}
    for label in sorted(set(labels)):
        market, ticker = BENCH_TICKERS[label]
        key = f"BENCH:{label}"
        old = cache.get(key)
        loader = loaders.get(market)
        if loader is None:
            out[label] = old
            continue
        try:
            fresh = loader(ticker, _start_for(cache.last(key), first_date))
        except Exception as e:
            print(f"  ✗ 검증 벤치마크 {label} 실패: {repr(e)[:100]}")
            out[label] = old
            continue
        points = merge_points(old, fresh)
        if points:
            cache.put(key, points)
        out[label] = points
    return out
