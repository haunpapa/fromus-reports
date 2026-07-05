# 여러 카톡방 통합 아카이브 (Multi-room merge) — 설계

- 작성일: 2026-07-05
- 상태: spec review 2회 반영 완료 → 사용자 최종 검토 대기
- 관련 파일: `generator/update_archive.py`, `generator/chat_to_kb.py`, `generator/test_parse.py`, `generator/refresh.sh`, `generator/README.md`

## 0. 변경 이력
- **v1(초안)** — "방별 최신 1파일 선택". review에서 (a) 동일 표시명 방 충돌 시 방 유실, (b) txt 스냅샷 중복, (c) 래퍼/명시인자/standalone 경로 붕괴 등 6 HIGH+8 MEDIUM 확인.
- **v2** — "전체 파일 union + 내용 dedup"로 교체. review에서 (d) **초 절단(HH:MM) dedup 키로 같은 분 동일 발화 반복 유실**, (e) **keep-first 시간순 역전** 2 HIGH 신규 결함 확인.
- **v3(현재)** — "**방별 최신 스냅샷 verbatim 채택 + 같은 태그의 겹치지 않는 파일만 fold**". 흔한 경로(방별 최신 1개)는 **dedup을 아예 안 하므로** (d)·(e)가 원천 소멸(유실·역전 없음). 충돌/절단 같은 드문 경로만 content fold로 안전 처리하고 그 한계를 §7에 명시. v1·v2 지적 전량 반영.

## 1. 목표

지금은 카톡 export **한 개 파일**만 파싱하고 모든 산출물을 **덮어쓴다**. 방을 바꾸면 이전 방 산출물이 사라진다. 여러 대화방의 메시지를 **하나의 통합 아카이브로 누적·보존**하고, 그 결과를 지금과 동일하게 공개 허브(`chat_kb.json` → CI → Pages)로 배포한다.

### 확정된 요구사항 (브레인스토밍 결과)
- **누적/보존**: 여러 방을 합쳐 유지. 방을 바꿔도/추가해도 이전 방 데이터가 사라지지 않는다. **어떤 파일 선택 로직도 방 하나를 통째로 탈락시켜선 안 되고(room-level), 흔한 경로에서 메시지를 유실해선 안 된다(message-level).**
- **방별 분리 불필요**: 출력물은 방을 구분하지 않는다(하나의 메시지 풀). *단, 내부 귀속 정확도를 위해 방 태그는 내부적으로만 유지한다.*
- **공개 배포 포함**: 통합본을 `chat_kb.json`으로 커밋·push → 공개 허브에 게시. (다른 방 실명·대화 노출 인지·수용. 익명화는 후속 과제.)
- **입력 = Downloads 자동 스캔**: 기존처럼 `~/Downloads`·현재폴더의 `KakaoTalk_*`를 스캔하되 **여러 방을 자동 병합**한다.

## 2. 현재 동작 (as-is)

1. `find_input()` (`update_archive.py:163`) — cwd·`~/Downloads`에서 `KakaoTalk_*.txt|.csv` 중 **mtime 최신 1개**만 선택.
2. `parse_csv()`(`:140`) / `parse()`(`:185`) — 파일 1개 → `msgs`(파일마다 `idx` 0..N). **`time`은 `ds[11:16]`=HH:MM(초 절단, `:156`)**, txt도 `to24()`로 HH:MM.
3. `link_records(msgs)`(`:204`) — 링크 추출. 제목 없을 때 **idx 이웃**(`i+off`, `off∈{1,-1,2,-2,3,-3}`)에서 보충 (`:227-231`, idx 맵 `:223`, `sender` 가드 존재).
4. `strategy(msgs)`(`:382`) — 메시지별 독립(순서 무관). 시그널 레코드(`:403-408`)는 room 없음.
5. `aggregate`/`ontology` — 순서 무관.
6. `chat_to_kb.build(msgs, links, sig)` (`update_archive.py:667`) — `chat_kb.json` 생성. QnA에서 **idx forward 근접 스캔**(`chat_to_kb.py:157`, `range(idx+1, idx+6)`, `by_idx` `:34`)으로 교사 응답 매칭. **sender/room 가드 없음.**
7. 모든 산출물 `open(path,"w")` — **전량 덮어쓰기**. `chat_kb.json`만 리포 루트, 나머지(`온톨로지_데이터/`·뷰어 HTML·jsonl)는 `generator/.gitignore` 제외.

