#!/usr/bin/env node
/**
 * Verify overlay divider widens grid without shrinking timeline.
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
        const host = document.getElementById('gantt_here');
        return {
            timelineW: timeline?.getBoundingClientRect().width || 0,
            gridW: grid?.getBoundingClientRect().width || 0,
            hostW: host?.clientWidth || 0,
            timelineLeft: timeline?.getBoundingClientRect().left || 0,
            hostLeft: host?.getBoundingClientRect().left || 0
        };
    });

    await page.evaluate(() => {
        const host = document.getElementById('gantt_here');
        const overlayW = 700;
        host.style.setProperty('--sched-grid-overlay-w', overlayW + 'px');
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const timeline = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(3)');
        if (grid) grid.style.setProperty('width', overlayW + 'px', 'important');
        if (timeline) {
            timeline.style.setProperty('position', 'absolute', 'important');
            timeline.style.setProperty('left', '0', 'important');
            timeline.style.setProperty('width', (host.clientWidth - 16) + 'px', 'important');
        }
    });
    await page.waitForTimeout(100);

    const after = await page.evaluate(() => {
        const timeline = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(3)');
        const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        return {
            timelineW: timeline?.getBoundingClientRect().width || 0,
            gridW: grid?.getBoundingClientRect().width || 0
        };
    });

    const result = {
        before,
        after,
        timelineStable: Math.abs(after.timelineW - before.timelineW) < 8,
        gridGrew: after.gridW > before.gridW + 50,
        timelineFullWidth: before.timelineW >= before.hostW - 24
    };
    console.log(JSON.stringify(result, null, 2));
    if (!result.timelineStable || !result.gridGrew || !result.timelineFullWidth) process.exit(1);
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
