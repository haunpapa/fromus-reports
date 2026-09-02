# 성능 후속 개선 8건 구현 계획 (1차 계획의 "명시적 제외" 항목)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1차 병목 수정(머지 완료, CI 2m27s)에서 의도적으로 미룬 8건을 구현한다 — E2E 병렬화, SIGALRM 교체+모멘텀 히스토리 복원, Chart.js 제거(SVG), 앱 JS 해시 분리, sw.js 리포트 캐시 상한, chat_to_kb 단일 패스, 뉴스 Batches API(비용 −50%), run() 예외 격리.

**Architecture:** 4개 페이즈 — A(저위험 백엔드 3건), B(E2E 격리+xdist), C(프론트 3건: SW→앱JS분리→SVG 순서, sw.js를 두 태스크가 건드리므로 직렬), D(뉴스 Batches API — 유일한 아키텍처 변경: 하루 지연 2단계 배치). 각 태스크 독립 커밋·개별 revert 가능.

**Tech Stack:** Python 3.11 stdlib(+ anthropic SDK는 Phase D에서 추가), GitHub Actions, Playwright + pytest-xdist, 바닐라 JS/SVG.

**사전 조건:**
- 작업 브랜치: `perf/followup-8` (main에서 분기)
- 테스트: `python3 -m pytest tests/ generator/test_parse.py -q --ignore=tests/e2e` (= CI 유닛 스텝과 동일). 베이스라인 **167 passed**.
- E2E 로컬: `python3 build_hub.py --phase render --json knowledge_base.json --out hub.html && mkdir -p _site && cp hub.html kb.*.json version.json sw.js manifest.webmanifest _site/; cp hub.app.*.js _site/ 2>/dev/null; cp -r vendor icons _site/ 2>/dev/null; E2E_SITE_DIR=_site python3 -m pytest tests/e2e -q` → 베이스라인 **28 passed, 2 skipped**. (chromium 설치됨)
- 생성물(`hub.html`, `kb.*.json`, `knowledge_base.json`, `version.json`, `feed.json`, `_site/`, `.omc/`) 절대 커밋 금지.
- 커밋 메시지 한글, 태스크당 1커밋.

---

## Phase A — 저위험 백엔드

### Task A1: `run()` 단계별 예외 격리

`hublib/ai_summary.py`의 `run()` docstring은 "어떤 단계가 실패해도 나머지는 진행한다"인데 실제로는 try/except가 없어 한 단계의 예외가 전체를 중단시킨다(1차 리뷰에서 발견된 기존 이슈).

**Files:**
- Modify: `hublib/ai_summary.py` (`run()`, 215-222행 부근)
- Test: `tests/test_ai_summary.py`

- [ ] **Step 1 (RED):** tests/test_ai_summary.py에 추가:

```python
def test_run_isolates_stage_failures(monkeypatch):
    """한 단계가 터져도 나머지 단계는 진행한다 — docstring 의 계약을 실제로 지킨다."""
    import hublib.ai_summary as A
    cache = A.AiCache(path="/nonexistent/skip-load.json")
    monkeypatch.setattr(A, "_run_weekly", lambda *a: (_ for _ in ()).throw(RuntimeError("weekly boom")))
    kb = {"build": {"to": "2026-09-01"}, "stance": [], "sentiment": [], "stocks": [], "chat": {}}
    out = A.run(kb, cache, lambda p, m: '{"lines": ["a"]}')
    assert out["digest"] is None            # 터진 단계는 None
    assert "stock_reasons" in out and "news_flags" in out   # 나머지는 실행됨
```

Run: `python3 -m pytest tests/test_ai_summary.py::test_run_isolates_stage_failures -q` → Expected: FAIL (RuntimeError 전파)

- [ ] **Step 2 (GREEN):** `run()`을 교체:

```python
def _stage(fn, *args):
    """단계 격리 — 실패는 None 으로 흡수하고 로그만 남긴다."""
    try:
        return fn(*args)
    except Exception as e:
        print(f"  ✗ AI 단계 {fn.__name__} 실패: {repr(e)[:80]}")
        return None


def run(kb, cache, call, model=""):
    """kb + 캐시 + call → ai_digest.json 내용. 어떤 단계가 실패해도 나머지는 진행한다."""
    to, cutoff = _cutoff(kb)
    return {"generated": _fmt_kst(), "range": f"{cutoff}~{to}", "model": model,
            "digest": _stage(_run_weekly, kb, cache, call, to, cutoff),
            "daily": _stage(_run_daily, kb, cache, call, to),
            "stock_reasons": _stage(_run_stock_reasons, kb, cache, call) or {},
            "news_flags": _stage(_run_news_flags, kb, cache, call) or {}}
```

주의: `stock_reasons`/`news_flags`는 소비자(`render._apply_news_flags`, kb.core)가 dict를 기대하므로 `or {}`로 형 보존. `digest`/`daily`는 원래 None 허용.

- [ ] **Step 3:** `python3 -m pytest tests/test_ai_summary.py tests/ -q --ignore=tests/e2e` → PASS. 커밋:

```bash
git add hublib/ai_summary.py tests/test_ai_summary.py
git commit -m "fix: AI run() 단계별 예외 격리 — docstring 계약(한 단계 실패해도 나머지 진행) 실제 구현"
```

---

### Task A2: SIGALRM 제거 + 모멘텀 정밀 히스토리 병렬 복원

`_stock_market_momentum`(momentum.py:187-198)의 SIGALRM 타임아웃은 메인 스레드 전용이라 병렬화를 막고, 그 때문에 `MARKET_MOMENTUM_HISTORY_STOCKS` 기본 0으로 정밀 보강이 CI에서 죽어 있다. `future.result(timeout=)`로 교체하고 히스토리 단계를 8워커로 병렬화한 뒤 CI에서 40종목을 켠다.

**Files:**
- Modify: `hublib/momentum.py` (`_stock_market_momentum` 187-198행, `enrich_market_momentum` 히스토리 루프 338-346행), `.github/workflows/build.yml` (Collect env)
- Test: `tests/` 신규 파일 없음 — 기존 스위트 + 신규 타임아웃 테스트를 `tests/test_verify.py`가 아닌 **새 파일 `tests/test_momentum.py`**에 (momentum 테스트 파일이 없으므로 신설)

- [ ] **Step 1 (RED):** `tests/test_momentum.py` 신설:

```python
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
```

Run → Expected: FAIL — `AttributeError: module 'hublib.momentum' has no attribute '_enrich_history'` (두 번째), 첫 번째는 SIGALRM 경로에 따라 통과할 수도 있으니 결과를 기록만 하고 진행.

- [ ] **Step 2 (GREEN):** momentum.py 수정.

`_stock_market_momentum`의 SIGALRM 블록 교체 — `import signal`·`_MarketDataTimeout`·핸들러 제거하고:

