#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 위클리 다이제스트 생성기
============================
knowledge_base.json(최근 리포트 구조화 데이터)을 Claude API로 요약해
ai_digest.json 을 생성합니다. build_hub.py 가 이를 읽어 허브 홈에 표시합니다.

요구사항:
  - 환경변수 ANTHROPIC_API_KEY (GitHub Actions Secret 권장)
  - knowledge_base.json (build_hub.py 1차 실행 산출물)

키가 없거나 실패해도 exit 0 — 빌드 파이프라인을 막지 않습니다.
"""
import json, os, sys, re, datetime, urllib.request

KB_PATH = "knowledge_base.json"
OUT_PATH = "ai_digest.json"
MODEL = os.environ.get("AI_DIGEST_MODEL", "claude-sonnet-4-6")
WINDOW_DAYS = 7

def bail(msg):
    print(f"ℹ️ AI 다이제스트 생략 — {msg}")
    sys.exit(0)

key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
if not key:
    bail("ANTHROPIC_API_KEY 미설정")
if not os.path.exists(KB_PATH):
    bail(f"{KB_PATH} 없음 (build_hub.py 먼저 실행)")

kb = json.load(open(KB_PATH, encoding="utf-8"))
to = (kb.get("build") or {}).get("to") or ""
if not to:
    bail("기준일 없음")
cutoff = (datetime.date.fromisoformat(to) - datetime.timedelta(days=WINDOW_DAYS)).isoformat()

# ── 컨텍스트 구성 (최근 7일) ──
stance = [s for s in kb.get("stance", []) if (s.get("date") or "") >= cutoff and "W" not in (s.get("date") or "")]
sent   = [s for s in kb.get("sentiment", []) if (s.get("date") or "") >= cutoff]
events = [e for e in kb.get("events", []) if (e.get("seen") or "") >= cutoff][:12]

def recent_mentions(obj):
    return [m for m in (obj.get("mentions") or []) if (m.get("date") or "") >= cutoff and "W" not in (m.get("date") or "")]

sec_top = sorted(((s["theme"], len(recent_mentions(s))) for s in kb.get("sectors", [])),
                 key=lambda x: -x[1])[:8]
stk_top = sorted(((s["name"], len(recent_mentions(s))) for s in kb.get("stocks", [])),
                 key=lambda x: -x[1])[:15]

ctx = {
    "기간": f"{cutoff} ~ {to}",
    "데일리_스탠스": [{"date": s["date"], "headline": s["headline"], "quote": (s.get("quote") or "")[:300],
                      "points": s.get("points", [])[:4]} for s in stance][-7:],
    "센티멘트": [{"date": s["date"], "score": s["score"]} for s in sent],
    "핫_섹터(언급수)": [f"{n} {c}회" for n, c in sec_top if c],
    "핫_종목(언급수)": [f"{n} {c}회" for n, c in stk_top if c],
    "포착된_이벤트": [{"seen": e["seen"], "title": e["title"]} for e in events],
}

prompt = f"""당신은 투자 리서치 요약 전문가입니다. 아래는 '프롬어스' 투자 커뮤니티의 최근 {WINDOW_DAYS}일 데일리 리포트를 구조화한 데이터입니다.

{json.dumps(ctx, ensure_ascii=False, indent=1)}

이 데이터를 근거로 주간 다이제스트를 작성하세요. 데이터에 없는 사실을 지어내지 마세요.
아래 JSON 형식으로만 답하세요 (다른 텍스트 금지):
{{
 "title": "이번 주를 관통하는 한 줄 헤드라인 (20자 내외)",
 "summary": "주간 시장 흐름 요약 3~4문장. 센티멘트 변화와 스탠스 변화 포함.",
 "themes": [{{"name": "테마명", "note": "왜 주목받았는지 1문장"}}, ...최대 3개],
 "stocks": ["주목 종목명", ...최대 5개, 핫_종목 목록에 있는 이름만],
 "risks": ["체크할 리스크 1문장", ...최대 3개]
}}"""

req = urllib.request.Request(
    "https://api.anthropic.com/v1/messages",
    data=json.dumps({
        "model": MODEL, "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8"),
    headers={"content-type": "application/json", "x-api-key": key,
             "anthropic-version": "2023-06-01"},
)
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        res = json.load(r)
    text = "".join(b.get("text", "") for b in res.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    digest = json.loads(m.group(0))
except Exception as e:
    bail(f"API 호출/파싱 실패 ({e})")

out = {
    "generated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
    "range": f"{cutoff}~{to}",
    "model": MODEL,
    "digest": digest,
}
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"→ {OUT_PATH} 생성 — {digest.get('title','')}")
