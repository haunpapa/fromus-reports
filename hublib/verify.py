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

# ── 리포트 수급 코호트 ───────────────────────────────────────────
REPORT_COHORT_MAX_STOCKS = 120      # 언급 많은 순으로 가격 수집 상한 — CI 시간 보호


def _bench_for_market(market):
    return "KOSDAQ" if "KOSDAQ" in str(market or "").upper() else "KOSPI"


def extract_report_calls(stocks, ticker_map, max_stocks=REPORT_COHORT_MAX_STOCKS):
    """리포트 종목 집계(knowledge_base.stocks) → 수급 포착 언급을 강세 콜로. 네트워크 없음.

    티커는 ticker_map[name] = {"code","market"} (momentum._build_ticker_map). 없으면 no_ticker 로 제외.
    """
    ranked = sorted((s for s in (stocks or []) if any(m.get("source") == "수급" for m in s.get("mentions") or [])),
                    key=lambda s: (-(s.get("count") or 0), s.get("name") or ""))[:max_stocks]
    raw, no_ticker = [], 0
    for s in ranked:
        meta = (ticker_map or {}).get(s.get("name"))
        sup = [m for m in s.get("mentions") or [] if m.get("source") == "수급"]
        if not meta or not meta.get("code"):
            no_ticker += len(sup)
            continue
        for m in sup:
            raw.append({"stock": s["name"], "market": "KR", "ticker": meta["code"], "date": m.get("date") or "",
                        "stance": "bullish", "type": "supply", "bench_label": _bench_for_market(meta.get("market")),
                        "source": {"sharer": "리포트",
                                   "snippet": " · ".join(filter(None, [m.get("label"), m.get("annotation")]))[:SNIPPET_MAX],
                                   "id": m.get("id") or ""}})
    merged = {}
    for c in sorted(raw, key=lambda x: (x["date"], x["stock"])):
        key = (c["stock"], c["date"])
        if key in merged:
            merged[key]["sources"].append(c["source"])
            continue
        merged[key] = {**{k: v for k, v in c.items() if k != "source"},
                       "conflict": False, "sources": [c["source"]]}
    calls = sorted(merged.values(), key=lambda c: (c["date"], c["stock"]))
    stats = {"population": len(raw) + no_ticker, "no_ticker": no_ticker,
             "stocks": len({c["stock"] for c in calls}), "merged_from": len(raw),
             "duplicate": len(raw) - len(calls)}
    return calls, stats


def downsample_series(points, step=5, max_points=80):
    """[(date, close)] → [[date, close]] 거래일 step 간격 + 마지막 점. 종목 상세 주가 오버레이용(코어 크기 보호)."""
    if not points:
        return []
    picked = list(points[::max(1, step)])
    if picked[-1] != points[-1]:
        picked.append(points[-1])
    while len(picked) > max_points:
        picked = picked[::2] if picked[-1] == points[-1] else picked[::2] + [points[-1]]
    return [[d, v] for d, v in picked]


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

# 가격을 못 구한 진짜 장애. no_entry(콜 이후 거래일이 아직 없음)는 여기 없다 —
# 며칠 전 콜은 진입 자체가 미래라 '판정 대기'지 '수집 실패'가 아니다.
FAILED_ERRORS = ("no_price", "bad_entry")


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
                              if c.get(key) is None and c.get("error") not in FAILED_ERRORS)
        stat["failed"] = sum(1 for c in scored if c.get("error") in FAILED_ERRORS)
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


def aggregate_themes(judged_calls, stock_themes, horizons=HORIZONS):
    """콜 → 테마별 통계. stock_themes: {종목명: [테마,...]}. 충돌 콜 제외. 콜 수 내림차순."""
    by_theme = {}
    for c in judged_calls:
        if c.get("conflict"):
            continue
        for th in stock_themes.get(c["stock"]) or []:
            by_theme.setdefault(th, []).append(c)
    out = []
    for th, cs in by_theme.items():
        row = {"theme": th, "cohort": "report", "calls": len(cs)}
        for h in horizons:
            key = f"h{h}"
            row[key] = _roll([c[key] for c in cs if isinstance(c.get(key), dict)])
        out.append(row)
    return sorted(out, key=lambda r: (-r["calls"], r["theme"]))


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


def _krx_market_lookup():
    """코드 → 'KOSPI'|'KOSDAQ'. 실패하면 전부 코스피로 폴백한다.

    이름이 아니라 코드로 조회한다 — '네이버'/'NAVER' 같은 표기 차이에 걸리지 않는다.
    """
    try:
        from hublib.momentum import _load_krx_listing
        table = {r["code"]: ("KOSDAQ" if "KOSDAQ" in str(r.get("market", "")).upper()
                             else "KOSPI") for r in _load_krx_listing()}
    except Exception as e:
        print(f"ℹ️ KRX 시장 구분 조회 실패 — 전부 코스피로 간주 ({repr(e)[:80]})")
        table = {}
    return lambda code: table.get(code, "KOSPI")


