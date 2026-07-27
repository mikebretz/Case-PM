/**
 * BIM / 3D model viewer — uses model-viewer for GLB/GLTF.
 */
(function (global) {
  'use strict';

  function safeSameOriginPath(fileUrl) {
    try {
      const u = new URL(String(fileUrl || ''), window.location.origin);
      if (u.origin !== window.location.origin) return null;
      if (!['http:', 'https:'].includes(u.protocol)) return null;
      return u.pathname + u.search + u.hash;
    } catch (_) {
      return null;
    }
  }

  function mount(container, fileUrl, ext, options) {
    if (!container) return;
    const opts = options || {};
    const fill = opts.fill !== false;
    const safeUrl = safeSameOriginPath(fileUrl);
    container.replaceChildren();
    const lower = (ext || '').toLowerCase();
    if (lower === 'pdf' && safeUrl) {
      const iframe = document.createElement('iframe');
      iframe.src = safeUrl;
      iframe.className = 'w-full rounded-lg border border-zinc-700';
      iframe.title = 'PDF';
      iframe.style.height = fill ? '100%' : '400px';
      iframe.style.minHeight = fill ? '0' : '400px';
      container.appendChild(iframe);
      return;
    }
    if (['glb', 'gltf'].includes(lower) && safeUrl) {
      const mv = document.createElement('model-viewer');
      mv.setAttribute('src', safeUrl);
      mv.setAttribute('camera-controls', '');
      mv.setAttribute('shadow-intensity', '1');
      mv.setAttribute('auto-rotate', '');
      mv.style.width = '100%';
      mv.style.height = fill ? '100%' : '420px';
      mv.style.minHeight = fill ? '0' : '420px';
      mv.style.background = '#0a0a0b';
      mv.style.borderRadius = fill ? '0' : '0.5rem';
      container.appendChild(mv);
      return;
    }
    const fallback = document.createElement('div');
    fallback.className = 'p-6 text-center text-zinc-400';
    fallback.innerHTML = `<p>Preview not available for .${lower} files.</p>`;
    if (safeUrl) {
      const link = document.createElement('a');
      link.href = safeUrl;
      link.className = 'text-emerald-400 underline mt-2 inline-block';
      link.download = '';
      link.textContent = 'Download model';
      fallback.appendChild(link);
    }
    container.appendChild(fallback);
  }

  function toggleFullscreen(el) {
    if (!el) return;
    if (!document.fullscreenElement) {
      (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
    } else {
      (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    }
  }

  function bindFullscreen(targetEl, btnEl) {
    if (!targetEl) return () => {};
    const updateBtn = () => {
      const on = !!document.fullscreenElement && document.fullscreenElement === targetEl;
      if (!btnEl) return;
      btnEl.innerHTML = on
        ? '<i class="fa-solid fa-compress mr-1"></i> Exit full screen'
        : '<i class="fa-solid fa-expand mr-1"></i> Full screen';
    };
    const onChange = () => updateBtn();
    document.addEventListener('fullscreenchange', onChange);
    btnEl?.addEventListener('click', () => toggleFullscreen(targetEl));
    updateBtn();
    return () => document.removeEventListener('fullscreenchange', onChange);
  }

  function openPopout(assetId) {
    if (!assetId) return null;
    const url = `/operations/bim-viewer?asset_id=${encodeURIComponent(assetId)}`;
    return window.open(url, 'casepm-bim-viewer', 'width=1400,height=900,resizable=yes,scrollbars=yes');
  }

  function mount4D(container, timeline, options) {
    if (!container) return;
    const opts = options || {};
    const links = (timeline && timeline.links) || [];
    const activeIdx = opts.activeIndex != null ? opts.activeIndex : 0;
    const active = links[activeIdx] || null;

    container.innerHTML = `
      <div class="bim-4d-bar flex flex-wrap items-center gap-2 p-2 bg-zinc-900 border border-zinc-700 rounded-lg text-xs">
        <span class="text-zinc-400 font-medium">4D / 5D</span>
        <input type="range" id="bim4dSlider" class="flex-1 min-w-[120px]" min="0" max="${Math.max(links.length - 1, 0)}" value="${activeIdx}" ${links.length ? '' : 'disabled'}>
        <span id="bim4dLabel" class="text-zinc-300 truncate max-w-[200px]">${active ? escHtml(active.task_name) : 'No schedule links'}</span>
        ${active && active.budget_amount ? `<span class="text-emerald-400">$${Number(active.budget_amount).toLocaleString()}</span>` : ''}
      </div>`;

    const slider = container.querySelector('#bim4dSlider');
    const label = container.querySelector('#bim4dLabel');
    if (!slider || !links.length) return;

    slider.addEventListener('input', () => {
      const idx = parseInt(slider.value, 10);
      const link = links[idx];
      if (label && link) {
        label.textContent = `${link.task_name || 'Task'}${link.start_date ? ` · ${link.start_date}` : ''}`;
      }
      if (typeof opts.onStep === 'function') opts.onStep(link, idx);
    });
  }

  function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  global.CasePMBimViewer = { mount, toggleFullscreen, bindFullscreen, openPopout, mount4D };
})(window);
