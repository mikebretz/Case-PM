(function () {
  'use strict';

  const root = document.getElementById('prProjectDetailRoot');
  const host = document.getElementById('prProjectDetail');
  if (!root || !host) return;

  const projectId = root.dataset.projectId;
  const approved = root.dataset.approved === '1';
  const isStaff = root.dataset.staff === '1';
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

  function formatBytes(n) {
    return PRD.formatBytes ? PRD.formatBytes(n) : String(n);
  }

  function docRow(d) {
    return PRD.renderListItem ? PRD.renderListItem(d) : `<li>${esc(d.name)}</li>`;
  }

  function meetingLine(label, block) {
    if (!block || (!block.date && !block.time && !block.location && !block.notes)) return '';
    return `<p class="pr-project-meta"><strong>${esc(label)}:</strong> ${formatDate(block.date)}${block.time ? ` ${esc(block.time)}` : ''}${block.location ? ` · ${esc(block.location)}` : ''}${block.mandatory ? ' (mandatory)' : ''}${block.notes ? ` — ${esc(block.notes)}` : ''}</p>`;
  }

  function keyDatesHtml(pr, p) {
    const pbm = pr.pre_bid_meeting || {};
    const jw = pr.job_walk || {};
    return `
      <aside class="pr-key-dates">
        <h3>Key dates</h3>
        <dl>
          <div><dt>Bid due</dt><dd>${formatDate(p.bid_date || pr.bid_date)}${pr.bid_due_time ? ` · ${esc(pr.bid_due_time)}` : ''}</dd></div>
          ${pr.pre_bid_date ? `<div><dt>Pre-bid</dt><dd>${formatDate(pr.pre_bid_date)}</dd></div>` : ''}
          ${pbm.date ? `<div><dt>Pre-bid meeting</dt><dd>${formatDate(pbm.date)}${pbm.time ? ` ${esc(pbm.time)}` : ''}</dd></div>` : ''}
          ${jw.date ? `<div><dt>Job walk</dt><dd>${formatDate(jw.date)}${jw.time ? ` ${esc(jw.time)}` : ''}</dd></div>` : ''}
        </dl>
        ${isStaff ? `<p class="pr-project-meta" style="margin-top:0.75rem"><a href="/plan-room/console">Edit in plan room console</a> · <a href="/estimating">Estimating</a></p>` : ''}
      </aside>`;
  }

  function bindTabs(container) {
    const panels = { docs: 'prPanelDocs', packages: 'prPanelPackages', addenda: 'prPanelAddenda', qa: 'prPanelQa' };
    container.querySelectorAll('.pr-subnav-tabs button').forEach((btn) => {
      btn.addEventListener('click', () => {
        container.querySelectorAll('.pr-subnav-tabs button').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        Object.values(panels).forEach((id) => document.getElementById(id)?.classList.add('hidden'));
        document.getElementById(panels[btn.dataset.panel])?.classList.remove('hidden');
      });
    });
  }

  if (!approved) {
    host.innerHTML = '<div class="pr-gate">Sign in with an approved plan room account to view plans and documents. <a href="/plan-room#prRegister">Register</a> or contact estimating if your application is pending.</div>';
    return;
  }

  fetch(`/api/bidder-network/projects/${projectId}`, { credentials: 'same-origin' })
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || data.error) {
        host.innerHTML = `<div class="pr-gate">${esc(data.error || 'Could not load this project.')}${isStaff ? ' <a href="/plan-room/console">Open plan room console</a> to publish it.' : ''}</div>`;
        return;
      }
      const p = data.project || {};
      const docs = data.documents || [];
      const sections = data.document_sections || [];
      const pkgs = data.packages || [];
      const addenda = data.addenda || [];
      const pr = data.plan_room || {};

      const docsPanel = sections.length
        ? sections.map((sec) => `
          <div class="pr-itb-block">
            <h3>${esc(sec.label)}</h3>
            <ul class="pr-doc-list">${(sec.documents || []).map((d) => docRow(d)).join('')}</ul>
          </div>`).join('')
        : (docs.length ? `<ul class="pr-doc-list">${docs.map((d) => docRow(d)).join('')}</ul>` : '<p class="pr-muted">No documents attached yet. Check back for addenda.</p>');

      const packagesPanel = pkgs.length ? pkgs.map((pkg) => `
            <div class="pr-pkg-card">
              <a class="pr-pkg-link" href="${esc(pkg.detail_url || `/plan-room/projects/${projectId}/packages/${pkg.id}`)}">${esc(pkg.title || pkg.number)}</a>
              <div class="pr-project-meta">Spec ${esc(pkg.spec_section || '—')} · Due ${formatDate(pkg.due_date)}</div>
              <p class="pr-project-meta">${esc(pkg.summary || '')}</p>
              <a class="pr-download" href="${esc(pkg.detail_url || `/plan-room/projects/${projectId}/packages/${pkg.id}`)}">View full ITB &amp; documents →</a>
            </div>
          `).join('') : '<p class="pr-muted">No published packages.</p>';

      const clarifications = data.clarifications || [];
      const zipUrl = data.documents_zip_url || '';
      const pendingAcks = data.pending_addendum_acks || 0;

      const addendaPanel = addenda.length ? addenda.map((a) => `
            <div class="pr-pkg-card" data-addendum-id="${a.id}">
              <strong>${esc(a.number)} — ${esc(a.title)}</strong> <span class="pr-project-meta">(${esc(a.package_title)})</span>
              ${a.require_rebid ? '<span class="pr-tag">Re-bid required</span>' : ''}
              ${a.acknowledged ? '<span class="pr-tag">Acknowledged</span>' : '<span class="pr-tag">Acknowledgment required</span>'}
              <p class="pr-project-meta">${esc(a.description || '')}</p>
              ${(a.documents || []).length ? `<ul class="pr-doc-list">${a.documents.map((d) => docRow(d)).join('')}</ul>` : ''}
              ${!a.acknowledged && !isStaff ? `<button type="button" class="pr-btn pr-ack-addendum" data-id="${a.id}" style="margin-top:0.5rem">I acknowledge this addendum</button>` : ''}
            </div>`).join('') : '<p class="pr-muted">No addenda issued.</p>';

      const qaPanel = `
        <div class="pr-itb-block">
          <h3>Public Q&amp;A</h3>
          <div id="prQaThread">${clarifications.length ? clarifications.map((q) => `
            <div class="pr-pkg-card">
              <strong>${esc(q.subject || 'Question')}</strong>
              <p class="pr-project-meta">${esc(q.asker_company)} · ${esc((q.created_at || '').slice(0, 10))}</p>
              <p>${esc(q.question_text)}</p>
              ${q.answer_text ? `<p class="pr-project-meta" style="margin-top:0.5rem"><strong>Answer:</strong> ${esc(q.answer_text)}</p>` : '<p class="pr-muted">Awaiting answer from estimating.</p>'}
            </div>`).join('') : '<p class="pr-muted">No questions posted yet.</p>'}
          </div>
          ${isStaff ? '' : `
          <form id="prAskQuestion" class="mt-3">
            <label class="pr-muted">Ask a clarification (visible to all bidders once answered)</label>
            <input type="text" name="subject" class="pr-search" placeholder="Subject" style="margin:0.35rem 0">
            <textarea name="question" rows="3" class="pr-search" style="width:100%;margin-bottom:0.5rem" placeholder="Your question…" required></textarea>
            <button type="submit" class="pr-btn" style="background:var(--pr-accent);color:#fff;border:none;padding:0.5rem 1rem;border-radius:8px;cursor:pointer">Submit question</button>
          </form>`}
        </div>`;
      host.innerHTML = `
        <div class="pr-detail-with-sidebar">
          <div>
            <div class="pr-detail-hero">
              <h1>${esc(p.name)}</h1>
              <div class="pr-project-meta">${esc(p.number)} · ${esc(p.location)} · ${esc(p.project_type || '')}</div>
              <div class="pr-due" style="margin-top:0.5rem">Bid date: ${formatDate(p.bid_date)}${pr.bid_due_time ? ` at ${esc(pr.bid_due_time)}` : ''}</div>
              ${pr.owner_name ? `<p class="pr-project-meta">Owner: ${esc(pr.owner_name)}</p>` : ''}
              ${pr.architect_name ? `<p class="pr-project-meta">Architect: ${esc(pr.architect_name)}</p>` : ''}
              ${pr.contact_email ? `<p class="pr-project-meta">Bid contact: ${esc(pr.contact_name || '')} <a href="mailto:${esc(pr.contact_email)}">${esc(pr.contact_email)}</a>${pr.contact_phone ? ` · ${esc(pr.contact_phone)}` : ''}</p>` : ''}
              <p style="margin-top:0.75rem">${esc(p.summary || pr.summary || '')}</p>
              <div id="prInstructionsSlot" class="pr-html-content" style="margin-top:0.75rem"></div>
              ${meetingLine('Pre-bid meeting', pr.pre_bid_meeting)}
              ${meetingLine('Job walk', pr.job_walk)}
            </div>
            ${pendingAcks && !isStaff ? `<div class="pr-gate">You have ${pendingAcks} addendum(s) to acknowledge before bidding.</div>` : ''}
            <nav class="pr-subnav-tabs">
              <button type="button" class="active" data-panel="docs">Plans &amp; specs</button>
              <button type="button" data-panel="packages">Bid packages (${pkgs.length})</button>
              <button type="button" data-panel="addenda">Addenda (${addenda.length})</button>
              <button type="button" data-panel="qa">Q&amp;A (${clarifications.length})</button>
            </nav>
            <div id="prPanelDocs" class="pr-panel">
              ${zipUrl ? `<p class="pr-project-meta"><a class="pr-download" href="${esc(zipUrl)}">Download all plans &amp; specs (.zip)</a></p>` : ''}
              <input type="search" class="pr-search pr-doc-search" id="prDocSearch" placeholder="Search documents by name…">
              <div id="prDocListWrap">${docsPanel}</div>
            </div>
            <div id="prPanelPackages" class="pr-panel hidden">${packagesPanel}</div>
            <div id="prPanelAddenda" class="pr-panel hidden">${addendaPanel}</div>
            <div id="prPanelQa" class="pr-panel hidden">${qaPanel}</div>
          </div>
          ${keyDatesHtml(pr, p)}
        </div>
      `;

      const instrSlot = document.getElementById('prInstructionsSlot');
      if (instrSlot && pr.instructions_html) {
        instrSlot.innerHTML = pr.instructions_html;
      } else if (instrSlot) {
        instrSlot.remove();
      }

      bindTabs(host);
      if (PRD.bindDocumentSearch) {
        PRD.bindDocumentSearch(document.getElementById('prDocSearch'), document.getElementById('prDocListWrap'));
      }
      host.querySelectorAll('.pr-ack-addendum').forEach((btn) => {
        btn.addEventListener('click', async () => {
          await fetch(`/api/bidder-network/addenda/${btn.dataset.id}/acknowledge`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
          });
          location.reload();
        });
      });
      document.getElementById('prAskQuestion')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        await fetch(`/api/bidder-network/projects/${projectId}/clarifications`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({
            subject: fd.get('subject'),
            question_text: fd.get('question'),
          }),
        });
        location.reload();
      });
    })
    .catch((err) => {
      console.error('plan room project detail', err);
      host.innerHTML = '<p class="pr-muted">Could not load project. Try refreshing or sign in again.</p>';
    });
})();