```python
def _stock_market_momentum(name, meta, index_series, start_date):
    timeout = int(os.environ.get("MARKET_MOMENTUM_STOCK_TIMEOUT", "7") or 7)
    try:
        fdr = _ensure_finance_datareader()
        from concurrent.futures import ThreadPoolExecutor
        ex = ThreadPoolExecutor(max_workers=1)      # 데이터 소스 행 방어 — 시그널 없이 워커 스레드에서도 동작
        try:
            df = ex.submit(fdr.DataReader, meta["code"], start_date).result(timeout=timeout)
        finally:
            ex.shutdown(wait=False)                 # 타임아웃 시 내부 스레드를 기다리지 않는다 — 결과는 버려짐(SIGALRM 도 소켓을 못 죽였으므로 등가)
    except Exception as e:
        return None, f"가격 데이터 실패: {repr(e)[:80]}"
    ...(이하 기존 로직 그대로)...
```

주의: `with ThreadPoolExecutor(...)` 형태를 쓰면 안 된다 — `with`는 shutdown(wait=True)라 타임아웃 후에도 느린 스레드를 기다려 신규 타임아웃 테스트(`< 3초` 단언)가 실패한다. 반드시 위처럼 명시 생성 + `finally: ex.shutdown(wait=False)`.

히스토리 루프(338-346행)를 헬퍼로 추출·병렬화:

```python
def _enrich_history(pairs, index_series, start_date, workers=8):
    """(stock, meta) 목록을 병렬 정밀 보강. 성공 수와 실패 메시지 목록을 돌려준다.
    쓰기(s["market_momentum"])는 결과 수집 후 메인 스레드에서만 한다."""
    from concurrent.futures import ThreadPoolExecutor
    if not pairs:
        return 0, []

    def _one(pair):
        s, meta = pair
        name = s.get("name") or ""
        try:
            mm, err = _stock_market_momentum(name, meta, index_series, start_date)
        except Exception as e:
            return s, None, f"{name}: {repr(e)[:60]}"
        return s, mm, (f"{name}: {err}" if err else None)

    done, failures = 0, []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(_one, pairs))
    for s, mm, err in results:
        if mm:
            s["market_momentum"] = mm
            done += 1
        elif err:
            failures.append(err)
    return done, failures
```

`enrich_market_momentum`의 기존 for 루프를 교체:

```python
    historical, hist_failures = _enrich_history(historical_candidates[:history_n], index_series, start_date)
    failures.extend(hist_failures)
```

(기존 진행 print는 병렬화로 의미가 없어지므로 완료 후 1줄 `print(f"    · 시장 히스토리 {historical}/{min(history_n, len(historical_candidates))}종목 보강")`로 대체. `MARKET_MOMENTUM_HISTORY_STOCKS` 기본값 0과 주석의 "환경변수로 켠다" 정책은 유지.)

- [ ] **Step 3:** build.yml Collect env에 추가:

```yaml
          MARKET_MOMENTUM_HISTORY_STOCKS: "40"   # 정밀 보강 복원 — SIGALRM 제거·8워커 병렬화로 이제 ~10초 (2026-09 후속 A2)
```

- [ ] **Step 4:** `python3 -m pytest tests/ generator/test_parse.py -q --ignore=tests/e2e` → PASS (베이스라인 167 + A1의 1개 + A2의 2개 = **170 expected**). YAML 검증: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml'))"`. 커밋:

```bash
git add hublib/momentum.py tests/test_momentum.py .github/workflows/build.yml
git commit -m "perf: 모멘텀 SIGALRM → future 타임아웃 교체 + 히스토리 보강 8워커 병렬화, CI 40종목 복원"
```

---

### Task A3: chat_to_kb 단일 패스 + match_stocks 후보 프리필터 + update_archive 중복 제거

로컬 생성기(`./generator/refresh.sh`) 최적화 — 33k 메시지 기준 −5~8초. **출력 불변이 절대 조건**이므로 골든 마스터로 고정한다.

**Files:**
- Modify: `generator/chat_to_kb.py` (`build()`), `generator/fromus_taxonomy.py` (`match_stocks`), `generator/update_archive.py` (mention Counter 중복 3회 → 1회, 죽은 루프 삭제)
- Test: `generator/test_parse.py` (기존 스위트가 taxonomy 회귀 방지막) + 골든 마스터 테스트 추가

- [ ] **Step 1 (골든 마스터 고정):** `generator/test_parse.py`에 refactor 전 출력 고정 테스트 추가. **반드시 리팩토링 전에 작성·통과 확인**:

```python
def test_build_golden_master():
    """리팩토링(단일 패스·프리필터) 전후 build() 출력 완전 동일 보장."""
    import chat_to_kb as C
    msgs = [
        {"idx": 0, "date": "2026-09-01", "sender": "ㄱ 이혜나", "room": "a",
         "body": "SK하이닉스 HBM 수요 강합니다. 반도체 사이클 주목하세요. 목표가 30만원"},
        {"idx": 1, "date": "2026-09-01", "sender": "회원1", "room": "a",
         "body": "하닉 지금 사도 될까요?"},
        {"idx": 2, "date": "2026-09-01", "sender": "ㄱ 이혜나", "room": "a",
         "body": "분할 매수로 접근하세요. 한 번에 몰빵은 금지입니다. 리스크 관리가 원칙."},
    ]
    links = [{"date": "2026-09-01", "sharer": "회원1", "url": "https://n.example/1",
              "title": "삼성전자 파운드리 수주", "category": "news", "outlet": "테스트"}]
    signals = [{"date": "2026-09-01", "sharer": "ㄱ 이혜나", "type": "view", "snippet": "하이닉스 강세",
                "full": "하이닉스 강세 지속", "stocks": [["SK하이닉스", "bullish"]], "themes": []}]
    out = C.build(msgs, links, signals)
    # 골든 값 — 이 단언들은 리팩토링 전 실제 출력으로 채운다(placeholder 금지):
    # 구현자는 먼저 이 테스트를 위 입력으로 실행해 실제 out 을 print 로 확인하고,
    # stocks 키 집합·counts·themes·targets·news·actions·strategy·qna 의 구체 값을 단언으로 고정한 뒤,
    # 그 단언이 리팩토링 전 코드에서 PASS 함을 확인하고 나서 리팩토링을 시작한다.
    raise NotImplementedError("리팩토링 전 실제 출력으로 단언을 채울 것")
```

절차: (a) 위 입력으로 현재 코드의 `build()` 출력을 덤프, (b) `NotImplementedError`를 지우고 핵심 단언(예: `assert set(out["stocks"]) == {...실제값...}`, `out["stocks"]["SK하이닉스"]["count"] == N`, `out["targets"][0]["value"] == ...`, themes 목록, actions/strategy 건수와 첫 항목 텍스트)으로 교체, (c) PASS 확인. 이 단언들이 리팩토링의 등가성 증명이 된다.

