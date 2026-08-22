# -*- coding: utf-8 -*-
"""셸 앱 JS 모듈 concat 주입 + kb 분할 순수 함수 테스트."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_concat_app_js_is_in_filename_order_and_complete():
    from hublib.render import concat_app_js
    files = sorted(glob.glob(os.path.join(ROOT, "hub", "*.js")))
    assert len(files) >= 10, "hub/*.js 모듈이 없음 — Task 2 분리 스크립트를 먼저 실행"
    js = concat_app_js()
    pos = -1
    for p in files:
        body = open(p, encoding="utf-8").read()
        i = js.find(body)
        assert i > pos, f"{os.path.basename(p)} 가 빠졌거나 순서가 틀림"
        pos = i


def test_inject_app_js_replaces_marker_without_backslash_mangling():
    from hublib.render import inject_app_js
    shell = '<script type="fu-app">/*APPJS*/\n/*ENDAPPJS*/</script>'
    js = r"const re=/\d+/; const s='$1 \\n';"        # 백슬래시·$1 이 re.sub 치환에서 깨지면 안 된다
    out = inject_app_js(shell, js)
    assert js in out
    assert "/*APPJS*/" in out and "/*ENDAPPJS*/" in out


def test_template_has_app_marker_and_no_inline_app_code():
    tpl = open(os.path.join(ROOT, "hub_template.html"), encoding="utf-8").read()
    assert "/*APPJS*/" in tpl and "/*ENDAPPJS*/" in tpl
    assert "function renderHome(" not in tpl, "앱 코드가 아직 템플릿에 인라인돼 있음"


def _mini_data():
    return {
        "build": {"schema": 2, "generated": "2026-08-23 07:30", "to": "2026-08-22"},
        "reports": [{"type": "daily", "date": "2026-08-22", "id": "2026-08-22", "sort_date": "2026-08-22",
                     "file": "reports/daily/x.html", "headline": "H", "subhead": "S",
                     "timeline": [{"title": "t"}], "insights": [{"name": "n"}], "glossary": []}],
        "search": [{"kind": "종목", "title": "삼성전자", "snippet": "", "date": "", "id": "", "tags": []}],
        "glossary": [{"term": "PER", "body": "..."}],
        "stocks": [{"name": "삼성전자", "count": 3, "mentions": [],
                    "chat": {"count": 10, "signals": 4, "stance": {"bullish": 2, "bearish": 0, "watch": 1},
                             "targets": [{"value": "90000"}],
                             "opinions": [{"date": "2026-08-0%d" % i} for i in range(1, 8)],
                             "news": [{"date": "2026-08-0%d" % i, "url": "https://x/%d" % i} for i in range(1, 8)],
                             "market_news": [{"date": "2026-08-01"}, {"date": "2026-08-02"}]}},
                   {"name": "기아", "count": 1, "mentions": []}],
        "sectors": [], "chat": {"build": {"messages": 1}, "themes": {"반도체": {}}, "co_edges": [{"a": "A", "b": "B", "w": 2}],
                                "actions": [1, 2], "strategy": [1], "targets": [], "qna": [], "news": [1, 2, 3],
                                "readings": [], "glossary": []},
    }


def test_slim_reports_keeps_only_ui_fields():
    from hublib.split import slim_reports
    out = slim_reports(_mini_data()["reports"])
    assert out == [{"type": "daily", "date": "2026-08-22", "id": "2026-08-22", "sort_date": "2026-08-22",
                    "file": "reports/daily/x.html", "headline": "H", "subhead": "S"}]


def test_slim_reports_does_not_mutate_input():
    from hublib.split import slim_reports
    data = _mini_data()
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    slim_reports(data["reports"])
    assert json.dumps(data, ensure_ascii=False, sort_keys=True) == before
