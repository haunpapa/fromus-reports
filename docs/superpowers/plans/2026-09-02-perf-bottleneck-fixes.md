# 성능 병목 수정 구현 계획 (2026-09-02 진단 기반)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-09-02 병목 진단에서 확인된 개선안을 적용해 CI 빌드를 4분 14초 → 약 2분으로 단축하고, 배포 아티팩트 14MB 낭비·AI 비용 반복 지출·프론트 부트 지연을 제거한다.

**Architecture:** 5개 페이즈로 나눈다 — ① 즉효 원라이너(배포·데이터 중복 제거), ② 네트워크 병렬화(최대 단일 병목), ③ CI 정비(캐시·설치), ④ AI 비용 누수 차단, ⑤ 프론트 부트 경로. 각 태스크는 독립적으로 머지 가능하며, 페이즈 순서 = 투자 대비 효과 순서다. 검증은 기존 pytest 스위트(tests/ + generator/test_parse.py)와 E2E(tests/e2e)로 한다.

**Tech Stack:** Python 3.11 (bs4/lxml/yfinance/FinanceDataReader), GitHub Actions (Pages artifact 배포), Playwright E2E, 바닐라 JS 셸(hub/*.js → hub_template.html 인라인).

**사전 조건:**
- 작업 브랜치: `perf/bottleneck-fixes` (main 직접 커밋 금지)
- 로컬 테스트 실행법: `python -m pytest tests/ generator/test_parse.py -q` (네트워크 없이 동작해야 함)
- E2E 로컬 실행법: `python build_hub.py --phase render && mkdir -p _site && cp hub.html kb.*.json version.json sw.js _site/ && cp -r vendor _site/ && E2E_SITE_DIR=_site python -m pytest tests/e2e -q` (chromium 필요: `python -m playwright install chromium`)
- CI 검증: push 후 Actions "Build & Deploy" 워크플로 확인. 이 리포는 **생성물을 커밋하지 않는다** — `hub.html`, `kb.*.json`, `knowledge_base.json` 등이 로컬에 생겨도 절대 `git add` 하지 말 것 (.gitignore 에 이미 있음).

---

## Phase 1 — 즉효 원라이너 (각 10분 이내, 서로 독립)

### Task 1: `knowledge_base.json` 배포 제거

클라이언트는 이 파일을 fetch하지 않는다(`window.KB_URL`이 렌더 시 `kb.*` 매니페스트로 치환되고, `hub/*.js`·`sw.js`·`index.html`에 `knowledge_base` 문자열 0건). 매일 14MB(gz 3.3MB)를 Pages에 올리는 것은 순수 낭비.

**Files:**
- Modify: `.github/workflows/build.yml:114`

- [ ] **Step 1: 참조 없음 재확인 (안전망)**

Run: `grep -rn "knowledge_base" hub/ sw.js index.html trade.html || echo "OK: 참조 없음"`
Expected: `OK: 참조 없음`

주의: `hub_template.html:765`에는 `window.KB_URL = /*KBURL*/"knowledge_base.json"/*ENDKBURL*/;` **플레이스홀더가 있다** — 렌더 시 `kb.*` 매니페스트로 치환되므로 배포본(`hub.html`)에는 남지 않는다. 그래서 grep 대상에서 의도적으로 뺐다. 확인하려면: `grep -c "knowledge_base" hub.html` → `0` (렌더된 셸 기준). 빌드 스크립트(`build_hub.py`/`hublib/`)의 히트도 무관 — 중간 산출물 용도.

- [ ] **Step 2: build.yml 수정**

`.github/workflows/build.yml:114`의 Assemble site 스텝에서:

```yaml
# 변경 전
          cp index.html hub.html knowledge_base.json trade.html manifest.webmanifest sw.js _site/
# 변경 후 (knowledge_base.json 제거)
          cp index.html hub.html trade.html manifest.webmanifest sw.js _site/
```

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/build.yml
git commit -m "perf: knowledge_base.json(14MB) Pages 배포 제외 — 클라이언트 미사용 중간 산출물"
```

---

### Task 2: 검색 인덱스 `hay` 필드 제거 (kb.search −39%)

`hay`는 같은 레코드의 `title+snippet+tags+kind`를 소문자로 이어붙인 순수 파생 데이터로 kb.search 5.25MB 중 2.03MB(39%)를 차지한다. 클라이언트 폴백이 이미 존재한다 — `hub/30_search.js:11`의 `SEARCH = (D.search||[]).map(it=> it.hay ? it : {...it, hay: hayOf(it)})`. 서버측 부착만 제거하면 **JS 수정 없이** 끝난다.

**Files:**
- Modify: `hublib/search.py:18-20` (`with_hay`), `hublib/search.py:40` (`_news_items`), `hublib/search.py:56` (`_opinion_items`)
- Test: `tests/test_search.py:23-29, 45` (기존 테스트가 hay 존재를 단언하므로 먼저 뒤집는다)

- [ ] **Step 1: 기존 테스트를 새 계약으로 수정 (RED)**

`tests/test_search.py`의 `test_with_hay_adds_lowercase_haystack_and_source`를 다음으로 교체:

```python
def test_with_hay_adds_source_but_not_hay():
    """hay 는 클라이언트(30_search.js hayOf)가 재계산한다 — 전송량 39% 절감 (2026-09)."""
    from hublib.search import with_hay
    items = [{"title": "SK하이닉스", "snippet": "HBM 수혜", "tags": ["반도체·메모리"], "kind": "종목"}]
    out = with_hay(items)
    assert out[0]["source"] == "report"
    assert "hay" not in out[0], "hay 는 더 이상 서버에서 만들지 않는다"
    assert "hay" not in items[0], "입력을 변경하면 안 된다"
```

같은 파일 45행 부근, 채팅 항목 테스트의 `assert all(i["source"] == "chat" and i["hay"] for i in out)`를:

```python
    assert all(i["source"] == "chat" and "hay" not in i for i in out)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_search.py -q`
Expected: FAIL (아직 서버가 hay를 부착하므로)

- [ ] **Step 3: 구현 — hay 부착 3곳 제거**

`hublib/search.py`:

```python
# with_hay (18-20행) — hay 제거, source 만 유지
def with_hay(items):
    """리포트 인덱스 항목에 source 를 붙인 새 리스트. hay 는 클라이언트가 재계산한다(30_search.js hayOf)."""
    return [{**it, "source": it.get("source", "report")} for it in (items or [])]
```

`_news_items` 40행: `out.append({**it, "hay": _hay(it)})` → `out.append(it)`
`_opinion_items` 56행: `out.append({**it, "hay": _hay(it)})` → `out.append(it)`
`_hay` 함수(13-15행)는 이제 미사용 — 삭제. 모듈 docstring(2행)의 "사전 토큰화(hay)" 문구도 갱신.

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `python -m pytest tests/ generator/test_parse.py -q`
Expected: PASS (참고: `tests/test_budget.py:10` 주석의 "hay 사전 토큰화(raw 의 약 40%)"는 사실 서술이므로 함께 갱신. 예산 상한은 상한이라 축소 방향에선 통과)

- [ ] **Step 5: E2E로 검색 동작 확인**

Run: 사전 조건의 E2E 로컬 실행법 사용, 또는 최소한 `python -m pytest tests/e2e -k search -q`
Expected: PASS — hay 없는 kb.search에서 폴백 경로(`hayOf`)로 검색 정상 동작

- [ ] **Step 6: 커밋**

```bash
git add hublib/search.py tests/test_search.py tests/test_budget.py
git commit -m "perf: 검색 인덱스 hay 필드 제거 — kb.search 39% 축소, 클라이언트 폴백(hayOf) 활용"
```

---

### Task 3: KRX 전종목 목록 중복 다운로드 제거

`_load_krx_listing`이 빌드당 2번 호출된다(①`enrich_market_momentum`→`_build_ticker_map`, ②`build_verify`→`_krx_market_lookup`). `lru_cache`는 `_build_ticker_map`(momentum.py:121)에만 있다. −5~15초 + 네트워크 실패 리스크 절반.

**Files:**
- Modify: `hublib/momentum.py:92`
- Test: `tests/test_verify.py` 또는 신규 테스트 함수 추가 (기존 파일에)

- [ ] **Step 1: 실패하는 테스트 작성 (RED)**

`tests/test_verify.py` 끝에 추가:

```python
def test_krx_listing_downloads_once_per_build(monkeypatch):
    """momentum 과 verify 가 KRX 목록을 공유한다 — 빌드당 다운로드 1회 (2026-09 진단)."""
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
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_verify.py::test_krx_listing_downloads_once_per_build -q`
Expected: FAIL — `AttributeError: 'function' object has no attribute 'cache_clear'`

- [ ] **Step 3: 구현**

`hublib/momentum.py:92`:

```python
@functools.lru_cache(maxsize=1)   # 한 빌드에서 KRX 목록은 한 번만 — momentum 과 verify 가 공유한다 (호출자는 읽기 전용)
def _load_krx_listing():
```

주의 2가지: ① 반환 리스트를 호출자가 변경하면 안 된다 — 현재 두 호출자(`_build_ticker_map`, `_krx_market_lookup`) 모두 읽기 전용임을 확인했다. ② 실패 시 `[]`가 캐시되어 같은 빌드 안에서 재시도하지 않게 되는데, 기존에도 두 호출 다 실패-폴백 경로가 있으므로 동작 저하 없음. `momentum.py:121` `_build_ticker_map`의 기존 주석(같은 문구)은 이 함수로 옮겨졌으니 그쪽은 "(_load_krx_listing 이 캐시한다)"로 갱신.

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add hublib/momentum.py tests/test_verify.py
git commit -m "perf: KRX 전종목 목록 lru_cache — 빌드당 2회 다운로드를 1회로"
```

---

### Task 4: 14MB `knowledge_base.json` 전량 재기록 삭제

`render()`가 2KB짜리 `ai_digest.json`을 주입하려고 14MB 전체를 다시 쓴다(render.py:276-277). `ai_digest`는 어차피 `split_payload` → `kb.core.*.json`으로 나가므로 원본 재기록은 소비자가 없다.

**Files:**
- Modify: `hublib/render.py:270-277`, `tests/test_phases.py:57-59` (기존 테스트가 재기록을 단언하므로 먼저 뒤집는다)

- [ ] **Step 1: 소비자 없음 확인 (안전망)**

Run: `grep -rn "knowledge_base" merge_hub.py build_index.py ai_digest.py`
Expected: `knowledge_base.json`을 **render 이후에** 다시 읽어 `ai_digest` 키를 기대하는 코드가 없어야 한다. (`ai_digest.py`는 render **이전** 스텝에서 collect 산출물을 읽으므로 무관. 예상 밖의 히트가 있으면 이 태스크를 중단하고 보고할 것. `tests/test_phases.py:57-59`의 재기록 단언은 **알려진 소비자**로, 바로 다음 스텝에서 새 계약으로 뒤집는다.)

- [ ] **Step 2: 기존 테스트를 새 계약으로 수정 (RED)**

`tests/test_phases.py:57-59`의 재기록 단언을 교체:

```python
    # 변경 전
    # render 가 knowledge_base.json 에도 다이제스트를 반영했는지
    kb2 = json.loads((src / "kb_raw.json").read_text(encoding="utf-8"))
    assert kb2["ai_digest"]["digest"]["title"] == "테스트다이제스트"

    # 변경 후
    # render 는 원본 kb 를 재기록하지 않는다 — ai_digest 는 kb.core 로만 나간다 (2026-09 진단 Task 4)
    kb2 = json.loads((src / "kb_raw.json").read_text(encoding="utf-8"))
    assert kb2["ai_digest"] is None, "render 가 knowledge_base.json 을 재기록하면 안 된다"
```

Run: `python -m pytest tests/test_phases.py::test_collect_then_render -q`
Expected: FAIL — 아직 render가 재기록하므로 `kb2["ai_digest"]`가 채워져 있다

- [ ] **Step 3: 구현 — 재기록 2줄 삭제**

`hublib/render.py` 270-277행에서 재기록 부분만 제거:

```python
    # AI 위클리 다이제스트 반영 (ai_digest.py 산출물 — 없으면 무시)
    try:
        if os.path.exists("ai_digest.json"):
            with open("ai_digest.json", encoding="utf-8") as f:
                data["ai_digest"] = json.load(f)
            print("ℹ️ ai_digest.json 반영")
            flags = (data["ai_digest"] or {}).get("news_flags") or {}
            if flags:
                data = _apply_news_flags(data, flags)
    except Exception as e:
        print(f"ℹ️ ai_digest.json 읽기 실패 — 무시 ({e})")
```

(삭제되는 것: `with open(json_in, "w", ...) as f: json.dump(data, f, ...)` 2줄과 주석의 "+ knowledge_base.json 재기록" 문구)

- [ ] **Step 4: 두 페이즈 통합 테스트 통과 확인 (GREEN)**

Run: `python -m pytest tests/test_phases.py tests/test_split.py -q`
Expected: PASS — Step 2에서 뒤집은 단언 포함

- [ ] **Step 5: 커밋**

```bash
git add hublib/render.py tests/test_phases.py
git commit -m "perf: render 단계의 knowledge_base.json 전량 재기록 삭제 — ai_digest 는 kb.core 로만 나간다"
```

---

## Phase 2 — 최대 단일 병목: 가격 수집 병렬화 (−90초)

### Task 5: `fetch_prices` 스레드풀 병렬화

96개 고유 티커를 완전 직렬로 요청해 CI Collect 126초의 대부분(~120초)을 차지한다. loader는 순수 HTTP 함수라 스레드 안전. **캐시 쓰기(`cache.put`)는 메인 스레드에서만** 수행한다(PriceCache는 thread-safe가 아님) — `hublib/ai_summary.py:171-179`가 이미 쓰는 패턴과 동일.

**Files:**
- Modify: `hublib/verify.py:366-399`
- Test: `tests/test_verify.py` (기존 fetch_prices 테스트 4개가 회귀 방지막; 병렬 격리 테스트 1개 추가)

- [ ] **Step 1: 실패 격리 병렬 테스트 작성 (RED 아님 — 기존 계약 고정)**

`tests/test_verify.py`의 fetch_prices 테스트들 옆에 추가:

```python
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
```

Run: `python -m pytest tests/test_verify.py::test_fetch_prices_parallel_isolates_failures -q`
Expected: PASS (직렬 구현에서도 통과 — 이 테스트는 병렬화가 깨뜨리면 안 되는 계약의 고정 장치)

- [ ] **Step 2: 구현 — 네트워크만 풀로, 캐시 쓰기는 메인 스레드**

`hublib/verify.py`의 `fetch_prices`를 교체 (파일 상단에 `from concurrent.futures import ThreadPoolExecutor` 추가):

```python
PRICE_WORKERS = 8   # 직렬 96티커 ≈ 120초 → 8워커 ≈ 15~30초. 소스별 레이트리밋 안쪽.


def fetch_prices(calls, cache, loaders=None, workers=PRICE_WORKERS):
    """콜 목록 → {'<market>:<ticker>': [(date, close)]}.

    종목당 1회만 요청하고, 캐시가 있으면 마지막 날부터 증분만 받는다.
    네트워크 호출만 스레드풀로 겹치고, 캐시 쓰기는 메인 스레드에서만 한다(PriceCache 는 thread-safe 아님).
    한 종목이 실패해도 빈 시계열로 격리하고 나머지는 계속한다.
    """
    loaders = loaders or DEFAULT_LOADERS
    wanted = {}
    for c in calls:
        key = f"{c['market']}:{c['ticker']}"
        prev = wanted.get(key)
        if prev is None or c["date"] < prev["first"]:
            wanted[key] = {"market": c["market"], "ticker": c["ticker"], "first": c["date"]}

    def _one(key):                      # 워커: 읽기(cache.get/last)와 네트워크만 — 쓰기 없음
        w = wanted[key]
        loader = loaders.get(w["market"])
        old = cache.get(key)
        if loader is None:
            return key, old, None
        start = _start_for(cache.last(key), w["first"])
        try:
            return key, old, loader(w["ticker"], start)
        except Exception as e:
            print(f"  ✗ 검증 가격 {key} 실패: {repr(e)[:100]}")
            return key, old, None

    out = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(_one, sorted(wanted)))   # 입력 순서 보존 → 결정론 유지
    for key, old, fresh in results:                    # 캐시 쓰기는 여기(메인 스레드)서만
        if fresh is None:
            out[key] = old
            continue
        points = merge_points(old, fresh)
        if points:
            cache.put(key, points)
        out[key] = points
    return out
