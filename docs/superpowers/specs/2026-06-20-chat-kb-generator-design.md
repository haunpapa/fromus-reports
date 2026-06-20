# chat_kb 생성기: CSV 입력 + 원문 보존 + 파이프라인 리포 보관 (2단계-A)

- 날짜: 2026-06-20
- 상태: 설계 승인 → spec 3-렌즈 검증 반영(rev2) → 구현 계획 대기
- 선행: 채팅 온톨로지 1단계·A·D·봇제외·관계망·모바일 완료.
- 범위 분리: 전체 범위(C)는 **A→B** 로 분리. 본 문서는 **A**(CSV+원문+리포보관). **B**(생성단계 정확귀속 개선, `find_ents`/`match_stocks` 도배 방지)는 후속 별도 사이클.
- 편집 지정 원칙: 본 문서의 라인번호는 현재 zip/리포 기준 참고치다. 구현은 **함수명·식별자 기준**(`parse`/`parse_csv`/`find_txt`/`find_input`/`strategy`/`main`/`openChatModal`)으로 편집하라 — 편집 시 라인이 밀린다.

## 1. 배경

`chat_kb.json` 생성 파이프라인이 리포에 없다(메모리상 "갭 B"). 카카오톡 export → 온톨로지 변환 스크립트는 로컬 zip(`온톨로지_데이터.zip`)에만 있고 버전관리되지 않는다. 현재 한계 3가지:

1. **버전관리 부재**: `update_archive.py`·`chat_to_kb.py`·`fromus_taxonomy.py` 가 리포 밖에만 존재 → 생성 로직 변경 이력 추적 불가, 재현 불가.
2. **입력 형식 제약**: `find_txt()`/`parse(txt)` 가 `.txt` export 만 처리. 사용자가 보유한 export 는 `.csv`(`Date,User,Message`) 형식이 다수(`~/Downloads`).
3. **원문 절단**: 채팅 근거 모달이 `snippet` 180자에서 잘림 — 긴 의견의 전문을 볼 수 없음. 모달에 `※ 현재 180자 요약 — 원문 전체는 2단계 예정` 안내가 하드코딩되어 있음.

### 1.1 현재 파이프라인 구조 (실측 확인 완료)

로컬 `update_archive.py`(93KB, 다목적 로컬 도구) 흐름:
```
find_txt() → parse(txt) → link_records → enrich(자체 resolve/resolve_all, naver) → strategy(msgs) → aggregate
  → [지식허브_통합 통합블록] chat_to_kb.build(msgs, links, sig) → chat_kb.json  (+ 뷰어 HTML)
```
- `parse(txt)`: `DATE_RE`(`-----  YYYY년 M월 D일 요일  -----` 구분줄)·`MSG_RE`(`[발신자] [오전|오후 H:MM] 본문`)·`to24()` → msgs `[{idx,date,weekday,time,sender,body}]`(body 는 멀티라인 join).
- 네이버 링크 해제는 `update_archive.py` 가 **자체 내장**(`http_get`/`resolve`/`resolve_all`, L202-271). 별도 `naver_resolve.py`(독립 진입점)는 이 파이프라인이 import 하지 않음.
- `strategy(msgs)`: 메시지별 `find_ents(body)`(종목 alias substring)·`find_ths`·`is_src`(SRC_MARKERS)로 signal 생성. `text = URLpat.sub("",body).strip()`(L290 스코프), `snippet = re.sub(r"\s+"," ",text)[:220]`.
- `chat_to_kb.build(msgs, links, signals, public=False)`: signal → `st["mentions"].append({date,sharer,source:"chat",stance,type,snippet:s["snippet"][:180]})`. `_anon()`/`_sanitize` 는 `public=True` 일 때만 적용. **현재 통합블록은 `build(msgs,links,sig)`(public 기본 False)로 호출 → 익명화 미적용·실명 그대로 산출**(리포 `chat_kb.json` 의 mention `sharer` 전부 실명 확인). 즉 익명화는 현재 동작 중이 아님.
- `parse(txt)` 의 msg dict 는 `body` 뿐 아니라 **`lines`(list)** 도 가짐(`cur["lines"]=[b]`, body 는 join). 다운스트림 `link_records(msgs)` 가 `m["lines"]` 를 리스트로 순회해 URL별 제목을 추출 → CSV 파서도 `lines` 를 반드시 산출해야 함(§3.2).
- **통합블록(L562-582)**: `intdir=P("지식허브_통합")` 하위폴더가 있으면 거기를 `sys.path` 에 넣고 `fromus_taxonomy, chat_to_kb, merge_hub` 를 **그 폴더에서** import → `chat_kb.json` 을 **`지식허브_통합/`** 에 쓰고, 같은 폴더의 `knowledge_base.json` 으로 자체 병합까지 수행. **여기 import 되는 merge_hub 는 리포 루트 정본이 아니라 zip 의 구버전(91줄, `recent` 스키마, opinions/market_news/co_edges 없음)이다.**

