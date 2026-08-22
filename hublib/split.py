# -*- coding: utf-8 -*-
"""render 단계의 kb 분할·슬림화 — 순수 함수만. knowledge_base.json 은 건드리지 않고 출력(kb.*)만 줄인다.

계약: docs/superpowers/specs/2026-08-23-hub-improvement-design.md §3.3 C2
"""

# 셸(hub/*.js)이 D.reports 에서 읽는 필드 전부 — FILE 맵·캘린더·커맨드팔레트·원문 모달 제목
REPORT_FIELDS = ("type", "date", "id", "sort_date", "file", "headline", "subhead")


def slim_reports(reports):
    """리포트 레코드를 셸이 쓰는 필드로만 투영한다. 원문은 reports/**/*.html 링크로 남아 있다."""
    return [{k: r[k] for k in REPORT_FIELDS if k in r} for r in (reports or [])]
