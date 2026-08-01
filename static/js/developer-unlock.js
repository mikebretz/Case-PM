/**
 * Case PM — Developer unlock edit mode (global)
 * When active, unlocks readonly/disabled fields and bypasses client-side lock checks.
 */
(function (global) {
  'use strict';

  let active = !!global.CASEPM_DEVELOPER_UNLOCK;

  function setBannerVisible(on) {
    const banner = document.getElementById('devUnlockBanner');
    if (!banner) return;
    banner.classList.toggle('hidden', !on);
    document.documentElement.classList.toggle('dev-unlock-active', on);
  }

  function updateToggleControls(on) {
    document.querySelectorAll('[data-dev-unlock-toggle]').forEach((btn) => {
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.classList.toggle('dev-unlock-toggle--on', on);
      const label = btn.querySelector('[data-dev-unlock-label]');
      if (label) {
        label.textContent = on ? 'Edit mode: ON' : 'Edit mode: OFF';
      }
      const icon = btn.querySelector('[data-dev-unlock-icon]');
      if (icon) {
        icon.classList.toggle('fa-lock-open', on);
        icon.classList.toggle('fa-pen-to-square', !on);
      }
    });
  }

  function unlockElement(el) {
    if (!el || el.dataset.devUnlockSkip === '1') return;
    if (el.hasAttribute('readonly')) {
      el.removeAttribute('readonly');
      el.dataset.devWasReadonly = '1';
    }
    if (el.getAttribute('contenteditable') === 'false') {
      el.setAttribute('contenteditable', 'true');
      el.dataset.devWasContenteditable = '1';
    }
    if (el.getAttribute('aria-readonly') === 'true') {
      el.setAttribute('aria-readonly', 'false');
      el.dataset.devWasAriaReadonly = '1';
    }
    if (el.disabled && el.dataset.devWasDisabled !== '1') {
      el.disabled = false;
      el.dataset.devUnlockedDisabled = '1';
    }
    el.classList.remove(
      'pointer-events-none',
      'opacity-60',
      'opacity-50',
      'cursor-not-allowed',
      'select-none',
      'dev-readonly',
      'read-only'
    );
    if (el.dataset.readonly === '1' || el.dataset.readonly === 'true') {
      el.dataset.devWasDataReadonly = '1';
      delete el.dataset.readonly;
    }
  }

  function sweep(root) {
    if (!active) return;
    const scope = root || document;
    const selectors = [
      'input[readonly]',
      'textarea[readonly]',
      'select[disabled]',
      'input[disabled]',
      'button[disabled]',
      '[data-dev-lock="1"]',
      '[data-readonly="1"]',
      '[data-readonly="true"]',
      '[contenteditable="false"]',
      '[aria-readonly="true"]',
      '.dev-readonly input',
      '.dev-readonly textarea',
      '.dev-readonly select',
      'table.alloc-sheet input',
      'table.alloc-sheet select',
      '#contractorSOVTableBody input',
      '#subSOVTableBody input',
      'table[data-spreadsheet="1"] input',
      'table[data-spreadsheet="1"] select',
      'table[data-spreadsheet="1"] textarea',
    ];
    scope.querySelectorAll(selectors.join(', ')).forEach(unlockElement);
  }

  function notify() {
    global.CASEPM_DEVELOPER_UNLOCK = active;
    setBannerVisible(active);
    updateToggleControls(active);
    sweep(document);
    global.dispatchEvent(new CustomEvent('casepm:developer-unlock-changed', { detail: { active } }));
  }

  function bindToggleButtons() {
    document.querySelectorAll('[data-dev-unlock-toggle]').forEach((btn) => {
      if (btn.dataset.devUnlockBound === '1') return;
      btn.dataset.devUnlockBound = '1';
      btn.addEventListener('click', async (ev) => {
        ev.preventDefault();
        const next = !isActive();
        try {
          await setActive(next);
        } catch (e) {
          alert(e.message || 'Could not change edit mode');
        }
      });
    });
  }

  async function syncFromServer() {
    if (!global.CASEPM_IS_DEVELOPER) return active;
    try {
      const res = await fetch('/api/developer/unlock-mode', { credentials: 'same-origin' });
      if (!res.ok) return active;
      const json = await res.json();
      active = !!json.active;
      notify();
    } catch (_) { /* ignore */ }
    return active;
  }

  async function setActive(on, opts) {
    active = !!on;
    if (!opts?.skipServer && global.CASEPM_IS_DEVELOPER) {
      try {
        const res = await fetch('/api/developer/unlock-mode', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active }),
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(json.error || 'Request failed');
        active = !!json.active;
      } catch (e) {
        active = !on;
        throw e;
      }
    }
    notify();
    return active;
  }

  function isActive() {
    return active;
  }

  function observe() {
    if (!global.MutationObserver) return;
    const obs = new MutationObserver(muts => {
      if (!active) return;
      muts.forEach(m => {
        m.addedNodes.forEach(node => {
          if (node.nodeType === 1) sweep(node);
        });
      });
    });
    obs.observe(document.documentElement, { childList: true, subtree: true });
  }

  const api = {
    isActive,
    setActive,
    syncFromServer,
    sweep,
  };

  global.CasePMDeveloperUnlock = api;

  document.addEventListener('DOMContentLoaded', () => {
    bindToggleButtons();
    notify();
    if (global.CASEPM_IS_DEVELOPER) syncFromServer();
    observe();
  });
})(typeof window !== 'undefined' ? window : globalThis);
