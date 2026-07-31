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
        <button type="button" id="acctSageOps" class="px-2 py-0.5 border border-zinc-600 rounded text-zinc-300">Ops dashboard</button>
        <button type="button" id="acctSagePolicyCasepm" class="px-2 py-0.5 border border-zinc-600 rounded">SOR: Case PM</button>
        <button type="button" id="acctSagePolicySage" class="px-2 py-0.5 border border-zinc-600 rounded">SOR: Sage</button>
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
      const v = await api(`/api/accounting/sage/compliance/year-end-variance?tax_year=${yr}`);
      await AD().alert(`Year ${yr}: W-2 rows ${v.w2_rows}. Sage sync issues ${v.sage_sync_issues}. Ready: ${v.ready ? 'yes' : 'review'}.`, v.ready ? 'success' : 'warning');
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
