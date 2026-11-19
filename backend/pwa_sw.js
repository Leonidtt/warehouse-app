/* PWA offline fallback. Do not cache API responses, login pages or user content. */
const CACHE_NAME = 'warehouse-beta-pwa-static-v1';
const OFFLINE = '/pwa/offline.html';
const PUBLIC_ASSETS = [OFFLINE, '/pwa/icon-180.png', '/pwa/icon-192.png', '/pwa/icon-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(PUBLIC_ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('warehouse-beta-pwa-') && key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.mode !== 'navigate' || request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname !== '/pwa/') return;
  event.respondWith(fetch(request, {cache:'no-store'}).catch(() => caches.match(OFFLINE)));
});
