/**
 * Case PM — Meeting Minutes (voice dictation, speaker tagging, recording, action items).
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_MEETINGS_CTX || {};
  const STATUS_COLORS = {
    Draft: 'bg-zinc-600/30 text-zinc-300',
    Scheduled: 'bg-sky-500/20 text-sky-300',
    'In Progress': 'bg-violet-500/20 text-violet-300',
    Completed: 'bg-emerald-500/20 text-emerald-300',
    Distributed: 'bg-cyan-500/20 text-cyan-300',
    Cancelled: 'bg-zinc-700 text-zinc-500',
  };

  const state = {
    meetings: [], stats: {}, catalog: null, editId: null, tab: 'details',
    speakers: [], transcriptSegments: [], agenda: [], actionItems: [], attendees: [],
    listening: false, recording: false, recognition: null, mediaRecorder: null,
    audioChunks: [], audioStream: null, audioContext: null, analyser: null,
    activeSpeakerId: 'sp1', speakerPitches: {}, lastPitch: null,
    recordingStartedAt: null, recordingTimer: null,
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
    state.catalog = await api('/api/meeting-minutes/catalog');
    return state.catalog;
  }

  async function load() {
    const pid = projectId();
    el('mmStatusText').textContent = 'Loading…';
    try {
      await loadCatalog();
      const j = await api(`/api/meeting-minutes${pid ? `?project_id=${pid}` : ''}`);
      state.meetings = j.meetings || [];
      state.stats = j.stats || {};
      ctx.scheduleUrl = j.schedule_url || ctx.scheduleUrl;
      if (el('mmProjectBadge')) el('mmProjectBadge').textContent = ctx.projectName || 'Select a project';
      populateFilters();
      renderStats();
      renderList();
      el('mmUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      el('mmStatusText').textContent = `${state.meetings.length} meeting(s) · ${state.stats.open_actions || 0} open action items`;
    } catch (e) { el('mmStatusText').textContent = 'Error: ' + e.message; }
  }

  function populateFilters() {
    const tf = el('mmTypeFilter');
    if (tf && tf.options.length <= 1) {
      (state.catalog?.meeting_types || []).forEach((t) => tf.add(new Option(t.label, t.key)));
    }
    const sf = el('mmStatusFilter');
    if (sf && sf.options.length <= 1) {
      (state.catalog?.statuses || []).forEach((s) => sf.add(new Option(s, s)));
    }
    const mt = el('mmMeetingType');
    if (mt && mt.options.length <= 1) {
      (state.catalog?.meeting_types || []).forEach((t) => mt.add(new Option(t.label, t.key)));
    }
    fillSelect(el('mmStatus'), state.catalog?.statuses || ['Draft'], 'Draft');
  }

  function renderStats() {
    const s = state.stats;
    const map = {
      mmstatTotal: s.total, mmstatMonth: s.this_month, mmstatScheduled: s.scheduled,
      mmstatDrafts: s.drafts, mmstatRecordings: s.with_recordings,
      mmstatOpenActions: s.open_actions, mmstatOverdue: s.overdue_actions,
    };
    Object.keys(map).forEach((id) => { if (el(id)) el(id).textContent = map[id] ?? 0; });
  }

  function filtered() {
    const term = (el('mmSearch')?.value || '').toLowerCase();
    const tf = el('mmTypeFilter')?.value || '';
    const sf = el('mmStatusFilter')?.value || '';
    return state.meetings.filter((m) => {
      if (tf && m.meeting_type !== tf) return false;
      if (sf && m.status !== sf) return false;
      if (term) {
        const blob = `${m.meeting_number} ${m.subject} ${m.location} ${m.organizer}`.toLowerCase();
        if (!blob.includes(term)) return false;
      }
      return true;
    });
  }

  function typeLabel(key) {
    const t = (state.catalog?.meeting_types || []).find((x) => x.key === key);
    return t ? t.label : (key || '').replace(/_/g, ' ');
  }

  function renderList() {
    const rows = filtered();
    const host = el('mmListHost');
    if (!rows.length) {
      host.innerHTML = '<div class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-users text-4xl mb-3 block text-zinc-600"></i>No meetings yet. Start with New Meeting or use voice capture during your next OAC.</div>';
      return;
    }
    host.innerHTML = `<table class="w-full text-sm"><thead class="bg-zinc-800 text-xs uppercase text-zinc-500 sticky top-0"><tr>
      <th class="text-left px-3 py-2">#</th><th class="text-left px-3 py-2">Date</th><th class="text-left px-3 py-2">Type</th>
      <th class="text-left px-3 py-2">Subject</th><th class="text-left px-3 py-2">Location</th><th class="text-center px-3 py-2">Actions</th>
      <th class="text-left px-3 py-2">Status</th><th class="px-3 py-2"></th>
    </tr></thead><tbody>${rows.map((m) => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" data-open="${m.id}">
        <td class="px-3 py-2 font-mono text-xs">${esc(m.meeting_number)}</td>
        <td class="px-3 py-2 text-xs whitespace-nowrap">${esc(m.meeting_date || '—')}</td>
        <td class="px-3 py-2 text-xs">${esc(typeLabel(m.meeting_type))}</td>
        <td class="px-3 py-2">${esc(m.subject)}${m.has_recording ? ' <i class="fa-solid fa-microphone text-violet-400 text-xs" title="Has recording"></i>' : ''}${m.synced_to_schedule ? ' <span class="text-violet-400 text-xs">🔗</span>' : ''}</td>
        <td class="px-3 py-2 text-xs text-zinc-400">${esc(m.location || '—')}</td>
        <td class="px-3 py-2 text-center"><span class="mm-chip bg-blue-500/20 text-blue-300">${m.open_action_count || 0} open</span></td>
        <td class="px-3 py-2"><span class="mm-chip ${STATUS_COLORS[m.status] || 'bg-zinc-700'}">${esc(m.status)}</span></td>
        <td class="px-3 py-2 text-zinc-500"><i class="fa-solid fa-chevron-right"></i></td>
      </tr>`).join('')}</tbody></table>`;
    host.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openEdit(parseInt(n.getAttribute('data-open'), 10))));
  }

  function setTab(tab) {
    state.tab = tab;
    ['details', 'agenda', 'capture', 'transcript', 'minutes', 'actions'].forEach((t) => {
      el(`mmTab${t.charAt(0).toUpperCase() + t.slice(1)}`)?.classList.toggle('bg-zinc-700', t === tab);
      el(`mmPanel${t.charAt(0).toUpperCase() + t.slice(1)}`)?.classList.toggle('hidden', t !== tab);
    });
    if (tab === 'capture') renderSpeakerBar();
    if (tab === 'transcript') renderTranscriptView();
    if (tab === 'agenda') renderAgendaEditor();
    if (tab === 'actions') renderActionEditor();
  }

  function resetModal() {
    stopAllCapture();
    state.editId = null;
    state.speakers = JSON.parse(JSON.stringify(state.catalog?.default_speakers || []));
    state.transcriptSegments = [];
    state.agenda = [];
    state.actionItems = [];
    state.attendees = [];
    el('mmModalTitle').textContent = 'New Meeting';
    ['mmSubject', 'mmLocation', 'mmVirtualLink', 'mmOrganizer', 'mmDiscussion', 'mmMinutesBody', 'mmAttendeesRaw'].forEach((id) => {
      if (el(id)) el(id).value = '';
    });
    el('mmDate').value = iso(new Date());
    el('mmStartTime').value = '';
    el('mmEndTime').value = '';
    el('mmNextDate').value = '';
    el('mmMeetingType').value = 'oac';
    el('mmStatus').value = 'Draft';
    el('mmPush').checked = false;
    el('mmSyncedBadge').classList.add('hidden');
    el('mmDelete').classList.add('hidden');
    el('mmRecordingPlayer').classList.add('hidden');
    el('mmRecordingPlayer').removeAttribute('src');
    setTab('details');
    loadAgendaTemplate('oac');
  }

  async function openCreate() {
    resetModal();
    el('mmModal').showModal();
  }

  function openEdit(id) {
    const m = state.meetings.find((x) => x.id === id);
    if (!m) return;
    resetModal();
    state.editId = id;
    state.speakers = m.speakers?.length ? m.speakers : JSON.parse(JSON.stringify(state.catalog?.default_speakers || []));
    state.transcriptSegments = m.transcript_segments || [];
    state.agenda = m.agenda || [];
    state.actionItems = m.action_items || [];
    state.attendees = m.attendees || [];
    el('mmModalTitle').textContent = m.meeting_number || 'Meeting';
    el('mmSubject').value = m.subject || '';
    el('mmLocation').value = m.location || '';
    el('mmVirtualLink').value = m.virtual_link || '';
    el('mmOrganizer').value = m.organizer || '';
    el('mmDiscussion').value = m.discussion_notes || '';
    el('mmMinutesBody').value = m.minutes_body || '';
    el('mmDate').value = m.meeting_date || iso(new Date());
    el('mmStartTime').value = m.start_time || '';
    el('mmEndTime').value = m.end_time || '';
    el('mmNextDate').value = m.next_meeting_date || '';
    el('mmMeetingType').value = m.meeting_type || 'other';
    el('mmStatus').value = m.status || 'Draft';
    el('mmAttendeesRaw').value = attendeesToText(state.attendees);
    el('mmPush').checked = m.synced_to_schedule;
    el('mmSyncedBadge').classList.toggle('hidden', !m.synced_to_schedule);
    el('mmDelete').classList.remove('hidden');
    if (m.has_recording) {
      el('mmRecordingPlayer').src = `/api/meeting-minutes/${m.id}/recording`;
      el('mmRecordingPlayer').classList.remove('hidden');
    }
    setTab('details');
    el('mmModal').showModal();
  }

  function attendeesToText(list) {
    return (list || []).map((a) => {
      if (typeof a === 'string') return a;
      const parts = [a.name, a.company].filter(Boolean);
      return parts.join(' — ');
    }).join('\n');
  }

  function textToAttendees(text) {
    return (text || '').split('\n').map((line) => line.trim()).filter(Boolean).map((line) => {
      const parts = line.split(/[—\-–,]/).map((p) => p.trim());
      return { name: parts[0] || line, company: parts[1] || '', present: true };
    });
  }

  async function loadAgendaTemplate(mtype) {
    try {
      const j = await api(`/api/meeting-minutes/catalog?type=${encodeURIComponent(mtype)}`);
      if (j.agenda_template?.length && !state.editId && !state.agenda.length) {
        state.agenda = j.agenda_template.map((x) => ({ ...x, notes: '' }));
        renderAgendaEditor();
      }
    } catch (_) {}
  }

  function renderSpeakerBar() {
    const host = el('mmSpeakerBar');
    if (!host) return;
    host.innerHTML = state.speakers.map((sp) => `
      <button type="button" class="mm-speaker-btn px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${sp.id === state.activeSpeakerId ? 'ring-2 ring-white' : 'opacity-80'}"
        data-sp="${sp.id}" style="background:${sp.color}33;border-color:${sp.color};color:${sp.color}">
        <i class="fa-solid fa-user mr-1"></i>${esc(sp.name || sp.label)}
      </button>`).join('') + `
      <button type="button" id="mmAddSpeaker" class="px-2 py-1.5 rounded-full text-xs bg-zinc-800 border border-zinc-600 text-zinc-400"><i class="fa-solid fa-plus"></i></button>`;
    host.querySelectorAll('[data-sp]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.activeSpeakerId = btn.getAttribute('data-sp');
        renderSpeakerBar();
      });
      btn.addEventListener('dblclick', () => {
        const sp = state.speakers.find((s) => s.id === btn.getAttribute('data-sp'));
        const name = prompt('Speaker name (e.g. Mike B., Superintendent):', sp?.name || sp?.label || '');
        if (name != null && sp) { sp.name = name.trim(); renderSpeakerBar(); }
      });
    });
    el('mmAddSpeaker')?.addEventListener('click', () => {
      const n = state.speakers.length + 1;
      const colors = ['#6366f1', '#f59e0b', '#14b8a6', '#ec4899', '#22c55e', '#0ea5e9'];
      state.speakers.push({ id: `sp${n}`, label: `Person ${n}`, name: '', color: colors[n % colors.length] });
      renderSpeakerBar();
    });
  }

  function activeSpeaker() {
    return state.speakers.find((s) => s.id === state.activeSpeakerId) || state.speakers[0] || { id: 'sp1', label: 'Person 1', name: '' };
  }

  function appendTranscript(text, pitch) {
    const sp = activeSpeaker();
    const label = sp.name || sp.label || 'Speaker';
    const last = state.transcriptSegments[state.transcriptSegments.length - 1];
    if (last && last.speaker_id === sp.id && Date.now() - (last._ts || 0) < 8000) {
      last.text = `${last.text} ${text}`.trim();
      last._ts = Date.now();
      if (pitch) last.pitch_hz = pitch;
    } else {
      state.transcriptSegments.push({
        speaker_id: sp.id, speaker_label: label, text: text.trim(),
        ts: new Date().toISOString(), pitch_hz: pitch || null, _ts: Date.now(),
      });
    }
    if (pitch) {
      const arr = state.speakerPitches[sp.id] || (state.speakerPitches[sp.id] = []);
      arr.push(pitch);
      if (arr.length > 20) arr.shift();
    }
    renderTranscriptView();
    syncDiscussionFromTranscript();
  }

  function syncDiscussionFromTranscript() {
    const lines = state.transcriptSegments.map((s) => `${s.speaker_label}: ${s.text}`);
    if (el('mmDiscussion')) el('mmDiscussion').value = lines.join('\n\n');
  }

  function renderTranscriptView() {
    const host = el('mmTranscriptView');
    if (!host) return;
    if (!state.transcriptSegments.length) {
      host.innerHTML = '<div class="text-zinc-500 text-sm py-4">No transcript yet. Use Live Capture to dictate with speaker tags.</div>';
      return;
    }
    host.innerHTML = state.transcriptSegments.map((s, i) => `
      <div class="mb-3 p-2 rounded-md bg-zinc-800/50 border border-zinc-700">
        <div class="text-xs font-semibold text-violet-300 mb-1">${esc(s.speaker_label)}${s.pitch_hz ? ` <span class="text-zinc-500 font-normal">(~${Math.round(s.pitch_hz)} Hz)</span>` : ''}</div>
        <div class="text-sm text-zinc-200">${esc(s.text)}</div>
      </div>`).join('');
  }

  function renderAgendaEditor() {
    const host = el('mmAgendaEditor');
    if (!host) return;
    host.innerHTML = (state.agenda.length ? state.agenda : [{ topic: '', presenter: '', minutes: 15, notes: '' }]).map((item, i) => `
      <div class="grid grid-cols-1 md:grid-cols-12 gap-2 mb-2 items-start" data-agenda="${i}">
        <div class="md:col-span-1 text-xs text-zinc-500 pt-2">${i + 1}.</div>
        <div class="md:col-span-5"><input class="mm-input mm-agenda-topic" value="${esc(item.topic || '')}" placeholder="Agenda topic"></div>
        <div class="md:col-span-2"><input class="mm-input mm-agenda-presenter" value="${esc(item.presenter || '')}" placeholder="Presenter"></div>
        <div class="md:col-span-1"><input type="number" class="mm-input mm-agenda-min" value="${item.minutes || 15}" min="1"></div>
        <div class="md:col-span-2"><input class="mm-input mm-agenda-notes" value="${esc(item.notes || '')}" placeholder="Notes"></div>
        <div class="md:col-span-1"><button type="button" class="text-red-400 text-xs mm-agenda-del" data-i="${i}"><i class="fa-solid fa-trash"></i></button></div>
      </div>`).join('') + '<button type="button" id="mmAgendaAdd" class="text-xs text-emerald-400 mt-1"><i class="fa-solid fa-plus mr-1"></i>Add item</button>';
    host.querySelectorAll('.mm-agenda-del').forEach((b) => b.addEventListener('click', () => {
      state.agenda.splice(parseInt(b.getAttribute('data-i'), 10), 1);
      renderAgendaEditor();
    }));
    el('mmAgendaAdd')?.addEventListener('click', () => {
      state.agenda.push({ topic: '', presenter: '', minutes: 15, notes: '' });
      renderAgendaEditor();
    });
  }

  function collectAgenda() {
    const host = el('mmAgendaEditor');
    if (!host) return state.agenda;
    return [...host.querySelectorAll('[data-agenda]')].map((row) => ({
      topic: row.querySelector('.mm-agenda-topic')?.value.trim() || '',
      presenter: row.querySelector('.mm-agenda-presenter')?.value.trim() || '',
      minutes: parseInt(row.querySelector('.mm-agenda-min')?.value, 10) || 15,
      notes: row.querySelector('.mm-agenda-notes')?.value.trim() || '',
    })).filter((x) => x.topic);
  }

  function renderActionEditor() {
    const host = el('mmActionEditor');
    if (!host) return;
    const items = state.actionItems.length ? state.actionItems : [];
    host.innerHTML = (items.length ? items : [{ description: '', assigned_to: '', due_date: '', status: 'Open', priority: 'Normal' }]).map((a, i) => `
      <div class="grid grid-cols-1 md:grid-cols-12 gap-2 mb-2" data-action="${i}">
        <div class="md:col-span-4"><input class="mm-input mm-act-desc" value="${esc(a.description || '')}" placeholder="Action description"></div>
        <div class="md:col-span-2"><input class="mm-input mm-act-assign" value="${esc(a.assigned_to || '')}" placeholder="Assigned to"></div>
        <div class="md:col-span-2"><input type="date" class="mm-input mm-act-due" value="${esc(a.due_date || '')}"></div>
        <div class="md:col-span-2"><select class="mm-input mm-act-status">${(state.catalog?.action_statuses || ['Open']).map((s) => `<option ${s === (a.status || 'Open') ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
        <div class="md:col-span-1"><select class="mm-input mm-act-pri">${(state.catalog?.action_priorities || ['Normal']).map((p) => `<option ${p === (a.priority || 'Normal') ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
        <div class="md:col-span-1"><button type="button" class="text-red-400 mm-act-del" data-i="${i}"><i class="fa-solid fa-trash"></i></button></div>
      </div>`).join('') + '<button type="button" id="mmActionAdd" class="text-xs text-emerald-400 mt-1"><i class="fa-solid fa-plus mr-1"></i>Add action item</button>';
    host.querySelectorAll('.mm-act-del').forEach((b) => b.addEventListener('click', () => {
      state.actionItems.splice(parseInt(b.getAttribute('data-i'), 10), 1);
      renderActionEditor();
    }));
    el('mmActionAdd')?.addEventListener('click', () => {
      state.actionItems.push({ description: '', assigned_to: '', due_date: '', status: 'Open', priority: 'Normal' });
      renderActionEditor();
    });
  }

  function collectActions() {
    const host = el('mmActionEditor');
    if (!host) return state.actionItems;
    return [...host.querySelectorAll('[data-action]')].map((row, i) => ({
      id: state.actionItems[i]?.id,
      item_number: state.actionItems[i]?.item_number || `AI-${String(i + 1).padStart(2, '0')}`,
      description: row.querySelector('.mm-act-desc')?.value.trim() || '',
      assigned_to: row.querySelector('.mm-act-assign')?.value.trim() || '',
      due_date: row.querySelector('.mm-act-due')?.value || '',
      status: row.querySelector('.mm-act-status')?.value || 'Open',
      priority: row.querySelector('.mm-act-pri')?.value || 'Normal',
    })).filter((x) => x.description);
  }

  function fillSelect(sel, opts, val) {
    if (!sel) return;
    sel.innerHTML = opts.map((o) => `<option value="${esc(o)}" ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join('');
  }

  function collectPayload() {
    state.agenda = collectAgenda();
    state.actionItems = collectActions();
    state.attendees = textToAttendees(el('mmAttendeesRaw')?.value || '');
    return {
      project_id: projectId(),
      subject: el('mmSubject').value.trim(),
      meeting_date: el('mmDate').value,
      start_time: el('mmStartTime').value.trim(),
      end_time: el('mmEndTime').value.trim(),
      next_meeting_date: el('mmNextDate').value || null,
      meeting_type: el('mmMeetingType').value,
      status: el('mmStatus').value,
      location: el('mmLocation').value.trim(),
      virtual_link: el('mmVirtualLink').value.trim(),
      organizer: el('mmOrganizer').value.trim(),
      attendees: state.attendees,
      agenda: state.agenda,
      discussion_notes: el('mmDiscussion').value.trim(),
      minutes_body: el('mmMinutesBody').value.trim(),
      transcript_segments: state.transcriptSegments.map(({ _ts, ...rest }) => rest),
      speakers: state.speakers,
      action_items: state.actionItems,
      push_to_schedule: el('mmPush').checked,
    };
  }

  async function save() {
    const payload = collectPayload();
    if (!payload.project_id || !payload.subject) { alert('Project and subject are required.'); return; }
    const btn = el('mmSave');
    btn.disabled = true;
    btn.textContent = 'Saving…';
    try {
      const url = state.editId ? `/api/meeting-minutes/${state.editId}` : '/api/meeting-minutes';
      const j = await api(url, { method: state.editId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (state.audioChunks.length && j.meeting?.id) {
        await uploadRecording(j.meeting.id);
      }
      el('mmModal').close();
      stopAllCapture();
      await load();
      if (global.showToast) global.showToast('Meeting saved');
    } catch (e) { alert(e.message); }
    finally { btn.disabled = false; btn.textContent = 'Save'; }
  }

  async function uploadRecording(meetingId) {
    if (!state.audioChunks.length) return;
    const blob = new Blob(state.audioChunks, { type: 'audio/webm' });
    const fd = new FormData();
    fd.append('file', blob, 'recording.webm');
    const dur = state.recordingStartedAt ? Math.round((Date.now() - state.recordingStartedAt) / 1000) : 0;
    fd.append('duration_sec', String(dur));
    await api(`/api/meeting-minutes/${meetingId}/recording`, { method: 'POST', body: fd });
    state.audioChunks = [];
  }

  async function del() {
    if (!state.editId || !confirm('Delete this meeting and its recording?')) return;
    try {
      await api(`/api/meeting-minutes/${state.editId}`, { method: 'DELETE' });
      el('mmModal').close();
      await load();
    } catch (e) { alert(e.message); }
  }

  async function generateMinutes() {
    if (!state.editId) {
      const payload = collectPayload();
      payload.auto_generate_minutes = true;
      if (!payload.project_id || !payload.subject) { alert('Save subject first or save the meeting.'); return; }
      try {
        const j = await api('/api/meeting-minutes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        state.editId = j.meeting.id;
        el('mmMinutesBody').value = j.meeting.minutes_body || '';
        setTab('minutes');
        if (global.showToast) global.showToast('Minutes generated');
      } catch (e) { alert(e.message); }
      return;
    }
    try {
      const j = await api(`/api/meeting-minutes/${state.editId}/generate?extract_actions=1`, { method: 'POST' });
      el('mmMinutesBody').value = j.meeting.minutes_body || '';
      state.actionItems = j.meeting.action_items || [];
      renderActionEditor();
      setTab('minutes');
      if (global.showToast) global.showToast('Minutes generated');
    } catch (e) { alert(e.message); }
  }

  async function fileToDocuments() {
    if (!state.editId) { alert('Save the meeting first.'); return; }
    try {
      await api(`/api/meeting-minutes/${state.editId}/file-to-documents`, { method: 'POST' });
      if (global.showToast) global.showToast('Filed to Documents › Meeting Minutes');
    } catch (e) { alert(e.message); }
  }

  function printMinutes() {
    const body = el('mmMinutesBody')?.value || '';
    const subject = el('mmSubject')?.value || 'Meeting Minutes';
    const html = `<!DOCTYPE html><html><head><title>${esc(subject)}</title>
      <style>body{font-family:Georgia,serif;max-width:720px;margin:2rem auto;line-height:1.5;white-space:pre-wrap;}</style></head>
      <body><h1>${esc(subject)}</h1><pre style="font-family:inherit;white-space:pre-wrap;">${esc(body)}</pre></body></html>`;
    if (global.CasePMPrint?.printHtmlInIframe) {
      global.CasePMPrint.printHtmlInIframe(html, subject);
    } else {
      const w = window.open('', '_blank');
      w.document.write(html);
      w.document.close();
      w.print();
    }
  }

  async function pushAll() {
    const pid = projectId();
    if (!pid) { alert('Select a project first.'); return; }
    if (!confirm('Push all dated meetings to the Schedule as milestones?')) return;
    try {
      const j = await api(`/api/meeting-minutes/push-to-schedule?project_id=${pid}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      await load();
      const go = confirm(`Pushed ${j.pushed} meeting(s). Open Schedule?`);
      if (go) window.location.href = (ctx.scheduleUrl || '/schedule') + `?project_id=${pid}`;
    } catch (e) { alert(e.message); }
  }

  // ── Voice: pitch estimation (rough speaker-change hint) ─────────────────
  function estimatePitch() {
    if (!state.analyser) return null;
    const buf = new Float32Array(state.analyser.fftSize);
    state.analyser.getFloatTimeDomainData(buf);
    let bestLag = -1;
    let bestCorr = 0;
    const minLag = Math.floor(state.audioContext.sampleRate / 400);
    const maxLag = Math.floor(state.audioContext.sampleRate / 80);
    for (let lag = minLag; lag < maxLag; lag++) {
      let corr = 0;
      for (let i = 0; i < buf.length - lag; i++) corr += buf[i] * buf[i + lag];
      if (corr > bestCorr) { bestCorr = corr; bestLag = lag; }
    }
    if (bestLag <= 0 || bestCorr < 0.01) return null;
    return state.audioContext.sampleRate / bestLag;
  }

  function suggestSpeakerFromPitch(pitch) {
    if (!pitch) return null;
    let bestId = null;
    let bestDiff = Infinity;
    Object.keys(state.speakerPitches).forEach((sid) => {
      const arr = state.speakerPitches[sid];
      if (!arr?.length) return;
      const avg = arr.reduce((a, b) => a + b, 0) / arr.length;
      const diff = Math.abs(avg - pitch) / avg;
      if (diff < bestDiff && diff < 0.12) { bestDiff = diff; bestId = sid; }
    });
    return bestId;
  }

  function maybeSwitchSpeaker(pitch) {
    if (!pitch || !state.listening) return;
    const current = state.speakerPitches[state.activeSpeakerId];
    if (!current?.length) return;
    const avg = current.reduce((a, b) => a + b, 0) / current.length;
    const delta = Math.abs(pitch - avg) / avg;
    if (delta > 0.18) {
      const suggested = suggestSpeakerFromPitch(pitch);
      if (suggested && suggested !== state.activeSpeakerId) {
        state.activeSpeakerId = suggested;
        renderSpeakerBar();
        if (global.showToast) global.showToast('Speaker voice change detected — switched tag');
      }
    }
  }

  async function startAudioAnalysis() {
    try {
      if (!state.audioStream) {
        state.audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      state.audioContext = new (global.AudioContext || global.webkitAudioContext)();
      const src = state.audioContext.createMediaStreamSource(state.audioStream);
      state.analyser = state.audioContext.createAnalyser();
      state.analyser.fftSize = 2048;
      src.connect(state.analyser);
    } catch (_) {}
  }

  function startDictation() {
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    const hint = el('mmCaptureHint');
    if (!window.isSecureContext) {
      if (hint) hint.innerHTML = '<span class="text-amber-400">Voice needs HTTPS. Type notes manually or use recording only.</span>';
      return;
    }
    if (!SR) {
      if (hint) hint.innerHTML = '<span class="text-amber-400">Speech recognition not supported in this browser. Recording still works.</span>';
      return;
    }
    if (state.listening) return;
    try {
      const rec = new SR();
      rec.lang = 'en-US';
      rec.interimResults = true;
      rec.continuous = true;
      let lastFinal = '';
      rec.onresult = (event) => {
        let interim = '';
        let finalText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const t = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += t;
          else interim += t;
        }
        const pitch = estimatePitch();
        if (pitch) maybeSwitchSpeaker(pitch);
        if (finalText && finalText !== lastFinal) {
          appendTranscript(finalText.trim(), pitch);
          lastFinal = finalText;
        } else if (interim && el('mmLivePreview')) {
          el('mmLivePreview').textContent = `${activeSpeaker().name || activeSpeaker().label}: ${interim}`;
        }
      };
      rec.onerror = () => stopDictation();
      rec.onend = () => { if (state.listening) { try { rec.start(); } catch (_) { stopDictation(); } } };
      rec.start();
      state.recognition = rec;
      state.listening = true;
      el('mmDictateBtn')?.classList.add('ring-2', 'ring-red-500');
      el('mmDictateLabel').textContent = 'Stop dictation';
      if (hint) hint.textContent = 'Listening… tap a speaker chip if the wrong person is tagged.';
      startAudioAnalysis();
    } catch (e) {
      if (hint) hint.textContent = 'Could not start dictation: ' + e.message;
    }
  }

  function stopDictation() {
    state.listening = false;
    if (state.recognition) { try { state.recognition.stop(); } catch (_) {} state.recognition = null; }
    el('mmDictateBtn')?.classList.remove('ring-2', 'ring-red-500');
    if (el('mmDictateLabel')) el('mmDictateLabel').textContent = 'Dictate';
    if (el('mmLivePreview')) el('mmLivePreview').textContent = '';
  }

  async function startRecording() {
    if (state.recording) return;
    try {
      if (!state.audioStream) {
        state.audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      await startAudioAnalysis();
      state.audioChunks = [];
      const rec = new MediaRecorder(state.audioStream, { mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4' });
      rec.ondataavailable = (e) => { if (e.data.size) state.audioChunks.push(e.data); };
      rec.start(1000);
      state.mediaRecorder = rec;
      state.recording = true;
      state.recordingStartedAt = Date.now();
      el('mmRecordBtn')?.classList.add('ring-2', 'ring-red-500');
      el('mmRecordLabel').textContent = 'Stop recording';
      state.recordingTimer = setInterval(() => {
        const sec = Math.round((Date.now() - state.recordingStartedAt) / 1000);
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        if (el('mmRecordTimer')) el('mmRecordTimer').textContent = `${m}:${String(s).padStart(2, '0')}`;
      }, 500);
      if (!state.listening) startDictation();
    } catch (e) { alert('Microphone access denied or unavailable: ' + e.message); }
  }

  function stopRecording() {
    state.recording = false;
    if (state.mediaRecorder) { try { state.mediaRecorder.stop(); } catch (_) {} state.mediaRecorder = null; }
    el('mmRecordBtn')?.classList.remove('ring-2', 'ring-red-500');
    if (el('mmRecordLabel')) el('mmRecordLabel').textContent = 'Record';
    clearInterval(state.recordingTimer);
  }

  function stopAllCapture() {
    stopDictation();
    stopRecording();
    if (state.audioStream) {
      state.audioStream.getTracks().forEach((t) => t.stop());
      state.audioStream = null;
    }
    if (state.audioContext) { try { state.audioContext.close(); } catch (_) {} state.audioContext = null; }
    state.analyser = null;
  }

  function bind() {
    el('mmBtnNew').addEventListener('click', openCreate);
    el('mmBtnRefresh')?.addEventListener('click', load);
    el('mmPushAll')?.addEventListener('click', pushAll);
    el('mmModalClose').addEventListener('click', () => { stopAllCapture(); el('mmModal').close(); });
    el('mmCancel').addEventListener('click', () => { stopAllCapture(); el('mmModal').close(); });
    el('mmSave').addEventListener('click', save);
    el('mmDelete').addEventListener('click', del);
    el('mmGenerate').addEventListener('click', generateMinutes);
    el('mmFileDocs').addEventListener('click', fileToDocuments);
    el('mmPrint').addEventListener('click', printMinutes);
    ['mmTabDetails', 'mmTabAgenda', 'mmTabCapture', 'mmTabTranscript', 'mmTabMinutes', 'mmTabActions'].forEach((id) => {
      el(id)?.addEventListener('click', () => setTab(id.replace('mmTab', '').toLowerCase()));
    });
    el('mmMeetingType')?.addEventListener('change', (e) => {
      if (!state.editId) loadAgendaTemplate(e.target.value);
    });
    el('mmDictateBtn')?.addEventListener('click', () => state.listening ? stopDictation() : startDictation());
    el('mmRecordBtn')?.addEventListener('click', () => state.recording ? stopRecording() : startRecording());
    ['mmSearch', 'mmTypeFilter', 'mmStatusFilter'].forEach((id) => {
      const node = el(id);
      if (node) { node.addEventListener('input', renderList); node.addEventListener('change', renderList); }
    });
    global.addEventListener('casepm:project-changed', load);
    global.onCasePmProjectChanged = (pid) => { ctx.projectId = pid; load(); };
  }

  function init() { bind(); load(); }
  global.CasePMMeetings = { refresh: load };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
