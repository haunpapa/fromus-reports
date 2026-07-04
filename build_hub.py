#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""프롬어스 Knowledge Hub 빌더 — CLI. 로직은 hublib/ 패키지에 있다."""
import argparse, glob, hashlib, json, os, re, sys
from hublib.config import _fmt_kst
from hublib.parse import discover, parse_report
from hublib.aggregate import aggregate, build_search
from hublib.momentum import enrich_market_momentum, fetch_index_series
from hublib.render import inject_hub_button

# 하위호환 re-export (tests/ 등에서 from build_hub import parse_report 사용)
__all__ = ['main', 'parse_report', 'aggregate', 'build_search', 'discover',
           'inject_hub_button', 'fetch_index_series', 'enrich_market_momentum']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".", help="리포트 탐색 루트 폴더")
    ap.add_argument("--files", nargs="*", help="명시적 파일 목록(선택)")
    ap.add_argument("--out", default="hub.html", help="허브 출력 파일")
    ap.add_argument("--json", default="knowledge_base.json", help="구조화 데이터 출력")
    ap.add_argument("--template", default=None, help="허브 템플릿 경로(기본: 스크립트 옆 hub_template.html)")
    ap.add_argument("--index", default=None, help="아카이브 index.html 경로(허브 버튼 주입 대상)")
    args = ap.parse_args()

    files = args.files if args.files else discover(args.src)
    if not files:
        sys.exit(f"리포트를 찾지 못했습니다 (src={args.src}). 파일명 규칙을 확인하세요.")
    print(f"발견한 리포트 {len(files)}개:")
    reports = []
    for p in files:
        try:
            rec = parse_report(p)
            rec["file"] = os.path.relpath(p, args.src).replace(os.sep, "/")  # 원문 링크용 상대경로
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

    # AI 위클리 다이제스트 (ai_digest.py 산출물 — 없으면 무시)
    ai_digest = None
    try:
        if os.path.exists("ai_digest.json"):
            with open("ai_digest.json", encoding="utf-8") as f:
                ai_digest = json.load(f)
            print("ℹ️ ai_digest.json 반영")
    except Exception as e:
        print(f"ℹ️ ai_digest.json 읽기 실패 — 무시 ({e})")

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
        "reports": reports, "search": search, "ai_digest": ai_digest, **agg,
    }

    # -- 채팅 온톨로지 병합 (chat_kb.json 있으면 자동) --
    _here = os.path.dirname(os.path.abspath(__file__))
    _chat_path = next((p for p in ("chat_kb.json", os.path.join(_here, "chat_kb.json"))
                       if os.path.exists(p)), None)
    if _chat_path:
        try:
            from merge_hub import merge as _merge_chat
            with open(_chat_path, encoding="utf-8") as _cf:
                _chat = json.load(_cf)
            data, _added = _merge_chat(data, _chat)
            print(f"chat_kb.json merged -- stocks +{_added}")
        except ImportError as _e:
            print(f"[WARN] merge_hub.py 없음 -- 채팅 병합 생략: {_e}", file=sys.stderr)
            data.setdefault("build", {})["chat_merge_error"] = f"import: {_e}"
        except Exception as _e:
            import traceback as _tb
            print(f"[ERROR] chat_kb.json 병합 실패 -- 비병합 허브 생성됨: {_e}", file=sys.stderr)
            _tb.print_exc()
            data.setdefault("build", {})["chat_merge_error"] = str(_e)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"\n→ {args.json} 작성 ({os.path.getsize(args.json)//1024} KB)")

    tpl = args.template or os.path.join(os.path.dirname(os.path.abspath(__file__)), "hub_template.html")
    if os.path.exists(tpl):
        with open(tpl, encoding="utf-8") as f:
            shell = f.read()
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        kb_hash = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
        kb_name = f"kb.{kb_hash}.json"
        out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
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
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(shell)
        print(f"→ {args.out} 셸 빌드 완료 ({os.path.getsize(args.out)//1024} KB) "
              f"+ {kb_name} ({len(payload)//1024//1024}MB)")
    else:
        print(f"⚠ 템플릿 없음({tpl}) — JSON만 생성했습니다.")

    # 아카이브 index.html 에 허브 버튼 주입
    index_path = args.index or os.path.join(os.path.dirname(args.out) or ".", "index.html")
    inject_hub_button(index_path)

    # 요약
    print(f"\n[요약] 종목 {len(agg['stocks'])}(최근 {agg.get('recent_reports','?')}개 리포트) · "
          f"섹터테마 {len(agg['sectors'])} · 스탠스 {len(agg['stance'])} · 원칙 {len(agg['principles'])} · "
          f"용어 {len(agg['glossary'])} · 검색항목 {len(search)} · 최근기준 {agg.get('recent_from','?')}~")


if __name__ == "__main__":
    main()
