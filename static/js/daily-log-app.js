/**
 * Case PM Daily Log — full field report.
 * Sections: manpower (company dropdown), equipment, deliveries, materials, delays,
 * visitors, phone calls, inspections, safety, accidents, quantities, dumpsters,
 * scheduled work. Photos are captured in-app via the device camera and uploaded
 * straight to the server — never written to the device's storage.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_DAILY_LOG_CTX || {};

  const DELAY_TYPES = ['Weather', 'Labor Shortage', 'Material', 'Equipment', 'Owner', 'Design/RFI', 'Inspection', 'Utility', 'Other'];
  const SAFETY_TYPES = ['Observation', 'Near Miss', 'Incident', 'Toolbox Talk', 'Violation', 'JHA/JSA', 'PPE Check'];
  const INSPECTION_RESULTS = ['Pass', 'Fail', 'Partial', 'Pending', 'N/A'];
  const SCHED_STATUS = ['On Track', 'Ahead', 'Behind', 'Complete', 'Not Started'];

  // Section definitions — each renders a collapsible block with dynamic rows.
  const SECTIONS = [
    { key: 'manpower', label: 'Manpower', icon: 'fa-users', color: 'text-emerald-400', always: true, fields: [
      { k: 'company', ph: 'Company / sub', type: 'company', w: 'flex-1' },
      { k: 'personnel_count', ph: 'Workers', type: 'number', w: 'w-20' },
      { k: 'hours', ph: 'Hrs', type: 'number', step: '0.5', w: 'w-20' },
      { k: 'work_performed', ph: 'Trade / work', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'equipment', label: 'Equipment', icon: 'fa-truck-pickup', color: 'text-zinc-300', fields: [
      { k: 'equipment_name', ph: 'Equipment', type: 'text', w: 'flex-1' },
      { k: 'quantity', ph: 'Qty', type: 'number', w: 'w-20' },
      { k: 'condition', ph: 'Condition / hours / notes', type: 'text', w: 'flex-1' },
    ] },
    { key: 'deliveries', label: 'Deliveries', icon: 'fa-box', color: 'text-amber-400', fields: [
      { k: 'item', ph: 'Item received', type: 'text', w: 'flex-1' },
      { k: 'supplier', ph: 'Supplier', type: 'text', w: 'flex-1', mHide: true },
      { k: 'quantity', ph: 'Qty', type: 'text', w: 'w-24' },
      { k: 'notes', ph: 'Notes', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'materials', label: 'Materials Installed / Stored', icon: 'fa-cubes-stacked', color: 'text-orange-300', fields: [
      { k: 'material', ph: 'Material', type: 'text', w: 'flex-1' },
      { k: 'supplier', ph: 'Supplier', type: 'text', w: 'flex-1', mHide: true },
      { k: 'quantity', ph: 'Qty', type: 'text', w: 'w-20' },
      { k: 'unit', ph: 'Unit', type: 'text', w: 'w-20' },
      { k: 'location', ph: 'Location', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'delays', label: 'Delays', icon: 'fa-clock', color: 'text-red-400', fields: [
      { k: 'type', ph: 'Type', type: 'select', options: DELAY_TYPES, w: 'w-36' },
      { k: 'description', ph: 'What was delayed & why', type: 'text', w: 'flex-1' },
      { k: 'hours_lost', ph: 'Hrs lost', type: 'number', step: '0.5', w: 'w-24' },
    ] },
    { key: 'visitors', label: 'Visitors', icon: 'fa-user-tie', color: 'text-violet-400', fields: [
      { k: 'name', ph: 'Name', type: 'text', w: 'flex-1' },
      { k: 'company', ph: 'Company', type: 'text', w: 'flex-1', mHide: true },
      { k: 'purpose', ph: 'Purpose', type: 'text', w: 'flex-1' },
      { k: 'time', ph: 'Time', type: 'text', w: 'w-24', mHide: true },
    ] },
    { key: 'phone_calls', label: 'Phone Calls / Communications', icon: 'fa-phone', color: 'text-sky-300', fields: [
      { k: 'contact', ph: 'Contact', type: 'text', w: 'flex-1' },
      { k: 'company', ph: 'Company', type: 'text', w: 'flex-1', mHide: true },
      { k: 'subject', ph: 'Subject', type: 'text', w: 'flex-1' },
      { k: 'notes', ph: 'Notes', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'inspections', label: 'Inspections', icon: 'fa-clipboard-check', color: 'text-teal-300', fields: [
      { k: 'type', ph: 'Inspection type', type: 'text', w: 'flex-1' },
      { k: 'agency', ph: 'Agency', type: 'text', w: 'flex-1', mHide: true },
      { k: 'inspector', ph: 'Inspector', type: 'text', w: 'flex-1', mHide: true },
      { k: 'result', ph: 'Result', type: 'select', options: INSPECTION_RESULTS, w: 'w-28' },
      { k: 'notes', ph: 'Notes', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'safety', label: 'Safety', icon: 'fa-hard-hat', color: 'text-yellow-400', fields: [
      { k: 'type', ph: 'Type', type: 'select', options: SAFETY_TYPES, w: 'w-36' },
      { k: 'description', ph: 'Description', type: 'text', w: 'flex-1' },
      { k: 'action', ph: 'Corrective action', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'accidents', label: 'Accidents / Incidents', icon: 'fa-triangle-exclamation', color: 'text-red-300', fields: [
      { k: 'person', ph: 'Person', type: 'text', w: 'flex-1' },
      { k: 'company', ph: 'Company', type: 'text', w: 'flex-1', mHide: true },
      { k: 'description', ph: 'Description', type: 'text', w: 'flex-1' },
      { k: 'treatment', ph: 'Treatment', type: 'text', w: 'flex-1', mHide: true },
    ] },
    { key: 'quantities', label: 'Quantities / Production', icon: 'fa-ruler-combined', color: 'text-lime-300', fields: [
      { k: 'description', ph: 'Work item', type: 'text', w: 'flex-1' },
      { k: 'quantity', ph: 'Qty', type: 'text', w: 'w-20' },
      { k: 'unit', ph: 'Unit', type: 'text', w: 'w-20' },
      { k: 'cost_code', ph: 'Cost code', type: 'text', w: 'w-28', mHide: true },
    ] },
    { key: 'dumpsters', label: 'Dumpster / Waste', icon: 'fa-dumpster', color: 'text-zinc-400', fields: [
      { k: 'type', ph: 'Waste type', type: 'text', w: 'flex-1' },
      { k: 'size', ph: 'Size', type: 'text', w: 'w-24' },
      { k: 'hauler', ph: 'Hauler', type: 'text', w: 'flex-1', mHide: true },
      { k: 'hauls', ph: 'Hauls', type: 'number', w: 'w-20' },
    ] },
    { key: 'scheduled_work', label: 'Scheduled Work / Look-Ahead', icon: 'fa-calendar-week', color: 'text-indigo-300', fields: [
      { k: 'activity', ph: 'Activity', type: 'text', w: 'flex-1' },
      { k: 'status', ph: 'Status', type: 'select', options: SCHED_STATUS, w: 'w-32' },
      { k: 'notes', ph: 'Notes', type: 'text', w: 'flex-1', mHide: true },
    ] },
  ];

  const DETAIL_KEYS = SECTIONS.filter((s) => !s.always).map((s) => s.key);

  const state = {
    logs: [], stats: {}, editingId: null,
    viewingLog: null,
    pendingPhotos: [],   // {id, blob, url, name}
    existingPhotos: [],
    armedPhoto: null,    // {blob, url}
    photoSeq: 0,
    companies: [],
    detailed: true,
    mobile: false,
    // camera
    stream: null, facingMode: 'environment', listening: false, recognition: null,
  };

  function isMobile() {
    return (('ontouchstart' in window) && window.matchMedia('(max-width: 768px)').matches)
      || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  }
  function projectId() {
    return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })();
  }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function fmtDate(iso) { if (!iso) return '—'; try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch (_) { return iso; } }
  function el(id) { return document.getElementById(id); }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  // ---------------- List ----------------
  async function loadList() {
    const pid = projectId();
    const q = pid ? `?project_id=${pid}` : '';
    el('dlogStatusText').textContent = 'Loading…';
    try {
      const res = await fetch(`/api/daily-logs${q}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed to load');
      state.logs = json.logs || [];
      state.stats = json.stats || {};
      renderStats();
      renderList();
      el('dlogStatusText').textContent = `${state.logs.length} report(s)`;
      el('dlogUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (e) {
      el('dlogStatusText').textContent = `Error: ${e.message}`;
    }
  }

  async function loadCompanies() {
    const pid = projectId();
    try {
      const res = await fetch(`/api/daily-logs/companies${pid ? `?project_id=${pid}` : ''}`);
      const json = await res.json();
      state.companies = json.companies || [];
      const dl = el('dlogCompanyList');
      if (dl) dl.innerHTML = state.companies.map((c) => `<option value="${esc(c.name)}">${esc(c.sources.join(', '))}</option>`).join('');
    } catch (_) { /* ignore */ }
  }

  function renderStats() {
    const s = state.stats;
    el('statTotal').textContent = s.total_reports ?? 0;
    el('statWeek').textContent = s.this_week ?? 0;
    el('statHours').textContent = s.total_man_hours ?? 0;
    el('statCrew').textContent = s.avg_crew_size ?? 0;
    el('statPhotos').textContent = s.photos_uploaded ?? 0;
    el('statDelays').textContent = s.open_delays ?? 0;
    const badge = el('dlogProjectBadge');
    if (badge) badge.textContent = ctx.projectName || 'All projects';
  }

  function filteredLogs() {
    const term = (el('dlogSearch').value || '').toLowerCase();
    const dateF = el('dlogDateFilter').value;
    const statusF = el('dlogStatusFilter').value;
    return state.logs.filter((l) => {
      if (dateF && l.date !== dateF) return false;
      if (statusF && (l.status || 'Submitted') !== statusF) return false;
      if (term) { const hay = `${l.date} ${l.weather || ''} ${l.work_performed || ''}`.toLowerCase(); if (!hay.includes(term)) return false; }
      return true;
    });
  }

  function statusBadge(status) {
    const st = status || 'Submitted';
    const cls = st === 'Reviewed' ? 'bg-blue-500/15 text-blue-400' : st === 'Draft' ? 'bg-zinc-700 text-zinc-300' : 'bg-emerald-500/15 text-emerald-400';
    return `<span class="dlog-chip ${cls}">${esc(st)}</span>`;
  }

  function renderList() {
    const tbody = el('dlogTableBody');
    const rows = filteredLogs();
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="px-6 py-12 text-center text-zinc-500">
        <i class="fa-solid fa-clipboard-list text-4xl mb-3 block text-zinc-600"></i>
        No daily logs yet. Tap <b>New Daily Log</b> to add today's report.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((l) => `
      <tr class="hover:bg-zinc-800/50 cursor-pointer" data-open="${l.id}">
        <td class="px-4 py-3 font-medium whitespace-nowrap">${fmtDate(l.date)}</td>
        <td class="px-4 py-3 text-zinc-300 dlog-hide-mobile">${esc(l.weather || '—')}</td>
        <td class="px-4 py-3 text-center text-zinc-300">${l.total_workers || '—'}</td>
        <td class="px-4 py-3 text-center text-zinc-300 dlog-hide-mobile">${l.total_hours || '—'}</td>
        <td class="px-4 py-3 text-zinc-300 max-w-[360px] truncate">${esc(l.work_performed || '—')}</td>
        <td class="px-4 py-3 text-center"><span class="dlog-chip bg-zinc-800 text-zinc-300">${l.photo_count || 0}</span></td>
        <td class="px-4 py-3 text-center dlog-hide-mobile">${statusBadge(l.status)}</td>
        <td class="px-4 py-3 text-center"><button class="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md" data-open="${l.id}">View</button></td>
      </tr>`).join('');
    tbody.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', (e) => { e.stopPropagation(); openDetail(parseInt(n.getAttribute('data-open'), 10)); }));
  }

  // ---------------- Sections (dynamic) ----------------
  // Flex-basis / min-width per field-width hint so cells wrap instead of collapsing.
  const CELL_STYLE = {
    'flex-1': 'flex:1 1 170px; min-width:150px;',
    'w-20': 'flex:0 1 84px; min-width:70px;',
    'w-24': 'flex:0 1 96px; min-width:80px;',
    'w-28': 'flex:0 1 112px; min-width:96px;',
    'w-32': 'flex:0 1 130px; min-width:110px;',
    'w-36': 'flex:0 1 150px; min-width:130px;',
  };

  function cellStyle(field) {
    if (field.type === 'company') return 'flex:2 1 220px; min-width:190px;';
    return CELL_STYLE[field.w] || 'flex:1 1 150px; min-width:130px;';
  }

  function buildSectionsHost() {
    const host = el('dlogSectionsHost');
    let dl = el('dlogCompanyList');
    if (!dl) { dl = document.createElement('datalist'); dl.id = 'dlogCompanyList'; document.body.appendChild(dl); }
    host.innerHTML = SECTIONS.map((s) => `
      <div class="dlog-section ${s.always ? '' : 'dlog-detailed'}">
        <div class="dlog-section-head" data-section-toggle="${s.key}">
          <span class="font-medium text-sm"><i class="fa-solid ${s.icon} ${s.color} mr-2"></i>${esc(s.label)}<span id="dlogCount_${s.key}" class="dlog-count-pill">0</span></span>
          <i class="fa-solid fa-chevron-down text-xs text-zinc-500"></i>
        </div>
        <div class="dlog-section-body ${s.always ? '' : 'hidden'}" data-section-body="${s.key}">
          <div id="dlogRows_${s.key}"></div>
          <button type="button" class="text-xs text-emerald-400 mt-2" data-add-row="${s.key}"><i class="fa-solid fa-plus mr-1"></i>Add ${esc(s.label.split(' ')[0].toLowerCase())}</button>
        </div>
      </div>`).join('');
    host.querySelectorAll('[data-section-toggle]').forEach((n) => n.addEventListener('click', () => {
      const body = host.querySelector(`[data-section-body="${n.getAttribute('data-section-toggle')}"]`);
      if (body) body.classList.toggle('hidden');
    }));
    host.querySelectorAll('[data-add-row]').forEach((n) => n.addEventListener('click', () => addRow(n.getAttribute('data-add-row'))));
  }

  function fieldHtml(field, val) {
    const cls = `dlog-cell${field.mHide ? ' dlog-hide-mobile' : ''}`;
    const style = cellStyle(field);
    if (field.type === 'select') {
      return `<select class="${cls}" style="${style}" data-field="${field.k}">${field.options.map((o) => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
    }
    if (field.type === 'company') {
      return `<input type="text" list="dlogCompanyList" class="${cls}" style="${style}" data-field="${field.k}" placeholder="${esc(field.ph)}" value="${esc(val || '')}">`;
    }
    const step = field.step ? ` step="${field.step}"` : '';
    const min = field.type === 'number' ? ' min="0"' : '';
    return `<input type="${field.type}" class="${cls}" style="${style}" data-field="${field.k}" placeholder="${esc(field.ph)}" value="${esc(val || '')}"${step}${min}>`;
  }

  function addRow(key, data) {
    const section = SECTIONS.find((s) => s.key === key);
    const container = el(`dlogRows_${key}`);
    if (!section || !container) return;
    const row = document.createElement('div');
    row.className = 'dlog-row';
    row.setAttribute('data-row', '');
    row.innerHTML = section.fields.map((f) => fieldHtml(f, (data || {})[f.k])).join('')
      + `<button type="button" class="text-red-400 hover:text-red-300 px-2 shrink-0" style="flex:0 0 24px" data-remove-row title="Remove"><i class="fa-solid fa-trash text-xs"></i></button>`;
    row.querySelector('[data-remove-row]').addEventListener('click', () => { row.remove(); updateCounts(); });
    container.appendChild(row);
    updateCounts();
  }

  function collectRows(key) {
    const container = el(`dlogRows_${key}`);
    if (!container) return [];
    const out = [];
    container.querySelectorAll('[data-row]').forEach((row) => {
      const obj = {};
      row.querySelectorAll('[data-field]').forEach((inp) => { obj[inp.getAttribute('data-field')] = (inp.value || '').trim(); });
      out.push(obj);
    });
    return out;
  }

  function updateCounts() {
    SECTIONS.forEach((s) => {
      const container = el(`dlogRows_${s.key}`);
      const counter = el(`dlogCount_${s.key}`);
      if (container && counter) counter.textContent = container.querySelectorAll('[data-row]').length;
    });
    el('dlogPhotoCount').textContent = state.pendingPhotos.length + state.existingPhotos.length;
  }

  // ---------------- Photos / camera ----------------
  function autoPhotoName() {
    state.photoSeq += 1;
    const d = el('dlogDate').value || new Date().toISOString().slice(0, 10);
    return `Photo ${state.photoSeq} · ${d}`;
  }

  async function openCamera() {
    el('dlogCamError').classList.add('hidden');
    el('dlogCameraModal').showModal();
    await startStream();
    renderCamThumbs();
  }

  async function startStream() {
    stopStream();
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: state.facingMode }, audio: false,
      });
      const v = el('dlogVideo');
      v.srcObject = state.stream;
      v.classList.remove('hidden');
      el('dlogCamError').classList.add('hidden');
    } catch (e) {
      el('dlogVideo').classList.add('hidden');
      const err = el('dlogCamError');
      if (!window.isSecureContext) {
        err.innerHTML = 'The in-app camera needs a secure (HTTPS) connection. Open Case PM over HTTPS (or localhost), or use <b>Browse</b> to add photos.';
      } else if (e && e.name === 'NotAllowedError') {
        err.innerHTML = 'Camera permission was denied. Allow camera access in your browser, or use <b>Browse</b> to add photos.';
      } else {
        err.innerHTML = 'Camera unavailable on this device. Use <b>Browse</b> to add photos instead.';
      }
      err.classList.remove('hidden');
    }
  }

  function stopStream() {
    if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; }
  }

  function captureFrame() {
    const v = el('dlogVideo');
    if (!v || !v.videoWidth) return null;
    const canvas = el('dlogSnapCanvas');
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
      const url = URL.createObjectURL(blob);
      state.armedPhoto = { blob, url };
      el('dlogCamShootLabel').textContent = 'Save';
      el('dlogCamShoot').classList.add('armed');
      el('dlogCamHint').innerHTML = 'Captured! Tap <b>Name (talk)</b> to name &amp; save, or <b>Save</b> for auto name.';
      renderCamThumbs();
    }, 'image/jpeg', 0.9);
  }

  function commitArmed(name) {
    if (!state.armedPhoto) return;
    const finalName = (name || '').trim() || autoPhotoName();
    state.pendingPhotos.push({ id: Date.now() + Math.random(), blob: state.armedPhoto.blob, url: state.armedPhoto.url, name: finalName });
    state.armedPhoto = null;
    stopListening();
    el('dlogCamShootLabel').textContent = 'Capture';
    el('dlogCamShoot').classList.remove('armed');
    el('dlogCamNameInput').classList.add('hidden');
    el('dlogCamNameInput').value = '';
    el('dlogCamNameLabel').textContent = 'Name (talk)';
    el('dlogCamHint').innerHTML = 'Tap <b>Capture</b> to snap. Then tap <b>Name (talk)</b> to name &amp; save, or <b>Capture</b> again to save as <span class="font-mono">Photo N · date</span>.';
    renderCamThumbs();
    renderPhotoGrid();
    updateCounts();
  }

  function renderCamThumbs() {
    const wrap = el('dlogCamThumbs');
    let html = '';
    if (state.armedPhoto) html += `<div class="dlog-photo ring-2 ring-blue-500"><img src="${state.armedPhoto.url}"><div class="dlog-photo-name">Unsaved</div></div>`;
    state.pendingPhotos.slice(-7).forEach((p) => { html += `<div class="dlog-photo"><img src="${p.url}"><div class="dlog-photo-name">${esc(p.name)}</div></div>`; });
    wrap.innerHTML = html;
  }

  function onCamName() {
    if (!state.armedPhoto) { el('dlogCamHint').innerHTML = 'Capture a photo first, then name it.'; return; }
    if (!state.listening) startListening();
    else commitArmed(el('dlogCamNameInput').value);
  }

  function startListening() {
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    const input = el('dlogCamNameInput');
    const hint = el('dlogCamHint');
    input.classList.remove('hidden');
    input.focus();
    el('dlogCamNameLabel').textContent = 'Stop & Save';
    el('dlogCamName').classList.add('listening');
    state.listening = true;
    if (!window.isSecureContext) {
      hint.innerHTML = '<span class="text-amber-400">Voice needs a secure (HTTPS) connection. Type the name, then tap Stop &amp; Save.</span>';
      return;
    }
    if (!SR) {
      hint.innerHTML = '<span class="text-amber-400">Voice isn\'t supported in this browser (try Chrome, Edge, or Safari). Type the name, then tap Stop &amp; Save.</span>';
      return;
    }
    try {
      const rec = new SR();
      rec.lang = 'en-US';
      rec.interimResults = true;
      rec.continuous = true;
      rec.onstart = () => { hint.innerHTML = '<span class="text-emerald-400"><i class="fa-solid fa-microphone"></i> Listening… say the file name, then tap Stop &amp; Save.</span>'; };
      rec.onresult = (event) => { let t = ''; for (let i = 0; i < event.results.length; i++) t += event.results[i][0].transcript; input.value = t.trim(); };
      rec.onerror = (e) => {
        const msg = e && e.error === 'not-allowed'
          ? 'Microphone permission denied. Allow mic access, or type the name.'
          : 'Voice error — type the name, then tap Stop & Save.';
        hint.innerHTML = `<span class="text-amber-400">${msg}</span>`;
      };
      rec.start();
      state.recognition = rec;
    } catch (_) {
      hint.innerHTML = '<span class="text-amber-400">Voice unavailable — type the name, then tap Stop &amp; Save.</span>';
    }
  }

  function stopListening() {
    state.listening = false;
    el('dlogCamName').classList.remove('listening');
    el('dlogCamNameLabel').textContent = 'Name (talk)';
    if (state.recognition) { try { state.recognition.stop(); } catch (_) {} state.recognition = null; }
  }

  function closeCamera() {
    if (state.armedPhoto) commitArmed('');
    stopListening();
    stopStream();
    el('dlogCameraModal').close();
    renderPhotoGrid();
    updateCounts();
  }

  function renderPhotoGrid() {
    const grid = el('dlogPhotoGrid');
    let html = '';
    state.pendingPhotos.forEach((p) => {
      html += `<div class="dlog-photo"><img src="${p.url}" alt="${esc(p.name)}"><div class="dlog-photo-name">${esc(p.name)}</div><div class="dlog-photo-del" data-del-pending="${p.id}"><i class="fa-solid fa-times"></i></div></div>`;
    });
    state.existingPhotos.forEach((p) => {
      html += `<div class="dlog-photo"><img src="${esc(p.url || '')}" alt="${esc(p.original_name || '')}"><div class="dlog-photo-name">${esc(p.original_name || p.filename || '')}</div></div>`;
    });
    grid.innerHTML = html || '<div class="text-xs text-zinc-500 col-span-full py-3 text-center">No photos yet — tap Open Camera.</div>';
    grid.querySelectorAll('[data-del-pending]').forEach((n) => n.addEventListener('click', () => {
      const id = n.getAttribute('data-del-pending');
      state.pendingPhotos = state.pendingPhotos.filter((p) => String(p.id) !== id);
      renderPhotoGrid(); updateCounts();
    }));
  }

  // ---------------- Modal open/save ----------------
  function populateProjects() {
    const sel = el('dlogProject');
    sel.innerHTML = (ctx.projects || []).map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    if (ctx.projectId) sel.value = String(ctx.projectId);
  }

  function resetModal() {
    state.editingId = null;
    state.pendingPhotos = []; state.existingPhotos = []; state.armedPhoto = null; state.photoSeq = 0;
    el('dlogModalTitle').textContent = 'New Daily Log';
    el('dlogDate').value = new Date().toISOString().slice(0, 10);
    ['dlogWeather', 'dlogWork', 'dlogNotes', 'dlogTempHigh', 'dlogTempLow', 'dlogWind', 'dlogHumidity', 'dlogPrecip', 'dlogWorkHours'].forEach((id) => { if (el(id)) el(id).value = ''; });
    if (el('dlogGround')) el('dlogGround').value = '';
    if (el('dlogWeatherImpact')) el('dlogWeatherImpact').value = '';
    el('dlogStatus').value = 'Submitted';
    SECTIONS.forEach((s) => { const c = el(`dlogRows_${s.key}`); if (c) c.innerHTML = ''; });
    renderPhotoGrid();
    updateCounts();
  }

  function openCreate() {
    resetModal();
    populateProjects();
    addRow('manpower');
    el('dlogModal').showModal();
  }

  async function openEdit(id) {
    resetModal();
    populateProjects();
    try {
      const res = await fetch(`/api/daily-logs/${id}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed');
      const log = json.log;
      state.editingId = id;
      el('dlogModalTitle').textContent = `Edit Daily Log — ${fmtDate(log.date)}`;
      el('dlogProject').value = String(log.project_id);
      el('dlogDate').value = log.date || '';
      el('dlogWeather').value = log.weather || '';
      el('dlogWork').value = log.work_performed || '';
      el('dlogNotes').value = log.notes || '';
      el('dlogStatus').value = log.status || 'Submitted';
      const d = log.details || {};
      if (el('dlogTempHigh')) el('dlogTempHigh').value = d.temperature || '';
      if (el('dlogTempLow')) el('dlogTempLow').value = d.temp_low || '';
      if (el('dlogWind')) el('dlogWind').value = d.wind || '';
      if (el('dlogHumidity')) el('dlogHumidity').value = d.humidity || '';
      if (el('dlogPrecip')) el('dlogPrecip').value = d.precipitation || '';
      if (el('dlogGround')) el('dlogGround').value = d.ground_condition || '';
      if (el('dlogWorkHours')) el('dlogWorkHours').value = d.work_hours || '';
      if (el('dlogWeatherImpact')) el('dlogWeatherImpact').value = d.weather_impact || '';
      (log.manpower || []).forEach((r) => addRow('manpower', r));
      (log.equipment || []).forEach((r) => addRow('equipment', r));
      DETAIL_KEYS.forEach((k) => { if (k !== 'equipment') (d[k] || []).forEach((r) => addRow(k, r)); });
      state.existingPhotos = log.photos || [];
      renderPhotoGrid();
      updateCounts();
      el('dlogDetailModal').close();
      el('dlogModal').showModal();
    } catch (e) { alert(e.message || 'Could not open log'); }
  }

  function collectPayload() {
    const payload = {
      project_id: parseInt(el('dlogProject').value, 10),
      date: el('dlogDate').value,
      weather: el('dlogWeather').value.trim(),
      work_performed: el('dlogWork').value.trim(),
      notes: el('dlogNotes').value.trim(),
      status: el('dlogStatus').value,
      temperature: el('dlogTempHigh').value, temp_low: el('dlogTempLow').value,
      wind: el('dlogWind').value, humidity: el('dlogHumidity').value,
      precipitation: el('dlogPrecip').value, ground_condition: el('dlogGround').value,
      work_hours: el('dlogWorkHours').value, weather_impact: el('dlogWeatherImpact').value,
    };
    SECTIONS.forEach((s) => { payload[s.key] = collectRows(s.key); });
    return payload;
  }

  async function save() {
    const payload = collectPayload();
    if (!payload.project_id || !payload.date) { alert('Project and date are required.'); return; }
    const saveBtn = el('dlogSave');
    saveBtn.disabled = true; saveBtn.textContent = 'Saving…';
    try {
      const url = state.editingId ? `/api/daily-logs/${state.editingId}` : '/api/daily-logs';
      const method = state.editingId ? 'PUT' : 'POST';
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Save failed');
      const logId = json.log.id;
      for (const photo of state.pendingPhotos) {
        const fd = new FormData();
        fd.append('file', photo.blob, `${photo.name}.jpg`);
        fd.append('name', photo.name);
        fd.append('kind', 'photo');
        await fetch(`/api/daily-logs/${logId}/attachments`, { method: 'POST', body: fd });
      }
      state.pendingPhotos.forEach((p) => { try { URL.revokeObjectURL(p.url); } catch (_) {} });
      state.pendingPhotos = [];
      el('dlogModal').close();
      await loadList();
      if (global.showToast) global.showToast('Daily log saved');
    } catch (e) { alert(e.message || 'Could not save'); }
    finally { saveBtn.disabled = false; saveBtn.textContent = 'Save Daily Log'; }
  }

  // ---------------- Print ----------------
  const DLOG_PRINT_COLUMNS = [
    { key: 'date', label: 'Date', width: '8%', align: 'center' },
    { key: 'weather', label: 'Weather', width: '10%' },
    { key: 'crew', label: 'Crew', width: '5%', align: 'center' },
    { key: 'hours', label: 'Hours', width: '5%', align: 'center' },
    { key: 'work', label: 'Work<br>Performed', width: '38%' },
    { key: 'photos', label: 'Photos', width: '5%', align: 'center' },
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

  function logRegisterRow(l) {
    return {
      date: fmtDate(l.date),
      weather: l.weather || '—',
      crew: l.total_workers ?? '—',
      hours: l.total_hours ?? '—',
      work: l.work_performed || '—',
      photos: l.photo_count ?? 0,
      status: l.status || 'Submitted',
    };
  }

  async function triggerDailyPrint(html) {
    if (global.CasePMOutput) {
      await global.CasePMOutput.deliverHtml({
        title: 'Daily Log',
        html,
        filenameBase: `Daily_Log_${projectId() || 'project'}`,
        sourceModule: 'daily_log',
        systemFolderKey: 'daily-logs',
        subfolder: 'Exports',
        printOptions: { bodyHtml: html, containerId: 'dlogPrintSheet', bodyClass: 'printing-daily-log' },
      });
      return;
    }
    global.CasePMPrint.triggerPrintPreview(html, { containerId: 'dlogPrintSheet', bodyClass: 'printing-daily-log' });
  }

  async function printLog() {
    if (typeof global.CasePMPrint === 'undefined') {
      alert('Print module not loaded.');
      return;
    }
    const rows = filteredLogs().map(logRegisterRow);
    const html = global.CasePMPrint.buildPrintDocument({
      meta: getPrintMeta(),
      sections: [{ title: 'DAILY LOG REGISTER', columns: DLOG_PRINT_COLUMNS, rows, emptyMessage: 'No daily logs to print.' }],
      rowsPerPage: 24,
    });
    await triggerDailyPrint(html);
  }

  function buildDailyReportBody(log) {
    const d = log.details || {};
    const block = (title, rows, render) => (rows && rows.length)
      ? `<div><h3>${esc(title)}</h3>${rows.map(render).join('')}</div>` : '';
    const photos = (log.photos || []).map((p) => `<div style="display:inline-block;width:120px;margin:4px 8px 4px 0;vertical-align:top;"><img src="${esc(p.url || '')}" alt="" style="width:100%;height:80px;object-fit:cover;border:1px solid #ccc;"><div style="font-size:7pt;margin-top:2px;">${esc(p.original_name || p.filename || '')}</div></div>`).join('');
    return `
      <div class="casepm-log-meta">
        <span><strong>Status:</strong> ${esc(log.status || 'Submitted')}</span>
        <span><strong>Weather:</strong> ${esc(log.weather || '—')}</span>
        <span><strong>Crew:</strong> ${log.total_workers || 0}</span>
        <span><strong>Hours:</strong> ${log.total_hours || 0}</span>
        ${log.author ? `<span><strong>By:</strong> ${esc(log.author)}</span>` : ''}
      </div>
      <div><h3>Work Performed</h3><div class="casepm-log-block">${esc(log.work_performed || '—')}</div></div>
      ${log.notes ? `<div><h3>Notes</h3><div class="casepm-log-block">${esc(log.notes)}</div></div>` : ''}
      ${block('Manpower', log.manpower, (m) => `<div class="casepm-log-line">• ${esc(m.company || '—')} — ${m.personnel_count || 0} × ${m.hours || 0}h ${m.work_performed ? '· ' + esc(m.work_performed) : ''}</div>`)}
      ${block('Equipment', log.equipment, (e) => `<div class="casepm-log-line">• ${esc(e.equipment_name)} (${e.quantity || 1}) ${e.condition ? '· ' + esc(e.condition) : ''}</div>`)}
      ${block('Deliveries', d.deliveries, (x) => `<div class="casepm-log-line">• ${esc(x.item)} ${x.supplier ? 'from ' + esc(x.supplier) : ''} ${x.quantity ? '· ' + esc(x.quantity) : ''}</div>`)}
      ${block('Materials', d.materials, (x) => `<div class="casepm-log-line">• ${esc(x.material)} ${x.quantity ? esc(x.quantity) + ' ' + esc(x.unit || '') : ''} ${x.location ? '@ ' + esc(x.location) : ''}</div>`)}
      ${block('Delays', d.delays, (x) => `<div class="casepm-log-line">• [${esc(x.type)}] ${esc(x.description)} ${x.hours_lost ? '· ' + esc(x.hours_lost) + 'h lost' : ''}</div>`)}
      ${block('Visitors', d.visitors, (x) => `<div class="casepm-log-line">• ${esc(x.name)} ${x.company ? '(' + esc(x.company) + ')' : ''} ${x.purpose ? '· ' + esc(x.purpose) : ''}</div>`)}
      ${block('Phone Calls', d.phone_calls, (x) => `<div class="casepm-log-line">• ${esc(x.contact)} ${x.company ? '(' + esc(x.company) + ')' : ''} — ${esc(x.subject || '')}</div>`)}
      ${block('Inspections', d.inspections, (x) => `<div class="casepm-log-line">• ${esc(x.type)} ${x.agency ? '(' + esc(x.agency) + ')' : ''} — ${esc(x.result || '')} ${x.notes ? '· ' + esc(x.notes) : ''}</div>`)}
      ${block('Safety', d.safety, (x) => `<div class="casepm-log-line">• [${esc(x.type)}] ${esc(x.description)} ${x.action ? '→ ' + esc(x.action) : ''}</div>`)}
      ${block('Accidents', d.accidents, (x) => `<div class="casepm-log-line">• ${esc(x.person)} ${x.company ? '(' + esc(x.company) + ')' : ''} — ${esc(x.description || '')}</div>`)}
      ${block('Quantities', d.quantities, (x) => `<div class="casepm-log-line">• ${esc(x.description)} — ${esc(x.quantity || '')} ${esc(x.unit || '')} ${x.cost_code ? '· ' + esc(x.cost_code) : ''}</div>`)}
      ${block('Dumpster / Waste', d.dumpsters, (x) => `<div class="casepm-log-line">• ${esc(x.type)} ${x.size ? '(' + esc(x.size) + ')' : ''} ${x.hauls ? '· ' + esc(x.hauls) + ' hauls' : ''}</div>`)}
      ${block('Scheduled Work', d.scheduled_work, (x) => `<div class="casepm-log-line">• ${esc(x.activity)} — ${esc(x.status || '')} ${x.notes ? '· ' + esc(x.notes) : ''}</div>`)}
      ${photos ? `<div><h3>Photos</h3><div>${photos}</div></div>` : ''}
    `;
  }

  async function printDetail() {
    if (!state.viewingLog) return;
    if (typeof global.CasePMPrint === 'undefined') {
      alert('Print module not loaded.');
      return;
    }
    const meta = getPrintMeta();
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const title = `DAILY LOG — ${fmtDate(state.viewingLog.date)}`;
    const html = `<div class="casepm-print-page">
      <div class="casepm-print-header">
        <div><div class="casepm-print-title">${esc(title)}</div></div>
        <div class="casepm-print-meta">
          ${meta.number ? `<div><span class="label">PROJECT ID</span><br>${esc(meta.number)}</div>` : ''}
          ${meta.name ? `<div style="margin-top:4px"><span class="label">PROJECT NAME</span><br>${esc(meta.name)}</div>` : ''}
        </div>
      </div>
      <div class="casepm-log-report">${buildDailyReportBody(state.viewingLog)}</div>
      <div class="casepm-print-footer">
        <span>Confidential</span>
        <span class="center">${esc(printedOn)}</span>
        <span class="right">Page 1</span>
      </div>
    </div>`;
    await triggerDailyPrint(html);
  }

  // ---------------- Detail ----------------
  async function openDetail(id) {
    try {
      const res = await fetch(`/api/daily-logs/${id}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed');
      const log = json.log;
      state.viewingLog = log;
      const d = log.details || {};
      el('dlogDetailTitle').textContent = `Daily Log — ${fmtDate(log.date)}`;
      const block = (title, rows, render) => (rows && rows.length) ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">${title}</div>${rows.map(render).join('')}</div>` : '';
      const photos = (log.photos || []).map((p) => `<a href="${esc(p.url || '#')}" target="_blank" class="dlog-photo block"><img src="${esc(p.url || '')}"><div class="dlog-photo-name">${esc(p.original_name || p.filename || '')}</div></a>`).join('');
      el('dlogDetailBody').innerHTML = `
        <div class="flex flex-wrap gap-3 items-center">
          ${statusBadge(log.status)}
          <span class="text-zinc-400"><i class="fa-solid fa-cloud-sun mr-1"></i>${esc(log.weather || '—')}</span>
          <span class="text-zinc-400"><i class="fa-solid fa-users mr-1"></i>${log.total_workers || 0} crew</span>
          <span class="text-zinc-400"><i class="fa-solid fa-clock mr-1"></i>${log.total_hours || 0} hrs</span>
          ${log.author ? `<span class="text-zinc-500 text-xs">by ${esc(log.author)}</span>` : ''}
        </div>
        <div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Work Performed</div><div class="whitespace-pre-wrap">${esc(log.work_performed || '—')}</div></div>
        ${log.notes ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Notes</div><div class="whitespace-pre-wrap">${esc(log.notes)}</div></div>` : ''}
        ${block('Manpower', log.manpower, (m) => `<div class="text-sm">• ${esc(m.company || '—')} — ${m.personnel_count || 0} × ${m.hours || 0}h ${m.work_performed ? '· ' + esc(m.work_performed) : ''}</div>`)}
        ${block('Equipment', log.equipment, (e) => `<div class="text-sm">• ${esc(e.equipment_name)} (${e.quantity || 1}) ${e.condition ? '· ' + esc(e.condition) : ''}</div>`)}
        ${block('Deliveries', d.deliveries, (x) => `<div class="text-sm">• ${esc(x.item)} ${x.supplier ? 'from ' + esc(x.supplier) : ''} ${x.quantity ? '· ' + esc(x.quantity) : ''}</div>`)}
        ${block('Materials', d.materials, (x) => `<div class="text-sm">• ${esc(x.material)} ${x.quantity ? esc(x.quantity) + ' ' + esc(x.unit || '') : ''} ${x.location ? '@ ' + esc(x.location) : ''}</div>`)}
        ${block('Delays', d.delays, (x) => `<div class="text-sm text-red-300">• [${esc(x.type)}] ${esc(x.description)} ${x.hours_lost ? '· ' + esc(x.hours_lost) + 'h lost' : ''}</div>`)}
        ${block('Visitors', d.visitors, (x) => `<div class="text-sm">• ${esc(x.name)} ${x.company ? '(' + esc(x.company) + ')' : ''} ${x.purpose ? '· ' + esc(x.purpose) : ''}</div>`)}
        ${block('Phone Calls', d.phone_calls, (x) => `<div class="text-sm">• ${esc(x.contact)} ${x.company ? '(' + esc(x.company) + ')' : ''} — ${esc(x.subject || '')}</div>`)}
        ${block('Inspections', d.inspections, (x) => `<div class="text-sm">• ${esc(x.type)} ${x.agency ? '(' + esc(x.agency) + ')' : ''} — <b>${esc(x.result || '')}</b> ${x.notes ? '· ' + esc(x.notes) : ''}</div>`)}
        ${block('Safety', d.safety, (x) => `<div class="text-sm text-yellow-300">• [${esc(x.type)}] ${esc(x.description)} ${x.action ? '→ ' + esc(x.action) : ''}</div>`)}
        ${block('Accidents', d.accidents, (x) => `<div class="text-sm text-red-300">• ${esc(x.person)} ${x.company ? '(' + esc(x.company) + ')' : ''} — ${esc(x.description || '')}</div>`)}
        ${block('Quantities', d.quantities, (x) => `<div class="text-sm">• ${esc(x.description)} — ${esc(x.quantity || '')} ${esc(x.unit || '')} ${x.cost_code ? '· ' + esc(x.cost_code) : ''}</div>`)}
        ${block('Dumpster / Waste', d.dumpsters, (x) => `<div class="text-sm">• ${esc(x.type)} ${x.size ? '(' + esc(x.size) + ')' : ''} ${x.hauls ? '· ' + esc(x.hauls) + ' hauls' : ''}</div>`)}
        ${block('Scheduled Work', d.scheduled_work, (x) => `<div class="text-sm">• ${esc(x.activity)} — <b>${esc(x.status || '')}</b> ${x.notes ? '· ' + esc(x.notes) : ''}</div>`)}
        ${photos ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Photos</div><div class="grid grid-cols-3 md:grid-cols-4 gap-2">${photos}</div></div>` : ''}
      `;
      el('dlogDetailEdit').onclick = () => openEdit(id);
      el('dlogDetailPrint').onclick = () => printDetail();
      el('dlogDetailModal').showModal();
    } catch (e) { alert(e.message || 'Could not load'); }
  }

  async function fetchWeather() {
    try {
      const res = await fetch('/api/dashboard/weather');
      const w = await res.json();
      if (w.ok) {
        el('dlogWeather').value = `${w.description}, ${w.temperature}°F (H${w.high}/L${w.low}), wind ${w.wind_mph} mph`;
        if (el('dlogTempHigh')) el('dlogTempHigh').value = w.high ?? '';
        if (el('dlogTempLow')) el('dlogTempLow').value = w.low ?? '';
        if (el('dlogWind')) el('dlogWind').value = w.wind_mph ?? '';
        if (el('dlogHumidity')) el('dlogHumidity').value = w.humidity ?? '';
      } else if (global.showToast) { global.showToast(w.error || 'Weather unavailable', 'error'); }
    } catch (_) { /* ignore */ }
  }

  function setMode(detailed) {
    state.detailed = detailed;
    el('dlogModeLabel').textContent = detailed ? 'Detailed' : 'Simple';
    document.querySelectorAll('.dlog-detailed').forEach((n) => n.classList.toggle('hidden', !detailed));
  }

  function bind() {
    el('dlogBtnNew').addEventListener('click', openCreate);
    el('dlogBtnPrint')?.addEventListener('click', printLog);
    el('dlogBtnRefresh')?.addEventListener('click', loadList);
    el('dlogModalClose').addEventListener('click', () => el('dlogModal').close());
    el('dlogCancel').addEventListener('click', () => el('dlogModal').close());
    el('dlogSave').addEventListener('click', save);
    el('dlogDetailClose').addEventListener('click', () => el('dlogDetailModal').close());
    el('dlogWeatherFetch').addEventListener('click', fetchWeather);
    el('dlogModeToggle').addEventListener('click', () => setMode(!state.detailed));

    // Conditions toggle (static section in template)
    document.querySelectorAll('[data-section-toggle="conditions"], [data-section-toggle="photos"]').forEach((n) => {
      n.addEventListener('click', () => {
        const body = document.querySelector(`[data-section-body="${n.getAttribute('data-section-toggle')}"]`);
        if (body) body.classList.toggle('hidden');
      });
    });

    el('dlogOpenCamera').addEventListener('click', openCamera);
    el('dlogCamClose').addEventListener('click', closeCamera);
    el('dlogCamDone').addEventListener('click', closeCamera);
    el('dlogCamShoot').addEventListener('click', onCamShoot);
    el('dlogCamName').addEventListener('click', onCamName);
    el('dlogCamSwitch').addEventListener('click', () => { state.facingMode = state.facingMode === 'environment' ? 'user' : 'environment'; startStream(); });

    el('dlogBrowseBtn').addEventListener('click', () => el('dlogBrowseInput').click());
    el('dlogBrowseInput').addEventListener('change', (e) => {
      for (const f of e.target.files) {
        const url = URL.createObjectURL(f);
        state.pendingPhotos.push({ id: Date.now() + Math.random(), blob: f, url, name: autoPhotoName() });
      }
      e.target.value = '';
      renderPhotoGrid(); updateCounts();
    });

    ['dlogSearch', 'dlogDateFilter', 'dlogStatusFilter'].forEach((id) => {
      el(id).addEventListener('input', renderList);
      el(id).addEventListener('change', renderList);
    });

    global.addEventListener('casepm:project-changed', onProjectChange);
    global.onCasePmProjectChanged = (pid) => { ctx.projectId = pid; onProjectChange(); };
  }

  function onProjectChange() { loadList(); loadCompanies(); }

  function init() {
    state.mobile = isMobile();
    buildSectionsHost();
    bind();
    if (state.mobile) setMode(false);
    loadList();
    loadCompanies();
  }

  global.CasePMDailyLog = { refresh: loadList, openCreate, printLog, printDetail };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
