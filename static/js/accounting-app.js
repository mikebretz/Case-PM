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
      else if (route === 'tax') root.innerHTML = global.CasePMAcctModulesUI ? await global.CasePMAcctModulesUI.renderTax() : await renderTax();
      else if (route === 'inventory') root.innerHTML = global.CasePMAcctModulesUI ? await global.CasePMAcctModulesUI.renderInventory() : await renderInventory();
      else if (route === 'po') root.innerHTML = global.CasePMAcctModulesUI ? await global.CasePMAcctModulesUI.renderPO() : await renderPO();
      else if (route === 'oe') root.innerHTML = global.CasePMAcctModulesUI ? await global.CasePMAcctModulesUI.renderOE() : await renderOE();
      else if (route === 'assets') root.innerHTML = global.CasePMAcctModulesUI ? await global.CasePMAcctModulesUI.renderAssets() : await renderAssets();
      else if (route === 'jobcost') root.innerHTML = renderJobCost();
      else if (route === 'reports') {
        if (global.CasePMAccountingReports) {
          root.innerHTML = await global.CasePMAccountingReports.render();
        } else {
          root.innerHTML = await renderReportsLegacy();
        }
      }
      else if (route === 'payroll') {
        root.innerHTML = global.CasePMAcctPayrollUI
          ? await global.CasePMAcctPayrollUI.render()
          : await renderPayroll();
      }
      else if (route === 'payments' || route === 'consolidation') {
        root.innerHTML = renderPlannedModule(route);
      } else {
        const mod = (catalog?.modules || []).find((m) => m.route === route);
        root.innerHTML = mod ? renderPlannedModule(route, mod) : '<p class="text-zinc-500">Module not found.</p>';
      }
      bindPanelHandlers(route);
      if (global.CasePMAcctModulesUI?.bindExtras) global.CasePMAcctModulesUI.bindExtras(route);
      if (route === 'payroll' && global.CasePMAcctPayrollUI?.bindHandlers) {
        global.CasePMAcctPayrollUI.bindHandlers();
      }
      if (route === 'reports' && global.CasePMAccountingReports?.bindHandlers) {
        global.CasePMAccountingReports.bindHandlers();
      }
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
      </div>
      <div class="flex flex-wrap gap-2 mt-4">
        <button type="button" class="px-3 py-2 text-xs bg-zinc-800 border border-zinc-700 rounded-md hover:bg-zinc-700" data-acct-dash="reports">Financial reports</button>
        <button type="button" class="px-3 py-2 text-xs bg-zinc-800 border border-zinc-700 rounded-md hover:bg-zinc-700" data-acct-dash="jobcost">Job cost</button>
        <button type="button" class="px-3 py-2 text-xs bg-zinc-800 border border-zinc-700 rounded-md hover:bg-zinc-700" data-acct-dash="gl">General ledger</button>
        <a href="/program-settings?tab=accounting" class="px-3 py-2 text-xs bg-zinc-800 border border-zinc-700 rounded-md hover:bg-zinc-700 inline-block">Construction G/L mapping</a>
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
    const [vendors, invoices, payments] = await Promise.all([
      api('/api/accounting/ap/vendors'),
      api('/api/accounting/ap/invoices'),
      api('/api/accounting/ap/payments'),
    ]);
    const open = (invoices.invoices || []).filter((i) => i.status === 'Open' || i.status === 'Partial');
    return `<div class="space-y-6">
      <div class="flex justify-between items-center">
        <h2 class="text-lg font-semibold text-white">Accounts Payable</h2>
        <button type="button" id="acctAddVendor" class="text-xs text-emerald-400">+ Vendor</button>
      </div>
      <div class="bg-zinc-800/40 border border-zinc-700 rounded-lg p-4">
        <h3 class="text-sm font-medium text-zinc-300 mb-2">Pay open invoices</h3>
        <p class="text-xs text-zinc-500 mb-3">Creates AP payment, posts Dr A/P · Cr Cash, and updates bank activity.</p>
        <button type="button" id="acctPayApBtn" class="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 rounded text-sm" ${open.length ? '' : 'disabled'}>Pay selected invoice…</button>
        <ul class="mt-3 text-xs space-y-1 max-h-32 overflow-y-auto">${open.map((i) =>
          `<li class="text-zinc-400"><span class="font-mono">${esc(i.document_number)}</span> — ${money(i.amount)} (vendor #${i.vendor_id}) <span class="text-zinc-600">id ${i.id}</span></li>`
        ).join('') || '<li>No open invoices — approve sub pay apps to auto-create AP.</li>'}</ul>
      </div>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="border border-zinc-700 rounded-lg overflow-hidden max-h-48 overflow-y-auto">
          <div class="px-3 py-2 bg-zinc-800 text-xs text-zinc-500">Vendors</div>
          <table class="w-full text-sm"><tbody>${(vendors.vendors || []).map((v) =>
            `<tr class="border-t border-zinc-800"><td class="px-3 py-2 font-mono text-xs">${esc(v.code)}</td><td class="px-3 py-2">${esc(v.name)}</td></tr>`
          ).join('')}</tbody></table>
        </div>
        <div class="border border-zinc-700 rounded-lg overflow-hidden max-h-48 overflow-y-auto">
          <div class="px-3 py-2 bg-zinc-800 text-xs text-zinc-500">Recent payments</div>
          ${(payments.payments || []).map((p) =>
            `<div class="px-3 py-2 border-t border-zinc-800 text-xs font-mono">${esc(p.payment_number)} ${money(p.amount)}</div>`
          ).join('') || '<div class="p-3 text-zinc-500 text-xs">No payments yet.</div>'}
        </div>
      </div>
    </div>`;
  }

  async function renderAR() {
    const [customers, invoices, receipts] = await Promise.all([
      api('/api/accounting/ar/customers'),
      api('/api/accounting/ar/invoices'),
      api('/api/accounting/ar/receipts'),
    ]);
    const open = (invoices.invoices || []).filter((i) => i.status === 'Open' || i.status === 'Partial');
    return `<div class="space-y-4">
      <div class="flex justify-between"><h2 class="text-lg font-semibold text-white">Accounts Receivable</h2>
        <button type="button" id="acctAddCustomer" class="text-xs text-emerald-400">+ Customer</button></div>
      <div class="bg-zinc-800/40 border border-zinc-700 rounded-lg p-4">
        <h3 class="text-sm font-medium text-zinc-300 mb-2">Cash application</h3>
        <button type="button" id="acctArReceiptBtn" class="px-3 py-2 bg-sky-600 hover:bg-sky-500 rounded text-sm" ${open.length ? '' : 'disabled'}>Apply receipt…</button>
        <ul class="mt-3 text-xs space-y-1">${open.map((i) =>
          `<li class="text-zinc-400 font-mono">${esc(i.document_number)} — ${money(i.amount)} (cust #${i.customer_id}) id ${i.id}</li>`
        ).join('') || '<li class="text-zinc-500">No open AR — approve G702 to auto-create owner invoices.</li>'}</ul>
      </div>
      <div class="grid md:grid-cols-2 gap-4 text-sm">
        <div class="border border-zinc-700 rounded-lg max-h-48 overflow-y-auto">
          ${(customers.customers || []).map((c) => `<div class="px-3 py-2 border-t border-zinc-800 font-mono text-xs">${esc(c.code)} — ${esc(c.name)}</div>`).join('')}
        </div>
        <div class="border border-zinc-700 rounded-lg max-h-48 overflow-y-auto">
          ${(receipts.receipts || []).map((r) => `<div class="px-3 py-2 border-t border-zinc-800 text-xs">${esc(r.receipt_number)} ${money(r.amount)}</div>`).join('') || '<div class="p-3 text-zinc-500 text-xs">No receipts.</div>'}
        </div>
      </div>
    </div>`;
  }

  async function renderBank() {
    const accounts = await api('/api/accounting/bank/accounts');
    const bankList = accounts.accounts || [];
    const bankId = bankList[0]?.id;
    let tx = { transactions: [] };
    if (bankId) tx = await api(`/api/accounting/bank/transactions?bank_account_id=${bankId}`);
    return `<h2 class="text-lg font-semibold text-white mb-3">Bank Services</h2>
      <button type="button" id="acctAddBank" class="text-xs text-emerald-400 mb-3">+ Bank account</button>
      <ul class="text-sm space-y-2 mb-4">${bankList.map((a) =>
        `<li class="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 font-mono">${esc(a.code)} — ${esc(a.name)}</li>`
      ).join('') || '<li class="text-zinc-500">No bank accounts yet.</li>'}</ul>
      <h3 class="text-sm text-zinc-400 mb-2">Unreconciled activity ${bankId ? `(account ${bankId})` : ''}</h3>
      <form id="acctReconForm" class="space-y-2 max-h-56 overflow-y-auto border border-zinc-700 rounded-lg p-2">
        ${(tx.transactions || []).filter((t) => !t.reconciled).map((t) =>
          `<label class="flex items-center gap-2 text-xs py-1 border-b border-zinc-800">
            <input type="checkbox" name="tx" value="${t.id}" />
            <span class="font-mono w-20">${money(t.amount)}</span>
            <span class="text-zinc-400 truncate">${esc(t.description || t.reference)}</span>
          </label>`
        ).join('') || '<p class="text-zinc-500 text-xs p-2">No unreconciled items — payments and receipts create bank lines automatically.</p>'}
      </form>
      <button type="button" id="acctReconBtn" class="mt-3 px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded text-sm" ${bankId ? '' : 'disabled'}>Mark selected reconciled</button>`;
  }

  async function renderPayroll() {
    const data = await api('/api/accounting/payroll/runs');
    return `<div>
      <h2 class="text-lg font-semibold text-white mb-2">Payroll</h2>
      <p class="text-xs text-zinc-500 mb-4">Create a pay run, then post to G/L (Dr labor · Cr liabilities · Cr cash).</p>
      <button type="button" id="acctNewPayroll" class="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 rounded text-sm mb-4">+ New pay run</button>
      <ul class="text-sm space-y-2">${(data.runs || []).map((r) =>
        `<li class="flex justify-between items-center border border-zinc-700 rounded px-3 py-2">
          <span class="font-mono text-xs">${esc(r.run_number)} — gross ${money(r.total_gross)} · ${esc(r.status)}</span>
          ${r.status === 'Open' ? `<button type="button" data-post-payroll="${r.id}" class="text-emerald-400 text-xs">Post to G/L</button>` : ''}
        </li>`
      ).join('') || '<li class="text-zinc-500">No pay runs.</li>'}</ul>
    </div>`;
  }

  async function renderAssets() {
    const data = await api('/api/accounting/assets');
    return `<h2 class="text-lg font-semibold text-white mb-3">Fixed Assets</h2>
      <div class="flex gap-2 mb-3">
        <button type="button" id="acctAddAsset" class="text-xs text-emerald-400">+ Asset</button>
        <button type="button" id="acctRunDep" class="text-xs text-violet-400">Run monthly depreciation</button>
      </div>
      <ul class="text-sm">${(data.assets || []).map((a) => `<li class="py-2 border-b border-zinc-800">${esc(a.asset_number)} — ${money(a.acquisition_cost)} · ${esc(a.status)}</li>`).join('')}</ul>`;
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
        ${(data.items || []).map((i) => `<tr class="border-t border-zinc-800"><td class="px-3 py-2 font-mono">${esc(i.item_number)}</td><td class="px-3 py-2">${esc(i.description)}</td><td class="px-3 py-2 text-right">${i.qty_on_hand}</td>
          <td class="px-3 py-2 text-right"><button type="button" class="text-emerald-400 text-xs acct-inv-adj" data-id="${i.id}">± Qty</button></td></tr>`).join('')}
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

  async function renderReportsLegacy() {
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

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  function bindPanelHandlers(route) {
    document.querySelectorAll('[data-acct-dash]').forEach((btn) => {
      btn.addEventListener('click', () => switchModule(btn.getAttribute('data-acct-dash')));
    });
    document.getElementById('acctPayApBtn')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Pay A/P invoice',
        fields: [
          { key: 'invId', label: 'AP invoice id (from list above)', required: true },
          { key: 'vendorId', label: 'Vendor id', required: true },
          { key: 'amt', label: 'Payment amount', type: 'number', step: '0.01', required: true },
        ],
        submitLabel: 'Post payment',
      });
      if (!data) return;
      const banks = await api('/api/accounting/bank/accounts');
      const bankId = (banks.accounts || [])[0]?.id;
      await api('/api/accounting/ap/payments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vendor_id: parseInt(data.vendorId, 10),
          amount: parseFloat(data.amt),
          bank_account_id: bankId,
          applications: [{ ap_document_id: parseInt(data.invId, 10), amount: parseFloat(data.amt) }],
        }),
      });
      switchModule('ap');
    });
    document.getElementById('acctArReceiptBtn')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Apply A/R receipt',
        fields: [
          { key: 'invId', label: 'AR invoice id', required: true },
          { key: 'custId', label: 'Customer id', required: true },
          { key: 'amt', label: 'Receipt amount', type: 'number', step: '0.01', required: true },
        ],
        submitLabel: 'Apply receipt',
      });
      if (!data) return;
      const banks = await api('/api/accounting/bank/accounts');
      const bankId = (banks.accounts || [])[0]?.id;
      await api('/api/accounting/ar/receipts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: parseInt(data.custId, 10),
          amount: parseFloat(data.amt),
          bank_account_id: bankId,
          applications: [{ ar_document_id: parseInt(data.invId, 10), amount: parseFloat(data.amt) }],
        }),
      });
      switchModule('ar');
    });
    document.getElementById('acctReconBtn')?.addEventListener('click', async () => {
      const banks = await api('/api/accounting/bank/accounts');
      const bankId = (banks.accounts || [])[0]?.id;
      if (!bankId) return;
      const ids = [...document.querySelectorAll('#acctReconForm input[name=tx]:checked')].map((el) => parseInt(el.value, 10));
      await api('/api/accounting/bank/reconcile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bank_account_id: bankId, transaction_ids: ids }),
      });
      switchModule('bank');
    });
    document.getElementById('acctNewPayroll')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Quick pay run (totals only)',
        fields: [
          { key: 'gross', label: 'Total gross wages', type: 'number', step: '0.01', required: true },
          { key: 'net', label: 'Net pay (employee deposits)', type: 'number', step: '0.01', defaultValue: '0' },
          { key: 'taxes', label: 'Payroll taxes / withholdings', type: 'number', step: '0.01', defaultValue: '0' },
        ],
        submitLabel: 'Create run',
      });
      if (!data) return;
      await api('/api/accounting/payroll/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          total_gross: parseFloat(data.gross),
          total_net: parseFloat(data.net || 0),
          total_taxes: parseFloat(data.taxes || 0),
        }),
      });
      switchModule('payroll');
    });
    document.querySelectorAll('[data-post-payroll]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api(`/api/accounting/payroll/runs/${btn.getAttribute('data-post-payroll')}/post`, { method: 'POST', body: '{}' });
        switchModule('payroll');
      });
    });
    document.getElementById('acctRunDep')?.addEventListener('click', async () => {
      try {
        const out = await api('/api/accounting/assets/depreciate', { method: 'POST', body: '{}' });
        await AD().alert(`Depreciation posted: ${money(out.total)}`, 'success');
        switchModule('assets');
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });
    document.getElementById('acctAddVendor')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Add vendor',
        fields: [
          { key: 'code', label: 'Vendor code', required: true },
          { key: 'name', label: 'Vendor name', required: true },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ap/vendors', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      switchModule('ap');
    });
    document.getElementById('acctAddCustomer')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Add customer',
        fields: [
          { key: 'code', label: 'Customer code', required: true },
          { key: 'name', label: 'Customer name', required: true },
        ],
      });
      if (!data) return;
      await api('/api/accounting/ar/customers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      switchModule('ar');
    });
    document.getElementById('acctAddBank')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Add bank account',
        fields: [
          { key: 'code', label: 'Bank code', required: true },
          { key: 'name', label: 'Bank name', required: true },
        ],
      });
      if (!data) return;
      await api('/api/accounting/bank/accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      switchModule('bank');
    });
    document.getElementById('acctAddTax')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Add tax group',
        fields: [
          { key: 'code', label: 'Tax group code (e.g. FL-SALES)', required: true },
          { key: 'rate', label: 'Rate %', type: 'number', step: '0.01', defaultValue: '7', required: true },
          {
            key: 'tax_type',
            label: 'Type',
            type: 'select',
            defaultValue: 'sales',
            options: [
              { value: 'sales', label: 'Sales tax' },
              { value: 'use', label: 'Use tax' },
              { value: 'withholding', label: 'Withholding' },
            ],
          },
        ],
      });
      if (!data) return;
      await api('/api/accounting/tax/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: data.code,
          description: data.code,
          rate_percent: parseFloat(data.rate || 0),
          tax_type: data.tax_type,
          authority: 'State',
        }),
      });
      switchModule('tax');
    });
    document.getElementById('acctAddItem')?.addEventListener('click', async () => {
      const item_number = await AD().promptRequired('Item number', '', { title: 'Add inventory item' });
      if (!item_number) return;
      await api('/api/accounting/inventory/items', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ item_number, description: item_number }) });
      switchModule('inventory');
    });
    document.querySelectorAll('.acct-inv-adj').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const delta = await AD().prompt('Quantity change (+ receive, − issue)', '1', { title: 'Adjust quantity', label: 'Qty delta' });
        if (delta == null || delta === '') return;
        await api(`/api/accounting/inventory/items/${btn.getAttribute('data-id')}/adjust`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ qty_delta: parseFloat(delta) }),
        });
        switchModule('inventory');
      });
    });
    document.getElementById('acctAddPO')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'New purchase order',
        fields: [
          { key: 'po_number', label: 'PO number', required: true },
          { key: 'vendorId', label: 'Vendor id (optional)' },
          { key: 'item', label: 'Line item number (inventory)', defaultValue: 'MAT-001' },
          { key: 'qty', label: 'Quantity', type: 'number', step: '0.01', defaultValue: '1' },
          { key: 'price', label: 'Unit price', type: 'number', step: '0.01', defaultValue: '0' },
        ],
      });
      if (!data) return;
      const qty = parseFloat(data.qty || 1);
      const price = parseFloat(data.price || 0);
      const item = data.item;
      const lines = item ? [{ item_number: item, description: item, qty, unit_price: price, qty_received: 0 }] : [];
      await api('/api/accounting/po/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          po_number: data.po_number,
          vendor_id: data.vendorId ? parseInt(data.vendorId, 10) : null,
          project_id: projectId(),
          lines,
        }),
      });
      switchModule('po');
    });
    document.getElementById('acctAddOE')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'New sales order',
        fields: [
          { key: 'order_number', label: 'Order number', required: true },
          { key: 'customerId', label: 'Customer id' },
          { key: 'desc', label: 'Line description', defaultValue: 'Materials sale' },
          { key: 'qty', label: 'Qty', type: 'number', step: '0.01', defaultValue: '1' },
          { key: 'price', label: 'Unit price', type: 'number', step: '0.01', defaultValue: '100' },
        ],
      });
      if (!data) return;
      const lines = [{ description: data.desc, qty: parseFloat(data.qty || 1), unit_price: parseFloat(data.price || 0), qty_shipped: 0 }];
      await api('/api/accounting/oe/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          order_number: data.order_number,
          customer_id: data.customerId ? parseInt(data.customerId, 10) : null,
          project_id: projectId(),
          lines,
        }),
      });
      switchModule('oe');
    });
    document.getElementById('acctAddAsset')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Add fixed asset',
        fields: [
          { key: 'asset_number', label: 'Asset number', required: true },
          { key: 'description', label: 'Description' },
          { key: 'cost', label: 'Acquisition cost', type: 'number', step: '0.01', defaultValue: '0' },
          { key: 'months', label: 'Useful life (months)', type: 'number', defaultValue: '60' },
          { key: 'location', label: 'Location (optional)' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/assets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asset_number: data.asset_number,
          description: data.description || data.asset_number,
          acquisition_cost: parseFloat(data.cost || 0),
          useful_life_months: parseInt(data.months || 60, 10),
          location: data.location || '',
        }),
      });
      switchModule('assets');
    });
    document.getElementById('acctNewJeBatch')?.addEventListener('click', async () => {
      const acct = await api('/api/accounting/gl/accounts');
      const accounts = acct.accounts || [];
      if (accounts.length < 2) {
        await AD().alert('Need at least 2 GL accounts', 'warning');
        return;
      }
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

  global.CasePMAccounting = {
    refresh,
    switchModule,
    _api: api,
    _esc: esc,
    _money: money,
    _projectId: projectId,
  };
})(window);
