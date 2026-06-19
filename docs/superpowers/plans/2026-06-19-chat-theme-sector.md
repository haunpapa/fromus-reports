# 채팅 테마 ↔ 섹터 결합 (D) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 리포트 섹터 카드에 이름이 매칭되는 채팅 테마의 stance 집계·논의 종목 칩·대표 의견을 결합한다.

**Architecture:** `merge_hub.py`가 `kb.chat.themes`를 이름 리스트 → 상세 dict(opinions_count·stance·대표의견)로 집계하고, `hub_template.html` `sectorCard`가 `s.theme` 매칭 시 채팅 근거를 렌더한다.

**Tech Stack:** Python 3.11(stdlib), stdlib unittest, 바닐라 JS.

**Spec:** `docs/superpowers/specs/2026-06-19-chat-theme-sector-design.md`

**테스트 전략**: merge_hub는 TDD(unittest). sectorCard(JS)는 빌드 스모크 + playwright 비주얼(실제 getComputedStyle/렌더로 검증).

---

## 파일 구조
- `merge_hub.py`: `THEME_OP_KEEP` 상수 + `_theme_blocks(kb, chat_themes)` + `merge()`의 `kb.chat.themes` 상세화
- `build/test_merge_hub.py`: 테마 집계 테스트
- `hub_template.html`: `sectorCard`에 채팅 근거 블록 + `.sc-chat` CSS

---

## Task 1: merge_hub 테마 집계 (TDD)

**Files:** Modify `merge_hub.py`(상수+`_theme_blocks`+`merge` L112), Test `build/test_merge_hub.py`

- [ ] **Step 1: 실패 테스트 추가** — `build/test_merge_hub.py` import에 `_theme_blocks` 추가 후 클래스

```python
from merge_hub import (  # noqa: E402
    _is_opinion, _name_in, _sort_desc, _build_comention_map, _augment, merge, _is_bot, _theme_blocks,
)

class TestThemeBlocks(unittest.TestCase):
    def _kb_with_chat(self):
        # 섹터 2개(반도체·기타), chat 종목 chat.opinions 보유
        return {
            "stocks": [
                {"name": "엔비디아", "chat": {"opinions": [
                    {"date": "2026-04-07", "sharer": "탱이", "stance": "bullish", "snippet": "엔비 좋다"},
                    {"date": "2026-04-02", "sharer": "탱이", "stance": "watch", "snippet": "관망"},
                ]}},
                {"name": "마이크론", "chat": {"opinions": [
                    {"date": "2026-04-08", "sharer": "문지영", "stance": "bullish", "snippet": "마이크론 강세"},
                ]}},
                {"name": "현대차", "chat": {"opinions": [
                    {"date": "2026-04-05", "sharer": "김철수", "stance": "bearish", "snippet": "현대차 약세"},
                ]}},
            ],
            "sectors": [{"theme": "반도체·메모리"}, {"theme": "자동차·현대차그룹"}],
        }

    def _chat_themes(self):
        return {
            "반도체·메모리": {"theme": "반도체·메모리", "count": 99, "stocks": ["엔비디아", "마이크론"], "mentions": []},
            "자동차·현대차그룹": {"theme": "자동차·현대차그룹", "count": 30, "stocks": ["현대차"], "mentions": []},
            "에너지·정유": {"theme": "에너지·정유", "count": 50, "stocks": ["엔비디아"], "mentions": []},  # 섹터에 없음(미집계)
        }

    def test_only_matched_themes(self):
        tb = _theme_blocks(self._kb_with_chat(), self._chat_themes())
        self.assertEqual(set(tb.keys()), {"반도체·메모리", "자동차·현대차그룹"})  # 에너지·정유 제외(섹터 없음)

    def test_stance_recount_and_count(self):
        tb = _theme_blocks(self._kb_with_chat(), self._chat_themes())
        semi = tb["반도체·메모리"]
        self.assertEqual(semi["opinions_count"], 3)                       # 엔비디아 2 + 마이크론 1
        self.assertEqual(semi["stance"], {"bullish": 2, "bearish": 0, "watch": 1})

    def test_opinions_have_stock_and_sorted(self):
        tb = _theme_blocks(self._kb_with_chat(), self._chat_themes())
        ops = tb["반도체·메모리"]["opinions"]
        self.assertTrue(all("stock" in o for o in ops))                   # stock 부착
        self.assertEqual([o["date"] for o in ops], ["2026-04-08", "2026-04-07", "2026-04-02"])  # 최신순

    def test_cap_applies_to_list_not_stance(self):
        kb = self._kb_with_chat()
        kb["stocks"][0]["chat"]["opinions"] = [
            {"date": f"2026-01-{i:02d}", "sharer": "x", "stance": "bullish", "snippet": "n"} for i in range(1, 13)
        ]  # 엔비디아 12개
        tb = _theme_blocks(kb, self._chat_themes())
        semi = tb["반도체·메모리"]
        self.assertLessEqual(len(semi["opinions"]), 8)                    # 대표 의견 ≤8
        self.assertEqual(semi["stance"]["bullish"], 12 + 1)               # stance는 상한 전 전체(엔비12+마이크론1)

    def test_stock_counted_independently_per_theme(self):
        # 실데이터: 한 종목이 여러 매칭 테마에 동시 소속(예: 마이크론 → 반도체 + 금융)
        kb = self._kb_with_chat()
        ct = self._chat_themes()
        ct["자동차·현대차그룹"]["stocks"] = ["현대차", "마이크론"]   # 마이크론을 두 테마에
        tb = _theme_blocks(kb, ct)
        semi_stocks = [o["stock"] for o in tb["반도체·메모리"]["opinions"]]
        auto_stocks = [o["stock"] for o in tb["자동차·현대차그룹"]["opinions"]]
        self.assertIn("마이크론", semi_stocks)
        self.assertIn("마이크론", auto_stocks)   # 두 테마에 독립 집계(공유·누적 아님)
```

