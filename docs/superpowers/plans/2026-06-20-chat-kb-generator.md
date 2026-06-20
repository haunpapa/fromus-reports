# chat_kb 생성기 2단계-A 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chat_kb 생성 파이프라인을 리포 `generator/` 에 보관하고, CSV 입력 지원과 의견 원문(full) 보존을 추가해 채팅 근거 모달에서 전문을 볼 수 있게 한다.

**Architecture:** zip 의 로컬 파이프라인(update_archive·chat_to_kb·fromus_taxonomy) 3개를 `generator/` 에 버전관리한다. `update_archive.py` 에 `parse_csv`/`find_input` 를 추가해 txt/csv 를 동일 msgs 스키마로 처리하고, 통합블록을 재작성해 `chat_kb.json` 을 **리포 루트**에만 쓴다(병합은 기존 CI `build_hub.py → merge_hub.merge` 가 전담, merge_hub 무변경). 원문은 `strategy()` signal 에 `full` 을 싣고 `chat_to_kb` 가 **의견(view/position) mention 에만** 복사하며, `hub_template.html` 모달이 `m.full` 을 표시한다.

**Tech Stack:** Python 3(stdlib: csv, datetime, glob, json, re, unittest), 바닐라 JS 템플릿(hub_template.html), GitHub Actions(build.yml — 변경 없음).

**선행 사실(spec §1 실측):**
- 리포 루트 `chat_kb.json`(2.55MB) 추적됨, `build_hub.py`(L1186-1204)가 `from merge_hub import merge` 로 소비, `build.yml` 은 `build_hub.py` 만 실행.
- 현재 파이프라인은 `public=False`(실명 산출), 익명화 미적용. A 도 실명 유지(회귀 0).
- 편집은 **함수명·식별자 기준**(라인번호는 참고치, 편집 시 밀림).
- 테스트는 **stdlib unittest** 직접 실행(`python <test>.py`), CI 에 테스트 스텝 없음(로컬 회귀).

**소스 위치(복사 원본):** `/tmp/onto/update_archive.py`, `/tmp/onto/지식허브_통합/chat_to_kb.py`, `/tmp/onto/지식허브_통합/fromus_taxonomy.py`. (zip 추출본. `/tmp` 휘발 시 `~/Downloads/온톨로지_데이터.zip` 재압축.)

---

## Task 1: generator/ 파이프라인 보관 + 빌드산출물 ignore

**Files:**
- Create: `generator/update_archive.py` (복사) · `generator/chat_to_kb.py` (복사) · `generator/fromus_taxonomy.py` (복사)
- Create: `generator/.gitignore`

- [ ] **Step 1: 3개 스크립트를 generator/ 로 복사**

```bash
cd /Users/haunpapa/Documents/GitHub/fromus-reports
mkdir -p generator
cp /tmp/onto/update_archive.py generator/update_archive.py
cp /tmp/onto/지식허브_통합/chat_to_kb.py generator/chat_to_kb.py
cp /tmp/onto/지식허브_통합/fromus_taxonomy.py generator/fromus_taxonomy.py
```

- [ ] **Step 2: generator/.gitignore 작성 (로컬 실행 산출물 커밋 금지)**

`generator/.gitignore`:
```gitignore
# 로컬 실행 산출물 — 커밋 금지 (chat_kb.json 은 리포 루트에 별도 생성)
# 입력 CSV 는 generator/ 에 두지 말 것(*.csv 로 git 침묵 무시됨) — 인자로 경로 전달
온톨로지_데이터/
*.html
*.jsonl
*.csv
resolve_cache.json
__pycache__/
```

- [ ] **Step 3: import 위생 확인 (모듈 import 부작용 없음)**

Run:
```bash
cd /Users/haunpapa/Documents/GitHub/fromus-reports
python -c "import sys; sys.path.insert(0,'generator'); import update_archive, chat_to_kb, fromus_taxonomy; print('OK', hasattr(update_archive,'parse'), hasattr(chat_to_kb,'build'))"
```
Expected: `OK True True` (네트워크·파일생성 없이 즉시 종료. `main()`/`input()` 은 `if __name__=="__main__"` 가드 안).

- [ ] **Step 4: Commit**

