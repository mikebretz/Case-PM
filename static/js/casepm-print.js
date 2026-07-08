/**
 * Case PM — shared log print with field picker (native print preview, no popup window).
 */
(function (global) {
  'use strict';

  const STYLE_ID = 'casepm-print-picker-styles';
  const PRINT_SHEET_STYLE_ID = 'casepm-print-sheet-styles';

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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
    if (document.getElementById(PRINT_SHEET_STYLE_ID)) return;
    const cls = bodyClass || 'casepm-printing';
    const style = document.createElement('style');
    style.id = PRINT_SHEET_STYLE_ID;
    style.textContent = `
      @media print {
        @page { size: landscape; margin: 0.3in 0.35in; }
        body.${cls},
        body.casepm-printing,
        body.printing-submittal-log,
        body.printing-co-log {
          background: #fff !important;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        body.${cls} #appShell > #appHeaderBar,
        body.${cls} #appSidebar,
        body.${cls} #appShell > .flex.flex-1 > div.h-10,
        body.${cls} #submittalChrome,
        body.${cls} .co-page,
        body.${cls} #scheduleChrome,
        body.${cls} .no-print,
        body.casepm-printing #appShell > #appHeaderBar,
        body.casepm-printing #appSidebar,
        body.casepm-printing #appShell > .flex.flex-1 > div.h-10,
        body.casepm-printing #submittalChrome,
        body.casepm-printing .co-page,
        body.casepm-printing #scheduleChrome,
        body.casepm-printing .no-print,
        body.printing-submittal-log #appShell > #appHeaderBar,
        body.printing-submittal-log #appSidebar,
        body.printing-submittal-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-submittal-log #submittalChrome,
        body.printing-submittal-log .no-print,
        body.printing-co-log #appShell > #appHeaderBar,
        body.printing-co-log #appSidebar,
        body.printing-co-log #appShell > .flex.flex-1 > div.h-10,
        body.printing-co-log .co-page > *:not(#coPrintSheet),
        body.printing-co-log .no-print {
          display: none !important;
        }
        body.${cls} #mainContent,
        body.casepm-printing #mainContent,
        body.printing-submittal-log #mainContent,
        body.printing-co-log #mainContent {
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
        body.printing-co-log #coPrintSheet {
          display: block !important;
          background: #fff !important;
          color: #111 !important;
          font-family: Arial, Helvetica, sans-serif;
          font-size: 7pt;
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
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 8px 16px;
          align-items: start;
          margin-bottom: 6px;
          border-bottom: 2px solid #111;
          padding-bottom: 6px;
        }
        .casepm-print-title, .submittal-print-title {
          font-size: 16pt;
          font-weight: 700;
          letter-spacing: 0.5px;
          color: #111;
          line-height: 1.1;
        }
        .casepm-print-meta, .submittal-print-meta {
          text-align: right;
          font-size: 7pt;
          line-height: 1.35;
          color: #222;
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
          font-size: 6.5pt;
          line-height: 1.2;
        }
        .casepm-print-table th, .casepm-print-table td,
        .submittal-print-table th, .submittal-print-table td {
          border: 1px solid #333;
          padding: 2px 3px;
          vertical-align: top;
          word-wrap: break-word;
          overflow-wrap: anywhere;
        }
        .casepm-print-table th, .submittal-print-table th {
          background: #f0f0f0;
          font-weight: 700;
          text-align: center;
          font-size: 5.5pt;
          text-transform: uppercase;
          line-height: 1.15;
          padding: 3px 2px;
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
            <button type="button" data-action="print" class="casepm-dialog-btn casepm-dialog-btn-primary" style="padding:0.5rem 1rem;border-radius:0.375rem;border:none;cursor:pointer;background:#059669;color:#fff;"><i class="fa-solid fa-print mr-1"></i> Print</button>
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
    if (!rows.length) {
      return `<table class="casepm-print-table"><tbody><tr><td colspan="${Math.max(columns.length, 1)}" style="text-align:center;padding:16px;color:#666">${esc(emptyMessage || 'No records to print.')}</td></tr></tbody></table>`;
    }
    const head = columns.map(c => `<th${c.width ? ` style="width:${c.width}"` : ''}>${c.label}</th>`).join('');
    const body = rows.map(row => {
      const cells = columns.map(c => {
        const val = typeof c.format === 'function' ? c.format(row) : (row[c.key] ?? '');
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

  function buildPrintDocument(opts) {
    const meta = opts.meta || {};
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });
    const sections = opts.sections || [{ title: opts.title, tableHtml: opts.tableHtml }];
    const pages = [];
    const ROWS_PER_PAGE = opts.rowsPerPage || 28;

    sections.forEach(section => {
      const rows = section.rows || [];
      const columns = section.columns || [];
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
    const loc = meta.location ? `<div style="margin-top:4px;font-size:7pt"><span class="label" style="font-weight:700">LOCATION</span><br>${esc(meta.location)}</div>` : '';
    const sectionNote = sectionContinued ? `<div class="casepm-print-section-title">${esc(title)} (continued)</div>` : '';
    return `
      <div class="casepm-print-header">
        <div>
          <div class="casepm-print-title">${esc(title)}</div>
          ${loc}
        </div>
        <div class="casepm-print-meta">
          ${meta.number ? `<div><span class="label">PROJECT ID</span><br>${esc(meta.number)}</div>` : ''}
          ${meta.name ? `<div style="margin-top:4px"><span class="label">PROJECT NAME</span><br>${esc(meta.name)}</div>` : ''}
        </div>
      </div>
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
    showFieldPicker,
    buildPrintTable,
    buildPrintDocument,
    buildPageBlock,
    triggerPrintPreview,
    openPrintWindow,
  };
})(window);
