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
  };

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
    const q = folderId != null ? `&folder_id=${folderId}` : '';
    const json = await api(`/api/documents/browse?project_id=${pid}${q}`);
    state.folders = json.folders || [];
    state.files = json.files || [];
    state.breadcrumbs = json.breadcrumbs || [];
    if (state.previewFileId && !state.files.some(f => f.id === state.previewFileId)) {
      closePreview();
    }
    render();
    loadTree();
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
      const chevron = hasChildren
        ? `<button type="button" class="docs-tree-chevron" data-toggle="${node.id}" aria-label="Toggle"><i class="fa-solid fa-chevron-${expanded ? 'down' : 'right'} text-[9px]"></i></button>`
        : '<span class="docs-tree-chevron placeholder"></span>';

      let html = `<div class="docs-tree-node" data-tree-folder="${node.id}">
        <div class="docs-tree-row${active}${sys}" data-folder-id="${node.id}" data-drop-folder="${node.id}">
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

    el.innerHTML = state.tree.map(n => renderNode(n, 0)).join('');

    el.querySelectorAll('[data-toggle]').forEach(btn => {
      btn.addEventListener('click', e => toggleFolderExpand(parseInt(btn.dataset.toggle, 10), e));
    });
    el.querySelectorAll('[data-folder-id]').forEach(row => {
      row.addEventListener('click', e => {
        if (e.target.closest('[data-toggle]')) return;
        openFolder(parseInt(row.dataset.folderId, 10));
      });
      bindFolderDropTarget(row);
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
    const folders = state.folders.filter(f => !q || f.name.toLowerCase().includes(q));
    const files = state.files.filter(f => !q || f.name.toLowerCase().includes(q));
    return { folders, files };
  }

  function selectItem(kind, id, locked, system) {
    state.selected = { kind, id, locked: !!locked, system: !!system };
    document.querySelectorAll('.docs-item.selected, .docs-table tr.selected').forEach(x => x.classList.remove('selected'));
    const sel = kind === 'folder'
      ? document.querySelector(`.docs-item[data-kind="folder"][data-id="${id}"], tr[data-kind="folder"][data-id="${id}"]`)
      : document.querySelector(`.docs-item[data-kind="file"][data-id="${id}"], tr[data-kind="file"][data-id="${id}"]`);
    sel?.classList.add('selected');
  }

  function renderGrid(folders, files) {
    const grid = document.getElementById('docsGrid');
    const table = document.getElementById('docsTable');
    const tableBody = document.getElementById('docsTableBody');
    if (!grid || !table || !tableBody) return;

    grid.classList.remove('hidden');
    table.classList.add('hidden');

    let html = '';
    folders.forEach(f => {
      const sel = state.selected?.kind === 'folder' && state.selected.id === f.id ? ' selected' : '';
      const lock = f.is_system ? '<span class="docs-item-badge">System</span>' : '';
      html += `<div class="docs-item folder${sel}" data-kind="folder" data-id="${f.id}" data-system="${f.is_system ? '1' : ''}" data-drop-folder="${f.id}">
        ${lock}
        <div class="docs-item-icon"><i class="fa-solid fa-folder"></i></div>
        <div class="docs-item-name">${esc(f.name)}</div>
        <div class="docs-item-meta">${f.file_count || 0} files</div>
      </div>`;
    });
    files.forEach(f => {
      const sel = state.selected?.kind === 'file' && state.selected.id === f.id ? ' selected' : '';
      const fi = fileIcon(f.name, f.mime_type);
      const lock = f.is_system_locked ? '<span class="docs-item-badge">Job</span>' : '';
      html += `<div class="docs-item file ${fi.cls}${sel}" data-kind="file" data-id="${f.id}" data-locked="${f.is_system_locked ? '1' : ''}" draggable="${f.is_system_locked ? 'false' : 'true'}">
        ${lock}
        <div class="docs-item-icon"><i class="fa-solid ${fi.icon}"></i></div>
        <div class="docs-item-name">${esc(f.name)}</div>
        <div class="docs-item-meta">${esc(f.size || '')}</div>
      </div>`;
    });
    grid.innerHTML = html;
    bindItemEvents(grid);
  }

  function renderList(folders, files) {
    const grid = document.getElementById('docsGrid');
    const table = document.getElementById('docsTable');
    const tableBody = document.getElementById('docsTableBody');
    if (!grid || !table || !tableBody) return;

    grid.classList.add('hidden');
    table.classList.remove('hidden');

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
      html += `<tr class="${sel}" data-kind="file" data-id="${f.id}" data-locked="${f.is_system_locked ? '1' : ''}" draggable="${f.is_system_locked ? 'false' : 'true'}">
        <td class="docs-row-icon ${fi.cls}"><i class="fa-solid ${fi.icon}"></i></td>
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
      return;
    }
    empty?.classList.add('hidden');
    gridWrap?.classList.remove('hidden');
    if (state.viewMode === 'list') renderList(folders, files);
    else renderGrid(folders, files);
  }

  function bindItemEvents(container) {
    container.querySelectorAll('[data-kind]').forEach(el => {
      el.addEventListener('click', e => {
        if (state.draggingFileId) return;
        const kind = el.dataset.kind;
        const id = parseInt(el.dataset.id, 10);
        if (e.detail === 2) {
          if (kind === 'folder') openFolder(id);
          else downloadFile(id);
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
      if (el.dataset.kind === 'file' && el.dataset.locked !== '1') bindFileDrag(el);
      if (el.dataset.kind === 'folder') bindFolderDropTarget(el);
    });
  }

  function bindFileDrag(el) {
    el.addEventListener('dragstart', e => {
      const id = parseInt(el.dataset.id, 10);
      state.draggingFileId = id;
      el.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', String(id));
    });
    el.addEventListener('dragend', () => {
      state.draggingFileId = null;
      el.classList.remove('dragging');
      clearDropHighlights();
    });
  }

  function bindFolderDropTarget(el) {
    const folderId = parseInt(el.dataset.dropFolder || el.dataset.folderId, 10);
    if (!folderId) return;
    el.addEventListener('dragover', e => {
      if (!state.draggingFileId) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      el.classList.add('drop-target');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drop-target'));
    el.addEventListener('drop', async e => {
      e.preventDefault();
      el.classList.remove('drop-target');
      const fileId = state.draggingFileId || parseInt(e.dataTransfer.getData('text/plain'), 10);
      if (!fileId) return;
      await moveFileToFolder(fileId, folderId);
    });
  }

  function clearDropHighlights() {
    document.querySelectorAll('.drop-target').forEach(x => x.classList.remove('drop-target'));
  }

  async function moveFileToFolder(fileId, folderId) {
    const file = state.files.find(f => f.id === fileId);
    if (!file || file.is_system_locked) return;
    if (file.folder_id === folderId) return;
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

  async function showPreview(fileId) {
    state.previewFileId = fileId;
    const panel = document.getElementById('docsPreviewPanel');
    panel?.classList.add('open');
    await loadPreview(fileId);
  }

  async function loadPreview(fileId) {
    const body = document.getElementById('docsPreviewBody');
    if (!body) return;
    try {
      const json = await api(`/api/documents/${fileId}`);
      const doc = json.document;
      state.previewDoc = doc;
      const kind = isPreviewable(doc);
      let media = '';
      if (kind === 'image') {
        media = `<img class="docs-preview-media" src="${esc(doc.file_url)}" alt="${esc(doc.name)}">`;
      } else if (kind === 'pdf') {
        media = `<iframe class="docs-preview-frame" src="${esc(doc.file_url)}" title="${esc(doc.name)}"></iframe>`;
      } else {
        const fi = fileIcon(doc.name, doc.mime_type);
        media = `<div class="text-center py-8"><i class="fa-solid ${fi.icon} text-5xl ${fi.cls} text-amber-400"></i><p class="text-sm text-zinc-400 mt-3">No preview for this file type</p></div>`;
      }
      body.innerHTML = `
        ${media}
        <h3 class="text-sm font-semibold text-white mt-3 break-words">${esc(doc.name)}</h3>
        <dl class="docs-preview-meta">
          <dt>Uploaded by</dt><dd>${esc(doc.uploaded_by_name || 'Unknown')}</dd>
          <dt>Uploaded</dt><dd>${esc(doc.created_at ? doc.created_at.slice(0, 16).replace('T', ' ') : '—')}</dd>
          <dt>Modified</dt><dd>${esc(doc.updated_at ? doc.updated_at.slice(0, 16).replace('T', ' ') : '—')}</dd>
          <dt>Size</dt><dd>${esc(doc.size || '—')}</dd>
          <dt>Type</dt><dd>${esc(doc.document_type || doc.mime_type || '—')}</dd>
          <dt>Folder</dt><dd>${esc(doc.folder_name || '—')}</dd>
          ${doc.is_system_locked ? '<dt>Status</dt><dd class="text-violet-300">Locked job file</dd>' : ''}
        </dl>
        <div class="docs-preview-actions">
          <button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewDownload"><i class="fa-solid fa-download"></i> Download</button>
          <button type="button" class="docs-btn docs-btn-secondary" id="docsPreviewShare"><i class="fa-solid fa-link"></i> Share</button>
        </div>`;
      document.getElementById('docsPreviewDownload')?.addEventListener('click', () => downloadFile(doc.id));
      document.getElementById('docsPreviewShare')?.addEventListener('click', () => createShareLink(doc.id));
    } catch (err) {
      body.innerHTML = `<p class="text-red-400 text-sm">${esc(err.message)}</p>`;
    }
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
    if (state.selected.kind === 'folder') {
      if (!state.selected.system) {
        items.push({ label: 'Rename', action: () => startRename('folder', state.selected.id) });
        items.push({ label: 'Delete', action: () => deleteFolder(state.selected.id), danger: true });
      }
      items.push({ label: 'Open', action: () => openFolder(state.selected.id) });
    } else {
      items.push({ label: 'Preview', action: () => showPreview(state.selected.id) });
      items.push({ label: 'Download', action: () => downloadFile(state.selected.id) });
      items.push({ label: 'Copy share link', action: () => createShareLink(state.selected.id) });
      items.push({ label: 'Rename', action: () => startRename('file', state.selected.id), disabled: state.selected.locked });
      items.push({ label: 'Delete', action: () => deleteFile(state.selected.id), danger: true, disabled: state.selected.locked });
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

  async function createShareLink(fileId) {
    const json = await api(`/api/documents/${fileId}/share-links`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expires_days: 30 }),
    });
    const url = json.share_link?.share_url || '';
    state.shareUrl = url;
    document.getElementById('docsShareUrl').value = url;
    document.getElementById('docsShareMeta').textContent = json.share_link?.expires_at
      ? `Expires ${json.share_link.expires_at.slice(0, 10)} · ${json.share_link.download_count || 0} downloads`
      : '';
    document.getElementById('docsShareDialog')?.showModal();
  }

  function downloadFile(id) {
    window.open(`/api/documents/${id}/download`, '_blank');
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
    document.getElementById('docsBtnUpload')?.addEventListener('click', () => {
      document.getElementById('docsFileInput')?.click();
    });
    document.getElementById('docsFileInput')?.addEventListener('change', async e => {
      try {
        await uploadFiles(e.target.files);
        toast('Upload complete');
      } catch (err) {
        alert(err.message);
      }
      e.target.value = '';
    });
    document.getElementById('docsBtnNewFolder')?.addEventListener('click', newSubFolder);
    document.getElementById('docsBtnNewMainFolder')?.addEventListener('click', newMainFolder);
    document.getElementById('docsSearch')?.addEventListener('input', e => {
      state.search = e.target.value;
      render();
    });
    document.getElementById('docsViewGrid')?.addEventListener('click', () => {
      state.viewMode = 'grid';
      document.getElementById('docsViewGrid')?.classList.add('active');
      document.getElementById('docsViewList')?.classList.remove('active');
      render();
    });
    document.getElementById('docsViewList')?.addEventListener('click', () => {
      state.viewMode = 'list';
      document.getElementById('docsViewList')?.classList.add('active');
      document.getElementById('docsViewGrid')?.classList.remove('active');
      render();
    });
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

    const drop = document.getElementById('docsDropZone');
    if (drop) {
      ['dragenter', 'dragover'].forEach(ev => {
        drop.addEventListener(ev, e => {
          if (state.draggingFileId) return;
          e.preventDefault();
          drop.classList.add('drag-over');
        });
      });
      ['dragleave', 'drop'].forEach(ev => {
        drop.addEventListener(ev, e => {
          if (state.draggingFileId) return;
          e.preventDefault();
          drop.classList.remove('drag-over');
        });
      });
      drop.addEventListener('drop', async e => {
        if (state.draggingFileId) return;
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
