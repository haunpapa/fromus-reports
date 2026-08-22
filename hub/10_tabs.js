/* ───────── TABS ───────── */
const TABS=['home','sectors','stocks','analytics','trade','strategy','glossary','graph','chat','verify'];
function showTab(name,fromHash){
  if(!TABS.includes(name))name='home';
  if(name==='verify' && !verifyOn()) name='home';
  $$('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  $$('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+name));
  if(name==='trade'){const f=document.getElementById('tradeFrame');if(f&&!f.getAttribute('src'))f.setAttribute('src',f.dataset.src);}
  if(typeof graphSetActive==='function') graphSetActive(name==='graph');
  if(!fromHash){ try{history.replaceState(null,'','#'+name);}catch(e){} window.scrollTo({top:0,behavior:'smooth'}); }
}
$('#tabs').addEventListener('click',e=>{const b=e.target.closest('.tab');if(b)showTab(b.dataset.tab);});
const _bn=document.getElementById('bnav'); if(_bn)_bn.addEventListener('click',e=>{const b=e.target.closest('.tab');if(b)showTab(b.dataset.tab);});
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

