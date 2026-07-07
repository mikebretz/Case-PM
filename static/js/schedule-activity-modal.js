/**
 * Tabbed activity detail modal (MS Project / Primavera style)
 */
(function (global) {
    'use strict';

    let currentTaskId = null;
    let activeTab = 'general';

    function wbsFor(task) {
        if (window.ScheduleApp && typeof ScheduleApp.wbsCode === 'function') {
            return ScheduleApp.wbsCode(task);
        }
        if (typeof gantt.getWBSCode === 'function') {
            try { return gantt.getWBSCode(task); } catch (e) { /* community edition */ }
        }
        return String(task.activity_id || task.id);
    }

    function succTemplate(taskId) {
        const task = gantt.getTask(taskId);
        const links = task.$source || [];
        return links.map(lid => {
            const link = gantt.getLink(lid);
            const tgt = gantt.getTask(link.target);
            const code = wbsFor(tgt);
            const types = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' };
            const lag = link.lag ? (link.lag > 0 ? `+${link.lag}` : link.lag) : '';
            return `${code}${types[link.type] || 'FS'}${lag}`;
        }).join(', ');
    }

    function openActivityModal(taskId) {
        if (!gantt.isTaskExists(taskId)) return;
        currentTaskId = taskId;
        activeTab = 'general';
        const dlg = document.getElementById('scheduleActivityModal');
        if (!dlg) return;
        populateForm(taskId);
        switchModalTab('general');
        dlg.showModal();
    }

    function closeActivityModal() {
        document.getElementById('scheduleActivityModal')?.close();
        currentTaskId = null;
    }

    function switchModalTab(tab) {
        activeTab = tab;
        document.querySelectorAll('.sched-modal-tab').forEach(btn => {
            const on = btn.dataset.tab === tab;
            btn.classList.toggle('border-emerald-500', on);
            btn.classList.toggle('text-white', on);
            btn.classList.toggle('border-transparent', !on);
            btn.classList.toggle('text-zinc-400', !on);
        });
        document.querySelectorAll('.sched-modal-panel').forEach(p => {
            p.classList.toggle('hidden', p.dataset.panel !== tab);
        });
    }

    function val(id) {
        const el = document.getElementById(id);
        return el ? el.value : '';
    }

    function setVal(id, v) {
        const el = document.getElementById(id);
        if (el) el.value = v != null ? v : '';
    }

    function populateForm(taskId) {
        const t = gantt.getTask(taskId);
        setVal('sam_text', t.text || '');
        setVal('sam_activity_id', t.activity_id || '');
        setVal('sam_type', t.type || 'task');
        setVal('sam_duration', t.duration != null ? t.duration : '');
        setVal('sam_start', t.start_date ? gantt.templates.format_date(t.start_date) : '');
        setVal('sam_finish', t.end_date ? gantt.templates.format_date(t.end_date) : '');
        const pct = Math.round((t.progress || 0) <= 1 ? (t.progress || 0) * 100 : (t.progress || 0));
        setVal('sam_progress', pct);
        setVal('sam_predecessors', predString(taskId));
        setVal('sam_successors', succTemplate(taskId));
        setVal('sam_resource', t.resource || '');
        setVal('sam_owner', t.owner || '');
        setVal('sam_work_hours', t.work_hours || '');
        setVal('sam_cost', t.cost || '');
        setVal('sam_fixed_cost', t.fixed_cost || '');
        setVal('sam_constraint_type', t.constraint_type || 'asap');
        setVal('sam_constraint_date', t.constraint_date || '');
        setVal('sam_deadline', t.deadline || '');
        setVal('sam_priority', t.priority || '1000');
        setVal('sam_calendar', t.calendar || 'Standard');
        setVal('sam_activity_code', t.activity_code || '');
        setVal('sam_phase', t.phase || '');
        setVal('sam_discipline', t.discipline || '');
        setVal('sam_actual_start', t.actual_start || '');
        setVal('sam_actual_finish', t.actual_finish || '');
        setVal('sam_remaining', t.remaining_duration || '');
        setVal('sam_notes', t.notes || '');
        setVal('sam_hyperlink', t.hyperlink || '');
        setVal('sam_bar_color', t.bar_color || '#3b82f6');
        setVal('sam_free_float', t.free_float != null ? t.free_float : (t.$free != null ? t.$free : ''));
        setVal('sam_total_float', t.total_float != null ? t.total_float : (t.$slack != null ? t.$slack : ''));
        document.getElementById('sam_modal_title').textContent = t.text || 'Activity Detail';
        document.getElementById('sam_wbs_badge').textContent = wbsFor(t);
    }

    function predString(taskId) {
        const task = gantt.getTask(taskId);
        const links = task.$target || [];
        const types = { '0': 'FS', '1': 'SS', '2': 'FF', '3': 'SF' };
        return links.map(lid => {
            const link = gantt.getLink(lid);
            const src = gantt.getTask(link.source);
            const code = wbsFor(src);
            const lag = link.lag ? (link.lag > 0 ? `+${link.lag}` : link.lag) : '';
            return `${code}${types[link.type] || 'FS'}${lag}`;
        }).join(', ');
    }

    function applyPredecessorString(taskId, predStr) {
        const existing = [...(gantt.getTask(taskId).$target || [])];
        existing.forEach(lid => gantt.deleteLink(lid));
        if (!predStr || !predStr.trim()) return;
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
                const wbs = wbsFor(t);
                if (wbs === code || String(t.id) === code || String(t.activity_id) === code) sourceId = t.id;
            });
            if (sourceId && sourceId !== taskId) {
                gantt.addLink({ source: sourceId, target: taskId, type, lag });
            }
        });
    }

    function toModalDate(value) {
        if (!value) return null;
        if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
        if (typeof CasePMSchedule !== 'undefined') {
            const d = CasePMSchedule.parseDate(value);
            if (d) return d;
        }
        if (gantt.date && gantt.date.str_to_date) {
            const d = gantt.date.str_to_date(value);
            if (d && !Number.isNaN(d.getTime())) return d;
        }
        return null;
    }

    function saveActivityModal() {
        if (!currentTaskId || !gantt.isTaskExists(currentTaskId)) return;
        const t = gantt.getTask(currentTaskId);
        t.text = val('sam_text');
        t.activity_id = val('sam_activity_id');
        t.type = val('sam_type');
        t.duration = parseFloat(val('sam_duration')) || 0;
        const start = val('sam_start');
        if (start) t.start_date = toModalDate(start);
        const finish = val('sam_finish');
        if (finish) t.end_date = toModalDate(finish);
        t.progress = Math.min(1, parseInt(val('sam_progress'), 10) / 100 || 0);
        t.resource = val('sam_resource');
        t.owner = val('sam_owner');
        t.work_hours = val('sam_work_hours');
        t.cost = val('sam_cost');
        t.fixed_cost = val('sam_fixed_cost');
        t.constraint_type = val('sam_constraint_type');
        t.constraint_date = val('sam_constraint_date') || null;
        t.deadline = val('sam_deadline') || null;
        t.priority = val('sam_priority');
        t.calendar = val('sam_calendar');
        t.activity_code = val('sam_activity_code');
        t.phase = val('sam_phase');
        t.discipline = val('sam_discipline');
        t.actual_start = val('sam_actual_start') || null;
        t.actual_finish = val('sam_actual_finish') || null;
        t.remaining_duration = val('sam_remaining');
        t.notes = val('sam_notes');
        t.hyperlink = val('sam_hyperlink');
        t.bar_color = val('sam_bar_color');
        gantt.updateTask(currentTaskId);
        if (window.ScheduleApp && ScheduleApp.applyPredecessorString) {
            ScheduleApp.applyPredecessorString(currentTaskId, val('sam_predecessors'));
        } else {
            applyPredecessorString(currentTaskId, val('sam_predecessors'));
        }
        if (window.ScheduleApp && ScheduleApp.runSchedule) ScheduleApp.runSchedule();
        else gantt.render();
        if (window.CasePMActivityLog) {
            CasePMActivityLog.log('Updated activity', t.text, 'schedule');
        }
        if (window.ScheduleApp && ScheduleApp.queueSave) ScheduleApp.queueSave();
        else if (window.ScheduleApp && ScheduleApp.saveSchedule) ScheduleApp.saveSchedule();
        closeActivityModal();
    }

    function deleteFromModal() {
        if (!currentTaskId) return;
        if (!confirm('Delete this activity?')) return;
        const name = gantt.getTask(currentTaskId).text;
        gantt.deleteTask(currentTaskId);
        if (window.CasePMActivityLog) CasePMActivityLog.log('Deleted activity', name, 'schedule');
        closeActivityModal();
    }

    global.ScheduleActivityModal = {
        open: openActivityModal,
        close: closeActivityModal,
        switchTab: switchModalTab,
        save: saveActivityModal,
        delete: deleteFromModal
    };
})(typeof window !== 'undefined' ? window : global);
