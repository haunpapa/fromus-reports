#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 요약 CLI — knowledge_base.json → ai_digest.json (위클리·데일리·종목 이유·뉴스 플래그).

로직은 hublib/ai_summary.py 에 있고 여기서는 키 확인·HTTP 호출·파일 IO 만 한다.
키가 없거나 실패해도 exit 0 — 빌드를 막지 않는다.
"""
import json
import os
import sys
import urllib.request

from hublib.ai_summary import AiCache, run

KB_PATH, OUT_PATH = "knowledge_base.json", "ai_digest.json"
MODEL = os.environ.get("AI_DIGEST_MODEL", "claude-sonnet-4-6")
API_URL = "https://api.anthropic.com/v1/messages"
TIMEOUT = 90


def bail(msg):
    print(f"ℹ️ AI 요약 생략 — {msg}")
    sys.exit(0)


def make_call(key):
    """prompt → 응답 텍스트. 실패는 예외로 올려 보내고 호출부(ai_summary)가 단계별로 격리한다."""
    def call(prompt, max_tokens):
        req = urllib.request.Request(
            API_URL,
            data=json.dumps({"model": MODEL, "max_tokens": max_tokens,
                             "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
            headers={"content-type": "application/json", "x-api-key": key,
                     "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            res = json.load(r)
        return "".join(b.get("text", "") for b in res.get("content", []))
    return call


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        bail("ANTHROPIC_API_KEY 미설정")
    if not os.path.exists(KB_PATH):
        bail(f"{KB_PATH} 없음 (build_hub.py 먼저 실행)")
    try:
        with open(KB_PATH, encoding="utf-8") as f:
            kb = json.load(f)
    except Exception as e:
        bail(f"{KB_PATH} 읽기 실패 ({e})")
    if not (kb.get("build") or {}).get("to"):
        bail("기준일 없음")

    cache = AiCache()
    out = run(kb, cache, make_call(key), model=MODEL)
    cache.save()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"→ {OUT_PATH} — 위클리 {'O' if out['digest'] else 'X'} · 데일리 {'O' if out['daily'] else 'X'} · "
          f"종목 이유 {len(out['stock_reasons'])} · neutral 뉴스 {len(out['news_flags'])}")


if __name__ == "__main__":
    main()
