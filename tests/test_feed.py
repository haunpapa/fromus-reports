# -*- coding: utf-8 -*-
"""JSON Feed 1.1 산출 (스펙 C5)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_build_feed_json_feed_1_1():
    from hublib.feed import build_feed
    data = {"build": {"to": "2026-08-22", "generated": "2026-08-22 07:30"},
            "reports": [{"id": "2026-08-22", "type": "daily", "date": "2026-08-22", "file": "reports/daily/a.html", "headline": "H", "subhead": "S"}],
            "stance": [{"id": "2026-08-22", "date": "2026-08-22", "headline": "H", "points": ["p1", "p2"]}],
            "whats_new": {"since": "2026-08-21", "new_stocks": [{"name": "신규주", "count": 2}], "surging": [], "new_calls": [], "new_targets": [], "new_reports": ["2026-08-22"]}}
    f = build_feed(data, base_url="https://example.org/hub/")
    assert f["version"] == "https://jsonfeed.org/version/1.1"
    assert f["feed_url"] == "https://example.org/hub/feed.json"
    ids = [i["id"] for i in f["items"]]
    assert "report:2026-08-22" in ids and "whatsnew:2026-08-22" in ids
    rep = next(i for i in f["items"] if i["id"] == "report:2026-08-22")
    assert rep["url"] == "https://example.org/hub/reports/daily/a.html" and "p1" in rep["content_text"]
    wn = next(i for i in f["items"] if i["id"] == "whatsnew:2026-08-22")
    assert "신규주" in wn["content_text"] and wn["url"].endswith("hub.html#home")


def test_build_feed_relative_without_base():
    from hublib.feed import build_feed
    f = build_feed({"build": {"to": "x"}, "reports": [], "stance": []}, base_url="")
    assert f["feed_url"] == "feed.json" and f["items"] == []