### 1.2 소비측(리포, 정본)

- **CI 병합 진입점은 `build_hub.py`**(merge_hub.py 직접 호출 아님). `.github/workflows/build.yml`: `python build_hub.py --src . --json knowledge_base.json` 실행 → `build_hub.py`(L1186-1204)가 **리포 루트 `chat_kb.json`** 을 찾아 `from merge_hub import merge` 로 `knowledge_base.json` 을 **in-place** 병합. 별도 `.merged.json` 미생성.
- 리포 루트 `merge_hub.py`(정본): `_augment`(`{**m,"co_stocks":co}`)·`_chat_block`(opinions/market_news/news)이 mention 의 **미지 필드를 통째 통과**시킴(L71-74,114-125) → 원문 필드 추가 시 merge 무변경(실측 확인).
- 리포 루트 `chat_kb.json`(2.55MB) 이미 git 추적됨. `build.yml` auto-commit `file_pattern` 에 `chat_kb.json` 없음 → **사람이 직접 커밋**. paths 트리거에는 `chat_kb.json`·`merge_hub.py` 포함(변경 시 CI 빌드).

### 1.3 CSV 형식 (실측 확인 완료)

`~/Downloads/KakaoTalk_Chat_*프롬어스*.csv` (최신 06-19 = 11,388행, 멀티라인 3,525·시스템메시지 793 포함):
```
﻿Date,User,Message            ← BOM(efbbbf) 포함 헤더
2026-03-19 17:43:30,"대성","대성님이 들어왔습니다.↵타인, 기관 등의 사칭에..."
```
- `Date`: `YYYY-MM-DD HH:MM:SS` (이미 24시간제, 초 포함, 요일 없음).
- `User`: 발신자. `Message`: 따옴표로 감싼 멀티라인 본문(개행 포함) — Python `csv` 모듈이 정상 파싱(수동 split 금지).
- 입장/공지 등 시스템 메시지 행 존재(txt export 에는 없음) → 종목·테마 미포함이라 `strategy()` 에서 자연 제외(짧은 alias 우연 substring 오탐 가능성은 B 과제, 회귀 테스트로 노이즈 확인).
- txt 와 CSV 는 메시지/멤버 카운트가 다름(CSV 가 시스템메시지 포함) → `build` 메타 수치·정렬에 미세 차이(버그 아님, README 주석).

## 2. 목표 / 비목표

### 목표
- 채팅 생성 파이프라인을 리포 `generator/` 에 보관(버전관리·재현성).
- `.csv` export 입력 지원 — `.txt` 와 동일 msgs 스키마 산출, 다운스트림 무변경.
- 채팅 **의견 근거 원문 보존** — 의견(view/position) mention 에 `full` 필드(전문, 상한 1500자, 개행 보존) 추가, 모달에서 전문 표시 + 구 안내문구 제거.

### 비목표
- **생성단계 정확귀속 개선**(`find_ents`/`match_stocks` 도배 방지) — 후속 B.
- **관련시황(research/market_news) 원문 보존** — 퍼온 외부 시황·증권사 자료라 저작권·크기·프라이버시 민감. 본 작업은 의견만, market_news 전문은 선택적 후속.
- `naver_resolve.py`/HTML 뷰어/`build_hub.py`/`apply_hub_patch.py` 보관·정리.
- 발언자 실명(`sharer`)·본문 PII 공개 프라이버시 강화 — 별도 후속. **현재 파이프라인은 익명화 미적용(public=False, 실명 산출)이며 본 작업도 이를 유지(회귀 0)**. 신규 `full` 본문도 `_sanitize` 비대상이라 스크럽하지 않음(§6 의식적 한계).
- CI 에서 chat_kb 생성 — 파이프라인은 **로컬 실행 도구**(네이버 네트워크·뷰어 의존). chat_kb.json 은 로컬 생성 후 사람이 커밋.

## 3. 설계

### 3.1 `generator/` 디렉토리 (파이프라인 보관)

