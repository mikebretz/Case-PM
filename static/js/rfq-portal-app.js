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

  async function submitQuote(rfqId, amount) {
    await api(`/api/rfqs/${rfqId}/portal-quote`, {
      method: 'POST',
      body: JSON.stringify({ quoted_amount: amount }),
    });
    await load();
  }

  async function load() {
    const id = pid();
    const el = document.getElementById('rfqPortalList');
    if (!id || !el) {
      if (el) el.innerHTML = '<p class="text-zinc-500">Select a project first.</p>';
      return;
    }
    const { rfqs } = await api(`/api/rfqs/portal?project_id=${id}`);
    if (!rfqs.length) {
      el.innerHTML = '<p class="text-zinc-500 text-center py-12">No RFQs assigned to your company.</p>';
      return;
    }
    el.innerHTML = rfqs.map(r => `
      <div class="border border-zinc-700 rounded-lg bg-zinc-900 p-4">
        <div class="flex justify-between items-start gap-4">
          <div>
            <div class="font-mono text-sky-400">${esc(r.number)}</div>
            <div class="font-medium text-white mt-1">${esc(r.title)}</div>
            <div class="text-xs text-zinc-400 mt-1">${esc(r.description || '')}</div>
            <div class="text-xs text-zinc-500 mt-2">Due: ${r.due_date || '—'} · Status: ${esc(r.status)}</div>
          </div>
          <div class="text-right shrink-0">
            ${r.status === 'Sent' ? `<button type="button" data-quote="${r.id}" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-medium">Submit Quote</button>` : ''}
            ${r.quoted_amount ? `<div class="text-sm font-mono text-emerald-400 mt-2">${fmt(r.quoted_amount)}</div>` : ''}
          </div>
        </div>
      </div>`).join('');
    el.querySelectorAll('[data-quote]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const rfqId = parseInt(btn.getAttribute('data-quote'), 10);
        const rfq = rfqs.find(x => x.id === rfqId);
        let amount = prompt('Quote amount ($):', rfq?.allocations?.[0]?.amount || '0');
        if (amount == null) return;
        amount = parseFloat(amount) || 0;
        if (!amount) return;
        try {
          await submitQuote(rfqId, amount);
          alert('Quote submitted.');
        } catch (e) {
          alert(e.message);
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const rfqId = new URLSearchParams(location.search).get('rfq_id');
    load().then(() => {
      if (rfqId) {
        const btn = document.querySelector(`[data-quote="${rfqId}"]`);
        if (btn) btn.click();
      }
    });
  });
})();
