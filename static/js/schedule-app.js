/* Case PM — Primavera / MS Project style scheduling application */
(function () {
    'use strict';

    const STORAGE_KEY = 'casepm_schedule_v4';
    const LINK_TYPES = { FS: '0', SS: '1', FF: '2', SF: '3' };
    const LINK_LABELS = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' };

    const EXTENDED_FIELDS = [
        'activity_id', 'resource', 'owner', 'work_hours', 'cost', 'fixed_cost',
        'actual_start', 'actual_finish', 'remaining_duration', 'constraint_type', 'constraint_date',
        'deadline', 'priority', 'calendar', 'activity_code', 'phase', 'discipline',
        'bar_color', 'notes', 'hyperlink', 'free_float', 'total_float'
    ];

    let ganttReady = false;
    let saveTimer = null;
    let resizeTimer = null;
    let baselines = [];
    let customColumns = [];
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
        link_width: 2
    };

    function buildEmptySchedule() {
        const today = CasePMSchedule.formatDate(new Date());
        return {
            data: [{
                id: 1,
                text: 'New Construction Project',
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

    function updateGridWidth() {
        if (!ganttReady || !gantt.config.columns) return;
        const width = gantt.config.columns.reduce((sum, col) => sum + (parseInt(col.width, 10) || 0), 0);
        gantt.config.grid_width = width;
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
        gantt.eachTask(id => sanitizeTaskDates(gantt.getTask(id)));
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

    function editorForField(field) {
        if (!field || field.type === 'readonly' || field.type === 'successors') return null;
        if (field.type === 'predecessor') return { type: 'predecessor', map_to: 'auto' };
        if (field.type === 'date') return { type: 'date', map_to: field.map_to };
        if (field.type === 'number') return { type: 'number', map_to: field.map_to, min: 0, max: 999999 };
        if (field.type === 'percent') return { type: 'number', map_to: field.map_to, min: 0, max: 100 };
        return { type: 'text', map_to: field.map_to };
    }

    function buildColumnConfig() {
        const builtins = [
            { name: 'wbs', label: 'WBS', width: 55, align: 'center', resize: true, template: t => wbsCode(t) },
            { name: 'activity_id', label: 'ID', width: 60, align: 'center', resize: true, editor: { type: 'text', map_to: 'activity_id' }, template: t => t.activity_id || '' },
            { name: 'text', label: 'Activity Name', tree: true, width: 200, min_width: 100, resize: true, editor: { type: 'text', map_to: 'text' } },
            { name: 'duration', label: 'Dur', align: 'center', width: 50, min_width: 40, resize: true, editor: { type: 'number', map_to: 'duration', min: 0, max: 9999 } },
            { name: 'start_date', label: 'Start', align: 'center', width: 95, min_width: 80, resize: true, editor: { type: 'date', map_to: 'start_date' }, template: t => formatDateSafe(t.start_date) },
            { name: 'end_date', label: 'Finish', align: 'center', width: 95, min_width: 80, resize: true, editor: { type: 'date', map_to: 'end_date' }, template: t => formatDateSafe(t.end_date) },
            { name: 'predecessors', label: 'Predecessors', width: 110, min_width: 70, resize: true, editor: { type: 'predecessor', map_to: 'auto' }, template: predTemplate },
            { name: 'successors', label: 'Successors', width: 100, min_width: 70, resize: true, template: succTemplate },
            { name: 'progress', label: '%', align: 'center', width: 45, min_width: 40, resize: true, editor: { type: 'number', map_to: 'progress', min: 0, max: 100 }, template: t => Math.round((t.progress || 0) <= 1 ? (t.progress || 0) * 100 : (t.progress || 0)) },
            { name: 'resource', label: 'Resource', width: 100, min_width: 60, resize: true, editor: { type: 'text', map_to: 'resource' } },
            { name: 'owner', label: 'Responsible', width: 100, min_width: 60, resize: true, editor: { type: 'text', map_to: 'owner' } },
            { name: 'total_float', label: 'Total Float', width: 70, align: 'center', resize: true, template: t => t.$slack != null ? t.$slack : (t.total_float != null ? t.total_float : '') },
            { name: 'bar_color', label: 'Color', width: 55, align: 'center', resize: true, template: t => t.bar_color ? `<span class="sched-color-swatch" style="background:${t.bar_color}"></span>` : '—', editor: { type: 'text', map_to: 'bar_color' } }
        ];

        const cols = builtins.map(c => Object.assign({}, c, { width: colWidth(c.name, c.width) }));

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

        return cols;
    }

    function configureGantt() {
        if (gantt.plugins) {
            gantt.plugins({ tooltip: true });
        }

        gantt.config.date_format = '%Y-%m-%d';
        gantt.config.xml_date = '%Y-%m-%d';
        gantt.config.work_time = false;
        gantt.config.correct_work_time = false;
        gantt.config.skip_off_time = false;
        gantt.config.duration_unit = 'day';
        gantt.config.time_step = 1440;
        gantt.config.row_height = 34;
        gantt.config.bar_height = 22;
        gantt.config.scale_height = 50;
        gantt.config.scroll_size = 20;
        gantt.config.fit_tasks = true;
        gantt.config.show_errors = false;
        gantt.config.highlight_critical_path = true;
        gantt.config.grid_elastic_columns = false;
        gantt.config.keep_grid_width = true;
        gantt.config.reorder_grid_columns = false;
        gantt.config.open_tree_initially = true;
        gantt.config.details_on_dblclick = false;

        gantt.config.layout = {
            css: 'gantt_container',
            cols: [
                {
                    width: 580,
                    min_width: 320,
                    max_width: 900,
                    rows: [{ view: 'grid', scrollY: 'scrollVer' }]
                },
                { resizer: true, width: 1 },
                {
                    rows: [
                        { view: 'timeline', scrollX: 'scrollHor', scrollY: 'scrollVer' },
                        { view: 'scrollbar', id: 'scrollHor', height: 20 }
                    ]
                },
                { view: 'scrollbar', id: 'scrollVer' }
            ]
        };

        gantt.config.columns = buildColumnConfig();

        gantt.attachEvent('onBeforeLightbox', () => false);

        gantt.attachEvent('onTaskLoading', (task) => {
            sanitizeTaskDates(task);
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
            const p = Math.round((task.progress || 0) * 100);
            if (p >= 100) classes.push('cpm_complete');
            else if (p > 0) classes.push('cpm_in_progress');
            return classes.join(' ');
        };

        gantt.templates.task_style = function (start, end, task) {
            if (task.type === 'project') return '';
            let color = task.bar_color;
            if (!color) {
                if (isTaskCritical(task)) color = scheduleSettings.critical_bar_color;
                else if (Math.round((task.progress || 0) * 100) >= 100) color = scheduleSettings.complete_bar_color;
                else if ((task.progress || 0) > 0) color = scheduleSettings.progress_bar_color;
                else if (task.type === 'milestone') color = scheduleSettings.milestone_color;
                else color = scheduleSettings.default_bar_color;
            }
            return `background-color:${color}55;border:2px solid ${color};box-shadow:0 0 8px ${color}44;`;
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
                Progress: ${Math.round((task.progress || 0) * 100)}%<br/>
                ${preds ? 'Predecessors: ' + preds : ''}`;
        };

        gantt.attachEvent('onTaskClick', function (id, e) {
            const target = e.target || e.srcElement;
            if (!target.closest || !target.closest('.gantt_grid')) return true;
            if (target.closest('.gantt_tree_icon')) return true;
            const pos = gantt.locateCell && gantt.locateCell(target);
            if (!pos) return true;
            const col = gantt.config.columns[pos.column];
            if (!col || !col.editor || col.name === 'wbs' || col.name === 'successors') return true;
            setTimeout(() => {
                if (gantt.ext && gantt.ext.inlineEditors) {
                    gantt.ext.inlineEditors.startEdit(id, col.name);
                } else if (gantt.inlineEditors) {
                    gantt.inlineEditors.startEdit(id, col.name);
                }
            }, 0);
            return false;
        });

        gantt.attachEvent('onTaskDblClick', function (id) {
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
            if (task.progress > 1) {
                task.progress = Math.min(1, task.progress / 100);
            }
            queueSave();
        });
        gantt.attachEvent('onAfterTaskAdd', queueSave);
        gantt.attachEvent('onAfterTaskDelete', queueSave);
        gantt.attachEvent('onAfterLinkAdd', queueSave);
        gantt.attachEvent('onAfterLinkUpdate', queueSave);
        gantt.attachEvent('onAfterLinkDelete', queueSave);
        gantt.attachEvent('onAfterTaskDrag', queueSave);
        gantt.attachEvent('onAfterColumnReorder', queueSave);
        gantt.attachEvent('onColumnResizeEnd', function (index, column, new_width) {
            if (column && column.name) columnWidths[column.name] = new_width;
            updateGridWidth();
            queueSave();
        });
        gantt.attachEvent('onGanttRender', () => {
            refreshWbsCodes();
            updateStatusBar();
        });

        updateGridWidth();
        gantt.init('gantt_here');
        sanitizeAllTaskDates();
        ganttReady = true;
        resizeGanttHost();
        window.addEventListener('resize', resizeGanttHost);
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
        resizeTimer = setTimeout(() => gantt.render(), 80);
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
        return { data, links, baselines, customColumns, columnWidths, settings: scheduleSettings };
    }

    function loadSchedulePayload(payload) {
        if (!payload || !payload.data) return false;
        customColumns = payload.customColumns || [];
        columnWidths = payload.columnWidths || {};
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
        gantt.render();
        setSaveStatus('Ready');
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
        const sel = document.getElementById('scheduleProjectSelect');
        return sel ? parseInt(sel.value, 10) || 1 : 1;
    }

    function applyGanttDisplayStyles() {
        const s = scheduleSettings;
        const root = document.documentElement;
        root.style.setProperty('--gantt-bar-normal', s.default_bar_color || '#3b82f6');
        root.style.setProperty('--gantt-bar-critical', s.critical_bar_color || '#ef4444');
        root.style.setProperty('--gantt-bar-progress', s.progress_bar_color || '#f59e0b');
        root.style.setProperty('--gantt-bar-complete', s.complete_bar_color || '#71717a');
        root.style.setProperty('--gantt-milestone', s.milestone_color || '#8b5cf6');
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
        applyGanttDisplayStyles();
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
    }

    function setSaveStatus(msg) {
        const el = document.getElementById('scheduleSaveStatus');
        if (el) el.textContent = msg;
    }

    // ─── Toolbar ───
    function addActivity(type) {
        const parent = gantt.getSelectedId() || 0;
        const today = toGanttDate(CasePMSchedule.formatDate(new Date()));
        const id = gantt.addTask({
            text: type === 'milestone' ? 'New Milestone' : 'New Activity',
            type: type || 'task',
            start_date: today,
            end_date: type === 'milestone' ? today : CasePMSchedule.addCalendarDays(today, 5),
            duration: type === 'milestone' ? 0 : 5,
            progress: 0,
            parent: parent
        }, parent);
        gantt.selectTask(id);
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

    function indentSelected() {
        const id = gantt.getSelectedId();
        if (!id) return;
        const prev = gantt.getPrevSibling(id);
        if (prev) gantt.moveTask(id, gantt.getChildren(prev).length, prev);
    }

    function outdentSelected() {
        const id = gantt.getSelectedId();
        if (!id) return;
        const parent = gantt.getParent(id);
        if (!parent) return;
        const gp = gantt.getParent(parent);
        gantt.moveTask(id, gantt.getTaskIndex(parent) + 1, gp);
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
        showScheduleAlert(`Baseline saved: ${name}`, 'success');
        queueSave();
    }

    function runSchedule() {
        const tasks = [];
        gantt.eachTask(t => tasks.push(Object.assign({}, t)));
        const links = gantt.getLinks().map(l => Object.assign({}, l));
        const { updates, wbsMap } = CasePMSchedule.runCPM(tasks, links);
        updates.forEach((patch, id) => {
            if (!gantt.isTaskExists(id)) return;
            const task = gantt.getTask(id);
            if (patch.start_date) task.start_date = toGanttDate(patch.start_date);
            if (patch.end_date) task.end_date = toGanttDate(patch.end_date);
            if (patch.total_float != null) task.total_float = patch.total_float;
            if (patch.free_float != null) task.free_float = patch.free_float;
            task.$slack = patch.$slack;
            task.$critical = patch.$critical;
            sanitizeTaskDates(task);
            gantt.refreshTask(id);
        });
        sanitizeAllTaskDates();
        wbsCodeMap = wbsMap || CasePMSchedule.buildWbsMap(tasks);
        gantt.render();
        updateStatusBar();
        queueSave();
        logActivity('Ran CPM schedule', `${updates.size} activities calculated`);
    }

    function showAddColumnDialog() {
        const dlg = document.getElementById('scheduleFieldPickerModal');
        if (!dlg || typeof CasePMScheduleFields === 'undefined') {
            showScheduleAlert('Field catalog not loaded.', 'error');
            return;
        }
        const existing = gantt.config.columns.map(c => c.name);
        const addable = CasePMScheduleFields.getAddableFields(existing);
        const container = document.getElementById('scheduleFieldPickerList');
        if (!addable.length) {
            container.innerHTML = '<p class="text-zinc-400 text-sm p-4">All standard fields are already visible in the grid.</p>';
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
        dlg.showModal();
    }

    function addFieldColumn(mapTo) {
        const field = CasePMScheduleFields.getField(mapTo);
        if (!field) return;
        if (customColumns.find(c => (c.map_to || c.name) === mapTo)) {
            showScheduleAlert('Column already visible.', 'warning');
            return;
        }
        customColumns.push({ name: mapTo, map_to: mapTo, label: field.label, width: 100 });
        gantt.config.columns = buildColumnConfig();
        updateGridWidth();
        gantt.render();
        document.getElementById('scheduleFieldPickerModal')?.close();
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
        gantt.eachTask(t => { if (t.type !== 'project' && isTaskCritical(t)) critical++; });
        el.innerHTML = `
            <span>Start: <b>${formatDateSafe(range.start_date)}</b></span>
            <span>Finish: <b>${formatDateSafe(range.end_date)}</b></span>
            <span>Activities: <b>${countTasks()}</b></span>
            <span>Critical: <b class="text-red-400">${critical}</b></span>
            <span class="text-zinc-600">| Click cell to edit · Double-click row for full detail · Drag column borders to resize</span>`;
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

    function printGantt() {
        document.body.classList.add('printing-gantt');
        const panel = document.getElementById('ganttViewPanel');
        if (panel) panel.classList.add('print-active');
        switchScheduleView('gantt');
        gantt.render();
        setTimeout(() => {
            window.print();
            setTimeout(() => {
                document.body.classList.remove('printing-gantt');
                panel?.classList.remove('print-active');
            }, 500);
        }, 300);
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
        dlg.className = 'bg-zinc-900 border border-zinc-700 rounded-2xl p-0 w-full max-w-md shadow-2xl';
        dlg.innerHTML = `<div class="px-5 py-3 border-b border-zinc-700 ${colors[type] || 'text-sky-400'} font-semibold text-sm">${type || 'Notice'}</div>
            <div class="px-5 py-4 text-sm text-zinc-200">${message}</div>
            <div class="px-5 py-3 border-t border-zinc-700 flex justify-end">
                <button class="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm">OK</button>
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
        runSchedule();
        switchScheduleView('gantt');

        document.getElementById('scheduleProjectSelect')?.addEventListener('change', async () => {
            await loadSchedule();
            runSchedule();
        });
        document.getElementById('dataDateInput')?.addEventListener('change', () => {
            scheduleSettings.data_date = document.getElementById('dataDateInput').value;
            queueSave();
        });
    }

    window.ScheduleApp = {
        init, addActivity, deleteSelected, indentSelected, outdentSelected,
        linkSelected, unlinkSelected, zoomGantt, setTimescale, showDisplaySettings, saveDisplaySettings,
        wbsCode,
        toggleCriticalPath, setBaseline,
        runSchedule, switchScheduleView, renderLookAhead, focusActivity,
        exportJson, importFile, printGantt, printLookAhead, saveSchedule,
        loadSchedule, clearSchedule, showAddColumnDialog, addFieldColumn, queueSave
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
