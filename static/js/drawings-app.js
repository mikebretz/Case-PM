/**
 * Case PM — Drawings module (Procore / Bluebeam / ACC / Fieldwire parity)
 */
(function (global) {
  'use strict';

  const SECTION_ORDER = ['G', 'C', 'A', 'S', 'M', 'E', 'P', 'FP', 'L', 'T', 'I', 'OTHER'];
  const MARKUP_TOOLS = ['pan', 'select', 'line', 'rect', 'cloud', 'arrow', 'text', 'highlight', 'measure', 'rfi_pin', 'calibrate'];

  let state = {
    drawings: [],
    sections: {},
    stats: {},
    rfis: [],
    view: 'sections',
    activeSection: null,
    openDrawing: null,
    openDetail: null,
    revisions: [],
    markups: [],
    tool: 'pan',
    layerFilter: { personal: true, published: true },
    scale: 1,
    panX: 0,
    panY: 0,
    pdfDoc: null,
    pdfPage: 1,
    renderTask: null,
    drawing: false,
    drawStart: null,
    tempMarkup: null,
    pixelsPerUnit: null,
    measureUnit: 'ft',
    compareMode: false,
    compareOpacity: 0.5,
    compareRevisionId: null,
  };

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString();
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || json.message || 'Request failed');
    return json;
  }

  async function loadDashboard() {
    const pid = projectId();
    if (!pid) return;
    state.stats = await api(`/api/drawings/dashboard?project_id=${pid}`);
    renderSummary();
    renderSectionTabs();
  }

  async function loadDrawings() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/drawings?project_id=${pid}`);
    state.drawings = json.drawings || [];
    state.sections = json.sections || {};
    if (!state.activeSection) {
      const keys = Object.keys(state.sections);
      state.activeSection = keys.sort(sectionSort)[0] || null;
    }
    renderSectionTabs();
    renderActiveView();
  }

  async function loadRfis() {
    const pid = projectId();
    if (!pid) return;
    try {
      const json = await api(`/api/drawings/rfis?project_id=${pid}`);
      state.rfis = json.rfis || [];
    } catch { state.rfis = []; }
  }

  function sectionSort(a, b) {
    const ia = SECTION_ORDER.indexOf(a);
    const ib = SECTION_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  }

  function renderSummary() {
    const s = state.stats;
    const map = {
      statDrawTotal: s.total_sheets || 0,
      statDrawCurrent: s.current_sheets || 0,
      statDrawSections: s.section_count || 0,
      statDrawRevisions: s.total_revisions || 0,
      statDrawReview: s.for_review || 0,
      statDrawSuperseded: s.superseded || 0,
    };
    Object.keys(map).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
  }

  function renderSectionTabs() {
    const el = document.getElementById('drawSectionTabs');
    if (!el) return;
    const sections = state.sections || {};
    const keys = Object.keys(sections).sort(sectionSort);
    if (!keys.length) {
      el.innerHTML = '<span class="text-xs text-zinc-500">Upload drawings to populate sections (A, S, M, E…)</span>';
      return;
    }
    el.innerHTML = keys.map(sec => {
      const count = (sections[sec] || []).length;
      const active = state.activeSection === sec ? 'bg-sky-700 text-white' : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
      return `<button type="button" onclick="CasePMDrawings.selectSection('${esc(sec)}')" class="px-3 py-1.5 rounded-md text-xs font-medium ${active}">${esc(sec)} <span class="opacity-70">(${count})</span></button>`;
    }).join('');
  }

  function renderActiveView() {
    if (state.view === 'sections') renderSectionGrid();
    if (state.view === 'list') renderTable();
    if (state.view === 'viewer' && state.openDrawing) renderViewerChrome();
  }

  function filteredDrawings() {
    const search = (document.getElementById('drawSearch')?.value || '').toLowerCase();
    const discipline = document.getElementById('drawDisciplineFilter')?.value || '';
    const status = document.getElementById('drawStatusFilter')?.value || '';
    return state.drawings.filter(d => {
      const text = `${d.sheet_number} ${d.title} ${d.discipline}`.toLowerCase();
      if (search && !text.includes(search)) return false;
      if (discipline && d.discipline !== discipline) return false;
      if (status && d.status !== status) return false;
      return true;
    });
  }

  async function renderThumb(canvas, drawing) {
    if (!global.pdfjsLib || !drawing.file_url) {
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#27272a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#71717a';
      ctx.font = '12px sans-serif';
      ctx.fillText(drawing.sheet_number, 10, 24);
      return;
    }
    try {
      const res = await fetch(drawing.file_url, { credentials: 'same-origin' });
      const buf = await res.arrayBuffer();
      const pdf = await pdfjsLib.getDocument({ data: buf.slice(0) }).promise;
      const page = await pdf.getPage(1);
      const viewport = page.getViewport({ scale: 0.25 });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
    } catch {
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#27272a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
  }

  function renderSectionGrid() {
    const grid = document.getElementById('drawSectionGrid');
    if (!grid) return;
    const items = (state.sections[state.activeSection] || []).filter(d => filteredDrawings().some(f => f.id === d.id));
    if (!items.length) {
      grid.innerHTML = '<div class="col-span-full py-16 text-center text-zinc-500">No drawings in this section. Upload a drawing set or individual sheets.</div>';
      return;
    }
    grid.innerHTML = items.map(d => `
      <div class="bg-zinc-800 border border-zinc-700 rounded-md overflow-hidden hover:border-sky-600 cursor-pointer group" ondblclick="CasePMDrawings.openViewer(${d.id})" onclick="CasePMDrawings.previewSheet(${d.id})">
        <div class="aspect-[4/3] bg-zinc-900 relative">
          <canvas id="thumb-${d.id}" class="w-full h-full object-contain"></canvas>
          <div class="absolute top-2 left-2 font-mono text-xs bg-black/60 px-2 py-0.5 rounded text-sky-300">${esc(d.sheet_number)}</div>
          <div class="absolute top-2 right-2 text-[10px] bg-black/60 px-2 py-0.5 rounded">${esc(d.revision_label || 'Rev 0')}</div>
        </div>
        <div class="p-2">
          <div class="text-xs font-medium truncate">${esc(d.title || 'Untitled')}</div>
          <div class="text-[10px] text-zinc-500 mt-0.5">${esc(d.discipline)} · ${fmtDate(d.drawing_date)}</div>
        </div>
      </div>`).join('');
    items.forEach(d => {
      const c = document.getElementById(`thumb-${d.id}`);
      if (c) renderThumb(c, d);
    });
  }

  function renderTable() {
    const tbody = document.getElementById('drawTableBody');
    if (!tbody) return;
    const rows = filteredDrawings();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="px-6 py-12 text-center text-zinc-500">No drawings found.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(d => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" ondblclick="CasePMDrawings.openViewer(${d.id})">
        <td class="px-4 py-3 font-mono text-sky-400">${esc(d.sheet_number)}</td>
        <td class="px-4 py-3 max-w-[280px] truncate">${esc(d.title)}</td>
        <td class="px-4 py-3 text-xs">${esc(d.discipline)}</td>
        <td class="px-4 py-3 text-xs font-mono">${esc(d.section_prefix)}</td>
        <td class="px-4 py-3 text-center text-xs">${esc(d.revision_label || '—')}</td>
        <td class="px-4 py-3 text-center text-xs">${fmtDate(d.drawing_date)}</td>
        <td class="px-4 py-3 text-center"><span class="px-2 py-0.5 rounded-full text-[10px] ${d.status === 'Current' ? 'bg-emerald-900/50 text-emerald-300' : 'bg-zinc-700 text-zinc-400'}">${esc(d.status)}</span></td>
        <td class="px-4 py-3 text-center text-xs text-zinc-500">${d.revision_count || 1}</td>
      </tr>`).join('');
  }

  function switchView(view) {
    state.view = view;
    ['sections', 'list', 'viewer'].forEach(v => {
      document.getElementById(`drawPanel${v.charAt(0).toUpperCase() + v.slice(1)}`)?.classList.toggle('hidden', v !== view);
      const btn = document.getElementById(`btnView${v.charAt(0).toUpperCase() + v.slice(1)}`);
      if (btn) {
        btn.classList.toggle('hidden', v === 'viewer' && view !== 'viewer');
        btn.classList.toggle('bg-sky-700', v === view);
        btn.classList.toggle('text-white', v === view);
        btn.classList.toggle('bg-zinc-800', v !== view);
        btn.classList.toggle('text-zinc-300', v !== view);
      }
    });
    renderActiveView();
  }

  function selectSection(sec) {
    state.activeSection = sec;
    renderSectionTabs();
    renderSectionGrid();
  }

  async function previewSheet(id) {
    const d = state.drawings.find(x => x.id === id);
    if (!d) return;
    const el = document.getElementById('drawPreviewPane');
    if (!el) return;
    el.classList.remove('hidden');
    el.innerHTML = `<div class="text-xs text-zinc-500 mb-2">Double-click to open full viewer</div>
      <div class="font-mono text-sky-400">${esc(d.sheet_number)}</div>
      <div class="text-sm font-medium mt-1">${esc(d.title)}</div>
      <div class="text-xs text-zinc-500 mt-2">${esc(d.discipline)} · ${esc(d.revision_label)} · ${fmtDate(d.drawing_date)}</div>
      <div class="text-xs text-zinc-500 mt-1">Set: ${esc(d.set_name || '—')}</div>
      <button type="button" onclick="CasePMDrawings.openViewer(${d.id})" class="mt-3 px-3 py-1.5 text-xs bg-sky-800 hover:bg-sky-700 rounded-md">Open Viewer</button>`;
  }

  async function openViewer(id) {
    const detail = await api(`/api/drawings/${id}`);
    state.openDrawing = state.drawings.find(x => x.id === id) || detail;
    state.openDetail = detail;
    state.revisions = detail.revisions || [];
    state.markups = detail.markups || [];
    state.pdfDoc = null;
    state.scale = 1;
    state.panX = 0;
    state.panY = 0;
    switchView('viewer');
    await renderPdf();
    renderMarkupOverlay();
    renderViewerSidebar();
  }

  function closeViewer() {
    state.openDrawing = null;
    state.openDetail = null;
    state.pdfDoc = null;
    switchView('sections');
  }

  function renderViewerChrome() {
    const title = document.getElementById('viewerSheetTitle');
    if (title && state.openDrawing) {
      title.textContent = `${state.openDrawing.sheet_number} — ${state.openDrawing.title || ''}`;
    }
    const revSel = document.getElementById('viewerRevisionSelect');
    if (revSel && state.revisions.length) {
      revSel.innerHTML = state.revisions.map(r =>
        `<option value="${r.id}" ${r.is_current ? 'selected' : ''}>${esc(r.revision_label)} ${r.is_current ? '(Current)' : ''} · ${fmtDate(r.uploaded_at)}</option>`
      ).join('');
    }
    highlightActiveTool();
  }

  function renderViewerSidebar() {
    const el = document.getElementById('viewerSidebar');
    if (!el || !state.openDetail) return;
    const revs = (state.revisions || []).map(r =>
      `<div class="text-xs py-1 border-b border-zinc-800 ${r.is_current ? 'text-emerald-400' : 'text-zinc-400'}">${esc(r.revision_label)} · ${fmtDate(r.uploaded_at)} ${r.is_current ? '· Current' : '· Archived'}</div>`
    ).join('') || '<div class="text-xs text-zinc-500">No revision history</div>';
    const rfis = (state.openDetail.linked_rfis || []).map(r =>
      `<a href="/rfis" class="block text-xs text-sky-400 hover:underline">${esc(r.number)} — ${esc(r.subject)}</a>`
    ).join('') || '<div class="text-xs text-zinc-500">No linked RFIs</div>';
    el.innerHTML = `
      <div class="text-xs uppercase text-zinc-500 mb-2">Revision History</div>
      <div class="mb-4 max-h-32 overflow-auto">${revs}</div>
      <div class="text-xs uppercase text-zinc-500 mb-2">Linked RFIs</div>
      <div class="mb-4">${rfis}</div>
      <div class="text-xs uppercase text-zinc-500 mb-2">Sheet Info</div>
      <div class="text-xs space-y-1 text-zinc-400">
        <div>Discipline: ${esc(state.openDetail.discipline)}</div>
        <div>Section: ${esc(state.openDetail.section_prefix)}</div>
        <div>Date: ${fmtDate(state.openDetail.drawing_date)}</div>
        <div>Set: ${esc(state.openDetail.set_name || '—')}</div>
        <div>Markups: ${state.markups.length}</div>
      </div>`;
  }

  async function renderPdf() {
    if (!state.openDrawing || !global.pdfjsLib) return;
    const canvas = document.getElementById('drawPdfCanvas');
    const wrap = document.getElementById('drawViewerWrap');
    if (!canvas || !wrap) return;
    const url = state.compareMode && state.compareRevisionId
      ? `/api/drawings/${state.openDrawing.id}/revisions/${state.compareRevisionId}/file`
      : state.openDrawing.file_url;
    const res = await fetch(url, { credentials: 'same-origin' });
    const buf = await res.arrayBuffer();
    if (state.renderTask) try { state.renderTask.cancel(); } catch {}
    state.pdfDoc = await pdfjsLib.getDocument({ data: buf.slice(0) }).promise;
    const page = await state.pdfDoc.getPage(state.pdfPage);
    const baseScale = Math.min((wrap.clientWidth - 40) / page.getViewport({ scale: 1 }).width, (wrap.clientHeight - 40) / page.getViewport({ scale: 1 }).height, 2);
    const viewport = page.getViewport({ scale: baseScale * state.scale });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext('2d');
    state.renderTask = page.render({ canvasContext: ctx, viewport });
    await state.renderTask.promise;
    const overlay = document.getElementById('drawMarkupSvg');
    if (overlay) {
      overlay.setAttribute('width', viewport.width);
      overlay.setAttribute('height', viewport.height);
      overlay.style.width = viewport.width + 'px';
      overlay.style.height = viewport.height + 'px';
    }
    renderMarkupOverlay();
  }

  function visibleMarkups() {
    return state.markups.filter(m => state.layerFilter[m.layer] !== false);
  }

  function renderMarkupOverlay() {
    const svg = document.getElementById('drawMarkupSvg');
    if (!svg) return;
    const g = state.panX || state.panY ? `transform="translate(${state.panX},${state.panY})"` : '';
    const shapes = visibleMarkups().map(m => markupSvg(m)).join('');
    svg.innerHTML = `<g ${g}>${shapes}${state.tempMarkup || ''}</g>`;
    svg.querySelectorAll('[data-rfi-pin]').forEach(el => {
      el.addEventListener('click', e => {
        e.stopPropagation();
        const rfiId = el.getAttribute('data-rfi-pin');
        if (rfiId) global.location.href = `/rfis`;
      });
    });
  }

  function markupSvg(m) {
    const geom = m.geometry || {};
    const style = m.style || {};
    const color = style.color || (m.layer === 'published' ? '#22c55e' : '#38bdf8');
    const sw = style.lineWidth || 2;
    const fill = style.fill || (m.markup_type === 'highlight' ? 'rgba(250,204,21,0.25)' : 'none');
    if (m.markup_type === 'line' || m.markup_type === 'measure') {
      const pts = geom.points || [];
      if (pts.length < 4) return '';
      const label = m.markup_type === 'measure' && m.measurement_value
        ? `<text x="${pts[2]}" y="${pts[3] - 6}" fill="${color}" font-size="11">${m.measurement_value} ${m.measurement_unit || ''}</text>` : '';
      return `<line x1="${pts[0]}" y1="${pts[1]}" x2="${pts[2]}" y2="${pts[3]}" stroke="${color}" stroke-width="${sw}" />${label}`;
    }
    if (m.markup_type === 'rect' || m.markup_type === 'highlight') {
      return `<rect x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" stroke="${color}" stroke-width="${sw}" fill="${fill}" />`;
    }
    if (m.markup_type === 'cloud') {
      const x = geom.x || 0; const y = geom.y || 0; const w = geom.w || 80; const h = geom.h || 50;
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="6 4" />`;
    }
    if (m.markup_type === 'arrow' && geom.points) {
      const p = geom.points;
      return `<line x1="${p[0]}" y1="${p[1]}" x2="${p[2]}" y2="${p[3]}" stroke="${color}" stroke-width="${sw}" marker-end="url(#arrowhead)" />`;
    }
    if (m.markup_type === 'text') {
      return `<text x="${geom.x}" y="${geom.y}" fill="${color}" font-size="13">${esc(m.label || '')}</text>`;
    }
    if (m.markup_type === 'rfi_pin') {
      const x = geom.x || 0; const y = geom.y || 0;
      return `<g data-rfi-pin="${m.linked_rfi_id || ''}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="10" fill="#f97316" stroke="#fff" stroke-width="2"/><text x="${x}" y="${y + 4}" text-anchor="middle" fill="#fff" font-size="9" font-weight="bold">R</text></g>`;
    }
    return '';
  }

  function setTool(tool) {
    state.tool = tool;
    highlightActiveTool();
  }

  function highlightActiveTool() {
    MARKUP_TOOLS.forEach(t => {
      const btn = document.getElementById(`tool-${t}`);
      if (!btn) return;
      btn.classList.toggle('bg-sky-700', state.tool === t);
      btn.classList.toggle('text-white', state.tool === t);
    });
  }

  function viewerCoords(evt) {
    const svg = document.getElementById('drawMarkupSvg');
    const rect = svg.getBoundingClientRect();
    return { x: evt.clientX - rect.left - state.panX, y: evt.clientY - rect.top - state.panY };
  }

  function bindViewerEvents() {
    const svg = document.getElementById('drawMarkupSvg');
    if (!svg || svg._bound) return;
    svg._bound = true;
    svg.addEventListener('mousedown', onViewerDown);
    svg.addEventListener('mousemove', onViewerMove);
    svg.addEventListener('mouseup', onViewerUp);
    svg.addEventListener('wheel', e => {
      if (!state.openDrawing) return;
      e.preventDefault();
      state.scale = Math.max(0.4, Math.min(4, state.scale + (e.deltaY < 0 ? 0.1 : -0.1)));
      renderPdf();
    }, { passive: false });
  }

  function onViewerDown(evt) {
    if (state.tool === 'pan') {
      state.drawing = true;
      state.drawStart = { x: evt.clientX - state.panX, y: evt.clientY - state.panY, pan: true };
      return;
    }
    if (['line', 'rect', 'cloud', 'arrow', 'highlight', 'measure'].includes(state.tool)) {
      state.drawing = true;
      state.drawStart = viewerCoords(evt);
      return;
    }
    if (state.tool === 'text') {
      const pt = viewerCoords(evt);
      const label = prompt('Text label:');
      if (label) saveMarkup({ markup_type: 'text', geometry: { x: pt.x, y: pt.y }, label });
      return;
    }
    if (state.tool === 'rfi_pin') {
      const pt = viewerCoords(evt);
      placeRfiPin(pt);
    }
    if (state.tool === 'calibrate') {
      const pt = viewerCoords(evt);
      if (!state.drawStart) { state.drawStart = pt; toast('Click second point for known distance'); return; }
      const dist = prompt('Known distance (feet):', '10');
      if (dist) {
        const dx = pt.x - state.drawStart.x; const dy = pt.y - state.drawStart.y;
        const px = Math.sqrt(dx * dx + dy * dy);
        state.pixelsPerUnit = px / (parseFloat(dist) || 1);
        toast(`Scale set: ${state.pixelsPerUnit.toFixed(2)} px/ft`);
      }
      state.drawStart = null;
    }
  }

  function onViewerMove(evt) {
    if (!state.drawing || !state.drawStart) return;
    if (state.drawStart.pan) {
      state.panX = evt.clientX - state.drawStart.x;
      state.panY = evt.clientY - state.drawStart.y;
      renderMarkupOverlay();
      return;
    }
    const pt = viewerCoords(evt);
    const s = state.drawStart;
    if (['rect', 'cloud', 'highlight'].includes(state.tool)) {
      const x = Math.min(s.x, pt.x); const y = Math.min(s.y, pt.y);
      state.tempMarkup = `<rect x="${x}" y="${y}" width="${Math.abs(pt.x - s.x)}" height="${Math.abs(pt.y - s.y)}" stroke="#38bdf8" stroke-width="2" fill="none" stroke-dasharray="4 3" />`;
    } else if (['line', 'arrow', 'measure'].includes(state.tool)) {
      state.tempMarkup = `<line x1="${s.x}" y1="${s.y}" x2="${pt.x}" y2="${pt.y}" stroke="#38bdf8" stroke-width="2" stroke-dasharray="4 3" />`;
    }
    renderMarkupOverlay();
  }

  async function onViewerUp(evt) {
    if (!state.drawing || !state.drawStart || state.drawStart.pan) {
      state.drawing = false;
      state.drawStart = null;
      state.tempMarkup = null;
      return;
    }
    const pt = viewerCoords(evt);
    const s = state.drawStart;
    const type = state.tool;
    let geometry = {};
    let measurement_value = null;
    if (['rect', 'cloud', 'highlight'].includes(type)) {
      geometry = { x: Math.min(s.x, pt.x), y: Math.min(s.y, pt.y), w: Math.abs(pt.x - s.x), h: Math.abs(pt.y - s.y) };
    } else if (['line', 'arrow', 'measure'].includes(type)) {
      geometry = { points: [s.x, s.y, pt.x, pt.y] };
      if (type === 'measure' && state.pixelsPerUnit) {
        const dx = pt.x - s.x; const dy = pt.y - s.y;
        measurement_value = Math.round((Math.sqrt(dx * dx + dy * dy) / state.pixelsPerUnit) * 100) / 100;
      }
    }
    state.drawing = false;
    state.drawStart = null;
    state.tempMarkup = null;
    if ((geometry.w === 0 && geometry.h === 0) && !geometry.points) return;
    await saveMarkup({ markup_type: type === 'measure' ? 'measure' : type, geometry, measurement_value, measurement_unit: state.measureUnit });
  }

  async function placeRfiPin(pt) {
    const opts = state.rfis.map(r => `${r.number}: ${r.subject}`).join('\n');
    const pick = prompt(`Link RFI pin to:\n${opts}\n\nEnter RFI number (e.g. RFI-001):`);
    if (!pick) return;
    const rfi = state.rfis.find(r => pick.toUpperCase().includes(r.number.toUpperCase()) || r.number.toUpperCase() === pick.toUpperCase());
    if (!rfi) { alert('RFI not found'); return; }
    await saveMarkup({
      markup_type: 'rfi_pin',
      geometry: { x: pt.x, y: pt.y },
      linked_rfi_id: rfi.id,
      label: rfi.number,
      publish: true,
    });
  }

  async function saveMarkup(payload) {
    if (!state.openDrawing) return;
    const body = {
      markup_type: payload.markup_type,
      geometry: payload.geometry,
      style: payload.style || { color: '#38bdf8', lineWidth: 2 },
      label: payload.label,
      linked_rfi_id: payload.linked_rfi_id,
      measurement_value: payload.measurement_value,
      measurement_unit: payload.measurement_unit || state.measureUnit,
      layer: payload.publish ? 'published' : 'personal',
      publish: !!payload.publish,
    };
    const json = await api(`/api/drawings/${state.openDrawing.id}/markups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    state.markups.push(json.markup);
    renderMarkupOverlay();
    renderViewerSidebar();
    toast('Markup saved');
  }

  async function publishPersonalMarkups() {
    const personal = state.markups.filter(m => m.layer === 'personal' && m.user_id);
    for (const m of personal) {
      await api(`/api/drawings/markups/${m.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ publish: true }),
      });
      m.layer = 'published';
    }
    renderMarkupOverlay();
    toast('Personal markups published');
  }

  function toggleLayer(layer) {
    state.layerFilter[layer] = !state.layerFilter[layer];
    const el = document.getElementById(`layer-${layer}`);
    if (el) el.classList.toggle('opacity-40', !state.layerFilter[layer]);
    renderMarkupOverlay();
  }

  async function loadRevisionInViewer() {
    const revId = parseInt(document.getElementById('viewerRevisionSelect')?.value, 10);
    if (!revId || !state.openDrawing) return;
    state.compareRevisionId = revId;
    state.compareMode = true;
    await renderPdf();
    toast('Viewing selected revision — toggle Compare to overlay with current');
  }

  async function toggleCompareOverlay() {
    state.compareMode = !state.compareMode;
    if (!state.compareMode) state.compareRevisionId = null;
    await renderPdf();
  }

  function printSheet() {
    window.print();
  }

  function openUploadModal(mode) {
    document.getElementById('uploadMode').value = mode || 'individual';
    document.getElementById('uploadDrawingModal')?.showModal();
  }

  function openSubstituteModal() {
    document.getElementById('substituteModal')?.showModal();
  }

  async function submitUpload(e) {
    e.preventDefault();
    const mode = document.getElementById('uploadMode').value;
    const file = document.getElementById('uploadFile').files[0];
    if (!file) { alert('Select a PDF'); return; }
    const fd = new FormData();
    fd.append('project_id', projectId());
    fd.append('file', file);
    fd.append('set_name', document.getElementById('uploadSetName').value || 'Drawing Upload');
    if (mode === 'individual') {
      const sheet = document.getElementById('uploadSheetNumber').value;
      if (sheet) fd.append('sheet_number', sheet);
      const title = document.getElementById('uploadTitle').value;
      if (title) fd.append('title', title);
    }
    const url = mode === 'set' ? '/api/drawings/upload-set' : '/api/drawings/upload';
    try {
      const res = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Upload failed');
      document.getElementById('uploadDrawingModal').close();
      toast(mode === 'set' ? `Processed ${json.created_count} sheets` : `Uploaded ${json.drawing?.sheet_number}`);
      if (json.needs_review?.length) alert(`${json.needs_review.length} page(s) need manual sheet numbers.`);
      await Promise.all([loadDashboard(), loadDrawings()]);
    } catch (err) { alert(err.message); }
  }

  async function submitSubstitute(e) {
    e.preventDefault();
    const files = document.getElementById('substituteFiles').files;
    if (!files.length) { alert('Select revised PDF page(s)'); return; }
    const fd = new FormData();
    fd.append('project_id', projectId());
    fd.append('set_name', document.getElementById('substituteSetName').value || 'Substitute Pages');
    Array.from(files).forEach(f => fd.append('files', f));
    try {
      const res = await fetch('/api/drawings/substitute', { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Substitute failed');
      document.getElementById('substituteModal').close();
      const msg = `Substituted ${json.substituted?.length || 0} sheet(s)`;
      if (json.skipped?.length) alert(`${msg}. Skipped: ${json.skipped.length}. See console.`);
      else toast(msg);
      console.log('Substitute result', json);
      await Promise.all([loadDashboard(), loadDrawings()]);
    } catch (err) { alert(err.message); }
  }

  function bindFilters() {
    ['drawSearch', 'drawDisciplineFilter', 'drawStatusFilter'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', () => renderActiveView());
    });
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-16 right-6 z-[70] px-4 py-2 rounded-md bg-emerald-900 text-emerald-100 text-sm shadow-lg';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2800);
  }

  async function init() {
    if (!projectId()) { alert('Select a project to manage drawings.'); return; }
    if (global.pdfjsLib) {
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }
    bindFilters();
    bindViewerEvents();
    await Promise.all([loadDashboard(), loadDrawings(), loadRfis()]);
  }

  global.CasePMDrawings = {
    init,
    switchView,
    selectSection,
    openViewer,
    closeViewer,
    previewSheet,
    setTool,
    toggleLayer,
    publishPersonalMarkups,
    loadRevisionInViewer,
    toggleCompareOverlay,
    printSheet,
    openUploadModal,
    openSubstituteModal,
    submitUpload,
    submitSubstitute,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
