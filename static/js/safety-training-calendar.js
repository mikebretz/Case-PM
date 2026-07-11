/**
 * Safety — certification expiration calendar and scheduled training events.
 */
(function (global) {
  'use strict';

  const state = { month: new Date(), events: [], scheduled: [], links: {}, users: [], view: 'list' };

  function el(id) { return document.getElementById(id); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function projectId() {
    const ctx = global.CASEPM_SAFETY_CTX || {};
    return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })();
  }
  async function api(url, opts) { const r = await fetch(url, opts); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Request failed'); return j; }

  function setView(view) {
    state.view = view;
    el('cViewList')?.classList.toggle('bg-emerald-700', view === 'list');
    el('cViewList')?.classList.toggle('bg-zinc-800', view !== 'list');
    el('cViewCal')?.classList.toggle('bg-emerald-700', view === 'calendar');
    el('cViewCal')?.classList.toggle('bg-zinc-800', view !== 'calendar');
    el('cListWrap')?.classList.toggle('hidden', view !== 'list');
    el('cCalWrap')?.classList.toggle('hidden', view !== 'calendar');
    if (view === 'calendar') renderCalendar();
  }

  async function loadCalendar() {
    const pid = projectId();
    const y = state.month.getFullYear();
    const m = state.month.getMonth();
    const start = new Date(y, m, 1).toISOString().slice(0, 10);
    const end = new Date(y, m + 1, 0).toISOString().slice(0, 10);
    const j = await api(`/api/safety/training-calendar?project_id=${pid || ''}&start=${start}&end=${end}`);
    state.events = j.cert_events || [];
    state.scheduled = j.scheduled_events || [];
    state.links = j.training_links || {};
    state.users = j.users || [];
    populateUserSelect();
    if (state.view === 'calendar') renderCalendar();
  }

  function populateUserSelect() {
    const sel = el('tSchedUser');
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="">— Select user —</option>' + state.users.map((u) => `<option value="${u.id}">${esc(u.name)} (${esc(u.email)})</option>`).join('');
    if (cur) sel.value = cur;
  }

  function eventsOnDay(iso) {
    const cert = state.events.filter((e) => e.event_date === iso);
    const sched = state.scheduled.map((e) => ({
      id: `sched-${e.id}`,
      source: 'scheduled',
      event_date: e.event_date,
      title: `${e.cert_type || 'Training'} — ${e.person_name}`,
      status: (e.status || 'scheduled').toLowerCase(),
      person_name: e.person_name,
      cert_type: e.cert_type,
      training_url: e.training_url,
      raw: e,
    })).filter((e) => e.event_date === iso);
    return [...cert, ...sched];
  }

  function renderCalendar() {
    const grid = el('cCalGrid');
    const title = el('cCalTitle');
    if (!grid || !title) return;
    const y = state.month.getFullYear();
    const m = state.month.getMonth();
    title.textContent = state.month.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    const first = new Date(y, m, 1);
    const startPad = first.getDay();
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const today = new Date().toISOString().slice(0, 10);
    let html = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => `<div class="saf-cal-h">${d}</div>`).join('');
    for (let i = 0; i < startPad; i++) html += '<div class="saf-cal-day other"></div>';
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const evs = eventsOnDay(iso);
      const isToday = iso === today;
      html += `<div class="saf-cal-day${isToday ? ' today' : ''}"><div class="text-zinc-400 font-medium">${d}</div>`;
      evs.slice(0, 3).forEach((ev) => {
        const cls = ev.status === 'expired' ? 'expired' : ev.status === 'expiring' ? 'expiring' : ev.source === 'scheduled' ? 'scheduled' : 'valid';
        html += `<span class="saf-cal-ev ${cls}" data-ev="${esc(ev.id)}" title="${esc(ev.title)}">${esc(ev.title)}</span>`;
      });
      if (evs.length > 3) html += `<span class="text-[9px] text-zinc-500">+${evs.length - 3} more</span>`;
      html += '</div>';
    }
    grid.innerHTML = html;
    grid.querySelectorAll('[data-ev]').forEach((n) => n.addEventListener('click', () => {
      const id = n.getAttribute('data-ev');
      const ev = [...state.events, ...state.scheduled.map((s) => ({ ...s, id: `sched-${s.id}`, source: 'scheduled' }))].find((e) => String(e.id) === id);
      if (ev?.training_url) window.open(ev.training_url, '_blank');
      else if (ev?.raw?.training_url) window.open(ev.raw.training_url, '_blank');
    }));
  }

  async function ensureCertTypes() {
    const typeSel = el('tSchedType');
    if (!typeSel || typeSel.options.length > 1) return;
    let types = global.CasePMSafety?.getCertTypes?.() || [];
    if (!types.length) {
      const pid = projectId();
      const j = await api(`/api/safety/certifications${pid ? `?project_id=${pid}` : ''}`);
      types = j.cert_types || [];
    }
    typeSel.innerHTML = types.map((t) => `<option>${esc(t)}</option>`).join('');
  }

  async function openSchedule(prefill) {
    await ensureCertTypes().catch(() => {});
    const p = prefill || {};
    el('tSchedPerson').value = p.person_name || '';
    el('tSchedCompany').value = p.company || '';
    el('tSchedDate').value = p.event_date || new Date().toISOString().slice(0, 10);
    el('tSchedProvider').value = p.training_provider || '';
    el('tSchedUrl').value = p.training_url || '';
    el('tSchedNotes').value = p.notes || '';
    el('tSchedNotify').checked = true;
    const typeSel = el('tSchedType');
    if (p.cert_type && typeSel) typeSel.value = p.cert_type;
    applyDefaultLink();
    el('tSchedModal').showModal();
  }

  function applyDefaultLink() {
    const type = el('tSchedType')?.value;
    const link = state.links[type];
    if (link && el('tSchedUrl') && !el('tSchedUrl').value) {
      el('tSchedUrl').value = link.url || '';
      if (!el('tSchedProvider').value) el('tSchedProvider').value = link.label || '';
    }
  }

  async function saveSchedule() {
    const person = el('tSchedPerson').value.trim();
    const eventDate = el('tSchedDate').value;
    if (!person || !eventDate) { alert('Person and date are required.'); return; }
    const payload = {
      project_id: projectId(),
      person_name: person,
      company: el('tSchedCompany').value.trim(),
      cert_type: el('tSchedType').value,
      event_date: eventDate,
      training_provider: el('tSchedProvider').value.trim(),
      training_url: el('tSchedUrl').value.trim(),
      notes: el('tSchedNotes').value.trim(),
      notify_user_id: el('tSchedUser').value || null,
      send_internal_task: el('tSchedNotify').checked,
    };
    const btn = el('tSchedSave');
    btn.disabled = true;
    try {
      await api('/api/safety/training-events', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      el('tSchedModal').close();
      await loadCalendar();
      if (global.CasePMSafety?.refreshCerts) await global.CasePMSafety.refreshCerts();
      if (global.showToast) global.showToast('Training scheduled — internal task sent if enabled');
    } catch (e) { alert(e.message); } finally { btn.disabled = false; }
  }

  function bind() {
    el('cViewList')?.addEventListener('click', () => setView('list'));
    el('cViewCal')?.addEventListener('click', () => { setView('calendar'); loadCalendar().catch(() => {}); });
    el('cScheduleTraining')?.addEventListener('click', () => openSchedule());
    el('cCalPrev')?.addEventListener('click', () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1); loadCalendar().catch(() => {}); });
    el('cCalNext')?.addEventListener('click', () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1); loadCalendar().catch(() => {}); });
    el('tSchedClose')?.addEventListener('click', () => el('tSchedModal').close());
    el('tSchedCancel')?.addEventListener('click', () => el('tSchedModal').close());
    el('tSchedSave')?.addEventListener('click', saveSchedule);
    el('tSchedLinkPick')?.addEventListener('click', applyDefaultLink);
    el('tSchedType')?.addEventListener('change', applyDefaultLink);
    global.addEventListener('casepm:project-changed', () => loadCalendar().catch(() => {}));
  }

  function init() {
    if (!el('cCalGrid')) return;
    bind();
    setView('list');
  }

  global.CasePMSafetyCalendar = { loadCalendar, openSchedule, setView };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
