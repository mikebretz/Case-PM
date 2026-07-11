/**
 * Central Audit Log page — extensive search and filtering
 */
(function (global) {
  'use strict';

  const state = {
    offset: 0,
    limit: 100,
    total: 0,
    events: [],
    loading: false,
  };

  function $(id) { return document.getElementById(id); }

  function formatTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  }

  function esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function collectFilters() {
    return {
      q: $('auditSearchQ')?.value?.trim() || '',
      module: $('auditFilterModule')?.value || 'all',
      category: $('auditFilterCategory')?.value || 'all',
      severity: $('auditFilterSeverity')?.value || 'all',
      user_name: $('auditFilterUser')?.value?.trim() || '',
      company_name: $('auditFilterCompany')?.value?.trim() || '',
      project_name: $('auditFilterProject')?.value?.trim() || '',
      entity_ref: $('auditFilterEntityRef')?.value?.trim() || '',
      change_order_id: $('auditFilterChangeOrder')?.value?.trim() || '',
      target_type: $('auditFilterTargetType')?.value?.trim() || '',
      date_from: $('auditFilterDateFrom')?.value || '',
      date_to: $('auditFilterDateTo')?.value || '',
      limit: state.limit,
      offset: state.offset,
    };
  }

  function setFiltersFromUrl() {
    const p = new URLSearchParams(global.location.search);
    const map = {
      q: 'auditSearchQ',
      module: 'auditFilterModule',
      category: 'auditFilterCategory',
      user_name: 'auditFilterUser',
      company_name: 'auditFilterCompany',
      project_name: 'auditFilterProject',
      entity_ref: 'auditFilterEntityRef',
      change_order_id: 'auditFilterChangeOrder',
    };
    Object.entries(map).forEach(([param, id]) => {
      const el = $(id);
      if (el && p.has(param)) el.value = p.get(param);
    });
  }

  function updateUrl() {
    const f = collectFilters();
    const p = new URLSearchParams();
    ['q', 'module', 'category', 'user_name', 'company_name', 'project_name', 'entity_ref', 'change_order_id'].forEach(k => {
      if (f[k] && f[k] !== 'all') p.set(k, f[k]);
    });
    const qs = p.toString();
    global.history.replaceState({}, '', qs ? `?${qs}` : global.location.pathname);
  }

  async function loadStats() {
    try {
      const res = await fetch('/api/audit-log/stats', { credentials: 'same-origin' });
      const json = await res.json();
      const el = $('auditStatsBar');
      if (!el || !json.stats) return;
      const s = json.stats;
      el.innerHTML = `
        <span><strong class="text-zinc-300">${(s.total || 0).toLocaleString()}</strong> total events</span>
        <span class="text-zinc-600">|</span>
        <span>Last: ${s.last_event_at ? formatTime(s.last_event_at) : '—'}</span>
        <span class="text-zinc-600">|</span>
        <span class="truncate">Top: ${(s.by_module || []).slice(0, 4).map(m => `${esc(m.label)} (${m.count})`).join(' · ') || '—'}</span>`;
    } catch (_) {}
  }

  async function loadEvents(resetOffset) {
    if (resetOffset) state.offset = 0;
    state.loading = true;
    const tbody = $('auditLogTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-10 text-center text-zinc-500">Loading audit log…</td></tr>';
    updateUrl();
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
      $('auditResultCount').textContent = `Showing ${state.events.length} of ${state.total.toLocaleString()} events`;
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-10 text-center text-red-400">${esc(err.message)}</td></tr>`;
    }
    state.loading = false;
  }

  function severityClass(sev) {
    if (sev === 'critical') return 'text-red-400';
    if (sev === 'warning') return 'text-amber-400';
    return 'text-zinc-500';
  }

  function renderTable() {
    const tbody = $('auditLogTableBody');
    if (!tbody) return;
    if (!state.events.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-10 text-center text-zinc-500">No events match your filters.</td></tr>';
      return;
    }
    tbody.innerHTML = state.events.map((e, idx) => {
      const refs = [e.entity_ref, e.project_name, e.company_name].filter(Boolean).join(' · ');
      const meta = e.metadata && Object.keys(e.metadata).length
        ? `<details class="mt-1"><summary class="text-xs text-emerald-500 cursor-pointer">Details</summary><pre class="text-[10px] text-zinc-500 mt-1 whitespace-pre-wrap">${esc(JSON.stringify(e.metadata, null, 2))}</pre></details>`
        : '';
      return `<tr class="border-b border-zinc-800 hover:bg-zinc-800/30 align-top" data-idx="${idx}">
        <td class="px-3 py-2.5 text-xs text-zinc-500 whitespace-nowrap">${formatTime(e.timestamp)}</td>
        <td class="px-3 py-2.5 text-xs"><span class="text-emerald-400/90">${esc(e.module_label || e.module)}</span></td>
        <td class="px-3 py-2.5 text-sm font-medium">${esc(e.action)}</td>
        <td class="px-3 py-2.5 text-sm text-zinc-400">${esc(e.detail)}${meta}</td>
        <td class="px-3 py-2.5 text-xs text-zinc-400">${esc(e.user_name)}</td>
        <td class="px-3 py-2.5 text-xs text-zinc-500">${esc(refs)}</td>
        <td class="px-3 py-2.5 text-xs uppercase ${severityClass(e.severity)}">${esc(e.category || 'other')}</td>
        <td class="px-3 py-2.5 text-xs text-zinc-600 font-mono">${e.change_order_id ? 'CO#' + e.change_order_id : (e.target_type ? esc(e.target_type) + (e.target_id ? ' #' + e.target_id : '') : '—')}</td>
      </tr>`;
    }).join('');
  }

  function clearFilters() {
    ['auditSearchQ', 'auditFilterUser', 'auditFilterCompany', 'auditFilterProject', 'auditFilterEntityRef', 'auditFilterChangeOrder', 'auditFilterTargetType', 'auditFilterDateFrom', 'auditFilterDateTo'].forEach(id => {
      const el = $(id);
      if (el) el.value = '';
    });
    ['auditFilterModule', 'auditFilterCategory', 'auditFilterSeverity'].forEach(id => {
      const el = $(id);
      if (el) el.value = 'all';
    });
    loadEvents(true);
  }

  async function exportCsv() {
    const filters = collectFilters();
    filters.limit = 2000;
    filters.offset = 0;
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null && v !== '' && v !== 'all') params.set(k, v);
    });
    const res = await fetch(`/api/audit-log/events?${params}`, { credentials: 'same-origin' });
    const json = await res.json();
    const rows = json.events || [];
    const header = ['timestamp', 'module', 'action', 'detail', 'user_name', 'user_email', 'project_name', 'company_name', 'entity_ref', 'change_order_id', 'category', 'severity'];
    const lines = [header.join(',')];
    rows.forEach(e => {
      lines.push(header.map(h => `"${String(e[h] || '').replace(/"/g, '""')}"`).join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `casepm_audit_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
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

  function bind() {
    $('auditSearchBtn')?.addEventListener('click', () => loadEvents(true));
    $('auditClearBtn')?.addEventListener('click', clearFilters);
    $('auditExportCsvBtn')?.addEventListener('click', exportCsv);
    $('auditExportJsonBtn')?.addEventListener('click', async () => {
      if (global.CasePMActivityLog) CasePMActivityLog.exportLog();
    });
    $('auditPrevBtn')?.addEventListener('click', pagePrev);
    $('auditNextBtn')?.addEventListener('click', pageNext);
    $('auditSearchQ')?.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') loadEvents(true);
    });
    document.querySelectorAll('[data-module-chip]').forEach(btn => {
      btn.addEventListener('click', () => {
        const mod = btn.dataset.moduleChip;
        if ($('auditFilterModule')) $('auditFilterModule').value = mod;
        loadEvents(true);
      });
    });
  }

  function init() {
    setFiltersFromUrl();
    bind();
    loadStats();
    loadEvents(true);
  }

  global.CasePMAuditLogPage = { init, loadEvents, clearFilters, exportCsv };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
