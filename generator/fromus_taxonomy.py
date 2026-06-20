# -*- coding: utf-8 -*-
"""프롬어스 통합 Taxonomy = 허브 정규화(build_hub) + 채팅 엔티티 병합."""
import re

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

STOCK_ALIASES.update({
    "micron": "마이크론", "sandisk": "샌디스크", "dell": "델", "d-wave": "디웨이브",
    "dwave": "디웨이브", "nvidia": "엔비디아", "tesla": "테슬라", "google": "구글",
    "oracle": "오라클", "palantir": "팔란티어",
})

STOCK_ALIASES.update({
    "포스코홀딩스": "POSCO홀딩스", "naver": "네이버", "ionq": "아이온큐",
    "rigetti": "리게티", "kai": "한국항공우주", "한올바이오파": "한올바이오파마",
})

STOCK_STOPWORDS = {
    "등", "외", "관련주", "부품주", "수혜주", "테마", "생태계", "공급망",
    "반도체", "바이오", "로봇", "소프트웨어", "우주항공", "2차전지", "이차전지",
    "양자컴퓨터", "증권주", "방산", "조선", "채권", "보험", "은행", "원전",
    "메모리", "HBM", "ESS", "AI", "ETF", "코스피", "코스닥",
    "자동차", "제약", "엔터", "은", "silver", "차전지", "헬스케어", "금융",
    "음식료", "화학", "철강", "건설", "유통", "운송",
}

STOCK_STOPWORDS.update({
    "IT서비스", "전기·전자", "운송장비·부품", "전력", "통신", "지수", "시장",
    "대만", "브라질", "한국", "미국", "중국", "일본", "유럽", "인도",
    "미국채", "휴머노이드", "대형주", "중소형주", "기타",
})

ETF_BRANDS = ("KODEX", "TIGER", "KBSTAR", "ARIRANG", "PLUS", "SOL", "ACE",
              "RISE", "KOSEF", "TIMEFOLIO", "HANARO", "KIWOOM", "WON")

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
    (("은(", "은銀", "안전자산", "원자재", "구리", "우라늄", "희토류",
      "골드", "귀금속", "금값", "금 비중", "금 etf", "금etf", "금 가격"), "원자재·안전자산"),
    (("삼성그룹", "삼성그룹 동반"), "삼성그룹"),
    # ── 채팅 자산/섹터 보강 테마 (오분류 방지를 위해 다의어가 아닌 명시 키워드만) ──
    (("코인", "가상자산", "암호화폐", "비트코인", "이더리움", "스테이블코인", "btc"), "가상자산·디지털자산"),
    (("국제유가", "원유", "wti", "브렌트유", "유가 상승", "유가 하락", "정유사", "opec", "셰일"), "에너지·정유"),
    (("전기차", "자율주행", "로보택시", "fsd", "옵티머스"), "전기차·자율주행"),
    (("k팝", "케이팝", "아이돌", "앨범 판매", "엔터주", "넷플릭스"), "엔터·미디어"),
    (("k푸드", "음식료", "라면 수출", "불닭"), "K푸드·소비재"),
]

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

def normalize_stock(name):
    n = (name or "").strip()
    key = n.lower().replace(" ", "")
    return STOCK_ALIASES.get(key, n)

def sector_theme(name):
    low = (name or "").lower()
    for keys, theme in SECTOR_THEME:
        if any(k in low for k in keys):
            return theme
    return (name or "").strip()

def expand_stock_names(nm):
    """'현대차·기아' 처럼 알려진 종목들이 '·'로 묶인 복합 표기를 개별 종목으로 분리."""
    if "·" in nm:
        parts = [normalize_stock(p.strip()) for p in nm.split("·") if p.strip()]
        if len(parts) >= 2 and all(p in _KNOWN_STOCKS for p in parts):
            return parts
    return [nm]

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

def parse_target_prices(s):
    """문자열에서 목표가/콜 스니펫 추출."""
    out = []
    for m in re.finditer(r"(?:목표(?:주)?가|TP)\s*[:\-]?\s*([0-9][0-9,\.]*)\s*(만원|만|달러|원|\$)?", s, re.I):
        val = m.group(1).replace(",", "")
        unit = m.group(2) or ""
        out.append({"value": val, "unit": unit, "raw": m.group(0).strip()})
    # "(KB TP 380만)" 형태의 출처 포함
    return out

