# -*- coding: utf-8 -*-
import os, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_archive as U

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
        f.write(text); f.close(); return f.name

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
        old = os.path.join(d, "KakaoTalk_old.csv"); open(old, "w").close()
        time.sleep(0.02)
        new = os.path.join(d, "KakaoTalk_new.csv"); open(new, "w").close()
        out = os.path.join(d, "뉴스_전체아카이브.csv"); open(out, "w").close()  # 출력형(미선택)
        # 명시 인자 우선
        self.assertEqual(U.find_input(["prog", new]), new)

if __name__ == "__main__":
    unittest.main(verbosity=2)
