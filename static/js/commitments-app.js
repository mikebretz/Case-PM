/**
 * Case PM — Commitments module (PO, Subcontract, Supply, Service)
 * Procore/RedTeam-style workflow · AIA forms · Sage 300 · DocuSign-ready
 */
(function (global) {
  'use strict';

  const TYPES = ['Purchase Order', 'Subcontract', 'Material Supply', 'Service Agreement'];
  const STATUSES = ['Draft', 'Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner', 'Approved', 'Rejected', 'Partially Invoiced', 'Closed', 'Void'];
  const AIA_FORMS = ['A101', 'A102', 'A201', 'A401', 'A501', 'A701', 'A312', 'Other', 'N/A'];
  const SIGNATURE_METHODS = [
    { value: 'internal', label: 'Certified internal signature' },
    { value: 'docusign', label: 'DocuSign eSignature' },
    { value: 'wet_signature', label: 'Wet signature (upload executed copy)' },
  ];
  const DELETABLE_STATUSES = ['Draft', 'Rejected', 'Void'];

  const ROLE_MAP = {
    'Project Manager': ['Project Manager', 'Admin'],
    'Contractor Accounting': ['Contractor Accounting', 'Admin'],
    'Owner': ['Owner', 'Admin'],
    'Creator': ['Project Manager', 'Admin', 'Company User'],
  };

  let state = {
    commitments: [],
    costCodes: [],
    companies: [],
    stats: {},
    sageLog: [],
    auditLog: [],
    filter: { search: '', status: '', type: '' },
    allocationRows: [],
    drawerRecord: null,
    modalOriginalType: null,
    modalStatus: 'Draft',
  };

  function projectCtx() {
    return global.COMMITMENT_PROJECT_CTX || {};
  }

  function userRole() {
    return (global.CASEPM_PORTAL && global.CASEPM_PORTAL.role) || 'Admin';
  }

  function userName() {
    return (global.CASEPM_PORTAL && (global.CASEPM_PORTAL.full_name || global.CASEPM_PORTAL.email)) || 'User';
  }

  function canActOnBall(role) {
    if (!role) return false;
    if (userRole() === 'Admin') return true;
    return (ROLE_MAP[role] || [role]).includes(userRole());
  }

  function canDelete(c) {
    return userRole() === 'Admin' && DELETABLE_STATUSES.includes(c.status);
  }

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    if (typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.projectId) return CasePMWorkflow.projectId();
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function auditLogKey() {
    return `casepm_commitment_audit_p${projectId() || 'default'}`;
  }

  function loadAuditLog() {
    try {
      state.auditLog = JSON.parse(localStorage.getItem(auditLogKey()) || '[]');
    } catch {
      state.auditLog = [];
    }
  }

  function saveAuditLog() {
    if (state.auditLog.length > 1000) state.auditLog.length = 1000;
    localStorage.setItem(auditLogKey(), JSON.stringify(state.auditLog));
  }

  function logCommitmentAudit(action, details = {}) {
    const entry = {
      id: Date.now() + Math.random(),
      timestamp: new Date().toISOString(),
      action,
      user: userName(),
      details,
    };
    state.auditLog.unshift(entry);
    saveAuditLog();
  }

  function fmt(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString();
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || json.message || 'Request failed');
    return json;
  }

  function loadCompanies() {
    try {
      state.companies = JSON.parse(localStorage.getItem('casepm_companies') || '[]');
    } catch { state.companies = []; }
  }

  async function loadCostCodes() {
    const pid = projectId();
    if (!pid) return;
    try {
      const json = await api(`/api/commitments/cost-codes?project_id=${pid}`);
      state.costCodes = json.cost_codes || [];
    } catch {
      if (typeof CasePMBudgetSync !== 'undefined') {
        await CasePMBudgetSync.init().catch(() => {});
        const lines = JSON.parse(global.casepmStore?.getItem('budgetLines') || '[]');
        state.costCodes = lines.map(l => ({ code: l.cost_code, description: l.description }));
      }
    }
  }

  async function loadDashboard() {
    const pid = projectId();
    if (!pid) return;
    try {
      state.stats = await api(`/api/commitments/dashboard?project_id=${pid}`);
      renderSummary();
    } catch {
      state.stats = {};
    }
  }

  async function loadCommitments() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/commitments?project_id=${pid}`);
    state.commitments = json.commitments || [];
    renderTable();
    syncCommitmentsToLocalStorage();
  }

  function syncCommitmentsToLocalStorage() {
    const pid = projectId();
    const payload = state.commitments.map(c => ({
      id: c.id,
      number: c.number,
      description: c.description,
      title: c.title,
      commitment_type: c.commitment_type,
      status: c.status,
      company_name: c.company_name,
      company_id: c.company_id,
      original_amount: c.original_amount,
      current_amount: c.current_amount,
    }));
    localStorage.setItem(`casepm_commitments_p${pid}`, JSON.stringify(payload));
    localStorage.setItem('casepm_commitments', JSON.stringify(payload));
  }

  async function loadSageLog() {
    const pid = projectId();
    if (!pid) return;
    try {
      const res = await fetch(`/api/sage/sync-events?project_id=${pid}&limit=30`, { credentials: 'same-origin' });
      const json = await res.json();
      state.sageLog = (json.events || []).filter(e =>
        ['CommitmentApproved', 'CommitmentSubmitted', 'CommitmentDocuSignSent'].includes(e.event_type)
      );
    } catch { state.sageLog = []; }
    renderSageBar();
  }

  function renderSummary() {
    const s = state.stats;
    const map = {
      statTotal: s.total_count || 0,
      statApproved: s.approved_count || 0,
      statPending: s.pending_count || 0,
      statApprovedTotal: fmt(s.approved_total),
      statPendingTotal: fmt(s.pending_total),
      statCommitted: fmt(s.committed_total),
    };
    Object.keys(map).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
  }

  function filteredRows() {
    const { search, status, type } = state.filter;
    return state.commitments.filter(c => {
      const text = `${c.number} ${c.title} ${c.description} ${c.company_name || ''}`.toLowerCase();
      if (search && !text.includes(search.toLowerCase())) return false;
      if (status && c.status !== status) return false;
      if (type && c.commitment_type !== type) return false;
      return true;
    });
  }

  function statusBadge(status) {
    const colors = {
      Draft: 'bg-zinc-700 text-zinc-300', Submitted: 'bg-amber-900/50 text-amber-300',
      'Pending PM': 'bg-amber-900/50 text-amber-300', 'Pending Accounting': 'bg-purple-900/50 text-purple-300',
      'Pending Owner': 'bg-orange-900/50 text-orange-300', Approved: 'bg-emerald-900/50 text-emerald-400',
      Rejected: 'bg-red-900/50 text-red-400', 'Partially Invoiced': 'bg-sky-900/50 text-sky-300',
      Closed: 'bg-zinc-800 text-zinc-500', Void: 'bg-zinc-800 text-zinc-500',
    };
    const cls = colors[status] || 'bg-zinc-700 text-zinc-300';
    return `<span class="inline-block px-2 py-0.5 rounded text-[10px] font-medium ${cls}">${status}</span>`;
  }

  function sigBadge(c) {
    const map = {
      unsigned: 'text-zinc-500', pending_signatures: 'text-amber-400',
      partially_signed: 'text-sky-400', fully_executed: 'text-emerald-400',
    };
    const st = c.signature_status || 'unsigned';
    const label = st.replace(/_/g, ' ');
    return `<span class="text-[10px] ${map[st] || 'text-zinc-500'}">${label}</span>`;
  }

  function renderTable() {
    const tbody = document.getElementById('comTableBody');
    if (!tbody) return;
    const rows = filteredRows();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="11" class="px-6 py-12 text-center text-zinc-500">No commitments yet. Click New Commitment to start.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(c => {
      const showSubmit = c.status === 'Draft';
      const showApprove = ['Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner'].includes(c.status) && canActOnBall(c.ball_in_court_role);
      return `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" onclick="CasePMCommitments.view(${c.id})">
        <td class="px-4 py-3 font-mono text-emerald-400 whitespace-nowrap">${esc(c.number)}</td>
        <td class="px-4 py-3 text-xs text-zinc-400">${esc(c.commitment_type)}</td>
        <td class="px-4 py-3 max-w-[200px] truncate">${esc(c.title || c.description)}</td>
        <td class="px-4 py-3 text-xs">${esc(c.company_name || '—')}</td>
        <td class="px-4 py-3 text-xs font-mono">${esc(c.aia_form || '—')}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(c.original_amount)}</td>
        <td class="px-4 py-3 text-right font-mono text-amber-400">+${fmt(c.approved_changes)}</td>
        <td class="px-4 py-3 text-right font-mono font-medium">${fmt(c.current_amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(c.status)}</td>
        <td class="px-4 py-3 text-center">${sigBadge(c)}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-1">
            <button onclick="CasePMCommitments.printCommitment(${c.id})" class="p-1.5 text-sky-400 hover:bg-zinc-800 rounded" title="Print"><i class="fa-solid fa-print"></i></button>
            ${showSubmit ? `<button onclick="CasePMCommitments.workflow(${c.id},'submit')" class="p-1.5 text-amber-400 hover:bg-zinc-800 rounded" title="Submit"><i class="fa-solid fa-paper-plane"></i></button>` : ''}
            ${showApprove ? `<button onclick="CasePMCommitments.workflow(${c.id},'approve')" class="p-1.5 text-emerald-400 hover:bg-zinc-800 rounded" title="Approve"><i class="fa-solid fa-check"></i></button>
            <button onclick="CasePMCommitments.workflow(${c.id},'reject')" class="p-1.5 text-red-400 hover:bg-zinc-800 rounded" title="Reject"><i class="fa-solid fa-times"></i></button>` : ''}
            <button onclick="CasePMCommitments.edit(${c.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded"><i class="fa-solid fa-edit"></i></button>
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  function renderSageBar() {
    const el = document.getElementById('comSageStatusText');
    if (!el) return;
    const ctx = projectCtx();
    const job = ctx.sage_job || ctx.number || '—';
    const latest = state.sageLog[0];
    el.textContent = latest
      ? `Sage 300 · Job ${job} · ${latest.event_type} · ${latest.status} · ${new Date(latest.created_at).toLocaleString()}`
      : `Sage 300 · Job ${job} · No commitment sync events yet`;
  }

  function openSageSyncLogModal() {
    let modal = document.getElementById('comSageSyncLogModal');
    if (!modal) {
      modal = document.createElement('dialog');
      modal.id = 'comSageSyncLogModal';
      modal.className = 'bg-zinc-900 border border-zinc-700 rounded-lg p-0 text-white max-w-2xl w-full';
      document.body.appendChild(modal);
    }
    const rows = state.sageLog.length
      ? state.sageLog.slice(0, 40).map(e => `
        <tr class="border-b border-zinc-800">
          <td class="py-2 pr-3 text-[10px] text-zinc-400 whitespace-nowrap">${new Date(e.created_at).toLocaleString()}</td>
          <td class="py-2 pr-3 text-xs">${esc(e.event_type)}</td>
          <td class="py-2 pr-3 text-xs ${e.status === 'queued' ? 'text-amber-400' : e.status === 'error' ? 'text-red-400' : 'text-emerald-400'}">${esc(e.status)}</td>
          <td class="py-2 text-xs text-zinc-300">${esc(e.message || '')}</td>
        </tr>`).join('')
      : '<tr><td colspan="4" class="py-6 text-center text-zinc-500 text-sm">No Sage sync events recorded yet.</td></tr>';
    modal.innerHTML = `
      <div class="p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold">Sage 300 Commitment Sync Log</h3>
          <button type="button" onclick="document.getElementById('comSageSyncLogModal').close()" class="text-zinc-400 hover:text-white"><i class="fa-solid fa-times"></i></button>
        </div>
        <p class="text-xs text-zinc-400 mb-3">Commitment submit, approve, and DocuSign events post to Sage when SAGE_API_URL is configured.</p>
        <div class="max-h-80 overflow-auto">
          <table class="w-full text-left"><thead><tr class="text-[10px] text-zinc-500 uppercase"><th class="pb-2">Time</th><th class="pb-2">Event</th><th class="pb-2">Status</th><th class="pb-2">Detail</th></tr></thead>
          <tbody>${rows}</tbody></table>
        </div>
      </div>`;
    modal.showModal();
    const pid = projectId();
    if (pid) {
      fetch(`/api/sage/sync-events?project_id=${pid}&limit=40`, { credentials: 'same-origin' })
        .then(r => r.json())
        .then(json => {
          const events = (json.events || []).filter(e =>
            ['CommitmentApproved', 'CommitmentSubmitted', 'CommitmentDocuSignSent'].includes(e.event_type)
          );
          if (!events.length) return;
          state.sageLog = events;
          openSageSyncLogModal();
        })
        .catch(() => {});
    }
  }

  function showCommitmentAuditLog() {
    loadAuditLog();
    const modal = document.createElement('dialog');
    modal.className = 'modal rounded-md p-0 text-white w-full max-w-6xl';
    modal.style.backgroundColor = '#18181b';
    modal.style.border = '1px solid #3f3f46';
    const entries = state.auditLog.slice(0, 200);
    let rows = entries.length
      ? entries.map(e => `
        <tr class="border-b border-zinc-800">
          <td class="px-4 py-2 text-xs text-zinc-400 whitespace-nowrap">${new Date(e.timestamp).toLocaleString()}</td>
          <td class="px-4 py-2 text-xs font-medium">${esc(e.action)}</td>
          <td class="px-4 py-2 text-xs text-zinc-300">${esc(JSON.stringify(e.details || {}))}</td>
          <td class="px-4 py-2 text-xs">${esc(e.user)}</td>
        </tr>`).join('')
      : '<tr><td colspan="4" class="px-4 py-8 text-center text-zinc-500">No audit events yet. Actions on commitments will appear here.</td></tr>';
    modal.innerHTML = `
      <div class="p-6">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-xl font-semibold">Commitment Audit Log</h3>
          <button type="button" onclick="this.closest('dialog').close(); this.closest('dialog').remove()" class="text-zinc-400 hover:text-white"><i class="fa-solid fa-times text-xl"></i></button>
        </div>
        <div class="text-xs text-zinc-400 mb-3">Showing last ${entries.length} events · Newest first</div>
        <div class="max-h-[520px] overflow-auto border border-zinc-700 rounded-md">
          <table class="w-full text-sm">
            <thead class="bg-zinc-800 sticky top-0">
              <tr>
                <th class="px-4 py-2 text-left font-medium text-zinc-400 w-44">Timestamp</th>
                <th class="px-4 py-2 text-left font-medium text-zinc-400 w-40">Action</th>
                <th class="px-4 py-2 text-left font-medium text-zinc-400">Details</th>
                <th class="px-4 py-2 text-left font-medium text-zinc-400 w-28">User</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-zinc-800">${rows}</tbody>
          </table>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.showModal();
  }

  function populateSelect(id, options, selected) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = options.map(o => {
      const val = typeof o === 'string' ? o : o.value;
      const label = typeof o === 'string' ? o : o.label;
      return `<option value="${val}" ${String(val) === String(selected) ? 'selected' : ''}>${esc(label)}</option>`;
    }).join('');
  }

  function populateCompanySelect(selectedId) {
    const el = document.getElementById('modalCompany');
    if (!el) return;
    el.innerHTML = '<option value="">— Select Company —</option>' +
      state.companies.map(c => {
        const name = c.company_name || c.name || '';
        const id = c.id || name;
        return `<option value="${id}" data-name="${esc(name)}" ${String(id) === String(selectedId) ? 'selected' : ''}>${esc(name)}</option>`;
      }).join('');
  }

  function onCompanyChange() {
    const sel = document.getElementById('modalCompany');
    const name = sel?.options[sel.selectedIndex]?.dataset?.name || '';
    const hidden = document.getElementById('modalCompanyName');
    if (hidden) hidden.value = name;
  }

  function defaultAiaForType(type) {
    if (type === 'Subcontract') return 'A401';
    if (type === 'Service Agreement') return 'A201';
    if (type === 'Material Supply') return 'N/A';
    if (type === 'Purchase Order') return 'N/A';
    return 'A101';
  }

  async function previewNextNumber(type) {
    const pid = projectId();
    if (!pid || !type) return '';
    try {
      const json = await api(`/api/commitments/next-number?project_id=${pid}&type=${encodeURIComponent(type)}`);
      return json.number || '';
    } catch {
      return '';
    }
  }

  async function onTypeChange() {
    const type = document.getElementById('modalType')?.value;
    const aiaEl = document.getElementById('modalAiaForm');
    if (aiaEl && (!aiaEl.value || aiaEl.value === defaultAiaForType(state.modalOriginalType))) {
      aiaEl.value = defaultAiaForType(type);
    }
    const status = state.modalStatus || document.getElementById('modalStatus')?.value || 'Draft';
    const numEl = document.getElementById('modalNumber');
    if (!numEl) return;
    if (status === 'Draft' && (!state.modalOriginalType || type !== state.modalOriginalType)) {
      const next = await previewNextNumber(type);
      if (next) numEl.value = next;
    }
  }

  function renderAllocationRows() {
    const container = document.getElementById('allocationRows');
    if (!container) return;
    if (!state.allocationRows.length) state.allocationRows = [{ cost_code: '', amount: 0, description: '' }];
    container.innerHTML = state.allocationRows.map((row, idx) => `
      <div class="grid grid-cols-12 gap-2 items-center mb-2">
        <div class="col-span-4">
          <select class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs alloc-cost-code" data-idx="${idx}">
            <option value="">Cost code…</option>
            ${state.costCodes.map(c => `<option value="${c.code}" ${c.code === row.cost_code ? 'selected' : ''}>${c.code} — ${esc(c.description || '')}</option>`).join('')}
          </select>
        </div>
        <div class="col-span-4"><input type="text" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs alloc-desc" data-idx="${idx}" value="${esc(row.description || '')}" placeholder="Description"></div>
        <div class="col-span-2"><input type="number" step="0.01" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs text-right alloc-amt" data-idx="${idx}" value="${row.amount || 0}"></div>
        <div class="col-span-2 flex gap-1">
          <button type="button" onclick="CasePMCommitments.addAllocRow()" class="px-2 py-1 text-xs bg-zinc-700 rounded">+</button>
          ${state.allocationRows.length > 1 ? `<button type="button" onclick="CasePMCommitments.removeAllocRow(${idx})" class="px-2 py-1 text-xs bg-red-900/50 text-red-400 rounded">×</button>` : ''}
        </div>
      </div>`).join('');
  }

  function readAllocations() {
    const rows = [];
    document.querySelectorAll('.alloc-cost-code').forEach((sel, idx) => {
      const code = sel.value;
      const desc = document.querySelector(`.alloc-desc[data-idx="${idx}"]`)?.value || '';
      const amt = parseFloat(document.querySelector(`.alloc-amt[data-idx="${idx}"]`)?.value) || 0;
      if (code || amt) rows.push({ cost_code: code, amount: amt, description: desc });
    });
    return rows;
  }

  function setVal(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.type === 'checkbox') el.checked = !!val;
    else el.value = val ?? '';
  }

  async function openModal(record) {
    const ctx = projectCtx();
    state.modalOriginalType = record?.commitment_type || null;
    state.modalStatus = record?.status || 'Draft';
    document.getElementById('modalRecordId').value = record?.id || '';
    document.getElementById('comModalHeading').textContent = record ? `Edit ${record.number}` : 'New Commitment';
    populateSelect('modalType', TYPES, record?.commitment_type || 'Purchase Order');
    populateSelect('modalStatus', STATUSES, record?.status || 'Draft');
    populateSelect('modalAiaForm', AIA_FORMS, record?.aia_form || defaultAiaForType(record?.commitment_type));
    populateSelect('modalSignatureMethod', SIGNATURE_METHODS.map(s => s.value), record?.signature_method || 'internal');
    populateCompanySelect(record?.company_id);
    setVal('modalTitle', record?.title || '');
    setVal('modalDescription', record?.description || '');
    setVal('modalCompanyName', record?.company_name || '');
    setVal('modalContactName', record?.contact_name || '');
    setVal('modalContactEmail', record?.contact_email || '');
    setVal('modalContactPhone', record?.contact_phone || '');
    setVal('modalRetainage', record?.retainage_percent || 0);
    setVal('modalPaymentTerms', record?.payment_terms || '');
    setVal('modalFreightTerms', record?.freight_terms || '');
    setVal('modalBillingType', record?.billing_type || 'Lump Sum');
    setVal('modalScope', record?.scope_of_work || record?.notes || '');
    setVal('modalDate', record?.date ? record.date.split('T')[0] : new Date().toISOString().split('T')[0]);
    setVal('modalStartDate', record?.start_date ? record.start_date.split('T')[0] : '');
    setVal('modalEndDate', record?.end_date ? record.end_date.split('T')[0] : '');
    setVal('modalDeliveryDate', record?.delivery_date ? record.delivery_date.split('T')[0] : '');
    setVal('modalAmount', record?.original_amount || '');
    setVal('modalOwnerName', record?.owner_name || ctx.name || '');
    setVal('modalContractorName', record?.contractor_name || 'Case Contracting');
    setVal('modalArchitectEngineer', record?.architect_engineer || '');
    const numEl = document.getElementById('modalNumber');
    if (record?.number) {
      numEl.value = record.number;
    } else {
      const next = await previewNextNumber(record?.commitment_type || 'Purchase Order');
      numEl.value = next || 'Auto on save';
    }
    state.allocationRows = (record?.allocations?.length)
      ? record.allocations.map(a => ({ ...a }))
      : [{ cost_code: '', amount: record?.original_amount || 0, description: '' }];
    onCompanyChange();
    renderAllocationRows();
    document.getElementById('comModal').showModal();
  }

  function readPayload() {
    const companySel = document.getElementById('modalCompany');
    const companyName = document.getElementById('modalCompanyName')?.value || companySel?.options[companySel.selectedIndex]?.dataset?.name || '';
    const allocs = readAllocations();
    const total = allocs.reduce((s, a) => s + (a.amount || 0), 0);
    return {
      project_id: projectId(),
      title: document.getElementById('modalTitle').value.trim(),
      description: document.getElementById('modalDescription').value.trim(),
      commitment_type: document.getElementById('modalType').value,
      status: document.getElementById('modalStatus').value,
      aia_form: document.getElementById('modalAiaForm').value,
      signature_method: document.getElementById('modalSignatureMethod').value,
      company_id: companySel?.value || null,
      company_name: companyName,
      contact_name: document.getElementById('modalContactName')?.value.trim() || null,
      contact_email: document.getElementById('modalContactEmail')?.value.trim() || null,
      contact_phone: document.getElementById('modalContactPhone')?.value.trim() || null,
      retainage_percent: parseFloat(document.getElementById('modalRetainage').value) || 0,
      payment_terms: document.getElementById('modalPaymentTerms').value.trim(),
      freight_terms: document.getElementById('modalFreightTerms')?.value.trim() || null,
      billing_type: document.getElementById('modalBillingType')?.value || 'Lump Sum',
      scope_of_work: document.getElementById('modalScope').value.trim(),
      date: document.getElementById('modalDate').value,
      start_date: document.getElementById('modalStartDate')?.value || null,
      end_date: document.getElementById('modalEndDate')?.value || null,
      delivery_date: document.getElementById('modalDeliveryDate')?.value || null,
      owner_name: document.getElementById('modalOwnerName')?.value.trim() || null,
      contractor_name: document.getElementById('modalContractorName')?.value.trim() || null,
      architect_engineer: document.getElementById('modalArchitectEngineer')?.value.trim() || null,
      bond_required: document.getElementById('modalBondRequired')?.checked || false,
      tax_exempt: document.getElementById('modalTaxExempt')?.checked || false,
      insurance_requirements: document.getElementById('modalInsuranceRequirements')?.value.trim() || null,
      original_amount: total || parseFloat(document.getElementById('modalAmount').value) || 0,
      allocations: allocs,
    };
  }

  async function saveModal(e) {
    e.preventDefault();
    const id = document.getElementById('modalRecordId').value;
    const payload = readPayload();
    if (!payload.title && !payload.description) {
      alert('Title or description is required.');
      return;
    }
    try {
      const json = id
        ? await api(`/api/commitments/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
        : await api('/api/commitments', { method: 'POST', body: JSON.stringify(payload) });
      if (json.budget_warnings?.length) {
        console.warn('Budget warnings:', json.budget_warnings);
      }
      const saved = json.commitment;
      logCommitmentAudit(id ? 'COMMITMENT_UPDATED' : 'COMMITMENT_CREATED', {
        number: saved?.number,
        type: saved?.commitment_type,
        status: saved?.status,
        amount: saved?.current_amount,
      });
      document.getElementById('comModal').close();
      await refreshAll();
      toast('Commitment saved');
    } catch (err) {
      alert(err.message);
    }
  }

  async function deleteCommitment(id) {
    const c = state.commitments.find(x => x.id === id) || state.drawerRecord;
    if (!c) return;
    if (!canDelete(c)) {
      alert('Only administrators can delete Draft, Rejected, or Void commitments.');
      return;
    }
    if (!confirm(`Permanently delete ${c.number}? This cannot be undone.`)) return;
    try {
      await api(`/api/commitments/${id}`, { method: 'DELETE' });
      logCommitmentAudit('COMMITMENT_DELETED', { number: c.number, type: c.commitment_type });
      closeDrawer();
      await refreshAll();
      toast(`${c.number} deleted`);
    } catch (err) {
      alert(err.message);
    }
  }

  async function workflow(id, action) {
    const c = state.commitments.find(x => x.id === id);
    if (!c) return;
    const verb = action === 'submit' ? 'Submit' : action === 'reject' ? 'Reject' : 'Approve';
    if (!confirm(`${verb} ${c.number}?`)) return;
    try {
      const json = await api(`/api/commitments/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action }) });
      logCommitmentAudit(`COMMITMENT_${action.toUpperCase()}`, { number: c.number, new_status: json.new_status });
      if (json.final_approved && typeof CasePMBudgetSync !== 'undefined') {
        await CasePMBudgetSync.init().catch(() => {});
        await CasePMBudgetSync.loadFromServer().catch(() => {});
      }
      if (json.final_approved && typeof CasePMPayAppSync !== 'undefined') {
        await CasePMPayAppSync.init().catch(() => {});
        await CasePMPayAppSync.loadFromServer().catch(() => {});
      }
      await refreshAll();
      if (state.drawerRecord?.id === id) {
        state.drawerRecord = json.commitment;
        renderDrawer(json.commitment);
      }
      toast(json.final_approved ? `${c.number} approved — synced to budget & SOV` : `${c.number} → ${json.new_status}`);
    } catch (err) {
      alert(err.message);
    }
  }

  async function sendDocuSign(id) {
    if (!confirm('Send this commitment to DocuSign for eSignature? (Requires DocuSign integration configured on server.)')) return;
    try {
      const json = await api(`/api/commitments/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action: 'send_docusign' }) });
      logCommitmentAudit('COMMITMENT_DOCUSIGN_SENT', { number: json.commitment?.number });
      await refreshAll();
      toast(`DocuSign envelope queued: ${json.commitment?.docusign_envelope_id || 'pending'}`);
    } catch (err) {
      alert(err.message);
    }
  }

  async function signInternal(id) {
    if (!confirm('Apply your certified digital signature to this commitment?')) return;
    try {
      await api(`/api/commitments/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action: 'sign_internal' }) });
      logCommitmentAudit('COMMITMENT_SIGNED', { number: state.drawerRecord?.number });
      await refreshAll();
      toast('Signature recorded');
    } catch (err) {
      alert(err.message);
    }
  }

  function closeDrawer() {
    document.getElementById('comDetailDrawer')?.classList.remove('open');
    document.getElementById('comDrawerBackdrop')?.classList.add('hidden');
    state.drawerRecord = null;
  }

  function openDrawer() {
    document.getElementById('comDetailDrawer')?.classList.add('open');
    document.getElementById('comDrawerBackdrop')?.classList.remove('hidden');
  }

  function renderDrawer(c) {
    document.getElementById('drawerTitle').textContent = `${c.number} — ${c.title || c.description}`;
    const allocs = (c.allocations || []).map(a =>
      `<tr class="border-b border-zinc-800"><td class="py-2 font-mono text-xs">${esc(a.cost_code)}</td><td class="py-2">${esc(a.description || '')}</td><td class="py-2 text-right font-mono">${fmt(a.amount)}</td></tr>`
    ).join('');
    const sigs = (c.certified_signatures || []).map(s =>
      `<div class="text-xs text-zinc-400">${esc(s.signed_by_name)} · ${fmtDate(s.signed_at)} · ${esc(s.method)}</div>`
    ).join('') || '<span class="text-zinc-500">No signatures yet</span>';
    document.getElementById('drawerBody').innerHTML = `
      <div class="space-y-2 text-sm">
        <p><span class="text-zinc-500">Type</span><br>${esc(c.commitment_type)} · ${statusBadge(c.status)}</p>
        <p><span class="text-zinc-500">Vendor</span><br>${esc(c.company_name || '—')}</p>
        ${c.contact_name ? `<p><span class="text-zinc-500">Contact</span><br>${esc(c.contact_name)} ${c.contact_email ? `· ${esc(c.contact_email)}` : ''} ${c.contact_phone ? `· ${esc(c.contact_phone)}` : ''}</p>` : ''}
        <p><span class="text-zinc-500">AIA Form</span><br>${esc(c.aia_form)} · ${esc(c.billing_type || 'Lump Sum')} · Retainage ${c.retainage_percent || 0}%</p>
        <p><span class="text-zinc-500">Amount</span><br><span class="font-mono text-lg">${fmt(c.current_amount)}</span></p>
        <p><span class="text-zinc-500">Dates</span><br>Contract ${fmtDate(c.date)}${c.start_date ? ` · Start ${fmtDate(c.start_date)}` : ''}${c.end_date ? ` · End ${fmtDate(c.end_date)}` : ''}${c.delivery_date ? ` · Delivery ${fmtDate(c.delivery_date)}` : ''}</p>
        <p><span class="text-zinc-500">Ball in court</span><br>${esc(c.ball_in_court_role || '—')}</p>
        <p><span class="text-zinc-500">Signature</span><br>${sigBadge(c)} · ${esc(c.signature_method)}</p>
        ${c.docusign_envelope_id ? `<p><span class="text-zinc-500">DocuSign</span><br>${esc(c.docusign_envelope_id)} (${esc(c.docusign_status || '—')})</p>` : ''}
        <p><span class="text-zinc-500">Payment terms</span><br>${esc(c.payment_terms || '—')}${c.freight_terms ? ` · Freight: ${esc(c.freight_terms)}` : ''}</p>
        ${c.owner_name || c.contractor_name ? `<p><span class="text-zinc-500">Parties</span><br>Owner: ${esc(c.owner_name || '—')} · GC: ${esc(c.contractor_name || '—')}${c.architect_engineer ? ` · A/E: ${esc(c.architect_engineer)}` : ''}</p>` : ''}
        ${c.bond_required ? '<p class="text-amber-400 text-xs">Performance & Payment Bond Required</p>' : ''}
        ${c.insurance_requirements ? `<p><span class="text-zinc-500">Insurance</span><br>${esc(c.insurance_requirements)}</p>` : ''}
        <p><span class="text-zinc-500">Scope</span><br>${esc(c.scope_of_work || c.description || '—')}</p>
        <p><span class="text-zinc-500">Sage</span><br>${esc(c.sage_sync_status || '—')}</p>
      </div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Schedule of Values / Allocations</div>
      <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left py-1">Code</th><th class="text-left py-1">Description</th><th class="text-right py-1">Amount</th></tr></thead>
      <tbody>${allocs || '<tr><td colspan="3" class="py-3 text-zinc-500">No allocations</td></tr>'}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Signatures</div>${sigs}</div>`;
    const showSubmit = c.status === 'Draft';
    const showApprove = ['Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner'].includes(c.status) && canActOnBall(c.ball_in_court_role);
    const showDelete = canDelete(c);
    document.getElementById('drawerActions').innerHTML = `
      <button type="button" onclick="CasePMCommitments.printCommitment(${c.id})" class="px-4 py-2 bg-sky-700 hover:bg-sky-600 rounded-md text-sm"><i class="fa-solid fa-print mr-1"></i>Print</button>
      ${showSubmit ? `<button type="button" onclick="CasePMCommitments.workflow(${c.id},'submit')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-md text-sm">Submit</button>` : ''}
      ${showApprove ? `<button type="button" onclick="CasePMCommitments.workflow(${c.id},'approve')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm">Approve</button>
      <button type="button" onclick="CasePMCommitments.workflow(${c.id},'reject')" class="px-4 py-2 bg-zinc-800 text-red-400 rounded-md text-sm">Reject</button>` : ''}
      ${c.status === 'Approved' && c.signature_status !== 'fully_executed' ? `
        <button type="button" onclick="CasePMCommitments.signInternal(${c.id})" class="px-4 py-2 bg-sky-700 hover:bg-sky-600 rounded-md text-sm">Certified Sign</button>
        <button type="button" onclick="CasePMCommitments.sendDocuSign(${c.id})" class="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 rounded-md text-sm"><i class="fa-solid fa-file-signature mr-1"></i>DocuSign</button>` : ''}
      <button type="button" onclick="CasePMCommitments.edit(${c.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>
      ${showDelete ? `<button type="button" onclick="CasePMCommitments.deleteCommitment(${c.id})" class="px-4 py-2 bg-red-900/60 hover:bg-red-800 text-red-300 rounded-md text-sm"><i class="fa-solid fa-trash mr-1"></i>Delete</button>` : ''}`;
    openDrawer();
  }

  async function view(id) {
    const c = await api(`/api/commitments/${id}`);
    state.drawerRecord = c;
    renderDrawer(c);
  }

  function buildPrintStyles() {
    return `
      @page { size: letter; margin: 0.5in; }
      @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
      body { font-family: "Times New Roman", Times, serif; padding: 8px 12px; font-size: 10px; line-height: 1.25; color: #000; }
      .main-header { border: 2px solid #000; padding: 6px 10px; margin-bottom: 8px; }
      .header-top { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #000; padding-bottom: 4px; margin-bottom: 6px; }
      .header-title { font-size: 14px; font-weight: bold; letter-spacing: 0.5px; }
      .header-subtitle { font-size: 11px; font-weight: bold; }
      .info-row { display: flex; margin-bottom: 3px; font-size: 9.5px; }
      .info-label { font-weight: bold; width: 110px; flex-shrink: 0; }
      .info-value { flex: 1; }
      .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 6px 0; }
      .box { border: 1px solid #000; padding: 6px 8px; font-size: 9px; line-height: 1.3; }
      .box-title { font-weight: bold; font-size: 9.5px; margin-bottom: 4px; border-bottom: 1px solid #000; padding-bottom: 2px; }
      table.data { width: 100%; border-collapse: collapse; font-size: 9px; margin: 6px 0; }
      table.data td, table.data th { border: 1px solid #000; padding: 3px 5px; vertical-align: top; }
      .right { text-align: right; font-family: "Courier New", monospace; }
      .bold { font-weight: bold; }
      .section-title { font-weight: bold; font-size: 10px; margin: 8px 0 4px; }
      .cert-text { font-size: 8.5px; margin: 4px 0; line-height: 1.35; text-align: justify; }
      .sig-line { border-top: 1px solid #000; margin-top: 28px; padding-top: 4px; font-size: 8.5px; width: 45%; display: inline-block; margin-right: 4%; }
      .footer-note { font-size: 7px; color: #555; margin-top: 10px; text-align: center; }
    `;
  }

  function sovTableHtml(allocations, total) {
    const rows = (allocations || []).map((a, i) =>
      `<tr><td class="right">${i + 1}</td><td>${esc(a.cost_code)}</td><td>${esc(a.description || '')}</td><td class="right">${fmt(a.amount)}</td></tr>`
    ).join('');
    return `
      <table class="data">
        <thead><tr><th>#</th><th>Cost Code</th><th>Description</th><th class="right">Amount</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4">No line items</td></tr>'}</tbody>
        <tfoot><tr><td colspan="3" class="bold right">CONTRACT SUM</td><td class="right bold">${fmt(total)}</td></tr></tfoot>
      </table>`;
  }

  function buildAiaPrintHtml(c) {
    const ctx = projectCtx();
    const form = c.aia_form || 'N/A';
    const isPO = c.commitment_type === 'Purchase Order' || form === 'N/A';
    const isSub = c.commitment_type === 'Subcontract' || form === 'A401';
    const docTitle = isPO ? 'PURCHASE ORDER' : isSub ? 'AGREEMENT BETWEEN CONTRACTOR AND SUBCONTRACTOR' : 'AGREEMENT';
    const docSubtitle = isPO ? 'PURCHASE ORDER' : `AIA DOCUMENT ${form}`;
    const owner = c.owner_name || ctx.name || '___________________________';
    const contractor = c.contractor_name || 'Case Contracting';
    const project = ctx.name || '—';
    const projectNo = ctx.number || '—';
    const address = ctx.address || '—';
    const total = c.current_amount || c.original_amount || 0;
    const retainPct = c.retainage_percent || 0;

    let articles = '';
    if (isSub || form === 'A401') {
      articles = `
        <div class="section-title">ARTICLE 1 — THE WORK</div>
        <div class="cert-text">Subcontractor shall perform the Work described as: <strong>${esc(c.title || c.description)}</strong>. Scope: ${esc(c.scope_of_work || c.description || '')}</div>
        <div class="section-title">ARTICLE 2 — CONTRACT SUM</div>
        <div class="cert-text">The Contractor shall pay the Subcontractor the Contract Sum of <strong>${fmt(total)}</strong> for performance of the Work (${esc(c.billing_type || 'Lump Sum')}).</div>
        <div class="section-title">ARTICLE 3 — PAYMENT</div>
        <div class="cert-text">Payment terms: ${esc(c.payment_terms || 'Per progress billing')}. Retainage: ${retainPct}%. ${c.bond_required ? 'Performance and Payment Bonds required.' : ''}</div>
        <div class="section-title">ARTICLE 4 — TIME</div>
        <div class="cert-text">Commencement: ${fmtDate(c.start_date || c.date)}. Substantial Completion: ${fmtDate(c.end_date)}. Contract Date: ${fmtDate(c.date)}.</div>
        ${c.insurance_requirements ? `<div class="section-title">ARTICLE 5 — INSURANCE</div><div class="cert-text">${esc(c.insurance_requirements)}</div>` : ''}`;
    } else if (form === 'A101' || form === 'A102') {
      articles = `
        <div class="section-title">ARTICLE 1 — THE WORK</div>
        <div class="cert-text">Contractor shall provide the Work: <strong>${esc(c.title || c.description)}</strong></div>
        <div class="section-title">ARTICLE 2 — CONTRACT SUM</div>
        <div class="cert-text">${form === 'A102' ? 'Cost of the Work plus Contractor\'s Fee' : 'Stipulated Sum'}: <strong>${fmt(total)}</strong> (${esc(c.billing_type || 'Lump Sum')})</div>
        <div class="section-title">ARTICLE 3 — PAYMENT</div>
        <div class="cert-text">${esc(c.payment_terms || 'Per AIA progress billing')}. Retainage ${retainPct}%.</div>`;
    } else {
      articles = `
        <div class="section-title">SCOPE / DESCRIPTION</div>
        <div class="cert-text">${esc(c.scope_of_work || c.description || '')}</div>
        <div class="section-title">AMOUNT</div>
        <div class="cert-text">Total: <strong>${fmt(total)}</strong></div>`;
    }

    return `
      <div class="main-header">
        <div class="header-top">
          <div class="header-title">${docTitle}</div>
          <div class="header-subtitle">${docSubtitle}</div>
          <div style="font-size:8px;text-align:right;">${esc(c.number)}</div>
        </div>
        <div class="two-col">
          <div>
            <div class="info-row"><span class="info-label">PROJECT:</span><span class="info-value">${esc(project)}</span></div>
            <div class="info-row"><span class="info-label">PROJECT NO:</span><span class="info-value">${esc(projectNo)}</span></div>
            <div class="info-row"><span class="info-label">ADDRESS:</span><span class="info-value">${esc(address)}</span></div>
            ${ctx.sage_job ? `<div class="info-row"><span class="info-label">SAGE JOB:</span><span class="info-value">${esc(ctx.sage_job)}</span></div>` : ''}
          </div>
          <div>
            <div class="info-row"><span class="info-label">CONTRACT DATE:</span><span class="info-value">${fmtDate(c.date)}</span></div>
            <div class="info-row"><span class="info-label">TYPE:</span><span class="info-value">${esc(c.commitment_type)}</span></div>
            <div class="info-row"><span class="info-label">STATUS:</span><span class="info-value">${esc(c.status)}</span></div>
            ${c.delivery_date ? `<div class="info-row"><span class="info-label">DELIVERY:</span><span class="info-value">${fmtDate(c.delivery_date)}</span></div>` : ''}
          </div>
        </div>
      </div>
      <div class="two-col">
        <div class="box">
          <div class="box-title">${isPO ? 'VENDOR' : isSub ? 'SUBCONTRACTOR' : 'CONTRACTOR / VENDOR'}</div>
          <strong>${esc(c.company_name || '—')}</strong><br>
          ${c.contact_name ? `Attn: ${esc(c.contact_name)}<br>` : ''}
          ${c.contact_email ? `${esc(c.contact_email)}<br>` : ''}
          ${c.contact_phone ? esc(c.contact_phone) : ''}
        </div>
        <div class="box">
          <div class="box-title">PARTIES</div>
          <div class="info-row"><span class="info-label">OWNER:</span><span>${esc(owner)}</span></div>
          <div class="info-row"><span class="info-label">CONTRACTOR:</span><span>${esc(contractor)}</span></div>
          ${c.architect_engineer ? `<div class="info-row"><span class="info-label">ARCHITECT:</span><span>${esc(c.architect_engineer)}</span></div>` : ''}
        </div>
      </div>
      ${articles}
      <div class="section-title">${isPO ? 'LINE ITEMS' : 'SCHEDULE OF VALUES'}</div>
      ${sovTableHtml(c.allocations, total)}
      ${isPO && c.freight_terms ? `<div class="cert-text">Freight Terms: ${esc(c.freight_terms)}${c.tax_exempt ? ' · TAX EXEMPT' : ''}</div>` : ''}
      <div class="section-title">SIGNATURES</div>
      <div class="cert-text">Signature method: ${esc(c.signature_method || 'internal')}. Status: ${esc((c.signature_status || 'unsigned').replace(/_/g, ' '))}.</div>
      ${(c.certified_signatures || []).map(s => `<div class="cert-text">Signed by ${esc(s.signed_by_name)} on ${fmtDate(s.signed_at)} (${esc(s.method)})</div>`).join('')}
      <div style="margin-top:20px;">
        <div class="sig-line">CONTRACTOR<br><br>Date: _______________</div>
        <div class="sig-line">${isPO ? 'VENDOR' : 'SUBCONTRACTOR'}<br><br>Date: _______________</div>
      </div>
      <div class="footer-note">Generated by Case PM · ${new Date().toLocaleString()} · Form ${esc(form)} · Not an official AIA document unless executed</div>`;
  }

  async function printCommitment(id) {
    let c = state.commitments.find(x => x.id === id);
    if (!c || !c.allocations) {
      try { c = await api(`/api/commitments/${id}`); } catch (err) { alert(err.message); return; }
    }
    const form = c.aia_form || 'N/A';
    const printHTML = `<!DOCTYPE html><html><head><title>${esc(c.number)} — ${esc(form)}</title><style>${buildPrintStyles()}</style></head><body>${buildAiaPrintHtml(c)}</body></html>`;
    const win = window.open('', '_blank', 'width=900,height=700');
    if (!win) { alert('Pop-up blocked. Allow pop-ups to print.'); return; }
    win.document.write(printHTML);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 400);
    logCommitmentAudit('COMMITMENT_PRINTED', { number: c.number, form: c.aia_form });
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-16 right-6 z-[90] px-4 py-2 rounded-md bg-emerald-900 text-emerald-100 text-sm shadow-lg';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2800);
  }

  function exportExcel() {
    if (typeof XLSX === 'undefined') { alert('Excel library not loaded'); return; }
    const data = state.commitments.map(c => ({
      Number: c.number, Type: c.commitment_type, Title: c.title, Vendor: c.company_name,
      AIA: c.aia_form, Original: c.original_amount, Changes: c.approved_changes, Current: c.current_amount,
      Status: c.status, Signature: c.signature_status, Sage: c.sage_sync_status,
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Commitments');
    XLSX.writeFile(wb, `Commitments_${projectId() || 'project'}.xlsx`);
  }

  function bindFilters() {
    const rerender = () => {
      state.filter.search = document.getElementById('comSearch')?.value || '';
      state.filter.status = document.getElementById('comStatusFilter')?.value || '';
      state.filter.type = document.getElementById('comTypeFilter')?.value || '';
      renderTable();
    };
    ['comSearch', 'comStatusFilter', 'comTypeFilter'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', rerender);
    });
    populateSelect('comStatusFilter', [''].concat(STATUSES), '');
    const typeFilter = document.getElementById('comTypeFilter');
    if (typeFilter) {
      typeFilter.innerHTML = '<option value="">All Types</option>' + TYPES.map(t => `<option>${t}</option>`).join('');
    }
  }

  async function refreshAll() {
    await Promise.all([loadDashboard(), loadCommitments(), loadSageLog()]);
  }

  async function init() {
    if (!projectId()) {
      alert('Select a project to manage commitments.');
      return;
    }
    loadAuditLog();
    if (typeof CasePMWorkflow !== 'undefined') await CasePMWorkflow.loadPortal().catch(() => {});
    if (typeof CasePMBudgetSync !== 'undefined') await CasePMBudgetSync.init().catch(() => {});
    if (typeof CasePMPayAppSync !== 'undefined') await CasePMPayAppSync.init().catch(() => {});
    loadCompanies();
    await loadCostCodes();
    bindFilters();
    await refreshAll();
  }

  global.CasePMCommitments = {
    init,
    openModal,
    saveModal,
    newCommitment: () => openModal(null),
    edit: id => api(`/api/commitments/${id}`).then(openModal).catch(e => alert(e.message)),
    view,
    closeDrawer,
    workflow,
    sendDocuSign,
    signInternal,
    deleteCommitment,
    printCommitment,
    onTypeChange,
    openSageSyncLogModal,
    showCommitmentAuditLog,
    addAllocRow: () => { state.allocationRows.push({ cost_code: '', amount: 0, description: '' }); renderAllocationRows(); },
    removeAllocRow: idx => { state.allocationRows.splice(idx, 1); renderAllocationRows(); },
    onCompanyChange,
    exportExcel,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
