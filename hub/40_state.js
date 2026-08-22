/* ═══════════ V2 LOGIC ═══════════ */
/* ── 테마 토글 ── */
function curTheme(){return document.documentElement.getAttribute('data-theme')||'light';}
function setTheme(t){
  document.documentElement.setAttribute('data-theme',t);
  try{localStorage.setItem('fu-theme',t);}catch(e){}
  const btn=$('#themeBtn'); if(btn) btn.textContent = t==='dark'?'☀️':'🌙';
  if(window.__charts){window.__charts.forEach(c=>{try{c.destroy();}catch(e){}});window.__charts=[];}
  if(typeof drawTrend==='function') drawTrend();
  if(typeof drawStockSparks==='function') drawStockSparks();
}
(function(){const b=$('#themeBtn'); if(b){b.textContent=curTheme()==='dark'?'☀️':'🌙'; b.addEventListener('click',()=>setTheme(curTheme()==='dark'?'light':'dark'));}})();

/* ── 탭 가로스크롤 페이드(모바일) ── */
(function(){const w=$('#tabswrap'),t=$('#tabs'); if(!w||!t)return;
  const upd=()=>{w.classList.toggle('more', t.scrollWidth - t.clientWidth - t.scrollLeft > 4);};
  t.addEventListener('scroll',upd); window.addEventListener('resize',upd); setTimeout(upd,200);})();

/* ── 워치리스트(localStorage) ── */
let WL=(()=>{try{return new Set(JSON.parse(localStorage.getItem('fu-watch')||'[]'));}catch(e){return new Set();}})();
function wlKey(kind,name){return kind+':'+name;}
function isWatched(kind,name){return WL.has(wlKey(kind,name));}
function toggleWatch(kind,name){const k=wlKey(kind,name); if(WL.has(k))WL.delete(k); else WL.add(k); try{localStorage.setItem('fu-watch',JSON.stringify([...WL]));}catch(e){}}
function renderWatchHome(){
  const host=$('#watchHome'); if(!host)return;
  const items=[...WL];
  if(!items.length){host.innerHTML=`<div class="card"><div class="sec-title" style="margin:0 0 4px;font-size:17px">⭐ 내 워치리스트</div><div class="watch-empty">종목·섹터 옆의 ☆ 를 눌러 관심 항목을 모아보세요 — 여기에 바로 모입니다.</div></div>`;return;}
  const chips=items.map(k=>{const idx=k.indexOf(':');const kind=k.slice(0,idx),name=k.slice(idx+1);
    const dataAttr=kind==='stock'?`data-stock="${esc(name)}"`:`data-go="sectors" data-sector="${esc(name)}"`;
    return `<span class="chip" ${dataAttr}><span style="color:var(--gold)">★</span> ${esc(name)} <span style="color:var(--text-4);font-size:10px">${kind==='stock'?'종목':'섹터'}</span></span>`;}).join('');
  host.innerHTML=`<div class="card"><div class="sec-title" style="margin:0 0 4px;font-size:17px">⭐ 내 워치리스트 <span class="count-badge">${items.length}</span></div><div class="sec-sub">클릭하면 해당 항목으로 이동 · 이 브라우저에 저장됩니다</div><div>${chips}</div></div>`;
}

/* ── 모멘텀: 시장 데이터 우선, 없으면 언급 최근성 폴백 ── */
function dnum(d){ if(!d)return null;
  let m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(d);
  if(m)return Math.floor(Date.UTC(+m[1],+m[2]-1,+m[3])/864e5);
  m=/^(\d{4})-W(\d{2})$/.exec(d);
  if(m){const s=new Date(Date.UTC(+m[1],0,1+(+m[2]-1)*7));const dow=s.getUTCDay()||7; s.setUTCDate(s.getUTCDate()+1-dow); return Math.floor(s.getTime()/864e5);}
  return null;}
