# -*- coding: utf-8 -*-
"""AI 요약 — 위클리 다이제스트(기존) + 데일리 3줄 + 종목 '왜 언급됐나' + 뉴스 neutral 플래그. 증분 캐시.

API 호출은 call(prompt, max_tokens) -> str 로 주입한다(테스트·오프라인). 계약: 스펙 §3.3 C6.
"""
import datetime
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from hublib.ai_prompts import DAILY_PROMPT, NEWS_PROMPT, STOCK_PROMPT, WEEKLY_PROMPT
from hublib.config import _fmt_kst

WINDOW_DAYS = 7
STOCK_JOBS_PER_RUN = 30
NEWS_BATCH = 40
NEWS_MAX_BATCHES = 5
AI_WORKERS = 6                # 종목·뉴스 호출 동시성 — API 레이트리밋 안쪽에서 지연만 겹치게
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
        self.data[key] = value
        self.dirty = True

    def save(self):
        if not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"v": CACHE_VERSION, "items": self.data}, f, ensure_ascii=False)


def parse_json(text):
    """모델 응답에서 첫 JSON 객체를 뽑는다. 못 찾거나 깨졌으면 None."""
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
    """최근 7일 스탠스·센티멘트·핫섹터·핫종목·이벤트 — 위클리 프롬프트 입력."""
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
    """아직 분류 안 된 채팅 뉴스만 배치로. 하루 호출 상한 = batch × max_batches."""
    todo = [{"title": n.get("title") or "", "url": n.get("url") or ""}
            for n in ((kb.get("chat") or {}).get("news") or []) if n.get("url") and not cache.get(f"news:{n['url']}")]
    return [todo[i:i + batch] for i in range(0, min(len(todo), batch * max_batches), batch)]


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _cached_or_call(cache, key, prompt, call, max_tokens, parse):
    """캐시 히트면 그대로, 아니면 1회 호출 후 파싱 성공분만 캐시. 실패는 None."""
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


def _run_weekly(kb, cache, call, to, cutoff):
    return _cached_or_call(cache, f"weekly:{cutoff}~{to}", WEEKLY_PROMPT.format(ctx=_j(weekly_ctx(kb))), call, 1200,
                           lambda d: d if isinstance(d, dict) and d.get("title") else None)


def _run_daily(kb, cache, call, to):
    today = [s for s in kb.get("stance", []) if s.get("date") == to]
    if not today:
        return None
    ctx = {"스탠스": today[0], "센티멘트": [s for s in kb.get("sentiment", []) if s.get("date") == to]}
    d = _cached_or_call(cache, f"daily:{to}", DAILY_PROMPT.format(date=to, ctx=_j(ctx)), call, 400,
                        lambda d: d if isinstance(d, dict) and isinstance(d.get("lines"), list) else None)
    return {"date": to, "lines": [str(x) for x in d["lines"][:3]]} if d else None


def _run_stock_reasons(kb, cache, call):
    def one(job):
        return job["name"], _cached_or_call(cache, job["key"], STOCK_PROMPT.format(name=job["name"], ctx=_j(job["ctx"])), call, 200,
                                            lambda d, j=job: {"text": d["text"], "as_of": j["as_of"]} if isinstance(d, dict) and d.get("text") else None)

    with ThreadPoolExecutor(max_workers=AI_WORKERS) as ex:
        reasons = {name: r for name, r in ex.map(one, stock_jobs(kb, cache)) if r}
    for s in kb.get("stocks") or []:          # 이번에 새로 만들지 않았어도 캐시에 있는 최신 것은 싣는다
        ms = s.get("mentions") or []
        if ms and s["name"] not in reasons:
            hit = cache.get(f"stock:{s['name']}:{max(m.get('date') or '' for m in ms)}")
            if hit:
                reasons[s["name"]] = hit
    return reasons


def _run_news_flags(kb, cache, call):
    def one(batch):                            # 배치는 캐시 키가 없다(항목별로 저장) — _cached_or_call 을 쓰지 않는다
        try:
            d = parse_json(call(NEWS_PROMPT.format(ctx=_j(batch)), 1500))
            return batch, d.get("flags") if isinstance(d, dict) and isinstance(d.get("flags"), dict) else {}
        except Exception as e:
            print(f"  ✗ AI news batch: {repr(e)[:80]}")
            return batch, {}

    with ThreadPoolExecutor(max_workers=AI_WORKERS) as ex:
        results = list(ex.map(one, news_batches(kb, cache)))
    for batch, got in results:                 # 캐시 기록은 메인 스레드에서만
        for item in batch:
            flag = got.get(item["url"])
            if flag not in ("neutral", "relevant") and got:
                flag = "relevant"          # 응답은 왔는데 이 url 만 빠짐 → 관련으로 보고 캐시 (매일 다시 묻지 않는다)
            if flag in ("neutral", "relevant"):
                cache.put(f"news:{item['url']}", flag)
    return {n["url"]: "neutral" for n in ((kb.get("chat") or {}).get("news") or [])
            if n.get("url") and cache.get(f"news:{n['url']}") == "neutral"}


def run(kb, cache, call, model=""):
    """kb + 캐시 + call → ai_digest.json 내용. 어떤 단계가 실패해도 나머지는 진행한다."""
    to, cutoff = _cutoff(kb)
    return {"generated": _fmt_kst(), "range": f"{cutoff}~{to}", "model": model,
            "digest": _run_weekly(kb, cache, call, to, cutoff),
            "daily": _run_daily(kb, cache, call, to),
            "stock_reasons": _run_stock_reasons(kb, cache, call),
            "news_flags": _run_news_flags(kb, cache, call)}
