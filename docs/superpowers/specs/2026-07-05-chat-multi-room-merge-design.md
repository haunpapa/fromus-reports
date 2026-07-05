# 여러 카톡방 통합 아카이브 (Multi-room merge) — 설계

- 작성일: 2026-07-05
- 상태: spec review 1회 반영 완료 → 사용자 최종 검토 대기
- 관련 파일: `generator/update_archive.py`, `generator/chat_to_kb.py`, `generator/test_parse.py`, `generator/refresh.sh`, `generator/README.md`

## 0. 변경 이력
- v1(초안): "방별 최신 1파일 선택" 접근. 다관점 spec review에서 (a) 동일 표시명 방 충돌 시 방 유실, (b) txt 스냅샷 중복 누적, (c) 래퍼/명시인자/standalone 경로의 가드·idx 붕괴 등 6 HIGH + 8 MEDIUM 결함 확인.
- v2(현재): **"전체 파일 union + 내용 기반 중복제거"**로 병합 메커니즘 교체. 방 태그는 파일 선택이 아니라 **근접 가드/정렬 용도로만** 사용. 지적 전량 반영.

## 1. 목표

지금은 카톡 export **한 개 파일**만 파싱하고 모든 산출물을 **덮어쓴다**. 방을 바꾸면 이전 방 산출물이 사라진다. 여러 대화방의 메시지를 **하나의 통합 아카이브로 누적·보존**하고, 그 결과를 지금과 동일하게 공개 허브(`chat_kb.json` → CI → Pages)로 배포한다.

### 확정된 요구사항 (브레인스토밍 결과)
- **누적/보존**: 여러 방을 합쳐 유지. 방을 바꿔도/추가해도 이전 방 데이터가 사라지지 않는다. **(어떤 파일 선택 로직도 방 하나를 통째로 탈락시켜선 안 된다.)**
- **방별 분리 불필요**: 출력물은 방을 구분하지 않는다(하나의 메시지 풀). *단, 내부 귀속 정확도를 위해 방 태그는 내부적으로만 유지한다.*
- **공개 배포 포함**: 통합본을 `chat_kb.json`으로 커밋·push → 공개 허브에 게시. (다른 방 실명·대화가 공개될 수 있음을 인지하고 진행. 익명화는 별도 후속 과제.)
- **입력 = Downloads 자동 스캔**: 기존처럼 `~/Downloads`·현재폴더의 `KakaoTalk_*`를 스캔하되, **여러 방을 자동 병합**한다.

## 2. 현재 동작 (as-is)

1. `find_input()` (`update_archive.py:163`) — cwd·`~/Downloads`에서 `KakaoTalk_*.txt|.csv` 중 **mtime 최신 1개**만 선택.
2. `parse_csv()` / `parse()` — 파일 1개 → `msgs`(파일마다 `idx` 0..N).
3. `link_records(msgs)` — 링크 추출. 제목 없을 때 **idx 이웃**(`i+off`, `off∈{1,-1,2,-2,3,-3}`)에서 보충 (`update_archive.py:227-231`, idx 맵은 `:223`, `sender` 일치 가드 존재).
4. `strategy(msgs)` — 메시지별 독립 처리(순서 무관). 시그널 레코드(`:403-408`)는 `msg_idx/date/time/sharer/entities/themes/stance/type/stocks/snippet/full/core/teacher` 필드만 — **room 없음**.
5. `aggregate` / `ontology` — 순서 무관.
6. `chat_to_kb.build(msgs, links, sig)` (`update_archive.py:667`) — `chat_kb.json` 생성. QnA에서 **idx forward 근접 스캔**(`chat_to_kb.py:157`, `range(idx+1, idx+6)`, `by_idx`는 `:34`)으로 교사 응답 매칭. **sender/room 가드 없음.**
7. 모든 산출물 `open(path,"w")` — **전량 덮어쓰기**. `chat_kb.json`만 리포 루트, 나머지(`온톨로지_데이터/`·뷰어 HTML·jsonl)는 `generator/.gitignore` 제외.

