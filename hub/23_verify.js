/* ───────── VERIFY ───────── */
let vHorizon = 20;
let vShowLow = false;
const PRIMARY_H = ((D.verify&&D.verify.meta&&D.verify.meta.primary)||20);
const vPct = x => x==null ? '—' : (x>0?'+':'')+x.toFixed(1)+'%p';

function verifyOn(){ return !!(D.verify && D.verify.enabled); }
function syncVerifyTab(){ $$('.tab[data-tab="verify"]').forEach(b=>{ b.style.display = verifyOn()?'':'none'; }); }

function renderVerify(){
  const host=$('#view-verify'); if(!host) return;
  syncVerifyTab();
  if(!verifyOn()){ host.innerHTML=''; return; }
  const V=D.verify, m=V.meta||{}, key='h'+vHorizon, s=(V.summary||{})[key]||{};
  const toggle=(m.horizons||[5,20,60]).map(h=>
    `<button data-vh="${h}" class="${h===vHorizon?'on':''}">${h}일</button>`).join('');
  const warn=(s.pending||0)>(s.judged||0)?' vh-warn':'';
  host.innerHTML=`
    <div class="sec-title">✅ 콜 검증 <span class="count-badge">${m.calls||0}</span></div>
    <div class="sec-sub">채팅에서 방향을 밝힌 발화를 이후 실제 주가와 대조했다 —
      발화 다음 거래일 종가 진입 · 거래일 기준 구간 · 지수 대비 초과수익</div>
    <div class="v-toggle" id="vHorizon">${toggle}</div>
    <div class="v-score">
      <div class="v-cell"><div class="v-num">${s.hit_rate==null?'—':s.hit_rate.toFixed(1)+'%'}</div>
        <div class="v-lbl">적중률 (${s.hit||0}/${s.judged||0})</div></div>
      <div class="v-cell"><div class="v-num">${vPct(s.avg_excess)}</div>
        <div class="v-lbl">평균 초과수익</div></div>
      <div class="v-cell${warn}"><div class="v-num">${s.pending||0}</div>
        <div class="v-lbl">판정 대기</div></div>
      <div class="v-cell"><div class="v-num">${s.bullish||0} · ${s.bearish||0}</div>
        <div class="v-lbl">강세 · 약세</div></div>
    </div>
    <div class="v-note">강세 ${s.bullish||0}건 대 약세 ${s.bearish||0}건으로 강세 편향이 크다 —
      사실상 강세 의견의 초과수익 검증이다. 표본이 얇은 종목은 아래로 내렸다. 투자 권유가 아니다.</div>
    <div id="vRank"></div>`;
  $('#vHorizon').addEventListener('click',e=>{const b=e.target.closest('button');
    if(b){vHorizon=+b.dataset.vh;renderVerify();}});
  drawVerifyRank();
}

function drawVerifyRank(){
  const key='h'+vHorizon, all=(D.verify.stocks||[]);
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
    if(!box.dataset.filled){ box.innerHTML=vCallRows(h.dataset.vstock); box.dataset.filled='1'; }
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

function vCallRows(name){
  const key='h'+vHorizon;
  const cs=(D.verify.calls||[]).filter(c=>c.stock===name)
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

