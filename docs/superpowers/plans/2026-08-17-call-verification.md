# 성과 검증 레이어 (Call Verification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카카오톡 채팅에서 방향(강세/약세)을 밝힌 발화를 발화 이후 실제 주가와 대조해, 종목 단위 적중률·초과수익을 산출하고 허브에 전용 `검증` 탭으로 노출한다.

**Architecture:** `hublib/verify.py` 단일 모듈에 **순수 함수 3개**(`extract_calls`/`judge_call`/`aggregate_calls`)와 **네트워크 1개**(`fetch_prices`)를 분리해 담는다. 순수 함수는 네트워크 없이 전량 테스트하고, 수집은 loader 주입으로 테스트한다. `collect` 단계에서 `knowledge_base.json["verify"]` 를 만들고, 프론트는 기존 무의존성 원칙대로 순수 JS/CSS로 렌더한다. 어떤 실패도 허브 빌드를 깨뜨리지 않는다.

**Tech Stack:** Python 3.11 · FinanceDataReader(KR) · yfinance(US) · pytest · 순수 JS/CSS (외부 라이브러리 없음)

**Spec:** [docs/superpowers/specs/2026-08-17-call-verification-design.md](../specs/2026-08-17-call-verification-design.md)

---

## 파일 구조

| 파일 | 상태 | 책임 |
|---|---|---|
| `hublib/verify.py` | 신규 (~330줄) | 콜 추출·판정·집계·가격수집·캐시. 이 기능의 전부 |
| `tests/test_verify.py` | 신규 (~230줄) | 순수 함수 전량 + loader 주입 수집 테스트 |
| `tests/fixtures/chat_kb_mini.json` | 신규 | 추출 규칙 4가지를 최소 크기로 자극하는 픽스처 |
| `hublib/render.py` | 수정 | `collect()` 에 verify 배선 (약 30줄) |
| `tests/test_phases.py` | 수정 | 하위 프로세스에 `VERIFY_SKIP=1` — 2단계 빌드 테스트를 네트워크에서 격리 |
| `hub_template.html` | 수정 | 검증 탭 CSS·마크업·렌더 함수 + 종목 카드 칩 |
| `.github/workflows/build.yml` | 수정 | `build/price_cache.json` 캐시 스텝 |
| `.gitignore` | 수정 | `build/price_cache.json` 추가 |
| `README.md` | 수정 | 스키마 표에 `verify` 행 |

`verify.py` 를 더 쪼개지 않는 이유: 이 레포의 `hublib/*.py` 는 모듈당 하나의 파이프라인 단계를 담고(`parse`/`aggregate`/`momentum`), 가장 큰 `momentum.py` 가 400줄이다. 330줄은 그 관례 안에 있고, 4개 함수가 하나의 데이터 흐름을 이루므로 분리하면 오히려 추적이 어려워진다.

## 사전 확인

- [ ] **작업 브랜치 생성**

```bash
git checkout -b feat/call-verification && git status --short
```

- [ ] **기존 테스트가 통과하는 상태에서 시작하는지 확인**

```bash
python -m pytest tests/ generator/test_parse.py -q
```

기대: 전량 PASS. 실패가 있으면 여기서 멈추고 보고할 것.

---

## Task 1: 콜 추출 (`extract_calls`) — 순수 함수

**Files:**
- Create: `tests/fixtures/chat_kb_mini.json`
- Create: `tests/test_verify.py`
- Create: `hublib/verify.py`

`chat_kb.json` 의 `stocks[].mentions` 에서 방향성 발화만 뽑아 **봇 제외 → 무벤치마크(ASSET) 제외 → 중복 병합 → 충돌 표시** 4단계를 거친다. 네트워크·파일 IO 없음.

- [ ] **Step 1: 픽스처 작성**

`tests/fixtures/chat_kb_mini.json` — 4가지 규칙을 각각 자극하는 최소 데이터:

```json
{
  "build": {"generated_from": "kakao_chat"},
  "stocks": {
    "삼성전자": {
      "name": "삼성전자", "market": "KR", "ticker": "005930",
      "mentions": [
        {"date": "2026-05-04", "sharer": "가", "stance": "bullish", "type": "view", "snippet": "A"},
        {"date": "2026-05-04", "sharer": "나", "stance": "bullish", "type": "position", "snippet": "B"},
        {"date": "2026-05-11", "sharer": "가", "stance": "bullish", "type": "view", "snippet": "C"},
        {"date": "2026-05-11", "sharer": "다", "stance": "bearish", "type": "view", "snippet": "D"},
        {"date": "2026-05-12", "sharer": "가", "stance": "neutral", "type": "view", "snippet": "E"},
        {"date": "2026-05-13", "sharer": "김병철(봇)", "stance": "bullish", "type": "view", "snippet": "F"}
      ]
    },
    "비트코인": {
      "name": "비트코인", "market": "ASSET", "ticker": "BTC",
      "mentions": [
        {"date": "2026-05-04", "sharer": "가", "stance": "bullish", "type": "view", "snippet": "G"},
        {"date": "2026-05-05", "sharer": "김병철(봇)", "stance": "bearish", "type": "view", "snippet": "H"}
      ]
    },
    "무티커": {
      "name": "무티커", "market": "KR", "ticker": "",
      "mentions": [
        {"date": "2026-05-04", "sharer": "가", "stance": "bullish", "type": "view", "snippet": "I"}
      ]
    }
  }
}
```

