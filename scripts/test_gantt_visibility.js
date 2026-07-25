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
        const gridCell = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const gridRight = gridCell ? gridCell.getBoundingClientRect().right : hostRect.left;

        const heads = [...document.querySelectorAll('#gantt_here .gantt_grid_head_cell')];
        const visibleHeads = heads.filter(h => {
            const r = h.getBoundingClientRect();
            return r.width > 2 && r.right > hostRect.left + 4 && r.left < gridRight - 4;
        });

        const bars = [...document.querySelectorAll('#gantt_here .gantt_task_line')];
        const barsInChart = bars.filter(b => {
            const r = b.getBoundingClientRect();
            return r.width > 0 && r.left >= gridRight - 4;
        });

        const wbsGridRows = document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row.sched-wbs-l0, #gantt_here .gantt_grid_data .gantt_row.sched-wbs-l1').length;
        const wbsChartRows = document.querySelectorAll('#gantt_here .gantt_task_row.sched-wbs-l0, #gantt_here .gantt_task_row.sched-wbs-l1').length;

        return {
            gridPaneW: gridCell ? gridCell.getBoundingClientRect().width : 0,
            headCount: heads.length,
            visibleHeads: visibleHeads.length,
            visibleHeadLabels: visibleHeads.map(h => h.textContent.trim()).filter(Boolean),
            barCount: bars.length,
            barsInChart: barsInChart.length,
            wbsChartRows
        };
    });
    console.log(JSON.stringify(result, null, 2));
    if (result.visibleHeads < 4 || result.barsInChart < 1 || result.wbsChartRows > 0) process.exit(1);
    await browser.close();
})();
