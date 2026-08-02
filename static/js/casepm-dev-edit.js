/**
 * Case PM — Developer page edit mode helpers (spreadsheet-style overrides).
 * Works with CasePMDeveloperUnlock session flag.
 */
(function (global) {
  'use strict';

  const refreshers = new Set();

  function isActive() {
    return !!(global.CasePMDeveloperUnlock && global.CasePMDeveloperUnlock.isActive());
  }

  function installCanAccessPatch() {
    if (!global.canAccessModule || global.canAccessModule.__casepmDevPatch) return;
    const orig = global.canAccessModule;
    global.canAccessModule = function casepmCanAccessModuleDev(moduleKey, minAccess) {
      if (global.CASEPM_IS_DEVELOPER && isActive()) return true;
      return orig(moduleKey, minAccess);
    };
    global.canAccessModule.__casepmDevPatch = true;
  }

  function notifyRefreshers(active) {
    refreshers.forEach((fn) => {
      try { fn(!!active); } catch (err) { console.error(err); }
    });
  }

  function onUnlockChanged(ev) {
    installCanAccessPatch();
    notifyRefreshers(ev?.detail?.active ?? isActive());
  }

  global.casepmDevEditActive = isActive;
  global.CasePMDevEdit = {
    isActive,
    registerRefresh(fn) {
      if (typeof fn === 'function') refreshers.add(fn);
    },
    installCanAccessPatch,
  };

  global.addEventListener('casepm:developer-unlock-changed', onUnlockChanged);
  document.addEventListener('DOMContentLoaded', () => {
    installCanAccessPatch();
    if (isActive()) notifyRefreshers(true);
  });
})(typeof window !== 'undefined' ? window : globalThis);
