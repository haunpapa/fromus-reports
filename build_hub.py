#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
프롬어스 Knowledge Hub Builder
================================
데일리/위클리 리포트(HTML)를 구조화 추출 → knowledge_base.json 생성 →
self-contained 인터랙티브 허브(hub.html)로 빌드.

사용법:
    python build_hub.py                     # 현재 폴더(및 하위)에서 리포트 자동 탐색
    python build_hub.py --src ./reports     # 특정 폴더 지정
    python build_hub.py --src . --out hub.html --json knowledge_base.json

리포트 파일명 규칙(자동 인식):
    데일리:  YYYY-MM-DD.html   (예: 2026-05-29.html, 오타 2026-05.28.html 도 허용)
    위클리:  YYYY-Www.html     (예: 2026-W22.html)
    또는:    프롬어스_Daily_Report_YYYY-MM-DD.html

GitHub Actions에서 새 리포트 커밋 시 이 스크립트를 자동 실행하도록 구성합니다.
"""
import argparse, json, os, re, sys, glob, datetime, html as _html
from collections import defaultdict, OrderedDict

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("BeautifulSoup4 가 필요합니다:  pip install beautifulsoup4 lxml")

# ─────────────────────────────────────────────────────────────────────────
# 정규화 사전
# ─────────────────────────────────────────────────────────────────────────
STOCK_ALIASES = {
    "하닉": "SK하이닉스", "에스케이하이닉스": "SK하이닉스", "sk하이닉스": "SK하이닉스",
    "삼전": "삼성전자", "삼성": "삼성전자",
    "엔비": "엔비디아", "엔비디아": "엔비디아", "nvda": "엔비디아",
    "ms": "마이크로소프트", "마소": "마이크로소프트", "마이크로소프트": "마이크로소프트",
    "두산e": "두산에너빌리티", "두산에너빌리티": "두산에너빌리티",
    "lg엔솔": "LG에너지솔루션", "엘지엔솔": "LG에너지솔루션", "lg에너지솔루션": "LG에너지솔루션",
    "모비스": "현대모비스", "현대차": "현대차", "현대자동차": "현대차",
    "팔란티어": "팔란티어", "오라클": "오라클", "테슬라": "테슬라",
    "마이크론": "마이크론", "샌디스크": "샌디스크", "키옥시아": "키옥시아",
    "네이버": "네이버", "기아": "기아",
}
# 종목으로 오인식되기 쉬운 일반 명사 / 섹터어 (정확히 일치할 때만 제거)
STOCK_STOPWORDS = {
    "등", "외", "관련주", "부품주", "수혜주", "테마", "생태계", "공급망",
    "반도체", "바이오", "로봇", "소프트웨어", "우주항공", "2차전지", "이차전지",
    "양자컴퓨터", "증권주", "방산", "조선", "채권", "보험", "은행", "원전",
    "메모리", "HBM", "ESS", "AI", "ETF", "코스피", "코스닥",
    "자동차", "제약", "엔터", "은", "silver", "차전지", "헬스케어", "금융",
    "음식료", "화학", "철강", "건설", "유통", "운송",
}
# 영문 표기 → 한글 정규화(중복 제거)
STOCK_ALIASES.update({
    "micron": "마이크론", "sandisk": "샌디스크", "dell": "델", "d-wave": "디웨이브",
    "dwave": "디웨이브", "nvidia": "엔비디아", "tesla": "테슬라", "google": "구글",
    "oracle": "오라클", "palantir": "팔란티어",
})
# ETF 브랜드(접두) — 전체 명칭을 종목명으로 유지
ETF_BRANDS = ("KODEX", "TIGER", "KBSTAR", "ARIRANG", "PLUS", "SOL", "ACE",
              "RISE", "KOSEF", "TIMEFOLIO", "HANARO", "KIWOOM", "WON")

# 섹터 → 대표 테마 정규화
SECTOR_THEME = [
    (("반도체", "hbm", "메모리", "dram", "nand", "d램", "파운드리"), "반도체·메모리"),
    (("로봇", "로보", "피지컬", "휴머노이드"), "로봇·피지컬AI"),
    (("소프트웨어", "sw", "소프트"), "소프트웨어·AI"),
    (("바이오", "제약", "헬스", "인슐린"), "바이오·제약"),
    (("전력", "ess", "터빈", "원전", "에너빌"), "AI 전력·원전·ESS"),
    (("우주", "항공", "스페이스", "위성"), "우주항공·위성"),
    (("보험", "금리", "은행", "금융"), "금융·금리수혜"),
    (("이차전지", "2차전지", "배터리"), "2차전지"),
    (("자동차", "현대차", "모빌리티", "글로비스"), "자동차·현대차그룹"),
    (("증권",), "증권·자본시장"),
    (("양자",), "양자컴퓨터"),
    (("조선", "해양", "방산"), "조선·방산"),
    (("채권", "자산배분"), "채권·자산배분"),
    (("은(", "은銀", "안전자산", "원자재"), "원자재·안전자산"),
    (("삼성그룹", "삼성그룹 동반"), "삼성그룹"),
]
# 테마 → 키워드 역매핑 (대표님 직접 언급 가중 판정용)
THEME_KEYS = {}
for _keys, _theme in SECTOR_THEME:
    THEME_KEYS.setdefault(_theme, _keys)

# 수급(스마트머니) 카드 식별 — 테마 섹터와 분리
def is_supply_card(name):
    n = name or ""
    if "TOP" in n.upper():
        return True
    if any(k in n for k in ("투신", "연기금", "사모펀드", "기금")):
        return True
    if any(k in n for k in ("외인", "외국인", "기관")) and any(k in n for k in ("매수", "순매수")):
        return True
    return False

def supply_tag(name):
    n = name or ""
    who = ("외국인" if ("외인" in n or "외국인" in n) else
           "연기금" if "연기금" in n else "투신" if "투신" in n else
           "사모펀드" if "사모펀드" in n else "기관" if "기관" in n else "기관")
    where = "코스닥" if "코스닥" in n else "코스피" if "코스피" in n else ""
    return f"{who} 순매수{(' · ' + where) if where else ''}"

# 살아있는 전략 원칙 버킷 (키워드 매칭)
PRINCIPLE_BUCKETS = [
    ("현금은 총알 — 변동성 대비 현금 비중 확보", "💵", ("총알", "현금 비중", "현금(", "현금은", "예비 총알", "현금 확보")),
    ("분할매수·적립 — 타이밍 대신 기계적 매수", "📈", ("분할매수", "분할 매수", "적립", "적립식", "분할 매도", "분할매도")),
    ("매도 없는 계좌 — 장기 종목 분리 보유", "🔒", ("매도 없는", "매도는 없는", "매도없는", "장기 투자", "장기로 들고")),
    ("순환매 대비 — 다음 차례 섹터 미리 준비", "🔁", ("순환매",)),
    ("쏠림 경계 — 대형주 양극화·투기성 주의", "⚖️", ("쏠림", "양극화", "투기성", "몰빵")),
    ("레버리지 자제 — 단일종목 레버리지 ETF 경계", "🚨", ("레버리지",)),
    ("추격매수 자제 — '남들 사니까' 매매 금지", "✋", ("추격매수", "추격 매수", "따라 들어가")),
    ("노후·연금 — 수익만큼 미래도 함께", "🌱", ("노후", "연금", "은퇴")),
]

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

# ─────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────
def txt(el, sep=" "):
    if el is None:
        return ""
    s = el.get_text(sep, strip=True)
    return re.sub(r"\s+", " ", s).strip()

def txt_tight(el):
    """인라인 <em> 등으로 끊긴 제목을 자연스럽게 합치되 <br>은 공백으로."""
    if el is None:
        return ""
    for br in el.find_all("br"):
        br.replace_with("")           # 공백 sentinel (strip에 안 지워지도록)
    s = el.get_text("", strip=True).replace("", " ")
    return re.sub(r"\s+", " ", s).strip()

def classes(el):
    return set(el.get("class", []) or [])

def parse_target_prices(s):
    """문자열에서 목표가/콜 스니펫 추출."""
    out = []
    for m in re.finditer(r"(?:목표(?:주)?가|TP)\s*[:\-]?\s*([0-9][0-9,\.]*)\s*(만원|만|달러|원|\$)?", s, re.I):
        val = m.group(1).replace(",", "")
        unit = m.group(2) or ""
        out.append({"value": val, "unit": unit, "raw": m.group(0).strip()})
    # "(KB TP 380만)" 형태의 출처 포함
    return out

def parse_num(s):
    if not s:
        return None
    m = re.search(r"-?[0-9][0-9,\.]*", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None

def normalize_stock(name):
    n = name.strip()
    key = n.lower().replace(" ", "")
    return STOCK_ALIASES.get(key, n)

def sector_theme(name):
    low = name.lower()
    for keys, theme in SECTOR_THEME:
        if any(k in low for k in keys):
            return theme
    return name.strip()

# ─────────────────────────────────────────────────────────────────────────
# 파일명/날짜 파싱
# ─────────────────────────────────────────────────────────────────────────
def detect_report(path, soup):
    fn = os.path.basename(path)
    title = txt(soup.title) if soup.title else ""
    # 위클리?
    mw = re.search(r"(\d{4})[-_]?W(\d{1,2})", fn) or re.search(r"\bW(\d{1,2})\b", title)
    is_weekly = bool(mw) or ("Weekly" in title)
    if is_weekly:
        if mw and mw.lastindex == 2:
            year, week = int(mw.group(1)), int(mw.group(2))
        else:
            mw2 = re.search(r"W(\d{1,2})", title)
            week = int(mw2.group(1)) if mw2 else 1
            my = re.search(r"(\d{4})", title)
            year = int(my.group(1)) if my else datetime.date.today().year
        try:
            sort_date = datetime.date.fromisocalendar(year, week, 5)  # 금요일
        except Exception:
            sort_date = datetime.date(year, 1, 1)
        return {"type": "weekly", "year": year, "week": week,
                "id": f"{year}-W{week:02d}", "sort_date": sort_date.isoformat()}
    # 데일리: title 우선, 없으면 파일명
    md = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", title) \
         or re.search(r"(\d{4})[.\-_](\d{1,2})[.\-_](\d{1,2})", fn)
    if md:
        y, mo, d = int(md.group(1)), int(md.group(2)), int(md.group(3))
        try:
            dt = datetime.date(y, mo, d)
            return {"type": "daily", "date": dt.isoformat(),
                    "id": dt.isoformat(), "sort_date": dt.isoformat(),
                    "weekday": WEEKDAY_KR[dt.weekday()]}
        except ValueError:
            pass
    return {"type": "daily", "date": fn, "id": fn, "sort_date": "9999-99-99", "weekday": "?"}

# ─────────────────────────────────────────────────────────────────────────
# 섹션 라우팅 헬퍼
# ─────────────────────────────────────────────────────────────────────────
def section_kind(title):
    t = title.lower()
    if any(k in title for k in ("온도", "Temperature")) or "temperature" in t:
        return "market"
    if any(k in title for k in ("무슨 일", "흐름", "Timeline")) or "timeline" in t:
        return "timeline"
    if any(k in title for k in ("핵심", "프벤져스", "Insight", "한마디", "알려준")):
        return "insights"
    if any(k in title for k in ("경제 교실", "쉬운 경제", "용어", "Economics", "배운")):
        return "glossary"
    if any(k in title for k in ("읽어", "자료", "Reading")):
        return "reading"
    if any(k in title for k in ("섹터", "Sector", "종목", "Key Moves", "주목하는")):
        return "sectors"
    if any(k in title for k in ("체크포인트", "다음 주", "다음주", "Tomorrow", "Next", "이것만은")):
        return "next"
    if any(k in title for k in ("할 일", "전략", "Action", "Strategy", "우리는 이렇게")):
        return "strategy"
    return "other"

# ─────────────────────────────────────────────────────────────────────────
# 용어(교육) vs 리서치/뉴스 카드 분류 — 용어 사전 누락 방지(교육성 카드 폭넓게 수집)
# ─────────────────────────────────────────────────────────────────────────
EDU_STRONG = ("용어", "경제 교실", "쉬운 설명", "쉽게", "암기", "심화", "직관",
              "신조어", "한 장", "이해", "뭔데", "해설", "기초", "풀이", "개념")
RESEARCH_MARKERS = ("증권", "투자증권", "리서치", "보고서", "산업노트", "기업분석",
                    "탑픽", "Exhibit", "한국경제 1면", "한경 1면", "인터뷰", "일정",
                    "신규 ETF", "실적", "FY2", "Premier", "큐레이션", "보도",
                    "골드만", "JP모건", "모건스탠리", "바클레이즈", "다올", "Vol.")
def card_is_glossary(tag, title):
    """교육·용어 카드면 True(용어 사전), 증권사 리서치·실적·뉴스면 False(자료)."""
    s = (tag or "") + " " + (title or "")
    if any(m in s for m in EDU_STRONG):
        return True
    if any(m in s for m in RESEARCH_MARKERS):
        return False
    return True   # 기본 포함 — 사용자 요청: 누락 줄이고 더 많이 아카이빙

# ─────────────────────────────────────────────────────────────────────────
# 단일 리포트 파싱
# ─────────────────────────────────────────────────────────────────────────
def parse_report(path):
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    meta = detect_report(path, soup)
    rec = {**meta, "file": os.path.basename(path)}

    # 커버
    rec["headline"] = txt_tight(soup.select_one(".cover-title"))
    rec["subhead"] = txt(soup.select_one(".cover-sub"))
    cover_meta = []
    for it in soup.select(".cover-meta-item"):
        cover_meta.append({"val": txt(it.select_one(".val")), "lbl": txt(it.select_one(".lbl"))})
    rec["cover_meta"] = cover_meta

    # 지표 (temp-card)
    indicators = []
    for c in soup.select(".temp-card"):
        indicators.append({
            "label": txt(c.select_one(".temp-label")),
            "value": txt(c.select_one(".temp-val")),
            "change": txt(c.select_one(".temp-chg")),
            "explain": txt(c.select_one(".temp-explain")),
        })
    rec["indicators"] = indicators

    # 게이지 (weekly)
    gauges = []
    for g in soup.select(".gauge-card"):
        gauges.append({
            "label": txt(g.select_one(".gauge-label")),
            "value": txt(g.select_one(".gauge-val")),
            "desc": txt(g.select_one(".gauge-desc")),
        })
    rec["gauges"] = gauges

    # 수급 테이블
    supply = []
    st = soup.select_one(".supply-table")
    if st:
        heads = [txt(th) for th in st.select("thead th")]
        for tr in st.select("tbody tr"):
            cells = [txt(td) for td in tr.select("td")]
            if cells:
                supply.append(dict(zip(heads, cells)) if heads and len(heads) == len(cells)
                               else {"cells": cells})
    rec["supply"] = supply

    # 타임라인
    timeline = []
    for it in soup.select(".tl-item"):
        tags = []
        for tg in it.select(".tl-tag"):
            cl = classes(tg)
            tone = "good" if "good" in cl else "bad" if "bad" in cl else "neutral"
            tags.append({"text": txt(tg), "tone": tone})
        timeline.append({
            "when": txt(it.select_one(".tl-date")),
            "title": txt(it.select_one(".tl-title")),
            "desc": txt(it.select_one(".tl-desc")),
            "tags": tags,
        })
    rec["timeline"] = timeline

    # 인사이트
    insights = []
    for card in soup.select(".insight-card"):
        bullets = []
        for li in card.select(".insight-bullets li"):
            cl = [c for c in classes(li)]
            bullets.append({"kind": (cl[0] if cl else ""), "text": txt(li)})
        keymsgs = []
        for kr in card.select(".key-message-box .key-row"):
            keymsgs.append({"title": txt(kr.select_one(".key-title")),
                            "desc": txt(kr.select_one(".key-desc"))})
        insights.append({
            "name": txt(card.select_one(".insight-name")),
            "role": txt(card.select_one(".insight-role")),
            "body": txt(card.select_one(".insight-body")),
            "quote": txt(card.select_one(".insight-quote")),
            "bullets": bullets,
            "key_messages": keymsgs,
        })
    rec["insights"] = insights

    # 섹터
    sectors = []
    for c in soup.select(".sector-card"):
        stocks = [txt(s) for s in c.select(".sector-stocks span")]
        sectors.append({
            "name": txt(c.select_one(".sector-name")),
            "sub": txt(c.select_one(".sector-name-sub")),
            "stocks": stocks,
            "note": txt(c.select_one(".sector-note")),
        })
    rec["sectors"] = sectors

    # 섹션별 라우팅: edu-card(reading vs glossary), check-item, strat/key-row(strategy vs next)
    readings, glossary, actions, strategy, nexts = [], [], [], [], []
    for sec in soup.select(".section"):
        kind = section_kind(txt(sec.select_one(".section-title")))
        for e in sec.select(".edu-card"):
            item = {"tag": txt(e.select_one(".edu-tag")),
                    "title": txt(e.select_one(".edu-title")),
                    "body": txt(e.select_one(".edu-body"))[:1600]}
            # 섹션 위치가 아니라 카드 유형으로 라우팅
            (glossary if card_is_glossary(item["tag"], item["title"]) else readings).append(item)
        for ci in sec.select(".check-item"):
            ic = ci.select_one(".check-icon")
            cl = classes(ic) if ic else set()
            kindc = "do" if "do" in cl else "dont" if "dont" in cl else "watch" if "watch" in cl else ""
            body = ci.find_all("div")
            actions.append({"kind": kindc, "text": txt(body[-1] if body else ci)})
        for sr in sec.select(".strat-row"):
            row = {"title": txt(sr.select_one(".strat-title")),
                   "desc": txt(sr.select_one(".strat-desc")),
                   "why": txt(sr.select_one(".strat-why"))}
            (nexts if kind == "next" else strategy).append(row)
        if kind == "next":
            for kr in sec.select(".key-message-box .key-row"):
                nexts.append({"title": txt(kr.select_one(".key-title")),
                              "desc": txt(kr.select_one(".key-desc")), "why": ""})
    rec["readings"], rec["glossary"] = readings, glossary
    rec["actions"], rec["strategy"], rec["next"] = actions, strategy, nexts

    # 인용구
    q = soup.select_one(".daily-quote, .weekly-quote")
    if q:
        rec["quote"] = {"text": txt(q.select_one("blockquote")),
                        "cite": txt(q.select_one("cite")),
                        "extra": txt(q.select_one("p"))}
    else:
        rec["quote"] = {}
    return rec

# ─────────────────────────────────────────────────────────────────────────
# 집계
# ─────────────────────────────────────────────────────────────────────────
def split_stock_token(span):
    """'SK하이닉스 (KB TP 380만)' → ('SK하이닉스', '(KB TP 380만)')
       'KODEX 레버리지' → ('KODEX 레버리지', '')  (ETF는 전체 유지)
       '삼성전자 HBM4E' → ('삼성전자', 'HBM4E')"""
    s = (span or "").strip()
    s = re.sub(r"^\s*(?:[①-⑩]|\d{1,2}[\.\)])\s*", "", s)   # 선두 순위번호(①/1./1)) 제거
    ann = ""
    mp = re.search(r"\(([^)]*)\)", s)
    if mp:
        ann = mp.group(0)
        s = (s[:mp.start()] + s[mp.end():]).strip()
    # 꼬리 수익률/등락 표기 분리 (+6.47%, -2.3%, ↑ 등)
    mperf = re.search(r"\s*[+\-]?\s*\d[\d\.]*\s*%.*$|\s*[↑↓➚➘]+.*$", s)
    if mperf:
        ann = (s[mperf.start():].strip() + " " + ann).strip()
        s = s[:mperf.start()].strip()
    up = s.upper()
    if any(up.startswith(b) for b in ETF_BRANDS):           # ETF: 전체 명칭 유지
        return s.strip(), ann
    parts = s.split(" ", 1)
    name = re.sub(r"\s*\d+$", "", parts[0]).strip()         # 'SK하이닉스 1' → 'SK하이닉스'
    extra = parts[1].strip() if len(parts) > 1 else ""
    annotation = " ".join(x for x in [extra, ann] if x).strip()
    return name, annotation

def aggregate(reports, window_days=31):
    reports = sorted(reports, key=lambda r: r["sort_date"])
    # 섹터·테마·종목·수급 = '최근 1개월' 윈도우만 집계. 전략·용어·시계열 = 전체.
    valid = [r["sort_date"] for r in reports if r.get("sort_date") and r["sort_date"] <= "9999"]
    recent, recent_from = reports, (reports[0]["sort_date"] if reports else "")
    if valid:
        try:
            max_d = max(datetime.date.fromisoformat(d) for d in valid)
            cutoff = (max_d - datetime.timedelta(days=window_days)).isoformat()
            recent = [r for r in reports if r.get("sort_date", "") >= cutoff]
            recent_from = cutoff
        except Exception:
            pass
    stocks = {}
    sectors = {}
    supply_days = []   # 날짜별 스마트머니 TOP
    for r in recent:
        label = r.get("date") or r.get("id")
        # 이혜나 대표님 발언 텍스트(인용·핵심메시지·불릿) — 섹터 가중 판정용
        rep_text = ""
        for _i in r["insights"]:
            if "이혜나" in _i.get("name", ""):
                rep_text += " " + (_i.get("quote") or "")
                rep_text += " " + " ".join((k.get("title","")+" "+k.get("desc","")) for k in _i.get("key_messages", []))
                rep_text += " " + " ".join((b.get("text") or "") for b in _i.get("bullets", []))
        rep_text = rep_text.lower()
        for sec in r["sectors"]:
            supply = is_supply_card(sec["name"])
            theme = sector_theme(sec["name"])
            if not supply:
                S = sectors.setdefault(theme, {"theme": theme, "names": set(), "mentions": [],
                                               "stocks": set(), "count": 0, "rep": 0})
                S["names"].add(sec["name"]); S["count"] += 1
                S["mentions"].append({"date": label, "rtype": r["type"], "id": r["id"],
                                      "name": sec["name"], "sub": sec["sub"],
                                      "stocks": sec["stocks"], "note": sec["note"]})
                # 대표님 직접 언급 가중: 섹터 노트에 대표님/이혜나 또는 대표님 발언에 테마 키워드
                note_l = sec["note"] or ""
                kws = THEME_KEYS.get(theme, (theme,))
                if ("대표님" in note_l) or ("이혜나" in note_l) or any(kw and kw.lower() in rep_text for kw in kws):
                    S["rep"] += 1
            else:
                supply_days.append({"date": label, "rtype": r["type"], "id": r["id"],
                                    "label": sec["name"], "who": supply_tag(sec["name"]),
                                    "stocks": sec["stocks"], "note": sec["note"]})
            for raw in sec["stocks"]:
                nm, ann = split_stock_token(raw)
                nm = normalize_stock(nm)
                if not nm or nm in STOCK_STOPWORDS or len(nm) < 2 or nm[0].isdigit():
                    continue   # 날짜·숫자 토큰(예: '27일') 제거
                T = stocks.setdefault(nm, {"name": nm, "mentions": [], "sectors": set(),
                                           "themes": set(), "supply_tags": set(),
                                           "targets": [], "count": 0,
                                           "theme_count": 0, "supply_count": 0})
                T["count"] += 1
                tp = parse_target_prices(raw)
                for t in tp:
                    t2 = dict(t); t2["date"] = label; t2["context"] = raw
                    T["targets"].append(t2)
                if supply:
                    T["supply_count"] += 1
                    T["supply_tags"].add(supply_tag(sec["name"]))
                    T["mentions"].append({"date": label, "rtype": r["type"], "id": r["id"],
                                          "source": "수급", "label": supply_tag(sec["name"]),
                                          "annotation": ann, "note": sec["note"][:160]})
                else:
                    T["theme_count"] += 1
                    T["sectors"].add(sec["name"]); T["themes"].add(theme)
                    S["stocks"].add(nm)
                    T["mentions"].append({"date": label, "rtype": r["type"], "id": r["id"],
                                          "source": "테마", "label": sec["name"], "theme": theme,
                                          "annotation": ann, "note": sec["note"][:200]})
    # set → list
    for S in sectors.values():
        S["names"] = sorted(S["names"]); S["stocks"] = sorted(S["stocks"])
    for T in stocks.values():
        T["sectors"] = sorted(T["sectors"]); T["themes"] = sorted(T["themes"])
        T["supply_tags"] = sorted(T["supply_tags"])
        # 목표가 중복 제거
        seen = set(); uniq = []
        for t in T["targets"]:
            k = (t["value"], t["unit"], t["date"])
            if k not in seen:
                seen.add(k); uniq.append(t)
        T["targets"] = uniq

    # ── 팀 스탠스 변화 타임라인 (이혜나 대표님 중심) ──
    stance = []
    for r in reports:
        rep = next((i for i in r["insights"] if "이혜나" in i["name"]), None)
        if not rep and r["insights"]:
            rep = r["insights"][0]
        stance.append({
            "date": r.get("date") or r.get("id"),
            "rtype": r["type"], "id": r["id"], "weekday": r.get("weekday", ""),
            "headline": r["headline"], "subhead": r["subhead"],
            "name": rep["name"] if rep else "",
            "quote": rep["quote"] if rep else "",
            "points": [k["title"] for k in (rep["key_messages"] if rep else [])][:4] or
                      [b["text"][:80] for b in (rep["bullets"] if rep else [])][:4],
            "report_quote": r["quote"].get("text", ""),
        })

    # ── 살아있는 전략 원칙 ──
    principles = []
    for name, icon, keys in PRINCIPLE_BUCKETS:
        occ = []
        for r in reports:
            label = r.get("date") or r.get("id")
            pool = []
            pool += [(a["text"], "체크리스트") for a in r["actions"]]
            pool += [(s["title"] + " — " + s["desc"], "주간전략") for s in r["strategy"]]
            pool += [(i["quote"], "대표님") for i in r["insights"] if i["quote"]]
            pool += [(k["title"] + " — " + k["desc"], "핵심메시지")
                     for i in r["insights"] for k in i["key_messages"]]
            for text, src in pool:
                if text and any(k in text for k in keys):
                    occ.append({"date": label, "rtype": r["type"], "id": r["id"],
                                "text": text[:200], "source": src})
        if occ:
            # 날짜 중복 정리
            seen = set(); uniq = []
            for o in occ:
                k = (o["date"], o["text"][:40])
                if k not in seen:
                    seen.add(k); uniq.append(o)
            principles.append({"principle": name, "icon": icon, "count": len(uniq),
                               "last_seen": max(o["date"] for o in uniq),
                               "occurrences": uniq})
    principles.sort(key=lambda p: (-p["count"], p["last_seen"]), reverse=False)
    principles.sort(key=lambda p: p["count"], reverse=True)

    # ── 용어집 (교육성 카드 전체 누적, 같은 용어 재등장 시 최신본으로 갱신) ──
    glossary = {}
    for r in reports:   # 전체 기간 누적
        for g in r["glossary"]:
            term = (g.get("title") or "").strip()
            if not term:
                continue
            glossary[term] = {"term": term, "tag": g.get("tag", ""),
                              "body": g["body"], "date": r.get("date") or r.get("id"),
                              "id": r["id"]}

    # ── 이벤트/촉매 (참고용) ──
    events = []
    for r in reports:
        for n in r["next"]:
            events.append({"title": n["title"], "desc": n["desc"],
                           "seen": r.get("date") or r.get("id"), "id": r["id"]})

    # ── 지표 시계열 (데일리) — 라벨 표준화, 하루 1값 ──
    EXC = ("선물", "인버스", "레버리지", "저점", "거래대금")
    CANON = [
        ("코스피", lambda n: "코스피" in n and "코스닥" not in n and not any(x in n for x in EXC)),
        ("코스닥", lambda n: "코스닥" in n and not any(x in n for x in EXC)),
        ("원/달러", lambda n: "원/달러" in n or "환율" in n),
        ("WTI 유가", lambda n: "WTI" in n or "유가" in n),
        ("나스닥", lambda n: "나스닥" in n),
        ("美 10년물 금리", lambda n: "10년물" in n and ("美" in n or "미" in n)),
    ]
    series = {k: [] for k, _ in CANON}
    for r in reports:
        if r["type"] != "daily":
            continue
        for canon, match in CANON:
            for ind in r["indicators"]:
                if not match(ind["label"]):
                    continue
                if "%" in (ind["value"] or ""):     # 등락률(%) 값은 종가 레벨이 아님 → 제외
                    continue
                v = parse_num(ind["value"])
                if v is not None:
                    series[canon].append({"date": r["date"], "value": v, "change": ind["change"]})
                    break
    series = {k: v for k, v in series.items() if v}

    return {
        "stocks": sorted(stocks.values(), key=lambda x: (-x["count"], x["name"])),
        "sectors": sorted(sectors.values(), key=lambda x: -x["count"]),
        "supply_days": supply_days,
        "recent_from": recent_from,
        "recent_reports": len(recent),
        "window_days": window_days,
        "stance": stance,
        "principles": principles,
        "glossary": sorted(glossary.values(), key=lambda x: x["date"], reverse=True),
        "events": events,
        "series": {k: v for k, v in series.items()},
    }

# ─────────────────────────────────────────────────────────────────────────
# 검색 인덱스
# ─────────────────────────────────────────────────────────────────────────
def build_search(reports, agg):
    idx = []
    def add(kind, title, snippet, date, rid, tags=None, extra=None):
        idx.append({"kind": kind, "title": title or "", "snippet": (snippet or "")[:300],
                    "date": date or "", "id": rid or "", "tags": tags or [], "extra": extra or {}})
    for r in reports:
        label = r.get("date") or r.get("id")
        for t in r["timeline"]:
            add("타임라인", t["title"], t["desc"], label, r["id"],
                [x["text"] for x in t["tags"]])
        for i in r["insights"]:
            if i["quote"]:
                add("인사이트", i["name"], i["quote"], label, r["id"], [i["role"]])
            for k in i["key_messages"]:
                add("핵심메시지", k["title"], k["desc"], label, r["id"], [i["name"]])
        for rd in r["readings"]:
            add("리서치/자료", rd["title"], rd["body"], label, r["id"], [rd["tag"]])
        for s in r["sectors"]:
            add("섹터", s["name"], s["note"], label, r["id"], s["stocks"])
    for st in agg["stocks"]:
        add("종목", st["name"], "; ".join(m["annotation"] for m in st["mentions"] if m["annotation"])[:300],
            st["mentions"][-1]["date"] if st["mentions"] else "", "",
            st["themes"], {"count": st["count"]})
    for g in agg["glossary"]:
        add("용어", g["term"], g["body"], g["date"], g["id"], [g["tag"]])
    for p in agg["principles"]:
        add("전략원칙", p["principle"], "; ".join(o["text"] for o in p["occurrences"][:3]),
            p["last_seen"], "", [], {"count": p["count"]})
    return idx

# ─────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────
REPORT_RE = re.compile(r"(?:^\d{4}[-.]\d{2}[-.]\d{2}\.html$)|(?:^\d{4}-W\d{1,2}\.html$)"
                       r"|(?:프롬어스.*\d{4}[-.]\d{2}[-.]\d{2}.*\.html$)", re.I)

def discover(src):
    found = []
    for root, _dirs, files in os.walk(src):
        # 산출물/숨김 폴더 제외
        if any(seg in root for seg in (os.sep + ".git", os.sep + "node_modules")):
            continue
        for fn in files:
            base = os.path.basename(fn)
            if base in ("hub.html", "index.html", "dashboard.html", "dashboard-glass.html"):
                continue
            if base.startswith("report_"):
                continue
            if REPORT_RE.match(base):
                found.append(os.path.join(root, fn))
    return sorted(found)

# ─────────────────────────────────────────────────────────────────────────
# 아카이브 index.html 에 '지식 허브' 버튼 주입 (build_index.py 미수정, 안전)
# ─────────────────────────────────────────────────────────────────────────
HUB_BTN_CSS = ("\n.hub-btn{display:inline-block;margin-top:22px;padding:11px 24px;"
               "border:1px solid var(--gold-border);border-radius:100px;background:var(--gold-bg);"
               "color:var(--gold);text-decoration:none;font-size:14px;font-weight:600;"
               "transition:all .2s ease}\n"
               ".hub-btn:hover{background:var(--gold);color:#fff;transform:translateY(-1px);"
               "box-shadow:0 4px 14px rgba(184,134,11,.2)}\n")
HUB_BTN_HTML = '\n  <a href="hub.html" class="hub-btn">📊 지식 허브 — 검색·섹터·종목·전략 →</a>'

def inject_hub_button(index_path):
    if not os.path.exists(index_path):
        print(f"ℹ️ index.html 없음({index_path}) — 허브 버튼 주입 생략")
        return
    with open(index_path, encoding="utf-8") as f:
        html = f.read()
    if "hub-btn" in html:
        return  # 이미 주입됨
    changed = False
    if "</style>" in html:
        html = html.replace("</style>", HUB_BTN_CSS + "</style>", 1); changed = True
    m = re.search(r'(<p class="header-sub">.*?</p>)', html, re.S)
    if m:
        html = html[:m.end()] + HUB_BTN_HTML + html[m.end():]; changed = True
    if changed:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"→ {index_path} 에 지식 허브 버튼 주입 완료")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".", help="리포트 탐색 루트 폴더")
    ap.add_argument("--files", nargs="*", help="명시적 파일 목록(선택)")
    ap.add_argument("--out", default="hub.html", help="허브 출력 파일")
    ap.add_argument("--json", default="knowledge_base.json", help="구조화 데이터 출력")
    ap.add_argument("--template", default=None, help="허브 템플릿 경로(기본: 스크립트 옆 hub_template.html)")
    ap.add_argument("--index", default=None, help="아카이브 index.html 경로(허브 버튼 주입 대상)")
    args = ap.parse_args()

    files = args.files if args.files else discover(args.src)
    if not files:
        sys.exit(f"리포트를 찾지 못했습니다 (src={args.src}). 파일명 규칙을 확인하세요.")
    print(f"발견한 리포트 {len(files)}개:")
    reports = []
    for p in files:
        try:
            rec = parse_report(p)
            rec["file"] = os.path.relpath(p, args.src).replace(os.sep, "/")  # 원문 링크용 상대경로
            reports.append(rec)
            print(f"  ✓ {rec['file']}")
        except Exception as e:
            print(f"  ✗ {os.path.basename(p)}  ({e})")
    reports.sort(key=lambda r: r["sort_date"])
    agg = aggregate(reports)
    search = build_search(reports, agg)

    daily = [r for r in reports if r["type"] == "daily"]
    weekly = [r for r in reports if r["type"] == "weekly"]
    data = {
        "build": {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                  "reports": len(reports), "daily": len(daily), "weekly": len(weekly),
                  "from": daily[0]["date"] if daily else (reports[0]["id"] if reports else ""),
                  "to": daily[-1]["date"] if daily else (reports[-1]["id"] if reports else ""),
                  "recent_from": agg.get("recent_from", ""), "recent_reports": agg.get("recent_reports", 0)},
        "reports": reports, "search": search, **agg,
    }
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"\n→ {args.json} 작성 ({os.path.getsize(args.json)//1024} KB)")

    tpl = args.template or os.path.join(os.path.dirname(os.path.abspath(__file__)), "hub_template.html")
    if os.path.exists(tpl):
        with open(tpl, encoding="utf-8") as f:
            shell = f.read()
        payload = json.dumps(data, ensure_ascii=False)
        # /*DATA*/ ... /*ENDDATA*/ 사이를 재빌드 가능하게 치환
        new_block = "/*DATA*/" + payload + "/*ENDDATA*/"
        if "/*DATA*/" in shell and "/*ENDDATA*/" in shell:
            shell = re.sub(r"/\*DATA\*/.*?/\*ENDDATA\*/", lambda _m: new_block, shell,
                           count=1, flags=re.S)
        else:
            sys.exit("템플릿에 /*DATA*/ … /*ENDDATA*/ 마커가 없습니다.")
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(shell)
        print(f"→ {args.out} 빌드 완료 ({os.path.getsize(args.out)//1024} KB)")
    else:
        print(f"⚠ 템플릿 없음({tpl}) — JSON만 생성했습니다.")

    # 아카이브 index.html 에 허브 버튼 주입
    index_path = args.index or os.path.join(os.path.dirname(args.out) or ".", "index.html")
    inject_hub_button(index_path)

    # 요약
    print(f"\n[요약] 종목 {len(agg['stocks'])}(최근 {agg.get('recent_reports','?')}개 리포트) · "
          f"섹터테마 {len(agg['sectors'])} · 스탠스 {len(agg['stance'])} · 원칙 {len(agg['principles'])} · "
          f"용어 {len(agg['glossary'])} · 검색항목 {len(search)} · 최근기준 {agg.get('recent_from','?')}~")

if __name__ == "__main__":
    main()
