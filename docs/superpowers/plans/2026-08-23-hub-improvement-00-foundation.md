# 지식허브 개선 — 00 기반(Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 셸 JS 를 모듈 파일로 분리하고, 부트를 "코어만 받고 활성 탭만 그리는" 구조로 바꿔 초기 전송·렌더 비용을 1/5 이하로 줄인다. 이후 Track A(데이터)·Track B(UI)가 충돌 없이 병렬로 달릴 수 있는 토대를 만든다.

**Architecture:** `hub_template.html` 의 단일 `fu-app` 블록을 `hub/*.js` 로 쪼개고 `render.py` 가 빌드타임에 사전순 concat 한다(런타임 동작 불변). `hublib/split.py` 가 `knowledge_base.json` 을 `kb.core` + 청크(chat/search/glossary/stockchat)로 나누고, 셸은 `loadChunk()` 로 필요 시점에 받는다. `sw.js` v4 는 청크별로 구 해시를 정리한다. 모든 변경은 Playwright 스모크 테스트(Task 1)를 먼저 깔고 그 위에서 진행한다.

**Tech Stack:** Python 3.11 · pytest · pytest-playwright(chromium) · 순수 JS/CSS · GitHub Actions

**Spec:** [docs/superpowers/specs/2026-08-23-hub-improvement-design.md](../specs/2026-08-23-hub-improvement-design.md) — 특히 §3.3 데이터 계약 C1·C2 를 이 계획이 구현한다.

**이 계획은 순차 실행한다.** Task 순서가 곧 의존 순서다(스모크 → 분리 → 슬림 → 지연 렌더 → 청크 → 토스트 → safeHref → 문서). 이 계획이 main 에 머지된 뒤 Track A·B 계획을 병렬로 시작한다.

**범위 메모:** 스펙이 A/B 에 배정한 두 가지를 이 계획이 먼저 가져간다 — 검색 디바운스 + `hay` 런타임 메모(P5 일부, Task 6)와 `build/report.md` 크기 리포트(Q1 일부, Task 5). Track A 는 `hay` 를 빌드 시 미리 넣고 예산 표를 **덧붙이며**, Track B 는 디바운스를 다시 만들지 않는다.

---

## 파일 구조

| 파일 | 상태 | 책임 |
|---|---|---|
| `tests/e2e/conftest.py` | 신규 | `E2E_SITE_DIR` 를 정적 서빙하는 `site_url` 픽스처 (없으면 skip) |
| `tests/e2e/test_hub_smoke.py` | 신규 | 부트·탭·검색·딥링크·청크·SW 스모크 10+ |
| `requirements-dev.txt` | 수정 | `pytest-playwright` 추가 |
| `hub/00_util.js` … `hub/90_init.js` | 신규(18개) | 기존 앱 블록을 섹션 주석 경계로 분리. 파일명 숫자 = concat 순서 |
| `hub_template.html` | 수정 | 앱 블록 → `/*APPJS*//*ENDAPPJS*/` 마커, KBURL 매니페스트, 토스트 CSS |
| `hublib/split.py` | 신규 (~70줄) | `slim_reports`·`slim_stock_chat`·`split_payload` 순수 함수 |
| `hublib/render.py` | 수정 | `concat_app_js`·`inject_app_js`·청크 출력·`version.json`·크기 리포트 |
| `sw.js` | 수정 | v4 — `kb.<chunk>.<hash>.json` 인식, 청크별 구 해시 정리 |
| `merge_hub.py` | 수정 | 뉴스 URL 스킴 필터 (Q4) |
| `tests/test_split.py` | 신규 | split 순수 함수 + concat 주입 테스트 |
| `tests/test_phases.py` | 수정 | 코어/청크 파일·매니페스트·SW v4 단언 |
| `tests/test_merge_url.py` | 신규 | merge 단계 URL 필터 |
| `.github/workflows/build.yml` | 수정 | e2e 스텝, `version.json` 복사 |
| `.gitignore` | 수정 | `version.json`, `build/report.md` |
| `README.md` | 수정 | 아키텍처·파일 구조·kb 분할 설명 |

`hub/*.js` 를 ES 모듈로 만들지 않는 이유는 스펙 §3.2 참고. 파일을 18개로 나누는 기준은 **기존 섹션 주석**이다 — 리팩토링이 아니라 "자르기"라서 동작이 바뀔 수 없고, 테스트로 원본과 바이트 동일함을 확인한다.

## 사전 확인

- [ ] **작업 브랜치 생성** (worktree 권장 — @superpowers:using-git-worktrees)

```bash
git checkout -b feat/hub-foundation && git status --short
```

- [ ] **기존 테스트 통과 확인**

```bash
VERIFY_SKIP=1 python -m pytest tests/ generator/test_parse.py -q
```

기대: `123 passed`. 실패가 있으면 멈추고 보고.

- [ ] **로컬 렌더 가능 확인** (knowledge_base.json 이 리포 루트에 있어야 한다 — 없으면 `python build_hub.py --phase collect --src .` 로 생성, 5분 내외)

```bash
python build_hub.py --phase render --json knowledge_base.json --out hub.html && ls kb.*.json
```

기대: `→ hub.html 셸 빌드 완료 (155 KB) + kb.<hash>.json (4MB)`

---

## Task 1: Playwright 스모크 테스트 (Q2) — 안전망 먼저

**Files:**
- Create: `tests/e2e/__init__.py` (빈 파일)
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_hub_smoke.py`
- Modify: `requirements-dev.txt`
- Modify: `.github/workflows/build.yml`

셸 JS 에는 테스트가 0개다. 이후 Task 들이 부트 구조를 바꾸므로 **먼저** 현재 동작을 고정한다. 테스트는 `E2E_SITE_DIR` 가 없으면 전부 skip 되어 기존 `pytest tests/` 실행 시간에 영향을 주지 않는다.

- [ ] **Step 1: 의존성 추가**

`requirements-dev.txt`:
```
pytest>=8
pytest-playwright>=0.5
```

```bash
pip install -r requirements-dev.txt && python -m playwright install chromium
```

- [ ] **Step 2: 정적 서버 픽스처**

`tests/e2e/conftest.py`:
```python
# -*- coding: utf-8 -*-
"""E2E 스모크용 정적 서버 — E2E_SITE_DIR(hub.html·kb.*.json·sw.js 가 있는 폴더)를 서빙한다.
환경변수가 없으면 전부 skip — 단위 테스트 실행 시간에 영향 없음."""
import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_a):           # 테스트 출력 오염 방지
        pass


@pytest.fixture(scope="session")
def site_url():
    site = os.environ.get("E2E_SITE_DIR")
    if not site:
        pytest.skip("E2E_SITE_DIR 미설정 — 스모크 테스트 생략")
    site = os.path.abspath(site)
    if not os.path.exists(os.path.join(site, "hub.html")):
        pytest.skip(f"{site}/hub.html 없음 — 먼저 render 하세요")
    handler = functools.partial(_QuietHandler, directory=site)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/"
    finally:
        srv.shutdown()
```

- [ ] **Step 3: 스모크 테스트 작성 (현재 동작 기준)**

`tests/e2e/test_hub_smoke.py`:
```python
# -*- coding: utf-8 -*-
"""허브 셸 스모크 — 부트·탭·검색·딥링크·SW. 실행: E2E_SITE_DIR=. python -m pytest tests/e2e -q"""
import json
import os

import pytest

pytest.importorskip("playwright")   # 플러그인 없으면 모듈 전체 skip

IGNORED_CONSOLE = ("fonts.googleapis", "fonts.gstatic", "cdnjs.cloudflare")   # 외부 리소스 차단 환경 허용


def _boot(page, site_url, frag=""):
    """hub.html 을 열고 부트 오버레이가 사라질 때까지 기다린다. 콘솔 에러 목록을 돌려준다."""
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error"
            and not any(k in m.text for k in IGNORED_CONSOLE) else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site_url + "hub.html" + frag)
    page.wait_for_selector("#fu-boot", state="detached", timeout=30000)
    return errors


def test_boot_renders_home_without_errors(page, site_url):
    errors = _boot(page, site_url)
    assert page.locator("#view-home.active").count() == 1
    assert page.locator("#view-home .briefing").count() == 1
    assert errors == [], errors


@pytest.mark.parametrize("tab", ["analytics", "sectors", "stocks", "strategy", "glossary", "graph", "chat"])
def test_tab_renders_via_hash(page, site_url, tab):
    errors = _boot(page, site_url, "#" + tab)
    view = page.locator(f"#view-{tab}")
    page.wait_for_function(
        f"document.querySelector('#view-{tab}') && document.querySelector('#view-{tab}').innerHTML.length > 200",
        timeout=15000)
    assert "active" in (view.get_attribute("class") or "")
    assert errors == [], errors


def test_verify_tab_when_enabled(page, site_url):
    _boot(page, site_url)
    enabled = page.evaluate("!!(window.DATA && window.DATA.verify && window.DATA.verify.enabled)")
    if not enabled:
        pytest.skip("verify 비활성 빌드")
    page.goto(site_url + "hub.html#verify")
    page.wait_for_selector("#view-verify .v-score", timeout=15000)


