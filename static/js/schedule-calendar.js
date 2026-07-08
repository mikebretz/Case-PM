/**
 * Case PM — 12-month calendar schedule view with activity bars across days.
 */
(function (global) {
  'use strict';

  const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'];
  const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  function parseDate(value) {
    if (!value) return null;
    if (value instanceof Date && !isNaN(value)) return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    if (typeof global.CasePMSchedule !== 'undefined' && global.CasePMSchedule.parseDate) {
      const d = global.CasePMSchedule.parseDate(value);
      if (d) return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }
    const raw = String(value).trim();
    const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) return new Date(+iso[1], +iso[2] - 1, +iso[3]);
    const us = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
    if (us) {
      const yr = us[3].length === 2 ? 2000 + +us[3] : +us[3];
      return new Date(yr, +us[1] - 1, +us[2]);
    }
    const d = new Date(raw);
    return isNaN(d) ? null : new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function sameDay(a, b) {
    return a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function dayKey(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function taskColor(task, idx) {
    if (task.critical || task.$critical) return '#ef4444';
    const palette = ['#10b981', '#0ea5e9', '#8b5cf6', '#f59e0b', '#ec4899', '#14b8a6', '#6366f1'];
    return palette[idx % palette.length];
  }

  function collectTasks(getTasks) {
    const tasks = typeof getTasks === 'function' ? getTasks() : [];
    return tasks.filter(t => t && t.type !== 'project' && t.start_date).map(t => {
      const start = parseDate(t.start_date);
      let end = parseDate(t.end_date);
      if (!end && start) end = new Date(start);
      if (start && end && end < start) end = new Date(start);
      return { task: t, start, end, label: t.text || t.name || 'Activity' };
    }).filter(x => x.start);
  }

  function resolveYear(tasks, preferredYear) {
    if (preferredYear) return preferredYear;
    let min = null;
    let max = null;
    tasks.forEach(t => {
      if (!min || t.start < min) min = t.start;
      if (!max || (t.end && t.end > max)) max = t.end;
      else if (!max || t.start > max) max = t.start;
    });
    if (min) return min.getFullYear();
    return new Date().getFullYear();
  }

  function tasksForDay(tasks, day) {
    return tasks.filter(t => {
      const end = t.end || t.start;
      return t.start <= day && end >= day;
    });
  }

  function renderMonth(year, month, tasks) {
    const first = new Date(year, month, 1);
    const last = new Date(year, month + 1, 0);
    const startPad = first.getDay();
    const daysInMonth = last.getDate();

    let cells = '';
    for (let i = 0; i < startPad; i++) {
      cells += '<div class="sched-cal-day sched-cal-day-pad"></div>';
    }
    for (let d = 1; d <= daysInMonth; d++) {
      const day = new Date(year, month, d);
      const isWeekend = day.getDay() === 0 || day.getDay() === 6;
      const dayTasks = tasksForDay(tasks, day);
      const bars = dayTasks.slice(0, 4).map((t, i) => {
        const isStart = sameDay(t.start, day);
        const isEnd = sameDay(t.end || t.start, day);
        const cls = ['sched-cal-bar'];
        if (isStart) cls.push('sched-cal-bar-start');
        if (isEnd) cls.push('sched-cal-bar-end');
        if (!isStart && !isEnd) cls.push('sched-cal-bar-mid');
        const title = `${t.label} (${t.start.toLocaleDateString()} – ${(t.end || t.start).toLocaleDateString()})`;
        return `<div class="${cls.join(' ')}" style="background:${taskColor(t.task, i)}" title="${esc(title)}">${isStart ? esc(t.label.length > 14 ? t.label.slice(0, 12) + '…' : t.label) : '&nbsp;'}</div>`;
      }).join('');
      const more = dayTasks.length > 4 ? `<div class="sched-cal-more">+${dayTasks.length - 4} more</div>` : '';
      cells += `<div class="sched-cal-day${isWeekend ? ' sched-cal-weekend' : ''}">
        <div class="sched-cal-day-num">${d}</div>
        <div class="sched-cal-bars">${bars}${more}</div>
      </div>`;
    }
    const totalCells = startPad + daysInMonth;
    const trailing = (7 - (totalCells % 7)) % 7;
    for (let i = 0; i < trailing; i++) {
      cells += '<div class="sched-cal-day sched-cal-day-pad"></div>';
    }

    return `<div class="sched-cal-month">
      <div class="sched-cal-month-title">${MONTH_NAMES[month]} ${year}</div>
      <div class="sched-cal-dow">${DOW.map(d => `<span>${d}</span>`).join('')}</div>
      <div class="sched-cal-grid">${cells}</div>
    </div>`;
  }

  function render(container, options) {
    if (!container) return;
    const tasks = collectTasks(options.getTasks);
    const year = resolveYear(tasks, options.year);
    const yearInput = options.yearInputId ? document.getElementById(options.yearInputId) : null;
    if (yearInput && !yearInput.value) yearInput.value = year;

    const displayYear = yearInput ? parseInt(yearInput.value, 10) || year : year;

    if (!tasks.length) {
      container.innerHTML = `<div class="sched-cal-empty">
        <p class="text-zinc-400 text-center py-12">No scheduled activities with dates. Add activities on the Gantt chart or import a schedule.</p>
      </div>`;
      return;
    }

    let html = `<div class="sched-cal-toolbar no-print">
      <div class="flex items-center gap-3 flex-wrap">
        <label class="text-sm text-zinc-400 flex items-center gap-2">Year
          <input type="number" id="schedCalYearInput" value="${displayYear}" min="2000" max="2100"
            class="w-24 bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-sm text-white"
            onchange="ScheduleCalendar.rerender()">
        </label>
        <span class="text-xs text-zinc-500">${tasks.length} activities with dates</span>
        <button type="button" class="schedule-toolbar-btn" onclick="ScheduleCalendar.rerender()"><i class="fa-solid fa-rotate"></i> Refresh</button>
      </div>
    </div>
    <div class="sched-cal-year-grid">`;

    for (let m = 0; m < 12; m++) {
      html += renderMonth(displayYear, m, tasks);
    }
    html += '</div>';
    container.innerHTML = html;
  }

  let _container = null;
  let _options = {};

  function init(containerId, options) {
    _container = document.getElementById(containerId);
    _options = options || {};
    render(_container, _options);
  }

  function rerender() {
    if (!_container) _container = document.getElementById('scheduleCalendarContent');
    const yearInput = document.getElementById('schedCalYearInput');
    if (yearInput) _options.year = parseInt(yearInput.value, 10) || _options.year;
    render(_container, _options);
  }

  global.ScheduleCalendar = { init, render, rerender };
})(window);
