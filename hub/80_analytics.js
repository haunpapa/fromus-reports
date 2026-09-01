/* ───────── ANALYTICS (분석) ───────── */
function anWeekCols(){
  const from=dnum((D.build&&D.build.from)||''), to=TO_DAY;
  if(from==null) return [];
  const n=Math.max(1,Math.ceil((to-from+1)/7));
  const cols=[];
  for(let i=0;i<n;i++){const d=new Date((from+i*7)*864e5);cols.push((d.getUTCMonth()+1)+'/'+d.getUTCDate());}
  return cols;
}
function renderAnalytics(){
  const el=$('#view-analytics'); if(!el) return;
  const cols=anWeekCols();
  const from=dnum((D.build&&D.build.from)||'');
  /* 1) 섹터 로테이션 히트맵 */
  const secs=(D.sectors||[]).slice(0,12);
  const heat=secs.map(s=>{
    const row=new Array(cols.length).fill(0);
    (s.mentions||[]).forEach(m=>{const x=dnum(m.date); if(x==null||from==null)return; let wi=Math.floor((x-from)/7); if(wi<0)wi=0; if(wi>=cols.length)wi=cols.length-1; row[wi]++;});
    return {theme:s.theme,row};
  });
  const hmMax=Math.max(1,...heat.flatMap(h=>h.row));
  const hmRows=heat.map(h=>`<tr><th class="rowh" data-go="sectors" data-sector="${esc(h.theme)}" title="${esc(h.theme)} — 클릭하면 섹터 탭으로">${esc(h.theme)}</th>${h.row.map((v,i)=>{
    const lv=v===0?'':(v>=hmMax*0.66?'c3':v>=hmMax*0.33?'c2':'c1');
    return `<td class="cell ${lv}" title="${esc(h.theme)} · ${cols[i]} 주간 · ${v}회 언급">${v||''}</td>`;}).join('')}</tr>`).join('');
  /* 2) 언급 모멘텀 보드 */
  const buckets={'mo-hot':[],'mo-warm':[],'mo-cool':[]};
  (D.stocks||[]).forEach(s=>{ if((s.count||0)<2)return; const m=mentionMomentum(s.mentions); if(m&&buckets[m.cls]) buckets[m.cls].push({s,m});});
  Object.values(buckets).forEach(arr=>arr.sort((a,b)=>(b.s.count||0)-(a.s.count||0)));
  const moCol=(key,head)=>{const items=buckets[key].slice(0,10);
    return `<div class="mo-col"><h4>${head} <span class="count-badge">${buckets[key].length}</span></h4>${
      items.map(x=>`<div class="mo-item" data-stock="${esc(x.s.name)}"><span>${esc(x.s.name)} <span style="color:var(--text-4);font-size:11px">${x.s.count}회</span></span><span class="r">${esc(x.m.reason)}</span></div>`).join('')||'<div style="font-size:12px;color:var(--text-4)">해당 없음</div>'}</div>`;};
  /* 3) 수급 레이더 */
  const GROUPS=['외국인','기관','연기금','투신','사모펀드'];
  const acc={};
  (D.supply_days||[]).forEach(d=>{
    const grp=GROUPS.find(g=>(d.who||'').includes(g))||'기타';
    (d.stocks||[]).forEach(raw=>{
      const nm=gClean(raw); if(!nm||nm.length<2)return;
      const A=acc[nm]=acc[nm]||{name:nm,total:0,by:{},last:''};
      A.total++; A.by[grp]=(A.by[grp]||0)+1; if((d.date||'')>A.last)A.last=d.date;
    });
  });
  const radar=Object.values(acc).filter(a=>a.total>=2).sort((a,b)=>b.total-a.total||a.name.localeCompare(b.name)).slice(0,15);
  const srRows=radar.map((a,i)=>`<div class="sr-row"><span class="sr-rank">${i+1}</span><span class="sr-name" data-stock="${esc(a.name)}">${esc(a.name)}</span><span class="sr-total">${a.total}회</span><span class="sr-tags">${GROUPS.filter(g=>a.by[g]).map(g=>`<span class="sr-tag">${g} <b>${a.by[g]}</b></span>`).join('')}</span><span class="sr-last">최근 ${esc(fmtDate(a.last))}</span></div>`).join('');
  el.innerHTML=`
    <div class="sec-title">📊 분석 대시보드</div>
    <div class="sec-sub">리포트 언급 데이터 기반 자동 집계 · ${esc((D.build&&D.build.recent_from)?fmtDate(D.build.recent_from)+'~ 기준':'')}</div>
    <div class="an-card">
      <div class="an-title">🔄 섹터 로테이션 히트맵</div>
      <div class="an-sub">주차별(가로축) 테마 언급 강도 — 진할수록 그 주에 집중 언급. 테마명을 누르면 섹터 탭으로</div>
      <div class="hm-wrap"><table class="hm"><thead><tr><th></th>${cols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${hmRows}</tbody></table></div>
    </div>
    <div class="an-card">
      <div class="an-title">⚡ 언급 모멘텀 보드</div>
      <div class="an-sub">최근 14일 vs 직전 14일 언급 빈도 비교 — 종목을 누르면 상세 보기</div>
      <div class="mo-cols">${moCol('mo-hot','🔥 가열')}${moCol('mo-warm','↗ 상승')}${moCol('mo-cool','❄ 냉각')}</div>
    </div>
    <div class="an-card">
      <div class="an-title">🧲 수급 레이더</div>
      <div class="an-sub">외국인·기관·연기금·투신·사모펀드 순매수 TOP 리스트 등장 횟수 누적 — 반복 등장 = 꾸준히 담기는 종목 (2회 이상만 표시)</div>
      ${srRows||'<div class="empty">수급 데이터가 부족합니다.</div>'}
    </div>
    <div class="an-card">
      <div class="an-title">🌡 시장 심리(센티멘트) 추이</div>
      <div class="an-sub">리포트 텍스트의 긍정/부정 키워드 비율 — +100 강한 낙관 · −100 강한 비관 · 막대를 누르면 해당 리포트</div>
      <div class="idx-chart" id="cSent" style="height:210px"></div>
    </div>`;
  drawSentiment();
}
/* 인라인 SVG 센티멘트 막대 (C3 — Chart.js 대체). 막대 클릭→리포트, 호버 정보는 <title> 네이티브 툴팁.
   CSS 변수 색을 그리는 시점에 굽는다 — 테마 전환 시 setTheme 가 재호출해 색을 갱신한다. */
