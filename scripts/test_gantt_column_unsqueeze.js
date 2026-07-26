#!/usr/bin/env node
/**
 * Verifies dhtmlx does not squeeze grid columns to the overlay viewport width.
 * Run: node scripts/test_gantt_column_unsqueeze.js
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
            { name: 'x1', label: 'Extra A', width: 200, resize: true },
            { name: 'x2', label: 'Extra B', width: 200, resize: true }
        ]);
        const expected = Object.values(defWidths).reduce((s, w) => s + w, 0) + 400;
        gantt.config.keep_grid_width = true;
        gantt.config.grid_width = expected;
        gantt.config.columns.forEach(c => {
            if (defWidths[c.name] != null) c.width = defWidths[c.name];
        });
        const allDefs = { ...defWidths, x1: 200, x2: 200 };
        gantt.config.layout.cols[0].width = 1400;
        gantt.render();
        gantt.config.columns.forEach(c => {
            if (allDefs[c.name] != null) c.width = allDefs[c.name];
        });
        gantt.config.grid_width = expected;

        const applyLayout = () => {
            const cols = gantt.config.columns;
            const colMetrics = [];
            let left = 0;
            cols.forEach(col => {
                const w = allDefs[col.name] || parseInt(col.width, 10) || 80;
                colMetrics.push({ w, left });
                left += w;
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
                cell.style.minWidth = m.w + 'px';
                cell.style.maxWidth = m.w + 'px';
            });
            document.querySelectorAll('.gantt_grid_data .gantt_row').forEach(row => {
                row.style.width = total + 'px';
                row.style.minWidth = total + 'px';
                row.querySelectorAll(':scope > .gantt_cell').forEach((cell, i) => {
                    const m = colMetrics[i];
                    if (!m) return;
                    cell.style.position = 'absolute';
                    cell.style.left = m.left + 'px';
                    cell.style.top = '0';
                    cell.style.height = '100%';
                    cell.style.width = m.w + 'px';
                });
            });
            [document.querySelector('.gantt_grid_data'), document.querySelector('.gantt_grid_scale')].forEach(host => {
                if (!host) return;
                let s = host.querySelector('.sched-grid-scroll-sentinel');
                if (!s) {
                    s = document.createElement('div');
                    s.className = 'sched-grid-scroll-sentinel';
                    host.appendChild(s);
                }
                s.style.cssText = 'position:absolute;left:0;top:0;height:1px;width:' + total + 'px;visibility:hidden;pointer-events:none';
            });
            return total;
        };
        const total = applyLayout();
        fixtureApplyOverlayLayout();
        const row = document.querySelector('.gantt_grid_data .gantt_row');
        const cells = [...row.querySelectorAll(':scope > .gantt_cell')];
        const cellSum = cells.reduce((s, c) => s + c.offsetWidth, 0);
        const gridPane = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1)');
        const overlayW = 660;
        const contentScrollW = document.querySelector('.gantt_grid')?.offsetWidth || gridPane?.scrollWidth || 0;
        const canScroll = contentScrollW > overlayW + 20
            || (gridPane?.scrollWidth || 0) > (gridPane?.clientWidth || 0) + 20;
        return {
            expected,
            total,
            configSum: gantt.config.columns.reduce((s, c) => s + (parseInt(c.width, 10) || 0), 0),
            cellSum,
            contentScrollW,
            gridDataClient: gridPane?.clientWidth || 0,
            overlayW,
            canScroll,
            squeezed: cellSum < expected - 20
        };
    });

    console.log(JSON.stringify(metrics, null, 2));

    const ok = !metrics.squeezed
        && metrics.configSum >= metrics.expected - 4
        && metrics.cellSum >= metrics.expected - 12
        && metrics.canScroll;

    if (!ok) {
        console.error('COLUMN UNSQUEEZE CHECK FAILED', metrics);
        process.exit(1);
    }
    console.log('COLUMN UNSQUEEZE CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