이 픽스처가 만드는 기대값(계획 검산용):
- 방향성 발화 중 티커 보유 = 7건 (E는 neutral 제외, I는 티커 없어 제외)
- 봇 2(F·H) · ASSET 2(G·H) · 교집합 1(H)
- 핵심(core) 4건 (A·B·C·D) → 중복 병합 후 3콜 (A+B 병합) → 중복분 1
- 충돌 2콜 (05-11 강세 C, 약세 D)

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_verify.py`:

```python
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
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_verify.py -q
```

기대: 4건 모두 FAIL — `ModuleNotFoundError: No module named 'hublib.verify'`

- [ ] **Step 4: 최소 구현**

`hublib/verify.py` 생성:

```python
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
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_verify.py -q
```

기대: `4 passed`

- [ ] **Step 6: 실제 데이터로 스펙 수치 검산 (일회성, 커밋 안 함)**

```bash
python -c "
import json
from hublib.verify import extract_calls
calls, stats = extract_calls(json.load(open('chat_kb.json')))
print(stats); print('final judged candidates:', sum(1 for c in calls if not c['conflict']))
"
```

기대(2026-08-17 스냅샷): `population 329 · bot 138 · asset 52 · bot_and_asset 24 · core 163 · duplicate 13 · conflict 4`, final `146`.
**수치가 다르면 chat_kb.json 이 갱신된 것이다.** 스펙 §3은 스냅샷이므로 불일치 자체는 결함이 아니다 — 다만 `bot+asset-교집합+core == population` 검산은 반드시 맞아야 하고, 틀리면 멈추고 보고할 것.

- [ ] **Step 7: 커밋**

```bash
git add hublib/verify.py tests/test_verify.py tests/fixtures/chat_kb_mini.json
git commit -m "feat: 콜 검증 — 방향성 발화 추출(봇·ASSET 제외, 중복 병합, 충돌 표시)"
```

---

## Task 2: 콜 판정 (`judge_call`) — 순수 함수

**Files:**
- Modify: `hublib/verify.py`
- Modify: `tests/test_verify.py`

발화 **다음 거래일 종가**로 진입해 **거래일** h개 뒤 종가로 청산하고, 같은 시장 지수 대비 초과수익과 적중 여부를 낸다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_verify.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_verify.py -q -k "entry or horizon or excess or bearish or benchmark or price or pending or immature"
```

기대: 전부 FAIL — `cannot import name 'judge_call'`

- [ ] **Step 3: 구현**

`hublib/verify.py` 에 추가:

```python
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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_verify.py -q
```

기대: `16 passed`

- [ ] **Step 5: 커밋**

```bash
git add hublib/verify.py tests/test_verify.py
git commit -m "feat: 콜 판정 — 다음 거래일 진입, 거래일 구간, 지수 대비 초과수익"
```

---

## Task 3: 집계 (`aggregate_calls`) — 순수 함수

**Files:**
- Modify: `hublib/verify.py`
- Modify: `tests/test_verify.py`

판정 결과를 전체 요약과 종목별 행으로 접는다. 이름이 `aggregate` 가 아닌 이유는 `hublib/aggregate.py` 에 이미 리포트 집계용 `aggregate()` 가 있어서다 — 같은 이름이 두 개면 import 를 읽을 때마다 어느 쪽인지 확인해야 한다. **충돌·판정대기·수집실패는 적중률 분모에서 뺀다.**

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_verify.py -q -k aggregate
```

기대: 4건 FAIL — `cannot import name 'aggregate_calls'`

- [ ] **Step 3: 구현**

```python
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
    """판정된 콜 → {summary, stocks}. 충돌 콜은 통계에서 제외한다."""
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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_verify.py -q
```

기대: `20 passed`

- [ ] **Step 5: 커밋**

```bash
git add hublib/verify.py tests/test_verify.py
git commit -m "feat: 콜 집계 — 충돌·대기·실패 분모 제외 + 표본부족 하단 고정"
```

---

## Task 4: 가격 캐시 (`PriceCache`)

**Files:**
- Modify: `hublib/verify.py`
- Modify: `tests/test_verify.py`
- Modify: `.gitignore`

`hublib/cache.py:ParseCache` 와 같은 패턴. 다른 점은 **증분 이어붙이기**(가격은 매일 자란다)와 **버전 무효화**다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_verify.py -q -k "merge_points or price_cache"
```

