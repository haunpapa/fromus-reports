# 채팅 근거 정확도 + 인터랙션 교정 (1단계)

- 날짜: 2026-06-19
- 상태: 설계 승인 → 구현 계획 대기
- 범위: 1단계(소비 단계 교정). 2단계(chat_kb 생성기·원문 보존)는 별도 사이클.

## 1. 배경 / 문제

PR #2(`feat: 카카오톡 채팅 온톨로지 ↔ 지식허브 결합`)로 종목 카드에 💬 채팅 근거가
표시되지만, **근거가 해당 종목과 이어지지 않는다**는 사용자 피드백이 있었다.
데이터 진단으로 근본 원인을 확정했다.

| 증거 | 값 | 의미 |
|---|---|---|
| 멘션 복제율 | 3.0× (고유 메시지 876 → 멘션 2,647) | 시황 1개가 평균 3개 종목에 복제 |
| 다종목 중복 귀속 | 453개 메시지(절반↑), 최악 24개 종목 | "특징 종목: 마이크론, 테슬라…" 한 줄이 AMD·TSMC·구글… 동시 삽입 |
| `type=research`(시황) | 2,103개 = 전체 79% | 데일리 시황. 실제 의견(view+position)은 21% |
| snippet에 종목명 포함 | 38%만 | 긴 시황이 180자로 잘려 종목명조차 없음 |

**메커니즘**: `chat_kb.json` 생성기(리포에 없음 = 2단계 과제)가 데일리 시황에서
언급된 모든 종목명을 뽑아 각 종목에 같은 글을 복제한다. `renderChat`은 날짜순
최근 5개만 보여줘서 거의 모든 종목 카드가 동일한 시황으로 도배된다.

`merge_hub.py`는 종목명 **정확 일치**(`cstocks.get(nm)`)로만 채팅 블록을 붙이므로
병합 단계의 버그는 아니다. 다만 `chat_kb.json`에는 이미 멘션을 구분할 수 있는
`type` 필드(`research` / `view` / `position`)가 들어 있어, **소비 단계에서 즉시 교정 가능**하다.

## 2. 목표 / 비목표

### 목표 (사용자 피드백 #1~#4)
1. **#1 정확도**: 종목 카드 근거를 "실제 의견" 중심으로 재구성, 종목 무관 시황 노이즈 제거.
2. **#2 모달**: 멘션 클릭 시 모달로 전문 + 맥락(함께 언급 종목·발언자 타임라인·관련 뉴스).
3. **#3 뉴스 정렬**: 공유 뉴스를 최신순으로.
4. **#4 더보기**: 초기 N개 + 10개씩 추가 로드.

### 비목표 (이번 spec 제외 — 후속 사이클)
- 전역 "시장 시황 타임라인" 섹션, Q&A/전략/액션/목표가 전용 뷰 (A의 전역 섹션)
- D 테마 단위 결합
- `chat_kb.json` 생성 파이프라인 / 원문 보존 (2단계)
- `apply_hub_patch.py`(1회용 부트스트랩) 제거 — 후속 정리

## 3. 설계

### 3.1 데이터 흐름 (변경점 2곳)

```
chat_kb.json (변경 없음 — 기존 type 필드 활용)
  └─> merge_hub.py        [강화: 분류·필터·co_stocks·정렬]
  └─> build_hub.py        [변경 없음 — merge 훅 그대로]
  └─> hub_template.html   [renderChat 재작성 + 모달 + 더보기 JS]
```

### 3.2 `merge_hub.py` 강화

핵심: 종목별 `chat` 블록을 의견/관련시황/뉴스로 분리하고, 모달용 `co_stocks`를 주입한다.
**불변성 적용 범위(한정)**: 입력 `chat_kb`의 멘션 객체를 변경하지 않고 새 복사본을 만든다(co_stocks 미오염). 단 `merge(kb, chat)`의 **`kb` 인자는 기존 계약대로 in-place 보강**한다(`build_hub.py` L1195가 같은 객체 반환을 가정). → `merge()` 전체를 순수 함수로 재작성하지 않는다(과한 리팩토링 방지).

#### 3.2.1 멘션 분류
- **의견(opinions)**: `type ∈ {view, position}` — 사람이 그 종목 맥락에서 한 발언. 전량 유지(상한 100).
- **관련 시황(market_news)**: `type == research` **이고** 본문에 종목명/티커가 실제 등장하는 것만. (상한 50)
- **버림**: `type == research` 이면서 종목명 미포함 — 도배의 원흉, 카드에서 제외.

