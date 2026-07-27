/**
 * Idle session timeout — warn before logout, then force sign-out and clear the screen.
 */
(function (global) {
  'use strict';

  const cfg = global.CASEPM_SESSION_IDLE || {};
  const timeoutMin = parseInt(cfg.timeoutMinutes, 10) || 0;
  const warnMin = Math.max(1, parseInt(cfg.warnMinutes, 10) || 5);
  if (!timeoutMin || timeoutMin <= 0) return;

  const timeoutMs = timeoutMin * 60000;
  const warnMs = Math.min(warnMin * 60000, Math.max(0, timeoutMs - 60000));
  let lastActivity = Date.now();
  let warned = false;
  let logoutTimer = null;
  let touchTimer = null;
  let expired = false;

  function csrfHeaders() {
    const token = global.CasePMSecurity && typeof global.CasePMSecurity.token === 'function'
      ? global.CasePMSecurity.token()
      : '';
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['X-CSRF-Token'] = token;
    return headers;
  }

  function msUntilLogout() {
    return timeoutMs - (Date.now() - lastActivity);
  }

  function lockScreen(message) {
    document.documentElement.style.overflow = 'hidden';
    if (document.getElementById('casepm-session-veil')) return;
    const veil = document.createElement('div');
    veil.id = 'casepm-session-veil';
    veil.setAttribute('role', 'alertdialog');
    veil.setAttribute('aria-live', 'assertive');
    veil.setAttribute('aria-label', message || 'Signing out');
    veil.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:2147483647',
      'background:#09090b',
      'color:#e4e4e7',
      'display:flex',
      'align-items:center',
      'justify-content:center',
      'font:600 1rem/1.4 system-ui,sans-serif',
      'text-align:center',
      'padding:2rem',
    ].join(';');
    veil.textContent = message || 'Signing out due to inactivity…';
    document.body.appendChild(veil);
    document.querySelectorAll('body > *:not(#casepm-session-veil)').forEach((el) => {
      el.setAttribute('aria-hidden', 'true');
      el.style.visibility = 'hidden';
    });
  }

  function touchServerDebounced() {
    if (expired) return;
    clearTimeout(touchTimer);
    touchTimer = setTimeout(() => {
      if (expired) return;
      fetch('/api/session/touch', {
        method: 'POST',
        headers: csrfHeaders(),
        credentials: 'same-origin',
        keepalive: true,
      }).catch(() => {});
    }, 1500);
  }

  function forceLogout() {
    if (expired) return;
    expired = true;
    global.__CASEPM_SESSION_EXPIRED = true;
    clearTimeout(logoutTimer);
    clearTimeout(touchTimer);
    lockScreen('Your session expired. Redirecting to sign in…');
    const target = '/logout?reason=idle';
    try {
      global.stop && global.stop();
    } catch (_) { /* presence timers */ }
    window.setTimeout(() => {
      window.location.replace(target);
    }, 150);
  }

  function scheduleLogout() {
    clearTimeout(logoutTimer);
    const remaining = msUntilLogout();
    if (remaining <= 0) {
      forceLogout();
      return;
    }
    logoutTimer = setTimeout(() => {
      if (msUntilLogout() <= 0) forceLogout();
      else scheduleLogout();
    }, Math.min(remaining, 5000));
  }

  function showWarning() {
    const minsLeft = Math.max(1, Math.ceil(msUntilLogout() / 60000));
    const msg = `You will be signed out in about ${minsLeft} minute${minsLeft === 1 ? '' : 's'} due to inactivity. Move the mouse or press a key to stay signed in.`;
    if (typeof global.CasePMDialog !== 'undefined' && typeof global.CasePMDialog.alert === 'function') {
      global.CasePMDialog.alert(msg, 'warning');
    }
  }

  function bump() {
    if (expired) return;
    lastActivity = Date.now();
    if (warned) warned = false;
    scheduleLogout();
    touchServerDebounced();
  }

  ['click', 'keydown', 'mousemove', 'scroll', 'touchstart'].forEach((ev) => {
    document.addEventListener(ev, bump, { passive: true });
  });

  setInterval(() => {
    if (expired) return;
    const remaining = msUntilLogout();
    if (remaining <= 0) {
      forceLogout();
      return;
    }
    const warnAt = timeoutMs - warnMs;
    const idleMs = Date.now() - lastActivity;
    if (idleMs >= warnAt && !warned) {
      warned = true;
      showWarning();
    }
  }, 5000);

  scheduleLogout();
  bump();
}(window));
