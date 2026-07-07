/**
 * Case PM — Import MS Project XML & Primavera P6 XER into dhtmlx-gantt format
 */
(function (global) {
    'use strict';

    const MS_LINK_TO_GANTT = { '0': '2', '1': '0', '2': '3', '3': '1' }; // FF,FS,SF,SS
    const P6_LINK_TO_GANTT = { PR_FS: '0', PR_SS: '1', PR_FF: '2', PR_SF: '3', FS: '0', SS: '1', FF: '2', SF: '3' };

    function parseXer(content) {
        const tables = {};
        const lines = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
        let currentTable = null;
        let fields = [];

        lines.forEach(line => {
            if (!line.trim()) return;
            if (line.startsWith('%T\t')) {
                currentTable = line.substring(3).trim();
                tables[currentTable] = { fields: [], rows: [] };
                fields = [];
                return;
            }
            if (line.startsWith('%F\t') && currentTable) {
                fields = line.substring(3).split('\t');
                tables[currentTable].fields = fields;
                return;
            }
            if (line.startsWith('%R\t') && currentTable && fields.length) {
                const vals = line.substring(3).split('\t');
                const row = {};
                fields.forEach((f, i) => { row[f] = vals[i] !== undefined ? vals[i] : ''; });
                tables[currentTable].rows.push(row);
            }
        });

        const wbsRows = (tables.PROJWBS || tables.WBS || {}).rows || [];
        const taskRows = (tables.TASK || {}).rows || [];
        const predRows = (tables.TASKPRED || {}).rows || [];

        if (!taskRows.length) throw new Error('No TASK records found in XER file.');

        const wbsMap = new Map();
        wbsRows.forEach(w => {
            const id = w.wbs_id || w.proj_node_flag;
            if (id) wbsMap.set(String(id), w);
        });

        const data = [];
        const idMap = new Map(); // task_id -> gantt id
        let ganttId = 1;

        // WBS summary nodes first
        const wbsGanttId = new Map();
        wbsRows.sort((a, b) => (parseInt(a.seq_num, 10) || 0) - (parseInt(b.seq_num, 10) || 0));
        wbsRows.forEach(w => {
            const wbsId = w.wbs_id;
            if (!wbsId) return;
            const parentWbs = w.parent_wbs_id && w.parent_wbs_id !== w.wbs_id ? w.parent_wbs_id : null;
            const gid = ganttId++;
            wbsGanttId.set(String(wbsId), gid);
            const parentGid = parentWbs && wbsGanttId.has(String(parentWbs)) ? wbsGanttId.get(String(parentWbs)) : 0;
            data.push({
                id: gid,
                text: w.wbs_name || w.wbs_short_name || `WBS ${wbsId}`,
                type: 'project',
                parent: parentGid,
                open: true,
                duration: 1,
                progress: 0
            });
        });

        taskRows.forEach(t => {
            const tid = t.task_id;
            if (!tid) return;
            const gid = ganttId++;
            idMap.set(String(tid), gid);

            const wbsId = t.wbs_id;
            let parent = 0;
            if (wbsId && wbsGanttId.has(String(wbsId))) parent = wbsGanttId.get(String(wbsId));

            const durHours = parseFloat(t.target_drtn_hr_cnt || t.remain_drtn_hr_cnt || t.act_drtn_hr_cnt || '8');
            const duration = Math.max(0, Math.round(durHours / 8));
            const start = parseP6Date(t.target_start_date || t.act_start_date || t.early_start_date || t.restart_date);
            const end = parseP6Date(t.target_end_date || t.act_end_date || t.early_end_date || t.reend_date);
            const isMilestone = (t.task_type || '').includes('Mile') || duration === 0;

            const row = {
                id: gid,
                text: t.task_name || t.task_code || `Activity ${tid}`,
                parent,
                type: isMilestone ? 'milestone' : 'task',
                duration: isMilestone ? 0 : Math.max(1, duration),
                progress: parseP6Progress(t.phys_complete_pct || t.complete_pct),
                resource: t.rsrc_id || '',
                owner: t.task_code || ''
            };
            if (start) row.start_date = start;
            if (end && !start) row.end_date = end;
            data.push(row);
        });

        const links = [];
        let linkId = 1;
        predRows.forEach(p => {
            const target = idMap.get(String(p.task_id));
            const source = idMap.get(String(p.pred_task_id));
            if (!target || !source) return;
            const type = P6_LINK_TO_GANTT[p.pred_type] || '0';
            const lagHours = parseFloat(p.lag_hr_cnt || '0');
            links.push({
                id: linkId++,
                source,
                target,
                type,
                lag: Math.round(lagHours / 8)
            });
        });

        return { data, links, source: 'Primavera XER' };
    }

    function parseP6Date(val) {
        if (!val || val === '') return null;
        const s = String(val).trim();
        if (s.length >= 10) return s.substring(0, 10);
        return null;
    }

    function parseP6Progress(val) {
        const n = parseFloat(val);
        if (Number.isNaN(n)) return 0;
        return n > 1 ? n / 100 : n;
    }

    function parseMsProjectXml(content) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(content, 'text/xml');
        if (doc.querySelector('parsererror')) throw new Error('Invalid XML file.');

        const tasks = [...doc.getElementsByTagName('Task')].filter(t => {
            const uid = textOf(t, 'UID');
            return uid && uid !== '0';
        });

        if (!tasks.length) throw new Error('No tasks found in MS Project XML.');

        const data = [];
        const uidMap = new Map();
        const links = [];
        let linkId = 1;

        tasks.forEach((t, idx) => {
            const uid = textOf(t, 'UID');
            const gid = idx + 1;
            uidMap.set(uid, gid);

            const summary = textOf(t, 'Summary') === '1';
            const milestone = textOf(t, 'Milestone') === '1';
            const outline = parseInt(textOf(t, 'OutlineLevel') || '1', 10);
            const name = textOf(t, 'Name') || `Task ${uid}`;
            const start = parseMsDate(textOf(t, 'Start'));
            const finish = parseMsDate(textOf(t, 'Finish'));
            const dur = parseMsDuration(textOf(t, 'Duration'));
            const pct = parseInt(textOf(t, 'PercentComplete') || '0', 10);

            const row = {
                id: gid,
                text: name,
                parent: 0,
                type: summary ? 'project' : (milestone ? 'milestone' : 'task'),
                progress: pct / 100,
                open: true
            };
            if (start) row.start_date = start;
            if (dur != null) row.duration = milestone ? 0 : Math.max(1, dur);
            else if (start && finish) row.duration = Math.max(1, workDaysBetween(start, finish));

            row._outline = outline;
            data.push(row);

            [...t.getElementsByTagName('PredecessorLink')].forEach(pl => {
                const predUid = textOf(pl, 'PredecessorUID');
                const msType = textOf(pl, 'Type') || '1';
                const lag = parseInt(textOf(pl, 'LinkLag') || '0', 10);
                const source = uidMap.get(predUid);
                if (source) {
                    links.push({
                        id: linkId++,
                        source,
                        target: gid,
                        type: MS_LINK_TO_GANTT[msType] || '0',
                        lag: Math.round(lag / 4800) // MS stores lag in tenths of minutes? often 4800 = 1 day
                    });
                }
            });
        });

        // Build hierarchy from outline levels
        const stack = [{ id: 0, level: 0 }];
        data.forEach(task => {
            const level = task._outline || 1;
            while (stack.length > 1 && stack[stack.length - 1].level >= level) stack.pop();
            task.parent = stack[stack.length - 1].id;
            delete task._outline;
            if (task.type === 'project') stack.push({ id: task.id, level });
        });

        return { data, links, source: 'MS Project XML' };
    }

    function textOf(el, tag) {
        const n = el.getElementsByTagName(tag)[0];
        return n ? (n.textContent || '').trim() : '';
    }

    function parseMsDate(val) {
        if (!val) return null;
        const d = new Date(val);
        if (Number.isNaN(d.getTime())) return null;
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    function parseMsDuration(val) {
        if (!val) return null;
        const m = String(val).match(/PT(\d+)H/);
        if (m) return Math.max(1, Math.round(parseInt(m[1], 10) / 8));
        const m2 = String(val).match(/P(\d+)D/);
        if (m2) return parseInt(m2[1], 10);
        return null;
    }

    function workDaysBetween(startStr, endStr) {
        const s = new Date(startStr);
        const e = new Date(endStr);
        let n = 0;
        const c = new Date(s);
        while (c <= e) {
            const d = c.getDay();
            if (d !== 0 && d !== 6) n++;
            c.setDate(c.getDate() + 1);
        }
        return n;
    }

    function detectAndParse(filename, content) {
        const lower = (filename || '').toLowerCase();
        if (lower.endsWith('.xer') || content.trimStart().startsWith('%T')) {
            return parseXer(content);
        }
        if (lower.endsWith('.xml') || content.trimStart().startsWith('<?xml') || content.includes('<Project')) {
            return parseMsProjectXml(content);
        }
        if (lower.endsWith('.json')) {
            const j = JSON.parse(content);
            if (j.data) return j;
            throw new Error('JSON must contain a data array.');
        }
        throw new Error('Unsupported format. Use .xer (Primavera), .xml (MS Project export), or .json.');
    }

    global.CasePMScheduleImport = { detectAndParse, parseXer, parseMsProjectXml };
})(typeof window !== 'undefined' ? window : global);