```bash
git add generator/update_archive.py generator/chat_to_kb.py generator/fromus_taxonomy.py generator/.gitignore
git commit -m "feat: 채팅 생성 파이프라인 generator/ 보관 (update_archive·chat_to_kb·fromus_taxonomy)"
```

---

## Task 2: CSV 입력 — parse_csv + find_input + main 분기/빈가드 (TDD)

**Files:**
- Create: `generator/test_parse.py`
- Modify: `generator/update_archive.py` (상단 import 에 `datetime`; `find_txt` → `find_input`; `parse_csv` 신규; `main()` 입력선택·빈가드)

- [ ] **Step 1: 실패 테스트 작성 — parse_csv / find_input**

`generator/test_parse.py`:
```python
# -*- coding: utf-8 -*-
import os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_archive as U

CSV_SAMPLE = (
    "﻿Date,User,Message\n"
    '2026-03-19 17:43:30,"대성","대성님이 들어왔습니다."\n'
    '2026-03-20 09:05:00,"ㄱ 이혜나","삼성전자 좋게 봅니다.\n추가 매수 고려"\n'
    '깨진행없음\n'
    ',"빈날짜","날짜 없는 행"\n'
)

class TestParseCsv(unittest.TestCase):
    def _write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        f.write(text); f.close(); return f.name

    def test_schema_and_fields(self):
        msgs = U.parse_csv(self._write(CSV_SAMPLE))
        # 헤더 스킵 + 열부족('깨진행없음') + 빈날짜 행 skip → 정상 2건
        self.assertEqual(len(msgs), 2)
        m0, m1 = msgs
        self.assertEqual(m0["date"], "2026-03-19")
        self.assertEqual(m0["time"], "17:43")          # 초 절단
        self.assertEqual(m0["weekday"], "목요일")        # 2026-03-19 = 목
        self.assertEqual(m0["sender"], "대성")
        self.assertEqual(m0["idx"], 0)
        self.assertEqual(m1["idx"], 1)
        # lines 키(list) 필수 + body == join(lines), 멀티라인 보존
        self.assertIsInstance(m1["lines"], list)
        self.assertEqual(m1["body"], "\n".join(m1["lines"]))
        self.assertIn("추가 매수 고려", m1["body"])
        self.assertEqual(len(m1["lines"]), 2)

    def test_empty_returns_list(self):
        self.assertEqual(U.parse_csv(self._write("﻿Date,User,Message\n")), [])

class TestFindInput(unittest.TestCase):
    def test_arg_priority_and_prefix(self):
        d = tempfile.mkdtemp()
        old = os.path.join(d, "KakaoTalk_old.csv"); open(old, "w").close()
        time.sleep(0.02)
        new = os.path.join(d, "KakaoTalk_new.csv"); open(new, "w").close()
        out = os.path.join(d, "뉴스_전체아카이브.csv"); open(out, "w").close()  # 출력형(미선택)
        # 명시 인자 우선
        self.assertEqual(U.find_input(["prog", new]), new)

if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/haunpapa/Documents/GitHub/fromus-reports && python generator/test_parse.py`
Expected: FAIL (`AttributeError: module 'update_archive' has no attribute 'parse_csv'` / `find_input`).

- [ ] **Step 3: 상단 import 에 datetime 추가**

`generator/update_archive.py` 상단 `import os, re, sys, csv, json, time, glob, base64` 줄 바로 아래에 추가:
```python
import datetime
```

> ⚠️ Step 4(find_txt 제거)와 Step 5(호출부 `find_txt()`→`find_input()` 수정)는 **반드시 연속 적용**하라. Step 4만 적용한 중간 상태에서 `main()` 을 실행하면 `NameError: find_txt` 가 난다(import-only 위생체크는 main 미실행이라 안전).

- [ ] **Step 4: parse_csv + find_input 구현 (기존 find_txt 교체)**

