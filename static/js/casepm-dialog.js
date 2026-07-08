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
        cursor: move;
      }
      .casepm-drag-handle, dialog .drag-handle {
        cursor: move;
        user-select: none;
      }
      dialog.casepm-dialog.casepm-dragged,
      dialog.casepm-draggable.casepm-dragged {
        transform: none !important;
        margin: 0 !important;
      }
    `;
    document.head.appendChild(style);
  }

  function makeDraggable(el, handleSelector) {
    if (!el || el.dataset.casepmDraggable === '1') return;
    const handle = typeof handleSelector === 'string'
      ? el.querySelector(handleSelector)
      : (handleSelector || el.querySelector('.casepm-drag-handle, .drag-handle, .casepm-dialog-title'));
    if (!handle) return;
    el.dataset.casepmDraggable = '1';
    el.classList.add('casepm-draggable');
    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
    handle.onmousedown = (e) => {
      if (e.button !== 0) return;
      if (e.target.closest('button, input, select, textarea, a, label')) return;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      el.style.position = 'fixed';
      el.style.margin = '0';
      el.style.top = rect.top + 'px';
      el.style.left = rect.left + 'px';
      el.style.transform = 'none';
      el.classList.add('casepm-dragged');
      pos3 = e.clientX;
      pos4 = e.clientY;
      const onUp = () => {
        document.removeEventListener('mouseup', onUp);
        document.removeEventListener('mousemove', onMove);
      };
      const onMove = (ev) => {
        ev.preventDefault();
        pos1 = pos3 - ev.clientX;
        pos2 = pos4 - ev.clientY;
        pos3 = ev.clientX;
        pos4 = ev.clientY;
        el.style.top = (el.offsetTop - pos2) + 'px';
        el.style.left = (el.offsetLeft - pos1) + 'px';
      };
      document.addEventListener('mouseup', onUp);
      document.addEventListener('mousemove', onMove);
    };
  }

  function findDialogHandle(dialog) {
    return dialog.querySelector('.casepm-drag-handle, .drag-handle, .casepm-dialog-title')
      || dialog.querySelector(':scope > div:first-child > div:first-child')
      || dialog.querySelector(':scope > div:first-child');
  }

  function patchDialogElement(dialog) {
    if (!dialog || dialog.tagName !== 'DIALOG' || dialog.dataset.casepmDraggable === '1') return;
    let handle = findDialogHandle(dialog);
    if (handle && !handle.classList.contains('casepm-drag-handle') && !handle.classList.contains('drag-handle')) {
      handle.classList.add('casepm-drag-handle');
    }
    makeDraggable(dialog, handle);
  }

  function initAllDialogs(root) {
    (root || document).querySelectorAll('dialog').forEach(patchDialogElement);
  }

  function observeDialogs() {
    if (global.__casepmDialogObserver) return;
    initAllDialogs();
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((m) => {
        m.addedNodes.forEach((node) => {
          if (node.nodeType !== 1) return;
          if (node.tagName === 'DIALOG') patchDialogElement(node);
          else if (node.querySelectorAll) node.querySelectorAll('dialog').forEach(patchDialogElement);
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
    global.__casepmDialogObserver = observer;
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
      makeDraggable(dialog, '.casepm-dialog-title');
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
      makeDraggable(dialog, '.casepm-dialog-title');
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
    makeDraggable,
    initAllDialogs,
    observeDialogs,
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', observeDialogs);
  } else {
    observeDialogs();
  }
})(window);
