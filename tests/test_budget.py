# -*- coding: utf-8 -*-
"""kb 출력 크기 예산 — KB_BUDGET_CHECK=1 일 때만(렌더 직후 cwd 의 kb.*.json). 초과는 경고이지 실패가 아니다.
실패 조건은 '코어가 예산의 2배' 뿐 — 데이터가 자라도 첫 화면 전송을 지키기 위한 하드 게이트."""
import glob
import os
import re

import pytest

BUDGET_MB = {"core": 2.5, "chat": 3.5, "search": 5.0, "glossary": 1.0, "stockchat": 3.0}


@pytest.mark.skipif(os.environ.get("KB_BUDGET_CHECK") != "1", reason="KB_BUDGET_CHECK=1 일 때만")
def test_kb_chunks_within_budget():
    files = glob.glob("kb.*.json")
    assert files, "렌더 산출물 없음 — build_hub.py --phase render 먼저"
    lines, hard_fail = [], []
    for p in sorted(files):
        m = re.match(r"kb\.([a-z]+)\.[0-9a-f]+\.json$", os.path.basename(p))
        if not m:
            continue
        name, mb = m.group(1), os.path.getsize(p) / 1e6
        budget = BUDGET_MB.get(name)
        flag = "" if budget is None or mb <= budget else " ⚠ 예산 초과"
        lines.append(f"| {name} | {mb:.2f} MB | {budget or '-'} MB |{flag}")
        if name == "core" and mb > BUDGET_MB["core"] * 2:
            hard_fail.append(f"core {mb:.2f}MB > {BUDGET_MB['core']*2}MB")
    os.makedirs("build", exist_ok=True)
    with open("build/report.md", "a", encoding="utf-8") as f:
        f.write("\n### 크기 예산\n\n| 청크 | 실제 | 예산 |\n|---|---|---|\n" + "\n".join(lines) + "\n")
    assert not hard_fail, hard_fail
