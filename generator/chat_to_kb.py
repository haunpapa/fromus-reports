# -*- coding: utf-8 -*-
"""채팅 → chat_kb.json (허브 knowledge_base 호환). stocks/themes/readings/glossary/actions/strategy/targets/qna/news."""
import json, re
from collections import defaultdict, Counter
import fromus_taxonomy as T

def CANON(n): return T._CANON_ALIGN.get(n, n)
TEACHERS={"ㄱ 이혜나","밝쌤👩🏻‍🏫","황유정@ggulmoney_ssam","김병철","김병철(봇)","탱이"}
URL=re.compile(r"https?://[^\s]+")
SRC_MARK=("키움","한지영","Bloomberg","블룸버그","장 시작 전","개장전","개장 전","마감 시황","마감시황","[출처","출처:","리서치","Three Points","컨센서스","목표주가","Preview","애널리스트","증권 ","증권]","UBS","Jefferies","골드만","모건","다올","미래에셋","신한","하나증권","NH투자")

import hashlib
def _anon(name):
    if name in TEACHERS: return name          # 운영진은 리포트에 이미 공개됨
    return "프로미·"+hashlib.md5(name.encode()).hexdigest()[:4]
def _sanitize(kb):
    for st in kb["stocks"].values():
        for m in st["mentions"]: m["sharer"]=_anon(m["sharer"])
    for arr in ("actions","strategy","readings","glossary"):
        for it in kb.get(arr,[]):
            if "sharer" in it: it["sharer"]=_anon(it["sharer"])
    for n in kb.get("news",[]): n["sharer"]=_anon(n.get("sharer",""))
    for q in kb.get("qna",[]):
        q["q_by"]=_anon(q["q_by"]); q["a_by"]=_anon(q["a_by"])
    for t in kb.get("targets",[]): t["sharer"]=_anon(t["sharer"])
    return kb

