#!/usr/bin/env node
/**
 * Verifies grid pane grows to column total width (no halfway squeeze).
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
        const base = { hierarchy: 56, activity_id: 72, text: 240, duration: 64, start_date: 108, end_date: 108 };
        gantt.config.columns = gantt.config.columns.concat([
            { name: 'x1', label: 'Extra A', width: 200, resize: true },
            { name: 'x2', label: 'Extra B', width: 200, resize: true }
        ]);
        const allDefs = { ...base, x1: 200, x2: 200 };
        const expected = Object.values(allDefs).reduce((s, w) => s + w, 0);
        gantt.config.columns.forEach(c => { if (allDefs[c.name] != null) c.width = allDefs[c.name]; });
        gantt.config.grid_width = expected;
        gantt.render();
        const paneW = Math.max(expected, 660);
        document.getElementById('gantt_here').style.setProperty('--sched-grid-overlay-w', paneW + 'px');
        document.getElementById('gantt_here').style.setProperty('--sched-grid-min-width', expected + 'px');
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        if (grid) grid.style.setProperty('width', paneW + 'px', 'important');
        const gridInner = document.querySelector('.gantt_grid');
        if (gridInner) { gridInner.style.width = expected + 'px'; gridInner.style.minWidth = expected + 'px'; }
        return {
            expected,
            paneW: grid?.getBoundingClientRect().width || 0,
            gridInnerW: gridInner?.offsetWidth || 0,
            paneFitsColumns: (grid?.getBoundingClientRect().width || 0) >= expected - 8
        };
    });

    console.log(JSON.stringify(metrics, null, 2));
    if (!metrics.paneFitsColumns) { console.error('PANE WIDTH CHECK FAILED'); process.exit(1); }
    console.log('PANE WIDTH CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
