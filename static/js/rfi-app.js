/**
 * Case PM — RFI module
 */
(function (global) {
  'use strict';

  const STATUSES = ['Draft', 'Open', 'Under Review', 'Awaiting Response', 'Answered', 'Closed', 'Void'];
  const PRIORITIES = ['Low', 'Medium', 'High', 'Critical'];
  const DISCIPLINES = ['Architectural', 'Structural', 'Civil', 'MEP', 'Electrical', 'Plumbing', 'Fire Protection', 'General'];

  let state = {
    rfis: [],
    stats: {},
    companies: [],
    users: [],
    linkOptions: { change_orders: [], pcos: [] },
    selected: null,
    filter: { search: '', status: '', priority: '', ball: '' },
    drawerRecord: null,
    modalMode: 'create',
    modalRfiId: null,
    modalAttachments: [],
    pendingFiles: [],
    pendingDocLinks: [],
    docPickerFolderId: null,
    docPickerSelected: new Set(),
    docPickerFiles: [],
    docPickerFolders: [],
    docPickerBreadcrumbs: [],
    allocationRows: [],
  };

  function isStaffPortal() {
    if (typeof global.CasePMApprovalResponder !== 'undefined' && global.CasePMApprovalResponder.isStaffPortal) {
      return global.CasePMApprovalResponder.isStaffPortal();
    }
    const p = global.CASEPM_PORTAL;
    return !p || p.portal === 'staff' || p.role === 'Admin';
  }

  function canDeleteRfi() {
    if (global.CASEPM_IS_DEVELOPER) return true;
    if (document.body?.dataset?.isDeveloper === '1') return true;
    if (document.body?.dataset?.isAdmin === '1') return true;
    const p = global.CASEPM_PORTAL || {};
    return p.isAdmin === true || p.role === 'Admin' || p.role === 'Developer';
  }

  function canEnterRfis() {
    if (typeof global.canAccessModule === 'function') {
      return global.canAccessModule('rfis', 'entry');
    }
    return isStaffPortal();
  }

  function canEditRfis() {
    if (typeof global.canAccessModule === 'function') {
      return global.canAccessModule('rfis', 'edit');
    }
    return isStaffPortal();
  }

  async function openResponder(id) {
    if (!canEnterRfis()) {
      await view(id);
      return;
    }
    if (typeof global.CasePMApprovalResponder !== 'undefined') {
      await global.CasePMApprovalResponder.open('rfi', id);
      return;
    }
    await respond(id);
  }

  async function refresh() {
    await Promise.all([loadRfis(), loadDashboard()]);
  }

  function fmtFileSize(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function attachmentHref(att, rfiId) {
    if (att.url) return att.url;
    if (att.document_id) return `/api/documents/${att.document_id}/download`;
    if (att.filename && rfiId) return `/uploads/rfis/${rfiId}/${att.filename}`;
    return '#';
  }

  function stripAttachmentMeta(att) {
    const { url, source, pending, file_size, ...rest } = att;
    return rest;
  }

  function attachmentCount(r) {
    return (r?.attachments || []).length;
  }

  function totalModalAttachmentCount() {
    return state.modalAttachments.length + state.pendingFiles.length + state.pendingDocLinks.length;
  }

  function updateAttachmentBadge() {
    const count = totalModalAttachmentCount();
    const badge = document.getElementById('rfiAttachmentCountBadge');
    const text = document.getElementById('rfiAttachmentCountText');
    if (!badge || !text) return;
    if (count > 0) {
      badge.classList.remove('hidden');
      badge.classList.add('inline-flex');
      text.textContent = String(count);
    } else {
      badge.classList.add('hidden');
      badge.classList.remove('inline-flex');
    }
  }

  function scrollToAttachments() {
    document.getElementById('rfiAttachmentsSection')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function setActiveRfiForAttachments(rfiId) {
    state.modalRfiId = rfiId || null;
  }

  function resetModalAttachments() {
    state.modalRfiId = null;
    state.modalAttachments = [];
    state.pendingFiles = [];
    state.pendingDocLinks = [];
    renderModalAttachments();
  }

  function renderModalAttachments() {
    const el = document.getElementById('rfiAttachmentList');
    const hint = document.getElementById('rfiAttachmentHint');
    if (!el) return;
    const rfiId = state.modalRfiId;
    const pendingCount = state.pendingFiles.length + state.pendingDocLinks.length;
    const items = [...state.modalAttachments];
    state.pendingFiles.forEach((file, i) => {
      items.push({
        original_name: file.name,
        pending: true,
        pending_type: 'file',
        pending_index: i,
        file_size: file.size,
      });
    });
    state.pendingDocLinks.forEach((doc, i) => {
      items.push({
        document_id: doc.id,
        original_name: doc.name,
        linked_from_documents: true,
        pending: true,
        pending_type: 'document',
        pending_index: i,
      });
    });
    if (!items.length) {
      el.innerHTML = `<div class="flex items-center gap-3 rounded-lg border border-dashed border-zinc-700 bg-zinc-900/40 px-4 py-3 text-xs text-zinc-500">
        <i class="fa-solid fa-file-circle-plus text-lg text-zinc-600"></i>
        <span>No files attached yet — use the upload area above to add supporting documents.</span>
      </div>`;
      if (hint) hint.textContent = rfiId ? 'Saved to Documents › RFIs' : 'Files attach automatically when you save';
      updateAttachmentBadge();
      return;
    }
    if (hint) {
      hint.textContent = rfiId
        ? 'Uploads are filed to Documents › RFIs'
        : `${pendingCount ? pendingCount + ' file(s) ready — ' : ''}will attach when you save`;
    }
    el.innerHTML = items.map((att, idx) => {
      const name = esc(att.original_name || att.filename || 'File');
      const badge = att.linked_from_documents || att.document_id
        ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-sky-900/50 text-sky-300">Documents</span>'
        : att.pending
          ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/50 text-amber-300">Pending</span>'
          : '<span class="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300">Upload</span>';
      const size = att.file_size ? `<span class="text-zinc-500">${fmtFileSize(att.file_size)}</span>` : '';
      const link = att.pending
        ? `<span class="text-zinc-200 truncate flex-1">${name}</span>`
        : `<a href="${esc(attachmentHref(att, rfiId))}" target="_blank" rel="noopener" class="text-sky-400 hover:underline truncate flex-1">${name}</a>`;
      return `<div class="rfi-attachment-row">
        <i class="fa-solid ${att.document_id || att.linked_from_documents ? 'fa-file-lines text-sky-400' : 'fa-paperclip text-zinc-400'}"></i>
        ${link}
        ${size}
        ${badge}
        <button type="button" class="text-zinc-500 hover:text-red-400 p-1" data-rfi-att-remove="${idx}" title="Remove"><i class="fa-solid fa-times"></i></button>
      </div>`;
    }).join('');
    el.querySelectorAll('[data-rfi-att-remove]').forEach(btn => {
      btn.addEventListener('click', () => removeModalAttachment(parseInt(btn.dataset.rfiAttRemove, 10)));
    });
    updateAttachmentBadge();
  }

  async function loadModalAttachments(rfiId) {
    if (!rfiId) {
      resetModalAttachments();
      return;
    }
    state.modalRfiId = rfiId;
    state.pendingFiles = [];
    state.pendingDocLinks = [];
    try {
      const json = await api(`/api/rfis/${rfiId}/attachments`);
      state.modalAttachments = json.attachments || [];
    } catch {
      state.modalAttachments = [];
    }
    renderModalAttachments();
  }

  async function uploadFilesToRfi(rfiId, files) {
    if (!rfiId || !files?.length) return;
    for (const file of files) {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`/api/rfis/${rfiId}/attachments`, { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || 'Upload failed');
      if (json.attachments) state.modalAttachments = json.attachments;
    }
  }

  async function linkDocumentsToRfi(rfiId, docIds) {
    if (!rfiId || !docIds?.length) return;
    for (const docId of docIds) {
      const json = await api(`/api/rfis/${rfiId}/attachments/link`, {
        method: 'POST',
        body: JSON.stringify({ document_id: docId }),
      });
      if (json.attachments) state.modalAttachments = json.attachments;
    }
  }

  async function flushPendingAttachments(rfiId) {
    if (!rfiId) return;
    const files = [...state.pendingFiles];
    const docs = [...state.pendingDocLinks];
    state.pendingFiles = [];
    state.pendingDocLinks = [];
    if (files.length) await uploadFilesToRfi(rfiId, files);
    if (docs.length) await linkDocumentsToRfi(rfiId, docs.map(d => d.id));
    state.modalRfiId = rfiId;
    await loadModalAttachments(rfiId);
  }

  async function removeModalAttachment(displayIndex) {
    const rfiId = state.modalRfiId;
    const savedCount = state.modalAttachments.length;
    if (displayIndex < savedCount) {
      if (!rfiId) return;
      const next = state.modalAttachments.filter((_, i) => i !== displayIndex).map(stripAttachmentMeta);
      await api(`/api/rfis/${rfiId}`, { method: 'PUT', body: JSON.stringify({ attachments: next }) });
      state.modalAttachments = next;
      renderModalAttachments();
      return;
    }
    const pendingIdx = displayIndex - savedCount;
    const filePendingCount = state.pendingFiles.length;
    if (pendingIdx < filePendingCount) {
      state.pendingFiles.splice(pendingIdx, 1);
    } else {
      state.pendingDocLinks.splice(pendingIdx - filePendingCount, 1);
    }
    renderModalAttachments();
  }

  async function handleAttachmentFiles(fileList) {
    const files = Array.from(fileList || []).filter(f => f && f.name);
    if (!files.length) return;
    if (state.modalRfiId) {
      try {
        await uploadFilesToRfi(state.modalRfiId, files);
        renderModalAttachments();
        toast('File(s) attached');
      } catch (e) { alert(e.message); }
      return;
    }
    state.pendingFiles.push(...files);
    renderModalAttachments();
  }

  function bindDrawerAttachmentHandlers(rfiId) {
    const dropZone = document.getElementById('rfiDrawerDropZone');
    const fileInput = document.getElementById('rfiDrawerAttachmentInput');
    if (!dropZone || !fileInput) return;

    const onFiles = async (files) => {
      const list = Array.from(files || []).filter(f => f?.name);
      if (!list.length) return;
      setActiveRfiForAttachments(rfiId);
      try {
        await uploadFilesToRfi(rfiId, list);
        toast('File(s) attached');
        await view(rfiId);
      } catch (e) { alert(e.message); }
      fileInput.value = '';
    };

    dropZone.onclick = e => {
      if (e.target.closest('[data-drawer-docs]')) return;
      fileInput.click();
    };
    fileInput.onchange = e => { onFiles(e.target.files); };
    dropZone.querySelector('[data-drawer-docs]')?.addEventListener('click', e => {
      e.stopPropagation();
      setActiveRfiForAttachments(rfiId);
      openDocumentPicker();
    });

    ['dragenter', 'dragover'].forEach(evt => {
      dropZone.addEventListener(evt, e => {
        e.preventDefault();
        dropZone.classList.add('rfi-drop-active');
      });
    });
    ['dragleave', 'drop'].forEach(evt => {
      dropZone.addEventListener(evt, e => {
        e.preventDefault();
        if (evt === 'drop') onFiles(e.dataTransfer?.files);
        dropZone.classList.remove('rfi-drop-active');
      });
    });
  }

  function bindAttachmentHandlers() {
    const dropZone = document.getElementById('rfiAttachmentDropZone');
    const fileInput = document.getElementById('rfiAttachmentInput');
    const browseBtn = document.getElementById('rfiBrowseFilesBtn');
    const docsBtn = document.getElementById('rfiBrowseDocumentsBtn');

    browseBtn?.addEventListener('click', e => { e.stopPropagation(); fileInput?.click(); });
    if (docsBtn) {
      docsBtn.classList.toggle('hidden', !isStaffPortal());
      docsBtn.addEventListener('click', e => { e.stopPropagation(); openDocumentPicker(); });
    }
    dropZone?.addEventListener('click', e => {
      if (e.target.closest('button')) return;
      fileInput?.click();
    });
    fileInput?.addEventListener('change', e => {
      handleAttachmentFiles(e.target.files);
      e.target.value = '';
    });

    if (dropZone) {
      ['dragenter', 'dragover'].forEach(evt => {
        dropZone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          dropZone.classList.add('rfi-drop-active');
        });
      });
      ['dragleave', 'drop'].forEach(evt => {
        dropZone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          if (evt === 'drop') handleAttachmentFiles(e.dataTransfer?.files);
          dropZone.classList.remove('rfi-drop-active');
        });
      });
    }

    document.getElementById('rfiDocumentPickerClose')?.addEventListener('click', closeDocumentPicker);
    document.getElementById('rfiDocPickerCancel')?.addEventListener('click', closeDocumentPicker);
    document.getElementById('rfiDocPickerAttach')?.addEventListener('click', confirmDocPickerAttach);
    document.getElementById('rfiDocPickerSearchBtn')?.addEventListener('click', () => {
      const q = document.getElementById('rfiDocPickerSearch')?.value?.trim();
      if (q) searchDocPicker(q);
      else loadDocPickerBrowse(state.docPickerFolderId);
    });
    document.getElementById('rfiDocPickerSearch')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const q = e.target.value?.trim();
        if (q) searchDocPicker(q);
        else loadDocPickerBrowse(state.docPickerFolderId);
      }
    });
  }

  function updateDocPickerSelectionUi() {
    const count = state.docPickerSelected.size;
    const el = document.getElementById('rfiDocPickerSelectedCount');
    const btn = document.getElementById('rfiDocPickerAttach');
    if (el) el.textContent = `${count} selected`;
    if (btn) btn.disabled = count === 0;
  }

  function renderDocPickerBreadcrumbs() {
    const el = document.getElementById('rfiDocPickerBreadcrumbs');
    if (!el) return;
    const crumbs = [{ id: null, name: 'All folders' }, ...(state.docPickerBreadcrumbs || [])];
    el.innerHTML = crumbs.map((c, i) => {
      const isLast = i === crumbs.length - 1;
      const label = esc(c.name);
      if (isLast) return `<span class="text-zinc-300">${label}</span>`;
      return `<button type="button" class="text-sky-400 hover:underline" data-rfi-crumb="${c.id ?? ''}">${label}</button><span class="text-zinc-600">/</span>`;
    }).join('');
    el.querySelectorAll('[data-rfi-crumb]').forEach(btn => {
      btn.addEventListener('click', () => {
        const raw = btn.dataset.rfiCrumb;
        loadDocPickerBrowse(raw === '' ? null : parseInt(raw, 10));
      });
    });
  }

  function renderDocPickerBody() {
    const body = document.getElementById('rfiDocPickerBody');
    if (!body) return;
    const folders = state.docPickerFolders || [];
    const files = state.docPickerFiles || [];
    if (!folders.length && !files.length) {
      body.innerHTML = '<div class="p-6 text-center text-zinc-500 text-sm">No folders or files here.</div>';
      return;
    }
    const folderRows = folders.map(f => `
      <button type="button" class="rfi-doc-picker-row w-full flex items-center gap-3 px-4 py-2.5 text-left border-b border-zinc-800/80" data-rfi-folder="${f.id}">
        <i class="fa-solid fa-folder text-amber-400"></i>
        <span class="flex-1 truncate text-sm">${esc(f.name)}</span>
        <span class="text-xs text-zinc-500">${f.file_count || 0} files</span>
        <i class="fa-solid fa-chevron-right text-zinc-600 text-xs"></i>
      </button>`).join('');
    const fileRows = files.map(f => {
      const checked = state.docPickerSelected.has(f.id) ? 'checked' : '';
      return `<label class="rfi-doc-picker-row flex items-center gap-3 px-4 py-2.5 border-b border-zinc-800/80 cursor-pointer">
        <input type="checkbox" class="rounded border-zinc-600 bg-zinc-800" data-rfi-doc-id="${f.id}" ${checked}>
        <i class="fa-solid fa-file text-zinc-400"></i>
        <span class="flex-1 truncate text-sm">${esc(f.name)}</span>
        <span class="text-xs text-zinc-500">${fmtFileSize(f.file_size)}</span>
      </label>`;
    }).join('');
    body.innerHTML = folderRows + fileRows;
    body.querySelectorAll('[data-rfi-folder]').forEach(btn => {
      btn.addEventListener('click', () => loadDocPickerBrowse(parseInt(btn.dataset.rfiFolder, 10)));
    });
    body.querySelectorAll('[data-rfi-doc-id]').forEach(cb => {
      cb.addEventListener('change', () => {
        const id = parseInt(cb.dataset.rfiDocId, 10);
        if (cb.checked) state.docPickerSelected.add(id);
        else state.docPickerSelected.delete(id);
        updateDocPickerSelectionUi();
      });
    });
  }

  async function loadDocPickerBrowse(folderId) {
    const pid = projectId();
    if (!pid) return;
    state.docPickerFolderId = folderId;
    const body = document.getElementById('rfiDocPickerBody');
    if (body) body.innerHTML = '<div class="p-6 text-center text-zinc-500 text-sm">Loading…</div>';
    const q = folderId != null ? `&folder_id=${folderId}` : '';
    try {
      const json = await api(`/api/documents/browse?project_id=${pid}${q}`);
      state.docPickerFolders = json.folders || [];
      state.docPickerFiles = json.files || [];
      state.docPickerBreadcrumbs = json.breadcrumbs || [];
      renderDocPickerBreadcrumbs();
      renderDocPickerBody();
    } catch (e) {
      if (body) body.innerHTML = `<div class="p-6 text-center text-red-400 text-sm">${esc(e.message)}</div>`;
    }
  }

  async function searchDocPicker(query) {
    const pid = projectId();
    if (!pid) return;
    const body = document.getElementById('rfiDocPickerBody');
    if (body) body.innerHTML = '<div class="p-6 text-center text-zinc-500 text-sm">Searching…</div>';
    try {
      const json = await api(`/api/documents/search?project_id=${pid}&q=${encodeURIComponent(query)}`);
      state.docPickerFolders = json.folders || [];
      state.docPickerFiles = json.files || [];
      state.docPickerBreadcrumbs = [{ id: null, name: `Search: ${query}` }];
      renderDocPickerBreadcrumbs();
      renderDocPickerBody();
    } catch (e) {
      if (body) body.innerHTML = `<div class="p-6 text-center text-red-400 text-sm">${esc(e.message)}</div>`;
    }
  }

  async function openDocumentPicker() {
    const dlg = document.getElementById('rfiDocumentPicker');
    if (!dlg) return;
    state.docPickerSelected = new Set();
    state.docPickerFolderId = null;
    document.getElementById('rfiDocPickerSearch').value = '';
    updateDocPickerSelectionUi();
    dlg.showModal();
    await loadDocPickerBrowse(null);
  }

  function closeDocumentPicker() {
    document.getElementById('rfiDocumentPicker')?.close();
  }

  async function confirmDocPickerAttach() {
    const selectedIds = [...state.docPickerSelected];
    if (!selectedIds.length) return;
    const selectedDocs = (state.docPickerFiles || []).filter(f => selectedIds.includes(f.id));
    closeDocumentPicker();
    if (state.modalRfiId) {
      try {
        await linkDocumentsToRfi(state.modalRfiId, selectedIds);
        renderModalAttachments();
        toast('Document(s) attached');
        if (state.drawerRecord?.id === state.modalRfiId) await view(state.modalRfiId);
      } catch (e) { alert(e.message); }
      return;
    }
    selectedIds.forEach(id => {
      const doc = selectedDocs.find(d => d.id === id) || { id, name: `Document #${id}` };
      if (!state.pendingDocLinks.some(d => d.id === id)) state.pendingDocLinks.push({ id: doc.id, name: doc.name });
    });
    renderModalAttachments();
  }

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function userName() {
    if (global.CASEPM_PORTAL && global.CASEPM_PORTAL.userName) return global.CASEPM_PORTAL.userName;
    return 'User';
  }

  function userRole() {
    return (global.CASEPM_PORTAL && global.CASEPM_PORTAL.role) || 'Admin';
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString();
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || json.message || 'Request failed');
    return json;
  }

  function loadCompanies() {
    try { state.companies = JSON.parse(localStorage.getItem('casepm_companies') || '[]'); } catch { state.companies = []; }
    try { state.users = JSON.parse(localStorage.getItem('casepm_users') || localStorage.getItem('users') || '[]'); } catch { state.users = []; }
  }

  async function loadDashboard() {
    const pid = projectId();
    if (!pid) return;
    state.stats = await api(`/api/rfis/dashboard?project_id=${pid}`);
    renderSummary();
  }

  async function loadRfis() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/rfis?project_id=${pid}`);
    state.rfis = json.rfis || [];
    renderTable();
  }

  async function loadLinkOptions() {
    const pid = projectId();
    if (!pid) return;
    try {
      state.linkOptions = await api(`/api/rfis/link-options?project_id=${pid}`);
    } catch { state.linkOptions = { change_orders: [], pcos: [] }; }
  }

  function renderSummary() {
    const s = state.stats;
    const map = {
      statRfiTotal: s.total || 0,
      statRfiOpen: s.open || 0,
      statRfiAwaiting: s.awaiting_response || 0,
      statRfiAnswered: s.answered || 0,
      statRfiOverdue: s.overdue || 0,
      statRfiClosed: s.closed || 0,
      statRfiCostImpact: s.with_cost_impact || 0,
      statRfiSchedImpact: s.with_schedule_impact || 0,
    };
    Object.keys(map).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
  }

  function filteredRfis() {
    const { search, status, priority } = state.filter;
    return state.rfis.filter(r => {
      const text = `${r.number} ${r.subject} ${r.question || ''} ${r.received_from_company || ''} ${r.drawing_reference || ''}`.toLowerCase();
      if (search && !text.includes(search.toLowerCase())) return false;
      if (status && r.status !== status) return false;
      if (priority && r.priority !== priority) return false;
      return true;
    });
  }

  function statusBadge(status) {
    const colors = {
      Draft: 'bg-zinc-700 text-zinc-300',
      Open: 'bg-sky-900/60 text-sky-300',
      'Under Review': 'bg-amber-900/60 text-amber-300',
      'Awaiting Response': 'bg-orange-900/60 text-orange-300',
      Answered: 'bg-emerald-900/60 text-emerald-300',
      Closed: 'bg-zinc-800 text-zinc-400',
      Void: 'bg-red-950/60 text-red-400',
    };
    return `<span class="px-2 py-0.5 rounded-full text-[10px] font-medium ${colors[status] || 'bg-zinc-700 text-zinc-300'}">${esc(status)}</span>`;
  }

  function priorityBadge(p) {
    const colors = { Critical: 'text-red-400', High: 'text-orange-400', Medium: 'text-amber-300', Low: 'text-zinc-400' };
    return `<span class="text-xs font-medium ${colors[p] || 'text-zinc-400'}">${esc(p || '—')}</span>`;
  }

  function ballBadge(role) {
    if (!role) return '<span class="text-zinc-500">—</span>';
    return `<span class="px-2 py-0.5 rounded text-[10px] bg-violet-900/50 text-violet-300">${esc(role)}</span>`;
  }

  function renderTable() {
    const tbody = document.getElementById('rfiTableBody');
    if (!tbody) return;
    const rows = filteredRfis();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="12" class="px-6 py-12 text-center text-zinc-500">No RFIs found. Create your first RFI.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const attCount = attachmentCount(r);
      const attCell = attCount
        ? `<span class="inline-flex items-center gap-1 text-emerald-400" title="${attCount} attachment(s)"><i class="fa-solid fa-paperclip"></i>${attCount}</span>`
        : '<span class="text-zinc-600">—</span>';
      return `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer ${r.is_overdue ? 'bg-red-950/10' : ''}" onclick="CasePMRfis.view(${r.id})">
        <td class="px-4 py-3 font-mono text-sky-400 whitespace-nowrap">${esc(r.number)}</td>
        <td class="px-4 py-3 max-w-[280px]">
          <div class="font-medium truncate">${esc(r.subject)}</div>
          <div class="text-[10px] text-zinc-500 truncate">${esc(r.question || '')}</div>
        </td>
        <td class="px-4 py-3 text-xs text-zinc-400">${esc(r.received_from_company || r.from_party || '—')}</td>
        <td class="px-4 py-3 text-xs text-zinc-400">${esc(r.to_party || r.assignees?.[0] || '—')}</td>
        <td class="px-4 py-3 text-xs font-mono">${esc(r.drawing_reference || '—')}</td>
        <td class="px-4 py-3 text-xs font-mono">${esc(r.spec_reference || '—')}</td>
        <td class="px-4 py-3 text-center">${priorityBadge(r.priority)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(r.status)}</td>
        <td class="px-4 py-3 text-center">${ballBadge(r.ball_in_court_role)}</td>
        <td class="px-4 py-3 text-center text-xs whitespace-nowrap ${r.is_overdue ? 'text-red-400 font-semibold' : 'text-zinc-400'}">${fmtDate(r.due_date)}</td>
        <td class="px-4 py-3 text-center text-xs">${attCell}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-1">
            <button onclick="CasePMRfis.printDetail(${r.id})" class="p-1.5 text-zinc-300 hover:bg-zinc-800 rounded" title="Print RFI"><i class="fa-solid fa-print"></i></button>
            <button onclick="CasePMRfis.openResponder(${r.id})" class="p-1.5 text-emerald-400 hover:bg-zinc-800 rounded" title="${canEnterRfis() ? 'Review &amp; Respond' : 'View'}"><i class="fa-solid fa-${canEnterRfis() ? 'reply' : 'eye'}"></i></button>
            ${canEditRfis() && isStaffPortal() ? `<button onclick="CasePMRfis.edit(${r.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded" title="Edit"><i class="fa-solid fa-edit"></i></button>` : ''}
            ${canDeleteRfi() ? `<button onclick="CasePMRfis.deleteRfi(${r.id})" class="p-1.5 text-red-400 hover:bg-zinc-800 rounded" title="Delete RFI"><i class="fa-solid fa-trash"></i></button>` : ''}
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  function bindFilters() {
    ['rfiSearch', 'rfiStatusFilter', 'rfiPriorityFilter'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const evt = el.tagName === 'INPUT' ? 'input' : 'change';
      el.addEventListener(evt, () => {
        state.filter.search = document.getElementById('rfiSearch')?.value || '';
        state.filter.status = document.getElementById('rfiStatusFilter')?.value || '';
        state.filter.priority = document.getElementById('rfiPriorityFilter')?.value || '';
        renderTable();
      });
    });
  }

  function populateCompanySelects() {
    const sel = document.getElementById('modalRfiCompany');
    if (!sel) return;
    sel.innerHTML = '<option value="">— Select Company —</option>' +
      state.companies.map(c => {
        const name = c.company_name || c.name || '';
        return `<option value="${esc(name)}">${esc(name)}</option>`;
      }).join('');
  }

  function openModal(mode, record) {
    state.modalMode = mode;
    state.drawerRecord = record || null;
    const dlg = document.getElementById('rfiModal');
    if (!dlg) return;
    document.getElementById('rfiModalTitle').textContent = mode === 'create' ? 'New RFI' : `Edit ${record?.number || 'RFI'}`;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
    const setCheck = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    if (mode === 'create') {
      set('modalRfiSubject', '');
      set('modalRfiQuestion', '');
      set('modalRfiPriority', 'Medium');
      set('modalRfiStatus', 'Draft');
      set('modalRfiDueDate', '');
      set('modalRfiDrawing', '');
      set('modalRfiSpec', '');
      set('modalRfiFrom', userName());
      set('modalRfiTo', 'Architect');
      set('modalRfiManager', userName());
      set('modalRfiAssignees', '');
      set('modalRfiDistribution', '');
      set('modalRfiNotes', '');
      set('modalRfiLocation', '');
      set('modalRfiDiscipline', '');
      set('modalRfiCostImpact', '');
      set('modalRfiSchedDays', '0');
      setCheck('modalRfiPrivate', false);
      document.getElementById('modalRfiNumber').textContent = 'Auto';
    } else if (record) {
      set('modalRfiSubject', record.subject);
      set('modalRfiQuestion', record.question);
      set('modalRfiPriority', record.priority);
      set('modalRfiStatus', record.status);
      set('modalRfiDueDate', record.due_date ? record.due_date.slice(0, 10) : '');
      set('modalRfiDrawing', record.drawing_reference);
      set('modalRfiSpec', record.spec_reference);
      set('modalRfiFrom', record.from_party);
      set('modalRfiTo', record.to_party);
      set('modalRfiCompany', record.received_from_company);
      set('modalRfiContact', record.received_from_contact);
      set('modalRfiContractor', record.responsible_contractor);
      set('modalRfiManager', record.rfi_manager_name);
      set('modalRfiAssignees', (record.assignees || []).join(', '));
      set('modalRfiDistribution', (record.distribution || []).join(', '));
      set('modalRfiNotes', record.notes);
      set('modalRfiLocation', record.location_description);
      set('modalRfiDiscipline', record.discipline);
      set('modalRfiCostImpact', record.cost_impact_amount || '');
      set('modalRfiSchedDays', record.schedule_impact_days || 0);
      setCheck('modalRfiPrivate', record.is_private);
      document.getElementById('modalRfiNumber').textContent = record.number;
    }
    populateCompanySelects();
    const details = document.getElementById('rfiDetailsSection');
    if (details) details.open = mode !== 'create';
    if (mode === 'create') {
      resetModalAttachments();
    } else if (record?.id) {
      state.modalRfiId = record.id;
      state.modalAttachments = (record.attachments || []).map(a => ({ ...a }));
      state.pendingFiles = [];
      state.pendingDocLinks = [];
      renderModalAttachments();
      loadModalAttachments(record.id);
    } else {
      resetModalAttachments();
    }
    dlg.showModal();
    if (mode === 'create') {
      requestAnimationFrame(() => scrollToAttachments());
    }
  }

  async function focusAttachments(id) {
    if (id) await edit(id);
    else scrollToAttachments();
    setTimeout(scrollToAttachments, 200);
  }

  function modalPayload() {
    const assignees = (document.getElementById('modalRfiAssignees')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
    const distribution = (document.getElementById('modalRfiDistribution')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
    return {
      subject: document.getElementById('modalRfiSubject')?.value?.trim(),
      question: document.getElementById('modalRfiQuestion')?.value?.trim(),
      priority: document.getElementById('modalRfiPriority')?.value,
      due_date: document.getElementById('modalRfiDueDate')?.value || null,
      drawing_reference: document.getElementById('modalRfiDrawing')?.value?.trim(),
      spec_reference: document.getElementById('modalRfiSpec')?.value?.trim(),
      from_party: document.getElementById('modalRfiFrom')?.value?.trim(),
      to_party: document.getElementById('modalRfiTo')?.value,
      received_from_company: document.getElementById('modalRfiCompany')?.value,
      received_from_contact: document.getElementById('modalRfiContact')?.value?.trim(),
      responsible_contractor: document.getElementById('modalRfiContractor')?.value?.trim(),
      rfi_manager_name: document.getElementById('modalRfiManager')?.value?.trim(),
      assignees,
      distribution,
      notes: document.getElementById('modalRfiNotes')?.value?.trim(),
      location_description: document.getElementById('modalRfiLocation')?.value?.trim(),
      discipline: document.getElementById('modalRfiDiscipline')?.value,
      cost_impact_amount: parseFloat(document.getElementById('modalRfiCostImpact')?.value) || 0,
      schedule_impact_days: parseInt(document.getElementById('modalRfiSchedDays')?.value, 10) || 0,
      is_private: document.getElementById('modalRfiPrivate')?.checked,
    };
  }

  async function saveModal(createAsOpen) {
    const payload = modalPayload();
    if (!payload.subject) { alert('Subject is required.'); return; }
    try {
      let rfiId = state.modalRfiId;
      if (state.modalMode === 'create') {
        payload.project_id = projectId();
        if (createAsOpen) payload.create_as_open = true;
        const json = await api('/api/rfis', { method: 'POST', body: JSON.stringify(payload) });
        rfiId = json.rfi?.id;
        if (rfiId) await flushPendingAttachments(rfiId);
        toast('RFI created');
      } else if (state.drawerRecord) {
        rfiId = state.drawerRecord.id;
        await api(`/api/rfis/${rfiId}`, { method: 'PUT', body: JSON.stringify(payload) });
        if (state.pendingFiles.length || state.pendingDocLinks.length) {
          await flushPendingAttachments(rfiId);
        }
        toast('RFI updated');
      }
      document.getElementById('rfiModal')?.close();
      await Promise.all([loadRfis(), loadDashboard()]);
    } catch (e) { alert(e.message); }
  }

  async function view(id) {
    try {
      const r = await api(`/api/rfis/${id}`);
      state.drawerRecord = r;
      const actionable = r.status && !['Closed', 'Void', 'Draft'].includes(r.status);
      if (actionable && typeof global.CasePMApprovalResponder !== 'undefined') {
        await openResponder(id);
        return;
      }
      renderDrawer(r);
      document.getElementById('rfiDetailDrawer')?.classList.add('open');
      document.getElementById('rfiDrawerBackdrop')?.classList.remove('hidden');
    } catch (e) { alert(e.message); }
  }

  function closeDrawer() {
    document.getElementById('rfiDetailDrawer')?.classList.remove('open');
    document.getElementById('rfiDrawerBackdrop')?.classList.add('hidden');
    state.drawerRecord = null;
  }

  function drawingPinHref(pin, rfiId) {
    const pid = projectId();
    const q = new URLSearchParams();
    if (pid) q.set('project_id', pid);
    if (pin.drawing_id) q.set('drawing_id', pin.drawing_id);
    else if (pin.drawing_sheet) q.set('sheet', pin.drawing_sheet);
    const nx = pin.nx != null ? pin.nx : (pin.x <= 1 && pin.x >= 0 ? pin.x : null);
    const ny = pin.ny != null ? pin.ny : (pin.y <= 1 && pin.y >= 0 ? pin.y : null);
    if (nx != null) q.set('x', nx);
    if (ny != null) q.set('y', ny);
    if (rfiId) q.set('rfi_id', rfiId);
    return `/drawings?${q.toString()}`;
  }

  function renderDrawer(r) {
    const el = document.getElementById('rfiDrawerContent');
    if (!el) return;
    const responses = (r.responses || []).map(resp => `
      <div class="border border-zinc-700 rounded-md p-3 ${resp.is_official ? 'border-emerald-700 bg-emerald-950/20' : ''}">
        <div class="flex justify-between text-xs text-zinc-500 mb-1">
          <span>${esc(resp.user_name)} ${resp.is_official ? '<span class="text-emerald-400 ml-1">Official Answer</span>' : ''}</span>
          <span>${fmtDate(resp.created_at)}</span>
        </div>
        <div class="text-sm whitespace-pre-wrap">${esc(resp.body)}</div>
      </div>`).join('') || '<p class="text-zinc-500 text-sm">No responses yet.</p>';

    const pins = (r.plan_pins || []).map((p, i) => `
      <div class="text-xs bg-zinc-800 rounded px-2 py-1 flex justify-between">
        <a href="${drawingPinHref(p, r.id)}" class="hover:text-sky-300"><i class="fa-solid fa-map-pin text-sky-400 mr-1"></i>${esc(p.drawing_sheet || r.drawing_reference || 'Sheet')}${p.nx != null ? '' : ` @ (${p.x || 0}, ${p.y || 0})`}</a>
        <button onclick="CasePMRfis.removePin(${r.id}, ${i})" class="text-red-400"><i class="fa-solid fa-times"></i></button>
      </div>`).join('') || '<p class="text-zinc-500 text-xs">No plan pins yet. Open <a href="/drawings" class="text-sky-400 underline">Drawings</a> to place RFI pins on sheets.</p>';

    const linked = [
      ...(r.linked_change_orders || []).map(c => `<a href="/change-orders" class="text-emerald-400 text-xs">${esc(c.number)} — ${esc(c.title)}</a>`),
      ...(r.linked_pcos || []).map(p => `<a href="/change-orders" class="text-sky-400 text-xs">${esc(p.number)} — ${esc(p.title)}</a>`),
    ].join('<br>') || '<span class="text-zinc-500 text-xs">No linked COs/PCOs</span>';

    const attList = (r.attachments || []).map(att => {
      const name = esc(att.original_name || att.filename || 'File');
      const href = esc(attachmentHref(att, r.id));
      const icon = att.document_id || att.linked_from_documents ? 'fa-file-lines text-sky-400' : 'fa-paperclip text-zinc-400';
      return `<a href="${href}" target="_blank" rel="noopener" class="flex items-center gap-2 text-xs bg-zinc-800 rounded px-2 py-1.5 hover:bg-zinc-700 border border-zinc-700">
        <i class="fa-solid ${icon}"></i><span class="truncate">${name}</span>
      </a>`;
    }).join('');

    el.innerHTML = `
      <div class="flex items-start justify-between mb-4 gap-3">
        <div class="min-w-0">
          <div class="font-mono text-sky-400 text-lg">${esc(r.number)}</div>
          <h2 class="text-xl font-semibold mt-1">${esc(r.subject)}</h2>
          <div class="flex flex-wrap gap-2 mt-2">${statusBadge(r.status)} ${priorityBadge(r.priority)} ${ballBadge(r.ball_in_court_role)}</div>
        </div>
        <div class="flex items-center gap-2 flex-shrink-0">
          <button type="button" onclick="CasePMRfis.printDetail(${r.id})" class="px-3 py-1.5 text-xs bg-white text-zinc-900 hover:bg-zinc-100 rounded-md font-semibold border border-zinc-300"><i class="fa-solid fa-print mr-1"></i>Print</button>
          <button onclick="CasePMRfis.closeDrawer()" class="text-zinc-400 hover:text-white text-xl leading-none">&times;</button>
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-4">
        <div><span class="text-zinc-500">Due</span><div class="${r.is_overdue ? 'text-red-400' : ''}">${fmtDate(r.due_date)}</div></div>
        <div><span class="text-zinc-500">Drawing</span><div class="font-mono">${esc(r.drawing_reference || '—')}</div></div>
        <div><span class="text-zinc-500">Spec</span><div class="font-mono">${esc(r.spec_reference || '—')}</div></div>
        <div><span class="text-zinc-500">Discipline</span><div>${esc(r.discipline || '—')}</div></div>
        <div><span class="text-zinc-500">From</span><div>${esc(r.received_from_company || r.from_party || '—')}</div></div>
        <div><span class="text-zinc-500">To / Assignee</span><div>${esc((r.assignees || []).join(', ') || r.to_party || '—')}</div></div>
        <div><span class="text-zinc-500">RFI Manager</span><div>${esc(r.rfi_manager_name || '—')}</div></div>
        <div><span class="text-zinc-500">Cost Impact</span><div>${r.cost_impact_amount ? '$' + Number(r.cost_impact_amount).toLocaleString() : '—'}</div></div>
      </div>
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-1">Question</h3>
        <p class="text-sm whitespace-pre-wrap bg-zinc-800/50 rounded-md p-3 border border-zinc-700">${esc(r.question || '—')}</p>
      </div>
      <div class="mb-4 rfi-attachments-card">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs uppercase text-emerald-400 font-semibold tracking-wide"><i class="fa-solid fa-paperclip mr-1"></i>Attachments</h3>
          <span class="text-[10px] text-zinc-500">${(r.attachments || []).length} file(s)</span>
        </div>
        <div id="rfiDrawerDropZone" class="border-2 border-dashed border-emerald-700/40 hover:border-emerald-500 rounded-lg p-3 text-center cursor-pointer bg-zinc-950/50 mb-2 transition-all">
          <div class="text-xs text-zinc-400"><i class="fa-solid fa-cloud-arrow-up text-emerald-500 mr-1"></i>Drop files here or click to upload</div>
          ${isStaffPortal() ? '<button type="button" data-drawer-docs class="mt-2 text-xs px-2 py-1 rounded bg-sky-900/50 text-sky-200 border border-sky-700/50 hover:bg-sky-800/60">Browse Documents</button>' : ''}
        </div>
        <div class="space-y-1">${attList || '<p class="text-zinc-500 text-xs px-1">No files attached yet</p>'}</div>
      </div>
      ${r.official_answer ? `<div class="mb-4"><h3 class="text-xs uppercase text-emerald-500 mb-1">Official Answer</h3><p class="text-sm whitespace-pre-wrap bg-emerald-950/20 rounded-md p-3 border border-emerald-800">${esc(r.official_answer)}</p></div>` : ''}
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-2">Responses</h3>
        <div class="space-y-2 max-h-48 overflow-auto">${responses}</div>
      </div>
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-2">Plan Pins</h3>
        <div class="space-y-1 mb-2">${pins}</div>
        <button type="button" onclick="CasePMRfis.addPlanPin(${r.id})" class="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700"><i class="fa-solid fa-map-pin mr-1"></i>Add Plan Pin</button>
      </div>
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-1">Linked Change Orders / PCOs</h3>
        <div class="space-y-1">${linked}</div>
      </div>
      <div class="flex flex-wrap gap-2 pt-3 border-t border-zinc-700">
        <button onclick="CasePMRfis.openResponder(${r.id})" class="px-4 py-2 text-sm bg-emerald-600 hover:bg-emerald-500 rounded-md font-semibold"><i class="fa-solid fa-${canEnterRfis() ? 'reply' : 'eye'} mr-1"></i>${canEnterRfis() ? 'Review &amp; Respond' : 'View'}</button>
        ${canEnterRfis() && isStaffPortal() ? `
        <button onclick="CasePMRfis.workflow(${r.id}, 'submit')" class="px-3 py-1.5 text-xs bg-sky-800 hover:bg-sky-700 rounded-md">Send for Review</button>
        <button onclick="CasePMRfis.workflow(${r.id}, 'close')" class="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md">Close RFI</button>
        <button onclick="CasePMRfis.promotePco(${r.id})" class="px-3 py-1.5 text-xs bg-violet-800 hover:bg-violet-700 rounded-md"><i class="fa-solid fa-lightbulb mr-1"></i>Create PCO</button>` : ''}
        ${canEditRfis() && isStaffPortal() ? `<button onclick="CasePMRfis.edit(${r.id})" class="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md"><i class="fa-solid fa-edit mr-1"></i>Edit</button>` : ''}
        ${canDeleteRfi() ? `<button onclick="CasePMRfis.deleteRfi(${r.id})" class="px-3 py-1.5 text-xs bg-red-900/70 hover:bg-red-800 text-red-200 rounded-md"><i class="fa-solid fa-trash mr-1"></i>Delete</button>` : ''}
      </div>`;
    bindDrawerAttachmentHandlers(r.id);
  }

  async function respond(id) {
    await openResponder(id);
  }

  async function workflow(id, action) {
    try {
      await api(`/api/rfis/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action }) });
      toast('Workflow updated');
      await Promise.all([loadRfis(), loadDashboard()]);
      if (state.drawerRecord?.id === id) view(id);
    } catch (e) { alert(e.message); }
  }

  async function promotePco(id) {
    const amount = prompt('Estimated ROM for PCO ($):', '0');
    if (amount === null) return;
    try {
      const json = await api(`/api/rfis/${id}/promote-pco`, { method: 'POST', body: JSON.stringify({ estimated_amount: parseFloat(amount) || 0 }) });
      toast(`PCO ${json.pco?.number || ''} created from RFI`);
      await loadLinkOptions();
      if (state.drawerRecord?.id === id) view(id);
    } catch (e) { alert(e.message); }
  }

  async function deleteRfi(id) {
    const r = state.rfis.find((row) => row.id === id) || state.drawerRecord;
    const label = r ? `${r.number || id}: ${r.subject || ''}` : `RFI #${id}`;
    const ok = typeof CasePMDialog !== 'undefined'
      ? await CasePMDialog.confirm(
        `Permanently delete ${label}?\n\nThis cannot be undone. Linked CO/PCO references will be cleared.`,
        { title: 'Delete RFI', danger: true, confirmText: 'Delete' },
      )
      : confirm(`Permanently delete ${label}?`);
    if (!ok) return;
    try {
      await api(`/api/rfis/${id}`, { method: 'DELETE' });
      toast('RFI deleted', 'success');
      if (state.drawerRecord?.id === id) closeDrawer();
      state.selected = null;
      await Promise.all([loadRfis(), loadDashboard()]);
    } catch (e) {
      alert(e.message || 'Could not delete RFI');
    }
  }

  async function addPlanPin(id) {
    const sheet = state.drawerRecord?.drawing_reference || '';
    const q = new URLSearchParams();
    const pid = projectId();
    if (pid) q.set('project_id', pid);
    if (sheet) q.set('sheet', sheet);
    q.set('rfi_id', id);
    global.location.href = `/drawings?${q.toString()}`;
  }

  async function removePin(id, index) {
    const r = await api(`/api/rfis/${id}`);
    const pins = [...(r.plan_pins || [])];
    const removed = pins[index];
    if (!removed) return;
    if (removed.markup_id) {
      try {
        await api(`/api/drawings/markups/${removed.markup_id}`, { method: 'DELETE' });
      } catch {
        pins.splice(index, 1);
        await api(`/api/rfis/${id}`, { method: 'PUT', body: JSON.stringify({ plan_pins: pins }) });
      }
    } else {
      pins.splice(index, 1);
      await api(`/api/rfis/${id}`, { method: 'PUT', body: JSON.stringify({ plan_pins: pins }) });
    }
    view(id);
  }

  async function edit(id) {
    const r = await api(`/api/rfis/${id}`);
    openModal('edit', r);
  }

  async function exportExcel() {
    if (typeof XLSX === 'undefined') { alert('Excel library not loaded'); return; }
    const rows = filteredRfis().map(r => ({
      Number: r.number, Subject: r.subject, Status: r.status, Priority: r.priority,
      'Ball In Court': r.ball_in_court_role, Due: r.due_date, Drawing: r.drawing_reference,
      Spec: r.spec_reference, Company: r.received_from_company, Question: r.question,
      Answer: r.official_answer, 'Cost Impact': r.cost_impact_amount, 'Sched Days': r.schedule_impact_days,
    }));
    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'RFI Log');
    const filename = `RFI_Log_${projectId() || 'project'}.xlsx`;
    if (global.CasePMOutput) {
      const buf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
      await global.CasePMOutput.deliverBlob({
        title: 'Export RFI Log',
        blob: new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
        mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename,
        filenameBase: `RFI_Log_${projectId() || 'project'}`,
        sourceModule: 'rfis',
        systemFolderKey: 'rfis',
        subfolder: 'Exports',
        fileLabel: 'Excel (.xlsx)',
      });
      return;
    }
    XLSX.writeFile(wb, filename);
  }

  const RFI_BASE_PRINT_COLUMNS = [
    { key: 'number', label: 'RFI #', width: '6%', mono: true, alwaysShow: true },
    { key: 'subject', label: 'Subject', width: '16%', logPhrase: true, logWords: 4, alwaysShow: true },
    { key: 'received_from_company', label: 'From', width: '10%', logPhrase: true, logWords: 3 },
    { key: 'to_party', label: 'To', width: '8%', logPhrase: true, logWords: 3 },
    { key: 'status', label: 'Status', width: '8%', align: 'center', alwaysShow: true },
    { key: 'ball_in_court_role', label: 'Ball<br>in Court', width: '8%', align: 'center' },
    { key: 'due_date', label: 'Due', width: '7%', align: 'center' },
    { key: 'date', label: 'Initiated', width: '7%', align: 'center' },
  ];

  const RFI_REFERENCE_PRINT_COLUMNS = [
    { key: 'drawing_reference', label: 'Drawing', width: '7%', mono: true },
    { key: 'spec_reference', label: 'Spec', width: '7%', mono: true },
  ];

  const RFI_DATE_COLUMN_KEYS = ['due_date', 'date'];

  const RFI_CONTENT_OPTIONS = [
    { key: 'dates', label: 'Include date columns', default: true },
    { key: 'drawing', label: 'Include drawing reference', default: true },
    { key: 'spec', label: 'Include spec reference', default: true },
    { key: 'location', label: 'Show location in header', default: false },
    { key: 'printedDate', label: 'Show printed date in footer', default: true },
  ];

  const RFI_OPTIONAL_PRINT_FIELDS = [
    { key: 'question', label: 'Question (short)', default: false },
    { key: 'official_answer', label: 'Official Answer (short)', default: false },
    { key: 'priority', label: 'Priority', default: false },
    { key: 'from_party', label: 'From Party', default: false },
    { key: 'responsible_contractor', label: 'Responsible Contractor', default: false },
    { key: 'rfi_manager_name', label: 'RFI Manager', default: false },
    { key: 'discipline', label: 'Discipline', default: false },
    { key: 'location_description', label: 'Location', default: false },
    { key: 'cost_impact_amount', label: 'Cost Impact', default: false },
    { key: 'schedule_impact_days', label: 'Schedule Days', default: false },
    { key: 'notes', label: 'Notes', default: false },
  ];

  const RFI_DETAIL_PRINT_OPTIONS = [
    { key: 'dates', label: 'Include dates', default: true },
    { key: 'drawing', label: 'Include drawing reference', default: true },
    { key: 'spec', label: 'Include spec reference', default: true },
    { key: 'discipline', label: 'Include discipline', default: false },
    { key: 'impacts', label: 'Include cost & schedule impact', default: true },
    { key: 'responses', label: 'Include responses', default: true },
    { key: 'attachments', label: 'Include attachments', default: true },
    { key: 'linked', label: 'Include linked COs / PCOs', default: true },
    { key: 'location', label: 'Show location in header', default: false },
    { key: 'printedDate', label: 'Show printed date in footer', default: true },
  ];

  function resolveRfiPrintColumns(selectedOptionalKeys, contentOptions) {
    const opts = contentOptions || {};
    let columns = [...RFI_BASE_PRINT_COLUMNS];
    if (opts.drawing !== false) columns.splice(2, 0, RFI_REFERENCE_PRINT_COLUMNS[0]);
    if (opts.spec !== false) {
      const insertAt = columns.findIndex(c => c.key === 'received_from_company');
      columns.splice(insertAt >= 0 ? insertAt : 2, 0, RFI_REFERENCE_PRINT_COLUMNS[1]);
    }
    if (opts.dates === false) {
      columns = columns.filter(c => !RFI_DATE_COLUMN_KEYS.includes(c.key));
    }
    const optional = RFI_OPTIONAL_PRINT_FIELDS
      .filter(f => (selectedOptionalKeys || []).includes(f.key))
      .map(f => ({
        key: f.key,
        label: f.label.replace(/ /g, '<br>'),
        width: '7%',
        logPhrase: ['question', 'official_answer', 'notes'].includes(f.key),
        logWords: 4,
      }));
    return [...columns, ...optional];
  }

  function hasPrintValue(value) {
    const P = global.CasePMPrint;
    if (P && P.isEmptyPrintCell) return !P.isEmptyPrintCell(value);
    const text = value == null ? '' : String(value).replace(/\s+/g, ' ').trim();
    return !!text && text !== '—' && text !== '-';
  }

  function printValue(r, key) {
    if (key === 'due_date' || key === 'date') return fmtDate(r[key]);
    if (key === 'cost_impact_amount') return r.cost_impact_amount ? '$' + Number(r.cost_impact_amount).toLocaleString() : '';
    if (key === 'question' || key === 'official_answer' || key === 'notes') {
      const P = global.CasePMPrint;
      return P && P.logPhrase ? P.logPhrase(r[key], 4) : (r[key] ?? '');
    }
    if (key === 'subject' || key === 'received_from_company' || key === 'to_party') {
      const P = global.CasePMPrint;
      return P && P.logPhrase ? P.logPhrase(r[key], 4) : (r[key] ?? '');
    }
    return r[key] ?? '';
  }

  function getRfiPrintMeta() {
    if (global.CasePMPrint && global.CasePMPrint.getProjectMeta) {
      return global.CasePMPrint.getProjectMeta();
    }
    const nameEl = document.getElementById('currentProjectName');
    return {
      name: (nameEl?.textContent || '').trim() || 'Project',
      number: projectId() || '',
      location: '',
    };
  }

  async function triggerRfiPrint(html, options) {
    const opts = options || {};
    if (global.CasePMOutput) {
      await global.CasePMOutput.deliverHtml({
        title: opts.title || 'RFI',
        html,
        filenameBase: opts.filenameBase || `RFI_${projectId() || 'project'}`,
        sourceModule: 'rfis',
        systemFolderKey: 'rfis',
        subfolder: opts.subfolder || 'Exports',
        printOptions: {
          bodyHtml: html,
          containerId: 'rfiPrintSheet',
          bodyClass: opts.bodyClass || 'printing-rfi-log',
          portrait: !!opts.portrait,
          docTitle: opts.docTitle,
          title: opts.title,
        },
      });
      return;
    }
    if (opts.portrait && global.CasePMPrint.printPortraitDocument) {
      global.CasePMPrint.printPortraitDocument(html, opts.docTitle || 'RFI');
      return;
    }
    global.CasePMPrint.triggerPrintPreview(html, {
      containerId: 'rfiPrintSheet',
      bodyClass: opts.bodyClass || 'printing-rfi-log',
    });
  }

  function buildRfiDetailPrintHtml(r, printOpts) {
    const opts = printOpts || {};
    const meta = getRfiPrintMeta();
    const P = global.CasePMPrint;
    const e = P ? P.esc : esc;
    const writableField = (label, value) => {
      if (P && P.buildWritableField) return P.buildWritableField(label, value);
      if (!hasPrintValue(value)) return '';
      return `<div><span class="label">${e(label)}</span>${e(value)}</div>`;
    };

    const metaFields = [];
    metaFields.push(writableField('Due Date', fmtDate(r.due_date)));
    metaFields.push(writableField('Initiated', fmtDate(r.date)));
    metaFields.push(writableField('Drawing', r.drawing_reference));
    metaFields.push(writableField('Spec', r.spec_reference));
    metaFields.push(writableField('Discipline', r.discipline));
    metaFields.push(writableField('From', r.received_from_company || r.from_party));
    metaFields.push(writableField('To / Assignee', (r.assignees || []).join(', ') || r.to_party));
    metaFields.push(writableField('Cost Impact', r.cost_impact_amount ? '$' + Number(r.cost_impact_amount).toLocaleString() : ''));
    metaFields.push(writableField('Schedule Impact', r.schedule_impact_days ? `${r.schedule_impact_days} days` : ''));

    const attachmentNames = (r.attachments || []).map(att => att.original_name || att.filename || 'File');
    const linkedItems = [
      ...(r.linked_change_orders || []).map(c => `CO ${c.number}`),
      ...(r.linked_pcos || []).map(p => `PCO ${p.number}`),
    ];

    const headerOpts = { showLocation: opts.location !== false };
    const statusBadge = hasPrintValue(r.status)
      ? `<span class="rfi-detail-status">${e(r.status)}</span>`
      : '';

    const questionBlock = P && P.buildWritableBox
      ? P.buildWritableBox('Question', r.question || '', { minHeight: 36 })
      : `<div class="rfi-detail-box"><h4>Question</h4>${e(r.question || '—')}</div>`;
    const answerBlock = P && P.buildWritableBox
      ? P.buildWritableBox('Official Answer / Response', r.official_answer || '', { minHeight: 36 })
      : `<div class="rfi-detail-box"><h4>Official Answer / Response</h4><div class="write-area" style="min-height:36px;border:1px dashed #bbb;background:#fafafa"></div></div>`;

    const sigBlocks = P && P.buildManualSigBlock
      ? `<div class="casepm-manual-sigs">
          ${P.buildManualSigBlock('Requested By', { compact: true })}
          ${P.buildManualSigBlock('Responded By (Architect / Engineer)', { compact: true })}
        </div>`
      : '';

    const inlineExtras = [
      attachmentNames.length ? `<div class="rfi-signoff-inline"><strong>Attachments:</strong> ${e(attachmentNames.join(', '))}</div>` : '',
      linkedItems.length ? `<div class="rfi-signoff-inline"><strong>Linked:</strong> ${e(linkedItems.join(', '))}</div>` : '',
    ].filter(Boolean).join('');

    return `<div class="casepm-print-page casepm-rfi-signoff-onepage">
      ${global.CasePMPrint.buildPrintHeaderHtml(meta, 'REQUEST FOR INFORMATION', headerOpts)}
      <div class="casepm-rfi-detail">
        <div class="rfi-detail-identifier">
          <span class="rfi-detail-number">${e(r.number)}</span>
          ${statusBadge}
        </div>
        <div class="rfi-detail-subject">${e(r.subject || '')}</div>
        <div class="rfi-detail-grid">${metaFields.filter(Boolean).join('')}</div>
        ${questionBlock}
        ${answerBlock}
        ${inlineExtras}
        ${sigBlocks ? `<div class="co-doc-sigs"><h3>Authorization &amp; Sign-off</h3><p>Print, complete by hand, and return signed.</p>${sigBlocks}</div>` : ''}
      </div>
      <div class="casepm-print-footer">
        <span>Confidential</span>
        <span class="center">${opts.printedDate !== false ? '__PRINTED_ON__' : ''}</span>
        <span class="right"></span>
      </div>
    </div>`;
  }

  async function printDetail(id) {
    if (typeof global.CasePMPrint === 'undefined') { alert('Print module not loaded'); return; }
    let r = state.drawerRecord;
    const targetId = id || r?.id;
    if (!targetId) return;
    if (!r || r.id !== targetId) {
      try {
        r = await api(`/api/rfis/${targetId}`);
      } catch (e) {
        alert(e.message);
        return;
      }
    }
    const printOpts = {
      dates: true,
      drawing: true,
      spec: true,
      discipline: true,
      impacts: true,
      attachments: true,
      linked: true,
      location: false,
      printedDate: true,
    };
    const html = buildRfiDetailPrintHtml(r, printOpts);
    await triggerRfiPrint(html, {
      title: `RFI ${r.number}`,
      filenameBase: `RFI_${r.number || r.id}`,
      subfolder: 'Printed',
      portrait: true,
      docTitle: `RFI ${r.number}`,
      bodyClass: 'printing-rfi-detail',
    });
  }

  async function printLog() {
    if (typeof global.CasePMPrint === 'undefined') { alert('Print module not loaded'); return; }
    const picked = await global.CasePMPrint.showFieldPicker({
      title: 'Print RFI Log',
      note: 'Standard RFI register columns are always included. Drawing, spec, and date columns can be toggled above. Empty columns are omitted automatically.',
      contentOptions: RFI_CONTENT_OPTIONS,
      fields: RFI_OPTIONAL_PRINT_FIELDS,
    });
    if (!picked) return;
    const columns = resolveRfiPrintColumns(picked.fields, picked.contentOptions);
    const rows = filteredRfis().map(r => {
      const obj = {};
      columns.forEach(c => { obj[c.key] = printValue(r, c.key); });
      return obj;
    });
    const meta = getRfiPrintMeta();
    const html = global.CasePMPrint.buildPrintDocument({
      meta,
      sections: [{ title: 'RFI LOG', columns, rows, emptyMessage: 'No RFIs to print.' }],
      flowing: true,
      printOptions: {
        showLocation: picked.contentOptions?.location !== false,
        showPrintedDate: picked.contentOptions?.printedDate !== false,
      },
    });
    await triggerRfiPrint(html, {
      title: 'RFI Log',
      filenameBase: `RFI_Log_${projectId() || 'project'}`,
    });
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-16 right-6 z-[70] px-4 py-2 rounded-md bg-emerald-900 text-emerald-100 text-sm shadow-lg';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2800);
  }

  async function init() {
    if (!projectId()) {
      alert('Select a project to manage RFIs.');
      return;
    }
    if (typeof CasePMWorkflow !== 'undefined') await CasePMWorkflow.loadPortal().catch(() => {});
    loadCompanies();
    bindFilters();
    bindAttachmentHandlers();
    await Promise.all([loadDashboard(), loadRfis(), loadLinkOptions()]);
    const newBtn = document.querySelector('[onclick="CasePMRfis.newRfi()"]');
    if (newBtn && !canEnterRfis()) newBtn.classList.add('hidden');
    global.addEventListener('casepm:approval-responded', () => refresh());
    const params = new URLSearchParams(window.location.search);
    if (params.get('respond') === '1' && params.get('rfi_id')) {
      const id = parseInt(params.get('rfi_id'), 10);
      if (id && typeof global.CasePMApprovalResponder !== 'undefined') {
        await global.CasePMApprovalResponder.open('rfi', id);
      } else if (id) {
        await view(id);
      }
    } else if (params.get('open') === '1' && params.get('rfi_id')) {
      const id = parseInt(params.get('rfi_id'), 10);
      if (id) await view(id);
    }
    if (new URLSearchParams(window.location.search).get('action') === 'new') {
      openModal('create');
    }
  }

  global.CasePMRfis = {
    init,
    newRfi: () => openModal('create'),
    saveModal,
    saveAsOpen: () => saveModal(true),
    view,
    edit,
    respond,
    openResponder,
    refresh,
    workflow,
    promotePco,
    deleteRfi,
    addPlanPin,
    removePin,
    closeDrawer,
    exportExcel,
    printLog,
    printDetail,
    focusAttachments,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
