/**
 * Case PM — Change Orders & PCO module
 * Procore/RedTeam-style workflow with budget, pay app, and Sage integration.
 */
(function (global) {
  'use strict';

  const CO_STATUSES = ['Draft', 'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect', 'Approved', 'Rejected', 'Void'];
  const PCO_STATUSES = ['Open', 'Pricing', 'Pending Review', 'Approved for CO', 'Promoted', 'Void', 'Closed'];
  const REASONS = ['Owner Request', 'Design Change', 'Unforeseen Condition', 'Code Compliance', 'Error or Omission', 'Value Engineering', 'Schedule Acceleration', 'Other'];
  const PRIORITIES = ['Low', 'Medium', 'High', 'Critical'];
  const CONTRACT_TYPES = ['Owner', 'Contractor', 'Subcontract'];

  let state = {
    tab: 'cos',
    changeOrders: [],
    pcos: [],
    costCodes: [],
    companies: [],
    contacts: [],
    stats: {},
    sageLog: [],
    selectedCo: null,
    selectedPco: null,
    allocationRows: [],
    filter: { search: '', status: '', priority: '' },
    rfis: [],
    commitments: [],
    drawerRecord: null,
    drawerType: null,
  };

  const ROLE_MAP = {
    'Project Manager': ['Project Manager', 'Admin', 'Contractor Accounting'],
    'Architect': ['Architect', 'Admin'],
    'Owner': ['Owner', 'Admin'],
    'Creator': ['Project Manager', 'Admin', 'Company User'],
  };

  function userRole() {
    return (global.CASEPM_PORTAL && global.CASEPM_PORTAL.role) || 'Admin';
  }

  function canActOnBall(role) {
    if (!role) return false;
    if (userRole() === 'Admin') return true;
    return (ROLE_MAP[role] || [role]).includes(userRole());
  }

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    if (typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.projectId) return CasePMWorkflow.projectId();
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
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
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function attachmentHref(parentId, att) {
    return `/uploads/change_orders/${parentId}/${att.filename}`;
  }

  function canApprove() {
    if (typeof CasePMWorkflow !== 'undefined' && global.CASEPM_PORTAL) {
      return CasePMWorkflow.canApprove('Change Orders');
    }
    return true;
  }

  function currentUserName() {
    if (global.CASEPM_PORTAL && global.CASEPM_PORTAL.userName) return global.CASEPM_PORTAL.userName;
    return 'User';
  }

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || json.message || 'Request failed');
    return json;
  }

  function loadCompaniesFromStorage() {
    try {
      state.companies = JSON.parse(localStorage.getItem('casepm_companies') || '[]');
    } catch { state.companies = []; }
    const users = JSON.parse(localStorage.getItem('casepm_users') || localStorage.getItem('users') || '[]');
    state.contacts = Array.isArray(users) ? users : [];
  }

  async function loadCostCodes() {
    const pid = projectId();
    if (!pid) return;
    try {
      const json = await api(`/api/change-orders/cost-codes?project_id=${pid}`);
      state.costCodes = json.cost_codes || [];
    } catch {
      if (typeof CasePMBudgetSync !== 'undefined') {
        await CasePMBudgetSync.init().catch(() => {});
        const lines = JSON.parse(global.casepmStore.getItem('budgetLines') || '[]');
        state.costCodes = lines.map(l => ({ code: l.cost_code, description: l.description, cost_type: l.cost_type }));
      }
    }
  }

  async function loadDashboard() {
    const pid = projectId();
    if (!pid) return;
    state.stats = await api(`/api/change-orders/dashboard?project_id=${pid}`);
    renderSummary();
  }

  async function loadChangeOrders() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/change-orders?project_id=${pid}`);
    state.changeOrders = json.change_orders || [];
    renderCoTable();
  }

  async function loadPcos() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/pcos?project_id=${pid}`);
    state.pcos = json.pcos || [];
    renderPcoTable();
  }

  async function loadLinkOptions() {
    const pid = projectId();
    if (!pid) return;
    try {
      const json = await api(`/api/change-orders/link-options?project_id=${pid}`);
      state.rfis = json.rfis || [];
      state.commitments = json.commitments || [];
    } catch { state.rfis = []; }
    if (!state.commitments?.length) {
      try {
        state.commitments = JSON.parse(localStorage.getItem(`casepm_commitments_p${pid}`) || localStorage.getItem('casepm_commitments') || '[]');
      } catch { state.commitments = []; }
    }
  }

  function populateLinkSelects(record) {
    const rfiSel = document.getElementById('modalLinkedRfi');
    const comSel = document.getElementById('modalLinkedCommitment');
    if (rfiSel) {
      rfiSel.innerHTML = '<option value="">— None —</option>' +
        state.rfis.map(r => `<option value="${r.id}" ${String(record?.linked_rfi_id) === String(r.id) ? 'selected' : ''}>${r.number} — ${r.subject || ''}</option>`).join('');
    }
    if (comSel) {
      comSel.innerHTML = '<option value="">— None —</option>' +
        state.commitments.map((c, i) => {
          const ref = c.number || `COM-${c.id || i + 1}`;
          const label = c.description || c.title || ref;
          return `<option value="${ref}" ${record?.linked_commitment_ref === ref ? 'selected' : ''}>${ref} — ${label}</option>`;
        }).join('');
    }
  }

  async function loadSageLog() {
    const pid = projectId();
    if (!pid) return;
    try {
      const res = await fetch(`/api/sage/sync-events?project_id=${pid}&limit=30`, { credentials: 'same-origin' });
      const json = await res.json();
      state.sageLog = (json.events || []).filter(e =>
        ['ChangeOrderApproved', 'ChangeOrderSubmitted', 'PCOSubmitted', 'PCOPromoted'].includes(e.event_type)
      );
    } catch { state.sageLog = []; }
    renderSageBar();
  }

  function statusBadge(status) {
    const colors = {
      Draft: 'bg-zinc-700 text-zinc-300', Open: 'bg-sky-900/50 text-sky-300', Pricing: 'bg-indigo-900/50 text-indigo-300',
      Submitted: 'bg-amber-900/50 text-amber-300', 'Under Review': 'bg-amber-900/50 text-amber-300',
      'Pending Owner': 'bg-orange-900/50 text-orange-300', 'Pending Architect': 'bg-purple-900/50 text-purple-300',
      'Pending Review': 'bg-amber-900/50 text-amber-300', 'Approved for CO': 'bg-emerald-900/50 text-emerald-300',
      Approved: 'bg-emerald-900/50 text-emerald-400', Rejected: 'bg-red-900/50 text-red-400',
      Promoted: 'bg-zinc-600 text-zinc-200', Void: 'bg-zinc-800 text-zinc-500', Closed: 'bg-zinc-800 text-zinc-500',
    };
    const cls = colors[status] || 'bg-zinc-700 text-zinc-300';
    return `<span class="inline-block px-2 py-0.5 rounded text-[10px] font-medium ${cls}">${status}</span>`;
  }

  function ballBadge(role) {
    if (!role) return '<span class="text-zinc-600">—</span>';
    return `<span class="text-[10px] text-amber-400"><i class="fa-solid fa-user-clock mr-1"></i>${role}</span>`;
  }

  function renderSummary() {
    const s = state.stats;
    const map = {
      statTotalCo: s.total_cos || 0,
      statApproved: s.approved_count || 0,
      statPending: s.pending_count || 0,
      statOpenPco: s.open_pco_count || 0,
      statApprovedTotal: fmt(s.approved_total),
      statPendingTotal: fmt(s.pending_total),
      statPcoRom: fmt(s.pco_rom_total),
      statAvgDays: s.avg_approval_days ? `${s.avg_approval_days} days` : '—',
    };
    Object.keys(map).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
  }

  function filteredCos() {
    const { search, status, priority } = state.filter;
    return state.changeOrders.filter(co => {
      const text = `${co.number} ${co.title} ${co.description} ${co.company_name || ''}`.toLowerCase();
      if (search && !text.includes(search.toLowerCase())) return false;
      if (status && co.status !== status) return false;
      if (priority && co.priority !== priority) return false;
      return true;
    });
  }

  function filteredPcos() {
    const { search, status } = state.filter;
    return state.pcos.filter(p => {
      const text = `${p.number} ${p.title} ${p.description} ${p.company_name || ''}`.toLowerCase();
      if (search && !text.includes(search.toLowerCase())) return false;
      if (status && p.status !== status) return false;
      return true;
    });
  }

  function renderCoTable() {
    const tbody = document.getElementById('coTableBody');
    if (!tbody) return;
    const rows = filteredCos();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="px-6 py-12 text-center text-zinc-500">No change orders found.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(co => {
      const showSubmit = co.status === 'Draft';
      const showApprove = ['Submitted', 'Pending Architect', 'Pending Owner'].includes(co.status) && canActOnBall(co.ball_in_court_role);
      const showReject = showApprove;
      const approveLabel = co.status === 'Pending Owner' ? 'Final Approve' : 'Approve Step';
      return `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" onclick="CasePMChangeOrders.viewCo(${co.id})">
        <td class="px-4 py-3 font-mono text-emerald-400 whitespace-nowrap">${co.number || '—'}</td>
        <td class="px-4 py-3 whitespace-nowrap">${fmtDate(co.date)}</td>
        <td class="px-4 py-3 max-w-[200px] truncate">${co.title || co.description}</td>
        <td class="px-4 py-3 text-xs text-zinc-400">${co.company_name || '—'}</td>
        <td class="px-4 py-3 font-mono text-xs">${co.cost_code || (co.allocations?.[0]?.cost_code) || '—'}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(co.amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(co.status)}</td>
        <td class="px-4 py-3 text-center">${ballBadge(co.ball_in_court_role)}</td>
        <td class="px-4 py-3 text-center text-[10px] ${co.sov_synced_at ? 'text-emerald-400' : 'text-zinc-500'}">${co.sov_synced_at ? 'SOV ✓' : (co.sage_sync_status || '—')}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-1">
            ${showSubmit ? `<button onclick="CasePMChangeOrders.workflowCo(${co.id},'submit')" class="p-1.5 text-amber-400 hover:bg-zinc-800 rounded" title="Submit"><i class="fa-solid fa-paper-plane"></i></button>` : ''}
            ${showApprove ? `<button onclick="CasePMChangeOrders.workflowCo(${co.id},'approve')" class="p-1.5 text-emerald-400 hover:bg-zinc-800 rounded" title="${approveLabel}"><i class="fa-solid fa-check"></i></button>` : ''}
            ${showReject ? `<button onclick="CasePMChangeOrders.workflowCo(${co.id},'reject')" class="p-1.5 text-red-400 hover:bg-zinc-800 rounded" title="Reject"><i class="fa-solid fa-times"></i></button>` : ''}
            <button onclick="CasePMChangeOrders.editCo(${co.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded"><i class="fa-solid fa-edit"></i></button>
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  function renderPcoTable() {
    const tbody = document.getElementById('pcoTableBody');
    if (!tbody) return;
    const rows = filteredPcos();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-12 text-center text-zinc-500">No PCOs yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(p => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" onclick="CasePMChangeOrders.viewPco(${p.id})">
        <td class="px-4 py-3 font-mono text-sky-400 whitespace-nowrap">${p.number}</td>
        <td class="px-4 py-3 max-w-[240px] truncate">${p.title}</td>
        <td class="px-4 py-3 text-xs text-zinc-400">${p.company_name || '—'}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(p.estimated_amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(p.status)}</td>
        <td class="px-4 py-3 text-center">${ballBadge(p.ball_in_court_role)}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-1">
            ${p.status !== 'Promoted' && p.status !== 'Void' ? `<button onclick="CasePMChangeOrders.promotePco(${p.id})" class="p-1.5 text-emerald-400 hover:bg-zinc-800 rounded" title="Promote to CO"><i class="fa-solid fa-arrow-right"></i></button>` : ''}
            ${p.change_order_id ? `<span class="text-[10px] text-emerald-400">→ CO</span>` : ''}
            <button onclick="CasePMChangeOrders.editPco(${p.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded"><i class="fa-solid fa-edit"></i></button>
          </div>
        </td>
      </tr>`).join('');
  }

  function renderSageBar() {
    const el = document.getElementById('coSageStatusText');
    if (!el) return;
    const latest = state.sageLog[0];
    if (!latest) {
      el.textContent = 'Sage 300 PCO/CO · No sync events yet';
      return;
    }
    el.textContent = `Sage 300 · ${latest.event_type} · ${latest.status} · ${new Date(latest.created_at).toLocaleString()}`;
  }

  function switchTab(tab) {
    state.tab = tab;
    document.getElementById('tabCos').classList.toggle('hidden', tab !== 'cos');
    document.getElementById('tabPcos').classList.toggle('hidden', tab !== 'pcos');
    document.getElementById('btnTabCos').className = tab === 'cos'
      ? 'px-4 py-2 rounded-md text-sm font-medium bg-emerald-600 text-white'
      : 'px-4 py-2 rounded-md text-sm font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
    document.getElementById('btnTabPcos').className = tab === 'pcos'
      ? 'px-4 py-2 rounded-md text-sm font-medium bg-emerald-600 text-white'
      : 'px-4 py-2 rounded-md text-sm font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
  }

  function populateSelect(id, options, selected) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = options.map(o => {
      const val = typeof o === 'string' ? o : o.value;
      const label = typeof o === 'string' ? o : o.label;
      return `<option value="${val}" ${val === selected ? 'selected' : ''}>${label}</option>`;
    }).join('');
  }

  function populateCompanySelect(selectedId) {
    const el = document.getElementById('modalCompany');
    if (!el) return;
    el.innerHTML = '<option value="">— Select Company —</option>' +
      state.companies.map(c => {
        const name = c.company_name || c.name || '';
        const id = c.id || name;
        return `<option value="${id}" data-name="${name.replace(/"/g, '')}" ${String(id) === String(selectedId) ? 'selected' : ''}>${name}</option>`;
      }).join('');
  }

  function onCompanyChange() {
    const sel = document.getElementById('modalCompany');
    const contactSel = document.getElementById('modalContact');
    if (!sel || !contactSel) return;
    const companyName = sel.options[sel.selectedIndex]?.dataset?.name || sel.options[sel.selectedIndex]?.text || '';
    const contacts = state.contacts.filter(u => {
      const cn = u.company || u.company_name || '';
      return cn && companyName && cn.toLowerCase() === companyName.toLowerCase();
    });
    contactSel.innerHTML = '<option value="">— Select Contact —</option>' +
      contacts.map(u => {
        const name = `${u.firstName || u.first_name || ''} ${u.lastName || u.last_name || ''}`.trim() || u.email;
        return `<option value="${name}" data-email="${u.email || ''}" data-phone="${(u.phones && u.phones[0] && u.phones[0].number) || ''}">${name}</option>`;
      }).join('');
  }

  function onContactChange() {
    const sel = document.getElementById('modalContact');
    if (!sel || sel.selectedIndex < 0) return;
    const opt = sel.options[sel.selectedIndex];
    const emailEl = document.getElementById('modalContactEmail');
    const phoneEl = document.getElementById('modalContactPhone');
    if (emailEl) emailEl.value = opt.dataset.email || '';
    if (phoneEl) phoneEl.value = opt.dataset.phone || '';
  }

  function renderAllocationRows() {
    const container = document.getElementById('allocationRows');
    if (!container) return;
    if (!state.allocationRows.length) {
      state.allocationRows = [{ cost_code: '', amount: 0, description: '' }];
    }
    container.innerHTML = state.allocationRows.map((row, idx) => `
      <div class="grid grid-cols-12 gap-2 items-center mb-2">
        <div class="col-span-4">
          <select class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs alloc-cost-code" data-idx="${idx}">
            <option value="">Cost code…</option>
            ${state.costCodes.map(c => `<option value="${c.code}" ${c.code === row.cost_code ? 'selected' : ''}>${c.code} — ${c.description || ''}</option>`).join('')}
          </select>
        </div>
        <div class="col-span-3"><input type="text" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs alloc-desc" data-idx="${idx}" value="${row.description || ''}" placeholder="Description"></div>
        <div class="col-span-3"><input type="number" step="0.01" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-xs text-right alloc-amt" data-idx="${idx}" value="${row.amount || 0}"></div>
        <div class="col-span-2 flex gap-1">
          <button type="button" onclick="CasePMChangeOrders.addAllocRow()" class="px-2 py-1 text-xs bg-zinc-700 rounded">+</button>
          ${state.allocationRows.length > 1 ? `<button type="button" onclick="CasePMChangeOrders.removeAllocRow(${idx})" class="px-2 py-1 text-xs bg-red-900/50 text-red-400 rounded">×</button>` : ''}
        </div>
      </div>`).join('');
  }

  function readAllocationsFromDom() {
    const rows = [];
    document.querySelectorAll('.alloc-cost-code').forEach((sel, idx) => {
      const code = sel.value;
      const desc = document.querySelector(`.alloc-desc[data-idx="${idx}"]`)?.value || '';
      const amt = parseFloat(document.querySelector(`.alloc-amt[data-idx="${idx}"]`)?.value) || 0;
      if (code || amt) rows.push({ cost_code: code, amount: amt, description: desc });
    });
    return rows;
  }

  function readModalPayload(type) {
    const companySel = document.getElementById('modalCompany');
    const companyName = companySel?.options[companySel.selectedIndex]?.dataset?.name || '';
    const allocs = readAllocationsFromDom();
    const total = allocs.reduce((s, a) => s + (a.amount || 0), 0);
    const base = {
      project_id: projectId(),
      title: document.getElementById('modalTitle')?.value?.trim(),
      description: document.getElementById('modalDescription')?.value?.trim(),
      reason: document.getElementById('modalReason')?.value,
      priority: document.getElementById('modalPriority')?.value,
      schedule_impact_days: parseInt(document.getElementById('modalScheduleDays')?.value, 10) || 0,
      company_id: companySel?.value || null,
      company_name: companyName,
      contact_name: document.getElementById('modalContact')?.value,
      contact_email: document.getElementById('modalContactEmail')?.value,
      contact_phone: document.getElementById('modalContactPhone')?.value,
      requested_by: document.getElementById('modalRequestedBy')?.value || currentUserName(),
      notes: document.getElementById('modalNotes')?.value,
      contract_type: document.getElementById('modalContractType')?.value,
      linked_rfi_id: document.getElementById('modalLinkedRfi')?.value || null,
      linked_commitment_ref: document.getElementById('modalLinkedCommitment')?.value || null,
      allocations: allocs,
    };
    if (type === 'pco') {
      return { ...base, estimated_amount: total || parseFloat(document.getElementById('modalAmount')?.value) || 0, status: document.getElementById('modalStatus')?.value || 'Open' };
    }
    return { ...base, amount: total || parseFloat(document.getElementById('modalAmount')?.value) || 0, status: document.getElementById('modalStatus')?.value || 'Draft', date: document.getElementById('modalDate')?.value };
  }

  function renderModalAttachmentList(record, mode) {
    const el = document.getElementById('modalAttachmentList');
    const input = document.getElementById('modalAttachmentInput');
    if (input) input.value = '';
    if (!el) return;
    const atts = (record && record.attachments) || [];
    if (mode !== 'co' || !atts.length) {
      el.innerHTML = '<span class="text-zinc-500">No files yet — save first, then upload on edit</span>';
      return;
    }
    el.innerHTML = atts.map(a =>
      `<a href="${attachmentHref(record.id, a)}" target="_blank" rel="noopener" class="text-emerald-400 hover:underline">${esc(a.original_name || a.filename)}</a>`
    ).join(' · ');
  }

  async function uploadModalAttachments(coId) {
    const input = document.getElementById('modalAttachmentInput');
    if (!input?.files?.length) return;
    for (const file of input.files) {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`/api/change-orders/${coId}/attachments`, { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || 'Attachment upload failed');
    }
  }

  function openModal(mode, record) {
    const modal = document.getElementById('coModal');
    const isPco = mode === 'pco';
    document.getElementById('modalMode').value = mode;
    document.getElementById('modalRecordId').value = record?.id || '';
    document.getElementById('coModalHeading').textContent = record
      ? (isPco ? `Edit PCO ${record.number}` : `Edit ${record.number}`)
      : (isPco ? 'New Potential Change Order (PCO)' : 'New Change Order');
    document.getElementById('modalDateRow').classList.toggle('hidden', isPco);
    document.getElementById('modalContractTypeRow').classList.toggle('hidden', isPco);
    populateSelect('modalStatus', isPco ? PCO_STATUSES : CO_STATUSES, record?.status || (isPco ? 'Open' : 'Draft'));
    populateSelect('modalReason', [''].concat(REASONS), record?.reason || '');
    populateSelect('modalPriority', PRIORITIES, record?.priority || 'Medium');
    populateSelect('modalContractType', CONTRACT_TYPES, record?.contract_type || 'Owner');
    populateCompanySelect(record?.company_id);
    document.getElementById('modalTitle').value = record?.title || '';
    document.getElementById('modalDescription').value = record?.description || '';
    document.getElementById('modalAmount').value = record ? (isPco ? record.estimated_amount : record.amount) : '';
    document.getElementById('modalScheduleDays').value = record?.schedule_impact_days || 0;
    document.getElementById('modalRequestedBy').value = record?.requested_by || currentUserName();
    document.getElementById('modalNotes').value = record?.notes || '';
    document.getElementById('modalDate').value = record?.date ? record.date.split('T')[0] : new Date().toISOString().split('T')[0];
    document.getElementById('modalContactEmail').value = record?.contact_email || '';
    document.getElementById('modalContactPhone').value = record?.contact_phone || '';
    state.allocationRows = (record?.allocations && record.allocations.length)
      ? record.allocations.map(a => ({ ...a }))
      : [{ cost_code: record?.cost_code || '', amount: record?.amount || record?.estimated_amount || 0, description: '' }];
    onCompanyChange();
    if (record?.contact_name) {
      const csel = document.getElementById('modalContact');
      if (csel) csel.value = record.contact_name;
    }
    populateLinkSelects(record);
    renderModalAttachmentList(record, mode);
    renderAllocationRows();
    modal.showModal();
  }

  async function saveModal(e) {
    e.preventDefault();
    const mode = document.getElementById('modalMode').value;
    const id = document.getElementById('modalRecordId').value;
    const payload = readModalPayload(mode);
    if (!payload.title && !payload.description) {
      alert('Title or description is required.');
      return;
    }
    try {
      if (mode === 'pco') {
        const json = id
          ? await api(`/api/pcos/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
          : await api('/api/pcos', { method: 'POST', body: JSON.stringify(payload) });
        await loadPcos();
        await loadDashboard();
      } else {
        const json = id
          ? await api(`/api/change-orders/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
          : await api('/api/change-orders', { method: 'POST', body: JSON.stringify(payload) });
        const coId = id || json.change_order?.id;
        if (coId) await uploadModalAttachments(coId);
        await loadChangeOrders();
        await loadDashboard();
      }
      document.getElementById('coModal').close();
      toast('Saved successfully');
    } catch (err) {
      alert(err.message);
    }
  }

  async function applyCoSync(json) {
    if (json.sync_result && typeof CasePMPayAppSync !== 'undefined') {
      CasePMPayAppSync.applyCoSyncResult(json.sync_result);
    }
    if (json.budget_sync_result && typeof CasePMBudgetSync !== 'undefined') {
      CasePMBudgetSync.applyBudgetSyncResult(json.budget_sync_result);
    }
    global.dispatchEvent(new CustomEvent('casepm:co-approved', { detail: json }));
  }

  async function workflowCo(id, action) {
    const co = state.changeOrders.find(c => c.id === id);
    if (!co) return;
    const verb = action === 'submit' ? 'Submit' : action === 'reject' ? 'Reject' : 'Approve';
    const extra = action === 'approve' && co.status === 'Pending Owner'
      ? ' Final approval will sync to Budget, SOV, Schedule, and Sage 300.'
      : '';
    if (!confirm(`${verb} ${co.number}?${extra}`)) return;
    try {
      const json = await api(`/api/change-orders/${id}/workflow`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      if (json.final_approved) {
        await applyCoSync(json);
      }
      if (action === 'submit' && typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.onChangeOrderSubmitted) {
        await CasePMWorkflow.onChangeOrderSubmitted(json.change_order || co).catch(() => {});
      }
      await loadChangeOrders();
      await loadDashboard();
      await loadSageLog();
      if (state.drawerRecord && state.drawerRecord.id === id && json.change_order) {
        state.drawerRecord = json.change_order;
        renderDrawerCo(json.change_order);
      }
      const applied = json.sync_result?.sov_amount_applied;
      const msg = json.final_approved
        ? (applied != null ? `Approved — $${Number(applied).toLocaleString()} synced to SOV & budget` : 'Approved and synced')
        : `${co.number} — ${json.new_status}${json.ball_in_court_role ? ` · ball: ${json.ball_in_court_role}` : ''}`;
      toast(msg);
    } catch (err) {
      alert(err.message);
    }
  }

  function openDrawer() {
    document.getElementById('coDetailDrawer')?.classList.add('open');
    const backdrop = document.getElementById('coDrawerBackdrop');
    if (backdrop) backdrop.classList.remove('hidden');
  }

  function closeDrawer() {
    document.getElementById('coDetailDrawer')?.classList.remove('open');
    const backdrop = document.getElementById('coDrawerBackdrop');
    if (backdrop) backdrop.classList.add('hidden');
    state.drawerRecord = null;
    state.drawerType = null;
  }

  function linkedRfiLabel(rfiId) {
    if (!rfiId) return '—';
    const r = state.rfis.find(x => String(x.id) === String(rfiId));
    return r ? `${r.number} — ${r.subject || ''}` : `RFI #${rfiId}`;
  }

  function renderDrawerCo(co) {
    document.getElementById('drawerTitle').textContent = `${co.number} — ${co.title || 'Change Order'}`;
    const allocs = (co.allocations || []).map(a =>
      `<tr class="border-b border-zinc-800"><td class="py-2 font-mono text-xs">${esc(a.cost_code)}</td><td class="py-2">${esc(a.description || '')}</td><td class="py-2 text-right font-mono">${fmt(a.amount)}</td></tr>`
    ).join('');
    const atts = (co.attachments || []).map(a =>
      `<a href="${attachmentHref(co.id, a)}" target="_blank" rel="noopener" class="text-emerald-400 hover:underline">${esc(a.original_name || a.filename)}</a>`
    ).join(' · ') || '—';
    document.getElementById('drawerBody').innerHTML = `
      <div class="space-y-2">
        <p><span class="text-zinc-500">Status</span><br>${statusBadge(co.status)}</p>
        <p><span class="text-zinc-500">Ball in court</span><br>${ballBadge(co.ball_in_court_role)}</p>
        <p><span class="text-zinc-500">Amount</span><br><span class="font-mono text-lg">${fmt(co.amount)}</span></p>
        <p><span class="text-zinc-500">Schedule impact</span><br>${co.schedule_impact_days || 0} days</p>
        <p><span class="text-zinc-500">Company</span><br>${esc(co.company_name || '—')}</p>
        <p><span class="text-zinc-500">Contact</span><br>${esc(co.contact_name || '—')}</p>
        <p><span class="text-zinc-500">Reason</span><br>${esc(co.reason || '—')}</p>
        <p><span class="text-zinc-500">Description</span><br>${esc(co.description || '—')}</p>
        ${co.source_pco_id ? `<p><span class="text-zinc-500">Source PCO</span><br>#${co.source_pco_id}</p>` : ''}
        <p><span class="text-zinc-500">Linked RFI</span><br>${esc(linkedRfiLabel(co.linked_rfi_id))}</p>
        <p><span class="text-zinc-500">Linked commitment</span><br>${esc(co.linked_commitment_ref || '—')}</p>
        <p><span class="text-zinc-500">Sage / SOV</span><br>${co.sov_synced_at ? '<span class="text-emerald-400">SOV synced</span>' : esc(co.sage_sync_status || '—')}</p>
      </div>
      <div class="mt-4">
        <div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Cost code allocations</div>
        <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left py-1">Code</th><th class="text-left py-1">Description</th><th class="text-right py-1">Amount</th></tr></thead>
        <tbody>${allocs || '<tr><td colspan="3" class="py-3 text-zinc-500">No allocations</td></tr>'}</tbody></table>
      </div>
      <div class="mt-4">
        <div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Attachments</div>
        <p>${atts}</p>
      </div>`;
    const showSubmit = co.status === 'Draft';
    const showApprove = ['Submitted', 'Pending Architect', 'Pending Owner'].includes(co.status) && canActOnBall(co.ball_in_court_role);
    document.getElementById('drawerActions').innerHTML = `
      ${showSubmit ? `<button type="button" onclick="CasePMChangeOrders.workflowCo(${co.id},'submit')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-md text-sm">Submit</button>` : ''}
      ${showApprove ? `<button type="button" onclick="CasePMChangeOrders.workflowCo(${co.id},'approve')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm">Approve</button>
      <button type="button" onclick="CasePMChangeOrders.workflowCo(${co.id},'reject')" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm text-red-400">Reject</button>` : ''}
      <button type="button" onclick="CasePMChangeOrders.editCo(${co.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>`;
    openDrawer();
  }

  function renderDrawerPco(p) {
    document.getElementById('drawerTitle').textContent = `${p.number} — ${p.title || 'PCO'}`;
    const allocs = (p.allocations || []).map(a =>
      `<tr class="border-b border-zinc-800"><td class="py-2 font-mono text-xs">${esc(a.cost_code)}</td><td class="py-2">${esc(a.description || '')}</td><td class="py-2 text-right font-mono">${fmt(a.amount)}</td></tr>`
    ).join('');
    document.getElementById('drawerBody').innerHTML = `
      <div class="space-y-2">
        <p><span class="text-zinc-500">Status</span><br>${statusBadge(p.status)}</p>
        <p><span class="text-zinc-500">ROM</span><br><span class="font-mono text-lg">${fmt(p.estimated_amount)}</span></p>
        <p><span class="text-zinc-500">Company</span><br>${esc(p.company_name || '—')}</p>
        <p><span class="text-zinc-500">Contact</span><br>${esc(p.contact_name || '—')}</p>
        <p><span class="text-zinc-500">Description</span><br>${esc(p.description || '—')}</p>
        ${p.change_order_id ? `<p><span class="text-zinc-500">Promoted to CO</span><br>#${p.change_order_id}</p>` : ''}
      </div>
      <div class="mt-4">
        <div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Allocations</div>
        <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left py-1">Code</th><th class="text-left py-1">Description</th><th class="text-right py-1">Amount</th></tr></thead>
        <tbody>${allocs || '<tr><td colspan="3" class="py-3 text-zinc-500">No allocations</td></tr>'}</tbody></table>
      </div>`;
    document.getElementById('drawerActions').innerHTML = `
      ${p.status !== 'Promoted' && p.status !== 'Void' ? `<button type="button" onclick="CasePMChangeOrders.promotePco(${p.id})" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm">Promote to CO</button>` : ''}
      <button type="button" onclick="CasePMChangeOrders.editPco(${p.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>`;
    openDrawer();
  }

  async function promotePco(id) {
    const p = state.pcos.find(x => x.id === id);
    if (!p) return;
    if (!confirm(`Promote PCO ${p.number} to a formal Change Order?`)) return;
    try {
      const json = await api(`/api/pcos/${id}/promote`, { method: 'POST', body: '{}' });
      await loadPcos();
      await loadChangeOrders();
      await loadDashboard();
      await loadSageLog();
      toast(`Promoted to ${json.change_order?.number}`);
      switchTab('cos');
    } catch (err) { alert(err.message); }
  }

  async function viewCo(id) {
    try {
      const co = await api(`/api/change-orders/${id}`);
      state.drawerRecord = co;
      state.drawerType = 'co';
      renderDrawerCo(co);
    } catch (err) {
      alert(err.message);
    }
  }

  async function viewPco(id) {
    try {
      const p = await api(`/api/pcos/${id}`);
      state.drawerRecord = p;
      state.drawerType = 'pco';
      renderDrawerPco(p);
    } catch (err) {
      alert(err.message);
    }
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-16 right-6 z-[70] px-4 py-2 rounded-md bg-emerald-900 text-emerald-100 text-sm shadow-lg';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2800);
  }

  const CO_PRINT_FIELDS = [
    { key: 'number', label: 'CO #', default: true },
    { key: 'date', label: 'Date', default: true },
    { key: 'title', label: 'Title', default: true },
    { key: 'description', label: 'Description', default: false },
    { key: 'company_name', label: 'Company', default: true },
    { key: 'contact_name', label: 'Contact', default: true },
    { key: 'cost_code', label: 'Cost Code', default: true },
    { key: 'amount', label: 'Amount', default: true },
    { key: 'status', label: 'Status', default: true },
    { key: 'ball_in_court_role', label: 'Ball in Court', default: true },
    { key: 'schedule_impact_days', label: 'Schedule Days', default: false },
    { key: 'reason', label: 'Reason', default: false },
    { key: 'priority', label: 'Priority', default: false },
    { key: 'contract_type', label: 'Contract Type', default: false },
    { key: 'sage_sync_status', label: 'Sage Sync', default: false },
    { key: 'sov_synced_at', label: 'SOV Synced', default: false },
    { key: 'notes', label: 'Notes', default: false },
  ];

  const PCO_PRINT_FIELDS = [
    { key: 'number', label: 'PCO #', default: true },
    { key: 'title', label: 'Title', default: true },
    { key: 'company_name', label: 'Company', default: true },
    { key: 'contact_name', label: 'Contact', default: true },
    { key: 'estimated_amount', label: 'ROM', default: true },
    { key: 'status', label: 'Status', default: true },
    { key: 'ball_in_court_role', label: 'Ball in Court', default: true },
    { key: 'reason', label: 'Reason', default: false },
    { key: 'priority', label: 'Priority', default: false },
    { key: 'date', label: 'Date', default: true },
    { key: 'notes', label: 'Notes', default: false },
    { key: 'change_order_id', label: 'Linked CO', default: false },
  ];

  function coPrintValue(co, key) {
    if (key === 'date') return fmtDate(co.date);
    if (key === 'amount') return fmt(co.amount);
    if (key === 'cost_code') return co.cost_code || (co.allocations?.[0]?.cost_code) || '';
    if (key === 'sov_synced_at') return co.sov_synced_at ? 'Yes' : 'No';
    return co[key] ?? '';
  }

  function pcoPrintValue(pco, key) {
    if (key === 'estimated_amount') return fmt(pco.estimated_amount);
    if (key === 'date') return fmtDate(pco.date);
    if (key === 'change_order_id') return pco.change_order_id ? `CO ${pco.change_order_id}` : '';
    return pco[key] ?? '';
  }

  function getCoPrintMeta() {
    const nameEl = document.getElementById('currentProjectName');
    return {
      name: (nameEl?.textContent || '').trim() || 'Project',
      number: projectId() || '',
      location: '',
    };
  }

  function buildLogSection(title, fieldDefs, selectedKeys, rows, valueFn) {
    const columns = selectedKeys.map(k => {
      const def = fieldDefs.find(f => f.key === k);
      return { key: k, label: def?.label || k };
    });
    const data = rows.map(r => {
      const obj = {};
      selectedKeys.forEach(k => { obj[k] = valueFn(r, k); });
      return obj;
    });
    return { title, columns, rows: data, emptyMessage: `No ${title.toLowerCase()} records.` };
  }

  async function printLog() {
    if (typeof global.CasePMPrint === 'undefined') {
      alert('Print module not loaded.');
      return;
    }
    const allFields = [...CO_PRINT_FIELDS];
    PCO_PRINT_FIELDS.forEach(f => {
      if (!allFields.find(x => x.key === f.key)) allFields.push(f);
    });
    const uniqueFields = [];
    const seen = new Set();
    [...CO_PRINT_FIELDS, ...PCO_PRINT_FIELDS].forEach(f => {
      if (!seen.has(f.key)) { seen.add(f.key); uniqueFields.push(f); }
    });

    const picked = await global.CasePMPrint.showFieldPicker({
      title: 'Print Change Order Log',
      logTypes: [
        { value: 'cos', label: 'Change Orders' },
        { value: 'pcos', label: 'PCO Log' },
        { value: 'both', label: 'Both' },
      ],
      fields: uniqueFields,
    });
    if (!picked) return;

    const meta = getCoPrintMeta();
    const sections = [];
    if (picked.logType === 'cos' || picked.logType === 'both') {
      sections.push(buildLogSection('CHANGE ORDER LOG', CO_PRINT_FIELDS, picked.fields, filteredCos(), coPrintValue));
    }
    if (picked.logType === 'pcos' || picked.logType === 'both') {
      sections.push(buildLogSection('POTENTIAL CHANGE ORDER LOG', PCO_PRINT_FIELDS, picked.fields, filteredPcos(), pcoPrintValue));
    }

    const html = global.CasePMPrint.buildPrintDocument({ meta, sections, rowsPerPage: 26 });
    global.CasePMPrint.openPrintWindow(html, 'Change Order Log');
  }

  function exportExcel() {
    if (typeof XLSX === 'undefined') { alert('Excel library not loaded'); return; }
    const data = state.changeOrders.map(co => ({
      Number: co.number, Date: co.date, Title: co.title, Company: co.company_name,
      Amount: co.amount, Status: co.status, 'Ball In Court': co.ball_in_court_role,
      'Schedule Days': co.schedule_impact_days, 'SOV Synced': co.sov_synced_at ? 'Yes' : 'No',
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Change Orders');
    XLSX.writeFile(wb, `Change_Orders_${projectId() || 'project'}.xlsx`);
  }

  function openSageLog() {
    let modal = document.getElementById('coSageLogModal');
    if (!modal) {
      modal = document.createElement('dialog');
      modal.id = 'coSageLogModal';
      modal.className = 'bg-zinc-900 border border-zinc-700 rounded-lg p-0 text-white max-w-2xl w-full';
      document.body.appendChild(modal);
    }
    const rows = state.sageLog.length ? state.sageLog.map(e => `
      <tr class="border-b border-zinc-800"><td class="py-2 text-[10px] text-zinc-400">${new Date(e.created_at).toLocaleString()}</td>
      <td class="py-2 text-xs">${e.event_type}</td><td class="py-2 text-xs text-emerald-400">${e.status}</td>
      <td class="py-2 text-xs">${e.message || ''}</td></tr>`).join('')
      : '<tr><td colspan="4" class="py-6 text-center text-zinc-500">No events</td></tr>';
    modal.innerHTML = `<div class="p-5"><div class="flex justify-between mb-4"><h3 class="font-semibold">Sage 300 PCO/CO Log</h3>
      <button onclick="document.getElementById('coSageLogModal').close()"><i class="fa-solid fa-times"></i></button></div>
      <table class="w-full text-left text-sm"><thead><tr class="text-[10px] text-zinc-500"><th>Time</th><th>Event</th><th>Status</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    modal.showModal();
  }

  function bindFilters() {
    const search = document.getElementById('coSearch');
    const status = document.getElementById('coStatusFilter');
    const priority = document.getElementById('coPriorityFilter');
    const rerender = () => {
      state.filter.search = search?.value || '';
      state.filter.status = status?.value || '';
      state.filter.priority = priority?.value || '';
      renderCoTable();
      renderPcoTable();
    };
    if (search) search.addEventListener('input', rerender);
    if (status) status.addEventListener('change', rerender);
    if (priority) priority.addEventListener('change', rerender);
  }

  async function init() {
    if (!projectId()) {
      alert('Select a project to manage change orders.');
      return;
    }
    if (typeof CasePMWorkflow !== 'undefined') await CasePMWorkflow.loadPortal().catch(() => {});
    if (typeof CasePMBudgetSync !== 'undefined') await CasePMBudgetSync.init().catch(() => {});
    if (typeof CasePMPayAppSync !== 'undefined') await CasePMPayAppSync.init().catch(() => {});
    loadCompaniesFromStorage();
    await loadCostCodes();
    await Promise.all([loadLinkOptions(), loadDashboard(), loadChangeOrders(), loadPcos(), loadSageLog()]);
    bindFilters();
    switchTab('cos');
    global.addEventListener('casepm:co-approved', () => {
      loadChangeOrders();
      loadDashboard();
    });
  }

  global.CasePMChangeOrders = {
    init,
    switchTab,
    openModal,
    saveModal,
    editCo: id => api(`/api/change-orders/${id}`).then(openModal.bind(null, 'co')).catch(e => alert(e.message)),
    editPco: id => api(`/api/pcos/${id}`).then(openModal.bind(null, 'pco')).catch(e => alert(e.message)),
    viewCo, viewPco, workflowCo, closeDrawer, promotePco,
    addAllocRow: () => { state.allocationRows.push({ cost_code: '', amount: 0, description: '' }); renderAllocationRows(); },
    removeAllocRow: idx => { state.allocationRows.splice(idx, 1); renderAllocationRows(); },
    onCompanyChange, onContactChange, exportExcel, printLog, openSageLog,
    newPco: () => openModal('pco', null),
    newCo: () => openModal('co', null),
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
