/* 简单 Service Worker：缓存静态资源，支持离线查看 */
const CACHE = 'couple-diary-v4';
const STATIC_ASSETS = ['/', '/index.html', '/manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('fetch', (e) => {
  if (e.request.url.includes('/api/') || e.request.url.includes('/uploads/')) {
    return;
  }
  const url = new URL(e.request.url);
  const isHtml = e.request.mode === 'navigate' || url.pathname === '/' || url.pathname.endsWith('.html');
  const isVersionedStatic = url.searchParams.has('v');

  // 登录页与带版本号的静态资源优先走网络，避免不同域名下旧缓存样式不一致。
  if (isHtml || isVersionedStatic) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request).then((r) => r || caches.match('/index.html')))
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request))
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
