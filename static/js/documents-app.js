(function (global) {
  'use strict';

  const LARGE_FILE_BYTES = 10 * 1024 * 1024;

  const state = {
    projectId: null,
    folderId: null,
    folders: [],
    files: [],
    breadcrumbs: [],
    tree: [],
    viewMode: 'grid',
    search: '',
    selected: null,
    renameTarget: null,
    shareUrl: '',
    expandedFolders: new Set(),
    previewFileId: null,
    previewDoc: null,
    draggingFileId: null,
    draggingFolderId: null,
    browseMode: 'normal',
    searchAll: false,
    previewTab: 'details',
    permissionsFolderId: null,
    versionUploadId: null,
    bulkSelected: new Set(),
    bulkMode: false,
    iconSize: 'md',
  };

  function devUnlock() {
    return typeof CasePMDeveloperUnlock !== 'undefined' && CasePMDeveloperUnlock.isActive();
  }

  function fileIsLocked(doc) {
    if (devUnlock()) return false;
    return !!(doc?.is_system_locked || doc?.is_edit_locked);
  }

  function currentUserId() {
    return global.CASEPM_CURRENT_USER_ID || null;
  }

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function projectName() {
    const pid = projectId();
    const reg = global.CASEPM_PROJECT_REGISTRY || [];
    const hit = reg.find(p => p.id === pid);
    return hit?.name || 'Select Project';
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  function fileIcon(name, mime) {
    const ext = (name || '').split('.').pop()?.toLowerCase() || '';
    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].includes(ext)) return { icon: 'fa-file-image', cls: 'file-img' };
    if (ext === 'pdf' || (mime || '').includes('pdf')) return { icon: 'fa-file-pdf', cls: 'file-pdf' };
    if (['doc', 'docx', 'txt', 'rtf'].includes(ext)) return { icon: 'fa-file-lines', cls: 'file-doc' };
    if (['xls', 'xlsx', 'csv'].includes(ext)) return { icon: 'fa-file-excel', cls: 'file-doc' };
    if (['zip', 'rar', '7z'].includes(ext)) return { icon: 'fa-file-zipper', cls: '' };
    return { icon: 'fa-file', cls: '' };
  }

  function isPreviewable(doc) {
    const mime = (doc?.mime_type || '').toLowerCase();
    const ext = (doc?.name || '').split('.').pop()?.toLowerCase() || '';
    if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].includes(ext)) return 'image';
    if (mime.includes('pdf') || ext === 'pdf') return 'pdf';
    return null;
  }

  function previewKind(doc) {
    const base = isPreviewable(doc);
    if (base) return base;
    if (doc?.editor_kind === 'sheet') return 'sheet';
    if (doc?.editor_kind === 'doc') return 'doc';
    return null;
  }

  function applyIconSize(size) {
    state.iconSize = size || 'md';
    try { localStorage.setItem('casepm_docs_icon_size', state.iconSize); } catch (_) {}
    const wrap = document.getElementById('docsGridWrap');
    wrap?.classList.remove('icon-sm', 'icon-md', 'icon-lg', 'icon-xl');
    wrap?.classList.add(`icon-${state.iconSize}`);
    const sel = document.getElementById('docsIconSize');
    if (sel) sel.value = state.iconSize;
  }

  function renderFolderThumb(folder) {
    const thumbs = folder.preview_thumbs || [];
    if (!thumbs.length) {
      return '<div class="docs-item-icon"><i class="fa-solid fa-folder"></i></div>';
    }
    const mini = thumbs.map((t) => {
      if (t.type === 'image') return `<img src="${esc(t.url)}" alt="">`;
      if (t.type === 'pdf') return '<div class="docs-folder-mini pdf"><i class="fa-solid fa-file-pdf"></i></div>';
      if (t.type === 'sheet') return '<div class="docs-folder-mini sheet"><i class="fa-solid fa-file-excel"></i></div>';
      if (t.type === 'doc') return '<div class="docs-folder-mini doc"><i class="fa-solid fa-file-word"></i></div>';
      return '';
    }).join('');
    return `<div class="docs-folder-thumb"><div class="docs-folder-back"></div><div class="docs-folder-front">${mini}</div></div>`;
  }

  function renderFileThumb(f, fi) {
    if (fi.cls === 'file-img' && f.file_url) {
      return `<div class="docs-file-thumb"><img src="${esc(f.file_url)}" alt=""></div>`;
    }
    return `<div class="docs-file-thumb"><i class="fa-solid ${fi.icon} ${fi.cls}"></i></div>`;
  }

  function sheetTableFromAoa(aoa, maxR = 20, maxC = 10) {
    const rows = (aoa || []).slice(0, maxR);
    let html = '<div class="docs-preview-office sheet"><table><tbody>';
    rows.forEach((row) => {
      html += '<tr>';
      for (let c = 0; c < maxC; c++) {
        const val = row && row[c] != null ? row[c] : '';
        html += `<td>${esc(String(val))}</td>`;
      }
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
  }

  function sheetTableFromLuckysheet(sheets) {
    const s = (sheets && sheets[0]) || {};
    const grid = s.data || [];
    const celldata = s.celldata || [];
    if (!grid.length && celldata.length) {
      const aoa = [];
      celldata.forEach((c) => {
        aoa[c.r] = aoa[c.r] || [];
        const v = c.v && (c.v.m != null ? c.v.m : c.v.v);
        aoa[c.r][c.c] = v;
      });
      return sheetTableFromAoa(aoa);
    }
    const aoa = grid.map((row) => (row || []).map((cell) => {
      if (cell == null) return '';
      if (typeof cell === 'object') return cell.m != null ? cell.m : (cell.v != null ? cell.v : '');
      return cell;
    }));
    return sheetTableFromAoa(aoa);
  }

  async function buildOfficePreviewHtml(doc) {
    const json = await api(`/api/documents/${doc.id}/editor-content`);
    const kind = doc.editor_kind || json.editor_kind;
    if (kind === 'doc') {
      let html = json.editor_content || '';
      if (!html && json.download_url) {
        html = '<p style="color:#71717a;font-size:0.8rem;">No saved content yet. Double-click to open in the Word editor.</p>';
      }
      return `<div class="docs-preview-office doc">${html}</div>`;
    }
    if (kind === 'sheet') {
      if (json.editor_content) {
        try {
          return sheetTableFromLuckysheet(JSON.parse(json.editor_content));
        } catch (_) { /* fall through */ }
      }
      if (json.download_url && global.XLSX) {
        const dl = await fetch(json.download_url, { credentials: 'same-origin' });
        const buf = await dl.arrayBuffer();
        const wb = global.XLSX.read(buf, { type: 'array' });
        const name = wb.SheetNames[0];
        const aoa = global.XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1 });
        return sheetTableFromAoa(aoa);
      }
      return '<div class="docs-preview-office sheet"><p style="color:#71717a;">Open in the spreadsheet editor to view this file.</p></div>';
    }
    return '';
  }

  function ensureExpandedDefaults() {
    state.tree.forEach(node => {
      if (node.parent_id == null) state.expandedFolders.add(node.id);
    });
  }

  function toggleFolderExpand(folderId, e) {
    e?.stopPropagation();
    if (state.expandedFolders.has(folderId)) state.expandedFolders.delete(folderId);
    else state.expandedFolders.add(folderId);
    renderTree();
  }

  async function loadTree() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/document-folders/tree?project_id=${pid}`);
    state.tree = json.tree || [];
    if (!state.expandedFolders.size) ensureExpandedDefaults();
    renderTree();
  }

  async function loadBrowse(folderId) {
    const pid = projectId();
    if (!pid) return;
    state.projectId = pid;
    state.folderId = folderId;
    state.browseMode = 'normal';
    const q = folderId != null ? `&folder_id=${folderId}` : '';
    try {
      const json = await api(`/api/documents/browse?project_id=${pid}${q}`);
      state.folders = json.folders || [];
      state.files = json.files || [];
      state.breadcrumbs = json.breadcrumbs || [];
      if (state.previewFileId && !state.files.some(f => f.id === state.previewFileId)) {
        closePreview();
      }
      render();
      loadTree();
      updateDownloadZipButton();
    } catch (err) {
      if (folderId != null && String(err.message || '').includes('access')) {
        toast('You do not have access to that folder');
        state.folderId = null;
        await openRoot();
        return;
      }
      throw err;
    }
  }

  function openFolder(id) {
    loadBrowse(id);
  }

  function openRoot() {
    const myFiles = state.tree.find(n => n.system_key === 'my-files')
      || state.folders.find(f => f.system_key === 'my-files');
    if (myFiles) {
      openFolder(myFiles.id);
      return;
    }
    const first = state.tree[0] || state.folders[0];
    if (first) openFolder(first.id);
    else loadBrowse(null);
  }

  function renderTree() {
    const el = document.getElementById('docsTree');
    if (!el) return;

    const renderNode = (node, depth) => {
      const hasChildren = (node.children || []).length > 0;
      const expanded = state.expandedFolders.has(node.id);
      const active = state.folderId === node.id ? ' active' : '';
      const sys = node.is_system ? ' system' : '';
      const draggable = node.is_system ? '' : ' draggable="true"';
      const chevron = hasChildren
        ? `<button type="button" class="docs-tree-chevron" data-toggle="${node.id}" aria-label="Toggle"><i class="fa-solid fa-chevron-${expanded ? 'down' : 'right'} text-[9px]"></i></button>`
        : '<span class="docs-tree-chevron placeholder"></span>';

      let html = `<div class="docs-tree-node" data-tree-folder="${node.id}">
        <div class="docs-tree-row${active}${sys}" data-folder-id="${node.id}" data-drop-folder="${node.id}" data-system="${node.is_system ? '1' : ''}"${draggable}>
          ${chevron}
          <i class="fa-solid fa-folder${node.is_system ? '-tree' : ''} text-amber-400 text-xs"></i>
          <span class="truncate flex-1">${esc(node.name)}</span>
        </div>`;
      if (hasChildren && expanded) {
        html += `<div class="docs-tree-children">${node.children.map(c => renderNode(c, depth + 1)).join('')}</div>`;
      }
      html += '</div>';
      return html;
    };

    el.innerHTML = `<div class="docs-tree-root-drop" data-drop-root="1" title="Drop folder here to move to top level">Top level</div>`
      + state.tree.map(n => renderNode(n, 0)).join('');

    const rootDrop = el.querySelector('[data-drop-root]');
    if (rootDrop) bindFolderDropTarget(rootDrop, null);

    el.querySelectorAll('[data-toggle]').forEach(btn => {
      btn.addEventListener('click', e => toggleFolderExpand(parseInt(btn.dataset.toggle, 10), e));
    });
    el.querySelectorAll('[data-folder-id]').forEach(row => {
      row.addEventListener('click', e => {
        if (e.target.closest('[data-toggle]')) return;
        if (state.draggingFolderId) return;
        openFolder(parseInt(row.dataset.folderId, 10));
      });
      bindFolderDropTarget(row, parseInt(row.dataset.folderId, 10));
      if (row.dataset.system !== '1') bindFolderDrag(row, parseInt(row.dataset.folderId, 10));
    });
  }

  function renderBreadcrumbs() {
    const el = document.getElementById('docsBreadcrumbs');
    if (!el) return;
    const parts = [`<span class="docs-crumb" data-folder="root"><i class="fa-solid fa-house"></i> Project</span>`];
    state.breadcrumbs.forEach(b => {
      parts.push('<span class="docs-crumb-sep">/</span>');
      parts.push(`<span class="docs-crumb" data-folder="${b.id}">${esc(b.name)}</span>`);
    });
    el.innerHTML = parts.join('');
    el.querySelectorAll('.docs-crumb').forEach(cr => {
      cr.addEventListener('click', () => {
        const f = cr.dataset.folder;
        if (f === 'root') openRoot();
        else loadBrowse(parseInt(f, 10));
      });
    });
  }

  function filteredItems() {
    const q = state.search.trim().toLowerCase();
    if (state.browseMode === 'trash') {
      return { folders: state.folders, files: state.files };
    }
    const folders = state.folders.filter(f => !q || f.name.toLowerCase().includes(q));
    const files = state.files.filter(f => !q || f.name.toLowerCase().includes(q));
    return { folders, files };
  }

  let searchTimer = null;
  async function runGlobalSearch() {
    const pid = projectId();
    const q = state.search.trim();
    if (!state.searchAll || !q || !pid) {
      render();
      return;
    }
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      try {
        const json = await api(`/api/documents/search?project_id=${pid}&q=${encodeURIComponent(q)}`);
        state.folders = json.folders || [];
        state.files = json.files || [];
        state.browseMode = 'search';
        renderBrowseResults();
      } catch (e) {
        console.error(e);
      }
    }, 300);
  }

  function renderBrowseResults() {
    renderBreadcrumbs();
    const empty = document.getElementById('docsEmpty');
    const gridWrap = document.getElementById('docsGridWrap');
    const { folders, files } = { folders: state.folders, files: state.files };
    if (!folders.length && !files.length) {
      document.getElementById('docsGrid').innerHTML = '';
      document.getElementById('docsTableBody').innerHTML = '';
      empty?.classList.remove('hidden');
      if (empty) empty.innerHTML = '<p class="text-zinc-500">No matches found.</p>';
      gridWrap?.classList.add('hidden');
      updateDownloadZipButton();
      syncSelectAllCheckbox();
      return;
    }
    empty?.classList.add('hidden');
    gridWrap?.classList.remove('hidden');
    if (state.viewMode === 'list') renderList(folders, files);
    else renderGrid(folders, files);
    updateDownloadZipButton();
    syncSelectAllCheckbox();
  }

  async function loadTrash() {
    const pid = projectId();
    if (!pid) return;
    state.browseMode = 'trash';
    state.folderId = null;
    const json = await api(`/api/documents/trash?project_id=${pid}`);
    state.folders = json.folders || [];
    state.files = json.files || [];
    state.breadcrumbs = [{ id: 0, name: 'Recycle bin' }];
    closePreview();
    renderBrowseResults();
    updateDownloadZipButton();
  }

  async function exitTrash() {
    state.browseMode = 'normal';
    await loadBrowse(null);
    openRoot();
  }

  function findNodeInTree(id) {
    let found = null;
    const walk = (nodes) => {
      for (const n of nodes || []) {
        if (n.id === id) { found = n; return; }
        walk(n.children);
      }
    };
    walk(state.tree);
    return found;
  }

  function isNodeInSubtree(node, searchId) {
    if (!node) return false;
    if (node.id === searchId) return true;
    return (node.children || []).some(c => isNodeInSubtree(c, searchId));
  }

  function canDropFolderOn(dragId, targetId) {
    if (!dragId || !targetId || dragId === targetId) return false;
    const dragNode = findNodeInTree(dragId);
    return !(dragNode && isNodeInSubtree(dragNode, targetId));
  }

  function setViewMode(mode) {
    state.viewMode = mode;
    const wrap = document.getElementById('docsGridWrap');
    wrap?.classList.toggle('view-grid', mode === 'grid');
    wrap?.classList.toggle('view-list', mode === 'list');
    document.getElementById('docsViewGrid')?.classList.toggle('active', mode === 'grid');
    document.getElementById('docsViewList')?.classList.toggle('active', mode === 'list');
    render();
  }

  function selectItem(kind, id, locked, system) {
    const effectiveLocked = devUnlock() ? false : !!locked;
    state.selected = { kind, id, locked: effectiveLocked, system: !!system };
    document.querySelectorAll('.docs-item.selected, .docs-table tr.selected').forEach(x => x.classList.remove('selected'));
    const sel = kind === 'folder'
      ? document.querySelector(`.docs-item[data-kind="folder"][data-id="${id}"], tr[data-kind="folder"][data-id="${id}"]`)
      : document.querySelector(`.docs-item[data-kind="file"][data-id="${id}"], tr[data-kind="file"][data-id="${id}"]`);
    sel?.classList.add('selected');
  }

  function renderGrid(folders, files) {
    const grid = document.getElementById('docsGrid');
    const tableBody = document.getElementById('docsTableBody');
    if (!grid || !tableBody) return;

    tableBody.innerHTML = '';

    let html = '';
    folders.forEach(f => {
      const sel = state.selected?.kind === 'folder' && state.selected.id === f.id ? ' selected' : '';
      const lock = f.is_system ? '<span class="docs-item-badge">System</span>' : '';
      html += `<div class="docs-item folder${sel}" data-kind="folder" data-id="${f.id}" data-system="${f.is_system ? '1' : ''}" data-drop-folder="${f.id}">
        ${lock}
        ${renderFolderThumb(f)}
        <div class="docs-item-name">${esc(f.name)}</div>
        <div class="docs-item-meta">${f.file_count || 0} files</div>
      </div>`;
    });
    files.forEach(f => {
      const sel = state.selected?.kind === 'file' && state.selected.id === f.id ? ' selected' : '';
      const fi = fileIcon(f.name, f.mime_type);
      const lock = f.is_system_locked ? '<span class="docs-item-badge">Job</span>' : '';
      const co = f.is_checked_out ? `<span class="docs-item-badge checkout" title="Checked out by ${esc(f.checked_out_by_name || '')}"><i class="fa-solid fa-lock text-[9px]"></i></span>` : '';
      const bulk = state.browseMode === 'normal' ? `<input type="checkbox" class="docs-bulk-cb" data-bulk-id="${f.id}" ${state.bulkSelected.has(f.id) ? 'checked' : ''}>` : '';
      html += `<div class="docs-item file ${fi.cls}${sel}" data-kind="file" data-id="${f.id}" data-locked="${f.is_system_locked && !devUnlock() ? '1' : ''}" data-edit-locked="${f.is_edit_locked && !devUnlock() ? '1' : ''}" draggable="${(f.is_system_locked || f.is_edit_locked) && !devUnlock() ? 'false' : 'true'}">
        ${lock}${co}${bulk}
        ${renderFileThumb(f, fi)}
        <div class="docs-item-name">${esc(f.name)}</div>
        <div class="docs-item-meta">${esc(f.size || '')}</div>
      </div>`;
    });
    grid.innerHTML = html;
    bindItemEvents(grid);
  }

  function renderList(folders, files) {
    const grid = document.getElementById('docsGrid');
    const tableBody = document.getElementById('docsTableBody');
    if (!grid || !tableBody) return;

    grid.innerHTML = '';

    let html = '';
    folders.forEach(f => {
      const sel = state.selected?.kind === 'folder' && state.selected.id === f.id ? ' selected' : '';
      html += `<tr class="${sel}" data-kind="folder" data-id="${f.id}" data-system="${f.is_system ? '1' : ''}" data-drop-folder="${f.id}">
        <td class="docs-row-icon"><i class="fa-solid fa-folder"></i></td>
        <td>${esc(f.name)}${f.is_system ? ' <span class="text-[10px] text-violet-400">System</span>' : ''}</td>
        <td class="text-xs text-zinc-500">Folder</td>
        <td class="text-xs text-zinc-500">${f.file_count || 0}</td>
        <td class="text-xs text-zinc-500"></td>
        <td class="text-xs text-zinc-500"></td>
      </tr>`;
    });
    files.forEach(f => {
      const sel = state.selected?.kind === 'file' && state.selected.id === f.id ? ' selected' : '';
      const fi = fileIcon(f.name, f.mime_type);
      html += `<tr class="${sel}" data-kind="file" data-id="${f.id}" data-locked="${f.is_system_locked && !devUnlock() ? '1' : ''}" data-edit-locked="${f.is_edit_locked && !devUnlock() ? '1' : ''}" draggable="${(f.is_system_locked || f.is_edit_locked) && !devUnlock() ? 'false' : 'true'}">
        <td class="docs-row-icon ${fi.cls}">${state.browseMode === 'normal' ? `<input type="checkbox" class="docs-bulk-cb" data-bulk-id="${f.id}" ${state.bulkSelected.has(f.id) ? 'checked' : ''}>` : ''}<i class="fa-solid ${fi.icon}"></i>${f.is_checked_out ? ' <i class="fa-solid fa-lock text-amber-400 text-[10px]" title="Checked out"></i>' : ''}</td>
        <td>${esc(f.name)}</td>
        <td class="text-xs text-zinc-500">${esc(f.document_type || '')}</td>
        <td class="text-xs">${esc(f.size || '')}</td>
        <td class="text-xs text-zinc-500">${esc(f.uploaded || '')}</td>
        <td class="text-xs text-zinc-500">${esc(f.uploaded_by_name || '—')}</td>
      </tr>`;
    });
    tableBody.innerHTML = html;
    bindItemEvents(tableBody);
  }

  function render() {
    renderBreadcrumbs();
    const empty = document.getElementById('docsEmpty');
    const gridWrap = document.getElementById('docsGridWrap');
    const { folders, files } = filteredItems();
    if (!folders.length && !files.length) {
      document.getElementById('docsGrid').innerHTML = '';
      document.getElementById('docsTableBody').innerHTML = '';
      empty?.classList.remove('hidden');
      gridWrap?.classList.add('hidden');
      updateDownloadZipButton();
      syncSelectAllCheckbox();
      return;
    }
    empty?.classList.add('hidden');
    gridWrap?.classList.remove('hidden');
    if (state.viewMode === 'list') renderList(folders, files);
    else renderGrid(folders, files);
    updateDownloadZipButton();
    syncSelectAllCheckbox();
  }

  function bindItemEvents(container) {
    container.querySelectorAll('[data-kind]').forEach(el => {
      el.addEventListener('click', e => {
        if (state.draggingFileId || state.draggingFolderId) return;
        const kind = el.dataset.kind;
        const id = parseInt(el.dataset.id, 10);
        if (e.detail === 2) {
          if (kind === 'folder') openFolder(id);
          else openDocumentViewerFromList(id);
          return;
        }
        selectItem(kind, id, el.dataset.locked === '1', el.dataset.system === '1');
        if (kind === 'file') showPreview(id);
      });
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        selectItem(el.dataset.kind, parseInt(el.dataset.id, 10), el.dataset.locked === '1', el.dataset.system === '1');
        showContextMenu(e.clientX, e.clientY);
      });
      if (el.dataset.kind === 'file' && el.dataset.locked !== '1' && el.dataset.editLocked !== '1') bindFileDrag(el);
      if (el.dataset.kind === 'folder') bindFolderDropTarget(el, parseInt(el.dataset.dropFolder, 10));
    });
    container.querySelectorAll('.docs-bulk-cb').forEach(cb => {
      cb.addEventListener('click', e => e.stopPropagation());
      cb.addEventListener('change', () => toggleBulkSelect(parseInt(cb.dataset.bulkId, 10), cb.checked));
    });
  }

  function bindFolderDrag(el, folderId) {
    el.addEventListener('dragstart', e => {
      state.draggingFolderId = folderId;
      el.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('application/x-docs-folder', String(folderId));
      e.stopPropagation();
    });
    el.addEventListener('dragend', () => {
      state.draggingFolderId = null;
      el.classList.remove('dragging');
      clearDropHighlights();
    });
  }

  function bindFileDrag(el) {
    el.addEventListener('dragstart', e => {
      const id = parseInt(el.dataset.id, 10);
      state.draggingFileId = id;
      el.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('application/x-docs-file', String(id));
    });
    el.addEventListener('dragend', () => {
      state.draggingFileId = null;
      el.classList.remove('dragging');
      clearDropHighlights();
    });
  }

  function bindFolderDropTarget(el, folderId) {
    el.addEventListener('dragover', e => {
      if (!state.draggingFileId && !state.draggingFolderId) return;
      if (state.draggingFolderId && folderId != null && !canDropFolderOn(state.draggingFolderId, folderId)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      el.classList.add('drop-target');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drop-target'));
    el.addEventListener('drop', async e => {
      e.preventDefault();
      el.classList.remove('drop-target');
      if (state.draggingFolderId) {
        await moveFolderToParent(state.draggingFolderId, folderId);
        return;
      }
      const fileId = state.draggingFileId || parseInt(e.dataTransfer.getData('application/x-docs-file'), 10);
      if (!fileId || folderId == null) return;
      await moveFileToFolder(fileId, folderId);
    });
  }

  function clearDropHighlights() {
    document.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target'));
  }

  async function moveFileToFolder(fileId, folderId) {
    const file = state.files.find(f => f.id === fileId) || state.previewDoc;
    if (fileIsLocked(file)) return;
    if (file?.folder_id === folderId) return;
    try {
      await api(`/api/documents/${fileId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_id: folderId }),
      });
      toast('File moved');
      if (state.previewFileId === fileId) await loadPreview(fileId);
      await loadBrowse(state.folderId);
    } catch (err) {
      alert(err.message || 'Could not move file');
    }
  }

  async function moveFolderToParent(folderId, parentId) {
    const node = findNodeInTree(folderId);
    if (!node || node.is_system) return;
    if (parentId != null && !canDropFolderOn(folderId, parentId)) return;
    const currentParent = node.parent_id ?? null;
    const nextParent = parentId ?? null;
    if (currentParent === nextParent) return;
    try {
      await api(`/api/document-folders/${folderId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_id: nextParent }),
      });
      toast('Folder moved');
      await loadBrowse(state.folderId);
    } catch (err) {
      alert(err.message || 'Could not move folder');
    }
  }

  async function showPreview(fileId) {
    state.previewFileId = fileId;
    const panel = document.getElementById('docsPreviewPanel');
    panel?.classList.add('open');
    await loadPreview(fileId);
  }

  async function loadPreview(fileId, tab) {
    state.previewTab = tab || state.previewTab || 'details';
    const body = document.getElementById('docsPreviewBody');
    if (!body) return;
    try {
      const json = await api(`/api/documents/${fileId}`);
      const doc = json.document;
      state.previewDoc = doc;
      const tabs = `
        <div class="flex gap-1 mb-3 flex-wrap">
          ${['details', 'versions', 'comments', 'activity'].map(t =>
            `<button type="button" class="docs-preview-tab${state.previewTab === t ? ' active' : ''}" data-ptab="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</button>`
          ).join('')}
        </div>`;
      let content = '';
      if (state.previewTab === 'details') {
        content = renderPreviewDetails(doc);
        body.innerHTML = tabs + content;
        body.querySelectorAll('[data-ptab]').forEach(btn => {
          btn.addEventListener('click', () => loadPreview(fileId, btn.dataset.ptab));
        });
        bindPreviewActions(doc);
        const kind = previewKind(doc);
        if (kind === 'doc' || kind === 'sheet') {
          const host = document.getElementById('docsOfficePreviewHost');
          try {
            const html = await buildOfficePreviewHtml(doc);
            if (host) host.outerHTML = html;
          } catch (err) {
            if (host) host.innerHTML = `<p class="text-red-400 text-sm">${esc(err.message)}</p>`;
          }
        }
        return;
      }
      if (state.previewTab === 'versions') content = await renderPreviewVersions(fileId, doc);
      else if (state.previewTab === 'comments') content = await renderPreviewComments(fileId);
      else content = await renderPreviewActivity(fileId);
      body.innerHTML = tabs + content;
      body.querySelectorAll('[data-ptab]').forEach(btn => {
        btn.addEventListener('click', () => loadPreview(fileId, btn.dataset.ptab));
      });
      bindPreviewActions(doc);
    } catch (err) {
      body.innerHTML = `<p class="text-red-400 text-sm">${esc(err.message)}</p>`;
    }
  }

  function renderPreviewDetails(doc) {
    const kind = previewKind(doc);
    let media = '';
    if (kind === 'image') {
      media = `<img class="docs-preview-media" src="${esc(doc.file_url)}" alt="${esc(doc.name)}">`;
    } else if (kind === 'pdf') {
      media = `<iframe class="docs-preview-frame" src="${esc(doc.file_url)}" title="${esc(doc.name)}"></iframe>`;
    } else if (kind === 'doc' || kind === 'sheet') {
      media = '<div id="docsOfficePreviewHost" class="docs-preview-loading"><i class="fa-solid fa-spinner fa-spin mr-2"></i>Loading preview…</div>';
    } else {
      const fi = fileIcon(doc.name, doc.mime_type);
      media = `<div class="text-center py-8"><i class="fa-solid ${fi.icon} text-5xl ${fi.cls} text-amber-400"></i><p class="text-sm text-zinc-400 mt-3">No preview for this file type</p></div>`;
    }
    const openLabel = kind === 'doc' || kind === 'sheet'
      ? 'Open in editor'
      : (kind ? 'Open &amp; markup' : '');
    return `
      ${media}
      <h3 class="text-sm font-semibold text-white mt-3 break-words">${esc(doc.name)}</h3>
      <dl class="docs-preview-meta">
        <dt>Uploaded by</dt><dd>${esc(doc.uploaded_by_name || 'Unknown')}</dd>
        <dt>Uploaded</dt><dd>${esc(doc.created_at ? doc.created_at.slice(0, 16).replace('T', ' ') : '—')}</dd>
        <dt>Modified</dt><dd>${esc(doc.updated_at ? doc.updated_at.slice(0, 16).replace('T', ' ') : '—')}</dd>
        <dt>Size</dt><dd>${esc(doc.size || '—')}</dd>
        <dt>Versions</dt><dd>${esc(doc.version_count || 1)}</dd>
        <dt>Type</dt><dd>${esc(doc.document_type || doc.mime_type || '—')}</dd>
        <dt>Folder</dt><dd>${esc(doc.folder_name || '—')}</dd>
        ${doc.is_system_locked && !devUnlock() ? '<dt>Status</dt><dd class="text-violet-300">Locked job file</dd>' : (doc.is_system_locked ? '<dt>Status</dt><dd class="text-red-300">Unlocked for editing (dev mode)</dd>' : '')}
        ${doc.is_checked_out ? `<dt>Checked out</dt><dd class="text-amber-300">${esc(doc.checked_out_by_name || 'Someone')}${doc.checked_out_at ? ' · ' + esc(doc.checked_out_at.slice(0, 16).replace('T', ' ')) : ''}</dd>` : ''}
        ${doc.legal_hold ? '<dt>Legal hold</dt><dd class="text-red-300">On hold — cannot delete</dd>' : ''}
        ${(doc.tags || []).length ? `<dt>Tags</dt><dd>${esc((doc.tags || []).join(', '))}</dd>` : ''}
      </dl>
      <div class="docs-preview-actions">
        ${kind ? `<button type="button" class="docs-btn docs-btn-primary" id="docsPreviewOpen"><i class="fa-solid fa-${kind === 'doc' ? 'file-word' : kind === 'sheet' ? 'file-excel' : 'pen-ruler'}"></i> ${openLabel}</button>` : ''}
        <button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewDownload"><i class="fa-solid fa-download"></i> Download</button>
        <button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewShare"><i class="fa-solid fa-link"></i> Share</button>
        ${doc.can_check_out ? '<button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewCheckout"><i class="fa-solid fa-lock"></i> Check out</button>' : ''}
        ${doc.can_check_in ? '<button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewCheckin"><i class="fa-solid fa-lock-open"></i> Check in</button>' : ''}
        ${doc.can_force_unlock ? '<button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewForceUnlock"><i class="fa-solid fa-unlock"></i> Force unlock</button>' : ''}
        ${(!doc.is_system_locked || devUnlock()) && !doc.is_edit_locked ? '<button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewNewVersion"><i class="fa-solid fa-clock-rotate-left"></i> New version</button>' : ''}
      </div>
      ${(!doc.is_system_locked || devUnlock()) ? `<div class="mt-3 pt-3 border-t border-zinc-800">
        <label class="text-xs text-zinc-500 block mb-1">Tags (comma-separated)</label>
        <input type="text" id="docsPreviewTags" class="docs-input w-full text-xs mb-2" value="${esc((doc.tags || []).join(', '))}">
        <button type="button" class="docs-btn docs-btn-secondary w-full text-xs" id="docsPreviewSaveTags">Save tags</button>
      </div>` : ''}`;
  }

  async function renderPreviewVersions(fileId, doc) {
    const json = await api(`/api/documents/${fileId}/versions`);
    const rows = (json.versions || []).map(v =>
      `<div class="flex items-center justify-between gap-2 py-2 border-b border-zinc-800 text-xs">
        <span>v${v.version_no} · ${esc(v.size)} · ${esc(v.created_at?.slice(0, 10) || '')}</span>
        <span class="flex gap-1">
          <a class="text-sky-400" href="/api/documents/${fileId}/versions/${v.id}/download">DL</a>
          <button type="button" class="text-emerald-400" data-restore-ver="${v.id}">Restore</button>
        </span>
      </div>`
    ).join('');
    return `<p class="text-xs text-zinc-500 mb-2">Current: v${json.current_version || 1}</p>${rows || '<p class="text-zinc-500 text-sm">No prior versions yet.</p>'}`;
  }

  async function renderPreviewComments(fileId) {
    const json = await api(`/api/documents/${fileId}/comments`);
    const list = (json.comments || []).map(c =>
      `<div class="mb-2 p-2 bg-zinc-800/50 rounded text-xs"><div class="text-zinc-400">${esc(c.user_name)} · ${esc(c.created_at?.slice(0, 16).replace('T', ' ') || '')}</div><div class="mt-1">${esc(c.body)}</div></div>`
    ).join('');
    return `${list || '<p class="text-zinc-500 text-sm">No comments yet.</p>'}
      <textarea id="docsNewComment" class="docs-input w-full mt-2 text-xs" rows="3" placeholder="Add a comment…"></textarea>
      <button type="button" class="docs-btn docs-btn-primary mt-2 w-full" id="docsPostComment">Post comment</button>`;
  }

  async function renderPreviewActivity(fileId) {
    const json = await api(`/api/documents/${fileId}/activity`);
    const rows = (json.activity || []).map(a =>
      `<div class="py-1.5 border-b border-zinc-800 text-xs"><span class="text-zinc-300">${esc(a.action)}</span>
        <span class="text-zinc-500"> · ${esc(a.user_name || 'System')} · ${esc(a.created_at?.slice(0, 16).replace('T', ' ') || '')}</span></div>`
    ).join('');
    return rows || '<p class="text-zinc-500 text-sm">No activity recorded.</p>';
  }

  function bindPreviewActions(doc) {
    document.getElementById('docsPreviewOpen')?.addEventListener('click', () => openDocumentViewerFromList(doc.id));
    document.getElementById('docsPreviewDownload')?.addEventListener('click', () => downloadFile(doc.id));
    document.getElementById('docsPreviewShare')?.addEventListener('click', () => copyShareLink(doc.id));
    document.getElementById('docsPreviewCheckout')?.addEventListener('click', () => checkoutDocument(doc.id));
    document.getElementById('docsPreviewCheckin')?.addEventListener('click', () => checkinDocument(doc.id));
    document.getElementById('docsPreviewForceUnlock')?.addEventListener('click', () => forceUnlockDocument(doc.id));
    document.getElementById('docsPreviewSaveTags')?.addEventListener('click', async () => {
      const tags = document.getElementById('docsPreviewTags')?.value || '';
      await api(`/api/documents/${doc.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: tags.split(',').map(t => t.trim()).filter(Boolean) }),
      });
      toast('Tags saved');
      await loadPreview(doc.id);
    });
    document.getElementById('docsPreviewNewVersion')?.addEventListener('click', () => {
      state.versionUploadId = doc.id;
      document.getElementById('docsVersionInput')?.click();
    });
    document.getElementById('docsPostComment')?.addEventListener('click', async () => {
      const text = document.getElementById('docsNewComment')?.value?.trim();
      if (!text) return;
      await api(`/api/documents/${doc.id}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: text }),
      });
      await loadPreview(doc.id, 'comments');
    });
    document.querySelectorAll('[data-restore-ver]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Restore this version as the current file?')) return;
        await api(`/api/documents/${doc.id}/versions/${btn.dataset.restoreVer}/restore`, { method: 'POST' });
        toast('Version restored');
        await loadPreview(doc.id, 'versions');
        await loadBrowse(state.folderId);
      });
    });
  }

  function closePreview() {
    state.previewFileId = null;
    state.previewDoc = null;
    document.getElementById('docsPreviewPanel')?.classList.remove('open');
    const body = document.getElementById('docsPreviewBody');
    if (body) {
      body.innerHTML = `<div class="docs-preview-placeholder text-center text-zinc-500 text-sm py-12">
        <i class="fa-solid fa-file-lines text-3xl mb-2 block text-zinc-600"></i>
        Select a file to preview
      </div>`;
    }
  }

  function showContextMenu(x, y) {
    document.querySelector('.docs-context')?.remove();
    if (!state.selected) return;
    const menu = document.createElement('div');
    menu.className = 'docs-context';
    const items = [];
    if (state.browseMode === 'trash') {
      if (state.selected.kind === 'file') {
        items.push({ label: 'Restore', action: () => restoreFile(state.selected.id) });
        items.push({ label: 'Delete permanently', action: () => permanentDeleteFile(state.selected.id), danger: true });
      } else {
        items.push({ label: 'Restore folder', action: () => restoreFolder(state.selected.id) });
      }
    } else if (state.selected.kind === 'folder') {
      items.push({ label: 'Open', action: () => openFolder(state.selected.id) });
      items.push({ label: 'Download folder as ZIP', action: () => downloadFolderZip(state.selected.id) });
      items.push({ label: 'Share folder link…', action: () => createFolderShareLink(state.selected.id) });
      items.push({ label: 'Request files link…', action: () => createFolderShareLink(state.selected.id, true) });
      items.push({ label: 'Folder permissions…', action: () => openPermissions(state.selected.id) });
      if (!state.selected.system) {
        items.push({ label: 'Rename', action: () => startRename('folder', state.selected.id) });
        items.push({ label: 'Delete', action: () => deleteFolder(state.selected.id), danger: true });
      }
    } else {
      const file = state.files.find(f => f.id === state.selected.id) || state.previewDoc;
      if (file && file.editor_kind) {
        const editorLabel = file.editor_kind === 'sheet' ? 'Open in Spreadsheet editor' : 'Open in Document editor';
        items.push({ label: editorLabel, action: () => openInEditor(state.selected.id, file.editor_kind) });
      }
      if (file && isPreviewable(file)) {
        items.push({ label: 'Open & markup', action: () => openDocumentViewerFromList(state.selected.id) });
      }
      items.push({ label: 'Preview', action: () => showPreview(state.selected.id) });
      items.push({ label: 'Download', action: () => downloadFile(state.selected.id) });
      if (file?.can_check_out) items.push({ label: 'Check out', action: () => checkoutDocument(state.selected.id) });
      if (file?.can_check_in) items.push({ label: 'Check in', action: () => checkinDocument(state.selected.id) });
      if (file?.can_force_unlock) items.push({ label: 'Force unlock', action: () => forceUnlockDocument(state.selected.id) });
      items.push({ label: 'Get shareable link (copy)', action: () => copyShareLink(state.selected.id) });
      items.push({ label: 'Share link options…', action: () => createShareLink(state.selected.id) });
      const locked = devUnlock() ? false : state.selected.locked;
      items.push({ label: 'Rename', action: () => startRename('file', state.selected.id), disabled: locked });
      items.push({ label: 'Delete', action: () => deleteFile(state.selected.id), danger: true, disabled: locked });
    }
    items.forEach(it => {
      if (it.disabled) return;
      const btn = document.createElement('button');
      btn.textContent = it.label;
      if (it.danger) btn.classList.add('danger');
      btn.addEventListener('click', () => { menu.remove(); it.action(); });
      menu.appendChild(btn);
    });
    document.body.appendChild(menu);
    menu.style.left = `${Math.min(x, window.innerWidth - 180)}px`;
    menu.style.top = `${Math.min(y, window.innerHeight - 200)}px`;
    setTimeout(() => document.addEventListener('click', () => menu.remove(), { once: true }), 0);
  }

  async function uploadFiles(fileList, opts) {
    const pid = projectId();
    if (!pid || !fileList?.length) return null;
    const results = [];
    for (const file of fileList) {
      const fd = new FormData();
      fd.append('project_id', pid);
      fd.append('file', file);
      fd.append('name', file.name);
      if (state.folderId) fd.append('folder_id', state.folderId);
      if (opts?.createShareLink) fd.append('create_share_link', '1');
      const res = await fetch('/api/documents', { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || `Upload failed: ${file.name}`);
      results.push(json);
    }
    await loadBrowse(state.folderId);
    return results;
  }

  async function uploadFileAsShareLink(file, projectIdOverride) {
    const pid = projectIdOverride || projectId();
    if (!pid) throw new Error('Select a project');
    const fd = new FormData();
    fd.append('project_id', pid);
    fd.append('file', file);
    fd.append('name', file.name);
    fd.append('create_share_link', '1');
    const res = await fetch('/api/documents', { method: 'POST', body: fd, credentials: 'same-origin' });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Upload failed');
    return json.share_link;
  }

  async function offerLinkInstead(file, composeState) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    const useLink = await (global.CasePMDialog?.confirm
      ? global.CasePMDialog.confirm(
        `"${file.name}" is ${mb} MB. Upload to Documents and insert a download link instead of attaching? (Recommended for large files, like OneDrive/Dropbox)`,
        { title: 'Large attachment', confirmLabel: 'Use link', cancelLabel: 'Attach anyway' },
      )
      : Promise.resolve(confirm(`Large file (${mb} MB). Use Documents link instead?`)));
    if (!useLink) {
      addFilesDirect(file, composeState);
      return;
    }
    try {
      const link = await uploadFileAsShareLink(file);
      const url = link?.share_url || link?.download_url;
      if (!url) throw new Error('No share link returned');
      const body = document.getElementById('inlineComposeBody');
      if (body) {
        const line = `\n\nDownload: ${file.name}\n${url}\n`;
        body.value = (body.value || '') + line;
      }
      if (composeState && !composeState.attachments) composeState.attachments = [];
      composeState.attachments.push({
        name: `${file.name} (link)`,
        size: 'Link',
        type: 'text/uri-list',
        isLink: true,
        linkUrl: url,
      });
      if (global.CasePMEmail?.refreshComposeAttachmentUI) global.CasePMEmail.refreshComposeAttachmentUI();
      toast(`Link inserted — ${file.name}`);
    } catch (e) {
      alert(e.message || 'Failed to create share link');
      addFilesDirect(file, composeState);
    }
  }

  function addFilesDirect(file, composeState) {
    if (!composeState) return;
    if (!composeState.attachments) composeState.attachments = [];
    const entry = {
      name: file.name,
      size: formatFileSize(file.size),
      type: file.type,
      mimeType: file.type,
      file,
    };
    composeState.attachments.push(entry);
    const reader = new FileReader();
    reader.onload = () => {
      entry.dataBase64 = String(reader.result || '').split(',')[1] || '';
    };
    reader.readAsDataURL(file);
    if (global.CasePMEmail?.refreshComposeAttachmentUI) global.CasePMEmail.refreshComposeAttachmentUI();
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function toast(msg) {
    if (global.CasePMDialog?.toast) global.CasePMDialog.toast(msg);
    else console.log(msg);
  }

  async function copyShareLink(fileId, password, expiresDays) {
    try {
      const days = expiresDays || parseInt(document.getElementById('docsShareExpiryDays')?.value || '30', 10);
      const json = await api(`/api/documents/${fileId}/share-links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expires_days: days, password: password || undefined }),
      });
      const url = json.share_link?.share_url || '';
      if (!url) throw new Error('No share link returned');
      if (json.share_link?.approval_status === 'pending') {
        toast('Share link submitted for PM approval — it will not work until approved');
        return;
      }
      await navigator.clipboard.writeText(url);
      toast(`Share link copied — expires in ${json.share_link?.expires_in_days || days} days`);
    } catch (err) {
      alert(err.message || 'Could not create share link');
    }
  }

  async function createShareLink(fileId) {
    const password = document.getElementById('docsSharePassword')?.value || '';
    const days = parseInt(document.getElementById('docsShareExpiryDays')?.value || '30', 10);
    const json = await api(`/api/documents/${fileId}/share-links`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expires_days: days, password: password || undefined }),
    });
    const url = json.share_link?.share_url || '';
    state.shareUrl = url;
    document.getElementById('docsShareUrl').value = url;
    document.getElementById('docsShareMeta').textContent = json.share_link?.approval_status === 'pending'
      ? 'Pending PM approval — link inactive until approved'
      : json.share_link?.expires_at
      ? `Expires ${json.share_link.expires_at.slice(0, 10)} · ${json.share_link.download_count || 0} downloads`
      : '';
    document.getElementById('docsShareDialog')?.showModal();
  }

  async function createFolderShareLink(folderId, allowUpload) {
    const password = document.getElementById('docsFolderSharePassword')?.value || '';
    const days = parseInt(document.getElementById('docsFolderShareExpiryDays')?.value || '30', 10);
    const json = await api(`/api/document-folders/${folderId}/share-links`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expires_days: days,
        password: password || undefined,
        allow_upload: !!allowUpload,
      }),
    });
    const url = json.share_link?.share_url || '';
    document.getElementById('docsFolderShareUrl').value = url;
    document.getElementById('docsFolderShareUpload').checked = !!allowUpload;
    document.getElementById('docsFolderShareDialog')?.showModal();
    if (url) {
      await navigator.clipboard.writeText(url);
      toast(json.share_link?.approval_status === 'pending'
        ? 'Link pending PM approval'
        : allowUpload ? 'Request-files link copied' : 'Folder share link copied');
    }
  }

  async function openPermissions(folderId) {
    state.permissionsFolderId = folderId;
    const usersJson = await api('/api/users/list');
    const sel = document.getElementById('docsPermUser');
    if (sel) {
      sel.innerHTML = (usersJson.users || []).map(u =>
        `<option value="${u.id}">${esc(u.name)} (${esc(u.email)})</option>`
      ).join('');
    }
    await refreshPermissionsList();
    document.getElementById('docsPermissionsDialog')?.showModal();
  }

  async function refreshPermissionsList() {
    const el = document.getElementById('docsPermList');
    if (!el || !state.permissionsFolderId) return;
    const json = await api(`/api/document-folders/${state.permissionsFolderId}/permissions`);
    el.innerHTML = (json.permissions || []).map(p => `
      <div class="docs-perm-row">
        <span class="flex-1 min-w-[10rem] truncate">${esc(p.user_name)} <span class="text-zinc-500 text-xs">${esc(p.user_email)}</span></span>
        <label class="text-xs"><input type="checkbox" data-pid="${p.id}" data-k="can_view" ${p.can_view ? 'checked' : ''}> View</label>
        <label class="text-xs"><input type="checkbox" data-pid="${p.id}" data-k="can_upload" ${p.can_upload ? 'checked' : ''}> Upload</label>
        <label class="text-xs"><input type="checkbox" data-pid="${p.id}" data-k="can_manage" ${p.can_manage ? 'checked' : ''}> Manage</label>
        <button type="button" class="text-red-400 text-xs shrink-0" data-del-pid="${p.id}">Remove</button>
      </div>`).join('') || '<p class="text-zinc-500 text-xs">No restrictions — folder is open to all project users.</p>';
    el.querySelectorAll('[data-del-pid]').forEach(btn => {
      btn.addEventListener('click', async () => {
        await api(`/api/document-folders/permissions/${btn.dataset.delPid}`, { method: 'DELETE' });
        await refreshPermissionsList();
      });
    });
    el.querySelectorAll('input[data-pid]').forEach(ch => {
      ch.addEventListener('change', async () => {
        const perm = (json.permissions || []).find(x => x.id === parseInt(ch.dataset.pid, 10));
        if (!perm) return;
        const body = { user_id: perm.user_id, can_view: false, can_upload: false, can_manage: false };
        el.querySelectorAll(`input[data-pid="${ch.dataset.pid}"]`).forEach(c => { body[c.dataset.k] = c.checked; });
        await api(`/api/document-folders/${state.permissionsFolderId}/permissions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      });
    });
  }

  async function restoreFile(id) {
    await api(`/api/documents/${id}/restore`, { method: 'POST' });
    toast('File restored');
    await loadTrash();
  }

  async function restoreFolder(id) {
    await api(`/api/document-folders/${id}/restore`, { method: 'POST' });
    toast('Folder restored');
    await loadTrash();
  }

  async function permanentDeleteFile(id) {
    if (!confirm('Permanently delete? This cannot be undone.')) return;
    await api(`/api/documents/${id}/permanent`, { method: 'DELETE' });
    await loadTrash();
  }

  async function checkoutDocument(id) {
    await api(`/api/documents/${id}/checkout`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    toast('File checked out — you have exclusive edit access');
    if (state.previewFileId === id) await loadPreview(id);
    await loadBrowse(state.folderId);
  }

  async function checkinDocument(id) {
    await api(`/api/documents/${id}/checkin`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    toast('File checked in');
    if (state.previewFileId === id) await loadPreview(id);
    await loadBrowse(state.folderId);
  }

  async function forceUnlockDocument(id) {
    if (!confirm('Force unlock this file? The person who checked it out will lose edit access.')) return;
    await api(`/api/documents/${id}/force-unlock`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    toast('File unlocked');
    if (state.previewFileId === id) await loadPreview(id);
    await loadBrowse(state.folderId);
  }

  function selectableFileIds() {
    if (state.browseMode !== 'normal') return [];
    return filteredItems().files.map((f) => f.id);
  }

  function syncSelectAllCheckbox() {
    const ids = selectableFileIds();
    const allSelected = ids.length > 0 && ids.every((id) => state.bulkSelected.has(id));
    const someSelected = ids.some((id) => state.bulkSelected.has(id));
    ['docsSelectAll', 'docsSelectAllList'].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.checked = allSelected;
      el.indeterminate = !allSelected && someSelected;
      el.disabled = !ids.length;
    });
    document.getElementById('docsSelectAllWrap')?.classList.toggle('hidden', state.browseMode !== 'normal');
  }

  function toggleSelectAll(checked) {
    const ids = selectableFileIds();
    if (checked) ids.forEach((id) => state.bulkSelected.add(id));
    else ids.forEach((id) => state.bulkSelected.delete(id));
    updateBulkToolbar();
    syncSelectAllCheckbox();
    render();
  }

  function toggleBulkSelect(id, checked) {
    if (checked) state.bulkSelected.add(id);
    else state.bulkSelected.delete(id);
    updateBulkToolbar();
    syncSelectAllCheckbox();
  }

  function updateBulkToolbar() {
    const bar = document.getElementById('docsBulkBar');
    const count = document.getElementById('docsBulkCount');
    if (count) count.textContent = String(state.bulkSelected.size);
    if (bar) bar.classList.toggle('hidden', state.bulkSelected.size === 0);
  }

  async function bulkMove() {
    const ids = [...state.bulkSelected];
    if (!ids.length || state.folderId == null) {
      toast('Select files and open a destination folder');
      return;
    }
    await api('/api/documents/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'move', document_ids: ids, folder_id: state.folderId }),
    });
    state.bulkSelected.clear();
    updateBulkToolbar();
    toast('Files moved');
    await loadBrowse(state.folderId);
  }

  async function bulkDelete() {
    const ids = [...state.bulkSelected];
    if (!ids.length || !confirm(`Move ${ids.length} file(s) to recycle bin?`)) return;
    await api('/api/documents/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', document_ids: ids }),
    });
    state.bulkSelected.clear();
    updateBulkToolbar();
    toast('Files moved to trash');
    await loadBrowse(state.folderId);
  }

  function bulkDownloadZip() {
    const ids = [...state.bulkSelected];
    if (!ids.length) return;
    fetch('/api/documents/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'download_zip', document_ids: ids }),
      credentials: 'same-origin',
    }).then(async res => {
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        alert(j.error || 'Download failed');
        return;
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'documents.zip';
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  async function applyFolderTemplate() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/documents/folder-templates?project_id=${pid}`);
    const templates = json.templates || [];
    if (!templates.length) {
      toast('No folder templates available');
      return;
    }
    const names = templates.map((t, i) => `${i + 1}. ${t.name}${t.project_type ? ` (${t.project_type})` : ''}`).join('\n');
    const pick = prompt(`Apply folder template:\n${names}\n\nEnter number:`);
    const idx = parseInt(pick, 10) - 1;
    if (Number.isNaN(idx) || !templates[idx]) return;
    await api(`/api/documents/folder-templates/${templates[idx].id}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: pid }),
    });
    toast(`Template "${templates[idx].name}" applied`);
    await loadTree();
    await loadBrowse(state.folderId);
  }

  function downloadFile(id) {
    window.open(`/api/documents/${id}/download`, '_blank');
  }

  function openDocumentViewerFromList(id) {
    const doc = state.files.find(f => f.id === id);
    // Route spreadsheets/word docs to the built-in editors.
    if (doc && doc.editor_kind) {
      openInEditor(id, doc.editor_kind);
      return;
    }
    if (!doc || !isPreviewable(doc)) {
      downloadFile(id);
      return;
    }
    const pid = projectId();
    global.location.href = `/documents/viewer?doc_id=${id}${pid ? `&project_id=${pid}` : ''}`;
  }

  function openInEditor(id, kind) {
    const pid = projectId();
    const page = kind === 'sheet' ? '/documents/sheet' : '/documents/word';
    global.location.href = `${page}?doc_id=${id}${pid ? `&project_id=${pid}` : ''}`;
  }

  function newEditorDoc(kind) {
    const pid = projectId();
    const page = kind === 'sheet' ? '/documents/sheet' : '/documents/word';
    const parts = [];
    if (pid) parts.push(`project_id=${pid}`);
    if (state.folderId) parts.push(`folder_id=${state.folderId}`);
    global.location.href = parts.length ? `${page}?${parts.join('&')}` : page;
  }

  function downloadFolderZip(folderId) {
    const fid = folderId ?? state.folderId;
    if (!fid) {
      toast('Select a folder first');
      return;
    }
    window.location.href = `/api/document-folders/${fid}/download-zip`;
  }

  function updateDownloadZipButton() {
    const btn = document.getElementById('docsBtnDownloadZip');
    if (!btn) return;
    const show = state.browseMode === 'normal' && state.folderId != null;
    btn.classList.toggle('hidden', !show);
  }

  function formatShareLinkMeta(link) {
    const parts = [];
    if (link.revoked) parts.push('Revoked');
    if (link.has_password) parts.push('Password');
    if (link.allow_upload) parts.push('Uploads allowed');
    if (link.expires_at) parts.push(`Expires ${link.expires_at.slice(0, 10)}`);
    if (link.approval_status === 'pending') parts.push('Pending approval');
    parts.push(`${link.download_count || 0} downloads`);
    return parts.join(' · ');
  }

  function renderShareLinkRow(link) {
    const kind = link.target_type === 'folder' ? 'folder' : 'file';
    const revoked = link.revoked ? ' revoked' : '';
    const typeLabel = kind === 'folder'
      ? (link.allow_upload ? 'Request files' : 'Folder')
      : 'File';
    return `<div class="docs-share-link-row${revoked}" data-link-kind="${kind}" data-link-id="${link.id}">
      <div class="meta min-w-0">
        <div class="font-medium truncate">${esc(link.target_name || link.label || 'Link')}</div>
        <div class="text-xs text-zinc-500">${esc(typeLabel)} · ${esc(formatShareLinkMeta(link))}</div>
        <div class="text-[10px] text-zinc-600 truncate mt-0.5">${esc(link.share_url || '')}</div>
      </div>
      <div class="actions">
        ${link.share_url && !link.revoked ? `<button type="button" class="docs-btn docs-btn-secondary text-xs" data-copy-url="${esc(link.share_url)}">Copy</button>` : ''}
        ${!link.revoked ? `<button type="button" class="docs-btn docs-btn-secondary text-xs text-red-300" data-revoke-link="${kind}:${link.id}">Revoke</button>` : ''}
        ${link.approval_status === 'pending' ? `<button type="button" class="docs-btn docs-btn-secondary text-xs text-emerald-300" data-approve-link="${kind}:${link.id}">Approve</button>` : ''}
      </div>
    </div>`;
  }

  async function openShareLinksAdmin() {
    const pid = projectId();
    if (!pid) {
      toast('Select a project first');
      return;
    }
    const body = document.getElementById('docsShareLinksAdminBody');
    if (body) body.innerHTML = '<p class="text-zinc-500 text-sm">Loading…</p>';
    document.getElementById('docsShareLinksAdminDialog')?.showModal();
    try {
      const json = await api(`/api/documents/share-links/admin?project_id=${pid}`);
      const fileLinks = json.file_links || [];
      const folderLinks = json.folder_links || [];
      const all = [...fileLinks, ...folderLinks].sort((a, b) =>
        String(b.created_at || '').localeCompare(String(a.created_at || '')));
      if (!body) return;
      if (!all.length) {
        body.innerHTML = '<p class="text-zinc-500 text-sm">No share links yet. Right-click a file or folder to create one.</p>';
        return;
      }
      body.innerHTML = all.map(renderShareLinkRow).join('');
      body.querySelectorAll('[data-copy-url]').forEach(btn => {
        btn.addEventListener('click', async () => {
          await navigator.clipboard.writeText(btn.dataset.copyUrl || '');
          toast('Link copied');
        });
      });
      body.querySelectorAll('[data-revoke-link]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const [kind, id] = (btn.dataset.revokeLink || '').split(':');
          if (!kind || !id || !confirm('Revoke this share link? Recipients will no longer be able to use it.')) return;
          await api(`/api/documents/share-links/admin/${kind}/${id}`, { method: 'DELETE' });
          toast('Link revoked');
          await openShareLinksAdmin();
        });
      });
      body.querySelectorAll('[data-approve-link]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const [kind, id] = (btn.dataset.approveLink || '').split(':');
          if (!kind || !id) return;
          await api(`/api/documents/share-links/${kind}/${id}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approve: true }),
          });
          toast('Link approved');
          await openShareLinksAdmin();
        });
      });
    } catch (err) {
      if (body) body.innerHTML = `<p class="text-red-400 text-sm">${esc(err.message)}</p>`;
    }
  }

  async function deleteFile(id) {
    if (!confirm('Delete this file?')) return;
    await api(`/api/documents/${id}`, { method: 'DELETE' });
    if (state.previewFileId === id) closePreview();
    await loadBrowse(state.folderId);
  }

  async function deleteFolder(id) {
    if (!confirm('Delete this folder? It must be empty.')) return;
    await api(`/api/document-folders/${id}`, { method: 'DELETE' });
    await loadBrowse(state.folderId);
  }

  function startRename(kind, id) {
    state.renameTarget = { kind, id };
    let name = '';
    if (kind === 'file') name = state.files.find(f => f.id === id)?.name || '';
    else name = state.folders.find(f => f.id === id)?.name || '';
    document.getElementById('docsRenameInput').value = name;
    document.getElementById('docsRenameDialog')?.showModal();
  }

  async function saveRename() {
    const name = document.getElementById('docsRenameInput')?.value?.trim();
    if (!state.renameTarget || !name) return;
    if (state.renameTarget.kind === 'file') {
      await api(`/api/documents/${state.renameTarget.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
    } else {
      await api(`/api/document-folders/${state.renameTarget.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
    }
    document.getElementById('docsRenameDialog')?.close();
    await loadBrowse(state.folderId);
  }

  async function createFolder(parentId, label) {
    const name = prompt(label || 'Folder name');
    if (!name?.trim()) return;
    await api('/api/document-folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId(),
        parent_id: parentId,
        name: name.trim(),
      }),
    });
    await loadBrowse(state.folderId);
  }

  function newSubFolder() {
    createFolder(state.folderId, 'New subfolder name');
  }

  function newMainFolder() {
    createFolder(null, 'New main folder name');
  }

  function updateProjectLabel() {
    const el = document.getElementById('docsProjectName');
    if (el) el.textContent = projectName();
  }

  function bindUi() {
    applyIconSize(localStorage.getItem('casepm_docs_icon_size') || 'md');
    document.getElementById('docsIconSize')?.addEventListener('change', (e) => applyIconSize(e.target.value));
    ['docsSelectAll', 'docsSelectAllList'].forEach((id) => {
      document.getElementById(id)?.addEventListener('change', (e) => toggleSelectAll(e.target.checked));
    });
    document.getElementById('docsBtnUpload')?.addEventListener('click', () => {
      document.getElementById('docsFileInput')?.click();
    });
    document.getElementById('docsFileInput')?.addEventListener('change', async e => {
      try {
        const results = await uploadFiles(e.target.files);
        toast('Upload complete');
        const dup = results?.find(r => r?.duplicate_warning);
        if (dup?.duplicate_warning) toast(dup.duplicate_warning.message);
      } catch (err) {
        alert(err.message);
      }
      e.target.value = '';
    });
    document.getElementById('docsBtnNewFolder')?.addEventListener('click', newSubFolder);
    document.getElementById('docsBtnNewMainFolder')?.addEventListener('click', newMainFolder);
    document.getElementById('docsBtnNewSheet')?.addEventListener('click', () => newEditorDoc('sheet'));
    document.getElementById('docsBtnNewDoc')?.addEventListener('click', () => newEditorDoc('doc'));
    document.getElementById('docsBtnTrash')?.addEventListener('click', () => {
      if (state.browseMode === 'trash') exitTrash();
      else loadTrash();
    });
    document.getElementById('docsBtnShareLinks')?.addEventListener('click', openShareLinksAdmin);
    document.getElementById('docsBtnDownloadZip')?.addEventListener('click', () => downloadFolderZip());
    document.getElementById('docsBtnTemplate')?.addEventListener('click', applyFolderTemplate);
    document.getElementById('docsBulkMove')?.addEventListener('click', bulkMove);
    document.getElementById('docsBulkDelete')?.addEventListener('click', bulkDelete);
    document.getElementById('docsBulkZip')?.addEventListener('click', bulkDownloadZip);
    document.getElementById('docsBulkClear')?.addEventListener('click', () => {
      state.bulkSelected.clear();
      updateBulkToolbar();
      syncSelectAllCheckbox();
      render();
    });
    document.getElementById('docsShareLinksAdminClose')?.addEventListener('click', () => {
      document.getElementById('docsShareLinksAdminDialog')?.close();
    });
    document.getElementById('docsSearch')?.addEventListener('input', e => {
      state.search = e.target.value;
      if (state.searchAll) runGlobalSearch();
      else render();
    });
    document.getElementById('docsSearchAll')?.addEventListener('change', e => {
      state.searchAll = e.target.checked;
      if (state.searchAll) {
        if (state.search.trim()) runGlobalSearch();
        else toast('Type a search term to search all folders');
      } else {
        state.browseMode = 'normal';
        loadBrowse(state.folderId);
      }
    });
    document.getElementById('docsViewGrid')?.addEventListener('click', () => setViewMode('grid'));
    document.getElementById('docsViewList')?.addEventListener('click', () => setViewMode('list'));
    document.getElementById('docsShareCopy')?.addEventListener('click', async () => {
      const url = document.getElementById('docsShareUrl')?.value;
      if (url) {
        await navigator.clipboard.writeText(url);
        toast('Link copied');
      }
    });
    document.getElementById('docsShareClose')?.addEventListener('click', () => {
      document.getElementById('docsShareDialog')?.close();
    });
    document.getElementById('docsRenameSave')?.addEventListener('click', saveRename);
    document.getElementById('docsRenameCancel')?.addEventListener('click', () => {
      document.getElementById('docsRenameDialog')?.close();
    });
    document.getElementById('docsPreviewClose')?.addEventListener('click', closePreview);
    document.getElementById('docsFolderShareCopy')?.addEventListener('click', async () => {
      const url = document.getElementById('docsFolderShareUrl')?.value;
      if (url) { await navigator.clipboard.writeText(url); toast('Link copied'); }
    });
    document.getElementById('docsFolderShareClose')?.addEventListener('click', () => {
      document.getElementById('docsFolderShareDialog')?.close();
    });
    document.getElementById('docsPermClose')?.addEventListener('click', () => {
      document.getElementById('docsPermissionsDialog')?.close();
    });
    document.getElementById('docsPermAdd')?.addEventListener('click', async () => {
      const uid = document.getElementById('docsPermUser')?.value;
      if (!uid || !state.permissionsFolderId) return;
    await api(`/api/document-folders/${state.permissionsFolderId}/permissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: parseInt(uid, 10),
        can_view: true,
        can_upload: false,
        can_manage: false,
      }),
    });
      await refreshPermissionsList();
    });
    document.getElementById('docsVersionInput')?.addEventListener('change', async e => {
      const file = e.target.files?.[0];
      const docId = state.versionUploadId;
      e.target.value = '';
      if (!file || !docId) return;
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`/api/documents/${docId}/versions`, { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json();
      if (!res.ok) alert(json.error || 'Version upload failed');
      else {
        toast('New version uploaded');
        await loadPreview(docId, 'versions');
        await loadBrowse(state.folderId);
      }
    });

    const drop = document.getElementById('docsDropZone');
    if (drop) {
      ['dragenter', 'dragover'].forEach(ev => {
        drop.addEventListener(ev, e => {
          if (state.draggingFileId || state.draggingFolderId) return;
          e.preventDefault();
          drop.classList.add('drag-over');
        });
      });
      ['dragleave', 'drop'].forEach(ev => {
        drop.addEventListener(ev, e => {
          if (state.draggingFileId || state.draggingFolderId) return;
          e.preventDefault();
          drop.classList.remove('drag-over');
        });
      });
      drop.addEventListener('drop', async e => {
        if (state.draggingFileId || state.draggingFolderId) return;
        try {
          await uploadFiles(e.dataTransfer?.files);
          toast('Upload complete');
        } catch (err) {
          alert(err.message);
        }
      });
    }
  }

  async function reloadForProject() {
    updateProjectLabel();
    state.folderId = null;
    state.expandedFolders = new Set();
    state.selected = null;
    closePreview();
    const pid = projectId();
    if (!pid) {
      document.getElementById('docsEmpty')?.classList.remove('hidden');
      const empty = document.getElementById('docsEmpty');
      if (empty) empty.innerHTML = '<p class="text-zinc-500">Select a project in the header to browse documents.</p>';
      return;
    }
    await loadBrowse(null);
    openRoot();
  }

  async function init() {
    bindUi();
    global.onCasePmProjectChanged = () => reloadForProject();
    await reloadForProject();
  }

  global.CasePMDocs = {
    init,
    uploadFileAsShareLink,
    offerLinkInstead,
    LARGE_FILE_BYTES,
    loadBrowse,
    projectId,
  };

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('docsPage')) init();
  });
})(window);
