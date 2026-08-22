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

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hub")


def concat_app_js(app_dir=APP_DIR):
    """hub/*.js 를 파일명 사전순으로 이어붙인다 — 파일명 숫자가 곧 실행 순서."""
    import glob
    files = sorted(glob.glob(os.path.join(app_dir, "*.js")))
    if not files:
        raise FileNotFoundError(f"앱 모듈 없음: {app_dir}/*.js")
    parts = []
    for p in files:
        with open(p, encoding="utf-8") as f:
            parts.append(f"/* ==== {os.path.basename(p)} ==== */\n" + f.read())
    return "\n".join(parts)


def inject_app_js(shell, app_js):
    """/*APPJS*/ … /*ENDAPPJS*/ 사이에 앱 코드를 넣는다. 치환 함수를 써서 JS 의 백슬래시·$1 이 re 에 해석되지 않게 한다."""
    if "/*APPJS*/" not in shell or "/*ENDAPPJS*/" not in shell:
        raise ValueError("템플릿에 /*APPJS*/ … /*ENDAPPJS*/ 마커가 없습니다.")
    return re.sub(r"/\*APPJS\*/.*?/\*ENDAPPJS\*/",
                  lambda _m: "/*APPJS*/\n" + app_js + "\n/*ENDAPPJS*/", shell, count=1, flags=re.S)


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
        from hublib.search import build_chat_search
        chat_items = build_chat_search(chat)
        data = {**data, "search": (data.get("search") or []) + chat_items}
        print(f"chat_kb.json merged -- stocks +{added} · 검색항목 +{len(chat_items)}")
    except ImportError as e:
        print(f"[WARN] merge_hub.py 없음 -- 채팅 병합 생략: {e}", file=sys.stderr)
        data.setdefault("build", {})["chat_merge_error"] = f"import: {e}"
    except Exception as e:
        import traceback
        print(f"[ERROR] chat_kb.json 병합 실패 -- 비병합 허브 생성됨: {e}", file=sys.stderr)
        traceback.print_exc()
        data.setdefault("build", {})["chat_merge_error"] = str(e)
    return data


def _build_verify_safe(data):
    """chat_kb.json 원본으로 검증 레이어를 만든다. 실패해도 빌드는 계속된다.

    _merge_chat_kb 와 달리 **cwd 만 본다**(리포 루트 폴백 없음). 검증은 네트워크를
    타므로, tmp 폴더에서 도는 tests/test_phases.py 가 리포 루트의 실제 chat_kb.json 을
    집어 시세를 받아버리면 안 된다. CI 는 리포 루트에서 실행하므로 cwd 만으로 충분하다.
    """
    import json, sys
    if os.environ.get("VERIFY_SKIP") in ("1", "true", "TRUE", "yes"):
        print("ℹ️ VERIFY_SKIP -- 검증 레이어 생략")
        return None
    if not os.path.exists("chat_kb.json"):
        return None
    try:
        from hublib.verify import build_verify
        with open("chat_kb.json", encoding="utf-8") as f:
            chat = json.load(f)
        out = build_verify(chat_kb=chat)
        if out and out.get("enabled"):
            m = out["meta"]
            print(f"검증 레이어 -- {m['calls']}콜 / {m['stocks']}종목")
        elif out:
            print(f"ℹ️ 검증 레이어 비활성 -- {out.get('reason')}")
        return out
    except Exception as e:
        print(f"[WARN] 검증 레이어 생략 -- {e}", file=sys.stderr)
        data.setdefault("build", {})["verify_error"] = str(e)
        return None


def _build_whats_new_safe(data):
    """전일 요약 대비 diff. 첫 빌드·실패는 None — 빌드는 계속된다."""
    import sys
    try:
        from hublib.whatsnew import diff, load_summary, save_summary, summarize, SUMMARY_PATH
        prev = load_summary(SUMMARY_PATH)
        cur = summarize(data)
        out = diff(prev, data)
        if out is None and prev and prev.get("to") == cur["to"]:
            out = prev.get("last_diff")            # 같은 날 재빌드(푸시 트리거) — 그날 아침의 diff 를 그대로 유지
        if prev is None or prev.get("to") != cur["to"]:
            save_summary(SUMMARY_PATH, {**cur, "last_diff": out})   # 기준일이 바뀔 때만 요약(+그날의 diff) 갱신
        print("what's new --", "없음(첫 빌드/동일 기준일)" if out is None else
              f"신규 {len(out['new_stocks'])} · 급증 {len(out['surging'])} · "
              f"콜 {len(out['new_calls'])} · 목표가 {len(out['new_targets'])}")
        return out
    except Exception as e:
        print(f"[WARN] what's new 생략 -- {e}", file=sys.stderr)
        data.setdefault("build", {})["whats_new_error"] = str(e)
        return None