zip 의 채팅 생성 스크립트 **3개**를 리포에 복사(2개 폴더에 분산되어 있음):
- `generator/update_archive.py` ← `/tmp/onto/update_archive.py` (파서·링크·시그널·생성. CSV·원문·통합블록 편집 대상).
- `generator/chat_to_kb.py` ← `/tmp/onto/지식허브_통합/chat_to_kb.py` (온톨로지 빌더. 원문 편집 대상).
- `generator/fromus_taxonomy.py` ← `/tmp/onto/지식허브_통합/fromus_taxonomy.py` (종목·테마 분류. A 무변경; B 대상).
- `generator/README.md` — 로컬 실행 절차.
- `generator/test_parse.py` — 단위 테스트.

**`naver_resolve.py` 미보관**: `update_archive.py` 가 해제 로직 자체 내장(§1.1). 독립 도구라 chat_kb 생성 경로 비참여 → YAGNI.

**merge_hub.py 비복제·비import (정본 단일화)**: 리포 루트 `merge_hub.py` 가 유일 정본. generator 는 import 하지 않는다.

**통합블록(L562-582) 재작성 — 핵심**: 현재 블록은 `지식허브_통합/` 하위폴더를 전제로 그 폴더의 구버전 merge_hub 까지 import·병합한다. generator/ 에서는:
- `P("지식허브_통합")` 탐색·`sys.path.insert(intdir)`·`import merge_hub`·`knowledge_base.merged.json` 자체병합을 **모두 제거**.
- 대신 단순화: `import chat_to_kb`(generator/ 동거, chat_to_kb 가 `import fromus_taxonomy` 도 동거로 해결) → `kb = chat_to_kb.build(msgs, links, sig)` → **chat_kb.json 을 리포 루트에 기록**.
  - **`public` 인자 미지정 = 기본 False = 현재 동작·실명 유지(회귀 0)**. 익명화(public=True)는 비목표이며, 전환 시 기존 산출물의 sharer 가 전부 `프로미·해시` 로 바뀌는 회귀가 발생하므로 본 작업에서 하지 않음.
  - 리포 루트 경로: `REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` (generator/ 의 부모). 출력: `os.path.join(REPO_ROOT, "chat_kb.json")` — `build_hub.py`(L1188)가 소비하는 정본 위치와 일치.
- **순서 보존**: `build()` 의 news 생성은 `l.get("clean_title")` 를 우선 사용하고, `clean_title` 은 `dedup()`(main `uniq=dedup(links)`)에서만 설정된다. 재작성 블록은 반드시 **`dedup()` 이후**에 위치해야 함(현재 통합블록도 dedup 뒤). 이동 금지.
- **main 전체 경로 유지**: A 는 통합블록의 출력 위치·self-merge 만 변경한다. `parse(_csv)`→`link_records`→`enrich`(자체 resolve, 네이버 네트워크)→`strategy`→`aggregate`→온톨로지→`온톨로지_데이터/` 11파일·뷰어 HTML 기록은 그대로 — **로컬 전용 도구**라 네트워크·파일쓰기 정상. (chat_kb 만 만드는 경량 경로 분리는 비목표.)
- **빈 입력 가드**: 빈/전부-skip CSV 로 `msgs==[]` 면 main 의 `aggregate`/meta(`msgs[0]["date"]`)가 IndexError. main 진입 직후 `if not msgs: print(...); return` 조기 종료 가드 추가(현재 `build()` 만 빈입력 방어).
- 병합은 **CI `build_hub.py → merge_hub.merge`** 가 전담(generator 책임 = chat_kb.json 생성까지). → merge_hub.py 진짜 무변경.
- `import update_archive` 시 모듈 본문이 main() 을 실행하지 않도록 `if __name__=="__main__"` 가드 유지(현재 L586 존재) — 모듈 레벨에 open/network 없음(ENTITIES 등은 리터럴), `requests` 는 try/except 폴백 → **테스트가 부작용 없이 함수만 import 가능**.

`generator/README.md` 절차:
1. `python generator/update_archive.py <export.txt|csv>` (리포 루트에서 실행 권장). 인자 없으면 `~/Downloads`·cwd 에서 최신 `KakaoTalk_*` 자동탐색.
2. 생성된 **리포 루트 `chat_kb.json`** 을 사람이 직접 커밋(`build.yml` auto-commit 비대상).
3. CI `build.yml → build_hub.py` 가 `merge_hub.merge(chat_kb.json)` 로 `knowledge_base.json` in-place 병합 → Pages 배포.
4. 주의: 로컬 전용(네이버 네트워크·뷰어). 테스트는 로컬 `python generator/test_parse.py`(CI 에 테스트 스텝 없음).

