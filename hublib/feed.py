# -*- coding: utf-8 -*-
"""JSON Feed 1.1 — 최근 리포트 + 오늘 달라진 것. RSS 리더·슬랙·봇 연동용."""
FEED_ITEMS = 30
PUBLISH_TIME = "T07:30:00+09:00"        # 빌드 시각(07:30 KST)을 항목 발행 시각으로 쓴다


def _join(base, path):
    return (base.rstrip("/") + "/" + path) if base else path


def _report_item(r, stance_by_id, base):
    st = stance_by_id.get(r.get("id"), {})
    points = "\n".join(f"- {p}" for p in (st.get("points") or []))
    return {"id": f"report:{r['id']}", "url": _join(base, r.get("file") or ""),
            "title": r.get("headline") or r["id"],
            # 위클리는 date 가 None·id 가 '2026-W18' 이라 RFC 3339 가 안 된다 → sort_date(실제 날짜) 우선
            "date_published": (r.get("sort_date") or r.get("date") or r["id"])[:10] + PUBLISH_TIME,
            "content_text": "\n".join(filter(None, [r.get("subhead"), points])) or (r.get("headline") or "")}


def _whatsnew_item(w, to, base):
    parts = []
    if w.get("new_stocks"):
        parts.append("신규 종목: " + ", ".join(f"{x['name']}({x['count']})" for x in w["new_stocks"][:10]))
    if w.get("surging"):
        parts.append("언급 급증: " + ", ".join(f"{x['name']} {x['prev']}→{x['recent']}" for x in w["surging"][:10]))
    if w.get("new_calls"):
        parts.append(f"새 콜 {len(w['new_calls'])}건")
    if w.get("new_targets"):
        parts.append("새 목표가: " + ", ".join(f"{x['stock']} {x['value']}{x['unit']}" for x in w["new_targets"][:10]))
    return {"id": f"whatsnew:{to}", "url": _join(base, "hub.html#home"), "title": f"오늘 달라진 것 — {to}",
            "date_published": to + PUBLISH_TIME, "content_text": "\n".join(parts) or "변화 없음"}


def build_feed(data, base_url=""):
    """knowledge_base → JSON Feed 1.1 dict. 입력은 변경하지 않는다."""
    b = data.get("build") or {}
    stance_by_id = {s.get("id"): s for s in (data.get("stance") or [])}
    reports = sorted((r for r in (data.get("reports") or []) if r.get("id")),
                     key=lambda r: r.get("sort_date") or r["id"], reverse=True)
    items = [_report_item(r, stance_by_id, base_url) for r in reports[:FEED_ITEMS]]
    if data.get("whats_new"):
        items.insert(0, _whatsnew_item(data["whats_new"], b.get("to") or "", base_url))
    return {"version": "https://jsonfeed.org/version/1.1", "title": "프롬어스 Knowledge Hub",
            "home_page_url": _join(base_url, "hub.html"), "feed_url": _join(base_url, "feed.json"),
            "language": "ko", "items": items}