- [ ] **Step 2 (chat_to_kb 단일 패스):** `build()` 서두에서 메시지별 파생값을 1회 계산:

```python
    for m in msgs:                       # 파생값 1회 계산 — 7개 수집 루프가 재사용 (2026-09 후속 A3)
        body = m["body"]
        m["_clean"] = URL.sub("", body).strip()
        m["_teacher"] = m["sender"] in TEACHERS
        m["_stocks"] = T.match_stocks(body)
```

이후 각 루프에서: 49-54행 stocks 루프는 `m["_stocks"]` 사용, 96행 targets 루프의 `T.match_stocks(m["body"])` → `m["_stocks"]`, 각 루프의 `URL.sub("",m["body"]).strip()` → `m["_clean"]`, `m["sender"] in TEACHERS`/`not in TEACHERS` → `m["_teacher"]` 사용. 루프 통합은 하지 않는다(7개 수집기의 순서·가독성 유지 — 낭비의 대부분은 파생값 재계산이었다). 마지막에 임시 키 정리:

```python
    for m in msgs:
        m.pop("_clean", None); m.pop("_teacher", None); m.pop("_stocks", None)
```

(주의: `build()`는 호출자의 msgs dict를 이미 참조로 쓰므로 임시 키 정리로 입력 오염을 방지 — 불변성 원칙과의 절충을 주석으로 명시.)

- [ ] **Step 3 (match_stocks 후보 프리필터):** `generator/fromus_taxonomy.py`의 `match_stocks`를 의미 불변으로 가속 — 전체 별칭 순회 전에 한 번의 결합 정규식으로 후보만 추린다:

```python
import re as _re
_ALIAS_SCAN = None   # 모듈 로드 순서상 _ALIAS_SURFACE 완성 후 첫 호출에서 컴파일

def _alias_scan():
    global _ALIAS_SCAN
    if _ALIAS_SCAN is None:
        surfs = sorted(_ALIAS_SURFACE, key=len, reverse=True)
        _ALIAS_SCAN = _re.compile("|".join(_re.escape(s) for s in surfs))
    return _ALIAS_SCAN

def match_stocks(text):
    text = text or ""
    out = set()
    candidates = set(_alias_scan().findall(text))      # 대부분의 메시지는 후보 0~2개
    for surf in candidates:
        canon = _ALIAS_SURFACE.get(surf)
        if canon is None or canon in STOCK_STOPWORDS or len(canon) < 2:
            continue
        if _surf_in(text, surf):                        # 경계·부정접미사 검사는 기존 그대로
            out.add(canon)
    return out
```

주의 3가지: ① re 교대는 "최장"이 아니라 **각 위치에서 첫 번째로 매치되는 대안**을 고른다 — `sorted(..., key=len, reverse=True)`로 길이 내림차순 배열해야 각 위치에서 최장 우선이 된다(필수). 잔여 리스크는 "긴 매치 안에 완전히 포함된 **다른 canon**의 짧은 표면형"인데, 현재 `_ALIAS_SURFACE` 전수 검사 결과 그런 쌍이 없다(하이닉스⊂SK하이닉스 등 부분문자열 쌍은 전부 동일 canon). 이는 구조 보장이 아닌 경험적 사실이므로 **불변식 테스트를 함께 추가**한다:

```python
def test_alias_substring_pairs_share_canon():
    """프리필터 안전 불변식: 표면형 A⊂B 이면 canon(A)==canon(B). 깨지면 프리필터가 조용히 누락시킨다."""
    from fromus_taxonomy import _ALIAS_SURFACE
    surfs = list(_ALIAS_SURFACE)
    for a in surfs:
        for b in surfs:
            if a != b and a in b:
                assert _ALIAS_SURFACE[a] == _ALIAS_SURFACE[b], f"{a!r}⊂{b!r} 인데 canon 이 다름 — 프리필터 누락 위험"
```

② 기존 taxonomy 테스트 + Step 1 골든 마스터로 등가성 확인 — 반례 발견 시 **프리필터를 폐기하고 이 스텝만 스킵**(안전 우선). ③ `match_themes_for_stock`은 건드리지 않는다.

- [ ] **Step 4 (update_archive 중복 제거):** `generator/update_archive.py`에서:
  1. 276-277행의 죽은 루프(`for m in msgs: bym  # placeholder`) 삭제.
  2. mention Counter 3중 계산 통합: **엔티티 맵은 반드시 전 메시지의 원본 body(URL 포함) 기준으로 계산**한다 — `aggregate()`(~471-474행)와 `ontology()`(~543-546행)의 mention 루프는 게이트 없이 전체 msgs를 세고 URL 안의 별칭(TSLA 등)도 카운트하는 반면, `strategy()`(~442-443행)는 `len(text)<6` 메시지를 find_ents 호출 **전에** 건너뛴다. 따라서 strategy의 게이트를 맵 계산에 끌고 오면 mention이 언더카운트되어 등가성이 깨진다. 올바른 구조: `{idx: ents}` 맵을 전 메시지에 대해 1회 계산 → aggregate/ontology는 맵을 그대로 소비, strategy는 자기 게이트(len<6 스킵)를 **소비 시점에** 유지. 구현 전 세 루프를 읽고 술어가 정말 등가인지(`any(a in body)`) 확인 — 다르면 공통부만 추출.
  3. 검증: update_archive는 카톡 CSV가 필요해 CI 테스트가 없다 — `generator/test_parse.py`가 커버하는 함수 범위를 확인하고, 커버 밖이면 통합한 헬퍼에 대한 소형 단위 테스트 1개 추가.

- [ ] **Step 5:** `python3 -m pytest generator/test_parse.py tests/ -q --ignore=tests/e2e` → PASS (골든 마스터 포함). 커밋:

```bash
git add generator/chat_to_kb.py generator/fromus_taxonomy.py generator/update_archive.py generator/test_parse.py
git commit -m "perf: 생성기 단일 패스·별칭 프리필터·mention 계산 통합 — 골든 마스터로 출력 불변 보장"
```

---

## Phase B — E2E 격리 + 병렬화

### Task B1: version.json 토스트 테스트 route 격리 + pytest-xdist `-n 4`

`test_update_toast_when_version_differs`(test_hub_smoke.py:123-134)가 `_site/version.json`을 실제로 덮어써 병렬 실행 시 다른 워커의 부트를 오염시킨다. `page.route()`로 응답만 가로채도록 바꾸면 파일 무변경·xdist 안전. `test_boot_timing_recorded`의 `build/e2e_timing.json` 쓰기는 이 테스트 하나만 쓰므로 경합 없음(확인만).