function drawSentiment(){
  const wrap=document.getElementById('cSent'); if(!wrap)return;   // .idx-chart 랩 자체 — 재그리기 가능
  const S=(D.sentiment||[]);
  if(S.length<2){wrap.innerHTML='<div class="empty">센티멘트 데이터가 없습니다 — build_hub.py 재실행 필요</div>';return;}
  const cs=getComputedStyle(document.documentElement);
  const G=cs.getPropertyValue('--green').trim()||'#247a3d', R=cs.getPropertyValue('--red').trim()||'#c2402f',
        GD=cs.getPropertyValue('--gold').trim()||'#9a7508', GRID=cs.getPropertyValue('--grid').trim()||'#ece6d7';
  const W=640, H=210, P=18, mid=H/2;
  const bw=Math.max(2,(W-2*P)/S.length-2);
  const bars=S.map((p,i)=>{
    const c=p.score>=15?G:p.score<=-15?R:GD;
    const h=Math.abs(p.score)/100*(H/2-P);
    const x=P+(W-2*P)*i/S.length, y=p.score>=0?mid-h:mid;
    return `<rect class="fu-bar" data-i="${i}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1,h).toFixed(1)}" rx="1.5" fill="${c}" style="cursor:pointer">
      <title>${fmtDate(p.date)} · ${p.score}점${p.headline?(' · '+esc(p.headline)):''} (긍정 ${p.pos} · 부정 ${p.neg})</title></rect>`;
  }).join('');
  wrap.innerHTML=`<svg class="fu-bars" viewBox="0 0 ${W} ${H}" role="img" aria-label="센티멘트 추이">
    <line x1="${P}" y1="${mid}" x2="${W-P}" y2="${mid}" stroke="${GRID}" stroke-width="1"/>
    ${bars}</svg>`;
  wrap.querySelector('svg').addEventListener('click', e=>{
    const r=e.target.closest('.fu-bar'); if(r) openReport(S[+r.dataset.i].id);
  });
}

