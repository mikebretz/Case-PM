/**
 * Pay application unified workflow — server authority for status, ball-in-court, Sage queue.
 */
(function (global) {
  'use strict';

  function projectId() {
    if (global.CasePMPayAppSync && typeof global.CasePMPayAppSync.projectId === 'function') {
      return global.CasePMPayAppSync.projectId();
    }
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  async function api(path, opts) {
    const res = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  function applyState(state) {
    if (!state || !global.casepmStore) return;
    const keys = global.CasePMPayAppSync?.SYNC_KEYS;
    Object.keys(state).forEach((key) => {
      if (!keys || keys.has(key) || key.startsWith('_')) {
        global.casepmStore.setItem(key, JSON.stringify(state[key]));
      }
    });
    global.dispatchEvent(new CustomEvent('casepm:payapp-state-refreshed', { detail: state }));
  }

  async function workflow(entityType, action, body) {
    const pid = projectId();
    if (!pid) throw new Error('Select a project first');
    const json = await api('/api/pay-applications/workflow', {
      method: 'POST',
      body: JSON.stringify({
        project_id: pid,
        entity_type: entityType,
        action,
        ...body,
      }),
    });
    if (json.state) applyState(json.state);
    return json;
  }

  function canActOnBall(ballRole) {
    if (!ballRole) return false;
    if (typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.canApprove) {
      if (!CasePMWorkflow.canApprove('Pay Applications')) return false;
    }
    const portal = global.CASEPM_PORTAL;
    if (!portal || !portal.role) return true;
    const role = portal.role;
    if (role === 'Admin') return true;
    const map = {
      'Project Manager': ['Project Manager', 'Admin', 'Superintendent'],
      Owner: ['Owner', 'Admin'],
      'Contractor Accounting': ['Contractor Accounting', 'Admin'],
      Creator: ['Project Manager', 'Admin', 'Superintendent'],
      Subcontractor: ['Company User', 'Admin'],
    };
    return (map[ballRole] || [ballRole]).includes(role);
  }

  function g702ApprovableStatuses() {
    return ['Submitted', 'Under Review', 'Pending Owner', 'Pending Accounting'];
  }

  async function erpReview(eventId, action, notes) {
    return api(`/api/sage/sync-events/${eventId}/accounting`, {
      method: 'POST',
      body: JSON.stringify({ action, notes: notes || '' }),
    });
  }

  async function loadErpQueue() {
    const pid = projectId();
    if (!pid) return [];
    const json = await api(`/api/sage/sync-events?project_id=${pid}&limit=50`);
    return (json.events || []).filter((e) =>
      ['G702Submitted', 'G702Approved', 'SubPayAppSubmitted', 'SubPayAppApproved'].includes(e.event_type)
    );
  }

  function fmtMoney(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  async function renderErpTable(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const events = await loadErpQueue();
    if (!events.length) {
      el.innerHTML = '<tr><td colspan="6" class="px-4 py-10 text-center text-zinc-500">No pay app ERP events pending.</td></tr>';
      return;
    }
    el.innerHTML = events.map((e) => `
      <tr class="border-b border-zinc-800">
        <td class="px-4 py-2 text-xs">${e.created_at ? new Date(e.created_at).toLocaleString() : ''}</td>
        <td class="px-4 py-2 text-xs font-mono">${esc(e.event_type)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.accounting_status || e.status)}</td>
        <td class="px-4 py-2 text-xs">${esc(e.message || '')}</td>
        <td class="px-4 py-2 text-xs font-mono">${esc(e.sage_job_number || '')}</td>
        <td class="px-4 py-2 text-center text-xs">
          ${e.accounting_status === 'pending_review' ? `
            <button type="button" onclick="CasePMPayAppWorkflow.erpAccept(${e.id})" class="text-emerald-400 mr-2">Accept</button>
            <button type="button" onclick="CasePMPayAppWorkflow.erpReject(${e.id})" class="text-red-400">Reject</button>
          ` : esc(e.status)}
        </td>
      </tr>`).join('');
  }

  async function erpAccept(id) {
    await erpReview(id, 'accept');
    await renderErpTable('payAppErpTableBody');
    if (typeof renderSageSyncStatus === 'function') renderSageSyncStatus();
  }

  async function erpReject(id) {
    const notes = prompt('Rejection notes:') || '';
    if (!notes) return;
    await erpReview(id, 'reject', notes);
    await renderErpTable('payAppErpTableBody');
  }

  global.CasePMPayAppWorkflow = {
    workflow,
    applyState,
    canActOnBall,
    g702ApprovableStatuses,
    loadErpQueue,
    renderErpTable,
    erpAccept,
    erpReject,
    projectId,
  };
})(window);