# ===== 채팅 온톨로지 엔티티 병합 =====
_CANON_ALIGN={'알파벳': '구글', '포스코홀딩스': 'POSCO홀딩스'}
_MY_ENTITIES={'삼성전자': {'m': 'KR', 'tk': '005930', 'sec': '반도체', 'al': ['삼성전자']}, 'SK하이닉스': {'m': 'KR', 'tk': '000660', 'sec': '반도체', 'al': ['SK하이닉스', '하이닉스']}, '한미반도체': {'m': 'KR', 'tk': '042700', 'sec': '반도체장비', 'al': ['한미반도체']}, '삼성전기': {'m': 'KR', 'tk': '009150', 'sec': '전자부품', 'al': ['삼성전기']}, '리노공업': {'m': 'KR', 'tk': '058470', 'sec': '반도체장비', 'al': ['리노공업']}, '주성엔지니어링': {'m': 'KR', 'tk': '036930', 'sec': '반도체장비', 'al': ['주성엔지니어링']}, '원익IPS': {'m': 'KR', 'tk': '240810', 'sec': '반도체장비', 'al': ['원익IPS']}, 'HPSP': {'m': 'KR', 'tk': '403870', 'sec': '반도체장비', 'al': ['HPSP']}, '두산에너빌리티': {'m': 'KR', 'tk': '034020', 'sec': '전력/원전', 'al': ['두산에너빌리티']}, '효성중공업': {'m': 'KR', 'tk': '298040', 'sec': '전력인프라', 'al': ['효성중공업']}, 'LS일렉트릭': {'m': 'KR', 'tk': '010120', 'sec': '전력인프라', 'al': ['LS일렉트릭', 'LS ELECTRIC']}, '산일전기': {'m': 'KR', 'tk': '062040', 'sec': '전력인프라', 'al': ['산일전기']}, '제룡전기': {'m': 'KR', 'tk': '033100', 'sec': '전력인프라', 'al': ['제룡전기']}, 'HD현대일렉트릭': {'m': 'KR', 'tk': '267260', 'sec': '전력인프라', 'al': ['HD현대일렉트릭', '현대일렉트릭', 'HD현대일렉']}, '대한전선': {'m': 'KR', 'tk': '001440', 'sec': '전선', 'al': ['대한전선']}, '한화에어로스페이스': {'m': 'KR', 'tk': '012450', 'sec': '방산', 'al': ['한화에어로스페이스', '한화에어로']}, '한화오션': {'m': 'KR', 'tk': '042660', 'sec': '조선/방산', 'al': ['한화오션']}, '한화시스템': {'m': 'KR', 'tk': '272210', 'sec': '방산', 'al': ['한화시스템']}, '현대로템': {'m': 'KR', 'tk': '064350', 'sec': '방산/철도', 'al': ['현대로템']}, 'LIG넥스원': {'m': 'KR', 'tk': '079550', 'sec': '방산', 'al': ['LIG넥스원', 'LIG넥스', '넥스원']}, '한국항공우주': {'m': 'KR', 'tk': '047810', 'sec': '방산/우주', 'al': ['한국항공우주', 'KAI']}, 'HD현대중공업': {'m': 'KR', 'tk': '329180', 'sec': '조선', 'al': ['HD현대중공업']}, '삼성중공업': {'m': 'KR', 'tk': '010140', 'sec': '조선', 'al': ['삼성중공업']}, 'HD현대미포': {'m': 'KR', 'tk': '010620', 'sec': '조선', 'al': ['HD현대미포', '현대미포']}, '두산로보틱스': {'m': 'KR', 'tk': '454910', 'sec': '로봇', 'al': ['두산로보틱스']}, '레인보우로보틱스': {'m': 'KR', 'tk': '277810', 'sec': '로봇', 'al': ['레인보우로보틱스', '레인보우로보']}, '두산밥캣': {'m': 'KR', 'tk': '241560', 'sec': '기계', 'al': ['두산밥캣']}, 'LG에너지솔루션': {'m': 'KR', 'tk': '373220', 'sec': '2차전지', 'al': ['LG에너지솔루션', '엘지에너지솔루션', 'LG엔솔']}, '삼성SDI': {'m': 'KR', 'tk': '006400', 'sec': '2차전지', 'al': ['삼성SDI']}, '엘앤에프': {'m': 'KR', 'tk': '066970', 'sec': '2차전지소재', 'al': ['엘앤에프']}, '에코프로비엠': {'m': 'KR', 'tk': '247540', 'sec': '2차전지소재', 'al': ['에코프로비엠']}, '포스코홀딩스': {'m': 'KR', 'tk': '005490', 'sec': '소재/2차전지', 'al': ['포스코홀딩스']}, '포스코퓨처엠': {'m': 'KR', 'tk': '003670', 'sec': '2차전지소재', 'al': ['포스코퓨처엠']}, '네이버': {'m': 'KR', 'tk': '035420', 'sec': '플랫폼', 'al': ['네이버', 'NAVER']}, '카카오': {'m': 'KR', 'tk': '035720', 'sec': '플랫폼', 'al': ['카카오뱅크', '카카오페이', '카카오']}, '하이브': {'m': 'KR', 'tk': '352820', 'sec': '엔터', 'al': ['하이브']}, '에스엠': {'m': 'KR', 'tk': '041510', 'sec': '엔터', 'al': ['에스엠엔터', 'SM엔터']}, '삼성바이오로직스': {'m': 'KR', 'tk': '207940', 'sec': '바이오', 'al': ['삼성바이오로직스', '삼성바이오']}, '알테오젠': {'m': 'KR', 'tk': '196170', 'sec': '바이오', 'al': ['알테오젠']}, 'SK스퀘어': {'m': 'KR', 'tk': '402340', 'sec': '반도체/지주', 'al': ['SK스퀘어']}, '삼양식품': {'m': 'KR', 'tk': '003230', 'sec': 'K푸드', 'al': ['삼양식품']}, '엔비디아': {'m': 'US', 'tk': 'NVDA', 'sec': 'AI반도체', 'al': ['엔비디아', 'NVIDIA', '엔디비아', '엔비디아', '$NVDA', 'NVDA']}, '테슬라': {'m': 'US', 'tk': 'TSLA', 'sec': '전기차/AI', 'al': ['테슬라', '$TSLA', 'TSLA']}, '마이크론': {'m': 'US', 'tk': 'MU', 'sec': '메모리', 'al': ['마이크론', '$MU', 'MU']}, '애플': {'m': 'US', 'tk': 'AAPL', 'sec': '빅테크', 'al': ['애플', '$AAPL', 'AAPL']}, '알파벳': {'m': 'US', 'tk': 'GOOGL', 'sec': '빅테크', 'al': ['알파벳', '구글', '$GOOGL', 'GOOGL', 'GOOG']}, '아마존': {'m': 'US', 'tk': 'AMZN', 'sec': '빅테크', 'al': ['아마존', '$AMZN', 'AMZN']}, '메타': {'m': 'US', 'tk': 'META', 'sec': '빅테크', 'al': ['메타플랫폼', '$META']}, '마이크로소프트': {'m': 'US', 'tk': 'MSFT', 'sec': '빅테크', 'al': ['마이크로소프트', '마소', '$MSFT', 'MSFT']}, '브로드컴': {'m': 'US', 'tk': 'AVGO', 'sec': 'AI반도체', 'al': ['브로드컴', '$AVGO', 'AVGO']}, 'AMD': {'m': 'US', 'tk': 'AMD', 'sec': 'AI반도체', 'al': ['$AMD', ' AMD', 'AMD ']}, 'ASML': {'m': 'US', 'tk': 'ASML', 'sec': '반도체장비', 'al': ['ASML']}, 'TSMC': {'m': 'US', 'tk': 'TSM', 'sec': '파운드리', 'al': ['TSMC', '$TSM', '대만 반도체']}, '팔란티어': {'m': 'US', 'tk': 'PLTR', 'sec': 'AI소프트', 'al': ['팔란티어', '$PLTR', 'PLTR']}, '오라클': {'m': 'US', 'tk': 'ORCL', 'sec': '클라우드', 'al': ['오라클', '$ORCL', 'ORCL']}, '코인베이스': {'m': 'US', 'tk': 'COIN', 'sec': '가상자산', 'al': ['코인베이스', '$COIN']}, '로빈후드': {'m': 'US', 'tk': 'HOOD', 'sec': '핀테크', 'al': ['로빈후드', '$HOOD', 'HOOD']}, '오클로': {'m': 'US', 'tk': 'OKLO', 'sec': 'SMR/원전', 'al': ['오클로', '$OKLO', 'OKLO']}, '뉴스케일': {'m': 'US', 'tk': 'SMR', 'sec': 'SMR/원전', 'al': ['뉴스케일', '$SMR']}, '넷플릭스': {'m': 'US', 'tk': 'NFLX', 'sec': '미디어', 'al': ['넷플릭스', '$NFLX', 'NFLX']}, '샌디스크': {'m': 'US', 'tk': 'SNDK', 'sec': '메모리', 'al': ['샌디스크', '$SNDK', 'SNDK']}, '인텔': {'m': 'US', 'tk': 'INTC', 'sec': '반도체', 'al': ['인텔', '$INTC', 'INTC']}, '퀄컴': {'m': 'US', 'tk': 'QCOM', 'sec': '반도체', 'al': ['퀄컴', '$QCOM', 'QCOM']}, 'MP머티리얼즈': {'m': 'US', 'tk': 'MP', 'sec': '희토류', 'al': ['MP머티리얼즈', 'MP머티리얼']}, '코어위브': {'m': 'US', 'tk': 'CRWV', 'sec': 'AI인프라', 'al': ['코어위브', '$CRWV', 'CRWV']}, '버티브': {'m': 'US', 'tk': 'VRT', 'sec': '데이터센터', 'al': ['버티브']}, '나비우스': {'m': 'US', 'tk': 'NBIS', 'sec': 'AI인프라', 'al': ['나비우스', '$NBIS', 'NBIS']}, '로켓랩': {'m': 'US', 'tk': 'RKLB', 'sec': '우주', 'al': ['로켓랩', '$RKLB', 'RKLB']}, '비트코인': {'m': 'ASSET', 'tk': 'BTC', 'sec': '가상자산', 'al': ['비트코인', 'BTC']}, '이더리움': {'m': 'ASSET', 'tk': 'ETH', 'sec': '가상자산', 'al': ['이더리움', 'ETH']}, '금(Gold)': {'m': 'ASSET', 'tk': 'GOLD', 'sec': '귀금속', 'al': ['금값', '금 ETF', '금ETF', '금 현물', '금 비중', '금 가격', '골드', '금 투자', '금 매수']}, '우라늄': {'m': 'ASSET', 'tk': 'U', 'sec': '원전연료', 'al': ['우라늄']}, '구리(Copper)': {'m': 'ASSET', 'tk': 'CU', 'sec': '산업금속', 'al': ['구리값', '구리 가격', '구리 수요', '구리 ETF']}, '원유/유가': {'m': 'ASSET', 'tk': 'OIL', 'sec': '에너지', 'al': ['국제유가', 'WTI', '브렌트유', '유가 상승', '유가 하락', '원유 재고']}}
_MY_THEMES={'AI': ['AI', '인공지능', '에이아이'], '반도체': ['반도체'], 'HBM/메모리': ['HBM', '메모리', 'D램', 'DRAM', '낸드', 'NAND'], '파운드리': ['파운드리'], '전력인프라': ['전력망', '전력 인프라', '송전', '변압기', '전선', '그리드', '전력기기'], '원전/SMR': ['원전', 'SMR', '원자력', '소형모듈원전'], '방산': ['방산', '방위산업', '무기'], '조선': ['조선', '선박', '수주'], '2차전지': ['2차전지', '배터리', '양극재', '음극재'], '로봇/휴머노이드': ['로봇', '휴머노이드'], '우주/위성': ['우주', '위성', '발사체'], '바이오/제약': ['바이오', '제약', '비만치료제', '신약'], '데이터센터': ['데이터센터', 'IDC'], '자율주행': ['자율주행', '로보택시'], '희토류': ['희토류'], '스테이블코인': ['스테이블코인'], '가상자산': ['코인', '가상자산', '암호화폐'], 'K푸드': ['K푸드', '음식료', '라면 수출'], '엔터': ['엔터주', 'K팝', '앨범 판매'], '금리/매크로': ['금리 인하', '금리 인상', '연준', 'FOMC', '파월'], '환율': ['환율', '원달러', '달러 강세'], '관세/무역': ['관세', '무역전쟁', '리쇼어링']}
for _c,_i in _MY_ENTITIES.items():
    _cn=_CANON_ALIGN.get(_c,_c)
    for _a in _i["al"]:
        _k=_a.lower().replace(" ","")
        if len(_k)>=2 and _k not in STOCK_ALIASES: STOCK_ALIASES[_k]=_cn
