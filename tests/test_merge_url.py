# -*- coding: utf-8 -*-
"""채팅 뉴스 URL 은 http/https 만 허브에 실린다 — javascript: 등은 빈 문자열로 (Q4)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_safe_url_allows_only_http_https():
    from merge_hub import _safe_url
    assert _safe_url("https://n.news.naver.com/a/1") == "https://n.news.naver.com/a/1"
    assert _safe_url("http://x.y/z") == "http://x.y/z"
    assert _safe_url("javascript:alert(1)") == ""
    assert _safe_url("data:text/html,hi") == ""
    assert _safe_url(None) == ""


def test_merge_filters_news_urls():
    from merge_hub import merge
    kb = {"build": {}, "stocks": [{"name": "삼성전자", "count": 1, "mentions": []}], "glossary": [], "sectors": []}
    chat = {"stocks": {"삼성전자": {"count": 2, "mentions": [], "news": [
                {"date": "2026-08-01", "title": "a", "url": "javascript:alert(1)"},
                {"date": "2026-08-02", "title": "b", "url": "https://ok/1"}]}},
            "news": [{"date": "2026-08-01", "title": "a", "url": "javascript:alert(1)", "stocks": []}]}
    out, _ = merge(kb, chat)
    urls = [n["url"] for n in out["stocks"][0]["chat"]["news"]]
    assert "javascript:alert(1)" not in urls and "https://ok/1" in urls
    assert out["chat"]["news"][0]["url"] == ""
