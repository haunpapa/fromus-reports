# 채팅 정확귀속 proximity 게이팅 (2단계-B) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 생성단계에서 채팅 mention 귀속을 "종목 등장 + 주변 ±60자 stance 신호" proximity로 게이팅해 시황 도배(-61%)를 제거하고 종목별 stance를 정확화한다.

**Architecture:** `strategy()`(update_archive)에 `attribute_stocks()` 신규 — find_ents 후보를 ±60 stance 게이팅 + 인접종목 절단 세그먼트로 종목별 stance 계산 → signal에 `stocks=[(canon,stance)]` 추가(기존 `entities`/`stance`는 뷰어 호환 위해 유지). `chat_to_kb.build`의 mention 루프를 `stocks` 기준으로 변경. 소비단계·taxonomy·뷰어 무변경.

**Tech Stack:** Python 3 stdlib(re, unittest). 편집은 **함수명 기준**(라인번호는 참고치).

**선행 사실(spec 실측):**
- `generator/update_archive.py`: 키워드 `POS/VIEWKW/WATCH/BULL/BEAR`(L117-127)·`SRC_MARKERS`(L111)·`find_ents`(L307)·`hit`(L319)·`strategy`(L320, sig.append L339)·`ENTITIES`(canon→{"al":[...]}). `aggregate`/`ontology`는 `s["entities"]`·`s["stance"]`만 사용(stocks 미사용 → 무변경 보장).
- `generator/chat_to_kb.py`: mention 루프(L56-63)는 `s["entities"]` 순회, `S()`/`CANON()`(`_CANON_ALIGN` 정렬). count/테마(L49-54)·targets/news는 `match_stocks`(substring) 독립 경로 → 무변경.
- 테스트: stdlib unittest 직접 실행(`python generator/test_parse.py`).
- spec: `docs/superpowers/specs/2026-06-20-chat-attribution-proximity-design.md` (모든 의사코드 sanity 실측 통과).

---

## 시작 전제 (Task 1 전)

브랜치 `feat/chat-attribution-proximity`(HEAD=`9edeef4b` spec 커밋)에서 시작하고, `git status` 로 추적 변경 없음(clean)을 확인한다 — 다른 브랜치/worktree 의 잔여 적용 방지.

## Task 1: `attribute_stocks` + 경계 헬퍼 + `strategy` stocks 필드 (TDD)

**Files:**
- Modify: `generator/update_archive.py` (`find_ents`/`hit` 다음에 헬퍼·`attribute_stocks` 추가; `strategy`의 sig.append에 `stocks`)
- Modify: `generator/test_parse.py` (`TestAttribute` 추가)

- [ ] **Step 1: 실패 테스트 작성** — `generator/test_parse.py` 의 `if __name__` 위에 추가(상단에 `import update_archive as U` 이미 있음)

```python
class TestAttribute(unittest.TestCase):
    def test_amd_korean_context(self):            # ③ 양성(경계로직 교정 전엔 RED)
        self.assertIn("AMD", U.ENTITIES)
        r = dict(U.attribute_stocks("AMD 추매했어요 좋음", False))
        self.assertIn("AMD", r)

    def test_amdocs_excluded(self):               # ③ 음성(오탐 제외)
        r = dict(U.attribute_stocks("AMDOCS는 통신소프트라 관심", False))
        self.assertNotIn("AMD", r)

    def test_no_signal_excluded(self):            # 단순 언급 → 제외
        r = dict(U.attribute_stocks("오늘 삼성전자 뉴스 봤어", False))
        self.assertNotIn("삼성전자", r)

    def test_far_signal_excluded(self):           # ② stance 멀리(>윈도우) → 제외
        filler = "가" * (U.W_ATTR + 10)
        r = dict(U.attribute_stocks(f"삼성전자{filler}좋게 봅니다", False))
        self.assertNotIn("삼성전자", r)

    def test_per_segment_split(self):             # ⑤ 근접 복수종목 절단
        r = dict(U.attribute_stocks("삼성전자는 손절하고 정리했지만 하이닉스는 추매로 담았습니다", False))
        self.assertEqual(r.get("삼성전자"), "bearish")
        self.assertEqual(r.get("SK하이닉스"), "bullish")

    def test_research_stance_label(self):         # ④ 시황 stance="자료"
        body = U.SRC_MARKERS[0] + " 삼성전자 비중확대 기대"
        r = dict(U.attribute_stocks(body, True))
        if "삼성전자" in r:
            self.assertEqual(r["삼성전자"], "자료")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/haunpapa/Documents/GitHub/fromus-reports && python generator/test_parse.py 2>&1 | tail -6`
