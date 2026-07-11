/**
 * Case PM — pick files from project Documents for attachments/uploads.
 */
(function (global) {
  'use strict';

  let state = {
    folderId: null,
    folders: [],
    files: [],
    breadcrumbs: [],
    selected: new Set(),
    onPick: null,
    multiple: true,
    title: 'Browse Documents',
    projectIdOverride: null,
  };

  function projectId() {
    if (state.projectIdOverride != null) return state.projectIdOverride;
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  async function api(path) {
    const res = await fetch(path, { credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || json.message || 'Request failed');
    return json;
  }

  function dlg() {
    return document.getElementById('casepmDocPicker');
  }

  function updateSelectionUi() {
    const count = state.selected.size;
    const el = document.getElementById('casepmDocPickerCount');
    const btn = document.getElementById('casepmDocPickerAttach');
    if (el) el.textContent = `${count} selected`;
    if (btn) {
      btn.disabled = count === 0;
      btn.textContent = state.multiple ? 'Attach' : 'Select';
    }
  }

  function renderBreadcrumbs() {
    const el = document.getElementById('casepmDocPickerBreadcrumbs');
    if (!el) return;
    const crumbs = [{ id: null, name: 'All folders' }, ...(state.breadcrumbs || [])];
    el.innerHTML = crumbs.map((c, i) => {
      const isLast = i === crumbs.length - 1;
      const label = esc(c.name);
      if (isLast) return `<span class="text-zinc-300">${label}</span>`;
      return `<button type="button" class="text-sky-400 hover:underline" data-doc-crumb="${c.id ?? ''}">${label}</button><span class="text-zinc-600 mx-1">/</span>`;
    }).join('');
    el.querySelectorAll('[data-doc-crumb]').forEach(btn => {
      btn.addEventListener('click', () => {
        const raw = btn.dataset.docCrumb;
        loadBrowse(raw === '' ? null : parseInt(raw, 10));
      });
    });
  }

  function renderBody() {
    const body = document.getElementById('casepmDocPickerBody');
    if (!body) return;
    const folders = state.folders || [];
    const files = state.files || [];
    if (!folders.length && !files.length) {
      body.innerHTML = '<div class="p-6 text-center text-zinc-500 text-sm">No folders or files here.</div>';
      return;
    }
    const folderRows = folders.map(f => `
      <button type="button" class="doc-picker-row w-full flex items-center gap-3 px-4 py-2.5 text-left border-b border-zinc-800/80 hover:bg-zinc-800/50" data-doc-folder="${f.id}">
        <i class="fa-solid fa-folder text-amber-400"></i>
        <span class="flex-1 truncate text-sm">${esc(f.name)}</span>
        <span class="text-xs text-zinc-500">${f.file_count || 0} files</span>
      </button>`).join('');
    const fileRows = files.map(f => {
      const checked = state.selected.has(f.id) ? 'checked' : '';
      return `
      <label class="doc-picker-row w-full flex items-center gap-3 px-4 py-2.5 text-left border-b border-zinc-800/80 hover:bg-zinc-800/50 cursor-pointer">
        <input type="${state.multiple ? 'checkbox' : 'radio'}" name="casepm-doc-pick" value="${f.id}" class="accent-emerald-500" ${checked}>
        <i class="fa-solid fa-file text-sky-400"></i>
        <span class="flex-1 truncate text-sm">${esc(f.name || f.original_filename || f.filename)}</span>
        <span class="text-xs text-zinc-500">${f.extension || ''}</span>
      </label>`;
    }).join('');
    body.innerHTML = folderRows + fileRows;
    body.querySelectorAll('[data-doc-folder]').forEach(btn => {
      btn.addEventListener('click', () => loadBrowse(parseInt(btn.dataset.docFolder, 10)));
    });
    body.querySelectorAll('input[name="casepm-doc-pick"]').forEach(input => {
      input.addEventListener('change', () => {
        const id = parseInt(input.value, 10);
        if (!state.multiple) state.selected.clear();
        if (input.checked) state.selected.add(id);
        else state.selected.delete(id);
        if (!state.multiple && input.checked) {
          body.querySelectorAll('input[name="casepm-doc-pick"]').forEach(other => {
            if (other !== input) other.checked = false;
          });
        }
        updateSelectionUi();
      });
    });
  }

  async function loadBrowse(folderId) {
    const pid = projectId();
    if (!pid) return;
    state.folderId = folderId;
    const body = document.getElementById('casepmDocPickerBody');
    if (body) body.innerHTML = '<div class="p-6 text-center text-zinc-500 text-sm">Loading…</div>';
    try {
      const q = folderId != null ? `project_id=${pid}&folder_id=${folderId}` : `project_id=${pid}`;
      const json = await api(`/api/documents/browse?${q}`);
      state.folders = json.folders || [];
      state.files = json.files || [];
      state.breadcrumbs = json.breadcrumbs || [];
      renderBreadcrumbs();
      renderBody();
    } catch (e) {
      if (body) body.innerHTML = `<div class="p-6 text-center text-red-400 text-sm">${esc(e.message)}</div>`;
    }
  }

  async function search(query) {
    const pid = projectId();
    if (!pid) return;
    const body = document.getElementById('casepmDocPickerBody');
    if (body) body.innerHTML = '<div class="p-6 text-center text-zinc-500 text-sm">Searching…</div>';
    try {
      const json = await api(`/api/documents/search?project_id=${pid}&q=${encodeURIComponent(query)}`);
      state.folders = json.folders || [];
      state.files = json.files || [];
      state.breadcrumbs = [{ id: null, name: `Search: ${query}` }];
      renderBreadcrumbs();
      renderBody();
    } catch (e) {
      if (body) body.innerHTML = `<div class="p-6 text-center text-red-400 text-sm">${esc(e.message)}</div>`;
    }
  }

  function close() {
    dlg()?.close();
    state.onPick = null;
    state.projectIdOverride = null;
  }

  async function confirmPick() {
    const ids = [...state.selected];
    if (!ids.length) return;
    let docs = (state.files || []).filter(f => ids.includes(f.id));
    if (state.accept === 'pdf') {
      docs = docs.filter(d => {
        const ext = (d.extension || d.filename || d.name || '').toLowerCase();
        return ext.endsWith('.pdf') || ext === 'pdf';
      });
      if (!docs.length) {
        alert('Please select PDF files only.');
        return;
      }
    }
    const cb = state.onPick;
    close();
    if (typeof cb === 'function') await cb(docs, docs.map(d => d.id));
  }

  /**
   * Open document picker.
   * @param {{ title?: string, multiple?: boolean, accept?: string, projectId?: number, onPick: (docs: object[], ids: number[]) => void|Promise }} options
   */
  async function open(options = {}) {
    const modal = dlg();
    if (!modal) {
      alert('Document picker is not available on this page.');
      return;
    }
    state.onPick = options.onPick || null;
    state.multiple = options.multiple !== false;
    state.accept = (options.accept || '').toLowerCase();
    state.selected = new Set();
    state.title = options.title || 'Browse Documents';
    state.projectIdOverride = options.projectId != null ? parseInt(options.projectId, 10) : null;
    const attachBtn = document.getElementById('casepmDocPickerAttach');
    if (attachBtn) attachBtn.textContent = state.multiple ? 'Attach' : 'Select';
    const titleEl = document.getElementById('casepmDocPickerTitle');
    if (titleEl) titleEl.textContent = state.title;
    const searchEl = document.getElementById('casepmDocPickerSearch');
    if (searchEl) searchEl.value = '';
    updateSelectionUi();
    modal.showModal();
    await loadBrowse(null);
  }

  async function linkToEntity(entityType, entityId, documentIds) {
    const res = await fetch('/api/attachments/link', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId, document_ids: documentIds }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Link failed');
    return json;
  }

  /**
   * Add a "Browse Documents" button next to a file input or container.
   */
  function addBrowseButton(container, options = {}) {
    if (!container) return null;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = options.className || 'px-3 py-1.5 text-xs font-medium bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md text-zinc-200';
    btn.innerHTML = '<i class="fa-solid fa-folder-tree mr-1.5"></i>Browse Documents';
    btn.addEventListener('click', () => {
      const pid = typeof options.getProjectId === 'function'
        ? options.getProjectId()
        : options.projectId;
      if (!pid) {
        alert(options.projectRequiredMessage || 'Save the project first, then choose from Documents.');
        return;
      }
      open({
        title: options.title || 'Select from Documents',
        multiple: options.multiple !== false,
        accept: options.accept,
        projectId: pid,
        onPick: async (docs, ids) => {
          const entityId = typeof options.getEntityId === 'function'
            ? options.getEntityId()
            : options.entityId;
          if (options.entityType && entityId) {
            await linkToEntity(options.entityType, entityId, ids);
          }
          if (typeof options.onPick === 'function') await options.onPick(docs, ids);
        },
      });
    });
    if (options.insertBefore) container.insertBefore(btn, options.insertBefore);
    else container.appendChild(btn);
    return btn;
  }

  function bindUi() {
    document.getElementById('casepmDocPickerClose')?.addEventListener('click', close);
    document.getElementById('casepmDocPickerCancel')?.addEventListener('click', close);
    document.getElementById('casepmDocPickerAttach')?.addEventListener('click', confirmPick);
    document.getElementById('casepmDocPickerSearchBtn')?.addEventListener('click', () => {
      const q = document.getElementById('casepmDocPickerSearch')?.value?.trim();
      if (q) search(q);
      else loadBrowse(state.folderId);
    });
    document.getElementById('casepmDocPickerSearch')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const q = e.target.value?.trim();
        if (q) search(q);
        else loadBrowse(state.folderId);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindUi);
  } else {
    bindUi();
  }

  global.CasePMDocPicker = { open, close, linkToEntity, addBrowseButton, projectId };
})(window);
