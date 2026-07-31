/**
 * Waves 1–7 UI: Plaid Link, Sage hybrid, compliance calendar, report designer depth.
 */
(function (global) {
  'use strict';

  let ctx = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  function loadPlaidScript() {
    return new Promise((resolve, reject) => {
      if (global.Plaid) {
        resolve(global.Plaid);
        return;
      }
      const s = document.createElement('script');
      s.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';
      s.onload = () => resolve(global.Plaid);
      s.onerror = () => reject(new Error('Plaid Link script failed to load'));
      document.head.appendChild(s);
    });
  }

  async function bindPlaidLink(btnId) {
    const btn = document.getElementById(btnId);
    if (!btn || !ctx) return;
    btn.addEventListener('click', async () => {
      try {
        const { api } = ctx;
        const tok = await api('/api/accounting/integrations/plaid/link-token', { method: 'POST', body: '{}' });
        if (!tok.link_token) {
          await AD().alert(tok.message || 'Plaid not configured (PLAID_CLIENT_ID / PLAID_SECRET).', 'warning');
          return;
        }
        const Plaid = await loadPlaidScript();
        const handler = Plaid.create({
          token: tok.link_token,
          onSuccess: async (public_token) => {
            await api('/api/accounting/integrations/plaid/exchange', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ public_token }),
            });
            await AD().alert('Bank account linked via Plaid.', 'success');
            if (global.CasePMAcctTierUI?.mountAdminIntegrations) {
              await global.CasePMAcctTierUI.mountAdminIntegrations();
            }
          },
        });
        handler.open();
      } catch (e) {
        await AD().alert(e.message || 'Plaid Link failed', 'error');
      }
    });
  }

  async function sageHybridSection(st) {
    const { esc } = ctx;
    const h = st.sage_hybrid || {};
    const log = (h.last_sync || []).slice().reverse().map((e) =>
      `<li class="text-[10px] text-zinc-500">${esc(e.at)} · ${esc(e.direction || '')} ${esc(e.entity || '')} (${e.count || ''})</li>`
    ).join('') || '<li class="text-zinc-600">No sync log yet.</li>';
    return `<div class="border border-zinc-700 rounded p-2 text-xs space-y-2">
      <div class="text-zinc-400">Sage hybrid</div>
      <div>System of record: <strong class="text-zinc-200">${esc(h.system_of_record || 'casepm')}</strong>
        · Policy: <strong>${esc(h.conflict_policy || 'casepm_wins')}</strong>
        · Export queue: ${h.export_queue_size || 0}</div>
      <div class="flex flex-wrap gap-1">
        <button type="button" id="acctSagePushVendors" class="px-2 py-0.5 border border-zinc-600 rounded text-emerald-400">Push vendors</button>
        <button type="button" id="acctSagePushApLive" class="px-2 py-0.5 border border-zinc-600 rounded text-rose-400">Push AP live</button>
        <button type="button" id="acctSageConflicts" class="px-2 py-0.5 border border-zinc-600 rounded text-sky-400">Vendor conflicts</button>
        <button type="button" id="acctSageGlConflicts" class="px-2 py-0.5 border border-zinc-600 rounded text-violet-400">G/L conflicts</button>
        <button type="button" id="acctSagePullAp" class="px-2 py-0.5 border border-zinc-600 rounded text-cyan-400">Pull open AP</button>
        <button type="button" id="acctSageInbox" class="px-2 py-0.5 border border-zinc-600 rounded text-orange-400">Exception inbox</button>
        <button type="button" id="acctSagePullAr" class="px-2 py-0.5 border border-zinc-600 rounded text-emerald-300">Pull open AR</button>
        <button type="button" id="acctSageMirrorCov" class="px-2 py-0.5 border border-indigo-700 rounded text-indigo-300">Mirror coverage</button>
        <button type="button" id="acctSagePullCust" class="px-2 py-0.5 border border-zinc-600 rounded text-cyan-300">Pull customers</button>
        <button type="button" id="acctSagePushCust" class="px-2 py-0.5 border border-zinc-600 rounded text-cyan-400">Push customers</button>
        <button type="button" id="acctSagePushArLive" class="px-2 py-0.5 border border-rose-700 rounded text-rose-300">Push AR live</button>
        <button type="button" id="acctSagePushApPay" class="px-2 py-0.5 border border-amber-800 rounded text-amber-300">Push AP payments</button>
        <button type="button" id="acctSagePushGl" class="px-2 py-0.5 border border-violet-800 rounded text-violet-300">Push G/L batches</button>
        <button type="button" id="acctSagePullBanks" class="px-2 py-0.5 border border-zinc-600 rounded">Pull banks</button>
        <button type="button" id="acctSagePullTax" class="px-2 py-0.5 border border-zinc-600 rounded">Pull tax groups</button>
        <button type="button" id="acctSageDistQueue" class="px-2 py-0.5 border border-zinc-600 rounded">Queue PO export</button>
        <button type="button" id="acctSagePushArRcp" class="px-2 py-0.5 border border-emerald-800 rounded text-emerald-200">Push AR receipts</button>
        <button type="button" id="acctSagePortfolio" class="px-2 py-0.5 border border-indigo-800 rounded text-indigo-200">Portfolio reconcile</button>
        <button type="button" id="acctSageDistEx" class="px-2 py-0.5 border border-amber-900 rounded text-amber-200">Dist exceptions</button>
        <button type="button" id="acctSageYearVar" class="px-2 py-0.5 border border-violet-900 rounded text-violet-200">Year-end variance</button>
        <button type="button" id="acctSagePullArRcp2" class="px-2 py-0.5 border border-cyan-900 rounded text-cyan-200">Pull AR cash</button>
        <button type="button" id="acctSageSegVal" class="px-2 py-0.5 border border-zinc-600 rounded">Validate segments</button>
        <button type="button" id="acctSageRetry" class="px-2 py-0.5 border border-orange-900 rounded text-orange-200">Retry inbox</button>
        <button type="button" id="acctSageDrift" class="px-2 py-0.5 border border-pink-900 rounded text-pink-200">Drift dashboard</button>
        <button type="button" id="acctSageFlushC" class="px-2 py-0.5 border border-zinc-600 rounded">Flush CRE queue</button>
        <button type="button" id="acctSageOps" class="px-2 py-0.5 border border-zinc-600 rounded text-zinc-300">Ops dashboard</button>
        <button type="button" id="acctSagePolicyCasepm" class="px-2 py-0.5 border border-zinc-600 rounded">SOR: Case PM</button>
        <button type="button" id="acctSagePolicySage" class="px-2 py-0.5 border border-zinc-600 rounded">SOR: Sage</button>
        <button type="button" id="acctSageProfilePack" class="px-2 py-0.5 border border-teal-900 rounded text-teal-200">Apply CRE pack</button>
        <button type="button" id="acctSageSyncHealth" class="px-2 py-0.5 border border-teal-800 rounded text-teal-300">Sync health</button>
        <button type="button" id="acctSageDriftPanel" class="px-2 py-0.5 border border-pink-800 rounded text-pink-300">Drift panel</button>
        <button type="button" id="acctSageReadOnly" class="px-2 py-0.5 border border-red-900 rounded text-red-300">Sage read-only</button>
        <button type="button" id="acctMonthCloseWiz" class="px-2 py-0.5 border border-amber-700 rounded text-amber-200">Month-close wizard</button>
        <button type="button" id="acctSageTaxPush" class="px-2 py-0.5 border border-lime-900 rounded text-lime-200">Push line tax</button>
        <button type="button" id="acctSagePullPo" class="px-2 py-0.5 border border-lime-800 rounded text-lime-300">Pull PO status</button>
        <button type="button" id="acctSageFaPull" class="px-2 py-0.5 border border-sky-900 rounded text-sky-200">Pull FA</button>
        <button type="button" id="acctSagePrPull" class="px-2 py-0.5 border border-sky-800 rounded text-sky-300">Pull PR employees</button>
        <button type="button" id="acctSageMultiCo" class="px-2 py-0.5 border border-indigo-900 rounded text-indigo-200">Multi-co health</button>
        <button type="button" id="acctCreQueue" class="px-2 py-0.5 border border-orange-900 rounded text-orange-200">CRE queue</button>
        <button type="button" id="acctSageOpsRunbook" class="px-2 py-0.5 border border-zinc-500 rounded text-zinc-200">Ops runbook</button>
        <button type="button" id="acctSageReportPack" class="px-2 py-0.5 border border-violet-900 rounded text-violet-200">Schedule reports</button>
        <button type="button" id="acctSageBkPull" class="px-2 py-0.5 border border-cyan-900 rounded text-cyan-200">Pull BK</button>
        <button type="button" id="acctSageBkReconEx" class="px-2 py-0.5 border border-cyan-800 rounded text-cyan-300">BK exceptions</button>
        <button type="button" id="acctSageApPayAck" class="px-2 py-0.5 border border-rose-900 rounded text-rose-200">AP payment ack</button>
        <button type="button" id="acctCrePortfolio" class="px-2 py-0.5 border border-orange-800 rounded text-orange-300">CRE portfolio</button>
        <button type="button" id="acctDistPoReceipts" class="px-2 py-0.5 border border-lime-900 rounded text-lime-300">Pull PO receipts</button>
        <button type="button" id="acctThreeWayRpt" class="px-2 py-0.5 border border-amber-900 rounded text-amber-300">3-way report</button>
      </div>
      <ul class="max-h-20 overflow-y-auto">${log}</ul>
    </div>`;
  }

  function bindSageHybrid() {
    const { api } = ctx;
    document.getElementById('acctSagePushVendors')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-vendors', { method: 'POST', body: '{}' });
      await AD().alert(`Pushed ${r.pushed || 0} vendor(s) (${r.mode || ''}).`, 'info');
    });
    document.getElementById('acctSagePushAp')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-open-ap', { method: 'POST', body: '{}' });
      await AD().alert(`Queued ${r.queued || 0} open AP document(s).`, 'info');
    });
    document.getElementById('acctSagePushApLive')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-open-ap-live', { method: 'POST', body: '{}' });
      const errN = r.error_count || 0;
      const errLines = (r.errors || []).slice(0, 5).map((e) => `${e.document_number}: ${e.error || e.mode || 'failed'}`).join('\n');
      await AD().alert(
        `Live push: ${r.pushed || 0} document(s).${errN ? ` Errors: ${errN}\n${errLines}` : ''}`,
        errN ? 'warning' : 'info',
      );
    });
    document.getElementById('acctSageGlConflicts')?.addEventListener('click', async () => {
      const c = await api('/api/accounting/sage/conflicts/gl');
      const lines = (c.conflicts || []).slice(0, 15).map(
        (x) => `${x.account_number}: ${x.type} — local "${x.local_name}" vs sage "${x.sage_name || '—'}"`,
      ).join('\n');
      await AD().alert(lines || 'No G/L account conflicts detected.', (c.conflicts || []).length ? 'warning' : 'success');
    });
    document.getElementById('acctSagePullAp')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/pull-open-ap', { method: 'POST', body: '{}' });
      await AD().alert(`Imported ${r.created || 0} open AP invoice(s) from Sage (${r.skipped || 0} skipped).`, 'info');
    });
    document.getElementById('acctSageInbox')?.addEventListener('click', async () => {
      const box = await api('/api/accounting/sage/exceptions');
      const lines = [
        `Vendor conflicts: ${(box.vendor_conflicts || []).length}`,
        `G/L conflicts: ${(box.gl_conflicts || []).length}`,
        `AP push errors: ${(box.ap_push_errors || []).length}`,
        `Export queue: ${box.export_queue_size || 0}`,
      ].join('\n');
      await AD().alert(lines, 'info');
    });
    document.getElementById('acctSagePullAr')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/pull-open-ar', { method: 'POST', body: '{}' });
      await AD().alert(`Imported ${r.created || 0} AR invoice(s).`, 'info');
    });
    document.getElementById('acctSageMirrorCov')?.addEventListener('click', async () => {
      const c = await api('/api/accounting/sage/mirror/coverage');
      const lines = (c.modules || []).filter((m) => m.mirror_pull || m.mirror_push).slice(0, 12).map(
        (m) => `${m.code}: pull=${m.mirror_pull ? 'Y' : 'n'} push=${m.mirror_push ? 'Y' : 'n'}`,
      ).join('\n');
      await AD().alert(lines || 'No mirror capabilities.', 'info');
    });
    document.getElementById('acctSagePullCust')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/pull-customers', { method: 'POST', body: '{}' });
      await AD().alert(`Customers: ${r.created || 0} created, ${r.updated || 0} updated.`, 'info');
    });
    document.getElementById('acctSagePushCust')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-customers', { method: 'POST', body: '{}' });
      await AD().alert(`Pushed ${r.pushed || 0} customer(s). Errors: ${r.error_count || 0}.`, 'info');
    });
    document.getElementById('acctSagePushArLive')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-open-ar-live', { method: 'POST', body: '{}' });
      await AD().alert(`AR live: ${r.pushed || 0}. Errors: ${r.error_count || 0}.`, r.error_count ? 'warning' : 'info');
    });
    document.getElementById('acctSagePushApPay')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-ap-payments', { method: 'POST', body: '{}' });
      await AD().alert(`AP payment batches processed: ${r.processed || 0}.`, 'info');
    });
    document.getElementById('acctSagePushGl')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-gl-batches', { method: 'POST', body: '{}' });
      await AD().alert(`G/L batches processed: ${r.processed || 0}.`, 'info');
    });
    document.getElementById('acctSagePullBanks')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/pull-banks', { method: 'POST', body: '{}' });
      await AD().alert(`Bank accounts created: ${r.created || 0}.`, 'info');
    });
    document.getElementById('acctSagePullTax')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/pull-tax-groups', { method: 'POST', body: '{}' });
      await AD().alert(`Tax groups imported: ${r.imported || 0}.`, 'info');
    });
    document.getElementById('acctSageDistQueue')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/distribution/queue-export', { method: 'POST', body: '{}' });
      await AD().alert(`Queued ${r.queued || 0} PO(s). Queue size ${r.queue_size || 0}.`, 'info');
    });
    document.getElementById('acctSagePushArRcp')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/push-ar-receipts', { method: 'POST', body: '{}' });
      await AD().alert(`AR receipts processed: ${r.processed || 0}.`, 'info');
    });
    document.getElementById('acctSagePortfolio')?.addEventListener('click', async () => {
      const d = await api('/api/accounting/sage/portfolio/dashboard');
      await AD().alert(`${d.warning_count || 0} project(s) with Sage variance warnings (of ${(d.projects || []).length} checked).`, 'info');
    });
    document.getElementById('acctSageDistEx')?.addEventListener('click', async () => {
      const d = await api('/api/accounting/sage/distribution/exceptions');
      await AD().alert(`Distribution errors: ${(d.distribution_errors || []).length}. Queue: ${d.distribution_queue_size || 0}.`, 'info');
    });
    document.getElementById('acctSageYearVar')?.addEventListener('click', async () => {
      const yr = new Date().getFullYear();
      const v = await api(`/api/accounting/sage/compliance/year-end-extended?tax_year=${yr}`);
      await AD().alert(`Year ${yr}: W-2 rows ${v.w2_rows}. Sage sync issues ${v.sage_sync_issues}. 1099 vendors ${v['1099_vendor_count']}.`, v.ready ? 'success' : 'warning');
    });
    document.getElementById('acctSagePullArRcp2')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/pull-ar-receipts', { method: 'POST', body: '{}' });
      await AD().alert(`Applied ${r.applied || 0} receipt line(s).`, 'info');
      const ap = await api('/api/accounting/sage/sync/pull-ap-status', { method: 'POST', body: '{}' });
      await AD().alert(`AP status updated: ${ap.updated || 0} document(s).`, 'info');
    });
    document.getElementById('acctSageSegVal')?.addEventListener('click', async () => {
      const v = await api('/api/accounting/sage/segment-map/validate');
      await AD().alert(v.ok ? 'Segment map OK vs Sage GL.' : `Missing in Sage: ${(v.missing_in_sage || []).slice(0, 8).join(', ')}`, v.ok ? 'success' : 'warning');
    });
    document.getElementById('acctSageRetry')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/retry-inbox', { method: 'POST', body: '{}' });
      await AD().alert(r.skipped ? `Skipped: ${r.reason}` : 'Retried AP/AR push.', 'info');
    });
    document.getElementById('acctSageDrift')?.addEventListener('click', async () => {
      const d = await api('/api/accounting/sage/drift/dashboard');
      const inbox = d.inbox || {};
      await AD().alert(
        `Open AR ${d.open_ar} · AP ${d.open_ap} · parity warnings ${d.parity_warning_count} · AP push errors ${(inbox.ap_push_errors || []).length}`,
        'info',
      );
    });
    document.getElementById('acctSageProfilePack')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/profile-packs/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pack_id: 'sage300_cre_2024' }),
      });
      await AD().alert(`Profile pack applied: ${r.pack_id || 'sage300_cre_2024'}.`, 'success');
    });
    document.getElementById('acctSageSyncHealth')?.addEventListener('click', async () => {
      const h = await api('/api/accounting/sage/sync-health');
      await AD().alert(`Sage sync health: ${h.grade} (${h.score}/100).`, h.score >= 75 ? 'success' : 'warning');
    });
    document.getElementById('acctSageDriftPanel')?.addEventListener('click', async () => {
      const p = await api('/api/accounting/sage/drift/panel');
      const health = p.health || {};
      const dash = p.dashboard || {};
      await AD().alert(
        `Health ${health.grade || '—'} (${health.score ?? '—'}) · open AR ${dash.open_ar} · AP ${dash.open_ap} · CRE queue ${(p.construction_queue || []).length}`,
        'info',
      );
    });
    document.getElementById('acctSageReadOnly')?.addEventListener('click', async () => {
      const cur = await api('/api/accounting/sage/read-only');
      const enable = !cur.enabled;
      const ok = await AD().confirm(
        enable ? 'Enable Sage read-only mode? Local GL posting will be blocked.' : 'Disable Sage read-only mode?',
        'Read-only',
      );
      if (!ok) return;
      await api('/api/accounting/sage/read-only', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enable }),
      });
      await AD().alert(enable ? 'Read-only mode ON.' : 'Read-only mode OFF.', enable ? 'warning' : 'success');
    });
    document.getElementById('acctMonthCloseWiz')?.addEventListener('click', async () => {
      const w = await api('/api/accounting/cash/month-close-wizard');
      const lines = (w.steps || []).map((s) => `${s.done ? '✓' : '○'} ${s.label}`).join('\n');
      await AD().alert(`${w.ready ? 'Ready to close.' : 'Not ready.'}\n${lines}`, w.ready ? 'success' : 'warning');
    });
    document.getElementById('acctSageTaxPush')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/tax/push-batch', { method: 'POST', body: JSON.stringify({ document_type: 'ap' }) });
      await AD().alert(`Tax push: ${r.pushed || 0} posted, ${r.errors || 0} errors.`, (r.errors || 0) ? 'warning' : 'success');
    });
    document.getElementById('acctSagePullPo')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/distribution/pull-po', { method: 'POST', body: '{}' });
      await AD().alert(`PO statuses updated: ${r.updated || 0}.`, 'info');
    });
    document.getElementById('acctSageFaPull')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/fa/pull', { method: 'POST', body: '{}' });
      await AD().alert(`FA pull — created ${r.created || 0}, updated ${r.updated || 0}.`, 'info');
    });
    document.getElementById('acctSagePrPull')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/pr/pull-employees', { method: 'POST', body: '{}' });
      await AD().alert(`PR employees cached: ${r.imported || 0}.`, 'info');
    });
    document.getElementById('acctSageMultiCo')?.addEventListener('click', async () => {
      const h = await api('/api/accounting/sage/platform/multi-company-health');
      await AD().alert(`Avg sync health ${h.average_score || '—'} across ${(h.companies || []).length} company row(s).`, 'info');
    });
    document.getElementById('acctCreQueue')?.addEventListener('click', async () => {
      const q = await api('/api/accounting/sage/construction/queue');
      await AD().alert(`CRE queue: ${q.queue_size || 0} item(s), ${q.stuck_count || 0} stuck.`, (q.stuck_count || 0) ? 'warning' : 'info');
    });
    document.getElementById('acctSageOpsRunbook')?.addEventListener('click', async () => {
      const d = await api('/api/accounting/sage/ops/runbook');
      const h = d.health || {};
      await AD().alert(`Ops runbook — health ${h.grade || '—'} (${h.score ?? '—'}), CRE queue ${d.construction_queue?.queue_size ?? '—'}.`, 'info');
    });
    document.getElementById('acctSageReportPack')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/report-packs/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pack_id: 'month_end_core' }),
      });
      await AD().alert(`Scheduled ${(r.scheduled || []).length} report(s) from pack ${r.pack_id || 'month_end_core'}.`, 'success');
    });
    document.getElementById('acctSageBkPull')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/bk/pull', { method: 'POST', body: '{}' });
      await AD().alert(`BK imported: ${r.imported || 0} (${r.version || 1}).`, 'info');
    });
    document.getElementById('acctSageBkReconEx')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/bank/sage-recon/exceptions');
      await AD().alert(`BK reconciliation exceptions: ${r.count || 0}.`, (r.count || 0) ? 'warning' : 'success');
    });
    document.getElementById('acctSageApPayAck')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/ap/payment-ack', { method: 'POST', body: '{}' });
      await AD().alert(`AP payments updated: ${r.updated || 0}.`, 'info');
    });
    document.getElementById('acctCrePortfolio')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/cre/portfolio-variance');
      await AD().alert(`Portfolio checked: ${(r.projects || []).length} project(s), warnings ${r.warning_count || 0}.`, 'info');
    });
    document.getElementById('acctDistPoReceipts')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/distribution/po-receipts/pull', { method: 'POST', body: '{}' });
      await AD().alert(`PO receipt lines: ${r.lines || 0}.`, 'info');
    });
    document.getElementById('acctThreeWayRpt')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/ap/three-way-vendor-report');
      await AD().alert(`3-way matched ${r.matched || 0}, exceptions ${r.exception_count || 0}.`, 'info');
    });
    document.getElementById('acctSageFlushC')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/construction/flush-queue', { method: 'POST', body: '{}' });
      await AD().alert(`Processed ${r.processed || 0} · errors ${r.errors || 0} · remaining ${r.remaining || 0}`, 'info');
    });
    document.getElementById('acctSageOps')?.addEventListener('click', async () => {
      const d = await api('/api/accounting/sage/mirror/dashboard');
      const p = d.pending || {};
      await AD().alert(
        `Pending AR push: ${p.open_ar_pending_push || 0}. AP: ${p.open_ap_pending_push || 0}. Inbox AP errors: ${(d.inbox?.ap_push_errors || []).length}`,
        'info',
      );
    });
    document.getElementById('acctSageConflicts')?.addEventListener('click', async () => {
      const c = await api('/api/accounting/sage/conflicts/vendors');
      const lines = (c.conflicts || []).slice(0, 15).map((x) => `${x.code}: ${x.type} — local "${x.local_name}" vs sage "${x.sage_name || '—'}"`).join('\n');
      if (!(c.conflicts || []).length) {
        await AD().alert('No vendor conflicts detected.', 'success');
        return;
      }
      const first = c.conflicts[0];
      const useSage = await AD().confirm(`Resolve ${first.code} using Sage name "${first.sage_name}"?`, 'Conflict');
      if (useSage) {
        await api('/api/accounting/sage/conflicts/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: first.code, winner: 'sage', sage_name: first.sage_name }),
        });
      }
      await AD().alert(lines || 'Done', 'info');
    });
    const policy = async (sor) => {
      await api('/api/accounting/sage/hybrid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_of_record: sor, conflict_policy: sor === 'sage' ? 'sage_wins' : 'casepm_wins' }),
      });
      await global.CasePMAcctTierUI?.mountAdminIntegrations?.();
    };
    document.getElementById('acctSagePolicyCasepm')?.addEventListener('click', () => policy('casepm'));
    document.getElementById('acctSagePolicySage')?.addEventListener('click', () => policy('sage'));
  }

  async function complianceCalendarHtml() {
    const { api, esc } = ctx;
    const cal = await api('/api/accounting/compliance/calendar');
    const rows = (cal.deadlines || []).map((d) =>
      `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${esc(d.form)}</td><td class="px-2 py-1">${esc(d.label)}</td>
        <td class="px-2 py-1">${esc(d.due)}</td><td class="px-2 py-1 text-${d.status === 'past_due' ? 'red' : d.status === 'due_soon' ? 'amber' : 'zinc'}-400">${esc(d.status)}</td></tr>`
    ).join('');
    return `<div class="border border-zinc-700 rounded p-2 text-xs mt-2">
      <div class="flex justify-between items-center mb-1"><span class="text-zinc-400">Filing calendar ${cal.tax_year}</span>
        <button type="button" id="acctW2Amend" class="text-violet-400">W-2 amendment pkg</button></div>
      <div class="flex flex-wrap gap-2 mt-2">
        <button type="button" id="acctEfileTransmit" class="text-emerald-400">Log e-file transmit</button>
        <button type="button" id="acctEfileLog" class="text-zinc-400">Transmit log</button>
        <button type="button" id="acctComplianceRemind" class="text-amber-400">Email reminders</button>
      </div>
      <table class="w-full mt-2"><thead><tr class="text-zinc-500"><th class="text-left px-2">Form</th><th class="text-left px-2">Item</th><th class="text-left px-2">Due</th><th class="text-left px-2">Status</th></tr></thead><tbody>${rows}</tbody></table>
    </div>`;
  }

  function bindComplianceCalendar() {
    document.getElementById('acctW2Amend')?.addEventListener('click', async () => {
      const yr = new Date().getFullYear() - 1;
      await ctx.api('/api/accounting/compliance/amendment/w2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tax_year: yr, reason: 'User-initiated amendment' }),
      });
      global.open(`/api/accounting/compliance/w2-efile/${yr}`, '_blank');
    });
    document.getElementById('acctEfileTransmit')?.addEventListener('click', async () => {
      const yr = new Date().getFullYear() - 1;
      const r = await ctx.api('/api/accounting/compliance/efile/transmit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ form: '1099', tax_year: yr, status: 'transmitted' }),
      });
      await AD().alert(`Transmit logged: ${r.acknowledgment_id || r.id}`, 'success');
    });
    document.getElementById('acctEfileLog')?.addEventListener('click', async () => {
      const log = await ctx.api('/api/accounting/compliance/efile/log');
      const lines = (log.entries || []).map((e) => `${e.form} ${e.tax_year}: ${e.status} (${e.acknowledgment_id})`).join('\n');
      await AD().alert(lines || 'No transmits logged.', 'info');
    });
    document.getElementById('acctComplianceRemind')?.addEventListener('click', async () => {
      const email = await AD().prompt('Send reminders to email:', '', 'Compliance');
      if (email == null) return;
      const r = await ctx.api('/api/accounting/compliance/reminders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      await AD().alert(r.smtp_sent ? 'Reminders sent.' : 'Reminders generated (configure SMTP to email).', 'info');
    });
  }

  global.CasePMAcctWaves17UI = {
    init(c) {
      ctx = c;
    },
    async enhanceIntegrationsPanel(extraHtml) {
      return extraHtml;
    },
    async afterIntegrationsMount() {
      await bindPlaidLink('acctPlaidLink');
      bindSageHybrid();
      bindComplianceCalendar();
    },
    sageHybridSection,
    complianceCalendarHtml,
    bindPlaidLink,
  };
})(window);
