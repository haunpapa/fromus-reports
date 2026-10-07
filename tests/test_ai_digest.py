# -*- coding: utf-8 -*-
"""ai_digest CLI — Sonnet 5.5 전환: 요청 본문(effort)·max_tokens 여유·사용량 집계·캐시 버전. API 호출 없음."""
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _kb():
    return {
        "build": {"to": "2026-10-06", "generated": "2026-10-06 19:30"},
        "stance": [{"date": "2026-10-06", "headline": "H", "quote": "Q", "points": ["p1"]}],
        "sentiment": [{"date": "2026-10-06", "score": 10}],
        "events": [], "sectors": [],
        "stocks": [{"name": "삼성전자", "count": 9, "mentions": [{"date": "2026-10-06", "label": "기관 순매수", "note": "n1"}]}],
        "chat": {"news": [{"title": "반도체 급등", "url": "https://x/1"}]},
    }


def test_request_body_carries_model_effort_and_prompt():
    import ai_digest
    body = ai_digest.request_body("프롬프트", 500, model="claude-sonnet-5-5", effort="medium")
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 500
    assert body["output_config"] == {"effort": "medium"}
    assert body["messages"] == [{"role": "user", "content": "프롬프트"}]
    assert "thinking" not in body          # Sonnet 5.5: thinking.disabled 는 400 — effort 로만 제어한다


def test_default_model_and_effort_follow_env(monkeypatch):
    import ai_digest
    try:
        monkeypatch.delenv("AI_DIGEST_MODEL", raising=False)
        monkeypatch.delenv("AI_DIGEST_EFFORT", raising=False)
        importlib.reload(ai_digest)
        assert ai_digest.MODEL == "claude-sonnet-5-5"
        assert ai_digest.EFFORT == "medium"
        monkeypatch.setenv("AI_DIGEST_MODEL", "model-x")
        monkeypatch.setenv("AI_DIGEST_EFFORT", "low")
        importlib.reload(ai_digest)
        assert ai_digest.MODEL == "model-x" and ai_digest.EFFORT == "low"
    finally:
        monkeypatch.delenv("AI_DIGEST_MODEL", raising=False)
        monkeypatch.delenv("AI_DIGEST_EFFORT", raising=False)
        importlib.reload(ai_digest)


def test_usage_summary_totals_and_flags():
    import ai_digest
    stats = [
        {"model": "claude-sonnet-5-5", "input_tokens": 100, "output_tokens": 20, "stop_reason": "end_turn"},
        {"model": "claude-sonnet-5-5", "input_tokens": 50, "output_tokens": 500, "stop_reason": "max_tokens"},
        {"model": "claude-sonnet-5-5", "input_tokens": 10, "output_tokens": 0, "stop_reason": "refusal"},
    ]
    assert ai_digest.summarize_usage(stats) == {
        "calls": 3, "input_tokens": 160, "output_tokens": 520,
        "truncated": 1, "refused": 1, "models": ["claude-sonnet-5-5"],
    }
    assert ai_digest.summarize_usage([]) == {
        "calls": 0, "input_tokens": 0, "output_tokens": 0, "truncated": 0, "refused": 0, "models": [],
    }


def test_usage_record_from_api_response():
    import ai_digest
    res = {"model": "claude-sonnet-5-5-20260901", "stop_reason": "end_turn",
           "usage": {"input_tokens": 7, "output_tokens": 3, "cache_read_input_tokens": 0},
           "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": "{}"}]}
    assert ai_digest.usage_record(res) == {"model": "claude-sonnet-5-5-20260901", "stop_reason": "end_turn",
                                           "input_tokens": 7, "output_tokens": 3}
    assert ai_digest.usage_record({}) == {"model": "", "stop_reason": "", "input_tokens": 0, "output_tokens": 0}


def test_news_batch_requests_carry_effort_and_headroom():
    from hublib.ai_summary import NEWS_MAX_TOKENS, _news_batch_requests
    todo = [{"title": f"t{i}", "url": f"https://x/{i}"} for i in range(3)]
    reqs, chunks = _news_batch_requests(todo, "claude-sonnet-5-5", chunk_size=2, effort="medium")
    assert [r["custom_id"] for r in reqs] == ["b0", "b1"]
    p = reqs[0]["params"]
    assert p["model"] == "claude-sonnet-5-5"
    assert p["max_tokens"] == NEWS_MAX_TOKENS
    assert p["output_config"] == {"effort": "medium"}
    assert chunks == {"b0": ["https://x/0", "https://x/1"], "b1": ["https://x/2"]}
    reqs_plain, _ = _news_batch_requests(todo, "m", chunk_size=2)      # effort 미지정 호출자는 그대로
    assert "output_config" not in reqs_plain[0]["params"]


