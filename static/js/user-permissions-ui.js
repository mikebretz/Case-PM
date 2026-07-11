/**
 * Case PM — User permissions matrix (admin only)
 */
(function (global) {
  'use strict';

  let catalog = null;
  let currentMatrix = null;

  const ACCESS_COLORS = {
    none: 'text-zinc-600',
    client_view: 'text-sky-400',
    view: 'text-zinc-300',
    entry: 'text-amber-400',
    edit: 'text-emerald-400',
    admin: 'text-violet-400',
  };

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function loadCatalog() {
    if (catalog) return catalog;
    const res = await fetch('/api/permissions/catalog', { credentials: 'same-origin' });
    const json = await res.json();
    catalog = json.catalog || json;
    return catalog;
  }

  function defaultMatrix(portal = 'staff') {
    const modules = {};
    (catalog?.groups || []).forEach(g => {
      (g.modules || []).forEach(([key]) => {
        modules[key] = { access: 'none', approve: 'none' };
      });
    });
    return { version: 2, portal, modules, global: { customized: true } };
  }

  function setMatrix(data) {
    currentMatrix = data && data.version === 2 ? JSON.parse(JSON.stringify(data)) : defaultMatrix();
    if (!currentMatrix.modules) currentMatrix.modules = {};
    if (!currentMatrix.global) currentMatrix.global = {};
    return currentMatrix;
  }

  function getMatrix() {
    return currentMatrix;
  }

  function render(containerId, matrix, opts) {
    const el = document.getElementById(containerId);
    if (!el || !catalog) return;
    currentMatrix = setMatrix(matrix);
    const options = opts || {};
    const approvalMods = new Set(catalog.approval_modules || []);

    let html = `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div>
          <label class="block text-[10px] uppercase text-zinc-500 mb-1">Portal / experience</label>
          <select id="permPortalSelect" class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm" onchange="CasePMPermissionsUI.setPortal(this.value)">
            ${(catalog.portal_types || []).map(([v, l]) =>
              `<option value="${v}" ${currentMatrix.portal === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}
          </select>
        </div>
        <div class="md:col-span-2 flex flex-wrap gap-2 items-end">
          <span class="text-[10px] uppercase text-zinc-500 w-full">Role templates</span>
          ${Object.keys(catalog.role_templates || {}).map(role =>
            `<button type="button" class="px-2.5 py-1 text-xs bg-zinc-700 hover:bg-zinc-600 rounded-lg" onclick="CasePMPermissionsUI.applyTemplate('${esc(role)}')">${esc(role)}</button>`
          ).join('')}
          <button type="button" class="px-2.5 py-1 text-xs bg-zinc-800 border border-zinc-600 rounded-lg" onclick="CasePMPermissionsUI.setAllAccess('none')">Clear all</button>
          <button type="button" class="px-2.5 py-1 text-xs bg-zinc-800 border border-zinc-600 rounded-lg" onclick="CasePMPermissionsUI.setAllAccess('view')">All view</button>
        </div>
      </div>
      <div class="text-[10px] text-zinc-500 mb-3 flex flex-wrap gap-3">
        ${(catalog.access_levels || []).map(([k, l]) =>
          `<span><span class="${ACCESS_COLORS[k] || ''}">■</span> ${esc(l)}</span>`).join('')}
      </div>`;

    (catalog.groups || []).forEach(group => {
      html += `
        <div class="mb-4 border border-zinc-800 rounded-xl overflow-hidden">
          <div class="bg-zinc-800/80 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">${esc(group.label)}</div>
          <table class="w-full text-sm">
            <thead class="text-[10px] uppercase text-zinc-500 border-b border-zinc-800">
              <tr>
                <th class="text-left px-4 py-2 w-[40%]">Module</th>
                <th class="text-left px-3 py-2">Access</th>
                <th class="text-left px-3 py-2">Approvals</th>
              </tr>
            </thead>
            <tbody>`;
      (group.modules || []).forEach(([key, label]) => {
        const mp = currentMatrix.modules[key] || { access: 'none', approve: 'none' };
        const showApprove = approvalMods.has(key);
        html += `<tr class="border-b border-zinc-800/60 hover:bg-zinc-800/30">
          <td class="px-4 py-2 font-medium text-zinc-200">${esc(label)}</td>
          <td class="px-3 py-2">
            <select class="perm-access w-full max-w-[200px] bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs ${ACCESS_COLORS[mp.access] || ''}"
                    data-module="${key}" onchange="CasePMPermissionsUI.onAccessChange(this)">
              ${(catalog.access_levels || []).map(([v, l]) =>
                `<option value="${v}" ${mp.access === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}
            </select>
          </td>
          <td class="px-3 py-2">`;
        if (showApprove) {
          html += `<select class="perm-approve w-full max-w-[200px] bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs"
                          data-module="${key}" onchange="CasePMPermissionsUI.onApproveChange(this)">
            ${(catalog.approve_levels || []).map(([v, l]) =>
              `<option value="${v}" ${mp.approve === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}
          </select>`;
        } else {
          html += `<span class="text-xs text-zinc-600">—</span>`;
        }
        html += `</td></tr>`;
      });
      html += `</tbody></table></div>`;
    });

    if (options.showGlobal) {
      html += `
        <div class="border border-zinc-800 rounded-xl p-4 mt-2">
          <div class="text-xs font-semibold text-zinc-400 mb-2 uppercase">Global options</div>
          <label class="flex items-center gap-2 text-sm cursor-pointer mb-2">
            <input type="checkbox" id="permClientPortalOnly" class="accent-emerald-600"
              ${currentMatrix.global?.client_portal_only ? 'checked' : ''}
              onchange="CasePMPermissionsUI.setGlobal('client_portal_only', this.checked)">
            Restrict to client/sub portal navigation only
          </label>
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" id="permHideFinancials" class="accent-emerald-600"
              ${currentMatrix.global?.hide_financials ? 'checked' : ''}
              onchange="CasePMPermissionsUI.setGlobal('hide_financials', this.checked)">
            Hide financial totals on client/consultant views
          </label>
        </div>`;
    }

    el.innerHTML = html;
  }

  async function initAndRender(containerId, matrix, opts) {
    await loadCatalog();
    render(containerId, matrix, opts);
  }

  function onAccessChange(sel) {
    const key = sel.dataset.module;
    if (!currentMatrix.modules[key]) currentMatrix.modules[key] = { access: 'none', approve: 'none' };
    currentMatrix.modules[key].access = sel.value;
    sel.className = `perm-access w-full max-w-[200px] bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs ${ACCESS_COLORS[sel.value] || ''}`;
    if (sel.value === 'none') currentMatrix.modules[key].approve = 'none';
  }

  function onApproveChange(sel) {
    const key = sel.dataset.module;
    if (!currentMatrix.modules[key]) currentMatrix.modules[key] = { access: 'view', approve: 'none' };
    currentMatrix.modules[key].approve = sel.value;
  }

  function setPortal(portal) {
    currentMatrix.portal = portal;
  }

  function setGlobal(key, val) {
    if (!currentMatrix.global) currentMatrix.global = {};
    currentMatrix.global[key] = !!val;
  }

  async function applyTemplate(role) {
    const res = await fetch(`/api/permissions/template/${encodeURIComponent(role)}`, { credentials: 'same-origin' });
    const json = await res.json();
    if (json.permissions) {
      render(document.querySelector('[id^="permissionsContainer"]')?.id || 'permissionsContainer', json.permissions, { showGlobal: true });
    }
  }

  function setAllAccess(level) {
    Object.keys(currentMatrix.modules || {}).forEach(k => {
      currentMatrix.modules[k] = { access: level, approve: level === 'none' ? 'none' : (currentMatrix.modules[k]?.approve || 'none') };
    });
    const host = document.getElementById('permissionsContainer');
    if (host) render(host.id, currentMatrix, { showGlobal: true });
  }

  function summaryLabel(matrix) {
    if (!matrix?.modules) return 'Default';
    const mods = Object.values(matrix.modules);
    const any = mods.filter(m => m.access && m.access !== 'none');
    const edits = any.filter(m => ['edit', 'admin'].includes(m.access));
    const approves = mods.filter(m => m.approve && m.approve !== 'none');
    if (!any.length) return 'No access';
    if (edits.length >= 10) return 'Broad edit';
    if (approves.length) return `${approves.length} approvals`;
    return `${any.length} modules`;
  }

  async function saveForUser(serverUserId, matrix) {
    const payload = matrix || currentMatrix;
    const res = await fetch(`/api/users/${serverUserId}/permissions`, {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ permissions: payload }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Could not save permissions');
    return json;
  }

  global.CasePMPermissionsUI = {
    loadCatalog, initAndRender, render, getMatrix, setMatrix,
    onAccessChange, onApproveChange, setPortal, setGlobal,
    applyTemplate, setAllAccess, summaryLabel, saveForUser,
  };
})(window);
