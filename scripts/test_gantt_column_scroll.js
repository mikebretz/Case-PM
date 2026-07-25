#!/usr/bin/env node
/**
 * Verifies grid columns extend past overlay viewport and can scroll horizontally.
 * Run: node scripts/test_gantt_column_scroll.js
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
        const extra = [
            { name: 'x1', label: 'Col A', width: 180, resize: true },
            { name: 'x2', label: 'Col B', width: 180, resize: true },
            { name: 'x3', label: 'Col C', width: 180, resize: true }
        ];
        gantt.config.columns = gantt.config.columns.concat(extra);
        const cols = gantt.config.columns;
        const metrics = [];
        let left = 0;
        cols.forEach(col => {
            const w = parseInt(col.width, 10) || 80;
            metrics.push({ w, left });
            left += w;
        });
        const total = left;
        gantt.config.grid_width = total;
        gantt.render();
        gantt.config.grid_width = total;
        const head = document.querySelector('.gantt_grid_scale .gantt_grid_head');
        if (head) { head.style.width = total + 'px'; head.style.minWidth = total + 'px'; }
        document.querySelectorAll('.gantt_grid_scale .gantt_grid_head_cell').forEach((cell, i) => {
            const m = metrics[i];
            if (!m) return;
            cell.style.width = m.w + 'px';
            cell.style.left = m.left + 'px';
        });
        document.querySelectorAll('.gantt_grid_data .gantt_row').forEach(row => {
            row.style.width = total + 'px';
            row.style.minWidth = total + 'px';
            row.querySelectorAll(':scope > .gantt_cell').forEach((cell, i) => {
                const m = metrics[i];
                if (!m) return;
                cell.style.width = m.w + 'px';
                cell.style.left = m.left + 'px';
            });
        });
        const scrollHost = document.querySelector('[data-cell-id="gridScroll"]');
        const inner = scrollHost?.querySelector('div');
        if (inner) { inner.style.width = total + 'px'; inner.style.minWidth = total + 'px'; }
        const gridData = document.querySelector('.gantt_grid_data');
        const gridScale = document.querySelector('.gantt_grid_scale');
        const heads = [...document.querySelectorAll('.gantt_grid_head_cell')];
        const cells = [...document.querySelector('.gantt_grid_data .gantt_row')?.querySelectorAll(':scope > .gantt_cell') || []];
        const mismatches = heads.map((h, i) => ({
            i,
            leftDiff: Math.abs(parseFloat(h.style.left) - parseFloat(cells[i]?.style.left || 0)),
            widthDiff: Math.abs((h.offsetWidth || 0) - (cells[i]?.offsetWidth || 0))
        })).filter(x => x.leftDiff > 1 || x.widthDiff > 2);
        return {
            total,
            overlayW: 660,
            gridDataClient: gridData?.clientWidth || 0,
            gridDataScroll: gridData?.scrollWidth || 0,
            headWidth: head?.offsetWidth || 0,
            scrollInner: inner?.offsetWidth || 0,
            mismatches,
            canScroll: (gridData?.scrollWidth || 0) > (gridData?.clientWidth || 0) + 20
        };
    });

    console.log(JSON.stringify(metrics, null, 2));

    const ok = metrics.canScroll
        && metrics.gridDataScroll >= metrics.total - 4
        && metrics.mismatches.length === 0;

    if (!ok) {
        console.error('COLUMN SCROLL CHECK FAILED', metrics);
        process.exit(1);
    }
    console.log('COLUMN SCROLL CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