### 교차 메시지(idx 인접) 의존 지점 — 전수 조사
| 위치 | 내용 | 방 병합 시 리스크 |
|---|---|---|
| `update_archive.py:227-231` | link 제목 보충: `idx.get(i+off)`, `nb["sender"]==r["sharer"]` 가드 | A방 링크가 B방 인접 메시지에서 제목 오귀속(동명이인 시) |
| `chat_to_kb.py:157-158` | QnA 응답: `range(idx+1, idx+6)`의 교사 메시지 | A방 질문이 B방 교사 응답으로 오귀속 |
| `update_archive.py:214,217` | 메시지 **내부** `lines` 스캔 | 무관(단일 메시지 내부) — 변경 없음 |
| `attribute_stocks()` (`:348`) | 단일 `body` | 무관 — 변경 없음 |
| `strategy()`→mention 경유(`chat_to_kb.py:56-63`) | 시그널 1개=메시지 1개, 단일 body 귀속 | **인접 메시지를 끌어오지 않음** → 크로스룸 오귀속 구조 아님(단, room 가드 대상도 아님, §4.4) |

### 순서/결정론 의존 지점 (방 병합과 무관·기존 이슈)
| 위치 | 내용 | 비고 |
|---|---|---|
| `chat_to_kb.py:89` `for x in sset` | set 반복 순서 → stocks dict 삽입순 → `json.dump(indent=1)` 키 순서 → 바이트 diff | `match_stocks`가 set 반환(`fromus_taxonomy.py`). PYTHONHASHSEED 미고정 시 프로세스마다 chat_kb.json 키 순서 변동. **§4.7에서 sorted()로 고정.** |
| `update_archive.py:561-568` dedup tie-break | date+time 동률 시 원본 순서 의존 | 산출물 `uniq`는 **로컬 뷰어 HTML(gitignore)** 로만 감 → chat_kb.json diff와 무관. 변경 없음. |

### date 범위(`msgs[0]/msgs[-1]`) 의존 지점
| 위치 | 내용 |
|---|---|
| `update_archive.py:605` | `date_from=msgs[0]["date"]`, `date_to=msgs[-1]["date"]` (온톨로지 뷰어 meta) |
| `chat_to_kb.py:173` | `"from"=msgs[0]`, `"to"=msgs[-1]` (**공개 chat_kb.json** build meta) |

### chat_kb.json 하류 소비자 (영향 없음 확인 대상)
| 소비자 | 위치 | room 사용 | 판정 |
|---|---|---|---|
| `merge_hub.py` (comention/co_edges) | `:34,67,72` 키 `(date, sharer, snippet[:40])` | 안 읽음 | **코드 무변경.** 단 다방 데이터가 comention 정확도에 주는 영향은 §7 한계로 명시 |
| `hublib/render.py` `_merge_chat_kb` | `:41-63` | 안 읽음 | 코드 무변경·영향 없음 |
| CI 트리거 | `.github/workflows/build.yml:13` (`chat_kb.json` push paths) | — | 통합본 커밋도 동일하게 CI 정상 발동 |

## 3. 채택 접근 — ② 전체 파일 union + 내용 기반 중복제거 (v2)

Downloads의 `KakaoTalk_*`를 **전부 파싱**하고, 메시지를 **내용 키 `(date,time,sender,body)`로 중복제거**해 통합한다. **파일을 이름으로 선택/탈락시키지 않으므로**(v1의 방 유실·txt 중복 문제 원천 제거), 카톡이 방마다 발행하는 전체-히스토리 스냅샷들이 여러 개 있어도 union+dedup으로 정확히 "각 메시지 1개"로 수렴한다. 방 태그(`room`)는 **파일 선택이 아니라 근접 가드·정렬 용도로만** 사용한다.

- 카톡 export = 그 방의 전체 히스토리 스냅샷 → 같은 방을 여러 번 내보내도 union+dedup으로 최신 superset과 동일 결과, 손실 없음.
- 서로 다른 방은 내용 키가 겹치지 않으므로(동일 `(date,time,sender,body)`는 천문학적으로 희박) 각자 보존.
- **방 유실 불가**: 이름 기반 파일 탈락이 없으므로 요구사항(누적/보존)을 구조적으로 보장.

### 기각한 대안
- **v1 방별 최신 1파일**: 동일 표시명 방 충돌 시 방 유실, txt 스냅샷 중복. (spec review에서 확정 기각.)
- **stateful 병합 저장소**: 상태 손상 위험·복잡도. YAGNI.

