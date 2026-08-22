/* ───────── GLOSSARY ───────── */
let glossQuery='';
function renderGlossary(){
  $('#view-glossary').innerHTML=`
    <div class="sec-title">📚 경제 용어 사전 <span class="count-badge">${(D.glossary||[]).length}</span></div>
    <div class="sec-sub">리포트의 교육·용어 카드 전체 누적 (경제 교실·쉬운 설명·심화·암기·신조어 등)</div>
    <div class="controls"><input id="glossq" type="text" placeholder="용어 검색… (예: ADR, 멀티플, 레버리지)" value="${esc(glossQuery)}"></div>
    <div id="glossList"></div>`;
  $('#glossq').addEventListener('input',e=>{glossQuery=e.target.value;drawGloss();});
  drawGloss();
}
function drawGloss(){
  const q=glossQuery.trim().toLowerCase();
  let list=(D.glossary||[]).filter(g=>!q||(g.term+g.body).toLowerCase().includes(q));
  const host=$('#glossList');
  host.innerHTML=list.length?list.map(g=>`
    <div class="gcard">
      ${g.tag?`<span class="gtag">${esc(g.tag)}</span>`:''}
      <div class="gterm">${esc(g.term)}</div>
      <div class="gbody">${esc(g.body)}</div>
      <div class="gdate">${esc(fmtDate(g.date))} ${srcLink(g.id)}</div>
    </div>`).join(''):'<div class="empty">검색 결과가 없습니다.</div>';
}

