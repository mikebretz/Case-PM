/**
 * Pay Application server sync — loads/saves project state via API while preserving
 * casepmStore localStorage for offline resilience and backward compatibility.
 */
(function (global) {
  'use strict';

  const SYNC_KEYS = new Set([
    'contractorSOV', 'payAppBillingLines', 'currentPayAppPeriod', 'payAppHistory',
    'subcontractorSOV', 'subPayAppHistory', 'subPendingSubmissions', 'subPayAppNumbers',
    'subSOVStatus', 'subLienWaivers', 'subLienWaiverArchive', 'previousSubPayAppArchive',
    'mainLienWaiver', 'payAppRetainagePercent', 'requireLienWaiverOnSubPayApp',
    'requireSubmissionDeadline', 'submissionDeadlineDay', 'allowZeroDollarSubPayApps',
    'requireAllSubPayAppsBeforeG702Submit', 'payAppAuditLog', 'sageSyncAutoEnabled',
    'contractorSOVLocked',
  ]);

  let saveTimer = null;
  let serverVersion = 0;
  let enabled = true;
  let saveInFlight = null;

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
      const res = await fetch(`/api/pay-applications/state?project_id=${pid}`, { credentials: 'same-origin' });
      if (!res.ok) return null;
      const json = await res.json();
      if (!json.data) return null;
      serverVersion = json.version || 0;
      applyBundleToLocal(json.data);
      return json;
    } catch (e) {
      console.warn('[PayAppSync] load failed', e);
      return null;
    }
  }

  async function saveToServer(patch, fullReplace) {
    const pid = projectId();
    if (!pid || !enabled) {
      return {
        ok: false,
        error: !pid
          ? 'No project selected. Choose a project from the header dropdown, then save again.'
          : 'Pay app sync is disabled.',
      };
    }
    const body = {
      project_id: pid,
      full_replace: !!fullReplace,
      data: fullReplace ? collectLocalBundle() : (patch || collectLocalBundle()),
    };
    if (!fullReplace && patch) body.patch = patch;
    try {
      const res = await fetch('/api/pay-applications/state', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        return { ok: false, error: json.error || `Save failed (HTTP ${res.status})` };
      }
      serverVersion = json.version || serverVersion;
      return { ok: true, ...json };
    } catch (e) {
      console.warn('[PayAppSync] save failed', e);
      return { ok: false, error: e.message || 'Network error while saving' };
    }
  }

  function scheduleSave(patch) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      saveTimer = null;
      saveToServer(patch, false);
    }, 800);
  }

  function isSavePending() {
    return !!saveTimer || !!saveInFlight;
  }

  async function flushSave() {
    clearTimeout(saveTimer);
    saveTimer = null;
    if (saveInFlight) {
      try { await saveInFlight; } catch { /* ignore */ }
    }
    saveInFlight = saveToServer(null, true);
    try {
      return await saveInFlight;
    } finally {
      saveInFlight = null;
    }
  }

  function patchSafeSetLocalStorage() {
    const store = global.casepmStore;
    if (!store || store._payAppSyncPatched) return;
    const original = store.setItem.bind(store);
    store.setItem = function (key, value) {
      original(key, value);
      if (SYNC_KEYS.has(key)) {
        let parsed;
        try { parsed = JSON.parse(value); } catch { parsed = value; }
        scheduleSave({ [key]: parsed });
      }
    };
    store._payAppSyncPatched = true;
  }

  async function importLocalIfServerEmpty() {
    const pid = projectId();
    if (!pid) return;
    const loaded = await loadFromServer();
    if (loaded && loaded.data) return;
    const bundle = collectLocalBundle();
    if (!Object.keys(bundle).length) return;
    await fetch('/api/pay-applications/import-local', {
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
      console.warn('[PayAppSync] sage queue failed', e);
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
      return json.events || [];
    } catch {
      return [];
    }
  }

  function applyContractorSovToLocal(sovLines) {
    const store = global.casepmStore;
    if (!store || !Array.isArray(sovLines)) return false;
    store.setItem('contractorSOV', JSON.stringify(sovLines));
    return true;
  }

  function applySubSovToLocal(subSov) {
    const store = global.casepmStore;
    if (!store || !subSov || typeof subSov !== 'object') return false;
    store.setItem('subcontractorSOV', JSON.stringify(subSov));
    return true;
  }

  function applyCoSyncResult(syncResult) {
    if (!syncResult || syncResult.error) return false;
    let updated = false;
    if (syncResult.contractorSOV) {
      applyContractorSovToLocal(syncResult.contractorSOV);
      updated = true;
    }
    if (syncResult.subcontractorSOV) {
      applySubSovToLocal(syncResult.subcontractorSOV);
      updated = true;
    }
    return updated;
  }

  async function refreshFromServer() {
    const json = await loadFromServer();
    if (json && json.data) {
      global.dispatchEvent(new CustomEvent('casepm:payapp-state-refreshed', { detail: json.data }));
    }
    return json;
  }

  async function init() {
    patchSafeSetLocalStorage();
    if (typeof CasePMWorkflow !== 'undefined') {
      try { await CasePMWorkflow.loadPortal(); } catch { /* ignore */ }
    }
    await importLocalIfServerEmpty();
    await loadFromServer();
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden' && (saveTimer || saveInFlight)) {
          flushSave().catch(() => {});
        }
      });
      window.addEventListener('pagehide', () => {
        if (saveTimer || saveInFlight) {
          flushSave().catch(() => {});
        }
      });
    }
  }

  global.CasePMPayAppSync = {
    init,
    loadFromServer,
    saveToServer,
    flushSave,
    isSavePending,
    collectLocalBundle,
    applyBundleToLocal,
    applyContractorSovToLocal,
    applySubSovToLocal,
    applyCoSyncResult,
    refreshFromServer,
    queueSageEvent,
    fetchSageEvents,
    SYNC_KEYS,
  };
})(window);
