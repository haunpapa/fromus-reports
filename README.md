# fromus-reports

프롬어스 투자 커뮤니티의 데일리/위클리 리포트와 카카오톡 대화를 구조화해
검색·섹터·종목·전략 지식 허브(`hub.html`)로 제공하는 정적 사이트.

## 아키텍처

```
카카오톡 CSV(수동 export, 여러 방 가능)
  └─ generator/refresh.sh → update_archive.py ─→ chat_kb.json (방별 병합, 로컬 실행·커밋)
reports/daily·weekly/*.html (수동 작성·커밋)
  └─ CI(.github/workflows/build.yml — main push 또는 KST 월~금 07:30 크론)
       ├─ build_index.py                → index.html (아카이브 목록)
       ├─ build_hub.py --phase collect  → knowledge_base.json (파싱·집계·시세·모멘텀·chat 병합·콜 검증 — 배포하지 않는 중간 산출물)
       ├─ ai_digest.py                  → ai_digest.json (AI 위클리·데일리·종목 사유·뉴스 분류, 시크릿 있을 때만)
       └─ build_hub.py --phase render   → hub.html(셸) + hub.app.<hash>.js(hub/*.js concat)
                                          + kb.core.<hash>.json + kb.{chat,search,glossary,stockchat}.<hash>.json
                                          + version.json + feed.json
  └─ GitHub Pages (Actions artifact 배포 — 산출물은 커밋하지 않음)
```

카카오톡 생성기(`generator/`)의 사용법·다방 병합 주의는 [generator/README.md](generator/README.md) 참고.

빌더 로직은 `hublib/` 패키지에 있다:

| 모듈 | 책임 |
|---|---|
| `hublib/config.py` | 공통 상수·타소노미(종목 별칭/섹터 테마/원칙 버킷)·시간 헬퍼 |
| `hublib/parse.py` | 리포트 HTML 파싱·정규화 (BeautifulSoup) |
| `hublib/cache.py` | 리포트 파싱 증분 캐시 (파일 sha1 기준) |
| `hublib/aggregate.py` | 종목·섹터 집계, 리포트 검색 인덱스 |
| `hublib/search.py` | 검색 인덱스 보강 — `source` 부착 + 채팅 항목(뉴스·의견) |
| `hublib/momentum.py` | 지수 시계열·시장 모멘텀 (yfinance/KRX) — 종목별 future 타임아웃, 히스토리 보강 병렬 수집 |
| `hublib/verify.py` | 채팅 콜 추출·판정·집계 + 가격 수집(8워커 병렬)/증분 캐시 |
| `hublib/whatsnew.py` | 전일 빌드 대비 "오늘 달라진 것" |
| `hublib/ai_summary.py` | AI 요약(위클리·데일리 3줄·종목 사유·뉴스 neutral 플래그) + 증분 캐시·실패 센티널 |
| `hublib/ai_prompts.py` | AI 프롬프트 문구 (로직 diff 와 분리) |
| `hublib/schema.py` | knowledge_base 최소 스키마 검사 — 셸이 빈 화면으로 죽는 키 누락을 빌드에서 잡는다 |
| `hublib/split.py` | render 출력 분할·슬림화 (코어/청크, 순수 함수) |
| `hublib/feed.py` | JSON Feed 1.1 생성 |
| `hublib/render.py` | `collect`/`render` 2단계 빌드 + 앱 JS 해시 배출·preload 주입 + index 허브 버튼 주입 |
| `hub/*.js` | 허브 셸 앱 코드 — 파일명 숫자 순서로 concat 해 내용 해시 파일 `hub.app.<hash>.js` 로 배출한다. `hub_template.html` 의 `/*APPSRC*/` 마커에 그 경로가, `<!--APPPRELOAD-->`·`<!--KBPRELOAD-->` 마커에 preload 링크가 들어간다. **앱 로직은 템플릿이 아니라 `hub/*.js` 에서 고친다** |

## 로컬 빌드

```bash
pip install -r requirements.txt
python build_hub.py --phase all --src . --out hub.html --json knowledge_base.json
python -m http.server 8000   # → http://localhost:8000/hub.html
```

