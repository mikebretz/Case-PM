/**
 * Accounting — Cost Code Library (project job cost catalog).
 */
(function (global) {
  'use strict';

  let ctx = null;
  let state = { library: null, cost_codes: [], cost_types: [], summary: null };

  function H() {
    return ctx || {};
  }

  function init(context) {
    ctx = context;
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  async function load() {
    const { api, projectId } = H();
    const pid = projectId();
    if (!pid) {
      state = { library: null, cost_codes: [], cost_types: [], summary: null };
      return;
    }
    const data = await api(`/api/accounting/cost-code-library?project_id=${pid}`);
    state.library = data.library || {};
    state.cost_codes = data.cost_codes || [];
    state.cost_types = data.cost_types || [];
    state.summary = data.summary || {};
    state.budget_url = data.budget_url;
    state.version = data.version;
  }

  function renderTypesEditor() {
    const types = state.library?.costTypes || [];
    if (!types.length) {
      return '<p class="text-xs text-zinc-500">No custom cost types yet — defaults from change orders still apply.</p>';
    }
    return `<ul class="text-sm space-y-1 max-h-40 overflow-y-auto">${types.map((t, i) => `
      <li class="flex justify-between items-center bg-zinc-800 rounded px-2 py-1">
        <span>${esc(t)}</span>
        <button type="button" class="text-red-400 text-xs" data-cc-remove-type="${i}">Remove</button>
      </li>`).join('')}</ul>`;
  }

  function renderCustomCodes() {
    const rows = state.library?.customCostCodes || [];
    if (!rows.length) {
      return '<p class="text-xs text-zinc-500">No custom library codes — budget line codes still appear in the picker.</p>';
    }
    return `<div class="overflow-x-auto max-h-56 overflow-y-auto border border-zinc-700 rounded">
      <table class="w-full text-xs">
        <thead class="text-zinc-500 sticky top-0 bg-zinc-900"><tr><th class="text-left p-2">Code</th><th class="text-left p-2">Description</th><th class="text-left p-2">Type</th><th></th></tr></thead>
        <tbody>${rows.map((r, i) => `<tr class="border-t border-zinc-800">
          <td class="p-2 font-mono text-emerald-400">${esc(r.code)}</td>
          <td class="p-2">${esc(r.description || '')}</td>
          <td class="p-2 text-zinc-400">${esc(r.cost_type || '')}</td>
          <td class="p-2"><button type="button" class="text-red-400" data-cc-remove-code="${i}">×</button></td>
        </tr>`).join('')}</tbody>
      </table>
    </div>`;
  }

  function renderPickerPreview(filter) {
    const q = (filter || '').trim().toLowerCase();
    let rows = state.cost_codes || [];
    if (q) {
      rows = rows.filter((r) => {
        const blob = `${r.code} ${r.description} ${r.cost_type}`.toLowerCase();
        return blob.includes(q);
      });
    }
    const shown = rows.slice(0, 80);
    return `<div class="overflow-x-auto max-h-64 overflow-y-auto border border-zinc-700 rounded text-xs">
      <table class="w-full">
        <thead class="text-zinc-500 sticky top-0 bg-zinc-900"><tr>
          <th class="text-left p-2">Code</th><th class="text-left p-2">Description</th><th class="text-left p-2">Type</th><th class="text-left p-2">Source</th>
        </tr></thead>
        <tbody>${shown.map((r) => `<tr class="border-t border-zinc-800">
          <td class="p-2 font-mono text-sky-400">${esc(r.code)}</td>
          <td class="p-2">${esc(r.description || '')}</td>
          <td class="p-2">${esc(r.cost_type || '')}</td>
          <td class="p-2 text-zinc-500">${r.original_budget != null && (r.original_budget || r.approved_changes) ? 'Budget' : 'Library'}</td>
        </tr>`).join('')}${!shown.length ? '<tr><td colspan="4" class="p-3 text-zinc-500">No codes match.</td></tr>' : ''}
      </tbody></table>
      ${rows.length > 80 ? `<p class="p-2 text-zinc-500">Showing 80 of ${rows.length} codes.</p>` : ''}
    </div>`;
  }

  async function render() {
    const { projectId } = H();
    const pid = projectId();
    if (!pid) {
      return `<p class="text-zinc-500 text-sm">Select a project to manage the cost code library.</p>`;
    }
    await load();
    const sum = state.summary || {};
    const active = state.library?.activeCostCodeList || 'csi';
    return `<div class="space-y-5 max-w-4xl">
      <div>
        <h2 class="text-lg font-semibold text-white">Cost Code Library</h2>
        <p class="text-xs text-zinc-400 mt-1">Central job cost catalog for this project (like Procore cost codes or Sage job phases). Pay applications, budget, commitments, and change orders pull from this list.</p>
      </div>
      <div class="grid md:grid-cols-3 gap-2 text-sm">
        <div class="bg-zinc-800 border border-zinc-700 rounded p-3"><span class="text-zinc-500 text-xs">Picker codes</span><br><strong>${sum.picker_count || 0}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-3"><span class="text-zinc-500 text-xs">From budget lines</span><br><strong>${sum.budget_line_codes || 0}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-3"><span class="text-zinc-500 text-xs">Custom library</span><br><strong>${sum.custom_codes || 0}</strong></div>
      </div>
      <div class="flex flex-wrap gap-2 text-xs">
        <a href="${esc(state.budget_url || '/budget')}" class="px-3 py-2 bg-zinc-800 border border-zinc-600 rounded hover:bg-zinc-700">Open Budget (lines &amp; CSI lists)</a>
        <a href="/program-settings?tab=sage" class="px-3 py-2 bg-zinc-800 border border-zinc-600 rounded hover:bg-zinc-700">Sage cost code prefix → Settings</a>
      </div>
      <div class="border border-zinc-700 rounded-lg p-4 space-y-3">
        <h3 class="text-sm font-medium text-zinc-200">Active code list</h3>
        <select id="ccLibActiveList" class="w-full max-w-md bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm">
          <option value="csi" ${active === 'csi' ? 'selected' : ''}>CSI Master (built-in)</option>
          <option value="custom" ${active === 'custom' ? 'selected' : ''}>Custom library codes</option>
        </select>
        <p class="text-[10px] text-zinc-500">Budget page uses this when adding lines from the master list. Budget dollar amounts always come from budget lines.</p>
      </div>
      <div class="border border-zinc-700 rounded-lg p-4 space-y-3">
        <div class="flex justify-between items-center">
          <h3 class="text-sm font-medium text-zinc-200">Cost types</h3>
          <button type="button" id="ccLibAddType" class="text-xs px-2 py-1 bg-emerald-800 rounded">Add type</button>
        </div>
        <div id="ccLibTypesWrap">${renderTypesEditor()}</div>
      </div>
      <div class="border border-zinc-700 rounded-lg p-4 space-y-3">
        <div class="flex justify-between items-center">
          <h3 class="text-sm font-medium text-zinc-200">Custom cost codes</h3>
          <button type="button" id="ccLibAddCode" class="text-xs px-2 py-1 bg-emerald-800 rounded">Add code</button>
        </div>
        <div id="ccLibCustomWrap">${renderCustomCodes()}</div>
      </div>
      <div class="border border-zinc-700 rounded-lg p-4 space-y-3">
        <h3 class="text-sm font-medium text-zinc-200">Effective picker (budget + library)</h3>
        <input type="search" id="ccLibPickerFilter" placeholder="Filter codes…" class="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm">
        <div id="ccLibPickerWrap">${renderPickerPreview()}</div>
      </div>
      <button type="button" id="ccLibSave" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded text-sm font-semibold">Save library to server</button>
      <p class="text-[10px] text-zinc-500">Version ${state.version || 0} · Changes sync to the same project budget state used across modules.</p>
    </div>`;
  }

  async function saveLibrary() {
    const { api, projectId, AD, switchModule } = H();
    const pid = projectId();
    const active = document.getElementById('ccLibActiveList')?.value || state.library?.activeCostCodeList || 'csi';
    const payload = {
      project_id: pid,
      library: {
        costTypes: state.library?.costTypes || [],
        customCostCodes: state.library?.customCostCodes || [],
        activeCostCodeList: active,
        costCodeLists: state.library?.costCodeLists || {},
      },
    };
    await api('/api/accounting/cost-code-library', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (global.CasePMCostCodeLibrary) global.CasePMCostCodeLibrary.invalidate(pid);
    await AD().alert('Cost code library saved.', 'success');
    if (switchModule) switchModule('cost-codes');
  }

  function refreshDomSections() {
    const tw = document.getElementById('ccLibTypesWrap');
    if (tw) tw.innerHTML = renderTypesEditor();
    const cw = document.getElementById('ccLibCustomWrap');
    if (cw) cw.innerHTML = renderCustomCodes();
    const pw = document.getElementById('ccLibPickerWrap');
    const filter = document.getElementById('ccLibPickerFilter')?.value || '';
    if (pw) pw.innerHTML = renderPickerPreview(filter);
  }

  function bindHandlers() {
    document.getElementById('ccLibSave')?.addEventListener('click', () => {
      saveLibrary().catch((e) => H().AD().alert(e.message, 'error'));
    });
    document.getElementById('ccLibAddType')?.addEventListener('click', async () => {
      const name = await H().AD().promptRequired('Cost type name', '', { title: 'Add cost type' });
      if (!name) return;
      const trimmed = String(name).trim();
      if (!trimmed) return;
      state.library = state.library || {};
      const types = state.library.costTypes || [];
      if (!types.includes(trimmed)) types.push(trimmed);
      state.library.costTypes = types;
      refreshDomSections();
    });
    document.getElementById('ccLibAddCode')?.addEventListener('click', async () => {
      const code = await H().AD().promptRequired('Cost code', '', { title: 'Add cost code' });
      if (!code) return;
      const desc = await H().AD().promptRequired('Description', '', { title: 'Add cost code' });
      if (!desc) return;
      state.library = state.library || {};
      const list = state.library.customCostCodes || [];
      list.push({ code: String(code).trim(), description: String(desc).trim() });
      state.library.customCostCodes = list;
      state.cost_codes = [...state.cost_codes, { code: String(code).trim(), description: String(desc).trim() }];
      refreshDomSections();
    });
    document.getElementById('ccLibPickerFilter')?.addEventListener('input', (e) => {
      const pw = document.getElementById('ccLibPickerWrap');
      if (pw) pw.innerHTML = renderPickerPreview(e.target.value);
    });
    document.getElementById('ccLibTypesWrap')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-cc-remove-type]');
      if (!btn) return;
      const idx = parseInt(btn.getAttribute('data-cc-remove-type'), 10);
      const types = [...(state.library?.costTypes || [])];
      types.splice(idx, 1);
      state.library.costTypes = types;
      refreshDomSections();
    });
    document.getElementById('ccLibCustomWrap')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-cc-remove-code]');
      if (!btn) return;
      const idx = parseInt(btn.getAttribute('data-cc-remove-code'), 10);
      const list = [...(state.library?.customCostCodes || [])];
      list.splice(idx, 1);
      state.library.customCostCodes = list;
      refreshDomSections();
    });
  }

  global.CasePMAcctCostCodesUI = { init, render, bindHandlers };
})(typeof window !== 'undefined' ? window : globalThis);
