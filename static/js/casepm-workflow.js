/**
 * Case PM Workflow API — connects modules to approvals, internal comms, notifications.
 */
(function (global) {
  'use strict';

  let portal = null;

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options && options.headers) },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || res.statusText);
    }
    return res.json();
  }

  async function loadPortal() {
    if (portal) return portal;
    try {
      portal = await api('/api/portal/context');
    } catch (err) {
      console.warn('[CasePM] portal context unavailable, using page fallback', err);
      portal = buildFallbackPortalFromDom();
    }
    global.CASEPM_PORTAL = portal;
    return portal;
  }

  function buildFallbackPortalFromDom() {
    const body = document.body;
    const subVendor = !!(body && body.classList.contains('portal-sub-vendor'));
    const companyId = body && body.getAttribute('data-user-company-id');
    return {
      userId: Number((body && body.getAttribute('data-current-user-id')) || 0) || null,
      userName: (body && body.getAttribute('data-current-user')) || '',
      userEmail: (body && body.getAttribute('data-current-user-email')) || '',
      role: (body && body.getAttribute('data-current-user-role')) || '',
      companyId: companyId || null,
      companyName: (body && body.getAttribute('data-current-user-company')) || '',
      isSubVendorPayPortal: subVendor,
      vendorCompanyLinked: subVendor ? !!companyId : true,
      permissions: { global: {} },
    };
  }

  function projectId() {
    return Number(
      global.CASEPM_ACTIVE_PROJECT_ID ||
      (typeof casepmStore !== 'undefined' && casepmStore.projectId()) ||
      0
    ) || null;
  }

  function payAppUrl() {
    const pid = projectId();
    return pid ? `/pay-applications?project_id=${pid}` : '/pay-applications';
  }

  async function emit(event, data) {
    return api('/api/workflow/event', {
      method: 'POST',
      body: JSON.stringify({ event, project_id: projectId(), ...data }),
    });
  }

  async function requestApproval(opts) {
    return api('/api/approvals', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId(), ...opts }),
    });
  }

  async function decide(approvalId, decision, comments) {
    return api(`/api/approvals/${approvalId}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, comments: comments || '' }),
    });
  }

  async function fetchInternal(folder) {
    const q = folder ? `?folder=${encodeURIComponent(folder)}` : '';
    return api(`/api/internal-messages${q}`);
  }

  async function markInternalRead(msgId) {
    return api(`/api/internal-messages/${msgId}/read`, { method: 'POST' });
  }

  async function archiveInternal(msgId) {
    return api(`/api/internal-messages/${msgId}/archive`, { method: 'POST' });
  }

  async function saveModuleState(module, stateKey, data, companyId) {
    return api(`/api/module-state/${module}/${stateKey}?project_id=${projectId()}${companyId ? `&company_id=${companyId}` : ''}`, {
      method: 'PUT',
      body: JSON.stringify({ project_id: projectId(), company_id: companyId || null, data }),
    });
  }

  async function loadModuleState(module, stateKey, companyId) {
    const q = `?project_id=${projectId()}${companyId ? `&company_id=${companyId}` : ''}`;
    return api(`/api/module-state/${module}/${stateKey}${q}`);
  }

  function canApprove(module) {
    if (!portal) return false;
    if (portal.role === 'Admin' || portal.role === 'Developer') return true;
    return !!(portal.canApprove && portal.canApprove[module]);
  }

  function isSub() {
    return portal && portal.isSub;
  }

  function isArchitect() {
    return portal && portal.isArchitect;
  }

  // ─── Pay Application hooks ─────────────────────────────────
  async function onG702Submitted(period, snapshot) {
    const billingLines = snapshot?.billingLines || {};
    const sov = snapshot?.contractorSOV || [];
    const thisPeriodTotal = sov.reduce((sum, line) => {
      const b = billingLines[line.id] || {};
      return sum + (b.workThisPeriod || 0) + (b.materialsStored || 0) + (b.coWorkThisPeriod || 0);
    }, 0);
    return emit('submit', {
      module: 'Pay Applications',
      entity_type: 'G702',
      entity_id: `period-${period.periodNumber}`,
      title: `Pay Application #${period.periodNumber} submitted for review`,
      description: `GC pay application period ${period.periodNumber} — $${thisPeriodTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })} this period.`,
      action_url: payAppUrl(),
      payload: {
        snapshotType: 'g702',
        periodNumber: period.periodNumber,
        periodStart: period.periodStart,
        periodEnd: period.periodEnd,
        status: period.status || 'Submitted',
        budgetContractAmount: snapshot?.budgetContractAmount,
        contractorSOV: sov.map(line => ({
          id: line.id,
          cost_code: line.cost_code,
          description: line.description,
          original: line.original,
          co_amount: line.co_amount,
          billed_to_date: line.billed_to_date,
        })),
        billingLines,
        thisPeriodTotal,
      },
    });
  }

  async function onG702Approved(period) {
    return emit('notify', {
      module: 'Pay Applications',
      title: `Pay Application #${period.periodNumber} approved`,
      description: `Period ${period.periodNumber} has been approved and archived.`,
      action_url: payAppUrl(),
      folder: 'alerts',
      msg_type: 'alert',
    });
  }

  async function onG702RevisionRequested(period, reason) {
    return emit('notify', {
      module: 'Pay Applications',
      title: `Pay Application #${period.periodNumber} — revision requested`,
      description: reason || 'Please revise and resubmit.',
      action_url: payAppUrl(),
      folder: 'action-required',
      requires_action: true,
    });
  }

  async function onSubSOVSubmitted(companyId, companyName, snapshot) {
    const lines = (snapshot?.lines || []).map(line => ({
      cost_code: line.cost_code,
      description: line.description,
      original: line.original,
      co_amount: line.co_amount,
      billed_to_date: line.billed_to_date,
    }));
    const totalOriginal = lines.reduce((s, l) => s + (l.original || 0), 0);
    return emit('submit', {
      module: 'Pay Applications',
      entity_type: 'SubSOV',
      entity_id: String(companyId),
      company_id: Number(companyId) || null,
      title: `Sub SOV submitted — ${companyName}`,
      description: `${companyName} submitted Schedule of Values (${lines.length} lines, $${totalOriginal.toLocaleString(undefined, { minimumFractionDigits: 2 })} original).`,
      action_url: payAppUrl(),
      assignee_role: 'Project Manager',
      payload: {
        snapshotType: 'sub_sov',
        companyId,
        companyName,
        lines,
        totalOriginal,
      },
    });
  }

  async function onSubSOVApproved(companyId, companyName) {
    return emit('notify', {
      module: 'Pay Applications',
      title: `Sub SOV approved — ${companyName}`,
      description: 'Your Schedule of Values is approved. You may now submit monthly pay applications.',
      action_url: payAppUrl(),
      folder: 'team',
      msg_type: 'message',
      user_ids: portal && portal.isSub ? [portal.userId] : undefined,
    });
  }

  async function onSubPayAppSubmitted(companyId, companyName, periodNum, amount, snapshot) {
    return emit('submit', {
      module: 'Pay Applications',
      entity_type: 'SubPayApp',
      entity_id: `${companyId}-${periodNum}`,
      company_id: Number(companyId) || null,
      title: `Sub Pay App #${periodNum} — ${companyName}`,
      description: `Amount this period: $${Number(amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}.`,
      action_url: payAppUrl(),
      payload: {
        snapshotType: 'sub_pay_app',
        companyId,
        companyName,
        periodNum,
        amount,
        lines: snapshot?.lines || [],
        periodStart: snapshot?.periodStart,
        periodEnd: snapshot?.periodEnd,
      },
    });
  }

  async function onSubPayAppApproved(companyId, companyName, periodNum) {
    return emit('notify', {
      module: 'Pay Applications',
      title: `Pay App #${periodNum} approved — ${companyName}`,
      description: 'Your pay application has been approved and committed.',
      action_url: payAppUrl(),
      folder: 'team',
      msg_type: 'message',
    });
  }

  async function onSubPayAppRevision(companyId, companyName, periodNum, reason) {
    return emit('notify', {
      module: 'Pay Applications',
      title: `Pay App #${periodNum} revision — ${companyName}`,
      description: reason || 'Revision requested by PM.',
      action_url: payAppUrl(),
      folder: 'action-required',
      requires_action: true,
    });
  }

  async function notifySubPayAppDue(companyId, companyName, userId) {
    return emit('notify', {
      module: 'Pay Applications',
      title: `Submit Pay Application — ${companyName}`,
      description: 'Your pay application is due for the current billing period.',
      action_url: payAppUrl(),
      folder: 'action-required',
      user_ids: userId ? [userId] : [],
      requires_action: true,
    });
  }

  // ─── Submittals / RFIs / COs ───────────────────────────────
  async function onSubmittalToArchitect(submittal) {
    return emit('submit', {
      module: 'Submittals',
      entity_type: 'Submittal',
      entity_id: submittal.id || submittal.number,
      title: `Submittal ${submittal.number} — architect review`,
      description: submittal.description || submittal.title || '',
      action_url: `/submittals?project_id=${projectId()}`,
      assignee_role: 'Architect',
    });
  }

  async function onSubmittalDecision(submittal, decision) {
    return emit('notify', {
      module: 'Submittals',
      title: `Submittal ${submittal.number} — ${decision}`,
      description: submittal.review_comments || decision,
      action_url: `/submittals?project_id=${projectId()}`,
      folder: decision === 'Rejected' || decision === 'Revise & Resubmit' ? 'action-required' : 'alerts',
      requires_action: decision === 'Revise & Resubmit',
    });
  }

  async function onRFIStatusChange(rfi, newStatus) {
    if (newStatus === 'Awaiting Response') {
      return emit('submit', {
        module: 'RFIs',
        entity_type: 'RFI',
        entity_id: rfi.id,
        title: `RFI ${rfi.number} — response needed`,
        description: rfi.subject || '',
        action_url: `/rfis?project_id=${projectId()}`,
      });
    }
    return emit('notify', {
      module: 'RFIs',
      title: `RFI ${rfi.number} — ${newStatus}`,
      description: rfi.subject || '',
      action_url: `/rfis?project_id=${projectId()}`,
      folder: 'alerts',
    });
  }

  async function onChangeOrderSubmitted(co) {
    return emit('submit', {
      module: 'Change Orders',
      entity_type: 'ChangeOrder',
      entity_id: co.id,
      title: `Change Order ${co.number} pending approval`,
      description: co.description || '',
      action_url: `/change-orders?project_id=${projectId()}`,
      payload: {
        snapshotType: 'change_order',
        number: co.number,
        description: co.description || co.title || '',
        amount: co.amount,
        status: co.status,
      },
    });
  }

  async function onPCOSubmitted(pco) {
    return emit('submit', {
      module: 'Change Orders',
      entity_type: 'PCO',
      entity_id: pco.id,
      title: `PCO ${pco.number} — ${pco.title}`,
      description: pco.description || '',
      action_url: `/change-orders?project_id=${projectId()}`,
      payload: {
        snapshotType: 'pco',
        number: pco.number,
        title: pco.title,
        estimated_amount: pco.estimated_amount,
        status: pco.status,
      },
    });
  }

  // ─── Budget hooks ───────────────────────────────────────────
  async function onBudgetPublished(revision, snapshot) {
    const lines = snapshot?.budgetLines || [];
    const totalOriginal = lines.reduce((s, l) => s + (l.original_budget || 0), 0);
    return emit('submit', {
      module: 'Budget',
      entity_type: 'BudgetRevision',
      entity_id: `rev-${revision}`,
      title: `Budget Revision ${revision} published for approval`,
      description: `Budget published with ${lines.length} lines — $${totalOriginal.toLocaleString(undefined, { minimumFractionDigits: 2 })} original.`,
      action_url: `/budget?project_id=${projectId()}`,
      payload: {
        snapshotType: 'budget',
        revision,
        linesCount: lines.length,
        totalOriginal,
        contractAmount: snapshot?.budgetContractAmount,
      },
    });
  }

  async function onBudgetSaved(linesCount, totalOriginal) {
    return emit('notify', {
      module: 'Budget',
      title: 'Budget saved',
      description: `Budget draft saved (${linesCount} lines, $${totalOriginal.toLocaleString(undefined, { minimumFractionDigits: 2 })} original).`,
      action_url: `/budget?project_id=${projectId()}`,
      folder: 'team',
      msg_type: 'message',
    });
  }

  global.CasePMWorkflow = {
    loadPortal,
    projectId,
    emit,
    requestApproval,
    decide,
    fetchInternal,
    markInternalRead,
    archiveInternal,
    saveModuleState,
    loadModuleState,
    canApprove,
    isSub,
    isArchitect,
    onG702Submitted,
    onG702Approved,
    onG702RevisionRequested,
    onSubSOVSubmitted,
    onSubSOVApproved,
    onSubPayAppSubmitted,
    onSubPayAppApproved,
    onSubPayAppRevision,
    notifySubPayAppDue,
    onSubmittalToArchitect,
    onSubmittalDecision,
    onRFIStatusChange,
    onChangeOrderSubmitted,
    onPCOSubmitted,
    onBudgetPublished,
    onBudgetSaved,
  };
})(window);
