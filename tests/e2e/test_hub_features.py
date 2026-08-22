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


# ───────────────────────── Task 3: 검색 2.0 ─────────────────────────

def test_search_alias_pins_stock_card(page, site_url):
    _boot(page, site_url)
    has_alias = page.evaluate(
        "!!(window.DATA.build && window.DATA.build.aliases && window.DATA.build.aliases['하닉']"
        " && (window.DATA.stocks||[]).some(s=>s.name==='SK하이닉스'))")
    if not has_alias:
        pytest.skip("aliases 없는 빌드이거나 SK하이닉스 미수록")
    page.fill("#q", "하닉")
    page.wait_for_selector("#searchPanel.open .sr-pin", timeout=15000)
    assert "SK하이닉스" in page.inner_text("#searchPanel .sr-pin")


def test_search_source_and_period_filters(page, site_url):
    _boot(page, site_url)
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    has_chat = page.evaluate("(window.DATA.search||[]).some(i=>i.source==='chat')")
    if has_chat:
        page.click('#searchPanel .sp-src[data-src="chat"]')
        # 핀 카드(.sr-pin)의 '종목' 은 제외 — .sr 안의 종류 배지만 본다
        page.wait_for_function(
            "[...document.querySelectorAll('#searchPanel .sr .sr-kind')].every(k=>/채팅|목표가/.test(k.textContent))",
            timeout=5000)
    page.click('#searchPanel .sp-period[data-period="7"]')
    page.wait_for_timeout(300)
    assert page.locator("#searchPanel .sp-period.on").get_attribute("data-period") == "7"


def test_recent_queries_shown_on_empty_focus(page, site_url):
    _boot(page, site_url)
    page.fill("#q", "반도체")
    page.wait_for_selector("#searchPanel.open .sr", timeout=15000)
    page.click("#searchPanel button.sr >> nth=0")     # a.sr(채팅뉴스)은 새 탭을 열므로 button 만
    page.keyboard.press("Escape")
    page.fill("#q", "")
    page.click("#q")
    page.wait_for_selector("#searchPanel .sp-recent", timeout=5000)
    assert "반도체" in page.inner_text("#searchPanel .sp-recent")


# ───────────────────────── Task 4: 종목 상세 뷰 ─────────────────────────

def test_stock_detail_route(page, site_url):
    _boot(page, site_url)
    first = page.evaluate("window.DATA.stocks[0].name")
    page.goto(site_url + "hub.html#stock/" + first)
    page.wait_for_selector("#view-stock.active .sd-head", timeout=15000)
    assert first in page.inner_text("#view-stock .sd-head")
    assert page.locator("#view-stock .sd-mentions .mention").count() >= 1


def test_stock_chip_opens_detail(page, site_url):
    _boot(page, site_url)
    page.click("#view-home [data-stock] >> nth=0")
    page.wait_for_selector("#view-stock.active .sd-head", timeout=15000)
    assert page.evaluate("location.hash").startswith("#stock/")


def test_mobile_search_select_keeps_stock_detail(page, site_url):
    """모바일 검색 시트에서 종목 핀을 선택하면 history.back() 없이 상세 뷰가 유지돼야 한다."""
    page.set_viewport_size({"width": 375, "height": 812})
    _boot(page, site_url)
    first = page.evaluate("window.DATA.stocks[0].name")
    page.click("#q")
    page.fill("#q", first)
    page.wait_for_selector("#searchPanel.open .sr-pin", timeout=15000)
    page.click("#searchPanel .sr-pin")
    page.wait_for_timeout(400)
    assert page.locator("#view-stock.active .sd-head").count() == 1
    assert page.evaluate("location.hash").startswith("#stock/")
    assert page.evaluate("document.body.classList.contains('search-open')") is False
