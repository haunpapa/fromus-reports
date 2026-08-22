# -*- coding: utf-8 -*-
"""knowledge_base 최소 스키마 검증 (스펙 Q1)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ok():
    return {"build": {"schema": 2, "generated": "x", "to": "2026-08-22"}, "reports": [], "search": [],
            "stocks": [{"name": "A", "count": 1, "mentions": []}], "sectors": [{"theme": "T", "count": 1, "mentions": []}],
            "stance": [], "principles": [], "glossary": [], "events": [], "sentiment": [], "series": {}}


def test_validate_ok_returns_empty():
    from hublib.schema import validate
    assert validate(_ok()) == []


def test_validate_reports_missing_and_wrong_types():
    from hublib.schema import validate
    d = _ok(); d.pop("stocks"); d["sectors"] = "nope"; d["stocks_x"] = 1
    probs = validate(d)
    assert any("stocks" in p and "누락" in p for p in probs)
    assert any("sectors" in p and "list" in p for p in probs)


def test_validate_item_required_keys():
    from hublib.schema import validate
    d = _ok(); d["stocks"] = [{"count": 1}]
    assert any("stocks[0]" in p and "name" in p for p in validate(d))
