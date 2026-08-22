/* ───────── STOCKS ───────── */
let stockSort='count', stockQuery='', stockOnlyWatch=false, stockHotOnly=false, stockSupplyOnly=false;
let stockTheme='', stockWho='', stockMin=0;
function renderStocks(){
  $('#view-stocks').innerHTML=`
    <div class="sec-title">📈 종목 유니버스 <span class="count-badge">${(D.stocks||[]).length}</span></div>
    <div class="sec-sub">${RECENT_LABEL} · 테마/수급 출처와 시점</div>
    <div class="controls">
      <input id="stockq" type="text" placeholder="종목명 검색…" value="${esc(stockQuery)}">
      <div class="seg" id="stockSort">
        <button data-s="count" class="${stockSort==='count'?'on':''}">언급순</button>
        <button data-s="supply" class="${stockSort==='supply'?'on':''}">수급포착순</button>
        <button data-s="name" class="${stockSort==='name'?'on':''}">이름순</button>
      </div>
    </div>
    <div class="stock-tools">
      <label class="check-chip"><input id="stockWatchOnly" type="checkbox" ${stockOnlyWatch?'checked':''}> 워치만</label>
      <label class="check-chip"><input id="stockHotOnly" type="checkbox" ${stockHotOnly?'checked':''}> 뜨거운 종목</label>
      <label class="check-chip"><input id="stockSupplyOnly" type="checkbox" ${stockSupplyOnly?'checked':''}> 수급 있음</label>
      <select id="stockTheme" class="sel"><option value="">전체 테마</option>${[...new Set((D.stocks||[]).flatMap(s=>s.themes||[]))].sort((a,b)=>a.localeCompare(b,'ko')).map(t=>`<option value="${esc(t)}" ${stockTheme===t?'selected':''}>${esc(t)}</option>`).join('')}</select>
      <select id="stockWho" class="sel"><option value="">전체 수급주체</option>${['외국인','기관','연기금','투신','사모펀드'].map(g=>`<option value="${g}" ${stockWho===g?'selected':''}>${g}</option>`).join('')}</select>
      <select id="stockMin" class="sel"><option value="0">언급 전체</option><option value="3" ${stockMin===3?'selected':''}>3회+</option><option value="5" ${stockMin===5?'selected':''}>5회+</option><option value="10" ${stockMin===10?'selected':''}>10회+</option></select>
      <button class="cmp-add" id="stockReset">필터 초기화</button>
      <span class="stock-meta-line" id="stockResultMeta"></span>
    </div>
    <div id="stockList"></div>`;
  $('#stockq').addEventListener('input',e=>{stockQuery=e.target.value;drawStockList();});
  $('#stockSort').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;stockSort=b.dataset.s;$$('#stockSort button').forEach(x=>x.classList.toggle('on',x===b));drawStockList();});
  $('#stockWatchOnly').addEventListener('change',e=>{stockOnlyWatch=e.target.checked;drawStockList();});
  $('#stockHotOnly').addEventListener('change',e=>{stockHotOnly=e.target.checked;drawStockList();});
  $('#stockSupplyOnly').addEventListener('change',e=>{stockSupplyOnly=e.target.checked;drawStockList();});
  $('#stockTheme').addEventListener('change',e=>{stockTheme=e.target.value;drawStockList();});
  $('#stockWho').addEventListener('change',e=>{stockWho=e.target.value;drawStockList();});
  $('#stockMin').addEventListener('change',e=>{stockMin=+e.target.value;drawStockList();});
  $('#stockReset').addEventListener('click',()=>{stockQuery='';stockOnlyWatch=false;stockHotOnly=false;stockSupplyOnly=false;stockSort='count';stockTheme='';stockWho='';stockMin=0;renderStocks();});
  drawStockList();
}
function drawStockList(){
  let list=(D.stocks||[]).slice();
  const q=stockQuery.trim().toLowerCase();
  if(q) list=list.filter(s=>s.name.toLowerCase().includes(q));
  if(stockOnlyWatch) list=list.filter(s=>isWatched('stock',s.name));
  if(stockHotOnly) list=list.filter(s=>{const m=momentumOf(s); return m && (m.cls==='mo-hot'||m.cls==='mo-warm');});
  if(stockSupplyOnly) list=list.filter(s=>(s.supply_count||0)>0);
  if(stockTheme) list=list.filter(s=>(s.themes||[]).includes(stockTheme));
  if(stockWho) list=list.filter(s=>(s.supply_tags||[]).some(t=>t.includes(stockWho)));
  if(stockMin) list=list.filter(s=>(s.count||0)>=stockMin);
  const meta=$('#stockResultMeta'); if(meta) meta.textContent=`${list.length.toLocaleString()} / ${(D.stocks||[]).length.toLocaleString()} 종목`;
  if(stockSort==='name') list.sort((a,b)=>a.name.localeCompare(b.name,'ko'));
  else if(stockSort==='supply') list.sort((a,b)=>(b.supply_count-a.supply_count)||(b.count-a.count));
  else list.sort((a,b)=>(b.count-a.count)||a.name.localeCompare(b.name,'ko'));
  const host=$('#stockList');
  if(!list.length){host.innerHTML='<div class="empty">검색 결과가 없습니다.</div>';return;}
  host.innerHTML=list.map(stockRow).join('');
  drawStockSparks();
}
const CHAT_INIT_OP = 3, CHAT_INIT_NEWS = 4, CHAT_MORE = 10;

