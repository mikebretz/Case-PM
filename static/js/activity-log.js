/**
 * Case PM — server-backed activity log (per-page + central audit)
 */
(function (global) {
  'use strict';

  const STORAGE_KEY = 'casepm_activity_log_v1';
  const SYNC_FLAG = 'casepm_audit_local_synced_v1';
  const MAX_LOCAL = 2000;
  const IS_ADMIN = () => document.body.dataset.isAdmin === '1';

  function pageModule() {
    const ep = (document.body.dataset.pageModule || '').trim();
    if (ep) return ep;
    const path = (global.location.pathname || '').replace(/^\//, '').split('/')[0] || 'app';
    return path.replace(/-/g, '_') || 'app';
  }

  function currentUserLabel() {
    return document.body.dataset.currentUser || 'User';
  }

  function currentUserId() {
    const id = document.body.dataset.currentUserId;
    return id ? parseInt(id, 10) : null;
  }

  function activeProjectMeta() {
    const pid = document.body.dataset.activeProjectId;
    const pname = document.body.dataset.activeProjectName || '';
    return {
      project_id: pid ? parseInt(pid, 10) : null,
      project_name: pname,
    };
  }

  function loadLocal() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch (e) {
      return [];
    }
  }

  function saveLocal(entries) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_LOCAL)));
  }

  function coerceTimestamp(val) {
    if (val == null || val === '') return new Date().toISOString();
    if (typeof val === 'number') {
      const d = new Date(val > 1e12 ? val : val * 1000);
      return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
    }
    const d = new Date(val);
    return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
  }

  function formatTime(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso || '';
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function normalizeEntry(action, detail, module, meta) {
    const m = meta || {};
    const proj = activeProjectMeta();
    return {
      client_id: m.client_id || (`cli-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`),
      module: module || m.module || pageModule(),
      action: String(action || 'Action'),
      detail: detail ? String(detail) : (m.detail || ''),
      category: m.category || 'other',
      severity: m.severity || 'info',
      user_name: m.user_name || currentUserLabel(),
      user_id: m.user_id || currentUserId(),
      project_id: m.project_id ?? proj.project_id,
      project_name: m.project_name || proj.project_name,
      company_id: m.company_id ?? null,
      company_name: m.company_name || '',
      change_order_id: m.change_order_id ?? null,
      target_type: m.target_type || '',
      target_id: m.target_id ?? null,
      entity_ref: m.entity_ref || '',
      metadata: m.metadata || m.details || {},
      timestamp: coerceTimestamp(m.timestamp),
    };
  }

  async function postToServer(entry) {
    if (!IS_ADMIN()) return;
    try {
      await fetch('/api/audit-log/events', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(entry),
      });
    } catch (_) { /* offline */ }
  }

  function log(action, detail, module, meta) {
    const entry = normalizeEntry(action, detail, module, meta);
    const local = {
      id: entry.client_id,
      module: entry.module,
      action: entry.action,
      detail: entry.detail,
      user: entry.user_name,
      ts: entry.timestamp,
      category: entry.category,
      project_name: entry.project_name,
      company_name: entry.company_name,
      entity_ref: entry.entity_ref,
    };
    const all = loadLocal();
    all.unshift(local);
    saveLocal(all);
    postToServer(entry);
    refreshFooterPreview();
    return entry;
  }

  async function fetchServerEntries(filters) {
    const params = new URLSearchParams();
    const f = filters || {};
    Object.entries(f).forEach(([k, v]) => {
      if (v != null && v !== '' && v !== 'all') params.set(k, v);
    });
    if (!params.has('limit')) params.set('limit', '200');
    const res = await fetch(`/api/audit-log/events?${params}`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('Could not load audit log');
    const json = await res.json();
    return json;
  }

  function getEntries(filter) {
    const f = filter || {};
    return loadLocal().filter(e => {
      if (f.module && f.module !== 'all' && e.module !== f.module) return false;
      if (f.search) {
        const q = f.search.toLowerCase();
        const blob = [e.action, e.detail, e.module, e.user, e.project_name, e.company_name, e.entity_ref].join(' ').toLowerCase();
        if (!blob.includes(q)) return false;
      }
      return true;
    });
  }

  function refreshFooterPreview() {
    const el = document.getElementById('footerActivityPreview');
    if (!el) return;
    const mod = pageModule();
    const recent = getEntries({ module: mod }).slice(0, 1)[0];
    el.textContent = recent ? `${recent.action}${recent.detail ? ': ' + recent.detail : ''}` : '';
    el.title = recent ? formatTime(recent.ts) : '';
  }

  function renderRows(rows, tbody) {
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-8 text-center text-zinc-500">No activity logged yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(e => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/40 align-top">
        <td class="px-3 py-2 text-xs text-zinc-500 whitespace-nowrap">${formatTime(e.timestamp || e.ts)}</td>
        <td class="px-3 py-2 text-xs text-emerald-400/90">${escapeHtml(e.module_label || e.module)}</td>
        <td class="px-3 py-2 text-sm font-medium">${escapeHtml(e.action)}</td>
        <td class="px-3 py-2 text-sm text-zinc-400">${escapeHtml(e.detail || e.details || '')}</td>
        <td class="px-3 py-2 text-xs text-zinc-500">${escapeHtml(e.user_name || e.user || '')}</td>
        <td class="px-3 py-2 text-xs text-zinc-600">${[e.entity_ref, e.project_name, e.company_name].filter(Boolean).map(escapeHtml).join(' · ')}</td>
      </tr>`).join('');
  }

  async function renderLogTable() {
    const tbody = document.getElementById('globalActivityLogBody');
    if (!tbody) return;
    const search = (document.getElementById('globalActivityLogSearch')?.value || '').trim();
    const mod = document.getElementById('globalActivityLogModule')?.value || pageModule();
    tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-zinc-500">Loading…</td></tr>';
    if (IS_ADMIN()) {
      try {
        const json = await fetchServerEntries({ module: mod, q: search, limit: 200 });
        renderRows(json.events || [], tbody);
        return;
      } catch (_) { /* fall through to local */ }
    }
    renderRows(getEntries({ module: mod === 'all' ? null : mod, search: search || null }), tbody);
  }

  function showLogModal(opts) {
    if (!IS_ADMIN()) {
      alert('Activity log is available to administrators only.');
      return;
    }
    const options = opts || {};
    const mod = options.module || pageModule();
    const dlg = document.getElementById('globalActivityLogModal');
    if (!dlg) {
      alert('Activity log modal not found.');
      return;
    }
    const searchEl = document.getElementById('globalActivityLogSearch');
    const moduleEl = document.getElementById('globalActivityLogModule');
    if (searchEl) searchEl.value = options.search || '';
    if (moduleEl) moduleEl.value = options.moduleOnly ? mod : (options.module || mod);
    renderLogTable();
    dlg.showModal();
  }

  async function exportLog() {
    if (IS_ADMIN()) {
      try {
        const json = await fetchServerEntries({ limit: 500, module: 'all' });
        const blob = new Blob([JSON.stringify(json.events || [], null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `casepm_audit_log_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        return;
      } catch (_) {}
    }
    const blob = new Blob([JSON.stringify(loadLocal(), null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `casepm_activity_log_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
  }

  function collectLegacyLocalEntries() {
    const out = [];
    const push = (entry, module, defaults) => {
      if (!entry || !entry.action) return;
      out.push(normalizeEntry(
        entry.action,
        entry.detail || entry.summary || (typeof entry.details === 'string' ? entry.details : JSON.stringify(entry.details || '')),
        module,
        {
          ...defaults,
          client_id: entry.id ? `legacy-${module}-${entry.id}` : undefined,
          user_name: entry.user || entry.userName || defaults.user_name,
          timestamp: entry.timestamp || entry.ts || entry.date,
          company_id: entry.targetCompanyId || entry.company_id,
          change_order_id: entry.changeOrderId || entry.change_order_id,
          entity_ref: entry.entityRef || entry.entity_ref || '',
          metadata: entry.details && typeof entry.details === 'object' ? entry.details : {},
        }
      ));
    };

    try {
      JSON.parse(localStorage.getItem('companyAuditLog') || '[]').forEach(e => push(e, 'companies', {}));
    } catch (_) {}
    try {
      JSON.parse(localStorage.getItem('userAuditLog') || '[]').forEach(e => push(e, 'users', { target_type: 'User', target_id: e.targetUserId }));
    } catch (_) {}
    const store = global.casepmStore || { getItem: (k) => localStorage.getItem(k) };
    try {
      JSON.parse(store.getItem('payAppAuditLog') || '[]').forEach(e => push(e, 'pay_applications', {}));
    } catch (_) {}
    try {
      JSON.parse(store.getItem('budgetAuditLog') || '[]').forEach(e => push(e, 'budget', {}));
    } catch (_) {}
    try {
      JSON.parse(store.getItem('publishAuditLog') || '[]').forEach(e => push(e, 'budget', { category: 'publish' }));
    } catch (_) {}
    loadLocal().forEach(e => push(e, e.module || 'app', { client_id: e.id ? `legacy-local-${e.id}` : undefined }));

    Object.keys(localStorage).filter(k => k.startsWith('casepm_commitment_audit_')).forEach(key => {
      try {
        JSON.parse(localStorage.getItem(key) || '[]').forEach(e => push(e, 'commitments', {}));
      } catch (_) {}
    });
    return out;
  }

  async function syncLegacyToServer() {
    if (!IS_ADMIN() || localStorage.getItem(SYNC_FLAG)) return;
    const batch = collectLegacyLocalEntries();
    if (!batch.length) {
      localStorage.setItem(SYNC_FLAG, '1');
      return;
    }
    try {
      const events = batch.slice(0, 500).map((e) => ({ ...e, timestamp: coerceTimestamp(e.timestamp) }));
      const res = await fetch('/api/audit-log/events/batch', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events }),
      });
      if (res.ok) {
        localStorage.setItem(SYNC_FLAG, '1');
      } else if (!global.__casepmAuditSyncWarned) {
        global.__casepmAuditSyncWarned = true;
        console.warn('[ActivityLog] Legacy audit sync failed:', res.status);
      }
    } catch (err) {
      if (!global.__casepmAuditSyncWarned) {
        global.__casepmAuditSyncWarned = true;
        console.warn('[ActivityLog] Legacy audit sync failed:', err.message || err);
      }
    }
  }

  function init() {
    if (!IS_ADMIN()) return;
    refreshFooterPreview();
    syncLegacyToServer();
    document.getElementById('globalActivityLogSearch')?.addEventListener('input', () => renderLogTable());
    document.getElementById('globalActivityLogModule')?.addEventListener('change', () => renderLogTable());
  }

  global.CasePMActivityLog = {
    log,
    getEntries,
    showLogModal,
    renderLogTable,
    exportLog,
    refreshFooterPreview,
    pageModule,
    fetchServerEntries,
    syncLegacyToServer,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : global);