Expected: FAIL (`AttributeError: module 'update_archive' has no attribute 'attribute_stocks'`).

- [ ] **Step 3: 헬퍼 + attribute_stocks 구현** — `generator/update_archive.py` 의 `def hit(...)` 다음 줄(= `def strategy` 직전)에 삽입:

```python
W_ATTR = 60
STANCE_SIGNAL = POS + VIEWKW + WATCH + BULL + BEAR   # 귀속 게이팅 신호(%·목표가 제외)

def _ascii_alnum(c):
    return bool(c) and c.isascii() and c.isalnum()

def _alias_spans(body, alias):
    """공백패딩 alias(' AMD','AMD ')는 strip 후 매칭. 영문은 ASCII 영숫자만 경계
       (한글/공백/기호는 경계 통과 → 'AMD 추매' 귀속, 'AMDOCS' 제외). 한글은 substring."""
    surf = alias.strip()
    if not surf:
        return []
    spans = []
    for m in re.finditer(re.escape(surf), body):
        i, j = m.start(), m.end()
        if surf.isascii():
            b = body[i-1] if i > 0 else ""
            a = body[j] if j < len(body) else ""
            if _ascii_alnum(b) or _ascii_alnum(a):
                continue
        spans.append((i, j))
    return spans

def attribute_stocks(body, is_src):
    """find_ents 후보 → ±60 stance 게이팅 + 인접종목 절단 세그먼트로 [(canon, stance)]."""
    cand = list(find_ents(body))
    spans_by = {c: [s for al in ENTITIES[c]["al"] for s in _alias_spans(body, al)] for c in cand}
    marks = sorted((i, j, c) for c, sp in spans_by.items() for (i, j) in sp)
    out = []
    for canon in cand:
        sp = spans_by[canon]
        if not sp:                                              # 경계인식 등장 없음(영문 오탐)
            continue
        gate = " ".join(body[max(0, i-W_ATTR): j+W_ATTR] for (i, j) in sp)
        if not any(k in gate for k in STANCE_SIGNAL):           # 주변 stance 신호 없음 → 도배 제외
            continue
        if is_src:
            stance = "자료"
        else:
            others = sorted(oi for (oi, oj, oc) in marks if oc != canon)
            cut = []                                            # 한국어 후치: 좌=자기 시작, 우=다음 다른종목 시작
            for (i, j) in sp:
                hi = j + W_ATTR
                for oi in others:
                    if oi >= j:
                        hi = min(hi, oi); break
                cut.append(body[i: hi])
            seg = " ".join(cut)
            bu, be, wa = hit(seg, BULL), hit(seg, BEAR), hit(seg, WATCH)
            if len(bu) > len(be): stance = "bullish"
            elif len(be) > len(bu): stance = "bearish"
            elif wa and not (bu or be): stance = "watch"
            elif bu and be: stance = "mixed"
            else: stance = "neutral"
        out.append((canon, stance))
    return out
```
주의: `W_ATTR`/`STANCE_SIGNAL`/헬퍼는 `POS`…`WATCH`(L117-127) 정의 **뒤**, `attribute_stocks`는 `find_ents`/`hit` **뒤**에 와야 한다(이미 그 위치).

