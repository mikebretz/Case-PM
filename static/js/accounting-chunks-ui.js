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
    const [panel, wip, retainage, closeout] = await Promise.all([
      api(`/api/accounting/jobcost/${pid}/panel`),
      api(`/api/accounting/jobcost/${pid}/wip`).catch(() => ({})),
      api(`/api/accounting/jobcost/${pid}/retainage`).catch(() => ({})),
      api(`/api/accounting/jobcost/${pid}/closeout`).catch(() => ({})),
    ]);
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
        <a href="/accounting?module=cost-codes" class="text-emerald-400 underline">Cost code library</a>
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
      <div class="border border-zinc-700 rounded p-3 space-y-2">
        <h3 class="text-sm text-zinc-300">Retainage &amp; closeout (Wave 13)</h3>
        <div class="text-xs text-zinc-400 grid md:grid-cols-3 gap-2">
          <span>Owner (pay apps): <strong>${money(retainage.owner_retainage_pay_apps)}</strong></span>
          <span>Sub (pay apps): <strong>${money(retainage.sub_retainage_pay_apps)}</strong></span>
          <span>A/P retainage: <strong>${money(retainage.ap_retainage_held)}</strong></span>
        </div>
        <div class="flex flex-wrap gap-2 text-xs">
          <button type="button" id="acctJcRetSync" class="px-2 py-1 bg-emerald-900 rounded border border-emerald-700">Sync owner retainage holds</button>
          <button type="button" id="acctJcRetRelease" class="px-2 py-1 bg-violet-900 rounded border border-violet-700">Release retainage → A/R</button>
          <button type="button" id="acctJcCostCodeCsv" class="px-2 py-1 bg-zinc-800 rounded border border-zinc-600">Cost-code profitability CSV</button>
          <button type="button" id="acctJcCloseout" class="px-2 py-1 bg-amber-900 rounded border border-amber-700">Accounting closeout checklist</button>
          <button type="button" id="acctJcReversePost" class="px-2 py-1 bg-red-950 rounded border border-red-800 text-red-300">Reverse construction post</button>
          <button type="button" id="acctJcSageReconcile" class="px-2 py-1 bg-indigo-950 rounded border border-indigo-700">Sage job reconcile</button>
          <button type="button" id="acctJcIntegrationHealth" class="px-2 py-1 bg-teal-950 rounded border border-teal-700 text-teal-200">Integration health</button>
        </div>
        ${(closeout.items || []).length ? `<ul class="text-xs list-disc pl-4 text-amber-300">${(closeout.items || []).map((i) => `<li>${esc(i.label)}</li>`).join('')}</ul>` : ''}
        ${closeout.ready_to_close ? '<p class="text-xs text-emerald-400">No blocking closeout warnings.</p>' : ''}
      </div>
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
    document.getElementById('acctJcRetSync')?.addEventListener('click', async () => {
      const pid = projectId();
      const r = await api(`/api/accounting/jobcost/${pid}/retainage/sync`, { method: 'POST', body: '{}' });
      await AD().alert(`Posted ${r.posted_count || 0} retainage hold(s).`, 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcRetRelease')?.addEventListener('click', async () => {
      const pid = projectId();
      const cust = await AD().prompt('Customer id for retainage release invoice:', '', 'Retainage');
      const amt = await AD().prompt('Release amount:', '', 'Retainage');
      if (!cust || !amt) return;
      const r = await api(`/api/accounting/jobcost/${pid}/retainage/release`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customer_id: parseInt(cust, 10), amount: parseFloat(amt) }),
      });
      await AD().alert(`A/R document #${r.ar_document_id} for ${amt}.`, 'success');
      switchModule('ar');
    });
    document.getElementById('acctJcCostCodeCsv')?.addEventListener('click', async () => {
      const pid = projectId();
      const data = await api(`/api/accounting/jobcost/${pid}/cost-code-profit`);
      const rows = data.rows || [];
      const header = 'cost_code,budget_revised,committed,budget_actual,variance_budget_vs_actual,variance_committed_vs_actual';
      const body = rows.map((r) => [r.cost_code, r.budget_revised, r.committed, r.budget_actual, r.variance_budget_vs_actual, r.variance_committed_vs_actual].join(',')).join('\n');
      const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `cost-code-profit-p${pid}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
    document.getElementById('acctJcCloseout')?.addEventListener('click', async () => {
      const pid = projectId();
      const c = await api(`/api/accounting/jobcost/${pid}/closeout`);
      const lines = (c.items || []).map((i) => `• ${i.label}`).join('\n') || 'No open items.';
      await AD().alert(`${c.ready_to_close ? 'Ready to close.\n' : 'Review before close.\n'}${lines}`, c.ready_to_close ? 'success' : 'warning');
    });
    document.getElementById('acctJcReversePost')?.addEventListener('click', async () => {
      const key = await AD().prompt('Construction post source_key (from AcctPostLink):', '', 'Reverse');
      if (!key) return;
      const reason = await AD().prompt('Reason (optional):', '', 'Reverse');
      const ok = await AD().confirm(`Reverse construction post "${key}"?`, 'Reverse');
      if (!ok) return;
      const r = await api('/api/accounting/construction/reverse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_key: key, reason: reason || '' }),
      });
      await AD().alert(`Reversal batches: ${(r.reversal_batches || []).join(', ') || 'none'}`, 'success');
      switchModule('jobcost');
    });
    document.getElementById('acctJcSageReconcile')?.addEventListener('click', async () => {
      const pid = projectId();
      const r = await api(`/api/accounting/jobcost/${pid}/sage-reconcile`);
      const lines = (r.items || []).map((i) => `• ${i.label}`).join('\n') || 'No variances reported.';
      await AD().alert(`${r.aligned ? 'Aligned with Sage.\n' : 'Review variances.\n'}${lines}`, r.aligned ? 'success' : 'warning');
    });
    document.getElementById('acctJcIntegrationHealth')?.addEventListener('click', async () => {
      const pid = projectId();
      const r = await api(`/api/accounting/integration/health?project_id=${encodeURIComponent(pid)}`);
      const issues = (r.issues || []).map((i) => i.code).join(', ') || 'none';
      await AD().alert(
        `Health ${r.grade || '—'} (${r.score ?? '—'})\nG702 pending: ${JSON.stringify(r.g702_pending || []).slice(0, 120)}\nIssues: ${issues}`,
        (r.score || 0) >= 75 ? 'success' : 'warning',
      );
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

  async function renderConstructionSyncPanel() {
    const { api, esc, money, projectId } = H();
    const pid = projectId();
    if (!pid) {
      return `<p class="text-zinc-500 text-sm">Select a project to manage construction ↔ accounting sync.</p>`;
    }
    const [pending, cutover, parity, gapList, alerts] = await Promise.all([
      api(`/api/accounting/construction/pending-dashboard?project_id=${pid}`),
      api('/api/accounting/sage/cutover-checklist').catch(() => ({})),
      api('/api/accounting/sage/parity-matrix').catch(() => ({})),
      api('/api/accounting/sage/parity-gaps-prioritized').catch(() => ({})),
      api('/api/accounting/sage/go-live-alerts').catch(() => ({})),
    ]);
    const sections = (pending.sections || []).map((s) =>
      `<div class="border border-zinc-700 rounded p-3"><div class="text-sm text-white font-medium">${esc(s.label)} <span class="text-amber-400">(${s.count})</span></div>
        <ul class="text-xs text-zinc-400 mt-1 max-h-24 overflow-y-auto">${(s.items || []).slice(0, 8).map((it) => `<li class="font-mono">${esc(JSON.stringify(it).slice(0, 120))}</li>`).join('') || '<li>—</li>'}</ul></div>`
    ).join('');
    const cutSteps = (cutover.steps || []).map((s) =>
      `<li class="${s.ok ? 'text-emerald-400' : 'text-amber-300'}">${s.ok ? '✓' : '○'} ${esc(s.label)}</li>`
    ).join('');
    const gapRows = (parity.gaps || []).slice(0, 6).map((g) =>
      `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${esc(g.module)}</td><td class="px-2 py-1 text-xs text-zinc-400">${esc(g.gap_notes)}</td></tr>`
    ).join('');
    const priRows = (gapList.gaps || []).slice(0, 8).map((g) =>
      `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${g.rank || '—'}</td><td class="px-2 py-1 font-mono">${esc(g.module)}</td><td class="px-2 py-1 text-xs text-zinc-400">${esc(g.recommended_action)}</td></tr>`
    ).join('');
    return `<div class="space-y-4">
      <h2 class="text-lg font-semibold text-white">Construction sync &amp; Sage operations</h2>
      <p class="text-xs text-zinc-500">Pending posts for project ${pid} · total ${pending.total_pending || 0}</p>
      <div class="grid md:grid-cols-2 gap-3">${sections || '<p class="text-emerald-400 text-sm">No pending construction financial posts.</p>'}</div>
      <div class="flex flex-wrap gap-2">
        <button type="button" id="acctCsSyncAll" class="px-3 py-2 text-sm bg-emerald-800 rounded">Sync all pending</button>
        <button type="button" id="acctCsPlaybook" class="px-3 py-2 text-sm bg-violet-900 rounded">Run cutover playbook</button>
        <button type="button" id="acctCsEmailDigest" class="px-3 py-2 text-sm bg-sky-900 rounded">Email go-live digest</button>
        <button type="button" id="acctCsGapFix" class="px-3 py-2 text-sm bg-amber-900 rounded">Auto-fix top parity gaps</button>
        <button type="button" id="acctCsFinalize" class="px-3 py-2 text-sm bg-emerald-950 rounded">Finalize ops</button>
        <button type="button" id="acctCsOwnerDraw" class="px-3 py-2 text-sm bg-sky-950 rounded">Owner draw package</button>
        <button type="button" id="acctCsWaiverLib" class="px-3 py-2 text-sm bg-zinc-800 rounded">Waiver library</button>
        <button type="button" id="acctCsRefresh" class="px-3 py-2 text-sm bg-zinc-800 rounded">Refresh</button>
      </div>
      <div class="border border-zinc-700 rounded p-3">
        <h3 class="text-sm text-zinc-300 mb-2">Sage cutover ${cutover.ready ? '<span class="text-emerald-400">ready</span>' : '<span class="text-amber-400">incomplete</span>'}</h3>
        <ul class="text-xs list-none space-y-1">${cutSteps}</ul>
      </div>
      <div class="border border-zinc-700 rounded p-3">
        <h3 class="text-sm text-zinc-300 mb-2">Go-live alerts (${alerts.alert_count || 0})</h3>
        <ul class="text-xs text-zinc-400">${(alerts.alerts || []).map((a) => `<li>${esc(a.severity)}: ${esc(a.code)}</li>`).join('') || '<li>None</li>'}</ul>
      </div>
      <div class="border border-zinc-700 rounded p-3 overflow-x-auto">
        <h3 class="text-sm text-zinc-300 mb-2">Sage parity gaps (${parity.gap_count || 0})</h3>
        <table class="w-full text-xs"><thead class="text-zinc-500"><tr><th class="text-left px-2">Module</th><th class="text-left px-2">Note</th></tr></thead><tbody>${gapRows || '<tr><td colspan="2" class="p-2">No critical gaps flagged.</td></tr>'}</tbody></table>
      </div>
      <div class="border border-zinc-700 rounded p-3 overflow-x-auto">
        <h3 class="text-sm text-zinc-300 mb-2">Prioritized gap list (${gapList.gap_count || 0})</h3>
        <table class="w-full text-xs"><thead class="text-zinc-500"><tr><th class="text-left px-2">#</th><th class="text-left px-2">Module</th><th class="text-left px-2">Action</th></tr></thead><tbody>${priRows || '<tr><td colspan="3" class="p-2">Run refresh to build list.</td></tr>'}</tbody></table>
      </div>
    </div>`;
  }

  function bindConstructionSyncPanel() {
    const { api, AD, switchModule, projectId } = H();
    document.getElementById('acctCsSyncAll')?.addEventListener('click', async () => {
      const pid = projectId();
      const ok = await AD().confirm('Post all pending G702, sub AP, commitments, and COs for this project?', 'Sync');
      if (!ok) return;
      await api('/api/accounting/construction/sync-all-pending', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid }),
      });
      await AD().alert('Sync complete.', 'success');
      switchModule('construction-sync');
    });
    document.getElementById('acctCsPlaybook')?.addEventListener('click', async () => {
      const pid = projectId();
      const ok = await AD().confirm('Resolve Sage vendor name conflicts (Sage wins), retry AP push, and flush construction mirror queue?', 'Playbook');
      if (!ok) return;
      const out = await api('/api/accounting/sage/cutover-playbook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid, winner: 'sage' }),
      });
      await AD().alert(`Playbook done — ${out.vendor_resolved || 0} vendor(s) resolved.`, 'success');
      switchModule('construction-sync');
    });
    document.getElementById('acctCsEmailDigest')?.addEventListener('click', async () => {
      const out = await api('/api/accounting/sage/go-live-email-digest', { method: 'POST' });
      const msg = out.sent ? 'Digest email sent to admin notification address.' : `Email not sent (${out.reason || 'unknown'}).`;
      await AD().alert(msg, out.sent ? 'success' : 'info');
    });
    document.getElementById('acctCsGapFix')?.addEventListener('click', async () => {
      const ok = await AD().confirm('Run automated fixes for the top prioritized Sage parity gaps?', 'Auto-fix');
      if (!ok) return;
      await api('/api/accounting/sage/parity-gaps-auto-fix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: 3 }),
      });
      await AD().alert('Auto-fix batch finished.', 'success');
      switchModule('construction-sync');
    });
    document.getElementById('acctCsFinalize')?.addEventListener('click', async () => {
      const ok = await AD().confirm('Apply CRE auto-post (if off), refresh cutover, auto-fix parity gaps, and flush construction queue?', 'Finalize');
      if (!ok) return;
      const out = await api('/api/accounting/platform/finalize-ops', { method: 'POST', body: '{}' });
      const st = out.status || {};
      await AD().alert(
        st.ready_for_daily_ops ? 'Ops finalized — ready for daily use.' : `Finalize complete with ${st.hole_count || 0} item(s) to review.`,
        st.ready_for_daily_ops ? 'success' : 'info',
      );
      switchModule('construction-sync');
    });
    document.getElementById('acctCsOwnerDraw')?.addEventListener('click', async () => {
      const pid = projectId();
      const period = await AD().prompt('G702 period number for owner draw package:', '', 'Owner draw');
      if (period == null || !String(period).trim()) return;
      const out = await api('/api/accounting/construction/owner-draw-package', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid, period_number: String(period).trim() }),
      });
      await AD().alert(`Draw request #${out.draw_request_id} created for client portal.`, 'success');
    });
    document.getElementById('acctCsWaiverLib')?.addEventListener('click', async () => {
      const lib = await api('/api/portal/waiver-library');
      const lines = (lib.companies || []).filter((c) => c.waiver_count).slice(0, 12).map(
        (c) => `${c.name}: ${c.waiver_count} waiver(s)`,
      );
      await AD().alert(lines.join('\n') || 'No waivers indexed yet.', 'info');
    });
    document.getElementById('acctCsRefresh')?.addEventListener('click', () => switchModule('construction-sync'));
  }

  global.CasePMAcctChunksUI = {
    filterNavByScreens,
    renderJobCostPanel,
    bindJobCostPanel,
    renderConstructionSyncPanel,
    bindConstructionSyncPanel,
    bankAutoMatchSection,
    enhancePaymentsStripe,
    bindDistributionExtras,
  };
})(typeof window !== 'undefined' ? window : globalThis);
