/* ───────── chip / tag navigation ───────── */
document.addEventListener('click',e=>{
  const stockTag=e.target.closest('[data-stock]');
  if(stockTag){
    showTab('stocks'); stockQuery=stockTag.dataset.stock; stockSort='count';
    renderStocks();
    try{history.replaceState(null,'','#stocks/'+encodeURIComponent(stockTag.dataset.stock));}catch(e){}
    const first=$('#stockList .strow-detail'); if(first) first.classList.add('open');
    return;
  }
  const go=e.target.closest('[data-go]');
  if(go){
    const target=go.dataset.go, sector=go.dataset.sector;
    showTab(target);
    if(target==='sectors' && sector){
      const card=$$('#view-sectors .scard').find(c=>c.querySelector('.scard-name')?.textContent===sector);
      if(card){ card.querySelector('.scard-detail').classList.add('open');
        setTimeout(()=>card.scrollIntoView({behavior:'smooth',block:'center'}),60); }
    }
  }
});