def _bench_label(call, market_of):
    return "US" if call["market"] == "US" else market_of(call["ticker"])


def _judge_all(calls, prices, benches, horizons):
    out = []
    for c in calls:
        series = prices.get(f"{c['market']}:{c['ticker']}") or []
        bench = benches.get(c["bench_label"]) or []
        out.append({**c, **judge_call(c, series, bench, horizons=horizons)})
    return out


def _with_series(stock_rows, prices):
    return [{**row, "series": downsample_series(prices.get(f"{row['market']}:{row['ticker']}") or [])}
            for row in stock_rows]


def _report_cohort(rep_calls, rep_stats, report_stocks, prices, benches, horizons, generated):
    """리포트 수급 코호트 블록(verify.report) + 테마 집계(verify.themes)."""
    rj = _judge_all(rep_calls, prices, benches, horizons)
    ragg = aggregate_calls(rj, horizons=horizons)
    themes = {s["name"]: list(s.get("themes") or []) for s in report_stocks}
    block = {
        "enabled": True,
        "meta": {"cohort": "report", "calls": len(rj), "stocks": len(ragg["stocks"]),
                 "population": rep_stats["population"], "horizons": list(horizons),
                 "primary": PRIMARY_HORIZON, "entry": "next_trading_close", "unit": "trading_days",
                 "excluded": {"no_ticker": rep_stats["no_ticker"], "duplicate": rep_stats["duplicate"]},
                 "generated": generated},
        "summary": ragg["summary"],
        "stocks": _with_series(ragg["stocks"], prices),
        "calls": rj,
    }
    return block, aggregate_themes(rj, themes, horizons=horizons)


def build_verify(chat_kb=None, cache_path="build/price_cache.json", loaders=None, market_of=None,
                 horizons=HORIZONS, report_stocks=None, ticker_map=None):
    """검증 레이어 전체를 조립한다. chat 데이터가 없으면 None.

    report_stocks 가 주어지면 리포트 수급 코호트(verify.report)·테마 집계(verify.themes)도 만든다.
    두 코호트는 가격 캐시·벤치마크만 공유하고 통계는 합치지 않는다.
    예상 못 한 예외는 {'enabled': False, 'reason': ...} — 검증 때문에 허브 빌드가 실패해선 안 된다.
    """
    if not chat_kb:
        return None
    try:
        from hublib.config import _fmt_kst
        calls, stats = extract_calls(chat_kb)
        if not calls:
            return {"enabled": False, "reason": "no calls"}

        market_of = market_of or _krx_market_lookup()
        for c in calls:
            c["bench_label"] = _bench_label(c, market_of)

        rep_calls, rep_stats = [], {}
        if report_stocks:
            if ticker_map is None:
                from hublib.momentum import _build_ticker_map
                ticker_map = _build_ticker_map()
            rep_calls, rep_stats = extract_report_calls(report_stocks, ticker_map)

        cache = PriceCache(cache_path)
        all_calls = calls + rep_calls
        first = min(c["date"] for c in all_calls)
        prices = fetch_prices(all_calls, cache, loaders=loaders)
        benches = fetch_benchmarks([c["bench_label"] for c in all_calls], first, cache, loaders=loaders)
        cache.save()

        judged = _judge_all(calls, prices, benches, horizons)
        agg = aggregate_calls(judged, horizons=horizons)
        scored = [c for c in judged if not c["conflict"]]
        generated = _fmt_kst()
        out = {
            "enabled": True,
            "meta": {
                "cohort": "core", "calls": len(scored), "merged_from": stats["core"],
                "stocks": len(agg["stocks"]), "population": stats["population"],
                "horizons": list(horizons), "primary": PRIMARY_HORIZON,
                "entry": "next_trading_close", "unit": "trading_days",
                "excluded": {k: stats[k] for k in
                             ("bot", "asset", "bot_and_asset", "duplicate", "conflict")},
                "generated": generated,
            },
            "summary": agg["summary"],
            "stocks": _with_series(agg["stocks"], prices),
            "calls": judged,
        }
        if rep_calls:
            out["report"], out["themes"] = _report_cohort(
                rep_calls, rep_stats, report_stocks, prices, benches, horizons, generated)
        elif report_stocks:
            out["report"] = {"enabled": False, "reason": "no supply mentions with ticker",
                             "meta": {"cohort": "report", "excluded": rep_stats}}
        return out
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"enabled": False, "reason": repr(e)[:200]}
