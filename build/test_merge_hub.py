#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_hub 순수 로직 단위 테스트 (네트워크 불필요).
실행:  python build/test_merge_hub.py   또는   python -m unittest build.test_merge_hub"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from merge_hub import (  # noqa: E402
    _is_opinion, _name_in, _sort_desc, _build_comention_map, _augment,
)

DAILY = {"date": "2026-04-01", "sharer": "김병철", "type": "research",
         "stance": "자료", "snippet": "특징종목: 엔비디아 상승, 구글 약보합"}

def _chat_fixture():
    return {
        "구글":   {"ticker": "GOOGL", "mentions": [dict(DAILY)]},
        "엔비디아": {"ticker": "NVDA",  "mentions": [dict(DAILY)]},
    }


class TestHelpers(unittest.TestCase):
    def test_is_opinion(self):
        self.assertTrue(_is_opinion({"type": "view"}))
        self.assertTrue(_is_opinion({"type": "position"}))
        self.assertFalse(_is_opinion({"type": "research"}))
        self.assertFalse(_is_opinion({}))

    def test_name_in_matches_name_or_ticker(self):
        m = {"snippet": "엔비디아 +5%, 구글 약보합"}
        self.assertTrue(_name_in(m, "구글", "GOOGL"))
        self.assertTrue(_name_in({"snippet": "GOOGL 목표 300"}, "구글", "GOOGL"))
        self.assertFalse(_name_in({"snippet": "반도체 일반 시황"}, "구글", "GOOGL"))
        self.assertFalse(_name_in({"snippet": None}, "구글", "GOOGL"))

    def test_sort_desc_by_date_safe(self):
        items = [{"date": "2026-04-02"}, {"date": "2026-04-07"}, {}]
        out = _sort_desc(items)
        self.assertEqual([i.get("date", "") for i in out], ["2026-04-07", "2026-04-02", ""])


class TestCoStocks(unittest.TestCase):
    def test_comention_map_groups_same_message(self):
        comap = _build_comention_map(_chat_fixture())
        key = (DAILY["date"], DAILY["sharer"], DAILY["snippet"][:40])
        self.assertEqual(comap[key], {"구글", "엔비디아"})

    def test_augment_adds_others_excludes_self(self):
        comap = _build_comention_map(_chat_fixture())
        aug = _augment(dict(DAILY), "구글", comap)
        self.assertEqual(aug["co_stocks"], ["엔비디아"])     # 자기 자신 제외
        self.assertNotIn("구글", aug["co_stocks"])

    def test_augment_is_immutable(self):
        m = dict(DAILY)
        comap = _build_comention_map(_chat_fixture())
        _augment(m, "구글", comap)
        self.assertNotIn("co_stocks", m)                    # 원본 미오염


if __name__ == "__main__":
    unittest.main()
