/**
 * Tier 1–4 wave UI — integrations hub (admin), compliance shortcuts, Sage sync.
 */
(function (global) {
  'use strict';

  let ctx = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  async function integrationsPanelHtml() {
    const { api, esc } = ctx;
    const st = await api('/api/accounting/integrations/status');
    const sage = st.sage || {};
    const stripe = st.stripe || {};
    const plaid = st.plaid || {};
    const web = sage.web_api || {};
    const hybridBlock = global.CasePMAcctWaves17UI
      ? await global.CasePMAcctWaves17UI.sageHybridSection(st)
      : '';
    const calBlock = global.CasePMAcctWaves17UI
      ? await global.CasePMAcctWaves17UI.complianceCalendarHtml()
      : '';
    return `<section class="border border-violet-900/40 rounded-lg p-3 bg-violet-950/20 space-y-3">
      <h3 class="text-sm font-semibold text-violet-200">Integrations &amp; Sage hybrid</h3>
      <div class="grid md:grid-cols-3 gap-2 text-xs">
        <div class="border border-zinc-700 rounded p-2">
          <div class="text-zinc-500">Stripe</div>
          <div class="text-zinc-200">${esc(stripe.mode || 'off')} · ${stripe.stripe_configured ? 'keys set' : 'no secret key'}</div>
          <div class="text-[10px] text-zinc-600">Webhook secret: ${stripe.webhook_secret_set ? 'set' : 'optional'}</div>
        </div>
        <div class="border border-zinc-700 rounded p-2">
          <div class="text-zinc-500">Plaid</div>
          <div class="text-zinc-200">${plaid.configured ? (plaid.linked ? 'linked' : 'ready') : 'not configured'}</div>
          <button type="button" id="acctPlaidLink" class="mt-1 px-2 py-0.5 border border-zinc-600 rounded text-sky-400">Link bank (Plaid)</button>
        </div>
        <div class="border border-zinc-700 rounded p-2">
          <div class="text-zinc-500">Sage Web API</div>
          <div class="text-zinc-200">${web.configured ? esc(web.mode || 'configured') : 'not configured'}</div>
        </div>
      </div>
      ${hybridBlock}
      ${calBlock}
      <div class="flex flex-wrap gap-2 text-xs">
        <button type="button" id="acctTierSageVendors" class="px-2 py-1 border border-zinc-600 rounded text-emerald-400">Pull Sage vendors</button>
        <button type="button" id="acctTierSageGl" class="px-2 py-1 border border-zinc-600 rounded text-sky-400">Pull Sage G/L</button>
        <button type="button" id="acctTierSageQueue" class="px-2 py-1 border border-zinc-600 rounded text-amber-400">Queue open J/E to Sage</button>
        <button type="button" id="acctTierSageFlush" class="px-2 py-1 border border-zinc-600 rounded text-rose-400">Flush Sage queues</button>
        <button type="button" id="acctTierW2" class="px-2 py-1 border border-zinc-600 rounded text-zinc-300">W-2 e-file pkg</button>
        <button type="button" id="acctTier941" class="px-2 py-1 border border-zinc-600 rounded text-zinc-300">941 e-file pkg</button>
        <button type="button" id="acctTier1099Log" class="px-2 py-1 border border-zinc-600 rounded text-violet-300">Log 1099 transmit</button>
      </div>
      <p class="text-[10px] text-zinc-600">Set STRIPE_SECRET_KEY, PLAID_CLIENT_ID/SECRET, and Sage credentials in environment or Program Settings.</p>
    </section>`;
  }

  function bindIntegrationsPanel() {
    const { api, switchModule } = ctx;
    const yr = new Date().getFullYear() - 1;
    document.getElementById('acctTierSageVendors')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/vendors', { method: 'POST' });
      await AD().alert(`Sage vendors: created ${r.created || 0}, updated ${r.updated || 0} (${r.mode || r.message || ''})`, 'info');
      switchModule('admin');
    });
    document.getElementById('acctTierSageGl')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/gl-accounts', { method: 'POST' });
      await AD().alert(`G/L accounts created: ${r.created || 0}`, 'info');
      switchModule('admin');
    });
    document.getElementById('acctTierSageQueue')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/queue-batches', { method: 'POST' });
      await AD().alert(`Queued ${r.queued || 0} batch(es) for Sage export.`, 'success');
      switchModule('admin');
    });
    document.getElementById('acctTierSageFlush')?.addEventListener('click', async () => {
      const r = await api('/api/accounting/sage/sync/flush', { method: 'POST', body: '{}' });
      await AD().alert(`Flushed ${r.processed || 0} queue item(s). Check sync log.`, 'info');
      switchModule('admin');
    });
    document.getElementById('acctTierW2')?.addEventListener('click', () => {
      global.open(`/api/accounting/compliance/w2-efile/${yr}`, '_blank');
    });
    document.getElementById('acctTier941')?.addEventListener('click', () => {
      const q = Math.floor((new Date().getMonth()) / 3) + 1;
      global.open(`/api/accounting/compliance/941-efile?quarter=${q}&year=${new Date().getFullYear()}`, '_blank');
    });
    document.getElementById('acctTier1099Log')?.addEventListener('click', async () => {
      await api('/api/accounting/compliance/1099/transmit-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tax_year: yr }),
      });
      await AD().alert('1099 transmit logged on ledger.', 'success');
      switchModule('admin');
    });
  }

  async function mountAdminIntegrations() {
    const root = document.getElementById('acctPlatIntegrations');
    if (!root || !ctx) return;
    root.innerHTML = await integrationsPanelHtml();
    bindIntegrationsPanel();
    if (global.CasePMAcctWaves17UI?.afterIntegrationsMount) {
      await global.CasePMAcctWaves17UI.afterIntegrationsMount();
    }
  }

  global.CasePMAcctTierUI = {
    init(c) {
      ctx = c;
    },
    mountAdminIntegrations,
  };
})(window);
