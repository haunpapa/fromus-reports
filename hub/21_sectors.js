/* ───────── SECTORS ───────── */
function renderSectors(){
  const secs=D.sectors||[];
  $('#view-sectors').innerHTML=`
    <div class="sec-title">🧩 섹터·테마 클러스터 <span class="count-badge">${secs.length}</span></div>
    <div class="sec-sub">${RECENT_LABEL} · 코너 편성+수급·시황 간접 언급 합산 · 카드를 누르면 시점별 전개</div>
    <div class="cluster">${secs.map((s,i)=>sectorCard(s,i)).join('')}</div>`;
}
function sectorCard(s,i){
  const stocks=(s.stocks||[]).slice(0,12);
  const tl=(s.mentions||[]).slice().reverse().map(m=>`
    <div class="row"><span class="d">${esc(fmtDate(m.date))}</span> · ${m.kind&&m.kind!=='코너'?`<span class="tag" style="font-size:10px">${esc(m.kind)}</span> `:''}<b>${esc(m.name)}</b>${m.sub?` <span style="color:var(--text-3)">(${esc(m.sub)})</span>`:''} ${srcLink(m.id)}
      ${m.note?`<div style="color:var(--text-3);margin-top:3px">${esc(m.note.slice(0,180))}</div>`:''}</div>`).join('');
  // ── 채팅 테마 결합 (D.chat.themes 가 dict 일 때만; 기존 빌드는 이름 리스트) ──
  const tmap = (D.chat && !Array.isArray(D.chat.themes)) ? (D.chat.themes||{}) : {};
  const ct = tmap[s.theme];
  const chatHead = ct ? `<div class="sc-chat">💬 채팅 의견 ${ct.opinions_count}건 · <span style="color:#7c3aed">강세 ${ct.stance.bullish} · 약세 ${ct.stance.bearish} · 관망 ${ct.stance.watch}</span>
    <div class="sc-chat-stocks">${(ct.stocks||[]).map(n=>`<span class="tag" data-stock="${esc(n)}">${esc(n)}</span>`).join('')}</div></div>` : '';
  const chatDetail = (ct && (ct.opinions||[]).length) ? `<div class="sc-chat-ops"><div style="font-size:11.5px;font-weight:700;color:#7c3aed;margin-bottom:3px">💬 대표 의견</div>${ct.opinions.map(o=>`<div class="mention"><span class="md">${esc(fmtDate(o.date))}</span> <span class="tag" data-stock="${esc(o.stock)}">${esc(o.stock)}</span> <span style="color:var(--text-3)">${esc(o.sharer||'')}</span> ${esc((o.snippet||'').slice(0,120))}</div>`).join('')}</div>` : '';
  return `<div class="scard">
    <div class="scard-head" onclick="this.parentNode.querySelector('.scard-detail').classList.toggle('open')">
      <span class="scard-rank serif">${i+1}</span>
      <span class="scard-name">${esc(s.theme)}</span>
      <button class="star ${isWatched('sector',s.theme)?'on':''}" data-watch="sector:${esc(s.theme)}" title="워치리스트에 추가/제거" onclick="event.stopPropagation();toggleWatchEl(this)">${isWatched('sector',s.theme)?'★':'☆'}</button>
      <span class="count-badge">${s.count}회</span>
    </div>
    <div class="intensity"><i style="width:${Math.round((s.count||0)/SECMAX*100)}%"></i></div>
    <div style="margin:2px 0 2px;font-size:11px;color:var(--text-3)">코너 ${s.direct??s.count}회 · 간접 언급 ${s.indirect??0}회${s.rep?` · 대표님 연관 ${s.rep}회`:''}</div>
    <div style="margin:2px 0 8px">${momentumChip(s)}</div>
    <div class="scard-stocks">${stocks.map(n=>`<span class="tag" data-stock="${esc(n)}">${esc(n)}</span>`).join('')||'<span style="font-size:12px;color:var(--text-4)">개별 종목 태그 없음</span>'}</div>
    ${chatHead}
    <span class="toggle" onclick="this.parentNode.querySelector('.scard-detail').classList.toggle('open')">▾ 시점별 전개 ${(s.mentions||[]).length}건</span>
    <div class="scard-detail"><div class="mini-tl">${tl}</div>${chatDetail}</div>
  </div>`;
}

