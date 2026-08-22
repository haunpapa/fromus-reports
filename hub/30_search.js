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