```python
OPINION_TYPES = {"view", "position"}
def _is_opinion(m):   return m.get("type") in OPINION_TYPES
def _name_in(m, nm, ticker):
    sn = m.get("snippet", "") or ""
    return (nm in sn) or (bool(ticker) and ticker in sn)
def _sort_desc(items):    # date 역순(키 없어도 안전)
    return sorted(items, key=lambda x: x.get("date", ""), reverse=True)
```

#### 3.2.2 co_stocks (모달 "왜 이 종목에 붙었나")
`merge()` 시작 시 chat 전체 멘션을 1회 순회하여 동일 메시지 → 언급 종목 집합 맵을 만든다.
메시지 키는 진단에서 검증된 `(date, sharer, snippet[:40])`.

```python
def _build_comention_map(cstocks):
    msg2names = defaultdict(set)
    for nm, cs in cstocks.items():
        for m in cs.get("mentions", []):
            key = (m.get("date"), m.get("sharer"), (m.get("snippet","") or "")[:40])
            msg2names[key].add(nm)
    return msg2names
```
각 멘션 복사본에 `co_stocks = sorted(msg2names[key] - {nm})` 주입(자기 자신 제외, 불변 복사).

#### 3.2.3 새 chat 블록 스키마
```jsonc
stock.chat = {
  "count":   int,
  "signals": int,
  "stance":  { "bullish": int, "bearish": int, "watch": int },
  "opinions":     [ { date, sharer, stance, type, snippet, co_stocks:[name…] } ],  // 최신순, ≤100
  "market_news":  [ { date, sharer, stance, type, snippet, co_stocks:[name…] } ],  // research∩종목명, 최신순, ≤50
  "news":         [ { date, title, outlet, url } ],                                // 최신순, ≤50 — 실제 chat_kb 필드만
  "targets":      [ … ]   // 기존 유지
}
```
- **news 객체는 실제 chat_kb.json 필드(`date,title,outlet,url`)만 보유**한다. `sharer/stocks/themes`는 데이터 원천에 없으므로 소비 코드가 신뢰하지 않는다(필요 시 2단계 생성기 과제).
- 기존 `recent` 키는 `opinions`로 대체(이름·의미 변경). `market_news` 신규.
- `_strip_prior_chat`은 `stock.chat`·`kb.chat`을 통째 제거하므로 **멱등성 유지**(신규 키도 자동 정리).
- 채팅 전용 종목(`chat_only`)도 동일 스키마 적용.

### 3.3 종목 카드 — `renderChat(s)` 재작성

`hub_template.html`의 `renderChat`(현 L922~929)을 교체한다. 출력 구성:

