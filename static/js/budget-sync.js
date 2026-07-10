/**
 * Budget server sync — loads/saves project budget state via API while preserving
 * casepmStore localStorage for offline resilience and backward compatibility.
 */
(function (global) {
  'use strict';

  const SYNC_KEYS = new Set([
    'budgetLines', 'budgetRevision', 'budgetLocked', 'budgetSnapshots',
    'publishAuditLog', 'budgetAuditLog', 'costTypes', 'customCostCodes',
    'activeCostCodeList', 'budgetContractAmount', 'budgetPublished',
    'budgetSageSyncAutoEnabled',
  ]);

  let saveTimer = null;
  let serverVersion = 0;
  let enabled = true;

  function projectId() {
    if (typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.projectId) {
      return CasePMWorkflow.projectId();
    }
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function collectLocalBundle() {
    const store = global.casepmStore;
    if (!store) return {};
    const bundle = {};
    SYNC_KEYS.forEach(key => {
      const raw = store.getItem(key);
      if (raw != null) {
        try { bundle[key] = JSON.parse(raw); } catch { bundle[key] = raw; }
      }
    });
    return bundle;
  }

  function applyBundleToLocal(bundle) {
    const store = global.casepmStore;
    if (!store || !bundle) return;
    Object.keys(bundle).forEach(key => {
      if (!SYNC_KEYS.has(key)) return;
      const val = bundle[key];
      store.setItem(key, typeof val === 'string' ? val : JSON.stringify(val));
    });
  }

  async function loadFromServer() {
    const pid = projectId();
    if (!pid || !enabled) return null;
    try {
      const res = await fetch(`/api/budget/state?project_id=${pid}`, { credentials: 'same-origin' });
      if (!res.ok) return null;
      const json = await res.json();
      if (!json.data) return null;
      serverVersion = json.version || 0;
      applyBundleToLocal(json.data);
      return json;
    } catch (e) {
      console.warn('[BudgetSync] load failed', e);
      return null;
    }
  }

  async function saveToServer(patch, fullReplace) {
    const pid = projectId();
    if (!pid || !enabled) return null;
    const body = {
      project_id: pid,
      full_replace: !!fullReplace,
      data: fullReplace ? collectLocalBundle() : (patch || collectLocalBundle()),
    };
    if (!fullReplace && patch) body.patch = patch;
    try {
      const res = await fetch('/api/budget/state', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) return null;
      const json = await res.json();
      serverVersion = json.version || serverVersion;
      return json;
    } catch (e) {
      console.warn('[BudgetSync] save failed', e);
      return null;
    }
  }

  function scheduleSave(patch) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveToServer(patch, false), 800);
  }

  function patchSafeSetLocalStorage() {
    const store = global.casepmStore;
    if (!store || store._budgetSyncPatched) return;
    const original = store.setItem.bind(store);
    store.setItem = function (key, value) {
      original(key, value);
      if (SYNC_KEYS.has(key)) {
        let parsed;
        try { parsed = JSON.parse(value); } catch { parsed = value; }
        scheduleSave({ [key]: parsed });
      }
    };
    store._budgetSyncPatched = true;
  }

  async function importLocalIfServerEmpty() {
    const pid = projectId();
    if (!pid) return;
    const loaded = await loadFromServer();
    if (loaded && loaded.data) return;
    const bundle = collectLocalBundle();
    if (!Object.keys(bundle).length) return;
    await fetch('/api/budget/import-local', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: pid, data: bundle }),
    });
  }

  async function queueSageEvent(eventType, payload, message) {
    const pid = projectId();
    if (!pid) return null;
    try {
      const res = await fetch('/api/sage/sync-events', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid, event_type: eventType, payload, message }),
      });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn('[BudgetSync] sage queue failed', e);
      return null;
    }
  }

  async function fetchSageEvents(limit) {
    const pid = projectId();
    if (!pid) return [];
    try {
      const res = await fetch(`/api/sage/sync-events?project_id=${pid}&limit=${limit || 40}`, { credentials: 'same-origin' });
      if (!res.ok) return [];
      const json = await res.json();
      return (json.events || []).filter(e =>
        ['BudgetSaved', 'BudgetPublished', 'BudgetSageSync', 'ChangeOrderApproved'].includes(e.event_type)
      );
    } catch {
      return [];
    }
  }

  async function fetchPendingChangeOrders() {
    const pid = projectId();
    if (!pid) return [];
    try {
      const res = await fetch(`/api/budget/pending-change-orders?project_id=${pid}`, { credentials: 'same-origin' });
      if (!res.ok) return [];
      const json = await res.json();
      return json.pending_items || json.change_orders || [];
    } catch {
      return [];
    }
  }

  async function refreshFromServer() {
    const json = await loadFromServer();
    if (json && json.data) {
      global.dispatchEvent(new CustomEvent('casepm:budget-state-refreshed', { detail: json.data }));
    }
    return json;
  }

  function applyBudgetSyncResult(syncResult) {
    if (!syncResult || !syncResult.budgetLines) return false;
    const store = global.casepmStore;
    if (!store) return false;
    store.setItem('budgetLines', JSON.stringify(syncResult.budgetLines));
    return true;
  }

  async function init() {
    patchSafeSetLocalStorage();
    if (typeof CasePMWorkflow !== 'undefined') {
      try { await CasePMWorkflow.loadPortal(); } catch { /* ignore */ }
    }
    await importLocalIfServerEmpty();
    return loadFromServer();
  }

  global.CasePMBudgetSync = {
    init,
    loadFromServer,
    saveToServer,
    collectLocalBundle,
    applyBundleToLocal,
    applyBudgetSyncResult,
    refreshFromServer,
    queueSageEvent,
    fetchSageEvents,
    fetchPendingChangeOrders,
    SYNC_KEYS,
  };
})(window);
