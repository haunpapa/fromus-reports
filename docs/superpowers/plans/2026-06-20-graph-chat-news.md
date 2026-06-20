# 관계망 채팅 의견·뉴스 연동 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관계망(graph)에 종목↔종목 동시언급 엣지(채팅 의견 + 뉴스)와 종목 노드 stance 링을 추가한다.

**Architecture:** `merge_hub.py`가 `kb.chat.co_edges`(종목쌍 가중치)를 집계하고, `hub_template.html`의 `buildGraph`가 양쪽이 그래프 노드인 쌍만 `kind='co'` 엣지로 추가, `gDraw`가 점선·stance 링으로 렌더.

**Tech Stack:** Python 3.11(stdlib `itertools`), stdlib unittest, 바닐라 JS(canvas force graph).

**Spec:** `docs/superpowers/specs/2026-06-20-graph-chat-news-design.md`

**테스트 전략**: merge_hub는 TDD(unittest). graph(JS canvas)는 빌드 스모크 + playwright(점선 엣지·stance 링 실제 렌더).

---

## 파일 구조
- `merge_hub.py`: `import itertools` + `CO_EDGE_MIN_W/PER_NODE` 상수 + `_co_edges(chat)` + `kb.chat.co_edges` 설정
- `build/test_merge_hub.py`: `_co_edges` 테스트
- `hub_template.html`: `buildGraph`(co 엣지) + `gDraw`(점선·stance 링)

---

## Task 1: merge_hub co_edges 집계 (TDD)

**Files:** Modify `merge_hub.py` · Test `build/test_merge_hub.py`

- [ ] **Step 1: 실패 테스트 추가** — import에 `_co_edges` 추가 + 클래스

```python
from merge_hub import (  # noqa: E402  (기존 줄에 _co_edges 추가)
    _is_opinion, _name_in, _sort_desc, _build_comention_map, _augment, merge, _is_bot, _theme_blocks, _co_edges,
)

class TestCoEdges(unittest.TestCase):
    def _chat(self):
        D = lambda dt, sh, ty, snip: {"date": dt, "sharer": sh, "type": ty, "snippet": snip}
        return {
            "stocks": {
                # 엔비디아-AMD를 의견 2회(탱이·문지영) 동시언급 → w=2(임계값 통과)
                # 봇/research도 엔비-AMD 동시언급하나 제외돼야(가중치 미반영)
                "엔비디아": {"mentions": [
                    D("2026-04-01", "탱이", "view", "엔비AMD"), D("2026-04-02", "문지영", "view", "엔비AMD2"),
                    D("2026-04-03", "김병철(봇)", "view", "봇 엔비AMD"),   # 봇 → 제외
                    D("2026-04-04", "x", "research", "시황 엔비AMD")]},   # research → 제외
                "AMD": {"mentions": [
                    D("2026-04-01", "탱이", "view", "엔비AMD"), D("2026-04-02", "문지영", "view", "엔비AMD2"),
                    D("2026-04-03", "김병철(봇)", "view", "봇 엔비AMD"),
                    D("2026-04-04", "x", "research", "시황 엔비AMD")]},
            },
            "news": [
                {"stocks": ["엔비디아", "AMD"], "title": "n1"},   # 엔비-AMD +1 → 의견2 + 뉴스1 = 3
                {"stocks": ["삼성전자"], "title": "n2"},          # 1종목 → 쌍 없음
            ],
        }

    def test_sum_normalize_threshold(self):
        edges = {(e["a"], e["b"]): e["w"] for e in _co_edges(self._chat())}
        self.assertEqual(edges.get(("AMD", "엔비디아")), 3)   # 의견 2 + 뉴스 1, 정규화(a<b), w≥2 통과

    def test_bot_and_research_excluded(self):
        # 봇(04-03)·research(04-04)도 엔비-AMD 동시언급하나 제외 → 5가 아닌 3
        edges = {(e["a"], e["b"]): e["w"] for e in _co_edges(self._chat())}
        self.assertEqual(edges.get(("AMD", "엔비디아")), 3)   # 봇·research 미반영

    def test_top6_union(self):
        # 허브 H가 7개 종목과 각 w=2 동시언급. H 기준 top6 초과분(7번째)도
        # 상대 종목 기준 top6라 '합집합'으로 유지 → H 관련 7쌍 모두 남음(교집합이면 6).
        DD = lambda dt, sh, sn: {"date": dt, "sharer": sh, "type": "view", "snippet": sn}
        others = list("ABCDEFG")  # 7개
        stocks = {"H": {"mentions": []}}
        for o in others: stocks[o] = {"mentions": []}
        for k in range(2):  # 각 쌍 2회 → w=2
            for o in others:
                sn = f"H{o}{k}"
                stocks["H"]["mentions"].append(DD(f"2026-05-0{k+1}", f"u{k}{o}", sn))
                stocks[o]["mentions"].append(DD(f"2026-05-0{k+1}", f"u{k}{o}", sn))
        edges = _co_edges({"stocks": stocks, "news": []})
        hPairs = [e for e in edges if "H" in (e["a"], e["b"])]
        self.assertEqual(len(hPairs), 7)   # 합집합: 7쌍 모두 유지(교집합이면 6)
```
> `_co_edges`는 임계값(`w≥2`)·종목당 top6(합집합)를 **적용한 결과**를 반환한다. 위 테스트는 그 최종 반환값을 검증한다.

