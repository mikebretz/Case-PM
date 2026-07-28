/**
 * Outlook-style calendar for the Email workspace.
 */
(function (global) {
  'use strict';

  let EVENT_TYPES = [
    { id: 'owner_meeting', label: 'Owner meeting', defaultTitle: 'Owner meeting' },
    { id: 'site_visit', label: 'Site visit', defaultTitle: 'Site visit' },
    { id: 'precon', label: 'Pre-construction walkthrough', defaultTitle: 'Pre-construction walkthrough' },
    { id: 'bid', label: 'Bid meeting / walkthrough', defaultTitle: 'Bid meeting' },
    { id: 'safety', label: 'Safety meeting', defaultTitle: 'Safety meeting' },
    { id: 'toolbox_talk', label: 'Toolbox / tailgate talk', defaultTitle: 'Toolbox talk' },
    { id: 'oac', label: 'OAC meeting', defaultTitle: 'OAC meeting' },
    { id: 'subcontractor', label: 'Subcontractor coordination', defaultTitle: 'Subcontractor coordination' },
    { id: 'design', label: 'Design coordination / BIM', defaultTitle: 'Design coordination' },
    { id: 'schedule', label: 'Schedule / CPM review', defaultTitle: 'Schedule review' },
    { id: 'submittal', label: 'Submittal review', defaultTitle: 'Submittal review' },
    { id: 'closeout', label: 'Closeout / punch', defaultTitle: 'Closeout meeting' },
    { id: 'internal', label: 'Internal team', defaultTitle: 'Internal team meeting' },
    { id: 'stakeholder', label: 'Client / stakeholder', defaultTitle: 'Stakeholder meeting' },
    { id: 'coordination', label: 'Coordination', defaultTitle: 'Coordination meeting' },
    { id: 'meeting', label: 'General meeting', defaultTitle: 'Meeting' },
    { id: 'other', label: 'Other', defaultTitle: 'Meeting' },
  ];

  let ctx = { userEmail: '', userName: '', projectId: null, projectName: '' };
  let events = [];
  let viewDate = new Date();
  let selectedDay = new Date();
  let editingEvent = null;
  let rootEl = null;
  let outlookConnected = false;
  let outlookSyncStatus = '';
  let coordinatedEventTypes = new Set([
    'owner_meeting', 'site_visit', 'precon', 'bid', 'oac', 'oac_weekly',
    'superintendent', 'subcontractor', 'safety', 'toolbox_talk', 'design',
    'schedule', 'submittal', 'closeout', 'internal', 'stakeholder',
  ]);

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

  async function loadEvents(syncOutlook) {
    const url = syncOutlook ? '/api/email/calendar?sync_outlook=1' : '/api/email/calendar';
    const res = await fetch(url);
    if (!res.ok) throw new Error('Could not load calendar');
    const data = await res.json();
    events = Array.isArray(data.events) ? data.events : [];
    outlookConnected = !!(data.outlook_connected || data.outlook_sync?.connected);
    if (data.outlook_sync?.error) {
      outlookSyncStatus = `Outlook sync issue: ${data.outlook_sync.error}. Reconnect Outlook in Email Settings to grant calendar access.`;
    } else if (data.outlook_sync?.synced_from_outlook != null) {
      outlookSyncStatus = `Synced ${data.outlook_sync.synced_from_outlook} events from Outlook.`;
    } else {
      outlookSyncStatus = outlookConnected ? 'Outlook connected — click Sync to refresh.' : 'Connect Outlook in Email Settings to sync your calendar.';
    }
  }

  async function syncOutlook() {
    const res = await fetch('/api/email/calendar/sync-outlook', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      outlookSyncStatus = data.error || 'Outlook sync failed';
      render();
      return;
    }
    events = data.events || events;
    outlookSyncStatus = `Synced ${data.synced_from_outlook || 0} events from Outlook.`;
    render();
    if (global.CasePMEmail?.toast) global.CasePMEmail.toast(outlookSyncStatus, 'success');
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
    const map = {
      owner_meeting: 'owner',
      site_visit: 'site',
      superintendent: 'site',
      safety: 'safety',
      toolbox_talk: 'safety',
      precon: 'precon',
      bid: 'bid',
      oac: 'oac',
      oac_weekly: 'oac',
    };
    return map[type] || '';
  }

  async function loadCatalog() {
    try {
      const res = await fetch('/api/email/calendar/catalog');
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.event_types) && data.event_types.length) {
        EVENT_TYPES = data.event_types;
      }
      if (Array.isArray(data.coordinated_event_types)) {
        coordinatedEventTypes = new Set(data.coordinated_event_types);
      }
      if (global.CasePMEmail?.setCalendarSidebar && Array.isArray(data.sidebar)) {
        global.CasePMEmail.setCalendarSidebar(data.sidebar);
      }
    } catch (e) {
      /* keep defaults */
    }
  }

  function eventTypeLabel(id) {
    return EVENT_TYPES.find(t => t.id === id)?.label || id || 'Meeting';
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

  function renderDaySchedule() {
    const dayEvents = eventsForDay(selectedDay);
    if (!dayEvents.length) {
      return `<div class="text-sm text-zinc-500 p-3">No meetings on this day. Double-click a day on the calendar or pick a meeting type in the sidebar to schedule one.</div>`;
    }
    return dayEvents.map(ev => `
      <div class="email-calendar-agenda-item" data-event-id="${esc(ev.id)}">
        <div class="text-sm font-medium text-zinc-100">${esc(ev.title)}</div>
        <div class="text-[10px] uppercase tracking-wide text-zinc-500 mt-0.5">${esc(eventTypeLabel(ev.eventType))}${ev.source === 'meeting_minutes' ? ' · from Meeting Minutes' : ''}</div>
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
          <button type="button" class="email-calendar-nav-btn" data-cal-action="sync-outlook" title="Sync with Outlook calendar">
            <i class="fa-brands fa-microsoft"></i> Sync Outlook
          </button>
          <span class="email-calendar-outlook-status">${esc(outlookSyncStatus)}</span>
          <a href="/company-map" class="email-calendar-nav-btn" style="text-decoration:none;"><i class="fa-solid fa-map-location-dot"></i> Job map</a>
        </div>
        <div class="email-calendar-body">
          <div class="email-calendar-month">${renderMonth()}</div>
          <aside class="email-calendar-agenda">
            <div class="email-calendar-agenda-head">${esc(fmtDayTitle(selectedDay))}</div>
            <div class="text-[10px] text-zinc-500 px-3 pb-2">Day schedule — click a meeting to open it</div>
            <div class="email-calendar-agenda-list">${renderDaySchedule()}</div>
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
    rootEl.querySelector('[data-cal-action="sync-outlook"]')?.addEventListener('click', () => syncOutlook());
    rootEl.querySelectorAll('[data-day]').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('[data-event-id]')) return;
        selectedDay = startOfDay(new Date(el.getAttribute('data-day')));
        render();
      });
      el.addEventListener('dblclick', (e) => {
        if (e.target.closest('[data-event-id]')) return;
        const day = startOfDay(new Date(el.getAttribute('data-day')));
        selectedDay = day;
        openEventModal(null, day);
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

  function openEventModal(existing, forDay, prefill) {
    const baseDay = forDay || selectedDay;
    const pre = prefill || {};
    const isReadOnly = !!(existing && (existing.readOnly || existing.source === 'meeting_minutes'));
    editingEvent = existing ? { ...existing } : {
      id: uid(),
      title: pre.title || '',
      eventType: pre.eventType || (ctx.projectId ? 'owner_meeting' : 'meeting'),
      ...defaultEventTimes(baseDay),
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
    const readOnlyNote = isReadOnly
      ? `<div class="text-xs text-amber-300/90 bg-amber-950/40 border border-amber-800/50 rounded-md p-2 mb-3">This meeting was created on another page (Meeting Minutes, Safety, etc.) and appears here automatically. <a href="/meeting-minutes" class="text-emerald-400 hover:underline">Open Meeting Minutes</a> to edit the record.</div>`
      : '';
    backdrop.innerHTML = `
      <div class="email-calendar-modal" role="dialog" aria-modal="true">
        <div class="email-calendar-modal-head">
          <h3 class="text-white font-semibold">${isReadOnly ? 'Meeting details' : (existing ? 'Edit meeting' : 'New meeting invite')}</h3>
          <button type="button" class="email-calendar-nav-btn" data-close-modal><i class="fa-solid fa-times"></i></button>
        </div>
        <div class="email-calendar-modal-body">
          ${readOnlyNote}
          <div class="email-calendar-field">
            <label>Title</label>
            <input type="text" id="calTitle" value="${esc(editingEvent.title || '')}" placeholder="Owner meeting, toolbox talk, bid walkthrough…" ${isReadOnly ? 'readonly' : ''}>
          </div>
          <div class="email-calendar-row">
            <div class="email-calendar-field">
              <label>Start</label>
              <input type="datetime-local" id="calStart" value="${toLocalInputValue(editingEvent.start)}" ${isReadOnly ? 'readonly' : ''}>
            </div>
            <div class="email-calendar-field">
              <label>End</label>
              <input type="datetime-local" id="calEnd" value="${toLocalInputValue(editingEvent.end)}" ${isReadOnly ? 'readonly' : ''}>
            </div>
          </div>
          <div class="email-calendar-row">
            <div class="email-calendar-field">
              <label>Meeting type</label>
              <select id="calType" ${isReadOnly ? 'disabled' : ''}>
                ${EVENT_TYPES.map(t => `<option value="${t.id}" ${editingEvent.eventType === t.id ? 'selected' : ''}>${t.label}</option>`).join('')}
              </select>
            </div>
            <div class="email-calendar-field">
              <label>Reminder (minutes)</label>
              <input type="number" id="calReminder" min="0" step="5" value="${editingEvent.reminderMinutes || 15}" ${isReadOnly ? 'readonly' : ''}>
            </div>
          </div>
          <div class="email-calendar-field">
            <label>Location (job site, business, or address)</label>
            <input type="text" id="calLocation" value="${esc(editingEvent.location || '')}" placeholder="Start typing a job site, business name, or US address…" ${isReadOnly ? 'readonly' : ''}>
          </div>
          <div class="email-calendar-field">
            <label>Attendees (comma-separated emails)</label>
            <input type="text" id="calAttendees" value="${esc((editingEvent.attendees || []).join(', '))}" placeholder="owner@client.com, pm@company.com" ${isReadOnly ? 'readonly' : ''}>
          </div>
          <div class="email-calendar-field">
            <label>Notes for email invite</label>
            <textarea id="calBody" placeholder="Details included in the invite email — dial-in, documents, talking points…" ${isReadOnly ? 'readonly' : ''}>${esc((editingEvent.body || '').replace(/<[^>]+>/g, ''))}</textarea>
          </div>
          ${isReadOnly ? '' : `
          <label class="flex items-center gap-2 text-sm text-zinc-300 mb-1" id="calLinkMinutesWrap">
            <input type="checkbox" id="calLinkMinutes" class="accent-emerald-600" checked>
            Also create a Meeting Minutes record (links calendar ↔ minutes like Procore)
          </label>
          <label class="flex items-center gap-2 text-sm text-zinc-300 mb-1">
            <input type="checkbox" id="calSyncOutlook" class="accent-emerald-600" ${outlookConnected ? 'checked' : ''} ${outlookConnected ? '' : 'disabled'}>
            Sync to Outlook calendar
          </label>
          <label class="flex items-center gap-2 text-sm text-zinc-300 mb-2">
            <input type="checkbox" id="calSendInvites" class="accent-emerald-600" checked>
            Send email invites to attendees (when SMTP is configured)
          </label>`}
          <div class="email-calendar-modal-actions">
            ${existing && !isReadOnly ? '<button type="button" class="email-calendar-nav-btn" data-delete-event style="margin-right:auto;color:#fca5a5;">Delete</button>' : ''}
            <button type="button" class="email-calendar-nav-btn" data-close-modal>${isReadOnly ? 'Close' : 'Cancel'}</button>
            ${isReadOnly ? '' : '<button type="button" class="email-calendar-nav-btn" data-save-event style="background:#059669;border-color:#059669;color:#fff;">Save</button>'}
          </div>
        </div>
      </div>`;
    document.body.appendChild(backdrop);

    const syncLinkMinutesVisibility = () => {
      const type = backdrop.querySelector('#calType')?.value || editingEvent.eventType;
      const wrap = backdrop.querySelector('#calLinkMinutesWrap');
      const box = backdrop.querySelector('#calLinkMinutes');
      const coordinated = coordinatedEventTypes.has(type);
      if (wrap) wrap.classList.toggle('hidden', !coordinated || !!existing);
      if (box && coordinated && !existing) box.checked = true;
    };
    backdrop.querySelector('#calType')?.addEventListener('change', syncLinkMinutesVisibility);
    syncLinkMinutesVisibility();

    const locInput = backdrop.querySelector('#calLocation');
    if (!isReadOnly && global.CasePMAddressAutocomplete && locInput) {
      global.CasePMAddressAutocomplete.attach(locInput, {
        getNearLat: () => editingEvent.locationMeta?.latitude ?? ctx.projectLat,
        getNearLng: () => editingEvent.locationMeta?.longitude ?? ctx.projectLng,
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
      if (isReadOnly) return;
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
      let savedData = null;
      if (isNew) {
        const res = await fetch('/api/email/calendar/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            event: payload,
            send_invites: backdrop.querySelector('#calSendInvites').checked,
            sync_outlook: backdrop.querySelector('#calSyncOutlook')?.checked !== false,
            link_meeting_minutes: backdrop.querySelector('#calLinkMinutes')?.checked === true,
          }),
        });
        savedData = await res.json();
        if (!res.ok) {
          alert(savedData.error || 'Could not save meeting');
          return;
        }
        events.push(savedData.event);
      } else {
        const res = await fetch(`/api/email/calendar/events/${encodeURIComponent(payload.id)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event: payload }),
        });
        savedData = await res.json();
        if (!res.ok) {
          alert(savedData.error || 'Could not update meeting');
          return;
        }
        events = events.map(e => String(e.id) === String(payload.id) ? savedData.event : e);
      }
      selectedDay = startOfDay(new Date(payload.start));
      viewDate = new Date(selectedDay);
      close();
      render();
      if (global.CasePMEmail?.toast) {
        const mmNote = savedData?.meeting_minute_id ? ' Meeting Minutes record created and linked.' : '';
        global.CasePMEmail.toast((isNew ? 'Meeting created.' : 'Meeting updated.') + mmNote, 'success');
      }
    });
  }

  async function init(options) {
    ctx = { ...ctx, ...(options || {}) };
    rootEl = options?.container || document.getElementById('emailCalendarRoot');
    if (!rootEl) return;
    await loadCatalog();
    await loadEvents(true);
    if (options?.prefillProjectId) {
      ctx.projectId = options.prefillProjectId;
      ctx.projectName = options.prefillProjectName || '';
    }
    render();
    if (options?.openNew) {
      setTimeout(() => openEventModal(null, null, {
        eventType: options.prefillEventType,
        title: options.prefillTitle,
      }), 100);
    }
  }

  global.CasePMEmailCalendar = { init, render, loadEvents, syncOutlook, openEventModal, loadCatalog };
})(window);