`generator/update_archive.py` 의 `def find_txt():` 함수 전체를 아래로 **교체**:
```python
WEEKDAY_KO = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]

def parse_csv(path):
    """카카오톡 CSV(Date,User,Message) → parse(txt) 와 동일 msgs 스키마."""
    msgs = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:                      # 헤더 1행 스킵
        if len(row) < 3:                       # 열 부족 방어
            continue
        ds = row[0] or ""
        try:                                   # 깨진/비ISO 날짜 행 skip
            d = datetime.date(int(ds[0:4]), int(ds[5:7]), int(ds[8:10]))
        except (ValueError, IndexError):
            continue
        body = row[2]
        lines = body.split("\n")               # link_records 가 m["lines"] 순회 → 필수
        msgs.append({"idx": len(msgs), "date": ds[:10], "weekday": WEEKDAY_KO[d.weekday()],
                     "time": ds[11:16], "sender": row[1].strip(),
                     "body": "\n".join(lines), "lines": lines})
    return msgs

def find_input(argv=None):
    """txt/csv 입력 자동 선택. 명시 인자 우선 → cwd·~/Downloads 의 KakaoTalk_* 최신."""
    argv = sys.argv if argv is None else argv
    for a in argv[1:]:
        if a.lower().endswith((".txt", ".csv")) and os.path.exists(a):
            return a
    cands = []
    for root in (os.getcwd(), os.path.expanduser("~/Downloads")):
        for pat in ("KakaoTalk_*.txt", "KakaoTalk_*.csv"):   # 출력 CSV 오선택 방지(prefix 제한)
            cands += glob.glob(os.path.join(root, pat))
    cands = sorted(set(cands), key=os.path.getmtime, reverse=True)
    return cands[0] if cands else None
```

- [ ] **Step 5: main() 입력선택 + 분기 + 빈가드**

`generator/update_archive.py` `main()` 의 아래 4줄
```python
    txt=find_txt()
    if not txt: print("[!] 카카오톡 .txt 를 찾지 못했습니다. 이 폴더에 넣고 실행하세요."); return
    print(f"▶ 입력: {os.path.basename(txt)}")
    msgs=parse(txt); links=link_records(msgs); enrich(links)
```
를 아래로 교체:
```python
    path=find_input()
    if not path: print("[!] 카카오톡 .txt/.csv 를 찾지 못했습니다. 인자로 경로를 주거나 ~/Downloads 에 두세요."); return
    print(f"▶ 입력: {os.path.basename(path)}")
    msgs = parse_csv(path) if path.lower().endswith(".csv") else parse(path)
    if not msgs: print("[!] 메시지가 비어 있습니다(파싱 0건)."); return
    links=link_records(msgs); enrich(links)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python generator/test_parse.py`
Expected: PASS (parse_csv·find_input 테스트 OK).

- [ ] **Step 7: Commit**

```bash
git add generator/update_archive.py generator/test_parse.py
git commit -m "feat: CSV 입력 지원 — parse_csv + find_input(txt/csv 자동) + 빈입력 가드"
```

---

## Task 3: 원문 보존 — strategy full + chat_to_kb 게이팅 (TDD)

**Files:**
- Modify: `generator/test_parse.py` (full 테스트 추가)
- Modify: `generator/update_archive.py` (`strategy()` signal 에 `full`)
- Modify: `generator/chat_to_kb.py` (의견 mention 에만 `full`)

- [ ] **Step 1: 실패 테스트 추가 — strategy full + chat_to_kb 게이팅**

