/**
 * Centered Case PM dialogs for the Accounting module (no native prompt/alert).
 */
(function (global) {
  'use strict';

  function dlg() {
    return global.CasePMDialog;
  }

  async function alert(message, type = 'info') {
    if (dlg()?.alert) return dlg().alert(message, type);
    global.alert(message);
  }

  async function confirm(message, options = {}) {
    if (dlg()?.confirm) return dlg().confirm(message, options);
    return global.confirm(message);
  }

  async function prompt(label, defaultValue = '', options = {}) {
    if (dlg()?.prompt) return dlg().prompt(label, defaultValue, options);
    return global.prompt(label, defaultValue);
  }

  async function form(options) {
    if (dlg()?.form) return dlg().form(options);
    return null;
  }

  /** Single required prompt; returns null if cancelled or empty. */
  async function promptRequired(label, defaultValue = '', options = {}) {
    const val = await prompt(label, defaultValue, { label, ...options });
    if (val == null || val === '') return null;
    return val;
  }

  global.CasePMAccountingDialog = {
    alert,
    confirm,
    prompt,
    promptRequired,
    form,
    select: (opts) => (dlg()?.select ? dlg().select(opts) : Promise.resolve(null)),
  };
})(window);
