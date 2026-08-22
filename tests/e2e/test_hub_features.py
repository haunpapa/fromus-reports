# -*- coding: utf-8 -*-
"""Track B 기능 스모크 — 모바일 내비·검색 2.0·종목 상세·홈 카드·검증 코호트.

Track A 가 만드는 새 필드(whats_new·aliases·verify.report 등)가 없는 빌드에서는
해당 단언을 skip 하거나 '없으면 없어야 한다'로 대칭 검증한다."""
import pytest

pytest.importorskip("playwright")

from tests.e2e.test_hub_smoke import _boot   # noqa: E402


# ───────────────────────── Task 2: 모바일 내비 ─────────────────────────

def test_mobile_bottom_nav_has_five_plus_more(page, site_url):
    page.set_viewport_size({"width": 375, "height": 812})
    _boot(page, site_url, "#stocks")            # 홈이 아닌 탭에서 더보기를 눌러도 탭이 바뀌면 안 된다
    visible = page.evaluate("[...document.querySelectorAll('#bnav .tab')].filter(b=>b.offsetParent!==null).length")
    assert visible == 5
    page.click("#bnavMore")
    page.wait_for_selector("#bsheet.open", timeout=5000)
    assert "active" in (page.get_attribute("#view-stocks", "class") or ""), "더보기가 showTab(undefined) 로 홈으로 튐"
    page.click('#bsheet .tab[data-tab="glossary"]')
    page.wait_for_function("document.querySelector('#view-glossary').classList.contains('active')", timeout=10000)
    assert page.evaluate("document.querySelector('#bsheet').classList.contains('open')") is False
    assert "active" in page.get_attribute("#bnavMore", "class")


def test_mobile_search_sheet_opens_and_closes(page, site_url):
    page.set_viewport_size({"width": 375, "height": 812})
    _boot(page, site_url)
    page.click("#q")
    page.wait_for_selector("body.search-open", timeout=5000)
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    # 기하 확인 — 클래스만 붙고 55px 띠에 갇히는 회귀를 잡는다 (.topbar 가 전체화면 층이어야 한다)
    box = page.evaluate("(r=>({h:r.height,t:r.top}))(document.querySelector('.topbar').getBoundingClientRect())")
    assert box["t"] == 0 and box["h"] >= 700, box
    panel = page.evaluate("document.querySelector('#searchPanel').getBoundingClientRect().height")
    assert panel > 200, "결과 패널이 보이는 높이로 펼쳐져야 한다"
    assert page.evaluate("getComputedStyle(document.querySelector('#bnav')).display") == "none"
    page.click("#qClose")
    page.wait_for_function("!document.body.classList.contains('search-open')", timeout=5000)
