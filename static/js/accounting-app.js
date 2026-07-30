/**
 * Case PM built-in accounting suite (standalone ERP).
 */
(function (global) {
  'use strict';

  let catalog = null;
  let dashboard = null;
  let activeModule = 'dashboard';

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  async function api(path, options) {
    const res = await fetch(path, { credentials: 'same-origin', ...(options || {}) });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || res.statusText);
    return json;
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function money(n) {
    const v = parseFloat(n) || 0;
    return v.toLocaleString(undefined, { style: 'currency', currency: 'USD' });
  }

  function statusClass(st) {
    if (st === 'live') return 'status-live';
    if (st === 'beta') return 'status-beta';
    return 'status-planned';
  }

  function buildNav() {
    const mods = [{ id: 'dashboard', name: 'Dashboard', route: 'dashboard', status: 'live' }];
    (catalog?.modules || []).forEach((m) => mods.push(m));
    const nav = document.getElementById('acctModuleNav');
    const mob = document.getElementById('acctModuleNavMobile');
    const html = mods.map((m) => {
      const route = m.route || m.id;
      return `<button type="button" class="acct-nav-btn ${activeModule === route ? 'active' : ''}" data-route="${esc(route)}">
        <span class="${statusClass(m.status)} mr-1">●</span>${esc(m.name)}
      </button>`;
    }).join('');
    if (nav) nav.innerHTML = html;
    if (mob) mob.innerHTML = mods.map((m) => {
      const route = m.route || m.id;
      return `<button type="button" class="acct-nav-btn whitespace-nowrap px-3 ${activeModule === route ? 'active' : ''}" data-route="${esc(route)}">${esc(m.name)}</button>`;
    }).join('');
    document.querySelectorAll('.acct-nav-btn').forEach((btn) => {
      btn.addEventListener('click', () => switchModule(btn.getAttribute('data-route')));
    });
  }

  async function switchModule(route) {
    activeModule = route || 'dashboard';
    buildNav();
    const root = document.getElementById('acctPanelRoot');
    if (!root) return;
    root.innerHTML = '<p class="text-zinc-500 text-sm">Loading…</p>';
    try {
      if (route === 'dashboard') root.innerHTML = renderDashboard();
      else if (route === 'gl') root.innerHTML = await renderGL();
      else if (route === 'ap') root.innerHTML = await renderAP();
      else if (route === 'ar') root.innerHTML = await renderAR();
      else if (route === 'bank') root.innerHTML = await renderBank();
      else if (route === 'tax') root.innerHTML = await renderTax();
      else if (route === 'inventory') root.innerHTML = await renderInventory();
      else if (route === 'po') root.innerHTML = await renderPO();
      else if (route === 'oe') root.innerHTML = await renderOE();
      else if (route === 'assets') root.innerHTML = await renderAssets();
      else if (route === 'jobcost') root.innerHTML = renderJobCost();
      else if (route === 'reports') root.innerHTML = await renderReports();
      else if (route === 'payroll' || route === 'payments' || route === 'consolidation') {
        root.innerHTML = renderPlannedModule(route);
      } else {
        const mod = (catalog?.modules || []).find((m) => m.route === route);
        root.innerHTML = mod ? renderPlannedModule(route, mod) : '<p class="text-zinc-500">Module not found.</p>';
      }
      bindPanelHandlers(route);
    } catch (e) {
      root.innerHTML = `<p class="text-red-400">${esc(e.message)}</p>`;
    }
  }

  function renderDashboard() {
    const d = dashboard || {};
    const k = d.kpis || {};
    const sync = d.external_sync?.sage_300 || {};
    return `
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-4"><div class="text-xs text-zinc-500">Open A/P</div><div class="text-xl font-semibold text-amber-400">${money(k.open_ap)}</div></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-4"><div class="text-xs text-zinc-500">Open A/R</div><div class="text-xl font-semibold text-sky-400">${money(k.open_ar)}</div></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-4"><div class="text-xs text-zinc-500">G/L Accounts</div><div class="text-xl font-semibold">${k.gl_accounts || 0}</div></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-4"><div class="text-xs text-zinc-500">Open J/E Batches</div><div class="text-xl font-semibold">${k.open_batches || 0}</div></div>
      </div>
      ${d.project ? `<p class="text-xs text-zinc-500 mb-4">Active project context: <strong class="text-zinc-300">${esc(d.project.name)}</strong> · Job ${esc(d.project.job_number || '—')}</p>` : ''}
      <div class="bg-zinc-800/50 border border-zinc-700 rounded-lg p-4 mb-4">
        <h2 class="text-sm font-semibold text-white mb-2">Company books</h2>
        <p class="text-xs text-zinc-400">Ledger <span class="font-mono text-emerald-400">${esc(d.ledger?.code)}</span> — ${esc(d.ledger?.name)} (${esc(d.ledger?.base_currency)})</p>
        <p class="text-xs text-zinc-500 mt-2">Vendors: ${k.vendors || 0} · Customers: ${k.customers || 0} · Bank accounts: ${k.bank_accounts || 0}</p>
      </div>
      <div class="text-xs text-zinc-500 border border-zinc-800 rounded-lg p-3 ${sync.enabled ? 'border-amber-900/50' : ''}">
        <i class="fa-solid fa-plug mr-1"></i>
        External Sage 300 sync: <strong class="${sync.enabled ? 'text-amber-400' : 'text-zinc-400'}">${sync.enabled ? 'Enabled' : 'Off (standalone mode)'}</strong>.
        ${sync.enabled && d.external_sync?.pending_construction_exports ? ` · ${d.external_sync.pending_construction_exports} construction export(s) pending review.` : ''}
        <a href="/program-settings?tab=sage" class="text-emerald-400 hover:underline ml-1">Configure in Program Settings</a>
      </div>`;
  }

  function renderPlannedModule(route, mod) {
    const m = mod || (catalog?.modules || []).find((x) => x.route === route);
    return `<div class="max-w-xl">
      <h2 class="text-lg font-semibold text-white">${esc(m?.name || route)}</h2>
      <p class="text-sm text-zinc-400 mt-2">${esc(m?.summary || '')}</p>
      <p class="text-xs text-amber-400 mt-4 uppercase tracking-wide">${esc(m?.status || 'planned')} — expanded workflows shipping in upcoming releases.</p>
      <ul class="text-xs text-zinc-500 mt-3 list-disc pl-5">${(m?.features || []).map((f) => `<li>${esc(f)}</li>`).join('')}</ul>
    </div>`;
  }

  function renderJobCost() {
    const pid = projectId();
    return `<div>
      <h2 class="text-lg font-semibold text-white">Project &amp; Job Costing</h2>
      <p class="text-sm text-zinc-400 mt-2">Job cost lives in Case PM Budget, Commitments, and Pay Applications. Posting flows into the built-in G/L when journal batches are created.</p>
      <div class="flex flex-wrap gap-3 mt-4 text-sm">
        <a href="/budget${pid ? '?project_id=' + pid : ''}" class="text-emerald-400 hover:underline">Budget</a>
        <a href="/commitments" class="text-emerald-400 hover:underline">Commitments</a>
        <a href="/pay-applications" class="text-emerald-400 hover:underline">Pay Applications</a>
        <a href="/forecast" class="text-emerald-400 hover:underline">Forecast</a>
      </div>
      <button type="button" id="acctJobReconcile" class="mt-6 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-medium">Reconcile project financials</button>
      <pre id="acctJobReconcileOut" class="text-xs text-zinc-500 mt-2 font-mono"></pre>
    </div>`;
  }

  async function renderGL() {
    const [acct, batches] = await Promise.all([
      api('/api/accounting/gl/accounts'),
      api('/api/accounting/gl/batches'),
    ]);
    return `<div class="space-y-6">
      <section>
        <div class="flex justify-between items-center mb-2">
          <h2 class="text-lg font-semibold text-white">Chart of Accounts</h2>
          <button type="button" id="acctAddAccount" class="text-xs text-emerald-400 hover:underline">+ Account</button>
        </div>
        <div class="overflow-x-auto border border-zinc-700 rounded-lg">
          <table class="w-full text-sm"><thead class="bg-zinc-800 text-zinc-400 text-xs"><tr>
            <th class="text-left px-3 py-2">Number</th><th class="text-left px-3 py-2">Description</th><th class="text-left px-3 py-2">Type</th>
          </tr></thead><tbody>
            ${(acct.accounts || []).map((a) => `<tr class="border-t border-zinc-800"><td class="px-3 py-2 font-mono">${esc(a.account_number)}</td><td class="px-3 py-2">${esc(a.description)}</td><td class="px-3 py-2 text-xs">${esc(a.account_type)}</td></tr>`).join('')}
          </tbody></table>
        </div>
      </section>
      <section>
        <h2 class="text-lg font-semibold text-white mb-2">Journal batches</h2>
        <div class="overflow-x-auto border border-zinc-700 rounded-lg">
          <table class="w-full text-sm"><thead class="bg-zinc-800 text-xs text-zinc-400"><tr>
            <th class="px-3 py-2 text-left">Batch</th><th class="px-3 py-2 text-left">Date</th><th class="px-3 py-2 text-left">Status</th><th class="px-3 py-2"></th>
          </tr></thead><tbody>
            ${(batches.batches || []).map((b) => `<tr class="border-t border-zinc-800">
              <td class="px-3 py-2 font-mono">${esc(b.batch_number)}</td>
              <td class="px-3 py-2">${esc(b.batch_date)}</td>
              <td class="px-3 py-2">${esc(b.status)}</td>
              <td class="px-3 py-2 text-right">${b.status === 'Open' ? `<button type="button" data-post-batch="${b.id}" class="text-emerald-400 text-xs">Post</button>` : ''}</td>
            </tr>`).join('')}
          </tbody></table>
        </div>
        <button type="button" id="acctNewJeBatch" class="mt-3 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">New sample journal batch</button>
      </section>
    </div>`;
  }

  async function renderAP() {
    const [vendors, invoices] = await Promise.all([
      api('/api/accounting/ap/vendors'),
      api('/api/accounting/ap/invoices'),
    ]);
    return `<div class="space-y-6">
      <div class="flex justify-between"><h2 class="text-lg font-semibold text-white">Accounts Payable</h2>
        <button type="button" id="acctAddVendor" class="text-xs text-emerald-400">+ Vendor</button></div>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="border border-zinc-700 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
          <table class="w-full text-sm"><tbody>${(vendors.vendors || []).map((v) =>
            `<tr class="border-t border-zinc-800"><td class="px-3 py-2 font-mono text-xs">${esc(v.code)}</td><td class="px-3 py-2">${esc(v.name)}</td></tr>`
          ).join('')}</tbody></table>
        </div>
        <div class="border border-zinc-700 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
          <table class="w-full text-sm"><tbody>${(invoices.invoices || []).map((i) =>
            `<tr class="border-t border-zinc-800"><td class="px-3 py-2 font-mono">${esc(i.document_number)}</td><td class="px-3 py-2 text-right">${money(i.amount)}</td></tr>`
          ).join('')}</tbody></table>
        </div>
      </div>
    </div>`;
  }

  async function renderAR() {
    const [customers, invoices] = await Promise.all([
      api('/api/accounting/ar/customers'),
      api('/api/accounting/ar/invoices'),
    ]);
    return `<div class="space-y-4">
      <div class="flex justify-between"><h2 class="text-lg font-semibold text-white">Accounts Receivable</h2>
        <button type="button" id="acctAddCustomer" class="text-xs text-emerald-400">+ Customer</button></div>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="border border-zinc-700 rounded-lg max-h-64 overflow-y-auto text-sm">
          ${(customers.customers || []).map((c) => `<div class="px-3 py-2 border-t border-zinc-800 font-mono text-xs">${esc(c.code)} — ${esc(c.name)}</div>`).join('')}
        </div>
        <div class="border border-zinc-700 rounded-lg max-h-64 overflow-y-auto text-sm">
          ${(invoices.invoices || []).map((i) => `<div class="px-3 py-2 border-t border-zinc-800 flex justify-between"><span>${esc(i.document_number)}</span><span>${money(i.amount)}</span></div>`).join('')}
        </div>
      </div>
    </div>`;
  }

  async function renderBank() {
    const data = await api('/api/accounting/bank/accounts');
    return `<h2 class="text-lg font-semibold text-white mb-3">Bank Services</h2>
      <button type="button" id="acctAddBank" class="text-xs text-emerald-400 mb-3">+ Bank account</button>
      <ul class="text-sm space-y-2">${(data.accounts || []).map((a) =>
        `<li class="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono">${esc(a.code)} — ${esc(a.name)}</li>`
      ).join('') || '<li class="text-zinc-500">No bank accounts yet.</li>'}</ul>`;
  }

  async function renderTax() {
    const data = await api('/api/accounting/tax/groups');
    return `<h2 class="text-lg font-semibold text-white mb-3">Tax Services</h2>
      <button type="button" id="acctAddTax" class="text-xs text-emerald-400 mb-3">+ Tax group</button>
      <ul class="text-sm">${(data.groups || []).map((g) =>
        `<li class="py-2 border-b border-zinc-800">${esc(g.code)} — ${esc(g.description)} (${g.rate_percent}%)</li>`
      ).join('') || '<li class="text-zinc-500">No tax groups.</li>'}</ul>`;
  }

  async function renderInventory() {
    const data = await api('/api/accounting/inventory/items');
    return `<h2 class="text-lg font-semibold text-white mb-3">Inventory Control</h2>
      <button type="button" id="acctAddItem" class="text-xs text-emerald-400 mb-3">+ Item</button>
      <table class="w-full text-sm border border-zinc-700 rounded-lg"><tbody>
        ${(data.items || []).map((i) => `<tr class="border-t border-zinc-800"><td class="px-3 py-2 font-mono">${esc(i.item_number)}</td><td class="px-3 py-2">${esc(i.description)}</td><td class="px-3 py-2 text-right">${i.qty_on_hand}</td></tr>`).join('')}
      </tbody></table>`;
  }

  async function renderPO() {
    const data = await api('/api/accounting/po/orders');
    return `<h2 class="text-lg font-semibold text-white mb-3">Purchase Orders</h2>
      <button type="button" id="acctAddPO" class="text-xs text-emerald-400 mb-3">+ PO</button>
      <ul class="text-sm">${(data.orders || []).map((o) => `<li class="py-2 border-b border-zinc-800 font-mono">${esc(o.po_number)} — ${money(o.total_amount)}</li>`).join('')}</ul>`;
  }

  async function renderOE() {
    const data = await api('/api/accounting/oe/orders');
    return `<h2 class="text-lg font-semibold text-white mb-3">Order Entry</h2>
      <button type="button" id="acctAddOE" class="text-xs text-emerald-400 mb-3">+ Sales order</button>
      <ul class="text-sm">${(data.orders || []).map((o) => `<li class="py-2 border-b border-zinc-800 font-mono">${esc(o.order_number)} — ${money(o.total_amount)}</li>`).join('')}</ul>`;
  }

  async function renderAssets() {
    const data = await api('/api/accounting/assets');
    return `<h2 class="text-lg font-semibold text-white mb-3">Fixed Assets</h2>
      <button type="button" id="acctAddAsset" class="text-xs text-emerald-400 mb-3">+ Asset</button>
      <ul class="text-sm">${(data.assets || []).map((a) => `<li class="py-2 border-b border-zinc-800">${esc(a.asset_number)} — ${money(a.acquisition_cost)}</li>`).join('')}</ul>`;
  }

  async function renderReports() {
    const [tb, ap, ar] = await Promise.all([
      api('/api/accounting/reports/trial-balance'),
      api('/api/accounting/reports/ap-aging'),
      api('/api/accounting/reports/ar-aging'),
    ]);
    return `<h2 class="text-lg font-semibold text-white mb-4">Financial Reports</h2>
      <h3 class="text-sm font-medium text-zinc-300 mb-2">Trial balance</h3>
      <div class="overflow-x-auto border border-zinc-700 rounded-lg mb-6 max-h-48 overflow-y-auto">
        <table class="w-full text-xs"><tbody>
          ${(tb.rows || []).map((r) => `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono">${esc(r.account_number)}</td><td class="px-2 py-1">${esc(r.description)}</td><td class="px-2 py-1 text-right">${money(r.debit)}</td><td class="px-2 py-1 text-right">${money(r.credit)}</td></tr>`).join('')}
        </tbody></table>
      </div>
      <div class="grid md:grid-cols-2 gap-4 text-sm">
        <div><h3 class="text-sm text-zinc-400 mb-2">A/P aging</h3><pre class="text-xs font-mono text-zinc-500">${esc(JSON.stringify(ap.buckets, null, 2))}</pre></div>
        <div><h3 class="text-sm text-zinc-400 mb-2">A/R aging</h3><pre class="text-xs font-mono text-zinc-500">${esc(JSON.stringify(ar.buckets, null, 2))}</pre></div>
      </div>`;
  }

  function bindPanelHandlers(route) {
    document.getElementById('acctAddVendor')?.addEventListener('click', async () => {
      const code = prompt('Vendor code');
      const name = prompt('Vendor name');
      if (!code || !name) return;
      await api('/api/accounting/ap/vendors', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code, name }) });
      switchModule('ap');
    });
    document.getElementById('acctAddCustomer')?.addEventListener('click', async () => {
      const code = prompt('Customer code');
      const name = prompt('Customer name');
      if (!code || !name) return;
      await api('/api/accounting/ar/customers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code, name }) });
      switchModule('ar');
    });
    document.getElementById('acctAddBank')?.addEventListener('click', async () => {
      const code = prompt('Bank code');
      const name = prompt('Bank name');
      if (!code || !name) return;
      await api('/api/accounting/bank/accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code, name }) });
      switchModule('bank');
    });
    document.getElementById('acctAddTax')?.addEventListener('click', async () => {
      const code = prompt('Tax group code');
      if (!code) return;
      await api('/api/accounting/tax/groups', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code, description: code, rate_percent: 0 }) });
      switchModule('tax');
    });
    document.getElementById('acctAddItem')?.addEventListener('click', async () => {
      const item_number = prompt('Item number');
      if (!item_number) return;
      await api('/api/accounting/inventory/items', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ item_number, description: item_number }) });
      switchModule('inventory');
    });
    document.getElementById('acctAddPO')?.addEventListener('click', async () => {
      const po_number = prompt('PO number');
      if (!po_number) return;
      await api('/api/accounting/po/orders', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ po_number, total_amount: 0 }) });
      switchModule('po');
    });
    document.getElementById('acctAddOE')?.addEventListener('click', async () => {
      const order_number = prompt('Order number');
      if (!order_number) return;
      await api('/api/accounting/oe/orders', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ order_number, total_amount: 0 }) });
      switchModule('oe');
    });
    document.getElementById('acctAddAsset')?.addEventListener('click', async () => {
      const asset_number = prompt('Asset number');
      if (!asset_number) return;
      await api('/api/accounting/assets', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset_number, acquisition_cost: 0 }) });
      switchModule('assets');
    });
    document.getElementById('acctNewJeBatch')?.addEventListener('click', async () => {
      const acct = await api('/api/accounting/gl/accounts');
      const accounts = acct.accounts || [];
      if (accounts.length < 2) return alert('Need at least 2 GL accounts');
      const cash = accounts.find((a) => a.account_number.startsWith('10')) || accounts[0];
      const expense = accounts.find((a) => a.account_type === 'expense') || accounts[1];
      await api('/api/accounting/gl/batches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: 'Sample entry',
          lines: [
            { account_id: expense.id, debit: 100, credit: 0, description: 'Sample expense' },
            { account_id: cash.id, debit: 0, credit: 100, description: 'Cash offset' },
          ],
        }),
      });
      switchModule('gl');
    });
    document.querySelectorAll('[data-post-batch]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api(`/api/accounting/gl/batches/${btn.getAttribute('data-post-batch')}/post`, { method: 'POST', body: '{}' });
        switchModule('gl');
      });
    });
    document.getElementById('acctJobReconcile')?.addEventListener('click', async () => {
      const out = document.getElementById('acctJobReconcileOut');
      try {
        const json = await (global.CasePMAccountingReconcile?.reconcileProject({ force: true }) || api(`/api/accounting/reconcile?project_id=${projectId()}`, { method: 'POST', body: '{}' }));
        out.textContent = JSON.stringify(json, null, 2);
      } catch (e) {
        out.textContent = e.message;
      }
    });
  }

  async function refresh() {
    const pid = projectId();
    const q = pid ? `?project_id=${pid}` : '';
    [catalog, dashboard] = await Promise.all([
      api('/api/accounting/catalog'),
      api(`/api/accounting/dashboard${q}`),
    ]);
    const badge = document.getElementById('acctLedgerBadge');
    if (badge && dashboard.ledger) {
      badge.textContent = `${dashboard.ledger.code} · ${dashboard.ledger.base_currency}`;
    }
    buildNav();
    await switchModule(activeModule);
  }

  async function init() {
    document.getElementById('acctRefreshBtn')?.addEventListener('click', refresh);
    const params = new URLSearchParams(global.location.search);
    const m = params.get('module');
    if (m) activeModule = m;
    await refresh();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  global.CasePMAccounting = { refresh, switchModule };
})(window);
