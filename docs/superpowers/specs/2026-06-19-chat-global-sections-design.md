# 채팅 전역 섹션 탭 (A 후속)

- 날짜: 2026-06-19
- 상태: 설계 승인 → 구현 계획 대기
- 선행: 1단계(채팅 근거 정확도, `feat/chat-evidence-accuracy`) 완료·머지됨.

## 1. 배경

채팅 전역 데이터가 `knowledge_base.json`의 `chat` 섹션에 병합돼 있고 `window.DATA.chat`으로 주입되지만(확인됨), **UI에 전혀 노출되지 않는다**. 1단계는 종목 카드의 채팅 근거만 다뤘다.

`D.chat` 보유 데이터: `actions` 635 · `strategy` 374 · `targets` 81 · `news` 1,467 · `readings` 33 · `qna` 6.

## 2. 목표 / 비목표

### 목표
새 "💬 채팅" 탭으로 채팅 전역 데이터(전략·목표가·액션·뉴스·교육·Q&A)를 노출한다.

### 비목표 (이번 제외)
- `merge_hub.py`·`build_hub.py` 변경 — `D.chat` 이미 주입됨, 클라이언트 렌더만.
- 2단계 생성기(원문 보존), D 테마 결합, `sharer` 실명 프라이버시.

## 3. 설계 (`hub_template.html`만 변경)

### 3.1 라우팅 / 탭
- `TABS` 배열(L654 `['home','sectors',...]`)에 `'chat'` 추가.
- nav 2곳에 채팅 탭 추가: side-nav(`#tabswrap`/`#tabs`)와 하단 `#bnav`. 기존 `.tab[data-tab]` 마크업을 복제해 `data-tab="chat"`, 라벨 "💬 채팅". (탭 클릭은 기존 위임 핸들러 L663-664가 `showTab` 호출)
- 뷰 컨테이너: `<div class="view" id="view-chat"></div>` 추가(기존 view-* 옆 L571-578).
- 초기 렌더: L1859 일괄 렌더 줄에 `renderChatView()` 추가(다른 뷰와 동일 패턴 — `showTab`은 보이기/숨기기만 하므로 init에서 1회 렌더).
- `showTab`에 chat 특수처리 불필요(graph/trade 같은 예외 아님).

### 3.2 레이아웃 (`renderChatView()`)
- **점프 칩 바 고정(중요 — 문서 window 스크롤 환경)**: 페이지는 뷰 내부 스크롤 컨테이너가 없고 **문서(window)가 스크롤**된다(`showTab` L661 `window.scrollTo`). 기존 **`.topbar`가 `position:sticky; top:0; z-index:60`(약 56px)**로 이미 있으므로, 점프 칩은 `top:0`이 아니라 **`top: <topbar 높이>`(약 56px) 오프셋** + `z-index < 60`(topbar 아래에 붙음)으로 고정. 전략·목표가·액션·뉴스·교육·Q&A 앵커 점프.
- **앵커 점프 오프셋**: 점프 시 `sec-title`이 sticky topbar+칩 뒤로 가리지 않도록 각 `sec-title`(또는 앵커 타깃)에 `scroll-margin-top: <topbar+칩 높이>` 적용(또는 JS `scrollIntoView` 후 오프셋 보정). `showTab`의 `window.scrollTo(top:0)`와는 별개 경로.
- 섹션 순서: 🧭 전략(374) → 🎯 목표가(81) → 💡 액션(635) → 📰 뉴스(1,467) → 📚 교육(33) → ❓ Q&A(6).
- 각 섹션: 기존 `sec-title` 패턴 + 초기 N개 + **더보기 10개씩**(기존 `CHAT_MORE=10` 상수 L934 재사용 — 새 상수 금지). 모든 리스트 **렌더 시 date 역순 정렬, 불변 패턴**(`[...arr].sort(...)` — 원본 `D.chat` 미변경; 저장 데이터는 date 오름차순).
- 초기 표시: 전략 6 · 목표가 12 · 액션 8 · 뉴스 6 · 교육 6 · Q&A 전부(6).

