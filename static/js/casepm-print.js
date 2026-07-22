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

  /** Company branding for print headers (logo + name from program settings). */
  function getCompanyMeta() {
    const info = global.CASEPM_COMPANY_INFO || {};
    const logoEl = document.getElementById('headerCompanyLogo');
    const logoFromDom = logoEl?.src && !logoEl.src.endsWith('/') ? logoEl.src : '';
    const name = (info.dba || info.name || 'Case PM').trim();
    return {
      name,
      logo: (info.logo || logoFromDom || '').trim(),
    };
  }

  /** Shared project header meta for all log prints. */
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
      .casepm-print-content-options {
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
        margin-bottom: 0.75rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #3f3f46;
      }
      .casepm-print-content-options label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.8125rem;
        color: #d4d4d8;
        cursor: pointer;
      }
      .casepm-print-content-options-title {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #71717a;
        font-weight: 600;
        margin-bottom: 0.25rem;
      }
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
        body.printing-co-detail #appShell > #appHeaderBar,
        body.printing-co-detail #appSidebar,
        body.printing-co-detail #appFooterBar,
        body.printing-co-detail #appShell > .flex.flex-1 > div.h-10,
        body.printing-co-detail .co-page,
        body.printing-co-detail #coDetailDrawer,
        body.printing-co-detail #coDrawerBackdrop,
        body.printing-co-detail .fixed.bottom-0,
        body.printing-co-detail dialog,
        body.printing-co-detail .no-print,
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
        body.printing-co-detail #coPrintSheet,
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
        body.printing-co-detail,
        body.printing-budget-log {
          background: #fff !important;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        body.printing-rfi-detail #mainContent,
        body.printing-co-detail #mainContent,
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
          page-break-inside: avoid;
          break-inside: avoid-page;
        }
        .casepm-print-page:last-child, .submittal-print-page:last-child {
          page-break-after: auto;
          break-after: auto;
        }
        .casepm-flowing-register, .submittal-flowing-register {
          background: #fff;
          color: #111;
        }
        .casepm-flowing-register .casepm-print-header,
        .submittal-flowing-register .submittal-print-header {
          page-break-after: avoid;
          break-after: avoid-page;
        }
        .casepm-flowing-register .casepm-print-table thead,
        .submittal-flowing-register .submittal-print-table thead,
        .submittal-flowing-register .casepm-print-table thead {
          display: table-header-group;
        }
        .casepm-flowing-register .casepm-print-table tr,
        .submittal-flowing-register .submittal-print-table tr,
        .submittal-flowing-register .casepm-print-table tr {
          page-break-inside: avoid;
          break-inside: avoid;
        }
        .casepm-flowing-register .casepm-print-footer,
        .submittal-flowing-register .submittal-print-footer {
          page-break-before: avoid;
          break-before: avoid-page;
        }
        .casepm-manual-sigs {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 14px;
          margin-top: 16px;
          page-break-inside: avoid;
        }
        .casepm-manual-sigs.three-col { grid-template-columns: repeat(3, 1fr); }
        .casepm-manual-sig-block {
          border: 1px solid #ccc;
          border-radius: 2px;
          padding: 10px;
          font-size: 7.5pt;
        }
        .casepm-manual-sig-role {
          font-size: 6.5pt;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #666;
          margin-bottom: 8px;
        }
        .casepm-manual-field {
          margin-bottom: 6px;
          font-size: 7pt;
        }
        .casepm-manual-field .label {
          display: block;
          font-size: 6pt;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #666;
          font-weight: 700;
          margin-bottom: 2px;
        }
        .casepm-manual-field .line {
          border-bottom: 1px solid #888;
          min-height: 20px;
        }
        .casepm-manual-field .value {
          padding: 2px 0;
          color: #222;
        }
        .casepm-manual-box {
          border: 1px solid #ccc;
          border-radius: 2px;
          padding: 10px 12px;
          margin-bottom: 10px;
        }
        .casepm-manual-box h4 {
          margin: 0 0 6px;
          font-size: 7pt;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #555;
          font-weight: 700;
        }
        .casepm-manual-box .prefill {
          font-size: 8pt;
          color: #444;
          white-space: pre-wrap;
          margin-bottom: 8px;
          padding-bottom: 6px;
          border-bottom: 1px dashed #ccc;
        }
        .casepm-manual-box .write-area {
          border: 1px dashed #bbb;
          border-radius: 2px;
          background: #fafafa;
        }
        .casepm-rfi-signoff-onepage { page-break-inside: avoid; break-inside: avoid-page; }
        .casepm-rfi-signoff-onepage .casepm-print-header { margin-bottom: 5px; padding-bottom: 5px; }
        .casepm-rfi-signoff-onepage .casepm-rfi-detail { font-size: 7.5pt; line-height: 1.3; }
        .casepm-rfi-signoff-onepage .rfi-detail-number { font-size: 10pt; }
        .casepm-rfi-signoff-onepage .rfi-detail-subject { font-size: 9.5pt; margin-bottom: 5px; line-height: 1.2; }
        .casepm-rfi-signoff-onepage .rfi-detail-grid { grid-template-columns: repeat(4, 1fr); gap: 3px 8px; margin-bottom: 5px; font-size: 7pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-field { margin-bottom: 1px; font-size: 6pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-field .label { font-size: 5.5pt; margin-bottom: 0; }
        .casepm-rfi-signoff-onepage .casepm-manual-field .line { min-height: 11px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box { padding: 5px 7px; margin-bottom: 4px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box h4 { margin-bottom: 2px; font-size: 5.5pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-box .prefill { font-size: 7pt; margin-bottom: 4px; padding-bottom: 3px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box .write-area { min-height: 36px !important; }
        .casepm-rfi-signoff-onepage .casepm-manual-sig-block { padding: 5px 6px; }
        .casepm-rfi-signoff-onepage .casepm-manual-sigs { gap: 6px; margin-top: 5px; }
        .casepm-rfi-signoff-onepage .co-doc-sigs { margin-top: 5px; page-break-inside: avoid; }
        .casepm-rfi-signoff-onepage .co-doc-sigs h3 { margin: 0 0 2px; font-size: 5.5pt; }
        .casepm-rfi-signoff-onepage .co-doc-sigs p { font-size: 6pt !important; margin: 0 0 4px !important; }
        .casepm-rfi-signoff-onepage .rfi-signoff-inline { font-size: 6.5pt; color: #555; margin-bottom: 3px; line-height: 1.25; }
        .casepm-rfi-signoff-onepage .casepm-print-footer { margin-top: 4px; padding-top: 3px; }
        .casepm-print-header, .submittal-print-header {
          margin-bottom: 8px;
          border-bottom: 1.5px solid #222;
          padding-bottom: 8px;
        }
        .casepm-print-header-continued, .submittal-print-header-continued {
          margin-bottom: 6px;
          padding-bottom: 4px;
          border-bottom: 1px solid #bbb;
        }
        .casepm-print-continued-title, .submittal-print-continued-title {
          font-size: 8pt;
          font-weight: 700;
          letter-spacing: 0.3px;
          color: #333;
          text-transform: uppercase;
        }
        .casepm-print-continued-label, .submittal-print-continued-label {
          font-weight: 500;
          color: #666;
          text-transform: none;
          font-size: 7.5pt;
        }
        .casepm-print-header-table, .submittal-print-header-table {
          width: 100%;
          border-collapse: collapse;
        }
        .casepm-print-header-table td, .submittal-print-header-table td {
          border: none;
          vertical-align: middle;
          padding: 0;
        }
        .casepm-print-header-brand, .submittal-print-header-brand {
          width: 52px;
          padding-right: 10px;
          vertical-align: top;
        }
        .casepm-print-logo, .submittal-print-logo {
          display: block;
          max-width: 48px;
          max-height: 36px;
          object-fit: contain;
        }
        .casepm-print-logo-placeholder, .submittal-print-logo-placeholder {
          width: 36px;
          height: 36px;
          border-radius: 4px;
          background: #1a1a1a;
          color: #fff;
          font-size: 14pt;
          font-weight: 700;
          display: flex;
          align-items: center;
          justify-content: center;
          line-height: 1;
        }
        .casepm-print-header-center, .submittal-print-header-center {
          padding-right: 14px;
          vertical-align: top;
        }
        .casepm-print-company-name, .submittal-print-company-name {
          font-size: 7pt;
          font-weight: 600;
          color: #444;
          letter-spacing: 0.2px;
          margin-bottom: 2px;
          line-height: 1.2;
        }
        .casepm-print-title, .submittal-print-title {
          font-size: 11pt;
          font-weight: 700;
          letter-spacing: 0.5px;
          color: #111;
          line-height: 1.15;
          text-transform: uppercase;
        }
        .casepm-print-location, .submittal-print-location {
          margin-top: 3px;
          font-size: 6pt;
          color: #555;
          line-height: 1.3;
        }
        .casepm-print-location .label, .submittal-print-location .label {
          font-weight: 700;
          text-transform: uppercase;
          font-size: 5.5pt;
          color: #777;
        }
        .casepm-print-header-right, .submittal-print-header-right {
          text-align: right;
          width: 32%;
          padding-left: 10px;
          white-space: normal;
          word-break: normal;
          overflow-wrap: normal;
          vertical-align: top;
        }
        .casepm-print-meta, .submittal-print-meta {
          text-align: right;
          font-size: 6.5pt;
          line-height: 1.4;
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
          font-size: 5.5pt;
          color: #666;
          letter-spacing: 0.03em;
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
          margin-top: 10px;
          padding-top: 5px;
          border-top: 1px solid #ccc;
          font-size: 6.5pt;
          color: #666;
        }
        .casepm-print-footer .center, .submittal-print-footer .center { text-align: center; }
        .casepm-print-footer .right, .submittal-print-footer .right { text-align: right; }
        .casepm-print-section-title {
          font-size: 8pt;
          font-weight: 600;
          margin: 8px 0 4px;
          color: #444;
          text-transform: uppercase;
          letter-spacing: 0.3px;
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
        .casepm-rfi-detail .rfi-detail-identifier {
          display: flex;
          align-items: baseline;
          gap: 10px;
          margin-bottom: 4px;
          flex-wrap: wrap;
        }
        .casepm-rfi-detail .rfi-detail-number {
          font-family: 'Courier New', Courier, monospace;
          font-size: 11pt;
          font-weight: 700;
          color: #111;
        }
        .casepm-rfi-detail .rfi-detail-status {
          font-size: 7pt;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #555;
          padding: 2px 8px;
          border: 1px solid #ccc;
          border-radius: 3px;
        }
        .casepm-rfi-detail .rfi-detail-subject {
          font-size: 12pt;
          font-weight: 700;
          margin-bottom: 10px;
          color: #111;
          line-height: 1.25;
        }
        .casepm-rfi-detail .rfi-detail-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
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
          border: 1px solid #ccc;
          border-radius: 2px;
          padding: 8px 10px;
          margin-bottom: 10px;
          white-space: pre-wrap;
          min-height: 40px;
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
        .casepm-rfi-signoff-onepage { page-break-inside: avoid; break-inside: avoid-page; }
        .casepm-rfi-signoff-onepage .casepm-print-header { margin-bottom: 5px; padding-bottom: 5px; }
        .casepm-rfi-signoff-onepage .casepm-rfi-detail { font-size: 7.5pt; line-height: 1.3; }
        .casepm-rfi-signoff-onepage .rfi-detail-number { font-size: 10pt; }
        .casepm-rfi-signoff-onepage .rfi-detail-subject { font-size: 9.5pt; margin-bottom: 5px; line-height: 1.2; }
        .casepm-rfi-signoff-onepage .rfi-detail-grid { grid-template-columns: repeat(4, 1fr); gap: 3px 8px; margin-bottom: 5px; font-size: 7pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-field { margin-bottom: 1px; font-size: 6pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-field .label { font-size: 5.5pt; margin-bottom: 0; }
        .casepm-rfi-signoff-onepage .casepm-manual-field .line { min-height: 11px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box { padding: 5px 7px; margin-bottom: 4px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box h4 { margin-bottom: 2px; font-size: 5.5pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-box .prefill { font-size: 7pt; margin-bottom: 4px; padding-bottom: 3px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box .write-area { min-height: 36px !important; }
        .casepm-rfi-signoff-onepage .casepm-manual-sig-block { padding: 5px 6px; }
        .casepm-rfi-signoff-onepage .casepm-manual-sigs { gap: 6px; margin-top: 5px; }
        .casepm-rfi-signoff-onepage .co-doc-sigs { margin-top: 5px; page-break-inside: avoid; }
        .casepm-rfi-signoff-onepage .co-doc-sigs h3 { margin: 0 0 2px; font-size: 5.5pt; }
        .casepm-rfi-signoff-onepage .co-doc-sigs p { font-size: 6pt !important; margin: 0 0 4px !important; }
        .casepm-rfi-signoff-onepage .rfi-signoff-inline { font-size: 6.5pt; color: #555; margin-bottom: 3px; line-height: 1.25; }
        .casepm-rfi-signoff-onepage .casepm-print-footer { margin-top: 4px; padding-top: 3px; }
      }
    `;
    document.head.appendChild(style);
  }

  function showFieldPicker(options) {
    ensureStyles();
    const fields = options.fields || [];
    const contentOptions = options.contentOptions || [];
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

      const contentOptsHtml = contentOptions.length ? `
        <div class="casepm-print-content-options">
          <div class="casepm-print-content-options-title">Print options</div>
          ${contentOptions.map(co => `
            <label><input type="checkbox" data-content="${esc(co.key)}" ${co.default !== false ? 'checked' : ''}${co.locked ? ' disabled checked' : ''}> ${esc(co.label)}</label>
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
            ${contentOptsHtml}
            ${note ? `<p class="casepm-print-field-note">${esc(note)}</p>` : ''}
            ${fields.length ? `<div class="casepm-print-toolbar">
              <button type="button" data-action="all">Select All</button>
              <button type="button" data-action="none">Clear All</button>
              <button type="button" data-action="default">Defaults</button>
            </div>
            <div class="casepm-print-field-grid">
              ${fields.map(f => `
                <label><input type="checkbox" data-field="${esc(f.key)}" ${f.default !== false ? 'checked' : ''}${f.locked ? ' disabled checked' : ''}> ${esc(f.label)}</label>
              `).join('')}
            </div>` : ''}
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
      const contentBoxes = () => Array.from(dialog.querySelectorAll('input[data-content]'));
      const finish = (result) => { dialog.close(); dialog.remove(); resolve(result); };

      if (fields.length) {
        dialog.querySelector('[data-action="all"]').onclick = () => boxes().forEach(b => { if (!b.disabled) b.checked = true; });
        dialog.querySelector('[data-action="none"]').onclick = () => boxes().forEach(b => { if (!b.disabled) b.checked = false; });
        dialog.querySelector('[data-action="default"]').onclick = () => {
          boxes().forEach(b => {
            const f = fields.find(x => x.key === b.dataset.field);
            if (!b.disabled) b.checked = f ? f.default !== false : true;
          });
          contentBoxes().forEach(b => {
            const co = contentOptions.find(x => x.key === b.dataset.content);
            if (!b.disabled) b.checked = co ? co.default !== false : true;
          });
        };
      } else if (contentOptions.length) {
        dialog.querySelector('[data-action="all"]')?.remove();
        dialog.querySelector('[data-action="none"]')?.remove();
        const defaultBtn = dialog.querySelector('[data-action="default"]');
        if (defaultBtn) {
          defaultBtn.textContent = 'Reset';
          defaultBtn.onclick = () => {
            contentBoxes().forEach(b => {
              const co = contentOptions.find(x => x.key === b.dataset.content);
              if (!b.disabled) b.checked = co ? co.default !== false : true;
            });
          };
        }
      }
      dialog.querySelector('[data-action="close"]').onclick = () => finish(null);
      dialog.querySelector('[data-action="cancel"]').onclick = () => finish(null);
      dialog.querySelector('[data-action="print"]').onclick = () => {
        const selected = boxes().filter(b => b.checked).map(b => b.dataset.field);
        if (fields.length && !selected.length) {
          if (global.CasePMDialog) global.CasePMDialog.alert('Select at least one field to print.');
          else alert('Select at least one field to print.');
          return;
        }
        const content = {};
        contentBoxes().forEach(b => { content[b.dataset.content] = b.checked; });
        const logTypeEl = dialog.querySelector('input[name="casepmPrintLogType"]:checked');
        finish({
          fields: selected,
          logType: logTypeEl ? logTypeEl.value : defaultLogType,
          contentOptions: content,
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

  function buildPrintHeaderHtml(meta, title, options) {
    const opts = options || {};
    const prefix = opts.classPrefix || 'casepm-print-';

    if (opts.continued) {
      return `<div class="${prefix}header ${prefix}header-continued">
        <span class="${prefix}continued-title">${esc(title)} <span class="${prefix}continued-label">(continued)</span></span>
      </div>`;
    }

    const company = getCompanyMeta();
    const logoHtml = company.logo
      ? `<img src="${company.logo}" alt="" class="${prefix}logo">`
      : `<div class="${prefix}logo-placeholder">${esc(company.name.charAt(0).toUpperCase())}</div>`;

    const showLoc = opts.showLocation !== false && meta.location;
    const loc = showLoc
      ? `<div class="${prefix}location"><span class="label">Location</span> ${esc(meta.location)}</div>`
      : '';

    const projectMeta = [];
    if (meta.number) projectMeta.push(`<div><span class="label">Project No.</span><br>${esc(meta.number)}</div>`);
    if (meta.name) projectMeta.push(`<div><span class="label">Project</span><br>${esc(meta.name)}</div>`);

    return `<div class="${prefix}header">
      <table class="${prefix}header-table"><tr>
        <td class="${prefix}header-brand">${logoHtml}</td>
        <td class="${prefix}header-center">
          <div class="${prefix}company-name">${esc(company.name)}</div>
          <div class="${prefix}title">${esc(title)}</div>
          ${loc}
        </td>
        <td class="${prefix}header-right">
          <div class="${prefix}meta">${projectMeta.join('')}</div>
        </td>
      </tr></table>
    </div>`;
  }

  /** Estimate rows that fit on one printed landscape page without bleeding into the next. */
  function estimateLogRowsPerPage(options) {
    const opts = options || {};
    const columnCount = opts.columnCount || 12;
    const fullHeader = opts.fullHeader !== false;
    let rows = fullHeader ? 12 : 16;
    if (columnCount > 10) rows -= Math.ceil((columnCount - 10) / 2);
    if (columnCount > 16) rows -= 3;
    if (columnCount > 20) rows -= 2;
    return Math.max(6, Math.min(18, rows));
  }

  /** Split register rows into page chunks (smaller first page when full header is used). */
  function paginateLogRows(rows, options) {
    if (!rows.length) return [[]];
    const opts = options || {};
    const columnCount = opts.columnCount || 12;
    const firstPageRows = opts.firstPageRows || estimateLogRowsPerPage({ columnCount, fullHeader: true });
    const contPageRows = opts.contPageRows || estimateLogRowsPerPage({ columnCount, fullHeader: false });
    const pages = [rows.slice(0, firstPageRows)];
    let i = firstPageRows;
    while (i < rows.length) {
      pages.push(rows.slice(i, i + contPageRows));
      i += contPageRows;
    }
    return pages;
  }

  function buildPrintFooterHtml(printedOn, pageNum, totalPages, options) {
    const opts = options || {};
    const showDate = opts.showPrintedDate !== false;
    const pageLabel = totalPages > 1 ? `Page ${pageNum} of ${totalPages}` : (pageNum > 1 ? `Page ${pageNum}` : '');
    return `<div class="casepm-print-footer">
      <span>Confidential</span>
      <span class="center">${showDate ? esc(printedOn) : ''}</span>
      <span class="right">${pageLabel}</span>
    </div>`;
  }

  /** Manual sign-off block with blank lines for ink signatures. */
  function buildManualSigBlock(role, options) {
    const opts = options || {};
    const compact = !!opts.compact;
    const fields = compact
      ? ['Signature', 'Print Name', 'Date']
      : ['Signature', 'Print Name', 'Title', 'Date'];
    const fieldHtml = fields.map(label =>
      `<div class="casepm-manual-field"><span class="label">${esc(label)}</span><div class="line"></div></div>`
    ).join('');
    const compactCls = compact ? ' casepm-manual-sig-compact' : '';
    return `<div class="casepm-manual-sig-block${compactCls}">
      <div class="casepm-manual-sig-role">${esc(role)}</div>
      ${fieldHtml}
    </div>`;
  }

  /** Label with pre-filled value or a blank line for handwriting. */
  function buildWritableField(label, value, options) {
    const opts = options || {};
    const text = normalizePrintCell(value);
    if (!opts.blank && text && !isEmptyPrintCell(text)) {
      return `<div class="casepm-manual-field"><span class="label">${esc(label)}</span><div class="value">${esc(text)}</div></div>`;
    }
    return `<div class="casepm-manual-field"><span class="label">${esc(label)}</span><div class="line"></div></div>`;
  }

  /** Box with optional prefill text and a large blank area for handwritten responses. */
  function buildWritableBox(label, content, options) {
    const opts = options || {};
    const minH = opts.minHeight || 80;
    const text = normalizePrintCell(content);
    const showPrefill = !opts.blankOnly && text && !isEmptyPrintCell(text);
    return `<div class="casepm-manual-box">
      <h4>${esc(label)}</h4>
      ${showPrefill ? `<div class="prefill">${esc(text)}</div>` : ''}
      <div class="write-area" style="min-height:${minH}px"></div>
    </div>`;
  }

  /**
   * Flowing register print — document header once at top, column headers repeat per page.
   * Avoids duplicate document headers bleeding onto the same physical page.
   */
  function buildFlowingRegisterHtml(meta, title, columns, rows, options) {
    const opts = options || {};
    const registerRows = rows || [];
    const activeColumns = rebalanceColumnWidths(pruneEmptyColumns(columns || [], registerRows));
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const prefix = opts.classPrefix || 'casepm-print-';
    const headerOpts = {
      classPrefix: prefix,
      showLocation: opts.showLocation !== false,
    };
    const footerOpts = { showPrintedDate: opts.showPrintedDate !== false };
    const sheetClass = opts.sheetClass || 'casepm-flowing-register';
    const tableHtml = buildPrintTable(activeColumns, registerRows, opts.emptyMessage);
    const footerClass = prefix === 'submittal-print-' ? 'submittal-print-footer' : 'casepm-print-footer';
    const showDate = footerOpts.showPrintedDate;
    return `<div class="${sheetClass}">
      ${buildPrintHeaderHtml(meta, title, headerOpts)}
      ${tableHtml.replace('casepm-print-table', `${prefix.replace(/-$/, '')}-table casepm-print-table`)}
      <div class="${footerClass}">
        <span>Confidential</span>
        <span class="center">${showDate ? esc(printedOn) : ''}</span>
        <span class="right"></span>
      </div>
    </div>`;
  }

  function buildPrintDocument(opts) {
    const meta = opts.meta || {};
    const printOpts = opts.printOptions || {};
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const sections = opts.sections || [{ title: opts.title, tableHtml: opts.tableHtml }];

    if (opts.flowing) {
      return sections.map(section => buildFlowingRegisterHtml(meta, section.title, section.columns || [], section.rows || [], {
        showLocation: printOpts.showLocation !== false,
        showPrintedDate: printOpts.showPrintedDate !== false,
        emptyMessage: section.emptyMessage,
      })).join('');
    }

    const pages = [];
    const headerOpts = {
      showLocation: printOpts.showLocation !== false,
    };
    const footerOpts = {
      showPrintedDate: printOpts.showPrintedDate !== false,
    };

    sections.forEach(section => {
      const rows = section.rows || [];
      const columns = rebalanceColumnWidths(pruneEmptyColumns(section.columns || [], rows));
      if (!rows.length) {
        pages.push(buildPageBlock(meta, section.title, buildPrintTable(columns, [], section.emptyMessage), printedOn, 1, 1, false, headerOpts, footerOpts));
        return;
      }
      const rowPages = paginateLogRows(rows, {
        columnCount: columns.length,
        firstPageRows: opts.rowsPerPage ? Math.min(opts.rowsPerPage, estimateLogRowsPerPage({ columnCount: columns.length, fullHeader: true })) : undefined,
      });
      const totalPages = rowPages.length;
      rowPages.forEach((chunk, p) => {
        const tableHtml = buildPrintTable(columns, chunk);
        pages.push(buildPageBlock(meta, section.title, tableHtml, printedOn, p + 1, totalPages, p > 0, headerOpts, footerOpts));
      });
    });

    return pages.map((p) => `<div class="casepm-print-page">${p}</div>`).join('');
  }

  function buildPageBlock(meta, title, tableHtml, printedOn, pageNum, totalPages, sectionContinued, headerOpts, footerOpts) {
    const hOpts = { ...(headerOpts || {}), continued: !!sectionContinued };
    const sectionNote = sectionContinued && false
      ? `<div class="casepm-print-section-title">${esc(title)} (continued)</div>`
      : '';
    return `
      ${buildPrintHeaderHtml(meta, title, hOpts)}
      ${sectionNote}
      ${tableHtml}
      ${buildPrintFooterHtml(printedOn, pageNum, totalPages, footerOpts)}`;
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

  /** Portrait document print (individual RFI, CO, etc.) in an isolated iframe. */
  function printPortraitDocument(bodyHtml, docTitle, extraCss) {
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const headerCss = `
        .casepm-print-page { page-break-after: always; break-after: page; page-break-inside: avoid; break-inside: avoid-page; }
        .casepm-print-page:last-child { page-break-after: auto; break-after: auto; }
        .casepm-print-header { margin-bottom: 10px; border-bottom: 1.5px solid #222; padding-bottom: 10px; }
        .casepm-print-header-table { width: 100%; border-collapse: collapse; }
        .casepm-print-header-table td { border: none; vertical-align: middle; padding: 0; }
        .casepm-print-header-brand { width: 56px; padding-right: 12px; vertical-align: top; }
        .casepm-print-logo { display: block; max-width: 52px; max-height: 40px; object-fit: contain; }
        .casepm-print-logo-placeholder { width: 40px; height: 40px; border-radius: 4px; background: #1a1a1a; color: #fff; font-size: 16pt; font-weight: 700; display: flex; align-items: center; justify-content: center; }
        .casepm-print-header-center { padding-right: 16px; vertical-align: top; }
        .casepm-print-company-name { font-size: 8pt; font-weight: 600; color: #444; margin-bottom: 3px; }
        .casepm-print-title { font-size: 13pt; font-weight: 700; letter-spacing: 0.5px; color: #111; text-transform: uppercase; line-height: 1.15; }
        .casepm-print-location { margin-top: 4px; font-size: 7pt; color: #555; }
        .casepm-print-location .label { font-weight: 700; text-transform: uppercase; font-size: 6pt; color: #777; }
        .casepm-print-header-right { text-align: right; width: 34%; vertical-align: top; }
        .casepm-print-meta { text-align: right; font-size: 7pt; line-height: 1.4; color: #222; }
        .casepm-print-meta .label { font-weight: 700; text-transform: uppercase; font-size: 6pt; color: #666; }
        .casepm-print-footer { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; margin-top: 12px; padding-top: 6px; border-top: 1px solid #ccc; font-size: 7pt; color: #666; }
        .casepm-print-footer .center { text-align: center; }
        .casepm-print-footer .right { text-align: right; }
        .casepm-rfi-detail { font-size: 9pt; line-height: 1.45; color: #111; }
        .casepm-rfi-detail .rfi-detail-identifier { display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
        .casepm-rfi-detail .rfi-detail-number { font-family: 'Courier New', Courier, monospace; font-size: 12pt; font-weight: 700; color: #111; }
        .casepm-rfi-detail .rfi-detail-status { font-size: 7.5pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #555; padding: 2px 8px; border: 1px solid #ccc; border-radius: 3px; }
        .casepm-rfi-detail .rfi-detail-subject { font-size: 13pt; font-weight: 700; margin-bottom: 12px; color: #111; line-height: 1.25; }
        .casepm-rfi-detail .rfi-detail-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px 16px; margin-bottom: 14px; font-size: 8pt; }
        .casepm-rfi-detail .rfi-detail-grid .label { display: block; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.04em; color: #666; font-weight: 700; margin-bottom: 1px; }
        .casepm-rfi-detail .rfi-detail-box { border: 1px solid #ccc; border-radius: 2px; padding: 10px 12px; margin-bottom: 10px; white-space: pre-wrap; min-height: 40px; }
        .casepm-rfi-detail .rfi-detail-box h4 { margin: 0 0 6px; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.05em; color: #555; font-weight: 700; }
        .casepm-rfi-detail .rfi-detail-list { margin: 0; padding-left: 16px; font-size: 8pt; }
        .casepm-co-document { font-size: 9pt; line-height: 1.45; color: #111; position: relative; }
        .casepm-co-document .co-doc-watermark {
          position: absolute; top: 42%; left: 50%; transform: translate(-50%, -50%) rotate(-32deg);
          font-size: 52pt; font-weight: 700; color: rgba(0,0,0,0.06); letter-spacing: 0.15em; text-transform: uppercase;
          pointer-events: none; white-space: nowrap; z-index: 0;
        }
        .casepm-co-document > *:not(.co-doc-watermark) { position: relative; z-index: 1; }
        .casepm-co-document .co-doc-hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin: 12px 0 14px; padding-bottom: 10px; border-bottom: 2px solid #222; }
        .casepm-co-document .co-doc-number { font-family: 'Courier New', Courier, monospace; font-size: 14pt; font-weight: 700; color: #111; }
        .casepm-co-document .co-doc-hero-meta { text-align: right; font-size: 8pt; color: #444; line-height: 1.5; }
        .casepm-co-document .co-doc-status { display: inline-block; font-size: 7pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; padding: 2px 8px; border: 1px solid #999; border-radius: 3px; color: #555; }
        .casepm-co-document .co-doc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 20px; margin-bottom: 14px; font-size: 8pt; }
        .casepm-co-document .co-doc-grid .label { display: block; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.05em; color: #666; font-weight: 700; margin-bottom: 2px; }
        .casepm-co-document .co-doc-section { margin-bottom: 12px; }
        .casepm-co-document .co-doc-section h3 { margin: 0 0 5px; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.06em; color: #555; font-weight: 700; }
        .casepm-co-document .co-doc-body { border: 1px solid #ccc; border-radius: 2px; padding: 10px 12px; white-space: pre-wrap; min-height: 56px; background: #fafafa; }
        .casepm-co-document .co-doc-table { width: 100%; border-collapse: collapse; font-size: 8pt; margin-bottom: 12px; }
        .casepm-co-document .co-doc-table th, .casepm-co-document .co-doc-table td { border: 1px solid #bbb; padding: 5px 8px; vertical-align: top; }
        .casepm-co-document .co-doc-table th { background: #f0f0f0; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.04em; color: #555; font-weight: 700; text-align: left; }
        .casepm-co-document .co-doc-table td.r, .casepm-co-document .co-doc-table th.r { text-align: right; }
        .casepm-co-document .co-doc-table td.mono { font-family: 'Courier New', Courier, monospace; }
        .casepm-co-document .co-doc-table tfoot td { font-weight: 700; background: #f7f7f7; }
        .casepm-co-document .co-doc-sum-row td { padding: 4px 8px; }
        .casepm-co-document .co-doc-sum-row .label-col { color: #555; }
        .casepm-co-document .co-doc-sigs { margin-top: 16px; page-break-inside: avoid; }
        .casepm-co-document .co-doc-sigs h3 { margin: 0 0 8px; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.06em; color: #555; font-weight: 700; }
        .casepm-co-document .co-doc-sig-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
        .casepm-co-document .co-doc-sig-grid.two-col { grid-template-columns: 1fr 1fr; }
        .casepm-co-document .co-doc-sig-block { border: 1px solid #ccc; border-radius: 2px; padding: 10px; min-height: 88px; font-size: 7.5pt; }
        .casepm-co-document .co-doc-sig-role { font-size: 6.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-bottom: 8px; }
        .casepm-co-document .co-doc-sig-line { border-bottom: 1px solid #888; height: 22px; margin-bottom: 6px; }
        .casepm-co-document .co-doc-sig-filled { font-size: 7pt; color: #222; margin-top: 4px; }
        .casepm-co-document .co-doc-history { font-size: 7.5pt; color: #444; margin-top: 10px; }
        .casepm-co-document .co-doc-history-item { padding: 4px 0; border-bottom: 1px solid #eee; }
        .casepm-manual-sigs { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 16px; page-break-inside: avoid; }
        .casepm-manual-sigs.three-col { grid-template-columns: repeat(3, 1fr); }
        .casepm-manual-sig-block { border: 1px solid #ccc; border-radius: 2px; padding: 10px; font-size: 7.5pt; }
        .casepm-manual-sig-role { font-size: 6.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #666; margin-bottom: 8px; }
        .casepm-manual-field { margin-bottom: 6px; font-size: 7pt; }
        .casepm-manual-field .label { display: block; font-size: 6pt; text-transform: uppercase; letter-spacing: 0.04em; color: #666; font-weight: 700; margin-bottom: 2px; }
        .casepm-manual-field .line { border-bottom: 1px solid #888; min-height: 20px; }
        .casepm-manual-field .value { padding: 2px 0; color: #222; }
        .casepm-manual-box { border: 1px solid #ccc; border-radius: 2px; padding: 10px 12px; margin-bottom: 10px; }
        .casepm-manual-box h4 { margin: 0 0 6px; font-size: 7pt; text-transform: uppercase; letter-spacing: 0.05em; color: #555; font-weight: 700; }
        .casepm-manual-box .prefill { font-size: 8pt; color: #444; white-space: pre-wrap; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px dashed #ccc; }
        .casepm-manual-box .write-area { border: 1px dashed #bbb; border-radius: 2px; background: #fafafa; }
        .casepm-rfi-signoff-onepage { page-break-inside: avoid; break-inside: avoid-page; }
        .casepm-rfi-signoff-onepage .casepm-print-header { margin-bottom: 5px; padding-bottom: 5px; }
        .casepm-rfi-signoff-onepage .casepm-rfi-detail { font-size: 7.5pt; line-height: 1.3; }
        .casepm-rfi-signoff-onepage .rfi-detail-number { font-size: 10pt; }
        .casepm-rfi-signoff-onepage .rfi-detail-subject { font-size: 9.5pt; margin-bottom: 5px; line-height: 1.2; }
        .casepm-rfi-signoff-onepage .rfi-detail-grid { grid-template-columns: repeat(4, 1fr); gap: 3px 8px; margin-bottom: 5px; font-size: 7pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-field { margin-bottom: 1px; font-size: 6pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-field .label { font-size: 5.5pt; margin-bottom: 0; }
        .casepm-rfi-signoff-onepage .casepm-manual-field .line { min-height: 11px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box { padding: 5px 7px; margin-bottom: 4px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box h4 { margin-bottom: 2px; font-size: 5.5pt; }
        .casepm-rfi-signoff-onepage .casepm-manual-box .prefill { font-size: 7pt; margin-bottom: 4px; padding-bottom: 3px; }
        .casepm-rfi-signoff-onepage .casepm-manual-box .write-area { min-height: 36px !important; }
        .casepm-rfi-signoff-onepage .casepm-manual-sig-block { padding: 5px 6px; }
        .casepm-rfi-signoff-onepage .casepm-manual-sigs { gap: 6px; margin-top: 5px; }
        .casepm-rfi-signoff-onepage .co-doc-sigs { margin-top: 5px; page-break-inside: avoid; }
        .casepm-rfi-signoff-onepage .co-doc-sigs h3 { margin: 0 0 2px; font-size: 5.5pt; }
        .casepm-rfi-signoff-onepage .co-doc-sigs p { font-size: 6pt !important; margin: 0 0 4px !important; }
        .casepm-rfi-signoff-onepage .rfi-signoff-inline { font-size: 6.5pt; color: #555; margin-bottom: 3px; line-height: 1.25; }
        .casepm-rfi-signoff-onepage .casepm-print-footer { margin-top: 4px; padding-top: 3px; }`;
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(docTitle || 'Print')}</title>
      <style>
        @page { size: portrait; margin: 0.45in 0.5in; }
        body { margin: 0; font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        ${headerCss}
        ${extraCss || ''}
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

  function buildPortraitPreviewDocument(bodyHtml, docTitle, extraCss) {
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const portraitCss = `
        @page { size: portrait; margin: 0.45in 0.5in; }
        body { margin: 0; font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        .casepm-print-page { page-break-after: always; break-after: page; page-break-inside: avoid; break-inside: avoid-page; }
        .casepm-print-header { margin-bottom: 10px; border-bottom: 1.5px solid #222; padding-bottom: 10px; }
        .casepm-print-title { font-size: 13pt; font-weight: 700; letter-spacing: 0.5px; color: #111; text-transform: uppercase; }
        .casepm-print-footer { margin-top: 12px; padding-top: 6px; border-top: 1px solid #ccc; font-size: 7pt; color: #666; text-align: center; }
        .casepm-rfi-detail, .casepm-submittal-detail { font-size: 9pt; line-height: 1.45; color: #111; }
        .casepm-rfi-detail .rfi-detail-number, .casepm-submittal-detail .sub-detail-number { font-family: 'Courier New', Courier, monospace; font-size: 12pt; font-weight: 700; }
        .casepm-rfi-detail .rfi-detail-subject, .casepm-submittal-detail .sub-detail-subject { font-size: 13pt; font-weight: 700; margin-bottom: 12px; }
        .casepm-rfi-detail .rfi-detail-grid, .casepm-submittal-detail .sub-detail-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px 16px; margin-bottom: 14px; font-size: 8pt; }
        .casepm-rfi-detail .label, .casepm-submittal-detail .label { display: block; font-size: 6.5pt; text-transform: uppercase; color: #666; font-weight: 700; margin-bottom: 1px; }
        .casepm-rfi-detail .rfi-detail-box, .casepm-submittal-detail .sub-detail-box { border: 1px solid #ccc; border-radius: 2px; padding: 10px 12px; margin-bottom: 10px; white-space: pre-wrap; min-height: 40px; }
        .casepm-rfi-detail .rfi-detail-box h4, .casepm-submittal-detail .sub-detail-box h4 { margin: 0 0 6px; font-size: 7pt; text-transform: uppercase; color: #555; font-weight: 700; }
        ${extraCss || ''}`;
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(docTitle || 'Document')}</title>
      <style>${portraitCss}</style></head>
      <body>${String(bodyHtml || '').replace('__PRINTED_ON__', esc(printedOn))}</body></html>`;
  }

  const DOC_VIEWER_STYLE_ID = 'casepm-doc-viewer-styles';

  function ensureDocViewerStyles() {
    if (document.getElementById(DOC_VIEWER_STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = DOC_VIEWER_STYLE_ID;
    style.textContent = `
      dialog.casepm-doc-viewer { border: none; padding: 0; background: transparent; max-width: min(920px, 96vw); width: 100%; }
      dialog.casepm-doc-viewer::backdrop { background: rgba(0,0,0,0.72); }
      .casepm-doc-viewer-panel { background: #18181b; border: 1px solid #3f3f46; border-radius: 1rem; overflow: hidden; box-shadow: 0 24px 64px rgba(0,0,0,0.45); display: flex; flex-direction: column; max-height: 88vh; }
      .casepm-doc-viewer-header { padding: 1rem 1.25rem; border-bottom: 1px solid #27272a; background: #09090b; cursor: move; user-select: none; }
      .casepm-doc-viewer-title { font-size: 1rem; font-weight: 600; color: #fafafa; }
      .casepm-doc-viewer-subtitle { font-size: 0.8rem; color: #a1a1aa; margin-top: 0.15rem; }
      .casepm-doc-viewer-body { flex: 1; min-height: 0; background: #52525b; padding: 1rem; overflow: auto; }
      .casepm-doc-viewer-frame-wrap { background: #fff; border-radius: 0.5rem; box-shadow: 0 8px 32px rgba(0,0,0,0.35); min-height: min(70vh, 720px); }
      .casepm-doc-viewer-frame { display: block; width: 100%; min-height: min(70vh, 720px); border: 0; border-radius: 0.5rem; background: #fff; }
      .casepm-doc-viewer-footer { padding: 0.85rem 1.25rem; border-top: 1px solid #27272a; background: #18181b; display: flex; justify-content: flex-end; gap: 0.75rem; }
      .casepm-doc-viewer-btn { padding: 0.5rem 1.1rem; border-radius: 0.6rem; font-size: 0.875rem; font-weight: 500; border: none; cursor: pointer; }
      .casepm-doc-viewer-btn-primary { background: #059669; color: #fff; }
      .casepm-doc-viewer-btn-primary:hover { background: #047857; }
      .casepm-doc-viewer-btn-secondary { background: #3f3f46; color: #e4e4e7; }
      .casepm-doc-viewer-btn-secondary:hover { background: #52525b; }`;
    document.head.appendChild(style);
  }

  function makeDocViewerDraggable(dialog) {
    const handle = dialog.querySelector('.casepm-doc-viewer-header');
    if (!handle) return;
    let pos1 = 0; let pos2 = 0; let pos3 = 0; let pos4 = 0;
    handle.onmousedown = (e) => {
      if (e.target.closest('button')) return;
      e.preventDefault();
      pos3 = e.clientX;
      pos4 = e.clientY;
      document.onmouseup = closeDrag;
      document.onmousemove = drag;
    };
    function drag(e) {
      e.preventDefault();
      pos1 = pos3 - e.clientX;
      pos2 = pos4 - e.clientY;
      pos3 = e.clientX;
      pos4 = e.clientY;
      dialog.style.top = `${dialog.offsetTop - pos2}px`;
      dialog.style.left = `${dialog.offsetLeft - pos1}px`;
      dialog.style.transform = 'none';
      dialog.style.margin = '0';
    }
    function closeDrag() {
      document.onmouseup = null;
      document.onmousemove = null;
    }
  }

  /** In-app document viewer — print-formatted HTML in an iframe with Print + Close. */
  function openHtmlDocumentViewer(opts) {
    ensureDocViewerStyles();
    const options = opts || {};
    const bodyHtml = options.bodyHtml || '';
    if (!bodyHtml) return null;

    document.querySelectorAll('dialog.casepm-doc-viewer').forEach((d) => {
      try { d.close(); } catch (_) { /* ignore */ }
      d.remove();
    });

    const docTitle = options.docTitle || options.title || 'Document';
    const fullHtml = buildPortraitPreviewDocument(bodyHtml, docTitle, options.extraCss);

    const dialog = document.createElement('dialog');
    dialog.className = 'casepm-doc-viewer';
    dialog.style.cssText = 'position:fixed;top:6vh;left:50%;transform:translateX(-50%);margin:0;';

    dialog.innerHTML = `
      <div class="casepm-doc-viewer-panel">
        <div class="casepm-doc-viewer-header">
          <div class="casepm-doc-viewer-title">${esc(options.title || docTitle)}</div>
          ${options.subtitle ? `<div class="casepm-doc-viewer-subtitle">${esc(options.subtitle)}</div>` : ''}
        </div>
        <div class="casepm-doc-viewer-body">
          <div class="casepm-doc-viewer-frame-wrap">
            <iframe class="casepm-doc-viewer-frame" title="${esc(docTitle)}"></iframe>
          </div>
        </div>
        <div class="casepm-doc-viewer-footer">
          <button type="button" class="casepm-doc-viewer-btn casepm-doc-viewer-btn-secondary" data-action="close">Close</button>
          <button type="button" class="casepm-doc-viewer-btn casepm-doc-viewer-btn-primary" data-action="print">Print</button>
        </div>
      </div>`;

    document.body.appendChild(dialog);
    const frame = dialog.querySelector('.casepm-doc-viewer-frame');
    if (frame) frame.srcdoc = fullHtml;

    dialog.querySelector('[data-action="close"]')?.addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-action="print"]')?.addEventListener('click', () => {
      try {
        frame?.contentWindow?.focus();
        frame?.contentWindow?.print();
      } catch (_) {
        printHtmlInIframe(fullHtml, { landscape: false, delay: 300 });
      }
    });
    dialog.addEventListener('close', () => dialog.remove());
    dialog.addEventListener('cancel', (e) => { e.preventDefault(); dialog.close(); });
    dialog.showModal();
    makeDocViewerDraggable(dialog);
    return dialog;
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
    estimateLogRowsPerPage,
    paginateLogRows,
    isEmptyPrintCell,
    getCompanyMeta,
    getProjectMeta,
    buildPrintHeaderHtml,
    buildPrintFooterHtml,
    buildFlowingRegisterHtml,
    buildManualSigBlock,
    buildWritableField,
    buildWritableBox,
    showFieldPicker,
    buildPrintTable,
    buildPrintDocument,
    buildPageBlock,
    printHtmlInIframe,
    printPortraitDocument,
    triggerPrintPreview,
    openPrintWindow,
    buildPortraitPreviewDocument,
    openHtmlDocumentViewer,
  };
})(window);
