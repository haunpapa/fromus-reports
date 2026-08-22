/* ───────── STOCK DETAIL (#stock/<이름>) ─────────
   공유 가능한 단일 종목 화면. 주가 시계열(C4)·AI 이유(C6)는 없으면 조용히 빠진다. */
let sdName='';
function openStock(name){
  if(!STOCK_BY_NAME[name]) { showTab('stocks'); stockQuery=name; renderStocks(); return; }
  sdName=name;
  showTab('stock', true);
  renderStockDetail(name);
  try{history.replaceState(null,'','#stock/'+encodeURIComponent(name));}catch(e){}
  window.scrollTo({top:0,behavior:'smooth'});
}
function sdSeries(name){                       // 주가 시계열: 채팅 코호트 → 리포트 코호트 순 (C4, 없으면 null)
  const a=VMAP[name]; if(a&&a.series&&a.series.length>1) return a.series;
  const r=((D.verify&&D.verify.report&&D.verify.report.stocks)||[]).find(s=>s.name===name);
  return (r&&r.series&&r.series.length>1) ? r.series : null;
}
function sdCalls(name){
  const core=((D.verify&&D.verify.calls)||[]).filter(c=>c.stock===name).map(c=>({...c,cohort:'채팅'}));
  const rep=((D.verify&&D.verify.report&&D.verify.report.calls)||[]).filter(c=>c.stock===name).map(c=>({...c,cohort:'리포트'}));
  return core.concat(rep);
}
/* 주가 선 + 리포트 언급(점) + 콜(삼각형) 오버레이 — 외부 라이브러리 없이 canvas 직접 */
function drawPriceOverlay(cv, series, mentionDates, calls){
  if(!cv) return;
  const ctx=cv.getContext('2d'), dpr=window.devicePixelRatio||1;
  const W=cv.clientWidth||600, H=cv.clientHeight||180; cv.width=W*dpr; cv.height=H*dpr; ctx.scale(dpr,dpr);
  const cs=getComputedStyle(document.documentElement);
  const gold=cs.getPropertyValue('--gold').trim()||'#9a7508', grid=cs.getPropertyValue('--grid').trim()||'#ece6d7', tx=cs.getPropertyValue('--text-4').trim()||'#aaa';
  const pad={l:44,r:10,t:10,b:20};
  const xs=series.map(p=>dnum(p[0])), ys=series.map(p=>p[1]);
  const x0=Math.min(...xs), x1=Math.max(...xs), y0=Math.min(...ys), y1=Math.max(...ys);
  const X=d=>pad.l+(d-x0)/Math.max(1,x1-x0)*(W-pad.l-pad.r), Y=v=>pad.t+(1-(v-y0)/Math.max(1e-9,y1-y0))*(H-pad.t-pad.b);
  ctx.clearRect(0,0,W,H);
  ctx.strokeStyle=grid; ctx.lineWidth=1; ctx.font='10px JetBrains Mono, monospace'; ctx.fillStyle=tx; ctx.textAlign='right';
  [y0,(y0+y1)/2,y1].forEach(v=>{ const y=Y(v); ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(W-pad.r,y); ctx.stroke();
    ctx.fillText(v>=1000?Math.round(v).toLocaleString():v.toFixed(1), pad.l-4, y+3); });
  ctx.beginPath(); series.forEach((p,i)=>{ const x=X(xs[i]), y=Y(p[1]); i?ctx.lineTo(x,y):ctx.moveTo(x,y); });
  ctx.strokeStyle='#2f5fd0'; ctx.lineWidth=1.8; ctx.lineJoin='round'; ctx.stroke();
  const yAt=d=>{ let best=null; for(let i=0;i<xs.length;i++){ if(xs[i]<=d) best=i; } return best==null?null:Y(ys[best]); };
  (mentionDates||[]).forEach(d=>{ const dd=dnum(d); if(dd==null||dd<x0||dd>x1) return; const y=yAt(dd); if(y==null) return;
    ctx.beginPath(); ctx.arc(X(dd),y,3.2,0,7); ctx.fillStyle=gold; ctx.fill(); });
  (calls||[]).forEach(c=>{ const dd=dnum(c.date); if(dd==null||dd<x0||dd>x1) return; const y=yAt(dd); if(y==null) return;
    ctx.beginPath(); ctx.moveTo(X(dd),y-9); ctx.lineTo(X(dd)-5,y-2); ctx.lineTo(X(dd)+5,y-2); ctx.closePath();
    ctx.fillStyle=c.stance==='bearish'?'#c2402f':'#247a3d'; ctx.fill(); });
  ctx.textAlign='center'; ctx.fillStyle=tx;
  [x0,x1].forEach(d=>ctx.fillText(fmtDate(new Date(d*864e5).toISOString().slice(0,10)), X(d), H-6));
}
function sdCallRows(name){
  const key='h'+PRIMARY_H;
  const cs=sdCalls(name).sort((a,b)=>a.date<b.date?1:a.date>b.date?-1:0);
  if(!cs.length) return '<div class="v-mini">검증 대상 콜이 없습니다.</div>';
  return cs.map(c=>{ const r=c[key];
    const badge = c.conflict ? '<span class="v-badge conf">의견 갈림</span>'
      : (c.error==='no_price'||c.error==='bad_entry') ? '<span class="v-badge pend">가격 없음</span>'
      : !r ? '<span class="v-badge pend">판정 대기</span>'
      : `<span class="v-badge ${r.hit?'hit':'miss'}">${vPct(r.excess!=null?r.excess:r.ret)}</span>`;
    const src=(c.sources||[])[0]||{};
    return `<div class="mention"><span class="md">${esc(fmtDate(c.date))}</span><span class="pill">${esc(c.cohort)}</span>
      <span class="v-dir ${esc(c.stance)}">${c.stance==='bullish'?'강세':'약세'}</span> ${badge}
      <span style="color:var(--text-3)">${esc(src.sharer||'')}</span> ${esc(src.snippet||'')} ${src.id?srcLink(src.id):''}</div>`; }).join('');
}
function sdNeighbors(name){
  const co=((D.chat&&D.chat.co_edges)||[]).filter(e=>e.a===name||e.b===name).sort((a,b)=>b.w-a.w).slice(0,6)
    .map(e=>{ const o=e.a===name?e.b:e.a; return `<span class="tag" data-stock="${esc(o)}">${esc(o)} <span style="color:var(--text-4)">${e.w}</span></span>`; }).join('');
  return co?`<div style="margin:10px 0 4px;font-size:11.5px;color:var(--text-3)">💬 채팅에서 함께 언급</div><div>${co}</div>`:'';
}
function renderStockDetail(name){
  const s=STOCK_BY_NAME[name]; const host=$('#view-stock'); if(!s||!host) return;
  const reason=(D.ai_digest&&D.ai_digest.stock_reasons&&D.ai_digest.stock_reasons[name])||null;   // C6
  const themes=(s.themes||[]).map(t=>`<span class="pill theme" data-go="sectors" data-sector="${esc(t)}">${esc(t)}</span>`).join('');
  const tags=(s.supply_tags||[]).map(t=>`<span class="pill supply">${esc(t)}</span>`).join('');
  const series=sdSeries(name);
  const allM=(s.mentions||[]).slice().reverse();
  host.innerHTML=`
    <span class="sd-back" data-go="stocks">← 종목 목록</span>
    <div class="sd-head">
      <button class="star ${isWatched('stock',name)?'on':''}" data-watch="stock:${esc(name)}" onclick="toggleWatchEl(this)">${isWatched('stock',name)?'★':'☆'}</button>
      <span class="sd-name">${esc(name)}</span>${momentumChip(s)}<span class="count-badge">${s.count||0}회</span>${verifyChip(name)}
      <span class="sd-act"><button type="button" class="cmp-add ${isComparePicked(name)?'on':''}" data-cmp="${esc(name)}">${isComparePicked(name)?'비교중':'비교'}</button>
        <button type="button" id="sdCopy">링크 복사</button></span>
    </div>
    <div>${themes}${tags}${s.chat?`<span class="pill" style="background:#f5f3ff;color:#7c3aed">💬 ${s.chat.count}</span>`:''}</div>
    ${reason?`<div class="sd-reason">🤖 ${esc(reason.text)} <span style="color:var(--text-4);font-size:11px">· ${esc(fmtDate(reason.as_of))} 기준 AI 요약</span></div>`:''}
    <div class="sd-grid">
      <div class="card">
        <div class="sec-title" style="margin:0 0 4px;font-size:16px">${series?'📉 주가와 언급 시점':'📈 주별 언급 빈도'}</div>
        <canvas class="sd-chart" id="sdChart"></canvas>
        <div class="sd-legend">${series?'<span><i style="background:#2f5fd0"></i>종가(주 단위)</span><span><i style="background:var(--gold)"></i>리포트 언급</span><span><i style="background:#247a3d"></i>강세 콜</span><span><i style="background:#c2402f"></i>약세 콜</span>':'<span><i style="background:var(--gold)"></i>리포트 언급 수 / 주</span>'}</div>
        ${relatedChips(name)}${sdNeighbors(name)}
      </div>
      <div class="card">
        <div class="sec-title" style="margin:0 0 4px;font-size:16px">✅ 콜 검증 <span class="v-mini">${PRIMARY_H}거래일 · 지수 대비</span></div>
        <div class="sd-calls">${sdCallRows(name)}</div>
      </div>
    </div>
    <div class="card"><div class="sec-title" style="margin:0 0 4px;font-size:16px">🗂 언급 타임라인 <span class="count-badge">${allM.length}</span></div>
      <div class="sd-mentions">${allM.map(stMentionHtml).join('')||'<div class="empty">리포트 언급 없음</div>'}</div></div>
    ${s.chat?`<div class="card">${renderChat(s)}</div>`:''}`;
  const cv=$('#sdChart');
  if(series) drawPriceOverlay(cv, series, (s.mentions||[]).map(m=>m.date), sdCalls(name));
  else if(cv){ cv.width=cv.clientWidth||600; cv.height=180; drawSpark(cv, weeklyCounts(s.mentions)); }
  const copy=$('#sdCopy');
  if(copy) copy.addEventListener('click',()=>{ const url=location.origin+location.pathname+'#stock/'+encodeURIComponent(name);
    (navigator.clipboard?navigator.clipboard.writeText(url):Promise.reject()).then(()=>{copy.textContent='복사됨';setTimeout(()=>{copy.textContent='링크 복사';},1500);}).catch(()=>prompt('링크',url)); });
}
