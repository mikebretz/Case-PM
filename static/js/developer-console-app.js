/**
 * Developer Console — tabs and program update management.
 */
(function (global) {
  'use strict';

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || res.statusText);
    return json;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function switchDevTab(tab) {
    document.querySelectorAll('[id^="dev-tab-content-"]').forEach((el) => el.classList.add('hidden'));
    const content = document.getElementById('dev-tab-content-' + tab);
    if (content) content.classList.remove('hidden');
    document.querySelectorAll('.dev-tab-btn').forEach((el) => el.classList.remove('active'));
    const activeTab = document.getElementById('dev-tab-' + tab);
    if (activeTab) activeTab.classList.add('active');
    if (tab === 'updates') loadUpdatesPanel();
    const url = new URL(window.location.href);
    url.searchParams.set('tab', tab);
    window.history.replaceState({}, '', url);
  }

  function typeLabel(type) {
    const map = {
      snapshot: 'Snapshot',
      install: 'Install',
      rollback: 'Rollback',
      git_pull: 'Git pull',
    };
    return map[type] || type || 'Event';
  }

  function typeBadgeClass(type) {
    const map = {
      snapshot: 'text-sky-400',
      install: 'text-emerald-400',
      rollback: 'text-amber-400',
      git_pull: 'text-violet-400',
    };
    return map[type] || 'text-zinc-400';
  }

  function renderUpdatesStatus(data) {
    const versionEl = document.getElementById('devUpdateVersion');
    const gitEl = document.getElementById('devUpdateGitInfo');
    const folderEl = document.getElementById('devSnapshotFolder');
    const countEl = document.getElementById('devSnapshotCount');
    const protectedEl = document.getElementById('devProtectedPaths');
    const gitPullBtn = document.getElementById('devGitPullBtn');
    const gitStatusEl = document.getElementById('devGitPullStatus');

    if (versionEl) versionEl.textContent = `v${data.version || '?'}`;
    if (folderEl) folderEl.value = data.snapshot_folder || '';
    if (countEl) countEl.textContent = String(data.snapshot_count ?? 0);

    const git = data.git || {};
    if (gitEl) {
      if (!git.available) {
        gitEl.textContent = 'Git not detected — use upload zip to install updates.';
      } else {
        const behind = git.behind ? ` · ${git.behind} commit(s) behind origin/main` : '';
        gitEl.textContent = `${git.branch || 'branch'} @ ${git.commit || '?'} — ${git.subject || ''}${behind}`;
      }
    }
    if (gitPullBtn) gitPullBtn.disabled = !git.available;
    if (gitStatusEl) {
      gitStatusEl.textContent = git.available
        ? (git.behind ? `${git.behind} update(s) available on GitHub` : 'Up to date with origin/main')
        : 'Git pull unavailable in this folder';
    }
    if (protectedEl) {
      protectedEl.textContent = (data.user_data_protected || ['instance/', 'uploads/']).join(', ');
    }
  }

  function renderSnapshots(snapshots) {
    const host = document.getElementById('devSnapshotList');
    if (!host) return;
    if (!snapshots?.length) {
      host.innerHTML = '<div class="text-sm text-zinc-500 py-6 text-center">No code snapshots yet. Save one before installing updates.</div>';
      return;
    }
    host.innerHTML = snapshots.map((s) => `
      <div class="flex flex-wrap justify-between items-center gap-3 py-3 border-b border-zinc-800 last:border-0 text-sm hover:bg-zinc-800/40 px-1 -mx-1 rounded-md">
        <div class="min-w-0 flex-1">
          <div class="font-medium text-white">${escapeHtml(s.label || s.filename)}</div>
          <div class="font-mono text-xs text-emerald-400/90 truncate">${escapeHtml(s.filename)}</div>
          <div class="text-xs text-zinc-500 mt-0.5">
            ${(s.size_bytes / 1024 / 1024).toFixed(2)} MB · ${escapeHtml(s.created_at_display || s.created_at)}
            ${s.git_commit ? ` · git ${escapeHtml(s.git_commit)}` : ''}
            ${s.file_count ? ` · ${s.file_count} files` : ''}
          </div>
          ${s.note ? `<div class="text-xs text-zinc-500 mt-1">${escapeHtml(s.note)}</div>` : ''}
        </div>
        <button type="button" class="dev-tool-btn !w-auto !h-9 text-xs"
                onclick="CasePMDeveloperConsole.restoreSnapshot(${JSON.stringify(s.filename)})">
          <i class="fa-solid fa-rotate-left text-amber-400"></i><span>Restore this version</span>
        </button>
      </div>`).join('');
  }

  function renderHistory(history) {
    const host = document.getElementById('devUpdateHistory');
    if (!host) return;
    if (!history?.length) {
      host.innerHTML = '<div class="text-sm text-zinc-500 py-4">No update history yet.</div>';
      return;
    }
    host.innerHTML = history.map((h) => `
      <div class="py-3 border-b border-zinc-800 last:border-0 text-sm">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs uppercase tracking-wide ${typeBadgeClass(h.type)}">${escapeHtml(typeLabel(h.type))}</span>
          <span class="font-medium text-white">${escapeHtml(h.label || h.type)}</span>
          ${h.status === 'failed' ? '<span class="text-xs text-red-400">failed</span>' : ''}
        </div>
        <div class="text-xs text-zinc-500 mt-1">
          ${escapeHtml(h.created_at_display || h.created_at || '')}
          ${h.actor ? ` · ${escapeHtml(h.actor)}` : ''}
          ${h.git_commit_after ? ` · git ${escapeHtml(h.git_commit_after)}` : ''}
        </div>
        ${h.note ? `<div class="text-xs text-zinc-500 mt-1">${escapeHtml(h.note)}</div>` : ''}
        ${h.snapshot_file ? `<div class="text-xs text-zinc-600 mt-1 font-mono">snapshot: ${escapeHtml(h.snapshot_file)}</div>` : ''}
      </div>`).join('');
  }

  async function loadUpdatesPanel() {
    const host = document.getElementById('devSnapshotList');
    if (host) host.innerHTML = '<div class="text-sm text-zinc-500 py-4">Loading…</div>';
    try {
      const data = await api('/api/developer/updates/status');
      renderUpdatesStatus(data);
      renderSnapshots(data.snapshots || []);
      renderHistory(data.history || []);
    } catch (err) {
      if (host) host.innerHTML = `<div class="text-sm text-red-400 py-4">${escapeHtml(err.message)}</div>`;
    }
  }

  async function saveSnapshotFolder() {
    const folder = document.getElementById('devSnapshotFolder')?.value?.trim();
    try {
      await api('/api/developer/updates/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snapshot_folder: folder }),
      });
      CasePMDialog?.alert('Snapshot folder saved.', 'success');
      await loadUpdatesPanel();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Could not save folder.', 'error');
    }
  }

  async function createSnapshot() {
    const label = document.getElementById('devSnapshotLabel')?.value?.trim() || 'Manual snapshot';
    const note = document.getElementById('devSnapshotNote')?.value?.trim() || '';
    const ok = await CasePMDialog?.confirm(
      'Save a snapshot of the current application code?\n\nUser data (database, uploads, settings) is NOT included — only program files.',
      { title: 'Save code snapshot', confirmLabel: 'Save snapshot' }
    );
    if (!ok) return;
    try {
      const json = await api('/api/developer/updates/snapshot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label, note }),
      });
      CasePMDialog?.alert(`Snapshot saved: ${json.result?.filename}`, 'success');
      document.getElementById('devSnapshotLabel').value = '';
      document.getElementById('devSnapshotNote').value = '';
      await loadUpdatesPanel();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Snapshot failed.', 'error');
    }
  }

  async function restoreSnapshot(filename) {
    const ok = await CasePMDialog?.confirm(
      `Restore application code from:\n${filename}\n\nA safety snapshot of the current code is created first.\n\nYour database, uploads, and program settings are NOT changed.\n\nRestart run.bat after restoring.`,
      { title: 'Restore code version', confirmLabel: 'Restore', danger: true }
    );
    if (!ok) return;
    try {
      const json = await api('/api/developer/updates/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename }),
      });
      const safety = json.result?.safety_snapshot;
      CasePMDialog?.alert(
        `Code restored from ${filename}.${safety ? `\n\nSafety copy: ${safety}` : ''}\n\nClose run.bat and restart it, then press Ctrl+F5 in your browser.`,
        'success'
      );
      await loadUpdatesPanel();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Restore failed.', 'error');
    }
  }

  async function installUpdateZip(input) {
    const file = input?.files?.[0];
    if (!file) return;
    const label = document.getElementById('devInstallLabel')?.value?.trim() || `Installed ${file.name}`;
    const note = document.getElementById('devInstallNote')?.value?.trim() || '';
    const ok = await CasePMDialog?.confirm(
      `Install update from ${file.name}?\n\nA safety snapshot is created first.\n\nUser data (instance/, uploads/) is never overwritten.`,
      { title: 'Install update', confirmLabel: 'Install' }
    );
    if (!ok) {
      input.value = '';
      return;
    }
    const form = new FormData();
    form.append('file', file);
    form.append('label', label);
    form.append('note', note);
    try {
      const res = await fetch('/api/developer/updates/install', {
        method: 'POST',
        credentials: 'same-origin',
        body: form,
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || res.statusText);
      CasePMDialog?.alert(
        `Update installed (${json.result?.files_applied || 0} files).\n\nSafety snapshot: ${json.result?.safety_snapshot || 'n/a'}\n\nRestart run.bat and hard-refresh your browser.`,
        'success'
      );
      input.value = '';
      document.getElementById('devInstallLabel').value = '';
      document.getElementById('devInstallNote').value = '';
      await loadUpdatesPanel();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Install failed.', 'error');
      input.value = '';
    }
  }

  async function gitPullUpdate() {
    const ok = await CasePMDialog?.confirm(
      'Pull latest code from origin/main?\n\nA safety snapshot is created first. User data is not touched.',
      { title: 'Git pull update', confirmLabel: 'Pull updates' }
    );
    if (!ok) return;
    const btn = document.getElementById('devGitPullBtn');
    if (btn) btn.disabled = true;
    try {
      const json = await api('/api/developer/updates/git-pull', { method: 'POST' });
      const after = json.result?.git_after;
      CasePMDialog?.alert(
        `Git pull complete.\n\nNow at: ${after?.commit || '?'} — ${after?.subject || ''}\n\nRestart run.bat and hard-refresh your browser.`,
        'success'
      );
      await loadUpdatesPanel();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Git pull failed.', 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function initDevTabs() {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab') || 'overview';
    switchDevTab(tab);
  }

  global.CasePMDeveloperConsole = {
    switchDevTab,
    loadUpdatesPanel,
    saveSnapshotFolder,
    createSnapshot,
    restoreSnapshot,
    installUpdateZip,
    gitPullUpdate,
    initDevTabs,
  };
})(window);
