#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 요약 CLI — knowledge_base.json → ai_digest.json (위클리·데일리·종목 이유·뉴스 플래그).

로직은 hublib/ai_summary.py 에 있고 여기서는 키 확인·HTTP 호출·파일 IO·사용량 로그만 한다.
키가 없거나 실패해도 exit 0 — 빌드를 막지 않는다.

모델은 Sonnet 5.5(기본). thinking 은 끌 수 없고(`disabled` 는 400) `output_config.effort` 로만 조절한다 —
thinking 토큰이 max_tokens 에 포함되므로 상한은 hublib/ai_summary 의 *_MAX_TOKENS 로 여유를 둔다.
뉴스 neutral 분류만 Batches API 2단계 배치(비용 50%↓, 플래그 최대 하루 지연 수용) —
weekly/daily/종목 이유는 당일성이 필요해 동기 call(urllib) 유지. SDK 미설치 시 뉴스도 동기 폴백.
"""
import json
import os
import sys
import urllib.request

from hublib.ai_summary import AiCache, run

KB_PATH, OUT_PATH = "knowledge_base.json", "ai_digest.json"
MODEL = os.environ.get("AI_DIGEST_MODEL", "claude-sonnet-5-5")
DEFAULT_EFFORT = "medium"      # 분류·요약은 medium 이면 충분 — 더 올리면 thinking 토큰만 는다
VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")   # API 가 받는 값. 잘못된 값은 모든 호출이 400 → 센티널 7일 잠금이라 main 이 먼저 막는다


def effort_from_env(env):
    """AI_DIGEST_EFFORT 정규화 — 빈 값(미설정 vars.*)·공백은 기본값, 대소문자는 정리. 유효성 판정은 main 이 bail 로 한다."""
    return (env.get("AI_DIGEST_EFFORT") or DEFAULT_EFFORT).strip().lower() or DEFAULT_EFFORT


EFFORT = effort_from_env(os.environ)
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT = 90


def bail(msg):
    print(f"ℹ️ AI 요약 생략 — {msg}")
    sys.exit(0)


def request_body(prompt, max_tokens, model=MODEL, effort=EFFORT):
    """Messages API 요청 본문. thinking 필드는 보내지 않는다 — Sonnet 5.5 에서 disabled 는 400, 기본이 adaptive."""
    return {"model": model, "max_tokens": max_tokens,
            "output_config": {"effort": effort},
            "messages": [{"role": "user", "content": prompt}]}


def usage_record(res):
    """응답 → 사용량 레코드(모델·종료 사유·입출력 토큰). 달러 환산은 하지 않는다 — 측정값만 남긴다."""
    usage = res.get("usage") or {}
    return {"model": res.get("model") or "", "stop_reason": res.get("stop_reason") or "",
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0)}


def summarize_usage(stats):
    """사용량 레코드 목록 → 합계 + 잘림(max_tokens)·거절(refusal) 건수. 비용 추적과 상한 튜닝의 근거."""
    return {"calls": len(stats),
            "input_tokens": sum(s["input_tokens"] for s in stats),
            "output_tokens": sum(s["output_tokens"] for s in stats),
            "truncated": sum(1 for s in stats if s["stop_reason"] == "max_tokens"),
            "refused": sum(1 for s in stats if s["stop_reason"] == "refusal"),
            "models": sorted({s["model"] for s in stats if s["model"]})}


def _warn_stop(rec):
    """잘림·거절은 조용히 파싱 실패로 묻히므로 로그에 드러낸다(실패 센티널 3회 → 7일 잠금의 원인)."""
    if rec["stop_reason"] == "max_tokens":
        print(f"  ⚠ AI 응답 잘림(max_tokens) — 출력 {rec['output_tokens']}토큰: *_MAX_TOKENS 상한을 올려야 한다", file=sys.stderr)
    elif rec["stop_reason"] == "refusal":
        print("  ⚠ AI 요청 거절(refusal) — 해당 항목은 실패 센티널로 기록된다", file=sys.stderr)


def _text_of(content):
    """content 블록을 타입으로 읽는다 — 응답 앞에 thinking 블록이 올 수 있다(adaptive thinking)."""
    return "".join(b.get("text", "") for b in content or [] if b.get("type") == "text")


def make_call(key, stats):
    """prompt → 응답 텍스트. 실패는 예외로 올려 보내고 호출부(ai_summary)가 단계별로 격리한다.
    stats 에 호출별 사용량을 모은다 — 워커 스레드에서 호출되지만 list.append 만 하므로 안전하다."""
    def call(prompt, max_tokens):
        req = urllib.request.Request(
            API_URL,
            data=json.dumps(request_body(prompt, max_tokens)).encode("utf-8"),
            headers={"content-type": "application/json", "x-api-key": key,
                     "anthropic-version": API_VERSION})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            res = json.load(r)
        rec = usage_record(res)
        stats.append(rec)
        _warn_stop(rec)
        return _text_of(res.get("content"))
    return call


def make_batch_ops(key, model, effort, stats):
    """Batches API — SDK 가 없으면 None(동기 폴백). 수거한 결과의 사용량도 stats 에 더한다(전일 제출분)."""
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic(api_key=key)

    def submit(reqs):
        b = client.messages.batches.create(requests=reqs)
        return b.id

    def retrieve(bid):
        return client.messages.batches.retrieve(bid).processing_status

    def results(bid):
        # errored/expired 요청은 succeeded 가 아니라 결과에서 빠진다 → 그 청크 url 들은
        # 캐시되지 않고 다음날 자동 재제출(자기 치유, 비용은 재시도 1회분).
        out = []
        for r in client.messages.batches.results(bid):
            if r.result.type != "succeeded":
                continue
            msg = r.result.message
            out.append({"custom_id": r.custom_id,
                        "text": next((blk.text for blk in msg.content if blk.type == "text"), "")})
            rec = usage_record({"model": msg.model, "stop_reason": msg.stop_reason,
                                "usage": {"input_tokens": msg.usage.input_tokens,
                                          "output_tokens": msg.usage.output_tokens}})
            stats.append(rec)
            _warn_stop(rec)
        return out

    return {"submit": submit, "retrieve": retrieve, "results": results, "model": model, "effort": effort}


def _usage_line(u, fallback_model):
    tail = (f" · 잘림 {u['truncated']}" if u["truncated"] else "") + (f" · 거절 {u['refused']}" if u["refused"] else "")
    return (f"   사용량 — {'/'.join(u['models']) or fallback_model} · effort {EFFORT} · 호출 {u['calls']} · "
            f"입력 {u['input_tokens']:,} · 출력 {u['output_tokens']:,} 토큰{tail}")


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        bail("ANTHROPIC_API_KEY 미설정")
    if EFFORT not in VALID_EFFORTS:
        bail(f"AI_DIGEST_EFFORT={EFFORT!r} 미지원 — {'|'.join(VALID_EFFORTS)} 중 하나")
    if not os.path.exists(KB_PATH):
        bail(f"{KB_PATH} 없음 (build_hub.py 먼저 실행)")
    try:
        with open(KB_PATH, encoding="utf-8") as f:
            kb = json.load(f)
    except Exception as e:
        bail(f"{KB_PATH} 읽기 실패 ({e})")
    if not (kb.get("build") or {}).get("to"):
        bail("기준일 없음")

    cache = AiCache(model=MODEL)       # 모델이 바뀌면 요약 키만 버리고 뉴스 플래그·pending 배치는 유지
    stats = []
    out = run(kb, cache, make_call(key, stats), model=MODEL, batch=make_batch_ops(key, MODEL, EFFORT, stats))
    cache.save()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"→ {OUT_PATH} — 위클리 {'O' if out['digest'] else 'X'} · 데일리 {'O' if out['daily'] else 'X'} · "
          f"종목 이유 {len(out['stock_reasons'])} · neutral 뉴스 {len(out['news_flags'])}")
    print(_usage_line(summarize_usage(stats), MODEL))


if __name__ == "__main__":
    main()
