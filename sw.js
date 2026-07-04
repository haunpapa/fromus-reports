/* From Us Knowledge Hub — Service Worker v2
   셸(html): stale-while-revalidate — 캐시 즉시 표시 + 백그라운드 갱신
   kb.<hash>.json: cache-first — 해시가 바뀌면 URL이 바뀌므로 영구 캐시 안전 (구 해시는 제거) */
const CACHE = 'fu-hub-v2';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['./hub.html'])).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || !e.request.url.startsWith(self.location.origin)) return;
  const path = new URL(e.request.url).pathname;

  // 불변 데이터 (해시 파일명) — cache-first + 구버전 해시 파일 정리
  if (/\/kb\.[0-9a-f]{6,}\.json$/.test(path)) {
    e.respondWith(
      caches.match(e.request).then(m => m || fetch(e.request).then(r => {
        if (r && r.ok) {
          const cp = r.clone();
          caches.open(CACHE).then(async c => {
            // 새 해시를 캐시하면서 다른 kb.*.json 항목은 삭제 (캐시 무한 누적 방지)
            const keys = await c.keys();
            await Promise.all(keys
              .filter(k => /\/kb\.[0-9a-f]{6,}\.json$/.test(new URL(k.url).pathname) && k.url !== e.request.url)
              .map(k => c.delete(k)));
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