function chatMentionRow(s, kind, m, idx){
  return `<div class="mention chat-clk" data-chat-stock="${esc(s.name)}" data-chat-kind="${kind}" data-chat-idx="${idx}" style="cursor:pointer">
    <span class="md">${esc(fmtDate(m.date))}</span>
    <span class="src-pill" style="background:#f5f3ff;color:#7c3aed">💬 ${esc(m.sharer||'')}</span>
    <span>${esc((m.snippet||'').slice(0,120))}${(m.co_stocks&&m.co_stocks.length)?` <span style="color:var(--text-4)">+${m.co_stocks.length}</span>`:''}</span></div>`;
}
function chatNewsRow(n){
  return `<div class="mention${n.neutral?' news-neutral':''}"><span class="md">${esc(fmtDate(n.date))}</span>
    <span class="src-pill 테마">뉴스</span>
    <span>${esc(n.title)} <a class="src" href="${esc(safeHref(n.url))}" target="_blank" rel="noopener">${esc(n.outlet||'열기')}↗</a></span></div>`;
}
function renderChat(s){
  const c=s.chat; if(!c) return '';
  const st=c.stance||{};
  const badge=`<span style="color:#7c3aed">강세 ${st.bullish||0} · 약세 ${st.bearish||0} · 관망 ${st.watch||0}</span>`;
  const ops=c.opinions||[], mkt=c.market_news||[], nws=c.news||[];
  const opsN=c.opinions_n??ops.length, mktN=c.market_news_n??mkt.length, nwsN=c.news_n??nws.length;   // 코어는 앞부분만 싣고 개수를 따로 준다 (스펙 C2)
  const opHtml = ops.slice(0,CHAT_INIT_OP).map((m,i)=>chatMentionRow(s,'opinion',m,i)).join('')
    || '<div style="font-size:11.5px;color:var(--text-4)">개별 의견 없음</div>';
  const opMore = opsN>CHAT_INIT_OP
    ? `<div class="chat-more" data-chat-stock="${esc(s.name)}" data-chat-kind="opinion" data-chat-shown="${Math.min(CHAT_INIT_OP,ops.length)}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 의견 ${opsN-CHAT_INIT_OP}건 더보기</div>` : '';
  const mktBlock = mktN
    ? `<details class="chat-mkt" style="margin-top:6px"><summary style="cursor:pointer;color:#16a34a;font-size:11.5px">📰 관련 시황 ${mktN}건</summary>
        <div class="chat-mkt-body" data-chat-stock="${esc(s.name)}" data-chat-shown="0"></div></details>` : '';
  const nwHtml = nws.slice(0,CHAT_INIT_NEWS).map(chatNewsRow).join('');
  const nwMore = nwsN>CHAT_INIT_NEWS
    ? `<div class="chat-more-news" data-chat-stock="${esc(s.name)}" data-chat-shown="${Math.min(CHAT_INIT_NEWS,nws.length)}" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 뉴스 ${nwsN-CHAT_INIT_NEWS}건 더보기</div>` : '';
  return `<div style="margin-top:10px;border-top:1px dashed var(--border);padding-top:8px">
    <div style="font-size:11.5px;font-weight:700;color:#7c3aed;margin-bottom:4px">💬 채팅 근거 · ${c.count}회 · ${badge}</div>
    <div style="font-size:11px;color:var(--text-3);margin-bottom:3px">💡 의견</div>${opHtml}${opMore}
    ${mktBlock}
    ${nwsN?`<div style="font-size:11px;color:var(--text-3);margin:5px 0 3px">📰 뉴스(최신순)</div>${nwHtml}${nwMore}`:''}
  </div>`;
}
function stMentionHtml(m){
  return `<div class="mention"><span class="md">${esc(fmtDate(m.date))}</span>
      <span class="src-pill ${m.source==='수급'?'수급':'테마'}">${esc(m.source||'')}</span>
      <span>${esc(m.label||m.theme||'')}${m.annotation?` <span style="color:var(--text-3)">· ${esc(m.annotation)}</span>`:''} ${srcLink(m.id)}</span></div>`;
}
function stockRow(s){
  const themes=(s.themes||[]).slice(0,2).map(t=>`<span class="pill theme">${esc(t)}</span>`).join('');
  const tags=(s.supply_tags||[]).slice(0,2).map(t=>`<span class="pill supply">${esc(t)}</span>`).join('');
  const allM=(s.mentions||[]).slice().reverse();
  const headM=allM.slice(0,10).map(stMentionHtml).join('');
  const restM=allM.slice(10);
  const moreM=restM.length?`<div class="st-rest" style="display:none">${restM.map(stMentionHtml).join('')}</div><div class="st-more" style="cursor:pointer;color:#16a34a;font-size:11.5px;margin:3px 0">＋ 테마·수급 ${restM.length}개 더보기</div>`:'';
  const chatPill = s.chat ? `<span class="pill" style="background:#f5f3ff;color:#7c3aed">\uD83D\uDCAC ${s.chat.count}</span>` : '';
  const vPill = verifyChip(s.name);
  return `<div class="strow">
    <div class="strow-head" onclick="this.parentNode.querySelector('.strow-detail').classList.toggle('open')">
      <button class="star ${isWatched('stock',s.name)?'on':''}" data-watch="stock:${esc(s.name)}" title="워치리스트에 추가/제거" onclick="event.stopPropagation();toggleWatchEl(this)">${isWatched('stock',s.name)?'★':'☆'}</button>
      <span class="strow-name">${esc(s.name)}</span>
      ${(D.ai_digest&&D.ai_digest.stock_reasons&&D.ai_digest.stock_reasons[s.name])?`<span class="strow-sub" title="AI 요약">${esc(D.ai_digest.stock_reasons[s.name].text)}</span>`:''}
      <span class="strow-mini">${momentumChip(s)}${themes}${tags}${chatPill}${vPill}</span>
      <canvas class="strow-spark" data-spark-name="${esc(s.name)}" width="156" height="52"></canvas>
      <button class="cmp-add ${isComparePicked(s.name)?'on':''}" data-cmp="${esc(s.name)}" onclick="event.stopPropagation();toggleCompare('${esc(s.name)}')">${isComparePicked(s.name)?'비교중':'비교'}</button>
      <span class="strow-cnt">${s.count}회</span>
    </div>
    <div class="strow-detail">
      <div style="font-size:11.5px;color:var(--text-3);margin:6px 0 4px">테마 언급 ${s.theme_count||0} · 수급 포착 ${s.supply_count||0}${(s.themes||[]).length?' · '+esc(s.themes.join(', ')):''}</div>
      ${relatedChips(s.name)}
      ${headM}${moreM}${renderChat(s)}
    </div>
  </div>`;
}

