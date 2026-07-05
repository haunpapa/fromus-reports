#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
프롬어스 카톡 온톨로지 — 일일 자동 업데이트 (로컬 실행용 · 자체완결)
─────────────────────────────────────────────────────────────────
새 카카오톡 내보내기(.txt)를 이 폴더에 넣고 실행하면:
  파싱 → 링크추출 → 제목매칭 → 네이버해제(캐시) → 투자전략 → 온톨로지 → HTML 뷰어
까지 전부 다시 생성합니다.
  · 이미 해제한 네이버 링크는 resolve_cache.json 에 저장 → 다음엔 '새 링크만' 접속(빠름)
  · 결과물: 프롬어스_온톨로지_뷰어.html, 뉴스_전체아카이브.csv
사용:  python update_archive.py           (최신 .txt 자동 선택)
       python update_archive.py --no-resolve   (네트워크 해제 건너뛰기)
"""
import os, re, sys, csv, json, time, glob, base64
import datetime
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit, parse_qsl, urlencode
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
try:
    import requests; _SESS=requests.Session()
except Exception:
    requests=None; _SESS=None
import urllib.request

BASE=os.path.dirname(os.path.abspath(__file__))
def P(*a): return os.path.join(BASE,*a)

# ===== 주입되는 상수(빌드시 치환) =====
ENTITIES={'삼성전자': {'m': 'KR', 'tk': '005930', 'sec': '반도체', 'al': ['삼성전자']}, 'SK하이닉스': {'m': 'KR', 'tk': '000660', 'sec': '반도체', 'al': ['SK하이닉스', '하이닉스']}, '한미반도체': {'m': 'KR', 'tk': '042700', 'sec': '반도체장비', 'al': ['한미반도체']}, '삼성전기': {'m': 'KR', 'tk': '009150', 'sec': '전자부품', 'al': ['삼성전기']}, '리노공업': {'m': 'KR', 'tk': '058470', 'sec': '반도체장비', 'al': ['리노공업']}, '주성엔지니어링': {'m': 'KR', 'tk': '036930', 'sec': '반도체장비', 'al': ['주성엔지니어링']}, '원익IPS': {'m': 'KR', 'tk': '240810', 'sec': '반도체장비', 'al': ['원익IPS']}, 'HPSP': {'m': 'KR', 'tk': '403870', 'sec': '반도체장비', 'al': ['HPSP']}, '두산에너빌리티': {'m': 'KR', 'tk': '034020', 'sec': '전력/원전', 'al': ['두산에너빌리티']}, '효성중공업': {'m': 'KR', 'tk': '298040', 'sec': '전력인프라', 'al': ['효성중공업']}, 'LS일렉트릭': {'m': 'KR', 'tk': '010120', 'sec': '전력인프라', 'al': ['LS일렉트릭', 'LS ELECTRIC']}, '산일전기': {'m': 'KR', 'tk': '062040', 'sec': '전력인프라', 'al': ['산일전기']}, '제룡전기': {'m': 'KR', 'tk': '033100', 'sec': '전력인프라', 'al': ['제룡전기']}, 'HD현대일렉트릭': {'m': 'KR', 'tk': '267260', 'sec': '전력인프라', 'al': ['HD현대일렉트릭', '현대일렉트릭', 'HD현대일렉']}, '대한전선': {'m': 'KR', 'tk': '001440', 'sec': '전선', 'al': ['대한전선']}, '한화에어로스페이스': {'m': 'KR', 'tk': '012450', 'sec': '방산', 'al': ['한화에어로스페이스', '한화에어로']}, '한화오션': {'m': 'KR', 'tk': '042660', 'sec': '조선/방산', 'al': ['한화오션']}, '한화시스템': {'m': 'KR', 'tk': '272210', 'sec': '방산', 'al': ['한화시스템']}, '현대로템': {'m': 'KR', 'tk': '064350', 'sec': '방산/철도', 'al': ['현대로템']}, 'LIG넥스원': {'m': 'KR', 'tk': '079550', 'sec': '방산', 'al': ['LIG넥스원', 'LIG넥스', '넥스원']}, '한국항공우주': {'m': 'KR', 'tk': '047810', 'sec': '방산/우주', 'al': ['한국항공우주', 'KAI']}, 'HD현대중공업': {'m': 'KR', 'tk': '329180', 'sec': '조선', 'al': ['HD현대중공업']}, '삼성중공업': {'m': 'KR', 'tk': '010140', 'sec': '조선', 'al': ['삼성중공업']}, 'HD현대미포': {'m': 'KR', 'tk': '010620', 'sec': '조선', 'al': ['HD현대미포', '현대미포']}, '두산로보틱스': {'m': 'KR', 'tk': '454910', 'sec': '로봇', 'al': ['두산로보틱스']}, '레인보우로보틱스': {'m': 'KR', 'tk': '277810', 'sec': '로봇', 'al': ['레인보우로보틱스', '레인보우로보']}, '두산밥캣': {'m': 'KR', 'tk': '241560', 'sec': '기계', 'al': ['두산밥캣']}, 'LG에너지솔루션': {'m': 'KR', 'tk': '373220', 'sec': '2차전지', 'al': ['LG에너지솔루션', '엘지에너지솔루션', 'LG엔솔']}, '삼성SDI': {'m': 'KR', 'tk': '006400', 'sec': '2차전지', 'al': ['삼성SDI']}, '엘앤에프': {'m': 'KR', 'tk': '066970', 'sec': '2차전지소재', 'al': ['엘앤에프']}, '에코프로비엠': {'m': 'KR', 'tk': '247540', 'sec': '2차전지소재', 'al': ['에코프로비엠']}, '포스코홀딩스': {'m': 'KR', 'tk': '005490', 'sec': '소재/2차전지', 'al': ['포스코홀딩스']}, '포스코퓨처엠': {'m': 'KR', 'tk': '003670', 'sec': '2차전지소재', 'al': ['포스코퓨처엠']}, '네이버': {'m': 'KR', 'tk': '035420', 'sec': '플랫폼', 'al': ['네이버', 'NAVER']}, '카카오': {'m': 'KR', 'tk': '035720', 'sec': '플랫폼', 'al': ['카카오뱅크', '카카오페이', '카카오']}, '하이브': {'m': 'KR', 'tk': '352820', 'sec': '엔터', 'al': ['하이브']}, '에스엠': {'m': 'KR', 'tk': '041510', 'sec': '엔터', 'al': ['에스엠엔터', 'SM엔터']}, '삼성바이오로직스': {'m': 'KR', 'tk': '207940', 'sec': '바이오', 'al': ['삼성바이오로직스', '삼성바이오']}, '알테오젠': {'m': 'KR', 'tk': '196170', 'sec': '바이오', 'al': ['알테오젠']}, 'SK스퀘어': {'m': 'KR', 'tk': '402340', 'sec': '반도체/지주', 'al': ['SK스퀘어']}, '삼양식품': {'m': 'KR', 'tk': '003230', 'sec': 'K푸드', 'al': ['삼양식품']}, '엔비디아': {'m': 'US', 'tk': 'NVDA', 'sec': 'AI반도체', 'al': ['엔비디아', 'NVIDIA', '엔디비아', '엔비디아', '$NVDA', 'NVDA']}, '테슬라': {'m': 'US', 'tk': 'TSLA', 'sec': '전기차/AI', 'al': ['테슬라', '$TSLA', 'TSLA']}, '마이크론': {'m': 'US', 'tk': 'MU', 'sec': '메모리', 'al': ['마이크론', '$MU', 'MU']}, '애플': {'m': 'US', 'tk': 'AAPL', 'sec': '빅테크', 'al': ['애플', '$AAPL', 'AAPL']}, '알파벳': {'m': 'US', 'tk': 'GOOGL', 'sec': '빅테크', 'al': ['알파벳', '구글', '$GOOGL', 'GOOGL', 'GOOG']}, '아마존': {'m': 'US', 'tk': 'AMZN', 'sec': '빅테크', 'al': ['아마존', '$AMZN', 'AMZN']}, '메타': {'m': 'US', 'tk': 'META', 'sec': '빅테크', 'al': ['메타플랫폼', '$META']}, '마이크로소프트': {'m': 'US', 'tk': 'MSFT', 'sec': '빅테크', 'al': ['마이크로소프트', '마소', '$MSFT', 'MSFT']}, '브로드컴': {'m': 'US', 'tk': 'AVGO', 'sec': 'AI반도체', 'al': ['브로드컴', '$AVGO', 'AVGO']}, 'AMD': {'m': 'US', 'tk': 'AMD', 'sec': 'AI반도체', 'al': ['$AMD', ' AMD', 'AMD ']}, 'ASML': {'m': 'US', 'tk': 'ASML', 'sec': '반도체장비', 'al': ['ASML']}, 'TSMC': {'m': 'US', 'tk': 'TSM', 'sec': '파운드리', 'al': ['TSMC', '$TSM', '대만 반도체']}, '팔란티어': {'m': 'US', 'tk': 'PLTR', 'sec': 'AI소프트', 'al': ['팔란티어', '$PLTR', 'PLTR']}, '오라클': {'m': 'US', 'tk': 'ORCL', 'sec': '클라우드', 'al': ['오라클', '$ORCL', 'ORCL']}, '코인베이스': {'m': 'US', 'tk': 'COIN', 'sec': '가상자산', 'al': ['코인베이스', '$COIN']}, '로빈후드': {'m': 'US', 'tk': 'HOOD', 'sec': '핀테크', 'al': ['로빈후드', '$HOOD', 'HOOD']}, '오클로': {'m': 'US', 'tk': 'OKLO', 'sec': 'SMR/원전', 'al': ['오클로', '$OKLO', 'OKLO']}, '뉴스케일': {'m': 'US', 'tk': 'SMR', 'sec': 'SMR/원전', 'al': ['뉴스케일', '$SMR']}, '넷플릭스': {'m': 'US', 'tk': 'NFLX', 'sec': '미디어', 'al': ['넷플릭스', '$NFLX', 'NFLX']}, '샌디스크': {'m': 'US', 'tk': 'SNDK', 'sec': '메모리', 'al': ['샌디스크', '$SNDK', 'SNDK']}, '인텔': {'m': 'US', 'tk': 'INTC', 'sec': '반도체', 'al': ['인텔', '$INTC', 'INTC']}, '퀄컴': {'m': 'US', 'tk': 'QCOM', 'sec': '반도체', 'al': ['퀄컴', '$QCOM', 'QCOM']}, 'MP머티리얼즈': {'m': 'US', 'tk': 'MP', 'sec': '희토류', 'al': ['MP머티리얼즈', 'MP머티리얼']}, '코어위브': {'m': 'US', 'tk': 'CRWV', 'sec': 'AI인프라', 'al': ['코어위브', '$CRWV', 'CRWV']}, '버티브': {'m': 'US', 'tk': 'VRT', 'sec': '데이터센터', 'al': ['버티브']}, '나비우스': {'m': 'US', 'tk': 'NBIS', 'sec': 'AI인프라', 'al': ['나비우스', '$NBIS', 'NBIS']}, '로켓랩': {'m': 'US', 'tk': 'RKLB', 'sec': '우주', 'al': ['로켓랩', '$RKLB', 'RKLB']}, '비트코인': {'m': 'ASSET', 'tk': 'BTC', 'sec': '가상자산', 'al': ['비트코인', 'BTC']}, '이더리움': {'m': 'ASSET', 'tk': 'ETH', 'sec': '가상자산', 'al': ['이더리움', 'ETH']}, '금(Gold)': {'m': 'ASSET', 'tk': 'GOLD', 'sec': '귀금속', 'al': ['금값', '금 ETF', '금ETF', '금 현물', '금 비중', '금 가격', '골드', '금 투자', '금 매수']}, '우라늄': {'m': 'ASSET', 'tk': 'U', 'sec': '원전연료', 'al': ['우라늄']}, '구리(Copper)': {'m': 'ASSET', 'tk': 'CU', 'sec': '산업금속', 'al': ['구리값', '구리 가격', '구리 수요', '구리 ETF']}, '원유/유가': {'m': 'ASSET', 'tk': 'OIL', 'sec': '에너지', 'al': ['국제유가', 'WTI', '브렌트유', '유가 상승', '유가 하락', '원유 재고']}}
THEMES={'AI': ['AI', '인공지능', '에이아이'], '반도체': ['반도체'], 'HBM/메모리': ['HBM', '메모리', 'D램', 'DRAM', '낸드', 'NAND'], '파운드리': ['파운드리'], '전력인프라': ['전력망', '전력 인프라', '송전', '변압기', '전선', '그리드', '전력기기'], '원전/SMR': ['원전', 'SMR', '원자력', '소형모듈원전'], '방산': ['방산', '방위산업', '무기'], '조선': ['조선', '선박', '수주'], '2차전지': ['2차전지', '배터리', '양극재', '음극재'], '로봇/휴머노이드': ['로봇', '휴머노이드'], '우주/위성': ['우주', '위성', '발사체'], '바이오/제약': ['바이오', '제약', '비만치료제', '신약'], '데이터센터': ['데이터센터', 'IDC'], '자율주행': ['자율주행', '로보택시'], '희토류': ['희토류'], '스테이블코인': ['스테이블코인'], '가상자산': ['코인', '가상자산', '암호화폐'], 'K푸드': ['K푸드', '음식료', '라면 수출'], '엔터': ['엔터주', 'K팝', '앨범 판매'], '금리/매크로': ['금리 인하', '금리 인상', '연준', 'FOMC', '파월'], '환율': ['환율', '원달러', '달러 강세'], '관세/무역': ['관세', '무역전쟁', '리쇼어링']}
NAVER_OID={'001': '연합뉴스', '002': '프레시안', '003': '뉴시스', '005': '국민일보', '008': '머니투데이', '009': '매일경제', '011': '서울경제', '014': '파이낸셜뉴스', '015': '한국경제', '016': '헤럴드경제', '018': '이데일리', '020': '동아일보', '021': '문화일보', '023': '조선일보', '025': '중앙일보', '028': '한겨레', '029': '디지털타임스', '030': '전자신문', '031': '아이뉴스24', '032': '경향신문', '050': '한국경제매거진', '052': 'YTN', '055': 'SBS', '056': 'KBS', '057': 'MBN', '079': '노컷뉴스', '081': '서울신문', '088': '매일신문', '092': '지디넷코리아', '119': '데일리안', '138': '디지털데일리', '214': 'MBC', '215': '한국경제TV', '243': '이코노미스트', '277': '아시아경제', '293': '블로터', '366': '조선비즈', '374': 'SBS Biz', '421': '뉴스1', '422': '연합뉴스', '437': '오마이뉴스', '448': 'TV조선', '449': '채널A', '469': '한국일보', '640': '코리아중앙데일리', '648': '비즈워치', '655': '시사IN', '658': '중앙SUNDAY', '665': '한경비즈니스'}
CSS=base64.b64decode("Kntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQo6cm9vdHsKICAtLWJnOiNlZWYxZjU7IC0tY2FyZDojZmZmOyAtLWluazojMTYyMDJlOyAtLW11dDojNjQ3NDhiOyAtLWxpbmU6I2UyZThmMDsKICAtLW5hdjojMGYxYjJkOyAtLW5hdjI6IzE2MjYzZDsgLS1hY2M6IzI1NjNlYjsgLS1hY2MyOiMxZDRlZDg7CiAgLS1idWxsOiMxNmEzNGE7IC0tYmVhcjojZGMyNjI2OyAtLXdhdGNoOiNkOTc3MDY7IC0tbmV1OiM2NDc0OGI7IC0tcmVzOiM3YzNhZWQ7Cn0KYm9keXtmb250LWZhbWlseToiUHJldGVuZGFyZCIsIkFwcGxlIFNEIEdvdGhpYyBOZW8iLCJNYWxndW4gR290aGljIixzeXN0ZW0tdWksc2Fucy1zZXJpZjsKICBiYWNrZ3JvdW5kOnZhcigtLWJnKTtjb2xvcjp2YXIoLS1pbmspO2xpbmUtaGVpZ2h0OjEuNTstd2Via2l0LWZvbnQtc21vb3RoaW5nOmFudGlhbGlhc2VkfQphe2NvbG9yOnZhcigtLWFjYyk7dGV4dC1kZWNvcmF0aW9uOm5vbmV9YTpob3Zlcnt0ZXh0LWRlY29yYXRpb246dW5kZXJsaW5lfQpoZWFkZXIudG9we2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDEyMGRlZyx2YXIoLS1uYXYpLHZhcigtLW5hdjIpKTtjb2xvcjojZmZmO3BhZGRpbmc6MjJweCAyNnB4IDB9CmhlYWRlci50b3AgLnQxe2ZvbnQtc2l6ZToxM3B4O2xldHRlci1zcGFjaW5nOjJweDtjb2xvcjojOWZiM2NjO2ZvbnQtd2VpZ2h0OjYwMH0KaGVhZGVyLnRvcCBoMXtmb250LXNpemU6MjRweDtmb250LXdlaWdodDo4MDA7bWFyZ2luOjNweCAwIDJweH0KaGVhZGVyLnRvcCAuc3Vie2NvbG9yOiNiOWM3ZGE7Zm9udC1zaXplOjEzcHg7bWFyZ2luLWJvdHRvbToxNHB4fQpuYXYudGFic3tkaXNwbGF5OmZsZXg7Z2FwOjJweDtmbGV4LXdyYXA6d3JhcH0KbmF2LnRhYnMgYnV0dG9ue2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7Ym9yZGVyOjA7Y29sb3I6I2FlYmZkNDtwYWRkaW5nOjExcHggMTZweDtmb250LXNpemU6MTRweDsKICBmb250LXdlaWdodDo3MDA7Y3Vyc29yOnBvaW50ZXI7Ym9yZGVyLWJvdHRvbTozcHggc29saWQgdHJhbnNwYXJlbnQ7Zm9udC1mYW1pbHk6aW5oZXJpdH0KbmF2LnRhYnMgYnV0dG9uOmhvdmVye2NvbG9yOiNmZmZ9Cm5hdi50YWJzIGJ1dHRvbi5vbntjb2xvcjojZmZmO2JvcmRlci1ib3R0b20tY29sb3I6IzViOWRmZn0KbWFpbnttYXgtd2lkdGg6MTI0MHB4O21hcmdpbjowIGF1dG87cGFkZGluZzoyMnB4fQouc2VjdGlvbntkaXNwbGF5Om5vbmV9LnNlY3Rpb24ub257ZGlzcGxheTpibG9jazthbmltYXRpb246ZmFkZSAuMjVzfQpAa2V5ZnJhbWVzIGZhZGV7ZnJvbXtvcGFjaXR5OjA7dHJhbnNmb3JtOnRyYW5zbGF0ZVkoNHB4KX10b3tvcGFjaXR5OjE7dHJhbnNmb3JtOm5vbmV9fQouY2FyZHN7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoYXV0by1maXQsbWlubWF4KDE1MHB4LDFmcikpO2dhcDoxMnB4O21hcmdpbi1ib3R0b206MThweH0KLnN0YXR7YmFja2dyb3VuZDp2YXIoLS1jYXJkKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTRweDtwYWRkaW5nOjE1cHggMTZweH0KLnN0YXQgLm57Zm9udC1zaXplOjI2cHg7Zm9udC13ZWlnaHQ6ODAwO2xldHRlci1zcGFjaW5nOi0uNXB4fQouc3RhdCAubHtmb250LXNpemU6MTIuNXB4O2NvbG9yOnZhcigtLW11dCk7bWFyZ2luLXRvcDoycHg7Zm9udC13ZWlnaHQ6NjAwfQouc3RhdCAuc3tmb250LXNpemU6MTFweDtjb2xvcjojOTRhM2I4O21hcmdpbi10b3A6NHB4fQoucGFuZWx7YmFja2dyb3VuZDp2YXIoLS1jYXJkKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTRweDtwYWRkaW5nOjE4cHg7bWFyZ2luLWJvdHRvbToxOHB4fQoucGFuZWwgaDJ7Zm9udC1zaXplOjE1cHg7Zm9udC13ZWlnaHQ6ODAwO21hcmdpbi1ib3R0b206MnB4fQoucGFuZWwgLmRlc2N7Zm9udC1zaXplOjEyLjVweDtjb2xvcjp2YXIoLS1tdXQpO21hcmdpbi1ib3R0b206MTRweH0KLmdyaWQye2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6MThweH0KQG1lZGlhKG1heC13aWR0aDo4NjBweCl7LmdyaWQye2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9fQouYmFyLXJvd3tkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxMHB4O21hcmdpbjo2cHggMDtmb250LXNpemU6MTNweH0KLmJhci1yb3cgLmxhYnt3aWR0aDoxMjBweDtmbGV4Om5vbmU7Zm9udC13ZWlnaHQ6NjAwO3doaXRlLXNwYWNlOm5vd3JhcDtvdmVyZmxvdzpoaWRkZW47dGV4dC1vdmVyZmxvdzplbGxpcHNpc30KLmJhci1yb3cgLnRyYWNre2ZsZXg6MTtiYWNrZ3JvdW5kOiNlZWYyZjc7Ym9yZGVyLXJhZGl1czo2cHg7aGVpZ2h0OjE2cHg7b3ZlcmZsb3c6aGlkZGVufQouYmFyLXJvdyAuZmlsbHtoZWlnaHQ6MTAwJTtib3JkZXItcmFkaXVzOjZweDtiYWNrZ3JvdW5kOnZhcigtLWFjYyl9Ci5iYXItcm93IC52e3dpZHRoOjQ2cHg7dGV4dC1hbGlnbjpyaWdodDtjb2xvcjp2YXIoLS1tdXQpO2ZvbnQtdmFyaWFudC1udW1lcmljOnRhYnVsYXItbnVtc30KLmNvbnRyb2xze2Rpc3BsYXk6ZmxleDtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwO2FsaWduLWl0ZW1zOmNlbnRlcjttYXJnaW4tYm90dG9tOjEycHh9Ci5jb250cm9scyBpbnB1dCwuY29udHJvbHMgc2VsZWN0e2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC1zaXplOjEzcHg7cGFkZGluZzo4cHggMTBweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpOwogIGJvcmRlci1yYWRpdXM6OXB4O2JhY2tncm91bmQ6I2ZmZjtjb2xvcjp2YXIoLS1pbmspfQouY29udHJvbHMgaW5wdXRbdHlwZT1zZWFyY2hde21pbi13aWR0aDoyMDBweDtmbGV4OjF9Ci5jaGlwe2ZvbnQtc2l6ZToxMXB4O2ZvbnQtd2VpZ2h0OjcwMDtwYWRkaW5nOjJweCA4cHg7Ym9yZGVyLXJhZGl1czoyMHB4O3doaXRlLXNwYWNlOm5vd3JhcH0KLmMtbmV3c3tiYWNrZ3JvdW5kOiNlMGVkZmY7Y29sb3I6IzFkNGVkOH0uYy1icm9rZXJfcmVwb3J0e2JhY2tncm91bmQ6I2VkZTlmZTtjb2xvcjojNmQyOGQ5fQouYy12aWRlb3tiYWNrZ3JvdW5kOiNmZWUyZTI7Y29sb3I6I2I5MWMxY30uYy1zb2NpYWx7YmFja2dyb3VuZDojZmNlN2YzO2NvbG9yOiNiZTE4NWR9Ci5jLWJsb2d7YmFja2dyb3VuZDojZGNmY2U3O2NvbG9yOiMxNTgwM2R9LmMtbWVzc2VuZ2Vye2JhY2tncm91bmQ6I2NmZmFmZTtjb2xvcjojMGU3NDkwfQouYy1kb2MsLmMtZGF0YSwuYy1kaXNjbG9zdXJle2JhY2tncm91bmQ6I2YxZjVmOTtjb2xvcjojNDc1NTY5fS5jLWludGVybmFsLC5jLXBlcnNvbmFsLC5jLWZvcm0sLmMtY29tbXVuaXR5LC5jLXNob3J0ZW5lciwuYy1vdGhlcntiYWNrZ3JvdW5kOiNmMWY1Zjk7Y29sb3I6IzY0NzQ4Yn0KdGFibGV7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2U7Zm9udC1zaXplOjEzcHh9CnRoLHRke3RleHQtYWxpZ246bGVmdDtwYWRkaW5nOjhweCAxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO3ZlcnRpY2FsLWFsaWduOnRvcH0KdGh7Zm9udC1zaXplOjExLjVweDtjb2xvcjp2YXIoLS1tdXQpO2ZvbnQtd2VpZ2h0OjcwMDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6LjRweDtjdXJzb3I6cG9pbnRlcjt1c2VyLXNlbGVjdDpub25lO3Bvc2l0aW9uOnN0aWNreTt0b3A6MDtiYWNrZ3JvdW5kOiNmZmZ9CnRib2R5IHRyOmhvdmVye2JhY2tncm91bmQ6I2Y4ZmFmY30KdGQuY210e2NvbG9yOiMzMzQxNTU7bWF4LXdpZHRoOjQyMHB4fQoubXV0ZWR7Y29sb3I6dmFyKC0tbXV0KX0ubm93cmFwe3doaXRlLXNwYWNlOm5vd3JhcH0KLnBhZ2Vye2Rpc3BsYXk6ZmxleDtnYXA6NnB4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO21hcmdpbi10b3A6MTRweDtmb250LXNpemU6MTNweH0KLnBhZ2VyIGJ1dHRvbntib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JhY2tncm91bmQ6I2ZmZjtib3JkZXItcmFkaXVzOjhweDtwYWRkaW5nOjZweCAxMXB4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXR9Ci5wYWdlciBidXR0b246ZGlzYWJsZWR7b3BhY2l0eTouNDtjdXJzb3I6ZGVmYXVsdH0KLmxlYW57ZGlzcGxheTppbmxpbmUtYmxvY2s7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6ODAwO3BhZGRpbmc6MnB4IDdweDtib3JkZXItcmFkaXVzOjZweH0KLmxlYW4uYnVsbGlzaHtiYWNrZ3JvdW5kOiNkY2ZjZTc7Y29sb3I6IzE1ODAzZH0ubGVhbi5iZWFyaXNoe2JhY2tncm91bmQ6I2ZlZTJlMjtjb2xvcjojYjkxYzFjfQoubGVhbi53YXRjaHtiYWNrZ3JvdW5kOiNmZWYzYzc7Y29sb3I6I2I0NTMwOX0ubGVhbi5uZXV0cmFse2JhY2tncm91bmQ6I2YxZjVmOTtjb2xvcjojNDc1NTY5fS5sZWFuLm1peGVke2JhY2tncm91bmQ6I2UwZTdmZjtjb2xvcjojNDMzOGNhfQouc3RiYXJ7ZGlzcGxheTpmbGV4O2hlaWdodDoxNHB4O2JvcmRlci1yYWRpdXM6NXB4O292ZXJmbG93OmhpZGRlbjttaW4td2lkdGg6OTBweH0KLnN0YmFyIGl7ZGlzcGxheTpibG9ja30uc3RiYXIgLmJ7YmFja2dyb3VuZDp2YXIoLS1idWxsKX0uc3RiYXIgLnJ7YmFja2dyb3VuZDp2YXIoLS1iZWFyKX0uc3RiYXIgLnd7YmFja2dyb3VuZDp2YXIoLS13YXRjaCl9LnN0YmFyIC5ue2JhY2tncm91bmQ6I2NiZDVlMX0KLm1jYXJke2JhY2tncm91bmQ6dmFyKC0tY2FyZCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjE0cHg7cGFkZGluZzoxNnB4fQoubWdyaWR7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoYXV0by1maWxsLG1pbm1heCgyOTBweCwxZnIpKTtnYXA6MTRweH0KLm1jYXJkIC5ubXtmb250LXNpemU6MTZweDtmb250LXdlaWdodDo4MDB9Lm1jYXJkIC5yb3tmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1hY2MpO2ZvbnQtd2VpZ2h0OjcwMH0KLm1jYXJkIC5yb3d7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2ZvbnQtc2l6ZToxMi41cHg7bWFyZ2luOjNweCAwO2NvbG9yOiM0NzU1Njl9Ci50YWd7ZGlzcGxheTppbmxpbmUtYmxvY2s7YmFja2dyb3VuZDojZWVmMmY3O2NvbG9yOiM0NzU1Njk7Zm9udC1zaXplOjExcHg7Zm9udC13ZWlnaHQ6NjAwO3BhZGRpbmc6MnB4IDdweDtib3JkZXItcmFkaXVzOjZweDttYXJnaW46MnB4IDNweCAwIDB9Ci5zaWd7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoxMHB4IDB9Ci5zaWcgLm1ldGF7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0KTttYXJnaW4tYm90dG9tOjNweDtkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5zaWcgLndob3tmb250LXdlaWdodDo4MDA7Y29sb3I6dmFyKC0taW5rKX0KLnNpZyAuZW50c3tmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjMil9Ci5zaWcgLnR4e2ZvbnQtc2l6ZToxMy41cHg7Y29sb3I6IzFlMjkzYn0KLmxlZ2VuZHtkaXNwbGF5OmZsZXg7Z2FwOjE0cHg7ZmxleC13cmFwOndyYXA7Zm9udC1zaXplOjEycHg7Y29sb3I6IzQ3NTU2OTttYXJnaW4tYm90dG9tOjhweH0KLmxlZ2VuZCBpe2Rpc3BsYXk6aW5saW5lLWJsb2NrO3dpZHRoOjExcHg7aGVpZ2h0OjExcHg7Ym9yZGVyLXJhZGl1czozcHg7bWFyZ2luLXJpZ2h0OjRweDt2ZXJ0aWNhbC1hbGlnbjotMXB4fQpzdmcgLm5sYWJlbHtmb250LXNpemU6OXB4O2ZpbGw6IzMzNDE1NTtmb250LXdlaWdodDo2MDB9Ci5nd3JhcHt3aWR0aDoxMDAlO292ZXJmbG93OmF1dG87Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEycHg7YmFja2dyb3VuZDojZmJmY2ZlfQoubm90ZXtmb250LXNpemU6MTIuNXB4O2NvbG9yOiM0NzU1Njk7YmFja2dyb3VuZDojZjhmYWZjO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLWxlZnQ6M3B4IHNvbGlkIHZhcigtLWFjYyk7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzoxMXB4IDEzcHg7bWFyZ2luOjEwcHggMH0KLnNjaGVtYS1ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmcjtnYXA6MTBweH0KQG1lZGlhKG1heC13aWR0aDo3NjBweCl7LnNjaGVtYS1ncmlke2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9LmNhcmRzIC5zdGF0IC5ue2ZvbnQtc2l6ZToyMnB4fX0KLmt2e2Rpc3BsYXk6ZmxleDtnYXA6OHB4O2ZvbnQtc2l6ZToxM3B4O3BhZGRpbmc6NXB4IDA7Ym9yZGVyLWJvdHRvbToxcHggZGFzaGVkIHZhcigtLWxpbmUpfQoua3YgYnttaW4td2lkdGg6MTMwcHg7Y29sb3I6dmFyKC0tbXV0KTtmb250LXdlaWdodDo3MDB9Ci5mb290e2NvbG9yOiM5NGEzYjg7Zm9udC1zaXplOjEycHg7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzoyNHB4fQo=").decode("utf-8")
JS=base64.b64decode("Y29uc3QgJD0ocyxlPWRvY3VtZW50KT0+ZS5xdWVyeVNlbGVjdG9yKHMpOwpjb25zdCAkJD0ocyxlPWRvY3VtZW50KT0+Wy4uLmUucXVlcnlTZWxlY3RvckFsbChzKV07CmNvbnN0IGVzYz1zPT4ocz09bnVsbD8iIjoiIitzKS5yZXBsYWNlKC9bJjw+Il0vZyxjPT4oeycmJzonJmFtcDsnLCc8JzonJmx0OycsJz4nOicmZ3Q7JywnIic6JyZxdW90Oyd9W2NdKSk7CmNvbnN0IFBJPXY9PnBhcnNlSW50KHZ8fDAsMTApfHwwOwpjb25zdCBmbXROPW49PigrbikudG9Mb2NhbGVTdHJpbmcoJ2tvLUtSJyk7CmNvbnN0IEQ9REFUQTsKY29uc3QgU1RDT0w9e2J1bGxpc2g6JyMxNmEzNGEnLGJlYXJpc2g6JyNkYzI2MjYnLHdhdGNoOicjZDk3NzA2JyxuZXV0cmFsOicjOTRhM2I4JyxtaXhlZDonIzYzNjZmMSd9Owpjb25zdCBMRUFOS089e2J1bGxpc2g6J+qwleyEuCcsYmVhcmlzaDon7JW97IS4Jyx3YXRjaDon6rSA66edJyxuZXV0cmFsOifspJHrpr0nLG1peGVkOiftmLzsobAnfTsKY29uc3QgTUtUS089e0tSOifqta3rgrQnLFVTOifrr7jqta0nLEFTU0VUOifsnpDsgrAnfTsKCmNvbnN0IHJlbmRlcmVkPXt9Owpjb25zdCBSRU5ERVI9e307CmZ1bmN0aW9uIHNob3coaWQpewogICQkKCcuc2VjdGlvbicpLmZvckVhY2gocz0+cy5jbGFzc0xpc3QudG9nZ2xlKCdvbicscy5pZD09PWlkKSk7CiAgJCQoJ25hdi50YWJzIGJ1dHRvbicpLmZvckVhY2goYj0+Yi5jbGFzc0xpc3QudG9nZ2xlKCdvbicsYi5kYXRhc2V0LnQ9PT1pZCkpOwogIGlmKCFyZW5kZXJlZFtpZF0mJlJFTkRFUltpZF0pe1JFTkRFUltpZF0oKTtyZW5kZXJlZFtpZF09dHJ1ZTt9CiAgd2luZG93LnNjcm9sbFRvKDAsMCk7Cn0KZnVuY3Rpb24gYmFyUm93KGxhYix2YWwsbWF4LGNvbG9yLHN1ZmZpeCl7CiAgY29uc3Qgdz1tYXg/TWF0aC5tYXgoMixNYXRoLnJvdW5kKHZhbC9tYXgqMTAwKSk6MDsKICByZXR1cm4gYDxkaXYgY2xhc3M9ImJhci1yb3ciPjxkaXYgY2xhc3M9ImxhYiIgdGl0bGU9IiR7ZXNjKGxhYil9Ij4ke2VzYyhsYWIpfTwvZGl2PgogICA8ZGl2IGNsYXNzPSJ0cmFjayI+PGRpdiBjbGFzcz0iZmlsbCIgc3R5bGU9IndpZHRoOiR7d30lO2JhY2tncm91bmQ6JHtjb2xvcnx8J3ZhcigtLWFjYyknfSI+PC9kaXY+PC9kaXY+CiAgIDxkaXYgY2xhc3M9InYiPiR7Zm10Tih2YWwpfSR7c3VmZml4fHwnJ308L2Rpdj48L2Rpdj5gOwp9CmZ1bmN0aW9uIHN0YmFyKGIscix3LG4pewogIGNvbnN0IHQ9YityK3crbnx8MTtjb25zdCBwPXg9PngvdCoxMDA7CiAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJzdGJhciIgdGl0bGU9IuqwleyEuCAke2J9IMK3IOyVveyEuCAke3J9IMK3IOq0gOunnSAke3d9IMK3IOykkeumvSAke259Ij4KICAgPGkgY2xhc3M9ImIiIHN0eWxlPSJ3aWR0aDoke3AoYil9JSI+PC9pPjxpIGNsYXNzPSJyIiBzdHlsZT0id2lkdGg6JHtwKHIpfSUiPjwvaT4KICAgPGkgY2xhc3M9InciIHN0eWxlPSJ3aWR0aDoke3Aodyl9JSI+PC9pPjxpIGNsYXNzPSJuIiBzdHlsZT0id2lkdGg6JHtwKG4pfSUiPjwvaT48L2Rpdj5gOwp9CgovKiAtLS0tLS0tLS0tLS0tLS0tIE9WRVJWSUVXIC0tLS0tLS0tLS0tLS0tLS0gKi8KUkVOREVSLm92ZXJ2aWV3PSgpPT57CiAgY29uc3QgbT1ELm1ldGE7CiAgY29uc3QgY2FyZHM9WwogICAgWyfrqZTsi5zsp4AnLGZtdE4obS5tZXNzYWdlcyksbS5kYXRlX2Zyb20rJyB+ICcrbS5kYXRlX3RvXSwKICAgIFsn66mk67KEJyxmbXROKG0ubWVtYmVyc190b3RhbCksJ+2ZnOuPmSDtlbXsi6wgJyttLm1lbWJlcnNfY29yZSsn7J24J10sCiAgICBbJ+qzteycoCDrp4HtgawnLGZtdE4obS5saW5rc190b3RhbCksJ+uIhOudvSAwIMK3IOyghOyImCDrs7TsobQnXSwKICAgIFsn64m07IqkIOq4sOyCrCcsZm10TihtLm5ld3NfbGlua3MpLCcrIOymneq2jOumrO2PrO2KuCDrk7EnXSwKICAgIFsn6rCc7J24IOyghOuetSDsi5zqt7jrhJAnLGZtdE4obS5zdHJhdGVneV9wZXJzb25hbCksJ+2PrOyngOyFmMK36rSA7KCQJ10sCiAgICBbJ+qzteycoCDrpqzshJzsuZgv7Iuc7ZmpJyxmbXROKG0uc3RyYXRlZ3lfcmVzZWFyY2gpLCftjbzsmKgg7J6Q66OMJ10KICBdOwogICQoJyNvdi1jYXJkcycpLmlubmVySFRNTD1jYXJkcy5tYXAoYz0+YDxkaXYgY2xhc3M9InN0YXQiPjxkaXYgY2xhc3M9Im4iPiR7Y1sxXX08L2Rpdj4KICAgICA8ZGl2IGNsYXNzPSJsIj4ke2NbMF19PC9kaXY+PGRpdiBjbGFzcz0icyI+JHtlc2MoY1syXSl9PC9kaXY+PC9kaXY+YCkuam9pbignJyk7CiAgLy8gdGltZWxpbmUgc3ZnCiAgJCgnI292LXRpbWVsaW5lJykuaW5uZXJIVE1MPXRpbWVsaW5lU1ZHKEQudGltZWxpbmUpOwogIC8vIGNhdGVnb3JpZXMKICBjb25zdCBjYXQ9T2JqZWN0LmVudHJpZXMoRC5jYXRlZ29yaWVzKS5zb3J0KChhLGIpPT5iWzFdLWFbMV0pOwogIGNvbnN0IGNtYXg9Y2F0WzBdWzFdOwogIGNvbnN0IENBVEtPPXtuZXdzOifribTsiqQnLGJyb2tlcl9yZXBvcnQ6J+ymneq2jCDrpqztj6ztirgnLHZpZGVvOifsmIHsg4Eo7Jyg7Yqc67iMKScsc29jaWFsOidTTlMnLGJsb2c6J+u4lOuhnOq3uCcsCiAgICBtZXNzZW5nZXI6J+2FlOugiOq3uOueqCcsZG9jOifrrLjshJwnLGRhdGE6J+yLnOyEuC/rjbDsnbTthLAnLGRpc2Nsb3N1cmU6J+qzteyLnChEQVJUKScsaW50ZXJuYWw6J+uCtOu2gC/subTthqEnLAogICAgY29tbXVuaXR5Oifsu6TrrqTri4jti7AnLHNob3J0ZW5lcjon64uo7LaV66eB7YGsJyxmb3JtOifshKTrrLgnLHBlcnNvbmFsOifqsJzsnbjtjpjsnbTsp4AnLG90aGVyOifquLDtg4AnfTsKICAkKCcjb3YtY2F0cycpLmlubmVySFRNTD1jYXQubWFwKGM9PmJhclJvdyhDQVRLT1tjWzBdXXx8Y1swXSxjWzFdLGNtYXgsJyMzYjgyZjYnKSkuam9pbignJyk7CiAgLy8gb3V0bGV0cwogIGNvbnN0IG9tPUQub3V0bGV0c1swXS5jb3VudDsKICAkKCcjb3Ytb3V0bGV0cycpLmlubmVySFRNTD1ELm91dGxldHMuc2xpY2UoMCwxNSkubWFwKG89PmJhclJvdyhvLm91dGxldCxvLmNvdW50LG9tLCcjMGVhNWU5JykpLmpvaW4oJycpOwogIC8vIHRoZW1lcwogIGNvbnN0IHRoPUQudGhlbWVzLnNsaWNlKDAsMTIpO2NvbnN0IHRtPXRoWzBdLm1lbnRpb25zOwogICQoJyNvdi10aGVtZXMnKS5pbm5lckhUTUw9dGgubWFwKHQ9PmJhclJvdyh0LnRoZW1lLFBJKHQubWVudGlvbnMpLFBJKHRtKSwnIzhiNWNmNicpKS5qb2luKCcnKTsKfTsKZnVuY3Rpb24gdGltZWxpbmVTVkcodGwpewogIGNvbnN0IFc9MTEyMCxIPTE4MCxwYWQ9Mjg7CiAgY29uc3Qgbj10bC5sZW5ndGg7Y29uc3QgbWF4TT1NYXRoLm1heCguLi50bC5tYXAoZD0+ZC5tc2dzKSk7Y29uc3QgbWF4TD1NYXRoLm1heCguLi50bC5tYXAoZD0+ZC5saW5rcykpOwogIGNvbnN0IHg9aT0+cGFkK2kqKFctMipwYWQpLyhuLTEpOwogIGNvbnN0IHlNPXY9PkgtcGFkLSh2L21heE0pKihILTIqcGFkKTsKICBjb25zdCB5TD12PT5ILXBhZC0odi9tYXhMKSooSC0yKnBhZCk7CiAgbGV0IGFyZWE9J00nK3goMCkrJywnKyhILXBhZCk7dGwuZm9yRWFjaCgoZCxpKT0+YXJlYSs9JyBMJyt4KGkpLnRvRml4ZWQoMSkrJywnK3lNKGQubXNncykudG9GaXhlZCgxKSk7CiAgYXJlYSs9JyBMJyt4KG4tMSkrJywnKyhILXBhZCkrJyBaJzsKICBsZXQgbGluZT0nJzt0bC5mb3JFYWNoKChkLGkpPT5saW5lKz0oaT8nIEwnOidNJykreChpKS50b0ZpeGVkKDEpKycsJyt5TChkLmxpbmtzKS50b0ZpeGVkKDEpKTsKICAvLyBtb250aCB0aWNrcwogIGxldCB0aWNrcz0nJztsZXQgbGFzdE09Jyc7CiAgdGwuZm9yRWFjaCgoZCxpKT0+e2NvbnN0IG1vPWQuZGF0ZS5zbGljZSgwLDcpO2lmKG1vIT09bGFzdE0pe2xhc3RNPW1vOwogICAgdGlja3MrPWA8bGluZSB4MT0iJHt4KGkpfSIgeTE9IiR7cGFkLTZ9IiB4Mj0iJHt4KGkpfSIgeTI9IiR7SC1wYWR9IiBzdHJva2U9IiNlMmU4ZjAiLz4KICAgICAgPHRleHQgeD0iJHt4KGkpKzN9IiB5PSIke3BhZCsyfSIgZm9udC1zaXplPSIxMCIgZmlsbD0iIzk0YTNiOCI+JHtkLmRhdGUuc2xpY2UoMCw3KX08L3RleHQ+YDt9fSk7CiAgcmV0dXJuIGA8c3ZnIHZpZXdCb3g9IjAgMCAke1d9ICR7SH0iIHdpZHRoPSIxMDAlIiBwcmVzZXJ2ZUFzcGVjdFJhdGlvPSJ4TWlkWU1pZCBtZWV0Ij4KICAgICR7dGlja3N9CiAgICA8cGF0aCBkPSIke2FyZWF9IiBmaWxsPSJyZ2JhKDU5LDEzMCwyNDYsLjEzKSIvPgogICAgPHBhdGggZD0iJHtsaW5lfSIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjMGVhNWU5IiBzdHJva2Utd2lkdGg9IjEuOCIvPgogICAgPHRleHQgeD0iJHtwYWR9IiB5PSIke0gtOH0iIGZvbnQtc2l6ZT0iMTAiIGZpbGw9IiM5NGEzYjgiPuydvOuzhCDCtyDrqbTsoIE966mU7Iuc7KeAKOy1nOuMgCAke21heE19KSDCtyDtjIzrnoDshKA96rO17Jyg66eB7YGsKOy1nOuMgCAke21heEx9KTwvdGV4dD4KICA8L3N2Zz5gOwp9CgovKiAtLS0tLS0tLS0tLS0tLS0tIE5FV1MgQVJDSElWRSAtLS0tLS0tLS0tLS0tLS0tICovCmxldCBORVdTPXtyb3dzOltdLHBhZ2U6MCxzb3J0RGVzYzp0cnVlLHBlcjo1MH07ClJFTkRFUi5uZXdzPSgpPT57CiAgLy8gcG9wdWxhdGUgc2VsZWN0cwogIGNvbnN0IGNhdHM9Wy4uLm5ldyBTZXQoRC5uZXdzLm1hcChuPT5uLmMpKV07CiAgY29uc3QgQ0FUS089e25ld3M6J+uJtOyKpCcsYnJva2VyX3JlcG9ydDon7Kad6raMIOumrO2PrO2KuCcsdmlkZW86J+yYgeyDgScsc29jaWFsOidTTlMnLGJsb2c6J+u4lOuhnOq3uCcsbWVzc2VuZ2VyOifthZTroIjqt7jrnqgnLAogICAgZG9jOifrrLjshJwnLGRhdGE6J+yLnOyEuC/rjbDsnbTthLAnLGRpc2Nsb3N1cmU6J+qzteyLnCcsaW50ZXJuYWw6J+uCtOu2gCcsY29tbXVuaXR5Oifsu6TrrqTri4jti7AnLHNob3J0ZW5lcjon64uo7LaV66eB7YGsJywKICAgIGZvcm06J+yEpOusuCcscGVyc29uYWw6J+qwnOyduCcsb3RoZXI6J+q4sO2DgCd9OwogICQoJyNuZi1jYXQnKS5pbm5lckhUTUw9JzxvcHRpb24gdmFsdWU9IiI+67aE66WYIOyghOyytDwvb3B0aW9uPicrY2F0cy5tYXAoYz0+YDxvcHRpb24gdmFsdWU9IiR7Y30iPiR7Q0FUS09bY118fGN9PC9vcHRpb24+YCkuam9pbignJyk7CiAgY29uc3Qgb2M9e307RC5uZXdzLmZvckVhY2gobj0+b2Nbbi5vXT0ob2Nbbi5vXXx8MCkrMSk7CiAgY29uc3Qgb3V0cz1PYmplY3QuZW50cmllcyhvYykuc29ydCgoYSxiKT0+YlsxXS1hWzFdKTsKICAkKCcjbmYtb3V0JykuaW5uZXJIVE1MPSc8b3B0aW9uIHZhbHVlPSIiPuyWuOuhoOyCrCDsoITssrQ8L29wdGlvbj4nK291dHMuZmlsdGVyKG89Pm9bMV0+PTIpLm1hcChvPT5gPG9wdGlvbiB2YWx1ZT0iJHtlc2Mob1swXSl9Ij4ke2VzYyhvWzBdKX0gKCR7b1sxXX0pPC9vcHRpb24+YCkuam9pbignJyk7CiAgY29uc3Qgc2M9e307RC5uZXdzLmZvckVhY2gobj0+c2Nbbi5zXT0oc2Nbbi5zXXx8MCkrMSk7CiAgY29uc3Qgc2hzPU9iamVjdC5lbnRyaWVzKHNjKS5zb3J0KChhLGIpPT5iWzFdLWFbMV0pLmZpbHRlcihzPT5zWzFdPj0yKTsKICAkKCcjbmYtc2hyJykuaW5uZXJIVE1MPSc8b3B0aW9uIHZhbHVlPSIiPuqzteycoOyekCDsoITssrQ8L29wdGlvbj4nK3Nocy5tYXAocz0+YDxvcHRpb24gdmFsdWU9IiR7ZXNjKHNbMF0pfSI+JHtlc2Moc1swXSl9ICgke3NbMV19KTwvb3B0aW9uPmApLmpvaW4oJycpOwogIGNvbnN0IGR0cz1bLi4ubmV3IFNldChELm5ld3MubWFwKG49Pm4uZHQpKV07CiAgJCgnI25mLWR1cCcpLmlubmVySFRNTD0nPG9wdGlvbiB2YWx1ZT0iIj7qtazrtoQg7KCE7LK0PC9vcHRpb24+JytkdHMubWFwKGQ9PmA8b3B0aW9uIHZhbHVlPSIke2VzYyhkKX0iPiR7ZXNjKGQpfTwvb3B0aW9uPmApLmpvaW4oJycpOwogIFsnI25mLXEnLCcjbmYtY2F0JywnI25mLW91dCcsJyNuZi1zaHInLCcjbmYtZHVwJywnI25mLWZyb20nLCcjbmYtdG8nXS5mb3JFYWNoKHNlbD0+JChzZWwpLmFkZEV2ZW50TGlzdGVuZXIoJ2lucHV0JyxhcHBseU5ld3MpKTsKICAkKCcjbmYtcmVzZXQnKS5vbmNsaWNrPSgpPT57WycjbmYtcScsJyNuZi1jYXQnLCcjbmYtb3V0JywnI25mLXNocicsJyNuZi1kdXAnLCcjbmYtZnJvbScsJyNuZi10byddLmZvckVhY2gocz0+JChzKS52YWx1ZT0nJyk7YXBwbHlOZXdzKCk7fTsKICAkKCcjbmV3cy10aC1kYXRlJykub25jbGljaz0oKT0+e05FV1Muc29ydERlc2M9IU5FV1Muc29ydERlc2M7YXBwbHlOZXdzKCk7fTsKICBhcHBseU5ld3MoKTsKfTsKZnVuY3Rpb24gYXBwbHlOZXdzKCl7CiAgY29uc3QgcT0kKCcjbmYtcScpLnZhbHVlLnRyaW0oKS50b0xvd2VyQ2FzZSgpLGNhdD0kKCcjbmYtY2F0JykudmFsdWUsb3V0PSQoJyNuZi1vdXQnKS52YWx1ZSwKICAgICAgICBzaHI9JCgnI25mLXNocicpLnZhbHVlLGZyPSQoJyNuZi1mcm9tJykudmFsdWUsdG89JCgnI25mLXRvJykudmFsdWUsZHVwPSQoJyNuZi1kdXAnKS52YWx1ZTsKICBsZXQgcj1ELm5ld3MuZmlsdGVyKG49PnsKICAgIGlmKGNhdCYmbi5jIT09Y2F0KXJldHVybiBmYWxzZTsKICAgIGlmKG91dCYmbi5vIT09b3V0KXJldHVybiBmYWxzZTsKICAgIGlmKHNociYmbi5zIT09c2hyKXJldHVybiBmYWxzZTsKICAgIGlmKGR1cCYmbi5kdCE9PWR1cClyZXR1cm4gZmFsc2U7CiAgICBpZihmciYmbi5kPGZyKXJldHVybiBmYWxzZTsKICAgIGlmKHRvJiZuLmQ+dG8pcmV0dXJuIGZhbHNlOwogICAgaWYocSYmISgobi50aXx8JycpLnRvTG93ZXJDYXNlKCkuaW5jbHVkZXMocSl8fChuLm98fCcnKS50b0xvd2VyQ2FzZSgpLmluY2x1ZGVzKHEpfHwobi51fHwnJykudG9Mb3dlckNhc2UoKS5pbmNsdWRlcyhxKXx8KG4uc3x8JycpLnRvTG93ZXJDYXNlKCkuaW5jbHVkZXMocSkpKXJldHVybiBmYWxzZTsKICAgIHJldHVybiB0cnVlO30pOwogIHIuc29ydCgoYSxiKT0+IE5FV1Muc29ydERlc2MgPyBiLmQubG9jYWxlQ29tcGFyZShhLmQpOmEuZC5sb2NhbGVDb21wYXJlKGIuZCkpOwogIE5FV1Mucm93cz1yO05FV1MucGFnZT0wO3JlbmRlck5ld3MoKTsKfQpmdW5jdGlvbiByZW5kZXJOZXdzKCl7CiAgY29uc3Qgcj1ORVdTLnJvd3MsdG90PUQubmV3cy5sZW5ndGg7CiAgY29uc3QgTT1ELm1ldGE7CiAgJCgnI25ld3MtY291bnQnKS5pbm5lckhUTUw9YOqzoOycoCDquLDsgqwgPGI+JHtmbXROKHRvdCl9PC9iPuqxtCDspJEgPGI+JHtmbXROKHIubGVuZ3RoKX08L2I+6rG0IO2RnOyLnCDCtyDrhKTsnbTrsoQg7ZW07KCcIDxiPiR7Zm10TihNLnJlc29sdmVkfHwwKX08L2I+IMK3IOygnOuqqSA8Yj4ke00udGl0bGVkX3BjdH0lPC9iPmA7CiAgY29uc3Qgc3RhcnQ9TkVXUy5wYWdlKk5FV1MucGVyLHBhZ2U9ci5zbGljZShzdGFydCxzdGFydCtORVdTLnBlcik7CiAgY29uc3QgQ0FUS089e25ld3M6J+uJtOyKpCcsYnJva2VyX3JlcG9ydDon66as7Y+s7Yq4Jyx2aWRlbzon7JiB7IOBJyxzb2NpYWw6J1NOUycsYmxvZzon67iU66Gc6re4JyxtZXNzZW5nZXI6J+2FlOugiOq3uOueqCcsCiAgICBkb2M6J+usuOyEnCcsZGF0YTon7Iuc7IS4JyxkaXNjbG9zdXJlOifqs7Xsi5wnLGludGVybmFsOifrgrTrtoAnLGNvbW11bml0eTon7Luk666k64uI7YuwJyxzaG9ydGVuZXI6J+uLqOy2lScsZm9ybTon7ISk66y4JyxwZXJzb25hbDon6rCc7J24JyxvdGhlcjon6riw7YOAJ307CiAgJCgnI25ld3MtYm9keScpLmlubmVySFRNTD1wYWdlLm1hcChuPT57CiAgICBjb25zdCBzaGFyZT1uLm4+PTI/YDxiPiR7bi5ufTwvYj7tmoxgOicxJzsKICAgIGNvbnN0IHdobz1lc2Mobi5zKSsobi5zbj4xP2AgPHNwYW4gY2xhc3M9Im11dGVkIj7smbggJHtuLnNuLTF9PC9zcGFuPmA6JycpOwogICAgY29uc3QgdGl0bGU9bi50aT9lc2Mobi50aSk6JzxzcGFuIGNsYXNzPSJtdXRlZCI+KOygnOuqqSDsl4bsnYwgwrcg66eB7YGsIOywuOyhsCk8L3NwYW4+JzsKICAgIGNvbnN0IGJhZGdlPW4ubj49Mj8nIDxzcGFuIGNsYXNzPSJjaGlwIGMtYnJva2VyX3JlcG9ydCI+7J6s6rO17JygPC9zcGFuPic6Jyc7CiAgICByZXR1cm4gYDx0cj4KICAgIDx0ZCBjbGFzcz0ibm93cmFwIj4ke24uZH08L3RkPgogICAgPHRkIGNsYXNzPSJub3dyYXAiIHN0eWxlPSJ0ZXh0LWFsaWduOmNlbnRlciI+JHtzaGFyZX08L3RkPgogICAgPHRkIGNsYXNzPSJub3dyYXAiPiR7d2hvfTwvdGQ+CiAgICA8dGQgY2xhc3M9Im5vd3JhcCI+JHtlc2Mobi5vKX08L3RkPgogICAgPHRkPjxzcGFuIGNsYXNzPSJjaGlwIGMtJHtuLmN9Ij4ke0NBVEtPW24uY118fG4uY308L3NwYW4+PC90ZD4KICAgIDx0ZCBjbGFzcz0iY210Ij4ke3RpdGxlfSR7YmFkZ2V9PC90ZD4KICAgIDx0ZD48YSBocmVmPSIke2VzYyhuLnUpfSIgdGFyZ2V0PSJfYmxhbmsiIHJlbD0ibm9vcGVuZXIiPuyXtOq4sCDihpc8L2E+PC90ZD48L3RyPmA7fSkuam9pbignJykKICAgIHx8Jzx0cj48dGQgY29sc3Bhbj03IGNsYXNzPSJtdXRlZCIgc3R5bGU9InBhZGRpbmc6MjRweDt0ZXh0LWFsaWduOmNlbnRlciI+7KGw6rG07JeQIOunnuuKlCDtla3rqqnsnbQg7JeG7Iq164uI64ukLjwvdGQ+PC90cj4nOwogIGNvbnN0IHBhZ2VzPU1hdGguY2VpbChyLmxlbmd0aC9ORVdTLnBlcil8fDE7CiAgJCgnI25ld3MtcGFnZXInKS5pbm5lckhUTUw9YDxidXR0b24gJHtORVdTLnBhZ2U8PTA/J2Rpc2FibGVkJzonJ30gaWQ9Im5wLXByZXYiPuKAuSDsnbTsoIQ8L2J1dHRvbj4KICAgIDxzcGFuPiR7TkVXUy5wYWdlKzF9IC8gJHtwYWdlc308L3NwYW4+CiAgICA8YnV0dG9uICR7TkVXUy5wYWdlPj1wYWdlcy0xPydkaXNhYmxlZCc6Jyd9IGlkPSJucC1uZXh0Ij7ri6TsnYwg4oC6PC9idXR0b24+YDsKICAkKCcjbnAtcHJldicpJiYoJCgnI25wLXByZXYnKS5vbmNsaWNrPSgpPT57TkVXUy5wYWdlLS07cmVuZGVyTmV3cygpO30pOwogICQoJyNucC1uZXh0JykmJigkKCcjbnAtbmV4dCcpLm9uY2xpY2s9KCk9PntORVdTLnBhZ2UrKztyZW5kZXJOZXdzKCk7fSk7Cn0KCi8qIC0tLS0tLS0tLS0tLS0tLS0gU1RSQVRFR1kgLS0tLS0tLS0tLS0tLS0tLSAqLwpsZXQgU0lHPXtyb3dzOltdLHBhZ2U6MCxwZXI6NTB9OwpSRU5ERVIuc3RyYXRlZ3k9KCk9PnsKICAvLyBzdWIgbmF2CiAgJCQoJyNzdHJhdGVneSAuc3VibmF2IGJ1dHRvbicpLmZvckVhY2goYj0+Yi5vbmNsaWNrPSgpPT57CiAgICAkJCgnI3N0cmF0ZWd5IC5zdWJuYXYgYnV0dG9uJykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC50b2dnbGUoJ29uJyx4PT09YikpOwogICAgJCQoJyNzdHJhdGVneSAuc3ViJykuZm9yRWFjaChzPT5zLmNsYXNzTGlzdC50b2dnbGUoJ29uJyxzLmlkPT09Yi5kYXRhc2V0LnMpKTt9KTsKICByZW5kZXJDYXRhbG9nKCk7cmVuZGVyTWF0cml4KCk7cmVuZGVyRmVlZENvbnRyb2xzKCk7YXBwbHlGZWVkKCk7Cn07CmZ1bmN0aW9uIHJlbmRlckNhdGFsb2coKXsKICBjb25zdCByb3dzPUQuZW50aXRpZXMuc2xpY2UoKS5zb3J0KChhLGIpPT5QSShiLm1lbnRpb25zKS1QSShhLm1lbnRpb25zKSk7CiAgJCgnI2NhdC1ib2R5JykuaW5uZXJIVE1MPXJvd3MubWFwKGU9PmA8dHIgc3R5bGU9ImN1cnNvcjpwb2ludGVyIiBvbmNsaWNrPSJmb2N1c0VudGl0eSgnJHtlc2MoZS5lbnRpdHkpfScpIj4KICAgIDx0ZD48Yj4ke2VzYyhlLmVudGl0eSl9PC9iPjwvdGQ+PHRkIGNsYXNzPSJub3dyYXAgbXV0ZWQiPiR7TUtUS09bZS5tYXJrZXRdfHxlLm1hcmtldH08L3RkPgogICAgPHRkIGNsYXNzPSJub3dyYXAgbXV0ZWQiPiR7ZXNjKGUudGlja2VyKX08L3RkPjx0ZCBjbGFzcz0ibm93cmFwIj4ke2VzYyhlLnNlY3Rvcil9PC90ZD4KICAgIDx0ZCBzdHlsZT0idGV4dC1hbGlnbjpyaWdodCI+JHtmbXROKGUubWVudGlvbnMpfTwvdGQ+CiAgICA8dGQgc3R5bGU9InRleHQtYWxpZ246cmlnaHQiPiR7Zm10TihlLnBlcnNvbmFsX3NpZ25hbHMpfTwvdGQ+CiAgICA8dGQ+JHtzdGJhcihQSShlLmJ1bGxpc2gpLFBJKGUuYmVhcmlzaCksUEkoZS53YXRjaCksUEkoZS5uZXV0cmFsKSl9PC90ZD4KICAgIDx0ZCBjbGFzcz0ibXV0ZWQiIHN0eWxlPSJmb250LXNpemU6MTJweCI+JHtlc2MoZS50b3Bfdm9pY2VzKX08L3RkPjwvdHI+YCkuam9pbignJyk7Cn07CmZ1bmN0aW9uIHJlbmRlck1hdHJpeCgpewogIGNvbnN0IGNvcmU9RC5tZW1iZXJzLm1hcChtPT5tLm1lbWJlcik7CiAgY29uc3QgdG9wPUQuZW50aXRpZXMuc2xpY2UoKS5zb3J0KChhLGIpPT5QSShiLnBlcnNvbmFsX3NpZ25hbHMpLVBJKGEucGVyc29uYWxfc2lnbmFscykpLnNsaWNlKDAsMTYpOwogIGNvbnN0IG1hcD17fTtELnBlcnNvbl9lbnRpdHkuZm9yRWFjaChwPT5tYXBbcC5wZXJzb24rJ3wnK3AuZW50aXR5XT1wKTsKICBsZXQgaGVhZD0nPHRoIHN0eWxlPSJtaW4td2lkdGg6OTBweCI+66mk67KEIO+8vCDsooXrqqk8L3RoPicrdG9wLm1hcChlPT5gPHRoIHRpdGxlPSIke2VzYyhlLmVudGl0eSl9IiBzdHlsZT0id3JpdGluZy1tb2RlOnZlcnRpY2FsLXJsO3RyYW5zZm9ybTpyb3RhdGUoMTgwZGVnKTtoZWlnaHQ6ODRweDtwYWRkaW5nOjRweCI+JHtlc2MoZS5lbnRpdHkpfTwvdGg+YCkuam9pbignJyk7CiAgbGV0IGJvZHk9Y29yZS5tYXAobWI9PnsKICAgIGNvbnN0IHJvbGU9KEQubWVtYmVycy5maW5kKHg9PngubWVtYmVyPT09bWIpfHx7fSkucm9sZXx8Jyc7CiAgICByZXR1cm4gYDx0cj48dGQgY2xhc3M9Im5vd3JhcCI+PGI+JHtlc2MobWIpfTwvYj48ZGl2IGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxMXB4Ij4ke2VzYyhyb2xlKX08L2Rpdj48L3RkPmArCiAgICAgIHRvcC5tYXAoZT0+e2NvbnN0IGM9bWFwW21iKyd8JytlLmVudGl0eV07CiAgICAgICAgaWYoIWMpcmV0dXJuICc8dGQgc3R5bGU9InRleHQtYWxpZ246Y2VudGVyO2NvbG9yOiNjYmQ1ZTEiPsK3PC90ZD4nOwogICAgICAgIGNvbnN0IGNvbD1TVENPTF9sZWFuKGMubGVhbik7CiAgICAgICAgcmV0dXJuIGA8dGQgc3R5bGU9InRleHQtYWxpZ246Y2VudGVyIj48c3BhbiBjbGFzcz0ibGVhbiAke2MubGVhbn0iIHRpdGxlPSLqsJUke2MuYnVsbGlzaH0v7JW9JHtjLmJlYXJpc2h9L+q0gCR7Yy53YXRjaH0gwrcgJHtMRUFOS09bYy5sZWFuXXx8Jyd9Ij4ke2MudG90YWx9PC9zcGFuPjwvdGQ+YDsKICAgICAgfSkuam9pbignJykrJzwvdHI+Jzt9KS5qb2luKCcnKTsKICAkKCcjbWF0cml4LXRhYmxlJykuaW5uZXJIVE1MPSc8dGhlYWQ+PHRyPicraGVhZCsnPC90cj48L3RoZWFkPjx0Ym9keT4nK2JvZHkrJzwvdGJvZHk+JzsKfTsKZnVuY3Rpb24gU1RDT0xfbGVhbihsKXtyZXR1cm4gU1RDT0xbbF18fFNUQ09MLm5ldXRyYWw7fQpmdW5jdGlvbiByZW5kZXJGZWVkQ29udHJvbHMoKXsKICBjb25zdCBwcGw9Wy4uLm5ldyBTZXQoRC5zaWduYWxzLm1hcChzPT5zLnMpKV07CiAgJCgnI3NmLXBlcnNvbicpLmlubmVySFRNTD0nPG9wdGlvbiB2YWx1ZT0iIj7snbjrrLwg7KCE7LK0PC9vcHRpb24+JytELm1lbWJlcnMubWFwKG09PmA8b3B0aW9uPiR7ZXNjKG0ubWVtYmVyKX08L29wdGlvbj5gKS5qb2luKCcnKTsKICBjb25zdCBlbnRzPUQuZW50aXRpZXMubWFwKGU9PmUuZW50aXR5KTsKICAkKCcjc2YtZW50JykuaW5uZXJIVE1MPSc8b3B0aW9uIHZhbHVlPSIiPuyiheuqqSDsoITssrQ8L29wdGlvbj4nK2VudHMubWFwKGU9PmA8b3B0aW9uPiR7ZXNjKGUpfTwvb3B0aW9uPmApLmpvaW4oJycpOwogICQoJyNzZi1zdGFuY2UnKS5pbm5lckhUTUw9JzxvcHRpb24gdmFsdWU9IiI+7Iqk7YOg7IqkIOyghOyytDwvb3B0aW9uPicrWydidWxsaXNoJywnYmVhcmlzaCcsJ3dhdGNoJywnbmV1dHJhbCcsJ21peGVkJ10ubWFwKHM9PmA8b3B0aW9uIHZhbHVlPSIke3N9Ij4ke0xFQU5LT1tzXX08L29wdGlvbj5gKS5qb2luKCcnKTsKICAkKCcjc2YtdHlwZScpLmlubmVySFRNTD0nPG9wdGlvbiB2YWx1ZT0iIj7snKDtmJUg7KCE7LK0PC9vcHRpb24+PG9wdGlvbiB2YWx1ZT0icGVyc29uYWwiPuqwnOyduCjtj6zsp4DshZgr6rSA7KCQKTwvb3B0aW9uPjxvcHRpb24gdmFsdWU9InBvc2l0aW9uIj7tj6zsp4DshZgv66ek66ekPC9vcHRpb24+PG9wdGlvbiB2YWx1ZT0idmlldyI+6rSA7KCQL+yLnO2Zqey9lOupmO2KuDwvb3B0aW9uPjxvcHRpb24gdmFsdWU9InJlc2VhcmNoIj7qs7XsnKAg66as7ISc7LmYL+yLnO2ZqTwvb3B0aW9uPic7CiAgWycjc2YtcGVyc29uJywnI3NmLWVudCcsJyNzZi1zdGFuY2UnLCcjc2YtdHlwZScsJyNzZi1xJ10uZm9yRWFjaChzPT4kKHMpLmFkZEV2ZW50TGlzdGVuZXIoJ2lucHV0JyxhcHBseUZlZWQpKTsKfQp3aW5kb3cuZm9jdXNFbnRpdHk9KGUpPT57IC8vIGp1bXAgZnJvbSBjYXRhbG9nIHRvIGZlZWQKICAkJCgnI3N0cmF0ZWd5IC5zdWJuYXYgYnV0dG9uJykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC50b2dnbGUoJ29uJyx4LmRhdGFzZXQucz09PSdzdWItZmVlZCcpKTsKICAkJCgnI3N0cmF0ZWd5IC5zdWInKS5mb3JFYWNoKHM9PnMuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLHMuaWQ9PT0nc3ViLWZlZWQnKSk7CiAgJCgnI3NmLWVudCcpLnZhbHVlPWU7YXBwbHlGZWVkKCk7JCgnI3N0cmF0ZWd5Jykuc2Nyb2xsSW50b1ZpZXcoe2JlaGF2aW9yOidzbW9vdGgnfSk7Cn07CndpbmRvdy5mb2N1c1BlcnNvbj0ocCk9PntzaG93KCdzdHJhdGVneScpO3NldFRpbWVvdXQoKCk9PnsKICAkJCgnI3N0cmF0ZWd5IC5zdWJuYXYgYnV0dG9uJykuZm9yRWFjaCh4PT54LmNsYXNzTGlzdC50b2dnbGUoJ29uJyx4LmRhdGFzZXQucz09PSdzdWItZmVlZCcpKTsKICAkJCgnI3N0cmF0ZWd5IC5zdWInKS5mb3JFYWNoKHM9PnMuY2xhc3NMaXN0LnRvZ2dsZSgnb24nLHMuaWQ9PT0nc3ViLWZlZWQnKSk7CiAgJCgnI3NmLXBlcnNvbicpLnZhbHVlPXA7YXBwbHlGZWVkKCk7fSw2MCk7fTsKZnVuY3Rpb24gYXBwbHlGZWVkKCl7CiAgY29uc3QgcD0kKCcjc2YtcGVyc29uJykudmFsdWUsZT0kKCcjc2YtZW50JykudmFsdWUsc3Q9JCgnI3NmLXN0YW5jZScpLnZhbHVlLHR5PSQoJyNzZi10eXBlJykudmFsdWUscT0kKCcjc2YtcScpLnZhbHVlLnRyaW0oKS50b0xvd2VyQ2FzZSgpOwogIGxldCByPUQuc2lnbmFscy5maWx0ZXIocz0+ewogICAgaWYocCYmcy5zIT09cClyZXR1cm4gZmFsc2U7CiAgICBpZihlJiYhKHMuZXx8W10pLmluY2x1ZGVzKGUpKXJldHVybiBmYWxzZTsKICAgIGlmKHN0JiZzLnN0IT09c3QpcmV0dXJuIGZhbHNlOwogICAgaWYodHk9PT0ncGVyc29uYWwnJiZzLnR5PT09J3Jlc2VhcmNoJylyZXR1cm4gZmFsc2U7CiAgICBpZih0eT09PSdwb3NpdGlvbicmJnMudHkhPT0ncG9zaXRpb24nKXJldHVybiBmYWxzZTsKICAgIGlmKHR5PT09J3ZpZXcnJiZzLnR5IT09J3ZpZXcnKXJldHVybiBmYWxzZTsKICAgIGlmKHR5PT09J3Jlc2VhcmNoJyYmcy50eSE9PSdyZXNlYXJjaCcpcmV0dXJuIGZhbHNlOwogICAgaWYocSYmIShzLnh8fCcnKS50b0xvd2VyQ2FzZSgpLmluY2x1ZGVzKHEpJiYhKHMuZXx8W10pLmpvaW4oJywnKS50b0xvd2VyQ2FzZSgpLmluY2x1ZGVzKHEpKXJldHVybiBmYWxzZTsKICAgIHJldHVybiB0cnVlO30pOwogIHIuc29ydCgoYSxiKT0+KGIuZCkubG9jYWxlQ29tcGFyZShhLmQpKTsKICBTSUcucm93cz1yO1NJRy5wYWdlPTA7cmVuZGVyRmVlZCgpOwp9CmZ1bmN0aW9uIHJlbmRlckZlZWQoKXsKICBjb25zdCByPVNJRy5yb3dzOwogICQoJyNmZWVkLWNvdW50JykuaW5uZXJIVE1MPWDsoITssrQgPGI+JHtmbXROKEQuc2lnbmFscy5sZW5ndGgpfTwvYj7qsJwg7Iuc6re464SQIOykkSA8Yj4ke2ZtdE4oci5sZW5ndGgpfTwvYj7qsJxgOwogIGNvbnN0IHN0YXJ0PVNJRy5wYWdlKlNJRy5wZXIscGFnZT1yLnNsaWNlKHN0YXJ0LHN0YXJ0K1NJRy5wZXIpOwogIGNvbnN0IFRZS089e3Bvc2l0aW9uOiftj6zsp4DshZgv66ek66ekJyx2aWV3OifqtIDsoJAv7Iuc7ZmpJyxpZGVhOifslYTsnbTrlJTslrQnLHJlc2VhcmNoOifqs7XsnKAg66as7ISc7LmYJ307CiAgJCgnI2ZlZWQtYm9keScpLmlubmVySFRNTD1wYWdlLm1hcChzPT57CiAgICBjb25zdCBsZWFuPXMudHk9PT0ncmVzZWFyY2gnPycnOmA8c3BhbiBjbGFzcz0ibGVhbiAke3Muc3R9Ij4ke0xFQU5LT1tzLnN0XXx8cy5zdH08L3NwYW4+YDsKICAgIGNvbnN0IGVudHM9KHMuZXx8W10pLm1hcCh4PT5gPHNwYW4gY2xhc3M9ImVudHMiPiR7ZXNjKHgpfTwvc3Bhbj5gKS5qb2luKCcgwrcgJyk7CiAgICBjb25zdCB0aHM9KHMudGh8fFtdKS5tYXAoeD0+YDxzcGFuIGNsYXNzPSJ0YWciPiR7ZXNjKHgpfTwvc3Bhbj5gKS5qb2luKCcnKTsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic2lnIj48ZGl2IGNsYXNzPSJtZXRhIj48c3BhbiBjbGFzcz0id2hvIj4ke2VzYyhzLnMpfTwvc3Bhbj4KICAgICAgPHNwYW4+JHtzLmR9PC9zcGFuPiAke2xlYW59IDxzcGFuIGNsYXNzPSJtdXRlZCI+JHtUWUtPW3MudHldfHxzLnR5fTwvc3Bhbj4gJHtlbnRzfTwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ0eCI+JHtlc2Mocy54KX08L2Rpdj48ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjNweCI+JHt0aHN9PC9kaXY+PC9kaXY+YDt9KS5qb2luKCcnKQogICAgfHwnPGRpdiBjbGFzcz0ibXV0ZWQiIHN0eWxlPSJwYWRkaW5nOjIwcHg7dGV4dC1hbGlnbjpjZW50ZXIiPuyhsOqxtOyXkCDrp57ripQg7Iuc6re464SQ7J20IOyXhuyKteuLiOuLpC48L2Rpdj4nOwogIGNvbnN0IHBhZ2VzPU1hdGguY2VpbChyLmxlbmd0aC9TSUcucGVyKXx8MTsKICAkKCcjZmVlZC1wYWdlcicpLmlubmVySFRNTD1gPGJ1dHRvbiAke1NJRy5wYWdlPD0wPydkaXNhYmxlZCc6Jyd9IGlkPSJzcC1wcmV2Ij7igLkg7J207KCEPC9idXR0b24+CiAgICA8c3Bhbj4ke1NJRy5wYWdlKzF9IC8gJHtwYWdlc308L3NwYW4+PGJ1dHRvbiAke1NJRy5wYWdlPj1wYWdlcy0xPydkaXNhYmxlZCc6Jyd9IGlkPSJzcC1uZXh0Ij7ri6TsnYwg4oC6PC9idXR0b24+YDsKICAkKCcjc3AtcHJldicpJiYoJCgnI3NwLXByZXYnKS5vbmNsaWNrPSgpPT57U0lHLnBhZ2UtLTtyZW5kZXJGZWVkKCk7fSk7CiAgJCgnI3NwLW5leHQnKSYmKCQoJyNzcC1uZXh0Jykub25jbGljaz0oKT0+e1NJRy5wYWdlKys7cmVuZGVyRmVlZCgpO30pOwp9CgovKiAtLS0tLS0tLS0tLS0tLS0tIE1FTUJFUlMgLS0tLS0tLS0tLS0tLS0tLSAqLwpSRU5ERVIubWVtYmVycz0oKT0+ewogIGNvbnN0IHRhZ3M9cz0+KHN8fCcnKS5zcGxpdCgnOycpLmZpbHRlcihCb29sZWFuKS5tYXAodD0+YDxzcGFuIGNsYXNzPSJ0YWciPiR7ZXNjKHQpfTwvc3Bhbj5gKS5qb2luKCcnKTsKICAkKCcjbWVtLWdyaWQnKS5pbm5lckhUTUw9RC5tZW1iZXJzLm1hcChtPT57CiAgICBjb25zdCB0ZWFjaD0obS5pc190ZWFjaGVyPT09J1RydWUnfHxtLmlzX3RlYWNoZXI9PT10cnVlKT8nPHNwYW4gY2xhc3M9ImNoaXAgYy1uZXdzIiBzdHlsZT0ibWFyZ2luLWxlZnQ6NnB4Ij7smrTsmIEv6rCV7IKsPC9zcGFuPic6Jyc7CiAgICBjb25zdCBzaWc9UEkobS5wZXJzb25hbF9zaWduYWxzKTsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0ibWNhcmQiPjxkaXYgY2xhc3M9Im5tIj4ke2VzYyhtLm1lbWJlcil9ICR7dGVhY2h9PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InJvIj4ke2VzYyhtLnJvbGUpfTwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJtYXJnaW46OHB4IDAiPgogICAgICAgIDxkaXYgY2xhc3M9InJvdyI+PHNwYW4+66mU7Iuc7KeAPC9zcGFuPjxiPiR7Zm10TihtLm1lc3NhZ2VzKX08L2I+PC9kaXY+CiAgICAgICAgPGRpdiBjbGFzcz0icm93Ij48c3Bhbj7qs7XsnKAg66eB7YGsPC9zcGFuPjxiPiR7Zm10TihtLmxpbmtzX3NoYXJlZCl9PC9iPjwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9InJvdyI+PHNwYW4+6rCc7J24IOyghOuetSDsi5zqt7jrhJA8L3NwYW4+PGI+JHtmbXROKHNpZyl9PC9iPjwvZGl2PjwvZGl2PgogICAgICAke3NpZz9gPGRpdiBzdHlsZT0ibWFyZ2luOjZweCAwIj4ke3N0YmFyKFBJKG0uYnVsbGlzaCksUEkobS5iZWFyaXNoKSxQSShtLndhdGNoKSxNYXRoLm1heCgwLHNpZy1QSShtLmJ1bGxpc2gpLVBJKG0uYmVhcmlzaCktUEkobS53YXRjaCkpKX08L2Rpdj5gOicnfQogICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjhweDtmb250LXNpemU6MTJweDtjb2xvcjojNDc1NTY5O2ZvbnQtd2VpZ2h0OjcwMCI+6rSA7IusIOyiheuqqTwvZGl2PgogICAgICA8ZGl2PiR7dGFncyhtLnRvcF9lbnRpdGllcyl8fCc8c3BhbiBjbGFzcz1tdXRlZCBzdHlsZT0iZm9udC1zaXplOjEycHgiPuKAlDwvc3Bhbj4nfTwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjZweDtmb250LXNpemU6MTJweDtjb2xvcjojNDc1NTY5O2ZvbnQtd2VpZ2h0OjcwMCI+6rSA7IusIO2FjOuniDwvZGl2PgogICAgICA8ZGl2PiR7dGFncyhtLnRvcF90aGVtZXMpfHwnPHNwYW4gY2xhc3M9bXV0ZWQgc3R5bGU9ImZvbnQtc2l6ZToxMnB4Ij7igJQ8L3NwYW4+J308L2Rpdj4KICAgICAgPGJ1dHRvbiBjbGFzcz0ibWVtby1idG4iIG9uY2xpY2s9ImZvY3VzUGVyc29uKCcke2VzYyhtLm1lbWJlcikucmVwbGFjZSgvJy9nLCJcXCciKX0nKSIKICAgICAgICBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4O3dpZHRoOjEwMCU7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtiYWNrZ3JvdW5kOiNmOGZhZmM7Ym9yZGVyLXJhZGl1czo5cHg7cGFkZGluZzo4cHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo3MDA7Y29sb3I6dmFyKC0tYWNjKSI+7J20IOuppOuyhCDsoITrnrUg67O06riwIOKGkjwvYnV0dG9uPgogICAgPC9kaXY+YDt9KS5qb2luKCcnKTsKfTsKCi8qIC0tLS0tLS0tLS0tLS0tLS0gR1JBUEggLS0tLS0tLS0tLS0tLS0tLSAqLwpSRU5ERVIuZ3JhcGg9KCk9PntkcmF3R3JhcGgoKTsKICAkKCcjZy1tb2RlJykub25jaGFuZ2U9ZHJhd0dyYXBoO307CmZ1bmN0aW9uIGRyYXdHcmFwaCgpewogIGNvbnN0IG1vZGU9JCgnI2ctbW9kZScpLnZhbHVlOwogIGNvbnN0IE49RC5ncmFwaC5ub2RlcyxFPUQuZ3JhcGguZWRnZXM7CiAgbGV0IHVzZU5vZGVzLHVzZUVkZ2VzOwogIGNvbnN0IHRvcEVudD1uZXcgU2V0KEQuZW50aXRpZXMuc2xpY2UoKS5zb3J0KChhLGIpPT5QSShiLm1lbnRpb25zKS1QSShhLm1lbnRpb25zKSkuc2xpY2UoMCwyOCkubWFwKGU9PidFOicrZS5lbnRpdHkpKTsKICBpZihtb2RlPT09J3N0YW5jZScpewogICAgdXNlRWRnZXM9RS5maWx0ZXIoZT0+ZS5yZWw9PT0nSEFTX1NUQU5DRScmJnRvcEVudC5oYXMoZS50YXJnZXQpKTsKICAgIGNvbnN0IGlkcz1uZXcgU2V0KCk7dXNlRWRnZXMuZm9yRWFjaChlPT57aWRzLmFkZChlLnNvdXJjZSk7aWRzLmFkZChlLnRhcmdldCk7fSk7CiAgICB1c2VOb2Rlcz1OLmZpbHRlcihuPT5pZHMuaGFzKG4uaWQpKTsKICB9ZWxzZXsgLy8gdGhlbWUgbWFwCiAgICB1c2VFZGdlcz1FLmZpbHRlcihlPT4oZS5yZWw9PT0nQkVMT05HU19UTycmJnRvcEVudC5oYXMoZS5zb3VyY2UpKXx8KGUucmVsPT09J0ZPQ1VTRVNfT04nJiYoZS53ZWlnaHR8fDApPj0zKSk7CiAgICBjb25zdCBpZHM9bmV3IFNldCgpO3VzZUVkZ2VzLmZvckVhY2goZT0+e2lkcy5hZGQoZS5zb3VyY2UpO2lkcy5hZGQoZS50YXJnZXQpO30pOwogICAgdXNlTm9kZXM9Ti5maWx0ZXIobj0+aWRzLmhhcyhuLmlkKSk7CiAgfQogIGNvbnN0IFc9MTE4MCxIPTcyMDsKICBsYXlvdXQodXNlTm9kZXMsdXNlRWRnZXMsVyxILDMyMCk7CiAgY29uc3QgY29sPW49Pm4udHlwZT09PSdNZW1iZXInPycjMGYxYjJkJzpuLnR5cGU9PT0nVGhlbWUnPycjN2MzYWVkJzoKICAgICAobi5tYXJrZXQ9PT0nS1InPycjMjU2M2ViJzpuLm1hcmtldD09PSdVUyc/JyMwZWE1ZTknOicjZDk3NzA2Jyk7CiAgY29uc3QgcmFkPW49Pm4udHlwZT09PSdNZW1iZXInPzEyOm4udHlwZT09PSdUaGVtZSc/TWF0aC5taW4oMjAsOSsobi5tZW50aW9uc3x8MCkvMTIwKToKICAgICBNYXRoLm1pbigxOCw2KyhuLm1lbnRpb25zfHwwKS8zMCk7CiAgY29uc3QgaWR4PXt9O3VzZU5vZGVzLmZvckVhY2gobj0+aWR4W24uaWRdPW4pOwogIGxldCBlZGdlU3ZnPXVzZUVkZ2VzLm1hcChlPT57Y29uc3QgYT1pZHhbZS5zb3VyY2VdLGI9aWR4W2UudGFyZ2V0XTtpZighYXx8IWIpcmV0dXJuJyc7CiAgICBjb25zdCBjPWUucmVsPT09J0hBU19TVEFOQ0UnPyhTVENPTFtlLmxlYW5dfHwnI2NiZDVlMScpOicjY2JkNWUxJzsKICAgIGNvbnN0IHd3PWUucmVsPT09J0hBU19TVEFOQ0UnP01hdGgubWluKDQsMSsoZS53ZWlnaHR8fDEpLzUpOjEuMjsKICAgIHJldHVybiBgPGxpbmUgeDE9IiR7YS54LnRvRml4ZWQoMSl9IiB5MT0iJHthLnkudG9GaXhlZCgxKX0iIHgyPSIke2IueC50b0ZpeGVkKDEpfSIgeTI9IiR7Yi55LnRvRml4ZWQoMSl9IiBzdHJva2U9IiR7Y30iIHN0cm9rZS13aWR0aD0iJHt3d30iIHN0cm9rZS1vcGFjaXR5PSIuNSIvPmA7fSkuam9pbignJyk7CiAgbGV0IG5vZGVTdmc9dXNlTm9kZXMubWFwKG49Pntjb25zdCByPXJhZChuKTsKICAgIHJldHVybiBgPGcgY2xhc3M9ImduIiBkYXRhLWlkPSIke2VzYyhuLmlkKX0iPjxjaXJjbGUgY3g9IiR7bi54LnRvRml4ZWQoMSl9IiBjeT0iJHtuLnkudG9GaXhlZCgxKX0iIHI9IiR7ci50b0ZpeGVkKDEpfSIKICAgICAgZmlsbD0iJHtjb2wobil9IiBzdHJva2U9IiNmZmYiIHN0cm9rZS13aWR0aD0iMS41Ii8+CiAgICAgIDx0ZXh0IGNsYXNzPSJubGFiZWwiIHg9IiR7bi54LnRvRml4ZWQoMSl9IiB5PSIkeyhuLnktci0zKS50b0ZpeGVkKDEpfSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+JHtlc2Mobi5sYWJlbCl9PC90ZXh0PjwvZz5gO30pLmpvaW4oJycpOwogICQoJyNncmFwaC1zdmcnKS5pbm5lckhUTUw9YDxzdmcgdmlld0JveD0iMCAwICR7V30gJHtIfSIgd2lkdGg9IiR7V30iIGhlaWdodD0iJHtIfSI+JHtlZGdlU3ZnfSR7bm9kZVN2Z308L3N2Zz5gOwp9CmZ1bmN0aW9uIGxheW91dChub2RlcyxlZGdlcyxXLEgsaXRlcnMpewogIGNvbnN0IGlkeD17fTtub2Rlcy5mb3JFYWNoKChuLGkpPT57aWR4W24uaWRdPW47bi54PVcvMitNYXRoLmNvcyhpKSoyMjArKE1hdGgucmFuZG9tKCktLjUpKjEyMDtuLnk9SC8yK01hdGguc2luKGkqMS43KSoxODArKE1hdGgucmFuZG9tKCktLjUpKjEyMDt9KTsKICBjb25zdCBrPU1hdGguc3FydChXKkgvTWF0aC5tYXgoMSxub2Rlcy5sZW5ndGgpKSowLjYyOwogIGNvbnN0IGFkaj1lZGdlcy5tYXAoZT0+W2lkeFtlLnNvdXJjZV0saWR4W2UudGFyZ2V0XV0pLmZpbHRlcihwPT5wWzBdJiZwWzFdKTsKICBsZXQgdD1XLzk7CiAgZm9yKGxldCBpdD0wO2l0PGl0ZXJzO2l0KyspewogICAgbm9kZXMuZm9yRWFjaChhPT57YS5keD0wO2EuZHk9MDt9KTsKICAgIGZvcihsZXQgaT0wO2k8bm9kZXMubGVuZ3RoO2krKylmb3IobGV0IGo9aSsxO2o8bm9kZXMubGVuZ3RoO2orKyl7CiAgICAgIGNvbnN0IGE9bm9kZXNbaV0sYj1ub2Rlc1tqXTtsZXQgZHg9YS54LWIueCxkeT1hLnktYi55O2xldCBkPU1hdGguaHlwb3QoZHgsZHkpfHwuMDE7CiAgICAgIGNvbnN0IGY9ayprL2Q7Y29uc3QgdXg9ZHgvZCx1eT1keS9kO2EuZHgrPXV4KmY7YS5keSs9dXkqZjtiLmR4LT11eCpmO2IuZHktPXV5KmY7fQogICAgYWRqLmZvckVhY2goKFthLGJdKT0+e2xldCBkeD1hLngtYi54LGR5PWEueS1iLnk7bGV0IGQ9TWF0aC5oeXBvdChkeCxkeSl8fC4wMTsKICAgICAgY29uc3QgZj1kKmQvaztjb25zdCB1eD1keC9kLHV5PWR5L2Q7YS5keC09dXgqZjthLmR5LT11eSpmO2IuZHgrPXV4KmY7Yi5keSs9dXkqZjt9KTsKICAgIG5vZGVzLmZvckVhY2goYT0+eyAvLyBncmF2aXR5CiAgICAgIGEuZHgrPShXLzItYS54KSowLjAxMjthLmR5Kz0oSC8yLWEueSkqMC4wMTI7CiAgICAgIGxldCBkPU1hdGguaHlwb3QoYS5keCxhLmR5KXx8LjAxO2NvbnN0IG09TWF0aC5taW4oZCx0KTsKICAgICAgYS54Kz1hLmR4L2QqbTthLnkrPWEuZHkvZCptOwogICAgICBhLng9TWF0aC5tYXgoNDAsTWF0aC5taW4oVy00MCxhLngpKTthLnk9TWF0aC5tYXgoMjgsTWF0aC5taW4oSC0yMixhLnkpKTt9KTsKICAgIHQqPTAuOTc7CiAgfQp9CgovKiAtLS0tLS0tLS0tLS0tLS0tIE9OVE9MT0dZIC0tLS0tLS0tLS0tLS0tLS0gKi8KUkVOREVSLm9udG9sb2d5PSgpPT57CiAgY29uc3Qgcz1ELnNjaGVtYSxtPUQubWV0YTsKICAkKCcjb250by1zY2hlbWEnKS5pbm5lckhUTUw9YDxkaXYgY2xhc3M9InBhbmVsIj48aDI+64W465OcICjsl5Tti7Dti7ApIOycoO2YlTwvaDI+CiAgICAgPGRpdiBjbGFzcz0iZGVzYyI+JHtzLm5vZGVfdHlwZXMubWFwKGVzYykuam9pbignIMK3ICcpfTwvZGl2PjwvZGl2PgogICAgIDxkaXYgY2xhc3M9InBhbmVsIj48aDI+6rSA6rOEICjsl6Psp4ApIOycoO2YlTwvaDI+PGRpdiBjbGFzcz0iZGVzYyI+JHtzLmVkZ2VfdHlwZXMubWFwKGVzYykuam9pbignIMK3ICcpfTwvZGl2PjwvZGl2PmA7CiAgJCgnI29udG8tbWV0YScpLmlubmVySFRNTD1bCiAgICBbJ+yxhOuEkCcsbS5jaGFubmVsXSxbJ+q4sOqwhCcsbS5kYXRlX2Zyb20rJyB+ICcrbS5kYXRlX3RvXSxbJ+uplOyLnOyngCcsZm10TihtLm1lc3NhZ2VzKV0sCiAgICBbJ+uppOuyhCjsoITssrQv7ZW17IusKScsZm10TihtLm1lbWJlcnNfdG90YWwpKycgLyAnK20ubWVtYmVyc19jb3JlXSwKICAgIFsn6rO17JygIOunge2BrCjsoITsiJgpJyxmbXROKG0ubGlua3NfdG90YWwpXSxbJ+uJtOyKpCDquLDsgqwnLGZtdE4obS5uZXdzX2xpbmtzKV0sCiAgICBbJ+qwnOyduCDsoITrnrUg7Iuc6re464SQJyxmbXROKG0uc3RyYXRlZ3lfcGVyc29uYWwpXSxbJ+qzteycoCDrpqzshJzsuZgv7Iuc7ZmpJyxmbXROKG0uc3RyYXRlZ3lfcmVzZWFyY2gpXSwKICAgIFsn6re4656Y7ZSEIOuFuOuTnC/sl6Psp4AnLGZtdE4oRC5ncmFwaC5ub2Rlcy5sZW5ndGgpKycgLyAnK2ZtdE4oRC5ncmFwaC5lZGdlcy5sZW5ndGgpXQogIF0ubWFwKGs9PmA8ZGl2IGNsYXNzPSJrdiI+PGI+JHtlc2Moa1swXSl9PC9iPjxzcGFuPiR7ZXNjKGtbMV0pfTwvc3Bhbj48L2Rpdj5gKS5qb2luKCcnKTsKfTsKCmRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoJ0RPTUNvbnRlbnRMb2FkZWQnLCgpPT57CiAgJCQoJ25hdi50YWJzIGJ1dHRvbicpLmZvckVhY2goYj0+Yi5vbmNsaWNrPSgpPT5zaG93KGIuZGF0YXNldC50KSk7CiAgc2hvdygnb3ZlcnZpZXcnKTsKfSk7Cg==").decode("utf-8")
BODY=base64.b64decode("PGhlYWRlciBjbGFzcz0idG9wIj4KICA8ZGl2IGNsYXNzPSJ0MSI+UFJPTSBVUyDCtyBLTk9XTEVER0UgT05UT0xPR1k8L2Rpdj4KICA8aDE+7ZSE66Gs7Ja07IqkIOy5tO2GoSDsmKjthqjroZzsp4Ag7JWE7Lm07J2067iMPC9oMT4KICA8ZGl2IGNsYXNzPSJzdWIiPuuJtOyKpCDsoITsiJgg7JWE7Lm07J2067mZIMK3IOq1rOyEseybkCDtiKzsnpDsoITrnrUgwrcg7KKF66qpwrfthYzrp4jCt+yduOusvCDsp4Dsi53qt7jrnpjtlIQ8L2Rpdj4KICA8bmF2IGNsYXNzPSJ0YWJzIj4KICAgIDxidXR0b24gZGF0YS10PSJvdmVydmlldyI+6rCc7JqUPC9idXR0b24+CiAgICA8YnV0dG9uIGRhdGEtdD0ibmV3cyI+64m07IqkIOyVhOy5tOydtOu4jDwvYnV0dG9uPgogICAgPGJ1dHRvbiBkYXRhLXQ9InN0cmF0ZWd5Ij7tiKzsnpDsoITrnrU8L2J1dHRvbj4KICAgIDxidXR0b24gZGF0YS10PSJtZW1iZXJzIj7rqaTrsoQ8L2J1dHRvbj4KICAgIDxidXR0b24gZGF0YS10PSJncmFwaCI+6rSA6rOEIOq3uOuemO2UhDwvYnV0dG9uPgogICAgPGJ1dHRvbiBkYXRhLXQ9Im9udG9sb2d5Ij7smKjthqjroZzsp4A8L2J1dHRvbj4KICA8L25hdj4KPC9oZWFkZXI+CjxtYWluPgogIDwhLS0gT1ZFUlZJRVcgLS0+CiAgPHNlY3Rpb24gaWQ9Im92ZXJ2aWV3IiBjbGFzcz0ic2VjdGlvbiI+CiAgICA8ZGl2IGlkPSJvdi1jYXJkcyIgY2xhc3M9ImNhcmRzIj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBhbmVsIj48aDI+7Zmc64+ZIO2DgOyehOudvOyduDwvaDI+PGRpdiBjbGFzcz0iZGVzYyI+6riw6rCEIOykkSDsnbzrs4Qg66mU7Iuc7KeAwrfqs7XsnKDrp4Htgawg7LaU7J20PC9kaXY+PGRpdiBpZD0ib3YtdGltZWxpbmUiPjwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iZ3JpZDIiPgogICAgICA8ZGl2IGNsYXNzPSJwYW5lbCI+PGgyPuunge2BrCDrtoTrpZg8L2gyPjxkaXYgY2xhc3M9ImRlc2MiPuqzteycoOuQnCAxLDc5NuqwnCDrp4HtgazsnZgg7Jyg7ZiVIOu2hO2PrDwvZGl2PjxkaXYgaWQ9Im92LWNhdHMiPjwvZGl2PjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwYW5lbCI+PGgyPuyjvOyalCDslrjroaDsgqwgwrcg7Lac7LKYPC9oMj48ZGl2IGNsYXNzPSJkZXNjIj7ribTsiqQv66as7Y+s7Yq4IOq4sOykgCDsg4HsnIQgMTU8L2Rpdj48ZGl2IGlkPSJvdi1vdXRsZXRzIj48L2Rpdj48L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0icGFuZWwiPjxoMj7tlbXsi6wg7YWM66eIPC9oMj48ZGl2IGNsYXNzPSJkZXNjIj7rjIDtmZTsl5DshJwg6rCA7J6lIOunjuydtCDslrjquInrkJwg7Yis7J6QIO2FjOuniDwvZGl2PjxkaXYgaWQ9Im92LXRoZW1lcyI+PC9kaXY+PC9kaXY+CiAgPC9zZWN0aW9uPgoKICA8IS0tIE5FV1MgLS0+CiAgPHNlY3Rpb24gaWQ9Im5ld3MiIGNsYXNzPSJzZWN0aW9uIj4KICAgIDxkaXYgY2xhc3M9InBhbmVsIj4KICAgICAgPGgyPuuJtOyKpCDCtyDrp4Htgawg7JWE7Lm07J2067iMPC9oMj4KICAgICAgPGRpdiBjbGFzcz0iZGVzYyI+7KCE7LK0IDEsNzk27ZqMIOqzteycoOulvCA8Yj7qs6DsnKAg6riw7IKsIDEsNzUx6rG0PC9iPuycvOuhnCDsoJXrpqwuIOqwmeydgCDquLDsgqwg7J6s6rO17Jyg64qUICJO7ZqMIuuhnCDtlansuZjqs6AsIOuwmOuztSDrnbzrsqjsnYAg7KCc6rGw7ZaI7Iq164uI64ukLiBuYXZlci5tZSA1NDLqsbTsnYAg7Iuk7KCcIOq4sOyCrOyjvOyGjOuhnCDtlbTsoJzrkKguPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNvbnRyb2xzIj4KICAgICAgICA8aW5wdXQgdHlwZT0ic2VhcmNoIiBpZD0ibmYtcSIgcGxhY2Vob2xkZXI9IuygnOuqqcK37Ja466Gg7IKswrdVUkzCt+qzteycoOyekCDqsoDsg4kiPgogICAgICAgIDxzZWxlY3QgaWQ9Im5mLWNhdCI+PC9zZWxlY3Q+PHNlbGVjdCBpZD0ibmYtb3V0Ij48L3NlbGVjdD48c2VsZWN0IGlkPSJuZi1zaHIiPjwvc2VsZWN0PjxzZWxlY3QgaWQ9Im5mLWR1cCI+PC9zZWxlY3Q+CiAgICAgICAgPGlucHV0IHR5cGU9ImRhdGUiIGlkPSJuZi1mcm9tIiB0aXRsZT0i7Iuc7J6R7J28Ij48aW5wdXQgdHlwZT0iZGF0ZSIgaWQ9Im5mLXRvIiB0aXRsZT0i7KKF66OM7J28Ij4KICAgICAgICA8YnV0dG9uIGlkPSJuZi1yZXNldCIgY2xhc3M9InBhZ2VyIiBzdHlsZT0iYm9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtiYWNrZ3JvdW5kOiNmZmY7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzo4cHggMTJweDtjdXJzb3I6cG9pbnRlcjtmb250LWZhbWlseTppbmhlcml0Ij7stIjquLDtmZQ8L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgaWQ9Im5ld3MtY291bnQiIGNsYXNzPSJtdXRlZCIgc3R5bGU9ImZvbnQtc2l6ZToxM3B4O21hcmdpbi1ib3R0b206NnB4Ij48L2Rpdj4KICAgICAgPGRpdiBzdHlsZT0ib3ZlcmZsb3c6YXV0bzttYXgtaGVpZ2h0OjcwdmgiPgogICAgICA8dGFibGU+PHRoZWFkPjx0cj4KICAgICAgICA8dGggaWQ9Im5ld3MtdGgtZGF0ZSI+64Kg7KecIOKHhTwvdGg+PHRoPuqzteycoDwvdGg+PHRoPuqzteycoOyekDwvdGg+PHRoPuyWuOuhoOyCrDwvdGg+PHRoPuu2hOulmDwvdGg+PHRoPuygnOuqqSAvIOuCtOyaqTwvdGg+PHRoPuunge2BrDwvdGg+CiAgICAgIDwvdHI+PC90aGVhZD48dGJvZHkgaWQ9Im5ld3MtYm9keSI+PC90Ym9keT48L3RhYmxlPgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBpZD0ibmV3cy1wYWdlciIgY2xhc3M9InBhZ2VyIj48L2Rpdj4KICAgIDwvZGl2PgogIDwvc2VjdGlvbj4KCiAgPCEtLSBTVFJBVEVHWSAtLT4KICA8c2VjdGlvbiBpZD0ic3RyYXRlZ3kiIGNsYXNzPSJzZWN0aW9uIj4KICAgIDxkaXYgY2xhc3M9InBhbmVsIiBzdHlsZT0icGFkZGluZy1ib3R0b206OHB4Ij4KICAgICAgPGgyPuq1rOyEseybkCDtiKzsnpDsoITrnrUg7JWE7Lm07J2067iMPC9oMj4KICAgICAgPGRpdiBjbGFzcz0iZGVzYyI+6rCc7J24IO2PrOyngOyFmMK36rSA7KCQ6rO8IOqzteycoCDrpqzshJzsuZjrpbwg67aE66as7ZW0IOy2lOy2nO2WiOyKteuLiOuLpC4gKO2CpOybjOuTnMK37JeU7Yuw7YuwIOq4sOuwmCDsnpDrj5kg7LaU7LacKTwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJzdWJuYXYiIHN0eWxlPSJkaXNwbGF5OmZsZXg7Z2FwOjZweDtmbGV4LXdyYXA6d3JhcDttYXJnaW4tdG9wOjZweCI+CiAgICAgICAgPGJ1dHRvbiBjbGFzcz0ib24iIGRhdGEtcz0ic3ViLWNhdGFsb2ciIHN0eWxlPSJib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JhY2tncm91bmQ6I2YxZjVmOTtib3JkZXItcmFkaXVzOjlweDtwYWRkaW5nOjhweCAxM3B4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NzAwIj7sooXrqqkg7Lm07YOI66Gc6re4PC9idXR0b24+CiAgICAgICAgPGJ1dHRvbiBkYXRhLXM9InN1Yi1tYXRyaXgiIHN0eWxlPSJib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JhY2tncm91bmQ6I2ZmZjtib3JkZXItcmFkaXVzOjlweDtwYWRkaW5nOjhweCAxM3B4O2N1cnNvcjpwb2ludGVyO2ZvbnQtZmFtaWx5OmluaGVyaXQ7Zm9udC13ZWlnaHQ6NzAwIj7snbjrrLwgw5cg7KKF66qpIOunpO2KuOumreyKpDwvYnV0dG9uPgogICAgICAgIDxidXR0b24gZGF0YS1zPSJzdWItZmVlZCIgc3R5bGU9ImJvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7YmFja2dyb3VuZDojZmZmO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6OHB4IDEzcHg7Y3Vyc29yOnBvaW50ZXI7Zm9udC1mYW1pbHk6aW5oZXJpdDtmb250LXdlaWdodDo3MDAiPuyghOuetSDsi5zqt7jrhJAg7ZS865OcPC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGlkPSJzdWItY2F0YWxvZyIgY2xhc3M9InN1YiBvbiI+CiAgICAgIDxkaXYgY2xhc3M9InBhbmVsIj4KICAgICAgICA8ZGl2IGNsYXNzPSJsZWdlbmQiPjxzcGFuPjxpIHN0eWxlPSJiYWNrZ3JvdW5kOiMxNmEzNGEiPjwvaT7qsJXshLgo66ek7IiYL+u5hOykke2ZleuMgCk8L3NwYW4+PHNwYW4+PGkgc3R5bGU9ImJhY2tncm91bmQ6I2RjMjYyNiI+PC9pPuyVveyEuCjrp6Trj4Qv7LaV7IaMKTwvc3Bhbj48c3Bhbj48aSBzdHlsZT0iYmFja2dyb3VuZDojZDk3NzA2Ij48L2k+6rSA66edPC9zcGFuPjxzcGFuPjxpIHN0eWxlPSJiYWNrZ3JvdW5kOiNjYmQ1ZTEiPjwvaT7spJHrpr0v7Ja46riJPC9zcGFuPjwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9Im92ZXJmbG93OmF1dG87bWF4LWhlaWdodDo3MnZoIj4KICAgICAgICA8dGFibGU+PHRoZWFkPjx0cj48dGg+7KKF66qpL+yekOyCsDwvdGg+PHRoPuyLnOyepTwvdGg+PHRoPu2LsOy7pDwvdGg+PHRoPuyEue2EsDwvdGg+PHRoIHN0eWxlPSJ0ZXh0LWFsaWduOnJpZ2h0Ij7slrjquIk8L3RoPjx0aCBzdHlsZT0idGV4dC1hbGlnbjpyaWdodCI+7Iuc6re464SQPC90aD48dGg+7Iqk7YOg7IqkPC90aD48dGg+7KO87JqUIOuwnOyWuOyekDwvdGg+PC90cj48L3RoZWFkPgogICAgICAgIDx0Ym9keSBpZD0iY2F0LWJvZHkiPjwvdGJvZHk+PC90YWJsZT48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJub3RlIj7tlonsnYQg7YG066at7ZWY66m0IO2VtOuLuSDsooXrqqnsnZgg7KCE6561IOyLnOq3uOuEkOunjCDrqqjslYQg67O8IOyImCDsnojsirXri4jri6QuPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGlkPSJzdWItbWF0cml4IiBjbGFzcz0ic3ViIj4KICAgICAgPGRpdiBjbGFzcz0icGFuZWwiPgogICAgICAgIDxoMj7snbjrrLwgw5cg7KKF66qpIOyKpO2DoOyKpCDrp6Ttirjrpq3siqQ8L2gyPjxkaXYgY2xhc3M9ImRlc2MiPuyFgCDsiKvsnpDripQg7ZW064u5IOuppOuyhOydmCDqt7gg7KKF66qpIOq0gOugqCDqsJzsnbgg7Iuc6re464SQIOyImCwg7IOJ7J2AIOyihe2VqSDsiqTtg6DsiqQ8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJvdmVyZmxvdzphdXRvIj48dGFibGUgaWQ9Im1hdHJpeC10YWJsZSI+PC90YWJsZT48L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICAgIDxkaXYgaWQ9InN1Yi1mZWVkIiBjbGFzcz0ic3ViIj4KICAgICAgPGRpdiBjbGFzcz0icGFuZWwiPgogICAgICAgIDxkaXYgY2xhc3M9ImNvbnRyb2xzIj4KICAgICAgICAgIDxzZWxlY3QgaWQ9InNmLXBlcnNvbiI+PC9zZWxlY3Q+PHNlbGVjdCBpZD0ic2YtZW50Ij48L3NlbGVjdD48c2VsZWN0IGlkPSJzZi1zdGFuY2UiPjwvc2VsZWN0PjxzZWxlY3QgaWQ9InNmLXR5cGUiPjwvc2VsZWN0PgogICAgICAgICAgPGlucHV0IHR5cGU9InNlYXJjaCIgaWQ9InNmLXEiIHBsYWNlaG9sZGVyPSLsi5zqt7jrhJAg64K07JqpIOqygOyDiSI+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBpZD0iZmVlZC1jb3VudCIgY2xhc3M9Im11dGVkIiBzdHlsZT0iZm9udC1zaXplOjEzcHg7bWFyZ2luLWJvdHRvbTo2cHgiPjwvZGl2PgogICAgICAgIDxkaXYgaWQ9ImZlZWQtYm9keSIgc3R5bGU9Im1heC1oZWlnaHQ6NzB2aDtvdmVyZmxvdzphdXRvIj48L2Rpdj4KICAgICAgICA8ZGl2IGlkPSJmZWVkLXBhZ2VyIiBjbGFzcz0icGFnZXIiPjwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvc2VjdGlvbj4KCiAgPCEtLSBNRU1CRVJTIC0tPgogIDxzZWN0aW9uIGlkPSJtZW1iZXJzIiBjbGFzcz0ic2VjdGlvbiI+CiAgICA8ZGl2IGNsYXNzPSJwYW5lbCIgc3R5bGU9Im1hcmdpbi1ib3R0b206MTRweCI+PGgyPu2VteyLrCDqtazshLHsm5A8L2gyPjxkaXYgY2xhc3M9ImRlc2MiPu2ZnOuPmeufiSDquLDspIAg7ZW17IusIDEz7J24LiDsubTrk5zsnZgg67KE7Yq87Jy866GcIOqwgeyekOydmCDsoITrnrUg7Iuc6re464SQ66GcIOydtOuPme2VqeuLiOuLpC48L2Rpdj48L2Rpdj4KICAgIDxkaXYgaWQ9Im1lbS1ncmlkIiBjbGFzcz0ibWdyaWQiPjwvZGl2PgogIDwvc2VjdGlvbj4KCiAgPCEtLSBHUkFQSCAtLT4KICA8c2VjdGlvbiBpZD0iZ3JhcGgiIGNsYXNzPSJzZWN0aW9uIj4KICAgIDxkaXYgY2xhc3M9InBhbmVsIj4KICAgICAgPGgyPuq0gOqzhCDqt7jrnpjtlIQ8L2gyPgogICAgICA8ZGl2IGNsYXNzPSJkZXNjIj7rqaTrsoTCt+yiheuqqcK37YWM66eI66W8IOyeh+uKlCDsp4Dsi53qt7jrnpjtlIQuIO2PrOyKpCDroIjsnbTslYTsm4PsnLzroZwg7J6Q64+ZIOuwsOy5mOuQqeuLiOuLpC48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY29udHJvbHMiPgogICAgICAgIDxzZWxlY3QgaWQ9ImctbW9kZSI+PG9wdGlvbiB2YWx1ZT0ic3RhbmNlIj7rqaTrsoQg4oaSIOyiheuqqSDsiqTtg6DsiqQ8L29wdGlvbj48b3B0aW9uIHZhbHVlPSJ0aGVtZSI+7YWM66eIIOKGlCDsooXrqqkg4oaUIOuppOuyhCDsp4Drj4Q8L29wdGlvbj48L3NlbGVjdD4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImxlZ2VuZCI+CiAgICAgICAgPHNwYW4+PGkgc3R5bGU9ImJhY2tncm91bmQ6IzBmMWIyZCI+PC9pPuuppOuyhDwvc3Bhbj48c3Bhbj48aSBzdHlsZT0iYmFja2dyb3VuZDojMjU2M2ViIj48L2k+6rWt64K0IOyiheuqqTwvc3Bhbj4KICAgICAgICA8c3Bhbj48aSBzdHlsZT0iYmFja2dyb3VuZDojMGVhNWU5Ij48L2k+66+46rWtIOyiheuqqTwvc3Bhbj48c3Bhbj48aSBzdHlsZT0iYmFja2dyb3VuZDojZDk3NzA2Ij48L2k+7J6Q7IKwKOq4iMK37L2U7J24wrfsnKDqsIApPC9zcGFuPgogICAgICAgIDxzcGFuPjxpIHN0eWxlPSJiYWNrZ3JvdW5kOiM3YzNhZWQiPjwvaT7thYzrp4g8L3NwYW4+CiAgICAgICAgPHNwYW4gc3R5bGU9Im1hcmdpbi1sZWZ0OjEwcHgiPjxpIHN0eWxlPSJiYWNrZ3JvdW5kOiMxNmEzNGEiPjwvaT7qsJXshLgg7Jej7KeAPC9zcGFuPjxzcGFuPjxpIHN0eWxlPSJiYWNrZ3JvdW5kOiNkYzI2MjYiPjwvaT7slb3shLgg7Jej7KeAPC9zcGFuPgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iZ3dyYXAiIGlkPSJncmFwaC1zdmciPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJub3RlIj7shKAg7IOJKOyKpO2DoOyKpCDrqqjrk5wpOiDstIjroZ096rCV7IS4IMK3IOu5qOqwlT3slb3shLggwrcg7ZqM7IOJPeykkeumvS/qtIDrp50uIOuFuOuTnCDtgazquLDripQg7Ja46riJIOu5iOuPhOyXkCDruYTroYDtlanri4jri6QuPC9kaXY+CiAgICA8L2Rpdj4KICA8L3NlY3Rpb24+CgogIDwhLS0gT05UT0xPR1kgLS0+CiAgPHNlY3Rpb24gaWQ9Im9udG9sb2d5IiBjbGFzcz0ic2VjdGlvbiI+CiAgICA8ZGl2IGlkPSJvbnRvLXNjaGVtYSIgY2xhc3M9InNjaGVtYS1ncmlkIj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBhbmVsIj48aDI+642w7J207YSwIOyalOyVvTwvaDI+PGRpdiBpZD0ib250by1tZXRhIj48L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InBhbmVsIj48aDI+6rWs7LaVIOuwqeuylSDCtyDtlZzqs4Q8L2gyPgogICAgICA8ZGl2IGNsYXNzPSJub3RlIj48Yj7ribTsiqQg7JWE7Lm07J2067mZOjwvYj4g64yA7ZmUIOuCtCDrqqjrk6AgVVJMKDEsNzk26rCcKeydhCDqs7XsnKDsnpDCt+yLnOqwgcK37L2U66mY7Yq47JmAIO2VqOq7mCAxMDAlIOuztOyhtO2WiOyKteuLiOuLpC4g6riw7IKsIOygnOuqqeydgCDrqaTrsoTrk6TsnbQg66eB7YGs7JmAIO2VqOq7mCDrtpnsl6zrhKPsnYAg67O466y47J2EIOykhCDri6jsnITroZwg66ek7Lmt7ZW0IDxiPjEsNjU46rG0KDkyJSk8L2I+7J2EIO2ZleuztO2WiOyKteuLiOuLpCjsm7kg7KCR7IaNIOyXhuydtCkuIOuEpOydtOuyhCDri6jstpXrp4HtgazCt+uEpOydtOuyhOuJtOyKpCDrk7HsnYAg7Jm467aAIOygkeyGjeydtCDssKjri6jrkJjslrQsIOuzuOusuOyXkOuPhCDsoJzrqqnsnbQg7JeG642YIDEzOOqxtOunjCDrr7jsiJjsp5HsnLzroZwg64Ko7JWY7Iq164uI64ukLjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJub3RlIj48Yj7tiKzsnpDsoITrnrUg7LaU7LacOjwvYj4g7KKF66qpwrfti7Dsu6TCt+2FjOuniCDsgqzsoIQgKyDsoITrnrUg7YKk7JuM65OcKOu5hOykkcK366ek7IiYwrfrp6Trj4TCt+yGkOygiMK37LCo7J217Iuk7ZiEwrfsoITrp50g65OxKeuhnCDsnpDrj5kg7LaU7Lac7ZaI7Iq164uI64ukLiDtjbzsmKgg7Iuc7ZmpL+umrOyEnOy5mCDsnpDro4wo7YKk7JuAIO2VnOyngOyYgcK3Qmxvb21iZXJnIOuTsSnripQgPGI+J+qzteycoCDrpqzshJzsuZgnPC9iPuuhnCwg66mk67KEIOuzuOyduOydmCDrp6Trp6TCt+q0gOygkOydgCA8Yj4n6rCc7J24IO2PrOyngOyFmC/qtIDsoJAnPC9iPuycvOuhnCDrtoTrpqztlojsirXri4jri6QuIO2CpOybjOuTnCDquLDrsJjsnbTrr4DroZwg7J2867aAIOyYpOu2hOulmOqwgCDsnojsnYQg7IiYIOyeiOyWtCDssLjqs6Dsmqkg7Iug7Zi466GcIOuztOyLnOq4uCDqtoztlanri4jri6QuPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9Im5vdGUiPjxiPu2VqOq7mCDsoJzqs7XrkJjripQg7YyM7J28OjwvYj4gbmV3c19hcmNoaXZlLmNzdijsoITssrQg66eB7YGsKSwgc3RyYXRlZ3lfc2lnbmFscy5qc29uKOyLnOq3uOuEkCDsm5Drs7gpLCBlbnRpdHlfY2F0YWxvZy5jc3bCt3BlcnNvbl9lbnRpdHlfbWF0cml4LmNzdsK3bWVtYmVyX3Byb2ZpbGVzLmNzdijsp5Hqs4QpLCBvbnRvbG9neS5qc29uwrdvbnRvbG9neV9ub2Rlcy9lZGdlcy5jc3Yo7KeA7Iud6re4656Y7ZSEKSwgbWVzc2FnZXMuanNvbmwo6rWs7KGw7ZmUIOybkOusuCkuPC9kaXY+CiAgICA8L2Rpdj4KICA8L3NlY3Rpb24+CjwvbWFpbj4KPGRpdiBjbGFzcz0iZm9vdCI+7ZSE66Gs7Ja07IqkIOy5tO2GoSDsmKjthqjroZzsp4Agwrcg7IOd7ISx7J28IOq4sOykgCDsnpDrj5kg67aE7ISdIMK3IO2IrOyekO2MkOuLqOydmCDssYXsnoTsnYAg67O47J247JeQ6rKMIOyeiOyKteuLiOuLpC48L2Rpdj4K").decode("utf-8")

ROLE={"ㄱ 이혜나":"운영자/대표","밝쌤👩🏻‍🏫":"강사(대표님)","황유정@ggulmoney_ssam":"강사(꿀머니쌤)",
 "김병철":"강사/리서치","김병철(봇)":"브리핑 봇","탱이":"핵심멤버","임희성":"핵심멤버(부방장)",
 "김은지":"핵심멤버","문지영":"핵심멤버","나현석":"핵심멤버","구자민":"핵심멤버(부방장)",
 "장희찬":"멤버","대성":"부방장"}
CORE=["ㄱ 이혜나","밝쌤👩🏻‍🏫","탱이","김병철","임희성","김은지","문지영",
      "황유정@ggulmoney_ssam","나현석","구자민","김병철(봇)","장희찬","대성"]
TEACHERS={"ㄱ 이혜나","밝쌤👩🏻‍🏫","황유정@ggulmoney_ssam","김병철","김병철(봇)"}

DOMAIN_MAP={
 "n.news.naver.com":(None,"news"),"m.news.naver.com":(None,"news"),
 "naver.me":("네이버 단축링크","news"),
 "plus.hankyung.com":("한국경제","news"),"hankyung.com":("한국경제","news"),
 "news.einfomax.co.kr":("연합인포맥스","news"),"kiwoom.com":("키움증권(리포트)","broker_report"),
 "v.daum.net":("다음뉴스","news"),"news.daum.net":("다음뉴스","news"),
 "g-enews.com":("글로벌이코노믹","news"),"m.g-enews.com":("글로벌이코노믹","news"),
 "biz.chosun.com":("조선비즈","news"),"chosun.com":("조선일보","news"),
 "edaily.co.kr":("이데일리","news"),"m.edaily.co.kr":("이데일리","news"),
 "yna.co.kr":("연합뉴스","news"),"m.yna.co.kr":("연합뉴스","news"),
 "mk.co.kr":("매일경제","news"),"m.mk.co.kr":("매일경제","news"),"theguru.co.kr":("더구루","news"),
 "mt.co.kr":("머니투데이","news"),"news.mt.co.kr":("머니투데이","news"),
 "wallstreetcn.com":("월스트리트(中)","news"),"kr.investing.com":("인베스팅닷컴","news"),
 "investing.com":("인베스팅닷컴","news"),"newsis.com":("뉴시스","news"),
 "newsprime.co.kr":("프라임경제","news"),"etoday.co.kr":("이투데이","news"),
 "reuters.com":("로이터","news"),"newspim.com":("뉴스핌","news"),
 "asiae.co.kr":("아시아경제","news"),"cm.asiae.co.kr":("아시아경제","news"),
 "sedaily.com":("서울경제","news"),"fnnews.com":("파이낸셜뉴스","news"),"dt.co.kr":("디지털타임스","news"),
 "youtu.be":("유튜브","video"),"youtube.com":("유튜브","video"),"m.youtube.com":("유튜브","video"),
 "t.me":("텔레그램","messenger"),"instagram.com":("인스타그램","social"),
 "blog.naver.com":("네이버블로그","blog"),"m.blog.naver.com":("네이버블로그","blog"),
 "notion.so":("노션 문서","doc"),"notion.site":("노션 문서","doc"),
 "fromusedu.kr":("프롬어스(자체)","internal"),
 "buly.kr":("단축링크","shortener"),"bit.ly":("단축링크","shortener"),
 "share.google":("구글 공유","shortener"),"han.gl":("단축링크","shortener"),
 "open.kakao.com":("오픈카톡","internal"),"invite.kakao.com":("카톡 초대","internal"),
 "pf.kakao.com":("카카오채널","internal"),"talk.kakao.com":("카카오","internal"),
}
EXTRA={
 "zdnet.co.kr":("지디넷코리아","news"),"biz.sbs.co.kr":("SBS Biz","news"),"mediapen.com":("미디어펜","news"),
 "thelec.kr":("디일렉","news"),"donga.com":("동아일보","news"),"m.donga.com":("동아일보","news"),
 "m.sedaily.com":("서울경제","news"),"ebn.co.kr":("EBN","news"),"ctee.com.tw":("공상시보(대만)","news"),
 "wsj.com":("월스트리트저널","news"),"cn.wsj.com":("월스트리트저널(中)","news"),
 "businesspost.co.kr":("비즈니스포스트","news"),"m.businesspost.co.kr":("비즈니스포스트","news"),
 "m.etoday.co.kr":("이투데이","news"),"digitaltoday.co.kr":("디지털투데이","news"),
 "joongang.co.kr":("중앙일보","news"),"hani.co.kr":("한겨레","news"),"bloomberg.com":("블룸버그","news"),
 "money.udn.com":("UDN경제일보(대만)","news"),"udn.com":("UDN(대만)","news"),
 "view.asiae.co.kr":("아시아경제","news"),"biz.newdaily.co.kr":("뉴데일리경제","news"),
 "newdaily.co.kr":("뉴데일리","news"),"electrek.co":("Electrek","news"),
 "seekingalpha.com":("Seeking Alpha","news"),"trendforce.com":("TrendForce","news"),
 "trendforce.cn":("TrendForce(中)","news"),"kmib.co.kr":("국민일보","news"),"thebell.co.kr":("더벨","news"),
 "m.thebell.co.kr":("더벨","news"),"econovill.com":("이코노믹리뷰","news"),"m.seoul.co.kr":("서울신문","news"),
 "seoul.co.kr":("서울신문","news"),"axios.com":("Axios","news"),"blockmedia.co.kr":("블록미디어","news"),
 "nytimes.com":("뉴욕타임스","news"),"cnbc.com":("CNBC","news"),"ft.com":("파이낸셜타임스","news"),
 "kedglobal.com":("코리아경제데일리(EN)","news"),"newstown.co.kr":("뉴스타운","news"),
 "imnews.imbc.com":("MBC","news"),"ddaily.co.kr":("디지털데일리","news"),
 "bbs2.shinhansec.com":("신한투자증권(리포트)","broker_report"),
 "securities.miraeasset.com":("미래에셋증권(리포트)","broker_report"),
 "bbn.kiwoom.com":("키움증권(리포트)","broker_report"),"samsungpop.com":("삼성증권(리포트)","broker_report"),
 "money2.daishin.com":("대신증권(리포트)","broker_report"),"google.com":("구글","other"),
 "cafe.naver.com":("네이버카페","community"),"finance.naver.com":("네이버금융","data"),
 "m.stock.naver.com":("네이버증권","data"),"dart.fss.or.kr":("전자공시 DART","disclosure"),
 "vo.la":("단축링크","shortener"),"zrr.kr":("단축링크","shortener"),"tinyurl.com":("단축링크","shortener"),
 "forms.gle":("구글폼","form"),"docs.google.com":("구글문서","doc"),"form.naver.com":("네이버폼","form"),
 "haunpapa.github.io":("개인 페이지","personal"),"github.io":("개인 페이지","personal"),
 "fromusacademy.kr":("프롬어스(자체)","internal"),
}
def heur(d):
    for kw in ("news","press","econom","econ","biz","finance","ilbo","sec","daily","times","post","journal","media"):
        if kw in d: return ("뉴스/금융 매체","news")
    return None

# ---- 투자전략 키워드 ----
SRC_MARKERS=["키움","한지영","Bloomberg","블룸버그","UBS","Jefferies","제프리스","골드만","Goldman","모건",
 "Morgan","JP모건","뱅크오브","BofA","[출처","출처:","출처 :","Weekly","Ep.","리서치","증권 ","증권]",
 "장 시작 전","개장전","개장 전","마감 시황","마감시황","오늘의 리서치","Three Points","컨센서스",
 "투자의견","적정주가","목표주가","Preview","1Q26","2Q26","3Q26","4Q26","시황맨","월스트리트파인더",
 "텔레그램","애널리스트","컨콜","어닝","실적 발표","잠정실적","핵심공시","로이터","Reuters","Axios",
 "다올","미래에셋","삼성증권","신한","NH투자","하나증권","BBH","CNBC","WSJ"]
POS=["비중확대","비중 확대","비중을 늘","비중 늘","비중늘","비중축소","비중 축소","비중을 줄","비중 줄",
 "담았","담아","담는","추매","추가매수","불타기","물타기","줍줍","분할매수","분할 매수","풀매수",
 "익절","손절","평단","계좌","홀딩","들고","보유중","보유 중","편입","진입했","들어갔","들어감",
 "매수했","매도했","사놨","사뒀","팔았","정리했","비중","시드"]
VIEWKW=["전망","관점","생각","예상","봅니다","보입니다","같습니다","같아요","듯","개인적으","제 생각",
 "본다","좋게","유망","수혜","주목","관심","기대","담을","사야","사고싶","눈여겨"]
BULL=["비중확대","비중 확대","비중을 늘","비중 늘","담았","담아","추매","추가매수","줍줍","분할매수","풀매수",
 "편입","진입","들어갔","사야","사고싶","유망","수혜","탑픽","톱픽","좋게","기대","매력","담을"]
BEAR=["비중축소","비중 축소","비중을 줄","비중 줄","덜어","손절","정리했","익절","차익실현","팔았","매도했",
 "조심","경계","리스크 관리","고점 부담","빼야","줄였"]
WATCH=["관심","지켜","주목","관찰","워치","후보","체크","봐야","담을지","대기","눈여겨","살펴볼"]
# 뉴스 복붙 감지(매체명/형식) — URL 동반 또는 이들 + 강세/약세 키워드 없음 → research
NEWS_HINT=["기자","특파원","연합뉴스","한국경제","매일경제","이데일리","서울경제","뉴스1","파이낸셜",
 "블로터","지디넷","조선비즈","머니투데이","헤럴드","전자신문","아시아경제","더벨","인포스탁","뉴시스",
 "[속보]","[단독]","보도"]

URLpat=re.compile(r"https?://[^\s]+")
DATE_RE=re.compile(r"^-{5,}\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(.+?)\s*-{5,}\s*$")
MSG_RE=re.compile(r"^\[([^\]]+)\]\s*\[(오전|오후)\s*(\d{1,2}):(\d{2})\]\s?(.*)$")
NAVER_ART=re.compile(r"/article/(\d{3})/(\d+)")

WEEKDAY_KO = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]

def parse_csv(path):
    """카카오톡 CSV(Date,User,Message) → parse(txt) 와 동일 msgs 스키마."""
    msgs = []
    skipped = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    for row in rows[1:]:                      # 헤더 1행 스킵
        if len(row) < 3:                       # 열 부족 방어
            skipped += 1; continue
        ds = row[0] or ""
        try:                                   # 깨진/비ISO 날짜 행 skip
            d = datetime.date(int(ds[0:4]), int(ds[5:7]), int(ds[8:10]))
        except (ValueError, IndexError):
            skipped += 1; continue
        body = row[2]
        lines = body.split("\n")               # link_records 가 m["lines"] 순회 → 필수
        msgs.append({"idx": len(msgs), "date": ds[:10], "weekday": WEEKDAY_KO[d.weekday()],
                     "time": ds[11:16], "sender": row[1].strip(),
                     "body": "\n".join(lines), "lines": lines})
    if skipped:
        print(f"[parse_csv] 스킵된 행: {skipped}건")
    return msgs

_ROOM_RE = re.compile(r"^KakaoTalk_Chat_(.+)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.(?:csv|txt)$")
_TS_TAIL_RE = re.compile(r"_\d{4}-\d{2}-\d{2}(?:[-_]\d{2}){0,3}$")
def room_of(path):
    """카톡 export 파일명 → 방 태그(선택/탈락용 아님, 근접 가드·정렬용)."""
    base = os.path.basename(path)
    m = _ROOM_RE.match(base)
    if m:
        return m.group(1)
    stem = os.path.splitext(base)[0]
    return _TS_TAIL_RE.sub("", stem)   # 끝 타임스탬프 있으면 제거, 없으면 그대로

def find_input(argv=None):
    """txt/csv 입력 자동 선택. 명시 인자 우선 → cwd·~/Downloads 의 KakaoTalk_* 최신."""
    argv = sys.argv if argv is None else argv
    for a in argv[1:]:
        if a.lower().endswith((".txt", ".csv")) and os.path.exists(a):
            return a
    cands = []
    for root in (os.getcwd(), os.path.expanduser("~/Downloads")):
        for pat in ("KakaoTalk_*.txt", "KakaoTalk_*.csv"):   # 출력 CSV 오선택 방지(prefix 제한)
            cands += glob.glob(os.path.join(root, pat))
    cands = sorted(set(cands), key=os.path.getmtime, reverse=True)
    return cands[0] if cands else None

def to24(ap,h,m):
    h=int(h);m=int(m)
    if ap=="오전" and h==12:h=0
    if ap=="오후" and h!=12:h+=12
    return f"{h:02d}:{m:02d}"
def is_text(s):
    s=s.strip(); return len(s)>=6 and not s.startswith("http") and not re.match(r"^[\s\-=•▶▪️◆●▣\*]+$",s)
def tidy(s): return re.sub(r"\s+"," ",URLpat.sub("",s)).strip(" -·•▶▪️◆●▣*\t")[:200]

def parse(txt):
    lines=open(txt,encoding="utf-8-sig").read().split("\n")
    msgs=[];cur=None;date=None;wd=None
    def flush():
        nonlocal cur
        if cur: msgs.append(cur);cur=None
    for ln in lines:
        d=DATE_RE.match(ln)
        if d:
            flush();date=f"{int(d.group(1)):04d}-{int(d.group(2)):02d}-{int(d.group(3)):02d}";wd=d.group(4);continue
        m=MSG_RE.match(ln)
        if m:
            flush();sd,ap,h,mi,b=m.groups()
            cur={"idx":len(msgs),"date":date,"weekday":wd,"time":to24(ap,h,mi),"sender":sd.strip(),"lines":[b]}
        elif cur is not None: cur["lines"].append(ln)
    flush()
    for m in msgs: m["body"]="\n".join(m["lines"])
    return msgs

def link_records(msgs):
    recs=[]
    for m in msgs:
        lines=m["lines"]
        for li,ln in enumerate(lines):
            for u in URLpat.findall(ln):
                u=u.rstrip(").,>]”’'\"")
                pre=ln[:ln.find(u)].strip(); title=""
                if is_text(pre): title=pre
                if not title:
                    for k in range(li-1,-1,-1):
                        if is_text(lines[k]) and not URLpat.search(lines[k]): title=lines[k].strip();break
                if not title:
                    for k in range(li+1,len(lines)):
                        if is_text(lines[k]) and not URLpat.search(lines[k]): title=lines[k].strip();break
                recs.append({"msg_idx":m["idx"],"date":m["date"],"time":m["time"],"sharer":m["sender"],
                             "url":u,"title":tidy(title) if title else "","title_src":"line" if title else ""})
    bym=defaultdict(list)
    for m in msgs: bym  # placeholder
    idx={m["idx"]:m for m in msgs}
    for r in recs:
        if r["title"]: continue
        i=r["msg_idx"]
        for off in (1,-1,2,-2,3,-3):
            nb=idx.get(i+off)
            if nb and nb["sender"]==r["sharer"] and not URLpat.search(nb["body"]):
                t=tidy(nb["body"])
                if len(t)>=10: r["title"]=t; r["title_src"]="near"; break
    return recs

# ===== 네트워크 해제 (캐시) =====
UA=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
OG_TITLE=re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',re.I|re.S)
OG_SITE=re.compile(r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']',re.I|re.S)
TITLE_TAG=re.compile(r"<title[^>]*>(.*?)</title>",re.I|re.S)
def http_get(url,timeout=12):
    if _SESS is not None:
        r=_SESS.get(url,headers={"User-Agent":UA},timeout=timeout,allow_redirects=True); return r.url,r.text
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        raw=resp.read()
        try: html=raw.decode("utf-8")
        except: html=raw.decode("euc-kr","ignore")
        return resp.geturl(),html
def resolve(url):
    try: final,html=http_get(url)
    except Exception as e: return {"final":"","title":"","outlet":"","err":str(e)[:60]}
    if "link.naver.com" in final:
        import urllib.parse as _up
        mm=re.search(r"[?&]url=([^&]+)",final)
        if mm: final=_up.unquote(mm.group(1))
    title=""
    m=OG_TITLE.search(html) or TITLE_TAG.search(html)
    if m:
        title=re.sub(r"\s+"," ",re.sub(r"&[a-z]+;"," ",m.group(1))).strip()
        title=re.sub(r"\s*[-|:]{1,2}\s*(네이버.*|.{0,16}(뉴스|신문|일보|경제|타임스|미디어|코리아|korea|닷컴|TV|Biz))\s*$","",title,flags=re.I).strip()
    outlet="";nm=NAVER_ART.search(final)
    if nm: outlet=NAVER_OID.get(nm.group(1),f"네이버뉴스(코드 {nm.group(1)})")
    if not outlet:
        s=OG_SITE.search(html)
        if s: outlet=s.group(1).strip()
    if not outlet: outlet=re.sub(r"^https?://(www\.)?","",final).split("/")[0]
    return {"final":final,"title":title,"outlet":outlet,"err":""}

def domain(u):
    d=urlsplit(u).netloc.lower(); return d[4:] if d.startswith("www.") else d
def enrich(links):
    for l in links:
        u=l["url"]; d=domain(u); l["domain"]=d
        g=NAVER_ART.search(u); l["naver_oid"]=g.group(1) if g else None; l["naver_aid"]=g.group(2) if g else None
        outlet,cat=DOMAIN_MAP.get(d,(None,None))
        if d in("n.news.naver.com","m.news.naver.com"):
            oid=l["naver_oid"]; outlet=NAVER_OID.get(oid,f"네이버뉴스(코드 {oid})") if oid else "네이버뉴스"; cat="news"
        if outlet is None:
            if d in EXTRA: outlet,cat=EXTRA[d]
            else:
                h=heur(d)
                if h: outlet,cat=h
                else: outlet=d or "(기타)"; cat="other"
        l["outlet"]=outlet; l["category"]=cat or "other"

def resolve_all(links,cache,do_net=True):
    def needs(l):
        d=l["domain"]; isn=("naver.me" in d) or ("news.naver.com" in d)
        return isn and (not l["title"] or "naver.me" in d)
    todo=[l for l in links if needs(l) and l["url"] not in cache]
    new=0
    if do_net and todo:
        print(f"  네이버 신규 해제: {len(todo)}개 접속 중...")
        def work(l): return l["url"],resolve(l["url"])
        with ThreadPoolExecutor(max_workers=8) as ex:
            for f in as_completed([ex.submit(work,l) for l in todo]):
                u,res=f.result()
                if res.get("final"): cache[u]=res
                new+=1
    # 캐시 적용
    for l in links:
        c=cache.get(l["url"])
        if c and c.get("final"):
            l["resolved_url"]=c["final"]
            if c.get("title") and not l["title"]: l["title"]=c["title"]; l["title_src"]="web"
            if c.get("outlet"): l["outlet"]=c["outlet"]
        else:
            l.setdefault("resolved_url","")
    return new

# ===== 투자전략 =====
def find_ents(b):
    s=set()
    for c,info in ENTITIES.items():
        for a in info["al"]:
            if a in b: s.add(c);break
    return s
def find_ths(b):
    s=set()
    for th,al in THEMES.items():
        for a in al:
            if a in b: s.add(th);break
    return s
def hit(t,kws): return [k for k in kws if k in t]

W_ATTR = 60
STANCE_SIGNAL = POS + VIEWKW + WATCH + BULL + BEAR   # 귀속 게이팅 신호(%·목표가 제외)

def _ascii_alnum(c):
    return bool(c) and c.isascii() and c.isalnum()

def _alias_spans(body, alias):
    """공백패딩 alias(' AMD','AMD ')는 strip 후 매칭. 영문은 ASCII 영숫자만 경계
       (한글/공백/기호는 경계 통과 → 'AMD 추매' 귀속, 'AMDOCS' 제외). 한글은 substring."""
    surf = alias.strip()
    if not surf:
        return []
    spans = []
    for m in re.finditer(re.escape(surf), body):
        i, j = m.start(), m.end()
        if surf.isascii():
            b = body[i-1] if i > 0 else ""
            a = body[j] if j < len(body) else ""
            if _ascii_alnum(b) or _ascii_alnum(a):
                continue
        spans.append((i, j))
    return spans

def attribute_stocks(body, is_src):
    """find_ents 후보 → ±60 stance 게이팅 + 인접종목 절단 세그먼트로 [(canon, stance)]."""
    cand = list(find_ents(body))
    spans_by = {c: [s for al in ENTITIES[c]["al"] for s in _alias_spans(body, al)] for c in cand}
    marks = sorted((i, j, c) for c, sp in spans_by.items() for (i, j) in sp)
    out = []
    for canon in cand:
        sp = spans_by[canon]
        if not sp:                                              # 경계인식 등장 없음(영문 오탐)
            continue
        gate = " ".join(body[max(0, i-W_ATTR): j+W_ATTR] for (i, j) in sp)
        if not any(k in gate for k in STANCE_SIGNAL):           # 주변 stance 신호 없음 → 도배 제외
            continue
        if is_src:
            stance = "자료"
        else:
            others = sorted(oi for (oi, oj, oc) in marks if oc != canon)
            cut = []                                            # 한국어 후치: 좌=자기 시작, 우=다음 다른종목 시작
            for (i, j) in sp:
                hi = j + W_ATTR
                for oi in others:
                    if oi >= j:
                        hi = min(hi, oi); break
                cut.append(body[i: hi])
            seg = " ".join(cut)
            bu, be, wa = hit(seg, BULL), hit(seg, BEAR), hit(seg, WATCH)
            if len(bu) > len(be): stance = "bullish"
            elif len(be) > len(bu): stance = "bearish"
            elif wa and not (bu or be): stance = "watch"
            elif bu and be: stance = "mixed"
            else: stance = "neutral"
        out.append((canon, stance))
    return out

def strategy(msgs):
    sig=[]
    for m in msgs:
        body=m["body"]; text=URLpat.sub("",body).strip()
        if len(text)<6: continue
        ents=find_ents(body); ths=find_ths(body)
        if not(ents or ths): continue
        is_src=any(mk in body for mk in SRC_MARKERS)
        pos=hit(text,POS); view=hit(text,VIEWKW); watch=hit(text,WATCH); bull=hit(text,BULL); bear=hit(text,BEAR)
        is_news=bool(URLpat.search(body) or any(k in body for k in NEWS_HINT)) and not(bull or bear)
        is_research=is_src or is_news
        if is_research: stype="research"; stance="자료"
        else:
            if pos: stype="position"
            elif view or watch: stype="view"
            else: continue
            if len(bull)>len(bear): stance="bullish"
            elif len(bear)>len(bull): stance="bearish"
            elif watch and not(bull or bear): stance="watch"
            elif bull and bear: stance="mixed"
            else: stance="neutral"
        sig.append({"msg_idx":m["idx"],"date":m["date"],"time":m["time"],"sharer":m["sender"],
            "entities":sorted(ents),"themes":sorted(ths),"stance":stance,"type":stype,
            "stocks":attribute_stocks(body, is_research),
            "snippet":re.sub(r"\s+"," ",text)[:220],
            "full":re.sub(r"[ \t]+"," ",text).strip()[:1500],  # URL 제거된 원문 (body 아님)
            "core":m["sender"] in CORE,"teacher":m["sender"] in TEACHERS})
    return sig

# ===== 집계 =====
def aggregate(msgs, sig):
    personal=[s for s in sig if s["type"]!="research"]
    mention=Counter()
    for m in msgs:
        b=m["body"]
        for c,info in ENTITIES.items():
            if any(a in b for a in info["al"]): mention[c]+=1
    ent_sig=defaultdict(Counter); ent_sh=defaultdict(Counter); ent_dt=defaultdict(list)
    for s in personal:
        for e in s["entities"]:
            ent_sig[e][s["stance"]]+=1; ent_sh[e][s["sharer"]]+=1; ent_dt[e].append(s["date"])
    ent_rows=[]
    for c,info in ENTITIES.items():
        if mention[c]==0 and not ent_sig[c]: continue
        sc=ent_sig[c]
        ent_rows.append({"entity":c,"market":info["m"],"ticker":info["tk"],"sector":info["sec"],
            "mentions":mention[c],"personal_signals":sum(sc.values()),"bullish":sc["bullish"],
            "bearish":sc["bearish"],"watch":sc["watch"],"neutral":sc["neutral"]+sc["mixed"],
            "top_voices":";".join(f"{k}({v})" for k,v in ent_sh[c].most_common(3)),
            "first":min(ent_dt[c]) if ent_dt[c] else "","last":max(ent_dt[c]) if ent_dt[c] else ""})
    ent_rows.sort(key=lambda r:-r["mentions"])
    pe=defaultdict(Counter); pem_idx=defaultdict(list)
    for s in personal:
        for e in s["entities"]: pe[(s["sharer"],e)][s["stance"]]+=1; pem_idx[(s["sharer"],e)].append(s["msg_idx"])
    pe_rows=[]
    for (p,e),sc in sorted(pe.items(),key=lambda kv:-sum(kv[1].values())):
        b,br,wt=sc["bullish"],sc["bearish"],sc["watch"]
        lean="강세" if b>br and b>=wt else("약세" if br>b else("관망" if wt>=max(b,br) and wt>0 else "중립"))
        pe_rows.append({"person":p,"role":ROLE.get(p,"멤버"),"entity":e,"ticker":ENTITIES[e]["tk"],
            "total":sum(sc.values()),"bullish":b,"bearish":br,"watch":wt,"neutral":sc["neutral"]+sc["mixed"],
            "lean":lean,"msg_idxs":";".join(map(str,pem_idx[(p,e)][:30]))})
    mcount=Counter(m["sender"] for m in msgs); lcount=Counter()
    m_ent=defaultdict(Counter); m_th=defaultdict(Counter); m_st=defaultdict(Counter)
    for s in personal:
        for e in s["entities"]: m_ent[s["sharer"]][e]+=1
        for t in s["themes"]: m_th[s["sharer"]][t]+=1
        m_st[s["sharer"]][s["stance"]]+=1
    prof=[]
    for p in CORE:
        prof.append({"member":p,"role":ROLE.get(p,"멤버"),"is_teacher":p in TEACHERS,
            "messages":mcount[p],"links_shared":LINKCOUNT.get(p,0),"personal_signals":sum(m_st[p].values()),
            "bullish":m_st[p]["bullish"],"bearish":m_st[p]["bearish"],"watch":m_st[p]["watch"],
            "top_entities":";".join(f"{k}({v})" for k,v in m_ent[p].most_common(6)),
            "top_themes":";".join(f"{k}({v})" for k,v in m_th[p].most_common(5))})
    prof.sort(key=lambda r:-r["messages"])
    th_total=Counter()
    for m in msgs:
        for t,al in THEMES.items():
            if any(a in m["body"] for a in al): th_total[t]+=1
    th_sig=Counter()
    for s in personal:
        for t in s["themes"]: th_sig[t]+=1
    th_rows=[{"theme":t,"mentions":n,"personal_signals":th_sig[t]} for t,n in th_total.most_common()]
    return ent_rows,pe_rows,prof,th_rows,th_total

SEC2THEME={"반도체":"반도체","반도체장비":"반도체","AI반도체":"AI","메모리":"HBM/메모리","파운드리":"파운드리",
 "전력/원전":"원전/SMR","전력인프라":"전력인프라","전선":"전력인프라","방산":"방산","조선":"조선","조선/방산":"조선",
 "방산/철도":"방산","방산/우주":"우주/위성","로봇":"로봇/휴머노이드","2차전지":"2차전지","2차전지소재":"2차전지",
 "전기차/AI":"자율주행","SMR/원전":"원전/SMR","가상자산":"가상자산","바이오":"바이오/제약","엔터":"엔터",
 "원전연료":"원전/SMR","희토류":"희토류"}
def ontology(msgs,sig,links,th_total):
    personal=[s for s in sig if s["type"]!="research"]
    nodes=[];edges=[]
    mcount=Counter(m["sender"] for m in msgs); lcount=Counter(l["sharer"] for l in links)
    m_th=defaultdict(Counter); m_st=defaultdict(Counter)
    for s in personal:
        for t in s["themes"]: m_th[s["sharer"]][t]+=1
        m_st[s["sharer"]][s["stance"]]+=1
    ids=set()
    def node(i,t,l,**k): nodes.append({"id":i,"type":t,"label":l,**k}); ids.add(i)
    for p in CORE:
        node(f"M:{p}","Member",p,role=ROLE.get(p,"멤버"),is_teacher=p in TEACHERS,
             messages=mcount[p],links=lcount[p],signals=sum(m_st[p].values()))
    for t,n in th_total.items(): node(f"T:{t}","Theme",t,mentions=n)
    mention=Counter()
    for m in msgs:
        b=m["body"]
        for c,info in ENTITIES.items():
            if any(a in b for a in info["al"]): mention[c]+=1
    ent_st=defaultdict(Counter)
    for s in personal:
        for e in s["entities"]: ent_st[e][s["stance"]]+=1
    for c,info in ENTITIES.items():
        if mention[c]==0: continue
        sc=ent_st[c]
        node(f"E:{c}","Entity",c,market=info["m"],ticker=info["tk"],sector=info["sec"],
             mentions=mention[c],signals=sum(sc.values()),bullish=sc["bullish"],bearish=sc["bearish"],watch=sc["watch"])
        th=SEC2THEME.get(info["sec"])
        if th and f"T:{th}" in ids: edges.append({"source":f"E:{c}","target":f"T:{th}","rel":"BELONGS_TO"})
    oc=Counter(l["outlet"] for l in links)
    for o,n in oc.most_common():
        if n>=3: node(f"O:{o}","Outlet",o,count=n)
    pe=defaultdict(Counter)
    for s in personal:
        for e in s["entities"]: pe[(s["sharer"],e)][s["stance"]]+=1
    for (p,e),sc in pe.items():
        b,br,wt=sc["bullish"],sc["bearish"],sc["watch"]
        lean="bullish" if b>br and b>=wt else("bearish" if br>b else("watch" if wt>=max(b,br) and wt>0 else "neutral"))
        edges.append({"source":f"M:{p}","target":f"E:{e}","rel":"HAS_STANCE","weight":sum(sc.values()),
                      "bullish":b,"bearish":br,"watch":wt,"lean":lean})
    for p in CORE:
        for t,n in m_th[p].most_common(8):
            if n>=2 and f"T:{t}" in ids: edges.append({"source":f"M:{p}","target":f"T:{t}","rel":"FOCUSES_ON","weight":n})
    mo=defaultdict(Counter)
    for l in links: mo[l["sharer"]][l["outlet"]]+=1
    for p in CORE:
        for o,n in mo[p].most_common(6):
            if n>=2 and f"O:{o}" in ids: edges.append({"source":f"M:{p}","target":f"O:{o}","rel":"SHARES","weight":n})
    return nodes,edges

# ===== 중복 정리 =====
TRACK={"utm_source","utm_medium","utm_campaign","utm_term","utm_content","ref","sns","cds","sid",
       "from","botref","botevent","input","si","lfrom","rc","ntype","t","cd","s","fbclid","gclid","sicode"}
def artkey(l):
    u=l.get("resolved_url") or l["url"]
    g=NAVER_ART.search(u)
    if g: return "naver:"+g.group(1)+"/"+g.group(2)
    sp=urlsplit(u); q=[(k,v) for k,v in parse_qsl(sp.query) if k.lower() not in TRACK]
    return "url:"+sp.scheme+"://"+sp.netloc.replace("www.","")+sp.path.rstrip("/")+("?"+urlencode(sorted(q)) if q else "")
LBL_KW=["기사를 공유합니다","기사 공유","원문 확인","원문확인","보고서 링크","리포트 링크","보고서링크","리포트링크",
    "톡게시판","메시지가 삭제","키움 한지영","공유합니다","공유드립니다","참고하세요","참고 부탁","좋은 아침",
    "굿모닝","오늘의 리서치 자료","링크:","링크 :","출처 :","출처:","원글 출처"]
LBL_EXACT={"키움 한지영","한지영","리포트 링크","보고서 링크","※ 원문 확인:","기사를 공유합니다:","메시지가 삭제되었습니다."}
def is_boiler(t):
    s=(t or "").strip()
    if not s: return False
    if len(s)<=3: return True
    if s in LBL_EXACT: return True
    if len(s)<22 and (s.endswith(":") or s.endswith("：")): return True
    if any(k in s for k in LBL_KW) and len(s)<40: return True
    return False
def dedup(links):
    for l in links: l["artkey"]=artkey(l)
    art_n=Counter(l["artkey"] for l in links)
    title_arts=defaultdict(set)
    for l in links:
        if l.get("title"): title_arts[l["title"]].add(l["artkey"])
    for l in links:
        t=l.get("title","")
        if is_boiler(t) and l.get("title_src")!="web": l["clean_title"]="";l["was_label"]=True
        else: l["clean_title"]=t;l["was_label"]=False
        if art_n[l["artkey"]]>=2: l["dup_type"]="재공유"
        elif t and len(title_arts[t])>=2: l["dup_type"]="라벨중복"
        else: l["dup_type"]="고유"
        l["share_count"]=art_n[l["artkey"]]
    groups=defaultdict(list)
    for l in links: groups[l["artkey"]].append(l)
    uniq=[]
    for ak,rows in groups.items():
        rs=sorted(rows,key=lambda r:r["date"]+r["time"])
        rep=next((r for r in rs if r["clean_title"]),rs[0])
        sharers=list(dict.fromkeys(r["sharer"] for r in rs))
        uniq.append({"i":rep["msg_idx"],"d":rs[0]["date"],"s":sharers[0],"sn":len(sharers),"n":len(rows),
            "o":rep.get("outlet",""),"c":rep.get("category",""),"u":rep.get("resolved_url") or rep["url"],
            "ti":rep["clean_title"],"lab":1 if rep["was_label"] else 0,
            "dt":"재공유" if len(rows)>=2 else rep["dup_type"]})
    uniq.sort(key=lambda x:x["d"],reverse=True)
    return uniq

# ===== 뷰어 =====
def build_viewer(vd):
    data=json.dumps(vd,ensure_ascii=False).replace("</","<\\/")
    html=("<!DOCTYPE html>\n<html lang=\"ko\"><head>\n<meta charset=\"utf-8\">\n"
      "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
      "<title>프롬어스 카톡 온톨로지 아카이브</title>\n<style>"+CSS+"</style>\n</head><body>\n"
      +BODY+"\n<script>const DATA="+data+";</script>\n<script>"+JS+"</script>\n</body></html>")
    open(P("프롬어스_온톨로지_뷰어.html"),"w",encoding="utf-8").write(html)

LINKCOUNT={}
def main():
    do_net="--no-resolve" not in sys.argv
    path=find_input()
    if not path: print("[!] 카카오톡 .txt/.csv 를 찾지 못했습니다. 인자로 경로를 주거나 ~/Downloads 에 두세요."); return
    print(f"▶ 입력: {os.path.basename(path)}")
    msgs = parse_csv(path) if path.lower().endswith(".csv") else parse(path)
    if not msgs: print("[!] 메시지가 비어 있습니다(파싱 0건)."); return
    links=link_records(msgs); enrich(links)
    global LINKCOUNT; LINKCOUNT=Counter(l["sharer"] for l in links)
    print(f"▶ 메시지 {len(msgs)} · 링크 {len(links)} · 로컬제목 {sum(1 for l in links if l['title'])}")
    cache={}
    cf=P("resolve_cache.json")
    if os.path.exists(cf):
        try: cache=json.load(open(cf,encoding="utf-8"))
        except: cache={}
    new=resolve_all(links,cache,do_net)
    json.dump(cache,open(cf,"w",encoding="utf-8"),ensure_ascii=False)
    print(f"▶ 네이버 해제: 신규 {new} · 캐시총 {len(cache)} · 적용 {sum(1 for l in links if l.get('resolved_url'))}")
    sig=strategy(msgs)
    ent_rows,pe_rows,prof,th_rows,th_total=aggregate(msgs,sig)
    nodes,edges=ontology(msgs,sig,links,th_total)
    uniq=dedup(links)
    personal=[s for s in sig if s["type"]!="research"]; research=[s for s in sig if s["type"]=="research"]
    titled=sum(1 for l in links if l["clean_title"]); resolved=sum(1 for l in links if l.get("resolved_url"))
    meta={"channel":"프롬어스 오픈카톡(정규반)","date_from":msgs[0]["date"],"date_to":msgs[-1]["date"],
      "messages":len(msgs),"members_total":len(set(m["sender"] for m in msgs)),"members_core":len(CORE),
      "links_total":len(links),"news_links":sum(1 for l in links if l["category"]=="news"),
      "strategy_personal":len(personal),"strategy_research":len(research),
      "titled":titled,"titled_pct":round(titled/len(links)*100),"resolved":resolved,
      "unique_articles":len(uniq),"reshare_rows":sum(1 for l in links if l["dup_type"]=="재공유"),
      "label_rows":sum(1 for l in links if l["dup_type"]=="라벨중복")}
    schema={"node_types":["Member","Theme","Entity(종목/자산)","Outlet(언론사)","NewsItem","StrategySignal"],
      "edge_types":["SHARED(멤버→뉴스)","PUBLISHED_BY(뉴스→언론사)","HAS_STANCE(멤버→종목)",
        "BELONGS_TO(종목→테마)","FOCUSES_ON(멤버→테마)","SHARES(멤버→언론사)"]}
    tl=defaultdict(lambda:{"msgs":0,"links":0})
    for m in msgs: tl[m["date"]]["msgs"]+=1
    for l in links: tl[l["date"]]["links"]+=1
    timeline=[{"date":d,"msgs":v["msgs"],"links":v["links"]} for d,v in sorted(tl.items())]
    outr=Counter(l["outlet"] for l in links if l["category"] in("news","broker_report"))
    outlets=[{"outlet":o,"count":n} for o,n in outr.most_common(40)]
    sigs=[{"i":s["msg_idx"],"d":s["date"],"s":s["sharer"],"e":s["entities"],"th":s["themes"],
           "st":s["stance"],"ty":s["type"],"x":s["snippet"]} for s in sig]
    vd={"meta":meta,"schema":schema,"members":prof,"entities":ent_rows,"themes":th_rows,
        "person_entity":pe_rows,"outlets":outlets,"categories":dict(Counter(l["category"] for l in links)),
        "timeline":timeline,"news":uniq,"signals":sigs,"graph":{"nodes":nodes,"edges":edges}}
    build_viewer(vd)
    # ===== 온톨로지_데이터 폴더 전체 자동 갱신 =====
    DDIR=P("온톨로지_데이터"); os.makedirs(DDIR,exist_ok=True)
    def DP(*a): return os.path.join(DDIR,*a)
    def wcsv(path,rows):
        if not rows: return
        try: f=open(path,"w",encoding="utf-8-sig",newline="")
        except PermissionError:
            b,e=os.path.splitext(path); path=b+"_new"+e
            print(f"  (열려있어 {os.path.basename(path)}로 저장)"); f=open(path,"w",encoding="utf-8-sig",newline="")
        with f:
            w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    def wjson(path,obj):
        try: json.dump(obj,open(path,"w",encoding="utf-8"),ensure_ascii=False)
        except PermissionError:
            b,e=os.path.splitext(path); json.dump(obj,open(b+"_new"+e,"w",encoding="utf-8"),ensure_ascii=False)
    cols=["msg_idx","date","time","sharer","outlet","category","dup_type","share_count",
          "clean_title","title","title_src","url","resolved_url","artkey"]
    wcsv(DP("뉴스_전체아카이브.csv"),[{c:l.get(c,"") for c in cols} for l in links])
    wcsv(DP("종목_카탈로그.csv"),ent_rows)
    wcsv(DP("인물x종목_매트릭스.csv"),pe_rows)
    wcsv(DP("멤버_프로필.csv"),prof)
    wcsv(DP("테마_카탈로그.csv"),th_rows)
    wjson(DP("전략시그널.json"),sig)
    wjson(DP("온톨로지_그래프.json"),{"schema":schema,"meta":meta,"nodes":nodes,"edges":edges})
    wcsv(DP("온톨로지_노드.csv"),[{"id":n["id"],"type":n["type"],"label":n["label"],
        "extra":json.dumps({k:v for k,v in n.items() if k not in("id","type","label")},ensure_ascii=False)} for n in nodes])
    wcsv(DP("온톨로지_엣지.csv"),[{"source":e["source"],"target":e["target"],"rel":e["rel"],
        "extra":json.dumps({k:v for k,v in e.items() if k not in("source","target","rel")},ensure_ascii=False)} for e in edges])
    wjson(DP("링크_제목포함.json"),links)
    try:
        with open(DP("메시지_구조화원문.jsonl"),"w",encoding="utf-8") as f:
            for m in msgs:
                uu=URLpat.findall(m["body"])
                f.write(json.dumps({"idx":m["idx"],"date":m["date"],"weekday":m.get("weekday"),
                    "time":m["time"],"sender":m["sender"],"body":m["body"],"urls":uu,"n_urls":len(uu)},
                    ensure_ascii=False)+"\n")
    except PermissionError: pass
    # ===== chat_kb.json 생성 (리포 루트, public=False=실명 유지). 병합은 CI build_hub.py 전담 =====
    try:
        import chat_to_kb
        kb=chat_to_kb.build(msgs, links, sig)
        REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out=os.path.join(REPO_ROOT,"chat_kb.json")
        json.dump(kb, open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"▶ chat_kb.json 생성: {out} (stocks {len(kb['stocks'])})")
    except Exception as e:
        print(f"  (chat_kb.json 생성 실패: {str(e)[:80]})")
    print(f"▶ 완료: 고유기사 {len(uniq)} · 전략 개인 {len(personal)}/리서치 {len(research)} · 노드 {len(nodes)}/엣지 {len(edges)}")
    print(f"▶ 저장: 프롬어스_온톨로지_뷰어.html · 온톨로지_데이터/ (11개 파일 갱신)")

if __name__=="__main__":
    import traceback
    try: main()
    except SystemExit: pass
    except BaseException:
        print("\n[오류] 아래를 복사해 알려주세요:\n"); traceback.print_exc()
    finally:
        try: input("\n===== 끝났습니다. Enter 키로 닫기 =====\n")
        except Exception: pass
