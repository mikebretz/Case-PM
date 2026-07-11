/**
 * Case PM — accounting-style currency inputs and formatting.
 * Blank by default (no zero placeholder). Right-aligned with .00 cents on blur.
 */
(function (global) {
  'use strict';

  const usdFmt = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function isBlank(value) {
    return value == null || String(value).trim() === '';
  }

  function parseUSD(value) {
    if (isBlank(value)) return null;
    const cleaned = String(value).replace(/[^0-9.-]+/g, '');
    if (!cleaned || cleaned === '-' || cleaned === '.') return null;
    const n = Number(cleaned);
    return Number.isFinite(n) ? n : null;
  }

  function roundCents(n) {
    if (!Number.isFinite(n)) return null;
    return Math.round(n * 100) / 100;
  }

  function formatUSD(amount, options) {
    const opts = options || {};
    const digits = opts.fractionDigits != null ? opts.fractionDigits : 2;
    if (!Number.isFinite(Number(amount))) return '';
    if (digits === 0) {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(Number(amount));
    }
    return usdFmt.format(roundCents(Number(amount)));
  }

  function displayUSD(amount, options) {
    if (isBlank(amount) || !Number.isFinite(Number(amount))) return '—';
    return formatUSD(amount, options);
  }

  function setupMoneyInput(el, options) {
    if (!el || el.dataset.casepmMoneySetup === 'true') return;
    el.dataset.casepmMoneySetup = 'true';
    const opts = options || {};
    const blankZero = opts.blankZero !== false;

    if (!el.classList.contains('casepm-money-input')) {
      el.classList.add('casepm-money-input');
    }
    if (el.type === 'number') el.type = 'text';
    el.setAttribute('inputmode', 'decimal');
    el.setAttribute('autocomplete', 'off');

    const initial = parseUSD(el.value);
    if (initial == null || (blankZero && initial === 0)) {
      el.value = '';
    } else {
      el.value = formatUSD(initial);
    }

    el.addEventListener('focus', function onFocus() {
      const raw = parseUSD(this.value);
      if (raw == null) {
        this.value = '';
        return;
      }
      this.value = String(raw);
      try { this.select(); } catch (_) { /* ignore */ }
    });

    el.addEventListener('blur', function onBlur() {
      const raw = parseUSD(this.value);
      if (raw == null || (blankZero && raw === 0)) {
        this.value = '';
        return;
      }
      this.value = formatUSD(raw);
    });
  }

  function setupMoneyInputs(root) {
    const scope = root || document;
    scope.querySelectorAll('.casepm-money-input, [data-casepm-money]').forEach((el) => setupMoneyInput(el));
  }

  function readMoneyInput(el) {
    return parseUSD(el && el.value);
  }

  function setMoneyInput(el, amount) {
    if (!el) return;
    const n = parseUSD(amount);
    el.value = n == null || n === 0 ? '' : formatUSD(n);
  }

  function appendMoneyToFormData(formData, fieldName, el) {
    const n = readMoneyInput(el);
    if (n == null) formData.set(fieldName, '');
    else formData.set(fieldName, String(roundCents(n)));
  }

  global.CasePMMoney = {
    parseUSD,
    formatUSD,
    displayUSD,
    roundCents,
    setupMoneyInput,
    setupMoneyInputs,
    readMoneyInput,
    setMoneyInput,
    appendMoneyToFormData,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setupMoneyInputs());
  } else {
    setupMoneyInputs();
  }
})(window);
