# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 리포트 집계·검색 인덱스."""
import datetime, json
from hublib.config import PRINCIPLE_BUCKETS, STOCK_STOPWORDS, THEME_KEYS, is_supply_card, supply_tag
from hublib.parse import expand_stock_names, normalize_stock, parse_num, parse_target_prices, sector_theme, split_stock_token


def aggregate(reports, window_days=31):
    reports = sorted(reports, key=lambda r: r["sort_date"])
    # 섹터·테마·종목·수급 = '최근 1개월' 윈도우만 집계. 전략·용어·시계열 = 전체.
    valid = [r["sort_date"] for r in reports if r.get("sort_date") and r["sort_date"] <= "9999"]
    recent, recent_from = reports, (reports[0]["sort_date"] if reports else "")
    if valid:
        try:
            max_d = max(datetime.date.fromisoformat(d) for d in valid)
            cutoff = (max_d - datetime.timedelta(days=window_days)).isoformat()
            recent = [r for r in reports if r.get("sort_date", "") >= cutoff]
            recent_from = cutoff
        except Exception:
            pass
    stocks = {}
    sectors = {}
    supply_days = []   # 날짜별 스마트머니 TOP
    for r in recent:
        label = r.get("date") or r.get("id")
        # 이혜나 대표님 발언 텍스트(인용·핵심메시지·불릿) — 섹터 가중 판정용
        rep_text = ""
        for _i in r["insights"]:
            if "이혜나" in _i.get("name", ""):
                rep_text += " " + (_i.get("quote") or "")
                rep_text += " " + " ".join((k.get("title","")+" "+k.get("desc","")) for k in _i.get("key_messages", []))
                rep_text += " " + " ".join((b.get("text") or "") for b in _i.get("bullets", []))
        rep_text = rep_text.lower()
        for sec in r["sectors"]:
            supply = is_supply_card(sec["name"])
            theme = sector_theme(sec["name"])
            if not supply:
                S = sectors.setdefault(theme, {"theme": theme, "names": set(), "mentions": [],
                                               "stocks": set(), "count": 0, "rep": 0})
                S["names"].add(sec["name"]); S["count"] += 1
                S["mentions"].append({"date": label, "rtype": r["type"], "id": r["id"],
                                      "name": sec["name"], "sub": sec["sub"],
                                      "stocks": sec["stocks"], "note": sec["note"]})
                # 대표님 직접 언급 가중: 섹터 노트에 대표님/이혜나 또는 대표님 발언에 테마 키워드
                note_l = sec["note"] or ""
                kws = THEME_KEYS.get(theme, (theme,))
                if ("대표님" in note_l) or ("이혜나" in note_l) or any(kw and kw.lower() in rep_text for kw in kws):
                    S["rep"] += 1
            else:
                supply_days.append({"date": label, "rtype": r["type"], "id": r["id"],
                                    "label": sec["name"], "who": supply_tag(sec["name"]),
                                    "stocks": sec["stocks"], "note": sec["note"]})
            for raw in sec["stocks"]:
                nm0, ann = split_stock_token(raw)
                for nm in expand_stock_names(normalize_stock(nm0)):
                    if not nm or nm in STOCK_STOPWORDS or len(nm) < 2 or nm[0].isdigit():
                        continue   # 날짜·숫자 토큰(예: '27일') 제거
                    T = stocks.setdefault(nm, {"name": nm, "mentions": [], "sectors": set(),
                                               "themes": set(), "supply_tags": set(),
                                               "targets": [], "count": 0,
                                               "theme_count": 0, "supply_count": 0})
                    T["count"] += 1
                    tp = parse_target_prices(raw)
                    for t in tp:
                        t2 = dict(t); t2["date"] = label; t2["context"] = raw
                        T["targets"].append(t2)
                    if supply:
                        T["supply_count"] += 1
                        T["supply_tags"].add(supply_tag(sec["name"]))
                        T["mentions"].append({"date": label, "rtype": r["type"], "id": r["id"],
                                              "source": "수급", "label": supply_tag(sec["name"]),
                                              "annotation": ann, "note": sec["note"][:160]})
                    else:
                        T["theme_count"] += 1
                        T["sectors"].add(sec["name"]); T["themes"].add(theme)
                        S["stocks"].add(nm)
                        T["mentions"].append({"date": label, "rtype": r["type"], "id": r["id"],
                                              "source": "테마", "label": sec["name"], "theme": theme,
                                              "annotation": ann, "note": sec["note"][:200]})
    # set → list
    for S in sectors.values():
        S["names"] = sorted(S["names"]); S["stocks"] = sorted(S["stocks"])
    for T in stocks.values():
        T["sectors"] = sorted(T["sectors"]); T["themes"] = sorted(T["themes"])
        T["supply_tags"] = sorted(T["supply_tags"])
        # 목표가 중복 제거
        seen = set(); uniq = []
        for t in T["targets"]:
            k = (t["value"], t["unit"], t["date"])
            if k not in seen:
                seen.add(k); uniq.append(t)
        T["targets"] = uniq

    # ── 팀 스탠스 변화 타임라인 (이혜나 대표님 중심) ──
    stance = []
    for r in reports:
        rep = next((i for i in r["insights"] if "이혜나" in i["name"]), None)
        if not rep and r["insights"]:
            rep = r["insights"][0]
        stance.append({
            "date": r.get("date") or r.get("id"),
            "rtype": r["type"], "id": r["id"], "weekday": r.get("weekday", ""),
            "headline": r["headline"], "subhead": r["subhead"],
            "name": rep["name"] if rep else "",
            "quote": rep["quote"] if rep else "",
            "points": [k["title"] for k in (rep["key_messages"] if rep else [])][:4] or
                      [b["text"][:80] for b in (rep["bullets"] if rep else [])][:4],
            "report_quote": r["quote"].get("text", ""),
        })

    # ── 살아있는 전략 원칙 ──
    principles = []
    for name, icon, keys in PRINCIPLE_BUCKETS:
        occ = []
        for r in reports:
            label = r.get("date") or r.get("id")
            pool = []
            pool += [(a["text"], "체크리스트") for a in r["actions"]]
            pool += [(s["title"] + " — " + s["desc"], "주간전략") for s in r["strategy"]]
            pool += [(i["quote"], "대표님") for i in r["insights"] if i["quote"]]
            pool += [(k["title"] + " — " + k["desc"], "핵심메시지")
                     for i in r["insights"] for k in i["key_messages"]]
            for text, src in pool:
                if text and any(k in text for k in keys):
                    occ.append({"date": label, "rtype": r["type"], "id": r["id"],
                                "text": text[:200], "source": src})
        if occ:
            # 날짜 중복 정리
            seen = set(); uniq = []
            for o in occ:
                k = (o["date"], o["text"][:40])
                if k not in seen:
                    seen.add(k); uniq.append(o)
            principles.append({"principle": name, "icon": icon, "count": len(uniq),
                               "last_seen": max(o["date"] for o in uniq),
                               "occurrences": uniq})
    principles.sort(key=lambda p: (-p["count"], p["last_seen"]), reverse=False)
    principles.sort(key=lambda p: p["count"], reverse=True)

    # ── 용어집 (교육성 카드 전체 누적, 같은 용어 재등장 시 최신본으로 갱신) ──
    glossary = {}
    for r in reports:   # 전체 기간 누적
        for g in r["glossary"]:
            term = (g.get("title") or "").strip()
            if not term:
                continue
            glossary[term] = {"term": term, "tag": g.get("tag", ""),
                              "body": g["body"], "date": r.get("date") or r.get("id"),
                              "id": r["id"]}

    # ── 이벤트/촉매 (참고용) ──
    events = []
    for r in reports:
        for n in r["next"]:
            events.append({"title": n["title"], "desc": n["desc"],
                           "seen": r.get("date") or r.get("id"), "id": r["id"]})

    # ── 센티멘트(리포트 톤) — 키워드 사전 기반 ──
    POS_WORDS = ("상승", "급등", "강세", "반등", "돌파", "호재", "순매수", "상향", "개선",
                 "기대", "수혜", "서프라이즈", "최고", "호조", "확대", "가속", "랠리", "신고가", "낙관")
    NEG_WORDS = ("하락", "급락", "약세", "악재", "순매도", "하향", "이탈", "우려", "부진",
                 "리스크", "경고", "쇼크", "공포", "불안", "축소", "둔화", "침체", "신저가", "비관")
    sentiment = []
    for r in reports:
        if r["type"] != "daily":
            continue
        pool = [r.get("headline", ""), r.get("subhead", "")]
        pool += [(i.get("quote") or "") for i in r["insights"]]
        pool += [(ind.get("explain") or "") for ind in r["indicators"]]
        pool += [(s.get("note") or "") for s in r["sectors"]]
        pool.append(json.dumps(r.get("timeline", []), ensure_ascii=False))
        text = " ".join(pool)
        pos = sum(text.count(w) for w in POS_WORDS)
        neg = sum(text.count(w) for w in NEG_WORDS)
        tot = pos + neg
        score = round(100 * (pos - neg) / tot) if tot else 0
        sentiment.append({"date": r["date"], "id": r["id"], "score": score,
                          "pos": pos, "neg": neg, "headline": r.get("headline", "")})

    # ── 지표 시계열 (데일리) — 라벨 표준화, 하루 1값 ──
    EXC = ("선물", "인버스", "레버리지", "저점", "거래대금")
    CANON = [
        ("코스피", lambda n: "코스피" in n and "코스닥" not in n and not any(x in n for x in EXC)),
        ("코스닥", lambda n: "코스닥" in n and not any(x in n for x in EXC)),
        ("원/달러", lambda n: "원/달러" in n or "환율" in n),
        ("WTI 유가", lambda n: "WTI" in n or "유가" in n),
        ("나스닥", lambda n: "나스닥" in n),
        ("美 10년물 금리", lambda n: "10년물" in n and ("美" in n or "미" in n)),
    ]
    series = {k: [] for k, _ in CANON}
    for r in reports:
        if r["type"] != "daily":
            continue
        for canon, match in CANON:
            for ind in r["indicators"]:
                if not match(ind["label"]):
                    continue
                if "%" in (ind["value"] or ""):     # 등락률(%) 값은 종가 레벨이 아님 → 제외
                    continue
                v = parse_num(ind["value"])
                if v is not None:
                    series[canon].append({"date": r["date"], "value": v, "change": ind["change"]})
                    break
    series = {k: v for k, v in series.items() if v}

    return {
        "stocks": sorted(stocks.values(), key=lambda x: (-x["count"], x["name"])),
        "sectors": sorted(sectors.values(), key=lambda x: -x["count"]),
        "supply_days": supply_days,
        "recent_from": recent_from,
        "recent_reports": len(recent),
        "window_days": window_days,
        "stance": stance,
        "principles": principles,
        "glossary": sorted(glossary.values(), key=lambda x: x["date"], reverse=True),
        "events": events,
        "sentiment": sentiment,
        "series": {k: v for k, v in series.items()},
    }

