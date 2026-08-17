# 성과 검증 레이어 (Call Verification) — 설계

- 작성일: 2026-08-17
- 상태: 브레인스토밍 확정 → 사용자 최종 검토 대기
- 관련 파일(신규): `hublib/verify.py`, `tests/test_verify.py`
- 관련 파일(수정): `hublib/render.py`, `hub_template.html`, `.github/workflows/build.yml`, `.gitignore`, `README.md`

## 1. 목표

지금 허브는 **"누가 무엇을 말했다"까지만** 보여준다. 채팅 온톨로지에 종목·날짜·방향(stance)·티커가 모두 붙어 있는데도, **"그래서 그 판단이 맞았나"** 를 되짚는 화면이 없다.

발화 시점 이후의 실제 주가를 대조해 **종목 단위 적중률·초과수익**을 산출하고, 전용 `검증` 탭으로 노출한다. 사이트의 성격을 *기록 아카이브* 에서 *검증되는 지식* 으로 옮기는 것이 목적이다.

### 확정된 요구사항 (브레인스토밍 결과)
- **범위**: `chat.stocks[].mentions` 중 `stance ∈ {bullish, bearish}` 만. 목표주가(`targets`)·행동원칙(`actions`)·리포트 본문은 1차 범위 밖.
- **귀속 단위**: **종목 단위만**. 발화자별 적중률·랭킹은 **산출하지 않는다**. 발화자명은 근거 행에만 남긴다(이미 종목 카드에 노출 중인 수준).
- **코호트**: 봇(`김병철(봇)`)·ASSET 제외한 **핵심 163건 / 35종목**. 봇·ASSET도 `cohort` 태그를 달아 산출은 하되 UI 기본 필터에서 뺀다.
- **구조**: 전용 `검증` 탭 신설 + 기존 종목 카드에 요약 칩. 주가 차트는 2차 과제.
- **무의존성 원칙 유지**: 허브 셸은 외부 JS 라이브러리를 쓰지 않는다. 신규 파이썬 의존성도 0 (fdr·yfinance는 이미 CI에 있음).

## 2. 현재 동작 (as-is)

### 2.1 데이터 경로
```
chat_kb.json (수동 생성·커밋)
  └─ hublib/render.py:_merge_chat_kb → merge_hub.merge()
       └─ knowledge_base.json["chat"], ["stocks"][].chat
            └─ render() → kb.<hash>.json → hub_template.html 이 fetch
```

### 2.2 `chat_kb.stocks[<종목명>]` 스키마 (실측)
```
name, market("KR"|"US"|"ASSET"|""), ticker, sector, count, themes,
mentions: [{date, sharer, source:"chat", stance, type, snippet, full}]
news, targets
```
- `stance` 분포(전체 3,672 mentions): `자료` 2544 · `neutral` 704 · `bullish` 303 · `watch` 92 · `bearish` 26 · `mixed` 3
- `type` 분포: `research` 2544 · `view` 811 · `position` 317
- `stance ∈ {bullish,bearish}` 인 건은 **전부 `type ∈ {view, position}`** (research는 전량 `자료`)

### 2.3 기존 가격 수집 자산 (재사용 대상)
| 위치 | 내용 | 검증 레이어에서의 활용 |
|---|---|---|
| `hublib/momentum.py:77` `_ensure_finance_datareader()` | fdr 지연 import + 자동설치 | 그대로 재사용 |
| `hublib/momentum.py:92` `_load_krx_listing()` | KRX 전종목(코드·**Market**·시총) | **코드→시장(KOSPI/KOSDAQ)** 매핑에 재사용 |
| `hublib/momentum.py:185` `_stock_market_momentum()` | `fdr.DataReader(code, start)` 일봉 | 호출 패턴만 참고(로직 공유 안 함) |
| `hublib/momentum.py:9` `fetch_index_series(reports)` | 지수 시계열 | **재사용 불가** — §4.3 참조 |
| `hublib/cache.py` `ParseCache` | 파일 sha1 증분 캐시 | 캐시 설계 패턴 참고 |

### 2.4 CI 현황
- 스케줄 매일 07:30 KST + `reports/**`·`chat_kb.json`·`hublib/**` push
- 총 소요 **1분 10초~1분 26초** (최근 8회 전량 성공)
- `build/parse_cache.json` 이 `actions/cache@v4` 로 복원됨

## 3. 검증 대상 코호트 (실측 확정)

