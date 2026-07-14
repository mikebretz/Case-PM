/**
 * Developer Console — tabs and program update management.
 */
(function (global) {
  'use strict';

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', ...opts });
    const contentType = res.headers.get('content-type') || '';
    const json = contentType.includes('application/json')
      ? await res.json().catch(() => ({}))
      : {};
    if (!res.ok) {
      const msg = json.error || res.statusText || 'Request failed';
      if (res.status === 404 && path.includes('/api/developer/presence')) {
        throw new Error('Presence API not found — restart the server (PULL-AND-RESTART-SERVER.bat), then hard-refresh this page.');
      }
      throw new Error(msg);
    }
    return json;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  let livePollTimer = null;
  let liveWatchSessionKey = null;
  let liveWatchPopup = null;
  let liveWatchPopupKey = null;
  const LIVE_POLL_MS = 1000;

  function stopLivePolling() {
    if (livePollTimer) {
      clearInterval(livePollTimer);
      livePollTimer = null;
    }
  }

  function showLiveUsersError(message) {
    const host = document.getElementById('devLiveUserList');
    const statusEl = document.getElementById('devLiveRefreshStatus');
    const countEl = document.getElementById('devLiveOnlineCount');
    const text = message || 'Could not load live users.';
    if (host) {
      host.innerHTML = `
        <div class="text-red-300/90 text-center py-6 text-xs space-y-2 px-3">
          <div class="font-medium">${escapeHtml(text)}</div>
          <div class="text-zinc-500">On the server PC, run <code class="text-zinc-400">PULL-AND-RESTART-SERVER.bat</code>, then hard-refresh (Ctrl+Shift+R).</div>
        </div>`;
    }
    if (countEl) countEl.textContent = '— online';
    if (statusEl) statusEl.textContent = text;
  }

  function showLiveWatchError(message) {
    const host = document.getElementById('devLiveWatchPanel');
    if (!host) return;
    host.innerHTML = `
      <div class="text-red-300/90 text-sm text-center py-16 px-4 space-y-2">
        <div>${escapeHtml(message || 'Could not load session.')}</div>
      </div>`;
  }

  function liveWatchPopupUrl(sessionKey) {
    return `/developer/live-watch?session=${encodeURIComponent(sessionKey)}`;
  }

  function openLiveWatchPopup(sessionKey) {
    if (!sessionKey) return false;
    const url = liveWatchPopupUrl(sessionKey);
    const winName = 'casepm-live-watch';
    try {
      if (liveWatchPopup && !liveWatchPopup.closed) {
        if (liveWatchPopupKey !== sessionKey) {
          liveWatchPopup.location.href = url;
        }
        liveWatchPopup.focus();
      } else {
        liveWatchPopup = window.open(
          url,
          winName,
          'popup=yes,width=1440,height=900,menubar=no,toolbar=no,location=no,status=no,scrollbars=yes,resizable=yes'
        );
        if (liveWatchPopup) liveWatchPopup.focus();
      }
      liveWatchPopupKey = sessionKey;
      return !!(liveWatchPopup && !liveWatchPopup.closed);
    } catch (_) {
      return false;
    }
  }

  function liveThumbUrl(sessionKey) {
    return `/api/developer/presence/thumbnail/${encodeURIComponent(sessionKey)}?t=${Date.now()}`;
  }

  function formatSeenAgo(iso) {
    if (!iso) return '—';
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return iso;
    const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (sec < 10) return 'just now';
    if (sec < 60) return `${sec}s ago`;
    const min = Math.floor(sec / 60);
    return `${min}m ago`;
  }

  function stableSessionSort(sessions) {
    return [...(sessions || [])].sort((a, b) => {
      if (!!a.online !== !!b.online) return a.online ? -1 : 1;
      const an = (a.user_name || a.user_email || '').toLowerCase();
      const bn = (b.user_name || b.user_email || '').toLowerCase();
      if (an !== bn) return an.localeCompare(bn);
      return String(a.session_key || '').localeCompare(String(b.session_key || ''));
    });
  }

  function liveSessionRowHtml(s) {
    const online = !!s.online;
    const active = liveWatchSessionKey === s.session_key;
    const sub = [s.page_module, s.project_name, s.active_tab].filter(Boolean).join(' · ');
    return `
      <div class="dev-live-user ${active ? 'active' : ''}" data-session-key="${escapeHtml(s.session_key)}">
        <span class="dev-live-dot ${online ? 'online' : 'offline'}"></span>
        <div class="min-w-0 flex-1">
          <div class="font-medium text-white truncate dev-live-name">${escapeHtml(s.user_name || s.user_email || 'User')}</div>
          <div class="text-[10px] text-zinc-500 truncate dev-live-meta">${escapeHtml(s.user_role || '')} · ${escapeHtml(formatSeenAgo(s.last_seen_at))}</div>
          <div class="text-[10px] text-zinc-400 truncate mt-0.5 dev-live-sub">${escapeHtml(sub || s.page_title || (online ? 'Online' : 'Recently active'))}</div>
        </div>
      </div>`;
  }

  function patchLiveSessionRow(el, s) {
    if (!el) return;
    el.classList.toggle('active', liveWatchSessionKey === s.session_key);
    const dot = el.querySelector('.dev-live-dot');
    if (dot) dot.className = `dev-live-dot ${s.online ? 'online' : 'offline'}`;
    const sub = [s.page_module, s.project_name, s.active_tab].filter(Boolean).join(' · ');
    const meta = el.querySelector('.dev-live-meta');
    if (meta) meta.textContent = `${s.user_role || ''} · ${formatSeenAgo(s.last_seen_at)}`;
    const subEl = el.querySelector('.dev-live-sub');
    if (subEl) subEl.textContent = sub || s.page_title || (s.online ? 'Online' : 'Recently active');
  }

  function bindLiveUserListClicks() {
    const host = document.getElementById('devLiveUserList');
    if (!host || host.dataset.clickBound) return;
    host.dataset.clickBound = '1';
    host.addEventListener('click', (ev) => {
      const row = ev.target.closest('.dev-live-user');
      if (!row || !row.dataset.sessionKey) return;
      watchLiveSession(row.dataset.sessionKey);
    });
  }

  function bindLiveWatchPanelClicks() {
    const panel = document.getElementById('devLiveWatchPanel');
    if (!panel || panel.dataset.clickBound) return;
    panel.dataset.clickBound = '1';
    panel.addEventListener('click', (ev) => {
      const trigger = ev.target.closest('[data-live-open-popup]');
      if (!trigger) return;
      const key = trigger.dataset.sessionKey
        || trigger.closest('[data-session-key]')?.dataset.sessionKey;
      if (key) openLiveWatchPopup(key);
    });
  }

  function renderLiveSessionList(sessions) {
    const host = document.getElementById('devLiveUserList');
    if (!host) return;
    const sorted = stableSessionSort(sessions);
    if (!sorted.length) {
      host.dataset.sessionKeys = '';
      host.innerHTML = `
        <div class="text-zinc-500 text-center py-6 text-xs space-y-2 px-2">
          <div>No active sessions detected.</div>
          <div class="text-zinc-600">Other users must be logged in on a page that has been refreshed after the latest server update. Heartbeats send every ~10s.</div>
        </div>`;
      return;
    }
    const keys = sorted.map((s) => s.session_key).join('\n');
    const prevKeys = host.dataset.sessionKeys || '';
    if (keys === prevKeys) {
      sorted.forEach((s) => {
        const el = host.querySelector(`.dev-live-user[data-session-key="${CSS.escape(String(s.session_key))}"]`);
        patchLiveSessionRow(el, s);
      });
      return;
    }
    const scrollTop = host.scrollTop;
    host.dataset.sessionKeys = keys;
    host.innerHTML = sorted.map(liveSessionRowHtml).join('');
    host.scrollTop = scrollTop;
  }

  function renderLiveWatchPanel(session, forceFull) {
    const host = document.getElementById('devLiveWatchPanel');
    if (!host || !session) return;

    const shell = document.getElementById('devLiveWatchShell');
    if (!forceFull && shell && shell.dataset.sessionKey === session.session_key) {
      const onlineEl = document.getElementById('devLiveWatchOnline');
      const seenEl = document.getElementById('devLiveWatchSeen');
      const activityEl = document.getElementById('devLiveWatchActivity');
      const lastEl = document.getElementById('devLiveWatchLastAction');
      const pageTitleEl = document.getElementById('devLiveWatchPageTitle');
      const pagePathEl = document.getElementById('devLiveWatchPagePath');
      const projectEl = document.getElementById('devLiveWatchProject');
      const tabEl = document.getElementById('devLiveWatchTab');
      const scrollEl = document.getElementById('devLiveWatchScroll');
      const headingsEl = document.getElementById('devLiveWatchHeadings');
      const modalsEl = document.getElementById('devLiveWatchModals');
      const selectedEl = document.getElementById('devLiveWatchSelected');
      const img = document.getElementById('devLiveThumb');
      if (onlineEl) {
        onlineEl.textContent = session.online ? '● Online' : '○ Idle';
        onlineEl.className = session.online ? 'text-emerald-400' : 'text-zinc-500';
      }
      if (seenEl) seenEl.textContent = 'Seen ' + formatSeenAgo(session.last_seen_at);
      if (activityEl) activityEl.textContent = session.activity_summary || '—';
      if (lastEl) {
        lastEl.innerHTML = session.last_action
          ? `Last: ${escapeHtml(session.last_action)} <span class="text-zinc-600">(${escapeHtml(formatSeenAgo(session.last_action_at))})</span>`
          : '';
      }
      if (pageTitleEl) pageTitleEl.textContent = session.page_title || '—';
      if (pagePathEl) pagePathEl.textContent = session.page_path || (session.view_state && session.view_state.url) || '';
      if (projectEl) projectEl.textContent = session.project_name || '—';
      if (tabEl) tabEl.textContent = session.active_tab || '—';
      if (scrollEl) scrollEl.textContent = session.scroll_pct != null ? session.scroll_pct + '%' : '—';
      if (headingsEl) {
        const headings = (session.view_state && session.view_state.headings) || [];
        headingsEl.innerHTML = headings.length
          ? headings.map((h) => `<li>${escapeHtml(h)}</li>`).join('')
          : '<li class="text-zinc-600">—</li>';
      }
      if (modalsEl) {
        const modals = (session.view_state && session.view_state.open_modals) || [];
        modalsEl.innerHTML = modals.length
          ? modals.map((m) => `<span class="inline-block px-2 py-0.5 bg-amber-950 text-amber-300 rounded text-xs mr-1">${escapeHtml(m)}</span>`).join('')
          : '<span class="text-zinc-600 text-xs">None open</span>';
      }
      if (selectedEl) {
        const selected = (session.view_state && session.view_state.selected) || [];
        selectedEl.innerHTML = selected.length
          ? selected.map((s) => `<span class="inline-block px-2 py-0.5 bg-zinc-800 text-zinc-300 rounded text-xs mr-1">${escapeHtml(s)}</span>`).join('')
          : '<span class="text-zinc-600 text-xs">—</span>';
      }
      if (img && session.has_thumbnail) {
        img.src = liveThumbUrl(session.session_key);
      } else if (session.has_thumbnail && !img) {
        renderLiveWatchPanel(session, true);
        return;
      }
      return;
    }

    const vs = session.view_state || {};
    const headings = (vs.headings || []).map((h) => `<li>${escapeHtml(h)}</li>`).join('') || '<li class="text-zinc-600">—</li>';
    const modals = (vs.open_modals || []).length
      ? vs.open_modals.map((m) => `<span class="inline-block px-2 py-0.5 bg-amber-950 text-amber-300 rounded text-xs mr-1">${escapeHtml(m)}</span>`).join('')
      : '<span class="text-zinc-600 text-xs">None open</span>';
    const selected = (vs.selected || []).length
      ? vs.selected.map((s) => `<span class="inline-block px-2 py-0.5 bg-zinc-800 text-zinc-300 rounded text-xs mr-1">${escapeHtml(s)}</span>`).join('')
      : '<span class="text-zinc-600 text-xs">—</span>';
    const thumbUrl = session.has_thumbnail ? liveThumbUrl(session.session_key) : '';
    const sk = escapeHtml(session.session_key);
    host.innerHTML = `
      <div id="devLiveWatchShell" data-session-key="${sk}">
      <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <div class="text-lg font-semibold text-white">${escapeHtml(session.user_name || '')}</div>
          <div class="text-xs text-zinc-500">${escapeHtml(session.user_email || '')} · ${escapeHtml(session.user_role || '')}</div>
        </div>
        <div class="flex flex-col items-end gap-2">
          <button type="button" class="dev-tool-btn !w-auto !py-1.5 !px-3 text-xs" data-live-open-popup data-session-key="${sk}">
            <i class="fa-solid fa-up-right-from-square text-sky-400"></i><span>Open full screen window</span>
          </button>
          <div class="text-[10px] text-zinc-500">Optional — larger view in a new window</div>
          <div class="text-right text-xs">
            <div id="devLiveWatchOnline" class="${session.online ? 'text-emerald-400' : 'text-zinc-500'}">${session.online ? '● Online' : '○ Idle'}</div>
            <div id="devLiveWatchSeen" class="text-zinc-500">Seen ${escapeHtml(formatSeenAgo(session.last_seen_at))}</div>
          </div>
        </div>
      </div>
      <div class="dev-live-screen mb-4">
        ${thumbUrl
          ? `<img src="${thumbUrl}" alt="Live viewport" id="devLiveThumb">`
          : '<div class="dev-live-screen-placeholder text-xs p-6 text-center">Viewport snapshot loading — captures refresh every ~5s from their browser.</div>'}
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm mb-3">
        <div class="bg-zinc-900 border border-zinc-800 rounded-md p-3">
          <div class="text-[10px] uppercase text-zinc-500 mb-1">Page</div>
          <div id="devLiveWatchPageTitle" class="text-white font-medium">${escapeHtml(session.page_title || '—')}</div>
          <div id="devLiveWatchPagePath" class="text-xs text-zinc-500 font-mono mt-1 break-all">${escapeHtml(session.page_path || vs.url || '')}</div>
        </div>
        <div class="bg-zinc-900 border border-zinc-800 rounded-md p-3">
          <div class="text-[10px] uppercase text-zinc-500 mb-1">Context</div>
          <div class="text-zinc-300"><span class="text-zinc-500">Project:</span> <span id="devLiveWatchProject">${escapeHtml(session.project_name || '—')}</span></div>
          <div class="text-zinc-300"><span class="text-zinc-500">Tab:</span> <span id="devLiveWatchTab">${escapeHtml(session.active_tab || '—')}</span></div>
          <div class="text-zinc-300"><span class="text-zinc-500">Scroll:</span> <span id="devLiveWatchScroll">${session.scroll_pct != null ? session.scroll_pct + '%' : '—'}</span></div>
        </div>
      </div>
      <div class="bg-zinc-900 border border-zinc-800 rounded-md p-3 mb-3">
        <div class="text-[10px] uppercase text-zinc-500 mb-1">Activity</div>
        <div id="devLiveWatchActivity" class="text-sm text-amber-200/90">${escapeHtml(session.activity_summary || '—')}</div>
        <div id="devLiveWatchLastAction" class="text-xs text-zinc-500 mt-1">${session.last_action ? `Last: ${escapeHtml(session.last_action)} <span class="text-zinc-600">(${escapeHtml(formatSeenAgo(session.last_action_at))})</span>` : ''}</div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        <div>
          <div class="text-[10px] uppercase text-zinc-500 mb-1">Visible headings</div>
          <ul id="devLiveWatchHeadings" class="list-disc pl-4 text-zinc-400 space-y-0.5">${headings}</ul>
        </div>
        <div>
          <div class="text-[10px] uppercase text-zinc-500 mb-1">Open modals</div>
          <div id="devLiveWatchModals" class="mb-2">${modals}</div>
          <div class="text-[10px] uppercase text-zinc-500 mb-1">Selections</div>
          <div id="devLiveWatchSelected">${selected}</div>
        </div>
      </div>
      </div>
    `;
  }

  async function refreshLiveUsers() {
    const statusEl = document.getElementById('devLiveRefreshStatus');
    const countEl = document.getElementById('devLiveOnlineCount');
    try {
      const data = await api('/api/developer/presence');
      renderLiveSessionList(data.sessions || []);
      if (countEl) {
        const online = data.online_count || 0;
        const total = data.session_count || (data.sessions || []).length;
        countEl.textContent = `${online} online · ${total} session${total === 1 ? '' : 's'}`;
      }
      if (statusEl) statusEl.textContent = `Live · ${new Date().toLocaleTimeString()}`;
      if (liveWatchSessionKey) {
        const detail = await api(`/api/developer/presence/session/${encodeURIComponent(liveWatchSessionKey)}`);
        if (detail.session) renderLiveWatchPanel(detail.session, false);
      }
    } catch (err) {
      showLiveUsersError(err.message || 'Refresh failed');
    }
  }

  function watchLiveSession(sessionKey) {
    if (!sessionKey) return;
    liveWatchSessionKey = sessionKey;
    document.querySelectorAll('.dev-live-user').forEach((el) => {
      el.classList.toggle('active', el.dataset.sessionKey === sessionKey);
    });
    const panel = document.getElementById('devLiveWatchPanel');
    if (panel) {
      panel.innerHTML = '<div class="text-zinc-500 text-sm text-center py-16">Loading session…</div>';
    }
    api(`/api/developer/presence/session/${encodeURIComponent(sessionKey)}`)
      .then((detail) => {
        if (detail.session) {
          renderLiveWatchPanel(detail.session, true);
        } else {
          showLiveWatchError('Session not found.');
        }
      })
      .catch((err) => {
        showLiveWatchError(err.message || 'Could not load session.');
      });
  }

  function loadLiveUsersPanel() {
    stopLivePolling();
    liveWatchSessionKey = null;
    bindLiveUserListClicks();
    bindLiveWatchPanelClicks();
    const list = document.getElementById('devLiveUserList');
    if (list) list.dataset.sessionKeys = '';
    const panel = document.getElementById('devLiveWatchPanel');
    if (panel) {
      panel.innerHTML = '<div class="text-zinc-500 text-sm text-center py-16">Select a session on the left to watch their screen and activity.</div>';
    }
    refreshLiveUsers();
    livePollTimer = setInterval(refreshLiveUsers, LIVE_POLL_MS);
  }

  function switchDevTab(tab) {
    if (tab !== 'live') stopLivePolling();
    document.querySelectorAll('[id^="dev-tab-content-"]').forEach((el) => el.classList.add('hidden'));
    const content = document.getElementById('dev-tab-content-' + tab);
    if (content) content.classList.remove('hidden');
    document.querySelectorAll('.dev-tab-btn').forEach((el) => el.classList.remove('active'));
    const activeTab = document.getElementById('dev-tab-' + tab);
    if (activeTab) activeTab.classList.add('active');
    if (tab === 'updates') loadUpdatesPanel();
    if (tab === 'tools') loadMaintenancePanel();
    if (tab === 'live') loadLiveUsersPanel();
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
    const restartEl = document.getElementById('devRestartBanner');

    if (versionEl) {
      const running = data.running_build || '?';
      versionEl.textContent = data.restart_required
        ? `v${data.version || '?'} · running ${running}`
        : `v${data.version || '?'} · ${running}`;
    }
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
    if (restartEl) {
      if (data.restart_required) {
        restartEl.classList.remove('hidden');
        restartEl.textContent =
          `Server is still running build ${data.running_build || '?'}. ` +
          `Disk has ${git.commit || '?'}. Close RUN-AS-SERVER.bat and run PULL-AND-RESTART-SERVER.bat ` +
          `(or restart run.bat on this PC only).`;
      } else {
        restartEl.classList.add('hidden');
        restartEl.textContent = '';
      }
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
        `Git pull complete.\n\nNow at: ${after?.commit || '?'} — ${after?.subject || ''}\n\n` +
          'RESTART REQUIRED for remote users:\n' +
          '• Server PC: run PULL-AND-RESTART-SERVER.bat\n' +
          '• Or close RUN-AS-SERVER.bat and open it again\n' +
          '• Remote PCs: Ctrl+Shift+R — footer build id must change',
        'success'
      );
      await loadUpdatesPanel();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Git pull failed.', 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function clearAllProgramData() {
    const ok = await CasePMDialog?.confirm(
      'This permanently deletes all projects, users, documents, uploads, and settings.\n\nA safety backup is created first, then the program is reset to a fresh install with the default admin account.',
      { title: 'Clear all program data', confirmLabel: 'Continue', danger: true }
    );
    if (!ok) return;
    const typed = await CasePMDialog?.prompt(
      'Type DELETE ALL to confirm clearing everything.',
      { title: 'Final confirmation', defaultValue: '', submitLabel: 'Clear everything', label: 'Confirmation text' }
    );
    if ((typed || '').trim().toUpperCase() !== 'DELETE ALL') {
      CasePMDialog?.alert('Clear cancelled — confirmation text did not match.', 'info');
      return;
    }
    try {
      const json = await api('/api/developer/maintenance/clear-all-program', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: 'DELETE ALL' }),
      });
      const safety = json.result?.safety_backup;
      const login = json.default_login || { email: 'admin@casepm.local', password: 'admin123' };
      await CasePMDialog?.alert(
        `All program data has been cleared.${safety ? `\n\nSafety backup: ${safety}` : ''}\n\nDefault login:\n${login.email}\n${login.password}\n\nYou will now be signed out.`,
        'success'
      );
      window.location.href = '/logout?next=/login';
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Clear failed.', 'error');
    }
  }

  let maintCatalog = null;

  function maintScopeAll() {
    return document.getElementById('devMaintScopeAll')?.checked !== false;
  }

  function selectedMaintProjectIds() {
    const boxes = document.querySelectorAll('.dev-maint-project-cb:checked');
    return Array.from(boxes).map((el) => parseInt(el.value, 10)).filter((n) => !Number.isNaN(n));
  }

  function updateMaintScopeSummary() {
    const el = document.getElementById('devMaintScopeSummary');
    if (!el) return;
    if (maintScopeAll()) {
      el.textContent = 'All projects — every clear action applies program-wide for the selected module.';
      return;
    }
    const ids = selectedMaintProjectIds();
    if (!ids.length) {
      el.textContent = 'No projects selected — pick one or more jobs below.';
      return;
    }
    const labels = ids.map((id) => {
      const p = (maintCatalog?.projects || []).find((row) => row.id === id);
      return p?.label || `Project ${id}`;
    });
    el.textContent = `Selected: ${labels.join('; ')}`;
  }

  function onMaintScopeChange() {
    const list = document.getElementById('devMaintProjectList');
    const all = maintScopeAll();
    if (list) list.classList.toggle('hidden', all);
    updateMaintScopeSummary();
  }

  function renderMaintProjectList(projects) {
    const host = document.getElementById('devMaintProjectList');
    if (!host) return;
    if (!projects?.length) {
      host.innerHTML = '<div class="text-sm text-zinc-500 py-4 text-center">No projects in the database.</div>';
      return;
    }
    host.innerHTML = projects.map((p) => `
      <label class="dev-maint-project cursor-pointer">
        <input type="checkbox" class="dev-maint-project-cb accent-red-600" value="${p.id}" onchange="CasePMDeveloperConsole.updateMaintScopeSummary()">
        <span class="text-zinc-200 truncate">${escapeHtml(p.label)}</span>
        ${p.status ? `<span class="text-xs text-zinc-500 ml-auto flex-shrink-0">${escapeHtml(p.status)}</span>` : ''}
      </label>`).join('');
  }

  function renderMaintModuleGrid(modules) {
    const host = document.getElementById('devMaintModuleGrid');
    if (!host) return;
    host.innerHTML = (modules || []).map((m) => `
      <div class="dev-maint-module ${m.danger ? 'danger' : ''}">
        <div class="flex items-start gap-2">
          <i class="fa-solid ${escapeHtml(m.icon || 'fa-database')} ${escapeHtml(m.color || 'text-zinc-400')} w-5 mt-0.5"></i>
          <div class="min-w-0 flex-1">
            <div class="font-medium text-sm text-white">${escapeHtml(m.label)}</div>
            <div class="text-xs text-zinc-500 mt-0.5">${escapeHtml(m.description)}</div>
            ${m.scope === 'global' ? '<div class="text-[10px] uppercase tracking-wide text-amber-500/90 mt-1">Program-wide</div>' : ''}
          </div>
        </div>
        <button type="button" class="dev-maint-clear-btn dev-tool-btn danger !w-full text-xs mt-1"
                data-module-key="${escapeHtml(m.key)}"
                data-module-label="${escapeHtml(m.label)}"
                data-module-danger="${m.danger ? '1' : '0'}">
          <i class="fa-solid fa-eraser"></i><span>Clear ${escapeHtml(m.label)}</span>
        </button>
      </div>`).join('');
    host.querySelectorAll('.dev-maint-clear-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        clearModuleData(
          btn.dataset.moduleKey,
          btn.dataset.moduleLabel,
          btn.dataset.moduleDanger === '1'
        );
      });
    });
  }

  async function loadMaintenancePanel() {
    const grid = document.getElementById('devMaintModuleGrid');
    if (grid) grid.innerHTML = '<div class="text-sm text-zinc-500 py-6 text-center col-span-full">Loading modules…</div>';
    try {
      const data = await api('/api/developer/maintenance/catalog');
      maintCatalog = data;
      renderMaintProjectList(data.projects || []);
      renderMaintModuleGrid(data.modules || []);
      onMaintScopeChange();
    } catch (err) {
      if (grid) grid.innerHTML = `<div class="text-sm text-red-400 py-6 text-center col-span-full">${escapeHtml(err.message)}</div>`;
    }
  }

  async function clearModuleData(moduleKey, moduleLabel, isDanger) {
    if (!global.CasePMDialog) {
      alert('Dialog module not loaded — refresh the page and try again.');
      return;
    }
    const allProjects = maintScopeAll();
    const projectIds = allProjects ? [] : selectedMaintProjectIds();
    if (!allProjects && !projectIds.length) {
      CasePMDialog.alert('Select at least one project, or choose All Projects.', 'info');
      return;
    }
    const scopeText = allProjects ? 'ALL projects' : `${projectIds.length} selected project(s)`;
    const ok = await CasePMDialog.confirm(
      `Clear ${moduleLabel} data for ${scopeText}?\n\nThis permanently deletes database records and uploaded files for this module. This cannot be undone.`,
      { title: `Clear ${moduleLabel}`, confirmLabel: 'Continue', danger: true }
    );
    if (!ok) return;
    const typed = await CasePMDialog.prompt(
      'Type CLEAR to confirm.',
      { title: 'Confirm clear', defaultValue: '', submitLabel: 'Clear data', label: 'Confirmation text' }
    );
    if ((typed || '').trim().toUpperCase() !== 'CLEAR') {
      CasePMDialog.alert('Clear cancelled — confirmation text did not match.', 'info');
      return;
    }
    try {
      const json = await api('/api/developer/maintenance/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          module: moduleKey,
          all_projects: allProjects,
          project_ids: projectIds,
          confirm: 'CLEAR',
        }),
      });
      const stats = json.result && typeof json.result === 'object'
        ? Object.entries(json.result).map(([k, v]) => `${k}: ${v}`).join('\n')
        : '';
      if (json.result?.skipped) {
        CasePMDialog.alert(
          `Nothing was cleared for ${moduleLabel}.\n\n${json.result.reason || 'No matching project scope.'}`,
          'warning'
        );
        return;
      }
      const deletedTotal = json.result && typeof json.result === 'object'
        ? Object.values(json.result).reduce((sum, v) => sum + (typeof v === 'number' ? v : 0), 0)
        : 0;
      if (!deletedTotal && !json.result?.skipped) {
        CasePMDialog.alert(
          `${moduleLabel}: no records were found for ${scopeText}.${stats ? `\n\n${stats}` : ''}`,
          'info'
        );
        return;
      }
      CasePMDialog.alert(
        `${moduleLabel} data cleared for ${scopeText}.${stats ? `\n\n${stats}` : ''}`,
        'success'
      );
      if (moduleKey === 'projects' || moduleKey === 'change_orders') await loadMaintenancePanel();
    } catch (err) {
      CasePMDialog.alert(err.message || 'Clear failed.', 'error');
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
    loadMaintenancePanel,
    loadLiveUsersPanel,
    watchLiveSession,
    openLiveWatchPopup,
    refreshLiveUsers,
    onMaintScopeChange,
    updateMaintScopeSummary,
    clearModuleData,
    clearAllProgramData,
    saveSnapshotFolder,
    createSnapshot,
    restoreSnapshot,
    installUpdateZip,
    gitPullUpdate,
    initDevTabs,
  };
})(window);