def test_global_search_returns_results(page, site_url):
    errors = _boot(page, site_url)
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    assert page.locator("#searchPanel .sr").count() > 0
    assert errors == [], errors


def test_stock_deep_link_opens_detail(page, site_url):
    _boot(page, site_url)
    first = page.evaluate("(window.DATA.stocks||[])[0] && window.DATA.stocks[0].name")
    assert first, "종목 데이터 없음"
    page.goto(site_url + "hub.html#stocks/" + first)
    page.wait_for_selector("#stockList .strow-detail.open", timeout=15000)


def test_no_javascript_hrefs(page, site_url):
    _boot(page, site_url, "#chat")
    page.wait_for_timeout(500)
    bad = page.evaluate("[...document.querySelectorAll('a[href]')].filter(a=>/^javascript:/i.test(a.getAttribute('href'))).length")
    assert bad == 0


def test_service_worker_registers(page, site_url):
    _boot(page, site_url)
    ok = page.evaluate("navigator.serviceWorker.ready.then(r=>!!r.active)")
    assert ok


def test_boot_timing_recorded(page, site_url):
    """성능 회귀 관찰용 — 부트 완료까지 시간을 build/e2e_timing.json 에 남긴다. 단언은 느슨하게."""
    _boot(page, site_url)
    nav = page.evaluate("performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd")
    dom = page.evaluate("document.getElementsByTagName('*').length")
    canvases = page.evaluate("document.querySelectorAll('canvas').length")
    os.makedirs("build", exist_ok=True)
    with open("build/e2e_timing.json", "w", encoding="utf-8") as f:
        json.dump({"dcl_ms": nav, "dom_nodes": dom, "canvases": canvases}, f)
    assert nav < 15000
```

- [ ] **Step 4: 실행 — 현재 셸에서 전부 통과하는지**

```bash
python build_hub.py --phase render --json knowledge_base.json --out hub.html
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```

기대: `14 passed` (탭 7개 파라미터 포함 · verify 비활성이면 1 skipped). 로컬이 오프라인이면 cdnjs 의 Chart.js 를 못 받아 `Chart is not defined` pageerror 로 실패한다(홈의 지수 차트가 쓴다 — Track B 의 P4 vendoring 전까지) — 네트워크가 있는 상태에서 돌린다. `test_no_javascript_hrefs` 가 실패하면 채팅 URL 에 실제로 `javascript:` 가 있는 것 — Task 7 에서 고치므로 그때까지 `xfail` 로 표시하지 말고 **실패 원인을 기록**한 뒤 진행.

- [ ] **Step 5: 환경변수 없이 실행하면 skip 되는지**

```bash
python -m pytest tests/e2e -q
```

기대: `14 skipped`.

- [ ] **Step 6: CI 스텝 추가** — `.github/workflows/build.yml` 의 `Assemble site` **뒤**, `configure-pages` **앞**에:

```yaml
      - name: E2E 스모크 (셸 JS — _site 기준)
        run: |
          pip install pytest-playwright && python -m playwright install --with-deps chromium
          E2E_SITE_DIR=_site python -m pytest tests/e2e -q
```

- [ ] **Step 7: 커밋**

```bash
git add tests/e2e requirements-dev.txt .github/workflows/build.yml
git commit -m "test(hub): 셸 JS Playwright 스모크 테스트 — 부트·탭·검색·딥링크·SW (E2E_SITE_DIR 없으면 skip)"
```

---

## Task 2: 셸 JS 모듈 분리 (Q3) — 빌드타임 concat

**Files:**
- Create: `hub/00_util.js` … `hub/90_init.js` (18개, 스크립트가 생성)
- Modify: `hub_template.html` (앱 블록 → 마커)
- Modify: `hublib/render.py`
- Create: `tests/test_split.py` (concat 부분)

- [ ] **Step 1: concat 주입 테스트 작성 (RED)**

`tests/test_split.py`:
```python
# -*- coding: utf-8 -*-
"""셸 앱 JS 모듈 concat 주입 + kb 분할 순수 함수 테스트."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_concat_app_js_is_in_filename_order_and_complete():
    from hublib.render import concat_app_js
    files = sorted(glob.glob(os.path.join(ROOT, "hub", "*.js")))
    assert len(files) >= 10, "hub/*.js 모듈이 없음 — Task 2 분리 스크립트를 먼저 실행"
    js = concat_app_js()
    pos = -1
    for p in files:
        body = open(p, encoding="utf-8").read()
        i = js.find(body)
        assert i > pos, f"{os.path.basename(p)} 가 빠졌거나 순서가 틀림"
        pos = i


def test_inject_app_js_replaces_marker_without_backslash_mangling():
    from hublib.render import inject_app_js
    shell = '<script type="fu-app">/*APPJS*/\n/*ENDAPPJS*/</script>'
    js = r"const re=/\d+/; const s='$1 \\n';"        # 백슬래시·$1 이 re.sub 치환에서 깨지면 안 된다
    out = inject_app_js(shell, js)
    assert js in out
    assert "/*APPJS*/" in out and "/*ENDAPPJS*/" in out


def test_template_has_app_marker_and_no_inline_app_code():
    tpl = open(os.path.join(ROOT, "hub_template.html"), encoding="utf-8").read()
    assert "/*APPJS*/" in tpl and "/*ENDAPPJS*/" in tpl
    assert "function renderHome(" not in tpl, "앱 코드가 아직 템플릿에 인라인돼 있음"
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/test_split.py -q
```

기대: 3 failed (`concat_app_js` 없음 / 마커 없음).

- [ ] **Step 3: 분리 스크립트 작성·실행** — 일회용. `tools/split_app_js.py` 로 저장 후 실행하고 **커밋하지 않는다**.

```python
# -*- coding: utf-8 -*-
"""hub_template.html 의 단일 fu-app 블록을 섹션 주석 경계로 hub/*.js 에 자른다 (일회용)."""
import os
import re

T = open("hub_template.html", encoding="utf-8").read()
m = re.search(r'<script type="fu-app">\n(.*?)\n</script>', T, re.S)
assert m, "fu-app 블록 없음"
js = m.group(1)

# (파일명, 섹션 주석 라벨) — 라벨은 '/* ─── LABEL ─── */' 또는 '/* ═══ LABEL ═══ */' 주석의 텍스트
SECTIONS = [
    ("00_util.js", None),
    ("10_tabs.js", "TABS"),
    ("20_home.js", "HOME"),
    ("21_sectors.js", "SECTORS"),
    ("22_stocks.js", "STOCKS"),
    ("23_verify.js", "VERIFY"),
    ("24_strategy.js", "STRATEGY"),
    ("25_chat.js", "CHAT GLOBAL SECTIONS"),
    ("26_glossary.js", "GLOSSARY"),
    ("30_search.js", "GLOBAL SEARCH"),
    ("31_nav.js", "chip / tag navigation"),
    ("40_state.js", "V2 LOGIC"),
    ("50_graph.js", "V3: 관계망 그래프"),
    ("60_popover.js", "V3: 호버 팝오버"),
    ("61_report_modal.js", "V3.1: 원문 리포트 모달"),
    ("70_exec_ux.js", "V4: Executive UX"),
    ("80_analytics.js", "ANALYTICS"),
    ("90_init.js", "INIT"),
]
positions = []
for name, label in SECTIONS:
    if label is None:
        positions.append((name, 0)); continue
    mm = re.search(r"/\*\s*[─═]+\s*" + re.escape(label), js)
    assert mm, f"섹션 주석 못 찾음: {label}"
    positions.append((name, mm.start()))
order = [p for _, p in positions]
assert order == sorted(order) and len(set(order)) == len(order), "섹션 순서가 원본과 다름"

os.makedirs("hub", exist_ok=True)
bounds = positions + [(None, len(js))]
pieces = []
for (name, start), (_, end) in zip(bounds, bounds[1:]):
    piece = js[start:end]
    pieces.append(piece)
    with open(os.path.join("hub", name), "w", encoding="utf-8") as f:
        f.write(piece)
assert "".join(pieces) == js, "조각을 이어붙인 결과가 원본과 다름"

new = T[:m.start(1)] + "/*APPJS*/\n/*ENDAPPJS*/" + T[m.end(1):]
with open("hub_template.html", "w", encoding="utf-8") as f:
    f.write(new)
print(f"분리 완료 — {len(pieces)}개 파일, 원본 {len(js):,}자")
```

```bash
python tools/split_app_js.py && wc -l hub/*.js && rm tools/split_app_js.py && rmdir tools
```

기대: `분리 완료 — 18개 파일`. 가장 큰 파일(`50_graph.js`·`70_exec_ux.js`)도 400줄 이하인지 확인. 800줄을 넘는 파일이 있으면 보고(이번 범위에선 추가 분리하지 않는다).

- [ ] **Step 4: render.py 에 concat·주입 추가** — `hublib/render.py` 상단 `HUB_BTN_HTML` 아래에:

```python
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hub")


def concat_app_js(app_dir=APP_DIR):
    """hub/*.js 를 파일명 사전순으로 이어붙인다 — 파일명 숫자가 곧 실행 순서."""
    import glob
    files = sorted(glob.glob(os.path.join(app_dir, "*.js")))
    if not files:
        raise FileNotFoundError(f"앱 모듈 없음: {app_dir}/*.js")
    parts = []
    for p in files:
        with open(p, encoding="utf-8") as f:
            parts.append(f"/* ==== {os.path.basename(p)} ==== */\n" + f.read())
    return "\n".join(parts)


