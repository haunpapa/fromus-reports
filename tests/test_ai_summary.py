# -*- coding: utf-8 -*-
"""AI 증분 요약 — 캐시·잡 선택·오케스트레이션. API 는 가짜 call 로 대체."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _kb():
    return {
        "build": {"to": "2026-08-22", "generated": "2026-08-22 07:30"},
        "stance": [{"date": "2026-08-22", "headline": "H", "quote": "Q", "points": ["p1"]}],
        "sentiment": [{"date": "2026-08-22", "score": 10}],
        "events": [], "sectors": [{"theme": "반도체·메모리", "mentions": [{"date": "2026-08-22"}]}],
        "stocks": [{"name": "삼성전자", "count": 9, "mentions": [{"date": "2026-08-22", "label": "기관 순매수", "note": "n1"}]},
                   {"name": "기아", "count": 2, "mentions": [{"date": "2026-07-01", "label": "자동차", "note": "n2"}]}],
        "chat": {"news": [{"title": "반도체 급등", "url": "https://x/1"}, {"title": "맛집 추천", "url": "https://x/2"}]},
    }


def test_cache_roundtrip(tmp_path):
    from hublib.ai_summary import AiCache
    c = AiCache(str(tmp_path / "ai.json")); assert c.get("k") is None
    c.put("k", {"a": 1}); c.save()
    assert AiCache(str(tmp_path / "ai.json")).get("k") == {"a": 1}


def test_parse_json_extracts_object_from_text():
    from hublib.ai_summary import parse_json
    assert parse_json('앞말 {"a": [1, 2]} 뒷말') == {"a": [1, 2]}
    assert parse_json("no json") is None


def test_stock_jobs_skip_cached_and_cap(tmp_path):
    from hublib.ai_summary import AiCache, stock_jobs
    c = AiCache(str(tmp_path / "ai.json"))
    jobs = stock_jobs(_kb(), c, limit=10)
    assert [j["name"] for j in jobs] == ["삼성전자", "기아"]
    assert jobs[0]["key"] == "stock:삼성전자:2026-08-22"
    c.put("stock:삼성전자:2026-08-22", {"text": "x", "as_of": "2026-08-22"})
    assert [j["name"] for j in stock_jobs(_kb(), c, limit=10)] == ["기아"]
    assert len(stock_jobs(_kb(), c, limit=1)) == 1


def test_news_batches_skip_cached(tmp_path):
    from hublib.ai_summary import AiCache, news_batches
    c = AiCache(str(tmp_path / "ai.json"))
    c.put("news:https://x/1", "relevant")
    b = news_batches(_kb(), c, batch=40, max_batches=5)
    assert b == [[{"title": "맛집 추천", "url": "https://x/2"}]]


def test_run_orchestrates_with_fake_call_and_caches(tmp_path):
    from hublib.ai_summary import AiCache, run
    calls = []

    def fake(prompt, max_tokens):
        calls.append(prompt)
        if "주간 다이제스트" in prompt:
            return json.dumps({"title": "t", "summary": "s", "themes": [], "stocks": [], "risks": []})
        if "3줄" in prompt:
            return json.dumps({"lines": ["a", "b", "c"]})
        if "뉴스 제목" in prompt:
            return json.dumps({"flags": {"https://x/1": "relevant", "https://x/2": "neutral"}})
        return json.dumps({"text": "최근 기관 순매수로 언급"})
    c = AiCache(str(tmp_path / "ai.json"))
    out = run(_kb(), c, fake, model="m")
    assert out["digest"]["title"] == "t" and out["daily"] == {"date": "2026-08-22", "lines": ["a", "b", "c"]}
    assert out["stock_reasons"]["삼성전자"]["text"] == "최근 기관 순매수로 언급"
    assert out["news_flags"] == {"https://x/2": "neutral"}
    n1 = len(calls)
    out2 = run(_kb(), c, fake, model="m")        # 두 번째 실행은 전부 캐시 히트
    assert len(calls) == n1 and out2["news_flags"] == out["news_flags"]


def test_run_survives_bad_responses(tmp_path):
    from hublib.ai_summary import AiCache, run
    out = run(_kb(), AiCache(str(tmp_path / "ai.json")), lambda p, m: "garbage", model="m")
    assert out["digest"] is None and out["daily"] is None and out["stock_reasons"] == {} and out["news_flags"] == {}