- [ ] **Step 4: strategy sig.append 에 stocks 추가** — `strategy()` 의 `sig.append({...})` 에서
```python
            "entities":sorted(ents),"themes":sorted(ths),"stance":stance,"type":stype,
```
를 아래로 교체(entities/stance 유지 + stocks 추가):
```python
            "entities":sorted(ents),"themes":sorted(ths),"stance":stance,"type":stype,
            "stocks":attribute_stocks(body, is_src),
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python generator/test_parse.py 2>&1 | tail -4`
Expected: PASS (`TestAttribute` 6개 포함 전체 OK).

- [ ] **Step 6: Commit**

```bash
git add generator/update_archive.py generator/test_parse.py
git commit -m "feat: 생성단계 정확귀속 — attribute_stocks(±60 proximity + 경계교정 + per-segment stance)"
```

---

## Task 2: `chat_to_kb.build` mention 을 stocks 기준으로 (TDD)

**Files:**
- Modify: `generator/chat_to_kb.py` (mention 루프 L56-63)
- Modify: `generator/test_parse.py` (`TestMentionStocks` 추가)

- [ ] **Step 1: 실패 테스트 작성** — `generator/test_parse.py` 에 추가(상단에 `import chat_to_kb as C`):

```python
class TestMentionStocks(unittest.TestCase):
    def _msg(self, idx, body):
        return {"idx": idx, "date": "2026-03-20", "weekday": "금요일",
                "time": "09:00", "sender": "ㄱ 이혜나", "body": body, "lines": body.split("\n")}

    def test_mention_uses_stocks_per_stance(self):
        sig = {"date": "2026-03-20", "time": "09:00", "sharer": "ㄱ 이혜나",
               "entities": ["삼성전자", "SK하이닉스"], "themes": [], "stance": "mixed", "type": "view",
               "snippet": "삼성 손절 하이닉스 추매", "full": "삼성 손절 하이닉스 추매",
               "stocks": [("삼성전자", "bearish"), ("SK하이닉스", "bullish")]}
        kb = C.build([self._msg(0, "x")], [], [sig])
        ss = kb["stocks"]["삼성전자"]["mentions"][0]
        hh = kb["stocks"]["SK하이닉스"]["mentions"][0]
        self.assertEqual(ss["stance"], "bearish")     # 종목별 stance
        self.assertEqual(hh["stance"], "bullish")
        self.assertEqual(ss.get("full"), "삼성 손절 하이닉스 추매")   # 의견 full 유지

    def test_research_no_full(self):
        sig = {"date": "2026-03-19", "sharer": "키움", "entities": ["삼성전자"], "themes": [],
               "stance": "자료", "type": "research", "snippet": "시황", "full": "시황 전문",
               "stocks": [("삼성전자", "자료")]}
        kb = C.build([self._msg(0, "x")], [], [sig])
        m = kb["stocks"]["삼성전자"]["mentions"][0]
        self.assertEqual(m["type"], "research")
        self.assertNotIn("full", m)                   # research 는 full 없음
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `python generator/test_parse.py 2>&1 | tail -6`
Expected: FAIL (현행 루프가 `s["entities"]` 기반이라 종목별 stance 가 메시지 stance("mixed")로 들어감 → `assertEqual(ss["stance"],"bearish")` 실패).

- [ ] **Step 3: mention 루프 교체** — `generator/chat_to_kb.py` build() 의
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
를 아래로 교체:
```python
    for s in signals:
        for e, st_stance in s.get("stocks", []):       # proximity 귀속 + 종목별 stance
            st=S(e)
            ment={"date":s["date"],"sharer":s["sharer"],"source":"chat",
                  "stance":st_stance,"type":s["type"],"snippet":s["snippet"][:180]}
            if s.get("type") in ("view","position"):   # 의견만 원문 보존(research 제외)
                ment["full"]=s.get("full","")
            st["mentions"].append(ment)