def inject_app_js(shell, app_js):
    """/*APPJS*/ … /*ENDAPPJS*/ 사이에 앱 코드를 넣는다. 치환 함수를 써서 JS 의 백슬래시·$1 이 re 에 해석되지 않게 한다."""
    if "/*APPJS*/" not in shell or "/*ENDAPPJS*/" not in shell:
        raise ValueError("템플릿에 /*APPJS*/ … /*ENDAPPJS*/ 마커가 없습니다.")
    return re.sub(r"/\*APPJS\*/.*?/\*ENDAPPJS\*/",
                  lambda _m: "/*APPJS*/\n" + app_js + "\n/*ENDAPPJS*/", shell, count=1, flags=re.S)
```

그리고 `render()` 안에서 `shell = f.read()` 직후에 한 줄 추가:

```python
        shell = inject_app_js(shell, concat_app_js())
```

또한 기존 KBURL 치환도 치환 함수로 바꾼다(같은 이유):

```python
            shell = re.sub(r"/\*KBURL\*/.*?/\*ENDKBURL\*/",
                           lambda _m: f'/*KBURL*/"{kb_name}"/*ENDKBURL*/', shell, count=1, flags=re.S)
```

- [ ] **Step 5: 테스트 통과 확인 + 렌더 결과가 원본과 동작 동일한지**

```bash
python -m pytest tests/test_split.py tests/test_phases.py -q
python build_hub.py --phase render --json knowledge_base.json --out hub.html
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```

기대: 전부 PASS. 스모크가 깨지면 분리 경계가 잘못된 것 — `hub/*.js` 를 지우고 Step 3 의 라벨을 고쳐 재실행.

- [ ] **Step 6: 커밋**

```bash
git add hub/ hub_template.html hublib/render.py tests/test_split.py
git commit -m "refactor(hub): 셸 앱 JS를 hub/*.js 18개 모듈로 분리 — render.py 가 빌드타임 사전순 concat 주입 (동작 불변)"
```

---

## Task 3: `reports` 슬림화 (P2)

**Files:**
- Create: `hublib/split.py`
- Modify: `hublib/render.py` (render 에서 사용)
- Modify: `tests/test_split.py` (추가)

셸이 `D.reports` 에서 읽는 필드는 `id·file·type·date·sort_date·headline·subhead` 뿐이다(`FILE` 맵, 캘린더, 커맨드팔레트, 모달 제목). 나머지 2.5MB 는 출력에서 뺀다. `knowledge_base.json` 자체는 건드리지 않는다.

- [ ] **Step 1: 테스트 (RED)** — `tests/test_split.py` 에 추가:

```python
def _mini_data():
    return {
        "build": {"schema": 2, "generated": "2026-08-23 07:30", "to": "2026-08-22"},
        "reports": [{"type": "daily", "date": "2026-08-22", "id": "2026-08-22", "sort_date": "2026-08-22",
                     "file": "reports/daily/x.html", "headline": "H", "subhead": "S",
                     "timeline": [{"title": "t"}], "insights": [{"name": "n"}], "glossary": []}],
        "search": [{"kind": "종목", "title": "삼성전자", "snippet": "", "date": "", "id": "", "tags": []}],
        "glossary": [{"term": "PER", "body": "..."}],
        "stocks": [{"name": "삼성전자", "count": 3, "mentions": [],
                    "chat": {"count": 10, "signals": 4, "stance": {"bullish": 2, "bearish": 0, "watch": 1},
                             "targets": [{"value": "90000"}],
                             "opinions": [{"date": "2026-08-0%d" % i} for i in range(1, 8)],
                             "news": [{"date": "2026-08-0%d" % i, "url": "https://x/%d" % i} for i in range(1, 8)],
                             "market_news": [{"date": "2026-08-01"}, {"date": "2026-08-02"}]}},
                   {"name": "기아", "count": 1, "mentions": []}],
        "sectors": [], "chat": {"build": {"messages": 1}, "themes": {"반도체": {}}, "co_edges": [{"a": "A", "b": "B", "w": 2}],
                                "actions": [1, 2], "strategy": [1], "targets": [], "qna": [], "news": [1, 2, 3],
                                "readings": [], "glossary": []},
    }


def test_slim_reports_keeps_only_ui_fields():
    from hublib.split import slim_reports
    out = slim_reports(_mini_data()["reports"])
    assert out == [{"type": "daily", "date": "2026-08-22", "id": "2026-08-22", "sort_date": "2026-08-22",
                    "file": "reports/daily/x.html", "headline": "H", "subhead": "S"}]


def test_slim_reports_does_not_mutate_input():
    from hublib.split import slim_reports
    data = _mini_data()
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    slim_reports(data["reports"])
    assert json.dumps(data, ensure_ascii=False, sort_keys=True) == before
```

파일 상단 import 에 `import json` 추가.

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_split.py -q` → `hublib.split` 없음으로 2 failed.

- [ ] **Step 3: 구현** — `hublib/split.py`:

```python
# -*- coding: utf-8 -*-
"""render 단계의 kb 분할·슬림화 — 순수 함수만. knowledge_base.json 은 건드리지 않고 출력(kb.*)만 줄인다.

계약: docs/superpowers/specs/2026-08-23-hub-improvement-design.md §3.3 C2
"""

# 셸(hub/*.js)이 D.reports 에서 읽는 필드 전부 — FILE 맵·캘린더·커맨드팔레트·원문 모달 제목
REPORT_FIELDS = ("type", "date", "id", "sort_date", "file", "headline", "subhead")


def slim_reports(reports):
    """리포트 레코드를 셸이 쓰는 필드로만 투영한다. 원문은 reports/**/*.html 링크로 남아 있다."""
    return [{k: r[k] for k in REPORT_FIELDS if k in r} for r in (reports or [])]
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_split.py -q` → PASS.

- [ ] **Step 5: render 에 적용** — `hublib/render.py` `render()` 에서 `payload = json.dumps(data, ...)` 직전에:

```python
    from hublib.split import slim_reports
    out_data = {**data, "reports": slim_reports(data.get("reports"))}
    payload = json.dumps(out_data, ensure_ascii=False, separators=(",", ":"))
```

(`data` 는 `knowledge_base.json` 재기록에 쓰이므로 변경하지 않는다 — 새 dict.)

- [ ] **Step 6: 크기 확인 + 스모크**

```bash
python build_hub.py --phase render --json knowledge_base.json --out hub.html && ls -la kb.*.json
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```

기대: kb 파일이 9.2MB → **약 6.7MB**. 스모크 PASS(캘린더·커맨드팔레트·원문 모달이 reports 필드만 쓰므로).

- [ ] **Step 7: 커밋**

```bash
git add hublib/split.py hublib/render.py tests/test_split.py
git commit -m "perf(hub): kb 출력의 reports 를 UI 사용 필드 7개로 투영 — 9.2MB→6.7MB (knowledge_base.json 불변)"
```

---

## Task 4: 활성 탭만 렌더 + 스파크라인 지연 (P3)

**Files:**
- Modify: `hub/10_tabs.js`
- Modify: `hub/23_verify.js`
- Modify: `hub/40_state.js`
- Modify: `hub/90_init.js`

현재 `90_init.js` 가 9개 `render*()` 를 동기 호출한다(460ms). 홈만 부트에서 그리고 나머지는 `showTab` 첫 진입 시 그린다. `renderVerify` 가 하던 "검증 탭 버튼 표시/숨김"은 부트에서 항상 필요하므로 분리한다.

- [ ] **Step 1: 스모크에 지연 렌더 단언 추가 (RED)** — `tests/e2e/test_hub_smoke.py` 끝에:

```python
def test_boot_renders_only_home(page, site_url):
    """부트 직후에는 홈만 그려져 있어야 한다(P3). 다른 탭은 첫 진입 시 렌더."""
    _boot(page, site_url)
    assert page.evaluate("document.querySelector('#view-stocks').innerHTML.length") == 0
    assert page.evaluate("document.querySelectorAll('canvas').length") < 15
    page.click('#tabs .tab[data-tab="stocks"]')
    page.wait_for_selector("#stockList .strow", timeout=15000)
    assert page.evaluate("document.querySelector('#view-stocks').innerHTML.length") > 200
```

```bash
E2E_SITE_DIR=. python -m pytest tests/e2e -q -k only_home
```
기대: FAIL (현재는 전량 렌더).

- [ ] **Step 2: `hub/10_tabs.js` — `showTab` 앞에 렌더 레지스트리 추가, `showTab` 수정**

`const TABS=[...]` 바로 아래에 추가:
```js
/* 탭별 렌더러 — 첫 진입 시 1회만 실행 (P3). Promise 를 돌려주는 렌더러는 청크 로딩 후 렌더한다 (P1). */
const VIEW_RENDERERS = {
  home:      ()=>renderHome(),
  sectors:   ()=>renderSectors(),
  stocks:    ()=>renderStocks(),
  analytics: ()=>renderAnalytics(),
  strategy:  ()=>renderStrategy(),
  verify:    ()=>renderVerify(),
  graph:     ()=>renderGraph(),
  glossary:  ()=>renderGlossary(),
  chat:      ()=>renderChatView(),
};
const RENDERED = new Set();
function ensureView(name){
  if(RENDERED.has(name)) return Promise.resolve();
  const fn=VIEW_RENDERERS[name]; if(!fn) return Promise.resolve();
  RENDERED.add(name);
  let p; try{ p=Promise.resolve(fn()); }catch(e){ p=Promise.reject(e); }
  return p.catch(e=>{
    RENDERED.delete(name);                         // 실패는 기억하지 않는다 — 다시 시도 가능
    console.error('탭 렌더 실패:', name, e);
    const host=document.getElementById('view-'+name);
    if(host) host.innerHTML=`<div class="empty">데이터를 불러오지 못했습니다. <button type="button" class="cmp-add" data-view-retry="${esc(name)}">다시 시도</button></div>`;
  });
}
document.addEventListener('click',e=>{ const b=e.target.closest('[data-view-retry]'); if(b) ensureView(b.dataset.viewRetry); });
```

`showTab` 을 다음으로 교체:
```js
function showTab(name,fromHash){
  if(!TABS.includes(name))name='home';
  if(name==='verify' && !verifyOn()) name='home';
  $$('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  $$('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+name));
  const ready=ensureView(name);
  if(name==='trade'){const f=document.getElementById('tradeFrame');if(f&&!f.getAttribute('src'))f.setAttribute('src',f.dataset.src);}
  ready.then(()=>{ if(typeof graphSetActive==='function') graphSetActive(name==='graph'); });
  if(!fromHash){ try{history.replaceState(null,'','#'+name);}catch(e){} window.scrollTo({top:0,behavior:'smooth'}); }
}
```

- [ ] **Step 3: `hub/23_verify.js` — 탭 표시 동기화 분리**

`renderVerify` 안의 `$$('.tab[data-tab="verify"]').forEach(...)` 줄을 `syncVerifyTab();` 으로 바꾸고, `function verifyOn()` 아래에 추가:
```js
function syncVerifyTab(){ $$('.tab[data-tab="verify"]').forEach(b=>{ b.style.display = verifyOn()?'':'none'; }); }
```

- [ ] **Step 4: `hub/40_state.js` — 스파크라인을 보일 때 그리기**

`function drawStockSparks(){...}` 한 줄을 다음으로 교체:
```js
/* 스파크라인 — 뷰포트에 들어온 행만 그린다 (208개 canvas 즉시 렌더 방지) */
const SPARK_IO = ('IntersectionObserver' in window) ? new IntersectionObserver(entries=>{
  entries.forEach(en=>{
    if(!en.isIntersecting) return;
    const cv=en.target; SPARK_IO.unobserve(cv);
    const s=STOCK_BY_NAME[cv.dataset.sparkName]; if(s) drawSpark(cv, weeklyCounts(s.mentions));
  });
},{rootMargin:'240px'}) : null;
function drawStockSparks(){
  $$('.strow-spark').forEach(cv=>{
    if(SPARK_IO){ SPARK_IO.observe(cv); return; }
    const s=STOCK_BY_NAME[cv.dataset.sparkName]; if(s) drawSpark(cv, weeklyCounts(s.mentions));
  });
}
```
(`setTheme` 이 `drawStockSparks()` 를 다시 부르면 보이는 행은 observer 콜백으로 즉시 다시 그려진다.)

- [ ] **Step 5: `hub/90_init.js` — INIT 교체**

`renderHome();renderSectors();...renderVerify();` 줄을:
```js
RENDERED.add('home'); renderHome(); syncVerifyTab();
```
로 바꾼다. 파일 끝 `tabFromHash();` 뒤에 추가:
```js
try{ performance.mark('fu:app-ready'); }catch(e){}
```

- [ ] **Step 6: 렌더 + 스모크 전량**

```bash
python build_hub.py --phase render --json knowledge_base.json --out hub.html
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```
기대: 전부 PASS (`only_home` 포함). `build/e2e_timing.json` 의 `dom_nodes` 가 17,000대 → 3,000대, `canvases` ≤ 15 인지 눈으로 확인해 커밋 메시지에 적는다.

- [ ] **Step 7: 커밋**

```bash
git add hub/ tests/e2e/test_hub_smoke.py
git commit -m "perf(hub): 활성 탭만 렌더(첫 진입 시 1회) + 스파크라인 IntersectionObserver — 부트 DOM 17.6K→3K, canvas 213→<15"
```

---

## Task 5: 코어 + 청크 분할 로딩 (P1) — Python 쪽

**Files:**
- Modify: `hublib/split.py` (`slim_stock_chat`, `split_payload`)
- Modify: `hublib/render.py` (`render()` 재작성)
- Modify: `hub_template.html` (부트스트랩 core fetch — Step 5a)
- Modify: `tests/test_split.py`, `tests/test_phases.py`
- Modify: `.gitignore`, `.github/workflows/build.yml`

- [ ] **Step 1: 테스트 (RED)** — `tests/test_split.py` 에 추가:

```python
def test_split_payload_core_and_chunks():
    from hublib.split import split_payload
    data = _mini_data()
    core, chunks = split_payload(data)

    # 코어에서 빠지는 것
    assert "search" not in core and "glossary" not in core
    assert core["build"]["counts"] == {"glossary": 1, "search": 1}
    assert core["reports"][0].keys() == {"type", "date", "id", "sort_date", "file", "headline", "subhead"}
    # chat 은 관계망·섹터 카드가 쓰는 themes/co_edges 와 섹션 개수만 남는다
    assert set(core["chat"].keys()) == {"build", "themes", "co_edges", "counts"}
    assert core["chat"]["counts"]["news"] == 3 and core["chat"]["counts"]["actions"] == 2
    # 종목 chat 은 초기 표시분만 + 전체 개수
    sc = core["stocks"][0]["chat"]
    assert len(sc["opinions"]) == 3 and sc["opinions_n"] == 7
    assert len(sc["news"]) == 4 and sc["news_n"] == 7
    assert sc["market_news"] == [] and sc["market_news_n"] == 2
    assert sc["stance"] == {"bullish": 2, "bearish": 0, "watch": 1} and sc["targets"] == [{"value": "90000"}]
    assert "chat" not in core["stocks"][1]

    # 청크
    assert chunks["search"] == data["search"]
    assert chunks["glossary"] == data["glossary"]
    assert chunks["chat"] == data["chat"]
    assert list(chunks["stockchat"].keys()) == ["삼성전자"]
    assert chunks["stockchat"]["삼성전자"] == data["stocks"][0]["chat"]


def test_split_payload_without_chat():
    from hublib.split import split_payload
    data = _mini_data(); data.pop("chat")
    for s in data["stocks"]: s.pop("chat", None)
    core, chunks = split_payload(data)
    assert "chat" not in core
    assert chunks["chat"] is None and chunks["stockchat"] == {}


def test_split_payload_does_not_mutate_input():
    from hublib.split import split_payload
    data = _mini_data()
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    split_payload(data)
    assert json.dumps(data, ensure_ascii=False, sort_keys=True) == before
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_split.py -q` → 3 failed.

- [ ] **Step 3: 구현** — `hublib/split.py` 에 추가:

```python
CHAT_CORE_KEYS = ("build", "themes", "co_edges")          # 관계망·섹터 카드가 부트 직후 읽는 것
CHAT_COUNT_KEYS = ("actions", "strategy", "targets", "qna", "news", "readings", "glossary")
STOCK_CHAT_OPINIONS = 3        # 종목 행 펼침 시 바로 보이는 의견 수 (hub/22_stocks.js CHAT_INIT_OP 와 같아야 한다)
STOCK_CHAT_NEWS = 4            # 같은 이유 (CHAT_INIT_NEWS)


def slim_stock_chat(chat):
    """종목 chat 블록을 초기 표시분 + 전체 개수로 줄인다. 전체는 stockchat 청크에 있다."""
    if not chat:
        return None
    ops = chat.get("opinions") or []
    news = chat.get("news") or []
    mkt = chat.get("market_news") or []
    return {
        "count": chat.get("count", 0), "signals": chat.get("signals", 0),
        "stance": chat.get("stance") or {}, "targets": chat.get("targets") or [],
        "opinions": ops[:STOCK_CHAT_OPINIONS], "news": news[:STOCK_CHAT_NEWS], "market_news": [],
        "opinions_n": len(ops), "news_n": len(news), "market_news_n": len(mkt),
    }


def split_payload(data):
    """knowledge_base 전체 → (core, {chat, search, glossary, stockchat}). 입력은 변경하지 않는다."""
    chat = data.get("chat") or None
    stocks = data.get("stocks") or []
    core = {k: v for k, v in data.items() if k not in ("search", "glossary")}
    core["reports"] = slim_reports(data.get("reports"))
    core["stocks"] = [({**s, "chat": slim_stock_chat(s["chat"])} if s.get("chat") else s) for s in stocks]
    core["build"] = {**(data.get("build") or {}),
                     "counts": {"glossary": len(data.get("glossary") or []),
                                "search": len(data.get("search") or [])}}
    if chat:
        core["chat"] = {**{k: chat[k] for k in CHAT_CORE_KEYS if k in chat},
                        "counts": {k: len(chat.get(k) or []) for k in CHAT_COUNT_KEYS}}
    else:
        core.pop("chat", None)
    chunks = {
        "chat": chat,
        "search": data.get("search") or [],
        "glossary": data.get("glossary") or [],
        "stockchat": {s["name"]: s["chat"] for s in stocks if s.get("chat")},
    }
    return core, chunks
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_split.py -q` → PASS.

- [ ] **Step 5: `render()` 재작성** — `hublib/render.py` 의 `render` 함수 전체를 다음으로 교체:

```python
def _emit_json(out_dir, name, obj):
    """kb.<name>.<hash>.json 기록 → (파일명, 바이트 수). 해시는 청크 자신의 내용 — 안 바뀐 청크는 파일명이 유지된다."""
    import hashlib, json
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    h = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    fname = f"kb.{name}.{h}.json"
    with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
        f.write(payload)
    return fname, len(payload.encode("utf-8"))


def _write_size_report(sizes, path="build/report.md"):
    """섹션별 바이트를 Markdown 표로 — CI Job Summary 에 붙인다 (Q1)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = "\n".join(f"| {k} | {v/1e6:.2f} MB |" for k, v in sizes.items())
    total = sum(sizes.values())
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"### kb 출력 크기\n\n| 파일 | raw |\n|---|---|\n{rows}\n| **합계** | **{total/1e6:.2f} MB** |\n")


