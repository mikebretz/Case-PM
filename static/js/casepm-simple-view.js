/**
 * Simple view — hides advanced controls on heavy modules (budget, pay apps, COs, submittals).
 */
(function (global) {
  'use strict';

  const MODULE = (document.body?.getAttribute('data-page-module') || 'app').replace(/-/g, '_');
  const SIMPLE_MODULES = new Set(['budget', 'pay_applications', 'change_orders', 'submittals']);
  const uid = document.body?.getAttribute('data-current-user-id') || '0';
  const KEY = `casepm_simple_view_u${uid}`;

  function isSimple() {
    try {
      return localStorage.getItem(KEY) !== '0';
    } catch (_) {
      return true;
    }
  }

  function setSimple(on) {
    try {
      localStorage.setItem(KEY, on ? '1' : '0');
    } catch (_) { /* ignore */ }
    apply();
  }

  function apply() {
    const on = isSimple() && SIMPLE_MODULES.has(MODULE);
    document.documentElement.classList.toggle('casepm-simple-view', on);
    document.body?.classList.toggle('casepm-simple-view', on);
    const btn = document.getElementById('casepmSimpleViewToggle');
    if (btn) {
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.title = on ? 'Show advanced tools' : 'Simplify screen';
      const label = btn.querySelector('.casepm-simple-view-label');
      if (label) label.textContent = on ? 'Advanced' : 'Simple';
    }
  }

  function injectToggle() {
    if (!SIMPLE_MODULES.has(MODULE)) return;
    if (document.getElementById('casepmSimpleViewToggle')) return;
    const header = document.getElementById('appHeaderBar');
    if (!header) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'casepmSimpleViewToggle';
    btn.className = 'hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white ml-2';
    btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles text-emerald-400"></i><span class="casepm-simple-view-label">Simple</span>';
    btn.addEventListener('click', () => setSimple(!isSimple()));
    const right = header.querySelector('.flex.items-center.gap-3:last-child') || header.lastElementChild;
    if (right) right.prepend(btn);
    else header.appendChild(btn);
  }

  apply();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { injectToggle(); apply(); });
  } else {
    injectToggle();
  }

  global.CasePMSimpleView = { isSimple, setSimple, apply };
})(window);