```

설계 근거: 워커에서 `cache.get`/`cache.last`는 dict **읽기**뿐이고 쓰기는 결과 수집 후 메인 스레드에서만 일어나므로 경합 없음. `ex.map` + `sorted(wanted)`로 처리 순서·출력이 직렬 구현과 동일(결정론).

- [ ] **Step 3: 기존 계약 전체 통과 확인**

Run: `python -m pytest tests/test_verify.py -q`
Expected: PASS — 특히 `test_fetch_prices_uses_cache_and_only_requests_the_gap`, `test_fetch_prices_cold_start_reaches_back_before_first_call` (증분·콜드스타트 계약 유지)

- [ ] **Step 4: 커밋**

```bash
git add hublib/verify.py tests/test_verify.py
git commit -m "perf: fetch_prices 8워커 병렬화 — CI Collect 120초→약 20초, 캐시 쓰기는 메인 스레드 유지"
```

**주의 (YAGNI):** `fetch_benchmarks`(2~3회 요청, ~3초)와 지수 3종(`fetch_index_series`)은 이번에 건드리지 않는다 — 효과 대비 리스크가 낮은 후속 후보로 남긴다. `momentum.py`의 SIGALRM 교체(병렬화 선행 조건)도 별도 계획으로 분리한다(죽어 있는 정밀 보강 레이어 복구와 묶어서).

---

## Phase 3 — CI 정비

### Task 6: requirements 통합 + pip 캐시

pip 설치가 4곳에 분산되어 있다: build.yml 3곳(47, 105, 121행대) + `momentum.py:86`의 **런타임 자동 설치**(CI에서 매번 6초). `requirements-dev.txt`는 존재하지만 워크플로가 안 쓴다(드리프트).

**Files:**
- Create: `requirements.txt`
- Modify: `requirements-dev.txt`, `.github/workflows/build.yml:43-48, 105-106, 121-125`

- [ ] **Step 1: requirements.txt 생성**

```
# 빌드(collect·render) 런타임 의존성 — CI 와 로컬이 같은 목록을 쓴다
beautifulsoup4
lxml
yfinance
finance-datareader
```

- [ ] **Step 2: requirements-dev.txt 갱신**

```
-r requirements.txt
pytest>=8
pytest-playwright>=0.5
playwright==1.55.0
```

주의: `playwright` 핀 버전은 작성 시점의 최신 안정판으로 맞춘다 — `pip index versions playwright` 로 확인 후 기입 (핀 목적은 Task 7의 브라우저 캐시 키 안정화).

- [ ] **Step 3: build.yml 설치 스텝 통합**

```yaml
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: requirements*.txt

      - name: Install deps
        run: pip install -r requirements-dev.txt
