# 지식허브 개선 — Track A (데이터·파이프라인) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 허브 데이터에 (1) 채팅까지 포함한 검색 인덱스, (2) 리포트 수급 코호트·테마 집계·주가 시계열을 더한 검증 레이어, (3) 전일 대비 What's new + feed.json, (4) 증분 캐시 기반 AI 요약(데일리·종목 이유·뉴스 플래그), (5) 스키마 검증·크기 예산 CI 게이트를 추가한다. 모두 스펙 §3.3 의 C3~C6 계약대로 산출하며, UI(Track B)가 없어도 빌드는 그대로 성공한다.

**Architecture:** 기존 관례(모듈 = 파이프라인 1단계, 순수 함수 + 네트워크 분리, 실패는 `build.<단계>_error` 로 격리)를 따른다. 새 모듈 `hublib/{search,whatsnew,feed,schema,ai_summary}.py`, 기존 `hublib/verify.py` 확장. `collect()` 배선만 `hublib/render.py` 에서 바꾼다(render 함수 본문은 건드리지 않는다 — 기반 계획이 소유).

**Tech Stack:** Python 3.11 · pytest · FinanceDataReader(KR) · Anthropic Messages API(urllib) · GitHub Actions cache

**Spec:** [docs/superpowers/specs/2026-08-23-hub-improvement-design.md](../specs/2026-08-23-hub-improvement-design.md)

**전제:** 00-foundation 계획이 main 에 머지된 상태. 이 트랙은 `hub/*.js`·`hub_template.html` 을 **건드리지 않는다** (Track B 소유). `.github/workflows/build.yml` 은 캐시 스텝·Summary 스텝만 추가한다.

---

## 파일 구조

| 파일 | 상태 | 책임 |
|---|---|---|
| `hublib/search.py` | 신규 (~90줄) | `with_hay`·`build_chat_search` — 검색 인덱스 보강(C3) |
| `hublib/verify.py` | 수정 (+~120줄) | `extract_report_calls`·`downsample_series`·`aggregate_themes`·`build_verify` 확장(C4) |
| `hublib/momentum.py` | 수정 (2줄) | `_build_ticker_map` 메모이즈 — KRX 목록 1회만 조회 |
| `hublib/whatsnew.py` | 신규 (~90줄) | `summarize`·`diff`·`load_summary`·`save_summary`(C5) |
| `hublib/feed.py` | 신규 (~60줄) | JSON Feed 1.1 `build_feed` |
| `hublib/schema.py` | 신규 (~50줄) | 최소 스키마 `validate` |
| `hublib/ai_summary.py` | 신규 (~220줄) | `AiCache`·컨텍스트 빌더·잡 선택·`run` 오케스트레이션(C6) |
| `ai_digest.py` | 재작성 (~50줄) | 얇은 CLI — kb·캐시 로드 → `run` → 저장 |
| `hublib/render.py` | 수정 | `collect()` 배선 + `render()` 에 feed/news_flags 2줄 |
| `tests/test_search.py` · `test_whatsnew.py` · `test_feed.py` · `test_schema.py` · `test_ai_summary.py` · `test_budget.py` | 신규 | 순수 함수 전량 |
| `tests/test_verify.py` | 수정 (+) | 리포트 코호트·다운샘플·테마 집계 (픽스처는 테스트 안 인라인) |
| `.github/workflows/build.yml` | 수정 | kb_summary·ai_cache 캐시, 예산 테스트, Job Summary |
| `.gitignore` | 수정 | `feed.json`, `build/kb_summary.json`, `build/ai_cache.json` |
| `README.md` | 수정 | 스키마 표 행 추가 |

## 사전 확인

- [ ] **worktree·브랜치** — `git worktree add ../fromus-track-a -b feat/hub-track-a` (기반 계획 말미 참고) 후 그 폴더에서 작업
- [ ] `VERIFY_SKIP=1 python -m pytest tests/ generator/test_parse.py -q` 전량 PASS
- [ ] `knowledge_base.json` 이 루트에 있으면 로컬 검증에 쓴다(없어도 단위 테스트는 된다)

---

## Task 1: 검색 인덱스 보강 — `hay`·채팅 kind·별칭 (F1/P5 데이터)

**Files:**
- Create: `hublib/search.py`
- Create: `tests/test_search.py`
- Modify: `hublib/render.py` (`collect`·`_merge_chat_kb`)

- [ ] **Step 1: 테스트 (RED)** — `tests/test_search.py`:

```python
# -*- coding: utf-8 -*-
"""검색 인덱스 보강 — hay 사전 토큰화 + 채팅 kind (스펙 C3)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _chat():
    return {
        "stocks": {
            "삼성전자": {"name": "삼성전자", "market": "KR", "ticker": "005930", "mentions": [
                {"date": "2026-08-01", "sharer": "가", "stance": "bullish", "type": "view", "snippet": "삼전 간다", "full": "삼전 간다 길게"},
                {"date": "2026-08-02", "sharer": "김병철(봇)", "stance": "bullish", "type": "view", "snippet": "봇"},
                {"date": "2026-08-03", "sharer": "나", "stance": "자료", "type": "research", "snippet": "자료 링크"},
            ]}},
        "news": [{"date": "2026-08-01", "sharer": "탱이", "outlet": "연합뉴스", "title": "반도체 급등", "url": "https://x/1",
                  "stocks": ["삼성전자"], "themes": ["반도체·메모리"]}],
        "targets": [{"stock": "구글", "value": "300", "unit": "달러", "raw": "목표주가 300달러", "date": "2026-08-04", "sharer": "ㄱ 이혜나"}],
    }


def test_with_hay_adds_lowercase_haystack_and_source():
    from hublib.search import with_hay
    items = [{"kind": "종목", "title": "SK하이닉스", "snippet": "HBM 수혜", "date": "", "id": "", "tags": ["반도체·메모리"]}]
    out = with_hay(items)
    assert out[0]["hay"] == "sk하이닉스 hbm 수혜 반도체·메모리 종목"
    assert out[0]["source"] == "report"
    assert "hay" not in items[0], "입력을 변경하면 안 된다"


def test_build_chat_search_news_opinion_target():
    from hublib.search import build_chat_search
    out = build_chat_search(_chat())
    kinds = [i["kind"] for i in out]
    assert kinds.count("채팅뉴스") == 1 and kinds.count("채팅의견") == 1 and kinds.count("목표가") == 1
    news = next(i for i in out if i["kind"] == "채팅뉴스")
    assert news["title"] == "반도체 급등" and news["extra"] == {"url": "https://x/1", "outlet": "연합뉴스", "stocks": ["삼성전자"], "sharer": "탱이"}
    assert "삼성전자" in news["tags"] and "반도체·메모리" in news["tags"]
    op = next(i for i in out if i["kind"] == "채팅의견")
    assert op["title"] == "삼성전자 · 가" and op["snippet"] == "삼전 간다 길게"
    assert op["extra"] == {"stock": "삼성전자", "sharer": "가", "stance": "bullish", "date": "2026-08-01"}
    tg = next(i for i in out if i["kind"] == "목표가")
    assert tg["title"] == "구글 목표가 300달러" and tg["extra"]["stock"] == "구글"
    assert all(i["source"] == "chat" and i["hay"] for i in out)


def test_build_chat_search_skips_bot_and_research_and_bad_urls():
    from hublib.search import build_chat_search
    chat = _chat()
    chat["news"][0]["url"] = "javascript:alert(1)"
    out = build_chat_search(chat)
    assert not [i for i in out if i["kind"] == "채팅뉴스"], "비 http 링크 뉴스는 싣지 않는다"
    ops = [i for i in out if i["kind"] == "채팅의견"]
    assert len(ops) == 1 and ops[0]["extra"]["sharer"] == "가"
```

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_search.py -q` → 3 failed.

- [ ] **Step 3: 구현** — `hublib/search.py`:

```python
# -*- coding: utf-8 -*-
"""검색 인덱스 보강 — 사전 토큰화(hay) + 채팅 항목(뉴스·의견·목표가). 순수 함수.

리포트 항목은 hublib.aggregate.build_search 가 만든다. 이 모듈은 그 결과에 hay/source 를 붙이고,
chat_kb 에서 채팅 항목을 더한다. 계약: 스펙 §3.3 C3
"""
from hublib.verify import BOT_SHARER

OPINION_TYPES = ("view", "position")
SNIPPET_LIMIT = 300


def _hay(it):
    return " ".join(filter(None, [it.get("title", ""), it.get("snippet", ""),
                                  " ".join(it.get("tags") or []), it.get("kind", "")])).lower()


def with_hay(items):
    """리포트 인덱스 항목에 hay·source 를 붙인 새 리스트."""
    return [{**it, "source": it.get("source", "report"), "hay": _hay(it)} for it in (items or [])]


def _is_http(u):
    return (u or "").lower().startswith(("http://", "https://"))


