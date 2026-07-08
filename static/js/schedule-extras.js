/* Case PM Schedule — pan slider, theme, histogram, baseline restore, EVM S-curve, non-work shading helpers */
(function (global) {
    'use strict';

    let api = null;
    let rangeBound = false;
    let rangeDragging = false;
    const bgPan = { active: false, startX: 0, startScroll: 0, pointerId: null };

    function init(hooks) {
        api = hooks;
        initTimelineRangeSlider();
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

    function getPanWrap() {
        return document.getElementById('scheduleTimelinePan');
    }

    function getRangeEl() {
        return document.getElementById('scheduleTimelineRange');
    }

    function updateTimelinePanBar() {
        const wrap = getPanWrap();
        const range = getRangeEl();
        if (!wrap || !range || !api?.getPanMetrics) return;
        const hostWrap = document.getElementById('scheduleGanttHost');
        if (!hostWrap) return;
        const metrics = api.getPanMetrics();
        if (!metrics || metrics.maxScroll <= 0) {
            wrap.classList.add('hidden');
            return;
        }
        wrap.classList.remove('hidden');
        const timelineW = api.getTimelineWidth();
        wrap.style.left = Math.max(0, hostWrap.clientWidth - timelineW) + 'px';
        wrap.style.width = timelineW + 'px';

        const max = Math.max(1, Math.round(metrics.maxScroll));
        const val = Math.max(0, Math.min(max, Math.round(metrics.scrollX)));
        if (!rangeDragging) {
            range.max = String(max);
            range.value = String(val);
        }
    }

    function initTimelineRangeSlider() {
        if (rangeBound) return;
        const wrap = getPanWrap();
        const range = getRangeEl();
        if (!wrap || !range) return;
        rangeBound = true;

        range.addEventListener('pointerdown', () => { rangeDragging = true; });
        range.addEventListener('input', () => {
            const metrics = api.getPanMetrics();
            if (!metrics) return;
            api.setScrollX(Number(range.value));
        });
        const endDrag = () => { rangeDragging = false; updateTimelinePanBar(); };
        range.addEventListener('pointerup', endDrag);
        range.addEventListener('pointercancel', endDrag);
        range.addEventListener('change', endDrag);
    }

    function initTimelineBackgroundPan() {
        if (bgPan.inited) return;
        bgPan.inited = true;
        const host = document.getElementById('gantt_here');
        if (!host) return;
        host.addEventListener('pointerdown', e => {
            if (e.button !== 0 && e.button !== 1) return;
            if (e.target.closest('#scheduleOverlayControls, #scheduleChartResizer, #scheduleTimelinePan, #scheduleTimelineRange')) return;
            const onBar = e.target.closest('.gantt_task_line, .gantt_task_link, .gantt_link_arrow, .sched-floating-cell-editor');
            const inTimeline = e.target.closest('.gantt_layout_cell:nth-child(3)');
            if (!inTimeline || onBar) return;
            if (!e.target.closest('.gantt_task_scale, .gantt_scale_cell, .gantt_task_bg, .gantt_task, .gantt_data_area')) return;
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
        const endBg = () => {
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
