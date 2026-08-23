/* ───────── HOME ───────── */
function renderHome(){
  const b=D.build||{};
  const tzLabel = b.timezone_label || '한국시간(KST)';
  $('#buildMeta').textContent = `${b.from||''} ~ ${b.to||''} · 갱신 ${b.generated||''} ${tzLabel}`;
  const topSectors=(D.sectors||[]).slice(0,6);
  const topStocks=(D.stocks||[]).slice(0,10);
  const latest=(D.stance||[]).slice(-1)[0]||{};
  const topPrin=(D.principles||[]).slice(0,4);
  const REP_W=2;  // 대표님 직접 언급 가중치
  const coreSectors=(D.sectors||[]).map(s=>({s,why:sectorWhy(s),score:(s.count||0)+REP_W*(s.rep||0)}))
    .filter(x=>x.why).sort((a,b)=>(b.score-a.score)||(b.s.count-a.s.count)).slice(0,5);
  $('#view-home').innerHTML = `
    <div class="briefing"><div class="brf-in">
      <div class="brf-tag"><span class="live"></span>오늘의 브리핑<span class="brf-date">${esc(fmtDate(latest.date))} · ${esc(latest.name||'프벤져스')}</span></div>
      <div class="brf-h">${esc(latest.headline||'흩어진 리포트를 하나의 전략으로')}</div>
      ${latest.subhead?`<div class="brf-sub">${esc(latest.subhead)}</div>`:`<div class="brf-sub">데일리·위클리 리포트를 구조화해, 섹터·종목·전략·용어를 한곳에서 검색하고 점검합니다.</div>`}
      ${(latest.quote||latest.report_quote)?`<div class="brf-quote">${esc(latest.quote||latest.report_quote)}<cite>— ${esc(latest.name||'프벤져스')}, ${esc(fmtDate(latest.date))}</cite></div>`:''}
      ${(latest.points||[]).length?`<div class="brf-points">${(latest.points||[]).slice(0,4).map((p,i)=>`<div class="brf-pt"><span class="k">${i+1}</span><span>${esc(p)}</span></div>`).join('')}</div>`:''}
      ${aiDailyLines()}
    </div></div>
    ${whatsNewCard()}
    ${aiDigestCard()}
    <div class="statrow">
      <button class="stat" data-go="strategy"><div class="v">${b.reports||0}</div><div class="l">리포트 <span class="go">→</span></div></button>
      <button class="stat" data-go="strategy"><div class="v">${b.daily||0}</div><div class="l">데일리</div></button>
      <button class="stat" data-go="strategy"><div class="v">${b.weekly||0}</div><div class="l">위클리</div></button>
      <button class="stat" data-go="stocks"><div class="v">${(D.stocks||[]).length}</div><div class="l">종목 <span class="go">→</span></div></button>
      <button class="stat" data-go="sectors"><div class="v">${(D.sectors||[]).length}</div><div class="l">섹터 <span class="go">→</span></div></button>
      <button class="stat" data-go="glossary"><div class="v">${(((D.build&&D.build.counts)||{}).glossary) ?? (D.glossary||[]).length}</div><div class="l">용어 <span class="go">→</span></div></button>
      <button class="stat" data-go="analytics"><div class="v">📊</div><div class="l">분석 <span class="go">→</span></div></button>
    </div>
    <div id="watchHome"></div>
    <div id="watchDigest"></div>
    ${calendarCard()}
    ${(D.events||[]).length?`<div class="card">
      <div class="sec-title" style="margin:0 0 4px;font-size:17px">📅 최근 포착된 일정·이벤트 <span class="count-badge">${(D.events||[]).length}</span></div>
      <div class="sec-sub">리포트에서 추출한 실적·정책·수급 이벤트 — 최근 포착순</div>
      <div class="evscroll">${eventCards()}</div>
    </div>`:''}
    <div class="card">
      <div class="sec-title" style="margin:0 0 4px;font-size:17px">📉 지수 추이</div>
      <div class="sec-sub">KOSPI · KOSDAQ · 나스닥 — 일별 종가 · 독립 3분할 · ${(b.index_source==='yfinance')?'야후 파이낸스 연동(정확·무오차)':'리포트 추출값'}</div>
      <div class="idx-grid">
        <div class="idx-cell"><div class="idx-h"><i style="background:#dc2626"></i>KOSPI</div><div class="idx-chart"><canvas id="cKOSPI"></canvas></div></div>
        <div class="idx-cell"><div class="idx-h"><i style="background:#2563eb"></i>KOSDAQ</div><div class="idx-chart"><canvas id="cKOSDAQ"></canvas></div></div>
        <div class="idx-cell"><div class="idx-h"><i style="background:#7c3aed"></i>나스닥</div><div class="idx-chart"><canvas id="cNAS"></canvas></div></div>
      </div>
    </div>
    <div class="card">
      <div class="sec-title" style="margin:0 0 4px;font-size:17px">🧭 지금 살아있는 전략</div>
      <div class="sec-sub">최신 스탠스 · 반복 강화된 원칙 · 프벤져스 코어 섹터</div>
      <div class="now-strat">
        <div class="q">“${esc((latest.quote||latest.report_quote||'').slice(0,160))}”</div>
        <cite>— ${esc(latest.name||'프벤져스')}, ${esc(fmtDate(latest.date))} · ${esc(latest.headline||'')}</cite>
      </div>
      <div style="margin-top:14px">
        ${topPrin.map(p=>`<span class="chip" data-go="strategy">${p.icon} ${esc(p.principle.split(' — ')[0])} <span class="n">${p.count}</span></span>`).join('')}
      </div>
      <div class="core-head">🎯 프벤져스 코어 섹터 TOP 5 <span style="font-weight:400;color:var(--text-4)">· 최근 1개월 기준</span></div>
      <div class="core-grid">
      ${coreSectors.map((x,i)=>{const s=x.s,w=x.why; const note=(w.note||''); const short=note.length>200?note.slice(0,198)+'…':note; const chips=(s.stocks||[]).slice(0,4).map(n=>`<span class="core-chip" data-stock="${esc(n)}">${esc(n)}</span>`).join(''); const repBadge=(s.rep||0)>0?`<span class="rep-badge">👑 대표님 강조 ${s.rep}</span>`:''; return `
        <div class="core-sec">
          <div class="core-top"><span class="core-rank">${i+1}</span><span class="core-name">${esc(s.theme)}</span><span class="count-badge">${s.count}회</span>${repBadge}</div>
          <div class="core-why"><span class="lbl">근거</span> ${esc(short)}</div>
          <div class="core-meta">${esc(fmtDate(w.date))} 기준 ${srcLink(w.id)} ${chips}</div>
        </div>`;}).join('') || '<div style="font-size:12px;color:var(--text-4);margin-top:8px">근거 있는 섹터 데이터가 아직 없습니다.</div>'}
      </div>
    </div>
    <div class="card">
      <div class="sec-title" style="margin:0 0 4px;font-size:17px">🔥 최다 등장 섹터·종목</div>
      <div class="sec-sub">${RECENT_LABEL} 빈도 상위 — 클릭하면 해당 탭으로</div>
      <div style="margin-bottom:6px;font-size:12px;color:var(--text-3)">섹터·테마</div>
      <div>${topSectors.map(s=>`<span class="chip" data-go="sectors" data-sector="${esc(s.theme)}">${esc(s.theme)} <span class="n">${s.count}</span></span>`).join('')}</div>
      <div style="margin:12px 0 6px;font-size:12px;color:var(--text-3)">종목</div>
      <div>${topStocks.map(s=>`<span class="chip" data-go="stocks" data-stock="${esc(s.name)}">${esc(s.name)} <span class="n">${s.count}</span></span>`).join('')}</div>
    </div>`;
  drawTrend(); renderWatchHome(); renderDigest();
  const _cw=$('#calWrap'); if(_cw)_cw.addEventListener('click',e=>{const i=e.target.closest('.cal-on'); if(i)openReport(i.dataset.rid);});
}
/* ── 오늘 달라진 것 (C5) — 데이터 없으면 카드 자체가 없다 ── */
/* 목표가 표시 — '800000원' 대신 '800,000원'. 값이 숫자가 아니면 그대로 둔다. */
function wnTarget(value, unit){
  const n = Number(String(value||'').replace(/,/g,''));
  return (Number.isFinite(n) && String(value||'').trim() !== '' ? n.toLocaleString('ko-KR') : (value||'')) + (unit||'');
}
function whatsNewCard(){
  const w=D.whats_new; if(!w) return '';
  const rows=[];
  if((w.new_stocks||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">신규 등장</span>${w.new_stocks.slice(0,8).map(x=>`<span class="chip" data-stock="${esc(x.name)}">${esc(x.name)} <span class="n">${esc(x.count)}</span></span>`).join('')}</div>`);
  if((w.surging||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">언급 급증</span>${w.surging.slice(0,6).map(x=>`<span class="chip" data-stock="${esc(x.name)}">${esc(x.name)} <span class="n">${esc(x.prev)}→${esc(x.recent)}</span></span>`).join('')}</div>`);
  if((w.new_calls||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">새 콜</span>${verifyOn()?`<span class="chip" data-go="verify">${w.new_calls.length}건 · 검증 탭 →</span>`:`<span class="chip">${w.new_calls.length}건</span>`}${w.new_calls.slice(0,4).map(c=>`<span class="chip" data-stock="${esc(c.stock)}">${esc(c.stock)} <span class="n">${c.stance==='bullish'?'강세':'약세'}${c.date?' · '+esc(fmtDate(c.date)):''}</span></span>`).join('')}</div>`);
  if((w.new_targets||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">새 목표가</span>${w.new_targets.slice(0,6).map(t=>`<span class="chip" data-stock="${esc(t.stock)}">${esc(t.stock)} <span class="n">${esc(wnTarget(t.value,t.unit))}${t.date?' · '+esc(fmtDate(t.date)):''}</span></span>`).join('')}</div>`);
  if((w.new_reports||[]).length) rows.push(`<div class="wn-row"><span class="wn-k">새 리포트</span>${w.new_reports.slice(0,4).map(id=>`<span class="chip" data-report="${esc(id)}">${esc(fmtDate(id))}</span>`).join('')}</div>`);
  if(!rows.length) return '';
  return `<div class="card" id="whatsNew" style="border-color:var(--gold-border)">
    <div class="sec-title" style="margin:0 0 4px;font-size:17px">🆕 오늘 달라진 것</div>
    <div class="sec-sub">${esc(fmtDate(w.since))} 빌드 이후 변화 · <a class="src" href="feed.json">feed.json↗</a></div>${rows.join('')}</div>`;
}
/* ── AI 데일리 3줄 (C6) ── */
function aiDailyLines(){
  const d=D.ai_digest&&D.ai_digest.daily; if(!d||!(d.lines||[]).length) return '';
  return `<div class="brf-ai"><span class="brf-ai-k">🤖 AI 3줄</span>${d.lines.slice(0,3).map(l=>`<div>${esc(l)}</div>`).join('')}</div>`;
}
/* ── AI 위클리 다이제스트 (AlphaSense Smart Summaries 벤치마크) ── */
function aiDigestCard(){
  const w=D.ai_digest, a=w&&w.digest; if(!a) return '';
  const th=(a.themes||[]).map(t=>`<div class="aid-item"><b>${esc(t.name||'')}</b><span>${esc(t.note||'')}</span></div>`).join('');
  const stx=(a.stocks||[]).filter(n=>STOCK_BY_NAME[n]).map(n=>`<span class="tag" data-stock="${esc(n)}">${esc(n)}</span>`).join('');
  const rk=(a.risks||[]).map(r=>`<li>${esc(r)}</li>`).join('');
  return `<div class="card aid">
    <div class="sec-title" style="margin:0 0 4px;font-size:17px">🤖 AI 위클리 다이제스트</div>
    <div class="sec-sub">최근 7일 리포트를 AI가 요약 · ${esc(w.generated||'')} 생성 · 투자 판단의 참고용</div>
    ${a.title?`<div class="aid-title">"${esc(a.title)}"</div>`:''}
    <div class="aid-sum">${esc(a.summary||'')}</div>
    ${th?`<div class="aid-grid">${th}</div>`:''}
    ${stx?`<div style="margin-top:12px"><div style="font-size:11.5px;color:var(--text-3);margin-bottom:4px">주목 종목</div>${stx}</div>`:''}
    ${rk?`<div style="margin-top:12px"><div style="font-size:11.5px;color:var(--text-3);margin-bottom:4px">리스크 체크</div><ul class="aid-risks">${rk}</ul></div>`:''}
  </div>`;
}
/* ── 리포트 캘린더 (Logseq 데일리노트 벤치마크) ── */
function calendarCard(){
  const reps=(D.reports||[]).filter(r=>r.sort_date&&r.sort_date<='9999');
  const from=dnum((D.build&&D.build.from)||''), to=TO_DAY;
  if(!reps.length||from==null) return '';
  const byDay={};
  reps.forEach(r=>{const k=r.sort_date; if(!byDay[k]||r.type==='daily')byDay[k]=r;});
  const sd=new Date(from*864e5); let start=from-((sd.getUTCDay()+6)%7);
  const weeks=Math.ceil((to-start+1)/7);
  let cols='';
  for(let w=0;w<weeks;w++){
    let cells='';
    for(let d=0;d<7;d++){
      const day=start+w*7+d;
      if(day>to){cells+='<i></i>';continue;}
      const ds=new Date(day*864e5).toISOString().slice(0,10);
      const r=byDay[ds];
      cells+=r?`<i class="cal-on ${r.type==='weekly'?'cal-w':''}" data-rid="${esc(r.id)}" title="${esc(fmtDate(ds))} · ${esc(r.headline||r.id)}"></i>`
             :`<i title="${esc(fmtDate(ds))}"></i>`;
    }
    cols+=`<div class="cal-col">${cells}</div>`;
  }
  return `<div class="card"><div class="sec-title" style="margin:0 0 4px;font-size:17px">🗓 리포트 캘린더</div>
    <div class="sec-sub">발행 히트맵 — 칸을 누르면 해당 리포트 · <span style="color:var(--gold)">■</span> 데일리 <span style="color:var(--purple)">■</span> 위클리</div>
    <div class="cal-wrap" id="calWrap">${cols}</div></div>`;
}
/* ── 워치리스트 다이제스트 (Koyfin watchlist analytics 벤치마크) ── */
let DIGEST_CACHE=null;
function renderDigest(){
  const host=$('#watchDigest'); if(!host) return;
  if(DIGEST_CACHE!==null){host.innerHTML=DIGEST_CACHE;return;}
  let last=null; try{last=localStorage.getItem('fu-last-seen');}catch(e){}
  const to=(D.build&&D.build.to)||'';
  try{localStorage.setItem('fu-last-seen',to);}catch(e){}
  const L=dnum(last);
  if(L==null||!WL.size||last>=to){DIGEST_CACHE='';host.innerHTML='';return;}
  const items=[];
  WL.forEach(k=>{const i=k.indexOf(':'),kind=k.slice(0,i),name=k.slice(i+1);
    const obj=kind==='stock'?STOCK_BY_NAME[name]:(D.sectors||[]).find(s=>s.theme===name);
    if(!obj)return;
    const fresh=(obj.mentions||[]).filter(m=>{const x=dnum(m.date);return x!=null&&x>L;});
    if(fresh.length)items.push({kind,name,n:fresh.length,m:fresh[fresh.length-1]});});
  if(!items.length){DIGEST_CACHE='';host.innerHTML='';return;}
  items.sort((a,b)=>b.n-a.n);
  DIGEST_CACHE=`<div class="card" style="border-color:var(--gold-border)">
    <div class="sec-title" style="margin:0 0 4px;font-size:17px">🔔 워치리스트 새 소식 <span class="count-badge">${items.length}</span></div>
    <div class="sec-sub">지난 방문(${esc(fmtDate(last))}) 이후 관심 항목의 새 언급</div>
    ${items.map(it=>`<div class="sr-row"><span class="sr-name" ${it.kind==='stock'?`data-stock="${esc(it.name)}"`:`data-go="sectors" data-sector="${esc(it.name)}"`}>${it.kind==='sector'?'🧩 ':''}${esc(it.name)}</span><span class="sr-total">새 언급 ${it.n}건</span><span style="font-size:12px;color:var(--text-3)">${esc(it.m.label||it.m.name||'')} · ${esc(fmtDate(it.m.date))}</span></div>`).join('')}
  </div>`;
  host.innerHTML=DIGEST_CACHE;
}
function drawTrend(){
  const S=D.series||{};
  miniChart('cKOSPI', S['코스피'], '#dc2626');
  miniChart('cKOSDAQ', S['코스닥'], '#2563eb');
  miniChart('cNAS', S['나스닥'], '#7c3aed');
}
function miniChart(id, data, color){
  const el=document.getElementById(id); if(!el) return;
  if(!window.Chart || !data || data.length<2){
    const wrap=el.closest('.idx-chart');
    const last=(data&&data.length)?data[data.length-1].value.toLocaleString():null;
    if(wrap) wrap.innerHTML=`<div class="empty" style="padding:28px 8px;font-size:12px">데이터 부족<br><span style="font-size:10.5px;color:var(--text-4)">${last?('최근값 '+last):'리포트에 종가 미기재일 多'}</span></div>`;
    return;
  }
  const _cs=getComputedStyle(document.documentElement);
  const _grid=_cs.getPropertyValue('--grid').trim()||'#f0ece5';
  const _tx=_cs.getPropertyValue('--text-3').trim()||'#8a847a';
  const _ch=new Chart(el,{type:'line',
    data:{labels:data.map(p=>fmtDate(p.date)),datasets:[{data:data.map(p=>p.value),borderColor:color,backgroundColor:color+'22',tension:.3,fill:true,pointRadius:2,borderWidth:2}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
      scales:{y:{grid:{color:_grid},ticks:{font:{family:'JetBrains Mono',size:9},color:color}},
              x:{grid:{display:false},ticks:{font:{family:'JetBrains Mono',size:9},color:_tx,maxRotation:0,autoSkip:true,maxTicksLimit:5}}}}});
  (window.__charts=window.__charts||[]).push(_ch);
}

