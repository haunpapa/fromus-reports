# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 지수 시계열·시장 모멘텀(yfinance/KRX)."""
import datetime, os, signal, subprocess, sys
from hublib.config import _fmt_kst, _today_kst


INDEX_TICKERS = [("코스피", "^KS11"), ("코스닥", "^KQ11"), ("나스닥", "^IXIC")]

def fetch_index_series(reports):
    try:
        import yfinance as yf
    except Exception as e:
        print(f"ℹ️ yfinance 미설치 — 리포트 추출 시계열 사용 ({repr(e)[:80]})")
        return {}
    dates = [r["sort_date"] for r in reports if r.get("sort_date") and r["sort_date"] <= "9999"]
    if not dates:
        return {}
    lo = min(datetime.date.fromisoformat(d) for d in dates) - datetime.timedelta(days=4)
    hi = max(datetime.date.fromisoformat(d) for d in dates) + datetime.timedelta(days=2)
    out = {}
    for name, tk in INDEX_TICKERS:
        try:
            h = yf.Ticker(tk).history(start=lo.isoformat(), end=hi.isoformat(), interval="1d")
            pts = []
            for idx, row in h.iterrows():
                v = float(row["Close"])
                if v != v or v <= 0:      # NaN/이상치 제외
                    continue
                pts.append({"date": idx.date().isoformat(), "value": round(v, 2), "change": ""})
            if len(pts) >= 2:
                out[name] = pts
                print(f"  ✓ 지수 {name}({tk}) {len(pts)}일 (야후)")
        except Exception as e:
            print(f"  ✗ 지수 {name}({tk}) 실패: {repr(e)[:100]}")
    return out

def _safe_float(v, default=None):
    try:
        if v is None:
            return default
        x = float(v)
        if x != x:
            return default
        return x
    except Exception:
        return default

def _pct(now, prev):
    now = _safe_float(now); prev = _safe_float(prev)
    if now is None or prev is None or prev <= 0:
        return None
    return (now / prev) - 1.0

def _clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

def _series_return(points, days=5):
    if not points or len(points) <= days:
        return 0.0
    vals = [_safe_float(p.get("value")) for p in points if _safe_float(p.get("value")) is not None]
    if len(vals) <= days or vals[-days-1] <= 0:
        return 0.0
    return vals[-1] / vals[-days-1] - 1.0

def _market_regime(index_series):
    kospi5 = _series_return(index_series.get("코스피"), 5)
    kosdaq5 = _series_return(index_series.get("코스닥"), 5)
    kospi20 = _series_return(index_series.get("코스피"), 20)
    kosdaq20 = _series_return(index_series.get("코스닥"), 20)
    avg5 = (kospi5 + kosdaq5) / 2.0
    avg20 = (kospi20 + kosdaq20) / 2.0
    score = _clamp(50 + avg5 * 300 + avg20 * 120)
    state = "risk_on" if score >= 58 else "risk_off" if score <= 42 else "neutral"
    return {"state": state, "score": round(score, 1), "kospi_5d": round(kospi5 * 100, 2),
            "kosdaq_5d": round(kosdaq5 * 100, 2), "avg_20d": round(avg20 * 100, 2)}

def _ensure_finance_datareader():
    try:
        import FinanceDataReader as fdr
        return fdr
    except Exception as first_error:
        if os.environ.get("MARKET_MOMENTUM_AUTO_INSTALL", "1") not in ("1", "true", "TRUE", "yes"):
            raise first_error
        try:
            print("ℹ️ FinanceDataReader 미설치 — 시장 모멘텀 수집을 위해 자동 설치를 시도합니다.")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "finance-datareader"])
            import FinanceDataReader as fdr
            return fdr
        except Exception as install_error:
            raise RuntimeError(f"FinanceDataReader 준비 실패: {install_error}") from first_error

