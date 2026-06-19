# -*- coding: utf-8 -*-
"""knowledge_base.json(리포트 허브) + chat_kb.json(채팅) 비파괴 병합 → knowledge_base.merged.json
   - 같은 종목: 리포트 엔트리에 chat 블록(채팅 멘션/스탠스/뉴스) 추가
   - 채팅 전용 종목: source=chat 으로 신규 추가 (리포트엔 없지만 채팅에서 논의된 종목)
   - 최상위 chat 섹션(readings/glossary/actions/strategy/targets/qna/news) 추가
   사용:  python merge_hub.py knowledge_base.json chat_kb.json"""
import json, sys
from collections import Counter, defaultdict

OPINION_TYPES = {"view", "position"}
BOT_SHARERS = {"김병철(봇)"}   # 자동 시황 봇 — 채팅 근거에서 제외
OPINION_KEEP = 100
MARKET_KEEP = 50
NEWS_KEEP = 50

def _is_opinion(m):
    return m.get("type") in OPINION_TYPES

def _is_bot(m):
    return m.get("sharer") in BOT_SHARERS

def _name_in(m, nm, ticker):
    sn = m.get("snippet", "") or ""
    return (nm in sn) or (bool(ticker) and ticker in sn)

def _sort_desc(items):
    # date 키가 없어도 안전하게 내림차순(최신순)
    return sorted(items, key=lambda x: x.get("date", "") or "", reverse=True)

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

THEME_OP_KEEP = 8

def _theme_blocks(kb, chat_themes):
    """리포트 섹터 분류 기준으로 그 섹터 종목의 채팅 의견을 집계.
       chat_kb 테마 stocks 분류는 부정확(무관 종목 혼입)해 사용하지 않고,
       리포트 섹터(정확한 분류)의 stocks를 순회하되 섹터 이름이 채팅 테마에도 있을 때만 결합."""
    by_name = {s.get("name"): s for s in kb.get("stocks", [])}
    out = {}
    for sec in kb.get("sectors", []):
        tname = sec.get("theme")
        if tname not in chat_themes:   # 채팅에서 논의된 테마(이름 매칭)만
            continue
        ops, seen = [], []
        for nm in sec.get("stocks", []):   # ← 리포트 섹터 stocks(신뢰 가능한 분류)
            s = by_name.get(nm)
            if not s:
                continue
            sops = s.get("chat", {}).get("opinions") or []
            if sops:
                seen.append(nm)
            for op in sops:
                ops.append({**op, "stock": nm})   # 출처 종목 부착(불변)
        if not ops:   # 채팅 의견 있는 섹터 종목 없으면 결합 안 함
            continue
        ops = _sort_desc(ops)
        st = Counter(o.get("stance") for o in ops if o.get("stance") in ("bullish", "bearish", "watch"))
        out[tname] = {
            "opinions_count": len(ops),
            "stocks": seen,   # 채팅 의견 있는 섹터 종목만
            "stance": {"bullish": st["bullish"], "bearish": st["bearish"], "watch": st["watch"]},
            "opinions": ops[:THEME_OP_KEEP],
        }
    return out

def stance_summary(mentions):
    c=Counter(m.get("stance") for m in mentions if m.get("stance") in("bullish","bearish","watch"))
    return {"bullish":c["bullish"],"bearish":c["bearish"],"watch":c["watch"]}

def _chat_block(cs, nm, comap, with_targets=True):
    ments = [m for m in cs.get("mentions", []) if not _is_bot(m)]   # 봇 멘션 제외
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

def _strip_prior_chat(kb):
    """이미 병합된 산출물에 재실행해도 idempotent 하도록 직전 채팅 주입물을 제거."""
    stocks=kb.get("stocks")
    if isinstance(stocks,list):
        kb["stocks"]=[s for s in stocks if not s.get("chat_only")]
        for s in kb["stocks"]:
            s.pop("chat",None); s.pop("has_chat",None)
    gl=kb.get("glossary")
    if isinstance(gl,list):
        kb["glossary"]=[g for g in gl if g.get("source")!="chat"]
    kb.pop("chat",None)
    if isinstance(kb.get("build"),dict):
        kb["build"].pop("chat_merged",None); kb["build"].pop("chat_stocks_added",None)

