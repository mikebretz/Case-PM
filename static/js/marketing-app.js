(function () {
  'use strict';

  const ctx = window.CASEPM_MARKETING_CTX || {};
  const STAGES = ['inquiry', 'qualification', 'proposal', 'negotiation', 'won', 'lost'];
  let leads = [];
  let stagesMeta = [];

  function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  async function api(path, opts) {
    const headers = { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json', ...(opts?.headers || {}) };
    const token = csrf();
    if (token && (opts?.method || 'GET') !== 'GET') headers['X-CSRF-Token'] = token;
    const res = await fetch(path, { credentials: 'same-origin', ...opts, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function showTab(name) {
    document.querySelectorAll('.mk-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    document.querySelectorAll('.mk-panel').forEach(p => p.classList.add('hidden'));
    const id = {
      pipeline: 'mkPanelPipeline',
      portfolio: 'mkPanelPortfolio',
      campaigns: 'mkPanelCampaigns',
      reviews: 'mkPanelReviews',
      assets: 'mkPanelAssets',
      capture: 'mkPanelCapture',
      proposals: 'mkPanelProposals',
      web: 'mkPanelWeb',
      analytics: 'mkPanelAnalytics',
    }[name];
    document.getElementById(id)?.classList.remove('hidden');
  }

  function renderDashboard(d) {
    const host = document.getElementById('mkDashboard');
    if (!host) return;
    const cards = [
      ['Forecast (history)', `$${Number(d.forecast_with_history || d.pipeline_weighted_value || 0).toLocaleString()}`],
      ['Marketing spend', `$${Number(d.marketing_spend_total || 0).toLocaleString()}`],
      ['Campaign opens/clicks', `${d.campaign_opens || 0} / ${d.campaign_clicks || 0}`],
      ['Portfolio views', d.portfolio_page_views || 0],
    ];
    host.innerHTML = cards.map(([label, val]) => `
      <div class="mk-card"><div class="mk-stat">${esc(val)}</div><div class="mk-stat-label">${esc(label)}</div></div>`).join('');
  }

  function renderPipeline() {
    const host = document.getElementById('mkPipeline');
    if (!host) return;
    host.innerHTML = STAGES.map(stage => {
      const items = leads.filter(l => (l.stage || 'inquiry') === stage);
      return `<div class="mk-col" data-stage="${esc(stage)}"><h3>${esc(stage)}</h3>
        ${items.map(l => `<div class="mk-lead" data-id="${l.id}">
          <div class="font-medium text-white">${esc(l.title)}</div>
          <div class="text-zinc-500">${esc(l.contact_name || l.email || '')}</div>
          <div class="text-emerald-500/80">$${Number(l.estimated_value || 0).toLocaleString()} · ${l.probability || 0}%</div>
        </div>`).join('')}
      </div>`;
    }).join('');
    host.querySelectorAll('.mk-lead').forEach(el => {
      el.addEventListener('click', () => openLeadMenu(parseInt(el.dataset.id, 10)));
    });
  }

  async function openLeadMenu(id) {
    const lead = leads.find(l => l.id === id);
    if (!lead) return;
    const next = prompt(`Stage for "${lead.title}" (${STAGES.join(', ')}):`, lead.stage || 'inquiry');
    if (!next || !STAGES.includes(next)) return;
    await api(`/api/marketing/leads/${id}/stage`, { method: 'POST', body: JSON.stringify({ stage: next }) });
    await loadLeads();
    if (next === 'won' && confirm('Convert to estimate / project?')) {
      const out = await api(`/api/marketing/leads/${id}/convert-estimate`, { method: 'POST', body: '{}' });
      alert(`Estimate #${out.estimate_id} on project #${out.project_id}`);
    }
  }

  async function loadLeads() {
    const data = await api('/api/marketing/leads');
    leads = data.leads || [];
    stagesMeta = data.stages || STAGES;
    renderPipeline();
  }

  async function loadDashboard() {
    const d = await api('/api/marketing/dashboard');
    renderDashboard(d);
    const detail = document.getElementById('mkAnalyticsDetail');
    if (detail) detail.textContent = JSON.stringify(d, null, 2);
  }

  async function loadCaseStudies() {
    const data = await api('/api/marketing/case-studies');
    const host = document.getElementById('mkCaseStudies');
    if (!host) return;
    const rows = data.case_studies || [];
    if (!rows.length) { host.innerHTML = '<p class="text-zinc-500">No case studies yet.</p>'; return; }
    host.innerHTML = rows.map(c => `
      <div class="border border-zinc-700 rounded-md p-3 flex justify-between gap-2 flex-wrap">
        <div><div class="font-medium text-white">${esc(c.title)}</div>
        <div class="text-xs text-zinc-500">${esc(c.status)} · v${c.version}</div></div>
        <div class="flex gap-2">
          ${c.status !== 'published' ? `<button type="button" class="text-xs text-emerald-400 mk-pub" data-id="${c.id}">Publish</button>` : ''}
          ${c.status === 'published' && c.slug ? `<a class="text-xs text-sky-400" target="_blank" href="/public/marketing/case-study/${esc(c.slug)}">View</a>` : ''}
        </div>
      </div>`).join('');
    host.querySelectorAll('.mk-pub').forEach(btn => btn.addEventListener('click', async () => {
      await api(`/api/marketing/case-studies/${btn.dataset.id}/publish`, { method: 'POST', body: '{}' });
      loadCaseStudies();
    }));
  }

  async function loadCampaigns() {
    const data = await api('/api/marketing/campaigns');
    const host = document.getElementById('mkCampaigns');
    if (!host) return;
    const rows = data.campaigns || [];
    host.innerHTML = rows.length ? rows.map(c => `
      <div class="border border-zinc-700 rounded-md p-3 mb-2 flex justify-between">
        <div><div class="font-medium">${esc(c.name)}</div><div class="text-xs text-zinc-500">${esc(c.status)} · ${esc(c.channel)}</div></div>
        ${c.status !== 'sent' ? `<button type="button" class="text-xs text-emerald-400 mk-send-c" data-id="${c.id}">Send</button>` : `<span class="text-xs text-zinc-500">Sent</span>`}
      </div>`).join('') : '<p class="text-zinc-500">No campaigns.</p>';
    host.querySelectorAll('.mk-send-c').forEach(btn => btn.addEventListener('click', async () => {
      const test = confirm('Send test only to your email? Cancel for segment send.');
      let body = '{}';
      if (test) {
        const email = prompt('Test email:');
        if (!email) return;
        body = JSON.stringify({ test_email: email });
      }
      await api(`/api/marketing/campaigns/${btn.dataset.id}/send`, { method: 'POST', body });
      loadCampaigns();
    }));
  }

  async function loadReviews() {
    const data = await api('/api/marketing/reviews');
    const host = document.getElementById('mkReviews');
    if (!host) return;
    const rows = data.reviews || [];
    host.innerHTML = rows.length ? rows.map(r => `
      <div class="border border-zinc-700 rounded-md p-3 mb-2">
        <div class="text-zinc-400 text-xs">Project #${r.project_id} · ${esc(r.platform)} · ${esc(r.status)}</div>
        ${r.rating ? `<div>${'★'.repeat(r.rating)}</div>` : ''}
        <div>${esc(r.testimonial_text || '')}</div>
      </div>`).join('') : '<p class="text-zinc-500">No completed reviews.</p>';
  }

  async function loadAssets() {
    const q = ctx.projectId ? `?project_id=${ctx.projectId}` : '';
    const data = await api(`/api/marketing/assets${q}`);
    const host = document.getElementById('mkAssets');
    if (!host) return;
    const rows = data.assets || [];
    host.innerHTML = rows.length ? rows.map(a => `
      <div class="border border-zinc-700 rounded-md overflow-hidden">
        ${a.preview_url ? `<img src="${esc(a.preview_url)}" alt="" class="w-full h-24 object-cover">` : ''}
        <div class="p-2 text-xs">${esc(a.title)}</div>
      </div>`).join('') : '<p class="text-zinc-500 col-span-full">No marketing assets. Sync from project photos.</p>';
  }

  function setupCapture() {
    const origin = window.location.origin;
    const ep = document.getElementById('mkLeadEndpoint');
    if (ep) {
      ep.textContent = `POST ${origin}/api/public/marketing/leads  {"contact_name","email","phone","notes","source":"website"}`;
    }
    const hint = document.getElementById('mkEmbedHint');
    if (hint) hint.textContent = `${origin}/public/marketing/case-study/<slug>`;
  }

  async function loadAll() {
    await Promise.all([loadDashboard(), loadLeads(), loadCaseStudies(), loadCampaigns(), loadReviews(), loadAssets()]);
    setupCapture();
  }

  document.querySelectorAll('.mk-tab').forEach(t => t.addEventListener('click', () => showTab(t.dataset.tab)));
  document.getElementById('mkRefresh')?.addEventListener('click', loadAll);
  document.getElementById('mkNewLead')?.addEventListener('click', async () => {
    const title = prompt('Lead title / project description:');
    if (!title) return;
    const email = prompt('Contact email:') || '';
    await api('/api/marketing/leads', { method: 'POST', body: JSON.stringify({ title, email, source: 'referral' }) });
    loadLeads();
    loadDashboard();
  });
  document.getElementById('mkBuildCaseStudy')?.addEventListener('click', async () => {
    if (!ctx.projectId) { alert('Select an active project first.'); return; }
    await api('/api/marketing/case-studies/from-project', { method: 'POST', body: JSON.stringify({ project_id: ctx.projectId }) });
    loadCaseStudies();
  });
  document.getElementById('mkSyncAssets')?.addEventListener('click', async () => {
    if (!ctx.projectId) { alert('Select an active project first.'); return; }
    await api('/api/marketing/assets/sync', { method: 'POST', body: JSON.stringify({ project_id: ctx.projectId }) });
    loadAssets();
  });
  document.getElementById('mkNewReview')?.addEventListener('click', async () => {
    if (!ctx.projectId) { alert('Select an active project first.'); return; }
    const row = await api('/api/marketing/reviews', { method: 'POST', body: JSON.stringify({ project_id: ctx.projectId, platform: 'google' }) });
    const email = prompt('Send review request to client email:');
    if (email) await api(`/api/marketing/reviews/${row.id}/send`, { method: 'POST', body: JSON.stringify({ email }) });
    loadReviews();
  });
  document.getElementById('mkNewCampaign')?.addEventListener('click', async () => {
    const name = prompt('Campaign name:');
    if (!name) return;
    const subject = prompt('Email subject:') || name;
    await api('/api/marketing/campaigns', {
      method: 'POST',
      body: JSON.stringify({
        name,
        subject,
        channel: 'email',
        body_text: 'Thank you for your interest in our construction services.',
        segment: { stage: 'inquiry' },
      }),
    });
    loadCampaigns();
  });

  async function loadLanding() {
    const data = await api('/api/marketing/landing-pages');
    const host = document.getElementById('mkLandingPages');
    if (host) {
      host.innerHTML = (data.pages || []).map(p =>
        `<div class="mb-2"><a class="text-sky-400" href="${esc(p.public_url)}" target="_blank">${esc(p.title)}</a> · ${esc(p.status)}</div>`,
      ).join('') || '<p class="text-zinc-500">No landing pages.</p>';
    }
    const settings = await api('/api/marketing/settings');
    const sh = document.getElementById('mkMarketingSettings');
    if (sh) sh.innerHTML = `<pre class="text-xs">${esc(JSON.stringify(settings, null, 2))}</pre>`;
  }

  document.getElementById('mkBuildProposal')?.addEventListener('click', async () => {
    const estId = prompt('Estimate ID to build proposal from:');
    if (!estId) return;
    const out = await api('/api/marketing/proposals', { method: 'POST', body: JSON.stringify({ estimate_id: parseInt(estId, 10) }) });
    const host = document.getElementById('mkProposals');
    if (host) host.innerHTML = `<p>Proposal <a class="text-sky-400" href="${esc(out.public_url)}" target="_blank">#${out.id}</a></p>`;
  });
  document.getElementById('mkSeedLanding')?.addEventListener('click', () => loadLanding());
  document.getElementById('mkAddSpend')?.addEventListener('click', async () => {
    const amount = prompt('Spend amount USD:');
    if (!amount) return;
    const channel = prompt('Channel (paid_ads, houzz, other):') || 'paid_ads';
    await api('/api/marketing/spend', { method: 'POST', body: JSON.stringify({ amount: parseFloat(amount), channel, label: 'Manual entry' }) });
    loadDashboard();
  });
  document.getElementById('mkRunAutomation')?.addEventListener('click', async () => {
    if (!ctx.projectId) { alert('Select active project'); return; }
    const out = await api('/api/marketing/automation/run', { method: 'POST', body: JSON.stringify({ project_id: ctx.projectId }) });
    alert(`Automation fired: ${(out.fired || []).length} action(s)`);
  });

  loadAll();
  loadLanding().catch(() => {});
})();
