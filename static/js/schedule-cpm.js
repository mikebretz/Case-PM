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

    function buildAdjacency(links) {
        const preds = new Map();
        const succs = new Map();
        (links || []).forEach(link => {
            if (!preds.has(link.target)) preds.set(link.target, []);
            if (!succs.has(link.source)) succs.set(link.source, []);
            preds.get(link.target).push(link);
            succs.get(link.source).push(link);
        });
        return { preds, succs };
    }

    /**
     * Intelligent construction look-ahead (Procore / P6 style).
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

    global.CasePMSchedule = {
        parseDate,
        formatDate,
        addWorkDays,
        workDaysBetween,
        taskEndDate,
        taskStartDate,
        isWorkDay,
        computeLookAhead,
        groupLookAheadByWbs
    };
})(typeof window !== 'undefined' ? window : global);
