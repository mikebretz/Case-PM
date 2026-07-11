/**
 * Case PM — freeze shell chrome so only page tables/content panes scroll.
 * Chrome is viewport-fixed in base.html; this script blocks Ctrl+scroll browser
 * zoom on header/sidebar/footer and wraps unstructured pages.
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

  const ZOOM_ALLOWED = [
    '.casepm-zoom-allowed',
    '#luckysheet',
    '#luckysheetcellsheet',
    '.luckysheet-wa-calculate',
    '.tox-edit-area',
    '.tox-tinymce',
    '#gantt_here',
    '#scheduleGanttHost',
    '#drawViewerWrap',
    '#drawViewerCanvas',
    '.draw-viewer-stage',
    '.word-page',
    '.sheet-page',
  ].join(',');

  const CHROME = '#appHeaderBar, #appSidebar, #appFooterBar, .portal-banner-sub, .portal-banner-architect';

  function isInChrome(el) {
    return el && el.closest && el.closest(CHROME);
  }

  function isZoomAllowed(el) {
    return el && el.closest && el.closest(ZOOM_ALLOWED);
  }

  function blockBrowserZoom(e) {
    if (!(e.ctrlKey || e.metaKey)) return;
    if (isZoomAllowed(e.target)) return;
    e.preventDefault();
  }

  function initLegacyScrollWrap() {
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

  function initChromeZoomGuard() {
    document.addEventListener('wheel', blockBrowserZoom, { passive: false, capture: true });
    // Safari trackpad pinch sometimes fires gesture events
    document.addEventListener('gesturestart', (e) => {
      if (isInChrome(e.target) && !isZoomAllowed(e.target)) e.preventDefault();
    }, { passive: false, capture: true });
  }

  function init() {
    initLegacyScrollWrap();
    initChromeZoomGuard();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
