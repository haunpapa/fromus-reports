/* ───────── VERIFY ───────── */
let vHorizon = 20;
let vShowLow = false;
let vCohort = 'core';          // 'core'=채팅 콜 · 'report'=리포트 수급 포착 (합산하지 않는다)
const PRIMARY_H = ((D.verify&&D.verify.meta&&D.verify.meta.primary)||20);
const vPct = x => x==null ? '—' : (x>0?'+':'')+x.toFixed(1)+'%p';

function verifyOn(){ return !!(D.verify && D.verify.enabled); }
function syncVerifyTab(){ $$('.tab[data-tab="verify"]').forEach(b=>{ b.style.display = verifyOn()?'':'none'; }); }

function vData(){ return (vCohort==='report' && D.verify && D.verify.report && D.verify.report.enabled) ? D.verify.report : D.verify; }
function renderVerify(){
  const host=$('#view-verify'); if(!host) return;
  syncVerifyTab();
  if(!verifyOn()){ host.innerHTML=''; return; }
  const hasRep=!!(D.verify.report&&D.verify.report.enabled);
  if(!hasRep) vCohort='core';
  const V=vData(), m=V.meta||{}, key='h'+vHorizon, s=(V.summary||{})[key]||{};
  const toggle=(m.horizons||[5,20,60]).map(h=>`<button data-vh="${h}" class="${h===vHorizon?'on':''}">${h}일</button>`).join('');
  const cohortUi=hasRep?`<div class="seg" id="vCohort"><button data-cohort="core" class="${vCohort==='core'?'on':''}">채팅 콜</button><button data-cohort="report" class="${vCohort==='report'?'on':''}">리포트 수급 포착</button></div>`:'';
  const warn=(s.pending||0)>(s.judged||0)?' vh-warn':'';
  const sub = vCohort==='report'
    ? '리포트의 기관·외국인 순매수 포착을 강세 콜로 보고, 발표 다음 거래일 종가 진입 · 거래일 기준 구간 · 지수 대비 초과수익으로 대조했다 (채팅 콜과 합산하지 않음)'
    : '채팅에서 방향을 밝힌 발화를 이후 실제 주가와 대조했다 — 발화 다음 거래일 종가 진입 · 거래일 기준 구간 · 지수 대비 초과수익';
  host.innerHTML=`
    <div class="sec-title">✅ 콜 검증 <span class="count-badge">${m.calls||0}</span></div>
    <div class="sec-sub">${sub}</div>
    <div class="v-controls">${cohortUi}<div class="v-toggle" id="vHorizon">${toggle}</div></div>
    <div class="v-score">
      <div class="v-cell"><div class="v-num">${s.hit_rate==null?'—':s.hit_rate.toFixed(1)+'%'}</div><div class="v-lbl">적중률 (${s.hit||0}/${s.judged||0})</div></div>
      <div class="v-cell"><div class="v-num">${vPct(s.avg_excess)}</div><div class="v-lbl">평균 초과수익</div></div>
      <div class="v-cell${warn}"><div class="v-num">${s.pending||0}</div><div class="v-lbl">판정 대기</div></div>
      <div class="v-cell"><div class="v-num">${s.bullish||0} · ${s.bearish||0}</div><div class="v-lbl">강세 · 약세</div></div>
    </div>
    ${vCohort==='core'?`<div class="v-note">강세 ${s.bullish||0}건 대 약세 ${s.bearish||0}건으로 강세 편향이 크다 — 사실상 강세 의견의 초과수익 검증이다. 표본이 얇은 종목은 아래로 내렸다. 투자 권유가 아니다.</div>`
      :`<div class="v-note">수급 포착은 전부 강세로 본다. 포착 = 리포트 발행일 기준이며 실제 순매수일보다 하루 늦을 수 있다. 투자 권유가 아니다.</div>`}
    <div class="card"><div class="sec-title" style="margin:0 0 4px;font-size:16px">📊 ${vHorizon}거래일 초과수익 분포</div><canvas id="vHist" class="sd-chart" style="height:150px"></canvas></div>
    ${vCohort==='report'?'<div class="sec-title" style="font-size:16px">🧩 테마별</div><div id="vThemes"></div>':''}
    <div id="vRank"></div>`;
  $('#vHorizon').addEventListener('click',e=>{const b=e.target.closest('button'); if(b){vHorizon=+b.dataset.vh;renderVerify();}});
  const vc=$('#vCohort'); if(vc) vc.addEventListener('click',e=>{const b=e.target.closest('button'); if(b){vCohort=b.dataset.cohort;renderVerify();}});
  drawHistogram($('#vHist'), (V.calls||[]).filter(c=>!c.conflict&&c[key]&&c[key].excess!=null).map(c=>c[key].excess));
  if(vCohort==='report') drawThemes();
  drawVerifyRank();
}