def render(json_in="knowledge_base.json", out="hub.html", template=None, index_path=None):
    """knowledge_base.json(+ai_digest.json) → kb.core.<h>.json + 청크 + hub 셸 + version.json.
    파싱·네트워크 없음 — render 단계만 실행 시 bs4/yfinance 없이 동작한다."""
    import glob, json, sys
    from hublib.split import split_payload
    with open(json_in, encoding="utf-8") as f:
        data = json.load(f)

    # AI 위클리 다이제스트 반영 (ai_digest.py 산출물 — 없으면 무시) + knowledge_base.json 재기록
    try:
        if os.path.exists("ai_digest.json"):
            with open("ai_digest.json", encoding="utf-8") as f:
                data["ai_digest"] = json.load(f)
            print("ℹ️ ai_digest.json 반영")
            with open(json_in, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"ℹ️ ai_digest.json 읽기 실패 — 무시 ({e})")

    here = os.path.dirname(os.path.abspath(__file__))
    tpl = template or os.path.join(os.path.dirname(here), "hub_template.html")
    out_dir = os.path.dirname(os.path.abspath(out)) or "."
    for old in glob.glob(os.path.join(out_dir, "kb.*.json")):   # 구 해시(구 형식 kb.<h>.json 포함) 정리
        os.remove(old)

    core, chunks = split_payload(data)
    manifest, sizes = {}, {}
    manifest["core"], sizes["core"] = _emit_json(out_dir, "core", core)
    for name, obj in chunks.items():
        if obj:                                                   # 빈 청크(chat 없음 등)는 파일·매니페스트에서 생략
            manifest[name], sizes[name] = _emit_json(out_dir, name, obj)

    with open(os.path.join(out_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"core": manifest["core"], "generated": (data.get("build") or {}).get("generated", "")},
                  f, ensure_ascii=False)

    _write_size_report(sizes)
    if os.path.exists(tpl):                                        # 템플릿이 없어도 kb.*·version.json 은 이미 만들어졌다 (기존 동작 유지)
        with open(tpl, encoding="utf-8") as f:
            shell = f.read()
        shell = inject_app_js(shell, concat_app_js())
        if "/*KBURL*/" not in shell or "/*ENDKBURL*/" not in shell:
            sys.exit("템플릿에 /*KBURL*/ … /*ENDKBURL*/ 마커가 없습니다.")
        shell = re.sub(r"/\*KBURL\*/.*?/\*ENDKBURL\*/",
                       lambda _m: "/*KBURL*/" + json.dumps(manifest, ensure_ascii=False) + "/*ENDKBURL*/",
                       shell, count=1, flags=re.S)
        with open(out, "w", encoding="utf-8") as f:
            f.write(shell)
        print(f"→ {out} 셸 빌드 완료 ({os.path.getsize(out)//1024} KB) + " +
              " · ".join(f"{n} {b/1e6:.2f}MB" for n, b in sizes.items()))
    else:
        print(f"⚠ 템플릿 없음({tpl}) — kb.*.json 만 생성했습니다.")

    idx = index_path or os.path.join(os.path.dirname(out) or ".", "index.html")
    inject_hub_button(idx)
