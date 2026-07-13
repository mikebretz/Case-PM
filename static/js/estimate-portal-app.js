(function () {
  'use strict';

  const state = { rows: [] };

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

  function openDialog(el) {
    if (!el) return;
    if (window.CasePMDialog?.open) window.CasePMDialog.open(el);
    else el.showModal();
  }

  function closeDialog(el) {
    if (el && typeof el.close === 'function') el.close();
  }

  async function portalAlert(message, type = 'success') {
    if (window.CasePMDialog?.alert) return window.CasePMDialog.alert(message, type);
    alert(message);
  }

  async function respond(invitationId, body) {
    await api(`/api/estimates/portal/${invitationId}/respond`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    await load();
  }

  function addQuoteLineRow(desc = '', amount = '') {
    const wrap = document.getElementById('estPortalQuoteLines');
    if (!wrap) return;
    const row = document.createElement('div');
    row.className = 'flex gap-2';
    row.innerHTML = `
      <input type="text" placeholder="Description" class="ql-desc flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm" value="${esc(desc)}">
      <input type="number" step="0.01" placeholder="Amt" class="ql-amt w-24 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm font-mono" value="${amount}">
      <button type="button" class="text-red-400 px-1 remove-ql">×</button>`;
    row.querySelector('.remove-ql').addEventListener('click', () => row.remove());
    wrap.appendChild(row);
  }

  function readQuoteLines() {
    return [...document.querySelectorAll('#estPortalQuoteLines .flex.gap-2')].map(row => ({
      description: row.querySelector('.ql-desc')?.value || '',
      amount: parseFloat(row.querySelector('.ql-amt')?.value) || 0,
    })).filter(l => l.description || l.amount);
  }

  function openQuoteModal(row) {
    const inv = row.invitation;
    const pkg = row.bid_package;
    document.getElementById('estPortalQuoteInvId').value = inv.id;
    document.getElementById('estPortalQuotePkgTitle').textContent = `${pkg.number} — ${pkg.title}`;
    document.getElementById('estPortalQuoteAmount').value = '';
    document.getElementById('estPortalQuoteNotes').value = '';
    const ql = document.getElementById('estPortalQuoteLines');
    if (ql) ql.innerHTML = '';
    addQuoteLineRow();
    openDialog(document.getElementById('estPortalQuoteModal'));
    document.getElementById('estPortalQuoteAmount').focus();
  }

  function openDeclineModal(row) {
    document.getElementById('estPortalDeclineInvId').value = row.invitation.id;
    document.getElementById('estPortalDeclineReason').value = 'Not bidding this scope';
    openDialog(document.getElementById('estPortalDeclineModal'));
  }

  async function load() {
    const id = pid();
    const el = document.getElementById('estPortalList');
    if (!id || !el) {
      if (el) el.innerHTML = '<p class="text-zinc-500">Select a project first.</p>';
      return;
    }
    const { invitations } = await api(`/api/estimates/portal?project_id=${id}`);
    state.rows = invitations || [];
    if (!state.rows.length) {
      el.innerHTML = '<p class="text-zinc-500 text-center py-12">No RFP invitations assigned to your company.</p>';
      return;
    }
    el.innerHTML = state.rows.map(row => {
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
            <div class="flex flex-col gap-2 shrink-0 est-portal-card-actions">
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
      btn.addEventListener('click', () => {
        const invId = parseInt(btn.closest('[data-inv]').dataset.inv, 10);
        const row = state.rows.find(r => r.invitation.id === invId);
        if (row) openQuoteModal(row);
      });
    });

    el.querySelectorAll('.btn-decline').forEach(btn => {
      btn.addEventListener('click', () => {
        const invId = parseInt(btn.closest('[data-inv]').dataset.inv, 10);
        const row = state.rows.find(r => r.invitation.id === invId);
        if (row) openDeclineModal(row);
      });
    });
  }

  function bindEvents() {
    document.querySelectorAll('.estPortalModalClose').forEach(btn => {
      btn.addEventListener('click', () => closeDialog(document.getElementById(btn.getAttribute('data-target'))));
    });

    document.getElementById('estPortalAddQuoteLine')?.addEventListener('click', () => addQuoteLineRow());

    document.getElementById('estPortalQuoteForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const invId = parseInt(document.getElementById('estPortalQuoteInvId').value, 10);
      let amount = parseFloat(document.getElementById('estPortalQuoteAmount').value) || 0;
      const quote_lines = readQuoteLines();
      if (!amount && quote_lines.length) amount = quote_lines.reduce((s, l) => s + l.amount, 0);
      if (!amount) {
        await portalAlert('Enter a quote amount or line items.', 'warning');
        return;
      }
      const notes = document.getElementById('estPortalQuoteNotes').value || '';
      try {
        await respond(invId, { action: 'quote', quote_amount: amount, quote_notes: notes, quote_lines });
        closeDialog(document.getElementById('estPortalQuoteModal'));
        await portalAlert('Quote submitted.', 'success');
      } catch (err) {
        await portalAlert(err.message, 'error');
      }
    });

    document.getElementById('estPortalDeclineForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      const invId = parseInt(document.getElementById('estPortalDeclineInvId').value, 10);
      const reason = document.getElementById('estPortalDeclineReason').value || '';
      try {
        await respond(invId, { action: 'not_interested', reason });
        closeDialog(document.getElementById('estPortalDeclineModal'));
        await portalAlert('Response recorded.', 'success');
      } catch (err) {
        await portalAlert(err.message, 'error');
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.CasePMDialog?.initAllDialogs) window.CasePMDialog.initAllDialogs();
    bindEvents();
    const pkgId = new URLSearchParams(location.search).get('package_id');
    load().then(() => {
      if (pkgId && state.rows.length) {
        const row = state.rows.find(r => String(r.bid_package.id) === String(pkgId)) || state.rows[0];
        if (row && (row.invitation.status === 'Sent' || row.invitation.status === 'Viewed')) {
          openQuoteModal(row);
        }
      }
    }).catch(err => portalAlert(err.message, 'error'));
  });
})();
