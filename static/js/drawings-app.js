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
    compareOverlayActive: false,
    compareOpacity: 0.7,
    compareRevisionId: null,
    compareBaseRevisionId: null,
    canvasSize: { w: 0, h: 0 },
    lastViewport: null,
    focusPin: null,
    previewDrawingId: null,
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

  function renderSummary() { /* KPI bar removed */ }

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
      <div class="bg-zinc-800 border border-zinc-700 rounded-md overflow-hidden hover:border-sky-600 cursor-pointer group relative" ondblclick="CasePMDrawings.openViewer(${d.id})" onclick="CasePMDrawings.previewSheet(${d.id})">
        <button type="button" onclick="event.stopPropagation(); CasePMDrawings.deleteDrawing(${d.id})" class="absolute bottom-2 right-2 z-10 opacity-0 group-hover:opacity-100 px-2 py-1 rounded bg-red-900/90 hover:bg-red-800 text-[10px] text-red-100" title="Delete sheet"><i class="fa-solid fa-trash"></i></button>
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
      tbody.innerHTML = '<tr><td colspan="9" class="px-6 py-12 text-center text-zinc-500">No drawings found.</td></tr>';
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
        <td class="px-4 py-3 text-center">
          <button type="button" onclick="event.stopPropagation(); CasePMDrawings.deleteDrawing(${d.id})" class="px-2 py-1 rounded bg-red-900/60 hover:bg-red-800 text-[10px] text-red-100" title="Delete sheet"><i class="fa-solid fa-trash"></i></button>
        </td>
      </tr>`).join('');
  }

  function switchView(view) {
    state.view = view;
    document.getElementById('drawPage')?.classList.toggle('draw-page-viewer-active', view === 'viewer');
    ['sections', 'list', 'viewer'].forEach(v => {
      document.getElementById(`drawPanel${v.charAt(0).toUpperCase() + v.slice(1)}`)?.classList.toggle('hidden', v !== view);
      const btn = document.getElementById(`btnView${v.charAt(0).toUpperCase() + v.slice(1)}`);
      if (btn) {
        if (v === 'viewer') btn.classList.toggle('hidden', !state.openDrawing);
        btn.classList.toggle('bg-sky-700', v === view);
        btn.classList.toggle('text-white', v === view);
        btn.classList.toggle('bg-zinc-800', v !== view);
        btn.classList.toggle('text-zinc-300', v !== view);
      }
    });
    renderActiveView();
    if (view === 'viewer' && state.openDrawing) {
      requestAnimationFrame(() => renderPdf());
    }
  }

  function selectSection(sec) {
    state.activeSection = sec;
    renderSectionTabs();
    renderSectionGrid();
  }

  async function previewSheet(id) {
    const d = state.drawings.find(x => x.id === id);
    if (!d) return;
    state.previewDrawingId = id;
    const pane = document.getElementById('drawPreviewPane');
    const thumb = document.getElementById('drawPreviewThumb');
    const openBtn = document.getElementById('drawPreviewOpenBtn');
    if (pane) {
      pane.className = 'truncate text-zinc-300 min-w-0';
      pane.textContent = `${d.sheet_number} — ${d.title || 'Untitled'}`;
      pane.title = `${d.sheet_number} — ${d.title || ''} · ${d.discipline || ''}`;
    }
    if (thumb) {
      thumb.classList.remove('hidden');
      renderThumb(thumb, d);
    }
    openBtn?.classList.remove('hidden');
    document.getElementById('drawPreviewDeleteBtn')?.classList.remove('hidden');
  }

  function deletePreviewedSheet() {
    if (!state.previewDrawingId) return;
    const d = state.drawings.find(x => x.id === state.previewDrawingId);
    deleteDrawing(state.previewDrawingId, d?.sheet_number);
  }

  function deleteOpenSheet() {
    if (!state.openDrawing) return;
    deleteDrawing(state.openDrawing.id, state.openDrawing.sheet_number);
  }

  function openPreviewedSheet() {
    if (state.previewDrawingId) openViewer(state.previewDrawingId);
  }

  async function openViewer(id, opts) {
    const detail = await api(`/api/drawings/${id}`);
    state.openDrawing = state.drawings.find(x => x.id === id) || detail;
    state.openDetail = detail;
    state.revisions = detail.revisions || [];
    state.markups = detail.markups || [];
    state.pdfDoc = null;
    state.scale = 1;
    state.panX = 0;
    state.panY = 0;
    state.compareOverlayActive = false;
    state.compareBaseRevisionId = null;
    state.focusPin = opts || null;
    state.previewDrawingId = id;
    previewSheet(id);
    switchView('viewer');
    await renderPdf();
    renderViewerSidebar();
    if (opts && (opts.focusX != null || opts.focusY != null)) {
      focusOnPoint(opts.focusX, opts.focusY);
    }
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
    const rfis = (state.openDetail.linked_rfis || []).map(r => {
      const pin = (state.markups || []).find(m => m.linked_rfi_id === r.id && m.markup_type === 'rfi_pin');
      const g = pin?.geometry || {};
      const q = new URLSearchParams({ project_id: projectId(), sheet: state.openDetail.sheet_number, rfi_id: r.id });
      if (g.nx != null) q.set('x', g.nx);
      if (g.ny != null) q.set('y', g.ny);
      if (state.openDetail.id) q.set('drawing_id', state.openDetail.id);
      return `<a href="/drawings?${q.toString()}" class="block text-xs text-sky-400 hover:underline">${esc(r.number)} — ${esc(r.subject)}</a>`;
    }).join('') || '<div class="text-xs text-zinc-500">No linked RFIs</div>';
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

  function canvasDims() {
    const w = state.canvasSize.w || parseFloat(document.getElementById('drawMarkupSvg')?.getAttribute('width')) || 1;
    const h = state.canvasSize.h || parseFloat(document.getElementById('drawMarkupSvg')?.getAttribute('height')) || 1;
    return { w, h };
  }

  function normalizeGeometry(geometry) {
    const { w, h } = canvasDims();
    const geom = { ...(geometry || {}) };
    if (geom.x != null && geom.y != null && w > 0 && h > 0) {
      geom.nx = geom.nx ?? geom.x / w;
      geom.ny = geom.ny ?? geom.y / h;
      geom.canvasW = w;
      geom.canvasH = h;
    }
    if (geom.points && geom.points.length >= 4 && w > 0 && h > 0) {
      geom.npoints = geom.points.map((v, i) => (i % 2 === 0 ? v / w : v / h));
    }
    return geom;
  }

  function resolveGeom(geom) {
    if (!geom) return {};
    const { w, h } = canvasDims();
    const cw = geom.canvasW || w;
    const ch = geom.canvasH || h;
    const out = { ...geom };
    if (geom.nx != null && geom.ny != null) {
      out.x = geom.nx * w;
      out.y = geom.ny * h;
    }
    if (geom.npoints && geom.npoints.length >= 4) {
      out.points = geom.npoints.map((v, i) => (i % 2 === 0 ? v * w : v * h));
    } else if (geom.points && cw && ch && (cw !== w || ch !== h)) {
      out.points = geom.points.map((v, i) => (i % 2 === 0 ? (v / cw) * w : (v / ch) * h));
    }
    if (geom.w != null && geom.h != null && cw && ch) {
      out.w = (geom.w / cw) * w;
      out.h = (geom.h / ch) * h;
    }
    return out;
  }

  function focusOnPoint(x, y) {
    const { w, h } = canvasDims();
    if (!w || !h) return;
    const px = (x <= 1 && x >= 0) ? x * w : x;
    const py = (y <= 1 && y >= 0) ? y * h : y;
    state.scale = Math.min(2.2, Math.max(1.2, state.scale));
    state.panX = Math.round((w / 2 - px) * 0.35);
    state.panY = Math.round((h / 2 - py) * 0.35);
    renderMarkupOverlay();
    state.tempMarkup = `<circle cx="${px}" cy="${py}" r="28" fill="none" stroke="#f97316" stroke-width="3" opacity="0.9"/><circle cx="${px}" cy="${py}" r="8" fill="#f97316" opacity="0.5"/>`;
    renderMarkupOverlay();
    setTimeout(() => { state.tempMarkup = null; renderMarkupOverlay(); }, 3000);
  }

  async function fetchPdfBytes(url) {
    const res = await fetch(url, { credentials: 'same-origin' });
    return res.arrayBuffer();
  }

  async function renderPageToCanvas(pdfDoc, canvas, viewport) {
    const page = await pdfDoc.getPage(1);
    const vp = viewport || page.getViewport({ scale: 1 });
    canvas.width = vp.width;
    canvas.height = vp.height;
    await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
    return vp;
  }

  function pixelDiff(oldCtx, newCtx, width, height, opacity) {
    const oldData = oldCtx.getImageData(0, 0, width, height).data;
    const newData = newCtx.getImageData(0, 0, width, height).data;
    const out = newCtx.createImageData(width, height);
    const thr = 42;
    for (let i = 0; i < oldData.length; i += 4) {
      const og = 0.299 * oldData[i] + 0.587 * oldData[i + 1] + 0.114 * oldData[i + 2];
      const ng = 0.299 * newData[i] + 0.587 * newData[i + 1] + 0.114 * newData[i + 2];
      const oldInk = og < 235;
      const newInk = ng < 235;
      if (!oldInk && newInk) {
        out.data[i] = 30; out.data[i + 1] = 100; out.data[i + 2] = 255; out.data[i + 3] = Math.round(255 * opacity);
      } else if (oldInk && !newInk) {
        out.data[i] = 255; out.data[i + 1] = 40; out.data[i + 2] = 40; out.data[i + 3] = Math.round(255 * opacity);
      } else if (oldInk && newInk && Math.abs(og - ng) > thr) {
        out.data[i] = 180; out.data[i + 1] = 80; out.data[i + 2] = 255; out.data[i + 3] = Math.round(200 * opacity);
      } else {
        out.data[i + 3] = 0;
      }
    }
    return out;
  }

  async function renderCompareDiff() {
    const diffCanvas = document.getElementById('drawDiffCanvas');
    if (!diffCanvas || !state.compareOverlayActive || !state.compareBaseRevisionId || !state.openDrawing || !state.pdfDoc) {
      diffCanvas?.classList.add('hidden');
      return;
    }
    try {
      const oldBuf = await fetchPdfBytes(`/api/drawings/${state.openDrawing.id}/revisions/${state.compareBaseRevisionId}/file`);
      const oldDoc = await pdfjsLib.getDocument({ data: oldBuf.slice(0) }).promise;
      const vp = state.lastViewport || (await state.pdfDoc.getPage(state.pdfPage)).getViewport({ scale: 1 });
      const offOld = document.createElement('canvas');
      const offNew = document.createElement('canvas');
      await renderPageToCanvas(oldDoc, offOld, vp);
      await renderPageToCanvas(state.pdfDoc, offNew, vp);
      diffCanvas.width = vp.width;
      diffCanvas.height = vp.height;
      diffCanvas.style.width = vp.width + 'px';
      diffCanvas.style.height = vp.height + 'px';
      const diff = pixelDiff(offOld.getContext('2d'), offNew.getContext('2d'), vp.width, vp.height, state.compareOpacity);
      diffCanvas.getContext('2d').putImageData(diff, 0, 0);
      diffCanvas.classList.remove('hidden');
    } catch (e) {
      console.warn('Compare diff failed', e);
      diffCanvas.classList.add('hidden');
    }
  }

  async function renderPdf() {
    if (!state.openDrawing || !global.pdfjsLib) return;
    const canvas = document.getElementById('drawPdfCanvas');
    const wrap = document.getElementById('drawViewerWrap');
    if (!canvas || !wrap) return;
    const url = state.openDrawing.file_url;
    const buf = await fetchPdfBytes(url);
    if (state.renderTask) try { state.renderTask.cancel(); } catch {}
    state.pdfDoc = await pdfjsLib.getDocument({ data: buf.slice(0) }).promise;
    const page = await state.pdfDoc.getPage(state.pdfPage);
    const maxScale = document.fullscreenElement ? 4 : 3;
    const baseScale = Math.min((wrap.clientWidth - 16) / page.getViewport({ scale: 1 }).width, (wrap.clientHeight - 16) / page.getViewport({ scale: 1 }).height, maxScale);
    const viewport = page.getViewport({ scale: baseScale * state.scale });
    state.lastViewport = viewport;
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    state.canvasSize = { w: viewport.width, h: viewport.height };
    const ctx = canvas.getContext('2d');
    state.renderTask = page.render({ canvasContext: ctx, viewport });
    await state.renderTask.promise;
    const overlay = document.getElementById('drawMarkupSvg');
    const diffCanvas = document.getElementById('drawDiffCanvas');
    if (overlay) {
      overlay.setAttribute('width', viewport.width);
      overlay.setAttribute('height', viewport.height);
      overlay.style.width = viewport.width + 'px';
      overlay.style.height = viewport.height + 'px';
    }
    if (diffCanvas) {
      diffCanvas.style.width = viewport.width + 'px';
      diffCanvas.style.height = viewport.height + 'px';
    }
    renderMarkupOverlay();
    await renderCompareDiff();
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
        const pid = projectId();
        const sheet = state.openDrawing?.sheet_number || '';
        const nx = el.getAttribute('data-nx');
        const ny = el.getAttribute('data-ny');
        let href = `/rfis${rfiId ? `?rfi_id=${rfiId}` : ''}`;
        if (pid) href += `${href.includes('?') ? '&' : '?'}project_id=${pid}`;
        global.location.href = href;
      });
    });
  }

  function markupSvg(m) {
    const geom = resolveGeom(m.geometry || {});
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
      const nx = (m.geometry || {}).nx ?? (geom.x / (canvasDims().w || 1));
      const ny = (m.geometry || {}).ny ?? (geom.y / (canvasDims().h || 1));
      return `<g data-rfi-pin="${m.linked_rfi_id || ''}" data-nx="${nx}" data-ny="${ny}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="10" fill="#f97316" stroke="#fff" stroke-width="2"/><text x="${x}" y="${y + 4}" text-anchor="middle" fill="#fff" font-size="9" font-weight="bold">R</text><title>${esc(m.label || 'RFI')}</title></g>`;
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
    const geometry = normalizeGeometry(payload.geometry || {});
    const body = {
      markup_type: payload.markup_type,
      geometry,
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
    state.compareBaseRevisionId = revId;
    const current = state.revisions.find(r => r.is_current);
    if (current && revId === current.id) {
      state.compareOverlayActive = false;
      document.getElementById('drawDiffCanvas')?.classList.add('hidden');
      toast('Select an older revision to compare against current');
      return;
    }
    state.compareOverlayActive = true;
    document.getElementById('compareOpacity')?.classList.remove('hidden');
    document.getElementById('btnCompareOverlay')?.classList.add('bg-sky-700', 'text-white');
    await renderCompareDiff();
    toast('Compare overlay: blue = added, red = removed');
  }

  async function toggleCompareOverlay() {
    if (!state.compareBaseRevisionId) {
      const revId = parseInt(document.getElementById('viewerRevisionSelect')?.value, 10);
      if (revId) state.compareBaseRevisionId = revId;
    }
    state.compareOverlayActive = !state.compareOverlayActive;
    document.getElementById('btnCompareOverlay')?.classList.toggle('bg-sky-700', state.compareOverlayActive);
    document.getElementById('btnCompareOverlay')?.classList.toggle('text-white', state.compareOverlayActive);
    document.getElementById('compareOpacity')?.classList.toggle('hidden', !state.compareOverlayActive);
    if (state.compareOverlayActive) await renderCompareDiff();
    else document.getElementById('drawDiffCanvas')?.classList.add('hidden');
  }

  function setCompareOpacity(val) {
    state.compareOpacity = (parseInt(val, 10) || 70) / 100;
    if (state.compareOverlayActive) renderCompareDiff();
  }

  async function exportTakeoffToBudget() {
    const costCode = prompt('Cost code for takeoff lines:', '01-000');
    if (costCode === null) return;
    try {
      const json = await api('/api/drawings/export-takeoff-to-budget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId(),
          drawing_id: state.openDrawing?.id || null,
          cost_code: costCode,
        }),
      });
      toast(`Exported ${json.imported} takeoff item(s) to Budget`);
      if (confirm(`Open Budget to review ${json.imported} imported takeoff line(s)?`)) {
        global.location.href = `/budget?project_id=${projectId()}`;
      }
    } catch (e) { alert(e.message); }
  }

  async function handleDeepLink() {
    const p = new URLSearchParams(global.location.search);
    if (!p.get('drawing_id') && !p.get('sheet')) return;
    const drawingId = parseInt(p.get('drawing_id'), 10);
    const sheet = p.get('sheet');
    const x = p.get('x');
    const y = p.get('y');
    const focus = (x != null && y != null) ? { focusX: parseFloat(x), focusY: parseFloat(y), rfiId: p.get('rfi_id') } : null;
    if (drawingId) {
      await openViewer(drawingId, focus);
      return;
    }
    if (sheet) {
      try {
        const json = await api(`/api/drawings/by-sheet?project_id=${projectId()}&sheet=${encodeURIComponent(sheet)}`);
        await openViewer(json.id, focus);
      } catch { /* sheet not found */ }
    }
  }

  function togglePrintMenu() {
    document.getElementById('printMenu')?.classList.toggle('hidden');
  }

  function printSheet(withMarkups) {
    document.getElementById('printMenu')?.classList.add('hidden');
    if (!state.openDrawing) {
      alert('Open a sheet in the viewer first.');
      return;
    }
    if (state.view !== 'viewer') switchView('viewer');
    const modeClass = withMarkups ? 'printing-drawing-markup' : 'printing-drawing-clean';
    document.body.classList.add('printing-drawing-sheet', modeClass);
    const cleanup = () => document.body.classList.remove('printing-drawing-sheet', 'printing-drawing-markup', 'printing-drawing-clean');
    window.addEventListener('afterprint', cleanup, { once: true });
    setTimeout(cleanup, 4000);
    window.print();
  }

  function toggleFullscreen() {
    const el = document.getElementById('drawPanelViewer');
    if (!el) return;
    if (!document.fullscreenElement) {
      (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
    } else {
      (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    }
  }

  function onFullscreenChange() {
    const btn = document.getElementById('btnFullscreen');
    const on = !!document.fullscreenElement;
    if (btn) btn.innerHTML = on ? '<i class="fa-solid fa-compress"></i>' : '<i class="fa-solid fa-expand"></i>';
    if (state.openDrawing) setTimeout(() => renderPdf(), 100);
  }

  function openUploadModal() {
    document.getElementById('uploadDrawingModal')?.showModal();
  }

  function openSubstituteModal() {
    document.getElementById('substituteModal')?.showModal();
  }

  function showUploadResults(json) {
    const body = document.getElementById('uploadResultsBody');
    const dialog = document.getElementById('uploadResultsModal');
    if (!body || !dialog) return;
    const pages = json.pages || json.drawings || [];
    const review = json.needs_review || [];
    let html = '';
    if (json.needs_review_count > 0) {
      html += `<p class="text-amber-400 text-xs mb-3">${json.needs_review_count} page(s) imported with provisional sheet numbers — filter by <strong>For Review</strong> to assign correct numbers.</p>`;
    }
    if (pages.length) {
      html += `<table class="w-full text-xs"><thead><tr class="text-zinc-400 border-b border-zinc-700">
        <th class="text-left py-2 pr-2">Page</th><th class="text-left py-2 pr-2">Sheet #</th>
        <th class="text-left py-2 pr-2">Revision</th><th class="text-left py-2 pr-2">Date</th>
        <th class="text-left py-2">Title</th></tr></thead><tbody>`;
      html += pages.map(p => `<tr class="border-b border-zinc-800 ${p.needs_review ? 'text-amber-200' : ''}">
        <td class="py-2 pr-2">${esc(p.page || '—')}</td>
        <td class="py-2 pr-2 font-mono ${p.needs_review ? 'text-amber-300' : 'text-sky-300'}">${esc(p.sheet_number)}</td>
        <td class="py-2 pr-2">${esc(p.revision_label || p.revision_number || '—')}</td>
        <td class="py-2 pr-2">${esc(p.drawing_date ? fmtDate(p.drawing_date) : '—')}</td>
        <td class="py-2 truncate max-w-[180px]">${esc(p.title || '—')}</td></tr>`).join('');
      html += '</tbody></table>';
    }
    if (review.length && !pages.length) {
      html += `<p class="text-amber-400 text-xs mt-3 mb-1">${review.length} page(s) could not be matched to a sheet number:</p>
        <ul class="text-xs text-zinc-400 list-disc pl-4">${review.map(r => `<li>Page ${esc(r.page)} → ${esc(r.assigned_sheet || 'skipped')}${r.detected_revision ? ` (rev ${esc(r.detected_revision)} detected)` : ''}</li>`).join('')}</ul>`;
    }
    body.innerHTML = html || '<p class="text-zinc-400 text-sm">No pages imported.</p>';
    dialog.showModal();
  }

  async function deleteDrawing(id, sheetLabel) {
    const d = state.drawings.find(x => x.id === id);
    const label = sheetLabel || d?.sheet_number || 'this sheet';
    if (!confirm(`Delete ${label} and all of its revisions? This cannot be undone.`)) return;
    try {
      await api(`/api/drawings/${id}`, { method: 'DELETE' });
      if (state.openDrawing?.id === id) closeViewer();
      if (state.previewDrawingId === id) {
        state.previewDrawingId = null;
        const pane = document.getElementById('drawPreviewPane');
        if (pane) {
          pane.textContent = 'Sheet preview — click a thumbnail';
          pane.className = 'truncate text-zinc-500 min-w-0';
        }
        document.getElementById('drawPreviewThumb')?.classList.add('hidden');
        document.getElementById('drawPreviewOpenBtn')?.classList.add('hidden');
        document.getElementById('drawPreviewDeleteBtn')?.classList.add('hidden');
      }
      toast(`Deleted ${label}`);
      await Promise.all([loadDashboard(), loadDrawings()]);
    } catch (err) { alert(err.message); }
  }

  async function submitUpload(e) {
    e.preventDefault();
    const file = document.getElementById('uploadFile').files[0];
    if (!file) { alert('Select a PDF'); return; }
    const submitBtn = e.target.querySelector('button[type="submit"]');
    const origLabel = submitBtn?.textContent;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Processing…';
    }
    const fd = new FormData();
    fd.append('project_id', projectId());
    fd.append('file', file);
    fd.append('set_name', document.getElementById('uploadSetName').value || 'Drawing Upload');
    const sheet = document.getElementById('uploadSheetNumber').value;
    if (sheet) fd.append('sheet_number', sheet);
    const title = document.getElementById('uploadTitle').value;
    if (title) fd.append('title', title);
    try {
      const res = await fetch('/api/drawings/upload', { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = json.needs_review?.length
          ? `\n\n${json.needs_review.length} page(s) listed for review.`
          : '';
        throw new Error((json.error || 'Upload failed') + detail);
      }
      document.getElementById('uploadDrawingModal').close();
      const count = json.created_count || json.drawings?.length || 1;
      const reviewNote = json.needs_review_count ? ` (${json.needs_review_count} need sheet numbers)` : '';
      toast(json.split ? `Imported ${count} sheets from drawing set${reviewNote}` : `Uploaded ${json.drawing?.sheet_number || count + ' sheet(s)'}`);
      showUploadResults(json);
      await Promise.all([loadDashboard(), loadDrawings()]);
    } catch (err) {
      alert(err.message);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = origLabel || 'Upload';
      }
    }
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
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('click', e => {
      if (!e.target.closest('#printMenu') && !e.target.closest('#btnPrintMenu')) {
        document.getElementById('printMenu')?.classList.add('hidden');
      }
    });
    await Promise.all([loadDashboard(), loadDrawings(), loadRfis()]);
    await handleDeepLink();
  }

  global.CasePMDrawings = {
    init,
    switchView,
    selectSection,
    openViewer,
    closeViewer,
    previewSheet,
    openPreviewedSheet,
    setTool,
    toggleLayer,
    publishPersonalMarkups,
    loadRevisionInViewer,
    toggleCompareOverlay,
    setCompareOpacity,
    exportTakeoffToBudget,
    togglePrintMenu,
    printSheet,
    toggleFullscreen,
    openUploadModal,
    openSubstituteModal,
    submitUpload,
    submitSubstitute,
    deleteDrawing,
    deletePreviewedSheet,
    deleteOpenSheet,
    showUploadResults,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