> 이하 수치는 **2026-08-17 시점 `chat_kb.json` 스냅샷**이다. 규모 감각과 UI 설계 근거로 쓰며, 테스트 단언 대상이 아니다(§8).

`stance ∈ {bullish,bearish}` 전체는 **329건**이며 **전건 티커 보유**(공백 0). 내역:

| 구분 | 건수 | 제외 사유 |
|---|---|---|
| `김병철(봇)` 발화 | 138 | 미 증시 시황 브리핑 자동 게시. 뉴스 논조 파생 stance이지 사람의 판단이 아님 |
| ASSET (원유 26·비트코인 20·금 3·이더 3) | 52 | 대응 벤치마크 지수 부재 → 초과수익 정의 불가 |
| **핵심 코호트 (`cohort:"core"`)** | **163 / 35종목** | — |

> 두 제외 조건은 **겹친다**(봇이 ASSET을 말한 건 24). 분할이 아니므로 `138 + 52 + 163 ≠ 329` 다.
> 검산: `138 + 52 − 24 + 163 = 329` ✓. `cohort` 는 배타적 라벨이 아니라 `bot`·`asset` 두 개의 독립 플래그로 구현한다.

핵심 163건의 구성:
- 시장: KR 83 · US 80
- 방향: bullish 147 · **bearish 16** ← 강한 강세 편향. §6.3 정직성 장치의 근거
- 유형: view 93 · position 70
- 기간: **2026-03-05 ~ 2026-08-13** (US 최초 03-05, KR 최초 03-09)

### 3.1 중복·충돌 (실측)
- **중복**: `(종목, 날짜, 방향)` 이 같은 그룹 12개, 중복분 13건 → **163 → 고유 콜 150건**
- **충돌**: 같은 `(종목, 날짜)` 에 bullish/bearish 공존 **2건** (테슬라 2026-07-24, 삼성전자 2026-06-08) → 4개 콜

**최종 판정 대상 = 150 − 4 = 146콜 / 35종목.**

### 3.2 최종 146콜의 실제 분포 — UI 설계를 좌우함
| 축 | 실측 |
|---|---|
| 시장 | KR 73 · US 73 (균형) |
| 방향 | bullish **132** · bearish **14** |
| 월별 | 03월 17 · 04월 22 · 05월 27 · **06월 47** · 07월 29 · 08월 4 |
| 종목당 콜 | 최소 1 · **중앙값 2** · 최대 24 (SK하이닉스) |
| **콜 5건 이상** | **7종목 / 88콜 (60%)** — SK하이닉스 24, 삼성전자 15, 엔비디아 13, 테슬라 13, 마이크론 12, 오라클 6, 구글 5 |
| 콜 5건 미만 | 28종목 / 58콜 (40%) |

**이 분포에서 나오는 결론 둘:**
1. 랭킹 테이블에 의미 있게 설 수 있는 종목은 **7개뿐**이다. 35종목을 한 테이블에 늘어놓으면 대부분이 회색이라 화면이 망가진다 → §6.3에서 기본 노출을 7종목으로 제한한다.
2. 종목별 적중률은 표본이 얇다. **전체 요약(146콜)이 주인공이고 종목 랭킹은 보조**라는 위계를 UI가 드러내야 한다.

## 4. 지표 정의

### 4.1 진입 시점 — look-ahead 차단
발화일 종가로 진입하면 **장 마감 후 발화가 미래를 훔친다**. 카톡 발화 시각은 `chat_kb` 에 분 단위까지만 있고 장 마감 여부를 신뢰할 수 없으므로, **일괄적으로 발화일보다 뒤인 첫 거래일의 종가**를 진입가로 쓴다.

```
entry_idx = 종목 시계열에서 date > mention_date 인 첫 인덱스
entry_date, entry_price = series[entry_idx]
```
발화일이 금요일이면 월요일, 휴장일이면 다음 개장일이 자동으로 잡힌다. 별도 휴장일 달력이 필요 없다.

### 4.2 구간 — 달력일이 아닌 **거래일**
`h ∈ {5, 20, 60}` 거래일. 위치 오프셋으로 계산한다.
```
exit_idx = entry_idx + h
exit_idx > len(series)-1  →  해당 구간 판정 불가(pending, null)
```

**성숙도 실측** (2026-08-17 기준, 최종 146콜, 달력일→거래일 근사):

