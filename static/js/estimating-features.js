/**
 * Case PM Estimating — extended features (recommendations 1–29)
 */
(function (global) {
  'use strict';

  const EST = () => global.CasePMEstimating;
  const api = async (path, opts) => {
    const res = await fetch(path, { credentials: 'same-origin', ...opts, headers: { ...(opts?.headers || {}) } });
    const isJson = (opts?.headers?.['Content-Type'] || '').includes('json') || !opts?.body || typeof opts.body === 'string';
    const json = isJson ? await res.json().catch(() => ({})) : null;
    if (!res.ok) throw new Error(json?.error || 'Request failed');
    return json ?? res;
  };
  const apiJson = (path, opts = {}) => api(path, { ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) } });

  function fmt(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
  }
  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }
  function pid() {
    return EST()?.state?.current?.project_id || global.CASEPM_ESTIMATE_CTX?.projectId || global.CASEPM_ACTIVE_PROJECT_ID;
  }
  function estId() {
    return EST()?.state?.current?.id;
  }
  function openDialog(el) {
    if (!el) return;
    if (global.CasePMDialog?.open) global.CasePMDialog.open(el);
    else el.showModal();
  }
  function closeDialog(el) {
    el?.close?.();
  }
  async function alert(msg, type = 'info') {
    if (global.CasePMDialog?.alert) return global.CasePMDialog.alert(msg, type);
    window.alert(msg);
  }

  async function loadFeeBreakdown() {
    const id = estId();
    const el = document.getElementById('estFeeBreakdown');
    if (!id || !el) return;
    const fb = await apiJson(`/api/estimates/${id}/fee-breakdown`);
    el.innerHTML = `
      <div class="grid grid-cols-2 gap-2 text-sm">
        <div class="flex justify-between"><span class="text-zinc-500">Direct</span><span class="font-mono">${fmt(fb.direct_cost)}</span></div>
        ${fb.alternates_total > 0 ? `<div class="flex justify-between text-zinc-400"><span>Alternates (separate)</span><span class="font-mono">${fmt(fb.alternates_total)}</span></div>` : ''}
        <div class="flex justify-between"><span class="text-zinc-500">Contingency</span><span class="font-mono">${fmt(fb.contingency)}</span></div>
        <div class="flex justify-between"><span class="text-zinc-500">Overhead</span><span class="font-mono">${fmt(fb.overhead)}</span></div>
        <div class="flex justify-between"><span class="text-zinc-500">Profit</span><span class="font-mono">${fmt(fb.profit)}</span></div>
        <div class="flex justify-between"><span class="text-zinc-500">Tax</span><span class="font-mono">${fmt(fb.tax)}</span></div>
        <div class="flex justify-between font-semibold text-emerald-400"><span>Total</span><span class="font-mono">${fmt(fb.total)}</span></div>
      </div>`;
  }

  async function loadLibrary() {
    const el = document.getElementById('estLibraryList');
    if (!el) return;
    const { assemblies } = await apiJson(`/api/estimates/assemblies?project_id=${pid() || ''}`);
    el.innerHTML = assemblies.map(a => `
      <div class="border border-zinc-700 rounded-lg p-3 bg-zinc-900 flex justify-between gap-3 items-start">
        <div>
          <div class="font-medium">${esc(a.name)}</div>
          <div class="text-xs text-zinc-500">${esc(a.trade)} · Spec ${esc(a.spec_section)} · ${esc(a.unit)}</div>
          <div class="text-xs text-zinc-400 mt-1">${(a.components || []).length} component(s)</div>
        </div>
        <button type="button" class="text-emerald-400 text-sm apply-asm" data-id="${a.id}">Apply</button>
      </div>`).join('') || '<p class="text-zinc-500">No assemblies.</p>';
    el.querySelectorAll('.apply-asm').forEach(btn => btn.addEventListener('click', async () => {
      const qtyStr = global.CasePMDialog?.prompt
        ? await global.CasePMDialog.prompt('Quantity:', '1', { title: 'Apply Assembly' })
        : prompt('Quantity:', '1');
      const qty = parseFloat(qtyStr || '1') || 1;
      if (qtyStr == null) return;
      await apiJson(`/api/estimates/${estId()}/apply-assembly`, { method: 'POST', body: JSON.stringify({ assembly_id: parseInt(btn.dataset.id, 10), quantity: qty }) });
      await EST().loadCurrent();
      await alert('Assembly applied to worksheet.', 'success');
      EST().setTab('worksheet');
    }));
  }

  async function loadAlternates() {
    const el = document.getElementById('estAlternatesBody');
    if (!el || !estId()) return;
    const { alternates } = await apiJson(`/api/estimates/${estId()}/alternates`);
    const rows = alternates.length ? alternates : [{ alt_key: 'ALT-1', label: 'Alternate 1', include_in_base: false, amount: 0, notes: '' }];
    el.innerHTML = rows.map(a => `
      <tr>
        <td class="p-2"><input class="alt-key w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm" value="${esc(a.alt_key)}"></td>
        <td class="p-2"><input class="alt-label w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm" value="${esc(a.label)}"></td>
        <td class="p-2 text-center"><input type="checkbox" class="alt-base" ${a.include_in_base ? 'checked' : ''}></td>
        <td class="p-2 text-right font-mono">${fmt(a.amount)}</td>
        <td class="p-2"><input class="alt-notes w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm" value="${esc(a.notes)}"></td>
      </tr>`).join('');
  }

  async function saveAlternates() {
    const rows = [...document.querySelectorAll('#estAlternatesBody tr')].map(tr => ({
      alt_key: tr.querySelector('.alt-key')?.value,
      label: tr.querySelector('.alt-label')?.value,
      include_in_base: tr.querySelector('.alt-base')?.checked,
      notes: tr.querySelector('.alt-notes')?.value,
    }));
    await apiJson(`/api/estimates/${estId()}/alternates`, { method: 'POST', body: JSON.stringify({ alternates: rows }) });
    await loadAlternates();
    await alert('Alternates saved.', 'success');
  }

  async function loadSnapshots() {
    const el = document.getElementById('estSnapshotsList');
    if (!el || !estId()) return;
    const { snapshots } = await apiJson(`/api/estimates/${estId()}/snapshots`);
    el.innerHTML = snapshots.map(s => `
      <div class="flex justify-between items-center py-2 border-b border-zinc-800 text-sm">
        <span>${esc(s.label)} <span class="text-zinc-500 text-xs">${esc(s.created_at || '')}</span></span>
        <button type="button" class="text-sky-400 text-xs view-snap" data-id="${s.id}">View</button>
      </div>`).join('') || '<p class="text-zinc-500 text-sm">No snapshots yet.</p>';
    el.querySelectorAll('.view-snap').forEach(btn => btn.addEventListener('click', async () => {
      const data = await apiJson(`/api/estimates/${estId()}/snapshots/${btn.dataset.id}`);
      openDialog(document.getElementById('estSnapshotViewModal'));
      document.getElementById('estSnapshotViewBody').textContent = JSON.stringify(data, null, 2);
    }));
  }

  async function createSnapshot() {
    const label = await (global.CasePMDialog?.prompt ? global.CasePMDialog.prompt('Snapshot label:', `Rev ${new Date().toLocaleDateString()}`, { title: 'Save Snapshot' }) : prompt('Label:'));
    if (!label) return;
    await apiJson(`/api/estimates/${estId()}/snapshots`, { method: 'POST', body: JSON.stringify({ label }) });
    await loadSnapshots();
    await alert('Snapshot saved.', 'success');
  }

  async function loadMappings() {
    const el = document.getElementById('estMappingsBody');
    if (!el) return;
    const { mappings } = await apiJson(`/api/estimates/budget-mappings?project_id=${pid()}`);
    el.innerHTML = (mappings.length ? mappings : [{ spec_section: '', cost_code: '', cost_type: 'Subcontract' }]).map(m => `
      <tr>
        <td class="p-1"><input class="map-spec w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm" value="${esc(m.spec_section)}"></td>
        <td class="p-1"><input class="map-code w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm font-mono" value="${esc(m.cost_code)}"></td>
        <td class="p-1"><input class="map-type w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-sm" value="${esc(m.cost_type)}"></td>
      </tr>`).join('');
  }

  async function saveMappings() {
    const mappings = [...document.querySelectorAll('#estMappingsBody tr')].map(tr => ({
      spec_section: tr.querySelector('.map-spec')?.value,
      cost_code: tr.querySelector('.map-code')?.value,
      cost_type: tr.querySelector('.map-type')?.value,
    }));
    await apiJson('/api/estimates/budget-mappings', { method: 'POST', body: JSON.stringify({ project_id: pid(), mappings }) });
    await alert('Budget mappings saved.', 'success');
  }

  const liveTakeoffLines = [];

  function renderLiveTakeoffLines() {
    const body = document.getElementById('estTakeoffLiveLinesBody');
    if (!body) return;
    if (!liveTakeoffLines.length) {
      body.innerHTML = '<tr><td colspan="3" class="p-2 text-zinc-600">Measure on drawing to see lines here</td></tr>';
      return;
    }
    body.innerHTML = liveTakeoffLines.map((l, i) => `
      <tr class="hover:bg-zinc-800">
        <td class="px-2 py-1 text-zinc-300">${esc(l.description)}</td>
        <td class="px-2 py-1 text-right font-mono text-emerald-400">${l.quantity}</td>
        <td class="px-2 py-1 text-zinc-500">${esc(l.unit)}</td>
      </tr>`).join('');
  }

  function bindTakeoffChannel() {
    const id = estId();
    if (!id || typeof BroadcastChannel === 'undefined') return;
    if (global._estTakeoffChannel) return;
    global._estTakeoffChannel = new BroadcastChannel(global.CasePMEstimateTakeoff?.channelName(id) || `casepm-est-takeoff-${id}`);
    global._estTakeoffChannel.onmessage = ev => {
      const msg = ev.data || {};
      if (msg.type === 'takeoff-lines' && msg.lines?.length) {
        liveTakeoffLines.push(...msg.lines);
        renderLiveTakeoffLines();
        loadTakeoffLive().catch(() => {});
      }
      if (msg.type === 'markup-saved') loadTakeoffLive().catch(() => {});
    };
  }

  async function applyLiveTakeoffLines() {
    if (!liveTakeoffLines.length || !estId()) return alert('No live takeoff lines to add.', 'warning');
    const added = liveTakeoffLines.length;
    const lines = [...(EST()?.state?.current?.lines || []), ...liveTakeoffLines.map(row => ({
      cost_code: row.cost_code || row.spec_section || '01-000',
      spec_section: row.spec_section || '',
      description: row.description || '',
      cost_type: row.cost_type || 'Subcontract',
      quantity: row.quantity || 0,
      unit: row.unit || 'EA',
      unit_cost: row.unit_cost || 0,
      source: 'takeoff',
      source_ref: row.source_ref || '',
      group_key: row.group_key || '',
    }))];
    await apiJson(`/api/estimates/${estId()}`, { method: 'PUT', body: JSON.stringify({ lines }) });
    liveTakeoffLines.length = 0;
    renderLiveTakeoffLines();
    await EST().loadCurrent();
    await alert(`Added ${added} takeoff line(s) to worksheet.`, 'success');
    EST().setTab('worksheet');
  }
    const list = document.getElementById('estTakeoffLiveList');
    if (!estId()) return;
    const data = await apiJson(`/api/estimates/${estId()}/takeoff-live`);
    if (list) {
      list.innerHTML = (data.items || []).map(i => `
        <tr class="takeoff-row hover:bg-zinc-800 cursor-pointer" data-did="${i.drawing_id}" data-mid="${i.markup_id}">
          <td class="px-2 py-1 font-mono text-sky-400 text-xs">${esc(i.sheet_number)}</td>
          <td class="px-2 py-1 text-xs">${esc(i.description)}</td>
          <td class="px-2 py-1 text-right font-mono text-xs">${i.quantity}</td>
        </tr>`).join('') || '<tr><td colspan="3" class="p-4 text-zinc-500 text-sm">No markups — use measure/area tools in the viewer</td></tr>';
      list.querySelectorAll('.takeoff-row').forEach(row => row.addEventListener('click', () => {
        const did = parseInt(row.dataset.did, 10);
        if (global._estTakeoffViewer && did) {
          const sel = document.querySelector('.ett-drawing-select');
          if (sel) sel.value = String(did);
          global._estTakeoffViewer.refresh?.();
        }
      }));
    }
    initTakeoffViewer(data);
    bindTakeoffChannel();
  }

  function initTakeoffViewer(liveData) {
    const root = document.getElementById('estTakeoffViewer');
    if (!root || !global.CasePMEstimateTakeoff || !estId()) return;
    if (!global._estTakeoffViewer) {
      global._estTakeoffViewer = global.CasePMEstimateTakeoff.init(root, {
        projectId: pid(),
        estimateId: estId(),
        drawingId: liveData?.drawings?.[0]?.id,
      });
    } else {
      global._estTakeoffViewer.refresh?.();
    }
  }

  async function loadSettingsForm() {
    const id = estId();
    if (!id) return;
    const settings = await apiJson(`/api/estimates/${id}/settings`);
    const auto = document.getElementById('estAwardAutoCommitment');
    const mode = document.getElementById('estRfpNotifyMode');
    if (auto) auto.checked = !!settings.award_auto_commitment;
    if (mode) mode.value = settings.rfp_notify_mode || 'both';
  }

  async function saveSettings() {
    const id = estId();
    if (!id) return;
    await apiJson(`/api/estimates/${id}/settings`, {
      method: 'PUT',
      body: JSON.stringify({
        award_auto_commitment: !!document.getElementById('estAwardAutoCommitment')?.checked,
        rfp_notify_mode: document.getElementById('estRfpNotifyMode')?.value || 'both',
      }),
    });
    const json = await apiJson(`/api/estimates/${id}/settings`);
    if (EST()?.state?.current) EST().state.current.settings = json;
    await alert('Preferences saved.', 'success');
  }

  async function runBulkEdit() {
    const ids = [...document.querySelectorAll('#estWorksheetBody tr.selected')].map(tr => parseInt(tr.dataset.lineId, 10)).filter(Boolean);
    if (!ids.length) return alert('Select rows using checkboxes first.', 'warning');
    const costType = await (global.CasePMDialog?.prompt ? global.CasePMDialog.prompt('New cost type (leave blank to skip):', '', { title: 'Bulk Edit' }) : prompt('Cost type:'));
    const patch = {};
    if (costType) patch.cost_type = costType;
    const spec = await (global.CasePMDialog?.prompt ? global.CasePMDialog.prompt('New spec section (leave blank to skip):', '', { title: 'Bulk Edit' }) : prompt('Spec:'));
    if (spec) patch.spec_section = spec;
    if (!Object.keys(patch).length) return;
    await apiJson(`/api/estimates/${estId()}/bulk-edit`, { method: 'POST', body: JSON.stringify({ line_ids: ids, patch }) });
    await EST().loadCurrent();
    await alert(`Updated ${ids.length} row(s).`, 'success');
  }

  async function applyQuickFilter(kind) {
    const filters = { unpriced: kind === 'unpriced', source: kind === 'takeoff' ? 'takeoff' : undefined, kind: kind === 'alternate' ? 'alternate' : undefined };
    const data = await apiJson(`/api/estimates/${estId()}/filter-lines`, { method: 'POST', body: JSON.stringify({ filters }) });
    document.getElementById('estFilterSummary').textContent = `${data.count} line(s) · ${data.groups.length} group(s)`;
    if (EST()?.state?.current) {
      EST().state.current._filteredLines = data.lines;
      EST().renderWorksheet?.({ ...EST().state.current, lines: data.lines });
    }
  }

  async function lookupUnitCost(costCode) {
    const hist = await apiJson(`/api/estimates/cost-history?cost_code=${encodeURIComponent(costCode)}&project_id=${pid()}`);
    const row = hist.history?.[0];
    const msg = row ? `History: ${fmt(row.unit_cost)} / ${row.unit} — ${row.description || ''}` : '';
    await alert(msg || 'No historical pricing found for this cost code.', msg ? 'info' : 'warning');
  }

  async function runAiScope() {
    const text = document.getElementById('estAiScopeText')?.value || '';
    if (!text.trim()) return alert('Paste spec text first.', 'warning');
    const { suggestions } = await apiJson(`/api/estimates/${estId()}/ai-scope`, { method: 'POST', body: JSON.stringify({ text }) });
    const el = document.getElementById('estAiScopeResults');
    if (el) {
      el.innerHTML = suggestions.map(s => `<div class="text-sm py-1 border-b border-zinc-800">${esc(s.description)} · ${s.quantity} ${esc(s.unit)}</div>`).join('') || '<p class="text-zinc-500">No suggestions.</p>';
    }
  }

  async function applyAiScope() {
    const text = document.getElementById('estAiScopeText')?.value || '';
    await apiJson(`/api/estimates/${estId()}/ai-scope`, { method: 'POST', body: JSON.stringify({ text, apply: true }) });
    await EST().loadCurrent();
    await alert('AI scope lines added.', 'success');
    EST().setTab('worksheet');
  }

  function bindKeyboardShortcuts() {
    document.addEventListener('keydown', e => {
      if (!document.querySelector('.est-page')) return;
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        document.getElementById('estSaveLines')?.click();
      }
    });
  }

  function enhanceWorksheetRows() {
    const orig = EST()?.renderWorksheet;
    if (!orig || EST()._worksheetEnhanced) return;
    EST()._worksheetEnhanced = true;
    EST().renderWorksheet = function (est) {
      orig.call(this, est);
      EST().wireSpecSectionCells?.(document.getElementById('estWorksheetBody'));
      document.querySelectorAll('#estWorksheetBody tr').forEach((tr, i) => {
        const line = (est.lines || [])[i];
        if (line?.id) tr.dataset.lineId = line.id;
        if (line?.markup_id) {
          tr.classList.add('cursor-pointer');
          tr.title = 'Click cost code to open takeoff on drawing';
        }
        const cc = tr.querySelector('[data-f="cost_code"]');
        if (cc && !cc.dataset.lookup) {
          cc.dataset.lookup = '1';
          cc.addEventListener('dblclick', () => lookupUnitCost(cc.value));
        }
      });
      const head = document.querySelector('.est-sheet thead tr');
      if (head && !head.querySelector('.est-bulk-col')) {
        head.innerHTML = '<th class="est-bulk-col px-2"></th>' + head.innerHTML;
        document.querySelectorAll('#estWorksheetBody tr').forEach(tr => {
          const td = document.createElement('td');
          td.className = 'px-2 text-center';
          td.innerHTML = '<input type="checkbox" class="row-select">';
          td.querySelector('input').addEventListener('change', e => tr.classList.toggle('selected', e.target.checked));
          tr.prepend(td);
        });
      }
    };
  }

  function bindToolbar() {
    document.getElementById('estExportExcel')?.addEventListener('click', () => {
      window.location.href = `/api/estimates/${estId()}/export-excel`;
    });
    document.getElementById('estExportLevelingExcel')?.addEventListener('click', () => {
      window.location.href = `/api/estimates/${estId()}/export-leveling-excel`;
    });
    document.getElementById('estImportExcelInput')?.addEventListener('change', async e => {
      const file = e.target.files?.[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`/api/estimates/${estId()}/import-excel`, { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json();
      if (!res.ok) return alert(json.error, 'error');
      await EST().loadCurrent();
      await alert(`Imported ${json.imported} rows.`, 'success');
      e.target.value = '';
    });
    document.getElementById('estSaveSnapshot')?.addEventListener('click', () => createSnapshot().catch(e => alert(e.message, 'error')));
    document.getElementById('estSaveAlternates')?.addEventListener('click', () => saveAlternates().catch(e => alert(e.message, 'error')));
    document.getElementById('estSaveMappings')?.addEventListener('click', () => saveMappings().catch(e => alert(e.message, 'error')));
    document.getElementById('estSyncForecast')?.addEventListener('click', async () => {
      const json = await apiJson(`/api/estimates/${estId()}/sync-forecast`, { method: 'POST', body: '{}' });
      await alert(`Forecast ROM set to ${fmt(json.estimate_rom)}`, 'success');
    });
    document.getElementById('estContingencyDraw')?.addEventListener('click', async () => {
      const amtStr = global.CasePMDialog?.prompt
        ? await global.CasePMDialog.prompt('Contingency release amount ($):', '0', { title: 'Contingency Drawdown' })
        : prompt('Contingency release amount:', '0');
      if (amtStr == null) return;
      const amt = parseFloat(amtStr) || 0;
      if (!amt) return;
      await apiJson(`/api/estimates/${estId()}/contingency-drawdown`, { method: 'POST', body: JSON.stringify({ amount: amt, note: 'Estimate contingency release' }) });
      await alert('Contingency drawdown applied to budget.', 'success');
    });
    document.getElementById('estRunReminders')?.addEventListener('click', async () => {
      const json = await apiJson('/api/estimates/run-reminders', { method: 'POST', body: '{}' });
      await alert(`Sent ${json.reminders_sent} reminder(s).`, 'success');
    });
    document.getElementById('estBulkEdit')?.addEventListener('click', () => runBulkEdit().catch(e => alert(e.message, 'error')));
    document.querySelectorAll('[data-quick-filter]').forEach(btn => btn.addEventListener('click', () => applyQuickFilter(btn.dataset.quickFilter).catch(() => {})));
    document.getElementById('estAiScopePreview')?.addEventListener('click', () => runAiScope().catch(e => alert(e.message, 'error')));
    document.getElementById('estAiScopeApply')?.addEventListener('click', () => applyAiScope().catch(e => alert(e.message, 'error')));
    document.getElementById('estRefreshTakeoffLive')?.addEventListener('click', () => loadTakeoffLive().catch(() => {}));
    document.getElementById('estRefreshTakeoff')?.addEventListener('click', () => {
      loadTakeoffLive().catch(() => {});
      EST()?.loadTakeoffPreview?.();
    });
    document.getElementById('estApplyLiveTakeoff')?.addEventListener('click', () => applyLiveTakeoffLines().catch(e => alert(e.message, 'error')));
    document.getElementById('estPopoutTakeoff')?.addEventListener('click', () => {
      const q = new URLSearchParams({ project_id: pid(), estimate_id: estId() });
      const sel = document.querySelector('.ett-drawing-select');
      if (sel?.value) q.set('drawing_id', sel.value);
      window.open(`/estimating/takeoff-popout?${q}`, 'casepm-est-takeoff', 'width=1200,height=800,resizable=yes');
    });
    document.getElementById('estSaveSettings')?.addEventListener('click', () => saveSettings().catch(e => alert(e.message, 'error')));
  }

  function onTabChange(tab) {
    if (tab === 'summary') { loadFeeBreakdown(); loadSettingsForm(); }
    if (tab === 'library') loadLibrary();
    if (tab === 'alternates') loadAlternates();
    if (tab === 'award') loadMappings();
    if (tab === 'takeoff') {
      global._estTakeoffViewer = null;
      liveTakeoffLines.length = 0;
      renderLiveTakeoffLines();
      loadTakeoffLive();
      EST()?.loadTakeoffPreview?.();
    }
    if (tab === 'tools') loadSnapshots();
  }

  function hookTabs() {
    const orig = EST()?.setTab;
    if (!orig || EST()._tabsHooked) return;
    EST()._tabsHooked = true;
    EST().setTab = function (tab) {
      orig.call(this, tab);
      onTabChange(tab);
    };
  }

  function init() {
    if (!document.querySelector('.est-page')) return;
    enhanceWorksheetRows();
    hookTabs();
    bindToolbar();
    bindKeyboardShortcuts();
    document.querySelectorAll('.estModalClose, .est-ext-modal-close').forEach(btn => {
      btn.addEventListener('click', () => closeDialog(document.getElementById(btn.dataset.target)));
    });
    if (global.CasePMDialog?.initAllDialogs) global.CasePMDialog.initAllDialogs();
    setTimeout(() => onTabChange(EST()?.state?.tab || 'summary'), 500);
  }

  document.addEventListener('DOMContentLoaded', () => setTimeout(init, 100));

  global.CasePMEstimatingFeatures = {
    loadFeeBreakdown, loadLibrary, loadSnapshots, loadTakeoffLive, loadSettingsForm, onTabChange,
  };
})(window);
