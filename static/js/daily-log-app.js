/**
 * Case PM Daily Log — field-friendly daily reports with easy photo capture.
 * Simple path: project + date + work + photos. Detailed path: manpower, equipment,
 * deliveries, delays, visitors, safety. Mobile-optimized capture with speech-to-text naming.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_DAILY_LOG_CTX || {};
  const SECTIONS = ['manpower', 'equipment', 'deliveries', 'delays', 'visitors', 'safety'];
  const DELAY_TYPES = ['Weather', 'Labor', 'Material', 'Equipment', 'Owner', 'Design/RFI', 'Other'];
  const SAFETY_TYPES = ['Observation', 'Near Miss', 'Incident', 'Toolbox Talk', 'Violation'];

  const state = {
    logs: [],
    stats: {},
    editingId: null,
    pendingPhotos: [],     // [{id, file, dataUrl, name}]
    existingPhotos: [],     // already-uploaded (edit mode)
    armedPhoto: null,       // {file, dataUrl} captured, awaiting name/save
    photoSeq: 0,
    listening: false,
    recognition: null,
    detailed: true,
    mobile: false,
  };

  function isMobile() {
    return (('ontouchstart' in window) && window.matchMedia('(max-width: 768px)').matches)
      || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  }

  function projectId() {
    return ctx.projectId || (function () {
      try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; }
    })();
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
    catch (_) { return iso; }
  }

  function el(id) { return document.getElementById(id); }

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
      if (term) {
        const hay = `${l.date} ${l.weather || ''} ${l.work_performed || ''}`.toLowerCase();
        if (!hay.includes(term)) return false;
      }
      return true;
    });
  }

  function statusBadge(status) {
    const st = status || 'Submitted';
    const cls = st === 'Reviewed' ? 'bg-blue-500/15 text-blue-400'
      : st === 'Draft' ? 'bg-zinc-700 text-zinc-300'
      : 'bg-emerald-500/15 text-emerald-400';
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
        <td class="px-4 py-3 text-center">
          <button class="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md" data-open="${l.id}">View</button>
        </td>
      </tr>`).join('');
    tbody.querySelectorAll('[data-open]').forEach((n) => {
      n.addEventListener('click', (e) => { e.stopPropagation(); openDetail(parseInt(n.getAttribute('data-open'), 10)); });
    });
  }

  // ---------------- Row builders ----------------
  function rowInput(cls, ph, val, extra) {
    return `<input type="${extra?.type || 'text'}" class="dlog-input ${cls}" placeholder="${esc(ph)}" value="${esc(val || '')}" ${extra?.attrs || ''}>`;
  }

  function selectInput(cls, options, val) {
    return `<select class="dlog-input ${cls}">${options.map((o) => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
  }

  function removeBtn() {
    return `<button type="button" class="text-red-400 hover:text-red-300 px-2 shrink-0" data-remove-row><i class="fa-solid fa-trash text-xs"></i></button>`;
  }

  const ROW_BUILDERS = {
    manpower: (r = {}) => `<div class="flex gap-2 items-center" data-row>
      ${rowInput('dl-company flex-1', 'Company / sub', r.company)}
      ${rowInput('dl-workers w-20', 'Crew', r.personnel_count, { type: 'number', attrs: 'min="0"' })}
      ${rowInput('dl-hours w-20', 'Hrs', r.hours, { type: 'number', attrs: 'step="0.5" min="0"' })}
      ${rowInput('dl-trade flex-1 dlog-hide-mobile', 'Trade / work', r.work_performed)}
      ${removeBtn()}</div>`,
    equipment: (r = {}) => `<div class="flex gap-2 items-center" data-row>
      ${rowInput('dl-name flex-1', 'Equipment', r.equipment_name)}
      ${rowInput('dl-qty w-20', 'Qty', r.quantity, { type: 'number', attrs: 'min="1"' })}
      ${rowInput('dl-cond flex-1', 'Condition / notes', r.condition)}
      ${removeBtn()}</div>`,
    deliveries: (r = {}) => `<div class="flex gap-2 items-center" data-row>
      ${rowInput('dl-item flex-1', 'Item received', r.item)}
      ${rowInput('dl-supplier flex-1 dlog-hide-mobile', 'Supplier', r.supplier)}
      ${rowInput('dl-qty w-24', 'Qty', r.quantity)}
      ${removeBtn()}</div>`,
    delays: (r = {}) => `<div class="flex gap-2 items-center" data-row>
      ${selectInput('dl-type w-32', DELAY_TYPES, r.type)}
      ${rowInput('dl-desc flex-1', 'What was delayed & why', r.description)}
      ${rowInput('dl-hours w-24', 'Hrs lost', r.hours_lost, { type: 'number', attrs: 'step="0.5" min="0"' })}
      ${removeBtn()}</div>`,
    visitors: (r = {}) => `<div class="flex gap-2 items-center" data-row>
      ${rowInput('dl-name flex-1', 'Name', r.name)}
      ${rowInput('dl-company flex-1 dlog-hide-mobile', 'Company', r.company)}
      ${rowInput('dl-purpose flex-1', 'Purpose', r.purpose)}
      ${removeBtn()}</div>`,
    safety: (r = {}) => `<div class="flex gap-2 items-center" data-row>
      ${selectInput('dl-type w-36', SAFETY_TYPES, r.type)}
      ${rowInput('dl-desc flex-1', 'Description', r.description)}
      ${removeBtn()}</div>`,
  };

  function addRow(section, data) {
    const container = el(`dlog${cap(section)}Rows`);
    if (!container) return;
    const wrap = document.createElement('div');
    wrap.innerHTML = ROW_BUILDERS[section](data);
    const node = wrap.firstElementChild;
    node.querySelector('[data-remove-row]')?.addEventListener('click', () => {
      node.remove();
      updateRowCounts();
    });
    container.appendChild(node);
    updateRowCounts();
  }

  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function collectRows(section) {
    const container = el(`dlog${cap(section)}Rows`);
    if (!container) return [];
    const out = [];
    container.querySelectorAll('[data-row]').forEach((row) => {
      const get = (sel) => row.querySelector(sel)?.value?.trim() || '';
      if (section === 'manpower') out.push({ company: get('.dl-company'), personnel_count: get('.dl-workers'), hours: get('.dl-hours'), work_performed: get('.dl-trade') });
      else if (section === 'equipment') out.push({ equipment_name: get('.dl-name'), quantity: get('.dl-qty'), condition: get('.dl-cond') });
      else if (section === 'deliveries') out.push({ item: get('.dl-item'), supplier: get('.dl-supplier'), quantity: get('.dl-qty') });
      else if (section === 'delays') out.push({ type: get('.dl-type'), description: get('.dl-desc'), hours_lost: get('.dl-hours') });
      else if (section === 'visitors') out.push({ name: get('.dl-name'), company: get('.dl-company'), purpose: get('.dl-purpose') });
      else if (section === 'safety') out.push({ type: get('.dl-type'), description: get('.dl-desc') });
    });
    return out;
  }

  function updateRowCounts() {
    SECTIONS.forEach((s) => {
      const container = el(`dlog${cap(s)}Rows`);
      const counter = el(`dlog${cap(s)}Count`);
      if (container && counter) counter.textContent = container.querySelectorAll('[data-row]').length;
    });
    el('dlogPhotoCount').textContent = state.pendingPhotos.length + state.existingPhotos.length;
  }

  // ---------------- Photos ----------------
  function autoPhotoName() {
    state.photoSeq += 1;
    const d = el('dlogDate').value || new Date().toISOString().slice(0, 10);
    return `Photo ${state.photoSeq} · ${d}`;
  }

  function readFile(file) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.readAsDataURL(file);
    });
  }

  async function onCapture(file) {
    if (!file) return;
    const dataUrl = await readFile(file);
    state.armedPhoto = { file, dataUrl };
    // Arm the shoot button to "Save", reveal name option.
    el('dlogShootBtnLabel').textContent = 'Save Photo';
    el('dlogShootBtn').classList.add('armed');
    el('dlogNameHint').innerHTML = 'Captured! Tap <b>Name (talk)</b> to name it, or tap <b>Save Photo</b> to save as auto name.';
    renderPhotoGrid(); // shows armed preview
  }

  function commitArmed(name) {
    if (!state.armedPhoto) return;
    const finalName = (name || '').trim() || autoPhotoName();
    state.pendingPhotos.push({
      id: Date.now() + Math.random(),
      file: state.armedPhoto.file,
      dataUrl: state.armedPhoto.dataUrl,
      name: finalName,
    });
    state.armedPhoto = null;
    stopListening();
    el('dlogShootBtnLabel').textContent = 'Take Photo';
    el('dlogShootBtn').classList.remove('armed');
    el('dlogNameInput').classList.add('hidden');
    el('dlogNameInput').value = '';
    el('dlogNameBtnLabel').textContent = 'Name (talk)';
    el('dlogNameHint').innerHTML = 'Tap <b>Take Photo</b> to capture. Then tap <b>Name (talk)</b> to speak/type a file name and save, or tap <b>Take Photo</b> again to save as <span class="font-mono">Photo N · date</span>.';
    renderPhotoGrid();
    updateRowCounts();
  }

  function renderPhotoGrid() {
    const grid = el('dlogPhotoGrid');
    let html = '';
    if (state.armedPhoto) {
      html += `<div class="dlog-photo ring-2 ring-blue-500">
        <img src="${state.armedPhoto.dataUrl}" alt="captured">
        <div class="dlog-photo-name">Unsaved — name or save</div>
      </div>`;
    }
    state.pendingPhotos.forEach((p) => {
      html += `<div class="dlog-photo">
        <img src="${p.dataUrl}" alt="${esc(p.name)}">
        <div class="dlog-photo-name">${esc(p.name)}</div>
        <div class="dlog-photo-del" data-del-pending="${p.id}"><i class="fa-solid fa-times"></i></div>
      </div>`;
    });
    state.existingPhotos.forEach((p) => {
      html += `<div class="dlog-photo">
        <img src="${esc(p.url || '')}" alt="${esc(p.original_name || '')}">
        <div class="dlog-photo-name">${esc(p.original_name || p.filename || '')}</div>
      </div>`;
    });
    grid.innerHTML = html;
    grid.querySelectorAll('[data-del-pending]').forEach((n) => {
      n.addEventListener('click', () => {
        const id = n.getAttribute('data-del-pending');
        state.pendingPhotos = state.pendingPhotos.filter((p) => String(p.id) !== id);
        renderPhotoGrid();
        updateRowCounts();
      });
    });
  }

  // Speech-to-text naming
  function startListening() {
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    el('dlogNameInput').classList.remove('hidden');
    el('dlogNameInput').focus();
    el('dlogNameBtnLabel').textContent = 'Stop & Save';
    el('dlogNameBtn').classList.add('listening');
    state.listening = true;
    if (!SR) return; // typing still works
    try {
      const rec = new SR();
      rec.lang = 'en-US';
      rec.interimResults = true;
      rec.continuous = true;
      rec.onresult = (event) => {
        let text = '';
        for (let i = 0; i < event.results.length; i++) text += event.results[i][0].transcript;
        el('dlogNameInput').value = text.trim();
      };
      rec.onerror = () => {};
      rec.start();
      state.recognition = rec;
    } catch (_) { /* fallback to typing */ }
  }

  function stopListening() {
    state.listening = false;
    el('dlogNameBtn').classList.remove('listening');
    el('dlogNameBtnLabel').textContent = state.armedPhoto ? 'Save with name' : 'Name (talk)';
    if (state.recognition) {
      try { state.recognition.stop(); } catch (_) { /* ignore */ }
      state.recognition = null;
    }
  }

  function onNameButton() {
    if (!state.armedPhoto) {
      el('dlogNameHint').innerHTML = 'Take a photo first, then name it.';
      return;
    }
    if (!state.listening) {
      startListening();
    } else {
      const name = el('dlogNameInput').value;
      commitArmed(name);
    }
  }

  function onShootButton() {
    if (state.armedPhoto) {
      commitArmed(''); // auto name
      return;
    }
    el('dlogPhotoInput').click();
  }

  // ---------------- Modal ----------------
  function populateProjects() {
    const sel = el('dlogProject');
    sel.innerHTML = (ctx.projects || []).map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('');
    if (ctx.projectId) sel.value = String(ctx.projectId);
  }

  function resetModal() {
    state.editingId = null;
    state.pendingPhotos = [];
    state.existingPhotos = [];
    state.armedPhoto = null;
    state.photoSeq = 0;
    el('dlogModalTitle').textContent = 'New Daily Log';
    el('dlogDate').value = new Date().toISOString().slice(0, 10);
    el('dlogWeather').value = '';
    el('dlogWork').value = '';
    el('dlogNotes').value = '';
    el('dlogStatus').value = 'Submitted';
    SECTIONS.forEach((s) => { const c = el(`dlog${cap(s)}Rows`); if (c) c.innerHTML = ''; });
    renderPhotoGrid();
    updateRowCounts();
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
      (log.manpower || []).forEach((r) => addRow('manpower', r));
      (log.equipment || []).forEach((r) => addRow('equipment', r));
      const d = log.details || {};
      (d.deliveries || []).forEach((r) => addRow('deliveries', r));
      (d.delays || []).forEach((r) => addRow('delays', r));
      (d.visitors || []).forEach((r) => addRow('visitors', r));
      (d.safety || []).forEach((r) => addRow('safety', r));
      state.existingPhotos = log.photos || [];
      renderPhotoGrid();
      updateRowCounts();
      el('dlogDetailModal').close();
      el('dlogModal').showModal();
    } catch (e) {
      alert(e.message || 'Could not open log');
    }
  }

  async function save() {
    const pid = parseInt(el('dlogProject').value, 10);
    const date = el('dlogDate').value;
    if (!pid || !date) { alert('Project and date are required.'); return; }
    if (state.armedPhoto) commitArmed(''); // save any captured-but-unnamed photo

    const payload = {
      project_id: pid,
      date,
      weather: el('dlogWeather').value.trim(),
      work_performed: el('dlogWork').value.trim(),
      notes: el('dlogNotes').value.trim(),
      status: el('dlogStatus').value,
      manpower: collectRows('manpower'),
      equipment: collectRows('equipment'),
      deliveries: collectRows('deliveries'),
      delays: collectRows('delays'),
      visitors: collectRows('visitors'),
      safety: collectRows('safety'),
    };

    const saveBtn = el('dlogSave');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';
    try {
      const url = state.editingId ? `/api/daily-logs/${state.editingId}` : '/api/daily-logs';
      const method = state.editingId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Save failed');
      const logId = json.log.id;

      for (const photo of state.pendingPhotos) {
        const fd = new FormData();
        const ext = (photo.file.name && photo.file.name.includes('.')) ? photo.file.name.slice(photo.file.name.lastIndexOf('.')) : '.jpg';
        fd.append('file', photo.file, `${photo.name}${ext}`);
        fd.append('name', photo.name);
        fd.append('kind', 'photo');
        await fetch(`/api/daily-logs/${logId}/attachments`, { method: 'POST', body: fd });
      }

      el('dlogModal').close();
      await loadList();
      if (global.showToast) global.showToast('Daily log saved');
    } catch (e) {
      alert(e.message || 'Could not save');
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Daily Log';
    }
  }

  // ---------------- Detail ----------------
  async function openDetail(id) {
    try {
      const res = await fetch(`/api/daily-logs/${id}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed');
      const log = json.log;
      el('dlogDetailTitle').textContent = `Daily Log — ${fmtDate(log.date)}`;
      const d = log.details || {};
      const section = (title, rows, render) => (rows && rows.length)
        ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">${title}</div>${rows.map(render).join('')}</div>` : '';
      const photos = (log.photos || []).map((p) => `
        <a href="${esc(p.url || '#')}" target="_blank" class="dlog-photo block">
          <img src="${esc(p.url || '')}" alt="${esc(p.original_name || '')}">
          <div class="dlog-photo-name">${esc(p.original_name || p.filename || '')}</div>
        </a>`).join('');
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
        ${section('Manpower', log.manpower, (m) => `<div class="text-sm">• ${esc(m.company || '—')} — ${m.personnel_count || 0} × ${m.hours || 0}h ${m.work_performed ? '· ' + esc(m.work_performed) : ''}</div>`)}
        ${section('Equipment', log.equipment, (e) => `<div class="text-sm">• ${esc(e.equipment_name)} (${e.quantity || 1}) ${e.condition ? '· ' + esc(e.condition) : ''}</div>`)}
        ${section('Deliveries', d.deliveries, (x) => `<div class="text-sm">• ${esc(x.item)} ${x.supplier ? 'from ' + esc(x.supplier) : ''} ${x.quantity ? '· ' + esc(x.quantity) : ''}</div>`)}
        ${section('Delays', d.delays, (x) => `<div class="text-sm text-red-300">• [${esc(x.type)}] ${esc(x.description)} ${x.hours_lost ? '· ' + esc(x.hours_lost) + 'h lost' : ''}</div>`)}
        ${section('Visitors', d.visitors, (x) => `<div class="text-sm">• ${esc(x.name)} ${x.company ? '(' + esc(x.company) + ')' : ''} ${x.purpose ? '· ' + esc(x.purpose) : ''}</div>`)}
        ${section('Safety', d.safety, (x) => `<div class="text-sm text-yellow-300">• [${esc(x.type)}] ${esc(x.description)}</div>`)}
        ${photos ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Photos</div><div class="grid grid-cols-3 md:grid-cols-4 gap-2">${photos}</div></div>` : ''}
      `;
      el('dlogDetailEdit').onclick = () => openEdit(id);
      el('dlogDetailModal').showModal();
    } catch (e) {
      alert(e.message || 'Could not load');
    }
  }

  // ---------------- Weather ----------------
  async function fetchWeather() {
    try {
      const res = await fetch('/api/dashboard/weather');
      const w = await res.json();
      if (w.ok) {
        el('dlogWeather').value = `${w.description}, ${w.temperature}°F (H${w.high}/L${w.low}), wind ${w.wind_mph} mph`;
      } else if (global.showToast) {
        global.showToast(w.error || 'Weather unavailable', 'error');
      }
    } catch (_) { /* ignore */ }
  }

  // ---------------- Sections toggle & mode ----------------
  function toggleSection(name) {
    const body = document.querySelector(`[data-section-body="${name}"]`);
    if (body) body.classList.toggle('hidden');
  }

  function setMode(detailed) {
    state.detailed = detailed;
    el('dlogModeLabel').textContent = detailed ? 'Detailed' : 'Simple';
    document.querySelectorAll('.dlog-detailed').forEach((n) => n.classList.toggle('hidden', !detailed));
  }

  // ---------------- Init ----------------
  function bind() {
    el('dlogBtnNew').addEventListener('click', openCreate);
    el('dlogBtnRefresh')?.addEventListener('click', loadList);
    el('dlogModalClose').addEventListener('click', () => el('dlogModal').close());
    el('dlogCancel').addEventListener('click', () => el('dlogModal').close());
    el('dlogSave').addEventListener('click', save);
    el('dlogDetailClose').addEventListener('click', () => el('dlogDetailModal').close());
    el('dlogWeatherFetch').addEventListener('click', fetchWeather);
    el('dlogModeToggle').addEventListener('click', () => setMode(!state.detailed));

    el('dlogShootBtn').addEventListener('click', onShootButton);
    el('dlogNameBtn').addEventListener('click', onNameButton);
    el('dlogPhotoInput').addEventListener('change', (e) => { onCapture(e.target.files[0]); e.target.value = ''; });
    el('dlogBrowseBtn').addEventListener('click', () => el('dlogBrowseInput').click());
    el('dlogBrowseInput').addEventListener('change', async (e) => {
      for (const f of e.target.files) {
        const dataUrl = await readFile(f);
        state.pendingPhotos.push({ id: Date.now() + Math.random(), file: f, dataUrl, name: autoPhotoName() });
      }
      e.target.value = '';
      renderPhotoGrid();
      updateRowCounts();
    });

    document.querySelectorAll('[data-section-toggle]').forEach((n) => {
      n.addEventListener('click', () => toggleSection(n.getAttribute('data-section-toggle')));
    });
    document.querySelectorAll('[data-add-row]').forEach((n) => {
      n.addEventListener('click', () => addRow(n.getAttribute('data-add-row')));
    });

    ['dlogSearch', 'dlogDateFilter', 'dlogStatusFilter'].forEach((id) => {
      el(id).addEventListener('input', renderList);
      el(id).addEventListener('change', renderList);
    });

    global.addEventListener('casepm:project-changed', loadList);
    global.onCasePmProjectChanged = function (pid) { ctx.projectId = pid; loadList(); };
  }

  function init() {
    state.mobile = isMobile();
    if (state.mobile) {
      // On phones, start in Simple mode and open detail sections on demand.
      document.body.classList.add('dlog-mobile');
    }
    bind();
    if (state.mobile) setMode(false);
    loadList();
  }

  global.CasePMDailyLog = { refresh: loadList, openCreate };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
