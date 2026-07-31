/**
 * Parity wave 2 UI hooks — cash workbench, credit review, bank OFX/dist, tax filing, report designer.
 */
(function (global) {
  'use strict';

  function helpers() {
    const A = global.CasePMAccounting || {};
    return { api: A._api, esc: A._esc, money: A._money, switchModule: A.switchModule, AD: () => global.CasePMAccountingDialog || {} };
  }

  async function renderCashWorkbenchPanel(customerId) {
    const { api, esc, money } = helpers();
    const data = await api(`/api/accounting/ar/cash-workbench/${customerId}`);
    const invRows = (data.open_invoices || []).map((i) =>
      `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono">${esc(i.document_number)}</td>
        <td class="px-2 py-1 text-right">${money(i.open_amount)}</td>
        <td class="px-2 py-1"><input type="number" step="0.01" class="acct-cash-apply-amt w-20 bg-zinc-900 border border-zinc-600 rounded px-1" data-doc="${i.ar_document_id}" value="${i.open_amount}"></td></tr>`
    ).join('');
    const rcptOpts = (data.unapplied_receipts || []).map((r) =>
      `<option value="${r.receipt_id}">${esc(r.receipt_number)} — ${money(r.unapplied_amount)} unapplied</option>`
    ).join('');
    return `<div class="border border-zinc-700 rounded-lg p-3 mt-4" id="acctCashWorkbench">
      <h3 class="text-sm font-medium text-white mb-2">Cash application workbench</h3>
      <div class="flex flex-wrap gap-2 items-end mb-2">
        <div><label class="text-xs text-zinc-500 block">Receipt</label>
          <select id="acctCashWbReceipt" class="bg-zinc-900 border border-zinc-600 rounded text-sm px-2 py-1">${rcptOpts || '<option value="">No unapplied receipts</option>'}</select></div>
        <button type="button" id="acctCashWbApply" class="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 rounded text-sm">Apply to invoices</button>
      </div>
      <table class="w-full text-xs"><thead class="text-zinc-500"><tr><th class="text-left px-2">Invoice</th><th class="text-right px-2">Open</th><th class="text-right px-2">Apply</th></tr></thead>
        <tbody>${invRows || '<tr><td colspan="3" class="p-2 text-zinc-500">No open invoices.</td></tr>'}</tbody></table>
    </div>`;
  }

  function bindCashWorkbench(customerId) {
    const { api, AD } = helpers();
    document.getElementById('acctCashWbApply')?.addEventListener('click', async () => {
      const rid = document.getElementById('acctCashWbReceipt')?.value;
      if (!rid) return AD().alert('Select a receipt', 'warning');
      const applications = [];
      document.querySelectorAll('.acct-cash-apply-amt').forEach((inp) => {
        const amt = parseFloat(inp.value);
        if (amt > 0) applications.push({ ar_document_id: parseInt(inp.getAttribute('data-doc'), 10), amount: amt });
      });
      try {
        await api('/api/accounting/ar/cash-application/apply', {
          method: 'POST',
          body: JSON.stringify({ receipt_id: parseInt(rid, 10), applications }),
        });
        await AD().alert('Cash applied.', 'success');
        helpers().switchModule('ar');
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });
  }

  async function renderCreditReviewSection() {
    const { api, esc, money } = helpers();
    const data = await api('/api/accounting/ar/credit-reviews');
    const rows = (data.reviews || []).map((r) =>
      `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${esc(r.customer_code)}</td>
        <td class="px-2 py-1">${esc(r.status)}</td><td class="px-2 py-1 text-right">${money(r.requested_limit)}</td>
        <td class="px-2 py-1 text-xs">${esc(r.reason || '')}</td>
        ${r.status === 'Open' ? `<td class="px-2 py-1"><button type="button" class="text-emerald-400 text-xs acct-cr-approve" data-id="${r.id}">Approve</button>
          <button type="button" class="text-red-400 text-xs acct-cr-deny" data-id="${r.id}">Deny</button></td>` : '<td></td>'}
      </tr>`
    ).join('');
    return `<div class="border border-zinc-700 rounded-lg p-3 mt-4">
      <div class="flex justify-between items-center mb-2"><h3 class="text-sm text-white">Credit review queue</h3>
        <button type="button" id="acctCrNew" class="text-xs text-emerald-400">+ Request review</button></div>
      <table class="w-full text-xs"><thead class="text-zinc-500"><tr><th class="text-left px-2">Customer</th><th>Status</th><th class="text-right">Limit</th><th>Reason</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="p-2 text-zinc-500">No reviews.</td></tr>'}</tbody></table>
    </div>`;
  }

  function bindCreditReview() {
    const { api, AD, switchModule } = helpers();
    document.getElementById('acctCrNew')?.addEventListener('click', async () => {
      const customerId = await AD().prompt('Customer id for credit review:', '', 'Credit review');
      const limit = await AD().prompt('Requested credit limit:', '50000', 'Credit review');
      if (!customerId) return;
      await api('/api/accounting/ar/credit-reviews', {
        method: 'POST',
        body: JSON.stringify({ customer_id: parseInt(customerId, 10), requested_limit: parseFloat(limit || 0), reason: 'Manual review' }),
      });
      switchModule('ar');
    });
    document.querySelectorAll('.acct-cr-approve').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api('/api/accounting/ar/credit-reviews', {
          method: 'POST',
          body: JSON.stringify({ resolve_review_id: parseInt(btn.getAttribute('data-id'), 10), approved: true, clear_hold: true }),
        });
        switchModule('ar');
      });
    });
    document.querySelectorAll('.acct-cr-deny').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api('/api/accounting/ar/credit-reviews', {
          method: 'POST',
          body: JSON.stringify({ resolve_review_id: parseInt(btn.getAttribute('data-id'), 10), approved: false }),
        });
        switchModule('ar');
      });
    });
  }

  async function bankExtrasHtml() {
    const { api, esc } = helpers();
    const codes = await api('/api/accounting/bank/distribution-codes');
    const list = (codes.codes || []).map((c) => `<li class="font-mono text-xs">${esc(c.code)} — ${esc(c.name)} (${(c.lines || []).length} lines)</li>`).join('');
    return `<div class="grid md:grid-cols-2 gap-3 mt-4">
      <div class="border border-zinc-700 rounded-lg p-3">
        <h3 class="text-sm text-zinc-300 mb-2">Distribution codes</h3>
        <ul class="space-y-1 mb-2">${list || '<li class="text-zinc-500 text-xs">None defined.</li>'}</ul>
        <button type="button" id="acctBankAddDist" class="text-xs text-emerald-400">+ Add distribution code</button>
      </div>
      <div class="border border-zinc-700 rounded-lg p-3">
        <h3 class="text-sm text-zinc-300 mb-2">OFX / bank feed import</h3>
        <textarea id="acctOfxPaste" class="w-full h-24 bg-zinc-900 border border-zinc-600 rounded text-xs font-mono p-2" placeholder="Paste OFX/QFX snippet…"></textarea>
        <button type="button" id="acctOfxImport" class="mt-2 px-3 py-1.5 bg-violet-600 rounded text-sm">Import transactions</button>
      </div>
    </div>`;
  }

  function bindBankExtras(getSelectedBankId) {
    const { api, AD, switchModule } = helpers();
    document.getElementById('acctBankAddDist')?.addEventListener('click', async () => {
      const code = await AD().prompt('Distribution code:', 'DEP-GL', 'Bank');
      const acct = await AD().prompt('G/L account number (100%):', '4000', 'Bank');
      if (!code) return;
      await api('/api/accounting/bank/distribution-codes', {
        method: 'POST',
        body: JSON.stringify({ code, name: code, lines: [{ account_number: acct, percent: 100 }] }),
      });
      switchModule('bank');
    });
    document.getElementById('acctOfxImport')?.addEventListener('click', async () => {
      const bankId = getSelectedBankId();
      const text = document.getElementById('acctOfxPaste')?.value || '';
      if (!bankId || !text.trim()) return AD().alert('Select bank and paste OFX', 'warning');
      const out = await api('/api/accounting/bank/ofx-import', { method: 'POST', body: JSON.stringify({ bank_account_id: bankId, ofx_text: text }) });
      await AD().alert(`Imported ${out.imported} transaction(s).`, 'success');
      switchModule('bank');
    });
  }

  async function enhanceDashboard(root) {
    const { api, esc, money } = helpers();
    try {
      const kpi = await api('/api/accounting/bi/kpi-dashboard');
      const extra = document.createElement('div');
      extra.className = 'grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4';
      extra.innerHTML = (kpi.tiles || []).slice(0, 8).map((t) =>
        `<div class="bg-zinc-800/60 border border-zinc-700 rounded-lg p-3"><div class="text-[10px] text-zinc-500 uppercase">${esc(t.label)}</div>
          <div class="text-lg font-semibold">${t.format === 'money' ? money(t.value) : esc(String(t.value))}</div></div>`
      ).join('');
      const first = root.querySelector('.grid');
      if (first && first.parentNode) first.parentNode.insertBefore(extra, first.nextSibling);
    } catch (_) { /* optional */ }
  }

  global.CasePMAcctParityUI = {
    renderCashWorkbenchPanel,
    bindCashWorkbench,
    renderCreditReviewSection,
    bindCreditReview,
    bankExtrasHtml,
    bindBankExtras,
    enhanceDashboard,
  };
})(typeof window !== 'undefined' ? window : globalThis);
