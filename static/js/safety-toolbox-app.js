/**
 * Case PM Safety — Toolbox / tailgate talks with agenda, recording, dictation, voice training.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_SAFETY_CTX || {};
  const MEETING_TYPE = 'toolbox_talk';
  const state = {
    meetings: [], catalog: null, editId: null, tab: 'details',
    agenda: [], transcriptSegments: [], speakers: [],
    recording: false, listening: false, recordChunks: [],
    audioStream: null, mediaRecorder: null, audioContext: null, analyser: null,
    recordingStartedAt: null, recordTimer: null, recognition: null,
    voiceEngine: null, playbackHighlightIdx: -1,
  };

  function el(id) { return document.getElementById(id); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function projectId() { return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })(); }
  async function api(url, opts) { const r = await fetch(url, opts); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Request failed'); return j; }
  function fmtDate(iso) { if (!iso) return ''; try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch (_) { return iso; } }

  function voice() {
    if (!state.voiceEngine && global.CasePMVoiceDiarization) {
      state.voiceEngine = global.CasePMVoiceDiarization.createSpeakerEngine();
    }
    return state.voiceEngine;
  }

  async function loadCatalog() {
    if (state.catalog) return state.catalog;
    const j = await api('/api/meeting-minutes/catalog');
    state.catalog = j;
    return j;
  }

  async function refresh() {
    const pid = projectId();
    if (!el('tbList')) return;
    try {
      const j = await api(`/api/meeting-minutes?meeting_type=${MEETING_TYPE}${pid ? `&project_id=${pid}` : ''}`);
      state.meetings = j.meetings || [];
      renderList();
    } catch (e) {
      if (el('tbList')) el('tbList').innerHTML = `<div class="px-6 py-8 text-center text-red-400 text-sm">${esc(e.message)}</div>`;
    }
  }

  function renderList() {
    const host = el('tbList');
    if (!host) return;
    const term = (el('tbSearch')?.value || '').toLowerCase();
    const rows = state.meetings.filter((m) => {
      if (!term) return true;
      return `${m.subject} ${m.location || ''} ${m.organizer || ''}`.toLowerCase().includes(term);
    });
    if (!rows.length) {
      host.innerHTML = '<div class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-toolbox text-4xl mb-3 block text-zinc-600"></i>No toolbox meetings yet. Start with <b>New Toolbox Meeting</b>.</div>';
      return;
    }
    host.innerHTML = rows.map((m) => `
      <div class="saf-row" data-tb-open="${m.id}">
        <i class="fa-solid fa-toolbox text-emerald-400 text-lg w-6 text-center"></i>
        <div class="min-w-0 flex-1">
          <div class="text-sm truncate">${esc(m.subject || 'Toolbox talk')}</div>
          <div class="saf-meta">
            <span><i class="fa-solid fa-calendar"></i> ${fmtDate(m.meeting_date)}</span>
            ${m.location ? `<span><i class="fa-solid fa-location-dot"></i> ${esc(m.location)}</span>` : ''}
            ${m.organizer ? `<span><i class="fa-solid fa-user"></i> ${esc(m.organizer)}</span>` : ''}
            ${m.has_recording ? '<span><i class="fa-solid fa-microphone text-red-400"></i> Recording</span>' : ''}
          </div>
        </div>
        <span class="saf-chip bg-zinc-700 text-zinc-300">${esc(m.status || 'Draft')}</span>
      </div>`).join('');
    host.querySelectorAll('[data-tb-open]').forEach((n) => n.addEventListener('click', () => openMeeting(parseInt(n.getAttribute('data-tb-open'), 10))));
  }

  function setTab(tab) {
    state.tab = tab;
    ['Details', 'Agenda', 'Capture', 'Transcript', 'Minutes'].forEach((t) => {
      const key = t.toLowerCase();
      el(`tbTab${t}`)?.classList.toggle('active', key === tab);
      el(`tbPanel${t}`)?.classList.toggle('hidden', key !== tab);
    });
  }

  function loadAgendaTemplate() {
    const tpl = (state.catalog?.agenda_templates || {})[MEETING_TYPE] || [];
    state.agenda = tpl.map((row, i) => ({ ...row, idx: i + 1, notes: row.notes || '' }));
    renderAgenda();
  }

  function renderAgenda() {
    const host = el('tbAgendaEditor');
    if (!host) return;
    host.innerHTML = state.agenda.map((row, i) => `
      <div class="grid grid-cols-12 gap-2 mb-2 items-center">
        <div class="col-span-1 text-xs text-zinc-500">${i + 1}</div>
        <div class="col-span-5"><input class="saf-input text-xs" data-agenda-field="topic" data-agenda-i="${i}" value="${esc(row.topic || '')}"></div>
        <div class="col-span-2"><input class="saf-input text-xs" data-agenda-field="presenter" data-agenda-i="${i}" value="${esc(row.presenter || '')}"></div>
        <div class="col-span-1"><input type="number" class="saf-input text-xs" data-agenda-field="minutes" data-agenda-i="${i}" value="${row.minutes || ''}"></div>
        <div class="col-span-3"><input class="saf-input text-xs" data-agenda-field="notes" data-agenda-i="${i}" value="${esc(row.notes || '')}" placeholder="Notes"></div>
      </div>`).join('');
    host.querySelectorAll('[data-agenda-field]').forEach((inp) => {
      inp.addEventListener('input', () => {
        const i = parseInt(inp.getAttribute('data-agenda-i'), 10);
        const field = inp.getAttribute('data-agenda-field');
        if (state.agenda[i]) state.agenda[i][field] = inp.type === 'number' ? parseInt(inp.value, 10) || 0 : inp.value;
      });
    });
  }

  function renderSpeakerBar() {
    const host = el('tbSpeakerBar');
    if (!host) return;
    const eng = voice();
    host.innerHTML = eng.getSpeakers().map((sp) => {
      const trained = sp.voice_profile?.trained_count > 0;
      return `<button type="button" class="px-3 py-1 rounded-full text-xs font-medium border ${eng.getActiveSpeakerId() === sp.id ? 'border-white' : 'border-zinc-600'}" data-sp-id="${sp.id}" style="background:${sp.color}22;color:${sp.color}">
        <i class="fa-solid fa-user mr-1"></i>${esc(sp.name || sp.label)}${trained ? ' <i class="fa-solid fa-brain text-[9px]"></i>' : ''}
      </button>`;
    }).join('');
    host.querySelectorAll('[data-sp-id]').forEach((btn) => {
      btn.addEventListener('click', () => { eng.setActiveSpeakerId(btn.getAttribute('data-sp-id')); renderSpeakerBar(); });
      btn.addEventListener('dblclick', () => {
        const name = prompt('Speaker name:', eng.getSpeakers().find((s) => s.id === btn.getAttribute('data-sp-id'))?.name || '');
        if (name != null) { eng.renameSpeaker(btn.getAttribute('data-sp-id'), name); state.speakers = eng.getSpeakers(); renderSpeakerBar(); }
      });
    });
  }

  function appendTranscript(text, isFinal) {
    if (!text?.trim()) return;
    const eng = voice();
    const fingerprint = eng.captureFingerprint();
    const speakerId = eng.autoAssignSpeaker(fingerprint);
    const sp = eng.getSpeakers().find((s) => s.id === speakerId);
    const last = state.transcriptSegments[state.transcriptSegments.length - 1];
    if (last && last.speaker_id === speakerId && !last.locked) {
      last.text += (isFinal ? ' ' : '') + text.trim();
      if (fingerprint) last.voice_fingerprint = fingerprint;
    } else {
      state.transcriptSegments.push({
        speaker_id: speakerId,
        speaker_label: eng.speakerLabel(sp),
        text: text.trim(),
        audio_offset_ms: eng.audioOffsetMs(),
        voice_fingerprint: fingerprint || null,
        auto_assigned: true,
      });
    }
    state.speakers = eng.getSpeakers();
    renderSpeakerBar();
    renderTranscript();
    syncDiscussion();
    if (el('tbLivePreview')) el('tbLivePreview').textContent = state.transcriptSegments.slice(-1)[0]?.text || '';
  }

  function renderTranscript() {
    const host = el('tbTranscriptView');
    if (!host) return;
    if (!state.transcriptSegments.length) {
      host.innerHTML = '<div class="text-zinc-500 text-sm py-4">No transcript yet. Record and dictate on the Record tab.</div>';
      return;
    }
    host.innerHTML = state.transcriptSegments.map((seg, i) => `
      <div class="mb-2 p-2 rounded-md border border-zinc-800 hover:bg-zinc-800/50 cursor-pointer ${state.playbackHighlightIdx === i ? 'bg-zinc-800' : ''}" data-tb-seg="${i}">
        <div class="text-xs font-semibold mb-0.5" style="color:${(state.speakers.find(s => s.id === seg.speaker_id) || {}).color || '#a1a1aa'}">${esc(seg.speaker_label)}${seg.user_corrected ? ' <i class="fa-solid fa-brain text-[9px]"></i>' : ''}</div>
        <div class="text-sm text-zinc-200">${esc(seg.text)}</div>
      </div>`).join('');
    host.querySelectorAll('[data-tb-seg]').forEach((row) => {
      row.addEventListener('click', (e) => {
        const idx = parseInt(row.getAttribute('data-tb-seg'), 10);
        if (e.target.closest('[data-tb-seg]')) showSpeakerPicker(idx, row);
      });
    });
  }

  function showSpeakerPicker(segIdx, anchorEl) {
    const eng = voice();
    document.getElementById('tbSpeakerPicker')?.remove();
    const pop = document.createElement('div');
    pop.id = 'tbSpeakerPicker';
    pop.className = 'fixed z-[100001] bg-zinc-900 border border-zinc-600 rounded-lg shadow-xl p-2 min-w-[180px]';
    pop.innerHTML = eng.getSpeakers().map((sp) => `
      <button type="button" class="w-full text-left px-3 py-2 text-sm rounded-md hover:bg-zinc-800 tb-pick-sp" data-sp="${sp.id}" style="color:${sp.color}">${esc(sp.name || sp.label)}</button>`).join('');
    document.body.appendChild(pop);
    const rect = anchorEl.getBoundingClientRect();
    pop.style.left = `${Math.min(rect.left, window.innerWidth - 200)}px`;
    pop.style.top = `${rect.bottom + 4}px`;
    pop.querySelectorAll('.tb-pick-sp').forEach((btn) => {
      btn.addEventListener('click', () => {
        reassignSegment(segIdx, btn.getAttribute('data-sp'));
        pop.remove();
      });
    });
    setTimeout(() => document.addEventListener('click', function close(e) {
      if (!pop.contains(e.target)) { pop.remove(); document.removeEventListener('click', close); }
    }), 0);
  }

  function reassignSegment(segIdx, newSpeakerId) {
    const eng = voice();
    const seg = state.transcriptSegments[segIdx];
    const sp = eng.getSpeakers().find((s) => s.id === newSpeakerId);
    if (!seg || !sp) return;
    seg.speaker_id = newSpeakerId;
    seg.speaker_label = eng.speakerLabel(sp);
    seg.user_corrected = true;
    if (seg.voice_fingerprint) eng.trainFromCorrection(newSpeakerId, seg.voice_fingerprint);
    state.speakers = eng.getSpeakers();
    eng.persistProfiles(projectId());
    renderSpeakerBar();
    renderTranscript();
    syncDiscussion();
  }

  function syncDiscussion() {
    const lines = state.transcriptSegments.map((s) => `${s.speaker_label}: ${s.text}`);
    if (el('tbDiscussion')) el('tbDiscussion').value = lines.join('\n\n');
  }

  function resetModal() {
    state.editId = null;
    state.transcriptSegments = [];
    state.agenda = [];
    stopAllCapture();
    el('tbModalTitle').textContent = 'New Toolbox Meeting';
    el('tbDelete').classList.add('hidden');
    el('tbSubject').value = '';
    el('tbDate').value = new Date().toISOString().slice(0, 10);
    el('tbLocation').value = '';
    el('tbOrganizer').value = '';
    el('tbAttendees').value = '';
    el('tbDiscussion').value = '';
    el('tbMinutesBody').value = '';
    const player = el('tbRecordingPlayer');
    if (player) { player.src = ''; player.classList.add('hidden'); }
    const eng = voice();
    eng.initSpeakers((state.catalog?.default_speakers) || [], projectId());
    state.speakers = eng.getSpeakers();
    loadAgendaTemplate();
    renderSpeakerBar();
    renderTranscript();
    setTab('details');
  }

  async function openCreate() {
    await loadCatalog();
    resetModal();
    el('tbModal').showModal();
  }

  async function openMeeting(id) {
    await loadCatalog();
    const j = await api(`/api/meeting-minutes/${id}`);
    const m = j.meeting;
    state.editId = id;
    el('tbModalTitle').textContent = m.subject || 'Toolbox Meeting';
    el('tbDelete').classList.remove('hidden');
    el('tbSubject').value = m.subject || '';
    el('tbDate').value = m.meeting_date || '';
    el('tbLocation').value = m.location || '';
    el('tbOrganizer').value = m.organizer || '';
    el('tbAttendees').value = (m.attendees || []).map((a) => `${a.name || ''}${a.company ? ' — ' + a.company : ''}`).join('\n');
    el('tbDiscussion').value = m.discussion_notes || '';
    el('tbMinutesBody').value = m.minutes_body || '';
    state.agenda = m.agenda || [];
    if (!state.agenda.length) loadAgendaTemplate();
    else renderAgenda();
    state.transcriptSegments = m.transcript_segments || [];
    const eng = voice();
    eng.initSpeakers(m.speakers || state.catalog?.default_speakers || [], projectId());
    state.speakers = eng.getSpeakers();
    renderSpeakerBar();
    renderTranscript();
    if (m.has_recording) {
      const player = el('tbRecordingPlayer');
      if (player) { player.src = `/api/meeting-minutes/${id}/recording`; player.classList.remove('hidden'); }
    }
    el('tbModal').showModal();
  }

  function collectPayload() {
    const attendees = (el('tbAttendees').value || '').split('\n').map((line) => {
      const parts = line.split('—').map((s) => s.trim());
      return { name: parts[0] || '', company: parts[1] || '' };
    }).filter((a) => a.name);
    return {
      project_id: projectId(),
      meeting_type: MEETING_TYPE,
      subject: el('tbSubject').value.trim() || 'Toolbox / Tailgate Talk',
      meeting_date: el('tbDate').value,
      location: el('tbLocation').value.trim(),
      organizer: el('tbOrganizer').value.trim(),
      status: 'Completed',
      attendees,
      discussion_notes: el('tbDiscussion').value,
      minutes_body: el('tbMinutesBody').value,
      agenda: state.agenda,
      transcript_segments: state.transcriptSegments,
      speakers: voice().getSpeakers(),
    };
  }

  async function save() {
    const payload = collectPayload();
    if (!payload.project_id) { alert('Select a project first.'); return; }
    const url = state.editId ? `/api/meeting-minutes/${state.editId}` : '/api/meeting-minutes';
    const method = state.editId ? 'PUT' : 'POST';
    const j = await api(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const meetingId = state.editId || j.meeting?.id;
    voice().persistProfiles(projectId());
    if (state.recordChunks.length && meetingId) {
      const blob = new Blob(state.recordChunks, { type: state.recordChunks[0]?.type || 'audio/webm' });
      const fd = new FormData();
      fd.append('file', blob, 'toolbox-recording.webm');
      await fetch(`/api/meeting-minutes/${meetingId}/recording`, { method: 'POST', body: fd });
      state.recordChunks = [];
    }
    stopAllCapture();
    el('tbModal').close();
    refresh();
  }

  async function del() {
    if (!state.editId || !confirm('Delete this toolbox meeting?')) return;
    await api(`/api/meeting-minutes/${state.editId}`, { method: 'DELETE' });
    el('tbModal').close();
    refresh();
  }

  async function generateMinutes() {
    if (!state.editId) { alert('Save the meeting first.'); return; }
    const j = await api(`/api/meeting-minutes/${state.editId}/generate`, { method: 'POST' });
    if (j.minutes_body) el('tbMinutesBody').value = j.minutes_body;
  }

  function printAgenda(blank) {
    const project = ctx.projectName || 'Project';
    const date = el('tbDate')?.value || new Date().toISOString().slice(0, 10);
    const subject = blank ? 'Toolbox / Tailgate Talk' : (el('tbSubject').value || 'Toolbox Talk');
    const rows = blank ? (state.catalog?.agenda_templates?.[MEETING_TYPE] || []) : state.agenda;
    const html = `<!DOCTYPE html><html><head><title>Toolbox Agenda</title>
      <style>body{font-family:Arial,sans-serif;padding:24px;color:#111}h1{font-size:18px}table{width:100%;border-collapse:collapse;margin-top:16px}th,td{border:1px solid #ccc;padding:8px;text-align:left;font-size:12px}th{background:#f4f4f5}.meta{font-size:12px;color:#444;margin:8px 0}.sign{margin-top:32px;font-size:11px} .sign td{height:28px}</style></head><body>
      <h1>Toolbox / Tailgate Safety Meeting</h1>
      <div class="meta"><strong>Project:</strong> ${esc(project)} &nbsp; <strong>Date:</strong> ${esc(date)} &nbsp; <strong>Topic:</strong> ${esc(subject)}</div>
      <p style="font-size:11px;color:#555">OSHA 1926.21(b)(2) — employers must instruct employees on hazards, safe practices, and emergency procedures. Document attendance and topics covered.</p>
      <table><thead><tr><th>#</th><th>Agenda item</th><th>Led by</th><th>Min</th><th>Notes / discussion</th></tr></thead><tbody>
      ${rows.map((r, i) => `<tr><td>${i + 1}</td><td>${esc(r.topic || '')}</td><td>${esc(r.presenter || '')}</td><td>${r.minutes || ''}</td><td>${blank ? '' : esc(r.notes || '')}</td></tr>`).join('')}
      </tbody></table>
      <table class="sign"><tr><td>Foreman / safety lead signature:</td><td>Date:</td></tr></table>
      <table class="sign"><tr><td colspan="2"><strong>Attendance (print names & sign):</strong></td></tr>
      ${[1,2,3,4,5,6,7,8].map(() => '<tr><td>Name: _________________________</td><td>Company: _____________ Signature: _____________</td></tr>').join('')}
      </table></body></html>`;
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); w.focus(); w.print(); }
  }

  function printMinutes() {
    const body = el('tbMinutesBody').value || el('tbDiscussion').value;
    const html = `<!DOCTYPE html><html><head><title>Toolbox Minutes</title><style>body{font-family:Arial;padding:24px;white-space:pre-wrap;font-size:12px}</style></head><body><h2>Toolbox Meeting Minutes</h2><pre>${esc(body)}</pre></body></html>`;
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); w.focus(); w.print(); }
  }

  function startDictation() {
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    if (!SR) { alert('Dictation requires Chrome/Edge over HTTPS.'); return; }
    if (state.listening) return stopDictation();
    state.recognition = new SR();
    state.recognition.continuous = true;
    state.recognition.interimResults = true;
    state.recognition.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) appendTranscript(t, true);
        else interim += t;
      }
      if (el('tbLivePreview') && interim) el('tbLivePreview').textContent = interim;
    };
    state.recognition.start();
    state.listening = true;
    el('tbDictateLabel').textContent = 'Stop dictating';
  }

  function stopDictation() {
    if (state.recognition) { try { state.recognition.stop(); } catch (_) {} state.recognition = null; }
    state.listening = false;
    if (el('tbDictateLabel')) el('tbDictateLabel').textContent = 'Dictate';
  }

  async function startRecording() {
    if (state.recording) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.audioStream = stream;
    state.audioContext = new AudioContext();
    const source = state.audioContext.createMediaStreamSource(stream);
    state.analyser = state.audioContext.createAnalyser();
    source.connect(state.analyser);
    voice().setAnalyser(state.audioContext, state.analyser);
    voice().setRecordingStart(Date.now());
    state.recordingStartedAt = Date.now();
    state.recordChunks = [];
    state.mediaRecorder = new MediaRecorder(stream);
    state.mediaRecorder.ondataavailable = (e) => { if (e.data.size) state.recordChunks.push(e.data); };
    state.mediaRecorder.start(1000);
    state.recording = true;
    el('tbRecordLabel').textContent = 'Stop';
    state.recordTimer = setInterval(() => {
      const sec = Math.floor((Date.now() - state.recordingStartedAt) / 1000);
      if (el('tbRecordTimer')) el('tbRecordTimer').textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
    }, 500);
    if (!state.listening) startDictation();
  }

  function stopRecording() {
    if (state.mediaRecorder?.state === 'recording') state.mediaRecorder.stop();
    state.recording = false;
    if (el('tbRecordLabel')) el('tbRecordLabel').textContent = 'Record';
    clearInterval(state.recordTimer);
    stopDictation();
  }

  function stopAllCapture() {
    stopRecording();
    if (state.audioStream) { state.audioStream.getTracks().forEach((t) => t.stop()); state.audioStream = null; }
    if (state.audioContext) { try { state.audioContext.close(); } catch (_) {} state.audioContext = null; }
  }

  function reprocessAll() {
    const eng = voice();
    state.transcriptSegments = eng.reprocessSegments(state.transcriptSegments);
    eng.persistProfiles(projectId());
    renderTranscript();
    syncDiscussion();
  }

  function trainFromReview() {
    const eng = voice();
    const result = global.CasePMVoiceDiarization?.trainFromTranscriptReview(eng, state.transcriptSegments) || { trained: 0 };
    eng.persistProfiles(projectId());
    alert(result.trained ? `Trained ${result.trained} sample(s) from your corrections.` : 'Correct speaker tags on transcript lines first.');
  }

  function runVoiceTest() {
    const eng = voice();
    const result = global.CasePMVoiceDiarization?.runVoiceSelfTest(eng) || {};
    eng.persistProfiles(projectId());
    const pct = Math.round((result.accuracy || 0) * 100);
    const msg = `Voice test: ${result.correct}/${result.total} correct (${pct}%)`;
    if (el('tbVoiceTestResult')) el('tbVoiceTestResult').textContent = msg;
    alert(msg);
  }

  function bind() {
    el('tbSearch')?.addEventListener('input', renderList);
    el('tbPrintBlankAgenda')?.addEventListener('click', async () => { await loadCatalog(); printAgenda(true); });
    el('tbModalClose')?.addEventListener('click', () => { stopAllCapture(); el('tbModal').close(); });
    el('tbCancel')?.addEventListener('click', () => { stopAllCapture(); el('tbModal').close(); });
    el('tbSave')?.addEventListener('click', () => save().catch((e) => alert(e.message)));
    el('tbDelete')?.addEventListener('click', () => del().catch((e) => alert(e.message)));
    el('tbGenerate')?.addEventListener('click', () => generateMinutes().catch((e) => alert(e.message)));
    el('tbPrintAgenda')?.addEventListener('click', () => printAgenda(false));
    el('tbPrintMinutes')?.addEventListener('click', printMinutes);
    el('tbRecordBtn')?.addEventListener('click', () => state.recording ? stopRecording() : startRecording().catch((e) => alert(e.message)));
    el('tbDictateBtn')?.addEventListener('click', () => state.listening ? stopDictation() : startDictation());
    el('tbAutoDetect')?.addEventListener('change', (e) => voice().setAutoDetect(e.target.checked));
    el('tbRetrain')?.addEventListener('click', reprocessAll);
    el('tbTrainReview')?.addEventListener('click', trainFromReview);
    el('tbVoiceTest')?.addEventListener('click', runVoiceTest);
    ['Details', 'Agenda', 'Capture', 'Transcript', 'Minutes'].forEach((t) => {
      el(`tbTab${t}`)?.addEventListener('click', () => setTab(t.toLowerCase()));
    });
    global.addEventListener('casepm:project-changed', refresh);
  }

  function init() {
    if (!el('tbList')) return;
    bind();
    loadCatalog().then(refresh);
  }

  global.CasePMSafetyToolbox = { refresh, openCreate, openMeeting };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
