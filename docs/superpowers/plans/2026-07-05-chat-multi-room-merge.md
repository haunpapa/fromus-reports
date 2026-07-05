# 여러 카톡방 통합 아카이브 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `~/Downloads`의 여러 카톡방 export를 하나로 병합해 `chat_kb.json`을 생성하도록 `generator/`를 확장한다(방별 최신 스냅샷 verbatim + 겹치지 않는 파일만 fold).

**Architecture:** 입력 선택을 단수→복수(`find_inputs`)로 바꾸고, 파일명에서 방 태그(`room_of`)를 추출한다. 방별로 최신 스냅샷을 그대로 채택하고 같은 태그의 겹치지 않는 메시지만 fold-in하는 `merge_inputs()`를 신설한다. 각 메시지에 내부 `room` 태그를 실어 근접 귀속 로직(link 제목 보충·QnA 응답 매칭)이 방 경계를 넘지 않도록 `.get("room")` 가드를 추가한다. 출력물은 방을 구분하지 않는다.

**Tech Stack:** Python 3 (stdlib only: `os, csv, glob, datetime, collections`), `unittest`. 기존 `generator/update_archive.py`·`chat_to_kb.py` 파이프라인.

**Branch:** `feat/chat-multi-room-merge` (이미 체크아웃됨). Spec: `docs/superpowers/specs/2026-07-05-chat-multi-room-merge-design.md`.

**공통 테스트 명령:** `cd /Users/haunpapa/Documents/GitHub/fromus-reports && python generator/test_parse.py -v`
(단일 테스트: `python generator/test_parse.py TestClass.test_method -v` — `unittest.main`이 인자를 받음)

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `generator/update_archive.py` | 파싱·병합·링크·전략·온톨로지·chat_kb 생성 | `find_inputs`/`find_input` 래퍼·`room_of`·`_content_key`/`_keyed`·`merge_inputs` 신설; `main()` 배선; `link_records` 방 가드; meta date min/max·channel·rooms; jsonl `room` |
| `generator/chat_to_kb.py` | msgs→chat_kb.json | QnA 방 가드; build meta from/to min/max; set 반복 `sorted()` |
| `generator/test_parse.py` | 단위·통합 테스트 | 신규 테스트 클래스 추가(기존 유지) |
| `generator/refresh.sh` | 갱신·배포 래퍼 | 안내 주석 |
| `generator/README.md` | 로컬 사용법 | 다방 병합 동작·주의 |

**설계 불변식(모든 태스크 공통):**
- `room`은 **내부 태그** — `chat_kb.json` 출력에 넣지 않는다(방 무관 유지).
- 근접 가드는 양쪽 `.get("room")` 사용(room 없는 직접호출도 None==None으로 기존 동작 보존).
- `main()`은 항상 `merge_inputs()`를 거친다(단일 파일도 태깅·idx 재부여 공통 경로).

---

## Task 1: `room_of()` — 파일명에서 방 태그 추출

**Files:**
- Modify: `generator/update_archive.py` (`find_input` 근처, `:163` 앞에 추가)
- Test: `generator/test_parse.py` (신규 `TestRoomOf`)

- [ ] **Step 1: 실패 테스트 작성** (`test_parse.py` 끝, `if __name__` 앞에 추가)

```python
class TestRoomOf(unittest.TestCase):
    def test_regex_name(self):
        # 실데이터 규칙: KakaoTalk_Chat_<room>_<타임스탬프>.csv
        self.assertEqual(
            U.room_of("/x/KakaoTalk_Chat_2026 프롬어스_2026-05-20-20-33-17.csv"),
            "2026 프롬어스")

    def test_fallback_strips_trailing_timestamp(self):
        # 규칙 불일치 → basename에서 끝 타임스탬프 제거(있으면), 없으면 확장자만 제거
        self.assertEqual(U.room_of("/x/KakaoTalk_myroom_2026-05-20.txt"), "KakaoTalk_myroom")
        self.assertEqual(U.room_of("/x/KakaoTalk_plain.csv"), "KakaoTalk_plain")
```

- [ ] **Step 2: 실패 확인**

Run: `python generator/test_parse.py TestRoomOf -v`
Expected: FAIL — `AttributeError: module 'update_archive' has no attribute 'room_of'`

- [ ] **Step 3: 최소 구현** (`update_archive.py`, `def find_input` 바로 위에 삽입)

```python
_ROOM_RE = re.compile(r"^KakaoTalk_Chat_(.+)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(?:csv|txt)$")
_TS_TAIL_RE = re.compile(r"_\d{4}-\d{2}-\d{2}(?:[-_]\d{2}){0,3}$")
def room_of(path):
    """카톡 export 파일명 → 방 태그(선택/탈락용 아님, 근접 가드·정렬용)."""
    base = os.path.basename(path)
    m = _ROOM_RE.match(base)
    if m:
        return m.group(1)
    stem = os.path.splitext(base)[0]
    return _TS_TAIL_RE.sub("", stem)   # 끝 타임스탬프 있으면 제거, 없으면 그대로
```

