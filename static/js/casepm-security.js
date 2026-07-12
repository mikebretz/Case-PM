/**
 * Injects CSRF token into fetch requests for remote / cloud deployments.
 */
(function (global) {
  'use strict';

  function token() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  const nativeFetch = global.fetch.bind(global);
  global.fetch = function (input, init) {
    const opts = init ? { ...init } : {};
    const headers = new Headers(opts.headers || {});
    const t = token();
    const method = (opts.method || 'GET').toUpperCase();
    if (t && !['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers.has('X-CSRF-Token')) {
      headers.set('X-CSRF-Token', t);
    }
    opts.headers = headers;
    opts.credentials = opts.credentials || 'same-origin';
    return nativeFetch(input, opts);
  };

  global.CasePMSecurity = { token };
})(window);
