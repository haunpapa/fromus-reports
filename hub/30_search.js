/* ───────── GLOBAL SEARCH ───────── */
let searchFilter='all';
let SEARCH=[];                     // search 청크 로딩 후 채워진다 (P1)
let searchTimer=null;
function ensureSearch(){ return loadChunk('search').then(()=>{ SEARCH = D.search||[]; }); }
function scheduleSearch(){
  clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>ensureSearch().then(runSearch).catch(()=>{
    const p=$('#searchPanel'); p.innerHTML=chunkFailHtml('search'); p.classList.add('open'); }), 120);   // 키스트로크 디바운스
}
function scoreItem(it,tokens){
  const hay = it.hay || (it.title+' '+it.snippet+' '+(it.tags||[]).join(' ')+' '+it.kind).toLowerCase();
  let sc=0;
  for(const t of tokens){ if(!hay.includes(t))return -1; sc += (it.title.toLowerCase().includes(t)?3:1); }
  return sc;
}
function runSearch(){
  const raw=$('#q').value.trim();
  $('#clr').style.display=raw?'block':'none';
  const panel=$('#searchPanel');
  if(!raw){panel.classList.remove('open');panel.innerHTML='';return;}
  const tokens=raw.toLowerCase().split(/\s+/).filter(Boolean);
  let res=SEARCH.map(it=>({it,sc:scoreItem(it,tokens)})).filter(x=>x.sc>=0);
  // 종목명 직접 매칭 보너스
  res.sort((a,b)=> b.sc-a.sc || (b.it.date||'').localeCompare(a.it.date||''));
  const kinds=[...new Set(res.map(x=>x.it.kind))];
  if(searchFilter!=='all') res=res.filter(x=>x.it.kind===searchFilter);
  const top=res.slice(0,50);
  const head=`<div class="sp-head">
     <span class="sp-filter ${searchFilter==='all'?'on':''}" data-f="all">전체 ${res.length>50?'50+':res.length}</span>
     ${kinds.map(k=>`<span class="sp-filter ${searchFilter===k?'on':''}" data-f="${esc(k)}">${esc(k)}</span>`).join('')}</div>`;
  const body= top.length? top.map(x=>{
      const it=x.it;
      return `<button class="sr" ${it.id&&FILE[it.id]?`data-report="${esc(it.id)}" data-q="${esc(it.title||'')}"`:''}>
        <div class="sr-top"><span class="sr-kind">${esc(it.kind)}</span><span class="sr-title">${hl(it.title,tokens)}</span><span class="sr-date">${esc(fmtDate(it.date))}</span></div>
        <div class="sr-snip">${hl(it.snippet,tokens)}</div></button>`;
    }).join('') : '<div class="sr-empty">결과가 없습니다.</div>';
  panel.innerHTML=head+body;
  panel.classList.add('open');
  $('#searchHint').textContent=`“${raw}” — ${res.length}건`;
}
function hl(s,tokens){
  s=esc(s||'');
  tokens.forEach(t=>{ if(t.length<1)return; try{s=s.replace(new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig'),'<mark>$1</mark>');}catch(e){} });
  return s;
}
$('#q').addEventListener('input',scheduleSearch);
$('#q').addEventListener('focus',()=>{ ensureSearch().catch(()=>{}); if($('#q').value.trim())scheduleSearch(); });
$('#clr').addEventListener('click',()=>{$('#q').value='';searchFilter='all';runSearch();$('#searchHint').textContent='';$('#q').focus();});
$('#searchPanel').addEventListener('click',e=>{const f=e.target.closest('.sp-filter');if(f){searchFilter=f.dataset.f;runSearch();}});
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