**Files:**
- Modify: `tests/e2e/test_hub_smoke.py:123-134`, `requirements-dev.txt`, `.github/workflows/build.yml` (E2E 스텝)

- [ ] **Step 1:** 토스트 테스트를 route 방식으로 교체:

```python
def test_update_toast_when_version_differs(page, site_url):
    """새 배포 감지 토스트 — version.json 응답만 가로챈다(파일 무변경·병렬 안전)."""
    page.route("**/version.json*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"core":"kb.core.0000000000.json","generated":"2099-01-01 00:00"}'))
    _boot(page, site_url)
    page.wait_for_selector("#fu-toast", timeout=10000)
```

전제 확인: 부트의 version 폴링이 `fetch('version.json?nosw='+...)`이고 `page.route`는 SW를 거치기 전 네트워크 레이어에서 가로챈다 — 단 **SW가 응답을 대신 만들면 route가 안 잡힐 수 있다**. sw.js:35는 `?nosw=`를 가로채지 않고 네트워크 직행이므로 route가 잡는다. 구현 후 이 테스트가 단독으로 PASS함을 먼저 확인.

- [ ] **Step 2:** `requirements-dev.txt`에 `pytest-xdist>=3` 추가. build.yml E2E 실행줄:

```yaml
          E2E_SITE_DIR=_site python -m pytest tests/e2e -q -n 4
```

- [ ] **Step 3 (검증):** 로컬에서 3회 반복 실행으로 플레이키 확인:

```bash
for i in 1 2 3; do E2E_SITE_DIR=_site python3 -m pytest tests/e2e -q -n 4 || break; done
```

Expected: 3회 모두 28 passed (병렬로 ~10-14초). 실패가 나오면 실패 테스트를 기록하고 `-n 4`를 되돌리는 대신 **해당 테스트만 `@pytest.mark.xdist_group("serial")`로 격리**를 먼저 시도 — 주의: `xdist_group`은 기본 `--dist load`에서 무시되므로 이 폴백을 쓰는 순간 실행 옵션을 `-n 4 --dist loadgroup`으로 바꿔야 한다(build.yml 포함).

- [ ] **Step 4:** 커밋:

```bash
git add tests/e2e/test_hub_smoke.py requirements-dev.txt .github/workflows/build.yml
git commit -m "perf: E2E 병렬화(-n 4) — 토스트 테스트 route 격리로 파일 변조 제거, 30초→약 12초"
```

---

## Phase C — 프론트 3건 (순서 고정: C1 → C2 → C3, sw.js·템플릿 충돌 방지)

### Task C1: sw.js 리포트 캐시 분리 + 상한

현재 kb 외 모든 GET이 `fu-hub-v4`에 무제한 SWR 적재 — 리포트 106개(~7.7MB)가 브라우저에 영구 잔류하고 상한이 없다. `/reports/` 경로를 별도 캐시로 분리하고 FIFO 상한 30개를 적용한다.

**Files:**
- Modify: `sw.js`
- Test: `tests/test_phases.py::test_hub_template_has_kb_retry_fallback`(84행)이 `"fu-hub-v4" in sw`를 단언 — **Step 2의 v5 범프에 맞춰 같은 커밋에서 `"fu-hub-v5"`로 갱신**. E2E `test_service_worker_registers`.

- [ ] **Step 1:** sw.js fetch 핸들러의 SWR 분기 앞에 리포트 분기 추가:

```js
const REPORTS_CACHE = 'fu-reports-v1';
const REPORTS_MAX = 30;                       // FIFO 상한 — 리포트는 매일 늘므로 방치하면 무한 증식

// (fetch 핸들러 안, chunk 분기 다음에)
  if (path.includes('/reports/')) {
    e.respondWith(
      caches.open(REPORTS_CACHE).then(c => c.match(e.request).then(cached => {
        const net = fetch(e.request).then(r => {
          if (r && r.ok) {
            const cp = r.clone();
            c.put(e.request, cp).then(async () => {
              const keys = await c.keys();
              for (const k of keys.slice(0, Math.max(0, keys.length - REPORTS_MAX))) await c.delete(k);
            });
          }
          return r;
        }).catch(() => cached);
        return cached || net;
      }))
    );
    return;
  }
```

activate 핸들러의 구캐시 정리 필터를 `k !== CACHE && k !== REPORTS_CACHE`로 확장(리포트 캐시가 버전 정리에 휩쓸리지 않게). 주석에 "Cache API keys()는 삽입순 보장이 명시 스펙은 아니나 실구현이 삽입순 — 근사 FIFO로 충분" 명시.

- [ ] **Step 2 (레거시 회수 — 핵심):** 기존 사용자 브라우저에는 이미 `fu-hub-v4` 안에 `/reports/` 엔트리(~7.7MB)가 SWR로 쌓여 있다. 분기만 추가하면 **앞으로의** 요청만 새 캐시로 갈 뿐 기존 잔류분이 영구히 남아 태스크 목표(무한 증식 차단+회수)의 절반이 미달이다. 해결: `CACHE = 'fu-hub-v5'`로 범프 — activate의 "다른 캐시 전량 삭제"가 v4를 통째로 지우면서 레거시 리포트도 함께 회수된다(프리캐시는 install에서 재구축). 이에 따라 `tests/test_phases.py:83`의 `assert "fu-hub-v4" in sw` 단언을 `"fu-hub-v5"`로 갱신(같은 커밋).

- [ ] **Step 3:** 유닛 + E2E 전체 실행 → PASS. 커밋:

```bash
git add sw.js tests/test_phases.py
git commit -m "perf: SW 리포트 캐시 분리(fu-reports-v1)+FIFO 상한 30, v5 범프로 레거시 잔류분 회수"
```

---

### Task C2: 앱 JS 해시 분리 (`hub.app.<hash>.js`)

앱 JS 120KB가 셸에 인라인이라 데이터만 바뀌어도 매일 gz 54KB 전량 재다운로드된다. 해시 파일로 분리하면 코드 변경 시에만 받는다. **부트 순서 계약 유지가 핵심**: 앱 JS는 `window.DATA` 설정 후 실행되어야 한다.

**Files:**
- Modify: `hublib/render.py` (`inject_app_js` → `inject_app_src` + `emit_app_js`), `hub_template.html` (fu-app 래퍼 삭제 + APPSRC 마커 + 동적 로드), `sw.js` (해시 앱 파일 cache-first)
- Test: `tests/test_phases.py` (셸에 인라인 앱 JS가 없고 hub.app.*.js가 생성·참조되는지), **`tests/test_split.py` — 기존 2개 테스트가 C2로 깨지므로 반드시 갱신**: ① `test_inject_app_js_replaces_marker_without_backslash_mangling`(25-31행) → `inject_app_src` 대상 등가 테스트로 교체(백슬래시·`$1` 무손상 단언은 치환 함수 패턴 확인용으로 유지), ② `test_template_has_app_marker_and_no_inline_app_code`(47-50행, 템플릿에 `/*APPJS*/` 존재를 직접 단언) → `/*APPSRC*/…/*ENDAPPSRC*/` 존재 + `"function renderHome(" not in tpl` 단언으로 갱신. E2E 전체.

