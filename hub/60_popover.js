/* ═══════════ V3: 호버 팝오버 미리보기 (Quartz link preview) ═══════════ */
const POP=$('#popover'); let popTimer=null, popHideTimer=null;
function stockPreview(st){
  const themes=(st.themes||[]).slice(0,3).map(t=>`<span class="pill theme">${esc(t)}</span>`).join('');
  const last=(st.mentions||[]).slice(-1)[0]||{};
  const note=last.note||last.annotation||last.label||last.theme||'';
  return `<div class="pv-head"><span class="pv-kind">종목</span><span class="pv-name">${esc(st.name)}</span><span class="pv-cnt">${st.count||0}회</span></div>
    <div class="pv-pills">${momentumChip(st)}${themes}</div>
    <canvas class="pv-spark" width="560" height="68" data-pvspark="${esc(st.name)}"></canvas>
    ${note?`<div class="pv-note"><span class="pvd">${esc(fmtDate(last.date))}</span> ${esc(note.slice(0,150))}</div>`:''}
    <div class="pv-foot">테마 ${st.theme_count||0} · 수급 ${st.supply_count||0}${(st.sectors||[]).length?' · '+esc((st.sectors||[]).slice(0,3).join(', ')):''}</div>`;
}
function sectorPreview(sec){
  const why=(typeof sectorWhy==='function')?sectorWhy(sec):null;
  const note=why?(why.note||''):'';
  const stocks=(sec.stocks||[]).slice(0,8).map(n=>esc(gClean(n))).join(' · ');
  return `<div class="pv-head"><span class="pv-kind">섹터</span><span class="pv-name">${esc(sec.theme)}</span><span class="pv-cnt">${sec.count||0}회</span></div>
    <div class="pv-pills">${momentumChip(sec)}${(sec.rep||0)>0?`<span class="rep-badge">👑 대표님 강조 ${sec.rep}</span>`:''}</div>
    <div class="pv-foot" style="margin:0 0 8px">${stocks}</div>
    ${note?`<div class="pv-note"><span class="pvd">${esc(fmtDate(why.date))}</span> ${esc(note.slice(0,150))}</div>`:''}`;
}
function positionPopover(el){
  const r=el.getBoundingClientRect(); const pw=POP.offsetWidth||300, ph=POP.offsetHeight||140;
  let left=r.left, top=r.bottom+8;
  if(left+pw>innerWidth-10) left=innerWidth-pw-10; if(left<10)left=10;
  if(top+ph>innerHeight-10) top=r.top-ph-8; if(top<10)top=10;
  POP.style.left=left+'px'; POP.style.top=top+'px';
}
function openPopover(el){
  let html=null, sparkName=null;
  if(el.dataset.stock){const st=STOCK_BY_NAME[el.dataset.stock]||STOCK_BY_NAME[gClean(el.dataset.stock)]; if(st){html=stockPreview(st); sparkName=st.name;}}
  else if(el.dataset.sector){const sec=SECTOR_BY_THEME[el.dataset.sector]; if(sec)html=sectorPreview(sec);}
  if(!html)return;
  POP.innerHTML=html; POP.classList.add('on'); positionPopover(el);
  if(sparkName){const cv=POP.querySelector('[data-pvspark]'); const st=STOCK_BY_NAME[sparkName]; if(cv&&st)drawSpark(cv,weeklyCounts(st.mentions));}
}
function hidePopover(){POP.classList.remove('on');}
document.addEventListener('mouseover',e=>{
  const el=e.target.closest('[data-stock],[data-sector]'); if(!el)return;
  if(el.closest('#graphCanvas'))return;
  clearTimeout(popHideTimer); clearTimeout(popTimer);
  popTimer=setTimeout(()=>openPopover(el),200);
});
document.addEventListener('mouseout',e=>{
  const el=e.target.closest('[data-stock],[data-sector]'); if(!el)return;
  clearTimeout(popTimer); popHideTimer=setTimeout(hidePopover,140);
});
window.addEventListener('scroll',hidePopover,true);

