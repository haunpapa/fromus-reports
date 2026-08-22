# -*- coding: utf-8 -*-
"""E2E 스모크용 정적 서버 — E2E_SITE_DIR(hub.html·kb.*.json·sw.js 가 있는 폴더)를 서빙한다.
환경변수가 없으면 전부 skip — 단위 테스트 실행 시간에 영향 없음."""
import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_a):           # 테스트 출력 오염 방지
        pass


@pytest.fixture(scope="session")
def site_url():
    site = os.environ.get("E2E_SITE_DIR")
    if not site:
        pytest.skip("E2E_SITE_DIR 미설정 — 스모크 테스트 생략")
    site = os.path.abspath(site)
    if not os.path.exists(os.path.join(site, "hub.html")):
        pytest.skip(f"{site}/hub.html 없음 — 먼저 render 하세요")
    handler = functools.partial(_QuietHandler, directory=site)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/"
    finally:
        srv.shutdown()
