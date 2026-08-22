/* ───────── STRATEGY ───────── */
let stanceOrder='desc';   // 기본: 최신 자료부터(내림차순)
function renderStrategy(){
  $('#view-strategy').innerHTML=`
    <div class="sec-title">🧭 팀 스탠스 변화 <span class="count-badge">${(D.stance||[]).length}</span></div>
    <div class="sec-sub">대표님·팀의 관점이 어떻게 움직였나 — <span class="toggle" id="ord">▾ 시간순/역순 전환</span></div>
    <div id="stanceWrap"></div>
    <div class="sec-title">💡 살아있는 전략 원칙 <span class="count-badge">${(D.principles||[]).length}</span></div>
    <div class="sec-sub">전체 기간 반복·강화된 핵심 원칙 — 카드를 누르면 근거</div>
    <div id="prinWrap"></div>`;
  $('#ord').addEventListener('click',()=>{stanceOrder=stanceOrder==='asc'?'desc':'asc';drawStance();});
  drawStance();
  $('#prinWrap').innerHTML=(D.principles||[]).map(prinCard).join('');
}
function drawStance(){
  let list=(D.stance||[]).slice();
  if(stanceOrder==='desc') list.reverse();
  $('#stanceWrap').innerHTML=`<div class="stl">${list.map(s=>`
    <div class="stl-item">
      <span class="stl-dot ${s.rtype==='weekly'?'w':''}"></span>
      <div class="stl-date">${esc(fmtDate(s.date))}${s.weekday?' ('+esc(s.weekday)+')':''} ${s.rtype==='weekly'?'· 주간':''} ${srcLink(s.id)}</div>
      <div class="stl-head">${esc(s.headline||'')}</div>
      ${s.quote?`<div class="stl-quote">“${esc(s.quote)}”</div>`:''}
      <div class="stl-points">${(s.points||[]).map(p=>`<span class="chip">${esc(p.length>60?p.slice(0,60)+'…':p)}</span>`).join('')}</div>
    </div>`).join('')}</div>`;
}
function prinCard(p){
  const max=(D.principles||[])[0]?.count||1;
  const occ=(p.occurrences||[]).slice().reverse().map(o=>`
    <div class="mention"><span class="md">${esc(fmtDate(o.date))}</span>
      <span class="src-pill 테마">${esc(o.source||'')}</span>
      <span>${esc(o.text)} ${srcLink(o.id)}</span></div>`).join('');
  const parts=p.principle.split(' — ');
  return `<div class="pcard">
    <div class="pcard-head" onclick="this.parentNode.querySelector('.pcard-detail').classList.toggle('open')">
      <span class="pcard-ico">${p.icon||'•'}</span>
      <span class="pcard-name">${esc(parts[0])}${parts[1]?`<div style="font-size:12px;color:var(--text-3);font-weight:400;margin-top:2px">${esc(parts[1])}</div>`:''}</span>
      <span class="pcard-meta">${p.count}회<br>~${esc(fmtDate(p.last_seen))}</span>
    </div>
    <div class="pbar"><i style="width:${Math.round(p.count/max*100)}%"></i></div>
    <div class="pcard-detail">${occ}</div>
  </div>`;
}

