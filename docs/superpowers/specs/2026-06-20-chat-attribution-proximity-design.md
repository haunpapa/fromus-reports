# 채팅 생성단계 정확귀속 — proximity 게이팅 (2단계-B)

- 날짜: 2026-06-20
- 상태: 설계 승인(규칙 비교로 Aw 확정) → 구현 계획 대기
- 선행: 2단계-A(생성기 CSV+원문+리포보관) 완료·배포.
- 접근/범위(확정): **규칙 정교화**(LLM 아님), **전체 proximity**(시황+의견), 공격성 **Aw(±60, stance 신호)**.

## 1. 배경

종목 카드의 💬 채팅 근거가 종목과 무관하게 도배된다. 근본 원인: `chat_to_kb.build`가 `strategy()`의 `signal["entities"]`(= `find_ents`의 **본문 전체 substring 매칭**)를 무비판적으로 전부 mention에 복제한다. 테마 귀속(`match_themes_for_stock`)은 이미 종목명 주변 ±36자 proximity 게이팅이 있는데, **종목 mention 귀속에는 없다.**

### 1.1 진단 (최신 11,316 메시지 실측)
- mention 분포: research **2,303**(78%) / view 452 / position 178
- snippet에 종목명 실제 포함: **36%**(research 31%) → 64%가 해당 종목명 없이 귀속
- 메시지당 귀속 종목 수: 평균 2.97, **최대 24**, 5+종목 메시지 169개(시황 1개가 최대 24종목에 복제)

### 1.2 규칙 비교 분석 (5규칙, `/tmp/compare_attr.py`)
아래는 **경계로직 교정 후**(영문 alias strip + ASCII-only 경계, §3.1) 수치다.

| 규칙 | 귀속쌍 | vs현행 | 최대 | 5+종목 | 비고 |
|---|---|---|---|---|---|
| 현행(baseline) | 3,718 | — | 24 | 169 | — |
| 보수 B(경계인식 등장만) | 3,729 | +0% | 24 | 171 | 한글 종목명이라 substring과 사실상 동일 → **무의미** |
| 완화 A'(±60 + 등락%/목표가) | 2,469 | -34% | 24 | 121 | 시황은 종목마다 %가 붙어 나열이 다 "신호" → **시황 도배 못 막음(역효과)** |
| **공격 Aw(±60, stance) ← 채택** | **1,483** | **-61%** | **14** | **62** | 도배 제거 + false negative 완화의 균형점 |
| 공격 A(±40, stance) | 1,170 | -69% | 11 | 36 | 더 강력하나 짧은 코멘트 놓쳐 false negative 큼(삼성/하이닉스 탈락) |

**결론**: 보수·완화는 탈락. `%` 신호는 시황 나열을 전부 살려 역효과 → **제외**. `stance` 키워드 기반 + window ±60(`Aw`)이 도배 제거(-61%, 최대 24→14)와 false negative 사이 균형점. (경계로직 교정으로 AMD 등 영문 종목의 한글 문맥 등장이 살아나 Aw가 1,431→1,483으로 소폭 증가했으나 도배 제거 효과는 유지.)

## 2. 목표 / 비목표

### 목표
- mention 귀속을 **"종목 표면형이 본문에 (영문은 경계인식) 등장 + 주변 ±60자에 stance 신호가 있을 때만"** 으로 변경(도배 제거).
- 종목별 stance 재계산(메시지 단위 stance 복제 → 종목 주변 세그먼트 기준).

### 비목표
- 종목 사전 통합(`update_archive.ENTITIES` ↔ `taxonomy.STOCK_META`) — `_CANON_ALIGN` 정렬 유지, 통합은 후속.
- LLM 분류, 소비단계(merge_hub/hub_template/co_edges) 변경, `find_ents` 전역 시그니처 변경, 등락%/목표가 신호(역효과).
- 뷰어/온톨로지 산출(`aggregate`/`ontology`) 동작 변경 — `entities`/`stance` 필드 **유지**로 무변경 보장.

