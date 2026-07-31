/**
 * G/L Consolidation — entity tree, consolidated trial balance, elimination runs.
 */
(function (global) {
  'use strict';

  let ctx = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  async function render() {
    const { api, esc, money } = ctx;
    const [tree, runs, ctb, ownership, finBs, finPl] = await Promise.all([
      api('/api/accounting/consolidation/ledgers'),
      api('/api/accounting/consolidation/runs'),
      api('/api/accounting/consolidation/trial-balance'),
      api('/api/accounting/consolidation/ownership'),
      api('/api/accounting/consolidation/financials?statement=balance_sheet'),
      api('/api/accounting/consolidation/financials?statement=income_statement'),
    ]);
    const rows = (ctb.rows || []).filter((r) => Math.abs(r.debit) > 0.01 || Math.abs(r.credit) > 0.01);

    function renderTree(nodes, depth) {
      return (nodes || []).map((n) => {
        const L = n.ledger || n;
        const kids = n.children || [];
        return `<div class="ml-${Math.min(depth * 3, 12)} border-l border-zinc-800 pl-2 py-1 text-xs">
          <span class="font-mono text-emerald-400">${esc(L.code)}</span>
          <span class="text-zinc-300 ml-2">${esc(L.name)}</span>
          ${kids.length ? renderTree(kids, depth + 1) : ''}
        </div>`;
      }).join('');
    }

    return `<div class="space-y-6">
      <div class="flex flex-wrap justify-between gap-2 items-start">
        <div>
          <h2 class="text-lg font-semibold text-white">G/L Consolidation</h2>
          <p class="text-xs text-zinc-500 mt-1">Subsidiary ledgers, consolidated trial balance, elimination journal entries.</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" id="acctConAddLedger" class="text-xs px-3 py-2 border border-zinc-700 rounded-md text-emerald-400">+ Subsidiary ledger</button>
          <button type="button" id="acctConNewRun" class="text-xs px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded-md text-white">+ Consolidation run</button>
          <button type="button" id="acctConRefreshTb" class="text-xs px-3 py-2 border border-zinc-700 rounded-md text-zinc-300">Refresh roll-up</button>
          <button type="button" id="acctConLockPeriod" class="text-xs px-3 py-2 border border-zinc-700 rounded-md text-amber-400">Lock period</button>
        </div>
      </div>

      <div class="grid lg:grid-cols-2 gap-4">
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Entity structure</h3>
          <div class="border border-zinc-700 rounded-lg p-3 bg-zinc-900/40 max-h-40 overflow-y-auto">
            ${renderTree(tree.tree || [], 0) || '<p class="text-zinc-500 text-xs">Primary ledger only — add subsidiaries.</p>'}
          </div>
          <p class="text-[10px] text-zinc-600 mt-1">${(tree.ledgers || []).length} active ledger(s)</p>
        </div>
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Consolidation runs</h3>
          <div class="border border-zinc-700 rounded-lg divide-y divide-zinc-800 text-xs max-h-40 overflow-y-auto">
            ${(runs.runs || []).map((r) => `<div class="p-2 flex justify-between items-center">
              <div>
                <span class="font-mono text-violet-400">${esc(r.run_number)}</span>
                <span class="text-zinc-500 ml-2">${esc(r.period_end)} · ${esc(r.status)}</span>
              </div>
              ${r.status === 'Open' ? `<span>
                <button type="button" class="acct-con-suggest text-sky-400 bg-transparent border-none cursor-pointer mr-2" data-id="${r.id}">Suggest elim.</button>
                <button type="button" class="acct-con-rollup text-violet-400 bg-transparent border-none cursor-pointer mr-2" data-id="${r.id}">Rollup</button>
                <button type="button" class="acct-con-elim text-emerald-400 bg-transparent border-none cursor-pointer" data-id="${r.id}">Post eliminations</button>
              </span>` : `<span class="text-zinc-600">JE ${esc(r.elimination_batch_id || '—')}</span>`}
            </div>`).join('') || '<p class="p-3 text-zinc-500">No runs yet.</p>'}
          </div>
        </div>
      </div>

      <div class="grid lg:grid-cols-2 gap-4">
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Consolidated balance sheet (roll-up)</h3>
          <p class="text-xs text-zinc-600 mb-1">${(finBs.rows || []).length} account(s) · ownership: ${(ownership.ownership || []).length}</p>
          <div class="border border-zinc-700 rounded-lg max-h-32 overflow-y-auto text-xs p-2 text-zinc-500">
            ${(finBs.rows || []).slice(0, 8).map((r) => `<div class="flex justify-between"><span class="font-mono">${esc(r.account_number)}</span><span>${money(r.balance)}</span></div>`).join('') || 'No balances'}
          </div>
        </div>
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Consolidated P&amp;L</h3>
          <p class="text-xs text-emerald-400">Net: ${money((finPl.totals || {}).net_income)}</p>
          <div class="border border-zinc-700 rounded-lg max-h-32 overflow-y-auto text-xs p-2 text-zinc-500">
            ${(finPl.rows || []).slice(0, 8).map((r) => `<div class="flex justify-between"><span class="font-mono">${esc(r.account_number)}</span><span>${money(r.balance)}</span></div>`).join('') || 'No P&amp;L activity'}
          </div>
        </div>
      </div>

      <div>
        <h3 class="text-sm text-zinc-400 mb-2">Consolidated trial balance — ${esc(ctb.parent_code || 'MAIN')}</h3>
        <div class="border border-zinc-700 rounded-lg overflow-x-auto max-h-96 overflow-y-auto">
          <table class="w-full text-xs">
            <thead class="bg-zinc-800 sticky top-0 text-zinc-500"><tr>
              <th class="text-left px-2 py-2">Account</th>
              <th class="text-left px-2 py-2">Description</th>
              <th class="text-right px-2 py-2">Debit</th>
              <th class="text-right px-2 py-2">Credit</th>
              <th class="text-right px-2 py-2">Balance</th>
            </tr></thead>
            <tbody>
              ${rows.map((r) => `<tr class="border-t border-zinc-800">
                <td class="px-2 py-1 font-mono">${esc(r.account_number)}</td>
                <td class="px-2 py-1 text-zinc-400">${esc(r.description)}</td>
                <td class="px-2 py-1 text-right font-mono">${money(r.debit)}</td>
                <td class="px-2 py-1 text-right font-mono">${money(r.credit)}</td>
                <td class="px-2 py-1 text-right font-mono">${money(r.balance)}</td>
              </tr>`).join('') || '<tr><td colspan="5" class="p-3 text-zinc-500">No posted activity across entities.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;
  }

  function bindHandlers() {
    const { api, switchModule, esc } = ctx;

    document.getElementById('acctConRefreshTb')?.addEventListener('click', () => switchModule('consolidation'));

    document.getElementById('acctConAddLedger')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Add subsidiary ledger',
        fields: [
          { key: 'code', label: 'Ledger code', required: true, defaultValue: 'SUB01' },
          { key: 'name', label: 'Company name', required: true },
          { key: 'base_currency', label: 'Currency', defaultValue: 'USD' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/consolidation/ledgers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      switchModule('consolidation');
    });

    document.getElementById('acctConNewRun')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'New consolidation run',
        fields: [
          { key: 'period_end', label: 'Period end', type: 'date', defaultValue: new Date().toISOString().slice(0, 10) },
          { key: 'notes', label: 'Notes' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/consolidation/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      switchModule('consolidation');
    });

    document.getElementById('acctConLockPeriod')?.addEventListener('click', async () => {
      const pk = new Date().toISOString().slice(0, 7);
      const data = await AD().form({
        title: 'Lock entity periods',
        fields: [{ key: 'period_key', label: 'Period (YYYY-MM)', defaultValue: pk, required: true }],
      });
      if (!data) return;
      await api('/api/accounting/consolidation/lock-period', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period_key: data.period_key, lock_children: true }),
      });
      switchModule('consolidation');
    });

    document.querySelectorAll('.acct-con-suggest').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const runId = btn.getAttribute('data-id');
        const sug = await api(`/api/accounting/consolidation/runs/${runId}/suggest-eliminations`);
        const lines = sug.suggestions || [];
        if (!lines.length) {
          await AD().alert?.({ title: 'No suggestions', message: 'No intercompany balances matched default due from/to accounts.' });
          return;
        }
        await api(`/api/accounting/consolidation/runs/${runId}/post-eliminations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lines }),
        });
        switchModule('consolidation');
      });
    });

    document.querySelectorAll('.acct-con-rollup').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const runId = btn.getAttribute('data-id');
        await api(`/api/accounting/consolidation/runs/${runId}/rollup`, { method: 'POST' });
        switchModule('consolidation');
      });
    });

    document.querySelectorAll('.acct-con-elim').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const runId = btn.getAttribute('data-id');
        const gl = await api('/api/accounting/gl/accounts');
        const accounts = (gl.accounts || []).filter((a) => a.is_posting);
        const data = await AD().form({
          title: 'Elimination entry (balanced pair)',
          fields: [
            {
              key: 'debit_account',
              label: 'Debit account',
              type: 'select',
              required: true,
              options: accounts.map((a) => ({ value: a.account_number, label: `${a.account_number} — ${a.description}` })),
            },
            {
              key: 'credit_account',
              label: 'Credit account',
              type: 'select',
              required: true,
              options: accounts.map((a) => ({ value: a.account_number, label: `${a.account_number} — ${a.description}` })),
            },
            { key: 'amount', label: 'Amount', required: true, defaultValue: '0' },
            { key: 'description', label: 'Memo', defaultValue: 'Intercompany elimination' },
          ],
        });
        if (!data) return;
        const amt = parseFloat(data.amount) || 0;
        if (amt <= 0) return;
        await api(`/api/accounting/consolidation/runs/${runId}/post-eliminations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lines: [
              { account_number: data.debit_account, debit: amt, credit: 0, description: data.description },
              { account_number: data.credit_account, debit: 0, credit: amt, description: data.description },
            ],
          }),
        });
        switchModule('consolidation');
      });
    });
  }

  global.CasePMAcctConsolidationUI = {
    init(c) {
      ctx = c;
    },
    render,
    bindHandlers,
  };
})(typeof window !== 'undefined' ? window : global);
