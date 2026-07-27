#!/usr/bin/env node
/**
 * Verify task-bounded rolling calendar bounds (tight window + padding).
 */
function computeRollingCalendarBounds(tasks) {
    const ROLLING_PAD_DAYS = 28;
    const ROLLING_MIN_SPAN_DAYS = 56;
    const addDays = (d, n) => {
        const x = new Date(d.getTime());
        x.setDate(x.getDate() + n);
        return x;
    };
    const daysBetween = (a, b) => Math.round((b - a) / 86400000);

    const today = new Date();
    const defaults = {
        start: addDays(today, -ROLLING_PAD_DAYS),
        end: addDays(today, ROLLING_MIN_SPAN_DAYS)
    };

    let minStart = null;
    let maxEnd = null;
    tasks.forEach(t => {
        const ts = new Date(t.start_date);
        const te = new Date(t.end_date);
        if (!Number.isNaN(ts.getTime()) && (!minStart || ts < minStart)) minStart = ts;
        if (!Number.isNaN(te.getTime()) && (!maxEnd || te > maxEnd)) maxEnd = te;
    });

    if (!minStart || !maxEnd) return defaults;

    let start = addDays(minStart, -ROLLING_PAD_DAYS);
    let end = addDays(maxEnd, ROLLING_PAD_DAYS);
    if (daysBetween(start, end) < ROLLING_MIN_SPAN_DAYS) {
        end = addDays(start, ROLLING_MIN_SPAN_DAYS);
    }
    return { start, end };
}

const bounds = computeRollingCalendarBounds([
    { start_date: '2023-06-05', end_date: '2023-07-28' }
]);

const spanDays = Math.round((bounds.end - bounds.start) / 86400000);
const result = {
    includesJune2023: bounds.start <= new Date('2023-06-05'),
    spanDays,
    spanUnderOneYear: spanDays < 366
};
console.log(JSON.stringify(result, null, 2));
if (!result.includesJune2023) process.exit(1);
if (!result.spanUnderOneYear) process.exit(1);