`generator/test_parse.py` 의 `if __name__` 위에 추가(상단에 `import chat_to_kb as C` 도 추가):
```python
class TestFull(unittest.TestCase):
    def _msg(self, idx, body):
        return {"idx": idx, "date": "2026-03-20", "weekday": "금요일",
                "time": "09:00", "sender": "ㄱ 이혜나", "body": body, "lines": body.split("\n")}

    def test_strategy_full(self):
        alias = U.ENTITIES[list(U.ENTITIES)[0]]["al"][0]   # 실재 alias(하드코딩 금지)
        bull = U.BULL[0]
        body = f"{alias} 관련 {bull} 라고 봅니다.\n둘째 줄 유지 https://x.co/aaa"
        sig = U.strategy([self._msg(0, body)])
        self.assertTrue(sig, "signal 이 생성되어야 함(실재 alias+키워드)")
        s = sig[0]
        self.assertIn("full", s)
        self.assertLessEqual(len(s["full"]), 1500)
        self.assertIn("\n", s["full"])              # 개행 보존
        self.assertNotIn("http", s["full"])          # URL 제거

    def test_mention_full_opinion_only(self):
        # view(의견) 시그널엔 full, research(자료) 시그널엔 full 없음
        view_sig = {"date":"2026-03-20","time":"09:00","sharer":"ㄱ 이혜나",
                    "entities":["삼성전자"],"themes":[],"stance":"bullish","type":"view",
                    "snippet":"좋게 봅니다","full":"좋게 봅니다\n장기 보유"}
        res_sig = {**view_sig, "type":"research"}
        msgs = [self._msg(0, "x")]
        kb = C.build(msgs, [], [view_sig, res_sig])
        ms = kb["stocks"]["삼성전자"]["mentions"]
        view_m = [m for m in ms if m["type"]=="view"][0]
        res_m  = [m for m in ms if m["type"]=="research"][0]
        self.assertEqual(view_m.get("full"), "좋게 봅니다\n장기 보유")
        self.assertNotIn("full", res_m)

    def test_pii_guard_warns_not_blocks(self):
        # 의식적 한계 인지용: full 에 긴 숫자열(전화/계좌) 노출 시 경고만(차단 아님)
        import re as _re
        sig = {"date":"2026-03-20","time":"09:00","sharer":"ㄱ 이혜나","entities":["삼성전자"],
               "themes":[],"stance":"bullish","type":"view","snippet":"연락처","full":"연락처 01012345678"}
        kb = C.build([self._msg(0,"x")], [], [sig])
        leaked = [m for m in kb["stocks"]["삼성전자"]["mentions"] if _re.search(r"\d{8,}", m.get("full",""))]
        if leaked:
            print(f"[PII 경고] full 에 긴 숫자열 노출 {len(leaked)}건 — 후속 마스킹 검토")
        self.assertTrue(True)   # 차단 아님(인지용)

class TestParseTxtGolden(unittest.TestCase):
    def test_txt_unchanged(self):
        import tempfile
        txt = ("--------------- 2026년 3월 19일 목요일 ---------------\n"
               "[대성] [오후 5:43] 첫 줄\n둘째 줄\n")
        f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        f.write(txt); f.close()
        msgs = U.parse(f.name)
        self.assertEqual(len(msgs), 1)
        m = msgs[0]
        self.assertEqual((m["date"], m["time"], m["weekday"], m["sender"]),
                         ("2026-03-19", "17:43", "목요일", "대성"))
        self.assertIsInstance(m["lines"], list)
        self.assertIn("둘째 줄", m["body"])
```
주의: `삼성전자` 가 `T._CANON_ALIGN`/`STOCK_META` 에서 canon 으로 유지되는지 확인. 다르면 `kb["stocks"]` 키를 `C.CANON("삼성전자")` 로 조회. (clean_title 기반 news 제목 검증은 전체 파이프라인 의존이라 Task 8 Step 2 스모크에서 확인.)

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `python generator/test_parse.py`
Expected: FAIL (`'full' not in s` / `view_m.get("full")` is None).

- [ ] **Step 3: strategy() 에 full 추가**

`generator/update_archive.py` `strategy()` 의 `sig.append({...})` 에서
```python
            "snippet":re.sub(r"\s+"," ",text)[:220],"core":m["sender"] in CORE,"teacher":m["sender"] in TEACHERS})
```
를 아래로 교체:
```python
            "snippet":re.sub(r"\s+"," ",text)[:220],
            "full":re.sub(r"[ \t]+"," ",text).strip()[:1500],
            "core":m["sender"] in CORE,"teacher":m["sender"] in TEACHERS})
```
(`text` 는 이미 `URLpat.sub("",body).strip()` — URL 제거됨. `[ \t]+` 만 정리해 개행 보존.)

- [ ] **Step 4: chat_to_kb.build mention 게이팅**

`generator/chat_to_kb.py` build() 의
```python
    for s in signals:
        for e in s["entities"]:
            st=S(e)
            st["mentions"].append({"date":s["date"],"sharer":s["sharer"],"source":"chat",
                "stance":s["stance"],"type":s["type"],"snippet":s["snippet"][:180]})
```
를 아래로 교체:
```python
    for s in signals:
        for e in s["entities"]:
            st=S(e)
            ment={"date":s["date"],"sharer":s["sharer"],"source":"chat",
                  "stance":s["stance"],"type":s["type"],"snippet":s["snippet"][:180]}
            if s.get("type") in ("view","position"):   # 의견만 원문 보존(research 제외)
                ment["full"]=s.get("full","")
            st["mentions"].append(ment)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python generator/test_parse.py`
