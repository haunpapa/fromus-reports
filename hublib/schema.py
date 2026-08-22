# -*- coding: utf-8 -*-
"""knowledge_base.json 최소 스키마(v2) — 셸이 빈 화면으로 조용히 죽는 키 누락을 빌드에서 잡는다.
키 추가는 자유(마이너), 여기 적힌 키의 누락·타입 변경만 문제로 본다."""

TOP = {"build": dict, "reports": list, "search": list, "stocks": list, "sectors": list, "stance": list,
       "principles": list, "glossary": list, "events": list, "sentiment": list, "series": dict}
ITEM_KEYS = {"stocks": ("name", "count", "mentions"), "sectors": ("theme", "count", "mentions"),
             "search": ("kind", "title", "snippet"), "reports": ("id", "type", "file")}
BUILD_KEYS = ("schema", "generated", "to")
ITEM_SCAN_MAX = 2000        # 앞쪽 표본만 본다 — 전량 스캔은 빌드 시간만 먹고 새로 잡는 게 없다


def validate(data):
    """문제 목록(문자열). 비어 있으면 통과."""
    probs = []
    for k, t in TOP.items():
        if k not in data:
            probs.append(f"{k}: 누락")
            continue
        if not isinstance(data[k], t):
            probs.append(f"{k}: {t.__name__} 여야 함 ({type(data[k]).__name__})")
    for k in BUILD_KEYS:
        if isinstance(data.get("build"), dict) and k not in data["build"]:
            probs.append(f"build.{k}: 누락")
    for k, keys in ITEM_KEYS.items():
        arr = data.get(k)
        if not isinstance(arr, list):
            continue
        for i, it in enumerate(arr[:ITEM_SCAN_MAX]):
            for kk in keys:
                if not isinstance(it, dict) or kk not in it:
                    probs.append(f"{k}[{i}]: {kk} 누락")
                    break
    return probs
