/**
 * Case PM — RFI module (Procore / RedTeam / ACC feature parity)
 */
(function (global) {
  'use strict';

  const STATUSES = ['Draft', 'Open', 'Under Review', 'Awaiting Response', 'Answered', 'Closed', 'Void'];
  const PRIORITIES = ['Low', 'Medium', 'High', 'Critical'];
  const DISCIPLINES = ['Architectural', 'Structural', 'Civil', 'MEP', 'Electrical', 'Plumbing', 'Fire Protection', 'General'];

  let state = {
    rfis: [],
    stats: {},
    companies: [],
    users: [],
    linkOptions: { change_orders: [], pcos: [] },
    selected: null,
    filter: { search: '', status: '', priority: '', ball: '' },
    drawerRecord: null,
    modalMode: 'create',
    allocationRows: [],
  };

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function userName() {
    if (global.CASEPM_PORTAL && global.CASEPM_PORTAL.userName) return global.CASEPM_PORTAL.userName;
    return 'User';
  }

  function userRole() {
    return (global.CASEPM_PORTAL && global.CASEPM_PORTAL.role) || 'Admin';
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
    try { state.companies = JSON.parse(localStorage.getItem('casepm_companies') || '[]'); } catch { state.companies = []; }
    try { state.users = JSON.parse(localStorage.getItem('casepm_users') || localStorage.getItem('users') || '[]'); } catch { state.users = []; }
  }

  async function loadDashboard() {
    const pid = projectId();
    if (!pid) return;
    state.stats = await api(`/api/rfis/dashboard?project_id=${pid}`);
    renderSummary();
  }

  async function loadRfis() {
    const pid = projectId();
    if (!pid) return;
    const json = await api(`/api/rfis?project_id=${pid}`);
    state.rfis = json.rfis || [];
    renderTable();
  }

  async function loadLinkOptions() {
    const pid = projectId();
    if (!pid) return;
    try {
      state.linkOptions = await api(`/api/rfis/link-options?project_id=${pid}`);
    } catch { state.linkOptions = { change_orders: [], pcos: [] }; }
  }

  function renderSummary() {
    const s = state.stats;
    const map = {
      statRfiTotal: s.total || 0,
      statRfiOpen: s.open || 0,
      statRfiAwaiting: s.awaiting_response || 0,
      statRfiAnswered: s.answered || 0,
      statRfiOverdue: s.overdue || 0,
      statRfiClosed: s.closed || 0,
      statRfiCostImpact: s.with_cost_impact || 0,
      statRfiSchedImpact: s.with_schedule_impact || 0,
    };
    Object.keys(map).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = map[id];
    });
  }

  function filteredRfis() {
    const { search, status, priority } = state.filter;
    return state.rfis.filter(r => {
      const text = `${r.number} ${r.subject} ${r.question || ''} ${r.received_from_company || ''} ${r.drawing_reference || ''}`.toLowerCase();
      if (search && !text.includes(search.toLowerCase())) return false;
      if (status && r.status !== status) return false;
      if (priority && r.priority !== priority) return false;
      return true;
    });
  }

  function statusBadge(status) {
    const colors = {
      Draft: 'bg-zinc-700 text-zinc-300',
      Open: 'bg-sky-900/60 text-sky-300',
      'Under Review': 'bg-amber-900/60 text-amber-300',
      'Awaiting Response': 'bg-orange-900/60 text-orange-300',
      Answered: 'bg-emerald-900/60 text-emerald-300',
      Closed: 'bg-zinc-800 text-zinc-400',
      Void: 'bg-red-950/60 text-red-400',
    };
    return `<span class="px-2 py-0.5 rounded-full text-[10px] font-medium ${colors[status] || 'bg-zinc-700 text-zinc-300'}">${esc(status)}</span>`;
  }

  function priorityBadge(p) {
    const colors = { Critical: 'text-red-400', High: 'text-orange-400', Medium: 'text-amber-300', Low: 'text-zinc-400' };
    return `<span class="text-xs font-medium ${colors[p] || 'text-zinc-400'}">${esc(p || '—')}</span>`;
  }

  function ballBadge(role) {
    if (!role) return '<span class="text-zinc-500">—</span>';
    return `<span class="px-2 py-0.5 rounded text-[10px] bg-violet-900/50 text-violet-300">${esc(role)}</span>`;
  }

  function renderTable() {
    const tbody = document.getElementById('rfiTableBody');
    if (!tbody) return;
    const rows = filteredRfis();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="11" class="px-6 py-12 text-center text-zinc-500">No RFIs found. Create your first RFI.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr class="border-b border-zinc-800 hover:bg-zinc-800/50 cursor-pointer ${r.is_overdue ? 'bg-red-950/10' : ''}" onclick="CasePMRfis.view(${r.id})">
        <td class="px-4 py-3 font-mono text-sky-400 whitespace-nowrap">${esc(r.number)}</td>
        <td class="px-4 py-3 max-w-[280px]">
          <div class="font-medium truncate">${esc(r.subject)}</div>
          <div class="text-[10px] text-zinc-500 truncate">${esc(r.question || '')}</div>
        </td>
        <td class="px-4 py-3 text-xs text-zinc-400">${esc(r.received_from_company || r.from_party || '—')}</td>
        <td class="px-4 py-3 text-xs text-zinc-400">${esc(r.to_party || r.assignees?.[0] || '—')}</td>
        <td class="px-4 py-3 text-xs font-mono">${esc(r.drawing_reference || '—')}</td>
        <td class="px-4 py-3 text-xs font-mono">${esc(r.spec_reference || '—')}</td>
        <td class="px-4 py-3 text-center">${priorityBadge(r.priority)}</td>
        <td class="px-4 py-3 text-center">${statusBadge(r.status)}</td>
        <td class="px-4 py-3 text-center">${ballBadge(r.ball_in_court_role)}</td>
        <td class="px-4 py-3 text-center text-xs whitespace-nowrap ${r.is_overdue ? 'text-red-400 font-semibold' : 'text-zinc-400'}">${fmtDate(r.due_date)}</td>
        <td class="px-4 py-3 text-center" onclick="event.stopPropagation()">
          <div class="flex items-center justify-center gap-1">
            <button onclick="CasePMRfis.respond(${r.id})" class="p-1.5 text-emerald-400 hover:bg-zinc-800 rounded" title="Respond"><i class="fa-solid fa-reply"></i></button>
            <button onclick="CasePMRfis.edit(${r.id})" class="p-1.5 text-zinc-400 hover:bg-zinc-800 rounded" title="Edit"><i class="fa-solid fa-edit"></i></button>
          </div>
        </td>
      </tr>`).join('');
  }

  function bindFilters() {
    ['rfiSearch', 'rfiStatusFilter', 'rfiPriorityFilter'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      const evt = el.tagName === 'INPUT' ? 'input' : 'change';
      el.addEventListener(evt, () => {
        state.filter.search = document.getElementById('rfiSearch')?.value || '';
        state.filter.status = document.getElementById('rfiStatusFilter')?.value || '';
        state.filter.priority = document.getElementById('rfiPriorityFilter')?.value || '';
        renderTable();
      });
    });
  }

  function populateCompanySelects() {
    const sel = document.getElementById('modalRfiCompany');
    if (!sel) return;
    sel.innerHTML = '<option value="">— Select Company —</option>' +
      state.companies.map(c => {
        const name = c.company_name || c.name || '';
        return `<option value="${esc(name)}">${esc(name)}</option>`;
      }).join('');
  }

  function openModal(mode, record) {
    state.modalMode = mode;
    state.drawerRecord = record || null;
    const dlg = document.getElementById('rfiModal');
    if (!dlg) return;
    document.getElementById('rfiModalTitle').textContent = mode === 'create' ? 'New RFI' : `Edit ${record?.number || 'RFI'}`;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
    const setCheck = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    if (mode === 'create') {
      set('modalRfiSubject', '');
      set('modalRfiQuestion', '');
      set('modalRfiPriority', 'Medium');
      set('modalRfiStatus', 'Draft');
      set('modalRfiDueDate', '');
      set('modalRfiDrawing', '');
      set('modalRfiSpec', '');
      set('modalRfiFrom', userName());
      set('modalRfiTo', 'Architect');
      set('modalRfiManager', userName());
      set('modalRfiAssignees', '');
      set('modalRfiDistribution', '');
      set('modalRfiNotes', '');
      set('modalRfiLocation', '');
      set('modalRfiDiscipline', '');
      set('modalRfiCostImpact', '');
      set('modalRfiSchedDays', '0');
      setCheck('modalRfiPrivate', false);
      document.getElementById('modalRfiNumber').textContent = 'Auto';
    } else if (record) {
      set('modalRfiSubject', record.subject);
      set('modalRfiQuestion', record.question);
      set('modalRfiPriority', record.priority);
      set('modalRfiStatus', record.status);
      set('modalRfiDueDate', record.due_date ? record.due_date.slice(0, 10) : '');
      set('modalRfiDrawing', record.drawing_reference);
      set('modalRfiSpec', record.spec_reference);
      set('modalRfiFrom', record.from_party);
      set('modalRfiTo', record.to_party);
      set('modalRfiCompany', record.received_from_company);
      set('modalRfiContact', record.received_from_contact);
      set('modalRfiContractor', record.responsible_contractor);
      set('modalRfiManager', record.rfi_manager_name);
      set('modalRfiAssignees', (record.assignees || []).join(', '));
      set('modalRfiDistribution', (record.distribution || []).join(', '));
      set('modalRfiNotes', record.notes);
      set('modalRfiLocation', record.location_description);
      set('modalRfiDiscipline', record.discipline);
      set('modalRfiCostImpact', record.cost_impact_amount || '');
      set('modalRfiSchedDays', record.schedule_impact_days || 0);
      setCheck('modalRfiPrivate', record.is_private);
      document.getElementById('modalRfiNumber').textContent = record.number;
    }
    populateCompanySelects();
    dlg.showModal();
  }

  function modalPayload() {
    const assignees = (document.getElementById('modalRfiAssignees')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
    const distribution = (document.getElementById('modalRfiDistribution')?.value || '').split(',').map(s => s.trim()).filter(Boolean);
    return {
      subject: document.getElementById('modalRfiSubject')?.value?.trim(),
      question: document.getElementById('modalRfiQuestion')?.value?.trim(),
      priority: document.getElementById('modalRfiPriority')?.value,
      status: document.getElementById('modalRfiStatus')?.value,
      due_date: document.getElementById('modalRfiDueDate')?.value || null,
      drawing_reference: document.getElementById('modalRfiDrawing')?.value?.trim(),
      spec_reference: document.getElementById('modalRfiSpec')?.value?.trim(),
      from_party: document.getElementById('modalRfiFrom')?.value?.trim(),
      to_party: document.getElementById('modalRfiTo')?.value,
      received_from_company: document.getElementById('modalRfiCompany')?.value,
      received_from_contact: document.getElementById('modalRfiContact')?.value?.trim(),
      responsible_contractor: document.getElementById('modalRfiContractor')?.value?.trim(),
      rfi_manager_name: document.getElementById('modalRfiManager')?.value?.trim(),
      assignees,
      distribution,
      notes: document.getElementById('modalRfiNotes')?.value?.trim(),
      location_description: document.getElementById('modalRfiLocation')?.value?.trim(),
      discipline: document.getElementById('modalRfiDiscipline')?.value,
      cost_impact_amount: parseFloat(document.getElementById('modalRfiCostImpact')?.value) || 0,
      schedule_impact_days: parseInt(document.getElementById('modalRfiSchedDays')?.value, 10) || 0,
      is_private: document.getElementById('modalRfiPrivate')?.checked,
    };
  }

  async function saveModal(createAsOpen) {
    const payload = modalPayload();
    if (!payload.subject) { alert('Subject is required.'); return; }
    try {
      if (state.modalMode === 'create') {
        payload.project_id = projectId();
        if (createAsOpen) payload.create_as_open = true;
        await api('/api/rfis', { method: 'POST', body: JSON.stringify(payload) });
        toast('RFI created');
      } else if (state.drawerRecord) {
        await api(`/api/rfis/${state.drawerRecord.id}`, { method: 'PUT', body: JSON.stringify(payload) });
        toast('RFI updated');
      }
      document.getElementById('rfiModal')?.close();
      await Promise.all([loadRfis(), loadDashboard()]);
    } catch (e) { alert(e.message); }
  }

  async function view(id) {
    try {
      const r = await api(`/api/rfis/${id}`);
      state.drawerRecord = r;
      renderDrawer(r);
      document.getElementById('rfiDetailDrawer')?.classList.add('open');
      document.getElementById('rfiDrawerBackdrop')?.classList.remove('hidden');
    } catch (e) { alert(e.message); }
  }

  function closeDrawer() {
    document.getElementById('rfiDetailDrawer')?.classList.remove('open');
    document.getElementById('rfiDrawerBackdrop')?.classList.add('hidden');
    state.drawerRecord = null;
  }

  function drawingPinHref(pin, rfiId) {
    const pid = projectId();
    const q = new URLSearchParams();
    if (pid) q.set('project_id', pid);
    if (pin.drawing_id) q.set('drawing_id', pin.drawing_id);
    else if (pin.drawing_sheet) q.set('sheet', pin.drawing_sheet);
    const nx = pin.nx != null ? pin.nx : (pin.x <= 1 && pin.x >= 0 ? pin.x : null);
    const ny = pin.ny != null ? pin.ny : (pin.y <= 1 && pin.y >= 0 ? pin.y : null);
    if (nx != null) q.set('x', nx);
    if (ny != null) q.set('y', ny);
    if (rfiId) q.set('rfi_id', rfiId);
    return `/drawings?${q.toString()}`;
  }

  function renderDrawer(r) {
    const el = document.getElementById('rfiDrawerContent');
    if (!el) return;
    const responses = (r.responses || []).map(resp => `
      <div class="border border-zinc-700 rounded-md p-3 ${resp.is_official ? 'border-emerald-700 bg-emerald-950/20' : ''}">
        <div class="flex justify-between text-xs text-zinc-500 mb-1">
          <span>${esc(resp.user_name)} ${resp.is_official ? '<span class="text-emerald-400 ml-1">Official Answer</span>' : ''}</span>
          <span>${fmtDate(resp.created_at)}</span>
        </div>
        <div class="text-sm whitespace-pre-wrap">${esc(resp.body)}</div>
      </div>`).join('') || '<p class="text-zinc-500 text-sm">No responses yet.</p>';

    const pins = (r.plan_pins || []).map((p, i) => `
      <div class="text-xs bg-zinc-800 rounded px-2 py-1 flex justify-between">
        <a href="${drawingPinHref(p, r.id)}" class="hover:text-sky-300"><i class="fa-solid fa-map-pin text-sky-400 mr-1"></i>${esc(p.drawing_sheet || r.drawing_reference || 'Sheet')}${p.nx != null ? '' : ` @ (${p.x || 0}, ${p.y || 0})`}</a>
        <button onclick="CasePMRfis.removePin(${r.id}, ${i})" class="text-red-400"><i class="fa-solid fa-times"></i></button>
      </div>`).join('') || '<p class="text-zinc-500 text-xs">No plan pins yet. Open <a href="/drawings" class="text-sky-400 underline">Drawings</a> to place RFI pins on sheets.</p>';

    const linked = [
      ...(r.linked_change_orders || []).map(c => `<a href="/change-orders" class="text-emerald-400 text-xs">${esc(c.number)} — ${esc(c.title)}</a>`),
      ...(r.linked_pcos || []).map(p => `<a href="/change-orders" class="text-sky-400 text-xs">${esc(p.number)} — ${esc(p.title)}</a>`),
    ].join('<br>') || '<span class="text-zinc-500 text-xs">No linked COs/PCOs</span>';

    el.innerHTML = `
      <div class="flex items-start justify-between mb-4">
        <div>
          <div class="font-mono text-sky-400 text-lg">${esc(r.number)}</div>
          <h2 class="text-xl font-semibold mt-1">${esc(r.subject)}</h2>
          <div class="flex flex-wrap gap-2 mt-2">${statusBadge(r.status)} ${priorityBadge(r.priority)} ${ballBadge(r.ball_in_court_role)}</div>
        </div>
        <button onclick="CasePMRfis.closeDrawer()" class="text-zinc-400 hover:text-white text-xl">&times;</button>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-4">
        <div><span class="text-zinc-500">Due</span><div class="${r.is_overdue ? 'text-red-400' : ''}">${fmtDate(r.due_date)}</div></div>
        <div><span class="text-zinc-500">Drawing</span><div class="font-mono">${esc(r.drawing_reference || '—')}</div></div>
        <div><span class="text-zinc-500">Spec</span><div class="font-mono">${esc(r.spec_reference || '—')}</div></div>
        <div><span class="text-zinc-500">Discipline</span><div>${esc(r.discipline || '—')}</div></div>
        <div><span class="text-zinc-500">From</span><div>${esc(r.received_from_company || r.from_party || '—')}</div></div>
        <div><span class="text-zinc-500">To / Assignee</span><div>${esc((r.assignees || []).join(', ') || r.to_party || '—')}</div></div>
        <div><span class="text-zinc-500">RFI Manager</span><div>${esc(r.rfi_manager_name || '—')}</div></div>
        <div><span class="text-zinc-500">Cost Impact</span><div>${r.cost_impact_amount ? '$' + Number(r.cost_impact_amount).toLocaleString() : '—'}</div></div>
      </div>
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-1">Question</h3>
        <p class="text-sm whitespace-pre-wrap bg-zinc-800/50 rounded-md p-3 border border-zinc-700">${esc(r.question || '—')}</p>
      </div>
      ${r.official_answer ? `<div class="mb-4"><h3 class="text-xs uppercase text-emerald-500 mb-1">Official Answer</h3><p class="text-sm whitespace-pre-wrap bg-emerald-950/20 rounded-md p-3 border border-emerald-800">${esc(r.official_answer)}</p></div>` : ''}
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-2">Responses</h3>
        <div class="space-y-2 max-h-48 overflow-auto">${responses}</div>
      </div>
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-2">Plan Pins</h3>
        <div class="space-y-1 mb-2">${pins}</div>
        <button type="button" onclick="CasePMRfis.addPlanPin(${r.id})" class="text-xs px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700"><i class="fa-solid fa-map-pin mr-1"></i>Add Plan Pin</button>
      </div>
      <div class="mb-4">
        <h3 class="text-xs uppercase text-zinc-500 mb-1">Linked Change Orders / PCOs</h3>
        <div class="space-y-1">${linked}</div>
      </div>
      <div class="flex flex-wrap gap-2 pt-3 border-t border-zinc-700">
        <button onclick="CasePMRfis.respond(${r.id})" class="px-3 py-1.5 text-xs bg-emerald-700 hover:bg-emerald-600 rounded-md"><i class="fa-solid fa-reply mr-1"></i>Respond</button>
        <button onclick="CasePMRfis.workflow(${r.id}, 'submit')" class="px-3 py-1.5 text-xs bg-sky-800 hover:bg-sky-700 rounded-md">Submit / Open</button>
        <button onclick="CasePMRfis.workflow(${r.id}, 'return_to_assignee')" class="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md">Ball → Assignee</button>
        <button onclick="CasePMRfis.workflow(${r.id}, 'return_to_manager')" class="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md">Ball → Manager</button>
        <button onclick="CasePMRfis.workflow(${r.id}, 'close')" class="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md">Close</button>
        <button onclick="CasePMRfis.promotePco(${r.id})" class="px-3 py-1.5 text-xs bg-violet-800 hover:bg-violet-700 rounded-md"><i class="fa-solid fa-lightbulb mr-1"></i>Create PCO</button>
        <button onclick="CasePMRfis.edit(${r.id})" class="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 rounded-md"><i class="fa-solid fa-edit mr-1"></i>Edit</button>
      </div>`;
  }

  async function respond(id) {
    const body = prompt('Enter your RFI response:');
    if (!body) return;
    const official = confirm('Mark this as the official answer?');
    try {
      await api(`/api/rfis/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action: 'respond', body, is_official: official }) });
      toast('Response posted');
      await Promise.all([loadRfis(), loadDashboard()]);
      if (state.drawerRecord?.id === id) view(id);
      if (typeof CasePMWorkflow !== 'undefined') CasePMWorkflow.onRFIStatusChange?.({ rfiId: id, status: official ? 'Answered' : 'Under Review' });
    } catch (e) { alert(e.message); }
  }

  async function workflow(id, action) {
    try {
      await api(`/api/rfis/${id}/workflow`, { method: 'POST', body: JSON.stringify({ action }) });
      toast('Workflow updated');
      await Promise.all([loadRfis(), loadDashboard()]);
      if (state.drawerRecord?.id === id) view(id);
    } catch (e) { alert(e.message); }
  }

  async function promotePco(id) {
    const amount = prompt('Estimated ROM for PCO ($):', '0');
    if (amount === null) return;
    try {
      const json = await api(`/api/rfis/${id}/promote-pco`, { method: 'POST', body: JSON.stringify({ estimated_amount: parseFloat(amount) || 0 }) });
      toast(`PCO ${json.pco?.number || ''} created from RFI`);
      await loadLinkOptions();
      if (state.drawerRecord?.id === id) view(id);
    } catch (e) { alert(e.message); }
  }

  async function addPlanPin(id) {
    const sheet = state.drawerRecord?.drawing_reference || '';
    const q = new URLSearchParams();
    const pid = projectId();
    if (pid) q.set('project_id', pid);
    if (sheet) q.set('sheet', sheet);
    q.set('rfi_id', id);
    global.location.href = `/drawings?${q.toString()}`;
  }

  async function removePin(id, index) {
    const r = await api(`/api/rfis/${id}`);
    const pins = [...(r.plan_pins || [])];
    const removed = pins[index];
    if (!removed) return;
    if (removed.markup_id) {
      try {
        await api(`/api/drawings/markups/${removed.markup_id}`, { method: 'DELETE' });
      } catch {
        pins.splice(index, 1);
        await api(`/api/rfis/${id}`, { method: 'PUT', body: JSON.stringify({ plan_pins: pins }) });
      }
    } else {
      pins.splice(index, 1);
      await api(`/api/rfis/${id}`, { method: 'PUT', body: JSON.stringify({ plan_pins: pins }) });
    }
    view(id);
  }

  async function edit(id) {
    const r = await api(`/api/rfis/${id}`);
    openModal('edit', r);
  }

  function exportExcel() {
    if (typeof XLSX === 'undefined') { alert('Excel library not loaded'); return; }
    const rows = filteredRfis().map(r => ({
      Number: r.number, Subject: r.subject, Status: r.status, Priority: r.priority,
      'Ball In Court': r.ball_in_court_role, Due: r.due_date, Drawing: r.drawing_reference,
      Spec: r.spec_reference, Company: r.received_from_company, Question: r.question,
      Answer: r.official_answer, 'Cost Impact': r.cost_impact_amount, 'Sched Days': r.schedule_impact_days,
    }));
    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'RFI Log');
    XLSX.writeFile(wb, `RFI_Log_${projectId() || 'project'}.xlsx`);
  }

  const RFI_BASE_PRINT_COLUMNS = [
    { key: 'number', label: 'RFI #', width: '5%', mono: true },
    { key: 'subject', label: 'Subject', width: '12%' },
    { key: 'question', label: 'Question', width: '14%' },
    { key: 'drawing_reference', label: 'Drawing', width: '6%', mono: true },
    { key: 'spec_reference', label: 'Spec', width: '6%', mono: true },
    { key: 'received_from_company', label: 'From<br>Company', width: '8%' },
    { key: 'to_party', label: 'To', width: '6%' },
    { key: 'priority', label: 'Priority', width: '5%', align: 'center' },
    { key: 'status', label: 'Status', width: '7%', align: 'center' },
    { key: 'ball_in_court_role', label: 'Ball<br>in Court', width: '7%', align: 'center' },
    { key: 'due_date', label: 'Due<br>Date', width: '6%', align: 'center' },
    { key: 'official_answer', label: 'Official<br>Answer', width: '12%' },
    { key: 'date', label: 'Date<br>Initiated', width: '6%', align: 'center' },
  ];

  const RFI_OPTIONAL_PRINT_FIELDS = [
    { key: 'from_party', label: 'From Party', default: false },
    { key: 'responsible_contractor', label: 'Responsible Contractor', default: false },
    { key: 'rfi_manager_name', label: 'RFI Manager', default: false },
    { key: 'discipline', label: 'Discipline', default: false },
    { key: 'location_description', label: 'Location', default: false },
    { key: 'cost_impact_amount', label: 'Cost Impact', default: false },
    { key: 'schedule_impact_days', label: 'Schedule Days', default: false },
    { key: 'notes', label: 'Notes', default: false },
  ];

  function printValue(r, key) {
    if (key === 'due_date' || key === 'date') return fmtDate(r[key]);
    if (key === 'cost_impact_amount') return r.cost_impact_amount ? '$' + Number(r.cost_impact_amount).toLocaleString() : '';
    return r[key] ?? '';
  }

  async function printLog() {
    if (typeof global.CasePMPrint === 'undefined') { alert('Print module not loaded'); return; }
    const picked = await global.CasePMPrint.showFieldPicker({
      title: 'Print RFI Log',
      note: 'Standard RFI register columns are always included. Choose extra columns to append on the right.',
      fields: RFI_OPTIONAL_PRINT_FIELDS,
    });
    if (!picked) return;
    const optional = RFI_OPTIONAL_PRINT_FIELDS.filter(f => picked.fields.includes(f.key))
      .map(f => ({ key: f.key, label: f.label.replace(/ /g, '<br>'), width: '6%' }));
    const columns = [...RFI_BASE_PRINT_COLUMNS, ...optional];
    const rows = filteredRfis().map(r => {
      const obj = {};
      columns.forEach(c => { obj[c.key] = printValue(r, c.key); });
      return obj;
    });
    const nameEl = document.getElementById('currentProjectName');
    const meta = { name: (nameEl?.textContent || '').trim() || 'Project', number: projectId() || '', location: '' };
    const html = global.CasePMPrint.buildPrintDocument({
      meta,
      sections: [{ title: 'RFI LOG', columns, rows, emptyMessage: 'No RFIs to print.' }],
      rowsPerPage: 24,
    });
    global.CasePMPrint.triggerPrintPreview(html, { containerId: 'rfiPrintSheet', bodyClass: 'printing-rfi-log' });
  }

  function toast(msg) {
    const t = document.createElement('div');
    t.className = 'fixed bottom-16 right-6 z-[70] px-4 py-2 rounded-md bg-emerald-900 text-emerald-100 text-sm shadow-lg';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2800);
  }

  async function init() {
    if (!projectId()) {
      alert('Select a project to manage RFIs.');
      return;
    }
    if (typeof CasePMWorkflow !== 'undefined') await CasePMWorkflow.loadPortal().catch(() => {});
    loadCompanies();
    bindFilters();
    await Promise.all([loadDashboard(), loadRfis(), loadLinkOptions()]);
    const params = new URLSearchParams(window.location.search);
    if (params.get('open') === '1' && params.get('rfi_id')) {
      const id = parseInt(params.get('rfi_id'), 10);
      if (id) await view(id);
    }
    if (new URLSearchParams(window.location.search).get('action') === 'new') {
      openModal('create');
    }
  }

  global.CasePMRfis = {
    init,
    newRfi: () => openModal('create'),
    saveModal,
    saveAsOpen: () => saveModal(true),
    view,
    edit,
    respond,
    workflow,
    promotePco,
    addPlanPin,
    removePin,
    closeDrawer,
    exportExcel,
    printLog,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