Expected: PASS (전체).

- [ ] **Step 6: Commit**

```bash
git add generator/update_archive.py generator/chat_to_kb.py generator/test_parse.py
git commit -m "feat: 의견 원문(full) 보존 — strategy full(1500자·개행) + chat_to_kb view/position 게이팅"
```

---

## Task 4: 통합블록 재작성 — chat_kb.json 을 리포 루트에만

**Files:**
- Modify: `generator/update_archive.py` (`main()` 끝 지식허브 통합블록)

- [ ] **Step 1: 통합블록 교체**

`generator/update_archive.py` 의 아래 블록(주석 `# ===== 지식허브 통합 ...` 부터 그 `try/except` 끝까지)
```python
    # ===== 지식허브 통합 (지식허브_통합/ 폴더가 있으면 chat_kb.json + 병합본 생성) =====
    try:
        intdir=P("지식허브_통합")
        if os.path.isdir(intdir):
            if intdir not in sys.path: sys.path.insert(0,intdir)
            import fromus_taxonomy, chat_to_kb, merge_hub
            kb=chat_to_kb.build(msgs, links, sig)
            json.dump(kb, open(os.path.join(intdir,"chat_kb.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
            done="chat_kb.json"
            kbp=os.path.join(intdir,"knowledge_base.json")
            if os.path.exists(kbp):
                try:
                    base=json.load(open(kbp,encoding="utf-8"))
                    merged,added=merge_hub.merge(base, kb)
                    json.dump(merged, open(os.path.join(intdir,"knowledge_base.merged.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
                    done+=" + knowledge_base.merged.json(채팅종목+{})".format(added)
                except Exception as e2:
                    done+=" (병합 건너뜀: {})".format(str(e2)[:40])
            print(f"▶ 지식허브 통합: {done}")
    except Exception as e:
        print(f"  (지식허브 통합 건너뜀: {str(e)[:60]})")
```
를 아래로 교체(반드시 `uniq=dedup(links)` 이후 위치 유지 — clean_title 의존):
```python
    # ===== chat_kb.json 생성 (리포 루트, public=False=실명 유지). 병합은 CI build_hub.py 전담 =====
    try:
        import chat_to_kb
        kb=chat_to_kb.build(msgs, links, sig)
        REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out=os.path.join(REPO_ROOT,"chat_kb.json")
        json.dump(kb, open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"▶ chat_kb.json 생성: {out} (stocks {len(kb['stocks'])})")
    except Exception as e:
        print(f"  (chat_kb.json 생성 실패: {str(e)[:80]})")
```

- [ ] **Step 2: import 위생 재확인 (merge_hub 비import)**

Run:
```bash
cd /Users/haunpapa/Documents/GitHub/fromus-reports
python -c "import sys; sys.path.insert(0,'generator'); import update_archive; print('OK')"
grep -n "merge_hub\|지식허브_통합\|knowledge_base.merged" generator/update_archive.py || echo "정리 완료(잔존 없음)"
```
Expected: `OK` + 잔존 참조 없음(있으면 안 됨).

- [ ] **Step 3: Commit**

```bash
git add generator/update_archive.py
git commit -m "refactor: 통합블록 재작성 — chat_kb.json 리포 루트 기록, 구버전 merge_hub 자체병합 제거"
```

---

## Task 5: merge_hub full 통과 테스트 (merge_hub 무변경 검증)

**Files:**
- Modify: `build/test_merge_hub.py` (full 통과 테스트 추가)

- [ ] **Step 1: 기존 테스트 구조 파악**

Run: `sed -n '1,40p' build/test_merge_hub.py` 로 import·기존 fixture(예: `_full_chat`/`_chat`) 패턴 확인. 새 테스트는 동일 스타일(stdlib unittest) 사용.

- [ ] **Step 2: full 통과 테스트 추가**

