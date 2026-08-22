/* ───────── GLOBAL SEARCH 2.0 ─────────
   데이터 계약 C3: it.source('report'|'chat') · it.hay · it.extra · D.build.aliases.
   구 빌드(필드 없음)에서는 리포트 항목만·별칭 없음으로 그대로 동작한다. */
let searchFilter='all', searchSrc='all', searchPeriod='all';   // kind · 출처 · 기간
let SEARCH=[];                     // search 청크 로딩 후 채워진다 (P1)
let searchTimer=null;
const RECENT_KEY='fu-recent-q', RECENT_N=5;
const hayOf=it=>(it.title+' '+it.snippet+' '+(it.tags||[]).join(' ')+' '+it.kind).toLowerCase();
function ensureSearch(){ return loadChunk('search').then(()=>{
  if(SEARCH.length) return;                       // 한 번만: hay 가 없는(구 빌드) 항목은 새 객체로 보강 — 원본 변경 없음
  SEARCH = (D.search||[]).map(it=> it.hay ? it : {...it, hay: hayOf(it)}); }); }
function scheduleSearch(){
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>ensureSearch().then(runSearch).catch(()=>{
    const p=$('#searchPanel'); p.innerHTML=chunkFailHtml('search'); p.classList.add('open'); }), 120);   // 키스트로크 디바운스
}

/* ── 최근 검색어 (이 브라우저에만 저장) ── */
function recentQueries(){ try{ return JSON.parse(localStorage.getItem(RECENT_KEY)||'[]'); }catch(e){ return []; } }
function pushRecent(q){ const list=[q, ...recentQueries().filter(x=>x!==q)].slice(0,RECENT_N);
  try{ localStorage.setItem(RECENT_KEY, JSON.stringify(list)); }catch(e){} }

/* ── 별칭 확장: '하닉' → ['하닉','sk하이닉스'] ── */
const ALIASES=(D.build&&D.build.aliases)||{};
function expandToken(t){ const canon=ALIASES[t]; return canon ? [t, (''+canon).toLowerCase()] : [t]; }

function scoreItem(it,tokens){
  const hay=it.hay, title=(it.title||'').toLowerCase();
  let sc=0;
  for(const alts of tokens){
    if(!alts.some(a=>hay.includes(a))) return -1;
    sc += alts.some(a=>title.includes(a)) ? 3 : 1;
  }
  return sc;
}
function periodCutoff(){ return searchPeriod==='all' ? null : TO_DAY - (+searchPeriod); }

