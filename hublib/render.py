# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 2단계 빌드(collect/render) + index.html 허브 버튼 주입.

collect: 파싱·집계·시세·모멘텀·검색·chat 병합 → knowledge_base.json (무거운 단계)
render : knowledge_base.json(+ai_digest.json) → kb.<hash>.json + hub 셸 (파싱·네트워크 없음)

render 단계는 bs4/yfinance import를 하지 않는다 — collect 는 함수 내부에서 지연 import.
"""
import os, re


HUB_BTN_CSS = ("\n.hub-btn{display:inline-block;margin-top:22px;padding:11px 24px;"
               "border:1px solid var(--gold-border);border-radius:100px;background:var(--gold-bg);"
               "color:var(--gold);text-decoration:none;font-size:14px;font-weight:600;"
               "transition:all .2s ease}\n"
               ".hub-btn:hover{background:var(--gold);color:#fff;transform:translateY(-1px);"
               "box-shadow:0 4px 14px rgba(184,134,11,.2)}\n")

HUB_BTN_HTML = '\n  <a href="hub.html" class="hub-btn">📊 지식 허브 — 검색·섹터·종목·전략 →</a>'

def inject_hub_button(index_path):
    if not os.path.exists(index_path):
        print(f"ℹ️ index.html 없음({index_path}) — 허브 버튼 주입 생략")
        return
    with open(index_path, encoding="utf-8") as f:
        html = f.read()
    if "hub-btn" in html:
        return  # 이미 주입됨
    changed = False
    if "</style>" in html:
        html = html.replace("</style>", HUB_BTN_CSS + "</style>", 1); changed = True
    m = re.search(r'(<p class="header-sub">.*?</p>)', html, re.S)
    if m:
        html = html[:m.end()] + HUB_BTN_HTML + html[m.end():]; changed = True
    if changed:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"→ {index_path} 에 지식 허브 버튼 주입 완료")


def _merge_chat_kb(data):
    """chat_kb.json(있으면) 을 knowledge_base 데이터에 병합. 실패해도 비병합 데이터 반환."""
    import json, sys
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chat_path = next((p for p in ("chat_kb.json", os.path.join(repo_root, "chat_kb.json"))
                      if os.path.exists(p)), None)
    if not chat_path:
        return data
    try:
        from merge_hub import merge as _merge_chat
        with open(chat_path, encoding="utf-8") as cf:
            chat = json.load(cf)
        data, added = _merge_chat(data, chat)
        print(f"chat_kb.json merged -- stocks +{added}")
    except ImportError as e:
        print(f"[WARN] merge_hub.py 없음 -- 채팅 병합 생략: {e}", file=sys.stderr)
        data.setdefault("build", {})["chat_merge_error"] = f"import: {e}"
    except Exception as e:
        import traceback
        print(f"[ERROR] chat_kb.json 병합 실패 -- 비병합 허브 생성됨: {e}", file=sys.stderr)
        traceback.print_exc()
        data.setdefault("build", {})["chat_merge_error"] = str(e)
    return data


def collect(src=".", files=None, json_out="knowledge_base.json"):
    """리포트 파싱→집계→시세→모멘텀→검색→chat 병합→knowledge_base.json 기록.
    무거운 단계 — parse/aggregate/momentum 를 지연 import 한다."""
    import json, sys
    from hublib.config import _fmt_kst
    from hublib.parse import discover, parse_report
    from hublib.aggregate import aggregate, build_search
    from hublib.momentum import fetch_index_series, enrich_market_momentum

    files = files if files else discover(src)
    if not files:
        sys.exit(f"리포트를 찾지 못했습니다 (src={src}). 파일명 규칙을 확인하세요.")
    print(f"발견한 리포트 {len(files)}개:")
    reports = []
    for p in files:
        try:
            rec = parse_report(p)
            rec["file"] = os.path.relpath(p, src).replace(os.sep, "/")  # 원문 링크용 상대경로
            reports.append(rec)
            print(f"  ✓ {rec['file']}")
        except Exception as e:
            print(f"  ✗ {os.path.basename(p)}  ({e})")
    reports.sort(key=lambda r: r["sort_date"])
    agg = aggregate(reports)
    idx_series = fetch_index_series(reports)      # 야후 정확 지수로 시계열 덮어쓰기
    if idx_series:
        agg["series"].update(idx_series)
    market_momentum_meta = enrich_market_momentum(agg, agg.get("series", {}))
    search = build_search(reports, agg)

    daily = [r for r in reports if r["type"] == "daily"]
    weekly = [r for r in reports if r["type"] == "weekly"]
    data = {
        "build": {"generated": _fmt_kst(), "timezone": "Asia/Seoul", "timezone_label": "한국시간(KST)",
                  "reports": len(reports), "daily": len(daily), "weekly": len(weekly),
                  "from": daily[0]["date"] if daily else (reports[0]["id"] if reports else ""),
                  "to": daily[-1]["date"] if daily else (reports[-1]["id"] if reports else ""),
                  "recent_from": agg.get("recent_from", ""), "recent_reports": agg.get("recent_reports", 0),
                  "index_source": "yfinance" if idx_series else "report",
                  "market_momentum": market_momentum_meta},
        # ai_digest 는 render 단계에서 주입 (ai_digest.py 가 knowledge_base.json 을 읽고 생성)
        "reports": reports, "search": search, "ai_digest": None, **agg,
    }
    data = _merge_chat_kb(data)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"\n→ {json_out} 작성 ({os.path.getsize(json_out)//1024} KB)")
    print(f"\n[요약] 종목 {len(agg['stocks'])}(최근 {agg.get('recent_reports','?')}개 리포트) · "
          f"섹터테마 {len(agg['sectors'])} · 스탠스 {len(agg['stance'])} · 원칙 {len(agg['principles'])} · "
          f"용어 {len(agg['glossary'])} · 검색항목 {len(search)} · 최근기준 {agg.get('recent_from','?')}~")
    return data


def render(json_in="knowledge_base.json", out="hub.html", template=None, index_path=None):
    """knowledge_base.json(+ai_digest.json) → kb.<hash>.json + hub 셸.
    파싱·네트워크 없음 — render 단계만 실행 시 bs4/yfinance 없이 동작한다."""
    import glob, hashlib, json, sys
    with open(json_in, encoding="utf-8") as f:
        data = json.load(f)

    # AI 위클리 다이제스트 반영 (ai_digest.py 산출물 — 없으면 무시) + knowledge_base.json 재기록
    try:
        if os.path.exists("ai_digest.json"):
            with open("ai_digest.json", encoding="utf-8") as f:
                data["ai_digest"] = json.load(f)
            print("ℹ️ ai_digest.json 반영")
            with open(json_in, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"ℹ️ ai_digest.json 읽기 실패 — 무시 ({e})")

    here = os.path.dirname(os.path.abspath(__file__))
    tpl = template or os.path.join(os.path.dirname(here), "hub_template.html")
    if os.path.exists(tpl):
        with open(tpl, encoding="utf-8") as f:
            shell = f.read()
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        kb_hash = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
        kb_name = f"kb.{kb_hash}.json"
        out_dir = os.path.dirname(os.path.abspath(out)) or "."
        # 이전 해시 파일 정리 후 새 파일 기록 (셸 캐시 무효화를 위해 파일명에 해시)
        for old in glob.glob(os.path.join(out_dir, "kb.*.json")):
            os.remove(old)
        with open(os.path.join(out_dir, kb_name), "w", encoding="utf-8") as f:
            f.write(payload)
        # /*KBURL*/ ... /*ENDKBURL*/ 사이를 새 해시 파일명으로 치환
        if "/*KBURL*/" in shell and "/*ENDKBURL*/" in shell:
            shell = re.sub(r"/\*KBURL\*/.*?/\*ENDKBURL\*/",
                           f'/*KBURL*/"{kb_name}"/*ENDKBURL*/', shell, count=1, flags=re.S)
        else:
            sys.exit("템플릿에 /*KBURL*/ … /*ENDKBURL*/ 마커가 없습니다.")
        with open(out, "w", encoding="utf-8") as f:
            f.write(shell)
        print(f"→ {out} 셸 빌드 완료 ({os.path.getsize(out)//1024} KB) "
              f"+ {kb_name} ({len(payload)//1024//1024}MB)")
    else:
        print(f"⚠ 템플릿 없음({tpl}) — JSON만 생성했습니다.")

    # 아카이브 index.html 에 허브 버튼 주입
    idx = index_path or os.path.join(os.path.dirname(out) or ".", "index.html")
    inject_hub_button(idx)