기대: 5건 FAIL

- [ ] **Step 3: 구현**

`hublib/verify.py` 상단 import 에 `import json, os` 추가하고:

```python
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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_verify.py -q
```

기대: `25 passed`

- [ ] **Step 5: `.gitignore` 에 캐시 추가**

`build/parse_cache.json` 줄 바로 아래에 추가:

```
build/price_cache.json
```

- [ ] **Step 6: 커밋**

```bash
git add hublib/verify.py tests/test_verify.py .gitignore
git commit -m "feat: 가격 증분 캐시 — 버전 무효화·손상 폴백"
```

---

## Task 5: 가격 수집 (`fetch_prices`) — 네트워크

**Files:**
- Modify: `hublib/verify.py`
- Modify: `tests/test_verify.py`

**KR은 fdr, US는 yfinance.** 같은 시장의 종목과 벤치마크를 같은 소스에서 받아 거래일 달력을 맞춘다. 테스트는 **loader 주입**으로 네트워크 없이 돈다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_verify.py -q -k fetch_prices
```

기대: 4건 FAIL

- [ ] **Step 3: 구현**

```python
import datetime

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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_verify.py -q
```

기대: `29 passed`

- [ ] **Step 5: 커밋**

```bash
git add hublib/verify.py tests/test_verify.py
git commit -m "feat: 검증용 가격 수집 — 종목당 1회·증분·실패 격리"
```

---

## Task 6: 조립 (`build_verify`) + 빌더 배선

**Files:**
- Modify: `hublib/verify.py`
- Modify: `tests/test_verify.py`
- Modify: `hublib/render.py`
- Modify: `tests/test_phases.py`

코스피/코스닥 판별을 붙이고 전 단계를 조립한다. **어떤 예외도 허브 빌드를 깨지 않는다.**

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_verify.py -q -k build_verify
```

기대: 4건 FAIL

- [ ] **Step 3: 구현**

```python
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


def build_verify(chat_kb=None, cache_path="build/price_cache.json",
                 loaders=None, market_of=None, horizons=HORIZONS):
    """검증 레이어 전체를 조립한다. chat 데이터가 없으면 None.

    예상 못 한 예외는 {'enabled': False, 'reason': ...} 로 바꿔 반환한다 —
    검증 레이어 때문에 허브 빌드가 실패해선 안 된다.
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

        cache = PriceCache(cache_path)
        first = min(c["date"] for c in calls)
        prices = fetch_prices(calls, cache, loaders=loaders)
        benches = fetch_benchmarks([c["bench_label"] for c in calls], first, cache,
                                   loaders=loaders)
        cache.save()

        judged = []
        for c in calls:
            series = prices.get(f"{c['market']}:{c['ticker']}") or []
            bench = benches.get(c["bench_label"]) or []
            judged.append({**c, **judge_call(c, series, bench, horizons=horizons)})

        agg = aggregate_calls(judged, horizons=horizons)
        scored = [c for c in judged if not c["conflict"]]
        return {
            "enabled": True,
            "meta": {
                "cohort": "core", "calls": len(scored), "merged_from": stats["core"],
                "stocks": len(agg["stocks"]), "population": stats["population"],
                "horizons": list(horizons), "primary": PRIMARY_HORIZON,
                "entry": "next_trading_close", "unit": "trading_days",
                "excluded": {k: stats[k] for k in
                             ("bot", "asset", "bot_and_asset", "duplicate", "conflict")},
                "generated": _fmt_kst(),
            },
            "summary": agg["summary"],
            "stocks": agg["stocks"],
            "calls": judged,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"enabled": False, "reason": repr(e)[:200]}
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_verify.py -q
```

기대: `33 passed`

- [ ] **Step 5: `hublib/render.py` 배선**

`collect()` 안에서 `data = _merge_chat_kb(data)` 바로 다음 줄에 삽입:

```python
    data["verify"] = _build_verify_safe(data)
```

그리고 `_merge_chat_kb` 함수 정의 바로 아래에 헬퍼를 추가한다. **`data["chat"]` 이 아니라 원본 `chat_kb.json` 을 직접 읽는다** — `merge_hub.merge()` 가 구조를 재가공하므로 원본 스키마에만 의존해야 병합 로직 변경에 흔들리지 않는다:

