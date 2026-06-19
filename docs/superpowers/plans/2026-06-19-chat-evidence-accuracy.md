# 채팅 근거 정확도 + 인터랙션 교정 (1단계) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 카드의 채팅 근거를 "실제 의견" 중심으로 재구성하고(시황 노이즈 분리), 멘션 클릭 모달·더보기·뉴스 최신순 정렬을 추가한다.

**Architecture:** `chat_kb.json`은 그대로 두고 소비 단계만 고친다. `merge_hub.py`가 멘션을 의견/관련시황/뉴스로 분리·정렬하고 모달용 `co_stocks`를 주입한다. `hub_template.html`의 `renderChat`을 재작성하고 채팅 전용 모달·더보기 핸들러를 추가한다.

**Tech Stack:** Python 3.11(표준 라이브러리만), stdlib `unittest`, 바닐라 JS(빌드 산출물 `hub.html`).

**Spec:** `docs/superpowers/specs/2026-06-19-chat-evidence-accuracy-design.md`

---

## 파일 구조

| 파일 | 책임 | 변경 |
|---|---|---|
| `merge_hub.py` | chat_kb ↔ KB 병합. 분류·필터·정렬·co_stocks·새 chat 스키마 | 수정 |
| `build/test_merge_hub.py` | merge_hub 순수 로직 단위 테스트 | 신규 |
| `hub_template.html` | `renderChat` 재작성 + 채팅 모달 + 더보기/접기 JS | 수정 |

**테스트 전략 주의**: Python(`merge_hub`)은 TDD(unittest). JS(`hub_template.html`)는 브라우저 테스트 인프라가 없으므로 **빌드 스모크(마커 grep) + 비주얼 확인**으로 검증한다(Task 7).

---

## Task 1: merge_hub 분류·필터·정렬 헬퍼 (TDD)

**Files:**
- Modify: `merge_hub.py`
- Test: `build/test_merge_hub.py` (신규)

- [ ] **Step 1: 실패 테스트 작성** — `build/test_merge_hub.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_hub 순수 로직 단위 테스트 (네트워크 불필요).
실행:  python build/test_merge_hub.py   또는   python -m unittest build.test_merge_hub"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from merge_hub import (  # noqa: E402
    _is_opinion, _name_in, _sort_desc,
)


class TestHelpers(unittest.TestCase):
    def test_is_opinion(self):
        self.assertTrue(_is_opinion({"type": "view"}))
        self.assertTrue(_is_opinion({"type": "position"}))
        self.assertFalse(_is_opinion({"type": "research"}))
        self.assertFalse(_is_opinion({}))

    def test_name_in_matches_name_or_ticker(self):
        m = {"snippet": "엔비디아 +5%, 구글 약보합"}
        self.assertTrue(_name_in(m, "구글", "GOOGL"))
        self.assertTrue(_name_in({"snippet": "GOOGL 목표 300"}, "구글", "GOOGL"))
        self.assertFalse(_name_in({"snippet": "반도체 일반 시황"}, "구글", "GOOGL"))
        self.assertFalse(_name_in({"snippet": None}, "구글", "GOOGL"))

    def test_sort_desc_by_date_safe(self):
        items = [{"date": "2026-04-02"}, {"date": "2026-04-07"}, {}]
        out = _sort_desc(items)
        self.assertEqual([i.get("date", "") for i in out], ["2026-04-07", "2026-04-02", ""])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `python build/test_merge_hub.py`
Expected: FAIL — `ImportError: cannot import name '_is_opinion'`

- [ ] **Step 3: 헬퍼 구현** — `merge_hub.py` 상단(import 직후)에 상수+헬퍼 추가. 기존 `_recent`는 `_sort_desc`로 대체한다.

```python
import json, sys
from collections import Counter, defaultdict

OPINION_TYPES = {"view", "position"}
OPINION_KEEP = 100
MARKET_KEEP = 50
NEWS_KEEP = 50

def _is_opinion(m):
    return m.get("type") in OPINION_TYPES