| 구간 | 판정 가능 | 판정 대기 |
|---|---|---|
| h5 | 144 | 2 |
| **h20** | **133** | 13 |
| h60 | **55** | **91** |

→ **기본 노출은 h20**. h60은 아직 62%가 판정 대기라 토글은 제공하되 "판정 대기 91건" 을 크게 병기한다. 시간이 지나면 자연히 채워지므로 지표 자체는 유지한다.

### 4.3 벤치마크 — 시장 내부에서만 비교
| 종목 시장 | 종목 가격 소스 | 벤치마크 | 벤치마크 소스 |
|---|---|---|---|
| KR (KOSPI) | `fdr.DataReader(code, start)` | 코스피 `KS11` | fdr |
| KR (KOSDAQ) | 〃 | 코스닥 `KQ11` | fdr |
| US | `yfinance` | 나스닥 `^IXIC` | yfinance |
| ASSET (비핵심) | yfinance 프록시 `CL=F`/`GC=F`/`BTC-USD`/`ETH-USD` | **없음** | — |

**같은 시장의 종목과 벤치마크는 같은 소스에서 받는다.** 거래일 달력이 어긋나면 초과수익이 조용히 틀어지기 때문이다. 시장을 가로지르는 비교는 하지 않는다.

- KOSPI/KOSDAQ 판별: `_load_krx_listing()` 의 `Market` 필드를 **코드 기준**으로 조회. 조회 실패 시 코스피로 폴백하고 `bench_fallback:true` 로 표시한다. (`_build_ticker_map()` 은 이름 기준이라 쓰지 않는다 — `네이버`/`NAVER` 같은 표기 차이에 취약)
- **`fetch_index_series(reports)` 를 재사용하지 않는 이유**: 그 함수는 시계열 범위를 *리포트 날짜* 에서 뽑는데, 리포트 최초일은 2026-04-06인 반면 **콜 최초일은 2026-03-05** 다. 3월 콜의 벤치마크가 통째로 비게 된다. verify는 자체 범위로 별도 수집한다.
- 벤치마크 정렬은 인덱스가 아니라 **날짜 asof** 로 한다: `entry_date`·`exit_date` 각각에 대해 **그 날짜 이하 최근 거래일** 값을 쓴다. 종목 거래정지 등으로 두 시계열의 거래일 수가 어긋나도 안전하다.

### 4.4 산식
```
ret    = exit_price / entry_price - 1
bench  = bench_at(exit_date) / bench_at(entry_date) - 1
excess = ret - bench                       ← 1차 지표
hit    = (excess > 0) if stance == "bullish" else (excess < 0)
```
ASSET 코호트는 `bench = null`, `excess = null` 이고 `hit` 은 절대수익 부호로 판정한다(별도 표기).

**적중률 분모에서 빼는 것**: pending(미성숙), 충돌(§3.1), 가격 수집 실패. 0으로 채워 넣지 않는다.

### 4.5 중복·충돌 처리 규칙
- **중복** `(종목, 날짜, 방향)`: 1콜로 병합하고 원 발화들을 `sources[]` 에 보존. 근거 화면에는 전부 보여주되 통계 분모는 1로 센다.
- **충돌** 같은 `(종목, 날짜)` 에 양방향 공존: `conflict:true` 로 표시하고 **통계에서 제외**. 근거 화면에는 "의견 갈림"으로 양쪽 다 보여준다.

## 5. 파이프라인

### 5.1 배치 위치
`collect` 단계 끝, `_merge_chat_kb()` **직후**. verify는 병합된 `data["chat"]` 이 아니라 **원본 `chat_kb.json` 의 `stocks`** 를 읽는다(merge가 형태를 바꾸는 것과 무관하게 동작).

```python
# hublib/render.py collect() 내부
data = _merge_chat_kb(data)
data["verify"] = _build_verify_safe()     # 실패해도 build 계속
```
`_build_verify_safe()` 는 `_merge_chat_kb()` 와 **같은 방식으로 `chat_kb.json` 경로를 스스로 찾아 읽는다**(cwd → 리포 루트). `data["chat"]` 을 읽지 않는 이유는 `merge_hub.merge()` 가 구조를 재가공하기 때문이다 — 원본 스키마에만 의존해야 병합 로직 변경에 영향받지 않는다. 파일이 없으면 `None` 을 반환하고 `verify` 키를 만들지 않는다.

