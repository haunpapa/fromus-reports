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
        if _usable(cache.get(key)):
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


_FAIL_KEY = "__fail__"
FAIL_MAX = 3           # 이 횟수 연속 실패하면 TTL 동안 재시도하지 않는다
FAIL_TTL_DAYS = 7      # TTL 이 지나면 1회 더 시도 (모델·프롬프트가 고쳐졌을 수 있다)


def _fail_info(hit):
    """캐시 값이 실패 센티널이면 그 dict, 아니면 None."""
    return hit[_FAIL_KEY] if isinstance(hit, dict) and _FAIL_KEY in hit else None


def _usable(hit):
    """진짜 결과인가 — 실패 센티널·None 은 결과가 아니다."""
    return hit is not None and _fail_info(hit) is None


def _cached_or_call(cache, key, prompt, call, max_tokens, parse):
    """캐시 히트면 그대로. 실패도 센티널로 캐시해 FAIL_MAX 회 이후 TTL 까지 재호출하지 않는다.

    _run_stock_reasons 가 워커 스레드에서 부른다 — 센티널 cache.put 도 성공 put 과 같은
    단일 dict 연산(CPython)이라 스레드 안전성은 기존과 동일하다.
    """
    hit = cache.get(key)
    fail = _fail_info(hit)
    if fail:
        try:
            expiry = (datetime.date.fromisoformat(fail["at"]) + datetime.timedelta(days=FAIL_TTL_DAYS)).isoformat()
            if fail.get("n", 0) >= FAIL_MAX and datetime.date.today().isoformat() < expiry:
                return None
        except (KeyError, ValueError):
            fail = None            # 손상된 센티널 — 무시하고 재시도(다음 기록이 정상 형식으로 덮는다)
        hit = None
    if hit is not None:
        return hit
    try:
        val = parse(parse_json(call(prompt, max_tokens)))
    except Exception as e:
        print(f"  ✗ AI {key}: {repr(e)[:80]}")
        val = None
    if val is not None:
        cache.put(key, val)                                     # 성공이 센티널을 덮는다
    else:
        n = (fail or {}).get("n", 0) + 1
        cache.put(key, {_FAIL_KEY: {"n": n, "at": datetime.date.today().isoformat()}})
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
            if _usable(hit):
                reasons[s["name"]] = hit
    return reasons


_PENDING_KEY = "__news_batch__"


def _news_batch_requests(todo, model, batch=NEWS_BATCH):
    """미분류 뉴스 → (Batches API 요청 목록, {custom_id: [url]} 청크 멤버십). custom_id 'b<i>' 는 40건 묶음 인덱스."""
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    reqs = [{"custom_id": f"b{i}",
             "params": {"model": model, "max_tokens": 1500,
                        "messages": [{"role": "user", "content": NEWS_PROMPT.format(ctx=_j(chunk))}]}}
            for i, chunk in enumerate(chunks)]
    return reqs, {f"b{i}": [it["url"] for it in chunk] for i, chunk in enumerate(chunks)}


def _apply_news_results(cache, results, chunk_urls):
    """배치 결과(각 항목 {'custom_id','text'}) → 항목별 news: 캐시 기록.

    동기 경로(_run_news_flags 의 기존 규칙)와 동일하게: 응답은 왔는데 그 청크의 특정 url 만 빠졌으면
    relevant 로 간주해 캐시한다 — 모델이 매일 같은 url 을 누락해 무한 재제출되는 것을 막는다.
    chunk_urls: {custom_id: [url, ...]} — 제출 시점에 pending 에 함께 저장해 둔 청크 멤버십.
    배치 내 개별 요청이 errored/expired 면 results 에 그 custom_id 가 없어 해당 청크 url 들이
    캐시되지 않고 다음날 자동 재제출된다 — 의도된 자기 치유(비용은 재시도 1회분).
    """
    for r in results:
        d = parse_json(r.get("text") or "")
        flags = d.get("flags") if isinstance(d, dict) and isinstance(d.get("flags"), dict) else {}
        urls = (chunk_urls or {}).get(r.get("custom_id") or "")
        if urls is None:
            urls = list(flags)      # 멤버십 유실(레거시 pending·캐시 롤백) 폴백 — 응답에 있는 url 만이라도 반영(자기 치유)
        for url in urls:
            flag = flags.get(url)
            if flag not in ("neutral", "relevant") and flags:
                flag = "relevant"
            if flag in ("neutral", "relevant"):
                cache.put(f"news:{url}", flag)


