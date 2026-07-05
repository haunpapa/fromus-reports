# 여러 카톡방 통합 아카이브 (Multi-room merge) — 설계

- 작성일: 2026-07-05
- 상태: 설계 승인 대기(spec review 전)
- 관련 파일: `generator/update_archive.py`, `generator/chat_to_kb.py`, `generator/test_parse.py`, `generator/refresh.sh`

## 1. 목표

지금은 카톡 export **한 개 파일**만 파싱하고 모든 산출물을 **덮어쓴다**. 방을 바꾸면 이전 방 산출물이 사라진다. 여러 대화방의 메시지를 **하나의 통합 아카이브로 누적·보존**하고, 그 결과를 지금과 동일하게 공개 허브(`chat_kb.json` → CI → Pages)로 배포한다.

### 확정된 요구사항 (브레인스토밍 결과)
- **누적/보존**: 여러 방을 합쳐 유지. 방을 바꿔도 이전 방 데이터가 사라지지 않는다.
- **방별 분리 불필요**: 출력물은 방을 구분하지 않는다(하나의 메시지 풀). *단, 내부 귀속 정확도를 위해 방 태그는 내부적으로만 유지한다.*
- **공개 배포 포함**: 통합본을 `chat_kb.json`으로 커밋·push → 공개 허브에 게시. (다른 방 실명·대화가 공개될 수 있음을 인지하고 진행. 익명화는 별도 후속 과제.)
- **입력 = Downloads 자동 스캔**: 기존처럼 `~/Downloads`·현재폴더의 `KakaoTalk_*`를 스캔하되, **여러 방을 자동 병합**한다.

## 2. 현재 동작 (as-is)

1. `find_input()` (`update_archive.py:163`) — cwd·`~/Downloads`에서 `KakaoTalk_*.txt|.csv` 중 **mtime 최신 1개**만 선택.
2. `parse_csv()` / `parse()` — 파일 1개 → `msgs`(파일마다 `idx` 0..N).
3. `link_records(msgs)` — 링크 추출. 제목 없을 때 **idx 이웃**(`i+off`, `off∈{1,-1,2,-2,3,-3}`)에서 보충 (`update_archive.py:228`, `sender` 일치 가드 존재).
4. `strategy(msgs)` — 메시지별 독립 처리(순서 무관).
5. `aggregate` / `ontology` / `dedup` — 순서 무관.
6. `chat_to_kb.build(msgs, links, sig)` (`update_archive.py:666`) — `chat_kb.json` 생성. QnA에서 **idx forward 근접 스캔**(`chat_to_kb.py:157`, `range(idx+1, idx+6)`)으로 교사 응답 매칭. **sender/room 가드 없음.**
7. 모든 산출물 `open(path,"w")` — **전량 덮어쓰기**. `chat_kb.json`만 리포 루트, 나머지(`온톨로지_데이터/`·뷰어 HTML·jsonl)는 `generator/.gitignore` 제외.

### 교차 메시지(idx 인접) 의존 지점 — 전수 조사 결과
| 위치 | 내용 | 방 병합 시 리스크 |
|---|---|---|
| `update_archive.py:228` | link 제목 보충: `idx.get(i+off)`, `nb["sender"]==r["sharer"]` 가드 | A방 링크가 B방 인접 메시지에서 제목 오귀속 (동명이인 시) |
| `chat_to_kb.py:157-158` | QnA 응답: `range(idx+1, idx+6)`의 교사 메시지 | A방 질문이 B방 교사 응답으로 오귀속 |
| `update_archive.py:214,217` | 메시지 **내부** `lines` 스캔 | 무관(단일 메시지 내부) — 변경 없음 |
| `attribute_stocks()` (`:348`) | 단일 `body` | 무관 — 변경 없음 |

### date 범위(`msgs[0]/msgs[-1]`) 의존 지점
| 위치 | 내용 |
|---|---|
| `update_archive.py:605` | `date_from=msgs[0]["date"]`, `date_to=msgs[-1]["date"]` (온톨로지 뷰어 meta) |
| `chat_to_kb.py:173` | `"from"=msgs[0]`, `"to"=msgs[-1]` (**공개 chat_kb.json** build meta) |

## 3. 채택 접근 — ① 방별 최신 export + 방 경계 보존

Downloads의 `KakaoTalk_*`를 **파일명에서 방 이름을 추출해 방별 그룹핑 → 방마다 mtime 최신 1개**만 파싱. 카톡 export는 그 방의 전체 히스토리 스냅샷이므로 방별 최신 1개면 그 방은 완전 보존된다. 각 방 메시지를 idx 공간에서 **연속 배치**하고, 근접 스캔 2곳에 **방 경계 가드**를 추가한다.