- [ ] **Step 1 (RED):** test_phases.py의 `test_collect_then_render`에 단언 추가:

```python
    app_files = list(src.glob("hub.app.*.js"))
    assert len(app_files) == 1, "앱 JS 는 해시 파일로 분리 배출돼야 함"
    assert app_files[0].name in shell, "셸이 앱 JS 해시 파일을 참조해야 함"
    assert "/* ==== 00_util.js ==== */" not in shell, "앱 JS 가 셸에 인라인되면 안 됨"
```

Run → FAIL.

- [ ] **Step 2 (render.py):** `render()`에서 `inject_app_js(shell, concat_app_js())` 대신:

```python
def emit_app_js(out_dir, app_js):
    """앱 JS 를 내용 해시 파일로 배출하고 파일명을 돌려준다. 구 해시는 render() 서두의 kb.* 정리와 같은 방식으로 정리."""
    h = hashlib.sha1(app_js.encode("utf-8")).hexdigest()[:10]
    name = f"hub.app.{h}.js"
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        f.write(app_js)
    return name
```

- render() 서두의 구파일 정리 glob에 `hub.app.*.js` 추가.
- 셸 처리 — **주의: `/*APPJS*/` 마커는 `<script type="fu-app">`(비실행 블록) 안에 있다.** 그 안에 `window.FU_APP_SRC=...`를 넣으면 fu-app eval 루프가 사라진 뒤(Step 3) **아무도 실행하지 않아 부트가 확실히 실패**한다. 올바른 구조: 파일명은 **부트 스크립트 자신의 마커**로 주입한다.
  - `hub_template.html`: `<script type="fu-app">` 래퍼와 `/*APPJS*/…/*ENDAPPJS*/` 마커 블록을 **통째로 삭제**하고, 부트 스크립트(일반 실행 스크립트) 안의 `coreUrl` 계산 근처에 새 마커를 추가:

```js
    const appSrc = /*APPSRC*/""/*ENDAPPSRC*/;   // 렌더가 "./hub.app.<h>.js" 로 치환 — 빈 문자열이면 구 빌드(인라인) 경로 없음 에러
```

  - `hublib/render.py`: `inject_app_js`를 마커 치환 함수로 교체(KBURL 치환과 동일 패턴 — re.sub + 치환 함수):

```python
def inject_app_src(shell, app_name):
    """부트 스크립트의 /*APPSRC*/ 마커를 앱 JS 해시 경로로 치환."""
    if "/*APPSRC*/" not in shell or "/*ENDAPPSRC*/" not in shell:
        raise ValueError("템플릿에 /*APPSRC*/ … /*ENDAPPSRC*/ 마커가 없습니다.")
    return re.sub(r"/\*APPSRC\*/.*?/\*ENDAPPSRC\*/",
                  lambda _m: f'/*APPSRC*/"./{app_name}"/*ENDAPPSRC*/', shell, count=1, flags=re.S)
```

  - `render()`: `shell = inject_app_js(shell, concat_app_js())` → `shell = inject_app_src(shell, emit_app_js(out_dir, concat_app_js()))`. 기존 `inject_app_js` 함수는 삭제(사용처·테스트 grep 후 — 참조가 남으면 함께 갱신).

- Assemble(_site 복사): build.yml의 `cp kb.*.json _site/` 옆에 `cp hub.app.*.js _site/ 2>/dev/null || true` 추가. **로컬 E2E 사전 조건의 cp 목록에도 추가**(계획 서두 명령 갱신).
- head에 preload 추가(선택 아님 — 인라인을 뺀 만큼 로드 타이밍 보상): `inject_core_preload`와 같은 방식으로 `<!--APPPRELOAD-->` 마커 + `<link rel="preload" as="script" href="./hub.app.<h>.js">` 주입 함수 `inject_app_preload` 추가, 템플릿 head의 KBPRELOAD 아래 마커 배치.

- [ ] **Step 3 (템플릿 부트):** fu-app eval 루프(부트 스크립트 내 `document.querySelectorAll('script[type="fu-app"]').forEach(...)` — 정확한 형태를 먼저 읽을 것)를 외부 스크립트 로드로 교체:

```js
    // 앱 JS 는 해시 파일 — DATA 준비 후 로드해야 하는 순서 계약은 동일 (동적 삽입 classic script = 전역 실행)
    await new Promise(function(res, rej){
      var s = document.createElement('script');
      s.src = appSrc; s.onload = res; s.onerror = function(){ rej(new Error('app js 로드 실패: ' + appSrc)); };
      document.body.appendChild(s);
    });
```

(`appSrc`는 Step 2의 `/*APPSRC*/` 마커 상수 — 부트 스크립트 스코프 안에 이미 있다.) **함수 선언이 전역에 남는 계약** 유지 필수: 동적 삽입 classic script는 전역 실행이므로 `renderHome` 등 전역 접근 등가. onerror는 기존 KB 404 자기치유 catch로 흘러가도록 이 await를 기존 try 블록 **안**에 배치.

- [ ] **Step 4 (sw.js):** 해시 앱 파일 cache-first + 구해시 정리:

```js
const APP_RE = /\/hub\.app\.[0-9a-f]{6,}\.js$/;
```

fetch 핸들러에서 `APP_RE.test(path)`면 kb 청크와 동일한 cache-first + 같은 패턴 구해시 삭제 로직 적용(청크명 'app' 취급— `chunkOf`를 확장하거나 별도 분기). PRECACHE의 `./vendor/chart.umd.min.js`는 C3에서 다루므로 여기선 유지.

- [ ] **Step 5:** 유닛(신규 단언 포함) + E2E 전체 → PASS. `test_boot_renders_home_without_errors`의 외부 스크립트 0 단언(line 30-32)은 same-origin이라 통과 — 확인. 커밋:

```bash
git add hublib/render.py hub_template.html sw.js tests/test_phases.py tests/test_split.py .github/workflows/build.yml docs/superpowers/plans/2026-09-02-perf-followup-8.md
git commit -m "perf: 앱 JS 해시 분리(hub.app.<hash>.js) — 코드 변경 시에만 재다운로드, SW cache-first"
```

---

### Task C3: Chart.js 제거 → 인라인 SVG 차트

