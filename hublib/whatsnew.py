# -*- coding: utf-8 -*-
"""전일 빌드 대비 '오늘 달라진 것' — 요약(summarize)을 남겨 두고 다음 빌드에서 diff 한다. 순수 함수 + 파일 IO 2개.

계약: 스펙 §3.3 C5. 요약 파일은 build/kb_summary.json (actions/cache 로 보존).
"""
import json
import os

SURGE_MIN = 3        # 전일 대비 언급 +3 이상이면 '급증'
SUMMARY_PATH = "build/kb_summary.json"


def summarize(data):
    """다음 빌드에서 비교할 최소 지문 — 종목 언급수/최근일, 콜·목표가·리포트 키 목록."""
    b = data.get("build") or {}
    stocks = {}
    for s in data.get("stocks") or []:
        ms = s.get("mentions") or []
        stocks[s["name"]] = {"count": s.get("count") or 0,
                             "last": max((m.get("date") or "" for m in ms), default="")}
    v = data.get("verify") or {}
    # set() — 원본에 완전 중복 레코드가 있다(같은 사람이 같은 날 같은 목표가를 반복 게시).
    # 그대로 두면 홈 '오늘 달라진 것' 카드가 같은 항목을 여러 번 보여 준다.
    calls = sorted({f"{c['stock']}|{c['date']}|{c['stance']}" for c in (v.get("calls") or [])}) if v.get("enabled") else []
    targets = sorted({f"{t.get('stock','')}|{t.get('value','')}|{(t.get('unit') or '').strip()}|{t.get('date','')}"
                      for t in ((data.get("chat") or {}).get("targets") or [])})
    return {"to": b.get("to") or "", "generated": b.get("generated") or "", "stocks": stocks,
            "calls": calls, "targets": targets,
            "reports": sorted(r["id"] for r in (data.get("reports") or []) if r.get("id"))}


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
    """저장된 전일 요약. 없거나 손상됐으면 None — 그날은 diff 를 건너뛴다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_summary(path, summary):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)
