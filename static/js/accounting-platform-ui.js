/**
 * Platform & administration — fiscal calendar, locations, security, audit, import/export.
 */
(function (global) {
  'use strict';

  let ctx = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  const MODULE_ROUTES = [
    'dashboard', 'gl', 'ap', 'ar', 'bank', 'tax', 'assets', 'inventory', 'oe', 'po',
    'jobcost', 'payroll', 'payments', 'reports', 'consolidation', 'admin',
  ];

  async function render() {
    const { api, esc } = ctx;
    const [
      periods, locations, audit, integrity, locale, perms, schedule, archives,
      glSec, optFields, secMatrix, revalRuns,
    ] = await Promise.all([
      api('/api/accounting/platform/fiscal-periods'),
      api('/api/accounting/platform/locations'),
      api('/api/accounting/platform/audit-log'),
      api('/api/accounting/platform/integrity'),
      api('/api/accounting/platform/locale'),
      api('/api/accounting/platform/screen-permissions').catch(() => ({ permissions: {} })),
      api('/api/accounting/platform/posting-schedule'),
      api('/api/accounting/platform/fiscal-archives'),
      api('/api/accounting/platform/gl-security'),
      api('/api/accounting/platform/optional-fields'),
      api('/api/accounting/platform/security-matrix'),
      api('/api/accounting/platform/revaluation-runs'),
    ]);
    const openPeriods = (periods.periods || []).filter((p) => p.status === 'Open').length;
    const permMap = perms.permissions || {};
    global._acctScreenPermDraft = { ...permMap };
    const permHtml = MODULE_ROUTES.map((r) =>
      `<label class="flex items-center gap-2"><input type="checkbox" class="acct-plat-perm" data-route="${r}" ${permMap[r] !== false ? 'checked' : ''} /> ${esc(r)}</label>`
    ).join('');

    const scheduleRows = [
      ...(schedule.upcoming?.gl || []).map((x) => ({ ...x, module: 'GL' })),
      ...(schedule.upcoming?.ap || []).map((x) => ({ ...x, module: 'AP' })),
      ...(schedule.upcoming?.ar || []).map((x) => ({ ...x, module: 'AR' })),
    ].slice(0, 20);

    const archiveHtml = (archives.years || []).map((y) =>
      `<div class="flex justify-between py-1 gap-2">
        <span class="font-mono">FY${y.fiscal_year}</span>
        <span class="text-zinc-500">${y.closed_periods}/${y.period_count} closed</span>
        <button type="button" class="text-violet-400 acct-plat-archive-view" data-fy="${y.fiscal_year}">Snapshot</button>
      </div>`
    ).join('') || '<p class="text-zinc-600">No fiscal years generated yet.</p>';

    const glSecHtml = (glSec.rules || []).slice(0, 8).map((r) =>
      `<div class="text-zinc-400">Acct #${esc(r.account_number)} · ${esc(r.access_level)} · ${esc(r.role_key || 'user ' + (r.user_id || '—'))}</div>`
    ).join('') || '<p class="text-zinc-600">No G/L account security rules.</p>';

    const optHtml = (optFields.fields || []).slice(0, 10).map((f) =>
      `<div>${esc(f.entity_type)} · <span class="text-zinc-300">${esc(f.field_key)}</span> — ${esc(f.label)}</div>`
    ).join('') || '<p class="text-zinc-600">No optional field definitions.</p>';

    const revalHtml = (revalRuns.runs || []).slice(0, 8).map((r) =>
      `<div class="flex justify-between gap-2"><span class="font-mono">${esc(r.run_number)}</span>
        <span class="text-zinc-500">${esc((r.period_end || '').slice(0, 10))}</span>
        <span class="${r.status === 'Posted' ? 'text-emerald-500' : 'text-zinc-400'}">${esc(r.status)}</span></div>`
    ).join('') || '<p class="text-zinc-600">No FX revaluation runs yet.</p>';

    const auditField = (audit.entries || []).filter((e) => e.action === 'field_update').slice(0, 8);
    const auditFieldHtml = auditField.map((e) =>
      `<div class="text-zinc-500">${esc(e.entity_type || '')} #${e.entity_id || '—'} · ${esc((e.created_at || '').slice(0, 19))}</div>`
    ).join('') || '<p class="text-zinc-600">Field-level changes appear here when vendors/customers are edited.</p>';

    return `<div class="space-y-6">
      <div class="flex flex-wrap justify-between gap-2">
        <div>
          <h2 class="text-lg font-semibold text-white">Platform &amp; administration</h2>
          <p class="text-xs text-zinc-500 mt-1">Fiscal calendar, locations, G/L security, optional fields, audit, imports, and posting schedules.</p>
        </div>
        <div class="flex flex-wrap gap-2 text-xs">
          <button type="button" id="acctPlatYearEnd" class="px-3 py-2 border border-zinc-700 rounded-md text-violet-400">Year-end close</button>
          <button type="button" id="acctPlatReporter" class="px-3 py-2 border border-zinc-700 rounded-md text-cyan-400">Financial reporter</button>
          <button type="button" id="acctPlatImportHub" class="px-3 py-2 border border-zinc-700 rounded-md text-emerald-400">Import hub</button>
          <button type="button" id="acctPlatGenFy" class="px-3 py-2 border border-zinc-700 rounded-md text-emerald-400">Generate fiscal year</button>
          <button type="button" id="acctPlatAddLoc" class="px-3 py-2 border border-zinc-700 rounded-md text-sky-400">+ Location</button>
          <button type="button" id="acctPlatIntegrity" class="px-3 py-2 border border-zinc-700 rounded-md text-amber-400">Re-run integrity</button>
          <a href="/api/accounting/platform/export/chart" class="px-3 py-2 border border-zinc-700 rounded-md text-zinc-300 inline-block">Export COA</a>
          <button type="button" id="acctPlatReopen" class="px-3 py-2 border border-zinc-700 rounded-md text-amber-300">Reopen FY</button>
          <button type="button" id="acctPlatRemediate" class="px-3 py-2 border border-zinc-700 rounded-md text-red-300">Remediate</button>
          <button type="button" id="acctPlatGlSec" class="px-3 py-2 border border-zinc-700 rounded-md text-zinc-300">+ G/L security</button>
          <button type="button" id="acctPlatOptField" class="px-3 py-2 border border-zinc-700 rounded-md text-zinc-300">+ Optional field</button>
        </div>
      </div>

      <div class="grid md:grid-cols-3 gap-3 text-xs">
        <div class="border border-zinc-700 rounded-lg p-3">
          <div class="text-zinc-500">Fiscal periods</div>
          <div class="text-xl text-white">${(periods.periods || []).length}</div>
          <div class="text-zinc-600">${openPeriods} open</div>
        </div>
        <div class="border border-zinc-700 rounded-lg p-3">
          <div class="text-zinc-500">Locations</div>
          <div class="text-xl text-white">${(locations.locations || []).length}</div>
        </div>
        <div class="border border-zinc-700 rounded-lg p-3 ${integrity.ok ? 'border-emerald-900/40' : 'border-amber-800'}">
          <div class="text-zinc-500">Data integrity</div>
          <div class="${integrity.ok ? 'text-emerald-400' : 'text-amber-400'}">${integrity.ok ? 'OK' : `${integrity.issue_count || 0} issue(s)`}</div>
        </div>
      </div>

      <section class="border border-zinc-700 rounded-lg p-3">
        <h3 class="text-sm text-zinc-400 mb-2">Screen permissions (module access)</h3>
        <p class="text-xs text-zinc-600 mb-2">Toggle routes for this ledger. Enforced on API calls and navigation when catalog loads <code class="text-zinc-500">allowed_screens</code>.</p>
        <div id="acctPlatScreenPerms" class="grid sm:grid-cols-3 lg:grid-cols-4 gap-2 text-xs">${permHtml}</div>
        <button type="button" id="acctPlatSavePerms" class="mt-2 text-xs text-emerald-400">Save permissions</button>
        <p class="text-[10px] text-zinc-600 mt-2">Roles in G/L security matrix: ${esc((secMatrix.roles || []).join(', '))}</p>
      </section>

      <div class="grid lg:grid-cols-2 gap-4">
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">Fiscal calendar</h3>
          <div class="max-h-40 overflow-y-auto divide-y divide-zinc-800 text-xs">
            ${(periods.periods || []).slice(0, 24).map((p) => `<div class="py-1 flex justify-between gap-2">
              <span class="font-mono">${esc(p.period_key)}</span>
              <button type="button" class="acct-plat-period-toggle text-[10px] ${p.status === 'Closed' ? 'text-amber-400' : 'text-emerald-400'}" data-id="${p.id}" data-action="${p.status === 'Closed' ? 'open' : 'close'}">${p.status === 'Closed' ? 'Reopen' : 'Close'}</button>
              <span class="${p.status === 'Closed' ? 'text-zinc-600' : 'text-emerald-400'}">${esc(p.status)}</span>
            </div>`).join('') || '<p class="text-zinc-600">Generate a fiscal year to begin.</p>'}
          </div>
        </section>
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">Fiscal archives</h3>
          <div class="text-xs max-h-40 overflow-y-auto">${archiveHtml}</div>
          <pre id="acctPlatArchiveOut" class="text-[10px] text-zinc-600 mt-2 max-h-24 overflow-auto font-mono"></pre>
        </section>
      </div>

      <section class="border border-zinc-700 rounded-lg p-3">
        <h3 class="text-sm text-zinc-400 mb-2">Posting schedule</h3>
        <p class="text-xs text-zinc-600 mb-2">Due now — GL: <strong class="text-zinc-300">${schedule.gl_recurring_due || 0}</strong> · AP: <strong>${schedule.ap_recurring_due || 0}</strong> · AR: <strong>${schedule.ar_recurring_due || 0}</strong></p>
        <div class="overflow-x-auto text-xs">
          <table class="w-full"><thead class="text-zinc-500"><tr><th class="text-left py-1">Module</th><th class="text-left">Next run</th><th class="text-left">Label</th><th></th></tr></thead>
          <tbody>${scheduleRows.map((r) => `<tr class="border-t border-zinc-800">
            <td class="py-1">${esc(r.module)}</td>
            <td class="${r.due ? 'text-amber-400' : ''}">${esc(r.next_run_date)}</td>
            <td>${esc(String(r.label))}</td>
            <td>${r.due ? '<span class="text-amber-500">Due</span>' : ''}</td>
          </tr>`).join('') || '<tr><td colspan="4" class="text-zinc-600 py-2">No recurring schedules configured.</td></tr>'}
          </tbody></table>
        </div>
      </section>

      <div class="grid lg:grid-cols-2 gap-4">
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">G/L account security</h3>
          <div class="text-xs space-y-1">${glSecHtml}</div>
        </section>
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">Optional fields</h3>
          <div class="text-xs space-y-1">${optHtml}</div>
        </section>
      </div>

      <div class="grid lg:grid-cols-2 gap-4">
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">FX revaluation history</h3>
          <div class="text-xs space-y-1">${revalHtml}</div>
        </section>
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">Locale (multi-language beta)</h3>
          <p class="text-xs text-zinc-500">UI language: <span class="text-zinc-300">${esc(locale.ui_language || 'en')}</span> · dates: ${esc(locale.date_format || 'ISO')}</p>
          <button type="button" id="acctPlatLocale" class="mt-2 text-xs text-violet-400 bg-transparent border-none cursor-pointer">Edit locale</button>
          <a href="/api/accounting/platform/i18n" class="block mt-2 text-xs text-zinc-500 hover:text-emerald-400" target="_blank" rel="noopener">View i18n string pack (JSON)</a>
        </section>
      </div>

      <section class="border border-zinc-700 rounded-lg p-3">
        <h3 class="text-sm text-zinc-400 mb-2">Field-level audit (recent)</h3>
        <div class="text-xs mb-3">${auditFieldHtml}</div>
        <h3 class="text-sm text-zinc-400 mb-2">Activity log</h3>
        <div class="text-xs max-h-40 overflow-y-auto space-y-1">
          ${(audit.entries || []).slice(0, 15).map((e) => `<div class="flex justify-between gap-2 text-zinc-400">
            <span>${esc(e.action)} · ${esc(e.entity_type || '')}</span>
            <span class="text-zinc-600">${esc((e.created_at || '').slice(0, 19))}</span>
          </div>`).join('') || '<p class="text-zinc-600">No entries yet.</p>'}
        </div>
      </section>
    </div>`;
  }

  function bindHandlers() {
    const { api, switchModule } = ctx;

    document.getElementById('acctPlatGenFy')?.addEventListener('click', async () => {
      const y = new Date().getFullYear();
      const data = await AD().form({
        title: 'Generate fiscal periods',
        fields: [{ key: 'fiscal_year', label: 'Fiscal year', defaultValue: String(y), required: true }],
      });
      if (!data) return;
      await api('/api/accounting/platform/fiscal-periods', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fiscal_year: parseInt(data.fiscal_year, 10) }),
      });
      switchModule('admin');
    });

    document.querySelectorAll('.acct-plat-period-toggle').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api('/api/accounting/platform/fiscal-periods', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: btn.getAttribute('data-action'), period_id: parseInt(btn.getAttribute('data-id'), 10) }),
        });
        switchModule('admin');
      });
    });

    document.querySelectorAll('.acct-plat-archive-view').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const fy = btn.getAttribute('data-fy');
        const snap = await api(`/api/accounting/gl/fiscal-archive/${fy}`);
        const out = document.getElementById('acctPlatArchiveOut');
        if (out) {
          out.textContent = `FY${snap.fiscal_year}: ${(snap.periods || []).length} periods, TB lines ${(snap.trial_balance || []).length}, archived ${snap.archived_at || ''}`;
        }
      });
    });

    document.getElementById('acctPlatAddLoc')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'New location',
        fields: [
          { key: 'code', label: 'Code', required: true },
          { key: 'name', label: 'Name', required: true },
        ],
      });
      if (!data) return;
      await api('/api/accounting/platform/locations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      switchModule('admin');
    });

    document.getElementById('acctPlatIntegrity')?.addEventListener('click', () => switchModule('admin'));

    document.getElementById('acctPlatYearEnd')?.addEventListener('click', async () => {
      const y = new Date().getFullYear();
      if (!await AD().confirm(`Close FY${y} and post retained earnings?`)) return;
      await api('/api/accounting/platform/year-end-close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fiscal_year: y }),
      });
      switchModule('admin');
    });

    document.getElementById('acctPlatReporter')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/platform/financial-reporter/run?report_type=cash_flow');
      await AD().alert(`Cash flow (indirect): net change ${r.net_change_cash ?? '—'}`, 'info');
    });

    async function importCsv(path, title, hint) {
      const data = await AD().form({
        title,
        fields: [{ key: 'csv', label: hint, type: 'textarea', required: true }],
      });
      if (!data) return;
      await api(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: data.csv }),
      });
      switchModule('admin');
    }

    document.getElementById('acctPlatImportHub')?.addEventListener('click', async () => {
      const pick = await AD().select({
        title: 'Import hub',
        message: 'Choose import type',
        items: [
          { value: 'vendors', label: 'Vendors (CSV)' },
          { value: 'customers', label: 'Customers (CSV)' },
          { value: 'journals', label: 'Journal lines (CSV)' },
          { value: 'chart', label: 'Chart of accounts (CSV)' },
          { value: 'open_ap', label: 'Open A/P documents (CSV)' },
          { value: 'open_ar', label: 'Open A/R documents (CSV)' },
        ],
        submitLabel: 'Continue',
      });
      if (!pick) return;
      const map = {
        vendors: ['/api/accounting/platform/import/vendors', 'Import vendors', 'code,name,terms,email'],
        customers: ['/api/accounting/platform/import/customers', 'Import customers', 'code,name,terms,email'],
        journals: ['/api/accounting/platform/import/journals', 'Import journals', 'account_number,debit,credit,description,batch_key'],
        chart: ['/api/accounting/platform/import/chart', 'Import COA', 'account_number,description,account_type'],
        open_ap: ['/api/accounting/platform/import/open-ap', 'Import open AP', 'vendor_code,document_number,amount,due_date'],
        open_ar: ['/api/accounting/platform/import/open-ar', 'Import open AR', 'customer_code,document_number,amount,due_date'],
      };
      const [path, title, hint] = map[pick.value] || [];
      if (path) await importCsv(path, title, hint);
    });

    document.getElementById('acctPlatReopen')?.addEventListener('click', async () => {
      const y = new Date().getFullYear();
      await api('/api/accounting/platform/year-end-reopen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fiscal_year: y }),
      });
      switchModule('admin');
    });

    document.getElementById('acctPlatRemediate')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/platform/integrity/remediate', { method: 'POST' });
      await AD().alert(`Removed ${(r.removed_empty_batches || []).length} empty batch(es).`, 'info');
      switchModule('admin');
    });

    document.getElementById('acctPlatGlSec')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'G/L account security rule',
        fields: [
          { key: 'account_id', label: 'G/L account ID', required: true },
          { key: 'role_key', label: 'Role key (e.g. accounting_user)', defaultValue: 'accounting_user' },
          { key: 'access_level', label: 'Access (none/view/post)', defaultValue: 'view' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/platform/gl-security', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: parseInt(data.account_id, 10),
          role_key: data.role_key,
          access_level: data.access_level,
        }),
      });
      switchModule('admin');
    });

    document.getElementById('acctPlatOptField')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Optional field definition',
        fields: [
          { key: 'entity_type', label: 'Entity (vendor/customer)', defaultValue: 'vendor', required: true },
          { key: 'field_key', label: 'Field key', required: true },
          { key: 'label', label: 'Label', required: true },
        ],
      });
      if (!data) return;
      await api('/api/accounting/platform/optional-fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      switchModule('admin');
    });

    document.getElementById('acctPlatSavePerms')?.addEventListener('click', async () => {
      const permissions = {};
      document.querySelectorAll('.acct-plat-perm').forEach((el) => {
        permissions[el.getAttribute('data-route')] = el.checked;
      });
      await api('/api/accounting/platform/screen-permissions', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissions }),
      });
      await AD().alert('Screen permissions saved. Reload accounting to refresh navigation.', 'success');
    });

    document.getElementById('acctPlatLocale')?.addEventListener('click', async () => {
      const loc = await api('/api/accounting/platform/locale');
      const data = await AD().form({
        title: 'Locale settings',
        fields: [
          { key: 'ui_language', label: 'UI language', defaultValue: loc.ui_language || 'en' },
          { key: 'date_format', label: 'Date format', defaultValue: loc.date_format || 'ISO' },
          { key: 'number_format', label: 'Number format', defaultValue: loc.number_format || 'US' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/platform/locale', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      switchModule('admin');
    });
  }

  global.CasePMAcctPlatformUI = {
    init(c) {
      ctx = c;
    },
    render,
    bindHandlers,
  };
})(typeof window !== 'undefined' ? window : global);
