/**
 * Platform & administration — fiscal calendar, locations, security, audit, import/export.
 */
(function (global) {
  'use strict';

  let ctx = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  async function render() {
    const { api, esc } = ctx;
    const [periods, locations, audit, integrity, locale, perms] = await Promise.all([
      api('/api/accounting/platform/fiscal-periods'),
      api('/api/accounting/platform/locations'),
      api('/api/accounting/platform/audit-log'),
      api('/api/accounting/platform/integrity'),
      api('/api/accounting/platform/locale'),
      api('/api/accounting/platform/screen-permissions').catch(() => ({ permissions: {} })),
    ]);
    const openPeriods = (periods.periods || []).filter((p) => p.status === 'Open').length;
    const routes = ['gl', 'ap', 'ar', 'bank', 'payroll', 'reports', 'admin', 'consolidation'];
    const permMap = perms.permissions || {};
    global._acctScreenPermDraft = { ...permMap };
    const permHtml = routes.map((r) =>
      `<label class="flex items-center gap-2"><input type="checkbox" class="acct-plat-perm" data-route="${r}" ${permMap[r] !== false ? 'checked' : ''} /> ${esc(r)}</label>`
    ).join('');
    return `<div class="space-y-6">
      <div class="flex flex-wrap justify-between gap-2">
        <div>
          <h2 class="text-lg font-semibold text-white">Platform &amp; administration</h2>
          <p class="text-xs text-zinc-500 mt-1">Fiscal calendar, locations, G/L security, optional fields, audit, and data tools.</p>
        </div>
        <div class="flex flex-wrap gap-2 text-xs">
          <button type="button" id="acctPlatYearEnd" class="px-3 py-2 border border-zinc-700 rounded-md text-violet-400">Year-end close</button>
          <button type="button" id="acctPlatReporter" class="px-3 py-2 border border-zinc-700 rounded-md text-cyan-400">Financial reporter</button>
          <button type="button" id="acctPlatImportVend" class="px-3 py-2 border border-zinc-700 rounded-md text-zinc-300">Import vendors</button>
          <a href="/api/accounting/platform/export/vendors" class="px-3 py-2 border border-zinc-700 rounded-md text-zinc-300 inline-block">Export vendors</a>
          <button type="button" id="acctPlatGenFy" class="px-3 py-2 border border-zinc-700 rounded-md text-emerald-400">Generate fiscal year</button>
          <button type="button" id="acctPlatAddLoc" class="px-3 py-2 border border-zinc-700 rounded-md text-sky-400">+ Location</button>
          <button type="button" id="acctPlatIntegrity" class="px-3 py-2 border border-zinc-700 rounded-md text-amber-400">Re-run integrity</button>
          <a href="/api/accounting/platform/export/chart" class="px-3 py-2 border border-zinc-700 rounded-md text-zinc-300 inline-block">Export COA</a>
          <button type="button" id="acctPlatImportJe" class="px-3 py-2 border border-zinc-700 rounded-md text-zinc-300">Import journals</button>
          <button type="button" id="acctPlatReopen" class="px-3 py-2 border border-zinc-700 rounded-md text-amber-300">Reopen FY</button>
          <button type="button" id="acctPlatRemediate" class="px-3 py-2 border border-zinc-700 rounded-md text-red-300">Remediate</button>
          <button type="button" id="acctPlatSchedule" class="px-3 py-2 border border-zinc-700 rounded-md text-violet-300">Posting schedule</button>
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
        <p class="text-xs text-zinc-600 mb-2">Restrict accounting routes per role label stored on ledger settings.</p>
        <div id="acctPlatScreenPerms" class="grid sm:grid-cols-2 gap-2 text-xs">${permHtml}</div>
        <button type="button" id="acctPlatSavePerms" class="mt-2 text-xs text-emerald-400">Save permissions</button>
      </section>

      <div class="grid lg:grid-cols-2 gap-4">
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">Fiscal calendar</h3>
          <div class="max-h-48 overflow-y-auto divide-y divide-zinc-800 text-xs">
            ${(periods.periods || []).slice(0, 12).map((p) => `<div class="py-1 flex justify-between">
              <span class="font-mono">${esc(p.period_key)}</span>
              <span class="${p.status === 'Closed' ? 'text-zinc-600' : 'text-emerald-400'}">${esc(p.status)}</span>
            </div>`).join('') || '<p class="text-zinc-600">Generate a fiscal year to begin.</p>'}
          </div>
        </section>
        <section class="border border-zinc-700 rounded-lg p-3">
          <h3 class="text-sm text-zinc-400 mb-2">Locale (multi-language beta)</h3>
          <p class="text-xs text-zinc-500">UI language: <span class="text-zinc-300">${esc(locale.ui_language || 'en')}</span></p>
          <button type="button" id="acctPlatLocale" class="mt-2 text-xs text-violet-400 bg-transparent border-none cursor-pointer">Edit locale</button>
        </section>
      </div>

      <section class="border border-zinc-700 rounded-lg p-3">
        <h3 class="text-sm text-zinc-400 mb-2">Recent audit log</h3>
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
      if (!await AD().confirm({ title: 'Year-end close?', message: `Close FY${y} and post retained earnings?` })) return;
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

    document.getElementById('acctPlatImportVend')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Import vendors CSV',
        fields: [{ key: 'csv', label: 'Paste CSV', type: 'textarea', required: true }],
      });
      if (!data) return;
      await api('/api/accounting/platform/import/vendors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: data.csv }),
      });
      switchModule('admin');
    });

    document.getElementById('acctPlatImportJe')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Import journal CSV',
        fields: [{ key: 'csv', label: 'account_number,debit,credit,description,batch_key', type: 'textarea', required: true }],
      });
      if (!data) return;
      await api('/api/accounting/platform/import/journals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: data.csv }),
      });
      switchModule('admin');
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

    document.getElementById('acctPlatSchedule')?.addEventListener('click', async () => {
      const s = await api('/api/accounting/platform/posting-schedule');
      await AD().alert(`Due: GL ${s.gl_recurring_due}, AP ${s.ap_recurring_due}, AR ${s.ar_recurring_due}`, 'info');
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
      await AD().alert('Screen permissions saved.', 'success');
    });

    document.getElementById('acctPlatLocale')?.addEventListener('click', async () => {
      const loc = await api('/api/accounting/platform/locale');
      const data = await AD().form({
        title: 'Locale settings',
        fields: [
          { key: 'ui_language', label: 'UI language', defaultValue: loc.ui_language || 'en' },
          { key: 'date_format', label: 'Date format', defaultValue: loc.date_format || 'ISO' },
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
