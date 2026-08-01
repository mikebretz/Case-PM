/**
 * Ensures saves and API calls target the active project shown in the header.
 */
(function (global) {
  'use strict';

  function activeProjectIdFromDom() {
    const raw = document.body?.getAttribute('data-active-project-id')
      || global.CASEPM_ACTIVE_PROJECT_ID
      || '';
    const id = parseInt(raw, 10);
    return id > 0 ? id : null;
  }

  function assertProjectMatch(expectedId, context) {
    const active = activeProjectIdFromDom();
    if (!active || !expectedId) return true;
    if (parseInt(expectedId, 10) !== active) {
      const msg = `This action is for a different project than "${document.body?.getAttribute('data-active-project-name') || 'current'}". Switch projects and try again.`;
      console.warn('[CasePM] Project guard:', context, { expectedId, active });
      if (global.CasePMDialog?.alert) global.CasePMDialog.alert(msg, 'warning');
      else alert(msg);
      return false;
    }
    return true;
  }

  function installFetchGuard() {
    if (global.__casepmFetchGuardInstalled) return;
    global.__casepmFetchGuardInstalled = true;
    const orig = global.fetch.bind(global);
    global.fetch = function casepmFetch(input, init) {
      try {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const method = ((init && init.method) || 'GET').toUpperCase();
        if (method !== 'GET' && method !== 'HEAD' && url.includes('/api/')) {
          const body = init && init.body;
          if (body && typeof body === 'string' && body.startsWith('{')) {
            const parsed = JSON.parse(body);
            if (parsed.project_id != null && !assertProjectMatch(parsed.project_id, url)) {
              return Promise.resolve(new Response(JSON.stringify({ error: 'Project mismatch' }), { status: 409 }));
            }
          }
        }
      } catch (_) { /* ignore */ }
      return orig(input, init);
    };
  }

  installFetchGuard();

  global.CasePMProjectGuard = {
    activeProjectIdFromDom,
    assertProjectMatch,
  };
})(window);
