// ============================================================================
// SENPARMIS TECH ATTENDANCE TRACKER — SERVICE WORKER
// Offline-first attendance marking with background sync
// ============================================================================

const CACHE_NAME = 'attendance-v3';
const STATIC_ASSETS = [
  '/',
  '/static/css/app.css',
  '/static/css/mark.css',
  '/static/js/mark.js',
  '/manifest.json',
];

const CACHE_STRATEGIES = {
  // Network first, fallback to cache
  networkFirst: ['/mark', '/scan', '/records', '/students', '/lookup', '/dashboard'],
  // Cache first for static assets
  cacheFirst: ['/static/', '/manifest.json'],
};

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Skip non-GET requests
  if (event.request.method !== 'GET') return;

  // Skip cross-origin
  if (url.origin !== location.origin) return;

  // API routes - network only (don't cache POST/attendance saves)
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/save') || url.pathname.includes('/import')) {
    return;
  }

  // Determine strategy
  const isStatic = CACHE_STRATEGIES.cacheFirst.some(p => url.pathname.startsWith(p));
  const isNetworkFirst = CACHE_STRATEGIES.networkFirst.some(p => url.pathname.startsWith(p));

  if (isStatic) {
    event.respondWith(cacheFirst(event.request));
  } else if (isNetworkFirst || url.pathname === '/') {
    event.respondWith(networkFirst(event.request));
  }
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) return cached;

    // Return offline page for navigation requests
    if (request.mode === 'navigate') {
      return caches.match('/') || new Response('Offline', { status: 503 });
    }
    return new Response('Offline', { status: 503 });
  }
}

// Background Sync for attendance saves
self.addEventListener('sync', event => {
  if (event.tag === 'attendance-sync') {
    event.waitUntil(syncAttendance());
  }
});

async function syncAttendance() {
  const clients = await self.clients.matchAll();
  clients.forEach(client => client.postMessage({ type: 'sync-start' }));

  try {
    // Get pending attendance data from IndexedDB
    const pending = await getPendingAttendance();
    for (const item of pending) {
      await fetch(item.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item.data),
      });
      await deletePendingAttendance(item.id);
    }
    clients.forEach(client => client.postMessage({ type: 'sync-complete' }));
  } catch (e) {
    clients.forEach(client => client.postMessage({ type: 'sync-failed', error: e.message }));
  }
}

// IndexedDB helpers for offline queue
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('AttendanceDB', 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending')) {
        db.createObjectStore('pending', { keyPath: 'id', autoIncrement: true });
      }
    };
  });
}

function getPendingAttendance() {
  return openDB().then(db => new Promise((resolve, reject) => {
    const tx = db.transaction('pending', 'readonly');
    const store = tx.objectStore('pending');
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  }));
}

function deletePendingAttendance(id) {
  return openDB().then(db => new Promise((resolve, reject) => {
    const tx = db.transaction('pending', 'readwrite');
    const store = tx.objectStore('pending');
    const request = store.delete(id);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  }));
}

// Push notifications (future enhancement)
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/img/icon-192.png',
      badge: '/static/img/badge-72.png',
      tag: data.tag,
      data: data.url,
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.notification.data) {
    event.waitUntil(clients.openWindow(event.notification.data));
  }
});