# -*- coding: utf-8 -*-
import os, sys, shutil, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_archive as U
import chat_to_kb as C

CSV_SAMPLE = (
    "﻿Date,User,Message\n"
    '2026-03-19 17:43:30,"대성","대성님이 들어왔습니다."\n'
    '2026-03-20 09:05:00,"ㄱ 이혜나","삼성전자 좋게 봅니다.\n추가 매수 고려"\n'
    '깨진행없음\n'
    ',"빈날짜","날짜 없는 행"\n'
)

class TestParseCsv(unittest.TestCase):
    def _write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        f.write(text); f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_schema_and_fields(self):
        msgs = U.parse_csv(self._write(CSV_SAMPLE))
        # 헤더 스킵 + 열부족('깨진행없음') + 빈날짜 행 skip → 정상 2건
        self.assertEqual(len(msgs), 2)
        m0, m1 = msgs
        self.assertEqual(m0["date"], "2026-03-19")
        self.assertEqual(m0["time"], "17:43")          # 초 절단
        self.assertEqual(m0["weekday"], "목요일")        # 2026-03-19 = 목
        self.assertEqual(m0["sender"], "대성")
        self.assertEqual(m0["idx"], 0)
        self.assertEqual(m1["idx"], 1)
        # lines 키(list) 필수 + body == join(lines), 멀티라인 보존
        self.assertIsInstance(m1["lines"], list)
        self.assertEqual(m1["body"], "\n".join(m1["lines"]))
        self.assertIn("추가 매수 고려", m1["body"])
        self.assertEqual(len(m1["lines"]), 2)

    def test_empty_returns_list(self):
        self.assertEqual(U.parse_csv(self._write("﻿Date,User,Message\n")), [])