```

- [ ] **Step 3b: 기존 TestFull 픽스처에 `stocks` 추가** (필수 — stocks 키 없는 시그널은 새 루프서 종목 엔트리를 못 만들어 `kb["stocks"]["삼성전자"]` KeyError)

`generator/test_parse.py`:
- `test_mention_full_opinion_only` 의 `view_sig` dict 에 `"stocks":[("삼성전자","bullish")]` 추가(`res_sig = {**view_sig, "type":"research"}` 가 stocks 상속).
- `test_pii_guard_warns_not_blocks` 의 `sig` 끝 `"full":"연락처 01012345678"}` → `"full":"연락처 01012345678","stocks":[("삼성전자","bullish")]}`.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python generator/test_parse.py 2>&1 | tail -4`
Expected: PASS (전체 — 기존 + 신규 TestMentionStocks 2 + 갱신된 TestFull 2).

- [ ] **Step 5: Commit**

```bash
git add generator/chat_to_kb.py generator/test_parse.py
git commit -m "feat: chat_to_kb mention 을 stocks(proximity) 기준으로 — 종목별 stance"
```

---

## Task 3: 재생성 + before/after 정량·소비처 회귀 검증 + 데이터 배포 (컨트롤러 주도)

> ⚠️ 네트워크(네이버 해제) + 대용량 데이터 커밋 포함. 도배가 의도적으로 대폭 줄어드므로(귀속 -61%) 커밋 전 정량·회귀를 반드시 확인하고 사용자에게 규모를 알린다.

**Files:**
- Modify(데이터): 리포 루트 `chat_kb.json`

- [ ] **Step 1: before/after 정량 (도구 재사용)**

`/tmp/compare_attr.py`(경계 교정본)는 현행 baseline·Aw 규칙을 측정한다. 그러나 **실제 산출은 Task 1·2 코드**이므로, 코드 적용 후 실제 재생성으로 검증한다. 먼저 현행 chat_kb.json 통계를 보관:
```bash
cd /Users/haunpapa/Documents/GitHub/fromus-reports
python3 -c "import json;d=json.load(open('chat_kb.json'));ms=[m for s in d['stocks'].values() for m in s['mentions']];print('BEFORE mention',len(ms))"
```

- [ ] **Step 2: 재생성** (Task 1·2 적용 후)

```bash
LATEST=$(ls -t ~/Downloads/KakaoTalk_*.csv | head -1)
python generator/update_archive.py "$LATEST" < /dev/null 2>&1 | tail -6
```
Expected: `chat_kb.json 생성` 성공. **출력에 `생성 실패` 문자열이 없는지 확인**(생성 블록이 `try/except Exception` 이라 예외 시 메시지만 출력하고 exit 0 → 실패 은폐 가능). 네트워크 불안정 시 `--no-resolve` 추가(뉴스 제목 품질만 저하).

- [ ] **Step 3: 귀속 정량 검증 (도배 감소)**

```bash
python3 -c "
import json; d=json.load(open('chat_kb.json'))
ms=[(nm,m) for nm,s in d['stocks'].items() for m in s['mentions']]
from collections import Counter
msg={}
for nm,m in ms:
    k=(m.get('date'),m.get('sharer'),(m.get('snippet','')or'')[:40]); msg.setdefault(k,set()).add(nm)
dup=[len(v) for v in msg.values()]
hit=sum(nm in (m.get('snippet','')or'') for nm,m in ms)
print('AFTER mention',len(ms),'| 종목명포함%',hit*100//len(ms),'| 메시지당 평균%.2f 최대%d'%(sum(dup)/len(dup),max(dup)))
print('type',Counter(m['type'] for _,m in ms))
"
```
Expected: mention 대폭 감소(약 -55~-60%), 종목명포함% 상승(36%→상향), 메시지당 최대 24→~14.