### 기각한 대안
- **② 모든 스냅샷 union + 내용 dedup + 시간순**: 최대 보존이지만 스냅샷 누적 시 매 실행마다 전량 파싱(무한 증가·느림), 시간순 인터리빙이라 방 경계 처리가 더 복잡. 카톡 트리밍 손실 방어는 실무상 불필요.
- **③ stateful 병합 저장소**: 상태 손상 위험·복잡도. 현재 규모에 과함(YAGNI).

## 4. 상세 설계

### 4.1 입력 — `find_input()` → `find_inputs()` (복수 반환)
- 시그니처: `find_inputs(argv=None) -> list[str]`.
- **명시 인자 우선**: `argv[1:]` 중 `.txt|.csv` 실존 경로가 **하나 이상**이면 그 리스트를 그대로 반환(방 그룹핑 생략, 사용자 명시 존중).
- 인자 없으면: cwd·`~/Downloads`에서 `KakaoTalk_*.txt|.csv` glob → **방별 그룹핑 → 방마다 mtime 최신 1개** → 리스트 반환.
- 하나도 없으면 `[]` 반환. (main에서 기존과 동일한 안내 후 종료.)
- 기존 `find_input` 단수 시그니처를 참조하는 테스트는 `find_inputs`로 이관하거나 `find_input`을 `find_inputs()[:1]` 얇은 래퍼로 유지(테스트 호환).

### 4.2 방 이름 추출 — `room_of(path) -> str`
- 파일명 규칙: `KakaoTalk_Chat_<room>_<YYYY-MM-DD-HH-MM-SS>.(csv|txt)` (실데이터: `KakaoTalk_Chat_2026 프롬어스_2026-05-20-20-33-17.csv`).
- 정규식: `^KakaoTalk_Chat_(.+)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(?:csv|txt)$` → group(1) = 방 이름. (greedy `.+` + 끝 앵커된 타임스탬프 → 마지막 타임스탬프를 ts로 정확히 분리.)
- **폴백**(패턴 불일치, 주로 txt): basename에서 확장자만 제거한 문자열을 방 키로 사용 → 그 파일이 자기 자신의 그룹이 되어 **항상 포함**(누락 방지). txt는 best-effort.

### 4.3 파싱·병합·idx 재부여
- 각 파일: 확장자로 `parse_csv`/`parse` 분기(기존 `update_archive.py:586` 로직 재사용).
- 각 메시지에 내부 태그 `m["room"] = room_of(file)` 부여.
- **정렬(결정론)**: 방 키 기준 사전순 정렬 → 각 방 내부는 파싱 순서(=export의 시간순) 유지. 방끼리 이어붙임. *결정론적 순서 = chat_kb.json 커밋 diff 노이즈 최소화.*
- 이어붙인 뒤 **전역 `idx` 재부여**: `for i,m in enumerate(merged): m["idx"]=i`. (link_records/strategy/chat_to_kb가 재부여된 idx를 일관되게 사용.)
- 결과: 한 방의 메시지는 idx 공간에서 **연속(contiguous)** → 근접 스캔이 방 내부에 머무름. 방 경계에서만 가드가 작동.
- dedup: 방별 최신 1파일이므로 방 내부 중복 없음. 방 간 동일 `(date,time,sender,body)`는 우연이며 서로 다른 방이므로 **유지**(제거 안 함). 별도 dedup 패스 불필요.

### 4.4 방 경계 근접 가드 (정확도 핵심)
- **`update_archive.py:228` link_records**: 이웃 후보에 방 일치 조건 추가. `idx` 맵(`:223`)에 원 메시지도 있으므로:
  ```python
  nb = idx.get(i+off)
  if nb and nb["room"]==idx[i]["room"] and nb["sender"]==r["sharer"] and not URLpat.search(nb["body"]):
  ```
- **`chat_to_kb.py:157` QnA**: forward 스캔에 방 일치 조건 추가.
  ```python
  for j in range(m["idx"]+1, min(m["idx"]+6, len(msgs))):
      nb = by_idx.get(j)
      if nb and nb.get("room")==m.get("room") and nb["sender"] in TEACHERS:
  ```
  - `room`이 `chat_to_kb.build`까지 흐르도록 `update_archive.py`가 넘기는 `msgs`가 `room` 키를 포함(4.3에서 부여). `build()`는 `room`을 **출력에 넣지 않음**(내부 가드 전용) → chat_kb.json은 방 무관 유지.
  - `.get("room")` 사용 → room 없는 레거시/직접호출도 안전(둘 다 None → 동일 취급, 기존 동작 보존).

