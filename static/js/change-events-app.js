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

  function statusBadge(status) {
    if (CO.statusBadge) return CO.statusBadge(status);
    return `<span class="text-xs">${esc(status)}</span>`;
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
          ${r.status === 'Sent' ? `<button onclick="CasePMChangeOrdersExt.openRfqQuote(${r.id})" class="text-emerald-400 text-xs">Quote</button>` : ''}
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
        <td class="px-4 py-3 text-center flex gap-1 justify-center">
          ${c.status === 'Draft' ? `<button onclick="CasePMChangeOrdersExt.corWorkflow(${c.id},'submit')" class="text-amber-400 text-xs">Submit</button>` : ''}
          ${['Submitted','Under Review'].includes(c.status) ? `<button onclick="CasePMChangeOrdersExt.corWorkflow(${c.id},'approve',true)" class="text-emerald-400 text-xs">Approve→PCO</button>` : ''}
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
            <button onclick="CasePMChangeOrdersExt.erpReview(${e.id},'accept')" class="text-emerald-400 text-xs mr-2">Accept</button>
            <button onclick="CasePMChangeOrdersExt.erpReview(${e.id},'reject')" class="text-red-400 text-xs">Reject</button>` : esc(e.status)}
        </td>
      </tr>`).join('');
  }

  async function newChangeEvent() {
    const title = prompt('Change Event title:');
    if (!title) return;
    const rom = parseFloat(prompt('ROM amount (owner estimate):', '0') || '0') || 0;
    await api('/api/change-events', { method: 'POST', body: JSON.stringify({ project_id: pid(), title, rom_amount: rom }) });
    await loadChangeEvents();
  }

  async function newRfq() {
    const title = prompt('RFQ title:');
    if (!title) return;
    const company = prompt('Subcontractor company name:') || '';
    const commitment = prompt('Linked commitment # (optional):') || '';
    const costCode = prompt('Cost code:') || '';
    const amount = parseFloat(prompt('Estimated amount:', '0') || '0') || 0;
    await api('/api/rfqs', {
      method: 'POST',
      body: JSON.stringify({
        project_id: pid(), title, company_name: company, linked_commitment_ref: commitment,
        allocations: costCode ? [{ cost_code: costCode, cost_type: 'Subcontract', amount }] : [],
      }),
    });
    await loadRfqs();
  }

  async function newCor() {
    const title = prompt('COR title:');
    if (!title) return;
    const amount = parseFloat(prompt('Amount:', '0') || '0') || 0;
    const drawing = prompt('Drawing revision (optional):') || '';
    await api('/api/cors', {
      method: 'POST',
      body: JSON.stringify({
        project_id: pid(), title, amount, drawing_revision: drawing,
        allocations: [{ cost_code: '01-0000', cost_type: 'Other', amount }],
      }),
    });
    await loadCors();
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
    const amt = parseFloat(prompt(`Quote amount for ${r?.number}:`, r?.allocations?.[0]?.amount || '0') || '0') || 0;
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
    if (!confirm('Promote CPCO to Subcontractor Change Order (SCO)?')) return;
    await api(`/api/pcos/${id}/promote-cpco`, { method: 'POST', body: '{}' });
    await Promise.all([loadCpcos(), CO.loadChangeOrders ? CO.loadChangeOrders() : null]);
    if (CO.switchTab) CO.switchTab('subs');
  }

  async function erpReview(id, action) {
    const notes = action === 'reject' ? (prompt('Rejection notes:') || '') : '';
    await api(`/api/sage/sync-events/${id}/accounting`, { method: 'POST', body: JSON.stringify({ action, notes }) });
    await loadErpQueue();
  }

  async function viewChangeEvent(id) {
    const e = await api(`/api/change-events/${id}`);
    alert(`${e.number} — ${e.title}\nROM: ${fmt(e.rom_amount)}\nRFQs: ${(e.rfqs||[]).length} · CORs: ${(e.cors||[]).length} · PCOs: ${(e.pcos||[]).length}`);
  }

  async function loadTabData(tab) {
    if (tab === 'events') await loadChangeEvents();
    if (tab === 'rfqs') await loadRfqs();
    if (tab === 'cors') await loadCors();
    if (tab === 'cpcos') await loadCpcos();
    if (tab === 'erp') await loadErpQueue();
    if (tab === 'subs' || tab === 'cos') await loadBillingVariance();
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
    newChangeEvent, newRfq, newCor, rfqWorkflow, openRfqQuote, corWorkflow, promoteCpco,
    erpReview, viewChangeEvent, switchExtTab, ext,
  };
})(window);
