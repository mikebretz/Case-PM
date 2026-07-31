(function (global) {
  'use strict';
  const ctx = global.CASEPM_SUB_COMPLIANCE_CTX || {};
  function pid() { return ctx.projectId || parseInt(new URLSearchParams(location.search).get('project_id'), 10) || null; }

  async function loadLibrary() {
    const el = document.getElementById('subComplianceStatus');
    if (!el) return;
    try {
      const r = await fetch('/api/portal/compliance-library', { credentials: 'same-origin' });
      const j = await r.json();
      const invalid = (j.companies || []).filter((c) => !c.coi_valid).length;
      el.textContent = `${j.count || 0} companies · ${invalid} missing/expired COI`;
    } catch (_) {
      el.textContent = '';
    }
  }

  document.getElementById('subWaiverForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const projectId = pid();
    const companyId = document.getElementById('subCompanyId').value;
    const file = document.getElementById('subWaiverFile').files[0];
    if (!projectId || !companyId || !file) { alert('Project, company, and file required.'); return; }
    const fd = new FormData();
    fd.append('project_id', projectId);
    fd.append('company_id', companyId);
    fd.append('period', document.getElementById('subPeriod').value || '');
    fd.append('file', file);
    const r = await fetch('/api/portal/compliance/lien-waiver', { method: 'POST', credentials: 'same-origin', body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Upload failed');
    alert('Lien waiver registered for AP compliance.');
    loadLibrary();
  });

  document.getElementById('subCoiForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const companyId = document.getElementById('subCoiCompanyId').value;
    const file = document.getElementById('subCoiFile').files[0];
    const exp = document.getElementById('subCoiExp').value;
    if (!companyId || !file || !exp) { alert('Company, expiration, and file required.'); return; }
    const fd = new FormData();
    fd.append('company_id', companyId);
    fd.append('expiration_date', exp);
    fd.append('file', file);
    const r = await fetch('/api/portal/compliance/coi', { method: 'POST', credentials: 'same-origin', body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Upload failed');
    alert('COI saved.');
    loadLibrary();
  });

  loadLibrary();
})(window);