_KNOWN_STOCKS=set(STOCK_ALIASES.values())
STOCK_META={_CANON_ALIGN.get(_c,_c):{"market":_i["m"],"ticker":_i["tk"],"sector":_i["sec"]} for _c,_i in _MY_ENTITIES.items()}
_STOP_NORM={s.lower().replace(" ","") for s in STOCK_STOPWORDS}
# 표면형 별칭(원문 탐색용)
_ALIAS_SURFACE={}
for _c,_i in _MY_ENTITIES.items():
    for _a in _i["al"]:
        if len(_a)>=2: _ALIAS_SURFACE[_a]=_CANON_ALIGN.get(_c,_c)
for _v in set(STOCK_ALIASES.values()):
    if len(_v)>=2: _ALIAS_SURFACE.setdefault(_v,_v)

# ── 경계 인식 매칭(substring 오탐 방지) ──
# ASCII 표면형(AMD/ETH/BTC/KAI/MU/btc 등)은 영숫자 단어경계를 요구해
# AMDOCS·ETHERNET·GBTC·KAIST 류 오탐을 막는다.
# 한글 접두 충돌(메타→메타버스, 골드→골드만, 코인→코인노래방, 전기차→전기차단기)은 부정문맥으로 배제.
def _is_ascii(s): return all(ord(c) < 128 for c in s)
def _ascii_alnum(ch): return ch.isalnum() and ord(ch) < 128
_NEG_NEXT = {
    "메타": ("버스", "데이터", "인지", "물질"),  # 메타버스/메타데이터/메타인지
    "골드": ("만",),                              # 골드만삭스
    "코인": ("노래방",),                          # 코인노래방
    "전기차": ("단기",),                          # 전기차단기
}
def _surf_in(text, surf):
    """경계 인식 포함 검사. ASCII는 영숫자 경계, 한글은 _NEG_NEXT 부정문맥 배제."""
    if not surf or not text: return False
    ascii_s = _is_ascii(surf); neg = () if ascii_s else _NEG_NEXT.get(surf, ())
    L = len(surf); i = text.find(surf)
    while i >= 0:
        if ascii_s:
            b = text[i-1] if i > 0 else ""
            a = text[i+L] if i+L < len(text) else ""
            if not (b and _ascii_alnum(b)) and not (a and _ascii_alnum(a)): return True
        else:
            nxt = text[i+L:i+L+4]
            if not any(nxt.startswith(n) for n in neg): return True
        i = text.find(surf, i+1)
    return False

