# -*- coding: utf-8 -*-
"""render 단계의 kb 분할·슬림화 — 순수 함수만. knowledge_base.json 은 건드리지 않고 출력(kb.*)만 줄인다.

계약: docs/superpowers/specs/2026-08-23-hub-improvement-design.md §3.3 C2
"""

# 셸(hub/*.js)이 D.reports 에서 읽는 필드 전부 — FILE 맵·캘린더·커맨드팔레트·원문 모달 제목
REPORT_FIELDS = ("type", "date", "id", "sort_date", "file", "headline", "subhead")


def slim_reports(reports):
    """리포트 레코드를 셸이 쓰는 필드로만 투영한다. 원문은 reports/**/*.html 링크로 남아 있다."""
    return [{k: r[k] for k in REPORT_FIELDS if k in r} for r in (reports or [])]


CHAT_CORE_KEYS = ("build", "themes", "co_edges")          # 관계망·섹터 카드가 부트 직후 읽는 것
CHAT_COUNT_KEYS = ("actions", "strategy", "targets", "qna", "news", "readings", "glossary")
STOCK_CHAT_OPINIONS = 3        # 종목 행 펼침 시 바로 보이는 의견 수 (hub/22_stocks.js CHAT_INIT_OP 와 같아야 한다)
STOCK_CHAT_NEWS = 4            # 같은 이유 (CHAT_INIT_NEWS)


def slim_stock_chat(chat):
    """종목 chat 블록을 초기 표시분 + 전체 개수로 줄인다. 전체는 stockchat 청크에 있다."""
    if not chat:
        return None
    ops = chat.get("opinions") or []
    news = chat.get("news") or []
    mkt = chat.get("market_news") or []
    return {
        "count": chat.get("count", 0), "signals": chat.get("signals", 0),
        "stance": chat.get("stance") or {}, "targets": chat.get("targets") or [],
        "opinions": ops[:STOCK_CHAT_OPINIONS], "news": news[:STOCK_CHAT_NEWS], "market_news": [],
        "opinions_n": len(ops), "news_n": len(news), "market_news_n": len(mkt),
    }


def split_payload(data):
    """knowledge_base 전체 → (core, {chat, search, glossary, stockchat}). 입력은 변경하지 않는다."""
    chat = data.get("chat") or None
    stocks = data.get("stocks") or []
    core = {k: v for k, v in data.items() if k not in ("search", "glossary")}
    core["reports"] = slim_reports(data.get("reports"))
    core["stocks"] = [({**s, "chat": slim_stock_chat(s["chat"])} if s.get("chat") else s) for s in stocks]
    core["build"] = {**(data.get("build") or {}),
                     "counts": {"glossary": len(data.get("glossary") or []),
                                "search": len(data.get("search") or [])}}
    if chat:
        core["chat"] = {**{k: chat[k] for k in CHAT_CORE_KEYS if k in chat},
                        "counts": {k: len(chat.get(k) or []) for k in CHAT_COUNT_KEYS}}
    else:
        core.pop("chat", None)
    chunks = {
        "chat": chat,
        "search": data.get("search") or [],
        "glossary": data.get("glossary") or [],
        "stockchat": {s["name"]: s["chat"] for s in stocks if s.get("chat")},
    }
    return core, chunks
