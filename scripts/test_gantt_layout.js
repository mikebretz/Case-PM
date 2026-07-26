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
        const overlayW = 660;
        const colsW = gantt.config.columns.reduce((s, c) => s + (parseInt(c.width, 10) || 0), 0);
        const gridCell = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const gridInner = document.querySelector('#gantt_here .gantt_grid');
        const hostLeft = document.getElementById('gantt_here')?.getBoundingClientRect().left || 0;
        const bars = [...document.querySelectorAll('#gantt_here .gantt_task_line')];
        return {
            gaps, align, rowHeight: window.gantt?.config?.row_height,
            overlayW, colsW,
            gridPaneW: gridCell?.getBoundingClientRect().width || 0,
            gridContentW: gridInner?.getBoundingClientRect().width || 0,
            barsInChart: bars.filter(b => b.getBoundingClientRect().left >= hostLeft + overlayW - 8).length,
            barCount: bars.length,
            maxGap: Math.max(...gaps, 0),
            maxAlign: Math.max(...align.map(a => Math.abs(a || 0)), 0)
        };
    });

    console.log(JSON.stringify(metrics, null, 2));

    const ok = metrics.maxGap <= 0.5 && metrics.maxAlign <= 1 && metrics.rowHeight === 24
        && metrics.gridContentW >= metrics.colsW - 8
        && Math.abs(metrics.gridPaneW - metrics.overlayW) <= 8
        && metrics.barsInChart >= 1;

    if (!ok) {
        console.error('LAYOUT CHECK FAILED', metrics);
        process.exit(1);
    }
    console.log('LAYOUT CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