def match_stocks(text):
    text = text or ""
    out=set()
    for surf,canon in _ALIAS_SURFACE.items():
        if canon in STOCK_STOPWORDS or len(canon)<2: continue
        if _surf_in(text, surf): out.add(canon)
    return out
def match_themes(text):
    low=(text or "").lower(); out=set()
    for keys,theme in SECTOR_THEME:
        if any(_surf_in(low,k) for k in keys): out.add(theme)
    return out
def principle_hits(text):
    return [(lbl,emo) for lbl,emo,kws in PRINCIPLE_BUCKETS if any(k in text for k in kws)]

# ===== 종목 대표 테마(오분류 방지) =====
# 종목 고유 섹터(STOCK_META.sector) → 허브 표준 테마. 키워드 우연 매칭이 아니라
# 종목 정체성에 따라 #1 테마를 확정한다.
SECTOR_TO_THEME = {
    "반도체": "반도체·메모리", "AI반도체": "반도체·메모리", "메모리": "반도체·메모리",
    "반도체장비": "반도체·메모리", "파운드리": "반도체·메모리", "반도체/지주": "반도체·메모리",
    "전자부품": "반도체·메모리",
    "전력/원전": "AI 전력·원전·ESS", "전력인프라": "AI 전력·원전·ESS", "전선": "AI 전력·원전·ESS",
    "SMR/원전": "AI 전력·원전·ESS", "원전연료": "AI 전력·원전·ESS", "데이터센터": "AI 전력·원전·ESS",
    "방산": "조선·방산", "조선": "조선·방산", "조선/방산": "조선·방산",
    "방산/철도": "조선·방산", "방산/우주": "조선·방산",
    "로봇": "로봇·피지컬AI", "기계": "로봇·피지컬AI",
    "2차전지": "2차전지", "2차전지소재": "2차전지", "소재/2차전지": "2차전지",
    "플랫폼": "소프트웨어·AI", "빅테크": "소프트웨어·AI", "AI소프트": "소프트웨어·AI",
    "클라우드": "소프트웨어·AI", "AI인프라": "소프트웨어·AI",
    "바이오": "바이오·제약",
    "엔터": "엔터·미디어", "미디어": "엔터·미디어",
    "전기차/AI": "전기차·자율주행",
    "가상자산": "가상자산·디지털자산",
    "핀테크": "증권·자본시장",
    "우주": "우주항공·위성",
    "희토류": "원자재·안전자산", "산업금속": "원자재·안전자산", "귀금속": "원자재·안전자산",
    "에너지": "에너지·정유",
    "K푸드": "K푸드·소비재",
}