- [ ] **Step 4: 소비처 회귀 (merge 산출)**

```bash
python merge_hub.py knowledge_base.json chat_kb.json 2>&1 | tail -3
python3 -c "
import json, collections; d=json.load(open('knowledge_base.merged.json'))
chatst=[s for s in d['stocks'] if s.get('chat')]
mn=sum(len(s['chat'].get('market_news',[])) for s in chatst)
op=sum(len(s['chat'].get('opinions',[])) for s in chatst)
ce=len(d.get('chat',{}).get('co_edges',[]))
conly=sum(1 for s in d['stocks'] if s.get('chat_only'))
sc=collections.Counter()
for s in chatst:
    for k,v in (s['chat'].get('stance') or {}).items(): sc[k]+=v
print('chat종목',len(chatst),'chat_only',conly,'opinions',op,'market_news',mn,'co_edges',ce,'stance',dict(sc))
"
rm -f knowledge_base.merged.json
```
확인: chat 종목 수 0 붕괴 안 함, opinions/market_news 존재, co_edges 감소(가짜쌍↓), stance 강세/약세 0 아님(mixed 편중 아님). **`chat_only` 종목 수를 현행(약 33개)과 비교** — mention=0 게이팅으로 일부 탈락 가능(`merge_hub` L162 `count<2 and not mentions`), 급감 시 임계/윈도우 재검토.

- [ ] **Step 5: 샘플 수동 검수 + playwright**

```bash
python3 -c "
import json,random; d=json.load(open('chat_kb.json'))
ms=[(nm,m) for nm,s in d['stocks'].items() for m in s['mentions'] if m['type'] in ('view','position')]
import itertools
for nm,m in ms[:12]: print(nm,'|',m['stance'],'|',(m.get('snippet','')[:50]))
"
```
무작위 12건이 실제 그 종목 의견인지 눈으로 확인. 이어서 `/tmp` 빌드 + playwright: `python build_hub.py --src . --out /tmp/hub_b.html --json /tmp/kb_b.json` → 종목 모달 의견이 종목과 일치, 콘솔 에러 0.

- [ ] **Step 6: 전체 테스트 재확인**

Run: `python generator/test_parse.py && python build/test_merge_hub.py`
Expected: 둘 다 PASS.

- [ ] **Step 7: 데이터 커밋 (사용자 확인 후)** — `chat_kb.json` 만 스테이징(산출물 제외)

```bash
git add chat_kb.json
git commit -m "data: chat_kb.json 재생성 — 정확귀속 proximity 적용(도배 제거)"
```
또는 `./generator/refresh.sh` 로 재생성→커밋→배포 일괄(이미 재생성했으면 push만).

---

## 완료 기준 (Definition of Done)
- `python generator/test_parse.py`(TestAttribute·TestMentionStocks 포함)·`python build/test_merge_hub.py` 전부 PASS.
- `chat_kb.json` mention 대폭 감소(-55%대), 종목명포함% 상승, 메시지당 최대 24→~14.
- merge 산출: chat 종목 유지, co_edges 가짜쌍 감소, stance 강세/약세 0 아님.
- 모달 의견이 해당 종목과 실제 일치(샘플 검수).
- `merge_hub.py`/`hub_template.html`/`build.yml`/`aggregate`/`ontology` 무변경.
- main 머지 후 CI 그린 + Pages 반영.

## 비목표(재확인)
종목 사전 통합(ENTITIES↔STOCK_META), LLM, 한글 substring 오탐 근본 제거, 전방 수식 stance — 모두 후속.

## 머지/배포
1. `feat/chat-attribution-proximity` 회귀: `git fetch origin main && git merge origin/main`.
2. 전체 테스트 재실행 → main 머지 → push → `gh run watch` CI 그린 → Pages 확인.
3. 메모리 `chat-evidence-accuracy.md` 2단계-B 완료 갱신.