### 교차 메시지(idx 인접) 의존 지점 — 전수 조사
| 위치 | 내용 | 방 병합 시 리스크 |
|---|---|---|
| `update_archive.py:227-231` | link 제목 보충 `idx.get(i+off)`, `sender` 가드 | A방 링크가 B방 인접에서 제목 오귀속(동명이인) — §4.4 가드 |
| `chat_to_kb.py:157-158` | QnA 응답 `range(idx+1, idx+6)` 교사 메시지 | A방 질문이 B방 교사 응답으로 오귀속 — §4.4 가드 |
| `update_archive.py:214,217` | 메시지 **내부** `lines` 스캔 | 무관(단일 메시지 내부) — 변경 없음 |
| `attribute_stocks()`(`:348`), `strategy()`→mention(`chat_to_kb.py:56-63`) | 단일 body / 시그널 1개=메시지 1개 | 인접 메시지 안 끌어옴 → 크로스룸 구조 아님(가드 불필요·불가, §4.4) |

### 순서/결정론·date 범위 의존 지점
| 위치 | 내용 | 처리 |
|---|---|---|
| `chat_to_kb.py:89` `for x in sset` | set 반복 순서 → stocks dict 삽입순 → `json.dump(indent=1)` 키 순서 → 바이트 diff (PYTHONHASHSEED 미고정) | §4.7 `sorted()` 고정 |
| `update_archive.py:561-568` dedup tie-break | 산출물 `uniq`는 로컬 뷰어 HTML(gitignore)로만 감 | chat_kb.json diff와 무관 — 변경 없음 |
| `update_archive.py:605` | `date_from=msgs[0]`, `date_to=msgs[-1]` (뷰어 meta) | §4.5 min/max |
| `chat_to_kb.py:173` | `"from"=msgs[0]`, `"to"=msgs[-1]` (**공개 chat_kb.json** meta) | §4.5 min/max |

### chat_kb.json 하류 소비자 (영향 없음 확인 대상)
| 소비자 | 위치 | room 사용 | 판정 |
|---|---|---|---|
| `merge_hub.py` comention/co_edges | `:34,67,72` 키 `(date, sharer, snippet[:40])` | 안 읽음 | 코드 무변경. 다방 comention 정확도 영향은 §7 |
| `hublib/render.py` `_merge_chat_kb` | `:41-63` | 안 읽음 | 무변경·영향 없음 |
| CI 트리거 | `.github/workflows/build.yml:13` (`chat_kb.json` paths) | — | 통합본 커밋도 CI 정상 발동 |

## 3. 채택 접근 — ③ 방별 최신 verbatim + content fold (v3)

**핵심 원칙: 흔한 경로에서는 dedup을 하지 않는다.** 방마다 카톡 export는 그 방의 전체 히스토리 스냅샷이므로, 방별로 **최신 스냅샷 1개를 그대로(verbatim) 채택**하면 그 방은 완전하고 파일 순서가 곧 시간순이라 유실·역전이 없다. 파일을 **이름으로 탈락시키지 않기 위해**(v1의 방 유실 방지), 같은 태그에 여러 파일이 있으면 최신을 base로 삼고 **base에 없는 메시지만** 다른 파일에서 fold-in 한다.

- **흔한 경로**(각 방 = 최신 스냅샷 1개): dedup 없음 → 같은 분 동일 발화 반복도 보존(v2 결함 d 소멸), 파일 순서=시간순(v2 결함 e 소멸).
- **드문 경로**(동일 표시명 다른 방 / 방 나갔다 재입장·export 절단으로 base가 완전하지 않음): 같은 태그의 다른 파일에서 겹치지 않는 메시지를 content 기준으로 fold-in → **방/메시지 유실 없음**. 단 이 경로의 content 비교는 초 절단·분 단위라 best-effort(§7).
- 방 태그(`room`)는 **파일 선택이 아니라 근접 가드·정렬 용도**로만 쓰인다.