def _name_in(m, nm, ticker):
    sn = m.get("snippet", "") or ""
    return (nm in sn) or (bool(ticker) and ticker in sn)

def _sort_desc(items):
    # date 키가 없어도 안전하게 내림차순(최신순)
    return sorted(items, key=lambda x: x.get("date", "") or "", reverse=True)
```

기존 `_recent` 함수(정의부)를 삭제한다. (사용처는 `_chat_block` 한 곳 — Task 3에서 교체)

- [ ] **Step 4: 통과 확인**

Run: `python build/test_merge_hub.py`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add merge_hub.py build/test_merge_hub.py
git commit -m "feat: merge_hub 분류·필터·정렬 헬퍼 + 테스트"
```

---

## Task 2: co_stocks 동일메시지 맵 (TDD)

**Files:** Modify `merge_hub.py` · Test `build/test_merge_hub.py`

- [ ] **Step 1: 실패 테스트 추가** — `build/test_merge_hub.py`의 import에 `_build_comention_map, _augment` 추가하고 클래스 추가

```python
from merge_hub import (  # noqa: E402
    _is_opinion, _name_in, _sort_desc, _build_comention_map, _augment,
)

DAILY = {"date": "2026-04-01", "sharer": "김병철", "type": "research",
         "stance": "자료", "snippet": "특징종목: 엔비디아 상승, 구글 약보합"}

def _chat_fixture():
    return {
        "구글":   {"ticker": "GOOGL", "mentions": [dict(DAILY)]},
        "엔비디아": {"ticker": "NVDA",  "mentions": [dict(DAILY)]},
    }

class TestCoStocks(unittest.TestCase):
    def test_comention_map_groups_same_message(self):
        comap = _build_comention_map(_chat_fixture())
        key = (DAILY["date"], DAILY["sharer"], DAILY["snippet"][:40])
        self.assertEqual(comap[key], {"구글", "엔비디아"})

    def test_augment_adds_others_excludes_self(self):
        comap = _build_comention_map(_chat_fixture())
        aug = _augment(dict(DAILY), "구글", comap)
        self.assertEqual(aug["co_stocks"], ["엔비디아"])     # 자기 자신 제외
        self.assertNotIn("구글", aug["co_stocks"])

    def test_augment_is_immutable(self):
        m = dict(DAILY)
        comap = _build_comention_map(_chat_fixture())
        _augment(m, "구글", comap)
        self.assertNotIn("co_stocks", m)                    # 원본 미오염
```

- [ ] **Step 2: 실패 확인** — Run: `python build/test_merge_hub.py` → FAIL (ImportError)

- [ ] **Step 3: 구현** — `merge_hub.py`에 추가

```python
def _build_comention_map(cstocks):
    msg2names = defaultdict(set)
    for nm, cs in cstocks.items():
        for m in cs.get("mentions", []):
            key = (m.get("date"), m.get("sharer"), (m.get("snippet", "") or "")[:40])
            msg2names[key].add(nm)
    return msg2names

def _augment(m, nm, comap):
    key = (m.get("date"), m.get("sharer"), (m.get("snippet", "") or "")[:40])
    co = sorted(comap.get(key, set()) - {nm})
    return {**m, "co_stocks": co}   # 불변 복사 — 원본 멘션 미변경
```

- [ ] **Step 4: 통과 확인** — Run: `python build/test_merge_hub.py` → PASS

- [ ] **Step 5: 커밋**

```bash
git add merge_hub.py build/test_merge_hub.py
git commit -m "feat: merge_hub co_stocks 동일메시지 맵 + 불변 주입"
```

---

## Task 3: _chat_block 새 스키마 + merge() 연결 (TDD)

**Files:** Modify `merge_hub.py:18-23`(`_chat_block`), `merge_hub.py:39-77`(`merge`) · Test `build/test_merge_hub.py`

- [ ] **Step 1: 실패 테스트 추가** — 분류·정렬·상한·멱등성을 end-to-end로

