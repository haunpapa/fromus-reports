# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 채팅 방향성 발화(콜)의 사후 성과 검증.

설계: docs/superpowers/specs/2026-08-17-call-verification-design.md

순수 함수(extract_calls·judge_call·aggregate_calls)와 네트워크(fetch_prices)를 분리한다.
순수 함수는 네트워크 없이 전량 테스트되고, 어떤 실패도 허브 빌드를 깨뜨리지 않는다.
"""

BOT_SHARER = "김병철(봇)"
BENCHED_MARKETS = ("KR", "US")     # 대응 벤치마크 지수가 있는 시장
SNIPPET_MAX = 140


def extract_calls(chat_kb):
    """chat_kb → (calls, stats). 네트워크·파일 IO 없음.

    봇 발화와 무벤치마크(ASSET·미상) 종목을 뺀 뒤, 같은 (종목,날짜,방향)을 한 콜로
    병합하고, 같은 (종목,날짜)에 양방향이 공존하면 conflict 로 표시한다.
    conflict 콜도 반환한다 — 통계 제외는 aggregate_calls 의 책임이다.
    """
    raw = []
    for name, s in (chat_kb.get("stocks") or {}).items():
        market = s.get("market") or ""
        ticker = s.get("ticker") or ""
        if not ticker:
            continue                    # 티커 없으면 가격 대조 자체가 불가
        for m in s.get("mentions") or []:
            if m.get("stance") not in ("bullish", "bearish"):
                continue
            raw.append({
                "stock": name, "market": market, "ticker": ticker,
                "date": m.get("date") or "", "stance": m["stance"],
                "type": m.get("type") or "", "sharer": m.get("sharer") or "",
                "snippet": (m.get("snippet") or "")[:SNIPPET_MAX],
                "is_bot": m.get("sharer") == BOT_SHARER,
                "is_asset": market not in BENCHED_MARKETS,
            })

    core = [c for c in raw if not c["is_bot"] and not c["is_asset"]]

    # 정렬 후 병합 — set/dict 순서에 의존하지 않아 빌드마다 같은 바이트가 나온다
    merged = {}
    for c in sorted(core, key=lambda x: (x["date"], x["stock"], x["stance"], x["sharer"])):
        key = (c["stock"], c["date"], c["stance"])
        if key in merged:
            merged[key]["sources"].append({"sharer": c["sharer"], "snippet": c["snippet"]})
            continue
        merged[key] = {
            "stock": c["stock"], "market": c["market"], "ticker": c["ticker"],
            "date": c["date"], "stance": c["stance"], "type": c["type"],
            "conflict": False,
            "sources": [{"sharer": c["sharer"], "snippet": c["snippet"]}],
        }

    stance_by_day = {}
    for stock, date, stance in merged:
        stance_by_day.setdefault((stock, date), set()).add(stance)
    for call in merged.values():
        call["conflict"] = len(stance_by_day[(call["stock"], call["date"])]) > 1

    calls = sorted(merged.values(), key=lambda c: (c["date"], c["stock"], c["stance"]))
    stats = {
        "population": len(raw),
        "bot": sum(1 for c in raw if c["is_bot"]),
        "asset": sum(1 for c in raw if c["is_asset"]),
        "bot_and_asset": sum(1 for c in raw if c["is_bot"] and c["is_asset"]),
        "core": len(core),
        "duplicate": len(core) - len(merged),
        "conflict": sum(1 for c in calls if c["conflict"]),
    }
    return calls, stats
