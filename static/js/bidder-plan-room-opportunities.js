(function () {
  'use strict';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  const gate = document.getElementById('prAccessGate');
  const list = document.getElementById('prOpportunityList');
  if (!gate || !list) return;

  const approved = gate.dataset.approved === '1';
  const reason = gate.dataset.reason || '';

  if (!approved) {
    let text = 'Your plan room access is not active yet.';
    if (reason === 'pending_approval') {
      text = 'Your registration is pending approval. Our estimating team will email you when you can view bid opportunities.';
    } else if (reason === 'not_registered') {
      text = 'No approved registration found for your account. <a class="pr-link" href="/plan-room">Apply here</a>.';
    }
    gate.innerHTML = `<div class="pr-gate">${text}</div>`;
    list.innerHTML = '';
    return;
  }

  gate.innerHTML = '<p class="pr-muted">You are approved to view published opportunities below.</p>';

  fetch('/api/bidder-network/opportunities', { credentials: 'same-origin' })
    .then((r) => r.json())
    .then((data) => {
      const rows = data.opportunities || [];
      if (!rows.length) {
        list.innerHTML = '<p class="pr-muted">No public bid packages at this time. Check back soon.</p>';
        return;
      }
      list.innerHTML = rows.map((o) => `
        <article class="pr-opp-card">
          <h3>${esc(o.title)}</h3>
          <div class="pr-opp-meta">
            ${o.project_name ? esc(o.project_name) + ' · ' : ''}
            Spec ${esc(o.spec_section || '—')} · Due ${esc(o.due_date || 'TBD')}
          </div>
          <p>${esc(o.summary || '')}</p>
          <a class="pr-link" href="${esc(o.portal_url)}">Open in bid portal →</a>
        </article>
      `).join('');
    })
    .catch(() => {
      list.innerHTML = '<p class="pr-muted">Could not load opportunities.</p>';
    });
})();
