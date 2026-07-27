/**
 * BIM / 3D model viewer — uses model-viewer for GLB/GLTF.
 */
(function (global) {
  'use strict';

  function mount(container, fileUrl, ext, options) {
    if (!container) return;
    const opts = options || {};
    const fill = opts.fill !== false;
    container.innerHTML = '';
    const lower = (ext || '').toLowerCase();
    if (lower === 'pdf') {
      const minH = fill ? '100%' : '400px';
      container.innerHTML = `<iframe src="${fileUrl}" class="w-full rounded-lg border border-zinc-700" style="height:${minH};min-height:${fill ? '0' : '400px'};" title="PDF"></iframe>`;
      return;
    }
    if (['glb', 'gltf'].includes(lower)) {
      const mv = document.createElement('model-viewer');
      mv.setAttribute('src', fileUrl);
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
    container.innerHTML = `<div class="p-6 text-center text-zinc-400">
      <p>Preview not available for .${lower} files.</p>
      <a href="${fileUrl}" class="text-emerald-400 underline mt-2 inline-block" download>Download model</a>
    </div>`;
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

  global.CasePMBimViewer = { mount, toggleFullscreen, bindFullscreen, openPopout };
})(window);
