/* From Us Knowledge Hub — Service Worker v5
   셸(html): stale-while-revalidate — 캐시 즉시 표시 + 백그라운드 갱신
   kb.<chunk>.<hash>.json: cache-first — 해시가 바뀌면 URL이 바뀌므로 영구 캐시 안전.
   청크별로 구 해시만 정리한다 (chat 청크를 받으면서 core 캐시를 지우면 안 된다).
   /reports/: 별도 캐시(fu-reports-v1) + FIFO 상한 — 리포트는 매일 늘므로 방치하면 무한 증식.
   v5 범프: v4 에 SWR 로 쌓인 레거시 /reports/ 잔류분(~7.7MB)을 activate 정리로 통째 회수. */
const CACHE = 'fu-hub-v5';
const REPORTS_CACHE = 'fu-reports-v1';
const REPORTS_MAX = 30;                       // FIFO 상한 — 리포트는 매일 늘므로 방치하면 무한 증식
const PRECACHE = ['./hub.html'];
// kb.core.<h>.json · kb.chat.<h>.json … | 구 형식 kb.<h>.json 도 인식(청크명 'legacy')
const KB_RE = /\/kb\.(?:([a-z]+)\.)?[0-9a-f]{6,}\.json$/;
// hub.app.<h>.js — 앱 JS 해시 파일. kb 청크와 동일한 cache-first + 구해시 정리(청크명 'app')
const APP_RE = /\/hub\.app\.[0-9a-f]{6,}\.js$/;

self.addEventListener('install', e => {
  // cache:'reload' — HTTP 캐시를 우회해 항상 네트워크의 최신 셸을 프리캐시
  e.waitUntil(caches.open(CACHE)
    .then(c => c.addAll(PRECACHE.map(u => new Request(u, {cache: 'reload'}))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(
      ks.filter(k => k !== CACHE && k !== REPORTS_CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function chunkOf(pathname) {
  const m = KB_RE.exec(pathname);
  if (m) return m[1] || 'legacy';
  return APP_RE.test(pathname) ? 'app' : null;   // 해시 앱 JS 도 청크 취급 — cache-first + 같은 청크 구해시만 삭제
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

  // 리포트 원문 — 별도 캐시(SWR) + 근사 FIFO 상한.
  // Cache API keys()는 삽입순 보장이 명시 스펙은 아니나 실구현이 삽입순 — 근사 FIFO로 충분.
  if (path.includes('/reports/')) {
    e.respondWith(
      caches.open(REPORTS_CACHE).then(c => c.match(e.request).then(cached => {
        const net = fetch(e.request).then(r => {
          if (r && r.ok) {
            const cp = r.clone();
            c.put(e.request, cp).then(async () => {
              const keys = await c.keys();
              for (const k of keys.slice(0, Math.max(0, keys.length - REPORTS_MAX))) await c.delete(k);
            });
          }
          return r;
        }).catch(() => cached);
        return cached || net;
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
