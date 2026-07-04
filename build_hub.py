#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""프롬어스 Knowledge Hub 빌더 — CLI. 로직은 hublib/ 패키지에 있다.

  --phase collect : 파싱·집계·시세·모멘텀·검색 → knowledge_base.json (무거움)
  --phase render  : knowledge_base.json(+ai_digest.json) → kb.<hash>.json + hub 셸 (가벼움)
  --phase all     : collect → render (기본값 · 기존 호출과 호환)

render 만 실행할 때는 bs4/yfinance 가 없어도 동작한다 (collect 가 지연 import 하므로).
"""
import argparse
from hublib.render import collect, render


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["collect", "render", "all"], default="all",
                    help="collect(무거움)/render(가벼움)/all(기본)")
    ap.add_argument("--src", default=".", help="리포트 탐색 루트 폴더")
    ap.add_argument("--files", nargs="*", help="명시적 파일 목록(선택)")
    ap.add_argument("--out", default="hub.html", help="허브 출력 파일")
    ap.add_argument("--json", default="knowledge_base.json", help="구조화 데이터 출력/입력")
    ap.add_argument("--template", default=None, help="허브 템플릿 경로(기본: 리포 루트 hub_template.html)")
    ap.add_argument("--index", default=None, help="아카이브 index.html 경로(허브 버튼 주입 대상)")
    args = ap.parse_args()

    if args.phase in ("collect", "all"):
        collect(src=args.src, files=args.files, json_out=args.json)
    if args.phase in ("render", "all"):
        render(json_in=args.json, out=args.out, template=args.template, index_path=args.index)


if __name__ == "__main__":
    main()