const TO_DAY=(()=>{const t=dnum((D.build&&D.build.to)||''); return t||Math.floor(Date.now()/864e5);})();
function mentionMomentum(mentions){
  const days=(mentions||[]).map(m=>dnum(m.date)).filter(x=>x!=null);
  if(!days.length)return null;
  const rec=days.filter(x=>x>=TO_DAY-13).length;
  const pri=days.filter(x=>x<TO_DAY-13&&x>=TO_DAY-27).length;
  if(rec>=3&&rec>pri*1.5) return {cls:'mo-hot',txt:'🔥 언급 가열',reason:`최근 14일 ${rec}회 · 직전 14일 ${pri}회`};
  if(rec>=2&&rec>pri)     return {cls:'mo-warm',txt:'↗ 언급 상승',reason:`최근 14일 ${rec}회 · 직전 14일 ${pri}회`};
  if(pri>=2&&rec<=pri*0.5) return {cls:'mo-cool',txt:'❄ 언급 냉각',reason:`최근 14일 ${rec}회 · 직전 14일 ${pri}회`};
  if(rec>=1)              return {cls:'mo-flat',txt:'· 언급 유지',reason:`최근 14일 ${rec}회 · 직전 14일 ${pri}회`};
  return null;
}
function marketMomentum(mm){
  if(!mm||!mm.state)return null;
  const cls={hot:'mo-hot',warm:'mo-warm',cool:'mo-cool',flat:'mo-flat'}[mm.state]||'mo-flat';
  return {cls,txt:mm.label||({hot:'🔥 시장 과열',warm:'↗ 시장 상승',cool:'❄ 시장 냉각',flat:'· 시장 유지'}[mm.state]||'· 시장 유지'),reason:mm.reason||'',score:mm.score};
}
function momentumOf(o){
  if(Array.isArray(o))return mentionMomentum(o);
  const m=marketMomentum(o&&o.market_momentum);
  if(m)return m;
  return mentionMomentum(o&&o.mentions);
}
function momentumChip(o){
  const m=momentumOf(o);
  if(!m)return '';
  const title=esc([m.reason,m.score!=null?`점수 ${m.score}`:''].filter(Boolean).join(' · '));
  return `<span class="mo-chip ${m.cls}" title="${title}">${m.txt}</span>`;
}
const SECMAX=Math.max(1,...((D.sectors||[]).map(s=>s.count||0)));