def _validate_schema_safe(data):
    """최소 스키마 검증. 검증기 자체가 터지면 빈 목록 — 검증 때문에 빌드가 멈춰선 안 된다."""
    import sys
    try:
        from hublib.schema import validate
        return validate(data)
    except Exception as e:
        print(f"[WARN] 스키마 검증 생략 -- {e}", file=sys.stderr)
        data.setdefault("build", {})["schema_error"] = str(e)
        return []


def collect(src=".", files=None, json_out="knowledge_base.json"):
    """리포트 파싱→집계→시세→모멘텀→검색→chat 병합→knowledge_base.json 기록.
    무거운 단계 — parse/aggregate/momentum 를 지연 import 한다."""
    import json, sys
    from hublib.config import _fmt_kst, STOCK_ALIASES
    from hublib.parse import discover, parse_report
    from hublib.aggregate import aggregate, build_search
    from hublib.search import with_hay
    from hublib.momentum import fetch_index_series, enrich_market_momentum
    from hublib.cache import ParseCache

    files = files if files else discover(src)
    if not files:
        sys.exit(f"리포트를 찾지 못했습니다 (src={src}). 파일명 규칙을 확인하세요.")
    print(f"발견한 리포트 {len(files)}개:")
    cache = ParseCache()               # 파일 sha1 기준 증분 캐시 — 바뀐 리포트만 재파싱
    reports = []
    for p in files:
        try:
            rec = cache.get_or_parse(p, parse_report)   # 사본 반환 — 캐시 오염 없음
            rec["file"] = os.path.relpath(p, src).replace(os.sep, "/")  # 원문 링크용 상대경로
            reports.append(rec)
            print(f"  ✓ {rec['file']}")
        except Exception as e:
            print(f"  ✗ {os.path.basename(p)}  ({e})")
    cache.save()
    reports.sort(key=lambda r: r["sort_date"])
    agg = aggregate(reports)
    idx_series = fetch_index_series(reports)      # 야후 정확 지수로 시계열 덮어쓰기
    if idx_series:
        agg["series"].update(idx_series)
    market_momentum_meta = enrich_market_momentum(agg, agg.get("series", {}))
    search = with_hay(build_search(reports, agg))

    daily = [r for r in reports if r["type"] == "daily"]
    weekly = [r for r in reports if r["type"] == "weekly"]
    data = {
        "build": {"schema": 2, "generated": _fmt_kst(), "timezone": "Asia/Seoul", "timezone_label": "한국시간(KST)",
                  "reports": len(reports), "daily": len(daily), "weekly": len(weekly),
                  "from": daily[0]["date"] if daily else (reports[0]["id"] if reports else ""),
                  "to": daily[-1]["date"] if daily else (reports[-1]["id"] if reports else ""),
                  "recent_from": agg.get("recent_from", ""), "recent_reports": agg.get("recent_reports", 0),
                  "index_source": "yfinance" if idx_series else "report",
                  "market_momentum": market_momentum_meta,
                  "aliases": {k.lower(): v for k, v in STOCK_ALIASES.items()}},
        # ai_digest 는 render 단계에서 주입 (ai_digest.py 가 knowledge_base.json 을 읽고 생성)
        "reports": reports, "search": search, "ai_digest": None, **agg,
    }
    data = _merge_chat_kb(data)
    data["verify"] = _build_verify_safe(data)
    data["whats_new"] = _build_whats_new_safe(data)

    problems = _validate_schema_safe(data)
    if problems:
        print(f"[WARN] 스키마 문제 {len(problems)}건: " + " | ".join(problems[:10]), file=sys.stderr)
        data = {**data, "build": {**(data.get("build") or {}), "schema_warnings": problems[:50]}}
        if any("누락" in p and "[" not in p for p in problems):     # 최상위 키 누락만 빌드 실패
            sys.exit("knowledge_base 최상위 키 누락 — 빌드 중단")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"\n→ {json_out} 작성 ({os.path.getsize(json_out)//1024} KB)")
    print(f"\n[요약] 종목 {len(agg['stocks'])}(최근 {agg.get('recent_reports','?')}개 리포트) · "
          f"섹터테마 {len(agg['sectors'])} · 스탠스 {len(agg['stance'])} · 원칙 {len(agg['principles'])} · "
          f"용어 {len(agg['glossary'])} · 검색항목 {len(search)} · 최근기준 {agg.get('recent_from','?')}~")
    return data


