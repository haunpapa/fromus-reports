# 지식허브 개선 — Track B (셸 UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 허브 셸에 (1) 외부 의존 정리(Chart.js vendoring·폰트 축소), (2) 모바일 내비 정리, (3) 채팅까지 닿는 통합 검색 UI, (4) 공유 가능한 종목 상세 뷰 `#stock/<이름>`, (5) 홈 "오늘 달라진 것"·AI 데일리·종목 이유, (6) 검증 탭 코호트 토글·테마·분포 히스토그램을 추가한다. Track A 의 새 필드가 아직 없어도(널) 모든 화면이 동작해야 한다.

**Architecture:** 기반 계획이 만든 `hub/*.js` 모듈 구조 위에서 작업한다. 새 화면은 새 파일(`hub/27_stock_detail.js`), 기존 화면 수정은 해당 모듈 안에서. 외부 라이브러리를 추가하지 않는다(차트는 기존 `drawSpark` 와 같은 canvas 직접 그리기). 각 Task 는 Playwright 스모크(`tests/e2e/test_hub_features.py`)로 고정한다.

**Tech Stack:** 순수 JS/CSS · Chart.js 4.4.1(vendored, 기존 3개 차트만) · pytest-playwright

**Spec:** [docs/superpowers/specs/2026-08-23-hub-improvement-design.md](../specs/2026-08-23-hub-improvement-design.md) — 계약 C3~C6 의 소비자.

**전제:** 00-foundation 머지됨. 이 트랙은 `hublib/*.py`·`merge_hub.py`·`ai_digest.py` 를 **건드리지 않는다**. `.github/workflows/build.yml` 은 `cp -r vendor` 1줄, `sw.js` 는 프리캐시 1줄만.

**렌더·스모크 루틴 (매 Task 끝에 실행):**
```bash
python build_hub.py --phase render --json knowledge_base.json --out hub.html && E2E_SITE_DIR=. python -m pytest tests/e2e -q
```

---

## 파일 구조

| 파일 | 상태 | 책임 |
|---|---|---|
| `vendor/chart.umd.min.js` | 신규(커밋) | Chart.js 4.4.1 — cdnjs 의존 제거 |
| `hub_template.html` | 수정 | head(스크립트·폰트), bnav 5+더보기 시트, 검색 시트 마크업, `#view-stock`, CSS |
| `sw.js` | 수정(1줄) | 프리캐시에 vendor 추가 |
| `hub/10_tabs.js` | 수정 | `stock` 라우트, 더보기 시트 |
| `hub/30_search.js` | 재작성 (~200줄) | 검색 2.0 UI(필터·별칭·핀·최근 검색어·라우팅) + 모바일 시트 |
| `hub/27_stock_detail.js` | 신규 (~220줄) | 종목 상세 뷰 + 주가 오버레이 canvas |
| `hub/20_home.js` | 수정 | 오늘 달라진 것 카드 · AI 데일리 3줄 |
| `hub/22_stocks.js` | 수정 | 행 부제(AI 이유) · neutral 뉴스 표시 |
| `hub/23_verify.js` | 수정 | 코호트 토글 · 테마 표 · 히스토그램 · `vCallRows(name, calls)` |
| `hub/31_nav.js` | 수정 | `data-stock` 클릭 → 상세 뷰 |
| `hub/25_chat.js` | 수정 | neutral 뉴스 클래스 |
| `tests/e2e/test_hub_features.py` | 신규 | Task 별 스모크 |
| `tests/e2e/test_hub_smoke.py` | 수정(1곳) | 외부 스크립트 0 단언 |
| `.github/workflows/build.yml` | 수정(1줄) | `cp -r vendor _site/` |

## 사전 확인

- [ ] `git worktree add ../fromus-track-b -b feat/hub-track-b` 후 그 폴더에서 작업
- [ ] `VERIFY_SKIP=1 python -m pytest tests/ -q` PASS, 렌더·스모크 루틴 PASS
- [ ] `tests/e2e/test_hub_features.py` 를 만들고 `test_hub_smoke.py` 의 `_boot`·`IGNORED_CONSOLE` 를 import 해 쓴다:

```python
# -*- coding: utf-8 -*-
"""Track B 기능 스모크 — Task 별로 아래에 추가한다."""
import os
import pytest
pytest.importorskip("playwright")
from tests.e2e.test_hub_smoke import _boot   # noqa: E402
```

---

## Task 1: Chart.js vendoring + defer · 폰트 웨이트 축소 (P4)

**Files:** `vendor/chart.umd.min.js`, `hub_template.html`, `sw.js`, `.github/workflows/build.yml`, `tests/e2e/test_hub_smoke.py`

- [ ] **Step 1: 스모크 단언 (RED)** — `test_hub_smoke.py` 의 `test_boot_renders_home_without_errors` 끝에:

```python
    ext = page.evaluate("[...document.scripts].filter(s=>/^https?:/.test(s.src)).length")
    assert ext == 0, "외부 호스트 스크립트가 남아 있음"
    assert page.evaluate("typeof window.Chart") == "function"
```

- [ ] **Step 2: 라이브러리 내려받기** (현재 cdnjs 에서 쓰던 것과 같은 파일)

```bash
mkdir -p vendor && curl -fsSL https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js -o vendor/chart.umd.min.js
head -c 120 vendor/chart.umd.min.js; echo; wc -c vendor/chart.umd.min.js
```
기대: 첫 줄에 `Chart.js v4.4.1`, 크기 ≈ 200KB. 아니면 중단.

