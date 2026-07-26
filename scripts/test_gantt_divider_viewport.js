#!/usr/bin/env node
/**
 * Verifies grid content grows with columns while viewport stays divider-controlled.
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
        const layout = fixtureApplyOverlayLayout();
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const layoutContent = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1) .gantt_layout_content');
        const gridInner = document.querySelector('#gantt_here .gantt_grid');
        return {
            expected,
            overlayW: layout.overlayW,
            paneW: grid?.getBoundingClientRect().width || 0,
            contentScrollW: layoutContent?.scrollWidth || gridInner?.offsetWidth || 0,
            contentFitsColumns: (layoutContent?.scrollWidth || gridInner?.offsetWidth || 0) >= expected - 8,
            viewportUnchanged: Math.abs((grid?.getBoundingClientRect().width || 0) - 660) <= 8,
            canScroll: (layoutContent?.scrollWidth || 0) > (layoutContent?.clientWidth || 0) + 20
        };
    });

    console.log(JSON.stringify(metrics, null, 2));
    if (!metrics.contentFitsColumns || !metrics.viewportUnchanged) {
        console.error('PANE WIDTH CHECK FAILED');
        process.exit(1);
    }
    console.log('PANE WIDTH CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
