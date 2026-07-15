// Minimal service worker: makes the app installable + serves a cached app shell
// when offline. API calls are always network-first (never cached) so trading
// data is never stale.
//
// IMPORTANT: the HTML shell (index.html / navigations) is NETWORK-FIRST so a new
// deploy is picked up immediately — a cache-first shell would keep serving the old
// index.html (and thus the old hashed JS bundle) against a new API and crash. Only
// hashed, immutable build assets are cache-first. Bump CACHE on breaking SW changes.
const CACHE = 'smarttrader-shell-v2';
const SHELL = ['/index.html', '/icon.svg', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Never cache API/socket traffic.
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api') || url.pathname.startsWith('/socket.io')) {
    return;
  }

  // Navigations + the HTML shell: NETWORK-FIRST so a deploy is seen right away.
  // The fresh index.html references the new hashed bundles; fall back to cache offline.
  const isShell =
    e.request.mode === 'navigate' ||
    url.pathname === '/' ||
    url.pathname === '/index.html';
  if (isShell) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put('/index.html', copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match('/index.html')),
    );
    return;
  }

  // Hashed, immutable build assets: cache-first (names change per build → no staleness).
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match('/index.html'))),
  );
});