```python
from merge_hub import merge  # noqa: E402  (기존 import 줄에 합쳐도 됨)

def _full_chat():
    return {
        "build": {}, "themes": {}, "glossary": [], "readings": [],
        "actions": [], "strategy": [], "targets": [], "qna": [], "news": [],
        "stocks": {
            "구글": {"count": 3, "ticker": "GOOGL", "market": "US", "themes": [], "targets": [],
                "mentions": [
                    {"date": "2026-04-07", "sharer": "탱이", "type": "view", "stance": "watch", "snippet": "구글 300불 회복"},
                    {"date": "2026-04-02", "sharer": "탱이", "type": "view", "stance": "bullish", "snippet": "AI 인프라가 핵심"},
                    dict(DAILY),  # research + 구글 포함 → market_news
                ],
                "news": [
                    {"date": "2026-04-05", "title": "구글 TPU", "outlet": "한경", "url": "http://x"},
                    {"date": "2026-04-08", "title": "브로드컴 계약", "outlet": "매경", "url": "http://y"},
                ]},
            "엔비디아": {"count": 2, "ticker": "NVDA", "market": "US", "themes": [], "targets": [],
                "mentions": [
                    dict(DAILY),  # 구글과 동일 메시지 → co_stocks
                    {"date": "2026-03-20", "sharer": "X", "type": "research", "stance": "자료", "snippet": "반도체 일반 시황"},  # 엔비디아 미포함 → 제외
                ],
                "news": []},
        },
    }

def _kb():
    return {"build": {}, "stocks": [{"name": "구글", "count": 5, "mentions": []}], "glossary": []}

class TestChatBlock(unittest.TestCase):
    def test_classification_and_sort(self):
        kb, _ = merge(_kb(), _full_chat())
        g = next(s for s in kb["stocks"] if s["name"] == "구글")["chat"]
        self.assertEqual([o["date"] for o in g["opinions"]], ["2026-04-07", "2026-04-02"])  # view 2개, 최신순
        self.assertEqual(len(g["market_news"]), 1)                                          # research+구글포함 1개
        self.assertEqual([n["date"] for n in g["news"]], ["2026-04-08", "2026-04-05"])      # 뉴스 최신순

    def test_market_news_excludes_unrelated_research(self):
        kb, _ = merge(_kb(), _full_chat())  # 엔비디아는 chat_only로 추가됨
        nv = next(s for s in kb["stocks"] if s["name"] == "엔비디아")["chat"]
        self.assertEqual(len(nv["market_news"]), 1)  # DAILY만, "반도체 일반 시황"은 제외

    def test_co_stocks_in_block(self):
        kb, _ = merge(_kb(), _full_chat())
        g = next(s for s in kb["stocks"] if s["name"] == "구글")["chat"]
        self.assertEqual(g["market_news"][0]["co_stocks"], ["엔비디아"])

    def test_idempotent(self):
        kb = _kb()
        merge(kb, _full_chat())
        snap = json.dumps(kb, sort_keys=True, ensure_ascii=False)
        merge(kb, _full_chat())  # 2회차
        self.assertEqual(json.dumps(kb, sort_keys=True, ensure_ascii=False), snap)

    def test_input_chat_unchanged(self):
        chat = _full_chat()
        before = json.dumps(chat, sort_keys=True, ensure_ascii=False)
        merge(_kb(), chat)
        self.assertEqual(json.dumps(chat, sort_keys=True, ensure_ascii=False), before)

    def test_caps(self):
        chat = _full_chat()
        chat["stocks"]["구글"]["mentions"] = [
            {"date": "2026-01-01", "type": "view", "stance": "bullish", "snippet": "x"} for _ in range(105)
        ]
        kb, _ = merge(_kb(), chat)
        g = next(s for s in kb["stocks"] if s["name"] == "구글")["chat"]
        self.assertEqual(len(g["opinions"]), 100)   # 105개 입력 → OPINION_KEEP=100 으로 잘림(상한 실검증)
```