def _load_krx_listing():
    try:
        fdr = _ensure_finance_datareader()
        df = fdr.StockListing('KRX')
        rows = []
        for _, r in df.iterrows():
            name = str(r.get('Name') or '').strip()
            code = str(r.get('Code') or '').strip().zfill(6)
            market = str(r.get('Market') or '').strip()
            amount = _safe_float(r.get('Amount'), 0) or 0
            if name and code and code != '000000':
                rows.append({
                    "name": name, "code": code, "market": market,
                    "close": _safe_float(r.get('Close')),
                    "change_1d": _safe_float(r.get('ChagesRatio'), _safe_float(r.get('ChangeRatio'), 0)) or 0,
                    "changes": _safe_float(r.get('Changes'), 0) or 0,
                    "volume": _safe_float(r.get('Volume'), 0) or 0,
                    "amount": amount,
                    "marcap": _safe_float(r.get('Marcap'), 0) or 0,
                })
        ranked = sorted([r for r in rows if r.get("amount")], key=lambda x: x["amount"])
        denom = max(1, len(ranked) - 1)
        for i, r in enumerate(ranked):
            r["amount_percentile"] = round(i / denom * 100, 1)
        return rows
    except Exception as e:
        print(f"ℹ️ KRX 종목 목록 조회 실패 — 시장 모멘텀 생략 ({repr(e)[:120]})")
        return []

def _build_ticker_map():
    rows = _load_krx_listing()
    name_map = {}
    for r in rows:
        name_map.setdefault(r["name"], r)
    # 지식허브의 약칭/정규화명과 KRX 공식명을 연결하는 최소 보정값
    manual = {
        "네이버": "NAVER",
        "카카오뱅크": "카카오뱅크",
        "LG엔솔": "LG에너지솔루션",
        "엘지에너지솔루션": "LG에너지솔루션",
        "두산에너빌리티": "두산에너빌리티",
        "현대차": "현대차",
        "기아": "기아",
    }
    for alias, official in manual.items():
        if official in name_map:
            name_map.setdefault(alias, name_map[official])
    return name_map

class _MarketDataTimeout(Exception):
    pass

def _snapshot_market_momentum(name, meta, index_series):
    """KRX 종목 목록이 제공하는 당일 가격·거래대금 스냅샷으로 빠르게 시장 분위기를 반영한다."""
    ret1 = (_safe_float(meta.get("change_1d"), 0) or 0) / 100.0
    market_key = "코스닥" if "KOSDAQ" in str(meta.get("market", "")).upper() else "코스피"
    market1 = _series_return(index_series.get(market_key), 1)
    rel1 = ret1 - market1
    amount_pct = _safe_float(meta.get("amount_percentile"), 50) or 50
    regime = _market_regime(index_series)
    regime_adj = 4 if regime["state"] == "risk_on" else -4 if regime["state"] == "risk_off" else 0
    # KRX snapshot is a same-day signal. Treat one-day weakness as cooling only when
    # the drop is meaningful versus the market, so a broad red day does not mark most
    # of the hub as cooled.
    score = 50 + ret1 * 360 + rel1 * 300 + (amount_pct - 50) * 0.10 + regime_adj
    score = _clamp(score)
    if ret1 >= 0.05 or (ret1 >= 0.03 and amount_pct >= 80) or score >= 76:
        state, label = "hot", "🔥 시장 과열"
    elif ret1 >= 0.012 or score >= 60:
        state, label = "warm", "↗ 시장 상승"
    elif (ret1 <= -0.07 and rel1 <= -0.03) or (ret1 <= -0.05 and rel1 <= -0.05) or (score <= 25 and rel1 <= -0.02):
        state, label = "cool", "❄ 시장 냉각"
    else:
        state, label = "flat", "· 시장 유지"
    reason = f"당일 {ret1*100:+.1f}%, 거래대금 분위 {amount_pct:.0f}, {market_key} 대비 {rel1*100:+.1f}%p"
    return {
        "state": state,
        "label": label,
        "score": round(score, 1),
        "reason": reason,
        "ticker": meta["code"],
        "market": meta.get("market", ""),
        "last_close": meta.get("close"),
        "ret_1d": round(ret1 * 100, 2),
        "ret_5d": 0,
        "ret_20d": 0,
        "volume_ratio_5d_20d": 1,
        "relative_5d": round(rel1 * 100, 2),
        "amount_percentile": amount_pct,
        "source": "FinanceDataReader/KRX snapshot",
        "updated": _fmt_kst("%Y-%m-%d"),
    }

