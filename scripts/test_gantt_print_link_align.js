#!/usr/bin/env node
/**
 * Print predecessor link alignment checks (per-row bar track SVGs).
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

    const metrics = await page.evaluate(() => window.__printLinkMetrics);

    console.log(JSON.stringify(metrics, null, 2));

    const ok = metrics.pathCount >= 2
        && metrics.arrowCount >= 1
        && metrics.row0.svgMatchesTrack
        && metrics.row1.svgMatchesTrack
        && metrics.row0.barLeftPct >= 8
        && metrics.row0.barLeftPct <= 12
        && metrics.row1.barLeftPct >= 43
        && metrics.row1.barLeftPct <= 47;

    if (!ok) {
        console.error('PRINT LINK ALIGN CHECK FAILED', metrics);
        process.exit(1);
    }
    console.log('PRINT LINK ALIGN CHECK PASSED');
    await browser.close();
}

main().catch(e => { console.error(e); process.exit(1); });
