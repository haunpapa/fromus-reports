# 채팅 테마 ↔ 섹터 결합 (D)

- 날짜: 2026-06-19
- 상태: 설계 승인(C안) → 구현 계획 대기
- 선행: 1단계(근거 정확도)·A(전역 섹션, 탭은 숨김)·봇 제외 완료.

## 1. 배경

채팅 테마 20개와 리포트 섹터가 **같은 분류 체계**라 이름이 정확히 일치한다(14개: 반도체·메모리, AI 전력·원전·ESS, 양자컴퓨터, 조선·방산, 금융·금리수혜 등). 채팅 탭은 숨김 상태이므로, **섹터를 볼 때 그 테마의 채팅 분위기가 연결되어** 보이게 한다.

채팅 stance 집계가 의미 있는 신호임을 확인(봇 제외 후): 반도체·메모리 의견 337(강세 166·약세 14·관망 43), AI 전력·원전·ESS 의견 51(강세 24·관망 5).

## 2. 목표 / 비목표

### 목표 (C안 — 풍부)
리포트 섹터 카드에 이름이 매칭되는 채팅 테마의 **stance 집계 + 채팅 논의 종목 칩 + 대표 의견 미리보기**를 결합한다.

### 비목표 (이번 제외)
- 채팅 전용 테마 6개(에너지·정유, 가상자산·디지털자산, 전기차·자율주행, 원자재·안전자산, K푸드·소비재, 엔터·미디어) — 매칭되는 리포트 섹터가 없음. 후속에서 필요 시.
- 2단계 생성기, `sharer` 프라이버시.

## 3. 설계

### 3.1 `merge_hub.py` — 테마 집계
현재 `kb.chat.themes`는 **이름 리스트**(L108 `list(chat.get("themes",{}).keys())`)뿐 → **상세 dict**로 교체.

merge 끝(종목 `chat` 블록 생성 후, 이미 봇 제외·정렬됨)에서 각 채팅 테마의 종목 `chat.opinions`를 모아 집계:

```jsonc
kb.chat.themes = {
  "반도체·메모리": {
    "count":  int,                       // chat_kb themes[t].count
    "stocks": [name…],                   // 채팅 테마 종목 (chat_kb)
    "stance": { "bullish":int, "bearish":int, "watch":int },  // 종목 opinions stance 합산(봇 제외)
    "opinions": [ { date, sharer, stance, snippet, stock } ]  // 테마 종목 의견 합산·최신순·≤THEME_OP_KEEP(8), 각 의견에 출처 stock 부착
  }, …
}
```
- 집계 소스: 각 테마 `stocks`의 `STOCK_BY_NAME` 대응 종목 `chat.opinions`(이미 봇 제외·view/position). 종목명을 의견에 `stock` 필드로 부착.
- `stance` 합산: 종목 `chat.stance`를 더하거나 opinions의 stance를 카운트(둘 중 일관된 방법, 봇 제외).
- 불변: 원본 `chat_kb`·종목 chat 객체 변경 없이 새 구조 생성.

### 3.2 `hub_template.html` — `sectorCard`
`s.theme`이 `D.chat.themes`에 있으면(`const ct = (D.chat?.themes||{})[s.theme]`) 채팅 근거를 렌더:
- **카드 본문**(종목 칩 아래): `💬 채팅 ${ct.count}회 · 강세 X·약세 Y·관망 Z` + **채팅 논의 종목 칩**(`ct.stocks`, `data-stock` → 클릭 시 종목 탭). 섹터의 `stocks`와 별개로 채팅에서 논의된 종목.
- **`scard-detail`(펼침)**: 💬 **대표 의견 미리보기** — `ct.opinions`를 `날짜 · [종목] · 발언자 · snippet(120자)` 행으로(최신순). 카드 본문은 가볍게 유지하고 상세는 펼침에.
- `D.chat.themes`에 없는 섹터(채팅 전용 아님, 일별 동적 섹터 12개)는 채팅 블록 없음(기존 그대로).

### 3.3 데이터 / 결정
- 정렬: 대표 의견 date 역순(불변 `[...].sort`).
- 종목 칩은 기존 `data-stock` 위임(L1110-1116 문서 click) 재사용 — 종목 탭 이동.
- 상한: 대표 의견 테마당 ≤8(`THEME_OP_KEEP`). KB 크기: 14테마 × 8 ≈ 112 의견, 미미.

## 4. 테스트
- `build/test_merge_hub.py` 확장: 테마 집계 — stance 합산 정확, 봇 제외, 대표 의견에 `stock` 부착·최신순·상한(≤8), 이름 매칭 테마만 집계.
- 스모크: 빌드 후 `knowledge_base.json`의 `chat.themes`가 dict이고 `반도체·메모리`에 stance/opinions 존재.
- playwright: 섹터 탭 → 매칭 섹터(반도체·메모리) 카드에 채팅 stance + 종목 칩, 펼침에 대표 의견. **실제 `getComputedStyle`/렌더로 검증**(이전 hidden 교훈). 콘솔 에러 없음.

## 5. 파일 변경
- `merge_hub.py`: 테마 집계 함수 + `kb.chat.themes` 상세화.
- `hub_template.html`: `sectorCard`에 채팅 근거 블록.
- `build/test_merge_hub.py`: 테마 집계 테스트.
- (변경 없음) `build_hub.py`, `chat_kb.json`.

## 6. 리스크 / 주의
- **stance 합산 출처 일관성**: 종목 `chat.stance`(이미 봇 제외 집계) 합산 vs opinions 재카운트 — 한 방법으로 통일(중복 합산 방지).
- **대표 의견 종목 부착**: 테마 여러 종목의 의견을 합치므로 각 의견이 어느 종목인지 `stock` 필드 필수(안 그러면 맥락 불명).
- **채팅 전용 테마 6개 손실**: 섹터에 없어 노출 안 됨 — 비목표로 명시, 후속.
- **`D.chat?.themes` 옵셔널 체이닝**: 기존 빌드(이름 리스트)와 하위호환 — `Array.isArray`면 무시하고 dict일 때만 사용.
