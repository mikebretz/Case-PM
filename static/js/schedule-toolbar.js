/**
 * Case PM — customizable schedule toolbar (main bar + overflow menu).
 */
(function (global) {
  'use strict';

  const STORAGE_KEY = 'casepm_schedule_toolbar_visible';

  const TOOL_DEFS = [
    { id: 'undo', label: 'Undo', group: 'history', defaultOnBar: true },
    { id: 'redo', label: 'Redo', group: 'history', defaultOnBar: true },
    { id: 'add-activity', label: 'Add Activity', group: 'edit', defaultOnBar: true },
    { id: 'add-milestone', label: 'Add Milestone', group: 'edit', defaultOnBar: true },
    { id: 'duplicate', label: 'Duplicate', group: 'edit', defaultOnBar: true },
    { id: 'delete', label: 'Delete', group: 'edit', defaultOnBar: true },
    { id: 'indent', label: 'Indent', group: 'structure', defaultOnBar: true },
    { id: 'outdent', label: 'Outdent', group: 'structure', defaultOnBar: true },
    { id: 'align', label: 'Cell Alignment & Font', group: 'format', defaultOnBar: true },
    { id: 'link-fs', label: 'Link FS', group: 'links', defaultOnBar: true },
    { id: 'link-ss', label: 'Link SS', group: 'links', defaultOnBar: false },
    { id: 'link-ff', label: 'Link FF', group: 'links', defaultOnBar: false },
    { id: 'link-sf', label: 'Link SF', group: 'links', defaultOnBar: false },
    { id: 'unlink', label: 'Unlink', group: 'links', defaultOnBar: true },
    { id: 'run-schedule', label: 'Schedule (CPM)', group: 'schedule', defaultOnBar: true },
    { id: 'critical-path', label: 'Critical Path', group: 'schedule', defaultOnBar: true },
    { id: 'set-baseline', label: 'Set Baseline', group: 'schedule', defaultOnBar: false },
    { id: 'baselines', label: 'Baselines', group: 'schedule', defaultOnBar: false },
    { id: 'resources', label: 'Resources', group: 'schedule', defaultOnBar: false },
    { id: 'timescale', label: 'Timescale & Zoom', group: 'view', defaultOnBar: true },
    { id: 'pan-prev', label: 'Previous Month', group: 'view', defaultOnBar: false },
    { id: 'pan-next', label: 'Next Month', group: 'view', defaultOnBar: false },
    { id: 'fit-view', label: 'Fit View', group: 'view', defaultOnBar: true },
    { id: 'today', label: 'Today', group: 'view', defaultOnBar: true },
    { id: 'critical-filter', label: 'Critical Only', group: 'view', defaultOnBar: false },
    { id: 'sort', label: 'Sort by Start', group: 'view', defaultOnBar: false },
    { id: 'export-csv', label: 'Export CSV', group: 'export', defaultOnBar: false },
    { id: 'export-xer', label: 'Export XER', group: 'export', defaultOnBar: false },
    { id: 'export-xml', label: 'Export XML', group: 'export', defaultOnBar: false },
    { id: 'display', label: 'Display Settings', group: 'view', defaultOnBar: false },
    { id: 'theme', label: 'Light/Dark Theme', group: 'view', defaultOnBar: false },
    { id: 'scurve', label: 'S-Curve', group: 'analysis', defaultOnBar: false },
    { id: 'histogram', label: 'Histogram', group: 'analysis', defaultOnBar: false },
    { id: 'reset-calendar', label: 'Reset Calendar', group: 'view', defaultOnBar: false },
    { id: 'all-fields', label: 'All Fields', group: 'columns', defaultOnBar: false },
    { id: 'columns', label: 'Column Manager', group: 'columns', defaultOnBar: false },
  ];

  let visibleOnBar = null;
  let moreMenuOpen = false;

  function defaultVisible() {
    return TOOL_DEFS.filter(t => t.defaultOnBar).map(t => t.id);
  }

  function loadVisible() {
    if (visibleOnBar) return visibleOnBar;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length) {
          visibleOnBar = parsed;
          return visibleOnBar;
        }
      }
    } catch { /* ignore */ }
    visibleOnBar = defaultVisible();
    return visibleOnBar;
  }

  function saveVisible() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(visibleOnBar));
  }

  function isOnBar(id) {
    return loadVisible().includes(id);
  }

  function applyVisibility() {
    const bar = document.getElementById('scheduleMainToolbar');
    if (!bar) return;
    bar.querySelectorAll('[data-sched-tool]').forEach((el) => {
      const id = el.getAttribute('data-sched-tool');
      if (!id) return;
      const show = isOnBar(id);
      el.classList.toggle('hidden', !show);
      el.setAttribute('aria-hidden', show ? 'false' : 'true');
    });
    bar.querySelectorAll('[data-sched-tool-group]').forEach((group) => {
      const children = group.querySelectorAll('[data-sched-tool]');
      const anyVisible = Array.from(children).some(ch => !ch.classList.contains('hidden'));
      group.classList.toggle('hidden', !anyVisible);
    });
    renderMoreMenu();
  }

  function getOverflowTools() {
    return TOOL_DEFS.filter(t => !isOnBar(t.id));
  }

  function renderMoreMenu() {
    const menu = document.getElementById('scheduleMoreToolsMenu');
    if (!menu) return;
    const overflow = getOverflowTools();
    if (!overflow.length) {
      menu.innerHTML = '<div class="px-3 py-2 text-xs text-zinc-500">All tools are on the toolbar.</div>';
      return;
    }
    const groups = {};
    overflow.forEach(t => {
      if (!groups[t.group]) groups[t.group] = [];
      groups[t.group].push(t);
    });
    let html = '';
    Object.keys(groups).forEach((gk) => {
      html += `<div class="px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-500">${gk}</div>`;
      groups[gk].forEach(t => {
        const el = document.querySelector(`#scheduleMainToolbar [data-sched-tool="${t.id}"]`);
        if (!el) return;
        const clone = el.cloneNode(true);
        clone.classList.remove('hidden');
        clone.removeAttribute('aria-hidden');
        clone.classList.add('schedule-more-tool-clone', 'w-full', 'justify-start');
        html += `<div class="px-1 py-0.5" data-more-tool="${t.id}"></div>`;
      });
    });
    menu.innerHTML = html;
    menu.querySelectorAll('[data-more-tool]').forEach((slot) => {
      const id = slot.getAttribute('data-more-tool');
      const source = document.querySelector(`#scheduleMainToolbar [data-sched-tool="${id}"]`);
      if (!source) return;
      const def = TOOL_DEFS.find(t => t.id === id);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'schedule-toolbar-btn schedule-more-tool-item w-full justify-start';
      btn.innerHTML = source.querySelector('button')?.innerHTML || def?.label || id;
      btn.title = source.querySelector('button')?.title || def?.label || '';
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeMoreMenu();
        const inner = source.querySelector('button');
        if (inner) inner.click();
        else if (source.tagName === 'BUTTON') source.click();
      });
      slot.appendChild(btn);
    });
  }

  function closeMoreMenu() {
    const menu = document.getElementById('scheduleMoreToolsMenu');
    const btn = document.getElementById('scheduleMoreToolsBtn');
    if (menu) menu.classList.add('hidden');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    moreMenuOpen = false;
  }

  function toggleMoreMenu() {
    const menu = document.getElementById('scheduleMoreToolsMenu');
    const btn = document.getElementById('scheduleMoreToolsBtn');
    if (!menu) return;
    moreMenuOpen = !moreMenuOpen;
    if (moreMenuOpen) {
      renderMoreMenu();
      menu.classList.remove('hidden');
      if (btn) btn.setAttribute('aria-expanded', 'true');
    } else {
      closeMoreMenu();
    }
  }

  function showCustomizeDialog() {
    const visible = [...loadVisible()];
    const lines = TOOL_DEFS.map(t => {
      const checked = visible.includes(t.id) ? 'checked' : '';
      return `<label class="flex items-center gap-2 py-1 text-sm text-zinc-200 cursor-pointer">
        <input type="checkbox" data-tool-id="${t.id}" ${checked} class="accent-emerald-500">
        <span>${t.label}</span>
      </label>`;
    }).join('');

    const dialog = document.createElement('dialog');
    dialog.className = 'bg-zinc-900 border border-zinc-700 rounded-lg p-0 text-white max-w-md w-full shadow-2xl';
    dialog.innerHTML = `
      <div class="casepm-drag-handle px-4 py-3 border-b border-zinc-700 flex justify-between items-center cursor-move">
        <div>
          <h3 class="font-semibold text-sm">Customize Toolbar</h3>
          <p class="text-xs text-zinc-500">Checked tools appear on the main bar. Others are in <b>More Tools</b>.</p>
        </div>
        <button type="button" data-close class="text-zinc-400 hover:text-white text-lg">&times;</button>
      </div>
      <div class="p-4 max-h-[50vh] overflow-auto grid grid-cols-1 sm:grid-cols-2 gap-x-4">${lines}</div>
      <div class="px-4 py-3 border-t border-zinc-700 flex justify-between gap-2">
        <button type="button" data-reset class="text-xs text-zinc-400 hover:text-white">Reset defaults</button>
        <div class="flex gap-2">
          <button type="button" data-cancel class="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md">Cancel</button>
          <button type="button" data-save class="px-3 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 rounded-md font-medium">Save</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    if (global.CasePMDialog && global.CasePMDialog.makeDraggable) {
      global.CasePMDialog.makeDraggable(dialog, '.casepm-drag-handle');
    }
    dialog.showModal();
    dialog.querySelector('[data-close]').onclick = () => dialog.close();
    dialog.querySelector('[data-cancel]').onclick = () => dialog.close();
    dialog.querySelector('[data-reset]').onclick = () => {
      dialog.querySelectorAll('input[data-tool-id]').forEach(inp => {
        const def = TOOL_DEFS.find(t => t.id === inp.dataset.toolId);
        inp.checked = def ? def.defaultOnBar : false;
      });
    };
    dialog.querySelector('[data-save]').onclick = () => {
      visibleOnBar = Array.from(dialog.querySelectorAll('input[data-tool-id]:checked')).map(i => i.dataset.toolId);
      if (!visibleOnBar.length) {
        alert('Select at least one tool for the toolbar.');
        return;
      }
      saveVisible();
      applyVisibility();
      dialog.close();
    };
    dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('cancel', (e) => { e.preventDefault(); dialog.close(); });
  }

  function init() {
    loadVisible();
    applyVisibility();
    const moreBtn = document.getElementById('scheduleMoreToolsBtn');
    const customBtn = document.getElementById('scheduleCustomizeToolbarBtn');
    if (moreBtn) moreBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleMoreMenu(); });
    if (customBtn) customBtn.addEventListener('click', showCustomizeDialog);
    document.addEventListener('click', (e) => {
      if (!moreMenuOpen) return;
      const menu = document.getElementById('scheduleMoreToolsMenu');
      const btn = document.getElementById('scheduleMoreToolsBtn');
      if (menu && !menu.contains(e.target) && e.target !== btn && !btn?.contains(e.target)) {
        closeMoreMenu();
      }
    });
  }

  global.ScheduleToolbar = { init, applyVisibility, showCustomizeDialog, TOOL_DEFS };
})(window);