def primary_theme(canon):
    """종목 표준명 → 대표 테마. 매핑이 없으면 키워드 추론, 그래도 없으면 '' 반환."""
    meta = STOCK_META.get(canon)
    if not meta:
        return ""
    sec = meta.get("sector", "")
    if sec in SECTOR_TO_THEME:
        return SECTOR_TO_THEME[sec]
    t = sector_theme(sec)
    return t if t != sec else ""

# canon → 표면형(별칭) 목록 (근접도 게이팅용)
from collections import defaultdict as _dd
_CANON_SURFACES = _dd(list)
for _surf, _canon in _ALIAS_SURFACE.items():
    _CANON_SURFACES[_canon].append(_surf)

def match_themes_for_stock(text, canon, window=36):
    """본문에서 해당 종목 표면형 주변(±window자) 안의 테마만 반환.
       종목과 무관한 메시지 전반의 동시출현 노이즈를 차단한다.
       표면형 위치도 경계 인식으로 잡아 오탐(AMDOCS 등) 주변 윈도우를 만들지 않는다."""
    low = (text or "").lower()
    surfaces = _CANON_SURFACES.get(canon) or [canon]
    hits = set()
    for surf in surfaces:
        sl = surf.lower()
        ascii_s = _is_ascii(surf)
        neg = () if ascii_s else _NEG_NEXT.get(surf, ())
        L = len(sl)
        start = 0
        while True:
            i = low.find(sl, start)
            if i < 0:
                break
            if ascii_s:
                b = low[i-1] if i > 0 else ""
                a = low[i+L] if i+L < len(low) else ""
                ok = not (b and _ascii_alnum(b)) and not (a and _ascii_alnum(a))
            else:
                ok = not any(low[i+L:i+L+4].startswith(n) for n in neg)
            if ok:
                seg = low[max(0, i - window): i + L + window]
                for keys, theme in SECTOR_THEME:
                    if any(_surf_in(seg, k) for k in keys):
                        hits.add(theme)
            start = i + L
    return hits