/* 초과수익 분포 히스토그램 — 5%p 빈, 0 기준 좌(적)/우(녹) */
function drawHistogram(cv, values){
  if(!cv) return; const dpr=window.devicePixelRatio||1; const W=cv.clientWidth||600, H=150; cv.width=W*dpr; cv.height=H*dpr;
  const ctx=cv.getContext('2d'); ctx.scale(dpr,dpr); ctx.clearRect(0,0,W,H);
  const cs=getComputedStyle(document.documentElement), tx=cs.getPropertyValue('--text-4').trim()||'#aaa';
  if(!values.length){ ctx.fillStyle=tx; ctx.font='12px Noto Sans KR'; ctx.fillText('판정된 콜이 아직 없습니다', 12, 24); return; }
  const BIN=5, lo=Math.floor(Math.min(-10,...values)/BIN)*BIN, hi=Math.ceil(Math.max(10,...values)/BIN)*BIN;
  const n=(hi-lo)/BIN, bins=new Array(n).fill(0);
  values.forEach(v=>{ let i=Math.floor((v-lo)/BIN); if(i>=n)i=n-1; if(i<0)i=0; bins[i]++; });
  const max=Math.max(1,...bins), pad={l:8,r:8,t:10,b:22}, bw=(W-pad.l-pad.r)/n;
  bins.forEach((c,i)=>{ const x=pad.l+i*bw, h=(c/max)*(H-pad.t-pad.b), from=lo+i*BIN;
    ctx.fillStyle= from>=0 ? '#247a3d' : '#c2402f'; ctx.globalAlpha=.75; ctx.fillRect(x+1, H-pad.b-h, bw-2, h); ctx.globalAlpha=1;
    if(c){ ctx.fillStyle=tx; ctx.font='10px JetBrains Mono'; ctx.textAlign='center'; ctx.fillText(c, x+bw/2, H-pad.b-h-3); } });
  ctx.fillStyle=tx; ctx.font='10px JetBrains Mono'; ctx.textAlign='center';
  for(let i=0;i<=n;i+=Math.max(1,Math.round(n/8))) ctx.fillText((lo+i*BIN)+'%p', pad.l+i*bw, H-6);
}

/* 테마별 집계 (C4) — 리포트 코호트에서만 노출 */
function drawThemes(){
  const key='h'+vHorizon, rows=(D.verify.themes||[]), host=$('#vThemes'); if(!host) return;
  host.innerHTML = rows.length ? rows.map(t=>{ const h=t[key]||{};
    return `<div class="v-row"><div class="v-row-head" data-go="sectors" data-sector="${esc(t.theme)}"><span class="v-name">${esc(t.theme)}</span>
      <span class="v-mini">${t.calls}콜</span><span class="v-mini">${h.judged?`${h.hit}/${h.judged}`:'판정 전'}</span>
      <span class="v-hr">${h.hit_rate==null?'—':h.hit_rate.toFixed(0)+'%'}</span><span class="v-ex">${vPct(h.median_excess!=null?h.median_excess:h.avg_excess)}</span></div></div>`; }).join('')
    : '<div class="v-mini">테마 집계 없음</div>';
}

