/**
 * Case PM — Commitments module (PO, Subcontract, Supply, Service)
 * AIA forms · Sage 300 · DocuSign-ready
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

  function setMoneyVal(id, amount) {
    const el = document.getElementById(id);
    if (!el) return;
    if (global.CasePMMoney) CasePMMoney.setMoneyInput(el, amount);
    else el.value = amount || '';
  }

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
    'Project Manager': ['Project Manager', 'Admin', 'Developer'],
    'Contractor Accounting': ['Contractor Accounting', 'Admin', 'Developer'],
    'Owner': ['Owner', 'Admin', 'Developer'],
    'Creator': ['Project Manager', 'Admin', 'Developer', 'Company User'],
  };

  let state = {
    commitments: [],
    costCodes: [],
    companies: [],
    stats: {},
    sageLog: [],
    auditLog: [],
    integrations: null,
    filter: { search: '', status: '', type: '' },
    allocationRows: [],
    drawerRecord: null,
    modalOriginalType: null,
    modalStatus: 'Draft',
    aiaContract: null,
    portalLoaded: false,
  };

  function projectCtx() {
    return global.COMMITMENT_PROJECT_CTX || {};
  }

  function isAdmin() {
    const p = global.CASEPM_PORTAL;
    if (p) {
      if (p.isAdmin === true) return true;
      if (p.role === 'Admin' || p.role === 'Developer') return true;
      if (p.permissions && p.permissions.modules === '*') return true;
    }
    return false;
  }

  function userRole() {
    return (global.CASEPM_PORTAL && global.CASEPM_PORTAL.role) || '';
  }

  function userName() {
    return (global.CASEPM_PORTAL && (global.CASEPM_PORTAL.full_name || global.CASEPM_PORTAL.email)) || 'User';
  }

  function canActOnBall(role) {
    if (!role) return false;
    if (isAdmin()) return true;
    return (ROLE_MAP[role] || [role]).includes(userRole());
  }

  function canDeleteRecord(c) {
    return isAdmin() && c && c.id;
  }

  function isDirectlyDeletable(c) {
    return DELETABLE_STATUSES.includes(c.status);
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
    if (global.CasePMActivityLog) {
      CasePMActivityLog.log(action, typeof details === 'string' ? details : (details.summary || details.description || ''), 'commitments', {
        category: details.category || 'update',
        entity_ref: details.number || details.commitment_number || '',
        company_name: details.company_name || '',
        metadata: details,
      });
    }
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
    const types = (global.CasePMCommitmentSageSync && CasePMCommitmentSageSync.COMMITMENT_SAGE_EVENTS) || [
      'CommitmentApproved', 'CommitmentSubmitted', 'CommitmentDocuSignSent',
      'CommitmentApprovalStep', 'CommitmentRejected', 'CommitmentVoided', 'CommitmentUpdated', 'CommitmentExecuted',
    ];
    try {
      if (global.CasePMCommitmentSageSync) {
        state.sageLog = await CasePMCommitmentSageSync.fetchSageEvents(40);
      } else {
        const res = await fetch(`/api/sage/sync-events?project_id=${pid}&limit=40`, { credentials: 'same-origin' });
        const json = await res.json();
        state.sageLog = (json.events || []).filter(e => types.includes(e.event_type));
      }
    } catch { state.sageLog = []; }
    renderSageBar();
  }

  async function loadIntegrations() {
    if (global.CasePMCommitmentSageSync) {
      state.integrations = await CasePMCommitmentSageSync.fetchIntegrationStatus();
    }
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

  function reviewButtonHtml(id, label) {
    const text = label || 'Review & Respond';
    return `<button type="button" onclick="event.stopPropagation(); CasePMCommitments.openReviewModal(${id})" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-semibold whitespace-nowrap shadow-md"><i class="fa-solid fa-clipboard-check mr-1"></i>${text}</button>`;
  }

  function commitmentNeedsReview(c) {
    if (!c) return false;
    return ['Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner'].includes(c.status) && canActOnBall(c.ball_in_court_role);
  }

  async function openCommitmentItem(id) {
    const cached = state.commitments.find(x => x.id === id);
    if (cached && commitmentNeedsReview(cached)) {
      openReviewModal(id);
      return;
    }
    await view(id);
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
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer" onclick="CasePMCommitments.openCommitmentItem(${c.id})">
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
            ${showSubmit ? `<button onclick="CasePMCommitments.workflow(${c.id},'submit')" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 rounded-md text-xs font-medium">Submit</button>` : ''}
            ${showApprove ? reviewButtonHtml(c.id) : ''}
            <button onclick="CasePMCommitments.edit(${c.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded"><i class="fa-solid fa-edit"></i></button>
            ${isAdmin() ? `<button onclick="CasePMCommitments.deleteCommitment(${c.id})" class="p-1.5 text-red-400 hover:bg-zinc-800 rounded" title="Delete (Admin)"><i class="fa-solid fa-trash"></i></button>` : ''}
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  function renderSageBar() {
    const el = document.getElementById('comSageStatusText');
    const intEl = document.getElementById('comIntegrationStatus');
    if (!el) return;
    const ctx = projectCtx();
    const job = ctx.sage_job || ctx.number || '—';
    const latest = state.sageLog[0];
    el.textContent = latest
      ? `Sage 300 · Job ${job} · ${latest.event_type} · ${latest.status} · ${new Date(latest.created_at).toLocaleString()}`
      : `Sage 300 · Job ${job} · No commitment sync events yet`;
    if (intEl && state.integrations) {
      const s = state.integrations.sage_300?.configured ? 'Sage ✓' : 'Sage ○';
      const a = state.integrations.aia?.catina?.configured ? 'AIA Catina ✓' : 'AIA Catina ○';
      const d = state.integrations.docusign?.configured ? 'DocuSign ✓' : 'DocuSign ○';
      intEl.textContent = `${s} · ${a} · ${d}`;
    }
  }

  async function openSageSyncLogModal() {
    await loadSageLog();
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
          <td class="py-2 pr-3 text-xs ${e.status === 'queued' ? 'text-amber-400' : e.status === 'error' ? 'text-red-400' : e.status === 'simulated' ? 'text-sky-400' : 'text-emerald-400'}">${esc(e.status)}</td>
          <td class="py-2 text-xs text-zinc-300">${esc(e.message || '')}</td>
          <td class="py-2 text-right">${e.status === 'error' ? `<button type="button" onclick="CasePMCommitments.retrySageEvent(${e.id})" class="text-xs text-amber-400 underline">Retry</button>` : ''}</td>
        </tr>`).join('')
      : '<tr><td colspan="5" class="py-6 text-center text-zinc-500 text-sm">No Sage sync events recorded yet.</td></tr>';
    modal.innerHTML = `
      <div class="p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold">Sage 300 Commitment Sync Log</h3>
          <button type="button" onclick="document.getElementById('comSageSyncLogModal').close()" class="text-zinc-400 hover:text-white"><i class="fa-solid fa-times"></i></button>
        </div>
        <p class="text-xs text-zinc-400 mb-3">PO → AP · Subcontracts → Subcontracts module · Full allocation/vendor payloads when SAGE_API_URL is configured.</p>
        <div class="max-h-80 overflow-auto">
          <table class="w-full text-left"><thead><tr class="text-[10px] text-zinc-500 uppercase"><th class="pb-2">Time</th><th class="pb-2">Event</th><th class="pb-2">Status</th><th class="pb-2">Detail</th><th class="pb-2"></th></tr></thead>
          <tbody id="comSageLogBody">${rows}</tbody></table>
        </div>
      </div>`;
    modal.showModal();
  }

  async function retrySageEvent(eventId) {
    try {
      if (global.CasePMCommitmentSageSync) {
        await CasePMCommitmentSageSync.retryEvent(eventId);
      }
      await loadSageLog();
      toast('Sage event retried');
    } catch (err) {
      alert(err.message);
    }
  }

  async function syncSageForCommitment(id) {
    try {
      const json = global.CasePMCommitmentSageSync
        ? await CasePMCommitmentSageSync.syncCommitment(id)
        : await api(`/api/commitments/${id}/sage-sync`, { method: 'POST', body: '{}' });
      await refreshAll();
      if (state.drawerRecord?.id === id) renderDrawer(json.commitment);
      toast(`Sage sync: ${json.event?.status || 'queued'}`);
    } catch (err) {
      alert(err.message);
    }
  }

  async function openCatina(id) {
    try {
      await CasePMCommitmentSageSync.openCatina(id);
      toast('Opened AIA Contract Documents (Catina)');
    } catch (err) {
      alert(err.message);
    }
  }

  async function registerAiaDocument(id) {
    const docUrl = prompt('Paste the AIA Catina document URL (or document ID):');
    if (!docUrl) return;
    const isUrl = docUrl.startsWith('http');
    try {
      const json = await CasePMCommitmentSageSync.registerAiaDocument(id, isUrl ? null : docUrl, isUrl ? docUrl : null);
      await refreshAll();
      if (state.drawerRecord?.id === id) renderDrawer(json.commitment);
      toast('Official AIA document linked');
    } catch (err) {
      alert(err.message);
    }
  }

  function showIntegrationsModal() {
    const i = state.integrations || {};
    const modal = document.createElement('dialog');
    modal.className = 'bg-zinc-900 border border-zinc-700 rounded-lg p-0 text-white max-w-lg w-full';
    modal.innerHTML = `
      <div class="p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-semibold">Integrations</h3>
          <button type="button" class="text-zinc-400 hover:text-white" onclick="this.closest('dialog').close(); this.closest('dialog').remove()"><i class="fa-solid fa-times"></i></button>
        </div>
        <div class="space-y-4 text-sm">
          <div class="border border-zinc-700 rounded-md p-3">
            <div class="font-medium text-emerald-400 mb-1">Sage 300 CRE</div>
            <p class="text-xs text-zinc-400">${i.sage_300?.configured ? 'SAGE_API_URL configured — live posting enabled.' : 'Set SAGE_API_URL + SAGE_API_KEY on server. Events log as simulated until configured.'}</p>
            <p class="text-xs text-zinc-500 mt-1">Project sage_job_number required per project.</p>
          </div>
          <div class="border border-zinc-700 rounded-md p-3">
            <div class="font-medium text-sky-400 mb-1">AIA Contract Documents (Catina)</div>
            <p class="text-xs text-zinc-400">Official licensed AIA forms. Use <strong>Open in Catina</strong> on a commitment, then <strong>Link AIA Document</strong> to attach the executed document.</p>
            <p class="text-xs text-zinc-500 mt-1">Env: AIA_CATINA_ORG_ID or AIA_CATINA_ENABLED=1</p>
          </div>
          <div class="border border-zinc-700 rounded-md p-3">
            <div class="font-medium text-indigo-400 mb-1">DocuSign</div>
            <p class="text-xs text-zinc-400">${i.docusign?.configured ? 'DocuSign JWT configured — live envelopes on send.' : 'Simulated envelope IDs until DOCUSIGN_* env vars set. Prefer Catina for official AIA e-sign.'}</p>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.showModal();
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
        const id = c.server_id != null && c.server_id !== '' ? c.server_id : (c.id || name);
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

  function contractFormKey() {
    const form = document.getElementById('modalAiaForm')?.value;
    const type = document.getElementById('modalType')?.value;
    if (global.CasePMAiaTemplates) return global.CasePMAiaTemplates.resolveFormKey(form, type);
    return form || 'A401';
  }

  function readContractFromForm() {
    const sections = [];
    document.querySelectorAll('[data-contract-section-id]').forEach(el => {
      const id = el.dataset.contractSectionId;
      const titleEl = document.querySelector(`[data-contract-title="${id}"]`);
      const bodyEl = document.querySelector(`[data-contract-body="${id}"]`);
      const enabledEl = document.querySelector(`[data-contract-enabled="${id}"]`);
      if (!bodyEl) return;
      sections.push({
        id,
        title: titleEl?.value || '',
        body: bodyEl.value || '',
        enabled: enabledEl ? enabledEl.checked : true,
        builtin: el.dataset.contractBuiltin === '1',
      });
    });
    return {
      form: contractFormKey(),
      inclusions: document.getElementById('modalInclusions')?.value || '',
      exclusions: document.getElementById('modalExclusions')?.value || '',
      scope_supplement: document.getElementById('modalScopeSupplement')?.value || '',
      sections,
    };
  }

  function renderContractSections() {
    const container = document.getElementById('contractSectionsList');
    if (!container) return;
    const contract = state.aiaContract;
    if (!contract || !contract.sections) {
      container.innerHTML = '<p class="text-xs text-zinc-500">Select an AIA form to load contract articles.</p>';
      return;
    }
    container.innerHTML = contract.sections.map((s, idx) => `
      <div class="border border-zinc-700 rounded-md p-3 bg-zinc-900" data-contract-section-id="${esc(s.id)}" data-contract-builtin="${s.builtin ? '1' : '0'}">
        <div class="flex items-center gap-2 mb-2">
          <input type="checkbox" data-contract-enabled="${esc(s.id)}" ${s.enabled !== false ? 'checked' : ''} class="rounded border-zinc-600">
          <input type="text" data-contract-title="${esc(s.id)}" value="${esc(s.title)}" class="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs font-semibold">
          ${!s.builtin ? `<button type="button" onclick="CasePMCommitments.removeContractSection('${esc(s.id)}')" class="px-2 py-1 text-xs text-red-400 hover:bg-red-900/40 rounded">Remove</button>` : ''}
        </div>
        <textarea data-contract-body="${esc(s.id)}" rows="8" class="w-full bg-zinc-950 border border-zinc-700 rounded-md px-3 py-2 text-xs font-mono leading-relaxed">${esc(s.body || '')}</textarea>
      </div>`).join('');
  }

  function loadContractTemplate(forceReset) {
    if (!global.CasePMAiaTemplates) return;
    const key = contractFormKey();
    if (forceReset || !state.aiaContract) {
      state.aiaContract = global.CasePMAiaTemplates.cloneTemplate(key);
    } else {
      state.aiaContract = global.CasePMAiaTemplates.mergeContract(state.aiaContract, key);
    }
    document.getElementById('modalInclusions').value = state.aiaContract.inclusions || '';
    document.getElementById('modalExclusions').value = state.aiaContract.exclusions || '';
    document.getElementById('modalScopeSupplement').value = state.aiaContract.scope_supplement || '';
    renderContractSections();
  }

  function setContractFromRecord(record) {
    if (!global.CasePMAiaTemplates) return;
    const form = record?.aia_form || document.getElementById('modalAiaForm')?.value;
    const type = record?.commitment_type || document.getElementById('modalType')?.value || 'Purchase Order';
    const key = global.CasePMAiaTemplates.resolveFormKey(form, type);
    state.aiaContract = record?.aia_contract
      ? global.CasePMAiaTemplates.mergeContract(record.aia_contract, key)
      : global.CasePMAiaTemplates.cloneTemplate(key);
    const inc = document.getElementById('modalInclusions');
    const exc = document.getElementById('modalExclusions');
    const scope = document.getElementById('modalScopeSupplement');
    if (inc) inc.value = state.aiaContract.inclusions || '';
    if (exc) exc.value = state.aiaContract.exclusions || '';
    if (scope) scope.value = state.aiaContract.scope_supplement || '';
    renderContractSections();
  }

  function onAiaFormChange() {
    if (confirm('Load contract template for the selected AIA form? Unsaved article edits in this session will be replaced.')) {
      loadContractTemplate(true);
    }
  }

  function toggleContractEditor() {
    const panel = document.getElementById('contractEditorPanel');
    const chevron = document.getElementById('contractEditorChevron');
    if (!panel) return;
    panel.classList.toggle('hidden');
    if (chevron) chevron.classList.toggle('fa-chevron-down', panel.classList.contains('hidden'));
    if (chevron) chevron.classList.toggle('fa-chevron-up', !panel.classList.contains('hidden'));
  }

  function addContractSection() {
    if (!state.aiaContract) loadContractTemplate(true);
    const id = `custom-${Date.now()}`;
    state.aiaContract.sections.push({
      id,
      title: 'NEW ARTICLE / SECTION',
      body: 'Enter contract language here.',
      enabled: true,
      builtin: false,
    });
    renderContractSections();
  }

  function removeContractSection(id) {
    if (!state.aiaContract) return;
    state.aiaContract.sections = state.aiaContract.sections.filter(s => s.id !== id);
    renderContractSections();
  }

  function updateAdminDeleteBar(record) {
    const bar = document.getElementById('adminDeleteBar');
    const btn = document.getElementById('modalDeleteBtn');
    if (!bar) return;
    if (isAdmin() && record?.id) {
      bar.classList.remove('hidden');
      if (btn) {
        const deletable = isDirectlyDeletable(record);
        btn.title = deletable ? 'Delete permanently' : `Status: ${record.status} — will void then delete`;
      }
    } else {
      bar.classList.add('hidden');
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
    populateSelect('modalAiaForm', AIA_FORMS, record?.aia_form || defaultAiaForType(record?.commitment_type) || ctx.prime_aia_form || defaultAiaForType('Purchase Order'));
    populateSelect('modalSignatureMethod', SIGNATURE_METHODS.map(s => s.value), record?.signature_method || 'internal');
    populateCompanySelect(record?.company_id);
    setVal('modalTitle', record?.title || '');
    setVal('modalDescription', record?.description || '');
    setVal('modalCompanyName', record?.company_name || '');
    setVal('modalContactName', record?.contact_name || '');
    setVal('modalContactEmail', record?.contact_email || '');
    setVal('modalContactPhone', record?.contact_phone || '');
    setVal('modalRetainage', (record?.retainage_percent != null && record?.retainage_percent !== '')
      ? record.retainage_percent
      : (parseFloat(ctx.default_retainage_percent) || 0));
    setVal('modalPaymentTerms', record?.payment_terms || '');
    setVal('modalFreightTerms', record?.freight_terms || '');
    setVal('modalBillingType', record?.billing_type || 'Lump Sum');
    setVal('modalScope', record?.scope_of_work || record?.notes || '');
    setVal('modalDate', record?.date ? record.date.split('T')[0] : new Date().toISOString().split('T')[0]);
    setVal('modalStartDate', record?.start_date ? record.start_date.split('T')[0] : '');
    setVal('modalEndDate', record?.end_date ? record.end_date.split('T')[0] : '');
    setVal('modalDeliveryDate', record?.delivery_date ? record.delivery_date.split('T')[0] : '');
    setMoneyVal('modalAmount', record?.original_amount || '');
    if (global.CasePMMoney) CasePMMoney.setupMoneyInput(document.getElementById('modalAmount'));
    setVal('modalOwnerName', record?.owner_name || ctx.owner_legal_name || ctx.client || '');
    setVal('modalContractorName', record?.contractor_name || ctx.contractor_legal_name || 'Case Contracting');
    setVal('modalArchitectEngineer', record?.architect_engineer || ctx.architect_of_record || '');
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
    setContractFromRecord(record);
    updateAdminDeleteBar(record);
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
      original_amount: total || readMoney('modalAmount'),
      allocations: allocs,
      aia_contract: readContractFromForm(),
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

  async function deleteCommitment(id, options = {}) {
    const c = state.commitments.find(x => x.id === id) || state.drawerRecord;
    if (!c) return;
    if (!canDeleteRecord(c)) {
      alert(`Only administrators can delete commitments. Your role: ${userRole() || 'unknown'}.`);
      return;
    }
    const needsForce = !isDirectlyDeletable(c);
    const msg = needsForce
      ? `${c.number} is "${c.status}". As Admin, void and permanently delete?`
      : `Permanently delete ${c.number}? This cannot be undone.`;
    if (!options.skipConfirm && !confirm(msg)) return;
    try {
      const url = needsForce ? `/api/commitments/${id}?force=1` : `/api/commitments/${id}`;
      await api(url, { method: 'DELETE', body: needsForce ? JSON.stringify({ force: true }) : undefined });
      logCommitmentAudit('COMMITMENT_DELETED', { number: c.number, type: c.commitment_type, forced: needsForce });
      closeDrawer();
      document.getElementById('comModal')?.close();
      await refreshAll();
      toast(`${c.number} deleted`);
    } catch (err) {
      alert(err.message);
    }
  }

  function deleteFromModal() {
    const id = document.getElementById('modalRecordId')?.value;
    if (id) deleteCommitment(parseInt(id, 10));
  }

  async function applyCommitmentWorkflow(id, action, comments) {
    const c = state.commitments.find(x => x.id === id);
    if (!c) return;
    try {
      const json = await api(`/api/commitments/${id}/workflow`, {
        method: 'POST',
        body: JSON.stringify({ action, comments: comments || '' }),
      });
      logCommitmentAudit(`COMMITMENT_${action.toUpperCase()}`, { number: c.number, new_status: json.new_status });
      if (typeof CasePMAccountingReconcile !== 'undefined') {
        CasePMAccountingReconcile.applyReconcileResult({
          budget_sync_result: json.budget_sync_result,
          sync_result: json.sov_sync_result,
        });
      } else if (json.final_approved && typeof CasePMBudgetSync !== 'undefined') {
        await CasePMBudgetSync.init().catch(() => {});
        await CasePMBudgetSync.loadFromServer().catch(() => {});
      }
      if (typeof CasePMAccountingReconcile === 'undefined' && json.final_approved && typeof CasePMPayAppSync !== 'undefined') {
        await CasePMPayAppSync.init().catch(() => {});
        await CasePMPayAppSync.loadFromServer().catch(() => {});
      }
      await refreshAll();
      if (state.drawerRecord?.id === id) {
        state.drawerRecord = json.commitment;
        renderDrawer(json.commitment);
      }
      toast(json.final_approved ? `${c.number} approved — synced to budget & SOV` : `${c.number} → ${json.new_status}`);
      if (action === 'approve' || action === 'reject') closeDrawer();
    } catch (err) {
      alert(err.message);
      throw err;
    }
  }

  function openReviewModal(id) {
    closeDrawer();
    const c = state.commitments.find(x => x.id === id) || (state.drawerRecord?.id === id ? state.drawerRecord : null);
    if (!c) {
      view(id).then(() => openReviewModal(id));
      return;
    }
    if (typeof global.CasePMApprovalResponder === 'undefined') {
      applyCommitmentWorkflow(id, 'approve');
      return;
    }
    const allocLines = (c.allocations || []).map(a =>
      `<div class="flex justify-between gap-3 text-xs"><span class="font-mono text-emerald-400">${esc(a.cost_code)}</span><span class="truncate text-zinc-400">${esc(a.description || '')}</span><span class="font-mono">${fmt(a.amount)}</span></div>`
    ).join('') || '<div class="text-zinc-500 text-xs">No allocations</div>';
    global.CasePMApprovalResponder.openLocal({
      module: 'Commitments',
      entityId: id,
      title: `${c.number} — ${c.title || c.description || 'Commitment'}`,
      status: c.status,
      ball: c.ball_in_court_role,
      summaryHtml: `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Type</span><span>${esc(c.commitment_type)} · ${esc(c.aia_form || '—')}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Vendor</span><span>${esc(c.company_name || '—')}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Amount</span><span class="font-mono text-emerald-400">${fmt(c.current_amount)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Status</span><span>${statusBadge(c.status)}</span></div>
        <div class="pt-2 border-t border-zinc-800 mt-2"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Schedule of Values</div>${allocLines}</div>
        ${c.scope_of_work || c.description ? `<div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Scope</div><p class="text-sm whitespace-pre-wrap">${esc(c.scope_of_work || c.description)}</p></div>` : ''}`,
      actions: [
        { action: 'approve', label: 'Approve', style: 'primary' },
        { action: 'reject', label: 'Reject', requires_comment: true, style: 'danger' },
      ],
      onSubmit: async (action, comment) => {
        await applyCommitmentWorkflow(id, action, comment);
      },
    });
  }

  async function workflow(id, action) {
    const c = state.commitments.find(x => x.id === id);
    if (!c) return;
    if (action === 'approve' || action === 'reject') {
      openReviewModal(id);
      return;
    }
    const verb = action === 'submit' ? 'Submit' : action;
    if (!confirm(`${verb} ${c.number}?`)) return;
    await applyCommitmentWorkflow(id, action);
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
    if (typeof CasePMEsign === 'undefined') {
      alert('E-sign module not loaded.');
      return;
    }
    let payload;
    try {
      payload = await CasePMEsign.buildAttestationPayload();
    } catch (err) {
      alert(err.message || 'Set up your signature in User Management first.');
      return;
    }
    if (!confirm('Apply your certified electronic signature to this commitment? This will be locked to your profile signature hash.')) return;
    try {
      await api(`/api/commitments/${id}/workflow`, {
        method: 'POST',
        body: JSON.stringify({ action: 'sign_internal', ...payload }),
      });
      logCommitmentAudit('COMMITMENT_SIGNED', { number: state.drawerRecord?.number });
      await refreshAll();
      toast('Electronic signature recorded and document locked');
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
    const showSubmit = c.status === 'Draft';
    const showApprove = ['Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner'].includes(c.status) && canActOnBall(c.ball_in_court_role);
    const reviewBanner = showApprove ? `
      <div class="mb-6 p-4 rounded-lg bg-emerald-950/50 border-2 border-emerald-600 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div class="text-emerald-400 font-semibold">Your review is needed</div>
          <div class="text-xs text-zinc-400 mt-1">Ball in court: ${esc(c.ball_in_court_role || '—')} · ${esc(c.status)}</div>
        </div>
        ${reviewButtonHtml(c.id)}
      </div>` : '';
    const allocs = (c.allocations || []).map(a =>
      `<tr class="border-b border-zinc-800"><td class="py-2 font-mono text-xs">${esc(a.cost_code)}</td><td class="py-2">${esc(a.description || '')}</td><td class="py-2 text-right font-mono">${fmt(a.amount)}</td></tr>`
    ).join('');
    const sigs = (c.certified_signatures || []).map(s =>
      `<div class="text-xs text-zinc-400">${esc(s.signed_by_name)} · ${fmtDate(s.signed_at)} · ${esc(s.method)}</div>`
    ).join('') || '<span class="text-zinc-500">No signatures yet</span>';
    const bodyHtml = `
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
        ${c.external_document_url ? `<p><span class="text-zinc-500">Official AIA</span><br><a href="${esc(c.external_document_url)}" target="_blank" rel="noopener" class="text-violet-400 underline">${esc(c.external_document_provider || 'catina')} — ${esc(c.external_document_id || 'linked')}</a></p>` : ''}
      </div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Schedule of Values / Allocations</div>
      <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left py-1">Code</th><th class="text-left py-1">Description</th><th class="text-right py-1">Amount</th></tr></thead>
      <tbody>${allocs || '<tr><td colspan="3" class="py-3 text-zinc-500">No allocations</td></tr>'}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Signatures</div>${sigs}</div>`;
    document.getElementById('drawerBody').innerHTML = reviewBanner + bodyHtml;
    const showAdminDelete = canDeleteRecord(c);
    document.getElementById('drawerActions').innerHTML = `
      <button type="button" onclick="CasePMCommitments.printCommitment(${c.id})" class="px-4 py-2 bg-sky-700 hover:bg-sky-600 rounded-md text-sm"><i class="fa-solid fa-print mr-1"></i>Print</button>
      <button type="button" onclick="CasePMCommitments.editContractLanguage(${c.id})" class="px-4 py-2 bg-indigo-800 hover:bg-indigo-700 rounded-md text-sm"><i class="fa-solid fa-file-contract mr-1"></i>Contract Language</button>
      <button type="button" onclick="CasePMCommitments.openCatina(${c.id})" class="px-4 py-2 bg-violet-800 hover:bg-violet-700 rounded-md text-sm" title="AIA Contract Documents (Catina)"><i class="fa-solid fa-building-columns mr-1"></i>Open in Catina</button>
      <button type="button" onclick="CasePMCommitments.registerAiaDocument(${c.id})" class="px-4 py-2 bg-violet-900/60 hover:bg-violet-800 rounded-md text-sm">Link AIA Document</button>
      <button type="button" onclick="CasePMCommitments.syncSageForCommitment(${c.id})" class="px-4 py-2 bg-amber-800 hover:bg-amber-700 rounded-md text-sm" title="Sync to Sage 300"><i class="fa-solid fa-rotate mr-1"></i>Sage Sync</button>
      ${showSubmit ? `<button type="button" onclick="CasePMCommitments.workflow(${c.id},'submit')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-md text-sm">Submit</button>` : ''}
      ${c.status === 'Approved' && c.signature_status !== 'fully_executed' ? `
        <button type="button" onclick="CasePMCommitments.signInternal(${c.id})" class="px-4 py-2 bg-sky-700 hover:bg-sky-600 rounded-md text-sm" title="Sign with your User Management e-signature">E-Sign (My Signature)</button>
        <button type="button" onclick="CasePMCommitments.sendDocuSign(${c.id})" class="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 rounded-md text-sm" title="Send via DocuSign for third-party certified signing"><i class="fa-solid fa-file-signature mr-1"></i>DocuSign</button>` : ''}
      <button type="button" onclick="CasePMCommitments.edit(${c.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>
      ${showAdminDelete ? `<button type="button" onclick="CasePMCommitments.deleteCommitment(${c.id})" class="px-4 py-2 bg-red-900/70 hover:bg-red-800 text-red-200 rounded-md text-sm" title="${isDirectlyDeletable(c) ? 'Delete' : 'Void & delete'}"><i class="fa-solid fa-trash mr-1"></i>Delete</button>` : ''}`;
    if (showApprove) {
      openReviewModal(c.id);
      return;
    }
    openDrawer();
  }

  async function view(id) {
    const c = await api(`/api/commitments/${id}`);
    state.drawerRecord = c;
    if (commitmentNeedsReview(c)) {
      openReviewModal(id);
      return;
    }
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
    const contract = c.aia_contract || (global.CasePMAiaTemplates
      ? global.CasePMAiaTemplates.cloneTemplate(global.CasePMAiaTemplates.resolveFormKey(form, c.commitment_type))
      : null);
    const isPO = c.commitment_type === 'Purchase Order' || form === 'N/A';
    const isSub = c.commitment_type === 'Subcontract' || form === 'A401';
    const docTitle = contract?.title || (isPO ? 'PURCHASE ORDER' : isSub ? 'AGREEMENT BETWEEN CONTRACTOR AND SUBCONTRACTOR' : 'AGREEMENT');
    const docSubtitle = isPO ? 'PURCHASE ORDER' : `AIA DOCUMENT ${form}`;
    const owner = c.owner_name || ctx.name || '___________________________';
    const contractor = c.contractor_name || 'Case Contracting';
    const project = ctx.name || '—';
    const projectNo = ctx.number || '—';
    const address = ctx.address || '—';
    const total = c.current_amount || c.original_amount || 0;
    const retainPct = c.retainage_percent || 0;

    const inclusions = contract?.inclusions || '';
    const exclusions = contract?.exclusions || '';
    const scopeSupp = contract?.scope_supplement || c.scope_of_work || c.description || '';
    const enabledSections = (contract?.sections || []).filter(s => s.enabled !== false);

    const scopeBlock = (inclusions || exclusions || scopeSupp) ? `
      <div class="section-title">SUPPLEMENTARY SCOPE SCHEDULE</div>
      ${scopeSupp ? `<div class="box" style="margin-bottom:6px;"><div class="box-title">SCOPE OF WORK</div><div class="cert-text" style="white-space:pre-wrap;">${esc(scopeSupp)}</div></div>` : ''}
      ${inclusions ? `<div class="box" style="margin-bottom:6px;"><div class="box-title">INCLUSIONS</div><div class="cert-text" style="white-space:pre-wrap;">${esc(inclusions)}</div></div>` : ''}
      ${exclusions ? `<div class="box" style="margin-bottom:6px;"><div class="box-title">EXCLUSIONS</div><div class="cert-text" style="white-space:pre-wrap;">${esc(exclusions)}</div></div>` : ''}
    ` : '';

    const articlesHtml = enabledSections.length
      ? enabledSections.map(s => `
        <div class="section-title">${esc(s.title)}</div>
        <div class="cert-text" style="white-space:pre-wrap;">${esc(s.body || '')}</div>`).join('')
      : `<div class="cert-text">${esc(c.scope_of_work || c.description || '')}</div>`;

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
      ${scopeBlock}
      <div class="section-title">CONTRACT SUMMARY</div>
      <div class="cert-text">Contract Amount: <strong>${fmt(total)}</strong> · Billing: ${esc(c.billing_type || 'Lump Sum')} · Retainage: ${retainPct}% · Payment: ${esc(c.payment_terms || '—')}${c.bond_required ? ' · Bonds Required' : ''}</div>
      ${c.insurance_requirements ? `<div class="cert-text">Insurance: ${esc(c.insurance_requirements)}</div>` : ''}
      <div class="section-title">CONTRACT ARTICLES</div>
      ${articlesHtml}
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

  async function editContractLanguage(id) {
    closeDrawer();
    const record = await api(`/api/commitments/${id}`);
    await openModal(record);
    const panel = document.getElementById('contractEditorPanel');
    const chevron = document.getElementById('contractEditorChevron');
    if (panel) panel.classList.remove('hidden');
    if (chevron) { chevron.classList.remove('fa-chevron-down'); chevron.classList.add('fa-chevron-up'); }
    panel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function printCommitment(id) {
    let c = state.commitments.find(x => x.id === id);
    if (!c || !c.allocations) {
      try { c = await api(`/api/commitments/${id}`); } catch (err) { alert(err.message); return; }
    }
    const form = c.aia_form || 'N/A';
    const printHTML = `<!DOCTYPE html><html><head><title>${esc(c.number)} — ${esc(form)}</title><style>${buildPrintStyles()}</style></head><body>${buildAiaPrintHtml(c)}</body></html>`;
    if (global.CasePMOutput) {
      await global.CasePMOutput.deliverHtml({
        title: `${c.number} — ${form}`,
        html: printHTML,
        filenameBase: `${c.number || 'Commitment'}_${form}`.replace(/[<>:"/\\|?*]+/g, '_'),
        sourceModule: 'commitments',
        systemFolderKey: 'contracts',
        subfolder: 'Exports',
        printOptions: { landscape: true },
      });
      logCommitmentAudit('COMMITMENT_PRINTED', { number: c.number, form: c.aia_form });
      return;
    }
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

  async function exportExcel() {
    if (typeof XLSX === 'undefined') { alert('Excel library not loaded'); return; }
    const data = state.commitments.map(c => ({
      Number: c.number, Type: c.commitment_type, Title: c.title, Vendor: c.company_name,
      AIA: c.aia_form, Original: c.original_amount, Changes: c.approved_changes, Current: c.current_amount,
      Status: c.status, Signature: c.signature_status, Sage: c.sage_sync_status,
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Commitments');
    const filename = `Commitments_${projectId() || 'project'}.xlsx`;
    if (global.CasePMOutput) {
      const buf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
      await global.CasePMOutput.deliverBlob({
        title: 'Export Commitments',
        blob: new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
        mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename,
        filenameBase: `Commitments_${projectId() || 'project'}`,
        sourceModule: 'commitments',
        systemFolderKey: 'contracts',
        subfolder: 'Exports',
        fileLabel: 'Excel (.xlsx)',
      });
      return;
    }
    XLSX.writeFile(wb, filename);
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
    await Promise.all([loadDashboard(), loadCommitments(), loadSageLog(), loadIntegrations()]);
  }

  async function init() {
    if (!projectId()) {
      alert('Select a project to manage commitments.');
      return;
    }
    loadAuditLog();
    if (typeof CasePMWorkflow !== 'undefined') await CasePMWorkflow.loadPortal().catch(() => {});
    if (typeof CasePMAccountingReconcile !== 'undefined') {
      await CasePMAccountingReconcile.initAndReconcile().catch(() => {});
    } else {
      if (typeof CasePMBudgetSync !== 'undefined') await CasePMBudgetSync.init().catch(() => {});
      if (typeof CasePMPayAppSync !== 'undefined') await CasePMPayAppSync.init().catch(() => {});
    }
    loadCompanies();
    await loadCostCodes();
    bindFilters();
    await refreshAll();
    renderTable();
    global.addEventListener('casepm:accounting-reconciled', () => {
      refreshAll().then(() => renderTable());
    });
  }

  global.CasePMCommitments = {
    init,
    openModal,
    saveModal,
    newCommitment: () => openModal(null),
    edit: id => api(`/api/commitments/${id}`).then(openModal).catch(e => alert(e.message)),
    view,
    openCommitmentItem,
    closeDrawer,
    workflow,
    openReviewModal,
    sendDocuSign,
    signInternal,
    deleteCommitment,
    deleteFromModal,
    printCommitment,
    editContractLanguage,
    onTypeChange,
    onAiaFormChange,
    openSageSyncLogModal,
    showCommitmentAuditLog,
    showIntegrationsModal,
    syncSageForCommitment,
    retrySageEvent,
    openCatina,
    registerAiaDocument,
    toggleContractEditor,
    loadContractTemplate,
    addContractSection,
    removeContractSection,
    isAdmin,
    addAllocRow: () => { state.allocationRows.push({ cost_code: '', amount: 0, description: '' }); renderAllocationRows(); },
    removeAllocRow: idx => { state.allocationRows.splice(idx, 1); renderAllocationRows(); },
    onCompanyChange,
    exportExcel,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
