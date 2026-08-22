# 지식허브 개선 (성능·기능·품질) 설계 스펙

**날짜:** 2026-08-23
**상태:** 승인 (사용자: Phase 1·2·3 동시 진행, F7 익명화 제외 · 발언자 실명 표기 유지)
**근거 진단:** 2026-08-23 실측 — kb.<hash>.json 9.2MB(gzip 2.7MB) 단일 fetch, 9탭 전량 렌더 460ms, DOM 17,655·canvas 213, JS 힙 47MB, `reports` 2.5MB 미사용 전송, Chart.js·Fonts CSS 렌더 블로킹, 전역 검색에 채팅 미포함.

## 1. 목표

1. **첫 화면 비용을 첫 화면에 필요한 만큼으로** — 코어 데이터만 받고 활성 탭만 그린다.
2. **매일 올 이유** — 오늘 달라진 것, 채팅까지 닿는 검색, 공유 가능한 종목 상세.
3. **회귀 안전망** — 셸 JS 스모크 테스트와 kb 크기 예산을 CI 게이트로.

## 2. 범위

| ID | 항목 | 트랙 |
|---|---|---|
| Q2 | Playwright 스모크 테스트 (셸 JS 회귀 안전망) | 기반 |
| Q3 | 셸 JS를 `hub/*.js` 로 분리, `render.py` 가 빌드타임 concat | 기반 |
| P3 | 활성 탭만 렌더 · 스파크라인 IntersectionObserver | 기반 |
| P2 | `reports` 를 UI 사용 필드로 투영 | 기반 |
| P1 | 코어 + 청크(chat·search·glossary·stockchat) 분할 로딩 · SW v4 | 기반 |
| P6 | `version.json` 기반 "새 데이터 준비됨" 토스트 | 기반 |
| Q4 | `safeHref` (http/https 만) · merge 단계 URL 필터 | 기반 |
| F1 | 통합 검색 2.0 — 채팅뉴스·채팅의견·목표가 인덱스, 별칭, 기간/출처 필터, 최근 검색어 | A(인덱스) + B(UI) |
| F3 | 검증 확장 — 리포트 수급 코호트 · 테마 집계 · 주가 시계열 · 분포 히스토그램 | A + B |
| F4 | What's new diff + `feed.json` + 홈 카드 | A + B |
| F5 | AI 증분 요약 — 데일리 3줄 · 종목 언급 이유 · 뉴스 neutral 플래그 (캐시) | A + B |
| Q1 | kb 크기 예산 · 최소 스키마 검증 · Job Summary | A |
| F2 | 종목 상세 뷰 `#stock/<이름>` | B |
| F6 | 모바일 하단 탭 5개 + 더보기 · 검색 시트 | B |
| P4 | Chart.js vendoring + defer + SW 프리캐시 · 폰트 웨이트 축소 | B |
| P5 | 검색 디바운스 + 사전 토큰화(`hay`) | A(`hay`) + B(디바운스) |

**범위 밖:** F7 익명화(사용자 결정으로 제외 — `sharer` 실명 유지), 발화자 랭킹(README 정책), Web Worker 검색(측정 후 판단), 폰트 self-host, Chart.js 완전 제거.

## 3. 아키텍처

### 3.1 빌드 (변경 후)

```
collect  : parse → aggregate → momentum → search(report) → chat merge(+chat search) → verify(core+report) → whats_new → schema 검증 → knowledge_base.json
ai_digest: knowledge_base.json → (캐시 증분) → ai_digest.json {digest, daily, stock_reasons, news_flags}
render   : knowledge_base.json + ai_digest.json → split → kb.core.<h>.json + kb.{chat,search,glossary,stockchat}.<h>.json
           + hub.html(셸: hub/*.js concat 주입, KBURL 매니페스트) + version.json + feed.json + build/report.md
```

`knowledge_base.json` 은 **전체 데이터(schema 2) 그대로** 유지한다. 분할·슬림화는 render 의 출력(kb.*)에만 적용한다.

### 3.2 셸 (변경 후)