def build_search(reports, agg):
    idx = []
    def add(kind, title, snippet, date, rid, tags=None, extra=None):
        idx.append({"kind": kind, "title": title or "", "snippet": (snippet or "")[:300],
                    "date": date or "", "id": rid or "", "tags": tags or [], "extra": extra or {}})
    for r in reports:
        label = r.get("date") or r.get("id")
        for t in r["timeline"]:
            add("타임라인", t["title"], t["desc"], label, r["id"],
                [x["text"] for x in t["tags"]])
        for i in r["insights"]:
            if i["quote"]:
                add("인사이트", i["name"], i["quote"], label, r["id"], [i["role"]])
            for k in i["key_messages"]:
                add("핵심메시지", k["title"], k["desc"], label, r["id"], [i["name"]])
        for rd in r["readings"]:
            add("리서치/자료", rd["title"], rd["body"], label, r["id"], [rd["tag"]])
        for s in r["sectors"]:
            add("섹터", s["name"], s["note"], label, r["id"], s["stocks"])
    for st in agg["stocks"]:
        add("종목", st["name"], "; ".join(m["annotation"] for m in st["mentions"] if m["annotation"])[:300],
            st["mentions"][-1]["date"] if st["mentions"] else "", "",
            st["themes"], {"count": st["count"]})
    for g in agg["glossary"]:
        add("용어", g["term"], g["body"], g["date"], g["id"], [g["tag"]])
    for p in agg["principles"]:
        add("전략원칙", p["principle"], "; ".join(o["text"] for o in p["occurrences"][:3]),
            p["last_seen"], "", [], {"count": p["count"]})
    return idx