```

그리고: `Run tests` 스텝에서 `pip install pytest && ` 제거, `Install Playwright` 스텝에서 `pip install pytest-playwright` 제거(Task 7에서 스텝 자체를 재구성). `Collect` 스텝에 런타임 pip 금지 환경 변수 추가:

```yaml
      - name: Collect (파싱·집계·시세 — 1회만)
        env:
          MARKET_MOMENTUM_AUTO_INSTALL: "0"   # CI 는 requirements 로만 설치 — 런타임 pip 금지(누락 시 조용한 6초 대신 즉시 실패)
          PYTHONUNBUFFERED: "1"               # 로그 실시간 flush — 스텝 내부 구간 프로파일링 가능하게
        run: python build_hub.py --phase collect --src . --json knowledge_base.json
```

- [ ] **Step 4: 로컬 스모크**

Run: `pip install -r requirements-dev.txt && python -m pytest tests/ generator/test_parse.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add requirements.txt requirements-dev.txt .github/workflows/build.yml
git commit -m "ci: pip 설치 4곳 → requirements 단일화 + setup-python pip 캐시, CI 런타임 pip 금지"
```

---

### Task 7: Playwright 브라우저 캐시 키 수리 (현재 실제로 깨져 있음)

`python -c 'import playwright; print(playwright.__version__)'`이 `AttributeError`를 내는데 echo는 성공해 조용히 통과 → 캐시 키가 `pw-browsers-Linux-`(버전 빈 문자열)로 영구 고정. CI 로그로 확인된 실제 버그다. 버전이 올라가는 순간 "히트하지만 낡은 브라우저 → 재다운로드 → 저장은 영구 스킵" 상태가 된다.

**Files:**
- Modify: `.github/workflows/build.yml:121-138`

- [ ] **Step 1: 스텝 재구성**

```yaml
      - name: Playwright version
        id: pw
        run: echo "version=$(python -c 'import importlib.metadata as m; print(m.version("playwright"))')" >> "$GITHUB_OUTPUT"

      # 브라우저 리비전은 playwright 버전에 따라간다 — 버전이 캐시 키. 핀(requirements-dev.txt)으로 키가 안정된다.
      - name: Restore Playwright browsers
        id: pwcache
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: pw-browsers-${{ runner.os }}-${{ steps.pw.outputs.version }}

      - name: E2E 스모크 (셸 JS — _site 기준)
        run: |
          if [ "${{ steps.pwcache.outputs.cache-hit }}" = "true" ]; then
            python -m playwright install chromium          # 캐시 히트 — 브라우저 다운로드·apt 생략
          else
            python -m playwright install --with-deps chromium
          fi
          E2E_SITE_DIR=_site python -m pytest tests/e2e -q
