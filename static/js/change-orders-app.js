/**
 * Case PM — Change Orders & PCO module
 * Workflow with budget, pay app, and Sage integration.
 */
(function (global) {
  'use strict';

  function readMoney(id) {
    const el = document.getElementById(id);
    if (!el) return 0;
    if (global.CasePMMoney) {
      const n = CasePMMoney.readMoneyInput(el);
      return n == null ? 0 : n;
    }
    return parseFloat(el.value) || 0;
  }

  function setMoney(id, amount) {
    const el = document.getElementById(id);
    if (!el) return;
    if (global.CasePMMoney) CasePMMoney.setMoneyInput(el, amount);
    else el.value = amount || '';
  }

  function openDialog(el) {
    if (!el) return;
    if (global.CasePMDialog?.open) global.CasePMDialog.open(el);
    else el.showModal();
  }

  async function coPrompt(message, defaultValue = '', options = {}) {
    if (global.CasePMDialog?.prompt) return global.CasePMDialog.prompt(message, defaultValue, options);
    return prompt(message, defaultValue);
  }

  async function coConfirm(message, options = {}) {
    if (global.CasePMDialog?.confirm) return global.CasePMDialog.confirm(message, options);
    return confirm(message);
  }

  const CO_STATUSES = ['Draft', 'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect', 'Pending Accounting', 'Approved', 'Rejected', 'Void'];
  const SUB_CO_STATUSES = ['Draft', 'Submitted', 'Under Review', 'Pending Accounting', 'Approved', 'Rejected', 'Void'];
  const CO_EDITABLE_STATUSES = ['Draft', 'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect', 'Pending Accounting', 'Rejected', 'Void'];
  const PCO_STATUSES = ['Open', 'Pricing', 'Pending Review', 'Approved for CO', 'Promoted', 'Void', 'Closed'];
  const REASONS = ['Owner Request', 'Design Change', 'Unforeseen Condition', 'Code Compliance', 'Error or Omission', 'Value Engineering', 'Schedule Acceleration', 'Other'];
  const PRIORITIES = ['Low', 'Medium', 'High', 'Critical'];
  const CONTRACT_TYPES = ['Owner', 'Contractor', 'Subcontract'];
  const SUB_CO_KINDS = ['Contract Add', 'Budget Transfer', 'Owner CO Backcharge'];

  const DEFAULT_COST_TYPES = ['Labor', 'Material', 'Subcontract', 'Equipment', 'General Conditions', 'Other'];

  let state = {
    tab: 'cos',
    changeOrders: [],
    pcos: [],
    costCodes: [],
    costTypes: DEFAULT_COST_TYPES.slice(),
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
    ownerChangeOrders: [],
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
    const roleName = userRole();
    if (roleName === 'Admin' || roleName === 'Developer') return true;
    return (ROLE_MAP[role] || [role]).includes(roleName);
  }

  function coApprovableStatuses(co) {
    return isSubCo(co)
      ? subCoApproveStatuses()
      : ['Submitted', 'Pending Architect', 'Pending Owner', 'Pending Accounting'];
  }

  function coNeedsReview(co) {
    if (!co) return false;
    return coApprovableStatuses(co).includes(co.status) && canActOnBall(co.ball_in_court_role);
  }

  function pcoNeedsReview(p) {
    if (!p) return false;
    return ['Pricing', 'Pending Review'].includes(p.status) && canActOnBall(p.ball_in_court_role);
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

  function attachmentHref(parentId, att, kind) {
    if (att.document_id || att.linked_from_documents) {
      return `/api/documents/${att.document_id}/download`;
    }
    const folder = kind === 'pco' ? `pco_${parentId}` : String(parentId);
    return `/uploads/change_orders/${folder}/${att.filename}`;
  }

  function attachmentLabel(att) {
    const name = esc(att.original_name || att.filename || 'File');
    if (att.linked_from_documents || att.document_id) {
      return `${name} <span class="text-zinc-500">(Documents)</span>`;
    }
    return name;
  }

  function canApprove() {
    if (typeof CasePMWorkflow !== 'undefined' && global.CASEPM_PORTAL) {
      return CasePMWorkflow.canApprove('Change Orders');
    }
    return true;
  }

  function devUnlock() {
    return typeof CasePMDeveloperUnlock !== 'undefined' && CasePMDeveloperUnlock.isActive();
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
      state.costTypes = json.cost_types?.length ? json.cost_types : DEFAULT_COST_TYPES.slice();
    } catch {
      if (typeof CasePMBudgetSync !== 'undefined') {
        await CasePMBudgetSync.init().catch(() => {});
        const lines = JSON.parse(global.casepmStore.getItem('budgetLines') || '[]');
        state.costCodes = lines.map(l => ({ code: l.cost_code, description: l.description, cost_type: l.cost_type }));
        state.costTypes = JSON.parse(global.casepmStore.getItem('costTypes') || 'null') || DEFAULT_COST_TYPES.slice();
      }
    }
  }

  function lookupCostCodeMeta(code) {
    if (!code) return null;
    const norm = String(code).replace(/[\s-]/g, '').toUpperCase();
    return state.costCodes.find(c => String(c.code).replace(/[\s-]/g, '').toUpperCase() === norm) || null;
  }

  function isSubCo(record) {
    return record && (record.is_subcontract || record.contract_type === 'Subcontract' || record.contract_type === 'Subcontractor' || String(record.number || '').startsWith('SCO-'));
  }

  function ownerCos() {
    return state.changeOrders.filter(co => !isSubCo(co));
  }

  function subCos() {
    return state.changeOrders.filter(co => isSubCo(co));
  }

  function validateAllocations(allocations, { requireRows = true, requireAmount = false, subCoKind = null } = {}) {
    const rows = (allocations || []).filter(a => a.cost_code || a.cost_type || a.description || a.amount);
    if (requireRows && !rows.length) {
      return { ok: false, message: 'At least one cost code allocation is required (cost code, cost type, and amount).' };
    }
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      if (!row.cost_code) return { ok: false, message: `Row ${i + 1}: cost code is required.` };
      if (!row.cost_type) return { ok: false, message: `Row ${i + 1}: cost type is required.` };
      if (requireAmount && !Number(row.amount)) return { ok: false, message: `Row ${i + 1}: amount must be non-zero.` };
    }
    const kind = subCoKind || '';
    if (kind === 'Budget Transfer') {
      if (rows.length < 2) return { ok: false, message: 'Budget transfer requires at least two allocation rows (from and to cost codes).' };
      const net = Math.round(rows.reduce((s, r) => s + (Number(r.amount) || 0), 0) * 100) / 100;
      if (net !== 0) return { ok: false, message: `Budget transfer allocations must net to zero (current net: ${net.toLocaleString()}).` };
      const hasPos = rows.some(r => Number(r.amount) > 0);
      const hasNeg = rows.some(r => Number(r.amount) < 0);
      if (!hasPos || !hasNeg) return { ok: false, message: 'Budget transfer requires at least one positive and one negative allocation row.' };
    } else if (kind === 'Contract Add' && requireAmount) {
      const total = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
      if (total <= 0) return { ok: false, message: 'Contract add subcontractor change orders require a positive total amount.' };
    }
    return { ok: true, rows };
  }

  function showAllocationValidation(message) {
    const el = document.getElementById('allocationValidation');
    if (!el) return;
    if (!message) {
      el.classList.add('hidden');
      el.textContent = '';
      return;
    }
    el.textContent = message;
    el.classList.remove('hidden');
  }

  function updateAllocationTotal() {
    const total = readAllocationsFromDom().reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
    const el = document.getElementById('allocationTotal');
    if (el) el.textContent = fmt(total);
    const amountInput = document.getElementById('modalAmount');
    if (amountInput && total) setMoney('modalAmount', total);
  }

  function onAllocCostCodeChange(idx) {
    const sel = document.querySelector(`.alloc-cost-code[data-idx="${idx}"]`);
    if (!sel) return;
    const meta = lookupCostCodeMeta(sel.value);
    if (!meta) return;
    const typeSel = document.querySelector(`.alloc-cost-type[data-idx="${idx}"]`);
    const descInput = document.querySelector(`.alloc-desc[data-idx="${idx}"]`);
    if (typeSel && meta.cost_type) typeSel.value = meta.cost_type;
    if (descInput && !descInput.value && meta.description) descInput.value = meta.description;
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
    state.ownerChangeOrders = ownerCos().filter(c => c.status === 'Approved' || ['Submitted', 'Pending Owner', 'Pending Architect', 'Under Review'].includes(c.status))
      .map(c => ({ id: c.id, number: c.number, title: c.title || c.description, status: c.status, amount: c.amount }));
    renderCoTable();
    renderSubCoTable();
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
      state.ownerChangeOrders = json.owner_change_orders || [];
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
    const ownerSel = document.getElementById('modalLinkedOwnerCo');
    if (rfiSel) {
      rfiSel.innerHTML = '<option value="">— None —</option>' +
        state.rfis.map(r => `<option value="${r.id}" ${String(record?.linked_rfi_id) === String(r.id) ? 'selected' : ''}>${r.number} — ${r.subject || ''}</option>`).join('');
    }
    const subCommitments = state.commitments.filter(c => (c.commitment_type || '') === 'Subcontract');
    const commitments = isSubCo(record) || document.getElementById('modalMode')?.value === 'sub'
      ? (subCommitments.length ? subCommitments : state.commitments)
      : state.commitments;
    if (comSel) {
      comSel.innerHTML = '<option value="">— None —</option>' +
        commitments.map((c, i) => {
          const ref = c.number || `COM-${c.id || i + 1}`;
          const label = c.company_name ? `${c.company_name} — ${ref}` : (c.description || c.title || ref);
          return `<option value="${ref}" data-company-id="${esc(c.company_id || '')}" data-company-name="${esc(c.company_name || '')}" ${record?.linked_commitment_ref === ref ? 'selected' : ''}>${label}</option>`;
        }).join('');
    }
    if (ownerSel) {
      ownerSel.innerHTML = '<option value="">— None (standalone) —</option>' +
        state.ownerChangeOrders.map(c => `<option value="${c.id}" ${String(record?.linked_owner_co_id) === String(c.id) ? 'selected' : ''}>${c.number} — ${esc(c.title || '')} (${c.status})</option>`).join('');
    }
  }

  function onSubCoKindChange() {
    const kind = document.getElementById('modalSubCoKind')?.value || '';
    const help = document.getElementById('allocationHelpText');
    if (help) {
      help.textContent = kind === 'Budget Transfer'
        ? 'Enter at least two rows with opposite signs that net to zero (move budget between cost codes). Does not change total contract value.'
        : kind === 'Contract Add'
          ? 'Positive amounts add to the subcontract commitment and Sub SOV. Link a subcontract commitment before submit.'
          : kind === 'Owner CO Backcharge'
            ? 'Link the approved owner CO below. Allocations should mirror the owner CO subcontract cost codes being backcharged to this sub.'
            : 'Cost code, cost type, and amount are required before submit or approval. Syncs to Budget, Sub SOV, and Sage Subcontracts.';
    }
  }

  function onLinkedCommitmentChange() {
    const sel = document.getElementById('modalLinkedCommitment');
    const companySel = document.getElementById('modalCompany');
    if (!sel || !companySel || document.getElementById('modalMode')?.value !== 'sub') return;
    const opt = sel.options[sel.selectedIndex];
    if (!opt || !opt.value) return;
    const cid = opt.dataset.companyId;
    const cname = opt.dataset.companyName;
    if (cid) {
      for (let i = 0; i < companySel.options.length; i += 1) {
        if (String(companySel.options[i].value) === String(cid)) {
          companySel.selectedIndex = i;
          onCompanyChange();
          return;
        }
      }
    }
    if (cname) {
      for (let i = 0; i < companySel.options.length; i += 1) {
        if ((companySel.options[i].dataset.name || companySel.options[i].text || '').toLowerCase() === cname.toLowerCase()) {
          companySel.selectedIndex = i;
          onCompanyChange();
          return;
        }
      }
    }
  }

  async function loadSageLog() {
    const pid = projectId();
    if (!pid) return;
    try {
      const res = await fetch(`/api/sage/sync-events?project_id=${pid}&limit=30`, { credentials: 'same-origin' });
      const json = await res.json();
      state.sageLog = (json.events || []).filter(e =>
        ['ChangeOrderApproved', 'ChangeOrderSubmitted', 'PCOSubmitted', 'PCOPromoted', 'CommitmentChangeOrderSubmitted', 'CommitmentChangeOrderApproved'].includes(e.event_type)
      );
    } catch { state.sageLog = []; }
    renderSageBar();
  }

  function statusBadge(status) {
    const colors = {
      Draft: 'bg-zinc-700 text-zinc-300', Open: 'bg-sky-900/50 text-sky-300', Pricing: 'bg-indigo-900/50 text-indigo-300',
      Submitted: 'bg-amber-900/50 text-amber-300', 'Under Review': 'bg-amber-900/50 text-amber-300',
      'Pending Owner': 'bg-orange-900/50 text-orange-300', 'Pending Architect': 'bg-purple-900/50 text-purple-300',
      'Pending Accounting': 'bg-amber-900/50 text-amber-300',
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
      statTotalSubCo: s.total_sub_cos || 0,
      statSubPending: s.sub_pending_count || 0,
    };
    Object.keys(map).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
  }

  function filteredCos() {
    const { search, status, priority } = state.filter;
    return ownerCos().filter(co => {
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

  function filteredSubCos() {
    const { search, status, priority } = state.filter;
    return subCos().filter(co => {
      const text = `${co.number} ${co.title} ${co.description} ${co.company_name || ''} ${co.sub_co_kind || ''}`.toLowerCase();
      if (search && !text.includes(search.toLowerCase())) return false;
      if (status && co.status !== status) return false;
      if (priority && co.priority !== priority) return false;
      return true;
    });
  }

  function ownerCoLabel(ownerCoId, co) {
    if (!ownerCoId) return '—';
    if (co?.linked_owner_co?.number) {
      return co.linked_owner_co.number;
    }
    const c = state.ownerChangeOrders.find(x => String(x.id) === String(ownerCoId))
      || ownerCos().find(x => String(x.id) === String(ownerCoId));
    return c ? `${c.number}` : `#${ownerCoId}`;
  }

  function ownerCoLink(ownerCoId, co) {
    if (!ownerCoId) return '—';
    const label = ownerCoLabel(ownerCoId, co);
    return `<button type="button" class="font-mono text-sky-400 hover:underline" onclick="event.stopPropagation(); CasePMChangeOrders.viewCo(${ownerCoId})">${esc(label)}</button>`;
  }

  function subCoLink(subId, number) {
    return `<button type="button" class="font-mono text-amber-400 hover:underline" onclick="event.stopPropagation(); CasePMChangeOrders.viewCo(${subId})">${esc(number)}</button>`;
  }

  function subCoApproveStatuses() {
    return ['Submitted', 'Pending Accounting'];
  }

  function renderSubCoTable() {
    const tbody = document.getElementById('subCoTableBody');
    if (!tbody) return;
    const rows = filteredSubCos();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="13" class="px-6 py-12 text-center text-zinc-500">No subcontractor change orders yet. Create one tied to an owner CO backcharge, contract add, or budget transfer.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(co => {
      const showSubmit = co.status === 'Draft';
      const showApprove = subCoApproveStatuses().includes(co.status) && canActOnBall(co.ball_in_court_role);
      const showReject = showApprove;
      const autoTag = co.auto_generated ? '<span class="ml-1 text-[9px] text-sky-400">AUTO</span>' : '';
      const variance = co.billing_variance != null ? co.billing_variance : null;
      const varianceCls = variance == null ? 'text-zinc-500' : (variance === 0 ? 'text-emerald-400' : (variance > 0 ? 'text-amber-400' : 'text-red-400'));
      return `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" onclick="CasePMChangeOrders.openCoItem(${co.id})">
        <td class="px-4 py-3 font-mono text-amber-400 whitespace-nowrap">${co.number || '—'}${autoTag}</td>
        <td class="px-4 py-3 whitespace-nowrap">${fmtDate(co.date)}</td>
        <td class="px-4 py-3 text-xs text-zinc-300">${co.company_name || '—'}</td>
        <td class="px-4 py-3 font-mono text-xs">${co.linked_commitment_ref || '—'}</td>
        <td class="px-4 py-3 font-mono text-xs text-sky-400">${ownerCoLink(co.linked_owner_co_id, co)}</td>
        <td class="px-4 py-3 text-xs">${co.sub_co_kind || '—'}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(co.amount)}</td>
        <td class="px-4 py-3 text-right font-mono text-xs">${co.billed_amount != null ? fmt(co.billed_amount) : '—'}</td>
        <td class="px-4 py-3 text-right font-mono text-xs ${varianceCls}">${variance != null ? fmt(variance) : '—'}</td>
        <td class="px-4 py-3 text-center">${statusBadge(co.status)}</td>
        <td class="px-4 py-3 text-center">${ballBadge(co.ball_in_court_role)}</td>
        <td class="px-4 py-3 text-center text-[10px] ${co.sov_synced_at ? 'text-emerald-400' : 'text-zinc-500'}">${co.sov_synced_at ? 'SOV ✓' : (co.sage_sync_status || '—')}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-2 flex-wrap">
            ${showSubmit ? `<button onclick="CasePMChangeOrders.workflowCo(${co.id},'submit')" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 rounded-md text-xs font-medium">Submit</button>` : ''}
            ${showApprove ? reviewButtonHtml(co.id) : ''}
            <button onclick="CasePMChangeOrders.editSubCo(${co.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded" title="Edit"><i class="fa-solid fa-edit"></i></button>
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  function reviewButtonHtml(coId, label, handler) {
    const text = label || 'Review & Respond';
    const fn = handler || 'openApprovalModal';
    return `<button type="button" onclick="event.stopPropagation(); CasePMChangeOrders.${fn}(${coId},'approve')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-semibold whitespace-nowrap shadow-md"><i class="fa-solid fa-clipboard-check mr-1"></i>${text}</button>`;
  }

  function renderCoTable() {
    const tbody = document.getElementById('coTableBody');
    if (!tbody) return;
    const rows = filteredCos();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="11" class="px-6 py-12 text-center text-zinc-500">No change orders found.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(co => {
      const showSubmit = co.status === 'Draft';
      const showApprove = (isSubCo(co) ? subCoApproveStatuses() : ['Submitted', 'Pending Architect', 'Pending Owner', 'Pending Accounting']).includes(co.status) && canActOnBall(co.ball_in_court_role);
      const showReject = showApprove;
      const approveLabel = co.status === 'Pending Owner' ? 'Final Approve' : 'Approve Step';
      const subCount = (co.linked_sub_change_orders || []).length;
      return `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" onclick="CasePMChangeOrders.openCoItem(${co.id})">
        <td class="px-4 py-3 font-mono text-emerald-400 whitespace-nowrap">${co.number || '—'}</td>
        <td class="px-4 py-3 whitespace-nowrap">${fmtDate(co.date)}</td>
        <td class="px-4 py-3 max-w-[200px] truncate">${co.title || co.description}</td>
        <td class="px-4 py-3 text-xs text-zinc-400">${co.company_name || '—'}</td>
        <td class="px-4 py-3 font-mono text-xs">${co.cost_code || (co.allocations?.[0]?.cost_code) || '—'}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(co.amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(co.status)}</td>
        <td class="px-4 py-3 text-center">${subCount ? `<span class="text-[10px] text-amber-400 font-medium">${subCount} SCO</span>` : '<span class="text-zinc-600">—</span>'}</td>
        <td class="px-4 py-3 text-center">${ballBadge(co.ball_in_court_role)}</td>
        <td class="px-4 py-3 text-center text-[10px] ${co.sov_synced_at ? 'text-emerald-400' : 'text-zinc-500'}">${co.sov_synced_at ? 'SOV ✓' : (co.sage_sync_status || '—')}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-2 flex-wrap">
            ${showSubmit ? `<button onclick="CasePMChangeOrders.workflowCo(${co.id},'submit')" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 rounded-md text-xs font-medium">Submit</button>` : ''}
            ${showApprove ? reviewButtonHtml(co.id, approveLabel) : ''}
            <button onclick="CasePMChangeOrders.editCo(${co.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded" title="Edit"><i class="fa-solid fa-edit"></i></button>
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
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" onclick="CasePMChangeOrders.openPcoItem(${p.id})">
        <td class="px-4 py-3 font-mono text-sky-400 whitespace-nowrap">${p.number}</td>
        <td class="px-4 py-3 max-w-[240px] truncate">${p.title}</td>
        <td class="px-4 py-3 text-xs text-zinc-400">${p.company_name || '—'}</td>
        <td class="px-4 py-3 text-right font-mono">${fmt(p.estimated_amount)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(p.status)}</td>
        <td class="px-4 py-3 text-center">${ballBadge(p.ball_in_court_role)}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-1">
            ${p.status === 'Open' ? `<button onclick="CasePMChangeOrders.pcoWorkflow(${p.id},'submit')" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 rounded-md text-xs font-medium">Submit</button>` : ''}
            ${['Pricing', 'Pending Review'].includes(p.status) && canActOnBall(p.ball_in_court_role) ? reviewButtonHtml(p.id, 'Review PCO', 'openPcoReviewModal') : ''}
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

  const CO_TAB_MODULES = { cos: 'change_orders_log', pcos: 'change_orders_pco', subs: 'change_orders_sub' };

  function canAccessCoTab(tab) {
    const mod = CO_TAB_MODULES[tab];
    if (!mod) return true;
    if (typeof canAccessModule === 'function') return canAccessModule(mod, 'view');
    const allowed = global.CASEPM_ALLOWED_MODULES || {};
    return allowed[mod] !== false;
  }

  function applyCoTabPermissions() {
    Object.entries(CO_TAB_MODULES).forEach(([tab, mod]) => {
      const btnId = tab === 'cos' ? 'btnTabCos' : (tab === 'pcos' ? 'btnTabPcos' : 'btnTabSubs');
      const btn = document.getElementById(btnId);
      if (btn) btn.classList.toggle('hidden', !canAccessCoTab(tab));
    });
    if (!canAccessCoTab(state.tab || 'cos')) {
      const first = Object.keys(CO_TAB_MODULES).find(t => canAccessCoTab(t));
      if (first) switchTab(first);
    }
  }

  function switchTab(tab) {
    if (!canAccessCoTab(tab)) {
      const first = Object.keys(CO_TAB_MODULES).find(t => canAccessCoTab(t));
      if (!first) return;
      tab = first;
    }
    state.tab = tab;
    document.getElementById('tabCos').classList.toggle('hidden', tab !== 'cos');
    document.getElementById('tabPcos').classList.toggle('hidden', tab !== 'pcos');
    document.getElementById('tabSubs').classList.toggle('hidden', tab !== 'subs');
    document.getElementById('btnTabCos').className = tab === 'cos'
      ? 'px-4 py-2 rounded-md text-sm font-medium bg-emerald-600 text-white'
      : 'px-4 py-2 rounded-md text-sm font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
    document.getElementById('btnTabPcos').className = tab === 'pcos'
      ? 'px-4 py-2 rounded-md text-sm font-medium bg-emerald-600 text-white'
      : 'px-4 py-2 rounded-md text-sm font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
    document.getElementById('btnTabSubs').className = tab === 'subs'
      ? 'px-4 py-2 rounded-md text-sm font-medium bg-amber-600 text-white'
      : 'px-4 py-2 rounded-md text-sm font-medium bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
    document.getElementById('btnNewSubCo')?.classList.toggle('hidden', tab !== 'subs');
    document.getElementById('statSubCard1')?.classList.toggle('hidden', tab !== 'subs');
    document.getElementById('statSubCard2')?.classList.toggle('hidden', tab !== 'subs');
    if (tab === 'subs') renderSubCoTable();
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
      state.allocationRows = [{ cost_code: '', cost_type: '', amount: 0, description: '' }];
    }
    const typeOptions = state.costTypes.length ? state.costTypes : DEFAULT_COST_TYPES;
    container.innerHTML = state.allocationRows.map((row, idx) => `
      <tr>
        <td class="alloc-num">${idx + 1}</td>
        <td>
          <select class="alloc-cost-code" data-idx="${idx}" onchange="CasePMChangeOrders.onAllocCostCodeChange(${idx})">
            <option value="">Select code…</option>
            ${state.costCodes.map(c => `<option value="${esc(c.code)}" ${c.code === row.cost_code ? 'selected' : ''}>${esc(c.code)}${c.description ? ` — ${esc(c.description)}` : ''}</option>`).join('')}
          </select>
        </td>
        <td>
          <select class="alloc-cost-type" data-idx="${idx}">
            <option value="">Select type…</option>
            ${typeOptions.map(t => `<option value="${esc(t)}" ${t === row.cost_type ? 'selected' : ''}>${esc(t)}</option>`).join('')}
          </select>
        </td>
        <td><input type="text" class="alloc-desc" data-idx="${idx}" value="${esc(row.description || '')}" placeholder="SOV / budget line description"></td>
        <td class="alloc-amt-cell"><input type="number" step="0.01" class="alloc-amt" data-idx="${idx}" value="${row.amount || 0}" oninput="CasePMChangeOrders.updateAllocationTotal()"></td>
        <td class="text-center">
          ${state.allocationRows.length > 1 ? `<button type="button" onclick="CasePMChangeOrders.removeAllocRow(${idx})" class="px-1.5 py-1 text-red-400 hover:text-red-300" title="Remove row"><i class="fa-solid fa-times"></i></button>` : ''}
        </td>
      </tr>`).join('');
    updateAllocationTotal();
    showAllocationValidation('');
  }

  function readAllocationsFromDom() {
    const rows = [];
    document.querySelectorAll('.alloc-cost-code').forEach((sel, idx) => {
      const code = sel.value?.trim();
      const costType = document.querySelector(`.alloc-cost-type[data-idx="${idx}"]`)?.value?.trim() || '';
      const desc = document.querySelector(`.alloc-desc[data-idx="${idx}"]`)?.value?.trim() || '';
      const amt = parseFloat(document.querySelector(`.alloc-amt[data-idx="${idx}"]`)?.value) || 0;
      if (code || costType || desc || amt) rows.push({ cost_code: code, cost_type: costType, amount: amt, description: desc });
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
      linked_owner_co_id: document.getElementById('modalLinkedOwnerCo')?.value || null,
      sub_co_kind: document.getElementById('modalSubCoKind')?.value || null,
      allocations: allocs,
    };
    if (type === 'sub') {
      base.contract_type = 'Subcontract';
      if (!base.sub_co_kind) base.sub_co_kind = 'Contract Add';
    }
    if (type === 'pco') {
      const payload = { ...base, estimated_amount: total || readMoney('modalAmount') };
      if (devUnlock()) {
        const num = document.getElementById('modalNumber')?.value?.trim();
        if (num) payload.number = num;
      }
      return payload;
    }
    const coPayload = { ...base, amount: total || readMoney('modalAmount'), date: document.getElementById('modalDate')?.value };
    if (devUnlock()) {
      const num = document.getElementById('modalNumber')?.value?.trim();
      if (num) coPayload.number = num;
      if (document.getElementById('modalStatus')?.value === 'Approved' || document.getElementById('modalStatus')?.value === 'Draft') {
        coPayload.executed_locked = false;
      }
    }
    return coPayload;
  }

  function renderModalAttachmentList(record, mode) {
    const el = document.getElementById('modalAttachmentList');
    const input = document.getElementById('modalAttachmentInput');
    if (input) input.value = '';
    if (!el) return;
    const atts = (record && record.attachments) || [];
    if ((mode !== 'co' && mode !== 'pco') || !atts.length) {
      el.innerHTML = '<span class="text-zinc-500">No files yet — save first, then upload on edit</span>';
      return;
    }
    const kind = mode === 'pco' ? 'pco' : 'co';
    el.innerHTML = atts.map(a =>
      `<a href="${attachmentHref(record.id, a, kind)}" target="_blank" rel="noopener" class="text-emerald-400 hover:underline">${attachmentLabel(a)}</a>`
    ).join(' · ');
  }

  async function refreshModalAttachments() {
    const mode = document.getElementById('modalMode')?.value;
    const id = document.getElementById('modalRecordId')?.value;
    if (!id || (mode !== 'co' && mode !== 'sub' && mode !== 'pco')) return;
    try {
      const path = mode === 'pco' ? `/api/pcos/${id}` : `/api/change-orders/${id}`;
      const json = await api(path);
      const record = mode === 'pco' ? json : json.change_order;
      renderModalAttachmentList(record, mode === 'sub' ? 'co' : mode);
    } catch (e) {
      console.warn('Could not refresh attachments', e);
    }
  }

  function bindAttachmentBrowse() {
    const container = document.getElementById('coAttachmentActions');
    if (!container || !global.CasePMDocPicker) return;
    global.CasePMDocPicker.addBrowseButton(container, {
      title: 'Attach from Documents',
      entityType: 'change_order',
      getEntityId: () => {
        const id = document.getElementById('modalRecordId')?.value;
        return id ? parseInt(id, 10) : null;
      },
      onPick: async () => {
        const id = document.getElementById('modalRecordId')?.value;
        if (!id) {
          alert('Save the change order first, then attach files from Documents.');
          return;
        }
        await refreshModalAttachments();
      },
    });
  }

  async function uploadModalAttachments(parentId, kind) {
    const input = document.getElementById('modalAttachmentInput');
    if (!input?.files?.length) return;
    const url = kind === 'pco'
      ? `/api/pcos/${parentId}/attachments`
      : `/api/change-orders/${parentId}/attachments`;
    for (const file of input.files) {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || 'Attachment upload failed');
    }
  }

  function openModal(mode, record) {
    const modal = document.getElementById('coModal');
    const isPco = mode === 'pco';
    const isSub = mode === 'sub' || isSubCo(record);
    document.getElementById('modalMode').value = isSub ? 'sub' : mode;
    document.getElementById('modalRecordId').value = record?.id || '';
    document.getElementById('coModalHeading').textContent = record
      ? (isPco ? `Edit PCO ${record.number}` : (isSub ? `Edit ${record.number}` : `Edit ${record.number}`))
      : (isPco ? 'New Potential Change Order (PCO)' : (isSub ? 'New Subcontractor Change Order (SCO)' : 'New Change Order'));
    document.getElementById('modalDateRow').classList.toggle('hidden', isPco);
    document.getElementById('modalContractTypeRow').classList.toggle('hidden', isPco || isSub);
    document.getElementById('modalSubKindRow')?.classList.toggle('hidden', !isSub);
    document.getElementById('modalOwnerCoRow')?.classList.toggle('hidden', !isSub);
    populateSelect('modalStatus', isPco ? PCO_STATUSES : (isSub ? SUB_CO_STATUSES : (
      (record?.status === 'Approved' && !devUnlock()) ? CO_STATUSES : CO_STATUSES
    )), record?.status || (isPco ? 'Open' : 'Draft'));
    populateSelect('modalReason', [''].concat(REASONS), record?.reason || '');
    populateSelect('modalPriority', PRIORITIES, record?.priority || 'Medium');
    if (!isSub) populateSelect('modalContractType', CONTRACT_TYPES, record?.contract_type || 'Owner');
    const kindSel = document.getElementById('modalSubCoKind');
    if (kindSel && isSub) kindSel.value = record?.sub_co_kind || 'Contract Add';
    populateCompanySelect(record?.company_id);
    document.getElementById('modalTitle').value = record?.title || '';
    document.getElementById('modalDescription').value = record?.description || '';
    setMoney('modalAmount', record ? (isPco ? record.estimated_amount : record.amount) : '');
    if (global.CasePMMoney) CasePMMoney.setupMoneyInput(document.getElementById('modalAmount'));
    document.getElementById('modalScheduleDays').value = record?.schedule_impact_days || 0;
    document.getElementById('modalRequestedBy').value = record?.requested_by || currentUserName();
    document.getElementById('modalNotes').value = record?.notes || '';
    document.getElementById('modalDate').value = record?.date ? record.date.split('T')[0] : new Date().toISOString().split('T')[0];
    const numRow = document.getElementById('modalNumberRow');
    const numEl = document.getElementById('modalNumber');
    if (numRow && numEl) {
      const showNum = devUnlock() && !!record;
      numRow.classList.toggle('hidden', !showNum);
      numEl.value = record?.number || '';
      numEl.disabled = !showNum;
    }
    document.getElementById('modalContactEmail').value = record?.contact_email || '';
    document.getElementById('modalContactPhone').value = record?.contact_phone || '';
    state.allocationRows = (record?.allocations && record.allocations.length)
      ? record.allocations.map(a => ({
        cost_code: a.cost_code || '',
        cost_type: a.cost_type || lookupCostCodeMeta(a.cost_code)?.cost_type || '',
        amount: a.amount || 0,
        description: a.description || '',
      }))
      : [{ cost_code: record?.cost_code || '', cost_type: '', amount: record?.amount || record?.estimated_amount || 0, description: '' }];
    onCompanyChange();
    if (record?.contact_name) {
      const csel = document.getElementById('modalContact');
      if (csel) csel.value = record.contact_name;
    }
    populateLinkSelects(record);
    if (record?.linked_owner_co_id) {
      const ownerSel = document.getElementById('modalLinkedOwnerCo');
      if (ownerSel) ownerSel.value = String(record.linked_owner_co_id);
    }
    const comSel = document.getElementById('modalLinkedCommitment');
    if (comSel && !comSel.dataset.bound) {
      comSel.dataset.bound = '1';
      comSel.addEventListener('change', onLinkedCommitmentChange);
    }
    onSubCoKindChange();
    renderModalAttachmentList(record, isSub ? 'co' : mode);
    renderAllocationRows();
    openDialog(modal);
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
    const status = payload.status || (mode === 'pco' ? 'Open' : 'Draft');
    const subCoKind = payload.sub_co_kind;
    const needsAlloc = mode === 'pco'
      ? !['Open', 'Draft'].includes(status)
      : status !== 'Draft';
    const allocCheck = validateAllocations(payload.allocations, {
      requireRows: needsAlloc,
      requireAmount: needsAlloc && subCoKind !== 'Budget Transfer',
      subCoKind,
    });
    if (!allocCheck.ok) {
      showAllocationValidation(allocCheck.message);
      alert(allocCheck.message);
      return;
    }
    if (mode === 'sub' && subCoKind === 'Contract Add' && needsAlloc && !payload.linked_commitment_ref) {
      alert('Contract add subcontractor change orders require a linked subcontract commitment.');
      return;
    }
    if (mode === 'sub' && subCoKind === 'Owner CO Backcharge' && needsAlloc && !payload.linked_owner_co_id) {
      alert('Owner CO backcharge subcontractor change orders require a linked owner change order.');
      return;
    }
    showAllocationValidation('');
    try {
      if (mode === 'pco') {
        const json = id
          ? await api(`/api/pcos/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
          : await api('/api/pcos', { method: 'POST', body: JSON.stringify(payload) });
        const pcoId = id || json.pco?.id || json.id;
        if (pcoId) await uploadModalAttachments(pcoId, 'pco');
        await loadPcos();
        await loadDashboard();
        document.getElementById('coModal').close();
        toast('Saved successfully');
      } else {
        const json = id
          ? await api(`/api/change-orders/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
          : await api('/api/change-orders', { method: 'POST', body: JSON.stringify(payload) });
        const coId = id || json.change_order?.id;
        if (coId) await uploadModalAttachments(coId, 'co');
        await applyCoSync(json);
        await loadChangeOrders();
        await loadDashboard();
        document.getElementById('coModal').close();
        const synced = json.sync_result && !json.sync_result.error;
        const budgetSynced = !!json.budget_sync_result;
        if (mode === 'sub') switchTab('subs');
        if (synced) {
          toast('Saved — amounts synced to Budget & Pay Application SOV');
        } else if (budgetSynced) {
          toast('Saved — pending amounts synced to Budget');
        } else if (json.sync_result?.error) {
          toast(`Saved, but SOV sync failed: ${json.sync_result.error}`);
        } else {
          toast('Saved successfully');
        }
      }
    } catch (err) {
      alert(err.message);
    }
  }

  async function applyCoSync(json) {
    if (!json) return false;
    let updated = false;
    if (json.sync_result && typeof CasePMPayAppSync !== 'undefined') {
      updated = CasePMPayAppSync.applyCoSyncResult(json.sync_result) || updated;
    }
    if (json.budget_sync_result && typeof CasePMBudgetSync !== 'undefined') {
      updated = CasePMBudgetSync.applyBudgetSyncResult(json.budget_sync_result) || updated;
    }
    if (updated || json.sync_result || json.budget_sync_result) {
      global.dispatchEvent(new CustomEvent('casepm:co-approved', { detail: json }));
    }
    return updated;
  }

  async function resyncSov(coId) {
    try {
      const json = await api(`/api/change-orders/${coId}/sync-to-sov`, { method: 'POST', body: '{}' });
      await applyCoSync({ sync_result: json });
      const subAmt = json.sub_sov_amount_applied || json.sync_result?.sub_sov_amount_applied;
      const msg = subAmt
        ? `Synced to Pay App SOV. Subcontractor SOV updated: ${fmt(subAmt)}.`
        : (json.already_synced || json.sync_result?.already_synced)
          ? 'Already synced to contractor SOV. No new subcontractor SOV lines matched.'
          : 'Synced to Budget & Pay Application SOV.';
      toast(msg);
      await loadChangeOrders();
      if (state.drawerRecord?.id === coId) await viewCo(coId);
    } catch (err) {
      alert(err.message);
    }
  }

  let approvalContext = { coId: null, signPanel: null };

  function approvalRequiresEsign(co) {
    if (isSubCo(co)) return false;
    const role = co?.ball_in_court_role;
    return role === 'Owner' || role === 'Architect';
  }

  function openApprovalModal(coId, intent) {
    closeDrawer();
    const co = state.changeOrders.find(c => c.id === coId) || (state.drawerRecord?.id === coId ? state.drawerRecord : null);
    if (!co) return;
    const allocCheck = validateAllocations(co.allocations || [], {
      requireRows: true,
      requireAmount: co.sub_co_kind !== 'Budget Transfer',
      subCoKind: co.sub_co_kind,
    });
    if (!allocCheck.ok && intent !== 'reject') {
      alert(`${allocCheck.message}\n\nComplete Schedule of Values allocations before approval.`);
      return;
    }
    if (typeof global.CasePMApprovalResponder !== 'undefined') {
      global.CasePMApprovalResponder.open('co', coId).catch(e => alert(e.message));
      return;
    }
    approvalContext = { coId };
    const modal = document.getElementById('coApprovalModal');
    document.getElementById('coApprovalTitle').textContent = 'Review Change Order';
    document.getElementById('coApprovalSubtitle').textContent = `${co.number} · ${co.ball_in_court_role || 'Approver'} review`;
    const allocLines = (co.allocations || []).map(a =>
      `<div class="flex justify-between gap-3 text-xs"><span class="font-mono text-emerald-400">${esc(a.cost_code)}</span><span class="text-zinc-400">${esc(a.cost_type || '')}</span><span class="font-mono">${fmt(a.amount)}</span></div>`
    ).join('') || '<div class="text-zinc-500">No allocations</div>';
    document.getElementById('coApprovalSummary').innerHTML = `
      <div class="flex justify-between"><span class="text-zinc-500">Title</span><span class="text-right max-w-[65%]">${esc(co.title || co.description)}</span></div>
      <div class="flex justify-between"><span class="text-zinc-500">Amount</span><span class="font-mono text-emerald-400">${fmt(co.amount)}</span></div>
      <div class="flex justify-between"><span class="text-zinc-500">Status</span><span>${statusBadge(co.status)}</span></div>
      <div class="pt-2 border-t border-zinc-800">
        <div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">SOV Allocations</div>
        ${allocLines}
      </div>`;
    const commentsEl = document.getElementById('coApprovalComments');
    if (commentsEl) {
      commentsEl.value = '';
      commentsEl.placeholder = intent === 'reject'
        ? 'Rejection reason (required)…'
        : 'Optional approval notes…';
    }
    document.getElementById('coApprovalCommentsRequired')?.classList.add('hidden');
    document.getElementById('coApprovalApproveBtn')?.classList.remove('hidden');
    document.getElementById('coApprovalRejectBtn')?.classList.remove('hidden');
    const signHost = document.getElementById('coApprovalSignPanel');
    if (approvalContext.signPanel) {
      approvalContext.signPanel.destroy();
      approvalContext.signPanel = null;
    }
    if (intent === 'approve' && approvalRequiresEsign(co) && signHost && typeof CasePMEsign !== 'undefined') {
      signHost.classList.remove('hidden');
      approvalContext.signPanel = CasePMEsign.mountSignPanel(signHost, {
        title: `${co.ball_in_court_role} Approval — Electronic Signature`,
        requireSignature: true,
      });
    } else if (signHost) {
      signHost.classList.add('hidden');
      signHost.innerHTML = '';
    }
    openDialog(modal);
    if (intent === 'reject') commentsEl?.focus();
  }

  async function confirmApprovalAction(action) {
    const coId = approvalContext.coId;
    if (!coId || !action) return;
    const comments = document.getElementById('coApprovalComments')?.value?.trim() || '';
    if (action === 'reject' && !comments) {
      alert('Please enter a rejection comment.');
      return;
    }
    let extra = {};
    if (action === 'approve' && approvalContext.signPanel) {
      try {
        extra = await approvalContext.signPanel.getPayload();
      } catch (err) {
        alert(err.message || 'Complete the electronic signature attestation.');
        return;
      }
    }
    document.getElementById('coApprovalModal')?.close();
    await workflowCo(coId, action, comments, extra);
    if (approvalContext.signPanel) {
      approvalContext.signPanel.destroy();
      approvalContext.signPanel = null;
    }
    approvalContext = { coId: null, signPanel: null };
  }

  async function workflowCo(id, action, comments, esignPayload) {
    const co = state.changeOrders.find(c => c.id === id) || state.drawerRecord;
    if (!co) return;
    const allocCheck = validateAllocations(co.allocations || [], {
      requireRows: true,
      requireAmount: co.sub_co_kind !== 'Budget Transfer',
      subCoKind: co.sub_co_kind,
    });
    if (!allocCheck.ok && (action === 'submit' || action === 'approve')) {
      alert(`${allocCheck.message}\n\nEdit the change order and complete the Schedule of Values allocations first.`);
      return;
    }
    if (action === 'submit') {
      if (!(await coConfirm(`Submit ${co.number} for approval?`, { title: 'Submit for approval' }))) return;
    }
    try {
      const json = await api(`/api/change-orders/${id}/workflow`, {
        method: 'POST',
        body: JSON.stringify({ action, comments: comments || '', ...(esignPayload || {}) }),
      });
      await applyCoSync(json);
      if (action === 'submit' && typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.onChangeOrderSubmitted) {
        await CasePMWorkflow.onChangeOrderSubmitted(json.change_order || co).catch(() => {});
      }
      await loadChangeOrders();
      await loadDashboard();
      await loadSageLog();
      if (json.auto_sub_change_orders?.length) {
        toast(`Owner CO approved — ${json.auto_sub_change_orders.length} draft Sub CO(s) auto-created`);
        switchTab('subs');
      }
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
    const showSubmit = co.status === 'Draft';
    const showApprove = (isSubCo(co) ? subCoApproveStatuses() : ['Submitted', 'Pending Architect', 'Pending Owner', 'Pending Accounting']).includes(co.status) && canActOnBall(co.ball_in_court_role);
    const approveLabel = co.status === 'Pending Owner' ? 'Review & Final Approve' : 'Review & Respond';
    const reviewBanner = showApprove ? `
      <div class="mb-6 p-4 rounded-lg bg-emerald-950/50 border-2 border-emerald-600 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div class="text-emerald-400 font-semibold">Your review is needed</div>
          <div class="text-xs text-zinc-400 mt-1">Ball in court: ${esc(co.ball_in_court_role || '—')} · Status: ${esc(co.status)}</div>
        </div>
        ${reviewButtonHtml(co.id, approveLabel)}
      </div>` : '';
    const allocs = (co.allocations || []).map(a =>
      `<tr class="border-b border-zinc-800"><td class="py-2 font-mono text-xs">${esc(a.cost_code)}</td><td class="py-2 text-xs text-zinc-400">${esc(a.cost_type || '—')}</td><td class="py-2">${esc(a.description || '')}</td><td class="py-2 text-right font-mono">${fmt(a.amount)}</td></tr>`
    ).join('');
    const atts = (co.attachments || []).map(a =>
      `<a href="${attachmentHref(co.id, a)}" target="_blank" rel="noopener" class="text-emerald-400 hover:underline">${attachmentLabel(a)}</a>`
    ).join(' · ') || '—';
    const bodyHtml = `
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
        ${isSubCo(co) ? `<p><span class="text-zinc-500">Sub CO Type</span><br>${esc(co.sub_co_kind || '—')}${co.auto_generated ? ' <span class="text-sky-400 text-xs">(auto-generated)</span>' : ''}</p>` : ''}
        ${co.linked_owner_co_id ? `<p><span class="text-zinc-500">Linked Owner CO</span><br>${ownerCoLink(co.linked_owner_co_id, co)}${co.linked_owner_co?.amount != null ? ` <span class="text-zinc-500 text-xs">(${fmt(co.linked_owner_co.amount)} ${esc(co.linked_owner_co.status || '')})</span>` : ''}</p>` : ''}
        ${isSubCo(co) && co.owner_sub_variance != null && co.linked_owner_co_id ? `<p><span class="text-zinc-500">Variance vs Owner CO</span><br><span class="font-mono ${co.owner_sub_variance >= 0 ? 'text-amber-400' : 'text-red-400'}">${fmt(co.owner_sub_variance)}</span> <span class="text-[10px] text-zinc-500">(sub − owner)</span></p>` : ''}
        ${!isSubCo(co) && (co.linked_sub_change_orders || []).length ? `<div class="mt-2"><div class="text-xs text-zinc-500 uppercase tracking-wide mb-1">Linked Sub Change Orders</div>
          <div class="space-y-1">${co.linked_sub_change_orders.map(s => `<div class="flex justify-between gap-2 text-xs"><span>${subCoLink(s.id, s.number)}${s.auto_generated ? ' <span class="text-sky-400">AUTO</span>' : ''} · ${esc(s.company_name || '')}</span><span class="font-mono">${fmt(s.amount)}</span><span>${statusBadge(s.status)}</span></div>`).join('')}
          ${co.owner_sub_variance != null ? `<div class="text-xs mt-2 pt-2 border-t border-zinc-800 flex justify-between"><span class="text-zinc-500">Owner vs linked sub total</span><span class="font-mono ${co.owner_sub_variance >= 0 ? 'text-emerald-400' : 'text-red-400'}">${fmt(co.owner_sub_variance)}</span></div>` : ''}
        </div>` : ''}
        <p><span class="text-zinc-500">Linked RFI</span><br>${co.linked_rfi_id ? `<a href="/rfis" class="text-sky-400 hover:underline">${esc(linkedRfiLabel(co.linked_rfi_id))}</a>` : '—'}</p>
        <p><span class="text-zinc-500">Linked commitment</span><br>${esc(co.linked_commitment_ref || '—')}</p>
        <p><span class="text-zinc-500">Sage / SOV</span><br>${co.sov_synced_at ? '<span class="text-emerald-400">Synced to Budget &amp; SOV</span>' : esc(co.sage_sync_status || '—')}</p>
        ${isSubCo(co) && co.status === 'Approved' ? `<p><span class="text-zinc-500">Billing variance</span><br><span class="font-mono ${(co.billing_variance || 0) === 0 ? 'text-emerald-400' : ((co.billing_variance || 0) > 0 ? 'text-amber-400' : 'text-red-400')}">${co.billing_variance != null ? fmt(co.billing_variance) : '—'}</span> <span class="text-[10px] text-zinc-500">(approved − billed)</span></p>` : ''}
      </div>
      ${(co.approval_history || []).length ? `<div class="mt-4"><div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Approval history</div>
        <div class="space-y-2">${co.approval_history.map(h => `<div class="text-xs border border-zinc-800 rounded p-2"><div class="text-zinc-400">${esc(h.user_name || '')} · ${esc(h.action)} · ${h.at ? new Date(h.at).toLocaleString() : ''}</div>${h.comment ? `<div class="mt-1">${esc(h.comment)}</div>` : ''}</div>`).join('')}</div></div>` : ''}
      <div class="mt-4">
        <div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Cost code allocations</div>
        <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left py-1">Code</th><th class="text-left py-1">Type</th><th class="text-left py-1">Description</th><th class="text-right py-1">Amount</th></tr></thead>
        <tbody>${allocs || '<tr><td colspan="4" class="py-3 text-zinc-500">No allocations</td></tr>'}</tbody></table>
      </div>
      <div class="mt-4">
        <div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Attachments</div>
        <p>${atts}</p>
      </div>`;
    document.getElementById('drawerBody').innerHTML = reviewBanner + bodyHtml;
    document.getElementById('drawerActions').innerHTML = `
      ${showSubmit ? `<button type="button" onclick="CasePMChangeOrders.workflowCo(${co.id},'submit')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-md text-sm">Submit for Approval</button>` : ''}
      ${canApprove() ? `<button type="button" onclick="CasePMChangeOrders.${isSubCo(co) ? 'editSubCo' : 'editCo'}(${co.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>
      <button type="button" onclick="CasePMChangeOrders.deleteCo(${co.id})" class="px-4 py-2 bg-red-950 hover:bg-red-900 border border-red-800 rounded-md text-sm text-red-300">Delete</button>` : ''}
      <button type="button" onclick="CasePMChangeOrders.closeDrawer()" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm text-zinc-400">Close</button>`;
    if (showApprove) {
      openApprovalModal(co.id, 'approve');
      return;
    }
    openDrawer();
  }

  function renderDrawerPco(p) {
    document.getElementById('drawerTitle').textContent = `${p.number} — ${p.title || 'PCO'}`;
    const showApprove = ['Pricing', 'Pending Review'].includes(p.status) && canActOnBall(p.ball_in_court_role);
    const reviewBanner = showApprove ? `
      <div class="mb-6 p-4 rounded-lg bg-emerald-950/50 border-2 border-emerald-600 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div class="text-emerald-400 font-semibold">PCO review needed</div>
          <div class="text-xs text-zinc-400 mt-1">Ball in court: ${esc(p.ball_in_court_role || '—')} · ${esc(p.status)}</div>
        </div>
        ${reviewButtonHtml(p.id, 'Review PCO', 'openPcoReviewModal')}
      </div>` : '';
    const allocs = (p.allocations || []).map(a =>
      `<tr class="border-b border-zinc-800"><td class="py-2 font-mono text-xs">${esc(a.cost_code)}</td><td class="py-2 text-xs text-zinc-400">${esc(a.cost_type || '—')}</td><td class="py-2">${esc(a.description || '')}</td><td class="py-2 text-right font-mono">${fmt(a.amount)}</td></tr>`
    ).join('');
    const atts = (p.attachments || []).map(a =>
      `<a href="${attachmentHref(p.id, a, 'pco')}" target="_blank" rel="noopener" class="text-emerald-400 hover:underline">${attachmentLabel(a)}</a>`
    ).join(' · ') || '—';
    const bodyHtml = `
      <div class="space-y-2">
        <p><span class="text-zinc-500">Status</span><br>${statusBadge(p.status)}</p>
        <p><span class="text-zinc-500">ROM</span><br><span class="font-mono text-lg">${fmt(p.estimated_amount)}</span></p>
        <p><span class="text-zinc-500">Company</span><br>${esc(p.company_name || '—')}</p>
        <p><span class="text-zinc-500">Contact</span><br>${esc(p.contact_name || '—')}</p>
        <p><span class="text-zinc-500">Description</span><br>${esc(p.description || '—')}</p>
        <p><span class="text-zinc-500">Linked RFI</span><br>${p.linked_rfi_id ? `<a href="/rfis" class="text-sky-400 hover:underline">${esc(linkedRfiLabel(p.linked_rfi_id))}</a>` : '—'}</p>
        ${p.change_order_id ? `<p><span class="text-zinc-500">Promoted to CO</span><br>#${p.change_order_id}</p>` : ''}
      </div>
      <div class="mt-4">
        <div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Allocations</div>
        <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left py-1">Code</th><th class="text-left py-1">Type</th><th class="text-left py-1">Description</th><th class="text-right py-1">Amount</th></tr></thead>
        <tbody>${allocs || '<tr><td colspan="4" class="py-3 text-zinc-500">No allocations</td></tr>'}</tbody></table>
      </div>
      <div class="mt-4">
        <div class="text-xs text-zinc-500 uppercase tracking-wide mb-2">Attachments</div>
        <p class="text-xs">${atts}</p>
        <label class="mt-2 inline-flex items-center gap-2 text-xs text-zinc-400 cursor-pointer">
          <input type="file" id="pcoDrawerAttachmentInput" class="text-xs file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:bg-zinc-700 file:text-white" onchange="CasePMChangeOrders.uploadPcoDrawerAttachment(${p.id})">
          Upload file
        </label>
      </div>`;
    document.getElementById('drawerBody').innerHTML = reviewBanner + bodyHtml;
    document.getElementById('drawerActions').innerHTML = `
      ${p.status === 'Open' ? `<button type="button" onclick="CasePMChangeOrders.pcoWorkflow(${p.id},'submit')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-md text-sm">Submit</button>` : ''}
      ${p.status !== 'Promoted' && p.status !== 'Void' ? `<button type="button" onclick="CasePMChangeOrders.promotePco(${p.id})" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm">Promote to CO</button>` : ''}
      <button type="button" onclick="CasePMChangeOrders.editPco(${p.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>
      <button type="button" onclick="CasePMChangeOrders.closeDrawer()" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm text-zinc-400">Close</button>`;
    if (showApprove) {
      openPcoReviewModal(p.id);
      return;
    }
    openDrawer();
  }

  function openPcoReviewModal(pcoId) {
    closeDrawer();
    const p = state.pcos.find(x => x.id === pcoId) || (state.drawerRecord?.id === pcoId ? state.drawerRecord : null);
    if (!p) return;
    if (typeof global.CasePMApprovalResponder === 'undefined') {
      pcoWorkflow(pcoId, 'approve');
      return;
    }
    const allocLines = (p.allocations || []).map(a =>
      `<div class="flex justify-between gap-3 text-xs"><span class="font-mono text-emerald-400">${esc(a.cost_code)}</span><span class="text-zinc-400">${esc(a.cost_type || '')}</span><span class="font-mono">${fmt(a.amount)}</span></div>`
    ).join('') || '<div class="text-zinc-500 text-xs">No allocations</div>';
    global.CasePMApprovalResponder.openLocal({
      module: 'PCO',
      entityId: pcoId,
      title: `${p.number} — ${p.title || 'Potential Change Order'}`,
      status: p.status,
      ball: p.ball_in_court_role,
      summaryHtml: `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">ROM</span><span class="font-mono text-emerald-400">${fmt(p.estimated_amount)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Company</span><span>${esc(p.company_name || '—')}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Status</span><span>${statusBadge(p.status)}</span></div>
        <div class="pt-2 border-t border-zinc-800 mt-2"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Allocations</div>${allocLines}</div>
        ${p.description ? `<div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Description</div><p class="text-sm whitespace-pre-wrap">${esc(p.description)}</p></div>` : ''}`,
      attachments: p.attachments || [],
      actions: [
        { action: 'approve', label: 'Approve Step', style: 'primary' },
        { action: 'reject', label: 'Reject', requires_comment: true, style: 'danger' },
      ],
      onSubmit: async (action, comment) => {
        if (action === 'reject') {
          await api(`/api/pcos/${pcoId}/workflow`, { method: 'POST', body: JSON.stringify({ action, comments: comment }) });
        } else {
          await api(`/api/pcos/${pcoId}/workflow`, { method: 'POST', body: JSON.stringify({ action }) });
        }
        await loadPcos();
        closeDrawer();
      },
    });
  }

  async function pcoWorkflow(id, action) {
    if (action === 'reject') {
      const comments = await coPrompt('Rejection reason:', '', { title: 'Reject PCO' });
      if (!comments) return;
      await api(`/api/pcos/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action, comments }) });
    } else {
      await api(`/api/pcos/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action }) });
    }
    await loadPcos();
    toast(`PCO ${action} complete`);
  }

  async function uploadPcoAttachment(pcoId, file) {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`/api/pcos/${pcoId}/attachments`, { method: 'POST', body: fd, credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Upload failed');
    return json;
  }

  async function uploadPcoDrawerAttachment(pcoId) {
    const input = document.getElementById('pcoDrawerAttachmentInput');
    if (!input?.files?.length) return;
    try {
      for (const file of input.files) {
        await uploadPcoAttachment(pcoId, file);
      }
      input.value = '';
      await viewPco(pcoId);
      toast('Attachment uploaded');
    } catch (err) {
      alert(err.message);
    }
  }

  async function promotePco(id) {
    const p = state.pcos.find(x => x.id === id);
    if (!p) return;
    const allocCheck = validateAllocations(p.allocations || [], { requireRows: true, requireAmount: true });
    if (!allocCheck.ok) {
      alert(`${allocCheck.message}\n\nEdit the PCO and complete cost code allocations before promoting.`);
      return;
    }
    if (!(await coConfirm(`Promote PCO ${p.number} to a formal Change Order?`, { title: 'Promote PCO' }))) return;
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

  async function openCoItem(id) {
    const cached = state.changeOrders.find(c => c.id === id);
    if (cached && coNeedsReview(cached)) {
      openApprovalModal(id, 'approve');
      return;
    }
    await viewCo(id);
  }

  async function openPcoItem(id) {
    const cached = state.pcos.find(p => p.id === id);
    if (cached && pcoNeedsReview(cached)) {
      openPcoReviewModal(id);
      return;
    }
    await viewPco(id);
  }

  async function viewCo(id) {
    try {
      const co = await api(`/api/change-orders/${id}`);
      state.drawerRecord = co;
      state.drawerType = 'co';
      if (coNeedsReview(co)) {
        openApprovalModal(id, 'approve');
        return;
      }
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
      if (pcoNeedsReview(p)) {
        openPcoReviewModal(id);
        return;
      }
      renderDrawerPco(p);
    } catch (err) {
      alert(err.message);
    }
  }

  async function deleteCo(id) {
    const co = state.changeOrders.find(c => c.id === id) || (state.drawerRecord?.id === id ? state.drawerRecord : null);
    if (!co) return;
    const approved = co.status === 'Approved';
    const unlock = devUnlock();
    const prompt = approved && !unlock
      ? `DELETE approved change order ${co.number}?\n\nThis is for testing only. Type DELETE to confirm.`
      : `Delete change order ${co.number}?`;
    if (approved && !unlock) {
      const typed = await coPrompt(prompt, '', { title: 'Confirm delete', label: 'Type DELETE to confirm' });
      if (typed !== 'DELETE') return;
    } else if (!(await coConfirm(prompt, { title: 'Confirm delete', danger: true }))) {
      return;
    }
    try {
      const url = `/api/change-orders/${id}${approved ? '?force=1' : ''}`;
      const json = await api(url, { method: 'DELETE' });
      if (json.reconcile_result && typeof CasePMAccountingReconcile !== 'undefined') {
        CasePMAccountingReconcile.applyReconcileResult(json.reconcile_result);
      }
      closeDrawer();
      await loadChangeOrders();
      await loadDashboard();
      toast(`${co.number} deleted`);
    } catch (err) {
      if (err.message && err.message.includes('force')) {
        const typed = await coPrompt(`${err.message}\n\nType DELETE to force-delete this approved CO for testing.`, '', {
          title: 'Force delete',
          label: 'Type DELETE to confirm',
        });
        if (typed !== 'DELETE') return;
        try {
          await api(`/api/change-orders/${id}?force=1`, { method: 'DELETE' });
          closeDrawer();
          await loadChangeOrders();
          await loadDashboard();
          toast(`${co.number} deleted`);
        } catch (e2) {
          alert(e2.message);
        }
      } else {
        alert(err.message);
      }
    }
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-16 right-6 z-[70] px-4 py-2 rounded-md bg-emerald-900 text-emerald-100 text-sm shadow-lg';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2800);
  }

  const CO_BASE_PRINT_COLUMNS = [
    { key: 'number', label: 'CO #', width: '6%', mono: true },
    { key: 'date', label: 'Date', width: '6%', align: 'center' },
    { key: 'title', label: 'Title / Description', width: '16%', maxLen: 90 },
    { key: 'company_name', label: 'Company', width: '10%', maxLen: 80 },
    { key: 'contact_name', label: 'Contact', width: '8%', maxLen: 70 },
    { key: 'cost_code', label: 'Cost<br>Code', width: '7%', mono: true },
    { key: 'amount', label: 'Amount', width: '8%', align: 'right' },
    { key: 'status', label: 'Status', width: '8%', align: 'center' },
    { key: 'ball_in_court_role', label: 'Ball<br>in Court', width: '8%', align: 'center' },
  ];

  const CO_OPTIONAL_PRINT_FIELDS = [
    { key: 'description', label: 'Full Description', default: false },
    { key: 'schedule_impact_days', label: 'Schedule Days', default: false },
    { key: 'reason', label: 'Reason', default: false },
    { key: 'priority', label: 'Priority', default: false },
    { key: 'contract_type', label: 'Contract Type', default: false },
    { key: 'sage_sync_status', label: 'Sage Sync', default: false },
    { key: 'sov_synced_at', label: 'SOV Synced', default: false },
    { key: 'notes', label: 'Notes', default: false },
  ];

  const PCO_BASE_PRINT_COLUMNS = [
    { key: 'number', label: 'PCO #', width: '6%', mono: true },
    { key: 'date', label: 'Date', width: '6%', align: 'center' },
    { key: 'title', label: 'Title / Description', width: '18%', maxLen: 90 },
    { key: 'company_name', label: 'Company', width: '10%', maxLen: 80 },
    { key: 'contact_name', label: 'Contact', width: '8%', maxLen: 70 },
    { key: 'estimated_amount', label: 'ROM', width: '8%', align: 'right' },
    { key: 'status', label: 'Status', width: '8%', align: 'center' },
    { key: 'ball_in_court_role', label: 'Ball<br>in Court', width: '8%', align: 'center' },
  ];

  const PCO_OPTIONAL_PRINT_FIELDS = [
    { key: 'reason', label: 'Reason', default: false },
    { key: 'priority', label: 'Priority', default: false },
    { key: 'notes', label: 'Notes', default: false },
    { key: 'change_order_id', label: 'Linked CO', default: false },
  ];

  function coPrintValue(co, key) {
    if (key === 'date') return fmtDate(co.date);
    if (key === 'amount') return fmt(co.amount);
    if (key === 'title') return co.title || co.description || '';
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
    if (global.CasePMPrint && global.CasePMPrint.getProjectMeta) {
      return global.CasePMPrint.getProjectMeta();
    }
    const nameEl = document.getElementById('currentProjectName');
    return {
      name: (nameEl?.textContent || '').trim() || 'Project',
      number: projectId() || '',
      location: '',
    };
  }

  function resolvePrintColumns(baseCols, optionalFieldDefs, selectedOptionalKeys) {
    const optional = optionalFieldDefs
      .filter(f => (selectedOptionalKeys || []).includes(f.key))
      .map(f => ({ key: f.key, label: f.label.replace(/ /g, '<br>'), width: '7%' }));
    return [...baseCols, ...optional];
  }

  function buildRegisterSection(title, columns, rows, valueFn) {
    const data = rows.map(r => {
      const obj = {};
      columns.forEach(c => { obj[c.key] = valueFn(r, c.key); });
      return obj;
    });
    return {
      title,
      columns: columns.map(c => ({
        key: c.key,
        label: c.label,
        width: c.width,
        align: c.align,
        mono: c.mono,
        maxLen: c.maxLen,
      })),
      rows: data,
      emptyMessage: `No ${title.toLowerCase()} records.`,
    };
  }

  async function printLog() {
    if (typeof global.CasePMPrint === 'undefined') {
      alert('Print module not loaded.');
      return;
    }

    const picked = await global.CasePMPrint.showFieldPicker({
      title: 'Print Change Order Log',
      note: 'Standard register columns are always included. Choose extra columns to append on the right. CO and PCO logs use the same optional field names where applicable.',
      logTypes: [
        { value: 'cos', label: 'Change Orders' },
        { value: 'pcos', label: 'PCO Log' },
        { value: 'both', label: 'Both' },
      ],
      fields: [...CO_OPTIONAL_PRINT_FIELDS, ...PCO_OPTIONAL_PRINT_FIELDS.filter(f => !CO_OPTIONAL_PRINT_FIELDS.find(c => c.key === f.key))],
    });
    if (!picked) return;

    const meta = getCoPrintMeta();
    const sections = [];
    if (picked.logType === 'cos' || picked.logType === 'both') {
      const cols = resolvePrintColumns(CO_BASE_PRINT_COLUMNS, CO_OPTIONAL_PRINT_FIELDS, picked.fields);
      sections.push(buildRegisterSection('CHANGE ORDER LOG', cols, filteredCos(), coPrintValue));
    }
    if (picked.logType === 'pcos' || picked.logType === 'both') {
      const cols = resolvePrintColumns(PCO_BASE_PRINT_COLUMNS, PCO_OPTIONAL_PRINT_FIELDS, picked.fields);
      sections.push(buildRegisterSection('POTENTIAL CHANGE ORDER LOG', cols, filteredPcos(), pcoPrintValue));
    }

    const html = global.CasePMPrint.buildPrintDocument({ meta, sections, rowsPerPage: 26 });
    if (global.CasePMOutput) {
      await global.CasePMOutput.deliverHtml({
        title: 'Change Order Log',
        html,
        filenameBase: `Change_Orders_${projectId() || 'project'}`,
        sourceModule: 'change_orders',
        systemFolderKey: 'contracts',
        subfolder: 'Exports',
        printOptions: { bodyHtml: html, containerId: 'coPrintSheet', bodyClass: 'printing-co-log' },
      });
      return;
    }
    global.CasePMPrint.triggerPrintPreview(html, {
      containerId: 'coPrintSheet',
      bodyClass: 'printing-co-log',
    });
  }

  async function exportExcel() {
    if (typeof XLSX === 'undefined') { alert('Excel library not loaded'); return; }
    const data = state.changeOrders.map(co => ({
      Number: co.number, Date: co.date, Title: co.title, Company: co.company_name,
      Amount: co.amount, Status: co.status, 'Ball In Court': co.ball_in_court_role,
      'Schedule Days': co.schedule_impact_days, 'SOV Synced': co.sov_synced_at ? 'Yes' : 'No',
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Change Orders');
    const filename = `Change_Orders_${projectId() || 'project'}.xlsx`;
    if (global.CasePMOutput) {
      const buf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
      await global.CasePMOutput.deliverBlob({
        title: 'Export Change Orders',
        blob: new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
        mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename,
        filenameBase: `Change_Orders_${projectId() || 'project'}`,
        sourceModule: 'change_orders',
        systemFolderKey: 'contracts',
        subfolder: 'Exports',
        fileLabel: 'Excel (.xlsx)',
      });
      return;
    }
    XLSX.writeFile(wb, filename);
  }

  function openSageLog() {
    let modal = document.getElementById('coSageLogModal');
    if (!modal) {
      modal = document.createElement('dialog');
      modal.id = 'coSageLogModal';
      modal.className = 'modal bg-zinc-900 border border-zinc-700 rounded-lg p-0 text-white max-w-2xl w-full';
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
    openDialog(modal);
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
      renderSubCoTable();
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
    if (typeof CasePMAccountingReconcile !== 'undefined') {
      await CasePMAccountingReconcile.initAndReconcile().catch(() => {});
    } else {
      if (typeof CasePMBudgetSync !== 'undefined') await CasePMBudgetSync.init().catch(() => {});
      if (typeof CasePMPayAppSync !== 'undefined') await CasePMPayAppSync.init().catch(() => {});
    }
    loadCompaniesFromStorage();
    await loadCostCodes();
    await Promise.all([loadLinkOptions(), loadDashboard(), loadChangeOrders(), loadPcos(), loadSageLog()]);
    bindFilters();
    bindAttachmentBrowse();
    applyCoTabPermissions();
    switchTab('cos');
    global.addEventListener('casepm:approval-responded', async (e) => {
      const detail = e.detail || {};
      if (!detail.local) await applyCoSync(detail);
      loadChangeOrders();
      loadDashboard();
    });
    const params = new URLSearchParams(window.location.search);
    if (params.get('respond') === '1' && params.get('co_id')) {
      const id = parseInt(params.get('co_id'), 10);
      if (id && typeof global.CasePMApprovalResponder !== 'undefined') {
        await global.CasePMApprovalResponder.open('co', id);
      } else if (id) {
        await viewCo(id);
      }
    } else if (params.get('open') === '1' && params.get('co_id')) {
      const id = parseInt(params.get('co_id'), 10);
      if (id) await viewCo(id);
    }
    global.addEventListener('casepm:co-approved', () => {
      loadChangeOrders();
      loadDashboard();
    });
    global.addEventListener('casepm:accounting-reconciled', () => {
      loadChangeOrders();
      loadDashboard();
    });
    global.addEventListener('casepm:developer-unlock-changed', () => {
      if (typeof CasePMDeveloperUnlock !== 'undefined') CasePMDeveloperUnlock.sweep(document);
    });
  }

  global.CasePMChangeOrders = {
    init,
    switchTab,
    projectId,
    openModal,
    saveModal,
    editCo: id => api(`/api/change-orders/${id}`).then(openModal.bind(null, 'co')).catch(e => alert(e.message)),
    editPco: id => api(`/api/pcos/${id}`).then(openModal.bind(null, 'pco')).catch(e => alert(e.message)),
    viewCo, viewPco, openCoItem, openPcoItem, workflowCo, pcoWorkflow, openPcoReviewModal,
    applyCoSync, resyncSov, openApprovalModal, confirmApprovalAction, closeDrawer, promotePco, deleteCo,
    uploadPcoAttachment, uploadPcoDrawerAttachment,
    addAllocRow: () => { state.allocationRows.push({ cost_code: '', cost_type: '', amount: 0, description: '' }); renderAllocationRows(); },
    removeAllocRow: idx => { state.allocationRows.splice(idx, 1); renderAllocationRows(); },
    onCompanyChange, onContactChange, onAllocCostCodeChange, updateAllocationTotal, exportExcel, printLog, openSageLog,
    newPco: () => openModal('pco', null),
    newCo: () => openModal('co', null),
    newSubCo: () => openModal('sub', { contract_type: 'Subcontract', sub_co_kind: 'Contract Add' }),
    editSubCo: id => api(`/api/change-orders/${id}`).then(r => openModal('sub', r)).catch(e => alert(e.message)),
    onSubCoKindChange,
    onLinkedCommitmentChange,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
