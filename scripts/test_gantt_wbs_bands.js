#!/usr/bin/env node
const path = require('path');
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    await page.goto('file://' + path.join(__dirname, 'gantt_layout_fixture.html'), { waitUntil: 'networkidle' });
    await page.waitForSelector('.gantt_task_line');
    await page.waitForTimeout(300);

    const result = await page.evaluate(() => {
        const WBS_GUTTER_COLORS = ['#0070c0', '#00b050', '#ffff00', '#ffc000'];
        function getWbsLevel(task) {
            const level = Number(task.$level);
            return Number.isFinite(level) ? Math.max(0, level) : 0;
        }
        function isSummaryTask(task) {
            return task && (task.type === 'project' || gantt.hasChild(task.id));
        }
        function taskShowsGutterLevel(task, gutterLevel) {
            if (gutterLevel === 0) return true;
            const maxLevel = WBS_GUTTER_COLORS.length - 1;
            const levelFor = t => Math.min(getWbsLevel(t), maxLevel);
            if (isSummaryTask(task) && levelFor(task) === gutterLevel) return true;
            let pid = task.parent;
            while (pid != null && pid !== 0 && pid !== '0') {
                if (!gantt.isTaskExists(pid)) break;
                const p = gantt.getTask(pid);
                if (isSummaryTask(p) && levelFor(p) === gutterLevel) return true;
                pid = p.parent;
            }
            return false;
        }

        const rows = [...document.querySelectorAll('#gantt_here .gantt_grid_data .gantt_row')];
        const checks = rows.map(row => {
            const id = gantt.locate(row);
            const task = gantt.getTask(id);
            const hierCell = row.querySelector('.sched-hierarchy-cell') || row.querySelector('.gantt_cell');
            const activeSlots = hierCell ? [...hierCell.querySelectorAll('.sched-wbs-slot-active, [class*="sched-wbs-slot"][style*="background"]')] : [];
            const expected = WBS_GUTTER_COLORS.map((_, i) => taskShowsGutterLevel(task, i));
            const expectedCount = expected.filter(Boolean).length;
            return {
                id,
                text: task.text,
                expectedCount,
                activeCount: activeSlots.length,
                blue: taskShowsGutterLevel(task, 0),
                green: taskShowsGutterLevel(task, 1),
                yellow: taskShowsGutterLevel(task, 2)
            };
        });

        return {
            rowChecks: checks,
            allRowsMatch: checks.every(c => c.expectedCount === c.activeCount),
            leafUnderYellow: checks.filter(c => c.yellow && !c.green === false && c.text === 'Project Management')
        };
    });
    console.log(JSON.stringify(result, null, 2));
    if (!result.allRowsMatch) process.exit(1);
    await browser.close();
})();