/* ── 스파크라인(주별 언급 빈도) ── */
function weeklyCounts(mentions){
  const from=dnum((D.build&&D.build.from)||''),to=TO_DAY;
  if(from==null)return [];
  const weeks=Math.max(1,Math.ceil((to-from)/7));
  const arr=new Array(weeks+1).fill(0);
  (mentions||[]).forEach(m=>{const x=dnum(m.date); if(x==null)return; let wi=Math.floor((x-from)/7); if(wi<0)wi=0; if(wi>weeks)wi=weeks; arr[wi]++;});
  return arr;
}
function drawSpark(cv,counts){
  if(!cv||!counts||counts.length<2)return;
  const ctx=cv.getContext('2d'),W=cv.width,H=cv.height,pad=5;
  ctx.clearRect(0,0,W,H);
  const max=Math.max(1,...counts),n=counts.length;
  const gold=getComputedStyle(document.documentElement).getPropertyValue('--gold').trim()||'#b8860b';
  const x=i=>pad+i*(W-2*pad)/(n-1), y=v=>H-pad-(v/max)*(H-2*pad);
  ctx.beginPath();ctx.moveTo(x(0),H-pad);counts.forEach((v,i)=>ctx.lineTo(x(i),y(v)));ctx.lineTo(x(n-1),H-pad);ctx.closePath();
  ctx.fillStyle=gold+'22';ctx.fill();
  ctx.beginPath();counts.forEach((v,i)=>{const px=x(i),py=y(v);i?ctx.lineTo(px,py):ctx.moveTo(px,py);});
  ctx.strokeStyle=gold;ctx.lineWidth=2;ctx.lineJoin='round';ctx.stroke();
  ctx.beginPath();ctx.arc(x(n-1),y(counts[n-1]),3,0,7);ctx.fillStyle=gold;ctx.fill();
}
const STOCK_BY_NAME={};(D.stocks||[]).forEach(s=>STOCK_BY_NAME[s.name]=s);
// ── 종목 상세: 테마·수급 멘션 더보기(초기 10 + 나머지 펼침) ──
document.addEventListener('click',e=>{
  const b=e.target.closest('.st-more'); if(!b)return;
  const rest=b.previousElementSibling;
  if(rest&&rest.classList.contains('st-rest')){ rest.style.display=''; b.remove(); }
});
// ── 채팅 더보기/접기 (data-chat-* 만 처리; data-stock 전역 핸들러와 분리) ──
function chatArr(stockName, kind){
  const s=STOCK_BY_NAME[stockName]; if(!s||!s.chat) return [];
  return kind==='opinion' ? (s.chat.opinions||[]) : (kind==='market' ? (s.chat.market_news||[]) : (s.chat.news||[]));
}
document.addEventListener('click', e=>{
  // 1) 의견/시황 더보기 (kind 일반화)
  const opMore=e.target.closest('.chat-more');
  if(opMore){
    const name=opMore.dataset.chatStock, kind=opMore.dataset.chatKind||'opinion';
    const shown=+opMore.dataset.chatShown;
    const arr=chatArr(name,kind); const next=Math.min(arr.length, shown+CHAT_MORE);
    const frag=arr.slice(shown,next).map((m,i)=>chatMentionRow(STOCK_BY_NAME[name],kind,m,shown+i)).join('');
    opMore.insertAdjacentHTML('beforebegin',frag);
    opMore.dataset.chatShown=next;
    const label=kind==='market'?'시황':'의견';
    if(next>=arr.length) opMore.remove(); else opMore.textContent=`＋ ${label} ${arr.length-next}건 더보기`;
    return;
  }
  // 2) 뉴스 더보기
  const nwMore=e.target.closest('.chat-more-news');
  if(nwMore){
    const name=nwMore.dataset.chatStock, shown=+nwMore.dataset.chatShown;
    const s=STOCK_BY_NAME[name], arr=(s&&s.chat&&s.chat.news)||[];
    const next=Math.min(arr.length, shown+CHAT_MORE);
    nwMore.insertAdjacentHTML('beforebegin', arr.slice(shown,next).map(chatNewsRow).join(''));
    nwMore.dataset.chatShown=next;
    if(next>=arr.length) nwMore.remove(); else nwMore.textContent=`＋ 뉴스 ${arr.length-next}건 더보기`;
    return;
  }
});
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
// 관련 시황 <details> 최초 펼침 시 채우기 + 더보기
document.addEventListener('toggle', e=>{
  const d=e.target.closest('details.chat-mkt'); if(!d||!d.open) return;
  const body=d.querySelector('.chat-mkt-body'); if(!body || +body.dataset.chatShown>0) return;
  const name=body.dataset.chatStock, arr=chatArr(name,'market');
  const n=Math.min(arr.length,5);
  body.innerHTML=arr.slice(0,n).map((m,i)=>chatMentionRow(STOCK_BY_NAME[name],'market',m,i)).join('')
    + (arr.length>n?`<div class="chat-more" data-chat-stock="${esc(name)}" data-chat-kind="market" data-chat-shown="${n}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 시황 ${arr.length-n}건 더보기</div>`:'');
  body.dataset.chatShown=n;
}, true);
/* ── 연관 종목(동시 언급) 맵 — Obsidian 백링크 벤치마크 ── */
const CO_MAP=(()=>{
  const co={};
  const add=(arr)=>{const names=[...new Set((arr||[]).map(x=>gClean(x)).filter(n=>STOCK_BY_NAME[n]))];
    for(let i=0;i<names.length;i++)for(let j=0;j<names.length;j++){if(i===j)continue;
      (co[names[i]]=co[names[i]]||{})[names[j]]=(co[names[i]][names[j]]||0)+1;}};
  (D.sectors||[]).forEach(s=>(s.mentions||[]).forEach(m=>add(m.stocks)));
  (D.supply_days||[]).forEach(d=>add(d.stocks));
  const out={};
  Object.keys(co).forEach(n=>{out[n]=Object.entries(co[n]).sort((a,b)=>b[1]-a[1]).slice(0,6);});
  return out;
})();
function relatedChips(name){
  const rel=CO_MAP[name]; if(!rel||!rel.length) return '';
  return `<div style="margin:10px 0 4px;font-size:11.5px;color:var(--text-3)">🔗 함께 언급된 종목</div>
    <div>${rel.map(([n,c])=>`<span class="tag" data-stock="${esc(n)}">${esc(n)} <span style="color:var(--text-4)">${c}</span></span>`).join('')}</div>`;
}
function drawStockSparks(){$$('.strow-spark').forEach(cv=>{const s=STOCK_BY_NAME[cv.dataset.sparkName]; if(s)drawSpark(cv,weeklyCounts(s.mentions));});}

/* ── 이벤트 카드 ── */
function eventCards(){
  const ev=(D.events||[]).slice().sort((a,b)=>(b.seen||'').localeCompare(a.seen||'')).slice(0,12);
  return ev.map(e=>`<div class="evcard"><div class="ed">${esc(fmtDate(e.seen))} ${srcLink(e.id)}</div><div class="et">${esc(e.title)}</div><div class="ex">${esc(e.desc||'')}</div></div>`).join('');
}

/* ── 워치 토글(인라인 핸들러: 행 펼침은 막되 토글은 직접 처리) ── */
function toggleWatchEl(el){const k=el.dataset.watch,idx=k.indexOf(':');const kind=k.slice(0,idx),name=k.slice(idx+1);
  toggleWatch(kind,name);const on=isWatched(kind,name);el.classList.toggle('on',on);el.textContent=on?'★':'☆';renderWatchHome();}
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&!/input|textarea/i.test(e.target.tagName||'')){e.preventDefault();const q=$('#q');if(q)q.focus();}
  if(e.key==='Escape'){const p=$('#searchPanel');if(p)p.classList.remove('open');}
});

