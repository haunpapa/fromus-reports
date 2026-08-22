const D = window.DATA || {};
const $ = (s,r=document)=>r.querySelector(s);
const $$ = (s,r=document)=>[...r.querySelectorAll(s)];
const esc = s => (s==null?'':(''+s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// id → 원문 파일 매핑
const FILE = {};
(D.reports||[]).forEach(r=>{ if(r.id&&r.file) FILE[r.id]=r.file; });
const srcLink = (id,q) => (id&&FILE[id]) ? `<a class="src" href="${esc(FILE[id])}" data-report="${esc(id)}"${q?` data-q="${esc(q)}"`:''}>원문↗</a>` : '';
const fmtDate = d => !d?'' : (/^\d{4}-W/.test(d) ? d.replace('-',' ') : (d.length>=10? d.slice(5).replace('-','/'):d));
const RECENT_LABEL = (()=>{const rf=(D.build&&D.build.recent_from)||''; return rf? ('최근 1개월 · '+fmtDate(rf)+'~ 기준 · 언급순') : '최근 1개월 · 언급순';})();
// 섹터의 '근거' = note 있는 최신 멘션
function sectorWhy(s){const ms=(s.mentions||[]);
  for(let i=ms.length-1;i>=0;i--){const n=ms[i].note||'';if(n.length>12&&(n.includes('대표님')||n.includes('이혜나')))return ms[i];}  // 대표님 언급 근거 우선
  for(let i=ms.length-1;i>=0;i--){if(ms[i].note&&ms[i].note.length>12)return ms[i];}
  return ms.length?ms[ms.length-1]:null;}


/* ── KB 매니페스트 · 청크 로더 (스펙 C1/C2) ──
   D 는 앱 상태 컨테이너다 — 청크가 도착하면 해당 키만 채운다. */
const KB = (typeof window.KB_URL === 'string') ? {core: window.KB_URL} : (window.KB_URL || {});
const CHUNKS = {};
function applyChunk(name, obj){
  if(name==='search') D.search = obj || [];
  else if(name==='glossary') D.glossary = obj || [];
  else if(name==='chat') D.chat = Object.assign({}, D.chat || {}, obj || {});
  else if(name==='stockchat'){ (D.stocks||[]).forEach(s=>{ if(obj && obj[s.name]) s.chat = obj[s.name]; }); }
}
function loadChunk(name){
  if(!KB[name]) return Promise.resolve(null);           // 매니페스트에 없음(구 빌드·빈 청크) → 조용히 통과
  if(!CHUNKS[name]) CHUNKS[name] = fetch(KB[name])
    .then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(obj=>{ applyChunk(name,obj); return obj; })
    .catch(e=>{ delete CHUNKS[name]; throw e; });        // 실패는 메모이즈하지 않는다 — 재시도 가능
  return CHUNKS[name];
}
function chunkFailHtml(name){
  return `<div class="empty">데이터를 불러오지 못했습니다. <button type="button" class="cmp-add" data-chunk-retry="${esc(name)}">다시 시도</button></div>`;
}
const safeHref = u => /^https?:\/\//i.test(u||'') ? u : '#';   // javascript: 등 차단 (Q4)