### 5.2 모듈 구조 — 네트워크와 판정을 분리
```
hublib/verify.py
  extract_calls(chat_kb) -> [Call]          # 순수. 코호트·중복·충돌 처리
  fetch_prices(calls) -> {key: Series}      # 네트워크. 캐시 사용
  judge_call(call, series, bench) -> dict   # 순수. 진입·구간·초과수익·hit
  aggregate(judged) -> dict                 # 순수. 종목별·전체 집계
  build_verify(chat_kb) -> dict             # 위 4개 조립 + 실패 격리
```
순수 함수 3개가 네트워크와 분리돼 있어 **CI 테스트는 네트워크 없이** 전량 돈다.

### 5.3 가격 캐시 `build/price_cache.json`
```json
{"v": 1,
 "series": {"KR:000660": {"last": "2026-08-16",
                          "points": [["2026-03-02", 195000.0], ...]}}}
```
- 키는 `<market>:<ticker>`. `v` 는 산식/스키마 변경 시 증가시켜 전량 무효화한다.
- 증분: `last` 다음 날부터만 받아 이어붙인다. 최초 1회만 전체 히스토리.
- 수집 범위 시작 = `min(mention_date) − 14일`(달력). 최초 콜이 2026-03-05이므로 실제 시작은 **2026-02-19**. 연휴가 끼어도 진입일(발화 다음 거래일)을 찾을 여유를 준다.
- `.gitignore` 에 `build/price_cache.json` 추가 (`parse_cache.json` 과 동일 취급)
- CI: `actions/cache@v4`, `key: price-cache-v1-${{ github.run_id }}` / `restore-keys: price-cache-v1-`
  (데이터가 매일 자라므로 항상 새로 저장하고 가장 최근 것을 복원하는 패턴)

### 5.4 비용 추정
35종목 + 벤치마크 3개. 최초 1회 약 40초, 캐시 이후 증분(최근 며칠)만 받으므로 약 10~15초. 현재 CI 1분 20초 대비 수용 가능하다. 종목당 타임아웃은 기존 `MARKET_MOMENTUM_STOCK_TIMEOUT`(7초)과 같은 방식으로 `VERIFY_STOCK_TIMEOUT`(기본 10초)을 둔다.

## 6. 산출 스키마 — `knowledge_base.json["verify"]`

`build.schema` 는 **2 유지**. 최상위 키 추가는 하위호환(마이너)이라는 기존 규약을 따른다.

> 아래는 **형식 예시**다. `calls`·`stocks`·`excluded`·`judged`·`pending`·`bullish`/`bearish` 는 §3 실측값이고, **`hit`·`hit_rate`·`avg_excess`·`ret`·`excess` 는 가격을 받아봐야 아는 값이라 `null` 로 두었다.** 이 스펙 어디에도 적중률 추정치를 적지 않는다 — 숫자를 미리 적어두면 구현이 그 숫자를 향해 끌려간다.

```json
"verify": {
  "enabled": true,
  "meta": {
    "cohort": "core", "calls": 146, "merged_from": 163, "stocks": 35,
    "horizons": [5, 20, 60], "primary": 20,
    "entry": "next_trading_close", "unit": "trading_days",
    "population": 329,
    "excluded": {"bot": 138, "asset": 52, "bot_and_asset": 24,
                 "duplicate": 13, "conflict": 4},
    "generated": "2026-08-17 07:30"
  },
  "summary": {
    "h20": {"judged": 133, "pending": 13, "failed": 0,
            "hit": null, "hit_rate": null,
            "avg_excess": null, "median_excess": null,
            "bullish": 132, "bearish": 14}
  },
  "stocks": [
    {"name": "SK하이닉스", "ticker": "000660", "market": "KR", "bench": "코스피",
     "calls": 24, "low_sample": false,
     "h20": {"judged": null, "hit": null, "hit_rate": null, "avg_excess": null}}
  ],
  "calls": [
    {"stock": "SK하이닉스", "market": "KR", "ticker": "000660",
     "date": "2026-06-12", "entry_date": "2026-06-15", "entry": null,
     "stance": "bullish", "type": "position", "conflict": false,
     "sources": [{"sharer": "…", "snippet": "…"}],
     "h5":  {"ret": null, "bench": null, "excess": null, "hit": null},
     "h20": {"ret": null, "bench": null, "excess": null, "hit": null},
     "h60": null}
  ]
}
```