### 기각한 대안
- v1 방별 최신 1파일(fold 없음): 동일 표시명 충돌 시 방 유실.
- v2 union-all + 전역 내용 dedup: 흔한 경로에까지 dedup을 적용해 초 절단 유실·keep-first 역전 유발.
- stateful 병합 저장소: 상태 손상 위험·복잡도. YAGNI.

### 성능
정확성을 위해 각 태그의 모든 파일을 파싱(base + fold 후보)한다. 현재 Downloads 프롬어스 CSV ~15개(~25MB) 파싱 ~1–3초로 무해(네트워크 해제는 `resolve_cache.json` 캐시). **housekeeping 권장(강제 아님)**: 같은 방 오래된 스냅샷은 최신본의 부분집합이라 Downloads에서 지워도 무손실·속도 개선. 스냅샷 수백 개 대비 (path,size,mtime) 파싱 캐시는 후속(§10).

## 4. 상세 설계

### 4.1 입력 — `find_input()` → `find_inputs()`
- 시그니처: `find_inputs(argv=None) -> list[str]`.
- **명시 인자 우선**: `argv[1:]` 중 `.txt|.csv` 실존 경로가 하나 이상이면 **그 경로들(복수 허용)** 반환.
- 인자 없으면: cwd·`~/Downloads`의 `KakaoTalk_*.txt|.csv` glob **전부**(출력형 CSV는 `KakaoTalk_` prefix로 자연 배제) → 경로 dedup → 리스트. **최신 1개로 좁히지 않는다.**
- 없으면 `[]`.
- **레거시 래퍼**(하위호환, 문자열/None + mtime 최신 의미 **동시** 보존):
  ```python
  def find_input(argv=None):
      r = find_inputs(argv)
      return max(r, key=os.path.getmtime, default=None)   # str | None
  ```
  `find_inputs()[:1]`(리스트) 금지 — `test_parse.py:51`(문자열 기대)·`:59`(`basename(picked)`)를 깨뜨림.

### 4.2 방 태그 — `room_of(path) -> str` (선택/탈락 아님, 가드·정렬용)
- 파일명 규칙: `KakaoTalk_Chat_<room>_<YYYY-MM-DD-HH-MM-SS>.(csv|txt)` (실데이터 `KakaoTalk_Chat_2026 프롬어스_2026-05-20-20-33-17.csv`).
- 정규식: `^KakaoTalk_Chat_(.+)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(?:csv|txt)$` → group(1)=방 표시명.
- 폴백(불일치, 주로 txt): basename에서 끝 타임스탬프 패턴이 있으면 제거, 없으면 확장자만 제거한 문자열.
- 태그는 파일을 탈락시키지 않음 → 표시명 충돌이 나도 **데이터 유실 없음**(fold로 흡수); 충돌 시 두 방이 한 태그로 묶여 근접 가드가 경계를 못 막는 **정확도 저하만** 발생(§7).

### 4.3 병합 알고리즘 (**모든 입력 경로 공통** — 자동 스캔·명시 인자 동일)
명령형 단계로 확정한다:
1. **그룹핑**: `find_inputs()` 결과를 `room_of` 태그로 group_by.
2. **태그별 base + fold**: 각 태그 그룹에서 파일을 mtime 내림차순 정렬.
   - `base` = 최신 파일을 `parse_csv`/`parse`로 파싱한 msgs(**dedup 없이 그대로**, 각 msg에 `room=태그`, `src_file=경로` 태깅). base의 내용 키 집합 `seen` 구성.
   - 나머지 파일(최신→오래된)을 파싱하며 내용 키가 `seen`에 **없는 메시지만** append(+seen 갱신, room/src_file 태깅). → 같은 방 재스냅샷이면 아무것도 안 붙음; 충돌·절단이면 겹치지 않는 메시지만 folded-in.
   - **fold가 실제로 발생한 태그에 한해** 그 그룹 내부를 **`(date, time)` 안정 정렬**(동률=현재 채택 순서 유지)로 시간 역전 보정. **fold가 없으면 정렬하지 않음**(base가 이미 시간순 → verbatim 보존).