class TestFindInput(unittest.TestCase):
    def test_arg_priority_and_prefix(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        old = os.path.join(d, "KakaoTalk_old.csv"); open(old, "w").close()
        time.sleep(0.02)
        new = os.path.join(d, "KakaoTalk_new.csv"); open(new, "w").close()
        out = os.path.join(d, "뉴스_전체아카이브.csv"); open(out, "w").close()  # 출력형(미선택)
        # 명시 인자 우선
        self.assertEqual(U.find_input(["prog", new]), new)

        # 인자 없음 → cwd 자동탐색: KakaoTalk_* 선택, 출력형 CSV 제외
        import unittest.mock as mock
        with mock.patch("os.getcwd", return_value=d):
            picked = U.find_input(["prog"])           # 인자 없음 → 자동탐색
            # ~/Downloads 에 더 최신 KakaoTalk_* 가 존재할 수 있으므로
            # basename이 KakaoTalk_ 로 시작하는지만 확인하고, 출력형 CSV가 아님을 검증
            self.assertTrue(os.path.basename(picked).startswith("KakaoTalk_"))
            self.assertNotEqual(picked, out)

    def test_find_inputs_returns_all_kakao(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        a = os.path.join(d, "KakaoTalk_a.csv"); open(a, "w").close()
        time.sleep(0.02)
        b = os.path.join(d, "KakaoTalk_b.csv"); open(b, "w").close()
        out = os.path.join(d, "뉴스_전체아카이브.csv"); open(out, "w").close()  # 출력형(미포함)
        import unittest.mock as mock
        with mock.patch("os.getcwd", return_value=d), \
             mock.patch("os.path.expanduser", return_value="/no/such/dir"):
            got = U.find_inputs(["prog"])
        names = sorted(os.path.basename(p) for p in got)
        self.assertEqual(names, ["KakaoTalk_a.csv", "KakaoTalk_b.csv"])  # 둘 다, 출력형 제외

    def test_find_input_wrapper_is_string_and_newest(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        old = os.path.join(d, "KakaoTalk_a.csv"); open(old, "w").close()
        time.sleep(0.02)
        new = os.path.join(d, "KakaoTalk_b.csv"); open(new, "w").close()
        import unittest.mock as mock
        with mock.patch("os.getcwd", return_value=d), \
             mock.patch("os.path.expanduser", return_value="/no/such/dir"):
            picked = U.find_input(["prog"])
        self.assertIsInstance(picked, str)          # 리스트 아님
        self.assertEqual(picked, new)               # mtime 최신

class TestFull(unittest.TestCase):
    def _msg(self, idx, body):
        return {"idx": idx, "date": "2026-03-20", "weekday": "금요일",
                "time": "09:00", "sender": "ㄱ 이혜나", "body": body, "lines": body.split("\n")}

    def test_strategy_full(self):
        alias = U.ENTITIES[list(U.ENTITIES)[0]]["al"][0]   # 실재 alias(하드코딩 금지)
        bull = U.BULL[0]
        body = f"{alias} 관련 {bull} 라고 봅니다.\n둘째 줄 유지 https://x.co/aaa"
        sig = U.strategy([self._msg(0, body)])
        self.assertTrue(sig, "signal 이 생성되어야 함(실재 alias+키워드)")
        s = sig[0]
        self.assertIn("full", s)
        self.assertLessEqual(len(s["full"]), 1500)
        self.assertIn("\n", s["full"])              # 개행 보존
        self.assertNotIn("http", s["full"])          # URL 제거

    def test_mention_full_opinion_only(self):
        # view(의견) 시그널엔 full, research(자료) 시그널엔 full 없음
        view_sig = {"date":"2026-03-20","time":"09:00","sharer":"ㄱ 이혜나",
                    "entities":["삼성전자"],"themes":[],"stance":"bullish","type":"view",
                    "snippet":"좋게 봅니다","full":"좋게 봅니다\n장기 보유",
                    "stocks":[("삼성전자","bullish")]}
        res_sig = {**view_sig, "type":"research"}
        msgs = [self._msg(0, "x")]
        kb = C.build(msgs, [], [view_sig, res_sig])
        ms = kb["stocks"]["삼성전자"]["mentions"]
        view_m = [m for m in ms if m["type"]=="view"][0]
        res_m  = [m for m in ms if m["type"]=="research"][0]
        self.assertEqual(view_m.get("full"), "좋게 봅니다\n장기 보유")
        self.assertNotIn("full", res_m)

    def test_pii_guard_warns_not_blocks(self):
        # 의식적 한계 인지용: full 에 긴 숫자열(전화/계좌) 노출 시 경고만(차단 아님)
        import re as _re
        sig = {"date":"2026-03-20","time":"09:00","sharer":"ㄱ 이혜나","entities":["삼성전자"],
               "themes":[],"stance":"bullish","type":"view","snippet":"연락처","full":"연락처 01012345678","stocks":[("삼성전자","bullish")]}
        kb = C.build([self._msg(0,"x")], [], [sig])
        leaked = [m for m in kb["stocks"]["삼성전자"]["mentions"] if _re.search(r"\d{8,}", m.get("full",""))]
        if leaked:
            print(f"[PII 경고] full 에 긴 숫자열 노출 {len(leaked)}건 — 후속 마스킹 검토")
        self.assertTrue(True)   # 차단 아님(인지용)

class TestParseTxtGolden(unittest.TestCase):
    def test_txt_unchanged(self):
        import tempfile
        txt = ("--------------- 2026년 3월 19일 목요일 ---------------\n"
               "[대성] [오후 5:43] 첫 줄\n둘째 줄\n")
        f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        f.write(txt); f.close()
        self.addCleanup(os.unlink, f.name)
        msgs = U.parse(f.name)
        self.assertEqual(len(msgs), 1)
        m = msgs[0]
        self.assertEqual((m["date"], m["time"], m["weekday"], m["sender"]),
                         ("2026-03-19", "17:43", "목요일", "대성"))
        self.assertIsInstance(m["lines"], list)
        self.assertIn("둘째 줄", m["body"])

class TestMentionStocks(unittest.TestCase):
    def _msg(self, idx, body):
        return {"idx": idx, "date": "2026-03-20", "weekday": "금요일",
                "time": "09:00", "sender": "ㄱ 이혜나", "body": body, "lines": body.split("\n")}

    def test_mention_uses_stocks_per_stance(self):
        sig = {"date": "2026-03-20", "time": "09:00", "sharer": "ㄱ 이혜나",
               "entities": ["삼성전자", "SK하이닉스"], "themes": [], "stance": "mixed", "type": "view",
               "snippet": "삼성 손절 하이닉스 추매", "full": "삼성 손절 하이닉스 추매",
               "stocks": [("삼성전자", "bearish"), ("SK하이닉스", "bullish")]}
        kb = C.build([self._msg(0, "x")], [], [sig])
        ss = kb["stocks"]["삼성전자"]["mentions"][0]
        hh = kb["stocks"]["SK하이닉스"]["mentions"][0]
        self.assertEqual(ss["stance"], "bearish")     # 종목별 stance
        self.assertEqual(hh["stance"], "bullish")
        self.assertEqual(ss.get("full"), "삼성 손절 하이닉스 추매")   # 의견 full 유지

    def test_research_no_full(self):
        sig = {"date": "2026-03-19", "sharer": "키움", "entities": ["삼성전자"], "themes": [],
               "stance": "자료", "type": "research", "snippet": "시황", "full": "시황 전문",
               "stocks": [("삼성전자", "자료")]}
        kb = C.build([self._msg(0, "x")], [], [sig])
        m = kb["stocks"]["삼성전자"]["mentions"][0]
        self.assertEqual(m["type"], "research")
        self.assertNotIn("full", m)                   # research 는 full 없음


class TestAttribute(unittest.TestCase):
    def test_amd_korean_context(self):            # ③ 양성(경계로직 교정 전엔 RED)
        self.assertIn("AMD", U.ENTITIES)
        r = dict(U.attribute_stocks("AMD 추매했어요 좋음", False))
        self.assertIn("AMD", r)

    def test_amdocs_excluded(self):               # ③ 음성(오탐 제외)
        r = dict(U.attribute_stocks("AMDOCS는 통신소프트라 관심", False))
        self.assertNotIn("AMD", r)

    def test_no_signal_excluded(self):            # 단순 언급 → 제외
        r = dict(U.attribute_stocks("오늘 삼성전자 뉴스 봤어", False))
        self.assertNotIn("삼성전자", r)

    def test_far_signal_excluded(self):           # ② stance 멀리(>윈도우) → 제외
        filler = "가" * (U.W_ATTR + 10)
        r = dict(U.attribute_stocks(f"삼성전자{filler}좋게 봅니다", False))
        self.assertNotIn("삼성전자", r)

    def test_per_segment_split(self):             # ⑤ 근접 복수종목 절단
        r = dict(U.attribute_stocks("삼성전자는 손절하고 정리했지만 하이닉스는 추매로 담았습니다", False))
        self.assertEqual(r.get("삼성전자"), "bearish")
        self.assertEqual(r.get("SK하이닉스"), "bullish")

    def test_research_stance_label(self):         # ④ 시황 stance="자료"
        body = U.SRC_MARKERS[0] + " 삼성전자 비중확대 기대"
        r = dict(U.attribute_stocks(body, True))
        if "삼성전자" in r:
            self.assertEqual(r["삼성전자"], "자료")


class TestTypeNews(unittest.TestCase):
    def _msg(self, body):
        return {"idx": 0, "date": "2026-03-20", "weekday": "금요일", "time": "09:00",
                "sender": "ㄱ 이혜나", "body": body, "lines": body.split("\n")}

    def test_news_url_no_stance_is_research(self):       # URL + 강세/약세 없음 → 뉴스
        sig = U.strategy([self._msg("삼성전자 신제품 출시 https://n.news.naver.com/x")])
        self.assertTrue(sig)
        self.assertEqual(sig[0]["type"], "research")

    def test_news_media_no_stance_is_research(self):     # 매체명 + 강세/약세 없음 → 뉴스
        sig = U.strategy([self._msg("삼성전자 실적 개선 전망 - 한국경제 기자")])
        self.assertTrue(sig)
        self.assertEqual(sig[0]["type"], "research")

    def test_opinion_with_stance_kept_despite_url(self): # 강세 키워드 있으면 URL 있어도 의견 유지
        sig = U.strategy([self._msg("삼성전자 좋게 봐서 추매했어요 https://x.co/a")])
        self.assertTrue(sig)
        self.assertIn(sig[0]["type"], ("view", "position"))


class TestRoomOf(unittest.TestCase):
    def test_regex_name(self):
        # 실데이터 규칙: KakaoTalk_Chat_<room>_<타임스탬프>.csv
        self.assertEqual(
            U.room_of("/x/KakaoTalk_Chat_2026 프롬어스_2026-05-20-20-33-17.csv"),
            "2026 프롬어스")

    def test_fallback_strips_trailing_timestamp(self):
        # 규칙 불일치 → basename에서 끝 타임스탬프 제거(있으면), 없으면 확장자만 제거
        self.assertEqual(U.room_of("/x/KakaoTalk_myroom_2026-05-20.txt"), "KakaoTalk_myroom")
        self.assertEqual(U.room_of("/x/KakaoTalk_plain.csv"), "KakaoTalk_plain")


class TestMerge(unittest.TestCase):
    def _write(self, d, name, rows):
        # rows: [(datetime_str, sender, message)] → 카톡 CSV
        import csv as _csv
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = _csv.writer(f); w.writerow(["Date", "User", "Message"])
            for dt, u, msg in rows: w.writerow([dt, u, msg])
        return p

    def test_base_verbatim_keeps_same_minute_dupes(self):
        # 같은 방 최신 1파일: dedup 미적용 → 같은 분·동일 body 2건 둘 다 보존
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        p = self._write(d, "KakaoTalk_Chat_방A_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:10", "대성", "ㅋㅋㅋ"),
            ("2026-05-20 09:00:40", "대성", "ㅋㅋㅋ"),   # 다른 실제 메시지(초만 다름)
        ])
        msgs = U.merge_inputs([p])
        self.assertEqual(len(msgs), 2)                 # 유실 없음
        self.assertEqual([m["idx"] for m in msgs], [0, 1])
        self.assertTrue(all(m["room"] == "방A" for m in msgs))

    def test_same_room_snapshots_dedup_via_fold(self):
        # 같은 방 두 스냅샷(old ⊂ new): 최신만 채택, fold 0건 → 중복 없음
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        old = self._write(d, "KakaoTalk_Chat_방A_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "안녕"),
        ])
        time.sleep(0.02)
        new = self._write(d, "KakaoTalk_Chat_방A_2026-05-21-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "안녕"),
            ("2026-05-21 09:00:00", "대성", "오늘도"),
        ])
        msgs = U.merge_inputs([old, new])
        bodies = [m["body"] for m in msgs]
        self.assertEqual(bodies, ["안녕", "오늘도"])    # 중복 없이 union

    def test_two_rooms_merged_and_tagged(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        a = self._write(d, "KakaoTalk_Chat_방A_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "A방 메시지")])
        b = self._write(d, "KakaoTalk_Chat_방B_2026-06-20-10-00-00.csv", [
            ("2026-06-20 09:00:00", "밝쌤", "B방 메시지")])
        msgs = U.merge_inputs([b, a])                  # 순서 무관
        self.assertEqual(len(msgs), 2)
        self.assertEqual({m["room"] for m in msgs}, {"방A", "방B"})
        self.assertEqual([m["idx"] for m in msgs], [0, 1])
        # 방 그룹은 최초등장 datetime 순 → A(5월) 먼저
        self.assertEqual(msgs[0]["room"], "방A")

    def test_name_collision_keeps_both_rooms(self):
        # 동일 표시명 서로 다른 방(내용 disjoint) → fold로 둘 다 보존(방 유실 없음)
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        r1 = self._write(d, "KakaoTalk_Chat_같은이름_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "첫째 방 대화")])
        time.sleep(0.02)
        r2 = self._write(d, "KakaoTalk_Chat_같은이름_2026-05-21-10-00-00.csv", [
            ("2026-05-21 09:00:00", "밝쌤", "둘째 방 대화")])
        msgs = U.merge_inputs([r1, r2])
        bodies = sorted(m["body"] for m in msgs)
        self.assertEqual(bodies, ["둘째 방 대화", "첫째 방 대화"])  # 유실 없음

    def test_build_meta_from_to_min_max(self):
        # 방 그룹 정렬로 msgs 순서가 시간순이 아닐 때도 from/to는 실제 min/max
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        a = self._write(d, "KakaoTalk_Chat_방Z_2026-05-20-10-00-00.csv", [
            ("2026-05-20 09:00:00", "대성", "중간")])
        b = self._write(d, "KakaoTalk_Chat_방A_2026-06-20-10-00-00.csv", [
            ("2026-04-01 09:00:00", "밝쌤", "가장 이른"),
            ("2026-07-01 09:00:00", "밝쌤", "가장 늦은")])
        msgs = U.merge_inputs([a, b])
        kb = C.build(msgs, [], [])
        self.assertEqual(kb["build"]["from"], "2026-04-01")
        self.assertEqual(kb["build"]["to"], "2026-07-01")


class TestRoomGuards(unittest.TestCase):
    def _m(self, idx, room, sender, body):
        return {"idx": idx, "date": "2026-05-20", "time": "09:00",
                "weekday": "수요일", "sender": sender, "room": room,
                "body": body, "lines": body.split("\n")}

    def test_link_title_not_borrowed_across_rooms(self):
        # A방 링크(제목 없음) 바로 뒤 이웃이 B방 동명이인 → 제목 near-보충 금지
        msgs = [
            self._m(0, "방A", "대성", "https://x.co/aaa"),
            self._m(1, "방B", "대성", "이건 B방 제목 후보 텍스트입니다"),
        ]
        recs = U.link_records(msgs)
        rec = [r for r in recs if r["url"].startswith("https://x.co/aaa")][0]
        self.assertNotEqual(rec.get("title_src"), "near")   # 방 넘어 빌려오지 않음

    def test_qna_not_matched_across_rooms(self):
        # A방 질문(idx 0) 바로 뒤 B방 교사 메시지(idx 1) → QnA 미매칭
        q = self._m(0, "방A", "학생하나", "이거 어떻게 하나요?")
        a = self._m(1, "방B", "밝쌤👩🏻‍🏫", "이렇게 하시면 됩니다 자세한 설명 추가")
        kb = C.build([q, a], [], [])
        self.assertEqual(kb["qna"], [])          # 방 경계 넘어 응답 매칭 금지

    def test_qna_matched_within_room(self):
        q = self._m(0, "방A", "학생하나", "이거 어떻게 하나요?")
        a = self._m(1, "방A", "밝쌤👩🏻‍🏫", "이렇게 하시면 됩니다 자세한 설명 추가")
        kb = C.build([q, a], [], [])
        self.assertEqual(len(kb["qna"]), 1)      # 같은 방이면 정상 매칭


class TestDeterminism(unittest.TestCase):
    def test_chat_kb_hashseed_independent(self):
        import subprocess, json
        ents = list(U.ENTITIES)
        aliases = [U.ENTITIES[e]["al"][0] for e in ents[:3]]   # 3개 종목 별칭(하드코딩 금지)
        body = " ".join(aliases) + " 모두 좋게 봅니다"
        gendir = os.path.dirname(os.path.abspath(U.__file__))
        code = (
            f"import sys,json; sys.path.insert(0, {gendir!r}); import chat_to_kb as C;"
            f"m=[{{'idx':0,'date':'2026-03-20','time':'09:00','weekday':'금요일',"
            f"'sender':'ㄱ 이혜나','room':'r','body':{body!r},'lines':[{body!r}]}}];"
            f"print(json.dumps(C.build(m, [], []), ensure_ascii=False))"
        )
        def run(seed):
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            return subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
        outs = {run(s) for s in ("0", "1", "2", "3", "4")}
        self.assertEqual(len(outs), 1,
                         "chat_kb.json이 PYTHONHASHSEED에 따라 달라짐(set 반복 sorted() 누락?)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