/* ── 종목 핀 카드 — 질의가 종목명(또는 별칭)과 정확히 맞으면 맨 위에 고정 ── */
function pinnedStock(raw){
  const q=raw.toLowerCase();
  const name=ALIASES[q] || Object.keys(STOCK_BY_NAME).find(n=>n.toLowerCase()===q);
  const s=name && STOCK_BY_NAME[name]; if(!s) return '';
  return `<div class="sr-pin" data-stock="${esc(s.name)}"><span class="sr-kind">종목</span><b>${esc(s.name)}</b>
    ${momentumChip(s)}<span class="sr-date">${s.count||0}회 · 수급 ${s.supply_count||0}${s.chat?` · 💬 ${s.chat.count}`:''}</span>
    <span class="sr-go">상세 →</span></div>`;
}
function resultRow(it,tokens){
  const top=`<div class="sr-top"><span class="sr-kind">${esc(it.kind)}</span><span class="sr-title">${hl(it.title,tokens)}</span><span class="sr-date">${esc(fmtDate(it.date))}</span></div><div class="sr-snip">${hl(it.snippet,tokens)}</div>`;
  const x=it.extra||{};
  if(it.kind==='채팅뉴스') return `<a class="sr" href="${esc(safeHref(x.url))}" target="_blank" rel="noopener">${top}</a>`;
  if(it.kind==='채팅의견'||it.kind==='목표가') return `<button class="sr" data-stock="${esc(x.stock||'')}">${top}</button>`;
  if(it.kind==='종목') return `<button class="sr" data-stock="${esc(it.title||'')}">${top}</button>`;
  return `<button class="sr" ${it.id&&FILE[it.id]?`data-report="${esc(it.id)}" data-q="${esc(it.title||'')}"`:''}>${top}</button>`;
}
const SRC_LABEL={all:'출처 전체',report:'리포트',chat:'채팅'};
function runSearch(){
  const raw=$('#q').value.trim();
  $('#clr').style.display=raw?'block':'none';
  const panel=$('#searchPanel');
  if(!raw){ drawRecent(); $('#searchHint').textContent=''; return; }
  const tokens=raw.toLowerCase().split(/\s+/).filter(Boolean).map(expandToken);
  const cut=periodCutoff();
  let res=SEARCH.map(it=>({it,sc:scoreItem(it,tokens)})).filter(x=>x.sc>=0);
  if(searchSrc!=='all') res=res.filter(x=>(x.it.source||'report')===searchSrc);
  if(cut!=null) res=res.filter(x=>{const d=dnum(x.it.date); return d!=null && d>=cut;});
  res.sort((a,b)=> b.sc-a.sc || (b.it.date||'').localeCompare(a.it.date||''));
  const kinds=[...new Set(res.map(x=>x.it.kind))];
  if(searchFilter!=='all') res=res.filter(x=>x.it.kind===searchFilter);
  const top=res.slice(0,50);
  const hasChat=SEARCH.some(i=>i.source==='chat');
  const head=`<div class="sp-head">
     <span class="sp-filter ${searchFilter==='all'?'on':''}" data-f="all">전체 ${res.length>50?'50+':res.length}</span>
     ${kinds.map(k=>`<span class="sp-filter ${searchFilter===k?'on':''}" data-f="${esc(k)}">${esc(k)}</span>`).join('')}</div>
     <div class="sp-head sp-head2">
       ${hasChat?['all','report','chat'].map(s=>`<span class="sp-src ${searchSrc===s?'on':''}" data-src="${s}">${SRC_LABEL[s]}</span>`).join(''):''}
       ${[['all','전체 기간'],['7','1주'],['31','1개월']].map(([p,l])=>`<span class="sp-period ${searchPeriod===p?'on':''}" data-period="${p}">${l}</span>`).join('')}
     </div>`;
  const body= top.length? top.map(x=>resultRow(x.it,tokens)).join('') : '<div class="sr-empty">결과가 없습니다.</div>';
  panel.innerHTML=head+pinnedStock(raw)+body;
  panel.classList.add('open');
  $('#searchHint').textContent=`“${raw}” — ${res.length}건`;
}
function drawRecent(){
  const panel=$('#searchPanel'), rq=recentQueries();
  if(!rq.length){ panel.classList.remove('open'); panel.innerHTML=''; return; }
  panel.innerHTML=`<div class="sp-recent"><span class="sp-recent-l">최근 검색</span>${rq.map(q=>`<button type="button" class="sp-filter" data-recent="${esc(q)}">${esc(q)}</button>`).join('')}</div>`;
  panel.classList.add('open');
}
function hl(s,tokens){
  s=esc(s||'');
  tokens.flat().forEach(t=>{ if(t.length<1)return; try{s=s.replace(new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig'),'<mark>$1</mark>');}catch(e){} });
  return s;
}
$('#q').addEventListener('input',scheduleSearch);
$('#q').addEventListener('focus',()=>{ ensureSearch().catch(()=>{}); if($('#q').value.trim())scheduleSearch(); else drawRecent(); });
$('#clr').addEventListener('click',()=>{$('#q').value='';searchFilter='all';runSearch();$('#searchHint').textContent='';$('#q').focus();});
/* 칩을 누르면 패널을 다시 그린다 → e.target 이 DOM 에서 떨어져 나가므로 아래 document 핸들러의
   e.target.closest('.searchwrap') 가 null 이 되어 패널이 닫혀 버린다. 버블링을 여기서 끊는다. */
$('#searchPanel').addEventListener('click',e=>{
  const f=e.target.closest('.sp-filter[data-f]'); if(f){e.stopPropagation();searchFilter=f.dataset.f;runSearch();return;}
  const s=e.target.closest('.sp-src'); if(s){e.stopPropagation();searchSrc=s.dataset.src;runSearch();return;}
  const p=e.target.closest('.sp-period'); if(p){e.stopPropagation();searchPeriod=p.dataset.period;runSearch();return;}
  const r=e.target.closest('[data-recent]'); if(r){e.stopPropagation();$('#q').value=r.dataset.recent;scheduleSearch();return;}
  if(e.target.closest('.sr,.sr-pin')){ const q=$('#q').value.trim(); if(q) pushRecent(q); }
});
document.addEventListener('click',e=>{ if(!e.target.closest('.searchwrap')) $('#searchPanel').classList.remove('open'); });

/* ───────── 모바일 검색 시트 ─────────
   포커스 시 전체화면(body.search-open). 닫힘 경로는 셋을 구분한다:
   'back'  = 닫기 버튼/Escape → pushState 한 항목을 history.back() 으로 되돌린다
   'pop'   = 뒤로가기 → 이미 되돌아온 상태라 아무 이동도 하지 않는다
   'select'= 결과 선택 → 마커만 지운다(replaceState). 여기서 back() 을 쓰면 직후 openStock 이
             replaceState 한 항목을 떠나 hashchange 가 이전 탭을 다시 열어 상세 뷰가 사라진다. */
const isNarrow=()=>matchMedia('(max-width:940px)').matches;
function openSearchSheet(){ if(!isNarrow()||document.body.classList.contains('search-open')) return;
  document.body.classList.add('search-open'); document.body.style.overflow='hidden'; try{history.pushState({fuSearch:1},'');}catch(e){} }
function closeSearchSheet(mode){ if(!document.body.classList.contains('search-open')) return;
  document.body.classList.remove('search-open'); document.body.style.overflow=''; $('#searchPanel').classList.remove('open'); $('#q').blur();
  const marked = history.state && history.state.fuSearch;
  try{ if(mode==='back' && marked) history.back(); else if(mode==='select' && marked) history.replaceState(null,'',location.href); }catch(e){} }
$('#q').addEventListener('focus',openSearchSheet);
$('#qClose').addEventListener('click',()=>closeSearchSheet('back'));
window.addEventListener('popstate',()=>closeSearchSheet('pop'));
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeSearchSheet('back'); });
/* 결과를 고르면 시트(모바일)와 드롭다운(데스크톱)이 남지 않게 닫는다 */
$('#searchPanel').addEventListener('click',e=>{ if(e.target.closest('.sr,.sr-pin')){ closeSearchSheet('select'); $('#searchPanel').classList.remove('open'); } });