- [ ] **Step 2: 실패 확인** — Run: `python build/test_merge_hub.py` → FAIL (스키마 키 `opinions` 없음 등)

- [ ] **Step 3: `_chat_block` 재작성** — `merge_hub.py` 기존 `_chat_block`(현 L18-23)을 교체

```python
def _chat_block(cs, nm, comap, with_targets=True):
    ments = cs.get("mentions", [])
    ticker = cs.get("ticker", "") or ""
    opinions = [_augment(m, nm, comap)
                for m in _sort_desc([m for m in ments if _is_opinion(m)])][:OPINION_KEEP]
    market = [_augment(m, nm, comap)
              for m in _sort_desc([m for m in ments
                                   if (not _is_opinion(m)) and _name_in(m, nm, ticker)])][:MARKET_KEEP]
    news = _sort_desc(cs.get("news", []))[:NEWS_KEEP]
    blk = {"count": cs.get("count", 0), "signals": len(ments),
           "stance": stance_summary(ments),
           "opinions": opinions, "market_news": market, "news": news}
    if with_targets:
        blk["targets"] = cs.get("targets", [])[:5]
    return blk
```

- [ ] **Step 4: `merge()` 연결** — `merge_hub.py` `merge()` 안에서 comap 1회 빌드 후 두 호출처를 교체

```python
def merge(kb, chat):
    _strip_prior_chat(kb)
    cstocks = chat.get("stocks", {})
    comap = _build_comention_map(cstocks)        # ← 추가
    report_names = set()
    for s in kb.get("stocks", []):
        nm = s.get("name"); report_names.add(nm)
        cs = cstocks.get(nm)
        if cs:
            s["chat"] = _chat_block(cs, nm, comap)   # ← 시그니처 변경
            s["has_chat"] = True
    added = 0
    for nm, cs in cstocks.items():
        if nm in report_names: continue
        if cs.get("count", 0) < 2 and not cs.get("mentions"): continue
        kb.setdefault("stocks", []).append({"name": nm, "count": 0, "source": "chat",
            "market": cs.get("market", ""), "ticker": cs.get("ticker", ""), "themes": cs.get("themes", []),
            "mentions": [], "sectors": [], "supply_tags": [], "targets": cs.get("targets", [])[:5],
            "chat": _chat_block(cs, nm, comap),       # ← 시그니처 변경
            "has_chat": True, "chat_only": True})
        added += 1
    # 3) glossary 병합 / 4) 최상위 chat 섹션 — 기존 L63-77 그대로 (변경 없음)
    # ... (기존 코드 유지)
```
> **편집 경계(중요)**: 위에서 실제로 바꾸는 것은 ① `comap = _build_comention_map(cstocks)` 1줄 추가, ② 두 곳의 `_chat_block(cs)` → `_chat_block(cs, nm, comap)` 호출 교체뿐이다. glossary 병합·최상위 chat 섹션(기존 L63-77)과 반환부는 **변경하지 않는다** — 함수 전체를 재작성하지 말 것.
> `__main__` 블록의 출력 통계(`merged['chat']['actions']` 등)는 기존대로 동작. 단 `linked` 계산은 그대로 둔다.

- [ ] **Step 5: 통과 확인** — Run: `python build/test_merge_hub.py` → PASS (전체)

- [ ] **Step 6: 커밋**

```bash
git add merge_hub.py build/test_merge_hub.py
git commit -m "feat: merge_hub 의견/관련시황/뉴스 분리 새 chat 스키마 + 멱등·불변 검증"
```

---

## Task 4: renderChat 재작성 (마크업 + 더보기 데이터 속성)

**Files:** Modify `hub_template.html:922-929` (`renderChat`)

JS 단위테스트 인프라가 없으므로 이 Task부터는 **구현 후 Task 7 스모크로 검증**한다.

- [ ] **Step 1: `renderChat` 교체** — 의견(초기 3) / 관련시황(접힘) / 뉴스(초기 4, 외부링크) + 더보기 트리거. 항목에 `data-chat-stock·data-chat-kind·data-chat-idx`(절대 인덱스) 부여. 기존 `esc`/`fmtDate` 헬퍼 재사용.