def _news_items(chat):
    out = []
    for n in chat.get("news") or []:
        if not _is_http(n.get("url")):
            continue
        stocks = list(n.get("stocks") or [])
        themes = list(n.get("themes") or [])
        it = {"kind": "채팅뉴스", "title": n.get("title") or "", "snippet": " · ".join(filter(None, [n.get("outlet"), ", ".join(stocks)]))[:SNIPPET_LIMIT],
              "date": n.get("date") or "", "id": "", "tags": stocks + themes + [n.get("sharer") or ""],
              "extra": {"url": n["url"], "outlet": n.get("outlet") or "", "stocks": stocks, "sharer": n.get("sharer") or ""},
              "source": "chat"}
        out.append({**it, "hay": _hay(it)})
    return out


def _opinion_items(chat):
    out = []
    for name, s in (chat.get("stocks") or {}).items():
        for m in s.get("mentions") or []:
            if m.get("type") not in OPINION_TYPES or m.get("sharer") == BOT_SHARER:
                continue
            text = (m.get("full") or m.get("snippet") or "")[:SNIPPET_LIMIT]
            it = {"kind": "채팅의견", "title": f"{name} · {m.get('sharer') or ''}", "snippet": text,
                  "date": m.get("date") or "", "id": "", "tags": [name, m.get("stance") or ""],
                  "extra": {"stock": name, "sharer": m.get("sharer") or "", "stance": m.get("stance") or "",
                            "date": m.get("date") or ""},
                  "source": "chat"}
            out.append({**it, "hay": _hay(it)})
    return out


def _target_items(chat):
    out = []
    for t in chat.get("targets") or []:
        title = f"{t.get('stock') or ''} 목표가 {t.get('value') or ''}{(t.get('unit') or '').strip()}"
        it = {"kind": "목표가", "title": title, "snippet": (t.get("raw") or "")[:SNIPPET_LIMIT],
              "date": t.get("date") or "", "id": "", "tags": [t.get("stock") or "", t.get("sharer") or ""],
              "extra": {"stock": t.get("stock") or "", "value": t.get("value") or "", "unit": (t.get("unit") or "").strip(),
                        "sharer": t.get("sharer") or ""},
              "source": "chat"}
        out.append({**it, "hay": _hay(it)})
    return out


def build_chat_search(chat):
    """chat_kb → 채팅뉴스·채팅의견·목표가 검색 항목. 봇·자료(research)·비 http 링크 제외."""
    if not chat:
        return []
    return _news_items(chat) + _opinion_items(chat) + _target_items(chat)
```

- [ ] **Step 4: 통과 확인** — `python -m pytest tests/test_search.py -q` → PASS.

- [ ] **Step 5: collect 배선** — `hublib/render.py`

`_merge_chat_kb` 의 `data, added = _merge_chat(data, chat)` 다음 줄에:
```python
        from hublib.search import build_chat_search
        data["search"] = (data.get("search") or []) + build_chat_search(chat)
```
`collect()` 의 `search = build_search(reports, agg)` 를:
```python
    from hublib.search import with_hay
    search = with_hay(build_search(reports, agg))
```
`data = {...}` 의 `"build": {...}` 안에 항목 추가:
```python
                  "aliases": {k.lower(): v for k, v in STOCK_ALIASES.items()},
```
(상단 `from hublib.config import _fmt_kst` → `from hublib.config import _fmt_kst, STOCK_ALIASES`.)

- [ ] **Step 6: 통합 확인**

```bash
VERIFY_SKIP=1 python -m pytest tests/ -q
python - <<'EOF'
import json; kb=json.load(open('knowledge_base.json'))
from collections import Counter; print(Counter(i['kind'] for i in kb['search']))
EOF
```
(두 번째는 `python build_hub.py --phase collect --src .` 를 먼저 돌린 뒤 — 약 5분.) 기대(2026-08-22 데이터): 채팅뉴스 ≈2,980 · 채팅의견 ≈720(view+position, 봇 제외) · 목표가 ≈206 추가 → 리포트 2,282 와 합쳐 총 ≈6,200.

- [ ] **Step 7: 커밋**

```bash
git add hublib/search.py hublib/render.py tests/test_search.py
git commit -m "feat(search): 검색 인덱스에 채팅뉴스·채팅의견·목표가 추가 + hay 사전 토큰화 + build.aliases"
```

---

## Task 2: 최소 스키마 검증 + 크기 예산 (Q1)

**Files:**
- Create: `hublib/schema.py`, `tests/test_schema.py`, `tests/test_budget.py`
- Modify: `hublib/render.py` (`collect` 끝), `.github/workflows/build.yml`

- [ ] **Step 1: 테스트 (RED)** — `tests/test_schema.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ok():
    return {"build": {"schema": 2, "generated": "x", "to": "2026-08-22"}, "reports": [], "search": [],
            "stocks": [{"name": "A", "count": 1, "mentions": []}], "sectors": [{"theme": "T", "count": 1, "mentions": []}],
            "stance": [], "principles": [], "glossary": [], "events": [], "sentiment": [], "series": {}}


def test_validate_ok_returns_empty():
    from hublib.schema import validate
    assert validate(_ok()) == []


def test_validate_reports_missing_and_wrong_types():
    from hublib.schema import validate
    d = _ok(); d.pop("stocks"); d["sectors"] = "nope"; d["stocks_x"] = 1
    probs = validate(d)
    assert any("stocks" in p and "누락" in p for p in probs)
    assert any("sectors" in p and "list" in p for p in probs)


def test_validate_item_required_keys():
    from hublib.schema import validate
    d = _ok(); d["stocks"] = [{"count": 1}]
    assert any("stocks[0]" in p and "name" in p for p in validate(d))
```

- [ ] **Step 2: 구현** — `hublib/schema.py`:

```python
# -*- coding: utf-8 -*-
"""knowledge_base.json 최소 스키마(v2) — 셸이 빈 화면으로 조용히 죽는 키 누락을 빌드에서 잡는다.
키 추가는 자유(마이너), 여기 적힌 키의 누락·타입 변경만 문제로 본다."""

TOP = {"build": dict, "reports": list, "search": list, "stocks": list, "sectors": list, "stance": list,
       "principles": list, "glossary": list, "events": list, "sentiment": list, "series": dict}
ITEM_KEYS = {"stocks": ("name", "count", "mentions"), "sectors": ("theme", "count", "mentions"),
             "search": ("kind", "title", "snippet"), "reports": ("id", "type", "file")}
BUILD_KEYS = ("schema", "generated", "to")


def validate(data):
    """문제 목록(문자열). 비어 있으면 통과."""
    probs = []
    for k, t in TOP.items():
        if k not in data:
            probs.append(f"{k}: 누락"); continue
        if not isinstance(data[k], t):
            probs.append(f"{k}: {t.__name__} 여야 함 ({type(data[k]).__name__})")
    for k in BUILD_KEYS:
        if isinstance(data.get("build"), dict) and k not in data["build"]:
            probs.append(f"build.{k}: 누락")
    for k, keys in ITEM_KEYS.items():
        arr = data.get(k)
        if not isinstance(arr, list):
            continue
        for i, it in enumerate(arr[:2000]):
            for kk in keys:
                if not isinstance(it, dict) or kk not in it:
                    probs.append(f"{k}[{i}]: {kk} 누락"); break
    return probs
```

- [ ] **Step 3: 통과 확인** — `python -m pytest tests/test_schema.py -q` → PASS.

- [ ] **Step 4: collect 배선** — `collect()` 의 `with open(json_out, "w", ...)` 직전:

```python
    from hublib.schema import validate
    problems = validate(data)
    if problems:
        print(f"[WARN] 스키마 문제 {len(problems)}건: " + " | ".join(problems[:10]), file=sys.stderr)
        data["build"]["schema_warnings"] = problems[:50]
        if any("누락" in p and "[" not in p for p in problems):     # 최상위 키 누락만 빌드 실패
            sys.exit("knowledge_base 최상위 키 누락 — 빌드 중단")
```

- [ ] **Step 5: 예산 테스트** — `tests/test_budget.py`:

```python
# -*- coding: utf-8 -*-
"""kb 출력 크기 예산 — KB_BUDGET_CHECK=1 일 때만(렌더 직후 cwd 의 kb.*.json). 초과는 경고이지 실패가 아니다.
실패 조건은 '코어가 예산의 2배' 뿐 — 데이터가 자라도 첫 화면 전송을 지키기 위한 하드 게이트."""
import glob
import os
import re

import pytest

BUDGET_MB = {"core": 2.5, "chat": 3.5, "search": 5.0, "glossary": 1.0, "stockchat": 3.0}


