/**
 * Case PM — unified Print / Save to file / Save to Documents / Export output.
 */
(function (global) {
  'use strict';

  const STYLE_ID = 'casepm-output-styles';

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return parseInt(global.CASEPM_ACTIVE_PROJECT_ID, 10) || null;
    try {
      return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null;
    } catch (_) {
      return null;
    }
  }

  function projectName() {
    const el = document.getElementById('currentProjectName');
    if (el && el.textContent.trim()) return el.textContent.trim();
    if (global.CASEPM_ACTIVE_PROJECT_NAME) return global.CASEPM_ACTIVE_PROJECT_NAME;
    return 'Project';
  }

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      dialog.casepm-output-dialog {
        margin: auto !important;
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        border: none;
        padding: 0;
        background: transparent;
        color: #fff;
        max-width: min(480px, 94vw);
        width: min(480px, 94vw);
        z-index: 1000002;
      }
      dialog.casepm-output-dialog::backdrop { background: rgba(0,0,0,0.72); }
      .casepm-output-panel {
        background: #18181b;
        border: 1px solid #3f3f46;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 25px 50px -12px rgba(0,0,0,0.55);
      }
      .casepm-output-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1rem 1.25rem;
        border-bottom: 1px solid #3f3f46;
        font-weight: 600;
      }
      .casepm-output-body { padding: 1rem 1.25rem; }
      .casepm-output-note { font-size: 0.75rem; color: #a1a1aa; line-height: 1.45; margin-bottom: 0.75rem; }
      .casepm-output-actions { display: flex; flex-direction: column; gap: 0.5rem; padding: 0 1.25rem 1.25rem; }
      .casepm-output-btn {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        width: 100%;
        text-align: left;
        padding: 0.75rem 1rem;
        border-radius: 0.5rem;
        border: 1px solid #3f3f46;
        background: #27272a;
        color: #e4e4e7;
        cursor: pointer;
        font-size: 0.875rem;
      }
      .casepm-output-btn:hover { background: #3f3f46; border-color: #52525b; }
      .casepm-output-btn i { width: 1.25rem; text-align: center; }
      .casepm-output-btn small { display: block; font-size: 0.7rem; color: #a1a1aa; margin-top: 2px; }
      .casepm-output-btn.primary { background: #059669; border-color: #059669; color: #fff; }
      .casepm-output-btn.primary:hover { background: #047857; }
      .casepm-output-cancel {
        margin-top: 0.25rem;
        text-align: center;
        font-size: 0.8rem;
        color: #a1a1aa;
        background: transparent;
        border: none;
        cursor: pointer;
        padding: 0.5rem;
      }
      .casepm-output-cancel:hover { color: #fff; }
    `;
    document.head.appendChild(style);
  }

  function toast(msg, isError) {
    if (global.showToast) {
      global.showToast(msg, isError ? 'error' : 'success');
      return;
    }
    if (global.CasePMDialog && global.CasePMDialog.alert) {
      global.CasePMDialog.alert(msg);
      return;
    }
    alert(msg);
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '');
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  function wrapHtmlDocument(title, bodyInner) {
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
<style>body{font-family:Arial,Helvetica,sans-serif;margin:24px;color:#111}@media print{body{margin:0.5in}}</style></head>
<body>${bodyInner}</body></html>`;
  }

  function extensionForMime(mime) {
    const m = {
      'application/pdf': 'pdf',
      'text/html': 'html',
      'text/plain': 'txt',
      'text/csv': 'csv',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
      'application/vnd.ms-excel': 'xls',
    };
    return m[(mime || '').toLowerCase()] || 'bin';
  }

  function filenameWithExt(base, mime, explicit) {
    const name = (base || 'export').replace(/[<>:"/\\|?*]+/g, '_');
    if (explicit) return explicit.includes('.') ? explicit : `${explicit}.${extensionForMime(mime)}`;
    const ext = extensionForMime(mime);
    return name.toLowerCase().endsWith('.' + ext) ? name : `${name}.${ext}`;
  }

  async function apiSaveOutput(payload) {
    const r = await fetch('/api/documents/save-output', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || 'Could not save to Documents');
    return j;
  }

  async function saveToDocuments({ name, blob, mimeType, sourceModule, systemFolderKey, subfolder }) {
    const pid = projectId();
    if (!pid) throw new Error('Select a project first to save to Documents.');
    const b64 = await blobToBase64(blob);
    const j = await apiSaveOutput({
      project_id: pid,
      name: name || 'Exported document',
      file_base64: b64,
      mime_type: mimeType || blob.type || 'application/octet-stream',
      source_module: sourceModule || 'export',
      system_folder_key: systemFolderKey || 'printed-output',
      subfolder: subfolder || null,
    });
    const docName = j.document?.name || name;
    const folder = subfolder ? `Documents › ${systemFolderKey || 'Printed Output'} › ${subfolder}` : 'Documents › Printed Output';
    toast(`Saved "${docName}" to ${folder}`);
    return j;
  }

  function printHtml(html, options) {
    const opts = options || {};
    if (opts.bodyHtml && global.CasePMPrint && global.CasePMPrint.triggerPrintPreview) {
      global.CasePMPrint.triggerPrintPreview(opts.bodyHtml, {
        containerId: opts.containerId || 'casepmPrintRoot',
        bodyClass: opts.bodyClass || 'casepm-printing',
      });
      return;
    }
    const doc = html.includes('<!DOCTYPE') || html.includes('<html') ? html : wrapHtmlDocument(opts.title || 'Print', html);
    if (global.CasePMPrint && global.CasePMPrint.printHtmlInIframe) {
      global.CasePMPrint.printHtmlInIframe(doc, { landscape: opts.landscape !== false, delay: opts.delay || 400 });
      return;
    }
    const w = window.open('', '_blank');
    if (!w) {
      toast('Allow pop-ups to print, or use Save to Documents.', true);
      return;
    }
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
  }

  function showOutputDialog(options) {
    ensureStyles();
    const opts = options || {};
    const title = opts.title || 'Output';
    const modes = opts.modes || ['print', 'file', 'documents'];
    const note = opts.note || 'Choose where to send this output. Use <b>Save as file</b> to download to your computer (or pick &ldquo;Save as PDF&rdquo; in the print dialog).';

    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = 'casepm-output-dialog';
      const buttons = [];
      if (modes.includes('print')) {
        buttons.push(`<button type="button" class="casepm-output-btn primary" data-action="print"><i class="fa-solid fa-print"></i><span><strong>Print</strong><small>Send to your printer or Save as PDF in the print dialog</small></span></button>`);
      }
      if (modes.includes('file')) {
        buttons.push(`<button type="button" class="casepm-output-btn" data-action="file"><i class="fa-solid fa-file-arrow-down"></i><span><strong>Save as file</strong><small>Download to your computer (${esc(opts.fileLabel || 'HTML, Excel, CSV, or PDF')})</small></span></button>`);
      }
      if (modes.includes('documents')) {
        buttons.push(`<button type="button" class="casepm-output-btn" data-action="documents"><i class="fa-solid fa-folder-tree"></i><span><strong>Save to Documents</strong><small>File into this project&rsquo;s Documents › Printed Output</small></span></button>`);
      }
      if (opts.importFromDocuments) {
        buttons.push(`<button type="button" class="casepm-output-btn" data-action="import"><i class="fa-solid fa-file-import"></i><span><strong>Import from Documents</strong><small>Pick an existing project file</small></span></button>`);
      }

      dialog.innerHTML = `
        <div class="casepm-output-panel">
          <div class="casepm-output-title">
            <span><i class="fa-solid fa-share-from-square text-emerald-400 mr-2"></i>${esc(title)}</span>
            <button type="button" data-action="cancel" class="text-zinc-400 hover:text-white bg-transparent border-0 cursor-pointer text-lg">&times;</button>
          </div>
          <div class="casepm-output-body">
            <p class="casepm-output-note">${note}</p>
          </div>
          <div class="casepm-output-actions">
            ${buttons.join('')}
            <button type="button" class="casepm-output-cancel" data-action="cancel">Cancel</button>
          </div>
        </div>`;

      document.body.appendChild(dialog);
      dialog.showModal();
      const finish = (val) => { dialog.close(); dialog.remove(); resolve(val); };
      dialog.querySelectorAll('[data-action]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const action = btn.getAttribute('data-action');
          if (action === 'cancel') finish(null);
          else finish(action);
        });
      });
      dialog.addEventListener('cancel', (e) => { e.preventDefault(); finish(null); });
    });
  }

  async function deliver(opts) {
    const choice = await showOutputDialog(opts);
    if (!choice) return null;
    try {
      if (choice === 'import' && typeof opts.onImport === 'function') {
        return await opts.onImport();
      }
      if (choice === 'print') {
        if (typeof opts.onPrint === 'function') await opts.onPrint();
        else if (opts.html) printHtml(opts.html, opts.printOptions || {});
        else if (opts.getHtml) printHtml(await opts.getHtml(), opts.printOptions || {});
        return { action: 'print' };
      }
      if (choice === 'file') {
        let blob = opts.blob || null;
        let mime = opts.mimeType || 'text/html';
        let filename = opts.filename || null;
        if (!blob && typeof opts.getBlob === 'function') {
          const built = await opts.getBlob();
          blob = built.blob;
          mime = built.mimeType || mime;
          filename = built.filename || filename;
        }
        if (!blob && opts.html) {
          const html = opts.html.includes('<!DOCTYPE') ? opts.html : wrapHtmlDocument(opts.title || 'Export', opts.html);
          blob = new Blob([html], { type: 'text/html;charset=utf-8' });
          mime = 'text/html';
        } else if (!blob && typeof opts.getHtml === 'function') {
          const html = await opts.getHtml();
          const doc = html.includes('<!DOCTYPE') ? html : wrapHtmlDocument(opts.title || 'Export', html);
          blob = new Blob([doc], { type: 'text/html;charset=utf-8' });
          mime = 'text/html';
        }
        if (!blob) throw new Error('Nothing to download');
        downloadBlob(blob, filenameWithExt(opts.filenameBase || opts.title || 'export', mime, filename));
        toast('Download started');
        return { action: 'file' };
      }
      if (choice === 'documents') {
        let blob = opts.blob || null;
        let mime = opts.mimeType || 'text/html';
        if (!blob && typeof opts.getBlob === 'function') {
          const built = await opts.getBlob();
          blob = built.blob;
          mime = built.mimeType || mime;
        }
        if (!blob && opts.html) {
          const html = opts.html.includes('<!DOCTYPE') ? opts.html : wrapHtmlDocument(opts.title || 'Export', opts.html);
          blob = new Blob([html], { type: 'text/html;charset=utf-8' });
          mime = 'text/html';
        } else if (!blob && typeof opts.getHtml === 'function') {
          const html = await opts.getHtml();
          const doc = html.includes('<!DOCTYPE') ? html : wrapHtmlDocument(opts.title || 'Export', html);
          blob = new Blob([doc], { type: 'text/html;charset=utf-8' });
          mime = 'text/html';
        }
        if (!blob) throw new Error('Nothing to save');
        const j = await saveToDocuments({
          name: opts.filenameBase || opts.title || 'Export',
          blob,
          mimeType: mime,
          sourceModule: opts.sourceModule || 'export',
          systemFolderKey: opts.systemFolderKey || 'printed-output',
          subfolder: opts.subfolder || null,
        });
        return { action: 'documents', document: j.document };
      }
    } catch (e) {
      toast(e.message || String(e), true);
      return null;
    }
    return null;
  }

  async function deliverHtml(opts) {
    const userOnPrint = opts.onPrint;
    return deliver({
      ...opts,
      onPrint: async () => {
        if (typeof userOnPrint === 'function') {
          await userOnPrint();
          return;
        }
        const html = opts.html || (typeof opts.getHtml === 'function' ? await opts.getHtml() : '');
        if (opts.printOptions && opts.printOptions.bodyHtml) {
          printHtml(null, opts.printOptions);
        } else {
          printHtml(html, { title: opts.title, ...opts.printOptions });
        }
      },
    });
  }

  async function deliverBlob(opts) {
    return deliver({
      title: opts.title || 'Export',
      modes: opts.modes || ['file', 'documents'],
      fileLabel: opts.fileLabel || (opts.mimeType || '').includes('sheet') ? 'Excel (.xlsx)' : 'File download',
      blob: opts.blob,
      mimeType: opts.mimeType,
      filename: opts.filename,
      filenameBase: opts.filenameBase,
      sourceModule: opts.sourceModule,
      systemFolderKey: opts.systemFolderKey,
      subfolder: opts.subfolder,
      getBlob: opts.getBlob,
    });
  }

  function importFromDocuments(pickOpts) {
    if (!global.CasePMDocPicker || !global.CasePMDocPicker.open) {
      toast('Document picker not available', true);
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      global.CasePMDocPicker.open({
        title: pickOpts?.title || 'Import from Documents',
        multiple: pickOpts?.multiple !== false,
        projectId: pickOpts?.projectId || projectId(),
        onPick: (files) => resolve(files),
      });
    });
  }

  async function showImportDialog(opts) {
    const choice = await showOutputDialog({
      title: opts.title || 'Import',
      note: opts.note || 'Import a file from your computer or pick one already filed in Documents.',
      modes: [],
      importFromDocuments: true,
    });
    if (choice === 'import') {
      const files = await importFromDocuments(opts);
      if (files && files.length && typeof opts.onPick === 'function') {
        await opts.onPick(files);
      }
      return files;
    }
    return null;
  }

  function bindFileInput(input, handler, accept) {
    if (!input) return;
    if (accept) input.setAttribute('accept', accept);
    input.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = '';
      if (file && handler) await handler(file);
    });
  }

  async function promptImport(opts) {
    ensureStyles();
    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = 'casepm-output-dialog';
      dialog.innerHTML = `
        <div class="casepm-output-panel">
          <div class="casepm-output-title">
            <span><i class="fa-solid fa-file-import text-sky-400 mr-2"></i>${esc(opts.title || 'Import')}</span>
            <button type="button" data-action="cancel" class="text-zinc-400 hover:text-white bg-transparent border-0 cursor-pointer text-lg">&times;</button>
          </div>
          <div class="casepm-output-body"><p class="casepm-output-note">${opts.note || 'Import from your computer or from project Documents.'}</p></div>
          <div class="casepm-output-actions">
            <button type="button" class="casepm-output-btn" data-action="browse"><i class="fa-solid fa-upload"></i><span><strong>Browse computer</strong><small>Select a file from this device</small></span></button>
            <button type="button" class="casepm-output-btn" data-action="documents"><i class="fa-solid fa-folder-tree"></i><span><strong>From Documents</strong><small>Use a file already on this project</small></span></button>
            <button type="button" class="casepm-output-cancel" data-action="cancel">Cancel</button>
          </div>
        </div>`;
      document.body.appendChild(dialog);
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.className = 'hidden';
      if (opts.accept) fileInput.accept = opts.accept;
      document.body.appendChild(fileInput);
      const finish = (val) => { dialog.close(); dialog.remove(); fileInput.remove(); resolve(val); };
      dialog.querySelector('[data-action="browse"]').onclick = () => fileInput.click();
      fileInput.onchange = async () => {
        const f = fileInput.files && fileInput.files[0];
        if (f && opts.onFile) await opts.onFile(f);
        finish(f || null);
      };
      dialog.querySelector('[data-action="documents"]').onclick = async () => {
        dialog.close();
        const files = await importFromDocuments(opts);
        if (files && files.length && opts.onDocuments) {
          if (opts.downloadFromDocuments !== false) {
            const picked = [];
            for (const doc of files) {
              try { picked.push(await fetchDocumentFile(doc)); } catch (e) { toast(e.message, true); }
            }
            if (picked.length) await opts.onDocuments(picked, files);
          } else {
            await opts.onDocuments(files);
          }
        }
        dialog.remove();
        fileInput.remove();
        resolve(files);
      };
      dialog.querySelectorAll('[data-action="cancel"]').forEach((b) => b.onclick = () => finish(null));
      dialog.addEventListener('cancel', (e) => { e.preventDefault(); finish(null); });
      dialog.showModal();
    });
  }

  function htmlFromElement(element, title) {
    if (!element) return wrapHtmlDocument(title || 'Export', '');
    return wrapHtmlDocument(title || 'Export', element.innerHTML);
  }

  async function fetchDocumentFile(doc) {
    const url = doc.download_url || `/api/documents/${doc.id}/download`;
    const r = await fetch(url, { credentials: 'same-origin' });
    if (!r.ok) throw new Error('Could not download file from Documents');
    const blob = await r.blob();
    const name = doc.name || doc.filename || `document-${doc.id}`;
    return new File([blob], name, { type: blob.type || 'application/octet-stream' });
  }

  global.CasePMOutput = {
    projectId,
    projectName,
    esc,
    wrapHtmlDocument,
    htmlFromElement,
    fetchDocumentFile,
    downloadBlob,
    blobToBase64,
    saveToDocuments,
    printHtml,
    showOutputDialog,
    deliver,
    deliverHtml,
    deliverBlob,
    importFromDocuments,
    showImportDialog,
    promptImport,
    bindFileInput,
    filenameWithExt,
  };
})(window);
