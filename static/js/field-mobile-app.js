(function () {
  'use strict';

  const ctx = window.CASEPM_FIELD_CTX || {};
  const QUEUE_KEY = 'casepm_field_queue';

  function queue() {
    try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); } catch (e) { return []; }
  }

  function saveQueue(items) {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
    updateQueueUi();
  }

  function updateQueueUi() {
    const el = document.getElementById('fmQueue');
    if (el) el.textContent = `Queue: ${queue().length} pending`;
  }

  function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  function capture(type) {
    const notes = document.getElementById('fmNotes')?.value?.trim() || '';
    const items = queue();
    items.push({
      type,
      project_id: ctx.projectId,
      title: `${type.replace('_', ' ')} — ${new Date().toLocaleString()}`,
      notes,
      captured_at: new Date().toISOString(),
      simple: { notes },
    });
    saveQueue(items);
    const notesEl = document.getElementById('fmNotes');
    if (notesEl) notesEl.value = '';
    toast('Saved offline — tap Sync when online');
  }

  function toast(msg) {
    const el = document.createElement('div');
    el.className = 'fixed bottom-4 left-1/2 -translate-x-1/2 bg-emerald-800 text-white px-4 py-2 rounded-lg text-sm z-[9999]';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
  }

  async function syncNow() {
    const items = queue();
    if (!items.length) { toast('Nothing to sync'); return; }
    const token = csrf();
    const res = await fetch('/api/field/offline-sync', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token, 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ items }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Sync failed');
    saveQueue([]);
    toast(`Synced ${data.synced || 0} item(s)`);
  }

  document.querySelectorAll('[data-capture]').forEach(btn => {
    btn.addEventListener('click', () => capture(btn.dataset.capture));
  });
  document.getElementById('fmSave')?.addEventListener('click', () => capture('daily_log'));
  document.getElementById('fmSync')?.addEventListener('click', () => syncNow().catch(e => toast(e.message)));

  if ('serviceWorker' in navigator && 'PushManager' in window) {
    navigator.serviceWorker.ready.then(reg => {
      reg.pushManager.getSubscription().then(sub => {
        if (!sub) return;
      });
    }).catch(() => {});
  }

  updateQueueUi();
})();
