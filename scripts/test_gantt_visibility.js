#!/usr/bin/env node
const path = require('path');
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + path.join(__dirname, 'gantt_layout_fixture.html'), { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_task_line');
    await page.waitForTimeout(300);

    const result = await page.evaluate(() => {
        const host = document.getElementById('gantt_here');
        const hostRect = host.getBoundingClientRect();
        const overlayW = 660;
        const gridCell = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');

        const heads = [...document.querySelectorAll('#gantt_here .gantt_grid_head_cell')];
        const visibleHeads = heads.filter(h => {
            const r = h.getBoundingClientRect();
            return r.width > 2 && r.right > hostRect.left + 4 && r.left < hostRect.left + overlayW - 4;
        });

        const bars = [...document.querySelectorAll('#gantt_here .gantt_task_line')];
        const barsInChart = bars.filter(b => {
            const r = b.getBoundingClientRect();
            return r.width > 0 && r.left >= hostRect.left + overlayW - 8;
        });

        return {
            gridPaneW: gridCell ? gridCell.getBoundingClientRect().width : 0,
            headCount: heads.length,
            visibleHeads: visibleHeads.length,
            barCount: bars.length,
            barsInChart: barsInChart.length
        };
    });
    console.log(JSON.stringify(result, null, 2));
    if (result.visibleHeads < 4 || result.barsInChart < 1) process.exit(1);
    await browser.close();
})();
