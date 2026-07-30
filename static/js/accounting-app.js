/**
 * Case PM Accounting module — Sage 300 dashboard, ERP queue, catalog, inquiries.
 */
(function (global) {
  'use strict';

  let catalogCache = null;
  let currentTab = 'overview';

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  async function api(path, options) {
    const res = await fetch(path, { credentials: 'same-origin', ...(options || {}) });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || res.statusText);
    return json;
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.acct-tab').forEach((btn) => {
      const on = btn.getAttribute('data-acct-tab') === tab;
      btn.classList.toggle('bg-emerald-600', on);
      btn.classList.toggle('text-white', on);
      btn.classList.toggle('bg-zinc-800', !on);
      btn.classList.toggle('text-zinc-300', !on);
    });
    document.querySelectorAll('.acct-panel').forEach((p) => p.classList.add('hidden'));
    const panel = document.getElementById(`acctPanel${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
    if (panel) panel.classList.remove('hidden');
    if (tab === 'catalog' && !catalogCache) loadCatalog();
    if (tab === 'erp') loadErpQueue();
  }

  function renderRecentEvents(events) {
    const tbody = document.getElementById('acctRecentEvents');
    if (!tbody) return;
    if (!events || !events.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-zinc-500">No sync events for this project.</td></tr>';
      return;
    }
    tbody.innerHTML = events.map((e) => `
      <tr class="hover:bg-zinc-800/50">
        <td class="px-4 py-2 text-xs text-zinc-500">${esc((e.created_at || '').slice(0, 19))}</td>
        <td class="px-4 py-2 font-mono text-xs">${esc(e.event_type)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.status)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.accounting_status || '—')}</td>
        <td class="px-4 py-2 text-xs text-zinc-400 truncate max-w-xs">${esc(e.message || '')}</td>
      </tr>
    `).join('');
  }

  function renderLinkedModules(mods) {
    const el = document.getElementById('acctLinkedModules');
    if (!el) return;
    el.innerHTML = (mods || []).map((m) => `
      <span class="text-[10px] px-2 py-1 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-300" title="${esc((m.events || []).join(', '))}">
        ${esc(m.name)} <span class="text-emerald-500">${esc(m.integration || '')}</span>
      </span>
    `).join('');
  }

  async function loadDashboard() {
    const pid = projectId();
    if (!pid) {
      document.getElementById('acctJobNumber').textContent = 'Select a project';
      return;
    }
    const data = await api(`/api/accounting/dashboard?project_id=${pid}`);
    const p = data.project || {};
    document.getElementById('acctJobNumber').textContent = p.sage_job_number || 'Not set';
    const st = data.sage_sync_status || {};
    document.getElementById('acctSyncLabel').textContent = st.label || '—';
    document.getElementById('acctSyncLabel').className = `text-lg font-semibold mt-1 ${st.class || 'text-zinc-300'}`;
    document.getElementById('acctSyncDetail').textContent = st.detail || '';
    document.getElementById('acctPendingReview').textContent = String((data.erp_queue || {}).pending_review_count || 0);
    const conn = data.connection || {};
    document.getElementById('acctMode').textContent = (conn.mode || 'offline').replace(/_/g, ' ');
    renderRecentEvents(data.recent_events);
    renderLinkedModules(data.linked_sage_modules);
    updateConnBadge(conn);
  }

  function updateConnBadge(conn) {
    const badge = document.getElementById('acctConnBadge');
    if (!badge) return;
    const mode = (conn && conn.mode) || 'offline';
    const colors = {
      cre_bridge_and_web_api: 'text-emerald-400 border-emerald-700',
      cre_bridge: 'text-sky-400 border-sky-700',
      web_api: 'text-violet-400 border-violet-700',
      web_api_partial: 'text-amber-400 border-amber-700',
      offline: 'text-zinc-500 border-zinc-700',
    };
    badge.className = `text-xs font-medium px-3 py-1 rounded-full bg-zinc-800 border ${colors[mode] || colors.offline}`;
    badge.textContent = mode.replace(/_/g, ' ');
  }

  async function loadConnection() {
    try {
      const conn = await api('/api/accounting/connection');
      updateConnBadge(conn);
    } catch (e) {
      console.warn('[Accounting]', e);
    }
  }

  async function loadErpQueue() {
    const pid = projectId();
    const tbody = document.getElementById('acctErpBody');
    if (!tbody || !pid) return;
    const filter = document.getElementById('acctErpFilter')?.value || '';
    let url = `/api/accounting/erp-queue?project_id=${pid}&limit=150`;
    if (filter) url += `&accounting_status=${encodeURIComponent(filter)}`;
    const data = await api(url);
    const events = data.events || [];
    if (!events.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-10 text-center text-zinc-500">No events in queue.</td></tr>';
      return;
    }
    tbody.innerHTML = events.map((e) => {
      const reviewBtns = e.accounting_status === 'pending_review'
        ? `<button type="button" data-erp-accept="${e.id}" class="text-emerald-400 text-xs mr-2">Accept</button>
           <button type="button" data-erp-reject="${e.id}" class="text-red-400 text-xs">Reject</button>`
        : `<button type="button" data-erp-retry="${e.id}" class="text-sky-400 text-xs">Retry Sage</button>`;
      return `<tr class="hover:bg-zinc-800/50">
        <td class="px-4 py-2 text-xs">${e.id}</td>
        <td class="px-4 py-2 text-xs font-mono">${esc(e.event_type)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.status)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.accounting_status)}</td>
        <td class="px-4 py-2 text-xs font-mono">${esc(e.sage_job_number)}</td>
        <td class="px-4 py-2 text-right">${reviewBtns}</td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('[data-erp-accept]').forEach((btn) => {
      btn.addEventListener('click', () => erpReview(btn.getAttribute('data-erp-accept'), 'accept'));
    });
    tbody.querySelectorAll('[data-erp-reject]').forEach((btn) => {
      btn.addEventListener('click', () => erpReview(btn.getAttribute('data-erp-reject'), 'reject'));
    });
    tbody.querySelectorAll('[data-erp-retry]').forEach((btn) => {
      btn.addEventListener('click', () => erpRetry(btn.getAttribute('data-erp-retry')));
    });
  }

  async function erpReview(id, action) {
    if (typeof CasePMPayAppWorkflow !== 'undefined' && CasePMPayAppWorkflow.erpReview) {
      await CasePMPayAppWorkflow.erpReview(id, action);
    } else {
      await api(`/api/sage/sync-events/${id}/accounting`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
    }
    await loadErpQueue();
    await loadDashboard();
  }

  async function erpRetry(id) {
    await api(`/api/sage/sync-events/${id}/retry`, { method: 'POST' });
    await loadErpQueue();
    await loadDashboard();
  }

  async function loadCatalog() {
    catalogCache = await api('/api/accounting/catalog');
    const notes = document.getElementById('acctCatalogNotes');
    if (notes && catalogCache.notes) {
      notes.textContent = catalogCache.notes.join(' ');
    }
    const plat = document.getElementById('acctPlatformGrid');
    if (plat) {
      plat.innerHTML = (catalogCache.platform || []).map((f) => `
        <div class="bg-zinc-900 border border-zinc-800 rounded p-3">
          <div class="text-sm font-medium text-zinc-200">${esc(f.name)}</div>
          <div class="text-[11px] text-zinc-500 mt-1">${esc(f.description)}</div>
        </div>
      `).join('');
    }
    const mods = document.getElementById('acctModuleGrid');
    if (mods) {
      mods.innerHTML = (catalogCache.modules || []).map((m) => {
        const apiInfo = m.web_api
          ? `<span class="text-[10px] text-sky-400 font-mono">${esc(m.web_api.module)}/${esc((m.web_api.resources || [])[0] || '')}</span>`
          : '<span class="text-[10px] text-zinc-600">CRE / desktop</span>';
        const events = ((m.casepm || {}).events || []).slice(0, 4).join(', ');
        return `<article class="bg-zinc-900 border border-zinc-700 rounded-lg p-4">
          <div class="flex justify-between gap-2 flex-wrap">
            <h4 class="font-semibold text-white">${esc(m.name)} <span class="text-zinc-500 font-normal text-xs">(${esc(m.code)})</span></h4>
            <span class="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">${esc(m.integration)} · ${esc(m.edition)}</span>
          </div>
          <p class="text-xs text-zinc-400 mt-1">${esc(m.summary)}</p>
          <ul class="text-[11px] text-zinc-500 mt-2 list-disc pl-4 space-y-0.5">${(m.features || []).slice(0, 5).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>
          <div class="mt-2 flex flex-wrap gap-2 items-center">${apiInfo}
            ${events ? `<span class="text-[10px] text-emerald-500">Case PM: ${esc(events)}${(m.casepm.events || []).length > 4 ? '…' : ''}</span>` : ''}
          </div>
        </article>`;
      }).join('');
    }
    const presetSel = document.getElementById('acctInquiryPreset');
    if (presetSel && presetSel.options.length <= 1) {
      (catalogCache.inquiry_presets || []).forEach((p, i) => {
        const opt = document.createElement('option');
        opt.value = String(i);
        opt.textContent = p.label;
        opt.dataset.module = p.module;
        opt.dataset.resource = p.resource;
        presetSel.appendChild(opt);
      });
    }
  }

  function applyInquiryPreset() {
    const sel = document.getElementById('acctInquiryPreset');
    const opt = sel?.selectedOptions?.[0];
    if (!opt) return;
    document.getElementById('acctInquiryModule').value = opt.dataset.module || '';
    document.getElementById('acctInquiryResource').value = opt.dataset.resource || '';
  }

  async function runInquiry() {
    const mod = document.getElementById('acctInquiryModule')?.value?.trim();
    const res = document.getElementById('acctInquiryResource')?.value?.trim();
    const out = document.getElementById('acctInquiryResult');
    if (!mod || !res) return;
    out.textContent = 'Loading…';
    try {
      const data = await api(`/api/accounting/web-api/resource?module=${encodeURIComponent(mod)}&resource=${encodeURIComponent(res)}&top=25`);
      out.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      out.textContent = e.message || String(e);
    }
  }

  async function probeWebApi() {
    const out = document.getElementById('acctInquiryResult');
    out.textContent = 'Probing…';
    try {
      const data = await api('/api/accounting/web-api/probe', { method: 'POST', body: '{}' });
      out.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      out.textContent = e.message || String(e);
    }
  }

  async function reconcile() {
    const out = document.getElementById('acctReconcileResult');
    out.textContent = 'Running…';
    try {
      if (typeof CasePMAccountingReconcile !== 'undefined') {
        const json = await CasePMAccountingReconcile.reconcileProject({ force: true });
        out.textContent = JSON.stringify(json, null, 2);
      } else {
        const pid = projectId();
        const json = await api(`/api/accounting/reconcile?project_id=${pid}`, { method: 'POST', body: '{}' });
        out.textContent = JSON.stringify(json, null, 2);
      }
    } catch (e) {
      out.textContent = e.message || String(e);
    }
  }

  async function pullSage() {
    const out = document.getElementById('acctPullResult');
    const pid = projectId();
    if (!pid) {
      out.textContent = 'Select a project first.';
      return;
    }
    out.textContent = 'Pulling…';
    try {
      const data = await api('/api/sage/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid }),
      });
      out.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      out.textContent = e.message || String(e);
    }
  }

  async function refresh() {
    await loadConnection();
    await loadDashboard();
    if (currentTab === 'erp') await loadErpQueue();
  }

  function bindUi() {
    document.querySelectorAll('.acct-tab').forEach((btn) => {
      btn.addEventListener('click', () => switchTab(btn.getAttribute('data-acct-tab')));
    });
    document.getElementById('acctRefreshBtn')?.addEventListener('click', () => refresh());
    document.getElementById('acctErpReload')?.addEventListener('click', () => loadErpQueue());
    document.getElementById('acctErpFilter')?.addEventListener('change', () => loadErpQueue());
    document.getElementById('acctInquiryPreset')?.addEventListener('change', applyInquiryPreset);
    document.getElementById('acctInquiryRun')?.addEventListener('click', runInquiry);
    document.getElementById('acctProbeBtn')?.addEventListener('click', probeWebApi);
    document.getElementById('acctReconcileBtn')?.addEventListener('click', reconcile);
    document.getElementById('acctPullBtn')?.addEventListener('click', pullSage);
  }

  async function init() {
    bindUi();
    switchTab('overview');
    const params = new URLSearchParams(global.location.search);
    const tab = params.get('tab');
    if (tab && document.querySelector(`[data-acct-tab="${tab}"]`)) switchTab(tab);
    try {
      await refresh();
      await loadCatalog();
      applyInquiryPreset();
    } catch (e) {
      console.warn('[Accounting] init', e);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  global.CasePMAccounting = { refresh, switchTab, loadErpQueue };
})(window);
