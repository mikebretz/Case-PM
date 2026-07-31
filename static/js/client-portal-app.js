(function () {
  'use strict';

  const ctx = window.CASEPM_CLIENT_PORTAL_CTX || {};
  let feed = {};

  function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  async function api(path, opts) {
    const headers = { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json', ...(opts?.headers || {}) };
    const token = csrf();
    if (token && (opts?.method || 'GET') !== 'GET') headers['X-CSRF-Token'] = token;
    const q = ctx.projectId ? `?project_id=${ctx.projectId}` : '';
    const res = await fetch(path + (path.includes('?') ? '' : q), { credentials: 'same-origin', ...opts, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function showTab(name) {
    document.querySelectorAll('.cp-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    document.querySelectorAll('.cp-panel').forEach(p => p.classList.add('hidden'));
    const map = { approvals: 'cpApprovals', selections: 'cpSelections', draws: 'cpDraws', payments: 'cpPayments', updates: 'cpItems' };
    document.getElementById(map[name])?.classList.remove('hidden');
  }

  function renderApprovals(items) {
    const host = document.getElementById('cpApprovals');
    if (!host) return;
    if (!items.length) { host.innerHTML = '<div class="p-6 text-zinc-500 text-center">No pending approvals.</div>'; return; }
    host.innerHTML = items.map(a => `
      <div class="cp-row">
        <div class="flex-1"><div class="font-medium text-white">${esc(a.title)}</div>
        <div class="text-xs text-zinc-500">${esc(a.item_type)} · ${esc(a.status)}</div></div>
        <div class="flex flex-col gap-1">${a.id ? `<button type="button" class="text-xs text-emerald-400 cp-respond" data-id="${a.id}">Respond</button>` : ''}
        ${a.action_url ? `<a href="${esc(a.action_url)}" class="text-xs text-sky-400">Open</a>` : ''}</div>
      </div>`).join('');
    host.querySelectorAll('.cp-respond').forEach(btn => btn.addEventListener('click', () => openRespond(parseInt(btn.dataset.id, 10))));
  }

  function renderSimpleList(hostId, items, empty, rowFn) {
    const host = document.getElementById(hostId);
    if (!host) return;
    if (!items.length) { host.innerHTML = `<div class="p-6 text-zinc-500 text-center">${empty}</div>`; return; }
    host.innerHTML = items.map(rowFn).join('');
  }

  function renderAll() {
    renderApprovals(feed.approvals || []);
    renderSimpleList('cpSelections', feed.selections || [], 'No selections pending.', s => `
      <div class="cp-row"><div class="flex-1"><div class="font-medium">${esc(s.title)}</div>
      <div class="text-xs text-zinc-500">${esc(s.category)} · ${esc(s.status)}</div></div>
      ${s.status === 'Pending' ? `<button type="button" class="text-xs text-emerald-400 cp-sel" data-id="${s.id}">Choose</button>` : `<span class="text-xs text-zinc-400">${esc(s.selected_option)}</span>`}
      </div>`);
    document.querySelectorAll('.cp-sel').forEach(btn => btn.addEventListener('click', async () => {
      const opt = prompt('Enter your selection:');
      if (!opt) return;
      await api(`/api/client-portal/selections/${btn.dataset.id}/choose`, { method: 'POST', body: JSON.stringify({ option: opt }) });
      load();
    }));
    renderSimpleList('cpDraws', feed.draw_requests || [], 'No draw requests.', d => {
      const docs = (d.package?.documents || []).map((doc) =>
        `<a href="${esc(doc.path)}" class="text-xs text-sky-400 block">${esc(doc.label)}</a>`,
      ).join('');
      return `<div class="cp-row"><div class="flex-1"><div class="font-medium">${esc(d.title)}</div>
      <div class="text-xs text-zinc-500">$${Number(d.amount||0).toLocaleString()} · ${esc(d.period || '')} · ${esc(d.status)}</div>
      ${docs}</div>
      <button type="button" class="text-xs text-emerald-400 cp-draw" data-id="${d.id}">Approve</button></div>`;
    });
    document.querySelectorAll('.cp-draw').forEach(btn => btn.addEventListener('click', async () => {
      await api(`/api/client-portal/draws/${btn.dataset.id}/respond`, { method: 'POST', body: JSON.stringify({ decision: 'Approved' }) });
      load();
    }));
    renderSimpleList('cpPayments', feed.payments || [], 'No payments.', p => `
      <div class="cp-row"><div class="flex-1"><div class="font-medium">${esc(p.title)}</div>
      <div class="text-xs text-zinc-500">$${Number(p.amount||0).toLocaleString()} · ${esc(p.method)} · ${esc(p.status)}</div></div></div>`);
    renderSimpleList('cpItems', feed.portal_items || [], 'No published updates.', i => `
      <div class="cp-row"><div class="font-medium">${esc(i.title)}</div><div class="text-xs text-zinc-500">${esc(i.status)}</div></div>`);
  }

  function openRespond(id) {
    document.getElementById('cpApprovalId').value = id;
    document.getElementById('cpRespondModal')?.showModal();
  }

  async function load() {
    feed = await api('/api/client-portal/feed');
    renderAll();
  }

  document.querySelectorAll('.cp-tab').forEach(t => t.addEventListener('click', () => showTab(t.dataset.tab)));
  document.getElementById('cpCancel')?.addEventListener('click', () => document.getElementById('cpRespondModal')?.close());
  document.getElementById('cpSubmit')?.addEventListener('click', async () => {
    const id = document.getElementById('cpApprovalId')?.value;
    await api(`/api/client-portal/approvals/${id}/respond`, {
      method: 'POST',
      body: JSON.stringify({ response: document.getElementById('cpResponseText')?.value, decision: document.getElementById('cpDecision')?.value }),
    });
    document.getElementById('cpRespondModal')?.close();
    load();
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => load().catch(console.error));
  else load().catch(console.error);
})();
