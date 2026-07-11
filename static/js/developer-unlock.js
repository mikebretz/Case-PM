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

  function unlockElement(el) {
    if (!el || el.dataset.devUnlockSkip === '1') return;
    if (el.hasAttribute('readonly')) {
      el.removeAttribute('readonly');
      el.dataset.devWasReadonly = '1';
    }
    if (el.disabled && el.dataset.devWasDisabled !== '1') {
      el.disabled = false;
      el.dataset.devUnlockedDisabled = '1';
    }
    el.classList.remove('pointer-events-none', 'opacity-60');
  }

  function sweep(root) {
    if (!active) return;
    const scope = root || document;
    scope.querySelectorAll('input[readonly], textarea[readonly], select[disabled], input[disabled], [data-dev-lock="1"]').forEach(unlockElement);
    scope.querySelectorAll('table.alloc-sheet input, table.alloc-sheet select, #contractorSOVTableBody input, #subSOVTableBody input').forEach(unlockElement);
  }

  function notify() {
    global.CASEPM_DEVELOPER_UNLOCK = active;
    setBannerVisible(active);
    sweep(document);
    global.dispatchEvent(new CustomEvent('casepm:developer-unlock-changed', { detail: { active } }));
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
    notify();
    if (global.CASEPM_IS_DEVELOPER) syncFromServer();
    observe();
  });
})(typeof window !== 'undefined' ? window : globalThis);
