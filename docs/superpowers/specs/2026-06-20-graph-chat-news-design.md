# 관계망에 채팅 의견·뉴스 연동

- 날짜: 2026-06-20
- 상태: 설계 승인 → 구현 계획 대기
- 선행: 채팅 온톨로지 1단계·A·D·봇제외 완료.

## 1. 배경

관계망(graph 탭)은 현재 **리포트 섹터 ↔ 종목** bipartite만 표시한다(`buildGraph`). 채팅 의견·뉴스의 종목 동시언급 관계와 채팅 분위기(stance)는 그래프에 없다.

데이터 확인(봇 제외): 종목쌍 동시언급(채팅 의견 메시지그룹 + 뉴스 stocks) **184쌍 중 w≥2가 90쌍**. 단 **그래프에 실제 렌더되려면 양쪽이 섹터 기반 그래프 노드여야 하므로 ~40쌍만 화면 엣지로 표시**된다(나머지는 chat_only 종목 포함). 렌더 예: SK하이닉스-삼성전자(34)·SK하이닉스-엔비디아(12) — 둘 다 그래프 노드. (구글-엔비디아(15)는 구글이 chat_only라 JSON엔 있으나 화면 엣지 없음.)

## 2. 목표 / 비목표

### 목표
- 관계망에 **종목↔종목 동시언급 엣지**(채팅 의견 + 뉴스, 합산) 추가.
- 종목 노드에 **채팅 stance**(강세/약세) 표시.

### 비목표
- 채팅 테마/뉴스를 별도 노드로 추가(엣지·노드속성만, 새 노드 레이어 없음).
- 채팅 전용 종목(섹터 노드에 없는 chat_only)용 신규 노드 생성 — 기존 그래프 노드 집합 유지.
- 2단계 생성기, 프라이버시.

## 3. 설계

### 3.1 `merge_hub.py` — `co_edges` 집계
`kb.chat.co_edges` 신규: 종목쌍 동시언급 가중치 `[{ "a":name, "b":name, "w":int }]`.

집계 소스(둘 합산). `merge_hub.py` 상단에 **`import itertools` 추가 필요**:
1. **채팅 의견 동시언급**: 봇 제외 `view/position` 멘션을 메시지 `(date, sharer, snippet[:40])`로 그룹핑 → 종목집합 → `itertools.combinations(sorted(set), 2)` 쌍, 메시지당 1회. **`_build_comention_map` 재사용 금지**(그건 봇·비의견 멘션까지 포함해 오염됨) — `_co_edges` 전용 그룹핑을 새로 만들되 키 절단은 **`snippet[:40]`**(기존 `_augment`/`_build_comention_map`과 통일).
2. **뉴스 동시언급**: `chat.news[].stocks`(2개+)의 정렬 쌍.

후처리:
- 정규화 쌍(`a<b` 정렬)으로 가중치 합산(채팅+뉴스 통합).
- **임계값 `CO_EDGE_MIN_W=2`**(1회성 제외 → 90쌍).
- **종목당 상위 `CO_EDGE_PER_NODE=6`**(허브 종목 엔비디아 등 엣지 폭주 방지): **합집합 의미** — 쌍의 어느 한쪽 종목 기준으로라도 w 상위 6 안에 들면 유지(양쪽 모두 top6일 필요 없음). (합집합 ≈83쌍 vs 교집합 ≈41쌍 — 합집합 채택)
- 불변: 원본 미변경, 새 리스트 생성.
- 멱등성: `_strip_prior_chat`이 `kb.pop("chat")` 통째 제거하므로 자동 정리.

노드 stance는 기존 종목 `chat.stance` 재사용(추가 집계 불필요).

### 3.2 `hub_template.html` — `buildGraph` / `gDraw`
- **`buildGraph`**: 기존 섹터→종목 엣지 생성 후, `D.chat.co_edges`를 순회해 **양쪽 종목이 이미 그래프 노드인 쌍만** 종목↔종목 엣지 추가. 노드 조회 키는 **`idx['K:'+gClean(name)]`**(노드 id 형식이 `'K:'+gClean(종목명)`); 한쪽이라도 `undefined`면 스킵(chat_only 종목·`major` 필터 제외 종목은 자연 스킵). `link.kind='co'`, `link.w` 부여. (기존 섹터-종목 link엔 `kind='sector'` 부여)
- **`gDraw` 엣지**: `link.kind`로 구분 — 섹터-종목(기존 회색 실선) / 종목-종목 `co`(**점선** `setLineDash`, `lineWidth`를 `w`로 가중). hover 동작은 기존 유지.
- **`gDraw` 노드 stance 링**: 종목 노드에서 `node.ref.chat.stance`로 우세 stance 판정 — `bullish>bearish`면 강세(`#16a34a`), `bearish>bullish`면 약세(`#dc2626`), **동률(`==`)·무(0:0)는 링 없음**. 노드 둘레 stroke 링만 추가, 본색(섹터 GPAL) 유지.
- `Array.isArray`/옵셔널 가드: `D.chat.co_edges`가 없으면(구버전) 종목-종목 엣지 생략(하위호환).

### 3.3 결정 (기본값)
- 채팅·뉴스 엣지는 **합산**(w 통합). 출처 구분 색은 없음(과밀 방지) — hover 시 정보는 후속.
- 임계값 `w≥2`, 종목당 상위 6.
- stance 링은 우세 1방향만(강세 vs 약세).

## 4. 테스트
- `build/test_merge_hub.py` 확장: `_co_edges` — 정규화 쌍·가중치 합산(채팅+뉴스 동일쌍 w 통합), 메시지당 1회(중복 카운트 없음), **봇·비의견(research) 멘션 제외**, 뉴스 3종목→3쌍(combinations), `w≥2` 임계값, **종목당 상위6 합집합**(한쪽 top6에만 들어도 유지되는 케이스 검증).
- 스모크: 빌드 후 `knowledge_base.json`의 `chat.co_edges`가 리스트이고 `SK하이닉스`-`삼성전자` 쌍 존재(w 높음).
- playwright: 관계망 탭 → 종목-종목 **점선 엣지** 존재(실제 렌더), 강세 종목 노드에 녹색 링. 콘솔 에러 없음.

## 5. 파일 변경
- `merge_hub.py`: `import itertools` + `CO_EDGE_*` 상수 + `_co_edges(chat)`(kb 인자 불요 — chat의 stocks·news만 사용) + `kb.chat.co_edges` 설정.
- `hub_template.html`: `buildGraph`(co 엣지) + `gDraw`(점선·stance 링).
- `build/test_merge_hub.py`: `_co_edges` 테스트.

## 6. 리스크 / 주의
- **허브 종목 엣지 폭주**: 엔비디아 등 다수 쌍 → 종목당 상위 6으로 제한.
- **채팅 전용 종목 → 렌더 쌍 축소**: `co_edges` 90쌍 중 양쪽이 그래프 노드인 **~40쌍만 화면 엣지**로 렌더(나머지는 chat_only 종목 포함, `buildGraph`가 `idx['K:'+gClean]` 부재로 자동 스킵). JSON `co_edges`엔 90쌍 모두 남음.
- **노드 색 충돌 없음**: stance는 테두리 링, 본색은 섹터色 유지.
- **데이터 정확성**: 의견 종목 귀속·뉴스 stocks는 종목명 기반(테마 분류보다 신뢰), `w≥2`로 1회성 노이즈 제외.