```

- [ ] **Step 2: 좀비 캐시 제거 (1회성)**

Run: `gh cache delete "pw-browsers-Linux-" -R haunpapa/fromus-reports || true`
Expected: 282MB 빈-버전 키 캐시 삭제 (이미 없으면 무시)

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/build.yml
git commit -m "ci: Playwright 브라우저 캐시 키 수리(importlib.metadata) + 히트 시 apt 12초 생략"
```

**리스크 노트:** 캐시 히트 시 `--with-deps`(apt)를 건너뛴다. ubuntu-latest 러너에 chromium 시스템 라이브러리가 이미 있어 대부분 무해하지만, **첫 CI 실행에서 E2E가 라이브러리 누락으로 실패하면** `--with-deps`를 조건 없이 되돌리고 브라우저 캐시만 유지한다(그래도 키 수리 효과는 남는다).

---

### Task 8: 롤링 캐시 3종 restore/save 분리 (실패일 캐시 유실 방지)

`actions/cache@v4`는 job이 실패하면 post-save를 건너뛴다. E2E가 하루 깨지면 그날 price/ai/kb_summary가 저장되지 않아 다음 날 이틀 전 캐시로 증분 구간이 2배가 된다. `cancel-in-progress` 취소 시에도 동일. run_id 키 자체는 의도된 롤링 패턴이므로 유지한다.

