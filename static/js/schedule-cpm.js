/**
 * Case PM — Construction CPM utilities & intelligent look-ahead filtering
 * Complements dhtmlx-gantt auto-scheduling / critical-path plugins.
 */
(function (global) {
    'use strict';

    const MS_DAY = 86400000;

    function parseDate(value) {
        if (!value) return null;
        if (value instanceof Date) return new Date(value.getTime());
        const d = new Date(value);
        return Number.isNaN(d.getTime()) ? null : d;
    }

    function formatDate(d) {
        if (!d) return '';
        const dt = parseDate(d);
        if (!dt) return '';
        const y = dt.getFullYear();
        const m = String(dt.getMonth() + 1).padStart(2, '0');
        const day = String(dt.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    function isWorkDay(d) {
        const day = d.getDay();
        return day !== 0 && day !== 6;
    }

    function addWorkDays(start, days) {
        const d = parseDate(start);
        if (!d) return null;
        let remaining = Math.round(Number(days) || 0);
        if (remaining === 0) return new Date(d.getTime());
        const step = remaining > 0 ? 1 : -1;
        remaining = Math.abs(remaining);
        while (remaining > 0) {
            d.setDate(d.getDate() + step);
            if (isWorkDay(d)) remaining--;
        }
        return new Date(d.getTime());
    }

    function workDaysBetween(start, end) {
        const s = parseDate(start);
        const e = parseDate(end);
        if (!s || !e) return 0;
        let count = 0;
        const cur = new Date(s.getTime());
        const forward = e >= s;
        while ((forward && cur <= e) || (!forward && cur >= e)) {
            if (isWorkDay(cur)) count++;
            cur.setDate(cur.getDate() + (forward ? 1 : -1));
        }
        return forward ? count : -count;
    }

    function taskEndDate(task) {
        if (task.end_date) return parseDate(task.end_date);
        if (task.start_date && task.duration != null) {
            const d = parseDate(task.start_date);
            if (!d) return null;
            if (task.type === 'milestone') return new Date(d.getTime());
            return addWorkDays(d, Math.max(0, Number(task.duration) - 1));
        }
        return null;
    }

    function taskStartDate(task) {
        return parseDate(task.start_date);
    }

    function isSummary(task) {
        return task.type === 'project' || task.$has_child;
    }

    function addCalendarDays(start, days) {
        const d = parseDate(start);
        if (!d) return null;
        const out = new Date(d.getTime());
        out.setDate(out.getDate() + Math.round(Number(days) || 0));
        return out;
    }

    function calendarDaysBetween(start, end) {
        const s = parseDate(start);
        const e = parseDate(end);
        if (!s || !e) return 0;
        return Math.round((e.getTime() - s.getTime()) / MS_DAY);
    }

    function calcFinishFromStart(start, duration, type) {
        const s = parseDate(start);
        if (!s) return null;
        const dur = Math.max(0, Number(duration) || 0);
        if (type === 'milestone' || dur === 0) return new Date(s.getTime());
        return addCalendarDays(s, dur);
    }

    function buildWbsMap(tasks) {
        const map = new Map();
        const byParent = new Map();
        (tasks || []).forEach(t => {
            const p = String(t.parent || 0);
            if (!byParent.has(p)) byParent.set(p, []);
            byParent.get(p).push(t);
        });
        byParent.forEach(list => list.sort((a, b) => (a.$index || 0) - (b.$index || 0) || String(a.id).localeCompare(String(b.id))));

        function walk(parentId, prefix) {
            const kids = byParent.get(String(parentId)) || [];
            kids.forEach((t, i) => {
                const code = prefix ? `${prefix}.${i + 1}` : String(i + 1);
                map.set(String(t.id), code);
                walk(t.id, code);
            });
        }
        walk(0, '');
        walk('0', '');
        return map;
    }

    function isTaskCritical(task) {
        if (!task || task.type === 'project') return false;
        if (task.$critical || task.critical) return true;
        const slack = task.$slack != null ? task.$slack : task.total_float;
        return slack != null && slack <= 0;
    }

    const CONSTRAINT_TYPES = {
        asap: 'asap', alap: 'alap', mso: 'mso', mfo: 'mfo',
        snet: 'snet', snlt: 'snlt', fnet: 'fnet', fnlt: 'fnlt'
    };

    function normalizeConstraintType(value) {
        const v = String(value || 'asap').toLowerCase();
        return CONSTRAINT_TYPES[v] ? v : 'asap';
    }

    function applyForwardConstraint(task, es, ef, esMap, efMap) {
        const type = normalizeConstraintType(task.constraint_type);
        const cDate = parseDate(task.constraint_date);
        if (!cDate || type === 'asap' || type === 'alap') return;
        const dur = Math.max(0, Number(task.duration) || 0);
        const id = String(task.id);
        let start = esMap.get(id);
        let finish = efMap.get(id);
        if (type === 'mso') {
            start = cDate;
            finish = task.type === 'milestone' ? cDate : calcFinishFromStart(cDate, dur, task.type);
        } else if (type === 'mfo') {
            finish = cDate;
            start = task.type === 'milestone' ? cDate : addCalendarDays(cDate, -dur);
        } else if (type === 'snet' && start < cDate) {
            start = cDate;
            finish = task.type === 'milestone' ? cDate : calcFinishFromStart(cDate, dur, task.type);
        } else if (type === 'fnet' && finish < cDate) {
            finish = cDate;
            start = task.type === 'milestone' ? cDate : addCalendarDays(cDate, -dur);
        }
        esMap.set(id, start);
        efMap.set(id, finish);
    }

    function applyBackwardConstraint(task, ls, lf, lsMap, lfMap) {
        const type = normalizeConstraintType(task.constraint_type);
        const cDate = parseDate(task.constraint_date);
        if (!cDate) return;
        const dur = Math.max(0, Number(task.duration) || 0);
        const id = String(task.id);
        let lateStart = lsMap.get(id);
        let lateFinish = lfMap.get(id);
        if (type === 'snlt' && lateStart > cDate) {
            lateStart = cDate;
            lateFinish = task.type === 'milestone' ? cDate : calcFinishFromStart(cDate, dur, task.type);
        } else if (type === 'fnlt' && lateFinish > cDate) {
            lateFinish = cDate;
            lateStart = task.type === 'milestone' ? cDate : addCalendarDays(cDate, -dur);
        }
        lsMap.set(id, lateStart);
        lfMap.set(id, lateFinish);
    }

    /**
     * Simplified EVM metrics per activity (MS Project / P6 style).
     */
    function computeEVM(task, dataDate) {
        const dd = parseDate(dataDate) || new Date();
        const cost = Number(task.cost) || Number(task.budgeted_cost) || 0;
        const actualCost = Number(task.actual_cost) || 0;
        const progress = task.progress <= 1 ? (Number(task.progress) || 0) : (Number(task.progress) || 0) / 100;
        const start = taskStartDate(task);
        const end = taskEndDate(task);
        const duration = Math.max(1, Number(task.duration) || 1);

        let bcws = 0;
        if (start && end && cost > 0) {
            const totalSpan = Math.max(1, calendarDaysBetween(start, end));
            const elapsed = Math.max(0, Math.min(totalSpan, calendarDaysBetween(start, dd)));
            bcws = cost * (elapsed / totalSpan);
        }

        const bcwp = cost * progress;
        const acwp = actualCost > 0 ? actualCost : bcwp;
        const cpi = acwp > 0 ? bcwp / acwp : null;
        const spi = bcws > 0 ? bcwp / bcws : null;
        const costVariance = bcwp - acwp;
        const scheduleVariance = bcwp - bcws;

        const schedPct = duration > 0 ? Math.min(100, Math.round((progress * duration / duration) * 100)) : Math.round(progress * 100);

        return {
            bcws: Math.round(bcws * 100) / 100,
            bcwp: Math.round(bcwp * 100) / 100,
            acwp: Math.round(acwp * 100) / 100,
            cpi: cpi != null ? Math.round(cpi * 1000) / 1000 : null,
            spi: spi != null ? Math.round(spi * 1000) / 1000 : null,
            cost_variance: Math.round(costVariance * 100) / 100,
            schedule_variance: Math.round(scheduleVariance * 100) / 100,
            schedule_percent_complete: schedPct
        };
    }

    /**
     * CPM forward/backward pass (community-edition fallback — no dhtmlx PRO plugins).
     * Updates activity dates from logic links and marks critical path (total float <= 0).
     */
    function runCPM(tasks, links, options) {
        const opts = options || {};
        const taskMap = new Map();
        (tasks || []).forEach(t => taskMap.set(String(t.id), Object.assign({}, t)));

        const childIds = new Map();
        taskMap.forEach((t, id) => {
            const p = String(t.parent || 0);
            if (!childIds.has(p)) childIds.set(p, []);
            childIds.get(p).push(id);
        });
        const isLeaf = id => !(childIds.get(String(id)) || []).length;

        const { preds, succs } = buildAdjacency(links || []);
        const leaves = [...taskMap.keys()].filter(id => {
            const t = taskMap.get(id);
            if (!isLeaf(id) || t.type === 'project') return false;
            const at = String(t.activity_type || '').toLowerCase();
            if (at === 'loe' || at === 'level of effort') return false;
            return true;
        });
        const today = parseDate(new Date()) || new Date();

        const es = new Map();
        const ef = new Map();
        const ls = new Map();
        const lf = new Map();

        leaves.forEach(id => {
            const t = taskMap.get(id);
            const start = parseDate(t.start_date) || today;
            const end = parseDate(t.end_date) || calcFinishFromStart(start, t.duration, t.type);
            es.set(id, start);
            ef.set(id, end);
        });

        const linkType = link => String(link.type ?? '0');
        const lagOf = link => Number(link.lag) || 0;

        function pushForward(succId, candidateStart) {
            const t = taskMap.get(succId);
            const dur = Math.max(0, Number(t.duration) || 0);
            const cand = parseDate(candidateStart);
            if (!cand) return;
            const cur = es.get(succId);
            if (!cur || cand > cur) {
                es.set(succId, cand);
                ef.set(succId, calcFinishFromStart(cand, dur, t.type));
            }
        }

        for (let pass = 0; pass < Math.max(1, leaves.length * 3); pass++) {
            let changed = false;
            leaves.forEach(succId => {
                (preds.get(succId) || preds.get(Number(succId)) || []).forEach(link => {
                    const predId = String(link.source);
                    if (!es.has(predId)) return;
                    const type = linkType(link);
                    const lag = lagOf(link);
                    const pes = es.get(predId);
                    const pef = ef.get(predId);
                    const before = es.get(succId)?.getTime();
                    if (type === '1') pushForward(succId, addCalendarDays(pes, lag));
                    else if (type === '2') {
                        const t = taskMap.get(succId);
                        const dur = Math.max(0, Number(t.duration) || 0);
                        const needEnd = addCalendarDays(pef, lag);
                        pushForward(succId, t.type === 'milestone' ? needEnd : addCalendarDays(needEnd, -dur));
                    } else if (type === '3') {
                        const t = taskMap.get(succId);
                        const dur = Math.max(0, Number(t.duration) || 0);
                        const needEnd = addCalendarDays(pes, lag);
                        pushForward(succId, t.type === 'milestone' ? needEnd : addCalendarDays(needEnd, -dur));
                    } else pushForward(succId, addCalendarDays(pef, lag));
                    if (es.get(succId)?.getTime() !== before) changed = true;
                });
            });
            if (!changed) break;
        }

        // Apply forward constraints (MSO, MFO, SNET, FNET)
        leaves.forEach(id => {
            const t = taskMap.get(id);
            applyForwardConstraint(t, es.get(id), ef.get(id), es, ef);
        });

        let projectEnd = today;
        leaves.forEach(id => {
            const e = ef.get(id);
            if (e && e > projectEnd) projectEnd = e;
        });

        leaves.forEach(id => {
            const t = taskMap.get(id);
            const dur = Math.max(0, Number(t.duration) || 0);
            lf.set(id, projectEnd);
            ls.set(id, t.type === 'milestone' ? projectEnd : addCalendarDays(projectEnd, -dur));
        });

        for (let pass = 0; pass < Math.max(1, leaves.length * 3); pass++) {
            let changed = false;
            [...leaves].reverse().forEach(predId => {
                const pt = taskMap.get(predId);
                const pdur = Math.max(0, Number(pt.duration) || 0);
                (succs.get(predId) || succs.get(Number(predId)) || []).forEach(link => {
                    const succId = String(link.target);
                    if (!ls.has(succId)) return;
                    const type = linkType(link);
                    const lag = lagOf(link);
                    let candLf = lf.get(predId);
                    if (type === '1') candLf = addCalendarDays(ls.get(succId), -lag);
                    else if (type === '2') candLf = addCalendarDays(lf.get(succId), -lag);
                    else if (type === '3') candLf = addCalendarDays(ls.get(succId), -lag);
                    else candLf = addCalendarDays(ls.get(succId), -lag);
                    const candLs = pt.type === 'milestone' ? candLf : addCalendarDays(candLf, -pdur);
                    if (candLs < ls.get(predId)) {
                        ls.set(predId, candLs);
                        lf.set(predId, candLf);
                        changed = true;
                    }
                });
            });
            if (!changed) break;
        }

        // Apply backward constraints (SNLT, FNLT)
        leaves.forEach(id => {
            const t = taskMap.get(id);
            applyBackwardConstraint(t, ls.get(id), lf.get(id), ls, lf);
        });

        const dataDate = parseDate(opts.dataDate) || today;

        const updates = new Map();
        leaves.forEach(id => {
            const t = taskMap.get(id);
            const totalFloat = Math.max(0, calendarDaysBetween(es.get(id), ls.get(id)));
            const critical = totalFloat <= 0;
            const constraint = normalizeConstraintType(t.constraint_type);
            let schedStart = es.get(id);
            let schedEnd = ef.get(id);
            if (constraint === 'alap') {
                schedStart = ls.get(id);
                schedEnd = lf.get(id);
            }
            const evm = computeEVM(Object.assign({}, t, {
                start_date: schedStart,
                end_date: schedEnd
            }), dataDate);
            updates.set(id, {
                start_date: schedStart,
                end_date: schedEnd,
                early_start: es.get(id),
                early_finish: ef.get(id),
                late_start: ls.get(id),
                late_finish: lf.get(id),
                total_float: totalFloat,
                free_float: totalFloat,
                $slack: totalFloat,
                $critical: critical,
                ...evm
            });
        });

        // Roll summary dates from children
        function rollup(parentId) {
            const kids = childIds.get(String(parentId)) || [];
            if (!kids.length) return;
            kids.forEach(rollup);
            if (!taskMap.has(String(parentId))) return;
            let minS = null;
            let maxE = null;
            kids.forEach(cid => {
                const u = updates.get(cid);
                const t = taskMap.get(cid);
                const s = u?.start_date || parseDate(t.start_date);
                const e = u?.end_date || parseDate(t.end_date);
                if (s && (!minS || s < minS)) minS = s;
                if (e && (!maxE || e > maxE)) maxE = e;
            });
            if (minS) {
                updates.set(String(parentId), {
                    start_date: minS,
                    end_date: maxE || minS,
                    total_float: null,
                    free_float: null,
                    $slack: null,
                    $critical: false
                });
            }
        }
        ['0', 0].forEach(r => rollup(r));
        childIds.forEach((_, pid) => rollup(pid));

        return { updates, wbsMap: buildWbsMap(tasks) };
    }

    function buildAdjacency(links) {
        const preds = new Map();
        const succs = new Map();
        (links || []).forEach(link => {
            const src = String(link.source);
            const tgt = String(link.target);
            if (!preds.has(tgt)) preds.set(tgt, []);
            if (!succs.has(src)) succs.set(src, []);
            preds.get(tgt).push(link);
            succs.get(src).push(link);
        });
        return { preds, succs };
    }

    /**
     * Intelligent construction look-ahead.
     * Returns scored activities — not everything, only what matters in the window.
     */
    function computeLookAhead(tasks, links, options) {
        const opts = Object.assign({
            dataDate: new Date(),
            horizonWorkDays: 14,
            minDuration: 3,
            includeCriticalBeyond: true,
            criticalBufferDays: 7,
            maxResults: 80
        }, options || {});

        const dataDate = parseDate(opts.dataDate) || new Date();
        const horizonEnd = addWorkDays(dataDate, opts.horizonWorkDays);
        const criticalEnd = addWorkDays(dataDate, opts.horizonWorkDays + opts.criticalBufferDays);
        const taskMap = new Map((tasks || []).map(t => [String(t.id), t]));
        const { preds, succs } = buildAdjacency(links || []);
        const results = [];

        (tasks || []).forEach(task => {
            if (isSummary(task)) return;
            const progress = Number(task.progress) || 0;
            if (progress >= 1) return;

            const start = taskStartDate(task);
            const end = taskEndDate(task);
            if (!start) return;

            const progressPct = progress <= 1 ? progress * 100 : progress;
            const inProgress = progressPct > 0 && progressPct < 100;
            const inWindow = start <= horizonEnd && (!end || end >= dataDate);
            const finishingSoon = end && end >= dataDate && end <= horizonEnd;
            const isCritical = !!task.$critical || !!task.critical;
            const isMilestone = task.type === 'milestone';
            const duration = Number(task.duration) || 0;
            const isMajor = duration >= opts.minDuration || isMilestone;
            const hasResource = !!(task.resource || task.owner);

            let score = 0;
            const reasons = [];

            if (isCritical && start <= criticalEnd) {
                score += 120;
                reasons.push('Critical path');
            }
            if (inProgress) {
                score += 90;
                reasons.push('In progress');
            }
            if (inWindow) {
                score += 70;
                reasons.push(`Within ${opts.horizonWorkDays}-day window`);
            }
            if (finishingSoon) {
                score += 50;
                reasons.push('Finishing in window');
            }
            if (isMilestone) {
                score += 45;
                reasons.push('Milestone');
            }
            if (isMajor) {
                score += 30;
                reasons.push('Major activity');
            }
            if (hasResource) {
                score += 20;
                reasons.push('Resource assigned');
            }

            // Near-critical: feeds a critical activity in the window
            const succLinks = succs.get(task.id) || [];
            succLinks.forEach(link => {
                const succ = taskMap.get(String(link.target));
                if (succ && (succ.$critical || succ.critical)) {
                    const sStart = taskStartDate(succ);
                    if (sStart && sStart <= horizonEnd) {
                        score += 35;
                        reasons.push('Drives critical successor');
                    }
                }
            });

            const predLinks = preds.get(task.id) || [];
            predLinks.forEach(link => {
                const pred = taskMap.get(String(link.source));
                if (pred && (pred.$critical || pred.critical) && inProgress) {
                    score += 25;
                    reasons.push('Successor to critical work');
                }
            });

            // Constraint / late starts
            if (task.constraint_type && task.constraint_type !== 'asap') {
                score += 15;
                reasons.push('Has constraint');
            }

            const floatVal = task.$free != null ? task.$free : task.free_float;
            if (floatVal != null && floatVal <= 2 && floatVal >= 0) {
                score += 25;
                reasons.push('Near-zero float');
            }

            if (score < 40 && !inWindow && !inProgress) return;

            results.push({
                task,
                score,
                reasons: [...new Set(reasons)],
                start: formatDate(start),
                end: formatDate(end),
                priority: score >= 100 ? 'High' : score >= 60 ? 'Medium' : 'Normal'
            });
        });

        results.sort((a, b) => {
            if (b.score !== a.score) return b.score - a.score;
            return (a.start || '').localeCompare(b.start || '');
        });

        return results.slice(0, opts.maxResults);
    }

    function groupLookAheadByWbs(tasks, lookAheadItems) {
        const wbsMap = new Map();
        tasks.forEach(t => {
            if (t.type === 'project' || t.$has_child) {
                wbsMap.set(String(t.id), t.text || t.wbs || `WBS ${t.id}`);
            }
        });
        const groups = new Map();
        lookAheadItems.forEach(item => {
            const parentId = String(item.task.parent || '0');
            const label = wbsMap.get(parentId) || 'Ungrouped Activities';
            if (!groups.has(label)) groups.set(label, []);
            groups.get(label).push(item);
        });
        return groups;
    }

    /** Project-level EVM rollup (BAC, BCWS, BCWP, ACWP, CPI, SPI, EAC, VAC). */
    function computeProjectEVM(tasks, dataDate) {
        const dd = parseDate(dataDate) || new Date();
        let bac = 0, bcws = 0, bcwp = 0, acwp = 0;
        (tasks || []).forEach(t => {
            if (!t || t.type === 'project') return;
            const cost = Number(t.cost) || Number(t.budgeted_cost) || 0;
            if (cost <= 0) return;
            const evm = computeEVM(t, dd);
            bac += cost;
            bcws += evm.bcws || 0;
            bcwp += evm.bcwp || 0;
            acwp += evm.acwp || 0;
        });
        const cpi = acwp > 0 ? bcwp / acwp : null;
        const spi = bcws > 0 ? bcwp / bcws : null;
        const eac = cpi && cpi > 0 ? bac / cpi : bac;
        const vac = bac - eac;
        return {
            bac: Math.round(bac * 100) / 100,
            bcws: Math.round(bcws * 100) / 100,
            bcwp: Math.round(bcwp * 100) / 100,
            acwp: Math.round(acwp * 100) / 100,
            cpi: cpi != null ? Math.round(cpi * 1000) / 1000 : null,
            spi: spi != null ? Math.round(spi * 1000) / 1000 : null,
            eac: Math.round(eac * 100) / 100,
            vac: Math.round(vac * 100) / 100,
            cv: Math.round((bcwp - acwp) * 100) / 100,
            sv: Math.round((bcwp - bcws) * 100) / 100
        };
    }

    /** Detect resource overallocation windows (same resource on overlapping tasks). */
    function detectResourceConflicts(tasks) {
        const byResource = new Map();
        (tasks || []).forEach(t => {
            if (!t || t.type === 'project' || t.type === 'milestone') return;
            const res = String(t.resource || '').trim();
            if (!res) return;
            const start = taskStartDate(t);
            const end = taskEndDate(t);
            if (!start || !end) return;
            res.split(/[,;]+/).map(s => s.trim()).filter(Boolean).forEach(r => {
                if (!byResource.has(r)) byResource.set(r, []);
                byResource.get(r).push({ id: t.id, text: t.text, start, end, duration: t.duration });
            });
        });
        const conflicts = [];
        byResource.forEach((list, resource) => {
            const sorted = list.slice().sort((a, b) => a.start - b.start);
            for (let i = 0; i < sorted.length; i++) {
                for (let j = i + 1; j < sorted.length; j++) {
                    const a = sorted[i];
                    const b = sorted[j];
                    if (b.start >= a.end) break;
                    conflicts.push({
                        resource,
                        taskA: a.id,
                        taskB: b.id,
                        textA: a.text,
                        textB: b.text,
                        overlapStart: b.start > a.start ? b.start : a.start,
                        overlapEnd: a.end < b.end ? a.end : b.end
                    });
                }
            }
        });
        return conflicts;
    }

    /**
     * Forward-pass resource leveling: delay lower-priority tasks to resolve overlaps.
     * Returns { updates: Map<id, {start_date, end_date}>, conflictsResolved, remaining }.
     */
    function levelResources(tasks, links, options) {
        const opts = options || {};
        const taskMap = new Map();
        (tasks || []).forEach(t => taskMap.set(String(t.id), Object.assign({}, t)));
        const conflicts = detectResourceConflicts([...taskMap.values()]);
        const updates = new Map();
        let resolved = 0;

        conflicts.forEach(c => {
            const a = taskMap.get(String(c.taskA));
            const b = taskMap.get(String(c.taskB));
            if (!a || !b) return;
            const aFloat = Number(a.total_float ?? a.$slack ?? 999);
            const bFloat = Number(b.total_float ?? b.$slack ?? 999);
            const moveId = aFloat <= bFloat ? String(c.taskB) : String(c.taskA);
            const stayId = moveId === String(c.taskA) ? String(c.taskB) : String(c.taskA);
            const move = taskMap.get(moveId);
            const stay = taskMap.get(stayId);
            if (!move || !stay) return;
            const stayEnd = taskEndDate(stay);
            if (!stayEnd) return;
            const newStart = addCalendarDays(stayEnd, opts.lagDays || 0);
            const dur = Math.max(0, Number(move.duration) || 0);
            const newEnd = move.type === 'milestone' ? newStart : addCalendarDays(newStart, dur);
            move.start_date = newStart;
            move.end_date = newEnd;
            taskMap.set(moveId, move);
            updates.set(moveId, { start_date: newStart, end_date: newEnd });
            resolved++;
        });

        return { updates, conflictsResolved: resolved, remaining: detectResourceConflicts([...taskMap.values()]).length };
    }

    /** Summarize schedule payload for portfolio dashboard. */
    function summarizeSchedulePayload(payload, dataDate) {
        if (!payload?.data?.length) return null;
        const tasks = payload.data;
        const links = payload.links || [];
        const dd = parseDate(dataDate) || new Date();
        const range = { start: null, end: null };
        let progressSum = 0, progressN = 0, critical = 0;
        tasks.forEach(t => {
            if (t.type === 'project') return;
            const s = taskStartDate(t);
            const e = taskEndDate(t);
            if (s && (!range.start || s < range.start)) range.start = s;
            if (e && (!range.end || e > range.end)) range.end = e;
            const p = t.progress <= 1 ? (Number(t.progress) || 0) : (Number(t.progress) || 0) / 100;
            progressSum += p;
            progressN++;
            if (t.$critical || t.critical) critical++;
        });
        const evm = computeProjectEVM(tasks, dd);
        return {
            activity_count: progressN,
            critical_count: critical,
            pct_complete: progressN ? Math.round((progressSum / progressN) * 100) : 0,
            start_date: range.start ? formatDate(range.start) : null,
            finish_date: range.end ? formatDate(range.end) : null,
            ...evm,
            link_count: links.length
        };
    }

    global.CasePMSchedule = {
        parseDate,
        formatDate,
        addWorkDays,
        addCalendarDays,
        workDaysBetween,
        calendarDaysBetween,
        taskEndDate,
        taskStartDate,
        isWorkDay,
        buildWbsMap,
        isTaskCritical,
        normalizeConstraintType,
        computeEVM,
        computeProjectEVM,
        detectResourceConflicts,
        levelResources,
        summarizeSchedulePayload,
        runCPM,
        computeLookAhead,
        groupLookAheadByWbs
    };
})(typeof window !== 'undefined' ? window : global);
