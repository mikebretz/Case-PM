/**
 * Outlook-style calendar for the Email workspace.
 */
(function (global) {
  'use strict';

  const EVENT_TYPES = [
    { id: 'meeting', label: 'Meeting' },
    { id: 'owner_meeting', label: 'Owner meeting' },
    { id: 'site_visit', label: 'Site visit' },
    { id: 'coordination', label: 'Coordination' },
    { id: 'other', label: 'Other' },
  ];

  let ctx = { userEmail: '', userName: '', projectId: null, projectName: '' };
  let events = [];
  let viewDate = new Date();
  let viewMode = 'month';
  let selectedDay = new Date();
  let editingEvent = null;
  let rootEl = null;

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function uid() {
    return 'evt_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function startOfDay(d) {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
  }

  function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function fmtDayTitle(d) {
    return d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  }

  function fmtMonthTitle(d) {
    return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  }

  function toLocalInputValue(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function eventStartDate(ev) {
    return ev.start ? new Date(ev.start) : null;
  }

  function eventsForDay(day) {
    return events.filter(ev => {
      const start = eventStartDate(ev);
      return start && sameDay(start, day);
    }).sort((a, b) => (a.start || '').localeCompare(b.start || ''));
  }

  async function loadEvents() {
    const res = await fetch('/api/email/calendar');
    if (!res.ok) throw new Error('Could not load calendar');
    const data = await res.json();
    events = Array.isArray(data.events) ? data.events : [];
  }

  async function saveEvents() {
    await fetch('/api/email/calendar', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ events }),
    });
  }

  function monthMatrix(baseDate) {
    const first = new Date(baseDate.getFullYear(), baseDate.getMonth(), 1);
    const start = new Date(first);
    start.setDate(first.getDate() - ((first.getDay() + 6) % 7));
    const weeks = [];
    let cursor = new Date(start);
    for (let w = 0; w < 6; w++) {
      const week = [];
      for (let d = 0; d < 7; d++) {
        week.push(new Date(cursor));
        cursor.setDate(cursor.getDate() + 1);
      }
      weeks.push(week);
    }
    return weeks;
  }

  function chipClass(type) {
    if (type === 'owner_meeting') return 'owner';
    if (type === 'site_visit') return 'site';
    return '';
  }

  function renderMonth() {
    const weeks = monthMatrix(viewDate);
    const today = startOfDay(new Date());
    const dows = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    let html = dows.map(d => `<div class="email-calendar-dow">${d}</div>`).join('');
    weeks.forEach(week => {
      week.forEach(day => {
        const outside = day.getMonth() !== viewDate.getMonth();
        const dayEvents = eventsForDay(day);
        html += `
          <div class="email-calendar-day ${outside ? 'outside' : ''} ${sameDay(day, today) ? 'today' : ''} ${sameDay(day, selectedDay) ? 'ring-1 ring-emerald-600' : ''}"
               data-day="${day.toISOString()}">
            <div class="email-calendar-day-num">${day.getDate()}</div>
            ${dayEvents.slice(0, 3).map(ev => `
              <button type="button" class="email-calendar-event-chip ${chipClass(ev.eventType)}"
                      data-event-id="${esc(ev.id)}" title="${esc(ev.title)}">
                ${esc(ev.title)}
              </button>`).join('')}
            ${dayEvents.length > 3 ? `<div class="text-[10px] text-zinc-500">+${dayEvents.length - 3} more</div>` : ''}
          </div>`;
      });
    });
    return html;
  }

  function renderAgenda() {
    const dayEvents = eventsForDay(selectedDay);
    if (!dayEvents.length) {
      return `<div class="text-sm text-zinc-500 p-3">No meetings scheduled. Click <strong>New meeting</strong> to create an invite.</div>`;
    }
    return dayEvents.map(ev => `
      <div class="email-calendar-agenda-item" data-event-id="${esc(ev.id)}">
        <div class="text-sm font-medium text-zinc-100">${esc(ev.title)}</div>
        <div class="text-xs text-zinc-400 mt-1">${esc(new Date(ev.start).toLocaleString())}${ev.end ? ` — ${esc(new Date(ev.end).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))}` : ''}</div>
        ${ev.location ? `<div class="text-xs text-zinc-500 mt-1"><i class="fa-solid fa-location-dot"></i> ${esc(ev.location)}</div>` : ''}
        ${ev.attendees?.length ? `<div class="text-[10px] text-zinc-500 mt-1">${ev.attendees.length} attendee${ev.attendees.length === 1 ? '' : 's'}</div>` : ''}
      </div>
    `).join('');
  }

  function render() {
    if (!rootEl) return;
    rootEl.innerHTML = `
      <div class="email-calendar-root">
        <div class="email-calendar-toolbar">
          <button type="button" class="email-calendar-nav-btn" data-cal-action="prev"><i class="fa-solid fa-chevron-left"></i></button>
          <button type="button" class="email-calendar-nav-btn" data-cal-action="today">Today</button>
          <button type="button" class="email-calendar-nav-btn" data-cal-action="next"><i class="fa-solid fa-chevron-right"></i></button>
          <div class="email-calendar-title">${esc(fmtMonthTitle(viewDate))}</div>
          <button type="button" class="email-calendar-nav-btn" data-cal-action="new" style="background:#059669;border-color:#059669;color:#fff;font-weight:600;">
            <i class="fa-solid fa-calendar-plus"></i> New meeting
          </button>
          <a href="/company-map" class="email-calendar-nav-btn" style="text-decoration:none;"><i class="fa-solid fa-map-location-dot"></i> Job map</a>
          <div class="email-calendar-view-tabs">
            <button type="button" class="email-calendar-view-tab ${viewMode === 'month' ? 'active' : ''}" data-cal-view="month">Month</button>
            <button type="button" class="email-calendar-view-tab ${viewMode === 'agenda' ? 'active' : ''}" data-cal-view="agenda">Agenda</button>
          </div>
        </div>
        <div class="email-calendar-body">
          <div class="email-calendar-month">${renderMonth()}</div>
          <aside class="email-calendar-agenda">
            <div class="email-calendar-agenda-head">${esc(fmtDayTitle(selectedDay))}</div>
            <div class="email-calendar-agenda-list">${renderAgenda()}</div>
          </aside>
        </div>
      </div>`;
    bindRootEvents();
  }

  function bindRootEvents() {
    rootEl.querySelector('[data-cal-action="prev"]')?.addEventListener('click', () => {
      viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1);
      render();
    });
    rootEl.querySelector('[data-cal-action="next"]')?.addEventListener('click', () => {
      viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1);
      render();
    });
    rootEl.querySelector('[data-cal-action="today"]')?.addEventListener('click', () => {
      viewDate = new Date();
      selectedDay = startOfDay(new Date());
      render();
    });
    rootEl.querySelector('[data-cal-action="new"]')?.addEventListener('click', () => openEventModal());
    rootEl.querySelectorAll('[data-day]').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('[data-event-id]')) return;
        selectedDay = startOfDay(new Date(el.getAttribute('data-day')));
        render();
      });
      el.querySelectorAll('[data-event-id]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const ev = events.find(x => String(x.id) === btn.getAttribute('data-event-id'));
          if (ev) openEventModal(ev);
        });
      });
    });
    rootEl.querySelectorAll('.email-calendar-agenda-item').forEach(el => {
      el.addEventListener('click', () => {
        const ev = events.find(x => String(x.id) === el.getAttribute('data-event-id'));
        if (ev) openEventModal(ev);
      });
    });
  }

  function defaultEventTimes(baseDay) {
    const start = new Date(baseDay);
    start.setHours(9, 0, 0, 0);
    const end = new Date(start);
    end.setHours(10, 0, 0, 0);
    return { start: start.toISOString(), end: end.toISOString() };
  }

  function openEventModal(existing) {
    editingEvent = existing ? { ...existing } : {
      id: uid(),
      title: '',
      eventType: ctx.projectId ? 'owner_meeting' : 'meeting',
      ...defaultEventTimes(selectedDay),
      location: '',
      locationMeta: {},
      body: '',
      attendees: [],
      projectId: ctx.projectId,
      projectName: ctx.projectName,
      reminderMinutes: 15,
      allDay: false,
      organizer: ctx.userEmail,
      organizerName: ctx.userName,
    };

    const backdrop = document.createElement('div');
    backdrop.className = 'email-calendar-modal-backdrop';
    backdrop.innerHTML = `
      <div class="email-calendar-modal" role="dialog" aria-modal="true">
        <div class="email-calendar-modal-head">
          <h3 class="text-white font-semibold">${existing ? 'Edit meeting' : 'New meeting invite'}</h3>
          <button type="button" class="email-calendar-nav-btn" data-close-modal><i class="fa-solid fa-times"></i></button>
        </div>
        <div class="email-calendar-modal-body">
          <div class="email-calendar-field">
            <label>Title</label>
            <input type="text" id="calTitle" value="${esc(editingEvent.title || '')}" placeholder="Owner meeting, coordination call, etc.">
          </div>
          <div class="email-calendar-row">
            <div class="email-calendar-field">
              <label>Start</label>
              <input type="datetime-local" id="calStart" value="${toLocalInputValue(editingEvent.start)}">
            </div>
            <div class="email-calendar-field">
              <label>End</label>
              <input type="datetime-local" id="calEnd" value="${toLocalInputValue(editingEvent.end)}">
            </div>
          </div>
          <div class="email-calendar-row">
            <div class="email-calendar-field">
              <label>Meeting type</label>
              <select id="calType">
                ${EVENT_TYPES.map(t => `<option value="${t.id}" ${editingEvent.eventType === t.id ? 'selected' : ''}>${t.label}</option>`).join('')}
              </select>
            </div>
            <div class="email-calendar-field">
              <label>Reminder (minutes)</label>
              <input type="number" id="calReminder" min="0" step="5" value="${editingEvent.reminderMinutes || 15}">
            </div>
          </div>
          <div class="email-calendar-field">
            <label>Location (job site or address)</label>
            <input type="text" id="calLocation" value="${esc(editingEvent.location || '')}" placeholder="Start typing a job site or address…">
          </div>
          <div class="email-calendar-field">
            <label>Attendees (comma-separated emails)</label>
            <input type="text" id="calAttendees" value="${esc((editingEvent.attendees || []).join(', '))}" placeholder="owner@client.com, pm@company.com">
          </div>
          <div class="email-calendar-field">
            <label>Agenda / invite message</label>
            <textarea id="calBody" placeholder="Meeting agenda, dial-in, documents to review…">${esc((editingEvent.body || '').replace(/<[^>]+>/g, ''))}</textarea>
          </div>
          <label class="flex items-center gap-2 text-sm text-zinc-300 mb-2">
            <input type="checkbox" id="calSendInvites" class="accent-emerald-600" checked>
            Send email invites to attendees (when SMTP is configured)
          </label>
          <div class="email-calendar-modal-actions">
            ${existing ? '<button type="button" class="email-calendar-nav-btn" data-delete-event style="margin-right:auto;color:#fca5a5;">Delete</button>' : ''}
            <button type="button" class="email-calendar-nav-btn" data-close-modal>Cancel</button>
            <button type="button" class="email-calendar-nav-btn" data-save-event style="background:#059669;border-color:#059669;color:#fff;">Save</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(backdrop);

    const locInput = backdrop.querySelector('#calLocation');
    if (global.CasePMAddressAutocomplete && locInput) {
      global.CasePMAddressAutocomplete.attach(locInput, {
        onSelect(item) {
          editingEvent.locationMeta = {
            projectId: item.id,
            latitude: item.latitude,
            longitude: item.longitude,
            kind: item.kind || item.source,
          };
          if (item.kind === 'project' || item.source === 'project') {
            editingEvent.projectId = item.id;
            editingEvent.projectName = item.name;
          }
        },
      });
    }

    const close = () => backdrop.remove();
    backdrop.querySelectorAll('[data-close-modal]').forEach(btn => btn.addEventListener('click', close));
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) close(); });

    backdrop.querySelector('[data-delete-event]')?.addEventListener('click', async () => {
      events = events.filter(e => String(e.id) !== String(editingEvent.id));
      await fetch(`/api/email/calendar/events/${encodeURIComponent(editingEvent.id)}`, { method: 'DELETE' });
      close();
      render();
    });

    backdrop.querySelector('[data-save-event]')?.addEventListener('click', async () => {
      const payload = {
        ...editingEvent,
        title: backdrop.querySelector('#calTitle').value.trim(),
        start: new Date(backdrop.querySelector('#calStart').value).toISOString(),
        end: new Date(backdrop.querySelector('#calEnd').value).toISOString(),
        eventType: backdrop.querySelector('#calType').value,
        reminderMinutes: parseInt(backdrop.querySelector('#calReminder').value, 10) || 15,
        location: backdrop.querySelector('#calLocation').value.trim(),
        attendees: backdrop.querySelector('#calAttendees').value.split(',').map(s => s.trim()).filter(Boolean),
        body: `<p>${esc(backdrop.querySelector('#calBody').value).replace(/\n/g, '<br>')}</p>`,
      };
      const isNew = !existing;
      if (isNew) {
        const res = await fetch('/api/email/calendar/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event: payload, send_invites: backdrop.querySelector('#calSendInvites').checked }),
        });
        const data = await res.json();
        if (!res.ok) {
          alert(data.error || 'Could not save meeting');
          return;
        }
        events.push(data.event);
      } else {
        const res = await fetch(`/api/email/calendar/events/${encodeURIComponent(payload.id)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event: payload }),
        });
        const data = await res.json();
        if (!res.ok) {
          alert(data.error || 'Could not update meeting');
          return;
        }
        events = events.map(e => String(e.id) === String(payload.id) ? data.event : e);
      }
      selectedDay = startOfDay(new Date(payload.start));
      viewDate = new Date(selectedDay);
      close();
      render();
      if (global.CasePMEmail?.toast) {
        global.CasePMEmail.toast(isNew ? 'Meeting created.' : 'Meeting updated.', 'success');
      }
    });
  }

  async function init(options) {
    ctx = { ...ctx, ...(options || {}) };
    rootEl = options?.container || document.getElementById('emailCalendarRoot');
    if (!rootEl) return;
    await loadEvents();
    if (options?.prefillProjectId) {
      ctx.projectId = options.prefillProjectId;
      ctx.projectName = options.prefillProjectName || '';
    }
    if (options?.openNew) {
      setTimeout(() => openEventModal(), 100);
    }
    render();
  }

  global.CasePMEmailCalendar = { init, render, loadEvents, openEventModal };
})(window);
