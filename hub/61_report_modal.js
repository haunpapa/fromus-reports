/* ═══════════ V3.1: 원문 리포트 모달 ═══════════ */
const REPORT_BY_ID={}; (D.reports||[]).forEach(r=>{ if(r.id) REPORT_BY_ID[r.id]=r; });
const RM={modal:$('#reportModal'),frame:$('#rmFrame'),title:$('#rmTitle'),open:$('#rmOpen'),
  jump:$('#rmJump'),load:$('#rmLoad')};
let rmQuery='', rmHit=null, rmBodyOverflow='';

function rmKindLabel(id){const r=REPORT_BY_ID[id]; if(!r)return '원문 리포트';
  return r.type==='weekly'?'주간 리포트':'데일리 리포트';}
function deriveQuery(el){
  const pick=(sel,c)=>{const n=c&&c.querySelector(sel);return n?n.textContent.trim():'';};
  let c;
  if(c=el.closest('.strow')) return pick('.strow-name',c);
  if(c=el.closest('.scard'))  return pick('.scard-name',c);
  if(c=el.closest('.evcard')) return pick('.et',c);
  if(c=el.closest('.gcard'))  return pick('.gterm',c);
  if(c=el.closest('.stl-item')) return pick('.stl-head',c)||pick('.stl-quote',c);
  if(c=el.closest('.core-meta')){const n=c.parentElement&&c.parentElement.querySelector('.core-name'); if(n)return n.textContent.trim();}
  if(c=el.closest('.mention')) {const sp=c.querySelector('span:last-child'); if(sp)return sp.textContent.replace('원문↗','').trim();}
  return '';
}
function highlightInFrame(doc, q){
  rmHit=null; if(!doc||!doc.body||!q) return false;
  const norm=s=>(s||'').replace(/\s+/g,'').toLowerCase();
  const STOP=new Set(['ai','ess','etf','tp','per','pbr','roe','it','us','상승','하락','기대','전망','대표','대표님','관련','종목','오늘','이번','시장','코스피','코스닥','지수','발표','예정','분석','공유','뉴스','이슈']);
  const full=norm(q);
  let toks=q.split(/[\s,./·…"'"“”()\[\]\-—:;?!%+~|]+/).map(t=>t.trim())
            .filter(t=>t.length>=2 && !STOP.has(t.toLowerCase()) && !/^\d+$/.test(t));
  toks=[...new Set(toks)].map(norm).filter(Boolean);
  let nodes=[]; try{ const w=doc.createTreeWalker(doc.body,NodeFilter.SHOW_TEXT,null,false);
    let n; while(n=w.nextNode()){ const t=n.parentElement&&n.parentElement.tagName; if(t==='SCRIPT'||t==='STYLE')continue;
      const v=n.nodeValue; if(v&&v.trim().length>1) nodes.push(n);} }catch(e){return false;}
  const total=nodes.length||1;
  let best=null,bestScore=0;
  nodes.forEach((tn,i)=>{
    const t=norm(tn.nodeValue); if(t.length<2)return;
    let score=0;
    if(full.length>=4 && t.includes(full)) score+=80+Math.min(full.length,24);
    let hit=0; for(const tk of toks){ if(t.includes(tk)){ score+=(tk.length>=3?14:6); hit++; } }
    if(hit>=2) score+=20;                            // 여러 키워드 동시 등장 = 강한 신호
    const frac=i/total; if(frac<0.10) score*=0.5;    // 표지·머리말 구간 감점
    const len=tn.nodeValue.trim().length; if(len>=40 && len<=600) score+=4; // 본문 문단 가점
    if(score>bestScore){bestScore=score;best=tn;}
  });
  if(!best || bestScore<14) return false;            // 충분히 분명할 때만 점프(아니면 맨 위에서 열림)
  const el=best.parentElement; if(!el) return false;
  rmHit=el;
  const prevBg=el.style.backgroundColor;
  el.style.transition='background-color .35s'; el.style.backgroundColor='rgba(245,200,80,.55)'; el.style.borderRadius='4px';
  try{el.scrollIntoView({behavior:'smooth',block:'center'});}catch(_){el.scrollIntoView();}
  setTimeout(()=>{ el.style.backgroundColor=prevBg||''; }, 2800);
  return true;
}
let rmFrameBusy=false;
RM.frame.addEventListener('load',()=>{
  if(!RM.modal.classList.contains('open')) return;
  if((RM.frame.getAttribute('src')||'')==='about:blank') return;
  RM.load.classList.add('hide');
  // 같은 출처(깃허브 페이지)면 내부 접근 가능 → 해당 부분으로 스크롤
  try{
    const doc=RM.frame.contentDocument;
    const found=rmQuery?highlightInFrame(doc,rmQuery):false;
    RM.jump.classList.toggle('show',!!found);
  }catch(e){ RM.jump.classList.remove('show'); }
  rmFrameBusy=false;
});
function openReport(id,q){
  const file=FILE[id]; if(!file)return;
  rmQuery=q||''; rmHit=null;
  const r=REPORT_BY_ID[id];
  $('.rmodal-kind').textContent=rmKindLabel(id);
  RM.title.innerHTML=r?`${esc(r.headline||file)}<span class="rm-date">${esc(fmtDate(r.date))}</span>`:esc(file);
  RM.open.href=file;
  RM.jump.classList.remove('show');
  RM.load.classList.remove('hide');
  rmFrameBusy=true;
  RM.frame.setAttribute('src',file);
  RM.modal.classList.add('open');
  rmBodyOverflow=document.body.style.overflow; document.body.style.overflow='hidden';
  const sp=$('#searchPanel'); if(sp)sp.classList.remove('open');
}
function closeReport(){
  if(!RM.modal.classList.contains('open'))return;
  RM.modal.classList.remove('open');
  setTimeout(()=>{ if(!RM.modal.classList.contains('open')) RM.frame.setAttribute('src','about:blank'); },220);
  document.body.style.overflow=rmBodyOverflow||'';
  rmHit=null; rmQuery='';
}
RM.jump.addEventListener('click',()=>{ if(rmHit){try{rmHit.scrollIntoView({behavior:'smooth',block:'center'});}catch(_){}}
  else if(rmQuery){try{highlightInFrame(RM.frame.contentDocument,rmQuery);}catch(_){}}});
