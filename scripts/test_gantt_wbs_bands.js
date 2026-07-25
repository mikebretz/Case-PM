#!/usr/bin/env node
const path = require('path');
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + path.join(__dirname, 'gantt_layout_fixture.html'), { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_task_line');
    await page.waitForTimeout(300);

    await page.evaluate(() => {
        const WBS_GUTTER_COLORS = ['#0070c0', '#00b050', '#ffff00', '#ffc000'];
        const WBS_GUTTER_WIDTH = 14;
        function isDescendantOf(task, ancestorId) {
            let pid = task.parent;
            while (pid != null && pid !== 0 && pid !== '0') {
                if (String(pid) === String(ancestorId)) return true;
                pid = gantt.getTask(pid).parent;
            }
            return String(task.id) === String(ancestorId);
        }
        function getSubtreeEndIdx(items, startIdx) {
            const { task, level } = items[startIdx];
            let endIdx = startIdx;
            for (let j = startIdx + 1; j < items.length; j++) {
                if (isDescendantOf(items[j].task, task.id)) endIdx = j;
                else if (items[j].level <= level) break;
            }
            return endIdx;
        }
        function computeWbsBandSegments(items) {
            const segments = [];
            const projIdx = items.findIndex(it => it.task.type === 'project');
            if (projIdx >= 0) {
                segments.push({ level: 0, startIdx: projIdx, endIdx: items.length - 1, color: WBS_GUTTER_COLORS[0] });
            }
            for (let i = 0; i < items.length; i++) {
                const { task, level } = items[i];
                if (level < 1 || gantt.hasChild(task.id) === false && task.type !== 'project') continue;
                if (!(task.type === 'project' || gantt.hasChild(task.id))) continue;
                const bandLevel = Math.min(level, WBS_GUTTER_COLORS.length - 1);
                segments.push({ level: bandLevel, startIdx: i, endIdx: getSubtreeEndIdx(items, i), color: WBS_GUTTER_COLORS[bandLevel] });
            }
            return segments;
        }
        const gridData = document.querySelector('#gantt_here .gantt_grid_data');
        let layer = gridData.querySelector('.sched-wbs-gutter-layer');
        if (!layer) {
            layer = document.createElement('div');
            layer.className = 'sched-wbs-gutter-layer';
            gridData.appendChild(layer);
        }
        const rows = [...gridData.querySelectorAll('.gantt_row')];
        const items = rows.map(row => {
            const id = gantt.locate(row);
            const task = gantt.getTask(id);
            return { row, task, level: task.$level };
        });
        const segments = computeWbsBandSegments(items);
        layer.innerHTML = '';
        segments.forEach(seg => {
            const startRow = items[seg.startIdx].row;
            const endRow = items[seg.endIdx].row;
            const top = startRow.offsetTop;
            const height = endRow.offsetTop + endRow.offsetHeight - startRow.offsetTop;
            const band = document.createElement('div');
            band.className = 'sched-wbs-band';
            band.style.cssText = `position:absolute;top:${top}px;left:${seg.level * WBS_GUTTER_WIDTH}px;width:${WBS_GUTTER_WIDTH}px;height:${height}px;background:${seg.color}`;
            layer.appendChild(band);
        });
        window.__wbsTest = { segmentCount: segments.length, bands: [...layer.querySelectorAll('.sched-wbs-band')].map(b => ({
            level: b.dataset.wbsLevel,
            height: b.offsetHeight,
            color: b.style.background || b.style.backgroundColor
        })) };
    });

    const result = await page.evaluate(() => window.__wbsTest);
    console.log(JSON.stringify(result, null, 2));
    const blue = await page.$('.sched-wbs-band[style*="#0070c0"], .sched-wbs-band[style*="rgb(0, 112, 192)"]');
    if (!result || result.segmentCount < 2 || !blue) process.exit(1);
    await browser.close();
})();