**Files:**
- Modify: `.github/workflows/build.yml:66-79, 88-93` (restore로 교체) + E2E 스텝 뒤에 save 3개 추가

- [ ] **Step 1: 기존 3개 캐시 스텝을 `actions/cache/restore@v4`로 교체**

`uses: actions/cache@v4` → `uses: actions/cache/restore@v4` (price-cache, kb-summary, ai-cache 3곳 — path/key/restore-keys는 그대로).

- [ ] **Step 2: E2E 스텝 직후에 save 3개 추가**

```yaml
      # 테스트가 깨진 날에도 그날 수집분은 저장한다 — 다음 빌드의 증분 구간이 늘지 않게 (restore 와 짝).
      # hashFiles 가드: Collect 이전에 job 이 죽으면 파일이 없다 — 빈 경로 save 에러(로그 노이즈) 방지.
      - name: Save price cache
        if: always() && hashFiles('build/price_cache.json') != ''
        uses: actions/cache/save@v4
        with:
          path: build/price_cache.json
          key: price-cache-v1-${{ github.run_id }}

      - name: Save kb summary
        if: always() && hashFiles('build/kb_summary.json') != ''
        uses: actions/cache/save@v4
        with:
          path: build/kb_summary.json
          key: kb-summary-${{ github.run_id }}

      - name: Save AI cache
        if: always() && hashFiles('build/ai_cache.json') != ''
        uses: actions/cache/save@v4
        with:
          path: build/ai_cache.json
          key: ai-cache-v1-${{ github.run_id }}
```

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/build.yml
git commit -m "ci: 롤링 캐시 3종 restore/save 분리 — 테스트 실패일에도 당일 수집분 보존"
```

---

### Task 9: 크론 주중 한정 + 타임아웃 + 검증

주말 크론 2회는 금요일 종가와 동일한 데이터로 6분 전량 재빌드다(순수 낭비). 그리고 `fetch_prices`의 FDR 경로에는 타임아웃이 없어 행 시 6시간 러너를 태울 수 있다.

**Files:**
- Modify: `.github/workflows/build.yml:24-25, 38-39`

- [ ] **Step 1: 크론·타임아웃 수정**

```yaml
  schedule:
    - cron: '30 22 * * 0-4'   # UTC 일~목 22:30 = KST 월~금 07:30 — 직전 거래일 종가 반영. 주말 아침 2회는 금요일과 동일 데이터라 생략
```

주의: KST 월요일 07:30 = UTC **일요일** 22:30이다. "월~금 KST 아침"을 원하면 `0-4`(일~목 UTC)가 맞다 — `1-5`로 쓰면 KST 화~토가 되어 월요일 아침 갱신이 빠진다.

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20        # fetch_prices 행 방어 — 정상 빌드는 5분 이내
```

- [ ] **Step 2: 커밋 + CI 전체 검증**

```bash
git add .github/workflows/build.yml
git commit -m "ci: 크론 주중(KST 월~금 아침) 한정 + job 타임아웃 20분"
git push -u origin perf/bottleneck-fixes
```

이후 `gh workflow run "Build & Deploy" --ref perf/bottleneck-fixes` 대신 — 이 워크플로는 main push/schedule 전용이므로 — **PR을 열어 리뷰 후 main 머지로 검증**한다. 머지 후 첫 실행에서 확인할 것: ① Collect 소요(126s → 30s대), ② `pw-browsers-Linux-1.55.0` 키로 저장, ③ `_site`에 knowledge_base.json 없음(Assemble 로그), ④ Job Summary의 kb 크기에서 search 청크 ~3.2MB.

---

## Phase 4 — AI 비용 누수 차단

### Task 10: 실패 응답 센티널 캐시

`_cached_or_call`(ai_summary.py:116-128)은 파싱 실패 시 캐시에 아무것도 남기지 않아 **매 빌드 동일 프롬프트를 재전송**한다. 계속 실패하는 항목이 하나라도 있으면 비용이 무한 반복된다.