`--phase collect` 는 파싱·네트워크가 필요한 무거운 단계, `--phase render` 는
`knowledge_base.json`(+`ai_digest.json`) 만 읽어 셸을 만드는 가벼운 단계(bs4/yfinance 불필요)다.
AI 요약까지 넣으려면 CI 와 같은 순서로 `collect` → `python ai_digest.py` → `render` 를 실행한다.

### 환경 변수

| 변수 | 용도 | 기본값 |
|---|---|---|
| `ANTHROPIC_API_KEY` | `ai_digest.py` 의 API 키 (CI Secret). 없으면 AI 요약을 생략한다 | — |
| `AI_DIGEST_MODEL` | AI 요약 모델 | `claude-sonnet-5-5` |
| `AI_DIGEST_EFFORT` | AI 요약 `output_config.effort` (Sonnet 5.5 는 thinking 을 끌 수 없어 effort 로 조절한다 — thinking 토큰이 `max_tokens` 에 포함된다) | `medium` |
| `SITE_BASE_URL` | `feed.json` 절대 URL 기준 (CI Variable). 없으면 상대 URL | — |
| `VERIFY_SKIP` | `1` 이면 검증 레이어 가격 수집을 건너뛴다 (테스트 네트워크 격리) | — |
| `MARKET_MOMENTUM_AUTO_INSTALL` | FinanceDataReader 누락 시 런타임 pip 설치 여부. CI 는 `0`(누락 시 모멘텀 생략) | `1` |
| `MARKET_MOMENTUM_MAX_STOCKS` | 모멘텀 계산 종목 상한 | `140` |
| `MARKET_MOMENTUM_HISTORY_STOCKS` | 히스토리 정밀 보강 종목 수. CI 는 `40` | `0` |
| `MARKET_MOMENTUM_STOCK_TIMEOUT` | 종목당 데이터 소스 타임아웃(초) | `7` |
| `KB_BUDGET_CHECK` | `1` 이면 `tests/test_budget.py` 가 kb 청크 크기 예산을 검사한다 | — |
| `E2E_SITE_DIR` | E2E 가 서빙할 폴더. 없으면 e2e 를 skip 한다 | — |

