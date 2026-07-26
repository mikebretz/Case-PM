#!/usr/bin/env node
/**
 * Print predecessor link overlay alignment checks.
 * Run: node scripts/test_gantt_print_link_align.js
 */
const path = require('path');
const { chromium } = require('playwright');

const FIXTURE = path.join(__dirname, 'gantt_print_link_fixture.html');

async function main() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
    await page.goto('file://' + FIXTURE, { waitUntil: 'load' });
    await page.waitForTimeout(100);

    const metrics = await page.evaluate(() => {
        const wrap = document.querySelector('.print-schedule-wrap');
        const table = wrap.querySelector('.schedule-print-table');
        const svg = wrap.querySelector('.print-inline-links');
        const barCell = table.querySelector('tbody .print-bar-cell');
        const wrapRect = wrap.getBoundingClientRect();
        const tableRect = table.getBoundingClientRect();
        const barRect = barCell.getBoundingClientRect();
        const svgRect = svg.getBoundingClientRect();
        const rowY = window.__printLinkRowY;
        const expectedY0 = rowY(0);
        const row0 = table.querySelector('tbody tr');
        const row0Rect = row0.getBoundingClientRect();
        const row0CenterPct = ((row0Rect.top + row0Rect.height / 2) - tableRect.top) / tableRect.height * 100;
        return {
            pathCount: window.__printLinkPathCount || svg.querySelectorAll('path').length,
            leftDelta: Math.abs(svgRect.left - barRect.left),
            widthDelta: Math.abs(svgRect.width - barRect.width),
            heightDelta: Math.abs(svgRect.height - tableRect.height),
            rowY0: expectedY0,
            row0CenterPct,
            rowYDelta: Math.abs(expectedY0 - row0CenterPct)
        };
    });

    console.log(JSON.stringify(metrics, null, 2));

    const ok = metrics.pathCount >= 1
        && metrics.leftDelta <= 1
        && metrics.widthDelta <= 1
        && metrics.heightDelta <= 1
        && metrics.rowYDelta <= 1.5;

    if (!ok) {
        console.error('PRINT LINK ALIGN CHECK FAILED', metrics);
        process.exit(1);
    }
    console.log('PRINT LINK ALIGN CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