**크기**: `calls` 146건 × (스니펫 120자 + 수치) ≈ **100~150KB**. 현재 `kb.<hash>.json` 5.7MB 대비 2~3% 증가로 무시 가능하다.

`low_sample` 은 `calls < 5` 인 종목에 붙는다(§6.3).

## 6.3 UI — `검증` 탭

§3.2 분포상 **전체 요약이 주인공, 종목 랭킹은 보조**다. 화면 위계를 그렇게 잡는다.

### 구성
1. **헤더 스코어보드** — 판정 133건 기준 적중률·평균 초과수익. `강세 132 · 약세 14` 와 `판정 대기 13` 을 같은 줄에 병기
2. **구간 토글** — 5일 / **20일**(기본) / 60일. h60 선택 시 "판정 대기 91건" 을 경고색으로 표시
3. **종목 랭킹 테이블** — **콜 5건 이상 7종목만 기본 노출**. 종목 / 콜 수 / 적중 / 적중률 / 평균 초과수익, 정렬 가능
4. **접이식** — `＋ 표본 부족 28종목 (58콜)` 을 접어두고, 펼치면 회색 처리된 채로 표시
5. **행 펼침** — 그 종목의 콜 목록(날짜·방향·초과수익 배지·당시 스니펫) + 종목 탭으로 점프
6. **종목 카드 요약 칩** — 기존 종목 탭 카드에 `✅ 20일 적중 n/m · 초과 ±x.x%p`. `low_sample` 종목은 칩 대신 `표본 n건` 만 표시해 적중률을 아예 노출하지 않는다

### 정직성 장치 (필수)
이 화면은 오독되기 쉽다. 세 가지를 데이터가 아니라 **UI에 못 박는다**.

1. **표본 부족 격리** — `calls < 5` 인 28종목은 기본 랭킹에서 빼고 접이식으로 내린다. 회색 + "표본 부족" 배지. 어떤 정렬에서도 상위로 올라오지 않는다.
2. **강세 편향 명시** — 헤더에 `강세 132 · 약세 14` 를 항상 병기. 이 지표가 사실상 *강세 의견의 초과수익 검증* 임을 숨기지 않는다.
3. **판정 대기 분리** — pending을 분모에서 빼고 별도 카운트로 노출. 적중률이 성숙 구간만의 값임을 드러낸다.

추가로 헤더 하단에 한 줄 각주를 고정한다: *"발화 다음 거래일 종가 진입, 거래일 기준 구간, 지수 대비 초과수익. 투자 권유가 아닙니다."*

### 탭 노출 제어
`hub_template.html` 의 `data-tab="verify"` 버튼은 기본 `style="display:none"` 으로 두고, **`KB.verify?.enabled === true` 일 때만 JS가 노출**한다. 데이터가 없거나 수집이 통째로 실패한 빌드에서는 탭 자체가 나타나지 않는다.

> 참고: 기존 `data-tab="chat"` 버튼(`hub_template.html:562`, `:617`)은 `display:none` 인 채 이를 되돌리는 JS가 없어 **영구 비활성** 상태다. verify 탭은 같은 실수를 반복하지 않도록 노출 조건을 명시적으로 구현하고 테스트한다.

## 7. 실패 모드

| 상황 | 처리 |
|---|---|
| 특정 종목 가격 수집 실패 | 그 종목 콜만 `h*: null` + `failed` 카운트. 빌드 계속 |
| 벤치마크 수집 실패 | 해당 시장 콜을 절대수익만으로 표기하고 `bench_missing:true`. hit은 절대 부호 판정 |
| fdr/yfinance 전량 실패 | `verify: {"enabled": false, "reason": "..."}`. 탭 자동 숨김. 빌드 성공 |
| `price_cache.json` 손상·파싱 실패 | 캐시 무시하고 전량 재수집 (`ParseCache` 와 동일한 폴백) |
| `chat_kb.json` 부재 | `verify` 키 미생성. 기존 `_merge_chat_kb` 와 동일하게 조용히 생략 |
| `build_verify` 내부 예외 | `try/except` 로 격리 + `build.verify_error` 기록. **허브 빌드는 절대 깨지지 않는다** |

기존 `_merge_chat_kb()` 가 실패를 삼키고 `chat_merge_error` 를 남기는 패턴과 동일하게 맞춘다.

## 8. 테스트

`tests/test_verify.py` (신규) — 전부 네트워크 없이 고정 픽스처로 돈다.

