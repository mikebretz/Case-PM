/**
 * Case PM Safety — observations/incidents, personnel OSHA training, and OSHA library.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_SAFETY_CTX || {};
  const state = {
    tab: 'reports',
    reportsScope: 'project',
    toolboxScope: 'project',
    viewUserId: '',
    reports: [], rStats: {}, rTypes: [], rSeverities: [], rStatuses: [], rEditId: null,
    rPhotos: [], rExisting: [], rPendingDocIds: [],
    photoSeq: 0, armedPhoto: null, stream: null, facingMode: 'environment',
    listening: false, recognition: null,
    certs: [], cStats: {}, cTypes: [], cEditId: null,
    library: [],
    rFieldGroups: [], rDetails: {}, rTab: 'overview',
  };

  const R_TAB_PANELS = { overview: 'rPanelOverview', incident: 'rPanelIncident', injury: 'rPanelInjury', witness: 'rPanelWitness', investigation: 'rPanelInvestigation', osha: 'rPanelOsha', photos: 'rPanelPhotos' };
  const R_TAB_GROUP_MAP = { rFieldsIncident: ['when_where', 'employee'], rFieldsInjury: ['incident', 'medical'], rFieldsWitness: ['witnesses'], rFieldsInvestigation: ['investigation'], rFieldsOsha: ['osha_insurance'] };

  function projectId() { return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })(); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(id) { return document.getElementById(id); }
  function fmtDate(iso) { if (!iso) return ''; try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch (_) { return iso; } }
  async function api(url, opts) { const r = await fetch(url, opts); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Request failed'); return j; }
  function fillSelect(sel, opts, val, blank) { sel.innerHTML = (blank ? `<option value="">${blank}</option>` : '') + opts.map((o) => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join(''); }

  function projectName(pid) {
    const p = (ctx.projects || []).find((x) => x.id === pid);
    return p ? p.name : '';
  }

  function updateScopeChrome() {
    const tab = state.tab;
    el('safReportsScope')?.classList.toggle('hidden', tab !== 'reports');
    el('safToolboxScope')?.classList.toggle('hidden', tab !== 'toolbox');
    el('safCompanyBadge')?.classList.toggle('hidden', tab !== 'training' && tab !== 'library');
    const badge = el('safProjectBadge');
    if (!badge) return;
    if (tab === 'training' || tab === 'library') {
      badge.textContent = 'Company-wide';
      badge.classList.remove('hidden');
    } else if (tab === 'toolbox' && state.toolboxScope === 'company') {
      badge.textContent = 'Company weekly agendas';
      badge.classList.remove('hidden');
    } else if (tab === 'reports' && state.reportsScope === 'all') {
      badge.textContent = 'All projects';
      badge.classList.remove('hidden');
    } else if (tab === 'toolbox' && state.toolboxScope === 'all') {
      badge.textContent = 'All meetings';
      badge.classList.remove('hidden');
    } else {
      badge.textContent = ctx.projectName || 'Select a project';
      badge.classList.toggle('hidden', !ctx.projectName);
    }
  }

  const SAFETY_TAB_MODULES = {
    reports: 'safety_reports',
    training: 'safety_training',
    toolbox: 'safety_toolbox',
    library: 'safety_library',
  };

  function canAccessSafetyTab(tab) {
    const mod = SAFETY_TAB_MODULES[tab];
    if (!mod) return true;
    if (typeof canAccessModule === 'function') return canAccessModule(mod, 'view');
    const allowed = global.CASEPM_ALLOWED_MODULES || {};
    return allowed[mod] !== false;
  }

  function applySafetyTabPermissions() {
    document.querySelectorAll('.saf-tab').forEach((t) => {
      const tab = t.getAttribute('data-tab');
      if (tab && SAFETY_TAB_MODULES[tab]) {
        t.classList.toggle('hidden', !canAccessSafetyTab(tab));
      }
    });
    if (!canAccessSafetyTab(state.tab || 'reports')) {
      const first = Object.keys(SAFETY_TAB_MODULES).find(t => canAccessSafetyTab(t));
      if (first) setTab(first);
    }
  }

  // ---------------- Tabs ----------------
  function setTab(tab) {
    if (!canAccessSafetyTab(tab)) {
      const first = Object.keys(SAFETY_TAB_MODULES).find(t => canAccessSafetyTab(t));
      if (!first) return;
      tab = first;
    }
    state.tab = tab;
    document.querySelectorAll('.saf-tab').forEach((t) => t.classList.toggle('active', t.getAttribute('data-tab') === tab));
    el('safTabReports').classList.toggle('hidden', tab !== 'reports');
    el('safTabTraining').classList.toggle('hidden', tab !== 'training');
    el('safTabToolbox').classList.toggle('hidden', tab !== 'toolbox');
    el('safTabLibrary').classList.toggle('hidden', tab !== 'library');
    const label = el('safBtnNewLabel');
    const newBtn = el('safBtnNew');
    if (newBtn) newBtn.style.display = (tab === 'library') ? 'none' : '';
    if (label) {
      if (tab === 'training') label.textContent = 'Add Certification';
      else if (tab === 'toolbox') label.textContent = (ctx.isAdmin && state.toolboxScope === 'company') ? 'New Weekly Agenda' : 'New Toolbox Meeting';
      else label.textContent = 'New Report';
    }
    updateScopeChrome();
    if (tab === 'library' && !state.library.length) loadLibrary();
    if (tab === 'training' && !state.certs.length) loadCerts();
    if (tab === 'training' && global.CasePMSafetyCalendar) global.CasePMSafetyCalendar.loadCalendar().catch(() => {});
    if (tab === 'toolbox' && global.CasePMSafetyToolbox) global.CasePMSafetyToolbox.refresh();
  }

  function setReportTab(tab) {
    state.rTab = tab;
    document.querySelectorAll('.r-subtab').forEach((b) => b.classList.toggle('active', b.getAttribute('data-r-tab') === tab));
    Object.entries(R_TAB_PANELS).forEach(([key, panelId]) => {
      const panel = el(panelId);
      if (panel) panel.classList.toggle('hidden', key !== tab);
    });
  }

  function fieldInputHtml(f, val) {
    const id = `rd_${f.key}`;
    const v = val == null ? '' : val;
    if (f.type === 'textarea') return `<div><label class="block text-xs text-zinc-400 mb-1">${esc(f.label)}</label><textarea id="${id}" data-rd="${f.key}" rows="2" class="saf-input resize-y text-sm">${esc(v)}</textarea></div>`;
    if (f.type === 'select') return `<div><label class="block text-xs text-zinc-400 mb-1">${esc(f.label)}</label><select id="${id}" data-rd="${f.key}" class="saf-input text-sm">${(f.options || []).map((o) => `<option ${o === v ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select></div>`;
    if (f.type === 'checkbox') return `<label class="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer"><input type="checkbox" id="${id}" data-rd="${f.key}" class="accent-emerald-500" ${v ? 'checked' : ''}> ${esc(f.label)}</label>`;
    const type = f.type === 'date' || f.type === 'time' || f.type === 'number' ? f.type : 'text';
    return `<div><label class="block text-xs text-zinc-400 mb-1">${esc(f.label)}</label><input type="${type}" id="${id}" data-rd="${f.key}" class="saf-input text-sm" value="${esc(v)}"></div>`;
  }

  function buildIncidentFields() {
    if (!state.rFieldGroups.length) return;
    Object.entries(R_TAB_GROUP_MAP).forEach(([hostId, groupKeys]) => {
      const host = el(hostId);
      if (!host) return;
      const groups = state.rFieldGroups.filter((g) => groupKeys.includes(g.key));
      host.innerHTML = groups.map((g) => `
        <div class="border border-zinc-800 rounded-md p-3">
          <div class="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">${esc(g.label)}</div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">${g.fields.map((f) => fieldInputHtml(f, state.rDetails[f.key])).join('')}</div>
        </div>`).join('');
    });
  }

  function collectDetails() {
    const details = { ...state.rDetails };
    document.querySelectorAll('[data-rd]').forEach((inp) => {
      const key = inp.getAttribute('data-rd');
      if (inp.type === 'checkbox') details[key] = inp.checked;
      else details[key] = inp.value;
    });
    return details;
  }

  function populateDetails(details) {
    state.rDetails = details || {};
    buildIncidentFields();
  }

  async function loadReports() {
    const scope = state.reportsScope || el('safReportsScope')?.value || 'project';
    const pid = scope === 'all' ? 'all' : projectId();
    const userId = state.viewUserId || el('safUserFilter')?.value || '';
    el('safStatusText').textContent = 'Loading…';
    try {
      let url = `/api/safety/reports${pid ? `?project_id=${pid}` : ''}`;
      if (userId) url += `${url.includes('?') ? '&' : '?'}reported_by_id=${encodeURIComponent(userId)}`;
      const j = await api(url);
      state.reports = j.reports || []; state.rStats = j.stats || {};
      state.rTypes = j.types || []; state.rSeverities = j.severities || []; state.rStatuses = j.statuses || [];
      state.rFieldGroups = j.incident_field_groups || [];
      buildIncidentFields();
      if (el('rTypeFilter').options.length <= 1) state.rTypes.forEach((t) => el('rTypeFilter').add(new Option(t, t)));
      if (el('rStatusFilter').options.length <= 1) state.rStatuses.forEach((t) => el('rStatusFilter').add(new Option(t, t)));
      const pf = el('rProjectFilter');
      if (pf && pf.options.length <= 1) (ctx.projects || []).forEach((p) => pf.add(new Option(p.name, String(p.id))));
      updateScopeChrome();
      renderReportStats(); renderReports();
      el('safUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      el('safStatusText').textContent = `${state.reports.length} report(s)`;
    } catch (e) { el('safStatusText').textContent = 'Error: ' + e.message; }
  }
  function renderReportStats() {
    const s = state.rStats;
    el('rstatDays').textContent = s.days_without_incident == null ? '—' : s.days_without_incident;
    el('rstatIncidents').textContent = s.incidents_ytd ?? 0;
    el('rstatNear').textContent = s.near_misses ?? 0;
    el('rstatObs').textContent = s.observations ?? 0;
    el('rstatOpen').textContent = s.open ?? 0;
    el('rstatTotal').textContent = s.total ?? 0;
  }
  function sevChip(s) { const m = { Low: 'bg-zinc-700 text-zinc-300', Medium: 'bg-amber-500/15 text-amber-400', High: 'bg-orange-500/15 text-orange-400', Critical: 'bg-red-500/15 text-red-400' }; return `<span class="saf-chip ${m[s] || 'bg-zinc-700 text-zinc-300'}">${esc(s)}</span>`; }
  function rStatusChip(s) { const open = s !== 'Closed'; return `<span class="saf-chip ${open ? 'bg-sky-500/15 text-sky-400' : 'bg-emerald-500/15 text-emerald-400'}">${esc(s)}</span>`; }
  function typeIcon(t) { const m = { 'Incident': 'fa-triangle-exclamation text-red-400', 'Injury': 'fa-kit-medical text-red-400', 'Near Miss': 'fa-circle-exclamation text-amber-400', 'Observation': 'fa-eye text-sky-400', 'Toolbox Talk': 'fa-comments text-emerald-400', 'Inspection': 'fa-clipboard-check text-teal-300', 'Violation': 'fa-ban text-red-400', 'Property Damage': 'fa-house-crack text-orange-400' }; return m[t] || 'fa-shield-halved text-zinc-400'; }
  function renderReports() {
    const term = (el('rSearch').value || '').toLowerCase();
    const tf = el('rTypeFilter').value, sf = el('rStatusFilter').value;
    const pj = el('rProjectFilter')?.value || '';
    const rows = state.reports.filter((r) => {
      if (tf && r.type !== tf) return false;
      if (sf && r.status !== sf) return false;
      if (pj && String(r.project_id) !== pj) return false;
      if (term && !`${r.number} ${r.description} ${r.location || ''} ${r.assigned_to || ''} ${projectName(r.project_id)}`.toLowerCase().includes(term)) return false;
      return true;
    });
    const host = el('rList');
    if (!rows.length) { host.innerHTML = `<div class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-shield-heart text-4xl mb-3 block text-zinc-600"></i>No safety reports yet.</div>`; return; }
    const showProject = state.reportsScope === 'all';
    host.innerHTML = rows.map((r) => `
      <div class="saf-row" data-open="${r.id}">
        <i class="fa-solid ${typeIcon(r.type)} text-lg w-6 text-center"></i>
        <div class="min-w-0 flex-1">
          <div class="text-sm truncate">${esc(r.description)}</div>
          <div class="saf-meta">
            <span class="font-mono">${esc(r.number || '')}</span>
            <span>${esc(r.type || '')}</span>
            ${showProject && r.project_id ? `<span><i class="fa-solid fa-folder"></i> ${esc(projectName(r.project_id))}</span>` : ''}
            ${r.location ? `<span><i class="fa-solid fa-location-dot"></i> ${esc(r.location)}</span>` : ''}
            ${r.assigned_to ? `<span><i class="fa-solid fa-user"></i> ${esc(r.assigned_to)}</span>` : ''}
            ${r.report_date ? `<span><i class="fa-solid fa-calendar"></i> ${fmtDate(r.report_date)}</span>` : ''}
            ${r.photo_count ? `<span><i class="fa-solid fa-image"></i> ${r.photo_count}</span>` : ''}
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">${sevChip(r.severity)}${rStatusChip(r.status)}</div>
      </div>`).join('');
    host.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openReport(parseInt(n.getAttribute('data-open'), 10))));
  }

  function resetReportModal() {
    state.rEditId = null; state.rPhotos = []; state.rExisting = []; state.rPendingDocIds = [];
    state.photoSeq = 0; state.armedPhoto = null; state.rDetails = {};
    el('rModalTitle').textContent = 'New Safety Report';
    fillSelect(el('rType'), state.rTypes, 'Observation');
    fillSelect(el('rSeverity'), state.rSeverities, 'Medium');
    fillSelect(el('rStatus'), state.rStatuses, 'Open');
    ['rDesc', 'rLocation', 'rAssigned', 'rDue', 'rImmediate', 'rRoot', 'rCorrective'].forEach((id) => { el(id).value = ''; });
    el('rDelete').classList.add('hidden');
    setReportTab('overview');
    buildIncidentFields();
    renderRPhotos();
  }

  function autoPhotoName() {
    state.photoSeq += 1;
    const rtype = el('rType')?.value || 'Safety';
    return `${rtype} photo ${state.photoSeq}`;
  }

  async function openCamera() {
    el('rCamError').classList.add('hidden');
    el('rCameraModal').showModal();
    await startStream();
    renderCamThumbs();
  }

  async function startStream() {
    stopStream();
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: state.facingMode }, audio: false });
      const v = el('rVideo');
      v.srcObject = state.stream;
      v.classList.remove('hidden');
      el('rCamError').classList.add('hidden');
    } catch (e) {
      el('rVideo').classList.add('hidden');
      const err = el('rCamError');
      if (!window.isSecureContext) err.innerHTML = 'Camera needs HTTPS (or localhost). Use <b>Browse</b> or <b>Browse Documents</b>.';
      else if (e && e.name === 'NotAllowedError') err.innerHTML = 'Camera permission denied. Use <b>Browse</b> or <b>Browse Documents</b>.';
      else err.innerHTML = 'Camera unavailable. Use <b>Browse</b> or <b>Browse Documents</b>.';
      err.classList.remove('hidden');
    }
  }

  function stopStream() {
    if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
  }

  function captureFrame() {
    const v = el('rVideo');
    if (!v || !v.videoWidth) return null;
    const canvas = el('rSnapCanvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d').drawImage(v, 0, 0);
    return canvas;
  }

  function onCamShoot() {
    if (state.armedPhoto) { commitArmed(''); return; }
    const canvas = captureFrame();
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      state.armedPhoto = { blob, url: URL.createObjectURL(blob) };
      el('rCamShootLabel').textContent = 'Save';
      el('rCamShoot').classList.add('armed');
      el('rCamHint').innerHTML = 'Captured! Tap <b>Name (talk)</b> to name &amp; save, or <b>Save</b> for auto name.';
      renderCamThumbs();
    }, 'image/jpeg', 0.9);
  }

  function commitArmed(name) {
    if (!state.armedPhoto) return;
    const finalName = (name || '').trim() || autoPhotoName();
    state.rPhotos.push({ id: Date.now() + Math.random(), blob: state.armedPhoto.blob, url: state.armedPhoto.url, name: finalName });
    state.armedPhoto = null;
    stopListening();
    el('rCamShootLabel').textContent = 'Capture';
    el('rCamShoot').classList.remove('armed');
    el('rCamNameInput').classList.add('hidden');
    el('rCamNameInput').value = '';
    el('rCamNameLabel').textContent = 'Name (talk)';
    el('rCamHint').innerHTML = 'Tap <b>Capture</b> to snap. Then tap <b>Name (talk)</b> to name &amp; save, or <b>Capture</b> again for auto name.';
    renderCamThumbs();
    renderRPhotos();
  }

  function renderCamThumbs() {
    const wrap = el('rCamThumbs');
    if (!wrap) return;
    let html = '';
    if (state.armedPhoto) html += `<div class="saf-photo ring-2 ring-blue-500"><img src="${state.armedPhoto.url}"><div class="saf-photo-name">Unsaved</div></div>`;
    state.rPhotos.slice(-7).forEach((p) => { html += `<div class="saf-photo"><img src="${p.url}"><div class="saf-photo-name">${esc(p.name)}</div></div>`; });
    wrap.innerHTML = html;
  }

  function onCamName() {
    if (!state.armedPhoto) { el('rCamHint').innerHTML = 'Capture a photo first, then name it.'; return; }
    if (!state.listening) startListening();
    else commitArmed(el('rCamNameInput').value);
  }

  function startListening() {
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    const input = el('rCamNameInput');
    const hint = el('rCamHint');
    input.classList.remove('hidden');
    input.focus();
    el('rCamNameLabel').textContent = 'Stop & Save';
    el('rCamName').classList.add('listening');
    state.listening = true;
    if (!window.isSecureContext) {
      hint.innerHTML = '<span class="text-amber-400">Voice needs HTTPS. Type the name, then tap Stop &amp; Save.</span>';
      return;
    }
    if (!SR) {
      hint.innerHTML = '<span class="text-amber-400">Voice not supported — type the name, then tap Stop &amp; Save.</span>';
      return;
    }
    try {
      const rec = new SR();
      rec.lang = 'en-US';
      rec.interimResults = true;
      rec.continuous = true;
      rec.onstart = () => { hint.innerHTML = '<span class="text-emerald-400"><i class="fa-solid fa-microphone"></i> Listening… say the file name.</span>'; };
      rec.onresult = (event) => { let t = ''; for (let i = 0; i < event.results.length; i++) t += event.results[i][0].transcript; input.value = t.trim(); };
      rec.onerror = () => { hint.innerHTML = '<span class="text-amber-400">Voice error — type the name, then tap Stop & Save.</span>'; };
      rec.start();
      state.recognition = rec;
    } catch (_) {
      hint.innerHTML = '<span class="text-amber-400">Voice unavailable — type the name, then tap Stop &amp; Save.</span>';
    }
  }

  function stopListening() {
    state.listening = false;
    el('rCamName')?.classList.remove('listening');
    if (el('rCamNameLabel')) el('rCamNameLabel').textContent = 'Name (talk)';
    if (state.recognition) { try { state.recognition.stop(); } catch (_) {} state.recognition = null; }
  }

  function closeCamera() {
    if (state.armedPhoto) commitArmed('');
    stopListening();
    stopStream();
    el('rCameraModal').close();
    renderRPhotos();
  }

  function setupPhotoActions() {
    const host = el('rPhotoActions');
    if (!host || host.dataset.bound) return;
    host.dataset.bound = '1';
    host.innerHTML = `
      <button type="button" id="rOpenCamera" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 rounded-md text-xs font-semibold"><i class="fa-solid fa-camera mr-1"></i>Open Camera</button>
      <button type="button" id="rBrowseBtn" class="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-md text-xs"><i class="fa-solid fa-folder-open mr-1"></i>Browse</button>`;
    el('rOpenCamera').addEventListener('click', openCamera);
    el('rBrowseBtn').addEventListener('click', () => el('rBrowseInput').click());
    if (global.CasePMDocPicker) {
      global.CasePMDocPicker.addBrowseButton(host, {
        className: 'px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-md text-xs',
        title: 'Select photos from Documents',
        accept: 'image',
        getProjectId: projectId,
        getEntityId: () => state.rEditId,
        entityType: 'safety_report',
        projectRequiredMessage: 'Select a project first.',
        onPick: async (_docs, ids) => {
          if (state.rEditId) {
            const j = await api(`/api/safety/reports/${state.rEditId}`);
            state.rExisting = j.report?.photos || [];
            renderRPhotos();
          } else if (ids?.length) {
            state.rPendingDocIds.push(...ids);
            renderRPhotos();
            if (global.showToast) global.showToast(`${ids.length} document(s) will attach when you save`);
          }
        },
      });
    }
  }
  function openReportCreate() { resetReportModal(); el('rModal').showModal(); }
  async function openReport(id) {
    resetReportModal();
    try {
      const j = await api(`/api/safety/reports/${id}`); const r = j.report; state.rEditId = id;
      el('rModalTitle').textContent = r.number || 'Safety Report';
      fillSelect(el('rType'), state.rTypes, r.type);
      fillSelect(el('rSeverity'), state.rSeverities, r.severity);
      fillSelect(el('rStatus'), state.rStatuses, r.status);
      el('rDesc').value = r.description || ''; el('rLocation').value = r.location || ''; el('rAssigned').value = r.assigned_to || '';
      el('rDue').value = r.due_date || ''; el('rImmediate').value = r.immediate_actions || ''; el('rRoot').value = r.root_cause || ''; el('rCorrective').value = r.corrective_actions || '';
      populateDetails(r.details || {});
      state.rExisting = r.photos || []; renderRPhotos();
      el('rDelete').classList.remove('hidden');
      el('rModal').showModal();
    } catch (e) { alert(e.message); }
  }
  function renderRPhotos() {
    const grid = el('rPhotoGrid'); let html = '';
    state.rPhotos.forEach((p) => {
      html += `<div class="saf-photo"><img src="${p.url}" alt="${esc(p.name)}"><div class="saf-photo-name">${esc(p.name)}</div><div class="saf-photo-del" data-delp="${p.id}"><i class="fa-solid fa-times"></i></div></div>`;
    });
    state.rExisting.forEach((p) => {
      html += `<div class="saf-photo"><img src="${esc(p.url || '')}" alt="${esc(p.original_name || '')}"><div class="saf-photo-name">${esc(p.original_name || p.filename || '')}</div></div>`;
    });
    if (state.rPendingDocIds.length && !state.rEditId) {
      html += `<div class="col-span-full text-xs text-amber-400 py-1">${state.rPendingDocIds.length} document(s) from Documents will attach on save.</div>`;
    }
    grid.innerHTML = html || '<div class="text-xs text-zinc-500 col-span-full py-2 text-center">No photos — tap Open Camera.</div>';
    el('rPhotoCount').textContent = (state.rPhotos.length + state.rExisting.length) ? `(${state.rPhotos.length + state.rExisting.length})` : '';
    grid.querySelectorAll('[data-delp]').forEach((n) => n.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = n.getAttribute('data-delp');
      state.rPhotos = state.rPhotos.filter((p) => String(p.id) !== id);
      renderRPhotos();
    }));
  }
  async function saveReport() {
    const pid = projectId(); const desc = el('rDesc').value.trim();
    if (!pid || !desc) { alert('Description is required.'); return; }
    const payload = { project_id: pid, type: el('rType').value, severity: el('rSeverity').value, status: el('rStatus').value,
      description: desc, location: el('rLocation').value.trim(), assigned_to: el('rAssigned').value.trim(), due_date: el('rDue').value,
      immediate_actions: el('rImmediate').value.trim(), root_cause: el('rRoot').value.trim(), corrective_actions: el('rCorrective').value.trim(),
      details: collectDetails() };
    const btn = el('rSave'); btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const url = state.rEditId ? `/api/safety/reports/${state.rEditId}` : '/api/safety/reports';
      const j = await api(url, { method: state.rEditId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const rid = j.report.id;
      for (const p of state.rPhotos) {
        const fd = new FormData();
        fd.append('file', p.blob, `${p.name}.jpg`);
        fd.append('name', p.name);
        fd.append('kind', 'photo');
        await fetch(`/api/safety/reports/${rid}/attachments`, { method: 'POST', body: fd });
      }
      if (state.rPendingDocIds.length) {
        await global.CasePMDocPicker?.linkToEntity('safety_report', rid, state.rPendingDocIds);
        state.rPendingDocIds = [];
      }
      state.rPhotos = []; el('rModal').close(); await loadReports();
      if (global.showToast) global.showToast('Safety report saved');
    } catch (e) { alert(e.message); } finally { btn.disabled = false; btn.textContent = 'Save'; }
  }
  async function delReport() { if (!state.rEditId || !confirm('Delete this report?')) return; try { await api(`/api/safety/reports/${state.rEditId}`, { method: 'DELETE' }); el('rModal').close(); await loadReports(); } catch (e) { alert(e.message); } }

  // ---------------- Certifications ----------------
  async function loadCerts() {
    try {
      const j = await api('/api/safety/certifications?project_id=all');
      state.certs = j.certifications || []; state.cStats = j.stats || {}; state.cTypes = j.cert_types || [];
      if (el('cTypeFilter').options.length <= 1) state.cTypes.forEach((t) => el('cTypeFilter').add(new Option(t, t)));
      const dl = el('cCompanyList'); const set = new Set(); state.certs.forEach((c) => { if (c.company) set.add(c.company); });
      dl.innerHTML = [...set].map((c) => `<option value="${esc(c)}">`).join('');
      renderCertStats(); renderCerts();
    } catch (e) { el('safStatusText').textContent = 'Error: ' + e.message; }
  }
  function renderCertStats() {
    const s = state.cStats;
    el('cstatPeople').textContent = s.people ?? 0; el('cstatTotal').textContent = s.total ?? 0;
    el('cstatOsha').textContent = s.osha_certs ?? 0; el('cstatValid').textContent = s.valid ?? 0;
    el('cstatExpiring').textContent = s.expiring_soon ?? 0; el('cstatExpired').textContent = s.expired ?? 0;
  }
  function certStatusChip(s) { const m = { Valid: 'bg-emerald-500/15 text-emerald-400', 'Expiring Soon': 'bg-amber-500/15 text-amber-400', Expired: 'bg-red-500/15 text-red-400' }; return `<span class="saf-chip ${m[s] || 'bg-zinc-700 text-zinc-300'}">${esc(s)}</span>`; }
  function renderCerts() {
    const term = (el('cSearch').value || '').toLowerCase();
    const tf = el('cTypeFilter').value, sf = el('cStatusFilter').value;
    const rows = state.certs.filter((c) => {
      if (tf && c.cert_type !== tf) return false;
      if (sf && c.cert_status !== sf) return false;
      if (term && !`${c.person_name} ${c.company || ''} ${c.cert_type} ${c.trade || ''}`.toLowerCase().includes(term)) return false;
      return true;
    });
    const tb = el('cList');
    if (!rows.length) { tb.innerHTML = `<tr><td colspan="6" class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-id-card text-4xl mb-3 block text-zinc-600"></i>No certifications yet. Add OSHA 10/30, First Aid, CPR, etc.</td></tr>`; return; }
    tb.innerHTML = rows.map((c) => `
      <tr class="hover:bg-zinc-800/50 cursor-pointer" data-open="${c.id}">
        <td class="px-4 py-3 font-medium">${esc(c.person_name)}${c.trade ? `<span class="text-xs text-zinc-500"> · ${esc(c.trade)}</span>` : ''}</td>
        <td class="px-4 py-3 text-zinc-300 saf-hide-mobile">${esc(c.company || '—')}</td>
        <td class="px-4 py-3">${esc(c.cert_type)}${c.card_number ? `<span class="text-xs text-zinc-500"> · #${esc(c.card_number)}</span>` : ''}</td>
        <td class="px-4 py-3 text-zinc-400 saf-hide-mobile">${fmtDate(c.issued_date) || '—'}</td>
        <td class="px-4 py-3 ${c.cert_status === 'Expired' ? 'text-red-400' : c.cert_status === 'Expiring Soon' ? 'text-amber-400' : 'text-zinc-300'}">${fmtDate(c.expiration_date) || '—'}${c.days_left != null && c.days_left >= 0 && c.cert_status === 'Expiring Soon' ? ` (${c.days_left}d)` : ''}</td>
        <td class="px-4 py-3 text-center">${certStatusChip(c.cert_status)}</td>
      </tr>`).join('');
    tb.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openCert(parseInt(n.getAttribute('data-open'), 10))));
  }
  function resetCertModal() {
    state.cEditId = null; el('cModalTitle').textContent = 'New Certification';
    ['cPerson', 'cCompany', 'cTrade', 'cCard', 'cIssuer', 'cIssued', 'cExpiration', 'cNotes'].forEach((id) => { el(id).value = ''; });
    fillSelect(el('cType'), state.cTypes, 'OSHA 10');
    el('cDelete').classList.add('hidden');
  }
  function openCertCreate() { if (!state.cTypes.length) { loadCerts().then(() => { resetCertModal(); el('cModal').showModal(); }); return; } resetCertModal(); el('cModal').showModal(); }
  function openCert(id) {
    const c = state.certs.find((x) => x.id === id); if (!c) return;
    resetCertModal(); state.cEditId = id; el('cModalTitle').textContent = c.person_name;
    el('cPerson').value = c.person_name || ''; el('cCompany').value = c.company || ''; el('cTrade').value = c.trade || '';
    el('cCard').value = c.card_number || ''; el('cIssuer').value = c.issuer || ''; el('cIssued').value = c.issued_date || '';
    el('cExpiration').value = c.expiration_date || ''; el('cNotes').value = c.notes || '';
    fillSelect(el('cType'), state.cTypes, c.cert_type);
    el('cDelete').classList.remove('hidden');
    el('cModal').showModal();
  }
  async function saveCert() {
    const person = el('cPerson').value.trim(); const type = el('cType').value;
    if (!person) { alert('Person name is required.'); return; }
    const payload = { project_id: projectId(), person_name: person, company: el('cCompany').value.trim(), trade: el('cTrade').value.trim(),
      cert_type: type, card_number: el('cCard').value.trim(), issuer: el('cIssuer').value.trim(),
      issued_date: el('cIssued').value, expiration_date: el('cExpiration').value, notes: el('cNotes').value.trim() };
    const btn = el('cSave'); btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const url = state.cEditId ? `/api/safety/certifications/${state.cEditId}` : '/api/safety/certifications';
      await api(url, { method: state.cEditId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      el('cModal').close(); await loadCerts();
      if (global.showToast) global.showToast('Certification saved');
    } catch (e) { alert(e.message); } finally { btn.disabled = false; btn.textContent = 'Save'; }
  }
  async function delCert() { if (!state.cEditId || !confirm('Delete this certification?')) return; try { await api(`/api/safety/certifications/${state.cEditId}`, { method: 'DELETE' }); el('cModal').close(); await loadCerts(); } catch (e) { alert(e.message); } }

  // ---------------- OSHA Library ----------------
  async function loadLibrary() {
    try {
      const j = await api('/api/safety/osha-library');
      state.library = j.library || [];
      renderLibrary();
    } catch (e) { el('safLibrary').innerHTML = `<div class="text-red-400">${esc(e.message)}</div>`; }
  }
  function renderLibrary() {
    el('safLibrary').innerHTML = state.library.map((it) => {
      const viewUrl = it.local_url || it.pdf_url || it.topic_url;
      return `<div class="saf-card flex flex-col">
        <div class="flex items-start justify-between gap-2">
          <div class="font-medium text-sm">${esc(it.title)}</div>
          ${it.pub ? `<span class="saf-chip bg-zinc-800 text-zinc-400 font-mono">${esc(it.pub)}</span>` : ''}
        </div>
        <div class="text-xs text-zinc-500 mt-1 flex-1">${esc(it.description || '')}</div>
        <div class="text-[10px] text-zinc-500 mt-2"><span class="saf-chip bg-zinc-800 text-zinc-400">${esc(it.category || '')}</span>${it.bundled_file ? '<span class="saf-chip bg-emerald-500/15 text-emerald-400 ml-1">Bundled</span>' : ''}</div>
        <div class="flex gap-2 mt-3">
          <a href="${esc(viewUrl)}" target="_blank" class="flex-1 text-center px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-md text-xs"><i class="fa-solid fa-arrow-up-right-from-square mr-1"></i>View</a>
          <button type="button" data-save="${esc(it.key)}" class="flex-1 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 rounded-md text-xs font-medium"><i class="fa-solid fa-download mr-1"></i>Save</button>
        </div>
      </div>`;
    }).join('');
    el('safLibrary').querySelectorAll('[data-save]').forEach((n) => n.addEventListener('click', () => saveToDocuments([n.getAttribute('data-save')])));
  }
  async function saveToDocuments(keys) {
    const pid = projectId();
    if (!pid) { alert('Select a project first.'); return; }
    el('safStatusText').textContent = 'Saving to Documents…';
    try {
      const j = await api(`/api/safety/osha-library/save-to-documents?project_id=${pid}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ keys: keys || null }) });
      const msg = `Saved ${j.saved_count} to Documents › Safety › OSHA Reference${j.failed && j.failed.length ? ` (${j.failed.length} unavailable)` : ''}`;
      el('safStatusText').textContent = msg;
      if (global.showToast) global.showToast(msg);
    } catch (e) { el('safStatusText').textContent = 'Error: ' + e.message; alert(e.message); }
  }

  async function checkLibraryUpdates() {
    const banner = el('safUpdateBanner');
    const btn = el('safCheckUpdates');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i>Checking…'; }
    try {
      const j = await api('/api/safety/osha-library/check-updates');
      const n = j.summary?.update_available || 0;
      if (banner) {
        if (n) {
          const names = (j.items || []).filter((i) => i.status === 'update_available').map((i) => i.title).slice(0, 4);
          banner.classList.remove('hidden');
          banner.innerHTML = `<i class="fa-solid fa-circle-exclamation mr-1"></i><b>${n} update(s) available</b> on OSHA.gov${names.length ? `: ${names.map(esc).join(', ')}${n > 4 ? '…' : ''}` : ''}. Use <b>Save</b> on each card to pull the latest into Documents.`;
        } else {
          banner.classList.remove('hidden');
          banner.className = 'mb-3 text-xs bg-emerald-900/30 border border-emerald-700 text-emerald-200 rounded-md px-3 py-2';
          banner.innerHTML = '<i class="fa-solid fa-check mr-1"></i>Bundled OSHA PDFs match the latest official versions checked just now.';
        }
      }
      el('safStatusText').textContent = `OSHA library checked — ${n} update(s) available`;
    } catch (e) {
      if (banner) { banner.classList.remove('hidden'); banner.className = 'mb-3 text-xs bg-red-900/30 border border-red-700 text-red-200 rounded-md px-3 py-2'; banner.textContent = e.message; }
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-rotate mr-1"></i>Check for updates'; }
    }
  }

  // ---------------- Init ----------------
  function bind() {
    document.querySelectorAll('.saf-tab').forEach((t) => t.addEventListener('click', () => setTab(t.getAttribute('data-tab'))));
    const userFilter = el('safUserFilter');
    if (userFilter && ctx.canBrowseUserSafety && (ctx.personnel || []).length) {
      userFilter.classList.remove('hidden');
      ctx.personnel.forEach((p) => userFilter.add(new Option(p.name, String(p.id))));
      userFilter.addEventListener('change', (e) => {
        state.viewUserId = e.target.value || '';
        loadReports();
      });
    }
    el('safReportsScope')?.addEventListener('change', (e) => { state.reportsScope = e.target.value; loadReports(); });
    el('safToolboxScope')?.addEventListener('change', (e) => {
      state.toolboxScope = e.target.value;
      updateScopeChrome();
      if (global.CasePMSafetyToolbox) global.CasePMSafetyToolbox.setScope(e.target.value);
      setTab('toolbox');
    });
    el('safBtnRefresh')?.addEventListener('click', () => { loadReports(); if (state.tab === 'training') loadCerts(); });
    el('safBtnNew').addEventListener('click', () => {
      if (state.tab === 'training') openCertCreate();
      else if (state.tab === 'toolbox' && global.CasePMSafetyToolbox) global.CasePMSafetyToolbox.openCreate();
      else openReportCreate();
    });

    el('rModalClose').addEventListener('click', () => el('rModal').close());
    el('rCancel').addEventListener('click', () => el('rModal').close());
    el('rSave').addEventListener('click', saveReport);
    el('rDelete').addEventListener('click', delReport);
    document.querySelectorAll('.r-subtab').forEach((b) => b.addEventListener('click', () => setReportTab(b.getAttribute('data-r-tab'))));
    setupPhotoActions();
    el('rBrowseInput').addEventListener('change', (e) => {
      for (const f of e.target.files) {
        state.rPhotos.push({ id: Date.now() + Math.random(), blob: f, url: URL.createObjectURL(f), name: autoPhotoName() });
      }
      e.target.value = '';
      renderRPhotos();
    });
    el('rCamClose')?.addEventListener('click', closeCamera);
    el('rCamDone')?.addEventListener('click', closeCamera);
    el('rCamShoot')?.addEventListener('click', onCamShoot);
    el('rCamName')?.addEventListener('click', onCamName);
    el('rCamSwitch')?.addEventListener('click', () => { state.facingMode = state.facingMode === 'environment' ? 'user' : 'environment'; startStream(); });
    ['rSearch', 'rTypeFilter', 'rStatusFilter', 'rProjectFilter'].forEach((id) => { el(id)?.addEventListener('input', renderReports); el(id)?.addEventListener('change', renderReports); });

    el('cModalClose').addEventListener('click', () => el('cModal').close());
    el('cCancel').addEventListener('click', () => el('cModal').close());
    el('cSave').addEventListener('click', saveCert);
    el('cDelete').addEventListener('click', delCert);
    ['cSearch', 'cTypeFilter', 'cStatusFilter'].forEach((id) => { el(id).addEventListener('input', renderCerts); el(id).addEventListener('change', renderCerts); });

    el('safImportAll').addEventListener('click', () => saveToDocuments(null));
    el('safCheckUpdates')?.addEventListener('click', () => checkLibraryUpdates().catch((e) => alert(e.message)));

    global.addEventListener('casepm:project-changed', () => { loadReports(); state.certs = []; state.library = []; updateScopeChrome(); });
    global.onCasePmProjectChanged = (pid, name) => { ctx.projectId = pid; ctx.projectName = name || projectName(pid); loadReports(); state.certs = []; state.library = []; updateScopeChrome(); };
  }
  function init() {
    if (el('safReportsScope')) state.reportsScope = el('safReportsScope').value;
    if (el('safToolboxScope')) state.toolboxScope = el('safToolboxScope').value;
    bind();
    applySafetyTabPermissions();
    loadReports();
    updateScopeChrome();
  }
  global.CasePMSafety = { refresh: loadReports, refreshCerts: loadCerts, getCertTypes: () => state.cTypes };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