- [ ] **Step 3: 템플릿 head** — `<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>` 를
```html
<script defer src="./vendor/chart.umd.min.js" id="chartjs"></script>
```
로. 폰트 링크 위에 preconnect 2줄:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
```
폰트 링크의 `family=` 를 실제 사용 웨이트로 줄인다 — 먼저 확인:
```bash
grep -o "font-weight:[0-9]*" hub_template.html hub/*.js | sort | uniq -c
```
결과에 **나오는 웨이트만** 남긴다(예: Sans 400;500;700;900 · Serif 700;900 · Playfair 0,700;1,600 · Mono 400;500;600). 300·600 이 안 쓰이면 제거.

- [ ] **Step 4: 부트가 Chart 준비를 기다리게** — 부트스트랩 스크립트에서 코어를 받는 `window.DATA = await r.json();` (기반 계획 Task 6 Step 2a 이후에도 이 줄은 그대로다) 다음 줄에:
```js
    await new Promise(function(res){           // defer 스크립트가 아직이면 load/error 까지(최대 3초) 대기
      if(window.Chart) return res();
      var s=document.getElementById('chartjs'); if(!s) return res();
      s.addEventListener('load',res); s.addEventListener('error',res); setTimeout(res,3000);
    });
```

- [ ] **Step 5: SW·워크플로** — `sw.js` `const PRECACHE = ['./hub.html'];` → `['./hub.html', './vendor/chart.umd.min.js']` 그리고 `CACHE` 를 `'fu-hub-v5'` 로 (`tests/test_phases.py` 의 `fu-hub-v4` 단언도 `v5` 로). `build.yml` `Assemble site` 에 `cp -r vendor _site/`, 그리고 `on.push.paths` 에 `- 'vendor/**'` 추가.

- [ ] **Step 6: 렌더·스모크 루틴** → PASS. 오프라인 확인(선택): 브라우저 DevTools Network "Offline" 에서 새로고침 → 분석 탭 센티멘트 차트가 그려지는지.

- [ ] **Step 7: 커밋**
```bash
git add vendor hub_template.html sw.js .github/workflows/build.yml tests/
git commit -m "perf(hub): Chart.js vendoring + defer + SW 프리캐시(v5), 폰트 웨이트 축소·preconnect — 렌더 블로킹 외부 리소스 0"
```

---

## Task 2: 모바일 내비 — 하단 탭 5개 + 더보기 시트, 검색 전체화면 시트 (F6)

**Files:** `hub_template.html`, `hub/10_tabs.js`, `hub/30_search.js`, `tests/e2e/test_hub_features.py`

- [ ] **Step 1: 스모크 (RED)** — `test_hub_features.py`:

```python
def test_mobile_bottom_nav_has_five_plus_more(page, site_url):
    page.set_viewport_size({"width": 375, "height": 812})
    _boot(page, site_url, "#stocks")            # 홈이 아닌 탭에서 더보기를 눌러도 탭이 바뀌면 안 된다
    visible = page.evaluate("[...document.querySelectorAll('#bnav .tab')].filter(b=>b.offsetParent!==null).length")
    assert visible == 5
    page.click("#bnavMore")
    page.wait_for_selector("#bsheet.open", timeout=5000)
    assert "active" in (page.get_attribute("#view-stocks", "class") or ""), "더보기가 showTab(undefined) 로 홈으로 튐"
    page.click('#bsheet .tab[data-tab="glossary"]')
    page.wait_for_function("document.querySelector('#view-glossary').classList.contains('active')", timeout=10000)
    assert page.evaluate("document.querySelector('#bsheet').classList.contains('open')") is False
    assert "active" in page.get_attribute("#bnavMore", "class")


def test_mobile_search_sheet_opens_and_closes(page, site_url):
    page.set_viewport_size({"width": 375, "height": 812})
    _boot(page, site_url)
    page.click("#q")
    page.wait_for_selector("body.search-open", timeout=5000)
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    # 기하 확인 — 클래스만 붙고 55px 띠에 갇히는 회귀를 잡는다 (.topbar 가 전체화면 층이어야 한다)
    box = page.evaluate("(r=>({h:r.height,t:r.top}))(document.querySelector('.topbar').getBoundingClientRect())")
    assert box["t"] == 0 and box["h"] >= 700, box
    panel = page.evaluate("document.querySelector('#searchPanel').getBoundingClientRect().height")
    assert panel > 200, "결과 패널이 보이는 높이로 펼쳐져야 한다"
    assert page.evaluate("getComputedStyle(document.querySelector('#bnav')).display") == "none"
    page.click("#qClose")
    page.wait_for_function("!document.body.classList.contains('search-open')", timeout=5000)
```

- [ ] **Step 2: 마크업** — `hub_template.html` 의 `<nav class="bnav" id="bnav">…</nav>` 전체를:

```html
<nav class="bnav" id="bnav" aria-label="하단 탭">
  <button class="tab active" data-tab="home"><span class="t-ico">⌂</span>개요</button>
  <button class="tab" data-tab="stocks"><span class="t-ico">📈</span>종목</button>
  <button class="tab" data-tab="sectors"><span class="t-ico">🧩</span>섹터</button>
  <button class="tab" data-tab="strategy"><span class="t-ico">🧭</span>전략</button>
  <button class="tab" id="bnavMore" type="button" aria-haspopup="true" aria-expanded="false"><span class="t-ico">☰</span>더보기</button>
</nav>
<div class="bsheet" id="bsheet" role="dialog" aria-label="더보기">
  <div class="bsheet-bd" data-bsheet-close></div>
  <div class="bsheet-box">
    <button class="tab" data-tab="analytics"><span class="t-ico">📊</span>분석</button>
    <button class="tab" data-tab="verify" style="display:none"><span class="t-ico">✅</span>검증</button>
    <button class="tab" data-tab="chat"><span class="t-ico">💬</span>채팅</button>
    <button class="tab" data-tab="glossary"><span class="t-ico">📚</span>용어</button>
    <button class="tab" data-tab="graph"><span class="t-ico">🕸</span>관계망</button>
    <button class="tab" data-tab="trade"><span class="t-ico">🚢</span>수출입동향</button>
  </div>
</div>
```
사이드바의 `<button class="tab" data-tab="chat" style="display:none">` 에서 `style="display:none"` 을 제거한다 — 더보기 시트에 채팅이 보이는데 데스크톱 사이드바만 숨길 이유가 없고, 발언자 실명 표기를 유지하기로 한 결정(스펙 §2)에 따라 숨김 근거도 없다. 대신 채팅 데이터가 없는 빌드에서는 숨긴다 — `hub/10_tabs.js` 에 `syncVerifyTab` 과 같은 꼴로 추가하고 `hub/90_init.js` 의 `syncVerifyTab();` 옆에서 호출한다:
```js
function syncChatTab(){ const on=!!(D.chat&&D.chat.counts); $$('.tab[data-tab="chat"]').forEach(b=>{ b.style.display=on?'':'none'; }); }
```
(숨김을 유지하고 싶으면 시트의 채팅 버튼도 같이 빼고 이 단계를 건너뛴다.)

검색창 `.searchbox` 안 `<button class="clr" id="clr">✕</button>` 뒤에:
```html
<button class="qclose" id="qClose" type="button" aria-label="검색 닫기">닫기</button>
```

- [ ] **Step 3: CSS** — `</style>` 직전:

```css
/* ── 모바일 더보기 시트 ── */
.bsheet{display:none;position:fixed;inset:0;z-index:90;}
.bsheet.open{display:block;}
.bsheet-bd{position:absolute;inset:0;background:rgba(0,0,0,.35);}
.bsheet-box{position:absolute;left:0;right:0;bottom:0;background:var(--surface);border-radius:18px 18px 0 0;
  padding:14px 12px calc(14px + env(safe-area-inset-bottom));display:grid;grid-template-columns:repeat(3,1fr);gap:8px;
  box-shadow:0 -8px 30px var(--shadow);}
.bsheet-box .tab{flex-direction:column;align-items:center;gap:4px;padding:12px 6px;color:var(--text-2);background:var(--surface-2);min-height:64px;font-size:12px;}
.bsheet-box .tab:hover{color:var(--text);background:var(--surface-3);}   /* 사이드바용 .tab:hover{color:#fff} 덮어쓰기 */
.bsheet-box .tab.active{color:var(--gold);background:var(--gold-bg);}
.bsheet-box .tab.active::before{display:none;}
/* ── 모바일 검색 시트 ──
   .searchwrap 은 .topbar(backdrop-filter + z-index:60) 의 자손이라 거기에 position:fixed 를 줘도
   topbar 가 containing block 이 되어 55px 띠 안에 갇힌다. 그래서 body 에 클래스를 걸고 .topbar 자체를 전체화면 층으로 만든다. */
.qclose{display:none;}
@media(max-width:940px){
  body.search-open .topbar{position:fixed;inset:0;z-index:100;backdrop-filter:none;background:var(--bg);overflow:auto;border-bottom:0;}
  body.search-open .topbar-inner{flex-direction:column;align-items:stretch;padding:10px 12px;}
  body.search-open .m-logo{display:none;}
  body.search-open .searchbox{display:flex;align-items:center;}
  body.search-open .qclose{display:inline-block;margin-left:8px;background:transparent;border:0;color:var(--gold);font-weight:700;font-size:13px;cursor:pointer;}
  body.search-open .search-panel{position:static;margin-top:8px;max-height:none;box-shadow:none;}
  body.search-open .search-panel.open{display:block;}
  body.search-open .bnav{display:none;}
  .strow-head{min-height:48px;}                 /* 터치 타깃 */
}
```

- [ ] **Step 4: `hub/10_tabs.js`** — 먼저 기존 하단 탭 위임 핸들러를 **`data-tab` 이 있는 버튼만** 잡도록 고친다(아니면 더보기 버튼이 `showTab(undefined)` → 홈으로 튄다):
```js
const _bn=document.getElementById('bnav'); if(_bn)_bn.addEventListener('click',e=>{const b=e.target.closest('.tab[data-tab]');if(b)showTab(b.dataset.tab);});
```
그 줄 아래에:

```js
/* 모바일 더보기 시트 — 시트 안 탭이 활성이면 '더보기' 버튼이 active 를 받는다 */
const SHEET_TABS=['analytics','verify','chat','glossary','graph','trade'];
function setSheet(open){ const s=$('#bsheet'), b=$('#bnavMore'); if(!s||!b) return; s.classList.toggle('open',open); b.setAttribute('aria-expanded',open?'true':'false'); }
(function(){ const b=$('#bnavMore'), s=$('#bsheet'); if(!b||!s) return;
  b.addEventListener('click',()=>setSheet(!s.classList.contains('open')));
  s.addEventListener('click',e=>{ if(e.target.closest('[data-bsheet-close]')){setSheet(false);return;} const t=e.target.closest('.tab'); if(t){ showTab(t.dataset.tab); setSheet(false);} });
})();
```
`showTab` 의 `$$('.tab').forEach(...)` 다음 줄에:
```js
  const more=$('#bnavMore'); if(more) more.classList.toggle('active', SHEET_TABS.includes(name));
