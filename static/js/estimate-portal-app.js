(function () {
  'use strict';

  function pid() {
    const params = new URLSearchParams(location.search);
    return params.get('project_id') || localStorage.getItem('casepm_current_project_id');
  }

  function fmt(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  async function respond(invitationId, body) {
    await api(`/api/estimates/portal/${invitationId}/respond`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    await load();
  }

  async function load() {
    const id = pid();
    const el = document.getElementById('estPortalList');
    if (!id || !el) {
      if (el) el.innerHTML = '<p class="text-zinc-500">Select a project first.</p>';
      return;
    }
    const { invitations } = await api(`/api/estimates/portal?project_id=${id}`);
    if (!invitations.length) {
      el.innerHTML = '<p class="text-zinc-500 text-center py-12">No RFP invitations assigned to your company.</p>';
      return;
    }
    el.innerHTML = invitations.map(row => {
      const inv = row.invitation;
      const pkg = row.bid_package;
      const open = inv.status === 'Sent' || inv.status === 'Viewed';
      return `
        <div class="border border-zinc-700 rounded-lg bg-zinc-900 p-4" data-inv="${inv.id}">
          <div class="flex justify-between items-start gap-4 flex-wrap">
            <div>
              <div class="text-xs text-zinc-500">${esc(row.estimate_number)} · ${esc(pkg.number)}</div>
              <div class="font-medium text-white mt-1">${esc(pkg.title)}</div>
              <div class="text-sm text-zinc-400 mt-1">Spec ${esc(pkg.spec_section || '—')} · Due ${pkg.due_date || '—'}</div>
              <div class="text-xs text-zinc-500 mt-2">${esc(pkg.scope_notes || pkg.description || '')}</div>
              <div class="text-xs text-zinc-500 mt-2">Status: ${esc(inv.status)}</div>
            </div>
            <div class="flex flex-col gap-2 shrink-0">
              ${open ? `
                <button type="button" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-medium btn-quote">Submit Quote</button>
                <button type="button" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm btn-decline">Not Interested</button>
              ` : ''}
              ${inv.quote_amount ? `<div class="text-sm font-mono text-emerald-400 text-right">${fmt(inv.quote_amount)}</div>` : ''}
              ${inv.decline_reason ? `<div class="text-xs text-zinc-500">${esc(inv.decline_reason)}</div>` : ''}
            </div>
          </div>
        </div>`;
    }).join('');

    el.querySelectorAll('.btn-quote').forEach(btn => {
      btn.addEventListener('click', async () => {
        const card = btn.closest('[data-inv]');
        const invId = parseInt(card.dataset.inv, 10);
        const amount = parseFloat(prompt('Quote amount ($):', '0') || '0');
        if (!amount) return;
        const notes = prompt('Notes (optional):', '') || '';
        try {
          await respond(invId, { action: 'quote', quote_amount: amount, quote_notes: notes });
          alert('Quote submitted.');
        } catch (e) { alert(e.message); }
      });
    });

    el.querySelectorAll('.btn-decline').forEach(btn => {
      btn.addEventListener('click', async () => {
        const card = btn.closest('[data-inv]');
        const invId = parseInt(card.dataset.inv, 10);
        const reason = prompt('Reason (optional):', 'Not bidding this scope') || '';
        try {
          await respond(invId, { action: 'not_interested', reason });
          alert('Response recorded.');
        } catch (e) { alert(e.message); }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const pkgId = new URLSearchParams(location.search).get('package_id');
    load().then(() => {
      if (pkgId) {
        const card = document.querySelector(`[data-inv]`);
        card?.querySelector('.btn-quote')?.click();
      }
    });
  });
})();
