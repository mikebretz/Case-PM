(function (global) {
  'use strict';

  const state = { estimates: [], current: null, takeoffItems: [], tab: 'summary', specBookSections: [], hasSpecBook: false };

  function pid() {
    if (global.CASEPM_ESTIMATE_CTX?.projectId) return global.CASEPM_ESTIMATE_CTX.projectId;
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function fmt(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  function openDialog(el) {
    if (!el) return;
    if (global.CasePMDialog?.open) global.CasePMDialog.open(el);
    else el.showModal();
  }

  function closeDialog(el) {
    if (!el) return;
    if (typeof el.close === 'function') el.close();
  }

  async function estAlert(message, type = 'info') {
    if (global.CasePMDialog?.alert) return global.CasePMDialog.alert(message, type);
    alert(message);
  }

  async function estConfirm(message, options = {}) {
    if (global.CasePMDialog?.confirm) return global.CasePMDialog.confirm(message, options);
    return confirm(message);
  }

  async function estPrompt(message, defaultValue = '', options = {}) {
    if (global.CasePMDialog?.prompt) return global.CasePMDialog.prompt(message, defaultValue, options);
    return prompt(message, defaultValue);
  }

  function toast(msg, type = 'success') {
    estAlert(msg, type);
  }

  function setTab(tab) {
    state.tab = tab;
    document.querySelectorAll('#estTabBar button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    document.querySelectorAll('.est-panel').forEach(p => p.classList.add('hidden'));
    const panel = document.getElementById(`estPanel${tab.charAt(0).toUpperCase() + tab.slice(1)}`);
    if (panel) panel.classList.remove('hidden');
    if (tab === 'leveling') renderLeveling();
    if (tab === 'takeoff') loadTakeoffPreview();
  }

  function updateSummaryBar(est) {
    if (!est) return;
    document.getElementById('estDirectTotal').textContent = fmt(est.direct_cost_total);
    document.getElementById('estLoadedTotal').textContent = fmt(est.total_amount);
    const pkgs = est.bid_packages || [];
    document.getElementById('estPkgCount').textContent = String(pkgs.length);
    let sent = 0;
    let quotes = 0;
    pkgs.forEach(p => (p.invitations || []).forEach(i => {
      if (i.status === 'Sent' || i.status === 'Viewed' || i.status === 'Quoted' || i.status === 'Awarded' || i.status === 'Declined' || i.status === 'Not Interested') sent += 1;
      if (i.status === 'Quoted' || i.status === 'Awarded') quotes += 1;
    }));
    document.getElementById('estInviteCount').textContent = String(sent);
    document.getElementById('estQuoteCount').textContent = String(quotes);
    document.getElementById('estStatusBadge').textContent = est.status || 'Draft';
  }

  function fillSummaryForm(est) {
    document.getElementById('estTitle').value = est.title || '';
    document.getElementById('estDescription').value = est.description || '';
    document.getElementById('estType').value = est.estimate_type || 'Hard Bid';
    document.getElementById('estStatus').value = est.status || 'Draft';
    document.getElementById('estBidDate').value = est.bid_date || '';
    document.getElementById('estDueDate').value = est.due_date || '';
    document.getElementById('estContingency').value = est.contingency_pct ?? 5;
    document.getElementById('estOverhead').value = est.overhead_pct ?? 10;
    document.getElementById('estProfit').value = est.profit_pct ?? 10;
    document.getElementById('estTax').value = est.tax_pct ?? 0;
  }

  async function loadSpecBookSections() {
    const id = pid();
    if (!id) {
      state.specBookSections = [];
      state.hasSpecBook = false;
      return;
    }
    try {
      const json = await api(`/api/estimates/spec-book-sections?project_id=${id}`);
      state.specBookSections = json.sections || [];
      state.hasSpecBook = !!json.has_spec_book;
      const dl = document.getElementById('estSpecBookDatalist');
      if (dl) {
        dl.innerHTML = state.specBookSections.map(s =>
          `<option value="${esc(s.code)}">${esc(s.label || s.title || s.code)}</option>`,
        ).join('');
      }
    } catch (_) {
      state.specBookSections = [];
      state.hasSpecBook = false;
    }
  }

  function specSectionCellHtml(value) {
    const pick = state.specBookSections.length
      ? `<select class="est-spec-pick w-full bg-zinc-900/80 text-[10px] text-zinc-400 border-0 border-t border-zinc-800/80 px-1.5 py-0.5 cursor-pointer hover:text-zinc-200" title="Pick from project spec book">
          <option value="">▼ Spec book</option>
          ${state.specBookSections.map(s => `<option value="${esc(s.code)}">${esc(s.code)}${s.title && s.title !== s.code ? ` — ${esc(s.title)}` : ''}</option>`).join('')}
        </select>`
      : '';
    return `<td class="p-0 align-top min-w-[130px]">
      <input data-f="spec_section" value="${esc(value)}" class="w-full bg-transparent border-0 px-2 py-1.5 text-sm" placeholder="09 21 00" list="estSpecBookDatalist" title="${state.hasSpecBook ? 'Type a spec # or pick from spec book below' : 'Spec section number'}">
      ${pick}
    </td>`;
  }

  function wireSpecSectionCells(root) {
    (root || document).querySelectorAll('.est-spec-pick').forEach(sel => {
      if (sel.dataset.wired) return;
      sel.dataset.wired = '1';
      sel.addEventListener('change', () => {
        if (!sel.value) return;
        const inp = sel.closest('td')?.querySelector('[data-f="spec_section"]');
        if (inp) inp.value = sel.value;
        sel.value = '';
      });
    });
  }

  function readWorksheetLines() {
    const rows = [];
    document.querySelectorAll('#estWorksheetBody tr').forEach(tr => {
      const get = name => tr.querySelector(`[data-f="${name}"]`)?.value ?? '';
      rows.push({
        cost_code: get('cost_code'),
        spec_section: get('spec_section'),
        description: get('description'),
        cost_type: get('cost_type'),
        quantity: parseFloat(get('quantity')) || 0,
        unit: get('unit'),
        unit_cost: parseFloat(get('unit_cost')) || 0,
        source: tr.dataset.source || 'manual',
        source_ref: tr.dataset.sourceRef || '',
        notes: get('notes'),
      });
    });
    return rows;
  }

  function filteredLines(lines) {
    const q = (document.getElementById('estLineSearch')?.value || '').trim().toLowerCase();
    if (!q) return lines;
    return lines.filter(l =>
      (l.cost_code || '').toLowerCase().includes(q) ||
      (l.spec_section || '').toLowerCase().includes(q) ||
      (l.description || '').toLowerCase().includes(q)
    );
  }

  function renderWorksheet(est) {
    const body = document.getElementById('estWorksheetBody');
    if (!body) return;
    const lines = filteredLines(est.lines || []);
    body.innerHTML = lines.map((l, i) => `
      <tr data-source="${esc(l.source)}" data-source-ref="${esc(l.source_ref)}">
        <td><input data-f="cost_code" value="${esc(l.cost_code)}"></td>
        ${specSectionCellHtml(l.spec_section)}
        <td><input data-f="description" value="${esc(l.description)}"></td>
        <td><select data-f="cost_type"><option ${l.cost_type === 'Subcontract' ? 'selected' : ''}>Subcontract</option><option ${l.cost_type === 'Material' ? 'selected' : ''}>Material</option><option ${l.cost_type === 'Labor' ? 'selected' : ''}>Labor</option><option ${l.cost_type === 'Equipment' ? 'selected' : ''}>Equipment</option><option ${l.cost_type === 'Other' ? 'selected' : ''}>Other</option></select></td>
        <td><input data-f="quantity" type="number" step="any" class="num" value="${l.quantity}"></td>
        <td><input data-f="unit" value="${esc(l.unit)}"></td>
        <td><input data-f="unit_cost" type="number" step="0.01" class="num" value="${l.unit_cost}"></td>
        <td class="num px-2 text-emerald-400 ext-cell">${fmt((l.quantity || 0) * (l.unit_cost || 0))}</td>
        <td class="px-2 text-xs text-zinc-500">${esc(l.source)}</td>
        <td><button type="button" class="text-red-400 px-2 del-line">×</button></td>
      </tr>`).join('');
    body.querySelectorAll('.del-line').forEach(btn => btn.addEventListener('click', e => {
      e.target.closest('tr')?.remove();
      recalcWsFooter();
    }));
    body.querySelectorAll('input[data-f="quantity"], input[data-f="unit_cost"]').forEach(inp => {
      inp.addEventListener('input', recalcWsFooter);
    });
    wireSpecSectionCells(body);
    recalcWsFooter();
  }

  function recalcWsFooter() {
    let total = 0;
    document.querySelectorAll('#estWorksheetBody tr').forEach(tr => {
      const qty = parseFloat(tr.querySelector('[data-f="quantity"]')?.value) || 0;
      const uc = parseFloat(tr.querySelector('[data-f="unit_cost"]')?.value) || 0;
      const ext = qty * uc;
      total += ext;
      const cell = tr.querySelector('.ext-cell');
      if (cell) cell.textContent = fmt(ext);
    });
    const el = document.getElementById('estWsDirect');
    if (el) el.textContent = fmt(total);
  }

  function renderPackages(est) {
    const el = document.getElementById('estPackagesList');
    if (!el) return;
    const pkgs = est.bid_packages || [];
    if (!pkgs.length) {
      el.innerHTML = '<p class="text-zinc-500 text-center py-8">No bid packages yet. Create one to send RFPs by spec section.</p>';
      return;
    }
    el.innerHTML = pkgs.map(p => {
      const invs = p.invitations || [];
      const invRows = invs.map(i => `
        <tr class="border-t border-zinc-800">
          <td class="py-2">${esc(i.company_name)}</td>
          <td class="py-2 text-xs">${esc(i.contact_email)}</td>
          <td class="py-2 text-center"><span class="text-xs">${esc(i.status)}</span></td>
          <td class="py-2 text-right font-mono">${i.quote_amount ? fmt(i.quote_amount) : '—'}</td>
          <td class="py-2 text-right">
            ${i.status === 'Quoted' ? `<button type="button" class="text-emerald-400 text-xs award-inv" data-pkg="${p.id}" data-inv="${i.id}">Award</button>` : ''}
          </td>
        </tr>`).join('');
      return `
        <div class="border border-zinc-700 rounded-lg bg-zinc-900 p-4">
          <div class="flex justify-between gap-3 flex-wrap">
            <div>
              <div class="font-mono text-sky-400">${esc(p.number)}</div>
              <div class="font-medium text-white">${esc(p.title)}</div>
              <div class="text-xs text-zinc-500 mt-1">Spec ${esc(p.spec_section || '—')} · Due ${p.due_date || '—'} · ${esc(p.status)}</div>
            </div>
            <div class="flex gap-2 flex-wrap">
              <button type="button" class="px-3 py-1.5 bg-zinc-700 rounded text-sm edit-pkg" data-id="${p.id}">Edit</button>
              <button type="button" class="px-3 py-1.5 bg-zinc-800 rounded text-sm mass-invite" data-id="${p.id}">Mass Invite Vendors</button>
              <button type="button" class="px-3 py-1.5 bg-emerald-700 rounded text-sm send-rfp" data-id="${p.id}">Send RFP Emails</button>
            </div>
          </div>
          ${p.description ? `<p class="text-sm text-zinc-300 mt-2">${esc(p.description)}</p>` : ''}
          ${p.scope_notes ? `<p class="text-sm text-zinc-400 mt-2">${esc(p.scope_notes)}</p>` : ''}
          <table class="w-full text-sm mt-3">
            <thead><tr class="text-zinc-500 text-xs"><th class="text-left">Vendor</th><th class="text-left">Email</th><th class="text-center">Status</th><th class="text-right">Quote</th><th></th></tr></thead>
            <tbody>${invRows || '<tr><td colspan="5" class="py-2 text-zinc-500">No invitations</td></tr>'}</tbody>
          </table>
        </div>`;
    }).join('');

    el.querySelectorAll('.mass-invite').forEach(btn => btn.addEventListener('click', () => massInvite(btn.dataset.id, true)));
    el.querySelectorAll('.send-rfp').forEach(btn => btn.addEventListener('click', () => massInvite(btn.dataset.id, false)));
    el.querySelectorAll('.edit-pkg').forEach(btn => btn.addEventListener('click', () => openPackageModal(parseInt(btn.dataset.id, 10))));
    el.querySelectorAll('.award-inv').forEach(btn => btn.addEventListener('click', async () => {
      try {
        await api(`/api/estimates/bid-packages/${btn.dataset.pkg}/award`, {
          method: 'POST',
          body: JSON.stringify({ invitation_id: parseInt(btn.dataset.inv, 10) }),
        });
        await loadCurrent();
        await estAlert('Vendor awarded for this package.', 'success');
      } catch (e) { estAlert(e.message, 'error'); }
    }));
  }

  async function massInvite(packageId, autoMatch) {
    try {
      const json = await api(`/api/estimates/bid-packages/${packageId}/mass-invite`, {
        method: 'POST',
        body: JSON.stringify({ auto_match: autoMatch, send_notifications: true }),
      });
      await loadCurrent();
      await estAlert(`Sent ${json.sent} invitation(s).`, 'success');
    } catch (e) { estAlert(e.message, 'error'); }
  }

  async function loadTakeoffPreview() {
    if (!state.current?.id) return;
    const q = document.getElementById('estTakeoffSearch')?.value || '';
    const url = `/api/estimates/${state.current.id}/takeoff-preview${q ? `?q=${encodeURIComponent(q)}` : ''}`;
    const json = await api(url);
    state.takeoffItems = json.items || [];
    const body = document.getElementById('estTakeoffBody');
    if (!body) return;
    if (!state.takeoffItems.length) {
      body.innerHTML = '<tr><td colspan="4" class="px-4 py-8 text-center text-zinc-500">No takeoff markups yet. Use the measure/area tools in the viewer above.</td></tr>';
      return;
    }
    body.innerHTML = state.takeoffItems.map(i => `
      <tr>
        <td class="px-3 py-2 font-mono text-sky-400">${esc(i.sheet_number)}</td>
        <td class="px-3 py-2">${esc(i.description)}</td>
        <td class="px-3 py-2 text-right font-mono">${i.quantity}</td>
        <td class="px-3 py-2">${esc(i.unit)}</td>
      </tr>`).join('');
  }

  async function renderLeveling() {
    if (!state.current?.id) return;
    const { matrix } = await api(`/api/estimates/${state.current.id}/leveling`);
    const grid = document.getElementById('estLevelingGrid');
    if (!grid) return;
    if (!matrix?.length) {
      grid.innerHTML = '<p class="text-zinc-500">No bid packages to level.</p>';
      return;
    }
    grid.innerHTML = matrix.map(row => {
      const pkg = row.package;
      const bids = row.bids || [];
      const bidCards = bids.length ? bids.map(b => `
        <div class="flex justify-between items-center py-2 border-t border-zinc-800 ${b.is_low ? 'level-low rounded px-2' : ''}">
          <div><div class="font-medium">${esc(b.company_name)}</div><div class="text-xs text-zinc-500">${esc(b.status)}</div></div>
          <div class="font-mono ${b.is_low ? 'text-emerald-400' : ''}">${fmt(b.quote_amount)}</div>
        </div>`).join('') : '<p class="text-zinc-500 text-sm py-2">No quotes yet</p>';
      return `<div class="level-card"><div class="font-mono text-sky-400">${esc(pkg.number)}</div><div class="font-medium">${esc(pkg.title)}</div><div class="text-xs text-zinc-500 mb-2">Spec ${esc(pkg.spec_section || '—')}</div>${bidCards}</div>`;
    }).join('');
  }

  function renderEstimateSelect() {
    const sel = document.getElementById('estEstimateSelect');
    if (!sel) return;
    sel.innerHTML = state.estimates.map(e => `<option value="${e.id}">${esc(e.number)} — ${esc(e.title)}</option>`).join('');
    if (state.current) sel.value = String(state.current.id);
  }

  async function loadEstimates() {
    const id = pid();
    if (!id) {
      await estAlert('Select a project first.', 'warning');
      return;
    }
    const json = await api(`/api/estimates?project_id=${id}`);
    state.estimates = json.estimates || [];
    await loadSpecBookSections();
    if (!state.estimates.length) {
      state.current = null;
      renderEstimateSelect();
      return;
    }
    const keep = state.current?.id;
    const detail = keep ? await api(`/api/estimates/${keep}`) : await api(`/api/estimates/${state.estimates[0].id}`);
    state.current = detail;
    renderEstimateSelect();
    renderAll();
  }

  async function loadCurrent() {
    if (!state.current?.id) return;
    state.current = await api(`/api/estimates/${state.current.id}`);
    const idx = state.estimates.findIndex(e => e.id === state.current.id);
    if (idx >= 0) state.estimates[idx] = state.current;
    renderAll();
  }

  function renderAll() {
    const est = state.current;
    if (!est) return;
    updateSummaryBar(est);
    fillSummaryForm(est);
    renderWorksheet(est);
    renderPackages(est);
  }

  async function createEstimate() {
    const id = pid();
    if (!id) return estAlert('Select a project first.', 'warning');
    const modal = document.getElementById('estNewEstimateModal');
    document.getElementById('estNewTitle').value = 'Project Estimate';
    openDialog(modal);
  }

  async function submitNewEstimate(e) {
    e.preventDefault();
    const id = pid();
    if (!id) return;
    const title = document.getElementById('estNewTitle').value.trim();
    if (!title) return;
    const estimate_type = document.getElementById('estNewType').value;
    const json = await api('/api/estimates', {
      method: 'POST',
      body: JSON.stringify({ project_id: id, title, estimate_type }),
    });
    closeDialog(document.getElementById('estNewEstimateModal'));
    state.current = json.estimate;
    await loadEstimates();
    await estAlert(`Created ${json.estimate.number}`, 'success');
  }

  async function saveSummary() {
    if (!state.current?.id) return;
    const body = {
      title: document.getElementById('estTitle').value,
      description: document.getElementById('estDescription').value,
      estimate_type: document.getElementById('estType').value,
      status: document.getElementById('estStatus').value,
      bid_date: document.getElementById('estBidDate').value || null,
      due_date: document.getElementById('estDueDate').value || null,
      contingency_pct: parseFloat(document.getElementById('estContingency').value) || 0,
      overhead_pct: parseFloat(document.getElementById('estOverhead').value) || 0,
      profit_pct: parseFloat(document.getElementById('estProfit').value) || 0,
      tax_pct: parseFloat(document.getElementById('estTax').value) || 0,
    };
    await api(`/api/estimates/${state.current.id}`, { method: 'PUT', body: JSON.stringify(body) });
    await loadCurrent();
    await estAlert('Estimate saved.', 'success');
  }

  async function saveLines() {
    if (!state.current?.id) return;
    const lines = readWorksheetLines();
    await api(`/api/estimates/${state.current.id}`, { method: 'PUT', body: JSON.stringify({ lines }) });
    await loadCurrent();
    await estAlert('Worksheet saved.', 'success');
  }

  function addLine() {
    const body = document.getElementById('estWorksheetBody');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input data-f="cost_code" value="01-000"></td>
      ${specSectionCellHtml('')}
      <td><input data-f="description"></td>
      <td><select data-f="cost_type"><option>Subcontract</option><option>Material</option><option>Labor</option><option>Equipment</option><option>Other</option></select></td>
      <td><input data-f="quantity" type="number" step="any" class="num" value="1"></td>
      <td><input data-f="unit" value="EA"></td>
      <td><input data-f="unit_cost" type="number" step="0.01" class="num" value="0"></td>
      <td class="num px-2 text-emerald-400 ext-cell">$0.00</td>
      <td class="px-2 text-xs text-zinc-500">manual</td>
      <td><button type="button" class="text-red-400 px-2 del-line">×</button></td>`;
    body.appendChild(tr);
    tr.querySelector('.del-line').addEventListener('click', () => { tr.remove(); recalcWsFooter(); });
    tr.querySelectorAll('input[data-f="quantity"], input[data-f="unit_cost"]').forEach(inp => inp.addEventListener('input', recalcWsFooter));
    wireSpecSectionCells(tr);
    recalcWsFooter();
  }

  async function openTakeoffImport() {
    if (!state.current?.id) return estAlert('Select or create an estimate first.', 'warning');
    const countEl = document.getElementById('estTakeoffCount');
    try {
      const json = await api(`/api/estimates/${state.current.id}/takeoff-preview`);
      const n = json.count || 0;
      if (countEl) countEl.textContent = n ? `${n} takeoff item(s) available to import.` : 'No takeoff markups found on drawings.';
      if (!n) return estAlert('No takeoff measurements found. Add measure/area markups in the takeoff viewer first.', 'warning');
    } catch (e) {
      if (countEl) countEl.textContent = '';
    }
    openDialog(document.getElementById('estTakeoffModal'));
  }

  async function submitTakeoffImport(e) {
    e.preventDefault();
    if (!state.current?.id) return;
    const costCode = document.getElementById('estTakeoffCostCode').value.trim() || '01-000';
    const json = await api(`/api/estimates/${state.current.id}/import-takeoff`, {
      method: 'POST',
      body: JSON.stringify({ cost_code: costCode }),
    });
    closeDialog(document.getElementById('estTakeoffModal'));
    await loadCurrent();
    await estAlert(`Imported ${json.imported} takeoff line(s).`, 'success');
    setTab('worksheet');
  }

  async function awardToBudget() {
    if (!state.current?.id) return;
    const ok = await estConfirm(
      'Push this estimate to the project budget as original budget lines? Existing matching cost codes will be increased.',
      { title: 'Award to Budget', confirmLabel: 'Push to Budget' },
    );
    if (!ok) return;
    const useBids = document.getElementById('estUseBidAwards')?.checked;
    const json = await api(`/api/estimates/${state.current.id}/award-to-budget`, {
      method: 'POST',
      body: JSON.stringify({ use_bid_awards: useBids }),
    });
    const r = json.result || {};
    const el = document.getElementById('estAwardResult');
    if (el) {
      el.classList.remove('hidden');
      el.textContent = `Pushed ${r.lines_pushed || 0} line(s) to budget (${r.created || 0} new, ${r.updated || 0} updated).`;
    }
    await loadCurrent();
    if (global.CasePMBudgetSync?.reload) global.CasePMBudgetSync.reload();
  }

  async function initPackageModalCsi() {
    if (!global.CasePMCsiCatalog) return;
    const divSel = document.getElementById('estPkgDivision');
    const specSel = document.getElementById('estPkgSpecSection');
    await CasePMCsiCatalog.fillDivisionSelect(divSel);
    await CasePMCsiCatalog.fillSpecSelect(specSel, divSel?.value);
    if (!divSel.dataset.wired) {
      CasePMCsiCatalog.wireDivisionSpecPair(divSel, specSel, () => {
        const spec = specSel.value;
        const title = document.querySelector('#estPackageForm [name="title"]');
        if (title && spec && !title.value.trim()) {
          const opt = specSel.selectedOptions[0];
          if (opt) title.value = opt.textContent.split('—').slice(1).join('—').trim() || spec;
        }
      });
      divSel.dataset.wired = '1';
    }
  }

  async function openPackageModal(packageId) {
    const form = document.getElementById('estPackageForm');
    const modal = document.getElementById('estPackageModal');
    if (!form || !modal) return;
    form.reset();
    document.getElementById('estPackageId').value = '';
    document.getElementById('estPackageModalTitle').textContent = 'New Bid Package / RFP';
    document.getElementById('estPackageSubmitBtn').textContent = 'Create Package';
    if (packageId) {
      const pkg = (state.current?.bid_packages || []).find(p => p.id === packageId);
      if (pkg) {
        document.getElementById('estPackageId').value = String(pkg.id);
        document.getElementById('estPackageModalTitle').textContent = 'Edit Bid Package / RFP';
        document.getElementById('estPackageSubmitBtn').textContent = 'Save Package';
        form.title.value = pkg.title || '';
        form.description.value = pkg.description || '';
        form.scope_notes.value = pkg.scope_notes || '';
        form.due_date.value = pkg.due_date || '';
      }
    }
    await initPackageModalCsi();
    const pkg = packageId ? (state.current?.bid_packages || []).find(p => p.id === packageId) : null;
    if (pkg) {
      const divSel = document.getElementById('estPkgDivision');
      const specSel = document.getElementById('estPkgSpecSection');
      if (pkg.division) divSel.value = String(pkg.division).padStart(2, '0').slice(0, 2);
      await CasePMCsiCatalog.fillSpecSelect(specSel, divSel.value, pkg.spec_section);
    }
    openDialog(modal);
  }

  function bindModalClosers() {
    document.querySelectorAll('.estModalClose').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-target');
        closeDialog(document.getElementById(id));
      });
    });
    const pkgCancel = document.getElementById('estPackageCancel');
    const pkgCancelBtn = document.querySelector('.estPackageCancelBtn');
    const closePkg = () => closeDialog(document.getElementById('estPackageModal'));
    pkgCancel?.addEventListener('click', closePkg);
    pkgCancelBtn?.addEventListener('click', closePkg);
  }

  function bindEvents() {
    bindModalClosers();
    document.querySelectorAll('#estTabBar button').forEach(btn => {
      btn.addEventListener('click', () => setTab(btn.dataset.tab));
    });
    document.getElementById('estNewBtn')?.addEventListener('click', () => createEstimate().catch(e => estAlert(e.message, 'error')));
    document.getElementById('estNewEstimateForm')?.addEventListener('submit', e => submitNewEstimate(e).catch(err => estAlert(err.message, 'error')));
    document.getElementById('estEstimateSelect')?.addEventListener('change', async e => {
      state.current = { id: parseInt(e.target.value, 10) };
      await loadCurrent();
    });
    document.getElementById('estSaveSummary')?.addEventListener('click', () => saveSummary().catch(e => estAlert(e.message, 'error')));
    document.getElementById('estAddLine')?.addEventListener('click', addLine);
    document.getElementById('estSaveLines')?.addEventListener('click', () => saveLines().catch(e => estAlert(e.message, 'error')));
    document.getElementById('estLineSearch')?.addEventListener('input', () => renderWorksheet(state.current || { lines: [] }));
    document.getElementById('estNewPackage')?.addEventListener('click', () => openPackageModal().catch(e => estAlert(e.message, 'error')));
    document.getElementById('estPackageForm')?.addEventListener('submit', async e => {
      e.preventDefault();
      if (!state.current?.id) return;
      const fd = new FormData(e.target);
      const body = Object.fromEntries(fd.entries());
      const pkgId = body.package_id;
      delete body.package_id;
      if (pkgId) {
        await api(`/api/estimates/bid-packages/${pkgId}`, { method: 'PUT', body: JSON.stringify(body) });
        await estAlert('Bid package updated.', 'success');
      } else {
        await api(`/api/estimates/${state.current.id}/bid-packages`, { method: 'POST', body: JSON.stringify(body) });
        await estAlert('Bid package created.', 'success');
      }
      closeDialog(document.getElementById('estPackageModal'));
      e.target.reset();
      await loadCurrent();
      setTab('rfp');
    });
    document.getElementById('estRefreshTakeoff')?.addEventListener('click', () => loadTakeoffPreview().catch(e => estAlert(e.message, 'error')));
    document.getElementById('estTakeoffSearch')?.addEventListener('input', () => loadTakeoffPreview().catch(() => {}));
    document.getElementById('estImportTakeoff')?.addEventListener('click', () => openTakeoffImport().catch(e => estAlert(e.message, 'error')));
    document.getElementById('estTakeoffForm')?.addEventListener('submit', e => submitTakeoffImport(e).catch(err => estAlert(err.message, 'error')));
    document.getElementById('estRefreshLeveling')?.addEventListener('click', () => renderLeveling().catch(e => estAlert(e.message, 'error')));
    document.getElementById('estAwardBudget')?.addEventListener('click', () => awardToBudget().catch(e => estAlert(e.message, 'error')));

    const tab = new URLSearchParams(location.search).get('tab');
    if (tab) setTab(tab);
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (global.CasePMDialog?.initAllDialogs) global.CasePMDialog.initAllDialogs();
    bindEvents();
    loadEstimates().catch(e => estAlert(e.message, 'error'));
  });

  global.CasePMEstimating = { loadEstimates, setTab, state, loadCurrent, renderWorksheet, renderAll, openPackageModal, loadSpecBookSections, wireSpecSectionCells };
})(window);
