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
  };

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const sel = document.getElementById('docsProjectSelect');
    if (sel?.value) return parseInt(sel.value, 10);
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
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
    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].includes(ext)) return 'fa-file-image file-img';
    if (ext === 'pdf' || (mime || '').includes('pdf')) return 'fa-file-pdf file-pdf';
    if (['doc', 'docx', 'txt', 'rtf'].includes(ext)) return 'fa-file-lines file-doc';
    if (['xls', 'xlsx', 'csv'].includes(ext)) return 'fa-file-excel file-doc';
    if (['zip', 'rar', '7z'].includes(ext)) return 'fa-file-zipper';
    return 'fa-file';
  }

  async function loadTree() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/document-folders/tree?project_id=${pid}`);
    state.tree = json.tree || [];
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
    state.selected = null;
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
    if (state.breadcrumbs.length) {
      loadBrowse(null);
      return;
    }
    const first = state.folders[0];
    if (first) openFolder(first.id);
  }

  function renderTree() {
    const el = document.getElementById('docsTree');
    if (!el) return;
    const renderNode = (node, depth) => {
      const pad = depth * 12;
      const active = state.folderId === node.id ? ' active' : '';
      const sys = node.is_system ? ' system' : '';
      let html = `<div class="docs-tree-item${active}${sys}" style="padding-left:${pad + 8}px" data-folder-id="${node.id}">
        <i class="fa-solid fa-folder${node.is_system ? '-tree' : ''}"></i>
        <span class="truncate">${esc(node.name)}</span>
      </div>`;
      (node.children || []).forEach(c => { html += renderNode(c, depth + 1); });
      return html;
    };
    el.innerHTML = state.tree.map(n => renderNode(n, 0)).join('');
    el.querySelectorAll('[data-folder-id]').forEach(row => {
      row.addEventListener('click', () => openFolder(parseInt(row.dataset.folderId, 10)));
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
        if (f === 'root') {
          const first = state.tree[0];
          openFolder(first ? first.id : null);
        } else loadBrowse(parseInt(f, 10));
      });
    });
  }

  function filteredItems() {
    const q = state.search.trim().toLowerCase();
    const folders = state.folders.filter(f => !q || f.name.toLowerCase().includes(q));
    const files = state.files.filter(f => !q || f.name.toLowerCase().includes(q));
    return { folders, files };
  }

  function render() {
    renderBreadcrumbs();
    const grid = document.getElementById('docsGrid');
    const empty = document.getElementById('docsEmpty');
    if (!grid) return;
    const { folders, files } = filteredItems();
    grid.classList.toggle('list-mode', state.viewMode === 'list');
    if (!folders.length && !files.length) {
      grid.innerHTML = '';
      empty?.classList.remove('hidden');
      return;
    }
    empty?.classList.add('hidden');
    let html = '';
    if (state.viewMode === 'list') {
      html += '<div class="docs-item" style="pointer-events:none;opacity:0.5;font-size:0.65rem;grid-template-columns:2rem 1fr 5rem 6rem 8rem auto"><span></span><span>Name</span><span>Type</span><span>Size</span><span>Modified</span><span></span></div>';
    }
    folders.forEach(f => {
      const sel = state.selected?.kind === 'folder' && state.selected.id === f.id ? ' selected' : '';
      const lock = f.is_system ? '<span class="docs-item-badge">System</span>' : '';
      html += `<div class="docs-item folder${sel}" data-kind="folder" data-id="${f.id}" data-system="${f.is_system ? '1' : ''}">
        ${lock}
        <div class="docs-item-icon"><i class="fa-solid fa-folder"></i></div>
        <div class="docs-item-name">${esc(f.name)}</div>
        <div class="docs-item-meta">${f.file_count || 0} files</div>
        ${state.viewMode === 'list' ? '<span class="text-xs text-zinc-500">Folder</span><span></span><span></span><span></span>' : ''}
      </div>`;
    });
    files.forEach(f => {
      const sel = state.selected?.kind === 'file' && state.selected.id === f.id ? ' selected' : '';
      const icon = fileIcon(f.name, f.mime_type);
      const lock = f.is_system_locked ? '<span class="docs-item-badge">Job</span>' : '';
      html += `<div class="docs-item file ${icon.split(' ').slice(1).join(' ')}${sel}" data-kind="file" data-id="${f.id}" data-locked="${f.is_system_locked ? '1' : ''}">
        ${lock}
        <div class="docs-item-icon"><i class="fa-solid ${icon.split(' ')[0]}"></i></div>
        <div class="docs-item-name">${esc(f.name)}</div>
        <div class="docs-item-meta">${esc(f.size || '')}</div>
        ${state.viewMode === 'list' ? `<span class="text-xs text-zinc-500">${esc(f.document_type || '')}</span><span class="text-xs">${esc(f.size || '')}</span><span class="text-xs text-zinc-500">${esc(f.uploaded || '')}</span><span></span>` : ''}
      </div>`;
    });
    grid.innerHTML = html;
    bindItemEvents(grid);
  }

  function bindItemEvents(grid) {
    grid.querySelectorAll('.docs-item[data-kind]').forEach(el => {
      el.addEventListener('click', e => {
        if (e.detail === 2) {
          if (el.dataset.kind === 'folder') openFolder(parseInt(el.dataset.id, 10));
          else downloadFile(parseInt(el.dataset.id, 10));
          return;
        }
        state.selected = { kind: el.dataset.kind, id: parseInt(el.dataset.id, 10), locked: el.dataset.locked === '1', system: el.dataset.system === '1' };
        grid.querySelectorAll('.docs-item').forEach(x => x.classList.remove('selected'));
        el.classList.add('selected');
      });
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        state.selected = { kind: el.dataset.kind, id: parseInt(el.dataset.id, 10), locked: el.dataset.locked === '1', system: el.dataset.system === '1' };
        showContextMenu(e.clientX, e.clientY);
      });
    });
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
    const close = () => menu.remove();
    setTimeout(() => document.addEventListener('click', close, { once: true }), 0);
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

  async function newFolder() {
    const name = prompt('New folder name');
    if (!name?.trim()) return;
    await api('/api/document-folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId(),
        parent_id: state.folderId,
        name: name.trim(),
      }),
    });
    await loadBrowse(state.folderId);
  }

  function bindUi() {
    document.getElementById('docsProjectSelect')?.addEventListener('change', () => {
      state.folderId = null;
      loadBrowse(null).then(openRoot);
    });
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
    document.getElementById('docsBtnNewFolder')?.addEventListener('click', newFolder);
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

    const drop = document.getElementById('docsDropZone');
    if (drop) {
      ['dragenter', 'dragover'].forEach(ev => {
        drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('drag-over'); });
      });
      ['dragleave', 'drop'].forEach(ev => {
        drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('drag-over'); });
      });
      drop.addEventListener('drop', async e => {
        try {
          await uploadFiles(e.dataTransfer?.files);
          toast('Upload complete');
        } catch (err) {
          alert(err.message);
        }
      });
    }
  }

  async function init() {
    bindUi();
    const pid = projectId();
    if (!pid) {
      document.getElementById('docsEmpty')?.classList.remove('hidden');
      document.getElementById('docsEmpty').innerHTML = '<p class="text-zinc-500">Select a project to browse documents.</p>';
      return;
    }
    await loadBrowse(null);
    openRoot();
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
    if (document.getElementById('docsGrid')) init();
  });
})(window);
