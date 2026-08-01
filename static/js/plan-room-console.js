(function () {
  'use strict';

  const ctx = window.CASEPM_PLAN_ROOM_CTX || {};
  let consoleData = null;
  let selectedPackageId = null;
  let manifestCategories = [];

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function api(path, opts) {
    const res = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', ...(opts?.headers || {}) },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  function showTab(name) {
    document.querySelectorAll('#prcTabs button').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === name);
    });
    document.querySelectorAll('.prc-tab-panel').forEach((panel) => panel.classList.add('prc-is-hidden'));
    const map = { project: 'prcTabProject', packages: 'prcTabPackages', bidders: 'prcTabBidders' };
    document.getElementById(map[name])?.classList.remove('prc-is-hidden');
    if (name === 'packages') {
      if (!selectedPackageId && consoleData?.packages?.length) {
        selectedPackageId = consoleData.packages[0].id;
      }
      renderPackageList();
      renderPackageEditor();
    }
    if (name === 'bidders') loadBidders();
  }

  function fillProjectForm(pr) {
    const form = document.getElementById('prcProjectForm');
    if (!form || !pr) return;
    form.published.checked = !!pr.published;
    form.summary.value = pr.summary || '';
    form.instructions_html.value = pr.instructions_html || '';
    form.bid_date.value = (pr.bid_date || '').slice(0, 10);
    form.bid_due_time.value = pr.bid_due_time || '';
    form.timezone.value = pr.timezone || 'America/Denver';
    form.pre_bid_date.value = (pr.pre_bid_date || '').slice(0, 10);
    form.owner_name.value = pr.owner_name || '';
    form.architect_name.value = pr.architect_name || '';
    form.engineer_name.value = pr.engineer_name || '';
    form.project_address.value = pr.project_address || '';
    form.contact_name.value = pr.contact_name || '';
    form.contact_email.value = pr.contact_email || '';
    form.contact_phone.value = pr.contact_phone || '';
    const pbm = pr.pre_bid_meeting || {};
    form.pre_bid_meeting_date.value = (pbm.date || '').slice(0, 10);
    form.pre_bid_meeting_time.value = pbm.time || '';
    form.pre_bid_meeting_location.value = pbm.location || '';
    form.pre_bid_meeting_virtual_url.value = pbm.virtual_url || '';
    form.pre_bid_meeting_mandatory.checked = !!pbm.mandatory;
    form.pre_bid_meeting_notes.value = pbm.notes || '';
    const jw = pr.job_walk || {};
    form.job_walk_date.value = (jw.date || '').slice(0, 10);
    form.job_walk_time.value = jw.time || '';
    form.job_walk_location.value = jw.location || '';
    form.job_walk_mandatory.checked = !!jw.mandatory;
    form.job_walk_notes.value = jw.notes || '';
    const bond = pr.bonding || {};
    form.bid_bond_percent.value = bond.bid_bond_percent || '';
    form.performance_bond.value = bond.performance_bond || '';
    form.payment_bond.value = bond.payment_bond || '';
    form.bonding_notes.value = bond.notes || '';
  }

  function projectPayloadFromForm(form) {
    return {
      published: form.published.checked,
      summary: form.summary.value,
      instructions_html: form.instructions_html.value,
      bid_date: form.bid_date.value || null,
      bid_due_time: form.bid_due_time.value,
      timezone: form.timezone.value,
      pre_bid_date: form.pre_bid_date.value || null,
      owner_name: form.owner_name.value,
      architect_name: form.architect_name.value,
      engineer_name: form.engineer_name.value,
      project_address: form.project_address.value,
      contact_name: form.contact_name.value,
      contact_email: form.contact_email.value,
      contact_phone: form.contact_phone.value,
      pre_bid_meeting: {
        date: form.pre_bid_meeting_date.value,
        time: form.pre_bid_meeting_time.value,
        location: form.pre_bid_meeting_location.value,
        virtual_url: form.pre_bid_meeting_virtual_url.value,
        mandatory: form.pre_bid_meeting_mandatory.checked,
        notes: form.pre_bid_meeting_notes.value,
      },
      job_walk: {
        date: form.job_walk_date.value,
        time: form.job_walk_time.value,
        location: form.job_walk_location.value,
        mandatory: form.job_walk_mandatory.checked,
        notes: form.job_walk_notes.value,
      },
      bonding: {
        bid_bond_percent: form.bid_bond_percent.value,
        performance_bond: form.performance_bond.value,
        payment_bond: form.payment_bond.value,
        notes: form.bonding_notes.value,
      },
    };
  }

  function renderPackageList() {
    const host = document.getElementById('prcPackageList');
    if (!host || !consoleData) return;
    const pkgs = consoleData.packages || [];
    if (!pkgs.length) {
      host.innerHTML = '<p class="p-3 text-sm text-zinc-500">No bid packages on this project. Create packages in Estimating first.</p>';
      return;
    }
    host.innerHTML = pkgs.map((p) => `
      <button type="button" class="prc-package-item${selectedPackageId === p.id ? ' active' : ''}" data-id="${p.id}">
        <div class="font-medium">${esc(p.title || p.number)}</div>
        <div class="text-xs text-zinc-400">${esc(p.spec_section || '')} · ${p.network_published ? 'Published' : 'Draft'}</div>
      </button>
    `).join('');
    host.querySelectorAll('.prc-package-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedPackageId = Number(btn.dataset.id);
        renderPackageList();
        renderPackageEditor();
      });
    });
  }

  function docOptions(selectedId) {
    const docs = consoleData?.project_documents || [];
    return docs.map((d) => `<option value="${d.id}"${Number(selectedId) === d.id ? ' selected' : ''}>${esc(d.name)} (${esc(d.filename)})</option>`).join('');
  }

  function renderPackageEditor() {
    const host = document.getElementById('prcPackageEditor');
    if (!host || !consoleData) return;
    const pkg = (consoleData.packages || []).find((p) => p.id === selectedPackageId);
    if (!pkg) {
      host.innerHTML = '<p class="text-zinc-500 text-sm">Select a bid package to edit its plan room manifest.</p>';
      return;
    }
    const manifest = pkg.manifest || { itb: {}, documents: {} };
    const itb = manifest.itb || {};
    const docs = manifest.documents || {};

    const sectionsHtml = manifestCategories.map((cat) => {
      const entries = docs[cat.key] || [];
      const rows = entries.map((entry, idx) => `
        <div class="prc-doc-row" data-cat="${cat.key}" data-idx="${idx}">
          <select class="prc-doc-id">${docOptions(entry.document_id)}</select>
          <input type="text" class="prc-doc-title" placeholder="Label override" value="${esc(entry.title || '')}">
          <input type="text" class="prc-doc-sheet" placeholder="Sheet / division" value="${esc(entry.sheet || '')}">
          <button type="button" class="prc-btn prc-btn-ghost text-xs prc-doc-remove">Remove</button>
        </div>
      `).join('');
      return `
        <div class="prc-doc-section" data-category="${cat.key}">
          <h3>${esc(cat.label)}</h3>
          <div class="prc-doc-rows">${rows}</div>
          <div class="flex flex-wrap gap-2 mt-2">
            <button type="button" class="prc-btn prc-btn-ghost text-xs prc-add-doc" data-cat="${cat.key}">Add existing document</button>
            <label class="prc-btn prc-btn-ghost text-xs cursor-pointer">
              Upload file
              <input type="file" class="hidden prc-upload" data-cat="${cat.key}">
            </label>
          </div>
        </div>
      `;
    }).join('');

    host.innerHTML = `
      <div class="flex flex-wrap justify-between gap-2 mb-3">
        <div>
          <h2 class="text-base font-semibold text-white">${esc(pkg.title || pkg.number)}</h2>
          <p class="text-xs text-zinc-400">Spec ${esc(pkg.spec_section || '—')} · Status ${esc(pkg.status || '')}</p>
        </div>
        <label class="prc-check-row text-sm">
          <input type="checkbox" id="prcPkgPublished" ${pkg.network_published ? 'checked' : ''}>
          Published to plan room
        </label>
      </div>
      <label class="block text-xs text-zinc-400 mb-3">Public package summary<textarea id="prcPkgSummary" rows="2" class="w-full mt-1">${esc(pkg.summary || '')}</textarea></label>
      <fieldset class="prc-fieldset mb-3">
        <legend>Package ITB (overrides project defaults where filled)</legend>
        <label class="block text-xs text-zinc-400 mb-2">Scope summary (HTML)<textarea id="prcItbScope" rows="3" class="w-full mt-1">${esc(itb.scope_summary_html || '')}</textarea></label>
        <label class="block text-xs text-zinc-400 mb-2">Instructions (HTML)<textarea id="prcItbInstructions" rows="3" class="w-full mt-1">${esc(itb.instructions_html || '')}</textarea></label>
        <label class="block text-xs text-zinc-400">Qualifications (HTML)<textarea id="prcItbQual" rows="2" class="w-full mt-1">${esc(itb.qualifications_html || '')}</textarea></label>
      </fieldset>
      <h3 class="text-sm font-medium text-zinc-300 mb-2">Document manifest</h3>
      ${sectionsHtml}
      <div class="mt-4 flex flex-wrap gap-2 items-center">
        <button type="button" id="prcSavePackage" class="prc-btn prc-btn-primary">Save package manifest</button>
        <button type="button" id="prcSyncEstimating" class="prc-btn prc-btn-ghost">Import from estimating attachments</button>
        <a href="/estimating" class="prc-btn prc-btn-ghost">Open estimating</a>
        <a href="/plan-room/projects/${ctx.projectId}/packages/${pkg.id}" target="_blank" rel="noopener" class="prc-btn prc-btn-ghost">Preview as bidder</a>
        <span id="prcPkgMsg" class="prc-msg"></span>
      </div>
    `;

    host.querySelectorAll('.prc-add-doc').forEach((btn) => {
      btn.addEventListener('click', () => {
        const cat = btn.dataset.cat;
        const section = host.querySelector(`.prc-doc-section[data-category="${cat}"] .prc-doc-rows`);
        const div = document.createElement('div');
        div.className = 'prc-doc-row';
        div.dataset.cat = cat;
        div.innerHTML = `
          <select class="prc-doc-id">${docOptions()}</select>
          <input type="text" class="prc-doc-title" placeholder="Label override">
          <input type="text" class="prc-doc-sheet" placeholder="Sheet / division">
          <button type="button" class="prc-btn prc-btn-ghost text-xs prc-doc-remove">Remove</button>
        `;
        section.appendChild(div);
        bindDocRow(div);
      });
    });

    host.querySelectorAll('.prc-upload').forEach((input) => {
      input.addEventListener('change', async () => {
        const file = input.files?.[0];
        if (!file || !ctx.projectId) return;
        const cat = input.dataset.cat;
        const fd = new FormData();
        fd.append('file', file);
        fd.append('category', cat);
        fd.append('name', file.name);
        try {
          const out = await api(`/api/bidder-network/admin/projects/${ctx.projectId}/plan-documents`, {
            method: 'POST',
            body: fd,
          });
          await loadConsole();
          selectedPackageId = pkg.id;
          renderPackageList();
          renderPackageEditor();
          const docId = out.document?.id;
          if (docId) {
            const section = document.querySelector(`.prc-doc-section[data-category="${cat}"] .prc-doc-rows`);
            const div = document.createElement('div');
            div.className = 'prc-doc-row';
            div.innerHTML = `
              <select class="prc-doc-id">${docOptions(docId)}</select>
              <input type="text" class="prc-doc-title" placeholder="Label override" value="${esc(file.name)}">
              <input type="text" class="prc-doc-sheet" placeholder="Sheet / division">
              <button type="button" class="prc-btn prc-btn-ghost text-xs prc-doc-remove">Remove</button>
            `;
            section?.appendChild(div);
            bindDocRow(div);
          }
        } catch (e) {
          alert(e.message);
        }
        input.value = '';
      });
    });

    host.querySelectorAll('.prc-doc-row').forEach(bindDocRow);

    document.getElementById('prcSavePackage')?.addEventListener('click', savePackageManifest);
    document.getElementById('prcSyncEstimating')?.addEventListener('click', async () => {
      if (!selectedPackageId) return;
      const msg = document.getElementById('prcPkgMsg');
      try {
        const out = await api(`/api/bidder-network/admin/bid-packages/${selectedPackageId}/sync-estimating`, { method: 'POST', body: '{}' });
        if (msg) msg.textContent = `Imported ${out.added || 0} document(s) from estimating.`;
        await loadConsole();
        renderPackageList();
        renderPackageEditor();
      } catch (e) {
        alert(e.message);
      }
    });
  }

  function bindDocRow(row) {
    row.querySelector('.prc-doc-remove')?.addEventListener('click', () => row.remove());
  }

  function collectManifestFromEditor() {
    const host = document.getElementById('prcPackageEditor');
    const documents = {};
    manifestCategories.forEach((cat) => {
      documents[cat.key] = [];
      host.querySelectorAll(`.prc-doc-section[data-category="${cat.key}"] .prc-doc-row`).forEach((row, idx) => {
        const did = row.querySelector('.prc-doc-id')?.value;
        if (!did) return;
        documents[cat.key].push({
          document_id: Number(did),
          title: row.querySelector('.prc-doc-title')?.value || '',
          sheet: row.querySelector('.prc-doc-sheet')?.value || '',
          sort_order: idx,
        });
      });
    });
    return {
      itb: {
        scope_summary_html: document.getElementById('prcItbScope')?.value || '',
        instructions_html: document.getElementById('prcItbInstructions')?.value || '',
        qualifications_html: document.getElementById('prcItbQual')?.value || '',
      },
      documents,
    };
  }

  async function savePackageManifest() {
    if (!selectedPackageId) return;
    const msg = document.getElementById('prcPkgMsg');
    try {
      await api(`/api/bidder-network/admin/bid-packages/${selectedPackageId}/manifest`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manifest: collectManifestFromEditor(),
          network_summary: document.getElementById('prcPkgSummary')?.value,
          network_published: document.getElementById('prcPkgPublished')?.checked,
        }),
      });
      if (msg) msg.textContent = 'Saved.';
      await loadConsole();
      selectedPackageId = selectedPackageId;
      renderPackageList();
      renderPackageEditor();
    } catch (e) {
      if (msg) msg.textContent = '';
      alert(e.message);
    }
  }

  async function loadConsole() {
    if (!ctx.projectId) return;
    consoleData = await api(`/api/bidder-network/admin/projects/${ctx.projectId}/console`);
    manifestCategories = consoleData.manifest_categories || [];
    fillProjectForm(consoleData.plan_room);
    renderPackageList();
    if (selectedPackageId) renderPackageEditor();
  }

  async function loadBidders() {
    const host = document.getElementById('prcBiddersPending');
    if (!host) return;
    host.innerHTML = '<p class="text-xs text-zinc-500">Loading…</p>';
    try {
      const data = await api('/api/bidder-network/registrations?status=pending');
      const rows = data.registrations || [];
      if (!rows.length) {
        host.innerHTML = '<p class="text-xs text-zinc-500">No pending registrations.</p>';
        return;
      }
      host.innerHTML = rows.map((r) => `
        <div class="border border-zinc-700 rounded-md p-3 flex flex-wrap justify-between gap-2">
          <div>
            <div class="font-medium text-white">${esc(r.company_name)}</div>
            <div class="text-xs text-zinc-400">${esc(r.contact_name)} · ${esc(r.email)}</div>
          </div>
          <div class="flex gap-2">
            <button type="button" class="prc-approve prc-btn prc-btn-primary text-xs" data-id="${r.id}">Approve</button>
            <button type="button" class="prc-reject prc-btn prc-btn-ghost text-xs" data-id="${r.id}">Reject</button>
          </div>
        </div>
      `).join('');
      host.querySelectorAll('.prc-approve').forEach((btn) => btn.addEventListener('click', async () => {
        await api(`/api/bidder-network/registrations/${btn.dataset.id}/approve`, { method: 'POST', body: '{}' });
        loadBidders();
      }));
      host.querySelectorAll('.prc-reject').forEach((btn) => btn.addEventListener('click', async () => {
        const reason = prompt('Rejection reason (optional):') || '';
        await api(`/api/bidder-network/registrations/${btn.dataset.id}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason }),
        });
        loadBidders();
      }));
    } catch (e) {
      host.innerHTML = `<p class="text-xs text-red-400">${esc(e.message)}</p>`;
    }
  }


  function bindConsoleUi() {
    document.getElementById('prcTabs')?.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-tab]');
      if (btn) showTab(btn.dataset.tab);
    });
    document.getElementById('prcProjectForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const msg = document.getElementById('prcProjectMsg');
      try {
        await api(`/api/bidder-network/projects/${ctx.projectId}/publish`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(projectPayloadFromForm(e.target)),
        });
        if (msg) msg.textContent = 'Project ITB saved.';
        await loadConsole();
      } catch (err) {
        if (msg) msg.textContent = '';
        alert(err.message);
      }
    });
    document.getElementById('prcPublishAll')?.addEventListener('click', async () => {
      if (!ctx.projectId || !confirm('Publish this project and all bid packages to the plan room?')) return;
      const form = document.getElementById('prcProjectForm');
      const payload = { ...projectPayloadFromForm(form), published: true, publish_all_packages: true };
      await api(`/api/bidder-network/projects/${ctx.projectId}/publish`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      await loadConsole();
      alert('Published.');
    });
    document.getElementById('prcBiddersRefresh')?.addEventListener('click', loadBidders);
  }

  function init() {
    bindConsoleUi();
    const params = new URLSearchParams(window.location.search);
    const pkgParam = params.get('package_id');
    if (pkgParam) {
      selectedPackageId = Number(pkgParam);
    }
    const noProject = document.getElementById('prcNoProject');
    const app = document.getElementById('prcApp');
    if (!ctx.projectId) {
      noProject?.classList.remove('prc-is-hidden');
      return;
    }
    noProject?.classList.add('prc-is-hidden');
    app?.classList.remove('prc-is-hidden');
    loadConsole()
      .then(() => {
        if (pkgParam || params.get('tab') === 'packages') {
          showTab('packages');
        } else if (params.get('tab') === 'bidders') {
          showTab('bidders');
        }
      })
      .catch((e) => alert(e.message));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
