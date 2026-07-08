/**
 * Case PM — shared log print with field picker (popup window, no app chrome).
 */
(function (global) {
  'use strict';

  const STYLE_ID = 'casepm-print-picker-styles';

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
    `;
    document.head.appendChild(style);
  }

  const PRINT_DOC_CSS = `
    @page { size: landscape; margin: 0.35in 0.4in; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 8pt;
      color: #111;
      background: #fff;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .casepm-print-page { page-break-after: always; break-after: page; }
    .casepm-print-page:last-child { page-break-after: auto; break-after: auto; }
    .casepm-print-header {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px 16px;
      align-items: start;
      margin-bottom: 8px;
      border-bottom: 2px solid #111;
      padding-bottom: 6px;
    }
    .casepm-print-title { font-size: 16pt; font-weight: 700; color: #111; line-height: 1.1; }
    .casepm-print-meta { text-align: right; font-size: 7pt; line-height: 1.35; color: #222; }
    .casepm-print-meta .label {
      font-weight: 700;
      text-transform: uppercase;
      font-size: 6pt;
      color: #444;
    }
    .casepm-print-table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 7pt;
      line-height: 1.2;
    }
    .casepm-print-table th, .casepm-print-table td {
      border: 1px solid #333;
      padding: 2px 4px;
      vertical-align: top;
      word-wrap: break-word;
      overflow-wrap: anywhere;
    }
    .casepm-print-table th {
      background: #f0f0f0;
      font-weight: 700;
      text-align: center;
      font-size: 6pt;
      text-transform: uppercase;
    }
    .casepm-print-table td.c { text-align: center; }
    .casepm-print-table td.r { text-align: right; }
    .casepm-print-footer {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      margin-top: 8px;
      padding-top: 4px;
      border-top: 1px solid #999;
      font-size: 7pt;
      color: #444;
    }
    .casepm-print-footer .center { text-align: center; }
    .casepm-print-footer .right { text-align: right; }
    .casepm-print-section-title {
      font-size: 11pt;
      font-weight: 700;
      margin: 12px 0 6px;
      color: #111;
    }
  `;

  function showFieldPicker(options) {
    ensureStyles();
    const fields = options.fields || [];
    const logTypes = options.logTypes || null;
    const title = options.title || 'Print Log';
    const defaultLogType = options.defaultLogType || (logTypes ? logTypes[0].value : null);

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
            <div class="casepm-print-toolbar">
              <button type="button" data-action="all">Select All</button>
              <button type="button" data-action="none">Clear All</button>
              <button type="button" data-action="default">Defaults</button>
            </div>
            <div class="casepm-print-field-grid">
              ${fields.map(f => `
                <label><input type="checkbox" data-field="${esc(f.key)}" ${f.default !== false ? 'checked' : ''}> ${esc(f.label)}</label>
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

      dialog.querySelector('[data-action="all"]').onclick = () => boxes().forEach(b => { b.checked = true; });
      dialog.querySelector('[data-action="none"]').onclick = () => boxes().forEach(b => { b.checked = false; });
      dialog.querySelector('[data-action="default"]').onclick = () => {
        boxes().forEach(b => {
          const f = fields.find(x => x.key === b.dataset.field);
          b.checked = f ? f.default !== false : true;
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
    const head = columns.map(c => `<th${c.width ? ` style="width:${c.width}"` : ''}>${esc(c.label)}</th>`).join('');
    const body = rows.map(row => {
      const cells = columns.map(c => {
        const val = typeof c.format === 'function' ? c.format(row) : (row[c.key] ?? '');
        const cls = c.align === 'center' ? ' class="c"' : (c.align === 'right' ? ' class="r"' : '');
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
        pages.push({
          title: section.title,
          html: buildPageBlock(meta, section.title, buildPrintTable(columns, [], section.emptyMessage), printedOn, 1, 1),
        });
        return;
      }
      const totalPages = Math.ceil(rows.length / ROWS_PER_PAGE);
      for (let p = 0; p < totalPages; p++) {
        const chunk = rows.slice(p * ROWS_PER_PAGE, (p + 1) * ROWS_PER_PAGE);
        const tableHtml = buildPrintTable(columns, chunk);
        pages.push({
          title: section.title,
          html: buildPageBlock(meta, section.title, tableHtml, printedOn, p + 1, totalPages, p > 0),
        });
      }
    });

    return pages.map((p, i) => `<div class="casepm-print-page">${p.html}</div>`).join('');
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
          <div style="margin-top:4px"><span class="label">PRINTED</span><br>${esc(printedOn)}</div>
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

  function openPrintWindow(bodyHtml, docTitle) {
    const w = window.open('', '_blank');
    if (!w) {
      if (global.CasePMDialog) global.CasePMDialog.alert('Pop-up blocked. Allow pop-ups to print this log.');
      else alert('Pop-up blocked. Allow pop-ups to print this log.');
      return null;
    }
    w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(docTitle || 'Print')}</title><style>${PRINT_DOC_CSS}</style></head><body>${bodyHtml}</body></html>`);
    w.document.close();
    w.focus();
    setTimeout(() => { w.print(); }, 450);
    return w;
  }

  global.CasePMPrint = {
    esc,
    showFieldPicker,
    buildPrintTable,
    buildPrintDocument,
    openPrintWindow,
    PRINT_DOC_CSS,
  };
})(window);