```
(시트의 `.tab[data-tab="verify"]` 도 `syncVerifyTab` 의 `$$('.tab[data-tab="verify"]')` 셀렉터에 잡히므로 추가 작업 없음.)

- [ ] **Step 5: `hub/30_search.js` 끝에 검색 시트**

세 가지 닫힘 경로를 구분한다 — **닫기 버튼**은 `history.back()` 으로 푸시한 항목을 되돌리고, **뒤로가기(popstate)** 는 이미 되돌아온 상태라 아무 이동도 하지 않으며, **결과 선택**은 마커만 지운다(`replaceState`). 결과 선택에서 `back()` 을 쓰면 그 직후 `openStock` 이 `replaceState('#stock/…')` 한 항목을 떠나 `hashchange` 가 이전 탭을 다시 열어 상세 뷰가 사라진다.
```js
/* 모바일 검색 시트 — 포커스 시 전체화면(body.search-open). 닫힘 경로: 'back'(닫기 버튼) · 'pop'(뒤로가기) · 'select'(결과 선택) */
const isNarrow=()=>matchMedia('(max-width:940px)').matches;
function openSearchSheet(){ if(!isNarrow()||document.body.classList.contains('search-open')) return;
  document.body.classList.add('search-open'); document.body.style.overflow='hidden'; try{history.pushState({fuSearch:1},'');}catch(e){} }
function closeSearchSheet(mode){ if(!document.body.classList.contains('search-open')) return;
  document.body.classList.remove('search-open'); document.body.style.overflow=''; $('#searchPanel').classList.remove('open'); $('#q').blur();
  const marked = history.state && history.state.fuSearch;
  try{ if(mode==='back' && marked) history.back(); else if(mode==='select' && marked) history.replaceState(null,'',location.href); }catch(e){} }
$('#q').addEventListener('focus',openSearchSheet);
$('#qClose').addEventListener('click',()=>closeSearchSheet('back'));
window.addEventListener('popstate',()=>closeSearchSheet('pop'));
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeSearchSheet('back'); });   // 기존 Escape 핸들러(패널 닫기)와 별개로 시트도 닫는다
```
검색 결과 클릭으로 탭이 바뀔 때 시트(모바일)와 드롭다운(데스크톱)이 남지 않도록, 기존 `document.addEventListener('click',e=>{ if(!e.target.closest('.searchwrap')) $('#searchPanel').classList.remove('open'); });` 아래에:
```js
$('#searchPanel').addEventListener('click',e=>{ if(e.target.closest('.sr,.sr-pin')){ closeSearchSheet('select'); $('#searchPanel').classList.remove('open'); } });
```

- [ ] **Step 6: 렌더·스모크 루틴** → PASS. 실기기(또는 DevTools 모바일)에서 하단 탭 5개·시트·검색 시트 눈으로 확인.

- [ ] **Step 7: 커밋**
```bash
git add hub_template.html hub/10_tabs.js hub/30_search.js tests/e2e/test_hub_features.py
git commit -m "feat(hub): 모바일 하단 탭 5개+더보기 시트, 검색 전체화면 시트(뒤로가기 닫힘), 행 터치 타깃 48px"
```

---

## Task 3: 통합 검색 2.0 UI (F1)

**Files:** `hub/30_search.js`(재작성), `hub_template.html`(CSS), `tests/e2e/test_hub_features.py`

데이터(C3): `it.source` `it.hay` `it.extra`, `D.build.aliases`. 없으면(구 데이터) 리포트 항목만·별칭 없음으로 동작.

- [ ] **Step 1: 스모크 (RED)**

```python
def test_search_alias_pins_stock_card(page, site_url):
    _boot(page, site_url)
    has_alias = page.evaluate("!!(window.DATA.build && window.DATA.build.aliases && window.DATA.build.aliases['하닉'] && (window.DATA.stocks||[]).some(s=>s.name==='SK하이닉스'))")
    if not has_alias:
        pytest.skip("aliases 없는 빌드이거나 SK하이닉스 미수록")
    page.fill("#q", "하닉")
    page.wait_for_selector("#searchPanel.open .sr-pin", timeout=15000)
    assert "SK하이닉스" in page.inner_text("#searchPanel .sr-pin")


def test_search_source_and_period_filters(page, site_url):
    _boot(page, site_url)
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    has_chat = page.evaluate("(window.DATA.search||[]).some(i=>i.source==='chat')")
    if has_chat:
        page.click('#searchPanel .sp-src[data-src="chat"]')
        page.wait_for_function("[...document.querySelectorAll('#searchPanel .sr .sr-kind')].every(k=>/채팅|목표가/.test(k.textContent))", timeout=5000)   # 핀 카드(.sr-pin)의 '종목' 은 제외
    page.click('#searchPanel .sp-period[data-period="7"]')
    page.wait_for_timeout(300)
    assert page.locator("#searchPanel .sp-period.on").get_attribute("data-period") == "7"


def test_recent_queries_shown_on_empty_focus(page, site_url):
    _boot(page, site_url)
    page.fill("#q", "반도체"); page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    page.click("#searchPanel button.sr >> nth=0")     # a.sr(채팅뉴스)은 새 탭을 열므로 button 만
    page.keyboard.press("Escape")
    page.fill("#q", ""); page.click("#q")
    page.wait_for_selector("#searchPanel .sp-recent", timeout=5000)
    assert "반도체" in page.inner_text("#searchPanel .sp-recent")
```

- [ ] **Step 2: `hub/30_search.js` 재작성** — 기반 계획의 청크 로딩·디바운스·모바일 시트를 포함한 전체:

```js
/* ───────── GLOBAL SEARCH 2.0 ───────── */
let searchFilter='all', searchSrc='all', searchPeriod='all';   // kind · 출처 · 기간
let SEARCH=[];
let searchTimer=null;
const RECENT_KEY='fu-recent-q', RECENT_N=5;
const hayOf=it=>(it.title+' '+it.snippet+' '+(it.tags||[]).join(' ')+' '+it.kind).toLowerCase();
function ensureSearch(){ return loadChunk('search').then(()=>{
  if(SEARCH.length) return;                       // 한 번만: hay 가 없는(구 빌드) 항목은 새 객체로 보강 — 원본 변경 없음
  SEARCH = (D.search||[]).map(it=> it.hay ? it : {...it, hay: hayOf(it)}); }); }
