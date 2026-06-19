#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_hub 순수 로직 단위 테스트 (네트워크 불필요).
실행:  python build/test_merge_hub.py   또는   python -m unittest build.test_merge_hub"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from merge_hub import (  # noqa: E402
    _is_opinion, _name_in, _sort_desc, _build_comention_map, _augment, merge, _is_bot, _theme_blocks,
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


class TestBotExclusion(unittest.TestCase):
    def test_is_bot(self):
        self.assertTrue(_is_bot({"sharer": "김병철(봇)"}))
        self.assertFalse(_is_bot({"sharer": "탱이"}))
        self.assertFalse(_is_bot({}))

    def test_bot_excluded_from_block(self):
        chat = _full_chat()
        chat["stocks"]["구글"]["mentions"] += [
            {"date": "2026-05-01", "sharer": "김병철(봇)", "type": "view", "stance": "bullish", "snippet": "구글 의견"},
            {"date": "2026-05-02", "sharer": "김병철(봇)", "type": "research", "stance": "자료", "snippet": "구글 시황 복붙"},
        ]
        kb, _ = merge(_kb(), chat)
        g = next(s for s in kb["stocks"] if s["name"] == "구글")["chat"]
        sharers = [m["sharer"] for m in g["opinions"] + g["market_news"]]
        self.assertNotIn("김병철(봇)", sharers)  # 봇은 의견·시황 양쪽에서 제외


class TestThemeBlocks(unittest.TestCase):
    def _kb_with_chat(self):
        # 섹터 2개(반도체·기타), chat 종목 chat.opinions 보유
        return {
            "stocks": [
                {"name": "엔비디아", "chat": {"opinions": [
                    {"date": "2026-04-07", "sharer": "탱이", "stance": "bullish", "snippet": "엔비 좋다"},
                    {"date": "2026-04-02", "sharer": "탱이", "stance": "watch", "snippet": "관망"},
                ]}},
                {"name": "마이크론", "chat": {"opinions": [
                    {"date": "2026-04-08", "sharer": "문지영", "stance": "bullish", "snippet": "마이크론 강세"},
                ]}},
                {"name": "현대차", "chat": {"opinions": [
                    {"date": "2026-04-05", "sharer": "김철수", "stance": "bearish", "snippet": "현대차 약세"},
                ]}},
            ],
            "sectors": [{"theme": "반도체·메모리"}, {"theme": "자동차·현대차그룹"}],
        }

    def _chat_themes(self):
        return {
            "반도체·메모리": {"theme": "반도체·메모리", "count": 99, "stocks": ["엔비디아", "마이크론"], "mentions": []},
            "자동차·현대차그룹": {"theme": "자동차·현대차그룹", "count": 30, "stocks": ["현대차"], "mentions": []},
            "에너지·정유": {"theme": "에너지·정유", "count": 50, "stocks": ["엔비디아"], "mentions": []},  # 섹터에 없음(미집계)
        }

    def test_only_matched_themes(self):
        tb = _theme_blocks(self._kb_with_chat(), self._chat_themes())
        self.assertEqual(set(tb.keys()), {"반도체·메모리", "자동차·현대차그룹"})  # 에너지·정유 제외(섹터 없음)

    def test_stance_recount_and_count(self):
        tb = _theme_blocks(self._kb_with_chat(), self._chat_themes())
        semi = tb["반도체·메모리"]
        self.assertEqual(semi["opinions_count"], 3)                       # 엔비디아 2 + 마이크론 1
        self.assertEqual(semi["stance"], {"bullish": 2, "bearish": 0, "watch": 1})

    def test_opinions_have_stock_and_sorted(self):
        tb = _theme_blocks(self._kb_with_chat(), self._chat_themes())
        ops = tb["반도체·메모리"]["opinions"]
        self.assertTrue(all("stock" in o for o in ops))                   # stock 부착
        self.assertEqual([o["date"] for o in ops], ["2026-04-08", "2026-04-07", "2026-04-02"])  # 최신순

    def test_cap_applies_to_list_not_stance(self):
        kb = self._kb_with_chat()
        kb["stocks"][0]["chat"]["opinions"] = [
            {"date": f"2026-01-{i:02d}", "sharer": "x", "stance": "bullish", "snippet": "n"} for i in range(1, 13)
        ]  # 엔비디아 12개
        tb = _theme_blocks(kb, self._chat_themes())
        semi = tb["반도체·메모리"]
        self.assertLessEqual(len(semi["opinions"]), 8)                    # 대표 의견 ≤8
        self.assertEqual(semi["stance"]["bullish"], 12 + 1)               # stance는 상한 전 전체(엔비12+마이크론1)

    def test_stock_counted_independently_per_theme(self):
        # 실데이터: 한 종목이 여러 매칭 테마에 동시 소속(예: 마이크론 → 반도체 + 금융)
        kb = self._kb_with_chat()
        ct = self._chat_themes()
        ct["자동차·현대차그룹"]["stocks"] = ["현대차", "마이크론"]   # 마이크론을 두 테마에
        tb = _theme_blocks(kb, ct)
        semi_stocks = [o["stock"] for o in tb["반도체·메모리"]["opinions"]]
        auto_stocks = [o["stock"] for o in tb["자동차·현대차그룹"]["opinions"]]
        self.assertIn("마이크론", semi_stocks)
        self.assertIn("마이크론", auto_stocks)   # 두 테마에 독립 집계(공유·누적 아님)


if __name__ == "__main__":
    unittest.main()
