/* Case PM Schedule — pan bar, theme, histogram, baseline restore, EVM S-curve, non-work shading helpers */
(function (global) {
    'use strict';

    let api = null;
    const pan = { bound: false, dragging: false, startX: 0, startScroll: 0 };
    const bgPan = { active: false, startX: 0, startScroll: 0 };

    function init(hooks) {
        api = hooks;
        initTimelinePanBar();
        initTimelineBackgroundPan();
        applyThemeFromSettings();
    }

    function applyThemeFromSettings() {
        const root = document.querySelector('.schedule-page-root');
        if (!root || !api) return;
        const theme = api.getSettings()?.theme || 'dark';
        root.classList.toggle('schedule-theme-dark', theme !== 'light');
        root.classList.toggle('schedule-theme-light', theme === 'light');
        const btn = document.getElementById('scheduleThemeToggleBtn');
        if (btn) {
            btn.innerHTML = theme === 'light'
                ? '<i class="fa-solid fa-moon"></i>'
                : '<i class="fa-solid fa-sun text-amber-400"></i>';
            btn.title = theme === 'light' ? 'Switch to dark mode (schedule page)' : 'Switch to light mode (schedule page)';
        }
    }

    function toggleTheme() {
        if (!api) return;
        const s = api.getSettings();
        s.theme = s.theme === 'light' ? 'dark' : 'light';
        applyThemeFromSettings();
        api.queueSave();
    }

    function getPanEl() {
        return document.getElementById('scheduleTimelinePan');
    }

    function scrollTimelineFromPan(ratio) {
        const metrics = api.getPanMetrics();
        if (!metrics || metrics.maxScroll <= 0) return;
        const clamped = Math.max(0, Math.min(1, ratio));
        api.setScrollX(clamped * metrics.maxScroll);
    }

    function updateTimelinePanBar() {
        const bar = getPanEl();
        if (!bar || !api?.getPanMetrics) return;
        const host = document.getElementById('gantt_here');
        if (!host) return;
        const metrics = api.getPanMetrics();
        if (!metrics || metrics.maxScroll <= 0) {
            bar.classList.add('hidden');
            return;
        }
        bar.classList.remove('hidden');
        const hostRect = host.getBoundingClientRect();
        const timelineW = api.getTimelineWidth();
        bar.style.left = (hostRect.width - timelineW) + 'px';
        bar.style.width = timelineW + 'px';

        const track = bar.querySelector('.schedule-timeline-pan-track');
        const thumb = bar.querySelector('.schedule-timeline-pan-thumb');
        if (!track || !thumb) return;
        const trackW = track.clientWidth || timelineW - 16;
        const thumbW = Math.max(28, Math.round((metrics.viewW / metrics.totalW) * trackW));
        const travel = Math.max(1, trackW - thumbW);
        const ratio = metrics.maxScroll > 0 ? metrics.scrollX / metrics.maxScroll : 0;
        thumb.style.width = thumbW + 'px';
        thumb.style.left = Math.round(ratio * travel) + 'px';
    }

    function initTimelinePanBar() {
        if (pan.bound) return;
        pan.bound = true;
        const bar = getPanEl();
        if (!bar) return;
        const track = bar.querySelector('.schedule-timeline-pan-track');
        const thumb = bar.querySelector('.schedule-timeline-pan-thumb');
        if (!track || !thumb) return;

        const scrollFromClientX = clientX => {
            const metrics = api.getPanMetrics();
            if (!metrics || metrics.maxScroll <= 0) return;
            const rect = track.getBoundingClientRect();
            const thumbW = thumb.offsetWidth;
            const travel = Math.max(1, rect.width - thumbW);
            const x = Math.max(0, Math.min(travel, clientX - rect.left - thumbW / 2));
            scrollTimelineFromPan(x / travel);
            updateTimelinePanBar();
        };

        const onPointerMove = e => {
            if (!pan.dragging) return;
            const metrics = api.getPanMetrics();
            if (!metrics || metrics.maxScroll <= 0) return;
            const rect = track.getBoundingClientRect();
            const thumbW = thumb.offsetWidth;
            const travel = Math.max(1, rect.width - thumbW);
            const delta = e.clientX - pan.startX;
            const deltaRatio = delta / travel;
            const next = pan.startScroll + deltaRatio * metrics.maxScroll;
            scrollTimelineFromPan(next / metrics.maxScroll);
            updateTimelinePanBar();
        };

        const endPan = () => {
            if (!pan.dragging) return;
            pan.dragging = false;
            try { thumb.releasePointerCapture(pan.pointerId); } catch (e) { /* ok */ }
        };

        thumb.addEventListener('pointerdown', e => {
            e.preventDefault();
            e.stopPropagation();
            pan.dragging = true;
            pan.startX = e.clientX;
            pan.startScroll = api.getScrollX();
            pan.pointerId = e.pointerId;
            try { thumb.setPointerCapture(e.pointerId); } catch (err) { /* ok */ }
        });
        track.addEventListener('pointerdown', e => {
            if (e.target === thumb) return;
            e.preventDefault();
            e.stopPropagation();
            scrollFromClientX(e.clientX);
        });
        thumb.addEventListener('pointermove', onPointerMove);
        thumb.addEventListener('pointerup', endPan);
        thumb.addEventListener('pointercancel', endPan);
        document.addEventListener('pointermove', onPointerMove);
        document.addEventListener('pointerup', endPan);
        document.addEventListener('pointercancel', endPan);
    }

    function initTimelineBackgroundPan() {
        if (bgPan.inited) return;
        bgPan.inited = true;
        const host = document.getElementById('gantt_here');
        if (!host) return;
        host.addEventListener('pointerdown', e => {
            if (e.button !== 0 && e.button !== 1) return;
            const onBar = e.target.closest('.gantt_task_line, .gantt_task_link, .gantt_link_arrow, .sched-floating-cell-editor');
            const onScale = e.target.closest('.gantt_task_scale, .gantt_scale_cell');
            const inTimeline = e.target.closest('.gantt_layout_cell:nth-child(3)');
            if (!inTimeline || onBar) return;
            if (!onScale && !e.target.closest('.gantt_task_bg, .gantt_task, .gantt_data_area')) return;
            bgPan.active = true;
            bgPan.startX = e.clientX;
            bgPan.startScroll = api.getScrollX();
            bgPan.pointerId = e.pointerId;
            e.preventDefault();
            try { host.setPointerCapture(e.pointerId); } catch (err) { /* ok */ }
        });
        const onMove = e => {
            if (!bgPan.active) return;
            const metrics = api.getPanMetrics();
            if (!metrics) return;
            const next = bgPan.startScroll - (e.clientX - bgPan.startX);
            api.setScrollX(Math.max(0, Math.min(metrics.maxScroll, next)));
            updateTimelinePanBar();
        };
        const endBg = e => {
            if (!bgPan.active) return;
            bgPan.active = false;
            try { host.releasePointerCapture(bgPan.pointerId); } catch (err) { /* ok */ }
        };
        host.addEventListener('pointermove', onMove);
        host.addEventListener('pointerup', endBg);
        host.addEventListener('pointercancel', endBg);
    }

    function showResourceHistogram() {
        const dlg = document.getElementById('scheduleResourceHistogramModal');
        const body = document.getElementById('scheduleResourceHistogramBody');
        if (!dlg || !body || !api) return;
        const tasks = api.getTasks();
        const byRes = new Map();
        tasks.forEach(t => {
            if (!t || t.type === 'project' || t.type === 'milestone') return;
            const res = String(t.resource || 'Unassigned').trim() || 'Unassigned';
            res.split(/[,;]+/).map(s => s.trim()).filter(Boolean).forEach(r => {
                if (!byRes.has(r)) byRes.set(r, []);
                byRes.get(r).push(t);
            });
        });
        if (!byRes.size) {
            body.innerHTML = '<p class="text-zinc-400 text-sm">Assign resources to activities to see the histogram.</p>';
        } else {
            let html = '<div class="space-y-4">';
            [...byRes.entries()].sort((a, b) => a[0].localeCompare(b[0])).forEach(([res, list]) => {
                const maxDur = Math.max(...list.map(t => Number(t.duration) || 1), 1);
                html += `<div><div class="text-sm font-medium text-emerald-400 mb-1">${res} <span class="text-zinc-500 font-normal">(${list.length} activities)</span></div><div class="space-y-1">`;
                list.slice(0, 12).forEach(t => {
                    const w = Math.max(8, Math.round(((Number(t.duration) || 1) / maxDur) * 100));
                    html += `<div class="flex items-center gap-2 text-xs">
                        <span class="w-32 truncate text-zinc-400">${t.text || ''}</span>
                        <div class="flex-1 h-4 bg-zinc-800 rounded overflow-hidden"><div class="h-full bg-emerald-600/80 rounded" style="width:${w}%"></div></div>
                        <span class="text-zinc-500 w-10 text-right">${t.duration || 0}d</span>
                    </div>`;
                });
                if (list.length > 12) html += `<div class="text-xs text-zinc-600">+${list.length - 12} more…</div>`;
                html += '</div></div>';
            });
            html += '</div>';
            body.innerHTML = html;
        }
        dlg.showModal();
    }

    function showEvmScurve() {
        const dlg = document.getElementById('scheduleEvmScurveModal');
        const canvas = document.getElementById('scheduleEvmScurveCanvas');
        if (!dlg || !canvas || !api) return;
        const tasks = api.getTasks();
        const dataDate = api.getDataDate();
        const range = api.getSubtaskDates();
        if (!range?.start_date || !tasks.length) {
            api.alert('Run Schedule with cost data to view the EVM S-curve.', 'info');
            return;
        }
        const start = api.parseDate(range.start_date);
        const end = api.parseDate(range.end_date) || api.parseDate(dataDate) || new Date();
        const dd = api.parseDate(dataDate) || new Date();
        if (!start) return;

        const months = [];
        let cur = new Date(start.getFullYear(), start.getMonth(), 1);
        const endM = new Date(end.getFullYear(), end.getMonth() + 1, 1);
        while (cur < endM && months.length < 36) {
            months.push(new Date(cur.getTime()));
            cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
        }

        const points = months.map(m => {
            const monthEnd = new Date(m.getFullYear(), m.getMonth() + 1, 0);
            const asOf = monthEnd > dd ? dd : monthEnd;
            let bac = 0, bcws = 0, bcwp = 0, acwp = 0;
            tasks.forEach(t => {
                if (!t || t.type === 'project') return;
                const cost = Number(t.cost) || 0;
                if (cost <= 0) return;
                bac += cost;
                const ts = api.parseDate(t.start_date);
                const te = api.parseDate(t.end_date);
                const prog = t.progress <= 1 ? (Number(t.progress) || 0) : (Number(t.progress) || 0) / 100;
                if (ts && te) {
                    const span = Math.max(1, api.daysBetween(ts, te));
                    const elapsed = Math.max(0, Math.min(span, api.daysBetween(ts, asOf)));
                    bcws += cost * (elapsed / span);
                }
                bcwp += cost * prog;
                acwp += Number(t.actual_cost) || cost * prog;
            });
            return { label: m.toLocaleDateString(undefined, { month: 'short', year: '2-digit' }), bac, bcws, bcwp, acwp };
        });

        const maxY = Math.max(...points.map(p => Math.max(p.bac, p.bcws, p.bcwp, p.acwp)), 1);
        const ctx = canvas.getContext('2d');
        const W = canvas.width = canvas.offsetWidth * 2 || 800;
        const H = canvas.height = 320;
        ctx.scale(2, 1);
        const w = W / 2;
        const pad = { l: 48, r: 16, t: 20, b: 36 };
        ctx.fillStyle = getComputedStyle(document.querySelector('.schedule-page-root')).getPropertyValue('--sched-bg').trim() || '#18181b';
        ctx.fillRect(0, 0, w, H);
        ctx.strokeStyle = '#3f3f46';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pad.l, pad.t);
        ctx.lineTo(pad.l, H - pad.b);
        ctx.lineTo(w - pad.r, H - pad.b);
        ctx.stroke();

        const plot = (key, color) => {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            points.forEach((p, i) => {
                const x = pad.l + (i / Math.max(1, points.length - 1)) * (w - pad.l - pad.r);
                const y = H - pad.b - (p[key] / maxY) * (H - pad.t - pad.b);
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            });
            ctx.stroke();
        };
        plot('bcws', '#94a3b8');
        plot('bcwp', '#10b981');
        plot('acwp', '#f59e0b');

        ctx.fillStyle = '#a1a1aa';
        ctx.font = '10px sans-serif';
        points.forEach((p, i) => {
            if (i % Math.ceil(points.length / 8) !== 0 && i !== points.length - 1) return;
            const x = pad.l + (i / Math.max(1, points.length - 1)) * (w - pad.l - pad.r);
            ctx.fillText(p.label, x - 12, H - 8);
        });

        const legend = document.getElementById('scheduleEvmScurveLegend');
        if (legend) {
            legend.innerHTML = `<span class="text-slate-400">■ BCWS</span> <span class="text-emerald-400">■ BCWP</span> <span class="text-amber-400">■ ACWP</span> <span class="text-zinc-500 ml-2">BAC $${points[points.length - 1]?.bac?.toLocaleString() || 0}</span>`;
        }
        dlg.showModal();
    }

    function setupNonWorkTemplates(gantt) {
        if (!gantt?.templates) return;
        gantt.templates.timeline_cell_class = function (task, date) {
            if (!date) return '';
            const d = date.getDay();
            return (d === 0 || d === 6) ? 'schedule-nonwork-cell' : '';
        };
        gantt.templates.scale_cell_class = function (date) {
            if (!date) return '';
            const d = date.getDay();
            return (d === 0 || d === 6) ? 'schedule-nonwork-scale' : '';
        };
    }

    function enableBarDrag(gantt, onDragEnd) {
        if (!gantt?.config) return;
        gantt.config.drag_move = true;
        gantt.config.drag_resize = true;
        gantt.config.drag_progress = true;
        gantt.config.drag_links = true;
        if (onDragEnd) gantt.attachEvent('onAfterTaskDrag', onDragEnd);
    }

    global.ScheduleExtras = {
        init,
        toggleTheme,
        applyThemeFromSettings,
        updateTimelinePanBar,
        showResourceHistogram,
        showEvmScurve,
        setupNonWorkTemplates,
        enableBarDrag
    };
})(typeof window !== 'undefined' ? window : global);
