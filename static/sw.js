/* Case PM — offline shell + web push */
const CACHE = 'casepm-v3';
const PRECACHE = ['/dashboard', '/daily-log'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) return;
  e.respondWith(
    fetch(e.request).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(e.request).then(r => r || caches.match('/dashboard')))
  );
});

self.addEventListener('push', (e) => {
  let data = { title: 'Case PM', body: 'New notification' };
  try { data = e.data ? e.data.json() : data; } catch (err) { /* use defaults */ }
  e.waitUntil(
    self.registration.showNotification(data.title || 'Case PM', {
      body: data.body || '',
      icon: '/static/manifest.json',
      data: data.link || '/',
    })
  );
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = e.notification.data || '/';
  e.waitUntil(clients.openWindow(url));
});
