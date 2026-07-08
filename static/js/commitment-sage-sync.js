/**
 * Commitment Sage 300 sync — queue events, manual sync, retry, integration status.
 */
(function (global) {
  'use strict';

  const COMMITMENT_SAGE_EVENTS = [
    'CommitmentSubmitted', 'CommitmentApproved', 'CommitmentApprovalStep',
    'CommitmentRejected', 'CommitmentVoided', 'CommitmentUpdated',
    'CommitmentDocuSignSent', 'CommitmentExecuted',
  ];

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    if (typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.projectId) return CasePMWorkflow.projectId();
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function sageAutoKey() {
    return `casepm_commitment_sage_auto_p${projectId() || 'default'}`;
  }

  function isAutoEnabled() {
    return localStorage.getItem(sageAutoKey()) !== '0';
  }

  function setAutoEnabled(on) {
    localStorage.setItem(sageAutoKey(), on ? '1' : '0');
  }

  async function fetchIntegrationStatus() {
    try {
      const res = await fetch('/api/integrations/status', { credentials: 'same-origin' });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  async function fetchSageEvents(limit) {
    const pid = projectId();
    if (!pid) return [];
    try {
      const res = await fetch(`/api/sage/sync-events?project_id=${pid}&limit=${limit || 50}`, { credentials: 'same-origin' });
      if (!res.ok) return [];
      const json = await res.json();
      return (json.events || []).filter(e => COMMITMENT_SAGE_EVENTS.includes(e.event_type));
    } catch {
      return [];
    }
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
      console.warn('[CommitmentSageSync] queue failed', e);
      return null;
    }
  }

  async function syncCommitment(commitmentId, eventType, message) {
    try {
      const res = await fetch(`/api/commitments/${commitmentId}/sage-sync`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_type: eventType || 'CommitmentUpdated', message }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Sage sync failed');
      return json;
    } catch (e) {
      console.warn('[CommitmentSageSync] sync failed', e);
      throw e;
    }
  }

  async function retryEvent(eventId) {
    const res = await fetch(`/api/sage/sync-events/${eventId}/retry`, {
      method: 'POST',
      credentials: 'same-origin',
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Retry failed');
    return json;
  }

  async function openCatina(commitmentId) {
    const res = await fetch(`/api/commitments/${commitmentId}/aia/catina-link`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Failed to get Catina link');
    if (json.url) window.open(json.url, '_blank', 'noopener');
    return json;
  }

  async function registerAiaDocument(commitmentId, docId, docUrl, provider) {
    const res = await fetch(`/api/commitments/${commitmentId}/aia/register-document`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: provider || 'catina',
        document_id: docId,
        document_url: docUrl,
      }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Register failed');
    return json;
  }

  async function exportAiaJson(commitmentId) {
    const res = await fetch(`/api/commitments/${commitmentId}/aia/export`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('Export failed');
    return await res.json();
  }

  global.CasePMCommitmentSageSync = {
    COMMITMENT_SAGE_EVENTS,
    projectId,
    isAutoEnabled,
    setAutoEnabled,
    fetchIntegrationStatus,
    fetchSageEvents,
    queueSageEvent,
    syncCommitment,
    retryEvent,
    openCatina,
    registerAiaDocument,
    exportAiaJson,
  };
})(window);