- [ ] **Step 2: 실패 확인** — Run: `python build/test_merge_hub.py` → FAIL (ImportError `_theme_blocks`)

- [ ] **Step 3: `_theme_blocks` 구현** — `merge_hub.py`에 상수+함수 추가(`stance_summary` 근처)

```python
THEME_OP_KEEP = 8

def _theme_blocks(kb, chat_themes):
    """채팅 테마 중 리포트 섹터와 이름 매칭되는 것만, 종목 chat.opinions를 모아 집계."""
    by_name = {s.get("name"): s for s in kb.get("stocks", [])}
    sector_themes = {sec.get("theme") for sec in kb.get("sectors", [])}
    out = {}
    for tname, tinfo in chat_themes.items():
        if tname not in sector_themes:   # 매칭 섹터 없으면 제외
            continue
        ops = []
        for nm in tinfo.get("stocks", []):
            s = by_name.get(nm)
            if not s:
                continue
            for op in (s.get("chat", {}).get("opinions") or []):
                ops.append({**op, "stock": nm})   # 출처 종목 부착(불변)
        ops = _sort_desc(ops)
        st = Counter(o.get("stance") for o in ops if o.get("stance") in ("bullish", "bearish", "watch"))
        out[tname] = {
            "opinions_count": len(ops),
            "stocks": tinfo.get("stocks", []),
            "stance": {"bullish": st["bullish"], "bearish": st["bearish"], "watch": st["watch"]},
            "opinions": ops[:THEME_OP_KEEP],
        }
    return out
```

- [ ] **Step 4: `merge()` 연결** — `merge_hub.py` L112 `"themes":list(...)` 교체

```python
        "stocks_added":added,"themes":_theme_blocks(kb, chat.get("themes", {}))}
```
> `kb["stocks"]`(종목 chat 포함)과 `kb["sectors"]`가 이 시점에 모두 존재하므로 순서 안전. 종목 `chat.opinions`는 이미 봇 제외·view/position.

- [ ] **Step 5: 통과 확인** — Run: `python build/test_merge_hub.py` → PASS (전체)

- [ ] **Step 6: 커밋**
```bash
git add merge_hub.py build/test_merge_hub.py
git commit -m "feat: merge_hub 채팅 테마↔섹터 집계 (stance 재카운트·대표의견·매칭만)"
```

---

## Task 2: sectorCard 채팅 근거 렌더

**Files:** Modify `hub_template.html` (`sectorCard` 함수 + `.sc-chat` CSS)

- [ ] **Step 1: sectorCard에 채팅 블록 추가** — `sectorCard` 안에서 `ct` 조회 후 본문/펼침에 삽입