### 3.2 CSV 입력 지원 (`generator/update_archive.py`)

#### `parse_csv(path)` 신규
`parse(txt)` 와 **동일한 msgs 스키마**를 반환(다운스트림 무변경):
- `csv` 모듈(L14 이미 import), `datetime` 신규 import. `open(path, encoding="utf-8-sig", newline="")`(BOM 제거 + 멀티라인 안전).
- `csv.reader` → **첫 행(헤더) 무조건 스킵**. 각 데이터 행 `row`:
  - `if len(row) < 3: continue` (열 부족 방어).
  - `ds = row[0]`; **try/except 로 날짜 파싱**: `date = ds[:10]`, `time = ds[11:16]`(초 절단), `weekday` = `datetime.date(int(y),int(m),int(d)).weekday()` → `["월요일","화요일","수요일","목요일","금요일","토요일","일요일"][i]`. 파싱 실패(빈/비ISO Date) 시 그 행 **skip + 누적 카운트**(또는 weekday="" 폴백) — 정책은 skip 권장.
  - `sender = row[1].strip()`, `body = row[2]`(개행 보존), `idx` = 누적 순번.
  - **`lines` 키 필수**: `link_records` 가 `m["lines"]` 를 리스트로 순회하므로 CSV msg 도 `lines = body.split("\n")` 산출(그리고 `body = "\n".join(lines)` 로 정합). txt `parse` 와 동일 스키마 `{idx,date,weekday,time,sender,body,lines}`.
- 빈/헤더만 파일 → `[]` 반환(`chat_to_kb.build` 빈입력 방어 + main 빈가드(§3.1)와 정합).

#### `find_input(argv)` 신규 (`find_txt` 일반화)
- argv 에서 `.txt`/`.csv` 확장자 + 존재 경로 우선 반환.
- 없으면 자동탐색: **검색 루트 = [cwd, `~/Downloads`]**, 패턴 = `KakaoTalk_*.txt`·`KakaoTalk_*.csv`(범용 `*.txt`/`*.csv` 폴백은 출력 CSV(`뉴스_전체아카이브.csv` 등) 오선택 위험이라 **`KakaoTalk_*` prefix 로 제한**). 합집합 중 `os.path.getmtime` 최신 1개. 실제 파일명 `KakaoTalk_Chat_2026 프롬어스_*.csv` 는 prefix 매칭됨.
- 호출부 `main()`(현재 `txt=find_txt()` L483, `parse(txt)` L486): `path = find_input(sys.argv)` → `msgs = parse_csv(path) if path.lower().endswith(".csv") else parse(path)` 로 분기.
- `find_txt()` 는 제거(외부 호출 없음) 또는 `find_input` 위임 얇은 래퍼.

### 3.3 원문 보존 (의견 180자 → 전문)

#### `strategy()` — `full` 필드 추가 (`generator/update_archive.py`, sig.append L306-308)
signal dict 에 `snippet`(미리보기 220) 유지 + `full` 추가:
- `full = re.sub(r"[ \t]+", " ", URLpat.sub("", body)).strip()[:1500]` — **개행 보존**(가로 공백만 정리), 상한 1500자(폭주·크기 방지). `body`/`text` 변수는 해당 스코프(L290)에 존재.

#### `chat_to_kb.build()` — 의견 mention 에만 `full` (`generator/chat_to_kb.py`, mention append L59-60)
```python
ment = {"date":s["date"],"sharer":s["sharer"],"source":"chat",
        "stance":s["stance"],"type":s["type"],"snippet":s["snippet"][:180]}
if s.get("type") in ("view","position"):   # 의견만 원문 보존
    ment["full"] = s.get("full","")
st["mentions"].append(ment)
```
- research(자료/시황) mention 은 `full` 미부여 → 모달이 `m.full || m.snippet` 폴백으로 180자 유지(비목표 정합).

#### `merge_hub.py` — 무변경 (검증만, generator 비import)
- `_augment`(`{**m}`)·`_chat_block`(opinions/market_news)이 `full` 자동 통과(실측: opinions/market_news 양 경로). news 는 멘션 아님(title 만)이라 `full` 없음이 정상. **그룹핑 키는 절대 `snippet[:40]` 유지**(`_co_edges`/`_build_comention_map`/`_augment` 모두 동일 키) — `full` 을 키로 쓰면 개행·길이 차로 동시언급 그룹핑이 깨짐. 구현계획에 불변 제약 명시.

