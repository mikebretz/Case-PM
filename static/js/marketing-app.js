(function () {
  'use strict';

  const ctx = window.CASEPM_MARKETING_CTX || {};
  const STAGES = ['inquiry', 'qualification', 'proposal', 'negotiation', 'won', 'lost'];
  let leads = [];
  let stagesMeta = [];
  let marketCatalog = [];
  let marketingSettings = {};

  async function marketingBaseUrl() {
    if (marketingSettings.public_base_url === undefined) {
      try {
        const s = await api('/api/marketing/settings');
        marketingSettings = s.settings || s;
      } catch (_) {
        marketingSettings = {};
      }
    }
    const custom = String(marketingSettings.public_base_url || '').replace(/\/$/, '');
    return custom || window.location.origin;
  }

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
      integrations: 'mkPanelIntegrations',
      analytics: 'mkPanelAnalytics',
    }[name];
    document.getElementById(id)?.classList.remove('hidden');
    const loader = {
      pipeline: loadLeads,
      portfolio: loadCaseStudies,
      campaigns: loadCampaigns,
      reviews: loadReviews,
      assets: loadAssets,
      capture: () => loadCapturePanel(),
      proposals: loadProposals,
      web: loadWebPanel,
      integrations: loadIntegrationsPanel,
      analytics: loadAnalyticsPanel,
    }[name];
    if (loader) loader().catch((e) => console.error('Marketing tab', name, e));
  }

  function renderActiveProject() {
    const el = document.getElementById('mkActiveProject');
    if (!el) return;
    if (ctx.projectId) {
      el.textContent = `Active project: ${ctx.projectName || '#' + ctx.projectId} — case studies, assets, and reviews use this project.`;
      el.classList.remove('hidden');
    } else {
      el.textContent = 'No active project — pick a project in the header to enable project-scoped actions.';
      el.classList.remove('hidden');
    }
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

  async function loadAnalyticsPanel() {
    await loadDashboard();
    await loadSpend();
  }

  async function loadSpend() {
    const data = await api('/api/marketing/spend');
    const host = document.getElementById('mkSpendList');
    if (!host) return;
    const rows = data.entries || [];
    if (!rows.length) {
      host.innerHTML = '<p class="text-zinc-500">No spend recorded yet.</p>';
      return;
    }
    host.innerHTML = `<table class="w-full text-left"><thead><tr class="text-zinc-500"><th class="py-1">Channel</th><th>Label</th><th class="text-right">Amount</th></tr></thead><tbody>
      ${rows.map(r => `<tr class="border-t border-zinc-800"><td class="py-1">${esc(r.channel)}</td><td>${esc(r.label || '')}</td><td class="text-right">$${Number(r.amount || 0).toLocaleString()}</td></tr>`).join('')}
    </tbody></table>`;
  }

  async function loadProposals() {
    const data = await api('/api/marketing/proposals');
    const host = document.getElementById('mkProposals');
    if (!host) return;
    const rows = data.proposals || [];
    if (!rows.length) {
      host.innerHTML = '<p class="text-zinc-500">No proposals yet. Build one from an estimate ID.</p>';
      return;
    }
    host.innerHTML = rows.map(p => `
      <div class="border border-zinc-700 rounded-md p-3 flex flex-wrap justify-between gap-2 items-center">
        <div>
          <div class="font-medium text-white">${esc(p.title || 'Proposal #' + p.id)}</div>
          <div class="text-xs text-zinc-500">${esc(p.status)} · estimate #${p.estimate_id} · ${p.view_count || 0} views</div>
        </div>
        <div class="flex gap-2 flex-wrap text-xs">
          <a class="text-sky-400" href="${esc(p.public_url)}" target="_blank">Open</a>
          <button type="button" class="text-emerald-400 mk-prop-send" data-id="${p.id}">Email</button>
          <button type="button" class="text-violet-400 mk-prop-pdf" data-id="${p.id}">PDF</button>
        </div>
      </div>`).join('');
    host.querySelectorAll('.mk-prop-send').forEach(btn => btn.addEventListener('click', async () => {
      const email = prompt('Send proposal link to:');
      if (!email) return;
      await api(`/api/marketing/proposals/${btn.dataset.id}/send`, { method: 'POST', body: JSON.stringify({ email }) });
      loadProposals();
    }));
    host.querySelectorAll('.mk-prop-pdf').forEach(btn => btn.addEventListener('click', async () => {
      await api(`/api/marketing/proposals/${btn.dataset.id}/pdf`, { method: 'POST', body: '{}' });
      alert('PDF generated (stored on proposal record).');
      loadProposals();
    }));
  }

  async function loadWebPanel() {
    await loadLanding();
    await populateSettingsForm();
    const kit = await api('/api/marketing/brand-kit').catch(() => ({}));
    const bk = document.getElementById('mkBrandKit');
    if (bk && kit.kits && kit.kits.length) {
      const b = kit.kits.find(k => k.is_default) || kit.kits[0];
      const primary = (b.colors && b.colors.primary) || '—';
      bk.innerHTML = `<div class="text-xs uppercase text-zinc-500 mb-1">Brand kit</div>
        <div class="text-zinc-300">${esc(b.name || 'Default')} · primary ${esc(primary)}</div>`;
    } else if (bk) {
      bk.innerHTML = '<div class="text-xs text-zinc-500">Brand kit not configured (API: POST /api/marketing/brand-kit).</div>';
    }
  }

  async function loadIntegrationsPanel() {
    const origin = window.location.origin;
    const cat = await api('/api/marketing/integrations/catalog');
    const host = document.getElementById('mkIntegrations');
    if (host) {
      host.innerHTML = (cat.integrations || []).map(i => {
        const url = i.path ? `${origin}${i.path}` : (i.env ? `env: ${i.env}` : '—');
        return `<div class="border border-zinc-700 rounded-md p-3">
          <div class="font-medium text-white">${esc(i.name)}</div>
          <div class="text-xs text-zinc-500">${esc(i.mode)}</div>
          <code class="text-xs break-all text-sky-300/90">${esc(url)}</code>
        </div>`;
      }).join('');
    }
    const refs = await api('/api/marketing/referrals');
    const rh = document.getElementById('mkReferrals');
    if (rh) {
      const rows = refs.referrals || refs.items || [];
      rh.innerHTML = rows.length ? rows.map(r => `
        <div class="border border-zinc-800 rounded p-2">#${r.id} · ${esc(r.status || '')} · incentive ${esc(r.incentive_type || '')}</div>
      `).join('') : '<p class="text-zinc-500">No referrals yet.</p>';
    }
  }

  async function runSeoAudit() {
    const out = await api('/api/marketing/seo/audit');
    const host = document.getElementById('mkSeoAudit');
    if (!host) return;
    const score = out.score != null ? out.score : out.overall_score;
    const items = [...(out.issues || []), ...(out.recommendations || [])];
    host.innerHTML = `<div class="text-emerald-400/90 mb-2">SEO score: ${esc(score != null ? String(score) : '—')}</div>
      <ul class="list-disc pl-4 space-y-1">${items.slice(0, 15).map(it => {
        const label = typeof it === 'string' ? it : (it.label || it.id || JSON.stringify(it));
        return `<li>${esc(label)}</li>`;
      }).join('')}</ul>`;
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

  async function populateSettingsForm() {
    const data = await api('/api/marketing/settings');
    marketingSettings = data.settings || {};
    const form = document.getElementById('mkSettingsForm');
    if (!form) return;
    ['public_base_url', 'google_place_id', 'houzz_profile_url', 'facebook_page_url'].forEach((name) => {
      const el = form.elements[name];
      if (el) el.value = marketingSettings[name] || '';
    });
    const crm = form.elements.crm_auto_push;
    if (crm) crm.checked = !!marketingSettings.crm_auto_push;
  }

  async function loadCapturePanel() {
    const base = await marketingBaseUrl();
    const ep = document.getElementById('mkLeadEndpoint');
    if (ep) {
      const sample = {
        contact_name: 'Jane Owner',
        email: 'jane@example.com',
        phone: '555-0100',
        notes: 'Kitchen remodel',
        source: 'website',
      };
      ep.textContent = `POST ${base}/api/public/marketing/leads\nContent-Type: application/json\n\n${JSON.stringify(sample, null, 2)}`;
    }
    const data = await api('/api/marketing/case-studies');
    const published = (data.case_studies || []).filter((c) => c.status === 'published' && c.slug);
    const links = document.getElementById('mkCaseStudyLinks');
    if (links) {
      links.innerHTML = published.length
        ? published.map((c) => `<div><a class="text-sky-400" href="${esc(base)}/public/marketing/case-study/${esc(c.slug)}" target="_blank">${esc(c.title)}</a></div>`).join('')
        : '<p class="text-zinc-500">Publish case studies in Portfolio to list share links here.</p>';
    }
    const site = document.getElementById('mkPublicSiteLink');
    if (site) {
      const url = `${base}/public/marketing/site/home`;
      site.href = url;
      site.textContent = url;
    }
  }

  async function loadMarketProfile() {
    const cat = await api('/api/marketing/construction-markets');
    marketCatalog = cat.markets || [];
    const schemeRes = await api('/api/marketing/market-scheme');
    const primary = schemeRes.resolved?.primary || 'commercial';
    const sel = document.getElementById('mkPrimaryMarket');
    if (sel) {
      sel.innerHTML = marketCatalog.map(m => `<option value="${m.id}" ${m.id === primary ? 'selected' : ''}>${esc(m.label)}</option>`).join('');
    }
    const host = document.getElementById('mkSchemeSummary');
    if (host && schemeRes.scheme) {
      const s = schemeRes.scheme;
      host.innerHTML = `<strong>${esc(s.headline)}</strong> — ${esc(s.summary)}
        <div class="mt-2 text-zinc-500">Sources: ${esc((s.recommended_lead_sources || []).join(', '))}
        · Content: ${esc((s.content_pillars || []).join(', '))}</div>`;
    }
  }

  async function loadAll() {
    renderActiveProject();
    try {
      await loadMarketProfile();
    } catch (e) {
      console.error('Marketing market profile', e);
    }
    await Promise.all([
      loadDashboard(),
      loadLeads(),
      loadCaseStudies(),
      loadCampaigns(),
      loadReviews(),
      loadAssets(),
    ]).catch((e) => console.error('Marketing load', e));
    loadCapturePanel().catch(() => {});
  }

  document.getElementById('mkApplyMarket')?.addEventListener('click', async () => {
    const primary = document.getElementById('mkPrimaryMarket')?.value;
    if (!primary) return;
    const btn = document.getElementById('mkApplyMarket');
    if (btn) btn.disabled = true;
    try {
      const out = await api('/api/marketing/market-scheme/apply', {
        method: 'POST',
        body: JSON.stringify({ primary_construction_market: primary }),
      });
      await loadMarketProfile();
      loadCampaigns();
      const parts = [];
      if (out.templates) parts.push(`${out.templates} new email templates`);
      if (out.content) parts.push(`${out.content} content blocks`);
      if (out.landing) parts.push('landing page updated');
      alert(parts.length ? `Applied: ${parts.join(', ')}.` : 'Marketing scheme applied.');
    } catch (e) {
      alert(e.message || 'Could not apply marketing scheme. Try again or check server logs.');
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  document.getElementById('mkSettingsForm')?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const body = {
      public_base_url: form.elements.public_base_url?.value?.trim() || '',
      google_place_id: form.elements.google_place_id?.value?.trim() || '',
      houzz_profile_url: form.elements.houzz_profile_url?.value?.trim() || '',
      facebook_page_url: form.elements.facebook_page_url?.value?.trim() || '',
      crm_auto_push: !!form.elements.crm_auto_push?.checked,
    };
    await api('/api/marketing/settings', { method: 'PUT', body: JSON.stringify(body) });
    marketingSettings = { ...marketingSettings, ...body };
    alert('Settings saved.');
    loadCapturePanel().catch(() => {});
  });

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
    let subject = '';
    let bodyText = 'Thank you for your interest in our construction services.';
    try {
      const tpl = await api('/api/marketing/campaign-templates');
      const templates = tpl.templates || [];
      if (templates.length) {
        const pick = prompt(`Template key (optional): ${templates.map(t => t.key).join(', ')}`);
        const t = templates.find(x => x.key === pick);
        if (t) {
          subject = t.subject || '';
          bodyText = t.name ? `Template: ${t.name}` : bodyText;
        }
      }
    } catch (_) { /* optional */ }
    const name = prompt('Campaign name:');
    if (!name) return;
    if (!subject) subject = prompt('Email subject:') || name;
    await api('/api/marketing/campaigns', {
      method: 'POST',
      body: JSON.stringify({
        name,
        subject,
        channel: 'email',
        body_text: bodyText,
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
  }

  document.getElementById('mkBuildProposal')?.addEventListener('click', async () => {
    const estId = prompt('Estimate ID to build proposal from:');
    if (!estId) return;
    await api('/api/marketing/proposals', { method: 'POST', body: JSON.stringify({ estimate_id: parseInt(estId, 10) }) });
    loadProposals();
  });
  document.getElementById('mkSeedLanding')?.addEventListener('click', () => loadWebPanel());
  document.getElementById('mkRunSeoAudit')?.addEventListener('click', () => runSeoAudit().catch(e => alert(e.message)));
  document.getElementById('mkNewReferral')?.addEventListener('click', async () => {
    const refId = prompt('Referrer lead ID (optional):');
    const title = prompt('Referred lead title:');
    if (!title) return;
    const email = prompt('Referred contact email:') || '';
    await api('/api/marketing/referrals', {
      method: 'POST',
      body: JSON.stringify({
        referrer_lead_id: refId ? parseInt(refId, 10) : null,
        referred_lead: { title, email, source: 'referral' },
      }),
    });
    loadIntegrationsPanel();
  });
  document.getElementById('mkAddSpend')?.addEventListener('click', async () => {
    const amount = prompt('Spend amount USD:');
    if (!amount) return;
    const channel = prompt('Channel (paid_ads, houzz, other):') || 'paid_ads';
    await api('/api/marketing/spend', { method: 'POST', body: JSON.stringify({ amount: parseFloat(amount), channel, label: 'Manual entry' }) });
    loadAnalyticsPanel();
  });
  document.getElementById('mkRunAutomation')?.addEventListener('click', async () => {
    if (!ctx.projectId) { alert('Select active project'); return; }
    const out = await api('/api/marketing/automation/run', { method: 'POST', body: JSON.stringify({ project_id: ctx.projectId }) });
    alert(`Automation fired: ${(out.fired || []).length} action(s)`);
  });

  loadAll().catch((e) => console.error('Marketing init', e));
})();