`build/test_merge_hub.py` 에 아래 테스트 클래스 추가(merge_hub import 경로는 파일 상단 기존 방식 따름):
```python
class TestFullPassthrough(unittest.TestCase):
    def test_full_flows_to_opinions_and_research_safe(self):
        import merge_hub
        kb = {"stocks": [{"name": "삼성전자", "ticker": "005930"}], "sectors": []}
        chat = {"build": {}, "stocks": {"삼성전자": {"count": 2, "ticker": "005930", "mentions": [
            {"date": "2026-03-20", "sharer": "ㄱ 이혜나", "source": "chat",
             "stance": "bullish", "type": "view", "snippet": "좋게 봅니다", "full": "좋게 봅니다\n장기 보유"},
            {"date": "2026-03-19", "sharer": "키움", "source": "chat",
             "stance": "bullish", "type": "research", "snippet": "삼성전자 리서치"},  # full 없음
        ], "news": [], "targets": []}},
        "themes": {}, "news": [], "targets": [], "actions": [], "strategy": [],
        "qna": [], "readings": [], "glossary": []}
        merged, _ = merge_hub.merge(kb, chat)
        s = next(x for x in merged["stocks"] if x["name"] == "삼성전자")
        ops = s["chat"]["opinions"]
        self.assertEqual(ops[0].get("full"), "좋게 봅니다\n장기 보유")   # full 통과
        # research(market_news)는 full 없어도 안전(KeyError 없이 통과)
        for m in s["chat"]["market_news"]:
            self.assertNotIn("full", m)
```

- [ ] **Step 3: 테스트 실행 (merge_hub 코드 무변경, 통과해야 함)**

Run: `cd /Users/haunpapa/Documents/GitHub/fromus-reports && python build/test_merge_hub.py`
Expected: PASS (기존 + 신규 전부). merge_hub.py 는 한 줄도 안 고침.

- [ ] **Step 4: Commit**

```bash
git add build/test_merge_hub.py
git commit -m "test: chat full 필드 merge_hub 통과 검증(의견 full 전파·research 누락 안전)"
```

---

## Task 6: hub_template 모달 — 전문 표시 + pre-wrap + 안내문구 제거

**Files:**
- Modify: `hub_template.html` (`openChatModal` 의 `#cmBody`)

- [ ] **Step 1: 모달 본문 교체**

`hub_template.html` `openChatModal` 의 `$('#cmBody').innerHTML = ` 템플릿에서
```javascript
    <div style="background:var(--surface-2);border-radius:8px;padding:12px;line-height:1.6;font-size:13px">${esc(m.snippet||'')}
      <div style="font-size:10.5px;color:var(--text-4);margin-top:6px">※ 현재 180자 요약 — 원문 전체는 2단계 예정</div></div>
```
를 아래로 교체(`m.full||m.snippet` + `white-space:pre-wrap` + 안내 div 제거):
```javascript
    <div style="background:var(--surface-2);border-radius:8px;padding:12px;line-height:1.6;font-size:13px;white-space:pre-wrap">${esc(m.full||m.snippet||'')}</div>
```
**나머지 snippet 사용처는 절대 변경 금지**(전역치환 금지): 모달 타임라인 `o.snippet.slice(0,60)`, `renderChat` 카드 `slice(0,120)`, 섹터 요약, 검색 인덱스·결과. `full` 은 이 #cmBody 한 곳만.

- [ ] **Step 2: 빌드해서 hub.html 생성(로컬 검증용, /tmp 출력 — tracked 파일 미오염)**

Run: `cd /Users/haunpapa/Documents/GitHub/fromus-reports && python build_hub.py --src . --out /tmp/hub_check.html --json /tmp/kb_check.json 2>&1 | tail -3`
Expected: 빌드 성공(`chat_kb.json merged ...` 포함). **tracked `hub.html`/`knowledge_base.json` 는 건드리지 않음**(검증엔 /tmp 산출물로 충분).

- [ ] **Step 3: playwright 검증 (전문·안내제거·콘솔)**