```

Task 3 에서 넣었던 `out_data = {**data, "reports": ...}` 줄은 `split_payload` 가 대신하므로 제거한다.

- [ ] **Step 5a: 부트스트랩이 매니페스트의 `core` 를 받도록** — 같은 커밋에 넣어야 스모크가 계속 초록이다. `hub_template.html` 마지막 `<script>`(부트스트랩)의

```js
    const r = await fetch(window.KB_URL);
```
를
```js
    // KB_URL 은 이제 매니페스트 객체({core, chat, …}) — 구 셸(문자열)도 그대로 동작
    const coreUrl = (typeof window.KB_URL === 'string') ? window.KB_URL : (window.KB_URL && window.KB_URL.core);
    if(!coreUrl) throw new Error('KB 매니페스트에 core 없음');
    const r = await fetch(coreUrl);
```
로 바꾼다. (이 줄을 빼먹으면 `fetch("[object Object]")` 가 404 → 캐시버스터 재로드 루프에 빠진다.)

- [ ] **Step 6: `tests/test_phases.py` 갱신** — 두 테스트의 kb 파일 단언을 교체:

`test_collect_then_render` 에서
```python
    kb_files = list(src.glob("kb.*.json"))
    assert len(kb_files) == 1, ...
    data = json.loads(kb_files[0].read_text(encoding="utf-8"))
    assert data["ai_digest"]["digest"]["title"] == "테스트다이제스트"
    assert kb_files[0].name in (src / "hub.html").read_text(encoding="utf-8")
```
→
```python
    core_files = list(src.glob("kb.core.*.json"))
    assert len(core_files) == 1, f"코어 파일이 정확히 1개여야 함: {core_files}"
    core = json.loads(core_files[0].read_text(encoding="utf-8"))
    assert core["ai_digest"]["digest"]["title"] == "테스트다이제스트"
    assert "search" not in core and "glossary" not in core, "검색·용어는 청크로 빠져야 함"
    shell = (src / "hub.html").read_text(encoding="utf-8")
    import re as _re
    man = json.loads(_re.search(r"/\*KBURL\*/(.*?)/\*ENDKBURL\*/", shell, _re.S).group(1))
    assert man["core"] == core_files[0].name
    assert "search" in man, "검색 청크는 리포트만 있어도 만들어져야 함"
    for name in ("search", "glossary", "chat", "stockchat"):      # 픽스처엔 용어·채팅이 없을 수 있다 → 있는 것만 확인
        if name in man:
            assert (src / man[name]).exists(), f"{name} 청크 파일 없음"
    assert (src / "version.json").exists()
    assert json.loads((src / "version.json").read_text(encoding="utf-8"))["core"] == man["core"]
```
(`_merge_chat_kb` 는 cwd 에 `chat_kb.json` 이 없으면 **리포 루트의 것으로 폴백**하므로 tmp 폴더 빌드에도 `chat`·`stockchat` 청크가 생길 수 있다 — 그래서 "있는 것만" 확인한다.)

`test_render_reuses_existing_kb_without_recollect` 의 마지막 줄을
```python
    assert len(list(src.glob("kb.core.*.json"))) == 1
```
로.

- [ ] **Step 7: 단위 테스트**

```bash
VERIFY_SKIP=1 python -m pytest tests/ -q
```
기대: PASS. 스모크도 돌려 보면 부트·홈·딥링크는 통과하고, **검색·용어·채팅 탭 3~4개만** Task 6 까지 실패한다(`D.search`/`D.glossary`/`D.chat` 섹션이 청크로 빠졌는데 셸이 아직 안 받으므로). 그 외가 실패하면 Step 5a 누락을 의심.

- [ ] **Step 8: `.gitignore`·워크플로**

`.gitignore` 의 `kb.*.json` 아래에:
```
version.json
build/report.md
build/e2e_timing.json
```

`.github/workflows/build.yml` `Assemble site` 의 `cp kb.*.json _site/ ...` 줄 아래에:
```yaml
          cp version.json _site/
