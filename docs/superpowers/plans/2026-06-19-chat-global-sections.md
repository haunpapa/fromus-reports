# 채팅 전역 섹션 탭 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 새 "💬 채팅" 탭으로 채팅 전역 데이터(전략·목표가·액션·뉴스·교육·Q&A)를 hub에 노출한다.

**Architecture:** `D.chat`(이미 주입됨)을 클라이언트에서 렌더만 한다. `hub_template.html`에 탭 등록 + `renderChatView()` + 더보기 핸들러 + sticky 점프칩 CSS만 추가. `merge_hub`/`build_hub` 변경 없음.

**Tech Stack:** 바닐라 JS(빌드 산출물 `hub.html`), 기존 hub 패턴(`TABS`/`showTab`/`renderXxx`/`sec-title`).

**Spec:** `docs/superpowers/specs/2026-06-19-chat-global-sections-design.md`

**테스트 전략**: JS라 단위테스트 인프라 없음 → **빌드 스모크(마커 grep) + playwright 비주얼**. 각 Task는 빌드 스모크로, 최종 Task는 playwright로 검증.

---

## 파일 구조
- `hub_template.html`만 수정:
  - `TABS` 배열(L654)에 `'chat'`
  - nav 2곳(`#tabs` L538-545, `#bnav` L590~)에 채팅 탭 버튼
  - `.page`(L570-578)에 `<div class="view" id="view-chat"></div>`
  - `renderChatView()` + 섹션 헬퍼 + 더보기/펼침 핸들러 (스크립트 영역, 기존 `renderGlossary` 근처)
  - 초기 렌더 줄(L1859)에 `renderChatView()`
  - sticky 점프칩 CSS(스타일 영역)

---

## Task 1: 채팅 탭 등록 (인프라)

**Files:** Modify `hub_template.html` (TABS L654, nav L538·L590, view L578, init L1859)

- [ ] **Step 1: `TABS`에 chat 추가**

`const TABS=['home','sectors','stocks','analytics','trade','strategy','glossary','graph'];`
→ `'graph'` 뒤에 `,'chat'` 추가.

- [ ] **Step 2: nav 버튼 추가 (2곳)**

`#tabs`(L538-545)의 전략 버튼 다음에, 그리고 `#bnav`(L590~)의 동일 위치에 각각 추가(기존 `.tab` 마크업 복제):
```html
<button class="tab" data-tab="chat"><span class="t-ico">💬</span>채팅</button>
```

- [ ] **Step 3: view 컨테이너 추가**

`.page`(L578 `view-graph` 다음)에:
```html
<div class="view" id="view-chat"></div>
```

- [ ] **Step 4: 빈 `renderChatView` 스텁 + init 호출**

`renderGlossary` 함수 근처에 임시 스텁:
```javascript
function renderChatView(){ $('#view-chat').innerHTML = '<div class="sec-title">💬 채팅</div>'; }
```
L1859 `renderHome();...renderGraph();` 줄 끝에 `renderChatView();` 추가.

