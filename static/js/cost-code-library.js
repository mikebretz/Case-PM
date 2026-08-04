/**
 * Shared project cost code library (Accounting / Budget / Pay Apps / COs).
 */
(function (global) {
  'use strict';

  const TTL_MS = 60 * 1000;
  let cache = { projectId: null, payload: null, loadedAt: 0 };

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    const raw = global.localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function invalidate(pid) {
    if (!pid || pid === cache.projectId) {
      cache = { projectId: null, payload: null, loadedAt: 0 };
    }
  }

  async function fetchLibrary(pid, options) {
    const force = options && options.force;
    const id = pid || projectId();
    if (!id) return { cost_codes: [], cost_types: [], library: {} };
    const now = Date.now();
    if (!force && cache.projectId === id && cache.payload && now - cache.loadedAt < TTL_MS) {
      return cache.payload;
    }
    const res = await fetch(`/api/accounting/cost-code-library?project_id=${encodeURIComponent(id)}`, {
      credentials: 'same-origin',
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || res.statusText);
    cache = { projectId: id, payload: json, loadedAt: now };
    return json;
  }

  function asBudgetLineShape(codes) {
    return (codes || []).map((c) => ({
      cost_code: c.code,
      description: c.description || '',
      cost_type: c.cost_type || '',
      original_budget: c.original_budget,
      approved_changes: c.approved_changes,
      pending: c.pending,
    }));
  }

  async function budgetLinesForPicker(pid, options) {
    const data = await fetchLibrary(pid, options);
    const fromApi = asBudgetLineShape(data.cost_codes);
    if (fromApi.length) return fromApi;
    try {
      const store = global.casepmStore || global.localStorage;
      return JSON.parse(store.getItem('budgetLines') || '[]');
    } catch {
      return [];
    }
  }

  global.CasePMCostCodeLibrary = {
    fetchLibrary,
    budgetLinesForPicker,
    asBudgetLineShape,
    invalidate,
    projectId,
  };
})(typeof window !== 'undefined' ? window : globalThis);