- [ ] **Step 2: 실패 확인** — Run: `python build/test_merge_hub.py` → FAIL (ImportError `_co_edges`)

- [ ] **Step 3: 구현** — `merge_hub.py` 상단 import에 `itertools` 추가, 상수+함수 추가

```python
import json, sys, itertools          # ← itertools 추가
# ...
CO_EDGE_MIN_W = 2
CO_EDGE_PER_NODE = 6

def _co_edges(chat):
    """종목쌍 동시언급(채팅 의견 봇제외·view/position + 뉴스 stocks) 가중치.
       _build_comention_map 재사용 금지(봇·비의견 포함). 독립 그룹핑, snippet[:40] 통일."""
    pair = Counter()
    # 1) 채팅 의견 동시언급
    msg = defaultdict(set)
    for nm, cs in chat.get("stocks", {}).items():
        for m in cs.get("mentions", []):
            if m.get("type") in OPINION_TYPES and not _is_bot(m):
                key = (m.get("date"), m.get("sharer"), (m.get("snippet", "") or "")[:40])
                msg[key].add(nm)
    for names in msg.values():
        for a, b in itertools.combinations(sorted(names), 2):
            pair[(a, b)] += 1
    # 2) 뉴스 동시언급
    for n in chat.get("news", []):
        for a, b in itertools.combinations(sorted(set(n.get("stocks") or [])), 2):
            pair[(a, b)] += 1
    # 임계값
    strong = {k: w for k, w in pair.items() if w >= CO_EDGE_MIN_W}
    # 종목당 상위 PER_NODE — 합집합(한쪽 top6에만 들어도 유지)
    per = defaultdict(list)
    for (a, b), w in strong.items():
        per[a].append(((a, b), w)); per[b].append(((a, b), w))
    keep = set()
    for lst in per.values():
        for pk, _w in sorted(lst, key=lambda x: -x[1])[:CO_EDGE_PER_NODE]:
            keep.add(pk)
    return [{"a": a, "b": b, "w": strong[(a, b)]} for (a, b) in sorted(keep)]
```

- [ ] **Step 4: `merge()` 연결** — `kb["chat"]` dict 설정부에 `co_edges` 키 추가

`kb["chat"]={...,"themes":_theme_blocks(kb, chat.get("themes", {}))}` 줄의 dict에 항목 추가:
```python
        "co_edges": _co_edges(chat),
```
> `_strip_prior_chat`이 `kb.pop("chat")` 통째 제거하므로 멱등 자동.

- [ ] **Step 5: 통과 확인** — Run: `python build/test_merge_hub.py` → PASS (전체)

- [ ] **Step 6: 커밋**
```bash
git add merge_hub.py build/test_merge_hub.py
git commit -m "feat: merge_hub co_edges 집계(채팅의견+뉴스 동시언급, 봇제외·합집합 top6)"
```

---

## Task 2: buildGraph co 엣지 + gDraw 점선·stance 링

**Files:** Modify `hub_template.html` (`buildGraph` ~L1421, `gDraw` 엣지 루프 ~L1489·노드 루프 ~L1498)

- [ ] **Step 1: `buildGraph`에 co 엣지 추가** — 섹터-종목 link 생성 루프 끝(`return {nodes,links,idx}` 직전)에 추가. 기존 섹터-종목 `links.push`에 `kind:'sector'`도 부여.