3. **방 순서**: 태그 그룹들을 각 그룹 **최초 등장 메시지 datetime 오름차순**으로 concat → `grouped_merged` (신규/최신 방이 뒤에 붙어 chat_kb.json diff 안정).
4. **전역 idx 재부여**: `for i,m in enumerate(grouped_merged): m["idx"]=i`. **최종 idx는 오직 `grouped_merged` 기준** → 한 방 메시지가 idx 공간에서 연속 → 근접 스캔이 방 내부에 머무름.
5. `grouped_merged`(=최종 msgs)를 downstream(link_records/strategy/chat_to_kb)에 전달.

- **내용 키** = `(date, time, sender, body, occ)`. `occ`=한 파일 내에서 그 `(date,time,sender,body)` 튜플의 0-based 등장 순번. → **fold 판정 시** 같은 분 동일 발화의 서로 다른 반복(예: 'ㅋㅋㅋ' 2회)을 구분(초 절단이라 순번으로 보강). 흔한 경로(base verbatim)는 이 키를 base 내부 dedup에 **쓰지 않으므로** 유실 원천 없음.

### 4.4 방 경계 근접 가드 (정확도)
- **`update_archive.py:227-231` link_records** — 두 가드 모두 방어적 `.get`(견고성 통일, room 미태깅 직접호출/테스트도 안전):
  ```python
  nb = idx.get(i+off)
  if nb and nb.get("room")==idx[i].get("room") and nb["sender"]==r["sharer"] and not URLpat.search(nb["body"]):
  ```
- **`chat_to_kb.py:157` QnA**:
  ```python
  for j in range(m["idx"]+1, min(m["idx"]+6, len(msgs))):
      nb = by_idx.get(j)
      if nb and nb.get("room")==m.get("room") and nb["sender"] in TEACHERS:
  ```
  - `room`은 §4.3에서 msgs에 실림. `build()`는 room을 **출력에 안 넣음** → chat_kb.json 방 무관 유지.
  - `.get("room")`의 None-동일취급은 *단일 방/단일 파일*에서만 "안전". 다파일인데 태깅을 건너뛰면 무력화 → §4.3을 **모든 경로 공통 단계**로 못박아 방지.
- **mention(signals) 경로는 가드 대상 아님**: signals에 room 없음(`:403`), mention은 단일-msg 스코프라 인접 메시지 안 끌어옴 → 크로스룸 오귀속 구조 아님. (`strategy()`에 `"room":m.get("room")` 추가는 선택.)

### 4.5 date 범위 min/max (2곳)
그룹 정렬로 `msgs[0]/msgs[-1]`가 전역 최소/최대가 아님:
- `update_archive.py:605`: `date_from=min(m["date"] for m in msgs)`, `date_to=max(...)`.
- `chat_to_kb.py:173`: `"from"=min(...)`, `"to"=max(...)`. (빈 msgs는 `:29` 빈 스키마 분기가 선점.)

### 4.6 채널 meta 파생 + 뷰어 헤더 (로컬 뷰어 전용)
- `update_archive.py:605`의 `"channel":"프롬어스 오픈카톡(정규반)"` 하드코딩 제거 → 방 목록 파생 문자열을 **`meta["channel"]`에 재대입**(방 1개=그 이름, N개=`f"{첫방} 외 {N-1}개"`), `meta["rooms"]=sorted(set(m["room"] for m in msgs))` 추가.
- 뷰어 JS는 `m.channel`을 "채널" 헤더에 능동 표시 → **제거만 하면 undefined로 깨짐** → 반드시 재대입. `meta["rooms"]`는 뷰어가 키 이름으로 직접 읽어 **무시(무해)**.
- 공개 영향 없음: `channel`은 뷰어 meta에만, 공개 chat_kb.json build meta에는 channel 필드 없음(`chat_to_kb.py:171-174`).