기존 chat_kb.json 에는 `full` 이 아직 없으므로(Task 8 재생성 전), 폴백으로 snippet 표시 + 안내문구 사라짐 + 콘솔 에러 없음을 확인. (full 실표시 검증은 Task 8 재생성 후.)
- `mcp__playwright__browser_navigate` → `file:///tmp/hub_check.html`
- 종목 펼침 → 의견 채팅 근거 클릭 → 모달 open
- `browser_evaluate`: `getComputedStyle($('#cmBody div')).whiteSpace === 'pre-wrap'`, 모달 텍스트에 `'2단계 예정'` 없음
- `browser_console_messages`: 에러 0

- [ ] **Step 4: Commit**

```bash
git add hub_template.html
git commit -m "feat: 채팅 근거 모달 전문 표시 — m.full 폴백 + pre-wrap + 180자 안내 제거"
```
(`hub_template.html` 만 커밋. /tmp 로 빌드했으므로 tracked `hub.html`/`knowledge_base.json` 는 dirty 아님 — `git status` 로 확인.)

---

## Task 7: generator/README.md (실행 절차 문서)

**Files:**
- Create: `generator/README.md`

- [ ] **Step 1: README 작성**

`generator/README.md`:
```markdown
# chat_kb 생성기 (로컬 전용)

카카오톡 export(`.txt`/`.csv`) → `chat_kb.json`(리포 루트) 생성 파이프라인.
네이버 링크 해제(네트워크)·온톨로지 뷰어를 포함하므로 **로컬에서만** 실행한다(CI 미실행).

## 실행
```bash
# 리포 루트에서 실행 권장
python generator/update_archive.py "~/Downloads/KakaoTalk_Chat_..._프롬어스_*.csv"
# 인자 없으면 cwd·~/Downloads 의 최신 KakaoTalk_* 자동 탐색
python generator/update_archive.py
```
→ 리포 루트 `chat_kb.json` 생성(의견 view/position mention 에 `full` 원문 포함).

## 배포 흐름
1. 위 명령으로 리포 루트 `chat_kb.json` 갱신.
2. `chat_kb.json` 을 **사람이 직접 커밋**(`build.yml` auto-commit 대상 아님).
3. CI(`build.yml`)가 `build_hub.py → merge_hub.merge(chat_kb.json)` 로 `knowledge_base.json` in-place 병합 → Pages 배포.

## 테스트
```bash
python generator/test_parse.py     # parse_csv·find_input·full (단위)
python build/test_merge_hub.py     # merge full 통과 (통합)
```

## 주의
- `chat_kb.json` 은 리포 루트에 쓰인다(generator/ 아님). 그 외 산출물(온톨로지_데이터/·뷰어 HTML·jsonl)은 `generator/.gitignore` 로 제외.
- 현재 `public=False`(실명 산출). 공개 익명화/본문 PII 마스킹은 후속 과제.
- txt 와 csv 는 메시지/멤버 카운트가 다르다(csv 가 시스템메시지 포함) — `build` 메타 수치 차이는 정상.
```

- [ ] **Step 2: Commit**

```bash
git add generator/README.md
git commit -m "docs: generator README — 로컬 실행·배포 흐름·테스트"
```

---

## Task 8: 스모크 — chat_kb.json 재생성 + 통합 검증 (로컬, 데이터 갱신)

> ⚠️ 이 태스크는 **네트워크(네이버 해제) + 대용량 데이터 커밋**(chat_kb.json 2.5MB+)을 포함한다. 최신 CSV(`~/Downloads/KakaoTalk_Chat_*프롬어스*.csv`, 06-19)로 재생성하므로 full 추가 + **데이터 최신화**가 함께 일어난다(큰 diff). chat_kb.json 커밋 전 사용자에게 diff 규모를 알리고 확인받는다.

**Files:**
- Modify(데이터): 리포 루트 `chat_kb.json`

- [ ] **Step 1: 최신 CSV 로 생성 실행**

Run:
```bash
cd /Users/haunpapa/Documents/GitHub/fromus-reports
LATEST=$(ls -t ~/Downloads/KakaoTalk_Chat_*프롬어스*.csv | head -1)
python generator/update_archive.py "$LATEST" < /dev/null 2>&1 | tail -5
```
Expected: `▶ chat_kb.json 생성: .../chat_kb.json (stocks N)`. (네트워크 끊김 시 `--no-resolve` 추가 — 뉴스 제목 품질만 저하.)
> ⚠️ `__main__` 끝에 `input("Enter 키로 닫기")` 프롬프트가 있다 → **반드시 `< /dev/null` 로 foreground 실행**(비대화형에서 EOFError 자동 통과). `run_in_background` 금지(무한 대기 위험). 부작용 산출물(온톨로지_데이터/·뷰어 HTML·resolve_cache.json)은 generator/ 에 떨어져 `.gitignore` 로 제외됨.

