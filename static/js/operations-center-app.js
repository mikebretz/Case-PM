(function () {
  'use strict';

  const ctx = window.CASEPM_OPS_CTX || {};
  const shell = window.CasePMModuleShell;
  const state = {
    categories: [],
    reportSources: [],
    categoryId: null,
    moduleKey: null,
    schema: null,
    records: [],
    bimAssets: [],
    stats: {},
    editingId: null,
    advancedOpen: false,
    aiThreadId: null,
    aiMessages: [],
    lastReport: null,
    activeBimAsset: null,
    bimFullscreenCleanup: null,
  };

  const $ = id => document.getElementById(id);
  const SPECIAL = new Set(['wip_snapshot', 'ai_insights', 'report_definitions', 'bim_models']);

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  function toast(msg, ok) {
    const el = document.createElement('div');
    el.className = 'ops-toast ' + (ok ? 'ok' : 'err');
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  function projectRequired() {
    const pid = ctx.projectId || parseInt(window.CASEPM_ACTIVE_PROJECT_ID || localStorage.getItem('casepm_current_project_id'), 10);
    return pid || null;
  }

  function updateProjectBanner() {
    const banner = $('opsProjectBanner');
    if (!banner) return;
    const needs = state.schema?.project_scoped !== false && state.moduleKey && state.moduleKey !== 'wip_snapshot';
    const has = !!projectRequired();
    banner.classList.toggle('hidden', !needs || has);
  }

  async function api(path, opts) {
    const method = (opts?.method || 'GET').toUpperCase();
    const headers = {
      'X-Requested-With': 'XMLHttpRequest',
      ...(opts?.headers || {}),
    };
    if (!(opts?.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    const token = csrfToken();
    if (token && method !== 'GET' && method !== 'HEAD') {
      headers['X-CSRF-Token'] = token;
    }
    let url = path;
    if (method === 'GET' && !path.includes('?') && projectRequired()) {
      url += `?project_id=${projectRequired()}`;
    }
    const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText || 'Request failed');
    return data;
  }

  function hideAllHosts() {
    ['opsWipHost', 'opsAiHost', 'opsReportHost', 'opsBimHost', 'opsListHost'].forEach(id => {
      const el = $(id);
      if (el) el.classList.add('hidden');
    });
  }

  function renderSidebar() {
    const host = $('opsSidebar');
    if (!host) return;
    host.innerHTML = state.categories.map(cat => {
      const mods = (cat.modules || []).map(m => `
        <button type="button" class="ops-mod-btn ${state.moduleKey === m.key ? 'active' : ''}" data-mod="${m.key}" data-readonly="${m.read_only ? '1' : '0'}">
          ${shell.esc(m.label)}
        </button>`).join('');
      return `
        <button type="button" class="ops-cat-btn ${state.categoryId === cat.id ? 'active' : ''}" data-cat="${cat.id}">
          <i class="fa-solid ${cat.icon || 'fa-folder'} w-4"></i>${shell.esc(cat.label)}
        </button>
        <div class="${state.categoryId === cat.id ? '' : 'hidden'}" data-cat-mods="${cat.id}">${mods}</div>`;
    }).join('');
    host.querySelectorAll('[data-cat]').forEach(btn => {
      btn.addEventListener('click', () => { state.categoryId = btn.dataset.cat; renderSidebar(); });
    });
    host.querySelectorAll('[data-mod]').forEach(btn => {
      btn.addEventListener('click', () => selectModule(btn.dataset.mod, btn.dataset.readonly === '1'));
    });
  }

  async function selectModule(key, readOnly) {
    state.moduleKey = key;
    state.editingId = null;
    renderSidebar();
    const mod = findModule(key);
    $('opsModuleTitle').textContent = mod?.label || key;
    $('opsModuleHint').textContent = readOnly ? 'Live report' : 'Quick Add · click row to edit';
    hideAllHosts();
    document.querySelector('.ops-page')?.classList.toggle('ops-bim-active', key === 'bim_models');
    if (state.bimFullscreenCleanup) {
      state.bimFullscreenCleanup();
      state.bimFullscreenCleanup = null;
    }

    if (key === 'wip_snapshot') {
      $('opsWipHost').classList.remove('hidden');
      $('opsQuickAdd').classList.add('hidden');
      await renderWip();
      return;
    }
    $('opsQuickAdd').classList.remove('hidden');

    if (key === 'ai_insights') {
      $('opsAiHost').classList.remove('hidden');
      $('opsQuickAdd').classList.add('hidden');
      await loadRecords();
      renderAiPanel();
      return;
    }
    if (key === 'report_definitions') {
      await loadRecords();
      $('opsReportHost').classList.remove('hidden');
      renderReportBuilder();
      return;
    }
    if (key === 'bim_models') {
      await loadRecords();
      $('opsBimHost').classList.remove('hidden');
      renderBimPanel();
      return;
    }

    $('opsListHost').classList.remove('hidden');
    await loadRecords();
    updateProjectBanner();
  }

  function findModule(key) {
    for (const cat of state.categories) {
      const m = (cat.modules || []).find(x => x.key === key);
      if (m) return m;
    }
    return null;
  }

  async function loadRecords() {
    if (!state.moduleKey || state.moduleKey === 'wip_snapshot') return;
    const pid = projectRequired();
    const q = pid ? `?project_id=${pid}` : '';
    const data = await api(`/api/operations/${state.moduleKey}${q}`);
    state.records = data.records || [];
    state.schema = data.schema || state.schema || {};
    state.stats = data.stats || {};
    state.bimAssets = data.bim_assets || [];
    renderStats();
    if (!SPECIAL.has(state.moduleKey)) renderList();
    updateProjectBanner();
  }

  function renderStats() {
    const s = state.stats;
    $('opsStats').innerHTML = `
      <div><div class="text-xs text-zinc-500">Total</div><div class="text-xl font-semibold">${s.total || 0}</div></div>
      <div><div class="text-xs text-zinc-500">Open</div><div class="text-xl font-semibold text-amber-400">${s.open || 0}</div></div>
      <div><div class="text-xs text-zinc-500">Done</div><div class="text-xl font-semibold text-emerald-400">${s.closed || 0}</div></div>`;
  }

  function renderList() {
    const host = $('opsListHost');
    if (!state.records.length) {
      host.innerHTML = `<div class="p-8 text-center text-zinc-500">
        <i class="fa-solid fa-inbox text-3xl mb-3 opacity-40"></i>
        <p>No items yet. Click <strong>Quick Add</strong> above.</p>
      </div>`;
      return;
    }
    host.innerHTML = state.records.map(r => `
      <div class="ops-row" data-id="${r.id}">
        <div class="flex-1 min-w-0">
          <div class="font-medium text-white truncate">${shell.esc(r.title || r.number || 'Untitled')}</div>
          <div class="text-xs text-zinc-500">${shell.esc(r.record_date || '')}${r.amount ? ' · $' + Number(r.amount).toLocaleString() : ''}</div>
        </div>
        ${shell.statusChip(r.status)}
      </div>`).join('');
    host.querySelectorAll('.ops-row').forEach(row => {
      row.addEventListener('click', () => { openModal(parseInt(row.dataset.id, 10)); });
    });
  }

  async function renderWip() {
    const host = $('opsWipHost');
    host.innerHTML = '<div class="text-zinc-400">Loading WIP…</div>';
    const data = await api('/api/operations/wip');
    const w = data.wip || data;
    if (w.projects) {
      host.innerHTML = `<h3 class="text-lg font-semibold mb-3">Portfolio WIP</h3>
        <table class="w-full text-sm"><thead><tr class="text-zinc-500 text-left">
          <th class="pb-2">Project</th><th class="pb-2 text-right">Revised</th><th class="pb-2 text-right">Actual</th>
          <th class="pb-2 text-right">%</th><th class="pb-2 text-right">Over/(Under)</th>
        </tr></thead><tbody>${w.projects.map(p => `<tr class="border-b border-zinc-800">
          <td class="py-2">${shell.esc(p.project_name)}</td>
          <td class="py-2 text-right">$${Number(p.revised_contract).toLocaleString()}</td>
          <td class="py-2 text-right">$${Number(p.actual_cost).toLocaleString()}</td>
          <td class="py-2 text-right">${p.percent_complete}%</td>
          <td class="py-2 text-right">$${Number(p.over_under_billing).toLocaleString()}</td>
        </tr>`).join('')}</tbody></table>`;
      return;
    }
    host.innerHTML = `<h3 class="text-lg font-semibold mb-4">WIP — ${shell.esc(w.project_name || '')}</h3>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
        ${wipCard('Revised Contract', w.revised_contract)}${wipCard('Actual', w.actual_cost)}
        ${wipCard('% Complete', w.percent_complete + '%')}${wipCard('Over/(Under)', w.over_under_billing, true)}
        ${wipCard('Gross Profit %', w.gross_profit_pct + '%')}
      </div>`;
  }

  function wipCard(label, val, hi) {
    const d = typeof val === 'number' ? '$' + Number(val).toLocaleString() : val;
    return `<div class="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700"><div class="text-xs text-zinc-500">${label}</div><div class="text-lg font-semibold ${hi ? 'text-amber-400' : ''} mt-1">${d}</div></div>`;
  }

  function renderAiPanel() {
    const host = $('opsAiHost');
    host.innerHTML = `
      <div class="ops-chat">
        <div class="ops-chat-msgs" id="opsChatMsgs">${state.aiMessages.map(m => `
          <div class="ops-chat-bubble ${m.role}">${shell.esc(m.content)}</div>`).join('') || '<p class="text-zinc-500 text-sm">Ask anything about this project — schedule risk, billing, change orders, safety.</p>'}
        </div>
        <div class="flex gap-2 mt-3 pt-3 border-t border-zinc-800">
          <input id="opsChatInput" class="ops-input flex-1" placeholder="e.g. What are the biggest schedule risks?" />
          <button type="button" id="opsChatSend" class="px-4 py-2 bg-emerald-600 rounded-md text-sm font-semibold text-white">Ask</button>
        </div>
      </div>`;
    $('opsChatSend')?.addEventListener('click', sendAiMessage);
    $('opsChatInput')?.addEventListener('keydown', e => { if (e.key === 'Enter') sendAiMessage(); });
  }

  async function sendAiMessage() {
    const input = $('opsChatInput');
    const msg = (input?.value || '').trim();
    if (!msg) return;
    input.value = '';
    state.aiMessages.push({ role: 'user', content: msg });
    renderAiPanel();
    try {
      const data = await api('/api/operations/ai/chat', {
        method: 'POST',
        body: JSON.stringify({ message: msg, thread_id: state.aiThreadId, project_id: projectRequired() }),
      });
      state.aiThreadId = data.thread_id;
      state.aiMessages = data.messages || state.aiMessages;
      if (data.response) state.aiMessages.push({ role: 'assistant', content: data.response });
      renderAiPanel();
      const msgs = $('opsChatMsgs');
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
    } catch (e) {
      toast(e.message, false);
    }
  }

  function renderReportBuilder() {
    const host = $('opsReportHost');
    const sources = state.reportSources?.sources || [];
    host.innerHTML = `
      <h3 class="text-lg font-semibold mb-3">Report Builder</h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div><label class="text-xs text-zinc-400">Data source</label>
          <select id="opsReportSource" class="ops-input mt-1">${sources.map(s => `<option value="${s.key}">${shell.esc(s.label)}</option>`).join('')}</select></div>
        <div><label class="text-xs text-zinc-400">Status filter (optional)</label>
          <input id="opsReportFilter" class="ops-input mt-1" placeholder="e.g. Open"></div>
        <div class="flex items-end"><button type="button" id="opsRunReport" class="w-full px-4 py-2 bg-emerald-600 rounded-md text-sm font-semibold text-white">Run Report</button></div>
      </div>
      <div id="opsReportOut" class="text-sm text-zinc-400">Run a report or save a definition via Quick Add, then open it to re-run.</div>
      <div class="mt-4 border-t border-zinc-800 pt-3">
        <div class="text-xs text-zinc-500 mb-2">Saved definitions</div>
        <div id="opsReportList"></div>
      </div>`;
    const list = $('opsReportList');
    if (list) {
      list.innerHTML = state.records.length ? state.records.map(r => `
        <div class="ops-row" data-rid="${r.id}"><span>${shell.esc(r.title)}</span>${shell.statusChip(r.status)}</div>`).join('') : '<p class="text-zinc-600 text-sm">No saved reports — use Quick Add.</p>';
      list.querySelectorAll('.ops-row').forEach(row => {
        row.addEventListener('click', () => runSavedReport(parseInt(row.dataset.rid, 10)));
      });
    }
    $('opsRunReport')?.addEventListener('click', runAdhocReport);
  }

  async function runAdhocReport() {
    try {
      const data = await api('/api/operations/reports/run', {
        method: 'POST',
        body: JSON.stringify({
          project_id: projectRequired(),
          source: $('opsReportSource')?.value,
          filters: { status: $('opsReportFilter')?.value || '' },
        }),
      });
      state.lastReport = data;
      renderReportOutput(data);
      toast(`Report ready — ${data.row_count} rows`, true);
    } catch (e) { toast(e.message, false); }
  }

  async function runSavedReport(id) {
    try {
      const data = await api(`/api/operations/report_definitions/${id}/action`, {
        method: 'POST',
        body: JSON.stringify({ action: 'run_report' }),
      });
      renderReportOutput(data.report);
      toast(`Report ran — ${data.report?.row_count || 0} rows`, true);
    } catch (e) { toast(e.message, false); }
  }

  function renderReportOutput(data) {
    if (!data) return;
    const out = $('opsReportOut');
    if (!out) return;
    const rows = data.rows || [];
    if (!rows.length) { out.innerHTML = '<p class="text-zinc-500">No rows matched.</p>'; return; }
    const cols = Object.keys(rows[0]);
    out.innerHTML = `
      <div class="flex justify-between mb-2"><span>${data.row_count} rows · ${shell.esc(data.source)}</span>
        <button type="button" id="opsDownloadCsv" class="text-emerald-400 text-sm">Download CSV</button></div>
      <div class="overflow-auto max-h-80 border border-zinc-800 rounded-lg">
        <table class="w-full text-xs"><thead><tr class="text-zinc-500">${cols.map(c => `<th class="p-2 text-left">${c}</th>`).join('')}</tr></thead>
        <tbody>${rows.slice(0, 50).map(r => `<tr class="border-t border-zinc-800">${cols.map(c => `<td class="p-2">${shell.esc(r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table>
      </div>`;
    $('opsDownloadCsv')?.addEventListener('click', () => {
      const blob = new Blob([data.csv || ''], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `report-${data.source}-${Date.now()}.csv`;
      a.click();
    });
  }

  function mountBimAsset(asset) {
    if (!asset) return;
    state.activeBimAsset = asset;
    const viewer = $('opsBimViewer');
    const title = $('opsBimActiveTitle');
    if (title) title.textContent = asset.title || asset.filename || 'Model';
    if (window.CasePMBimViewer && viewer) {
      CasePMBimViewer.mount(viewer, asset.file_url, asset.file_ext, { fill: true });
    }
    $('opsBimPopout')?.toggleAttribute('disabled', !asset.id);
  }

  function renderBimPanel() {
    const host = $('opsBimHost');
    const assets = state.bimAssets || [];
    const active = state.activeBimAsset || assets[0] || null;
    state.activeBimAsset = active;
    host.innerHTML = `
      <div class="ops-bim-layout">
        <div class="flex justify-between items-center gap-3 mb-3 flex-shrink-0">
          <h3 class="text-lg font-semibold">BIM / 3D Models</h3>
          <label class="px-4 py-2 bg-emerald-600 rounded-md text-sm font-semibold text-white cursor-pointer">
            <i class="fa-solid fa-upload mr-1"></i> Upload model
            <input type="file" id="opsBimFile" class="hidden" accept=".glb,.gltf,.ifc,.obj,.pdf">
          </label>
        </div>
        <div id="opsBimStage" class="ops-bim-stage">
          <div class="ops-bim-stage-bar">
            <div class="min-w-0">
              <div id="opsBimActiveTitle" class="text-sm font-medium truncate">${shell.esc(active?.title || active?.filename || 'Select a model below')}</div>
              <div class="text-xs text-zinc-500">${active ? `.${shell.esc(active.file_ext)}` : 'Upload or pick from the list'}</div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <button type="button" id="opsBimFullscreen" class="px-3 py-1.5 text-xs rounded-md border border-zinc-700 hover:bg-zinc-800 text-white bg-transparent cursor-pointer" ${active ? '' : 'disabled'}>
                <i class="fa-solid fa-expand mr-1"></i> Full screen
              </button>
              <button type="button" id="opsBimPopout" class="px-3 py-1.5 text-xs rounded-md border border-zinc-700 hover:bg-zinc-800 text-white bg-transparent cursor-pointer" ${active?.id ? '' : 'disabled'}>
                <i class="fa-solid fa-up-right-from-square mr-1"></i> New window
              </button>
            </div>
          </div>
          <div id="opsBimViewer"></div>
        </div>
        <details class="ops-bim-list-wrap" ${assets.length ? 'open' : ''}>
          <summary>Models (${assets.length})</summary>
          <div id="opsBimList"></div>
        </details>
      </div>`;

    const list = $('opsBimList');
    if (!assets.length) {
      list.innerHTML = '<p class="text-zinc-500 text-sm p-3">Upload GLB, GLTF, or PDF models. GLB opens in the 3D viewer.</p>';
    } else {
      list.innerHTML = assets.map(a => `
        <div class="ops-row ${active?.id === a.id ? 'bg-emerald-500/10' : ''}" data-aid="${a.id}" data-url="${shell.esc(a.file_url)}" data-ext="${a.file_ext}" data-title="${shell.esc(a.title || a.filename)}">
          <div><div class="font-medium text-white">${shell.esc(a.title || a.filename)}</div>
          <div class="text-xs text-zinc-500">${shell.esc(a.discipline || '')} · Rev ${shell.esc(a.revision || '—')} · .${a.file_ext}</div></div>
        </div>`).join('');
      list.querySelectorAll('.ops-row').forEach(row => {
        row.addEventListener('click', () => {
          mountBimAsset({
            id: parseInt(row.dataset.aid, 10),
            file_url: row.dataset.url,
            file_ext: row.dataset.ext,
            title: row.dataset.title,
            filename: row.dataset.title,
          });
          list.querySelectorAll('.ops-row').forEach(r => r.classList.remove('bg-emerald-500/10'));
          row.classList.add('bg-emerald-500/10');
        });
      });
    }

    if (active) mountBimAsset(active);

    if (state.bimFullscreenCleanup) state.bimFullscreenCleanup();
    state.bimFullscreenCleanup = window.CasePMBimViewer?.bindFullscreen($('opsBimStage'), $('opsBimFullscreen'));

    $('opsBimPopout')?.addEventListener('click', () => {
      if (state.activeBimAsset?.id) CasePMBimViewer.openPopout(state.activeBimAsset.id);
    });
    $('opsBimFile')?.addEventListener('change', uploadBim);
  }

  async function uploadBim(ev) {
    const file = ev.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('project_id', projectRequired() || '');
    fd.append('title', file.name);
    const token = csrfToken();
    try {
      const res = await fetch('/api/operations/bim/upload', {
        method: 'POST',
        body: fd,
        credentials: 'same-origin',
        headers: token ? { 'X-CSRF-Token': token } : {},
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Upload failed');
      toast('Model uploaded', true);
      await loadRecords();
      renderBimPanel();
    } catch (e) { toast(e.message, false); }
  }

  function deriveTitle(fields) {
    if (fields.simple.title) return fields.simple.title.trim();
    const first = state.schema?.simple?.[0];
    if (first && fields.simple[first[0]]) return String(fields.simple[first[0]]).trim();
    return 'New item';
  }

  async function openModal(recordId) {
    if (!state.moduleKey) {
      toast('Select a module on the left first.', false);
      return;
    }
    if (!state.schema?.simple?.length) {
      try {
        await loadRecords();
      } catch (e) {
        toast(e.message, false);
        return;
      }
    }
    if (!state.schema?.simple?.length) {
      toast('Form not available for this module.', false);
      return;
    }
    if (!recordId && state.schema.project_scoped !== false && !projectRequired()) {
      toast('Select a current project first.', false);
      return;
    }
    const record = recordId ? state.records.find(r => r.id === recordId) : null;
    state.editingId = recordId || null;
    state.advancedOpen = false;
    $('opsModalTitle').textContent = record ? 'Edit' : 'Quick Add';
    $('opsModalBody').innerHTML = shell.buildFormHtml(state.schema, 'ops', record);
    const statuses = state.schema.statuses || ['Draft'];
    const statusRow = `<div><label class="block text-xs text-zinc-400 mb-1">Status</label><select id="ops_status" class="ops-input">${statuses.map(s => `<option ${(record?.status || statuses[0]) === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>`;
    $('opsModalBody').insertAdjacentHTML('afterbegin', statusRow);
    $('opsAdvanced')?.classList.add('hidden');
    $('opsToggleAdvanced').innerHTML = '<i class="fa-solid fa-chevron-down mr-1"></i> More options';
    renderActionButtons(record);
    $('opsModal').showModal();
  }

  function renderActionButtons(record) {
    document.getElementById('opsModalActions')?.remove();
    let actions = '';
    if (state.moduleKey === 'correspondence' && record) actions += `<button type="button" id="opsPromoteRfi" class="text-sm text-sky-400 bg-transparent border-none cursor-pointer">Promote to RFI</button>`;
    if (state.moduleKey === 'tm_tickets' && record) actions += `<button type="button" id="opsPromoteCe" class="text-sm text-sky-400 bg-transparent border-none cursor-pointer">→ Change Event</button>`;
    if (state.moduleKey === 'vendor_invoices' && record) actions += `<button type="button" id="opsValidateInv" class="text-sm text-violet-400 bg-transparent border-none cursor-pointer">Validate vs SOV</button>`;
    if (state.moduleKey === 'timesheets' && record) actions += `<button type="button" id="opsPostTs" class="text-sm text-emerald-400 bg-transparent border-none cursor-pointer">Post to job cost</button>`;
    if (state.moduleKey === 'payment_batches' && record) actions += `<button type="button" id="opsProcessPay" class="text-sm text-emerald-400 bg-transparent border-none cursor-pointer">Process payment batch</button>`;
    if (state.moduleKey === 'report_definitions' && record) actions += `<button type="button" id="opsRunSaved" class="text-sm text-emerald-400 bg-transparent border-none cursor-pointer">Run report</button>`;
    if (actions) {
      $('opsModalBody').insertAdjacentHTML('beforeend', `<div id="opsModalActions" class="flex flex-wrap gap-3 pt-2 border-t border-zinc-800 mt-2">${actions}</div>`);
      $('opsPromoteRfi')?.addEventListener('click', () => runAction('promote_rfi'));
      $('opsPromoteCe')?.addEventListener('click', () => runAction('promote_change_event'));
      $('opsValidateInv')?.addEventListener('click', () => runAction('validate_invoice'));
      $('opsPostTs')?.addEventListener('click', () => runAction('post_timesheet'));
      $('opsProcessPay')?.addEventListener('click', () => runAction('process_payment'));
      $('opsRunSaved')?.addEventListener('click', () => runAction('run_report'));
    }
  }

  async function runAction(action) {
    try {
      const data = await api(`/api/operations/${state.moduleKey}/${state.editingId}/action`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      if (data.validation) toast((data.validation.messages || []).join(' · ') || 'Validated', !data.validation.valid === false);
      if (data.message) toast(data.message, true);
      if (data.report) { state.lastReport = data.report; if (state.moduleKey === 'report_definitions') { $('opsReportHost')?.classList.remove('hidden'); renderReportBuilder(); renderReportOutput(data.report); } }
      if (data.warnings?.length) toast(data.warnings.join(' · '), false);
      await loadRecords();
      $('opsModal').close();
    } catch (e) { toast(e.message, false); }
  }

  async function saveModal() {
    const bodyEl = $('opsModalBody');
    if (!bodyEl || !state.moduleKey) return;
    if (!state.editingId && state.schema?.project_scoped !== false && !projectRequired()) {
      toast('Select a current project first.', false);
      return;
    }
    const btn = $('opsModalSave');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
      const fields = shell.readFields(bodyEl, state.schema, 'ops');
      const title = deriveTitle(fields);
      const body = {
        title,
        project_id: projectRequired(),
        simple: fields.simple,
        advanced: fields.advanced,
        status: $('ops_status')?.value,
        amount: fields.simple.amount,
        record_date: fields.simple.work_date || fields.simple.due_date || fields.simple.invoice_date || fields.simple.cost_date || fields.simple.payment_date || fields.simple.bid_date,
      };
      if (state.editingId) {
        await api(`/api/operations/${state.moduleKey}/${state.editingId}`, { method: 'PUT', body: JSON.stringify(body) });
        toast('Saved', true);
      } else {
        await api(`/api/operations/${state.moduleKey}`, { method: 'POST', body: JSON.stringify(body) });
        toast('Created', true);
      }
      $('opsModal').close();
      await loadRecords();
      if (state.moduleKey === 'report_definitions') renderReportBuilder();
      if (state.moduleKey === 'bim_models') renderBimPanel();
    } catch (e) {
      toast(e.message, false);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
    }
  }

  function bindUi() {
    $('opsQuickAdd')?.addEventListener('click', () => {
      if (SPECIAL.has(state.moduleKey)) {
        if (state.moduleKey === 'report_definitions') openModal(null);
        else toast('Use the panel controls for this tool.', false);
        return;
      }
      openModal(null);
    });
    $('opsModalClose')?.addEventListener('click', () => $('opsModal').close());
    $('opsModalCancel')?.addEventListener('click', () => $('opsModal').close());
    $('opsModalSave')?.addEventListener('click', () => saveModal());
    $('opsToggleAdvanced')?.addEventListener('click', () => {
      state.advancedOpen = !state.advancedOpen;
      $('opsAdvanced')?.classList.toggle('hidden', !state.advancedOpen);
      $('opsToggleAdvanced').innerHTML = state.advancedOpen
        ? '<i class="fa-solid fa-chevron-up mr-1"></i> Fewer options'
        : '<i class="fa-solid fa-chevron-down mr-1"></i> More options';
    });
  }

  async function init() {
    bindUi();
    const data = await api('/api/operations/catalog');
    state.categories = data.categories || [];
    state.reportSources = data.report_sources || {};
    if (state.categories.length) {
      state.categoryId = state.categories[0].id;
      const firstMod = state.categories[0].modules?.[0];
      if (firstMod) await selectModule(firstMod.key, firstMod.read_only);
    }
    renderSidebar();
    updateProjectBanner();
  }

  function boot() {
    init().catch(err => {
      console.error(err);
      toast(err.message, false);
      const host = $('opsListHost');
      if (host) host.innerHTML = `<div class="p-6 text-red-400">${shell.esc(err.message)}</div>`;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