```python
def _build_verify_safe(data):
    """chat_kb.json 원본으로 검증 레이어를 만든다. 실패해도 빌드는 계속된다.

    _merge_chat_kb 와 달리 **cwd 만 본다**(리포 루트 폴백 없음). 검증은 네트워크를
    타므로, tmp 폴더에서 도는 tests/test_phases.py 가 리포 루트의 실제 chat_kb.json 을
    집어 시세를 받아버리면 안 된다. CI 는 리포 루트에서 실행하므로 cwd 만으로 충분하다.
    """
    import json, sys
    if os.environ.get("VERIFY_SKIP") in ("1", "true", "TRUE", "yes"):
        print("ℹ️ VERIFY_SKIP -- 검증 레이어 생략")
        return None
    if not os.path.exists("chat_kb.json"):
        return None
    try:
        from hublib.verify import build_verify
        with open("chat_kb.json", encoding="utf-8") as f:
            chat = json.load(f)
        out = build_verify(chat_kb=chat)
        if out and out.get("enabled"):
            m = out["meta"]
            print(f"검증 레이어 -- {m['calls']}콜 / {m['stocks']}종목")
        elif out:
            print(f"ℹ️ 검증 레이어 비활성 -- {out.get('reason')}")
        return out
    except Exception as e:
        print(f"[WARN] 검증 레이어 생략 -- {e}", file=sys.stderr)
        data.setdefault("build", {})["verify_error"] = str(e)
        return None
```

> **이건 실제 사고를 막는 장치다.** `_merge_chat_kb` 는 `("chat_kb.json", repo_root/"chat_kb.json")` 순으로 찾는데, 같은 패턴을 verify에 쓰면 `tests/test_phases.py` 가 tmp 폴더에서 `build_hub.py` 를 돌릴 때 **리포 루트의 진짜 `chat_kb.json` 을 읽어 35종목 시세를 네트워크로 받는다.** CI 테스트가 느려지고 외부 API에 의존하게 된다. cwd-only + 환경변수 킬스위치 두 겹으로 막는다.

- [ ] **Step 5b: `tests/test_phases.py` 에 킬스위치 적용**

`_run()` 이 하위 프로세스를 띄울 때 `VERIFY_SKIP=1` 을 넣는다. 검증 레이어는 `tests/test_verify.py` 가 전담하므로, 2단계 빌드 테스트는 네트워크와 무관해야 한다:

```python
def _run(args, cwd):
    env = {**os.environ, "VERIFY_SKIP": "1"}
    return subprocess.run([sys.executable, os.path.join(ROOT, "build_hub.py")] + args,
                          cwd=cwd, capture_output=True, text=True, timeout=300, env=env)
```

- [ ] **Step 6: 배선 확인 — 픽스처 빌드가 여전히 통과하는지**

```bash
time python -m pytest tests/ generator/test_parse.py -q
```

기대: 전량 PASS (33 + 기존).

**네트워크를 타지 않았는지 반드시 확인한다** — 이 스텝의 진짜 목적이다:

```bash
python -m pytest tests/test_phases.py -q -s 2>&1 | grep -c "검증 레이어"
```

기대: `0`. 1 이상이면 `_build_verify_safe` 가 tmp 폴더 밖의 `chat_kb.json` 을 집었거나 `VERIFY_SKIP` 이 하위 프로세스에 전달되지 않은 것이다. 그대로 두면 CI 테스트가 매번 35종목 시세를 받는다. 멈추고 Step 5·5b를 다시 확인할 것.

`test_phases` 소요 시간이 이전 대비 눈에 띄게 늘었다면(수 초 → 수십 초) 같은 문제다.

- [ ] **Step 7: 실제 데이터로 1회 수집 (네트워크 필요, 산출물 커밋 안 함)**

```bash
python -c "
import json
from hublib.verify import build_verify
v = build_verify(chat_kb=json.load(open('chat_kb.json')))
print(json.dumps(v['meta'], ensure_ascii=False, indent=1))
print(json.dumps(v['summary']['h20'], ensure_ascii=False, indent=1))
print('상위:', [(s['name'], s['calls'], s['h20']['hit_rate']) for s in v['stocks'][:7]])
print('KB 증가분(KB):', len(json.dumps(v, ensure_ascii=False))//1024)
"
```

확인 사항:
- `meta.calls` 가 §3.1 기대값 근처인가 (스냅샷 시점 146)
- `summary.h20.judged + pending + failed == meta.calls` 인가
- `failed` 가 0에 가까운가 — 5건 넘으면 어떤 티커가 실패했는지 로그로 확인하고 보고할 것
- 크기가 200KB 이하인가

- [ ] **Step 8: 커밋**

```bash
git add hublib/verify.py hublib/render.py tests/test_verify.py
git commit -m "feat: 검증 레이어 조립 + collect 배선 (실패는 빌드에 영향 없음)"
```