def _emit_json(out_dir, name, obj):
    """kb.<name>.<hash>.json 기록 → (파일명, 바이트 수). 해시는 청크 자신의 내용 — 안 바뀐 청크는 파일명이 유지된다."""
    import hashlib, json
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    h = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    fname = f"kb.{name}.{h}.json"
    with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
        f.write(payload)
    return fname, len(payload.encode("utf-8"))


def _write_size_report(sizes, path="build/report.md"):
    """섹션별 바이트를 Markdown 표로 — CI Job Summary 에 붙인다 (Q1)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = "\n".join(f"| {k} | {v/1e6:.2f} MB |" for k, v in sizes.items())
    total = sum(sizes.values())
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"### kb 출력 크기\n\n| 파일 | raw |\n|---|---|\n{rows}\n| **합계** | **{total/1e6:.2f} MB** |\n")


def render(json_in="knowledge_base.json", out="hub.html", template=None, index_path=None):
    """knowledge_base.json(+ai_digest.json) → kb.core.<h>.json + 청크 + hub 셸 + version.json.
    파싱·네트워크 없음 — render 단계만 실행 시 bs4/yfinance 없이 동작한다."""
    import glob, json, sys
    from hublib.split import split_payload
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
    out_dir = os.path.dirname(os.path.abspath(out)) or "."
    for old in glob.glob(os.path.join(out_dir, "kb.*.json")):   # 구 해시(구 형식 kb.<h>.json 포함) 정리
        os.remove(old)

    core, chunks = split_payload(data)
    manifest, sizes = {}, {}
    manifest["core"], sizes["core"] = _emit_json(out_dir, "core", core)
    for name, obj in chunks.items():
        if obj:                                                   # 빈 청크(chat 없음 등)는 파일·매니페스트에서 생략
            manifest[name], sizes[name] = _emit_json(out_dir, name, obj)

    with open(os.path.join(out_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"core": manifest["core"], "generated": (data.get("build") or {}).get("generated", "")},
                  f, ensure_ascii=False)

    from hublib.feed import build_feed
    with open(os.path.join(out_dir, "feed.json"), "w", encoding="utf-8") as f:
        json.dump(build_feed(data, os.environ.get("SITE_BASE_URL", "")), f, ensure_ascii=False, indent=1)

    _write_size_report(sizes)
    if os.path.exists(tpl):                                        # 템플릿이 없어도 kb.*·version.json 은 이미 만들어졌다
        with open(tpl, encoding="utf-8") as f:
            shell = f.read()
        shell = inject_app_js(shell, concat_app_js())
        if "/*KBURL*/" not in shell or "/*ENDKBURL*/" not in shell:
            sys.exit("템플릿에 /*KBURL*/ … /*ENDKBURL*/ 마커가 없습니다.")
        shell = re.sub(r"/\*KBURL\*/.*?/\*ENDKBURL\*/",
                       lambda _m: "/*KBURL*/" + json.dumps(manifest, ensure_ascii=False) + "/*ENDKBURL*/",
                       shell, count=1, flags=re.S)
        with open(out, "w", encoding="utf-8") as f:
            f.write(shell)
        print(f"→ {out} 셸 빌드 완료 ({os.path.getsize(out)//1024} KB) + " +
              " · ".join(f"{n} {b/1e6:.2f}MB" for n, b in sizes.items()))
    else:
        print(f"⚠ 템플릿 없음({tpl}) — kb.*.json 만 생성했습니다.")

    idx = index_path or os.path.join(os.path.dirname(out) or ".", "index.html")
    inject_hub_button(idx)
