/**
 * Audit Log page — matches Case PM admin list module pattern (daily log / user management).
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_AUDIT_LOG_CTX || {};

  const state = {
    offset: 0,
    limit: 100,
    total: 0,
    events: [],
    loading: false,
    activeModuleChip: 'all',
    advancedOpen: false,
    searchDebounce: null,
  };

  function $(id) { return document.getElementById(id); }

  function formatTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  }

  function formatTimeShort(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function collectFilters() {
    return {
      q: $('aloadSearch')?.value?.trim() || '',
      module: $('aloadModule')?.value || 'all',
      category: $('aloadCategory')?.value || 'all',
      severity: $('aloadSeverity')?.value || 'all',
      user_name: $('aloadUser')?.value?.trim() || '',
      company_name: $('aloadCompany')?.value?.trim() || '',
      project_name: $('aloadProject')?.value?.trim() || '',
      entity_ref: $('aloadEntityRef')?.value?.trim() || '',
      change_order_id: $('aloadChangeOrder')?.value?.trim() || '',
      target_type: $('aloadTargetType')?.value?.trim() || '',
      date_from: $('aloadDateFrom')?.value || '',
      date_to: $('aloadDateTo')?.value || '',
      limit: state.limit,
      offset: state.offset,
    };
  }

  const URL_PARAM_MAP = {
    q: 'aloadSearch',
    module: 'aloadModule',
    category: 'aloadCategory',
    severity: 'aloadSeverity',
    user_name: 'aloadUser',
    company_name: 'aloadCompany',
    project_name: 'aloadProject',
    entity_ref: 'aloadEntityRef',
    change_order_id: 'aloadChangeOrder',
    target_type: 'aloadTargetType',
    date_from: 'aloadDateFrom',
    date_to: 'aloadDateTo',
  };

  function setFiltersFromUrl() {
    const p = new URLSearchParams(global.location.search);
    Object.entries(URL_PARAM_MAP).forEach(([param, id]) => {
      const el = $(id);
      if (el && p.has(param)) el.value = p.get(param);
    });
    const mod = $('aloadModule')?.value || 'all';
    state.activeModuleChip = mod;
    syncModuleChips();
  }

  function updateUrl() {
    const f = collectFilters();
    const p = new URLSearchParams();
    Object.keys(URL_PARAM_MAP).forEach((k) => {
      if (f[k] && f[k] !== 'all') p.set(k, f[k]);
    });
    const qs = p.toString();
    global.history.replaceState({}, '', qs ? `?${qs}` : global.location.pathname);
  }

  function syncModuleChips() {
    const mod = $('aloadModule')?.value || 'all';
    state.activeModuleChip = mod;
    document.querySelectorAll('[data-module-chip]').forEach((btn) => {
      const chip = btn.dataset.moduleChip;
      const active = chip === mod || (chip === 'all' && mod === 'all');
      btn.classList.toggle('active', active);
    });
  }

  function setStat(id, value, extraClass) {
    const el = $(id);
    if (!el) return;
    el.textContent = value;
    if (extraClass) {
      el.className = `text-2xl font-semibold mt-1 ${extraClass}`;
    }
  }

  async function loadStats() {
    try {
      const res = await fetch('/api/audit-log/stats', { credentials: 'same-origin' });
      const json = await res.json();
      if (!json.stats) return;
      const s = json.stats;
      setStat('aloadStatTotal', (s.total || 0).toLocaleString());
      setStat('aloadStatToday', (s.today || 0).toLocaleString(), 'text-2xl font-semibold mt-1 text-emerald-400');
      setStat('aloadStatWeek', (s.this_week || 0).toLocaleString());
      setStat('aloadStatSecurity', (s.security_events || 0).toLocaleString(), 'text-2xl font-semibold mt-1 text-amber-400');
      setStat('aloadStatFailedLogins', (s.failed_logins || 0).toLocaleString(), 'text-2xl font-semibold mt-1 text-red-400');
      const lastEl = $('aloadStatLast');
      if (lastEl) lastEl.textContent = s.last_event_at ? formatTime(s.last_event_at) : '—';
    } catch (_) {}
  }

  function updatePagination() {
    const page = Math.floor(state.offset / state.limit) + 1;
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    const pageInfo = $('aloadPageInfo');
    const prev = $('aloadPrevBtn');
    const next = $('aloadNextBtn');
    if (pageInfo) pageInfo.textContent = state.total ? `Page ${page} / ${totalPages}` : '—';
    if (prev) prev.disabled = state.offset <= 0;
    if (next) next.disabled = state.offset + state.limit >= state.total;
  }

  function updateStatusBar() {
    const status = $('aloadStatusText');
    const updated = $('aloadUpdatedAt');
    if (status) {
      status.textContent = state.total
        ? `Showing ${state.offset + 1}–${Math.min(state.offset + state.events.length, state.total)} of ${state.total.toLocaleString()} events`
        : 'No events';
    }
    if (updated) {
      const hint = updated.querySelector('strong') ? '' : '';
      updated.innerHTML = `Updated ${new Date().toLocaleTimeString()} · Per-module logs: footer <strong class="text-zinc-400">Activity Log</strong>${hint}`;
    }
    updatePagination();
  }

  async function loadEvents(resetOffset) {
    if (resetOffset) state.offset = 0;
    state.loading = true;
    const tbody = $('aloadTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-12 text-center text-zinc-500">Loading audit log…</td></tr>';
    updateUrl();
    syncModuleChips();
    const filters = collectFilters();
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null && v !== '' && v !== 'all') params.set(k, v);
    });
    try {
      const res = await fetch(`/api/audit-log/events?${params}`, { credentials: 'same-origin' });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Load failed');
      state.events = json.events || [];
      state.total = json.total || 0;
      renderTable();
      updateStatusBar();
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="px-6 py-12 text-center text-red-400">${esc(err.message)}</td></tr>`;
    }
    state.loading = false;
  }

  function categoryClass(cat) {
    const c = (cat || 'other').toLowerCase();
    if (c === 'create') return 'aload-cat-pill aload-cat-create';
    if (c === 'update') return 'aload-cat-pill aload-cat-update';
    if (c === 'delete') return 'aload-cat-pill aload-cat-delete';
    if (c === 'login') return 'aload-cat-pill aload-cat-login';
    if (c === 'settings') return 'aload-cat-pill aload-cat-settings';
    return 'aload-cat-pill aload-cat-other';
  }

  function severityClass(sev) {
    if (sev === 'critical') return 'text-red-400';
    if (sev === 'warning') return 'text-amber-400';
    return 'text-zinc-400';
  }

  function truncate(s, len) {
    const t = String(s || '');
    return t.length > len ? t.slice(0, len) + '…' : t;
  }

  function renderTable() {
    const tbody = $('aloadTableBody');
    if (!tbody) return;
    if (!state.events.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-12 text-center text-zinc-500">No events match your filters.</td></tr>';
      return;
    }
    tbody.innerHTML = state.events.map((e, idx) => {
      const refs = [e.entity_ref, e.project_name, e.company_name].filter(Boolean).join(' · ');
      return `<tr data-idx="${idx}" title="Click for full details">
        <td class="px-4 py-3 text-xs text-zinc-500 whitespace-nowrap">${formatTimeShort(e.timestamp)}</td>
        <td class="px-4 py-3 text-xs"><span class="text-emerald-400/90 font-medium">${esc(e.module_label || e.module)}</span></td>
        <td class="px-4 py-3 text-sm font-medium text-white">${esc(e.action)}</td>
        <td class="px-4 py-3 text-sm text-zinc-400">${esc(truncate(e.detail, 120))}</td>
        <td class="px-4 py-3 text-xs text-zinc-400 aload-hide-mobile">${esc(e.user_name || '—')}</td>
        <td class="px-4 py-3 text-xs text-zinc-500 aload-hide-mobile">${esc(truncate(refs, 48) || '—')}</td>
        <td class="px-4 py-3"><span class="${categoryClass(e.category)}">${esc(e.category || 'other')}</span></td>
      </tr>`;
    }).join('');

    tbody.querySelectorAll('tr[data-idx]').forEach((row) => {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.idx, 10);
        if (!Number.isNaN(idx)) showDetail(state.events[idx]);
      });
    });
  }

  function detailRow(label, value) {
    if (value == null || value === '') return '';
    return `<div class="grid grid-cols-3 gap-2 py-1.5 border-b border-zinc-800/80">
      <div class="text-xs text-zinc-500 uppercase tracking-wide">${esc(label)}</div>
      <div class="col-span-2 text-sm text-zinc-200 break-words">${value}</div>
    </div>`;
  }

  function showDetail(e) {
    if (!e) return;
    const body = $('aloadDetailBody');
    const modal = $('aloadDetailModal');
    if (!body || !modal) return;
    const refs = [e.entity_ref, e.project_name, e.company_name].filter(Boolean).join(' · ');
    const target = e.change_order_id
      ? `Change Order #${e.change_order_id}`
      : (e.target_type ? `${e.target_type}${e.target_id ? ' #' + e.target_id : ''}` : '—');
    let metaHtml = '';
    if (e.metadata && Object.keys(e.metadata).length) {
      metaHtml = `<div class="mt-3">
        <div class="text-xs text-zinc-500 uppercase mb-2">Metadata</div>
        <pre class="text-xs text-zinc-400 bg-zinc-950 border border-zinc-800 rounded-md p-3 overflow-x-auto whitespace-pre-wrap">${esc(JSON.stringify(e.metadata, null, 2))}</pre>
      </div>`;
    }
    body.innerHTML = `
      ${detailRow('Time', esc(formatTime(e.timestamp)))}
      ${detailRow('Module', esc(e.module_label || e.module))}
      ${detailRow('Action', `<span class="font-semibold text-white">${esc(e.action)}</span>`)}
      ${detailRow('Detail', esc(e.detail || '—'))}
      ${detailRow('User', esc(e.user_name || '—') + (e.user_email ? ` <span class="text-zinc-500">(${esc(e.user_email)})</span>` : ''))}
      ${detailRow('Category', `<span class="${categoryClass(e.category)}">${esc(e.category || 'other')}</span>`)}
      ${detailRow('Severity', `<span class="${severityClass(e.severity)}">${esc(e.severity || 'info')}</span>`)}
      ${detailRow('References', esc(refs || '—'))}
      ${detailRow('Target', esc(target))}
      ${metaHtml}`;
    if (typeof modal.showModal === 'function') modal.showModal();
  }

  function closeDetail() {
    const modal = $('aloadDetailModal');
    if (modal && typeof modal.close === 'function') modal.close();
  }

  function clearFilters() {
    ['aloadSearch', 'aloadUser', 'aloadCompany', 'aloadProject', 'aloadEntityRef', 'aloadChangeOrder', 'aloadTargetType', 'aloadDateFrom', 'aloadDateTo'].forEach((id) => {
      const el = $(id);
      if (el) el.value = '';
    });
    ['aloadModule', 'aloadCategory', 'aloadSeverity'].forEach((id) => {
      const el = $(id);
      if (el) el.value = 'all';
    });
    state.activeModuleChip = 'all';
    syncModuleChips();
    loadEvents(true);
  }

  function scheduleSearch() {
    clearTimeout(state.searchDebounce);
    state.searchDebounce = setTimeout(() => loadEvents(true), 350);
  }

  async function exportCsv() {
    const filters = collectFilters();
    filters.limit = 2000;
    filters.offset = 0;
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null && v !== '' && v !== 'all') params.set(k, v);
    });
    try {
      const res = await fetch(`/api/audit-log/events?${params}`, { credentials: 'same-origin' });
      const json = await res.json();
      const rows = json.events || [];
      const header = ['timestamp', 'module', 'action', 'detail', 'user_name', 'user_email', 'project_name', 'company_name', 'entity_ref', 'change_order_id', 'category', 'severity'];
      const lines = [header.join(',')];
      rows.forEach((e) => {
        lines.push(header.map((h) => `"${String(e[h] || '').replace(/"/g, '""')}"`).join(','));
      });
      const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `casepm_audit_export_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      if (global.CasePMDialog) CasePMDialog.alert(err.message || 'Export failed', 'error');
    }
  }

  async function exportJson() {
    const filters = collectFilters();
    filters.limit = 2000;
    filters.offset = 0;
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null && v !== '' && v !== 'all') params.set(k, v);
    });
    try {
      const res = await fetch(`/api/audit-log/events?${params}`, { credentials: 'same-origin' });
      const json = await res.json();
      const blob = new Blob([JSON.stringify(json.events || [], null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `casepm_audit_export_${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      if (global.CasePMDialog) CasePMDialog.alert(err.message || 'Export failed', 'error');
    }
  }

  function toggleAdvanced() {
    state.advancedOpen = !state.advancedOpen;
    const body = $('aloadAdvancedBody');
    const chevron = $('aloadAdvancedChevron');
    const toggle = $('aloadAdvancedToggle');
    if (body) body.classList.toggle('hidden', !state.advancedOpen);
    if (chevron) chevron.style.transform = state.advancedOpen ? 'rotate(180deg)' : '';
    if (toggle) toggle.setAttribute('aria-expanded', state.advancedOpen ? 'true' : 'false');
  }

  function pagePrev() {
    state.offset = Math.max(0, state.offset - state.limit);
    loadEvents(false);
  }

  function pageNext() {
    if (state.offset + state.limit < state.total) {
      state.offset += state.limit;
      loadEvents(false);
    }
  }

  function refreshAll() {
    loadStats();
    loadEvents(false);
  }

  function bind() {
    $('aloadClearBtn')?.addEventListener('click', clearFilters);
    $('aloadExportCsv')?.addEventListener('click', exportCsv);
    $('aloadExportJson')?.addEventListener('click', exportJson);
    $('aloadBtnRefresh')?.addEventListener('click', refreshAll);
    $('aloadPrevBtn')?.addEventListener('click', pagePrev);
    $('aloadNextBtn')?.addEventListener('click', pageNext);
    $('aloadDetailClose')?.addEventListener('click', closeDetail);
    $('aloadDetailCloseBtn')?.addEventListener('click', closeDetail);

    $('aloadSearch')?.addEventListener('input', scheduleSearch);
    $('aloadSearch')?.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') loadEvents(true);
    });

    ['aloadModule', 'aloadCategory', 'aloadSeverity', 'aloadDateFrom', 'aloadDateTo'].forEach((id) => {
      $(id)?.addEventListener('change', () => {
        if (id === 'aloadModule') syncModuleChips();
        loadEvents(true);
      });
    });

    ['aloadUser', 'aloadCompany', 'aloadProject', 'aloadEntityRef', 'aloadChangeOrder', 'aloadTargetType'].forEach((id) => {
      $(id)?.addEventListener('input', scheduleSearch);
    });

    document.querySelectorAll('[data-module-chip]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const mod = btn.dataset.moduleChip || 'all';
        if ($('aloadModule')) $('aloadModule').value = mod;
        syncModuleChips();
        loadEvents(true);
      });
    });

    $('aloadAdvancedToggle')?.addEventListener('click', toggleAdvanced);
    $('aloadAdvancedToggle')?.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        toggleAdvanced();
      }
    });
  }

  function init() {
    setFiltersFromUrl();
    bind();
    loadStats();
    loadEvents(true);
  }

  global.CasePMAuditLogPage = { init, loadEvents, clearFilters, exportCsv, refreshAll };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