def _stock_market_momentum(name, meta, index_series, start_date):
    def _timeout_handler(_signum, _frame):
        raise _MarketDataTimeout("timeout")
    try:
        fdr = _ensure_finance_datareader()
        import signal
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(int(os.environ.get("MARKET_MOMENTUM_STOCK_TIMEOUT", "7") or 7))
        try:
            df = fdr.DataReader(meta["code"], start_date)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    except Exception as e:
        return None, f"가격 데이터 실패: {repr(e)[:80]}"
    if df is None or len(df) < 22:
        return None, "가격 데이터 부족"
    df = df.dropna().sort_index()
    if len(df) < 22:
        return None, "가격 데이터 부족"

    close = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else None
    last = _safe_float(close.iloc[-1])
    ret1 = _pct(close.iloc[-1], close.iloc[-2]) if len(close) >= 2 else 0.0
    ret5 = _pct(close.iloc[-1], close.iloc[-6]) if len(close) >= 6 else 0.0
    ret20 = _pct(close.iloc[-1], close.iloc[-21]) if len(close) >= 21 else 0.0
    ret1 = ret1 if ret1 is not None else 0.0
    ret5 = ret5 if ret5 is not None else 0.0
    ret20 = ret20 if ret20 is not None else 0.0
    high20 = _safe_float(close.tail(20).max(), last) or last
    high_pos = (last / high20) if high20 and high20 > 0 else 1.0

    vol_ratio = 1.0
    if volume is not None and len(volume) >= 25:
        recent_vol = _safe_float(volume.tail(5).mean())
        base_vol = _safe_float(volume.iloc[-25:-5].mean())
        if recent_vol is not None and base_vol and base_vol > 0:
            vol_ratio = recent_vol / base_vol

    market_key = "코스닥" if "KOSDAQ" in str(meta.get("market", "")).upper() else "코스피"
    market5 = _series_return(index_series.get(market_key), 5)
    rel5 = ret5 - market5
    regime = _market_regime(index_series)
    regime_adj = 5 if regime["state"] == "risk_on" else -5 if regime["state"] == "risk_off" else 0

    score = 50
    score += ret5 * 220
    score += ret20 * 90
    score += rel5 * 180
    score += max(-10, min(16, (vol_ratio - 1.0) * 18))
    score += max(-8, min(8, (high_pos - 0.94) * 85))
    score += regime_adj
    score = _clamp(score)

    if ((ret5 >= 0.06 and vol_ratio >= 1.35 and rel5 >= 0.02) or
            (ret5 >= 0.12 and vol_ratio >= 1.05) or score >= 78):
        state, label = "hot", "🔥 시장 과열"
    elif score >= 58 and (ret5 >= 0.015 or ret20 >= 0.035 or rel5 >= 0.015):
        state, label = "warm", "↗ 시장 상승"
    elif score <= 38 and ((ret5 <= -0.045 and rel5 <= -0.02) or ret20 <= -0.08 or vol_ratio <= 0.55):
        state, label = "cool", "❄ 시장 냉각"
    else:
        state, label = "flat", "· 시장 유지"

    reason = f"5일 {ret5*100:+.1f}%, 20일 {ret20*100:+.1f}%, 거래량 {vol_ratio:.1f}배, {market_key} 대비 {rel5*100:+.1f}%p"
    return {
        "state": state,
        "label": label,
        "score": round(score, 1),
        "reason": reason,
        "ticker": meta["code"],
        "market": meta.get("market", ""),
        "last_close": round(last, 2) if last is not None else None,
        "ret_1d": round(ret1 * 100, 2),
        "ret_5d": round(ret5 * 100, 2),
        "ret_20d": round(ret20 * 100, 2),
        "volume_ratio_5d_20d": round(vol_ratio, 2),
        "relative_5d": round(rel5 * 100, 2),
        "high20_position": round(high_pos * 100, 1),
        "source": "FinanceDataReader/KRX",
        "updated": _fmt_kst("%Y-%m-%d"),
    }, None

