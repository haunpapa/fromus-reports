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
            "[...document.querySelectorAll('#searchPanel .sr .sr-kind')].every(k=>/채팅/.test(k.textContent))",
            timeout=5000)
        # 칩을 눌러 패널을 다시 그려도 열린 채로 남아야 한다 (document 의 '바깥 클릭' 핸들러가 닫아버리던 회귀)
        assert page.locator("#searchPanel.open").is_visible()
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


# ───────────────────── Task 5: 홈 What's new · AI 데일리 ─────────────────────

def test_whats_new_card_matches_data(page, site_url):
    _boot(page, site_url)
    # diff 객체는 있어도 다섯 배열이 전부 빈 날이 있다 → '내용이 있을 때만' 카드
    has = page.evaluate(
        "(w=>!!w && ['new_stocks','surging','new_calls','new_targets','new_reports']"
        ".some(k=>(w[k]||[]).length))(window.DATA.whats_new)")
    assert page.locator("#whatsNew").count() == (1 if has else 0)
    if has:
        assert page.locator("#whatsNew [data-stock], #whatsNew [data-go], #whatsNew [data-report]").count() >= 1


def test_ai_daily_lines_when_present(page, site_url):
    _boot(page, site_url)
    has = page.evaluate("!!(window.DATA.ai_digest && window.DATA.ai_digest.daily && (window.DATA.ai_digest.daily.lines||[]).length)")
    assert page.locator(".brf-ai").count() == (1 if has else 0)


# ───────────────────── Task 6: 검증 탭 코호트·테마·분포 ─────────────────────

def test_verify_cohort_toggle_and_histogram(page, site_url):
    _boot(page, site_url)
    if not page.evaluate("typeof verifyOn==='function' && verifyOn()"):
        pytest.skip("verify 비활성 또는 숨김(VERIFY_TAB_HIDDEN)")
    page.goto(site_url + "hub.html#verify")
    page.wait_for_selector("#view-verify .v-score", timeout=15000)
    assert page.locator("#vHist").count() == 1
    has_rep = page.evaluate("!!(window.DATA.verify.report && window.DATA.verify.report.enabled)")
    assert page.locator("#vCohort").count() == (1 if has_rep else 0)
    if has_rep:
        page.click('#vCohort button[data-cohort="report"]')
        page.wait_for_selector("#vThemes", timeout=5000)
        if page.evaluate("(window.DATA.verify.themes||[]).length"):
            assert page.locator("#vThemes .v-row").count() >= 1
        assert "리포트" in page.inner_text("#view-verify .sec-sub")


def test_verify_tab_hidden_when_flag_set(page, site_url):
    """검증 탭은 일단 숨김 — 탭 버튼 3곳 display:none, #verify 딥링크는 홈으로, 홈 카드의 '검증 탭 →' 링크도 없어야 한다.
    플래그가 없으면 ReferenceError 로 실패한다 — 플래그 자체가 계약이다."""
    _boot(page, site_url, "#verify")
    if not page.evaluate("VERIFY_TAB_HIDDEN"):
        pytest.skip("검증 탭 활성(VERIFY_TAB_HIDDEN=false)")
    assert page.evaluate(
        "[...document.querySelectorAll('.tab[data-tab=\"verify\"]')].length >= 2 && "
        "[...document.querySelectorAll('.tab[data-tab=\"verify\"]')].every(b=>getComputedStyle(b).display==='none')")
    assert page.locator("#view-home.active").count() == 1, "#verify 는 홈으로 보내야 한다"
    assert page.evaluate("document.querySelector('#view-verify').innerHTML.length") == 0
    assert page.evaluate("document.querySelectorAll('#view-home [data-go=\"verify\"]').length") == 0, "홈에 죽은 '검증 탭 →' 링크"
