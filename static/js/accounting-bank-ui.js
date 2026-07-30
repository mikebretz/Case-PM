/**
 * Bank Services workspace — accounts, register, reconciliation, manual entries.
 */
(function (global) {
  'use strict';

  let ctx = null;
  let selectedBankId = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  function agingBucketsHtml(buckets, money, esc) {
    const b = buckets || {};
    const keys = [
      ['current', 'Current'],
      ['1_30', '1–30'],
      ['31_60', '31–60'],
      ['61_90', '61–90'],
      ['over_90', '90+'],
    ];
    return `<div class="grid grid-cols-5 gap-2 text-xs">${keys.map(([k, lab]) =>
      `<div class="bg-zinc-800 border border-zinc-700 rounded p-2"><div class="text-zinc-500">${esc(lab)}</div><div class="font-medium">${money(b[k])}</div></div>`
    ).join('')}</div>`;
  }

  async function render() {
    const { api, esc, money } = ctx;
    const accounts = await api('/api/accounting/bank/accounts');
    const list = accounts.accounts || [];
    if (!selectedBankId && list[0]) selectedBankId = list[0].id;
    let tx = { transactions: [] };
    if (selectedBankId) {
      tx = await api(`/api/accounting/bank/transactions?bank_account_id=${selectedBankId}`);
    }
    const sel = list.find((a) => a.id === selectedBankId);
    return `<div class="space-y-6">
      <div class="flex flex-wrap justify-between gap-2 items-start">
        <div>
          <h2 class="text-lg font-semibold text-white">Bank Services</h2>
          <p class="text-xs text-zinc-500 mt-1">Cash accounts, register, manual deposits/withdrawals, reconciliation.</p>
        </div>
        <div class="flex gap-2">
          <button type="button" id="acctAddBank" class="text-xs px-3 py-2 border border-zinc-700 rounded-md text-emerald-400">+ Bank account</button>
          <button type="button" id="acctBankManualTx" class="text-xs px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded-md text-white" ${selectedBankId ? '' : 'disabled'}>Manual entry</button>
        </div>
      </div>
      <div class="grid md:grid-cols-3 gap-3">
        ${list.map((a) => `<button type="button" class="text-left p-3 rounded-lg border ${a.id === selectedBankId ? 'border-emerald-600 bg-zinc-800' : 'border-zinc-700 bg-zinc-900/50'} acct-bank-pick" data-id="${a.id}">
          <div class="font-mono text-emerald-400 text-sm">${esc(a.code)}</div>
          <div class="text-xs text-zinc-400 truncate">${esc(a.name)}</div>
          <div class="text-lg font-semibold mt-2">${money(a.book_balance)}</div>
          <div class="text-[10px] text-zinc-500">${a.unreconciled_count} unreconciled · ${esc(a.currency)}</div>
        </button>`).join('') || '<p class="text-zinc-500 text-sm col-span-3">No bank accounts — add one linked to your cash G/L account.</p>'}
      </div>
      ${sel ? `<p class="text-xs text-zinc-500">Selected: <span class="text-zinc-300">${esc(sel.name)}</span> · G/L cash account id ${esc(sel.gl_account_id || '— (uses program default cash account)')}</p>` : ''}
      <div class="grid lg:grid-cols-2 gap-4">
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Register (recent)</h3>
          <div class="border border-zinc-700 rounded-lg max-h-64 overflow-y-auto">
            <table class="w-full text-xs"><thead class="bg-zinc-800 sticky top-0 text-zinc-500"><tr>
              <th class="text-left px-2 py-1">Date</th><th class="text-left px-2 py-1">Description</th>
              <th class="text-right px-2 py-1">Amount</th><th class="text-center px-2 py-1">Rec</th>
            </tr></thead><tbody>
              ${(tx.transactions || []).map((t) => `<tr class="border-t border-zinc-800">
                <td class="px-2 py-1">${esc(t.transaction_date)}</td>
                <td class="px-2 py-1">${esc(t.description || t.reference)}</td>
                <td class="px-2 py-1 text-right font-mono ${t.amount < 0 ? 'text-red-400' : 'text-emerald-400'}">${money(t.amount)}</td>
                <td class="px-2 py-1 text-center">${t.reconciled ? '✓' : '—'}</td>
              </tr>`).join('') || '<tr><td colspan="4" class="p-3 text-zinc-500">No transactions.</td></tr>'}
            </tbody></table>
          </div>
        </div>
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Reconcile</h3>
          <form id="acctReconForm" class="space-y-1 max-h-64 overflow-y-auto border border-zinc-700 rounded-lg p-2">
            ${(tx.transactions || []).filter((t) => !t.reconciled).map((t) =>
              `<label class="flex items-center gap-2 text-xs py-1 border-b border-zinc-800">
                <input type="checkbox" name="tx" value="${t.id}" />
                <span class="font-mono w-20">${money(t.amount)}</span>
                <span class="text-zinc-400 truncate">${esc(t.description || t.reference)}</span>
              </label>`
            ).join('') || '<p class="text-zinc-500 text-xs p-2">No unreconciled items.</p>'}
          </form>
          <button type="button" id="acctReconBtn" class="mt-2 px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded text-sm" ${selectedBankId ? '' : 'disabled'}>Mark selected reconciled</button>
        </div>
      </div>
    </div>`;
  }

  function bindHandlers() {
    const { api, switchModule, esc, money } = ctx;
    document.querySelectorAll('.acct-bank-pick').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedBankId = parseInt(btn.getAttribute('data-id'), 10);
        switchModule('bank');
      });
    });
    document.getElementById('acctAddBank')?.addEventListener('click', async () => {
      const gl = await api('/api/accounting/gl/accounts');
      const cashAccounts = (gl.accounts || []).filter((a) => a.account_type === 'asset');
      const data = await AD().form({
        title: 'Add bank account',
        fields: [
          { key: 'code', label: 'Bank code', required: true },
          { key: 'name', label: 'Account name', required: true },
          { key: 'currency', label: 'Currency', defaultValue: 'USD' },
          {
            key: 'gl_account_id',
            label: 'G/L cash account',
            type: 'select',
            options: [{ value: '', label: 'Program default (1000)' }].concat(
              cashAccounts.map((a) => ({ value: String(a.id), label: `${a.account_number} — ${a.description}` })),
            ),
          },
        ],
      });
      if (!data) return;
      await api('/api/accounting/bank/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...data,
          gl_account_id: data.gl_account_id ? parseInt(data.gl_account_id, 10) : null,
        }),
      });
      switchModule('bank');
    });
    document.getElementById('acctBankManualTx')?.addEventListener('click', async () => {
      if (!selectedBankId) return;
      const gl = await api('/api/accounting/gl/accounts');
      const offsetOpts = (gl.accounts || []).filter((a) => a.account_type !== 'asset');
      const data = await AD().form({
        title: 'Bank manual entry',
        message: 'Positive = deposit, negative = withdrawal.',
        fields: [
          { key: 'amount', label: 'Amount (+ deposit, − payment)', type: 'number', step: '0.01', required: true },
          { key: 'description', label: 'Description', required: true },
          { key: 'reference', label: 'Reference' },
          { key: 'transaction_date', label: 'Date (YYYY-MM-DD)', defaultValue: new Date().toISOString().slice(0, 10) },
          {
            key: 'post_to_gl',
            label: 'Post to G/L',
            type: 'select',
            defaultValue: '0',
            options: [{ value: '0', label: 'Bank register only' }, { value: '1', label: 'Post cash journal' }],
          },
          {
            key: 'offset_account_id',
            label: 'Offset account (if posting)',
            type: 'select',
            options: [{ value: '', label: 'Default expense/revenue' }].concat(
              offsetOpts.map((a) => ({ value: String(a.id), label: `${a.account_number} — ${a.description}` })),
            ),
          },
        ],
        submitLabel: 'Record',
      });
      if (!data) return;
      try {
        await api('/api/accounting/bank/transactions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            bank_account_id: selectedBankId,
            amount: parseFloat(data.amount),
            description: data.description,
            reference: data.reference,
            transaction_date: data.transaction_date,
            post_to_gl: data.post_to_gl === '1',
            offset_account_id: data.offset_account_id ? parseInt(data.offset_account_id, 10) : undefined,
          }),
        });
        switchModule('bank');
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });
    document.getElementById('acctReconBtn')?.addEventListener('click', async () => {
      if (!selectedBankId) return;
      const ids = [...document.querySelectorAll('#acctReconForm input[name=tx]:checked')].map((el) => parseInt(el.value, 10));
      try {
        await api('/api/accounting/bank/reconcile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ bank_account_id: selectedBankId, transaction_ids: ids }),
        });
        switchModule('bank');
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });
  }

  global.CasePMAcctBankUI = {
    init(context) {
      ctx = context;
    },
    render,
    bindHandlers,
    agingBucketsHtml,
  };
})(window);