```javascript
const CHAT_INIT_OP = 3, CHAT_INIT_NEWS = 4, CHAT_MORE = 10;

function chatMentionRow(s, kind, m, idx){
  return `<div class="mention chat-clk" data-chat-stock="${esc(s.name)}" data-chat-kind="${kind}" data-chat-idx="${idx}" style="cursor:pointer">
    <span class="md">${esc(fmtDate(m.date))}</span>
    <span class="src-pill" style="background:#f5f3ff;color:#7c3aed">💬 ${esc(m.sharer||'')}</span>
    <span>${esc((m.snippet||'').slice(0,120))}${(m.co_stocks&&m.co_stocks.length)?` <span style="color:var(--text-4)">+${m.co_stocks.length}</span>`:''}</span></div>`;
}
function chatNewsRow(n){
  return `<div class="mention"><span class="md">${esc(fmtDate(n.date))}</span>
    <span class="src-pill 테마">뉴스</span>
    <span>${esc(n.title)} <a class="src" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.outlet||'열기')}↗</a></span></div>`;
}
function renderChat(s){
  const c=s.chat; if(!c) return '';
  const st=c.stance||{};
  const badge=`<span style="color:#7c3aed">강세 ${st.bullish||0} · 약세 ${st.bearish||0} · 관망 ${st.watch||0}</span>`;
  const ops=c.opinions||[], mkt=c.market_news||[], nws=c.news||[];
  const opHtml = ops.slice(0,CHAT_INIT_OP).map((m,i)=>chatMentionRow(s,'opinion',m,i)).join('')
    || '<div style="font-size:11.5px;color:var(--text-4)">개별 의견 없음</div>';
  const opMore = ops.length>CHAT_INIT_OP
    ? `<div class="chat-more" data-chat-stock="${esc(s.name)}" data-chat-kind="opinion" data-chat-shown="${CHAT_INIT_OP}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 의견 ${ops.length-CHAT_INIT_OP}건 더보기</div>` : '';
  const mktBlock = mkt.length
    ? `<details class="chat-mkt" style="margin-top:6px"><summary style="cursor:pointer;color:#16a34a;font-size:11.5px">📰 관련 시황 ${mkt.length}건</summary>
        <div class="chat-mkt-body" data-chat-stock="${esc(s.name)}" data-chat-shown="0"></div></details>` : '';
  const nwHtml = nws.slice(0,CHAT_INIT_NEWS).map(chatNewsRow).join('');
  const nwMore = nws.length>CHAT_INIT_NEWS
    ? `<div class="chat-more-news" data-chat-stock="${esc(s.name)}" data-chat-shown="${CHAT_INIT_NEWS}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 뉴스 ${nws.length-CHAT_INIT_NEWS}건 더보기</div>` : '';
  return `<div style="margin-top:10px;border-top:1px dashed var(--border);padding-top:8px">
    <div style="font-size:11.5px;font-weight:700;color:#7c3aed;margin-bottom:4px">💬 채팅 근거 · ${c.count}회 · ${badge}</div>
    <div style="font-size:11px;color:var(--text-3);margin-bottom:3px">💡 의견</div>${opHtml}${opMore}
    ${mktBlock}
    ${nws.length?`<div style="font-size:11px;color:var(--text-3);margin:5px 0 3px">📰 뉴스(최신순)</div>${nwHtml}${nwMore}`:''}
  </div>`;
}
```

> 관련 시황(`<details>`)은 펼칠 때 채워지므로 Task 5 핸들러가 `summary` toggle을 처리한다. 의견/시황/뉴스 "더보기"도 Task 5에서 위임 처리.

- [ ] **Step 2: 임시 확인** — 문법 점검을 위해 빌드만:

Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -3`
Expected: 정상 종료, `chat_kb.json merged -- stocks +N` 출력

- [ ] **Step 3: 커밋**

