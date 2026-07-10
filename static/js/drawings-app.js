/**
 * Case PM — Drawings module (Procore / Bluebeam / ACC / Fieldwire parity)
 */
(function (global) {
  'use strict';

  const SECTION_ORDER = ['G', 'C', 'A', 'S', 'M', 'E', 'P', 'FP', 'L', 'T', 'I', 'OTHER'];
  const MARKUP_TOOLS = [
    'pan', 'select',
    'pen', 'line', 'polyline', 'arrow', 'rect', 'ellipse', 'polygon', 'cloud', 'crossout', 'highlight',
    'text', 'callout', 'stamp',
    'measure', 'area', 'count', 'calibrate',
    'rfi_pin', 'punch_pin', 'co_pin',
  ];

  const STAMP_PRESETS = [
    { label: 'APPROVED', value: 'APPROVED', color: '#22c55e' },
    { label: 'REJECTED', value: 'REJECTED', color: '#ef4444' },
    { label: 'REVISE', value: 'REVISE & RESUBMIT', color: '#f97316' },
    { label: 'REVIEWED', value: 'REVIEWED', color: '#38bdf8' },
    { label: 'VERIFIED', value: 'VERIFIED', color: '#a78bfa' },
    { label: 'VOID', value: 'VOID', color: '#71717a' },
    { label: 'AS NOTED', value: 'AS NOTED', color: '#facc15' },
  ];

  const TOOL_PALETTE_GROUPS = [
    { label: 'Navigation', tools: ['pan', 'select'] },
    { label: 'Freehand & lines', tools: ['pen', 'line', 'polyline', 'arrow'] },
    { label: 'Shapes', tools: ['rect', 'ellipse', 'polygon', 'cloud', 'crossout', 'highlight'] },
    { label: 'Text & stamps', tools: ['text', 'callout', 'stamp'] },
    { label: 'Measure', tools: ['measure', 'area', 'count', 'calibrate'] },
    { label: 'Field pins', tools: ['rfi_pin', 'co_pin', 'punch_pin'] },
  ];

  const TOOL_STYLE_DEFAULTS = {
    cloud: { color: '#ef4444', lineWidth: 2, opacity: 1, fillOpacity: 0, cloudScallop: 18 },
    highlight: { color: '#facc15', lineWidth: 1, opacity: 0.35, fillOpacity: 0.35 },
    measure: { color: '#22c55e', lineWidth: 2 },
    area: { color: '#22c55e', lineWidth: 2, fillOpacity: 0.15 },
    pen: { color: '#ef4444', lineWidth: 2, opacity: 1 },
    sketch: { color: '#ef4444', lineWidth: 2, opacity: 1 },
    polyline: { color: '#38bdf8', lineWidth: 2 },
    polygon: { color: '#38bdf8', lineWidth: 2, fillOpacity: 0.12 },
    crossout: { color: '#ef4444', lineWidth: 3 },
    count: { color: '#f97316', lineWidth: 2 },
    stamp: { color: '#22c55e', lineWidth: 2, fontSize: 12 },
    text: { color: '#f4f4f5', lineWidth: 1, fillOpacity: 0.9, fontSize: 14, showTextBorder: true },
    textbox: { color: '#f4f4f5', lineWidth: 1, fillOpacity: 0.9, fontSize: 14, showTextBorder: true },
    callout: { color: '#38bdf8', lineWidth: 2, fontSize: 13, fillOpacity: 0.92, showTextBorder: true, bubbleRadius: 10 },
  };

  const TWO_POINT_HINT = 'Click two points (pan/zoom between clicks with Alt+drag), or click-hold and drag.';

  const TOOL_META = {
    pan: { label: 'Pan', shortcut: 'H', icon: 'fa-hand', hint: 'Drag to move the sheet. Hold Alt to pan while using any tool.' },
    select: { label: 'Select', shortcut: 'V', icon: 'fa-arrow-pointer', hint: 'Click to select; Shift+click to add/remove. Drag a box to select everything inside. Drag selected items to move.' },
    pen: { label: 'Pen', shortcut: 'N', icon: 'fa-pen', hint: 'Draw freehand — popular for quick redlines and sketches (Bluebeam-style).' },
    line: { label: 'Line', shortcut: 'L', icon: 'fa-minus', hint: TWO_POINT_HINT },
    polyline: { label: 'Polyline', shortcut: 'I', icon: 'fa-draw-polygon', hint: 'Click each corner. Press Enter or double-click the last point to finish.' },
    arrow: { label: 'Arrow', shortcut: 'A', icon: 'fa-arrow-right', hint: TWO_POINT_HINT },
    rect: { label: 'Rectangle', shortcut: 'R', icon: 'fa-square', hint: TWO_POINT_HINT },
    ellipse: { label: 'Ellipse', shortcut: 'E', icon: 'fa-circle', hint: TWO_POINT_HINT },
    polygon: { label: 'Polygon', shortcut: 'G', icon: 'fa-shapes', hint: 'Click each vertex. Press Enter to close the shape.' },
    cloud: { label: 'Revision cloud', shortcut: 'U', icon: 'fa-cloud', hint: TWO_POINT_HINT },
    crossout: { label: 'Cross-out', shortcut: 'X', icon: 'fa-xmark', hint: TWO_POINT_HINT },
    highlight: { label: 'Highlight', shortcut: 'Y', icon: 'fa-highlighter', hint: TWO_POINT_HINT },
    text: { label: 'Text box', shortcut: 'T', icon: 'fa-font', hint: TWO_POINT_HINT },
    callout: { label: 'Callout bubble', shortcut: 'C', icon: 'fa-comment-dots', hint: 'Click the callout point, then the opposite corner of the bubble — or drag. Pan/zoom between clicks.' },
    stamp: { label: 'Stamp', shortcut: 'S', icon: 'fa-stamp', hint: 'Pick a stamp in the side panel, then click on the sheet to place it.' },
    measure: { label: 'Measure', shortcut: 'M', icon: 'fa-ruler', hint: 'Click two points (pan/zoom between clicks), then click to place the dimension line with extension lines — or drag A→B in one motion.' },
    area: { label: 'Area', shortcut: 'B', icon: 'fa-vector-square', hint: 'Click polygon corners, Enter to close — shows square feet when scale is set.' },
    count: { label: 'Count', shortcut: 'O', icon: 'fa-hashtag', hint: 'Click each item to count — Bluebeam-style running tally.' },
    calibrate: { label: 'Calibrate scale', shortcut: 'K', icon: 'fa-ruler-combined', hint: 'Click two points on a known dimension, then enter the real-world length.' },
    rfi_pin: { label: 'RFI pin', shortcut: 'F', icon: 'fa-map-pin', hint: 'Click the exact spot on the plan, then drag the label out of the way. Double-click the label to open that RFI.' },
    co_pin: { label: 'CO pin', shortcut: 'D', icon: 'fa-file-signature', hint: 'Pin a change order to the sheet. Drag the label aside; double-click to open the CO.' },
    punch_pin: { label: 'Punch pin', shortcut: 'J', icon: 'fa-thumbtack', hint: 'Pin a punch list item. Drag the label aside; double-click to open the item.' },
  };

  const TOOL_SHORTCUTS = {};
  Object.entries(TOOL_META).forEach(([tool, meta]) => {
    if (meta.shortcut) TOOL_SHORTCUTS[meta.shortcut.toLowerCase()] = tool;
  });

  const TWO_POINT_CLICK_TOOLS = [
    'line', 'rect', 'cloud', 'arrow', 'highlight', 'ellipse', 'callout', 'text', 'crossout', 'calibrate',
  ];

  function isTwoPointClickTool(tool) {
    return tool === 'measure' || TWO_POINT_CLICK_TOOLS.includes(tool);
  }

  async function drawConfirm(message, options) {
    if (global.CasePMDialog?.confirm) return global.CasePMDialog.confirm(message, options || {});
    return confirm(message);
  }

  async function drawPrompt(message, defaultValue, options) {
    if (global.CasePMDialog?.prompt) return global.CasePMDialog.prompt(message, defaultValue, options || {});
    return prompt(message, defaultValue);
  }

  async function drawSelect(options) {
    if (global.CasePMDialog?.select) return global.CasePMDialog.select(options || {});
    return null;
  }

  function pointsToPath(points, closed) {
    if (!points || points.length < 4) return '';
    let d = `M ${points[0]} ${points[1]}`;
    for (let i = 2; i < points.length; i += 2) {
      d += ` L ${points[i]} ${points[i + 1]}`;
    }
    if (closed) d += ' Z';
    return d;
  }

  function polygonAreaPx(points) {
    if (!points || points.length < 6) return 0;
    let area = 0;
    const n = points.length / 2;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      area += points[i * 2] * points[j * 2 + 1];
      area -= points[j * 2] * points[i * 2 + 1];
    }
    return Math.abs(area) / 2;
  }

  function formatAreaDisplay(pxArea) {
    if (!state.pixelsPerUnit) return `${Math.round(pxArea).toLocaleString()} sq px`;
    const sqFt = pxArea / (state.pixelsPerUnit * state.pixelsPerUnit);
    return `${Math.round(sqFt).toLocaleString()} SF`;
  }

  function renderToolPaletteHtml() {
    return `<div class="mb-3 pb-2 border-b border-zinc-700/80">
      <div class="text-[10px] uppercase text-zinc-500 mb-2">All markup tools</div>
      ${TOOL_PALETTE_GROUPS.map((group) => `
        <div class="mb-2">
          <div class="text-[9px] uppercase text-zinc-600 mb-1">${esc(group.label)}</div>
          <div class="grid grid-cols-3 gap-1">
            ${group.tools.map((tool) => {
              const meta = TOOL_META[tool] || { label: tool, icon: 'fa-shapes' };
              const active = state.tool === tool ? ' palette-active' : '';
              return `<button type="button" class="draw-palette-btn${active}" data-palette-tool="${tool}" title="${esc(meta.hint || meta.label)}">
                <i class="fa-solid ${meta.icon || 'fa-shapes'}"></i>${esc(meta.label)}</button>`;
            }).join('')}
          </div>
        </div>
      `).join('')}
    </div>`;
  }

  function gcd(a, b) {
    a = Math.abs(Math.round(a));
    b = Math.abs(Math.round(b));
    while (b) { const t = b; b = a % b; a = t; }
    return a || 1;
  }

  /** Architectural feet-inches from decimal feet (e.g. 2.125 → 2'-1 1/2"). */
  function formatFeetInches(decimalFeet, denom) {
    denom = denom || 16;
    if (decimalFeet == null || !Number.isFinite(decimalFeet)) return '0"';
    const neg = decimalFeet < 0;
    const feetDec = Math.abs(decimalFeet);
    const totalIn = feetDec * 12;
    let ft = Math.floor(totalIn / 12);
    let inches = totalIn - ft * 12;
    let inWhole = Math.floor(inches);
    let frac = inches - inWhole;
    let num = Math.round(frac * denom);
    if (num >= denom) { inWhole += 1; num = 0; }
    if (inWhole >= 12) { ft += 1; inWhole -= 12; }

    let inchStr;
    if (num === 0) {
      inchStr = `${inWhole}`;
    } else {
      const g = gcd(num, denom);
      num /= g;
      const d = denom / g;
      inchStr = inWhole > 0 ? `${inWhole} ${num}/${d}` : `${num}/${d}`;
    }

    const prefix = neg ? '-' : '';
    if (ft > 0) {
      if (inWhole === 0 && num === 0) return `${prefix}${ft}'-0"`;
      return `${prefix}${ft}'-${inchStr}"`;
    }
    if (inWhole === 0 && num === 0) return '0"';
    return `${prefix}${inchStr}"`;
  }

  function formatMeasurementDisplay(m) {
    if (m.measurement_value == null) return '';
    const unit = m.measurement_unit || '';
    if (unit === 'sf' || unit === 'sq ft' || m.markup_type === 'area') {
      const val = parseFloat(m.measurement_value);
      if (Number.isFinite(val)) return `${Math.round(val).toLocaleString()} SF`;
    }
    if (unit === 'px' || (!state.pixelsPerUnit && unit !== 'ft-in' && unit !== 'ft')) {
      return `${Math.round(m.measurement_value)} px`;
    }
    const feet = parseFloat(m.measurement_value);
    if (!Number.isFinite(feet)) return String(m.measurement_value);
    return formatFeetInches(feet);
  }

  function calloutLeaderAnchor(bx, by, bw, bh, tipX, tipY) {
    const cx = bx + bw / 2;
    const cy = by + bh / 2;
    const dx = tipX - cx;
    const dy = tipY - cy;
    if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return { x: cx, y: by + bh };
    const hw = bw / 2;
    const hh = bh / 2;
    const scaleX = dx !== 0 ? hw / Math.abs(dx) : Infinity;
    const scaleY = dy !== 0 ? hh / Math.abs(dy) : Infinity;
    const t = Math.min(scaleX, scaleY);
    return { x: cx + dx * t, y: cy + dy * t };
  }

  function calloutBubbleSvg(opts) {
    const {
      bx, by, bw, bh, tipX, tipY, color, sw, op, fillOp, style, label, placeholder, rx,
    } = opts;
    const anchor = calloutLeaderAnchor(bx, by, bw, bh, tipX, tipY);
    const fillOpVal = fillOp != null ? fillOp : 0.9;
    const bg = `rgba(24,24,27,${fillOpVal})`;
    const borderRx = rx || style?.bubbleRadius || 10;
    const geom = { x: bx, y: by, w: bw, h: bh };
    const displayLabel = label || (placeholder ? '' : '');
    const ta = textMarkupAttrs(style || {}, geom, displayLabel || placeholder || 'Double-click to edit');
    const textColor = style?.color || color;
    const textOpacity = displayLabel ? op : op * 0.55;
    return `
      <line x1="${tipX}" y1="${tipY}" x2="${anchor.x}" y2="${anchor.y}" stroke="${color}" stroke-width="${sw}" opacity="${op}" pointer-events="none"/>
      <circle cx="${tipX}" cy="${tipY}" r="3.5" fill="${color}" stroke="#fff" stroke-width="1" opacity="${op}" pointer-events="none"/>
      <rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="${borderRx}" ry="${borderRx}" stroke="${color}" stroke-width="${sw}" fill="${bg}" opacity="${op}" pointer-events="none"/>
      <text x="${ta.tx}" y="${by + ta.pad}" text-anchor="${ta.anchor}" fill="${textColor}" font-size="${ta.fs}" font-weight="${ta.weight}" font-style="${ta.italic}" opacity="${textOpacity}" pointer-events="none">${ta.tspans}</text>`;
  }

  function measureDimensionVisual(ax, ay, bx, by, offset, color, sw, op, labelText) {
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len;
    const uy = dy / len;
    const vx = -uy;
    const vy = ux;
    const off = offset || 0;
    const dax = ax + vx * off;
    const day = ay + vy * off;
    const dbx = bx + vx * off;
    const dby = by + vy * off;
    const cap = 7;
    const cdx = ux * cap;
    const cdy = uy * cap;
    const label = labelText
      ? `<text x="${(dax + dbx) / 2 + vx * 14}" y="${(day + dby) / 2 + vy * 14}" fill="${color}" font-size="12" font-weight="bold" text-anchor="middle" stroke="#09090b" stroke-width="3" paint-order="stroke">${esc(labelText)}</text>`
      : '';
    return `
      <line x1="${ax}" y1="${ay}" x2="${dax}" y2="${day}" stroke="${color}" stroke-width="${sw}" opacity="${op}" pointer-events="none"/>
      <line x1="${bx}" y1="${by}" x2="${dbx}" y2="${dby}" stroke="${color}" stroke-width="${sw}" opacity="${op}" pointer-events="none"/>
      <line x1="${dax}" y1="${day}" x2="${dbx}" y2="${dby}" stroke="${color}" stroke-width="${sw}" opacity="${op}" pointer-events="none"/>
      <line x1="${dax - vy * cap}" y1="${day + vx * cap}" x2="${dax + vy * cap}" y2="${day - vx * cap}" stroke="${color}" stroke-width="${sw}" opacity="${op}" pointer-events="none"/>
      <line x1="${dbx - vy * cap}" y1="${dby + vx * cap}" x2="${dbx + vy * cap}" y2="${dby - vx * cap}" stroke="${color}" stroke-width="${sw}" opacity="${op}" pointer-events="none"/>
      ${label}`;
  }

  function measureLineVisual(x1, y1, x2, y2, color, sw, op, labelText) {
    return measureDimensionVisual(x1, y1, x2, y2, 0, color, sw, op, labelText);
  }

  function measurePerpOffset(ax, ay, bx, by, px, py) {
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy) || 1;
    const vx = -dy / len;
    const vy = dx / len;
    return (px - ax) * vx + (py - ay) * vy;
  }

  function resetPointToolState() {
    state.pointPhase = null;
    state.pointA = null;
    state.pointB = null;
    state.pointOffset = 0;
    state.pointPointerDown = false;
    state.pointDownPt = null;
    state.pointDidDrag = false;
    state.drawing = false;
    state.drawStart = null;
  }

  function resetMeasureState() {
    resetPointToolState();
  }

  function pointToolPreviewMarkup() {
    const color = toolStyle(state.tool).color || '#38bdf8';
    const sw = toolStyle(state.tool).lineWidth || 2;
    if (state.tool === 'measure' && state.pointPhase === 'offset' && state.pointA && state.pointB) {
      const pxLen = Math.hypot(state.pointB.x - state.pointA.x, state.pointB.y - state.pointA.y);
      return measureDimensionVisual(
        state.pointA.x, state.pointA.y,
        state.pointB.x, state.pointB.y,
        state.pointOffset, color, sw, 0.9,
        formatMeasureLength(pxLen).display,
      );
    }
    if (state.pointPhase === 'second' && state.pointA) {
      return pointAnchorMarkup(state.pointA, color);
    }
    return '';
  }

  function pointAnchorMarkup(anchor, color) {
    const pt = anchor || state.pointA;
    if (!pt || !isTwoPointClickTool(state.tool)) return '';
    const c = color || toolStyle(state.tool).color || '#38bdf8';
    return `<circle cx="${pt.x}" cy="${pt.y}" r="6" fill="${c}" stroke="#fff" stroke-width="2"/>`
      + `<circle cx="${pt.x}" cy="${pt.y}" r="14" fill="none" stroke="${c}" stroke-width="1.5" stroke-dasharray="3 2" opacity="0.85"/>`;
  }

  function buildTwoPointPreview(tool, ax, ay, bx, by) {
    const activeStyle = toolStyle(tool);
    const sw = activeStyle.lineWidth || 2;
    const color = activeStyle.color || '#38bdf8';
    const scallop = activeStyle.cloudScallop || 18;
    if (['rect', 'highlight', 'ellipse', 'text', 'crossout'].includes(tool)) {
      const x = Math.min(ax, bx);
      const y = Math.min(ay, by);
      const rw = Math.abs(bx - ax);
      const rh = Math.abs(by - ay);
      if (tool === 'ellipse') {
        return `<ellipse cx="${x + rw / 2}" cy="${y + rh / 2}" rx="${rw / 2}" ry="${rh / 2}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
      }
      return `<rect x="${x}" y="${y}" width="${rw}" height="${rh}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
    }
    if (tool === 'callout') {
      const x = Math.min(ax, bx);
      const y = Math.min(ay, by);
      const rw = Math.max(Math.abs(bx - ax), 80);
      const rh = Math.max(Math.abs(by - ay), 36);
      return calloutBubbleSvg({
        bx: x, by: y, bw: rw, bh: rh,
        tipX: ax, tipY: ay,
        color, sw, op: 0.85,
        fillOp: activeStyle.fillOpacity ?? 0.5,
        style: activeStyle,
        placeholder: true,
      });
    }
    if (tool === 'cloud') {
      const x = Math.min(ax, bx);
      const y = Math.min(ay, by);
      return `<path d="${cloudPath(x, y, Math.abs(bx - ax), Math.abs(by - ay), scallop)}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
    }
    if (tool === 'line' || tool === 'arrow' || tool === 'calibrate') {
      const marker = tool === 'arrow' ? ' marker-end="url(#arrowhead)"' : '';
      return `<line x1="${ax}" y1="${ay}" x2="${bx}" y2="${by}" stroke="${color}" stroke-width="${sw}" stroke-dasharray="4 3"${marker} />`;
    }
    if (tool === 'measure') {
      const pxLen = Math.hypot(bx - ax, by - ay);
      return measureLineVisual(ax, ay, bx, by, color, sw, 0.85, formatMeasureLength(pxLen).display);
    }
    return '';
  }

  async function runCalibrateBetween(ax, ay, bx, by) {
    const dist = await drawPrompt('', '10\'-0"', {
      title: 'Calibrate scale',
      label: 'Known distance (feet & inches, e.g. 10\'-6" or 10.5)',
      placeholder: '10\'-0"',
      submitLabel: 'Set scale',
    });
    if (!dist) return;
    const px = Math.hypot(bx - ax, by - ay);
    if (px < 3) return;
    let feet = parseFloat(dist);
    if (!Number.isFinite(feet)) {
      const arch = dist.match(/(\d+)\s*['′-]\s*(\d+)?/);
      if (arch) feet = parseInt(arch[1], 10) + (parseInt(arch[2] || '0', 10) / 12);
      else feet = parseFloat(dist) || 1;
    }
    state.pixelsPerUnit = px / (feet || 1);
    state.scaleLabel = `Calibrated (${formatFeetInches(feet)})`;
    state.scalePdfPointsPerFoot = null;
    renderPropertiesPanel();
    updateViewerStatusBar();
    toast(`Scale set — ${formatFeetInches(feet)} on drawing`);
  }

  async function finishTwoPointMarkup(tool, ax, ay, bx, by, opts) {
    if (tool === 'measure') {
      await saveMeasureLine(ax, ay, bx, by, opts?.offset || 0);
      return;
    }
    if (tool === 'calibrate') {
      await runCalibrateBetween(ax, ay, bx, by);
      resetPointToolState();
      state.tempMarkup = null;
      renderMarkupOverlay();
      return;
    }
    let geometry = {};
    let measurement_value = null;
    let label = null;
    if (['rect', 'cloud', 'highlight', 'ellipse', 'text', 'crossout'].includes(tool)) {
      geometry = { x: Math.min(ax, bx), y: Math.min(ay, by), w: Math.abs(bx - ax), h: Math.abs(by - ay) };
      if (geometry.w < 3 && geometry.h < 3) {
        if (tool === 'text') {
          const hit = hitTestMarkup({ x: bx, y: by });
          if (hit && (hit.markup_type === 'text' || hit.markup_type === 'textbox')) {
            setMarkupSelection(new Set([hit.id]), hit.id);
            showTextEditor({ x: bx, y: by }, hit);
          }
        }
        resetPointToolState();
        state.tempMarkup = null;
        renderMarkupOverlay();
        return;
      }
      if (tool === 'text') {
        resetPointToolState();
        state.tempMarkup = null;
        showTextEditor({ x: geometry.x + 8, y: geometry.y + 8 }, null, geometry);
        return;
      }
    } else if (tool === 'callout') {
      const bxx = Math.min(ax, bx);
      const byy = Math.min(ay, by);
      const bw = Math.max(Math.abs(bx - ax), 80);
      const bh = Math.max(Math.abs(by - ay), 36);
      geometry = {
        x: bxx, y: byy, w: bw, h: bh,
        points: [ax, ay, bxx + bw, byy + bh],
        tipX: ax, tipY: ay,
      };
      if (bw < 24 && bh < 20) {
        resetPointToolState();
        state.tempMarkup = null;
        renderMarkupOverlay();
        return;
      }
      label = '';
    } else if (['line', 'arrow'].includes(tool)) {
      if (Math.hypot(bx - ax, by - ay) < 3) {
        resetPointToolState();
        state.tempMarkup = null;
        renderMarkupOverlay();
        return;
      }
      geometry = { points: [ax, ay, bx, by] };
    }
    resetPointToolState();
    state.tempMarkup = null;
    const saveType = tool === 'crossout' ? 'crossout' : tool;
    await saveMarkup({
      markup_type: saveType,
      geometry,
      measurement_value,
      measurement_unit: state.pixelsPerUnit ? state.measureUnit : 'px',
      label,
      style: { ...toolStyle(tool) },
    });
    if (tool === 'callout') {
      const last = state.markups[state.markups.length - 1];
      if (last) {
        const g = resolveGeom(last.geometry || {});
        showTextEditor({ x: g.x + 8, y: g.y + 8 }, last);
      }
    }
    renderMarkupOverlay();
  }

  async function handlePointToolUp(pt, didDrag, down) {
    const tool = state.tool;
    if (!isTwoPointClickTool(tool)) return false;

    if (tool === 'measure' && state.pointPhase === 'offset' && state.pointA && state.pointB) {
      state.pointOffset = measurePerpOffset(
        state.pointA.x, state.pointA.y,
        state.pointB.x, state.pointB.y,
        pt.x, pt.y,
      );
      await saveMeasureLine(
        state.pointA.x, state.pointA.y,
        state.pointB.x, state.pointB.y,
        state.pointOffset,
      );
      renderMarkupOverlay();
      return true;
    }

    if (state.pointPhase === 'second' && state.pointA) {
      if (Math.hypot(pt.x - state.pointA.x, pt.y - state.pointA.y) < 3) {
        toast('Pick a point farther from the first');
        state.tempMarkup = null;
        renderMarkupOverlay();
        return true;
      }
      if (tool === 'measure') {
        state.pointB = { x: pt.x, y: pt.y };
        state.pointPhase = 'offset';
        state.pointOffset = measurePerpOffset(
          state.pointA.x, state.pointA.y, pt.x, pt.y, pt.x, pt.y,
        );
        state.tempMarkup = null;
        toast('Click to place dimension line (extension lines to measured points)');
        renderMarkupOverlay();
        return true;
      }
      await finishTwoPointMarkup(tool, state.pointA.x, state.pointA.y, pt.x, pt.y);
      return true;
    }

    if (!state.pointPhase) {
      if (didDrag && Math.hypot(pt.x - down.x, pt.y - down.y) >= 3) {
        if (tool === 'measure') {
          state.pointA = { x: down.x, y: down.y };
          state.pointB = { x: pt.x, y: pt.y };
          state.pointPhase = 'offset';
          state.pointOffset = measurePerpOffset(down.x, down.y, pt.x, pt.y, pt.x, pt.y);
          state.tempMarkup = null;
          toast('Click to place dimension line (extension lines to measured points)');
        } else {
          await finishTwoPointMarkup(tool, down.x, down.y, pt.x, pt.y);
        }
        renderMarkupOverlay();
        return true;
      }
      state.pointA = { x: down.x, y: down.y };
      state.pointPhase = 'second';
      state.tempMarkup = null;
      toast(tool === 'measure'
        ? 'Click second point — pan/zoom as needed (Alt+drag)'
        : 'Click second point — pan/zoom between clicks (Alt+drag)');
      renderMarkupOverlay();
      return true;
    }
    return true;
  }

  async function saveMeasureLine(x1, y1, x2, y2, offset) {
    const pxLen = Math.hypot(x2 - x1, y2 - y1);
    if (pxLen < 3) return;
    const measureInfo = formatMeasureLength(pxLen);
    await saveMarkup({
      markup_type: 'measure',
      geometry: { points: [x1, y1, x2, y2], offset: offset || 0 },
      measurement_value: measureInfo.value,
      measurement_unit: measureInfo.unit,
      style: { ...toolStyle('measure') },
    });
    resetPointToolState();
    state.tempMarkup = null;
  }

  function updateViewerStatusBar() {
    const toolEl = document.getElementById('statusActiveTool');
    const scaleEl = document.getElementById('statusScale');
    const hintEl = document.getElementById('statusHint');
    if (!toolEl) return;
    const meta = TOOL_META[state.tool] || { label: state.tool, hint: '' };
    toolEl.textContent = meta.label + (meta.shortcut ? ` (${meta.shortcut})` : '');
    if (scaleEl) {
      if (state.scaleLabel && state.pixelsPerUnit) {
        scaleEl.innerHTML = `Scale: <strong>${esc(state.scaleLabel)}</strong>`;
      } else if (state.pixelsPerUnit) {
        scaleEl.innerHTML = 'Scale: <strong>Calibrated</strong>';
      } else {
        scaleEl.textContent = 'Scale: not set — calibrate or pick a preset';
      }
    }
    if (hintEl) hintEl.textContent = meta.hint || '';
  }

  function renderMarkupList() {
    const panel = document.getElementById('markupListPanel');
    const list = document.getElementById('markupListItems');
    if (!panel || !list) return;
    const items = visibleMarkups();
    if (!items.length) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    const typeIcon = {
      measure: 'fa-ruler', area: 'fa-vector-square', count: 'fa-hashtag', stamp: 'fa-stamp',
      pen: 'fa-pen', sketch: 'fa-pen', polyline: 'fa-draw-polygon', polygon: 'fa-shapes',
      crossout: 'fa-xmark', punch_pin: 'fa-thumbtack', co_pin: 'fa-file-signature',
      callout: 'fa-comment-dots', text: 'fa-font', textbox: 'fa-font',
      cloud: 'fa-cloud', rfi_pin: 'fa-map-pin', arrow: 'fa-arrow-right', highlight: 'fa-highlighter',
    };
    list.innerHTML = items.map(m => {
      const icon = typeIcon[m.markup_type] || 'fa-shapes';
      let sub = m.label ? String(m.label).split('\n')[0].slice(0, 40) : '';
      if (m.markup_type === 'measure' && m.measurement_value != null) {
        sub = formatMeasurementDisplay(m);
      } else if (m.markup_type === 'area' && m.measurement_value != null) {
        sub = formatMeasurementDisplay(m);
      }
      const sel = isMarkupSelected(m.id) ? ' markup-list-selected' : '';
      return `<div class="markup-list-item${sel}" data-markup-list-id="${m.id}">
        <i class="fa-solid ${icon} text-zinc-500 w-3 text-center text-[9px]"></i>
        <span class="flex-1 min-w-0 truncate text-zinc-300">${esc(m.markup_type)}${sub ? ` · ${esc(sub)}` : ''}</span>
      </div>`;
    }).join('');
    list.querySelectorAll('[data-markup-list-id]').forEach(el => {
      el.addEventListener('click', () => {
        setMarkupSelection(new Set([parseInt(el.getAttribute('data-markup-list-id'), 10)]));
        setTool('select');
        renderMarkupOverlay();
      });
    });
  }

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
    selectedMarkupIds: new Set(),
    selectMarquee: false,
    pointPhase: null,
    pointA: null,
    pointB: null,
    pointOffset: 0,
    pointPointerDown: false,
    pointDownPt: null,
    pointDidDrag: false,
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
    measureUnit: 'ft-in',
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
    sheetEditMode: false,
    sheetPendingEdits: {},
    searchPanelOpen: false,
    searchMode: 'text',
    searchScope: 'sheet',
    searchResults: [],
    searchBusy: false,
    searchTemplate: null,
    searchSnipping: false,
    docSnipping: false,
    pendingDocSnip: null,
    searchHighlight: null,
    selectedSearchIdx: null,
    uploadLogTimer: null,
    penPoints: null,
    pathPoints: null,
    countCounter: 1,
    selectedStamp: 'APPROVED',
    punchItems: [],
    changeOrders: [],
    pinSize: 1,
    pendingDrag: null,
    lastPinTap: { key: '', t: 0 },
    textDialogCtx: null,
    pdfRerenderTimer: null,
    lastPdfRenderScale: 0,
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
      clearMarkupSelection();
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
        clearMarkupSelection();
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

  async function loadPunchItems() {
    const pid = projectId();
    if (!pid) return;
    try {
      const json = await api(`/api/drawings/punch-items?project_id=${pid}`);
      state.punchItems = json.punch_items || [];
    } catch { state.punchItems = []; }
  }

  async function loadChangeOrders() {
    const pid = projectId();
    if (!pid) return;
    try {
      const json = await api(`/api/drawings/change-orders?project_id=${pid}`);
      state.changeOrders = json.change_orders || [];
    } catch { state.changeOrders = []; }
  }

  function navigateToRfi(rfiId) {
    const pid = projectId();
    const q = new URLSearchParams({ rfi_id: String(rfiId), open: '1' });
    if (pid) q.set('project_id', String(pid));
    global.location.href = `/rfis?${q.toString()}`;
  }

  function navigateToChangeOrder(coId) {
    const pid = projectId();
    const q = new URLSearchParams({ co_id: String(coId), open: '1' });
    if (pid) q.set('project_id', String(pid));
    global.location.href = `/change-orders?${q.toString()}`;
  }

  function openPinLink(pinType, linkId) {
    const id = linkId != null && linkId !== '' ? String(linkId) : '';
    if (!id) return;
    if (pinType === 'rfi') navigateToRfi(id);
    else if (pinType === 'co') navigateToChangeOrder(id);
  }

  function pinLinkFromMarkup(m) {
    if (!m) return { pinType: '', linkId: '' };
    if (m.markup_type === 'rfi_pin') {
      return { pinType: 'rfi', linkId: m.linked_rfi_id || '' };
    }
    if (m.markup_type === 'co_pin') {
      const g = resolvePinGeom(m.geometry || {});
      return { pinType: 'co', linkId: g.linkedCoId || m.linked_co_id || '' };
    }
    if (m.markup_type === 'punch_pin') {
      const g = resolvePinGeom(m.geometry || {});
      return { pinType: 'punch', linkId: g.linkedPunchId || '' };
    }
    return { pinType: '', linkId: '' };
  }

  function handlePinBadgeActivate(badgeEl) {
    if (!badgeEl) return;
    const pinType = badgeEl.getAttribute('data-pin-type');
    let linkId = badgeEl.getAttribute('data-pin-link');
    if (!linkId) {
      const markupId = parseInt(badgeEl.getAttribute('data-markup-id'), 10);
      const m = state.markups.find(x => x.id === markupId);
      const resolved = pinLinkFromMarkup(m);
      pinType = resolved.pinType || pinType;
      linkId = resolved.linkId;
    }
    openPinLink(pinType, linkId);
  }

  function registerPinBadgeTap(badgeEl) {
    const markupId = badgeEl.getAttribute('data-markup-id');
    const linkId = badgeEl.getAttribute('data-pin-link') || markupId;
    const key = `${markupId}:${linkId}`;
    const now = Date.now();
    if (state.lastPinTap.key === key && now - state.lastPinTap.t < 450) {
      state.lastPinTap = { key: '', t: 0 };
      handlePinBadgeActivate(badgeEl);
      return true;
    }
    state.lastPinTap = { key, t: now };
    return false;
  }

  /** Leader pin: anchor = exact point on plan; x/y = draggable label badge. */
  function resolvePinGeom(geom) {
    const g = resolveGeom(geom || {});
    if (g.pinSize == null && geom?.pinSize != null) g.pinSize = geom.pinSize;
    if (g.anchorX == null && g.x != null) {
      const off = 56 * (g.pinSize || 1);
      g.anchorX = g.x;
      g.anchorY = g.y;
      g.x = g.x + off;
      g.y = g.y - off;
    }
    return g;
  }

  function leaderPinSvg(opts) {
    const {
      id, anchorX, anchorY, badgeX, badgeY, color, letter, pinType, linkId, label, selected,
      pinSize = 1,
    } = opts;
    const scale = Math.max(0.5, Math.min(3, pinSize || 1));
    const badgeR = 11 * scale;
    const hitR = Math.max(14, 16 * scale);
    const anchorR = 3.5 * scale;
    const fontSize = Math.round(9 * scale);
    const stroke = selected ? '#fbbf24' : color;
    const title = esc(label || letter);
    return `<g class="markup-item leader-pin${selected ? ' markup-selected' : ''}">
      <line x1="${anchorX}" y1="${anchorY}" x2="${badgeX}" y2="${badgeY}" stroke="${stroke}" stroke-width="${1.5 * scale}" opacity="0.9" pointer-events="none"/>
      <circle cx="${anchorX}" cy="${anchorY}" r="${anchorR}" fill="${color}" stroke="#fff" stroke-width="${1.5 * scale}" pointer-events="none"/>
      <circle data-markup-id="${id}" data-pin-badge="1" data-pin-type="${pinType}" data-pin-link="${linkId || ''}" cx="${badgeX}" cy="${badgeY}" r="${hitR}" fill="transparent" pointer-events="all"/>
      <circle cx="${badgeX}" cy="${badgeY}" r="${badgeR}" fill="${color}" stroke="${selected ? '#fbbf24' : '#fff'}" stroke-width="${2 * scale}" pointer-events="none"/>
      <text x="${badgeX}" y="${badgeY + fontSize * 0.45}" text-anchor="middle" fill="#fff" font-size="${fontSize}" font-weight="bold" pointer-events="none">${esc(letter)}</text>
      <title>${title}</title>
    </g>`;
  }

  function computePdfRenderScale(unscaled, wrap) {
    const fitScale = Math.min(
      (wrap.clientWidth - 32) / unscaled.width,
      (wrap.clientHeight - 32) / unscaled.height,
    );
    const dpr = global.devicePixelRatio || 1;
    const minQuality = 200 / 72;
    const zoomBoost = Math.max(1, state.viewScale * 0.9);
    return Math.min(8, Math.max(minQuality, fitScale * dpr * zoomBoost, 2.5));
  }

  function schedulePdfQualityRerender() {
    if (!state.openDrawing || !state.pdfDoc) return;
    clearTimeout(state.pdfRerenderTimer);
    state.pdfRerenderTimer = setTimeout(() => {
      state.pdfRerenderTimer = null;
      renderPdf(false, { qualityOnly: true });
    }, 280);
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
    if (!await drawConfirm(`Delete drawing set "${setName}" and all ${count} sheet(s) currently in it? This cannot be undone.`, { title: 'Delete drawing set', danger: true, confirmLabel: 'Delete set' })) return;
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
    if (!await drawConfirm(`Delete ${ids.length} sheet(s)?\n\n${labels}\n\nThis cannot be undone.`, { title: 'Delete sheets', danger: true, confirmLabel: 'Delete' })) return;
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

  const SHEET_EDIT_COLUMNS = [
    'sheet_number', 'title', 'set_name', 'discipline', 'section_prefix',
    'revision_label', 'drawing_date', 'status',
  ];

  const SHEET_STATUS_OPTIONS = ['Current', 'For Review', 'Superseded'];

  function sheetCellValue(drawing, field) {
    const pending = state.sheetPendingEdits[drawing.id];
    if (pending && field in pending) return pending[field];
    const val = drawing[field];
    if (field === 'drawing_date' || field === 'received_date') {
      if (!val) return '';
      return String(val).slice(0, 10);
    }
    return val == null ? '' : String(val);
  }

  function isSheetCellDirty(drawingId, field) {
    return state.sheetPendingEdits[drawingId] && field in state.sheetPendingEdits[drawingId];
  }

  function isSheetRowDirty(drawingId) {
    const pending = state.sheetPendingEdits[drawingId];
    return pending && Object.keys(pending).length > 0;
  }

  function setSheetCellValue(drawingId, field, value) {
    const drawing = state.drawings.find(d => d.id === drawingId);
    if (!drawing) return;
    const original = drawing[field];
    const norm = (v) => (v == null ? '' : String(v).trim());
    if (norm(value) === norm(original)) {
      if (state.sheetPendingEdits[drawingId]) {
        delete state.sheetPendingEdits[drawingId][field];
        if (!Object.keys(state.sheetPendingEdits[drawingId]).length) {
          delete state.sheetPendingEdits[drawingId];
        }
      }
    } else {
      if (!state.sheetPendingEdits[drawingId]) state.sheetPendingEdits[drawingId] = {};
      state.sheetPendingEdits[drawingId][field] = value;
    }
    updateSheetEditBar();
    const row = document.querySelector(`#drawTableBody tr[data-drawing-id="${drawingId}"]`);
    if (row) {
      row.classList.toggle('draw-sheet-row-dirty', isSheetRowDirty(drawingId));
      row.querySelectorAll('.draw-sheet-cell-input').forEach(inp => {
        inp.classList.toggle('draw-sheet-cell-dirty', isSheetCellDirty(drawingId, inp.dataset.field));
      });
    }
  }

  function pendingSheetEditCount() {
    let n = 0;
    Object.values(state.sheetPendingEdits).forEach(fields => { n += Object.keys(fields).length; });
    return n;
  }

  function updateSheetEditBar() {
    const bar = document.getElementById('drawSheetEditBar');
    const countEl = document.getElementById('drawSheetEditCount');
    const panel = document.getElementById('drawPanelList');
    const n = pendingSheetEditCount();
    bar?.classList.toggle('hidden', !state.sheetEditMode);
    panel?.classList.toggle('draw-sheet-edit-active', state.sheetEditMode);
    if (countEl) {
      countEl.textContent = n ? `${n} unsaved cell${n === 1 ? '' : 's'}` : 'No unsaved changes';
    }
    const btn = document.getElementById('btnSheetEditMode');
    const lbl = document.getElementById('btnSheetEditModeLabel');
    if (btn) {
      btn.classList.toggle('bg-amber-700', state.sheetEditMode);
      btn.classList.toggle('text-white', state.sheetEditMode);
      btn.classList.toggle('bg-zinc-800', !state.sheetEditMode);
      btn.classList.toggle('text-zinc-300', !state.sheetEditMode);
    }
    if (lbl) lbl.textContent = state.sheetEditMode ? 'Editing…' : 'Edit table';
  }

  function mergeDrawingUpdates(updated) {
    (updated || []).forEach(d => {
      const idx = state.drawings.findIndex(x => x.id === d.id);
      if (idx >= 0) state.drawings[idx] = { ...state.drawings[idx], ...d };
    });
    const grouped = {};
    state.drawings.forEach(d => {
      const sec = d.section_prefix || 'OTHER';
      if (!grouped[sec]) grouped[sec] = [];
      grouped[sec].push(d);
    });
    Object.keys(grouped).forEach(sec => {
      grouped[sec].sort((a, b) => String(a.sort_key || a.sheet_number).localeCompare(String(b.sort_key || b.sheet_number)));
    });
    state.sections = grouped;
    renderSectionTabs();
    populateSetFilter();
  }

  function toggleSheetEditMode(force) {
    const next = force != null ? force : !state.sheetEditMode;
    if (!next && pendingSheetEditCount()) {
      drawConfirm('Discard unsaved sheet edits?', { title: 'Discard edits', danger: true, confirmLabel: 'Discard' }).then(ok => {
        if (ok) {
          state.sheetPendingEdits = {};
          state.sheetEditMode = false;
          updateSheetEditBar();
          if (state.view !== 'list') switchView('list');
          else renderTable();
        }
      });
      return;
    }
    state.sheetEditMode = next;
    if (state.sheetEditMode && state.view !== 'list') switchView('list');
    updateSheetEditBar();
    renderTable();
    if (state.sheetEditMode) bindSheetTablePaste();
  }

  function discardSheetEdits() {
    state.sheetPendingEdits = {};
    updateSheetEditBar();
    renderTable();
    toast('Edits discarded');
  }

  async function saveSheetEdits() {
    const updates = Object.entries(state.sheetPendingEdits).map(([id, fields]) => ({
      id: parseInt(id, 10),
      ...fields,
    }));
    if (!updates.length) {
      toast('No changes to save');
      return;
    }
    try {
      const json = await api('/api/drawings/bulk-update', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId(), updates }),
      });
      mergeDrawingUpdates(json.drawings);
      state.sheetPendingEdits = {};
      updateSheetEditBar();
      renderActiveView();
      if (json.errors?.length) {
        toastError(`${json.errors.length} row(s) could not be saved`);
      } else {
        toast(`Saved ${json.drawings?.length || updates.length} sheet(s)`);
      }
    } catch (e) {
      toastError(e.message || 'Could not save sheet edits');
    }
  }

  function sheetCellInput(d, field) {
    const val = esc(sheetCellValue(d, field));
    const dirty = isSheetCellDirty(d.id, field) ? ' draw-sheet-cell-dirty' : '';
    const mono = field === 'sheet_number' || field === 'section_prefix' ? ' font-mono' : '';
    if (field === 'status') {
      const opts = SHEET_STATUS_OPTIONS.map(s =>
        `<option value="${s}" ${sheetCellValue(d, field) === s ? 'selected' : ''}>${s}</option>`
      ).join('');
      return `<select data-drawing-id="${d.id}" data-field="${field}" class="draw-sheet-cell-input${dirty}${mono}" onclick="event.stopPropagation()" onmousedown="event.stopPropagation()" onchange="CasePMDrawings.onSheetCellInput(this)">${opts}</select>`;
    }
    const type = field === 'drawing_date' ? 'date' : 'text';
    return `<input type="${type}" value="${val}" data-drawing-id="${d.id}" data-field="${field}" class="draw-sheet-cell-input${dirty}${mono}" onclick="event.stopPropagation()" onmousedown="event.stopPropagation()" onchange="CasePMDrawings.onSheetCellInput(this)" oninput="CasePMDrawings.onSheetCellInput(this)">`;
  }

  function onSheetCellInput(el) {
    const id = parseInt(el.dataset.drawingId, 10);
    const field = el.dataset.field;
    setSheetCellValue(id, field, el.value);
  }

  function bindSheetTablePaste() {
    const tbody = document.getElementById('drawTableBody');
    if (!tbody || tbody._pasteBound) return;
    tbody._pasteBound = true;
    tbody.addEventListener('paste', e => {
      if (!state.sheetEditMode) return;
      const target = e.target;
      if (!target?.classList?.contains('draw-sheet-cell-input')) return;
      const clip = e.clipboardData?.getData('text/plain');
      if (!clip || (!clip.includes('\t') && !clip.includes('\n'))) return;
      e.preventDefault();
      const row = target.closest('tr[data-drawing-id]');
      const rows = Array.from(document.querySelectorAll('#drawTableBody tr[data-drawing-id]'));
      const startRow = rows.indexOf(row);
      const startCol = SHEET_EDIT_COLUMNS.indexOf(target.dataset.field);
      if (startRow < 0 || startCol < 0) return;
      const lines = clip.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd().split('\n');
      lines.forEach((line, ri) => {
        const tr = rows[startRow + ri];
        if (!tr) return;
        const id = parseInt(tr.dataset.drawingId, 10);
        line.split('\t').forEach((cell, ci) => {
          const field = SHEET_EDIT_COLUMNS[startCol + ci];
          if (!field) return;
          const v = cell.trim();
          setSheetCellValue(id, field, v);
          const inp = tr.querySelector(`[data-field="${field}"]`);
          if (inp) inp.value = v;
        });
      });
    });
  }

  function toggleSearchPanel(force) {
    const next = force != null ? !!force : !state.searchPanelOpen;
    state.searchPanelOpen = next;
    document.getElementById('drawSearchPanel')?.classList.toggle('hidden', !next);
    document.getElementById('btnSearchPanel')?.classList.toggle('tool-active', next);
    if (!next) {
      state.searchSnipping = false;
      clearSearchHighlight();
      updateViewerCursor();
    }
  }

  function setSearchMode(mode) {
    state.searchMode = mode;
    document.getElementById('drawSearchTabText')?.classList.toggle('active', mode === 'text');
    document.getElementById('drawSearchTabShape')?.classList.toggle('active', mode === 'shape');
    document.getElementById('drawSearchTextPane')?.classList.toggle('hidden', mode !== 'text');
    document.getElementById('drawSearchShapePane')?.classList.toggle('hidden', mode !== 'shape');
    renderSearchResults();
  }

  function setSearchScope(scope) {
    state.searchScope = scope;
    const radios = document.querySelectorAll('input[name="drawSearchScope"]');
    radios.forEach(r => { r.checked = r.value === scope; });
  }

  function setSearchStatus(msg, busy) {
    const el = document.getElementById('drawSearchStatus');
    if (!el) return;
    el.classList.toggle('hidden', !msg && !busy);
    el.innerHTML = busy
      ? `<i class="fa-solid fa-spinner fa-spin mr-1"></i>${esc(msg || 'Searching…')}`
      : esc(msg || '');
  }

  function renderSearchResults() {
    const el = document.getElementById('drawSearchResults');
    if (!el) return;
    const results = state.searchResults || [];
    if (!results.length) {
      el.innerHTML = `<div class="text-[10px] text-zinc-500 p-2">${state.searchMode === 'text'
        ? 'Search finds text line-by-line in the current sheet or every drawing in the project.'
        : 'Snip a symbol on the sheet, then find very similar shapes elsewhere. Edge-touching matches are filtered out.'}</div>`;
      return;
    }
    el.innerHTML = results.map((r, i) => {
      const active = state.selectedSearchIdx === i ? ' active' : '';
      const thumb = r.thumb
        ? `<img src="data:image/png;base64,${r.thumb}" class="draw-search-result-thumb" alt="">`
        : `<div class="draw-search-result-thumb flex items-center justify-center text-zinc-600"><i class="fa-solid fa-file-lines"></i></div>`;
      const sub = state.searchMode === 'shape'
        ? `${Math.round((r.score || 0) * 100)}% match`
        : esc(r.snippet || r.line_text || '');
      return `<button type="button" class="draw-search-result${active}" data-search-idx="${i}" onclick="CasePMDrawings.jumpToSearchResult(${i})">
        ${thumb}
        <div class="min-w-0 flex-1">
          <div class="font-mono text-sky-400 text-[11px] truncate">${esc(r.sheet_number || '')}</div>
          <div class="text-[10px] text-zinc-500 truncate">${esc(r.title || '')}</div>
          <div class="text-[10px] text-zinc-300 mt-0.5 line-clamp-2">${sub}</div>
        </div>
      </button>`;
    }).join('');
  }

  function searchHighlightMarkup() {
    const r = state.searchHighlight;
    if (!r || r.nx == null) return '';
    const { w, h } = canvasDims();
    if (!w || !h) return '';
    const x = (r.nx || 0) * w;
    const y = (r.ny || 0) * h;
    const rw = Math.max(12, (r.nw || 0.05) * w);
    const rh = Math.max(12, (r.nh || 0.05) * h);
    const cx = x + rw / 2;
    const cy = y + rh / 2;
    const pad = Math.max(10, Math.max(rw, rh) * 0.22);
    if (state.searchMode === 'shape') {
      const radius = Math.hypot(rw, rh) / 2 + pad;
      return `<g class="search-hit-shape" pointer-events="none">
        <circle cx="${cx}" cy="${cy}" r="${radius}" fill="rgba(250, 204, 21, 0.58)" stroke="#facc15" stroke-width="3"/>
        <circle cx="${cx}" cy="${cy}" r="${radius + 5}" fill="none" stroke="rgba(250, 204, 21, 0.4)" stroke-width="2"/>
      </g>`;
    }
    return `<rect class="search-hit-text" x="${x}" y="${y}" width="${rw}" height="${rh}" fill="rgba(250, 204, 21, 0.38)" stroke="#facc15" stroke-width="2" rx="3" pointer-events="none"/>`;
  }

  function clearSearchHighlight() {
    state.searchHighlight = null;
    state.selectedSearchIdx = null;
    renderMarkupOverlay();
    renderSearchResults();
  }

  async function jumpToSearchResult(idx) {
    const r = state.searchResults[idx];
    if (!r) return;
    state.selectedSearchIdx = idx;
    state.searchHighlight = r;
    renderSearchResults();
    if (!state.openDrawing || state.openDrawing.id !== r.drawing_id) {
      await openViewer(r.drawing_id);
    }
    const cx = (r.nx || 0) + (r.nw || 0.02) / 2;
    const cy = (r.ny || 0) + (r.nh || 0.02) / 2;
    focusOnPoint(cx, cy);
    renderSearchHighlight();
  }

  function renderSearchHighlight() {
    if (!state.searchHighlight) return;
    renderMarkupOverlay();
  }

  async function runTextSearch() {
    const query = document.getElementById('drawSearchTextInput')?.value?.trim();
    if (!query || query.length < 2) {
      toast('Enter at least 2 characters to search');
      return;
    }
    if (state.searchScope === 'sheet' && !state.openDrawing) {
      toast('Open a sheet first, or search all drawings');
      return;
    }
    setSearchStatus('Searching text…', true);
    state.searchBusy = true;
    state.searchHighlight = null;
    state.selectedSearchIdx = null;
    try {
      const json = await api('/api/drawings/search/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId(),
          query,
          scope: state.searchScope,
          drawing_id: state.openDrawing?.id,
        }),
      });
      state.searchResults = json.results || [];
      state.selectedSearchIdx = null;
      setSearchStatus(`${state.searchResults.length} line${state.searchResults.length === 1 ? '' : 's'} found`, false);
      renderSearchResults();
      if (!state.searchResults.length) toast('No text matches found');
    } catch (e) {
      setSearchStatus('', false);
      toastError(e.message || 'Text search failed');
    }
    state.searchBusy = false;
  }

  function captureCanvasRegion(x, y, w, h, opts) {
    const fullRes = opts && opts.fullRes;
    const canvas = document.getElementById('drawPdfCanvas');
    if (!canvas || w < 4 || h < 4) return null;
    const x0 = Math.max(0, Math.min(x, canvas.width - 1));
    const y0 = Math.max(0, Math.min(y, canvas.height - 1));
    const rw = Math.min(w, canvas.width - x0);
    const rh = Math.min(h, canvas.height - y0);
    if (rw < 4 || rh < 4) return null;
    let outW = rw;
    let outH = rh;
    if (!fullRes) {
      const maxSide = 220;
      const scale = Math.min(1, maxSide / Math.max(rw, rh));
      outW = Math.max(4, Math.round(rw * scale));
      outH = Math.max(4, Math.round(rh * scale));
    }
    const tmp = document.createElement('canvas');
    tmp.width = outW;
    tmp.height = outH;
    tmp.getContext('2d').drawImage(canvas, x0, y0, rw, rh, 0, 0, outW, outH);
    return { dataUrl: tmp.toDataURL('image/png'), docW: rw, docH: rh };
  }

  function isViewerSnipping() {
    return state.searchSnipping || state.docSnipping;
  }

  function snipRectPreview(x, y, rw, rh) {
    if (state.docSnipping) {
      return `<rect x="${x}" y="${y}" width="${rw}" height="${rh}" stroke="#34d399" stroke-width="2" fill="rgba(52,211,153,0.2)" stroke-dasharray="4 2"/>`;
    }
    return `<rect x="${x}" y="${y}" width="${rw}" height="${rh}" stroke="#a78bfa" stroke-width="2" fill="rgba(167,139,250,0.15)" stroke-dasharray="4 2"/>`;
  }

  function cancelDocSnip() {
    state.docSnipping = false;
    state.pendingDocSnip = null;
    state.drawing = false;
    state.drawStart = null;
    state.tempMarkup = null;
    updateViewerCursor();
    renderMarkupOverlay();
  }

  function startDocSnip() {
    if (!state.openDrawing) {
      toast('Open a sheet first');
      return;
    }
    state.searchSnipping = false;
    state.docSnipping = true;
    state.pendingDocSnip = null;
    state.drawing = false;
    state.drawStart = null;
    state.tempMarkup = null;
    updateViewerCursor();
    toast('Drag a box around the area to snip — like Windows Snipping Tool');
  }

  function openDocSnipSaveDialog(captured) {
    state.pendingDocSnip = captured;
    const dlg = document.getElementById('docSnipSaveDialog');
    const preview = document.getElementById('docSnipPreview');
    const nameEl = document.getElementById('docSnipName');
    if (!dlg || !captured?.dataUrl) return;
    const sheet = state.openDrawing?.sheet_number || 'Sheet';
    const title = state.openDrawing?.title ? ` — ${state.openDrawing.title}` : '';
    const date = new Date().toLocaleDateString();
    if (preview) preview.src = captured.dataUrl;
    if (nameEl) nameEl.value = `${sheet}${title} — snip ${date}`;
    dlg.showModal();
  }

  async function saveDocSnipToDocuments() {
    const captured = state.pendingDocSnip;
    const name = document.getElementById('docSnipName')?.value?.trim();
    const docType = document.getElementById('docSnipType')?.value || 'Drawing';
    if (!captured?.dataUrl) {
      toast('Nothing to save');
      return;
    }
    if (!name) {
      toast('Enter a document name');
      return;
    }
    if (!projectId()) {
      toast('Select a project first');
      return;
    }
    const saveBtn = document.getElementById('docSnipSave');
    if (saveBtn) saveBtn.disabled = true;
    try {
      const json = await api('/api/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId(),
          name,
          document_type: docType,
          image_data: captured.dataUrl,
          source_drawing_id: state.openDrawing?.id,
          source_sheet: state.openDrawing?.sheet_number,
          system_folder_key: 'my-files',
          source_metadata: {
            title: state.openDrawing?.title,
            revision_id: state.viewingRevisionId,
          },
        }),
      });
      document.getElementById('docSnipSaveDialog')?.close();
      state.pendingDocSnip = null;
      toast(`Saved to Documents — ${json.document?.name || name}`);
    } catch (e) {
      toastError(e.message || 'Failed to save document');
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  function bindDocSnipDialog() {
    document.getElementById('docSnipSave')?.addEventListener('click', () => saveDocSnipToDocuments());
    document.getElementById('docSnipCancel')?.addEventListener('click', () => {
      document.getElementById('docSnipSaveDialog')?.close();
      state.pendingDocSnip = null;
    });
    document.getElementById('docSnipDialogClose')?.addEventListener('click', () => {
      document.getElementById('docSnipSaveDialog')?.close();
      state.pendingDocSnip = null;
    });
    document.getElementById('docSnipSaveDialog')?.addEventListener('cancel', () => {
      state.pendingDocSnip = null;
    });
  }

  function startShapeSnip() {
    if (!state.openDrawing) {
      toast('Open a sheet to snip a shape from it');
      return;
    }
    toggleSearchPanel(true);
    setSearchMode('shape');
    state.searchSnipping = true;
    state.drawing = false;
    state.drawStart = null;
    state.tempMarkup = null;
    updateViewerCursor();
    toast('Drag a box around the shape to search for');
  }

  async function runShapeSearch() {
    if (!state.searchTemplate) {
      toast('Snip a shape on the sheet first');
      return;
    }
    if (state.searchScope === 'sheet' && !state.openDrawing) {
      toast('Open a sheet first');
      return;
    }
    const thresh = parseInt(document.getElementById('drawShapeThreshold')?.value || '82', 10) / 100;
    const scopeLabel = state.searchScope === 'project' ? 'project' : 'sheet';
    setSearchStatus(`Quick scan (${scopeLabel})…`, true);
    state.searchBusy = true;
    state.searchHighlight = null;
    state.selectedSearchIdx = null;
    try {
      const json = await api('/api/drawings/search/shape', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId(),
          scope: state.searchScope,
          drawing_id: state.openDrawing?.id,
          template: state.searchTemplate,
          threshold: thresh,
          render_scale: state.lastPdfRenderScale || null,
          snip_w: state.searchSnipDocW || null,
          snip_h: state.searchSnipDocH || null,
        }),
      });
      state.searchResults = json.results || [];
      state.selectedSearchIdx = null;
      setSearchStatus(`${state.searchResults.length} match${state.searchResults.length === 1 ? '' : 'es'}`, false);
      renderSearchResults();
      if (!state.searchResults.length) toast('No similar shapes found — try lowering match %');
    } catch (e) {
      setSearchStatus('', false);
      toastError(e.message || 'Shape search failed');
    }
    state.searchBusy = false;
  }

  function bindSearchPanel() {
    const slider = document.getElementById('drawShapeThreshold');
    const lbl = document.getElementById('drawShapeThresholdLabel');
    if (slider && !slider._bound) {
      slider._bound = true;
      slider.addEventListener('input', () => {
        if (lbl) lbl.textContent = `${slider.value}%`;
      });
    }
  }

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
    updateSheetEditBar();
    const rows = filteredDrawings();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="11" class="px-6 py-12 text-center text-zinc-500">No drawings found.</td></tr>';
      return;
    }
    if (state.sheetEditMode) {
      tbody.innerHTML = rows.map(d => `
      <tr data-drawing-id="${d.id}" class="border-b border-zinc-800 hover:bg-zinc-800/50 ${isSheetSelected(d.id) ? 'bg-sky-950/30' : ''} ${isSheetRowDirty(d.id) ? 'draw-sheet-row-dirty' : ''}" ondblclick="CasePMDrawings.openViewer(${d.id})">
        <td class="px-2 py-2 text-center" onclick="event.stopPropagation()">
          <input type="checkbox" class="accent-sky-500" ${isSheetSelected(d.id) ? 'checked' : ''} onchange="CasePMDrawings.toggleSheetSelection(${d.id}, this.checked)">
        </td>
        <td class="px-2 py-2">${sheetCellInput(d, 'sheet_number')}</td>
        <td class="px-2 py-2">${sheetCellInput(d, 'title')}</td>
        <td class="px-2 py-2">${sheetCellInput(d, 'set_name')}</td>
        <td class="px-2 py-2">${sheetCellInput(d, 'discipline')}</td>
        <td class="px-2 py-2">${sheetCellInput(d, 'section_prefix')}</td>
        <td class="px-2 py-2 text-center">${sheetCellInput(d, 'revision_label')}</td>
        <td class="px-2 py-2 text-center">${sheetCellInput(d, 'drawing_date')}</td>
        <td class="px-2 py-2 text-center">${sheetCellInput(d, 'status')}</td>
        <td class="px-4 py-2 text-center text-xs text-zinc-500">${d.revision_count || 1}</td>
        <td class="px-2 py-2 text-center">
          <button type="button" onclick="event.stopPropagation(); CasePMDrawings.deleteDrawing(${d.id})" class="px-2 py-1 rounded bg-red-900/60 hover:bg-red-800 text-[10px] text-red-100" title="Delete sheet"><i class="fa-solid fa-trash"></i></button>
        </td>
      </tr>`).join('');
    } else {
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
    }
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
      clearMarkupSelection();
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
      bindMarkupSvgEvents();
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
    updateViewerStatusBar();
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
      const fx = g.nanchorX != null ? g.nanchorX : g.nx;
      const fy = g.nanchorY != null ? g.nanchorY : g.ny;
      if (fx != null) q.set('x', fx);
      if (fy != null) q.set('y', fy);
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
    if (geom.anchorX != null && geom.anchorY != null) {
      geom.nanchorX = geom.nanchorX ?? geom.anchorX / w;
      geom.nanchorY = geom.nanchorY ?? geom.anchorY / h;
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
    if (geom.nanchorX != null) out.anchorX = geom.nanchorX * w;
    if (geom.nanchorY != null) out.anchorY = geom.nanchorY * h;
    if (geom.anchorX != null && geom.canvasW && geom.canvasW !== w) {
      out.anchorX = (geom.anchorX / geom.canvasW) * w;
      out.anchorY = (geom.anchorY / geom.canvasH) * h;
    }
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
    if (g.nanchorX != null) g.nanchorX += ndx;
    if (g.nanchorY != null) g.nanchorY += ndy;
    if (g.x != null) g.x += dx;
    if (g.y != null) g.y += dy;
    if (g.anchorX != null) g.anchorX += dx;
    if (g.anchorY != null) g.anchorY += dy;
    if (w && h) {
      g.canvasW = w;
      g.canvasH = h;
    }
    return g;
  }

  /** Move only the draggable badge on leader pins; anchor stays on the plan. */
  function translatePinBadgeGeometry(geom, dx, dy) {
    const { w, h } = canvasDims();
    const g = JSON.parse(JSON.stringify(geom || {}));
    const ndx = w ? dx / w : 0;
    const ndy = h ? dy / h : 0;
    if (g.nx != null) g.nx += ndx;
    if (g.ny != null) g.ny += ndy;
    if (g.x != null) g.x += dx;
    if (g.y != null) g.y += dy;
    if (w && h) {
      g.canvasW = w;
      g.canvasH = h;
    }
    return g;
  }

  function pinGeometryAt(anchorPt) {
    const offset = 56 * (state.pinSize || 1);
    return {
      anchorX: anchorPt.x,
      anchorY: anchorPt.y,
      x: anchorPt.x + offset,
      y: anchorPt.y - offset,
      pinSize: state.pinSize || 1,
    };
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
      if (m.markup_type === 'rfi_pin' || m.markup_type === 'co_pin' || m.markup_type === 'punch_pin') {
        const pg = resolvePinGeom(m.geometry || {});
        const hitR = 16 * (pg.pinSize || 1);
        d = Math.hypot(pt.x - (pg.x || 0), pt.y - (pg.y || 0));
        if (d <= hitR + 4) d = 0;
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
      } else if (m.markup_type === 'crossout' && g.w != null) {
        const inside = pt.x >= g.x && pt.x <= g.x + g.w && pt.y >= g.y && pt.y <= g.y + g.h;
        d = inside ? 0 : Math.min(
          Math.abs(pt.x - g.x), Math.abs(pt.x - (g.x + g.w)),
          Math.abs(pt.y - g.y), Math.abs(pt.y - (g.y + g.h))
        );
      } else if ((m.markup_type === 'pen' || m.markup_type === 'sketch' || m.markup_type === 'polyline' || m.markup_type === 'polygon' || m.markup_type === 'area') && g.points) {
        for (let i = 0; i < g.points.length - 2; i += 2) {
          const seg = distToSegment(pt.x, pt.y, g.points[i], g.points[i + 1], g.points[i + 2], g.points[i + 3]);
          d = Math.min(d, seg);
        }
        if (m.markup_type === 'polygon' || m.markup_type === 'area') {
          const last = g.points.length - 2;
          d = Math.min(d, distToSegment(pt.x, pt.y, g.points[last], g.points[last + 1], g.points[0], g.points[1]));
        }
      } else if (m.markup_type === 'stamp' && g.x != null) {
        const inside = pt.x >= g.x && pt.x <= g.x + (g.w || 110) && pt.y >= g.y && pt.y <= g.y + (g.h || 32);
        d = inside ? 0 : Math.hypot(pt.x - g.x, pt.y - g.y);
      } else if (m.markup_type === 'count' && g.x != null) {
        d = Math.hypot(pt.x - g.x, pt.y - g.y);
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

  function isMarkupSelected(id) {
    return state.selectedMarkupIds.has(id) || state.selectedMarkupId === id;
  }

  function setMarkupSelection(ids, primaryId) {
    state.selectedMarkupIds = ids instanceof Set ? ids : new Set(ids || []);
    state.selectedMarkupId = primaryId != null
      ? primaryId
      : (state.selectedMarkupIds.size ? [...state.selectedMarkupIds][0] : null);
    updateMarkupToolbar();
  }

  function clearMarkupSelection() {
    state.selectedMarkupIds = new Set();
    state.selectedMarkupId = null;
    updateMarkupToolbar();
  }

  function markupBounds(m) {
    const g = resolveGeom(m.geometry || {});
    const pad = 8;
    if (m.markup_type === 'rfi_pin' || m.markup_type === 'co_pin' || m.markup_type === 'punch_pin') {
      const pg = resolvePinGeom(m.geometry || {});
      const r = 16 * (pg.pinSize || 1) + pad;
      return { x: (pg.x || 0) - r, y: (pg.y || 0) - r, w: r * 2, h: r * 2 };
    }
    if (g.x != null && g.w != null && g.h != null) {
      return { x: g.x, y: g.y, w: g.w, h: g.h };
    }
    if (g.points && g.points.length >= 4) {
      let minX = g.points[0];
      let minY = g.points[1];
      let maxX = g.points[0];
      let maxY = g.points[1];
      for (let i = 0; i < g.points.length; i += 2) {
        minX = Math.min(minX, g.points[i]);
        maxX = Math.max(maxX, g.points[i]);
        minY = Math.min(minY, g.points[i + 1]);
        maxY = Math.max(maxY, g.points[i + 1]);
      }
      return { x: minX - pad, y: minY - pad, w: maxX - minX + pad * 2, h: maxY - minY + pad * 2 };
    }
    if (g.x != null && g.y != null) {
      return { x: g.x - pad, y: g.y - pad, w: pad * 2, h: pad * 2 };
    }
    return null;
  }

  function markupIntersectsRect(m, rect) {
    const b = markupBounds(m);
    if (!b) return false;
    return b.x < rect.x + rect.w && b.x + b.w > rect.x && b.y < rect.y + rect.h && b.y + b.h > rect.y;
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

  async function renderPdf(forceReload, opts) {
    if (!state.openDrawing || !global.pdfjsLib) return;
    const qualityOnly = opts?.qualityOnly;
    const canvas = document.getElementById('drawPdfCanvas');
    const wrap = document.getElementById('drawViewerWrap');
    if (!canvas || !wrap) return;

    const url = getViewerPdfUrl();
    const gen = ++state.renderGen;

    if (!qualityOnly && (forceReload || !state.pdfDoc || state.pdfUrl !== url)) {
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
    const renderScale = computePdfRenderScale(unscaled, wrap);
    if (qualityOnly && Math.abs(renderScale - state.lastPdfRenderScale) < 0.15) return;
    const viewport = page.getViewport({ scale: renderScale, rotation: page.rotate });
    if (gen !== state.renderGen) return;

    state.lastPdfRenderScale = renderScale;
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
    if (!qualityOnly) {
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
    } else {
      renderMarkupOverlay();
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
    </defs>${shapes}${pointToolPreviewMarkup()}${state.tempMarkup || ''}${searchHighlightMarkup()}`;
    updateMarkupToolbar();
    renderPropertiesPanel();
    renderMarkupList();
    updateViewerStatusBar();
  }

  function markupSvg(m) {
    const geom = resolveGeom(m.geometry || {});
    const style = m.style || {};
    const color = style.color || (m.layer === 'published' ? '#22c55e' : '#38bdf8');
    const sw = style.lineWidth || 2;
    const op = style.opacity != null ? style.opacity : 1;
    const fillOp = style.fillOpacity != null ? style.fillOpacity : 0.25;
    const fill = style.fill || (m.markup_type === 'highlight' ? `rgba(250,204,21,${fillOp})` : 'none');
    const selected = isMarkupSelected(m.id);
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
      const measureLabel = m.markup_type === 'measure' && m.measurement_value != null
        ? formatMeasurementDisplay(m) : '';
      visual = measureDimensionVisual(
        pts[0], pts[1], pts[2], pts[3],
        geom.offset || 0, selStroke, selSw, op, measureLabel,
      );
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
      let bx = Math.min(p[0], p[2]);
      let by = Math.min(p[1], p[3]);
      let bw = Math.max(Math.abs(p[2] - p[0]), 80);
      let bh = Math.max(Math.abs(p[3] - p[1]), 36);
      const tipX = geom.tipX != null ? geom.tipX : p[0];
      const tipY = geom.tipY != null ? geom.tipY : p[1];
      hit = `<rect data-markup-id="${id}" x="${bx}" y="${by}" width="${bw}" height="${bh}" fill="transparent" pointer-events="all"/>`;
      visual = calloutBubbleSvg({
        bx, by, bw, bh, tipX, tipY,
        color: selStroke, sw: selSw, op,
        fillOp: style.fillOpacity != null ? style.fillOpacity : 0.92,
        style, label: m.label, placeholder: !m.label,
        rx: style.bubbleRadius || 10,
      });
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
    } else if ((m.markup_type === 'pen' || m.markup_type === 'sketch') && geom.points) {
      const pts = geom.points;
      hit = `<path data-markup-id="${id}" d="${pointsToPath(pts, false)}" stroke="transparent" stroke-width="22" fill="none" pointer-events="stroke"/>`;
      visual = `<path d="${pointsToPath(pts, false)}" stroke="${selStroke}" stroke-width="${selSw}" fill="none" opacity="${op}" stroke-linecap="round" stroke-linejoin="round" pointer-events="none"/>`;
    } else if (m.markup_type === 'polyline' && geom.points) {
      hit = `<path data-markup-id="${id}" d="${pointsToPath(geom.points, false)}" stroke="transparent" stroke-width="22" fill="none" pointer-events="stroke"/>`;
      visual = `<path d="${pointsToPath(geom.points, false)}" stroke="${selStroke}" stroke-width="${selSw}" fill="none" opacity="${op}"${dash} pointer-events="none"/>`;
    } else if ((m.markup_type === 'polygon' || m.markup_type === 'area') && geom.points) {
      hit = `<path data-markup-id="${id}" d="${pointsToPath(geom.points, true)}" stroke="transparent" stroke-width="22" fill="rgba(0,0,0,0.01)" pointer-events="all"/>`;
      const fillCol = m.markup_type === 'area' ? `rgba(34,197,94,${fillOp})` : fill;
      const areaLabel = m.markup_type === 'area' && m.measurement_value != null ? formatMeasurementDisplay(m) : '';
      const cx = geom.points.reduce((s, v, i) => s + (i % 2 === 0 ? v : 0), 0) / (geom.points.length / 2);
      const cy = geom.points.reduce((s, v, i) => s + (i % 2 === 1 ? v : 0), 0) / (geom.points.length / 2);
      visual = `<path d="${pointsToPath(geom.points, true)}" stroke="${selStroke}" stroke-width="${selSw}" fill="${fillCol}" opacity="${op}"${dash} pointer-events="none"/>
        ${areaLabel ? `<text x="${cx}" y="${cy}" text-anchor="middle" fill="${selStroke}" font-size="12" font-weight="bold" pointer-events="none">${esc(areaLabel)}</text>` : ''}`;
    } else if (m.markup_type === 'crossout' && geom.w != null) {
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${geom.w}" height="${geom.h}" fill="transparent" pointer-events="all"/>`;
      visual = `<line x1="${geom.x}" y1="${geom.y}" x2="${geom.x + geom.w}" y2="${geom.y + geom.h}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}" pointer-events="none"/>
        <line x1="${geom.x + geom.w}" y1="${geom.y}" x2="${geom.x}" y2="${geom.y + geom.h}" stroke="${selStroke}" stroke-width="${selSw}" opacity="${op}" pointer-events="none"/>`;
    } else if (m.markup_type === 'stamp' && geom.x != null) {
      const tw = geom.w || 110;
      const th = geom.h || 32;
      const stampText = m.label || style.stampType || 'STAMP';
      const stampColor = style.color || color;
      hit = `<rect data-markup-id="${id}" x="${geom.x}" y="${geom.y}" width="${tw}" height="${th}" fill="transparent" pointer-events="all"/>`;
      visual = `<rect x="${geom.x}" y="${geom.y}" width="${tw}" height="${th}" rx="4" stroke="${stampColor}" stroke-width="2" fill="rgba(24,24,27,0.9)" opacity="${op}" pointer-events="none"/>
        <text x="${geom.x + tw / 2}" y="${geom.y + th / 2 + 4}" text-anchor="middle" fill="${stampColor}" font-size="${style.fontSize || 11}" font-weight="bold" pointer-events="none">${esc(stampText)}</text>`;
    } else if (m.markup_type === 'count' && geom.x != null) {
      const x = geom.x;
      const y = geom.y;
      const num = m.label || geom.countNum || '?';
      hit = `<circle data-markup-id="${id}" cx="${x}" cy="${y}" r="16" fill="transparent" pointer-events="all"/>`;
      visual = `<circle cx="${x}" cy="${y}" r="12" fill="${selStroke}" stroke="#fff" stroke-width="2" opacity="${op}" pointer-events="none"/>
        <text x="${x}" y="${y + 4}" text-anchor="middle" fill="#fff" font-size="10" font-weight="bold" pointer-events="none">${esc(String(num))}</text>`;
    } else if (m.markup_type === 'punch_pin') {
      const g = resolvePinGeom(m.geometry || {});
      return leaderPinSvg({
        id, anchorX: g.anchorX, anchorY: g.anchorY, badgeX: g.x, badgeY: g.y,
        color: '#8b5cf6', letter: 'P', pinType: 'punch', linkId: g.linkedPunchId || '',
        label: m.label || 'Punch', selected, pinSize: g.pinSize || 1,
      });
    } else if (m.markup_type === 'co_pin') {
      const g = resolvePinGeom(m.geometry || {});
      const coId = g.linkedCoId || m.linked_co_id;
      return leaderPinSvg({
        id, anchorX: g.anchorX, anchorY: g.anchorY, badgeX: g.x, badgeY: g.y,
        color: '#10b981', letter: 'CO', pinType: 'co', linkId: coId || '',
        label: m.label || 'Change Order', selected, pinSize: g.pinSize || 1,
      });
    } else if (m.markup_type === 'rfi_pin') {
      const g = resolvePinGeom(m.geometry || {});
      return leaderPinSvg({
        id, anchorX: g.anchorX, anchorY: g.anchorY, badgeX: g.x, badgeY: g.y,
        color: '#f97316', letter: 'R', pinType: 'rfi', linkId: m.linked_rfi_id || '',
        label: m.label || 'RFI', selected, pinSize: g.pinSize || 1,
      });
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
  const PIN_SIZE_PRESETS = [
    { label: 'Small', value: 0.75 }, { label: 'Medium', value: 1 }, { label: 'Large', value: 1.5 }, { label: 'XL', value: 2 },
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
    if (!silent) {
      renderPropertiesPanel();
      renderMarkupOverlay();
    } else {
      updateViewerStatusBar();
    }
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
    const showLine = ['line', 'arrow', 'rect', 'ellipse', 'cloud', 'measure', 'highlight', 'callout', 'pen', 'sketch', 'polyline', 'polygon', 'area', 'crossout', 'count', 'stamp'].includes(type);
    const showText = type === 'text' || type === 'textbox' || type === 'callout';
    const showArrow = type === 'arrow' || type === 'line' || type === 'callout';
    const showStamp = type === 'stamp';
    const showFill = ['rect', 'highlight', 'ellipse', 'text', 'textbox', 'callout'].includes(type);
    const geom = isSelected && ctx?.geometry ? resolveGeom(ctx.geometry) : null;
    const showSize = isSelected && ['rect', 'highlight', 'ellipse', 'cloud', 'textbox', 'callout'].includes(type);
    const isPinType = ['rfi_pin', 'co_pin', 'punch_pin'].includes(type);
    const showPinSize = isPinType && (isSelected || ['rfi_pin', 'co_pin', 'punch_pin'].includes(state.tool));
    const pinSize = isSelected && geom?.pinSize ? geom.pinSize : (state.pinSize || 1);
    const pinLink = isSelected ? pinLinkFromMarkup(ctx) : null;
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

    const meta = TOOL_META[type] || {};
    const toolHint = meta.hint || '';
    const showScale = !!state.openDrawing;
    const measureDisplay = isSelected && ctx?.markup_type === 'measure' && ctx.measurement_value != null
      ? formatMeasurementDisplay(ctx) : '';

    el.innerHTML = `
      ${!isSelected ? renderToolPaletteHtml() : ''}
      <div class="text-[10px] uppercase text-zinc-500 mb-1 sticky top-0 bg-zinc-800/95 py-1 z-10 border-b border-zinc-700/80">${esc(title)}</div>
      ${toolHint ? `<div class="markup-prop-hint mb-2">${esc(toolHint)}</div>` : ''}
      ${showLine ? propSection('Color & stroke', `
        ${propChips('Color', COLOR_PRESETS, color, 'color')}
        <div class="markup-prop-row">
          <label for="propColorPicker">Custom</label>
          <input type="color" id="propColorPicker" value="${color}">
        </div>
        ${propChips('Line weight', WIDTH_PRESETS, lineWidth, 'lineWidth')}
        ${propChips('Opacity', OPACITY_PRESETS, style.opacity ?? 1, 'opacity')}
        ${propRow('Dash px', 'propDashLen', dashParts.dash, 0, 64, 1, '0 = solid')}
        ${propRow('Gap px', 'propGapLen', dashParts.gap, 0, 64, 1)}
      `) : ''}
      ${showFill ? propSection('Fill', `
        ${propChips('Fill opacity', OPACITY_PRESETS, style.fillOpacity ?? (type === 'highlight' ? 0.25 : 0.75), 'fillOpacity')}
      `) : ''}
      ${showCloud ? propSection('Cloud', `
        ${propChips('Scallop size', CLOUD_PRESETS, cloudScallop, 'cloudScallop')}
      `) : ''}
      ${showText ? propSection('Text', `
        ${propChips('Font size', FONT_PRESETS, fontSize, 'fontSize')}
        ${propChips('Weight', FONT_WEIGHT_PRESETS, style.fontWeight || 'normal', 'fontWeight')}
        ${propChips('Align', TEXT_ALIGN_PRESETS, style.textAlign || 'left', 'textAlign')}
        ${type === 'text' || type === 'textbox' ? propChips('Border', [{ label: 'On', value: '1' }, { label: 'Off', value: '0' }], showTextBorder ? '1' : '0', 'showTextBorder') : ''}
        ${propRow('Pad px', 'propTextPadding', textPadding, 0, 48, 1)}
      `) : ''}
      ${showArrow ? propSection('Arrow', `
        ${propChips('Head', ARROW_HEAD_PRESETS, arrowHead, 'arrowHead')}
      `) : ''}
      ${showSize && geom ? propSection('Size', `
        ${propRow('Width', 'propGeomW', Math.round(geom.w || 0), 1, 8000, 1)}
        ${propRow('Height', 'propGeomH', Math.round(geom.h || 0), 1, 8000, 1)}
      `) : ''}
      ${showPinSize ? propSection('Pin size', `
        ${propChips('Badge size', PIN_SIZE_PRESETS, pinSize, 'pinSize')}
        <div class="markup-prop-hint">Double-click the pin badge to open the linked record.</div>
      `) : ''}
      ${isSelected && pinLink?.linkId && pinLink.pinType === 'rfi' ? `
        <button type="button" id="propOpenRfiBtn" class="w-full mt-2 px-2 py-1.5 rounded text-xs bg-orange-900/50 border border-orange-700 text-orange-200 hover:bg-orange-900">Open linked RFI</button>
      ` : ''}
      ${isSelected && pinLink?.linkId && pinLink.pinType === 'co' ? `
        <button type="button" id="propOpenCoBtn" class="w-full mt-2 px-2 py-1.5 rounded text-xs bg-emerald-900/50 border border-emerald-700 text-emerald-200 hover:bg-emerald-900">Open linked change order</button>
      ` : ''}
      ${showStamp ? propSection('Stamp type', `
        <div class="flex flex-wrap gap-1 mb-2">${STAMP_PRESETS.map(s => {
          const active = state.selectedStamp === s.value ? ' scale-preset-active' : '';
          return `<button type="button" class="scale-preset-btn${active}" data-stamp-value="${esc(s.value)}" style="border-color:${s.color}55">${esc(s.label)}</button>`;
        }).join('')}</div>
        <div class="markup-prop-hint">Click on the sheet to place the selected stamp.</div>
      `) : ''}
      ${isSelected && ctx?.markup_type === 'measure' && measureDisplay ? `
        <div class="markup-prop-hint">Length: <strong>${esc(measureDisplay)}</strong></div>
      ` : ''}
      ${isSelected && ctx?.markup_type === 'area' && ctx.measurement_value != null ? `
        <div class="markup-prop-hint">Area: <strong>${esc(formatMeasurementDisplay(ctx))}</strong></div>
      ` : ''}
      ${isSelected && showText ? propSection('Content', `
        <textarea id="propTextLabel" rows="4" class="w-full bg-zinc-900 border border-zinc-700 rounded p-2 text-xs text-white" placeholder="Type your note…">${esc(ctx.label || '')}</textarea>
      `) : ''}
      ${showScale ? propSection('Drawing scale', `
        <div class="markup-prop-hint">
          ${state.scaleLabel ? `Active scale: <strong>${esc(state.scaleLabel)}</strong>` : (state.pixelsPerUnit ? 'Scale: <strong>Calibrated on sheet</strong>' : 'No scale set — measurements show in pixels until you set one.')}
        </div>
        <div class="flex flex-wrap gap-1 mb-2">${SCALE_PRESETS.map(p => {
          const active = state.scalePdfPointsPerFoot && Math.abs(state.scalePdfPointsPerFoot - p.pdfPtsPerFoot) < 0.05;
          return `<button type="button" class="scale-preset-btn${active ? ' scale-preset-active' : ''}" data-scale-pts="${p.pdfPtsPerFoot}" data-scale-label="${esc(p.label)}">${esc(p.label)}</button>`;
        }).join('')}</div>
        <div class="markup-prop-row">
          <label for="propScaleInput">Custom</label>
          <input type="text" id="propScaleInput" placeholder='1/4"=1\'' class="text-left">
        </div>
        <button type="button" id="propScaleApplyBtn" class="w-full py-1.5 mb-1 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px]">Apply custom scale</button>
        <button type="button" id="propDetectScaleBtn" class="w-full py-1.5 mb-1 bg-sky-900/50 hover:bg-sky-900 rounded text-[10px] text-sky-200">Auto-detect from title block</button>
        <button type="button" id="propCalibrateBtn" class="w-full py-1.5 mb-1 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px]">Calibrate on a known dimension…</button>
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

    el.querySelectorAll('.prop-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const prop = chip.getAttribute('data-prop');
        const val = chip.getAttribute('data-value');
        if (prop === 'color') applyMarkupProperty({ color: val });
        else if (prop === 'lineWidth') applyMarkupProperty({ lineWidth: parseFloat(val) });
        else if (prop === 'opacity') applyMarkupProperty({ opacity: parseFloat(val) });
        else if (prop === 'fillOpacity') applyMarkupProperty({ fillOpacity: parseFloat(val) });
        else if (prop === 'cloudScallop') applyMarkupProperty({ cloudScallop: parseInt(val, 10) });
        else if (prop === 'fontSize') applyMarkupProperty({ fontSize: parseInt(val, 10) });
        else if (prop === 'fontWeight') applyMarkupProperty({ fontWeight: val });
        else if (prop === 'textAlign') applyMarkupProperty({ textAlign: val });
        else if (prop === 'showTextBorder') applyMarkupProperty({ showTextBorder: val === '1' });
        else if (prop === 'arrowHead') applyMarkupProperty({ arrowHead: val });
        else if (prop === 'pinSize') applyPinSize(parseFloat(val));
        renderPropertiesPanel();
        renderMarkupOverlay();
      });
    });

    el.querySelectorAll('.scale-preset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const pts = parseFloat(btn.getAttribute('data-scale-pts'));
        const lbl = btn.getAttribute('data-scale-label');
        applyScalePreset(pts, lbl);
        renderPropertiesPanel();
      });
    });

    el.querySelectorAll('[data-palette-tool]').forEach(btn => {
      btn.addEventListener('click', () => {
        setTool(btn.getAttribute('data-palette-tool'));
      });
    });

    el.querySelectorAll('[data-stamp-value]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.selectedStamp = btn.getAttribute('data-stamp-value');
        const preset = STAMP_PRESETS.find(s => s.value === state.selectedStamp);
        if (preset) applyMarkupProperty({ color: preset.color, stampType: preset.value });
        renderPropertiesPanel();
      });
    });
    bindLiveNum('propTextPadding', (input) => {
      const val = parseInt(input.value, 10);
      if (!Number.isNaN(val)) applyMarkupProperty({ textPadding: val });
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

    const colorPicker = document.getElementById('propColorPicker');
    if (colorPicker) colorPicker.addEventListener('input', () => {
      applyMarkupProperty({ color: colorPicker.value });
      renderPropertiesPanel();
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
    document.getElementById('propCalibrateBtn')?.addEventListener('click', () => { setTool('calibrate'); toast('Click two points on a known distance on the drawing'); });
    document.getElementById('propDetectScaleBtn')?.addEventListener('click', detectScale);
    document.getElementById('propScaleApplyBtn')?.addEventListener('click', applyManualScaleInput);
    document.getElementById('propScaleInput')?.addEventListener('keydown', e => { if (e.key === 'Enter') applyManualScaleInput(); });
    document.getElementById('propDeleteBtn')?.addEventListener('click', deleteSelectedMarkup);
    document.getElementById('propOpenRfiBtn')?.addEventListener('click', () => {
      const link = pinLinkFromMarkup(ctx);
      if (link.linkId) openPinLink('rfi', link.linkId);
    });
    document.getElementById('propOpenCoBtn')?.addEventListener('click', () => {
      const link = pinLinkFromMarkup(ctx);
      if (link.linkId) openPinLink('co', link.linkId);
    });
  }

  async function applyPinSize(size) {
    const val = Math.max(0.5, Math.min(3, parseFloat(size) || 1));
    state.pinSize = val;
    if (state.selectedMarkupId) {
      const m = state.markups.find(x => x.id === state.selectedMarkupId);
      if (m && ['rfi_pin', 'co_pin', 'punch_pin'].includes(m.markup_type)) {
        m.geometry = normalizeGeometry({ ...(m.geometry || {}), pinSize: val });
        await persistMarkup(m, { geometry: m.geometry });
        renderMarkupOverlay();
      }
    }
    renderPropertiesPanel();
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
      const feet = pxDist / state.pixelsPerUnit;
      return {
        value: Math.round(feet * 10000) / 10000,
        display: formatFeetInches(feet),
        unit: 'ft-in',
      };
    }
    const px = Math.round(pxDist);
    return { value: px, display: `${px} px`, unit: 'px' };
  }

  function setTool(tool) {
    if (state.tool !== tool) {
      clearMarkupSelection();
      state.draggingMarkup = null;
      state.pendingDrag = null;
      state.drawing = false;
      state.drawStart = null;
      state.tempMarkup = null;
      state.penPoints = null;
      state.pathPoints = null;
      state.selectMarquee = false;
      resetMeasureState();
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
    updateViewerStatusBar();
    if (tool === 'measure' && !state.pixelsPerUnit) {
      toast('Set the drawing scale first — pick a preset in the side panel or calibrate on a known dimension');
    }
  }

  function updateViewerCursor() {
    const wrap = document.getElementById('drawViewerWrap');
    if (!wrap) return;
    wrap.classList.remove('cursor-grab', 'cursor-grabbing', 'cursor-crosshair', 'cursor-pointer', 'search-snipping', 'doc-snipping');
    if (state.searchSnipping) {
      wrap.classList.add('search-snipping', 'cursor-crosshair');
      return;
    }
    if (state.docSnipping) {
      wrap.classList.add('doc-snipping', 'cursor-crosshair');
      return;
    }
    if (state.isPanning) wrap.classList.add('cursor-grabbing');
    else if (state.tool === 'pan') wrap.classList.add('cursor-grab');
    else if (state.tool === 'select') wrap.classList.add('cursor-pointer');
    else wrap.classList.add('cursor-crosshair');
  }

  function highlightActiveTool() {
    MARKUP_TOOLS.forEach(t => {
      const btn = document.getElementById(`tool-${t}`);
      if (!btn) return;
      btn.classList.toggle('tool-active', state.tool === t);
    });
  }

  function setMarkupColor(color) { applyMarkupProperty({ color }); }
  function setMarkupLineWidth(width) { applyMarkupProperty({ lineWidth: parseInt(width, 10) || 2 }); }

  function updateMarkupToolbar() {
    const btn = document.getElementById('btnDeleteMarkup');
    const hasSelection = state.selectedMarkupIds.size > 0 || state.selectedMarkupId;
    if (btn) btn.classList.toggle('hidden', !hasSelection);
  }

  async function deleteSelectedMarkup() {
    const ids = state.selectedMarkupIds.size
      ? [...state.selectedMarkupIds]
      : (state.selectedMarkupId ? [state.selectedMarkupId] : []);
    if (!ids.length) return;
    const label = ids.length === 1 ? 'Delete this markup?' : `Delete ${ids.length} markups?`;
    if (!await drawConfirm(label, { title: 'Delete markup', danger: true, confirmLabel: 'Delete' })) return;
    for (const id of ids) {
      try {
        await api(`/api/drawings/markups/${id}`, { method: 'DELETE' });
      } catch (e) {
        if (e.status !== 404) { alert(e.message); return; }
      }
    }
    state.markups = state.markups.filter(x => !ids.includes(x.id));
    clearMarkupSelection();
    renderMarkupOverlay();
    renderPropertiesPanel();
    toast(ids.length === 1 ? 'Markup deleted' : `${ids.length} markups deleted`);
  }

  function bindTextDialog() {
    const dialog = document.getElementById('drawTextDialog');
    if (!dialog || dialog._bound) return;
    dialog._bound = true;
    const closeDialog = () => {
      state.textEditorOpen = false;
      state.textDialogCtx = null;
      dialog.close();
    };
    document.getElementById('drawTextDialogClose')?.addEventListener('click', closeDialog);
    document.getElementById('drawTextDialogCancel')?.addEventListener('click', closeDialog);
    document.getElementById('drawTextDialogSave')?.addEventListener('click', async () => {
      const ctx = state.textDialogCtx;
      const input = document.getElementById('drawTextDialogInput');
      const text = input?.value.trim() || '';
      closeDialog();
      if (!text || !ctx) return;
      if (ctx.existingMarkup) {
        ctx.existingMarkup.label = text;
        await persistMarkup(ctx.existingMarkup, { label: text });
        renderMarkupOverlay();
        return;
      }
      const lines = text.split('\n');
      const fontSize = state.markupStyle.fontSize || 14;
      const geom = ctx.pendingGeometry || {
        x: ctx.pt.x,
        y: ctx.pt.y,
        w: 220,
        h: Math.max(28, lines.length * (fontSize + 6) + 12),
      };
      await saveMarkup({
        markup_type: 'textbox',
        geometry: geom,
        label: text,
        style: { ...toolStyle('text'), fillOpacity: toolStyle('text').fillOpacity ?? 0.9 },
      });
    });
    dialog.addEventListener('cancel', (e) => {
      e.preventDefault();
      state.textEditorOpen = false;
      state.textDialogCtx = null;
    });
  }

  function showTextEditor(pt, existingMarkup, pendingGeometry) {
    bindTextDialog();
    const dialog = document.getElementById('drawTextDialog');
    if (!dialog || state.textEditorOpen) return;
    state.textEditorOpen = true;
    state.textDialogCtx = { pt, existingMarkup, pendingGeometry };
    const titleEl = document.getElementById('drawTextDialogTitle');
    if (titleEl) {
      titleEl.textContent = existingMarkup?.markup_type === 'callout' ? 'Callout note' : 'Markup text';
    }
    const input = document.getElementById('drawTextDialogInput');
    if (input) {
      input.value = existingMarkup?.label || '';
      dialog.showModal();
      input.focus();
    }
  }

  function onViewerKeyDown(e) {
    if (!state.openDrawing || state.view !== 'viewer') return;
    const tag = (e.target?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target?.isContentEditable) return;
    if ((e.key === 'Delete' || e.key === 'Backspace') && (state.selectedMarkupIds.size || state.selectedMarkupId)) {
      e.preventDefault();
      deleteSelectedMarkup();
      return;
    }
    if (e.key === 'Escape') {
      if (state.docSnipping) {
        e.preventDefault();
        cancelDocSnip();
        return;
      }
      if (state.searchSnipping) {
        e.preventDefault();
        state.searchSnipping = false;
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        updateViewerCursor();
        renderMarkupOverlay();
        return;
      }
      clearMarkupSelection();
      state.drawing = false;
      state.drawStart = null;
      state.tempMarkup = null;
      state.penPoints = null;
      state.pathPoints = null;
      state.selectMarquee = false;
      resetMeasureState();
      setTool('pan');
      return;
    }
    if (e.key === 'Enter' && state.pathPoints && state.pathPoints.length >= 4) {
      e.preventDefault();
      finishPathTool();
      return;
    }
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const tool = TOOL_SHORTCUTS[e.key.toLowerCase()];
    if (tool) {
      e.preventDefault();
      setTool(tool);
    }
  }

  function onViewerDblClick(evt) {
    const badge = evt.target.closest?.('[data-pin-badge]');
    if (badge) {
      evt.preventDefault();
      evt.stopPropagation();
      handlePinBadgeActivate(badge);
      return;
    }
    const pt = screenToDoc(evt);
    const hit = hitTestMarkup(pt);
    if (!hit) return;
    if (hit.markup_type === 'rfi_pin' || hit.markup_type === 'co_pin') {
      const link = pinLinkFromMarkup(hit);
      if (link.linkId) openPinLink(link.pinType, link.linkId);
      return;
    }
    if (state.tool !== 'select' && state.tool !== 'pan') return;
    if (hit.markup_type === 'text' || hit.markup_type === 'textbox' || hit.markup_type === 'callout') {
      setMarkupSelection(new Set([hit.id]), hit.id);
      const g = resolveGeom(hit.geometry || {});
      showTextEditor({ x: g.x + 8, y: g.y + 8 }, hit);
      renderMarkupOverlay();
    }
  }

  function bindMarkupSvgEvents() {
    const svg = document.getElementById('drawMarkupSvg');
    if (!svg || svg._pinEventsBound) return;
    svg._pinEventsBound = true;
    svg.addEventListener('click', e => {
      const badge = e.target.closest('[data-pin-badge]');
      if (!badge) return;
      e.stopPropagation();
      if (registerPinBadgeTap(badge)) {
        e.preventDefault();
      }
    });
    svg.addEventListener('dblclick', e => {
      const badge = e.target.closest('[data-pin-badge]');
      if (!badge) return;
      e.preventDefault();
      e.stopPropagation();
      state.lastPinTap = { key: '', t: 0 };
      handlePinBadgeActivate(badge);
    });
  }

  function bindViewerEvents() {
    const wrap = document.getElementById('drawViewerWrap');
    if (!wrap || wrap._bound) return;
    wrap._bound = true;
    bindMarkupSvgEvents();
    wrap.addEventListener('mousedown', onViewerDown);
    wrap.addEventListener('mousemove', onViewerMove);
    wrap.addEventListener('mouseup', onViewerUp);
    wrap.addEventListener('mouseleave', onViewerUp);
    wrap.addEventListener('wheel', onViewerWheel, { passive: false });
    wrap.addEventListener('dblclick', onViewerDblClick);
    document.addEventListener('keydown', onViewerKeyDown);
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
      schedulePdfQualityRerender();
    });
  }

  async function onViewerDown(evt) {
    if (evt.button !== 0) return;
    if (isViewerSnipping()) {
      evt.preventDefault();
      state.drawing = true;
      state.drawStart = screenToDoc(evt);
      return;
    }
    if (state.tool === 'pan' || evt.altKey) {
      state.isPanning = true;
      state.panAnchor = { x: evt.clientX - state.panX, y: evt.clientY - state.panY };
      updateViewerCursor();
      return;
    }
    if (state.tool === 'select') {
      const pt = screenToDoc(evt);
      const hit = hitTestMarkup(pt);
      if (hit) {
        if (evt.shiftKey) {
          const ids = new Set(state.selectedMarkupIds);
          if (ids.has(hit.id)) ids.delete(hit.id);
          else ids.add(hit.id);
          setMarkupSelection(ids, hit.id);
        } else {
          setMarkupSelection(new Set([hit.id]), hit.id);
          state.pendingDrag = {
            id: hit.id,
            startPt: pt,
            orig: JSON.parse(JSON.stringify(hit.geometry || {})),
            moved: false,
          };
        }
        state.draggingMarkup = null;
        renderMarkupOverlay();
        renderPropertiesPanel();
        return;
      }
      state.selectMarquee = true;
      state.drawing = true;
      state.drawStart = pt;
      state.pendingDrag = null;
      state.draggingMarkup = null;
      if (!evt.shiftKey) clearMarkupSelection();
      return;
    }
    const pt = screenToDoc(evt);
    if (state.tool === 'pen') {
      state.drawing = true;
      state.penPoints = [pt.x, pt.y];
      return;
    }
    if (['polyline', 'polygon', 'area'].includes(state.tool)) {
      if (!state.pathPoints) state.pathPoints = [];
      state.pathPoints.push(pt.x, pt.y);
      const activeStyle = toolStyle(state.tool);
      const color = activeStyle.color || '#38bdf8';
      const closed = state.tool !== 'polyline';
      state.tempMarkup = `<path d="${pointsToPath(state.pathPoints, closed)}" stroke="${color}" stroke-width="2" fill="${closed ? 'rgba(56,189,248,0.08)' : 'none'}" stroke-dasharray="4 3"/>`;
      renderMarkupOverlay();
      return;
    }
    if (state.tool === 'count') {
      placeCountMarker(pt);
      return;
    }
    if (state.tool === 'stamp') {
      placeStamp(pt);
      return;
    }
    if (state.tool === 'rfi_pin') {
      placeRfiPin(pt);
      return;
    }
    if (state.tool === 'co_pin') {
      placeCoPin(pt);
      return;
    }
    if (state.tool === 'punch_pin') {
      placePunchPin(pt);
      return;
    }
    if (isTwoPointClickTool(state.tool)) {
      state.pointPointerDown = true;
      state.pointDownPt = pt;
      state.pointDidDrag = false;
      return;
    }
  }

  function onViewerMove(evt) {
    if (state.isPanning && state.panAnchor) {
      state.panX = evt.clientX - state.panAnchor.x;
      state.panY = evt.clientY - state.panAnchor.y;
      applyViewTransform();
      return;
    }
    if (isTwoPointClickTool(state.tool)) {
      const pt = screenToDoc(evt);
      if (state.pointPointerDown && state.pointDownPt) {
        if (Math.hypot(pt.x - state.pointDownPt.x, pt.y - state.pointDownPt.y) > 4) {
          state.pointDidDrag = true;
        }
      }
      if (state.tool === 'measure' && state.pointPhase === 'offset' && state.pointA && state.pointB) {
        state.pointOffset = measurePerpOffset(
          state.pointA.x, state.pointA.y,
          state.pointB.x, state.pointB.y,
          pt.x, pt.y,
        );
        state.tempMarkup = null;
        renderMarkupOverlay();
        return;
      }
      if (state.pointPhase === 'second' && state.pointA) {
        state.tempMarkup = buildTwoPointPreview(
          state.tool, state.pointA.x, state.pointA.y, pt.x, pt.y,
        );
        renderMarkupOverlay();
        return;
      }
      if (state.pointPointerDown && state.pointDidDrag && state.pointDownPt) {
        const down = state.pointDownPt;
        state.tempMarkup = buildTwoPointPreview(state.tool, down.x, down.y, pt.x, pt.y);
        renderMarkupOverlay();
        return;
      }
    }
    if (state.pendingDrag && !state.draggingMarkup) {
      const pt = screenToDoc(evt);
      const dx = pt.x - state.pendingDrag.startPt.x;
      const dy = pt.y - state.pendingDrag.startPt.y;
      if (Math.hypot(dx, dy) > 4) {
        state.draggingMarkup = { ...state.pendingDrag };
        state.pendingDrag = null;
      }
    }
    if (isViewerSnipping() && state.drawing && state.drawStart) {
      const pt = screenToDoc(evt);
      const s = state.drawStart;
      const x = Math.min(s.x, pt.x);
      const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x);
      const rh = Math.abs(pt.y - s.y);
      state.tempMarkup = snipRectPreview(x, y, rw, rh);
      renderMarkupOverlay();
      return;
    }
    if (state.tool === 'select' && state.selectMarquee && state.drawing && state.drawStart) {
      const pt = screenToDoc(evt);
      const s = state.drawStart;
      const x = Math.min(s.x, pt.x);
      const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x);
      const rh = Math.abs(pt.y - s.y);
      state.tempMarkup = `<rect x="${x}" y="${y}" width="${rw}" height="${rh}" stroke="#fbbf24" stroke-width="2" fill="rgba(251,191,36,0.12)" stroke-dasharray="4 2"/>`;
      renderMarkupOverlay();
      return;
    }
    if (state.draggingMarkup) {
      const pt = screenToDoc(evt);
      const m = state.markups.find(x => x.id === state.draggingMarkup.id);
      if (m) {
        const dx = pt.x - state.draggingMarkup.startPt.x;
        const dy = pt.y - state.draggingMarkup.startPt.y;
        if (Math.hypot(dx, dy) > 2) state.draggingMarkup.moved = true;
        const pinTypes = ['rfi_pin', 'co_pin', 'punch_pin'];
        m.geometry = pinTypes.includes(m.markup_type)
          ? translatePinBadgeGeometry(state.draggingMarkup.orig, dx, dy)
          : translateGeometry(state.draggingMarkup.orig, dx, dy);
        renderMarkupOverlay();
      }
      return;
    }
    if (state.tool === 'pen' && state.drawing && state.penPoints) {
      const pt = screenToDoc(evt);
      const pts = state.penPoints;
      const lx = pts[pts.length - 2];
      const ly = pts[pts.length - 1];
      if (Math.hypot(pt.x - lx, pt.y - ly) > 2) {
        state.penPoints.push(pt.x, pt.y);
        const color = toolStyle('pen').color || '#ef4444';
        const sw = toolStyle('pen').lineWidth || 2;
        state.tempMarkup = `<path d="${pointsToPath(state.penPoints, false)}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>`;
        renderMarkupOverlay();
      }
      return;
    }
    if (!state.drawing || !state.drawStart) return;
    if (isTwoPointClickTool(state.tool)) return;
    const pt = screenToDoc(evt);
    const s = state.drawStart;
    const activeStyle = toolStyle(state.tool);
    const sw = activeStyle.lineWidth || 2;
    const color = activeStyle.color || '#38bdf8';
    const scallop = activeStyle.cloudScallop || 18;
    if (['rect', 'highlight', 'ellipse', 'text', 'crossout'].includes(state.tool)) {
      const x = Math.min(s.x, pt.x); const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x); const rh = Math.abs(pt.y - s.y);
      if (state.tool === 'ellipse') {
        state.tempMarkup = `<ellipse cx="${x + rw / 2}" cy="${y + rh / 2}" rx="${rw / 2}" ry="${rh / 2}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
      } else {
        state.tempMarkup = `<rect x="${x}" y="${y}" width="${rw}" height="${rh}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
      }
    } else if (state.tool === 'callout') {
      const x = Math.min(s.x, pt.x);
      const y = Math.min(s.y, pt.y);
      const rw = Math.max(Math.abs(pt.x - s.x), 80);
      const rh = Math.max(Math.abs(pt.y - s.y), 36);
      state.tempMarkup = calloutBubbleSvg({
        bx: x, by: y, bw: rw, bh: rh,
        tipX: s.x, tipY: s.y,
        color, sw, op: 0.85,
        fillOp: activeStyle.fillOpacity ?? 0.5,
        style: activeStyle,
        placeholder: true,
      });
    } else if (state.tool === 'cloud') {
      const x = Math.min(s.x, pt.x); const y = Math.min(s.y, pt.y);
      state.tempMarkup = `<path d="${cloudPath(x, y, Math.abs(pt.x - s.x), Math.abs(pt.y - s.y), scallop)}" stroke="${color}" stroke-width="${sw}" fill="none" stroke-dasharray="4 3" />`;
    } else if (['line', 'arrow'].includes(state.tool)) {
      const marker = state.tool === 'arrow' ? ' marker-end="url(#arrowhead)"' : '';
      state.tempMarkup = `<line x1="${s.x}" y1="${s.y}" x2="${pt.x}" y2="${pt.y}" stroke="${color}" stroke-width="${sw}" stroke-dasharray="4 3"${marker} />`;
    }
    renderMarkupOverlay();
  }

  async function onViewerUp(evt) {
    if (isTwoPointClickTool(state.tool) && state.pointPointerDown && evt.type === 'mouseleave') {
      state.pointPointerDown = false;
      state.pointDownPt = null;
      state.pointDidDrag = false;
      state.tempMarkup = null;
      renderMarkupOverlay();
      return;
    }
    if (state.docSnipping && state.drawing && state.drawStart) {
      const pt = screenToDoc(evt);
      const s = state.drawStart;
      const x = Math.min(s.x, pt.x);
      const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x);
      const rh = Math.abs(pt.y - s.y);
      state.drawing = false;
      state.drawStart = null;
      state.docSnipping = false;
      state.tempMarkup = null;
      updateViewerCursor();
      if (rw >= 8 && rh >= 8) {
        const captured = captureCanvasRegion(x, y, rw, rh, { fullRes: true });
        if (captured?.dataUrl) openDocSnipSaveDialog(captured);
      } else {
        toast('Drag a larger box to snip');
      }
      renderMarkupOverlay();
      return;
    }
    if (state.searchSnipping && state.drawing && state.drawStart) {
      const pt = screenToDoc(evt);
      const s = state.drawStart;
      const x = Math.min(s.x, pt.x);
      const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x);
      const rh = Math.abs(pt.y - s.y);
      state.drawing = false;
      state.drawStart = null;
      state.searchSnipping = false;
      state.tempMarkup = null;
      updateViewerCursor();
      if (rw >= 8 && rh >= 8) {
        const captured = captureCanvasRegion(x, y, rw, rh);
        if (captured?.dataUrl) {
          state.searchTemplate = captured.dataUrl;
          state.searchSnipDocW = captured.docW;
          state.searchSnipDocH = captured.docH;
          const prev = document.getElementById('drawSearchShapePreview');
          if (prev) {
            prev.src = captured.dataUrl;
            prev.classList.remove('hidden');
          }
          await runShapeSearch();
        }
      }
      renderMarkupOverlay();
      return;
    }
    if (state.isPanning) {
      state.isPanning = false;
      state.panAnchor = null;
      updateViewerCursor();
      return;
    }
    if (state.pendingDrag && !state.draggingMarkup) {
      state.pendingDrag = null;
    }
    if (state.draggingMarkup) {
      const drag = state.draggingMarkup;
      const m = state.markups.find(x => x.id === drag.id);
      const moved = drag.moved;
      state.draggingMarkup = null;
      if (m && moved) {
        m.geometry = normalizeGeometry(m.geometry || {});
        await persistMarkup(m, { geometry: m.geometry });
      }
      renderPropertiesPanel();
      return;
    }
    if (state.tool === 'select' && state.selectMarquee && state.drawing && state.drawStart) {
      const pt = screenToDoc(evt);
      const s = state.drawStart;
      const x = Math.min(s.x, pt.x);
      const y = Math.min(s.y, pt.y);
      const rw = Math.abs(pt.x - s.x);
      const rh = Math.abs(pt.y - s.y);
      state.selectMarquee = false;
      state.drawing = false;
      state.drawStart = null;
      state.tempMarkup = null;
      if (rw >= 5 && rh >= 5) {
        const rect = { x, y, w: rw, h: rh };
        const ids = evt.shiftKey ? new Set(state.selectedMarkupIds) : new Set();
        visibleMarkups().forEach(m => {
          if (markupIntersectsRect(m, rect)) ids.add(m.id);
        });
        const primary = ids.size ? [...ids][ids.size - 1] : null;
        setMarkupSelection(ids, primary);
      }
      renderMarkupOverlay();
      renderPropertiesPanel();
      return;
    }
    if (state.tool === 'pen' && state.drawing) {
      if (state.penPoints && state.penPoints.length >= 4) {
        await saveMarkup({
          markup_type: 'sketch',
          geometry: { points: state.penPoints.slice() },
          style: { ...toolStyle('pen') },
        });
      }
      state.drawing = false;
      state.penPoints = null;
      state.tempMarkup = null;
      return;
    }
    if (isTwoPointClickTool(state.tool) && state.pointPointerDown) {
      const pt = screenToDoc(evt);
      state.pointPointerDown = false;
      const down = state.pointDownPt;
      state.pointDownPt = null;
      const didDrag = state.pointDidDrag;
      state.pointDidDrag = false;
      await handlePointToolUp(pt, didDrag, down);
      return;
    }
    if (!state.drawing || !state.drawStart) return;
    if (isTwoPointClickTool(state.tool)) return;
    const pt = screenToDoc(evt);
    const s = state.drawStart;
    const type = state.tool;
    let geometry = {};
    let measurement_value = null;
    let label = null;
    if (['rect', 'cloud', 'highlight', 'ellipse', 'text', 'crossout'].includes(type)) {
      geometry = { x: Math.min(s.x, pt.x), y: Math.min(s.y, pt.y), w: Math.abs(pt.x - s.x), h: Math.abs(pt.y - s.y) };
      if (geometry.w < 3 && geometry.h < 3) {
        if (type === 'text') {
          const hit = hitTestMarkup(pt);
          if (hit && (hit.markup_type === 'text' || hit.markup_type === 'textbox')) {
            setMarkupSelection(new Set([hit.id]), hit.id);
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
      const bx = Math.min(s.x, pt.x);
      const by = Math.min(s.y, pt.y);
      const bw = Math.max(Math.abs(pt.x - s.x), 80);
      const bh = Math.max(Math.abs(pt.y - s.y), 36);
      geometry = {
        x: bx, y: by, w: bw, h: bh,
        points: [s.x, s.y, bx + bw, by + bh],
        tipX: s.x, tipY: s.y,
      };
      if (bw < 24 && bh < 20) {
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        return;
      }
      label = '';
    } else if (['line', 'arrow'].includes(type)) {
      const pxLen = Math.hypot(pt.x - s.x, pt.y - s.y);
      if (pxLen < 3) {
        state.drawing = false;
        state.drawStart = null;
        state.tempMarkup = null;
        return;
      }
      geometry = { points: [s.x, s.y, pt.x, pt.y] };
    }
    state.drawing = false;
    state.drawStart = null;
    state.tempMarkup = null;
    const measureInfo = null;
    const saveType = type === 'crossout' ? 'crossout' : type;
    await saveMarkup({
      markup_type: saveType,
      geometry,
      measurement_value,
      measurement_unit: measureInfo ? measureInfo.unit : (state.pixelsPerUnit ? state.measureUnit : 'px'),
      label,
      style: { ...toolStyle(type) },
    });
    if (type === 'callout') {
      const last = state.markups[state.markups.length - 1];
      if (last) {
        const g = resolveGeom(last.geometry || {});
        showTextEditor({ x: g.x + 8, y: g.y + 8 }, last);
      }
    }
  }

  async function finishPathTool() {
    if (!state.pathPoints || state.pathPoints.length < 4) {
      state.pathPoints = null;
      state.tempMarkup = null;
      renderMarkupOverlay();
      return;
    }
    const type = state.tool;
    const points = state.pathPoints.slice();
    let measurement_value = null;
    let measurement_unit = null;
    if (type === 'area') {
      const pxArea = polygonAreaPx(points);
      if (state.pixelsPerUnit) {
        measurement_value = pxArea / (state.pixelsPerUnit * state.pixelsPerUnit);
        measurement_unit = 'sf';
      } else {
        measurement_value = pxArea;
        measurement_unit = 'px';
      }
    }
    state.pathPoints = null;
    state.tempMarkup = null;
    await saveMarkup({
      markup_type: type,
      geometry: { points },
      measurement_value,
      measurement_unit,
      style: { ...toolStyle(type) },
    });
  }

  async function placeCountMarker(pt) {
    const num = state.countCounter++;
    await saveMarkup({
      markup_type: 'count',
      geometry: { x: pt.x, y: pt.y, countNum: num },
      label: String(num),
      style: { ...toolStyle('count') },
    });
  }

  async function placeStamp(pt) {
    const preset = STAMP_PRESETS.find(s => s.value === state.selectedStamp) || STAMP_PRESETS[0];
    const text = preset.value;
    const w = Math.max(90, text.length * 7 + 20);
    await saveMarkup({
      markup_type: 'stamp',
      geometry: { x: pt.x - w / 2, y: pt.y - 16, w, h: 32 },
      label: text,
      style: { ...toolStyle('stamp'), color: preset.color, stampType: text },
    });
  }

  function focusPlacedPin(markup) {
    if (!markup?.id) return;
    state.tool = 'select';
    setMarkupSelection(new Set([markup.id]), markup.id);
    state.pendingDrag = null;
    state.draggingMarkup = null;
    const g = markup.geometry || {};
    if (g.pinSize != null) state.pinSize = g.pinSize;
    highlightActiveTool();
    updateViewerCursor();
    renderMarkupOverlay();
    renderPropertiesPanel();
  }

  async function placeRfiPin(pt) {
    if (!state.rfis.length) {
      alert('No RFIs on this project. Create an RFI first.');
      return;
    }
    const picked = await drawSelect({
      title: 'Link RFI pin',
      message: 'Choose the RFI to pin at this location on the sheet.',
      items: state.rfis.map(r => ({ value: r.id, label: `${r.number} — ${r.subject}` })),
      submitLabel: 'Place pin',
      emptyLabel: 'No RFIs found on this project',
    });
    if (!picked) return;
    const rfi = state.rfis.find(r => r.id === picked.value);
    if (!rfi) return;
    const markup = await saveMarkup({
      markup_type: 'rfi_pin',
      geometry: pinGeometryAt(pt),
      linked_rfi_id: rfi.id,
      label: rfi.number,
      publish: true,
    });
    focusPlacedPin(markup);
  }

  async function placeCoPin(pt) {
    if (!state.changeOrders.length) await loadChangeOrders();
    if (!state.changeOrders.length) {
      alert('No change orders on this project. Create a change order first.');
      return;
    }
    const picked = await drawSelect({
      title: 'Link change order pin',
      message: 'Choose the change order to pin at this location on the sheet.',
      items: state.changeOrders.map(c => ({
        value: c.id,
        label: `${c.number} — ${(c.title || c.description || '').slice(0, 80)}`,
      })),
      submitLabel: 'Place pin',
      emptyLabel: 'No change orders found on this project',
    });
    if (!picked) return;
    const co = state.changeOrders.find(c => c.id === picked.value);
    if (!co) return;
    const geom = pinGeometryAt(pt);
    geom.linkedCoId = co.id;
    const markup = await saveMarkup({
      markup_type: 'co_pin',
      geometry: geom,
      label: co.number,
      publish: true,
    });
    focusPlacedPin(markup);
  }

  async function placePunchPin(pt) {
    if (!state.punchItems.length) await loadPunchItems();
    if (!state.punchItems.length) {
      alert('No open punch list items on this project.');
      return;
    }
    const picked = await drawSelect({
      title: 'Link punch pin',
      message: 'Choose the punch list item to pin at this location.',
      items: state.punchItems.map(p => ({
        value: p.id,
        label: `${p.number || 'PL'} — ${(p.description || '').slice(0, 80)}`,
      })),
      submitLabel: 'Place pin',
      emptyLabel: 'No open punch items found',
    });
    if (!picked) return;
    const item = state.punchItems.find(p => p.id === picked.value);
    if (!item) return;
    const geom = pinGeometryAt(pt);
    geom.linkedPunchId = item.id;
    const markup = await saveMarkup({
      markup_type: 'punch_pin',
      geometry: geom,
      label: item.number || `PL-${item.id}`,
      publish: true,
    });
    focusPlacedPin(markup);
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
    return json.markup;
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
    const costCode = await drawPrompt('', '01-000', {
      title: 'Export takeoff to budget',
      label: 'Cost code for takeoff lines',
      submitLabel: 'Export',
    });
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
      if (await drawConfirm(`Open Budget to review ${json.imported} imported takeoff line(s)?`, { title: 'Open Budget', confirmLabel: 'Open Budget' })) {
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

  function collectPdfFiles(fileList) {
    return [...(fileList || [])].filter(
      (f) => f.name?.toLowerCase().endsWith('.pdf') || f.type === 'application/pdf'
    );
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

  function setUploadModalFiles(files) {
    const fileInput = document.getElementById('uploadFile');
    const nameEl = document.getElementById('uploadDropFileName');
    const pdfs = collectPdfFiles(files);
    if (!fileInput || !pdfs.length) return;
    const dt = new DataTransfer();
    pdfs.forEach((f) => dt.items.add(f));
    fileInput.files = dt.files;
    if (nameEl) {
      nameEl.textContent = pdfs.length === 1
        ? pdfs[0].name
        : `${pdfs.length} PDF files selected`;
    }
  }

  function setUploadModalFile(file) {
    setUploadModalFiles([file]);
  }

  function bindUploadModalDropZone() {
    const zone = document.getElementById('uploadModalDropZone');
    const fileInput = document.getElementById('uploadFile');
    if (!zone || !fileInput || zone._bound) return;
    zone._bound = true;
    const pickPdfs = (files) => collectPdfFiles(files);
    zone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
      const pdfs = pickPdfs(fileInput.files);
      const nameEl = document.getElementById('uploadDropFileName');
      if (nameEl) {
        nameEl.textContent = !pdfs.length ? '' : pdfs.length === 1
          ? pdfs[0].name
          : `${pdfs.length} PDF files selected`;
      }
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
      const pdfs = pickPdfs(e.dataTransfer?.files);
      if (!pdfs.length) {
        alert('Drop one or more PDF files.');
        return;
      }
      setUploadModalFiles(pdfs);
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
      const fileNote = json.file_count > 1 ? ` · ${json.file_count} files` : '';
      html += `<p class="text-xs text-zinc-400 mb-3">${expected ? `${expected} page(s) in file · ` : ''}${json.created_count || pages.length} sheet(s) imported${json.split ? ' (split from drawing set)' : ''}${fileNote}${splitNote}</p>`;
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
    if (!await drawConfirm(`Delete sheet ${label} and all of its revisions?${setNote}\n\nThis cannot be undone.`, { title: 'Delete sheet', danger: true, confirmLabel: 'Delete' })) return;
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

  function showUploadProgress(fileName, pageCount, batchLabel) {
    const dlg = document.getElementById('uploadProgressModal');
    const title = document.getElementById('uploadProgressTitle');
    const log = document.getElementById('uploadProgressLog');
    const bar = document.getElementById('uploadProgressBar');
    if (!dlg || !log) return;
    const batchPrefix = batchLabel ? `${batchLabel} — ` : '';
    if (title) {
      title.textContent = pageCount
        ? `${batchPrefix}Processing ${pageCount} pages — ${fileName}`
        : `${batchPrefix}Processing ${fileName}`;
    }
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

  function finishUploadProgress(json, finishOpts) {
    const opts = finishOpts || {};
    clearInterval(state.uploadLogTimer);
    state.uploadLogTimer = null;
    const bar = document.getElementById('uploadProgressBar');
    if (bar) bar.style.width = '100%';
    const pages = json.pages || json.drawings || [];
    if (json.warnings?.length) {
      json.warnings.forEach((w) => appendUploadLog(`⚠ ${w}`));
    }
    if (pages.length) {
      if (!opts.quietHeader) appendUploadLog('— Results —');
      pages.forEach(p => {
        const name = p.title || p.drawing_name || '—';
        const flag = p.needs_review ? ' · needs review' : '';
        appendUploadLog(`Page ${p.page || '?'} → ${p.sheet_number} · ${name}${flag}`);
      });
    } else if (!opts.keepOpen) {
      appendUploadLog('Import complete.');
    }
    if (opts.keepOpen) return;
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
    showUploadProgress(file.name, pageCount, opts.batchLabel || '');
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
      if (!opts.skipFinish) {
        finishUploadProgress(json, { keepOpen: !!opts.keepOpen, quietHeader: !!opts.keepOpen });
      }
      return json;
    } catch (e) {
      cancelUploadProgress();
      throw e;
    }
  }

  async function uploadMultiplePdfFiles(files, setName, extra) {
    const pdfs = collectPdfFiles(files);
    if (!pdfs.length) return null;
    const opts = extra || {};
    const combined = {
      ok: true,
      split: false,
      created_count: 0,
      needs_review_count: 0,
      pages: [],
      drawings: [],
      needs_review: [],
      warnings: [],
      file_count: pdfs.length,
    };
    const isBatch = pdfs.length > 1;
    for (let i = 0; i < pdfs.length; i++) {
      const file = pdfs[i];
      const fileSetName = isBatch
        ? `${setName || 'Drawing Upload'} — ${file.name.replace(/\.pdf$/i, '')}`
        : (setName || file.name.replace(/\.pdf$/i, '') || 'Drawing Upload');
      try {
        const json = await uploadPdfFile(file, fileSetName, {
          ...opts,
          batchLabel: isBatch ? `File ${i + 1} of ${pdfs.length}` : '',
          skipFinish: isBatch,
          sheet_number: isBatch ? '' : opts.sheet_number,
          title: isBatch ? '' : opts.title,
        });
        if (!json) continue;
        if (isBatch) {
          appendUploadLog(`✓ ${file.name} — ${json.created_count || json.drawings?.length || 0} sheet(s)`);
        }
        combined.created_count += json.created_count || json.drawings?.length || 0;
        combined.needs_review_count += json.needs_review_count || 0;
        combined.pages.push(...(json.pages || json.drawings || []));
        combined.drawings.push(...(json.drawings || []));
        combined.needs_review.push(...(json.needs_review || []));
        combined.warnings.push(...(json.warnings || []));
        combined.split = combined.split || !!json.split;
        if (json.split_engine) combined.split_engine = json.split_engine;
      } catch (err) {
        combined.warnings.push(`${file.name}: ${err.message || 'Upload failed'}`);
      }
    }
    if (!combined.created_count && !combined.needs_review.length) {
      throw new Error(combined.warnings[0] || 'No PDF files could be imported.');
    }
    finishUploadProgress(combined);
    return combined;
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
      const pdfs = collectPdfFiles(e.dataTransfer?.files);
      if (!pdfs.length) {
        alert('Drop one or more PDF drawing files to import sheets.');
        return;
      }
      try {
        document.getElementById('uploadDrawingModal')?.close();
        const json = await uploadMultiplePdfFiles(pdfs, 'Dropped Drawings');
        const count = json.created_count || json.drawings?.length || 0;
        const fileNote = json.file_count > 1 ? ` from ${json.file_count} files` : '';
        const reviewNote = json.needs_review_count ? ` (${json.needs_review_count} need sheet numbers)` : '';
        toast(`Imported ${count} sheet(s)${fileNote}${reviewNote}`);
        showUploadResults(json);
        await Promise.all([loadDashboard(), loadDrawings(), loadDrawingSets()]);
      } catch (err) {
        alert(err.message);
      }
    });
  }

  async function submitUpload(e) {
    e.preventDefault();
    const pdfs = collectPdfFiles(document.getElementById('uploadFile').files);
    if (!pdfs.length) { alert('Select one or more PDF files'); return; }
    const submitBtn = e.target.querySelector('button[type="submit"]');
    const origLabel = submitBtn?.textContent;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Processing…';
    }
    try {
      document.getElementById('uploadDrawingModal').close();
      const setName = document.getElementById('uploadSetName').value || 'Drawing Upload';
      const json = await uploadMultiplePdfFiles(pdfs, setName, {
        sheet_number: document.getElementById('uploadSheetNumber')?.value || '',
        title: document.getElementById('uploadTitle')?.value || '',
      });
      const count = json.created_count || json.drawings?.length || 0;
      const fileNote = json.file_count > 1 ? ` from ${json.file_count} files` : '';
      const reviewNote = json.needs_review_count ? ` (${json.needs_review_count} need sheet numbers)` : '';
      toast(`Imported ${count} sheet(s)${fileNote}${reviewNote}`);
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
    await Promise.all([loadDashboard(), loadDrawings(), loadRfis(), loadPunchItems(), loadChangeOrders(), loadDrawingSets()]);
    bindTextDialog();
    bindSearchPanel();
    bindDocSnipDialog();
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
    toggleSheetEditMode,
    saveSheetEdits,
    discardSheetEdits,
    onSheetCellInput,
    toggleSearchPanel,
    setSearchMode,
    setSearchScope,
    runTextSearch,
    startShapeSnip,
    startDocSnip,
    saveDocSnipToDocuments,
    runShapeSearch,
    jumpToSearchResult,
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
