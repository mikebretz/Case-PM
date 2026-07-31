/**
 * G/L, A/P, A/R advanced features (budgets, recurring, 1099, dunning, etc.)
 */
(function (global) {
  'use strict';

  let ctx = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  function formatSubledgerTieOut(sub, money) {
    const ap = sub?.ap || {};
    const ar = sub?.ar || {};
    const apOk = Math.abs(ap.difference || 0) < 0.02;
    const arOk = Math.abs(ar.difference || 0) < 0.02;
    return `<div class="space-y-2 text-xs text-zinc-300">
      <p class="text-zinc-500">Compares G/L control accounts to open A/P and A/R subledger balances (Sage-style tie-out).</p>
      <div class="grid sm:grid-cols-2 gap-2">
        <div class="border border-zinc-700 rounded p-2 ${apOk ? 'border-emerald-900/50' : 'border-amber-700'}">
          <div class="text-zinc-400">A/P · acct ${ap.gl_account || '—'}</div>
          <div>G/L balance: <span class="font-mono">${money(ap.gl_balance)}</span></div>
          <div>Open subledger: <span class="font-mono">${money(ap.subledger_open)}</span></div>
          <div class="${apOk ? 'text-emerald-400' : 'text-amber-400'}">${apOk ? 'In balance' : `Difference ${money(ap.difference)}`}</div>
        </div>
        <div class="border border-zinc-700 rounded p-2 ${arOk ? 'border-emerald-900/50' : 'border-amber-700'}">
          <div class="text-zinc-400">A/R · acct ${ar.gl_account || '—'}</div>
          <div>G/L balance: <span class="font-mono">${money(ar.gl_balance)}</span></div>
          <div>Open subledger: <span class="font-mono">${money(ar.subledger_open)}</span></div>
          <div class="${arOk ? 'text-emerald-400' : 'text-amber-400'}">${arOk ? 'In balance' : `Difference ${money(ar.difference)}`}</div>
        </div>
      </div>
    </div>`;
  }

  async function glExtrasHtml() {
    const { api, esc } = ctx;
    const results = await Promise.allSettled([
      api('/api/accounting/gl/budgets'),
      api('/api/accounting/gl/recurring-journals'),
      api('/api/accounting/gl/allocations'),
      api('/api/accounting/gl/intercompany'),
    ]);
    const budgets = results[0].status === 'fulfilled' ? results[0].value : { budgets: [] };
    const recurring = results[1].status === 'fulfilled' ? results[1].value : { recurring: [] };
    const alloc = results[2].status === 'fulfilled' ? results[2].value : { templates: [] };
    const ic = results[3].status === 'fulfilled' ? results[3].value : { entries: [] };
    const extrasFailed = results.some((r) => r.status === 'rejected');
    return `<section class="border border-zinc-700 rounded-lg p-4 space-y-4">
      <h3 class="text-sm font-semibold text-white">Advanced G/L</h3>
      <div class="flex flex-wrap gap-2 text-xs">
        <button type="button" id="acctGlNewBudget" class="px-2 py-1 border border-zinc-600 rounded text-emerald-400">+ Budget</button>
        <button type="button" id="acctGlNewRecurring" class="px-2 py-1 border border-zinc-600 rounded text-sky-400">+ Recurring journal</button>
        <button type="button" id="acctGlNewAlloc" class="px-2 py-1 border border-zinc-600 rounded text-violet-400">+ Allocation template</button>
        <button type="button" id="acctGlNewIc" class="px-2 py-1 border border-zinc-600 rounded text-amber-400">+ Intercompany</button>
        <button type="button" id="acctGlRefreshSub" class="px-2 py-1 border border-zinc-600 rounded text-zinc-300">Subledger tie-out</button>
        <button type="button" id="acctGlBudgetGrid" class="px-2 py-1 border border-zinc-600 rounded text-emerald-300">Budget grid</button>
        <button type="button" id="acctGlFxRate" class="px-2 py-1 border border-zinc-600 rounded text-cyan-400">FX rate</button>
        <button type="button" id="acctGlReval" class="px-2 py-1 border border-zinc-600 rounded text-cyan-300">Run revaluation</button>
        <button type="button" id="acctGlRunDue" class="px-2 py-1 border border-zinc-600 rounded text-zinc-300">Run due recurring</button>
        <button type="button" id="acctGlBudgetCompare" class="px-2 py-1 border border-zinc-600 rounded text-emerald-200">Compare budgets</button>
      </div>
      <p class="text-[11px] text-zinc-600">Subledger tie-out: click the button above to compare control accounts to open A/P and A/R.</p>
      ${extrasFailed ? '<p class="text-[11px] text-amber-500">Some advanced G/L data could not be loaded — refresh the page after a moment or check server logs.</p>' : ''}
      <div id="acctGlSubOut" class="hidden"></div>
      <div id="acctGlBudgetGridHost" class="mt-2"></div>
      <div class="grid md:grid-cols-3 gap-2 text-xs">
        <div><div class="text-zinc-500 mb-1">Budgets (${(budgets.budgets || []).length})</div>
          ${(budgets.budgets || []).slice(0, 3).map((b) => `<div class="flex justify-between gap-2 text-zinc-300"><span>${esc(b.name)} · FY${b.fiscal_year}</span>
            <button type="button" class="acct-gl-open-budget text-emerald-400 bg-transparent border-none cursor-pointer" data-id="${b.id}">Grid</button></div>`).join('') || '<div class="text-zinc-600">None</div>'}
        </div>
        <div><div class="text-zinc-500 mb-1">Recurring (${(recurring.recurring || []).length})</div>
          ${(recurring.recurring || []).slice(0, 3).map((r) => `<div class="flex justify-between gap-2"><span>${esc(r.code)}</span>
            ${r.is_active ? `<button type="button" class="acct-gl-run-rj text-emerald-400 bg-transparent border-none cursor-pointer" data-id="${r.id}">Run</button>` : ''}</div>`).join('') || '<div class="text-zinc-600">None</div>'}
        </div>
        <div><div class="text-zinc-500 mb-1">Allocations (${(alloc.templates || []).length})</div>
          ${(alloc.templates || []).slice(0, 3).map((t) => `<div class="flex justify-between"><span>${esc(t.code)}</span>
            <button type="button" class="acct-gl-run-alloc text-violet-400 bg-transparent border-none cursor-pointer" data-id="${t.id}">Run</button></div>`).join('') || '<div class="text-zinc-600">None</div>'}
        </div>
      </div>
      <div class="text-xs text-zinc-500">Open IC entries: ${(ic.entries || []).filter((e) => e.status === 'Open').length}
        ${(ic.entries || []).filter((e) => e.status === 'Open').slice(0, 2).map((e) =>
          `<button type="button" class="acct-gl-post-ic ml-2 text-amber-400 bg-transparent border-none cursor-pointer" data-id="${e.id}">Post ${esc(e.entry_number)}</button>`
        ).join('')}
      </div>
    </section>`;
  }

  async function apExtrasHtml() {
    const { api, esc, money } = ctx;
    const [groups, recurring, report] = await Promise.all([
      api('/api/accounting/ap/vendor-groups'),
      api('/api/accounting/ap/recurring-payables'),
      api(`/api/accounting/ap/reports/1099?year=${new Date().getFullYear()}`),
    ]);
    return `<section class="border border-zinc-700 rounded-lg p-4 space-y-3">
      <h3 class="text-sm font-semibold text-white">Advanced A/P</h3>
      <div class="flex flex-wrap gap-2 text-xs">
        <button type="button" id="acctApVendorGroup" class="px-2 py-1 border border-zinc-600 rounded text-emerald-400">+ Vendor group</button>
        <button type="button" id="acctApRecurring" class="px-2 py-1 border border-zinc-600 rounded text-sky-400">+ Recurring payable</button>
        <button type="button" id="acctAp1099" class="px-2 py-1 border border-zinc-600 rounded text-violet-400">1099 preview</button>
        <button type="button" id="acctApVendorActivity" class="px-2 py-1 border border-zinc-600 rounded text-amber-400">Vendor activity</button>
        <button type="button" id="acctApNacha" class="px-2 py-1 border border-zinc-600 rounded text-sky-300">EFT / NACHA</button>
        <button type="button" id="acctApMatchTol" class="px-2 py-1 border border-zinc-600 rounded text-zinc-300">Match tolerance</button>
        <button type="button" id="acctAp1099Efile" class="px-2 py-1 border border-zinc-600 rounded text-violet-300">1099 e-file</button>
        <button type="button" id="acctAp1099Print" class="px-2 py-1 border border-zinc-600 rounded text-violet-200">Print 1099</button>
        <button type="button" id="acctApMatchBench" class="px-2 py-1 border border-zinc-600 rounded text-amber-300">Match workbench</button>
        <button type="button" id="acctApWithhold" class="px-2 py-1 border border-zinc-600 rounded text-red-300">Withholding rules</button>
      </div>
      <div id="acctApVendorActOut" class="text-xs max-h-40 overflow-auto border border-zinc-800 rounded p-2 hidden"></div>
      <div class="text-xs text-zinc-500">Vendor groups: ${(groups.groups || []).length} · Recurring: ${(recurring.recurring || []).length}</div>
      <div class="text-xs text-zinc-400">1099 vendors (YTD): ${(report.vendors || []).length}</div>
      <p class="text-[10px] text-zinc-600">Invoices: use gross + retainage/withhold % on create. Match PO via three-way on open invoice row (API).</p>
    </section>`;
  }

  async function arExtrasHtml() {
    const { api, esc } = ctx;
    const [groups, overdue, batches] = await Promise.all([
      api('/api/accounting/ar/customer-groups'),
      api('/api/accounting/ar/dunning/overdue'),
      api('/api/accounting/ar/receipt-batches'),
    ]);
    return `<section class="border border-zinc-700 rounded-lg p-4 space-y-3">
      <h3 class="text-sm font-semibold text-white">Advanced A/R</h3>
      <div class="flex flex-wrap gap-2 text-xs">
        <button type="button" id="acctArCustGroup" class="px-2 py-1 border border-zinc-600 rounded text-emerald-400">+ Customer group</button>
        <button type="button" id="acctArMemo" class="px-2 py-1 border border-zinc-600 rounded text-sky-400">Credit/debit memo</button>
        <button type="button" id="acctArRecurring" class="px-2 py-1 border border-zinc-600 rounded text-violet-400">+ Recurring invoice</button>
        <button type="button" id="acctArReceiptBatch" class="px-2 py-1 border border-zinc-600 rounded text-amber-400">+ Receipt batch</button>
        <button type="button" id="acctArDunning" class="px-2 py-1 border border-zinc-600 rounded text-red-400">Dunning (30+ days)</button>
        <button type="button" id="acctArStmtPrint" class="px-2 py-1 border border-zinc-600 rounded text-zinc-300">Print statement</button>
        <button type="button" id="acctArDunningRules" class="px-2 py-1 border border-zinc-600 rounded text-orange-400">Dunning rules</button>
        <button type="button" id="acctArCashApp" class="px-2 py-1 border border-zinc-600 rounded text-emerald-300">Cash application</button>
        <button type="button" id="acctArDunningSmtp" class="px-2 py-1 border border-zinc-600 rounded text-orange-300">SMTP dunning run</button>
      </div>
      <div class="text-xs text-zinc-500">Customer groups: ${(groups.groups || []).length} · Overdue for dunning: ${(overdue.customers || []).length} · Receipt batches: ${(batches.batches || []).length}</div>
    </section>`;
  }

  function bindGlExtras() {
    const { api, switchModule, money } = ctx;
    document.getElementById('acctGlRefreshSub')?.addEventListener('click', async () => {
      const sub = await api('/api/accounting/gl/subledger-reconcile');
      const el = document.getElementById('acctGlSubOut');
      if (el) {
        el.classList.remove('hidden');
        el.innerHTML = formatSubledgerTieOut(sub, money);
      }
    });
    document.getElementById('acctGlNewBudget')?.addEventListener('click', async () => {
      const gl = await api('/api/accounting/gl/accounts');
      const accounts = gl.accounts || [];
      const data = await AD().form({
        title: 'Budget header',
        fields: [
          { key: 'name', label: 'Budget name', required: true },
          { key: 'fiscal_year', label: 'Fiscal year', defaultValue: String(new Date().getFullYear()) },
          { key: 'account_id', label: 'Sample account', type: 'select', required: true, options: accounts.map((a) => ({ value: String(a.id), label: `${a.account_number} — ${a.description}` })) },
          { key: 'period_key', label: 'Period YYYY-MM', defaultValue: new Date().toISOString().slice(0, 7) },
          { key: 'amount', label: 'Budget amount', defaultValue: '0' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/gl/budgets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: data.name,
          fiscal_year: parseInt(data.fiscal_year, 10),
          lines: [{ account_id: parseInt(data.account_id, 10), period_key: data.period_key, amount: parseFloat(data.amount) || 0 }],
        }),
      });
      switchModule('gl');
    });
    document.getElementById('acctGlNewRecurring')?.addEventListener('click', async () => {
      const gl = await api('/api/accounting/gl/accounts');
      const accts = gl.accounts || [];
      if (accts.length < 2) return;
      const data = await AD().form({
        title: 'Recurring journal',
        fields: [
          { key: 'code', label: 'Code', defaultValue: 'RJ-01' },
          { key: 'description', label: 'Description' },
          { key: 'next_run_date', label: 'Next run', type: 'date', defaultValue: new Date().toISOString().slice(0, 10) },
          { key: 'amount', label: 'Amount', defaultValue: '100' },
        ],
      });
      if (!data) return;
      const amt = parseFloat(data.amount) || 0;
      await api('/api/accounting/gl/recurring-journals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: data.code,
          description: data.description,
          next_run_date: data.next_run_date,
          lines: [
            { account_id: accts[0].id, debit: amt, credit: 0 },
            { account_id: accts[1].id, debit: 0, credit: amt },
          ],
        }),
      });
      switchModule('gl');
    });
    document.querySelectorAll('.acct-gl-run-rj').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api(`/api/accounting/gl/recurring-journals/${btn.getAttribute('data-id')}/run`, { method: 'POST' });
        switchModule('gl');
      });
    });
    document.getElementById('acctGlNewAlloc')?.addEventListener('click', async () => {
      const gl = await api('/api/accounting/gl/accounts');
      const accts = gl.accounts || [];
      const data = await AD().form({
        title: 'Allocation template',
        fields: [
          { key: 'code', label: 'Code', defaultValue: 'ALLOC-01' },
          { key: 'pool_account_id', label: 'Pool (credit) account', type: 'select', options: accts.map((a) => ({ value: String(a.id), label: a.account_number })) },
          { key: 'target_account_id', label: 'Target (debit) account', type: 'select', options: accts.map((a) => ({ value: String(a.id), label: a.account_number })) },
        ],
      });
      if (!data) return;
      await api('/api/accounting/gl/allocations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: data.code,
          pool_account_id: parseInt(data.pool_account_id, 10),
          lines: [{ account_id: parseInt(data.target_account_id, 10), percent: 100 }],
        }),
      });
      switchModule('gl');
    });
    document.querySelectorAll('.acct-gl-run-alloc').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const amt = await AD().form({ title: 'Allocation amount', fields: [{ key: 'amount', label: 'Amount', required: true }] });
        if (!amt) return;
        await api(`/api/accounting/gl/allocations/${btn.getAttribute('data-id')}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ amount: parseFloat(amt.amount) }),
        });
        switchModule('gl');
      });
    });
    document.getElementById('acctGlNewIc')?.addEventListener('click', async () => {
      const gl = await api('/api/accounting/gl/accounts');
      const accts = gl.accounts || [];
      const data = await AD().form({
        title: 'Intercompany entry',
        fields: [
          { key: 'amount', label: 'Amount', required: true },
          { key: 'from_account_id', label: 'Debit account', type: 'select', options: accts.map((a) => ({ value: String(a.id), label: a.account_number })) },
          { key: 'to_account_id', label: 'Credit account', type: 'select', options: accts.map((a) => ({ value: String(a.id), label: a.account_number })) },
        ],
      });
      if (!data) return;
      await api('/api/accounting/gl/intercompany', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          amount: parseFloat(data.amount),
          from_account_id: parseInt(data.from_account_id, 10),
          to_account_id: parseInt(data.to_account_id, 10),
        }),
      });
      switchModule('gl');
    });
    document.querySelectorAll('.acct-gl-post-ic').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api(`/api/accounting/gl/intercompany/${btn.getAttribute('data-id')}/post`, { method: 'POST' });
        switchModule('gl');
      });
    });

    document.getElementById('acctGlBudgetGrid')?.addEventListener('click', async () => {
      const budgets = await api('/api/accounting/gl/budgets');
      const b = (budgets.budgets || [])[0];
      if (!b) {
        await AD().alert('Create a budget first.', 'warning');
        return;
      }
      openBudgetGrid(b.id);
    });
    document.querySelectorAll('.acct-gl-open-budget').forEach((btn) => {
      btn.addEventListener('click', () => openBudgetGrid(parseInt(btn.getAttribute('data-id'), 10)));
    });

    async function openBudgetGrid(budgetId) {
      const { esc, api, switchModule } = ctx;
      const grid = await api(`/api/accounting/gl/budgets/${budgetId}/grid`);
      const periods = grid.periods || [];
      const rows = (grid.rows || []).slice(0, 20);
      const host = document.getElementById('acctGlBudgetGridHost');
      if (!host) return;
      const header = periods.map((p) => `<th class="px-1 text-right">${esc(p)}</th>`).join('');
      host.innerHTML = `<div class="mb-2 text-zinc-300 font-medium">Budget grid: ${esc(grid.budget?.name || '')}</div>
        <div class="overflow-auto max-h-64"><table class="text-xs w-full"><thead><tr><th>Acct</th>${header}</tr></thead><tbody>
        ${rows.map((r) => `<tr><td class="font-mono pr-2">${esc(r.account_number)}</td>
          ${periods.map((p) => `<td class="text-right"><input type="number" step="0.01" class="acct-bud-cell w-14 bg-zinc-900 border border-zinc-700 rounded" data-aid="${r.account_id}" data-pk="${esc(p)}" value="${r.periods[p] || 0}"></td>`).join('')}
        </tr>`).join('')}
        </tbody></table></div>
        <button type="button" id="acctGlSaveBudgetGrid" class="mt-2 text-xs text-emerald-400">Save budget grid</button>`;
      document.getElementById('acctGlSaveBudgetGrid')?.addEventListener('click', async () => {
        const cells = [];
        host.querySelectorAll('.acct-bud-cell').forEach((inp) => {
          cells.push({
            account_id: parseInt(inp.getAttribute('data-aid'), 10),
            period_key: inp.getAttribute('data-pk'),
            amount: parseFloat(inp.value) || 0,
          });
        });
        await api(`/api/accounting/gl/budgets/${budgetId}/grid`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cells }),
        });
        switchModule('gl');
      });
    }

    document.getElementById('acctGlFxRate')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Exchange rate',
        fields: [
          { key: 'currency_code', label: 'Currency', defaultValue: 'EUR' },
          { key: 'rate_date', label: 'Date', type: 'date', defaultValue: new Date().toISOString().slice(0, 10) },
          { key: 'rate_to_functional', label: 'Rate to functional currency', defaultValue: '1.08' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/gl/currency-rates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      switchModule('gl');
    });

    document.getElementById('acctGlReval')?.addEventListener('click', async () => {
      if (!await AD().confirm({ title: 'Run revaluation?', message: 'Posts FX adjustment journal.' })) return;
      try {
        await api('/api/accounting/gl/revaluation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ period_end: new Date().toISOString().slice(0, 10) }),
        });
        switchModule('gl');
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });

    document.getElementById('acctGlRunDue')?.addEventListener('click', async () => {
      try {
        const r = await api('/api/accounting/gl/recurring-journals/run-due', { method: 'POST' });
        await AD().alert(`Ran ${(r.runs || []).length} recurring journal(s).`, 'info');
        switchModule('gl');
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });

    document.getElementById('acctGlBudgetCompare')?.addEventListener('click', async () => {
      const budgets = await api('/api/accounting/gl/budgets');
      const ids = (budgets.budgets || []).slice(0, 3).map((b) => b.id);
      if (!ids.length) {
        await AD().alert('Create at least one budget first.', 'warning');
        return;
      }
      const cmp = await api(`/api/accounting/gl/budgets/compare?ids=${ids.join(',')}`);
      await AD().alert((cmp.budgets || []).map((b) => `${b.name}: ${b.total}`).join('\n'), 'info');
    });
  }

  function bindApExtras() {
    const { api, switchModule } = ctx;
    document.getElementById('acctApVendorGroup')?.addEventListener('click', async () => {
      const data = await AD().form({ title: 'Vendor group', fields: [{ key: 'code', label: 'Code', required: true }, { key: 'name', label: 'Name', required: true }] });
      if (!data) return;
      await api('/api/accounting/ap/vendor-groups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      switchModule('ap');
    });
    document.getElementById('acctApRecurring')?.addEventListener('click', async () => {
      const vendors = await api('/api/accounting/ap/vendors');
      const data = await AD().form({
        title: 'Recurring payable',
        fields: [
          { key: 'vendor_id', label: 'Vendor', type: 'select', required: true, options: (vendors.vendors || []).map((v) => ({ value: String(v.id), label: `${v.code} — ${v.name}` })) },
          { key: 'amount', label: 'Amount', required: true },
          { key: 'next_run_date', label: 'Next run', type: 'date', defaultValue: new Date().toISOString().slice(0, 10) },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ap/recurring-payables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor_id: parseInt(data.vendor_id, 10), amount: parseFloat(data.amount), next_run_date: data.next_run_date }),
      });
      switchModule('ap');
    });
    document.getElementById('acctAp1099')?.addEventListener('click', async () => {
      const r = await api(`/api/accounting/ap/reports/1099?year=${new Date().getFullYear()}`);
      await AD().alert(`1099 preview: ${(r.vendors || []).length} vendor(s) with payments.`, 'info');
    });

    document.getElementById('acctApVendorActivity')?.addEventListener('click', async () => {
      const { esc, money } = ctx;
      const r = await api('/api/accounting/ap/reports/vendor-activity');
      const out = document.getElementById('acctApVendorActOut');
      if (!out) return;
      out.classList.remove('hidden');
      out.innerHTML = `<table class="w-full text-xs"><thead><tr><th class="text-left">Vendor</th><th class="text-right">Billed</th><th class="text-right">Paid</th><th class="text-right">Open</th><th></th></tr></thead><tbody>
        ${(r.vendors || []).map((v) => `<tr class="border-t border-zinc-800"><td>${esc(v.code)} ${esc(v.name)}</td>
          <td class="text-right">${money(v.billed)}</td><td class="text-right">${money(v.paid)}</td><td class="text-right">${money(v.open)}</td>
          <td><button type="button" class="acct-ap-vend-det text-sky-400 bg-transparent border-none cursor-pointer" data-id="${v.vendor_id}">Detail</button></td></tr>`).join('')}
        </tbody></table>`;
      out.querySelectorAll('.acct-ap-vend-det').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const det = await api(`/api/accounting/ap/vendors/${btn.getAttribute('data-id')}/activity`);
          await AD().alert(`Invoices: ${(det.invoices || []).length}, Payments: ${(det.payments || []).length}`, 'info');
        });
      });
    });

    document.getElementById('acctApNacha')?.addEventListener('click', async () => {
      const pays = await api('/api/accounting/ap/payments');
      const posted = (pays.payments || []).filter((p) => p.status === 'Posted').slice(0, 10);
      if (!posted.length) {
        await AD().alert('No posted payments for NACHA export.', 'warning');
        return;
      }
      const ids = posted.map((p) => p.id);
      const res = await fetch('/api/accounting/ap/payments/nacha', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_ids: ids }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        await AD().alert(j.error || res.statusText, 'error');
        return;
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'ap-disbursement.ach';
      a.click();
    });

    document.getElementById('acctApMatchTol')?.addEventListener('click', async () => {
      const cur = await api('/api/accounting/ap/match-tolerance');
      const data = await AD().form({
        title: '3-way match tolerance',
        fields: [
          { key: 'amount_tolerance', label: 'Amount ($)', defaultValue: String(cur.amount_tolerance ?? 1) },
          { key: 'percent_tolerance', label: 'Percent', defaultValue: String(cur.percent_tolerance ?? 5) },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ap/match-tolerance', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          amount_tolerance: parseFloat(data.amount_tolerance),
          percent_tolerance: parseFloat(data.percent_tolerance),
        }),
      });
      switchModule('ap');
    });

    document.getElementById('acctAp1099Efile')?.addEventListener('click', async () => {
      const r = await api(`/api/accounting/ap/1099/efile?tax_year=${new Date().getFullYear() - 1}`);
      await AD().alert(`E-file stub: ${r.vendor_count} vendor(s). Copy from API response if needed.`, 'info');
    });

    document.getElementById('acctAp1099Print')?.addEventListener('click', () => {
      global.open(`/api/accounting/ap/reports/1099/print?tax_year=${new Date().getFullYear() - 1}`, '_blank');
    });

    document.getElementById('acctApMatchBench')?.addEventListener('click', async () => {
      const wb = await api('/api/accounting/ap/match-workbench');
      await AD().alert(`${(wb.exceptions || []).length} match exception(s) of ${(wb.all || []).length} invoice(s).`, 'info');
    });

    document.getElementById('acctApWithhold')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Withholding rule',
        fields: [
          { key: 'name', label: 'Name', defaultValue: 'Default withhold' },
          { key: 'withhold_percent', label: 'Percent', defaultValue: '10' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ap/withholding-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: data.name, withhold_percent: parseFloat(data.withhold_percent) }),
      });
      switchModule('ap');
    });
  }

  function bindArExtras() {
    const { api, switchModule } = ctx;
    document.getElementById('acctArCustGroup')?.addEventListener('click', async () => {
      const data = await AD().form({ title: 'Customer group', fields: [{ key: 'code', label: 'Code', required: true }, { key: 'name', label: 'Name', required: true }] });
      if (!data) return;
      await api('/api/accounting/ar/customer-groups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      switchModule('ar');
    });
    document.getElementById('acctArMemo')?.addEventListener('click', async () => {
      const customers = await api('/api/accounting/ar/customers');
      const data = await AD().form({
        title: 'AR memo',
        fields: [
          { key: 'customer_id', label: 'Customer', type: 'select', required: true, options: (customers.customers || []).map((c) => ({ value: String(c.id), label: c.name })) },
          { key: 'document_type', label: 'Type', type: 'select', options: [{ value: 'Credit', label: 'Credit' }, { value: 'Debit', label: 'Debit' }] },
          { key: 'amount', label: 'Amount', required: true },
          { key: 'post_gl', label: 'Post to G/L', type: 'checkbox', defaultValue: true },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ar/memos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: parseInt(data.customer_id, 10),
          document_type: data.document_type,
          amount: parseFloat(data.amount),
          post_gl: !!data.post_gl,
        }),
      });
      switchModule('ar');
    });
    document.getElementById('acctArRecurring')?.addEventListener('click', async () => {
      const customers = await api('/api/accounting/ar/customers');
      const data = await AD().form({
        title: 'Recurring AR',
        fields: [
          { key: 'customer_id', label: 'Customer', type: 'select', required: true, options: (customers.customers || []).map((c) => ({ value: String(c.id), label: c.name })) },
          { key: 'amount', label: 'Amount', required: true },
          { key: 'next_run_date', label: 'Next run', type: 'date', defaultValue: new Date().toISOString().slice(0, 10) },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ar/recurring-invoices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: parseInt(data.customer_id, 10), amount: parseFloat(data.amount), next_run_date: data.next_run_date }),
      });
      switchModule('ar');
    });
    document.getElementById('acctArReceiptBatch')?.addEventListener('click', async () => {
      const [customers, invoices] = await Promise.all([api('/api/accounting/ar/customers'), api('/api/accounting/ar/invoices')]);
      const open = (invoices.invoices || []).filter((i) => i.status === 'Open' || i.status === 'Partial');
      if (!open[0]) {
        await AD().alert('No open invoices for receipt batch.', 'warning');
        return;
      }
      const inv = open[0];
      const openAmt = (parseFloat(inv.amount) || 0) - (parseFloat(inv.amount_paid) || 0);
      const batch = await api('/api/accounting/ar/receipt-batches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          batch_date: new Date().toISOString().slice(0, 10),
          lines: [{ customer_id: inv.customer_id, ar_document_id: inv.id, amount: openAmt }],
        }),
      });
      await api(`/api/accounting/ar/receipt-batches/${batch.batch.id}/post`, { method: 'POST' });
      switchModule('ar');
    });
    document.getElementById('acctArDunning')?.addEventListener('click', async () => {
      const overdue = await api('/api/accounting/ar/dunning/overdue');
      const list = overdue.customers || [];
      if (!list[0]) {
        await AD().alert('No customers 30+ days overdue.', 'info');
        return;
      }
      const c = list[0];
      const out = await api('/api/accounting/ar/dunning/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: c.customer_id, level: c.suggested_dunning_level }),
      });
      if (out.mailto) {
        global.open(out.mailto, '_blank');
      } else {
        await AD().alert(out.body || 'Dunning logged (no customer email on file).', 'info');
      }
      switchModule('ar');
    });

    document.getElementById('acctArStmtPrint')?.addEventListener('click', async () => {
      const customers = await api('/api/accounting/ar/customers');
      const list = customers.customers || [];
      if (!list[0]) {
        await AD().alert('Add a customer first.', 'warning');
        return;
      }
      const pick = await AD().select({
        title: 'Print statement',
        items: list.map((c) => ({ value: String(c.id), label: `${c.code} — ${c.name}` })),
      });
      if (!pick) return;
      global.open(`/api/accounting/ar/customers/${pick.value}/statement/print`, '_blank');
    });

    document.getElementById('acctArDunningRules')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Dunning rule',
        fields: [
          { key: 'days_past_due', label: 'Days past due', defaultValue: '30', required: true },
          { key: 'letter_code', label: 'Letter code', defaultValue: 'L1' },
          { key: 'message_template', label: 'Message template (optional)' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ar/dunning/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          days_past_due: parseInt(data.days_past_due, 10),
          letter_code: data.letter_code,
          message_template: data.message_template,
        }),
      });
      switchModule('ar');
    });

    document.getElementById('acctArCashApp')?.addEventListener('click', async () => {
      const customers = await api('/api/accounting/ar/customers');
      const list = customers.customers || [];
      if (!list[0]) {
        await AD().alert('Add a customer first.', 'warning');
        return;
      }
      const pick = await AD().select({
        title: 'Cash application',
        items: list.map((c) => ({ value: String(c.id), label: `${c.code} — ${c.name}` })),
      });
      if (!pick) return;
      const wb = await api(`/api/accounting/ar/cash-application/${pick.value}`);
      const inv = (wb.open_invoices || [])[0];
      const rcpt = (wb.unapplied_receipts || [])[0];
      if (!inv || !rcpt) {
        await AD().alert('Need an open invoice and unapplied receipt for this customer.', 'warning');
        return;
      }
      const amt = Math.min(inv.open_amount, rcpt.unapplied_amount);
      await api('/api/accounting/ar/cash-application/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receipt_id: rcpt.receipt_id,
          applications: [{ ar_document_id: inv.ar_document_id, amount: amt }],
        }),
      });
      switchModule('ar');
    });

    document.getElementById('acctArDunningSmtp')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/ar/dunning/run-auto', { method: 'POST' });
      await AD().alert(`Processed ${r.processed || 0} dunning notice(s) via SMTP when configured.`, 'info');
      switchModule('ar');
    });
  }

  global.CasePMAcctGlApArExt = {
    init(c) {
      ctx = c;
    },
    glExtrasHtml,
    apExtrasHtml,
    arExtrasHtml,
    bindGlExtras,
    bindApExtras,
    bindArExtras,
  };
})(typeof window !== 'undefined' ? window : global);
