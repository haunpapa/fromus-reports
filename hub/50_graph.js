/* ═══════════ V3: 관계망 그래프 ═══════════ */
const SECTOR_BY_THEME={}; (D.sectors||[]).forEach(s=>SECTOR_BY_THEME[s.theme]=s);
const GPAL=['#dc2626','#2563eb','#16a34a','#7c3aed','#0891b2','#b8860b','#db2777','#ea580c','#0d9488','#4f46e5','#65a30d','#9333ea','#0284c7','#ca8a04','#e11d48','#059669','#a16207','#1d4ed8','#be123c','#15803d','#6d28d9','#0e7490','#c026d3','#0369a1','#b45309','#7e22ce','#047857','#9f1239'];
const GMAJOR_MIN=3, LEGEND_N=7;   // LEGEND_N: 범례 표시 + 상시 라벨 노출할 상위 섹터 수
let G=null, gAlpha=0, gRAF=null, gActive=false, gBuiltFilter=null;
let gView={k:1,tx:0,ty:0}, gHover=null, gDrag=null, gPan=null, gDirty=false;

function gClean(nm){return (''+nm).replace(/\s*[+\-]?\d[\d.,%]*\s*$/,'').trim()||nm;}
function buildGraph(filter){
  const sectors=(D.sectors||[]);
  const nodes=[], idx={}, links=[];
  // 종목간(co) 연결이 있는 종목 — major 필터에서 단일섹터 잔챙이라도 살림
  const coEdges = (D.chat && Array.isArray(D.chat.co_edges)) ? D.chat.co_edges : [];
  const coSet = new Set(); coEdges.forEach(e=>{coSet.add(gClean(e.a)); coSet.add(gClean(e.b));});
  sectors.forEach((s,i)=>{const id='S:'+s.theme;
    nodes.push({id,kind:'sector',name:s.theme,val:s.count||1,color:GPAL[i%GPAL.length],deg:0,ref:s,legend:i<LEGEND_N,
      x:Math.cos(i/sectors.length*6.283)*120,y:Math.sin(i/sectors.length*6.283)*120,vx:0,vy:0});
    idx[id]=nodes.length-1;});
  sectors.forEach((s,i)=>{const col=GPAL[i%GPAL.length], sIdx=idx['S:'+s.theme];
    (s.stocks||[]).forEach(raw=>{const nm=gClean(raw); const st=STOCK_BY_NAME[nm]||STOCK_BY_NAME[raw];
      const cnt=(st&&st.count)||1;
      if(filter==='major' && cnt<GMAJOR_MIN && !(st&&(st.sectors||[]).length>=2) && !coSet.has(nm)) return; // 주요: 언급 적고 단일섹터·종목간연결(co) 없으면 생략
      const id='K:'+nm;
      if(idx[id]==null){ nodes.push({id,kind:'stock',name:nm,val:cnt,color:col,deg:0,ref:st,
        x:(Math.random()-.5)*260,y:(Math.random()-.5)*260,vx:0,vy:0}); idx[id]=nodes.length-1; }
      links.push({s:sIdx,t:idx[id],kind:'sector'}); nodes[sIdx].deg++; nodes[idx[id]].deg++;
    });
  });
  // ── 채팅·뉴스 종목↔종목 엣지 (양쪽이 그래프 노드인 쌍만) ──
  coEdges.forEach(e=>{
    const ia=idx['K:'+gClean(e.a)], ib=idx['K:'+gClean(e.b)];
    if(ia==null||ib==null) return;            // chat_only·major필터 제외 종목 자연 스킵
    links.push({s:ia,t:ib,kind:'co',w:e.w}); nodes[ia].deg++; nodes[ib].deg++;
  });
  // major: 섹터 1개에만 매달리고 종목간(co) 연결 0인 잔가지(실연결 deg<=1 stock) 제거.
  // deg<=1 stock 은 반드시 co 링크가 없으므로(co 있으면 섹터+co=deg>=2) 제거해도 타 종목 연결 불변 → 1-pass 안전.
  if(filter==='major'){
    const drop=new Set(); nodes.forEach((n,i)=>{ if(n.kind==='stock' && n.deg<=1) drop.add(i); });
    if(drop.size){
      const keep=nodes.map((_,i)=>i).filter(i=>!drop.has(i)); const remap={}; keep.forEach((o,nw)=>remap[o]=nw);
      const N=keep.map(i=>nodes[i]); const L=links.filter(l=>!drop.has(l.s)&&!drop.has(l.t)).map(l=>({...l,s:remap[l.s],t:remap[l.t]}));
      N.forEach(n=>n.deg=0); L.forEach(l=>{N[l.s].deg++; N[l.t].deg++;}); const I={}; N.forEach((n,i)=>I[n.id]=i);
      return {nodes:N,links:L,idx:I};   // 섹터는 항상 유지(deg 0 이어도 표시)
    }
  }
  // 섹터는 항상 표시(고립 섹터도 유지).
  return {nodes,links,idx};
}
function gRadius(n){return n.kind==='sector' ? 7+Math.sqrt(n.val)*2.4 : 3+Math.sqrt(n.val)*1.5;}
function gTick(){
  const N=G.nodes, L=G.links, n=N.length;
  const REP=1500, SPRING=0.025, SLEN=64, GRAV=0.018, DAMP=0.84;
  // 척력 (O(n^2), ~수백 노드 OK)
  for(let i=0;i<n;i++){const a=N[i];
    for(let j=i+1;j<n;j++){const b=N[j];
      let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy||0.01; if(d2>90000)continue;
      const f=REP/d2*gAlpha; const d=Math.sqrt(d2); const fx=dx/d*f, fy=dy/d*f;
      a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
    }}
  // 인력(스프링)
  for(const e of L){const a=N[e.s], b=N[e.t];
    let dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||0.01;
    const f=(d-SLEN)*SPRING*gAlpha; const fx=dx/d*f, fy=dy/d*f;
    a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy;
  }
  // 중심 중력 + 적분
  for(const p of N){
    p.vx-=p.x*GRAV*gAlpha; p.vy-=p.y*GRAV*gAlpha;
    if(p===gDrag){p.x=p.fx; p.y=p.fy; p.vx=0; p.vy=0; continue;}
    p.vx*=DAMP; p.vy*=DAMP;
    p.vx=Math.max(-12,Math.min(12,p.vx)); p.vy=Math.max(-12,Math.min(12,p.vy));
    p.x+=p.vx; p.y+=p.vy;
  }
  if(gAlpha>0.02) gAlpha*=0.992;
}
function gFit(){
  const cv=$('#graphCanvas'); if(!cv)return; const W=cv.clientWidth,H=cv.clientHeight;
  let minX=1e9,maxX=-1e9,minY=1e9,maxY=-1e9;
  for(const p of G.nodes){minX=Math.min(minX,p.x);maxX=Math.max(maxX,p.x);minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y);}
  const gw=maxX-minX||1, gh=maxY-minY||1; const k=Math.min(W/(gw+120),H/(gh+120),1.6);
  gView.k=k; gView.tx=W/2-(minX+maxX)/2*k; gView.ty=H/2-(minY+maxY)/2*k;
}
function gNeighbors(node){const set=new Set();
  for(const e of G.links){ if(G.nodes[e.s]===node)set.add(G.nodes[e.t]); if(G.nodes[e.t]===node)set.add(G.nodes[e.s]); }
  return set;}
