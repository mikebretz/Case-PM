/* Case PM — Primavera / MS Project style scheduling application */
(function () {
    'use strict';

    const STORAGE_KEY = 'casepm_schedule_v5';
    const GRID_HEADER_TOP_H = 26;
    const GRID_HEADER_LABEL_H = 39;
    const GRID_HEADER_TOTAL_H = GRID_HEADER_TOP_H + GRID_HEADER_LABEL_H;
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
    let columnDefWidths = {};
    let wbsCodeMap = new Map();
    let scheduleSettings = {
        data_date: typeof CasePMSchedule !== 'undefined' ? CasePMSchedule.formatDate(new Date()) : '',
        calendar: 'standard',
        lookahead_days: 14,
        timescale: 'day',
        default_bar_color: '#3794ff',
        critical_bar_color: '#f1707b',
        progress_bar_color: '#eca06c',
        complete_bar_color: '#6ccb5f',
        milestone_color: '#3794ff',
        link_color: '#b0b0b0',
        link_width: 1,
        active_baseline_index: -1,
        show_baseline_bars: true,
        show_bar_labels: true,
        theme: 'dark',
        default_cell_align: { h: 'left', v: 'middle' },
        column_align: {},
        default_cell_style: { font_size: 11 },
        default_row_height: 24,
        default_bar_height: 16,
        summary_row_height: 24,
        summary_bar_height: 12
    };
    if (!scheduleSettings.print_settings) {
        scheduleSettings.print_settings = {
            include_summary: true,
            include_activity_table: true,
            include_inline_bars: true,
            include_predecessor_links: true,
            orientation: 'landscape',
            font_size_pt: 8,
            row_height_px: 24,
            chart_width_pct: 58,
            print_wbs_colors: true,
            print_bar_labels: false,
            print_column_mode: 'screen',
            print_grid_lines: true,
            print_timescale: 'week',
            print_show_nonwork: false,
            print_critical_color: '#c00000',
            paper_size: 'letter',
            margin_in: 0.35,
            print_scale: 100,
            fit_to_page: false,
            repeat_header: true,
            page_numbers: false,
            print_color_bars: true,
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
        syncGanttLayout();
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
        const sub = document.getElementById('scheduleProjectSubtitle');
        if (sub) {
            const meta = getProjectMeta();
            sub.textContent = meta.label || 'Gantt chart · CPM · baselines';
        }
    }

    const WBS_GUTTER_COLORS = ['#0070c0', '#00b050', '#ffff00', '#ffc000'];
    const WBS_GUTTER_WIDTH = 14;

    function buildP6DemoSchedule() {
        const tasks = [
            { id: 1, text: 'Pipe Repairs & Improvement 12', type: 'project', open: true, start_date: '2023-06-05', end_date: '2023-07-28', duration: 0, progress: 0 },
            { id: 2, parent: 1, text: 'Start Project', activity_id: 'A1000', type: 'milestone', start_date: '2023-06-05', end_date: '2023-06-05', duration: 0, progress: 1 },
            { id: 3, parent: 1, text: 'Contract Award Date', activity_id: 'A1005', type: 'milestone', start_date: '2023-06-05', end_date: '2023-06-05', duration: 0, progress: 1 },
            { id: 4, parent: 1, text: 'Demolition Piping', open: true, start_date: '2023-06-05', end_date: '2023-06-20', duration: 11, progress: 0.45 },
            { id: 5, parent: 4, text: 'Thrustblock', open: true, start_date: '2023-06-05', end_date: '2023-06-15', duration: 8, progress: 0.3 },
            { id: 6, parent: 5, text: 'Project Management', activity_id: 'A1010', start_date: '2023-06-05', end_date: '2023-07-15', duration: 28, progress: 0.35 },
            { id: 7, parent: 5, text: 'Site Mobilization', activity_id: 'A1015', start_date: '2023-06-05', end_date: '2023-06-09', duration: 3, progress: 1 },
            { id: 8, parent: 5, text: 'Remove Existing Piping', activity_id: 'A1020', start_date: '2023-06-08', end_date: '2023-06-18', duration: 8, progress: 0.6 },
            { id: 9, parent: 5, text: 'Remove Thrust Blocks', activity_id: 'A1025', start_date: '2023-06-10', end_date: '2023-06-15', duration: 4, progress: 0.5 },
            { id: 10, parent: 4, text: 'Piping', open: true, start_date: '2023-06-12', end_date: '2023-07-25', duration: 31, progress: 0.2 },
            { id: 11, parent: 10, text: 'Procure Pipe Materials', activity_id: 'A2005', start_date: '2023-06-12', end_date: '2023-06-25', duration: 9, progress: 0.8 },
            { id: 12, parent: 10, text: 'Install Piping & Couplings', activity_id: 'A2010', start_date: '2023-06-20', end_date: '2023-07-10', duration: 15, progress: 0.25 },
            { id: 13, parent: 10, text: 'Install Thrust Blocks', activity_id: 'A2015', start_date: '2023-06-22', end_date: '2023-07-05', duration: 9, progress: 0.15 },
            { id: 14, parent: 10, text: 'Pressure Test', activity_id: 'A2020', start_date: '2023-07-11', end_date: '2023-07-18', duration: 6, progress: 0 },
            { id: 15, parent: 4, text: 'Demolition Complete', activity_id: 'A1030', type: 'milestone', start_date: '2023-06-20', end_date: '2023-06-20', duration: 0, progress: 0 },
            { id: 16, parent: 10, text: 'Piping Complete', activity_id: 'A2030', type: 'milestone', start_date: '2023-07-25', end_date: '2023-07-25', duration: 0, progress: 0 },
            { id: 17, parent: 1, text: 'Restoration & Cleanup', open: true, start_date: '2023-07-18', end_date: '2023-07-28', duration: 8, progress: 0 },
            { id: 18, parent: 17, text: 'Backfill & Restore Surfaces', activity_id: 'A3010', start_date: '2023-07-18', end_date: '2023-07-24', duration: 5, progress: 0 },
            { id: 19, parent: 17, text: 'Final Inspection', activity_id: 'A3020', start_date: '2023-07-25', end_date: '2023-07-27', duration: 2, progress: 0 },
            { id: 20, parent: 1, text: 'Project Completion Date', activity_id: 'A9999', type: 'milestone', start_date: '2023-07-28', end_date: '2023-07-28', duration: 0, progress: 0 }
        ];
        const links = [
            { id: 1, source: 2, target: 6, type: '0' },
            { id: 2, source: 3, target: 7, type: '0' },
            { id: 3, source: 6, target: 7, type: '0' },
            { id: 4, source: 7, target: 8, type: '0' },
            { id: 5, source: 8, target: 9, type: '0' },
            { id: 6, source: 9, target: 15, type: '0' },
            { id: 7, source: 15, target: 11, type: '0' },
            { id: 8, source: 11, target: 12, type: '0' },
            { id: 9, source: 12, target: 13, type: '0' },
            { id: 10, source: 13, target: 14, type: '0' },
            { id: 11, source: 14, target: 16, type: '0' },
            { id: 12, source: 16, target: 18, type: '0' },
            { id: 13, source: 18, target: 19, type: '0' },
            { id: 14, source: 19, target: 20, type: '0' }
        ];
        return {
            data: tasks,
            links,
            customColumns: [],
            hiddenColumns: ['wbs', 'predecessors', 'successors', 'link_lag', 'progress', 'resource', 'owner', 'total_float', 'constraint_type', 'bar_color', 'collapse'],
            columnWidths: {},
            columnOrder: ['hierarchy', 'activity_id', 'text', 'duration', 'start_date', 'end_date'],
            settings: {
                timeline_pct: 0.48,
                grid_overlay_width_px: 660,
                default_row_height: 24,
                default_bar_height: 16,
                link_color: '#c00000',
                link_width: 1,
                timescale: 'day',
                data_date: '2023-06-15'
            }
        };
    }

    function isBareProjectSchedule(payload) {
        const data = payload?.data || [];
        if (data.length !== 1) return false;
        const only = data[0];
        return only && (only.type === 'project' || !only.parent) && !data.some(t => t.parent && String(t.parent) !== '0');
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

    function resolveColumnWidth(col) {
        if (!col) return 80;
        if (col.name === '_sched_add_col') {
            return parseInt(columnWidths[col.name] || columnDefWidths[col.name] || 36, 10) || 36;
        }
        const saved = columnWidths[col.name];
        if (saved != null && saved !== '') return parseInt(saved, 10) || 80;
        if (columnDefWidths[col.name] != null) return columnDefWidths[col.name];
        return parseInt(col.width, 10) || 80;
    }

    function restoreColumnWidthsFromConfig() {
        if (!ganttReady || !gantt.config.columns) return;
        gantt.config.columns.forEach((col, index) => {
            const w = resolveColumnWidth(col);
            col.width = w;
            if (gantt.config.columns[index]) gantt.config.columns[index].width = w;
        });
    }

    function getColumnsTotalWidth() {
        if (!gantt.config.columns) return 900;
        return gantt.config.columns.reduce((sum, col) => sum + resolveColumnWidth(col), 0);
    }

    function isAddColumnCol(col) {
        return col && col.name === '_sched_add_col';
    }

    function getColumnLayoutMetrics() {
        const cols = gantt.config.columns || [];
        const metrics = [];
        let left = 0;
        cols.forEach(col => {
            const w = resolveColumnWidth(col);
            metrics.push({ name: col.name, width: w, left, col });
            left += w;
        });
        return { columns: metrics, total: left };
    }

    function applyMetricToCell(cell, m, col, opts) {
        if (!cell || !m) return;
        const isHead = opts?.head === true;
        cell.style.position = 'absolute';
        cell.style.left = m.left + 'px';
        cell.style.right = 'auto';
        cell.style.width = m.width + 'px';
        cell.style.minWidth = m.width + 'px';
        cell.style.maxWidth = m.width + 'px';
        cell.style.flex = 'none';
        cell.style.flexGrow = '0';
        cell.style.flexShrink = '0';
        cell.style.boxSizing = 'border-box';
        if (!isHead) {
            cell.style.top = '0';
            cell.style.height = '100%';
        }
        if (col) cell.classList.toggle('sched-add-col-cell', isAddColumnCol(col));
    }

    function ensureGridScrollWidthSentinel(total) {
        const gridData = document.querySelector('#gantt_here .gantt_grid_data');
        const gridScale = document.querySelector('#gantt_here .gantt_grid_scale');
        [gridData, gridScale].forEach(host => {
            if (!host) return;
            let sentinel = host.querySelector(':scope > .sched-grid-scroll-sentinel');
            if (!sentinel) {
                sentinel = document.createElement('div');
                sentinel.className = 'sched-grid-scroll-sentinel';
                sentinel.setAttribute('aria-hidden', 'true');
                host.appendChild(sentinel);
            }
            sentinel.style.width = total + 'px';
            sentinel.style.height = '1px';
            sentinel.style.position = 'absolute';
            sentinel.style.left = '0';
            sentinel.style.top = '0';
            sentinel.style.pointerEvents = 'none';
            sentinel.style.visibility = 'hidden';
            sentinel.style.zIndex = '-1';
        });
    }

    function hideNativeColumnResizeWraps() {
        document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_column_resize_wrap:not(.sched-col-resize-grip)').forEach(wrap => {
            wrap.style.display = 'none';
            wrap.style.pointerEvents = 'none';
        });
    }

    function findColumnResizeIndex(clientX, clientY) {
        const scale = document.querySelector('#gantt_here .gantt_grid_scale');
        if (!scale) return -1;
        const scaleRect = scale.getBoundingClientRect();
        const headerTop = scaleRect.top + GRID_HEADER_TOP_H;
        const headerBottom = headerTop + GRID_HEADER_LABEL_H;
        if (clientY < headerTop - 4 || clientY > headerBottom + 4) return -1;
        const scrollLeft = scale.scrollLeft || 0;
        const xInContent = clientX - scaleRect.left + scrollLeft;
        const { columns } = getColumnLayoutMetrics();
        const hit = 10;
        for (let i = 0; i < columns.length; i++) {
            const col = columns[i].col;
            if (!col || col.resize === false || isAddColumnCol(col)) continue;
            const edge = columns[i].left + columns[i].width;
            if (Math.abs(xInContent - edge) <= hit) return i;
        }
        return -1;
    }

    function ensureAllColumnResizeGrips() {
        if (!ganttReady) return;
        const gridHead = document.querySelector('#gantt_here .gantt_grid_scale .gantt_grid_head');
        if (!gridHead) return;

        hideNativeColumnResizeWraps();

        const { columns: metrics, total } = getColumnLayoutMetrics();
        const cols = gantt.config.columns || [];

        let layer = gridHead.querySelector('.sched-col-grip-layer');
        if (!layer) {
            layer = document.createElement('div');
            layer.className = 'sched-col-grip-layer';
            gridHead.appendChild(layer);
        }
        layer.style.width = total + 'px';
        layer.style.height = '100%';
        layer.style.position = 'absolute';
        layer.style.top = '0';
        layer.style.left = '0';
        layer.style.pointerEvents = 'none';
        layer.style.zIndex = '200';
        layer.innerHTML = '';

        metrics.forEach((m, i) => {
            const col = cols[i];
            if (!col || col.resize === false || isAddColumnCol(col)) return;
            const grip = document.createElement('div');
            grip.className = 'sched-col-resize-grip gantt_grid_column_resize_wrap';
            grip.dataset.colIndex = String(i);
            grip.title = 'Drag to resize column';
            grip.innerHTML = '<div class="gantt_grid_column_resize"></div>';
            grip.style.left = (m.left + m.width) + 'px';
            layer.appendChild(grip);
        });
    }

    function applyColumnWidthsToDom() {
        if (!ganttReady) return;
        restoreColumnWidthsFromConfig();
        const cols = gantt.config.columns || [];
        const { columns: metrics, total } = getColumnLayoutMetrics();
        gantt.config.grid_width = total;
        gantt.config.keep_grid_width = true;

        const headCells = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
        const headCount = Math.min(headCells.length, metrics.length);
        for (let i = 0; i < headCount; i++) {
            applyMetricToCell(headCells[i], metrics[i], cols[i], { head: true });
            if (cols[i]?.name === '_sched_add_col') headCells[i].classList.add('sched-add-col-header');
        }

        const gridHead = document.querySelector('#gantt_here .gantt_grid_scale .gantt_grid_head');
        if (gridHead) {
            gridHead.style.position = 'relative';
            gridHead.style.width = total + 'px';
            gridHead.style.minWidth = total + 'px';
            gridHead.style.maxWidth = 'none';
        }
        const gridScale = document.querySelector('#gantt_here .gantt_grid_scale');
        if (gridScale) {
            gridScale.style.width = '100%';
            gridScale.style.minWidth = '0';
            gridScale.style.maxWidth = '100%';
        }
        const gridData = document.querySelector('#gantt_here .gantt_grid_data');
        if (gridData) {
            gridData.style.width = '100%';
            gridData.style.minWidth = '0';
            gridData.style.maxWidth = '100%';
        }

        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(row => {
            row.style.width = total + 'px';
            row.style.minWidth = total + 'px';
            row.style.maxWidth = 'none';
            const cells = row.querySelectorAll(':scope > .gantt_cell');
            const cellCount = Math.min(cells.length, metrics.length);
            for (let i = 0; i < cellCount; i++) {
                applyMetricToCell(cells[i], metrics[i], cols[i]);
            }
        });

        const gridInner = document.querySelector('#gantt_here .gantt_grid');
        if (gridInner) {
            gridInner.style.width = '100%';
            gridInner.style.minWidth = '0';
            gridInner.style.maxWidth = 'none';
        }
        const host = document.getElementById('gantt_here');
        if (host) host.style.setProperty('--sched-grid-min-width', total + 'px');

        syncGridScrollContentWidth(total);
        ensureGridScrollWidthSentinel(total);
        ensureAllColumnResizeGrips();
    }

    function syncGridScrollContentWidth(totalWidth) {
        const total = totalWidth || getColumnsTotalWidth();
        const scrollHost = document.querySelector('#gantt_here [data-cell-id="gridScroll"]');
        if (!scrollHost) return;
        scrollHost.style.width = '100%';
        scrollHost.style.overflowX = 'auto';
        const horScroll = scrollHost.querySelector('.gantt_hor_scroll') || scrollHost;
        horScroll.style.overflowX = 'auto';
        const inner = horScroll.querySelector(':scope > div') || horScroll.firstElementChild;
        if (inner) {
            inner.style.width = total + 'px';
            inner.style.minWidth = total + 'px';
        }
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
            if (name === '_sched_add_col') return;
            if (map.has(name)) {
                ordered.push(map.get(name));
                map.delete(name);
            }
        });
        map.forEach(c => ordered.push(c));
        return ordered;
    }

    function isOverlayMode() {
        return document.getElementById('scheduleGanttHost')?.classList.contains('schedule-overlay-mode');
    }

    function setOverlayElStyle(el, props) {
        if (!el) return;
        Object.entries(props).forEach(([key, val]) => {
            el.style.setProperty(key, val, 'important');
        });
    }

    function getGridPaneWidth() {
        return getGridOverlayWidth();
    }

    function getGridOverlayWidth() {
        const hostW = document.getElementById('gantt_here')?.offsetWidth
            || document.getElementById('scheduleGanttHost')?.clientWidth
            || 1200;
        const scrollW = gantt.config?.scroll_size || 16;
        const minOverlay = 0;
        const maxOverlay = Math.max(0, hostW - scrollW);
        const clamp = w => Math.max(minOverlay, Math.min(maxOverlay, w));
        if (scheduleSettings.grid_overlay_width_px != null && scheduleSettings.grid_overlay_width_px >= 0) {
            return clamp(scheduleSettings.grid_overlay_width_px);
        }
        if (scheduleSettings.timeline_width_px >= 180) {
            return clamp(hostW - scheduleSettings.timeline_width_px);
        }
        const gridPct = 1 - (scheduleSettings.timeline_pct ?? 0.48);
        return clamp(Math.round(hostW * gridPct));
    }

    function getTimelineWidth() {
        return getTimelineDomWidth();
    }

    function getTimelineDomWidth() {
        const hostW = document.getElementById('gantt_here')?.offsetWidth
            || document.getElementById('scheduleGanttHost')?.clientWidth
            || 1200;
        if (isOverlayMode()) {
            const scrollW = gantt.config?.scroll_size || 16;
            return Math.max(220, hostW - scrollW);
        }
        return Math.max(240, hostW - getGridOverlayWidth() - 24);
    }

    function getTimelineScrollMargin(fraction) {
        if (isOverlayMode()) {
            return getGridOverlayWidth() + 32;
        }
        const viewW = getTimelineDomWidth();
        if (fraction != null) return Math.round(viewW * fraction);
        return Math.round(viewW / 2);
    }

    function applyOverlayDomLayout() {
        if (!isOverlayMode()) return;
        const host = document.getElementById('gantt_here');
        const root = host?.querySelector('.gantt_layout_root');
        if (!host || !root) return;

        const hostW = host.clientWidth;
        const colsW = getColumnsTotalWidth();
        const overlayW = getGridOverlayWidth();

        const scrollW = gantt.config.scroll_size || 16;
        const chartW = Math.max(hostW - scrollW, 200);

        host.style.setProperty('--sched-grid-overlay-w', overlayW + 'px');
        host.style.setProperty('--sched-chart-left', overlayW + 'px');
        host.style.setProperty('--sched-grid-min-width', colsW + 'px');

        const cells = root.querySelectorAll(':scope > .gantt_layout_cell');
        const gridCell = cells[0];
        const resizerCell = cells[1];
        const timelineCell = cells[2];
        const verScroll = cells[3];

        setOverlayElStyle(resizerCell, {
            display: 'none',
            width: '0',
            'min-width': '0',
            'max-width': '0',
            flex: '0 0 0',
            padding: '0',
            margin: '0',
            border: 'none',
            overflow: 'hidden'
        });

        setOverlayElStyle(gridCell, {
            position: 'absolute',
            left: '0',
            top: '0',
            bottom: '0',
            width: overlayW + 'px',
            height: '100%',
            'z-index': '30',
            flex: 'none',
            overflow: 'hidden',
            background: 'var(--sched-bg, #1e1e1e)',
            'box-sizing': 'border-box',
            border: 'none',
            'box-shadow': 'none',
            'pointer-events': 'auto'
        });

        const gridInner = gridCell?.querySelector('.gantt_grid');
        if (gridInner) {
            gridInner.style.minWidth = '0';
            gridInner.style.width = '100%';
            gridInner.style.maxWidth = 'none';
        }

        setOverlayElStyle(timelineCell, {
            position: 'absolute',
            left: '0',
            top: '0',
            bottom: '0',
            right: scrollW + 'px',
            width: chartW + 'px',
            'min-width': chartW + 'px',
            'max-width': 'none',
            height: '100%',
            'z-index': '1',
            flex: 'none',
            overflow: 'hidden',
            'box-sizing': 'border-box',
            'pointer-events': 'auto'
        });

        setOverlayElStyle(verScroll, {
            position: 'relative',
            'z-index': '25',
            flex: '0 0 ' + scrollW + 'px',
            width: scrollW + 'px',
            'min-width': scrollW + 'px',
            height: '100%',
            'margin-left': 'auto'
        });

        setOverlayElStyle(root, {
            position: 'relative',
            width: '100%',
            height: '100%',
            display: 'flex',
            'flex-direction': 'row',
            overflow: 'hidden'
        });

        positionChartResizerVisual();
    }

    function syncLayoutTimelineWidth() {
        const hostW = document.getElementById('gantt_here')?.offsetWidth || 1000;
        if (isOverlayMode()) {
            if (gantt.config.layout?.cols?.[0]) gantt.config.layout.cols[0].width = getGridOverlayWidth();
            if (gantt.config.layout?.cols?.[2]) gantt.config.layout.cols[2].width = hostW;
            return;
        }
        const gridPaneW = getGridOverlayWidth();
        const timelineW = Math.max(240, hostW - gridPaneW - 24);
        if (gantt.config.layout?.cols?.[0]) gantt.config.layout.cols[0].width = gridPaneW;
        if (gantt.config.layout?.cols?.[2]) gantt.config.layout.cols[2].width = timelineW;
    }

    function syncGridColumnsFromConfig() {
        if (!ganttReady || !gantt.config.columns) return;
        syncColumnWidthsToConfig();
        const total = getColumnsTotalWidth();
        gantt.config.grid_width = total;
        gantt.config.keep_grid_width = true;
        const host = document.getElementById('gantt_here');
        if (host) host.style.setProperty('--sched-grid-min-width', total + 'px');
        applyColumnWidthsToDom();
    }

    function syncGridTableWidth() {
        syncGridColumnsFromConfig();
    }

    let headerSyncTimer = null;

    function syncColumnWidthsToConfig() {
        if (!ganttReady || !gantt.config.columns) return;
        restoreColumnWidthsFromConfig();
    }

    function queueColumnResizeHandleSync() { /* native dhtmlx handles resize grips */ }

    function syncGridHeaderAlignment() {
        syncGridColumnsFromConfig();
    }

    function queueGridHeaderSync() {
        clearTimeout(headerSyncTimer);
        headerSyncTimer = setTimeout(() => {
            syncGridColumnsFromConfig();
            applyCellAlignToDom();
            ensureColumnResizeGrips();
        }, 32);
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
        syncGanttLayout();
        if (persist) queueSave();
    }

    function positionChartResizerVisual() {
        const host = document.getElementById('scheduleGanttHost');
        const handle = document.getElementById('scheduleChartResizer');
        if (!handle || !host) return;
        if (!host.classList.contains('schedule-overlay-mode')) {
            handle.classList.add('hidden');
            return;
        }
        handle.classList.remove('hidden');
        const hostRect = host.getBoundingClientRect();
        const hostW = hostRect.width || host.clientWidth;
        const overlayW = getGridOverlayWidth();
        handle.style.left = Math.max(0, overlayW - 3) + 'px';
        handle.style.right = 'auto';
    }

    let layoutSyncInProgress = false;
    let layoutSyncPending = false;
    let lastOverlayKey = '';
    let lastGridWidthKey = '';

    function syncGanttLayout(options = {}) {
        if (!ganttReady || columnResizeInProgress) return;
        if (layoutSyncInProgress) {
            layoutSyncPending = true;
            return;
        }

        const root = document.querySelector('#gantt_here .gantt_layout_root');
        if (!root) return;

        const gridW = getColumnsTotalWidth();
        const host = document.getElementById('gantt_here');
        const hostW = host?.clientWidth || root.clientWidth || 1200;
        const isOverlay = isOverlayMode();
        const gridPaneW = getGridOverlayWidth();
        const timelineW = isOverlay ? hostW : Math.max(240, hostW - gridPaneW - 24);
        const sizeKey = `${hostW}|${gridW}|${gridPaneW}|${isOverlay}`;
        const gridKey = String(gridW);

        layoutSyncInProgress = true;
        try {
            if (host) {
                host.style.setProperty('--sched-grid-min-width', gridW + 'px');
                host.style.setProperty('--sched-grid-overlay-w', gridPaneW + 'px');
                host.style.setProperty('--sched-chart-left', gridPaneW + 'px');
                host.style.setProperty('--sched-timeline-width', timelineW + 'px');
            }

            gantt.config.grid_width = gridW;
            gantt.config.keep_grid_width = true;

            const cells = root.querySelectorAll(':scope > .gantt_layout_cell');

            if (gantt.config.layout?.cols?.[0]) {
                gantt.config.layout.cols[0].width = gridPaneW;
                gantt.config.layout.cols[0].min_width = isOverlay ? 0 : Math.max(gridW + 8, 200);
            }
            if (gantt.config.layout?.cols?.[2]) {
                gantt.config.layout.cols[2].width = isOverlay ? hostW : timelineW;
                gantt.config.layout.cols[2].min_width = isOverlay ? hostW : 220;
            }
            const gridCell = cells[0];
            const timelineCell = cells[2];
            if (timelineCell) ensureTimelineOverlayWidgets(timelineCell);
            const gridInner = gridCell?.querySelector('.gantt_grid');
            if (gridInner) {
                gridInner.style.minWidth = '0';
                gridInner.style.width = '100%';
                gridInner.style.maxWidth = 'none';
            }

            syncLayoutTimelineWidth();

            const needsSetSizes = !isOverlay && !options.skipSetSizes && sizeKey !== lastOverlayKey && !options.light;
            if (needsSetSizes && typeof gantt.setSizes === 'function') {
                lastOverlayKey = sizeKey;
                lastGridWidthKey = gridKey;
                gantt.setSizes();
            } else {
                applyColumnWidthsToDom();
            }

            if (isOverlay) applyOverlayDomLayout();
            else positionChartResizerVisual();
            if (!options.light) {
                ensureTimelineScrollbar();
                refreshTimelinePanBar();
            }
        } finally {
            layoutSyncInProgress = false;
            if (layoutSyncPending) {
                layoutSyncPending = false;
                queueGanttLayoutSync();
            }
        }
    }

    function queueGanttLayoutSync() {
        clearTimeout(overlayApplyTimer);
        overlayApplyTimer = setTimeout(syncGanttLayout, 16);
    }

    const overlayDrag = { active: false, bound: false, startX: 0, startW: 0 };

    function bindChartResizer() {
        if (overlayDrag.bound) return;
        overlayDrag.bound = true;

        document.addEventListener('mousedown', e => {
            const host = document.getElementById('scheduleGanttHost');
            if (!host?.classList.contains('schedule-overlay-mode')) return;
            const handle = document.getElementById('scheduleChartResizer');
            const onHandle = handle && (e.target === handle || handle.contains(e.target));
            let nearDivider = false;
            if (!onHandle) {
                const hostEl = document.getElementById('gantt_here');
                const hostRect = hostEl?.getBoundingClientRect();
                if (hostRect) {
                    const dividerX = hostRect.left + getGridOverlayWidth();
                    nearDivider = e.clientY >= hostRect.top && e.clientY <= hostRect.bottom
                        && Math.abs(e.clientX - dividerX) <= 12;
                }
            }
            if (!onHandle && !nearDivider) return;
            overlayDrag.active = true;
            overlayDrag.startX = e.clientX;
            overlayDrag.startW = getGridOverlayWidth();
            document.body.classList.add('schedule-chart-resizing');
            e.preventDefault();
            e.stopPropagation();
        });

        document.addEventListener('mousemove', e => {
            if (!overlayDrag.active) return;
            const hostEl = document.getElementById('gantt_here');
            if (!hostEl) return;
            const rect = hostEl.getBoundingClientRect();
            const dx = e.clientX - overlayDrag.startX;
            const scrollW = gantt.config?.scroll_size || 16;
            const maxW = Math.max(0, rect.width - scrollW);
            const gridW = Math.max(0, Math.min(maxW, overlayDrag.startW + dx));
            scheduleSettings.grid_overlay_width_px = gridW;
            scheduleSettings.timeline_width_px = null;
            scheduleSettings.timeline_pct = 1 - (gridW / rect.width);
            applyOverlayDomLayout();
            syncGanttLayout({ skipSetSizes: true, light: true });
        });

        document.addEventListener('mouseup', () => {
            if (!overlayDrag.active) return;
            overlayDrag.active = false;
            document.body.classList.remove('schedule-chart-resizing');
            queueSave();
        });
    }

    function persistLayoutPaneWidths() {
        if (!ganttReady) return;
        const host = document.getElementById('scheduleGanttHost');
        if (!host?.classList.contains('schedule-overlay-mode')) return;
        const overlayW = getGridOverlayWidth();
        if (overlayW >= 0 && Math.abs((scheduleSettings.grid_overlay_width_px || 0) - overlayW) > 4) {
            scheduleSettings.grid_overlay_width_px = overlayW;
            const hostW = document.getElementById('gantt_here')?.clientWidth;
            if (hostW) scheduleSettings.timeline_pct = 1 - (overlayW / hostW);
            scheduleSettings.timeline_width_px = null;
            queueSave();
        }
    }

    function bindLayoutResizePersistence() {
        if (bindLayoutResizePersistence.done) return;
        bindLayoutResizePersistence.done = true;
        document.addEventListener('mouseup', persistLayoutPaneWidths);
    }

    function initGanttLayout() {
        if (scheduleSettings.timeline_width_px == null && scheduleSettings.timeline_pct == null) {
            scheduleSettings.timeline_pct = 0.45;
        } else if (scheduleSettings.timeline_pct != null && scheduleSettings.timeline_pct > 0.7) {
            scheduleSettings.timeline_pct = 0.45;
            scheduleSettings.timeline_width_px = null;
        }
        const host = document.getElementById('scheduleGanttHost');
        host?.classList.remove('schedule-split-mode');
        host?.classList.add('schedule-overlay-mode');
        bindChartResizer();
        bindColumnResizeDrag();
        bindLayoutResizePersistence();

        if (!initGanttLayout.resizeBound) {
            initGanttLayout.resizeBound = true;
            window.addEventListener('resize', () => {
                const hostW = document.getElementById('gantt_here')?.offsetWidth;
                if (hostW && scheduleSettings.timeline_pct) {
                    scheduleSettings.timeline_width_px = Math.round(hostW * scheduleSettings.timeline_pct);
                }
                queueGanttLayoutSync();
            });
        }

        queueGanttLayoutSync();
    }

    function updateGridWidth() {
        syncGridTableWidth();
        queueGanttLayoutSync();
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
        if (ganttReady) {
            gantt.eachTask(t => {
                const ts = toGanttDate(t.start_date);
                const te = toGanttDate(t.end_date);
                if (ts) {
                    const padded = ganttDateAdd(ts, -60, 'day');
                    if (padded && padded < start) start = padded;
                }
                if (te) {
                    const padded = ganttDateAdd(te, 120, 'day');
                    if (padded && padded > end) end = padded;
                }
            });
        }
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
                syncGanttLayout();
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
        const timelineRowH = GRID_HEADER_TOTAL_H / 2;
        gantt.config.scale_height = Math.max(GRID_HEADER_TOTAL_H, rows * timelineRowH);
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
        const margin = marginPx != null ? marginPx : getTimelineScrollMargin(0.5);
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
            syncGanttLayout();
        });
    }

    function scrollToToday() {
        if (!ganttReady) return;
        const today = document.getElementById('dataDateInput')?.value || CasePMSchedule.formatDate(new Date());
        scrollTimelineToDate(today, getTimelineWidth() / 2);
        syncGanttLayout();
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
        syncGanttLayout();
    }

    function applyTimelineDateRange() {
        applyRollingCalendarRange(false);
    }

    function updateRowHeightsForLabels() {
        refreshGanttRowMetrics();
    }

    function getTaskRowHeight(task) {
        if (!task) return scheduleSettings.default_row_height || 24;
        const custom = parseInt(task.row_height, 10);
        if (!Number.isNaN(custom) && custom >= 18) return custom;
        return scheduleSettings.default_row_height || 24;
    }

    function getTaskBarHeight(task) {
        if (!task) return scheduleSettings.default_bar_height || 14;
        const custom = parseInt(task.bar_height, 10);
        if (!Number.isNaN(custom) && custom >= 6) return custom;
        if (isSummaryTask(task)) {
            return scheduleSettings.summary_bar_height || 10;
        }
        return scheduleSettings.default_bar_height || 14;
    }

    function buildTaskBarStyle(task) {
        const color = resolveBarColor(task);
        const barH = getTaskBarHeight(task);
        const parts = [
            `--dhx-gantt-task-background:${color}`,
            `--dhx-gantt-task-border:${color}`,
            `background-color:${color} !important`,
            `height:${barH}px`,
            `min-height:${barH}px`,
            `max-height:${barH}px`
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

    function applyP6RowMetrics() {
        const baseRow = 24;
        const barH = scheduleSettings.default_bar_height || 16;
        scheduleSettings.default_row_height = baseRow;
        if (!scheduleSettings.default_bar_height || scheduleSettings.default_bar_height < 8) {
            scheduleSettings.default_bar_height = 16;
        }
        if (!scheduleSettings.summary_bar_height || scheduleSettings.summary_bar_height < 6) {
            scheduleSettings.summary_bar_height = 12;
        }
        scheduleSettings.summary_row_height = baseRow;
        if (!ganttReady) return;
        gantt.config.row_height = baseRow;
        gantt.config.bar_height = barH;
        gantt.config.scale_height = GRID_HEADER_TOTAL_H;
        gantt.getTaskHeight = () => baseRow;
        const host = document.getElementById('gantt_here');
        if (host) {
            host.style.setProperty('--sched-row-h', baseRow + 'px');
            host.style.setProperty('--sched-bar-h', barH + 'px');
            host.style.setProperty('--sched-summary-bar-h', (scheduleSettings.summary_bar_height || 12) + 'px');
            host.style.setProperty('--sched-grid-header-total', GRID_HEADER_TOTAL_H + 'px');
            host.style.setProperty('--sched-grid-header-top', GRID_HEADER_TOP_H + 'px');
            host.style.setProperty('--sched-grid-header-label', GRID_HEADER_LABEL_H + 'px');
        }
    }

    function refreshGanttRowMetrics() {
        applyP6RowMetrics();
    }

    function applyRowHeightsToDom() {
        /* dhtmlx keeps grid + chart row heights in sync via getTaskHeight */
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
        const color = normalizeHexColor(obj?.color);
        if (color) out.color = color;
        return out;
    }

    function getDefaultCellFontSize() {
        return scheduleSettings.default_cell_style?.font_size || 13;
    }

    function getDefaultCellColor() {
        return normalizeHexColor(scheduleSettings.default_cell_style?.color) || '';
    }

    function getCellFontSize(task, colName) {
        const cell = task?.cell_align?.[colName];
        const col = scheduleSettings.column_align?.[colName];
        const fs = cell?.font_size || col?.font_size || getDefaultCellFontSize();
        const n = parseInt(fs, 10);
        return (!Number.isNaN(n) && n >= 9 && n <= 24) ? n : 13;
    }

    function getCellFontColor(task, colName) {
        const cell = task?.cell_align?.[colName];
        const col = scheduleSettings.column_align?.[colName];
        return normalizeHexColor(cell?.color || col?.color || getDefaultCellColor()) || '';
    }

    function getDefaultCellAlign() {
        return normalizeCellAlign(scheduleSettings.default_cell_align || { h: 'left', v: 'middle' });
    }

    function getCellAlign(task, colName) {
        const cell = task?.cell_align?.[colName];
        const col = scheduleSettings.column_align?.[colName];
        const colDef = getColumnDefaultAlign(colName);
        const def = getDefaultCellAlign();
        return normalizeCellAlign({
            h: cell?.h || col?.h || colDef.h || def.h,
            v: cell?.v || col?.v || colDef.v || def.v
        });
    }

    function getHeaderCellAlign(colName) {
        const col = scheduleSettings.column_align?.[colName];
        const colDef = getColumnDefaultAlign(colName);
        const def = getDefaultCellAlign();
        return normalizeCellAlign({
            h: col?.h || colDef.h || def.h,
            v: col?.v || colDef.v || def.v
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
                if (col.name === 'hierarchy') cell.classList.add('sched-hierarchy-cell');
                cell.style.fontSize = getCellFontSize(task, col.name) + 'px';
                const fontColor = getCellFontColor(task, col.name);
                cell.style.color = fontColor || '';
            });
        });
        applyRowHighlight();
        applyColumnHighlight();
        applyCellFocusHighlight();
        document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell').forEach((head, i) => {
            const col = gantt.config.columns[i];
            head.classList.toggle('sched-col-selected', !!(gridSelection.type === 'column' && col && gridSelection.colName === col.name));
            head.classList.toggle('sched-col-active', !!(gridSelection.type === 'column' && col && gridSelection.colName === col.name));
            if (!col) return;
            const a = getHeaderCellAlign(col.name);
            head.classList.remove(
                'sched-align-h-left', 'sched-align-h-center', 'sched-align-h-right',
                'sched-align-v-top', 'sched-align-v-middle', 'sched-align-v-bottom'
            );
            head.classList.add(`sched-align-h-${a.h}`, `sched-align-v-${a.v}`);
        });
    }

    function getActiveRowTaskId() {
        if (gridSelection.type === 'row' || gridSelection.type === 'cell') return gridSelection.taskId;
        return gantt.getSelectedId();
    }

    function getActiveTaskId() {
        return getActiveRowTaskId() || null;
    }

    function applyColumnHighlight() {
        if (!ganttReady) return;
        const selCol = gridSelection.type === 'column' ? gridSelection.colName : null;
        const colIdx = selCol ? gantt.config.columns.findIndex(c => c.name === selCol) : -1;
        document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row').forEach(row => {
            row.querySelectorAll(':scope > .gantt_cell').forEach((cell, i) => {
                cell.classList.toggle('sched-col-active', colIdx >= 0 && i === colIdx);
            });
        });
        const scale = document.querySelector('#gantt_here .gantt_grid_scale');
        if (!scale) return;
        const gridHead = scale.querySelector('.gantt_grid_head');
        if (!gridHead) return;
        let overlay = gridHead.querySelector('.sched-col-select-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'sched-col-select-overlay';
            gridHead.appendChild(overlay);
        }
        scale.querySelector(':scope > .sched-col-select-overlay')?.remove();
        if (colIdx < 0) {
            overlay.style.display = 'none';
            scale.classList.remove('sched-col-bar-selected');
            return;
        }
        const head = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell')[colIdx];
        const { columns: metrics } = getColumnLayoutMetrics();
        const m = metrics[colIdx];
        if (!m) {
            overlay.style.display = 'none';
            return;
        }
        overlay.style.display = 'block';
        overlay.style.left = m.left + 'px';
        overlay.style.width = m.width + 'px';
        scale.classList.add('sched-col-bar-selected');
    }

    function applyRowHighlight() {
        if (!ganttReady) return;
        if (gridSelection.type === 'cell' || floatingEditorActive) {
            document.querySelectorAll('#gantt_here .gantt_row.sched-row-active, #gantt_here .gantt_task_row.sched-row-active')
                .forEach(r => r.classList.remove('sched-row-active'));
            return;
        }
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

    function applyCellFocusHighlight() {
        if (!ganttReady) return;
        document.querySelectorAll('#gantt_here .gantt_cell.sched-cell-focus').forEach(c => c.classList.remove('sched-cell-focus'));
        if (gridSelection.type === 'cell' && gridSelection.taskId && gridSelection.colName) {
            const cell = findGridCell(gridSelection.taskId, gridSelection.colName);
            if (cell) cell.classList.add('sched-cell-focus');
        }
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
        const fsInp = document.getElementById('schedFontSizeInput');
        if (fsInp && gridSelection.type === 'cell' && gridSelection.taskId && gridSelection.colName) {
            fsInp.value = String(getCellFontSize(gantt.getTask(gridSelection.taskId), gridSelection.colName));
        } else if (fsInp && gridSelection.type === 'column' && gridSelection.colName) {
            const col = scheduleSettings.column_align?.[gridSelection.colName];
            fsInp.value = String(col?.font_size || getDefaultCellFontSize());
        }
        const colorInp = document.getElementById('schedFontColorInput');
        if (colorInp && gridSelection.type === 'cell' && gridSelection.taskId && gridSelection.colName) {
            colorInp.value = getCellFontColor(gantt.getTask(gridSelection.taskId), gridSelection.colName) || '#d4d4d4';
        } else if (colorInp && gridSelection.type === 'column' && gridSelection.colName) {
            const col = scheduleSettings.column_align?.[gridSelection.colName];
            colorInp.value = normalizeHexColor(col?.color) || getDefaultCellColor() || '#d4d4d4';
        }
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
                    delete t.cell_align[sel.colName][axis];
                    if (!Object.keys(t.cell_align[sel.colName]).length) delete t.cell_align[sel.colName];
                    if (!Object.keys(t.cell_align).length) delete t.cell_align;
                }
            });
            applyCellAlignToDom();
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

    function getColumnIndexFromHeaderX(clientX, heads) {
        const list = heads || document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
        for (let i = 0; i < list.length; i++) {
            const r = list[i].getBoundingClientRect();
            if (clientX >= r.left - 2 && clientX < r.right + 2) return i;
        }
        return -1;
    }

    function getColumnLabel(name) {
        const col = (gantt.config.columns || []).find(c => c.name === name);
        return col?.label || name || '';
    }

    function isMovableColumn(col) {
        if (!col) return false;
        return !isAddColumnCol(col) && col.name !== 'hierarchy' && col.name !== 'collapse';
    }

    function scrollColumnIntoView(colName) {
        const idx = gantt.config.columns.findIndex(c => c.name === colName);
        if (idx < 0) return;
        const head = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell')[idx];
        if (!head) return;
        const left = head.offsetLeft;
        const right = left + head.offsetWidth;
        const viewEl = document.querySelector('#gantt_here .gantt_grid_data')
            || document.querySelector('#gantt_here .gantt_grid_scale');
        if (!viewEl) return;
        const viewLeft = viewEl.scrollLeft;
        const viewRight = viewLeft + viewEl.clientWidth;
        if (left < viewLeft) preserveGridScrollLeft(Math.max(0, left - 8));
        else if (right > viewRight) preserveGridScrollLeft(right - viewEl.clientWidth + 8);
    }

    function selectGridColumn(colName) {
        if (!colName || isAddColumnCol({ name: colName })) return;
        gridSelection = { type: 'column', colName };
        if (typeof gantt.unselectTask === 'function') gantt.unselectTask();
        highlightGridSelection();
        scrollColumnIntoView(colName);
    }

    function removeSelectedColumn() {
        if (gridSelection.type !== 'column' || !gridSelection.colName) {
            return showScheduleAlert('Select a column header first, then press Delete or use Columns manager.', 'warning');
        }
        const name = gridSelection.colName;
        if (REQUIRED_COLUMNS.includes(name) || name === 'hierarchy') {
            return showScheduleAlert('This column cannot be removed.', 'warning');
        }
        const label = getColumnLabel(name);
        if (!confirm(`Remove column "${label}" from the grid?`)) return;
        removeColumn(name, { refreshManager: false });
        gridSelection = { type: null };
        highlightGridSelection();
    }

    function moveGridColumn(fromIdx, toIdx) {
        const cols = gantt.config.columns || [];
        if (fromIdx === toIdx || fromIdx < 0 || toIdx < 0 || fromIdx >= cols.length || toIdx >= cols.length) return;
        const fromCol = cols[fromIdx];
        const toCol = cols[toIdx];
        if (!isMovableColumn(fromCol) || !toCol || isAddColumnCol(toCol)) return;
        const names = cols.map(c => c.name).filter(n => n !== '_sched_add_col');
        const [moved] = names.splice(fromIdx, 1);
        names.splice(toIdx, 0, moved);
        columnOrder = names;
        scheduleSettings.column_order = names.slice();
        gantt.config.columns = buildColumnConfig();
        if (gridSelection.type === 'column') gridSelection.colName = moved;
        updateGridWidth();
        gantt.render();
        queueSave();
        logActivity('Moved column', moved);
    }

    function bindGridHorizontalScrollSync() {
        const gridData = document.querySelector('#gantt_here .gantt_grid_data');
        const scale = document.querySelector('#gantt_here .gantt_grid_scale');
        const scrollHost = document.querySelector('#gantt_here [data-cell-id="gridScroll"]');
        const horScroll = scrollHost?.querySelector('.gantt_hor_scroll') || scrollHost;
        if (!gridData || !scale) return;

        let syncing = false;
        const applyScroll = left => {
            if (syncing) return;
            syncing = true;
            if (gridData && Math.abs(gridData.scrollLeft - left) > 0.5) gridData.scrollLeft = left;
            if (scale && Math.abs(scale.scrollLeft - left) > 0.5) scale.scrollLeft = left;
            if (horScroll && horScroll !== scrollHost && Math.abs(horScroll.scrollLeft - left) > 0.5) horScroll.scrollLeft = left;
            if (scrollHost && Math.abs(scrollHost.scrollLeft - left) > 0.5) scrollHost.scrollLeft = left;
            syncing = false;
            applyColumnHighlight();
            ensureAllColumnResizeGrips();
        };

        if (!gridData.dataset.hscrollBound) {
            gridData.dataset.hscrollBound = '1';
            [horScroll, scrollHost, gridData, scale].filter(Boolean).forEach(el => {
                el.addEventListener('scroll', () => applyScroll(el.scrollLeft), { passive: true });
            });
        }

        const host = document.getElementById('gantt_here');
        if (host && !host.dataset.gridWheelBound) {
            host.dataset.gridWheelBound = '1';
            host.addEventListener('wheel', e => {
                const inGrid = e.target.closest?.('.gantt_grid_data, .gantt_grid_scale, [data-cell-id="gridScroll"]');
                if (!inGrid || !isOverlayMode()) return;
                if (Math.abs(e.deltaX) <= Math.abs(e.deltaY) && !e.shiftKey) return;
                const dx = e.deltaX || e.deltaY;
                const leader = horScroll || scrollHost || gridData;
                applyScroll(leader.scrollLeft + dx);
                e.preventDefault();
            }, { passive: false });
        }
        syncGridScrollContentWidth();
    }

    const colReorderDrag = { active: false, fromIdx: -1, toIdx: -1, startX: 0, startY: 0, pending: null };

    function ensureColumnDropIndicator() {
        const head = document.querySelector('#gantt_here .gantt_grid_scale .gantt_grid_head');
        if (!head) return null;
        let el = head.querySelector('.sched-col-drop-indicator');
        if (!el) {
            el = document.createElement('div');
            el.className = 'sched-col-drop-indicator';
            head.appendChild(el);
        }
        return el;
    }

    function positionColumnDropIndicator(colIdx) {
        const indicator = ensureColumnDropIndicator();
        if (!indicator) return;
        if (colIdx < 0) {
            indicator.style.display = 'none';
            return;
        }
        const heads = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
        const head = heads[colIdx];
        if (!head) {
            indicator.style.display = 'none';
            return;
        }
        indicator.style.display = 'block';
        indicator.style.left = head.offsetLeft + 'px';
    }

    function clearColumnDropIndicator() {
        const indicator = document.querySelector('#gantt_here .sched-col-drop-indicator');
        if (indicator) indicator.style.display = 'none';
    }

    function bindColumnReorderDrag() {
        if (bindColumnReorderDrag.done) return;
        bindColumnReorderDrag.done = true;
        const host = document.getElementById('gantt_here');
        if (!host) return;

        host.addEventListener('mousedown', e => {
            if (colResizeDrag.active || columnResizeInProgress) return;
            const scale = e.target.closest('.gantt_grid_scale');
            if (!scale) return;
            if (e.target.closest('.gantt_grid_column_resize_wrap') || e.target.closest('.sched-add-col-btn')) return;

            const heads = Array.from(scale.querySelectorAll('.gantt_grid_head_cell'));
            const idx = getColumnIndexFromHeaderX(e.clientX, heads);
            if (idx < 0) return;
            const col = gantt.config.columns[idx];
            if (!isMovableColumn(col)) return;
            if (gridSelection.type !== 'column' || gridSelection.colName !== col.name) return;

            const head = heads[idx];
            if (head) {
                const rect = head.getBoundingClientRect();
                if (e.clientY >= rect.top && rect.right - e.clientX <= 8) return;
            }

            colReorderDrag.pending = { fromIdx: idx, startX: e.clientX, startY: e.clientY };
        }, true);

        document.addEventListener('mousemove', e => {
            if (colReorderDrag.pending && !colReorderDrag.active) {
                const dx = Math.abs(e.clientX - colReorderDrag.pending.startX);
                const dy = Math.abs(e.clientY - colReorderDrag.pending.startY);
                if (dx > 5 || dy > 5) {
                    colReorderDrag.active = true;
                    colReorderDrag.fromIdx = colReorderDrag.pending.fromIdx;
                    document.body.classList.add('sched-col-dragging');
                }
            }
            if (!colReorderDrag.active) return;
            const heads = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
            const idx = getColumnIndexFromHeaderX(e.clientX, heads);
            colReorderDrag.toIdx = idx;
            positionColumnDropIndicator(idx);
        });

        document.addEventListener('mouseup', () => {
            if (colReorderDrag.active) {
                const { fromIdx, toIdx } = colReorderDrag;
                if (toIdx >= 0 && toIdx !== fromIdx) moveGridColumn(fromIdx, toIdx);
                clearColumnDropIndicator();
                colReorderDrag.active = false;
                document.body.classList.remove('sched-col-dragging');
            }
            colReorderDrag.pending = null;
        });
    }

    function bindGridSelectionHandlers() {
        if (bindGridSelectionHandlers.done) return;
        bindGridSelectionHandlers.done = true;
        const host = document.getElementById('gantt_here');
        if (!host) return;

        host.addEventListener('click', e => {
            if (e.target.closest('.gantt_grid_column_resize_wrap') || e.target.closest('.sched-add-col-btn')) return;
            const scale = e.target.closest('.gantt_grid_scale');
            if (!scale) return;

            const scaleRect = scale.getBoundingClientRect();
            const labelRowTop = scaleRect.top + GRID_HEADER_TOP_H;
            if (e.clientY < labelRowTop || e.clientY > scaleRect.bottom) return;

            const heads = Array.from(scale.querySelectorAll('.gantt_grid_head_cell'));
            const idx = getColumnIndexFromHeaderX(e.clientX, heads);
            if (idx < 0) return;

            const head = heads[idx];
            const col = gantt.config.columns[idx];
            if (!col || isAddColumnCol(col)) return;

            if (head) {
                const rect = head.getBoundingClientRect();
                if (e.clientY >= rect.top && rect.right - e.clientX <= 8) return;
            }

            selectGridColumn(col.name);
            e.stopPropagation();
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

        return Math.max(col.min_width || 50, Math.ceil(maxW));
    }

    function autoFitGridColumn(colIndex) {
        if (!ganttReady || !gantt.config.columns[colIndex] || gantt.config.columns[colIndex].resize === false) return;
        const col = gantt.config.columns[colIndex];
        const width = measureColumnContentWidth(colIndex);
        handleColumnResize(colIndex, col, width, true, true);
    }

    function getExposedGridWidth() {
        if (isOverlayMode()) {
            return getGridOverlayWidth();
        }
        const host = document.getElementById('gantt_here');
        if (!host) return 600;
        return Math.max(120, host.clientWidth - getTimelineWidth());
    }

    function getExposedGridRightEdge() {
        const host = document.getElementById('gantt_here');
        if (!host) return 0;
        const rect = host.getBoundingClientRect();
        if (isOverlayMode()) return rect.left + getExposedGridWidth();
        return rect.left + rect.width - getTimelineWidth();
    }

    function getPrintVisibleGridColumns(ps) {
        const opts = ps || scheduleSettings.print_settings || {};
        const cols = gantt.config.columns || [];
        const baseFilter = c => {
            if (c.name === '_sched_add_col') return false;
            if (c.name === 'collapse') return false;
            if (c.name === 'hierarchy') return opts.print_wbs_colors !== false;
            if (opts.print_hide_wbs && c.name === 'wbs') return false;
            if (opts.print_hide_id && c.name === 'activity_id') return false;
            if (opts.print_hide_color && c.name === 'bar_color') return false;
            return true;
        };
        const mapCols = list => list.map((col, index) => ({
            col,
            index,
            width: resolveColumnWidth(col)
        }));

        if (opts.print_column_mode === 'screen' || opts.print_column_mode == null) {
            return mapCols(cols.filter(baseFilter));
        }

        if (opts.print_column_mode !== 'visible_only') {
            return mapCols(cols.filter(baseFilter));
        }

        const headCells = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
        const host = document.getElementById('gantt_here');
        if (!host || !headCells.length) return mapCols(cols.filter(baseFilter));

        const viewRect = (document.querySelector('#gantt_here .gantt_grid_data') || host).getBoundingClientRect();
        const exposedRight = getExposedGridRightEdge();
        const gridScroll = document.querySelector('#gantt_here .gantt_grid_data')?.scrollLeft || 0;
        const visible = [];
        cols.forEach((col, index) => {
            if (!baseFilter(col)) return;
            const m = getColumnLayoutMetrics().columns[index];
            if (!m) return;
            const colLeft = m.left - gridScroll;
            const colRight = colLeft + m.width;
            if (colRight > 2 && colLeft < (exposedRight - viewRect.left) + 2) {
                visible.push({ col, index, width: m.width });
            }
        });
        return visible.length ? visible : mapCols(cols.filter(baseFilter));
    }

    function renderPrintCellHtml(task, col, hierarchyWidth) {
        if (col.name === 'hierarchy') return buildPrintHierarchyGutters(task, hierarchyWidth);
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

    function getColumnIndexFromResizeWrap(wrap) {
        if (wrap?.dataset?.colIndex != null) {
            const idx = parseInt(wrap.dataset.colIndex, 10);
            if (!Number.isNaN(idx)) return idx;
        }
        const scale = wrap?.closest('.gantt_grid_scale');
        if (!scale) return -1;
        const wrapRect = wrap.getBoundingClientRect();
        const headCells = Array.from(scale.querySelectorAll('.gantt_grid_head_cell'));
        let bestIdx = -1;
        let bestDist = Infinity;
        headCells.forEach((cell, i) => {
            const col = gantt.config.columns[i];
            if (!col || col.resize === false) return;
            const r = cell.getBoundingClientRect();
            const dist = Math.abs(wrapRect.left + wrapRect.width / 2 - r.right);
            if (dist < bestDist) {
                bestDist = dist;
                bestIdx = i;
            }
        });
        if (bestIdx >= 0) return bestIdx;
        const wraps = Array.from(scale.querySelectorAll('.gantt_grid_column_resize_wrap'));
        const wrapIdx = wraps.indexOf(wrap);
        if (wrapIdx < 0) return -1;
        let colIdx = 0;
        for (let i = 0; i < (gantt.config.columns || []).length; i++) {
            const col = gantt.config.columns[i];
            if (col.resize === false) continue;
            if (colIdx === wrapIdx) return i;
            colIdx++;
        }
        return wrapIdx < (gantt.config.columns || []).length ? wrapIdx : -1;
    }

    const colResizeDrag = { active: false, colIndex: -1, startX: 0, startW: 0 };

    let columnResizeInProgress = false;

    function ensureColumnResizeGrips() {
        ensureAllColumnResizeGrips();
    }

    function startColumnResize(colIndex, clientX) {
        const col = gantt.config.columns[colIndex];
        if (!col || col.resize === false) return;
        columnResizeInProgress = true;
        colResizeDrag.active = true;
        colResizeDrag.colIndex = colIndex;
        colResizeDrag.startX = clientX;
        colResizeDrag.startW = resolveColumnWidth(col);
        const grid = document.querySelector('#gantt_here .gantt_grid_data');
        columnResizeScrollLeft = grid ? grid.scrollLeft : 0;
        document.body.classList.add('sched-col-resizing');
    }

    function bindColumnResizeDrag() {
        if (bindColumnResizeDrag.done) return;
        bindColumnResizeDrag.done = true;
        const host = document.getElementById('gantt_here');
        if (!host) return;

        host.addEventListener('mousedown', e => {
            const resizeIdx = findColumnResizeIndex(e.clientX, e.clientY);
            if (resizeIdx >= 0) {
                e.preventDefault();
                e.stopPropagation();
                startColumnResize(resizeIdx, e.clientX);
                return;
            }

            const head = e.target.closest('.gantt_grid_head_cell');
            if (head && !e.target.closest('.gantt_grid_column_resize_wrap')) {
                const scale = head.closest('.gantt_grid_scale');
                if (scale) {
                    const heads = Array.from(scale.querySelectorAll('.gantt_grid_head_cell'));
                    const idx = heads.indexOf(head);
                    const col = gantt.config.columns[idx];
                    const rect = head.getBoundingClientRect();
                    if (col && col.resize !== false && rect.right - e.clientX <= 8) {
                        e.preventDefault();
                        e.stopPropagation();
                        startColumnResize(idx, e.clientX);
                        return;
                    }
                }
            }

            const grip = e.target.closest('.gantt_grid_column_resize, .gantt_grid_column_resize_wrap, .sched-col-resize-grip');
            if (!grip) return;
            const wrap = grip.closest('.gantt_grid_column_resize_wrap') || grip;
            const colIndex = getColumnIndexFromResizeWrap(wrap);
            if (colIndex < 0 || !gantt.config.columns[colIndex] || gantt.config.columns[colIndex].resize === false) return;
            e.preventDefault();
            e.stopPropagation();
            startColumnResize(colIndex, e.clientX);
        }, true);

        document.addEventListener('mousemove', e => {
            if (!colResizeDrag.active) return;
            const col = gantt.config.columns[colResizeDrag.colIndex];
            if (!col) return;
            const dx = e.clientX - colResizeDrag.startX;
            const newW = Math.max(col.min_width || 40, colResizeDrag.startW + dx);
            col.width = newW;
            columnWidths[col.name] = newW;
            gantt.config.grid_width = getColumnsTotalWidth();
            gantt.config.keep_grid_width = true;
            lastGridWidthKey = '';
            preserveGridScrollLeft(columnResizeScrollLeft);
            if (!bindColumnResizeDrag.resizeRaf) {
                bindColumnResizeDrag.resizeRaf = requestAnimationFrame(() => {
                    bindColumnResizeDrag.resizeRaf = null;
                    applyColumnWidthsToDom();
                    ensureAllColumnResizeGrips();
                });
            }
        });

        document.addEventListener('mouseup', () => {
            if (!colResizeDrag.active) return;
            const idx = colResizeDrag.colIndex;
            const col = gantt.config.columns[idx];
            if (col) {
                columnWidths[col.name] = col.width;
                columnDefWidths[col.name] = resolveColumnWidth(col);
                handleColumnResize(idx, col, col.width, true, true);
            }
            colResizeDrag.active = false;
            colResizeDrag.colIndex = -1;
            columnResizeInProgress = false;
            columnResizeScrollLeft = null;
            document.body.classList.remove('sched-col-resizing');
            lastGridWidthKey = '';
            gantt.config.grid_width = getColumnsTotalWidth();
            gantt.config.keep_grid_width = true;
            applyColumnWidthsToDom();
            ensureColumnResizeGrips();
            ensureAddColumnHeader();
            syncWbsGutterSpans();
            queueSave();
        });

        host.addEventListener('dblclick', e => {
            const wrap = e.target.closest('.gantt_grid_column_resize_wrap');
            if (!wrap) return;
            const scale = wrap.closest('.gantt_grid_scale');
            if (!scale) return;
            const colIndex = getColumnIndexFromResizeWrap(wrap);
            if (colIndex < 0) return;
            e.preventDefault();
            e.stopPropagation();
            autoFitGridColumn(colIndex);
        }, true);
    }

    function bindColumnResizeEnhancements() {
        bindColumnResizeDrag();
        bindColumnReorderDrag();
        bindGridHorizontalScrollSync();
        ensureColumnResizeGrips();
        ensureAddColumnHeader();
    }

    function handleColumnResize(index, column, new_width, persist, reflow) {
        const w = Math.max(column?.min_width || 50, parseInt(new_width, 10) || 80);
        if (column && column.name) {
            columnWidths[column.name] = w;
            column.width = w;
            if (gantt.config.columns[index]) gantt.config.columns[index].width = w;
        }
        gantt.config.keep_grid_width = true;
        gantt.config.grid_width = getColumnsTotalWidth();
        if (reflow) {
            lastGridWidthKey = '';
            applyColumnWidthsToDom();
            if (isOverlayMode()) {
                applyOverlayDomLayout();
                syncGanttLayout({ skipSetSizes: true, light: true });
            }
            applyCellAlignToDom();
            if (persist) queueSave();
        }
    }

    function resetColumnWidths() {
        columnWidths = {};
        gantt.config.columns = buildColumnConfig();
        syncGridColumnsFromConfig();
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

    function formatDateShort(value) {
        const d = toGanttDate(value);
        if (!d) return '—';
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const day = String(d.getDate()).padStart(2, '0');
        return `${day}-${months[d.getMonth()]}-${d.getFullYear()}`;
    }

    function formatDateSafe(value) {
        return formatDateShort(value);
    }

    function getWbsLevel(task) {
        if (!task) return 0;
        const level = Number(task.$level);
        return Number.isFinite(level) ? Math.max(0, level) : 0;
    }

    function getWbsLevelClass(task) {
        if (!task) return '';
        if (!isParentTask(task) && task.type !== 'project') return '';
        const level = Math.min(getWbsLevel(task), 3);
        return `sched-wbs-l${level}`;
    }

    function isSummaryTask(task) {
        return task && (task.type === 'project' || isParentTask(task));
    }

    function getColumnDefaultAlign(colName) {
        const right = ['duration', 'progress', 'total_float', 'link_lag', 'cpi', 'spi', 'cost'];
        const center = ['wbs', 'activity_id', 'start_date', 'end_date', 'constraint_type', 'collapse', 'bar_color'];
        if (right.includes(colName)) return { h: 'right', v: 'middle' };
        if (center.includes(colName)) return { h: 'center', v: 'middle' };
        return { h: 'left', v: 'middle' };
    }

    function ensureDefaultColumnAlignments() {
        if (!scheduleSettings.column_align) scheduleSettings.column_align = {};
        (gantt.config.columns || []).forEach(col => {
            if (!col?.name || scheduleSettings.column_align[col.name]) return;
            scheduleSettings.column_align[col.name] = Object.assign({}, getColumnDefaultAlign(col.name));
        });
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

    function isDescendantOf(task, ancestorId) {
        if (!task || ancestorId == null) return false;
        let pid = task.parent;
        while (pid != null && pid !== 0 && pid !== '0') {
            if (String(pid) === String(ancestorId)) return true;
            if (!gantt.isTaskExists(pid)) break;
            pid = gantt.getTask(pid).parent;
        }
        return String(task.id) === String(ancestorId);
    }

    function getVisibleTaskItems() {
        const rows = Array.from(document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row'));
        const items = [];
        rows.forEach(row => {
            let id = null;
            try { id = gantt.locate(row); } catch (e) { /* ok */ }
            if (!id || !gantt.isTaskExists(id)) return;
            const task = gantt.getTask(id);
            items.push({ row, id, task, level: getWbsLevel(task) });
        });
        return items;
    }

    let lastWbsBandSegments = [];

    function getSubtreeEndIdx(items, startIdx) {
        const { task, level } = items[startIdx];
        let endIdx = startIdx;
        for (let j = startIdx + 1; j < items.length; j++) {
            if (isDescendantOf(items[j].task, task.id)) endIdx = j;
            else if (items[j].level <= level) break;
        }
        return endIdx;
    }

    function ensureWbsGutterLayer(gridData) {
        if (!gridData) return null;
        let layer = gridData.querySelector('.sched-wbs-gutter-layer');
        if (!layer) {
            layer = document.createElement('div');
            layer.className = 'sched-wbs-gutter-layer';
            gridData.appendChild(layer);
        }
        const hierIdx = (gantt.config.columns || []).findIndex(c => c.name === 'hierarchy');
        const firstRow = gridData.querySelector('.gantt_row');
        const cells = firstRow ? firstRow.querySelectorAll(':scope > .gantt_cell') : [];
        const hierCell = hierIdx >= 0 ? cells[hierIdx] : firstRow?.querySelector('.sched-hierarchy-cell');
        if (hierCell) {
            layer.style.left = hierCell.offsetLeft + 'px';
            layer.style.width = (WBS_GUTTER_COLORS.length * WBS_GUTTER_WIDTH) + 'px';
        }
        return layer;
    }

    function computeWbsBandSegments(items) {
        const segments = [];
        if (!items.length) return segments;

        const projIdx = items.findIndex(it => it.task.type === 'project');
        if (projIdx >= 0) {
            segments.push({
                level: 0,
                startIdx: projIdx,
                endIdx: items.length - 1,
                color: WBS_GUTTER_COLORS[0]
            });
        }

        for (let i = 0; i < items.length; i++) {
            const { task, level } = items[i];
            if (level < 1 || !isSummaryTask(task)) continue;
            const bandLevel = Math.min(level, WBS_GUTTER_COLORS.length - 1);
            segments.push({
                level: bandLevel,
                startIdx: i,
                endIdx: getSubtreeEndIdx(items, i),
                color: WBS_GUTTER_COLORS[bandLevel]
            });
        }

        return segments;
    }

    function taskShowsGutterLevel(task, gutterLevel) {
        if (!task || !ganttReady) return false;
        if (gutterLevel === 0) return true;
        const maxLevel = WBS_GUTTER_COLORS.length - 1;
        const levelFor = t => Math.min(getWbsLevel(t), maxLevel);
        if (isSummaryTask(task) && levelFor(task) === gutterLevel) return true;
        let pid = task.parent;
        while (pid != null && pid !== 0 && pid !== '0') {
            if (!gantt.isTaskExists(pid)) break;
            const p = gantt.getTask(pid);
            if (isSummaryTask(p) && levelFor(p) === gutterLevel) return true;
            pid = p.parent;
        }
        return false;
    }

    function getNextTaskInTree(taskId) {
        if (!ganttReady) return null;
        let found = false;
        let next = null;
        gantt.eachTask(t => {
            if (found && next == null) next = t;
            if (String(t.id) === String(taskId)) found = true;
        });
        return next || null;
    }

    function hierarchyIndentTemplate(task) {
        const nextTask = getNextTaskInTree(task.id);
        let html = '<div class="sched-wbs-indents">';
        for (let i = 0; i < WBS_GUTTER_COLORS.length; i++) {
            const active = taskShowsGutterLevel(task, i);
            const extend = active && nextTask && taskShowsGutterLevel(nextTask, i);
            if (active) {
                const color = WBS_GUTTER_COLORS[i];
                html += `<span class="sched-wbs-slot sched-wbs-slot-active${extend ? ' sched-wbs-slot-extend' : ''}" style="--wbs-slot-color:${color};background-color:${color}"></span>`;
            } else {
                html += '<span class="sched-wbs-slot"></span>';
            }
        }
        html += '</div>';
        return html;
    }

    function buildPrintHierarchyGutters(task, hierarchyWidth) {
        const slotW = Math.max(4, Math.floor((hierarchyWidth || 56) / WBS_GUTTER_COLORS.length));
        let html = '<div class="print-wbs-indents">';
        for (let i = 0; i < WBS_GUTTER_COLORS.length; i++) {
            const active = taskShowsGutterLevel(task, i);
            const color = WBS_GUTTER_COLORS[i];
            html += active
                ? `<span class="print-wbs-gutter print-wbs-gutter-active" style="width:${slotW}px;min-width:${slotW}px;background:${color}"></span>`
                : `<span class="print-wbs-gutter print-wbs-gutter-spacer" style="width:${slotW}px;min-width:${slotW}px"></span>`;
        }
        html += '</div>';
        return html;
    }

    function syncWbsGutterSpans() {
        if (!ganttReady) return;
        const items = getVisibleTaskItems();
        if (items.length) lastWbsBandSegments = computeWbsBandSegments(items);
        document.querySelectorAll('#gantt_here .sched-wbs-gutter-layer .sched-wbs-band').forEach(el => el.remove());
    }

    function refreshWbsGutterDisplay() {
        if (!ganttReady) return;
        syncWbsGutterSpans();
        gantt.eachTask(id => gantt.refreshTask(id));
    }

    function bindWbsGutterScrollSync() {
        const gridData = document.querySelector('#gantt_here .gantt_grid_data');
        if (!gridData || gridData.dataset.wbsScrollBound) return;
        gridData.dataset.wbsScrollBound = '1';
        gridData.addEventListener('scroll', () => syncWbsGutterSpans(), { passive: true });
    }

    function activityNameTemplate(task) {
        const parent = isParentTask(task);
        if (parent) {
            const prefix = task.type === 'project' ? 'Project: ' : 'WBS: ';
            return `<span class="sched-wbs-header-label">${prefix}${task.text || ''}</span>`;
        }
        return `<span class="sched-activity-label">${task.text || ''}</span>`;
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

    function ensureAddColumnHeader() {
        if (!ganttReady) return;
        const cols = gantt.config.columns || [];
        const idx = cols.findIndex(c => c.name === '_sched_add_col');
        if (idx < 0) return;
        const headCells = document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell');
        const cell = headCells[idx];
        if (!cell) return;
        cell.classList.add('sched-add-col-header');
        if (cell.dataset.addColBound === '1') return;
        cell.dataset.addColBound = '1';
        cell.innerHTML = '<button type="button" class="sched-add-col-btn" title="Add column" aria-label="Add column">+</button>';
        const btn = cell.querySelector('.sched-add-col-btn');
        if (btn) {
            btn.addEventListener('click', e => {
                e.preventDefault();
                e.stopPropagation();
                showColumnManager();
            });
            btn.addEventListener('mousedown', e => e.stopPropagation());
        }
    }

    function addColumnCellTemplate() {
        return '';
    }

    function getAddColumnDef() {
        return {
            name: '_sched_add_col',
            label: '+',
            width: colWidth('_sched_add_col', 36),
            min_width: 32,
            max_width: 48,
            resize: false,
            align: 'center',
            template: addColumnCellTemplate
        };
    }

    function getBuiltinColumnDefs() {
        return [
            { name: 'hierarchy', label: '', width: 56, min_width: 14, resize: true, align: 'left', template: hierarchyIndentTemplate },
            { name: 'collapse', label: '', width: 28, min_width: 28, resize: false, align: 'center', template: collapseTemplate },
            { name: 'wbs', label: 'WBS', width: 58, align: 'center', resize: true, template: t => wbsCode(t) },
            { name: 'activity_id', label: 'Activity ID', width: 72, align: 'center', resize: true, editor: { type: 'sched_text', map_to: 'activity_id' }, template: t => t.activity_id || '' },
            { name: 'text', label: 'Activity Name', tree: false, width: 240, min_width: 120, resize: true, editor: { type: 'sched_text', map_to: 'text' }, template: activityNameTemplate },
            { name: 'duration', label: 'Original Duration', align: 'center', width: 64, min_width: 52, resize: true, editor: { type: 'sched_number', map_to: 'duration', min: 0, max: 9999 }, template: t => {
                if (t.type === 'project') return '';
                const d = Number(t.duration);
                return (Number.isFinite(d) ? d.toFixed(2) : '0.00') + 'd';
            } },
            { name: 'start_date', label: 'Start', align: 'center', width: 108, min_width: 96, resize: true, editor: { type: 'sched_date', map_to: 'start_date' }, template: t => formatDateSafe(t.start_date) },
            { name: 'end_date', label: 'Finish', align: 'center', width: 108, min_width: 96, resize: true, editor: { type: 'sched_date', map_to: 'end_date' }, template: t => formatDateSafe(t.end_date) },
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

        const ordered = orderColumns(cols).map(c => {
            const copy = Object.assign({}, c);
            if (copy.editor) {
                columnEditors.set(copy.name, copy.editor);
                delete copy.editor;
            }
            columnDefWidths[copy.name] = parseInt(copy.width, 10) || 80;
            return copy;
        });
        const addCol = getAddColumnDef();
        columnDefWidths[addCol.name] = parseInt(addCol.width, 10) || 36;
        return ordered.concat([addCol]);
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
        applyCellFocusHighlight();
    }

    function mountCellEditor(cell, wrap) {
        const grid = document.querySelector('#gantt_here .gantt_grid_data');
        if (!grid || !cell) return false;
        const cr = cell.getBoundingClientRect();
        const gr = grid.getBoundingClientRect();
        wrap.style.position = 'absolute';
        wrap.style.left = (cr.left - gr.left + grid.scrollLeft) + 'px';
        wrap.style.top = (cr.top - gr.top + grid.scrollTop) + 'px';
        wrap.style.width = Math.max(20, cr.width) + 'px';
        wrap.style.height = Math.max(18, cr.height) + 'px';
        wrap.style.right = 'auto';
        wrap.style.bottom = 'auto';
        grid.appendChild(wrap);
        return true;
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
        if (!mountCellEditor(cell, wrap)) {
            cell.appendChild(wrap);
        }
        gridSelection = { type: 'cell', taskId: id, colName };
        applyCellFocusHighlight();
        input.focus();
        if (input.select) input.select();

        const commit = () => {
            if (!floatingEditorActive) return;
            saveFloatingEditor(id, colName, input.value);
            closeFloatingEditor();
            gantt.render();
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
        gantt.config.row_height = 22;
        gantt.config.bar_height = 12;
        applyP6RowMetrics();
        gantt.config.scale_height = GRID_HEADER_TOTAL_H;
        updateScaleHeight();
        gantt.config.scroll_size = 16;
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
        gantt.config.reorder_grid_columns = false;
        gantt.config.open_tree_initially = true;
        gantt.config.details_on_dblclick = false;
        gantt.config.details_on_create = false;
        gantt.config.select_task = true;
        gantt.config.keyboard_navigation = false;
        gantt.config.show_task_cells = false;
        gantt.config.show_links = true;
        gantt.config.link_line_width = scheduleSettings.link_width || 2;
        gantt.config.link_attribute = 'data-link-id';

        gantt.config.min_column_width = 50;
        applyTimescaleScales(scheduleSettings.timescale || 'day');

        const todaySeed = new Date();
        gantt.config.start_date = new Date(todaySeed.getFullYear() - ROLLING_YEARS_BACK, 0, 1);
        gantt.config.end_date = new Date(todaySeed.getFullYear() + ROLLING_YEARS_FORWARD, 11, 31);

        const gridW = getColumnsTotalWidth();
        const hostW = document.getElementById('gantt_here')?.offsetWidth || 1000;
        const gridPaneW = scheduleSettings.grid_overlay_width_px != null && scheduleSettings.grid_overlay_width_px >= 0
            ? scheduleSettings.grid_overlay_width_px
            : Math.round(hostW * 0.45);
        gantt.config.grid_width = gridW;
        gantt.config.layout = {
            css: 'gantt_container',
            cols: [
                {
                    width: gridPaneW,
                    min_width: 0,
                    rows: [
                        { view: 'grid', scrollX: 'gridScroll', scrollY: 'scrollVer' },
                        { view: 'scrollbar', id: 'gridScroll', height: 20 }
                    ]
                },
                { width: 0, min_width: 0, max_width: 0 },
                {
                    width: hostW,
                    min_width: hostW,
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

        gantt.templates.format_date = function (date) {
            return formatDateShort(date);
        };

        gantt.templates.grid_row_class = function (start, end, task) {
            const classes = [];
            const level = getWbsLevel(task);
            if (isParentTask(task)) classes.push('cpm_project_row', 'sched-parent-row', 'sched-summary-row');
            const wbsCls = getWbsLevelClass(task);
            if (wbsCls) classes.push(wbsCls);
            classes.push(`sched-depth-${level}`);
            return classes.join(' ');
        };

        gantt.templates.task_row_class = function (start, end, task) {
            const classes = [`sched-depth-${getWbsLevel(task)}`];
            if (isParentTask(task)) classes.push('sched-summary-timeline-row');
            return classes.join(' ');
        };

        gantt.templates.task_class = function (start, end, task) {
            const classes = [];
            if (isSummaryTask(task)) {
                classes.push('cpm_summary', 'sched-summary-bar');
                const wbsCls = getWbsLevelClass(task);
                if (wbsCls) classes.push(wbsCls);
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
            if (isSummaryTask(task)) return '';
            return task.text || '';
        };

        gantt.templates.leftside_text = function () {
            return '';
        };

        gantt.templates.link_class = function (link) {
            const src = gantt.isTaskExists(link.source) ? gantt.getTask(link.source) : null;
            const tgt = gantt.isTaskExists(link.target) ? gantt.getTask(link.target) : null;
            const crit = gantt.config.highlight_critical_path && src && tgt
                && (isTaskCritical(src) || isTaskCritical(tgt));
            return crit ? 'cpm_schedule_link cpm_link_critical' : 'cpm_schedule_link';
        };

        applyGanttDisplayStyles();

        ensureDefaultColumnAlignments();

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

        gantt.attachEvent('onAfterTaskMove', () => {
            refreshWbsCodes();
            refreshWbsGutterDisplay();
            pushUndoState();
            queueSave();
        });
        gantt.attachEvent('onTaskOpened', () => { refreshWbsGutterDisplay(); });
        gantt.attachEvent('onTaskClosed', () => { refreshWbsGutterDisplay(); });
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
            if (target.closest?.('.gantt_grid_data .gantt_cell')) {
                const pos = locateGridCell(target);
                if (pos) {
                    gridSelection = { type: 'cell', taskId: pos.id, colName: pos.column };
                    if (typeof gantt.unselectTask === 'function' && gantt.getSelectedId()) {
                        gantt.unselectTask(gantt.getSelectedId());
                    }
                    highlightGridSelection();
                    return false;
                }
                gridSelection = { type: null };
                highlightGridSelection();
                return false;
            }
            gantt.selectTask(id);
            gridSelection = { type: null };
            highlightGridSelection();
            return true;
        });

        gantt.attachEvent('onTaskDblClick', function (id, e) {
            const target = e.target || e.srcElement;
            if (target.closest?.('.sched-tree-btn') || target.closest?.('.gantt_tree_icon')) return true;
            if (target.closest?.('.sched-floating-cell-editor')) return true;
            if (target.closest?.('.gantt_grid_data .gantt_cell')) {
                const pos = locateGridCell(target);
                if (pos && columnEditors.has(pos.column)
                    && !['wbs', 'successors', 'collapse', 'hierarchy'].includes(pos.column)
                    && !target.closest?.('.sched-tree-btn') && !target.closest?.('.gantt_tree_icon')) {
                    startCellEdit(pos.id, pos.column);
                    return false;
                }
            }
            if (window.ScheduleActivityModal) {
                ScheduleActivityModal.open(id);
                return false;
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
            }
            refreshTimelinePanBar();
        });
        gantt.attachEvent('onAfterColumnReorder', () => {
            columnOrder = gantt.config.columns.map(c => c.name);
            scheduleSettings.column_order = columnOrder.slice();
            syncGridTableWidth();
            queueSave();
            queueGridHeaderSync();
            queueGanttLayoutSync();
        });
        gantt.attachEvent('onColumnResizeStart', function () {
            columnResizeInProgress = true;
            const grid = document.querySelector('#gantt_here .gantt_grid_data');
            columnResizeScrollLeft = grid ? grid.scrollLeft : 0;
        });
        gantt.attachEvent('onColumnResize', function (index, column, new_width) {
            preserveGridScrollLeft(columnResizeScrollLeft);
            if (column && column.name) {
                column.width = new_width;
                columnWidths[column.name] = new_width;
                gantt.config.keep_grid_width = true;
                gantt.config.grid_width = getColumnsTotalWidth();
                applyColumnWidthsToDom();
            }
        });
        gantt.attachEvent('onColumnResizeEnd', function (index, column, new_width) {
            columnResizeInProgress = false;
            handleColumnResize(index, column, new_width, true, true);
            columnResizeScrollLeft = null;
        });
        gantt.attachEvent('onGanttRender', () => {
            refreshWbsCodes();
            updateStatusBar();
            updateDeadlineMarkers();
            ensureTimelineScrollbar();
            restoreTimelineScrollAfterRender();
            refreshTimelinePanBar();
            bindColumnResizeEnhancements();
            bindGridSelectionHandlers();
            applyCellAlignToDom();
            updateAlignToolbarButtons();
            if (isOverlayMode()) applyOverlayDomLayout();
            syncWbsGutterSpans();
            ensureColumnResizeGrips();
            ensureAddColumnHeader();
            bindWbsGutterScrollSync();
            applyColumnWidthsToDom();
            requestAnimationFrame(() => {
                restoreColumnWidthsFromConfig();
                applyColumnWidthsToDom();
                ensureAllColumnResizeGrips();
            });
        });

        document.addEventListener('keydown', onScheduleKeyDown);

        initBaselineBars();
        initBarLabels();
        initTimelineEngine();
        applyRollingCalendarRange(true);


        syncGridTableWidth();
        gantt.init('gantt_here');
        sanitizeAllTaskDates();
        initGanttLayout();
        ganttReady = true;
        bindColumnResizeEnhancements();
        bindGridSelectionHandlers();
        syncScheduleProjectContext();
        resizeGanttHost();
        queueGridHeaderSync();
        window.addEventListener('resize', resizeGanttHost);
    }

    function onScheduleKeyDown(e) {
        const tag = (e.target?.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target?.isContentEditable) return;
        if (!ganttReady) return;

        if (e.key === 'Delete' || e.key === 'Backspace') {
            if (gridSelection.type === 'column' && gridSelection.colName) {
                e.preventDefault();
                removeSelectedColumn();
                return;
            }
            e.preventDefault();
            deleteSelected();
            return;
        }
        if (e.key === 'F2') {
            e.preventDefault();
            if (gridSelection.type === 'cell' && gridSelection.taskId && gridSelection.colName) {
                startCellEdit(gridSelection.taskId, gridSelection.colName);
            } else {
                const id = gantt.getSelectedId();
                if (id) startCellEdit(id, 'text');
            }
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
        const panel = document.getElementById('ganttViewPanel');
        const host = document.getElementById('scheduleGanttHost');
        const chrome = document.getElementById('scheduleChrome');
        if (!host || !chrome) return;
        const top = chrome.getBoundingClientRect().bottom;
        const status = document.getElementById('scheduleStatusBar');
        const footer = document.querySelector('#mainContent + div, .border-t.border-zinc-800');
        const footerH = footer ? footer.offsetHeight : 40;
        const statusH = status ? status.offsetHeight + 8 : 0;
        const h = Math.max(360, window.innerHeight - top - statusH - footerH - 12);
        if (panel) panel.style.minHeight = h + 'px';
        host.style.height = h + 'px';
        const ganttEl = document.getElementById('gantt_here');
        if (ganttEl) ganttEl.style.height = h + 'px';
        if (!ganttReady) return;
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (typeof gantt.setSizes === 'function') gantt.setSizes();
            gantt.render();
            syncGanttLayout();
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
        ensureDefaultColumnAlignments();
        updateGridWidth();
        gantt.clearAll();
        gantt.parse({ data: payload.data, links: payload.links || [] });
        sanitizeAllTaskDates();
        runSchedule({ skipScroll: true });
        baselines = payload.baselines || [];
        if (payload.settings) scheduleSettings = Object.assign(scheduleSettings, payload.settings);
        applyP6RowMetrics();
        applyGanttDisplayStyles();
        if (!scheduleSettings.theme) scheduleSettings.theme = 'dark';
        if (window.ScheduleExtras) ScheduleExtras.applyThemeFromSettings();
        if (!scheduleSettings.print_settings) {
            scheduleSettings.print_settings = {
                include_summary: true,
                include_activity_table: true,
                include_inline_bars: true,
                include_predecessor_links: true,
                orientation: 'landscape',
                font_size_pt: 8,
                row_height_px: 24,
                chart_width_pct: 58,
                print_wbs_colors: true,
                include_schedule_chart: false,
                include_evm: false,
                include_footer: true
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
        queueGanttLayoutSync();
        gantt.render();
        queueGridHeaderSync();
        applyCellAlignToDom();
        pushUndoState();
        updateDataDateMarker();
        updateDeadlineMarkers();
        if (!initialTimelineFocused) {
            initialTimelineFocused = true;
            setTimeout(() => {
                focusInitialTimelineView();
                syncGanttLayout();
            }, 150);
        }
        return true;
    }

    async function loadSchedule() {
        const projectId = getSelectedProjectId();
        const params = new URLSearchParams(window.location.search);
        setSaveStatus('Loading…');

        if (params.get('schedule_demo') === 'p6') {
            loadP6DemoSchedule();
            return;
        }

        if (projectId > 0) {
            try {
                const res = await fetch(`/api/schedule?project_id=${projectId}`);
                if (res.ok) {
                    const json = await res.json();
                    if (json.payload?.data?.length) {
                        if (!isBareProjectSchedule(json.payload)) {
                            if (loadSchedulePayload(json.payload)) {
                                setSaveStatus('Loaded from server');
                                return;
                            }
                        }
                    }
                }
            } catch (e) { /* local fallback */ }
        }

        const local = localStorage.getItem(`${STORAGE_KEY}_${projectId}`);
        if (local) {
            try {
                const parsed = JSON.parse(local);
                if (parsed.data && parsed.data.length) {
                    if (isBareProjectSchedule(parsed)) {
                        loadP6DemoSchedule();
                        return;
                    }
                    if (loadSchedulePayload(parsed)) {
                        setSaveStatus('Loaded from browser');
                        return;
                    }
                }
            } catch (e) { /* ignore */ }
        }

        loadP6DemoSchedule();
    }

    function loadP6DemoSchedule() {
        loadSchedulePayload(buildP6DemoSchedule());
        setSaveStatus('P6 demo schedule loaded');
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
        if (!projectId) {
            setSaveStatus('No project');
            showScheduleAlert('Select a project before saving the schedule.', 'warning');
            return;
        }
        setSaveStatus('Saving…');
        const payload = serializeSchedule();
        localStorage.setItem(`${STORAGE_KEY}_${projectId}`, JSON.stringify(payload));
        try {
            const res = await fetch('/api/schedule', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project_id: projectId, payload })
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                setSaveStatus('Save failed');
                showScheduleAlert(err.error || 'Could not save schedule to the server.', 'error');
                return;
            }
            setSaveStatus('Saved');
            logActivity('Saved schedule', `${countTasks()} activities`);
        } catch (e) {
            setSaveStatus('Saved locally');
            showScheduleAlert('Saved locally only — server unreachable.', 'warning');
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
        const id = getActiveTaskId();
        if (!id) return showScheduleAlert('Select an activity first.', 'warning');
        if (window.ScheduleActivityModal) ScheduleActivityModal.open(id);
    }

    function applyGanttDisplayStyles() {
        const s = scheduleSettings;
        const root = document.documentElement;
        const linkColor = s.link_color || '#b0b0b0';
        root.style.setProperty('--gantt-link-color', linkColor);
        root.style.setProperty('--gantt-link-width', (s.link_width || 1) + 'px');
        if (ganttReady) {
            gantt.config.link_line_width = s.link_width || 1;
            const rowH = s.default_row_height || 24;
            const barH = s.default_bar_height || 16;
            const summaryBarH = s.summary_bar_height || 12;
            gantt.config.row_height = rowH;
            gantt.config.bar_height = barH;
            gantt.getTaskHeight = () => rowH;
            const host = document.getElementById('gantt_here');
            if (host) {
                host.style.setProperty('--sched-row-h', rowH + 'px');
                host.style.setProperty('--sched-bar-h', barH + 'px');
                host.style.setProperty('--sched-summary-bar-h', summaryBarH + 'px');
                host.style.setProperty('--sched-grid-header-total', GRID_HEADER_TOTAL_H + 'px');
                host.style.setProperty('--sched-grid-header-top', GRID_HEADER_TOP_H + 'px');
                host.style.setProperty('--sched-grid-header-label', GRID_HEADER_LABEL_H + 'px');
            }
            gantt.render();
        }
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
        document.documentElement.style.setProperty('--sched-grid-col-width', (widthByScale[scale] || 32) + 'px');
        updateScaleHeight();
    }

    function jumpToScheduleTasks() {
        let target = null;
        gantt.eachTask(t => {
            if (target || t.type === 'project') return;
            const d = toGanttDate(t.start_date);
            if (d) target = d;
        });
        if (target) scrollTimelineToDate(target, getTimelineScrollMargin());
        else scrollToToday();
    }

    function focusInitialTimelineView() {
        if (!ganttReady) return;
        applyRollingCalendarRange(true);
        gantt.render();
        const range = gantt.getSubtaskDates?.();
        if (range?.start_date && range?.end_date) fitScheduleView();
        else jumpToScheduleTasks();
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

    function applyFontColorToSelection(color) {
        const hex = normalizeHexColor(color);
        const sel = gridSelection;
        if (!sel.type) {
            if (!scheduleSettings.default_cell_style) scheduleSettings.default_cell_style = {};
            scheduleSettings.default_cell_style.color = hex;
        } else if (sel.type === 'column' && sel.colName) {
            if (!scheduleSettings.column_align) scheduleSettings.column_align = {};
            if (!scheduleSettings.column_align[sel.colName]) scheduleSettings.column_align[sel.colName] = {};
            scheduleSettings.column_align[sel.colName].color = hex;
            gantt.eachTask(t => {
                if (t.cell_align?.[sel.colName]) delete t.cell_align[sel.colName].color;
            });
        } else if (sel.type === 'cell' && sel.taskId && gantt.isTaskExists(sel.taskId)) {
            const task = gantt.getTask(sel.taskId);
            if (!task.cell_align) task.cell_align = {};
            if (!task.cell_align[sel.colName]) task.cell_align[sel.colName] = {};
            task.cell_align[sel.colName].color = hex;
            gantt.updateTask(sel.taskId);
        } else {
            const taskId = (sel.type === 'row' && sel.taskId) ? sel.taskId : gantt.getSelectedId();
            if (!taskId || !gantt.isTaskExists(taskId)) {
                if (!scheduleSettings.default_cell_style) scheduleSettings.default_cell_style = {};
                scheduleSettings.default_cell_style.color = hex;
            } else {
                const task = gantt.getTask(taskId);
                if (!task.cell_align) task.cell_align = {};
                (gantt.config.columns || []).forEach(col => {
                    if (!task.cell_align[col.name]) task.cell_align[col.name] = {};
                    task.cell_align[col.name].color = hex;
                });
                gantt.updateTask(taskId);
            }
        }
        highlightGridSelection();
        pushUndoState();
        queueSave();
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

    function setGridFontColor(color) {
        applyFontColorToSelection(color);
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
        let parent = getActiveTaskId();
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
        const id = getActiveTaskId();
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
        queueGanttLayoutSync();
        queueGridHeaderSync();
        if (window.ScheduleActivityModal) ScheduleActivityModal.open(id);
        else showScheduleAlert('Open activity detail by double-clicking a row.', 'info');
        logActivity('Added activity', type === 'milestone' ? 'Milestone' : 'Task');
    }

    function deleteSelected() {
        let ids = gantt.getSelectedTasks ? gantt.getSelectedTasks() : [];
        if (!ids.length) {
            const active = getActiveTaskId();
            if (active) ids = [active];
        }
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
        const id = getActiveTaskId();
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
        gridSelection = { type: 'row', taskId: id };
        gantt.selectTask(id);
        refreshWbsCodes();
        gantt.render();
        refreshWbsGutterDisplay();
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
        const id = getActiveTaskId();
        if (!id) return showScheduleAlert('Select an activity to outdent.', 'warning');
        const rootId = getRootProjectId();
        if (rootId != null && String(id) === String(rootId)) {
            return showScheduleAlert('The main project summary cannot be outdented.', 'warning');
        }
        const parent = gantt.getParent(id);
        if (!parent || parent === 0) return showScheduleAlert('Activity is already at top level.', 'warning');
        if (rootId != null && String(parent) === String(rootId)) {
            return showScheduleAlert('Cannot outdent past the project summary.', 'warning');
        }
        const grandParent = gantt.getParent(parent) || 0;
        const insertAt = gantt.getTaskIndex(parent) + 1;
        gantt.moveTask(id, insertAt, grandParent);
        demoteSummaryIfEmpty(parent);
        gridSelection = { type: 'row', taskId: id };
        gantt.selectTask(id);
        refreshWbsCodes();
        gantt.render();
        refreshWbsGutterDisplay();
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
        const id = getActiveTaskId();
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
        syncGanttLayout();
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
            const visibleCols = cols.filter(c => !isAddColumnCol(c));
            if (!visibleCols.length) {
                visible.innerHTML = '<p class="text-zinc-500 text-sm">No columns visible.</p>';
            } else {
                visible.innerHTML = `<p class="text-xs text-zinc-500 mb-2">Click a header to select a column. Drag a selected column header to reorder. Press Delete to remove the selected column.</p>`
                    + visibleCols.map(col => {
                    const required = REQUIRED_COLUMNS.includes(col.name) || col.name === 'hierarchy';
                    const label = col.label || col.name;
                    const selected = gridSelection.type === 'column' && gridSelection.colName === col.name;
                    return `<div class="flex items-center justify-between gap-2 px-3 py-2 rounded-md border ${selected ? 'border-emerald-500 bg-emerald-950/40' : 'bg-zinc-800/80 border-zinc-700'}">
                        <button type="button" class="text-sm text-left flex-1 hover:text-emerald-300" onclick="ScheduleApp.selectGridColumn('${col.name}')">${label}</button>
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

    function removeColumn(name, opts) {
        if (REQUIRED_COLUMNS.includes(name) || name === 'hierarchy') {
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
        if (opts?.refreshManager !== false) showColumnManager();
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
        try {
            ['ganttViewPanel', 'calendarViewPanel', 'lookaheadViewPanel', 'traceViewPanel', 'portfolioViewPanel'].forEach(id => {
                document.getElementById(id)?.classList.add('hidden');
            });
            document.querySelectorAll('.schedule-view-tab').forEach(btn => btn.classList.remove('active-view'));

            if (view === 'gantt') {
                document.getElementById('ganttViewPanel')?.classList.remove('hidden');
                document.getElementById('tabGantt')?.classList.add('active-view');
                if (ganttReady) {
                    resizeGanttHost();
                    gantt.render();
                    syncGanttLayout();
                }
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
        } catch (err) {
            console.error('switchScheduleView', err);
            showScheduleAlert('Could not open that view. Try refreshing the page.', 'warning');
        }
    }

    function renderCalendarView() {
        if (!ganttReady) {
            showScheduleAlert('Schedule is still loading…', 'warning');
            return;
        }
        if (!window.ScheduleCalendar) return;
        const tasks = [];
        gantt.eachTask(t => tasks.push(Object.assign({}, t)));
        ScheduleCalendar.init('scheduleCalendarContent', {
            getTasks: () => tasks,
        });
    }

    function renderLookAhead() {
        if (!ganttReady) {
            showScheduleAlert('Schedule is still loading…', 'warning');
            return;
        }
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
        if (!ganttReady) return;
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
        if (!ganttReady) return;
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
        document.getElementById('printIncludeLinks').checked = ps.include_predecessor_links !== false;
        document.getElementById('printIncludeChart').checked = !!ps.include_schedule_chart;
        document.getElementById('printIncludeEvm').checked = !!ps.include_evm;
        document.getElementById('printIncludeFooter').checked = !!ps.include_footer;
        const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        setVal('printOrientation', ps.orientation || 'landscape');
        setVal('printPaperSize', ps.paper_size || 'letter');
        setVal('printMarginIn', ps.margin_in ?? 0.35);
        setVal('printColumnMode', ps.print_column_mode || 'screen');
        setVal('printFontSize', ps.font_size_pt || 8);
        setVal('printRowHeight', ps.row_height_px || 16);
        setVal('printChartWidthPct', ps.chart_width_pct || 58);
        setVal('printTimescale', ps.print_timescale || 'week');
        setVal('printScale', ps.print_scale || 100);
        setVal('printCriticalColor', ps.print_critical_color || '#c00000');
        const setChk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = v; };
        setChk('printWbsColors', ps.print_wbs_colors !== false);
        setChk('printBarLabels', ps.print_bar_labels === true);
        setChk('printGridLines', ps.print_grid_lines !== false);
        setChk('printShowNonwork', ps.print_show_nonwork === true);
        setChk('printFitToPage', ps.fit_to_page === true);
        setChk('printRepeatHeader', ps.repeat_header !== false);
        setChk('printPageNumbers', ps.page_numbers === true);
        setChk('printColorBars', ps.print_color_bars !== false);
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
            include_predecessor_links: document.getElementById('printIncludeLinks')?.checked !== false,
            include_schedule_chart: document.getElementById('printIncludeChart')?.checked === true,
            include_evm: document.getElementById('printIncludeEvm')?.checked === true,
            include_footer: document.getElementById('printIncludeFooter')?.checked === true,
            orientation: document.getElementById('printOrientation')?.value || 'landscape',
            paper_size: document.getElementById('printPaperSize')?.value || 'letter',
            margin_in: parseFloat(document.getElementById('printMarginIn')?.value) || 0.35,
            print_column_mode: document.getElementById('printColumnMode')?.value || 'screen',
            font_size_pt: parseInt(document.getElementById('printFontSize')?.value, 10) || 8,
            row_height_px: parseInt(document.getElementById('printRowHeight')?.value, 10) || 16,
            chart_width_pct: parseInt(document.getElementById('printChartWidthPct')?.value, 10) || 58,
            print_timescale: document.getElementById('printTimescale')?.value || 'week',
            print_critical_color: document.getElementById('printCriticalColor')?.value || '#c00000',
            print_wbs_colors: document.getElementById('printWbsColors')?.checked !== false,
            print_bar_labels: document.getElementById('printBarLabels')?.checked === true,
            print_grid_lines: document.getElementById('printGridLines')?.checked !== false,
            print_show_nonwork: document.getElementById('printShowNonwork')?.checked === true,
            print_scale: parseInt(document.getElementById('printScale')?.value, 10) || 100,
            fit_to_page: document.getElementById('printFitToPage')?.checked === true,
            repeat_header: document.getElementById('printRepeatHeader')?.checked !== false,
            page_numbers: document.getElementById('printPageNumbers')?.checked === true,
            print_color_bars: document.getElementById('printColorBars')?.checked !== false,
            print_hide_wbs: scheduleSettings.print_settings?.print_hide_wbs === true,
            print_hide_id: scheduleSettings.print_settings?.print_hide_id === true,
            header_footer: hf
        };
        hf.include_footer = scheduleSettings.print_settings.include_footer;
        queueSave();
        document.getElementById('schedulePrintModal')?.close();
        printGantt();
    }

    function buildPrintTimescale(startMs, span, mode) {
        const ticks = mode === 'day' ? 14 : (mode === 'month' ? 6 : 10);
        const stepMs = mode === 'day' ? 86400000 : (mode === 'month' ? (span / ticks) : (span / ticks));
        let cells = '';
        for (let i = 0; i <= ticks; i++) {
            const pct = (i / ticks) * 100;
            const d = new Date(startMs + (mode === 'day' ? stepMs * i : (span * i / ticks)));
            cells += `<span class="print-ts-label" style="left:${pct}%">${formatDateShort(d)}</span>`;
        }
        return `<div class="print-timescale">${cells}</div>`;
    }

    function buildPrintBarMarkup(task, startMs, span) {
        const ts = toGanttDate(task.start_date)?.getTime() || startMs;
        const te = toGanttDate(task.end_date)?.getTime() || ts;
        const left = Math.max(0, ((ts - startMs) / span) * 100);
        const width = Math.max(task.type === 'milestone' ? 0.8 : 1.2, ((te - ts) / span) * 100);
        const color = resolveBarColor(task);
        if (task.type === 'milestone') {
            return `<div class="print-milestone" style="left:${left}%"></div>`;
        }
        if (isSummaryTask(task)) {
            return `<div class="print-bar print-bar-summary ${getWbsLevelClass(task) || 'sched-wbs-l0'}" style="left:${left}%;width:${width}%"></div>`;
        }
        const crit = gantt.config.highlight_critical_path && isTaskCritical(task);
        return `<div class="print-bar print-bar-task${crit ? ' print-bar-critical' : ''}" style="left:${left}%;width:${width}%;background:${color}"></div>`;
    }

    function buildPrintLinkPaths(rowMap, rowIdx, startMs, span, headerRowCount) {
        if (!rowIdx) return '';
        const headerRows = headerRowCount || 1;
        const totalRows = rowIdx + headerRows;
        const rowY = i => ((headerRows + i + 0.5) / totalRows) * 100;
        let paths = '';
        gantt.getLinks().forEach(link => {
            if (!gantt.isTaskExists(link.source) || !gantt.isTaskExists(link.target)) return;
            const src = gantt.getTask(link.source);
            const tgt = gantt.getTask(link.target);
            const si = rowMap.get(link.source);
            const ti = rowMap.get(link.target);
            if (si == null || ti == null) return;
            const x1 = ((toGanttDate(src.end_date)?.getTime() || startMs) - startMs) / span * 100;
            const x2 = ((toGanttDate(tgt.start_date)?.getTime() || startMs) - startMs) / span * 100;
            const y1 = rowY(si);
            const y2 = rowY(ti);
            const midX = Math.max(x1 + 1.5, Math.min(x1 + 3, x2 - 1));
            const crit = gantt.config.highlight_critical_path && (isTaskCritical(src) || isTaskCritical(tgt));
            const stroke = crit ? '#808080' : (scheduleSettings.link_color || '#b0b0b0');
            paths += `<path d="M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}" fill="none" stroke="${stroke}" stroke-width="1.2" stroke-linejoin="miter" stroke-linecap="square"/>`;
            paths += `<polygon points="${x2},${y2} ${x2 - 1.2},${y2 - 0.5} ${x2 - 1.2},${y2 + 0.5}" fill="${stroke}"/>`;
        });
        return paths;
    }

    function getPrintColumnAlignClass(col) {
        const align = col.align === 'center' ? 'c' : (col.align === 'right' ? 'r' : getColumnDefaultAlign(col.name).h);
        if (align === 'right' || align === 'r') return ' r';
        if (align === 'center' || align === 'c') return ' c';
        return '';
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
        const timescale = buildPrintTimescale(startMs, span, ps.print_timescale || 'week');
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
        const showLinks = ps.include_predecessor_links !== false;
        const printFontPt = parseInt(ps.font_size_pt, 10) || 8;
        const printRowH = gantt.config.row_height || parseInt(ps.row_height_px, 10) || 24;
        const chartWidthPct = parseInt(ps.chart_width_pct, 10);
        const textTablePct = showInlineBars
            ? (chartWidthPct >= 30 && chartWidthPct <= 80 ? 100 - chartWidthPct : (exposedW / splitTotal) * 100)
            : 100;
        const barTablePct = showInlineBars ? (100 - textTablePct) : 0;
        const visibleTextW = visibleCols.reduce((s, v) => s + v.width, 0) || 1;
        const hasHierarchyCol = visibleCols.some(v => v.col.name === 'hierarchy');
        const hierarchyPrintW = hasHierarchyCol
            ? (visibleCols.find(v => v.col.name === 'hierarchy')?.width || 56)
            : 0;

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
                const level = t.$level || 0;
                const cells = visibleCols.map(({ col, width: colW }) => {
                    const pct = ((colW / visibleTextW) * textTablePct).toFixed(3);
                    const align = getPrintColumnAlignClass(col);
                    const nameCls = col.name === 'text' ? ' print-name' : (col.name === 'hierarchy' ? ' print-col-hierarchy' : '');
                    const styleParts = [`width:${pct}%`];
                    if (col.name === 'text' && !hasHierarchyCol) styleParts.push(`padding-left:${4 + level * 10}px`);
                    const indent = ` style="${styleParts.join(';')}"`;
                    let content = renderPrintCellHtml(t, col, hierarchyPrintW);
                    if (col.name === 'progress' && !content.includes('%')) content += '%';
                    return `<td class="print-col-${col.name}${nameCls}${align}"${indent}>${content}</td>`;
                }).join('');
                const evmExtra = showEvm && !visibleCols.some(v => v.col.name === 'cpi')
                    ? `<td class="c print-col-cpi" style="width:${(textTablePct / visibleCols.length * 0.5).toFixed(2)}%">${t.cpi != null ? t.cpi : '—'}</td><td class="c print-col-spi" style="width:${(textTablePct / visibleCols.length * 0.5).toFixed(2)}%">${t.spi != null ? t.spi : '—'}</td>`
                    : '';
                const summary = isSummaryTask(t);
                const wbsCls = getWbsLevelClass(t);
                const barCell = showInlineBars
                    ? `<td class="print-bar-cell" style="width:${barTablePct.toFixed(2)}%"><div class="print-bar-track">${buildPrintBarMarkup(t, startMs, span)}</div></td>`
                    : '';
                rows += `<tr class="${summary ? 'print-summary' : ''}${wbsCls ? ' ' + wbsCls : ''}">${cells}${evmExtra}${barCell}</tr>`;
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
                const y1 = (si + 0.5) / rowIdx * 100;
                const y2 = (ti + 0.5) / rowIdx * 100;
                const midX = Math.max(x1 + 1.5, Math.min(x1 + 3, x2 - 1));
                chartLines += `<path d="M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}" fill="none" stroke="${scheduleSettings.link_color || '#b0b0b0'}" stroke-width="0.8" stroke-linejoin="miter"/>`;
            });
            chartBlock = `<div class="print-gantt-chart"><h3 class="print-chart-title">Schedule Chart</h3>${timescale}
                <svg class="print-chart-svg" viewBox="0 0 100 100" preserveAspectRatio="none" style="height:${chartH}px">${chartLines}${chartBars}</svg></div>`;
        }

        const evmHeader = showEvm && !visibleCols.some(v => v.col.name === 'cpi')
            ? `<th class="print-col-cpi c">CPI</th><th class="print-col-spi c">SPI</th>` : '';
        const barHeader = showInlineBars ? `<th class="print-bar-cell" style="width:${barTablePct.toFixed(2)}%">Schedule Bars</th>` : '';
        const colHeaders = visibleCols.map(({ col, width: colW }) => {
            const pct = ((colW / visibleTextW) * textTablePct).toFixed(3);
            const label = col.name === 'hierarchy' ? '' : (col.label || col.name || '');
            const align = getPrintColumnAlignClass(col);
            const hierarchyCls = col.name === 'hierarchy' ? ' print-col-hierarchy' : '';
            return `<th class="print-col-${col.name}${align}${hierarchyCls}" style="width:${pct}%">${label}</th>`;
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

        const tableBlock = showTable && visibleCols.length ? (() => {
            const headerRowCount = 1 + (showInlineBars && visibleCols.length ? 1 : 0);
            const linkSvg = (showLinks && showInlineBars && rowIdx)
                ? `<svg class="print-inline-links" viewBox="0 0 100 100" preserveAspectRatio="none">${buildPrintLinkPaths(rowMap, rowIdx, startMs, span, headerRowCount)}</svg>`
                : '';
            const wbsCls = ps.print_wbs_colors === false ? ' print-no-wbs-colors' : '';
            const gridCls = ps.print_grid_lines !== false ? ' print-show-grid' : '';
            const repeatCls = ps.repeat_header !== false ? ' print-repeat-header' : '';
            const fitCls = ps.fit_to_page ? ' print-fit-page' : '';
            const colorBarsCls = ps.print_color_bars === false ? ' print-mono-bars' : '';
            return `<div class="print-schedule-wrap${wbsCls}${gridCls}${repeatCls}${fitCls}${colorBarsCls}" style="--print-font-size:${printFontPt}pt;--print-row-height:${printRowH}px;--print-chart-width:${barTablePct.toFixed(2)}%" data-print-orientation="${ps.orientation || 'landscape'}">
                ${linkSvg}
                <table class="schedule-print-table schedule-print-table-compact schedule-print-table-visible-cols">
                <thead><tr>
                    ${colHeaders}${evmHeader}${barHeader}
                </tr>${tsRow}</thead>
                <tbody>${rows}</tbody>
            </table></div>`;
        })() : '';

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
        sheet.dataset.printOrientation = ps.orientation || 'landscape';
    }

    function printGantt() {
        buildPrintSheet();
        const sheet = document.getElementById('schedulePrintSheet');
        if (!sheet || !sheet.innerHTML.trim()) {
            showScheduleAlert('Nothing to print — add activities first.', 'warning');
            return;
        }
        const ps = scheduleSettings.print_settings || {};
        const orient = sheet.dataset.printOrientation || ps.orientation || 'landscape';
        const paper = ps.paper_size || 'letter';
        const margin = parseFloat(ps.margin_in) || 0.35;
        const scale = parseInt(ps.print_scale, 10) || 100;
        let pageStyle = document.getElementById('sched-print-page-style');
        if (!pageStyle) {
            pageStyle = document.createElement('style');
            pageStyle.id = 'sched-print-page-style';
            document.head.appendChild(pageStyle);
        }
        const pageSize = paper === 'a4' ? 'A4' : (paper === 'legal' ? 'legal' : (paper === 'tabloid' ? 'tabloid' : 'letter'));
        pageStyle.textContent = `@media print {
            @page { size: ${pageSize} ${orient}; margin: ${margin}in; }
            body.printing-gantt #schedulePrintSheet { zoom: ${scale / 100}; }
        }`;
        document.body.classList.toggle('printing-gantt-show-footer', sheet.dataset.printFooter === '1');
        document.body.classList.toggle('printing-gantt-fit-page', ps.fit_to_page === true);
        document.body.classList.toggle('printing-gantt-portrait', orient === 'portrait');
        document.body.classList.add('printing-gantt');
        requestAnimationFrame(() => {
            window.print();
            setTimeout(() => {
                document.body.classList.remove(
                    'printing-gantt',
                    'printing-gantt-show-footer',
                    'printing-gantt-portrait',
                    'printing-gantt-fit-page'
                );
            }, 800);
        });
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

    function hideAllOptionalColumns() {
        const keep = new Set(['hierarchy', 'collapse', 'wbs', 'activity_id', 'text', 'duration', 'start_date', 'end_date']);
        let hidden = 0;
        (gantt.config.columns || []).forEach(c => {
            if (keep.has(c.name) || REQUIRED_COLUMNS.includes(c.name) || isAddColumnCol(c)) return;
            if (!hiddenColumns.includes(c.name)) {
                hiddenColumns.push(c.name);
                hidden++;
            }
        });
        customColumns = customColumns.filter(c => keep.has(c.map_to || c.name));
        gantt.config.columns = buildColumnConfig();
        gridSelection = { type: null };
        updateGridWidth();
        gantt.render();
        queueSave();
        showScheduleAlert(hidden ? `Hidden ${hidden} optional columns. Use + or Columns to add them back.` : 'Only standard columns are visible.', 'success');
        document.getElementById('scheduleColumnManagerModal')?.close();
    }

    function showAllOptionalColumns() {
        if (typeof CasePMScheduleFields === 'undefined') {
            return showScheduleAlert('Field catalog not loaded.', 'error');
        }
        if (!confirm('Add all optional schedule fields as columns? You can remove them later from the Columns manager or by selecting a column and pressing Delete.')) return;
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
        resizeGanttHost();
        requestAnimationFrame(() => {
            syncScheduleProjectContext();
            resizeGanttHost();
            syncGanttLayout();
            focusInitialTimelineView();
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
                syncGanttLayout();
                focusInitialTimelineView();
                refreshTimelinePanBar();
                setTimeout(() => { syncGanttLayout(); refreshTimelinePanBar(); }, 250);
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
        showAllOptionalColumns, hideAllOptionalColumns, showFeaturesChecklist, showKeyboardShortcuts,
        exportJson, importFile, printGantt, printLookAhead, showPrintSetup, savePrintSettings, setPrintColumnToggle,
        showHeaderFooterSetup, saveHeaderFooterSettings, onHeaderLogoSelected, clearHeaderLogo,
        saveSchedule,
        loadSchedule, loadP6DemoSchedule, clearSchedule, showColumnManager, showAddColumnDialog, removeColumn, removeSelectedColumn, selectGridColumn, hideAllOptionalColumns, addFieldColumn, queueSave,
        setGridCellAlignH, setGridCellAlignV, setGridFontSize, setGridFontColor, setGridRowHeight, saveBarSettingsAsDefaults,
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