```javascript
  // 기존: links.push({s:sIdx,t:idx[id]}); → links.push({s:sIdx,t:idx[id],kind:'sector'});
  // ── 채팅·뉴스 종목↔종목 엣지 (양쪽이 그래프 노드인 쌍만) ──
  const coEdges = (D.chat && Array.isArray(D.chat.co_edges)) ? D.chat.co_edges : [];
  coEdges.forEach(e=>{
    const ia=idx['K:'+gClean(e.a)], ib=idx['K:'+gClean(e.b)];
    if(ia==null||ib==null) return;            // chat_only·major필터 제외 종목 자연 스킵
    links.push({s:ia,t:ib,kind:'co',w:e.w}); nodes[ia].deg++; nodes[ib].deg++;
  });
  return {nodes,links,idx};
```

- [ ] **Step 2: `gDraw` 엣지 점선 분기** — links 루프(L1489~) 교체

```javascript
  for(const e of G.links){const a=G.nodes[e.s], b=G.nodes[e.t];
    const hot = gHover && (a===gHover||b===gHover);
    const isCo = e.kind==='co';
    ctx.setLineDash(isCo ? [4/gView.k, 3/gView.k] : []);
    ctx.strokeStyle = hot ? (a.kind==='sector'?a.color:b.color) : (isCo ? '#7c3aed' : lineC);
    ctx.globalAlpha = gHover ? (hot?0.85:0.12) : (isCo ? 0.40 : 0.5);
    ctx.lineWidth = (hot?1.6 : (isCo ? Math.min(0.6+(e.w||1)*0.22, 2.0) : 0.7))/gView.k;
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  }
  ctx.setLineDash([]); ctx.globalAlpha=1;   // 점선·알파 리셋(원본 L1496 globalAlpha=1 포함, 노드 루프 영향 방지)
```
> 교체 범위는 기존 links 루프 + 직후 `ctx.globalAlpha=1;`(L1489~1496)이며, 노드 루프(이후) 진입 전에 `setLineDash([])`로 점선을 반드시 리셋한다.

- [ ] **Step 3: `gDraw` 노드 stance 링** — 노드 루프(L1498~)에서 fill·bg stroke 후, `if(p===gHover)` 처리에 이어 추가

```javascript
    if(p===gHover){ctx.lineWidth=2.4/gView.k; ctx.strokeStyle=p.color; ctx.stroke();}
    // stance 링 (종목 노드, 강세 녹/약세 빨강, 동률·무는 없음)
    if(p.kind==='stock' && p.ref && p.ref.chat){
      const st=p.ref.chat.stance||{};
      const ring = (st.bullish||0)>(st.bearish||0) ? '#16a34a' : ((st.bearish||0)>(st.bullish||0) ? '#dc2626' : null);
      if(ring){ ctx.beginPath(); ctx.arc(p.x,p.y,r+2.5/gView.k,0,6.2832); ctx.lineWidth=2/gView.k; ctx.strokeStyle=ring; ctx.stroke(); }
    }
```

- [ ] **Step 4: 빌드 스모크**

Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2`
Then:
```bash
python -c "import json;d=json.load(open('knowledge_base.json'));e=d['chat']['co_edges'];print('co_edges',len(e));print('SK-삼성:',[x for x in e if set([x['a'],x['b']])=={'SK하이닉스','삼성전자'}])"
grep -c "kind:'co'\|setLineDash\|stance 링" hub.html
```
Expected: co_edges **~83**(임계값 w≥2 후 90쌍 → 종목당 top6 합집합 적용 후 ~83), SK하이닉스-삼성전자 쌍 존재(w=34), 마커 >0

- [ ] **Step 5: playwright 비주얼 검증** (@superpowers:verification-before-completion)

HTTP 서버로 `hub.html?v=N`(캐시 회피) 열고 `showTab('graph')` 후:
- `G.links.filter(l=>l.kind==='co').length` > 0 (종목-종목 엣지 ~40)
- 강세 종목 노드에 stance 링 렌더(canvas라 G.nodes의 ref.chat.stance로 우세 판정 종목 존재 확인)
- 콘솔 에러 없음(favicon 제외)
- 스크린샷으로 점선 종목 엣지 시각 확인

- [ ] **Step 6: 커밋** (빌드 산출물 제외)
```bash
git add hub_template.html
git commit -m "feat: 관계망 종목↔종목 co 엣지(점선)+노드 stance 링"
```

---

## 완료 기준
- `python build/test_merge_hub.py` 전체 통과(co_edges: 정규화·합산·봇/research 제외·합집합 top6)
- `knowledge_base.json`의 `chat.co_edges` ~90쌍, SK하이닉스-삼성전자 포함
- 관계망에 종목-종목 점선 엣지(~40개 렌더)·강세/약세 노드 링
- 소스(`merge_hub.py`·`hub_template.html`·테스트)만 커밋