사용처는 딱 둘: 홈 지수 스파크라인 3개(`miniChart`, line), 분석 탭 센티멘트 막대(`drawSentiment`, bar + 클릭→리포트 + 툴팁). 68KB gz + 요청 1개 + 부트 훅이 사라진다. **UX 등가 조건**: 막대 클릭 → `openReport(id)` 유지, 호버 정보(날짜·헤드라인·긍정/부정)는 SVG `<title>` 네이티브 툴팁으로 대체.

**Files:**
- Modify: `hub/20_home.js` (`miniChart`), `hub/80_analytics.js` (`drawSentiment`), `hub_template.html` (chartjs script 태그·재그리기 훅 제거, `.idx-chart` CSS 확인), `sw.js` (PRECACHE에서 vendor 제거), `.github/workflows/build.yml`·`vendor/chart.umd.min.js` (파일 삭제 + Assemble에서 vendor 복사 정리 — icons만 남으면 `cp -r reports icons _site/`), `tests/e2e/test_hub_smoke.py` (Chart 단언 교체)
- 삭제: `vendor/chart.umd.min.js` (vendor 디렉터리가 비면 디렉터리째)

- [ ] **Step 1 (E2E 계약 먼저 수정 — RED):** test_hub_smoke.py:
  - line 33 `assert page.evaluate("typeof window.Chart") == "function"` → 데이터 유무에 관대하게: `assert page.evaluate("document.querySelectorAll('#view-home .idx-chart svg.fu-spark, #view-home .idx-chart .empty').length") == 3` (3개 셀이 전부 SVG 또는 빈 데이터 폴백으로 렌더 — 시리즈가 비어도 통과, Chart.js 부재가 계약)
  - line 90 `canvases` 수집과 line 101 `< 15` 단언 → svg 기준으로 교체하되, **canvas가 0이라고 단언하지 말 것** — `drawSpark`(종목 스파크)는 Chart.js 없이 canvas를 직접 그리므로 C3 이후에도 canvas는 남는다("사용처 딱 둘"은 Chart.js 기준).
  - E2E 실행 → 신규 단언 FAIL 확인.

- [ ] **Step 2 (`miniChart` SVG 구현, hub/20_home.js):** 기존 함수를 교체 — 시그니처·호출부(`drawTrend`) 불변:

```js
function miniChart(id, data, color){
  const el=document.getElementById(id); if(!el) return;
  const wrap=el.closest('.idx-chart');
  if(!data || data.length<2){
    const last=(data&&data.length)?data[data.length-1].value.toLocaleString():null;
    if(wrap) wrap.innerHTML=`<div class="empty" style="padding:28px 8px;font-size:12px">데이터 부족<br><span style="font-size:10.5px;color:var(--text-4)">${last?('최근값 '+last):'리포트에 종가 미기재일 多'}</span></div>`;
    return;
  }
  const W=260, H=80, P=6;
  const vs=data.map(p=>p.value), lo=Math.min(...vs), hi=Math.max(...vs), span=(hi-lo)||1;
  const x=i=>P+(W-2*P)*i/(data.length-1), y=v=>H-P-(H-2*P)*(v-lo)/span;
  const pts=data.map((p,i)=>`${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const area=`${P},${H-P} ${pts} ${(W-P).toFixed(1)},${H-P}`;
  const first=data[0], last=data[data.length-1];
  wrap.innerHTML=`<svg class="fu-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
      aria-label="${fmtDate(first.date)}~${fmtDate(last.date)} 종가 추이, 최근 ${last.value.toLocaleString()}">
    <title>${fmtDate(first.date)} ${first.value.toLocaleString()} → ${fmtDate(last.date)} ${last.value.toLocaleString()}</title>
    <polygon points="${area}" fill="${color}22"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="${x(data.length-1).toFixed(1)}" cy="${y(last.value).toFixed(1)}" r="2.5" fill="${color}"/>
  </svg>`;
}
```

(기존 Chart 버전이 그리던 축 눈금·라벨은 스파크라인 목적상 생략 — 마지막 값은 aria/타이틀로 보존. `window.__charts` 관리도 이 함수에선 제거.)

- [ ] **Step 3 (`drawSentiment` SVG 구현, hub/80_analytics.js):** bar + 클릭 + 툴팁 등가:

```js
function drawSentiment(){
  const el=document.getElementById('cSent'); if(!el)return;
  const wrap=el.closest('.idx-chart');
  const S=(D.sentiment||[]);
  if(S.length<2){if(wrap)wrap.innerHTML='<div class="empty">센티멘트 데이터가 없습니다 — build_hub.py 재실행 필요</div>';return;}
  const cs=getComputedStyle(document.documentElement);
  const G=cs.getPropertyValue('--green').trim()||'#247a3d', R=cs.getPropertyValue('--red').trim()||'#c2402f',
        GD=cs.getPropertyValue('--gold').trim()||'#9a7508', GRID=cs.getPropertyValue('--grid').trim()||'#ece6d7';
  const W=640, H=210, P=18, mid=H/2;
  const bw=Math.max(2,(W-2*P)/S.length-2);
  const bars=S.map((p,i)=>{
    const c=p.score>=15?G:p.score<=-15?R:GD;
    const h=Math.abs(p.score)/100*(H/2-P);
    const x=P+(W-2*P)*i/S.length, y=p.score>=0?mid-h:mid;
    return `<rect class="fu-bar" data-i="${i}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1,h).toFixed(1)}" rx="1.5" fill="${c}" style="cursor:pointer">
      <title>${fmtDate(p.date)} · ${p.score}점${p.headline?(' · '+p.headline):''} (긍정 ${p.pos} · 부정 ${p.neg})</title></rect>`;
  }).join('');
  wrap.innerHTML=`<svg class="fu-bars" viewBox="0 0 ${W} ${H}" role="img" aria-label="센티멘트 추이">
    <line x1="${P}" y1="${mid}" x2="${W-P}" y2="${mid}" stroke="${GRID}" stroke-width="1"/>
    ${bars}</svg>`;
  wrap.querySelector('svg').addEventListener('click', e=>{
    const r=e.target.closest('.fu-bar'); if(r) openReport(S[+r.dataset.i].id);
  });
}
```

(캔버스 `<canvas id="cSent">` 마크업(66행)은 wrap.innerHTML로 대체되므로 그대로 둬도 무해하나, 렌더 문자열에서 canvas를 제거하고 wrap에 직접 그리도록 정리. `if(!window.Chart||...)` 가드는 데이터 조건만 남긴다.)

- [ ] **Step 4 (제거):** ① `hub_template.html`: `<script defer src="./vendor/chart.umd.min.js" id="chartjs">` 태그 삭제, 1차에서 넣은 chartjs 재그리기 훅 블록 삭제, JetBrains Mono가 차트 눈금에만 쓰였는지 확인(다른 사용처 있음 — 유지). ② `sw.js` PRECACHE에서 `'./vendor/chart.umd.min.js'` 제거. ③ `git rm vendor/chart.umd.min.js` (vendor가 비면 build.yml `cp -r reports icons vendor _site/` → `cp -r reports icons _site/`). ④ `window.__charts` 잔여 참조 grep 후 정리. 테마 전환 경로: `setTheme`(hub/40_state.js:8-10)은 현재 `drawTrend`/`drawStockSparks`만 재호출한다 — SVG 센티멘트 막대는 CSS 변수 색을 그리는 시점에 굽기 때문에, **분석 탭이 렌더된 상태에서 테마 전환 시 `drawSentiment()` 재호출을 setTheme에 추가**해야 색이 갱신된다(`RENDERED.has('analytics')` 가드 + 존재 가드).

- [ ] **Step 5 (검증):** 유닛 + E2E 전체(-n 4) → PASS. 셸 빌드 후 브라우저 육안 확인: 홈 스파크라인 3개 렌더·색상, 분석 탭 막대 클릭→리포트 모달, 다크 모드 전환 시 색 갱신. 커밋:

```bash
git add hub/20_home.js hub/80_analytics.js hub_template.html sw.js tests/e2e/test_hub_smoke.py .github/workflows/build.yml
git rm vendor/chart.umd.min.js
git commit -m "perf: Chart.js 제거 — 스파크라인·센티멘트 막대 인라인 SVG 대체 (gz −68KB, 요청 −1, 부트 훅 제거)"
```

---

## Phase D — 뉴스 분류 Batches API (비용 −50%)

### Task D1: anthropic SDK 도입 + 뉴스 플래그 2단계 배치

뉴스 neutral 분류(하루 최대 200건)는 지연 허용 작업 — Batches API로 옮기면 비용 50% 절감. **설계: 하루 지연 2단계** — 오늘 빌드는 ① 어제 제출한 배치 결과를 수거해 캐시에 반영하고 ② 미분류분을 새 배치로 제출한다. 대기(polling) 없음 → CI 시간 영향 0. 뉴스 플래그가 최대 하루 늦는 것은 수용(neutral 필터는 표시 우선순위 문제일 뿐). weekly/daily/종목 이유는 동기 유지.

**Files:**
- Modify: `requirements.txt` (+`anthropic`), `ai_digest.py` (SDK 클라이언트 + batch ops 주입), `hublib/ai_summary.py` (`_run_news_flags` 배치 경로 추가), `hublib/ai_prompts.py` 확인(NEWS_PROMPT 재사용)
- Test: `tests/test_ai_summary.py` (가짜 batch ops로 제출/수거/폴백 검증)

- [ ] **Step 1 (RED):** tests/test_ai_summary.py에:

```python
def _news_kb(urls):
    return {"build": {"to": "2026-09-01"},
            "chat": {"news": [{"title": f"t{i}", "url": u} for i, u in enumerate(urls)]}}