#### `hub_template.html` — 모달 전문 표시 (`openChatModal`, #cmBody, L1762-1767)
- 본문 표시: `${esc(m.snippet||'')}` → `${esc(m.full||m.snippet||'')}`(하위호환 폴백).
- **L1764 안내 div(`※ 현재 180자 요약 — 원문 전체는 2단계 예정`) 제거**(full 표시와 모순).
- 본문 컨테이너 div(L1763, `line-height:1.6`)에 **`white-space:pre-wrap` 추가** — `esc()` 는 HTML 이스케이프만 하고 개행을 `<br>` 로 바꾸지 않으므로 pre-wrap 없으면 개행이 한 줄로 무너짐.
- **`full` 적용은 #cmBody 본문 단 한 곳만**. 나머지 `snippet` 사용처는 전부 유지(화이트리스트): 모달 발언 타임라인(L1759 `o.snippet.slice(0,60)`), 종목 카드 미리보기(`renderChat` L963 `slice(0,120)`), 섹터 요약(L884), 검색 인덱스·결과(L1157·L1181). **`snippet→full` 전역치환 금지**(카드 1500자 폭주 방지).

### 3.4 결정 (기본값)
- 원문 상한 1500자, 개행 보존, URL 제거. `full` 은 **의견(view/position) mention + 모달 본문 전용**.
- 파이프라인 로컬 실행, chat_kb.json 출력 = 리포 루트, merge_hub.py 단일 정본·무변경.
- generator = 3개 스크립트(naver_resolve 제외, merge_hub 비import).
- `public=False`(실명) 유지 = 현재 동작·회귀 0. 익명화·full 본문 PII 스크럽은 비목표(§6).

## 4. 테스트

### `generator/test_parse.py` (stdlib unittest, 로컬 실행)
실행: `python generator/test_parse.py`(generator/ 가 sys.path[0] → `import update_archive`·`chat_to_kb` 동거 해결). CI 에 테스트 스텝 없음(로컬 회귀 보장).
- `parse_csv`: 샘플 CSV 문자열(BOM·따옴표 멀티라인·시스템메시지·열부족·비ISO Date 행 포함) → msgs 스키마 검증(`date`·`time` 초절단·`weekday` 한글·`body` 개행보존·**`lines` 리스트 타입·body==join(lines)**·`idx` 순번), 깨진 날짜 행 skip, 빈/헤더만 → `[]`.
- `find_input`: 임시 디렉토리에 `KakaoTalk_*.txt`/`.csv` + 출력형 `뉴스_*.csv` 생성 → 확장자 인자 우선·최신 mtime 선택·출력 CSV 미선택 검증.
- txt 회귀(불변): 동일 `.txt` 입력에 `parse(txt)` 가 동일 msgs(idx·date·time·weekday·body 개행) 산출(골든).
- 원문: `strategy()` 가 **실재 ENTITIES alias + 강세 키워드**를 담은 body 에서 signal 생성 → `full` 존재·≤1500·개행 보존 검증. alias·키워드는 하드코딩 금지, `update_archive.ENTITIES`·`BULL`/`VIEWKW` 에서 직접 읽어 사용(상수 변경 시 테스트 안 깨짐). `chat_to_kb.build` 의 view/position mention 에 `full` 존재, research mention 에 `full` 부재.
- PII 가드(경량): full 샘플에 전화번호/계좌 같은 긴 숫자열(`\d{8,}`) 노출 시 경고(차단 아님) — 의식적 한계 인지용.
- news clean_title: 통합블록이 `dedup()` 이후 실행되어 news 제목이 `clean_title`(보일러플레이트 제거) 기반인지 1건 확인.

### `build/test_merge_hub.py` 확장 (기존 merge 테스트와 동거)
- 기존 fixture 에 `full` 키를 가진 view/position mention 추가 → `merge` 후 `stocks[*].chat.opinions[*].full` 통과 검증. market_news mention(research)에 `full` 부재 시 누락 안전(키 없음) 검증. 그룹핑 키 불변(`co_edges`/`co_stocks`가 full 무관) 확인.

