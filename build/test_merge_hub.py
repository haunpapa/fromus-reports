#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_hub 순수 로직 단위 테스트 (네트워크 불필요).
실행:  python build/test_merge_hub.py   또는   python -m unittest build.test_merge_hub"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from merge_hub import (  # noqa: E402
    _is_opinion, _name_in, _sort_desc, _build_comention_map, _augment, merge,
)
import json

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


def _full_chat():
    return {
        "build": {}, "themes": {}, "glossary": [], "readings": [],
        "actions": [], "strategy": [], "targets": [], "qna": [], "news": [],
        "stocks": {
            "구글": {"count": 3, "ticker": "GOOGL", "market": "US", "themes": [], "targets": [],
                "mentions": [
                    {"date": "2026-04-07", "sharer": "탱이", "type": "view", "stance": "watch", "snippet": "구글 300불 회복"},
                    {"date": "2026-04-02", "sharer": "탱이", "type": "view", "stance": "bullish", "snippet": "AI 인프라가 핵심"},
                    dict(DAILY),  # research + 구글 포함 → market_news
                ],
                "news": [
                    {"date": "2026-04-05", "title": "구글 TPU", "outlet": "한경", "url": "http://x"},
                    {"date": "2026-04-08", "title": "브로드컴 계약", "outlet": "매경", "url": "http://y"},
                ]},
            "엔비디아": {"count": 2, "ticker": "NVDA", "market": "US", "themes": [], "targets": [],
                "mentions": [
                    dict(DAILY),  # 구글과 동일 메시지 → co_stocks
                    {"date": "2026-03-20", "sharer": "X", "type": "research", "stance": "자료", "snippet": "반도체 일반 시황"},  # 엔비디아 미포함 → 제외
                ],
                "news": []},
        },
    }

def _kb():
    return {"build": {}, "stocks": [{"name": "구글", "count": 5, "mentions": []}], "glossary": []}


class TestChatBlock(unittest.TestCase):
    def test_classification_and_sort(self):
        kb, _ = merge(_kb(), _full_chat())
        g = next(s for s in kb["stocks"] if s["name"] == "구글")["chat"]
        self.assertEqual([o["date"] for o in g["opinions"]], ["2026-04-07", "2026-04-02"])  # view 2개, 최신순
        self.assertEqual(len(g["market_news"]), 1)                                          # research+구글포함 1개
        self.assertEqual([n["date"] for n in g["news"]], ["2026-04-08", "2026-04-05"])      # 뉴스 최신순

    def test_market_news_excludes_unrelated_research(self):
        kb, _ = merge(_kb(), _full_chat())  # 엔비디아는 chat_only로 추가됨
        nv = next(s for s in kb["stocks"] if s["name"] == "엔비디아")["chat"]
        self.assertEqual(len(nv["market_news"]), 1)  # DAILY만, "반도체 일반 시황"은 제외

    def test_co_stocks_in_block(self):
        kb, _ = merge(_kb(), _full_chat())
        g = next(s for s in kb["stocks"] if s["name"] == "구글")["chat"]
        self.assertEqual(g["market_news"][0]["co_stocks"], ["엔비디아"])

    def test_idempotent(self):
        kb = _kb()
        merge(kb, _full_chat())
        snap = json.dumps(kb, sort_keys=True, ensure_ascii=False)
        merge(kb, _full_chat())  # 2회차
        self.assertEqual(json.dumps(kb, sort_keys=True, ensure_ascii=False), snap)

    def test_input_chat_unchanged(self):
        chat = _full_chat()
        before = json.dumps(chat, sort_keys=True, ensure_ascii=False)
        merge(_kb(), chat)
        self.assertEqual(json.dumps(chat, sort_keys=True, ensure_ascii=False), before)

    def test_caps(self):
        chat = _full_chat()
        chat["stocks"]["구글"]["mentions"] = [
            {"date": "2026-01-01", "type": "view", "stance": "bullish", "snippet": "x"} for _ in range(105)
        ]
        kb, _ = merge(_kb(), chat)
        g = next(s for s in kb["stocks"] if s["name"] == "구글")["chat"]
        self.assertEqual(len(g["opinions"]), 100)   # 105개 입력 → OPINION_KEEP=100 으로 잘림(상한 실검증)


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
