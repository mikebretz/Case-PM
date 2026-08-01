(function () {
  'use strict';

  const root = document.getElementById('prProjectDetailRoot');
  const host = document.getElementById('prProjectDetail');
  if (!root || !host) return;

  const projectId = root.dataset.projectId;
  const approved = root.dataset.approved === '1';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso + (iso.length === 10 ? 'T12:00:00' : '')).toLocaleDateString();
    } catch (_) {
      return iso;
    }
  }

  function formatBytes(n) {
    const b = Number(n) || 0;
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
  }

  if (!approved) {
    host.innerHTML = '<div class="pr-gate">Sign in with an approved plan room account to view plans and documents.</div>';
    return;
  }

  fetch(`/api/bidder-network/projects/${projectId}`, { credentials: 'same-origin' })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        host.innerHTML = `<p class="pr-muted">${esc(data.error)}</p>`;
        return;
      }
      const p = data.project || {};
      const docs = data.documents || [];
      const pkgs = data.packages || [];
      const addenda = data.addenda || [];
      const pr = data.plan_room || {};

      host.innerHTML = `
        <div class="pr-detail-hero">
          <h1>${esc(p.name)}</h1>
          <div class="pr-project-meta">${esc(p.number)} · ${esc(p.location)} · ${esc(p.project_type || '')}</div>
          <div class="pr-due" style="margin-top:0.5rem">Bid date: ${formatDate(p.bid_date)}${pr.pre_bid_date ? ` · Pre-bid: ${formatDate(pr.pre_bid_date)}` : ''}</div>
          ${pr.contact_email ? `<p class="pr-project-meta">Bid contact: ${esc(pr.contact_name || '')} <a href="mailto:${esc(pr.contact_email)}">${esc(pr.contact_email)}</a></p>` : ''}
          <p style="margin-top:0.75rem">${esc(p.summary || pr.summary || '')}</p>
        </div>
        <div class="pr-detail-grid">
          <section class="pr-panel">
            <h2>Plans &amp; specifications</h2>
            ${docs.length ? `<ul class="pr-doc-list">${docs.map((d) => `
              <li>
                <span>${esc(d.name)} <span class="pr-project-meta">(${formatBytes(d.file_size)})</span></span>
                <a class="pr-download" href="${esc(d.download_url)}">Download</a>
              </li>`).join('')}</ul>` : '<p class="pr-muted">No documents attached yet. Check back for addenda.</p>'}
          </section>
          <section class="pr-panel">
            <h2>Bid packages</h2>
            ${pkgs.length ? pkgs.map((pkg) => `
              <div style="margin-bottom:1rem;padding-bottom:1rem;border-bottom:1px solid var(--pr-border)">
                <strong>${esc(pkg.title || pkg.number)}</strong>
                <div class="pr-project-meta">Spec ${esc(pkg.spec_section || '—')} · Due ${formatDate(pkg.due_date)}</div>
                <p class="pr-project-meta">${esc(pkg.summary || '')}</p>
                <a class="pr-download" href="${esc(pkg.portal_url)}">Submit quote in bid portal →</a>
              </div>
            `).join('') : '<p class="pr-muted">No published packages.</p>'}
          </section>
        </div>
        ${addenda.length ? `<section class="pr-panel"><h2>Addenda</h2><ul class="pr-doc-list">${addenda.map((a) => `
          <li><span><strong>${esc(a.number)}</strong> — ${esc(a.title)} (${esc(a.package_title)})</span></li>`).join('')}</ul></section>` : ''}
      `;
    })
    .catch(() => {
      host.innerHTML = '<p class="pr-muted">Could not load project.</p>';
    });
})();
