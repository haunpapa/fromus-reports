/* ═══════════ V4: Executive UX / 비교·탐색 고도화 ═══════════ */
function cleanLabel(s){return (s||'').replace(/\s+/g,' ').trim();}
function latestMention(obj){const ms=(obj&&obj.mentions)||[];return ms.length?ms[ms.length-1]:null;}
function injectMarketPulse(){
  const anchor=$('#watchHome'); if(!anchor||$('#marketPulse'))return;
  const hot=(D.sectors||[]).slice().map(s=>({s,m:momentumOf(s),why:sectorWhy(s)}))
    .sort((a,b)=>((b.m&&b.m.cls==='mo-hot')-(a.m&&a.m.cls==='mo-hot'))||((b.s.rep||0)-(a.s.rep||0))||((b.s.count||0)-(a.s.count||0)))[0];
  const supply=(D.stocks||[]).slice().filter(s=>(s.supply_count||0)>0).sort((a,b)=>(b.supply_count-a.supply_count)||(b.count-a.count))[0];
  const event=(D.events||[]).slice().sort((a,b)=>(b.seen||'').localeCompare(a.seen||''))[0];
  const h=hot&&hot.s, st=supply, ev=event;
  anchor.insertAdjacentHTML('afterend',`<div class="pulse-grid" id="marketPulse">
    <div class="pulse-card primary" ${h?`data-go="sectors" data-sector="${esc(h.theme)}" tabindex="0" role="button"`:''}>
      <div class="pulse-k">Market Pulse</div>
      <div class="pulse-h">${h?esc(h.theme):'핵심 섹터 대기 중'}</div>
      <div class="pulse-desc">${h&&hot.why?esc((hot.why.note||hot.why.name||'').slice(0,170)):'최근 리포트의 섹터 언급이 누적되면 이곳에 가장 중요한 변화가 표시됩니다.'}</div>
      <div class="pulse-row">${h?momentumChip(h):''}<span class="pulse-metric">${h?(h.count||0):0}회</span><span class="pulse-mini">대표님 강조 ${h?(h.rep||0):0}</span></div>
    </div>
    <div class="pulse-card" ${st?`data-stock="${esc(st.name)}" tabindex="0" role="button"`:''}>
      <div class="pulse-k">Supply Radar</div>
      <div class="pulse-h">${st?esc(st.name):'수급 포착 없음'}</div>
      <div class="pulse-desc">${st?esc(((latestMention(st)||{}).annotation||(latestMention(st)||{}).label||(st.themes||[]).join(', ')||'최근 수급 포착 종목').slice(0,155)):'수급 카드에서 포착된 종목을 우선 표시합니다.'}</div>
      <div class="pulse-row"><span class="pulse-metric">수급 ${st?(st.supply_count||0):0}</span><span class="pulse-mini">전체 ${st?(st.count||0):0}회 언급</span></div>
    </div>
    <div class="pulse-card" ${ev&&ev.id?`data-report="${esc(ev.id)}" data-q="${esc(ev.title||'')}" tabindex="0" role="button"`:''}>
      <div class="pulse-k">Event Watch</div>
      <div class="pulse-h">${ev?esc(ev.title):'일정 대기 중'}</div>
      <div class="pulse-desc">${ev?esc((ev.desc||'').slice(0,160)):'리포트에서 추출된 일정·정책·실적 이벤트가 표시됩니다.'}</div>
      <div class="pulse-row"><span class="pulse-metric">${ev?esc(fmtDate(ev.seen)):''}</span><span class="pulse-mini">원문에서 확인</span></div>
    </div>
  </div>`);
}

document.addEventListener('keydown',e=>{const el=e.target.closest('[role="button"][data-go],[role="button"][data-stock],[role="button"][data-report]'); if(el&&(e.key==='Enter'||e.key===' ')){e.preventDefault();el.click();}},true);