@pytest.mark.skipif(os.environ.get("KB_BUDGET_CHECK") != "1", reason="KB_BUDGET_CHECK=1 일 때만")
def test_kb_chunks_within_budget():
    files = glob.glob("kb.*.json")
    assert files, "렌더 산출물 없음 — build_hub.py --phase render 먼저"
    lines, hard_fail = [], []
    for p in files:
        m = re.match(r"kb\.([a-z]+)\.[0-9a-f]+\.json$", os.path.basename(p))
        if not m:
            continue
        name, mb = m.group(1), os.path.getsize(p) / 1e6
        budget = BUDGET_MB.get(name)
        flag = "" if budget is None or mb <= budget else " ⚠ 예산 초과"
        lines.append(f"| {name} | {mb:.2f} MB | {budget or '-'} MB |{flag}")
        if name == "core" and mb > BUDGET_MB["core"] * 2:
            hard_fail.append(f"core {mb:.2f}MB > {BUDGET_MB['core']*2}MB")
    os.makedirs("build", exist_ok=True)
    with open("build/report.md", "a", encoding="utf-8") as f:
        f.write("\n### 크기 예산\n\n| 청크 | 실제 | 예산 |\n|---|---|---|\n" + "\n".join(lines) + "\n")
    assert not hard_fail, hard_fail
```

- [ ] **Step 6: 워크플로** — `Run tests` 스텝(여기서 `pip install pytest` 가 된다) **뒤**에(Render 직후에 두면 pytest 가 없어 실패한다):

```yaml
      - name: kb 크기 예산 (경고만, 코어 2배 초과 시 실패)
        run: KB_BUDGET_CHECK=1 python -m pytest tests/test_budget.py -q
```

그리고 **별도로**, `E2E 스모크` 스텝(기반 계획이 `Assemble site` 뒤에 넣음) **뒤**·`configure-pages` **앞**에(타이밍 파일이 E2E 에서 나오므로):
```yaml
      - name: Job Summary (kb 크기·예산·E2E 타이밍)
        if: always()
        run: |
          cat build/report.md >> "$GITHUB_STEP_SUMMARY" 2>/dev/null || true
          [ -f build/e2e_timing.json ] && { echo; echo '### E2E 타이밍'; echo '```'; cat build/e2e_timing.json; echo; echo '```'; } >> "$GITHUB_STEP_SUMMARY" || true
```
최종 순서: Render → Run tests → **kb 크기 예산** → Assemble site → E2E 스모크 → **Job Summary** → configure-pages.

- [ ] **Step 7: 로컬 확인 + 커밋**

```bash
python -m pytest tests/test_schema.py -q
python build_hub.py --phase render --json knowledge_base.json --out hub.html && KB_BUDGET_CHECK=1 python -m pytest tests/test_budget.py -q && cat build/report.md
git add hublib/schema.py hublib/render.py tests/test_schema.py tests/test_budget.py .github/workflows/build.yml
git commit -m "ci: knowledge_base 최소 스키마 검증 + kb 청크 크기 예산 테스트 + Job Summary"
```

---

## Task 3: What's new diff + feed.json (F4 데이터)

**Files:**
- Create: `hublib/whatsnew.py`, `hublib/feed.py`, `tests/test_whatsnew.py`, `tests/test_feed.py`
- Modify: `hublib/render.py` (collect·render 배선), `.github/workflows/build.yml`, `.gitignore`

- [ ] **Step 1: 테스트 (RED)** — `tests/test_whatsnew.py`:

```python
# -*- coding: utf-8 -*-
"""전일 요약 대비 diff (스펙 C5)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _data(to="2026-08-22"):
    return {
        "build": {"to": to, "generated": f"{to} 07:30"},
        "reports": [{"id": "2026-08-21", "type": "daily"}, {"id": to, "type": "daily"}],
        "stocks": [{"name": "삼성전자", "count": 10, "mentions": [{"date": "2026-08-22"}]},
                   {"name": "신규주", "count": 2, "mentions": [{"date": "2026-08-22"}]},
                   {"name": "조용한주", "count": 3, "mentions": [{"date": "2026-07-01"}]}],
        "chat": {"targets": [{"stock": "구글", "value": "300", "unit": "달러", "date": "2026-08-22"}]},
        "verify": {"enabled": True, "calls": [{"stock": "삼성전자", "date": "2026-08-22", "stance": "bullish"}]},
    }


def test_summarize_shape():
    from hublib.whatsnew import summarize
    s = summarize(_data())
    assert s["to"] == "2026-08-22"
    assert s["stocks"]["삼성전자"] == {"count": 10, "last": "2026-08-22"}
    assert s["calls"] == ["삼성전자|2026-08-22|bullish"]
    assert s["targets"] == ["구글|300|달러|2026-08-22"]
    assert s["reports"] == ["2026-08-21", "2026-08-22"]


def test_diff_detects_new_surging_calls_targets_reports():
    from hublib.whatsnew import summarize, diff
    prev = summarize({**_data("2026-08-21"), "stocks": [{"name": "삼성전자", "count": 6, "mentions": []},
                                                        {"name": "조용한주", "count": 3, "mentions": []}],
                      "chat": {"targets": []}, "verify": {"enabled": True, "calls": []},
                      "reports": [{"id": "2026-08-21", "type": "daily"}]})
    cur = _data()
    out = diff(prev, cur)
    assert out["since"] == "2026-08-21"
    assert out["new_stocks"] == [{"name": "신규주", "count": 2}]
    assert out["surging"] == [{"name": "삼성전자", "recent": 10, "prev": 6}]   # +3 이상
    assert out["new_calls"] == [{"stock": "삼성전자", "stance": "bullish", "date": "2026-08-22"}]
    assert out["new_targets"] == [{"stock": "구글", "value": "300", "unit": "달러", "date": "2026-08-22"}]
    assert out["new_reports"] == ["2026-08-22"]


def test_diff_without_prev_is_none():
    from hublib.whatsnew import diff
    assert diff(None, _data()) is None


def test_diff_same_day_is_none():
    from hublib.whatsnew import summarize, diff
    assert diff(summarize(_data()), _data()) is None, "같은 빌드 기준일이면 diff 없음 (하루 2회 빌드 방지)"


def test_load_save_roundtrip(tmp_path):
    from hublib.whatsnew import summarize, save_summary, load_summary
    p = tmp_path / "kb_summary.json"
    s = summarize(_data()); save_summary(str(p), s)
    assert load_summary(str(p)) == s
    assert load_summary(str(tmp_path / "none.json")) is None
```

- [ ] **Step 2: 구현** — `hublib/whatsnew.py`:

```python
# -*- coding: utf-8 -*-
"""전일 빌드 대비 '오늘 달라진 것' — 요약(summarize)을 남겨 두고 다음 빌드에서 diff 한다. 순수 함수 + 파일 IO 2개.

