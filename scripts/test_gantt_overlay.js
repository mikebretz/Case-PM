#!/usr/bin/env node
/**
 * Verify split-mode divider widens grid pane while keeping bars visible.
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_layout_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_task_scale', { timeout: 15000 });
    await page.waitForTimeout(400);

    const before = await page.evaluate(() => {
        const timeline = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(3)');
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const bars = [...document.querySelectorAll('#gantt_here .gantt_task_line')];
        const gridRight = grid?.getBoundingClientRect().right || 0;
        return {
            timelineW: timeline?.getBoundingClientRect().width || 0,
            gridW: grid?.getBoundingClientRect().width || 0,
            barsInChart: bars.filter(b => b.getBoundingClientRect().left >= gridRight - 4).length
        };
    });

    await page.evaluate(() => {
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const timeline = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(3)');
        const host = document.getElementById('gantt_here');
        const newGridW = 720;
        const timelineW = Math.max(240, host.clientWidth - newGridW - 24);
        if (grid) grid.style.setProperty('width', newGridW + 'px', 'important');
        if (timeline) timeline.style.setProperty('width', timelineW + 'px', 'important');
    });
    await page.waitForTimeout(100);

    const after = await page.evaluate(() => {
        const timeline = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(3)');
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const bars = [...document.querySelectorAll('#gantt_here .gantt_task_line')];
        const gridRight = grid?.getBoundingClientRect().right || 0;
        return {
            timelineW: timeline?.getBoundingClientRect().width || 0,
            gridW: grid?.getBoundingClientRect().width || 0,
            barsInChart: bars.filter(b => b.getBoundingClientRect().left >= gridRight - 4).length
        };
    });

    const result = {
        before,
        after,
        gridGrew: after.gridW > before.gridW + 50,
        timelineShrunk: after.timelineW < before.timelineW - 40,
        barsStillVisible: after.barsInChart >= 1
    };
    console.log(JSON.stringify(result, null, 2));
    if (!result.gridGrew || !result.timelineShrunk || !result.barsStillVisible) process.exit(1);
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