def test_news_batch_submits_and_records_pending():
    """배치 경로: 미분류 뉴스를 제출하고 배치 id 를 캐시에 남긴다. 동기 호출은 하지 않는다."""
    from hublib.ai_summary import AiCache, _run_news_flags, _PENDING_KEY
    cache = AiCache(path="/nonexistent/x.json")
    submitted = {}

    def submit(reqs):
        submitted["reqs"] = reqs
        return "batch_abc"

    batch = {"submit": submit, "retrieve": lambda i: "in_progress", "results": lambda i: []}
    out = _run_news_flags(_news_kb(["https://a", "https://b"]), cache, call=None, batch=batch)
    assert out == {}                                     # 아직 분류 결과 없음
    assert cache.get(_PENDING_KEY)["id"] == "batch_abc"
    assert submitted["reqs"], "미분류 뉴스가 배치 요청으로 제출돼야 함"


def test_news_batch_collects_finished_results():
    """전일 배치가 끝났으면 결과를 캐시에 반영하고 pending 을 지운 뒤 새 배치를 제출한다."""
    import json as _j
    from hublib.ai_summary import AiCache, _run_news_flags, _PENDING_KEY
    cache = AiCache(path="/nonexistent/x.json")
    cache.put(_PENDING_KEY, {"id": "batch_old", "at": "2026-08-31",
                             "chunks": {"b0": ["https://a", "https://b"]}})
    results = [{"custom_id": "b0", "text": _j.dumps({"flags": {"https://a": "neutral", "https://b": "relevant"}})}]
    batch = {"submit": lambda reqs: "batch_new", "retrieve": lambda i: "ended",
             "results": lambda i: results}
    out = _run_news_flags(_news_kb(["https://a", "https://b", "https://c"]), cache, call=None, batch=batch)
    assert out == {"https://a": "neutral"}
    assert cache.get("news:https://a") == "neutral" and cache.get("news:https://b") == "relevant"
    assert cache.get(_PENDING_KEY)["id"] == "batch_new"   # 남은 c 가 새 배치로


def test_news_flags_sync_fallback_without_batch():
    """batch 미주입(키 없음·SDK 없음) 시 기존 동기 경로 그대로."""
    import json as _j
    from hublib.ai_summary import AiCache, _run_news_flags
    cache = AiCache(path="/nonexistent/x.json")
    call = lambda p, m: _j.dumps({"flags": {"https://a": "neutral"}})
    out = _run_news_flags(_news_kb(["https://a"]), cache, call)
    assert out == {"https://a": "neutral"}
```

Run → FAIL (`_PENDING_KEY` 없음, batch 파라미터 없음).

- [ ] **Step 2 (ai_summary.py 구현):**

```python
_PENDING_KEY = "__news_batch__"


def _news_batch_requests(todo, model, batch=NEWS_BATCH):
    """미분류 뉴스 → (Batches API 요청 목록, {custom_id: [url]} 청크 멤버십). custom_id 'b<i>' 는 40건 묶음 인덱스."""
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    reqs = [{"custom_id": f"b{i}",
             "params": {"model": model, "max_tokens": 1500,
                        "messages": [{"role": "user", "content": NEWS_PROMPT.format(ctx=_j(chunk))}]}}
            for i, chunk in enumerate(chunks)]
    return reqs, {f"b{i}": [it["url"] for it in chunk] for i, chunk in enumerate(chunks)}


