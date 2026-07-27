#!/usr/bin/env node
/**
 * Verifies vertical scroll range exceeds viewport for many tasks in overlay mode.
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_layout_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 700 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_row', { timeout: 15000 });

    const metrics = await page.evaluate(() => {
        const data = [];
        for (let i = 0; i < 80; i++) {
            data.push({
                id: 1000 + i,
                parent: 1,
                text: 'Task ' + i,
                activity_id: 'T' + i,
                start_date: '2023-06-05',
                end_date: '2023-06-20',
                duration: 11
            });
        }
        gantt.parse({ data, links: [] });
        fixtureApplyOverlayLayout();
        if (typeof gantt.setSizes === 'function') gantt.setSizes();
        const rowH = gantt.config.row_height || 24;
        const scaleH = gantt.config.scale_height || 65;
        const needH = scaleH + data.length * rowH;
        const viewH = document.getElementById('gantt_here')?.clientHeight || 700;
        const state = gantt.getScrollState?.() || {};
        const innerH = typeof state.inner_height === 'number' ? state.inner_height : needH;
        const maxScroll = Math.max(0, innerH - viewH + scaleH, needH - viewH);
        return {
            taskCount: 80,
            needH,
            viewH,
            innerH,
            maxScroll,
            canScroll: maxScroll > 120
        };
    });

    console.log(JSON.stringify(metrics, null, 2));
    if (!metrics.canScroll) {
        console.error('VERTICAL SCROLL CHECK FAILED');
        process.exit(1);
    }
    console.log('VERTICAL SCROLL CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