## 3. 설계

### 3.1 `strategy()` (generator/update_archive.py) — `stocks` 필드 추가
`aggregate`/`ontology`가 `s["entities"]`·`s["stance"]`에 의존하므로 **그 두 필드는 그대로 두고**, 신규 `s["stocks"] = [(canon, stance), …]`(종목별 proximity 귀속+stance)를 추가한다. `chat_to_kb`만 `stocks`를 사용.

신규 헬퍼(같은 모듈):
```python
W_ATTR = 60
STANCE_SIGNAL = POS + VIEWKW + WATCH + BULL + BEAR   # 귀속 게이팅 신호(%·목표가 제외)

def _ascii_alnum(c):
    return bool(c) and c.isascii() and c.isalnum()

def _alias_spans(body, alias):
    """alias 등장 위치들. 공백패딩 alias(' AMD','AMD ')는 strip 후 매칭.
       영문 표면형은 ASCII 영숫자만 경계로 인정(한글/공백/기호는 경계 통과 → 'AMD 추매' 귀속, 'AMDOCS' 제외).
       한글 표면형은 substring(경계검사 없음 — find_ents 상속, §6 한글 오탐 주의)."""
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
    """find_ents 후보를 proximity 게이팅(±60 stance 신호) → [(canon, stance)].
       귀속 게이팅은 ±W(관대)로 수치 유지, stance는 인접 종목 위치로 절단한 세그먼트로 계산(겹침 혼입 방지)."""
    cand = list(find_ents(body))
    spans_by = {c: [s for al in ENTITIES[c]["al"] for s in _alias_spans(body, al)] for c in cand}
    marks = sorted((i, j, c) for c, sp in spans_by.items() for (i, j) in sp)   # 절단 경계용
    out = []
    for canon in cand:
        sp = spans_by[canon]
        if not sp:                                          # 경계인식 등장 없음(영문 오탐)
            continue
        gate = " ".join(body[max(0, i-W_ATTR): j+W_ATTR] for (i, j) in sp)
        if not any(k in gate for k in STANCE_SIGNAL):       # 주변 stance 신호 없음 → 도배 제외
            continue
        if is_src:
            stance = "자료"                                 # 시황은 stance 라벨 유지
        else:
            others = sorted(oi for (oi, oj, oc) in marks if oc != canon)
            cut = []                                        # 한국어 후치 서술: 좌=자기 등장 시작, 우=다음 다른 종목 시작
            for (i, j) in sp:
                hi = j + W_ATTR
                for oi in others:
                    if oi >= j:
                        hi = min(hi, oi); break
                cut.append(body[i: hi])                      # 전방 수식("강력추천 삼성")은 감수(§6 한계)
            seg = " ".join(cut)
            bu, be, wa = hit(seg, BULL), hit(seg, BEAR), hit(seg, WATCH)
            if len(bu) > len(be): stance = "bullish"
            elif len(be) > len(bu): stance = "bearish"
            elif wa and not (bu or be): stance = "watch"
            elif bu and be: stance = "mixed"
            else: stance = "neutral"
        out.append((canon, stance))
    return out
```
`strategy()`의 `sig.append({...})` 에 `"stocks": attribute_stocks(body, is_src)` 추가(나머지 필드·`entities`·`stance` 불변).

### 3.2 `chat_to_kb.build()` — mention 귀속을 `stocks` 기준으로
mention 루프를 `s["entities"]`(전체) → `s["stocks"]`(proximity)로 변경하고, 종목별 stance 사용:
```python
for s in signals:
    for e, st_stance in s.get("stocks", []):
        st = S(e)
        ment = {"date": s["date"], "sharer": s["sharer"], "source": "chat",
                "stance": st_stance, "type": s["type"], "snippet": s["snippet"][:180]}
        if s.get("type") in ("view", "position"):
            ment["full"] = s.get("full", "")
        st["mentions"].append(ment)
```
- `s.get("stocks", [])` — 구버전 signal(stocks 없음) 방어. count(`match_stocks`)·테마(`match_themes_for_stock`)는 현행 유지(이미 정확).