def build(msgs, links, signals, public=False):
    if not msgs:   # 빈 입력 방어 — 빈 스키마 반환(크래시 방지)
        return {"build":{"generated_from":"kakao_chat","messages":0,"members":0,"from":"","to":"",
                         "stocks":0,"themes":0,"news":0},
                "stocks":{},"themes":{},"news":[],"targets":[],
                "readings":[],"glossary":[],"actions":[],"strategy":[],"qna":[]}
    by_idx={m["idx"]:m for m in msgs}
    # ---------- stocks ----------
    stocks={}
    def S(name):
        c=CANON(name)
        if c not in stocks:
            meta=T.STOCK_META.get(c,{})
            sec=meta.get("sector","")
            pt=T.primary_theme(c)
            stocks[c]={"name":c,"market":meta.get("market",""),"ticker":meta.get("ticker",""),
                       "sector":sec,"count":0,"themes":Counter(),"_primary":pt,
                       "mentions":[],"news":[],"targets":[]}
            if pt: stocks[c]["themes"][pt]+=2   # 대표테마 시드(카탈로그 연결용; 최종 #1은 핀으로 보장)
        return stocks[c]
    # 전 메시지 스캔: count + 근접도 게이팅 테마(동시출현 노이즈 차단)
    for m in msgs:
        body=m["body"]
        for canon in T.match_stocks(body):
            S(canon)["count"]+=1
            for th in T.match_themes_for_stock(body, canon):
                S(canon)["themes"][th]+=1
    # 시그널 기반 mention(스탠스/유형/스니펫)
    for s in signals:
        for e, st_stance in s.get("stocks", []):       # proximity 귀속 + 종목별 stance
            st=S(e)
            ment={"date":s["date"],"sharer":s["sharer"],"source":"chat",
                  "stance":st_stance,"type":s["type"],"snippet":s["snippet"][:180]}
            if s.get("type") in ("view","position"):   # 의견만 원문 보존(research 제외)
                ment["full"]=s.get("full","")
            st["mentions"].append(ment)
    # ---------- themes ----------
    themes={}
    for m in msgs:
        for th in T.match_themes(m["body"]):
            T_=themes.setdefault(th,{"theme":th,"count":0,"stocks":set(),"mentions":[]})
            T_["count"]+=1
    for s in signals:
        for th in s["themes"]:
            if th in themes:  # signal themes are my-naming; map via match? keep separate
                pass
    # 시그널의 테마(내 명칭) → hub 테마는 본문 재매칭으로 일원화
    for canon,st in stocks.items():
        for th,_ in st["themes"].most_common(3):
            if th in themes: themes[th]["stocks"].add(canon)
    # ---------- news ----------
    news=[]
    for l in links:
        if l.get("category") not in("news","broker_report"): continue
        title=l.get("clean_title") or l.get("title") or ""
        if not title: continue
        sset=T.match_stocks(title); thset=T.match_themes(title)
        rec={"date":l["date"],"sharer":l["sharer"],"outlet":l.get("outlet",""),
             "title":title[:140],"url":l.get("resolved_url") or l["url"],
             "stocks":sorted(CANON(x) for x in sset),"themes":sorted(thset)}
        news.append(rec)
        for x in sset:
            S(x)["news"].append({"date":l["date"],"title":title[:120],"outlet":l.get("outlet",""),"url":rec["url"]})
    # ---------- targets ----------
    targets=[]
    for m in msgs:
        tps=T.parse_target_prices(m["body"])
        if not tps: continue
        sset=T.match_stocks(m["body"])
        stock=sorted(CANON(x) for x in sset)[:1]
        for tp in tps:
            rec={"stock":stock[0] if stock else "","value":tp["value"],"unit":tp["unit"],
                 "raw":tp["raw"],"date":m["date"],"sharer":m["sender"]}
            targets.append(rec)
            if stock: S(stock[0])["targets"].append(rec)
    # ---------- readings / glossary (교육) ----------
    readings=[]; glossary=[]
    EDU=("비유","쉽게 말","쉽게말","쉽게 풀","개념","용어","~란","라고 보면","정의","뜻은","뜻이","의미는",
         "쉽게 설명","예를 들","예시","한마디로","정리하면","풀어서","이해하기 쉽","요약하면")
    GLOSS=("용어","개념","뜻","란?","란 ","이란","무엇","정의")
    for m in msgs:
        if m["sender"] not in TEACHERS: continue
        text=URL.sub("",m["body"]).strip()
        if len(text)<140: continue
        if text.lstrip().startswith("[") or any(mk in text for mk in SRC_MARK): continue  # 퍼온 리서치 제외
        if not any(k in text for k in EDU): continue
        first=re.split(r"[\n.!?]",text)[0][:60]
        item={"tag":"📚 채팅 교육","title":first,"body":re.sub(r"\s+"," ",text)[:1200],
              "date":m["date"],"sharer":m["sender"]}
        (glossary if any(k in text[:80] for k in GLOSS) else readings).append(item)
    # ---------- actions (do/dont/watch) ----------
    actions=[]
    DONT=("금지","하지마","하지 마","하지않","하지 않","자제","주의","경계","위험","말자","말것","마세요","피하")
    WATCH=("지켜","주목","대기","관찰","체크","확인하","주시","봐야")
    DO=("하세요","챙기","점검","준비","매수 대기","확인 필수","해두","담아두","기억해")
    for m in msgs:
        if m["sender"] not in TEACHERS: continue
        text=URL.sub("",m["body"]).strip()
        if not (8<len(text)<300): continue
        ph=T.principle_hits(text)
        kind=""
        if any(k in text for k in DONT): kind="dont"
        elif any(k in text for k in WATCH): kind="watch"
        elif any(k in text for k in DO) or ph: kind="do"
        if not kind: continue
        actions.append({"kind":kind,"text":re.sub(r"\s+"," ",text)[:160],"date":m["date"],
                        "sharer":m["sender"],"principle":ph[0][0] if ph else ""})
    # ---------- strategy (원칙 버킷) ----------
    strategy=[]
    for m in msgs:
        if m["sender"] not in TEACHERS: continue
        text=URL.sub("",m["body"]).strip()
        ph=T.principle_hits(text)
        if not ph or len(text)<20: continue
        strategy.append({"title":ph[0][0],"emoji":ph[0][1],"desc":re.sub(r"\s+"," ",text)[:200],
                         "date":m["date"],"sharer":m["sender"]})
    # ---------- qna ----------
    qna=[]
    QEND=("?","？")
    QKW=("궁금","질문있","여쭤","인가요","될까요","맞나요","어떻게 하","해야 하나","뭔가요","무엇인가")
    for m in msgs:
        if m["sender"] in TEACHERS: continue
        text=URL.sub("",m["body"]).strip()
        if not(6<len(text)<120): continue
        if text.lstrip().startswith("[") or any(mk in text for mk in SRC_MARK): continue  # 헤드라인/리서치 제외
        is_q = text.rstrip().endswith(QEND) or any(k in text for k in QKW)
        if not is_q: continue
        # 다음 5개 메시지 중 교사 응답
        ans=None
        for j in range(m["idx"]+1,min(m["idx"]+6,len(msgs))):
            nb=by_idx.get(j)
            if nb and nb.get("room")==m.get("room") and nb["sender"] in TEACHERS:
                at=URL.sub("",nb["body"]).strip()
                if len(at)>=10: ans={"a":re.sub(r'\s+',' ',at)[:240],"a_by":nb["sender"],"a_date":nb["date"]}; break
        if ans:
            qna.append({"q":re.sub(r'\s+',' ',text)[:160],"q_by":m["sender"],"q_date":m["date"],**ans})
    # set→list
    for st in stocks.values():
        pt=st.pop("_primary","")
        # 보조 테마는 2회 이상 근접 매칭된 것만(1회성 우연 동시출현 제거)
        ranked=[t for t,c in st["themes"].most_common() if t!=pt and c>=2]
        st["themes"]=([pt]+ranked)[:3] if pt else ranked[:3]
    for th in themes.values(): th["stocks"]=sorted(th["stocks"])
    meta={"generated_from":"kakao_chat","messages":len(msgs),
          "members":len(set(m.get("sender") for m in msgs)),
          "from":msgs[0].get("date",""),"to":msgs[-1].get("date",""),
          "stocks":len(stocks),"themes":len(themes),"news":len(news)}
    kb={"build":meta,"stocks":stocks,"themes":themes,"news":news,"targets":targets,
            "readings":readings,"glossary":glossary,"actions":actions,"strategy":strategy,"qna":qna}
    return _sanitize(kb) if public else kb

