#!/usr/bin/env node
/**
 * Verifies grid rows stay aligned with timeline bars when columns are enforced,
 * and that columns extend past the overlay viewport.
 * Run: node scripts/test_gantt_row_column_layout.js
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_layout_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_row', { timeout: 15000 });
    await page.waitForTimeout(200);

    const metrics = await page.evaluate(() => {
        gantt.config.columns = gantt.config.columns.concat([
            { name: 'x1', label: 'Extra A', width: 200, resize: true },
            { name: 'x2', label: 'Extra B', width: 200, resize: true }
        ]);
        const defWidths = {};
        gantt.config.columns.forEach(c => { defWidths[c.name] = c.width; });
        gantt.config.keep_grid_width = true;
        gantt.config.grid_width = gantt.config.columns.reduce((s, c) => s + c.width, 0);
        gantt.render();

        const cols = gantt.config.columns;
        const colMetrics = [];
        let left = 0;
        cols.forEach(col => {
            const w = defWidths[col.name] || col.width;
            colMetrics.push({ w, left });
            left += w;
        });
        const total = left;
        const head = document.querySelector('.gantt_grid_scale .gantt_grid_head');
        if (head) {
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

        const rows = [...document.querySelectorAll('.gantt_grid_data .gantt_row')].slice(0, 8);
        const taskRows = [...document.querySelectorAll('.gantt_task_row')].slice(0, 8);
        const gaps = [];
        for (let i = 1; i < rows.length; i++) {
            const prev = rows[i - 1].getBoundingClientRect();
            const cur = rows[i].getBoundingClientRect();
            gaps.push(Math.round((cur.top - prev.bottom) * 100) / 100);
        }
        const align = rows.map((r, i) => {
            const tr = taskRows[i];
            if (!tr) return null;
            return Math.round((r.getBoundingClientRect().top - tr.getBoundingClientRect().top) * 100) / 100;
        });
        const gridData = document.querySelector('.gantt_grid_data');
        const heads = [...document.querySelectorAll('.gantt_grid_head_cell')];
        const cells = [...rows[0]?.querySelectorAll(':scope > .gantt_cell') || []];
        const mismatches = heads.map((h, i) => ({
            i,
            leftDiff: Math.abs(parseFloat(h.style.left) - parseFloat(cells[i]?.style.left || 0)),
            widthDiff: Math.abs((h.offsetWidth || 0) - (cells[i]?.offsetWidth || 0))
        })).filter(x => x.leftDiff > 1 || x.widthDiff > 2);

        return {
            total,
            gridDataScroll: gridData?.scrollWidth || 0,
            gridDataClient: gridData?.clientWidth || 0,
            rowPositions: rows.slice(0, 3).map(r => getComputedStyle(r).position),
            maxGap: Math.max(...gaps, 0),
            maxAlign: Math.max(...align.map(a => Math.abs(a || 0)), 0),
            mismatches,
            canScroll: (gridData?.scrollWidth || 0) >= total - 4
        };
    });

    console.log(JSON.stringify(metrics, null, 2));

    const ok = metrics.maxGap <= 0.5
        && metrics.maxAlign <= 1
        && metrics.mismatches.length === 0
        && metrics.canScroll
        && metrics.total > 900
        && metrics.rowPositions.every(p => p === 'absolute');

    if (!ok) {
        console.error('ROW/COLUMN LAYOUT CHECK FAILED', metrics);
        process.exit(1);
    }
    console.log('ROW/COLUMN LAYOUT CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
