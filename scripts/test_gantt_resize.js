const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file:///workspace/scripts/gantt_layout_fixture.html', { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_grid_column_resize_wrap');
    const before = await page.evaluate(() => gantt.config.columns.find(c => c.name === 'text').width);
    const grip = await page.locator('.gantt_grid_column_resize_wrap').first();
    const box = await grip.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + 80, box.y + box.height / 2);
    await page.mouse.up();
    await page.waitForTimeout(300);
    const after = await page.evaluate(() => gantt.config.columns.find(c => c.name === 'text').width);
    console.log(JSON.stringify({ before, after, resized: after > before }));
    if (after <= before) process.exit(1);
    await browser.close();
})();
