/**
 * Mobile offline outbox — queues field items; sync only clears after successful server process.
 */
(function (global) {
  'use strict';
  const DB_NAME = 'casepm-offline';
  const STORE = 'outbox';

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function clientId() {
    return `c-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  }

  async function enqueue(item) {
    const db = await openDb();
    const payload = { ...item, client_id: item.client_id || clientId(), at: Date.now() };
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).add(payload);
      tx.oncomplete = () => resolve(payload);
      tx.onerror = () => reject(tx.error);
    });
  }

  async function drainToServer() {
    const db = await openDb();
    const items = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
    if (!items.length) return { synced: 0 };
    const syncResp = await fetch('/api/mobile/offline/sync', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    });
    if (!syncResp.ok) throw new Error('offline sync failed');
    const procResp = await fetch('/api/mobile/offline/process', { method: 'POST', credentials: 'same-origin', body: '{}' });
    const proc = await procResp.json().catch(() => ({}));
    if (!procResp.ok) throw new Error(proc.error || 'offline process failed');
    const remaining = proc.remaining ?? 0;
    if (remaining === 0) {
      const clearTx = db.transaction(STORE, 'readwrite');
      clearTx.objectStore(STORE).clear();
    }
    return { synced: items.length, remaining, processed: proc.processed };
  }

  global.CasePMOfflineOutbox = { enqueue, drainToServer, clientId };

  global.addEventListener('online', () => { drainToServer().catch(() => {}); });
  if (global.navigator.onLine) drainToServer().catch(() => {});
})(typeof window !== 'undefined' ? window : globalThis);
