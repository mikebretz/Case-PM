/**
 * Case PM — embedded estimating takeoff viewer (measure / area on drawings in-page or pop-out)
 */
(function (global) {
  'use strict';

  const SCALE_KEY = 'casepm-est-takeoff-scale';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  function channelName(estimateId) {
    return `casepm-est-takeoff-${estimateId || 'project'}`;
  }

  function loadScale(drawingId) {
    try {
      const all = JSON.parse(localStorage.getItem(SCALE_KEY) || '{}');
      return all[String(drawingId)] || null;
    } catch (_) {
      return null;
    }
  }

  function saveScale(drawingId, pixelsPerUnit, label) {
    try {
      const all = JSON.parse(localStorage.getItem(SCALE_KEY) || '{}');
      all[String(drawingId)] = { pixelsPerUnit, label };
      localStorage.setItem(SCALE_KEY, JSON.stringify(all));
    } catch (_) { /* ignore */ }
  }

  function formatFeetInches(feet) {
    if (!Number.isFinite(feet)) return '0"';
    const totalIn = Math.abs(feet) * 12;
    const ft = Math.floor(totalIn / 12);
    const inches = Math.round((totalIn - ft * 12) * 16) / 16;
    if (ft > 0) return `${feet < 0 ? '-' : ''}${ft}'-${inches}"`;
    return `${inches}"`;
  }

  function measureFromPx(pxLen, pixelsPerUnit) {
    if (!pixelsPerUnit) return { value: Math.round(pxLen), unit: 'px', display: `${Math.round(pxLen)} px` };
    const feet = pxLen / pixelsPerUnit;
    return { value: feet, unit: 'ft', display: formatFeetInches(feet) };
  }

  function areaFromPx(pxArea, pixelsPerUnit) {
    if (!pixelsPerUnit) return { value: Math.round(pxArea), unit: 'px', display: `${Math.round(pxArea)} sq px` };
    const sf = pxArea / (pixelsPerUnit * pixelsPerUnit);
    return { value: sf, unit: 'sf', display: `${Math.round(sf).toLocaleString()} SF` };
  }

  function createViewer(root, options) {
    const opts = options || {};
    const state = {
      projectId: opts.projectId,
      estimateId: opts.estimateId,
      drawingId: opts.drawingId || null,
      drawings: [],
      markups: [],
      tool: 'pan',
      scale: 1,
      panX: 0,
      panY: 0,
      pixelsPerUnit: null,
      scaleLabel: '',
      pdfDoc: null,
      pdfPage: 1,
      pageW: 0,
      pageH: 0,
      dragging: false,
      dragStart: null,
      pointA: null,
      pointB: null,
      pointPhase: null,
      tempPoints: [],
      channel: null,
      popout: !!opts.popout,
    };

    root.innerHTML = `
      <div class="ett-wrap flex flex-col h-full min-h-0 border border-zinc-700 rounded-md bg-zinc-950 overflow-hidden">
        <div class="ett-toolbar flex flex-wrap gap-2 items-center p-2 border-b border-zinc-800 bg-zinc-900 flex-shrink-0">
          <select class="ett-drawing-select bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-xs min-w-[140px]"></select>
          <button type="button" data-tool="pan" class="ett-tool px-2 py-1.5 rounded text-xs bg-zinc-800" title="Pan"><i class="fa-solid fa-hand"></i></button>
          <button type="button" data-tool="measure" class="ett-tool px-2 py-1.5 rounded text-xs bg-zinc-800" title="Measure"><i class="fa-solid fa-ruler"></i></button>
          <button type="button" data-tool="rect" class="ett-tool px-2 py-1.5 rounded text-xs bg-zinc-800" title="Area rectangle"><i class="fa-solid fa-vector-square"></i></button>
          <button type="button" data-tool="calibrate" class="ett-tool px-2 py-1.5 rounded text-xs bg-zinc-800" title="Calibrate scale"><i class="fa-solid fa-ruler-combined"></i></button>
          <span class="ett-scale text-xs text-zinc-500 ml-1">Scale: not set</span>
          ${opts.popout ? '' : '<button type="button" class="ett-popout px-2 py-1.5 rounded text-xs bg-sky-800 hover:bg-sky-700 ml-auto" title="Open on second monitor"><i class="fa-solid fa-up-right-from-square mr-1"></i>Pop Out</button>'}
        </div>
        <div class="ett-viewport flex-1 min-h-0 relative overflow-hidden cursor-grab">
          <div class="ett-stage absolute top-0 left-0" style="transform-origin:0 0">
            <canvas class="ett-pdf block"></canvas>
            <svg class="ett-overlay absolute top-0 left-0 pointer-events-none" style="overflow:visible"></svg>
          </div>
        </div>
        <div class="ett-status text-[10px] text-zinc-500 px-2 py-1 border-t border-zinc-800 flex-shrink-0">Alt+drag to pan · Scroll to zoom</div>
      </div>`;

    const viewport = root.querySelector('.ett-viewport');
    const stage = root.querySelector('.ett-stage');
    const canvas = root.querySelector('.ett-pdf');
    const overlay = root.querySelector('.ett-overlay');
    const ctx = canvas.getContext('2d');
    const select = root.querySelector('.ett-drawing-select');
    const scaleEl = root.querySelector('.ett-scale');

    function broadcast(type, data) {
      try {
        state.channel?.postMessage({ type, ...data, estimateId: state.estimateId, drawingId: state.drawingId });
      } catch (_) { /* ignore */ }
    }

    function setTool(tool) {
      state.tool = tool;
      state.pointA = state.pointB = state.pointPhase = null;
      state.tempPoints = [];
      root.querySelectorAll('.ett-tool').forEach(btn => {
        btn.classList.toggle('bg-emerald-700', btn.dataset.tool === tool);
        btn.classList.toggle('bg-zinc-800', btn.dataset.tool !== tool);
      });
      viewport.classList.toggle('cursor-crosshair', tool !== 'pan');
      viewport.classList.toggle('cursor-grab', tool === 'pan');
    }

    function applyTransform() {
      stage.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
    }

    function screenToWorld(clientX, clientY) {
      const rect = viewport.getBoundingClientRect();
      const x = (clientX - rect.left - state.panX) / state.scale;
      const y = (clientY - rect.top - state.panY) / state.scale;
      return { x, y };
    }

    function updateScaleLabel() {
      scaleEl.textContent = state.scaleLabel
        ? `Scale: ${state.scaleLabel}`
        : (state.pixelsPerUnit ? 'Scale: Calibrated' : 'Scale: not set — calibrate');
    }

    function renderMarkups() {
      const items = state.markups.filter(m => ['measure', 'rect', 'cloud', 'area'].includes(m.markup_type));
      overlay.setAttribute('width', state.pageW);
      overlay.setAttribute('height', state.pageH);
      overlay.innerHTML = items.map(m => {
        const g = m.geometry || {};
        const color = (m.style && m.style.color) || '#22c55e';
        if (m.markup_type === 'measure' && g.points && g.points.length >= 4) {
          const [x1, y1, x2, y2] = g.points;
          const label = m.measurement_value != null ? measureFromPx(
            Math.hypot(x2 - x1, y2 - y1), state.pixelsPerUnit,
          ).display : '';
          return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="2"/>
            <text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 6}" fill="${color}" font-size="12" text-anchor="middle">${esc(label)}</text>`;
        }
        if ((m.markup_type === 'rect' || m.markup_type === 'cloud') && g.x != null) {
          const w = g.w || 0;
          const h = g.h || 0;
          const label = m.measurement_value != null
            ? `${Math.round(m.measurement_value)} ${m.measurement_unit || 'SF'}`
            : areaFromPx(Math.abs(w * h), state.pixelsPerUnit).display;
          return `<rect x="${g.x}" y="${g.y}" width="${w}" height="${h}" fill="rgba(34,197,94,0.12)" stroke="${color}" stroke-width="2"/>
            <text x="${g.x + w / 2}" y="${g.y + h / 2}" fill="${color}" font-size="12" text-anchor="middle">${esc(label)}</text>`;
        }
        return '';
      }).join('');
      if (state.pointA && state.pointB) {
        overlay.innerHTML += `<line x1="${state.pointA.x}" y1="${state.pointA.y}" x2="${state.pointB.x}" y2="${state.pointB.y}" stroke="#38bdf8" stroke-width="2" stroke-dasharray="4"/>`;
      }
    }

    async function loadDrawing(drawingId) {
      if (!drawingId) return;
      state.drawingId = drawingId;
      const detail = await api(`/api/drawings/${drawingId}`);
      state.markups = detail.markups || [];
      const scale = loadScale(drawingId);
      if (scale) {
        state.pixelsPerUnit = scale.pixelsPerUnit;
        state.scaleLabel = scale.label || '';
      } else {
        state.pixelsPerUnit = null;
        state.scaleLabel = '';
      }
      updateScaleLabel();
      if (!detail.file_url) throw new Error('Drawing has no PDF file');
      if (!global.pdfjsLib) throw new Error('PDF.js not loaded');
      global.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      const pdf = await global.pdfjsLib.getDocument(detail.file_url).promise;
      state.pdfDoc = pdf;
      const page = await pdf.getPage(1);
      const vp = page.getViewport({ scale: 1.5 });
      state.pageW = vp.width;
      state.pageH = vp.height;
      canvas.width = vp.width;
      canvas.height = vp.height;
      await page.render({ canvasContext: ctx, viewport: vp }).promise;
      fitToView();
      renderMarkups();
      broadcast('drawing-changed', { drawingId });
    }

    function fitToView() {
      const rect = viewport.getBoundingClientRect();
      if (!state.pageW) return;
      state.scale = Math.min(rect.width / state.pageW, rect.height / state.pageH, 2) * 0.95;
      state.panX = (rect.width - state.pageW * state.scale) / 2;
      state.panY = (rect.height - state.pageH * state.scale) / 2;
      applyTransform();
    }

    async function saveMarkup(payload) {
      const json = await api(`/api/drawings/${state.drawingId}/markups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, publish: true, layer: 'published' }),
      });
      if (json.markup) {
        state.markups.push(json.markup);
        renderMarkups();
        broadcast('markup-saved', { markup: json.markup });
      }
      return json.markup;
    }

    async function finishMeasure(x1, y1, x2, y2) {
      const pxLen = Math.hypot(x2 - x1, y2 - y1);
      if (pxLen < 3) return;
      const info = measureFromPx(pxLen, state.pixelsPerUnit);
      await saveMarkup({
        markup_type: 'measure',
        geometry: { points: [x1, y1, x2, y2], offset: 0 },
        measurement_value: info.value,
        measurement_unit: info.unit,
        style: { color: '#22c55e', lineWidth: 2 },
        label: info.display,
      });
    }

    async function finishRect(x1, y1, x2, y2) {
      const x = Math.min(x1, x2);
      const y = Math.min(y1, y2);
      const w = Math.abs(x2 - x1);
      const h = Math.abs(y2 - y1);
      if (w < 3 || h < 3) return;
      const info = areaFromPx(w * h, state.pixelsPerUnit);
      await saveMarkup({
        markup_type: 'rect',
        geometry: { x, y, w, h },
        measurement_value: info.value,
        measurement_unit: info.unit,
        style: { color: '#22c55e', lineWidth: 2, fillOpacity: 0.15 },
        label: info.display,
      });
    }

    async function finishCalibrate(x1, y1, x2, y2) {
      const pxLen = Math.hypot(x2 - x1, y2 - y1);
      if (pxLen < 3) return;
      const input = global.CasePMDialog?.prompt
        ? await global.CasePMDialog.prompt('Known length (feet):', '10', { title: 'Calibrate Scale' })
        : prompt('Known length in feet:', '10');
      if (input == null) return;
      const feet = parseFloat(input) || 0;
      if (!feet) return;
      state.pixelsPerUnit = pxLen / feet;
      state.scaleLabel = `Calibrated (${feet} ft)`;
      saveScale(state.drawingId, state.pixelsPerUnit, state.scaleLabel);
      updateScaleLabel();
    }

    async function onPointerUp(e) {
      if (!state.dragging) return;
      state.dragging = false;
      const pt = screenToWorld(e.clientX, e.clientY);
      const start = state.dragStart;
      state.dragStart = null;
      if (!start) return;
      if (state.tool === 'pan') return;
      if (state.tool === 'calibrate') {
        await finishCalibrate(start.x, start.y, pt.x, pt.y);
        state.pointA = state.pointB = null;
        renderMarkups();
        return;
      }
      if (state.tool === 'measure') {
        if (!state.pointA) {
          state.pointA = start;
          state.pointB = pt;
          renderMarkups();
          return;
        }
        await finishMeasure(state.pointA.x, state.pointA.y, pt.x, pt.y);
        state.pointA = state.pointB = null;
        renderMarkups();
        return;
      }
      if (state.tool === 'rect') {
        await finishRect(start.x, start.y, pt.x, pt.y);
        renderMarkups();
      }
    }

    viewport.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      state.dragging = true;
      state.dragStart = screenToWorld(e.clientX, e.clientY);
      if (state.tool === 'pan') state._panOrigin = { x: e.clientX - state.panX, y: e.clientY - state.panY };
    });
    window.addEventListener('mousemove', e => {
      if (!state.dragging) return;
      if (state.tool === 'pan' && state._panOrigin) {
        state.panX = e.clientX - state._panOrigin.x;
        state.panY = e.clientY - state._panOrigin.y;
        applyTransform();
        return;
      }
      const pt = screenToWorld(e.clientX, e.clientY);
      if (state.tool === 'measure' && state.pointA) {
        state.pointB = pt;
        renderMarkups();
      }
    });
    window.addEventListener('mouseup', onPointerUp);
    viewport.addEventListener('wheel', e => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.9;
      const before = screenToWorld(e.clientX, e.clientY);
      state.scale = Math.min(8, Math.max(0.15, state.scale * factor));
      const rect = viewport.getBoundingClientRect();
      state.panX = e.clientX - rect.left - before.x * state.scale;
      state.panY = e.clientY - rect.top - before.y * state.scale;
      applyTransform();
    }, { passive: false });

    root.querySelectorAll('.ett-tool').forEach(btn => {
      btn.addEventListener('click', () => setTool(btn.dataset.tool));
    });
    select.addEventListener('change', () => loadDrawing(parseInt(select.value, 10)).catch(err => {
      root.querySelector('.ett-status').textContent = err.message;
    }));
    root.querySelector('.ett-popout')?.addEventListener('click', () => {
      const q = new URLSearchParams({
        project_id: state.projectId,
        estimate_id: state.estimateId,
        drawing_id: state.drawingId || '',
      });
      const w = window.open(`/estimating/takeoff-popout?${q}`, 'casepm-est-takeoff', 'width=1200,height=800,resizable=yes');
      if (w) w.focus();
    });

    async function init() {
      if (typeof BroadcastChannel !== 'undefined') {
        state.channel = new BroadcastChannel(channelName(state.estimateId));
        state.channel.onmessage = ev => {
          const msg = ev.data || {};
          if (msg.estimateId && msg.estimateId !== state.estimateId) return;
          if (msg.type === 'drawing-changed' && msg.drawingId && msg.drawingId !== state.drawingId) {
            select.value = String(msg.drawingId);
            loadDrawing(msg.drawingId).catch(() => {});
          }
          if (msg.type === 'markup-saved' && msg.drawingId === state.drawingId) {
            loadDrawing(state.drawingId).catch(() => {});
          }
          if (msg.type === 'refresh-takeoff') {
            loadDrawing(state.drawingId).catch(() => {});
          }
        };
      }
      const live = await api(`/api/estimates/${state.estimateId}/takeoff-live`);
      state.drawings = live.drawings || [];
      select.innerHTML = state.drawings.map(d =>
        `<option value="${d.id}">${esc(d.sheet_number)} — ${esc(d.title || '')}</option>`,
      ).join('') || '<option value="">No drawings</option>';
      const initial = opts.drawingId || state.drawings[0]?.id;
      if (initial) {
        select.value = String(initial);
        await loadDrawing(initial);
      }
      setTool('measure');
    }

    init().catch(err => {
      root.querySelector('.ett-status').textContent = err.message;
    });

    return {
      refresh: () => loadDrawing(state.drawingId).catch(() => {}),
      broadcastRefresh: () => broadcast('refresh-takeoff', {}),
    };
  }

  global.CasePMEstimateTakeoff = {
    init(container, options) {
      const el = typeof container === 'string' ? document.querySelector(container) : container;
      if (!el) return null;
      return createViewer(el, options);
    },
    channelName,
  };
})(window);
