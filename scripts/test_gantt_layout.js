#!/usr/bin/env node
/**
 * Headless visual/layout checks for P6-style Gantt overlay mode.
 * Run: node scripts/test_gantt_layout.js
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_layout_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_row', { timeout: 15000 });
    await page.waitForTimeout(500);

    const metrics = await page.evaluate(() => {
        const rows = Array.from(document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row')).slice(0, 8);
        const taskRows = Array.from(document.querySelectorAll('#gantt_here .gantt_task_row')).slice(0, 8);
        const rowHeights = rows.map(r => r.getBoundingClientRect().height);
        const taskHeights = taskRows.map(r => r.getBoundingClientRect().height);
        const gaps = [];
        for (let i = 1; i < rows.length; i++) {
            const prev = rows[i - 1].getBoundingClientRect();
            const cur = rows[i].getBoundingClientRect();
            gaps.push(Math.round((cur.top - prev.bottom) * 100) / 100);
        }
        const align = rows.map((r, i) => {
            const tr = taskRows[i];
            if (!tr) return null;
            const rg = r.getBoundingClientRect();
            const tg = tr.getBoundingClientRect();
            return Math.round((rg.top - tg.top) * 100) / 100;
        });
        const resizeWraps = document.querySelectorAll('#gantt_here .gantt_grid_column_resize_wrap').length;
        const overlay = document.getElementById('scheduleGanttHost')?.classList.contains('schedule-overlay-mode');
        const split = document.getElementById('scheduleGanttHost')?.classList.contains('schedule-split-mode');
        const linkSegs = document.querySelectorAll('#gantt_here .gantt_task_link .gantt_line_wrapper div').length;
        const timelineCell = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(3)');
        const timelineLeft = timelineCell ? timelineCell.getBoundingClientRect().left : 0;
        const hostLeft = document.getElementById('gantt_here')?.getBoundingClientRect().left || 0;
        const timelineWidth = timelineCell ? timelineCell.getBoundingClientRect().width : 0;
        const hostWidth = document.getElementById('gantt_here')?.clientWidth || 0;
        const heads = [...document.querySelectorAll('#gantt_here .gantt_grid_head_cell')];
        const visibleHeads = heads.filter(h => h.getBoundingClientRect().width > 2).length;
        const bars = [...document.querySelectorAll('#gantt_here .gantt_task_line')];
        const overlayW = 660;
        const barsInChart = bars.filter(b => b.getBoundingClientRect().left >= hostLeft + overlayW - 8).length;
        return {
            rowHeights, taskHeights, gaps, align, resizeWraps, overlay, split, linkSegs,
            rowHeight: window.gantt?.config?.row_height,
            timelineLeft, hostLeft, timelineWidth, hostWidth,
            visibleHeads, barsInChart, barCount: bars.length
        };
    });

    console.log(JSON.stringify(metrics, null, 2));

    const maxGap = Math.max(...metrics.gaps, 0);
    const maxAlign = Math.max(...metrics.align.map(a => Math.abs(a || 0)), 0);
    const overlayW = 660;
    const timelineStartsAtDivider = Math.abs(metrics.timelineLeft - (metrics.hostLeft + overlayW)) <= 12;
    const timelineFillsChartPane = metrics.timelineWidth >= metrics.hostWidth - overlayW - 32;
    const ok = metrics.overlay && !metrics.split && metrics.resizeWraps > 0
        && maxGap <= 0.5 && maxAlign <= 1 && metrics.rowHeight === 24
        && timelineStartsAtDivider && timelineFillsChartPane
        && metrics.visibleHeads >= 5 && metrics.barsInChart >= 1;

    if (!ok) {
        console.error('LAYOUT CHECK FAILED', {
            maxGap, maxAlign, timelineStartsAtDivider, timelineFillsChartPane,
            visibleHeads: metrics.visibleHeads, barsInChart: metrics.barsInChart, ok
        });
        process.exit(1);
    }
    console.log('LAYOUT CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