### 스모크 / playwright
- 단독: `python merge_hub.py knowledge_base.json chat_kb.json` → `knowledge_base.merged.json` 의 `stocks[*].chat.opinions[*].full` 존재.
- 정본: 리포 루트 `chat_kb.json` 의 `stocks[*].mentions[*]` 중 view/position 에 `full` 존재 → `build_hub.py` 실행 후 `knowledge_base.json` 의 `chat.opinions[*].full` 존재.
- playwright: 의견 채팅 근거 모달 → 180자 초과 전문 표시(개행 반영), `2단계 예정` 문구 사라짐, 콘솔 에러 없음.

## 5. 파일 변경
- **신규**: `generator/update_archive.py`·`generator/chat_to_kb.py`·`generator/fromus_taxonomy.py`(zip 복사) · `generator/README.md` · `generator/test_parse.py`.
- **수정(generator 내)**: `update_archive.py`(`parse_csv`·`find_input`·`strategy` full·`main()` 분기·**통합블록 재작성**(merge_hub/지식허브_통합 제거, chat_kb.json→리포루트)), `chat_to_kb.py`(의견 mention full).
- **수정(리포)**: `hub_template.html`(모달 `full` 표시 + pre-wrap + 안내문구 제거), `build/test_merge_hub.py`(full 통과 테스트).
- **무변경**: `merge_hub.py`·`build_hub.py`·`build.yml`(통과·소비만, 테스트로 검증).

## 6. 리스크 / 주의
- **통합블록 재작성**(critical): 출력 경로를 **리포 루트 chat_kb.json** 으로 못박지 않으면 `build_hub.py` 가 옛 chat_kb.json 을 계속 소비. merge_hub 자체병합 제거로 정본 단일화.
- **find_input 검색 루트**(critical): 기존 `find_txt` 는 스크립트 폴더만 glob → generator/ 에선 빈손. cwd+`~/Downloads`·`KakaoTalk_*` prefix 로 해결. 명시 인자 권장.
- **프라이버시·크기**: `full` 의견 한정(view/position ~544건) → research 2103건 제외로 크기·민감도 완화. chat_kb.json(현 2.55MB) 증분 제한적. 상한 1500. 발언자 실명·market_news 전문은 별도 후속(의식적 비목표).
- **모달 안내문구**: `180자 요약…2단계 예정` 제거 누락 시 full 과 모순. pre-wrap 필수(esc 개행 미변환).
- **CI 병합 경로**: 진입점은 `build_hub.py`(merge_hub 직접 아님), `knowledge_base.json` in-place(.merged.json 아님).
- **그룹핑 키 불변**: `snippet[:40]` 유지, `full` 을 키로 쓰지 말 것.
- **parse_csv `lines` 키**(critical): 누락 시 `link_records` 가 `m["lines"]` 에서 KeyError. `lines=body.split("\n")` 필수.
- **public/익명화**(critical): 현재 파이프라인은 `public=False`(실명) — 익명화가 동작 중이 아님. A 도 `public=False` 유지(회귀 0). 단 **chat_kb.json·Pages 에 실명 노출은 기존 상태**(A가 만든 문제 아님) — 익명화 전환은 별도 후속이며 sharer 전면 변경 회귀를 동반.
- **full 본문 PII 미스크럽**(high·의식적 한계): `_sanitize` 는 발화자 식별 필드만 익명화하고 `snippet`/`full` 본문은 건드리지 않음. 신규 full(≤1500자 raw body)은 본문 내 타 멤버 호명·연락처가 들어와도 그대로 노출. A 범위에선 스크럽하지 않음(경량 가드 테스트만). 공개 Pages 운영이라면 후속에서 본문 마스킹 검토 필요.
- **순서·빈입력 가드**: 통합블록은 `dedup()` 이후 위치(clean_title). 빈 CSV → `msgs==[]` 시 main 조기 종료 가드(aggregate/meta IndexError 방지).
- **main 전체 경로 로컬 의존**: chat_kb 생성에 네이버 resolve(네트워크)·뷰어·`온톨로지_데이터/` 기록이 함께 돔 → CI 불가, 로컬 전용. 단위 테스트는 함수 직접 호출(parse_csv/find_input/strategy)로 네트워크 회피.
- **CSV 엣지케이스**: 깨진 날짜 행 try/except skip, 헤더 첫행 스킵, 빈 파일 `[]`. txt/CSV msgs 카운트 차이는 정상(README 주석).
- **이중 분류 체계**(B 메모): `update_archive` 의 ENTITIES/THEMES 와 `fromus_taxonomy` 의 STOCK_META 가 별개 — A 무영향, B 정확귀속 시 통합 검토.
