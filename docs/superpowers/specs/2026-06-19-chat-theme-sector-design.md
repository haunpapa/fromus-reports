# 채팅 테마 ↔ 섹터 결합 (D)

- 날짜: 2026-06-19
- 상태: 설계 승인(C안) → 구현 계획 대기
- 선행: 1단계(근거 정확도)·A(전역 섹션, 탭은 숨김)·봇 제외 완료.

## 1. 배경

채팅 테마 20개와 리포트 섹터가 **같은 분류 체계**라 이름이 정확히 일치한다(14개: 반도체·메모리, AI 전력·원전·ESS, 양자컴퓨터, 조선·방산, 금융·금리수혜 등). 채팅 탭은 숨김 상태이므로, **섹터를 볼 때 그 테마의 채팅 분위기가 연결되어** 보이게 한다.

채팅 stance 집계가 의미 있는 신호임을 확인(봇 제외 후): 반도체·메모리 의견 337건(그중 stance 부여 223 — 강세 166·약세 14·관망 43, 나머지 중립), AI 전력·원전·ESS 의견 51건(강세 24·관망 5). **의견 수(337)와 stance 합(223)은 다른 수**임에 주의 — 라벨 모집단을 의견 수로 통일한다(§3.2).

## 2. 목표 / 비목표

### 목표 (C안 — 풍부)
리포트 섹터 카드에 이름이 매칭되는 채팅 테마의 **stance 집계 + 채팅 논의 종목 칩 + 대표 의견 미리보기**를 결합한다.

### 비목표 (이번 제외)
- 채팅 전용 테마 6개(에너지·정유, 가상자산·디지털자산, 전기차·자율주행, 원자재·안전자산, K푸드·소비재, 엔터·미디어) — 매칭되는 리포트 섹터가 없음. 후속에서 필요 시.
- 2단계 생성기, `sharer` 프라이버시.

## 3. 설계

### 3.1 `merge_hub.py` — 테마 집계
현재 `kb.chat.themes`는 **이름 리스트**(L108 `list(chat.get("themes",{}).keys())`)뿐 → **상세 dict**로 교체.

merge 끝(종목 `chat` 블록 생성 후, 이미 봇 제외·정렬됨)에서 **kb 종목 dict를 구성**(`by_name = {s["name"]: s for s in kb.get("stocks", [])}`)하고, 각 채팅 테마의 `stocks`를 순회해 종목 `chat.opinions`를 모아 집계:

```jsonc
kb.chat.themes = {
  "반도체·메모리": {
    "opinions_count": int,               // 봇 제외 의견(view/position) 총수 — 카드 라벨의 N
    "stocks": [name…],                   // 채팅 테마 종목 (chat_kb)
    "stance": { "bullish":int, "bearish":int, "watch":int },  // 아래 opinions 전체의 stance 재카운트(상한 적용 전)
    "opinions": [ { date, sharer, stance, snippet, stock } ]  // 대표 의견 최신순·≤THEME_OP_KEEP(8), 각 의견에 출처 stock 부착
  }, …
}
```
- **집계 소스**: 각 테마 `stocks` 이름으로 `by_name[nm]` 조회(`STOCK_BY_NAME`은 JS 전용이라 Python엔 없음 → kb 종목 dict 직접 구성). 그 종목의 `chat.opinions`(이미 봇 제외·view/position) 수집, 종목명을 `stock` 필드로 부착(`{**op, "stock": nm}`).
- **stance 합산 = opinions 기반 재카운트(확정)**: 수집한 의견 **전체**의 `stance`를 카운트(대표 의견 ≤8 상한 적용 **전** 전체 기준). 대표 의견 리스트와 동일 소스라 화면 검증 가능. 종목 `chat.stance`(stance_summary)는 type 무관 집계라 **사용 안 함**.
- `opinions_count` = 봇 제외 의견 총수(상한 전). `stance` 삼중값 합 ≤ `opinions_count`(나머지는 neutral/mixed).
- **THEME_OP_KEEP=8**(신규 상수, OPINION_KEEP과 구분)은 **대표 의견 리스트에만** 적용, `stance`·`opinions_count`는 전체 기준.
- 불변: 원본 `chat_kb`·종목 chat 객체 변경 없이 새 구조 생성.
- 멱등성: `_strip_prior_chat`이 `kb.pop("chat")` 통째 제거하므로 새 구조도 자동 정리.