def merge(kb, chat):
    # 주의: kb 를 in-place 로 보강(채팅 블록/종목/glossary 주입)하고 동일 객체를 반환한다.
    #       리포트 원본 데이터는 보존하되, 재실행 시 중복 누적을 막기 위해 직전 주입물을 먼저 제거.
    _strip_prior_chat(kb)
    cstocks=chat.get("stocks",{})
    comap = _build_comention_map(cstocks)        # ← 추가
    report_names=set()
    # 1) 리포트 종목에 chat 블록 주입
    for s in kb.get("stocks",[]):
        nm=s.get("name"); report_names.add(nm)
        cs=cstocks.get(nm)
        if cs:
            s["chat"]=_chat_block(cs, nm, comap)   # ← 시그니처 변경
            s["has_chat"]=True
    # 2) 채팅 전용 종목 추가
    added=0
    for nm,cs in cstocks.items():
        if nm in report_names: continue
        if cs.get("count",0)<2 and not cs.get("mentions"): continue
        kb.setdefault("stocks",[]).append({"name":nm,"count":0,"source":"chat",
            "market":cs.get("market",""),"ticker":cs.get("ticker",""),"themes":cs.get("themes",[]),
            "mentions":[],"sectors":[],"supply_tags":[],"targets":cs.get("targets",[])[:5],
            "chat":_chat_block(cs, nm, comap),       # ← 시그니처 변경
            "has_chat":True,"chat_only":True})
        added+=1
    # 3) glossary 병합(채팅 교육/용어 → source 표시)
    for g in chat.get("glossary",[])+chat.get("readings",[]):
        kb.setdefault("glossary",[]).append({"tag":g.get("tag","📚 채팅"),"title":g.get("title",""),
            "body":g.get("body",""),"source":"chat","date":g.get("date",""),"by":g.get("sharer","")})
    # 4) 최상위 chat 섹션
    kb["chat"]={"build":chat.get("build",{}),
        "actions":chat.get("actions",[]),"strategy":chat.get("strategy",[]),
        "targets":chat.get("targets",[]),"qna":chat.get("qna",[]),
        "news":chat.get("news",[]),"readings":chat.get("readings",[]),
        "glossary":chat.get("glossary",[]),
        "stocks_added":added,"themes":_theme_blocks(kb, chat.get("themes", {}))}
    # build 메타에 표시
    kb.setdefault("build",{})["chat_merged"]=True
    kb["build"]["chat_stocks_added"]=added
    return kb, added

if __name__=="__main__":
    kbp=sys.argv[1] if len(sys.argv)>1 else "knowledge_base.json"
    cbp=sys.argv[2] if len(sys.argv)>2 else "chat_kb.json"
    kb=json.load(open(kbp,encoding="utf-8"))
    chat=json.load(open(cbp,encoding="utf-8"))
    merged,added=merge(kb,chat)
    out="knowledge_base.merged.json"
    json.dump(merged,open(out,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
    linked=sum(1 for s in merged.get("stocks",[]) if s.get("has_chat") and not s.get("chat_only"))
    print(f"병합 완료 → {out}")
    print(f"  리포트 종목에 채팅근거 연결: {linked}개")
    print(f"  채팅 전용 종목 추가: {added}개")
    print(f"  채팅 섹션: 액션 {len(merged['chat']['actions'])} · 전략 {len(merged['chat']['strategy'])} · 목표가 {len(merged['chat']['targets'])} · Q&A {len(merged['chat']['qna'])} · 뉴스 {len(merged['chat']['news'])}")
