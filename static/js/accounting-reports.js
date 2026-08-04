/**
 * Accounting → Reports: catalog, filters, saved custom reports, CSV export.
 */
(function (global) {
  'use strict';

  function AD() {
    return global.CasePMAccountingDialog || {};
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

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  async function api(path, options) {
    const res = await fetch(path, { credentials: 'same-origin', ...(options || {}) });
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('text/csv')) return res;
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || res.statusText);
    return json;
  }

  function defaultDates() {
    const end = new Date();
    const start = new Date(end.getFullYear(), 0, 1);
    const iso = (d) => d.toISOString().slice(0, 10);
    return { start: iso(start), end: iso(end) };
  }

  function needsDateRange(type) {
    return ['income_statement', 'journal_register'].includes(type);
  }

  function renderReportBody(data) {
    const rtype = data.report || '';
    if (rtype === 'trial_balance') {
      const rows = data.rows || [];
      return `<div class="overflow-x-auto border border-zinc-700 rounded-lg acct-report-table-wrap">
        <table class="w-full text-xs"><thead class="sticky top-0 bg-zinc-800"><tr>
          <th class="text-left px-2 py-1">Account</th><th class="text-left px-2 py-1">Description</th>
          <th class="text-right px-2 py-1">Debit</th><th class="text-right px-2 py-1">Credit</th><th class="text-right px-2 py-1">Balance</th>
        </tr></thead><tbody>
        ${rows.map((r) => `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono">${esc(r.account_number)}</td>
          <td class="px-2 py-1">${esc(r.description)}</td>
          <td class="px-2 py-1 text-right">${money(r.debit)}</td><td class="px-2 py-1 text-right">${money(r.credit)}</td>
          <td class="px-2 py-1 text-right">${money(r.balance)}</td></tr>`).join('')}
        </tbody></table></div>`;
    }
    if (rtype === 'income_statement') {
      const rev = (data.detail?.revenue || []).map((r) =>
        `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono">${esc(r.account_number)}</td><td class="px-2 py-1">${esc(r.description)}</td><td class="px-2 py-1 text-right">${money(r.amount)}</td></tr>`
      ).join('');
      const exp = (data.detail?.expense || []).map((r) =>
        `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono">${esc(r.account_number)}</td><td class="px-2 py-1">${esc(r.description)}</td><td class="px-2 py-1 text-right">${money(r.amount)}</td></tr>`
      ).join('');
      return `<div class="grid md:grid-cols-3 gap-3 mb-4 text-sm">
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-3"><div class="text-zinc-500 text-xs">Revenue</div><div class="text-lg text-emerald-400">${money(data.total_revenue)}</div></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-3"><div class="text-zinc-500 text-xs">Expense</div><div class="text-lg text-amber-400">${money(data.total_expense)}</div></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-3"><div class="text-zinc-500 text-xs">Net income</div><div class="text-lg font-semibold text-white">${money(data.net_income)}</div></div>
      </div>
      <div class="grid md:grid-cols-2 gap-4">
        <div><h4 class="text-xs text-zinc-400 mb-1">Revenue</h4><table class="w-full text-xs border border-zinc-700 rounded-lg"><tbody>${rev || '<tr><td class="p-2 text-zinc-500">No revenue postings in period.</td></tr>'}</tbody></table></div>
        <div><h4 class="text-xs text-zinc-400 mb-1">Expense</h4><table class="w-full text-xs border border-zinc-700 rounded-lg"><tbody>${exp || '<tr><td class="p-2 text-zinc-500">No expense postings in period.</td></tr>'}</tbody></table></div>
      </div>`;
    }
    if (rtype === 'balance_sheet') {
      const section = (title, rows) => {
        const body = (rows || []).map((r) =>
          `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono">${esc(r.account_number)}</td><td class="px-2 py-1">${esc(r.description)}</td><td class="px-2 py-1 text-right">${money(r.balance)}</td></tr>`
        ).join('');
        return `<div><h4 class="text-xs text-zinc-400 mb-1">${esc(title)}</h4><table class="w-full text-xs border border-zinc-700 rounded-lg mb-3"><tbody>${body}</tbody></table></div>`;
      };
      const s = data.sections || {};
      return `<p class="text-xs text-zinc-500 mb-3">As of ${esc(data.as_of)}</p>
        <div class="grid md:grid-cols-3 gap-3 mb-4 text-sm">
          <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Assets: <strong>${money(data.total_assets)}</strong></div>
          <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Liabilities: <strong>${money(data.total_liabilities)}</strong></div>
          <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Equity: <strong>${money(data.total_equity)}</strong></div>
        </div>
        ${section('Assets', s.assets)}${section('Liabilities', s.liabilities)}${section('Equity', s.equity)}`;
    }
    if (rtype === 'journal_register') {
      const lines = data.lines || [];
      return `<p class="text-xs text-zinc-500 mb-2">${lines.length} posted line(s)</p>
        <div class="overflow-x-auto border border-zinc-700 rounded-lg acct-report-table-wrap">
        <table class="w-full text-xs"><thead class="sticky top-0 bg-zinc-800"><tr>
          <th class="text-left px-2 py-1">Date</th><th class="text-left px-2 py-1">Batch</th><th class="text-left px-2 py-1">Account</th>
          <th class="text-left px-2 py-1">Description</th><th class="text-right px-2 py-1">Debit</th><th class="text-right px-2 py-1">Credit</th>
        </tr></thead><tbody>
        ${lines.map((r) => `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${esc(r.batch_date)}</td><td class="px-2 py-1 font-mono">${esc(r.batch_number)}</td>
          <td class="px-2 py-1 font-mono">${esc(r.account_number)}</td><td class="px-2 py-1">${esc(r.description)}</td>
          <td class="px-2 py-1 text-right">${money(r.debit)}</td><td class="px-2 py-1 text-right">${money(r.credit)}</td></tr>`).join('')}
        </tbody></table></div>`;
    }
    if (rtype === 'ap_aging' || rtype === 'ar_aging') {
      const buckets = data.buckets || {};
      const docs = data.documents || [];
      return `<div class="grid grid-cols-2 md:grid-cols-5 gap-2 mb-4 text-xs">
        ${Object.entries(buckets).map(([k, v]) => `<div class="bg-zinc-800 border border-zinc-700 rounded p-2"><div class="text-zinc-500">${esc(k)}</div><div class="font-semibold">${money(v)}</div></div>`).join('')}
      </div>
      <div class="overflow-x-auto border border-zinc-700 rounded-lg acct-report-table-wrap">
        <table class="w-full text-xs"><thead><tr><th class="text-left px-2 py-1">Doc</th><th class="text-right px-2 py-1">Open</th><th class="text-left px-2 py-1">Due</th></tr></thead><tbody>
        ${docs.slice(0, 100).map((d) => `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono">${esc(d.document_number || d.id)}</td>
          <td class="px-2 py-1 text-right">${money(d.open_amount ?? d.balance)}</td><td class="px-2 py-1">${esc(d.due_date)}</td></tr>`).join('')}
        </tbody></table></div>`;
    }
    if (rtype === 'job_cost') {
      const rows = data.projects || [];
      return `<table class="w-full text-sm border border-zinc-700 rounded-lg"><thead class="bg-zinc-800"><tr>
        <th class="text-left px-3 py-2">Project</th><th class="text-left px-3 py-2">Name</th><th class="text-right px-3 py-2">Net cost</th><th class="text-right px-3 py-2">Lines</th>
      </tr></thead><tbody>
      ${rows.map((r) => `<tr class="border-t border-zinc-800"><td class="px-3 py-2 font-mono">${esc(r.project_number || r.project_id)}</td>
        <td class="px-3 py-2">${esc(r.project_name)}</td><td class="px-3 py-2 text-right">${money(r.net_cost)}</td><td class="px-3 py-2 text-right">${r.lines}</td></tr>`).join('')}
      </tbody></table>`;
    }
    if (rtype === 'construction_bridge') {
      const events = data.events || [];
      return `<p class="text-xs text-zinc-500 mb-2">Construction events linked to G/L, A/P, A/R, or PO (latest 500).</p>
        <table class="w-full text-xs border border-zinc-700 rounded-lg"><thead class="bg-zinc-800"><tr>
          <th class="text-left px-2 py-1">When</th><th class="text-left px-2 py-1">Source</th><th class="text-left px-2 py-1">Key</th><th class="text-left px-2 py-1">Batch</th>
        </tr></thead><tbody>
        ${events.map((e) => `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${esc(e.created_at)}</td>
          <td class="px-2 py-1">${esc(e.source_type)}</td><td class="px-2 py-1 font-mono text-[10px]">${esc(e.source_key)}</td>
          <td class="px-2 py-1">${e.journal_batch_id || '—'}</td></tr>`).join('') || '<tr><td colspan="4" class="p-3 text-zinc-500">No bridge posts yet — approve pay apps or commitments to populate.</td></tr>'}
        </tbody></table>`;
    }
    if (rtype === 'vendor_activity') {
      return `<table class="w-full text-sm border border-zinc-700 rounded-lg"><thead class="bg-zinc-800"><tr>
        <th class="text-left px-3 py-2">Vendor</th><th class="text-right px-3 py-2">Billed</th><th class="text-right px-3 py-2">Paid</th><th class="text-right px-3 py-2">Open</th>
      </tr></thead><tbody>
      ${(data.vendors || []).map((v) => `<tr class="border-t border-zinc-800"><td class="px-3 py-2">${esc(v.code)} — ${esc(v.name)}</td>
        <td class="px-3 py-2 text-right">${money(v.billed)}</td><td class="px-3 py-2 text-right">${money(v.paid)}</td><td class="px-3 py-2 text-right">${money(v.open)}</td></tr>`).join('')}
      </tbody></table>`;
    }
    if (rtype === 'customer_activity') {
      return `<table class="w-full text-sm border border-zinc-700 rounded-lg"><thead class="bg-zinc-800"><tr>
        <th class="text-left px-3 py-2">Customer</th><th class="text-right px-3 py-2">Billed</th><th class="text-right px-3 py-2">Collected</th><th class="text-right px-3 py-2">Open</th>
      </tr></thead><tbody>
      ${(data.customers || []).map((c) => `<tr class="border-t border-zinc-800"><td class="px-3 py-2">${esc(c.code)} — ${esc(c.name)}</td>
        <td class="px-3 py-2 text-right">${money(c.billed)}</td><td class="px-3 py-2 text-right">${money(c.collected)}</td><td class="px-3 py-2 text-right">${money(c.open)}</td></tr>`).join('')}
      </tbody></table>`;
    }
    if (rtype === 'cash_summary') {
      return `<table class="w-full text-sm border border-zinc-700 rounded-lg"><thead class="bg-zinc-800"><tr>
        <th class="text-left px-3 py-2">Bank</th><th class="text-right px-3 py-2">Balance</th><th class="text-right px-3 py-2">Unreconciled</th><th class="text-right px-3 py-2">Tx count</th>
      </tr></thead><tbody>
      ${(data.accounts || []).map((a) => `<tr class="border-t border-zinc-800"><td class="px-3 py-2">${esc(a.code)} — ${esc(a.name)}</td>
        <td class="px-3 py-2 text-right">${money(a.balance)}</td><td class="px-3 py-2 text-right">${money(a.unreconciled)}</td><td class="px-3 py-2 text-right">${a.transaction_count}</td></tr>`).join('')}
      </tbody></table>`;
    }
    return `<pre class="text-xs text-zinc-500 overflow-auto max-h-96">${esc(JSON.stringify(data, null, 2))}</pre>`;
  }

  async function renderShell() {
    const [catalog, custom, projectResp] = await Promise.all([
      api('/api/accounting/reports/catalog'),
      api('/api/accounting/reports/custom'),
      api('/api/accounting/reports/projects?status=active').catch(() => ({ projects: [] })),
    ]);
    const types = catalog.types || [];
    const dates = defaultDates();
    const pid = projectId();
    const projects = projectResp.projects || [];
    const byCat = {};
    types.forEach((t) => {
      const c = t.category || 'other';
      if (!byCat[c]) byCat[c] = [];
      byCat[c].push(t);
    });
    const catLabel = { financial: 'Financial', gl: 'General Ledger', ap: 'Payables', ar: 'Receivables', job: 'Job / Construction', bank: 'Bank' };

    const typeOptions = types.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');
    const projectOptions = [
      '<option value="">All projects</option>',
      ...projects.map((p) => {
        const selected = pid && p.id === pid ? ' selected' : '';
        const num = p.number || String(p.id);
        const label = p.name ? `${num} — ${p.name}` : num;
        return `<option value="${esc(String(p.id))}"${selected}>${esc(label)}</option>`;
      }),
    ].join('');
    const savedList = (custom.reports || []).map((r) =>
      `<li class="flex items-center justify-between gap-2 py-2 border-b border-zinc-800">
        <button type="button" class="text-left text-sm text-emerald-400 hover:underline acct-run-saved" data-id="${r.id}">${esc(r.name)}</button>
        <span class="text-[10px] text-zinc-500">${esc(r.report_type)}</span>
        <button type="button" class="text-xs text-red-400 acct-del-saved" data-id="${r.id}" title="Delete">×</button>
      </li>`
    ).join('');

    return `<div class="acct-reports-layout">
      <div class="acct-reports-sidebar space-y-4">
        <div class="border border-zinc-700 rounded-lg p-3 bg-zinc-800/50">
          <h3 class="text-sm font-medium text-white mb-2">Run report</h3>
          <label class="block text-xs text-zinc-400 mb-1">Report type</label>
          <select id="acctReportType" class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1.5 text-sm mb-2">${typeOptions}</select>
          <div id="acctReportDateFilters" class="space-y-2 mb-2">
            <div><label class="text-xs text-zinc-400">Start</label><input type="date" id="acctReportStart" value="${dates.start}" class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1 text-sm"></div>
            <div><label class="text-xs text-zinc-400">End</label><input type="date" id="acctReportEnd" value="${dates.end}" class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1 text-sm"></div>
          </div>
          <div class="mb-2"><label class="text-xs text-zinc-400">Project (optional)</label>
            <select id="acctReportProject" class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1.5 text-sm">
              ${projectOptions}
            </select>
            <p class="text-[10px] text-zinc-500 mt-0.5">Same jobs as Project Management — filter job cost and project-scoped reports.</p></div>
          <div class="flex flex-wrap gap-2">
            <button type="button" id="acctRunReportBtn" class="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 rounded text-sm">Run</button>
            <button type="button" id="acctExportCsvBtn" class="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded text-sm">Export CSV</button>
          </div>
          <div class="flex flex-col gap-1 mt-2">
            <button type="button" id="acctReportCompare" class="px-3 py-1.5 border border-zinc-600 rounded text-sm text-violet-400">Comparative P&amp;L</button>
            <button type="button" id="acctReportDesigner" class="px-3 py-1.5 border border-zinc-600 rounded text-sm">Report designer</button>
            <button type="button" id="acctReportSchedRun" class="px-3 py-1.5 border border-zinc-600 rounded text-sm text-amber-400">Run scheduled (email)</button>
          </div>
        </div>
        <div class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm font-medium text-white mb-2">Save as custom</h3>
          <input type="text" id="acctCustomReportName" placeholder="Report name" class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1 text-sm mb-2">
          <label class="flex items-center gap-2 text-xs text-zinc-400 mb-2"><input type="checkbox" id="acctCustomFavorite"> Favorite</label>
          <button type="button" id="acctSaveCustomBtn" class="w-full px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded text-sm">Save current filters</button>
        </div>
        <div class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm font-medium text-white mb-2">Saved reports</h3>
          <ul class="text-sm" id="acctSavedReportsList">${savedList || '<li class="text-zinc-500 text-xs">No saved reports yet.</li>'}</ul>
        </div>
        <div class="text-[10px] text-zinc-500 space-y-1">
          ${Object.keys(byCat).map((c) => `<div><span class="text-zinc-400">${esc(catLabel[c] || c)}:</span> ${byCat[c].map((t) => esc(t.name)).join(', ')}</div>`).join('')}
        </div>
      </div>
      <div class="acct-reports-main">
        <h2 class="text-lg font-semibold text-white mb-1 flex-shrink-0">Reporting & Analytics</h2>
        <p class="text-xs text-zinc-500 mb-3 flex-shrink-0">Standard financials, construction bridge audit, and saved custom layouts. Data comes from posted journals and open documents in the built-in ledger.</p>
        <div id="acctReportOutput" class="text-sm text-zinc-300"><p class="text-zinc-500">Choose a report and click Run.</p></div>
      </div>
    </div>`;
  }

  function currentFilters() {
    const filters = {};
    const start = document.getElementById('acctReportStart')?.value;
    const end = document.getElementById('acctReportEnd')?.value;
    const projectRaw = document.getElementById('acctReportProject')?.value;
    if (start) filters.start_date = start;
    if (end) filters.end_date = end;
    if (projectRaw) {
      const id = parseInt(projectRaw, 10);
      if (!Number.isNaN(id)) filters.project_id = id;
    }
    return filters;
  }

  function currentReportType() {
    return document.getElementById('acctReportType')?.value || 'trial_balance';
  }

  function toggleDateFilters() {
    const wrap = document.getElementById('acctReportDateFilters');
    if (!wrap) return;
    wrap.style.display = needsDateRange(currentReportType()) ? 'block' : 'none';
  }

  async function runReportIntoPanel(reportType, filters) {
    const out = document.getElementById('acctReportOutput');
    if (!out) return;
    out.innerHTML = '<p class="text-zinc-500 text-sm">Running…</p>';
    const body = { report_type: reportType, filters: filters || {} };
    const data = await api('/api/accounting/reports/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    out.innerHTML = renderReportBody(data);
  }

  async function exportCsv() {
    const reportType = currentReportType();
    const filters = currentFilters();
    const qs = new URLSearchParams({ type: reportType, format: 'csv' });
    if (filters.start_date) qs.set('start_date', filters.start_date);
    if (filters.end_date) qs.set('end_date', filters.end_date);
    if (filters.project_id) qs.set('project_id', String(filters.project_id));
    const res = await api(`/api/accounting/reports/run?${qs}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `casepm-${reportType}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function bindHandlers() {
    document.getElementById('acctReportType')?.addEventListener('change', toggleDateFilters);
    toggleDateFilters();

    document.getElementById('acctRunReportBtn')?.addEventListener('click', async () => {
      try {
        await runReportIntoPanel(currentReportType(), currentFilters());
      } catch (e) {
        const out = document.getElementById('acctReportOutput');
        if (out) out.innerHTML = `<p class="text-red-400">${esc(e.message)}</p>`;
      }
    });

    document.getElementById('acctExportCsvBtn')?.addEventListener('click', async () => {
      try {
        await exportCsv();
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });

    document.getElementById('acctReportCompare')?.addEventListener('click', async () => {
      const out = document.getElementById('acctReportOutput');
      try {
        const end = document.getElementById('acctReportEnd')?.value || defaultDates().end;
        const pa = end.slice(0, 7);
        const d = new Date(end);
        d.setMonth(d.getMonth() - 1);
        const pb = d.toISOString().slice(0, 7);
        const data = await api(`/api/accounting/reports/comparative?period_a=${pa}&period_b=${pb}`);
        out.innerHTML = `<div class="grid md:grid-cols-3 gap-3 mb-3">
          <div class="bg-zinc-800 border border-zinc-700 rounded p-3"><div class="text-xs text-zinc-500">${esc(pa)} net</div><div class="text-lg">${money(data.net_income_a)}</div></div>
          <div class="bg-zinc-800 border border-zinc-700 rounded p-3"><div class="text-xs text-zinc-500">${esc(pb)} net</div><div class="text-lg">${money(data.net_income_b)}</div></div>
          <div class="bg-zinc-800 border border-zinc-700 rounded p-3"><div class="text-xs text-zinc-500">Variance</div><div class="text-lg">${money(data.variance)}</div></div>
        </div>`;
      } catch (e) {
        out.innerHTML = `<p class="text-red-400">${esc(e.message)}</p>`;
      }
    });

    document.getElementById('acctReportDesigner')?.addEventListener('click', async () => {
      const layouts = await api('/api/accounting/reports/designer/layouts');
      const colsResp = await api('/api/accounting/reports/designer/columns');
      const catalog = colsResp[currentReportType()] || colsResp.trial_balance || [];
      const name = await AD().prompt('Layout name:', 'Trial balance columns', 'Report designer');
      if (!name) return;
      const colFields = catalog.map((col) => ({ key: col, label: col, type: 'checkbox', defaultValue: true }));
      const picked = colFields.length
        ? await AD().form({ title: 'Select columns', fields: colFields })
        : null;
      let cols = catalog;
      if (picked) {
        cols = catalog.filter((col) => picked[col]);
      }
      if (!cols.length) {
        const manual = await AD().prompt('Columns (comma-separated)', catalog.join(','), 'Columns');
        cols = (manual || '').split(',').map((c) => c.trim()).filter(Boolean);
      }
      const rtype = currentReportType();
      const saved = await api('/api/accounting/reports/designer/layouts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          report_type: rtype,
          columns: (cols || ['account_number', 'description', 'balance']),
          parameters: currentFilters(),
          comparative_period_b: document.getElementById('acctReportEnd')?.value?.slice(0, 7),
        }),
      });
      const run = await AD().confirm('Run this layout now?', 'Report designer');
      if (run && saved.layout?.id) {
        const data = await api(`/api/accounting/reports/designer/run/${encodeURIComponent(saved.layout.id)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(currentFilters()),
        });
        const out = document.getElementById('acctReportOutput');
        if (out) {
          out.innerHTML = `<pre class="text-xs overflow-auto max-h-96">${esc(JSON.stringify(data.projected_rows || data.report, null, 2))}</pre>`;
        }
      } else {
        await AD().alert(`${(layouts.layouts || []).length + 1} enhanced layout(s) saved.`, 'success');
      }
    });

    document.getElementById('acctReportSchedRun')?.addEventListener('click', async () => {
      const email = await AD().prompt('Email for new schedule (optional — uses SMTP from Program Settings)', '', 'Schedule report');
      if (email === null) return;
      if (email.trim()) {
        await api('/api/accounting/reports/schedule', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ report_type: currentReportType(), email: email.trim(), cron: '0 6 * * 1' }),
        });
      }
      const r = await api('/api/accounting/reports/run-scheduled', { method: 'POST', body: '{}' });
      const statuses = (r.schedules || []).map((s) => s.status).join(', ') || 'none';
      await AD().alert(`Ran ${r.ran} scheduled job(s). Status: ${statuses}`, 'info');
    });

    document.getElementById('acctSaveCustomBtn')?.addEventListener('click', async () => {
      const name = document.getElementById('acctCustomReportName')?.value?.trim();
      if (!name) {
        await AD().alert('Enter a name for this saved report.', 'warning');
        return;
      }
      try {
        await api('/api/accounting/reports/custom', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name,
            report_type: currentReportType(),
            filters: currentFilters(),
            is_favorite: !!document.getElementById('acctCustomFavorite')?.checked,
          }),
        });
        if (global.CasePMAccounting?.switchModule) global.CasePMAccounting.switchModule('reports');
        else location.reload();
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });

    document.querySelectorAll('.acct-run-saved').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-id');
        const out = document.getElementById('acctReportOutput');
        if (out) out.innerHTML = '<p class="text-zinc-500 text-sm">Running saved report…</p>';
        try {
          const data = await api(`/api/accounting/reports/custom/${id}/run`, { method: 'POST', body: '{}' });
          if (data.custom_report) {
            const sel = document.getElementById('acctReportType');
            if (sel) sel.value = data.custom_report.report_type;
            toggleDateFilters();
          }
          out.innerHTML = renderReportBody(data);
        } catch (e) {
          out.innerHTML = `<p class="text-red-400">${esc(e.message)}</p>`;
        }
      });
    });

    document.querySelectorAll('.acct-del-saved').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-id');
        const ok = await AD().confirm('Delete this saved report?', { title: 'Delete report', danger: true, confirmLabel: 'Delete' });
        if (!ok) return;
        try {
          await api(`/api/accounting/reports/custom/${id}`, { method: 'DELETE' });
          if (global.CasePMAccounting?.switchModule) global.CasePMAccounting.switchModule('reports');
        } catch (e) {
          await AD().alert(e.message, 'error');
        }
      });
    });

    const defaultType = 'trial_balance';
    runReportIntoPanel(defaultType, currentFilters()).catch(() => {});
  }

  async function render() {
    const html = await renderShell();
    return html;
  }

  global.CasePMAccountingReports = { render, bindHandlers, runReportIntoPanel, renderReportBody };
})(window);