- `hub_template.html` 은 HTML/CSS + `<script type="fu-app">/*APPJS*//*ENDAPPJS*/</script>` 마커만 가진다. `render.py` 가 `hub/*.js` 를 **파일명 사전순으로 concat** 해 마커 사이에 넣는다(런타임 동작은 현재와 동일: 단일 블록, 데이터 로딩 후 실행). ES 모듈로 바꾸지 않는 이유: 106개 함수가 공유하는 최상위 `let` 상태(`stockQuery` 등)를 전부 export/import 로 바꾸는 건 이번 범위의 위험 대비 이득이 없다. 파일 분리만으로 병렬 작업·파일 크기 규칙을 충족한다.
- 부트: `kb.core` 만 기다린 뒤 앱 블록 실행 → 홈만 렌더. 나머지 탭은 `showTab` 첫 진입 시 렌더(`RENDERED` Set). 청크는 필요 시점에 `loadChunk(name)` (메모이즈 Promise).
- 스파크라인: `IntersectionObserver` 로 보이는 행만 그린다.

### 3.3 데이터 계약 (트랙 간 인터페이스 — 변경 시 이 문서 갱신)

**C1. KBURL 매니페스트** (`hub_template.html` 마커, render 가 치환)
```js
window.KB_URL = /*KBURL*/{"core":"kb.core.<h>.json","chat":"kb.chat.<h>.json","search":"kb.search.<h>.json","glossary":"kb.glossary.<h>.json","stockchat":"kb.stockchat.<h>.json"}/*ENDKBURL*/;
```
문자열이면(구 셸) `{core: 문자열}` 로 해석한다. 해시는 청크별 자기 payload 의 sha1[:10] — 안 바뀐 청크는 파일명이 유지돼 SW 캐시가 재사용된다.

**C2. 코어/청크 내용**
- `core` = knowledge_base 에서 `search`·`glossary` 제거, `chat` → `{build, themes, co_edges, counts:{actions,strategy,targets,qna,news,readings,glossary}}`, `reports[]` → `{type,date,id,sort_date,file,headline,subhead}`, `stocks[].chat` → `{count,signals,stance,targets,opinions:[:3],news:[:4],market_news:[],opinions_n,news_n,market_news_n}`, `build.counts={glossary,search}`.
- `chat` 청크 = knowledge_base.chat 전체. `search` = 검색 인덱스 배열. `glossary` = 용어 배열. `stockchat` = `{"<종목명>": 전체 chat 블록}`.
- `version.json` = `{"core":"kb.core.<h>.json","generated":"YYYY-MM-DD HH:MM"}` — SW 를 우회(`?nosw=`)해 읽는다.

**C3. 검색 인덱스 항목** (`search[]`)
```json
{"kind":"채팅뉴스|채팅의견|목표가|타임라인|…","title":"","snippet":"","date":"","id":"","tags":[],"extra":{},
 "source":"report|chat","hay":"소문자 결합 문자열(title snippet tags kind)"}
```
채팅 kind 의 `extra`: 채팅뉴스 `{url,outlet,stocks[],sharer}` · 채팅의견 `{stock,sharer,stance,date}` · 목표가 `{stock,value,unit,sharer}`. 기존 항목은 `source:"report"`, `hay` 추가(하위호환). 채팅의견은 view/position 타입·봇 제외(≈720건), 실데이터 기준 전체 ≈6,200건.
`build.aliases` = `hublib.config.STOCK_ALIASES` (소문자 키 → 정규 종목명).

**C4. 검증 확장** (`verify`)
- 기존 `verify.{meta,summary,stocks,calls}` 는 채팅 코호트 그대로.
- 추가 `verify.report = {enabled, meta:{cohort:"report", calls, stocks, excluded:{no_ticker, ...}}, summary, stocks, calls}` — 리포트 **수급 포착 언급**(`mentions[].source=="수급"`)을 강세 콜로 본 코호트. 채팅 코호트와 절대 합산하지 않는다.
- 추가 `verify.themes = [{theme, cohort:"report", calls, h5,h20,h60:{judged,hit,hit_rate,avg_excess,median_excess}}]`.
- 두 코호트의 `stocks[]` 행에 `series:[[date,close],…]` (거래일 5일 간격 다운샘플 + 마지막 점, ≤ 80점) 추가.