```
같은 파일 상단 `on.push.paths` 목록에 두 줄 추가(없으면 `hub/*.js` 만 바꾼 커밋이 배포를 트리거하지 않는다):
```yaml
      - 'hub/**'
      - 'tests/e2e/**'
```
(`build/report.md` 를 `$GITHUB_STEP_SUMMARY` 에 붙이는 스텝은 Track A 계획 Task 2 가 넣는다 — 여기서는 파일만 만든다.)

- [ ] **Step 9: 커밋**

```bash
git add hublib/split.py hublib/render.py hub_template.html tests/test_split.py tests/test_phases.py .gitignore .github/workflows/build.yml
git commit -m "feat(render): kb 를 core + chat/search/glossary/stockchat 청크로 분할 출력 — KBURL 매니페스트·version.json·크기 리포트"
```

---

## Task 6: 청크 로더 + SW v4 (P1) — JS 쪽

**Files:**
- Modify: `hub/00_util.js`, `hub/10_tabs.js`, `hub/20_home.js`, `hub/22_stocks.js`, `hub/25_chat.js`, `hub/30_search.js`, `hub/40_state.js`, `hub/61_report_modal.js`, `hub/70_exec_ux.js`
- Modify: `sw.js`
- Modify: `tests/test_phases.py` (SW v4), `tests/e2e/test_hub_smoke.py`

- [ ] **Step 1: 스모크에 청크 단언 추가 (RED)**

```python
def test_search_loads_search_chunk_lazily(page, site_url):
    _boot(page, site_url)
    loaded = page.evaluate("performance.getEntriesByType('resource').some(r=>/kb\\.search\\./.test(r.name))")
    assert loaded is False, "부트에서 search 청크를 받으면 안 된다"
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    loaded = page.evaluate("performance.getEntriesByType('resource').some(r=>/kb\\.search\\./.test(r.name))")
    assert loaded is True


def test_core_is_small(page, site_url):
    _boot(page, site_url)
    size = page.evaluate("(performance.getEntriesByType('resource').find(r=>/kb\\.core\\./.test(r.name))||{}).decodedBodySize||0")
    assert 0 < size < 3_000_000, f"core 가 너무 큼: {size}"
```

- [ ] **Step 2: `hub/00_util.js` 끝에 로더 추가** (부트스트랩의 core fetch 는 Task 5 Step 5a 에서 이미 바꿨다)

```js
/* ── KB 매니페스트 · 청크 로더 (스펙 C1/C2) ──
   D 는 앱 상태 컨테이너다 — 청크가 도착하면 해당 키만 채운다. */
const KB = (typeof window.KB_URL === 'string') ? {core: window.KB_URL} : (window.KB_URL || {});
const CHUNKS = {};
function applyChunk(name, obj){
  if(name==='search') D.search = obj || [];
  else if(name==='glossary') D.glossary = obj || [];
  else if(name==='chat') D.chat = Object.assign({}, D.chat || {}, obj || {});
  else if(name==='stockchat'){ (D.stocks||[]).forEach(s=>{ if(obj && obj[s.name]) s.chat = obj[s.name]; }); }
}
function loadChunk(name){
  if(!KB[name]) return Promise.resolve(null);           // 매니페스트에 없음(구 빌드·빈 청크) → 조용히 통과
  if(!CHUNKS[name]) CHUNKS[name] = fetch(KB[name])
    .then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(obj=>{ applyChunk(name,obj); return obj; })
    .catch(e=>{ delete CHUNKS[name]; throw e; });        // 실패는 메모이즈하지 않는다 — 재시도 가능
  return CHUNKS[name];
}
function chunkFailHtml(name){
  return `<div class="empty">데이터를 불러오지 못했습니다. <button type="button" class="cmp-add" data-chunk-retry="${esc(name)}">다시 시도</button></div>`;
}
const safeHref = u => /^https?:\/\//i.test(u||'') ? u : '#';   // javascript: 등 차단 (Q4)
```

- [ ] **Step 3: `hub/10_tabs.js` — 청크가 필요한 탭 렌더러 교체**

`VIEW_RENDERERS` 의 두 줄:
```js
  glossary:  ()=>loadChunk('glossary').then(()=>renderGlossary()),
  chat:      ()=>loadChunk('chat').then(()=>renderChatView()),
```
`ensureView` 의 실패 처리에서 `data-view-retry` 마크업 대신 `chunkFailHtml(name)` 을 쓰고, 재시도 핸들러를 다음으로 교체:
```js
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-chunk-retry]'); if(!b) return;
  const name=b.dataset.chunkRetry;
  if(name==='search'){ scheduleSearch(); return; }
  if(name==='stockchat'){ const body=b.closest('.chat-mkt-body'); if(body){ body.dataset.chatShown='0'; loadChunk('stockchat').then(()=>fillMarketBody(body)).catch(()=>{}); } return; }
  ensureView(name);
});
```

- [ ] **Step 4: `hub/20_home.js` — 용어 개수 통계 타일**

`renderHome` 의 `<div class="v">${(D.glossary||[]).length}</div>` 를
```js
<div class="v">${(((D.build&&D.build.counts)||{}).glossary) ?? (D.glossary||[]).length}</div>
```

- [ ] **Step 5: `hub/22_stocks.js` — `renderChat` 을 개수 필드 기준으로**

```js
function renderChat(s){
  const c=s.chat; if(!c) return '';
  const st=c.stance||{};
  const badge=`<span style="color:#7c3aed">강세 ${st.bullish||0} · 약세 ${st.bearish||0} · 관망 ${st.watch||0}</span>`;
  const ops=c.opinions||[], mkt=c.market_news||[], nws=c.news||[];
  const opsN=c.opinions_n??ops.length, mktN=c.market_news_n??mkt.length, nwsN=c.news_n??nws.length;   // 코어는 앞부분만 싣고 개수를 따로 준다 (스펙 C2)
  const opHtml = ops.slice(0,CHAT_INIT_OP).map((m,i)=>chatMentionRow(s,'opinion',m,i)).join('')
    || '<div style="font-size:11.5px;color:var(--text-4)">개별 의견 없음</div>';
  const opMore = opsN>CHAT_INIT_OP
    ? `<div class="chat-more" data-chat-stock="${esc(s.name)}" data-chat-kind="opinion" data-chat-shown="${Math.min(CHAT_INIT_OP,ops.length)}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 의견 ${opsN-CHAT_INIT_OP}건 더보기</div>` : '';
  const mktBlock = mktN
    ? `<details class="chat-mkt" style="margin-top:6px"><summary style="cursor:pointer;color:#16a34a;font-size:11.5px">📰 관련 시황 ${mktN}건</summary>
        <div class="chat-mkt-body" data-chat-stock="${esc(s.name)}" data-chat-shown="0"></div></details>` : '';
  const nwHtml = nws.slice(0,CHAT_INIT_NEWS).map(chatNewsRow).join('');
  const nwMore = nwsN>CHAT_INIT_NEWS
    ? `<div class="chat-more-news" data-chat-stock="${esc(s.name)}" data-chat-shown="${Math.min(CHAT_INIT_NEWS,nws.length)}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 뉴스 ${nwsN-CHAT_INIT_NEWS}건 더보기</div>` : '';
  return `<div style="margin-top:10px;border-top:1px dashed var(--border);padding-top:8px">
    <div style="font-size:11.5px;font-weight:700;color:#7c3aed;margin-bottom:4px">💬 채팅 근거 · ${c.count}회 · ${badge}</div>
    <div style="font-size:11px;color:var(--text-3);margin-bottom:3px">💡 의견</div>${opHtml}${opMore}
    ${mktBlock}
    ${nwsN?`<div style="font-size:11px;color:var(--text-3);margin:5px 0 3px">📰 뉴스(최신순)</div>${nwHtml}${nwMore}`:''}
  </div>`;
}
```
`chatNewsRow` 의 `href="${esc(n.url)}"` → `href="${esc(safeHref(n.url))}"`.

- [ ] **Step 6: `hub/30_search.js` — 지연 로딩 + 디바운스(P5 일부)**

파일 첫 두 줄 `let searchFilter='all'; const SEARCH=(D.search||[]);` 를:
```js
let searchFilter='all';
let SEARCH=[];                     // search 청크 로딩 후 채워진다 (P1)
let searchTimer=null;
function ensureSearch(){ return loadChunk('search').then(()=>{ SEARCH = D.search||[]; }); }
function scheduleSearch(){
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>ensureSearch().then(runSearch).catch(()=>{
    const p=$('#searchPanel'); p.innerHTML=chunkFailHtml('search'); p.classList.add('open'); }), 120);   // 키스트로크 디바운스
}
```
`scoreItem` 의 첫 줄을 사전 토큰화 필드(Track A 가 빌드 시 넣는 `hay`) 우선으로 — 항목을 변경하지 않는다(불변 규칙):
```js
  const hay = it.hay || (it.title+' '+it.snippet+' '+(it.tags||[]).join(' ')+' '+it.kind).toLowerCase();
```
리스너 두 줄을:
```js
$('#q').addEventListener('input',scheduleSearch);
$('#q').addEventListener('focus',()=>{ ensureSearch().catch(()=>{}); if($('#q').value.trim())scheduleSearch(); });
```
`#clr` 핸들러의 `runSearch()` 는 그대로 둔다(빈 값이면 패널만 닫는다).

- [ ] **Step 7: `hub/40_state.js` — 채팅 더보기/시황을 청크 로딩 후 실행**

