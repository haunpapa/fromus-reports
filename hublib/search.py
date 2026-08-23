# -*- coding: utf-8 -*-
"""검색 인덱스 보강 — 사전 토큰화(hay) + 채팅 항목(뉴스·의견). 순수 함수.

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
        it = {"kind": "채팅뉴스", "title": n.get("title") or "",
              "snippet": " · ".join(filter(None, [n.get("outlet"), ", ".join(stocks)]))[:SNIPPET_LIMIT],
              "date": n.get("date") or "", "id": "", "tags": stocks + themes + [n.get("sharer") or ""],
              "extra": {"url": n["url"], "outlet": n.get("outlet") or "", "stocks": stocks,
                        "sharer": n.get("sharer") or ""},
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


def build_chat_search(chat):
    """chat_kb → 채팅뉴스·채팅의견 검색 항목. 봇·자료(research)·비 http 링크 제외.
    목표가(chat.targets)는 싣지 않는다 — 채팅 탭 섹션과 함께 뺐다(2026-08-23)."""
    if not chat:
        return []
    return _news_items(chat) + _opinion_items(chat)