**C5. What's new** (`whats_new`, 없으면 `null`)
```json
{"since":"YYYY-MM-DD","generated":"…","new_stocks":[{"name":"","count":0}],
 "surging":[{"name":"","recent":0,"prev":0}],"new_calls":[{"stock":"","stance":"","date":""}],
 "new_targets":[{"stock":"","value":"","unit":"","date":""}],"new_reports":["id"]}
```
전일 요약은 `build/kb_summary.json` (actions/cache) 에 보존한다. `feed.json` 은 JSON Feed 1.1.

**C6. AI** (`ai_digest` — 기존 키 유지, 추가)
```json
{"generated":"","range":"","model":"","digest":{…기존…},
 "daily":{"date":"","lines":["","",""]},
 "stock_reasons":{"<종목명>":{"text":"","as_of":"YYYY-MM-DD"}},
 "news_flags":{"<url>":"neutral|relevant"}}
```
render 는 `news_flags` 를 `chat.news[]`·`stocks[].chat.news[]` 항목에 `neutral:true` 로 병합한다. 캐시는 `build/ai_cache.json` (actions/cache). 키 없음·실패 시 기존처럼 조용히 생략.

### 3.4 파일 소유권 (병렬 작업 충돌 방지)

| 트랙 | 소유 | 건드리지 않음 |
|---|---|---|
| 기반 | `hub/*.js`(생성), `hub_template.html`, `hublib/render.py`, `hublib/split.py`, `sw.js`, `tests/e2e/*`, `tests/test_phases.py`, `tests/test_split.py` | — |
| A (데이터) | `hublib/{search,verify,whatsnew,schema,ai_summary}.py`, `merge_hub.py`, `ai_digest.py`, `hublib/render.py` 의 collect 배선만, `tests/test_*.py`, `.github/workflows/build.yml` 캐시 스텝 | `hub/*.js`, `hub_template.html` |
| B (UI) | `hub/*.js`, `hub_template.html`(CSS·head·bnav 마크업), `vendor/`, `sw.js` 프리캐시 1줄, `.github/workflows/build.yml` 의 `cp vendor` 1줄 | `hublib/*.py` |

B 는 A 의 필드가 없어도 동작해야 한다(`D.whats_new||null`, `st.series||null` 등 — 널 허용).

기반 계획이 먼저 가져가는 항목: 검색 디바운스 + `hay` 런타임 보강(P5 일부), `build/report.md` 크기 리포트(Q1 일부). A 는 `hay` 를 빌드 시 넣고 예산 표를 덧붙이며, B 는 디바운스를 재구현하지 않는다.

## 4. 오류 처리 원칙

- 청크 로딩 실패: 해당 탭/패널에 "불러오지 못했습니다 · 다시 시도" — 다른 탭에 영향 없음. 코어 실패는 기존 1회 캐시버스터 재로드 유지.
- 새 Python 단계(whats_new·report cohort·AI·schema)는 전부 try/except 로 격리, 실패 시 `build.<단계>_error` 에 기록하고 빌드는 계속된다(기존 verify 관례).
- 크기 예산 초과는 CI **경고**(Job Summary)이며 실패가 아니다. 스키마 필수 키 누락만 실패.

## 5. 테스트 전략

- Python: 순수 함수(split/search/whats_new/report cohort/schema/ai 캐시 선택) 전량 단위 테스트. 네트워크는 loader 주입·`VERIFY_SKIP`·키 부재로 격리.
- 셸: `tests/e2e/test_hub_smoke.py` (pytest-playwright) — 부트 완료·콘솔 에러 0·탭별 렌더·검색·딥링크·청크 로딩·SW 등록. `E2E_SITE_DIR` 없으면 skip. CI 에서 `_site` 조립 후 실행.
- 예산: `tests/test_budget.py` — `KB_BUDGET_CHECK=1` 일 때 kb.* 크기 상한 확인, 그 외 skip.

## 6. 측정 목표

| 지표 | 현재 | 목표 |
|---|---|---|
| 초기 데이터 전송(gzip) | 2.7MB | ≤ 0.6MB |
| 부트 렌더(데스크톱) | 460ms | < 100ms |
| 부트 DOM / canvas | 17,655 / 213 | ≈3,000 / ≤ 15 |
| 렌더 블로킹 외부 리소스 | 2 | 0 |
| 검색 가능 항목 | 2,282 | ≈ 6,200 |
| 셸 JS 테스트 | 0 | 스모크 10+ |