```bash
git add hub_template.html
git commit -m "feat: renderChat 의견/관련시황/뉴스 분리 + 더보기 마크업"
```

---

## Task 5: 더보기/접기 핸들러 + co_stocks 카운트

**Files:** Modify `hub_template.html` (스크립트 영역, `STOCK_BY_NAME` 정의 L1184 이후)

- [ ] **Step 1: 위임 핸들러 추가** — `STOCK_BY_NAME` 정의(L1184) 다음 줄에 추가. **반드시 `data-chat-*` 속성만** 사용(기존 L1071 `data-stock` 핸들러와 분리).

```javascript
// ── 채팅 더보기/접기 (data-chat-* 만 처리; data-stock 전역 핸들러와 분리) ──
function chatArr(stockName, kind){
  const s=STOCK_BY_NAME[stockName]; if(!s||!s.chat) return [];
  return kind==='opinion' ? (s.chat.opinions||[]) : (s.chat.market_news||[]);
}
document.addEventListener('click', e=>{
  // 1) 의견 더보기
  const opMore=e.target.closest('.chat-more');
  if(opMore){
    const name=opMore.dataset.chatStock, shown=+opMore.dataset.chatShown;
    const arr=chatArr(name,'opinion'); const next=Math.min(arr.length, shown+CHAT_MORE);
    const frag=arr.slice(shown,next).map((m,i)=>chatMentionRow(STOCK_BY_NAME[name],'opinion',m,shown+i)).join('');
    opMore.insertAdjacentHTML('beforebegin',frag);
    opMore.dataset.chatShown=next;
    if(next>=arr.length) opMore.remove(); else opMore.textContent=`＋ 의견 ${arr.length-next}건 더보기`;
    return;
  }
  // 2) 뉴스 더보기
  const nwMore=e.target.closest('.chat-more-news');
  if(nwMore){
    const name=nwMore.dataset.chatStock, shown=+nwMore.dataset.chatShown;
    const s=STOCK_BY_NAME[name], arr=(s&&s.chat&&s.chat.news)||[];
    const next=Math.min(arr.length, shown+CHAT_MORE);
    nwMore.insertAdjacentHTML('beforebegin', arr.slice(shown,next).map(chatNewsRow).join(''));
    nwMore.dataset.chatShown=next;
    if(next>=arr.length) nwMore.remove(); else nwMore.textContent=`＋ 뉴스 ${arr.length-next}건 더보기`;
    return;
  }
});
// 관련 시황 <details> 최초 펼침 시 채우기 + 더보기
document.addEventListener('toggle', e=>{
  const d=e.target.closest('details.chat-mkt'); if(!d||!d.open) return;
  const body=d.querySelector('.chat-mkt-body'); if(!body || +body.dataset.chatShown>0) return;
  const name=body.dataset.chatStock, arr=chatArr(name,'market');
  const n=Math.min(arr.length,5);
  body.innerHTML=arr.slice(0,n).map((m,i)=>chatMentionRow(STOCK_BY_NAME[name],'market',m,i)).join('')
    + (arr.length>n?`<div class="chat-more" data-chat-stock="${esc(name)}" data-chat-kind="market" data-chat-shown="${n}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 시황 ${arr.length-n}건 더보기</div>`:'');
  body.dataset.chatShown=n;
}, true);
```

> 시황 더보기(`data-chat-kind="market"`)는 위 click 핸들러 1)의 `.chat-more`가 kind를 보고 처리하도록 분기 추가:
> `.chat-more` 처리에서 `const kind=opMore.dataset.chatKind||'opinion';` 로 읽고 `chatArr(name,kind)` 사용, 라벨도 kind에 맞춰(`의견`/`시황`) 출력.

- [ ] **Step 2: `.chat-more` 핸들러를 kind 일반화** — Step 1의 의견 더보기 블록을 kind 대응으로 보정(위 노트 반영). `chatMentionRow`의 kind 인자도 `kind` 변수 전달.

- [ ] **Step 3: 빌드 확인** — Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2` → 정상

