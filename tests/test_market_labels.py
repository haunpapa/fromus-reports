"""시황 코너 제목이 섹터·테마 랭킹에 섞이지 않아야 한다 (2026-08-21 사용자 리포트)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest


# 실제 데일리 리포트에서 관찰된 시황 코너 제목들
MARKET_LABELS = [
    "시총 상위 급락", "시총 상위 강세", "시총 상위 동향",
    "코스피 — 기관은 대형주를 받았다", "코스피 — 외국인은 밖을 봤다",
    "코스닥 — 외국인 vs 기관", "−5.80% 장에서 오른 종목",
    "오늘의 특징주", "오늘의 급등", "오늘의 급락", "오늘의 실적·수주 뉴스",
    "약세 종목 · 오늘의 그림자", "코스닥 주도주", "대형주 순매수 상위",
    "급락장 방어주 · 순매수 상위", "인버스로 몸을 피한 자금",
    "인버스·레버리지의 하루", "코스닥 수급 포인트", "빨간불이 켜진 소수",
]

# 키워드 매핑이 우선이어야 하는 이름들 (시황 낱말이 섞여 있어도 테마 유지)
THEMED_NAMES = [
    ("로봇 — 오늘의 주도 섹터", "로봇·피지컬AI"),
    ("코스닥 — 소부장은 담겼다", "반도체·메모리"),
    ("코스닥 외국인 — 소부장 정조준", "반도체·메모리"),
    ("코스닥 — 소부장으로 몰린 자금", "반도체·메모리"),
    ("오늘의 주인공 · 2차전지 & 에너지", "2차전지"),
    ("코스닥 — 바이오가 끌었다", "바이오·제약"),
    ("조선·방산·정유 로테이션", "조선·방산"),
]


@pytest.mark.parametrize("name", MARKET_LABELS)
def test_market_labels_are_not_themes(name):
    from hublib.parse import sector_theme
    assert sector_theme(name) is None, f"{name!r} 는 테마가 아니라 시황 라벨"


@pytest.mark.parametrize("name,theme", THEMED_NAMES)
def test_keyword_mapping_wins_over_market_words(name, theme):
    from hublib.parse import sector_theme
    assert sector_theme(name) == theme


def test_unknown_sector_still_falls_back_to_raw_name():
    """매핑에 없는 진짜 섹터(예: 엔터)는 그대로 노출돼야 함 — 신규 테마 발견 경로 유지."""
    from hublib.parse import sector_theme
    assert sector_theme("엔터·미디어") == "엔터·미디어"


def _mini_report(sec_name):
    return {
        "type": "daily", "id": "2026-08-21", "date": "2026-08-21",
        "sort_date": "2026-08-21", "weekday": "목",
        "headline": "", "subhead": "", "quote": {},
        "insights": [], "timeline": [], "actions": [], "glossary": [],
        "indicators": [], "next": [], "readings": [], "strategy": [],
        "sectors": [{"name": sec_name, "sub": "", "note": "", "stocks": ["삼성전자"]}],
    }


def test_aggregate_excludes_market_labels_from_sector_ranking():
    from hublib.aggregate import aggregate
    agg = aggregate([_mini_report("오늘의 특징주")])
    assert all(s["theme"] != "오늘의 특징주" for s in agg["sectors"])


def test_aggregate_keeps_stock_mentions_from_market_sections():
    """시황 코너의 종목 언급은 종목 집계에 남되 출처는 '시황'."""
    from hublib.aggregate import aggregate
    agg = aggregate([_mini_report("오늘의 특징주")])
    stock = next((s for s in agg["stocks"] if s["name"] == "삼성전자"), None)
    assert stock is not None and stock["count"] == 1
    assert stock["theme_count"] == 0 and stock["themes"] == []
    assert stock["mentions"][0]["source"] == "시황"
    assert stock["mentions"][0]["label"] == "오늘의 특징주"
