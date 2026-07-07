/* Case PM — Primavera / MS Project style scheduling application */
(function () {
    'use strict';

    const STORAGE_KEY = 'casepm_schedule_v4';
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
        'baseline_start', 'baseline_finish', 'start_variance', 'finish_variance'
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
        timescale: 'week',
        default_bar_color: '#3b82f6',
        critical_bar_color: '#ef4444',
        progress_bar_color: '#f59e0b',
        complete_bar_color: '#71717a',
        milestone_color: '#8b5cf6',
        link_color: '#94a3b8',
        link_width: 2,
        active_baseline_index: -1,
        show_baseline_bars: true
    };

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
        if (!list) return;
        if (!baselines.length) {
            list.innerHTML = '<p class="text-zinc-500 text-sm p-2">No baselines saved. Click <b>Set Baseline</b> to capture the current schedule.</p>';
        } else {
            list.innerHTML = baselines.map((b, i) => {
                const active = scheduleSettings.active_baseline_index === i;
                const count = (b.data || []).length;
                return `<div class="flex items-center justify-between gap-2 px-3 py-2 rounded-md border ${active ? 'border-emerald-600 bg-emerald-950/30' : 'border-zinc-700 bg-zinc-800/80'}">
                    <div class="min-w-0">
                        <div class="text-sm font-medium truncate">${b.name}</div>
                        <div class="text-xs text-zinc-500">${count} activities · ${new Date(b.created).toLocaleString()}</div>
                    </div>
                    <div class="flex gap-1 flex-shrink-0">
                        <button type="button" class="schedule-toolbar-btn text-xs px-2 py-1" onclick="ScheduleApp.activateBaseline(${i})">${active ? 'Active' : 'Use'}</button>
                        <button type="button" class="schedule-toolbar-btn text-xs px-2 py-1 text-red-400" onclick="ScheduleApp.deleteBaseline(${i})">Delete</button>
                    </div>
                </div>`;
            }).join('');
        }
        dlg.showModal();
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


    function getProjectMeta() {
        const ctx = document.getElementById('scheduleProjectContext');
        if (ctx && ctx.dataset.projectId) {
            const number = ctx.dataset.projectNumber || '';
            const name = ctx.dataset.projectName || 'Project Schedule';
            return { id: ctx.dataset.projectId, number, name, label: number ? `${number} — ${name}` : name };
        }
        return { id: '', number: '', name: 'Project Schedule', label: 'Project Schedule' };
    }

    function buildEmptySchedule() {
        const today = CasePMSchedule.formatDate(new Date());
        const meta = getProjectMeta();
        return {
            data: [{
                id: 1,
                text: meta.name || 'Project Schedule',
                type: 'project',
                open: true,
                start_date: today,
                duration: 0,
                progress: 0
            }],
            links: []
        };
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

    function applyTaskBarColor(task) {
        if (!task || task.type === 'project') return;
        const color = resolveBarColor(task);
        task.color = task.bar_color || color;
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
        const hostW = document.getElementById('gantt_here')?.offsetWidth || 1200;
        if (scheduleSettings.timeline_width_px >= 180) {
            return Math.max(180, Math.min(hostW - 160, scheduleSettings.timeline_width_px));
        }
        const pct = scheduleSettings.timeline_pct ?? 0.45;
        return Math.max(200, Math.min(hostW - 160, Math.round(hostW * pct)));
    }

    function syncGridTableWidth() {
        if (!ganttReady || !gantt.config.columns) return;
        const total = getColumnsTotalWidth();
        gantt.config.grid_width = total;
    }

    function applyChartOverlay() {
        if (!ganttReady) return;
        const scroll = getTimelineScrollState();
        const root = document.querySelector('#gantt_here .gantt_layout_root');
        if (!root) return;

        const timelineW = getTimelineWidth();

        const cells = root.querySelectorAll(':scope > .gantt_layout_cell');
        const gridCell = cells[0];
        const nativeResizer = cells[1];
        const timelineCell = cells[2];
        if (!gridCell || !timelineCell) return;

        root.style.position = 'relative';
        gridCell.style.cssText = 'flex:1 1 auto;width:100%!important;min-width:0!important;position:relative;z-index:2;overflow:hidden;';
        if (nativeResizer) nativeResizer.style.cssText = 'display:none!important;width:0!important;min-width:0!important;';

        timelineCell.style.cssText = `position:absolute!important;top:0;right:0;bottom:0;width:${timelineW}px!important;z-index:15;box-shadow:-8px 0 24px rgba(0,0,0,0.55);pointer-events:auto;overflow:visible!important;`;

        let handle = document.getElementById('scheduleChartResizer');
        if (!handle) {
            handle = document.createElement('div');
            handle.id = 'scheduleChartResizer';
            handle.className = 'schedule-chart-resizer';
            handle.title = 'Drag to resize chart overlay';
            root.appendChild(handle);
        }
        handle.style.right = (timelineW - 4) + 'px';
        restoreTimelineScroll(scroll);
    }

    function queueChartOverlay() {
        clearTimeout(overlayApplyTimer);
        overlayApplyTimer = setTimeout(applyChartOverlay, 16);
    }

    const overlayDrag = { active: false, bound: false };

    function initChartOverlay() {
        if (scheduleSettings.timeline_width_px == null && scheduleSettings.timeline_pct == null) {
            scheduleSettings.timeline_pct = 0.45;
        }
        document.getElementById('scheduleGanttHost')?.classList.add('schedule-overlay-mode');

        if (!overlayDrag.bound) {
            overlayDrag.bound = true;
            document.addEventListener('mousedown', e => {
                const handle = document.getElementById('scheduleChartResizer');
                if (!handle || (!handle.contains(e.target) && e.target !== handle)) return;
                overlayDrag.active = true;
                e.preventDefault();
                e.stopPropagation();
            });
            document.addEventListener('mousemove', e => {
                if (!overlayDrag.active) return;
                const hostEl = document.getElementById('gantt_here');
                if (!hostEl) return;
                const rect = hostEl.getBoundingClientRect();
                const timelineW = Math.max(180, Math.min(rect.width - 160, rect.right - e.clientX));
                scheduleSettings.timeline_width_px = timelineW;
                scheduleSettings.timeline_pct = timelineW / rect.width;
                applyChartOverlay();
            });
            document.addEventListener('mouseup', () => {
                if (overlayDrag.active) {
                    overlayDrag.active = false;
                    queueSave();
                }
            });
            window.addEventListener('resize', () => {
                const hostW = document.getElementById('gantt_here')?.offsetWidth;
                if (hostW && scheduleSettings.timeline_pct) {
                    scheduleSettings.timeline_width_px = Math.round(hostW * scheduleSettings.timeline_pct);
                }
                queueChartOverlay();
            });
        }

        syncGridTableWidth();
        queueChartOverlay();
    }

    function updateGridWidth() {
        syncGridTableWidth();
        queueChartOverlay();
    }

    function constrainInlineEditor() {
        requestAnimationFrame(() => {
            const ph = document.querySelector('#gantt_here .gantt_grid_editor_placeholder, #gantt_here .gantt_inline_editor');
            if (!ph) return;
            const cell = ph.closest('.gantt_cell');
            if (!cell) return;
            const cw = cell.clientWidth;
            const ch = cell.clientHeight;
            ph.style.width = cw + 'px';
            ph.style.maxWidth = cw + 'px';
            ph.style.minWidth = '0';
            ph.style.height = Math.max(22, ch - 2) + 'px';
            ph.style.maxHeight = ch + 'px';
            ph.style.overflow = 'hidden';
            ph.style.boxSizing = 'border-box';
            ph.style.position = 'absolute';
            ph.style.left = '0';
            ph.style.top = '0';
            ph.querySelectorAll('input, select, textarea').forEach(inp => {
                inp.style.width = '100%';
                inp.style.maxWidth = '100%';
                inp.style.height = '100%';
                inp.style.minHeight = '0';
                inp.style.boxSizing = 'border-box';
                inp.style.fontSize = '13px';
                inp.style.padding = '2px 4px';
            });
        });
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

    function getProjectDateBounds() {
        if (!ganttReady) return null;
        const range = gantt.getSubtaskDates();
        let start = range?.start_date ? toGanttDate(range.start_date) : new Date();
        let end = range?.end_date ? toGanttDate(range.end_date) : new Date(start.getTime() + 120 * 86400000);
        if (!start) start = new Date();
        if (!end || end <= start) end = CasePMSchedule.addCalendarDays(start, 120);
        start = CasePMSchedule.addCalendarDays(start, -120);
        end = CasePMSchedule.addCalendarDays(end, 240);
        if (CasePMSchedule.calendarDaysBetween(start, end) < 540) {
            end = CasePMSchedule.addCalendarDays(start, 540);
        }
        return { start, end };
    }

    function applyTimelineDateRange() {
        const bounds = getProjectDateBounds();
        if (!bounds) return;
        gantt.config.start_date = bounds.start;
        gantt.config.end_date = bounds.end;
    }

    function handleColumnResize(index, column, new_width, persist) {
        if (column && column.name) {
            columnWidths[column.name] = new_width;
            column.width = new_width;
            if (gantt.config.columns[index]) {
                gantt.config.columns[index].width = new_width;
            }
        }
        syncGridTableWidth();
        if (persist) queueSave();
    }

    let baselineLayerBound = false;
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
            const barH = gantt.config.bar_height || 24;
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

    function collapseTemplate(task) {
        if (!ganttReady || !gantt.hasChild(task.id)) return '';
        const open = task.$open !== false;
        return `<span class="sched-tree-btn" title="${open ? 'Collapse' : 'Expand'}">${open ? '▾' : '▸'}</span>`;
    }

    function resolveBarColor(task) {
        if (!task || task.type === 'project') return '#64748b';
        if (task.bar_color) return task.bar_color;
        if (isTaskCritical(task)) return scheduleSettings.critical_bar_color;
        if (Math.round((task.progress || 0) * 100) >= 100) return scheduleSettings.complete_bar_color;
        if ((task.progress || 0) > 0) return scheduleSettings.progress_bar_color;
        if (task.type === 'milestone') return scheduleSettings.milestone_color;
        return scheduleSettings.default_bar_color;
    }

    function applyPredecessorString(taskId, predStr) {
        if (!gantt.isTaskExists(taskId)) return;
        const existing = [...(gantt.getTask(taskId).$target || [])];
        existing.forEach(lid => gantt.deleteLink(lid));
        if (predStr && predStr.trim()) {
            const parts = predStr.split(/[,;]+/).map(s => s.trim()).filter(Boolean);
            const types = { FS: '0', SS: '1', FF: '2', SF: '3' };
            parts.forEach(part => {
                const m = part.match(/^([^\s]+?)(FS|SS|FF|SF)?([+-]?\d+)?$/i);
                if (!m) return;
                const code = m[1];
                const type = types[(m[2] || 'FS').toUpperCase()] || '0';
                const lag = parseInt(m[3] || '0', 10) || 0;
                let sourceId = null;
                gantt.eachTask(t => {
                    if (sourceId) return;
                    const wbs = wbsCode(t);
                    if (wbs === code || String(t.id) === code || String(t.activity_id) === code) sourceId = t.id;
                });
                if (sourceId && sourceId !== taskId) {
                    gantt.addLink({ source: sourceId, target: taskId, type, lag });
                }
            });
        }
        gantt.refreshTask(taskId);
        gantt.render();
        refreshWbsCodes();
    }

    function getBuiltinColumnDefs() {
        return [
            { name: 'collapse', label: '', width: 30, min_width: 30, resize: false, align: 'center', template: collapseTemplate },
            { name: 'wbs', label: 'WBS', width: 58, align: 'center', resize: true, template: t => wbsCode(t) },
            { name: 'activity_id', label: 'ID', width: 64, align: 'center', resize: true, editor: { type: 'text', map_to: 'activity_id' }, template: t => t.activity_id || '' },
            { name: 'text', label: 'Activity Name', tree: false, width: 220, min_width: 120, resize: true, editor: { type: 'text', map_to: 'text' }, template: t => {
                const pad = (t.$level || 0) * 14;
                return `<span style="padding-left:${pad}px;display:inline-block">${t.text || ''}</span>`;
            } },
            { name: 'duration', label: 'Dur', align: 'center', width: 52, min_width: 44, resize: true, editor: { type: 'number', map_to: 'duration', min: 0, max: 9999 } },
            { name: 'start_date', label: 'Start', align: 'center', width: 98, min_width: 88, resize: true, editor: { type: 'date', map_to: 'start_date' }, template: t => formatDateSafe(t.start_date) },
            { name: 'end_date', label: 'Finish', align: 'center', width: 98, min_width: 88, resize: true, editor: { type: 'date', map_to: 'end_date' }, template: t => formatDateSafe(t.end_date) },
            { name: 'predecessors', label: 'Predecessors', width: 118, min_width: 80, resize: true, editor: { type: 'pred_string', map_to: 'auto' }, template: predTemplate },
            { name: 'successors', label: 'Successors', width: 108, min_width: 80, resize: true, template: succTemplate },
            { name: 'progress', label: '%', align: 'center', width: 48, min_width: 42, resize: true, editor: { type: 'number', map_to: 'progress', min: 0, max: 100 }, template: t => Math.round(effectiveProgress(t) * 100) },
            { name: 'resource', label: 'Resource', width: 108, min_width: 70, resize: true, editor: { type: 'text', map_to: 'resource' } },
            { name: 'owner', label: 'Responsible', width: 108, min_width: 70, resize: true, editor: { type: 'text', map_to: 'owner' } },
            { name: 'total_float', label: 'Total Float', width: 72, align: 'center', resize: true, template: t => t.$slack != null ? t.$slack : (t.total_float != null ? t.total_float : '') },
            { name: 'bar_color', label: 'Color', width: 58, align: 'center', resize: true, template: t => t.bar_color ? `<span class="sched-color-swatch" style="background:${t.bar_color}"></span>` : '—', editor: { type: 'color_hex', map_to: 'bar_color' } }
        ];
    }

    function editorForField(field) {
        if (!field || field.type === 'readonly' || field.type === 'successors') return null;
        if (field.type === 'predecessor') return { type: 'predecessor', map_to: 'auto' };
        if (field.type === 'date') return { type: 'date', map_to: field.map_to };
        if (field.type === 'number') return { type: 'number', map_to: field.map_to, min: 0, max: 999999 };
        if (field.type === 'percent') return { type: 'number', map_to: field.map_to, min: 0, max: 100 };
        return { type: 'text', map_to: field.map_to };
    }

    function buildColumnConfig() {
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

        return orderColumns(cols);
    }

    function registerCustomEditors() {
        if (!gantt.config.editor_types) gantt.config.editor_types = {};
        gantt.config.editor_types.pred_string = {
            show: function (id, column, config, placeholder) {
                const inp = document.createElement('input');
                inp.type = 'text';
                inp.className = 'gantt_grid_editor';
                inp.value = predTemplate(gantt.getTask(id));
                inp.placeholder = 'e.g. 1.2FS+2';
                placeholder.appendChild(inp);
                inp.focus();
                inp.select();
                constrainInlineEditor();
            },
            hide: function () { },
            set_value: function (value, id) {
                applyPredecessorString(id, value);
                queueSave();
            },
            get_value: function (id, column, node) {
                return node.querySelector('input')?.value || '';
            },
            is_changed: function (value, id, column, node) {
                const cur = node.querySelector('input')?.value || '';
                return cur !== predTemplate(gantt.getTask(id));
            },
            is_valid: function () { return true; },
            save: function (id, column, node) {
                applyPredecessorString(id, node.querySelector('input')?.value || '');
                queueSave();
            },
            focus: function (node) { node.querySelector('input')?.focus(); }
        };
        gantt.config.editor_types.color_hex = {
            show: function (id, column, config, placeholder) {
                const task = gantt.getTask(id);
                const inp = document.createElement('input');
                inp.type = 'color';
                inp.className = 'gantt_grid_editor sched-color-editor';
                inp.value = task.bar_color || scheduleSettings.default_bar_color || '#3b82f6';
                placeholder.appendChild(inp);
                inp.focus();
                constrainInlineEditor();
            },
            hide: function () { },
            set_value: function (value, id) {
                const t = gantt.getTask(id);
                t.bar_color = value;
                applyTaskBarColor(t);
                gantt.updateTask(id);
                gantt.render();
            },
            get_value: function (id, column, node) {
                return node.querySelector('input')?.value || '';
            },
            is_changed: function () { return true; },
            is_valid: function () { return true; },
            save: function (id, column, node) {
                const t = gantt.getTask(id);
                t.bar_color = node.querySelector('input')?.value || '';
                applyTaskBarColor(t);
                gantt.updateTask(id);
                gantt.render();
                queueSave();
            },
            focus: function (node) { node.querySelector('input')?.focus(); }
        };
    }

    let allowGridEdit = false;

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
        allowGridEdit = true;
        setTimeout(() => {
            if (gantt.ext && gantt.ext.inlineEditors) {
                gantt.ext.inlineEditors.startEdit(id, colName);
            } else if (gantt.inlineEditors && gantt.inlineEditors.startEdit) {
                gantt.inlineEditors.startEdit(id, colName);
            }
            setTimeout(() => { allowGridEdit = false; }, 100);
        }, 0);
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
        gantt.config.row_height = 38;
        gantt.config.bar_height = 24;
        gantt.config.scale_height = 52;
        gantt.config.scroll_size = 18;
        gantt.config.fit_tasks = false;
        gantt.config.show_errors = false;
        gantt.config.highlight_critical_path = true;
        gantt.config.grid_elastic_columns = false;
        gantt.config.keep_grid_width = false;
        gantt.config.round_dnd_dates = false;
        gantt.config.drag_timeline = { useKey: false };
        gantt.config.autosize = false;
        gantt.config.reorder_grid_columns = true;
        gantt.config.open_tree_initially = true;
        gantt.config.details_on_dblclick = false;
        gantt.config.details_on_create = false;
        gantt.config.select_task = true;
        gantt.config.keyboard_navigation = false;
        gantt.config.show_task_cells = true;
        gantt.config.show_links = true;

        gantt.config.layout = {
            css: 'gantt_container',
            cols: [
                {
                    rows: [
                        { view: 'grid', scrollX: 'gridScroll', scrollY: 'scrollVer' },
                        { view: 'scrollbar', id: 'gridScroll', height: 18 }
                    ]
                },
                { resizer: true, width: 1 },
                {
                    width: 600,
                    min_width: 200,
                    rows: [
                        { view: 'timeline', scrollX: 'scrollHor', scrollY: 'scrollVer' },
                        { view: 'scrollbar', id: 'scrollHor', height: 18 }
                    ]
                },
                { view: 'scrollbar', id: 'scrollVer' }
            ]
        };

        gantt.config.columns = buildColumnConfig();
        registerCustomEditors();

        gantt.attachEvent('onBeforeLightbox', () => false);

        gantt.attachEvent('onBeforeEditStart', () => {
            setTimeout(constrainInlineEditor, 0);
            return allowGridEdit;
        });

        gantt.attachEvent('onTaskLoading', (task) => {
            sanitizeTaskDates(task);
            applyTaskBarColor(task);
            return true;
        });

        gantt.templates.grid_row_class = function (start, end, task) {
            if (task.type === 'project') return 'cpm_project_row';
            return '';
        };

        gantt.templates.task_class = function (start, end, task) {
            const classes = [];
            if (gantt.config.highlight_critical_path && isTaskCritical(task)) classes.push('cpm_critical');
            if (task.type === 'milestone') classes.push('cpm_milestone');
            if (task.type === 'project') classes.push('cpm_summary');
            if (isLoeTask(task)) classes.push('cpm_loe');
            if (task.bar_color) classes.push('cpm_custom_color');
            const p = Math.round(effectiveProgress(task) * 100);
            if (p >= 100) classes.push('cpm_complete');
            else if (p > 0) classes.push('cpm_in_progress');
            return classes.join(' ');
        };

        gantt.templates.task_style = function (start, end, task) {
            if (task.type === 'project') return '';
            const color = resolveBarColor(task);
            return `--dhx-gantt-task-background:${color};--dhx-gantt-task-border:${color};background-color:${color} !important;border-color:${color} !important;`;
        };

        gantt.templates.task_text = function (start, end, task) {
            if (task.type === 'project') return '';
            return `<span class="gantt-bar-date-label">${formatDateSafe(start)}</span>`;
        };

        gantt.templates.rightside_text = function (start, end, task) {
            if (task.type === 'project' || task.type === 'milestone') return task.type === 'milestone' ? task.text : '';
            return formatDateSafe(end);
        };

        gantt.templates.link_class = function () {
            return 'cpm_schedule_link';
        };

        applyGanttDisplayStyles();

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
            if (target.closest?.('.sched-tree-btn')) {
                const t = gantt.getTask(id);
                if (gantt.hasChild(id)) {
                    if (t.$open !== false) gantt.close(id); else gantt.open(id);
                }
                return false;
            }
            if (target.closest?.('.gantt_tree_icon')) return true;
            gantt.selectTask(id);
            return true;
        });

        gantt.attachEvent('onTaskDblClick', function (id, e) {
            const target = e.target || e.srcElement;
            if (target.closest?.('.sched-tree-btn') || target.closest?.('.gantt_tree_icon')) return true;
            if (target.closest?.('.gantt_grid')) {
                const pos = (gantt.locateCell && gantt.locateCell(target)) || locateGridCell(target);
                let col = null;
                if (pos) {
                    if (typeof pos.column === 'number') col = gantt.config.columns[pos.column];
                    else if (typeof pos.column === 'string') col = gantt.config.columns.find(c => c.name === pos.column);
                    else if (pos.column && pos.column.name) col = pos.column;
                }
                if (col && col.editor && !['wbs', 'successors', 'collapse'].includes(col.name)) {
                    startCellEdit(id, col.name);
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
        gantt.attachEvent('onAfterTaskDrag', function () {
            applyTimelineDateRange();
            pushUndoState();
            queueSave();
            gantt.render();
        });
        gantt.attachEvent('onAfterColumnReorder', () => {
            columnOrder = gantt.config.columns.map(c => c.name);
            scheduleSettings.column_order = columnOrder.slice();
            syncGridTableWidth();
            queueSave();
            gantt.render();
        });
        gantt.attachEvent('onColumnResize', function (index, column, new_width) {
            handleColumnResize(index, column, new_width, false);
            return true;
        });
        gantt.attachEvent('onColumnResizeEnd', function (index, column, new_width) {
            handleColumnResize(index, column, new_width, true);
            gantt.render();
        });
        gantt.attachEvent('onGanttRender', () => {
            refreshWbsCodes();
            updateStatusBar();
            if (!overlayDrag.active) {
                requestAnimationFrame(applyChartOverlay);
            }
        });

        document.addEventListener('keydown', onScheduleKeyDown);

        initBaselineBars();
        applyTimelineDateRange();


        syncGridTableWidth();
        gantt.init('gantt_here');
        sanitizeAllTaskDates();
        initChartOverlay();
        ganttReady = true;
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
        refreshWbsCodes();
        applySettingsToUI();
        gantt.eachTask(t => applyTaskBarColor(t));
        applyBaselineVariance();
        applyTimelineDateRange();
        queueChartOverlay();
        gantt.render();
        setSaveStatus('Ready');
        pushUndoState();
        updateDataDateMarker();
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

        loadSchedulePayload(buildEmptySchedule());
        setSaveStatus('Empty schedule — add activities or import');
    }

    async function clearSchedule() {
        if (!confirm('Clear the entire schedule? This cannot be undone.')) return;
        const projectId = getSelectedProjectId();
        localStorage.removeItem(`${STORAGE_KEY}_${projectId}`);
        loadSchedulePayload(buildEmptySchedule());
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
        const fromStorage = localStorage.getItem('casepm_current_project_id');
        const id = parseInt(fromUrl || fromCtx || fromStorage || '0', 10);
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

    function setTimescale(scale, persist) {
        const map = { day: 0, week: 1, month: 2, quarter: 3 };
        const level = map[scale];
        if (level === undefined) return;
        scheduleSettings.timescale = scale;
        if (gantt.ext && gantt.ext.zoom) {
            gantt.ext.zoom.setLevel(level);
        } else {
            const scales = {
                day: [{ unit: 'day', step: 1, format: '%d %M' }],
                week: [{ unit: 'week', step: 1, format: 'W%W' }, { unit: 'day', step: 1, format: '%d' }],
                month: [{ unit: 'month', step: 1, format: '%F %Y' }, { unit: 'week', step: 1, format: 'W%W' }],
                quarter: [{ unit: 'year', step: 1, format: '%Y' }, { unit: 'month', step: 1, format: '%M' }]
            };
            gantt.config.scales = scales[scale] || scales.day;
            gantt.render();
        }
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
        const bl = document.getElementById('dispShowBaselineBars');
        if (bl) bl.checked = s.show_baseline_bars !== false;
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
        if (scheduleSettings.timescale) setTimescale(scheduleSettings.timescale, false);
        updateDataDateMarker();
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

    function addActivity(type) {
        const parent = resolveAddParent();
        const today = toGanttDate(CasePMSchedule.formatDate(new Date()));
        const id = gantt.addTask({
            text: type === 'milestone' ? 'New Milestone' : 'New Activity',
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
        gantt.selectTask(id);
        refreshWbsCodes();
        gantt.render();
        queueSave();
    }

    function outdentSelected() {
        const id = gantt.getSelectedId();
        if (!id) return showScheduleAlert('Select an activity to outdent.', 'warning');
        const parent = gantt.getParent(id);
        if (!parent || parent === 0) return showScheduleAlert('Activity is already at top level.', 'warning');
        const grandParent = gantt.getParent(parent) || 0;
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
        if (!gantt.ext || !gantt.ext.zoom) return;
        const cur = gantt.ext.zoom.getCurrentLevel();
        if (dir === 'in') gantt.ext.zoom.setLevel(Math.max(0, cur - 1));
        else gantt.ext.zoom.setLevel(Math.min(3, cur + 1));
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

    function scrollToScheduleRange() {
        if (!ganttReady) return;
        const range = gantt.getSubtaskDates();
        if (range?.start_date) {
            const d = toGanttDate(range.start_date);
            if (d) gantt.showDate(d);
        }
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
        applyTimelineDateRange();
        wbsCodeMap = wbsMap || CasePMSchedule.buildWbsMap(tasks);
        gantt.render();
        if (opts.scroll === true) scrollToScheduleRange();
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
        ['ganttViewPanel', 'lookaheadViewPanel', 'traceViewPanel'].forEach(id => {
            document.getElementById(id)?.classList.add('hidden');
        });
        document.querySelectorAll('.schedule-view-tab').forEach(btn => btn.classList.remove('active-view'));

        if (view === 'gantt') {
            document.getElementById('ganttViewPanel')?.classList.remove('hidden');
            document.getElementById('tabGantt')?.classList.add('active-view');
            resizeGanttHost();
            gantt.render();
        } else if (view === 'lookahead') {
            document.getElementById('lookaheadViewPanel')?.classList.remove('hidden');
            document.getElementById('tabLookahead')?.classList.add('active-view');
            renderLookAhead();
        } else if (view === 'trace') {
            document.getElementById('traceViewPanel')?.classList.remove('hidden');
            document.getElementById('tabTrace')?.classList.add('active-view');
            renderTraceTable();
        }
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
        gantt.eachTask(t => {
            if (t.type !== 'project' && isTaskCritical(t)) critical++;
            if (t.cpi != null && !Number.isNaN(Number(t.cpi))) { totalCpi += Number(t.cpi); cpiCount++; }
        });
        const avgCpi = cpiCount ? (totalCpi / cpiCount).toFixed(2) : '—';
        const blIdx = scheduleSettings.active_baseline_index;
        const blLabel = blIdx >= 0 && baselines[blIdx] ? baselines[blIdx].name : 'None';
        el.innerHTML = `
            <span>Start: <b>${formatDateSafe(range.start_date)}</b></span>
            <span>Finish: <b>${formatDateSafe(range.end_date)}</b></span>
            <span>Activities: <b>${countTasks()}</b></span>
            <span>Critical: <b class="text-red-400">${critical}</b></span>
            <span>Baseline: <b class="text-sky-400">${blLabel}</b></span>
            <span>Avg CPI: <b>${avgCpi}</b></span>
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
        const meta = getProjectMeta();
        const range = gantt.getSubtaskDates();
        const dataDate = document.getElementById('dataDateInput')?.value || scheduleSettings.data_date || CasePMSchedule.formatDate(new Date());
        const printed = new Date().toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
        const startMs = range?.start_date ? toGanttDate(range.start_date)?.getTime() : Date.now();
        const endMs = range?.end_date ? toGanttDate(range.end_date)?.getTime() : startMs + 86400000 * 30;
        const span = Math.max(endMs - startMs, 86400000);

        let critical = 0;
        gantt.eachTask(t => { if (t.type !== 'project' && isTaskCritical(t)) critical++; });

        const timescale = buildPrintTimescale(startMs, span);

        let rows = '';
        const rowMap = new Map();
        let rowIdx = 0;
        gantt.eachTask(t => {
            rowMap.set(t.id, rowIdx++);
            const ts = toGanttDate(t.start_date)?.getTime() || startMs;
            const te = toGanttDate(t.end_date)?.getTime() || ts;
            const left = Math.max(0, ((ts - startMs) / span) * 100);
            const width = Math.max(t.type === 'milestone' ? 0.8 : 1.2, ((te - ts) / span) * 100);
            const color = resolveBarColor(t);
            const level = t.$level || 0;
            const dateLabel = `${formatDateSafe(t.start_date)} – ${formatDateSafe(t.end_date)}`;
            rows += `<tr class="${t.type === 'project' ? 'print-summary' : ''}">
                <td>${wbsCode(t)}</td>
                <td class="print-name" style="padding-left:${8 + level * 14}px">${t.text || ''}</td>
                <td class="c">${t.duration != null ? t.duration : ''}</td>
                <td>${formatDateSafe(t.start_date)}</td>
                <td>${formatDateSafe(t.end_date)}</td>
                <td class="c">${Math.round((t.progress || 0) * 100)}%</td>
                <td>${predTemplate(t) || '—'}</td>
                <td class="print-bar-cell">
                    <div class="print-bar-dates">${dateLabel}</div>
                    <div class="print-bar-track"><div class="print-bar" style="left:${left}%;width:${width}%;background:${color}"></div></div>
                </td>
            </tr>`;
        });

        const links = gantt.getLinks();
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
            const color = resolveBarColor(t);
            chartBars += `<rect x="${x}" y="${y - 1.2}" width="${w}" height="2.4" fill="${color}" rx="0.3"/>`;
        });
        let chartLines = '';
        links.forEach(link => {
            if (!gantt.isTaskExists(link.source) || !gantt.isTaskExists(link.target)) return;
            const src = gantt.getTask(link.source);
            const tgt = gantt.getTask(link.target);
            const si = rowMap.get(link.source);
            const ti = rowMap.get(link.target);
            if (si == null || ti == null) return;
            const x1 = ((toGanttDate(src.end_date)?.getTime() || startMs) - startMs) / span * 100;
            const x2 = ((toGanttDate(tgt.start_date)?.getTime() || startMs) - startMs) / span * 100;
            const y1 = ((si + 0.5) / rowIdx) * 100;
            const y2 = ((ti + 0.5) / rowIdx) * 100;
            chartLines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#444" stroke-width="0.4"/>`;
        });
        const chartBlock = rowIdx ? `
            <div class="print-gantt-chart">
                <h3 class="print-chart-title">Schedule Chart</h3>
                ${timescale}
                <svg class="print-chart-svg" viewBox="0 0 100 100" preserveAspectRatio="none" style="height:${chartH}px">
                    ${chartLines}${chartBars}
                </svg>
            </div>` : '';

        const sheet = document.getElementById('schedulePrintSheet');
        if (!sheet) return;
        sheet.innerHTML = `
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
                </div>
            </div>
            <table class="schedule-print-table">
                <thead>
                    <tr>
                        <th>WBS</th><th>Activity Name</th><th>Dur</th><th>Start</th><th>Finish</th><th>%</th><th>Predecessors</th><th class="print-bar-cell">Gantt</th>
                    </tr>
                    <tr class="print-ts-row"><td colspan="7"></td><td class="print-bar-cell">${timescale}</td></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
            ${chartBlock}`;
    }

    function printGantt() {
        buildPrintSheet();
        const sheet = document.getElementById('schedulePrintSheet');
        if (!sheet || !sheet.innerHTML.trim()) {
            showScheduleAlert('Nothing to print — add activities first.', 'warning');
            return;
        }
        document.body.classList.add('printing-gantt');
        setTimeout(() => {
            window.print();
            setTimeout(() => document.body.classList.remove('printing-gantt'), 600);
        }, 150);
    }

    function printLookAhead() {
        renderLookAhead();
        document.body.classList.add('printing-lookahead');
        document.getElementById('lookaheadViewPanel')?.classList.add('print-active');
        setTimeout(() => {
            window.print();
            setTimeout(() => {
                document.body.classList.remove('printing-lookahead');
                document.getElementById('lookaheadViewPanel')?.classList.remove('print-active');
            }, 500);
        }, 200);
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

    function initZoom() {
        if (!gantt.ext || !gantt.ext.zoom) return;
        gantt.ext.zoom.init({
            levels: [
                { name: 'day', scale_height: 50, min_column_width: 50, scales: [{ unit: 'day', step: 1, format: '%d %M' }, { unit: 'month', step: 1, format: '%F %Y' }] },
                { name: 'week', scale_height: 50, min_column_width: 60, scales: [{ unit: 'week', step: 1, format: 'Week %W' }, { unit: 'month', step: 1, format: '%F %Y' }] },
                { name: 'month', scale_height: 50, min_column_width: 70, scales: [{ unit: 'month', step: 1, format: '%F %Y' }, { unit: 'year', step: 1, format: '%Y' }] },
                { name: 'quarter', scale_height: 50, min_column_width: 80, scales: [{ unit: 'quarter', step: 1, format: 'Q%q %Y' }, { unit: 'year', step: 1, format: '%Y' }] }
            ]
        });
        gantt.ext.zoom.setLevel(1);
    }

    async function init() {
        if (typeof gantt === 'undefined') {
            setSaveStatus('Gantt library failed to load — refresh page');
            return;
        }
        configureGantt();
        initZoom();
        if (scheduleSettings.timescale) setTimescale(scheduleSettings.timescale, false);
        await loadSchedule();
        runSchedule({ skipScroll: true });
        switchScheduleView('gantt');
        const pid = getSelectedProjectId();
        if (pid) localStorage.setItem('casepm_current_project_id', String(pid));

        document.getElementById('dataDateInput')?.addEventListener('change', () => {
            scheduleSettings.data_date = document.getElementById('dataDateInput').value;
            updateDataDateMarker();
            gantt.render();
            queueSave();
        });
    }

    window.ScheduleApp = {
        init, addActivity, deleteSelected, indentSelected, outdentSelected, openActivityDetail,
        linkSelected, unlinkSelected, zoomGantt, setTimescale, showDisplaySettings, saveDisplaySettings,
        wbsCode, applyPredecessorString,
        toggleCriticalPath, setBaseline, showBaselineManager, activateBaseline, deleteBaseline,
        undo, redo,
        runSchedule, switchScheduleView, renderLookAhead, focusActivity,
        exportJson, importFile, printGantt, printLookAhead, saveSchedule,
        loadSchedule, clearSchedule, showColumnManager, showAddColumnDialog, removeColumn, addFieldColumn, queueSave
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