계약: 스펙 §3.3 C5. 요약 파일은 build/kb_summary.json (actions/cache 로 보존).
"""
import json
import os

SURGE_MIN = 3        # 전일 대비 언급 +3 이상이면 '급증'
SUMMARY_PATH = "build/kb_summary.json"


def summarize(data):
    b = data.get("build") or {}
    stocks = {}
    for s in data.get("stocks") or []:
        ms = s.get("mentions") or []
        stocks[s["name"]] = {"count": s.get("count") or 0, "last": max((m.get("date") or "" for m in ms), default="")}
    v = data.get("verify") or {}
    calls = sorted(f"{c['stock']}|{c['date']}|{c['stance']}" for c in (v.get("calls") or [])) if v.get("enabled") else []
    targets = sorted(f"{t.get('stock','')}|{t.get('value','')}|{(t.get('unit') or '').strip()}|{t.get('date','')}"
                     for t in ((data.get("chat") or {}).get("targets") or []))
    return {"to": b.get("to") or "", "generated": b.get("generated") or "", "stocks": stocks,
            "calls": calls, "targets": targets, "reports": sorted(r["id"] for r in (data.get("reports") or []) if r.get("id"))}


def diff(prev, data):
    """prev 요약 대비 현재 데이터의 변화. 첫 빌드(prev 없음)·같은 기준일이면 None."""
    if not prev:
        return None
    cur = summarize(data)
    if cur["to"] <= (prev.get("to") or ""):
        return None
    ps = prev.get("stocks") or {}
    new_stocks = [{"name": n, "count": v["count"]} for n, v in cur["stocks"].items() if n not in ps]
    surging = [{"name": n, "recent": v["count"], "prev": ps[n]["count"]}
               for n, v in cur["stocks"].items() if n in ps and v["count"] - ps[n]["count"] >= SURGE_MIN]
    pc, pt, pr = set(prev.get("calls") or []), set(prev.get("targets") or []), set(prev.get("reports") or [])
    new_calls = [dict(zip(("stock", "date", "stance"), k.split("|"))) for k in cur["calls"] if k not in pc]
    new_targets = [dict(zip(("stock", "value", "unit", "date"), k.split("|"))) for k in cur["targets"] if k not in pt]
    return {
        "since": prev.get("to") or "", "generated": cur["generated"],
        "new_stocks": sorted(new_stocks, key=lambda x: (-x["count"], x["name"])),
        "surging": sorted(surging, key=lambda x: (-(x["recent"] - x["prev"]), x["name"])),
        "new_calls": [{"stock": c["stock"], "stance": c["stance"], "date": c["date"]} for c in new_calls],
        "new_targets": new_targets,
        "new_reports": [r for r in cur["reports"] if r not in pr],
    }


def load_summary(path=SUMMARY_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_summary(path, summary):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)
```

- [ ] **Step 3: 통과 확인** — `python -m pytest tests/test_whatsnew.py -q` → PASS.

- [ ] **Step 4: feed 테스트 (RED)** — `tests/test_feed.py`:

```python
# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_build_feed_json_feed_1_1():
    from hublib.feed import build_feed
    data = {"build": {"to": "2026-08-22", "generated": "2026-08-22 07:30"},
            "reports": [{"id": "2026-08-22", "type": "daily", "date": "2026-08-22", "file": "reports/daily/a.html", "headline": "H", "subhead": "S"}],
            "stance": [{"id": "2026-08-22", "date": "2026-08-22", "headline": "H", "points": ["p1", "p2"]}],
            "whats_new": {"since": "2026-08-21", "new_stocks": [{"name": "신규주", "count": 2}], "surging": [], "new_calls": [], "new_targets": [], "new_reports": ["2026-08-22"]}}
    f = build_feed(data, base_url="https://example.org/hub/")
    assert f["version"] == "https://jsonfeed.org/version/1.1"
    assert f["feed_url"] == "https://example.org/hub/feed.json"
    ids = [i["id"] for i in f["items"]]
    assert "report:2026-08-22" in ids and "whatsnew:2026-08-22" in ids
    rep = next(i for i in f["items"] if i["id"] == "report:2026-08-22")
    assert rep["url"] == "https://example.org/hub/reports/daily/a.html" and "p1" in rep["content_text"]
    wn = next(i for i in f["items"] if i["id"] == "whatsnew:2026-08-22")
    assert "신규주" in wn["content_text"] and wn["url"].endswith("hub.html#home")


def test_build_feed_relative_without_base():
    from hublib.feed import build_feed
    f = build_feed({"build": {"to": "x"}, "reports": [], "stance": []}, base_url="")
    assert f["feed_url"] == "feed.json" and f["items"] == []
```

- [ ] **Step 5: 구현** — `hublib/feed.py`:

```python
# -*- coding: utf-8 -*-
"""JSON Feed 1.1 — 최근 리포트 + 오늘 달라진 것. RSS 리더·슬랙·봇 연동용."""
FEED_ITEMS = 30


def _join(base, path):
    return (base.rstrip("/") + "/" + path) if base else path


def _report_item(r, stance_by_id, base):
    st = stance_by_id.get(r.get("id"), {})
    points = "\n".join(f"- {p}" for p in (st.get("points") or []))
    return {"id": f"report:{r['id']}", "url": _join(base, r.get("file") or ""),
            "title": r.get("headline") or r["id"],
            # 위클리는 date 가 None·id 가 '2026-W18' 이라 RFC 3339 가 안 된다 → sort_date(실제 날짜) 우선
            "date_published": (r.get("sort_date") or r.get("date") or r["id"])[:10] + "T07:30:00+09:00",
            "content_text": "\n".join(filter(None, [r.get("subhead"), points])) or (r.get("headline") or "")}


def _whatsnew_item(w, to, base):
    parts = []
    if w.get("new_stocks"):
        parts.append("신규 종목: " + ", ".join(f"{x['name']}({x['count']})" for x in w["new_stocks"][:10]))
    if w.get("surging"):
        parts.append("언급 급증: " + ", ".join(f"{x['name']} {x['prev']}→{x['recent']}" for x in w["surging"][:10]))
    if w.get("new_calls"):
        parts.append(f"새 콜 {len(w['new_calls'])}건")
    if w.get("new_targets"):
        parts.append("새 목표가: " + ", ".join(f"{x['stock']} {x['value']}{x['unit']}" for x in w["new_targets"][:10]))
    return {"id": f"whatsnew:{to}", "url": _join(base, "hub.html#home"), "title": f"오늘 달라진 것 — {to}",
            "date_published": to + "T07:30:00+09:00", "content_text": "\n".join(parts) or "변화 없음"}


def build_feed(data, base_url=""):
    b = data.get("build") or {}
    stance_by_id = {s.get("id"): s for s in (data.get("stance") or [])}
    reports = sorted((r for r in (data.get("reports") or []) if r.get("id")), key=lambda r: r.get("sort_date") or r["id"], reverse=True)
    items = [_report_item(r, stance_by_id, base_url) for r in reports[:FEED_ITEMS]]
    if data.get("whats_new"):
        items.insert(0, _whatsnew_item(data["whats_new"], b.get("to") or "", base_url))
    return {"version": "https://jsonfeed.org/version/1.1", "title": "프롬어스 Knowledge Hub",
            "home_page_url": _join(base_url, "hub.html"), "feed_url": _join(base_url, "feed.json"),
            "language": "ko", "items": items}
```

- [ ] **Step 6: 통과 확인** — `python -m pytest tests/test_feed.py -q` → PASS.

- [ ] **Step 7: 배선** — `hublib/render.py`

`collect()` 의 `data["verify"] = _build_verify_safe(data)` 다음에:
```python
    data["whats_new"] = _build_whats_new_safe(data)
```
모듈에 함수 추가(`_build_verify_safe` 아래):
```python
def _build_whats_new_safe(data):
    """전일 요약 대비 diff. 첫 빌드·실패는 None — 빌드는 계속된다."""
    import sys
    try:
        from hublib.whatsnew import diff, load_summary, save_summary, summarize, SUMMARY_PATH
        prev = load_summary(SUMMARY_PATH)
        cur = summarize(data)
        out = diff(prev, data)
        if out is None and prev and prev.get("to") == cur["to"]:
            out = prev.get("last_diff")            # 같은 날 재빌드(푸시 트리거) — 그날 아침의 diff 를 그대로 유지
        if prev is None or prev.get("to") != cur["to"]:
            save_summary(SUMMARY_PATH, {**cur, "last_diff": out})   # 기준일이 바뀔 때만 요약(+그날의 diff) 갱신
        print("what's new --", "없음(첫 빌드/동일 기준일)" if out is None else
              f"신규 {len(out['new_stocks'])} · 급증 {len(out['surging'])} · 콜 {len(out['new_calls'])} · 목표가 {len(out['new_targets'])}")
        return out
    except Exception as e:
        print(f"[WARN] what's new 생략 -- {e}", file=sys.stderr)
        data.setdefault("build", {})["whats_new_error"] = str(e)
        return None
```
`render()` 에서 `_write_size_report(sizes)` 앞에 2줄:
```python
    from hublib.feed import build_feed
    with open(os.path.join(out_dir, "feed.json"), "w", encoding="utf-8") as f:
        json.dump(build_feed(data, os.environ.get("SITE_BASE_URL", "")), f, ensure_ascii=False, indent=1)
```

- [ ] **Step 8: 워크플로·gitignore**

`build.yml` 의 price cache 스텝 뒤에:
```yaml
      - name: Restore kb summary (what's new 전일 기준)
        uses: actions/cache@v4
        with:
          path: build/kb_summary.json
          key: kb-summary-${{ github.run_id }}
          restore-keys: kb-summary-
```
`Render` 스텝에 `env: SITE_BASE_URL: ${{ vars.SITE_BASE_URL }}` 추가(리포 Variables 에 Pages URL 을 넣는다 — 없으면 상대 URL). `Assemble site` 에 `cp feed.json _site/ 2>/dev/null || true`.
`.gitignore` 에 `feed.json`, `build/kb_summary.json`.

- [ ] **Step 9: 확인 + 커밋**

```bash
VERIFY_SKIP=1 python -m pytest tests/ -q
git add hublib/whatsnew.py hublib/feed.py hublib/render.py tests/test_whatsnew.py tests/test_feed.py .github/workflows/build.yml .gitignore
git commit -m "feat(data): 전일 대비 what's new diff(build/kb_summary.json) + JSON Feed 1.1 feed.json"
```

---

## Task 4: 검증 확장 — 리포트 수급 코호트·테마 집계·주가 시계열 (F3 데이터)

**Files:**
- Modify: `hublib/verify.py`, `hublib/momentum.py`, `hublib/render.py`
- Modify: `tests/test_verify.py`

리포트의 수급 포착 언급(`mentions[].source=="수급"`, 현재 227건·90종목)을 "강세 콜"로 보고 채팅 코호트와 같은 판정기로 돌린다. 둘은 **절대 합산하지 않는다**. 티커는 `momentum._build_ticker_map()`(KRX 목록)으로 푼다 — US 종목은 티커가 없어 제외(`excluded.no_ticker`).

- [ ] **Step 1: 테스트 (RED)** — `tests/test_verify.py` 끝에 추가:

```python
# ── 리포트 수급 코호트 ───────────────────────────────────────────
def _report_stocks():
    return [
        {"name": "삼성전자", "count": 5, "themes": ["반도체·메모리"], "mentions": [
            {"date": "2026-05-04", "id": "2026-05-04", "source": "수급", "label": "기관 순매수 · 코스피", "annotation": "1,000억"},
            {"date": "2026-05-04", "id": "2026-05-04", "source": "테마", "label": "반도체"},
            {"date": "2026-05-11", "id": "2026-05-11", "source": "수급", "label": "외국인 순매수 · 코스피", "annotation": ""}]},
        {"name": "엔비디아", "count": 9, "themes": ["소프트웨어·AI"], "mentions": [
            {"date": "2026-05-04", "id": "2026-05-04", "source": "수급", "label": "기관 순매수"}]},
        {"name": "조용한주", "count": 1, "themes": [], "mentions": [{"date": "2026-05-04", "source": "테마"}]},
    ]


TICKER_MAP = {"삼성전자": {"code": "005930", "market": "KOSPI"}, "조용한주": {"code": "000001", "market": "KOSDAQ"}}


def test_extract_report_calls_supply_only_with_ticker():
    from hublib.verify import extract_report_calls
    calls, stats = extract_report_calls(_report_stocks(), TICKER_MAP)
    assert [c["date"] for c in calls] == ["2026-05-04", "2026-05-11"]
    c = calls[0]
    assert c["stock"] == "삼성전자" and c["ticker"] == "005930" and c["market"] == "KR"
    assert c["stance"] == "bullish" and c["type"] == "supply" and c["bench_label"] == "KOSPI" and c["conflict"] is False
    assert c["sources"] == [{"sharer": "리포트", "snippet": "기관 순매수 · 코스피 · 1,000억", "id": "2026-05-04"}]
    assert stats == {"population": 3, "no_ticker": 1, "stocks": 1, "merged_from": 2, "duplicate": 0}


def test_extract_report_calls_merges_same_day_and_caps_stocks():
    from hublib.verify import extract_report_calls
    stocks = _report_stocks()
    stocks[0]["mentions"].append({"date": "2026-05-04", "source": "수급", "label": "투신 순매수", "id": "2026-05-04"})
    calls, stats = extract_report_calls(stocks, TICKER_MAP)
    assert len([c for c in calls if c["date"] == "2026-05-04" and c["stock"] == "삼성전자"]) == 1
    assert stats["duplicate"] == 1
    calls2, _ = extract_report_calls(stocks, TICKER_MAP, max_stocks=0)
    assert calls2 == []


def test_downsample_series_every_5th_plus_last():
    from hublib.verify import downsample_series
    pts = [(f"2026-05-{i:02d}", float(i)) for i in range(1, 24)]
    out = downsample_series(pts, step=5, max_points=80)
    assert out[0] == ["2026-05-01", 1.0] and out[-1] == ["2026-05-23", 23.0]
    assert [d for d, _ in out] == ["2026-05-01", "2026-05-06", "2026-05-11", "2026-05-16", "2026-05-21", "2026-05-23"]
    assert len(downsample_series(pts, step=1, max_points=4)) <= 4
    assert downsample_series([], step=5) == []


def test_aggregate_themes_rolls_calls_by_stock_theme():
    from hublib.verify import aggregate_themes
    judged = [
        {"stock": "A", "conflict": False, "h20": {"hit": True, "excess": 4.0}},
        {"stock": "A", "conflict": False, "h20": {"hit": False, "excess": -2.0}},
        {"stock": "B", "conflict": False, "h20": {"hit": True, "excess": 1.0}},
        {"stock": "C", "conflict": True,  "h20": {"hit": True, "excess": 9.0}},
    ]
    themes = {"A": ["반도체·메모리", "삼성그룹"], "B": ["반도체·메모리"], "C": ["반도체·메모리"]}
    out = aggregate_themes(judged, themes, horizons=(20,))
    semi = next(t for t in out if t["theme"] == "반도체·메모리")
    assert semi["calls"] == 3 and semi["h20"]["judged"] == 3 and semi["h20"]["hit"] == 2
    assert semi["h20"]["avg_excess"] == 1.0
    assert next(t for t in out if t["theme"] == "삼성그룹")["calls"] == 2
    assert out[0]["theme"] == "반도체·메모리", "콜 수 내림차순"


def test_build_verify_report_cohort_with_fake_loaders(tmp_path):
    from hublib.verify import build_verify
    ser = _series(40)

    def loader(ticker, start):
        return ser
    out = build_verify(chat_kb=_mini(), report_stocks=_report_stocks(), ticker_map=TICKER_MAP,
                       cache_path=str(tmp_path / "c.json"), loaders={"KR": loader, "US": loader},
                       market_of=lambda code: "KOSPI")
    assert out["enabled"] and out["meta"]["cohort"] == "core"
    rep = out["report"]
    assert rep["enabled"] and rep["meta"]["cohort"] == "report" and rep["meta"]["calls"] == 2
    assert rep["meta"]["excluded"]["no_ticker"] == 1
    assert rep["stocks"][0]["name"] == "삼성전자" and rep["stocks"][0]["series"][0][0] <= "2026-05-04"
    assert out["stocks"][0]["series"], "채팅 코호트 종목에도 시계열"
    assert out["themes"] and out["themes"][0]["cohort"] == "report"
    assert all(c["stock"] != "삼성전자" or c["type"] == "supply" for c in rep["calls"])
```

(`_series`·`_mini` 는 파일 상단에 이미 있는 헬퍼.)

- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_verify.py -q -k "report or downsample or themes"` → 5 failed.

- [ ] **Step 3: `hublib/momentum.py` — 티커 맵 메모이즈**

`def _build_ticker_map():` 위에 `import functools` (파일 상단 import 에 추가) 와 데코레이터:
```python
@functools.lru_cache(maxsize=1)      # 한 빌드에서 KRX 목록은 한 번만 — momentum 과 verify 가 공유한다
def _build_ticker_map():
```

- [ ] **Step 4: `hublib/verify.py` 구현** — `HORIZONS` 정의 아래에 추가:

```python
# ── 리포트 수급 코호트 ───────────────────────────────────────────
REPORT_COHORT_MAX_STOCKS = 120      # 언급 많은 순으로 가격 수집 상한 — CI 시간 보호


def _bench_for_market(market):
    return "KOSDAQ" if "KOSDAQ" in str(market or "").upper() else "KOSPI"


def extract_report_calls(stocks, ticker_map, max_stocks=REPORT_COHORT_MAX_STOCKS):
    """리포트 종목 집계(knowledge_base.stocks) → 수급 포착 언급을 강세 콜로. 네트워크 없음.

    티커는 ticker_map[name] = {"code","market"} (momentum._build_ticker_map). 없으면 no_ticker 로 제외.
    """
    ranked = sorted((s for s in (stocks or []) if any(m.get("source") == "수급" for m in s.get("mentions") or [])),
                    key=lambda s: (-(s.get("count") or 0), s.get("name") or ""))[:max_stocks]
    raw, no_ticker = [], 0
    for s in ranked:
        meta = (ticker_map or {}).get(s.get("name"))
        sup = [m for m in s.get("mentions") or [] if m.get("source") == "수급"]
        if not meta or not meta.get("code"):
            no_ticker += len(sup)
            continue
        for m in sup:
            raw.append({"stock": s["name"], "market": "KR", "ticker": meta["code"], "date": m.get("date") or "",
                        "stance": "bullish", "type": "supply", "bench_label": _bench_for_market(meta.get("market")),
                        "source": {"sharer": "리포트", "snippet": " · ".join(filter(None, [m.get("label"), m.get("annotation")]))[:SNIPPET_MAX],
                                   "id": m.get("id") or ""}})
    merged = {}
    for c in sorted(raw, key=lambda x: (x["date"], x["stock"])):
        key = (c["stock"], c["date"])
        if key in merged:
            merged[key]["sources"].append(c["source"]); continue
        merged[key] = {k: v for k, v in c.items() if k != "source"} | {"conflict": False, "sources": [c["source"]]}
    calls = sorted(merged.values(), key=lambda c: (c["date"], c["stock"]))
    stats = {"population": len(raw) + no_ticker, "no_ticker": no_ticker,
             "stocks": len({c["stock"] for c in calls}), "merged_from": len(raw), "duplicate": len(raw) - len(calls)}
    return calls, stats


def downsample_series(points, step=5, max_points=80):
    """[(date, close)] → [[date, close]] 거래일 step 간격 + 마지막 점. 종목 상세 주가 오버레이용(코어 크기 보호)."""
    if not points:
        return []
    picked = list(points[::max(1, step)])
    if picked[-1] != points[-1]:
        picked.append(points[-1])
    while len(picked) > max_points:
        picked = picked[::2] if picked[-1] == points[-1] else picked[::2] + [points[-1]]
    return [[d, v] for d, v in picked]


def aggregate_themes(judged_calls, stock_themes, horizons=HORIZONS):
    """콜 → 테마별 통계. stock_themes: {종목명: [테마,...]}. 충돌 콜 제외. 콜 수 내림차순."""
    by_theme = {}
    for c in judged_calls:
        if c.get("conflict"):
            continue
        for th in stock_themes.get(c["stock"]) or []:
            by_theme.setdefault(th, []).append(c)
    out = []
    for th, cs in by_theme.items():
        row = {"theme": th, "cohort": "report", "calls": len(cs)}
        for h in horizons:
            key = f"h{h}"
            row[key] = _roll([c[key] for c in cs if isinstance(c.get(key), dict)])
        out.append(row)
    return sorted(out, key=lambda r: (-r["calls"], r["theme"]))
```

`build_verify` 를 다음으로 교체(채팅 코호트 로직은 그대로, 리포트 코호트·시계열·테마 추가):

```python
def _judge_all(calls, prices, benches, horizons):
    out = []
    for c in calls:
        series = prices.get(f"{c['market']}:{c['ticker']}") or []
        bench = benches.get(c["bench_label"]) or []
        out.append({**c, **judge_call(c, series, bench, horizons=horizons)})
    return out


def _with_series(stock_rows, prices):
    return [{**row, "series": downsample_series(prices.get(f"{row['market']}:{row['ticker']}") or [])} for row in stock_rows]


def build_verify(chat_kb=None, cache_path="build/price_cache.json", loaders=None, market_of=None,
                 horizons=HORIZONS, report_stocks=None, ticker_map=None):
    """검증 레이어 전체를 조립한다. chat 데이터가 없으면 None.

    report_stocks 가 주어지면 리포트 수급 코호트(verify.report)·테마 집계(verify.themes)도 만든다.
    두 코호트는 가격 캐시·벤치마크만 공유하고 통계는 합치지 않는다.
    예상 못 한 예외는 {'enabled': False, 'reason': ...} — 검증 때문에 허브 빌드가 실패해선 안 된다.
    """
    if not chat_kb:
        return None
    try:
        from hublib.config import _fmt_kst
        calls, stats = extract_calls(chat_kb)
        if not calls:
            return {"enabled": False, "reason": "no calls"}

        market_of = market_of or _krx_market_lookup()
        for c in calls:
            c["bench_label"] = _bench_label(c, market_of)

        rep_calls, rep_stats = [], {}
        if report_stocks:
            if ticker_map is None:
                from hublib.momentum import _build_ticker_map
                ticker_map = _build_ticker_map()
            rep_calls, rep_stats = extract_report_calls(report_stocks, ticker_map)

        cache = PriceCache(cache_path)
        all_calls = calls + rep_calls
        first = min(c["date"] for c in all_calls)
        prices = fetch_prices(all_calls, cache, loaders=loaders)
        benches = fetch_benchmarks([c["bench_label"] for c in all_calls], first, cache, loaders=loaders)
        cache.save()

        judged = _judge_all(calls, prices, benches, horizons)
        agg = aggregate_calls(judged, horizons=horizons)
        scored = [c for c in judged if not c["conflict"]]
        out = {
            "enabled": True,
            "meta": {
                "cohort": "core", "calls": len(scored), "merged_from": stats["core"],
                "stocks": len(agg["stocks"]), "population": stats["population"],
                "horizons": list(horizons), "primary": PRIMARY_HORIZON,
                "entry": "next_trading_close", "unit": "trading_days",
                "excluded": {k: stats[k] for k in ("bot", "asset", "bot_and_asset", "duplicate", "conflict")},
                "generated": _fmt_kst(),
            },
            "summary": agg["summary"],
            "stocks": _with_series(agg["stocks"], prices),
            "calls": judged,
        }
        if rep_calls:
            rj = _judge_all(rep_calls, prices, benches, horizons)
            ragg = aggregate_calls(rj, horizons=horizons)
            themes = {s["name"]: list(s.get("themes") or []) for s in report_stocks}
            out["report"] = {
                "enabled": True,
                "meta": {"cohort": "report", "calls": len(rj), "stocks": len(ragg["stocks"]),
                         "population": rep_stats["population"], "horizons": list(horizons), "primary": PRIMARY_HORIZON,
                         "entry": "next_trading_close", "unit": "trading_days",
                         "excluded": {"no_ticker": rep_stats["no_ticker"], "duplicate": rep_stats["duplicate"]},
                         "generated": _fmt_kst()},
                "summary": ragg["summary"],
                "stocks": _with_series(ragg["stocks"], prices),
                "calls": rj,
            }
            out["themes"] = aggregate_themes(rj, themes, horizons=horizons)
        elif report_stocks:
            out["report"] = {"enabled": False, "reason": "no supply mentions with ticker",
                             "meta": {"cohort": "report", "excluded": rep_stats}}
        return out
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"enabled": False, "reason": repr(e)[:200]}
```

- [ ] **Step 5: 통과 확인**

```bash
python -m pytest tests/test_verify.py -q
```
기대: 기존 테스트 포함 전량 PASS. `test_build_verify_end_to_end_with_fake_loaders` 가 `stocks[].series` 추가로 깨지면 그 테스트의 dict 동등 비교를 키 단위로 바꾼다(시계열은 파생 필드).

- [ ] **Step 6: collect 배선** — `hublib/render.py` `_build_verify_safe` 의 `out = build_verify(chat_kb=chat)` →
```python
        out = build_verify(chat_kb=chat, report_stocks=data.get("stocks"))
```
출력 로그에 한 줄:
```python
            rep = out.get("report") or {}
            if rep.get("enabled"):
                print(f"  리포트 코호트 -- {rep['meta']['calls']}콜 / {rep['meta']['stocks']}종목 · 테마 {len(out.get('themes') or [])}")
```

- [ ] **Step 7: 실제 수집 1회 (네트워크)** — CI 시간 영향을 본다.

```bash
time python build_hub.py --phase collect --src . --json knowledge_base.json 2>&1 | grep -E "검증|코호트|✗"
```
기대: 리포트 코호트 ≈ 200콜/80종목. 새 종목 가격 수집은 첫 1회만(이후 증분). 전체 collect 가 **기존 대비 +3분 이상** 늘면 `REPORT_COHORT_MAX_STOCKS` 를 80으로 낮추고 보고.

- [ ] **Step 8: 커밋**

```bash
git add hublib/verify.py hublib/momentum.py hublib/render.py tests/test_verify.py
git commit -m "feat(verify): 리포트 수급 코호트(verify.report)·테마 집계(verify.themes)·종목 주가 시계열(series) — 채팅 코호트와 분리"
```

---

## Task 5: AI 증분 요약 (F5 데이터)

**Files:**
- Create: `hublib/ai_summary.py`, `tests/test_ai_summary.py`
- Rewrite: `ai_digest.py`
- Modify: `hublib/render.py` (`render` 에 news_flags 병합), `.github/workflows/build.yml`, `.gitignore`

원칙: **API 호출 함수는 주입**(테스트는 가짜 `call`), 캐시 키로 같은 입력은 다시 묻지 않는다. 하루 호출 상한을 둔다. 모델 ID 는 기존처럼 `AI_DIGEST_MODEL` 환경변수(기본값 유지). 뉴스 배치 응답에서 **빠진 url 은 `relevant` 로 캐시**한다 — 모델의 누락을 매일 다시 묻는 비용보다, 기본값(표시)으로 두는 쪽이 싸고 안전하다(neutral 은 흐리게 표시일 뿐이다).

- [ ] **Step 1: 테스트 (RED)** — `tests/test_ai_summary.py`:

```python
# -*- coding: utf-8 -*-
"""AI 증분 요약 — 캐시·잡 선택·오케스트레이션. API 는 가짜 call 로 대체."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _kb():
    return {
        "build": {"to": "2026-08-22", "generated": "2026-08-22 07:30"},
        "stance": [{"date": "2026-08-22", "headline": "H", "quote": "Q", "points": ["p1"]}],
        "sentiment": [{"date": "2026-08-22", "score": 10}],
        "events": [], "sectors": [{"theme": "반도체·메모리", "mentions": [{"date": "2026-08-22"}]}],
        "stocks": [{"name": "삼성전자", "count": 9, "mentions": [{"date": "2026-08-22", "label": "기관 순매수", "note": "n1"}]},
                   {"name": "기아", "count": 2, "mentions": [{"date": "2026-07-01", "label": "자동차", "note": "n2"}]}],
        "chat": {"news": [{"title": "반도체 급등", "url": "https://x/1"}, {"title": "맛집 추천", "url": "https://x/2"}]},
    }