- [ ] **Step 5: 빌드 스모크**

Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2`
Expected: 정상 종료. `grep -c 'data-tab="chat"\|view-chat\|renderChatView' hub.html` → ≥3

- [ ] **Step 6: 커밋**
```bash
git add hub_template.html
git commit -m "feat: 채팅 탭 등록 (TABS·nav·view·init 스텁)"
```

---

## Task 2: renderChatView 본문 (6섹션 + 점프칩 + 정렬)

**Files:** Modify `hub_template.html` (`renderChatView` 교체 + 섹션 헬퍼)

- [ ] **Step 1: 정렬 헬퍼 + 초기개수 상수**

`renderChatView` 위에 추가(기존 `CHAT_MORE=10` L934 재사용 — 새 더보기 상수 금지):
```javascript
function cgDesc(arr){ return [...(arr||[])].sort((a,b)=>(b.date||'').localeCompare(a.date||'')); } // 불변 date 역순
const CG_INIT = { strategy:6, targets:12, actions:8, news:6, readings:6 };
const CG_SECS = [
  {key:'strategy', icon:'🧭', label:'전략'},
  {key:'targets',  icon:'🎯', label:'목표가'},
  {key:'actions',  icon:'💡', label:'액션'},
  {key:'news',     icon:'📰', label:'뉴스'},
  {key:'readings', icon:'📚', label:'교육'},
  {key:'qna',      icon:'❓', label:'Q&A'},
];
```

- [ ] **Step 2: 섹션 항목 렌더 헬퍼**

```javascript
function cgStrategyRow(s){
  const meta = `<span class="md">${esc(fmtDate(s.date))}</span> <span style="color:var(--text-3)">${esc(s.sharer||'')}</span>`;
  const desc = esc(s.desc||'');
  const long = desc.length>140;
  return `<div class="cg-card">${esc(s.emoji||'')} <b>${esc(s.title||'')}</b> ${meta}
    <div class="cg-body ${long?'cg-clip':''}" ${long?'data-cg-expand="1" style="cursor:pointer"':''}>${desc}</div></div>`;
}
function cgTargetRow(t){
  const unit = (t.unit||'').trim();
  return `<div class="cg-row"><span class="tag" data-stock="${esc(t.stock||'')}">${esc(t.stock||'')}</span>
    <b style="color:#7c3aed">${esc(t.value||'')}${unit?esc(unit):''}</b>
    <span class="md">${esc(fmtDate(t.date))}</span> <span style="color:var(--text-3)">${esc(t.sharer||'')}</span></div>`;
}
function cgActionRow(a){
  const k = a.kind||''; // do / watch / dont
  const c = k==='do'?'#16a34a':(k==='dont'?'#dc2626':'#d97706');
  const ic = k==='do'?'✅':(k==='dont'?'⛔':'👀');
  return `<div class="cg-row"><span style="color:${c}">${ic}</span> ${esc(a.text||'')}
    <span class="md">${esc(fmtDate(a.date))}</span> <span style="color:var(--text-3)">${esc(a.sharer||'')}</span></div>`;
}
function cgNewsRow(n){
  return `<div class="cg-row"><span class="md">${esc(fmtDate(n.date))}</span> ${esc(n.title||'')}
    <a class="src" href="${esc(n.url||'#')}" target="_blank" rel="noopener">${esc(n.outlet||'열기')}↗</a></div>`;
}
function cgReadingRow(r){
  const body = esc(r.body||''); const long = body.length>140;
  return `<div class="cg-card"><span class="src-pill 테마">${esc(r.tag||'📚')}</span> <b>${esc(r.title||'')}</b>
    <span class="md">${esc(fmtDate(r.date))}</span> <span style="color:var(--text-3)">${esc(r.sharer||'')}</span>
    <div class="cg-body ${long?'cg-clip':''}" ${long?'data-cg-expand="1" style="cursor:pointer"':''}>${body}</div></div>`;
}
function cgQnaRow(q){
  return `<div class="cg-card"><div><b>Q.</b> ${esc(q.q||'')} <span style="color:var(--text-3)">${esc(q.q_by||'')} · ${esc(fmtDate(q.q_date))}</span></div>
    <div style="margin-top:4px"><b>A.</b> ${esc(q.a||'')} <span style="color:var(--text-3)">${esc(q.a_by||'')} · ${esc(fmtDate(q.a_date))}</span></div></div>`;
}
const CG_RENDERERS = { strategy:cgStrategyRow, targets:cgTargetRow, actions:cgActionRow, news:cgNewsRow, readings:cgReadingRow, qna:cgQnaRow };
```

- [ ] **Step 3: `renderChatView` 본문 (점프칩 + 섹션)**

스텁을 교체:
```javascript
function renderChatView(){
  const c = D.chat || {};
  const chips = CG_SECS.filter(s=>(c[s.key]||[]).length)
    .map(s=>`<a class="cg-chip" href="#cg-${s.key}">${s.icon} ${s.label} ${ (c[s.key]||[]).length }</a>`).join('');
  const sections = CG_SECS.map(s=>{
    const arr = cgDesc(c[s.key]);
    if(!arr.length) return '';
    const init = s.key==='qna' ? arr.length : (CG_INIT[s.key]||6);
    const shown = arr.slice(0, init).map(CG_RENDERERS[s.key]).join('');
    const more = arr.length>init
      ? `<div class="cg-more" data-cg-sec="${s.key}" data-cg-shown="${init}" style="cursor:pointer;color:#16a34a;font-size:12px;margin:5px 0">＋ ${s.label} ${arr.length-init}건 더보기</div>` : '';
    return `<div class="sec-title" id="cg-${s.key}">${s.icon} ${s.label} <span class="count-badge">${arr.length}</span></div>
      <div class="cg-list" data-cg-list="${s.key}">${shown}</div>${more}`;
  }).join('');
  $('#view-chat').innerHTML = `<div class="cg-jump">${chips}</div>${sections}`;
}
```

- [ ] **Step 4: 빌드 스모크**

Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2`
Then: `grep -c 'cg-jump\|data-cg-sec\|cg-card' hub.html` → ≥1

- [ ] **Step 5: 커밋**
```bash
git add hub_template.html
git commit -m "feat: renderChatView 6섹션 렌더 + 점프칩 + 불변 date 정렬"
```

---

## Task 3: 더보기 + 인라인 펼침 핸들러

**Files:** Modify `hub_template.html` (스크립트 영역, `STOCK_BY_NAME` 정의 이후 — 1단계 채팅 핸들러 근처)

- [ ] **Step 1: 위임 핸들러 추가** (`data-cg-*`만 처리 — 기존 `data-stock`/`data-chat-*`와 분리)

