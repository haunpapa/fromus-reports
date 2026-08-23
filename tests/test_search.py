# -*- coding: utf-8 -*-
"""검색 인덱스 보강 — hay 사전 토큰화 + 채팅 kind (스펙 C3)."""
import os
import sys

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


def test_build_chat_search_news_and_opinion_only():
    """목표가는 검색 인덱스에 싣지 않는다 (2026-08-23 사용자 결정 — 채팅 탭 섹션과 함께 제거)."""
    from hublib.search import build_chat_search
    out = build_chat_search(_chat())
    kinds = [i["kind"] for i in out]
    assert kinds.count("채팅뉴스") == 1 and kinds.count("채팅의견") == 1
    assert "목표가" not in kinds, "chat.targets 가 있어도 검색 항목으로 만들지 않는다"
    news = next(i for i in out if i["kind"] == "채팅뉴스")
    assert news["title"] == "반도체 급등" and news["extra"] == {"url": "https://x/1", "outlet": "연합뉴스", "stocks": ["삼성전자"], "sharer": "탱이"}
    assert "삼성전자" in news["tags"] and "반도체·메모리" in news["tags"]
    op = next(i for i in out if i["kind"] == "채팅의견")
    assert op["title"] == "삼성전자 · 가" and op["snippet"] == "삼전 간다 길게"
    assert op["extra"] == {"stock": "삼성전자", "sharer": "가", "stance": "bullish", "date": "2026-08-01"}
    assert all(i["source"] == "chat" and i["hay"] for i in out)


def test_build_chat_search_skips_bot_and_research_and_bad_urls():
    from hublib.search import build_chat_search
    chat = _chat()
    chat["news"][0]["url"] = "javascript:alert(1)"
    out = build_chat_search(chat)
    assert not [i for i in out if i["kind"] == "채팅뉴스"], "비 http 링크 뉴스는 싣지 않는다"
    ops = [i for i in out if i["kind"] == "채팅의견"]
    assert len(ops) == 1 and ops[0]["extra"]["sharer"] == "가"