let CMP=(()=>{try{return JSON.parse(localStorage.getItem('fu-compare')||'[]').slice(0,4);}catch(e){return [];}})();
function isComparePicked(name){return CMP.includes(name);}
function saveCompare(){try{localStorage.setItem('fu-compare',JSON.stringify(CMP));}catch(e){}}
function toggleCompare(name){
  if(!name)return; const i=CMP.indexOf(name); if(i>=0)CMP.splice(i,1); else { if(CMP.length>=4)CMP.shift(); CMP.push(name); }
  saveCompare(); refreshCompareUI();
}
function setupCompareUI(){
  if($('#compareTray'))return;
  document.body.insertAdjacentHTML('beforeend',`<div class="cmp-tray" id="compareTray" aria-live="polite"><span class="cmp-title">종목 비교</span><div class="cmp-items" id="cmpItems"></div><button class="cmp-act" id="cmpOpen">비교 보기</button><button class="cmp-clear" id="cmpClear">비우기</button></div><div class="cmp-modal" id="cmpModal" role="dialog" aria-modal="true"><div class="cmp-back" data-cmpclose></div><div class="cmp-box"><div class="cmp-head"><h3>종목 비교 보드</h3><button class="cmp-close" data-cmpclose aria-label="닫기">✕</button></div><div class="cmp-body" id="cmpBody"></div></div></div>`);
  $('#cmpOpen').addEventListener('click',openCompareModal); $('#cmpClear').addEventListener('click',()=>{CMP=[];saveCompare();refreshCompareUI();});
  $$('[data-cmpclose]').forEach(b=>b.addEventListener('click',()=>$('#cmpModal').classList.remove('open')));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#cmpModal')&&$('#cmpModal').classList.contains('open'))$('#cmpModal').classList.remove('open');});
  refreshCompareUI();
}
function refreshCompareUI(){
  const tray=$('#compareTray'), items=$('#cmpItems'); if(!tray||!items)return;
  tray.classList.toggle('on',CMP.length>0);
  items.innerHTML=CMP.map(n=>`<span class="cmp-pill">${esc(n)} <button aria-label="비교 제거" onclick="toggleCompare('${esc(n)}')">✕</button></span>`).join('');
  $$('.cmp-add[data-cmp]').forEach(b=>{const on=isComparePicked(b.dataset.cmp); b.classList.toggle('on',on); b.textContent=on?'비교중':'비교';});
}
function compareCard(s){
  const last=latestMention(s)||{}; const note=last.annotation||last.label||last.theme||last.note||'';
  const themes=(s.themes||s.sectors||[]).slice(0,5).map(t=>`<span class="pill theme">${esc(t)}</span>`).join('');
  return `<div class="cmp-card"><div class="cmp-name"><button class="star ${isWatched('stock',s.name)?'on':''}" data-watch="stock:${esc(s.name)}" onclick="toggleWatchEl(this)">${isWatched('stock',s.name)?'★':'☆'}</button>${esc(s.name)}</div><canvas class="cmp-spark" width="520" height="88" data-cspark="${esc(s.name)}"></canvas><div class="cmp-kv"><div><b>${s.count||0}</b><span>전체 언급</span></div><div><b>${s.supply_count||0}</b><span>수급 포착</span></div><div><b>${s.theme_count||0}</b><span>테마 언급</span></div><div><b>${esc(fmtDate(last.date)||'-')}</b><span>최근 등장</span></div></div><div class="cmp-themes">${themes||'<span class="pulse-mini">테마 정보 없음</span>'}</div>${note?`<div class="cmp-note">${esc(note.slice(0,180))} ${last.id?srcLink(last.id,s.name):''}</div>`:''}</div>`;
}
function openCompareModal(){
  const list=CMP.map(n=>STOCK_BY_NAME[n]).filter(Boolean); const body=$('#cmpBody'); if(!body)return;
  body.innerHTML=list.length?`<div class="cmp-grid">${list.map(compareCard).join('')}</div>`:'<div class="empty">비교할 종목을 먼저 담아주세요.</div>';
  $('#cmpModal').classList.add('open');
  setTimeout(()=>{$$('[data-cspark]').forEach(cv=>{const st=STOCK_BY_NAME[cv.dataset.cspark]; if(st)drawSpark(cv,weeklyCounts(st.mentions));});},30);
}

document.addEventListener('click',e=>{const b=e.target.closest('[data-cmp]'); if(!b)return; e.stopPropagation(); toggleCompare(b.dataset.cmp);});

