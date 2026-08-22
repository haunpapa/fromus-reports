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

