/* Case PM — offline shell + web push (static assets only) */
const CACHE = 'casepm-v5';
const PRECACHE = ['/static/manifest.json'];

function isStaticAsset(url) {
  return url.pathname.startsWith('/static/');
}

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
  if (!isStaticAsset(url)) {
    e.respondWith(fetch(e.request));
    return;
  }
  e.respondWith(
    fetch(e.request).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(e.request))
  );
});

self.addEventListener('push', (e) => {
  let data = { title: 'Case PM', body: 'New notification' };
  try { data = e.data ? e.data.json() : data; } catch (err) { /* use defaults */ }
  let link = data.link || '/';
  try {
    const u = new URL(link, self.location.origin);
    if (u.origin !== self.location.origin) link = '/';
    else link = u.pathname + (u.search || '');
  } catch (_) {
    link = '/';
  }
  e.waitUntil(
    self.registration.showNotification(data.title || 'Case PM', {
      body: data.body || '',
      icon: '/static/manifest.json',
      data: link,
    })
  );
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  let url = e.notification.data || '/';
  try {
    const u = new URL(url, self.location.origin);
    if (u.origin !== self.location.origin) url = '/';
    else url = u.pathname + (u.search || '');
  } catch (_) {
    url = '/';
  }
  e.waitUntil(clients.openWindow(url));
});