**Files:**
- Modify: `hublib/ai_summary.py:116-128` (`_cached_or_call`), `hublib/ai_summary.py:86-101` (`stock_jobs`), `hublib/ai_summary.py:153-158` (캐시 폴백 읽기)
- Test: `tests/test_ai_summary.py`

- [ ] **Step 1: 실패하는 테스트 작성 (RED)**

`tests/test_ai_summary.py`에 추가 (기존 테스트의 fake cache/call 픽스처 스타일을 따를 것 — 파일을 먼저 읽고 기존 헬퍼 재사용):

```python
def test_failed_call_writes_sentinel_and_stops_after_max():
    """실패도 캐시한다 — FAIL_MAX 회 이후엔 재호출하지 않는다 (비용 무한 반복 차단, 2026-09)."""
    from hublib.ai_summary import AiCache, _cached_or_call, FAIL_MAX
    cache = AiCache(path="/nonexistent/skip-load.json")
    calls = {"n": 0}

    def bad_call(prompt, max_tokens):
        calls["n"] += 1
        return "이건 JSON 이 아님"

    for _ in range(FAIL_MAX + 2):
        assert _cached_or_call(cache, "k", "p", bad_call, 100, lambda d: d) is None
    assert calls["n"] == FAIL_MAX          # 이후 호출은 센티널이 흡수


def test_success_after_failure_overwrites_sentinel():
    from hublib.ai_summary import AiCache, _cached_or_call
    cache = AiCache(path="/nonexistent/skip-load.json")
    assert _cached_or_call(cache, "k", "p", lambda p, m: "깨진 응답", 100, lambda d: d) is None
    ok = _cached_or_call(cache, "k", "p", lambda p, m: '{"text": "정상"}', 100, lambda d: d)
    assert ok == {"text": "정상"}
    assert _cached_or_call(cache, "k", "p", lambda p, m: (_ for _ in ()).throw(RuntimeError()), 100, lambda d: d) == {"text": "정상"}


def test_stock_jobs_retries_key_with_fail_sentinel():
    """실패 센티널은 '결과 있음'이 아니다 — stock_jobs 가 재시도 대상으로 취급해야 한다."""
    from hublib.ai_summary import AiCache, stock_jobs, _FAIL_KEY
    cache = AiCache(path="/nonexistent/skip-load.json")
    kb = {"stocks": [{"name": "삼성전자", "count": 3,
                      "mentions": [{"date": "2026-09-01", "label": "l", "note": "n"}]}]}
    cache.put("stock:삼성전자:2026-09-01", {_FAIL_KEY: {"n": 1, "at": "2026-09-01"}})
    assert [j["name"] for j in stock_jobs(kb, cache)] == ["삼성전자"]
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_ai_summary.py -q`
Expected: FAIL — `ImportError: cannot import name 'FAIL_MAX'`

- [ ] **Step 3: 구현**

`hublib/ai_summary.py` — 상수·헬퍼 추가 후 `_cached_or_call` 교체:

```python
_FAIL_KEY = "__fail__"
FAIL_MAX = 3           # 이 횟수 연속 실패하면 TTL 동안 재시도하지 않는다
FAIL_TTL_DAYS = 7      # TTL 이 지나면 1회 더 시도 (모델·프롬프트가 고쳐졌을 수 있다)


def _fail_info(hit):
    """캐시 값이 실패 센티널이면 그 dict, 아니면 None."""
    return hit[_FAIL_KEY] if isinstance(hit, dict) and _FAIL_KEY in hit else None


def _usable(hit):
    """진짜 결과인가 — 실패 센티널·None 은 결과가 아니다."""
    return hit is not None and _fail_info(hit) is None


def _cached_or_call(cache, key, prompt, call, max_tokens, parse):
    """캐시 히트면 그대로. 실패도 센티널로 캐시해 FAIL_MAX 회 이후 TTL 까지 재호출하지 않는다."""
    hit = cache.get(key)
    fail = _fail_info(hit)
    if fail:
        expiry = (datetime.date.fromisoformat(fail["at"]) + datetime.timedelta(days=FAIL_TTL_DAYS)).isoformat()
        if fail.get("n", 0) >= FAIL_MAX and datetime.date.today().isoformat() < expiry:
            return None
        hit = None
    if hit is not None:
        return hit
    try:
        val = parse(parse_json(call(prompt, max_tokens)))
    except Exception as e:
        print(f"  ✗ AI {key}: {repr(e)[:80]}")
        val = None
    if val is not None:
        cache.put(key, val)                                     # 성공이 센티널을 덮는다
    else:
        n = (fail or {}).get("n", 0) + 1
        cache.put(key, {_FAIL_KEY: {"n": n, "at": datetime.date.today().isoformat()}})
    return val
```

`stock_jobs` 95행: `if cache.get(key):` → `if _usable(cache.get(key)):`
`_run_stock_reasons` 156-158행: `hit = cache.get(...)` 뒤 `if hit:` → `if _usable(hit):`

주의: `_run_daily`처럼 **정당하게 None을 반환하는 경우**(오늘 스탠스 없음)는 `_cached_or_call` 진입 전에 걸러지므로 센티널이 오염시키지 않는다. `news:` 키는 문자열 값이라 `_fail_info`가 None을 반환해 무해.

스레드 각주: `_run_stock_reasons`는 `_cached_or_call`을 워커 스레드에서 호출하므로 센티널 `cache.put`도 워커에서 일어난다 — **성공 캐시 기록이 원래부터 그랬고**(기존 동작), CPython dict 단일 연산이라 안전하다. Task 5의 "캐시 쓰기는 메인 스레드" 원칙은 PriceCache(다단계 쓰기)에 대한 것이며 AiCache의 기존 관례와 충돌하지 않는다.