---

## Task 7: CI 캐시

**Files:**
- Modify: `.github/workflows/build.yml`

- [ ] **Step 1: 캐시 스텝 추가**

`Restore parse cache` 스텝 **바로 아래**에 삽입:

```yaml
      - name: Restore price cache (검증 레이어)
        uses: actions/cache@v4
        with:
          path: build/price_cache.json
          key: price-cache-v1-${{ github.run_id }}
          restore-keys: price-cache-v1-
```

가격 데이터는 매일 자라므로 parse cache 처럼 내용 해시를 키로 쓸 수 없다. 매 실행마다 새로 저장하고 가장 최근 것을 복원하는 패턴을 쓴다. `v1` 은 `CACHE_VERSION` 과 함께 올린다.

- [ ] **Step 2: 워크플로 문법 검증**

```bash
grep -n "name: Restore\|name: Build index\|price_cache\|parse-cache\|price-cache" .github/workflows/build.yml
```

기대 출력 순서: `Restore parse cache` → `parse-cache-…` → `Restore price cache (검증 레이어)` → `build/price_cache.json` → `price-cache-v1-…` → `Build index`.

PyYAML 로 파싱 검증하지 않는 이유: 이 레포는 `requirements-dev.txt` 에 pytest만 두고 있어 PyYAML 이 없을 수 있다. 스텝 하나 추가에 새 의존성을 끌어들이지 않는다. 문법 오류는 push 시 GitHub 이 즉시 잡아준다.

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/build.yml
git commit -m "ci: 검증 레이어 가격 캐시 복원 스텝"
```

---

## Task 8: 검증 탭 UI

**Files:**
- Modify: `hub_template.html`

이 레포의 허브 셸은 **외부 JS 라이브러리를 쓰지 않는다.** 순수 JS/CSS로 작성하고 기존 클래스 관례(`sec-title`/`sec-sub`/`pill`/`mention`)를 따른다.

- [ ] **Step 1: CSS 추가**

`.strow-detail` 규칙(현재 `:292` 부근) 다음에 삽입:

```css
.v-toggle{display:flex;gap:6px;margin:10px 0 14px;}
.v-toggle button{border:1px solid var(--border);background:var(--surface);color:var(--text-2);
  font-size:12px;font-weight:600;border-radius:999px;padding:5px 15px;cursor:pointer;}