### 3.3 규칙 상세 (확정 기본값)
- window ±60자, 신호 = `POS/VIEWKW/WATCH/BULL/BEAR` 키워드(등락%·목표가는 **제외** — 역효과 입증).
- 종목 등장 = 영문 alias 단어경계 / 한글 alias substring(`find_ents` 후보 그대로).
- 종목별 stance: 시황(research)은 `"자료"`; 의견은 세그먼트 합본의 bull/bear/watch 우세.
- 신호 없는 단순 나열 종목 → 귀속 제외(도배 차단).
- 종목별 stance 는 **인접 종목 위치로 절단한 세그먼트**로 계산(겹침 stance 혼입 방지). 단 `snippet`/`full` 은 **메시지 전체 유지**(2단계-A 원문 보존) — 복수 종목 메시지는 모달 본문에 다른 종목 언급이 함께 보일 수 있음(의식적 한계).

## 4. 검증 (정답 라벨 없음 → before/after + 수동)

### 4.1 정량 (목표치, Aw 분석 기준)
- 귀속쌍 3,718 → **약 1,483(-61%)**, 메시지당 최대 24 → **약 14**, 5+종목 메시지 169 → **약 62**
- snippet 종목명 포함률 36% → **상승**(귀속이 종목 등장 기반)
- co_edges(관계망) 가짜 동시언급 쌍 감소(자동)
- 검증 재현 도구로 `generator/compare_attr.py` 보관(규칙 변경 시 재측정).

### 4.2 수동 / 회귀
- 무작위 20 mention이 실제 그 종목 관련인지 수동 검수
- false negative: 명확한 의견("삼성전자 좋게 봄")은 유지되는지(샘플)
- 뷰어/온톨로지 무변경: `aggregate`/`ontology` 산출이 동일(entities/stance 불변)
- **소비처 산출물 before/after**(재생성 후 `knowledge_base.merged.json`): chat 블록 보유 종목 수, market_news 건수, `co_edges` 쌍수, `stance_summary`(강세/약세/관망이 mixed 편중으로 0에 수렴하지 않는지)
- **영문 종목 회귀**: AMD 등 공백패딩 alias 종목이 한글 문맥에서 귀속되는지 + `mentions=0`으로 채팅전용 종목(`count<2 and not mentions`)에서 탈락하지 않는지
- **근접 복수종목 stance 분리**: "삼성전자 손절 … 하이닉스 추매" 단문에서 삼성=bearish·하이닉스=bullish 로 분리되는지

### 4.3 단위 테스트 (`generator/test_parse.py` 확장)
- `attribute_stocks`(픽스처는 매직넘버 금지 — `U.W_ATTR`·`U.ENTITIES`·`U.BULL` 등에서 동적 추출, 단 AMD 케이스는 `'AMD' in U.ENTITIES` assert 선행):
  ① 종목+stance 근접 → 귀속
  ② stance 멀리(filler `'가'*(U.W_ATTR+10)`) → 제외
  ③ **영문 경계(양성+음성)**: `'AMD 추매'` → AMD **귀속**(경계로직 교정 전엔 실패 = RED), `'AMDOCS는'` → AMD **제외**
  ④ 시황(is_src) stance="자료"
  ⑤ **근접 복수종목 절단**: "삼성전자 손절 … 하이닉스 추매" → 삼성=bearish·하이닉스=bullish 분리
- 순서: ③ 양성 케이스를 먼저 RED 로 작성 → `_alias_spans` strip/ASCII-경계 구현으로 GREEN.
- 회귀: `strategy()` 가 여전히 `entities`/`stance` 필드를 (현행과 동일하게) 산출.