function gDraw(){
  const cv=$('#graphCanvas'); if(!cv)return; const ctx=cv.getContext('2d');
  const W=cv.width,H=cv.height,dpr=window.devicePixelRatio||1;
  ctx.setTransform(1,0,0,1,0,0); ctx.clearRect(0,0,W,H);
  ctx.setTransform(gView.k*dpr,0,0,gView.k*dpr,gView.tx*dpr,gView.ty*dpr);
  const cs=getComputedStyle(document.documentElement);
  const lineC=cs.getPropertyValue('--border').trim()||'#e4dfd6';
  const txC=cs.getPropertyValue('--text-2').trim()||'#4a4540';
  const bg=cs.getPropertyValue('--surface').trim()||'#fff';
  const nb = gHover?gNeighbors(gHover):null;
  // links
  for(const e of G.links){const a=G.nodes[e.s], b=G.nodes[e.t];
    const hot = gHover && (a===gHover||b===gHover);
    const isCo = e.kind==='co';
    ctx.setLineDash(isCo ? [4/gView.k, 3/gView.k] : []);
    ctx.strokeStyle = hot ? (a.kind==='sector'?a.color:b.color) : (isCo ? '#7c3aed' : lineC);
    ctx.globalAlpha = gHover ? (hot?0.85:0.12) : (isCo ? 0.40 : 0.5);
    ctx.lineWidth = (hot?1.6 : (isCo ? Math.min(0.6+(e.w||1)*0.22, 2.0) : 0.7))/gView.k;
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  }
  ctx.setLineDash([]); ctx.globalAlpha=1;   // 점선·알파 리셋(원본 L1496 globalAlpha=1 포함, 노드 루프 영향 방지)
  // nodes
  for(const p of G.nodes){const r=gRadius(p);
    const dim = gHover && p!==gHover && !(nb&&nb.has(p));
    ctx.globalAlpha = dim?0.22:1;
    ctx.beginPath(); ctx.arc(p.x,p.y,r,0,6.2832);
    ctx.fillStyle=p.color||'#9a8f7d'; ctx.fill();
    ctx.lineWidth=1.4/gView.k; ctx.strokeStyle=bg; ctx.stroke();
    if(p===gHover){ctx.lineWidth=2.4/gView.k; ctx.strokeStyle=p.color; ctx.stroke();}
    // stance 링 (종목 노드, 강세 녹/약세 빨강, 동률·무는 없음)
    if(p.kind==='stock' && p.ref && p.ref.chat){
      const st=p.ref.chat.stance||{};
      const ring = (st.bullish||0)>(st.bearish||0) ? '#16a34a' : ((st.bearish||0)>(st.bullish||0) ? '#dc2626' : null);
      if(ring){ ctx.beginPath(); ctx.arc(p.x,p.y,r+2.5/gView.k,0,6.2832); ctx.lineWidth=2/gView.k; ctx.strokeStyle=ring; ctx.stroke(); }
    }
  }
  // labels: 범례(상위 LEGEND_N) 섹터는 항상, 나머지 섹터·종목은 hover/이웃/확대 시
  ctx.globalAlpha=1; ctx.textAlign='center'; ctx.textBaseline='top'; ctx.fillStyle=txC;
  for(const p of G.nodes){const r=gRadius(p);
    const isLegend = p.kind==='sector' && p.legend;
    const showLbl = isLegend || p===gHover || (nb&&nb.has(p)) || gView.k>1.25;
    if(!showLbl) continue;
    if(gHover && !isLegend && p!==gHover && !(nb&&nb.has(p))) continue;   // 범례 섹터는 hover 중에도 라벨 유지
    ctx.font=`${(p.kind==='sector'?12:10)}px 'Noto Sans KR',sans-serif`;
    ctx.fillStyle = p.kind==='sector'?txC:cs.getPropertyValue('--text-3').trim();
    ctx.fillText(p.name, p.x, p.y+r+2);
  }
  ctx.setTransform(1,0,0,1,0,0);
}
function gLoop(){ if(!gActive)return; if(gAlpha>0.02){gTick(); gDraw();} else if(gDirty){gDraw(); gDirty=false;} gRAF=requestAnimationFrame(gLoop); }
function gSizeCanvas(){const cv=$('#graphCanvas'); if(!cv)return; const dpr=window.devicePixelRatio||1;
  cv.width=cv.clientWidth*dpr; cv.height=cv.clientHeight*dpr; }
