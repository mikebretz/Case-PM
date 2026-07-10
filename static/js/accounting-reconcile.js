/**
 * Project-wide accounting reconciliation — keeps budget, pay apps, commitments, and COs in sync.
 */
(function (global) {
  'use strict';

  let reconcilePromise = null;
  let lastReconcileAt = 0;
  const MIN_INTERVAL_MS = 3000;

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    if (typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.projectId) return CasePMWorkflow.projectId();
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function applyReconcileResult(json) {
    if (!json) return false;
    let updated = false;
    if (json.budget_sync_result && typeof CasePMBudgetSync !== 'undefined') {
      updated = CasePMBudgetSync.applyBudgetSyncResult(json.budget_sync_result) || updated;
    }
    if (json.sync_result && typeof CasePMPayAppSync !== 'undefined') {
      updated = CasePMPayAppSync.applyCoSyncResult(json.sync_result) || updated;
    }
    if (updated || json.budget_sync_result || json.sync_result) {
      global.dispatchEvent(new CustomEvent('casepm:accounting-reconciled', { detail: json }));
    }
    return updated;
  }

  async function reconcileProject(options) {
    const pid = projectId();
    if (!pid) return null;
    const force = options && options.force;
    const now = Date.now();
    if (!force && reconcilePromise) return reconcilePromise;
    if (!force && now - lastReconcileAt < MIN_INTERVAL_MS) return null;

    reconcilePromise = (async () => {
      try {
        const res = await fetch(`/api/accounting/reconcile?project_id=${pid}`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(json.error || 'Accounting reconcile failed');
        lastReconcileAt = Date.now();
        applyReconcileResult(json);
        return json;
      } catch (err) {
        console.warn('[AccountingReconcile]', err.message || err);
        return null;
      } finally {
        reconcilePromise = null;
      }
    })();
    return reconcilePromise;
  }

  async function initAndReconcile() {
    const tasks = [];
    if (typeof CasePMBudgetSync !== 'undefined') tasks.push(CasePMBudgetSync.init());
    if (typeof CasePMPayAppSync !== 'undefined') tasks.push(CasePMPayAppSync.init());
    await Promise.all(tasks);
    return reconcileProject({ force: true });
  }

  global.CasePMAccountingReconcile = {
    reconcileProject,
    initAndReconcile,
    applyReconcileResult,
  };
})(window);
