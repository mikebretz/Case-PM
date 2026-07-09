/**
 * Case PM — Drawings module (Procore / Bluebeam / ACC / Fieldwire parity)
 */
(function (global) {
  'use strict';

  const SECTION_ORDER = ['G', 'C', 'A', 'S', 'M', 'E', 'P', 'FP', 'L', 'T', 'I', 'OTHER'];
  const MARKUP_TOOLS = ['pan', 'select', 'line', 'rect', 'ellipse', 'cloud', 'arrow', 'text', 'callout', 'highlight', 'measure', 'rfi_pin', 'calibrate'];

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
    viewScale: 1,
    panX: 0,
    panY: 0,
    baseCanvasSize: { w: 0, h: 0 },
    pdfBytes: null,
    pdfUrl: null,
    renderGen: 0,
    isPanning: false,
    panAnchor: null,
    selectedMarkupId: null,
    draggingMarkup: null,
    dragStartPt: null,
    dragOrigGeom: null,
    markupStyle: { color: '#38bdf8', lineWidth: 2, opacity: 1, fillOpacity: 0.25, cloudScallop: 18, fontSize: 14 },
    thumbQueue: [],
    thumbBusy: false,
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
    wheelRaf: null,
    wheelPending: null,
    textEditorOpen: false,
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
    if (!res.ok) {
      const err = new Error(json.error || json.message || 'Request failed');
      err.status = res.status;
      throw err;
    }
    return json;
  }

  async function reloadMarkups() {
    if (!state.openDrawing) return;
    try {
      const detail = await api(`/api/drawings/${state.openDrawing.id}`);
      state.markups = detail.markups || [];
      state.selectedMarkupId = null;
      state.draggingMarkup = null;
      renderMarkupOverlay();
    } catch (e) { console.warn('reloadMarkups', e); }
  }

  async function persistMarkup(m, payload) {
    if (!m?.id) return;
    try {
      const json = await api(`/api/drawings/markups/${m.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (json.markup) {
        const idx = state.markups.findIndex(x => x.id === m.id);
        if (idx >= 0) state.markups[idx] = json.markup;
      }
    } catch (e) {
      if (e.status === 404) {
        state.markups = state.markups.filter(x => x.id !== m.id);
        state.selectedMarkupId = null;
        toast('Markup was removed — refreshed list');
      } else {
        console.warn(e);
      }
    }
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

  async function renderThumbJob(canvas, drawing) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const drawPlaceholder = (label) => {
      canvas.width = 160;
      canvas.height = 120;
      ctx.fillStyle = '#27272a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#71717a';
      ctx.font = '11px sans-serif';
      ctx.fillText(label || drawing.sheet_number, 8, 20);
    };
    if (drawing.has_thumbnail && drawing.thumbnail_url) {
      try {
        const res = await fetch(drawing.thumbnail_url, { credentials: 'same-origin' });
        if (res.ok && res.headers.get('content-type')?.includes('image')) {
          const blob = await res.blob();
          const img = await createImageBitmap(blob);
          canvas.width = img.width;
          canvas.height = img.height;
          ctx.drawImage(img, 0, 0);
          return;
        }
      } catch { /* fall through to PDF */ }
    }
    if (!global.pdfjsLib || !drawing.file_url) {
      drawPlaceholder(drawing.sheet_number);
      return;
    }
    try {
      const res = await fetch(drawing.file_url, { credentials: 'same-origin' });
      const buf = await res.arrayBuffer();
      const pdf = await pdfjsLib.getDocument({ data: buf.slice(0) }).promise;
      const page = await pdf.getPage(1);
      const viewport = page.getViewport({ scale: 0.2, rotation: page.rotate });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: ctx, viewport }).promise;
    } catch {
      drawPlaceholder(drawing.sheet_number);
    }
  }

  function renderThumb(canvas, drawing) {
    state.thumbQueue.push({ canvas, drawing });
    pumpThumbQueue();
  }

  function pumpThumbQueue() {
    if (state.thumbBusy || !state.thumbQueue.length) return;
    state.thumbBusy = true;
    const job = state.thumbQueue.shift();
    renderThumbJob(job.canvas, job.drawing).finally(() => {
      state.thumbBusy = false;
      if (state.thumbQueue.length) requestAnimationFrame(pumpThumbQueue);
    });
  }

  const SECTION_GRID_CLASS = 'flex-1 overflow-auto p-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2 content-start min-h-0';

  function renderSectionGrid() {
    const grid = document.getElementById('drawSectionGrid');
    if (!grid) return;
    const items = (state.sections[state.activeSection] || []).filter(d => filteredDrawings().some(f => f.id === d.id));
    if (!items.length) {
      grid.className = 'flex-1 overflow-auto p-3 flex flex-col min-h-0';
      grid.innerHTML = `<div id="drawDropZone" class="flex-1 w-full min-h-[240px] flex flex-col items-center justify-center text-center border-2 border-dashed border-zinc-700 rounded-lg text-zinc-500 transition-colors">
        <i class="fa-solid fa-cloud-arrow-up text-2xl mb-2 block text-zinc-600"></i>
        <div class="text-sm">Drop a full drawing set PDF here</div>
        <div class="text-xs mt-1 text-zinc-600">or use Upload — pages are split automatically</div>
      </div>`;
      return;
    }
    grid.className = SECTION_GRID_CLASS;
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
    state.pdfBytes = null;
    state.pdfUrl = null;
    state.viewScale = 1;
    state.panX = 0;
    state.panY = 0;
    state.selectedMarkupId = null;
    state.compareOverlayActive = false;
    state.compareBaseRevisionId = null;
    state.focusPin = opts || null;
    state.previewDrawingId = id;
    previewSheet(id);
    switchView('viewer');
    updateViewerCursor();
    renderPropertiesPanel();
    await renderPdf(true);
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
    const w = state.baseCanvasSize.w || parseFloat(document.getElementById('drawMarkupSvg')?.getAttribute('width')) || 1;
    const h = state.baseCanvasSize.h || parseFloat(document.getElementById('drawMarkupSvg')?.getAttribute('height')) || 1;
    return { w, h };
  }

  function normalizeGeometry(geometry) {
    const { w, h } = canvasDims();
    const geom = { ...(geometry || {}) };
    if (!w || !h) return geom;
    geom.canvasW = w;
    geom.canvasH = h;
    if (geom.x != null && geom.y != null) {
      geom.nx = geom.nx ?? geom.x / w;
      geom.ny = geom.ny ?? geom.y / h;
    }
    if (geom.w != null && geom.h != null) {
      geom.nw = geom.nw ?? geom.w / w;
      geom.nh = geom.nh ?? geom.h / h;
    }
    if (geom.tipX != null && geom.tipY != null) {
      geom.ntipX = geom.ntipX ?? geom.tipX / w;
      geom.ntipY = geom.ntipY ?? geom.tipY / h;
    }
    if (geom.points && geom.points.length >= 4) {
      geom.npoints = geom.npoints ?? geom.points.map((v, i) => (i % 2 === 0 ? v / w : v / h));
    }
    return geom;
  }

  function resolveGeom(geom) {
    if (!geom) return {};
    const { w, h } = canvasDims();
    const out = { ...geom };
    if (geom.nx != null) out.x = geom.nx * w;
    if (geom.ny != null) out.y = geom.ny * h;
    if (geom.nw != null) out.w = geom.nw * w;
    if (geom.nh != null) out.h = geom.nh * h;
    if (geom.ntipX != null) out.tipX = geom.ntipX * w;
    if (geom.ntipY != null) out.tipY = geom.ntipY * h;
    if (geom.tipX != null && geom.canvasW && geom.canvasW !== w) {
      out.tipX = (geom.tipX / geom.canvasW) * w;
      out.tipY = (geom.tipY / geom.canvasH) * h;
    }
    if (geom.npoints && geom.npoints.length >= 4) {
      out.points = geom.npoints.map((v, i) => (i % 2 === 0 ? v * w : v * h));
    } else if (geom.points && geom.canvasW && geom.canvasH && (geom.canvasW !== w || geom.canvasH !== h)) {
      out.points = geom.points.map((v, i) => (i % 2 === 0 ? (v / geom.canvasW) * w : (v / geom.canvasH) * h));
    } else if (geom.points) {
      out.points = geom.points.slice();
    }
    if (geom.w != null && geom.h != null && geom.canvasW && geom.canvasH) {
      out.w = (geom.w / geom.canvasW) * w;
      out.h = (geom.h / geom.canvasH) * h;
    }
    return out;
  }

  function translateGeometry(geom, dx, dy) {
    const { w, h } = canvasDims();
    const g = JSON.parse(JSON.stringify(geom || {}));
    const ndx = w ? dx / w : 0;
    const ndy = h ? dy / h : 0;
    if (g.npoints && g.npoints.length >= 4) {
      g.npoints = g.npoints.map((v, i) => v + (i % 2 === 0 ? ndx : ndy));
    } else if (g.points && g.points.length >= 4) {
      g.points = g.points.map((v, i) => v + (i % 2 === 0 ? dx : dy));
      if (w && h) g.npoints = g.points.map((v, i) => (i % 2 === 0 ? v / w : v / h));
    }
    if (g.nx != null) g.nx += ndx;
    if (g.ny != null) g.ny += ndy;
    if (g.ntipX != null) g.ntipX += ndx;
    if (g.ntipY != null) g.ntipY += ndy;
    if (g.x != null) g.x += dx;
    if (g.y != null) g.y += dy;
    if (w && h) {
      g.canvasW = w;
      g.canvasH = h;
    }
    return g;
  }

  function applyViewTransform() {
    const stage = document.getElementById('drawViewerStage');
    if (!stage) return;
    stage.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.viewScale})`;
  }

  function fitToView() {
    const wrap = document.getElementById('drawViewerWrap');
    const { w, h } = state.baseCanvasSize;
    if (!wrap || !w || !h) return;
    const pad = 24;
    const sx = (wrap.clientWidth - pad) / w;
    const sy = (wrap.clientHeight - pad) / h;
    state.viewScale = Math.max(0.15, Math.min(sx, sy, 4));
    state.panX = Math.max(0, (wrap.clientWidth - w * state.viewScale) / 2);
    state.panY = Math.max(0, (wrap.clientHeight - h * state.viewScale) / 2);
    applyViewTransform();
  }

  function screenToDoc(evt) {
    const wrap = document.getElementById('drawViewerWrap');
    const rect = wrap.getBoundingClientRect();
    const sx = evt.clientX - rect.left;
    const sy = evt.clientY - rect.top;
    return {
      x: (sx - state.panX) / state.viewScale,
      y: (sy - state.panY) / state.viewScale,
    };
  }

  function revisionCloudPath(x, y, w, h, scallopRadius) {
    const r = Math.max(6, Math.min(scallopRadius || state.markupStyle.cloudScallop || 18, w / 4, h / 4));
    if (w < r * 2 || h < r * 2) {
      return `M ${x} ${y} L ${x + w} ${y} L ${x + w} ${y + h} L ${x} ${y + h} Z`;
    }

    function scallopEdge(x1, y1, x2, y2, ox, oy) {
      const len = Math.hypot(x2 - x1, y2 - y1);
      if (len < 1) return '';
      const ux = (x2 - x1) / len;
      const uy = (y2 - y1) / len;
      let d = '';
      let dist = 0;
      let cx = x1;
      let cy = y1;
      while (dist + 0.25 < len) {
        const step = Math.min(r * 2, len - dist);
        const mx = cx + ux * step * 0.5;
        const my = cy + uy * step * 0.5;
        const ex = cx + ux * step;
        const ey = cy + uy * step;
        d += ` Q ${mx + ox * r} ${my + oy * r} ${ex} ${ey}`;
        cx = ex;
        cy = ey;
        dist += step;
      }
      return d;
    }

    let d = `M ${x} ${y + h}`;
    d += scallopEdge(x, y + h, x, y, -1, 0);
    d += scallopEdge(x, y, x + w, y, 0, -1);
    d += scallopEdge(x + w, y, x + w, y + h, 1, 0);
    d += scallopEdge(x + w, y + h, x, y + h, 0, 1);
    return d + ' Z';
  }

  function cloudPath(x, y, w, h, scallopRadius) {
    return revisionCloudPath(x, y, w, h, scallopRadius);
  }

  function distToSegment(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len2 = dx * dx + dy * dy;
    if (!len2) return Math.hypot(px - x1, py - y1);
    let t = ((px - x1) * dx + (py - y1) * dy) / len2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  function hitTestMarkup(pt) {
    const tol = Math.max(18, 14 / state.viewScale);
    let best = null;
    let bestDist = tol;
    visibleMarkups().forEach(m => {
      const g = resolveGeom(m.geometry || {});
      let d = Infinity;
      if (m.markup_type === 'rfi_pin') {
        d = Math.hypot(pt.x - (g.x || 0), pt.y - (g.y || 0));
      } else if (['rect', 'cloud', 'highlight'].includes(m.markup_type)) {
        const inside = pt.x >= g.x && pt.x <= g.x + g.w && pt.y >= g.y && pt.y <= g.y + g.h;
        d = inside ? 0 : Math.min(
          Math.abs(pt.x - g.x), Math.abs(pt.x - (g.x + g.w)),
          Math.abs(pt.y - g.y), Math.abs(pt.y - (g.y + g.h))
        );
      } else if (m.markup_type === 'ellipse' && g.w && g.h) {
        const cx = g.x + g.w / 2;
        const cy = g.y + g.h / 2;
        const rx = Math.max(g.w / 2, 1);
        const ry = Math.max(g.h / 2, 1);
        const nx = (pt.x - cx) / rx;
        const ny = (pt.y - cy) / ry;
        d = Math.abs(nx * nx + ny * ny - 1) * Math.min(rx, ry);
      } else if (m.markup_type === 'callout' && g.points && g.points.length >= 4) {
        const bx = Math.min(g.points[0], g.points[2]);
        const by = Math.min(g.points[1], g.points[3]);
        const bw = Math.abs(g.points[2] - g.points[0]);
        const bh = Math.abs(g.points[3] - g.points[1]);
        const inside = pt.x >= bx && pt.x <= bx + bw && pt.y >= by && pt.y <= by + bh;
        d = inside ? 0 : distToSegment(pt.x, pt.y, g.tipX ?? g.points[0], g.tipY ?? g.points[3], bx + bw / 2, by + bh);
      } else if ((m.markup_type === 'text' || m.markup_type === 'textbox') && g.x != null) {
        const inside = pt.x >= g.x && pt.x <= g.x + (g.w || 180) && pt.y >= g.y && pt.y <= g.y + (g.h || 28);
        d = inside ? 0 : Math.hypot(pt.x - g.x, pt.y - g.y);
      } else if (g.points && g.points.length >= 4) {
        d = distToSegment(pt.x, pt.y, g.points[0], g.points[1], g.points[2], g.points[3]);
      } else if (g.x != null && g.y != null) {
        d = Math.hypot(pt.x - g.x, pt.y - g.y);
      }
      if (d <= bestDist) {
        bestDist = d;
        best = m;
      }
    });
    return best;
  }

  function focusOnPoint(x, y) {
    const { w, h } = canvasDims();
    if (!w || !h) return;
    const px = (x <= 1 && x >= 0) ? x * w : x;
    const py = (y <= 1 && y >= 0) ? y * h : y;
    const wrap = document.getElementById('drawViewerWrap');
    if (!wrap) return;
    state.viewScale = Math.min(2.5, Math.max(1, state.viewScale));
    state.panX = wrap.clientWidth / 2 - px * state.viewScale;
    state.panY = wrap.clientHeight / 2 - py * state.viewScale;
    applyViewTransform();
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
    const vp = viewport || page.getViewport({ scale: 1, rotation: page.rotate });
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
      const vp = state.lastViewport || (await state.pdfDoc.getPage(state.pdfPage)).getViewport({ scale: 1, rotation: (await state.pdfDoc.getPage(state.pdfPage)).rotate });
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

  async function renderPdf(forceReload) {
    if (!state.openDrawing || !global.pdfjsLib) return;
    const canvas = document.getElementById('drawPdfCanvas');
    const wrap = document.getElementById('drawViewerWrap');
    if (!canvas || !wrap) return;

    const url = state.openDrawing.file_url;
    const gen = ++state.renderGen;

    if (forceReload || !state.pdfDoc || state.pdfUrl !== url) {
      if (state.renderTask) {
        try { await state.renderTask.cancel(); } catch { /* cancelled */ }
        state.renderTask = null;
      }
      state.pdfUrl = url;
      const buf = await fetchPdfBytes(url);
      if (gen !== state.renderGen) return;
      state.pdfBytes = buf;
      state.pdfDoc = await pdfjsLib.getDocument({ data: buf.slice(0) }).promise;
    }

    const page = await state.pdfDoc.getPage(state.pdfPage);
    const unscaled = page.getViewport({ scale: 1, rotation: page.rotate });
    const fitScale = Math.min(
      (wrap.clientWidth - 32) / unscaled.width,
      (wrap.clientHeight - 32) / unscaled.height,
      2.5
    );
    const viewport = page.getViewport({ scale: Math.max(0.5, fitScale), rotation: page.rotate });
    if (gen !== state.renderGen) return;

    state.lastViewport = viewport;
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    state.baseCanvasSize = { w: viewport.width, h: viewport.height };

    const ctx = canvas.getContext('2d');
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (state.renderTask) {
      try { await state.renderTask.cancel(); } catch { /* cancelled */ }
    }
    state.renderTask = page.render({ canvasContext: ctx, viewport });
    try {
      await state.renderTask.promise;
    } catch (err) {
      if (err?.name === 'RenderingCancelledException') return;
      console.warn('PDF render failed', err);
      return;
    }
    if (gen !== state.renderGen) return;
    state.renderTask = null;

    const overlay = document.getElementById('drawMarkupSvg');
    const diffCanvas = document.getElementById('drawDiffCanvas');
    if (overlay) {
      overlay.setAttribute('width', viewport.width);
      overlay.setAttribute('height', viewport.height);
      overlay.style.width = viewport.width + 'px';
      overlay.style.height = viewport.height + 'px';
    }
    if (diffCanvas) {
      diffCanvas.width = viewport.width;
      diffCanvas.height = viewport.height;
      diffCanvas.style.width = viewport.width + 'px';
      diffCanvas.style.height = viewport.height + 'px';
    }
    fitToView();
    renderMarkupOverlay();
    await renderCompareDiff();
  }

  function visibleMarkups() {
    return state.markups.filter(m => state.layerFilter[m.layer] !== false);
  }

  function renderMarkupOverlay() {
    const svg = document.getElementById('drawMarkupSvg');
    if (!svg) return;
    const shapes = visibleMarkups().map(m => markupSvg(m)).join('');
    svg.innerHTML = `<defs>
      <marker id="arrowhead" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
        <polygon points="0 0, 10 5, 0 10" fill="context-stroke"/>
      </marker>
    </defs>${shapes}${state.tempMarkup || ''}`;
    svg.querySelectorAll('[data-rfi-pin]').forEach(el => {
      el.addEventListener('click', e => {
        e.stopPropagation();
        const rfiId = el.getAttribute('data-rfi-pin');
        const pid = projectId();
        let href = `/rfis${rfiId ? `?rfi_id=${rfiId}` : ''}`;
        if (pid) href += `${href.includes('?') ? '&' : '?'}project_id=${pid}`;
        global.location.href = href;
      });
    });
    svg.querySelectorAll('[data-markup-id]').forEach(el => {
      el.addEventListener('click', e => {
        e.stopPropagation();
        if (state.tool !== 'select') return;
        state.selectedMarkupId = parseInt(el.getAttribute('data-markup-id'), 10);
        renderMarkupOverlay();
        updateMarkupToolbar();
      });
    });
    updateMarkupToolbar();
    renderPropertiesPanel();
  }

  function markupSvg(m) {
    const geom = resolveGeom(m.geometry || {});
    const style = m.style || {};
    const color = style.color || (m.layer === 'published' ? '#22c55e' : '#38bdf8');
    const sw = style.lineWidth || 2;
    const op = style.opacity != null ? style.opacity : 1;
    const fillOp = style.fillOpacity != null ? style.fillOpacity : 0.25;
    const fill = style.fill || (m.markup_type === 'highlight' ? `rgba(250,204,21,${fillOp})` : 'none');
    const selected = state.selectedMarkupId === m.id;
    const selStroke = selected ? '#fbbf24' : color;
    const selSw = selected ? sw + 2 : sw;
    const scallop = style.cloudScallop || state.markupStyle.cloudScallop || 18;
    const id = m.id;
    let hit = '';
    let visual = '';

    if (m.markup_type === 'line' || m.markup_type === 'measure') {
      const pts = geom.points || [];
      if (pts.length < 4) return '';
      hit = `<line data-markup-id="${id}" x1="${pts[0]}" y1="${pts[1]}" x2="${pts[2]}" y2="${pts[3]}" stroke="transparent" stroke-width="22" pointer-events="stroke"/>`;
      const label = m.markup_type === 'measure' && m.measurement_value != null
        ? `<text x="${pts[2]}" y="${pts[3] - 8}" fill="${selStroke}" font-size="12" font-weight="bold">${m.measurement_value} ${m.measurement_unit || ''}</text>` : '';
      visual = `<line x1="${pts[0]}" y1="${pts[1]}" x2="${pts[2]}" y2="${pts[3]}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}" pointer-events="none"/>${label}`;
    } else if (m.markup_type === 'rect' || m.markup_type === 'highlight') {
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" fill="transparent" pointer-events="all"/>`;
      visual = `<rect x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" stroke="${selStroke}" stroke-width="${selSw}" fill="${fill}" opacity="${op}" pointer-events="none"/>`;
    } else if (m.markup_type === 'cloud') {
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" fill="transparent" pointer-events="all"/>`;
      visual = `<path d="${revisionCloudPath(geom.x, geom.y, geom.w, geom.h, scallop)}" stroke="${selStroke}" stroke-width="${selSw}" fill="none" opacity="${op}" pointer-events="none"/>`;
    } else if (m.markup_type === 'arrow' && geom.points) {
      const p = geom.points;
      hit = `<line data-markup-id="${id}" x1="${p[0]}" y1="${p[1]}" x2="${p[2]}" y2="${p[3]}" stroke="transparent" stroke-width="22" pointer-events="stroke"/>`;
      visual = `<line x1="${p[0]}" y1="${p[1]}" x2="${p[2]}" y2="${p[3]}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}" marker-end="url(#arrowhead)" pointer-events="none"/>`;
    } else if (m.markup_type === 'ellipse') {
      hit = `<ellipse data-markup-id="${id}" cx="${geom.x + geom.w / 2}" cy="${geom.y + geom.h / 2}" rx="${geom.w / 2}" ry="${geom.h / 2}" fill="transparent" pointer-events="all"/>`;
      visual = `<ellipse cx="${geom.x + geom.w / 2}" cy="${geom.y + geom.h / 2}" rx="${geom.w / 2}" ry="${geom.h / 2}" stroke="${selStroke}" stroke-width="${selSw}" fill="${fill}" opacity="${op}" pointer-events="none"/>`;
    } else if (m.markup_type === 'callout' && geom.points) {
      const p = geom.points;
      const bx = Math.min(p[0], p[2]);
      const by = Math.min(p[1], p[3]);
      const bw = Math.abs(p[2] - p[0]);
      const bh = Math.abs(p[3] - p[1]);
      const tipX = geom.tipX != null ? geom.tipX : p[0];
      const tipY = geom.tipY != null ? geom.tipY : p[3];
      hit = `<rect data-markup-id="${id}" x="${bx}" y="${by}" width="${bw}" height="${bh}" fill="transparent" pointer-events="all"/>`;
      visual = `<line x1="${tipX}" y1="${tipY}" x2="${bx + bw / 2}" y2="${by + bh}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}" pointer-events="none"/>
        <rect x="${bx}" y="${by}" width="${bw}" height="${bh}" stroke="${selStroke}" stroke-width="${selSw}" fill="rgba(24,24,27,0.85)" opacity="${op}" pointer-events="none"/>
        <text x="${bx + 8}" y="${by + 20}" fill="${selStroke}" font-size="${style.fontSize || 13}" pointer-events="none">${esc(m.label || '')}</text>`;
    } else if (m.markup_type === 'text' || m.markup_type === 'textbox') {
      const tw = geom.w || 180;
      const th = geom.h || 28;
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${tw}" height="${th}" fill="transparent" pointer-events="all"/>`;
      const bg = style.fillOpacity != null ? `rgba(24,24,27,${style.fillOpacity})` : 'rgba(24,24,27,0.75)';
      visual = `<rect x="${geom.x}" y="${geom.y}" width="${tw}" height="${th}" fill="${bg}" stroke="${selStroke}" stroke-width="${selected ? 2 : 1}" opacity="${op}" pointer-events="none"/>
        <text x="${geom.x + 6}" y="${geom.y + (style.fontSize || 14) + 4}" fill="${selStroke}" font-size="${style.fontSize || 14}" opacity="${op}" pointer-events="none">${esc(m.label || '')}</text>`;
    } else if (m.markup_type === 'rfi_pin') {
      const x = geom.x || 0; const y = geom.y || 0;
      return `<g data-rfi-pin="${m.linked_rfi_id || ''}" data-markup-id="${id}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="14" fill="transparent"/><circle cx="${x}" cy="${y}" r="10" fill="#f97316" stroke="#fff" stroke-width="2"/><text x="${x}" y="${y + 4}" text-anchor="middle" fill="#fff" font-size="9" font-weight="bold" pointer-events="none">R</text><title>${esc(m.label || 'RFI')}</title></g>`;
    } else {
      return '';
    }
    return `<g class="markup-item${selected ? ' markup-selected' : ''}">${hit}${visual}</g>`;
  }

  function activeMarkupContext() {
    if (state.selectedMarkupId) {
      return state.markups.find(m => m.id === state.selectedMarkupId) || null;
    }
    return { markup_type: state.tool, style: { ...state.markupStyle } };
  }

  function propChips(label, options, current, dataAttr) {
    return `<label class="block text-[10px] text-zinc-400 mb-1">${esc(label)}</label>
      <div class="flex flex-wrap gap-1 mb-2">${options.map(o => {
        const active = String(o.value) === String(current);
        return `<button type="button" class="prop-chip px-2 py-1 rounded text-[10px] border ${active ? 'bg-sky-700 border-sky-500 text-white' : 'bg-zinc-800 border-zinc-700 text-zinc-300'}" data-prop="${dataAttr}" data-value="${o.value}">${esc(o.label)}</button>`;
      }).join('')}</div>`;
  }

  const COLOR_PRESETS = [
    { label: 'Blue', value: '#38bdf8' }, { label: 'Red', value: '#ef4444' },
    { label: 'Green', value: '#22c55e' }, { label: 'Yellow', value: '#facc15' },
    { label: 'Orange', value: '#f97316' }, { label: 'White', value: '#f4f4f5' },
  ];
  const WIDTH_PRESETS = [
    { label: 'Hairline', value: 1 }, { label: 'Thin', value: 2 }, { label: 'Medium', value: 4 },
    { label: 'Thick', value: 6 }, { label: 'Heavy', value: 10 },
  ];
  const OPACITY_PRESETS = [
    { label: '100%', value: 1 }, { label: '75%', value: 0.75 }, { label: '50%', value: 0.5 }, { label: '25%', value: 0.25 },
  ];
  const CLOUD_PRESETS = [
    { label: 'Tight', value: 10 }, { label: 'Standard', value: 18 }, { label: 'Large', value: 28 }, { label: 'XL', value: 36 },
  ];
  const FONT_PRESETS = [
    { label: '10', value: 10 }, { label: '12', value: 12 }, { label: '14', value: 14 },
    { label: '18', value: 18 }, { label: '24', value: 24 }, { label: '32', value: 32 },
  ];

  function renderPropertiesPanel() {
    const el = document.getElementById('markupPropertiesPanel');
    if (!el) return;
    const ctx = activeMarkupContext();
    const type = ctx?.markup_type || state.tool;
    const style = ctx?.style || state.markupStyle;
    const isSelected = !!state.selectedMarkupId;
    const title = isSelected ? `Selected: ${type}` : `Tool: ${type}`;
    const showCloud = type === 'cloud';
    const showLine = ['line', 'arrow', 'rect', 'ellipse', 'cloud', 'measure', 'highlight', 'callout'].includes(type);
    const showText = type === 'text' || type === 'textbox' || type === 'callout';
    const showMeasure = type === 'measure' || (isSelected && ctx?.markup_type === 'measure');
    const showFill = ['rect', 'highlight', 'ellipse', 'text', 'textbox'].includes(type);

    el.innerHTML = `
      <div class="text-[10px] uppercase text-zinc-500 mb-2">${esc(title)}</div>
      ${showLine ? propChips('Color', COLOR_PRESETS, style.color || '#38bdf8', 'color') : ''}
      ${showLine ? propChips('Line weight', WIDTH_PRESETS, style.lineWidth || 2, 'lineWidth') : ''}
      ${showLine ? propChips('Opacity', OPACITY_PRESETS, style.opacity ?? 1, 'opacity') : ''}
      ${showFill ? propChips('Fill', OPACITY_PRESETS, style.fillOpacity ?? (type === 'highlight' ? 0.25 : 0.75), 'fillOpacity') : ''}
      ${showCloud ? propChips('Cloud size', CLOUD_PRESETS, style.cloudScallop || 18, 'cloudScallop') : ''}
      ${showText ? propChips('Font size', FONT_PRESETS, style.fontSize || 14, 'fontSize') : ''}
      ${isSelected && showText ? `
        <label class="block text-[10px] text-zinc-400 mb-1">Text</label>
        <textarea id="propTextLabel" rows="3" class="w-full bg-zinc-900 border border-zinc-700 rounded p-2 text-xs mb-2">${esc(ctx.label || '')}</textarea>
      ` : ''}
      ${showMeasure ? `
        <div class="text-[10px] text-zinc-400 mb-2 p-2 bg-zinc-900 rounded border border-zinc-700">
          Scale: ${state.pixelsPerUnit ? `${state.pixelsPerUnit.toFixed(2)} px/${state.measureUnit}` : 'Not calibrated — measurements show in pixels'}
        </div>
        <button type="button" id="propCalibrateBtn" class="w-full py-1.5 mb-2 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px]">Calibrate scale…</button>
      ` : ''}
      ${isSelected ? `<button type="button" id="propDeleteBtn" class="w-full py-1.5 bg-red-900/70 hover:bg-red-800 rounded text-[10px] text-red-100">Delete markup</button>` : ''}
    `;

    el.querySelectorAll('.prop-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.prop;
        let val = btn.dataset.value;
        if (['lineWidth', 'cloudScallop', 'fontSize'].includes(key)) val = parseInt(val, 10);
        if (['opacity', 'fillOpacity'].includes(key)) val = parseFloat(val);
        applyMarkupProperty({ [key]: val });
        renderPropertiesPanel();
      });
    });
    const textArea = document.getElementById('propTextLabel');
    if (textArea && isSelected) {
      textArea.addEventListener('change', async () => {
        const m = state.markups.find(x => x.id === state.selectedMarkupId);
        if (!m) return;
        m.label = textArea.value;
        await persistMarkup(m, { label: m.label });
        renderMarkupOverlay();
      });
    }
    document.getElementById('propCalibrateBtn')?.addEventListener('click', () => { setTool('calibrate'); toast('Click two points on a known distance'); });
    document.getElementById('propDeleteBtn')?.addEventListener('click', deleteSelectedMarkup);
  }

  async function applyMarkupProperty(patch) {
    if (state.selectedMarkupId) {
      const m = state.markups.find(x => x.id === state.selectedMarkupId);
      if (!m) return;
      m.style = { ...(m.style || {}), ...patch };
      await persistMarkup(m, { style: m.style });
      renderMarkupOverlay();
    } else {
      Object.assign(state.markupStyle, patch);
    }
  }

  function formatMeasureLength(pxDist) {
    if (state.pixelsPerUnit && pxDist > 0) {
      return { value: Math.round((pxDist / state.pixelsPerUnit) * 100) / 100, unit: state.measureUnit };
    }
    return { value: Math.round(pxDist), unit: 'px' };
  }

  function setTool(tool) {
    if (state.tool !== tool) {
      state.selectedMarkupId = null;
      state.draggingMarkup = null;
      state.drawing = false;
      state.drawStart = null;
      state.tempMarkup = null;
    }
    state.tool = tool;
    highlightActiveTool();
    updateViewerCursor();
    renderMarkupOverlay();
    renderPropertiesPanel();
    if (tool === 'measure' && !state.pixelsPerUnit) {
      toast('Tip: Calibrate scale first for feet/inches, or measurements show in pixels');
    }
  }

  function updateViewerCursor() {
    const wrap = document.getElementById('drawViewerWrap');
    if (!wrap) return;
    wrap.classList.remove('cursor-grab', 'cursor-grabbing', 'cursor-crosshair', 'cursor-pointer');
    if (state.isPanning) wrap.classList.add('cursor-grabbing');
    else if (state.tool === 'pan') wrap.classList.add('cursor-grab');
    else if (state.tool === 'select') wrap.classList.add('cursor-pointer');
    else wrap.classList.add('cursor-crosshair');
  }

  function highlightActiveTool() {
    MARKUP_TOOLS.forEach(t => {
      const btn = document.getElementById(`tool-${t}`);
      if (!btn) return;
      btn.classList.toggle('bg-sky-700', state.tool === t);
      btn.classList.toggle('text-white', state.tool === t);
    });
  }

  function setMarkupColor(color) { applyMarkupProperty({ color }); }
  function setMarkupLineWidth(width) { applyMarkupProperty({ lineWidth: parseInt(width, 10) || 2 }); }

  function updateMarkupToolbar() {
    const btn = document.getElementById('btnDeleteMarkup');
    if (btn) btn.classList.toggle('hidden', !state.selectedMarkupId);
  }

  async function deleteSelectedMarkup() {
    if (!state.selectedMarkupId) return;
    const m = state.markups.find(x => x.id === state.selectedMarkupId);
    if (!m || !confirm('Delete this markup?')) return;
    try {
      await api(`/api/drawings/markups/${m.id}`, { method: 'DELETE' });
    } catch (e) {
      if (e.status !== 404) { alert(e.message); return; }
    }
    state.markups = state.markups.filter(x => x.id !== m.id);
    state.selectedMarkupId = null;
    renderMarkupOverlay();
    renderPropertiesPanel();
    toast('Markup deleted');
  }

  function showTextEditor(pt, existingMarkup) {
    const wrap = document.getElementById('drawViewerWrap');
    if (!wrap || state.textEditorOpen) return;
    state.textEditorOpen = true;
    let editor = document.getElementById('drawTextEditor');
    if (!editor) {
      editor = document.createElement('div');
      editor.id = 'drawTextEditor';
      editor.className = 'absolute z-50 bg-zinc-900 border border-sky-600 rounded-md shadow-xl p-2';
      editor.innerHTML = `
        <textarea id="drawTextEditorInput" rows="3" class="w-56 bg-zinc-800 border border-zinc-700 rounded p-2 text-sm text-white mb-2" placeholder="Enter markup text…"></textarea>
        <div class="flex gap-2 justify-end">
          <button type="button" id="drawTextEditorCancel" class="px-2 py-1 text-xs bg-zinc-800 rounded">Cancel</button>
          <button type="button" id="drawTextEditorSave" class="px-2 py-1 text-xs bg-sky-700 rounded text-white">Place</button>
        </div>`;
      wrap.appendChild(editor);
    }
    const rect = wrap.getBoundingClientRect();
    editor.style.left = `${state.panX + pt.x * state.viewScale}px`;
    editor.style.top = `${state.panY + pt.y * state.viewScale}px`;
    editor.classList.remove('hidden');
    const input = document.getElementById('drawTextEditorInput');
    input.value = existingMarkup?.label || '';
    input.focus();

    const close = () => {
      state.textEditorOpen = false;
      editor.classList.add('hidden');
    };
    document.getElementById('drawTextEditorCancel').onclick = close;
    document.getElementById('drawTextEditorSave').onclick = async () => {
      const text = input.value.trim();
      close();
      if (!text) return;
      if (existingMarkup) {
        existingMarkup.label = text;
        await persistMarkup(existingMarkup, { label: text });
        renderMarkupOverlay();
        return;
      }
      const lines = text.split('\n');
      const fontSize = state.markupStyle.fontSize || 14;
      await saveMarkup({
        markup_type: 'textbox',
        geometry: { x: pt.x, y: pt.y, w: 220, h: Math.max(28, lines.length * (fontSize + 6) + 12) },
        label: text,
        style: { ...state.markupStyle, fillOpacity: 0.85 },
      });
    };
  }

  function bindViewerEvents() {
    const wrap = document.getElementById('drawViewerWrap');
    if (!wrap || wrap._bound) return;
    wrap._bound = true;
    wrap.addEventListener('mousedown', onViewerDown);
    wrap.addEventListener('mousemove', onViewerMove);
    wrap.addEventListener('mouseup', onViewerUp);
    wrap.addEventListener('mouseleave', onViewerUp);
    wrap.addEventListener('wheel', onViewerWheel, { passive: false });
    document.addEventListener('keydown', e => {
      if (!state.openDrawing) return;
      if ((e.key === 'Delete' || e.key === 'Backspace') && state.selectedMarkupId) {
        e.preventDefault();
        deleteSelectedMarkup();
      }
    });
    window.addEventListener('resize', () => {
      if (state.openDrawing && state.view === 'viewer') {
        clearTimeout(bindViewerEvents._resizeTimer);
        bindViewerEvents._resizeTimer = setTimeout(() => renderPdf(true), 150);
      }
    });
  }

  function onViewerWheel(e) {
    if (!state.openDrawing) return;
    e.preventDefault();
    const wrap = document.getElementById('drawViewerWrap');
    const rect = wrap.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
    const pending = state.wheelPending || { mx, my, factor: 1 };
    pending.mx = mx;
    pending.my = my;
    pending.factor *= factor;
    state.wheelPending = pending;
    if (state.wheelRaf) return;
    state.wheelRaf = requestAnimationFrame(() => {
      const p = state.wheelPending;
      state.wheelPending = null;
      state.wheelRaf = null;
      if (!p) return;
      const oldScale = state.viewScale;
      const newScale = Math.max(0.2, Math.min(8, oldScale * p.factor));
      state.panX = p.mx - ((p.mx - state.panX) * newScale) / oldScale;
      state.panY = p.my - ((p.my - state.panY) * newScale) / oldScale;
      state.viewScale = newScale;
      applyViewTransform();
    });
  }

  function onViewerDown(evt) {
    if (evt.button !== 0) return;
    if (state.tool === 'pan' || evt.altKey) {
      state.isPanning = true;
      state.panAnchor = { x: evt.clientX - state.panX, y: evt.clientY - state.panY };
      updateViewerCursor();
      return;
    }
    if (state.tool === 'select') {
      const pt = screenToDoc(evt);
      const hit = hitTestMarkup(pt);
      state.selectedMarkupId = hit ? hit.id : null;
      if (hit) {
        state.draggingMarkup = {
          id: hit.id,
          startPt: pt,
          orig: JSON.parse(JSON.stringify(hit.geometry || {})),
          moved: false,
        };
      } else {
        state.draggingMarkup = null;
      }
      renderMarkupOverlay();
      renderPropertiesPanel();
      return;
    }
    if (['line', 'rect', 'cloud', 'arrow', 'highlight', 'measure', 'ellipse', 'callout'].includes(state.tool)) {
      state.drawing = true;
      state.drawStart = screenToDoc(evt);
      return;
    }
    if (state.tool === 'text') {
      const pt = screenToDoc(evt);
      const hit = hitTestMarkup(pt);
      if (hit && (hit.markup_type === 'text' || hit.markup_type === 'textbox')) {
        state.selectedMarkupId = hit.id;
        showTextEditor(pt, hit);
      } else {
        showTextEditor(pt);
      }
      return;
    }
    if (state.tool === 'rfi_pin') {
      placeRfiPin(screenToDoc(evt));
      return;
    }
    if (state.tool === 'calibrate') {
      const pt = screenToDoc(evt);
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
    if (state.isPanning && state.panAnchor) {
      state.panX = evt.clientX - state.panAnchor.x;
      state.panY = evt.clientY - state.panAnchor.y;
      applyViewTransform();
      return;
    }
    if (state.draggingMarkup) {
      const pt = screenToDoc(evt);
      const m = state.markups.find(x => x.id === state.draggingMarkup.id);
      if (m) {
        const dx = pt.x - state.draggingMarkup.startPt.x;
        const dy = pt.y - state.draggingMarkup.startPt.y;
        if (Math.hypot(dx, dy) > 2) state.draggingMarkup.moved = true;
        m.geometry = translateGeometry(state.draggingMarkup.orig, dx, dy);
        renderMarkupOverlay();
      }
      return;
    }
    if (!state.drawing || !state.drawStart) return;
    const pt = screenToDoc(evt);
    const s = state.drawStart;
    const sw = state.markupStyle.lineWidth || 2;
    const color = state.markupStyle.color || '#38bdf8';
    const scallop = state.markupStyle.cloudScallop || 18;
    if (['rect', 'highlight', 'ellipse'].includes(state.tool)) {
      const x = Math.min(s.x, pt.x); const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x); const rh = Math.abs(pt.y - s.y);
      if (state.tool === 'ellipse') {
        state.tempMarkup = `<ellipse cx="${x + rw / 2}" cy="${y + rh / 2}" rx="${rw / 2}" ry="${rh / 2}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
      } else {
        state.tempMarkup = `<rect x="${x}" y="${y}" width="${rw}" height="${rh}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
      }
    } else if (state.tool === 'callout') {
      const x = Math.min(s.x, pt.x); const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x); const rh = Math.abs(pt.y - s.y);
      state.tempMarkup = `<line x1="${s.x}" y1="${s.y}" x2="${x + rw / 2}" y2="${y + rh}" stroke="${color}" stroke-width="${sw}" stroke-dasharray="4 3"/>
        <rect x="${x}" y="${y}" width="${rw}" height="${rh}" stroke="${color}" stroke-width="${sw}" fill="rgba(24,24,27,0.5)" stroke-dasharray="4 3"/>`;
    } else if (state.tool === 'cloud') {
      const x = Math.min(s.x, pt.x); const y = Math.min(s.y, pt.y);
      state.tempMarkup = `<path d="${cloudPath(x, y, Math.abs(pt.x - s.x), Math.abs(pt.y - s.y), scallop)}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
    } else if (['line', 'arrow', 'measure'].includes(state.tool)) {
      const marker = state.tool === 'arrow' ? ' marker-end="url(#arrowhead)"' : '';
      const pxLen = Math.hypot(pt.x - s.x, pt.y - s.y);
      const measureLabel = state.tool === 'measure'
        ? (() => {
          const m = formatMeasureLength(pxLen);
          return `<text x="${pt.x + 8}" y="${pt.y - 8}" fill="${color}" font-size="12" font-weight="bold">${m.value} ${m.unit}</text>`;
        })()
        : '';
      state.tempMarkup = `<line x1="${s.x}" y1="${s.y}" x2="${pt.x}" y2="${pt.y}" stroke="${color}" stroke-width="${sw}" stroke-dasharray="4 3"${marker} />${measureLabel}`;
    }
    renderMarkupOverlay();
  }

  async function onViewerUp(evt) {
    if (state.isPanning) {
      state.isPanning = false;
      state.panAnchor = null;
      updateViewerCursor();
      return;
    }
    if (state.draggingMarkup) {
      const drag = state.draggingMarkup;
      const m = state.markups.find(x => x.id === drag.id);
      const moved = drag.moved;
      state.draggingMarkup = null;
      if (m && moved) {
        await persistMarkup(m, { geometry: m.geometry });
      }
      renderPropertiesPanel();
      return;
    }
    if (!state.drawing || !state.drawStart) return;
    const pt = screenToDoc(evt);
    const s = state.drawStart;
    const type = state.tool;
    let geometry = {};
    let measurement_value = null;
    let label = null;
    if (['rect', 'cloud', 'highlight', 'ellipse'].includes(type)) {
      geometry = { x: Math.min(s.x, pt.x), y: Math.min(s.y, pt.y), w: Math.abs(pt.x - s.x), h: Math.abs(pt.y - s.y) };
      if (geometry.w < 3 && geometry.h < 3) {
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        return;
      }
    } else if (type === 'callout') {
      geometry = {
        x: Math.min(s.x, pt.x), y: Math.min(s.y, pt.y),
        w: Math.abs(pt.x - s.x), h: Math.abs(pt.y - s.y),
        points: [s.x, s.y, pt.x, pt.y],
        tipX: s.x, tipY: s.y,
      };
      if (geometry.w < 20 && geometry.h < 12) {
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        return;
      }
      label = 'Callout';
    } else if (['line', 'arrow', 'measure'].includes(type)) {
      const pxLen = Math.hypot(pt.x - s.x, pt.y - s.y);
      if (pxLen < 3) {
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        return;
      }
      geometry = { points: [s.x, s.y, pt.x, pt.y] };
      if (type === 'measure') {
        const m = formatMeasureLength(pxLen);
        measurement_value = m.value;
      }
    }
    state.drawing = false;
    state.drawStart = null;
    state.tempMarkup = null;
    await saveMarkup({
      markup_type: type === 'measure' ? 'measure' : type,
      geometry,
      measurement_value,
      measurement_unit: state.pixelsPerUnit ? state.measureUnit : 'px',
      label,
      style: { ...state.markupStyle },
    });
    if (type === 'callout') {
      const last = state.markups[state.markups.length - 1];
      if (last) showTextEditor({ x: geometry.x + 8, y: geometry.y + 8 }, last);
    }
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
    const style = payload.style || { ...state.markupStyle };
    const body = {
      markup_type: payload.markup_type,
      geometry,
      style,
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
    if (state.openDrawing) setTimeout(() => renderPdf(true), 100);
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
      html += `<p class="text-xs text-zinc-400 mb-3">${json.page_count ? `${json.page_count} page(s) in file · ` : ''}${json.created_count || pages.length} sheet(s) imported${json.split ? ' (split from drawing set)' : ''}</p>`;
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

  async function uploadPdfFile(file, setName, extra) {
    if (!file) return null;
    const opts = extra || {};
    const fd = new FormData();
    fd.append('project_id', projectId());
    fd.append('file', file);
    fd.append('set_name', setName || file.name.replace(/\.pdf$/i, '') || 'Drawing Upload');
    if (opts.sheet_number) fd.append('sheet_number', opts.sheet_number);
    if (opts.title) fd.append('title', opts.title);
    const res = await fetch('/api/drawings/upload', { method: 'POST', body: fd, credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = json.needs_review?.length
        ? `\n\n${json.needs_review.length} page(s) listed for review.`
        : '';
      throw new Error((json.error || 'Upload failed') + detail);
    }
    return json;
  }

  function bindSectionDropZone() {
    const panel = document.getElementById('drawPanelSections');
    if (!panel || panel._dropBound) return;
    panel._dropBound = true;
    let dragDepth = 0;
    const highlight = () => {
      panel.classList.add('draw-drop-active');
      document.getElementById('drawDropZone')?.classList.add('border-sky-500', 'bg-sky-950/20');
    };
    const unhighlight = () => {
      panel.classList.remove('draw-drop-active');
      document.getElementById('drawDropZone')?.classList.remove('border-sky-500', 'bg-sky-950/20');
    };
    const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
    panel.addEventListener('dragenter', (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth++;
      highlight();
    });
    panel.addEventListener('dragover', (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
    });
    panel.addEventListener('dragleave', () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) unhighlight();
    });
    panel.addEventListener('drop', async (e) => {
      e.preventDefault();
      dragDepth = 0;
      unhighlight();
      const file = [...(e.dataTransfer?.files || [])].find(
        (f) => f.name.toLowerCase().endsWith('.pdf') || f.type === 'application/pdf'
      );
      if (!file) {
        alert('Drop a PDF drawing set to import sheets.');
        return;
      }
      try {
        toast(`Uploading ${file.name}…`);
        const json = await uploadPdfFile(file, file.name.replace(/\.pdf$/i, ''));
        const count = json.created_count || json.drawings?.length || 1;
        const reviewNote = json.needs_review_count ? ` (${json.needs_review_count} need sheet numbers)` : '';
        toast(json.split ? `Imported ${count} sheets from drawing set${reviewNote}` : `Uploaded ${json.drawing?.sheet_number || count + ' sheet(s)'}`);
        showUploadResults(json);
        await Promise.all([loadDashboard(), loadDrawings()]);
      } catch (err) {
        alert(err.message);
      }
    });
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
    try {
      const json = await uploadPdfFile(
        file,
        document.getElementById('uploadSetName').value || 'Drawing Upload',
        {
          sheet_number: document.getElementById('uploadSheetNumber')?.value || '',
          title: document.getElementById('uploadTitle')?.value || '',
        }
      );
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
    bindSectionDropZone();
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
    setMarkupColor,
    setMarkupLineWidth,
    deleteSelectedMarkup,
    fitToView,
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