def test_cache_roundtrip(tmp_path):
    from hublib.ai_summary import AiCache
    c = AiCache(str(tmp_path / "ai.json")); assert c.get("k") is None
    c.put("k", {"a": 1}); c.save()
    assert AiCache(str(tmp_path / "ai.json")).get("k") == {"a": 1}


def test_parse_json_extracts_object_from_text():
    from hublib.ai_summary import parse_json
    assert parse_json('앞말 {"a": [1, 2]} 뒷말') == {"a": [1, 2]}
    assert parse_json("no json") is None


def test_stock_jobs_skip_cached_and_cap(tmp_path):
    from hublib.ai_summary import AiCache, stock_jobs
    c = AiCache(str(tmp_path / "ai.json"))
    jobs = stock_jobs(_kb(), c, limit=10)
    assert [j["name"] for j in jobs] == ["삼성전자", "기아"]
    assert jobs[0]["key"] == "stock:삼성전자:2026-08-22"
    c.put("stock:삼성전자:2026-08-22", {"text": "x", "as_of": "2026-08-22"})
    assert [j["name"] for j in stock_jobs(_kb(), c, limit=10)] == ["기아"]
    assert len(stock_jobs(_kb(), c, limit=1)) == 1


def test_news_batches_skip_cached(tmp_path):
    from hublib.ai_summary import AiCache, news_batches
    c = AiCache(str(tmp_path / "ai.json"))
    c.put("news:https://x/1", "relevant")
    b = news_batches(_kb(), c, batch=40, max_batches=5)
    assert b == [[{"title": "맛집 추천", "url": "https://x/2"}]]


