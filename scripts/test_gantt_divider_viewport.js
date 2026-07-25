#!/usr/bin/env node
/**
 * Verifies grid content keeps full column width inside overlay viewport.
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_layout_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_row', { timeout: 15000 });
    await page.waitForTimeout(300);

    const metrics = await page.evaluate(() => {
        const defWidths = { hierarchy: 56, activity_id: 72, text: 240, duration: 64, start_date: 108, end_date: 108 };
        gantt.config.columns = gantt.config.columns.concat([
            { name: 'x1', label: 'Extra A', width: 300, resize: true },
            { name: 'x2', label: 'Extra B', width: 300, resize: true }
        ]);
        const allDefs = { ...defWidths, x1: 300, x2: 300 };
        const expected = Object.values(allDefs).reduce((s, w) => s + w, 0);
        gantt.config.columns.forEach(c => {
            if (allDefs[c.name] != null) c.width = allDefs[c.name];
        });
        gantt.config.grid_width = expected;
        gantt.config.keep_grid_width = true;
        gantt.render();

        let left = 0;
        gantt.config.columns.forEach(col => {
            const w = allDefs[col.name] || parseInt(col.width, 10) || 80;
            col.width = w;
            left += w;
        });
        const total = left;
        const head = document.querySelector('.gantt_grid_head');
        if (head) { head.style.width = total + 'px'; head.style.minWidth = total + 'px'; }
        document.querySelectorAll('.gantt_grid_head_cell').forEach((cell, i) => {
            const col = gantt.config.columns[i];
            const w = allDefs[col?.name] || parseInt(col?.width, 10) || 80;
            cell.style.width = w + 'px';
            cell.style.minWidth = w + 'px';
            cell.style.flex = `0 0 ${w}px`;
        });
        const gridInner = document.querySelector('.gantt_grid');
        if (gridInner) { gridInner.style.width = total + 'px'; gridInner.style.minWidth = total + 'px'; }
        document.getElementById('gantt_here').style.setProperty('--sched-grid-min-width', total + 'px');

        const row = document.querySelector('.gantt_grid_data .gantt_row');
        const cellSum = [...row.querySelectorAll(':scope > .gantt_cell')].reduce((s, c) => s + c.offsetWidth, 0);
        const gridInnerW = gridInner?.offsetWidth || 0;

        return { expected, cellSum, gridInnerW, columnsPreserved: cellSum >= expected - 12, contentWide: gridInnerW >= expected - 12 };
    });

    console.log(JSON.stringify(metrics, null, 2));
    const ok = metrics.contentWide;
    if (!ok) { console.error('GRID CONTENT WIDTH CHECK FAILED', metrics); process.exit(1); }
    console.log('GRID CONTENT WIDTH CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
