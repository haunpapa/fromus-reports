/* ───────── CHAT GLOBAL SECTIONS ───────── */
function cgDesc(arr){ return [...(arr||[])].sort((a,b)=>(b.date||'').localeCompare(a.date||'')); } // 불변 date 역순
const CG_INIT = { strategy:6, targets:12, actions:8, news:6, readings:6 };
const CG_SECS = [
  {key:'strategy', icon:'🧭', label:'전략'},
  {key:'targets',  icon:'🎯', label:'목표가'},
  {key:'actions',  icon:'💡', label:'액션'},
  {key:'news',     icon:'📰', label:'뉴스'},
  {key:'readings', icon:'📚', label:'교육'},
  {key:'qna',      icon:'❓', label:'Q&A'},
];
function cgStrategyRow(s){
  const meta = `<span class="md">${esc(fmtDate(s.date))}</span> <span style="color:var(--text-3)">${esc(s.sharer||'')}</span>`;
  const desc = esc(s.desc||'');
  const long = desc.length>140;
  return `<div class="cg-card">${esc(s.emoji||'')} <b>${esc(s.title||'')}</b> ${meta}
    <div class="cg-body ${long?'cg-clip':''}" ${long?'data-cg-expand="1" style="cursor:pointer"':''}>${desc}</div></div>`;
}
function cgTargetRow(t){
  const unit = (t.unit||'').trim();
  return `<div class="cg-row"><span class="tag" data-stock="${esc(t.stock||'')}">${esc(t.stock||'')}</span>
    <b style="color:#7c3aed">${esc(t.value||'')}${unit?esc(unit):''}</b>
    <span class="md">${esc(fmtDate(t.date))}</span> <span style="color:var(--text-3)">${esc(t.sharer||'')}</span></div>`;
}
function cgActionRow(a){
  const k = a.kind||''; // do / watch / dont
  const c = k==='do'?'#16a34a':(k==='dont'?'#dc2626':'#d97706');
  const ic = k==='do'?'✅':(k==='dont'?'⛔':'👀');
  return `<div class="cg-row"><span style="color:${c}">${ic}</span> ${esc(a.text||'')}
    <span class="md">${esc(fmtDate(a.date))}</span> <span style="color:var(--text-3)">${esc(a.sharer||'')}</span></div>`;
}
function cgNewsRow(n){
  return `<div class="cg-row"><span class="md">${esc(fmtDate(n.date))}</span> ${esc(n.title||'')}
    <a class="src" href="${esc(n.url||'#')}" target="_blank" rel="noopener">${esc(n.outlet||'열기')}↗</a></div>`;
}
function cgReadingRow(r){
  const body = esc(r.body||''); const long = body.length>140;
  return `<div class="cg-card"><span class="src-pill 테마">${esc(r.tag||'📚')}</span> <b>${esc(r.title||'')}</b>
    <span class="md">${esc(fmtDate(r.date))}</span> <span style="color:var(--text-3)">${esc(r.sharer||'')}</span>
    <div class="cg-body ${long?'cg-clip':''}" ${long?'data-cg-expand="1" style="cursor:pointer"':''}>${body}</div></div>`;
}
function cgQnaRow(q){
  return `<div class="cg-card"><div><b>Q.</b> ${esc(q.q||'')} <span style="color:var(--text-3)">${esc(q.q_by||'')} · ${esc(fmtDate(q.q_date))}</span></div>
    <div style="margin-top:4px"><b>A.</b> ${esc(q.a||'')} <span style="color:var(--text-3)">${esc(q.a_by||'')} · ${esc(fmtDate(q.a_date))}</span></div></div>`;
}
const CG_RENDERERS = { strategy:cgStrategyRow, targets:cgTargetRow, actions:cgActionRow, news:cgNewsRow, readings:cgReadingRow, qna:cgQnaRow };
function renderChatView(){
  const c = D.chat || {};
  const chips = CG_SECS.filter(s=>(c[s.key]||[]).length)
    .map(s=>`<a class="cg-chip" href="#cg-${s.key}">${s.icon} ${s.label} ${ (c[s.key]||[]).length }</a>`).join('');
  const sections = CG_SECS.map(s=>{
    const arr = cgDesc(c[s.key]);
    if(!arr.length) return '';
    const init = s.key==='qna' ? arr.length : (CG_INIT[s.key]||6);
    const shown = arr.slice(0, init).map(CG_RENDERERS[s.key]).join('');
    const more = arr.length>init
      ? `<div class="cg-more" data-cg-sec="${s.key}" data-cg-shown="${init}" style="cursor:pointer;color:#16a34a;font-size:12px;margin:5px 0">＋ ${s.label} ${arr.length-init}건 더보기</div>` : '';
    return `<div class="sec-title" id="cg-${s.key}">${s.icon} ${s.label} <span class="count-badge">${arr.length}</span></div>
      <div class="cg-list" data-cg-list="${s.key}">${shown}</div>${more}`;
  }).join('');
  $('#view-chat').innerHTML = `<div class="cg-jump">${chips}</div>${sections}`;
}