def test_run_orchestrates_with_fake_call_and_caches(tmp_path):
    from hublib.ai_summary import AiCache, run
    calls = []

    def fake(prompt, max_tokens):
        calls.append(prompt)
        if "주간 다이제스트" in prompt:
            return json.dumps({"title": "t", "summary": "s", "themes": [], "stocks": [], "risks": []})
        if "3줄" in prompt:
            return json.dumps({"lines": ["a", "b", "c"]})
        if "뉴스 제목" in prompt:
            return json.dumps({"flags": {"https://x/1": "relevant", "https://x/2": "neutral"}})   # 배치의 모든 url 에 답한다
        return json.dumps({"text": "최근 기관 순매수로 언급"})
    c = AiCache(str(tmp_path / "ai.json"))
    out = run(_kb(), c, fake, model="m")
    assert out["digest"]["title"] == "t" and out["daily"] == {"date": "2026-08-22", "lines": ["a", "b", "c"]}
    assert out["stock_reasons"]["삼성전자"]["text"] == "최근 기관 순매수로 언급"
    assert out["news_flags"] == {"https://x/2": "neutral"}
    n1 = len(calls)
    out2 = run(_kb(), c, fake, model="m")        # 두 번째 실행은 전부 캐시 히트
    assert len(calls) == n1 and out2["news_flags"] == out["news_flags"]


