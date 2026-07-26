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
        const textCol = gantt.config.columns.find(c => c.name === 'text');
        const startCol = gantt.config.columns.find(c => c.name === 'start_date');
        if (textCol) textCol.width = 440;
        if (startCol) startCol.width = 208;
        const expected = gantt.config.columns.reduce((s, c) => s + (parseInt(c.width, 10) || 0), 0);
        gantt.config.grid_width = expected;
        if (gantt.config.layout?.cols?.[0]) {
            gantt.config.layout.cols[0].width = expected;
            gantt.config.layout.cols[0].min_width = expected;
        }
        fixtureApplyOverlayLayout();
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const timeline = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(3)');
        const gridInner = document.querySelector('.gantt_grid');
        const gridRight = grid?.getBoundingClientRect().right || 0;
        const timelineLeft = timeline?.getBoundingClientRect().left || 0;
        return {
            expected,
            paneW: grid?.getBoundingClientRect().width || 0,
            gridInnerW: gridInner?.offsetWidth || 0,
            gap: Math.round(timelineLeft - gridRight),
            paneFitsColumns: (grid?.getBoundingClientRect().width || 0) >= expected - 8
        };
    });

    console.log(JSON.stringify(metrics, null, 2));
    if (!metrics.paneFitsColumns || Math.abs(metrics.gap) > 4) {
        console.error('PANE WIDTH CHECK FAILED');
        process.exit(1);
    }
    console.log('PANE WIDTH CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
