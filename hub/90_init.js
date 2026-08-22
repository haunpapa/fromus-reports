/* ───────── INIT ───────── */
renderHome();renderSectors();renderStocks();renderAnalytics();renderStrategy();renderGlossary();renderGraph();renderChatView();renderVerify();
/* 빌드 시각·데이터 신선도 배지 (조용한 폴백 가시화) */
(function(){
  const el = document.getElementById('fu-status'); if(!el) return;
  const b = D.build || {};
  const warns = [];
  if (b.index_source === 'report') warns.push('지수 시세: 리포트 추출값 대체(yfinance 실패)');
  if (b.market_momentum && b.market_momentum.enabled === false) warns.push('시장 모멘텀: 비활성(' + (b.market_momentum.reason||'') + ')');
  if (b.chat_merge_error) warns.push('채팅 병합 실패: ' + b.chat_merge_error);
  el.innerHTML = '<span style="font-size:11px;color:var(--text-4)">빌드 ' + esc(b.generated||'?') + ' KST</span>' +
    (warns.length ? '<div style="font-size:11px;color:#b45309;margin-top:4px">⚠ ' + warns.map(esc).join(' · ') + '</div>' : '');
})();
/* PWA 서비스워커 등록 (http/https에서만) — 앱 블록은 load 이후 실행되므로 즉시 등록 */
if('serviceWorker' in navigator && /^https?:$/.test(location.protocol)){
  navigator.serviceWorker.register('./sw.js').catch(()=>{});
}
bootV4Enhancements();
tabFromHash();