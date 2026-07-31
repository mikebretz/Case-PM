/**
 * All priority chunks — UI wiring for core-5, bank, distribution, payroll, construction.
 */
(function (global) {
  'use strict';

  function H() {
    const A = global.CasePMAccounting || {};
    return { api: A._api, esc: A._esc, money: A._money, switchModule: A.switchModule, projectId: A._projectId, AD: () => global.CasePMAccountingDialog || {} };
  }

  function filterNavByScreens(catalog) {
    const allowed = catalog?.allowed_screens || {};
    if (!Object.keys(allowed).length) return catalog;
    const mods = (catalog.modules || []).filter((m) => {
      const r = m.route || m.id;
      return allowed[r] !== false;
    });
    return { ...catalog, modules: mods };
  }

  async function renderJobCostPanel() {
    const { api, esc, money, projectId } = H();
    const pid = projectId();
    if (!pid) {
      return `<p class="text-zinc-500 text-sm">Select a project in Case PM to view job cost accounting.</p>`;
    }
    const panel = await api(`/api/accounting/jobcost/${pid}/panel`);
    const wip = await api(`/api/accounting/jobcost/${pid}/wip`).catch(() => ({}));
    const rev = panel.revenue_recognition || {};
    const pa = panel.pay_applications || {};
    return `<div class="space-y-4">
      <h2 class="text-lg font-semibold text-white">Project &amp; Job Costing (Accounting)</h2>
      <div class="grid md:grid-cols-4 gap-2 text-sm">
        <div class="bg-zinc-800 border border-zinc-700 rounded p-3">Billed A/R<br><strong class="text-sky-400">${money(panel.billed_ar)}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-3">A/P on job<br><strong class="text-amber-400">${money(panel.committed_ap)}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-3">G/L job net<br><strong>${money(panel.gl_job_cost_net)}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-3">% complete<br><strong>${rev.percent_complete || 0}%</strong></div>
      </div>
      <div class="grid md:grid-cols-3 gap-2 text-xs">
        <div class="bg-zinc-900 border border-zinc-700 rounded p-2">Pay apps: <strong>${pa.count || 0}</strong> · billed <strong>${money(pa.total_billed)}</strong></div>
        <div class="bg-zinc-900 border border-zinc-700 rounded p-2">Retainage held: <strong>${money(pa.total_retainage)}</strong></div>
        <div class="bg-zinc-900 border border-zinc-700 rounded p-2">A/R vs pay app variance: <strong>${money(panel.variance_billed_vs_ar)}</strong></div>
      </div>
      ${(panel.variance_detail?.g702_pending_sync || []).length ? `<p class="text-xs text-amber-400">${panel.variance_detail.g702_pending_sync.length} approved G702 period(s) not yet in A/R — use sync below.</p>` : ''}
      ${(wip.sub_ap_pending || []).length ? `<p class="text-xs text-amber-400">${wip.sub_ap_pending.length} approved sub pay app(s) not yet in A/P.</p>` : ''}
      <div class="text-xs text-zinc-400 border border-zinc-800 rounded p-2">WIP: ${wip.status || '—'} · contract ${money(wip.contract_value)} · ${wip.completion_method || ''} · ${wip.percent_complete || 0}% · over/under <strong>${money(wip.over_under_billing)}</strong></div>
      <div class="flex flex-wrap gap-2 text-xs">
        <a href="${esc(panel.links?.budget || '#')}" class="text-emerald-400 underline">Budget</a>
        <a href="${esc(panel.links?.pay_apps || '#')}" class="text-emerald-400 underline">Pay applications</a>
        <a href="${esc(panel.links?.commitments || '#')}" class="text-emerald-400 underline">Commitments</a>
      </div>
      <button type="button" id="acctJcG702Sync" class="px-3 py-2 text-sm bg-emerald-800 rounded">Sync approved G702 → A/R</button>
      <button type="button" id="acctJcG702SyncAll" class="px-3 py-2 text-sm bg-emerald-900 rounded border border-emerald-700">Sync all pending G702</button>
      <button type="button" id="acctJcSubApSyncAll" class="px-3 py-2 text-sm bg-amber-900 rounded border border-amber-700">Sync all sub pay apps → A/P</button>
      <button type="button" id="acctJcCmtSyncAll" class="px-3 py-2 text-sm bg-sky-900 rounded border border-sky-700">Sync commitments → accounting</button>
      <button type="button" id="acctJcWipAdjust" class="px-3 py-2 text-sm bg-violet-900 rounded border border-violet-700">Post WIP billing adjustment</button>
      <button type="button" id="acctJcCoSyncAll" class="px-3 py-2 text-sm bg-sky-800 rounded border border-sky-700">Sync approved COs → accounting</button>
      <button type="button" id="acctJcProgressAr" class="px-3 py-2 text-sm bg-violet-700 rounded">Create A/R from progress billing</button>
    </div>`;
  }

  function bindJobCostPanel() {
    const { api, AD, switchModule, projectId } = H();
    document.getElementById('acctJcG702Sync')?.addEventListener('click', async () => {
      const pid = projectId();
      const pending = await api(`/api/accounting/jobcost/${pid}/g702-pending`);
      const p = (pending.pending || [])[0];
      if (!p) {
        await AD().alert('No approved G702 periods waiting for A/R sync (or already posted).', 'info');
        return;
      }
      const r = await api(`/api/accounting/jobcost/${pid}/g702-sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ period: p.period }),
      });
      await AD().alert(r.posted ? `Posted A/R for period ${p.period}.` : JSON.stringify(r), 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcG702SyncAll')?.addEventListener('click', async () => {
      const pid = projectId();
      const r = await api(`/api/accounting/jobcost/${pid}/g702-sync-all`, { method: 'POST', body: '{}' });
      await AD().alert(`Posted ${r.posted_count || 0} period(s).${(r.errors || []).length ? ` ${r.errors.length} error(s).` : ''}`, 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcSubApSyncAll')?.addEventListener('click', async () => {
      const pid = projectId();
      const r = await api(`/api/accounting/jobcost/${pid}/sub-ap-sync-all`, { method: 'POST', body: '{}' });
      await AD().alert(`Posted ${r.posted_count || 0} sub pay app(s) to A/P.`, 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcCmtSyncAll')?.addEventListener('click', async () => {
      const pid = projectId();
      const r = await api(`/api/accounting/jobcost/${pid}/commitments-sync-all`, { method: 'POST', body: '{}' });
      await AD().alert(`Posted ${r.posted_count || 0} commitment(s).`, 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcWipAdjust')?.addEventListener('click', async () => {
      const pid = projectId();
      const ok = await AD().confirm('Post a WIP journal entry from the current over/under billing analysis?', 'WIP');
      if (!ok) return;
      const r = await api(`/api/accounting/jobcost/${pid}/wip-adjust`, { method: 'POST', body: '{}' });
      await AD().alert(`WIP batch #${r.journal_batch_id} posted (${r.amount}).`, 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcCoSyncAll')?.addEventListener('click', async () => {
      const pid = projectId();
      const r = await api(`/api/accounting/jobcost/${pid}/co-sync-all`, { method: 'POST', body: '{}' });
      await AD().alert(`Posted ${r.posted_count || 0} change order(s).`, 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcProgressAr')?.addEventListener('click', async () => {
      const pid = projectId();
      const cust = await AD().prompt('Customer id for invoice:', '', 'Progress billing');
      const amt = await AD().prompt('Invoice amount:', '10000', 'Progress billing');
      if (!cust || !amt) return;
      await api('/api/accounting/ar/progress-billing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: parseInt(cust, 10), amount: parseFloat(amt), project_id: pid }),
      });
      switchModule('ar');
    });
  }

  async function bankAutoMatchSection(bankId) {
    if (!bankId) return '';
    const { api, esc } = H();
    const data = await api(`/api/accounting/bank/auto-match?bank_account_id=${bankId}`);
    const rows = (data.suggestions || []).slice(0, 8).map((s) =>
      `<li class="text-xs font-mono">Tx ${s.bank_transaction_id} ↔ ${esc(s.match_type)} #${s.match_id}</li>`
    ).join('');
    return `<div class="mt-3 border border-zinc-700 rounded p-2"><h4 class="text-xs text-zinc-400">Auto-match suggestions</h4>
      <ul>${rows || '<li class="text-zinc-600 text-xs">None</li>'}</ul></div>`;
  }

  async function enhancePaymentsStripe() {
    const { api, esc } = H();
    try {
      const cfg = await api('/api/accounting/payments/stripe-config');
      const el = document.getElementById('acctPpStripeStatus');
      if (el) el.textContent = `Stripe: ${cfg.mode} (${cfg.stripe_configured ? 'configured' : 'not configured'})`;
    } catch (_) { /* ignore */ }
  }

  function bindDistributionExtras(route) {
    const { api, AD, switchModule } = H();
    if (route === 'inventory') {
      document.getElementById('acctIcFifo')?.addEventListener('click', async () => {
        const itemId = await AD().prompt('Item id:', '', 'FIFO issue');
        const qty = await AD().prompt('Quantity:', '1', 'FIFO issue');
        if (!itemId) return;
        await api('/api/accounting/inventory/fifo-issue', {
          method: 'POST',
          body: JSON.stringify({ item_id: parseInt(itemId, 10), qty: parseFloat(qty) }),
        });
        switchModule('inventory');
      });
    }
    if (route === 'po') {
      document.querySelectorAll('.acct-po-voucher').forEach((btn) => {
        btn.addEventListener('click', async () => {
          await api(`/api/accounting/po/orders/${btn.getAttribute('data-id')}/create-ap-invoice`, { method: 'POST', body: '{}' });
          switchModule('ap');
        });
      });
    }
    if (route === 'oe') {
      document.querySelectorAll('.acct-oe-cogs').forEach((btn) => {
        btn.addEventListener('click', async () => {
          await api(`/api/accounting/oe/orders/${btn.getAttribute('data-id')}/ship-cogs`, { method: 'POST', body: '{}' });
          switchModule('gl');
        });
      });
    }
    if (route === 'payroll') {
      document.getElementById('acctPrTaxPkg')?.addEventListener('click', async () => {
        const y = new Date().getFullYear();
        const pkg = await api(`/api/accounting/payroll/tax-package/${y}`);
        await AD().alert(`Tax package: ${(pkg.w2?.employees || []).length} W-2 row(s), 4×941 quarters.`, 'info');
      });
    }
  }

  global.CasePMAcctChunksUI = {
    filterNavByScreens,
    renderJobCostPanel,
    bindJobCostPanel,
    bankAutoMatchSection,
    enhancePaymentsStripe,
    bindDistributionExtras,
  };
})(typeof window !== 'undefined' ? window : globalThis);