`function chatArr(...)` 아래의 **`.chat-more`/`.chat-more-news` 를 처리하는 click 리스너 1개**와 **capture 단계 `toggle` 리스너 1개**를 다음으로 교체한다. 그 사이에 있는 `.cg-more`/`[data-cg-expand]` 전역 섹션 click 리스너는 **그대로 둔다**(채팅 탭 더보기 담당):
```js
function expandChatMore(el){
  const name=el.dataset.chatStock, kind=el.dataset.chatKind||'opinion', shown=+el.dataset.chatShown;
  const arr=chatArr(name,kind); const next=Math.min(arr.length, shown+CHAT_MORE);
  el.insertAdjacentHTML('beforebegin', arr.slice(shown,next).map((m,i)=>chatMentionRow(STOCK_BY_NAME[name],kind,m,shown+i)).join(''));
  el.dataset.chatShown=next;
  const label=kind==='market'?'시황':'의견';
  if(next>=arr.length) el.remove(); else el.textContent=`＋ ${label} ${arr.length-next}건 더보기`;
}
function expandChatNews(el){
  const name=el.dataset.chatStock, shown=+el.dataset.chatShown;
  const s=STOCK_BY_NAME[name], arr=(s&&s.chat&&s.chat.news)||[];
  const next=Math.min(arr.length, shown+CHAT_MORE);
  el.insertAdjacentHTML('beforebegin', arr.slice(shown,next).map(chatNewsRow).join(''));
  el.dataset.chatShown=next;
  if(next>=arr.length) el.remove(); else el.textContent=`＋ 뉴스 ${arr.length-next}건 더보기`;
}
function withStockChat(el, fn){            // 전체 채팅 블록(stockchat 청크)이 필요한 동작 공통 래퍼
  const prev=el.textContent; el.textContent='불러오는 중…';
  loadChunk('stockchat').then(()=>fn(el)).catch(()=>{ el.textContent=prev+' (실패 · 다시 누르면 재시도)'; });
}
document.addEventListener('click', e=>{
  const opMore=e.target.closest('.chat-more');      if(opMore){ withStockChat(opMore, expandChatMore); return; }
  const nwMore=e.target.closest('.chat-more-news'); if(nwMore){ withStockChat(nwMore, expandChatNews); return; }
});
function fillMarketBody(body){
  const name=body.dataset.chatStock, arr=chatArr(name,'market');
  const n=Math.min(arr.length,5);
  body.innerHTML=arr.slice(0,n).map((m,i)=>chatMentionRow(STOCK_BY_NAME[name],'market',m,i)).join('')
    + (arr.length>n?`<div class="chat-more" data-chat-stock="${esc(name)}" data-chat-kind="market" data-chat-shown="${n}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 시황 ${arr.length-n}건 더보기</div>`:'');
  body.dataset.chatShown=n;
}
document.addEventListener('toggle', e=>{
  const d=e.target.closest('details.chat-mkt'); if(!d||!d.open) return;
  const body=d.querySelector('.chat-mkt-body'); if(!body || +body.dataset.chatShown>0) return;
  body.innerHTML='<div class="v-mini">불러오는 중…</div>';
  loadChunk('stockchat').then(()=>fillMarketBody(body)).catch(()=>{ body.innerHTML=chunkFailHtml('stockchat'); });
}, true);
```
(`cgDesc`/`.cg-more` 전역 섹션 핸들러는 chat 청크가 이미 로딩된 채팅 탭에서만 동작하므로 그대로.)

- [ ] **Step 8: `hub/61_report_modal.js` — 채팅 모달은 전체 블록 로딩 후**

`function openChatModal(stockName, kind, idx){` 를 `function _openChatModal(stockName, kind, idx){` 로 바꾸고, 그 위에:
```js
function openChatModal(stockName, kind, idx){
  loadChunk('stockchat').then(()=>_openChatModal(stockName, kind, idx))
    .catch(()=>_openChatModal(stockName, kind, idx));   // 실패해도 코어에 실린 앞부분(idx<3)은 열린다
}
```
`_openChatModal` 안의 뉴스 링크 `href="${esc(n.url)}"` → `href="${esc(safeHref(n.url))}"`.

- [ ] **Step 9: `hub/25_chat.js` — `cgNewsRow` 링크** `href="${esc(n.url||'#')}"` → `href="${esc(safeHref(n.url))}"`.

- [ ] **Step 10: `hub/70_exec_ux.js` — 커맨드팔레트 용어 항목은 청크 로딩 후 재구성**

`function openCommand(){...}` 를:
```js
function openCommand(){
  const m=$('#cmdk');m.classList.add('open');$('#cmdInput').value='';cmdIndex=0;drawCommandList();setTimeout(()=>$('#cmdInput').focus(),20);
  if(!(D.glossary||[]).length) loadChunk('glossary').then(()=>{ CMD_ITEMS=buildCommandItems(); drawCommandList(); }).catch(()=>{});
}
```

- [ ] **Step 11: `sw.js` v4 전체 교체**

```js
/* From Us Knowledge Hub — Service Worker v4
   셸(html): stale-while-revalidate — 캐시 즉시 표시 + 백그라운드 갱신
   kb.<chunk>.<hash>.json: cache-first — 해시가 바뀌면 URL이 바뀌므로 영구 캐시 안전.
   청크별로 구 해시만 정리한다 (chat 청크를 받으면서 core 캐시를 지우면 안 된다). */
const CACHE = 'fu-hub-v4';
const PRECACHE = ['./hub.html'];
// kb.core.<h>.json · kb.chat.<h>.json … | 구 형식 kb.<h>.json 도 인식(청크명 'legacy')
const KB_RE = /\/kb\.(?:([a-z]+)\.)?[0-9a-f]{6,}\.json$/;

self.addEventListener('install', e => {
  // cache:'reload' — HTTP 캐시를 우회해 항상 네트워크의 최신 셸을 프리캐시
  e.waitUntil(caches.open(CACHE)
    .then(c => c.addAll(PRECACHE.map(u => new Request(u, {cache: 'reload'}))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function chunkOf(pathname) {
  const m = KB_RE.exec(pathname);
  return m ? (m[1] || 'legacy') : null;
}

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || !e.request.url.startsWith(self.location.origin)) return;
  const url = new URL(e.request.url);
  const path = url.pathname;

  // 탈출구: ?nosw= 가 붙은 요청은 가로채지 않고 네트워크로 직행 (version.json 확인·캐시버스터 재로드)
  if (url.searchParams.has('nosw')) return;

  const chunk = chunkOf(path);
  if (chunk) {
    e.respondWith(
      caches.match(e.request).then(m => m || fetch(e.request).then(r => {
        if (r && r.ok) {
          const cp = r.clone();
          caches.open(CACHE).then(async c => {
            const keys = await c.keys();
            await Promise.all(keys
              .filter(k => chunkOf(new URL(k.url).pathname) === chunk && k.url !== e.request.url)
              .map(k => c.delete(k)));                 // 같은 청크의 구 해시만 삭제
            c.put(e.request, cp);
          });
        }
        return r;
      }))
    );
    return;
  }

  // 나머지 (셸·아이콘 등) — stale-while-revalidate
  e.respondWith(
    caches.match(e.request, {ignoreSearch: true}).then(cached => {
      const net = fetch(e.request).then(r => {
        if (r && r.ok) { const cp = r.clone(); caches.open(CACHE).then(c => c.put(e.request, cp)); }
        return r;
      }).catch(() => cached || caches.match('./hub.html'));
      return cached || net;
    })
  );
});
```

`tests/test_phases.py::test_hub_template_has_kb_retry_fallback` 의 `"fu-hub-v3"` → `"fu-hub-v4"`, `"cache: 'reload'"` 단언은 유지(위 코드에 문자열 그대로 있음).

- [ ] **Step 12: 전량 확인**

```bash
VERIFY_SKIP=1 python -m pytest tests/ -q
python build_hub.py --phase render --json knowledge_base.json --out hub.html && ls -la kb.*.json version.json
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```
기대: 단위 PASS · `kb.core` ≈ 1.5~2MB, `kb.chat` ≈ 2.3MB, `kb.search` ≈ 1.4MB, `kb.glossary` ≈ 0.5MB, `kb.stockchat` ≈ 1.5MB · 스모크 전부 PASS(청크 테스트 포함).

수동 확인(브라우저): 종목 행 펼침 → "＋ 의견 N건 더보기" 클릭 시 `kb.stockchat.*` 가 네트워크 탭에 1회만 나타나고 목록이 늘어나는지, 채팅 탭 진입 시 `kb.chat.*`, 용어 탭 진입 시 `kb.glossary.*`.

- [ ] **Step 13: 커밋**

```bash
git add hub/ sw.js tests/
git commit -m "perf(hub): 청크 지연 로딩(loadChunk) — 검색/용어/채팅/종목채팅은 필요 시점에 fetch, SW v4 청크별 구해시 정리, 검색 디바운스·safeHref"
```

---

## Task 7: 새 버전 토스트 (P6) + merge URL 필터 (Q4)

**Files:**
- Modify: `hub_template.html` (부트스트랩 스크립트·CSS)
- Modify: `merge_hub.py`
- Create: `tests/test_merge_url.py`

- [ ] **Step 1: merge URL 필터 테스트 (RED)** — `tests/test_merge_url.py`:

```python
# -*- coding: utf-8 -*-
"""채팅 뉴스 URL 은 http/https 만 허브에 실린다 — javascript: 등은 빈 문자열로 (Q4)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_safe_url_allows_only_http_https():
    from merge_hub import _safe_url
    assert _safe_url("https://n.news.naver.com/a/1") == "https://n.news.naver.com/a/1"
    assert _safe_url("http://x.y/z") == "http://x.y/z"
    assert _safe_url("javascript:alert(1)") == ""
    assert _safe_url("data:text/html,hi") == ""
    assert _safe_url(None) == ""


def test_merge_filters_news_urls():
    from merge_hub import merge
    kb = {"build": {}, "stocks": [{"name": "삼성전자", "count": 1, "mentions": []}], "glossary": [], "sectors": []}
    chat = {"stocks": {"삼성전자": {"count": 2, "mentions": [], "news": [
                {"date": "2026-08-01", "title": "a", "url": "javascript:alert(1)"},
                {"date": "2026-08-02", "title": "b", "url": "https://ok/1"}]}},
            "news": [{"date": "2026-08-01", "title": "a", "url": "javascript:alert(1)", "stocks": []}]}
    out, _ = merge(kb, chat)
    urls = [n["url"] for n in out["stocks"][0]["chat"]["news"]]
    assert "javascript:alert(1)" not in urls and "https://ok/1" in urls
    assert out["chat"]["news"][0]["url"] == ""
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_merge_url.py -q` → FAIL (`_safe_url` 없음).

- [ ] **Step 3: `merge_hub.py` 구현** — `_name_in` 위에 추가:

```python
def _safe_url(u):
    """허브에 싣는 링크는 http/https 만 — 카톡에서 온 문자열을 그대로 href 에 넣지 않는다."""
    u = (u or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else ""

def _safe_news(items):
    return [{**n, "url": _safe_url(n.get("url"))} for n in (items or [])]
```
`_chat_block` 의 `news = _sort_desc(cs.get("news", []))[:NEWS_KEEP]` → `news = _safe_news(_sort_desc(cs.get("news", []))[:NEWS_KEEP])`.
`merge` 의 `"news":chat.get("news",[])` → `"news":_safe_news(chat.get("news",[]))`.

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_merge_url.py -q` → PASS.

- [ ] **Step 5: 토스트 — `hub_template.html`**

부트스트랩 스크립트(마지막 `<script>`, `document.querySelectorAll('script[type="fu-app"]')...` 가 있는 블록)의 `if(boot){ boot.style.opacity = '0'; ... }` 줄 **뒤**, `})();` **앞**에:
```js
  // 새 빌드 감지 (P6) — 셸은 SWR 이라 재방문 첫 화면이 구 셸일 수 있다. version.json 은 ?nosw= 로 SW 를 우회한다.
  setTimeout(function(){
    fetch('./version.json?nosw=' + Date.now(), {cache: 'no-store'})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(v){
        var cur = (typeof window.KB_URL === 'string') ? window.KB_URL : (window.KB_URL && window.KB_URL.core);
        if(v && v.core && cur && v.core !== cur) showUpdateToast(v.generated || '');
      }).catch(function(){});
  }, 4000);
```
같은 스크립트의 `(async function(){` **앞**에 함수 추가:
```js
function showUpdateToast(gen){
  if(document.getElementById('fu-toast')) return;
  var t = document.createElement('div'); t.id = 'fu-toast'; t.className = 'fu-toast'; t.setAttribute('role', 'status');
  t.innerHTML = '새 데이터가 준비됐습니다' + (gen ? ' · ' + gen : '') + ' <button type="button">새로고침</button>';
  t.querySelector('button').onclick = function(){ location.replace(location.pathname + '?nosw=' + Date.now() + location.hash); };
  document.body.appendChild(t);
}
```
CSS — `</style>` 직전에:
```css
/* ── 새 버전 토스트 ── */
.fu-toast{position:fixed;left:50%;bottom:calc(74px + env(safe-area-inset-bottom));transform:translateX(-50%);z-index:200;
  background:var(--side-bg);color:var(--side-text);border:1px solid var(--side-line);border-radius:12px;padding:10px 14px;
  font-size:13px;box-shadow:0 8px 24px var(--shadow);white-space:nowrap;}
.fu-toast button{margin-left:10px;background:var(--side-gold);color:#181410;border:0;border-radius:8px;padding:5px 10px;font-weight:700;cursor:pointer;font-family:inherit;}
@media(min-width:941px){.fu-toast{bottom:24px;}}
```

- [ ] **Step 6: 스모크에 토스트 테스트 추가** — 구 셸 상황을 흉내 낸다: `version.json` 의 core 를 바꿔 두고 로드.

```python
def test_update_toast_when_version_differs(page, site_url):
    site = os.environ["E2E_SITE_DIR"]
    vpath = os.path.join(site, "version.json")
    orig = open(vpath, encoding="utf-8").read()
    try:
        with open(vpath, "w", encoding="utf-8") as f:
            f.write('{"core":"kb.core.0000000000.json","generated":"2099-01-01 00:00"}')
        _boot(page, site_url)
        page.wait_for_selector("#fu-toast", timeout=10000)
    finally:
        with open(vpath, "w", encoding="utf-8") as f:
            f.write(orig)
```

```bash
python build_hub.py --phase render --json knowledge_base.json --out hub.html
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```
기대: PASS. `test_no_javascript_hrefs` 도 이제 반드시 PASS(merge 필터 + safeHref 이중 방어) — 단, 로컬 `knowledge_base.json` 은 구 merge 산출물이므로 `collect` 를 다시 돌리지 않으면 Python 필터는 반영되지 않는다(safeHref 만으로 통과).

- [ ] **Step 7: 커밋**

```bash
git add hub_template.html merge_hub.py tests/test_merge_url.py tests/e2e/test_hub_smoke.py
git commit -m "feat(hub): version.json 기반 '새 데이터 준비됨' 토스트 + 채팅 뉴스 URL http/https 필터"
```

---

## Task 8: 문서 + CI 통과 + 머지

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README 갱신** — "아키텍처" 블록의 render 줄을:
```
       └─ build_hub.py --phase render   → hub.html(셸: hub/*.js concat) + kb.core.<hash>.json + kb.{chat,search,glossary,stockchat}.<hash>.json + version.json
```
빌더 표 아래에 행 추가:
```
| `hublib/split.py` | render 출력 분할·슬림화 (코어/청크, 순수 함수) |
| `hub/*.js` | 허브 셸 앱 코드 — 파일명 숫자 순서로 concat 되어 `hub_template.html` 의 `/*APPJS*/` 마커에 주입된다 |
```
"knowledge_base.json 스키마" 절 첫 문단의 `kb.<hash>.json 으로 fetch 해 렌더한다` → `kb.core.<hash>.json(첫 화면) + 청크(kb.chat/search/glossary/stockchat.<hash>.json, 필요 시점 fetch) 로 받아 렌더한다. 분할 규칙은 docs/superpowers/specs/2026-08-23-hub-improvement-design.md §3.3 C2`.
"테스트" 절에 추가:
```bash
# 셸 JS 스모크 (렌더 후)
pip install pytest-playwright && python -m playwright install chromium
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```

- [ ] **Step 2: 전체 테스트·렌더·스모크 마지막 확인**

```bash
VERIFY_SKIP=1 python -m pytest tests/ generator/test_parse.py -q && python build_hub.py --phase render --json knowledge_base.json --out hub.html && E2E_SITE_DIR=. python -m pytest tests/e2e -q
```

- [ ] **Step 3: 커밋·푸시·PR** (@superpowers:finishing-a-development-branch)

```bash
git add README.md && git commit -m "docs: 허브 기반 개편 — hub/*.js 모듈·kb 분할·스모크 테스트 설명"
git push -u origin feat/hub-foundation
gh pr create --title "허브 기반 개편: 모듈 분리·지연 렌더·청크 로딩·스모크 테스트" --body "$(cat <<'EOF'
## 요약
- 셸 JS 를 hub/*.js 18개로 분리(빌드타임 concat, 동작 불변)
- kb 를 core + chat/search/glossary/stockchat 청크로 분할, 필요 시점 로딩 · SW v4
- 활성 탭만 렌더 + 스파크라인 IntersectionObserver
- reports 슬림화, version.json 토스트, URL 스킴 필터
- Playwright 스모크 18개 (CI _site 기준)

## 측정 (로컬)
- kb 단일 9.2MB → core x.xMB + 청크 (첫 화면 전송 gzip 2.7MB → ~0.5MB)
- 부트 DOM 17,655 → ~3,000 · canvas 213 → <15

## 테스트 계획
- [ ] CI 단위 123+ · e2e 18 PASS
- [ ] 배포 후 모바일에서 홈·종목·채팅 탭 진입, 더보기, 검색 확인
- [ ] 다음 날 첫 방문 시 토스트 표시 확인

스펙: docs/superpowers/specs/2026-08-23-hub-improvement-design.md
EOF
)"
```

CI 가 초록이면 머지. 머지 후 Track A·B 계획을 시작한다:

```bash
git checkout main && git pull
git worktree add ../fromus-track-a -b feat/hub-track-a
git worktree add ../fromus-track-b -b feat/hub-track-b
```

---

## 범위 밖 (이 계획에 넣지 않는다)

- 검색 Web Worker, Chart.js 제거, 폰트 self-host — 측정 후 별도 판단
- `hub/*.js` 의 ES 모듈화 — 스펙 §3.2
- F7 익명화 — 사용자 결정으로 제외 (`sharer` 실명 유지)
