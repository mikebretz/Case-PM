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

  function openCorReviewModal(id) {
    if (CO.closeDrawer) CO.closeDrawer();
    const c = ext.cors.find(x => x.id === id);
    if (!c || typeof global.CasePMApprovalResponder === 'undefined') {
      corWorkflow(id, 'approve', c?.status === 'Pending Accounting');
      return;
    }
    const promotePco = c.status === 'Pending Accounting';
    global.CasePMApprovalResponder.openLocal({
      module: 'COR',
      entityId: id,
      title: `${c.number} — ${c.title || 'Change Order Request'}`,
      status: c.status,
      ball: c.ball_in_court_role,
      summaryHtml: `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Amount</span><span class="font-mono text-emerald-400">${fmt(c.amount)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Drawing</span><span>${esc(c.drawing_revision || '—')}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Schedule impact</span><span>${c.schedule_impact_days || 0} days</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Status</span><span>${statusBadge(c.status)}</span></div>
        ${c.description ? `<div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Description</div><p class="text-sm whitespace-pre-wrap">${esc(c.description)}</p></div>` : ''}`,
      actions: [
        { action: 'approve', label: promotePco ? 'Approve → PCO' : 'Approve Step', style: 'primary' },
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
      tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-10 text-center text-zinc-500">No CORs yet.</td></tr>';
      return;
    }
    tbody.innerHTML = ext.cors.map(c => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50">
        <td class="px-4 py-3 font-mono text-indigo-400">${esc(c.number)}</td>
        <td class="px-4 py-3">${esc(c.title)}</td>
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
    document.getElementById('ceModalContingencyRow')?.classList.toggle('hidden', mode !== 'event');
    document.getElementById('ceModalDrawingRow')?.classList.toggle('hidden', mode === 'rfq');
    if (mode === 'rfq') {
      document.getElementById('ceModalRfqCompany').value = record?.company_name || '';
      document.getElementById('ceModalRfqCommitment').value = record?.linked_commitment_ref || '';
      document.getElementById('ceModalRfqCostCode').value = record?.allocations?.[0]?.cost_code || '';
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
      await api('/api/cors', { method: 'POST', body: JSON.stringify({ project_id, title, amount: rom, drawing_revision: drawing, description, schedule_impact_days: schedule, allocations: [{ cost_code: '01-0000', cost_type: 'Other', amount: rom }] }) });
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

  async function viewChangeEvent(id) {
    const e = await api(`/api/change-events/${id}`);
    document.getElementById('coDetailDrawer').classList.add('open');
    document.getElementById('coDrawerBackdrop').classList.remove('hidden');
    document.getElementById('drawerTitle').textContent = `${e.number} — ${e.title || 'Change Event'}`;
    const rfqRows = (e.rfqs || []).map(r => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-sky-400">${esc(r.number)}</td><td class="py-1">${esc(r.company_name || '—')}</td><td class="py-1 text-center">${statusBadge(r.status)}</td><td class="py-1 text-right font-mono">${fmt(r.quoted_amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
    const corRows = (e.cors || []).map(c => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-indigo-400">${esc(c.number)}</td><td class="py-1">${esc(c.title)}</td><td class="py-1 text-center">${statusBadge(c.status)}</td><td class="py-1 text-right font-mono">${fmt(c.amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
    const pcoRows = (e.pcos || []).map(p => `<tr class="border-b border-zinc-800"><td class="py-1 font-mono text-amber-400">${esc(p.number)}</td><td class="py-1">${esc(p.title)}</td><td class="py-1 text-center">${statusBadge(p.status)}</td><td class="py-1 text-right font-mono">${fmt(p.estimated_amount)}</td></tr>`).join('') || '<tr><td colspan="4" class="py-3 text-zinc-500">None</td></tr>';
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
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">RFQs</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Sub</th><th class="text-center">Status</th><th class="text-right">Quote</th></tr></thead><tbody>${rfqRows}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">CORs</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Title</th><th class="text-center">Status</th><th class="text-right">Amount</th></tr></thead><tbody>${corRows}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">PCOs</div><table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left">#</th><th class="text-left">Title</th><th class="text-center">Status</th><th class="text-right">ROM</th></tr></thead><tbody>${pcoRows}</tbody></table></div>`;
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

  function switchExtTab(tab) {
    ['events', 'rfqs', 'cors', 'cpcos', 'erp'].forEach(t => {
      document.getElementById(`tab${t.charAt(0).toUpperCase() + t.slice(1)}`)?.classList.toggle('hidden', tab !== t);
      const btn = document.getElementById(`btnTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
      if (btn) btn.className = tab === t
        ? 'px-4 py-2 rounded-md text-sm font-medium bg-violet-600 text-white'
        : 'px-4 py-2 rounded-md text-sm font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
    });
    ['cos', 'pcos', 'subs'].forEach(t => document.getElementById(`tab${t.charAt(0).toUpperCase() + t.slice(1)}`)?.classList.add('hidden'));
    loadTabData(tab);
  }

  const origSwitch = CO.switchTab;
  CO.switchTab = function (tab) {
    if (['events', 'rfqs', 'cors', 'cpcos', 'erp'].includes(tab)) {
      switchExtTab(tab);
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
    loadChangeEvents, loadRfqs, loadCors, loadCpcos, loadErpQueue, loadBillingVariance,
    newChangeEvent, newRfq, newCor, openCeModal, saveCeModal, rfqWorkflow, openRfqQuote, corWorkflow, openCorReviewModal, openCeReviewModal, openErpReviewModal, promoteCpco,
    erpReview, viewChangeEvent, editChangeEvent, ceWorkflow, portalRfqQuote, switchExtTab, ext,
  };
})(window);