.v-toggle button.on{border-color:var(--gold-border);background:var(--gold-bg);color:var(--gold);}
.v-score{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px;}
.v-cell{border:1px solid var(--border);border-radius:12px;padding:13px 15px;background:var(--surface);}
.v-cell.vh-warn{border-color:#f0c987;background:#fffaf0;}
.v-num{font-size:21px;font-weight:700;font-family:'JetBrains Mono',monospace;}
.v-lbl{font-size:11.5px;color:var(--text-3);margin-top:3px;}
.v-note{font-size:11.5px;color:#b45309;background:#fffaf0;border:1px solid #f0c987;
  border-radius:9px;padding:9px 13px;margin-bottom:14px;line-height:1.65;}
.v-row{border-bottom:1px solid var(--border);}
.v-row.low{opacity:.55;}
.v-row-head{display:flex;align-items:center;gap:9px;padding:11px 5px;cursor:pointer;font-size:13px;}
.v-name{font-weight:600;min-width:104px;}
.v-mini{font-size:11.5px;color:var(--text-3);font-family:'JetBrains Mono',monospace;}
.v-hr,.v-ex{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:12.5px;font-weight:600;}
.v-ex{min-width:66px;text-align:right;}
.v-row-detail{display:none;padding:2px 5px 12px;}
.v-row-detail.open{display:block;}
.v-badge{font-size:10.5px;font-weight:700;border-radius:999px;padding:2px 8px;}
.v-badge.hit{background:#e8f6ec;color:#16a34a;}
.v-badge.miss{background:#fdeceb;color:#dc2626;}
.v-badge.pend{background:var(--surface-2,#f3f0ea);color:var(--text-3);}
.v-badge.conf{background:#f5f3ff;color:#7c3aed;}
.v-badge.low{background:var(--surface-2,#f3f0ea);color:var(--text-3);}
.v-dir{font-size:11px;font-weight:700;}
.v-dir.bullish{color:#dc2626;} .v-dir.bearish{color:#2563eb;}
.v-fold{font-size:12px;color:#16a34a;cursor:pointer;padding:11px 5px;}
@media(max-width:760px){.v-score{grid-template-columns:repeat(2,1fr);}
  .v-name{min-width:74px;} .v-row-head{flex-wrap:wrap;gap:6px;}}
```

- [ ] **Step 2: 탭 버튼 2곳 추가**

`hub_template.html:562` 와 `:617` 의 `data-tab="chat"` 버튼 **바로 앞**에 각각 삽입 (사이드 내비 + 하단 내비):

```html
        <button class="tab" data-tab="verify" style="display:none"><span class="t-ico">✅</span>검증</button>
```

기본 `display:none` 이고 데이터가 있을 때만 JS가 켠다. (기존 `data-tab="chat"` 버튼은 이를 되돌리는 코드가 없어 영구 비활성 상태다 — 같은 실수를 반복하지 않도록 Step 5에서 노출을 명시 구현하고 Step 7에서 눈으로 확인한다.)

- [ ] **Step 3: 뷰 컨테이너 추가**

`:597` 의 `<div class="view" id="view-glossary"></div>` **바로 앞**에 삽입:

```html
      <div class="view" id="view-verify"></div>
```

- [ ] **Step 4: `TABS` 배열에 등록**

`:681` 을 수정:

```js
const TABS=['home','sectors','stocks','analytics','trade','strategy','glossary','graph','chat','verify'];
```

- [ ] **Step 5: 렌더 함수 추가**

`/* ───────── STRATEGY ───────── */` 주석 **바로 앞**에 블록 전체를 삽입:

```js
/* ───────── VERIFY ───────── */
let vHorizon = 20;
let vShowLow = false;
const vPct = x => x==null ? '—' : (x>0?'+':'')+x.toFixed(1)+'%p';

function verifyOn(){ return !!(D.verify && D.verify.enabled); }

function renderVerify(){
  const host=$('#view-verify'); if(!host) return;
  $$('.tab[data-tab="verify"]').forEach(b=>{ b.style.display = verifyOn()?'':'none'; });
  if(!verifyOn()){ host.innerHTML=''; return; }
  const V=D.verify, m=V.meta||{}, key='h'+vHorizon, s=(V.summary||{})[key]||{};
  const toggle=(m.horizons||[5,20,60]).map(h=>
    `<button data-vh="${h}" class="${h===vHorizon?'on':''}">${h}일</button>`).join('');
  const warn=(s.pending||0)>(s.judged||0)?' vh-warn':'';
  host.innerHTML=`
    <div class="sec-title">✅ 콜 검증 <span class="count-badge">${m.calls||0}</span></div>
    <div class="sec-sub">채팅에서 방향을 밝힌 발화를 이후 실제 주가와 대조했다 —
      발화 다음 거래일 종가 진입 · 거래일 기준 구간 · 지수 대비 초과수익</div>
    <div class="v-toggle" id="vHorizon">${toggle}</div>
    <div class="v-score">
      <div class="v-cell"><div class="v-num">${s.hit_rate==null?'—':s.hit_rate.toFixed(1)+'%'}</div>
        <div class="v-lbl">적중률 (${s.hit||0}/${s.judged||0})</div></div>
      <div class="v-cell"><div class="v-num">${vPct(s.avg_excess)}</div>
        <div class="v-lbl">평균 초과수익</div></div>
      <div class="v-cell${warn}"><div class="v-num">${s.pending||0}</div>
        <div class="v-lbl">판정 대기</div></div>
      <div class="v-cell"><div class="v-num">${s.bullish||0} · ${s.bearish||0}</div>
        <div class="v-lbl">강세 · 약세</div></div>
    </div>
    <div class="v-note">강세 ${s.bullish||0}건 대 약세 ${s.bearish||0}건으로 강세 편향이 크다 —
      사실상 강세 의견의 초과수익 검증이다. 표본이 얇은 종목은 아래로 내렸다. 투자 권유가 아니다.</div>
    <div id="vRank"></div>`;
  $('#vHorizon').addEventListener('click',e=>{const b=e.target.closest('button');
    if(b){vHorizon=+b.dataset.vh;renderVerify();}});
  drawVerifyRank();
}

function drawVerifyRank(){
  const key='h'+vHorizon, all=(D.verify.stocks||[]);
  const main=all.filter(s=>!s.low_sample), low=all.filter(s=>s.low_sample);
  const lowCalls=low.reduce((a,s)=>a+(s.calls||0),0);
  $('#vRank').innerHTML =
    vRankRows(main,key) +
    (low.length?`<div class="v-fold" id="vFold">${vShowLow?'－':'＋'} 표본 부족 ${low.length}종목 (${lowCalls}콜)</div>
      ${vShowLow?vRankRows(low,key):''}`:'');
  const f=$('#vFold'); if(f)f.addEventListener('click',()=>{vShowLow=!vShowLow;drawVerifyRank();});
  $('#vRank').addEventListener('click',e=>{
    const h=e.target.closest('.v-row-head'); if(!h)return;
    const box=h.parentNode.querySelector('.v-row-detail');
    if(!box.dataset.filled){ box.innerHTML=vCallRows(h.dataset.vstock); box.dataset.filled='1'; }
    box.classList.toggle('open');
  });
}

function vRankRows(rows,key){
  return rows.map(st=>{const h=st[key]||{};
    return `<div class="v-row${st.low_sample?' low':''}">
      <div class="v-row-head" data-vstock="${esc(st.name)}">
        <span class="v-name">${esc(st.name)}</span>
        <span class="pill">${esc(st.market)}</span>
        ${st.low_sample?'<span class="v-badge low">표본 부족</span>':''}
        <span class="v-mini">${st.calls}콜</span>
        <span class="v-mini">${h.judged?`${h.hit}/${h.judged}`:'판정 전'}</span>
        <span class="v-hr">${h.hit_rate==null?'—':h.hit_rate.toFixed(0)+'%'}</span>
        <span class="v-ex">${vPct(h.avg_excess)}</span>
      </div><div class="v-row-detail"></div></div>`;}).join('');
}

function vCallRows(name){
  const key='h'+vHorizon;
  const cs=(D.verify.calls||[]).filter(c=>c.stock===name)
    .sort((a,b)=>a.date<b.date?1:a.date>b.date?-1:0);
  return cs.map(c=>{
    const r=c[key];
    const badge = c.conflict ? '<span class="v-badge conf">의견 갈림</span>'
      : c.error ? '<span class="v-badge pend">가격 없음</span>'
      : !r ? '<span class="v-badge pend">판정 대기</span>'
      : `<span class="v-badge ${r.hit?'hit':'miss'}">${vPct(r.excess!=null?r.excess:r.ret)}</span>`;
    const who=(c.sources||[]).map(x=>esc(x.sharer)).filter(Boolean).join(', ');
    const snip=esc(((c.sources||[])[0]||{}).snippet||'');
    return `<div class="mention"><span class="md">${esc(fmtDate(c.date))}</span>
      <span class="v-dir ${esc(c.stance)}">${c.stance==='bullish'?'강세':'약세'}</span>
      ${badge} <span style="color:var(--text-3)">${who}</span> ${snip}</div>`;
  }).join('') || '<div class="v-mini">표시할 콜이 없다.</div>';
}
```

- [ ] **Step 6: `showTab` 가드 + INIT 등록**

`showTab` 첫 줄 `if(!TABS.includes(name))name='home';` **다음**에 추가 — 검증 데이터가 없는데 `#verify` 로 들어오면 빈 화면이 뜨는 것을 막는다:

```js
  if(name==='verify' && !verifyOn()) name='home';
```

`:2013` INIT 줄 끝에 `renderVerify();` 추가:

```js
renderHome();renderSectors();renderStocks();renderAnalytics();renderStrategy();renderGlossary();renderGraph();renderChatView();renderVerify();
```

- [ ] **Step 7: 로컬 빌드 후 눈으로 확인**

```bash
python build_hub.py --phase all --src . --out hub_preview.html --json knowledge_base.json && python -m http.server 8000
```

브라우저에서 `http://localhost:8000/hub_preview.html#verify` 를 열고 확인:
- [ ] 좌측/하단 내비에 **검증** 탭이 보인다 (안 보이면 `D.verify.enabled` 를 콘솔에서 확인)
- [ ] 스코어보드 4칸이 채워지고 `—` 만 있지 않다
- [ ] 5일/20일/60일 토글이 동작하고, 60일에서 판정 대기 칸이 주황색으로 강조된다
- [ ] 랭킹 상단에 표본 5건 이상 종목만 나온다
- [ ] `＋ 표본 부족 N종목` 을 누르면 회색 행이 펼쳐진다
- [ ] 종목 행을 누르면 당시 발화 스니펫과 초과수익 배지가 나온다
- [ ] 콘솔에 에러가 없다
- [ ] 모바일 폭(375px)에서 스코어보드가 2열로 접힌다

- [ ] **Step 8: 커밋**

```bash
git add hub_template.html
git commit -m "feat: 검증 탭 — 스코어보드·구간 토글·종목 랭킹·근거 펼침"
```

`hub_preview.html` 은 `.gitignore` 대상이라 커밋되지 않는다. 확인할 것.

---

## Task 9: 종목 카드 칩 + 문서

**Files:**
- Modify: `hub_template.html`
- Modify: `README.md`

- [ ] **Step 1: 칩 헬퍼 추가**

Task 8에서 넣은 VERIFY 블록 끝에 추가. **표본 부족 종목은 적중률을 아예 노출하지 않는다** — 2콜짜리 100%가 신뢰의 근거로 읽히면 안 된다:

```js
const VMAP=(()=>{const m={};((D.verify&&D.verify.stocks)||[]).forEach(s=>m[s.name]=s);return m;})();
function verifyChip(name){
  const st=VMAP[name]; if(!st) return '';
  if(st.low_sample) return `<span class="pill" style="background:var(--surface-2,#f3f0ea);color:var(--text-3)">✅ ${st.calls}콜</span>`;
  const h=st['h'+PRIMARY_H]||{};
  if(!h.judged) return '';
  return `<span class="pill" style="background:#e8f6ec;color:#16a34a" title="${h.hit}/${h.judged} 적중 · 평균 초과 ${vPct(h.avg_excess)}">✅ ${h.hit}/${h.judged} · ${vPct(h.avg_excess)}</span>`;
}
```

같은 블록 상단에 상수를 추가한다 (사용자가 탭에서 구간을 바꿔도 카드 칩은 기준 구간으로 고정한다):

```js
const PRIMARY_H = ((D.verify&&D.verify.meta&&D.verify.meta.primary)||20);
```

- [ ] **Step 2: `stockRow` 에 칩 연결**

`hub_template.html:1012` 부근 `const chatPill = ...` 다음 줄에 추가:

```js
  const vPill = verifyChip(s.name);
```

같은 함수의 `.strow-mini` 안 `${chatPill}` 를 `${chatPill}${vPill}` 로 바꾼다.

> `verifyChip`/`VMAP` 은 `stockRow` 보다 아래에 정의되지만, 같은 스크립트 블록이라 함수 선언은 호이스팅되고 `VMAP`/`PRIMARY_H` 는 `renderStocks()` 가 INIT에서 호출되는 시점엔 이미 초기화돼 있다. 기존 `momentumChip`(`:1291`)이 `stockRow`(`:1002`)에서 쓰이는 것과 같은 구조다.

- [ ] **Step 3: 로컬 빌드로 칩 확인**

```bash
python build_hub.py --phase render --json knowledge_base.json --out hub_preview.html && python -m http.server 8000
```

`http://localhost:8000/hub_preview.html#stocks` 에서:
- [ ] SK하이닉스·삼성전자 등 콜 5건 이상 종목에 초록 `✅ n/m · +x.x%p` 칩이 보인다
- [ ] 콜이 적은 종목에는 회색 `✅ n콜` 만 보이고 **적중률이 노출되지 않는다**
- [ ] 검증 데이터가 없는 종목엔 칩이 아예 없다

- [ ] **Step 4: README 갱신**

`knowledge_base.json 스키마 (v2)` 표의 `ai_digest` 행 **바로 아래**에 추가:

```markdown
| `verify` | 채팅 방향성 발화의 사후 성과 검증 (`hublib/verify.py`) — `meta`/`summary`/`stocks`/`calls`. 봇·무벤치마크 종목 제외, 발화 다음 거래일 종가 진입, 지수 대비 초과수익. 수집 실패 시 `{"enabled": false}` |
```

`빌더 로직은 hublib/ 패키지에 있다` 표에도 추가:

```markdown
| `hublib/verify.py` | 채팅 콜 추출·판정·집계 + 가격 수집/캐시 |
```

아키텍처 다이어그램의 `build_hub.py --phase collect` 줄 설명에 `·검증` 을 덧붙인다.

- [ ] **Step 5: 전체 테스트 + 커밋**

```bash
python -m pytest tests/ generator/test_parse.py -q
```

기대: 전량 PASS.

```bash
git add hub_template.html README.md
git commit -m "feat: 종목 카드 검증 칩 + 문서"
```

---

## 마무리

- [ ] **최종 확인**

```bash
python -m pytest tests/ generator/test_parse.py -q && git status --short && git log --oneline main..HEAD
```

확인:
- 테스트 전량 PASS
- `git status` 에 산출물(`hub.html`/`knowledge_base.json`/`kb.*.json`/`hub_preview.html`/`build/price_cache.json`)이 **없다**
- 커밋 9개가 순서대로 있다

- [ ] **푸시 전 사용자 확인**

푸시하면 CI가 돌고 **Pages에 바로 공개된다.** 이 기능은 실명 발화자의 판단을 공개적으로 채점하는 성격이 있으므로, 푸시 전 반드시 사용자에게 로컬 프리뷰를 보여주고 승인을 받는다. 승인 없이 push 하지 않는다.

## 범위 밖 (이 계획에 넣지 않는다)

- 발화 시점 마커가 찍힌 주가 차트 (SVG 자체 렌더)
- 목표주가 179건 검증 (단위 정규화 필요)
- actions 1,916건 검증 (종목 필드 부재)
- 발화자별 성적표 — 스펙 §10에서 의도적으로 제외