def _find(*names):
    import os
    for base in (".", "온톨로지_데이터", os.path.join("..","온톨로지_데이터"), ".."):
        for nm in names:
            p=os.path.join(base,nm)
            if os.path.exists(p): return p
    raise FileNotFoundError(names)

if __name__=="__main__":
    msgs=[json.loads(l) for l in open(_find("메시지_구조화원문.jsonl","messages.jsonl"),encoding="utf-8")]
    links=json.load(open(_find("링크_제목포함.json","links_titled.json"),encoding="utf-8"))
    sig=json.load(open(_find("전략시그널.json","strategy_signals.json"),encoding="utf-8"))
    import sys as _s
    kb=build(msgs,links,sig, public=('--public' in _s.argv))
    json.dump(kb,open("chat_kb.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
    b=kb["build"]
    print(f"chat_kb.json 생성 · 종목 {b['stocks']} · 테마 {b['themes']} · 뉴스 {b['news']}")
    print(f"  교육(readings) {len(kb['readings'])} · 용어(glossary) {len(kb['glossary'])}")
    print(f"  액션 {len(kb['actions'])} · 전략 {len(kb['strategy'])} · 목표가 {len(kb['targets'])} · Q&A {len(kb['qna'])}")
    print()
    top=sorted(kb["stocks"].values(),key=lambda s:-s["count"])[:8]
    print("=== 종목 TOP8 (count · 테마 · 뉴스수) ===")
    for s in top: print(f"  {s['name']:12s} {s['count']:4d}회 · {','.join(s['themes'][:2])} · 뉴스{len(s['news'])} · 시그널{len(s['mentions'])}")