function scheduleSearch(){
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>ensureSearch().then(runSearch).catch(()=>{
    const p=$('#searchPanel'); p.innerHTML=chunkFailHtml('search'); p.classList.add('open'); }), 120);
}
function recentQueries(){ try{ return JSON.parse(localStorage.getItem(RECENT_KEY)||'[]'); }catch(e){ return []; } }
function pushRecent(q){ const list=[q, ...recentQueries().filter(x=>x!==q)].slice(0,RECENT_N); try{ localStorage.setItem(RECENT_KEY, JSON.stringify(list)); }catch(e){} }
const ALIASES=(D.build&&D.build.aliases)||{};
function expandToken(t){ const canon=ALIASES[t]; return canon ? [t, canon.toLowerCase()] : [t]; }   // '하닉' → ['하닉','sk하이닉스']
function scoreItem(it,tokens){
  const hay = it.hay;
  const title=(it.title||'').toLowerCase();
  let sc=0;
  for(const alts of tokens){
    const hit=alts.find(a=>hay.includes(a)); if(!hit) return -1;
    sc += alts.some(a=>title.includes(a)) ? 3 : 1;
  }
  return sc;
}
function periodCutoff(){ if(searchPeriod==='all') return null; return TO_DAY - (+searchPeriod); }
function pinnedStock(raw){
  const q=raw.toLowerCase(); const name=ALIASES[q] || Object.keys(STOCK_BY_NAME).find(n=>n.toLowerCase()===q);
  const s=name && STOCK_BY_NAME[name]; if(!s) return '';
  return `<div class="sr-pin" data-stock="${esc(s.name)}"><span class="sr-kind">종목</span><b>${esc(s.name)}</b>
    ${momentumChip(s)}<span class="sr-date">${s.count||0}회 · 수급 ${s.supply_count||0}${s.chat?` · 💬 ${s.chat.count}`:''}</span>
    <span class="sr-go">상세 →</span></div>`;
}
function resultRow(it,tokens){
  const top=`<div class="sr-top"><span class="sr-kind">${esc(it.kind)}</span><span class="sr-title">${hl(it.title,tokens)}</span><span class="sr-date">${esc(fmtDate(it.date))}</span></div><div class="sr-snip">${hl(it.snippet,tokens)}</div>`;
  const x=it.extra||{};
  if(it.kind==='채팅뉴스') return `<a class="sr" href="${esc(safeHref(x.url))}" target="_blank" rel="noopener">${top}</a>`;
  if(it.kind==='채팅의견'||it.kind==='목표가') return `<button class="sr" data-stock="${esc(x.stock||'')}">${top}</button>`;
  if(it.kind==='종목') return `<button class="sr" data-stock="${esc(it.title||'')}">${top}</button>`;
  return `<button class="sr" ${it.id&&FILE[it.id]?`data-report="${esc(it.id)}" data-q="${esc(it.title||'')}"`:''}>${top}</button>`;
}
function runSearch(){
  const raw=$('#q').value.trim();
  $('#clr').style.display=raw?'block':'none';
  const panel=$('#searchPanel');
  if(!raw){ drawRecent(); return; }
  const tokens=raw.toLowerCase().split(/\s+/).filter(Boolean).map(expandToken);
  const cut=periodCutoff();
  let res=SEARCH.map(it=>({it,sc:scoreItem(it,tokens)})).filter(x=>x.sc>=0);
  if(searchSrc!=='all') res=res.filter(x=>(x.it.source||'report')===searchSrc);
  if(cut!=null) res=res.filter(x=>{const d=dnum(x.it.date); return d!=null && d>=cut;});
  res.sort((a,b)=> b.sc-a.sc || (b.it.date||'').localeCompare(a.it.date||''));
  const kinds=[...new Set(res.map(x=>x.it.kind))];
  if(searchFilter!=='all') res=res.filter(x=>x.it.kind===searchFilter);
  const top=res.slice(0,50);
  const hasChat=SEARCH.some(i=>i.source==='chat');
  const head=`<div class="sp-head">
     <span class="sp-filter ${searchFilter==='all'?'on':''}" data-f="all">전체 ${res.length>50?'50+':res.length}</span>
     ${kinds.map(k=>`<span class="sp-filter ${searchFilter===k?'on':''}" data-f="${esc(k)}">${esc(k)}</span>`).join('')}</div>
     <div class="sp-head sp-head2">
       ${hasChat?['all','report','chat'].map(s=>`<span class="sp-src ${searchSrc===s?'on':''}" data-src="${s}">${{all:'출처 전체',report:'리포트',chat:'채팅'}[s]}</span>`).join(''):''}
       ${[['all','전체 기간'],['7','1주'],['31','1개월']].map(([p,l])=>`<span class="sp-period ${searchPeriod===p?'on':''}" data-period="${p}">${l}</span>`).join('')}
     </div>`;
  const body= top.length? top.map(x=>resultRow(x.it,tokens)).join('') : '<div class="sr-empty">결과가 없습니다.</div>';
  panel.innerHTML=head+pinnedStock(raw)+body;
  panel.classList.add('open');
  $('#searchHint').textContent=`“${raw}” — ${res.length}건`;
}
function drawRecent(){
  const panel=$('#searchPanel'); const rq=recentQueries();
  if(!rq.length){ panel.classList.remove('open'); panel.innerHTML=''; return; }
  panel.innerHTML=`<div class="sp-recent"><span class="sp-recent-l">최근 검색</span>${rq.map(q=>`<button type="button" class="sp-filter" data-recent="${esc(q)}">${esc(q)}</button>`).join('')}</div>`;
  panel.classList.add('open');
}
function hl(s,tokens){
  s=esc(s||'');
  tokens.flat().forEach(t=>{ if(t.length<1)return; try{s=s.replace(new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig'),'<mark>$1</mark>');}catch(e){} });
  return s;
}
$('#q').addEventListener('input',scheduleSearch);
$('#q').addEventListener('focus',()=>{ ensureSearch().catch(()=>{}); if($('#q').value.trim())scheduleSearch(); else drawRecent(); });
$('#clr').addEventListener('click',()=>{$('#q').value='';searchFilter='all';runSearch();$('#searchHint').textContent='';$('#q').focus();});
$('#searchPanel').addEventListener('click',e=>{
  const f=e.target.closest('.sp-filter[data-f]'); if(f){searchFilter=f.dataset.f;runSearch();return;}
  const s=e.target.closest('.sp-src'); if(s){searchSrc=s.dataset.src;runSearch();return;}
  const p=e.target.closest('.sp-period'); if(p){searchPeriod=p.dataset.period;runSearch();return;}
  const r=e.target.closest('[data-recent]'); if(r){$('#q').value=r.dataset.recent;scheduleSearch();return;}
  if(e.target.closest('.sr,.sr-pin')){ const q=$('#q').value.trim(); if(q) pushRecent(q); }
});
document.addEventListener('click',e=>{ if(!e.target.closest('.searchwrap')) $('#searchPanel').classList.remove('open'); });
$('#searchPanel').addEventListener('click',e=>{ if(e.target.closest('.sr,.sr-pin')){ closeSearchSheet('select'); $('#searchPanel').classList.remove('open'); } });

/* 모바일 검색 시트 — Task 2 Step 5 의 코드 그대로 (body.search-open · mode: 'back' | 'pop' | 'select') */
const isNarrow=()=>matchMedia('(max-width:940px)').matches;
function openSearchSheet(){ if(!isNarrow()||document.body.classList.contains('search-open')) return;
  document.body.classList.add('search-open'); document.body.style.overflow='hidden'; try{history.pushState({fuSearch:1},'');}catch(e){} }
function closeSearchSheet(mode){ if(!document.body.classList.contains('search-open')) return;
  document.body.classList.remove('search-open'); document.body.style.overflow=''; $('#searchPanel').classList.remove('open'); $('#q').blur();
  const marked = history.state && history.state.fuSearch;
  try{ if(mode==='back' && marked) history.back(); else if(mode==='select' && marked) history.replaceState(null,'',location.href); }catch(e){} }
$('#q').addEventListener('focus',openSearchSheet);
$('#qClose').addEventListener('click',()=>closeSearchSheet('back'));
window.addEventListener('popstate',()=>closeSearchSheet('pop'));
```
(`data-stock` 버튼 클릭은 `31_nav.js` 의 전역 핸들러가 처리한다 — Task 4 에서 상세 뷰로 연결된다.)

- [ ] **Step 3: CSS** — `</style>` 직전:
```css
.sp-head2{margin-top:-4px;}
.sp-src,.sp-period{font-size:11px;padding:3px 9px;border-radius:999px;border:1px solid var(--border);color:var(--text-3);cursor:pointer;margin-right:4px;}
.sp-src.on,.sp-period.on{border-color:var(--gold);color:var(--gold);background:var(--gold-bg);}
.sr-pin{display:flex;align-items:center;gap:10px;padding:10px 12px;margin:6px 0;border:1px solid var(--gold-border);background:var(--gold-bg);border-radius:10px;cursor:pointer;font-size:13px;}
.sr-pin .sr-go{margin-left:auto;color:var(--gold);font-weight:700;}
.sp-recent{padding:8px 4px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;}
.sp-recent-l{font-size:11px;color:var(--text-4);margin-right:4px;}
a.sr{text-decoration:none;color:inherit;display:block;}
```

- [ ] **Step 4: 렌더·스모크 루틴** → PASS (aliases 없는 로컬 데이터면 alias 테스트는 skip — Track A 머지 후 재확인).

- [ ] **Step 5: 커밋**
```bash
git add hub/30_search.js hub_template.html tests/e2e/test_hub_features.py
git commit -m "feat(search): 검색 2.0 — 출처/기간 필터, 별칭 확장, 종목 핀 카드, 최근 검색어, 채팅 결과 라우팅"
```

---

## Task 4: 종목 상세 뷰 `#stock/<이름>` (F2)

**Files:** `hub/27_stock_detail.js`(신규), `hub/10_tabs.js`, `hub/31_nav.js`, `hub/50_graph.js`, `hub/23_verify.js`, `hub_template.html`, `tests/e2e/test_hub_features.py`

- [ ] **Step 1: 스모크 (RED)**

```python
def test_stock_detail_route(page, site_url):
    _boot(page, site_url)
    first = page.evaluate("window.DATA.stocks[0].name")
    page.goto(site_url + "hub.html#stock/" + first)
    page.wait_for_selector("#view-stock.active .sd-head", timeout=15000)
    assert first in page.inner_text("#view-stock .sd-head")
    assert page.locator("#view-stock .sd-mentions .mention").count() >= 1


def test_stock_chip_opens_detail(page, site_url):
    _boot(page, site_url)
    page.click("#view-home [data-stock] >> nth=0")
    page.wait_for_selector("#view-stock.active .sd-head", timeout=15000)
    assert page.evaluate("location.hash").startswith("#stock/")


def test_mobile_search_select_keeps_stock_detail(page, site_url):
    """모바일 검색 시트에서 종목 핀을 선택하면 history.back() 없이 상세 뷰가 유지돼야 한다."""
    page.set_viewport_size({"width": 375, "height": 812})
    _boot(page, site_url)
    first = page.evaluate("window.DATA.stocks[0].name")
    page.click("#q"); page.fill("#q", first)
    page.wait_for_selector("#searchPanel.open .sr-pin", timeout=15000)
    page.click("#searchPanel .sr-pin")
    page.wait_for_timeout(400)
    assert page.locator("#view-stock.active .sd-head").count() == 1
    assert page.evaluate("location.hash").startswith("#stock/")
    assert page.evaluate("document.body.classList.contains('search-open')") is False
```

- [ ] **Step 2: 템플릿** — `<div class="view" id="view-chat"></div>` 아래에 `<div class="view" id="view-stock"></div>`. CSS(`</style>` 직전):

```css
/* ── 종목 상세 ── */
.sd-back{display:inline-block;margin-bottom:10px;font-size:12.5px;color:var(--text-3);cursor:pointer;}
.sd-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px;}
.sd-name{font-family:'Playfair Display','Noto Serif KR',serif;font-size:28px;font-weight:700;}
.sd-reason{font-size:13px;color:var(--text-2);margin:4px 0 12px;padding:8px 12px;border-left:3px solid var(--gold);background:var(--gold-bg);border-radius:0 8px 8px 0;}
.sd-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:14px;}
@media(max-width:880px){.sd-grid{grid-template-columns:1fr;}}
.sd-chart{width:100%;height:180px;display:block;}
.sd-legend{font-size:11px;color:var(--text-4);margin-top:4px;display:flex;gap:12px;flex-wrap:wrap;}
.sd-legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:-1px;}
.sd-act{margin-left:auto;display:flex;gap:6px;}
.sd-act button{font-size:12px;padding:5px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface);cursor:pointer;}
```

- [ ] **Step 3: `hub/27_stock_detail.js`**

```js
/* ───────── STOCK DETAIL (#stock/<이름>) ───────── */
let sdName='';
function openStock(name){
  if(!STOCK_BY_NAME[name]) { showTab('stocks'); stockQuery=name; renderStocks(); return; }
  sdName=name;
  showTab('stock', true);
  renderStockDetail(name);
  try{history.replaceState(null,'','#stock/'+encodeURIComponent(name));}catch(e){}
  window.scrollTo({top:0,behavior:'smooth'});
}
function sdSeries(name){                       // 주가 시계열: 채팅 코호트 → 리포트 코호트 순 (C4, 없으면 null)
  const a=VMAP[name]; if(a&&a.series&&a.series.length>1) return a.series;
  const r=(D.verify&&D.verify.report&&D.verify.report.stocks||[]).find(s=>s.name===name);
  return (r&&r.series&&r.series.length>1) ? r.series : null;
}
function sdCalls(name){
  const core=((D.verify&&D.verify.calls)||[]).filter(c=>c.stock===name).map(c=>({...c,cohort:'채팅'}));
  const rep=((D.verify&&D.verify.report&&D.verify.report.calls)||[]).filter(c=>c.stock===name).map(c=>({...c,cohort:'리포트'}));
  return core.concat(rep);
}
function drawPriceOverlay(cv, series, mentionDates, calls){
  const ctx=cv.getContext('2d'), dpr=window.devicePixelRatio||1;
  const W=cv.clientWidth||600, H=cv.clientHeight||180; cv.width=W*dpr; cv.height=H*dpr; ctx.scale(dpr,dpr);
  const cs=getComputedStyle(document.documentElement);
  const gold=cs.getPropertyValue('--gold').trim()||'#9a7508', grid=cs.getPropertyValue('--grid').trim()||'#ece6d7', tx=cs.getPropertyValue('--text-4').trim()||'#aaa';
  const pad={l:44,r:10,t:10,b:20};
  const xs=series.map(p=>dnum(p[0])), ys=series.map(p=>p[1]);
  const x0=Math.min(...xs), x1=Math.max(...xs), y0=Math.min(...ys), y1=Math.max(...ys);
  const X=d=>pad.l+(d-x0)/Math.max(1,x1-x0)*(W-pad.l-pad.r), Y=v=>pad.t+(1-(v-y0)/Math.max(1e-9,y1-y0))*(H-pad.t-pad.b);
  ctx.clearRect(0,0,W,H);
  ctx.strokeStyle=grid; ctx.lineWidth=1; ctx.font='10px JetBrains Mono, monospace'; ctx.fillStyle=tx; ctx.textAlign='right';
  [y0,(y0+y1)/2,y1].forEach(v=>{ const y=Y(v); ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke(); ctx.fillText(v>=1000?Math.round(v).toLocaleString():v.toFixed(1), pad.l-4, y+3); });
  ctx.beginPath(); series.forEach((p,i)=>{ const x=X(xs[i]), y=Y(p[1]); i?ctx.lineTo(x,y):ctx.moveTo(x,y); });
  ctx.strokeStyle='#2f5fd0'; ctx.lineWidth=1.8; ctx.lineJoin='round'; ctx.stroke();
  const yAt=d=>{ let best=null; for(let i=0;i<xs.length;i++){ if(xs[i]<=d) best=i; } return best==null?null:Y(ys[best]); };
  (mentionDates||[]).forEach(d=>{ const dd=dnum(d); if(dd==null||dd<x0||dd>x1) return; const y=yAt(dd); if(y==null) return;
    ctx.beginPath(); ctx.arc(X(dd),y,3.2,0,7); ctx.fillStyle=gold; ctx.fill(); });
  (calls||[]).forEach(c=>{ const dd=dnum(c.date); if(dd==null||dd<x0||dd>x1) return; const y=yAt(dd); if(y==null) return;
    ctx.beginPath(); ctx.moveTo(X(dd),y-9); ctx.lineTo(X(dd)-5,y-2); ctx.lineTo(X(dd)+5,y-2); ctx.closePath();
    ctx.fillStyle=c.stance==='bearish'?'#c2402f':'#247a3d'; ctx.fill(); });
  ctx.textAlign='center'; ctx.fillStyle=tx;
  [x0,x1].forEach(d=>ctx.fillText(fmtDate(new Date(d*864e5).toISOString().slice(0,10)), X(d), H-6));
}
function sdCallRows(name){
  const key='h'+PRIMARY_H;
  const cs=sdCalls(name).sort((a,b)=>a.date<b.date?1:a.date>b.date?-1:0);
  if(!cs.length) return '<div class="v-mini">검증 대상 콜이 없습니다.</div>';
  return cs.map(c=>{ const r=c[key];
    const badge = c.conflict ? '<span class="v-badge conf">의견 갈림</span>'
      : (c.error==='no_price'||c.error==='bad_entry') ? '<span class="v-badge pend">가격 없음</span>'
      : !r ? '<span class="v-badge pend">판정 대기</span>'
      : `<span class="v-badge ${r.hit?'hit':'miss'}">${vPct(r.excess!=null?r.excess:r.ret)}</span>`;
    const src=(c.sources||[])[0]||{};
    return `<div class="mention"><span class="md">${esc(fmtDate(c.date))}</span><span class="pill">${esc(c.cohort)}</span>
      <span class="v-dir ${esc(c.stance)}">${c.stance==='bullish'?'강세':'약세'}</span> ${badge}
      <span style="color:var(--text-3)">${esc(src.sharer||'')}</span> ${esc(src.snippet||'')} ${src.id?srcLink(src.id):''}</div>`; }).join('');
}
function sdNeighbors(name){
  const co=((D.chat&&D.chat.co_edges)||[]).filter(e=>e.a===name||e.b===name).sort((a,b)=>b.w-a.w).slice(0,6)
    .map(e=>{ const o=e.a===name?e.b:e.a; return `<span class="tag" data-stock="${esc(o)}">${esc(o)} <span style="color:var(--text-4)">${e.w}</span></span>`; }).join('');
  return co?`<div style="margin:10px 0 4px;font-size:11.5px;color:var(--text-3)">💬 채팅에서 함께 언급</div><div>${co}</div>`:'';
}
function renderStockDetail(name){
  const s=STOCK_BY_NAME[name]; const host=$('#view-stock'); if(!s||!host) return;
  const reason=(D.ai_digest&&D.ai_digest.stock_reasons&&D.ai_digest.stock_reasons[name])||null;   // C6
  const themes=(s.themes||[]).map(t=>`<span class="pill theme" data-go="sectors" data-sector="${esc(t)}">${esc(t)}</span>`).join('');
  const tags=(s.supply_tags||[]).map(t=>`<span class="pill supply">${esc(t)}</span>`).join('');
  const series=sdSeries(name);
  const allM=(s.mentions||[]).slice().reverse();
  host.innerHTML=`
    <span class="sd-back" data-go="stocks">← 종목 목록</span>
    <div class="sd-head">
      <button class="star ${isWatched('stock',name)?'on':''}" data-watch="stock:${esc(name)}" onclick="toggleWatchEl(this)">${isWatched('stock',name)?'★':'☆'}</button>
      <span class="sd-name">${esc(name)}</span>${momentumChip(s)}<span class="count-badge">${s.count||0}회</span>${verifyChip(name)}
      <span class="sd-act"><button type="button" class="cmp-add ${isComparePicked(name)?'on':''}" data-cmp="${esc(name)}">${isComparePicked(name)?'비교중':'비교'}</button>
        <button type="button" id="sdCopy">링크 복사</button></span>
    </div>
    <div>${themes}${tags}${s.chat?`<span class="pill" style="background:#f5f3ff;color:#7c3aed">💬 ${s.chat.count}</span>`:''}</div>
    ${reason?`<div class="sd-reason">🤖 ${esc(reason.text)} <span style="color:var(--text-4);font-size:11px">· ${esc(fmtDate(reason.as_of))} 기준 AI 요약</span></div>`:''}
    <div class="sd-grid">
      <div class="card">
        <div class="sec-title" style="margin:0 0 4px;font-size:16px">${series?'📉 주가와 언급 시점':'📈 주별 언급 빈도'}</div>
        <canvas class="sd-chart" id="sdChart"></canvas>
        <div class="sd-legend">${series?'<span><i style="background:#2f5fd0"></i>종가(주 단위)</span><span><i style="background:var(--gold)"></i>리포트 언급</span><span><i style="background:#247a3d"></i>강세 콜</span><span><i style="background:#c2402f"></i>약세 콜</span>':'<span><i style="background:var(--gold)"></i>리포트 언급 수 / 주</span>'}</div>
        ${relatedChips(name)}${sdNeighbors(name)}
      </div>
      <div class="card">
        <div class="sec-title" style="margin:0 0 4px;font-size:16px">✅ 콜 검증 <span class="v-mini">${PRIMARY_H}거래일 · 지수 대비</span></div>
        <div class="sd-calls">${sdCallRows(name)}</div>
      </div>
    </div>
    <div class="card"><div class="sec-title" style="margin:0 0 4px;font-size:16px">🗂 언급 타임라인 <span class="count-badge">${allM.length}</span></div>
      <div class="sd-mentions">${allM.map(stMentionHtml).join('')||'<div class="empty">리포트 언급 없음</div>'}</div></div>
    ${s.chat?`<div class="card">${renderChat(s)}</div>`:''}`;
  const cv=$('#sdChart');
  if(series) drawPriceOverlay(cv, series, (s.mentions||[]).map(m=>m.date), sdCalls(name));
  else { cv.width=cv.clientWidth||600; cv.height=180; drawSpark(cv, weeklyCounts(s.mentions)); }
  $('#sdCopy').addEventListener('click',()=>{ const url=location.origin+location.pathname+'#stock/'+encodeURIComponent(name);
    (navigator.clipboard?navigator.clipboard.writeText(url):Promise.reject()).then(()=>{$('#sdCopy').textContent='복사됨';setTimeout(()=>$('#sdCopy').textContent='링크 복사',1500);}).catch(()=>prompt('링크',url)); });
}
```

- [ ] **Step 4: 라우팅** — `hub/10_tabs.js`: `TABS` 에 `'stock'` 추가. `tabFromHash` 의 `showTab(t,true);` **앞**에(인자 없는 `#stock` 은 목록으로 보낸다):
```js
  if(t==='stock'){ if(arg) openStock(arg); else showTab('stocks',true); return; }
```
(`showTab('stock', true)` 는 사이드바에 해당 버튼이 없어 active 표시만 모두 해제된다 — 의도.)
`VIEW_RENDERERS` 에는 넣지 않는다(openStock 이 직접 렌더).

- [ ] **Step 5: `hub/31_nav.js`** — `data-stock` 전역 핸들러의 본문을 상세 뷰로:
```js
  const stockTag=e.target.closest('[data-stock]');
  if(stockTag){ openStock(stockTag.dataset.stock); return; }
```
(종목 탭의 필터 입력은 그대로 남는다. `hub/50_graph.js` 의 `gNavigate` 도 `if(p.kind==='stock'){ openStock(p.name); }` 로 바꾼다.)

- [ ] **Step 6: `hub/23_verify.js`** — `vCallRows(name)` 시그니처를 `vCallRows(name, calls)` 로, 첫 줄을 `const cs=((calls||D.verify.calls)||[]).filter(...)` 로 (Task 6 에서 코호트 토글이 쓴다).

- [ ] **Step 7: 렌더·스모크 루틴** → PASS. 기존 `test_stock_deep_link_opens_detail`(`#stocks/이름`)도 그대로 PASS 해야 한다.

- [ ] **Step 8: 커밋**
```bash
git add hub/27_stock_detail.js hub/10_tabs.js hub/31_nav.js hub/23_verify.js hub/50_graph.js hub_template.html tests/e2e/test_hub_features.py
git commit -m "feat(hub): 종목 상세 뷰 #stock/<이름> — 주가·언급 오버레이, 콜 검증(두 코호트), 채팅 근거, 관계 이웃, 링크 복사"
```

---

## Task 5: 홈 "오늘 달라진 것" · AI 데일리 3줄 · 종목 이유 · neutral 뉴스 (F4/F5 UI)

**Files:** `hub/20_home.js`, `hub/22_stocks.js`, `hub/25_chat.js`, `hub_template.html`(CSS), `tests/e2e/test_hub_features.py`

- [ ] **Step 1: 스모크 (RED)** — 데이터가 없으면 카드가 **없어야** 하고, 있으면 있어야 한다:

```python
def test_whats_new_card_matches_data(page, site_url):
    _boot(page, site_url)
    # diff 객체는 있어도 다섯 배열이 전부 빈 날이 있다 → '내용이 있을 때만' 카드
    has = page.evaluate("(w=>!!w && ['new_stocks','surging','new_calls','new_targets','new_reports'].some(k=>(w[k]||[]).length))(window.DATA.whats_new)")
    assert page.locator("#whatsNew").count() == (1 if has else 0)
    if has:
        assert page.locator("#whatsNew [data-stock], #whatsNew [data-go], #whatsNew [data-report]").count() >= 1


def test_ai_daily_lines_when_present(page, site_url):
    _boot(page, site_url)
    has = page.evaluate("!!(window.DATA.ai_digest && window.DATA.ai_digest.daily && (window.DATA.ai_digest.daily.lines||[]).length)")
    assert page.locator(".brf-ai").count() == (1 if has else 0)
```

- [ ] **Step 2: `hub/20_home.js`**

`renderHome` 의 `${aiDigestCard()}` 앞에 `${whatsNewCard()}` 를 넣고, 브리핑 카드 `brf-points` 블록 뒤(`</div></div>` 직전)에:
```js
      ${aiDailyLines()}
```
함수 추가(`aiDigestCard` 위):
```js
/* ── 오늘 달라진 것 (C5) — 데이터 없으면 카드 없음 ── */
function whatsNewCard(){
  const w=D.whats_new; if(!w) return '';
  const rows=[];
  if((w.new_stocks||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">신규 등장</span>${w.new_stocks.slice(0,8).map(x=>`<span class="chip" data-stock="${esc(x.name)}">${esc(x.name)} <span class="n">${x.count}</span></span>`).join('')}</div>`);
  if((w.surging||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">언급 급증</span>${w.surging.slice(0,6).map(x=>`<span class="chip" data-stock="${esc(x.name)}">${esc(x.name)} <span class="n">${x.prev}→${x.recent}</span></span>`).join('')}</div>`);
  if((w.new_calls||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">새 콜</span><span class="chip" data-go="verify">${w.new_calls.length}건 · 검증 탭 →</span>${w.new_calls.slice(0,4).map(c=>`<span class="chip" data-stock="${esc(c.stock)}">${esc(c.stock)} <span class="n">${c.stance==='bullish'?'강세':'약세'}</span></span>`).join('')}</div>`);
  if((w.new_targets||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">새 목표가</span>${w.new_targets.slice(0,6).map(t=>`<span class="chip" data-stock="${esc(t.stock)}">${esc(t.stock)} <span class="n">${esc(t.value)}${esc(t.unit||'')}</span></span>`).join('')}</div>`);
  if((w.new_reports||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">새 리포트</span>${w.new_reports.slice(0,4).map(id=>`<span class="chip" data-report="${esc(id)}">${esc(fmtDate(id))}</span>`).join('')}</div>`);
  if(!rows.length) return '';
  return `<div class="card" id="whatsNew" style="border-color:var(--gold-border)">
    <div class="sec-title" style="margin:0 0 4px;font-size:17px">🆕 오늘 달라진 것</div>
    <div class="sec-sub">${esc(fmtDate(w.since))} 빌드 이후 변화 · <a class="src" href="feed.json">feed.json↗</a></div>${rows.join('')}</div>`;
}
function aiDailyLines(){
  const d=D.ai_digest&&D.ai_digest.daily; if(!d||!(d.lines||[]).length) return '';
  return `<div class="brf-ai"><span class="brf-ai-k">🤖 AI 3줄</span>${d.lines.slice(0,3).map(l=>`<div>${esc(l)}</div>`).join('')}</div>`;
}
```
CSS:
```css
.wn-row{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px;margin-top:8px;}
.wn-k{font-size:11px;color:var(--text-3);min-width:64px;font-weight:600;}
.brf-ai{margin-top:12px;font-size:13px;color:var(--text-2);border-top:1px dashed var(--border);padding-top:10px;}
.brf-ai-k{font-size:11px;color:var(--gold);font-weight:700;display:block;margin-bottom:4px;}
.news-neutral{opacity:.5;}
```

- [ ] **Step 3: `hub/22_stocks.js`** — `stockRow` 의 `<span class="strow-name">${esc(s.name)}</span>` 뒤에 AI 이유 부제:
```js
      ${(D.ai_digest&&D.ai_digest.stock_reasons&&D.ai_digest.stock_reasons[s.name])?`<span class="strow-sub" title="AI 요약">${esc(D.ai_digest.stock_reasons[s.name].text)}</span>`:''}
```
CSS `.strow-sub{font-size:11px;color:var(--text-3);flex-basis:100%;order:9;}`. `chatNewsRow` 의 `<div class="mention">` → `<div class="mention${n.neutral?' news-neutral':''}">`. `hub/25_chat.js` `cgNewsRow` 도 같은 클래스.

- [ ] **Step 4: 렌더·스모크 루틴** → PASS. 커밋:
```bash
git add hub/20_home.js hub/22_stocks.js hub/25_chat.js hub_template.html tests/e2e/test_hub_features.py
git commit -m "feat(home): 오늘 달라진 것 카드(whats_new)·AI 데일리 3줄·종목 행 AI 이유·neutral 뉴스 흐리게 (데이터 없으면 숨김)"
```

---

## Task 6: 검증 탭 — 코호트 토글 · 테마 표 · 초과수익 분포 (F3 UI)

**Files:** `hub/23_verify.js`, `hub_template.html`(CSS), `tests/e2e/test_hub_features.py`

- [ ] **Step 1: 스모크 (RED)**

```python
def test_verify_cohort_toggle_and_histogram(page, site_url):
    _boot(page, site_url)
    if not page.evaluate("!!(window.DATA.verify && window.DATA.verify.enabled)"):
        pytest.skip("verify 비활성")
    page.goto(site_url + "hub.html#verify")
    page.wait_for_selector("#view-verify .v-score", timeout=15000)
    assert page.locator("#vHist").count() == 1
    has_rep = page.evaluate("!!(window.DATA.verify.report && window.DATA.verify.report.enabled)")
    assert page.locator("#vCohort").count() == (1 if has_rep else 0)
    if has_rep:
        page.click('#vCohort button[data-cohort="report"]')
        page.wait_for_selector("#vThemes", timeout=5000)
        if page.evaluate("(window.DATA.verify.themes||[]).length"):
            assert page.locator("#vThemes .v-row").count() >= 1
        assert "리포트" in page.inner_text("#view-verify .sec-sub")
```

- [ ] **Step 2: `hub/23_verify.js`** — 상단 상태에 `let vCohort='core';` 추가. `renderVerify` 를:

```js
function vData(){ return (vCohort==='report' && D.verify && D.verify.report && D.verify.report.enabled) ? D.verify.report : D.verify; }
function renderVerify(){
  const host=$('#view-verify'); if(!host) return;
  syncVerifyTab();
  if(!verifyOn()){ host.innerHTML=''; return; }
  const hasRep=!!(D.verify.report&&D.verify.report.enabled);
  if(!hasRep) vCohort='core';
  const V=vData(), m=V.meta||{}, key='h'+vHorizon, s=(V.summary||{})[key]||{};
  const toggle=(m.horizons||[5,20,60]).map(h=>`<button data-vh="${h}" class="${h===vHorizon?'on':''}">${h}일</button>`).join('');
  const cohortUi=hasRep?`<div class="seg" id="vCohort"><button data-cohort="core" class="${vCohort==='core'?'on':''}">채팅 콜</button><button data-cohort="report" class="${vCohort==='report'?'on':''}">리포트 수급 포착</button></div>`:'';
  const warn=(s.pending||0)>(s.judged||0)?' vh-warn':'';
  const sub = vCohort==='report'
    ? '리포트의 기관·외국인 순매수 포착을 강세 콜로 보고, 발표 다음 거래일 종가 진입 · 거래일 기준 구간 · 지수 대비 초과수익으로 대조했다 (채팅 콜과 합산하지 않음)'
    : '채팅에서 방향을 밝힌 발화를 이후 실제 주가와 대조했다 — 발화 다음 거래일 종가 진입 · 거래일 기준 구간 · 지수 대비 초과수익';
  host.innerHTML=`
    <div class="sec-title">✅ 콜 검증 <span class="count-badge">${m.calls||0}</span></div>
    <div class="sec-sub">${sub}</div>
    <div class="v-controls">${cohortUi}<div class="v-toggle" id="vHorizon">${toggle}</div></div>
    <div class="v-score">
      <div class="v-cell"><div class="v-num">${s.hit_rate==null?'—':s.hit_rate.toFixed(1)+'%'}</div><div class="v-lbl">적중률 (${s.hit||0}/${s.judged||0})</div></div>
      <div class="v-cell"><div class="v-num">${vPct(s.avg_excess)}</div><div class="v-lbl">평균 초과수익</div></div>
      <div class="v-cell${warn}"><div class="v-num">${s.pending||0}</div><div class="v-lbl">판정 대기</div></div>
      <div class="v-cell"><div class="v-num">${s.bullish||0} · ${s.bearish||0}</div><div class="v-lbl">강세 · 약세</div></div>
    </div>
    ${vCohort==='core'?`<div class="v-note">강세 ${s.bullish||0}건 대 약세 ${s.bearish||0}건으로 강세 편향이 크다 — 사실상 강세 의견의 초과수익 검증이다. 표본이 얇은 종목은 아래로 내렸다. 투자 권유가 아니다.</div>`
      :`<div class="v-note">수급 포착은 전부 강세로 본다. 포착 = 리포트 발행일 기준이며 실제 순매수일보다 하루 늦을 수 있다. 투자 권유가 아니다.</div>`}
    <div class="card"><div class="sec-title" style="margin:0 0 4px;font-size:16px">📊 ${vHorizon}거래일 초과수익 분포</div><canvas id="vHist" class="sd-chart" style="height:150px"></canvas></div>
    ${vCohort==='report'?'<div class="sec-title" style="font-size:16px">🧩 테마별</div><div id="vThemes"></div>':''}
    <div id="vRank"></div>`;
  $('#vHorizon').addEventListener('click',e=>{const b=e.target.closest('button'); if(b){vHorizon=+b.dataset.vh;renderVerify();}});
  const vc=$('#vCohort'); if(vc) vc.addEventListener('click',e=>{const b=e.target.closest('button'); if(b){vCohort=b.dataset.cohort;renderVerify();}});
  drawHistogram($('#vHist'), (V.calls||[]).filter(c=>!c.conflict&&c[key]&&c[key].excess!=null).map(c=>c[key].excess));
  if(vCohort==='report') drawThemes();
  drawVerifyRank();
}
function drawHistogram(cv, values){
  if(!cv) return; const dpr=window.devicePixelRatio||1; const W=cv.clientWidth||600, H=150; cv.width=W*dpr; cv.height=H*dpr;
  const ctx=cv.getContext('2d'); ctx.scale(dpr,dpr); ctx.clearRect(0,0,W,H);
  const cs=getComputedStyle(document.documentElement), tx=cs.getPropertyValue('--text-4').trim()||'#aaa';
  if(!values.length){ ctx.fillStyle=tx; ctx.font='12px Noto Sans KR'; ctx.fillText('판정된 콜이 아직 없습니다', 12, 24); return; }
  const BIN=5, lo=Math.floor(Math.min(-10,...values)/BIN)*BIN, hi=Math.ceil(Math.max(10,...values)/BIN)*BIN;
  const n=(hi-lo)/BIN, bins=new Array(n).fill(0);
  values.forEach(v=>{ let i=Math.floor((v-lo)/BIN); if(i>=n)i=n-1; if(i<0)i=0; bins[i]++; });
  const max=Math.max(1,...bins), pad={l:8,r:8,t:10,b:22}, bw=(W-pad.l-pad.r)/n;
  bins.forEach((c,i)=>{ const x=pad.l+i*bw, h=(c/max)*(H-pad.t-pad.b), from=lo+i*BIN;
    ctx.fillStyle= from>=0 ? '#247a3d' : '#c2402f'; ctx.globalAlpha=.75; ctx.fillRect(x+1, H-pad.b-h, bw-2, h); ctx.globalAlpha=1;
    if(c){ ctx.fillStyle=tx; ctx.font='10px JetBrains Mono'; ctx.textAlign='center'; ctx.fillText(c, x+bw/2, H-pad.b-h-3); } });
  ctx.fillStyle=tx; ctx.font='10px JetBrains Mono'; ctx.textAlign='center';
  for(let i=0;i<=n;i+=Math.max(1,Math.round(n/8))) ctx.fillText((lo+i*BIN)+'%p', pad.l+i*bw, H-6);
}
function drawThemes(){
  const key='h'+vHorizon, rows=(D.verify.themes||[]);
  $('#vThemes').innerHTML = rows.length ? rows.map(t=>{ const h=t[key]||{};
    return `<div class="v-row"><div class="v-row-head" data-go="sectors" data-sector="${esc(t.theme)}"><span class="v-name">${esc(t.theme)}</span>
      <span class="v-mini">${t.calls}콜</span><span class="v-mini">${h.judged?`${h.hit}/${h.judged}`:'판정 전'}</span>
      <span class="v-hr">${h.hit_rate==null?'—':h.hit_rate.toFixed(0)+'%'}</span><span class="v-ex">${vPct(h.median_excess!=null?h.median_excess:h.avg_excess)}</span></div></div>`; }).join('')
    : '<div class="v-mini">테마 집계 없음</div>';
}
```
`drawVerifyRank` 의 `all=(D.verify.stocks||[])` → `all=(vData().stocks||[])`, 행 펼침에서 `vCallRows(h.dataset.vstock)` → `vCallRows(h.dataset.vstock, vData().calls)`. `vRankRows`·`verifyChip`·`VMAP` 은 채팅 코호트 기준 그대로.

CSS: `.v-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0 12px;}`.

- [ ] **Step 3: 렌더·스모크 루틴** → PASS (report 코호트 없는 로컬 데이터면 토글 없음 분기로 통과). 커밋:
```bash
git add hub/23_verify.js hub_template.html tests/e2e/test_hub_features.py
git commit -m "feat(verify): 코호트 토글(채팅 콜/리포트 수급), 테마별 표, 초과수익 분포 히스토그램(canvas)"
```

---

## Task 7: 문서 + PR

- [ ] README "테스트" 절에 `tests/e2e/test_hub_features.py` 언급, "주의" 절에 `#stock/<이름>` 딥링크·`vendor/` 설명 추가.
- [ ] 전량: `VERIFY_SKIP=1 python -m pytest tests/ -q` + 렌더·스모크 루틴 + 모바일 뷰포트 스크린샷 2장(홈·종목 상세) 을 PR 에 첨부.
- [ ] PR 제목 "허브 UI 확장: 검색 2.0·종목 상세·모바일 내비·검증 코호트·What's new". Track A 가 먼저 머지됐다면 `knowledge_base.json` 을 다시 collect 해 alias/whats_new/report 코호트 스모크가 skip 없이 도는지 확인하고 결과를 본문에 적는다.

## 범위 밖

- 검색 Web Worker(항목 7천 건에서 디바운스로 충분한지 `build/e2e_timing.json` 으로 먼저 본다) · OG 메타(정적 셸이라 종목별 불가) · Chart.js 완전 제거 · 폰트 self-host
