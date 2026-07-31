/**
 * Mobile offline outbox — queues daily log ids for server process when back online.
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

  async function enqueue(item) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).add({ ...item, at: Date.now() });
      tx.oncomplete = () => resolve(true);
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
    if (!items.length) return;
    await fetch('/api/mobile/offline/sync', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    });
    await fetch('/api/mobile/offline/process', { method: 'POST', credentials: 'same-origin', body: '{}' });
    const clearTx = db.transaction(STORE, 'readwrite');
    clearTx.objectStore(STORE).clear();
  }

  global.CasePMOfflineOutbox = { enqueue, drainToServer };

  global.addEventListener('online', () => { drainToServer().catch(() => {}); });
  if (global.navigator.onLine) drainToServer().catch(() => {});
})(typeof window !== 'undefined' ? window : globalThis);
