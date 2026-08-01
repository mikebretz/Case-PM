(function () {
  'use strict';

  let allProjects = [];

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

  function renderGrid(rows) {
    const grid = document.getElementById('prProjectGrid');
    const count = document.getElementById('prProjectCount');
    if (count) count.textContent = `${rows.length} project${rows.length === 1 ? '' : 's'}`;
    if (!grid) return;
    if (!rows.length) {
      grid.innerHTML = '<p class="pr-muted">No active projects in the plan room.</p>';
      return;
    }
    grid.innerHTML = rows.map((p) => `
      <a class="pr-project-card" href="/plan-room/projects/${p.id}">
        <h3>${esc(p.name)}</h3>
        <div class="pr-project-meta">${esc(p.number)} · ${esc(p.location || '')} · ${esc(p.project_type || '')}</div>
        <div class="pr-due">Bid date: ${formatDate(p.bid_date)}</div>
        <p class="pr-project-meta">${esc(p.summary || '')}</p>
        <div class="pr-project-tags">
          ${(p.divisions || []).map((d) => `<span class="pr-tag">${esc(d)}</span>`).join('')}
          <span class="pr-tag">${p.package_count || 0} bid package(s)</span>
        </div>
      </a>
    `).join('');
  }

  function filterProjects(q) {
    const needle = (q || '').trim().toLowerCase();
    if (!needle) return allProjects;
    return allProjects.filter((p) => {
      const hay = `${p.name} ${p.number} ${p.location} ${p.summary}`.toLowerCase();
      return hay.includes(needle);
    });
  }

  const gate = document.getElementById('prAccessGate');
  const approved = gate && gate.dataset.approved === '1';
  if (!approved) {
    let text = 'Plan room access requires an approved registration.';
    const reason = gate?.dataset.reason || '';
    if (reason === 'pending_approval') {
      text = 'Your application is pending. You will be able to download plans once estimating approves your firm.';
    } else if (reason === 'not_registered') {
      text = 'No approved account found. <a href="/plan-room#prRegister">Register here</a>.';
    }
    if (gate) gate.innerHTML = `<div class="pr-gate">${text}</div>`;
  }

  fetch('/api/bidder-network/projects', { credentials: 'same-origin' })
    .then((r) => r.json())
    .then((data) => {
      if (data.error && !approved) return;
      allProjects = data.projects || [];
      renderGrid(allProjects);
    })
    .catch(() => {
      const grid = document.getElementById('prProjectGrid');
      if (grid) grid.innerHTML = '<p class="pr-muted">Could not load projects.</p>';
    });

  document.getElementById('prProjectSearch')?.addEventListener('input', (e) => {
    renderGrid(filterProjects(e.target.value));
  });
})();