def test_run_survives_bad_responses(tmp_path):
    from hublib.ai_summary import AiCache, run
    out = run(_kb(), AiCache(str(tmp_path / "ai.json")), lambda p, m: "garbage", model="m")
    assert out["digest"] is None and out["daily"] is None and out["stock_reasons"] == {} and out["news_flags"] == {}
```

- [ ] **Step 2: 구현** — `hublib/ai_summary.py`:

```python
# -*- coding: utf-8 -*-
"""AI 요약 — 위클리 다이제스트(기존) + 데일리 3줄 + 종목 '왜 언급됐나' + 뉴스 neutral 플래그. 증분 캐시.

API 호출은 call(prompt, max_tokens) -> str 로 주입한다(테스트·오프라인). 계약: 스펙 §3.3 C6.
"""
import datetime
import json
import os
import re

from hublib.config import _fmt_kst

WINDOW_DAYS = 7
STOCK_JOBS_PER_RUN = 30
NEWS_BATCH = 40
NEWS_MAX_BATCHES = 5
CACHE_VERSION = 1


class AiCache:
    """키 → 결과 캐시. 손상·버전 불일치 시 비어 있는 상태로 폴백."""

    def __init__(self, path="build/ai_cache.json"):
        self.path, self.data, self.dirty = path, {}, False
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if raw.get("v") == CACHE_VERSION:
                self.data = raw.get("items") or {}
        except Exception:
            self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value; self.dirty = True

    def save(self):
        if not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"v": CACHE_VERSION, "items": self.data}, f, ensure_ascii=False)


def parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _cutoff(kb):
    to = (kb.get("build") or {}).get("to") or ""
    return to, (datetime.date.fromisoformat(to) - datetime.timedelta(days=WINDOW_DAYS)).isoformat() if to else ""


def _recent(obj, cutoff):
    return [m for m in (obj.get("mentions") or []) if (m.get("date") or "") >= cutoff and "W" not in (m.get("date") or "")]


def weekly_ctx(kb):
    to, cutoff = _cutoff(kb)
    stance = [s for s in kb.get("stance", []) if (s.get("date") or "") >= cutoff and "W" not in (s.get("date") or "")]
    sec_top = sorted(((s["theme"], len(_recent(s, cutoff))) for s in kb.get("sectors", [])), key=lambda x: -x[1])[:8]
    stk_top = sorted(((s["name"], len(_recent(s, cutoff))) for s in kb.get("stocks", [])), key=lambda x: -x[1])[:15]
    return {"기간": f"{cutoff} ~ {to}",
            "데일리_스탠스": [{"date": s["date"], "headline": s.get("headline", ""), "quote": (s.get("quote") or "")[:300],
                            "points": (s.get("points") or [])[:4]} for s in stance][-7:],
            "센티멘트": [{"date": s["date"], "score": s["score"]} for s in kb.get("sentiment", []) if (s.get("date") or "") >= cutoff],
            "핫_섹터(언급수)": [f"{n} {c}회" for n, c in sec_top if c],
            "핫_종목(언급수)": [f"{n} {c}회" for n, c in stk_top if c],
            "포착된_이벤트": [{"seen": e["seen"], "title": e["title"]} for e in kb.get("events", []) if (e.get("seen") or "") >= cutoff][:12]}


WEEKLY_PROMPT = """당신은 투자 리서치 요약 전문가입니다. 아래는 '프롬어스' 투자 커뮤니티의 최근 7일 데일리 리포트를 구조화한 데이터입니다.

{ctx}

이 데이터를 근거로 주간 다이제스트를 작성하세요. 데이터에 없는 사실을 지어내지 마세요.
아래 JSON 형식으로만 답하세요 (다른 텍스트 금지):
{{"title": "이번 주를 관통하는 한 줄 헤드라인 (20자 내외)", "summary": "주간 시장 흐름 요약 3~4문장.", "themes": [{{"name": "테마명", "note": "1문장"}}], "stocks": ["핫_종목 목록에 있는 이름만, 최대 5"], "risks": ["1문장", "최대 3개"]}}"""

DAILY_PROMPT = """아래는 '프롬어스' 투자 커뮤니티의 {date} 데일리 리포트 요약 데이터입니다.

{ctx}

이 데이터만 근거로 오늘의 핵심을 3줄로 요약하세요. 각 줄 40자 이내, 데이터에 없는 사실 금지.
JSON 형식으로만 답하세요: {{"lines": ["...", "...", "..."]}}"""

STOCK_PROMPT = """'프롬어스' 리포트에서 종목 '{name}' 이(가) 최근 언급된 근거입니다 (최신순):

{ctx}

이 종목이 왜 언급되고 있는지 한 문장(60자 이내)으로 요약하세요. 데이터에 없는 사실 금지. 투자 권유 표현 금지.
JSON 형식으로만 답하세요: {{"text": "..."}}"""

NEWS_PROMPT = """아래 뉴스 제목 목록에서 주식·경제·산업·시장과 무관한 항목(맛집·일상·유머 등)을 'neutral', 관련 있으면 'relevant' 로 분류하세요.

{ctx}

JSON 형식으로만 답하세요: {{"flags": {{"<url>": "neutral|relevant", ...}}}} — 목록의 모든 url 을 포함하세요."""


def stock_jobs(kb, cache, limit=STOCK_JOBS_PER_RUN):
    """언급 많은 순으로, (종목, 최근 언급일) 키가 캐시에 없는 종목만 limit 개."""
    jobs = []
    for s in sorted(kb.get("stocks") or [], key=lambda x: (-(x.get("count") or 0), x.get("name") or "")):
        ms = s.get("mentions") or []
        if not ms:
            continue
        last = max(m.get("date") or "" for m in ms)
        key = f"stock:{s['name']}:{last}"
        if cache.get(key):
            continue
        ctx = [{"date": m.get("date"), "label": m.get("label") or m.get("theme") or "", "note": (m.get("note") or "")[:160]}
               for m in sorted(ms, key=lambda m: m.get("date") or "", reverse=True)[:6]]
        jobs.append({"name": s["name"], "key": key, "as_of": last, "ctx": ctx})
        if len(jobs) >= limit:
            break
    return jobs


def news_batches(kb, cache, batch=NEWS_BATCH, max_batches=NEWS_MAX_BATCHES):
    todo = [{"title": n.get("title") or "", "url": n.get("url") or ""}
            for n in ((kb.get("chat") or {}).get("news") or []) if n.get("url") and not cache.get(f"news:{n['url']}")]
    return [todo[i:i + batch] for i in range(0, min(len(todo), batch * max_batches), batch)]


