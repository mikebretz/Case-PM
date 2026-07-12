/**
 * Case PM — Permits & Inspections (Florida FBC tracking, calendar, schedule sync, jurisdiction directory).
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_PERMITS_CTX || {};
  const STATUS_COLORS = {
    'Not Started': 'bg-zinc-600/30 text-zinc-300',
    'Application Submitted': 'bg-blue-500/20 text-blue-300',
    'In Review': 'bg-indigo-500/20 text-indigo-300',
    'Issued': 'bg-cyan-500/20 text-cyan-300',
    'Scheduled': 'bg-sky-500/20 text-sky-300',
    'Inspection Requested': 'bg-violet-500/20 text-violet-300',
    'Passed': 'bg-emerald-500/20 text-emerald-300',
    'Failed': 'bg-red-500/20 text-red-300',
    'Correction Required': 'bg-amber-500/20 text-amber-300',
    'Re-inspection Scheduled': 'bg-orange-500/20 text-orange-300',
    'Closed': 'bg-emerald-700/30 text-emerald-200',
    'Cancelled': 'bg-zinc-700 text-zinc-500',
  };
  const EV_COLORS = {
    'Not Started': '#52525b', 'Scheduled': '#0ea5e9', 'Inspection Requested': '#8b5cf6',
    'Passed': '#059669', 'Failed': '#dc2626', 'Correction Required': '#d97706',
    'Issued': '#06b6d4', 'Closed': '#10b981',
  };

  const state = {
    items: [], stats: {}, statuses: [], trades: [], catalog: null,
    users: [], reminderOptions: [],
    view: 'cal', panel: 'tracker', editId: null, month: new Date(),
    selectedJurisdiction: null, dirResults: [],
  };

  function projectId() {
    return ctx.projectId || (function () {
      try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; }
    })();
  }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(id) { return document.getElementById(id); }
  function iso(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
  async function api(url, opts) { const r = await fetch(url, opts); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Request failed'); return j; }

  async function loadCatalog() {
    if (state.catalog) return state.catalog;
    state.catalog = await api('/api/permits-inspections/catalog');
    return state.catalog;
  }

  async function load() {
    const pid = projectId();
    el('piStatusText').textContent = 'Loading…';
    try {
      await loadCatalog();
      const j = await api(`/api/permits-inspections${pid ? `?project_id=${pid}` : ''}`);
      state.items = j.items || [];
      state.stats = j.stats || {};
      state.statuses = j.statuses || [];
      state.trades = j.trades || state.catalog?.trades || [];
      state.users = j.users || [];
      state.reminderOptions = j.reminder_options || [];
      ctx.scheduleUrl = j.schedule_url || ctx.scheduleUrl;
      const badge = el('piProjectBadge');
      if (badge) badge.textContent = ctx.projectName || 'Select a project';
      populateFilters();
      renderReminderOptions();
      populateNotifyUsers();
      renderStats();
      render();
      el('piUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      el('piStatusText').textContent = `${state.items.length} item(s) · ${state.stats.synced || 0} on schedule · ${state.stats.passed || 0} passed`;
      const params = new URLSearchParams(window.location.search);
      if (params.get('open') === '1' && params.get('item_id')) {
        const id = parseInt(params.get('item_id'), 10);
        if (id) openEdit(id);
      }
    } catch (e) { el('piStatusText').textContent = 'Error: ' + e.message; }
  }

  function populateFilters() {
    const sf = el('piStatusFilter');
    if (sf && sf.options.length <= 1) {
      state.statuses.forEach((s) => sf.add(new Option(s, s)));
    }
    const tf = el('piTradeFilter');
    if (tf && tf.options.length <= 1) {
      state.trades.forEach((t) => tf.add(new Option(t.label, t.key)));
    }
    const tpl = el('piTemplateTrade');
    if (tpl && tpl.options.length <= 1) {
      state.trades.forEach((t) => tpl.add(new Option(t.label, t.key)));
    }
    populateTradeSelect(el('piTrade'));
  }

  function populateTradeSelect(sel, val) {
    if (!sel) return;
    const current = val || sel.value || 'building';
    sel.innerHTML = state.trades.length
      ? state.trades.map((t) => `<option value="${esc(t.key)}" ${t.key === current ? 'selected' : ''}>${esc(t.label)}</option>`).join('')
      : '<option value="building">Building / Structural</option>';
  }

  function renderStats() {
    const s = state.stats;
    const map = {
      pistatTotal: s.total, pistatPermits: s.permits, pistatInspections: s.inspections,
      pistatWeek: s.this_week, pistatUpcoming: s.upcoming, pistatPassed: s.passed,
      pistatFailed: s.failed, pistatSynced: s.synced,
    };
    Object.keys(map).forEach((id) => { if (el(id)) el(id).textContent = map[id] ?? 0; });
  }

  function filtered() {
    const term = (el('piSearch')?.value || '').toLowerCase();
    const sf = el('piStatusFilter')?.value || '';
    const tf = el('piTradeFilter')?.value || '';
    const kf = el('piKindFilter')?.value || '';
    return state.items.filter((it) => {
      if (sf && it.status !== sf) return false;
      if (tf && it.trade !== tf) return false;
      if (kf && it.record_kind !== kf) return false;
      if (term) {
        const blob = `${it.item_number} ${it.title} ${it.trade} ${it.jurisdiction_name} ${it.permit_number} ${it.inspector}`.toLowerCase();
        if (!blob.includes(term)) return false;
      }
      return true;
    });
  }

  function render() {
    if (state.panel === 'directory') renderDirectory();
    else if (state.view === 'list') renderList();
    else renderCalendar();
  }

  function renderCalendar() {
    el('piCalHost')?.classList.remove('hidden');
    el('piListHost')?.classList.add('hidden');
    el('piCalNav').style.display = '';
    const y = state.month.getFullYear(), m = state.month.getMonth();
    el('piMonthLabel').textContent = state.month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    const first = new Date(y, m, 1);
    const gridStart = new Date(y, m, 1 - first.getDay());
    const byDate = {};
    filtered().forEach((it) => {
      if (!it.scheduled_date) return;
      (byDate[it.scheduled_date] = byDate[it.scheduled_date] || []).push(it);
    });
    const todayIso = iso(new Date());
    let html = '';
    for (let i = 0; i < 42; i++) {
      const cur = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
      const ci = iso(cur);
      const other = cur.getMonth() !== m;
      const evs = byDate[ci] || [];
      html += `<div class="cal-cell ${other ? 'other' : ''} ${ci === todayIso ? 'today' : ''}" data-newdate="${ci}">
        <div class="flex items-center justify-between"><span class="cal-num">${cur.getDate()}</span>${evs.length > 3 ? `<span class="text-[9px] text-zinc-500">+${evs.length - 3}</span>` : ''}</div>
        ${evs.slice(0, 3).map((it) => `<div class="cal-ev" data-open="${it.id}" style="background:${EV_COLORS[it.status] || '#f97316'};color:#fff;" title="${esc(it.title)}">${it.synced_to_schedule ? '🔗 ' : ''}${esc(it.title)}</div>`).join('')}
      </div>`;
    }
    el('piCalBody').innerHTML = html;
    el('piCalBody').querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', (e) => { e.stopPropagation(); openEdit(parseInt(n.getAttribute('data-open'), 10)); }));
    el('piCalBody').querySelectorAll('[data-newdate]').forEach((n) => n.addEventListener('click', () => openCreate(n.getAttribute('data-newdate'))));
  }

  function renderList() {
    el('piCalHost')?.classList.add('hidden');
    el('piListHost')?.classList.remove('hidden');
    el('piCalNav').style.display = 'none';
    const rows = filtered().slice().sort((a, b) => (a.scheduled_date || '9999').localeCompare(b.scheduled_date || '9999'));
    const host = el('piListHost');
    if (!rows.length) {
      host.innerHTML = '<div class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-clipboard-check text-4xl mb-3 block text-zinc-600"></i>No permits or inspections. Add one or import an FBC checklist.</div>';
      return;
    }
    host.innerHTML = `<table class="w-full text-sm"><thead class="bg-zinc-800 text-xs uppercase text-zinc-500 sticky top-0"><tr>
      <th class="text-left px-3 py-2">#</th><th class="text-left px-3 py-2">Type</th><th class="text-left px-3 py-2">Trade</th>
      <th class="text-left px-3 py-2">Title</th><th class="text-left px-3 py-2">Date</th><th class="text-left px-3 py-2">Jurisdiction</th><th class="text-left px-3 py-2">Status</th><th class="px-3 py-2"></th>
    </tr></thead><tbody>${rows.map((it) => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" data-open="${it.id}">
        <td class="px-3 py-2 font-mono text-xs">${esc(it.item_number)}</td>
        <td class="px-3 py-2 capitalize text-xs">${esc(it.record_kind)}</td>
        <td class="px-3 py-2 text-xs">${esc((it.trade || '').replace('_', ' '))}</td>
        <td class="px-3 py-2">${esc(it.title)}${it.synced_to_schedule ? ' <span class="text-violet-400 text-xs">🔗</span>' : ''}</td>
        <td class="px-3 py-2 text-xs whitespace-nowrap">${esc(it.scheduled_date || '—')}${it.scheduled_time ? ' ' + esc(it.scheduled_time) : ''}</td>
        <td class="px-3 py-2 text-xs text-zinc-400">${esc(it.jurisdiction_name || '—')}</td>
        <td class="px-3 py-2"><span class="pi-chip ${STATUS_COLORS[it.status] || 'bg-zinc-700'}">${esc(it.status)}</span></td>
        <td class="px-3 py-2 text-zinc-500"><i class="fa-solid fa-chevron-right"></i></td>
      </tr>`).join('')}</tbody></table>`;
    host.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openEdit(parseInt(n.getAttribute('data-open'), 10))));
  }

  async function renderDirectory() {
    el('piCalHost')?.classList.add('hidden');
    el('piListHost')?.classList.remove('hidden');
    el('piCalNav').style.display = 'none';
    const q = el('piDirSearch')?.value || '';
    const cat = el('piDirCategory')?.value || 'all';
    try {
      const j = await api(`/api/permits-inspections/directory?q=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}`);
      const results = j.results || [];
      state.dirResults = results;
      const host = el('piListHost');
      if (!results.length) {
        host.innerHTML = '<div class="px-6 py-12 text-center text-zinc-500">No jurisdictions found. Try a different search.</div>';
        return;
      }
      host.innerHTML = `<div class="p-4 grid gap-2">${results.map((r, idx) => `
        <div class="border border-zinc-700 rounded-md p-3 bg-zinc-900 hover:border-zinc-500 cursor-pointer pi-dir-row" data-dir-idx="${idx}">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="font-medium text-sm">${esc(r.display || r.name)}</div>
              <div class="text-xs text-zinc-500 mt-0.5">${esc(r.building_dept || r.role || r.region || '')}</div>
            </div>
            <span class="text-[10px] uppercase tracking-wide text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">${esc(r.type)}</span>
          </div>
          <div class="text-xs text-zinc-400 mt-2 flex flex-wrap gap-3">
            ${r.phone ? `<span><i class="fa-solid fa-phone mr-1"></i>${esc(r.phone)}</span>` : ''}
            ${r.url ? `<a href="${esc(r.url)}" target="_blank" class="text-emerald-400 hover:underline" onclick="event.stopPropagation()">Website</a>` : ''}
          </div>
        </div>`).join('')}</div>`;
      host.querySelectorAll('.pi-dir-row').forEach((row) => {
        row.addEventListener('click', () => {
          const idx = parseInt(row.getAttribute('data-dir-idx'), 10);
          const r = state.dirResults[idx];
          if (!r) return;
          state.selectedJurisdiction = r;
          el('piJurisdictionName').value = r.display || r.name || '';
          el('piAuthorityName').value = r.building_dept || r.name || '';
          el('piAuthorityPhone').value = r.phone || '';
          el('piAuthorityUrl').value = r.url || '';
          if (r.type && el('piJurisdictionLevel')) {
            const map = { county: 'county', city: 'city', state: 'state', utility: 'utility', water_management: 'water_management', fire: 'fire_district' };
            const lvl = map[r.type] || el('piJurisdictionLevel').value;
            el('piJurisdictionLevel').value = lvl;
          }
          if (global.showToast) global.showToast('Jurisdiction applied to form');
        });
      });
    } catch (e) {
      el('piListHost').innerHTML = `<div class="px-6 py-8 text-red-400">${esc(e.message)}</div>`;
    }
  }

  function setPanel(panel) {
    state.panel = panel;
    ['tracker', 'directory'].forEach((p) => {
      el(`piTab${p.charAt(0).toUpperCase() + p.slice(1)}`)?.classList.toggle('bg-zinc-700', p === panel);
    });
    el('piDirFilters')?.classList.toggle('hidden', panel !== 'directory');
    el('piTrackerFilters')?.classList.toggle('hidden', panel === 'directory');
    el('piTemplatePanel')?.classList.toggle('hidden', panel !== 'tracker');
    render();
  }

  function populateNotifyUsers() {
    const sel = el('piNotifyUsers');
    if (!sel) return;
    const selected = new Set([...(sel.selectedOptions || [])].map(o => o.value));
    sel.innerHTML = state.users.map((u) =>
      `<option value="${u.id}">${esc(u.name)}${u.role ? ` (${esc(u.role)})` : ''}</option>`
    ).join('');
    [...sel.options].forEach((o) => { o.selected = selected.has(o.value); });
  }

  function renderReminderOptions() {
    const host = el('piReminderOffsets');
    if (!host) return;
    const opts = state.reminderOptions.length ? state.reminderOptions : [
      { key: 'morning_of', label: 'Morning of (8:00 AM)' },
      { key: '1d', label: '1 day before' },
      { key: '1h', label: '1 hour before' },
      { key: '15m', label: '15 minutes before' },
    ];
    host.innerHTML = opts.map((o) => `
      <label class="flex items-center gap-2 cursor-pointer bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5">
        <input type="checkbox" class="pi-reminder-offset accent-emerald-500" value="${esc(o.key)}" ${['morning_of', '1h'].includes(o.key) ? 'checked' : ''}>
        <span>${esc(o.label)}</span>
      </label>`).join('');
  }

  function getSelectedReminderOffsets() {
    return [...document.querySelectorAll('.pi-reminder-offset:checked')].map((n) => n.value);
  }

  function setReminderOffsets(offsets) {
    const set = new Set(offsets || []);
    document.querySelectorAll('.pi-reminder-offset').forEach((n) => { n.checked = set.has(n.value); });
  }

  function getSelectedNotifyUserIds() {
    const sel = el('piNotifyUsers');
    if (!sel) return [];
    return [...sel.selectedOptions].map((o) => parseInt(o.value, 10)).filter(Boolean);
  }

  function setSelectedNotifyUserIds(ids) {
    const sel = el('piNotifyUsers');
    if (!sel) return;
    const set = new Set((ids || []).map(String));
    [...sel.options].forEach((o) => { o.selected = set.has(o.value); });
  }

  function resetModal() {
    state.editId = null;
    el('piModalTitle').textContent = 'New Permit / Inspection';
    ['piTitle', 'piDescription', 'piPermitNumber', 'piJurisdictionName', 'piAuthorityName',
      'piAuthorityPhone', 'piAuthorityUrl', 'piInspector', 'piLocation', 'piResultNotes', 'piCorrectionNotes', 'piFbcRef'].forEach((id) => {
      if (el(id)) el(id).value = '';
    });
    el('piDate').value = iso(new Date());
    el('piTime').value = '';
    el('piDuration').value = 1;
    el('piRecordKind').value = 'inspection';
    populateTradeSelect(el('piTrade'), 'building');
    el('piPhase').value = '';
    el('piJurisdictionLevel').value = 'county';
    fillSelect(el('piStatus'), state.statuses.length ? state.statuses : ['Not Started'], 'Not Started');
    el('piPush').checked = false;
    el('piSyncedBadge').classList.add('hidden');
    el('piDelete').classList.add('hidden');
    el('piNotifyNow')?.classList.add('hidden');
    if (el('piNotifyCreator')) el('piNotifyCreator').checked = true;
    setSelectedNotifyUserIds([]);
    setReminderOffsets(['morning_of', '1h']);
    if (state.selectedJurisdiction) {
      el('piJurisdictionName').value = state.selectedJurisdiction.display || state.selectedJurisdiction.name || '';
      el('piAuthorityName').value = state.selectedJurisdiction.building_dept || '';
      el('piAuthorityPhone').value = state.selectedJurisdiction.phone || '';
      el('piAuthorityUrl').value = state.selectedJurisdiction.url || '';
    }
  }

  function openCreate(dateStr) {
    resetModal();
    if (dateStr) el('piDate').value = dateStr;
    el('piModal').showModal();
  }

  function openEdit(id) {
    const it = state.items.find((x) => x.id === id);
    if (!it) return;
    resetModal();
    state.editId = id;
    el('piModalTitle').textContent = it.item_number || 'Permit / Inspection';
    el('piTitle').value = it.title || '';
    el('piDescription').value = it.description || '';
    el('piPermitNumber').value = it.permit_number || '';
    el('piJurisdictionName').value = it.jurisdiction_name || '';
    el('piAuthorityName').value = it.authority_name || '';
    el('piAuthorityPhone').value = it.authority_phone || '';
    el('piAuthorityUrl').value = it.authority_url || '';
    el('piInspector').value = it.inspector || '';
    el('piLocation').value = it.location || '';
    el('piResultNotes').value = it.result_notes || '';
    el('piCorrectionNotes').value = it.correction_notes || '';
    el('piFbcRef').value = it.fbc_reference || '';
    el('piDate').value = it.scheduled_date || iso(new Date());
    el('piTime').value = it.scheduled_time || '';
    el('piDuration').value = it.duration_days || 1;
    el('piRecordKind').value = it.record_kind || 'inspection';
    populateTradeSelect(el('piTrade'), it.trade || 'building');
    el('piPhase').value = it.inspection_phase || '';
    el('piJurisdictionLevel').value = it.jurisdiction_level || 'county';
    fillSelect(el('piStatus'), state.statuses, it.status);
    el('piPush').checked = it.synced_to_schedule;
    el('piSyncedBadge').classList.toggle('hidden', !it.synced_to_schedule);
    el('piDelete').classList.remove('hidden');
    el('piNotifyNow')?.classList.remove('hidden');
    if (el('piNotifyCreator')) el('piNotifyCreator').checked = it.notify_creator !== false;
    setSelectedNotifyUserIds(it.notify_user_ids || []);
    setReminderOffsets(it.reminder_offsets || ['morning_of', '1h']);
    el('piModal').showModal();
  }

  function fillSelect(sel, opts, val) {
    if (!sel) return;
    sel.innerHTML = opts.map((o) => {
      const v = typeof o === 'string' ? o : (o.key || o.label);
      const label = typeof o === 'string' ? o : (o.label || o.key);
      return `<option value="${esc(v)}" ${v === val ? 'selected' : ''}>${esc(label)}</option>`;
    }).join('');
  }

  function collectPayload() {
    return {
      project_id: projectId(),
      record_kind: el('piRecordKind').value,
      trade: el('piTrade').value,
      inspection_phase: el('piPhase').value.trim(),
      title: el('piTitle').value.trim(),
      description: el('piDescription').value.trim(),
      fbc_reference: el('piFbcRef').value.trim(),
      permit_number: el('piPermitNumber').value.trim(),
      jurisdiction_level: el('piJurisdictionLevel').value,
      jurisdiction_name: el('piJurisdictionName').value.trim(),
      authority_name: el('piAuthorityName').value.trim(),
      authority_phone: el('piAuthorityPhone').value.trim(),
      authority_url: el('piAuthorityUrl').value.trim(),
      scheduled_date: el('piDate').value,
      scheduled_time: el('piTime').value.trim(),
      duration_days: el('piDuration').value,
      status: el('piStatus').value,
      inspector: el('piInspector').value.trim(),
      location: el('piLocation').value.trim(),
      result_notes: el('piResultNotes').value.trim(),
      correction_notes: el('piCorrectionNotes').value.trim(),
      push_to_schedule: el('piPush').checked,
      notify_creator: el('piNotifyCreator')?.checked !== false,
      notify_user_ids: getSelectedNotifyUserIds(),
      reminder_offsets: getSelectedReminderOffsets(),
      send_notifications: true,
    };
  }

  async function notifyNow() {
    if (!state.editId) return;
    const btn = el('piNotifyNow');
    if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
    try {
      const j = await api(`/api/permits-inspections/${state.editId}/notify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notify_user_ids: getSelectedNotifyUserIds() }),
      });
      if (global.showToast) global.showToast(`Reminder sent to ${j.notified || 0} person(s)`);
    } catch (e) { alert(e.message); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Send reminder now'; }
    }
  }

  async function save() {
    const payload = collectPayload();
    if (!payload.project_id || !payload.title) { alert('Project and title are required.'); return; }
    const btn = el('piSave');
    btn.disabled = true;
    btn.textContent = 'Saving…';
    try {
      const url = state.editId ? `/api/permits-inspections/${state.editId}` : '/api/permits-inspections';
      await api(url, { method: state.editId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      el('piModal').close();
      await load();
      if (global.showToast) global.showToast('Saved');
    } catch (e) { alert(e.message); }
    finally { btn.disabled = false; btn.textContent = 'Save'; }
  }

  async function del() {
    if (!state.editId || !confirm('Delete this permit/inspection record?')) return;
    try {
      await api(`/api/permits-inspections/${state.editId}`, { method: 'DELETE' });
      el('piModal').close();
      await load();
    } catch (e) { alert(e.message); }
  }

  async function importTemplate() {
    const pid = projectId();
    const trade = el('piTemplateTrade').value;
    if (!pid) { alert('Select a project first.'); return; }
    if (!confirm(`Import full FBC inspection checklist for ${trade}? This creates multiple tracking rows.`)) return;
    try {
      const j = await api('/api/permits-inspections/from-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: pid,
          trade,
          scheduled_date: el('piTemplateDate').value || iso(new Date()),
          push_to_schedule: el('piTemplatePush').checked,
          jurisdiction: state.selectedJurisdiction || {
            name: el('piJurisdictionName')?.value,
            building_dept: el('piAuthorityName')?.value,
            phone: el('piAuthorityPhone')?.value,
            url: el('piAuthorityUrl')?.value,
          },
        }),
      });
      await load();
      if (global.showToast) global.showToast(`Imported ${j.count} checklist items`);
    } catch (e) { alert(e.message); }
  }

  async function pushAll() {
    const pid = projectId();
    if (!pid) { alert('Select a project first.'); return; }
    if (!confirm('Push all dated permits/inspections to the Schedule?')) return;
    try {
      const j = await api(`/api/permits-inspections/push-to-schedule?project_id=${pid}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      await load();
      const go = confirm(`Pushed ${j.pushed} item(s). Open Schedule now?`);
      if (go) window.location.href = (ctx.scheduleUrl || '/schedule') + `?project_id=${pid}`;
    } catch (e) { alert(e.message); }
  }

  async function importFromSchedule() {
    const pid = projectId();
    if (!pid) { alert('Select a project first.'); return; }
    try {
      const j = await api(`/api/permits-inspections/import-from-schedule?project_id=${pid}`, { method: 'POST' });
      await load();
      if (global.showToast) global.showToast(`Imported ${j.imported} milestone(s) from schedule`);
    } catch (e) { alert(e.message); }
  }

  function setView(v) {
    state.view = v;
    if (state.panel !== 'tracker') setPanel('tracker');
    el('piViewCal').className = 'px-3 py-2 text-sm ' + (v === 'cal' ? 'bg-zinc-700' : 'bg-zinc-800');
    el('piViewList').className = 'px-3 py-2 text-sm ' + (v === 'list' ? 'bg-zinc-700' : 'bg-zinc-800');
    render();
  }

  function bind() {
    el('piBtnNew').addEventListener('click', () => openCreate());
    el('piBtnRefresh')?.addEventListener('click', load);
    el('piViewCal').addEventListener('click', () => setView('cal'));
    el('piViewList').addEventListener('click', () => setView('list'));
    el('piTabTracker').addEventListener('click', () => setPanel('tracker'));
    el('piTabDirectory').addEventListener('click', () => setPanel('directory'));
    el('piPushAll').addEventListener('click', pushAll);
    el('piImportSchedule').addEventListener('click', importFromSchedule);
    el('piImportTemplate').addEventListener('click', importTemplate);
    el('piPrev').addEventListener('click', () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1); render(); });
    el('piNext').addEventListener('click', () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1); render(); });
    el('piToday').addEventListener('click', () => { state.month = new Date(); render(); });
    el('piModalClose').addEventListener('click', () => el('piModal').close());
    el('piCancel').addEventListener('click', () => el('piModal').close());
    el('piSave').addEventListener('click', save);
    el('piDelete').addEventListener('click', del);
    el('piNotifyNow')?.addEventListener('click', notifyNow);
    ['piSearch', 'piStatusFilter', 'piTradeFilter', 'piKindFilter'].forEach((id) => {
      const node = el(id);
      if (!node) return;
      node.addEventListener('input', render);
      node.addEventListener('change', render);
    });
    el('piDirSearch')?.addEventListener('input', () => { if (state.panel === 'directory') renderDirectory(); });
    el('piDirCategory')?.addEventListener('change', () => { if (state.panel === 'directory') renderDirectory(); });
    if (el('piTemplateDate')) el('piTemplateDate').value = iso(new Date());
    global.addEventListener('casepm:project-changed', load);
    global.onCasePmProjectChanged = (pid) => { ctx.projectId = pid; load(); };
  }

  function init() { bind(); load(); }
  global.CasePMPermits = { refresh: load };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