def _apply_news_results(cache, results, chunk_urls):
    """배치 결과(각 항목 {'custom_id','text'}) → 항목별 news: 캐시 기록.

    동기 경로(_run_news_flags 의 기존 규칙)와 동일하게: 응답은 왔는데 그 청크의 특정 url 만 빠졌으면
    relevant 로 간주해 캐시한다 — 모델이 매일 같은 url 을 누락해 무한 재제출되는 것을 막는다.
    chunk_urls: {custom_id: [url, ...]} — 제출 시점에 pending 에 함께 저장해 둔 청크 멤버십.
    """
    for r in results:
        d = parse_json(r.get("text") or "")
        flags = d.get("flags") if isinstance(d, dict) and isinstance(d.get("flags"), dict) else {}
        urls = (chunk_urls or {}).get(r.get("custom_id") or "")
        if urls is None:
            urls = list(flags)      # 멤버십 유실(레거시 pending·캐시 롤백) 폴백 — 응답에 있는 url 만이라도 반영(자기 치유)
        for url in urls:
            flag = flags.get(url)
            if flag not in ("neutral", "relevant") and flags:
                flag = "relevant"
            if flag in ("neutral", "relevant"):
                cache.put(f"news:{url}", flag)
```

`_run_news_flags(kb, cache, call, batch=None)`로 시그니처 확장:

```python
def _run_news_flags(kb, cache, call, batch=None):
    if batch is None:
        ...기존 동기 구현 그대로 (ThreadPoolExecutor 경로)...
        return {...기존 반환...}

    # ── 배치 경로: ① 전일 배치 수거 ② 미분류분 새 배치 제출 ③ 캐시 기준 neutral 반환
    pending = cache.get(_PENDING_KEY)
    if isinstance(pending, dict) and pending.get("id"):
        try:
            if batch["retrieve"](pending["id"]) == "ended":
                _apply_news_results(cache, batch["results"](pending["id"]), pending.get("chunks"))
                cache.put(_PENDING_KEY, {})               # 수거 완료
        except Exception as e:
            print(f"  ✗ 뉴스 배치 수거 실패: {repr(e)[:80]}")
    todo = [{"title": n.get("title") or "", "url": n.get("url") or ""}
            for n in ((kb.get("chat") or {}).get("news") or [])
            if n.get("url") and not cache.get(f"news:{n['url']}")]
    still = cache.get(_PENDING_KEY)
    if todo and not (isinstance(still, dict) and still.get("id")):   # 한 번에 한 배치만
        try:
            reqs, chunks = _news_batch_requests(todo[:NEWS_BATCH * NEWS_MAX_BATCHES], batch.get("model", ""))
            bid = batch["submit"](reqs)
            cache.put(_PENDING_KEY, {"id": bid, "at": datetime.date.today().isoformat(), "chunks": chunks})
        except Exception as e:
            print(f"  ✗ 뉴스 배치 제출 실패: {repr(e)[:80]}")
    return {n["url"]: "neutral" for n in ((kb.get("chat") or {}).get("news") or [])
            if n.get("url") and cache.get(f"news:{n['url']}") == "neutral"}
```

(주의: `_news_batch_requests`의 model 인자 배선은 구현 시 정리 — batch dict에 `"model"` 키를 넣어 전달하는 게 간단. `news_batches()` 기존 함수는 동기 경로가 계속 쓰므로 유지.)

`run(kb, cache, call, model="", batch=None)`으로 확장, `"news_flags": _stage(_run_news_flags, kb, cache, call, batch) or {}` — `_stage`가 위치 인자만 받으므로 batch를 위치로 전달.

- [ ] **Step 3 (ai_digest.py — SDK 배선):** `requirements.txt`에 `anthropic` 추가. ai_digest.py에서:

```python
def make_batch_ops(key, model):
    """Batches API — SDK 가 없으면 None(동기 폴백)."""
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic(api_key=key)

    def submit(reqs):
        b = client.messages.batches.create(requests=reqs)
        return b.id

    def retrieve(bid):
        return client.messages.batches.retrieve(bid).processing_status

    def results(bid):
        out = []
        for r in client.messages.batches.results(bid):
            if r.result.type == "succeeded":
                text = next((blk.text for blk in r.result.message.content if blk.type == "text"), "")
                out.append({"custom_id": r.custom_id, "text": text})
        return out

    return {"submit": submit, "retrieve": retrieve, "results": results, "model": model}
```

`main()`에서 `out = run(kb, cache, make_call(key), model=MODEL, batch=make_batch_ops(key, MODEL))`. 동기 `make_call`(urllib)은 weekly/daily/종목 이유용으로 유지 — 파일 주석에 "뉴스만 배치(비용 50%↓, 하루 지연), 나머지는 동기" 설계를 명시.

- [ ] **Step 4:** `python3 -m pytest tests/test_ai_summary.py tests/ generator/test_parse.py -q --ignore=tests/e2e` → PASS. `pip install anthropic` 후 `python3 -c "import anthropic; print(anthropic.__version__)"` 확인. 커밋:

```bash
git add requirements.txt ai_digest.py hublib/ai_summary.py tests/test_ai_summary.py
git commit -m "perf: 뉴스 분류 Batches API 2단계 배치 — 비용 50% 절감, 하루 지연 수용, SDK 미설치 시 동기 폴백"
```

**리스크 노트:** 첫 머지 후 이틀간은 뉴스 플래그가 비거나 부분적일 수 있다(첫날 제출만, 둘째 날부터 수거) — 정상. `_PENDING_KEY`가 ai_cache.json(롤링 캐시)에 실리므로 캐시 유실 시 배치 id 를 잃지만, 잃으면 그 배치 결과만 버려지고 다음 빌드가 재제출 — 자기 치유. 배치 내 개별 요청이 `errored`/`expired`면 results에 해당 custom_id 가 없어 그 청크 url 들이 캐시 안 되고 **다음날 자동 재제출**된다 — 의도된 자기 치유이며 비용은 재시도 1회분.

---

## 마무리: 검증·PR

- [ ] 전체 유닛: `python3 -m pytest tests/ generator/test_parse.py -q --ignore=tests/e2e` → PASS
- [ ] 전체 E2E: `-n 4`로 3회 반복 그린
- [ ] `main` 머지 후 첫 CI 확인 항목: ① E2E 스텝 ~53s → ~30s(캐시 히트 시 더 짧게), ② Collect에 히스토리 40종목 로그(`시장 히스토리 40/40`), ③ Job Summary에 hub.app.*.js 등장, ④ Pages에서 홈 스파크라인·분석 막대 SVG 렌더 확인, ⑤ 다음날 빌드에서 `뉴스 배치 수거` 로그
- [ ] 롤백 단위: 태스크별 커밋 — 특히 C3(SVG)가 시각 회귀 시 단독 revert 가능

## 명시적 제외 (이번에도 안 함)

- Chart.js tree-shake 빌드(노드 툴체인 도입) — C3의 SVG 대체가 이를 무의미하게 만듦
- weekly/daily/종목 이유의 Batches 전환 — 당일성 필요(다이제스트는 그날 아침 내용이어야 함)
- CSS 해시 분리 — 앱 JS 대비 효과 작음(gz ~10KB), 셸 재다운로드는 C2로 대부분 해소