def _cached_or_call(cache, key, prompt, call, max_tokens, parse):
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        val = parse(parse_json(call(prompt, max_tokens)))
    except Exception as e:
        print(f"  ✗ AI {key}: {repr(e)[:80]}")
        return None
    if val is not None:
        cache.put(key, val)
    return val


def run(kb, cache, call, model=""):
    """kb + 캐시 + call → ai_digest.json 내용. 어떤 단계가 실패해도 나머지는 진행한다."""
    to, cutoff = _cutoff(kb)
    j = lambda o: json.dumps(o, ensure_ascii=False, indent=1)
    digest = _cached_or_call(cache, f"weekly:{cutoff}~{to}", WEEKLY_PROMPT.format(ctx=j(weekly_ctx(kb))), call, 1200,
                             lambda d: d if isinstance(d, dict) and d.get("title") else None)
    today = [s for s in kb.get("stance", []) if s.get("date") == to]
    daily = None
    if today:
        d = _cached_or_call(cache, f"daily:{to}", DAILY_PROMPT.format(date=to, ctx=j({"스탠스": today[0], "센티멘트": [s for s in kb.get("sentiment", []) if s.get("date") == to]})),
                            call, 400, lambda d: d if isinstance(d, dict) and isinstance(d.get("lines"), list) else None)
        daily = {"date": to, "lines": [str(x) for x in d["lines"][:3]]} if d else None
    reasons = {}
    for job in stock_jobs(kb, cache):
        r = _cached_or_call(cache, job["key"], STOCK_PROMPT.format(name=job["name"], ctx=j(job["ctx"])), call, 200,
                            lambda d: {"text": d["text"], "as_of": job["as_of"]} if isinstance(d, dict) and d.get("text") else None)
        if r:
            reasons[job["name"]] = r
    for s in kb.get("stocks") or []:          # 이번에 새로 만들지 않았어도 캐시에 있는 최신 것은 싣는다
        ms = s.get("mentions") or []
        if ms and s["name"] not in reasons:
            hit = cache.get(f"stock:{s['name']}:{max(m.get('date') or '' for m in ms)}")
            if hit:
                reasons[s["name"]] = hit
    flags = {}
    for batch in news_batches(kb, cache):          # 배치는 캐시 키가 없다(항목별로 저장) — _cached_or_call 을 쓰지 않는다
        try:
            d = parse_json(call(NEWS_PROMPT.format(ctx=j(batch)), 1500))
            got = d.get("flags") if isinstance(d, dict) and isinstance(d.get("flags"), dict) else {}
        except Exception as e:
            print(f"  ✗ AI news batch: {repr(e)[:80]}"); got = {}
        for item in batch:
            flag = got.get(item["url"])
            if flag not in ("neutral", "relevant") and got:
                flag = "relevant"          # 응답은 왔는데 이 url 만 빠짐 → 관련으로 보고 캐시 (매일 다시 묻지 않는다)
            if flag in ("neutral", "relevant"):
                cache.put(f"news:{item['url']}", flag)
    for n in (kb.get("chat") or {}).get("news") or []:
        f = cache.get(f"news:{n.get('url')}")
        if f == "neutral":
            flags[n["url"]] = "neutral"
    return {"generated": _fmt_kst(), "range": f"{cutoff}~{to}", "model": model,
            "digest": digest, "daily": daily, "stock_reasons": reasons, "news_flags": flags}
```

- [ ] **Step 3: 통과 확인** — `python -m pytest tests/test_ai_summary.py -q` → PASS.

- [ ] **Step 4: `ai_digest.py` 재작성** (얇은 CLI — 키 없으면 exit 0):

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 요약 CLI — knowledge_base.json → ai_digest.json (위클리·데일리·종목 이유·뉴스 플래그). 로직은 hublib/ai_summary.py.
키가 없거나 실패해도 exit 0 — 빌드를 막지 않는다."""
import json
import os
import sys
import urllib.request

from hublib.ai_summary import AiCache, run

KB_PATH, OUT_PATH = "knowledge_base.json", "ai_digest.json"
MODEL = os.environ.get("AI_DIGEST_MODEL", "claude-sonnet-4-6")


def bail(msg):
    print(f"ℹ️ AI 요약 생략 — {msg}"); sys.exit(0)


def make_call(key):
    def call(prompt, max_tokens):
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": MODEL, "max_tokens": max_tokens,
                             "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
            headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=90) as r:
            res = json.load(r)
        return "".join(b.get("text", "") for b in res.get("content", []))
    return call


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        bail("ANTHROPIC_API_KEY 미설정")
    if not os.path.exists(KB_PATH):
        bail(f"{KB_PATH} 없음")
    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)
    cache = AiCache()
    out = run(kb, cache, make_call(key), model=MODEL)
    cache.save()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"→ {OUT_PATH} — 위클리 {'O' if out['digest'] else 'X'} · 데일리 {'O' if out['daily'] else 'X'} · "
          f"종목 이유 {len(out['stock_reasons'])} · neutral 뉴스 {len(out['news_flags'])}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: render 에 news_flags 병합** — `hublib/render.py` `render()` 의 ai_digest try 블록 안에서, `knowledge_base.json` 을 **재기록하는 `json.dump(data, f, ...)` 줄 바로 뒤**(= 재기록에는 플래그가 들어가지 않고, 이어지는 split 출력에만 들어간다)에:
```python
            flags = (data["ai_digest"] or {}).get("news_flags") or {}
            if flags:
                data = _apply_news_flags(data, flags)
```
(기반 계획이 `render()` 를 소유하지만 이미 머지된 뒤이므로, 이 3줄 + 아래 모듈 함수 1개만 추가한다.)
모듈에 추가:
```python
def _apply_news_flags(data, flags):
    """neutral 로 분류된 채팅 뉴스에 neutral:true 를 붙인 새 data (C6)."""
    mark = lambda items: [({**n, "neutral": True} if flags.get(n.get("url")) == "neutral" else n) for n in (items or [])]
    chat = data.get("chat")
    stocks = [({**s, "chat": {**s["chat"], "news": mark(s["chat"].get("news"))}} if s.get("chat") else s)
              for s in (data.get("stocks") or [])]
    out = {**data, "stocks": stocks}
    if chat:
        out["chat"] = {**chat, "news": mark(chat.get("news"))}
    return out
```
(이 병합은 `knowledge_base.json` 재기록 **이후**·split **이전**에 적용되도록 순서를 맞춘다 — 재기록 줄 뒤로 옮긴다.)

- [ ] **Step 6: 워크플로·gitignore** — `AI weekly digest` 스텝 **앞**에:

```yaml
      - name: Restore AI cache (증분 요약)
        uses: actions/cache@v4
        with:
          path: build/ai_cache.json
          key: ai-cache-v1-${{ github.run_id }}
          restore-keys: ai-cache-v1-
```
`.gitignore` 에 `build/ai_cache.json`.

- [ ] **Step 7: 확인 + 커밋**

```bash
python -m pytest tests/test_ai_summary.py tests/test_phases.py -q
ANTHROPIC_API_KEY= python ai_digest.py     # 키 없이 exit 0 확인
git add hublib/ai_summary.py ai_digest.py hublib/render.py tests/test_ai_summary.py .github/workflows/build.yml .gitignore
git commit -m "feat(ai): 증분 캐시 기반 AI 요약 — 데일리 3줄·종목 언급 이유·뉴스 neutral 플래그 (호출 주입·하루 상한)"
```

---

## Task 6: 문서 + PR

- [ ] **README 스키마 표에 행 추가**: `whats_new`(C5), `verify.report`/`verify.themes`/`stocks[].series`(C4), `search[].hay/source` + 채팅 kind(C3), `ai_digest.daily/stock_reasons/news_flags`(C6), `feed.json` 산출물, 새 캐시 3종(`kb_summary`·`ai_cache`·`price_cache`)과 CI 키.
- [ ] **전량 테스트** `VERIFY_SKIP=1 python -m pytest tests/ generator/test_parse.py -q`
- [ ] **PR** — 제목 "허브 데이터 확장: 채팅 검색·리포트 코호트·what's new·AI 증분·스키마/예산". 본문에 각 계약(C3~C6) 산출 예시 JSON 한 줄씩. 스펙 §3.4 범위 밖으로 건드린 것(`render()` 3줄 + `_apply_news_flags`, `momentum.py` 메모이즈 2줄)을 명시한다 — 기반이 먼저 머지돼 충돌은 없다. 머지 후 Track B 가 실데이터로 UI 를 확인할 수 있다(B 는 그 전에도 널 허용으로 개발한다).

## 범위 밖

- 발화자 랭킹(README 정책) · 익명화(F7, 제외) · 뉴스 neutral 을 허브에서 숨길지 여부는 Track B 판단(데이터는 플래그만)
