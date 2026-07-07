/* Case PM — Primavera / MS Project style scheduling application */
(function () {
    'use strict';

    const STORAGE_KEY = 'casepm_schedule_v3';
    const LINK_TYPES = { FS: '0', SS: '1', FF: '2', SF: '3' };
    const LINK_LABELS = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' };

    const EDITORS = {
        text: { type: 'text', map_to: 'text' },
        number: { type: 'number', map_to: 'duration', min: 0, max: 9999 },
        date: { type: 'date', map_to: 'start_date' },
        end_date: { type: 'date', map_to: 'end_date' },
        progress: { type: 'number', map_to: 'progress', min: 0, max: 1 },
        predecessors: { type: 'predecessor', map_to: 'auto' }
    };

    let ganttReady = false;
    let saveTimer = null;
    let baselines = [];
    let customColumns = [];
    let scheduleSettings = {
        data_date: CasePMSchedule.formatDate(new Date()),
        calendar: 'standard',
        lookahead_days: 14
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
                duration: 1,
                progress: 0
            }],
            links: []
        };
    }

    function predTemplate(task) {
        const links = task.$target || [];
        return links.map(lid => {
            const link = gantt.getLink(lid);
            const src = gantt.getTask(link.source);
            const code = gantt.getWBSCode ? gantt.getWBSCode(src) : src.id;
            const lag = link.lag ? (link.lag > 0 ? `+${link.lag}` : link.lag) : '';
            return `${code}${LINK_LABELS[link.type] || 'FS'}${lag}`;
        }).join(', ');
    }

    function buildColumnConfig() {
        const cols = [
            { name: 'wbs', label: 'WBS', width: 55, align: 'center', resize: true, template: gantt.getWBSCode },
            { name: 'text', label: 'Activity Name', tree: true, width: 200, min_width: 100, resize: true, editor: EDITORS.text },
            { name: 'duration', label: 'Dur', align: 'center', width: 50, min_width: 40, resize: true, editor: EDITORS.number },
            { name: 'start_date', label: 'Start', align: 'center', width: 95, min_width: 80, resize: true, editor: EDITORS.date },
            { name: 'end_date', label: 'Finish', align: 'center', width: 95, min_width: 80, resize: true, editor: EDITORS.end_date },
            {
                name: 'predecessors', label: 'Predecessors', width: 110, min_width: 70, resize: true,
                editor: EDITORS.predecessors, template: predTemplate
            },
            {
                name: 'progress', label: '%', align: 'center', width: 45, min_width: 40, resize: true,
                editor: { type: 'number', map_to: 'progress', min: 0, max: 100 },
                template: t => Math.round((t.progress || 0) <= 1 ? (t.progress || 0) * 100 : (t.progress || 0))
            },
            { name: 'resource', label: 'Resource', width: 100, min_width: 60, resize: true, editor: { type: 'text', map_to: 'resource' } },
            { name: 'owner', label: 'Responsible', width: 100, min_width: 60, resize: true, editor: { type: 'text', map_to: 'owner' } },
            {
                name: 'bar_color', label: 'Bar Color', width: 70, align: 'center', resize: true,
                template: t => t.bar_color ? `<span style="display:inline-block;width:14px;height:14px;border-radius:3px;background:${t.bar_color}"></span>` : '—',
                editor: { type: 'text', map_to: 'bar_color' }
            }
        ];

        customColumns.forEach(cc => {
            cols.push({
                name: cc.name,
                label: cc.label,
                width: cc.width || 90,
                min_width: 50,
                resize: true,
                editor: { type: 'text', map_to: cc.name },
                template: t => t[cc.name] || ''
            });
        });

        return cols;
    }

    function configureGantt() {
        gantt.plugins({
            critical_path: true,
            auto_scheduling: true,
            multiselect: true,
            tooltip: true,
            marker: true
        });

        gantt.config.date_format = '%Y-%m-%d';
        gantt.config.xml_date = '%Y-%m-%d';
        gantt.config.work_time = true;
        gantt.config.correct_work_time = true;
        gantt.config.skip_off_time = true;
        gantt.config.duration_unit = 'day';
        gantt.config.time_step = 1440;
        gantt.config.row_height = 34;
        gantt.config.bar_height = 22;
        gantt.config.fit_tasks = true;
        gantt.config.show_errors = false;
        gantt.config.auto_scheduling = true;
        gantt.config.auto_scheduling_strict = false;
        gantt.config.highlight_critical_path = true;
        gantt.config.grid_elastic_columns = 'min_width';
        gantt.config.reorder_grid_columns = true;
        gantt.config.open_tree_initially = true;

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

        gantt.config.lightbox.sections = [
            { name: 'description', height: 40, map_to: 'text', type: 'textarea', focus: true },
            { name: 'type', type: 'typeselect', map_to: 'type' },
            { name: 'time', type: 'duration', map_to: 'auto' },
            { name: 'predecessors', type: 'predecessor', map_to: 'auto' },
            {
                name: 'progress_section', type: 'template', map_to: 'progress',
                options: {
                    template: (task) => {
                        const pct = Math.round((task.progress || 0) * 100);
                        return `<label style="display:block;margin:8px 0 4px">% Complete: <b>${pct}%</b></label>
                            <input type="range" min="0" max="100" value="${pct}" style="width:100%"
                                oninput="this.previousElementSibling.innerHTML='% Complete: <b>'+this.value+'%</b>'"
                                onchange="gantt.getTask(${task.id}).progress=parseInt(this.value,10)/100;gantt.updateTask(${task.id})">`;
                    }
                }
            },
            { name: 'resource', height: 30, map_to: 'resource', type: 'textarea' },
            { name: 'owner', height: 30, map_to: 'owner', type: 'textarea' },
            {
                name: 'bar_color_section', type: 'template', map_to: 'bar_color',
                options: {
                    template: (task) => {
                        const c = task.bar_color || '#3b82f6';
                        return `<label style="display:block;margin:4px 0">Gantt Bar Color</label>
                            <input type="color" value="${c}" style="width:60px;height:32px;border:none;cursor:pointer"
                                onchange="gantt.getTask(${task.id}).bar_color=this.value;gantt.updateTask(${task.id});gantt.render()">`;
                    }
                }
            },
            { name: 'constraint', type: 'constraint' }
        ];

        gantt.templates.task_class = function (start, end, task) {
            const classes = [];
            if (gantt.config.highlight_critical_path && gantt.isCriticalTask(task)) classes.push('cpm_critical');
            if (task.type === 'milestone') classes.push('cpm_milestone');
            if (task.type === 'project') classes.push('cpm_summary');
            const p = Math.round((task.progress || 0) * 100);
            if (p >= 100) classes.push('cpm_complete');
            else if (p > 0) classes.push('cpm_in_progress');
            return classes.join(' ');
        };

        gantt.templates.task_style = function (start, end, task) {
            if (task.bar_color && task.type !== 'project') {
                return `background-color:${task.bar_color};border-color:${task.bar_color};`;
            }
            return '';
        };

        gantt.templates.tooltip_text = function (start, end, task) {
            const preds = predTemplate(task);
            return `<b>${task.text}</b><br/>
                Start: ${gantt.templates.tooltip_date_format(start)}<br/>
                Finish: ${gantt.templates.tooltip_date_format(end)}<br/>
                Duration: ${task.duration}d<br/>
                Progress: ${Math.round((task.progress || 0) * 100)}%<br/>
                ${preds ? 'Predecessors: ' + preds : ''}`;
        };

        gantt.attachEvent('onTaskDblClick', function (id, e) {
            if (e.target && e.target.closest('.gantt_grid')) {
                gantt.showLightbox(id);
                return false;
            }
            return true;
        });

        gantt.attachEvent('onAfterTaskUpdate', (id, task) => {
            if (task.progress > 1) {
                task.progress = Math.min(1, task.progress / 100);
                gantt.refreshTask(id);
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
        gantt.attachEvent('onColumnResizeEnd', () => { gantt.render(); queueSave(); });
        gantt.attachEvent('onGanttRender', () => { updateStatusBar(); injectColumnAddButton(); });

        gantt.init('gantt_here');
        ganttReady = true;
        resizeGanttHost();
        window.addEventListener('resize', resizeGanttHost);
    }

    function injectColumnAddButton() {
        const head = document.querySelector('.gantt_grid_head_cell[data-column-id="bar_color"]');
        if (!head || document.getElementById('ganttColAddBtn')) return;
        const btn = document.createElement('button');
        btn.id = 'ganttColAddBtn';
        btn.type = 'button';
        btn.title = 'Add custom column';
        btn.className = 'gantt-col-add-btn';
        btn.innerHTML = '+';
        btn.onclick = (e) => { e.stopPropagation(); showAddColumnDialog(); };
        const lastHead = document.querySelector('.gantt_grid_scale .gantt_grid_head_cell:last-child');
        if (lastHead) {
            lastHead.style.position = 'relative';
            lastHead.appendChild(btn);
        }
    }

    function resizeGanttHost() {
        const host = document.getElementById('scheduleGanttHost');
        const chrome = document.getElementById('scheduleChrome');
        if (!host || !chrome) return;
        const top = chrome.getBoundingClientRect().bottom;
        const status = document.getElementById('scheduleStatusBar');
        const statusH = status ? status.offsetHeight + 12 : 40;
        const h = Math.max(320, window.innerHeight - top - statusH - 16);
        host.style.height = h + 'px';
        if (ganttReady) gantt.render();
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
                start_date: t.start_date ? gantt.templates.format_date(t.start_date) : undefined,
                end_date: t.end_date ? gantt.templates.format_date(t.end_date) : undefined,
                duration: t.duration,
                progress: t.progress,
                open: t.open,
                resource: t.resource,
                owner: t.owner,
                bar_color: t.bar_color,
                constraint_type: t.constraint_type,
                constraint_date: t.constraint_date
            };
            customColumns.forEach(cc => { row[cc.name] = t[cc.name] || ''; });
            data.push(row);
        });
        const links = gantt.getLinks().map(l => ({
            id: l.id, source: l.source, target: l.target, type: String(l.type), lag: l.lag || 0
        }));
        return { data, links, baselines, customColumns, settings: scheduleSettings };
    }

    function loadSchedulePayload(payload) {
        if (!payload || !payload.data) return false;
        customColumns = payload.customColumns || [];
        gantt.config.columns = buildColumnConfig();
        gantt.clearAll();
        gantt.parse({ data: payload.data, links: payload.links || [] });
        baselines = payload.baselines || [];
        if (payload.settings) scheduleSettings = Object.assign(scheduleSettings, payload.settings);
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
        } catch (e) {
            setSaveStatus('Saved locally');
        }
    }

    function getSelectedProjectId() {
        const sel = document.getElementById('scheduleProjectSelect');
        return sel ? parseInt(sel.value, 10) || 1 : 1;
    }

    function applySettingsToUI() {
        const dd = document.getElementById('dataDateInput');
        const la = document.getElementById('lookaheadDaysInput');
        if (dd) dd.value = scheduleSettings.data_date || CasePMSchedule.formatDate(new Date());
        if (la) la.value = scheduleSettings.lookahead_days || 14;
    }

    function setSaveStatus(msg) {
        const el = document.getElementById('scheduleSaveStatus');
        if (el) el.textContent = msg;
    }

    // ─── Toolbar ───
    function addActivity(type) {
        const parent = gantt.getSelectedId() || 0;
        const today = CasePMSchedule.formatDate(new Date());
        const id = gantt.addTask({
            text: type === 'milestone' ? 'New Milestone' : 'New Activity',
            type: type || 'task',
            start_date: today,
            duration: type === 'milestone' ? 0 : 5,
            progress: 0,
            parent: parent
        }, parent);
        gantt.selectTask(id);
        gantt.showLightbox(id);
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
        if (gantt.autoSchedule) gantt.autoSchedule();
        gantt.render();
        updateStatusBar();
    }

    function showAddColumnDialog() {
        const label = prompt('New column header name:', 'Custom Field');
        if (!label || !label.trim()) return;
        const name = 'col_' + label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');
        if (customColumns.find(c => c.name === name)) {
            showScheduleAlert('Column already exists.', 'warning');
            return;
        }
        customColumns.push({ name, label: label.trim(), width: 100 });
        gantt.config.columns = buildColumnConfig();
        gantt.render();
        queueSave();
        showScheduleAlert(`Column "${label}" added. Click any cell to edit inline.`, 'success');
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
            const critical = gantt.isCriticalTask(t);
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-zinc-800/50 border-b border-zinc-800';
            tr.innerHTML = `
                <td class="px-3 py-2 font-mono text-xs">${gantt.getWBSCode(t)}</td>
                <td class="px-3 py-2 ${critical ? 'text-red-400' : ''}">${t.text}</td>
                <td class="px-3 py-2 text-center">${t.duration}</td>
                <td class="px-3 py-2">${gantt.templates.format_date(t.start_date)}</td>
                <td class="px-3 py-2">${t.end_date ? gantt.templates.format_date(t.end_date) : '—'}</td>
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
        gantt.eachTask(t => { if (t.type !== 'project' && gantt.isCriticalTask(t)) critical++; });
        el.innerHTML = `
            <span>Start: <b>${gantt.templates.format_date(range.start_date)}</b></span>
            <span>Finish: <b>${gantt.templates.format_date(range.end_date)}</b></span>
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
        linkSelected, unlinkSelected, zoomGantt, toggleCriticalPath, setBaseline,
        runSchedule, switchScheduleView, renderLookAhead, focusActivity,
        exportJson, importFile, printGantt, printLookAhead, saveSchedule,
        loadSchedule, clearSchedule, showAddColumnDialog
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
