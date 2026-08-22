/* ───────── TABS ───────── */
const TABS=['home','sectors','stocks','analytics','trade','strategy','glossary','graph','chat','verify'];
/* 탭별 렌더러 — 첫 진입 시 1회만 실행 (P3). Promise 를 돌려주는 렌더러는 청크 로딩 후 렌더한다 (P1). */
const VIEW_RENDERERS = {
  home:      ()=>renderHome(),
  sectors:   ()=>renderSectors(),
  stocks:    ()=>renderStocks(),
  analytics: ()=>renderAnalytics(),
  strategy:  ()=>renderStrategy(),
  verify:    ()=>renderVerify(),
  graph:     ()=>renderGraph(),
  glossary:  ()=>loadChunk('glossary').then(()=>renderGlossary()),
  chat:      ()=>loadChunk('chat').then(()=>renderChatView()),
};
const RENDERED = new Set();
function ensureView(name){
  if(RENDERED.has(name)) return Promise.resolve();
  const fn=VIEW_RENDERERS[name]; if(!fn) return Promise.resolve();
  RENDERED.add(name);
  let p; try{ p=Promise.resolve(fn()); }catch(e){ p=Promise.reject(e); }
  return p.catch(e=>{
    RENDERED.delete(name);                         // 실패는 기억하지 않는다 — 다시 시도 가능
    console.error('탭 렌더 실패:', name, e);
    const host=document.getElementById('view-'+name);
    if(host) host.innerHTML=chunkFailHtml(name);
  });
}
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-chunk-retry]'); if(!b) return;
  const name=b.dataset.chunkRetry;
  if(name==='search'){ scheduleSearch(); return; }
  if(name==='stockchat'){ const body=b.closest('.chat-mkt-body'); if(body){ body.dataset.chatShown='0'; loadChunk('stockchat').then(()=>fillMarketBody(body)).catch(()=>{}); } return; }
  ensureView(name);
});
function showTab(name,fromHash){
  if(!TABS.includes(name))name='home';
  if(name==='verify' && !verifyOn()) name='home';
  $$('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  const more=$('#bnavMore'); if(more) more.classList.toggle('active', SHEET_TABS.includes(name));
  $$('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+name));
  const ready=ensureView(name);
  if(name==='trade'){const f=document.getElementById('tradeFrame');if(f&&!f.getAttribute('src'))f.setAttribute('src',f.dataset.src);}
  ready.then(()=>{ if(typeof graphSetActive==='function') graphSetActive(name==='graph'); });
  if(!fromHash){ try{history.replaceState(null,'','#'+name);}catch(e){} window.scrollTo({top:0,behavior:'smooth'}); }
}
$('#tabs').addEventListener('click',e=>{const b=e.target.closest('.tab');if(b)showTab(b.dataset.tab);});
const _bn=document.getElementById('bnav'); if(_bn)_bn.addEventListener('click',e=>{const b=e.target.closest('.tab[data-tab]');if(b)showTab(b.dataset.tab);});
/* 모바일 더보기 시트 — 시트 안 탭이 활성이면 '더보기' 버튼이 active 를 받는다 */
const SHEET_TABS=['analytics','verify','chat','glossary','graph','trade'];
function setSheet(open){ const s=$('#bsheet'), b=$('#bnavMore'); if(!s||!b) return; s.classList.toggle('open',open); b.setAttribute('aria-expanded',open?'true':'false'); }
(function(){ const b=$('#bnavMore'), s=$('#bsheet'); if(!b||!s) return;
  b.addEventListener('click',()=>setSheet(!s.classList.contains('open')));
  s.addEventListener('click',e=>{ if(e.target.closest('[data-bsheet-close]')){setSheet(false);return;} const t=e.target.closest('.tab[data-tab]'); if(t){ showTab(t.dataset.tab); setSheet(false);} });
})();
/* 채팅 탭은 채팅 데이터가 실린 빌드에서만 보인다 (verify 와 같은 꼴) */
function syncChatTab(){ const on=!!(D.chat&&D.chat.counts); $$('.tab[data-tab="chat"]').forEach(b=>{ b.style.display=on?'':'none'; }); }
function tabFromHash(){
  let h=''; try{h=decodeURIComponent((location.hash||'').replace('#',''));}catch(e){h=(location.hash||'').replace('#','');}
  const ix=h.indexOf('/'); const t=ix<0?h:h.slice(0,ix); const arg=ix<0?'':h.slice(ix+1);
  if(!TABS.includes(t))return;
  showTab(t,true);
  if(!arg)return;
  if(t==='stocks'){stockQuery=arg;stockSort='count';renderStocks();const first=$('#stockList .strow-detail');if(first)first.classList.add('open');}
  else if(t==='sectors'){setTimeout(()=>{const card=$$('#view-sectors .scard').find(c=>c.querySelector('.scard-name')?.textContent===arg); if(card){card.querySelector('.scard-detail').classList.add('open');card.scrollIntoView({block:'center'});}},80);}
  else if(t==='glossary'){glossQuery=arg;renderGlossary();}
}
window.addEventListener('hashchange',tabFromHash);