- [ ] **Step 4: 통과 확인 + 전체 회귀**

Run: `python -m pytest tests/test_ai_summary.py tests/ -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add hublib/ai_summary.py tests/test_ai_summary.py
git commit -m "fix: AI 실패 응답 센티널 캐시 — 3회 실패 시 7일간 재호출 중단, 비용 무한 반복 차단"
```

---

## Phase 5 — 프론트 부트 경로 (FCP)

### Task 11: `kb.core` preload 주입

190KB 셸을 다 파싱한 뒤에야 core JSON(gz 344KB) fetch가 시작된다. `<head>`에 해시 URL preload를 렌더 시 주입하면 수백 ms 단축.

**Files:**
- Modify: `hub_template.html` (head, ~20행 부근), `hublib/render.py:306-316`
- Test: `tests/test_split.py` 또는 신규 함수 (렌더 셸 주입은 기존 테스트 파일 관례를 따른다 — `grep -rn "KBURL" tests/`로 기존 셸 치환 테스트 위치 확인 후 그 옆에 추가) + `tests/test_phases.py` 통합 단언 1줄

- [ ] **Step 1: 실패하는 테스트 작성 (RED)**

```python
def test_inject_core_preload_replaces_marker():
    from hublib.render import inject_core_preload
    shell = "<head>\n<!--KBPRELOAD-->\n</head>"
    out = inject_core_preload(shell, "kb.core.abc123.json")
    assert '<link rel="preload" as="fetch" type="application/json" href="./kb.core.abc123.json" crossorigin>' in out
    assert "<!--KBPRELOAD-->" not in out


def test_inject_core_preload_is_noop_without_marker():
    from hublib.render import inject_core_preload
    assert inject_core_preload("<head></head>", "kb.core.x.json") == "<head></head>"
```

Run 후 Expected: FAIL — `ImportError`

- [ ] **Step 2: 구현**

`hublib/render.py`에 순수 함수 추가:

```python
def inject_core_preload(shell, core_name):
    """<head> 의 KBPRELOAD 마커를 core 청크 preload 링크로 치환. 마커 없으면(구 템플릿) 그대로."""
    link = f'<link rel="preload" as="fetch" type="application/json" href="./{core_name}" crossorigin>'
    return shell.replace("<!--KBPRELOAD-->", link)
```

`render()`의 셸 처리부(312행 KBURL 치환 직전)에 `shell = inject_core_preload(shell, manifest["core"])` 한 줄 추가.

`hub_template.html` head — 테마 조기 적용 `<script>` 블록 바로 아래에 마커 추가:

```html
<!--KBPRELOAD-->
```

- [ ] **Step 3: 통합 커버리지 — test_phases 셸 검사에 단언 1줄 추가**

`tests/test_phases.py::test_collect_then_render`의 셸 검사부(49행 `man = json.loads(...)` 부근)에:

```python
    assert f'href="./{man["core"]}"' in shell and 'rel="preload"' in shell, "core preload 링크가 셸에 주입돼야 함"
```

- [ ] **Step 4: 통과 + E2E 확인**

Run: `python -m pytest tests/ -q` 그리고 E2E 로컬 실행(사전 조건 참고)
Expected: PASS. 렌더된 `hub.html` head에 preload 링크가 실제 해시로 들어갔는지 육안 확인: `grep "rel=\"preload\"" hub.html`

- [ ] **Step 5: 커밋**

```bash
git add hublib/render.py hub_template.html tests/
git commit -m "perf: kb.core preload 주입 — 셸 파싱 완료 전에 core fetch 시작"
```

---

### Task 12: Chart.js 부트 게이트 제거

부트가 `chart.umd.min.js`(200KB, self-host) load를 최대 3초까지 기다린다(hub_template.html:792-796). 실사용처 2곳(`hub/20_home.js`, `hub/80_analytics.js`)에는 이미 `if(!window.Chart)` 가드가 있다.

**Files:**
- Modify: `hub_template.html:792-796` (대기 블록), `hub/20_home.js`, `hub/80_analytics.js` (지연 도착 시 재그리기)

- [ ] **Step 1: 현재 가드 동작 파악**

Run: `grep -n "window.Chart" hub/20_home.js hub/80_analytics.js`
가드가 "차트만 건너뛰고 나머지는 그린다" 형태인지 확인. 차트 그리는 함수명(예: 스파크라인 렌더 함수)을 기록해 둔다 — Step 3의 재그리기 훅에서 호출할 대상.

- [ ] **Step 2: 부트 대기 블록 삭제**

`hub_template.html`의 boot 스크립트에서 다음 5줄 삭제:

```js
    await new Promise(function(res){           // defer 스크립트가 아직이면 load/error 까지(최대 3초) 대기
      if(window.Chart) return res();
      var s=document.getElementById('chartjs'); if(!s) return res();
      s.addEventListener('load',res); s.addEventListener('error',res); setTimeout(res,3000);
    });
```

- [ ] **Step 3: 지연 도착 재그리기 훅 추가**

boot 스크립트의 앱 JS 실행 **이후** 지점에 (fu-app eval 다음):

```js
  // Chart.js 가 부트보다 늦게 도착하면 — 차트만 있는 화면 요소를 한 번 다시 그린다 (가드가 이미 스킵해 둔 상태)
  (function(){
    var s=document.getElementById('chartjs');
    if(!s || window.Chart) return;
    s.addEventListener('load', function(){
      try{ if(typeof renderHome==='function') renderHome(); }catch(e){}
      try{ if(typeof renderAnalytics==='function') renderAnalytics(); }catch(e){}
    });
  })();
```