### 4.7 결정론 하드닝
- `chat_to_kb.py` set 반복부(`:89 for x in sset` 등 match_stocks/match_themes 결과 순회)를 **`sorted(...)`로 감싸** stocks/themes 삽입 순서 결정론화 → PYTHONHASHSEED 무관하게 chat_kb.json 키 순서 안정.

### 4.8 standalone `__main__` 경로
- `chat_to_kb.py` `__main__`은 `메시지_구조화원문.jsonl` 재로드 후 `build()` 직접 호출. jsonl에 room 없으면 standalone 실행 시 QnA 가드 무력화.
- **수정**: `update_archive.py:660-661` jsonl write dict에 `"room": m.get("room")` 추가. 프로덕션 경로(`refresh.sh`→`main()`→인메모리 msgs→`build`)는 jsonl 왕복 없음(원래 안전).

## 5. 데이터 흐름 (to-be)

```
~/Downloads/KakaoTalk_*  (여러 방·여러 스냅샷)
   │  find_inputs(): 전부 반환(이름 기반 탈락 없음)
   ▼
room_of 태그로 group_by
   │  태그별: 최신=base(verbatim, room·src_file 태깅) + base에 없는 메시지만 fold-in
   │  fold 발생 태그만 (date,time) 안정 정렬
   ▼
태그 그룹 concat(최초등장 datetime 순) = grouped_merged → 전역 idx 재부여
   ▼
최종 msgs (room·src_file·연속 idx)
   ├─ link_records   (방 경계 .get 가드)
   ├─ strategy/aggregate/ontology (순서 무관; mention 단일-msg 스코프)
   └─ chat_to_kb.build (QnA 방 경계 가드, date min/max, set 정렬)
        ▼
     chat_kb.json (방 무관 통합본) → refresh.sh 커밋·push → CI(build.yml) → Pages
        · merge_hub / render._merge_chat_kb: room 안 읽음(무변경). comention 정확도 영향은 §7
```

## 6. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `generator/update_archive.py` | `find_input`→`find_inputs`+레거시 래퍼(§4.1)·`room_of`(§4.2) 신설; `main()` 태그 group_by·base+fold·안정정렬·concat·idx 재부여(§4.3); `link_records` 방 `.get` 가드(§4.4); meta date min/max·channel 재대입·rooms(§4.5·4.6); jsonl write room 추가(§4.8) |
| `generator/chat_to_kb.py` | QnA 방 `.get` 가드(§4.4); build meta from/to min/max(§4.5); set 반복 `sorted()`(§4.7) |
| `generator/test_parse.py` | find_inputs(전부 반환)·래퍼(mtime·문자열)·room_of(정규+폴백)·base verbatim(dedup 안 함)·fold(겹침 흡수·occ 구분)·방경계 가드·통합경로(find_inputs→…→build) idx연속·room보유·date min/max 테스트 추가; 기존 assert 계약 유지 |
| `generator/refresh.sh` | 안내: "인자 없이 실행=다방 자동병합, 파일 명시=그 파일만" |
| `generator/README.md` | 다방 병합 동작·"파일 인자 시 단일 방만"·housekeeping 갱신 |
| (무변경·영향없음 확인) | `merge_hub.py`·`hublib/render.py`(`_merge_chat_kb`)·`.github/workflows/build.yml` |

