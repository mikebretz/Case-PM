(function () {
  'use strict';

  window.PlanRoomDocs = window.PlanRoomDocs || {};

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatBytes(n) {
    const b = Number(n) || 0;
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
  }

  function actionLinks(doc) {
    const parts = [];
    if (doc.view_url && doc.can_preview) {
      parts.push(`<a class="pr-download" href="${esc(doc.view_url)}">View</a>`);
    }
    parts.push(`<a class="pr-download" href="${esc(doc.download_url)}">Download</a>`);
    return parts.join('<span class="pr-doc-sep">·</span>');
  }

  function listItem(doc) {
    return `
      <li class="pr-doc-item" data-doc-name="${esc((doc.title || doc.name || '').toLowerCase())}">
        <span>${esc(doc.title || doc.name)}${doc.sheet ? ` <span class="pr-project-meta">(${esc(doc.sheet)})</span>` : ''}
          <span class="pr-project-meta"> · ${formatBytes(doc.file_size)}</span></span>
        <span class="pr-doc-actions">${actionLinks(doc)}</span>
      </li>`;
  }

  window.PlanRoomDocs.renderListItem = listItem;
  window.PlanRoomDocs.renderActionLinks = actionLinks;
  window.PlanRoomDocs.formatBytes = formatBytes;

  window.PlanRoomDocs.bindDocumentSearch = function (inputEl, containerEl) {
    if (!inputEl || !containerEl) return;
    inputEl.addEventListener('input', () => {
      const q = (inputEl.value || '').trim().toLowerCase();
      containerEl.querySelectorAll('.pr-doc-item').forEach((row) => {
        const name = row.dataset.docName || '';
        row.classList.toggle('hidden', q && !name.includes(q));
      });
    });
  };
})();