### 4.5 date 범위 min/max 수정 (2곳)
- 그룹 정렬로 `msgs[0]/msgs[-1]`가 전역 최소/최대가 아님. 두 곳 모두 전체 date의 min/max로:
  - `update_archive.py:605`: `date_from=min(m["date"] for m in msgs)`, `date_to=max(...)`.
  - `chat_to_kb.py:173`: `"from"=min(...)`, `"to"=max(...)` (빈 방어: msgs 비면 기존 빈 스키마 분기 유지 `:29`).

### 4.6 채널 meta 파생 (로컬 뷰어 전용)
- `update_archive.py:605`의 `"channel":"프롬어스 오픈카톡(정규반)"` 하드코딩 제거.
- 방 목록 파생: 방 1개면 그 이름, N개면 `f"{첫방} 외 {N-1}개"`. `meta["rooms"]=sorted(set(m["room"] for m in msgs))` 추가.
- **영향 범위 한정**: `channel`은 `update_archive.py` meta(온톨로지 뷰어 HTML, gitignore 제외)에만 존재. **공개 `chat_kb.json`의 build meta에는 channel 필드가 없음**(`chat_to_kb.py:171-174` 확인) → 허브 배포엔 영향 없음.

## 5. 데이터 흐름 (to-be)

```
~/Downloads/KakaoTalk_Chat_<방>_<ts>.csv  (여러 방)
   │  find_inputs(): 방별 최신 1개 리스트
   ▼
[room_of → 방 태그] → parse_csv/parse 각 파일
   │  방 키 사전순 + 방 내부 파싱순으로 concat → idx 재부여
   ▼
merged msgs (m["room"] 내부 태그 보유, idx 연속)
   ├─ link_records  (방 경계 가드)
   ├─ strategy/aggregate/ontology/dedup (순서 무관)
   └─ chat_to_kb.build (QnA 방 경계 가드, date min/max)
        ▼
     chat_kb.json (방 무관 통합본) → refresh.sh 커밋·push → CI → Pages
```

## 6. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `generator/update_archive.py` | `find_input`→`find_inputs`+`room_of` 신설; `main()` 다파일 파싱·병합·idx 재부여; `link_records` 방 가드(:228); meta date min/max·channel 파생(:605) |
| `generator/chat_to_kb.py` | QnA 방 가드(:157); build meta from/to min/max(:173) |
| `generator/test_parse.py` | find_inputs 방별최신/방추출/병합·idx재부여/방경계가드 테스트 추가 |
| `generator/refresh.sh` | 다파일 처리 시 변경 로그 문구 정도(선택). 핵심 로직은 update_archive가 담당 |
| `generator/README.md` | 다방 병합 동작·주의 문구 갱신 |

## 7. 알려진 한계 (명시)
- `fromus_taxonomy`의 `CORE`/`TEACHERS`/멤버 별명은 프롬어스 기준. 다른 방 멤버는 '일반 멤버'로 처리되고 별명→정식멤버 매칭은 안 될 수 있음. 종목 별칭(`ENTITIES`)은 전역이라 종목 인식은 동작.
- `members` 카운트는 sender 이름 기준 → 동명이인/여러 방의 동일 이름은 1명으로 합산.
- 공개 배포 시 다른 방 실명·대화 노출(사용자 인지·수용). 익명화는 후속 과제.
- txt export 파일명 규칙이 CSV와 달라 방 그룹핑은 best-effort(폴백=파일별 그룹). 실데이터는 CSV라 주 경로는 견고.

## 8. 테스트 계획 (`test_parse.py` 확장, 기존 통과 유지)
- **find_inputs**: 두 방(A_old, A_new, B_new) 임시 파일 → A는 최신만·B 포함 = 2개, 방별 최신 선택 검증. 출력형 CSV(`뉴스_전체아카이브.csv`) 미선택.
- **room_of**: `KakaoTalk_Chat_2026 프롬어스_2026-05-20-20-33-17.csv` → "2026 프롬어스"; 폴백 파일 → basename.
- **병합·idx**: 두 방 파싱 병합 후 idx 0..N-1 연속·유일, 방 내부 연속성.
- **방 경계 가드**: A방 질문 바로 뒤(idx+1) B방 교사 메시지 배치 → QnA 미매칭 확인. link 제목 오귀속 미발생.
- **date min/max**: 방 정렬로 msgs[0]가 전역 최소가 아닌 케이스에서 from/to가 실제 min/max.
- 기존 `test_parse.py`·`build/test_merge_hub.py` 통과 유지.

## 9. 하위호환·롤아웃
- 방이 1개뿐이면(현재 프롬어스만) 동작·출력은 기존과 사실상 동일(idx 재부여는 단일 방이라 순서 불변, date min/max=기존값).
- `find_input` 래퍼 유지로 기존 호출부/테스트 호환.
- `refresh.sh` 인터페이스 불변(인자 없으면 자동, 인자 주면 그 파일). CI 미실행(로컬 전용)은 그대로.