## 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ generator/test_parse.py -q --ignore=tests/e2e
```

```bash
# 셸 JS 스모크 (렌더 후) — pytest-xdist 로 4워커 병렬
python -m playwright install chromium
E2E_SITE_DIR=. python -m pytest tests/e2e -q -n 4
```

- `tests/e2e/test_hub_smoke.py` — 부트·탭·검색·딥링크·SW·성능 회귀 기본 스모크.
- `tests/e2e/test_hub_features.py` — 모바일 하단 탭·검색 시트, 검색 2.0(출처·기간·별칭·최근 검색어),
  종목 상세 뷰, 홈 "오늘 달라진 것"·AI 데일리, 검증 코호트 토글·테마·분포.
  아직 데이터에 없는 필드(`whats_new`·`build.aliases`·`verify.report`·`ai_digest.daily` 등)에 기대는
  단언은 **자동으로 skip 하거나 "없으면 없어야 한다"로 대칭 검증**한다 — 필드가 생기면 그대로 켜진다.
  검증 코호트 테스트는 `VERIFY_TAB_HIDDEN` 이 켜져 있는 동안 skip 되고, 대신 탭이 숨겨졌는지를 검증한다.
- CI 는 유닛 → kb 크기 예산(`KB_BUDGET_CHECK=1`, 경고만·코어 2배 초과 시 실패) → E2E 순으로 돈다.

## CI

- 트리거: main push(`reports/`·`chat_kb.json`·빌더·`hub/`·`sw.js`·`tests/e2e/`·워크플로·`requirements*.txt` 변경),
  크론 `30 22 * * 0-4`(KST 월~금 07:30 — 주말은 금요일과 같은 데이터라 생략), 수동 실행.
- job 타임아웃 20분 (2026-09 기준 실행 시간은 배포 포함 약 1분 30초~2분 40초).
- 의존성은 `requirements*.txt` 로 단일화하고 setup-python pip 캐시를 쓴다. CI 에서 런타임 pip 설치는 금지다.
  Playwright 브라우저는 `playwright` 버전(핀: `requirements-dev.txt`)을 키로 캐시한다.
- 롤링 캐시 3종(가격·kb 요약·AI)은 restore/save 를 분리해 **테스트가 깨진 날에도 당일 수집분을 저장**한다.

## knowledge_base.json 스키마 (v2)

`build.schema` 필드로 버전을 표기한다. **키 추가는 하위호환(마이너)**,
**키 의미 변경·삭제는 `schema` 증가**로 관리한다. hub.html 은 이 데이터를
`kb.core.<hash>.json`(첫 화면) + 청크(`kb.chat/search/glossary/stockchat.<hash>.json`, 필요 시점 fetch) 로 받아
렌더한다. 분할 규칙은 `docs/superpowers/specs/2026-08-23-hub-improvement-design.md` §3.3 C2.

최상위 키:

| 키 | 설명 |
|---|---|
| `build` | 빌드 메타: `schema`, `generated`(KST), `reports/daily/weekly` 수, `from/to`, `index_source`("yfinance"\|"report"), `market_momentum`, `aliases`(소문자 별칭→정규 종목명, C3), (실패 시)`chat_merge_error`·`verify_error`·`whats_new_error`·`schema_warnings` |
| `reports` | 파싱된 리포트 레코드 배열 (type/date/id/sections·insights 등) |
| `search` | 검색 인덱스 항목 배열 (kind/title/snippet/date/tags/extra) + `source`("report"\|"chat"). 채팅 kind 는 `채팅뉴스`·`채팅의견` 두 가지다(목표가는 2026-08-23 부터 싣지 않는다). 소문자 토큰 `hay` 는 싣지 않고 클라이언트가 재계산한다(`hub/30_search.js` `hayOf`) |
| `stocks` | 종목별 집계 (name/count/mentions/sectors/themes/targets/market_momentum) |
| `sectors` | 섹터테마별 집계 (theme/names/stocks/mentions/market_momentum) |
| `supply_days` | 날짜별 스마트머니(수급) TOP |
| `stance` | 데일리 대표 스탠스(headline/quote/points) |
| `principles` | 살아있는 전략 원칙 버킷 |
| `glossary` | 용어·개념 정의 |
| `events` | 포착된 이벤트 |
| `sentiment` | 일자별 센티멘트 점수 |
| `series` | 지수 시계열(코스피/코스닥/나스닥) |
| `chat` | 카카오톡 온톨로지 병합분(종목·뉴스·목표가·관계망 등, `merge_hub.py`) |
| `ai_digest` | AI 요약 (`ai_digest.py` 산출물, 없으면 null) — `digest`(위클리) + `daily:{date,lines[3]}` + `stock_reasons:{종목:{text,as_of}}` + `news_flags:{url:"neutral"\|"relevant"}` (C6). render 가 `news_flags` 를 `chat.news[]`·`stocks[].chat.news[]` 에 `neutral:true` 로 병합한다. `news_flags` 는 **Batches API 2단계**로 채운다 — 오늘 빌드가 제출하고 다음 빌드가 수거한다(비용 50% 절감, 하루 지연 수용, 2일 넘게 수거가 안 되면 잠금 해제, SDK 가 없으면 동기 호출로 폴백) |
| `verify` | 채팅 방향성 발화의 사후 성과 검증 (`hublib/verify.py`) — `meta`/`summary`/`stocks`/`calls`. 봇·무벤치마크 종목 제외, 발화 **다음 거래일 종가** 진입, 거래일 기준 h5/h20/h60, **지수 대비 초과수익**이 1차 지표. 수집 실패 시 `{"enabled": false}` |
| `verify.report` | 리포트 **수급 포착 언급**(`stocks[].mentions[].source=="수급"`)을 강세 콜로 본 별도 코호트 (C4). `meta.cohort=="report"`, `excluded.no_ticker`(US·비상장 제외). 채팅 코호트와 **절대 합산하지 않는다** |
| `verify.themes` | 리포트 코호트의 테마별 집계 `[{theme, cohort:"report", calls, h5/h20/h60}]` (C4) |
| `verify.stocks[].series` | 종목 주가 시계열 `[[date, close]]` — 거래일 5일 간격 다운샘플 + 마지막 점(≤80점). 두 코호트 모두 (C4) |
| `whats_new` | 전일 빌드 대비 변화 (`hublib/whatsnew.py`, C5) — `since`/`new_stocks`/`surging`/`new_calls`/`new_targets`/`new_reports`. 첫 빌드·같은 기준일이면 `null` |
| `recent_from`·`recent_reports`·`window_days` | 최근 집계 윈도우 메타 |

### 그 밖의 산출물·캐시

| 파일 | 설명 |
|---|---|
| `hub.app.<hash>.js` | 셸 앱 JS (`hub/*.js` concat). 내용 해시 파일명이라 코드가 바뀐 날만 재다운로드된다 |
| `version.json` | `{core, generated}` — 셸이 `?nosw=` 로 SW 를 우회해 새 빌드를 감지할 때 쓴다 |
| `feed.json` | JSON Feed 1.1 (`hublib/feed.py`) — 최근 리포트 30건 + 오늘 달라진 것. 절대 URL 은 CI Variable `SITE_BASE_URL` 이 있을 때만 |
| `build/parse_cache.json` | 리포트 파싱 캐시 (CI 키 `parse-cache-`) |
| `build/price_cache.json` | 검증 레이어 일봉 캐시 (CI 키 `price-cache-v1-`) |
| `build/kb_summary.json` | what's new 의 전일 요약 (CI 키 `kb-summary-`) |
| `build/ai_cache.json` | AI 증분 요약 캐시 (CI 키 `ai-cache-v1-`). 실패 응답도 센티널로 남겨 3회 연속 실패하면 7일간 재호출하지 않는다. 뉴스 배치의 pending 상태도 여기 둔다. 파일에 `model` 마커가 있어 `AI_DIGEST_MODEL` 이 바뀌면 위클리·데일리·종목 사유 키만 버리고(종목 사유는 빌드당 30개씩 재생성) 뉴스 플래그·pending 배치는 유지한다 |
| `build/report.md`·`build/e2e_timing.json` | kb 크기·예산·E2E 타이밍 — CI Job Summary 로 출력 |

## 주의

- `index.html`/`hub.html`/`hub.app.*.js`/`knowledge_base.json`/`ai_digest.json`/`kb.*.json`/`version.json`/`feed.json` 은
  CI 산출물이며 커밋하지 않는다(`.gitignore`). 소스는 `reports/`·`chat_kb.json` 과 빌더 코드다.
- `knowledge_base.json`(≈14MB)은 collect→render 사이의 중간 산출물이다. 클라이언트는 `kb.*.json` 청크만 받으므로
  **Pages 에 배포하지 않는다**.
- `trade.html` 은 별도 레포(korea-trade-dashboard)에서 CI가 동기화하며, 실패 시 리포 내 스냅샷을 유지한다.
- 카카오톡 원문은 실명을 포함한 채(`public=False`) 공개 배포한다. 익명화는 사용자 결정으로 범위에서 뺐다
  (PR #4, 2026-08-23). `generator/chat_to_kb.py --public` 로 정제본을 만들 수는 있다.
- `verify` 는 **종목 단위만** 집계한다. 발화자별 적중률·랭킹은 의도적으로 만들지 않는다
  (표본이 얇고 커뮤니티 리스크가 이익보다 크다). `calls[].sources[].sharer` 는 근거 표시용이다.
- 검증 대상 콜은 강세 편향이 크다(강세 132 · 약세 14, 2026-08-17 기준). 사실상
  **강세 의견의 초과수익 검증**이며 허브 화면에도 그렇게 명시한다.
- **검증 탭은 숨겨져 있다** — `hub/23_verify.js` 의 `VERIFY_TAB_HIDDEN = true`(리포트 코호트 h20 판정이 너무 얇다).
  `verify` 데이터는 계속 빌드되고 종목 상세의 "콜 검증" 카드는 보인다. `false` 로 바꾸면 탭·`#verify`·홈 링크가 함께 돌아온다.
- 채팅 **목표가**는 채팅 탭과 전역 검색에서 뺐다(2026-08-23). 데이터(`chat.targets`)와 홈 "새 목표가" 줄은 남아 있다.
- 로컬에서 verify 를 건너뛰려면 `VERIFY_SKIP=1` — `tests/test_phases.py` 가 이 값으로
  네트워크를 격리한다.
- 셸에는 **서드파티 JS 가 없다**. 지수 스파크라인·센티멘트 막대는 인라인 SVG(`hub/20_home.js`·`hub/80_analytics.js`)로 그린다
  — 2026-09-02 에 Chart.js(`vendor/`)를 걷어냈다.
- 서비스워커(`sw.js`, 캐시 `fu-hub-v5`): 셸은 stale-while-revalidate, 해시 파일(`kb.*.json`·`hub.app.*.js`)은 cache-first,
  `/reports/` 는 별도 캐시 `fu-reports-v1` 에 FIFO 30건 상한. 캐시 구조를 바꾸면 버전을 올려 activate 에서 구캐시를 정리한다.
- 딥링크는 두 가지다. `#stocks/<이름>` 은 **종목 목록**을 그 이름으로 걸러 첫 행을 펼치고,
  `#stock/<이름>`(단수)은 **공유용 종목 상세 뷰**를 연다 — 주가·언급 오버레이, 두 코호트의 콜 검증,
  채팅 근거, 관계 이웃이 한 화면에 있다. 칩·태그·검색 결과의 `data-stock` 클릭은 모두 상세 뷰로 간다.
- 모바일(≤940px) 하단 탭은 5개(개요·종목·섹터·전략·더보기)이고 나머지는 **더보기 시트**에 있다.
  검색창을 누르면 `body.search-open` 전체화면 시트가 열리며, 뒤로가기로 닫힌다.

## 변경 이력

| PR / 커밋 | 머지 | 내용 |
|---|---|---|
| [#1](https://github.com/haunpapa/fromus-reports/pull/1) | 2026-05-30 | 지식 허브 추가 — `build_hub.py`·`hub_template.html`, 아카이브 빌드와 `build.yml` 통합 |
| [#2](https://github.com/haunpapa/fromus-reports/pull/2) | 2026-06-19 | 카카오톡 채팅 온톨로지 ↔ 허브 결합 — `merge_hub.py` 비파괴·멱등 병합, 종목 카드 💬 채팅 근거 |
| [#3](https://github.com/haunpapa/fromus-reports/pull/3) | 2026-07-04 | 셸/데이터 분리(hub.html 5.3MB → 146KB 셸) · Pages artifact 배포 · `hublib/` 분리 · collect/render 2단계 · 파싱 증분 캐시 · 서비스워커 |
| [#4](https://github.com/haunpapa/fromus-reports/pull/4) | 2026-07-05 | 여러 카톡방 통합 아카이브 — 방별 최신 스냅샷 verbatim + fold 병합 (`generator/`) |
| [#5](https://github.com/haunpapa/fromus-reports/pull/5) | 2026-08-17 | 성과 검증 레이어 — 채팅 콜 vs 실제 주가(거래일 h5/h20/h60, 지수 대비 초과수익), `hublib/verify.py` |
| `50f1fe0`·`ca093f0`·`7746953` (main 직접) | 2026-08-23 | 허브 개선 기반·Track A·B — `hub/*.js` 모듈 분리, kb 청크 분할, 검색 2.0, 종목 상세, what's new, `feed.json`, AI 데일리·종목 사유, 리포트 코호트 검증. 이어서 검증 탭 숨김·채팅 목표가 제거(`83b931c`) |
| `28e8653`…`6a1db0e` (main 직접) | 2026-09-02 | 성능 병목 13건 — `knowledge_base.json` 배포 제외, 검색 `hay` 제거(search 청크 −39%), 가격 수집 병렬화, CI 캐시·pip 정비, AI 실패 센티널, kb.core preload, 웹폰트 비블로킹 (CI build job 4m14s → 2m27s) |
| [#6](https://github.com/haunpapa/fromus-reports/pull/6) | 2026-09-02 | 성능 후속 8건 — Chart.js 제거(인라인 SVG), 앱 JS 해시 분리, SW 리포트 캐시 상한, E2E `-n 4`, 모멘텀 future 타임아웃·병렬화, 생성기 단일 패스, 뉴스 Batches API, AI 단계별 예외 격리 |