function drawVerifyRank(){
  const key='h'+vHorizon, all=(vData().stocks||[]);
  const main=all.filter(s=>!s.low_sample), low=all.filter(s=>s.low_sample);
  const lowCalls=low.reduce((a,s)=>a+(s.calls||0),0);
  $('#vRank').innerHTML =
    vRankRows(main,key) +
    (low.length?`<div class="v-fold" id="vFold">${vShowLow?'－':'＋'} 표본 부족 ${low.length}종목 (${lowCalls}콜)</div>
      ${vShowLow?vRankRows(low,key):''}`:'');
  const f=$('#vFold'); if(f)f.addEventListener('click',()=>{vShowLow=!vShowLow;drawVerifyRank();});
  $('#vRank').addEventListener('click',e=>{
    const h=e.target.closest('.v-row-head'); if(!h)return;
    const box=h.parentNode.querySelector('.v-row-detail');
    if(!box.dataset.filled){ box.innerHTML=vCallRows(h.dataset.vstock, vData().calls); box.dataset.filled='1'; }
    box.classList.toggle('open');
  });
}

function vRankRows(rows,key){
  return rows.map(st=>{const h=st[key]||{};
    return `<div class="v-row${st.low_sample?' low':''}">
      <div class="v-row-head" data-vstock="${esc(st.name)}">
        <span class="v-name">${esc(st.name)}</span>
        <span class="pill">${esc(st.market)}</span>
        ${st.low_sample?'<span class="v-badge low">표본 부족</span>':''}
        <span class="v-mini">${st.calls}콜</span>
        <span class="v-mini">${h.judged?`${h.hit}/${h.judged}`:'판정 전'}</span>
        <span class="v-hr">${h.hit_rate==null?'—':h.hit_rate.toFixed(0)+'%'}</span>
        <span class="v-ex">${vPct(h.avg_excess)}</span>
      </div><div class="v-row-detail"></div></div>`;}).join('');
}

function vCallRows(name, calls){
  const key='h'+vHorizon;
  const cs=((calls||D.verify.calls)||[]).filter(c=>c.stock===name)
    .sort((a,b)=>a.date<b.date?1:a.date>b.date?-1:0);
  return cs.map(c=>{
    const r=c[key];
    const badge = c.conflict ? '<span class="v-badge conf">의견 갈림</span>'
      : c.error==='no_price'||c.error==='bad_entry' ? '<span class="v-badge pend">가격 없음</span>'
      : !r ? '<span class="v-badge pend">판정 대기</span>'
      : `<span class="v-badge ${r.hit?'hit':'miss'}">${vPct(r.excess!=null?r.excess:r.ret)}</span>`;
    const who=(c.sources||[]).map(x=>esc(x.sharer)).filter(Boolean).join(', ');
    const snip=esc(((c.sources||[])[0]||{}).snippet||'');
    return `<div class="mention"><span class="md">${esc(fmtDate(c.date))}</span>
      <span class="v-dir ${esc(c.stance)}">${c.stance==='bullish'?'강세':'약세'}</span>
      ${badge} <span style="color:var(--text-3)">${who}</span> ${snip}</div>`;
  }).join('') || '<div class="v-mini">표시할 콜이 없다.</div>';
}

const VMAP=(()=>{const m={};((D.verify&&D.verify.stocks)||[]).forEach(s=>m[s.name]=s);return m;})();
function verifyChip(name){
  const st=VMAP[name]; if(!st) return '';
  // 표본 부족 종목은 적중률을 아예 노출하지 않는다 — 2콜짜리 100%가 신뢰 근거로 읽히면 안 된다
  if(st.low_sample) return `<span class="pill" style="background:var(--surface-2,#f3f0ea);color:var(--text-3)">✅ ${st.calls}콜</span>`;
  const h=st['h'+PRIMARY_H]||{};
  if(!h.judged) return '';
  return `<span class="pill" style="background:#e8f6ec;color:#16a34a" title="${h.hit}/${h.judged} 적중 · 평균 초과 ${vPct(h.avg_excess)}">✅ ${h.hit}/${h.judged} · ${vPct(h.avg_excess)}</span>`;
}