```javascript
// ── 채팅 전역 섹션: 더보기 + 인라인 펼침 (data-cg-* 만) ──
document.addEventListener('click', e=>{
  // 더보기
  const more = e.target.closest('.cg-more');
  if(more){
    const sec = more.dataset.cgSec, shown = +more.dataset.cgShown;
    const arr = cgDesc((D.chat||{})[sec]);
    const next = Math.min(arr.length, shown + CHAT_MORE);
    const list = more.previousElementSibling; // .cg-list
    if(list) list.insertAdjacentHTML('beforeend', arr.slice(shown,next).map(CG_RENDERERS[sec]).join(''));
    more.dataset.cgShown = next;
    const label = (CG_SECS.find(s=>s.key===sec)||{}).label||'';
    if(next>=arr.length) more.remove(); else more.textContent = `＋ ${label} ${arr.length-next}건 더보기`;
    return;
  }
  // 인라인 펼침 (전략 desc / 교육 body)
  const exp = e.target.closest('[data-cg-expand]');
  if(exp){ exp.classList.toggle('cg-clip'); return; }
});
```

- [ ] **Step 2: 빌드 스모크 + 동작 grep**

Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2`
Then: `grep -c 'cg-more\|data-cg-expand' hub.html` → ≥1

- [ ] **Step 3: 커밋**
```bash
git add hub_template.html
git commit -m "feat: 채팅 전역 섹션 더보기 + 인라인 펼침 핸들러"
```

---

## Task 4: sticky 점프칩 CSS + 통합 비주얼 검증

**Files:** Modify `hub_template.html` (스타일 영역)

- [ ] **Step 1: CSS 추가** (스타일 블록. topbar 높이는 실측 후 오프셋 조정)

```css
.cg-jump{position:sticky;top:64px;z-index:50;background:var(--bg);display:flex;gap:6px;flex-wrap:wrap;
  padding:8px 0;border-bottom:1px solid var(--border);margin-bottom:8px}
.cg-chip{font-size:11.5px;color:#7c3aed;background:#f5f3ff;border:1px solid #e9d5ff;border-radius:999px;
  padding:3px 10px;text-decoration:none}
.cg-card,.cg-row{font-size:12.5px;padding:7px 0;border-bottom:1px dashed var(--border);line-height:1.55}
.cg-body{margin-top:4px;color:var(--text-2)}
.cg-clip{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* .md 는 `.mention .md` 로만 스코프됨 → cg 행에서 동일 룩 보조 규칙 */
.cg-card .md,.cg-row .md{font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--text-4);margin-right:7px}
#view-chat .sec-title{scroll-margin-top:112px}  /* topbar ~64 + 점프칩 ~48 */
@media(max-width:940px){ .cg-jump{top:60px} #view-chat .sec-title{scroll-margin-top:108px} }
```
> `.topbar` 실측 높이 ≈ 64px(데스크톱) / ~60px(모바일 ≤940px). z-index는 topbar(60) 미만(50). 시작값은 위와 같이 두되, Step 3 playwright에서 "점프 시 제목 안 가림"을 실측 확인해 미세 조정.

- [ ] **Step 2: 빌드**

Run: `python build_hub.py --src . --out hub.html --json knowledge_base.json 2>&1 | tail -2`

- [ ] **Step 3: playwright 비주얼 검증** (@superpowers:verification-before-completion)

로컬 HTTP 서버(`python3 -m http.server`)로 `hub.html` 열고:
- 콘솔 에러 없음(favicon 제외)
- `showTab('chat')` 후 `#view-chat`에 6개 `sec-title`(cg-strategy…cg-qna) 렌더
- 점프 칩 클릭 → 해당 섹션으로 이동(제목 안 가림)
- `.cg-more` 클릭 → 항목 추가, 라벨 갱신
- `data-cg-expand` 클릭 → 펼침 토글
- 목표가 `.tag[data-stock]` 클릭 → 종목 탭 이동
- 스크린샷으로 채팅 탭 + 점프칩 sticky 확인

- [ ] **Step 4: 산출물 커밋 제외 확인**

`git status --porcelain` — `hub.html`/`knowledge_base.json`은 빌드 산출물이라 **커밋 안 함**(CI 재생성). `hub_template.html`만 커밋됨.

- [ ] **Step 5: 커밋**
```bash
git add hub_template.html
git commit -m "feat: 채팅 전역 섹션 sticky 점프칩 CSS + scroll-margin"
```

---

## 완료 기준
- `hub.html` 빌드 성공, 채팅 탭에 6개 섹션 렌더
- 점프 칩 sticky 고정(topbar 아래), 클릭 점프 시 제목 안 가림
- 더보기·인라인 펼침·목표가 종목 클릭 동작
- 콘솔 에러 없음, 소스(`hub_template.html`)만 커밋