- [ ] **Step 2: chat_kb.json 에 의견 full 존재·research 부재 확인**

Run:
```bash
python -c "import json; d=json.load(open('chat_kb.json')); \
ms=[m for s in d['stocks'].values() for m in s['mentions']]; \
v=[m for m in ms if m['type'] in ('view','position')]; r=[m for m in ms if m['type']=='research']; \
print('의견', len(v), 'full보유', sum('full' in m for m in v)); \
print('자료', len(r), 'full보유', sum('full' in m for m in r)); \
nt=[n.get('title','') for n in d.get('news',[])][:3]; print('news제목샘플', nt)"
```
Expected: 의견 full보유 == 의견 수(>0), 자료 full보유 == 0. news 제목 샘플이 보일러플레이트 제거된 형태(clean_title 적용 — 통합블록이 dedup 이후 실행됨 확인).

- [ ] **Step 3: 병합 통과 스모크 (단독 경로)**

Run:
```bash
python merge_hub.py knowledge_base.json chat_kb.json 2>&1 | tail -3
python -c "import json; d=json.load(open('knowledge_base.merged.json')); \
ops=[o for s in d['stocks'] if s.get('chat') for o in s['chat'].get('opinions',[])]; \
print('opinions', len(ops), 'full보유', sum('full' in o for o in ops))"
rm -f knowledge_base.merged.json   # 스모크 산출물 정리(커밋 금지)
```
Expected: opinions full보유 > 0.

- [ ] **Step 4: 전체 테스트 재확인**

Run: `python generator/test_parse.py && python build/test_merge_hub.py`
Expected: 둘 다 PASS.

- [ ] **Step 5: /tmp 빌드 + playwright full 실표시 검증 (정본 knowledge_base.json 은 CI 가 재생성)**

Run: `python build_hub.py --src . --out /tmp/hub_full.html --json /tmp/kb_full.json 2>&1 | tail -2`
그 후 playwright(`file:///tmp/hub_full.html`): 의견 모달에서 **180자 초과 전문**(개행 반영) 표시, `2단계 예정` 없음, 콘솔 에러 0.
(tracked `knowledge_base.json`/`hub.html` 미오염 — push 시 CI 가 chat_kb.json 으로 재빌드.)

- [ ] **Step 6: 데이터 커밋 (사용자 확인 후)**

`git status` 로 **chat_kb.json 만** 스테이징(hub.html·knowledge_base.json·온톨로지_데이터/ 등 산출물 제외 — generator/.gitignore 및 수동 확인).
```bash
git add chat_kb.json
git commit -m "data: chat_kb.json 재생성 — 의견 원문(full) 포함 + 최신 카톡(06-19) 반영"
```

---

## 완료 기준 (Definition of Done)
- `generator/` 에 3 스크립트 + README + .gitignore + test_parse.py, import 부작용 없음.
- `python generator/test_parse.py`·`python build/test_merge_hub.py` 전부 PASS.
- `chat_kb.json` 의 view/position mention 에 `full` 존재, research 에 부재.
- 모달에서 의견 전문 표시(개행), `2단계 예정` 문구 사라짐, 콘솔 에러 0.
- `merge_hub.py`·`build_hub.py`·`build.yml` 무변경.
- main 머지 후 CI 빌드 그린 + Pages 반영.

## 머지/배포 (구현 완료 후)
1. `feat/chat-kb-generator` 회귀: `git fetch origin main && git merge origin/main` (충돌 시 해결).
2. 전체 테스트 재실행.
3. main 머지 → push → `gh run watch` 로 CI 그린 확인 → Pages 반영 확인.
4. 메모리 `chat-evidence-accuracy.md` 2단계-A 완료 갱신, 남은 후속(B 정확귀속·익명화·full PII) 명시.
