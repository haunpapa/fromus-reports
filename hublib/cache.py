# -*- coding: utf-8 -*-
"""리포트 파싱 결과 증분 캐시 — 파일 내용 sha1 기준 무효화.

리포트 HTML 은 한번 커밋되면 내용이 바뀌지 않으므로, 파일 내용 해시가 같으면
직전 파싱 결과를 재사용한다. 파서(hublib.parse.parse_report) 로직이 바뀌면
CI 캐시 키(hublib/parse.py 해시)가 달라져 자동 무효화된다.
"""
import copy
import hashlib
import json
import os


class ParseCache:
    def __init__(self, path="build/parse_cache.json"):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}
        self.dirty = False

    def get_or_parse(self, filepath, parser):
        """filepath 내용 해시가 캐시와 같으면 저장된 파싱 결과(사본)를 반환,
        아니면 parser(filepath) 를 실행해 캐시에 저장하고 사본을 반환한다."""
        with open(filepath, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()
        entry = self.data.get(filepath)
        if entry and entry.get("sha1") == digest:
            return copy.deepcopy(entry["parsed"])
        parsed = parser(filepath)
        self.data[filepath] = {"sha1": digest, "parsed": parsed}
        self.dirty = True
        return copy.deepcopy(parsed)

    def save(self):
        if not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