### 성능
- union-all은 매 실행마다 모든 스냅샷 파싱. 현재 Downloads에 프롬어스 CSV ~15개(~25MB). 순수 파이썬 파싱 ~1–3초로 실무상 무해(네트워크 해제는 기존대로 `resolve_cache.json` 캐시). 스냅샷이 수백 개로 증가하면 (path,size,mtime) 파싱 캐시를 후속 도입(§10). **housekeeping 권장**: union+dedup 특성상 같은 방의 오래된 스냅샷은 최신본의 부분집합이므로 Downloads에서 지워도 무손실이며 속도만 개선됨(강제 아님).

## 4. 상세 설계

### 4.1 입력 — `find_input()` → `find_inputs()`
- 시그니처: `find_inputs(argv=None) -> list[str]`.
- **명시 인자 우선**: `argv[1:]` 중 `.txt|.csv` 실존 경로가 **하나 이상**이면 **그 경로들(복수 허용)**을 반환.
- 인자 없으면: cwd·`~/Downloads`의 `KakaoTalk_*.txt|.csv` glob **전부**(출력형 CSV는 `KakaoTalk_` prefix 제한으로 자연 배제) → 경로 dedup → 리스트 반환. **최신 1개로 좁히지 않는다.**
- 하나도 없으면 `[]`.
- **레거시 래퍼**(하위호환): 문자열/None 계약 + "mtime 최신 1개" 의미를 **모두** 보존해야 함.
  ```python
  def find_input(argv=None):
      r = find_inputs(argv)
      return max(r, key=os.path.getmtime, default=None)   # str | None, 최신 1개
  ```
  - **주의**: `find_inputs()[:1]`(리스트) 반환 금지 — `test_parse.py:51`(`assertEqual(find_input(...), new)` 문자열 기대), `:59`(`os.path.basename(picked)` str 기대)를 깨뜨림. `max(..., default=None)`는 문자열/None 계약과 mtime-최신 의미를 동시 보존.

### 4.2 방 태그 — `room_of(path) -> str` (선택/탈락 아님, **가드·정렬용 태그**)
- 파일명 규칙: `KakaoTalk_Chat_<room>_<YYYY-MM-DD-HH-MM-SS>.(csv|txt)` (실데이터: `KakaoTalk_Chat_2026 프롬어스_2026-05-20-20-33-17.csv`).
- 정규식: `^KakaoTalk_Chat_(.+)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(?:csv|txt)$` → group(1) = 방 표시명.
- 폴백(패턴 불일치, 주로 txt): basename에서 **끝 타임스탬프 패턴(`_\d{4}-\d{2}-...`)이 있으면 제거한 문자열**, 없으면 확장자만 제거한 문자열을 태그로. (같은 방의 여러 날짜 txt 스냅샷이 같은 태그로 묶이도록 타임스탬프를 최대한 벗겨냄.)
- **태그는 근접 가드/정렬에만 쓰이고 파일을 탈락시키지 않는다** → 표시명 충돌이 나도 **데이터 유실은 없다**(§7 한계: 충돌 시 두 방이 한 태그로 묶여 근접 가드가 그 경계를 못 막는 정확도 저하만 발생).

### 4.3 파싱·병합·중복제거·idx 재부여 (**모든 입력 경로 공통 단계**)
자동 스캔이든 명시 인자든 **동일하게** 아래를 거친다(명시 인자 경로도 예외 없이 태깅·재부여):
1. 각 파일: 확장자로 `parse_csv`/`parse` 분기. 각 메시지에 `m["room"]=room_of(file)`, `m["src_file"]=file` 부여.
2. **정렬(결정론적·chronological 재구성)**: 파일을 **mtime 오름차순(오래된→최신)** 으로 처리하며, `(date,time,sender,body)` 내용 키가 **처음 등장할 때만** 채택(keep-first). 누적 스냅샷 특성상 오래된 파일=이른 히스토리, 최신 파일=그 뒤 증분 → keep-first가 올바른 시간순을 재구성.
3. **방 태그별 그룹 순서**: 통합 리스트를 방 태그로 그룹핑하되, 방 순서는 **각 방의 최초 등장 메시지 datetime 오름차순**으로(신규/최신 방이 뒤에 붙어 chat_kb.json diff 안정). 같은 방 내부는 2단계에서 얻은 순서 유지.
4. **전역 `idx` 재부여**: `for i,m in enumerate(merged): m["idx"]=i`. → 한 방 메시지가 idx 공간에서 **연속** → 근접 스캔이 방 내부에 머무름.
5. 결과 msgs는 `room`·`src_file`·연속 `idx` 보유 상태로 downstream(link_records/strategy/chat_to_kb)에 전달.
- dedup 근거: **내용 키 기반**이라 파일명/방 태그와 무관하게 동작 → CSV 재스냅샷·txt 이름 변형 모두 수렴. (v1의 "방별 최신이라 dedup 불필요" 전제는 폐기.)

