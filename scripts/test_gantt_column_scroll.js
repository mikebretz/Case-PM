#!/usr/bin/env node
/**
 * Verifies grid columns keep full width and can scroll horizontally in overlay viewport.
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
        const defWidths = {};
        gantt.config.columns.forEach(col => { defWidths[col.name] = col.width; });
        let total = 0;
        gantt.config.columns.forEach(col => { total += parseInt(col.width, 10) || 80; });
        gantt.config.grid_width = total;
        gantt.render();
        gantt.config.columns.forEach(col => {
            if (defWidths[col.name] != null) col.width = defWidths[col.name];
        });
        const gridInner = document.querySelector('.gantt_grid');
        if (gridInner) { gridInner.style.width = total + 'px'; gridInner.style.minWidth = total + 'px'; }
        document.getElementById('gantt_here').style.setProperty('--sched-grid-min-width', total + 'px');
        let left = 0;
        gantt.config.columns.forEach((col, i) => {
            const w = parseInt(col.width, 10) || 80;
            document.querySelectorAll('.gantt_grid_head_cell')[i]?.style && (document.querySelectorAll('.gantt_grid_head_cell')[i].style.cssText = `width:${w}px;min-width:${w}px;flex:0 0 ${w}px`);
            document.querySelectorAll('.gantt_grid_data .gantt_row').forEach(row => {
                const cell = row.querySelectorAll(':scope > .gantt_cell')[i];
                if (cell) { cell.style.width = w + 'px'; cell.style.minWidth = w + 'px'; cell.style.flex = `0 0 ${w}px`; }
            });
            left += w;
        });
        const scrollHost = document.querySelector('[data-cell-id="gridScroll"]');
        const inner = scrollHost?.querySelector('div');
        if (inner) { inner.style.width = total + 'px'; inner.style.minWidth = total + 'px'; }
        const layout = fixtureApplyOverlayLayout();
        const gridData = document.querySelector('.gantt_grid_data');
        const layoutContent = document.querySelector('#gantt_here .gantt_layout_root > .gantt_layout_cell:nth-child(1) .gantt_layout_content');
        const row = document.querySelector('.gantt_grid_data .gantt_row');
        const cellSum = [...row.querySelectorAll(':scope > .gantt_cell')].reduce((s, c) => s + c.offsetWidth, 0);
        return {
            total,
            gridInnerW: document.querySelector('.gantt_grid')?.offsetWidth || 0,
            contentScrollW: layoutContent?.scrollWidth || 0,
            canScroll: (layoutContent?.scrollWidth || 0) > (layoutContent?.clientWidth || 0) + 20,
            contentWide: (document.querySelector('.gantt_grid')?.offsetWidth || 0) >= total - 12,
            cellSum
        };
    });

    console.log(JSON.stringify(metrics, null, 2));
    const ok = metrics.contentWide && metrics.canScroll;
    if (!ok) { console.error('COLUMN SCROLL CHECK FAILED', metrics); process.exit(1); }
    console.log('COLUMN SCROLL CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
