/**
 * BIM / 3D model viewer — uses model-viewer for GLB/GLTF.
 */
(function (global) {
  'use strict';

  function mount(container, fileUrl, ext) {
    if (!container) return;
    container.innerHTML = '';
    const lower = (ext || '').toLowerCase();
    if (lower === 'pdf') {
      container.innerHTML = `<iframe src="${fileUrl}" class="w-full h-full min-h-[400px] rounded-lg border border-zinc-700" title="PDF"></iframe>`;
      return;
    }
    if (['glb', 'gltf'].includes(lower)) {
      const mv = document.createElement('model-viewer');
      mv.setAttribute('src', fileUrl);
      mv.setAttribute('camera-controls', '');
      mv.setAttribute('shadow-intensity', '1');
      mv.setAttribute('auto-rotate', '');
      mv.style.width = '100%';
      mv.style.height = '420px';
      mv.style.background = '#0a0a0b';
      mv.style.borderRadius = '0.5rem';
      container.appendChild(mv);
      return;
    }
    container.innerHTML = `<div class="p-6 text-center text-zinc-400">
      <p>Preview not available for .${lower} files.</p>
      <a href="${fileUrl}" class="text-emerald-400 underline mt-2 inline-block" download>Download model</a>
    </div>`;
  }

  global.CasePMBimViewer = { mount };
})(window);