| # | 대상 | 검증 내용 |
|---|---|---|
| 1 | `extract_calls` | **고정 픽스처**(`tests/fixtures/chat_kb_mini.json`)로 봇 제외·ASSET 제외·중복 병합·충돌 표시 4가지 규칙을 각각 검증 |
| 2 | `judge_call` 진입일 | 금요일 발화 → 월요일 진입. 휴장일 연속 → 다음 개장일 |
| 3 | `judge_call` 구간 | h20이 **거래일** 20개 뒤인지(달력일 아님) |
| 4 | `judge_call` 미성숙 | `entry_idx + h > len-1` → `null` (0 아님) |
| 5 | `judge_call` 산식 | 초과수익 = 종목수익 − 벤치수익, bearish는 부호 반전 hit |
| 6 | 벤치마크 asof | 벤치 시계열에 exit_date가 없을 때 그 이전 최근 거래일 사용 |
| 7 | `aggregate` | pending·conflict·failed가 분모에서 빠지는지, `low_sample` 플래그 |
| 8 | 실패 격리 | `fetch_prices` 가 던져도 `build_verify` 가 `enabled:false` 반환 |
| 9 | 캐시 | 증분 이어붙이기, `v` 불일치 시 전량 무효화, 손상 파일 폴백 |

**골든 스냅샷을 실제 `chat_kb.json` 에 묶지 않는다.** `chat_kb.json` 은 카톡 export가 들어올 때마다 갱신되므로, 실측 수치(146콜 등)를 단언하면 데이터 갱신마다 CI가 빨갛게 변한다. 대신:
- **로직 테스트**: 전부 `tests/fixtures/chat_kb_mini.json` 픽스처 기준 — 데이터 갱신과 무관
- **정합성 테스트**(실제 파일 대상, 수치 무관): `calls == merged_from − duplicate − conflict`, 모든 콜에 `ticker` 존재, `judged + pending + failed == calls`, `hit_rate` 가 0~100 범위. 관계식만 검증하므로 데이터가 늘어도 통과한다.

이 스펙 §3의 실측 수치(329/163/150/146 등)는 **2026-08-17 시점 스냅샷**이며 테스트 단언 대상이 아니다.

## 9. 작업 순서

1. `hublib/verify.py` — `extract_calls` + 테스트 1 (네트워크 없음, 실측 163/150/4 로 검증)
2. `judge_call` + `aggregate` + 테스트 2~7
3. `fetch_prices` + 캐시 + 테스트 8~9
4. `render.py` 배선 + `.gitignore` + CI 캐시 스텝
5. `hub_template.html` — 검증 탭 + 노출 조건 + 종목 카드 칩
6. `README.md` 스키마 표에 `verify` 행 추가

1~3단계까지는 CI에 아무 영향이 없고, 4단계에서 처음으로 빌드 시간이 늘어난다.

## 10. 범위 밖 (후속 과제)

- 발화 시점 마커가 찍힌 **주가 차트** (SVG 자체 렌더) — 2차
- **목표주가 179건** 검증 (단위 정규화 33건 필요: 달러/만원/원/무단위)
- **actions 1,916건** 검증 (종목 필드 부재 → 추출 단계 필요)
- 리포트 본문 종목 언급 검증
- 발화자별 성적표 — **의도적으로 범위 밖**. 표본 2~63건으로 통계적 유의성이 없고 커뮤니티 리스크가 이익보다 크다.

## 11. 알려진 한계 (문서에 남길 것)

1. **강세 편향** — 약세 콜이 **14건**뿐이라 하락 판단 능력은 사실상 측정되지 않는다.
2. **표본 규모** — 종목당 콜 **중앙값 2건**, 5건 이상은 35종목 중 **7개**뿐이다. 종목별 적중률은 경향 참고용이지 실력 추정치가 아니다.
3. **기간 편중** — 2026-06에 47건(32%)이 몰려 있다. 5개월치 데이터라 특정 국면의 성격이 결과에 크게 반영된다.
4. **h60 미성숙** — 60일 구간은 146건 중 55건만 판정 가능하다. 시간이 지나야 채워진다.
5. **stance 추출 정확도** — `bullish/bearish` 라벨 자체가 생성기의 판정이다. 라벨이 틀리면 검증도 틀린다. 근거 스니펫을 항상 함께 노출해 독자가 직접 확인할 수 있게 하는 이유다.
6. **거래 비용·슬리피지 미반영** — 종가 진입/종가 청산 가정이다.