주의: `renderHome`/`renderAnalytics`는 Step 1에서 확인한 **실제 함수명으로 교체**할 것. 함수가 전역이 아니면(모듈 스코프) `hub/20_home.js` 쪽에 `chartjs` load 리스너를 넣는 방식으로 전환한다 — 원칙: "게이트를 없애고, 차트는 도착하는 대로 그린다".

- [ ] **Step 4: E2E 전체 + 육안 확인**

Run: E2E 로컬 실행 (사전 조건 참고)
Expected: PASS — 특히 홈 탭 스모크. 추가로 브라우저에서 `hub.html`을 열어 ① 부트가 즉시 진행되는지 ② 스파크라인이 (약간 늦게라도) 그려지는지 확인.

- [ ] **Step 5: 커밋**

```bash
git add hub_template.html hub/
git commit -m "perf: Chart.js 부트 게이트 제거 — 최대 3초 대기 대신 도착 시 차트만 재그리기"
```

---

### Task 13: 웹폰트 렌더 블로킹 해제

4패밀리 12웨이트(한글 2종 포함)의 블로킹 stylesheet가 "불러오는 중" 플레이스홀더 표시조차 지연시킨다(hub_template.html:24). FCP 최대 타격 후보.

**Files:**
- Modify: `hub_template.html:24`

- [ ] **Step 1: 실사용 웨이트 감사**

Run: `grep -Eo "font-weight:\s*[0-9]+" hub_template.html | sort | uniq -c` 및 `grep -Eo "font-weight:\s*[0-9]+" hub/*.js | sort | uniq -c` (콜론 뒤 공백 표기까지 포착)
사용되지 않는 웨이트를 폰트 URL에서 제거한다. (기존 주석 "실제로 쓰이는 웨이트만 요청한다"를 사실로 만들기)

- [ ] **Step 2: 비블로킹 로드로 전환**

```html
<link rel="stylesheet" media="print" onload="this.media='all'"
      href="https://fonts.googleapis.com/css2?family=...(감사 결과 웨이트만)...&display=swap">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=...동일...&display=swap"></noscript>
```

`media="print"`는 렌더 블로킹을 피하는 표준 트릭 — 로드 완료 후 `all`로 승격되고, `display=swap`이라 폰트 도착 전에도 시스템 폰트로 텍스트가 보인다. 기존 `preconnect` 2줄(21-22행)은 유지.

- [ ] **Step 3: E2E + 육안 확인**

Run: E2E 로컬 실행. 브라우저에서 새로고침 시 FOUT(시스템 폰트 → 웹폰트 스왑)가 수용 가능한 수준인지 확인. 스왑이 거슬리면 본문(Noto Sans KR)만 블로킹 유지하고 장식 폰트(Playfair·Serif)만 비블로킹으로 절충.

- [ ] **Step 4: 커밋**

```bash
git add hub_template.html
git commit -m "perf: 웹폰트 비블로킹 로드 + 미사용 웨이트 제거 — FCP 개선"
```

---

## 마무리: PR 및 배포 검증

- [ ] **전체 테스트 최종 실행**: `python -m pytest tests/ generator/test_parse.py -q` → PASS
- [ ] **PR 생성**: `perf/bottleneck-fixes` → `main`. PR 본문에 진단 요약(4m14s → ~2m 예상)과 페이즈별 변경 목록. 전체 커밋 히스토리 기반으로 작성(`git diff main...HEAD`).
- [ ] **머지 후 첫 CI 실행 검증** (Task 9 Step 2의 체크리스트):
  1. build job 총 소요 (기대: 2분대)
  2. Collect 스텝 소요 (기대: 30초대, PYTHONUNBUFFERED로 내부 로그 실시간 확인)
  3. `pw-browsers-Linux-<버전>` 키로 캐시 저장됨
  4. Job Summary의 kb 크기: search ~3.2MB (hay 제거 반영)
  5. Pages 배포 후 사이트 정상: 허브 로딩, 검색, 홈 스파크라인, 검증 데이터
- [ ] **실패 시 롤백 단위**: 태스크별 커밋이 독립적이므로 문제 커밋만 `git revert` 가능. 특히 Task 12(부트 게이트)와 Task 7(apt 생략)은 리스크 노트의 폴백을 따른다.

## 명시적 제외 (후속 계획 후보 — YAGNI)

이번 계획에서 의도적으로 뺀 것들. 효과 대비 리스크·작업량이 커서 별도 계획으로 분리한다:
- E2E `pytest -n 4` 병렬화 (선행 조건: `version.json` 덮어쓰기 테스트·`e2e_timing.json` 공유 상태 격리)
- SIGALRM → `future.result(timeout=)` 교체 + 모멘텀 정밀 보강(`history_n`) 복원
- Chart.js tree-shaken 빌드 또는 인라인 SVG 스파크라인 대체 (gz 68KB → ~25KB)
- 앱 JS 120KB를 `hub.app.<hash>.js`로 분리 (매일 재다운로드 제거)
- sw.js 리포트 캐시 LRU 상한
- `chat_to_kb` 단일 패스 리팩토링 + `fromus_taxonomy` 정규식 교대 컴파일 (생성기 −5~8초, 로컬 전용)
- AI 뉴스 배치 Message Batches API 전환 (비용 50% 절감)
- Playwright 브라우저 캐시의 E2E 셋업 백그라운드 프리워밍 (−22초)
