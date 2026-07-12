/**
 * Case PM Weekly Log — compiles daily logs into an editable weekly/biweekly report.
 * Same look & feel as the Daily Log. Compile pulls manpower, equipment, deliveries,
 * delays, visitors, safety, inspections and daily summaries; every row is editable.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_WEEKLY_CTX || {};
  const DELAY_TYPES = ['Weather', 'Labor Shortage', 'Material', 'Equipment', 'Owner', 'Design/RFI', 'Inspection', 'Utility', 'Other'];
  const SAFETY_TYPES = ['Observation', 'Near Miss', 'Incident', 'Toolbox Talk', 'Violation', 'JHA/JSA', 'PPE Check'];
  const RESULTS = ['Pass', 'Fail', 'Partial', 'Pending', 'N/A'];

  const SECTIONS = [
    { key: 'daily_summaries', label: 'Daily Summaries', icon: 'fa-list-check', color: 'text-emerald-400', open: true, fields: [
      { k: 'date', ph: 'Date', type: 'date', w: 'w-40' },
      { k: 'work', ph: 'Work performed', type: 'text', w: 'flex-1' },
    ] },
    { key: 'manpower', label: 'Manpower', icon: 'fa-users', color: 'text-emerald-400', open: true, fields: [
      { k: 'company', ph: 'Company / sub', type: 'text', w: 'flex-1' },
      { k: 'days', ph: 'Days', type: 'number', w: 'w-20' },
      { k: 'workers', ph: 'Man-days', type: 'number', w: 'w-24' },
      { k: 'hours', ph: 'Hours', type: 'number', step: '0.5', w: 'w-24' },
    ] },
    { key: 'equipment', label: 'Equipment', icon: 'fa-truck-pickup', color: 'text-zinc-300', fields: [
      { k: 'equipment_name', ph: 'Equipment', type: 'text', w: 'flex-1' },
      { k: 'days', ph: 'Days', type: 'number', w: 'w-20' },
      { k: 'notes', ph: 'Notes', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'deliveries', label: 'Deliveries', icon: 'fa-box', color: 'text-amber-400', fields: [
      { k: 'item', ph: 'Item', type: 'text', w: 'flex-1' },
      { k: 'supplier', ph: 'Supplier', type: 'text', w: 'flex-1', mHide: true },
      { k: 'quantity', ph: 'Qty', type: 'text', w: 'w-24' },
    ] },
    { key: 'delays', label: 'Delays', icon: 'fa-clock', color: 'text-red-400', fields: [
      { k: 'type', ph: 'Type', type: 'select', options: DELAY_TYPES, w: 'w-36' },
      { k: 'description', ph: 'Description', type: 'text', w: 'flex-1' },
      { k: 'hours_lost', ph: 'Hrs lost', type: 'number', step: '0.5', w: 'w-24' },
    ] },
    { key: 'visitors', label: 'Visitors', icon: 'fa-user-tie', color: 'text-violet-400', fields: [
      { k: 'name', ph: 'Name', type: 'text', w: 'flex-1' },
      { k: 'company', ph: 'Company', type: 'text', w: 'flex-1', mHide: true },
      { k: 'purpose', ph: 'Purpose', type: 'text', w: 'flex-1' },
    ] },
    { key: 'safety', label: 'Safety', icon: 'fa-hard-hat', color: 'text-yellow-400', fields: [
      { k: 'type', ph: 'Type', type: 'select', options: SAFETY_TYPES, w: 'w-36' },
      { k: 'description', ph: 'Description', type: 'text', w: 'flex-1' },
      { k: 'action', ph: 'Action', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'inspections', label: 'Inspections', icon: 'fa-clipboard-check', color: 'text-teal-300', fields: [
      { k: 'type', ph: 'Type', type: 'text', w: 'flex-1' },
      { k: 'agency', ph: 'Agency', type: 'text', w: 'flex-1', mHide: true },
      { k: 'result', ph: 'Result', type: 'select', options: RESULTS, w: 'w-28' },
      { k: 'notes', ph: 'Notes', type: 'text', w: 'flex-1', mHide: true },
    ] },
  ];

  const state = { reports: [], stats: {}, editingId: null, viewingReport: null };

  function projectId() {
    return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })();
  }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(id) { return document.getElementById(id); }
  function fmtDate(iso) { if (!iso) return '—'; try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch (_) { return iso; } }

  // ---------- List ----------
  async function loadList() {
    const pid = projectId();
    el('wlogStatusText').textContent = 'Loading…';
    try {
      const res = await fetch(`/api/weekly-reports${pid ? `?project_id=${pid}` : ''}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed');
      state.reports = json.reports || [];
      state.stats = json.stats || {};
      renderStats();
      renderList();
      el('wlogStatusText').textContent = `${state.reports.length} report(s)`;
      el('wlogUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (e) { el('wlogStatusText').textContent = 'Error: ' + e.message; }
  }

  function renderStats() {
    const s = state.stats;
    el('wstatTotal').textContent = s.total_reports ?? 0;
    el('wstatMonth').textContent = s.this_month ?? 0;
    el('wstatHours').textContent = s.total_man_hours ?? 0;
    el('wstatDelays').textContent = s.open_delays ?? 0;
    const badge = el('wlogProjectBadge');
    if (badge) badge.textContent = ctx.projectName || 'All projects';
  }

  function statusBadge(status) {
    const st = status || 'Draft';
    const cls = st === 'Reviewed' ? 'bg-blue-500/15 text-blue-400' : st === 'Draft' ? 'bg-zinc-700 text-zinc-300' : 'bg-emerald-500/15 text-emerald-400';
    return `<span class="wlog-chip ${cls}">${esc(st)}</span>`;
  }

  function periodLabel(r) {
    if (r.period_start && r.period_end) return `${fmtDate(r.period_start)} – ${fmtDate(r.period_end)}`;
    return `Week ending ${fmtDate(r.period_end || r.week_ending)}`;
  }

  function filtered() {
    const term = (el('wlogSearch').value || '').toLowerCase();
    const st = el('wlogStatusFilter').value;
    return state.reports.filter((r) => {
      if (st && (r.status || 'Draft') !== st) return false;
      if (term) { const hay = `${periodLabel(r)} ${r.work_performed || ''}`.toLowerCase(); if (!hay.includes(term)) return false; }
      return true;
    });
  }

  function renderList() {
    const tbody = el('wlogTableBody');
    const rows = filtered();
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="px-6 py-12 text-center text-zinc-500">
        <i class="fa-solid fa-calendar-week text-4xl mb-3 block text-zinc-600"></i>
        No weekly logs yet. Tap <b>New Weekly Log</b> and Compile from your Daily Logs.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((r) => `
      <tr class="hover:bg-zinc-800/50 cursor-pointer" data-open="${r.id}">
        <td class="px-4 py-3 font-medium whitespace-nowrap">${periodLabel(r)}</td>
        <td class="px-4 py-3 text-center text-zinc-300 wlog-hide-mobile"><span class="wlog-chip bg-zinc-800 text-zinc-300 capitalize">${esc(r.period_type || 'weekly')}</span></td>
        <td class="px-4 py-3 text-center text-zinc-300">${r.total_workers || '—'}</td>
        <td class="px-4 py-3 text-center text-zinc-300 wlog-hide-mobile">${r.total_hours || '—'}</td>
        <td class="px-4 py-3 text-zinc-300 max-w-[360px] truncate">${esc((r.work_performed || '—').split('\n')[0])}</td>
        <td class="px-4 py-3 text-center wlog-hide-mobile">${statusBadge(r.status)}</td>
        <td class="px-4 py-3 text-center"><button class="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md" data-open="${r.id}">View</button></td>
      </tr>`).join('');
    tbody.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', (e) => { e.stopPropagation(); openDetail(parseInt(n.getAttribute('data-open'), 10)); }));
  }

  // ---------- Sections ----------
  const CELL_STYLE = {
    'flex-1': 'flex:1 1 170px; min-width:150px;',
    'w-20': 'flex:0 1 84px; min-width:70px;',
    'w-24': 'flex:0 1 96px; min-width:80px;',
    'w-28': 'flex:0 1 112px; min-width:96px;',
    'w-36': 'flex:0 1 150px; min-width:130px;',
    'w-40': 'flex:0 1 165px; min-width:140px;',
  };
  function cellStyle(f) { return CELL_STYLE[f.w] || 'flex:1 1 150px; min-width:130px;'; }

  function buildSectionsHost() {
    const host = el('wlogSectionsHost');
    host.innerHTML = SECTIONS.map((s) => `
      <div class="wlog-section">
        <div class="wlog-section-head" data-section-toggle="${s.key}">
          <span class="font-medium text-sm"><i class="fa-solid ${s.icon} ${s.color} mr-2"></i>${esc(s.label)}<span id="wcount_${s.key}" class="wlog-count-pill">0</span></span>
          <i class="fa-solid fa-chevron-down text-xs text-zinc-500"></i>
        </div>
        <div class="wlog-section-body ${s.open ? '' : 'hidden'}" data-section-body="${s.key}">
          <div id="wrows_${s.key}"></div>
          <button type="button" class="text-xs text-emerald-400 mt-2" data-add-row="${s.key}"><i class="fa-solid fa-plus mr-1"></i>Add row</button>
        </div>
      </div>`).join('');
    host.querySelectorAll('[data-section-toggle]').forEach((n) => n.addEventListener('click', () => {
      const b = host.querySelector(`[data-section-body="${n.getAttribute('data-section-toggle')}"]`);
      if (b) b.classList.toggle('hidden');
    }));
    host.querySelectorAll('[data-add-row]').forEach((n) => n.addEventListener('click', () => addRow(n.getAttribute('data-add-row'))));
  }

  function fieldHtml(f, val) {
    const cls = `wlog-cell${f.mHide ? ' wlog-hide-mobile' : ''}`;
    const style = cellStyle(f);
    if (f.type === 'select') return `<select class="${cls}" style="${style}" data-field="${f.k}">${f.options.map((o) => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    const step = f.step ? ` step="${f.step}"` : '';
    const min = f.type === 'number' ? ' min="0"' : '';
    return `<input type="${f.type}" class="${cls}" style="${style}" data-field="${f.k}" placeholder="${esc(f.ph)}" value="${esc(val || '')}"${step}${min}>`;
  }

  function addRow(key, data) {
    const s = SECTIONS.find((x) => x.key === key);
    const c = el(`wrows_${key}`);
    if (!s || !c) return;
    const row = document.createElement('div');
    row.className = 'wlog-row';
    row.setAttribute('data-row', '');
    row.innerHTML = s.fields.map((f) => fieldHtml(f, (data || {})[f.k])).join('')
      + `<button type="button" class="text-red-400 hover:text-red-300 px-2 shrink-0" style="flex:0 0 24px" data-remove-row><i class="fa-solid fa-trash text-xs"></i></button>`;
    row.querySelector('[data-remove-row]').addEventListener('click', () => { row.remove(); updateCounts(); });
    c.appendChild(row);
    updateCounts();
  }

  function collectRows(key) {
    const c = el(`wrows_${key}`);
    if (!c) return [];
    const out = [];
    c.querySelectorAll('[data-row]').forEach((row) => {
      const obj = {};
      row.querySelectorAll('[data-field]').forEach((inp) => { obj[inp.getAttribute('data-field')] = (inp.value || '').trim(); });
      out.push(obj);
    });
    return out;
  }

  function updateCounts() {
    SECTIONS.forEach((s) => { const c = el(`wrows_${s.key}`); const p = el(`wcount_${s.key}`); if (c && p) p.textContent = c.querySelectorAll('[data-row]').length; });
  }

  function loadDetailsIntoForm(details) {
    SECTIONS.forEach((s) => { const c = el(`wrows_${s.key}`); if (c) c.innerHTML = ''; });
    SECTIONS.forEach((s) => (details[s.key] || []).forEach((r) => addRow(s.key, r)));
    updateCounts();
  }

  // ---------- Compile ----------
  async function compile() {
    const pid = parseInt(el('wlogProject').value, 10) || projectId();
    const start = el('wlogStart').value;
    const end = el('wlogEnd').value;
    const ptype = el('wlogPeriodType').value;
    if (!pid || !start || !end) { alert('Choose project and date range first.'); return; }
    el('wlogCompileHint').textContent = 'Compiling…';
    try {
      const res = await fetch(`/api/weekly-reports/compile?project_id=${pid}&start=${start}&end=${end}&period_type=${ptype}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Compile failed');
      if (json.work_performed && !el('wlogWork').value.trim()) el('wlogWork').value = json.work_performed;
      loadDetailsIntoForm(json.details || {});
      el('wlogCompileHint').innerHTML = `<span class="text-emerald-400"><i class="fa-solid fa-check mr-1"></i>Compiled ${json.log_count} daily log(s). Edit rows as needed, then Save.</span>`;
    } catch (e) { el('wlogCompileHint').innerHTML = `<span class="text-red-400">Error: ${esc(e.message)}</span>`; }
  }

  // ---------- Modal ----------
  function populateProjects() {
    const sel = el('wlogProject');
    sel.innerHTML = (ctx.projects || []).map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    if (ctx.projectId) sel.value = String(ctx.projectId);
  }

  function defaultRange() {
    const today = new Date();
    const end = today.toISOString().slice(0, 10);
    const span = el('wlogPeriodType').value === 'biweekly' ? 13 : 6;
    const s = new Date(today.getTime() - span * 86400000).toISOString().slice(0, 10);
    el('wlogStart').value = s;
    el('wlogEnd').value = end;
  }

  function resetModal() {
    state.editingId = null;
    el('wlogModalTitle').textContent = 'New Weekly Log';
    el('wlogPeriodType').value = 'weekly';
    defaultRange();
    ['wlogWork', 'wlogSafety', 'wlogNotes'].forEach((id) => { el(id).value = ''; });
    el('wlogStatus').value = 'Submitted';
    el('wlogCompileHint').innerHTML = '<i class="fa-solid fa-circle-info mr-1"></i>Pick a period and tap <b>Compile</b> to pull data from the Daily Logs in that range. You can then add or remove any rows before saving.';
    SECTIONS.forEach((s) => { const c = el(`wrows_${s.key}`); if (c) c.innerHTML = ''; });
    updateCounts();
  }

  function openCreate() { resetModal(); populateProjects(); el('wlogModal').showModal(); }

  async function openEdit(id) {
    resetModal();
    populateProjects();
    try {
      const res = await fetch(`/api/weekly-reports/${id}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed');
      const r = json.report;
      state.editingId = id;
      el('wlogModalTitle').textContent = `Edit Weekly Log — ${periodLabel(r)}`;
      el('wlogProject').value = String(r.project_id);
      el('wlogPeriodType').value = r.period_type || 'weekly';
      if (r.period_start) el('wlogStart').value = r.period_start;
      if (r.period_end) el('wlogEnd').value = r.period_end;
      el('wlogWork').value = r.work_performed || '';
      el('wlogSafety').value = r.safety_notes || '';
      el('wlogNotes').value = r.notes || '';
      el('wlogStatus').value = r.status || 'Submitted';
      loadDetailsIntoForm(r.details || {});
      el('wlogDetailModal').close();
      el('wlogModal').showModal();
    } catch (e) { alert(e.message); }
  }

  async function save() {
    const pid = parseInt(el('wlogProject').value, 10);
    const end = el('wlogEnd').value;
    if (!pid || !end) { alert('Project and end date are required.'); return; }
    const payload = {
      project_id: pid,
      period_type: el('wlogPeriodType').value,
      period_start: el('wlogStart').value,
      period_end: end,
      work_performed: el('wlogWork').value.trim(),
      safety_notes: el('wlogSafety').value.trim(),
      notes: el('wlogNotes').value.trim(),
      status: el('wlogStatus').value,
    };
    SECTIONS.forEach((s) => { payload[s.key] = collectRows(s.key); });
    const btn = el('wlogSave');
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const url = state.editingId ? `/api/weekly-reports/${state.editingId}` : '/api/weekly-reports';
      const method = state.editingId ? 'PUT' : 'POST';
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Save failed');
      el('wlogModal').close();
      await loadList();
      if (global.showToast) global.showToast('Weekly log saved');
    } catch (e) { alert(e.message); }
    finally { btn.disabled = false; btn.textContent = 'Save Weekly Log'; }
  }

  // ---------- Print ----------
  const WLOG_PRINT_COLUMNS = [
    { key: 'period', label: 'Period', width: '18%' },
    { key: 'type', label: 'Type', width: '8%', align: 'center' },
    { key: 'workers', label: 'Man-Days', width: '8%', align: 'center' },
    { key: 'hours', label: 'Hours', width: '8%', align: 'center' },
    { key: 'work', label: 'Work<br>Performed', width: '40%' },
    { key: 'status', label: 'Status', width: '8%', align: 'center' },
  ];

  function getPrintMeta() {
    const nameEl = document.getElementById('currentProjectName');
    return {
      name: ctx.projectName || (nameEl?.textContent || '').trim() || 'Project',
      number: projectId() || '',
      location: '',
    };
  }

  function reportRegisterRow(r) {
    return {
      period: periodLabel(r),
      type: r.period_type || 'weekly',
      workers: r.total_workers ?? '—',
      hours: r.total_hours ?? '—',
      work: (r.work_performed || '—').split('\n')[0],
      status: r.status || 'Draft',
    };
  }

  async function triggerWeeklyPrint(html) {
    if (global.CasePMOutput) {
      await global.CasePMOutput.deliverHtml({
        title: 'Weekly Log',
        html,
        filenameBase: `Weekly_Log_${projectId() || 'project'}`,
        sourceModule: 'weekly_log',
        systemFolderKey: 'weekly-logs',
        subfolder: 'Exports',
        printOptions: { bodyHtml: html, containerId: 'wlogPrintSheet', bodyClass: 'printing-weekly-log' },
      });
      return;
    }
    global.CasePMPrint.triggerPrintPreview(html, { containerId: 'wlogPrintSheet', bodyClass: 'printing-weekly-log' });
  }

  async function printLog() {
    if (typeof global.CasePMPrint === 'undefined') {
      alert('Print module not loaded.');
      return;
    }
    const rows = filtered().map(reportRegisterRow);
    const html = global.CasePMPrint.buildPrintDocument({
      meta: getPrintMeta(),
      sections: [{ title: 'WEEKLY LOG REGISTER', columns: WLOG_PRINT_COLUMNS, rows, emptyMessage: 'No weekly logs to print.' }],
      rowsPerPage: 24,
    });
    await triggerWeeklyPrint(html);
  }

  function buildWeeklyReportBody(r) {
    const d = r.details || {};
    const block = (title, rows, render) => (rows && rows.length)
      ? `<div><h3>${esc(title)}</h3>${rows.map(render).join('')}</div>` : '';
    return `
      <div class="casepm-log-meta">
        <span><strong>Status:</strong> ${esc(r.status || 'Draft')}</span>
        <span><strong>Period:</strong> ${esc(periodLabel(r))}</span>
        <span><strong>Type:</strong> ${esc(r.period_type || 'weekly')}</span>
        <span><strong>Man-days:</strong> ${r.total_workers || 0}</span>
        <span><strong>Hours:</strong> ${r.total_hours || 0}</span>
        ${r.author ? `<span><strong>By:</strong> ${esc(r.author)}</span>` : ''}
      </div>
      <div><h3>Summary</h3><div class="casepm-log-block">${esc(r.work_performed || '—')}</div></div>
      ${r.safety_notes ? `<div><h3>Safety</h3><div class="casepm-log-block">${esc(r.safety_notes)}</div></div>` : ''}
      ${r.notes ? `<div><h3>Notes</h3><div class="casepm-log-block">${esc(r.notes)}</div></div>` : ''}
      ${block('Manpower', d.manpower, (m) => `<div class="casepm-log-line">• ${esc(m.company || '—')} — ${m.days || 0} days · ${m.workers || 0} man-days · ${m.hours || 0} hrs</div>`)}
      ${block('Equipment', d.equipment, (e) => `<div class="casepm-log-line">• ${esc(e.equipment_name)} ${e.days ? '· ' + esc(e.days) + ' days' : ''} ${e.notes ? '· ' + esc(e.notes) : ''}</div>`)}
      ${block('Deliveries', d.deliveries, (x) => `<div class="casepm-log-line">• ${esc(x.item)} ${x.supplier ? 'from ' + esc(x.supplier) : ''} ${x.quantity ? '· ' + esc(x.quantity) : ''}</div>`)}
      ${block('Delays', d.delays, (x) => `<div class="casepm-log-line">• [${esc(x.type)}] ${esc(x.description)} ${x.hours_lost ? '· ' + esc(x.hours_lost) + 'h' : ''}</div>`)}
      ${block('Visitors', d.visitors, (x) => `<div class="casepm-log-line">• ${esc(x.name)} ${x.company ? '(' + esc(x.company) + ')' : ''} ${x.purpose ? '· ' + esc(x.purpose) : ''}</div>`)}
      ${block('Safety', d.safety, (x) => `<div class="casepm-log-line">• [${esc(x.type)}] ${esc(x.description)} ${x.action ? '→ ' + esc(x.action) : ''}</div>`)}
      ${block('Inspections', d.inspections, (x) => `<div class="casepm-log-line">• ${esc(x.type)} ${x.agency ? '(' + esc(x.agency) + ')' : ''} — ${esc(x.result || '')}</div>`)}
      ${block('Daily Summaries', d.daily_summaries, (x) => `<div class="casepm-log-line">• <span style="color:#555">${esc(x.date)}</span> ${esc(x.work)}</div>`)}
    `;
  }

  async function printDetail() {
    if (!state.viewingReport) return;
    if (typeof global.CasePMPrint === 'undefined') {
      alert('Print module not loaded.');
      return;
    }
    const meta = getPrintMeta();
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const title = `WEEKLY LOG — ${periodLabel(state.viewingReport)}`;
    const html = `<div class="casepm-print-page">
      <div class="casepm-print-header">
        <div><div class="casepm-print-title">${esc(title)}</div></div>
        <div class="casepm-print-meta">
          ${meta.number ? `<div><span class="label">PROJECT ID</span><br>${esc(meta.number)}</div>` : ''}
          ${meta.name ? `<div style="margin-top:4px"><span class="label">PROJECT NAME</span><br>${esc(meta.name)}</div>` : ''}
        </div>
      </div>
      <div class="casepm-log-report">${buildWeeklyReportBody(state.viewingReport)}</div>
      <div class="casepm-print-footer">
        <span>Confidential</span>
        <span class="center">${esc(printedOn)}</span>
        <span class="right">Page 1</span>
      </div>
    </div>`;
    await triggerWeeklyPrint(html);
  }

  // ---------- Detail ----------
  async function openDetail(id) {
    try {
      const res = await fetch(`/api/weekly-reports/${id}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed');
      const r = json.report; const d = r.details || {};
      state.viewingReport = r;
      el('wlogDetailTitle').textContent = `Weekly Log — ${periodLabel(r)}`;
      const block = (title, rows, render) => (rows && rows.length) ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">${title}</div>${rows.map(render).join('')}</div>` : '';
      el('wlogDetailBody').innerHTML = `
        <div class="flex flex-wrap gap-3 items-center">
          ${statusBadge(r.status)}
          <span class="text-zinc-400 capitalize"><i class="fa-solid fa-calendar-week mr-1"></i>${esc(r.period_type || 'weekly')}</span>
          <span class="text-zinc-400"><i class="fa-solid fa-users mr-1"></i>${r.total_workers || 0} man-days</span>
          <span class="text-zinc-400"><i class="fa-solid fa-clock mr-1"></i>${r.total_hours || 0} hrs</span>
          ${r.author ? `<span class="text-zinc-500 text-xs">by ${esc(r.author)}</span>` : ''}
        </div>
        <div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Summary</div><div class="whitespace-pre-wrap">${esc(r.work_performed || '—')}</div></div>
        ${r.safety_notes ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Safety</div><div class="whitespace-pre-wrap">${esc(r.safety_notes)}</div></div>` : ''}
        ${block('Manpower', d.manpower, (m) => `<div class="text-sm">• ${esc(m.company || '—')} — ${m.days || 0} days · ${m.workers || 0} man-days · ${m.hours || 0} hrs</div>`)}
        ${block('Equipment', d.equipment, (e) => `<div class="text-sm">• ${esc(e.equipment_name)} ${e.days ? '· ' + esc(e.days) + ' days' : ''} ${e.notes ? '· ' + esc(e.notes) : ''}</div>`)}
        ${block('Deliveries', d.deliveries, (x) => `<div class="text-sm">• ${esc(x.item)} ${x.supplier ? 'from ' + esc(x.supplier) : ''} ${x.quantity ? '· ' + esc(x.quantity) : ''}</div>`)}
        ${block('Delays', d.delays, (x) => `<div class="text-sm text-red-300">• [${esc(x.type)}] ${esc(x.description)} ${x.hours_lost ? '· ' + esc(x.hours_lost) + 'h' : ''}</div>`)}
        ${block('Visitors', d.visitors, (x) => `<div class="text-sm">• ${esc(x.name)} ${x.company ? '(' + esc(x.company) + ')' : ''} ${x.purpose ? '· ' + esc(x.purpose) : ''}</div>`)}
        ${block('Safety', d.safety, (x) => `<div class="text-sm text-yellow-300">• [${esc(x.type)}] ${esc(x.description)} ${x.action ? '→ ' + esc(x.action) : ''}</div>`)}
        ${block('Inspections', d.inspections, (x) => `<div class="text-sm">• ${esc(x.type)} ${x.agency ? '(' + esc(x.agency) + ')' : ''} — <b>${esc(x.result || '')}</b></div>`)}
        ${block('Daily Summaries', d.daily_summaries, (x) => `<div class="text-sm">• <span class="text-zinc-500">${esc(x.date)}</span> ${esc(x.work)}</div>`)}
      `;
      el('wlogDetailEdit').onclick = () => openEdit(id);
      el('wlogDetailPrint').onclick = () => printDetail();
      el('wlogDetailModal').showModal();
    } catch (e) { alert(e.message); }
  }

  function bind() {
    el('wlogBtnNew').addEventListener('click', openCreate);
    el('wlogBtnPrint')?.addEventListener('click', printLog);
    el('wlogBtnRefresh')?.addEventListener('click', loadList);
    el('wlogModalClose').addEventListener('click', () => el('wlogModal').close());
    el('wlogCancel').addEventListener('click', () => el('wlogModal').close());
    el('wlogSave').addEventListener('click', save);
    el('wlogCompileBtn').addEventListener('click', compile);
    el('wlogPeriodType').addEventListener('change', defaultRange);
    el('wlogDetailClose').addEventListener('click', () => el('wlogDetailModal').close());
    ['wlogSearch', 'wlogStatusFilter'].forEach((id) => { el(id).addEventListener('input', renderList); el(id).addEventListener('change', renderList); });
    global.addEventListener('casepm:project-changed', onProjectChange);
    global.onCasePmProjectChanged = (pid) => { ctx.projectId = pid; onProjectChange(); };
  }
  function onProjectChange() { loadList(); }

  function init() { buildSectionsHost(); bind(); loadList(); }

  global.CasePMWeekly = { refresh: loadList, openCreate, printLog, printDetail };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