- [ ] **Step 4: 통과 확인**

Run: `python generator/test_parse.py TestRoomOf -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 커밋**

```bash
git add generator/update_archive.py generator/test_parse.py
git commit -m "feat: room_of — 카톡 파일명에서 방 태그 추출"
```

---

## Task 2: `find_inputs()` 복수 반환 + `find_input` 레거시 래퍼

**Files:**
- Modify: `generator/update_archive.py:163-174` (`find_input` 전체 교체)
- Test: `generator/test_parse.py` (`TestFindInput` 확장 — 기존 계약 유지 확인)

- [ ] **Step 1: 실패 테스트 작성** (`test_parse.py`의 `TestFindInput` 클래스에 메서드 추가)

```python
    def test_find_inputs_returns_all_kakao(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        a = os.path.join(d, "KakaoTalk_a.csv"); open(a, "w").close()
        time.sleep(0.02)
        b = os.path.join(d, "KakaoTalk_b.csv"); open(b, "w").close()
        out = os.path.join(d, "뉴스_전체아카이브.csv"); open(out, "w").close()  # 출력형(미포함)
        import unittest.mock as mock
        with mock.patch("os.getcwd", return_value=d), \
             mock.patch("os.path.expanduser", return_value="/no/such/dir"):
            got = U.find_inputs(["prog"])
        names = sorted(os.path.basename(p) for p in got)
        self.assertEqual(names, ["KakaoTalk_a.csv", "KakaoTalk_b.csv"])  # 둘 다, 출력형 제외

    def test_find_input_wrapper_is_string_and_newest(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        old = os.path.join(d, "KakaoTalk_a.csv"); open(old, "w").close()
        time.sleep(0.02)
        new = os.path.join(d, "KakaoTalk_b.csv"); open(new, "w").close()
        import unittest.mock as mock
        with mock.patch("os.getcwd", return_value=d), \
             mock.patch("os.path.expanduser", return_value="/no/such/dir"):
            picked = U.find_input(["prog"])
        self.assertIsInstance(picked, str)          # 리스트 아님
        self.assertEqual(picked, new)               # mtime 최신
```

(기존 `test_arg_priority_and_prefix`는 그대로 두어 `find_input(["prog", new]) == new` 문자열 계약이 유지되는지 회귀 검증.)

- [ ] **Step 2: 실패 확인** (진짜 RED는 `find_inputs` 미정의 테스트뿐)

Run: `python generator/test_parse.py TestFindInput.test_find_inputs_returns_all_kakao -v`
Expected: FAIL — `AttributeError: ... has no attribute 'find_inputs'`

참고: `test_find_input_wrapper_is_string_and_newest`는 **구현 전에도 PASS**한다(현행 `find_input`이 이미 문자열·mtime 최신을 반환) — 신규 래퍼가 그 계약을 깨지 않는지 지키는 **회귀 보증용**이다. `test_arg_priority_and_prefix`(기존)도 PASS 유지.

- [ ] **Step 3: 구현** (`update_archive.py:163-174`의 `find_input` 전체를 아래로 교체)

```python
def find_inputs(argv=None):
    """카톡 export 입력 '전부' 반환(이름 기반 탈락 없음). 명시 인자 우선."""
    argv = sys.argv if argv is None else argv
    args = [a for a in argv[1:] if a.lower().endswith((".txt", ".csv")) and os.path.exists(a)]
    if args:
        return args
    cands = []
    for root in (os.getcwd(), os.path.expanduser("~/Downloads")):
        for pat in ("KakaoTalk_*.txt", "KakaoTalk_*.csv"):   # 출력형 CSV는 prefix로 자연 배제
            cands += glob.glob(os.path.join(root, pat))
    return sorted(set(cands))

def find_input(argv=None):
    """레거시 래퍼: 문자열/None + mtime 최신 1개 계약 보존."""
    r = find_inputs(argv)
    return max(r, key=os.path.getmtime, default=None)
```

- [ ] **Step 4: 통과 확인**

Run: `python generator/test_parse.py TestFindInput -v`
Expected: PASS (기존 1 + 신규 2)

- [ ] **Step 5: 커밋**

```bash
git add generator/update_archive.py generator/test_parse.py
git commit -m "feat: find_inputs 복수 반환 + find_input 래퍼(문자열·최신)"
```

---

## Task 3: 병합 코어 — `merge_inputs()` (base verbatim + fold + idx 재부여)

**Files:**
- Modify: `generator/update_archive.py` (`find_input` 아래, `to24` 위에 추가)
- Test: `generator/test_parse.py` (신규 `TestMerge`)

핵심 규칙(spec §4.3): 방별 최신 스냅샷을 **dedup 없이 그대로** 채택(base) → 같은 분 동일 발화 반복 보존. 같은 태그의 다른 파일에서 **fold 판정 키 = `(date,time,sender,body)` 튜플 + 파일내 occ 순번**이 base에 없는 메시지만 fold-in. fold가 발생한 태그만 `(date,time)` 안정 정렬. 태그 그룹을 최초등장 datetime 순으로 concat 후 전역 idx 재부여.

> **용어(spec §4.3과 일치):** "fold 판정 키"는 `(date,time,sender,body)` 4-튜플에 파일내 `occ` 순번을 더한 값이다. 구현상 `_keyed()`가 `((key, occ), m)`로 반환하고 `seen`이 그 `(key,occ)` 쌍을 담는다 — 5개 요소가 모두 일치할 때만 중복으로 본다.

- [ ] **Step 1: 실패 테스트 작성** (`test_parse.py` 끝에 신규 클래스)

```python
class TestMerge(unittest.TestCase):
    def _write(self, d, name, rows):
        # rows: [(datetime_str, sender, message)] → 카톡 CSV
        import csv as _csv
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = _csv.writer(f); w.writerow(["Date", "User", "Message"])
            for dt, u, msg in rows: w.writerow([dt, u, msg])
        return p

    def test_base_verbatim_keeps_same_minute_dupes(self):
        # 같은 방 최신 1파일: dedup 미적용 → 같은 분·동일 body 2건 둘 다 보존
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        p = self._write(d, "KakaoTalk_Chat_방A_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:10", "대성", "ㅋㅋㅋ"),
            ("2026-05-20 09:00:40", "대성", "ㅋㅋㅋ"),   # 다른 실제 메시지(초만 다름)
        ])
        msgs = U.merge_inputs([p])
        self.assertEqual(len(msgs), 2)                 # 유실 없음
        self.assertEqual([m["idx"] for m in msgs], [0, 1])
        self.assertTrue(all(m["room"] == "방A" for m in msgs))

    def test_same_room_snapshots_dedup_via_fold(self):
        # 같은 방 두 스냅샷(old ⊂ new): 최신만 채택, fold 0건 → 중복 없음
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        old = self._write(d, "KakaoTalk_Chat_방A_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "안녕"),
        ])
        time.sleep(0.02)
        new = self._write(d, "KakaoTalk_Chat_방A_2026-05-21-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "안녕"),
            ("2026-05-21 09:00:00", "대성", "오늘도"),
        ])
        msgs = U.merge_inputs([old, new])
        bodies = [m["body"] for m in msgs]
        self.assertEqual(bodies, ["안녕", "오늘도"])    # 중복 없이 union

    def test_two_rooms_merged_and_tagged(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        a = self._write(d, "KakaoTalk_Chat_방A_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "A방 메시지")])
        b = self._write(d, "KakaoTalk_Chat_방B_2026-06-20-10-00-00.csv", [
            ("2026-06-20 09:00:00", "밝쌤", "B방 메시지")])
        msgs = U.merge_inputs([b, a])                  # 순서 무관
        self.assertEqual(len(msgs), 2)
        self.assertEqual({m["room"] for m in msgs}, {"방A", "방B"})
        self.assertEqual([m["idx"] for m in msgs], [0, 1])
        # 방 그룹은 최초등장 datetime 순 → A(5월) 먼저
        self.assertEqual(msgs[0]["room"], "방A")

    def test_name_collision_keeps_both_rooms(self):
        # 동일 표시명 서로 다른 방(내용 disjoint) → fold로 둘 다 보존(방 유실 없음)
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        r1 = self._write(d, "KakaoTalk_Chat_같은이름_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "첫째 방 대화")])
        time.sleep(0.02)
        r2 = self._write(d, "KakaoTalk_Chat_같은이름_2026-05-21-10-00-00.csv", [
            ("2026-05-21 09:00:00", "밝쌤", "둘째 방 대화")])
        msgs = U.merge_inputs([r1, r2])
        bodies = sorted(m["body"] for m in msgs)
        self.assertEqual(bodies, ["둘째 방 대화", "첫째 방 대화"])  # 유실 없음
```

- [ ] **Step 2: 실패 확인**

Run: `python generator/test_parse.py TestMerge -v`
Expected: FAIL — `merge_inputs` 미정의

- [ ] **Step 3: 구현** (`update_archive.py`, `find_input` 아래 · `to24` 위에 추가)

```python
def _parse_any(path):
    return parse_csv(path) if path.lower().endswith(".csv") else parse(path)

def _keyed(msgs):
    """각 msg에 파일 내 occ(동일 (date,time,sender,body) 등장 순번) 부여 → ((key,occ), m)."""
    counts = {}; out = []
    for m in msgs:
        k = (m["date"], m["time"], m["sender"], m["body"])
        occ = counts.get(k, 0); counts[k] = occ + 1
        out.append(((k, occ), m))
    return out

def merge_inputs(paths):
    """여러 카톡 export → 통합 msgs. 방별 최신 verbatim + 겹치지 않는 파일만 fold. idx 재부여."""
    groups = defaultdict(list)
    for p in paths:
        groups[room_of(p)].append(p)
    room_lists = {}
    for tag, files in groups.items():
        files = sorted(files, key=os.path.getmtime, reverse=True)   # 최신 먼저
        base = _parse_any(files[0])
        for m in base: m["room"] = tag; m["src_file"] = files[0]
        seen = set(ck for ck, _ in _keyed(base))
        folded = False
        for f in files[1:]:
            for ck, m in _keyed(_parse_any(f)):
                if ck not in seen:
                    seen.add(ck); m["room"] = tag; m["src_file"] = f
                    base.append(m); folded = True
        if folded:
            base.sort(key=lambda m: (m["date"], m["time"]))         # 안정 정렬(역전 보정)
        room_lists[tag] = base
    def _earliest(ms):
        return min(((m["date"], m["time"]) for m in ms), default=("", ""))
    merged = [m for ms in sorted(room_lists.values(), key=_earliest) for m in ms]
    for i, m in enumerate(merged): m["idx"] = i
    return merged
```

- [ ] **Step 4: 통과 확인**

Run: `python generator/test_parse.py TestMerge -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add generator/update_archive.py generator/test_parse.py
git commit -m "feat: merge_inputs — 방별 최신 verbatim + fold 병합"
```

---

## Task 4: `main()` 배선 — 단일 파일 → 다파일 병합

**Files:**
- Modify: `generator/update_archive.py:583-590` (입력/파싱 구간)

- [ ] **Step 1: 현재 코드 확인** (`:583-590`)

```python
    path=find_input()
    if not path: print("[!] 카카오톡 .txt/.csv 를 찾지 못했습니다. 인자로 경로를 주거나 ~/Downloads 에 두세요."); return
    print(f"▶ 입력: {os.path.basename(path)}")
    msgs = parse_csv(path) if path.lower().endswith(".csv") else parse(path)
    if not msgs: print("[!] 메시지가 비어 있습니다(파싱 0건)."); return
    links=link_records(msgs); enrich(links)
```

- [ ] **Step 2: 교체**

```python
    paths=find_inputs()
    if not paths: print("[!] 카카오톡 .txt/.csv 를 찾지 못했습니다. 인자로 경로를 주거나 ~/Downloads 에 두세요."); return
    print(f"▶ 입력 {len(paths)}개: " + ", ".join(os.path.basename(p) for p in paths))
    msgs = merge_inputs(paths)
    if not msgs: print("[!] 메시지가 비어 있습니다(파싱 0건)."); return
    _rooms = sorted(set(m.get("room","") for m in msgs))
    print(f"▶ 방 {len(_rooms)}개: {', '.join(_rooms)} · 메시지 {len(msgs)}")
    links=link_records(msgs); enrich(links)
```

- [ ] **Step 3: 스모크 확인** (실데이터 1건으로 end-to-end)

Run: `python generator/update_archive.py --no-resolve "$HOME/Downloads/$(ls -t ~/Downloads | grep '^KakaoTalk_Chat.*프롬어스.*\.csv$' | head -1)" < /dev/null`
Expected: `▶ 입력 1개: ...`, `▶ 방 1개: 2026 프롬어스 · 메시지 N`, `▶ chat_kb.json 생성` 출력, 오류 없음.
(주의: 이 명령은 `chat_kb.json`을 갱신함 — 커밋하지 말 것. Task 11에서 최종 검증.)

- [ ] **Step 4: 단위 테스트 회귀 확인**

Run: `python generator/test_parse.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add generator/update_archive.py
git commit -m "feat: main()에서 find_inputs+merge_inputs 배선(다방 병합)"
```

---

## Task 5: `link_records` 방 경계 가드

**Files:**
- Modify: `generator/update_archive.py:224-231`
- Test: `generator/test_parse.py` (신규 `TestRoomGuards`에 link 케이스)

- [ ] **Step 1: 실패 테스트 작성** (`test_parse.py` 끝, 신규 클래스)

```python
class TestRoomGuards(unittest.TestCase):
    def _m(self, idx, room, sender, body):
        return {"idx": idx, "date": "2026-05-20", "time": "09:00",
                "weekday": "수요일", "sender": sender, "room": room,
                "body": body, "lines": body.split("\n")}

    def test_link_title_not_borrowed_across_rooms(self):
        # A방 링크(제목 없음) 바로 뒤 이웃이 B방 동명이인 → 제목 near-보충 금지
        msgs = [
            self._m(0, "방A", "대성", "https://x.co/aaa"),
            self._m(1, "방B", "대성", "이건 B방 제목 후보 텍스트입니다"),
        ]
        recs = U.link_records(msgs)
        rec = [r for r in recs if r["url"].startswith("https://x.co/aaa")][0]
        self.assertNotEqual(rec.get("title_src"), "near")   # 방 넘어 빌려오지 않음
```

- [ ] **Step 2: 실패 확인**

Run: `python generator/test_parse.py TestRoomGuards.test_link_title_not_borrowed_across_rooms -v`
Expected: FAIL — 현재는 sender만 보므로 B방 텍스트를 near 제목으로 채택(`title_src == "near"`).

- [ ] **Step 3: 구현** (`:224-231` 교체 — `i=r["msg_idx"]` 아래에 `r_room` 추가, 조건에 방 일치)

```python
    for r in recs:
        if r["title"]: continue
        i=r["msg_idx"]
        r_room=idx.get(i,{}).get("room")
        for off in (1,-1,2,-2,3,-3):
            nb=idx.get(i+off)
            if nb and nb.get("room")==r_room and nb["sender"]==r["sharer"] and not URLpat.search(nb["body"]):
                t=tidy(nb["body"])
                if len(t)>=10: r["title"]=t; r["title_src"]="near"; break
```

- [ ] **Step 4: 통과 확인**

Run: `python generator/test_parse.py TestRoomGuards -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add generator/update_archive.py generator/test_parse.py
git commit -m "feat: link_records 방 경계 가드(.get room)"
```

---

## Task 6: `chat_to_kb` QnA 방 경계 가드

**Files:**
- Modify: `generator/chat_to_kb.py:157-159`
- Test: `generator/test_parse.py` (`TestRoomGuards`에 QnA 케이스)

- [ ] **Step 1: 실패 테스트 작성** (`TestRoomGuards`에 메서드 추가)

```python
    def test_qna_not_matched_across_rooms(self):
        # A방 질문(idx 0) 바로 뒤 B방 교사 메시지(idx 1) → QnA 미매칭
        q = self._m(0, "방A", "학생하나", "이거 어떻게 하나요?")
        a = self._m(1, "방B", "밝쌤👩🏻‍🏫", "이렇게 하시면 됩니다 자세한 설명 추가")
        kb = C.build([q, a], [], [])
        self.assertEqual(kb["qna"], [])          # 방 경계 넘어 응답 매칭 금지

    def test_qna_matched_within_room(self):
        q = self._m(0, "방A", "학생하나", "이거 어떻게 하나요?")
        a = self._m(1, "방A", "밝쌤👩🏻‍🏫", "이렇게 하시면 됩니다 자세한 설명 추가")
        kb = C.build([q, a], [], [])
        self.assertEqual(len(kb["qna"]), 1)      # 같은 방이면 정상 매칭
```

(교사 이름은 `chat_to_kb.py:8`의 `TEACHERS`에 실재하는 `"밝쌤👩🏻‍🏫"` 사용.)

- [ ] **Step 2: 실패 확인**

Run: `python generator/test_parse.py TestRoomGuards.test_qna_not_matched_across_rooms -v`
Expected: FAIL — 현재는 room 무시하고 매칭(`kb["qna"]` 1건).

- [ ] **Step 3: 구현** (`chat_to_kb.py:159` 조건에 방 일치 추가)

```python
        for j in range(m["idx"]+1,min(m["idx"]+6,len(msgs))):
            nb=by_idx.get(j)
            if nb and nb.get("room")==m.get("room") and nb["sender"] in TEACHERS:
```

- [ ] **Step 4: 통과 확인**

Run: `python generator/test_parse.py TestRoomGuards -v`
Expected: PASS (link + qna 3 tests)

- [ ] **Step 5: 커밋**

```bash
git add generator/chat_to_kb.py generator/test_parse.py
git commit -m "feat: chat_to_kb QnA 방 경계 가드(.get room)"
```

---

## Task 7: meta date min/max + channel/rooms 파생

**Files:**
- Modify: `generator/update_archive.py:605` (뷰어 meta)
- Modify: `generator/chat_to_kb.py:171-174` (build meta)
- Test: `generator/test_parse.py` (`TestMerge`에 date 케이스)

- [ ] **Step 1: 실패 테스트 작성** (`TestMerge`에 추가)

```python
    def test_build_meta_from_to_min_max(self):
        # 방 그룹 정렬로 msgs 순서가 시간순이 아닐 때도 from/to는 실제 min/max
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        a = self._write(d, "KakaoTalk_Chat_방Z_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "중간")])
        b = self._write(d, "KakaoTalk_Chat_방A_2026-06-20-10-00-00.csv", [
            ("2026-04-01 09:00:00", "밝쌤", "가장 이른"),
            ("2026-07-01 09:00:00", "밝쌤", "가장 늦은")])
        msgs = U.merge_inputs([a, b])
        kb = C.build(msgs, [], [])
        self.assertEqual(kb["build"]["from"], "2026-04-01")
        self.assertEqual(kb["build"]["to"], "2026-07-01")
```

- [ ] **Step 2: 실패 확인**

Run: `python generator/test_parse.py TestMerge.test_build_meta_from_to_min_max -v`
Expected: FAIL — 현재 `msgs[0]/msgs[-1]` 기준이라 min/max 불일치.

- [ ] **Step 3a: `chat_to_kb.py:171-174` 교체**

```python
    meta={"generated_from":"kakao_chat","messages":len(msgs),
          "members":len(set(m.get("sender") for m in msgs)),
          "from":min((m.get("date","") for m in msgs), default=""),
          "to":max((m.get("date","") for m in msgs), default=""),
          "stocks":len(stocks),"themes":len(themes),"news":len(news)}
```

- [ ] **Step 3b: `update_archive.py:605`의 meta 앞부분 교체**

현재:
```python
    meta={"channel":"프롬어스 오픈카톡(정규반)","date_from":msgs[0]["date"],"date_to":msgs[-1]["date"],
```
교체:
```python
    _mrooms=sorted(set(m.get("room","") for m in msgs))
    _channel=_mrooms[0] if len(_mrooms)==1 else f"{_mrooms[0]} 외 {len(_mrooms)-1}개"
    meta={"channel":_channel,"rooms":_mrooms,
          "date_from":min(m["date"] for m in msgs),"date_to":max(m["date"] for m in msgs),
```

- [ ] **Step 4: 통과 확인**

Run: `python generator/test_parse.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add generator/update_archive.py generator/chat_to_kb.py generator/test_parse.py
git commit -m "feat: meta date min/max + channel/rooms 파생"
```

---

## Task 8: chat_kb.json 결정론 — set 반복 `sorted()`

**Files:**
- Modify: `generator/chat_to_kb.py:51,53,67,89` (set 반복부)

set 반복 순서가 `stocks`/`themes` dict 삽입 순서 → `json.dump(indent=1)` 키 순서 → 바이트 diff를 결정한다. `sorted()`로 고정한다. (PYTHONHASHSEED 무관하게 chat_kb.json 안정.)

- [ ] **Step 1: 현재/교체 매핑**

| 라인 | 현재 | 교체 |
|---|---|---|
| `:51` | `for canon in T.match_stocks(body):` | `for canon in sorted(T.match_stocks(body)):` |
| `:53` | `for th in T.match_themes_for_stock(body, canon):` | `for th in sorted(T.match_themes_for_stock(body, canon)):` |
| `:67` | `for th in T.match_themes(m["body"]):` | `for th in sorted(T.match_themes(m["body"])):` |
| `:89` | `for x in sset:` | `for x in sorted(sset):` |

- [ ] **Step 2: 결정론 회귀 테스트 작성** (`test_parse.py` 끝, 신규 클래스 — 자동 가드)

여러 PYTHONHASHSEED로 서브프로세스에서 `chat_to_kb.build`를 돌려 출력 바이트가 동일한지 단언한다(set 반복 순서가 hashseed에 좌우되면 `sorted()` 누락으로 FAIL).

```python
class TestDeterminism(unittest.TestCase):
    def test_chat_kb_hashseed_independent(self):
        import subprocess, json
        ents = list(U.ENTITIES)
        aliases = [U.ENTITIES[e]["al"][0] for e in ents[:3]]   # 3개 종목 별칭(하드코딩 금지)
        body = " ".join(aliases) + " 모두 좋게 봅니다"
        gendir = os.path.dirname(os.path.abspath(U.__file__))
        code = (
            f"import sys,json; sys.path.insert(0, {gendir!r}); import chat_to_kb as C;"
            f"m=[{{'idx':0,'date':'2026-03-20','time':'09:00','weekday':'금요일',"
            f"'sender':'ㄱ 이혜나','room':'r','body':{body!r},'lines':[{body!r}]}}];"
            f"print(json.dumps(C.build(m, [], []), ensure_ascii=False))"
        )
        def run(seed):
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            return subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
        outs = {run(s) for s in ("0", "1", "2", "3", "4")}
        self.assertEqual(len(outs), 1,
                         "chat_kb.json이 PYTHONHASHSEED에 따라 달라짐(set 반복 sorted() 누락?)")
```

- [ ] **Step 3: 실패 확인**

Run: `python generator/test_parse.py TestDeterminism -v`
Expected: FAIL — `sorted()` 적용 전이라 시드별 출력이 갈려 `len(outs) > 1` (여러 종목의 dict 키 순서가 hashseed에 따라 달라짐).
(만약 우연히 PASS면 별칭 개수를 `ents[:5]`로 늘려 재확인.)

- [ ] **Step 4: 구현** — 위 매핑표의 `:51,53,67,89` 4곳을 `sorted(...)`로 교체.

- [ ] **Step 5: 통과 + 전체 회귀 확인**

Run: `python generator/test_parse.py -v`
Expected: `TestDeterminism` PASS(`len(outs)==1`) + 전 클래스 PASS

- [ ] **Step 6: (선택) 실데이터 스모크** — Downloads에 프롬어스 CSV가 있을 때만

```bash
cd /Users/haunpapa/Documents/GitHub/fromus-reports
F="$HOME/Downloads/$(ls -t ~/Downloads | grep '^KakaoTalk_Chat.*프롬어스.*\.csv$' | head -1)"
[ -n "$F" ] && PYTHONHASHSEED=1 python generator/update_archive.py --no-resolve "$F" < /dev/null >/dev/null && cp chat_kb.json /tmp/kb1.json \
  && PYTHONHASHSEED=2 python generator/update_archive.py --no-resolve "$F" < /dev/null >/dev/null && diff -q /tmp/kb1.json chat_kb.json && echo DETERMINISTIC
git checkout chat_kb.json 2>/dev/null || true   # 산출물 되돌리기(커밋 금지)
```
Expected: `DETERMINISTIC`(파일 있을 때) 또는 스킵.

- [ ] **Step 7: 커밋**

```bash
git add generator/chat_to_kb.py generator/test_parse.py
git commit -m "fix: chat_kb.json set 반복 sorted() 결정론 + 자동 회귀 테스트"
```

---

## Task 9: jsonl write에 `room` (standalone 경로 가드 유지)

**Files:**
- Modify: `generator/update_archive.py:660-662`

- [ ] **Step 1: 현재 코드 확인** (`:660-662`)

```python
                uu=URLpat.findall(m["body"])
                f.write(json.dumps({"idx":m["idx"],"date":m["date"],"weekday":m.get("weekday"),
                    "time":m["time"],"sender":m["sender"],"body":m["body"],"urls":uu,"n_urls":len(uu)},
```

- [ ] **Step 2: 교체** (dict에 `"room"` 추가)

```python
                uu=URLpat.findall(m["body"])
                f.write(json.dumps({"idx":m["idx"],"date":m["date"],"weekday":m.get("weekday"),
                    "time":m["time"],"sender":m["sender"],"room":m.get("room"),"body":m["body"],"urls":uu,"n_urls":len(uu)},
```

- [ ] **Step 3: 회귀 확인**

Run: `python generator/test_parse.py -v`
Expected: 전부 PASS (jsonl은 로컬 산출물이라 직접 단위테스트 없음 — 회귀만 확인)

- [ ] **Step 4: 커밋**

```bash
git add generator/update_archive.py
git commit -m "feat: jsonl write에 room 추가(standalone build 방 가드 유지)"
```

---

## Task 10: 통합 경로 테스트 (end-to-end idx 연속·room 보유·QnA)

**Files:**
- Test: `generator/test_parse.py` (`TestMerge`에 통합 케이스)

`find_inputs→merge_inputs→build`가 실제로 이어질 때 idx가 0..N-1 연속이고 각 msg에 room이 실리며 QnA 가드가 동작하는지 end-to-end 검증(단위 msgs 손수 주입이 아님).

- [ ] **Step 1: 테스트 작성** (`TestMerge`에 추가)

```python
    def test_integration_two_rooms_idx_and_room(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        a = self._write(d, "KakaoTalk_Chat_방A_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "학생하나", "이거 어떻게 하나요?")])
        b = self._write(d, "KakaoTalk_Chat_방B_2026-06-20-10-00-00.csv", [
            ("2026-06-20 09:00:00", "밝쌤👩🏻‍🏫", "이렇게 하시면 됩니다 자세한 설명 추가")])
        msgs = U.merge_inputs([a, b])
        self.assertEqual([m["idx"] for m in msgs], list(range(len(msgs))))  # 연속
        self.assertTrue(all("room" in m for m in msgs))
        kb = C.build(msgs, [], [])
        # 질문(방A)과 교사응답(방B)이 서로 다른 방 → QnA 매칭되면 안 됨
        self.assertEqual(kb["qna"], [])
```

- [ ] **Step 2: 실행**

Run: `python generator/test_parse.py TestMerge.test_integration_two_rooms_idx_and_room -v`
Expected: PASS (Task 3·6 구현으로 이미 통과 — 통합 경로 회귀 방어용)

- [ ] **Step 3: 커밋**

```bash
git add generator/test_parse.py
git commit -m "test: 다방 통합 경로(idx 연속·room·QnA 가드) end-to-end"
```

---

## Task 11: 문서(refresh.sh·README) + 전체 검증

**Files:**
- Modify: `generator/refresh.sh` (헤더 주석)
- Modify: `generator/README.md`

- [ ] **Step 1: `refresh.sh` 헤더 주석 보강** (`사용법:` 블록 아래에 추가)

```bash
# 다방 병합 주의:
#   · 인자 없이 실행  → ~/Downloads 의 모든 KakaoTalk_* 를 방별로 병합(다방 통합)
#   · 파일을 인자로 지정 → 그 파일만 처리(단일 방). 여러 방을 합치려면 인자 없이 실행!
```

- [ ] **Step 2: `README.md` 갱신** — "한 줄 갱신·배포" 아래에 다방 안내 추가

```markdown
## 여러 방 통합(다방 병합)
`~/Downloads` 에 여러 방의 `KakaoTalk_Chat_<방>_*.csv` 를 두고 **인자 없이** 실행하면 방별로 병합된다:
```bash
./generator/refresh.sh          # 다방 자동 병합(인자 없이!)
```
- 방마다 **최신 스냅샷 1개**를 그대로 채택(전체 히스토리 스냅샷). 오래된 스냅샷은 무시되므로 지워도 무손실(속도만 개선).
- **주의**: 파일을 인자로 지정하면 그 파일(단일 방)만 처리된다. 다방 병합은 반드시 인자 없이 실행.
- 방은 출력에서 구분되지 않고 하나로 합쳐진다. taxonomy(멤버 별명·교사)는 프롬어스 기준이라 다른 방 매칭은 약할 수 있다.
```

- [ ] **Step 3: 전체 테스트 스위트**

Run: `python generator/test_parse.py -v && python build/test_merge_hub.py`
Expected: 전부 PASS (`test_parse` 전 클래스 + `test_merge_hub`)

- [ ] **Step 4: 실데이터 end-to-end 최종 확인** (프롬어스 단일 방 = 기존과 동일 출력 회귀)

```bash
cd /Users/haunpapa/Documents/GitHub/fromus-reports
git stash -- chat_kb.json 2>/dev/null || true
python generator/update_archive.py --no-resolve < /dev/null   # 인자 없이 = Downloads 자동 스캔
python -c "import json; b=json.load(open('chat_kb.json'))['build']; print('방기간', b['from'], b['to'], '메시지', b['messages'], '종목', b['stocks'])"
git checkout chat_kb.json 2>/dev/null || true   # 검증용 — 실제 배포는 refresh.sh 로
```
Expected: 오류 없이 build 요약 출력. (실제 프롬어스+타 방을 Downloads에 두면 방 여러 개로 집계됨.)

- [ ] **Step 5: 커밋**

```bash
git add generator/refresh.sh generator/README.md
git commit -m "docs: 다방 병합 사용법(refresh.sh·README)"
```

---

## 완료 기준 (Definition of Done)
- [ ] `python generator/test_parse.py -v` 전부 PASS (기존 + 신규 `TestRoomOf`/`TestMerge`/`TestRoomGuards`/`TestDeterminism`/`TestFindInput` 확장)
- [ ] `python build/test_merge_hub.py` PASS
- [ ] 인자 없이 실행 시 Downloads의 여러 `KakaoTalk_Chat_*` 가 방별로 병합되어 `chat_kb.json` 생성
- [ ] 단일 방(프롬어스만)일 때 출력이 기존과 동일(회귀 없음)
- [ ] chat_kb.json이 PYTHONHASHSEED 무관하게 결정론적
- [ ] `chat_kb.json` 출력에 `room` 미노출(방 무관 유지)
- [ ] 배포는 `./generator/refresh.sh` 로 수행(사람이 chat_kb.json 커밋·push → CI)

## 주의(구현 중)
- `chat_kb.json`은 실행마다 갱신됨 — **검증 단계에서 생성된 것은 커밋하지 말 것**(`git checkout chat_kb.json`). 실제 데이터 배포는 사용자가 `refresh.sh` 로 별도 수행.
- 입력 CSV는 `generator/`에 두지 말 것(`*.csv` gitignore). `~/Downloads` 또는 인자 경로.
- 코드 스타일: 기존 파일의 compact(세미콜론) 스타일을 따르되 테스트는 일반 스타일 허용.
