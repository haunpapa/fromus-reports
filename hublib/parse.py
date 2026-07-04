# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 리포트 HTML 파싱·정규화."""
import datetime, os, re, sys
from hublib.config import ETF_BRANDS, SECTOR_THEME, STOCK_ALIASES, WEEKDAY_KR, _today_kst


try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("BeautifulSoup4 가 필요합니다:  pip install beautifulsoup4 lxml")

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

_KNOWN_STOCKS = set(STOCK_ALIASES.values())

def expand_stock_names(nm):
    """'현대차·기아' 처럼 알려진 종목들이 '·'로 묶인 복합 표기를 개별 종목으로 분리."""
    if "·" in nm:
        parts = [normalize_stock(p.strip()) for p in nm.split("·") if p.strip()]
        if len(parts) >= 2 and all(p in _KNOWN_STOCKS for p in parts):
            return parts
    return [nm]

def sector_theme(name):
    low = name.lower()
    for keys, theme in SECTOR_THEME:
        if any(k in low for k in keys):
            return theme
    return name.strip()

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
            year = int(my.group(1)) if my else _today_kst().year
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
    return True

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
    # 꼬리 금액 표기 분리 ('KODEX 레버리지 2,284억' → 'KODEX 레버리지' + '2,284억')
    mamt = re.search(r"\s*[+\-]?\d[\d,\.]*\s*(?:조|억|만)\s*원?\s*$", s)
    if mamt:
        ann = (s[mamt.start():].strip() + " " + ann).strip()
        s = s[:mamt.start()].strip()
    up = s.upper()
    if any(up.startswith(b) for b in ETF_BRANDS):           # ETF: 전체 명칭 유지
        return s.strip(), ann
    parts = s.split(" ", 1)
    name = re.sub(r"\s*\d+$", "", parts[0]).strip()         # 'SK하이닉스 1' → 'SK하이닉스'
    extra = parts[1].strip() if len(parts) > 1 else ""
    annotation = " ".join(x for x in [extra, ann] if x).strip()
    return name, annotation

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