### 4.4 방 경계 근접 가드 (정확도)
- **`update_archive.py:227-231` link_records**: 이웃 후보에 방 일치 조건 추가. 두 가드 모두 **방어적 `.get`** 사용(견고성 규칙 통일, room 미태깅 직접호출/테스트도 안전):
  ```python
  nb = idx.get(i+off)
  if nb and nb.get("room")==idx[i].get("room") and nb["sender"]==r["sharer"] and not URLpat.search(nb["body"]):
  ```
- **`chat_to_kb.py:157` QnA**: forward 스캔에 방 일치 조건 추가.
  ```python
  for j in range(m["idx"]+1, min(m["idx"]+6, len(msgs))):
      nb = by_idx.get(j)
      if nb and nb.get("room")==m.get("room") and nb["sender"] in TEACHERS:
  ```
  - `room`이 `build`까지 흐르도록 §4.3에서 msgs에 실림. `build()`는 `room`을 **출력에 넣지 않음** → chat_kb.json은 방 무관 유지.
  - `.get("room")` → room 없는 레거시/**단일 파일**은 둘 다 None으로 동일 취급(기존 동작 보존). **주의**: 이 None-동일취급은 *단일 방/단일 파일*에서만 "안전"하며, 다파일인데 room 태깅을 건너뛰면 가드가 무력화됨 → 그래서 §4.3을 **모든 경로 공통 단계**로 못박음.
- **mention(signals) 경로는 방 가드 대상이 아님**: `strategy()` 시그널 레코드에는 room이 없고(`:403`), `build`의 mention은 `for s in signals`(`:56-63`)로 처리됨. 다만 mention은 **시그널 1개=메시지 1개, 단일 body 귀속**이라 인접 메시지를 끌어오지 않음 → 크로스룸 오귀속 구조가 아님(가드 불필요). 향후 확장 대비로 `strategy()` 레코드에 `"room":m.get("room")` 추가는 **선택**.

### 4.5 date 범위 min/max 수정 (2곳)
그룹 정렬로 `msgs[0]/msgs[-1]`가 전역 최소/최대가 아님:
- `update_archive.py:605`: `date_from=min(m["date"] for m in msgs)`, `date_to=max(...)`.
- `chat_to_kb.py:173`: `"from"=min(...)`, `"to"=max(...)`. (빈 msgs는 `:29` 빈 스키마 분기가 선점 → 안전.)

### 4.6 채널 meta 파생 + 뷰어 헤더 보존 (로컬 뷰어 전용)
- `update_archive.py:605`의 `"channel":"프롬어스 오픈카톡(정규반)"` 하드코딩 제거.
- 방 목록 파생 문자열을 **`meta["channel"]`에 재대입**: 방 1개면 그 이름, N개면 `f"{첫방} 외 {N-1}개"`. `meta["rooms"]=sorted(set(m["room"] for m in msgs))` 추가.
- **뷰어 헤더 호환 확인**: 뷰어 JS는 `m.channel`을 "채널" 헤더 행에 능동 표시(`프롬어스_온톨로지_뷰어.html` 렌더). 따라서 channel을 **제거만 하면 undefined로 헤더가 깨짐** → 반드시 파생 문자열을 `meta["channel"]`에 재대입. `meta["rooms"]` 신규 키는 뷰어가 키 이름으로 직접 읽는 구조라 **무시(무해)**.
- **공개 영향 없음**: `channel`은 update_archive meta(뷰어 HTML, gitignore)에만 존재. 공개 `chat_kb.json` build meta에는 channel 필드 없음(`chat_to_kb.py:171-174`).

### 4.7 결정론 하드닝 (chat_kb.json diff 안정)
- `chat_to_kb.py`의 set 반복부(대표: `:89 for x in sset`, 그리고 `match_stocks`/`match_themes` 결과를 순회해 dict에 삽입하는 지점)를 **`sorted(...)`로 감싸** stocks/themes 삽입 순서를 결정론화. → PYTHONHASHSEED와 무관하게 chat_kb.json 키 순서 안정.
- §4.3의 "결정론적 순서"는 **메시지 배치 순서 + 이 set 정렬**까지 포함해 성립. (신규 방 삽입 위치에 따라 diff 크기는 달라질 수 있음 — 방 순서를 최초등장 datetime 기준으로 잡아 최소화하되, 완전 0은 아님.)

### 4.8 standalone `__main__` 경로 대응
- `chat_to_kb.py`의 `__main__`은 `메시지_구조화원문.jsonl`을 재로드해 `build()`를 직접 호출. 이 jsonl에 room이 없으면 standalone 실행 시 QnA 가드가 None==None으로 무력화.
- **수정**: `update_archive.py:660-661`의 jsonl write dict에 `"room": m.get("room")` (그리고 `"src_file"` 선택) 추가 → standalone 경로도 방 가드 유지.
- 프로덕션 경로(`refresh.sh` → `main()` → 인메모리 msgs → `build`)는 jsonl 왕복을 안 거치므로 원래 안전.

## 5. 데이터 흐름 (to-be)

```
~/Downloads/KakaoTalk_*  (여러 방·여러 스냅샷)
   │  find_inputs(): 전부 반환(이름 기반 탈락 없음)
   ▼
[room_of 태그 + src_file] → parse_csv/parse 각 파일
   │  mtime 오름차순 처리 + (date,time,sender,body) keep-first dedup
   │  방 그룹(최초등장 datetime 순) concat → 전역 idx 재부여
   ▼
merged msgs (room·src_file·연속 idx)
   ├─ link_records   (방 경계 .get 가드)
   ├─ strategy/aggregate/ontology (순서 무관; mention은 단일-msg 스코프)
   └─ chat_to_kb.build (QnA 방 경계 가드, date min/max, set 정렬)
        ▼
     chat_kb.json (방 무관 통합본) → refresh.sh 커밋·push → CI(build.yml) → Pages
        · merge_hub / render._merge_chat_kb: room 안 읽음(무변경). comention 정확도 영향은 §7
```

## 6. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `generator/update_archive.py` | `find_input`→`find_inputs`+레거시 래퍼(§4.1)·`room_of`(§4.2) 신설; `main()` 다파일 파싱·태깅·keep-first dedup·방그룹 concat·idx 재부여(§4.3); `link_records` 방 `.get` 가드(§4.4); meta date min/max·channel 파생 재대입·rooms(§4.5·4.6); jsonl write에 room 추가(§4.8) |
| `generator/chat_to_kb.py` | QnA 방 `.get` 가드(§4.4); build meta from/to min/max(§4.5); set 반복 `sorted()` 결정론(§4.7) |
| `generator/test_parse.py` | find_inputs(전부 반환)·find_input 래퍼(mtime 최신·문자열)·room_of(정규매칭+폴백)·keep-first dedup·방경계 가드·**통합경로(find_inputs→parse→병합→build) idx연속·room보유**·date min/max 테스트 추가; 기존 assert 계약 유지 |
| `generator/refresh.sh` | 안내 문구: "인자 없이 실행=다방 자동병합, 파일 명시=그 파일만" |
| `generator/README.md` | 다방 병합 동작·"파일 인자 시 단일 방만" 주의·housekeeping 갱신 |
| (무변경·영향없음 확인) | `merge_hub.py`·`hublib/render.py`(`_merge_chat_kb`)·`.github/workflows/build.yml` — room 미사용 |

## 7. 알려진 한계 (명시)
- **동일 표시명 방 충돌**: 서로 다른 물리적 방이 같은 표시명이면 한 `room` 태그로 묶임 → 데이터 유실은 없으나(union+dedup) 그 경계에서 근접 가드가 안 걸려 QnA/제목 오귀속 가능. (방 이름을 다르게 두면 회피.)
- **txt 다중 스냅샷**: txt는 파일명 규칙이 CSV와 달라 폴백 태그가 스냅샷마다 갈릴 수 있음 → 같은 방이 여러 태그로 나뉘어 근접 가드 정확도 저하 가능(내용 dedup으로 **중복/유실은 없음**). 실데이터는 CSV라 주 경로는 견고.
- **merge_hub comention 정확도**: `merge_hub.py`의 co_edges/comention 키가 `(date, sharer, snippet[:40])`뿐이고 chat_kb mention에 room이 없음 → 다른 방 동명이인이 같은 날 동일 앞40자 스니펫을 남기면 서로 다른 방 종목이 잘못 엮일 수 있음. (허용 불가 시 후속: mention에 내부 room 필드 + merge_hub 키에 room 포함, 공개 출력 미포함.)
- **mention 방 가드 부재**: signals에 room이 없어 mention 귀속은 방 경계 가드 대상이 아님(단, 단일-msg 스코프라 크로스룸 오귀속은 실현되지 않음).
- **taxonomy**: `CORE`/`TEACHERS`/멤버 별명은 프롬어스 기준. 다른 방 멤버는 '일반 멤버', 별명→정식멤버 매칭 안 될 수 있음(종목 별칭은 전역이라 동작).
- **members 카운트**: sender 이름 기준 → 동명이인/여러 방 동일 이름은 1명으로 합산.
- **공개 배포**: 다른 방 실명·대화 노출(사용자 인지·수용). 익명화 후속 과제.

## 8. 테스트 계획 (`test_parse.py` 확장, 기존 통과 유지)
- **find_inputs**: 여러 파일(다방·동일방 다스냅샷) 모두 반환됨(이름 기반 탈락 없음), 출력형 CSV 미포함.
- **find_input 래퍼**: 리스트가 아니라 **문자열/None** 반환, 그리고 **mtime 최신** 선택(기존 `test_arg_priority_and_prefix` 계약 유지). 사전순 첫 원소 아님.
- **room_of**: `KakaoTalk_Chat_2026 프롬어스_...csv`→"2026 프롬어스"; 폴백 파일→타임스탬프 제거 태그.
- **keep-first dedup**: 같은 방 2스냅샷(old⊂new) 병합 시 메시지 유일·시간순, 개수=union.
- **방 경계 가드**: A방 질문 바로 뒤(idx+1)에 B방 교사 메시지 배치 → QnA 미매칭. link 제목 오귀속 미발생. room 미태깅 직접호출에서도 KeyError 없음(.get).
- **통합 경로**: `find_inputs→parse→병합·idx재부여→build` 실행해 by_idx가 0..N-1 연속이고 각 msg에 room 보유, QnA 가드가 실제 경로에서 작동함을 검증(단위 msgs 주입이 아닌 end-to-end).
- **date min/max**: 방 그룹 정렬로 msgs[0]가 전역 최소가 아닌 케이스에서 from/to가 실제 min/max.
- 기존 `test_parse.py`·`build/test_merge_hub.py` 통과 유지.

## 9. 하위호환·롤아웃
- 방이 1개뿐이면(현재 프롬어스만) 동작·출력 사실상 동일(단일 방이라 idx 순서 불변, date min/max=기존값, dedup no-op).
- `find_input` 래퍼(mtime 최신·문자열/None)로 기존 호출부/테스트 호환.
- **`refresh.sh`/README 주의(중요)**: `refresh.sh "$@"` 전달 특성상 **파일을 인자로 명시하면 그 파일만 처리(=단일 방)**, **다방 자동병합은 인자 없이 실행(자동 스캔)** 해야 함. README.md의 "파일 지정" 예시에 이 의미를 명시하고, 다방 사용자는 인자 없이 실행하도록 안내.

## 10. 후속 과제(비범위)
- 스냅샷 수백 개 대비 (path,size,mtime) 파싱 캐시.
- 공개 익명화/본문 PII 마스킹(`build(public=True)` 경로 활성화).
- 동일 표시명 충돌/ txt 태그 안정화를 위한 방 인스턴스 식별자(내부 `src_file` 기반) 도입.
- merge_hub comention의 room-aware 키(내부 필드).
