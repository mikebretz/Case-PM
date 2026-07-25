#!/usr/bin/env node
/**
 * Verify rolling calendar bounds include tasks older than the default window.
 */
function computeRollingCalendarBounds(tasks, nowYear) {
    const ROLLING_YEARS_BACK = 2;
    const ROLLING_YEARS_FORWARD = 6;
    const ROLLING_MIN_SPAN_DAYS = 365 * 3;
    const addDays = (d, n) => {
        const x = new Date(d.getTime());
        x.setDate(x.getDate() + n);
        return x;
    };
    const daysBetween = (a, b) => Math.round((b - a) / 86400000);

    const defaults = {
        start: new Date(nowYear - ROLLING_YEARS_BACK, 0, 1),
        end: new Date(nowYear + ROLLING_YEARS_FORWARD, 11, 31)
    };
    let start = new Date(defaults.start.getTime());
    let end = new Date(defaults.end.getTime());
    tasks.forEach(t => {
        const ts = new Date(t.start_date);
        const te = new Date(t.end_date);
        if (!Number.isNaN(ts.getTime())) {
            const padded = addDays(ts, -60);
            if (padded < start) start = padded;
        }
        if (!Number.isNaN(te.getTime())) {
            const padded = addDays(te, 120);
            if (padded > end) end = padded;
        }
    });
    if (daysBetween(start, end) < ROLLING_MIN_SPAN_DAYS) {
        end = addDays(start, ROLLING_MIN_SPAN_DAYS);
    }
    return { start, end };
}

const bounds = computeRollingCalendarBounds([
    { start_date: '2023-06-05', end_date: '2023-07-28' }
], 2026);

const result = {
    startYear: bounds.start.getFullYear(),
    startMonth: bounds.start.getMonth() + 1,
    includesJune2023: bounds.start <= new Date('2023-06-05')
};
console.log(JSON.stringify(result, null, 2));
if (!result.includesJune2023) process.exit(1);