- [ ] **Step 4: 커밋**

```bash
git add hub_template.html
git commit -m "feat: 채팅 의견/시황/뉴스 더보기 + 관련시황 lazy 펼침 핸들러"
```

---

## Task 6: 채팅 모달 (HTML + open/close + ESC)

**Files:** Modify `hub_template.html` — 모달 DOM은 `#reportModal` 컨테이너 닫는 `</div>` 다음에, JS는 `closeReport`/`$$('[data-rclose]')` 정의 **근처**에 추가. **앵커는 라인 번호가 아닌 식별자 기준**(라인은 편집·빌드로 drift됨)

- [ ] **Step 1: 모달 DOM 추가** — `#reportModal` `</div>`(L617) 다음 줄. `.rmodal` **CSS 클래스만 재사용**, 별도 컨테이너.

```html
<div class="rmodal" id="chatModal" role="dialog" aria-modal="true">
  <div class="rmodal-bd" data-cmclose></div>
  <div class="rmodal-box" style="height:auto;max-height:88vh">
    <div class="rmodal-head">
      <span class="rmodal-kind" style="color:#7c3aed;background:#f5f3ff;border-color:#e9d5ff">💬 채팅</span>
      <span class="rmodal-title" id="cmTitle"></span>
      <button class="rmodal-close" aria-label="닫기" data-cmclose>✕</button>
    </div>
    <div class="rmodal-body" id="cmBody" style="padding:16px 18px;overflow:auto"></div>
  </div>
</div>
```

- [ ] **Step 2: open/close + ESC JS 추가** — `$$('[data-rclose]')...`(L1540) 위 또는 `closeReport` 다음

```javascript
let cmBodyOverflow='';
function openChatModal(stockName, kind, idx){
  const arr = chatArr(stockName, kind);
  const m = arr[idx]; if(!m) return;
  $('#cmTitle').innerHTML = `${esc(stockName)} <span class="rm-date">${esc(fmtDate(m.date))} · ${esc(m.sharer||'')} · ${esc(m.stance||'')}</span>`;
  const co = (m.co_stocks||[]).map(n=>`<span class="tag" data-stock="${esc(n)}">${esc(n)}</span>`).join('');
  const s = STOCK_BY_NAME[stockName]||{};
  const tl = ((s.chat&&s.chat.opinions)||[]).filter(o=>o.sharer===m.sharer)
    .map(o=>`<div style="font-size:11.5px;color:var(--text-3)">· ${esc(fmtDate(o.date))} ${esc(o.stance||'')} — ${esc((o.snippet||'').slice(0,60))}</div>`).join('');
  const news = ((s.chat&&s.chat.news)||[]).slice(0,4)
    .map(n=>`<div style="font-size:11.5px"><span class="md">${esc(fmtDate(n.date))}</span> ${esc(n.title)} <a class="src" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.outlet||'열기')}↗</a></div>`).join('');
  $('#cmBody').innerHTML = `
    <div style="background:var(--surface-2);border-radius:8px;padding:12px;line-height:1.6;font-size:13px">${esc(m.snippet||'')}
      <div style="font-size:10.5px;color:var(--text-4);margin-top:6px">※ 현재 180자 요약 — 원문 전체는 2단계 예정</div></div>
    ${co?`<div style="font-size:11px;font-weight:700;color:var(--text-3);margin-top:12px">함께 언급 종목</div><div>${co}</div>`:''}
    ${tl?`<div style="font-size:11px;font-weight:700;color:var(--text-3);margin-top:12px">${esc(m.sharer||'')} · ${esc(stockName)} 발언 타임라인</div>${tl}`:''}
    ${news?`<div style="font-size:11px;font-weight:700;color:var(--text-3);margin-top:12px">관련 뉴스</div>${news}`:''}`;
  $('#chatModal').classList.add('open');
  cmBodyOverflow=document.body.style.overflow; document.body.style.overflow='hidden';
}
function closeChatModal(){
  const cm=$('#chatModal'); if(!cm.classList.contains('open'))return;
  cm.classList.remove('open');
  document.body.style.overflow=cmBodyOverflow||'';
}
$$('[data-cmclose]').forEach(el=>el.addEventListener('click',closeChatModal));
document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&$('#chatModal').classList.contains('open')){e.stopPropagation();closeChatModal();} },true);
// 멘션 클릭 → 모달 (data-chat-idx 가진 항목)
document.addEventListener('click',e=>{
  const row=e.target.closest('.chat-clk'); if(!row) return;
  if(e.target.closest('a')) return;  // 내부 링크는 그대로
  openChatModal(row.dataset.chatStock, row.dataset.chatKind, +row.dataset.chatIdx);
});
```