- **헤더**: `💬 N회 · 강세 a · 약세 b · 관망 c`
- **💡 의견(최신순)**: 초기 3건 렌더 + 남으면 `＋ 의견 N건 더보기`(10개씩)
- **📰 관련 시황 M건 ▾**: 기본 접힘, 펼치면 초기 5건 + 더보기
- **📰 뉴스(최신순)**: 초기 4건 + 더보기
- **의견/관련시황 멘션 클릭 → 모달**. **뉴스는 모달을 열지 않고 기존 외부 링크(`url`) 그대로**(#3은 정렬만 변경, 클릭 동작은 외부 링크 유지).

더보기·접기·모달은 정적 `innerHTML`로 데이터를 다 박지 않고, **기존 전역 맵 `STOCK_BY_NAME`(hub_template L1184, name→stock O(1) 조회; `D = window.DATA`(L624)로부터 구축)에서 종목명으로 조회**해 핸들러가 추가 렌더한다(카드 HTML 비대화 방지).
- **data- 속성명 충돌 회피(중요)**: 기존 L1070의 document 레벨 위임 핸들러가 `data-stock`을 가로채 stocks 탭 이동 + `renderStocks()` 전체 재렌더를 수행한다. 채팅 더보기/모달 트리거는 반드시 **별도 속성**(`data-chat-stock`, `data-chat-kind`(`opinion`|`market`), `data-chat-idx`)을 쓴다. `data-chat-idx`는 **merge가 저장한 `opinions`/`market_news` 배열의 절대 인덱스**이며, `data-chat-kind`로 배열을 선택한다(더보기로 추가 렌더되는 항목도 동일 절대 인덱스 사용).

### 3.4 모달 (신규 — `.rmodal` **CSS 클래스만** 재사용)

⚠️ 기존 `.rmodal` 인프라(`#reportModal` L602~, `RM` 객체 L1453, `openReport`/`closeReport` L1516~, ESC L1548, 바디 스크롤락 `rmBodyOverflow` L1528)는 **iframe 리포트 뷰어 전용**(`RM.frame.src=file`)이다. 채팅 모달 본문은 iframe이 아니라 innerHTML 콘텐츠이므로 **CSS 클래스만 차용**하고 JS는 다음을 **새로** 만든다:
- 채팅 전용 **별도 모달 DOM 컨테이너** + `openChatModal(stockName, kind, idx)` / `closeChatModal()` (`kind ∈ {opinion, market}` — 뉴스는 모달 없음)
- 데이터 조회: `STOCK_BY_NAME[stockName].chat[kind==='opinion'?'opinions':'market_news'][idx]`
- ESC 핸들러는 **열린 모달(리포트/채팅)을 분기**해 닫는다(기존 `closeReport`와 공존). 바디 overflow 복원 변수는 **공유하지 않고 별도**로 둔다(`rmBodyOverflow` 미공유).

모달 본문:
- 헤더: `💬 채팅 · {종목} · {date} · {sharer} · {stance}`
- 본문: `snippet`(현재 180자). **2단계에서 원문으로 교체할 자리** — 주석/플래그로 표시.
- **함께 언급 종목**: `m.co_stocks` 칩
- **발언자 타임라인**: `STOCK_BY_NAME[stockName].chat.opinions` 중 같은 `sharer`만 날짜순
- **관련 뉴스**: `STOCK_BY_NAME[stockName].chat.news` 상위 몇 건 (외부 링크)

### 3.5 더보기 / 정렬 기본값
- 초기 표시: 의견 3 · 관련시황 0(접힘, 펼치면 5) · 뉴스 4
- 더보기 증분: 10
- 정렬: 의견·관련시황·뉴스 모두 `date` 역순(`merge_hub`에서 저장 시 정렬 → 렌더는 그대로)

## 4. 테스트 전략

프로젝트 컨벤션을 따른다: **stdlib `unittest`**, 픽스처 고정, 네트워크 불필요.
신규 `build/test_merge_hub.py` — 실행 `python build/test_merge_hub.py`. `merge_hub`는 **리포 루트 모듈**이므로 테스트 상단에 `sys.path.insert(0, <repo_root>)` 후 `from merge_hub import merge`(dartlab 테스트와 동일 패턴). 스모크 명령은 루트 cwd 기준.

작은 합성 `chat_kb`/`kb` 픽스처로 다음을 검증:
1. **분류**: 의견은 opinions로, 종목명 포함 research는 market_news로, 종목명 미포함 research는 둘 다에서 제외.
2. **co_stocks**: 동일 메시지가 2개 종목에 있을 때 서로의 이름이 co_stocks에 들어가고 자기 자신은 빠진다.
3. **정렬**: opinions·market_news·news가 date 역순.
4. **상한**: 각 리스트가 상한(100/50/50)을 넘지 않는다.
5. **멱등성**: `merge()`를 2회 적용해도 결과가 동일(누적 없음) — `_strip_prior_chat` 동작.
6. **불변성**: 입력 `chat_kb` 멘션 객체가 변경되지 않는다(co_stocks 미오염).

스모크(수동/CI): `python build_hub.py --src . --out hub.html --json knowledge_base.json` 실행 후
`hub.html`에 `renderChat`·`openChatModal`·더보기 마커가 존재하고 `chat_merged:true`인지 확인.

## 5. 파일 변경
- `merge_hub.py` — 분류·필터·co_stocks·정렬·새 스키마 (강화)
- `hub_template.html` — `renderChat` 재작성 + 채팅 모달 + 더보기/접기 JS
- `build/test_merge_hub.py` — 신규 단위 테스트
- (변경 없음) `chat_kb.json`, `build_hub.py`, `build.yml`
- (이번 미변경) `apply_hub_patch.py` — 직접 수정으로 대체, 제거는 후속 정리

## 6. 리스크 / 주의
- **KB 크기 증가**: 의견 전량 저장(상한 100). 추정 수백 KB~약 1 MB 증가 — 상한으로 관리, 허용 범위.
- **렌더 데이터 의존**(해소됨): `D = window.DATA`(L624)가 전역이고, `STOCK_BY_NAME`(L1184) name→stock 맵이 이미 존재하므로 더보기/모달은 이를 재사용한다.
- **co_stocks 키 충돌**: snippet[:40]이 같은 서로 다른 메시지의 오결합 가능성(낮음). 날짜+발언자로 충분히 분별.
- **2단계 연결점**: 모달 본문의 180자 자리는 2단계에서 원문으로 교체. 스키마에 원문 필드 추가 시 하위호환 유지.
