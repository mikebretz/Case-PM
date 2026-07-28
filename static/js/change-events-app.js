/**
 * Change Events, RFQs, CORs, CPCOs, ERP queue — extends CasePMChangeOrders
 */
(function (global) {
  'use strict';
  const CO = global.CasePMChangeOrders;
  if (!CO) return;

  const ext = {
    changeEvents: [],
    rfqs: [],
    cors: [],
    cpcos: [],
    erpEvents: [],
    billingVariances: [],
    subSovLines: [],
    ownerPcos: [],
    ceLineSelection: new Set(),
    ceVendorFilter: '',
    activeChangeEventId: null,
  };

  function pid() {
    if (global.CasePMChangeOrders && global.CasePMChangeOrders.projectId) return global.CasePMChangeOrders.projectId();
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  function fmt(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function cePrompt(message, defaultValue = '', options = {}) {
    if (global.CasePMDialog?.prompt) return global.CasePMDialog.prompt(message, defaultValue, options);
    return prompt(message, defaultValue);
  }

  async function ceConfirm(message, options = {}) {
    if (global.CasePMDialog?.confirm) return global.CasePMDialog.confirm(message, options);
    return confirm(message);
  }

  function statusBadge(status) {
    if (CO.statusBadge) return CO.statusBadge(status);
    return `<span class="text-xs">${esc(status)}</span>`;
  }

  function reviewButtonHtml(onclick, label) {
    const text = label || 'Review & Respond';
    return `<button type="button" onclick="${onclick}" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-semibold whitespace-nowrap shadow-md"><i class="fa-solid fa-clipboard-check mr-1"></i>${text}</button>`;
  }

  function canActOnBall(role) {
    if (!role) return false;
    if (typeof CO.canActOnBall === 'function') return CO.canActOnBall(role);
    return true;
  }

  function formatCorRollupHtml(c) {
    const rollup = c?.rollup_allocations || [];
    const linked = c?.linked_pcos || [];
    if (!linked.length && !rollup.length) {
      return '<div class="text-xs text-zinc-500 mt-2">No owner PCOs packaged. Line-item detail belongs on PCOs, not the COR.</div>';
    }
    const pcoList = linked.map(p => `<span class="inline-block mr-2 text-amber-400 font-mono text-xs">${esc(p.number)}</span>`).join('') || '—';
    const rows = rollup.map(a => `
      <tr class="border-b border-zinc-800">
        <td class="py-1 font-mono text-[10px] text-amber-400">${esc(a.pco_number || '')}</td>
        <td class="py-1 font-mono text-xs">${esc(a.cost_code)}</td>
        <td class="py-1 text-xs text-zinc-400">${esc(a.cost_type || '')}</td>
        <td class="py-1 text-xs">${esc(a.description || '')}</td>
        <td class="py-1 text-right font-mono">${fmt(a.amount)}</td>
      </tr>`).join('');
    return `
      <div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Packaged PCOs</div><div>${pcoList}</div></div>
      <div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">SOV rollup (from PCOs)</div>
        <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">PCO</th><th class="text-left">Code</th><th class="text-left">Type</th><th class="text-left">Description</th><th class="text-right">Amount</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="py-2 text-zinc-500">No SOV lines on linked PCOs yet.</td></tr>'}</tbody></table>
      </div>`;
  }

  async function loadOwnerPcos() {
    const id = pid();
    if (!id) return;
    const json = await api(`/api/pcos?project_id=${id}&scope=owner`);
    ext.ownerPcos = (json.pcos || []).filter(p => !p.linked_cor_id && p.status !== 'Promoted');
  }

  function renderCorPcoPicker(selectedIds) {
    const box = document.getElementById('ceModalCorPcos');
    if (!box) return;
    const selected = new Set((selectedIds || []).map(Number));
    if (!ext.ownerPcos?.length) {
      box.innerHTML = '<div class="text-xs text-zinc-500">No draft owner PCOs available. Create PCOs with SOV lines first, then package them in a COR.</div>';
      return;
    }
    box.innerHTML = ext.ownerPcos.map(p => `
      <label class="flex items-center gap-2 py-1 cursor-pointer hover:bg-zinc-700/40 rounded px-1">
        <input type="checkbox" value="${p.id}" ${selected.has(p.id) ? 'checked' : ''}>
        <span class="font-mono text-amber-400 text-xs">${esc(p.number)}</span>
        <span class="flex-1 truncate">${esc(p.title || '')}</span>
        <span class="font-mono text-xs text-zinc-400">${fmt(p.estimated_amount)}</span>
      </label>`).join('');
  }

  function openCorReviewModal(id) {
    if (CO.closeDrawer) CO.closeDrawer();
    const c = ext.cors.find(x => x.id === id);
    if (!c || typeof global.CasePMApprovalResponder === 'undefined') {
      corWorkflow(id, 'approve', c?.status === 'Pending Accounting');
      return;
    }
    const promotePco = c.status === 'Pending Accounting';
    const hasLinkedPcos = (c.linked_pcos || []).length > 0;
    global.CasePMApprovalResponder.openLocal({
      module: 'COR',
      entityId: id,
      title: `${c.number} — ${c.title || 'Change Order Request'}`,
      status: c.status,
      ball: c.ball_in_court_role,
      summaryHtml: `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Package total</span><span class="font-mono text-emerald-400">${fmt(c.amount)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Drawing</span><span>${esc(c.drawing_revision || '—')}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Schedule impact</span><span>${c.schedule_impact_days || 0} days</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Status</span><span>${statusBadge(c.status)}</span></div>
        ${c.description ? `<div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Description</div><p class="text-sm whitespace-pre-wrap">${esc(c.description)}</p></div>` : ''}
        ${formatCorRollupHtml(c)}`,
      actions: [
        { action: 'approve', label: promotePco ? (hasLinkedPcos ? 'Approve package' : 'Approve → PCO') : 'Approve Step', style: 'primary' },
        { action: 'reject', label: 'Reject', requires_comment: true, style: 'danger' },
      ],
      onSubmit: async (action, comment) => {
        await api(`/api/cors/${id}/workflow`, {
          method: 'POST',
          body: JSON.stringify({ action, promote_pco: promotePco && action === 'approve', comments: comment }),
        });
        await Promise.all([loadCors(), CO.loadPcos ? CO.loadPcos() : null]);
        if (promotePco && action === 'approve' && CO.switchTab) CO.switchTab('pcos');
      },
    });
  }

  async function openCeReviewModal(id) {
    if (CO.closeDrawer) CO.closeDrawer();
    let e = ext.changeEvents.find(x => x.id === id);
    if (!e) {
      try { e = await api(`/api/change-events/${id}`); } catch { return; }
    }
    if (!e || typeof global.CasePMApprovalResponder === 'undefined') {
      ceWorkflow(id, 'approve');
      return;
    }
    global.CasePMApprovalResponder.openLocal({
      module: 'Change Events',
      entityId: id,
      title: `${e.number} — ${e.title || 'Change Event'}`,
      status: e.status,
      summaryHtml: `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">ROM</span><span class="font-mono text-emerald-400">${fmt(e.rom_amount)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Schedule impact</span><span>${e.schedule_impact_days || 0} days</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Drawing</span><span>${esc(e.drawing_revision || '—')}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Status</span><span>${statusBadge(e.status)}</span></div>
        ${e.description ? `<div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Description</div><p class="text-sm whitespace-pre-wrap">${esc(e.description)}</p></div>` : ''}`,
      actions: [
        { action: 'approve', label: 'Advance Workflow', style: 'primary' },
        { action: 'reject', label: 'Void Event', requires_comment: true, style: 'danger' },
      ],
      onSubmit: async (action, comment) => {
        const json = await api(`/api/change-events/${id}/workflow`, {
          method: 'POST',
          body: JSON.stringify({ action, comments: comment }),
        });
        if (json.final && typeof global.CasePMBudgetSync !== 'undefined') {
          await global.CasePMBudgetSync.loadFromServer().catch(() => {});
        }
        await loadChangeEvents();
        if (action === 'reject') CO.closeDrawer();
        else await viewChangeEvent(id);
      },
    });
  }

  function openErpReviewModal(id) {
    if (CO.closeDrawer) CO.closeDrawer();
    const ev = ext.erpEvents.find(x => x.id === id);
    if (!ev || typeof global.CasePMApprovalResponder === 'undefined') {
      erpReview(id, 'accept');
      return;
    }
    global.CasePMApprovalResponder.openLocal({
      module: 'ERP / Sage',
      entityId: id,
      title: `${ev.event_type || 'ERP Event'} — Accounting Review`,
      status: ev.accounting_status || ev.status,
      summaryHtml: `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Event</span><span class="font-mono text-xs">${esc(ev.event_type)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Created</span><span class="text-xs">${ev.created_at ? new Date(ev.created_at).toLocaleString() : '—'}</span></div>
        <div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Message</div><p class="text-sm whitespace-pre-wrap">${esc(ev.message || '—')}</p></div>`,
      actions: [
        { action: 'approve', label: 'Accept & Post', style: 'primary' },
        { action: 'reject', label: 'Reject', requires_comment: true, style: 'danger' },
      ],
      onSubmit: async (action, comment) => {
        await api(`/api/sage/sync-events/${id}/accounting`, {
          method: 'POST',
          body: JSON.stringify({ action: action === 'approve' ? 'accept' : 'reject', notes: comment }),
        });
        await loadErpQueue();
      },
    });
  }

  async function loadCommitments() {
    const id = pid();
    if (!id) return;
    try {
      const json = await api(`/api/commitments?project_id=${id}`);
      ext.commitments = (json.commitments || []).filter(c => (c.commitment_type || '').toLowerCase() === 'subcontract');
    } catch {
      ext.commitments = [];
    }
  }

  function ceLineKey(line) {
    return String(line.id != null ? line.id : line._tmp);
  }

  function filteredCeLines(lines) {
    const vendor = (ext.ceVendorFilter || '').trim().toLowerCase();
    if (!vendor) return lines || [];
    return (lines || []).filter(l => (l.company_name || '').toLowerCase().includes(vendor) || (l.linked_commitment_ref || '').toLowerCase().includes(vendor));
  }

  function toggleCeLineSelection(lineKey, checked) {
    if (checked) ext.ceLineSelection.add(String(lineKey));
    else ext.ceLineSelection.delete(String(lineKey));
  }

  function toggleCeSelectAllLines(eventId, checked) {
    const e = ext._activeCeDetail;
    filteredCeLines(e?.line_items || []).forEach(l => {
      const key = ceLineKey(l);
      if (checked) ext.ceLineSelection.add(String(key));
      else ext.ceLineSelection.delete(String(key));
    });
    if (eventId) viewChangeEvent(eventId, { preserveSelection: true });
  }

  function addCeLineRow() {
    const tbody = document.getElementById('ceLineItemsBody');
    if (!tbody) return;
    const tmp = `tmp-${Date.now()}`;
    const opts = ext.commitments.map(c =>
      `<option value="${esc(c.number || '')}" data-company="${esc(c.company_name || '')}" data-company-id="${esc(c.company_id || '')}">${esc(c.number)} — ${esc(c.company_name || '')}</option>`
    ).join('');
    tbody.insertAdjacentHTML('beforeend', `
      <tr class="border-b border-zinc-800" data-line-key="${tmp}">
        <td class="py-2 px-1 text-center"><input type="checkbox" onchange="CasePMChangeOrdersExt.toggleCeLineSelection('${tmp}', this.checked)"></td>
        <td class="py-2 px-1"><input type="text" class="ce-line-cost w-20 bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs" placeholder="01-0000"></td>
        <td class="py-2 px-1"><input type="text" class="ce-line-desc w-full min-w-[8rem] bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs" placeholder="Description"></td>
        <td class="py-2 px-1"><select class="ce-line-commitment bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs min-w-[7rem]"><option value="">—</option>${opts}</select></td>
        <td class="py-2 px-1"><input type="text" class="ce-line-vendor w-full min-w-[6rem] bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs" placeholder="Vendor"></td>
        <td class="py-2 px-1 text-right"><input type="number" step="0.01" class="ce-line-amount w-24 bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs text-right" value="0"></td>
        <td class="py-2 px-1 text-xs text-zinc-500 ce-line-status">Open</td>
      </tr>`);
    tbody.querySelectorAll('.ce-line-commitment').forEach(sel => {
      if (sel.dataset.bound) return;
      sel.dataset.bound = '1';
      sel.addEventListener('change', () => {
        const opt = sel.selectedOptions[0];
        const row = sel.closest('tr');
        const vendor = row?.querySelector('.ce-line-vendor');
        if (vendor && opt?.dataset.company) vendor.value = opt.dataset.company;
      });
    });
  }

  function collectCeLineItemsFromDom() {
    const rows = [...document.querySelectorAll('#ceLineItemsBody tr[data-line-key]')];
    return rows.map((row, idx) => {
      const key = row.dataset.lineKey || '';
      const commitmentSel = row.querySelector('.ce-line-commitment');
      const opt = commitmentSel?.selectedOptions?.[0];
      return {
        id: key.startsWith('tmp-') ? null : parseInt(key, 10),
        sort_order: idx,
        cost_code: row.querySelector('.ce-line-cost')?.value?.trim() || '',
        description: row.querySelector('.ce-line-desc')?.value?.trim() || '',
        linked_commitment_ref: commitmentSel?.value?.trim() || '',
        company_name: row.querySelector('.ce-line-vendor')?.value?.trim() || opt?.dataset?.company || '',
        company_id: opt?.dataset?.companyId || '',
        amount: parseFloat(row.querySelector('.ce-line-amount')?.value) || 0,
        cost_type: 'Subcontract',
        status: row.querySelector('.ce-line-status')?.textContent?.trim() || 'Open',
        linked_rfq_id: row.dataset.linkedRfq ? parseInt(row.dataset.linkedRfq, 10) || null : null,
        linked_cpco_id: row.dataset.linkedCpco ? parseInt(row.dataset.linkedCpco, 10) || null : null,
        linked_sco_id: row.dataset.linkedSco ? parseInt(row.dataset.linkedSco, 10) || null : null,
      };
    });
  }

  async function saveCeLineItems(eventId) {
    const lines = collectCeLineItemsFromDom();
    const json = await api(`/api/change-events/${eventId}/line-items`, {
      method: 'PUT',
      body: JSON.stringify({ line_items: lines }),
    });
    ext.ceLineSelection.clear();
    await loadChangeEvents();
    await viewChangeEvent(eventId);
    return json;
  }

  async function bulkCreateFromCe(eventId, action) {
    const selected = [...ext.ceLineSelection].map(k => parseInt(k, 10)).filter(n => !Number.isNaN(n));
    if (!selected.length) {
      alert('Select at least one saved line item (save lines first if you just added new rows).');
      return;
    }
    const routes = {
      rfqs: '/bulk-create-rfqs',
      ccos: '/bulk-create-commitment-cos',
      cpcos: '/bulk-create-cpcos',
    };
    const path = routes[action];
    if (!path) return;
    const labels = { rfqs: 'draft RFQ(s)', ccos: 'draft commitment change order(s)', cpcos: 'draft CPCO(s)' };
    if (!(await ceConfirm(`Create ${labels[action]} grouped by vendor and commitment?`, { title: 'Bulk create' }))) return;
    const json = await api(`/api/change-events/${eventId}${path}`, {
      method: 'POST',
      body: JSON.stringify({ line_item_ids: selected }),
    });
    ext.ceLineSelection.clear();
    await Promise.all([loadChangeEvents(), loadRfqs(), loadCpcos(), CO.loadChangeOrders ? CO.loadChangeOrders() : null]);
    await viewChangeEvent(eventId);
    if (action === 'ccos' && CO.switchTab) CO.switchTab('subs');
    if (action === 'cpcos' && CO.switchTab) CO.switchTab('cpcos');
    if (action === 'rfqs' && CO.switchTab) CO.switchTab('rfqs');
    alert(`Created ${json.count || 0} ${labels[action]}.`);
  }

  function renderCeLineItemsTable(e) {
    const lines = filteredCeLines(e.line_items || []);
    const allKeys = lines.map(ceLineKey);
    const allSelected = allKeys.length > 0 && allKeys.every(k => ext.ceLineSelection.has(String(k)));
    const commitmentOpts = ext.commitments.map(c =>
      `<option value="${esc(c.number || '')}" data-company="${esc(c.company_name || '')}" data-company-id="${esc(c.company_id || '')}">${esc(c.number)} — ${esc(c.company_name || '')}</option>`
    ).join('');
    const rows = lines.map(line => {
      const key = ceLineKey(line);
      const selected = ext.ceLineSelection.has(String(key));
      const commitOpts = `<option value="">—</option>` + ext.commitments.map(c => {
        const val = c.number || '';
        const sel = val === (line.linked_commitment_ref || '') ? ' selected' : '';
        return `<option value="${esc(val)}" data-company="${esc(c.company_name || '')}" data-company-id="${esc(c.company_id || '')}"${sel}>${esc(c.number)} — ${esc(c.company_name || '')}</option>`;
      }).join('');
      return `
        <tr class="border-b border-zinc-800" data-line-key="${key}" data-linked-rfq="${line.linked_rfq_id || ''}" data-linked-cpco="${line.linked_cpco_id || ''}" data-linked-sco="${line.linked_sco_id || ''}">
          <td class="py-2 px-1 text-center"><input type="checkbox" ${selected ? 'checked' : ''} onchange="CasePMChangeOrdersExt.toggleCeLineSelection('${key}', this.checked)"></td>
          <td class="py-2 px-1"><input type="text" class="ce-line-cost w-20 bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs" value="${esc(line.cost_code || '')}"></td>
          <td class="py-2 px-1"><input type="text" class="ce-line-desc w-full min-w-[8rem] bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs" value="${esc(line.description || '')}"></td>
          <td class="py-2 px-1"><select class="ce-line-commitment bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs min-w-[7rem]">${commitOpts}</select></td>
          <td class="py-2 px-1"><input type="text" class="ce-line-vendor w-full min-w-[6rem] bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs" value="${esc(line.company_name || '')}"></td>
          <td class="py-2 px-1 text-right"><input type="number" step="0.01" class="ce-line-amount w-24 bg-zinc-900 border border-zinc-700 rounded px-1 py-1 text-xs text-right" value="${line.amount || 0}"></td>
          <td class="py-2 px-1 text-xs text-zinc-500 ce-line-status">${esc(line.status || 'Open')}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="7" class="py-4 text-center text-zinc-500 text-xs">No line items — add vendor/commitment lines for each subcontractor impacted.</td></tr>';

    return `
      <div class="mt-6">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-2">
          <div class="text-xs text-zinc-500 uppercase">Line items (vendor / commitment)</div>
          <div class="flex flex-wrap gap-2 items-center">
            <input type="text" placeholder="Filter vendor…" class="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs"
                   value="${esc(ext.ceVendorFilter)}"
                   onchange="CasePMChangeOrdersExt.setCeVendorFilter(this.value)">
            <button type="button" onclick="CasePMChangeOrdersExt.addCeLineRow()" class="px-2 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded">+ Line</button>
            <button type="button" onclick="CasePMChangeOrdersExt.saveCeLineItems(${e.id})" class="px-2 py-1 text-xs bg-violet-700 hover:bg-violet-600 rounded">Save lines</button>
          </div>
        </div>
        <p class="text-[10px] text-zinc-500 mb-2">Procore-style: one change event, multiple lines per vendor/commitment. Select lines, then bulk-create separate draft RFQs, CPCOs, or commitment COs (one per subcontractor commitment).</p>
        <div class="flex flex-wrap gap-2 mb-2">
          <button type="button" onclick="CasePMChangeOrdersExt.bulkCreateFromCe(${e.id}, 'rfqs')" class="px-2 py-1 text-xs bg-sky-800 hover:bg-sky-700 rounded">Add To → RFQs</button>
          <button type="button" onclick="CasePMChangeOrdersExt.bulkCreateFromCe(${e.id}, 'cpcos')" class="px-2 py-1 text-xs bg-amber-800 hover:bg-amber-700 rounded">Add To → CPCOs</button>
          <button type="button" onclick="CasePMChangeOrdersExt.bulkCreateFromCe(${e.id}, 'ccos')" class="px-2 py-1 text-xs bg-emerald-800 hover:bg-emerald-700 rounded">Add To → Draft CCOs</button>
        </div>
        <div class="overflow-x-auto border border-zinc-800 rounded-lg">
          <table class="w-full text-xs min-w-[44rem]">
            <thead class="bg-zinc-900/80 text-zinc-500">
              <tr>
                <th class="py-2 px-1 w-8 text-center"><input type="checkbox" ${allSelected ? 'checked' : ''} onchange="CasePMChangeOrdersExt.toggleCeSelectAllLines(${e.id}, this.checked)"></th>
                <th class="text-left py-2 px-1">Cost code</th>
                <th class="text-left py-2 px-1">Description</th>
                <th class="text-left py-2 px-1">Commitment</th>
                <th class="text-left py-2 px-1">Vendor</th>
                <th class="text-right py-2 px-1">ROM</th>
                <th class="text-left py-2 px-1">Status</th>
              </tr>
            </thead>
            <tbody id="ceLineItemsBody">${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  function setCeVendorFilter(value) {
    ext.ceVendorFilter = value || '';
    if (ext.activeChangeEventId) viewChangeEvent(ext.activeChangeEventId);
  }

  async function loadChangeEvents() {
    const id = pid();
    if (!id) return;
    const json = await api(`/api/change-events?project_id=${id}`);
    ext.changeEvents = json.change_events || [];
    renderChangeEventsTable();
  }

  async function loadRfqs() {
    const id = pid();
    if (!id) return;
    const json = await api(`/api/rfqs?project_id=${id}`);
    ext.rfqs = json.rfqs || [];
    renderRfqsTable();
  }

  async function loadCors() {
    const id = pid();
    if (!id) return;
    const json = await api(`/api/cors?project_id=${id}`);
    ext.cors = json.cors || [];
    renderCorsTable();
  }

  async function loadCpcos() {
    const id = pid();
    if (!id) return;
    const json = await api(`/api/pcos?project_id=${id}&scope=cpco`);
    ext.cpcos = json.pcos || [];
    renderCpcosTable();
  }

  async function loadErpQueue() {
    const id = pid();
    if (!id) return;
    const json = await api(`/api/sage/sync-events?project_id=${id}&limit=100`);
    ext.erpEvents = (json.events || []).filter(e =>
      ['pending_review', 'accepted', 'rejected'].includes(e.accounting_status) ||
      ['ChangeOrderApproved', 'CommitmentChangeOrderApproved', 'CORApproved', 'CPCOPromoted', 'RFQQuoted'].includes(e.event_type)
    );
    renderErpTable();
  }

  async function loadBillingVariance() {
    const id = pid();
    if (!id) return;
    try {
      const json = await api(`/api/change-orders/billing-variance?project_id=${id}`);
      ext.billingVariances = json.variances || [];
    } catch { ext.billingVariances = []; }
  }

  function renderChangeEventsTable() {
    const tbody = document.getElementById('ceEventsTableBody');
    if (!tbody) return;
    if (!ext.changeEvents.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="px-6 py-10 text-center text-zinc-500">No change events yet.</td></tr>';
      return;
    }
    tbody.innerHTML = ext.changeEvents.map(e => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50">
        <td class="px-4 py-3 font-mono text-violet-400">${esc(e.number)}</td>
        <td class="px-4 py-3">${esc(e.title)}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(e.rom_amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(e.status)}</td>
        <td class="px-4 py-3 text-xs">${e.schedule_impact_days || 0}d</td>
        <td class="px-4 py-3 text-xs">${esc(e.drawing_revision || '—')}</td>
        <td class="px-4 py-3 text-right font-mono text-amber-400">${e.contingency_release_amount ? fmt(e.contingency_release_amount) : '—'}</td>
        <td class="px-4 py-3 text-center">
          <button type="button" onclick="CasePMChangeOrdersExt.viewChangeEvent(${e.id})" class="text-sky-400 text-xs hover:underline">View</button>
        </td>
      </tr>`).join('');
  }

  function renderRfqsTable() {
    const tbody = document.getElementById('ceRfqsTableBody');
    if (!tbody) return;
    if (!ext.rfqs.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="px-6 py-10 text-center text-zinc-500">No RFQs yet. Send pricing requests to subcontractors before creating CPCOs.</td></tr>';
      return;
    }
    tbody.innerHTML = ext.rfqs.map(r => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50">
        <td class="px-4 py-3 font-mono text-sky-400">${esc(r.number)}</td>
        <td class="px-4 py-3">${esc(r.company_name || '—')}</td>
        <td class="px-4 py-3 font-mono text-xs">${esc(r.linked_commitment_ref || '—')}</td>
        <td class="px-4 py-3 text-center">${statusBadge(r.status)}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(r.quoted_amount)}</td>
        <td class="px-4 py-3 text-xs">${r.due_date ? new Date(r.due_date).toLocaleDateString() : '—'}</td>
        <td class="px-4 py-3 text-center text-[10px]">${esc(r.ball_in_court_role || '—')}</td>
        <td class="px-4 py-3 text-center flex gap-1 justify-center flex-wrap">
          ${r.status === 'Draft' ? `<button onclick="CasePMChangeOrdersExt.rfqWorkflow(${r.id},'send')" class="text-amber-400 text-xs">Send</button>` : ''}
          ${r.status === 'Sent' ? `<button onclick="CasePMChangeOrdersExt.openRfqQuote(${r.id})" class="text-emerald-400 text-xs">Quote</button><button onclick="CasePMChangeOrdersExt.portalRfqQuote(${r.id})" class="text-sky-400 text-xs">Portal</button>` : ''}
          ${r.status === 'Quoted' ? `<button onclick="CasePMChangeOrdersExt.rfqWorkflow(${r.id},'accept',true)" class="text-emerald-400 text-xs">Accept→CPCO</button>` : ''}
        </td>
      </tr>`).join('');
  }

  function renderCorsTable() {
    const tbody = document.getElementById('ceCorsTableBody');
    if (!tbody) return;
    if (!ext.cors.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="px-6 py-10 text-center text-zinc-500">No CORs yet.</td></tr>';
      return;
    }
    tbody.innerHTML = ext.cors.map(c => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50">
        <td class="px-4 py-3 font-mono text-indigo-400">${esc(c.number)}</td>
        <td class="px-4 py-3">${esc(c.title)}</td>
        <td class="px-4 py-3 text-xs">${(c.linked_pcos || []).length ? `${(c.linked_pcos || []).length} PCO(s)` : '—'}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(c.amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(c.status)}</td>
        <td class="px-4 py-3 text-xs">${esc(c.drawing_revision || '—')}</td>
        <td class="px-4 py-3 text-center text-[10px]">${esc(c.ball_in_court_role || '—')}</td>
        <td class="px-4 py-3 text-center flex gap-1 justify-center flex-wrap">
          ${c.status === 'Draft' ? `<button onclick="CasePMChangeOrdersExt.corWorkflow(${c.id},'submit')" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 rounded-md text-xs font-medium">Submit</button>` : ''}
          ${['Submitted', 'Under Review', 'Pending Owner', 'Pending Accounting'].includes(c.status) && canActOnBall(c.ball_in_court_role) ? reviewButtonHtml(`event.stopPropagation(); CasePMChangeOrdersExt.openCorReviewModal(${c.id})`, c.status === 'Pending Accounting' ? 'Review → PCO' : 'Review COR') : ''}
        </td>
      </tr>`).join('');
  }

  function renderCpcosTable() {
    const tbody = document.getElementById('ceCpcosTableBody');
    if (!tbody) return;
    if (!ext.cpcos.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-10 text-center text-zinc-500">No commitment PCOs (CPCOs) yet.</td></tr>';
      return;
    }
    tbody.innerHTML = ext.cpcos.map(p => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50">
        <td class="px-4 py-3 font-mono text-amber-400">${esc(p.number)}</td>
        <td class="px-4 py-3">${esc(p.title)}</td>
        <td class="px-4 py-3 text-xs">${esc(p.company_name || '—')}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(p.estimated_amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(p.status)}</td>
        <td class="px-4 py-3 font-mono text-xs">${p.source_rfq_id ? `RFQ #${p.source_rfq_id}` : '—'}</td>
        <td class="px-4 py-3 text-center">
          ${p.status !== 'Promoted' ? `<button onclick="CasePMChangeOrdersExt.promoteCpco(${p.id})" class="text-emerald-400 text-xs">→ SCO</button>` : '<span class="text-emerald-500 text-xs">SCO</span>'}
        </td>
      </tr>`).join('');
  }

  function renderErpTable() {
    const tbody = document.getElementById('ceErpTableBody');
    if (!tbody) return;
    if (!ext.erpEvents.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-10 text-center text-zinc-500">ERP queue empty.</td></tr>';
      return;
    }
    tbody.innerHTML = ext.erpEvents.map(e => `
      <tr class="border-b border-zinc-800">
        <td class="px-4 py-2 text-xs">${e.created_at ? new Date(e.created_at).toLocaleString() : ''}</td>
        <td class="px-4 py-2 text-xs font-mono">${esc(e.event_type)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.accounting_status || e.status)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.message || '')}</td>
        <td class="px-4 py-2 text-center">
          ${e.accounting_status === 'pending_review' ? `
            ${reviewButtonHtml(`CasePMChangeOrdersExt.openErpReviewModal(${e.id})`, 'Review ERP')}` : esc(e.status)}
        </td>
      </tr>`).join('');
  }

  async function newChangeEvent() {
    openCeModal('event');
  }

  async function newRfq() {
    openCeModal('rfq');
  }

  async function newCor() {
    await loadOwnerPcos();
    openCeModal('cor');
  }

  function openCeModal(mode, record) {
    const modal = document.getElementById('ceModal');
    if (!modal) return;
    document.getElementById('ceModalMode').value = mode;
    document.getElementById('ceModalId').value = record?.id || '';
    const titles = { event: 'Change Event', rfq: 'RFQ', cor: 'COR' };
    document.getElementById('ceModalTitle').textContent = record ? `Edit ${titles[mode]}` : `New ${titles[mode]}`;
    document.getElementById('ceModalTitleInput').value = record?.title || '';
    document.getElementById('ceModalRom').value = record?.rom_amount ?? record?.amount ?? record?.estimated_amount ?? 0;
    document.getElementById('ceModalSchedule').value = record?.schedule_impact_days ?? 0;
    document.getElementById('ceModalDrawing').value = record?.drawing_revision || '';
    document.getElementById('ceModalContingency').value = record?.contingency_release_amount ?? 0;
    document.getElementById('ceModalDescription').value = record?.description || '';
    document.getElementById('ceRfqFields')?.classList.toggle('hidden', mode !== 'rfq');
    document.getElementById('ceCorFields')?.classList.toggle('hidden', mode !== 'cor');
    document.getElementById('ceModalContingencyRow')?.classList.toggle('hidden', mode !== 'event');
    document.getElementById('ceModalDrawingRow')?.classList.toggle('hidden', mode === 'rfq');
    const romRow = document.getElementById('ceModalRom')?.closest('div');
    if (romRow) romRow.classList.toggle('hidden', mode === 'cor');
    if (mode === 'rfq') {
      document.getElementById('ceModalRfqCompany').value = record?.company_name || '';
      document.getElementById('ceModalRfqCommitment').value = record?.linked_commitment_ref || '';
      document.getElementById('ceModalRfqCostCode').value = record?.allocations?.[0]?.cost_code || '';
    }
    if (mode === 'cor') {
      renderCorPcoPicker((record?.linked_pcos || []).map(p => p.id));
    }
    if (global.CasePMChangeOrders?.openDialog) global.CasePMChangeOrders.openDialog(modal);
    else modal.showModal();
  }

  async function saveCeModal(e) {
    e.preventDefault();
    const mode = document.getElementById('ceModalMode').value;
    const id = document.getElementById('ceModalId').value;
    const title = document.getElementById('ceModalTitleInput').value.trim();
    const rom = parseFloat(document.getElementById('ceModalRom').value) || 0;
    const schedule = parseInt(document.getElementById('ceModalSchedule').value, 10) || 0;
    const drawing = document.getElementById('ceModalDrawing').value.trim();
    const contingency = parseFloat(document.getElementById('ceModalContingency').value) || 0;
    const description = document.getElementById('ceModalDescription').value.trim();
    const project_id = pid();
    if (mode === 'event') {
      if (id) {
        await api(`/api/change-events/${id}`, { method: 'PUT', body: JSON.stringify({ title, rom_amount: rom, schedule_impact_days: schedule, drawing_revision: drawing, contingency_release_amount: contingency, description }) });
      } else {
        await api('/api/change-events', { method: 'POST', body: JSON.stringify({ project_id, title, rom_amount: rom, schedule_impact_days: schedule, drawing_revision: drawing, contingency_release_amount: contingency, description }) });
      }
      await loadChangeEvents();
    } else if (mode === 'rfq') {
      const company = document.getElementById('ceModalRfqCompany')?.value?.trim() || '';
      const commitment = document.getElementById('ceModalRfqCommitment')?.value?.trim() || '';
      const costCode = document.getElementById('ceModalRfqCostCode')?.value?.trim() || '';
      if (!company) {
        alert('Subcontractor company is required for RFQs.');
        return;
      }
      await api('/api/rfqs', { method: 'POST', body: JSON.stringify({ project_id, title, company_name: company, linked_commitment_ref: commitment, allocations: costCode ? [{ cost_code: costCode, cost_type: 'Subcontract', amount: rom }] : [] }) });
      await loadRfqs();
    } else if (mode === 'cor') {
      const pcoIds = [...document.querySelectorAll('#ceModalCorPcos input[type=checkbox]:checked')].map(cb => parseInt(cb.value, 10)).filter(Boolean);
      if (!pcoIds.length) {
        alert('Select at least one owner PCO to package in this COR. SOV line items live on the PCOs.');
        return;
      }
      await api('/api/cors', { method: 'POST', body: JSON.stringify({ project_id, title, drawing_revision: drawing, description, schedule_impact_days: schedule, pco_ids: pcoIds }) });
      await loadCors();
    }
    document.getElementById('ceModal').close();
  }

  async function rfqWorkflow(id, action, promoteCpco) {
    await api(`/api/rfqs/${id}/workflow`, {
      method: 'POST',
      body: JSON.stringify({ action, promote_cpco: !!promoteCpco }),
    });
    await Promise.all([loadRfqs(), loadCpcos()]);
    if (promoteCpco) CO.switchTab('cpcos');
  }

  async function openRfqQuote(id) {
    const r = ext.rfqs.find(x => x.id === id);
    const amt = parseFloat((await cePrompt(`Quote amount for ${r?.number}:`, r?.allocations?.[0]?.amount || '0', { title: 'RFQ Quote' })) || '0') || 0;
    const allocs = (r?.allocations || []).map(a => ({ ...a, quoted_amount: amt }));
    await api(`/api/rfqs/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action: 'quote', allocations: allocs.length ? allocs : [{ cost_code: '01-0000', cost_type: 'Subcontract', amount: amt, quoted_amount: amt }] }) });
    await loadRfqs();
  }

  async function corWorkflow(id, action, promotePco) {
    await api(`/api/cors/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action, promote_pco: !!promotePco }) });
    await Promise.all([loadCors(), CO.loadPcos ? CO.loadPcos() : null]);
    if (promotePco && CO.switchTab) CO.switchTab('pcos');
  }

  async function promoteCpco(id) {
    if (!(await ceConfirm('Promote CPCO to Subcontractor Change Order (SCO)?', { title: 'Promote CPCO' }))) return;
    await api(`/api/pcos/${id}/promote-cpco`, { method: 'POST', body: '{}' });
    await Promise.all([loadCpcos(), CO.loadChangeOrders ? CO.loadChangeOrders() : null]);
    if (CO.switchTab) CO.switchTab('subs');
  }

  async function erpReview(id, action) {
    const notes = action === 'reject' ? ((await cePrompt('Rejection notes:', '', { title: 'Reject ERP Event' })) || '') : '';
    await api(`/api/sage/sync-events/${id}/accounting`, { method: 'POST', body: JSON.stringify({ action, notes }) });
    await loadErpQueue();
  }

  async function viewChangeEvent(id, opts = {}) {
    if (!opts.preserveSelection) ext.ceLineSelection.clear();
    ext.activeChangeEventId = id;
    await loadCommitments();
    const e = await api(`/api/change-events/${id}`);
    ext._activeCeDetail = e;
    document.getElementById('coDetailDrawer').classList.add('open');
    document.getElementById('coDrawerBackdrop').classList.remove('hidden');
    document.getElementById('drawerTitle').textContent = `${e.number} — ${e.title || 'Change Event'}`;
    const rfqRows = (e.rfqs || []).map(r => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-sky-400">${esc(r.number)}</td><td class="py-1">${esc(r.company_name || '—')}</td><td class="py-1 text-center">${statusBadge(r.status)}</td><td class="py-1 text-right font-mono">${fmt(r.quoted_amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
    const corRows = (e.cors || []).map(c => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-indigo-400">${esc(c.number)}</td><td class="py-1">${esc(c.title)}</td><td class="py-1 text-center">${statusBadge(c.status)}</td><td class="py-1 text-right font-mono">${fmt(c.amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
    const pcoRows = (e.pcos || []).map(p => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-amber-400">${esc(p.number)}</td><td class="py-1">${esc(p.title)}</td><td class="py-1 text-center">${statusBadge(p.status)}</td><td class="py-1 text-right font-mono">${fmt(p.estimated_amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
    const cpcoRows = (e.cpcos || []).map(p => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-amber-400">${esc(p.number)}</td><td class="py-1">${esc(p.company_name || '—')}</td><td class="py-1 text-center">${statusBadge(p.status)}</td><td class="py-1 text-right font-mono">${fmt(p.estimated_amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
    const ccoRows = (e.commitment_cos || []).map(c => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-emerald-400">${esc(c.number)}</td><td class="py-1">${esc(c.company_name || '—')}</td><td class="py-1 text-center">${statusBadge(c.status)}</td><td class="py-1 text-right font-mono">${fmt(c.amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
    const canWorkflow = ['Open', 'Pricing', 'Pending Review'].includes(e.status);
    const reviewBanner = canWorkflow && e.status !== 'Open' ? `
      <div class="mb-6 p-4 rounded-lg bg-emerald-950/50 border-2 border-emerald-600 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div class="text-emerald-400 font-semibold">Workflow action needed</div>
          <div class="text-xs text-zinc-400 mt-1">Status: ${esc(e.status)}</div>
        </div>
        ${reviewButtonHtml(`CasePMChangeOrdersExt.openCeReviewModal(${e.id})`, 'Review & Advance')}
      </div>` : '';
    document.getElementById('drawerBody').innerHTML = reviewBanner + `
      <div class="space-y-2">
        <p><span class="text-zinc-500">Status</span><br>${statusBadge(e.status)}</p>
        <p><span class="text-zinc-500">ROM</span><br><span class="font-mono text-lg">${fmt(e.rom_amount)}</span></p>
        <p><span class="text-zinc-500">Schedule impact</span><br>${e.schedule_impact_days || 0} days</p>
        <p><span class="text-zinc-500">Drawing revision</span><br>${esc(e.drawing_revision || '—')}</p>
        <p><span class="text-zinc-500">Contingency release</span><br>${e.contingency_release_amount ? fmt(e.contingency_release_amount) : '—'}</p>
        <p><span class="text-zinc-500">Description</span><br>${esc(e.description || '—')}</p>
      </div>
      ${renderCeLineItemsTable(e)}
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">RFQs</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Sub</th><th class="text-center">Status</th><th class="text-right">Quote</th></tr></thead><tbody>${rfqRows}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">CPCOs</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Sub</th><th class="text-center">Status</th><th class="text-right">ROM</th></tr></thead><tbody>${cpcoRows}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Commitment COs (CCO)</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Sub</th><th class="text-center">Status</th><th class="text-right">Amount</th></tr></thead><tbody>${ccoRows}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">CORs (owner)</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Title</th><th class="text-center">Status</th><th class="text-right">Amount</th></tr></thead><tbody>${corRows}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Owner PCOs</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Title</th><th class="text-center">Status</th><th class="text-right">ROM</th></tr></thead><tbody>${pcoRows}</tbody></table></div>`;
    document.getElementById('drawerActions').innerHTML = `
      ${e.status === 'Open' ? `<button type="button" onclick="CasePMChangeOrdersExt.ceWorkflow(${e.id},'submit')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-md text-sm">Submit for Pricing</button>` : ''}
      <button type="button" onclick="CasePMChangeOrdersExt.editChangeEvent(${e.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>
      <button type="button" onclick="CasePMChangeOrders.closeDrawer()" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm text-zinc-400">Close</button>`;
  }

  async function editChangeEvent(id) {
    const cached = ext.changeEvents.find(x => x.id === id);
    if (cached) {
      openCeModal('event', cached);
      return;
    }
    const e = await api(`/api/change-events/${id}`);
    openCeModal('event', e);
  }

  async function ceWorkflow(id, action) {
    await api(`/api/change-events/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action }) });
    await loadChangeEvents();
    if (action !== 'reject') await viewChangeEvent(id);
    else CasePMChangeOrders.closeDrawer();
  }

  async function portalRfqQuote(id) {
    const r = ext.rfqs.find(x => x.id === id);
    const amt = parseFloat((await cePrompt(`Quote amount for ${r?.number}:`, r?.allocations?.[0]?.amount || '0', { title: 'RFQ Portal Quote' })) || '0') || 0;
    if (!amt) return;
    await api(`/api/rfqs/${id}/portal-quote`, { method: 'POST', body: JSON.stringify({ quoted_amount: amt, cost_code: r?.allocations?.[0]?.cost_code || '01-0000' }) });
    await loadRfqs();
  }

  function renderBillingVarianceBanner() {
    const el = document.getElementById('coBillingVarianceBanner');
    if (!el || !ext.billingVariances.length) { if (el) el.classList.add('hidden'); return; }
    const flagged = ext.billingVariances.filter(v => Math.abs(v.variance || 0) > 0.01);
    if (!flagged.length) { el.classList.add('hidden'); return; }
    el.classList.remove('hidden');
    el.innerHTML = `<span class="text-amber-400 font-medium">${flagged.length} sub CO billing variance(s)</span> — ` +
      flagged.slice(0, 5).map(v => `<span class="font-mono">${esc(v.number)}: ${fmt(v.variance)}</span>`).join(' · ');
  }

  async function loadTabData(tab) {
    if (tab === 'events') await loadChangeEvents();
    if (tab === 'rfqs') await loadRfqs();
    if (tab === 'cors') await loadCors();
    if (tab === 'cpcos') await loadCpcos();
    if (tab === 'erp') await loadErpQueue();
    if (tab === 'subs' || tab === 'cos') {
      await loadBillingVariance();
      renderBillingVarianceBanner();
    }
  }

  const TAB_KEYS = { events: 'change_orders_events', rfqs: 'change_orders_rfq', cors: 'change_orders_cor', cpcos: 'change_orders_cpco', erp: 'change_orders_erp' };
  const TAB_SECTION = { events: 'change-events', rfqs: 'rfq', cors: 'cor', cpcos: 'cpco', erp: 'erp', cos: 'owner-co', pcos: 'pco', subs: 'sub-co' };
  if (global.CasePMPageHelp) global.CasePMPageHelp.registerTabSectionMap('change_orders', TAB_SECTION);

  function switchExtTab(tab) {
    ['events', 'rfqs', 'cors', 'cpcos', 'erp', 'templates'].forEach(t => {
      document.getElementById(`tab${t.charAt(0).toUpperCase() + t.slice(1)}`)?.classList.toggle('hidden', tab !== t);
      const btn = document.getElementById(`btnTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
      if (btn) btn.className = tab === t
        ? 'px-4 py-2 rounded-md text-sm font-medium bg-violet-600 text-white'
        : 'px-4 py-2 rounded-md text-sm font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
    });
    ['cos', 'pcos', 'subs'].forEach(t => document.getElementById(`tab${t.charAt(0).toUpperCase() + t.slice(1)}`)?.classList.add('hidden'));
    if (tab === 'templates' && CO.loadCoTemplates) CO.loadCoTemplates();
    loadTabData(tab);
  }

  const origSwitch = CO.switchTab;
  CO.switchTab = function (tab) {
    if (['events', 'rfqs', 'cors', 'cpcos', 'erp', 'templates'].includes(tab)) {
      switchExtTab(tab);
      if (global.CasePMPageHelp?.setContextFromTab) global.CasePMPageHelp.setContextFromTab(tab);
      return;
    }
    return origSwitch.call(CO, tab);
  };

  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      const params = new URLSearchParams(location.search);
      const tab = params.get('tab');
      if (tab && TAB_KEYS[tab]) CO.switchTab(tab);
      const rfqId = params.get('rfq_id');
      if (rfqId) CO.switchTab('rfqs');
    }, 500);
  });

  global.CasePMChangeOrdersExt = {
    loadChangeEvents, loadRfqs, loadCors, loadCpcos, loadErpQueue, loadBillingVariance, loadCommitments,
    newChangeEvent, newRfq, newCor, openCeModal, saveCeModal, rfqWorkflow, openRfqQuote, corWorkflow, openCorReviewModal, openCeReviewModal, openErpReviewModal, promoteCpco,
    erpReview, viewChangeEvent, editChangeEvent, ceWorkflow, portalRfqQuote, switchExtTab, ext,
    addCeLineRow, saveCeLineItems, bulkCreateFromCe, toggleCeLineSelection, toggleCeSelectAllLines, setCeVendorFilter,
  };
})(window);