> 모달 안 `data-stock` 칩은 기존 L1071 핸들러가 처리(해당 종목으로 이동) — 의도된 동작.

- [ ] **Step 3: 빌드 확인** — Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2` → 정상

- [ ] **Step 4: 커밋**

```bash
git add hub_template.html
git commit -m "feat: 채팅 멘션 클릭 모달(전문·함께언급·타임라인·뉴스) + ESC/닫기"
```

---

## Task 7: 통합 스모크 + 비주얼 검증

**Files:** 없음(검증만)

- [ ] **Step 1: 전체 테스트** — Run: `python build/test_merge_hub.py` → PASS

- [ ] **Step 2: 빌드 + 마커 검증**

```bash
python build_hub.py --src . --out hub.html --json knowledge_base.json
grep -c "renderChat\|openChatModal\|chat-clk\|data-chat-idx" hub.html   # >0
python -c "import json;d=json.load(open('knowledge_base.json'));print('chat_merged:',d['build'].get('chat_merged'));import itertools;s=[x for x in d['stocks'] if x.get('chat')][0];print('keys:',list(s['chat'].keys()))"
# 기대: chat_merged: True / keys 에 opinions·market_news·news 포함
```

- [ ] **Step 3: 데이터 정합 스폿체크** — 구글 카드 opinions가 모두 의견(view/position)인지, market_news가 종목명 포함인지 1건 확인

```bash
python -c "
import json;d=json.load(open('knowledge_base.json'))
g=[x for x in d['stocks'] if x['name']=='구글'][0]['chat']
print('opinions',len(g['opinions']),'market',len(g['market_news']),'news',len(g['news']))
print('news 최신순?', [n['date'] for n in g['news']]==sorted([n['date'] for n in g['news']],reverse=True))
"
```

- [ ] **Step 4: 비주얼 확인** — 브라우저에서 `hub.html` 열어 종목 카드 펼침 → 의견/관련시황(▾)/뉴스, 더보기, 멘션 클릭 모달, ESC 닫기 동작 확인. **특히 동일 시황이 2개+ 종목에 붙은 케이스 1건**(예: 시황 멘션이 있는 종목)을 골라 멘션의 `+N` 배지와 모달의 "함께 언급 종목" 칩이 표시되는지 확인(#2 co_stocks 경로 회귀 방지). (@superpowers:verification-before-completion)

- [ ] **Step 5: 산출물 커밋 제외 확인** — `hub.html`·`knowledge_base.json`은 CI가 재생성하는 빌드 산출물. 로컬 검증용이며 **커밋하지 않는다**(메모리 규칙). 소스(`merge_hub.py`·`hub_template.html`·테스트)만 커밋됨을 확인.

```bash
git status --porcelain   # hub.html/knowledge_base.json 변경은 commit 대상 아님
```

---

## 완료 기준
- `python build/test_merge_hub.py` 전부 통과(분류·co_stocks·정렬·멱등·불변·상한)
- 빌드된 `hub.html`에 renderChat/모달/더보기 마커 존재, `chat_merged:true`
- 종목 카드가 의견 우선 + 관련시황 접힘 + 뉴스 최신순으로 렌더, 멘션 클릭 시 모달
- 소스 3파일만 커밋(빌드 산출물 제외)
