(function () {
  'use strict';

  const ctx = window.CASEPM_CLIENT_PORTAL_CTX || {};

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

  function renderApprovals(items) {
    const host = document.getElementById('cpApprovals');
    if (!host) return;
    if (!items.length) {
      host.innerHTML = '<div class="p-6 text-zinc-500 text-center">No pending approvals.</div>';
      return;
    }
    host.innerHTML = items.map(a => `
      <div class="cp-row">
        <div class="flex-1 min-w-0">
          <div class="font-medium text-white">${esc(a.title)}</div>
          <div class="text-xs text-zinc-500 mt-0.5">${esc(a.item_type)} · ${esc(a.status)}</div>
          ${a.description ? `<div class="text-xs text-zinc-400 mt-1">${esc(a.description)}</div>` : ''}
        </div>
        <div class="flex flex-col gap-1 flex-shrink-0">
          ${a.action_url ? `<a href="${esc(a.action_url)}" class="text-xs text-sky-400">Open</a>` : ''}
          ${a.id ? `<button type="button" class="text-xs text-emerald-400 cp-respond" data-id="${a.id}">Respond</button>` : ''}
        </div>
      </div>`).join('');
    host.querySelectorAll('.cp-respond').forEach(btn => {
      btn.addEventListener('click', () => openRespond(parseInt(btn.dataset.id, 10)));
    });
  }

  function renderItems(items) {
    const host = document.getElementById('cpItems');
    if (!host) return;
    if (!items.length) {
      host.innerHTML = '<div class="p-6 text-zinc-500 text-center">No published updates yet.</div>';
      return;
    }
    host.innerHTML = items.map(i => `
      <div class="cp-row">
        <div class="flex-1">
          <div class="font-medium text-white">${esc(i.title)}</div>
          <div class="text-xs text-zinc-500">${esc(i.status)} · ${esc(i.record_date || '')}</div>
        </div>
      </div>`).join('');
  }

  function openRespond(id) {
    document.getElementById('cpApprovalId').value = id;
    document.getElementById('cpResponseText').value = '';
    document.getElementById('cpRespondModal')?.showModal();
  }

  async function load() {
    const data = await api('/api/client-portal/feed');
    renderApprovals(data.approvals || []);
    renderItems(data.portal_items || []);
  }

  document.getElementById('cpCancel')?.addEventListener('click', () => document.getElementById('cpRespondModal')?.close());
  document.getElementById('cpSubmit')?.addEventListener('click', async () => {
    const id = document.getElementById('cpApprovalId')?.value;
    try {
      await api(`/api/client-portal/approvals/${id}/respond`, {
        method: 'POST',
        body: JSON.stringify({
          response: document.getElementById('cpResponseText')?.value,
          decision: document.getElementById('cpDecision')?.value,
        }),
      });
      document.getElementById('cpRespondModal')?.close();
      await load();
    } catch (e) {
      alert(e.message);
    }
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => load().catch(e => console.error(e)));
  else load().catch(e => console.error(e));
})();
