# -*- coding: utf-8 -*-
"""리포트 파싱 증분 캐시 테스트 — 파일 내용 sha1 기준 무효화."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hublib.cache import ParseCache


def test_cache_hit_and_invalidation(tmp_path):
    cache_file = tmp_path / "parse_cache.json"
    target = tmp_path / "r.html"
    target.write_text("<html>v1</html>", encoding="utf-8")

    c = ParseCache(str(cache_file))
    calls = []

    def parser(p):
        calls.append(p)
        return {"parsed": "v1"}

    assert c.get_or_parse(str(target), parser) == {"parsed": "v1"}
    assert c.get_or_parse(str(target), parser) == {"parsed": "v1"}
    assert len(calls) == 1                      # 두 번째는 캐시 히트

    target.write_text("<html>v2</html>", encoding="utf-8")   # 내용 변경 → 무효화
    c.get_or_parse(str(target), parser)
    assert len(calls) == 2

    c.save()
    c2 = ParseCache(str(cache_file))            # 디스크에서 복원돼도 히트
    c2.get_or_parse(str(target), parser)
    assert len(calls) == 2


def test_cache_returns_independent_copies(tmp_path):
    # 캐시가 돌려준 객체를 호출자가 변경해도 캐시 원본은 오염되지 않아야 한다 (불변성)
    cache_file = tmp_path / "parse_cache.json"
    target = tmp_path / "r.html"
    target.write_text("x", encoding="utf-8")
    c = ParseCache(str(cache_file))
    first = c.get_or_parse(str(target), lambda p: {"k": [1, 2]})
    first["k"].append(999)
    second = c.get_or_parse(str(target), lambda p: {"k": [1, 2]})
    assert second == {"k": [1, 2]}, "캐시가 호출자 변경에 오염됨"


def test_save_is_noop_when_clean(tmp_path):
    cache_file = tmp_path / "parse_cache.json"
    c = ParseCache(str(cache_file))
    c.save()                                    # 변경 없음 → 파일 미생성
    assert not cache_file.exists()
