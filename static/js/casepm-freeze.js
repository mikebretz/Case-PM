/**
 * Case PM — freeze shell chrome so only page tables/content panes scroll.
 * Pages that already use a *-page / *-page-root flex stack are left alone.
 * Unstructured pages get a legacy inner scroll wrapper so header/sidebar/footer stay put.
 */
(function () {
  const KNOWN_ROOTS = [
    '.casepm-freeze-page',
    '.budget-page',
    '.forecast-page',
    '.pay-app-page',
    '.com-page',
    '.co-page',
    '.rfi-page',
    '.dlog-page',
    '.wlog-page',
    '.punch-page',
    '.saf-page',
    '.del-page',
    '.dash-page',
    '.docs-page',
    '.draw-page',
    '.sheet-page',
    '.word-page',
    '.projects-page-root',
    '.schedule-page-root',
    '.email-page-root',
    '.photos-page',
    '.insp-page',
    '.mm-page',
    '.companies-page',
    '.um-page',
    '.settings-page',
    '.notif-page',
    '.submittals-page',
  ].join(',');

  function init() {
    const mc = document.getElementById('mainContent');
    if (!mc || mc.dataset.freezeInit === '1') return;
    mc.dataset.freezeInit = '1';

    if (mc.querySelector(KNOWN_ROOTS)) return;

    const kids = Array.from(mc.childNodes).filter((n) => {
      if (n.nodeType === Node.TEXT_NODE) return (n.textContent || '').trim().length > 0;
      if (n.nodeType !== Node.ELEMENT_NODE) return false;
      const tag = n.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK' || tag === 'TEMPLATE') return false;
      if (tag === 'DIALOG') return false;
      return true;
    });

    if (!kids.length) return;

    const wrap = document.createElement('div');
    wrap.className = 'casepm-legacy-scroll';
    kids.forEach((n) => wrap.appendChild(n));
    mc.appendChild(wrap);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
