/**
 * Developer maintenance actions — queue module-specific tools from Developer Console.
 */
(function (global) {
  'use strict';

  const STORAGE_KEY = 'casepm_dev_action';

  function queue(action, path) {
    sessionStorage.setItem(STORAGE_KEY, action);
    window.location.href = path || '/';
  }

    function consume(action, fn) {
    if (!global.CASEPM_IS_DEVELOPER && document.body?.dataset?.isDeveloper !== '1') return;
    const pending = sessionStorage.getItem(STORAGE_KEY);
    if (pending !== action) return;
    sessionStorage.removeItem(STORAGE_KEY);
    try { fn(); } catch (err) { console.error(err); alert(err.message || String(err)); }
  }

  function consumeAny(map) {
    if (!global.CASEPM_IS_DEVELOPER && document.body?.dataset?.isDeveloper !== '1') return;
    const pending = sessionStorage.getItem(STORAGE_KEY);
    if (!pending || !map[pending]) return;
    sessionStorage.removeItem(STORAGE_KEY);
    try { map[pending](); } catch (err) { console.error(err); alert(err.message || String(err)); }
  }

  global.CasePMDevActions = { queue, consume, consumeAny };
})(window);
