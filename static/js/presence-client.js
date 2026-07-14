/**
 * Case PM — live presence heartbeats (all authenticated pages).
 * Developers can watch online users from Developer Console → Live Users.
 */
(function (global) {
  'use strict';

  const STORAGE_KEY = 'casepm_presence_session_key';
  const HEARTBEAT_MS = 10000;
  const THUMB_MS = 20000;
  let lastAction = '';
  let lastActionAt = null;
  let thumbTimer = null;
  let heartbeatTimer = null;
  let html2canvasLoading = null;
  let started = false;

  function currentUserId() {
    if (document.body && document.body.dataset.currentUserId) {
      return document.body.dataset.currentUserId;
    }
    if (document.documentElement && document.documentElement.dataset.currentUserId) {
      return document.documentElement.dataset.currentUserId;
    }
    const prof = global.CASEPM_CURRENT_USER;
    if (prof && prof.id != null && prof.id !== '') return String(prof.id);
    return '';
  }

  function csrfToken() {
    if (global.CasePMSecurity && typeof global.CasePMSecurity.token === 'function') {
      return global.CasePMSecurity.token();
    }
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function sessionKey() {
    try {
      let key = sessionStorage.getItem(STORAGE_KEY);
      if (!key) {
        key = (global.crypto && crypto.randomUUID)
          ? crypto.randomUUID()
          : ('ps-' + Date.now() + '-' + Math.random().toString(36).slice(2));
        sessionStorage.setItem(STORAGE_KEY, key);
      }
      return key;
    } catch (_) {
      return 'ps-fallback-' + (currentUserId() || '0');
    }
  }

  function elData(name) {
    return (document.documentElement.dataset[name] || (document.body && document.body.dataset[name]) || '').trim();
  }

  function activeTabLabel() {
    const selectors = [
      '.tab-button.active span',
      '.tab-button.active',
      '.dev-tab-btn.active',
      '[role="tab"][aria-selected="true"]',
    ];
    for (const sel of selectors) {
      const node = document.querySelector(sel);
      if (node && node.textContent) return node.textContent.trim().slice(0, 120);
    }
    return '';
  }

  function openModalTitles() {
    const titles = [];
    document.querySelectorAll('dialog[open] h2, dialog[open] h3, .modal[open] h2, .modal[open] h3').forEach((n) => {
      const t = (n.textContent || '').trim();
      if (t) titles.push(t.slice(0, 80));
    });
    return titles.slice(0, 3);
  }

  function visibleHeadings() {
    const out = [];
    document.querySelectorAll('h1, h2').forEach((n) => {
      if (n.offsetParent === null) return;
      const t = (n.textContent || '').trim();
      if (t) out.push(t.slice(0, 100));
    });
    return out.slice(0, 4);
  }

  function selectedLabels() {
    const out = [];
    document.querySelectorAll('select').forEach((sel) => {
      if (sel.offsetParent === null || !sel.value) return;
      const opt = sel.options[sel.selectedIndex];
      const label = opt ? opt.textContent.trim() : sel.value;
      if (label && !label.startsWith('--')) out.push(label.slice(0, 60));
    });
    return out.slice(0, 4);
  }

  function collectPresenceState() {
    const scrollEl = document.scrollingElement || document.documentElement;
    const scrollTop = scrollEl ? scrollEl.scrollTop : 0;
    const scrollHeight = scrollEl ? Math.max(scrollEl.scrollHeight - scrollEl.clientHeight, 1) : 1;
    const scrollPct = Math.min(100, Math.round((scrollTop / scrollHeight) * 100));

    const projectName = elData('activeProjectName');
    const projectId = elData('activeProjectId');

    const viewState = {
      url: global.location.pathname + global.location.search,
      headings: visibleHeadings(),
      open_modals: openModalTitles(),
      selected: selectedLabels(),
      focused: document.activeElement && document.activeElement !== document.body
        ? (document.activeElement.getAttribute('aria-label')
          || document.activeElement.getAttribute('placeholder')
          || document.activeElement.tagName || '').toString().slice(0, 80)
        : '',
    };

    const tab = activeTabLabel();
    const parts = [];
    if (projectName) parts.push('Project: ' + projectName);
    if (tab) parts.push('Tab: ' + tab);
    if (viewState.open_modals.length) parts.push('Modal: ' + viewState.open_modals[0]);
    if (lastAction) parts.push(lastAction);

    return {
      session_key: sessionKey(),
      page_path: global.location.pathname,
      page_title: document.title || '',
      page_module: elData('pageModule') || (document.body && document.body.dataset.pageModule) || '',
      project_id: projectId ? parseInt(projectId, 10) || null : null,
      project_name: projectName,
      active_tab: tab,
      activity_summary: parts.join(' · ').slice(0, 500),
      view_state: viewState,
      last_action: lastAction,
      last_action_at: lastActionAt,
      scroll_pct: scrollPct,
    };
  }

  function loadHtml2Canvas() {
    if (global.html2canvas) return Promise.resolve(global.html2canvas);
    if (html2canvasLoading) return html2canvasLoading;
    html2canvasLoading = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
      s.onload = () => resolve(global.html2canvas);
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return html2canvasLoading;
  }

  async function captureThumbnail() {
    if (document.hidden) return null;
    try {
      const shell = document.getElementById('appShell') || document.body;
      const h2c = await loadHtml2Canvas();
      const canvas = await h2c(shell, {
        scale: 0.3,
        logging: false,
        useCORS: true,
        ignoreElements: (node) => node.id === 'devUnlockBanner',
      });
      return canvas.toDataURL('image/jpeg', 0.55);
    } catch (_) {
      return null;
    }
  }

  async function sendHeartbeat(includeThumb) {
    if (!currentUserId()) return;
    const payload = collectPresenceState();
    if (includeThumb) {
      const thumb = await captureThumbnail();
      if (thumb) payload.thumbnail_b64 = thumb;
    }
    const headers = { 'Content-Type': 'application/json' };
    const token = csrfToken();
    if (token) headers['X-CSRF-Token'] = token;
    try {
      const res = await fetch('/api/presence/heartbeat', {
        method: 'POST',
        credentials: 'same-origin',
        headers,
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        console.warn('[CasePM Presence] heartbeat failed', res.status);
      }
    } catch (err) {
      console.warn('[CasePM Presence] heartbeat error', err);
    }
  }

  function noteAction(description) {
    if (!description) return;
    lastAction = String(description).slice(0, 200);
    lastActionAt = new Date().toISOString();
    sendHeartbeat(false);
  }

  function onClick(ev) {
    const t = ev.target;
    if (!t || t.closest('[data-presence-ignore]')) return;
    const btn = t.closest('button, a, [role="button"]');
    if (btn) {
      const label = (btn.getAttribute('aria-label') || btn.textContent || '').trim().replace(/\s+/g, ' ');
      if (label) noteAction('Clicked: ' + label.slice(0, 120));
      return;
    }
    if (t.matches('select')) {
      noteAction('Changed: ' + (t.name || t.id || 'dropdown'));
    }
  }

  function start() {
    if (started) return;
    if (!currentUserId()) return;
    started = true;

    document.addEventListener('click', onClick, true);
    sendHeartbeat(false);
    setTimeout(() => sendHeartbeat(true), 1500);
    heartbeatTimer = setInterval(() => sendHeartbeat(false), HEARTBEAT_MS);
    thumbTimer = setInterval(() => sendHeartbeat(true), THUMB_MS);

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) sendHeartbeat(true);
    });
  }

  function tryStart() {
    if (currentUserId()) start();
  }

  global.CasePMPresence = { start, tryStart, noteAction, collectPresenceState, sessionKey };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryStart);
  } else {
    tryStart();
  }
  global.addEventListener('load', tryStart);
}(window));