## 5. 파일 변경
- **수정**: `generator/update_archive.py`(`_alias_spans`·`attribute_stocks` 신규 + `strategy` sig 에 `stocks` 추가), `generator/chat_to_kb.py`(mention 루프 stocks 기준), `generator/test_parse.py`(테스트 추가).
- **신규(선택)**: `generator/compare_attr.py` — 이관 시 ① sys.path 의존 제거(동일 디렉터리) ② 입력 CSV 인자/없으면 skip(에러 금지) ③ 결정론적 소형 픽스처로 **상대비율** 회귀. 재현성 전제 못 갖추면 이관 대신 docs에 실행법만 남김. (현 `/tmp/compare_attr.py`는 `~/Downloads` glob 의존이라 그대로는 비재현.)
- **무변경**: `find_ents`/`aggregate`/`ontology`(entities·stance 유지), `fromus_taxonomy.py`, `merge_hub.py`, `hub_template.html`, `build.yml`.
- **데이터**: 재생성 후 `chat_kb.json` 갱신(mention 대폭 감소). `./generator/refresh.sh` 로 커밋·배포.

## 6. 리스크 / 주의
- **false negative**(진짜 관련 제거): window±60·stance 신호로 완화했으나 잔존 가능 → 구현 후 샘플 수동검수로 미세조정(window/신호). 너무 많이 빠지면 ±60→±80 또는 신호에 근거 키워드 보강. 또한 stance 세그먼트 좌측이 자기 종목 시작이라 "강력추천 삼성전자"류 **전방 수식 stance 는 놓칠 수 있음**(한국어는 "종목+서술" 후치가 우세라 영향 작음 — sanity 실측: 삼성=bearish·하이닉스=bullish 정확 분리).
- **이중 사전**(ENTITIES vs STOCK_META): 본 범위 비건드림. `attribute_stocks`는 ENTITIES 기준, `chat_to_kb`가 `CANON()`(`_CANON_ALIGN`)으로 정렬(현행과 동일).
- **stance 종목별화로 분포 변화**: 종목 카드 stance 요약(`stance_summary`)·관계망 stance 링이 종목별 정확값 반영(개선). 소비단계 코드 무변경.
- **mention 급감**: chat_kb.json 크기 감소(부수효과). co_edges·테마결합도 정확해짐.
- **소비단계: 코드 무변경, 산출물은 변함(개선)**: `merge_hub`/`hub_template` 코드는 안 바뀌나 mention 집합이 줄어 market_news(`_name_in`)·`co_edges`·`stance_summary`·테마결합 **산출물은 달라진다**(도배 제거 = 의도된 개선). 진짜 '무변경'은 `aggregate`/`ontology`(entities·stance 사용)에만 해당.
- **stance 종목별화 실효 범위**: `stance_summary`·테마 stance·ontology HAS_STANCE 는 view/position 만 집계(research '자료'·neutral 제외) → 개선 효과는 **의견 mention 에 한정**.
- **한글 alias 오탐 잔존**: 한글 표면형은 substring 이라 '구글링→알파벳'류 오탐 가능(find_ents 상속). ±60 게이팅이 도배는 줄이나 근본 제거 아님 — taxonomy `_NEG_NEXT` 한글 경계는 후속 통합 시 차용.
- **targets/news 비대칭**: targets·news·count·테마는 `match_stocks`(substring) 기준 유지, mentions 만 proximity → 한 종목이 'mention 0건인데 목표가 1건' 공존 가능(데이터 정합 OK, 카드 UX 설명 필요).
- **mentions=0 종목 탈락**: 게이팅으로 mention 0 이 된 채팅전용 종목은 `merge_hub`의 추가 조건(`count<2 and not mentions`)에서 빠질 수 있음 → 회귀 검수(§4.2).