def _run_news_flags(kb, cache, call, batch=None):
    if batch is None:
        def one(batch):                        # 배치는 캐시 키가 없다(항목별로 저장) — _cached_or_call 을 쓰지 않는다
            try:
                d = parse_json(call(NEWS_PROMPT.format(ctx=_j(batch)), 1500))
                return batch, d.get("flags") if isinstance(d, dict) and isinstance(d.get("flags"), dict) else {}
            except Exception as e:
                print(f"  ✗ AI news batch: {repr(e)[:80]}")
                return batch, {}

        with ThreadPoolExecutor(max_workers=AI_WORKERS) as ex:
            results = list(ex.map(one, news_batches(kb, cache)))
        for chunk, got in results:             # 캐시 기록은 메인 스레드에서만
            for item in chunk:
                flag = got.get(item["url"])
                if flag not in ("neutral", "relevant") and got:
                    flag = "relevant"      # 응답은 왔는데 이 url 만 빠짐 → 관련으로 보고 캐시 (매일 다시 묻지 않는다)
                if flag in ("neutral", "relevant"):
                    cache.put(f"news:{item['url']}", flag)
        return {n["url"]: "neutral" for n in ((kb.get("chat") or {}).get("news") or [])
                if n.get("url") and cache.get(f"news:{n['url']}") == "neutral"}

    # ── 배치 경로: ① 전일 배치 수거 ② 미분류분 새 배치 제출 ③ 캐시 기준 neutral 반환
    pending = cache.get(_PENDING_KEY)
    if isinstance(pending, dict) and pending.get("id"):
        try:
            if batch["retrieve"](pending["id"]) == "ended":
                _apply_news_results(cache, batch["results"](pending["id"]), pending.get("chunks"))
                cache.put(_PENDING_KEY, {})               # 수거 완료
        except Exception as e:
            print(f"  ✗ 뉴스 배치 수거 실패: {repr(e)[:80]}")
    todo = [{"title": n.get("title") or "", "url": n.get("url") or ""}
            for n in ((kb.get("chat") or {}).get("news") or [])
            if n.get("url") and not cache.get(f"news:{n['url']}")]
    still = cache.get(_PENDING_KEY)
    if todo and not (isinstance(still, dict) and still.get("id")):   # 한 번에 한 배치만
        try:
            reqs, chunks = _news_batch_requests(todo[:NEWS_BATCH * NEWS_MAX_BATCHES], batch.get("model", ""))
            bid = batch["submit"](reqs)
            cache.put(_PENDING_KEY, {"id": bid, "at": datetime.date.today().isoformat(), "chunks": chunks})
        except Exception as e:
            print(f"  ✗ 뉴스 배치 제출 실패: {repr(e)[:80]}")
    return {n["url"]: "neutral" for n in ((kb.get("chat") or {}).get("news") or [])
            if n.get("url") and cache.get(f"news:{n['url']}") == "neutral"}


def _stage(fn, *args):
    """단계 격리 — 실패는 None 으로 흡수하고 로그만 남긴다."""
    try:
        return fn(*args)
    except Exception as e:
        print(f"  ✗ AI 단계 {fn.__name__} 실패: {repr(e)[:80]}")
        return None


def run(kb, cache, call, model="", batch=None):
    """kb + 캐시 + call → ai_digest.json 내용. 어떤 단계가 실패해도 나머지는 진행한다.

    batch(Batches API ops)가 주입되면 뉴스 플래그만 2단계 배치 경로로 — 나머지 단계는 동기 call.
    """
    to, cutoff = _cutoff(kb)
    return {"generated": _fmt_kst(), "range": f"{cutoff}~{to}", "model": model,
            "digest": _stage(_run_weekly, kb, cache, call, to, cutoff),
            "daily": _stage(_run_daily, kb, cache, call, to),
            "stock_reasons": _stage(_run_stock_reasons, kb, cache, call) or {},
            "news_flags": _stage(_run_news_flags, kb, cache, call, batch) or {}}
