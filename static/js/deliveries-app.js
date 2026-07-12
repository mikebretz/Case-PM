/**
 * Case PM Deliveries — calendar scheduler with two-way Schedule sync.
 * Deliveries appear on a month calendar; push them to the Schedule as line items.
 * Adjusting those items in the Schedule flows back here (handled server-side).
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_DELIVERIES_CTX || {};
  const STATUS_COLORS = {
    'Scheduled': 'bg-zinc-600/30 text-zinc-300', 'Confirmed': 'bg-sky-500/20 text-sky-300',
    'In Transit': 'bg-indigo-500/20 text-indigo-300', 'Delivered': 'bg-emerald-500/20 text-emerald-300',
    'Partial': 'bg-amber-500/20 text-amber-300', 'Delayed': 'bg-red-500/20 text-red-300', 'Cancelled': 'bg-zinc-700 text-zinc-500',
  };
  const EV_COLORS = {
    'Scheduled': '#3f3f46', 'Confirmed': '#0284c7', 'In Transit': '#4f46e5',
    'Delivered': '#059669', 'Partial': '#d97706', 'Delayed': '#dc2626', 'Cancelled': '#52525b',
  };

  const state = { deliveries: [], stats: {}, statuses: [], view: 'cal', editId: null, month: new Date() };

  function projectId() { return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })(); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(id) { return document.getElementById(id); }
  function fmtDate(iso) { if (!iso) return ''; try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch (_) { return iso; } }
  function iso(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
  async function api(url, opts) { const r = await fetch(url, opts); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Request failed'); return j; }

  async function load() {
    const pid = projectId();
    el('delStatusText').textContent = 'Loading…';
    try {
      const j = await api(`/api/deliveries${pid ? `?project_id=${pid}` : ''}`);
      state.deliveries = j.deliveries || []; state.stats = j.stats || {}; state.statuses = j.statuses || [];
      if (el('delStatusFilter').options.length <= 1) state.statuses.forEach((s) => el('delStatusFilter').add(new Option(s, s)));
      renderStats(); render();
      el('delUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      el('delStatusText').textContent = `${state.deliveries.length} delivery(s) · ${state.stats.synced || 0} on schedule`;
    } catch (e) { el('delStatusText').textContent = 'Error: ' + e.message; }
  }

  function renderStats() {
    const s = state.stats;
    el('dstatTotal').textContent = s.total ?? 0;
    el('dstatWeek').textContent = s.this_week ?? 0;
    el('dstatUpcoming').textContent = s.upcoming ?? 0;
    el('dstatDelivered').textContent = s.delivered ?? 0;
    el('dstatDelayed').textContent = (s.delayed ?? 0) + (s.overdue ?? 0);
    el('dstatSynced').textContent = s.synced ?? 0;
  }

  function filtered() {
    const term = (el('delSearch').value || '').toLowerCase();
    const sf = el('delStatusFilter').value;
    return state.deliveries.filter((d) => {
      if (sf && d.status !== sf) return false;
      if (term && !`${d.delivery_number} ${d.supplier || ''} ${d.description || ''} ${d.po_number || ''}`.toLowerCase().includes(term)) return false;
      return true;
    });
  }

  function render() { state.view === 'list' ? renderList() : renderCalendar(); }

  function renderCalendar() {
    el('delCalHost').classList.remove('hidden'); el('delListHost').classList.add('hidden'); el('delCalNav').style.display = '';
    const y = state.month.getFullYear(), m = state.month.getMonth();
    el('delMonthLabel').textContent = state.month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    const first = new Date(y, m, 1);
    const startDay = first.getDay();
    const gridStart = new Date(y, m, 1 - startDay);
    const byDate = {};
    filtered().forEach((d) => { (byDate[d.delivery_date] = byDate[d.delivery_date] || []).push(d); });
    const todayIso = iso(new Date());
    let html = '';
    for (let i = 0; i < 42; i++) {
      const cur = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
      const ci = iso(cur);
      const other = cur.getMonth() !== m;
      const evs = byDate[ci] || [];
      html += `<div class="cal-cell ${other ? 'other' : ''} ${ci === todayIso ? 'today' : ''}" data-newdate="${ci}">
        <div class="flex items-center justify-between"><span class="cal-num">${cur.getDate()}</span>${evs.length > 3 ? `<span class="text-[9px] text-zinc-500">+${evs.length - 3}</span>` : ''}</div>
        ${evs.slice(0, 3).map((d) => `<div class="cal-ev" data-open="${d.id}" style="background:${EV_COLORS[d.status] || '#3f3f46'};color:#fff;" title="${esc(d.supplier || '')} — ${esc(d.description || '')}">${d.synced_to_schedule ? '🔗 ' : ''}${esc(d.supplier || d.description || 'Delivery')}</div>`).join('')}
      </div>`;
    }
    el('delCalBody').innerHTML = html;
    el('delCalBody').querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', (e) => { e.stopPropagation(); openEdit(parseInt(n.getAttribute('data-open'), 10)); }));
    el('delCalBody').querySelectorAll('[data-newdate]').forEach((n) => n.addEventListener('click', () => openCreate(n.getAttribute('data-newdate'))));
  }

  function renderList() {
    el('delCalHost').classList.add('hidden'); el('delListHost').classList.remove('hidden'); el('delCalNav').style.display = 'none';
    const rows = filtered().slice().sort((a, b) => (a.delivery_date || '').localeCompare(b.delivery_date || ''));
    const host = el('delListHost');
    if (!rows.length) { host.innerHTML = `<div class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-truck-ramp-box text-4xl mb-3 block text-zinc-600"></i>No deliveries. Add one or click a day on the calendar.</div>`; return; }
    host.innerHTML = rows.map((d) => `
      <div class="del-list-row" data-open="${d.id}">
        <div class="text-center shrink-0 w-14"><div class="text-[10px] text-zinc-500">${new Date(d.delivery_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short' })}</div><div class="text-lg font-semibold">${new Date(d.delivery_date + 'T00:00:00').getDate()}</div></div>
        <div class="min-w-0 flex-1">
          <div class="text-sm truncate">${esc(d.supplier || 'Delivery')} — ${esc(d.description || '')}</div>
          <div class="text-xs text-zinc-500 flex gap-3 flex-wrap mt-0.5">
            <span class="font-mono">${esc(d.delivery_number || '')}</span>
            ${d.time_window ? `<span><i class="fa-solid fa-clock"></i> ${esc(d.time_window)}</span>` : ''}
            ${d.po_number ? `<span><i class="fa-solid fa-file-invoice"></i> ${esc(d.po_number)}</span>` : ''}
            ${d.location ? `<span><i class="fa-solid fa-location-dot"></i> ${esc(d.location)}</span>` : ''}
            ${d.synced_to_schedule ? '<span class="text-violet-400"><i class="fa-solid fa-link"></i> On schedule</span>' : ''}
          </div>
        </div>
        <span class="del-chip ${STATUS_COLORS[d.status] || 'bg-zinc-700 text-zinc-300'}">${esc(d.status)}</span>
      </div>`).join('');
    host.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openEdit(parseInt(n.getAttribute('data-open'), 10))));
  }

  function fillSelect(sel, opts, val) { sel.innerHTML = opts.map((o) => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join(''); }

  function resetModal() {
    state.editId = null;
    el('delModalTitle').textContent = 'New Delivery';
    ['dDesc', 'dSupplier', 'dCarrier', 'dTime', 'dQuantity', 'dPo', 'dLocation', 'dResponsible', 'dReceived', 'dNotes'].forEach((id) => { el(id).value = ''; });
    el('dDate').value = iso(new Date()); el('dDuration').value = 1;
    fillSelect(el('dStatus'), state.statuses.length ? state.statuses : ['Scheduled'], 'Scheduled');
    el('dPush').checked = false; el('dSyncedBadge').classList.add('hidden');
    el('dDelete').classList.add('hidden');
  }
  function openCreate(dateStr) { resetModal(); if (dateStr) el('dDate').value = dateStr; el('delModal').showModal(); }
  function openEdit(id) {
    const d = state.deliveries.find((x) => x.id === id); if (!d) return;
    resetModal(); state.editId = id;
    el('delModalTitle').textContent = d.delivery_number || 'Delivery';
    el('dDesc').value = d.description || ''; el('dSupplier').value = d.supplier || ''; el('dCarrier').value = d.carrier || '';
    el('dDate').value = d.delivery_date || iso(new Date()); el('dTime').value = d.time_window || ''; el('dDuration').value = d.duration_days || 1;
    el('dQuantity').value = d.quantity || ''; el('dPo').value = d.po_number || ''; el('dLocation').value = d.location || '';
    el('dResponsible').value = d.responsible || ''; el('dReceived').value = d.received_by || ''; el('dNotes').value = d.notes || '';
    fillSelect(el('dStatus'), state.statuses, d.status);
    el('dPush').checked = d.synced_to_schedule; el('dSyncedBadge').classList.toggle('hidden', !d.synced_to_schedule);
    el('dDelete').classList.remove('hidden');
    el('delModal').showModal();
  }

  async function save() {
    const pid = projectId(); const desc = el('dDesc').value.trim(); const date = el('dDate').value;
    if (!pid || !desc || !date) { alert('Description and delivery date are required.'); return; }
    const payload = {
      project_id: pid, description: desc, supplier: el('dSupplier').value.trim(), carrier: el('dCarrier').value.trim(),
      delivery_date: date, time_window: el('dTime').value.trim(), duration_days: el('dDuration').value,
      status: el('dStatus').value, quantity: el('dQuantity').value.trim(), po_number: el('dPo').value.trim(),
      location: el('dLocation').value.trim(), responsible: el('dResponsible').value.trim(), received_by: el('dReceived').value.trim(),
      notes: el('dNotes').value.trim(), push_to_schedule: el('dPush').checked,
    };
    const btn = el('dSave'); btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const url = state.editId ? `/api/deliveries/${state.editId}` : '/api/deliveries';
      await api(url, { method: state.editId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      // If newly checked push on an existing delivery, ensure it's pushed.
      el('delModal').close(); await load();
      if (global.showToast) global.showToast('Delivery saved');
    } catch (e) { alert(e.message); } finally { btn.disabled = false; btn.textContent = 'Save'; }
  }
  async function del() { if (!state.editId || !confirm('Delete this delivery? (also removes its schedule line item)')) return; try { await api(`/api/deliveries/${state.editId}`, { method: 'DELETE' }); el('delModal').close(); await load(); } catch (e) { alert(e.message); } }

  async function pushAll() {
    const pid = projectId(); if (!pid) { alert('Select a project first.'); return; }
    if (!confirm('Push all deliveries to the Schedule as line items?')) return;
    try {
      const j = await api(`/api/deliveries/push-to-schedule?project_id=${pid}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      await load();
      const go = confirm(`Pushed ${j.pushed} delivery(s) to the Schedule. Open the Schedule now?`);
      if (go) window.location.href = (ctx.scheduleUrl || '/schedule') + `?project_id=${pid}`;
    } catch (e) { alert(e.message); }
  }

  function setView(v) {
    state.view = v;
    el('delViewCal').className = 'px-3 py-2 text-sm ' + (v === 'cal' ? 'bg-zinc-700' : 'bg-zinc-800');
    el('delViewList').className = 'px-3 py-2 text-sm ' + (v === 'list' ? 'bg-zinc-700' : 'bg-zinc-800');
    render();
  }

  function bind() {
    el('delBtnNew').addEventListener('click', () => openCreate());
    el('delBtnRefresh')?.addEventListener('click', load);
    el('delViewCal').addEventListener('click', () => setView('cal'));
    el('delViewList').addEventListener('click', () => setView('list'));
    el('delPushAll').addEventListener('click', pushAll);
    el('delPrev').addEventListener('click', () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1); render(); });
    el('delNext').addEventListener('click', () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1); render(); });
    el('delToday').addEventListener('click', () => { state.month = new Date(); render(); });
    el('delModalClose').addEventListener('click', () => el('delModal').close());
    el('dCancel').addEventListener('click', () => el('delModal').close());
    el('dSave').addEventListener('click', save);
    el('dDelete').addEventListener('click', del);
    ['delSearch', 'delStatusFilter'].forEach((id) => { el(id).addEventListener('input', render); el(id).addEventListener('change', render); });
    global.addEventListener('casepm:project-changed', load);
    global.onCasePmProjectChanged = (pid) => { ctx.projectId = pid; load(); };
  }
  function init() { bind(); load(); }
  global.CasePMDeliveries = { refresh: load };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
