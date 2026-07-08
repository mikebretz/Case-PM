/**
 * Case PM — centered alert/confirm dialogs (replaces browser alert/confirm styling app-wide).
 */
(function (global) {
  'use strict';

  const STYLE_ID = 'casepm-dialog-styles';

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      dialog.casepm-dialog {
        margin: auto !important;
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        border: none;
        padding: 0;
        background: transparent;
        color: #fff;
        max-width: min(520px, 92vw);
        width: min(520px, 92vw);
        z-index: 1000000;
      }
      dialog.casepm-dialog::backdrop {
        background: rgba(0, 0, 0, 0.72);
      }
      .casepm-dialog-panel {
        background: #18181b;
        border: 1px solid #3f3f46;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.55);
      }
      .casepm-dialog-body {
        padding: 1.25rem 1.5rem;
        font-size: 0.9375rem;
        line-height: 1.5;
        color: #e4e4e7;
        white-space: pre-wrap;
      }
      .casepm-dialog-actions {
        display: flex;
        justify-content: flex-end;
        gap: 0.5rem;
        padding: 0.875rem 1.25rem;
        background: #09090b;
        border-top: 1px solid #3f3f46;
      }
      .casepm-dialog-btn {
        padding: 0.5rem 1.25rem;
        border-radius: 0.375rem;
        font-size: 0.875rem;
        font-weight: 500;
        border: none;
        cursor: pointer;
      }
      .casepm-dialog-btn-primary {
        background: #059669;
        color: #fff;
      }
      .casepm-dialog-btn-primary:hover { background: #10b981; }
      .casepm-dialog-btn-secondary {
        background: #3f3f46;
        color: #e4e4e7;
      }
      .casepm-dialog-btn-secondary:hover { background: #52525b; }
      .casepm-dialog-btn-danger {
        background: #dc2626;
        color: #fff;
      }
      .casepm-dialog-btn-danger:hover { background: #ef4444; }
      .casepm-dialog-title {
        display: flex;
        align-items: center;
        gap: 0.625rem;
        padding: 1rem 1.5rem;
        border-bottom: 1px solid #3f3f46;
        font-weight: 600;
        font-size: 1rem;
      }
    `;
    document.head.appendChild(style);
  }

  function iconForType(type) {
    if (type === 'success') return '<i class="fa-solid fa-check-circle text-emerald-400"></i>';
    if (type === 'warning') return '<i class="fa-solid fa-exclamation-triangle text-amber-400"></i>';
    if (type === 'error') return '<i class="fa-solid fa-circle-xmark text-red-400"></i>';
    return '<i class="fa-solid fa-circle-info text-sky-400"></i>';
  }

  function titleForType(type) {
    if (type === 'success') return 'Success';
    if (type === 'warning') return 'Notice';
    if (type === 'error') return 'Error';
    return 'Case PM';
  }

  function closeDialog(dialog, result) {
    dialog.close();
    dialog.remove();
    return result;
  }

  function showCenteredAlert(message, type = 'info') {
    ensureStyles();
    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = 'casepm-dialog';
      dialog.innerHTML = `
        <div class="casepm-dialog-panel">
          <div class="casepm-dialog-title">${iconForType(type)}<span>${titleForType(type)}</span></div>
          <div class="casepm-dialog-body">${escapeHtml(String(message ?? ''))}</div>
          <div class="casepm-dialog-actions">
            <button type="button" class="casepm-dialog-btn casepm-dialog-btn-primary" data-action="ok">OK</button>
          </div>
        </div>`;
      document.body.appendChild(dialog);
      dialog.showModal();
      dialog.querySelector('[data-action="ok"]').onclick = () => resolve(closeDialog(dialog, true));
      dialog.addEventListener('cancel', (e) => {
        e.preventDefault();
        resolve(closeDialog(dialog, true));
      });
    });
  }

  function showCenteredConfirm(message, options = {}) {
    ensureStyles();
    const title = options.title || 'Confirm';
    const confirmLabel = options.confirmLabel || 'OK';
    const cancelLabel = options.cancelLabel || 'Cancel';
    const danger = !!options.danger;
    return new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = 'casepm-dialog';
      dialog.innerHTML = `
        <div class="casepm-dialog-panel">
          <div class="casepm-dialog-title">${iconForType(danger ? 'warning' : 'info')}<span>${escapeHtml(title)}</span></div>
          <div class="casepm-dialog-body">${escapeHtml(String(message ?? ''))}</div>
          <div class="casepm-dialog-actions">
            <button type="button" class="casepm-dialog-btn casepm-dialog-btn-secondary" data-action="cancel">${escapeHtml(cancelLabel)}</button>
            <button type="button" class="casepm-dialog-btn ${danger ? 'casepm-dialog-btn-danger' : 'casepm-dialog-btn-primary'}" data-action="confirm">${escapeHtml(confirmLabel)}</button>
          </div>
        </div>`;
      document.body.appendChild(dialog);
      dialog.showModal();
      dialog.querySelector('[data-action="cancel"]').onclick = () => resolve(closeDialog(dialog, false));
      dialog.querySelector('[data-action="confirm"]').onclick = () => resolve(closeDialog(dialog, true));
      dialog.addEventListener('cancel', (e) => {
        e.preventDefault();
        resolve(closeDialog(dialog, false));
      });
    });
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  global.CasePMDialog = {
    alert: showCenteredAlert,
    confirm: showCenteredConfirm,
  };

  // Route native alert() through centered dialog app-wide.
  global.showCenteredAlert = showCenteredAlert;
  if (!global.__casepmAlertPatched) {
    global.__casepmNativeAlert = global.alert.bind(global);
    global.alert = function (message) {
      showCenteredAlert(String(message ?? ''), 'info');
    };
    global.__casepmAlertPatched = true;
  }
})(window);
