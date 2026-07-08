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
    filter: { search: '', status: '', type: '' },
    allocationRows: [],
    drawerRecord: null,
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
    state.stats = await api(`/api/commitments/dashboard?project_id=${pid}`);
    renderSummary();
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
    const latest = state.sageLog[0];
    el.textContent = latest
      ? `Sage 300 AP · ${latest.event_type} · ${latest.status} · ${new Date(latest.created_at).toLocaleString()}`
      : 'Sage 300 Commitments · No sync events yet';
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

  function openModal(record) {
    document.getElementById('modalRecordId').value = record?.id || '';
    document.getElementById('comModalHeading').textContent = record ? `Edit ${record.number}` : 'New Commitment';
    populateSelect('modalType', TYPES, record?.commitment_type || 'Purchase Order');
    populateSelect('modalStatus', STATUSES, record?.status || 'Draft');
    populateSelect('modalAiaForm', AIA_FORMS, record?.aia_form || defaultAiaForType(record?.commitment_type));
    populateSelect('modalSignatureMethod', SIGNATURE_METHODS.map(s => s.value), record?.signature_method || 'internal');
    populateCompanySelect(record?.company_id);
    document.getElementById('modalTitle').value = record?.title || '';
    document.getElementById('modalDescription').value = record?.description || '';
    document.getElementById('modalCompanyName').value = record?.company_name || '';
    document.getElementById('modalRetainage').value = record?.retainage_percent || 0;
    document.getElementById('modalPaymentTerms').value = record?.payment_terms || '';
    document.getElementById('modalScope').value = record?.scope_of_work || record?.notes || '';
    document.getElementById('modalDate').value = record?.date ? record.date.split('T')[0] : new Date().toISOString().split('T')[0];
    document.getElementById('modalAmount').value = record?.original_amount || '';
    state.allocationRows = (record?.allocations?.length)
      ? record.allocations.map(a => ({ ...a }))
      : [{ cost_code: '', amount: record?.original_amount || 0, description: '' }];
    onCompanyChange();
    renderAllocationRows();
    document.getElementById('comModal').showModal();
  }

  function defaultAiaForType(type) {
    if (type === 'Subcontract') return 'A401';
    if (type === 'Purchase Order') return 'N/A';
    return 'N/A';
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
      retainage_percent: parseFloat(document.getElementById('modalRetainage').value) || 0,
      payment_terms: document.getElementById('modalPaymentTerms').value.trim(),
      scope_of_work: document.getElementById('modalScope').value.trim(),
      date: document.getElementById('modalDate').value,
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
      document.getElementById('comModal').close();
      await refreshAll();
      toast('Commitment saved');
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
        <p><span class="text-zinc-500">AIA Form</span><br>${esc(c.aia_form)} · Retainage ${c.retainage_percent || 0}%</p>
        <p><span class="text-zinc-500">Amount</span><br><span class="font-mono text-lg">${fmt(c.current_amount)}</span></p>
        <p><span class="text-zinc-500">Ball in court</span><br>${esc(c.ball_in_court_role || '—')}</p>
        <p><span class="text-zinc-500">Signature</span><br>${sigBadge(c)} · ${esc(c.signature_method)}</p>
        ${c.docusign_envelope_id ? `<p><span class="text-zinc-500">DocuSign</span><br>${esc(c.docusign_envelope_id)} (${esc(c.docusign_status || '—')})</p>` : ''}
        <p><span class="text-zinc-500">Payment terms</span><br>${esc(c.payment_terms || '—')}</p>
        <p><span class="text-zinc-500">Scope</span><br>${esc(c.scope_of_work || c.description || '—')}</p>
        <p><span class="text-zinc-500">Sage</span><br>${esc(c.sage_sync_status || '—')}</p>
      </div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Schedule of Values / Allocations</div>
      <table class="w-full text-xs"><thead><tr class="text-zinc-500"><th class="text-left py-1">Code</th><th class="text-left py-1">Description</th><th class="text-right py-1">Amount</th></tr></thead>
      <tbody>${allocs || '<tr><td colspan="3" class="py-3 text-zinc-500">No allocations</td></tr>'}</tbody></table></div>
      <div class="mt-4"><div class="text-xs text-zinc-500 uppercase mb-2">Signatures</div>${sigs}</div>`;
    const showSubmit = c.status === 'Draft';
    const showApprove = ['Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner'].includes(c.status) && canActOnBall(c.ball_in_court_role);
    document.getElementById('drawerActions').innerHTML = `
      ${showSubmit ? `<button type="button" onclick="CasePMCommitments.workflow(${c.id},'submit')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-md text-sm">Submit</button>` : ''}
      ${showApprove ? `<button type="button" onclick="CasePMCommitments.workflow(${c.id},'approve')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm">Approve</button>
      <button type="button" onclick="CasePMCommitments.workflow(${c.id},'reject')" class="px-4 py-2 bg-zinc-800 text-red-400 rounded-md text-sm">Reject</button>` : ''}
      ${c.status === 'Approved' && c.signature_status !== 'fully_executed' ? `
        <button type="button" onclick="CasePMCommitments.signInternal(${c.id})" class="px-4 py-2 bg-sky-700 hover:bg-sky-600 rounded-md text-sm">Certified Sign</button>
        <button type="button" onclick="CasePMCommitments.sendDocuSign(${c.id})" class="px-4 py-2 bg-indigo-700 hover:bg-indigo-600 rounded-md text-sm"><i class="fa-solid fa-file-signature mr-1"></i>DocuSign</button>` : ''}
      <button type="button" onclick="CasePMCommitments.edit(${c.id})" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Edit</button>`;
    openDrawer();
  }

  async function view(id) {
    const c = await api(`/api/commitments/${id}`);
    state.drawerRecord = c;
    renderDrawer(c);
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-16 right-6 z-[70] px-4 py-2 rounded-md bg-emerald-900 text-emerald-100 text-sm shadow-lg';
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
    addAllocRow: () => { state.allocationRows.push({ cost_code: '', amount: 0, description: '' }); renderAllocationRows(); },
    removeAllocRow: idx => { state.allocationRows.splice(idx, 1); renderAllocationRows(); },
    onCompanyChange,
    exportExcel,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
