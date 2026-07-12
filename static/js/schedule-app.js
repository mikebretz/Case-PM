/* Case PM — Primavera / MS Project style scheduling application */
(function () {
    'use strict';

    const STORAGE_KEY = 'casepm_schedule_v5';
    const LINK_TYPES = { FS: '0', SS: '1', FF: '2', SF: '3' };
    const LINK_LABELS = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' };

    const EXTENDED_FIELDS = [
        'activity_id', 'resource', 'owner', 'work_hours', 'cost', 'actual_cost', 'fixed_cost',
        'actual_start', 'actual_finish', 'remaining_duration', 'constraint_type', 'constraint_date',
        'deadline', 'priority', 'calendar', 'activity_code', 'activity_type', 'phase', 'discipline',
        'bar_color', 'notes', 'hyperlink', 'free_float', 'total_float',
        'early_start', 'early_finish', 'late_start', 'late_finish',
        'percent_complete_type', 'schedule_percent_complete',
        'bcws', 'bcwp', 'acwp', 'cpi', 'spi', 'cost_variance', 'schedule_variance',
        'baseline_start', 'baseline_finish', 'start_variance', 'finish_variance',
        'row_height', 'bar_height', 'bar_border_width', 'bar_border_color', 'bar_border_style'
    ];

    const UNDO_MAX = 40;
    let undoStack = [];
    let redoStack = [];
    let undoPaused = false;
    let dataDateMarkerId = null;

    let ganttReady = false;
    let saveTimer = null;
    let resizeTimer = null;
    let baselines = [];
    let customColumns = [];
    let hiddenColumns = [];
    let columnWidths = {};
    let wbsCodeMap = new Map();
    let scheduleSettings = {
        data_date: typeof CasePMSchedule !== 'undefined' ? CasePMSchedule.formatDate(new Date()) : '',
        calendar: 'standard',
        lookahead_days: 14,
        timescale: 'day',
        default_bar_color: '#3b82f6',
        critical_bar_color: '#ef4444',
        progress_bar_color: '#f59e0b',
        complete_bar_color: '#71717a',
        milestone_color: '#8b5cf6',
        link_color: '#94a3b8',
        link_width: 2,
        active_baseline_index: -1,
        show_baseline_bars: true,
        show_bar_labels: true,
        theme: 'dark',
        default_cell_align: { h: 'left', v: 'middle' },
        column_align: {},
        default_cell_style: { font_size: 13 },
        default_row_height: 32,
        default_bar_height: 22,
        summary_row_height: 48,
        summary_bar_height: 26
    };
    if (!scheduleSettings.print_settings) {
        scheduleSettings.print_settings = {
            include_summary: true,
            include_activity_table: true,
            include_inline_bars: true,
            include_schedule_chart: false,
            include_evm: false,
            include_footer: true,
            print_hide_wbs: false,
            print_hide_id: false,
            header_footer: null
        };
    }
    if (!scheduleSettings.compare_baseline_indices) scheduleSettings.compare_baseline_indices = [];

    const REQUIRED_COLUMNS = ['text', 'collapse'];
    const ROLLING_YEARS_BACK = 2;
    const ROLLING_YEARS_FORWARD = 6;
    const ROLLING_MIN_SPAN_DAYS = 365 * 3;

    let editingContext = null;
    let editorClampTimer = null;
    let floatingEditorActive = false;
    let rollingCalendarBounds = null;
    let initialTimelineFocused = false;
    let timelineScrollProgrammatic = false;
    let lastTimelineScrollX = 0;
    let timelineExtendTimer = null;
    let filterCriticalOnly = false;
    let clipboardTaskId = null;
    const columnEditors = new Map();

    function pushUndoState() {
        if (!ganttReady || undoPaused) return;
        const snap = JSON.stringify(serializeSchedule());
        if (undoStack.length && undoStack[undoStack.length - 1] === snap) return;
        undoStack.push(snap);
        if (undoStack.length > UNDO_MAX) undoStack.shift();
        redoStack = [];
        updateUndoButtons();
    }

    function restoreUndoState(json) {
        undoPaused = true;
        try {
            loadSchedulePayload(JSON.parse(json));
        } finally {
            undoPaused = false;
        }
        gantt.render();
        applyChartOverlay();
        updateStatusBar();
        updateUndoButtons();
        queueSave();
    }

    function undo() {
        if (undoStack.length < 2) return showScheduleAlert('Nothing to undo.', 'info');
        const current = undoStack.pop();
        redoStack.push(current);
        restoreUndoState(undoStack[undoStack.length - 1]);
        logActivity('Undo', 'Restored previous schedule state');
    }

    function redo() {
        if (!redoStack.length) return showScheduleAlert('Nothing to redo.', 'info');
        const snap = redoStack.pop();
        undoStack.push(snap);
        restoreUndoState(snap);
        logActivity('Redo', 'Restored next schedule state');
    }

    function updateUndoButtons() {
        const canUndo = undoStack.length > 1;
        const canRedo = redoStack.length > 0;
        document.getElementById('scheduleUndoBtn')?.toggleAttribute('disabled', !canUndo);
        document.getElementById('scheduleRedoBtn')?.toggleAttribute('disabled', !canRedo);
    }

    function baselineTaskMap(baseline) {
        const map = new Map();
        (baseline?.data || []).forEach(t => map.set(String(t.id), t));
        return map;
    }

    function applyBaselineVariance() {
        if (!ganttReady) return;
        const clearFields = t => {
            if (!t) return;
            t.baseline_start = null;
            t.baseline_finish = null;
            t.start_variance = null;
            t.finish_variance = null;
        };
        const idx = scheduleSettings.active_baseline_index;
        if (idx == null || idx < 0 || !baselines[idx]) {
            gantt.eachTask(clearFields);
            return;
        }
        const bMap = baselineTaskMap(baselines[idx]);
        gantt.eachTask(t => {
            if (!t || t.type === 'project') return;
            const b = bMap.get(String(t.id));
            if (!b) {
                clearFields(t);
                return;
            }
            t.baseline_start = b.start_date || null;
            t.baseline_finish = b.end_date || null;
            const curStart = toGanttDate(t.start_date);
            const curEnd = toGanttDate(t.end_date);
            const bStart = CasePMSchedule.parseDate(b.start_date);
            const bEnd = CasePMSchedule.parseDate(b.end_date);
            t.start_variance = (curStart && bStart) ? CasePMSchedule.calendarDaysBetween(bStart, curStart) : null;
            t.finish_variance = (curEnd && bEnd) ? CasePMSchedule.calendarDaysBetween(bEnd, curEnd) : null;
        });
    }

    function updateDataDateMarker() {
        if (!ganttReady || !gantt.addMarker) return;
        const dd = CasePMSchedule.parseDate(document.getElementById('dataDateInput')?.value || scheduleSettings.data_date);
        if (!dd) return;
        if (dataDateMarkerId != null) {
            try { gantt.deleteMarker(dataDateMarkerId); } catch (e) { /* ok */ }
            dataDateMarkerId = null;
        }
        dataDateMarkerId = gantt.addMarker({
            start_date: dd,
            css: 'schedule-data-date-marker',
            text: 'Data Date',
            title: 'Status / data date: ' + CasePMSchedule.formatDate(dd)
        });
    }

    function showBaselineManager() {
        const dlg = document.getElementById('scheduleBaselineModal');
        if (!dlg) return setBaseline();
        const list = document.getElementById('scheduleBaselineList');
        const compare = document.getElementById('scheduleBaselineCompare');
        if (!list) return;
        if (!baselines.length) {
            list.innerHTML = '<p class="text-zinc-500 text-sm p-2">No baselines saved. Click <b>Set Baseline</b> to capture the current schedule.</p>';
            if (compare) compare.innerHTML = '';
        } else {
            list.innerHTML = baselines.map((b, i) => {
                const active = scheduleSettings.active_baseline_index === i;
                const compared = (scheduleSettings.compare_baseline_indices || []).includes(i);
                const count = (b.data || []).length;
                return `<div class="flex items-center justify-between gap-2 px-3 py-2 rounded-md border ${active ? 'border-emerald-600 bg-emerald-950/30' : 'border-zinc-700 bg-zinc-800/80'}">
                    <div class="min-w-0 flex items-center gap-2">
                        <input type="checkbox" class="rounded border-zinc-600 baseline-compare-cb" data-idx="${i}" ${compared ? 'checked' : ''} title="Compare in table">
                        <div>
                            <div class="text-sm font-medium truncate">${b.name}</div>
                            <div class="text-xs text-zinc-500">${count} activities · ${new Date(b.created).toLocaleString()}</div>
                        </div>
                    </div>
                    <div class="flex gap-1 flex-shrink-0">
                        <button type="button" class="schedule-toolbar-btn text-xs px-2 py-1" onclick="ScheduleApp.restoreBaseline(${i})" title="Restore dates from this baseline">Restore</button>
                        <button type="button" class="schedule-toolbar-btn text-xs px-2 py-1" onclick="ScheduleApp.activateBaseline(${i})">${active ? 'Active' : 'Use'}</button>
                        <button type="button" class="schedule-toolbar-btn text-xs px-2 py-1 text-red-400" onclick="ScheduleApp.deleteBaseline(${i})">Delete</button>
                    </div>
                </div>`;
            }).join('');
            list.querySelectorAll('.baseline-compare-cb').forEach(cb => {
                cb.addEventListener('change', () => {
                    const idx = parseInt(cb.dataset.idx, 10);
                    let sel = scheduleSettings.compare_baseline_indices || [];
                    if (cb.checked) {
                        if (!sel.includes(idx)) sel.push(idx);
                    } else sel = sel.filter(i => i !== idx);
                    scheduleSettings.compare_baseline_indices = sel.slice(0, 3);
                    renderBaselineComparison();
                    queueSave();
                });
            });
            renderBaselineComparison();
        }
        dlg.showModal();
    }

    function renderBaselineComparison() {
        const el = document.getElementById('scheduleBaselineCompare');
        if (!el) return;
        const indices = (scheduleSettings.compare_baseline_indices || []).filter(i => baselines[i]);
        if (!indices.length) {
            el.innerHTML = '<p class="text-xs text-zinc-500 mt-3">Check baselines above to compare start/finish variance side-by-side.</p>';
            return;
        }
        let html = '<div class="mt-4 text-xs uppercase text-sky-400 font-semibold mb-2">Multi-baseline comparison</div>';
        html += '<div class="overflow-auto max-h-48 border border-zinc-700 rounded-md"><table class="w-full text-xs"><thead class="bg-zinc-900 sticky top-0"><tr>';
        html += '<th class="text-left px-2 py-1">WBS</th><th class="text-left px-2 py-1">Activity</th>';
        html += '<th class="text-left px-2 py-1">Current</th>';
        indices.forEach(i => { html += `<th class="text-left px-2 py-1">${baselines[i].name}</th>`; });
        html += '</tr></thead><tbody>';
        gantt.eachTask(t => {
            if (t.type === 'project') return;
            const wbs = wbsCode(t);
            html += `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${wbs}</td><td class="px-2 py-1 truncate max-w-[120px]">${t.text || ''}</td>`;
            html += `<td class="px-2 py-1 whitespace-nowrap">${formatDateSafe(t.start_date)} – ${formatDateSafe(t.end_date)}</td>`;
            indices.forEach(i => {
                const bMap = baselineTaskMap(baselines[i]);
                const b = bMap.get(String(t.id));
                const txt = b ? `${formatDateSafe(b.start_date)} – ${formatDateSafe(b.end_date)}` : '—';
                const sv = t.start_variance != null ? ` <span class="text-amber-400">(${t.start_variance}d)</span>` : '';
                html += `<td class="px-2 py-1 whitespace-nowrap">${txt}${i === scheduleSettings.active_baseline_index ? sv : ''}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table></div>';
        el.innerHTML = html;
    }

    function activateBaseline(index) {
        scheduleSettings.active_baseline_index = index;
        applyBaselineVariance();
        gantt.render();
        queueSave();
        showBaselineManager();
        showScheduleAlert(`Baseline "${baselines[index].name}" is now active for variance columns.`, 'success');
    }

    function deleteBaseline(index) {
        if (!baselines[index]) return;
        if (!confirm(`Delete baseline "${baselines[index].name}"?`)) return;
        baselines.splice(index, 1);
        if (scheduleSettings.active_baseline_index === index) scheduleSettings.active_baseline_index = -1;
        else if (scheduleSettings.active_baseline_index > index) scheduleSettings.active_baseline_index--;
        applyBaselineVariance();
        queueSave();
        showBaselineManager();
    }

    function restoreBaseline(index) {
        const b = baselines[index];
        if (!b) return;
        if (!confirm(`Restore all activity dates from "${b.name}"? Current dates will be overwritten.`)) return;
        const bMap = baselineTaskMap(b);
        gantt.eachTask(t => {
            if (t.type === 'project') return;
            const snap = bMap.get(String(t.id));
            if (!snap) return;
            if (snap.start_date) t.start_date = toGanttDate(snap.start_date);
            if (snap.end_date) t.end_date = toGanttDate(snap.end_date);
            if (snap.duration != null) t.duration = snap.duration;
            sanitizeTaskDates(t);
            gantt.updateTask(t.id);
        });
        runSchedule({ skipScroll: true });
        pushUndoState();
        queueSave();
        showBaselineManager();
        showScheduleAlert(`Schedule dates restored from "${b.name}".`, 'success');
        logActivity('Restored baseline', b.name);
    }


    function getProjectMeta() {
        const ctx = document.getElementById('scheduleProjectContext');
        if (ctx && ctx.dataset.projectId) {
            const number = ctx.dataset.projectNumber || '';
            const name = ctx.dataset.projectName || 'Project Schedule';
            return { id: ctx.dataset.projectId, number, name, label: number ? `${number} — ${name}` : name };
        }
        return { id: '', number: '', name: 'Project Schedule', label: 'Project Schedule' };
    }

    function syncScheduleProjectContext() {
        const ctx = document.getElementById('scheduleProjectContext');
        if (ctx?.dataset?.projectId) {
            localStorage.setItem('casepm_current_project_id', ctx.dataset.projectId);
        }
    }

    function buildEmptySchedule(opts) {
        const today = CasePMSchedule.formatDate(new Date());
        const start = (opts && opts.start) ? opts.start : today;
        const end = (opts && opts.end) ? opts.end : start;
        const text = (opts && opts.label) ? opts.label : 'Default Construction Project';
        return {
            data: [{
                id: 1,
                text: text,
                type: 'project',
                open: true,
                start_date: start,
                end_date: end,
                duration: 0,
                progress: 0
            }],
            links: []
        };
    }

    async function fetchProjectScheduleDefaults(projectId) {
        if (!projectId) return null;
        try {
            const res = await fetch(`/api/projects/${projectId}`);
            if (!res.ok) return null;
            const p = await res.json();
            if (!p.start_date || !p.end_date) return null;
            const label = p.number ? `${p.number} — ${p.name}` : (p.name || 'Project Schedule');
            return { start: p.start_date, end: p.end_date, label };
        } catch (e) {
            return null;
        }
    }

    function wbsCode(task) {
        if (!task) return '';
        if (typeof gantt !== 'undefined' && typeof gantt.getWBSCode === 'function') {
            try { return gantt.getWBSCode(task); } catch (e) { /* community edition */ }
        }
        return wbsCodeMap.get(String(task.id)) || String(task.activity_id || task.id);
    }

    function isTaskCritical(task) {
        if (!task) return false;
        if (typeof gantt !== 'undefined' && typeof gantt.isCriticalTask === 'function') {
            try { return gantt.isCriticalTask(task); } catch (e) { /* community edition */ }
        }
        return typeof CasePMSchedule !== 'undefined' && CasePMSchedule.isTaskCritical
            ? CasePMSchedule.isTaskCritical(task)
            : !!(task.$critical || task.critical);
    }

    function refreshWbsCodes() {
        if (!ganttReady) return;
        const tasks = [];
        gantt.eachTask(t => tasks.push({ id: t.id, parent: t.parent, $index: gantt.getTaskIndex(t.id) }));
        wbsCodeMap = CasePMSchedule.buildWbsMap(tasks);
    }

    let columnOrder = [];
    let overlayApplyTimer = null;

    function getColumnsTotalWidth() {
        if (!gantt.config.columns) return 900;
        return gantt.config.columns.reduce((sum, col) => sum + (parseInt(col.width, 10) || 0), 0);
    }

    function normalizeHexColor(value) {
        if (!value) return '';
        let hex = String(value).trim();
        if (!hex) return '';
        if (!hex.startsWith('#')) hex = '#' + hex;
        if (/^#[0-9a-fA-F]{3}$/.test(hex)) {
            hex = '#' + hex[1] + hex[1] + hex[2] + hex[2] + hex[3] + hex[3];
        }
        return /^#[0-9a-fA-F]{6}$/.test(hex) ? hex.toLowerCase() : '';
    }

    function applyTaskBarColor(task) {
        if (!task || task.type === 'project') return;
        if (task.bar_color) task.bar_color = normalizeHexColor(task.bar_color) || task.bar_color;
        task.color = resolveBarColor(task);
    }

    function orderColumns(cols) {
        const order = columnOrder.length ? columnOrder : (scheduleSettings.column_order || []);
        if (!order.length) return cols;
        const map = new Map(cols.map(c => [c.name, c]));
        const ordered = [];
        order.forEach(name => {
            if (map.has(name)) {
                ordered.push(map.get(name));
                map.delete(name);
            }
        });
        map.forEach(c => ordered.push(c));
        return ordered;
    }

    function getTimelineWidth() {
        return getTimelineDomWidth();
    }

    function getTimelineDomWidth() {
        const hostW = document.getElementById('gantt_here')?.offsetWidth
            || document.getElementById('scheduleGanttHost')?.clientWidth
            || 1200;
        if (scheduleSettings.timeline_width_px >= 180) {
            return Math.max(200, Math.min(hostW - 120, scheduleSettings.timeline_width_px));
        }
        const pct = scheduleSettings.timeline_pct ?? 0.75;
        return Math.max(240, Math.min(hostW - 120, Math.round(hostW * pct)));
    }

    function syncLayoutTimelineWidth() {
        const w = scheduleSettings.timeline_width_px >= 180
            ? scheduleSettings.timeline_width_px
            : Math.max(240, Math.round((document.getElementById('gantt_here')?.offsetWidth || 1000) * (scheduleSettings.timeline_pct ?? 0.75)));
        if (gantt.config.layout?.cols?.[2]) gantt.config.layout.cols[2].width = w;
    }

    function syncGridTableWidth() {
        if (!ganttReady || !gantt.config.columns) return;
        const total = getColumnsTotalWidth();
        gantt.config.grid_width = total;
        const host = document.getElementById('gantt_here');
        if (host) host.style.setProperty('--sched-grid-min-width', total + 'px');
    }

    let headerSyncTimer = null;
    let lastHeaderWidthsKey = '';

    function columnWidthsKey() {
        return (gantt.config.columns || []).map(c => `${c.name}:${parseInt(c.width, 10) || 80}`).join('|');
    }

    function applyColumnWidthToCell(cell, w) {
        if (!cell) return;
        cell.style.setProperty('width', w + 'px', 'important');
        cell.style.setProperty('min-width', w + 'px', 'important');
    }

    function applySingleColumnWidth(colIndex, width) {
        if (!ganttReady || !gantt.config.columns) return;
        const w = parseInt(width, 10) || 80;
        const headCells = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
        applyColumnWidthToCell(headCells[colIndex], w);
        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(row => {
            const cells = row.querySelectorAll(':scope > .gantt_cell');
            applyColumnWidthToCell(cells[colIndex], w);
        });
    }

    function syncColumnResizeHandlePositions() {
        if (!ganttReady || !gantt.config.columns) return;
        const scale = document.querySelector('#gantt_here .gantt_grid_scale');
        if (!scale) return;
        scale.style.position = 'relative';
        const scaleRect = scale.getBoundingClientRect();
        const headCells = scale.querySelectorAll('.gantt_grid_head_cell');
        const wraps = scale.querySelectorAll('.gantt_grid_column_resize_wrap');
        wraps.forEach((wrap, i) => {
            const cell = headCells[i];
            if (!cell) return;
            const cellRect = cell.getBoundingClientRect();
            const left = cellRect.right - scaleRect.left - 2;
            wrap.style.position = 'absolute';
            wrap.style.left = Math.max(0, Math.round(left)) + 'px';
            wrap.style.top = '0';
            wrap.style.height = '100%';
            wrap.style.marginLeft = '0';
        });
    }

    function syncColumnWidthsToConfig() {
        if (!ganttReady || !gantt.config.columns) return;
        gantt.config.columns.forEach((col, index) => {
            const saved = columnWidths[col.name];
            if (saved) {
                col.width = saved;
                gantt.config.columns[index].width = saved;
            }
        });
    }

    function applyGridColumnWidthStyles() {
        if (!ganttReady || !gantt.config.columns) return;
        syncColumnWidthsToConfig();
        const key = columnWidthsKey();
        if (key === lastHeaderWidthsKey) {
            syncColumnResizeHandlePositions();
            return;
        }
        lastHeaderWidthsKey = key;

        const cols = gantt.config.columns;
        const styleEl = document.getElementById('sched-grid-col-widths');
        if (styleEl) styleEl.textContent = '';

        document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell').forEach((cell, i) => {
            if (i < cols.length) applyColumnWidthToCell(cell, parseInt(cols[i].width, 10) || 80);
        });
        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(row => {
            row.querySelectorAll(':scope > .gantt_cell').forEach((cell, i) => {
                if (i < cols.length) applyColumnWidthToCell(cell, parseInt(cols[i].width, 10) || 80);
            });
        });
        syncColumnResizeHandlePositions();
    }

    function queueColumnResizeHandleSync() {
        requestAnimationFrame(() => {
            syncColumnResizeHandlePositions();
        });
    }

    function syncGridHeaderAlignment() {
        applyGridColumnWidthStyles();
    }

    function queueGridHeaderSync() {
        clearTimeout(headerSyncTimer);
        headerSyncTimer = setTimeout(applyGridColumnWidthStyles, 32);
    }

    function ensureTimelineOverlayWidgets(timelineCell) {
        let pan = timelineCell.querySelector(':scope > .schedule-timeline-pan');
        if (!pan) {
            pan = document.createElement('div');
            pan.className = 'schedule-timeline-pan';
            pan.id = 'scheduleTimelinePan';
            pan.setAttribute('aria-label', 'Calendar horizontal scroll');
            pan.innerHTML = '<span class="schedule-timeline-pan-label">Calendar</span><input type="range" id="scheduleTimelineRange" class="schedule-timeline-range" min="0" max="1000" value="0" step="1" aria-label="Pan calendar left and right">';
            timelineCell.appendChild(pan);
            if (window.ScheduleExtras?.rebindPanSlider) ScheduleExtras.rebindPanSlider();
        }
        pan.classList.remove('hidden');
        timelineCell.querySelector(':scope > .schedule-chart-resizer')?.remove();
    }

    function setTimelineWidthFromPct(pct, persist) {
        const hostW = document.getElementById('gantt_here')?.offsetWidth || document.getElementById('scheduleGanttHost')?.clientWidth;
        const clamped = Math.max(0.3, Math.min(0.88, pct));
        scheduleSettings.timeline_pct = clamped;
        if (hostW) scheduleSettings.timeline_width_px = Math.round(hostW * clamped);
        applyChartOverlay();
        if (persist) queueSave();
    }

    function positionChartResizerVisual() {
        const handle = document.getElementById('scheduleChartResizer');
        const host = document.getElementById('scheduleGanttHost');
        if (!handle || !host) return;
        const timelineW = getTimelineWidth();
        handle.classList.remove('hidden');
        handle.style.left = Math.max(0, host.clientWidth - timelineW - 7) + 'px';
        handle.style.right = 'auto';
    }

    function applyChartOverlay() {
        if (!ganttReady) return;
        const root = document.querySelector('#gantt_here .gantt_layout_root');
        if (!root) return;

        const timelineW = getTimelineWidth();
        const cells = root.querySelectorAll(':scope > .gantt_layout_cell');
        const gridCell = cells[0];
        const nativeResizer = cells[1];
        const timelineCell = cells[2];
        if (!gridCell || !timelineCell) return;

        const total = getColumnsTotalWidth();
        const host = document.getElementById('gantt_here');
        const hostW = host?.clientWidth || root.clientWidth || 1200;
        const leftPx = Math.max(0, hostW - timelineW);
        if (host) {
            host.style.setProperty('--sched-grid-min-width', total + 'px');
            host.style.setProperty('--sched-timeline-width', timelineW + 'px');
        }

        root.style.position = 'relative';
        gridCell.style.cssText = 'flex:1 1 auto;width:100%!important;min-width:0!important;position:relative;z-index:2;overflow:hidden;';
        if (nativeResizer) nativeResizer.style.cssText = 'display:none!important;width:0!important;min-width:0!important;';

        timelineCell.style.cssText = [
            'position:absolute!important',
            `left:${leftPx}px!important`,
            'right:auto!important',
            'top:0!important',
            'bottom:0!important',
            `width:${timelineW}px!important`,
            'max-width:' + timelineW + 'px!important',
            'z-index:18!important',
            'display:flex!important',
            'flex-direction:column!important',
            'overflow:hidden!important',
            'background:var(--sched-chart-bg)!important',
            'box-shadow:-10px 0 28px rgba(0,0,0,0.55)!important'
        ].join(';');

        ensureTimelineOverlayWidgets(timelineCell);

        positionChartResizerVisual();
        document.querySelector('#gantt_here .gantt_layout_root > .schedule-chart-resizer')?.remove();

        syncLayoutTimelineWidth();
        ensureTimelineScrollbar();
        refreshTimelinePanBar();
    }

    function queueChartOverlay() {
        clearTimeout(overlayApplyTimer);
        overlayApplyTimer = setTimeout(applyChartOverlay, 16);
    }

    const overlayDrag = { active: false, bound: false, startX: 0, startW: 0 };

    function bindChartResizer() {
        if (overlayDrag.bound) return;
        overlayDrag.bound = true;

        document.addEventListener('mousedown', e => {
            const handle = document.getElementById('scheduleChartResizer');
            if (!handle || (e.target !== handle && !handle.contains(e.target))) return;
            overlayDrag.active = true;
            overlayDrag.startX = e.clientX;
            overlayDrag.startW = scheduleSettings.timeline_width_px >= 180
                ? scheduleSettings.timeline_width_px
                : getTimelineWidth();
            document.body.classList.add('schedule-chart-resizing');
            e.preventDefault();
            e.stopPropagation();
        });

        document.addEventListener('mousemove', e => {
            if (!overlayDrag.active) return;
            const hostEl = document.getElementById('gantt_here');
            if (!hostEl) return;
            const rect = hostEl.getBoundingClientRect();
            const dx = overlayDrag.startX - e.clientX;
            const timelineW = Math.max(220, Math.min(rect.width - 120, overlayDrag.startW + dx));
            scheduleSettings.timeline_width_px = timelineW;
            scheduleSettings.timeline_pct = timelineW / rect.width;
            applyChartOverlay();
        });

        document.addEventListener('mouseup', () => {
            if (!overlayDrag.active) return;
            overlayDrag.active = false;
            document.body.classList.remove('schedule-chart-resizing');
            queueSave();
        });
    }

    function initChartOverlay() {
        if (scheduleSettings.timeline_width_px == null && scheduleSettings.timeline_pct == null) {
            scheduleSettings.timeline_pct = 0.75;
        } else if (scheduleSettings.timeline_pct != null && scheduleSettings.timeline_pct < 0.55) {
            scheduleSettings.timeline_pct = 0.75;
            scheduleSettings.timeline_width_px = null;
        }
        document.getElementById('scheduleGanttHost')?.classList.add('schedule-overlay-mode');
        bindChartResizer();

        if (!initChartOverlay.resizeBound) {
            initChartOverlay.resizeBound = true;
            window.addEventListener('resize', () => {
                const hostW = document.getElementById('gantt_here')?.offsetWidth;
                if (hostW && scheduleSettings.timeline_pct) {
                    scheduleSettings.timeline_width_px = Math.round(hostW * scheduleSettings.timeline_pct);
                }
                queueChartOverlay();
            });
        }

        queueChartOverlay();
    }

    function updateGridWidth() {
        syncGridTableWidth();
        queueChartOverlay();
    }

    function constrainInlineEditor() {
        const ph = document.querySelector('#gantt_here .gantt_grid_editor_placeholder, #gantt_here .gantt_inline_editor');
        if (!ph) return;

        let cell = null;
        let row = null;
        if (editingContext && gantt.isTaskExists(editingContext.taskId)) {
            const colIdx = gantt.config.columns.findIndex(c => c.name === editingContext.colName);
            const rows = document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row');
            rows.forEach(r => {
                if (cell) return;
                let rid = null;
                try { rid = gantt.locate(r); } catch (e) { /* ok */ }
                if (String(rid) === String(editingContext.taskId) && colIdx >= 0) {
                    row = r;
                    const cells = r.querySelectorAll(':scope > .gantt_cell');
                    cell = cells[colIdx];
                }
            });
        }
        if (!cell) cell = ph.closest('.gantt_cell');
        if (!cell) return;
        if (!row) row = cell.closest('.gantt_row');
        const gridData = cell.closest('.gantt_grid_data');
        if (!gridData || !row) return;

        const left = cell.offsetLeft;
        const top = row.offsetTop;
        const w = cell.offsetWidth;
        const h = row.offsetHeight;

        ph.style.cssText = [
            'position:absolute!important',
            `left:${left}px!important`,
            `top:${top}px!important`,
            `width:${w}px!important`,
            `height:${h}px!important`,
            'max-width:' + w + 'px!important',
            'max-height:' + h + 'px!important',
            'min-width:0!important',
            'overflow:hidden!important',
            'box-sizing:border-box!important',
            'z-index:30!important',
            'padding:0!important',
            'margin:0!important'
        ].join(';');

        ph.querySelectorAll('input, select, textarea').forEach(inp => {
            inp.style.cssText = 'width:100%!important;height:100%!important;max-width:100%!important;max-height:100%!important;box-sizing:border-box!important;font-size:13px!important;padding:2px 4px!important;margin:0!important;border-radius:2px!important;';
            if (inp.type === 'date') inp.style.minHeight = '0';
        });
    }

    function scheduleEditorClampLoop() {
        clearTimeout(editorClampTimer);
        constrainInlineEditor();
        let n = 0;
        const tick = () => {
            if (!document.querySelector('#gantt_here .gantt_grid_editor_placeholder')) return;
            constrainInlineEditor();
            if (++n < 12) editorClampTimer = setTimeout(tick, 50);
        };
        editorClampTimer = setTimeout(tick, 50);
    }

    function bindEditorClampObserver() {
        const grid = document.querySelector('#gantt_here .gantt_grid_data');
        if (!grid || grid.dataset.editorClampBound) return;
        grid.dataset.editorClampBound = '1';
        new MutationObserver(() => {
            if (document.querySelector('#gantt_here .gantt_grid_editor_placeholder')) {
                scheduleEditorClampLoop();
            }
        }).observe(grid, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
    }

    function getTimelineScrollState() {
        if (!ganttReady || typeof gantt.getScrollState !== 'function') return null;
        try { return gantt.getScrollState(); } catch (e) { return null; }
    }

    function restoreTimelineScroll(state) {
        if (!state || typeof gantt.scrollTo !== 'function') return;
        requestAnimationFrame(() => {
            try { gantt.scrollTo(state.x, state.y); } catch (e) { /* ok */ }
        });
    }

    function ganttDateAdd(date, amount, unit) {
        const d = toGanttDate(date);
        if (!d) return null;
        if (gantt.date && gantt.date.add) return gantt.date.add(d, amount, unit || 'day');
        return CasePMSchedule.addCalendarDays(d, amount);
    }

    function getDefaultCalendarBounds() {
        const y = new Date().getFullYear();
        return {
            start: new Date(y - ROLLING_YEARS_BACK, 0, 1),
            end: new Date(y + ROLLING_YEARS_FORWARD, 11, 31)
        };
    }

    function computeRollingCalendarBounds() {
        const defaults = getDefaultCalendarBounds();
        let start = new Date(defaults.start.getTime());
        let end = new Date(defaults.end.getTime());
        const floorYear = new Date().getFullYear() - ROLLING_YEARS_BACK;
        if (ganttReady) {
            gantt.eachTask(t => {
                const ts = toGanttDate(t.start_date);
                const te = toGanttDate(t.end_date);
                if (ts && ts.getFullYear() >= floorYear - 1) {
                    const padded = ganttDateAdd(ts, -60, 'day');
                    if (padded && padded < start) start = padded;
                }
                if (te) {
                    const padded = ganttDateAdd(te, 120, 'day');
                    if (padded && padded > end) end = padded;
                }
            });
        }
        if (start < defaults.start) start = new Date(defaults.start.getTime());
        if (CasePMSchedule.calendarDaysBetween(start, end) < ROLLING_MIN_SPAN_DAYS) {
            end = CasePMSchedule.addCalendarDays(start, ROLLING_MIN_SPAN_DAYS);
        }
        return { start, end };
    }

    function applyRollingCalendarRange(forceReset) {
        const bounds = computeRollingCalendarBounds();
        if (forceReset || !rollingCalendarBounds) {
            rollingCalendarBounds = bounds;
        } else {
            rollingCalendarBounds = {
                start: bounds.start < rollingCalendarBounds.start ? bounds.start : rollingCalendarBounds.start,
                end: bounds.end > rollingCalendarBounds.end ? bounds.end : rollingCalendarBounds.end
            };
            const defaults = getDefaultCalendarBounds();
            if (rollingCalendarBounds.start < defaults.start) {
                rollingCalendarBounds.start = new Date(defaults.start.getTime());
            }
        }
        gantt.config.start_date = new Date(rollingCalendarBounds.start.getTime());
        gantt.config.end_date = new Date(rollingCalendarBounds.end.getTime());
    }

    function resetTimelineCalendar() {
        rollingCalendarBounds = null;
        lastTimelineScrollX = 0;
        const defaults = getDefaultCalendarBounds();
        rollingCalendarBounds = {
            start: new Date(defaults.start.getTime()),
            end: new Date(defaults.end.getTime())
        };
        gantt.config.start_date = new Date(rollingCalendarBounds.start.getTime());
        gantt.config.end_date = new Date(rollingCalendarBounds.end.getTime());
        timelineScrollProgrammatic = true;
        gantt.render();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                const today = document.getElementById('dataDateInput')?.value
                    || scheduleSettings.data_date
                    || CasePMSchedule.formatDate(new Date());
                scrollTimelineToDate(today, getTimelineDomWidth() / 2);
                applyChartOverlay();
                updateStatusBar();
                timelineScrollProgrammatic = false;
                showScheduleAlert('Calendar reset to current year. Use the slider at the bottom of the chart or ◀ ▶ to pan.', 'success');
            });
        });
    }

    function getProjectDateBounds() {
        if (rollingCalendarBounds) return rollingCalendarBounds;
        return computeRollingCalendarBounds();
    }

    function updateScaleHeight() {
        const rows = (gantt.config.scales || []).length || 2;
        gantt.config.scale_height = Math.max(88, rows * 44);
    }

    function getTimelinePanMetrics() {
        if (!ganttReady) return null;
        const viewW = getTimelineDomWidth();
        let totalW = 0;
        try {
            if (gantt.config.start_date && gantt.config.end_date && typeof gantt.posFromDate === 'function') {
                totalW = Math.max(1, gantt.posFromDate(gantt.config.end_date) - gantt.posFromDate(gantt.config.start_date));
            }
        } catch (e) { /* ok */ }
        if (!totalW || totalW <= viewW) {
            const state = getTimelineScrollState();
            if (state?.inner_width > viewW) totalW = state.inner_width;
        }
        if (!totalW) totalW = viewW + 1;
        const scrollX = readTimelineScrollX();
        const maxScroll = Math.max(0, totalW - viewW);
        return { totalW, viewW, scrollX, maxScroll };
    }

    function refreshTimelinePanBar() {
        if (window.ScheduleExtras?.updateTimelinePanBar) ScheduleExtras.updateTimelinePanBar();
    }

    function bindTimelineScrollbarSync() {
        const bindEl = el => {
            if (!el || el.dataset.schedScrollBound) return;
            el.dataset.schedScrollBound = '1';
            el.addEventListener('scroll', () => {
                if (timelineScrollProgrammatic) return;
                const x = el.scrollLeft;
                if (x != null && !Number.isNaN(x)) {
                    lastTimelineScrollX = x;
                    refreshTimelinePanBar();
                }
            }, { passive: true });
        };
        getTimelineScrollElements().forEach(bindEl);
    }

    function getTimelineScrollElements() {
        const els = new Set();
        document.querySelectorAll(
            '#gantt_here .gantt_hor_scroll, #gantt_here .gantt_scroll_hor, ' +
            '#gantt_here [data-cell-id="scrollHor"], ' +
            '#gantt_here [data-cell-id="scrollHor"] .gantt_layout_outer_scroll, ' +
            '#gantt_here [data-cell-id="scrollHor"] .gantt_hor_scroll, ' +
            '#gantt_here .gantt_task .gantt_hor_scroll'
        ).forEach(el => els.add(el));
        return [...els];
    }

    function readTimelineScrollX() {
        const taskEl = document.querySelector('#gantt_here .gantt_layout_cell:nth-child(3) .gantt_task');
        if (taskEl) return taskEl.scrollLeft || 0;
        const state = getTimelineScrollState();
        if (state && state.x != null) return state.x;
        return lastTimelineScrollX || 0;
    }

    function getTimelineScrollTargets() {
        const sels = [
            '#gantt_here .gantt_layout_cell:nth-child(3) .gantt_task',
            '#gantt_here .gantt_layout_cell:nth-child(3) .gantt_task_bg',
            '#gantt_here .gantt_layout_cell:nth-child(3) .gantt_data_area'
        ];
        const els = new Set();
        sels.forEach(sel => document.querySelectorAll(sel).forEach(el => els.add(el)));
        getTimelineScrollElements().forEach(el => els.add(el));
        return [...els];
    }

    function syncTimelineScrollViews(x, y) {
        getTimelineScrollTargets().forEach(el => {
            if (Math.abs(el.scrollLeft - x) > 1) el.scrollLeft = x;
        });
        try {
            if (gantt.$ui?.getView) {
                const scrollHor = gantt.$ui.getView('scrollHor');
                if (scrollHor?.scrollTo) scrollHor.scrollTo(x, null);
            }
        } catch (e) { /* ok */ }
        if (y != null) {
            try {
                if (gantt.$ui?.getView) {
                    const scrollVer = gantt.$ui.getView('scrollVer');
                    if (scrollVer?.scrollTo) scrollVer.scrollTo(null, y);
                }
            } catch (e) { /* ok */ }
        }
    }

    function setTimelineScrollX(px) {
        const metrics = getTimelinePanMetrics();
        const maxScroll = metrics?.maxScroll ?? 999999;
        const x = Math.max(0, Math.min(maxScroll, Math.round(px)));
        const y = (typeof gantt.getScrollState === 'function' ? gantt.getScrollState()?.y : 0) || 0;
        lastTimelineScrollX = x;
        timelineScrollProgrammatic = true;
        syncTimelineScrollViews(x, y);
        try {
            if (gantt.scrollTo) gantt.scrollTo(x, y);
        } catch (e) { /* ok */ }
        requestAnimationFrame(() => {
            syncTimelineScrollViews(x, y);
            timelineScrollProgrammatic = false;
            refreshTimelinePanBar();
        });
    }

    function restoreTimelineScrollAfterRender() {
        if (!ganttReady || lastTimelineScrollX <= 0) return;
        const current = readTimelineScrollX();
        if (Math.abs(current - lastTimelineScrollX) < 2) return;
        const metrics = getTimelinePanMetrics();
        if (!metrics || metrics.maxScroll <= 0) return;
        const x = Math.min(lastTimelineScrollX, metrics.maxScroll);
        timelineScrollProgrammatic = true;
        try {
            if (gantt.scrollTo) gantt.scrollTo(x, (gantt.getScrollState()?.y) || 0);
        } catch (e) { /* ok */ }
        syncTimelineScrollViews(x);
        requestAnimationFrame(() => { timelineScrollProgrammatic = false; });
    }

    function maybeExtendTimelineOnScroll() {
        /* Disabled — extending the calendar on scroll was pulling the view backward in time. */
    }

    function panTimelineByDays(days) {
        if (!ganttReady || !days) return;
        const viewW = getTimelineDomWidth();
        const curX = readTimelineScrollX();
        let pivotDate = null;
        try {
            pivotDate = gantt.dateFromPos(curX + viewW / 2);
        } catch (e) { /* ok */ }
        if (!pivotDate) pivotDate = new Date();
        const next = gantt.date?.add
            ? gantt.date.add(pivotDate, days, 'day')
            : ganttDateAdd(pivotDate, days, 'day');
        if (next) scrollTimelineToDate(next, viewW / 2);
    }

    function scrollTimelineToDate(date, marginPx) {
        if (!date) return;
        const d = toGanttDate(date);
        if (!d) return;
        applyRollingCalendarRange(false);
        const viewW = getTimelineDomWidth();
        const margin = marginPx != null ? marginPx : Math.round(viewW / 2);
        const apply = () => {
            let x = null;
            try {
                if (typeof gantt.posFromDate === 'function') x = gantt.posFromDate(d);
            } catch (e) { /* ok */ }
            if (x != null && !Number.isNaN(x)) {
                setTimelineScrollX(Math.max(0, x - margin));
                return;
            }
            if (gantt.showDate) gantt.showDate(d);
            requestAnimationFrame(() => {
                try {
                    x = gantt.posFromDate(d);
                    if (x != null) setTimelineScrollX(Math.max(0, x - margin));
                } catch (e) { /* ok */ }
            });
        };
        requestAnimationFrame(() => requestAnimationFrame(apply));
    }

    function focusTimelineOnTask(id) {
        if (!ganttReady || !id || !gantt.isTaskExists(id)) return;
        const task = gantt.getTask(id);
        if (task.type === 'project') return;
        const start = toGanttDate(task.start_date);
        const end = toGanttDate(task.end_date) || start;
        if (!start) return;
        const viewW = getTimelineDomWidth();
        timelineScrollProgrammatic = true;
        requestAnimationFrame(() => {
            const left = typeof gantt.posFromDate === 'function' ? gantt.posFromDate(start) : null;
            const right = typeof gantt.posFromDate === 'function' ? gantt.posFromDate(end) : left;
            if (left != null) {
                const mid = (left + (right != null ? right : left)) / 2;
                setTimelineScrollX(Math.max(0, mid - viewW / 2));
            } else {
                scrollTimelineToDate(start, viewW / 2);
            }
        });
    }

    function panTimeline(direction, unit) {
        if (!ganttReady) return;
        const state = gantt.getScrollState?.();
        const cur = state?.x ?? readTimelineScrollX();
        if (unit === 'month' && typeof gantt.dateFromPos === 'function' && typeof gantt.posFromDate === 'function') {
            const pivot = gantt.dateFromPos(cur + getTimelineWidth() / 2) || new Date();
            const next = gantt.date.add
                ? gantt.date.add(pivot, direction, 'month')
                : ganttDateAdd(pivot, direction * 30, 'day');
            if (next) scrollTimelineToDate(next, getTimelineWidth() / 2);
            return;
        }
        const step = Math.max(160, Math.round(getTimelineWidth() * 0.45));
        setTimelineScrollX(cur + direction * step);
    }

    function initTimelineEngine() {
        if (initTimelineEngine.bound) return;
        initTimelineEngine.bound = true;

        gantt.attachEvent('onGanttScroll', function (left) {
            if (timelineScrollProgrammatic) return;
            if (left != null) {
                lastTimelineScrollX = left;
                getTimelineScrollElements().forEach(el => {
                    if (Math.abs(el.scrollLeft - left) > 1) el.scrollLeft = left;
                });
                refreshTimelinePanBar();
            }
        });

        const host = document.getElementById('gantt_here');
        if (host) {
            host.addEventListener('wheel', e => {
                const inTimeline = e.target.closest('.gantt_layout_cell:nth-child(3)');
                if (!inTimeline) return;
                const raw = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
                if (!raw) return;
                e.preventDefault();
                e.stopPropagation();
                const days = raw > 0 ? 7 : -7;
                panTimelineByDays(days);
            }, { passive: false, capture: true });
        }
        bindTimelineScrollbarSync();

        const gridData = document.querySelector('#gantt_here .gantt_grid_data');
        if (gridData && !gridData.dataset.resizeSyncBound) {
            gridData.dataset.resizeSyncBound = '1';
            gridData.addEventListener('scroll', () => queueGridHeaderSync(), { passive: true });
        }
    }

    function ensureTimelineScrollbar() {
        bindTimelineScrollbarSync();
        const scrollHor = document.querySelector('#gantt_here [data-cell-id="scrollHor"]');
        if (scrollHor) {
            scrollHor.style.pointerEvents = 'auto';
            scrollHor.style.zIndex = '30';
            const inner = scrollHor.querySelector('.gantt_layout_outer_scroll, .gantt_hor_scroll');
            if (inner) {
                inner.style.overflowX = 'auto';
                inner.style.pointerEvents = 'auto';
            }
        }
    }

    function syncTimelineToTasks(options) {
        if (!ganttReady) return;
        const opts = options || {};
        applyRollingCalendarRange(false);
        updateRowHeightsForLabels();
        gantt.render();
        requestAnimationFrame(() => {
            if (opts.scrollToTasks) scrollToScheduleRange();
            applyChartOverlay();
        });
    }

    function scrollToToday() {
        if (!ganttReady) return;
        const today = document.getElementById('dataDateInput')?.value || CasePMSchedule.formatDate(new Date());
        scrollTimelineToDate(today, getTimelineWidth() / 2);
        applyChartOverlay();
    }

    function fitScheduleView() {
        if (!ganttReady) return;
        const range = gantt.getSubtaskDates();
        if (!range?.start_date || !range?.end_date) return scrollToToday();
        const start = toGanttDate(range.start_date);
        const end = toGanttDate(range.end_date);
        if (!start || !end) return scrollToToday();
        applyRollingCalendarRange(false);
        const mid = gantt.date.add
            ? gantt.date.add(start, Math.round(CasePMSchedule.calendarDaysBetween(start, end) / 2), 'day')
            : ganttDateAdd(start, Math.round(CasePMSchedule.calendarDaysBetween(start, end) / 2), 'day');
        scrollTimelineToDate(mid, getTimelineWidth() / 2);
        applyChartOverlay();
    }

    function applyTimelineDateRange() {
        applyRollingCalendarRange(false);
    }

    function updateRowHeightsForLabels() {
        const showLabels = scheduleSettings.show_bar_labels !== false;
        const baseRow = scheduleSettings.default_row_height || 32;
        const baseBar = scheduleSettings.default_bar_height || 22;
        gantt.config.row_height = showLabels ? baseRow + 8 : baseRow;
        gantt.config.bar_height = baseBar;
        refreshGanttRowMetrics();
    }

    function getTaskRowHeight(task) {
        if (!task) return scheduleSettings.default_row_height || 32;
        const custom = parseInt(task.row_height, 10);
        if (!Number.isNaN(custom) && custom >= 18) return custom;
        if (task.type === 'project' || isParentTask(task)) {
            return scheduleSettings.summary_row_height || 48;
        }
        const showLabels = scheduleSettings.show_bar_labels !== false;
        const base = scheduleSettings.default_row_height || 32;
        return showLabels ? base + 8 : base;
    }

    function getTaskBarHeight(task) {
        if (!task) return scheduleSettings.default_bar_height || 22;
        const custom = parseInt(task.bar_height, 10);
        if (!Number.isNaN(custom) && custom >= 6) return custom;
        if (task.type === 'project' || isParentTask(task)) {
            return scheduleSettings.summary_bar_height || 26;
        }
        return scheduleSettings.default_bar_height || 22;
    }

    function buildTaskBarStyle(task) {
        const color = resolveBarColor(task);
        const barH = getTaskBarHeight(task);
        const parts = [
            `--dhx-gantt-task-background:${color}`,
            `--dhx-gantt-task-border:${color}`,
            `height:${barH}px`,
            `min-height:${barH}px`,
            `line-height:${Math.max(12, barH - 4)}px`,
            `background-color:${color} !important`
        ];
        const bw = parseInt(task.bar_border_width, 10);
        if (!Number.isNaN(bw) && bw > 0) {
            const bc = normalizeHexColor(task.bar_border_color) || task.bar_border_color || '#ffffff';
            parts.push(`border:${bw}px ${task.bar_border_style || 'solid'} ${bc} !important`);
        } else {
            parts.push(`border-color:${color} !important`);
        }
        return parts.join(';') + ';';
    }

    function refreshGanttRowMetrics() {
        if (!ganttReady) return;
        let maxH = scheduleSettings.summary_row_height || 48;
        gantt.eachTask(t => {
            maxH = Math.max(maxH, getTaskRowHeight(t));
        });
        gantt.config.row_height = maxH;
        if (typeof gantt.getTaskHeight === 'function') {
            gantt.getTaskHeight = task => getTaskRowHeight(task);
        }
    }

    function applyRowHeightsToDom() {
        if (!ganttReady) return;
        const applyToRow = row => {
            let taskId = null;
            try { taskId = gantt.locate(row); } catch (e) { /* ok */ }
            if (!taskId || !gantt.isTaskExists(taskId)) return;
            const h = getTaskRowHeight(gantt.getTask(taskId));
            row.style.height = h + 'px';
            row.style.minHeight = h + 'px';
            row.style.maxHeight = h + 'px';
        };
        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(applyToRow);
        document.querySelectorAll('#gantt_here .gantt_task_row').forEach(applyToRow);
    }

    function taskDateInputValue(task, field) {
        const d = toGanttDate(task[field]);
        return d ? CasePMSchedule.formatDate(d) : '';
    }

    function registerSchedCellEditors() {
        if (!gantt.config.editor_types) gantt.config.editor_types = {};

        gantt.config.editor_types.sched_text = {
            show(id, column, config, placeholder) {
                placeholder.innerHTML = '';
                const inp = document.createElement('input');
                inp.type = 'text';
                inp.className = 'sched-cell-editor';
                const field = config.map_to || column.name;
                inp.value = gantt.getTask(id)[field] || '';
                placeholder.appendChild(inp);
                scheduleEditorClampLoop();
                inp.focus();
                inp.select();
            },
            hide() {},
            get_value(id, column, node) {
                return node.querySelector('input')?.value || '';
            },
            set_value(value, id, column, node) {
                const field = column.editor.map_to || column.name;
                gantt.getTask(id)[field] = value;
                gantt.updateTask(id);
            },
            is_changed(value) { return true; },
            is_valid() { return true; },
            save(id, column, node) {
                const field = column.editor.map_to || column.name;
                gantt.getTask(id)[field] = node.querySelector('input')?.value || '';
                gantt.updateTask(id);
                queueSave();
            },
            focus(node) { node.querySelector('input')?.focus(); }
        };

        gantt.config.editor_types.sched_date = {
            show(id, column, config, placeholder) {
                placeholder.innerHTML = '';
                const inp = document.createElement('input');
                inp.type = 'date';
                inp.className = 'sched-cell-editor';
                const field = config.map_to || column.name;
                inp.value = taskDateInputValue(gantt.getTask(id), field);
                placeholder.appendChild(inp);
                scheduleEditorClampLoop();
                inp.focus();
            },
            hide() {},
            get_value(id, column, node) {
                return node.querySelector('input')?.value || '';
            },
            set_value(value, id, column) {
                const field = column.editor.map_to || column.name;
                const task = gantt.getTask(id);
                if (value) task[field] = toGanttDate(value);
                gantt.updateTask(id);
            },
            is_changed(value, id, column, node) {
                const field = column.editor.map_to || column.name;
                return (node.querySelector('input')?.value || '') !== taskDateInputValue(gantt.getTask(id), field);
            },
            is_valid() { return true; },
            save(id, column, node) {
                const field = column.editor.map_to || column.name;
                const val = node.querySelector('input')?.value;
                const task = gantt.getTask(id);
                if (val) task[field] = toGanttDate(val);
                sanitizeTaskDates(task);
                gantt.updateTask(id);
                queueSave();
            },
            focus(node) { node.querySelector('input')?.focus(); }
        };

        gantt.config.editor_types.sched_number = {
            show(id, column, config, placeholder) {
                placeholder.innerHTML = '';
                const inp = document.createElement('input');
                inp.type = 'number';
                inp.className = 'sched-cell-editor';
                const field = config.map_to || column.name;
                const task = gantt.getTask(id);
                let v = task[field];
                if (field === 'progress') v = Math.round(effectiveProgress(task) * 100);
                inp.value = v != null ? v : '';
                if (config.min != null) inp.min = config.min;
                if (config.max != null) inp.max = config.max;
                placeholder.appendChild(inp);
                scheduleEditorClampLoop();
                inp.focus();
                inp.select();
            },
            hide() {},
            get_value(id, column, node) {
                return node.querySelector('input')?.value || '';
            },
            set_value(value, id, column) {
                const field = column.editor.map_to || column.name;
                const task = gantt.getTask(id);
                const n = parseFloat(value);
                task[field] = field === 'progress' ? Math.min(1, Math.max(0, n / 100)) : n;
                gantt.updateTask(id);
            },
            is_changed() { return true; },
            is_valid() { return true; },
            save(id, column, node) {
                const field = column.editor.map_to || column.name;
                const n = parseFloat(node.querySelector('input')?.value);
                const task = gantt.getTask(id);
                if (!Number.isNaN(n)) {
                    task[field] = field === 'progress' ? Math.min(1, Math.max(0, n / 100)) : n;
                }
                gantt.updateTask(id);
                queueSave();
            },
            focus(node) { node.querySelector('input')?.focus(); }
        };
    }

    function normalizeCellAlign(obj) {
        const h = ['left', 'center', 'right'].includes(obj?.h) ? obj.h : 'left';
        const v = ['top', 'middle', 'bottom'].includes(obj?.v) ? obj.v : 'middle';
        const out = { h, v };
        const fs = parseInt(obj?.font_size, 10);
        if (!Number.isNaN(fs) && fs >= 9 && fs <= 24) out.font_size = fs;
        return out;
    }

    function getDefaultCellFontSize() {
        return scheduleSettings.default_cell_style?.font_size || 13;
    }

    function getCellFontSize(task, colName) {
        const cell = task?.cell_align?.[colName];
        const col = scheduleSettings.column_align?.[colName];
        const fs = cell?.font_size || col?.font_size || getDefaultCellFontSize();
        const n = parseInt(fs, 10);
        return (!Number.isNaN(n) && n >= 9 && n <= 24) ? n : 13;
    }

    function getDefaultCellAlign() {
        return normalizeCellAlign(scheduleSettings.default_cell_align || { h: 'left', v: 'middle' });
    }

    function getCellAlign(task, colName) {
        const cell = task?.cell_align?.[colName];
        const col = scheduleSettings.column_align?.[colName];
        const def = getDefaultCellAlign();
        return normalizeCellAlign({
            h: cell?.h || col?.h || def.h,
            v: cell?.v || col?.v || def.v
        });
    }

    function getSelectionAlignPreview() {
        const sel = gridSelection;
        if (sel.type === 'cell' && sel.taskId && gantt.isTaskExists(sel.taskId)) {
            return getCellAlign(gantt.getTask(sel.taskId), sel.colName);
        }
        if (sel.type === 'column' && sel.colName) {
            const col = scheduleSettings.column_align?.[sel.colName];
            const def = getDefaultCellAlign();
            return normalizeCellAlign({ h: col?.h || def.h, v: col?.v || def.v });
        }
        if ((sel.type === 'row' && sel.taskId) || gantt.getSelectedId()) {
            const taskId = sel.taskId || gantt.getSelectedId();
            if (taskId && gantt.isTaskExists(taskId)) {
                const task = gantt.getTask(taskId);
                const firstCol = gantt.config.columns?.[0]?.name;
                if (firstCol) return getCellAlign(task, firstCol);
            }
        }
        return getDefaultCellAlign();
    }

    function applyCellAlignToDom() {
        if (!ganttReady) return;
        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(row => {
            let taskId = null;
            try { taskId = gantt.locate(row); } catch (e) { /* ok */ }
            if (!taskId || !gantt.isTaskExists(taskId)) return;
            const task = gantt.getTask(taskId);
            row.querySelectorAll(':scope > .gantt_cell').forEach((cell, i) => {
                const col = gantt.config.columns[i];
                if (!col) return;
                const a = getCellAlign(task, col.name);
                cell.classList.remove(
                    'sched-align-h-left', 'sched-align-h-center', 'sched-align-h-right',
                    'sched-align-v-top', 'sched-align-v-middle', 'sched-align-v-bottom',
                    'sched-cell-selected'
                );
                cell.classList.add(`sched-align-h-${a.h}`, `sched-align-v-${a.v}`);
                cell.style.fontSize = getCellFontSize(task, col.name) + 'px';
            });
        });
        applyRowHighlight();
        document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell').forEach((head, i) => {
            const col = gantt.config.columns[i];
            head.classList.toggle('sched-col-selected', !!(gridSelection.type === 'column' && col && gridSelection.colName === col.name));
        });
    }

    function getActiveRowTaskId() {
        if (gridSelection.type === 'row' || gridSelection.type === 'cell') return gridSelection.taskId;
        return gantt.getSelectedId();
    }

    function applyRowHighlight() {
        if (!ganttReady) return;
        const activeId = getActiveRowTaskId();
        const match = (row) => {
            let taskId = null;
            try { taskId = gantt.locate(row); } catch (e) { /* ok */ }
            const on = !!(activeId && taskId && String(taskId) === String(activeId));
            row.classList.toggle('sched-row-active', on);
        };
        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(match);
        document.querySelectorAll('#gantt_here .gantt_task_row').forEach(match);
    }

    function highlightGridSelection() {
        applyCellAlignToDom();
        updateAlignToolbarButtons();
    }

    function updateAlignToolbarButtons() {
        const a = getSelectionAlignPreview();
        const hMap = { left: 'schedAlignLeftBtn', center: 'schedAlignCenterHBtn', right: 'schedAlignRightBtn' };
        Object.entries(hMap).forEach(([align, id]) => {
            document.getElementById(id)?.classList.toggle('active-tool', a.h === align);
        });
        const vMap = { top: 'schedAlignTopBtn', middle: 'schedAlignMiddleBtn', bottom: 'schedAlignBottomBtn' };
        Object.entries(vMap).forEach(([align, id]) => {
            document.getElementById(id)?.classList.toggle('active-tool', a.v === align);
        });
    }

    function applyAlignToSelection(axis, value) {
        const sel = gridSelection;
        if (!sel.type) {
            if (!scheduleSettings.default_cell_align) scheduleSettings.default_cell_align = getDefaultCellAlign();
            scheduleSettings.default_cell_align[axis] = value;
        } else if (sel.type === 'column' && sel.colName) {
            if (!scheduleSettings.column_align) scheduleSettings.column_align = {};
            if (!scheduleSettings.column_align[sel.colName]) scheduleSettings.column_align[sel.colName] = {};
            scheduleSettings.column_align[sel.colName][axis] = value;
            gantt.eachTask(t => {
                if (t.cell_align?.[sel.colName]) {
                    delete t.cell_align[sel.colName];
                    if (!Object.keys(t.cell_align).length) delete t.cell_align;
                }
            });
        } else if (sel.type === 'cell' && sel.taskId && gantt.isTaskExists(sel.taskId)) {
            const task = gantt.getTask(sel.taskId);
            if (!task.cell_align) task.cell_align = {};
            if (!task.cell_align[sel.colName]) task.cell_align[sel.colName] = {};
            task.cell_align[sel.colName][axis] = value;
            gantt.updateTask(sel.taskId);
        } else {
            const taskId = (sel.type === 'row' && sel.taskId) ? sel.taskId : gantt.getSelectedId();
            if (!taskId || !gantt.isTaskExists(taskId)) {
                if (!scheduleSettings.default_cell_align) scheduleSettings.default_cell_align = getDefaultCellAlign();
                scheduleSettings.default_cell_align[axis] = value;
            } else {
                const task = gantt.getTask(taskId);
                if (!task.cell_align) task.cell_align = {};
                (gantt.config.columns || []).forEach(col => {
                    if (!task.cell_align[col.name]) task.cell_align[col.name] = {};
                    task.cell_align[col.name][axis] = value;
                });
                gantt.updateTask(taskId);
            }
        }
        highlightGridSelection();
        pushUndoState();
        queueSave();
    }

    function bindGridSelectionHandlers() {
        if (bindGridSelectionHandlers.done) return;
        bindGridSelectionHandlers.done = true;
        const host = document.getElementById('gantt_here');
        if (!host) return;

        host.addEventListener('click', e => {
            const head = e.target.closest('.gantt_grid_head_cell');
            if (head && !e.target.closest('.gantt_grid_column_resize_wrap')) {
                const scale = head.closest('.gantt_grid_scale');
                if (!scale) return;
                const heads = Array.from(scale.querySelectorAll('.gantt_grid_head_cell'));
                const idx = heads.indexOf(head);
                const col = gantt.config.columns[idx];
                if (!col) return;
                gridSelection = { type: 'column', colName: col.name };
                highlightGridSelection();
                e.stopPropagation();
            }
        }, true);
    }

    let gridSelection = { type: null };
    let columnResizeScrollLeft = null;

    function getGridScrollElements() {
        return [
            document.querySelector('#gantt_here .gantt_grid_data'),
            document.querySelector('#gantt_here .gantt_grid_scale'),
            document.querySelector('#gantt_here [data-cell-id="gridScroll"] .gantt_hor_scroll'),
            document.querySelector('#gantt_here [data-cell-id="gridScroll"] .gantt_layout_outer_scroll')
        ].filter(Boolean);
    }

    function preserveGridScrollLeft(left) {
        getGridScrollElements().forEach(el => {
            if (left != null) el.scrollLeft = left;
        });
    }

    function measureColumnContentWidth(colIndex) {
        const col = gantt.config.columns[colIndex];
        if (!col) return 80;
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.font = '600 11px Arial, Helvetica, sans-serif';
        let maxW = ctx.measureText(col.label || col.name || '').width + 22;
        ctx.font = '13px Arial, Helvetica, sans-serif';

        const measureCell = cell => {
            if (!cell) return;
            const text = cell.textContent || '';
            maxW = Math.max(maxW, ctx.measureText(text).width + 18, cell.scrollWidth + 12);
        };

        document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell').forEach((cell, i) => {
            if (i === colIndex) measureCell(cell);
        });
        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(row => {
            const cells = row.querySelectorAll(':scope > .gantt_cell');
            measureCell(cells[colIndex]);
        });

        return Math.min(520, Math.max(col.min_width || 50, Math.ceil(maxW)));
    }

    function autoFitGridColumn(colIndex) {
        if (!ganttReady || !gantt.config.columns[colIndex] || gantt.config.columns[colIndex].resize === false) return;
        const col = gantt.config.columns[colIndex];
        const width = measureColumnContentWidth(colIndex);
        handleColumnResize(colIndex, col, width, true, true);
    }

    function getExposedGridWidth() {
        const host = document.getElementById('gantt_here');
        if (!host) return 600;
        return Math.max(120, host.clientWidth - getTimelineWidth());
    }

    function getExposedGridRightEdge() {
        const host = document.getElementById('gantt_here');
        if (!host) return 0;
        const rect = host.getBoundingClientRect();
        return rect.left + rect.width - getTimelineWidth();
    }

    function getPrintVisibleGridColumns(ps) {
        const opts = ps || scheduleSettings.print_settings || {};
        const cols = gantt.config.columns || [];
        const host = document.getElementById('gantt_here');
        const headCells = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
        if (!host || !headCells.length) {
            return cols
                .filter(c => c.name !== 'collapse')
                .filter(c => !(opts.print_hide_wbs && c.name === 'wbs'))
                .filter(c => !(opts.print_hide_id && c.name === 'activity_id'))
                .map((col, index) => ({ col, index, width: parseInt(col.width, 10) || 80 }));
        }
        const hostRect = host.getBoundingClientRect();
        const gridView = document.querySelector('#gantt_here .gantt_grid_data')
            || document.querySelector('#gantt_here .gantt_grid_scale');
        const viewRect = gridView?.getBoundingClientRect() || hostRect;
        const viewLeft = viewRect.left;
        const exposedRight = getExposedGridRightEdge();
        const visible = [];
        cols.forEach((col, index) => {
            if (col.name === 'collapse') return;
            if (opts.print_hide_wbs && col.name === 'wbs') return;
            if (opts.print_hide_id && col.name === 'activity_id') return;
            const cell = headCells[index];
            if (!cell) return;
            const rect = cell.getBoundingClientRect();
            const width = rect.width;
            if (width < 4) return;
            const fullyVisible = rect.left >= viewLeft - 0.5 && rect.right <= exposedRight + 0.5;
            if (!fullyVisible) return;
            visible.push({ col, index, width });
        });
        if (!visible.length) {
            return cols
                .filter(c => c.name !== 'collapse' && c.name !== 'bar_color')
                .filter(c => !(opts.print_hide_wbs && c.name === 'wbs'))
                .filter(c => !(opts.print_hide_id && c.name === 'activity_id'))
                .slice(0, 8)
                .map((col, index) => ({ col, index, width: parseInt(col.width, 10) || 80 }));
        }
        return visible;
    }

    function renderPrintCellHtml(task, col) {
        try {
            if (col.template && typeof col.template === 'function') {
                const html = col.template(task);
                return html != null ? String(html) : '';
            }
        } catch (e) { /* ok */ }
        if (col.name === 'progress') return String(Math.round(effectiveProgress(task) * 100));
        if (col.name === 'start_date' || col.name === 'end_date') return formatDateSafe(task[col.name]);
        if (col.name === 'predecessors') return predTemplate(task) || '—';
        if (col.name === 'successors') return succTemplate(task) || '—';
        const val = task[col.map_to || col.name];
        if (val == null || val === '') return col.name === 'text' ? '' : '—';
        return String(val);
    }

    const colResizeDrag = { active: false, colIndex: -1, startX: 0, startW: 0 };

    function bindColumnResizeEnhancements() {
        if (bindColumnResizeEnhancements.done) return;
        bindColumnResizeEnhancements.done = true;
        const host = document.getElementById('gantt_here');
        if (!host) return;

        const onColMove = e => {
            if (!colResizeDrag.active || colResizeDrag.colIndex < 0) return;
            const col = gantt.config.columns[colResizeDrag.colIndex];
            if (!col) return;
            const delta = e.clientX - colResizeDrag.startX;
            const newW = Math.max(col.min_width || 50, Math.min(520, colResizeDrag.startW + delta));
            handleColumnResize(colResizeDrag.colIndex, col, newW, false, false);
            preserveGridScrollLeft(columnResizeScrollLeft);
        };

        const endColResize = () => {
            if (!colResizeDrag.active) return;
            const idx = colResizeDrag.colIndex;
            colResizeDrag.active = false;
            if (idx >= 0 && gantt.config.columns[idx]) {
                handleColumnResize(idx, gantt.config.columns[idx], gantt.config.columns[idx].width, true, true);
            }
            colResizeDrag.colIndex = -1;
            columnResizeScrollLeft = null;
        };

        host.addEventListener('mousedown', e => {
            const tick = e.target.closest('.gantt_grid_column_resize, .gantt_grid_column_resize_wrap');
            if (!tick) return;
            const wrap = tick.closest('.gantt_grid_column_resize_wrap') || tick;
            const scale = wrap.closest('.gantt_grid_scale');
            if (!scale) return;
            const boundary = getExposedGridRightEdge();
            if (wrap.getBoundingClientRect().left > boundary - 4) return;
            const wraps = Array.from(scale.querySelectorAll('.gantt_grid_column_resize_wrap'));
            const colIndex = wraps.indexOf(wrap);
            if (colIndex < 0 || !gantt.config.columns[colIndex] || gantt.config.columns[colIndex].resize === false) return;
            const grid = document.querySelector('#gantt_here .gantt_grid_data');
            columnResizeScrollLeft = grid ? grid.scrollLeft : 0;
            colResizeDrag.active = true;
            colResizeDrag.colIndex = colIndex;
            colResizeDrag.startX = e.clientX;
            colResizeDrag.startW = parseInt(gantt.config.columns[colIndex].width, 10) || 80;
            e.preventDefault();
            e.stopPropagation();
        }, true);

        document.addEventListener('mousemove', onColMove);
        document.addEventListener('mouseup', endColResize);

        host.addEventListener('dblclick', e => {
            const wrap = e.target.closest('.gantt_grid_column_resize_wrap');
            if (!wrap) return;
            const boundary = getExposedGridRightEdge();
            if (wrap.getBoundingClientRect().left > boundary - 4) return;
            const scale = wrap.closest('.gantt_grid_scale');
            if (!scale) return;
            const wraps = Array.from(scale.querySelectorAll('.gantt_grid_column_resize_wrap'));
            const colIndex = wraps.indexOf(wrap);
            if (colIndex < 0) return;
            e.preventDefault();
            e.stopPropagation();
            autoFitGridColumn(colIndex);
        }, true);
    }

    function handleColumnResize(index, column, new_width, persist, reflow) {
        if (column && column.name) {
            columnWidths[column.name] = new_width;
            column.width = new_width;
            if (gantt.config.columns[index]) {
                gantt.config.columns[index].width = new_width;
            }
        }
        applySingleColumnWidth(index, new_width);
        queueColumnResizeHandleSync();
        if (reflow) {
            syncGridTableWidth();
            lastHeaderWidthsKey = '';
            applyGridColumnWidthStyles();
            queueChartOverlay();
            if (persist) queueSave();
        }
    }

    function resetColumnWidths() {
        columnWidths = {};
        gantt.config.columns = buildColumnConfig();
        syncGridTableWidth();
        lastHeaderWidthsKey = '';
        applyGridColumnWidthStyles();
        gantt.render();
        queueSave();
        showScheduleAlert('Column widths reset to defaults.', 'success');
    }

    let baselineLayerBound = false;
    let barLabelLayerBound = false;

    function buildBarSublabelText(task) {
        const parts = [];
        const pct = Math.round(effectiveProgress(task) * 100);
        parts.push(pct + '% complete');
        if (task.schedule_percent_complete != null && String(task.percent_complete_type || '').toLowerCase() === 'duration') {
            parts.push('Sched ' + Math.round(Number(task.schedule_percent_complete)) + '%');
        }
        if (task.cpi != null && !Number.isNaN(Number(task.cpi))) parts.push('CPI ' + Number(task.cpi).toFixed(2));
        if (task.spi != null && !Number.isNaN(Number(task.spi))) parts.push('SPI ' + Number(task.spi).toFixed(2));
        if (task.total_float != null) parts.push('TF ' + task.total_float + 'd');
        if (task.cost != null && task.cost !== '') {
            const cost = Number(task.cost);
            if (!Number.isNaN(cost)) parts.push('$' + cost.toLocaleString(undefined, { maximumFractionDigits: 0 }));
        }
        if (task.resource) parts.push(task.resource);
        return parts.join(' · ');
    }

    function initBarLabels() {
        if (barLabelLayerBound || typeof gantt.addTaskLayer !== 'function') return;
        barLabelLayerBound = true;
        gantt.addTaskLayer(function renderBarSublabel(task) {
            if (scheduleSettings.show_bar_labels === false) return null;
            if (task.type === 'project') return null;
            const start = toGanttDate(task.start_date);
            if (!start || typeof gantt.posFromDate !== 'function' || typeof gantt.getTaskTop !== 'function') return null;
            const left = gantt.posFromDate(start);
            const top = gantt.getTaskTop(task.id);
            if (left == null || top == null) return null;
            const label = buildBarSublabelText(task);
            if (!label) return null;
            const barH = getTaskBarHeight(task);
            const el = document.createElement('div');
            el.className = 'gantt_bar_sublabel';
            el.textContent = label;
            el.style.cssText = `position:absolute;left:${left}px;top:${top + barH + 2}px;max-width:420px;pointer-events:none;`;
            el.title = label;
            return el;
        });
    }

    function initBaselineBars() {
        if (baselineLayerBound || typeof gantt.addTaskLayer !== 'function') return;
        baselineLayerBound = true;
        gantt.addTaskLayer(function renderBaselineBar(task) {
            if (task.type === 'project' || scheduleSettings.show_baseline_bars === false) return null;
            if (!task.baseline_start || !task.baseline_finish) return null;
            const bStart = toGanttDate(task.baseline_start);
            const bEnd = toGanttDate(task.baseline_finish);
            if (!bStart || !bEnd || typeof gantt.posFromDate !== 'function' || typeof gantt.getTaskTop !== 'function') return null;
            const left = gantt.posFromDate(bStart);
            const right = gantt.posFromDate(bEnd);
            const top = gantt.getTaskTop(task.id);
            if (left == null || right == null || top == null) return null;
            const barH = getTaskBarHeight(task);
            const el = document.createElement('div');
            el.className = 'gantt_baseline_bar';
            el.style.cssText = `position:absolute;left:${left}px;width:${Math.max(3, right - left)}px;top:${top + barH - 5}px;height:4px;pointer-events:none;`;
            el.title = `Baseline: ${formatDateSafe(bStart)} – ${formatDateSafe(bEnd)}`;
            return el;
        });
    }

    function isLoeTask(task) {
        const t = String(task?.activity_type || '').toLowerCase();
        return t === 'loe' || t === 'level of effort';
    }

    function effectiveProgress(task) {
        if (!task) return 0;
        const type = String(task.percent_complete_type || 'physical').toLowerCase();
        if (type === 'duration' && task.schedule_percent_complete != null) {
            return Math.min(1, Number(task.schedule_percent_complete) / 100);
        }
        const p = Number(task.progress) || 0;
        return p <= 1 ? p : p / 100;
    }

    function toGanttDate(value) {
        if (!value) return null;
        if (value instanceof Date && !Number.isNaN(value.getTime())) return new Date(value.getTime());
        if (typeof value === 'string') {
            const parsed = CasePMSchedule.parseDate(value);
            if (parsed) return parsed;
            if (typeof gantt !== 'undefined' && gantt.date && gantt.date.parseDate) {
                const g = gantt.date.parseDate(value, gantt.config.date_format);
                if (g && !Number.isNaN(g.getTime())) return g;
            }
            if (typeof gantt !== 'undefined' && gantt.date && gantt.date.str_to_date) {
                const g = gantt.date.str_to_date(value);
                if (g && !Number.isNaN(g.getTime())) return g;
            }
        }
        return null;
    }

    function formatDateSafe(value) {
        const d = toGanttDate(value);
        if (!d) return '—';
        try {
            return gantt.templates.format_date(d);
        } catch (e) {
            return CasePMSchedule.formatDate(d);
        }
    }

    function coerceTaskDate(value) {
        return toGanttDate(value);
    }

    function normalizeTaskDates(data) {
        const today = CasePMSchedule.formatDate(new Date());
        (data || []).forEach(task => {
            let start = toGanttDate(task.start_date) || toGanttDate(today);
            task.start_date = CasePMSchedule.formatDate(start);
            const dur = Math.max(0, Number(task.duration) || 0);
            if (task.type === 'milestone') {
                task.duration = 0;
                task.end_date = task.start_date;
            } else if (task.type === 'project') {
                task.duration = dur || 0;
                const end = toGanttDate(task.end_date);
                task.end_date = end ? CasePMSchedule.formatDate(end) : task.start_date;
            } else if (!toGanttDate(task.end_date)) {
                task.end_date = CasePMSchedule.formatDate(CasePMSchedule.addCalendarDays(start, dur || 1));
            } else {
                task.end_date = CasePMSchedule.formatDate(toGanttDate(task.end_date));
            }
            if (task.duration == null || Number.isNaN(Number(task.duration))) {
                task.duration = task.type === 'project' ? 0 : (dur || 1);
            }
            if (task.constraint_date) {
                const cd = toGanttDate(task.constraint_date);
                if (cd) task.constraint_date = CasePMSchedule.formatDate(cd);
            }
        });
    }

    function sanitizeTaskDates(task) {
        if (!task) return;
        const start = toGanttDate(task.start_date);
        if (start) task.start_date = start;
        else if (task.type !== 'project') task.start_date = new Date();

        const dur = Math.max(0, Number(task.duration) || 0);
        if (task.type === 'milestone') {
            task.duration = 0;
            task.end_date = new Date(task.start_date.getTime());
            return;
        }
        if (task.type === 'project') {
            const end = toGanttDate(task.end_date);
            task.end_date = end || new Date(task.start_date.getTime());
            return;
        }
        let end = toGanttDate(task.end_date);
        if (!end) end = CasePMSchedule.addCalendarDays(task.start_date, dur || 1);
        task.end_date = end;
        if (!dur) {
            task.duration = Math.max(1, CasePMSchedule.calendarDaysBetween(task.start_date, task.end_date));
        }
    }

    function sanitizeAllTaskDates() {
        if (!ganttReady) return;
        gantt.eachTask(t => sanitizeTaskDates(t));
    }

    function predTemplate(task) {
        const links = task.$target || [];
        return links.map(lid => {
            const link = gantt.getLink(lid);
            const src = gantt.getTask(link.source);
            const code = wbsCode(src);
            const lag = link.lag ? (link.lag > 0 ? `+${link.lag}` : link.lag) : '';
            return `${code}${LINK_LABELS[link.type] || 'FS'}${lag}`;
        }).join(', ');
    }

    function colWidth(name, fallback) {
        return columnWidths[name] || fallback;
    }

    function succTemplate(task) {
        const links = task.$source || [];
        return links.map(lid => {
            const link = gantt.getLink(lid);
            const tgt = gantt.getTask(link.target);
            const code = wbsCode(tgt);
            const lag = link.lag ? (link.lag > 0 ? `+${link.lag}` : link.lag) : '';
            return `${code}${LINK_LABELS[link.type] || 'FS'}${lag}`;
        }).join(', ');
    }

    function isParentTask(task) {
        if (!task) return false;
        if (task.type === 'project') return true;
        return ganttReady && gantt.hasChild(task.id);
    }

    function activityNameTemplate(task) {
        const pad = (task.$level || 0) * 14;
        const parent = isParentTask(task);
        const cls = parent ? 'sched-parent-name' : '';
        const weight = parent ? 'font-weight:700;' : '';
        return `<span class="${cls}" style="padding-left:${pad}px;display:inline-block;${weight}">${task.text || ''}</span>`;
    }

    function collapseTemplate(task) {
        if (!ganttReady || !gantt.hasChild(task.id)) return '';
        const open = task.$open !== false;
        return `<span class="sched-tree-btn" title="${open ? 'Collapse' : 'Expand'}">${open ? '▾' : '▸'}</span>`;
    }

    function primaryLinkLag(task) {
        if (!ganttReady || !task.$target?.length) return '';
        const link = gantt.getLink(task.$target[0]);
        if (!link || link.lag == null || link.lag === 0) return '';
        return link.lag > 0 ? `+${link.lag}` : String(link.lag);
    }

    function constraintLabel(type) {
        const map = {
            asap: '', alap: 'ALAP', mso: 'MSO', mfo: 'MFO',
            snet: 'SNET', snlt: 'SNLT', fnet: 'FNET', fnlt: 'FNLT'
        };
        return map[String(type || 'asap').toLowerCase()] || String(type || '').toUpperCase();
    }

    function constraintTemplate(task) {
        if (!task || task.type === 'project') return '';
        const code = constraintLabel(task.constraint_type);
        if (!code) return '';
        const date = task.constraint_date ? formatDateSafe(task.constraint_date) : '';
        return `<span class="sched-constraint-badge" title="Constraint: ${code}${date ? ' ' + date : ''}">${code}</span>`;
    }

    function resolveBarColor(task) {
        if (!task || task.type === 'project') return '#64748b';
        const custom = normalizeHexColor(task.bar_color);
        if (custom) return custom;
        if (isTaskCritical(task)) return normalizeHexColor(scheduleSettings.critical_bar_color) || '#ef4444';
        if (Math.round(effectiveProgress(task) * 100) >= 100) return normalizeHexColor(scheduleSettings.complete_bar_color) || '#71717a';
        if (effectiveProgress(task) > 0) return normalizeHexColor(scheduleSettings.progress_bar_color) || '#f59e0b';
        if (task.type === 'milestone') return normalizeHexColor(scheduleSettings.milestone_color) || '#8b5cf6';
        return normalizeHexColor(scheduleSettings.default_bar_color) || '#3b82f6';
    }

    function applyPredecessorString(taskId, predStr, options) {
        if (!gantt.isTaskExists(taskId)) return false;
        const opts = options || {};
        const existing = [...(gantt.getTask(taskId).$target || [])];
        existing.forEach(lid => gantt.deleteLink(lid));
        const failed = [];
        let added = 0;
        if (predStr && predStr.trim()) {
            refreshWbsCodes();
            const lookup = { byWbs: new Map(), byActId: new Map(), byId: new Map() };
            gantt.eachTask(t => {
                if (String(t.id) === String(taskId)) return;
                lookup.byId.set(String(t.id), t.id);
                const wbs = String(wbsCode(t) || '').trim();
                if (wbs) lookup.byWbs.set(wbs, t.id);
                const actId = String(t.activity_id || '').trim();
                if (actId) lookup.byActId.set(actId, t.id);
            });
            const types = { FS: '0', SS: '1', FF: '2', SF: '3' };
            const parts = predStr.split(/[,;]+/).map(s => s.trim()).filter(Boolean);
            parts.forEach(part => {
                const parsed = parsePredecessorToken(part);
                if (!parsed) { failed.push(part); return; }
                const { code, type, lag } = parsed;
                let sourceId = lookup.byWbs.get(code) || lookup.byId.get(code) || lookup.byActId.get(code);
                if (!sourceId) {
                    const lc = code.toLowerCase();
                    lookup.byWbs.forEach((id, k) => { if (!sourceId && k.toLowerCase() === lc) sourceId = id; });
                    lookup.byActId.forEach((id, k) => { if (!sourceId && k.toLowerCase() === lc) sourceId = id; });
                }
                if (sourceId && String(sourceId) !== String(taskId)) {
                    gantt.addLink({ source: sourceId, target: taskId, type, lag });
                    added++;
                } else failed.push(part);
            });
        }
        gantt.refreshTask(taskId);
        refreshWbsCodes();
        if (!opts.skipSchedule) runSchedule({ skipScroll: true });
        if (!opts.skipUndo) pushUndoState();
        if (!opts.skipSave) queueSave();
        if (failed.length) showScheduleAlert(`Could not link predecessor(s): ${failed.join(', ')}. Use WBS, Activity ID, or task id (e.g. 1.2FS+2 or A101).`, 'warning');
        return added > 0 || (!predStr?.trim() && !failed.length);
    }

    function parsePredecessorToken(part) {
        const types = { FS: '0', SS: '1', FF: '2', SF: '3' };
        let rest = String(part || '').replace(/\s+/g, '');
        if (!rest) return null;
        let lag = 0;
        const lagM = rest.match(/([+-]\d+)$/);
        if (lagM) {
            lag = parseInt(lagM[1], 10) || 0;
            rest = rest.slice(0, -lagM[1].length);
        }
        let type = '0';
        const typeM = rest.match(/(FS|SS|FF|SF)$/i);
        if (typeM) {
            type = types[typeM[1].toUpperCase()] || '0';
            rest = rest.slice(0, -typeM[1].length);
        }
        const code = rest;
        if (!code) return null;
        return { code, type, lag };
    }

    function getBuiltinColumnDefs() {
        return [
            { name: 'collapse', label: '', width: 30, min_width: 30, resize: false, align: 'center', template: collapseTemplate },
            { name: 'wbs', label: 'WBS', width: 58, align: 'center', resize: true, template: t => wbsCode(t) },
            { name: 'activity_id', label: 'ID', width: 64, align: 'center', resize: true, editor: { type: 'sched_text', map_to: 'activity_id' }, template: t => t.activity_id || '' },
            { name: 'text', label: 'Activity Name', tree: false, width: 220, min_width: 120, resize: true, editor: { type: 'sched_text', map_to: 'text' }, template: activityNameTemplate },
            { name: 'duration', label: 'Dur', align: 'center', width: 52, min_width: 44, resize: true, editor: { type: 'sched_number', map_to: 'duration', min: 0, max: 9999 } },
            { name: 'start_date', label: 'Start', align: 'center', width: 98, min_width: 88, resize: true, editor: { type: 'sched_date', map_to: 'start_date' }, template: t => formatDateSafe(t.start_date) },
            { name: 'end_date', label: 'Finish', align: 'center', width: 98, min_width: 88, resize: true, editor: { type: 'sched_date', map_to: 'end_date' }, template: t => formatDateSafe(t.end_date) },
            { name: 'predecessors', label: 'Predecessors', width: 118, min_width: 80, resize: true, editor: { type: 'pred_string', map_to: 'auto' }, template: predTemplate },
            { name: 'link_lag', label: 'Lag', width: 48, align: 'center', resize: true, template: t => primaryLinkLag(t) },
            { name: 'successors', label: 'Successors', width: 108, min_width: 80, resize: true, template: succTemplate },
            { name: 'progress', label: '%', align: 'center', width: 48, min_width: 42, resize: true, editor: { type: 'sched_number', map_to: 'progress', min: 0, max: 100 }, template: t => Math.round(effectiveProgress(t) * 100) },
            { name: 'resource', label: 'Resource', width: 108, min_width: 70, resize: true, editor: { type: 'sched_text', map_to: 'resource' } },
            { name: 'owner', label: 'Responsible', width: 108, min_width: 70, resize: true, editor: { type: 'sched_text', map_to: 'owner' } },
            { name: 'total_float', label: 'Total Float', width: 72, align: 'center', resize: true, template: t => t.$slack != null ? t.$slack : (t.total_float != null ? t.total_float : '') },
            { name: 'constraint_type', label: 'Cstr', width: 52, align: 'center', resize: true, template: constraintTemplate },
            { name: 'bar_color', label: 'Color', width: 58, align: 'center', resize: true, template: t => {
                const c = normalizeHexColor(t.bar_color);
                return c ? `<span class="sched-color-swatch" style="background:${c}"></span>` : '—';
            }, editor: { type: 'color_hex', map_to: 'bar_color' } }
        ];
    }

    function editorForField(field) {
        if (!field || field.type === 'readonly' || field.type === 'successors') return null;
        if (field.type === 'predecessor') return { type: 'pred_string', map_to: 'auto' };
        if (field.type === 'date') return { type: 'sched_date', map_to: field.map_to };
        if (field.type === 'number') return { type: 'sched_number', map_to: field.map_to, min: 0, max: 999999 };
        if (field.type === 'percent') return { type: 'sched_number', map_to: field.map_to, min: 0, max: 100 };
        if (field.type === 'color') return { type: 'color_hex', map_to: field.map_to };
        return { type: 'sched_text', map_to: field.map_to };
    }

    function buildColumnConfig() {
        columnEditors.clear();
        const builtins = getBuiltinColumnDefs()
            .filter(c => !hiddenColumns.includes(c.name))
            .map(c => Object.assign({}, c, { width: colWidth(c.name, c.width) }));

        const cols = builtins.slice();
        customColumns.forEach(cc => {
            const field = (typeof CasePMScheduleFields !== 'undefined') ? CasePMScheduleFields.getField(cc.map_to || cc.name) : null;
            const col = {
                name: cc.map_to || cc.name,
                label: cc.label,
                width: colWidth(cc.map_to || cc.name, cc.width || 90),
                min_width: 50,
                resize: true,
                template: t => {
                    if (field && field.type === 'readonly') return t[field.map_to] != null ? t[field.map_to] : '';
                    return t[cc.map_to || cc.name] || '';
                }
            };
            const ed = field ? editorForField(field) : { type: 'text', map_to: cc.map_to || cc.name };
            if (ed) col.editor = ed;
            cols.push(col);
        });

        return orderColumns(cols).map(c => {
            const copy = Object.assign({}, c);
            if (copy.editor) {
                columnEditors.set(copy.name, copy.editor);
                delete copy.editor;
            }
            return copy;
        });
    }

    function findGridCell(taskId, colName) {
        const colIdx = gantt.config.columns.findIndex(c => c.name === colName);
        if (colIdx < 0) return null;
        for (const r of document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row')) {
            let rid = null;
            try { rid = gantt.locate(r); } catch (e) { /* ok */ }
            if (String(rid) === String(taskId)) {
                const cells = r.querySelectorAll(':scope > .gantt_cell');
                return cells[colIdx] || null;
            }
        }
        return null;
    }

    function closeFloatingEditor() {
        document.querySelectorAll('.sched-floating-cell-editor').forEach(el => el.remove());
        floatingEditorActive = false;
        editingContext = null;
    }

    function saveFloatingEditor(taskId, colName, value) {
        const ed = columnEditors.get(colName);
        if (!ed || !gantt.isTaskExists(taskId)) return;
        const task = gantt.getTask(taskId);
        const field = ed.map_to || colName;
        const type = ed.type || 'sched_text';

        if (type === 'pred_string') {
            applyPredecessorString(taskId, value, { skipSchedule: false, skipUndo: true, skipSave: true });
        } else if (type === 'color_hex') {
            task.bar_color = normalizeHexColor(value) || value;
            applyTaskBarColor(task);
            gantt.updateTask(taskId);
            gantt.refreshTask(taskId);
        } else if (type === 'sched_date' || type === 'date') {
            if (value) task[field] = toGanttDate(value);
            sanitizeTaskDates(task);
            gantt.updateTask(taskId);
        } else if (type === 'sched_number' || type === 'number') {
            const n = parseFloat(value);
            if (!Number.isNaN(n)) {
                task[field] = field === 'progress' ? Math.min(1, Math.max(0, n / 100)) : n;
            }
            gantt.updateTask(taskId);
        } else {
            task[field] = value;
            gantt.updateTask(taskId);
        }
        pushUndoState();
        queueSave();
    }

    function registerCustomEditors() {
        /* dhtmlx grid editors disabled — we use in-cell floating editors instead */
    }

    function locateGridCell(target) {
        if (!target || !target.closest) return null;
        const cell = target.closest('.gantt_cell');
        const row = target.closest('.gantt_row');
        if (!cell || !row) return null;
        let id = typeof gantt.locate === 'function' ? gantt.locate(target) : null;
        if (!id) {
            id = row.getAttribute('data-task-id') || row.getAttribute('task_id');
        }
        if (!id || !gantt.isTaskExists(id)) return null;
        const cells = Array.from(row.querySelectorAll(':scope > .gantt_cell'));
        const idx = cells.indexOf(cell);
        if (idx < 0 || !gantt.config.columns[idx]) return null;
        return { id, column: gantt.config.columns[idx].name };
    }

    function startCellEdit(id, colName) {
        const ed = columnEditors.get(colName);
        if (!ed) return;
        closeFloatingEditor();

        const cell = findGridCell(id, colName);
        if (!cell) return;

        editingContext = { taskId: id, colName };
        floatingEditorActive = true;
        const task = gantt.getTask(id);
        const field = ed.map_to || colName;

        const wrap = document.createElement('div');
        wrap.className = 'sched-floating-cell-editor';

        let input;
        if (ed.type === 'color_hex') {
            input = document.createElement('input');
            input.type = 'color';
            input.value = task.bar_color || scheduleSettings.default_bar_color || '#3b82f6';
        } else if (ed.type === 'sched_date' || ed.type === 'date') {
            input = document.createElement('input');
            input.type = 'date';
            input.value = taskDateInputValue(task, field);
        } else if (ed.type === 'sched_number' || ed.type === 'number') {
            input = document.createElement('input');
            input.type = 'number';
            let v = task[field];
            if (field === 'progress') v = Math.round(effectiveProgress(task) * 100);
            input.value = v != null ? v : '';
            if (ed.min != null) input.min = ed.min;
            if (ed.max != null) input.max = ed.max;
        } else {
            input = document.createElement('input');
            input.type = 'text';
            if (ed.type === 'pred_string') {
                input.value = predTemplate(task);
                input.placeholder = 'e.g. 1.2FS+2';
            } else {
                input.value = task[field] != null ? task[field] : '';
            }
        }
        input.className = 'sched-cell-editor';
        wrap.appendChild(input);
        cell.appendChild(wrap);
        input.focus();
        if (input.select) input.select();

        const commit = () => {
            if (!floatingEditorActive) return;
            saveFloatingEditor(id, colName, input.value);
            closeFloatingEditor();
            syncColumnWidthsToConfig();
            gantt.refreshTask(id);
            lastHeaderWidthsKey = '';
            queueGridHeaderSync();
        };
        input.addEventListener('keydown', e => {
            e.stopPropagation();
            if (e.key === 'Enter') { e.preventDefault(); commit(); }
            if (e.key === 'Escape') { e.preventDefault(); closeFloatingEditor(); gantt.render(); }
        });
        input.addEventListener('blur', () => setTimeout(() => {
            if (floatingEditorActive) commit();
        }, 150));
        wrap.addEventListener('mousedown', e => e.stopPropagation());
    }

    function configureGantt() {
        if (gantt.plugins) {
            gantt.plugins({ tooltip: true, marker: true });
        }

        gantt.config.date_format = '%Y-%m-%d';
        gantt.config.xml_date = '%Y-%m-%d';
        gantt.config.work_time = false;
        gantt.config.correct_work_time = false;
        gantt.config.skip_off_time = false;
        gantt.config.duration_unit = 'day';
        gantt.config.time_step = 1440;
        gantt.config.row_height = 32;
        gantt.config.bar_height = 22;
        updateRowHeightsForLabels();
        gantt.getTaskHeight = task => getTaskRowHeight(task);
        gantt.config.scale_height = 88;
        updateScaleHeight();
        gantt.config.scroll_size = 20;
        gantt.config.fit_tasks = false;
        gantt.config.show_errors = false;
        gantt.config.highlight_critical_path = true;
        gantt.config.grid_elastic_columns = false;
        gantt.config.keep_grid_width = true;
        gantt.config.round_dnd_dates = false;
        gantt.config.drag_timeline = { useKey: false };
        gantt.config.drag_move = true;
        gantt.config.drag_resize = true;
        gantt.config.drag_progress = true;
        gantt.config.autosize = false;
        gantt.config.reorder_grid_columns = true;
        gantt.config.open_tree_initially = true;
        gantt.config.details_on_dblclick = false;
        gantt.config.details_on_create = false;
        gantt.config.select_task = true;
        gantt.config.keyboard_navigation = false;
        gantt.config.show_task_cells = false;
        gantt.config.show_links = true;

        gantt.config.min_column_width = 50;
        applyTimescaleScales(scheduleSettings.timescale || 'day');

        const todaySeed = new Date();
        gantt.config.start_date = new Date(todaySeed.getFullYear() - ROLLING_YEARS_BACK, 0, 1);
        gantt.config.end_date = new Date(todaySeed.getFullYear() + ROLLING_YEARS_FORWARD, 11, 31);

        const gridW = getColumnsTotalWidth();
        gantt.config.layout = {
            css: 'gantt_container',
            cols: [
                {
                    min_width: 200,
                    rows: [
                        { view: 'grid', scrollX: 'gridScroll', scrollY: 'scrollVer' },
                        { view: 'scrollbar', id: 'gridScroll', height: 20 }
                    ]
                },
                { resizer: true, width: 1 },
                {
                    width: Math.max(360, Math.round((document.getElementById('gantt_here')?.offsetWidth || 1000) * 0.75)),
                    min_width: 220,
                    rows: [
                        { view: 'timeline', scrollX: 'scrollHor', scrollY: 'scrollVer' },
                        { view: 'scrollbar', id: 'scrollHor', height: 20 }
                    ]
                },
                { view: 'scrollbar', id: 'scrollVer' }
            ]
        };
        gantt.config.grid_width = gridW;

        gantt.config.columns = buildColumnConfig();
        registerCustomEditors();

        gantt.attachEvent('onBeforeTaskDisplay', function (id, task) {
            if (filterCriticalOnly) {
                if (task.type === 'project') return true;
                if (isTaskCritical(task)) return true;
                if (gantt.hasChild(id)) {
                    let childCritical = false;
                    gantt.eachTask(t => {
                        if (childCritical) return;
                        if (t.type !== 'project' && isTaskCritical(t)) childCritical = true;
                    }, id);
                    if (childCritical) return true;
                }
                return false;
            }
            if (task.type === 'project') return true;
            if (!taskFilterQuery) return true;
            const hay = [task.text, task.activity_id, task.resource, task.owner, wbsCode(task)].join(' ').toLowerCase();
            return hay.includes(taskFilterQuery);
        });

        gantt.attachEvent('onBeforeLightbox', () => false);

        gantt.attachEvent('onBeforeEditStart', () => false);

        gantt.attachEvent('onEmptyClick', () => closeFloatingEditor());

        gantt.attachEvent('onTaskLoading', (task) => {
            sanitizeTaskDates(task);
            applyTaskBarColor(task);
            return true;
        });

        gantt.templates.grid_row_class = function (start, end, task) {
            if (isParentTask(task)) return 'cpm_project_row sched-parent-row sched-summary-row';
            return '';
        };

        gantt.templates.task_class = function (start, end, task) {
            const classes = [];
            if (task.type === 'project') {
                classes.push('cpm_summary', 'sched-summary-bar');
                return classes.join(' ');
            }
            if (task.type === 'milestone') classes.push('cpm_milestone');
            if (isLoeTask(task)) classes.push('cpm_loe');
            const custom = normalizeHexColor(task.bar_color);
            if (custom) {
                classes.push('cpm_custom_color');
            } else {
                if (gantt.config.highlight_critical_path && isTaskCritical(task)) classes.push('cpm_critical');
                const p = Math.round(effectiveProgress(task) * 100);
                if (p >= 100) classes.push('cpm_complete');
                else if (p > 0) classes.push('cpm_in_progress');
            }
            return classes.join(' ');
        };

        gantt.templates.task_style = function (start, end, task) {
            return buildTaskBarStyle(task);
        };

        gantt.templates.task_text = function (start, end, task) {
            if (task.type === 'project') return task.text || '';
            return task.text || '';
        };

        gantt.templates.rightside_text = function (start, end, task) {
            if (task.type === 'project' || task.type === 'milestone') return task.type === 'milestone' ? task.text : '';
            return formatDateSafe(end);
        };

        gantt.templates.link_class = function () {
            return 'cpm_schedule_link';
        };

        applyGanttDisplayStyles();

        if (window.ScheduleExtras) ScheduleExtras.setupNonWorkTemplates(gantt);

        gantt.templates.tooltip_text = function (start, end, task) {
            const preds = predTemplate(task);
            return `<b>${task.text}</b><br/>
                Start: ${formatDateSafe(start)}<br/>
                Finish: ${formatDateSafe(end)}<br/>
                Duration: ${task.duration}d<br/>
                Progress: ${Math.round(effectiveProgress(task) * 100)}%<br/>
                ${preds ? 'Predecessors: ' + preds : ''}`;
        };

        gantt.attachEvent('onTaskClick', function (id, e) {
            const target = e.target || e.srcElement;
            if (!target.closest?.('.sched-floating-cell-editor')) {
                closeFloatingEditor();
            }
            if (target.closest?.('.sched-tree-btn')) {
                const t = gantt.getTask(id);
                if (gantt.hasChild(id)) {
                    if (t.$open !== false) gantt.close(id); else gantt.open(id);
                }
                return false;
            }
            if (target.closest?.('.gantt_tree_icon')) return true;
            gantt.selectTask(id);
            if (target.closest?.('.gantt_grid_data .gantt_cell')) {
                const pos = locateGridCell(target);
                if (pos) {
                    gridSelection = { type: 'cell', taskId: pos.id, colName: pos.column };
                    highlightGridSelection();
                } else {
                    gridSelection = { type: 'row', taskId: id };
                    highlightGridSelection();
                }
            }
            return true;
        });

        gantt.attachEvent('onTaskDblClick', function (id, e) {
            const target = e.target || e.srcElement;
            if (target.closest?.('.sched-tree-btn') || target.closest?.('.gantt_tree_icon')) return true;
            if (target.closest?.('.gantt_grid')) {
                const pos = (gantt.locateCell && gantt.locateCell(target)) || locateGridCell(target);
                let colName = null;
                if (pos) {
                    if (typeof pos.column === 'number' && gantt.config.columns[pos.column]) {
                        colName = gantt.config.columns[pos.column].name;
                    } else if (typeof pos.column === 'string') {
                        colName = pos.column;
                    } else if (pos.column?.name) {
                        colName = pos.column.name;
                    }
                }
                if (colName && columnEditors.has(colName) && !['wbs', 'successors', 'collapse'].includes(colName)) {
                    setTimeout(() => startCellEdit(id, colName), 0);
                    return false;
                }
                if (window.ScheduleActivityModal) {
                    ScheduleActivityModal.open(id);
                    return false;
                }
            }
            return true;
        });

        gantt.attachEvent('onBeforeTaskUpdate', (id, task) => {
            sanitizeTaskDates(task);
            return true;
        });

        gantt.attachEvent('onAfterTaskUpdate', (id, task) => {
            sanitizeTaskDates(task);
            if (task.progress > 1) task.progress = Math.min(1, task.progress / 100);
            applyTaskBarColor(task);
            gantt.refreshTask(id);
            pushUndoState();
            queueSave();
        });
        gantt.attachEvent('onAfterTaskAdd', () => { pushUndoState(); queueSave(); });
        gantt.attachEvent('onAfterTaskDelete', () => { pushUndoState(); queueSave(); });
        gantt.attachEvent('onAfterLinkAdd', () => { pushUndoState(); queueSave(); });
        gantt.attachEvent('onAfterLinkUpdate', () => { pushUndoState(); queueSave(); });
        gantt.attachEvent('onAfterLinkDelete', () => { pushUndoState(); queueSave(); });
        gantt.attachEvent('onAfterTaskDrag', function (id, mode) {
            applyRollingCalendarRange(false);
            pushUndoState();
            queueSave();
            if (mode === 'move' || mode === 'resize' || mode === 'progress') {
                runSchedule({ skipScroll: true });
            } else {
                queueChartOverlay();
            }
            refreshTimelinePanBar();
        });
        gantt.attachEvent('onAfterColumnReorder', () => {
            columnOrder = gantt.config.columns.map(c => c.name);
            scheduleSettings.column_order = columnOrder.slice();
            syncGridTableWidth();
            queueSave();
            queueGridHeaderSync();
            queueChartOverlay();
        });
        gantt.attachEvent('onColumnResizeStart', function () {
            const grid = document.querySelector('#gantt_here .gantt_grid_data');
            columnResizeScrollLeft = grid ? grid.scrollLeft : 0;
        });
        gantt.attachEvent('onColumnResize', function (index, column, new_width) {
            handleColumnResize(index, column, new_width, false, false);
            preserveGridScrollLeft(columnResizeScrollLeft);
            return false;
        });
        gantt.attachEvent('onColumnResizeEnd', function (index, column, new_width) {
            handleColumnResize(index, column, new_width, true, true);
            columnResizeScrollLeft = null;
        });
        gantt.attachEvent('onGanttRender', () => {
            refreshWbsCodes();
            syncColumnWidthsToConfig();
            updateStatusBar();
            updateDeadlineMarkers();
            ensureTimelineScrollbar();
            restoreTimelineScrollAfterRender();
            refreshTimelinePanBar();
            bindColumnResizeEnhancements();
            bindGridSelectionHandlers();
            queueGridHeaderSync();
            applyCellAlignToDom();
            updateAlignToolbarButtons();
            applyRowHeightsToDom();
            if (ganttReady && document.getElementById('scheduleGanttHost')?.classList.contains('schedule-overlay-mode')) {
                applyChartOverlay();
            }
        });

        document.addEventListener('keydown', onScheduleKeyDown);

        initBaselineBars();
        initBarLabels();
        initTimelineEngine();
        applyRollingCalendarRange(true);


        syncGridTableWidth();
        gantt.init('gantt_here');
        sanitizeAllTaskDates();
        initChartOverlay();
        ganttReady = true;
        bindColumnResizeEnhancements();
        bindGridSelectionHandlers();
        syncScheduleProjectContext();
        queueGridHeaderSync();
        resizeGanttHost();
        window.addEventListener('resize', resizeGanttHost);
    }

    function onScheduleKeyDown(e) {
        const tag = (e.target?.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target?.isContentEditable) return;
        if (!ganttReady) return;

        if (e.key === 'Delete' || e.key === 'Backspace') {
            e.preventDefault();
            deleteSelected();
            return;
        }
        if (e.key === 'F2') {
            e.preventDefault();
            const id = gantt.getSelectedId();
            if (!id) return;
            startCellEdit(id, 'text');
            return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
            const id = gantt.getSelectedId();
            if (id && gantt.isTaskExists(id)) {
                clipboardTaskId = id;
                e.preventDefault();
            }
            return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
            if (clipboardTaskId && gantt.isTaskExists(clipboardTaskId)) {
                e.preventDefault();
                gantt.selectTask(clipboardTaskId);
                duplicateSelected();
            }
            return;
        }
        if (e.key === '?' || (e.shiftKey && e.key === '/')) {
            e.preventDefault();
            showKeyboardShortcuts();
            return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
            e.preventDefault();
            duplicateSelected();
            return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
            e.preventDefault();
            undo();
            return;
        }
        if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) {
            e.preventDefault();
            redo();
        }
    }

    function logActivity(action, detail) {
        if (window.CasePMActivityLog) CasePMActivityLog.log(action, detail, 'schedule');
    }

    function resizeGanttHost() {
        const host = document.getElementById('scheduleGanttHost');
        const chrome = document.getElementById('scheduleChrome');
        if (!host || !chrome) return;
        const top = chrome.getBoundingClientRect().bottom;
        const status = document.getElementById('scheduleStatusBar');
        const footer = document.querySelector('#mainContent + div, .border-t.border-zinc-800');
        const footerH = footer ? footer.offsetHeight : 40;
        const statusH = status ? status.offsetHeight + 8 : 0;
        const h = Math.max(300, window.innerHeight - top - statusH - footerH - 12);
        host.style.height = h + 'px';
        if (!ganttReady) return;
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            gantt.render();
            applyChartOverlay();
            refreshTimelinePanBar();
        }, 80);
    }

    // ─── Persistence ───
    function serializeSchedule() {
        const data = [];
        gantt.eachTask(t => {
            const row = {
                id: t.id,
                text: t.text,
                parent: t.parent,
                type: t.type,
                start_date: t.start_date ? formatDateSafe(t.start_date) : undefined,
                end_date: t.end_date ? formatDateSafe(t.end_date) : undefined,
                duration: t.duration,
                progress: t.progress,
                open: t.open,
                resource: t.resource,
                owner: t.owner,
                bar_color: t.bar_color,
                constraint_type: t.constraint_type,
                constraint_date: t.constraint_date
            };
            EXTENDED_FIELDS.forEach(f => { if (t[f] != null && t[f] !== '') row[f] = t[f]; });
            if (t.cell_align && Object.keys(t.cell_align).length) row.cell_align = t.cell_align;
            customColumns.forEach(cc => { row[cc.map_to || cc.name] = t[cc.map_to || cc.name] || ''; });
            data.push(row);
        });
        const links = gantt.getLinks().map(l => ({
            id: l.id, source: l.source, target: l.target, type: String(l.type), lag: l.lag || 0
        }));
        return { data, links, baselines, customColumns, hiddenColumns, columnWidths, columnOrder: scheduleSettings.column_order || columnOrder, settings: scheduleSettings };
    }

    function loadSchedulePayload(payload) {
        if (!payload || !payload.data) return false;
        customColumns = payload.customColumns || [];
        hiddenColumns = payload.hiddenColumns || [];
        columnWidths = payload.columnWidths || {};
        columnOrder = payload.columnOrder || payload.settings?.column_order || [];
        scheduleSettings.column_order = columnOrder.slice();
        normalizeTaskDates(payload.data);
        gantt.config.columns = buildColumnConfig();
        updateGridWidth();
        gantt.clearAll();
        gantt.parse({ data: payload.data, links: payload.links || [] });
        sanitizeAllTaskDates();
        baselines = payload.baselines || [];
        if (payload.settings) scheduleSettings = Object.assign(scheduleSettings, payload.settings);
        if (!scheduleSettings.theme) scheduleSettings.theme = 'dark';
        if (window.ScheduleExtras) ScheduleExtras.applyThemeFromSettings();
        if (!scheduleSettings.print_settings) {
            scheduleSettings.print_settings = {
                include_summary: true, include_activity_table: true, include_inline_bars: true,
                include_schedule_chart: false, include_evm: false, include_footer: true
            };
        }
        ensureHeaderFooterSettings();
        if (!scheduleSettings.compare_baseline_indices) scheduleSettings.compare_baseline_indices = [];
        refreshWbsCodes();
        applySettingsToUI();
        gantt.eachTask(t => applyTaskBarColor(t));
        syncScheduleProjectContext();
        applyBaselineVariance();
        applyRollingCalendarRange(true);
        updateRowHeightsForLabels();
        syncScheduleProjectContext();
        queueChartOverlay();
        gantt.render();
        queueGridHeaderSync();
        setSaveStatus('Ready');
        pushUndoState();
        updateDataDateMarker();
        updateDeadlineMarkers();
        if (!initialTimelineFocused) {
            initialTimelineFocused = true;
            setTimeout(() => {
                applyRollingCalendarRange(true);
                gantt.render();
                jumpToScheduleTasks();
                applyChartOverlay();
            }, 150);
        }
        return true;
    }

    async function loadSchedule() {
        const projectId = getSelectedProjectId();
        setSaveStatus('Loading…');

        try {
            const res = await fetch(`/api/schedule?project_id=${projectId}`);
            if (res.ok) {
                const json = await res.json();
                if (json.payload && json.payload.data && json.payload.data.length) {
                    if (loadSchedulePayload(json.payload)) {
                        setSaveStatus('Loaded from server');
                        return;
                    }
                }
            }
        } catch (e) { /* local fallback */ }

        const local = localStorage.getItem(`${STORAGE_KEY}_${projectId}`);
        if (local) {
            try {
                const parsed = JSON.parse(local);
                if (parsed.data && parsed.data.length && loadSchedulePayload(parsed)) {
                    setSaveStatus('Loaded from browser');
                    return;
                }
            } catch (e) { /* ignore */ }
        }

        loadSchedulePayload(buildEmptySchedule(await fetchProjectScheduleDefaults(projectId)));
        setSaveStatus('Empty schedule — add activities or import');
    }

    async function clearSchedule() {
        if (!confirm('Clear the entire schedule? This cannot be undone.')) return;
        const projectId = getSelectedProjectId();
        localStorage.removeItem(`${STORAGE_KEY}_${projectId}`);
        loadSchedulePayload(buildEmptySchedule(await fetchProjectScheduleDefaults(projectId)));
        try {
            await fetch('/api/schedule', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_id: projectId, payload: serializeSchedule() })
            });
        } catch (e) { /* ok */ }
        setSaveStatus('Schedule cleared');
        logActivity('Cleared schedule', 'All activities removed');
    }

    function queueSave() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveSchedule, 800);
        setSaveStatus('Saving…');
    }

    async function saveSchedule() {
        if (!ganttReady) return;
        const projectId = getSelectedProjectId();
        const payload = serializeSchedule();
        localStorage.setItem(`${STORAGE_KEY}_${projectId}`, JSON.stringify(payload));
        try {
            await fetch('/api/schedule', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_id: projectId, payload })
            });
            setSaveStatus('Saved');
            logActivity('Saved schedule', `${countTasks()} activities`);
        } catch (e) {
            setSaveStatus('Saved locally');
        }
    }

    function getSelectedProjectId() {
        const fromUrl = new URLSearchParams(window.location.search).get('project_id');
        const ctx = document.getElementById('scheduleProjectContext');
        const fromCtx = ctx?.dataset?.projectId;
        const fromGlobal = window.CASEPM_ACTIVE_PROJECT_ID;
        const fromStorage = localStorage.getItem('casepm_current_project_id');
        const id = parseInt(fromUrl || fromCtx || fromGlobal || fromStorage || '0', 10);
        return id || 0;
    }

    function openActivityDetail() {
        const id = gantt.getSelectedId();
        if (!id) return showScheduleAlert('Select an activity first.', 'warning');
        if (window.ScheduleActivityModal) ScheduleActivityModal.open(id);
    }

    function applyGanttDisplayStyles() {
        const s = scheduleSettings;
        const root = document.documentElement;
        root.style.setProperty('--gantt-link-color', s.link_color || '#94a3b8');
        root.style.setProperty('--gantt-link-width', (s.link_width || 2) + 'px');
        if (ganttReady) gantt.render();
    }

    function applyTimescaleScales(scale) {
        const scales = {
            day: [
                { unit: 'month', step: 1, format: '%F %Y' },
                { unit: 'day', step: 1, format: '%d' }
            ],
            week: [
                { unit: 'month', step: 1, format: '%F %Y' },
                { unit: 'day', step: 1, format: '%d' }
            ],
            month: [
                { unit: 'year', step: 1, format: '%Y' },
                { unit: 'month', step: 1, format: '%M' },
                { unit: 'day', step: 1, format: '%d' }
            ],
            quarter: [
                { unit: 'year', step: 1, format: '%Y' },
                { unit: 'month', step: 3, format: '%M' }
            ]
        };
        gantt.config.scales = scales[scale] || scales.day;
        const widthByScale = { day: 32, week: 28, month: 18, quarter: 40 };
        gantt.config.min_column_width = widthByScale[scale] || 32;
        updateScaleHeight();
    }

    function jumpToScheduleTasks() {
        let target = null;
        gantt.eachTask(t => {
            if (target || t.type === 'project') return;
            const d = toGanttDate(t.start_date);
            if (d) target = d;
        });
        if (target) scrollTimelineToDate(target, getTimelineWidth() / 3);
        else scrollToToday();
    }

    function setTimescale(scale, persist) {
        if (!scale) return;
        scheduleSettings.timescale = scale;
        const anchor = gantt.getScrollState?.() && typeof gantt.dateFromPos === 'function'
            ? gantt.dateFromPos(gantt.getScrollState().x + getTimelineWidth() / 2)
            : null;
        applyTimescaleScales(scale);
        applyRollingCalendarRange(true);
        gantt.render();
        if (anchor) scrollTimelineToDate(anchor, getTimelineWidth() / 2);
        document.querySelectorAll('[data-timescale]').forEach(btn => {
            const on = btn.getAttribute('data-timescale') === scale;
            btn.classList.toggle('active-tool', on);
        });
        if (persist !== false) queueSave();
    }

    function showDisplaySettings() {
        const s = scheduleSettings;
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        set('dispBarColor', s.default_bar_color || '#3b82f6');
        set('dispCriticalColor', s.critical_bar_color || '#ef4444');
        set('dispProgressColor', s.progress_bar_color || '#f59e0b');
        set('dispCompleteColor', s.complete_bar_color || '#71717a');
        set('dispMilestoneColor', s.milestone_color || '#8b5cf6');
        set('dispLinkColor', s.link_color || '#94a3b8');
        set('dispLinkWidth', s.link_width || 2);
        set('dispDefaultRowHeight', s.default_row_height || 32);
        set('dispDefaultBarHeight', s.default_bar_height || 22);
        set('dispSummaryRowHeight', s.summary_row_height || 48);
        set('dispSummaryBarHeight', s.summary_bar_height || 26);
        const bl = document.getElementById('dispShowBaselineBars');
        if (bl) bl.checked = s.show_baseline_bars !== false;
        const lbl = document.getElementById('dispShowBarLabels');
        if (lbl) lbl.checked = s.show_bar_labels !== false;
        document.getElementById('scheduleDisplayModal')?.showModal();
    }

    function saveDisplaySettings() {
        const get = id => document.getElementById(id)?.value;
        scheduleSettings.default_bar_color = get('dispBarColor') || '#3b82f6';
        scheduleSettings.critical_bar_color = get('dispCriticalColor') || '#ef4444';
        scheduleSettings.progress_bar_color = get('dispProgressColor') || '#f59e0b';
        scheduleSettings.complete_bar_color = get('dispCompleteColor') || '#71717a';
        scheduleSettings.milestone_color = get('dispMilestoneColor') || '#8b5cf6';
        scheduleSettings.link_color = get('dispLinkColor') || '#94a3b8';
        scheduleSettings.link_width = parseInt(get('dispLinkWidth'), 10) || 2;
        scheduleSettings.show_baseline_bars = document.getElementById('dispShowBaselineBars')?.checked !== false;
        scheduleSettings.show_bar_labels = document.getElementById('dispShowBarLabels')?.checked !== false;
        scheduleSettings.default_row_height = parseInt(get('dispDefaultRowHeight'), 10) || 32;
        scheduleSettings.default_bar_height = parseInt(get('dispDefaultBarHeight'), 10) || 22;
        scheduleSettings.summary_row_height = parseInt(get('dispSummaryRowHeight'), 10) || 48;
        scheduleSettings.summary_bar_height = parseInt(get('dispSummaryBarHeight'), 10) || 26;
        gantt.eachTask(t => applyTaskBarColor(t));
        updateRowHeightsForLabels();
        applyGanttDisplayStyles();
        gantt.render();
        document.getElementById('scheduleDisplayModal')?.close();
        queueSave();
        showScheduleAlert('Display settings applied', 'success');
    }

    function applySettingsToUI() {
        const dd = document.getElementById('dataDateInput');
        const la = document.getElementById('lookaheadDaysInput');
        if (dd) dd.value = scheduleSettings.data_date || CasePMSchedule.formatDate(new Date());
        if (la) la.value = scheduleSettings.lookahead_days || 14;
        applyGanttDisplayStyles();
        if (!scheduleSettings.default_cell_align) {
            scheduleSettings.default_cell_align = { h: 'left', v: 'middle' };
        }
        if (scheduleSettings.grid_cell_align_h || scheduleSettings.grid_cell_align_v) {
            scheduleSettings.default_cell_align = normalizeCellAlign({
                h: scheduleSettings.grid_cell_align_h,
                v: scheduleSettings.grid_cell_align_v
            });
            delete scheduleSettings.grid_cell_align_h;
            delete scheduleSettings.grid_cell_align_v;
        }
        if (!scheduleSettings.column_align) scheduleSettings.column_align = {};
        if (!scheduleSettings.default_cell_style) scheduleSettings.default_cell_style = { font_size: 13 };
        const fsSel = document.getElementById('schedFontSizeInput');
        if (fsSel) fsSel.value = String(getDefaultCellFontSize());
        const rhSel = document.getElementById('schedRowHeightInput');
        if (rhSel) rhSel.value = String(scheduleSettings.default_row_height || 32);
        updateAlignToolbarButtons();
        if (scheduleSettings.timescale) setTimescale(scheduleSettings.timescale, false);
        else setTimescale('day', false);
        updateDataDateMarker();
    }

    function applyFontSizeToSelection(fontSize) {
        const fs = Math.max(9, Math.min(24, parseInt(fontSize, 10) || 13));
        const sel = gridSelection;
        if (!sel.type) {
            if (!scheduleSettings.default_cell_style) scheduleSettings.default_cell_style = {};
            scheduleSettings.default_cell_style.font_size = fs;
        } else if (sel.type === 'column' && sel.colName) {
            if (!scheduleSettings.column_align) scheduleSettings.column_align = {};
            if (!scheduleSettings.column_align[sel.colName]) scheduleSettings.column_align[sel.colName] = {};
            scheduleSettings.column_align[sel.colName].font_size = fs;
            gantt.eachTask(t => {
                if (t.cell_align?.[sel.colName]) delete t.cell_align[sel.colName].font_size;
            });
        } else if (sel.type === 'cell' && sel.taskId && gantt.isTaskExists(sel.taskId)) {
            const task = gantt.getTask(sel.taskId);
            if (!task.cell_align) task.cell_align = {};
            if (!task.cell_align[sel.colName]) task.cell_align[sel.colName] = {};
            task.cell_align[sel.colName].font_size = fs;
            gantt.updateTask(sel.taskId);
        } else {
            const taskId = (sel.type === 'row' && sel.taskId) ? sel.taskId : gantt.getSelectedId();
            if (!taskId || !gantt.isTaskExists(taskId)) {
                if (!scheduleSettings.default_cell_style) scheduleSettings.default_cell_style = {};
                scheduleSettings.default_cell_style.font_size = fs;
            } else {
                const task = gantt.getTask(taskId);
                if (!task.cell_align) task.cell_align = {};
                (gantt.config.columns || []).forEach(col => {
                    if (!task.cell_align[col.name]) task.cell_align[col.name] = {};
                    task.cell_align[col.name].font_size = fs;
                });
                gantt.updateTask(taskId);
            }
        }
        highlightGridSelection();
        pushUndoState();
        queueSave();
    }

    function applyRowHeightToSelection(height, allRows) {
        const h = Math.max(18, Math.min(80, parseInt(height, 10) || 32));
        if (allRows) {
            scheduleSettings.default_row_height = h;
            gantt.eachTask(t => {
                if (t.type !== 'project') delete t.row_height;
                gantt.updateTask(t.id);
            });
        } else {
            const sel = gridSelection;
            const taskId = (sel.type === 'cell' && sel.taskId) ? sel.taskId
                : ((sel.type === 'row' && sel.taskId) ? sel.taskId : gantt.getSelectedId());
            if (!taskId || !gantt.isTaskExists(taskId)) {
                scheduleSettings.default_row_height = h;
            } else {
                const task = gantt.getTask(taskId);
                task.row_height = h;
                gantt.updateTask(taskId);
            }
        }
        updateRowHeightsForLabels();
        gantt.render();
        applyRowHeightsToDom();
        pushUndoState();
        queueSave();
    }

    function setGridFontSize(fontSize) {
        applyFontSizeToSelection(fontSize);
        const inp = document.getElementById('schedFontSizeInput');
        if (inp) inp.value = String(Math.max(8, Math.min(24, parseInt(fontSize, 10) || 13)));
    }

    function setGridRowHeight(height, allRows) {
        applyRowHeightToSelection(height, !!allRows);
        const inp = document.getElementById('schedRowHeightInput');
        if (inp) inp.value = String(Math.max(18, Math.min(80, parseInt(height, 10) || 32)));
    }

    function saveBarSettingsAsDefaults(task) {
        if (!task) return;
        if (task.bar_color) scheduleSettings.default_bar_color = normalizeHexColor(task.bar_color) || task.bar_color;
        if (task.bar_height) scheduleSettings.default_bar_height = parseInt(task.bar_height, 10) || scheduleSettings.default_bar_height;
        if (task.type === 'project') {
            if (task.row_height) scheduleSettings.summary_row_height = parseInt(task.row_height, 10) || scheduleSettings.summary_row_height;
            if (task.bar_height) scheduleSettings.summary_bar_height = parseInt(task.bar_height, 10) || scheduleSettings.summary_bar_height;
        }
        gantt.eachTask(t => applyTaskBarColor(t));
        updateRowHeightsForLabels();
        applyGanttDisplayStyles();
        gantt.render();
        queueSave();
        showScheduleAlert('Bar settings saved as schedule defaults.', 'success');
    }

    function setGridCellAlignH(align) {
        if (!['left', 'center', 'right'].includes(align)) return;
        applyAlignToSelection('h', align);
    }

    function setGridCellAlignV(align) {
        if (!['top', 'middle', 'bottom'].includes(align)) return;
        applyAlignToSelection('v', align);
    }

    function setSaveStatus(msg) {
        const el = document.getElementById('scheduleSaveStatus');
        if (el) el.textContent = msg;
    }

    // ─── Toolbar ───
    function resolveAddParent() {
        let parent = gantt.getSelectedId();
        if (!parent || !gantt.isTaskExists(parent)) {
            parent = null;
            gantt.eachTask(t => {
                if (!parent && (t.parent === 0 || t.parent == null) && t.type === 'project') parent = t.id;
            });
        }
        if (!parent) parent = 0;
        if (parent && gantt.getTask(parent).type === 'task') promoteToSummary(parent);
        if (parent && gantt.isTaskExists(parent)) {
            const p = gantt.getTask(parent);
            p.open = true;
            gantt.updateTask(parent);
            gantt.open(parent);
        }
        return parent;
    }

    function duplicateSelected() {
        const id = gantt.getSelectedId();
        if (!id || !gantt.isTaskExists(id)) return showScheduleAlert('Select an activity to duplicate.', 'warning');
        const src = gantt.getTask(id);
        if (src.type === 'project') return showScheduleAlert('Select a task or milestone to duplicate, not a summary row.', 'warning');
        const clone = {
            text: (src.text || 'Activity') + ' (copy)',
            activity_id: nextActivityId(),
            type: src.type || 'task',
            start_date: toGanttDate(src.start_date),
            end_date: toGanttDate(src.end_date),
            duration: src.duration,
            progress: src.progress || 0,
            parent: src.parent,
            open: true,
            resource: src.resource,
            owner: src.owner,
            cost: src.cost,
            bar_color: src.bar_color,
            constraint_type: src.constraint_type,
            constraint_date: src.constraint_date,
            activity_type: src.activity_type,
            percent_complete_type: src.percent_complete_type,
            notes: src.notes
        };
        EXTENDED_FIELDS.forEach(f => {
            if (src[f] != null && clone[f] == null) clone[f] = src[f];
        });
        const newId = gantt.addTask(clone, src.parent);
        applyTaskBarColor(gantt.getTask(newId));
        gantt.selectTask(newId);
        focusTimelineOnTask(newId);
        gantt.render();
        pushUndoState();
        queueSave();
        logActivity('Duplicated activity', src.text);
    }

    function addActivity(type) {
        const parent = resolveAddParent();
        const today = toGanttDate(CasePMSchedule.formatDate(new Date()));
        const id = gantt.addTask({
            text: type === 'milestone' ? 'New Milestone' : 'New Activity',
            activity_id: nextActivityId(),
            type: type || 'task',
            start_date: today,
            end_date: type === 'milestone' ? today : CasePMSchedule.addCalendarDays(today, 5),
            duration: type === 'milestone' ? 0 : 5,
            progress: 0,
            open: true,
            parent: parent
        }, parent);
        applyTaskBarColor(gantt.getTask(id));
        gantt.selectTask(id);
        gantt.showTask(id);
        gantt.render();
        queueChartOverlay();
        queueGridHeaderSync();
        if (window.ScheduleActivityModal) ScheduleActivityModal.open(id);
        else showScheduleAlert('Open activity detail by double-clicking a row.', 'info');
        logActivity('Added activity', type === 'milestone' ? 'Milestone' : 'Task');
    }

    function deleteSelected() {
        const ids = gantt.getSelectedTasks ? gantt.getSelectedTasks() : [gantt.getSelectedId()].filter(Boolean);
        if (!ids.length) return showScheduleAlert('Select one or more activities first.', 'warning');
        if (!confirm('Delete selected activities and their relationships?')) return;
        ids.forEach(id => { if (gantt.isTaskExists(id)) gantt.deleteTask(id); });
    }

    function promoteToSummary(taskId) {
        const task = gantt.getTask(taskId);
        if (task.type === 'milestone') return;
        if (task.type !== 'project') {
            task.type = 'project';
            task.open = true;
            gantt.updateTask(taskId);
        }
    }

    function demoteSummaryIfEmpty(taskId) {
        if (!taskId || !gantt.isTaskExists(taskId)) return;
        const task = gantt.getTask(taskId);
        if (task.type === 'project' && !gantt.hasChild(taskId)) {
            task.type = 'task';
            gantt.updateTask(taskId);
        }
    }

    function indentSelected() {
        const id = gantt.getSelectedId();
        if (!id) return showScheduleAlert('Select an activity to indent.', 'warning');
        const parent = gantt.getParent(id);
        const prev = gantt.getPrevSibling(id);
        if (!prev) {
            if (parent && parent !== 0) {
                return showScheduleAlert('No sibling above at this level — use Outdent first.', 'warning');
            }
            return showScheduleAlert('No activity above to indent under.', 'warning');
        }
        promoteToSummary(prev);
        const childCount = gantt.getChildren(prev).filter(cid => cid !== id).length;
        gantt.moveTask(id, childCount, prev);
        gantt.open(prev);
        gantt.refreshTask(prev);
        gantt.selectTask(id);
        refreshWbsCodes();
        gantt.render();
        queueSave();
    }

    function getRootProjectId() {
        let rootId = null;
        gantt.eachTask(t => {
            if (!rootId && (t.parent === 0 || t.parent == null) && t.type === 'project') rootId = t.id;
        });
        return rootId;
    }

    function outdentSelected() {
        const id = gantt.getSelectedId();
        if (!id) return showScheduleAlert('Select an activity to outdent.', 'warning');
        const rootId = getRootProjectId();
        if (rootId != null && String(id) === String(rootId)) {
            return showScheduleAlert('The main project summary cannot be outdented.', 'warning');
        }
        const parent = gantt.getParent(id);
        if (!parent || parent === 0) return showScheduleAlert('Activity is already at top level.', 'warning');
        const grandParent = gantt.getParent(parent) || 0;
        if (grandParent === 0 || grandParent === '0') {
            return showScheduleAlert('Cannot outdent past the project summary — all activities must stay under the main construction task.', 'warning');
        }
        const insertAt = gantt.getTaskIndex(parent) + 1;
        gantt.moveTask(id, insertAt, grandParent);
        demoteSummaryIfEmpty(parent);
        gantt.selectTask(id);
        refreshWbsCodes();
        gantt.render();
        queueSave();
    }

    function linkSelected(type) {
        const ids = gantt.getSelectedTasks ? gantt.getSelectedTasks() : [];
        if (ids.length < 2) return showScheduleAlert('Select at least two activities to create a relationship.', 'warning');
        for (let i = 0; i < ids.length - 1; i++) {
            gantt.addLink({ source: ids[i], target: ids[i + 1], type: LINK_TYPES[type] || LINK_TYPES.FS });
        }
    }

    function unlinkSelected() {
        const id = gantt.getSelectedId();
        if (!id) return;
        const links = [...(gantt.getTask(id).$source || []), ...(gantt.getTask(id).$target || [])];
        links.forEach(lid => gantt.deleteLink(lid));
    }

    function zoomGantt(dir) {
        const cur = gantt.config.min_column_width || 50;
        gantt.config.min_column_width = Math.max(24, Math.min(100, cur + (dir === 'in' ? -6 : 6)));
        const anchor = gantt.getScrollState?.() && typeof gantt.dateFromPos === 'function'
            ? gantt.dateFromPos(gantt.getScrollState().x + getTimelineWidth() / 2)
            : null;
        applyRollingCalendarRange(true);
        gantt.render();
        if (anchor) scrollTimelineToDate(anchor, getTimelineWidth() / 2);
    }

    function toggleCriticalPath() {
        gantt.config.highlight_critical_path = !gantt.config.highlight_critical_path;
        gantt.render();
        document.getElementById('criticalPathBtn')?.classList.toggle('active-tool', gantt.config.highlight_critical_path);
    }

    function setBaseline() {
        const snap = serializeSchedule();
        const name = `Baseline ${baselines.length + 1} — ${CasePMSchedule.formatDate(new Date())}`;
        baselines.push({ name, created: new Date().toISOString(), data: snap.data });
        if (baselines.length > 10) baselines.shift();
        scheduleSettings.active_baseline_index = baselines.length - 1;
        applyBaselineVariance();
        gantt.render();
        showScheduleAlert(`Baseline saved: ${name}`, 'success');
        queueSave();
    }

    let taskFilterQuery = '';
    let deadlineMarkerIds = [];

    function updateDeadlineMarkers() {
        if (!ganttReady || !gantt.addMarker) return;
        deadlineMarkerIds.forEach(id => { try { gantt.deleteMarker(id); } catch (e) { /* ok */ } });
        deadlineMarkerIds = [];
        gantt.eachTask(t => {
            if (t.type === 'project' || !t.deadline) return;
            const d = toGanttDate(t.deadline);
            if (!d) return;
            const mid = gantt.addMarker({
                start_date: d,
                css: 'schedule-deadline-marker',
                text: '◆',
                title: `Deadline: ${t.text || ''} (${CasePMSchedule.formatDate(d)})`
            });
            deadlineMarkerIds.push(mid);
        });
    }

    function filterTasks(query) {
        taskFilterQuery = (query || '').trim().toLowerCase();
        gantt.render();
    }

    function toggleCriticalFilter() {
        filterCriticalOnly = !filterCriticalOnly;
        document.getElementById('criticalFilterBtn')?.classList.toggle('active-tool', filterCriticalOnly);
        gantt.render();
        showScheduleAlert(filterCriticalOnly ? 'Showing critical activities only' : 'Showing all activities', 'info');
    }

    function sortByStartDate() {
        if (!ganttReady) return;
        const buckets = new Map();
        gantt.eachTask(t => {
            const p = String(t.parent || 0);
            if (!buckets.has(p)) buckets.set(p, []);
            buckets.get(p).push(t);
        });
        buckets.forEach(list => {
            list.sort((a, b) => {
                const as = toGanttDate(a.start_date)?.getTime() || 0;
                const bs = toGanttDate(b.start_date)?.getTime() || 0;
                return as - bs || String(a.text || '').localeCompare(String(b.text || ''));
            });
            list.forEach((t, idx) => gantt.moveTask(t.id, idx, t.parent));
        });
        refreshWbsCodes();
        gantt.render();
        pushUndoState();
        queueSave();
        logActivity('Sorted schedule', 'Activities ordered by start date within each WBS level');
    }

    function exportXer() {
        if (typeof CasePMScheduleExport === 'undefined') {
            return showScheduleAlert('Export module not loaded.', 'error');
        }
        const blob = new Blob([CasePMScheduleExport.toXer(serializeSchedule(), getProjectMeta())], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `schedule_${CasePMSchedule.formatDate(new Date())}.xer`;
        a.click();
        logActivity('Exported XER', getProjectMeta().name);
    }

    function exportMsProjectXml() {
        if (typeof CasePMScheduleExport === 'undefined') {
            return showScheduleAlert('Export module not loaded.', 'error');
        }
        const blob = new Blob([CasePMScheduleExport.toMsProjectXml(serializeSchedule(), getProjectMeta())], { type: 'application/xml' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `schedule_${CasePMSchedule.formatDate(new Date())}.xml`;
        a.click();
        logActivity('Exported MS Project XML', getProjectMeta().name);
    }

    function nextActivityId() {
        let max = 0;
        gantt.eachTask(t => {
            const n = parseInt(String(t.activity_id || '').replace(/\D/g, ''), 10);
            if (!Number.isNaN(n) && n > max) max = n;
        });
        return String(max + 10);
    }

    function exportCsv() {
        const cols = (gantt.config.columns || []).filter(c => c.name !== 'collapse' && c.name !== 'bar_color');
        const headers = cols.map(c => c.label || c.name);
        const rows = [headers];
        gantt.eachTask(t => {
            rows.push(cols.map(c => {
                let v = '';
                if (c.name === 'wbs') v = wbsCode(t);
                else if (c.name === 'predecessors') v = predTemplate(t);
                else if (c.name === 'successors') v = succTemplate(t);
                else if (c.template) v = String(c.template(t)).replace(/<[^>]+>/g, '').trim();
                else v = t[c.name] != null ? t[c.name] : '';
                if (v instanceof Date) v = formatDateSafe(v);
                return v;
            }));
        });
        const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
        const filename = `schedule_${CasePMSchedule.formatDate(new Date())}.csv`;
        if (typeof CasePMOutput !== 'undefined') {
            CasePMOutput.deliverBlob({
                title: 'Export Schedule',
                blob: new Blob([csv], { type: 'text/csv' }),
                mimeType: 'text/csv',
                filename,
                filenameBase: `schedule_${CasePMSchedule.formatDate(new Date())}`,
                sourceModule: 'schedule',
                systemFolderKey: 'printed-output',
                fileLabel: 'CSV',
            });
            return;
        }
        const blob = new Blob([csv], { type: 'text/csv' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
    }

    function rollupSummaryProgress() {
        function walk(parentId) {
            const kids = gantt.getChildren(parentId) || [];
            kids.forEach(walk);
            if (!gantt.isTaskExists(parentId)) return;
            const t = gantt.getTask(parentId);
            if (t.type !== 'project') return;
            const children = kids.filter(id => gantt.isTaskExists(id)).map(id => gantt.getTask(id)).filter(c => c.type !== 'project');
            if (!children.length) return;
            const total = children.reduce((s, c) => s + (Number(c.duration) || 0), 0);
            if (total <= 0) return;
            const earned = children.reduce((s, c) => s + (Number(c.duration) || 0) * effectiveProgress(c), 0);
            t.progress = earned / total;
            gantt.refreshTask(parentId);
        }
        walk(0);
    }

    function scrollToScheduleRange() {
        if (!ganttReady) return;
        const range = gantt.getSubtaskDates();
        if (!range?.start_date) return;
        const d = toGanttDate(range.start_date);
        if (d) scrollTimelineToDate(CasePMSchedule.addCalendarDays(d, -7));
    }

    function runSchedule(options) {
        const opts = options || {};
        const dataDate = CasePMSchedule.parseDate(document.getElementById('dataDateInput')?.value) || new Date();
        scheduleSettings.data_date = CasePMSchedule.formatDate(dataDate);
        const tasks = [];
        gantt.eachTask(t => tasks.push(Object.assign({}, t)));
        const links = gantt.getLinks().map(l => Object.assign({}, l));
        const { updates, wbsMap } = CasePMSchedule.runCPM(tasks, links, { dataDate });
        const evmFields = ['bcws', 'bcwp', 'acwp', 'cpi', 'spi', 'cost_variance', 'schedule_variance', 'schedule_percent_complete'];
        const cpmFields = ['early_start', 'early_finish', 'late_start', 'late_finish'];
        updates.forEach((patch, id) => {
            if (!gantt.isTaskExists(id)) return;
            const task = gantt.getTask(id);
            if (patch.start_date) task.start_date = toGanttDate(patch.start_date);
            if (patch.end_date) task.end_date = toGanttDate(patch.end_date);
            cpmFields.forEach(f => {
                if (patch[f]) task[f] = CasePMSchedule.formatDate(patch[f]);
            });
            if (patch.total_float != null) task.total_float = patch.total_float;
            if (patch.free_float != null) task.free_float = patch.free_float;
            evmFields.forEach(f => { if (patch[f] != null) task[f] = patch[f]; });
            task.$slack = patch.$slack;
            task.$critical = patch.$critical;
            sanitizeTaskDates(task);
            gantt.refreshTask(id);
        });
        sanitizeAllTaskDates();
        applyBaselineVariance();
        rollupSummaryProgress();
        applyRollingCalendarRange(false);
        wbsCodeMap = wbsMap || CasePMSchedule.buildWbsMap(tasks);
        gantt.render();
        if (!opts.skipScroll) scrollToScheduleRange();
        updateDataDateMarker();
        applyChartOverlay();
        updateStatusBar();
        queueSave();
        logActivity('Ran CPM schedule', `${updates.size} activities calculated`);
    }

    function showColumnManager() {
        const dlg = document.getElementById('scheduleColumnManagerModal');
        if (!dlg) return showAddColumnDialog();
        const visible = document.getElementById('scheduleVisibleColumnsList');
        if (visible) {
            const cols = gantt.config.columns || [];
            if (!cols.length) {
                visible.innerHTML = '<p class="text-zinc-500 text-sm">No columns visible.</p>';
            } else {
                visible.innerHTML = cols.map(col => {
                    const required = REQUIRED_COLUMNS.includes(col.name);
                    const label = col.label || col.name;
                    return `<div class="flex items-center justify-between gap-2 px-3 py-2 rounded-md bg-zinc-800/80 border border-zinc-700">
                        <span class="text-sm">${label}</span>
                        ${required
                            ? '<span class="text-[0.65rem] text-zinc-500">Required</span>'
                            : `<button type="button" class="text-xs text-red-400 hover:text-red-300 px-2 py-1" onclick="ScheduleApp.removeColumn('${col.name}')">Remove</button>`}
                    </div>`;
                }).join('');
            }
        }
        showAddColumnDialog(true);
        dlg.showModal();
    }

    function showAddColumnDialog(managerMode) {
        const dlg = managerMode
            ? document.getElementById('scheduleColumnManagerModal')
            : document.getElementById('scheduleFieldPickerModal');
        if (!dlg || typeof CasePMScheduleFields === 'undefined') {
            if (!managerMode) showScheduleAlert('Field catalog not loaded.', 'error');
            return;
        }
        const existing = gantt.config.columns.map(c => c.name);
        const addable = CasePMScheduleFields.getAddableFields(existing);
        const container = document.getElementById(managerMode ? 'scheduleFieldPickerListMgr' : 'scheduleFieldPickerList');
        if (!container) return;
        if (!addable.length) {
            container.innerHTML = '<p class="text-zinc-400 text-sm p-2">All standard fields are already visible in the grid.</p>';
        } else {
            const groups = CasePMScheduleFields.groupFields(addable);
            let html = '';
            Object.keys(groups).sort().forEach(g => {
                html += `<div class="mb-3"><div class="text-xs uppercase text-emerald-400 font-semibold mb-1">${g}</div><div class="space-y-1">`;
                groups[g].forEach(f => {
                    html += `<button type="button" class="w-full text-left px-3 py-2 rounded-md bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-sm" onclick="ScheduleApp.addFieldColumn('${f.map_to}')">
                        <span class="font-medium">${f.label}</span>
                        <span class="block text-xs text-zinc-500 mt-0.5">${f.desc}</span>
                    </button>`;
                });
                html += '</div></div>';
            });
            container.innerHTML = html;
        }
        if (!managerMode) dlg.showModal();
    }

    function removeColumn(name) {
        if (REQUIRED_COLUMNS.includes(name)) {
            showScheduleAlert('Activity Name is required and cannot be removed.', 'warning');
            return;
        }
        const customIdx = customColumns.findIndex(c => (c.map_to || c.name) === name);
        if (customIdx >= 0) customColumns.splice(customIdx, 1);
        if (!hiddenColumns.includes(name)) hiddenColumns.push(name);
        gantt.config.columns = buildColumnConfig();
        updateGridWidth();
        gantt.render();
        queueSave();
        logActivity('Removed column', name);
        showColumnManager();
    }

    function addFieldColumn(mapTo) {
        const field = CasePMScheduleFields.getField(mapTo);
        if (!field) return;
        if (customColumns.find(c => (c.map_to || c.name) === mapTo)) {
            showScheduleAlert('Column already visible.', 'warning');
            return;
        }
        customColumns.push({ name: mapTo, map_to: mapTo, label: field.label, width: 100 });
        hiddenColumns = hiddenColumns.filter(n => n !== mapTo);
        gantt.config.columns = buildColumnConfig();
        updateGridWidth();
        gantt.render();
        document.getElementById('scheduleFieldPickerModal')?.close();
        document.getElementById('scheduleColumnManagerModal')?.close();
        queueSave();
        logActivity('Added column', field.label);
        showScheduleAlert(`Column "${field.label}" added to grid.`, 'success');
    }

    // ─── Views ───
    function switchScheduleView(view) {
        ['ganttViewPanel', 'calendarViewPanel', 'lookaheadViewPanel', 'traceViewPanel', 'portfolioViewPanel'].forEach(id => {
            document.getElementById(id)?.classList.add('hidden');
        });
        document.querySelectorAll('.schedule-view-tab').forEach(btn => btn.classList.remove('active-view'));

        if (view === 'gantt') {
            document.getElementById('ganttViewPanel')?.classList.remove('hidden');
            document.getElementById('tabGantt')?.classList.add('active-view');
            resizeGanttHost();
            gantt.render();
            applyChartOverlay();
        } else if (view === 'calendar') {
            document.getElementById('calendarViewPanel')?.classList.remove('hidden');
            document.getElementById('tabCalendar')?.classList.add('active-view');
            renderCalendarView();
        } else if (view === 'lookahead') {
            document.getElementById('lookaheadViewPanel')?.classList.remove('hidden');
            document.getElementById('tabLookahead')?.classList.add('active-view');
            renderLookAhead();
        } else if (view === 'trace') {
            document.getElementById('traceViewPanel')?.classList.remove('hidden');
            document.getElementById('tabTrace')?.classList.add('active-view');
            renderTraceTable();
        } else if (view === 'portfolio') {
            document.getElementById('portfolioViewPanel')?.classList.remove('hidden');
            document.getElementById('tabPortfolio')?.classList.add('active-view');
            renderPortfolio();
        }
    }

    function renderCalendarView() {
        if (!window.ScheduleCalendar) return;
        const tasks = [];
        gantt.eachTask(t => tasks.push(Object.assign({}, t)));
        ScheduleCalendar.init('scheduleCalendarContent', {
            getTasks: () => tasks,
        });
    }

    function renderLookAhead() {
        const tasks = [];
        gantt.eachTask(t => tasks.push(Object.assign({}, t)));
        const links = gantt.getLinks().map(l => Object.assign({}, l));
        const dataDate = CasePMSchedule.parseDate(document.getElementById('dataDateInput')?.value) || new Date();
        const horizon = parseInt(document.getElementById('lookaheadDaysInput')?.value, 10) || 14;
        scheduleSettings.data_date = CasePMSchedule.formatDate(dataDate);
        scheduleSettings.lookahead_days = horizon;

        const items = CasePMSchedule.computeLookAhead(tasks, links, { dataDate, horizonWorkDays: horizon, minDuration: 3 });
        const groups = CasePMSchedule.groupLookAheadByWbs(tasks, items);
        const container = document.getElementById('lookaheadContent');
        if (!container) return;

        if (!items.length) {
            container.innerHTML = '<p class="text-zinc-400 text-center py-12">No major activities in the look-ahead window.</p>';
            document.getElementById('lookaheadCount').textContent = '0';
            return;
        }

        let html = `<div class="mb-4 flex flex-wrap gap-4 text-sm text-zinc-400">
            <span>Data Date: <b class="text-white">${CasePMSchedule.formatDate(dataDate)}</b></span>
            <span>Horizon: <b class="text-white">${horizon} work days</b></span>
            <span>Activities: <b class="text-white">${items.length}</b></span>
        </div>`;

        groups.forEach((groupItems, wbsName) => {
            html += `<div class="mb-6"><h3 class="text-sm font-semibold text-emerald-400 uppercase mb-2">${wbsName}</h3>
                <table class="w-full text-sm bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                <thead><tr class="border-b border-zinc-800 bg-zinc-950 text-zinc-400 text-xs uppercase">
                    <th class="text-left px-4 py-2">Priority</th><th class="text-left px-4 py-2">Activity</th>
                    <th class="text-left px-4 py-2">Start</th><th class="text-left px-4 py-2">Finish</th>
                    <th class="text-left px-4 py-2">Resource</th><th class="text-left px-4 py-2">Why</th>
                </tr></thead><tbody class="divide-y divide-zinc-800">`;
            groupItems.forEach(item => {
                const priClass = item.priority === 'High' ? 'text-red-400' : item.priority === 'Medium' ? 'text-amber-400' : 'text-zinc-400';
                html += `<tr class="hover:bg-zinc-800/50">
                    <td class="px-4 py-2 ${priClass}">${item.priority}</td>
                    <td class="px-4 py-2 font-medium">${item.task.text}</td>
                    <td class="px-4 py-2 text-zinc-400">${item.start}</td>
                    <td class="px-4 py-2 text-zinc-400">${item.end || '—'}</td>
                    <td class="px-4 py-2">${item.task.resource || '—'}</td>
                    <td class="px-4 py-2 text-xs text-zinc-500">${item.reasons.join(' · ')}</td>
                </tr>`;
            });
            html += '</tbody></table></div>';
        });
        container.innerHTML = html;
        document.getElementById('lookaheadCount').textContent = items.length;
    }

    function renderTraceTable() {
        const tbody = document.getElementById('traceTableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        gantt.eachTask(t => {
            if (t.type === 'project') return;
            const critical = isTaskCritical(t);
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-zinc-800/50 border-b border-zinc-800';
            tr.innerHTML = `
                <td class="px-3 py-2 font-mono text-xs">${wbsCode(t)}</td>
                <td class="px-3 py-2 ${critical ? 'text-red-400' : ''}">${t.text}</td>
                <td class="px-3 py-2 text-center">${t.duration}</td>
                <td class="px-3 py-2">${formatDateSafe(t.start_date)}</td>
                <td class="px-3 py-2">${formatDateSafe(t.end_date)}</td>
                <td class="px-3 py-2 text-center">${Math.round((t.progress || 0) * 100)}%</td>
                <td class="px-3 py-2 text-xs">${predTemplate(t) || '—'}</td>
                <td class="px-3 py-2 text-center">${critical ? '<span class="text-red-400">Yes</span>' : '—'}</td>
                <td class="px-3 py-2">${t.resource || '—'}</td>`;
            tbody.appendChild(tr);
        });
    }

    function focusActivity(id) {
        switchScheduleView('gantt');
        gantt.selectTask(id);
        gantt.showTask(id);
        focusTimelineOnTask(id);
    }

    function countTasks() {
        let n = 0;
        gantt.eachTask(() => n++);
        return n;
    }

    function updateStatusBar() {
        const range = gantt.getSubtaskDates();
        const el = document.getElementById('scheduleStatusBar');
        if (!el) return;
        if (!range || !range.start_date) {
            el.innerHTML = '<span>Empty schedule — click <b>Activity</b> to add work or <b>Import</b> MS Project XML / Primavera XER</span>';
            return;
        }
        let critical = 0;
        let totalCpi = 0;
        let cpiCount = 0;
        const tasks = [];
        gantt.eachTask(t => {
            tasks.push(t);
            if (t.type !== 'project' && isTaskCritical(t)) critical++;
            if (t.cpi != null && !Number.isNaN(Number(t.cpi))) { totalCpi += Number(t.cpi); cpiCount++; }
        });
        const dataDate = document.getElementById('dataDateInput')?.value || scheduleSettings.data_date;
        const projectEvm = CasePMSchedule.computeProjectEVM ? CasePMSchedule.computeProjectEVM(tasks, dataDate) : null;
        const avgCpi = projectEvm?.cpi != null ? projectEvm.cpi : (cpiCount ? (totalCpi / cpiCount).toFixed(2) : '—');
        const blIdx = scheduleSettings.active_baseline_index;
        const blLabel = blIdx >= 0 && baselines[blIdx] ? baselines[blIdx].name : 'None';
        let viewRange = '';
        let calRange = '';
        if (ganttReady && rollingCalendarBounds) {
            calRange = `<span>Calendar: <b>${formatDateSafe(rollingCalendarBounds.start)}</b> – <b>${formatDateSafe(rollingCalendarBounds.end)}</b></span>`;
        }
        if (ganttReady && typeof gantt.getScrollState === 'function' && typeof gantt.dateFromPos === 'function') {
            const st = gantt.getScrollState();
            const viewW = getTimelineDomWidth();
            const left = st ? gantt.dateFromPos(st.x) : null;
            const right = st ? gantt.dateFromPos(st.x + viewW) : null;
            if (left && right) viewRange = `<span>Viewing: <b>${formatDateSafe(left)}</b> – <b>${formatDateSafe(right)}</b></span>`;
        }
        el.innerHTML = `
            <span>Start: <b>${formatDateSafe(range.start_date)}</b></span>
            <span>Finish: <b>${formatDateSafe(range.end_date)}</b></span>
            ${calRange}
            ${viewRange}
            <span>Activities: <b>${countTasks()}</b></span>
            <span>Critical: <b class="text-red-400">${critical}</b></span>
            <span>Baseline: <b class="text-sky-400">${blLabel}</b></span>
            <span>CPI: <b>${avgCpi}</b></span>
            <span>SPI: <b>${projectEvm?.spi ?? '—'}</b></span>
            <span>BAC: <b>${projectEvm?.bac != null ? '$' + Number(projectEvm.bac).toLocaleString() : '—'}</b></span>
            <span class="text-zinc-600">| Ctrl+Z undo · F2 edit · Del delete</span>`;
    }

    // ─── Import / Export / Print ───
    function exportJson() {
        const blob = new Blob([JSON.stringify(serializeSchedule(), null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `schedule_${CasePMSchedule.formatDate(new Date())}.json`;
        a.click();
    }

    function importFile(file) {
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                let payload;
                const content = e.target.result;
                if (typeof CasePMScheduleImport !== 'undefined') {
                    payload = CasePMScheduleImport.detectAndParse(file.name, content);
                } else {
                    payload = JSON.parse(content);
                }
                if (!payload.data) throw new Error('No tasks in file');
                loadSchedulePayload(payload);
                runSchedule();
                queueSave();
                showScheduleAlert(`Imported ${payload.data.length} items from ${payload.source || file.name}`, 'success');
                logActivity('Imported schedule', file.name);
            } catch (err) {
                showScheduleAlert('Import failed: ' + (err.message || err), 'error');
            }
        };
        reader.readAsText(file);
    }

    function runResourceLeveling() {
        if (!ganttReady || typeof CasePMSchedule.levelResources !== 'function') {
            return showScheduleAlert('Resource leveling engine not loaded.', 'error');
        }
        const tasks = [];
        gantt.eachTask(t => tasks.push(Object.assign({}, t)));
        const links = gantt.getLinks().map(l => Object.assign({}, l));
        const result = CasePMSchedule.levelResources(tasks, links, { lagDays: 0 });
        if (!result.updates.size) {
            const conflicts = CasePMSchedule.detectResourceConflicts(tasks);
            if (!conflicts.length) return showScheduleAlert('No resource conflicts detected.', 'info');
            return showScheduleAlert(`${conflicts.length} conflict(s) remain — tasks may lack float to shift.`, 'warning');
        }
        result.updates.forEach((patch, id) => {
            if (!gantt.isTaskExists(id)) return;
            const task = gantt.getTask(id);
            if (patch.start_date) task.start_date = toGanttDate(patch.start_date);
            if (patch.end_date) task.end_date = toGanttDate(patch.end_date);
            sanitizeTaskDates(task);
            gantt.refreshTask(id);
        });
        runSchedule({ skipScroll: true });
        pushUndoState();
        logActivity('Resource leveling', `Resolved ${result.conflictsResolved} conflict(s); ${result.remaining} remaining`);
        showScheduleAlert(`Leveled ${result.conflictsResolved} resource conflict(s). ${result.remaining} remaining.`, result.remaining ? 'warning' : 'success');
        showResourceLeveling();
    }

    function showResourceLeveling() {
        const dlg = document.getElementById('scheduleResourceModal');
        const list = document.getElementById('scheduleResourceConflictList');
        if (!dlg || !list) return runResourceLeveling();
        const tasks = [];
        gantt.eachTask(t => tasks.push(Object.assign({}, t)));
        const conflicts = CasePMSchedule.detectResourceConflicts ? CasePMSchedule.detectResourceConflicts(tasks) : [];
        if (!conflicts.length) {
            list.innerHTML = '<p class="text-zinc-400 text-sm">No resource overallocation detected. Assign resources to activities to enable leveling.</p>';
        } else {
            list.innerHTML = conflicts.map(c =>
                `<div class="px-3 py-2 rounded-md bg-zinc-800/80 border border-amber-800/50 text-sm">
                    <span class="text-amber-400 font-medium">${c.resource}</span>
                    <span class="text-zinc-400"> — </span>${c.textA || c.taskA} overlaps ${c.textB || c.taskB}
                </div>`
            ).join('');
        }
        dlg.showModal();
    }

    async function renderPortfolio() {
        const container = document.getElementById('portfolioContent');
        if (!container) return;
        container.innerHTML = '<p class="text-zinc-400 text-sm p-4">Loading portfolio schedules…</p>';
        try {
            const res = await fetch('/api/schedules/portfolio');
            if (!res.ok) throw new Error('Failed to load portfolio');
            const rows = await res.json();
            if (!rows.length) {
                container.innerHTML = '<p class="text-zinc-400 text-center py-12">No projects with schedules found.</p>';
                return;
            }
            let html = `<table class="w-full text-sm"><thead class="sticky top-0 bg-zinc-950 border-b border-zinc-800 text-xs uppercase text-zinc-400">
                <tr><th class="text-left px-3 py-2">Project</th><th class="text-left px-3 py-2">Start</th><th class="text-left px-3 py-2">Finish</th>
                <th class="text-center px-3 py-2">%</th><th class="text-center px-3 py-2">Critical</th><th class="text-center px-3 py-2">CPI</th><th class="text-center px-3 py-2">SPI</th><th class="text-center px-3 py-2">BAC</th></tr></thead><tbody>`;
            rows.forEach(r => {
                const cur = getSelectedProjectId() === r.project_id;
                html += `<tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer ${cur ? 'bg-emerald-950/20' : ''}" onclick="window.location.href='/schedule?project_id=${r.project_id}'">
                    <td class="px-3 py-2 font-medium">${r.project_number ? r.project_number + ' — ' : ''}${r.project_name}</td>
                    <td class="px-3 py-2">${r.start_date || '—'}</td>
                    <td class="px-3 py-2">${r.finish_date || '—'}</td>
                    <td class="px-3 py-2 text-center">${r.pct_complete != null ? r.pct_complete + '%' : '—'}</td>
                    <td class="px-3 py-2 text-center">${r.critical_count ?? '—'}</td>
                    <td class="px-3 py-2 text-center">${r.cpi != null ? r.cpi : '—'}</td>
                    <td class="px-3 py-2 text-center">${r.spi != null ? r.spi : '—'}</td>
                    <td class="px-3 py-2 text-center">${r.bac != null ? '$' + Number(r.bac).toLocaleString() : '—'}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<p class="text-red-400 text-sm p-4">${e.message || 'Could not load portfolio.'}</p>`;
        }
    }

    function hfCellFormattingDefaults(section, side) {
        const isHeader = section === 'header';
        return {
            font_size: isHeader ? (side === 'center' ? 16 : 11) : 9,
            color: isHeader ? '#111111' : '#444444',
            logo_height_pt: isHeader ? 42 : 24
        };
    }

    function defaultHeaderFooterSettings() {
        const mkSection = (centerText, rightText) => {
            const section = {};
            ['left', 'center', 'right'].forEach(side => {
                const fmt = hfCellFormattingDefaults('header', side);
                section[side + '_text'] = side === 'center' ? centerText : (side === 'right' ? rightText : '');
                section[side + '_logo'] = null;
                section[side + '_font_size'] = fmt.font_size;
                section[side + '_color'] = fmt.color;
                section[side + '_logo_height_pt'] = fmt.logo_height_pt;
            });
            return section;
        };
        const mkFooter = () => {
            const section = {};
            ['left', 'center', 'right'].forEach(side => {
                const fmt = hfCellFormattingDefaults('footer', side);
                section[side + '_text'] = side === 'center' ? 'Case PM · Project Controls' : (side === 'right' ? 'Printed {printed}' : '');
                section[side + '_logo'] = null;
                section[side + '_font_size'] = fmt.font_size;
                section[side + '_color'] = fmt.color;
                section[side + '_logo_height_pt'] = fmt.logo_height_pt;
            });
            return section;
        };
        return {
            include_header: true,
            include_footer: true,
            show_meta_row: true,
            header_band_height_pt: 80,
            footer_band_height_pt: 32,
            header: mkSection('Project Schedule', '{project}'),
            footer: mkFooter()
        };
    }

    function ensureHeaderFooterSettings() {
        if (!scheduleSettings.print_settings) scheduleSettings.print_settings = {};
        const defaults = defaultHeaderFooterSettings();
        if (!scheduleSettings.print_settings.header_footer) {
            scheduleSettings.print_settings.header_footer = defaults;
        } else {
            const hf = scheduleSettings.print_settings.header_footer;
            ['header', 'footer'].forEach(section => {
                hf[section] = Object.assign({}, defaults[section], hf[section] || {});
                ['left', 'center', 'right'].forEach(side => {
                    const fmt = hfCellFormattingDefaults(section, side);
                    if (hf[section][side + '_logo'] === undefined) hf[section][side + '_logo'] = null;
                    if (hf[section][side + '_text'] === undefined) hf[section][side + '_text'] = defaults[section][side + '_text'] || '';
                    if (hf[section][side + '_font_size'] == null) hf[section][side + '_font_size'] = fmt.font_size;
                    if (!hf[section][side + '_color']) hf[section][side + '_color'] = fmt.color;
                    if (hf[section][side + '_logo_height_pt'] == null) hf[section][side + '_logo_height_pt'] = fmt.logo_height_pt;
                });
            });
            if (hf.header_band_height_pt == null) hf.header_band_height_pt = defaults.header_band_height_pt;
            if (hf.footer_band_height_pt == null) hf.footer_band_height_pt = defaults.footer_band_height_pt;
        }
        return scheduleSettings.print_settings.header_footer;
    }

    function expandPrintTokens(text, ctx) {
        if (!text) return '';
        return String(text)
            .replace(/\{project\}/gi, ctx.projectName || '')
            .replace(/\{project_number\}/gi, ctx.projectNumber || '')
            .replace(/\{data_date\}/gi, ctx.dataDate || '')
            .replace(/\{printed\}/gi, ctx.printed || '')
            .replace(/\{schedule_start\}/gi, ctx.scheduleStart || '')
            .replace(/\{schedule_finish\}/gi, ctx.scheduleFinish || '')
            .replace(/\{activities\}/gi, String(ctx.activities ?? ''))
            .replace(/\{critical\}/gi, String(ctx.critical ?? ''));
    }

    function buildPrintHfCell(cfg, side, ctx, section) {
        const parts = [];
        const fontSize = cfg[side + '_font_size'] || (section === 'header' ? 11 : 9);
        const color = cfg[side + '_color'] || (section === 'header' ? '#111111' : '#444444');
        const logoH = cfg[side + '_logo_height_pt'] || (section === 'header' ? 42 : 24);
        const logo = cfg[side + '_logo'];
        if (logo) {
            parts.push(`<img src="${logo}" alt="" class="sched-print-hf-logo" style="max-height:${logoH}pt">`);
        }
        const text = expandPrintTokens(cfg[side + '_text'], ctx);
        if (text) {
            parts.push(`<span class="sched-print-hf-text" style="font-size:${fontSize}pt;color:${color}">${text}</span>`);
        }
        return parts.join('') || '&nbsp;';
    }

    function buildPrintHeaderFooterHtml(section, hf, ctx) {
        const cfg = hf[section];
        const bandClass = section === 'header' ? 'sched-print-hf-header' : 'sched-print-hf-footer';
        const bandH = section === 'header' ? (hf.header_band_height_pt || 80) : (hf.footer_band_height_pt || 32);
        return `<div class="sched-print-hf ${bandClass}" style="min-height:${bandH}pt">
            <div class="sched-print-hf-col sched-print-hf-left">${buildPrintHfCell(cfg, 'left', ctx, section)}</div>
            <div class="sched-print-hf-col sched-print-hf-center">${buildPrintHfCell(cfg, 'center', ctx, section)}</div>
            <div class="sched-print-hf-col sched-print-hf-right">${buildPrintHfCell(cfg, 'right', ctx, section)}</div>
        </div>`;
    }

    function hfFmtId(side, prop) {
        return 'hfHdr' + side.charAt(0).toUpperCase() + side.slice(1) + prop;
    }

    function loadHeaderFooterForm(hf) {
        document.getElementById('hfIncludeHeader').checked = hf.include_header !== false;
        document.getElementById('hfIncludeFooter').checked = hf.include_footer !== false;
        document.getElementById('hfShowMetaRow').checked = hf.show_meta_row !== false;
        document.getElementById('hfHeaderBandHeight').value = hf.header_band_height_pt || 80;
        document.getElementById('hfFooterBandHeight').value = hf.footer_band_height_pt || 32;
        document.getElementById('hfHeaderLeft').value = hf.header.left_text || '';
        document.getElementById('hfHeaderCenter').value = hf.header.center_text || 'Project Schedule';
        document.getElementById('hfHeaderRight').value = hf.header.right_text || '{project}';
        document.getElementById('hfFooterLeft').value = hf.footer.left_text || '';
        document.getElementById('hfFooterCenter').value = hf.footer.center_text || '';
        document.getElementById('hfFooterRight').value = hf.footer.right_text || '';
        ['left', 'center', 'right'].forEach(side => {
            const fmt = hf.header;
            const fs = document.getElementById(hfFmtId(side, 'FontSize'));
            const fc = document.getElementById(hfFmtId(side, 'Color'));
            const lh = document.getElementById(hfFmtId(side, 'LogoHeight'));
            if (fs) fs.value = String(fmt[side + '_font_size'] || 11);
            if (fc) fc.value = fmt[side + '_color'] || '#111111';
            if (lh) lh.value = String(fmt[side + '_logo_height_pt'] || 42);
        });
        syncHeaderFooterLogoPreviews(hf);
    }

    function syncHeaderFooterLogoPreviews(hf) {
        ['left', 'center', 'right'].forEach(side => {
            const img = document.getElementById('hfHeaderLogoPreview' + side.charAt(0).toUpperCase() + side.slice(1));
            const logo = hf.header[side + '_logo'];
            if (!img) return;
            if (logo) {
                img.src = logo;
                img.classList.remove('hidden');
            } else {
                img.removeAttribute('src');
                img.classList.add('hidden');
            }
        });
    }

    function showHeaderFooterSetup() {
        const dlg = document.getElementById('scheduleHeaderFooterModal');
        if (!dlg) return;
        loadHeaderFooterForm(ensureHeaderFooterSettings());
        dlg.showModal();
    }

    function onHeaderLogoSelected(file, side) {
        if (!file || !side) return;
        const reader = new FileReader();
        reader.onload = () => {
            const hf = ensureHeaderFooterSettings();
            hf.header[side + '_logo'] = reader.result;
            syncHeaderFooterLogoPreviews(hf);
        };
        reader.readAsDataURL(file);
    }

    function clearHeaderLogo(side) {
        const hf = ensureHeaderFooterSettings();
        hf.header[(side || 'left') + '_logo'] = null;
        syncHeaderFooterLogoPreviews(hf);
        const input = document.getElementById('hfLogoInput' + (side ? side.charAt(0).toUpperCase() + side.slice(1) : 'Left'));
        if (input) input.value = '';
    }

    function saveHeaderFooterSettings() {
        const hf = ensureHeaderFooterSettings();
        hf.include_header = document.getElementById('hfIncludeHeader')?.checked !== false;
        hf.include_footer = document.getElementById('hfIncludeFooter')?.checked !== false;
        hf.show_meta_row = document.getElementById('hfShowMetaRow')?.checked !== false;
        hf.header_band_height_pt = Math.max(48, Math.min(160, parseInt(document.getElementById('hfHeaderBandHeight')?.value, 10) || 80));
        hf.footer_band_height_pt = Math.max(20, Math.min(80, parseInt(document.getElementById('hfFooterBandHeight')?.value, 10) || 32));
        hf.header.left_text = document.getElementById('hfHeaderLeft')?.value || '';
        hf.header.center_text = document.getElementById('hfHeaderCenter')?.value || '';
        hf.header.right_text = document.getElementById('hfHeaderRight')?.value || '';
        hf.footer.left_text = document.getElementById('hfFooterLeft')?.value || '';
        hf.footer.center_text = document.getElementById('hfFooterCenter')?.value || '';
        hf.footer.right_text = document.getElementById('hfFooterRight')?.value || '';
        ['left', 'center', 'right'].forEach(side => {
            hf.header[side + '_font_size'] = parseInt(document.getElementById(hfFmtId(side, 'FontSize'))?.value, 10) || 11;
            hf.header[side + '_color'] = document.getElementById(hfFmtId(side, 'Color'))?.value || '#111111';
            hf.header[side + '_logo_height_pt'] = Math.max(12, Math.min(120, parseInt(document.getElementById(hfFmtId(side, 'LogoHeight'))?.value, 10) || 42));
        });
        scheduleSettings.print_settings.include_footer = hf.include_footer;
        queueSave();
        document.getElementById('scheduleHeaderFooterModal')?.close();
        showScheduleAlert('Header and footer settings saved. They apply on the next print.', 'success');
    }

    function updatePrintColumnToggleUI() {
        const ps = scheduleSettings.print_settings || {};
        const wbsOn = ps.print_hide_wbs !== true;
        const idOn = ps.print_hide_id !== true;
        document.getElementById('printWbsOn')?.classList.toggle('active-tool', wbsOn);
        document.getElementById('printWbsOff')?.classList.toggle('active-tool', !wbsOn);
        document.getElementById('printIdOn')?.classList.toggle('active-tool', idOn);
        document.getElementById('printIdOff')?.classList.toggle('active-tool', !idOn);
    }

    function setPrintColumnToggle(which, show) {
        if (!scheduleSettings.print_settings) scheduleSettings.print_settings = {};
        if (which === 'wbs') scheduleSettings.print_settings.print_hide_wbs = !show;
        if (which === 'id') scheduleSettings.print_settings.print_hide_id = !show;
        updatePrintColumnToggleUI();
        const vis = getPrintVisibleGridColumns(scheduleSettings.print_settings);
        const hint = document.getElementById('printVisibleColHint');
        if (hint) {
            const names = vis.map(v => v.col.label || v.col.name).join(', ');
            hint.textContent = vis.length
                ? `${vis.length} column(s) will print: ${names}`
                : 'No fully visible columns — drag chart divider or scroll grid.';
        }
    }

    function showPrintSetup() {
        const dlg = document.getElementById('schedulePrintModal');
        if (!dlg) return printGantt();
        const ps = scheduleSettings.print_settings || {};
        document.getElementById('printIncludeSummary').checked = ps.include_summary !== false;
        document.getElementById('printIncludeTable').checked = ps.include_activity_table !== false;
        document.getElementById('printIncludeInlineBars').checked = ps.include_inline_bars !== false;
        document.getElementById('printIncludeChart').checked = !!ps.include_schedule_chart;
        document.getElementById('printIncludeEvm').checked = !!ps.include_evm;
        document.getElementById('printIncludeFooter').checked = !!ps.include_footer;
        updatePrintColumnToggleUI();
        const vis = getPrintVisibleGridColumns(ps);
        const hint = document.getElementById('printVisibleColHint');
        if (hint) {
            const names = vis.map(v => v.col.label || v.col.name).join(', ');
            hint.textContent = vis.length
                ? `${vis.length} column(s) will print: ${names}`
                : 'No fully visible columns — drag chart divider or scroll grid.';
        }
        dlg.showModal();
    }

    function savePrintSettings() {
        const hf = ensureHeaderFooterSettings();
        const prev = scheduleSettings.print_settings || {};
        scheduleSettings.print_settings = {
            ...prev,
            include_summary: document.getElementById('printIncludeSummary')?.checked !== false,
            include_activity_table: document.getElementById('printIncludeTable')?.checked !== false,
            include_inline_bars: document.getElementById('printIncludeInlineBars')?.checked !== false,
            include_schedule_chart: document.getElementById('printIncludeChart')?.checked === true,
            include_evm: document.getElementById('printIncludeEvm')?.checked === true,
            include_footer: document.getElementById('printIncludeFooter')?.checked === true,
            print_hide_wbs: scheduleSettings.print_settings?.print_hide_wbs === true,
            print_hide_id: scheduleSettings.print_settings?.print_hide_id === true,
            header_footer: hf
        };
        hf.include_footer = scheduleSettings.print_settings.include_footer;
        queueSave();
        document.getElementById('schedulePrintModal')?.close();
        printGantt();
    }

    function buildPrintTimescale(startMs, span) {
        const ticks = 10;
        let cells = '';
        for (let i = 0; i <= ticks; i++) {
            const pct = (i / ticks) * 100;
            const d = new Date(startMs + (span * i / ticks));
            cells += `<span class="print-ts-label" style="left:${pct}%">${CasePMSchedule.formatDate(d)}</span>`;
        }
        return `<div class="print-timescale">${cells}</div>`;
    }

    function buildPrintSheet() {
        const ps = scheduleSettings.print_settings || {};
        const meta = getProjectMeta();
        const range = gantt.getSubtaskDates();
        const dataDate = document.getElementById('dataDateInput')?.value || scheduleSettings.data_date || CasePMSchedule.formatDate(new Date());
        const printed = new Date().toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
        const DAY_MS = 86400000;
        const PRINT_CHART_PAD_DAYS = 2;
        const scheduleStartMs = range?.start_date ? toGanttDate(range.start_date)?.getTime() : Date.now();
        const scheduleEndMs = range?.end_date ? toGanttDate(range.end_date)?.getTime() : scheduleStartMs + DAY_MS * 30;
        const startMs = scheduleStartMs - PRINT_CHART_PAD_DAYS * DAY_MS;
        const endMs = scheduleEndMs + PRINT_CHART_PAD_DAYS * DAY_MS;
        const span = Math.max(endMs - startMs, DAY_MS);
        const timescale = buildPrintTimescale(startMs, span);
        const showInlineBars = ps.include_inline_bars !== false;
        const showTable = ps.include_activity_table !== false;
        const showChart = ps.include_schedule_chart === true;
        const showEvm = ps.include_evm === true;
        const showSummary = ps.include_summary !== false;
        const visibleCols = showTable ? getPrintVisibleGridColumns(ps) : [];
        const hostW = document.getElementById('gantt_here')?.clientWidth || 1000;
        const exposedW = getExposedGridWidth();
        const timelineW = getTimelineWidth();
        const splitTotal = Math.max(exposedW + timelineW, 1);
        const textTablePct = showInlineBars ? (exposedW / splitTotal) * 100 : 100;
        const barTablePct = showInlineBars ? (timelineW / splitTotal) * 100 : 0;
        const visibleTextW = visibleCols.reduce((s, v) => s + v.width, 0) || 1;

        let critical = 0;
        const tasks = [];
        gantt.eachTask(t => {
            tasks.push(t);
            if (t.type !== 'project' && isTaskCritical(t)) critical++;
        });
        const projectEvm = CasePMSchedule.computeProjectEVM
            ? CasePMSchedule.computeProjectEVM(tasks, dataDate)
            : null;

        let rows = '';
        const rowMap = new Map();
        let rowIdx = 0;
        if (showTable && visibleCols.length) {
            gantt.eachTask(t => {
                rowMap.set(t.id, rowIdx++);
                const ts = toGanttDate(t.start_date)?.getTime() || startMs;
                const te = toGanttDate(t.end_date)?.getTime() || ts;
                const left = Math.max(0, ((ts - startMs) / span) * 100);
                const width = Math.max(t.type === 'milestone' ? 0.8 : 1.2, ((te - ts) / span) * 100);
                const color = resolveBarColor(t);
                const level = t.$level || 0;
                const dateLabel = `${formatDateSafe(t.start_date)} – ${formatDateSafe(t.end_date)}`;
                const cells = visibleCols.map(({ col, width: colW }) => {
                    const pct = ((colW / visibleTextW) * textTablePct).toFixed(3);
                    const align = col.align === 'center' ? ' c' : '';
                    const nameCls = col.name === 'text' ? ' print-name' : '';
                    const indent = col.name === 'text' ? ` style="padding-left:${4 + level * 10}px;width:${pct}%"` : ` style="width:${pct}%"`;
                    let content = renderPrintCellHtml(t, col);
                    if (col.name === 'progress' && !content.includes('%')) content += '%';
                    return `<td class="print-col-${col.name}${nameCls}${align}"${indent}>${content}</td>`;
                }).join('');
                const evmExtra = showEvm && !visibleCols.some(v => v.col.name === 'cpi')
                    ? `<td class="c print-col-cpi" style="width:${(textTablePct / visibleCols.length * 0.5).toFixed(2)}%">${t.cpi != null ? t.cpi : '—'}</td><td class="c print-col-spi" style="width:${(textTablePct / visibleCols.length * 0.5).toFixed(2)}%">${t.spi != null ? t.spi : '—'}</td>`
                    : '';
                const barCell = showInlineBars
                    ? `<td class="print-bar-cell" style="width:${barTablePct.toFixed(2)}%"><div class="print-bar-dates">${dateLabel}</div><div class="print-bar-track"><div class="print-bar" style="left:${left}%;width:${width}%;background:${color}"></div></div></td>`
                    : '';
                rows += `<tr class="${t.type === 'project' ? 'print-summary' : ''}">${cells}${evmExtra}${barCell}</tr>`;
            });
        }

        let chartBlock = '';
        if (showChart && rowIdx) {
            const chartH = Math.max(120, rowIdx * 18);
            let chartBars = '';
            gantt.eachTask(t => {
                const i = rowMap.get(t.id);
                if (i == null) return;
                const ts = toGanttDate(t.start_date)?.getTime() || startMs;
                const te = toGanttDate(t.end_date)?.getTime() || ts;
                const x = Math.max(0, ((ts - startMs) / span) * 100);
                const w = Math.max(t.type === 'milestone' ? 0.6 : 1, ((te - ts) / span) * 100);
                const y = ((i + 0.5) / rowIdx) * 100;
                chartBars += `<rect x="${x}" y="${y - 1.2}" width="${w}" height="2.4" fill="${resolveBarColor(t)}" rx="0.3"/>`;
            });
            let chartLines = '';
            gantt.getLinks().forEach(link => {
                if (!gantt.isTaskExists(link.source) || !gantt.isTaskExists(link.target)) return;
                const src = gantt.getTask(link.source);
                const tgt = gantt.getTask(link.target);
                const si = rowMap.get(link.source);
                const ti = rowMap.get(link.target);
                if (si == null || ti == null) return;
                const x1 = ((toGanttDate(src.end_date)?.getTime() || startMs) - startMs) / span * 100;
                const x2 = ((toGanttDate(tgt.start_date)?.getTime() || startMs) - startMs) / span * 100;
                chartLines += `<line x1="${x1}" y1="${(si + 0.5) / rowIdx * 100}" x2="${x2}" y2="${(ti + 0.5) / rowIdx * 100}" stroke="#444" stroke-width="0.4"/>`;
            });
            chartBlock = `<div class="print-gantt-chart"><h3 class="print-chart-title">Schedule Chart</h3>${timescale}
                <svg class="print-chart-svg" viewBox="0 0 100 100" preserveAspectRatio="none" style="height:${chartH}px">${chartLines}${chartBars}</svg></div>`;
        }

        const evmHeader = showEvm && !visibleCols.some(v => v.col.name === 'cpi')
            ? `<th class="print-col-cpi c">CPI</th><th class="print-col-spi c">SPI</th>` : '';
        const barHeader = showInlineBars ? `<th class="print-bar-cell" style="width:${barTablePct.toFixed(2)}%">Schedule Bars</th>` : '';
        const colHeaders = visibleCols.map(({ col, width: colW }) => {
            const pct = ((colW / visibleTextW) * textTablePct).toFixed(3);
            const label = col.label || col.name || '';
            const align = col.align === 'center' ? ' c' : '';
            return `<th class="print-col-${col.name}${align}" style="width:${pct}%">${label}</th>`;
        }).join('');
        const textColCount = visibleCols.length + (evmHeader ? 2 : 0);
        const tsRow = showInlineBars && textColCount
            ? `<tr class="print-ts-row"><td colspan="${textColCount}"></td><td class="print-bar-cell">${timescale}</td></tr>` : '';
        const evmSummary = showEvm && projectEvm ? `
            <div class="sched-print-evm-grid mt-2 text-xs">
                <div><span class="sched-print-label">BAC</span><strong>$${projectEvm.bac.toLocaleString()}</strong></div>
                <div><span class="sched-print-label">BCWP</span><strong>$${projectEvm.bcwp.toLocaleString()}</strong></div>
                <div><span class="sched-print-label">ACWP</span><strong>$${projectEvm.acwp.toLocaleString()}</strong></div>
                <div><span class="sched-print-label">CPI</span><strong>${projectEvm.cpi ?? '—'}</strong></div>
                <div><span class="sched-print-label">SPI</span><strong>${projectEvm.spi ?? '—'}</strong></div>
                <div><span class="sched-print-label">EAC</span><strong>$${projectEvm.eac.toLocaleString()}</strong></div>
                <div><span class="sched-print-label">VAC</span><strong>$${projectEvm.vac.toLocaleString()}</strong></div>
            </div>` : '';

        const headerBlock = (() => {
            const hf = ensureHeaderFooterSettings();
            const ctx = {
                projectName: meta.name,
                projectNumber: meta.number || '',
                dataDate: formatDateSafe(dataDate),
                printed,
                scheduleStart: range?.start_date ? formatDateSafe(range.start_date) : '—',
                scheduleFinish: range?.end_date ? formatDateSafe(range.end_date) : '—',
                activities: countTasks(),
                critical
            };
            let html = '';
            if (hf.include_header !== false) {
                html += buildPrintHeaderFooterHtml('header', hf, ctx);
            }
            if (showSummary && hf.show_meta_row !== false) {
                html += `
            <div class="schedule-print-header sched-print-meta-block">
                <div class="sched-print-meta-grid">
                    <div><span class="sched-print-label">Project</span><strong>${meta.name}</strong></div>
                    <div><span class="sched-print-label">Project No.</span><strong>${meta.number || '—'}</strong></div>
                    <div><span class="sched-print-label">Data Date</span><strong>${formatDateSafe(dataDate)}</strong></div>
                    <div><span class="sched-print-label">Printed</span><strong>${printed}</strong></div>
                    <div><span class="sched-print-label">Schedule Start</span><strong>${range?.start_date ? formatDateSafe(range.start_date) : '—'}</strong></div>
                    <div><span class="sched-print-label">Schedule Finish</span><strong>${range?.end_date ? formatDateSafe(range.end_date) : '—'}</strong></div>
                    <div><span class="sched-print-label">Activities</span><strong>${countTasks()}</strong></div>
                    <div><span class="sched-print-label">Critical</span><strong>${critical}</strong></div>
                </div>${evmSummary}
            </div>`;
            } else if (showSummary && !hf.include_header) {
                html += `
            <div class="schedule-print-header">
                <div class="sched-print-brand">Case PM · Project Controls</div>
                <h1 class="sched-print-title">Project Schedule</h1>
                <div class="sched-print-meta-grid">
                    <div><span class="sched-print-label">Project</span><strong>${meta.name}</strong></div>
                    <div><span class="sched-print-label">Project No.</span><strong>${meta.number || '—'}</strong></div>
                    <div><span class="sched-print-label">Data Date</span><strong>${formatDateSafe(dataDate)}</strong></div>
                    <div><span class="sched-print-label">Printed</span><strong>${printed}</strong></div>
                    <div><span class="sched-print-label">Schedule Start</span><strong>${range?.start_date ? formatDateSafe(range.start_date) : '—'}</strong></div>
                    <div><span class="sched-print-label">Schedule Finish</span><strong>${range?.end_date ? formatDateSafe(range.end_date) : '—'}</strong></div>
                    <div><span class="sched-print-label">Activities</span><strong>${countTasks()}</strong></div>
                    <div><span class="sched-print-label">Critical</span><strong>${critical}</strong></div>
                </div>${evmSummary}
            </div>`;
            }
            return html;
        })();

        const tableBlock = showTable && visibleCols.length ? `
            <table class="schedule-print-table schedule-print-table-compact schedule-print-table-visible-cols">
                <thead><tr>
                    ${colHeaders}${evmHeader}${barHeader}
                </tr>${tsRow}</thead>
                <tbody>${rows}</tbody>
            </table>` : '';

        const hf = ensureHeaderFooterSettings();
        const footerBlock = (() => {
            if (hf.include_footer === false) return '';
            const ctx = {
                projectName: meta.name,
                projectNumber: meta.number || '',
                dataDate: formatDateSafe(dataDate),
                printed,
                scheduleStart: range?.start_date ? formatDateSafe(range.start_date) : '—',
                scheduleFinish: range?.end_date ? formatDateSafe(range.end_date) : '—',
                activities: countTasks(),
                critical
            };
            return buildPrintHeaderFooterHtml('footer', hf, ctx);
        })();

        const sheet = document.getElementById('schedulePrintSheet');
        if (!sheet) return;
        sheet.innerHTML = headerBlock + tableBlock + chartBlock + footerBlock;
        sheet.dataset.printFooter = hf.include_footer !== false ? '1' : '0';
    }

    function printGantt() {
        buildPrintSheet();
        const sheet = document.getElementById('schedulePrintSheet');
        if (!sheet || !sheet.innerHTML.trim()) {
            showScheduleAlert('Nothing to print — add activities first.', 'warning');
            return;
        }
        const deliver = () => {
            document.body.classList.toggle('printing-gantt-show-footer', sheet.dataset.printFooter === '1');
            document.body.classList.add('printing-gantt');
            setTimeout(() => {
                window.print();
                setTimeout(() => document.body.classList.remove('printing-gantt', 'printing-gantt-show-footer'), 600);
            }, 150);
        };
        if (typeof CasePMOutput !== 'undefined') {
            const html = CasePMOutput.wrapHtmlDocument('Schedule Gantt', sheet.innerHTML);
            CasePMOutput.deliverHtml({
                title: 'Schedule Gantt',
                html,
                filenameBase: 'Schedule_Gantt',
                sourceModule: 'schedule',
                systemFolderKey: 'printed-output',
                onPrint: async () => deliver(),
            });
            return;
        }
        deliver();
    }

    function printLookAhead() {
        renderLookAhead();
        const panel = document.getElementById('lookaheadViewPanel');
        const deliver = () => {
            document.body.classList.add('printing-lookahead');
            panel?.classList.add('print-active');
            setTimeout(() => {
                window.print();
                setTimeout(() => {
                    document.body.classList.remove('printing-lookahead');
                    panel?.classList.remove('print-active');
                }, 500);
            }, 200);
        };
        if (typeof CasePMOutput !== 'undefined' && panel) {
            const html = CasePMOutput.wrapHtmlDocument('Schedule Look-Ahead', panel.innerHTML);
            CasePMOutput.deliverHtml({
                title: 'Schedule Look-Ahead',
                html,
                filenameBase: 'Schedule_LookAhead',
                sourceModule: 'schedule',
                systemFolderKey: 'printed-output',
                onPrint: async () => deliver(),
            });
            return;
        }
        deliver();
    }

    function showAllOptionalColumns() {
        if (typeof CasePMScheduleFields === 'undefined') {
            return showScheduleAlert('Field catalog not loaded.', 'error');
        }
        const existing = new Set((gantt.config.columns || []).map(c => c.name));
        let added = 0;
        CasePMScheduleFields.FIELDS.forEach(f => {
            const key = f.map_to || f.id;
            if (existing.has(key) || f.type === 'successors') return;
            hiddenColumns = hiddenColumns.filter(n => n !== key);
            if (!customColumns.find(c => (c.map_to || c.name) === key)) {
                customColumns.push({ name: key, map_to: key, label: f.label, width: 92 });
                added++;
            }
        });
        gantt.config.columns = buildColumnConfig();
        updateGridWidth();
        gantt.render();
        queueSave();
        showScheduleAlert(added ? `Added ${added} optional columns. Drag column edges to resize.` : 'All optional columns are already visible.', 'success');
    }

    function showKeyboardShortcuts() {
        const dlg = document.getElementById('scheduleShortcutsModal');
        if (!dlg) return showScheduleAlert('F2 edit · Del delete · Ctrl+D duplicate · Ctrl+C/V copy/paste · Ctrl+Z undo · ? this help', 'info');
        dlg.showModal();
    }

    function showFeaturesChecklist() {
        showScheduleAlert('All schedule features are installed.', 'success');
    }

    function showScheduleAlert(message, type) {
        const colors = { success: 'text-emerald-400', warning: 'text-amber-400', error: 'text-red-400', info: 'text-sky-400' };
        const dlg = document.createElement('dialog');
        dlg.className = 'schedule-modal-dialog bg-zinc-900 border border-zinc-700 rounded-md p-0 w-full max-w-md shadow-2xl';
        dlg.innerHTML = `<div class="px-5 py-3 border-b border-zinc-700 ${colors[type] || 'text-sky-400'} font-semibold text-sm">${type || 'Notice'}</div>
            <div class="px-5 py-4 text-sm text-zinc-200">${message}</div>
            <div class="px-5 py-3 border-t border-zinc-700 flex justify-end">
                <button class="schedule-toolbar-btn px-5 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm">OK</button>
            </div>`;
        document.body.appendChild(dlg);
        dlg.querySelector('button').onclick = () => { dlg.close(); dlg.remove(); };
        dlg.showModal();
    }

    async function init() {
        if (typeof gantt === 'undefined') {
            setSaveStatus('Gantt library failed to load — refresh page');
            return;
        }
        syncScheduleProjectContext();
        configureGantt();
        await loadSchedule();
        runSchedule({ skipScroll: true });
        applyRollingCalendarRange(true);
        applyTimescaleScales(scheduleSettings.timescale || 'day');
        updateRowHeightsForLabels();
        gantt.render();
        requestAnimationFrame(() => {
            syncScheduleProjectContext();
            applyChartOverlay();
            scrollToToday();
            queueGridHeaderSync();
        });
        switchScheduleView('gantt');
        updateAlignToolbarButtons();
        const pid = getSelectedProjectId();
        if (pid) localStorage.setItem('casepm_current_project_id', String(pid));

        document.getElementById('dataDateInput')?.addEventListener('change', () => {
            scheduleSettings.data_date = document.getElementById('dataDateInput').value;
            updateDataDateMarker();
            gantt.render();
            queueSave();
        });

        if (window.ScheduleExtras) {
            ScheduleExtras.init({
                getPanMetrics: getTimelinePanMetrics,
                getScrollX: readTimelineScrollX,
                setScrollX: setTimelineScrollX,
                getTimelineWidth: getTimelineDomWidth,
                getSettings: () => scheduleSettings,
                queueSave,
                getTasks: () => { const t = []; gantt.eachTask(x => t.push(x)); return t; },
                getDataDate: () => document.getElementById('dataDateInput')?.value || scheduleSettings.data_date,
                getSubtaskDates: () => gantt.getSubtaskDates(),
                parseDate: d => CasePMSchedule.parseDate(d),
                daysBetween: (a, b) => CasePMSchedule.calendarDaysBetween(a, b),
                alert: showScheduleAlert
            });
            requestAnimationFrame(() => {
                applyChartOverlay();
                scrollToToday();
                refreshTimelinePanBar();
                setTimeout(() => { applyChartOverlay(); refreshTimelinePanBar(); }, 250);
            });
        }
    }

    window.ScheduleApp = {
        init, addActivity, duplicateSelected, deleteSelected, indentSelected, outdentSelected, openActivityDetail,
        linkSelected, unlinkSelected, zoomGantt, setTimescale, showDisplaySettings, saveDisplaySettings,
        wbsCode, applyPredecessorString,
        toggleCriticalPath, toggleCriticalFilter, setBaseline, showBaselineManager, activateBaseline, deleteBaseline,
        undo, redo, fitScheduleView, scrollToToday, panTimeline, resetTimelineCalendar, filterTasks, exportCsv, focusTimelineOnTask,
        runSchedule, switchScheduleView, renderCalendarView, renderLookAhead, focusActivity, sortByStartDate, exportXer, exportMsProjectXml,
        showAllOptionalColumns, showFeaturesChecklist, showKeyboardShortcuts,
        exportJson, importFile, printGantt, printLookAhead, showPrintSetup, savePrintSettings, setPrintColumnToggle,
        showHeaderFooterSetup, saveHeaderFooterSettings, onHeaderLogoSelected, clearHeaderLogo,
        saveSchedule,
        loadSchedule, clearSchedule, showColumnManager, showAddColumnDialog, removeColumn, addFieldColumn, queueSave,
        setGridCellAlignH, setGridCellAlignV, setGridFontSize, setGridRowHeight, saveBarSettingsAsDefaults,
        runResourceLeveling, showResourceLeveling, renderPortfolio, resetColumnWidths, renderBaselineComparison,
        restoreBaseline, toggleScheduleTheme: () => window.ScheduleExtras?.toggleTheme(),
        showResourceHistogram: () => window.ScheduleExtras?.showResourceHistogram(),
        showEvmScurve: () => window.ScheduleExtras?.showEvmScurve()
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