def test_max_tokens_headroom_for_thinking_and_new_tokenizer():
    from hublib import ai_summary as a
    # thinking 토큰이 max_tokens 에 포함되고 토크나이저가 약 30% 더 쓴다 — 기존 1200/400/200/1500 보다 여유를 둔다
    assert a.WEEKLY_MAX_TOKENS >= 2000
    assert a.DAILY_MAX_TOKENS >= 600
    assert a.STOCK_MAX_TOKENS >= 500
    assert a.NEWS_MAX_TOKENS >= 2500


def test_stages_call_with_headroom_constants(tmp_path):
    from hublib import ai_summary as a
    from hublib.ai_summary import AiCache, run
    seen = []

    def fake(prompt, max_tokens):
        seen.append(max_tokens)
        if "주간 다이제스트" in prompt:
            return json.dumps({"title": "T", "summary": "S", "themes": [], "stocks": [], "risks": []})
        if "3줄로 요약" in prompt:
            return json.dumps({"lines": ["a", "b", "c"]})
        if "한 문장" in prompt:
            return json.dumps({"text": "이유"})
        return json.dumps({"flags": {"https://x/1": "relevant"}})

    run(_kb(), AiCache(str(tmp_path / "ai.json")), fake)       # batch=None → 뉴스는 동기 폴백
    assert set(seen) == {a.WEEKLY_MAX_TOKENS, a.DAILY_MAX_TOKENS, a.STOCK_MAX_TOKENS, a.NEWS_MAX_TOKENS}


# ── 캐시: 모델 마커 — 모델이 바뀌면 요약 키만 버리고 뉴스 플래그·pending 배치는 지킨다 ──
def _write_cache(path, model, items):
    path.write_text(json.dumps({"v": 1, "model": model, "items": items}, ensure_ascii=False), encoding="utf-8")


_MIXED = {"weekly:a~b": {"title": "old"}, "daily:2026-10-06": {"lines": ["x"]},
          "stock:삼성전자:2026-10-06": {"text": "t", "as_of": "2026-10-06"},
          "stock:기아:2026-10-01": {"__fail__": {"n": 3, "at": "2026-10-01"}},
          "news:https://x/1": "neutral", "news:https://x/2": "relevant",
          "__news_batch__": {"id": "batch_paid", "at": "2026-10-06", "chunks": {"b0": ["https://x/3"]}}}


def test_cache_model_change_drops_summaries_keeps_news_and_pending(tmp_path):
    from hublib.ai_summary import CACHE_VERSION, AiCache
    assert CACHE_VERSION == 1                       # 버전 범프로 전량 삭제하지 않는다(뉴스 2,980건 재분류 3주 소요)
    p = tmp_path / "ai.json"; _write_cache(p, "claude-sonnet-4-6", _MIXED)
    c = AiCache(str(p), model="claude-sonnet-5-5")
    assert set(c.data) == {"news:https://x/1", "news:https://x/2", "__news_batch__"}
    assert c.dirty                                  # 마커 갱신을 저장해야 다음 빌드가 다시 지우지 않는다
    c.save()
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["model"] == "claude-sonnet-5-5" and raw["v"] == CACHE_VERSION


def test_cache_same_model_keeps_everything(tmp_path):
    from hublib.ai_summary import AiCache
    p = tmp_path / "ai.json"; _write_cache(p, "claude-sonnet-5-5", _MIXED)
    c = AiCache(str(p), model="claude-sonnet-5-5")
    assert c.data == _MIXED and not c.dirty


def test_cache_legacy_file_without_model_marker_migrates_once(tmp_path):
    from hublib.ai_summary import AiCache
    p = tmp_path / "ai.json"
    p.write_text(json.dumps({"v": 1, "items": _MIXED}, ensure_ascii=False), encoding="utf-8")   # 4.6 시절 파일
    c = AiCache(str(p), model="claude-sonnet-5-5")
    assert "weekly:a~b" not in c.data and c.data["news:https://x/1"] == "neutral"
    c.save()
    assert AiCache(str(p), model="claude-sonnet-5-5").data == c.data      # 두 번째 로드는 그대로


def test_cache_without_model_arg_is_unchanged_legacy_behavior(tmp_path):
    from hublib.ai_summary import AiCache
    p = tmp_path / "ai.json"; _write_cache(p, "claude-sonnet-4-6", _MIXED)
    assert AiCache(str(p)).data == _MIXED           # 테스트·오프라인 호출자(model 미지정)는 마이그레이션 안 함