```javascript
function sectorCard(s,i){
  const stocks=(s.stocks||[]).slice(0,12);
  const tl=(s.mentions||[]).slice().reverse().map(m=>`
    <div class="row"><span class="d">${esc(fmtDate(m.date))}</span> · <b>${esc(m.name)}</b>${m.sub?` <span style="color:var(--text-3)">(${esc(m.sub)})</span>`:''} ${srcLink(m.id)}
      ${m.note?`<div style="color:var(--text-3);margin-top:3px">${esc(m.note.slice(0,180))}</div>`:''}</div>`).join('');
  // ── 채팅 테마 결합 (D.chat.themes 가 dict 일 때만; 기존 빌드는 이름 리스트) ──
  const tmap = (D.chat && !Array.isArray(D.chat.themes)) ? (D.chat.themes||{}) : {};
  const ct = tmap[s.theme];
  const chatHead = ct ? `<div class="sc-chat">💬 채팅 의견 ${ct.opinions_count}건 · <span style="color:#7c3aed">강세 ${ct.stance.bullish} · 약세 ${ct.stance.bearish} · 관망 ${ct.stance.watch}</span>
    <div class="sc-chat-stocks">${(ct.stocks||[]).map(n=>`<span class="tag" data-stock="${esc(n)}">${esc(n)}</span>`).join('')}</div></div>` : '';
  const chatDetail = (ct && (ct.opinions||[]).length) ? `<div class="sc-chat-ops"><div style="font-size:11.5px;font-weight:700;color:#7c3aed;margin-bottom:3px">💬 대표 의견</div>${ct.opinions.map(o=>`<div class="mention"><span class="md">${esc(fmtDate(o.date))}</span> <span class="tag" data-stock="${esc(o.stock)}">${esc(o.stock)}</span> <span style="color:var(--text-3)">${esc(o.sharer||'')}</span> ${esc((o.snippet||'').slice(0,120))}</div>`).join('')}</div>` : '';
  return `<div class="scard">
    <div class="scard-head" onclick="this.parentNode.querySelector('.scard-detail').classList.toggle('open')">
      <span class="scard-rank serif">${i+1}</span>
      <span class="scard-name">${esc(s.theme)}</span>
      <button class="star ${isWatched('sector',s.theme)?'on':''}" data-watch="sector:${esc(s.theme)}" title="워치리스트에 추가/제거" onclick="event.stopPropagation();toggleWatchEl(this)">${isWatched('sector',s.theme)?'★':'☆'}</button>
      <span class="count-badge">${s.count}회</span>
    </div>
    <div class="intensity"><i style="width:${Math.round((s.count||0)/SECMAX*100)}%"></i></div>
    <div style="margin:2px 0 8px">${momentumChip(s)}</div>
    <div class="scard-stocks">${stocks.map(n=>`<span class="tag" data-stock="${esc(n)}">${esc(n)}</span>`).join('')||'<span style="font-size:12px;color:var(--text-4)">개별 종목 태그 없음</span>'}</div>
    ${chatHead}
    <span class="toggle" onclick="this.parentNode.querySelector('.scard-detail').classList.toggle('open')">▾ 시점별 전개 ${(s.mentions||[]).length}건</span>
    <div class="scard-detail"><div class="mini-tl">${tl}</div>${chatDetail}</div>
  </div>`;
}
```
> 종목 칩은 기존 `data-stock` 위임 핸들러가 종목 탭 이동 처리. `chatHead`는 `scard-head`(토글 onclick) 밖이라 충돌 없음.

- [ ] **Step 2: `.sc-chat` CSS 추가** (스타일 영역)

```css
.sc-chat{margin-top:8px;padding-top:8px;border-top:1px dashed var(--border);font-size:11.5px;font-weight:700;color:#7c3aed}
.sc-chat-stocks{margin-top:5px;display:flex;flex-wrap:wrap;gap:4px}
.sc-chat-ops{margin-top:10px;border-top:1px dashed var(--border);padding-top:8px}
.sc-chat-ops .mention .tag{margin:0 4px}
```

- [ ] **Step 3: 빌드 스모크**

Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2`
Then:
```bash
python -c "import json;d=json.load(open('knowledge_base.json'));t=d['chat']['themes'];print('themes dict?',isinstance(t,dict));print('반도체·메모리:',{k:t['반도체·메모리'][k] for k in ['opinions_count','stance']} if isinstance(t,dict) else 'LIST')"
grep -c "sc-chat\|채팅 의견" hub.html   # >0
```
Expected: `themes dict? True`, 반도체·메모리 opinions_count/stance 출력, 마커 >0

- [ ] **Step 4: playwright 비주얼 검증** (@superpowers:verification-before-completion)

HTTP 서버로 `hub.html` 열고 `showTab('sectors')` 후:
- 매칭 섹터(반도체·메모리) `.scard`에 `.sc-chat`이 **실제 렌더**(getComputedStyle display ≠ none), stance 숫자 표시
- 채팅 논의 종목 칩 클릭 → 종목 탭 이동
- 카드 펼침 → `.sc-chat-ops` 대표 의견(날짜·종목·발언자) 표시
- 비매칭 섹터(일별 동적, 예: "오늘의 상한가")엔 `.sc-chat` 없음
- 콘솔 에러 없음(favicon 제외)

- [ ] **Step 5: 커밋** (빌드 산출물 제외)
```bash
git add hub_template.html
git commit -m "feat: 섹터 카드에 채팅 테마 결합(stance·논의종목·대표의견)"
```

---

## 완료 기준
- `python build/test_merge_hub.py` 전체 통과(테마 집계: 매칭만·stance 재카운트·stock 부착·상한 분리)
- `knowledge_base.json`의 `chat.themes`가 상세 dict, 매칭 14개 테마
- 섹터 카드에 채팅 stance·종목 칩·대표 의견 렌더(실제 표시 검증), 비매칭 섹터엔 없음
- 소스(`merge_hub.py`·`hub_template.html`·테스트)만 커밋