let CMD_ITEMS=[], cmdIndex=0;
function setupCommandPalette(){
  if($('#cmdk'))return;
  document.body.insertAdjacentHTML('beforeend',`<div class="cmdk" id="cmdk" role="dialog" aria-modal="true" aria-label="빠른 이동"><div class="cmdk-back" data-cmdclose></div><div class="cmdk-box"><div class="cmdk-search"><span>⌘K</span><input id="cmdInput" type="text" placeholder="빠른 이동: 종목·섹터·용어·리포트 검색"></div><div class="cmdk-list" id="cmdList"></div><div class="cmdk-foot"><span>↑↓ 이동</span><span>Enter 실행</span><span>Esc 닫기</span><span>/ 전역 검색</span></div></div></div>`);
  CMD_ITEMS=buildCommandItems();
  $('#cmdInput').addEventListener('input',()=>{cmdIndex=0;drawCommandList();});
  $('#cmdInput').addEventListener('keydown',e=>{const rows=$$('.cmdk-item'); if(e.key==='ArrowDown'){e.preventDefault();cmdIndex=Math.min(rows.length-1,cmdIndex+1);drawCommandList();} if(e.key==='ArrowUp'){e.preventDefault();cmdIndex=Math.max(0,cmdIndex-1);drawCommandList();} if(e.key==='Enter'){e.preventDefault();const row=$$('.cmdk-item')[cmdIndex]; if(row)runCommand(row.dataset.idx);}});
  $$('[data-cmdclose]').forEach(x=>x.addEventListener('click',closeCommand));
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommand();} if(e.key==='Escape'&&$('#cmdk').classList.contains('open'))closeCommand();});
}
function buildCommandItems(){
  const items=[
    {kind:'이동',title:'개요',sub:'홈 대시보드',go:()=>showTab('home')},
    {kind:'이동',title:'섹터·테마',sub:'테마 클러스터',go:()=>showTab('sectors')},
    {kind:'이동',title:'종목 유니버스',sub:'필터와 비교',go:()=>showTab('stocks')},
    {kind:'이동',title:'분석 대시보드',sub:'히트맵·모멘텀·수급 레이더',go:()=>showTab('analytics')},
    {kind:'이동',title:'전략',sub:'스탠스와 원칙',go:()=>showTab('strategy')},
    {kind:'이동',title:'관계망',sub:'섹터·종목 그래프',go:()=>showTab('graph')},
    {kind:'이동',title:'수출입동향',sub:'관세청 무역통계 대시보드',go:()=>showTab('trade')}
  ];
  (D.stocks||[]).slice(0,80).forEach(s=>items.push({kind:'종목',title:s.name,sub:`${s.count||0}회 · 수급 ${s.supply_count||0} · ${(s.themes||[]).slice(0,2).join(', ')}`,go:()=>{showTab('stocks');stockQuery=s.name;stockSort='count';renderStocks();}}));
  (D.sectors||[]).slice(0,50).forEach(s=>items.push({kind:'섹터',title:s.theme,sub:`${s.count||0}회 · ${(s.stocks||[]).slice(0,4).join(', ')}`,go:()=>{showTab('sectors');setTimeout(()=>{const card=$$('#view-sectors .scard').find(c=>c.querySelector('.scard-name')?.textContent===s.theme); if(card){card.querySelector('.scard-detail').classList.add('open');card.scrollIntoView({behavior:'smooth',block:'center'});}},80);}}));
  (D.glossary||[]).slice(0,80).forEach(g=>items.push({kind:'용어',title:g.term,sub:(g.body||'').slice(0,90),go:()=>{showTab('glossary');glossQuery=g.term;renderGlossary();}}));
  (D.reports||[]).slice().reverse().slice(0,40).forEach(r=>items.push({kind:r.type==='weekly'?'주간':'데일리',title:r.headline||r.file,sub:`${fmtDate(r.date)} · ${r.subhead||''}`,go:()=>openReport(r.id,r.headline||'')}));
  return items;
}
function openCommand(){
  const m=$('#cmdk');m.classList.add('open');$('#cmdInput').value='';cmdIndex=0;drawCommandList();setTimeout(()=>$('#cmdInput').focus(),20);
  if(!(D.glossary||[]).length) loadChunk('glossary').then(()=>{ CMD_ITEMS=buildCommandItems(); drawCommandList(); }).catch(()=>{});
}
function closeCommand(){$('#cmdk').classList.remove('open');}
function drawCommandList(){
  const q=($('#cmdInput')?.value||'').toLowerCase().trim();
  let res=CMD_ITEMS.map((it,i)=>({it,i,hay:(it.kind+' '+it.title+' '+it.sub).toLowerCase()})).filter(x=>!q||q.split(/\s+/).every(t=>x.hay.includes(t))).slice(0,40);
  if(cmdIndex>=res.length)cmdIndex=Math.max(0,res.length-1);
  $('#cmdList').innerHTML=res.length?res.map((x,n)=>`<button class="cmdk-item ${n===cmdIndex?'active':''}" data-idx="${x.i}"><span class="cmdk-kind">${esc(x.it.kind)}</span><span><div class="cmdk-main">${esc(x.it.title)}</div><div class="cmdk-sub">${esc(x.it.sub||'')}</div></span></button>`).join(''):'<div class="cmdk-empty">결과가 없습니다. 전역 검색(/)도 함께 활용해 보세요.</div>';
  $$('.cmdk-item').forEach(b=>b.addEventListener('click',()=>runCommand(b.dataset.idx)));
}
function runCommand(idx){const it=CMD_ITEMS[+idx]; if(!it)return; closeCommand(); setTimeout(()=>it.go(),20);}
function bootV4Enhancements(){setupCompareUI();setupCommandPalette();injectMarketPulse();refreshCompareUI();}

