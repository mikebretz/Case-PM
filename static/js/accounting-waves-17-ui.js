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
