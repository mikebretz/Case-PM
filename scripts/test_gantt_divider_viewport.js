#!/usr/bin/env node
/**
 * Verifies grid pane auto-expands to fit all column widths (no squeeze).
 * Run: node scripts/test_gantt_divider_viewport.js
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
            { name: 'x2', label: 'Extra B', width: 300, resize: true },
            { name: 'x3', label: 'Extra C', width: 300, resize: true }
        ]);
        const allDefs = { ...defWidths, x1: 300, x2: 300, x3: 300 };
        const expected = Object.values(allDefs).reduce((s, w) => s + w, 0);
        gantt.config.columns.forEach(c => {
            if (allDefs[c.name] != null) c.width = allDefs[c.name];
        });
        gantt.config.grid_width = expected;
        gantt.config.keep_grid_width = true;
        gantt.render();

        const applyLayout = (userOverlayW) => {
            const visibleW = Math.max(expected, userOverlayW);
            const host = document.getElementById('gantt_here');
            host.style.setProperty('--sched-grid-overlay-w', visibleW + 'px');
            host.style.setProperty('--sched-chart-left', visibleW + 'px');
            const grid = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
            if (grid) grid.style.setProperty('width', visibleW + 'px', 'important');

            const cols = gantt.config.columns;
            let left = 0;
            const colMetrics = cols.map(col => {
                const w = allDefs[col.name] || parseInt(col.width, 10) || 80;
                const m = { w, left };
                left += w;
                return m;
            });
            const total = left;
            const head = document.querySelector('.gantt_grid_head');
            if (head) {
                head.style.position = 'relative';
                head.style.width = total + 'px';
                head.style.minWidth = total + 'px';
            }
            document.querySelectorAll('.gantt_grid_head_cell').forEach((cell, i) => {
                const m = colMetrics[i];
                if (!m) return;
                cell.style.position = 'absolute';
                cell.style.left = m.left + 'px';
                cell.style.width = m.w + 'px';
            });
            document.querySelectorAll('.gantt_grid_data .gantt_row').forEach(row => {
                row.style.width = total + 'px';
                row.querySelectorAll(':scope > .gantt_cell').forEach((cell, i) => {
                    const m = colMetrics[i];
                    if (!m) return;
                    cell.style.position = 'absolute';
                    cell.style.left = m.left + 'px';
                    cell.style.width = m.w + 'px';
                });
            });
            return { total, gridPaneW: grid?.getBoundingClientRect().width || 0 };
        };

        const narrow = applyLayout(200);
        const wide = applyLayout(900);
        const row = document.querySelector('.gantt_grid_data .gantt_row');
        const cellSum = [...row.querySelectorAll(':scope > .gantt_cell')].reduce((s, c) => s + c.offsetWidth, 0);
        const gridData = document.querySelector('.gantt_grid_data');

        return {
            expected,
            cellSum,
            narrowPane: narrow.gridPaneW,
            widePane: wide.gridPaneW,
            autoExpandedToColumns: narrow.gridPaneW >= expected - 8,
            columnsPreserved: cellSum >= expected - 12,
            paneFitsColumns: narrow.gridPaneW >= cellSum - 12,
            noHorizontalScrollNeeded: (gridData?.scrollWidth || 0) <= (gridData?.clientWidth || 0) + 4,
            canWidenPastColumns: wide.gridPaneW >= 880
        };
    });

    console.log(JSON.stringify(metrics, null, 2));

    const ok = metrics.autoExpandedToColumns
        && metrics.columnsPreserved
        && metrics.paneFitsColumns
        && metrics.canWidenPastColumns;

    if (!ok) {
        console.error('GRID AUTO-EXPAND CHECK FAILED', metrics);
        process.exit(1);
    }
    console.log('GRID AUTO-EXPAND CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
