#!/usr/bin/env node
/**
 * Verifies custom column resize grips align with header cell right borders.
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_layout_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_row', { timeout: 15000 });

    await page.waitForSelector('.gantt_grid_head_cell', { timeout: 15000 });

    const metrics = await page.evaluate(() => {
        fixtureApplyOverlayLayout();
        const gridHead = document.querySelector('#gantt_here .gantt_grid_scale .gantt_grid_head')
            || document.querySelector('#gantt_here .gantt_grid_scale');
        if (!gridHead) return { error: 'no grid head' };
        const headCells = [...gridHead.querySelectorAll('.gantt_grid_head_cell')];
        let layer = gridHead.querySelector('.sched-col-grip-layer');
        if (!layer) {
            layer = document.createElement('div');
            layer.className = 'sched-col-grip-layer';
            gridHead.appendChild(layer);
        }
        layer.innerHTML = '';
        headCells.forEach((cell, i) => {
            const col = gantt.config.columns[i];
            if (!col || col.resize === false) return;
            const borderX = cell.offsetLeft + cell.offsetWidth;
            const grip = document.createElement('div');
            grip.className = 'sched-col-resize-grip gantt_grid_column_resize_wrap';
            grip.dataset.colIndex = String(i);
            grip.style.cssText = `position:absolute;left:${borderX}px;top:26px;height:39px;width:10px;margin-left:-5px`;
            grip.innerHTML = '<div class="gantt_grid_column_resize"></div>';
            layer.appendChild(grip);
        });

        const grips = [...layer.querySelectorAll('.sched-col-resize-grip')];
        const mismatches = [];
        grips.forEach(grip => {
            const i = parseInt(grip.dataset.colIndex, 10);
            const cell = headCells[i];
            if (!cell) return;
            const cellRect = cell.getBoundingClientRect();
            const gripRect = grip.getBoundingClientRect();
            const delta = Math.round((gripRect.left + gripRect.width / 2) - cellRect.right);
            if (Math.abs(delta) > 1) mismatches.push({ i, name: gantt.config.columns[i]?.name, delta });
        });

        const row = document.querySelector('.gantt_grid_data .gantt_row');
        const rowCells = row ? [...row.querySelectorAll(':scope > .gantt_cell')] : [];
        const rowMismatches = headCells.map((h, i) => {
            const c = rowCells[i];
            if (!c) return null;
            return {
                i,
                headLeft: parseFloat(h.style.left) || 0,
                cellLeft: parseFloat(c.style.left) || 0,
                headW: h.offsetWidth,
                cellW: c.offsetWidth
            };
        }).filter(x => x && (Math.abs(x.headLeft - x.cellLeft) > 1 || Math.abs(x.headW - x.cellW) > 2));

        return { gripCount: grips.length, mismatches, rowMismatches };
    });

    console.log(JSON.stringify(metrics, null, 2));
    if (metrics.error) { console.error(metrics.error); process.exit(1); }
    const ok = metrics.gripCount >= 4
        && metrics.mismatches.length === 0
        && metrics.rowMismatches.length === 0;
    if (!ok) {
        console.error('RESIZE GRIP ALIGN CHECK FAILED');
        process.exit(1);
    }
    console.log('RESIZE GRIP ALIGN CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
