/**
 * Case PM — shared log print with field picker (native print preview, no popup window).
 */
(function (global) {
  'use strict';

  const STYLE_ID = 'casepm-print-picker-styles';
  const PRINT_SHEET_STYLE_ID = 'casepm-print-sheet-styles-v2';

  const EMPTY_CELL_VALUES = new Set(['', '—', '-', '–', 'n/a', 'na', 'none', 'null', 'undefined']);

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function normalizePrintCell(value) {
    if (value == null) return '';
    return String(value).replace(/\s+/g, ' ').trim();
  }

  function isEmptyPrintCell(value) {
    const text = normalizePrintCell(value).toLowerCase();
    if (!text || EMPTY_CELL_VALUES.has(text)) return true;
    if (text === '$0' || text === '$0.00' || text === '0%' || text === '0.00%') return true;
    return false;
  }

  /** Short register label — first meaningful phrase / few whole words, not full descriptions. */
  function logPhrase(value, maxWords) {
    const text = normalizePrintCell(value);
    if (!text) return '';
    const limit = maxWords || 4;
    const clause = text.split(/\s*[.;]\s+|\s+—\s+|\n+/)[0].trim();
    const words = clause.split(/\s+/).filter(Boolean);
    if (!words.length) return '';
    const phrase = words.slice(0, limit).join(' ');
    if (words.length > limit) return `${phrase}…`;
    return phrase;
  }

  function truncatePrintText(value, maxLen) {
    const text = normalizePrintCell(value);
    const limit = maxLen || 48;
    if (text.length <= limit) return text;
    const slice = text.slice(0, limit);
    const lastSpace = slice.lastIndexOf(' ');
    const trimmed = (lastSpace > 12 ? slice.slice(0, lastSpace) : slice).trimEnd();
    return `${trimmed}…`;
  }

  function formatPrintCell(value, column) {
    if (column.check || column.mono) return value ?? '';
    if (column.logPhrase) return logPhrase(value, column.logWords || 4);
    if (column.maxLen) return truncatePrintText(value, column.maxLen);
    if (column.clamp === false) return value ?? '';
    const text = normalizePrintCell(value);
    if (text.length > 56) return truncatePrintText(text, 56);
    return text;
  }

  function pruneEmptyColumns(columns, rows) {
    return columns.filter((col) => {
      if (col.alwaysShow || col.check) return true;
      return rows.some((row) => {
        const raw = typeof col.format === 'function' ? col.format(row) : (row[col.key] ?? '');
        return !isEmptyPrintCell(formatPrintCell(raw, col));
      });
    });
  }

  function rebalanceColumnWidths(columns) {
    if (!columns.length) return columns;
    const total = columns.reduce((sum, col) => sum + (parseFloat(col.width) || 0), 0) || columns.length;
    return columns.map((col) => {
      const pct = parseFloat(col.width);
      const width = pct ? `${Math.max(4, Math.round((pct / total) * 100))}%` : `${Math.round(100 / columns.length)}%`;
      return { ...col, width };
    });
  }

  /** Shared ALDI-style project header meta for all log prints. */
  function getProjectMeta() {
    const shell = document.body;
    const nameEl = document.getElementById('currentProjectName');
    const name = (shell.dataset.activeProjectName || (nameEl?.textContent || '').trim() || global.CASEPM_ACTIVE_PROJECT_NAME || 'Project');
    const number = shell.dataset.activeProjectNumber
      || shell.dataset.activeProjectId
      || (global.CASEPM_ACTIVE_PROJECT_ID ? String(global.CASEPM_ACTIVE_PROJECT_ID) : '');
    const location = shell.dataset.activeProjectAddress || '';
    return { name, number, location };
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      dialog.casepm-print-picker {
        margin: auto !important;
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        border: none;
        padding: 0;
        background: transparent;
        color: #fff;
        max-width: min(560px, 94vw);
        width: min(560px, 94vw);
        z-index: 1000001;
      }
      dialog.casepm-print-picker::backdrop { background: rgba(0,0,0,0.72); }
      .casepm-print-picker-panel {
        background: #18181b;
        border: 1px solid #3f3f46;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 25px 50px -12px rgba(0,0,0,0.55);
      }
      .casepm-print-picker-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        padding: 1rem 1.25rem;
        border-bottom: 1px solid #3f3f46;
        font-weight: 600;
        cursor: move;
      }
      .casepm-print-picker-body { padding: 1rem 1.25rem; max-height: 55vh; overflow: auto; }
      .casepm-print-picker-actions {
        display: flex;
        justify-content: flex-end;
        gap: 0.5rem;
        padding: 0.875rem 1.25rem;
        background: #09090b;
        border-top: 1px solid #3f3f46;
      }
      .casepm-print-field-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.35rem 1rem;
      }
      .casepm-print-field-grid label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.8125rem;
        color: #d4d4d8;
        cursor: pointer;
      }
      .casepm-print-field-note {
        font-size: 0.75rem;
        color: #a1a1aa;
        margin-bottom: 0.75rem;
        line-height: 1.4;
      }
      .casepm-print-log-types {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
      }
      .casepm-print-log-types label {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.8125rem;
        color: #d4d4d8;
        cursor: pointer;
        padding: 0.35rem 0.65rem;
        background: #27272a;
        border: 1px solid #3f3f46;
        border-radius: 0.375rem;
      }
      .casepm-print-toolbar {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
        flex-wrap: wrap;
      }
      .casepm-print-toolbar button {
        font-size: 0.75rem;
        padding: 0.25rem 0.65rem;
        border-radius: 0.375rem;
        border: 1px solid #3f3f46;
        background: #27272a;
        color: #e4e4e7;
        cursor: pointer;
      }
      .casepm-print-toolbar button:hover { background: #3f3f46; }
      .casepm-print-root { display: none; }
    `;
    document.head.appendChild(style);
  }

  function ensurePrintSheetStyles(bodyClass) {
    const existing = document.getElementById(PRINT_SHEET_STYLE_ID);
    if (existing) existing.remove();
    const cls = bodyClass || 'casepm-printing';
    const style = document.createElement('style');
    style.id = PRINT_SHEET_STYLE_ID;
    style.textContent = `
      @media print {
        @page { size: landscape; margin: 0.35in 0.5in 0.35in 0.4in; }
        body.${cls},
        body.casepm-printing,
        body.printing-submittal-log,
        body.printing-co-log,
        body.printing-rfi-log,
        body.printing-daily-log,
        body.printing-weekly-log,
        body.printing-budget-log {
          background: #fff !important;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        body.${cls} #appShell > #appHeaderBar,
        body.${cls} #appSidebar,
        body.${cls} #appFooterBar,
        body.${cls} #appShell > .flex.flex-1 > div.h-10,
        body.${cls} #submittalChrome,
        body.${cls} .co-page,
        body.${cls} #scheduleChrome,
        body.${cls} .no-print,
        body.casepm-printing #appShell > #appHeaderBar,
        body.casepm-printing #appSidebar,
        body.casepm-printing #appFooterBar,
        body.casepm-printing #appShell > .flex.flex-1 > div.h-10,
        body.casepm-printing #submittalChrome,
        body.casepm-printing .co-page,
        body.casepm-printing #scheduleChrome,
        body.casepm-printing .no-print,
        body.printing-submittal-log #appShell > #appHeaderBar,
        body.printing-submittal-log #appSidebar,
        body.printing-submittal-log #appFooterBar,
        body.printing-submittal-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-submittal-log #submittalChrome,
        body.printing-submittal-log .no-print,
        body.printing-co-log #appShell > #appHeaderBar,
        body.printing-co-log #appSidebar,
        body.printing-co-log #appFooterBar,
        body.printing-co-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-co-log .co-page,
        body.printing-co-log #coDetailDrawer,
        body.printing-co-log .fixed.bottom-0,
        body.printing-co-log dialog,
        body.printing-co-log .no-print,
        body.printing-rfi-log #appShell > #appHeaderBar,
        body.printing-rfi-log #appSidebar,
        body.printing-rfi-log #appFooterBar,
        body.printing-rfi-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-rfi-log .rfi-page,
        body.printing-rfi-log #rfiDetailDrawer,
        body.printing-rfi-log #rfiDrawerBackdrop,
        body.printing-rfi-log .fixed.bottom-0,
        body.printing-rfi-log dialog,
        body.printing-rfi-log .no-print,
        body.printing-rfi-detail #appShell > #appHeaderBar,
        body.printing-rfi-detail #appSidebar,
        body.printing-rfi-detail #appFooterBar,
        body.printing-rfi-detail #appShell > .flex.flex-1 > div.h-10,
        body.printing-rfi-detail .rfi-page,
        body.printing-rfi-detail #rfiDetailDrawer,
        body.printing-rfi-detail #rfiDrawerBackdrop,
        body.printing-rfi-detail .fixed.bottom-0,
        body.printing-rfi-detail dialog,
        body.printing-rfi-detail .no-print,
        body.printing-daily-log #appShell > #appHeaderBar,
        body.printing-daily-log #appSidebar,
        body.printing-daily-log #appFooterBar,
        body.printing-daily-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-daily-log .dlog-page > *:not(#dlogPrintSheet),
        body.printing-daily-log #dlogModal,
        body.printing-daily-log #dlogDetailModal,
        body.printing-daily-log #dlogCameraModal,
        body.printing-daily-log .no-print,
        body.printing-weekly-log #appShell > #appHeaderBar,
        body.printing-weekly-log #appSidebar,
        body.printing-weekly-log #appFooterBar,
        body.printing-weekly-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-weekly-log .wlog-page > *:not(#wlogPrintSheet),
        body.printing-weekly-log #wlogModal,
        body.printing-weekly-log #wlogDetailModal,
        body.printing-weekly-log .no-print {
          display: none !important;
        }
        body.${cls} #mainContent,
        body.casepm-printing #mainContent,
        body.printing-submittal-log #mainContent,
        body.printing-co-log #mainContent,
        body.printing-rfi-log #mainContent,
        body.printing-daily-log #mainContent,
        body.printing-weekly-log #mainContent {
          padding: 0 !important;
          overflow: visible !important;
          display: block !important;
        }
        body.${cls} #casepmPrintRoot,
        body.${cls} #submittalPrintSheet,
        body.${cls} #coPrintSheet,
        body.casepm-printing #casepmPrintRoot,
        body.casepm-printing #submittalPrintSheet,
        body.casepm-printing #coPrintSheet,
        body.printing-submittal-log #submittalPrintSheet,
        body.printing-co-log #coPrintSheet,
        body.printing-rfi-log #rfiPrintSheet,
        body.printing-rfi-detail #rfiPrintSheet,
        body.printing-daily-log #dlogPrintSheet,
        body.printing-weekly-log #wlogPrintSheet,
        body.printing-budget-log #budgetPrintSheet {
          display: block !important;
          background: #fff !important;
          color: #111 !important;
          font-family: Arial, Helvetica, sans-serif;
          font-size: 7pt;
        }
        body.printing-rfi-detail,
        body.printing-budget-log {
          background: #fff !important;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        body.printing-rfi-detail #mainContent,
        body.printing-budget-log #mainContent {
          padding: 0 !important;
          overflow: visible !important;
          display: block !important;
        }
        body.printing-budget-log #appShell > #appHeaderBar,
        body.printing-budget-log #appSidebar,
        body.printing-budget-log #appFooterBar,
        body.printing-budget-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-budget-log .budget-page,
        body.printing-budget-log #sageSyncStatusBar,
        body.printing-budget-log .no-print,
        body.printing-budget-log dialog {
          display: none !important;
        }
        body.printing-co-log #sageSyncStatusBar,
        body.printing-rfi-log #sageSyncStatusBar,
        body.printing-submittal-log #sageSyncStatusBar {
          display: none !important;
        }
        .casepm-print-page, .submittal-print-page {
          page-break-after: always;
          break-after: page;
        }
        .casepm-print-page:last-child, .submittal-print-page:last-child {
          page-break-after: auto;
          break-after: auto;
        }
        .casepm-print-header, .submittal-print-header {
          margin-bottom: 6px;
          border-bottom: 2px solid #111;
          padding-bottom: 6px;
        }
        .casepm-print-header-table, .submittal-print-header-table {
          width: 100%;
          border-collapse: collapse;
        }
        .casepm-print-header-table td, .submittal-print-header-table td {
          border: none;
          vertical-align: top;
          padding: 0;
        }
        .casepm-print-header-left, .submittal-print-header-left { padding-right: 12px; }
        .casepm-print-header-right, .submittal-print-header-right {
          text-align: right;
          width: 34%;
          padding-left: 10px;
          white-space: normal;
          word-break: normal;
          overflow-wrap: normal;
        }
        .casepm-print-title, .submittal-print-title {
          font-size: 12pt;
          font-weight: 700;
          letter-spacing: 0.4px;
          color: #111;
          line-height: 1.15;
        }
        .casepm-print-meta, .submittal-print-meta {
          text-align: right;
          font-size: 6.5pt;
          line-height: 1.35;
          color: #222;
          word-break: normal;
          overflow-wrap: normal;
        }
        .casepm-print-meta > div, .submittal-print-meta > div {
          margin-bottom: 3px;
        }
        .casepm-print-meta .label, .submittal-print-meta .label {
          font-weight: 700;
          text-transform: uppercase;
          font-size: 6pt;
          color: #444;
        }
        .casepm-print-table, .submittal-print-table {
          width: 100%;
          border-collapse: collapse;
          table-layout: fixed;
          font-size: 6pt;
          line-height: 1.15;
        }
        .casepm-print-table th, .casepm-print-table td,
        .submittal-print-table th, .submittal-print-table td {
          border: 1px solid #333;
          padding: 2px 3px;
          vertical-align: middle;
          word-break: normal;
          overflow-wrap: normal;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .casepm-print-table th, .submittal-print-table th {
          background: #f0f0f0;
          font-weight: 700;
          text-align: center;
          font-size: 5pt;
          text-transform: uppercase;
          line-height: 1.1;
          padding: 3px 2px;
          white-space: normal;
        }
        .casepm-print-table td.c, .submittal-print-table td.c { text-align: center; }
        .casepm-print-table td.r, .submittal-print-table td.r { text-align: right; }
        .casepm-print-table td.mono, .submittal-print-table td.mono {
          font-family: 'Courier New', Courier, monospace;
          font-size: 6pt;
        }
        .casepm-print-table .check, .submittal-print-table .check {
          font-weight: 700;
          font-size: 8pt;
          text-align: center;
        }
        .casepm-print-footer, .submittal-print-footer {
          display: grid;
          grid-template-columns: 1fr auto 1fr;
          align-items: center;
          margin-top: 8px;
          padding-top: 4px;
          border-top: 1px solid #999;
          font-size: 7pt;
          color: #444;
        }
        .casepm-print-footer .center, .submittal-print-footer .center { text-align: center; }
        .casepm-print-footer .right, .submittal-print-footer .right { text-align: right; }
        .casepm-print-section-title {
          font-size: 11pt;
          font-weight: 700;
          margin: 12px 0 6px;
          color: #111;
        }
        .casepm-log-report { font-size: 9pt; line-height: 1.45; color: #111; }
        .casepm-log-report h3 {
          font-size: 8pt;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #555;
          margin: 12px 0 4px;
          font-weight: 700;
        }
        .casepm-log-report .casepm-log-line { margin: 2px 0; }
        .casepm-log-report .casepm-log-meta { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 10px; font-size: 8.5pt; color: #333; }
        .casepm-log-report .casepm-log-block { margin-bottom: 8px; white-space: pre-wrap; }
        .casepm-rfi-detail {
          font-size: 9pt;
          line-height: 1.45;
          color: #111;
        }
        .casepm-rfi-detail .rfi-detail-number {
          font-family: 'Courier New', Courier, monospace;
          font-size: 11pt;
          font-weight: 700;
          color: #111;
          margin-bottom: 2px;
        }
        .casepm-rfi-detail .rfi-detail-subject {
          font-size: 12pt;
          font-weight: 700;
          margin-bottom: 10px;
          color: #111;
        }
        .casepm-rfi-detail .rfi-detail-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px 12px;
          margin-bottom: 12px;
          font-size: 8pt;
        }
        .casepm-rfi-detail .rfi-detail-grid .label {
          display: block;
          font-size: 6.5pt;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #666;
          font-weight: 700;
          margin-bottom: 1px;
        }
        .casepm-rfi-detail .rfi-detail-box {
          border: 1px solid #333;
          padding: 8px 10px;
          margin-bottom: 10px;
          white-space: pre-wrap;
          min-height: 48px;
        }
        .casepm-rfi-detail .rfi-detail-box h4 {
          margin: 0 0 4px;
          font-size: 7pt;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #555;
        }
        .casepm-rfi-detail .rfi-detail-list {
          margin: 0;
          padding-left: 16px;
          font-size: 8pt;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function showFieldPicker(options) {
    ensureStyles();
    const fields = options.fields || [];
    const logTypes = options.logTypes || null;
    const title = options.title || 'Print Log';
    const defaultLogType = options.defaultLogType || (logTypes ? logTypes[0].value : null);
    const note = options.note || '';

    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = 'casepm-print-picker';
      const logTypeHtml = logTypes ? `
        <div class="casepm-print-log-types">
          ${logTypes.map((lt, i) => `
            <label><input type="radio" name="casepmPrintLogType" value="${esc(lt.value)}" ${i === 0 ? 'checked' : ''}> ${esc(lt.label)}</label>
          `).join('')}
        </div>` : '';

      dialog.innerHTML = `
        <div class="casepm-print-picker-panel">
          <div class="casepm-print-picker-title casepm-drag-handle">
            <span><i class="fa-solid fa-print text-emerald-400 mr-2"></i>${esc(title)}</span>
            <button type="button" data-action="close" class="text-zinc-400 hover:text-white bg-transparent border-0 cursor-pointer text-lg">&times;</button>
          </div>
          <div class="casepm-print-picker-body">
            ${logTypeHtml}
            ${note ? `<p class="casepm-print-field-note">${esc(note)}</p>` : ''}
            <div class="casepm-print-toolbar">
              <button type="button" data-action="all">Select All</button>
              <button type="button" data-action="none">Clear All</button>
              <button type="button" data-action="default">Defaults</button>
            </div>
            <div class="casepm-print-field-grid">
              ${fields.map(f => `
                <label><input type="checkbox" data-field="${esc(f.key)}" ${f.default !== false ? 'checked' : ''}${f.locked ? ' disabled checked' : ''}> ${esc(f.label)}</label>
              `).join('')}
            </div>
          </div>
          <div class="casepm-print-picker-actions">
            <button type="button" data-action="cancel" class="casepm-dialog-btn casepm-dialog-btn-secondary" style="padding:0.5rem 1rem;border-radius:0.375rem;border:none;cursor:pointer;background:#3f3f46;color:#e4e4e7;">Cancel</button>
            <button type="button" data-action="print" class="casepm-dialog-btn casepm-dialog-btn-primary" style="padding:0.5rem 1rem;border-radius:0.375rem;border:none;cursor:pointer;background:#059669;color:#fff;"><i class="fa-solid fa-arrow-right mr-1"></i> ${global.CasePMOutput ? 'Continue' : 'Print'}</button>
          </div>
        </div>`;

      document.body.appendChild(dialog);
      if (global.CasePMDialog && global.CasePMDialog.makeDraggable) {
        global.CasePMDialog.makeDraggable(dialog, '.casepm-drag-handle');
      }
      dialog.showModal();

      const boxes = () => Array.from(dialog.querySelectorAll('input[data-field]'));
      const finish = (result) => { dialog.close(); dialog.remove(); resolve(result); };

      dialog.querySelector('[data-action="all"]').onclick = () => boxes().forEach(b => { if (!b.disabled) b.checked = true; });
      dialog.querySelector('[data-action="none"]').onclick = () => boxes().forEach(b => { if (!b.disabled) b.checked = false; });
      dialog.querySelector('[data-action="default"]').onclick = () => {
        boxes().forEach(b => {
          const f = fields.find(x => x.key === b.dataset.field);
          if (!b.disabled) b.checked = f ? f.default !== false : true;
        });
      };
      dialog.querySelector('[data-action="close"]').onclick = () => finish(null);
      dialog.querySelector('[data-action="cancel"]').onclick = () => finish(null);
      dialog.querySelector('[data-action="print"]').onclick = () => {
        const selected = boxes().filter(b => b.checked).map(b => b.dataset.field);
        if (!selected.length) {
          if (global.CasePMDialog) global.CasePMDialog.alert('Select at least one field to print.');
          else alert('Select at least one field to print.');
          return;
        }
        const logTypeEl = dialog.querySelector('input[name="casepmPrintLogType"]:checked');
        finish({
          fields: selected,
          logType: logTypeEl ? logTypeEl.value : defaultLogType,
        });
      };
      dialog.addEventListener('cancel', (e) => { e.preventDefault(); finish(null); });
    });
  }

  function buildPrintTable(columns, rows, emptyMessage) {
    const activeColumns = rebalanceColumnWidths(pruneEmptyColumns(columns, rows));
    if (!rows.length) {
      const span = Math.max(activeColumns.length, 1);
      return `<table class="casepm-print-table"><tbody><tr><td colspan="${span}" style="text-align:center;padding:16px;color:#666">${esc(emptyMessage || 'No records to print.')}</td></tr></tbody></table>`;
    }
    const head = activeColumns.map(c => `<th${c.width ? ` style="width:${c.width}"` : ''}>${c.label}</th>`).join('');
    const body = rows.map(row => {
      const cells = activeColumns.map(c => {
        const raw = typeof c.format === 'function' ? c.format(row) : (row[c.key] ?? '');
        const val = formatPrintCell(raw, c);
        let cls = '';
        if (c.check) cls = ' class="check"';
        else if (c.mono) cls = ' class="mono' + (c.align === 'center' ? ' c"' : '"');
        else if (c.align === 'center') cls = ' class="c"';
        else if (c.align === 'right') cls = ' class="r"';
        return `<td${cls}>${esc(val)}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
    return `<table class="casepm-print-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function buildPrintHeaderHtml(meta, title) {
    const loc = meta.location
      ? `<div style="margin-top:4px;font-size:6.5pt"><span class="label" style="font-weight:700">LOCATION</span><br>${esc(meta.location)}</div>`
      : '';
    return `<div class="casepm-print-header">
      <table class="casepm-print-header-table"><tr>
        <td class="casepm-print-header-left">
          <div class="casepm-print-title">${esc(title)}</div>
          ${loc}
        </td>
        <td class="casepm-print-header-right">
          <div class="casepm-print-meta">
            ${meta.number ? `<div><span class="label">PROJECT ID</span><br>${esc(meta.number)}</div>` : ''}
            ${meta.name ? `<div><span class="label">PROJECT NAME</span><br>${esc(meta.name)}</div>` : ''}
          </div>
        </td>
      </tr></table>
    </div>`;
  }

  function buildPrintDocument(opts) {
    const meta = opts.meta || {};
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const sections = opts.sections || [{ title: opts.title, tableHtml: opts.tableHtml }];
    const pages = [];
    const ROWS_PER_PAGE = opts.rowsPerPage || 28;

    sections.forEach(section => {
      const rows = section.rows || [];
      const columns = rebalanceColumnWidths(pruneEmptyColumns(section.columns || [], rows));
      if (!rows.length) {
        pages.push(buildPageBlock(meta, section.title, buildPrintTable(columns, [], section.emptyMessage), printedOn, 1, 1));
        return;
      }
      const totalPages = Math.ceil(rows.length / ROWS_PER_PAGE);
      for (let p = 0; p < totalPages; p++) {
        const chunk = rows.slice(p * ROWS_PER_PAGE, (p + 1) * ROWS_PER_PAGE);
        const tableHtml = buildPrintTable(columns, chunk);
        pages.push(buildPageBlock(meta, section.title, tableHtml, printedOn, p + 1, totalPages, p > 0));
      }
    });

    return pages.map((p) => `<div class="casepm-print-page">${p}</div>`).join('');
  }

  function buildPageBlock(meta, title, tableHtml, printedOn, pageNum, totalPages, sectionContinued) {
    const sectionNote = sectionContinued ? `<div class="casepm-print-section-title">${esc(title)} (continued)</div>` : '';
    return `
      ${buildPrintHeaderHtml(meta, title)}
      ${sectionNote}
      ${tableHtml}
      <div class="casepm-print-footer">
        <span>Confidential</span>
        <span class="center">${esc(printedOn)}</span>
        <span class="right">Page ${pageNum}${totalPages > 1 ? ` of ${totalPages}` : ''}</span>
      </div>`;
  }

  function ensurePrintContainer(containerId) {
    let container = document.getElementById(containerId);
    if (!container) {
      container = document.createElement('div');
      container.id = containerId;
      container.className = 'casepm-print-root';
      container.setAttribute('aria-hidden', 'true');
      document.body.appendChild(container);
    }
    return container;
  }

  /** Portrait document print (individual RFI, etc.) in an isolated iframe. */
  function printPortraitDocument(bodyHtml, docTitle) {
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(docTitle || 'Print')}</title>
      <style>
        @page { size: portrait; margin: 0.45in 0.5in; }
        body { margin: 0; font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        .casepm-print-page { page-break-after: always; break-after: page; }
        .casepm-print-page:last-child { page-break-after: auto; break-after: auto; }
        .casepm-print-header { display: grid; grid-template-columns: 1fr minmax(0, 2.4in); gap: 10px 14px; align-items: start; margin-bottom: 6px; border-bottom: 2px solid #111; padding-bottom: 6px; }
        .casepm-print-title { font-size: 12pt; font-weight: 700; letter-spacing: 0.4px; color: #111; line-height: 1.15; }
        .casepm-print-meta { text-align: right; font-size: 6.5pt; line-height: 1.35; color: #222; word-break: normal; overflow-wrap: normal; }
        .casepm-print-meta .label { font-weight: 700; text-transform: uppercase; font-size: 6pt; color: #444; }
        .casepm-print-footer { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; margin-top: 8px; padding-top: 4px; border-top: 1px solid #999; font-size: 7pt; color: #444; }
        .casepm-print-footer .center { text-align: center; }
        .casepm-print-footer .right { text-align: right; }
        .casepm-rfi-detail { font-size: 9pt; line-height: 1.45; color: #111; }
        .casepm-rfi-detail .rfi-detail-number { font-family: 'Courier New', Courier, monospace; font-size: 11pt; font-weight: 700; margin-bottom: 2px; }
        .casepm-rfi-detail .rfi-detail-subject { font-size: 12pt; font-weight: 700; margin-bottom: 10px; }
        .casepm-rfi-detail .rfi-detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px 12px; margin-bottom: 12px; font-size: 8pt; }
        .casepm-rfi-detail .rfi-detail-grid .label { display: block; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.04em; color: #666; font-weight: 700; margin-bottom: 1px; }
        .casepm-rfi-detail .rfi-detail-box { border: 1px solid #333; padding: 8px 10px; margin-bottom: 10px; white-space: pre-wrap; min-height: 48px; }
        .casepm-rfi-detail .rfi-detail-box h4 { margin: 0 0 4px; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.05em; color: #555; }
        .casepm-rfi-detail .rfi-detail-list { margin: 0; padding-left: 16px; font-size: 8pt; }
      </style></head><body>${bodyHtml.replace('__PRINTED_ON__', esc(printedOn))}</body></html>`;
    printHtmlInIframe(html, { landscape: false, delay: 400 });
  }

  /** Print self-contained HTML in a sized off-screen iframe (G702/G703, etc.). */
  function printHtmlInIframe(html, options) {
    const opts = options || {};
    const landscape = opts.landscape !== false;
    const delay = opts.delay || 500;
    const iframe = document.createElement('iframe');
    iframe.setAttribute('aria-hidden', 'true');
    iframe.style.cssText = [
      'position:fixed',
      'left:-10000px',
      'top:0',
      landscape ? 'width:11in' : 'width:8.5in',
      landscape ? 'height:8.5in' : 'height:11in',
      'border:0',
      'visibility:hidden',
    ].join(';');
    document.body.appendChild(iframe);
    const win = iframe.contentWindow;
    const doc = win.document;
    doc.open();
    doc.write(html);
    doc.close();
    setTimeout(() => {
      try {
        win.focus();
        win.print();
      } finally {
        setTimeout(() => iframe.remove(), 900);
      }
    }, delay);
  }

  /** Opens the browser print preview directly — no new tab/window. */
  function triggerPrintPreview(bodyHtml, options) {
    ensureStyles();
    const opts = options || {};
    const containerId = opts.containerId || 'casepmPrintRoot';
    const bodyClass = opts.bodyClass || 'casepm-printing';
    ensurePrintSheetStyles(bodyClass);
    const container = ensurePrintContainer(containerId);
    container.innerHTML = bodyHtml;
    document.body.classList.add(bodyClass);
    const cleanup = () => {
      document.body.classList.remove(bodyClass);
      container.innerHTML = '';
      window.removeEventListener('afterprint', cleanup);
    };
    window.addEventListener('afterprint', cleanup);
    requestAnimationFrame(() => window.print());
  }

  /** @deprecated Use triggerPrintPreview */
  function openPrintWindow(bodyHtml, docTitle, options) {
    return triggerPrintPreview(bodyHtml, options);
  }

  global.CasePMPrint = {
    esc,
    logPhrase,
    truncatePrintText,
    formatPrintCell,
    pruneEmptyColumns,
    rebalanceColumnWidths,
    getProjectMeta,
    buildPrintHeaderHtml,
    showFieldPicker,
    buildPrintTable,
    buildPrintDocument,
    buildPageBlock,
    printHtmlInIframe,
    printPortraitDocument,
    triggerPrintPreview,
    openPrintWindow,
  };
})(window);
