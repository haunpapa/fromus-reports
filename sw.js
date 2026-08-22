/* From Us Knowledge Hub — Service Worker v4
   셸(html): stale-while-revalidate — 캐시 즉시 표시 + 백그라운드 갱신
   kb.<chunk>.<hash>.json: cache-first — 해시가 바뀌면 URL이 바뀌므로 영구 캐시 안전.
   청크별로 구 해시만 정리한다 (chat 청크를 받으면서 core 캐시를 지우면 안 된다). */
const CACHE = 'fu-hub-v4';
const PRECACHE = ['./hub.html', './vendor/chart.umd.min.js'];
// kb.core.<h>.json · kb.chat.<h>.json … | 구 형식 kb.<h>.json 도 인식(청크명 'legacy')
const KB_RE = /\/kb\.(?:([a-z]+)\.)?[0-9a-f]{6,}\.json$/;

self.addEventListener('install', e => {
  // cache:'reload' — HTTP 캐시를 우회해 항상 네트워크의 최신 셸을 프리캐시
  e.waitUntil(caches.open(CACHE)
    .then(c => c.addAll(PRECACHE.map(u => new Request(u, {cache: 'reload'}))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function chunkOf(pathname) {
  const m = KB_RE.exec(pathname);
  return m ? (m[1] || 'legacy') : null;
}

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || !e.request.url.startsWith(self.location.origin)) return;
  const url = new URL(e.request.url);
  const path = url.pathname;

  // 탈출구: ?nosw= 가 붙은 요청은 가로채지 않고 네트워크로 직행 (version.json 확인·캐시버스터 재로드)
  if (url.searchParams.has('nosw')) return;

  const chunk = chunkOf(path);
  if (chunk) {
    e.respondWith(
      caches.match(e.request).then(m => m || fetch(e.request).then(r => {
        if (r && r.ok) {
          const cp = r.clone();
          caches.open(CACHE).then(async c => {
            const keys = await c.keys();
            await Promise.all(keys
              .filter(k => chunkOf(new URL(k.url).pathname) === chunk && k.url !== e.request.url)
              .map(k => c.delete(k)));                 // 같은 청크의 구 해시만 삭제
            c.put(e.request, cp);
          });
        }
        return r;
      }))
    );
    return;
  }

  // 나머지 (셸·아이콘 등) — stale-while-revalidate
  e.respondWith(
    caches.match(e.request, {ignoreSearch: true}).then(cached => {
      const net = fetch(e.request).then(r => {
        if (r && r.ok) { const cp = r.clone(); caches.open(CACHE).then(c => c.put(e.request, cp)); }
        return r;
      }).catch(() => cached || caches.match('./hub.html'));
      return cached || net;
    })
  );
});
