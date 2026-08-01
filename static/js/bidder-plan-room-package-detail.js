(function () {
  'use strict';

  const root = document.getElementById('prPackageDetailRoot');
  const host = document.getElementById('prPackageDetail');
  if (!root || !host) return;

  const projectId = root.dataset.projectId;
  const packageId = root.dataset.packageId;
  const approved = root.dataset.approved === '1';
  const PRD = window.PlanRoomDocs || {};

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

  function docRow(d) {
    return PRD.renderListItem ? PRD.renderListItem(d) : `<li>${esc(d.name)}</li>`;
  }

  function meetingBlock(label, block) {
    if (!block || (!block.date && !block.time && !block.location && !block.notes)) return '';
    return `
      <div class="pr-itb-block">
        <h3>${esc(label)}</h3>
        <p class="pr-project-meta">
          ${block.date ? formatDate(block.date) : ''}${block.time ? ` · ${esc(block.time)}` : ''}
          ${block.mandatory ? ' · <strong>Mandatory</strong>' : ''}
        </p>
        ${block.location ? `<p>${esc(block.location)}</p>` : ''}
        ${block.virtual_url ? `<p><a href="${esc(block.virtual_url)}" target="_blank" rel="noopener">Join virtually</a></p>` : ''}
        ${block.notes ? `<p>${esc(block.notes)}</p>` : ''}
      </div>`;
  }

  function renderSections(sections) {
    if (!sections || !sections.length) {
      return '<p class="pr-muted">No categorized documents yet.</p>';
    }
    return sections.map((sec) => `
      <div class="pr-itb-block">
        <h3>${esc(sec.label)}</h3>
        <ul class="pr-doc-list">
          ${(sec.documents || []).map((d) => docRow(d)).join('')}
        </ul>
      </div>
    `).join('');
  }

  if (!approved) {
    host.innerHTML = '<div class="pr-gate">Sign in with an approved plan room account to view bid package documents.</div>';
    return;
  }

  fetch(`/api/bidder-network/projects/${projectId}/packages/${packageId}`, { credentials: 'same-origin' })
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || data.error) {
        host.innerHTML = `<div class="pr-gate">${esc(data.error || 'Could not load package.')}</div>`;
        return;
      }
      const p = data.project || {};
      const pr = data.plan_room || {};
      const pkg = data.package || {};
      const itb = pkg.itb || (pkg.manifest && pkg.manifest.itb) || {};
      const sections = data.document_sections || [];
      const addenda = data.addenda || [];
      const zipUrl = data.documents_zip_url || '';

      host.innerHTML = `
        <div class="pr-detail-hero">
          <h1>${esc(pkg.title || pkg.number)}</h1>
          <div class="pr-project-meta">${esc(p.name)} · Spec ${esc(pkg.spec_section || '—')} · Division ${esc(pkg.division || '—')}</div>
          <div class="pr-due" style="margin-top:0.5rem">Bid due: ${formatDate(pkg.due_date || pr.bid_date)}${pr.bid_due_time ? ` at ${esc(pr.bid_due_time)}` : ''}</div>
          <p style="margin-top:0.75rem">${esc(pkg.summary || '')}</p>
          <p style="margin-top:0.75rem"><a class="pr-download" href="${esc(pkg.portal_url)}">Submit quote in bid portal →</a></p>
        </div>
        <div class="pr-detail-grid">
          <section class="pr-panel">
            <h2>Invitation to bid</h2>
            <div id="prPkgScopeSlot" class="pr-html-content"></div>
            <div id="prPkgInstrSlot" class="pr-html-content"></div>
            <div id="prPkgQualSlot"></div>
            ${itb.wage_requirements ? `<p><strong>Prevailing wage:</strong> ${esc(itb.wage_requirements)}</p>` : ''}
            ${meetingBlock('Pre-bid meeting', itb.pre_bid_meeting && itb.pre_bid_meeting.date ? itb.pre_bid_meeting : pr.pre_bid_meeting)}
            ${meetingBlock('Job walk', itb.job_walk)}
            ${itb.bonding && (itb.bonding.bid_bond_percent || itb.bonding.notes) ? `
              <div class="pr-itb-block"><h3>Bonding</h3>
              <p class="pr-project-meta">Bid bond: ${esc(itb.bonding.bid_bond_percent || '—')}</p>
              <p>${esc(itb.bonding.notes || '')}</p></div>` : ''}
          </section>
          <section class="pr-panel">
            <h2>Plans, specs &amp; exhibits</h2>
            ${zipUrl ? `<p class="pr-project-meta"><a class="pr-download" href="${esc(zipUrl)}">Download package documents (.zip)</a></p>` : ''}
            <input type="search" class="pr-search pr-doc-search" id="prPkgDocSearch" placeholder="Search documents…">
            <div id="prPkgDocWrap">${renderSections(sections)}</div>
          </section>
        </div>
        ${addenda.length ? `<section class="pr-panel"><h2>Addenda</h2>${addenda.map((a) => `
          <div class="pr-pkg-card">
            <strong>${esc(a.number)} — ${esc(a.title)}</strong>
            ${a.require_rebid ? '<span class="pr-tag">Re-bid required</span>' : ''}
            ${a.acknowledged ? '<span class="pr-tag">Acknowledged</span>' : '<span class="pr-tag">Acknowledgment required</span>'}
            <p class="pr-project-meta">${esc(a.description || '')}</p>
            ${(a.documents || []).length ? `<ul class="pr-doc-list">${a.documents.map((d) => docRow(d)).join('')}</ul>` : ''}
            ${!a.acknowledged ? `<button type="button" class="pr-btn pr-ack-addendum" data-id="${a.id}" style="margin-top:0.5rem;background:var(--pr-accent);color:#fff;border:none;padding:0.4rem 0.8rem;border-radius:8px;cursor:pointer">I acknowledge this addendum</button>` : ''}
          </div>`).join('')}</section>` : ''}
      `;
      const scopeSlot = document.getElementById('prPkgScopeSlot');
      const instrSlot = document.getElementById('prPkgInstrSlot');
      const qualSlot = document.getElementById('prPkgQualSlot');
      if (scopeSlot && itb.scope_summary_html) scopeSlot.innerHTML = itb.scope_summary_html;
      else scopeSlot?.remove();
      const instr = itb.instructions_html || pr.instructions_html;
      if (instrSlot && instr) instrSlot.innerHTML = instr;
      else instrSlot?.remove();
      if (qualSlot && itb.qualifications_html) {
        qualSlot.innerHTML = `<div class="pr-itb-block"><h3>Qualifications</h3><div class="pr-html-content">${itb.qualifications_html}</div></div>`;
      } else qualSlot?.remove();
      if (PRD.bindDocumentSearch) {
        PRD.bindDocumentSearch(document.getElementById('prPkgDocSearch'), document.getElementById('prPkgDocWrap'));
      }
      host.querySelectorAll('.pr-ack-addendum').forEach((btn) => {
        btn.addEventListener('click', async () => {
          await fetch(`/api/bidder-network/addenda/${btn.dataset.id}/acknowledge`, {
            method: 'POST',
            credentials: 'same-origin',
          });
          location.reload();
        });
      });
    })
    .catch(() => {
      host.innerHTML = '<p class="pr-muted">Could not load package.</p>';
    });
})();
