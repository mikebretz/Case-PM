/* Case PM — Primavera / MS Project style scheduling application */
(function () {
    'use strict';

    const STORAGE_KEY = 'casepm_schedule_v2';
    const LINK_TYPES = { FS: '0', SS: '1', FF: '2', SF: '3' };
    const LINK_LABELS = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' };

    let ganttReady = false;
    let currentProjectId = null;
    let saveTimer = null;
    let baselines = [];
    let scheduleSettings = {
        data_date: CasePMSchedule.formatDate(new Date()),
        calendar: 'standard',
        lookahead_days: 14
    };

    // ─── Sample construction schedule (WBS + logic) ───
    function buildSampleSchedule() {
        const today = new Date();
        const d = (offset) => CasePMSchedule.formatDate(CasePMSchedule.addWorkDays(today, offset));
        return {
            data: [
                { id: 1, text: '1.0 General Requirements', type: 'project', open: true, start_date: d(0), duration: 120, progress: 0.15 },
                { id: 2, text: '1.1 Mobilization & Site Setup', parent: 1, start_date: d(0), duration: 5, progress: 1, resource: 'GC Superintendent', owner: 'General Contractor' },
                { id: 3, text: '1.2 Temporary Facilities', parent: 1, start_date: d(3), duration: 8, progress: 0.6, resource: 'Site Services', owner: 'General Contractor' },
                { id: 4, text: '1.3 Survey & Layout', parent: 1, start_date: d(5), duration: 3, progress: 0.4, resource: 'Surveyor', owner: 'Survey Co' },

                { id: 10, text: '2.0 Site & Earthwork', type: 'project', open: true, start_date: d(8), duration: 25, progress: 0.1 },
                { id: 11, text: '2.1 Clearing & Grubbing', parent: 10, start_date: d(8), duration: 4, progress: 0, resource: 'Earthwork Crew', owner: 'Sitework Sub' },
                { id: 12, text: '2.2 Mass Excavation', parent: 10, start_date: d(12), duration: 8, progress: 0, resource: 'Excavator', owner: 'Sitework Sub' },
                { id: 13, text: '2.3 Utility Trenching', parent: 10, start_date: d(18), duration: 6, progress: 0, resource: 'Underground', owner: 'Utilities Sub' },
                { id: 14, text: '2.4 Backfill & Compaction', parent: 10, start_date: d(24), duration: 5, progress: 0, resource: 'Earthwork Crew', owner: 'Sitework Sub' },

                { id: 20, text: '3.0 Concrete & Foundations', type: 'project', open: true, start_date: d(28), duration: 35, progress: 0 },
                { id: 21, text: '3.1 Footing Formwork', parent: 20, start_date: d(28), duration: 5, progress: 0, resource: 'Concrete Crew', owner: 'Concrete Sub' },
                { id: 22, text: '3.2 Footing Rebar', parent: 20, start_date: d(32), duration: 4, progress: 0, resource: 'Rebar Crew', owner: 'Concrete Sub' },
                { id: 23, text: '3.3 Footing Pour', parent: 20, start_date: d(36), duration: 2, progress: 0, type: 'milestone', resource: 'Concrete Crew', owner: 'Concrete Sub' },
                { id: 24, text: '3.4 Foundation Walls', parent: 20, start_date: d(38), duration: 10, progress: 0, resource: 'Concrete Crew', owner: 'Concrete Sub' },
                { id: 25, text: '3.5 Slab on Grade', parent: 20, start_date: d(48), duration: 8, progress: 0, resource: 'Concrete Crew', owner: 'Concrete Sub' },

                { id: 30, text: '4.0 Structure', type: 'project', open: true, start_date: d(55), duration: 45, progress: 0 },
                { id: 31, text: '4.1 Structural Steel Delivery', parent: 30, start_date: d(55), duration: 1, progress: 0, type: 'milestone', resource: 'Steel Supplier', owner: 'Steel Sub' },
                { id: 32, text: '4.2 Steel Erection L1', parent: 30, start_date: d(56), duration: 12, progress: 0, resource: 'Ironworkers', owner: 'Steel Sub' },
                { id: 33, text: '4.3 Metal Deck', parent: 30, start_date: d(66), duration: 8, progress: 0, resource: 'Steel Crew', owner: 'Steel Sub' },
                { id: 34, text: '4.4 Concrete Fill on Deck', parent: 30, start_date: d(74), duration: 6, progress: 0, resource: 'Concrete Crew', owner: 'Concrete Sub' },

                { id: 40, text: '5.0 Building Envelope', type: 'project', open: true, start_date: d(70), duration: 40, progress: 0 },
                { id: 41, text: '5.1 Roofing', parent: 40, start_date: d(80), duration: 10, progress: 0, resource: 'Roofing Crew', owner: 'Roofing Sub' },
                { id: 42, text: '5.2 Exterior Walls', parent: 40, start_date: d(70), duration: 15, progress: 0, resource: 'Framing Crew', owner: 'Framing Sub' },
                { id: 43, text: '5.3 Windows & Glazing', parent: 40, start_date: d(82), duration: 12, progress: 0, resource: 'Glaziers', owner: 'Glazing Sub' },

                { id: 50, text: '6.0 MEP Rough-In', type: 'project', open: true, start_date: d(75), duration: 35, progress: 0 },
                { id: 51, text: '6.1 Electrical Rough-In', parent: 50, start_date: d(75), duration: 15, progress: 0, resource: 'Electricians', owner: 'Electrical Sub' },
                { id: 52, text: '6.2 Plumbing Rough-In', parent: 50, start_date: d(78), duration: 12, progress: 0, resource: 'Plumbers', owner: 'Plumbing Sub' },
                { id: 53, text: '6.3 HVAC Rough-In', parent: 50, start_date: d(80), duration: 14, progress: 0, resource: 'HVAC Techs', owner: 'Mechanical Sub' },
                { id: 54, text: '6.4 Fire Protection', parent: 50, start_date: d(85), duration: 10, progress: 0, resource: 'Sprinkler Fitters', owner: 'Fire Protection' },

                { id: 60, text: '7.0 Interiors & Closeout', type: 'project', open: true, start_date: d(95), duration: 50, progress: 0 },
                { id: 61, text: '7.1 Drywall & Framing', parent: 60, start_date: d(95), duration: 20, progress: 0, resource: 'Drywall Crew', owner: 'Drywall Sub' },
                { id: 62, text: '7.2 Paint', parent: 60, start_date: d(115), duration: 12, progress: 0, resource: 'Painters', owner: 'Painting Sub' },
                { id: 63, text: '7.3 Flooring', parent: 60, start_date: d(120), duration: 10, progress: 0, resource: 'Floor Installers', owner: 'Flooring Sub' },
                { id: 64, text: '7.4 Final MEP & TAB', parent: 60, start_date: d(125), duration: 8, progress: 0, resource: 'MEP Team', owner: 'MEP Subs' },
                { id: 65, text: '7.5 Punch List & Turnover', parent: 60, start_date: d(135), duration: 10, progress: 0, type: 'milestone', resource: 'GC Team', owner: 'General Contractor' }
            ],
            links: [
                { id: 1, source: 2, target: 3, type: LINK_TYPES.FS, lag: 0 },
                { id: 2, source: 3, target: 4, type: LINK_TYPES.SS, lag: 2 },
                { id: 3, source: 4, target: 11, type: LINK_TYPES.FS, lag: 0 },
                { id: 4, source: 11, target: 12, type: LINK_TYPES.FS, lag: 0 },
                { id: 5, source: 12, target: 13, type: LINK_TYPES.FS, lag: 2 },
                { id: 6, source: 13, target: 14, type: LINK_TYPES.FS, lag: 0 },
                { id: 7, source: 14, target: 21, type: LINK_TYPES.FS, lag: 2 },
                { id: 8, source: 21, target: 22, type: LINK_TYPES.FS, lag: 0 },
                { id: 9, source: 22, target: 23, type: LINK_TYPES.FS, lag: 0 },
                { id: 10, source: 23, target: 24, type: LINK_TYPES.FS, lag: 0 },
                { id: 11, source: 24, target: 25, type: LINK_TYPES.FS, lag: 2 },
                { id: 12, source: 25, target: 31, type: LINK_TYPES.FS, lag: 2 },
                { id: 13, source: 31, target: 32, type: LINK_TYPES.FS, lag: 0 },
                { id: 14, source: 32, target: 33, type: LINK_TYPES.SS, lag: 5 },
                { id: 15, source: 33, target: 34, type: LINK_TYPES.FS, lag: 0 },
                { id: 16, source: 32, target: 42, type: LINK_TYPES.SS, lag: 8 },
                { id: 17, source: 42, target: 41, type: LINK_TYPES.FS, lag: 5 },
                { id: 18, source: 42, target: 43, type: LINK_TYPES.FS, lag: 7 },
                { id: 19, source: 34, target: 51, type: LINK_TYPES.FS, lag: 0 },
                { id: 20, source: 51, target: 52, type: LINK_TYPES.SS, lag: 3 },
                { id: 21, source: 52, target: 53, type: LINK_TYPES.SS, lag: 2 },
                { id: 22, source: 53, target: 54, type: LINK_TYPES.SS, lag: 3 },
                { id: 23, source: 43, target: 61, type: LINK_TYPES.FS, lag: 5 },
                { id: 24, source: 54, target: 61, type: LINK_TYPES.FS, lag: 0 },
                { id: 25, source: 61, target: 62, type: LINK_TYPES.FS, lag: 0 },
                { id: 26, source: 62, target: 63, type: LINK_TYPES.FS, lag: 3 },
                { id: 27, source: 63, target: 64, type: LINK_TYPES.FS, lag: 0 },
                { id: 28, source: 64, target: 65, type: LINK_TYPES.FS, lag: 2 }
            ]
        };
    }

    // ─── Gantt configuration ───
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
        gantt.config.row_height = 32;
        gantt.config.bar_height = 20;
        gantt.config.grid_width = 520;
        gantt.config.autosize = 'y';
        gantt.config.fit_tasks = true;
        gantt.config.show_errors = false;
        gantt.config.auto_scheduling = true;
        gantt.config.auto_scheduling_strict = true;
        gantt.config.highlight_critical_path = true;

        gantt.config.types = {
            project: 'project',
            task: 'task',
            milestone: 'milestone'
        };

        gantt.config.columns = [
            { name: 'wbs', label: 'WBS', width: 50, template: gantt.getWBSCode },
            { name: 'text', label: 'Activity Name', tree: true, width: 200, resize: true },
            { name: 'duration', label: 'Dur', align: 'center', width: 45, resize: true },
            { name: 'start_date', label: 'Start', align: 'center', width: 85, resize: true },
            { name: 'end_date', label: 'Finish', align: 'center', width: 85, resize: true },
            { name: 'predecessors', label: 'Pred', width: 70, resize: true },
            { name: 'progress', label: '%', align: 'center', width: 40, template: (t) => Math.round((t.progress || 0) * 100) },
            { name: 'resource', label: 'Resource', width: 90, resize: true },
            { name: 'owner', label: 'Responsible', width: 100, resize: true },
            { name: 'add', width: 30 }
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

        gantt.templates.tooltip_text = function (start, end, task) {
            const pred = (gantt.getTask(task.id).$target || [])
                .map(id => {
                    const l = gantt.getLink(id);
                    const src = gantt.getTask(l.source);
                    return `${src.text} (${LINK_LABELS[l.type] || 'FS'}${l.lag ? (l.lag > 0 ? '+' : '') + l.lag : ''})`;
                }).join(', ');
            return `<b>${task.text}</b><br/>
                Start: ${gantt.templates.tooltip_date_format(start)}<br/>
                Finish: ${gantt.templates.tooltip_date_format(end)}<br/>
                Duration: ${task.duration}d<br/>
                Progress: ${Math.round((task.progress || 0) * 100)}%<br/>
                ${pred ? 'Predecessors: ' + pred : ''}`;
        };

        gantt.config.lightbox.sections = [
            { name: 'description', height: 38, map_to: 'text', type: 'textarea', focus: true },
            { name: 'type', type: 'typeselect', map_to: 'type' },
            { name: 'time', type: 'duration', map_to: 'auto' },
            { name: 'progress', type: 'checkbox', map_to: 'progress', options: [{ key: 1, label: '100% Complete' }] },
            { name: 'resource', height: 30, map_to: 'resource', type: 'textarea' },
            { name: 'owner', height: 30, map_to: 'owner', type: 'textarea' },
            { name: 'constraint', type: 'constraint' }
        ];

        gantt.attachEvent('onAfterTaskUpdate', queueSave);
        gantt.attachEvent('onAfterTaskAdd', queueSave);
        gantt.attachEvent('onAfterTaskDelete', queueSave);
        gantt.attachEvent('onAfterLinkAdd', queueSave);
        gantt.attachEvent('onAfterLinkUpdate', queueSave);
        gantt.attachEvent('onAfterLinkDelete', queueSave);
        gantt.attachEvent('onAfterTaskDrag', queueSave);
        gantt.attachEvent('onGanttRender', updateStatusBar);

        gantt.init('gantt_here');
        ganttReady = true;
    }

    // ─── Persistence ───
    function serializeSchedule() {
        const data = [];
        gantt.eachTask(t => {
            data.push({
                id: t.id,
                text: t.text,
                parent: t.parent,
                type: t.type,
                start_date: gantt.templates.format_date(t.start_date),
                end_date: t.end_date ? gantt.templates.format_date(t.end_date) : undefined,
                duration: t.duration,
                progress: t.progress,
                open: t.open,
                resource: t.resource,
                owner: t.owner,
                constraint_type: t.constraint_type,
                constraint_date: t.constraint_date
            });
        });
        const links = gantt.getLinks().map(l => ({
            id: l.id, source: l.source, target: l.target, type: String(l.type), lag: l.lag || 0
        }));
        return { data, links, baselines, settings: scheduleSettings };
    }

    function loadSchedulePayload(payload) {
        if (!payload || !payload.data) return false;
        gantt.clearAll();
        gantt.parse({ data: payload.data, links: payload.links || [] });
        baselines = payload.baselines || [];
        if (payload.settings) scheduleSettings = Object.assign(scheduleSettings, payload.settings);
        applySettingsToUI();
        gantt.render();
        return true;
    }

    async function loadSchedule() {
        const projectId = getSelectedProjectId();
        currentProjectId = projectId;

        try {
            const res = await fetch(`/api/schedule?project_id=${projectId}`);
            if (res.ok) {
                const json = await res.json();
                if (json.payload && loadSchedulePayload(json.payload)) {
                    setSaveStatus('Loaded from server');
                    return;
                }
            }
        } catch (e) { /* fall through to local */ }

        const local = localStorage.getItem(`${STORAGE_KEY}_${projectId}`);
        if (local) {
            try {
                if (loadSchedulePayload(JSON.parse(local))) {
                    setSaveStatus('Loaded from browser');
                    return;
                }
            } catch (e) { /* ignore */ }
        }

        loadSchedulePayload(buildSampleSchedule());
        setSaveStatus('Sample schedule loaded');
        queueSave();
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
        if (dd) dd.value = scheduleSettings.data_date || '';
        if (la) la.value = scheduleSettings.lookahead_days || 14;
    }

    function setSaveStatus(msg) {
        const el = document.getElementById('scheduleSaveStatus');
        if (el) el.textContent = msg;
    }

    // ─── Toolbar actions ───
    function addActivity(type) {
        const parent = gantt.getSelectedId() || 0;
        const id = gantt.addTask({
            text: type === 'milestone' ? 'New Milestone' : 'New Activity',
            type: type || 'task',
            duration: type === 'milestone' ? 0 : 5,
            progress: 0,
            parent: parent
        }, parent);
        gantt.selectTask(id);
        gantt.showLightbox(id);
    }

    function deleteSelected() {
        const ids = gantt.getSelectedTasks ? gantt.getSelectedTasks() : [gantt.getSelectedId()];
        if (!ids || !ids.length) return showScheduleAlert('Select one or more activities first.', 'warning');
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
        const idx = gantt.getTaskIndex(parent) + 1;
        gantt.moveTask(id, idx, gp);
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
        const levels = ['day', 'week', 'month', 'quarter'];
        const cur = gantt.ext.zoom ? gantt.ext.zoom.getCurrentLevel() : 1;
        if (dir === 'in') gantt.ext.zoom && gantt.ext.zoom.setLevel(Math.max(0, cur - 1));
        else if (dir === 'out') gantt.ext.zoom && gantt.ext.zoom.setLevel(Math.min(3, cur + 1));
        else {
            gantt.config.scale_unit = dir === 'week' ? 'week' : dir === 'month' ? 'month' : 'day';
            gantt.render();
        }
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
        showScheduleAlert('CPM schedule calculated (forward/backward pass).', 'success');
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

        const items = CasePMSchedule.computeLookAhead(tasks, links, {
            dataDate,
            horizonWorkDays: horizon,
            minDuration: 3
        });
        const groups = CasePMSchedule.groupLookAheadByWbs(tasks, items);
        const container = document.getElementById('lookaheadContent');
        if (!container) return;

        if (!items.length) {
            container.innerHTML = '<p class="text-zinc-400 text-center py-12">No major activities in the look-ahead window.</p>';
            return;
        }

        let html = `<div class="mb-4 flex flex-wrap gap-4 text-sm text-zinc-400">
            <span><i class="fa-solid fa-calendar text-emerald-400"></i> Data Date: <b class="text-white">${CasePMSchedule.formatDate(dataDate)}</b></span>
            <span><i class="fa-solid fa-forward text-sky-400"></i> Horizon: <b class="text-white">${horizon} work days</b></span>
            <span><i class="fa-solid fa-list-check text-amber-400"></i> Activities: <b class="text-white">${items.length}</b></span>
        </div>`;

        groups.forEach((groupItems, wbsName) => {
            html += `<div class="mb-6">
                <h3 class="text-sm font-semibold text-emerald-400 uppercase tracking-wider mb-2">${wbsName}</h3>
                <div class="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
                <table class="w-full text-sm">
                <thead><tr class="border-b border-zinc-800 bg-zinc-950 text-zinc-400 text-xs uppercase">
                    <th class="text-left px-4 py-2">Priority</th>
                    <th class="text-left px-4 py-2">Activity</th>
                    <th class="text-left px-4 py-2">Start</th>
                    <th class="text-left px-4 py-2">Finish</th>
                    <th class="text-left px-4 py-2">Resource</th>
                    <th class="text-left px-4 py-2">Why included</th>
                    <th class="w-20"></th>
                </tr></thead><tbody class="divide-y divide-zinc-800">`;
            groupItems.forEach(item => {
                const priClass = item.priority === 'High' ? 'text-red-400' : item.priority === 'Medium' ? 'text-amber-400' : 'text-zinc-400';
                html += `<tr class="hover:bg-zinc-800/50">
                    <td class="px-4 py-2.5 font-medium ${priClass}">${item.priority}</td>
                    <td class="px-4 py-2.5 font-medium">${item.task.text}</td>
                    <td class="px-4 py-2.5 text-zinc-400">${item.start}</td>
                    <td class="px-4 py-2.5 text-zinc-400">${item.end || '—'}</td>
                    <td class="px-4 py-2.5">${item.task.resource || '—'}</td>
                    <td class="px-4 py-2.5 text-xs text-zinc-500">${item.reasons.join(' · ')}</td>
                    <td class="px-4 py-2.5">
                        <button class="text-xs text-sky-400 hover:text-sky-300" onclick="ScheduleApp.focusActivity(${item.task.id})">Gantt</button>
                    </td>
                </tr>`;
            });
            html += '</tbody></table></div></div>';
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
            const preds = (t.$target || []).map(lid => {
                const l = gantt.getLink(lid);
                const src = gantt.getTask(l.source);
                return `${src.text} (${LINK_LABELS[l.type]}${l.lag ? (l.lag > 0 ? '+' : '') + l.lag : ''})`;
            }).join('; ');
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-zinc-800/50 border-b border-zinc-800';
            tr.innerHTML = `
                <td class="px-3 py-2 font-mono text-xs">${gantt.getWBSCode(t)}</td>
                <td class="px-3 py-2 ${critical ? 'text-red-400 font-medium' : ''}">${t.text}</td>
                <td class="px-3 py-2 text-center">${t.duration}</td>
                <td class="px-3 py-2 text-sm">${gantt.templates.format_date(t.start_date)}</td>
                <td class="px-3 py-2 text-sm">${t.end_date ? gantt.templates.format_date(t.end_date) : '—'}</td>
                <td class="px-3 py-2 text-center">${Math.round((t.progress || 0) * 100)}%</td>
                <td class="px-3 py-2 text-xs text-zinc-400">${preds || '—'}</td>
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
        if (!el || !range.start_date) return;
        let critical = 0;
        gantt.eachTask(t => { if (t.type !== 'project' && gantt.isCriticalTask(t)) critical++; });
        el.innerHTML = `
            <span>Project Start: <b>${gantt.templates.format_date(range.start_date)}</b></span>
            <span>Project Finish: <b>${gantt.templates.format_date(range.end_date)}</b></span>
            <span>Activities: <b>${countTasks()}</b></span>
            <span>Critical: <b class="text-red-400">${critical}</b></span>`;
    }

    // ─── Import / Export / Print ───
    function exportJson() {
        const blob = new Blob([JSON.stringify(serializeSchedule(), null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `schedule_${CasePMSchedule.formatDate(new Date())}.json`;
        a.click();
    }

    function importJson(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                loadSchedulePayload(JSON.parse(e.target.result));
                queueSave();
                showScheduleAlert('Schedule imported successfully.', 'success');
            } catch (err) {
                showScheduleAlert('Invalid schedule file.', 'error');
            }
        };
        reader.readAsText(file);
    }

    function printGantt() {
        if (gantt.ext && gantt.ext.zoom) {
            gantt.ext.zoom.setLevel(2);
        }
        window.print();
    }

    function printLookAhead() {
        document.body.classList.add('printing-lookahead');
        window.print();
        setTimeout(() => document.body.classList.remove('printing-lookahead'), 500);
    }

    // ─── Dialogs ───
    function showScheduleAlert(message, type) {
        const colors = { success: 'emerald', warning: 'amber', error: 'red', info: 'sky' };
        const c = colors[type] || 'sky';
        const dlg = document.createElement('dialog');
        dlg.className = 'bg-zinc-900 border border-zinc-700 rounded-2xl p-0 w-full max-w-md shadow-2xl';
        dlg.innerHTML = `<div class="px-5 py-3 border-b border-zinc-700 text-${c}-400 font-semibold text-sm">${type || 'Notice'}</div>
            <div class="px-5 py-4 text-sm text-zinc-200">${message}</div>
            <div class="px-5 py-3 border-t border-zinc-700 flex justify-end">
                <button class="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm">OK</button>
            </div>`;
        document.body.appendChild(dlg);
        dlg.querySelector('button').onclick = () => { dlg.close(); dlg.remove(); };
        dlg.showModal();
    }

    // ─── Init ───
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
        document.getElementById('lookaheadDaysInput')?.addEventListener('change', renderLookAhead);

        console.log('%c[Case PM] Scheduling module ready.', 'color:#10b981;font-weight:bold');
    }

    window.ScheduleApp = {
        init,
        addActivity,
        deleteSelected,
        indentSelected,
        outdentSelected,
        linkSelected,
        unlinkSelected,
        zoomGantt,
        toggleCriticalPath,
        setBaseline,
        runSchedule,
        switchScheduleView,
        renderLookAhead,
        focusActivity,
        exportJson,
        importJson,
        printGantt,
        printLookAhead,
        saveSchedule,
        loadSchedule
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
