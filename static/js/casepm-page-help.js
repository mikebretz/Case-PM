/**
 * Case PM — global in-app page help (staff / main company only).
 */
(function (global) {
  'use strict';

  const DEVELOPER_MODULES = new Set(['developer']);

  let activePageKey = null;
  let activeSectionId = null;
  let pendingSectionId = null;
  let tabSectionMap = null;

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function isStaffMainCompany() {
    return document.body?.dataset?.isStaffPortal === '1';
  }

  function currentPageKey() {
    return document.body?.dataset?.pageModule || 'app';
  }

  function canShowHelp(pageKey) {
    if (!isStaffMainCompany()) return false;
    const key = pageKey || currentPageKey();
    if (DEVELOPER_MODULES.has(key)) return false;
    const guides = global.CasePMPageHelpGuides || {};
    return Boolean(guides[key] || guides.app);
  }

  function getGuide(pageKey) {
    const guides = global.CasePMPageHelpGuides || {};
    return guides[pageKey] || guides.app || null;
  }

  function getDialog() {
    return document.getElementById('casepmPageHelpModal');
  }

  function closeHelp() {
    const dlg = getDialog();
    if (dlg?.open) dlg.close();
  }

  function renderNav(guide, selectedId) {
    const nav = document.getElementById('casepmPageHelpNav');
    const layout = document.getElementById('casepmPageHelpLayout');
    if (!nav || !layout) return;
    const sections = guide.sections || [];
    const multi = sections.length > 1;
    layout.classList.toggle('casepm-help-single', !multi);
    nav.classList.toggle('hidden', !multi);
    if (!multi) {
      nav.innerHTML = '';
      return;
    }
    const pageKey = currentPageKey();
    let jump = '';
    if (activePageKey !== 'app' && getGuide('app')) {
      jump = `<button type="button" data-help-open-app class="casepm-help-nav-btn w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2 mb-2 border border-violet-700/40 text-violet-200 hover:bg-violet-900/40">
        <i class="fa-solid fa-book w-4 text-center"></i><span>Complete user guide (all modules)</span></button>`;
    } else if (activePageKey === 'app' && pageKey && pageKey !== 'app' && getGuide(pageKey)) {
      jump = `<button type="button" data-help-open-page="${esc(pageKey)}" class="casepm-help-nav-btn w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2 mb-2 border border-zinc-600 text-zinc-200 hover:bg-zinc-800">
        <i class="fa-solid fa-location-dot w-4 text-center"></i><span>Guide for this page only</span></button>`;
    }
    nav.innerHTML = jump + sections.map(s => `
      <button type="button" data-help-section="${esc(s.id)}"
        class="casepm-help-nav-btn w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2 ${s.id === selectedId ? 'bg-violet-700 text-white' : 'text-zinc-300 hover:bg-zinc-800'}">
        <i class="fa-solid ${esc(s.icon || 'fa-circle')} w-4 text-center opacity-80"></i>
        <span>${esc(s.title)}</span>
      </button>`).join('');
    nav.querySelector('[data-help-open-app]')?.addEventListener('click', (e) => {
      e.preventDefault();
      selectSection('app', getGuide('app')?.sections?.[0]?.id || 'welcome');
    });
    nav.querySelector('[data-help-open-page]')?.addEventListener('click', (e) => {
      e.preventDefault();
      const pk = e.currentTarget.getAttribute('data-help-open-page');
      if (pk) openHelp(pk);
    });
    nav.querySelectorAll('[data-help-section]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        selectSection(activePageKey, btn.dataset.helpSection);
      });
    });
  }

  function renderSubsteps(substeps, stepIndex) {
    if (!substeps?.length) return '';
    const items = substeps.map((sub, j) => `
      <div class="casepm-help-substep">
        <button type="button" class="casepm-help-substep-toggle" data-help-substep-toggle
          aria-expanded="false" aria-controls="casepm-help-sub-${stepIndex}-${j}">
          <i class="fa-solid fa-chevron-right casepm-help-substep-chevron" aria-hidden="true"></i>
          <span>${esc(sub.title)}</span>
        </button>
        <div id="casepm-help-sub-${stepIndex}-${j}" class="casepm-help-substep-detail hidden casepm-help-prose" hidden>
          <p class="text-sm text-zinc-300 mb-2">${sub.body}</p>
          ${sub.detail ? `<div class="casepm-help-detail text-xs text-zinc-300 bg-zinc-800/80 border border-zinc-700 rounded-lg px-3 py-2 mt-1 leading-relaxed">${sub.detail}</div>` : ''}
        </div>
      </div>`).join('');
    return `<div class="casepm-help-substeps hidden" data-help-substeps hidden>${items}</div>`;
  }

  function renderContent(guide, section) {
    const body = document.getElementById('casepmPageHelpBody');
    const titleEl = document.getElementById('casepmPageHelpTitle');
    const subEl = document.getElementById('casepmPageHelpSubtitle');
    if (!body || !section) return;
    if (titleEl) {
      const titleText = document.getElementById('casepmPageHelpTitleText');
      const isApp = activePageKey === 'app';
      const label = isApp
        ? 'User guide — Case PM'
        : `User guide · ${guide.title || 'This page'}`;
      if (titleText) titleText.textContent = label;
      else titleEl.textContent = label;
    }
    if (subEl) {
      subEl.textContent = guide.subtitle || section.title || '';
      if (activePageKey !== 'app') {
        subEl.textContent = (subEl.textContent ? subEl.textContent + ' — ' : '') + 'Use “Complete user guide” in the sidebar for the full manual.';
      }
    }
    const hasSubsteps = (section.steps || []).some(s => s.substeps?.length);
    const steps = (section.steps || []).map((step, i) => {
      const subs = step.substeps || [];
      const hasSubs = subs.length > 0;
      const numCls = hasSubs
        ? 'casepm-help-step-num'
        : 'casepm-help-step-num casepm-help-step-num-static';
      const numAttrs = hasSubs
        ? ` type="button" data-help-step-toggle aria-expanded="false" aria-controls="casepm-help-subs-${i}" title="Click for step-by-step details"`
        : '';
      return `
      <div class="casepm-help-step mb-5">
        <div class="flex items-start gap-3">
          <${hasSubs ? 'button' : 'span'} class="flex-shrink-0 w-7 h-7 rounded-full bg-violet-600 text-white text-sm font-bold flex items-center justify-center ${numCls}"${numAttrs}>${i + 1}</${hasSubs ? 'button' : 'span'}>
          <div class="min-w-0 flex-1">
            <h3 class="text-sm font-semibold text-white mb-1">${esc(step.title)}</h3>
            <div class="text-sm text-zinc-300 leading-relaxed casepm-help-prose">${step.body}</div>
            ${renderSubsteps(subs, i)}
          </div>
        </div>
      </div>`;
    }).join('');
    body.innerHTML = `
      ${guide.sections.length > 1 ? `<h2 class="text-base font-semibold text-white mb-1 flex items-center gap-2"><i class="fa-solid ${esc(section.icon || 'fa-book')} text-violet-400"></i>${esc(section.title)}</h2>` : ''}
      <p class="text-xs text-zinc-500 mb-1">${guide.sections.length > 1 ? 'Follow the steps below. Pick another topic from the list on the left anytime.' : 'Follow the steps below.'}</p>
      ${hasSubsteps ? '<p class="casepm-help-expand-hint"><i class="fa-solid fa-hand-pointer mr-1 opacity-70"></i>Click a <strong>step number</strong> to expand sub-steps. Click each <strong>sub-step name</strong> for what to do, how it works, and which other Case PM modules it connects to.</p>' : ''}
      ${steps || '<p class="text-sm text-zinc-500">No help content for this section yet.</p>'}`;
    body.scrollTop = 0;
  }

  function bindHelpStepToggles() {
    const body = document.getElementById('casepmPageHelpBody');
    if (!body || body.dataset.helpStepsBound === '1') return;
    body.dataset.helpStepsBound = '1';
    body.addEventListener('click', (e) => {
      const stepBtn = e.target.closest('[data-help-step-toggle]');
      if (stepBtn) {
        e.preventDefault();
        const expanded = stepBtn.getAttribute('aria-expanded') === 'true';
        const stepEl = stepBtn.closest('.casepm-help-step');
        const panel = stepEl?.querySelector('[data-help-substeps]');
        stepBtn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        if (panel) {
          panel.classList.toggle('hidden', expanded);
          panel.hidden = expanded;
        }
        return;
      }
      const subBtn = e.target.closest('[data-help-substep-toggle]');
      if (subBtn) {
        e.preventDefault();
        const expanded = subBtn.getAttribute('aria-expanded') === 'true';
        const controlsId = subBtn.getAttribute('aria-controls');
        const detail = controlsId ? document.getElementById(controlsId) : null;
        subBtn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        if (detail) {
          detail.classList.toggle('hidden', expanded);
          detail.hidden = expanded;
        }
      }
    });
  }

  function selectSection(pageKey, sectionId) {
    const guide = getGuide(pageKey);
    if (!guide) return;
    const section = (guide.sections || []).find(s => s.id === sectionId) || guide.sections[0];
    if (!section) return;
    activePageKey = pageKey;
    activeSectionId = section.id;
    renderNav(guide, section.id);
    renderContent(guide, section);
  }

  function openHelp(pageKey, sectionId) {
    if (!canShowHelp(pageKey)) return;
    const key = pageKey || currentPageKey();
    const guide = getGuide(key);
    if (!guide) return;
    const dlg = getDialog();
    if (!dlg) return;
    const section = sectionId || pendingSectionId || guide.sections[0]?.id;
    pendingSectionId = null;
    selectSection(key, section);
    if (!dlg.open) dlg.showModal();
  }

  function setContextFromTab(tabKey) {
    if (tabSectionMap && tabSectionMap[tabKey]) {
      pendingSectionId = tabSectionMap[tabKey];
      if (activePageKey === currentPageKey() && getDialog()?.open) {
        selectSection(activePageKey, pendingSectionId);
        pendingSectionId = null;
      }
    }
  }

  function registerTabSectionMap(pageKey, map) {
    if (currentPageKey() === pageKey) tabSectionMap = map;
  }

  function bindDialog() {
    const dlg = getDialog();
    if (!dlg || dlg.dataset.casepmHelpBound === '1') return;
    dlg.dataset.casepmHelpBound = '1';
    dlg.addEventListener('cancel', (e) => {
      e.preventDefault();
      closeHelp();
    });
    dlg.addEventListener('click', (e) => {
      if (e.target === dlg) closeHelp();
    });
    dlg.querySelectorAll('[data-casepm-help-close]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        closeHelp();
      });
    });
  }

  function initHeaderButton() {
    const btn = document.getElementById('casepmPageHelpBtn');
    if (!btn || btn.dataset.bound === '1') return;
    if (!canShowHelp()) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      openHelp();
    });
  }

  function init() {
    bindDialog();
    bindHelpStepToggles();
    initHeaderButton();
    document.querySelectorAll('[data-casepm-page-help]').forEach(el => {
      if (el.dataset.helpBound === '1') return;
      el.dataset.helpBound = '1';
      el.addEventListener('click', (e) => {
        e.preventDefault();
        openHelp(el.dataset.casepmPageHelp || undefined, el.dataset.casepmHelpSection || undefined);
      });
    });
  }

  global.CasePMPageHelp = {
    open: openHelp,
    close: closeHelp,
    canShow: canShowHelp,
    setContextFromTab,
    registerTabSectionMap,
    init,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
