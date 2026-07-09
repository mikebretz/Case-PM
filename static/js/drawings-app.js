/**
 * Case PM — Drawings module (Procore / Bluebeam / ACC / Fieldwire parity)
 */
(function (global) {
  'use strict';

  const SECTION_ORDER = ['G', 'C', 'A', 'S', 'M', 'E', 'P', 'FP', 'L', 'T', 'I', 'OTHER'];
  const MARKUP_TOOLS = ['pan', 'select', 'line', 'rect', 'ellipse', 'cloud', 'arrow', 'text', 'callout', 'highlight', 'measure', 'rfi_pin', 'calibrate'];

  const TOOL_STYLE_DEFAULTS = {
    cloud: { color: '#ef4444', lineWidth: 2, opacity: 1, fillOpacity: 0, cloudScallop: 18 },
    highlight: { color: '#facc15', lineWidth: 1, opacity: 0.35, fillOpacity: 0.35 },
    measure: { color: '#22c55e', lineWidth: 2 },
    text: { color: '#f4f4f5', lineWidth: 1, fillOpacity: 0.9, fontSize: 14, showTextBorder: true },
    textbox: { color: '#f4f4f5', lineWidth: 1, fillOpacity: 0.9, fontSize: 14, showTextBorder: true },
    callout: { color: '#38bdf8', lineWidth: 2, fontSize: 13 },
  };

  function toolStyle(tool) {
    const defaults = TOOL_STYLE_DEFAULTS[tool] || {};
    return { ...state.markupStyle, ...defaults };
  }

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
    markupStyle: {
      color: '#38bdf8', lineWidth: 2, opacity: 1, fillOpacity: 0.25, cloudScallop: 18,
      fontSize: 14, fontWeight: 'normal', fontStyle: 'normal', textAlign: 'left',
      textPadding: 6, showTextBorder: true, arrowHead: 'arrow',
    },
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
    compareRenderMode: 'diff',
    compareRevisionId: null,
    compareBaseRevisionId: null,
    compareDiffPending: false,
    compareDiffFailed: false,
    viewingRevisionId: null,
    pdfPageWidthPts: 0,
    scalePdfPointsPerFoot: null,
    scaleLabel: '',
    canvasSize: { w: 0, h: 0 },
    lastViewport: null,
    focusPin: null,
    previewDrawingId: null,
    wheelRaf: null,
    wheelPending: null,
    textEditorOpen: false,
    deleting: false,
    selectionMode: false,
    selectedDrawingIds: new Set(),
    uploadLogTimer: null,
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
    populateSetFilter();
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
    const setFilter = document.getElementById('drawSetFilter')?.value || '';
    return state.drawings.filter(d => {
      const text = `${d.sheet_number} ${d.title} ${d.discipline} ${d.set_name || ''}`.toLowerCase();
      if (search && !text.includes(search)) return false;
      if (discipline && d.discipline !== discipline) return false;
      if (status && d.status !== status) return false;
      if (setFilter && (d.set_name || 'Unnamed Set') !== setFilter) return false;
      return true;
    });
  }

  function isSheetSelected(id) {
    return state.selectedDrawingIds.has(id);
  }

  function updateBulkBar() {
    const bar = document.getElementById('drawBulkBar');
    const topBar = document.getElementById('drawSelectionBar');
    const countEl = document.getElementById('drawBulkCount');
    const countTop = document.getElementById('drawBulkCountTop');
    const n = state.selectedDrawingIds.size;
    const show = state.selectionMode || n > 0;
    bar?.classList.toggle('hidden', !show);
    topBar?.classList.toggle('hidden', !show);
    const label = n === 1 ? '1 sheet selected' : `${n} sheets selected`;
    if (countEl) countEl.textContent = label;
    if (countTop) countTop.textContent = label;
    const btn = document.getElementById('btnSelectSheets');
    const btnLabel = document.getElementById('btnSelectSheetsLabel');
    if (btn) {
      btn.classList.toggle('bg-sky-700', state.selectionMode);
      btn.classList.toggle('text-white', state.selectionMode);
    }
    if (btnLabel) btnLabel.textContent = state.selectionMode ? (n ? `Selecting (${n})` : 'Selecting…') : 'Select sheets';
  }

  function toggleSelectionMode() {
    state.selectionMode = !state.selectionMode;
    if (!state.selectionMode) state.selectedDrawingIds.clear();
    updateBulkBar();
    renderActiveView();
  }

  function toggleSheetSelection(id, force) {
    const on = force != null ? force : !state.selectedDrawingIds.has(id);
    if (on) {
      state.selectedDrawingIds.add(id);
      state.selectionMode = true;
    } else {
      state.selectedDrawingIds.delete(id);
      if (!state.selectedDrawingIds.size) state.selectionMode = false;
    }
    updateBulkBar();
    renderActiveView();
  }

  function onSheetClick(id, evt) {
    if (state.selectionMode || evt?.ctrlKey || evt?.metaKey) {
      evt?.stopPropagation();
      toggleSheetSelection(id);
      return;
    }
    previewSheet(id);
  }

  function selectAllVisible() {
    filteredDrawings().forEach(d => state.selectedDrawingIds.add(d.id));
    updateBulkBar();
    renderActiveView();
  }

  function clearSelection() {
    state.selectedDrawingIds.clear();
    updateBulkBar();
    renderActiveView();
  }

  function toggleSelectAllVisible(checked) {
    const rows = filteredDrawings();
    if (checked) rows.forEach(d => state.selectedDrawingIds.add(d.id));
    else rows.forEach(d => state.selectedDrawingIds.delete(d.id));
    updateBulkBar();
    renderActiveView();
  }

  async function loadDrawingSets() {
    const pid = projectId();
    if (!pid) return;
    try {
      const json = await api(`/api/drawings/sets?project_id=${pid}`);
      state.drawingSets = json.sets || [];
      populateSetFilter();
    } catch { state.drawingSets = []; }
  }

  function populateSetFilter() {
    const sel = document.getElementById('drawSetFilter');
    if (!sel) return;
    const current = sel.value;
    const names = [...new Set(state.drawings.map(d => d.set_name || 'Unnamed Set'))].sort();
    sel.innerHTML = '<option value="">All sets</option>'
      + names.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
    if (current && names.includes(current)) sel.value = current;
  }

  function openSetsModal() {
    renderSetsModal();
    document.getElementById('drawingSetsModal')?.showModal();
  }

  function renderSetsModal() {
    const body = document.getElementById('drawingSetsBody');
    if (!body) return;
    const sets = state.drawingSets.length ? state.drawingSets : [];
    if (!sets.length) {
      body.innerHTML = '<p class="text-zinc-500 text-sm">No drawing sets yet. Upload a PDF and name the set to create one.</p>';
      return;
    }
    body.innerHTML = `<table class="w-full text-xs"><thead><tr class="text-zinc-400 border-b border-zinc-700">
      <th class="text-left py-2 pr-2">Set name</th>
      <th class="text-center py-2 px-2">Sheets</th>
      <th class="text-center py-2 px-2">Revisions</th>
      <th class="text-left py-2 px-2">Latest upload</th>
      <th class="text-right py-2"></th>
    </tr></thead><tbody>${sets.map(s => `<tr class="border-b border-zinc-800">
      <td class="py-2 pr-2 font-medium text-sky-300">${esc(s.name)}</td>
      <td class="py-2 px-2 text-center">${s.sheet_count || 0}</td>
      <td class="py-2 px-2 text-center text-zinc-500">${s.revision_count || 0}</td>
      <td class="py-2 px-2">${s.latest_upload ? fmtDate(s.latest_upload) : '—'}</td>
      <td class="py-2 text-right">
        <button type="button" onclick="CasePMDrawings.filterBySet(${JSON.stringify(s.name)})" class="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded mr-1">Show</button>
        <button type="button" onclick="CasePMDrawings.deleteDrawingSet(${JSON.stringify(s.name)})" class="px-2 py-1 bg-red-900/70 hover:bg-red-800 rounded text-red-100">Delete set</button>
      </td>
    </tr>`).join('')}</tbody></table>`;
  }

  function filterBySet(name) {
    const sel = document.getElementById('drawSetFilter');
    if (sel) sel.value = name;
    document.getElementById('drawingSetsModal')?.close();
    switchView('list');
    renderActiveView();
  }

  async function deleteDrawingSet(setName) {
    if (!setName) return;
    const set = state.drawingSets.find(s => s.name === setName);
    const count = set?.sheet_count || 0;
    if (!confirm(`Delete drawing set "${setName}" and all ${count} sheet(s) currently in it? This cannot be undone.`)) return;
    try {
      const json = await api('/api/drawings/delete-set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId(), set_name: setName }),
      });
      toast(`Deleted ${json.deleted_count} sheet(s) from "${setName}"`);
      if (state.openDrawing && json.deleted_ids?.includes(state.openDrawing.id)) closeViewer();
      state.selectedDrawingIds.clear();
      updateBulkBar();
      document.getElementById('drawingSetsModal')?.close();
      await Promise.all([loadDashboard(), loadDrawings(), loadDrawingSets()]);
    } catch (e) { alert(e.message); }
  }

  async function deleteSelectedDrawings() {
    const ids = [...state.selectedDrawingIds];
    if (!ids.length) { toast('Check one or more sheets to delete'); return; }
    const labels = ids.map(id => state.drawings.find(d => d.id === id)?.sheet_number || id).join(', ');
    if (!confirm(`Delete ${ids.length} sheet(s)?\n\n${labels}\n\nThis cannot be undone.`)) return;
    if (state.deleting) return;
    state.deleting = true;
    toast(`Deleting ${ids.length} sheet(s)…`);
    try {
      const json = await api('/api/drawings/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId(), drawing_ids: ids }),
      });
      toast(`Deleted ${json.deleted_count} sheet(s)`);
      if (state.openDrawing && json.deleted_ids?.includes(state.openDrawing.id)) closeViewer();
      state.selectedDrawingIds.clear();
      state.selectionMode = false;
      updateBulkBar();
      await Promise.all([loadDashboard(), loadDrawings(), loadDrawingSets()]);
    } catch (e) {
      toastError(e.message || 'Bulk delete failed');
    } finally {
      state.deleting = false;
    }
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
      <div class="bg-zinc-800 border border-zinc-700 rounded-md overflow-hidden hover:border-sky-600 cursor-pointer group relative ${isSheetSelected(d.id) ? 'draw-sheet-selected' : ''}" ondblclick="CasePMDrawings.openViewer(${d.id})" onclick="CasePMDrawings.onSheetClick(${d.id}, event)">
        <input type="checkbox" class="draw-select-checkbox ${isSheetSelected(d.id) ? 'opacity-100' : 'opacity-60 group-hover:opacity-100'}" ${isSheetSelected(d.id) ? 'checked' : ''} onclick="event.stopPropagation(); CasePMDrawings.toggleSheetSelection(${d.id})" title="Select sheet">
        <button type="button" onclick="event.stopPropagation(); CasePMDrawings.deleteDrawing(${d.id})" class="absolute bottom-2 right-2 z-10 opacity-0 group-hover:opacity-100 px-2 py-1 rounded bg-red-900/90 hover:bg-red-800 text-[10px] text-red-100" title="Delete sheet"><i class="fa-solid fa-trash"></i></button>
        <div class="aspect-[4/3] bg-zinc-900 relative">
          <canvas id="thumb-${d.id}" class="w-full h-full object-contain"></canvas>
          <div class="absolute top-2 left-2 font-mono text-xs bg-black/60 px-2 py-0.5 rounded text-sky-300">${esc(d.sheet_number)}</div>
          <div class="absolute top-2 right-2 text-[10px] bg-black/60 px-2 py-0.5 rounded">${esc(d.revision_label || 'Rev 0')}</div>
        </div>
        <div class="p-2">
          <div class="text-xs font-medium truncate">${esc(d.title || 'Untitled')}</div>
          <div class="text-[10px] text-violet-300/90 truncate" title="${esc(d.set_name || '')}">${esc(d.set_name || 'Unnamed Set')}</div>
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
      tbody.innerHTML = '<tr><td colspan="11" class="px-6 py-12 text-center text-zinc-500">No drawings found.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(d => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer ${isSheetSelected(d.id) ? 'bg-sky-950/30' : ''}" ondblclick="CasePMDrawings.openViewer(${d.id})" onclick="CasePMDrawings.onSheetClick(${d.id}, event)">
        <td class="px-2 py-3 text-center" onclick="event.stopPropagation()">
          <input type="checkbox" class="accent-sky-500" ${isSheetSelected(d.id) ? 'checked' : ''} onchange="CasePMDrawings.toggleSheetSelection(${d.id}, this.checked)">
        </td>
        <td class="px-4 py-3 font-mono text-sky-400">${esc(d.sheet_number)}</td>
        <td class="px-4 py-3 max-w-[220px] truncate">${esc(d.title)}</td>
        <td class="px-4 py-3 text-xs text-violet-300 max-w-[140px] truncate" title="${esc(d.set_name || '')}">${esc(d.set_name || '—')}</td>
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
    const allCb = document.getElementById('drawTableSelectAll');
    if (allCb) {
      const visible = rows.map(d => d.id);
      allCb.checked = visible.length > 0 && visible.every(id => state.selectedDrawingIds.has(id));
      allCb.indeterminate = visible.some(id => state.selectedDrawingIds.has(id)) && !allCb.checked;
    }
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
    try {
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
      state.compareDiffFailed = false;
      state.compareRenderMode = 'diff';
      const currentRev = (detail.revisions || []).find(r => r.is_current);
      state.viewingRevisionId = currentRev?.id || detail.revisions?.[0]?.id || null;
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
    } catch (e) {
      toast(e.message || 'Drawing not found — it may have been deleted');
      const p = new URLSearchParams(global.location.search);
      if (p.get('drawing_id')) {
        p.delete('drawing_id');
        const qs = p.toString();
        global.history.replaceState({}, '', qs ? `${global.location.pathname}?${qs}` : global.location.pathname);
      }
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
      const setLabel = state.openDrawing.set_name ? ` · ${state.openDrawing.set_name}` : '';
      title.textContent = `${state.openDrawing.sheet_number} — ${state.openDrawing.title || ''}${setLabel}`;
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
    if (!res.ok) {
      let detail = `Drawing file not found (HTTP ${res.status})`;
      try {
        const err = await res.json();
        detail = err.error || detail;
      } catch (_) { /* ignore */ }
      const e = new Error(detail);
      e.status = res.status;
      throw e;
    }
    const buf = await res.arrayBuffer();
    if (!buf || buf.byteLength < 64) {
      throw new Error('Drawing file is empty or unreadable');
    }
    return buf;
  }

  function getViewerPdfUrl() {
    if (!state.openDrawing) return null;
    const current = state.revisions.find(r => r.is_current);
    const revId = state.viewingRevisionId || current?.id;
    if (!revId || (current && revId === current.id)) {
      return `/api/drawings/${state.openDrawing.id}/file`;
    }
    return `/api/drawings/${state.openDrawing.id}/revisions/${revId}/file`;
  }

  function showViewerPdfError(message) {
    const canvas = document.getElementById('drawPdfCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    canvas.width = Math.max(640, state.baseCanvasSize.w || 640);
    canvas.height = Math.max(320, state.baseCanvasSize.h || 320);
    ctx.fillStyle = '#18181b';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#fca5a5';
    ctx.font = '14px sans-serif';
    const lines = String(message || 'Could not load drawing PDF').split('\n');
    lines.forEach((line, i) => ctx.fillText(line, 32, 48 + i * 22));
    ctx.fillStyle = '#a1a1aa';
    ctx.font = '12px sans-serif';
    ctx.fillText('Re-upload this sheet or pick another revision from the dropdown.', 32, 48 + lines.length * 22 + 12);
    document.getElementById('drawDiffCanvas')?.classList.add('hidden');
  }

  async function renderPageToCanvas(pdfDoc, canvas, viewport, pageNum) {
    if (!pdfDoc) throw new Error('PDF document is not loaded');
    const page = await pdfDoc.getPage(pageNum || 1);
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
    if (state.compareDiffPending || state.compareDiffFailed) return;
    state.compareDiffPending = true;
    try {
      const oldBuf = await fetchPdfBytes(`/api/drawings/${state.openDrawing.id}/revisions/${state.compareBaseRevisionId}/file`);
      const oldDoc = await pdfjsLib.getDocument({ data: oldBuf.slice(0) }).promise;
      const curPage = await state.pdfDoc.getPage(state.pdfPage || 1);
      const vp = state.lastViewport || curPage.getViewport({ scale: 1, rotation: curPage.rotate });
      const offOld = document.createElement('canvas');
      const offNew = document.createElement('canvas');
      await renderPageToCanvas(oldDoc, offOld, vp, 1);
      await renderPageToCanvas(state.pdfDoc, offNew, vp, state.pdfPage || 1);
      diffCanvas.width = vp.width;
      diffCanvas.height = vp.height;
      diffCanvas.style.width = vp.width + 'px';
      diffCanvas.style.height = vp.height + 'px';
      const dctx = diffCanvas.getContext('2d');
      dctx.clearRect(0, 0, vp.width, vp.height);
      if (state.compareRenderMode === 'overlay') {
        dctx.globalAlpha = state.compareOpacity;
        dctx.drawImage(offOld, 0, 0);
        dctx.globalAlpha = 1;
      } else {
        const diff = pixelDiff(offOld.getContext('2d'), offNew.getContext('2d'), vp.width, vp.height, state.compareOpacity);
        dctx.putImageData(diff, 0, 0);
      }
      diffCanvas.classList.remove('hidden');
      state.compareDiffFailed = false;
    } catch (e) {
      console.warn('Compare diff failed', e);
      state.compareDiffFailed = true;
      diffCanvas.classList.add('hidden');
      toast(e.message || 'Could not load comparison revision — re-upload or pick another');
    } finally {
      state.compareDiffPending = false;
    }
  }

  async function renderPdf(forceReload) {
    if (!state.openDrawing || !global.pdfjsLib) return;
    const canvas = document.getElementById('drawPdfCanvas');
    const wrap = document.getElementById('drawViewerWrap');
    if (!canvas || !wrap) return;

    const url = getViewerPdfUrl();
    const gen = ++state.renderGen;

    if (forceReload || !state.pdfDoc || state.pdfUrl !== url) {
      if (state.renderTask) {
        try { await state.renderTask.cancel(); } catch { /* cancelled */ }
        state.renderTask = null;
      }
      state.pdfUrl = url;
      try {
        const buf = await fetchPdfBytes(url);
        if (gen !== state.renderGen) return;
        state.pdfBytes = buf;
        state.pdfDoc = await pdfjsLib.getDocument({ data: buf.slice(0) }).promise;
      } catch (e) {
        if (gen !== state.renderGen) return;
        state.pdfDoc = null;
        state.pdfBytes = null;
        showViewerPdfError(e.message);
        return;
      }
    }

    if (!state.pdfDoc) return;
    const page = await state.pdfDoc.getPage(state.pdfPage || 1);
    const unscaled = page.getViewport({ scale: 1, rotation: page.rotate });
    state.pdfPageWidthPts = unscaled.width;
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
    if (state.pixelsPerUnit && state.scalePdfPointsPerFoot) {
      applyScalePdfPtsPerFoot(state.scalePdfPointsPerFoot, state.scaleLabel, true);
    } else {
      await tryAutoDetectScale();
    }
    if (state.compareOverlayActive && !state.compareDiffFailed) {
      await renderCompareDiff();
    }
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
    const dash = style.strokeDash ? ` stroke-dasharray="${style.strokeDash}"` : '';
    const id = m.id;
    let hit = '';
    let visual = '';

    if (m.markup_type === 'line' || m.markup_type === 'measure') {
      const pts = geom.points || [];
      if (pts.length < 4) return '';
      hit = `<line data-markup-id="${id}" x1="${pts[0]}" y1="${pts[1]}" x2="${pts[2]}" y2="${pts[3]}" stroke="transparent" stroke-width="22" pointer-events="stroke"/>`;
      const label = m.markup_type === 'measure' && m.measurement_value != null
        ? `<text x="${pts[2]}" y="${pts[3] - 8}" fill="${selStroke}" font-size="12" font-weight="bold">${m.measurement_value} ${m.measurement_unit || ''}</text>` : '';
      visual = `<line x1="${pts[0]}" y1="${pts[1]}" x2="${pts[2]}" y2="${pts[3]}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}"${dash} pointer-events="none"/>${label}`;
    } else if (m.markup_type === 'rect' || m.markup_type === 'highlight') {
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" fill="transparent" pointer-events="all"/>`;
      visual = `<rect x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" stroke="${selStroke}" stroke-width="${selSw}" fill="${fill}" opacity="${op}"${dash} pointer-events="none"/>`;
    } else if (m.markup_type === 'cloud') {
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" fill="transparent" pointer-events="all"/>`;
      visual = `<path d="${revisionCloudPath(geom.x, geom.y, geom.w, geom.h, scallop)}" stroke="${selStroke}" stroke-width="${selSw}" fill="none" opacity="${op}"${dash} pointer-events="none"/>`;
    } else if (m.markup_type === 'arrow' && geom.points) {
      const p = geom.points;
      hit = `<line data-markup-id="${id}" x1="${p[0]}" y1="${p[1]}" x2="${p[2]}" y2="${p[3]}" stroke="transparent" stroke-width="22" pointer-events="stroke"/>`;
      visual = `<line x1="${p[0]}" y1="${p[1]}" x2="${p[2]}" y2="${p[3]}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}"${dash} marker-end="url(#arrowhead)" pointer-events="none"/>`;
    } else if (m.markup_type === 'ellipse') {
      hit = `<ellipse data-markup-id="${id}" cx="${geom.x + geom.w / 2}" cy="${geom.y + geom.h / 2}" rx="${geom.w / 2}" ry="${geom.h / 2}" fill="transparent" pointer-events="all"/>`;
      visual = `<ellipse cx="${geom.x + geom.w / 2}" cy="${geom.y + geom.h / 2}" rx="${geom.w / 2}" ry="${geom.h / 2}" stroke="${selStroke}" stroke-width="${selSw}" fill="${fill}" opacity="${op}"${dash} pointer-events="none"/>`;
    } else if (m.markup_type === 'callout' && geom.points) {
      const p = geom.points;
      const bx = Math.min(p[0], p[2]);
      const by = Math.min(p[1], p[3]);
      const bw = Math.abs(p[2] - p[0]);
      const bh = Math.abs(p[3] - p[1]);
      const tipX = geom.tipX != null ? geom.tipX : p[0];
      const tipY = geom.tipY != null ? geom.tipY : p[3];
      hit = `<rect data-markup-id="${id}" x="${bx}" y="${by}" width="${bw}" height="${bh}" fill="transparent" pointer-events="all"/>`;
      visual = `<line x1="${tipX}" y1="${tipY}" x2="${bx + bw / 2}" y2="${by + bh}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}"${dash} pointer-events="none"/>
        <rect x="${bx}" y="${by}" width="${bw}" height="${bh}" stroke="${selStroke}" stroke-width="${selSw}" fill="rgba(24,24,27,0.85)" opacity="${op}"${dash} pointer-events="none"/>
        <text x="${bx + 8}" y="${by + 20}" fill="${selStroke}" font-size="${style.fontSize || 13}" font-weight="${style.fontWeight === 'bold' ? 'bold' : 'normal'}" pointer-events="none">${esc(m.label || '')}</text>`;
    } else if (m.markup_type === 'text' || m.markup_type === 'textbox') {
      const tw = geom.w || 180;
      const th = geom.h || 28;
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${tw}" height="${th}" fill="transparent" pointer-events="all"/>`;
      const bg = style.fillOpacity != null ? `rgba(24,24,27,${style.fillOpacity})` : 'rgba(24,24,27,0.75)';
      const border = style.showTextBorder !== false
        ? `<rect x="${geom.x}" y="${geom.y}" width="${tw}" height="${th}" fill="${bg}" stroke="${selStroke}" stroke-width="${selected ? 2 : 1}" opacity="${op}" pointer-events="none"/>`
        : `<rect x="${geom.x}" y="${geom.y}" width="${tw}" height="${th}" fill="${bg}" stroke="none" opacity="${op}" pointer-events="none"/>`;
      const ta = textMarkupAttrs(style, geom, m.label);
      visual = `${border}
        <text x="${ta.tx}" y="${geom.y + ta.pad}" text-anchor="${ta.anchor}" fill="${selStroke}" font-size="${ta.fs}" font-weight="${ta.weight}" font-style="${ta.italic}" opacity="${op}" pointer-events="none">${ta.tspans}</text>`;
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
  const FONT_WEIGHT_PRESETS = [
    { label: 'Regular', value: 'normal' }, { label: 'Bold', value: 'bold' },
  ];
  const TEXT_ALIGN_PRESETS = [
    { label: 'Left', value: 'left' }, { label: 'Center', value: 'center' }, { label: 'Right', value: 'right' },
  ];
  const ARROW_HEAD_PRESETS = [
    { label: 'Arrow', value: 'arrow' }, { label: 'Open', value: 'open' }, { label: 'None', value: 'none' },
  ];
  const SCALE_PRESETS = [
    { label: '1/8"=1\'', pdfPtsPerFoot: 9 },
    { label: '1/4"=1\'', pdfPtsPerFoot: 18 },
    { label: '1/2"=1\'', pdfPtsPerFoot: 36 },
    { label: '1"=1\'', pdfPtsPerFoot: 72 },
    { label: '1"=10\'', pdfPtsPerFoot: 7.2 },
    { label: '1"=20\'', pdfPtsPerFoot: 3.6 },
    { label: '1"=30\'', pdfPtsPerFoot: 2.4 },
    { label: '1"=40\'', pdfPtsPerFoot: 1.8 },
    { label: '1:50', pdfPtsPerFoot: 1.44 },
    { label: '1:100', pdfPtsPerFoot: 0.72 },
  ];

  function applyScalePdfPtsPerFoot(pdfPtsPerFoot, label, silent) {
    if (!pdfPtsPerFoot || !state.pdfPageWidthPts || !state.baseCanvasSize.w) return false;
    const canvasPxPerPdfPt = state.baseCanvasSize.w / state.pdfPageWidthPts;
    state.pixelsPerUnit = pdfPtsPerFoot * canvasPxPerPdfPt;
    state.scalePdfPointsPerFoot = pdfPtsPerFoot;
    state.scaleLabel = label || '';
    if (!silent) renderPropertiesPanel();
    return true;
  }

  async function tryAutoDetectScale() {
    if (state.pixelsPerUnit || !state.openDrawing || !state.pdfPageWidthPts) return;
    try {
      const json = await api(`/api/drawings/${state.openDrawing.id}/detect-scale`);
      if (json.scale?.pdf_points_per_foot) {
        applyScalePdfPtsPerFoot(json.scale.pdf_points_per_foot, json.scale.scale_text, true);
      }
    } catch { /* optional */ }
  }

  async function detectScale() {
    if (!state.openDrawing) return;
    try {
      const json = await api(`/api/drawings/${state.openDrawing.id}/detect-scale`);
      if (!json.scale?.pdf_points_per_foot) {
        toast(json.message || 'No scale found on this sheet');
        return;
      }
      if (applyScalePdfPtsPerFoot(json.scale.pdf_points_per_foot, json.scale.scale_text)) {
        toast(`Scale detected: ${json.scale.scale_text}`);
      }
    } catch (e) { toast(e.message); }
  }

  function applyScalePreset(pdfPtsPerFoot, label) {
    if (applyScalePdfPtsPerFoot(pdfPtsPerFoot, label)) {
      toast(`Scale set: ${label}`);
    }
  }

  function applyManualScaleInput() {
    const raw = document.getElementById('propScaleInput')?.value?.trim();
    if (!raw) return;
    const arch = raw.match(/^(\d+)\s*\/\s*(\d+)\s*["″]?\s*=\s*(\d+)\s*(?:['′\-]\s*(\d{1,2})|['′])?$/i);
    if (arch) {
      const num = parseInt(arch[1], 10);
      const denom = parseInt(arch[2], 10);
      const feet = parseInt(arch[3], 10);
      const inches = parseInt(arch[4] || '0', 10);
      const paperIn = num / Math.max(denom, 1);
      const realFt = feet + inches / 12;
      const pdfPts = (paperIn / realFt) * 72;
      applyScalePreset(pdfPts, raw);
      return;
    }
    const ratio = raw.match(/^1\s*[:/]\s*(\d+)$/i);
    if (ratio) {
      applyScalePreset(72 / parseInt(ratio[1], 10), `1:${ratio[1]}`);
      return;
    }
    toast('Use format like 1/4"=1\' or 1:50');
  }

  function propRow(label, id, value, min, max, step, hint) {
    return `<div class="markup-prop-row">
      <label for="${id}">${esc(label)}${hint ? `<span class="block text-[9px] text-zinc-600">${esc(hint)}</span>` : ''}</label>
      <input type="number" id="${id}" value="${value}" min="${min}" max="${max}" step="${step}">
    </div>`;
  }

  function propRowText(label, id, value) {
    return `<div class="markup-prop-row">
      <label for="${id}">${esc(label)}</label>
      <input type="text" id="${id}" value="${esc(value)}">
    </div>`;
  }

  function propSection(title, body) {
    return `<div class="markup-props-section"><div class="markup-props-section-title">${esc(title)}</div>${body}</div>`;
  }

  function parseStrokeDash(strokeDash) {
    const parts = String(strokeDash || '').trim().split(/\s+/).filter(Boolean);
    return { dash: parseInt(parts[0], 10) || 0, gap: parseInt(parts[1], 10) || 0 };
  }

  function textAlignToNum(align) {
    if (align === 'center') return 1;
    if (align === 'right') return 2;
    return 0;
  }

  function numToTextAlign(n) {
    const v = parseInt(n, 10);
    if (v === 1) return 'center';
    if (v === 2) return 'right';
    return 'left';
  }

  function fontWeightToNum(fw) {
    return fw === 'bold' || fw === 700 || fw === '700' ? 700 : 400;
  }

  function textMarkupAttrs(style, geom, label) {
    const fs = style.fontSize || 14;
    const pad = style.textPadding ?? 6;
    const align = style.textAlign || 'left';
    const anchor = align === 'center' ? 'middle' : (align === 'right' ? 'end' : 'start');
    const tx = geom.x + (align === 'center' ? (geom.w || 180) / 2 : (align === 'right' ? (geom.w || 180) - pad : pad));
    const weight = style.fontWeight === 'bold' ? 'bold' : 'normal';
    const italic = style.fontStyle === 'italic' ? 'italic' : 'normal';
    const lines = String(label || '').split('\n');
    const lineH = fs + 4;
    const tspans = lines.map((line, i) =>
      `<tspan x="${tx}" dy="${i === 0 ? fs + pad : lineH}">${esc(line)}</tspan>`
    ).join('');
    return { fs, pad, anchor, tx, weight, italic, tspans, lineH };
  }

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
    const showArrow = type === 'arrow' || type === 'line' || type === 'callout';
    const showMeasure = type === 'measure' || (isSelected && ctx?.markup_type === 'measure');
    const showFill = ['rect', 'highlight', 'ellipse', 'text', 'textbox', 'callout'].includes(type);
    const showSize = isSelected && ['rect', 'highlight', 'ellipse', 'cloud', 'textbox', 'callout'].includes(type);
    const geom = isSelected && ctx?.geometry ? resolveGeom(ctx.geometry) : null;
    const color = style.color || '#38bdf8';
    const lineWidth = style.lineWidth || 2;
    const opacityPct = Math.round((style.opacity ?? 1) * 100);
    const fillOpacityPct = Math.round((style.fillOpacity ?? (type === 'highlight' ? 0.25 : 0.75)) * 100);
    const cloudScallop = style.cloudScallop || 18;
    const fontSize = style.fontSize || 14;
    const fontWeightNum = fontWeightToNum(style.fontWeight);
    const fontStyleDeg = style.fontStyle === 'italic' ? 1 : 0;
    const textAlignNum = textAlignToNum(style.textAlign || 'left');
    const textPadding = style.textPadding ?? 6;
    const showTextBorder = style.showTextBorder !== false ? 1 : 0;
    const arrowHead = style.arrowHead || 'arrow';
    const dashParts = parseStrokeDash(style.strokeDash || '');

    el.innerHTML = `
      <div class="text-[10px] uppercase text-zinc-500 mb-2 sticky top-0 bg-zinc-800/95 py-1 z-10 border-b border-zinc-700/80">${esc(title)}</div>
      ${showText && !isSelected ? `<div class="markup-prop-hint">Drag a rectangle on the sheet to create a text box. Set font and border options here first.</div>` : ''}
      ${showLine ? propSection('Stroke', `
        <div class="markup-prop-row">
          <label for="propColorPicker">Color</label>
          <input type="color" id="propColorPicker" value="${color}">
        </div>
        ${propRowText('Hex', 'propColorHex', color)}
        ${propRow('Weight px', 'propLineWidth', lineWidth, 0.5, 48, 0.5)}
        ${propRow('Opacity %', 'propOpacity', opacityPct, 0, 100, 1)}
        ${propRow('Dash px', 'propDashLen', dashParts.dash, 0, 64, 1, '0 = solid')}
        ${propRow('Gap px', 'propGapLen', dashParts.gap, 0, 64, 1)}
      `) : ''}
      ${showFill ? propSection('Fill', propRow('Opacity %', 'propFillOpacity', fillOpacityPct, 0, 100, 1)) : ''}
      ${showCloud ? propSection('Cloud', propRow('Scallop px', 'propCloudScallop', cloudScallop, 4, 64, 1)) : ''}
      ${showText ? propSection('Text', `
        ${propRow('Size px', 'propFontSize', fontSize, 6, 96, 1)}
        ${propRow('Weight', 'propFontWeight', fontWeightNum, 100, 900, 100, '400 or 700')}
        ${propRow('Italic', 'propFontItalic', fontStyleDeg, 0, 1, 1, '0=off 1=on')}
        ${propRow('Align', 'propTextAlign', textAlignNum, 0, 2, 1, '0=L 1=C 2=R')}
        ${propRow('Pad px', 'propTextPadding', textPadding, 0, 48, 1)}
        ${propRow('Border', 'propShowTextBorder', showTextBorder, 0, 1, 1, '0=off 1=on')}
      `) : ''}
      ${showArrow ? propSection('Arrow', `
        <div class="markup-prop-row">
          <label for="propArrowHead">Head type</label>
          <select id="propArrowHead">
            <option value="arrow" ${arrowHead === 'arrow' ? 'selected' : ''}>Arrow</option>
            <option value="open" ${arrowHead === 'open' ? 'selected' : ''}>Open</option>
            <option value="none" ${arrowHead === 'none' ? 'selected' : ''}>None</option>
          </select>
        </div>
      `) : ''}
      ${showSize && geom ? propSection('Geometry px', `
        ${propRow('Width', 'propGeomW', Math.round(geom.w || 0), 1, 8000, 1)}
        ${propRow('Height', 'propGeomH', Math.round(geom.h || 0), 1, 8000, 1)}
        ${geom.w && geom.h ? `<div class="markup-prop-hint">Area <strong>${Math.round(geom.w * geom.h).toLocaleString()}</strong> sq px</div>` : ''}
      `) : ''}
      ${isSelected && showText ? propSection('Content', `
        <textarea id="propTextLabel" rows="4" class="w-full bg-zinc-900 border border-zinc-700 rounded p-2 text-xs text-white">${esc(ctx.label || '')}</textarea>
      `) : ''}
      ${showMeasure ? propSection('Scale', `
        <div class="markup-prop-hint">
          ${state.scaleLabel ? `Scale <strong>${esc(state.scaleLabel)}</strong><br>` : ''}
          ${state.pixelsPerUnit ? `<strong>${state.pixelsPerUnit.toFixed(2)}</strong> px/ft` : 'Not set — values in pixels'}
        </div>
        ${propRow('PDF pt/ft', 'propScalePts', state.scalePdfPointsPerFoot || '', 0.1, 200, 0.1, '72 = 1"=1\'')}
        <div class="markup-prop-row">
          <label for="propScaleInput">Arch scale</label>
          <input type="text" id="propScaleInput" placeholder='1/4"=1\''>
        </div>
        <button type="button" id="propScaleApplyBtn" class="w-full py-1 mb-1 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px]">Apply arch scale</button>
        <button type="button" id="propDetectScaleBtn" class="w-full py-1 mb-1 bg-sky-900/50 hover:bg-sky-900 rounded text-[10px] text-sky-200">Auto-detect</button>
        <button type="button" id="propCalibrateBtn" class="w-full py-1 mb-1 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px]">Calibrate…</button>
      `) : ''}
      ${isSelected ? `<button type="button" id="propDeleteBtn" class="w-full mt-2 py-1.5 bg-red-900/70 hover:bg-red-800 rounded text-[10px] text-red-100">Delete markup</button>` : ''}
    `;

    const bindLiveNum = (id, applyFn) => {
      const input = document.getElementById(id);
      if (!input) return;
      const run = () => applyFn(input);
      input.addEventListener('input', run);
      input.addEventListener('change', run);
    };

    bindLiveNum('propLineWidth', (input) => {
      const val = parseFloat(input.value);
      if (!Number.isNaN(val)) applyMarkupProperty({ lineWidth: val });
      renderMarkupOverlay();
    });
    bindLiveNum('propOpacity', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ opacity: Math.min(100, Math.max(0, val)) / 100 });
      renderMarkupOverlay();
    });
    bindLiveNum('propFillOpacity', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ fillOpacity: Math.min(100, Math.max(0, val)) / 100 });
      renderMarkupOverlay();
    });
    bindLiveNum('propCloudScallop', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ cloudScallop: val });
      renderMarkupOverlay();
    });
    bindLiveNum('propFontSize', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ fontSize: val });
      renderMarkupOverlay();
    });
    bindLiveNum('propFontWeight', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ fontWeight: val >= 600 ? 'bold' : 'normal' });
      renderMarkupOverlay();
    });
    bindLiveNum('propFontItalic', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ fontStyle: val ? 'italic' : 'normal' });
      renderMarkupOverlay();
    });
    bindLiveNum('propTextAlign', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ textAlign: numToTextAlign(val) });
      renderMarkupOverlay();
    });
    bindLiveNum('propTextPadding', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ textPadding: val });
      renderMarkupOverlay();
    });
    bindLiveNum('propShowTextBorder', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ showTextBorder: val !== 0 });
      renderMarkupOverlay();
    });
    const applyDash = () => {
      const dash = parseInt(document.getElementById('propDashLen')?.value, 10) || 0;
      const gap = parseInt(document.getElementById('propGapLen')?.value, 10) || 0;
      const strokeDash = dash > 0 && gap > 0 ? `${dash} ${gap}` : (dash > 0 ? `${dash} ${dash}` : '');
      applyMarkupProperty({ strokeDash });
      renderMarkupOverlay();
    };
    bindLiveNum('propDashLen', applyDash);
    bindLiveNum('propGapLen', applyDash);

    bindLiveNum('propScalePts', (input) => {
      const val = parseFloat(input.value);
      if (!Number.isNaN(val) && val > 0) applyScalePdfPtsPerFoot(val, `1:${Math.round(72 / val)}`);
    });

    const colorPicker = document.getElementById('propColorPicker');
    const colorHex = document.getElementById('propColorHex');
    if (colorPicker) colorPicker.addEventListener('input', () => {
      applyMarkupProperty({ color: colorPicker.value });
      if (colorHex) colorHex.value = colorPicker.value;
      renderMarkupOverlay();
    });
    if (colorHex) colorHex.addEventListener('change', () => {
      applyMarkupProperty({ color: colorHex.value });
      renderMarkupOverlay();
    });

    const arrowSel = document.getElementById('propArrowHead');
    if (arrowSel) arrowSel.addEventListener('change', () => {
      applyMarkupProperty({ arrowHead: arrowSel.value });
      renderMarkupOverlay();
    });

    const applyGeomSize = async () => {
      if (!state.selectedMarkupId) return;
      const m = state.markups.find(x => x.id === state.selectedMarkupId);
      if (!m) return;
      const w = parseFloat(document.getElementById('propGeomW')?.value);
      const h = parseFloat(document.getElementById('propGeomH')?.value);
      if (Number.isNaN(w) || Number.isNaN(h)) return;
      const g = resolveGeom(m.geometry || {});
      m.geometry = normalizeGeometry({ x: g.x, y: g.y, w, h });
      await persistMarkup(m, { geometry: m.geometry });
      renderMarkupOverlay();
    };
    document.getElementById('propGeomW')?.addEventListener('input', applyGeomSize);
    document.getElementById('propGeomH')?.addEventListener('input', applyGeomSize);

    const textArea = document.getElementById('propTextLabel');
    if (textArea && isSelected) {
      textArea.addEventListener('input', async () => {
        const m = state.markups.find(x => x.id === state.selectedMarkupId);
        if (!m) return;
        m.label = textArea.value;
        await persistMarkup(m, { label: m.label });
        renderMarkupOverlay();
      });
    }
    document.getElementById('propCalibrateBtn')?.addEventListener('click', () => { setTool('calibrate'); toast('Click two points on a known distance'); });
    document.getElementById('propDetectScaleBtn')?.addEventListener('click', detectScale);
    document.getElementById('propScaleApplyBtn')?.addEventListener('click', applyManualScaleInput);
    document.getElementById('propScaleInput')?.addEventListener('keydown', e => { if (e.key === 'Enter') applyManualScaleInput(); });
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
    const defaults = TOOL_STYLE_DEFAULTS[tool];
    if (defaults) {
      Object.assign(state.markupStyle, defaults);
    }
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

  function showTextEditor(pt, existingMarkup, pendingGeometry) {
    const wrap = document.getElementById('drawViewerWrap');
    if (!wrap || state.textEditorOpen) return;
    state.textEditorOpen = true;
    state.pendingTextGeometry = pendingGeometry || null;
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
      state.pendingTextGeometry = null;
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
      const geom = state.pendingTextGeometry || {
        x: pt.x,
        y: pt.y,
        w: 220,
        h: Math.max(28, lines.length * (fontSize + 6) + 12),
      };
      state.pendingTextGeometry = null;
      await saveMarkup({
        markup_type: 'textbox',
        geometry: geom,
        label: text,
        style: { ...toolStyle('text'), fillOpacity: toolStyle('text').fillOpacity ?? 0.9 },
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
    if (['line', 'rect', 'cloud', 'arrow', 'highlight', 'measure', 'ellipse', 'callout', 'text'].includes(state.tool)) {
      state.drawing = true;
      state.drawStart = screenToDoc(evt);
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
        state.scaleLabel = 'Calibrated on drawing';
        state.scalePdfPointsPerFoot = null;
        renderPropertiesPanel();
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
    const activeStyle = toolStyle(state.tool);
    const sw = activeStyle.lineWidth || 2;
    const color = activeStyle.color || '#38bdf8';
    const scallop = activeStyle.cloudScallop || 18;
    if (['rect', 'highlight', 'ellipse', 'text'].includes(state.tool)) {
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
    if (['rect', 'cloud', 'highlight', 'ellipse', 'text'].includes(type)) {
      geometry = { x: Math.min(s.x, pt.x), y: Math.min(s.y, pt.y), w: Math.abs(pt.x - s.x), h: Math.abs(pt.y - s.y) };
      if (geometry.w < 3 && geometry.h < 3) {
        if (type === 'text') {
          const hit = hitTestMarkup(pt);
          if (hit && (hit.markup_type === 'text' || hit.markup_type === 'textbox')) {
            state.selectedMarkupId = hit.id;
            showTextEditor(pt, hit);
          }
        }
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        return;
      }
      if (type === 'text') {
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        showTextEditor({ x: geometry.x + 8, y: geometry.y + 8 }, null, geometry);
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
      style: { ...toolStyle(type) },
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

  async function viewRevisionInViewer() {
    const revId = parseInt(document.getElementById('viewerRevisionSelect')?.value, 10);
    if (!revId || !state.openDrawing) return;
    state.viewingRevisionId = revId;
    state.compareOverlayActive = false;
    state.compareDiffFailed = false;
    state.compareBaseRevisionId = null;
    document.getElementById('drawDiffCanvas')?.classList.add('hidden');
    document.getElementById('btnCompareOverlay')?.classList.remove('bg-sky-700', 'text-white');
    document.getElementById('compareOpacity')?.classList.add('hidden');
    document.getElementById('compareModeSelect')?.classList.add('hidden');
    await renderPdf(true);
    const rev = state.revisions.find(r => r.id === revId);
    toast(rev?.is_current ? 'Viewing current revision' : `Viewing ${rev?.revision_label || 'archived revision'}`);
  }

  function openCompareDialog() {
    if (!state.openDrawing) {
      toast('Open a sheet in the viewer first');
      return;
    }
    loadDrawingSets().then(() => {
    const dialog = document.getElementById('compareDialog');
    if (!dialog) return;
    const current = state.revisions.find(r => r.is_current) || state.revisions[0];
    const sorted = [...state.revisions].sort((a, b) => new Date(b.uploaded_at || 0) - new Date(a.uploaded_at || 0));
    const viewingId = state.viewingRevisionId || current?.id;
    const viewing = state.revisions.find(r => r.id === viewingId) || current;
    const prev = sorted.find(r => r.id !== viewing?.id);
    const summary = document.getElementById('compareDialogSummary');
    if (summary) {
      summary.innerHTML = `Compare <strong>${esc(state.openDrawing.sheet_number)}</strong> — viewing <strong>${esc(viewing?.revision_label || 'current')}</strong>`;
    }
    const prevBtn = document.getElementById('comparePreviousBtn');
    if (prevBtn) {
      prevBtn.disabled = !prev;
      prevBtn.textContent = prev ? `Compare to previous revision (${prev.revision_label})` : 'No previous revision available';
      prevBtn.dataset.revId = prev?.id || '';
    }
    const pick = document.getElementById('compareRevisionPick');
    if (pick) {
      const options = state.revisions.filter(r => r.id !== viewing?.id);
      pick.innerHTML = options.length
        ? options.map(r => `<option value="${r.id}">${esc(r.revision_label)} · ${fmtDate(r.uploaded_at)}${r.set_name ? ` · ${esc(r.set_name)}` : ''}</option>`).join('')
        : '<option value="">No other revisions</option>';
    }
    const setPick = document.getElementById('compareSetPick');
    if (setPick) {
      const viewing = state.revisions.find(r => r.id === (state.viewingRevisionId || state.revisions.find(x => x.is_current)?.id));
      const names = state.drawingSets.length
        ? state.drawingSets.map(s => s.name)
        : [...new Set(state.revisions.map(r => r.set_name).filter(Boolean))];
      setPick.innerHTML = '<option value="">— Compare to another drawing set —</option>'
        + names.filter(s => s !== viewing?.set_name).map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
    }
    dialog.showModal();
    });
  }

  async function startCompare(mode) {
    const dialog = document.getElementById('compareDialog');
    const viewingId = state.viewingRevisionId || state.revisions.find(r => r.is_current)?.id;
    let baseRevId = null;
    if (mode === 'previous') {
      baseRevId = parseInt(document.getElementById('comparePreviousBtn')?.dataset.revId, 10);
    } else if (mode === 'set') {
      const setName = document.getElementById('compareSetPick')?.value;
      const rev = state.revisions.find(r => r.set_name === setName);
      baseRevId = rev?.id;
      if (!baseRevId) { toast('No revision from that set for this sheet'); return; }
    } else {
      baseRevId = parseInt(document.getElementById('compareRevisionPick')?.value, 10);
    }
    if (!baseRevId) { toast('Select a revision to compare against'); return; }
    if (baseRevId === viewingId) { toast('Pick a different revision than the one you are viewing'); return; }
    state.compareRenderMode = document.querySelector('input[name="compareMode"]:checked')?.value || 'diff';
    state.compareBaseRevisionId = baseRevId;
    state.compareOverlayActive = true;
    state.compareDiffFailed = false;
    dialog?.close();
    document.getElementById('btnCompareOverlay')?.classList.add('bg-sky-700', 'text-white');
    document.getElementById('compareOpacity')?.classList.remove('hidden');
    const modeSel = document.getElementById('compareModeSelect');
    if (modeSel) {
      modeSel.classList.remove('hidden');
      modeSel.value = state.compareRenderMode;
    }
    await renderCompareDiff();
    toast(state.compareRenderMode === 'overlay'
      ? 'Overlay: previous revision shown in gray on top'
      : 'Change highlights: blue = added, red = removed');
  }

  function stopCompare() {
    state.compareOverlayActive = false;
    state.compareBaseRevisionId = null;
    state.compareDiffFailed = false;
    document.getElementById('drawDiffCanvas')?.classList.add('hidden');
    document.getElementById('btnCompareOverlay')?.classList.remove('bg-sky-700', 'text-white');
    document.getElementById('compareOpacity')?.classList.add('hidden');
    document.getElementById('compareModeSelect')?.classList.add('hidden');
  }

  function setCompareRenderMode(mode) {
    state.compareRenderMode = mode || 'diff';
    state.compareDiffFailed = false;
    if (state.compareOverlayActive) renderCompareDiff();
  }

  async function loadRevisionInViewer() {
    await viewRevisionInViewer();
  }

  async function toggleCompareOverlay() {
    if (state.compareOverlayActive) {
      stopCompare();
      return;
    }
    openCompareDialog();
  }

  function setCompareOpacity(val) {
    state.compareOpacity = (parseInt(val, 10) || 70) / 100;
    if (state.compareOverlayActive && !state.compareDiffFailed) renderCompareDiff();
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
    const dlg = document.getElementById('uploadDrawingModal');
    if (!dlg) return;
    dlg.showModal();
    if (global.CasePMDialog?.makeDraggable) {
      global.CasePMDialog.makeDraggable(dlg, '.casepm-drag-handle');
    }
    const fileInput = document.getElementById('uploadFile');
    const nameEl = document.getElementById('uploadDropFileName');
    if (nameEl && fileInput && !fileInput.files?.length) nameEl.textContent = '';
  }

  function setUploadModalFile(file) {
    const fileInput = document.getElementById('uploadFile');
    const nameEl = document.getElementById('uploadDropFileName');
    if (!fileInput || !file) return;
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    if (nameEl) nameEl.textContent = file.name;
  }

  function bindUploadModalDropZone() {
    const zone = document.getElementById('uploadModalDropZone');
    const fileInput = document.getElementById('uploadFile');
    if (!zone || !fileInput || zone._bound) return;
    zone._bound = true;
    const pickPdf = (files) => [...(files || [])].find(
      (f) => f.name?.toLowerCase().endsWith('.pdf') || f.type === 'application/pdf'
    );
    zone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
      const f = fileInput.files?.[0];
      const nameEl = document.getElementById('uploadDropFileName');
      if (nameEl) nameEl.textContent = f ? f.name : '';
    });
    ['dragenter', 'dragover'].forEach((evt) => {
      zone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        zone.classList.add('border-sky-500', 'bg-sky-950/30');
      });
    });
    zone.addEventListener('dragleave', (e) => {
      e.preventDefault();
      zone.classList.remove('border-sky-500', 'bg-sky-950/30');
    });
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove('border-sky-500', 'bg-sky-950/30');
      const file = pickPdf(e.dataTransfer?.files);
      if (!file) {
        alert('Drop a PDF file.');
        return;
      }
      setUploadModalFile(file);
    });
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
    if (json.warnings?.length) {
      html += `<div class="text-amber-300 text-xs mb-3 p-2 bg-amber-950/30 border border-amber-800/50 rounded-md">${json.warnings.map(w => esc(w)).join('<br>')}</div>`;
    }
    if (pages.length) {
      const expected = json.expected_page_count || json.page_count;
      const splitNote = json.split_engine ? ` · split via ${esc(json.split_engine)}` : '';
      html += `<p class="text-xs text-zinc-400 mb-3">${expected ? `${expected} page(s) in file · ` : ''}${json.created_count || pages.length} sheet(s) imported${json.split ? ' (split from drawing set)' : ''}${splitNote}</p>`;
      html += `<table class="w-full text-xs"><thead><tr class="text-zinc-400 border-b border-zinc-700">
        <th class="text-left py-2 pr-2">Page</th><th class="text-left py-2 pr-2">Sheet #</th>
        <th class="text-left py-2 pr-2">Proj #</th><th class="text-left py-2 pr-2">Revision</th>
        <th class="text-left py-2 pr-2">Drawing Name</th></tr></thead><tbody>`;
      html += pages.map(p => `<tr class="border-b border-zinc-800 ${p.needs_review ? 'text-amber-200' : ''}">
        <td class="py-2 pr-2">${esc(p.page || '—')}</td>
        <td class="py-2 pr-2 font-mono ${p.needs_review ? 'text-amber-300' : 'text-sky-300'}">${esc(p.sheet_number)}</td>
        <td class="py-2 pr-2 font-mono text-zinc-400">${esc(p.project_number || '—')}</td>
        <td class="py-2 pr-2">${esc(p.revision_label || p.revision_number || '—')}</td>
        <td class="py-2 truncate max-w-[200px]">${esc(p.title || '—')}</td></tr>`).join('');
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
    if (state.deleting) return;
    const d = state.drawings.find(x => x.id === id);
    const label = sheetLabel || d?.sheet_number || 'this sheet';
    const setNote = d?.set_name ? `\n\nSet: ${d.set_name}` : '';
    if (!confirm(`Delete sheet ${label} and all of its revisions?${setNote}\n\nThis cannot be undone.`)) return;
    state.deleting = true;
    toast(`Deleting ${label}…`);
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
      state.selectedDrawingIds.delete(id);
      updateBulkBar();
      toast(`Deleted ${label}`);
      await Promise.all([loadDashboard(), loadDrawings(), loadDrawingSets()]);
    } catch (err) {
      toastError(err.message || 'Delete failed');
    } finally {
      state.deleting = false;
    }
  }

  async function getPdfPageCount(file) {
    if (!file || !global.pdfjsLib) return null;
    try {
      const buf = await file.arrayBuffer();
      const pdf = await pdfjsLib.getDocument({ data: buf.slice(0) }).promise;
      return pdf.numPages;
    } catch {
      return null;
    }
  }

  function appendUploadLog(msg) {
    const log = document.getElementById('uploadProgressLog');
    if (!log) return;
    const line = document.createElement('div');
    line.className = 'py-0.5 text-zinc-300';
    line.textContent = msg;
    log.appendChild(line);
    while (log.children.length > 100) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
  }

  function showUploadProgress(fileName, pageCount) {
    const dlg = document.getElementById('uploadProgressModal');
    const title = document.getElementById('uploadProgressTitle');
    const log = document.getElementById('uploadProgressLog');
    const bar = document.getElementById('uploadProgressBar');
    if (!dlg || !log) return;
    if (title) title.textContent = pageCount ? `Processing ${pageCount} pages — ${fileName}` : `Processing ${fileName}`;
    log.innerHTML = '';
    if (bar) bar.style.width = '6%';
    appendUploadLog('Uploading PDF to server…');
    dlg.showModal();
    clearInterval(state.uploadLogTimer);
    let tick = 0;
    const generic = [
      'Splitting PDF into individual sheets…',
      'Scanning title block regions…',
      'Reading sheet numbers…',
      'Extracting drawing names…',
      'Detecting revisions…',
    ];
    state.uploadLogTimer = setInterval(() => {
      tick++;
      if (pageCount && pageCount > 0) {
        const page = Math.min(pageCount, Math.max(1, Math.ceil((tick * pageCount) / Math.max(pageCount, 12))));
        appendUploadLog(`Analyzing page ${page} of ${pageCount} — title block OCR…`);
        if (bar) bar.style.width = `${Math.min(94, 6 + (page / pageCount) * 88)}%`;
      } else {
        appendUploadLog(generic[tick % generic.length]);
        if (bar) bar.style.width = `${Math.min(94, 6 + tick * 4)}%`;
      }
    }, pageCount && pageCount > 40 ? 350 : 550);
  }

  function finishUploadProgress(json) {
    clearInterval(state.uploadLogTimer);
    state.uploadLogTimer = null;
    const bar = document.getElementById('uploadProgressBar');
    if (bar) bar.style.width = '100%';
    const pages = json.pages || json.drawings || [];
    if (json.warnings?.length) {
      json.warnings.forEach((w) => appendUploadLog(`⚠ ${w}`));
    }
    if (pages.length) {
      appendUploadLog('— Results —');
      pages.forEach(p => {
        const name = p.title || p.drawing_name || '—';
        const flag = p.needs_review ? ' · needs review' : '';
        appendUploadLog(`Page ${p.page || '?'} → ${p.sheet_number} · ${name}${flag}`);
      });
    } else {
      appendUploadLog('Import complete.');
    }
    setTimeout(() => document.getElementById('uploadProgressModal')?.close(), pages.length > 8 ? 2200 : 1400);
  }

  function cancelUploadProgress() {
    clearInterval(state.uploadLogTimer);
    state.uploadLogTimer = null;
    document.getElementById('uploadProgressModal')?.close();
  }

  async function uploadPdfFile(file, setName, extra) {
    if (!file) return null;
    const opts = extra || {};
    const pageCount = await getPdfPageCount(file);
    showUploadProgress(file.name, pageCount);
    const fd = new FormData();
    fd.append('project_id', projectId());
    fd.append('file', file);
    fd.append('set_name', setName || file.name.replace(/\.pdf$/i, '') || 'Drawing Upload');
    if (opts.sheet_number) fd.append('sheet_number', opts.sheet_number);
    if (opts.title) fd.append('title', opts.title);
    try {
      const res = await fetch('/api/drawings/upload', { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        cancelUploadProgress();
        const detail = json.needs_review?.length
          ? `\n\n${json.needs_review.length} page(s) listed for review.`
          : '';
        throw new Error((json.error || 'Upload failed') + detail);
      }
      finishUploadProgress(json);
      return json;
    } catch (e) {
      cancelUploadProgress();
      throw e;
    }
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
        document.getElementById('uploadDrawingModal')?.close();
        const json = await uploadPdfFile(file, file.name.replace(/\.pdf$/i, ''));
        const count = json.created_count || json.drawings?.length || 1;
        const reviewNote = json.needs_review_count ? ` (${json.needs_review_count} need sheet numbers)` : '';
        toast(json.split ? `Imported ${count} sheets from drawing set${reviewNote}` : `Uploaded ${json.drawing?.sheet_number || count + ' sheet(s)'}`);
        showUploadResults(json);
        await Promise.all([loadDashboard(), loadDrawings(), loadDrawingSets()]);
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
      document.getElementById('uploadDrawingModal').close();
      const json = await uploadPdfFile(
        file,
        document.getElementById('uploadSetName').value || 'Drawing Upload',
        {
          sheet_number: document.getElementById('uploadSheetNumber')?.value || '',
          title: document.getElementById('uploadTitle')?.value || '',
        }
      );
      const count = json.created_count || json.drawings?.length || 1;
      const reviewNote = json.needs_review_count ? ` (${json.needs_review_count} need sheet numbers)` : '';
      toast(json.split ? `Imported ${count} sheets from drawing set${reviewNote}` : `Uploaded ${json.drawing?.sheet_number || count + ' sheet(s)'}`);
      showUploadResults(json);
      await Promise.all([loadDashboard(), loadDrawings(), loadDrawingSets()]);
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
      await Promise.all([loadDashboard(), loadDrawings(), loadDrawingSets()]);
    } catch (err) { alert(err.message); }
  }

  function bindFilters() {
    ['drawSearch', 'drawDisciplineFilter', 'drawStatusFilter', 'drawSetFilter'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', () => renderActiveView());
    });
  }

  function toast(msg, isError) {
    const t = document.createElement('div');
    t.className = `fixed bottom-16 right-6 z-[70] px-4 py-2 rounded-md text-sm shadow-lg max-w-sm ${isError ? 'draw-toast-error' : 'bg-emerald-900 text-emerald-100'}`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), isError ? 4500 : 2800);
  }

  function toastError(msg) {
    toast(msg, true);
  }

  async function init() {
    if (!projectId()) { alert('Select a project to manage drawings.'); return; }
    if (global.pdfjsLib) {
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }
    bindFilters();
    bindViewerEvents();
    bindSectionDropZone();
    bindUploadModalDropZone();
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('click', e => {
      if (!e.target.closest('#printMenu') && !e.target.closest('#btnPrintMenu')) {
        document.getElementById('printMenu')?.classList.add('hidden');
      }
    });
    await Promise.all([loadDashboard(), loadDrawings(), loadRfis(), loadDrawingSets()]);
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
    viewRevisionInViewer,
    openCompareDialog,
    startCompare,
    stopCompare,
    setCompareRenderMode,
    toggleCompareOverlay,
    setCompareOpacity,
    detectScale,
    applyScalePreset,
    exportTakeoffToBudget,
    togglePrintMenu,
    printSheet,
    toggleFullscreen,
    openUploadModal,
    openSubstituteModal,
    submitUpload,
    submitSubstitute,
    deleteDrawing,
    deleteSelectedDrawings,
    deleteDrawingSet,
    toggleSelectionMode,
    toggleSheetSelection,
    onSheetClick,
    selectAllVisible,
    clearSelection,
    toggleSelectAllVisible,
    openSetsModal,
    filterBySet,
    loadDrawingSets,
    deletePreviewedSheet,
    deleteOpenSheet,
    showUploadResults,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
