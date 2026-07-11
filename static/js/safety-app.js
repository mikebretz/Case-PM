/**
 * Case PM Safety — observations/incidents, personnel OSHA training, and OSHA library.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_SAFETY_CTX || {};
  const state = {
    tab: 'reports',
    reports: [], rStats: {}, rTypes: [], rSeverities: [], rStatuses: [], rEditId: null, rPhotos: [], rExisting: [],
    certs: [], cStats: {}, cTypes: [], cEditId: null,
    library: [],
  };

  function projectId() { return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })(); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(id) { return document.getElementById(id); }
  function fmtDate(iso) { if (!iso) return ''; try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); } catch (_) { return iso; } }
  async function api(url, opts) { const r = await fetch(url, opts); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'Request failed'); return j; }
  function fillSelect(sel, opts, val, blank) { sel.innerHTML = (blank ? `<option value="">${blank}</option>` : '') + opts.map((o) => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join(''); }

  // ---------------- Tabs ----------------
  function setTab(tab) {
    state.tab = tab;
    document.querySelectorAll('.saf-tab').forEach((t) => t.classList.toggle('active', t.getAttribute('data-tab') === tab));
    el('safTabReports').classList.toggle('hidden', tab !== 'reports');
    el('safTabTraining').classList.toggle('hidden', tab !== 'training');
    el('safTabLibrary').classList.toggle('hidden', tab !== 'library');
    const label = el('safBtnNewLabel');
    el('safBtnNew').style.display = (tab === 'library') ? 'none' : '';
    if (label) label.textContent = tab === 'training' ? 'Add Certification' : 'New Report';
    if (tab === 'library' && !state.library.length) loadLibrary();
    if (tab === 'training' && !state.certs.length) loadCerts();
  }

  // ---------------- Reports ----------------
  async function loadReports() {
    const pid = projectId();
    el('safStatusText').textContent = 'Loading…';
    try {
      const j = await api(`/api/safety/reports${pid ? `?project_id=${pid}` : ''}`);
      state.reports = j.reports || []; state.rStats = j.stats || {};
      state.rTypes = j.types || []; state.rSeverities = j.severities || []; state.rStatuses = j.statuses || [];
      if (el('rTypeFilter').options.length <= 1) state.rTypes.forEach((t) => el('rTypeFilter').add(new Option(t, t)));
      if (el('rStatusFilter').options.length <= 1) state.rStatuses.forEach((t) => el('rStatusFilter').add(new Option(t, t)));
      const badge = el('safProjectBadge'); if (badge) badge.textContent = ctx.projectName || 'All projects';
      renderReportStats(); renderReports();
      el('safUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
      el('safStatusText').textContent = `${state.reports.length} report(s)`;
    } catch (e) { el('safStatusText').textContent = 'Error: ' + e.message; }
  }
  function renderReportStats() {
    const s = state.rStats;
    el('rstatDays').textContent = s.days_without_incident == null ? '—' : s.days_without_incident;
    el('rstatIncidents').textContent = s.incidents_ytd ?? 0;
    el('rstatNear').textContent = s.near_misses ?? 0;
    el('rstatObs').textContent = s.observations ?? 0;
    el('rstatOpen').textContent = s.open ?? 0;
    el('rstatTotal').textContent = s.total ?? 0;
  }
  function sevChip(s) { const m = { Low: 'bg-zinc-700 text-zinc-300', Medium: 'bg-amber-500/15 text-amber-400', High: 'bg-orange-500/15 text-orange-400', Critical: 'bg-red-500/15 text-red-400' }; return `<span class="saf-chip ${m[s] || 'bg-zinc-700 text-zinc-300'}">${esc(s)}</span>`; }
  function rStatusChip(s) { const open = s !== 'Closed'; return `<span class="saf-chip ${open ? 'bg-sky-500/15 text-sky-400' : 'bg-emerald-500/15 text-emerald-400'}">${esc(s)}</span>`; }
  function typeIcon(t) { const m = { 'Incident': 'fa-triangle-exclamation text-red-400', 'Injury': 'fa-kit-medical text-red-400', 'Near Miss': 'fa-circle-exclamation text-amber-400', 'Observation': 'fa-eye text-sky-400', 'Toolbox Talk': 'fa-comments text-emerald-400', 'Inspection': 'fa-clipboard-check text-teal-300', 'Violation': 'fa-ban text-red-400', 'Property Damage': 'fa-house-crack text-orange-400' }; return m[t] || 'fa-shield-halved text-zinc-400'; }
  function renderReports() {
    const term = (el('rSearch').value || '').toLowerCase();
    const tf = el('rTypeFilter').value, sf = el('rStatusFilter').value;
    const rows = state.reports.filter((r) => {
      if (tf && r.type !== tf) return false;
      if (sf && r.status !== sf) return false;
      if (term && !`${r.number} ${r.description} ${r.location || ''} ${r.assigned_to || ''}`.toLowerCase().includes(term)) return false;
      return true;
    });
    const host = el('rList');
    if (!rows.length) { host.innerHTML = `<div class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-shield-heart text-4xl mb-3 block text-zinc-600"></i>No safety reports yet.</div>`; return; }
    host.innerHTML = rows.map((r) => `
      <div class="saf-row" data-open="${r.id}">
        <i class="fa-solid ${typeIcon(r.type)} text-lg w-6 text-center"></i>
        <div class="min-w-0 flex-1">
          <div class="text-sm truncate">${esc(r.description)}</div>
          <div class="saf-meta">
            <span class="font-mono">${esc(r.number || '')}</span>
            <span>${esc(r.type || '')}</span>
            ${r.location ? `<span><i class="fa-solid fa-location-dot"></i> ${esc(r.location)}</span>` : ''}
            ${r.assigned_to ? `<span><i class="fa-solid fa-user"></i> ${esc(r.assigned_to)}</span>` : ''}
            ${r.report_date ? `<span><i class="fa-solid fa-calendar"></i> ${fmtDate(r.report_date)}</span>` : ''}
            ${r.photo_count ? `<span><i class="fa-solid fa-image"></i> ${r.photo_count}</span>` : ''}
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">${sevChip(r.severity)}${rStatusChip(r.status)}</div>
      </div>`).join('');
    host.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openReport(parseInt(n.getAttribute('data-open'), 10))));
  }

  function resetReportModal() {
    state.rEditId = null; state.rPhotos = []; state.rExisting = [];
    el('rModalTitle').textContent = 'New Safety Report';
    fillSelect(el('rType'), state.rTypes, 'Observation');
    fillSelect(el('rSeverity'), state.rSeverities, 'Medium');
    fillSelect(el('rStatus'), state.rStatuses, 'Open');
    ['rDesc', 'rLocation', 'rAssigned', 'rDue', 'rImmediate', 'rRoot', 'rCorrective'].forEach((id) => { el(id).value = ''; });
    el('rDelete').classList.add('hidden');
    renderRPhotos();
  }
  function openReportCreate() { resetReportModal(); el('rModal').showModal(); }
  async function openReport(id) {
    resetReportModal();
    try {
      const j = await api(`/api/safety/reports/${id}`); const r = j.report; state.rEditId = id;
      el('rModalTitle').textContent = r.number || 'Safety Report';
      fillSelect(el('rType'), state.rTypes, r.type);
      fillSelect(el('rSeverity'), state.rSeverities, r.severity);
      fillSelect(el('rStatus'), state.rStatuses, r.status);
      el('rDesc').value = r.description || ''; el('rLocation').value = r.location || ''; el('rAssigned').value = r.assigned_to || '';
      el('rDue').value = r.due_date || ''; el('rImmediate').value = r.immediate_actions || ''; el('rRoot').value = r.root_cause || ''; el('rCorrective').value = r.corrective_actions || '';
      state.rExisting = r.photos || []; renderRPhotos();
      el('rDelete').classList.remove('hidden');
      el('rModal').showModal();
    } catch (e) { alert(e.message); }
  }
  function renderRPhotos() {
    const grid = el('rPhotoGrid'); let html = '';
    state.rPhotos.forEach((p) => { html += `<div class="relative rounded overflow-hidden border border-zinc-700"><img src="${p.url}" style="width:100%;height:72px;object-fit:cover;"><button data-delp="${p.id}" class="absolute top-1 right-1 bg-black/70 text-white w-5 h-5 rounded-full text-xs">×</button></div>`; });
    state.rExisting.forEach((p) => { html += `<div class="rounded overflow-hidden border border-zinc-700"><img src="${esc(p.url || '')}" style="width:100%;height:72px;object-fit:cover;"></div>`; });
    grid.innerHTML = html || '<div class="text-xs text-zinc-500 col-span-full py-2 text-center">No photos.</div>';
    el('rPhotoCount').textContent = (state.rPhotos.length + state.rExisting.length) ? `(${state.rPhotos.length + state.rExisting.length})` : '';
    grid.querySelectorAll('[data-delp]').forEach((n) => n.addEventListener('click', () => { const id = n.getAttribute('data-delp'); state.rPhotos = state.rPhotos.filter((p) => String(p.id) !== id); renderRPhotos(); }));
  }
  async function saveReport() {
    const pid = projectId(); const desc = el('rDesc').value.trim();
    if (!pid || !desc) { alert('Description is required.'); return; }
    const payload = { project_id: pid, type: el('rType').value, severity: el('rSeverity').value, status: el('rStatus').value,
      description: desc, location: el('rLocation').value.trim(), assigned_to: el('rAssigned').value.trim(), due_date: el('rDue').value,
      immediate_actions: el('rImmediate').value.trim(), root_cause: el('rRoot').value.trim(), corrective_actions: el('rCorrective').value.trim() };
    const btn = el('rSave'); btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const url = state.rEditId ? `/api/safety/reports/${state.rEditId}` : '/api/safety/reports';
      const j = await api(url, { method: state.rEditId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const rid = j.report.id;
      for (const p of state.rPhotos) { const fd = new FormData(); fd.append('file', p.blob, `${p.name}.jpg`); fd.append('name', p.name); fd.append('kind', 'photo'); await fetch(`/api/safety/reports/${rid}/attachments`, { method: 'POST', body: fd }); }
      state.rPhotos = []; el('rModal').close(); await loadReports();
      if (global.showToast) global.showToast('Safety report saved');
    } catch (e) { alert(e.message); } finally { btn.disabled = false; btn.textContent = 'Save'; }
  }
  async function delReport() { if (!state.rEditId || !confirm('Delete this report?')) return; try { await api(`/api/safety/reports/${state.rEditId}`, { method: 'DELETE' }); el('rModal').close(); await loadReports(); } catch (e) { alert(e.message); } }

  // ---------------- Certifications ----------------
  async function loadCerts() {
    const pid = projectId();
    try {
      const j = await api(`/api/safety/certifications${pid ? `?project_id=${pid}` : ''}`);
      state.certs = j.certifications || []; state.cStats = j.stats || {}; state.cTypes = j.cert_types || [];
      if (el('cTypeFilter').options.length <= 1) state.cTypes.forEach((t) => el('cTypeFilter').add(new Option(t, t)));
      const dl = el('cCompanyList'); const set = new Set(); state.certs.forEach((c) => { if (c.company) set.add(c.company); });
      dl.innerHTML = [...set].map((c) => `<option value="${esc(c)}">`).join('');
      renderCertStats(); renderCerts();
    } catch (e) { el('safStatusText').textContent = 'Error: ' + e.message; }
  }
  function renderCertStats() {
    const s = state.cStats;
    el('cstatPeople').textContent = s.people ?? 0; el('cstatTotal').textContent = s.total ?? 0;
    el('cstatOsha').textContent = s.osha_certs ?? 0; el('cstatValid').textContent = s.valid ?? 0;
    el('cstatExpiring').textContent = s.expiring_soon ?? 0; el('cstatExpired').textContent = s.expired ?? 0;
  }
  function certStatusChip(s) { const m = { Valid: 'bg-emerald-500/15 text-emerald-400', 'Expiring Soon': 'bg-amber-500/15 text-amber-400', Expired: 'bg-red-500/15 text-red-400' }; return `<span class="saf-chip ${m[s] || 'bg-zinc-700 text-zinc-300'}">${esc(s)}</span>`; }
  function renderCerts() {
    const term = (el('cSearch').value || '').toLowerCase();
    const tf = el('cTypeFilter').value, sf = el('cStatusFilter').value;
    const rows = state.certs.filter((c) => {
      if (tf && c.cert_type !== tf) return false;
      if (sf && c.cert_status !== sf) return false;
      if (term && !`${c.person_name} ${c.company || ''} ${c.cert_type} ${c.trade || ''}`.toLowerCase().includes(term)) return false;
      return true;
    });
    const tb = el('cList');
    if (!rows.length) { tb.innerHTML = `<tr><td colspan="6" class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-id-card text-4xl mb-3 block text-zinc-600"></i>No certifications yet. Add OSHA 10/30, First Aid, CPR, etc.</td></tr>`; return; }
    tb.innerHTML = rows.map((c) => `
      <tr class="hover:bg-zinc-800/50 cursor-pointer" data-open="${c.id}">
        <td class="px-4 py-3 font-medium">${esc(c.person_name)}${c.trade ? `<span class="text-xs text-zinc-500"> · ${esc(c.trade)}</span>` : ''}</td>
        <td class="px-4 py-3 text-zinc-300 saf-hide-mobile">${esc(c.company || '—')}</td>
        <td class="px-4 py-3">${esc(c.cert_type)}${c.card_number ? `<span class="text-xs text-zinc-500"> · #${esc(c.card_number)}</span>` : ''}</td>
        <td class="px-4 py-3 text-zinc-400 saf-hide-mobile">${fmtDate(c.issued_date) || '—'}</td>
        <td class="px-4 py-3 ${c.cert_status === 'Expired' ? 'text-red-400' : c.cert_status === 'Expiring Soon' ? 'text-amber-400' : 'text-zinc-300'}">${fmtDate(c.expiration_date) || '—'}${c.days_left != null && c.days_left >= 0 && c.cert_status === 'Expiring Soon' ? ` (${c.days_left}d)` : ''}</td>
        <td class="px-4 py-3 text-center">${certStatusChip(c.cert_status)}</td>
      </tr>`).join('');
    tb.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openCert(parseInt(n.getAttribute('data-open'), 10))));
  }
  function resetCertModal() {
    state.cEditId = null; el('cModalTitle').textContent = 'New Certification';
    ['cPerson', 'cCompany', 'cTrade', 'cCard', 'cIssuer', 'cIssued', 'cExpiration', 'cNotes'].forEach((id) => { el(id).value = ''; });
    fillSelect(el('cType'), state.cTypes, 'OSHA 10');
    el('cDelete').classList.add('hidden');
  }
  function openCertCreate() { if (!state.cTypes.length) { loadCerts().then(() => { resetCertModal(); el('cModal').showModal(); }); return; } resetCertModal(); el('cModal').showModal(); }
  function openCert(id) {
    const c = state.certs.find((x) => x.id === id); if (!c) return;
    resetCertModal(); state.cEditId = id; el('cModalTitle').textContent = c.person_name;
    el('cPerson').value = c.person_name || ''; el('cCompany').value = c.company || ''; el('cTrade').value = c.trade || '';
    el('cCard').value = c.card_number || ''; el('cIssuer').value = c.issuer || ''; el('cIssued').value = c.issued_date || '';
    el('cExpiration').value = c.expiration_date || ''; el('cNotes').value = c.notes || '';
    fillSelect(el('cType'), state.cTypes, c.cert_type);
    el('cDelete').classList.remove('hidden');
    el('cModal').showModal();
  }
  async function saveCert() {
    const person = el('cPerson').value.trim(); const type = el('cType').value;
    if (!person) { alert('Person name is required.'); return; }
    const payload = { project_id: projectId(), person_name: person, company: el('cCompany').value.trim(), trade: el('cTrade').value.trim(),
      cert_type: type, card_number: el('cCard').value.trim(), issuer: el('cIssuer').value.trim(),
      issued_date: el('cIssued').value, expiration_date: el('cExpiration').value, notes: el('cNotes').value.trim() };
    const btn = el('cSave'); btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const url = state.cEditId ? `/api/safety/certifications/${state.cEditId}` : '/api/safety/certifications';
      await api(url, { method: state.cEditId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      el('cModal').close(); await loadCerts();
      if (global.showToast) global.showToast('Certification saved');
    } catch (e) { alert(e.message); } finally { btn.disabled = false; btn.textContent = 'Save'; }
  }
  async function delCert() { if (!state.cEditId || !confirm('Delete this certification?')) return; try { await api(`/api/safety/certifications/${state.cEditId}`, { method: 'DELETE' }); el('cModal').close(); await loadCerts(); } catch (e) { alert(e.message); } }

  // ---------------- OSHA Library ----------------
  async function loadLibrary() {
    try {
      const j = await api('/api/safety/osha-library');
      state.library = j.library || [];
      renderLibrary();
    } catch (e) { el('safLibrary').innerHTML = `<div class="text-red-400">${esc(e.message)}</div>`; }
  }
  function renderLibrary() {
    el('safLibrary').innerHTML = state.library.map((it) => {
      const viewUrl = it.local_url || it.pdf_url || it.topic_url;
      return `<div class="saf-card flex flex-col">
        <div class="flex items-start justify-between gap-2">
          <div class="font-medium text-sm">${esc(it.title)}</div>
          ${it.pub ? `<span class="saf-chip bg-zinc-800 text-zinc-400 font-mono">${esc(it.pub)}</span>` : ''}
        </div>
        <div class="text-xs text-zinc-500 mt-1 flex-1">${esc(it.description || '')}</div>
        <div class="text-[10px] text-zinc-500 mt-2"><span class="saf-chip bg-zinc-800 text-zinc-400">${esc(it.category || '')}</span>${it.bundled_file ? '<span class="saf-chip bg-emerald-500/15 text-emerald-400 ml-1">Bundled</span>' : ''}</div>
        <div class="flex gap-2 mt-3">
          <a href="${esc(viewUrl)}" target="_blank" class="flex-1 text-center px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-md text-xs"><i class="fa-solid fa-arrow-up-right-from-square mr-1"></i>View</a>
          <button type="button" data-save="${esc(it.key)}" class="flex-1 px-3 py-1.5 bg-sky-600 hover:bg-sky-500 rounded-md text-xs font-medium"><i class="fa-solid fa-download mr-1"></i>Save</button>
        </div>
      </div>`;
    }).join('');
    el('safLibrary').querySelectorAll('[data-save]').forEach((n) => n.addEventListener('click', () => saveToDocuments([n.getAttribute('data-save')])));
  }
  async function saveToDocuments(keys) {
    const pid = projectId();
    if (!pid) { alert('Select a project first.'); return; }
    el('safStatusText').textContent = 'Saving to Documents…';
    try {
      const j = await api(`/api/safety/osha-library/save-to-documents?project_id=${pid}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ keys: keys || null }) });
      const msg = `Saved ${j.saved_count} to Documents › Safety › OSHA Reference${j.failed && j.failed.length ? ` (${j.failed.length} unavailable)` : ''}`;
      el('safStatusText').textContent = msg;
      if (global.showToast) global.showToast(msg);
    } catch (e) { el('safStatusText').textContent = 'Error: ' + e.message; alert(e.message); }
  }

  // ---------------- Init ----------------
  function bind() {
    document.querySelectorAll('.saf-tab').forEach((t) => t.addEventListener('click', () => setTab(t.getAttribute('data-tab'))));
    el('safBtnRefresh')?.addEventListener('click', () => { loadReports(); if (state.tab === 'training') loadCerts(); });
    el('safBtnNew').addEventListener('click', () => { state.tab === 'training' ? openCertCreate() : openReportCreate(); });

    el('rModalClose').addEventListener('click', () => el('rModal').close());
    el('rCancel').addEventListener('click', () => el('rModal').close());
    el('rSave').addEventListener('click', saveReport);
    el('rDelete').addEventListener('click', delReport);
    el('rBrowseBtn').addEventListener('click', () => el('rBrowseInput').click());
    el('rBrowseInput').addEventListener('change', (e) => { for (const f of e.target.files) { state.rPhotos.push({ id: Date.now() + Math.random(), blob: f, url: URL.createObjectURL(f), name: `Safety photo ${state.rPhotos.length + 1}` }); } e.target.value = ''; renderRPhotos(); });
    ['rSearch', 'rTypeFilter', 'rStatusFilter'].forEach((id) => { el(id).addEventListener('input', renderReports); el(id).addEventListener('change', renderReports); });

    el('cModalClose').addEventListener('click', () => el('cModal').close());
    el('cCancel').addEventListener('click', () => el('cModal').close());
    el('cSave').addEventListener('click', saveCert);
    el('cDelete').addEventListener('click', delCert);
    ['cSearch', 'cTypeFilter', 'cStatusFilter'].forEach((id) => { el(id).addEventListener('input', renderCerts); el(id).addEventListener('change', renderCerts); });

    el('safImportAll').addEventListener('click', () => saveToDocuments(null));

    global.addEventListener('casepm:project-changed', () => { loadReports(); state.certs = []; state.library = []; });
    global.onCasePmProjectChanged = (pid) => { ctx.projectId = pid; loadReports(); state.certs = []; state.library = []; };
  }
  function init() { bind(); loadReports(); }
  global.CasePMSafety = { refresh: loadReports };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