## 7. 알려진 한계 (명시)
- **동일 표시명 방 충돌**: 서로 다른 물리적 방이 같은 표시명이면 한 `room` 태그로 묶임 → 데이터 유실은 없으나(fold) 경계에서 근접 가드가 안 걸려 QnA/제목 오귀속 가능. (방 이름을 다르게 두면 회피.)
- **fold 경로 best-effort**: 방 나갔다 재입장/export 절단 등으로 base가 불완전해 fold가 실행될 때, content 키가 분 단위(초 절단)라 같은 분 동일 발화 반복은 fold에서 1건으로 볼 수 있고 (date,time) 안정 정렬도 분 단위. **흔한 경로(방별 최신 verbatim)는 무손실·무역전**이며, 이 한계는 드문 fold 경로에 국한.
- **txt 다중 스냅샷**: txt는 파일명 규칙이 CSV와 달라 폴백 태그가 스냅샷마다 갈릴 수 있음 → 같은 방이 여러 태그로 나뉘면 중복 가능(fold는 같은 태그 내에서만). 실데이터는 CSV라 주 경로는 견고. **txt는 방별 최신 1개만 두길 권장.**
- **merge_hub comention 정확도**: co_edges/comention 키가 `(date, sharer, snippet[:40])`뿐이고 chat_kb mention에 room 없음 → 다른 방 동명이인이 같은 날 동일 앞40자 스니펫을 남기면 서로 다른 방 종목이 잘못 엮일 수 있음. (허용 불가 시 후속: mention 내부 room + merge_hub 키에 room, 공개 출력 미포함.)
- **mention 방 가드 부재**: signals에 room 없어 mention은 방 가드 대상 아님(단일-msg 스코프라 오귀속 미실현).
- **taxonomy**: `CORE`/`TEACHERS`/멤버 별명은 프롬어스 기준. 다른 방 멤버는 '일반 멤버', 별명 매칭 안 될 수 있음(종목 별칭은 전역이라 동작).
- **members 카운트**: sender 이름 기준 → 동명이인/여러 방 동일 이름은 1명 합산.
- **공개 배포**: 다른 방 실명·대화 노출(인지·수용). 익명화 후속.

## 8. 테스트 계획 (`test_parse.py` 확장, 기존 통과 유지)
- **find_inputs**: 여러 파일(다방·동일방 다스냅샷) 모두 반환, 출력형 CSV 미포함.
- **find_input 래퍼**: 리스트 아닌 **문자열/None** + **mtime 최신**(기존 `test_arg_priority_and_prefix` 계약 유지).
- **room_of**: 정규매칭→표시명; 폴백→타임스탬프 제거 태그.
- **base verbatim**: 같은 방 최신 1파일만 있을 때 **dedup 미적용** — 같은 분·동일 body·동일 sender 2건이 **둘 다 보존**(초 절단 유실 없음), 파일 순서 유지.
- **fold**: 같은 태그 old⊂new면 new만(fold 0건); 같은 태그 **disjoint(충돌/절단)** 이면 겹치지 않는 메시지 흡수, occ로 동일-분 반복 구분, fold 후 (date,time) 정렬로 역전 없음.
- **방 경계 가드**: A방 질문 뒤 B방 교사 메시지 → QnA 미매칭; link 제목 오귀속 없음; room 미태깅 직접호출도 KeyError 없음(.get).
- **통합 경로**: `find_inputs→parse→병합·idx재부여→build` end-to-end로 by_idx 0..N-1 연속·각 msg room 보유·QnA 가드 실작동.
- **date min/max**: 방 그룹 정렬로 msgs[0]가 전역 최소 아닌 케이스에서 from/to가 실제 min/max.
- 기존 `test_parse.py`·`build/test_merge_hub.py` 통과 유지.

## 9. 하위호환·롤아웃
- 방 1개(현재 프롬어스만): base verbatim이라 출력 **기존과 동일**(dedup·fold·정렬 미발생, idx 불변, date=기존값).
- `find_input` 래퍼(mtime 최신·문자열/None)로 기존 호출부/테스트 호환.
- **`refresh.sh`/README 주의(중요)**: `refresh.sh "$@"` 특성상 **파일을 인자로 명시하면 그 파일만(=단일 방)**, **다방 자동병합은 인자 없이 실행(자동 스캔)**. README "파일 지정" 예시에 이 의미 명시, 다방 사용자는 인자 없이 실행 안내.

## 10. 후속 과제(비범위)
- 스냅샷 수백 개 대비 (path,size,mtime) 파싱 캐시.
- 공개 익명화/본문 PII 마스킹(`build(public=True)` 활성화).
- 동일 표시명 충돌/txt 태그 안정화를 위한 방 인스턴스 식별자(내부 `src_file` 기반).
- merge_hub comention의 room-aware 키(내부 필드).
