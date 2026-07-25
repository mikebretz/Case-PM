#!/usr/bin/env node
/**
 * Verifies grid header cells align with data cells after column layout.
 * Run: node scripts/test_gantt_column_align.js
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_layout_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_row', { timeout: 15000 });
    await page.waitForTimeout(400);

    const before = await page.evaluate(() => {
        const heads = [...document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell')];
        const row = document.querySelector('#gantt_here .gantt_grid_data .gantt_row');
        const cells = row ? [...row.querySelectorAll(':scope > .gantt_cell')] : [];
        const mismatches = [];
        const pairs = Math.min(heads.length, cells.length);
        for (let i = 0; i < pairs; i++) {
            const hl = parseFloat(heads[i].style.left) || heads[i].offsetLeft;
            const cl = parseFloat(cells[i].style.left) || cells[i].offsetLeft;
            const hw = heads[i].offsetWidth;
            const cw = cells[i].offsetWidth;
            if (Math.abs(hl - cl) > 1 || Math.abs(hw - cw) > 2) {
                mismatches.push({ i, hl, cl, hw, cw });
            }
        }
        return { pairs, mismatches, headTotal: heads.reduce((s, h) => s + h.offsetWidth, 0) };
    });

    // Resize a column and re-check
    const grip = page.locator('.gantt_grid_column_resize_wrap').nth(2);
    const box = await grip.boundingBox();
    if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + 60, box.y + box.height / 2);
        await page.mouse.up();
        await page.waitForTimeout(300);
    }

    const after = await page.evaluate(() => {
        const heads = [...document.querySelectorAll('#gantt_here .gantt_grid_scale .gantt_grid_head_cell')];
        const row = document.querySelector('#gantt_here .gantt_grid_data .gantt_row');
        const cells = row ? [...row.querySelectorAll(':scope > .gantt_cell')] : [];
        const mismatches = [];
        const pairs = Math.min(heads.length, cells.length);
        for (let i = 0; i < pairs; i++) {
            const hl = parseFloat(heads[i].style.left) || heads[i].offsetLeft;
            const cl = parseFloat(cells[i].style.left) || cells[i].offsetLeft;
            const hw = heads[i].offsetWidth;
            const cw = cells[i].offsetWidth;
            if (Math.abs(hl - cl) > 1 || Math.abs(hw - cw) > 2) {
                mismatches.push({ i, hl, cl, hw, cw });
            }
        }
        const textCol = gantt.config.columns.find(c => c.name === 'text');
        return { pairs, mismatches, textWidth: textCol?.width };
    });

    console.log(JSON.stringify({ before, after }, null, 2));

    const ok = before.mismatches.length === 0 && after.mismatches.length === 0;
    if (!ok) {
        console.error('COLUMN ALIGN CHECK FAILED');
        process.exit(1);
    }
    console.log('COLUMN ALIGN CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