function gScreenToWorld(mx,my){return {x:(mx-gView.tx)/gView.k, y:(my-gView.ty)/gView.k};}
function gPick(mx,my){const w=gScreenToWorld(mx,my); let best=null,bd=1e9;
  for(const p of G.nodes){const r=gRadius(p)+4/gView.k; const dx=p.x-w.x,dy=p.y-w.y,d=dx*dx+dy*dy;
    if(d<r*r && d<bd){bd=d;best=p;}} return best;}
function gNavigate(p){
  if(p.kind==='stock'){ showTab('stocks'); stockQuery=p.name; stockSort='count';
    if($('#stockq'))$('#stockq').value=p.name; renderStocks();
    const f=$('#stockList .strow-detail'); if(f)f.classList.add('open');
  } else { showTab('sectors');
    const card=$$('#view-sectors .scard').find(c=>c.querySelector('.scard-name')?.textContent===p.name);
    if(card){card.querySelector('.scard-detail').classList.add('open'); setTimeout(()=>card.scrollIntoView({behavior:'smooth',block:'center'}),60);} }
}
function gWireCanvas(){
  const cv=$('#graphCanvas'); if(!cv||cv.__wired)return; cv.__wired=true;
  const tip=$('#graphTip');
  cv.addEventListener('mousemove',e=>{const r=cv.getBoundingClientRect(); const mx=e.clientX-r.left,my=e.clientY-r.top; gDirty=true;
    if(gDrag){const w=gScreenToWorld(mx,my); gDrag.fx=w.x; gDrag.fy=w.y; gAlpha=Math.max(gAlpha,0.3); return;}
    if(gPan){gView.tx+=e.clientX-gPan.x; gView.ty+=e.clientY-gPan.y; gPan={x:e.clientX,y:e.clientY}; return;}
    const hit=gPick(mx,my); gHover=hit;
    if(hit){cv.style.cursor='pointer'; const c=hit.ref&&hit.ref.count!=null?hit.ref.count:hit.val;
      tip.innerHTML=`<div class="gt-name">${esc(hit.name)}</div><div class="gt-meta">${hit.kind==='sector'?'섹터':'종목'} · ${c}회 · 연결 ${hit.deg}</div>`;
      tip.style.left=(e.clientX+14)+'px'; tip.style.top=(e.clientY+14)+'px'; tip.classList.add('on');
    } else {cv.style.cursor='grab'; tip.classList.remove('on');}
  });
  cv.addEventListener('mousedown',e=>{const r=cv.getBoundingClientRect(); const hit=gPick(e.clientX-r.left,e.clientY-r.top);
    if(hit){gDrag=hit; const w=gScreenToWorld(e.clientX-r.left,e.clientY-r.top); gDrag.fx=w.x; gDrag.fy=w.y; gDrag.__moved=false;}
    else gPan={x:e.clientX,y:e.clientY};});
  window.addEventListener('mouseup',e=>{ if(gDrag){gDrag=null;} gPan=null; });
  cv.addEventListener('dblclick',e=>{const r=cv.getBoundingClientRect(); const hit=gPick(e.clientX-r.left,e.clientY-r.top); if(hit)gNavigate(hit);}); // 1클릭/드래그=위치조정, 더블클릭=이동
  cv.addEventListener('wheel',e=>{e.preventDefault(); const r=cv.getBoundingClientRect(); const mx=e.clientX-r.left,my=e.clientY-r.top;
    const f=e.deltaY<0?1.12:0.89; const nk=Math.max(0.3,Math.min(3.2,gView.k*f));
    gView.tx=mx-(mx-gView.tx)*(nk/gView.k); gView.ty=my-(my-gView.ty)*(nk/gView.k); gView.k=nk; gDirty=true;},{passive:false});
  cv.addEventListener('mouseleave',()=>{tip.classList.remove('on'); gHover=null; gDirty=true;});
}
function renderGraph(){
  $('#view-graph').innerHTML=`
    <div class="sec-title">🕸 종목·섹터 관계망 <span class="count-badge" id="graphCount"></span></div>
    <div class="sec-sub">섹터(큰 노드)와 종목(작은 노드)의 연결 지도 · 노드를 끌어 위치 조정, 더블클릭하면 해당 항목으로 이동 · 같은 종목이 여러 섹터에 걸치면 클러스터를 잇습니다</div>
    <div class="graph-wrap">
      <div class="graph-controls">
        <div class="seg" id="graphFilter">
          <button data-g="major" class="on">주요 종목</button>
          <button data-g="all">전체 종목</button>
        </div>
        <div class="seg"><button id="graphReset">⟳ 재배치</button></div>
      </div>
      <div class="graph-hint">스크롤 확대 · 빈 곳 드래그 이동 · 노드 더블클릭 열기</div>
      <canvas class="graph-canvas" id="graphCanvas"></canvas>
      <div class="graph-legend" id="graphLegend"></div>
    </div>`;
  $('#graphFilter').addEventListener('click',e=>{const b=e.target.closest('button'); if(!b)return;
    $$('#graphFilter button').forEach(x=>x.classList.toggle('on',x===b)); gStart(b.dataset.g,true);});
  $('#graphReset').addEventListener('click',()=>gStart(gBuiltFilter||'major',true));
}
function gStart(filter,force){
  filter=filter||'major';
  gSizeCanvas(); gWireCanvas();
  if(force || gBuiltFilter!==filter){
    gHover=null; gDrag=null; gPan=null;
    G=buildGraph(filter); gBuiltFilter=filter;
    for(let i=0;i<160;i++){gAlpha=Math.max(gAlpha,1);gTick();} // 워밍업(정적 안정화)
    gFit();
    const sc=$('#graphCount'); if(sc)sc.textContent=G.nodes.length+'노드';
    const lg=$('#graphLegend'); if(lg){const tops=(D.sectors||[]).slice(0,LEGEND_N);
      lg.innerHTML=tops.map((s,i)=>`<span class="glg"><i style="background:${GPAL[i%GPAL.length]}"></i>${esc(s.theme)}</span>`).join('')
        +`<span class="glg-sep"></span>`
        +`<span class="glg"><i class="glg-ring" style="border-color:#16a34a"></i>강세</span>`
        +`<span class="glg"><i class="glg-ring" style="border-color:#dc2626"></i>약세</span>`
        +`<span class="glg"><span class="glg-dash"></span>동시언급</span>`;}
  }
  gAlpha=0.9;
}
function graphSetActive(on){
  gActive=on;
  if(on){ gStart(gBuiltFilter||'major',!G); if(!gRAF)gLoop(); }
  else { if(gRAF){cancelAnimationFrame(gRAF); gRAF=null;} const t=$('#graphTip'); if(t)t.classList.remove('on'); }
}
window.addEventListener('resize',()=>{ if(gActive){gSizeCanvas(); gFit(); gAlpha=Math.max(gAlpha,0.2);} });