### 3.3 섹션별 렌더
| 섹션 | 필드 | 렌더 |
|---|---|---|
| 전략 | emoji,title,desc,date,sharer | 카드. `title`+메타 표시, 긴 `desc`는 **인라인 펼침**(클릭 토글) |
| 목표가 | stock,value(문자열),unit,date,sharer | 행. 종목은 `data-stock`(클릭→종목탭, 기존 document click 위임 L1110-1116), `value`는 **문자열**("510")이므로 숫자 가정 금지, `unit` 공란(11/81건) **fallback**(빈 문자열이면 단위 생략) |
| 액션 | kind,text,date,sharer | `kind` **3종 do/watch/dont** 각각 **색/아이콘 구분** 리스트 (watch 포함 필수) |
| 뉴스 | date,title,outlet,url | 최신순, 제목+`outlet` **외부 링크**(`target=_blank`), 더보기 |
| 교육 | tag,title,body,date,sharer | 카드. `title`+`tag`, 긴 `body` 인라인 펼침 |
| Q&A | q,q_by,q_date,a,a_by,a_date | 문답 쌍(6건 전부) |

### 3.4 인터랙션 / 결정
- 긴 텍스트(전략 `desc`·교육 `body`)는 잘라 표시 + **인라인 펼침**. **새 모달 안 만듦**(1단계 `#chatModal`은 멘션 구조 전용이라 재사용 부적합, 범용 모달은 YAGNI).
- 더보기: 1단계와 동일하게 `data-*` 속성 + 위임 핸들러. 기존 `data-stock`(document click 위임 L1110-1116)·`data-chat-*`(1단계 L1224-1263)와 충돌 없는 **새 접두사 `data-cg-*`**(예: `data-cg-sec`, `data-cg-shown`) — 기존 `data-cg-*` 0건 확인.
- 목표가 종목 칩은 `data-stock` 재사용(클릭 시 종목 탭 이동 — 의도된 동작).
- 정렬은 렌더 시 클라이언트에서, **불변 패턴**(`[...arr].sort(...)`, 원본 `D.chat` 미변경 → merge_hub 무변경).

## 4. 테스트
JS라 단위테스트 인프라 없음 → **빌드 스모크 + playwright 비주얼**.
- 스모크: `python build_hub.py --src . --out hub.html --json knowledge_base.json` 후 `hub.html`에 `view-chat`·`renderChatView`·`data-cg-sec`·점프칩 마커 존재.
- playwright: 채팅 탭 전환 → 6개 섹션 렌더, 점프 칩 클릭 이동, 더보기, sticky 고정, 인라인 펼침, 목표가 종목 클릭→종목탭. 콘솔 에러 없음(favicon 제외).

## 5. 파일 변경
- `hub_template.html`만: `TABS`에 chat / nav 2곳 탭 / `view-chat` div / `renderChatView` + 더보기 핸들러 / init 렌더 줄 / sticky 점프칩 CSS.
- (변경 없음) `merge_hub.py`, `build_hub.py`, `chat_kb.json`.

## 6. 리스크 / 주의
- **뉴스 1,467건**: 반드시 초기 N + 더보기(전량 DOM 방지).
- **점프 칩 sticky(결정 완료)**: 문서 window 스크롤 환경 + 기존 `.topbar`(sticky top:0, z-index:60, ~56px). 칩은 `top:~56px` 오프셋 + `z-index<60`(topbar 아래). 앵커 타깃은 `scroll-margin-top` 보정. (§3.2 참조)
- **더보기 속성 충돌 회피**: 기존 `data-stock`(L1110-1116 위임)·`data-chat-*`(1단계 L1224-1263)와 다른 접두사 `data-cg-*` 사용.
- **데이터 타입 주의**: `targets.value` 문자열·`unit` 일부 공란(fallback); `news.url` 전건 존재(외부 링크 안전); **`news.stocks`/`news.themes`는 JSON 문자열(`'[]'`)이라 배열 아님 → 렌더하지 않음**(뉴스는 date/title/outlet/url만).
- nav 마크업: 기존 `.tab` 항목 구조를 그대로 복제(아이콘/라벨/data-tab) — plan에서 정확한 마크업 확인.