def _aggregate_market_momentum(items, label="시장"):
    vals = [x.get("market_momentum") for x in items if x.get("market_momentum")]
    vals = [v for v in vals if isinstance(v, dict) and isinstance(v.get("score"), (int, float))]
    if not vals:
        return None
    avg = sum(v["score"] for v in vals) / len(vals)
    hot = sum(1 for v in vals if v.get("state") == "hot") / len(vals)
    warm = sum(1 for v in vals if v.get("state") == "warm") / len(vals)
    cool = sum(1 for v in vals if v.get("state") == "cool") / len(vals)
    avg_ret1 = sum(float(v.get("ret_1d", 0)) for v in vals) / len(vals)
    avg_ret5 = sum(float(v.get("ret_5d", 0)) for v in vals) / len(vals)
    avg_vol = sum(float(v.get("volume_ratio_5d_20d", 1)) for v in vals) / len(vals)
    avg_amount = sum(float(v.get("amount_percentile", 50)) for v in vals if v.get("amount_percentile") is not None) / max(1, sum(1 for v in vals if v.get("amount_percentile") is not None))
    if avg >= 72 or hot >= 0.35:
        state, text = "hot", "🔥 시장 과열"
    elif avg >= 57 or (hot + warm) >= 0.45:
        state, text = "warm", "↗ 시장 상승"
    elif avg <= 32 or cool >= 0.70:
        state, text = "cool", "❄ 시장 냉각"
    else:
        state, text = "flat", "· 시장 유지"
    basis = f"당일 평균 {avg_ret1:+.1f}%, 거래대금 분위 {avg_amount:.0f}" if abs(avg_ret5) < 0.01 else f"5일 평균 {avg_ret5:+.1f}%, 거래량 {avg_vol:.1f}배"
    return {
        "state": state,
        "label": text,
        "score": round(avg, 1),
        "reason": f"편입 {len(vals)}개 평균 점수 {avg:.1f}, {basis}, 과열 {hot*100:.0f}%/냉각 {cool*100:.0f}%",
        "covered": len(vals),
        "hot_ratio": round(hot * 100, 1),
        "warm_ratio": round(warm * 100, 1),
        "cool_ratio": round(cool * 100, 1),
        "source": "component-stocks",
        "updated": _fmt_kst("%Y-%m-%d"),
    }

def enrich_market_momentum(agg, index_series):
    stocks = agg.get("stocks") or []
    sectors = agg.get("sectors") or []
    if not stocks:
        return {"enabled": False, "reason": "no stocks"}
    ticker_map = _build_ticker_map()
    if not ticker_map:
        return {"enabled": False, "reason": "no ticker map"}

    start_date = (_today_kst() - datetime.timedelta(days=110)).isoformat()
    max_n = int(os.environ.get("MARKET_MOMENTUM_MAX_STOCKS", "140") or 140)
    history_n = int(os.environ.get("MARKET_MOMENTUM_HISTORY_STOCKS", "0") or 0)
    failures = []
    enriched = 0
    historical = 0
    stock_by_name = {s.get("name"): s for s in stocks}
    candidates = sorted(stocks, key=lambda s: (-(s.get("count") or 0), s.get("name") or ""))[:max_n]

    # 1단계: KRX 당일 스냅샷으로 넓은 커버리지 확보
    historical_candidates = []
    for s in candidates:
        name = s.get("name") or ""
        meta = ticker_map.get(name)
        if not meta:
            failures.append(f"{name}: ticker")
            continue
        s["market_momentum"] = _snapshot_market_momentum(name, meta, index_series)
        enriched += 1
        historical_candidates.append((s, meta))

    # 2단계: 상위 일부는 5일·20일 가격/거래량 히스토리로 정밀 보강
    # 기본값은 0으로 두어 GitHub Actions 정기 빌드 지연을 막고, 필요 시 환경변수로 켠다.
    for s, meta in historical_candidates[:history_n]:
        name = s.get("name") or ""
        mm, err = _stock_market_momentum(name, meta, index_series, start_date)
        if mm:
            s["market_momentum"] = mm
            historical += 1
            print(f"    · 시장 히스토리 {historical}/{history_n} {name} {mm['label']} ({mm['score']})")
        elif err:
            failures.append(f"{name}: {err}")

    for sec in sectors:
        members = [stock_by_name[n] for n in (sec.get("stocks") or []) if n in stock_by_name]
        mm = _aggregate_market_momentum(members, sec.get("theme") or "섹터")
        if mm:
            sec["market_momentum"] = mm

    meta = {
        "enabled": enriched > 0,
        "source": "FinanceDataReader/KRX snapshot + limited history + index series",
        "covered_stocks": enriched,
        "historical_stocks": historical,
        "candidate_stocks": len(candidates),
        "sector_covered": sum(1 for s in sectors if s.get("market_momentum")),
        "market_regime": _market_regime(index_series),
        "fallback": "시장 데이터가 없는 항목은 기존 14일 언급량 기준 사용",
        "updated": _fmt_kst(),
    }
    if failures:
        meta["unmatched_sample"] = failures[:20]
    print(f"  ✓ 시장 모멘텀 종목 {enriched}/{len(candidates)}개 · 섹터 {meta['sector_covered']}개")
    return meta