### 3.2 `hub_template.html` — `sectorCard`
`s.theme`이 `D.chat.themes`(dict)에 있으면 채팅 근거를 렌더. **하위호환 가드 필수**(기존 빌드는 `chat.themes`가 이름 리스트): `const tmap = (D.chat && !Array.isArray(D.chat.themes)) ? (D.chat.themes||{}) : {}; const ct = tmap[s.theme];` — 옵셔널 체이닝만으론 리스트를 dict로 오인하니 `Array.isArray` 가드를 쓴다.
- **카드 본문**(종목 칩 아래): `💬 채팅 의견 ${ct.opinions_count}건 · 강세 X·약세 Y·관망 Z` — **N(의견 수)과 stance 같은 모집단**(의견). + **채팅 논의 종목 칩**(`ct.stocks`, `data-stock` → 클릭 시 종목 탭). 섹터의 `stocks`와 별개로 채팅에서 논의된 종목.
- **`scard-detail`(펼침)**: 💬 **대표 의견 미리보기** — `ct.opinions`를 `날짜 · [종목] · 발언자 · snippet(120자)` 행으로(최신순). 카드 본문은 가볍게 유지하고 상세는 펼침에.
- `D.chat.themes`에 없는 섹터(채팅 전용 아님, 일별 동적 섹터 12개)는 채팅 블록 없음(기존 그대로).

### 3.3 데이터 / 결정
- 정렬: 대표 의견 date 역순(불변 `[...].sort`).
- 종목 칩은 기존 `data-stock` 위임(document click 핸들러, `e.target.closest('[data-stock]')`) 재사용 — 종목 탭 이동. (라인은 drift되므로 식별자 기준)
- 상한: 대표 의견 테마당 ≤8(`THEME_OP_KEEP`). KB 크기: 14테마 × 8 ≈ 112 의견, 미미.

## 4. 테스트
- `build/test_merge_hub.py` 확장: 테마 집계 — stance = opinions 재카운트(상한 전 전체), `opinions_count` 정확, 봇 제외, 대표 의견에 `stock` 부착·최신순·상한(≤8 적용은 대표 리스트만), **이름 매칭 테마만 집계(비매칭 채팅 전용 6개 미집계)**, **한 종목이 여러 매칭 테마에 속하면 각 테마에 독립 집계**.
- 스모크: 빌드 후 `knowledge_base.json`의 `chat.themes`가 dict이고 `반도체·메모리`에 stance/opinions 존재.
- playwright: 섹터 탭 → 매칭 섹터(반도체·메모리) 카드에 채팅 stance + 종목 칩, 펼침에 대표 의견. **실제 `getComputedStyle`/렌더로 검증**(이전 hidden 교훈). 콘솔 에러 없음.

## 5. 파일 변경
- `merge_hub.py`: 테마 집계 함수 + `kb.chat.themes` 상세화.
- `hub_template.html`: `sectorCard`에 채팅 근거 블록.
- `build/test_merge_hub.py`: 테마 집계 테스트.
- (변경 없음) `build_hub.py`, `chat_kb.json`.

## 6. 리스크 / 주의
- **stance 합산 = opinions 재카운트로 확정**(§3.1): 수집한 의견 전체의 stance 카운트. 종목 `chat.stance`(stance_summary, type 무관)는 사용 안 함 — 대표 의견 리스트와 화면 숫자가 일치하도록.
- **대표 의견 종목 부착**: 테마 여러 종목의 의견을 합치므로 각 의견이 어느 종목인지 `stock` 필드 필수(안 그러면 맥락 불명).
- **채팅 전용 테마 6개 손실**: 섹터에 없어 노출 안 됨 — 비목표로 명시, 후속.
- **`D.chat?.themes` 옵셔널 체이닝**: 기존 빌드(이름 리스트)와 하위호환 — `Array.isArray`면 무시하고 dict일 때만 사용.