# ── effort 환경변수 검증 ──
def test_effort_from_env_blank_falls_back_and_normalizes():
    import ai_digest
    assert ai_digest.effort_from_env({}) == "medium"
    assert ai_digest.effort_from_env({"AI_DIGEST_EFFORT": ""}) == "medium"      # 빈 vars.* → "" 가 400 을 내지 않게
    assert ai_digest.effort_from_env({"AI_DIGEST_EFFORT": " Low "}) == "low"
    assert ai_digest.effort_from_env({"AI_DIGEST_EFFORT": "turbo"}) == "turbo"  # 정규화만, 판정은 main 이 한다
    assert "turbo" not in ai_digest.VALID_EFFORTS and {"low", "medium", "high"} <= set(ai_digest.VALID_EFFORTS)


def test_main_bails_exit0_on_invalid_effort(monkeypatch):
    import pytest
    import ai_digest
    try:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
        monkeypatch.setenv("AI_DIGEST_EFFORT", "turbo")
        importlib.reload(ai_digest)
        with pytest.raises(SystemExit) as e:
            ai_digest.main()                         # 키 확인 직후, KB 읽기·네트워크 전에 멈춘다
        assert e.value.code == 0
    finally:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AI_DIGEST_EFFORT", raising=False)
        importlib.reload(ai_digest)


# ── 통합: 실제로 보내는 본문·블록 읽기·배치 SDK 형태 ──
def test_make_call_sends_effort_body_and_reads_text_blocks(monkeypatch):
    import io
    import urllib.request
    import ai_digest
    sent = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        sent["body"] = json.loads(req.data.decode("utf-8"))
        sent["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _Resp(json.dumps({"model": "claude-sonnet-5-5", "stop_reason": "end_turn",
                                 "usage": {"input_tokens": 11, "output_tokens": 4},
                                 "content": [{"type": "thinking", "thinking": ""},
                                             {"type": "text", "text": '{"text":"ok"}'}]}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    stats = []
    assert ai_digest.make_call("k", stats)("프롬프트", 500) == '{"text":"ok"}'
    assert sent["body"] == {"model": ai_digest.MODEL, "max_tokens": 500, "output_config": {"effort": ai_digest.EFFORT},
                            "messages": [{"role": "user", "content": "프롬프트"}]}
    assert sent["headers"]["x-api-key"] == "k" and sent["headers"]["anthropic-version"] == ai_digest.API_VERSION
    assert stats == [{"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "input_tokens": 11, "output_tokens": 4}]


def test_news_flags_pass_effort_into_batch_submit():
    from hublib.ai_summary import AiCache, _run_news_flags
    submitted = {}

    def submit(reqs):
        submitted["reqs"] = reqs
        return "b1"

    batch = {"submit": submit, "retrieve": lambda i: "in_progress", "results": lambda i: [],
             "model": "claude-sonnet-5-5", "effort": "medium"}
    _run_news_flags({"chat": {"news": [{"title": "t", "url": "https://a"}]}}, AiCache(path="/nonexistent/x.json"),
                    call=None, batch=batch)
    p = submitted["reqs"][0]["params"]
    assert p["model"] == "claude-sonnet-5-5" and p["output_config"] == {"effort": "medium"}


def test_batch_results_read_sdk_message_shape_and_usage(monkeypatch):
    import types
    import ai_digest
    NS = types.SimpleNamespace
    msg = NS(model="claude-sonnet-5-5", stop_reason="end_turn", usage=NS(input_tokens=5, output_tokens=2),
             content=[NS(type="thinking", thinking=""), NS(type="text", text='{"flags":{}}')])
    rows = [NS(custom_id="b0", result=NS(type="succeeded", message=msg)),
            NS(custom_id="b1", result=NS(type="errored", message=None))]

    class _Batches:
        def create(self, requests):
            return NS(id="batch_x")

        def retrieve(self, bid):
            return NS(processing_status="ended")

        def results(self, bid):
            return iter(rows)

    class _Anthropic:
        def __init__(self, api_key):
            self.messages = NS(batches=_Batches())

    monkeypatch.setitem(sys.modules, "anthropic", NS(Anthropic=_Anthropic))
    stats = []
    ops = ai_digest.make_batch_ops("k", "claude-sonnet-5-5", "medium", stats)
    assert ops["model"] == "claude-sonnet-5-5" and ops["effort"] == "medium"
    assert ops["submit"]([]) == "batch_x" and ops["retrieve"]("batch_x") == "ended"
    assert ops["results"]("batch_x") == [{"custom_id": "b0", "text": '{"flags":{}}'}]   # errored 행은 건너뛴다
    assert stats == [{"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "input_tokens": 5, "output_tokens": 2}]
