# -*- coding: utf-8 -*-
"""허브 셸 스모크 — 부트·탭·검색·딥링크·SW. 실행: E2E_SITE_DIR=. python -m pytest tests/e2e -q"""
import json
import os

import pytest

pytest.importorskip("playwright")   # 플러그인 없으면 모듈 전체 skip

IGNORED_CONSOLE = ("fonts.googleapis", "fonts.gstatic", "cdnjs.cloudflare")   # 외부 리소스 차단 환경 허용


def _boot(page, site_url, frag=""):
    """hub.html 을 열고 부트 오버레이가 사라질 때까지 기다린다. 콘솔 에러 목록을 돌려준다."""
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error"
            and not any(k in m.text for k in IGNORED_CONSOLE) else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site_url + "hub.html" + frag)
    page.wait_for_selector("#fu-boot", state="detached", timeout=30000)
    return errors


def test_boot_renders_home_without_errors(page, site_url):
    errors = _boot(page, site_url)
    assert page.locator("#view-home.active").count() == 1
    assert page.locator("#view-home .briefing").count() == 1
    assert errors == [], errors
    # s.src 는 해석된 절대 URL 이라 자기 호스트도 https? 로 시작한다 → origin 으로 판별한다
    ext = page.evaluate(
        "[...document.scripts].filter(s=>s.src && new URL(s.src, location.href).origin !== location.origin).length")
    assert ext == 0, "외부 호스트 스크립트가 남아 있음"
    assert page.evaluate("typeof window.Chart") == "function"


@pytest.mark.parametrize("tab", ["analytics", "sectors", "stocks", "strategy", "glossary", "graph", "chat"])
def test_tab_renders_via_hash(page, site_url, tab):
    errors = _boot(page, site_url, "#" + tab)
    view = page.locator(f"#view-{tab}")
    page.wait_for_function(
        f"document.querySelector('#view-{tab}') && document.querySelector('#view-{tab}').innerHTML.length > 200",
        timeout=15000)
    assert "active" in (view.get_attribute("class") or "")
    assert errors == [], errors


def test_verify_tab_when_enabled(page, site_url):
    _boot(page, site_url)
    enabled = page.evaluate("typeof verifyOn==='function' && verifyOn()")
    if not enabled:
        pytest.skip("verify 비활성 빌드 또는 숨김(VERIFY_TAB_HIDDEN)")
    page.goto(site_url + "hub.html#verify")
    page.wait_for_selector("#view-verify .v-score", timeout=15000)


def test_global_search_returns_results(page, site_url):
    errors = _boot(page, site_url)
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    assert page.locator("#searchPanel .sr").count() > 0
    assert errors == [], errors


def test_stock_deep_link_opens_detail(page, site_url):
    _boot(page, site_url)
    first = page.evaluate("(window.DATA.stocks||[])[0] && window.DATA.stocks[0].name")
    assert first, "종목 데이터 없음"
    page.goto(site_url + "hub.html#stocks/" + first)
    page.wait_for_selector("#stockList .strow-detail.open", timeout=15000)


def test_no_javascript_hrefs(page, site_url):
    _boot(page, site_url, "#chat")
    page.wait_for_timeout(500)
    bad = page.evaluate("[...document.querySelectorAll('a[href]')].filter(a=>/^javascript:/i.test(a.getAttribute('href'))).length")
    assert bad == 0


def test_service_worker_registers(page, site_url):
    _boot(page, site_url)
    ok = page.evaluate("navigator.serviceWorker.ready.then(r=>!!r.active)")
    assert ok


def test_boot_timing_recorded(page, site_url):
    """성능 회귀 관찰용 — 부트 완료까지 시간을 build/e2e_timing.json 에 남긴다. 단언은 느슨하게."""
    _boot(page, site_url)
    nav = page.evaluate("performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd")
    dom = page.evaluate("document.getElementsByTagName('*').length")
    canvases = page.evaluate("document.querySelectorAll('canvas').length")
    os.makedirs("build", exist_ok=True)
    with open("build/e2e_timing.json", "w", encoding="utf-8") as f:
        json.dump({"dcl_ms": nav, "dom_nodes": dom, "canvases": canvases}, f)
    assert nav < 15000


def test_boot_renders_only_home(page, site_url):
    """부트 직후에는 홈만 그려져 있어야 한다(P3). 다른 탭은 첫 진입 시 렌더."""
    _boot(page, site_url)
    assert page.evaluate("document.querySelector('#view-stocks').innerHTML.length") == 0
    assert page.evaluate("document.querySelectorAll('canvas').length") < 15
    page.click('#tabs .tab[data-tab="stocks"]')
    page.wait_for_selector("#stockList .strow", timeout=15000)
    assert page.evaluate("document.querySelector('#view-stocks').innerHTML.length") > 200


def test_search_loads_search_chunk_lazily(page, site_url):
    _boot(page, site_url)
    loaded = page.evaluate("performance.getEntriesByType('resource').some(r=>/kb\\.search\\./.test(r.name))")
    assert loaded is False, "부트에서 search 청크를 받으면 안 된다"
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    loaded = page.evaluate("performance.getEntriesByType('resource').some(r=>/kb\\.search\\./.test(r.name))")
    assert loaded is True


def test_core_is_small(page, site_url):
    _boot(page, site_url)
    size = page.evaluate("(performance.getEntriesByType('resource').find(r=>/kb\\.core\\./.test(r.name))||{}).decodedBodySize||0")
    assert 0 < size < 3_000_000, f"core 가 너무 큼: {size}"


def test_update_toast_when_version_differs(page, site_url):
    """새 배포 감지 토스트 — version.json 응답만 가로챈다(파일 무변경·병렬 안전)."""
    page.route("**/version.json*", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body='{"core":"kb.core.0000000000.json","generated":"2099-01-01 00:00"}'))
    _boot(page, site_url)
    page.wait_for_selector("#fu-toast", timeout=10000)
