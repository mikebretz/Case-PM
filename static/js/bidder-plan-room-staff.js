(function () {
  'use strict';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function api(path, opts) {
    const headers = { 'X-Requested-With': 'XMLHttpRequest', ...(opts?.headers || {}) };
    const res = await fetch(path, { credentials: 'same-origin', ...opts, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  async function loadPlanRoomPending() {
    const host = document.getElementById('estPlanRoomPending');
    if (!host) return;
    host.innerHTML = '<p class="text-xs text-zinc-500">Loading…</p>';
    try {
      const data = await api('/api/bidder-network/registrations?status=pending');
      const rows = data.registrations || [];
      if (!rows.length) {
        host.innerHTML = '<p class="text-xs text-zinc-500">No pending bidder registrations.</p>';
        return;
      }
      host.innerHTML = rows.map((r) => `
        <div class="border border-zinc-700 rounded-md p-3 flex flex-wrap justify-between gap-2 items-start">
          <div>
            <div class="font-medium text-white">${esc(r.company_name)}</div>
            <div class="text-xs text-zinc-400">${esc(r.contact_name)} · ${esc(r.email)} · ${esc(r.phone || '')}</div>
            <div class="text-xs text-zinc-500 mt-1">${esc((r.specialties || []).join(', '))}</div>
            ${r.comments ? `<p class="text-xs text-zinc-400 mt-1">${esc(r.comments)}</p>` : ''}
          </div>
          <div class="flex gap-2">
            <button type="button" class="pr-approve px-2 py-1 bg-emerald-700 rounded text-xs" data-id="${r.id}">Approve</button>
            <button type="button" class="pr-reject px-2 py-1 bg-zinc-700 rounded text-xs" data-id="${r.id}">Reject</button>
          </div>
        </div>
      `).join('');
      host.querySelectorAll('.pr-approve').forEach((btn) => btn.addEventListener('click', async () => {
        if (!confirm('Approve this bidder? They can sign in and view published opportunities.')) return;
        await api(`/api/bidder-network/registrations/${btn.dataset.id}/approve`, { method: 'POST', body: '{}' });
        loadPlanRoomPending();
      }));
      host.querySelectorAll('.pr-reject').forEach((btn) => btn.addEventListener('click', async () => {
        const reason = prompt('Rejection reason (optional):') || '';
        await api(`/api/bidder-network/registrations/${btn.dataset.id}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason }),
        });
        loadPlanRoomPending();
      }));
    } catch (e) {
      host.innerHTML = `<p class="text-xs text-red-400">${esc(e.message)}</p>`;
    }
  }

  window.loadPlanRoomPending = loadPlanRoomPending;
  document.getElementById('estPlanRoomRefresh')?.addEventListener('click', loadPlanRoomPending);
  document.getElementById('estPlanRoomPublishProject')?.addEventListener('click', async () => {
    const pid = window.CASEPM_ESTIMATE_CTX?.projectId;
    if (!pid) {
      alert('Select an active project in the header first.');
      return;
    }
    const summary = prompt('Public project summary for plan room (optional):') || '';
    const bidDate = prompt('Bid date (YYYY-MM-DD, optional):') || '';
    try {
      await api(`/api/bidder-network/projects/${pid}/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          published: true,
          publish_all_packages: true,
          summary,
          bid_date: bidDate || undefined,
        }),
      });
      alert('Project published to plan room. Publish individual packages or attach documents on bid packages as needed.');
    } catch (e) {
      alert(e.message);
    }
  });
  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('estPlanRoomPending')) loadPlanRoomPending();
  });
})();
