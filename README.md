# fromus-reports

프롬어스 투자 커뮤니티의 데일리/위클리 리포트와 카카오톡 대화를 구조화해
검색·섹터·종목·전략 지식 허브(`hub.html`)로 제공하는 정적 사이트.

## 아키텍처

```
카카오톡 CSV(수동 export)
  └─ generator/update_archive.py ─→ chat_kb.json (커밋)
reports/daily·weekly/*.html (수동 작성·커밋)
  └─ CI(.github/workflows/build.yml)
       ├─ build_index.py                → index.html (아카이브 목록)
       ├─ build_hub.py --phase collect  → knowledge_base.json (파싱·집계·시세·모멘텀·chat 병합·콜 검증)
       ├─ ai_digest.py                  → ai_digest.json (AI 위클리 요약, 시크릿 있을 때만)
       └─ build_hub.py --phase render   → hub.html(셸: hub/*.js concat) + kb.core.<hash>.json + kb.{chat,search,glossary,stockchat}.<hash>.json + version.json
  └─ GitHub Pages (Actions artifact 배포 — 산출물은 커밋하지 않음)
```

빌더 로직은 `hublib/` 패키지에 있다:

| 모듈 | 책임 |
|---|---|
| `hublib/config.py` | 공통 상수·타소노미(종목 별칭/섹터 테마/원칙 버킷)·시간 헬퍼 |
| `hublib/parse.py` | 리포트 HTML 파싱·정규화 (BeautifulSoup) |
| `hublib/aggregate.py` | 종목·섹터 집계, 검색 인덱스 |
| `hublib/momentum.py` | 지수 시계열·시장 모멘텀 (yfinance/KRX) |
| `hublib/render.py` | `collect`/`render` 2단계 빌드 + index 허브 버튼 주입 |
| `hublib/cache.py` | 리포트 파싱 증분 캐시 (파일 sha1 기준) |
| `hublib/verify.py` | 채팅 콜 추출·판정·집계 + 가격 수집/증분 캐시 |
| `hublib/split.py` | render 출력 분할·슬림화 (코어/청크, 순수 함수) |
| `hub/*.js` | 허브 셸 앱 코드 — 파일명 숫자 순서로 concat 되어 `hub_template.html` 의 `/*APPJS*/` 마커에 주입된다 |

## 로컬 빌드

```bash
pip install beautifulsoup4 lxml yfinance
python build_hub.py --phase all --src . --out hub.html --json knowledge_base.json
python -m http.server 8000   # → http://localhost:8000/hub.html
```

`--phase collect` 는 파싱·네트워크가 필요한 무거운 단계, `--phase render` 는
`knowledge_base.json` 만 읽어 셸을 만드는 가벼운 단계(bs4/yfinance 불필요)다.

## 테스트

```bash
pip install pytest
python -m pytest tests/ generator/test_parse.py -q
```

```bash
# 셸 JS 스모크 (렌더 후)
pip install pytest-playwright && python -m playwright install chromium
E2E_SITE_DIR=. python -m pytest tests/e2e -q
```

## knowledge_base.json 스키마 (v2)

`build.schema` 필드로 버전을 표기한다. **키 추가는 하위호환(마이너)**,
**키 의미 변경·삭제는 `schema` 증가**로 관리한다. hub.html 은 이 데이터를
`kb.core.<hash>.json`(첫 화면) + 청크(`kb.chat/search/glossary/stockchat.<hash>.json`, 필요 시점 fetch) 로 받아
렌더한다. 분할 규칙은 `docs/superpowers/specs/2026-08-23-hub-improvement-design.md` §3.3 C2.

최상위 키:

| 키 | 설명 |
|---|---|
| `build` | 빌드 메타: `schema`, `generated`(KST), `reports/daily/weekly` 수, `from/to`, `index_source`("yfinance"\|"report"), `market_momentum`, (병합 실패 시)`chat_merge_error` |
| `reports` | 파싱된 리포트 레코드 배열 (type/date/id/sections·insights 등) |
| `search` | 검색 인덱스 항목 배열 (kind/title/snippet/date/tags) |
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
| `ai_digest` | AI 위클리 다이제스트 (`ai_digest.py` 산출물, 없으면 null) |
| `verify` | 채팅 방향성 발화의 사후 성과 검증 (`hublib/verify.py`) — `meta`/`summary`/`stocks`/`calls`. 봇·무벤치마크 종목 제외, 발화 **다음 거래일 종가** 진입, 거래일 기준 h5/h20/h60, **지수 대비 초과수익**이 1차 지표. 수집 실패 시 `{"enabled": false}` |
| `recent_from`·`recent_reports`·`window_days` | 최근 집계 윈도우 메타 |

## 주의

- `index.html`/`hub.html`/`knowledge_base.json`/`ai_digest.json`/`kb.*.json` 은 CI 산출물이며 커밋하지 않는다(`.gitignore`). 소스는 `reports/`·`chat_kb.json` 과 빌더 코드다.
- `trade.html` 은 별도 레포(korea-trade-dashboard)에서 CI가 동기화하며, 실패 시 리포 내 스냅샷을 유지한다.
- 카카오톡 원문은 실명 포함(`public=False`) — 공개 익명화는 후속 과제.
- `verify` 는 **종목 단위만** 집계한다. 발화자별 적중률·랭킹은 의도적으로 만들지 않는다
  (표본이 얇고 커뮤니티 리스크가 이익보다 크다). `calls[].sources[].sharer` 는 근거 표시용이다.
- 검증 대상 콜은 강세 편향이 크다(강세 132 · 약세 14, 2026-08-17 기준). 사실상
  **강세 의견의 초과수익 검증**이며 허브 화면에도 그렇게 명시한다.
- 로컬에서 verify 를 건너뛰려면 `VERIFY_SKIP=1` — `tests/test_phases.py` 가 이 값으로
  네트워크를 격리한다.