$$('[data-rclose]').forEach(el=>el.addEventListener('click',closeReport));
// ── 채팅 모달 (별도 컨테이너; RM/openReport/closeReport 재사용 금지) ──
let cmBodyOverflow='';
function openChatModal(stockName, kind, idx){
  const arr = chatArr(stockName, kind);
  const m = arr[idx]; if(!m) return;
  $('#cmTitle').innerHTML = `${esc(stockName)} <span class="rm-date">${esc(fmtDate(m.date))} · ${esc(m.sharer||'')} · ${esc(m.stance||'')}</span>`;
  const co = (m.co_stocks||[]).map(n=>`<span class="tag" data-stock="${esc(n)}">${esc(n)}</span>`).join('');
  const s = STOCK_BY_NAME[stockName]||{};
  const tl = ((s.chat&&s.chat.opinions)||[]).filter(o=>o.sharer===m.sharer)
    .map(o=>`<div style="font-size:11.5px;color:var(--text-3)">· ${esc(fmtDate(o.date))} ${esc(o.stance||'')} — ${esc((o.snippet||'').slice(0,60))}</div>`).join('');
  const news = ((s.chat&&s.chat.news)||[]).slice(0,4)
    .map(n=>`<div style="font-size:11.5px"><span class="md">${esc(fmtDate(n.date))}</span> ${esc(n.title)} <a class="src" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.outlet||'열기')}↗</a></div>`).join('');
  $('#cmBody').innerHTML = `
    <div style="background:var(--surface-2);border-radius:8px;padding:12px;line-height:1.6;font-size:13px;white-space:pre-wrap">${esc(m.full||m.snippet||'')}</div>
    ${co?`<div style="font-size:11px;font-weight:700;color:var(--text-3);margin-top:12px">함께 언급 종목</div><div>${co}</div>`:''}
    ${tl?`<div style="font-size:11px;font-weight:700;color:var(--text-3);margin-top:12px">${esc(m.sharer||'')} · ${esc(stockName)} 발언 타임라인</div>${tl}`:''}
    ${news?`<div style="font-size:11px;font-weight:700;color:var(--text-3);margin-top:12px">관련 뉴스</div>${news}`:''}`;
  $('#chatModal').classList.add('open');
  cmBodyOverflow=document.body.style.overflow; document.body.style.overflow='hidden';
}
function closeChatModal(){
  const cm=$('#chatModal'); if(!cm.classList.contains('open'))return;
  cm.classList.remove('open');
  document.body.style.overflow=cmBodyOverflow||'';
}
$$('[data-cmclose]').forEach(el=>el.addEventListener('click',closeChatModal));
document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&$('#chatModal').classList.contains('open')){e.stopPropagation();closeChatModal();} },true);
// 멘션 클릭 → 모달 (data-chat-idx 가진 항목)
document.addEventListener('click',e=>{
  const row=e.target.closest('.chat-clk'); if(!row) return;
  if(e.target.closest('a')) return;  // 내부 링크는 그대로
  openChatModal(row.dataset.chatStock, row.dataset.chatKind, +row.dataset.chatIdx);
});
/* 전역: 모든 원문 링크/검색결과 클릭을 모달로 가로채기 (새 탭 단축키는 허용) */
document.addEventListener('click',e=>{
  const a=e.target.closest('[data-report]'); if(!a)return;
  if(e.metaKey||e.ctrlKey||e.shiftKey||e.button===1) return; // 새 탭/창은 그대로
  e.preventDefault();
  openReport(a.dataset.report, a.dataset.q || deriveQuery(a));
});
document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&RM.modal.classList.contains('open')){e.stopPropagation();closeReport();} },true);



