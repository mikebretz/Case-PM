(function () {
  'use strict';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatDate(iso) {
    if (!iso) return 'TBD';
    try {
      return new Date(iso + (iso.length === 10 ? 'T12:00:00' : '')).toLocaleDateString();
    } catch (_) {
      return iso;
    }
  }

  function renderCard(p, { link } = { link: true }) {
    const inner = `
      <h3>${esc(p.name)}</h3>
      <div class="pr-project-meta">${esc(p.number)} · ${esc(p.location || 'Location TBD')}</div>
      <div class="pr-due">Bid date: ${formatDate(p.bid_date)}</div>
      ${p.summary ? `<p class="pr-project-meta">${esc(p.summary)}</p>` : ''}
      <div class="pr-project-tags">
        ${(p.divisions || []).slice(0, 4).map((d) => `<span class="pr-tag">${esc(d)}</span>`).join('')}
        ${p.package_count ? `<span class="pr-tag">${p.package_count} package(s)</span>` : ''}
      </div>`;
    if (link && p.detail_url) {
      return `<a class="pr-project-card" href="${esc(p.detail_url)}">${inner}</a>`;
    }
    return `<div class="pr-project-card">${inner}</div>`;
  }

  async function loadPublicTeaser() {
    const host = document.getElementById('prPublicProjectList');
    if (!host) return;
    try {
      const res = await fetch('/api/public/bidder-network/projects');
      const data = await res.json();
      const rows = data.projects || [];
      host.innerHTML = rows.length
        ? rows.map((p) => renderCard(p, { link: false })).join('')
        : '<p class="pr-muted">No public projects at this time.</p>';
    } catch (_) {
      host.innerHTML = '<p class="pr-muted">Unable to load project list.</p>';
    }
  }

  const form = document.getElementById('prRegisterForm');
  const msg = document.getElementById('prRegisterMsg');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (msg) msg.textContent = 'Submitting…';
      const fd = new FormData(form);
      const specialties = [...form.querySelectorAll('input[name="specialty"]:checked')].map((el) => el.value);
      fd.delete('specialty');
      fd.append('specialties', JSON.stringify(specialties));
      try {
        const res = await fetch('/api/public/bidder-network/register', { method: 'POST', body: fd, credentials: 'same-origin' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Registration failed');
        if (msg) msg.textContent = data.message || 'Thank you — your application is pending review.';
        form.reset();
      } catch (err) {
        if (msg) msg.textContent = err.message || 'Could not submit. Please try again.';
      }
    });
  }

  if (window.PR_PUBLIC_PROJECTS) loadPublicTeaser();
})();
