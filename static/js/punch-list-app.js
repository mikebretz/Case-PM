/**
 * Case PM Punch List — fast field check-offs, photos, assignees, status verification.
 * Tap the circle to complete/reopen; quick-add bar; list + board views; grouping;
 * in-app camera (photos go straight to Documents); comments and checklist sub-tasks.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_PUNCH_CTX || {};
  const state = {
    items: [], stats: {}, categories: [], statuses: [], priorities: [],
    editingId: null, view: 'list',
    pendingPhotos: [], existingPhotos: [], armedPhoto: null, stream: null, facingMode: 'environment', photoSeq: 0,
    detailId: null,
  };

  const NEXT_STATUS = { 'Open': 'Closed', 'In Progress': 'Closed', 'Ready for Review': 'Closed', 'Closed': 'Open' };

  function projectId() { return ctx.projectId || (function () { try { return parseInt(localStorage.getItem('casepm_current_project_id'), 10) || null; } catch (_) { return null; } })(); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(id) { return document.getElementById(id); }
  function fmtDate(iso) { if (!iso) return ''; try { return new Date(iso + (iso.length <= 10 ? 'T00:00:00' : '')).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); } catch (_) { return iso; } }

  async function api(url, opts) {
    const res = await fetch(url, opts);
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  // ---------- Load ----------
  async function load() {
    const pid = projectId();
    el('punchStatusText').textContent = 'Loading…';
    try {
      const json = await api(`/api/punch-items${pid ? `?project_id=${pid}` : ''}`);
      state.items = json.items || [];
      state.stats = json.stats || {};
      state.categories = json.categories || [];
      state.statuses = json.statuses || [];
      state.priorities = json.priorities || [];
      fillFilters();
      renderStats();
      render();
      el('punchStatusText').textContent = `${state.items.length} item(s) · ${state.stats.percent_complete || 0}% complete`;
      el('punchUpdatedAt').textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (e) { el('punchStatusText').textContent = 'Error: ' + e.message; }
  }

  function fillFilters() {
    const sf = el('punchStatusFilter');
    if (sf.options.length <= 1) state.statuses.forEach((s) => sf.add(new Option(s, s)));
    const pf = el('punchPriorityFilter');
    if (pf.options.length <= 1) state.priorities.forEach((p) => pf.add(new Option(p, p)));
    const badge = el('punchProjectBadge'); if (badge) badge.textContent = ctx.projectName || 'All projects';
    // company datalist from assignees seen
    const dl = el('punchCompanyList');
    const set = new Set();
    state.items.forEach((i) => { if (i.assigned_company) set.add(i.assigned_company); });
    dl.innerHTML = [...set].map((c) => `<option value="${esc(c)}">`).join('');
  }

  function renderStats() {
    const s = state.stats;
    el('pstatOpen').textContent = s.open ?? 0;
    el('pstatProgress').textContent = s.in_progress ?? 0;
    el('pstatReady').textContent = s.ready ?? 0;
    el('pstatClosed').textContent = s.closed ?? 0;
    el('pstatOverdue').textContent = s.overdue ?? 0;
    el('pstatPct').textContent = (s.percent_complete ?? 0) + '%';
  }

  function filtered() {
    const term = (el('punchSearch').value || '').toLowerCase();
    const sf = el('punchStatusFilter').value;
    const pf = el('punchPriorityFilter').value;
    const hideClosed = el('punchHideClosed').checked;
    return state.items.filter((i) => {
      if (sf && i.status !== sf) return false;
      if (pf && i.priority !== pf) return false;
      if (hideClosed && i.status === 'Closed') return false;
      if (term) { const hay = `${i.number} ${i.description} ${i.location || ''} ${i.assigned_to || ''} ${i.trade || ''}`.toLowerCase(); if (!hay.includes(term)) return false; }
      return true;
    });
  }

  function statusChip(s) {
    const map = { 'Open': 'bg-amber-500/15 text-amber-400', 'In Progress': 'bg-sky-500/15 text-sky-400', 'Ready for Review': 'bg-violet-500/15 text-violet-400', 'Closed': 'bg-emerald-500/15 text-emerald-400' };
    return `<span class="punch-chip ${map[s] || 'bg-zinc-700 text-zinc-300'}">${esc(s)}</span>`;
  }

  // ---------- List view ----------
  function rowHtml(i) {
    const done = i.status === 'Closed';
    const meta = [];
    if (i.number) meta.push(`<span class="font-mono">${esc(i.number)}</span>`);
    if (i.location) meta.push(`<span><i class="fa-solid fa-location-dot"></i> ${esc(i.location)}</span>`);
    if (i.trade) meta.push(`<span><i class="fa-solid fa-helmet-safety"></i> ${esc(i.trade)}</span>`);
    if (i.assigned_to) meta.push(`<span><i class="fa-solid fa-user"></i> ${esc(i.assigned_to)}</span>`);
    if (i.due_date) meta.push(`<span class="${i.is_overdue ? 'punch-overdue' : ''}"><i class="fa-solid fa-calendar"></i> ${fmtDate(i.due_date)}${i.is_overdue ? ' (overdue)' : ''}</span>`);
    if (i.photo_count) meta.push(`<span><i class="fa-solid fa-image"></i> ${i.photo_count}</span>`);
    if (i.subtask_total) meta.push(`<span><i class="fa-solid fa-list-check"></i> ${i.subtask_done}/${i.subtask_total}</span>`);
    if (i.comment_count) meta.push(`<span><i class="fa-solid fa-comment"></i> ${i.comment_count}</span>`);
    return `<div class="punch-row ${done ? 'done' : ''}" data-id="${i.id}">
      <div class="punch-pri ${esc(i.priority || 'Medium')}"></div>
      <div class="punch-check ${done ? 'checked' : ''}" data-check="${i.id}" title="Tap to ${done ? 'reopen' : 'mark complete'}"><i class="fa-solid fa-check"></i></div>
      <div class="min-w-0 flex-1" data-open="${i.id}">
        <div class="punch-desc text-sm truncate">${esc(i.description)}</div>
        <div class="punch-meta">${meta.join('')}</div>
      </div>
      <div class="flex items-center gap-2 shrink-0">${statusChip(i.status)}</div>
    </div>`;
  }

  function render() {
    if (state.view === 'board') { renderBoard(); return; }
    el('punchListHost').classList.remove('hidden');
    el('punchBoardHost').classList.add('hidden');
    const host = el('punchListHost');
    const rows = filtered();
    if (!rows.length) {
      host.innerHTML = `<div class="px-6 py-12 text-center text-zinc-500"><i class="fa-solid fa-clipboard-check text-4xl mb-3 block text-zinc-600"></i>No punch items. Use Quick Add above or New Item.</div>`;
      return;
    }
    const groupBy = el('punchGroupBy').value;
    if (!groupBy) {
      host.innerHTML = rows.map(rowHtml).join('');
    } else {
      const groups = {};
      rows.forEach((i) => { const k = i[groupBy] || '(none)'; (groups[k] = groups[k] || []).push(i); });
      host.innerHTML = Object.keys(groups).sort().map((k) => `
        <div class="px-4 py-2 bg-zinc-800 text-xs font-semibold text-zinc-300 sticky top-0">${esc(k)} <span class="text-zinc-500">(${groups[k].length})</span></div>
        ${groups[k].map(rowHtml).join('')}`).join('');
    }
    bindRows(host);
  }

  function bindRows(host) {
    host.querySelectorAll('[data-check]').forEach((n) => n.addEventListener('click', (e) => { e.stopPropagation(); toggleCheck(parseInt(n.getAttribute('data-check'), 10)); }));
    host.querySelectorAll('[data-open]').forEach((n) => n.addEventListener('click', () => openDetail(parseInt(n.getAttribute('data-open'), 10))));
    host.querySelectorAll('[data-card]').forEach((n) => n.addEventListener('click', () => openDetail(parseInt(n.getAttribute('data-card'), 10))));
  }

  function renderBoard() {
    el('punchListHost').classList.add('hidden');
    el('punchBoardHost').classList.remove('hidden');
    const host = el('punchBoardHost');
    const rows = filtered();
    const cols = state.statuses.length ? state.statuses : ['Open', 'In Progress', 'Ready for Review', 'Closed'];
    const colColors = { 'Open': 'text-amber-400', 'In Progress': 'text-sky-400', 'Ready for Review': 'text-violet-400', 'Closed': 'text-emerald-400' };
    host.innerHTML = `<div class="punch-board">${cols.map((c) => {
      const items = rows.filter((i) => i.status === c);
      return `<div class="punch-col">
        <div class="punch-col-head ${colColors[c] || ''}">${esc(c)} <span class="text-zinc-500">(${items.length})</span></div>
        <div class="punch-col-body">${items.map((i) => `
          <div class="punch-card" data-card="${i.id}">
            <div class="flex items-start gap-2">
              <div class="punch-pri ${esc(i.priority || 'Medium')}" style="width:4px;min-height:32px;border-radius:2px;"></div>
              <div class="min-w-0 flex-1">
                <div class="text-sm ${i.status === 'Closed' ? 'line-through text-zinc-500' : ''}">${esc(i.description)}</div>
                <div class="punch-meta mt-1">
                  ${i.location ? `<span><i class="fa-solid fa-location-dot"></i> ${esc(i.location)}</span>` : ''}
                  ${i.assigned_to ? `<span><i class="fa-solid fa-user"></i> ${esc(i.assigned_to)}</span>` : ''}
                  ${i.due_date ? `<span class="${i.is_overdue ? 'punch-overdue' : ''}"><i class="fa-solid fa-calendar"></i> ${fmtDate(i.due_date)}</span>` : ''}
                  ${i.photo_count ? `<span><i class="fa-solid fa-image"></i> ${i.photo_count}</span>` : ''}
                </div>
              </div>
            </div>
          </div>`).join('') || '<div class="text-xs text-zinc-600 text-center py-4">None</div>'}
        </div>
      </div>`;
    }).join('')}</div>`;
    bindRows(host);
  }

  async function toggleCheck(id) {
    const item = state.items.find((i) => i.id === id);
    if (!item) return;
    const next = NEXT_STATUS[item.status] || 'Closed';
    try {
      await api(`/api/punch-items/${id}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: next }) });
      await load();
    } catch (e) { alert(e.message); }
  }

  // ---------- Quick add ----------
  async function quickAdd() {
    const input = el('punchQuickAdd');
    const text = input.value.trim();
    if (!text) return;
    const pid = projectId();
    if (!pid) { alert('Select a project first.'); return; }
    try {
      await api('/api/punch-items', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_id: pid, description: text, status: 'Open' }) });
      input.value = '';
      await load();
    } catch (e) { alert(e.message); }
  }

  // ---------- Photos (in-app camera → Documents) ----------
  function autoName() { state.photoSeq += 1; return `Punch photo ${state.photoSeq} · ${new Date().toISOString().slice(0, 10)}`; }
  function readFile(f) { return new Promise((r) => { const rd = new FileReader(); rd.onload = (e) => r(e.target.result); rd.readAsDataURL(f); }); }

  async function openCamera() {
    el('punchCamError').classList.add('hidden');
    el('punchCameraModal').showModal();
    await startStream();
    renderCamThumbs();
  }
  async function startStream() {
    stopStream();
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: state.facingMode }, audio: false });
      const v = el('punchVideo'); v.srcObject = state.stream; v.classList.remove('hidden');
    } catch (e) {
      el('punchVideo').classList.add('hidden');
      const err = el('punchCamError');
      err.innerHTML = !window.isSecureContext ? 'Camera needs HTTPS. Use Browse instead.' : 'Camera unavailable — use Browse.';
      err.classList.remove('hidden');
    }
  }
  function stopStream() { if (state.stream) { state.stream.getTracks().forEach((t) => t.stop()); state.stream = null; } }
  function capture() {
    const v = el('punchVideo'); if (!v || !v.videoWidth) return;
    const c = el('punchSnapCanvas'); c.width = v.videoWidth; c.height = v.videoHeight; c.getContext('2d').drawImage(v, 0, 0);
    c.toBlob((blob) => {
      if (!blob) return;
      state.pendingPhotos.push({ id: Date.now() + Math.random(), blob, url: URL.createObjectURL(blob), name: autoName() });
      renderCamThumbs(); renderPhotoGrid();
    }, 'image/jpeg', 0.9);
  }
  function renderCamThumbs() {
    el('punchCamThumbs').innerHTML = state.pendingPhotos.slice(-8).map((p) => `<div class="rounded overflow-hidden border border-zinc-700"><img src="${p.url}" style="width:100%;height:64px;object-fit:cover;"></div>`).join('');
  }
  function closeCamera() { stopStream(); el('punchCameraModal').close(); renderPhotoGrid(); }
  function renderPhotoGrid() {
    const grid = el('punchPhotoGrid');
    let html = '';
    state.pendingPhotos.forEach((p) => { html += `<div class="relative rounded overflow-hidden border border-zinc-700"><img src="${p.url}" style="width:100%;height:72px;object-fit:cover;"><button data-delp="${p.id}" class="absolute top-1 right-1 bg-black/70 text-white w-5 h-5 rounded-full text-xs">×</button></div>`; });
    state.existingPhotos.forEach((p) => { html += `<div class="rounded overflow-hidden border border-zinc-700"><img src="${esc(p.url || '')}" style="width:100%;height:72px;object-fit:cover;"></div>`; });
    grid.innerHTML = html || '<div class="text-xs text-zinc-500 col-span-full py-2 text-center">No photos yet.</div>';
    el('punchPhotoCount').textContent = (state.pendingPhotos.length + state.existingPhotos.length) ? `(${state.pendingPhotos.length + state.existingPhotos.length})` : '';
    grid.querySelectorAll('[data-delp]').forEach((n) => n.addEventListener('click', () => { const id = n.getAttribute('data-delp'); state.pendingPhotos = state.pendingPhotos.filter((p) => String(p.id) !== id); renderPhotoGrid(); }));
  }

  // ---------- Subtasks ----------
  function addSubtaskRow(data) {
    const wrap = el('punchSubtasks');
    const row = document.createElement('div');
    row.className = 'flex items-center gap-2';
    row.setAttribute('data-subtask', '');
    row.innerHTML = `<input type="checkbox" class="accent-emerald-500 st-done" ${data && data.done ? 'checked' : ''}>
      <input type="text" class="punch-input st-text" placeholder="Checklist step" value="${esc((data && data.text) || '')}">
      <button type="button" class="text-red-400 px-2 st-del"><i class="fa-solid fa-trash text-xs"></i></button>`;
    row.querySelector('.st-del').addEventListener('click', () => row.remove());
    wrap.appendChild(row);
  }
  function collectSubtasks() {
    return [...el('punchSubtasks').querySelectorAll('[data-subtask]')].map((r) => ({
      text: r.querySelector('.st-text').value.trim(), done: r.querySelector('.st-done').checked,
    })).filter((s) => s.text);
  }

  // ---------- Modal ----------
  function fillSelect(sel, options, val) { sel.innerHTML = options.map((o) => `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join(''); }

  function resetModal() {
    state.editingId = null; state.pendingPhotos = []; state.existingPhotos = []; state.photoSeq = 0;
    el('punchModalTitle').textContent = 'New Punch Item';
    ['punchDesc', 'punchLocation', 'punchTrade', 'punchAssignee', 'punchCompany', 'punchDue'].forEach((id) => { el(id).value = ''; });
    fillSelect(el('punchCategory'), ['', ...state.categories], '');
    fillSelect(el('punchPriority'), state.priorities, 'Medium');
    fillSelect(el('punchStatus'), state.statuses, 'Open');
    el('punchSubtasks').innerHTML = '';
    el('punchDelete').classList.add('hidden');
    renderPhotoGrid();
  }

  function openCreate(prefill) {
    resetModal();
    if (prefill) el('punchDesc').value = prefill;
    el('punchModal').showModal();
  }

  async function openEdit(id) {
    resetModal();
    try {
      const json = await api(`/api/punch-items/${id}`);
      const it = json.item;
      state.editingId = id;
      el('punchModalTitle').textContent = `${it.number || 'Punch Item'}`;
      el('punchDesc').value = it.description || '';
      el('punchLocation').value = it.location || '';
      el('punchTrade').value = it.trade || '';
      el('punchAssignee').value = it.assigned_to || '';
      el('punchCompany').value = it.assigned_company || '';
      el('punchDue').value = it.due_date || '';
      fillSelect(el('punchCategory'), ['', ...state.categories], it.category || '');
      fillSelect(el('punchPriority'), state.priorities, it.priority || 'Medium');
      fillSelect(el('punchStatus'), state.statuses, it.status || 'Open');
      (it.subtasks || []).forEach(addSubtaskRow);
      state.existingPhotos = it.photos || [];
      renderPhotoGrid();
      el('punchDelete').classList.remove('hidden');
      el('punchDetailModal').close();
      el('punchModal').showModal();
    } catch (e) { alert(e.message); }
  }

  async function save() {
    const pid = projectId();
    const desc = el('punchDesc').value.trim();
    if (!pid || !desc) { alert('Description is required.'); return; }
    const payload = {
      project_id: pid,
      description: desc,
      location: el('punchLocation').value.trim(),
      trade: el('punchTrade').value.trim(),
      category: el('punchCategory').value,
      priority: el('punchPriority').value,
      status: el('punchStatus').value,
      assigned_to: el('punchAssignee').value.trim(),
      assigned_company: el('punchCompany').value.trim(),
      due_date: el('punchDue').value,
      subtasks: collectSubtasks(),
    };
    const btn = el('punchSave'); btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const url = state.editingId ? `/api/punch-items/${state.editingId}` : '/api/punch-items';
      const method = state.editingId ? 'PUT' : 'POST';
      const json = await api(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const itemId = json.item.id;
      for (const photo of state.pendingPhotos) {
        const fd = new FormData();
        fd.append('file', photo.blob, `${photo.name}.jpg`);
        fd.append('name', photo.name); fd.append('kind', 'photo');
        await fetch(`/api/punch-items/${itemId}/attachments`, { method: 'POST', body: fd });
      }
      state.pendingPhotos.forEach((p) => { try { URL.revokeObjectURL(p.url); } catch (_) {} });
      state.pendingPhotos = [];
      el('punchModal').close();
      await load();
      if (global.showToast) global.showToast('Punch item saved');
    } catch (e) { alert(e.message); }
    finally { btn.disabled = false; btn.textContent = 'Save Item'; }
  }

  async function del() {
    if (!state.editingId || !confirm('Delete this punch item?')) return;
    try { await api(`/api/punch-items/${state.editingId}`, { method: 'DELETE' }); el('punchModal').close(); await load(); }
    catch (e) { alert(e.message); }
  }

  // ---------- Detail ----------
  async function openDetail(id) {
    try {
      const json = await api(`/api/punch-items/${id}`);
      const it = json.item; state.detailId = id;
      el('punchDetailTitle').textContent = `${it.number || 'Punch Item'}`;
      const photos = (it.photos || []).map((p) => `<a href="${esc(p.url || '#')}" target="_blank" class="rounded overflow-hidden border border-zinc-700 block"><img src="${esc(p.url || '')}" style="width:100%;height:90px;object-fit:cover;"></a>`).join('');
      const subs = (it.subtasks || []).map((s) => `<div class="text-sm"><i class="fa-solid ${s.done ? 'fa-square-check text-emerald-400' : 'fa-square text-zinc-500'} mr-2"></i>${esc(s.text)}</div>`).join('');
      const comments = (it.comments || []).map((c) => `<div class="text-sm bg-zinc-950 border border-zinc-800 rounded-md p-2"><div>${esc(c.text)}</div><div class="text-[10px] text-zinc-500 mt-1">${esc(c.author || '')} · ${fmtDate((c.at || '').slice(0,10))}</div></div>`).join('');
      el('punchDetailBody').innerHTML = `
        <div class="flex flex-wrap gap-3 items-center">
          ${statusChip(it.status)}
          <span class="punch-chip bg-zinc-800 text-zinc-300">${esc(it.priority)} priority</span>
          ${it.is_overdue ? '<span class="punch-chip bg-red-500/15 text-red-400">Overdue</span>' : ''}
        </div>
        <div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Description</div><div class="whitespace-pre-wrap">${esc(it.description)}</div></div>
        <div class="grid grid-cols-2 gap-3 text-sm">
          ${it.location ? `<div><span class="text-zinc-500">Location:</span> ${esc(it.location)}</div>` : ''}
          ${it.trade ? `<div><span class="text-zinc-500">Trade:</span> ${esc(it.trade)}</div>` : ''}
          ${it.category ? `<div><span class="text-zinc-500">Category:</span> ${esc(it.category)}</div>` : ''}
          ${it.assigned_to ? `<div><span class="text-zinc-500">Assignee:</span> ${esc(it.assigned_to)}</div>` : ''}
          ${it.assigned_company ? `<div><span class="text-zinc-500">Company:</span> ${esc(it.assigned_company)}</div>` : ''}
          ${it.due_date ? `<div><span class="text-zinc-500">Due:</span> <span class="${it.is_overdue ? 'punch-overdue' : ''}">${fmtDate(it.due_date)}</span></div>` : ''}
        </div>
        ${subs ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Checklist (${it.subtask_done}/${it.subtask_total})</div>${subs}</div>` : ''}
        ${photos ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Photos</div><div class="grid grid-cols-3 md:grid-cols-4 gap-2">${photos}</div></div>` : ''}
        ${comments ? `<div><div class="text-xs uppercase tracking-wide text-zinc-500 mb-1">Comments</div><div class="space-y-2">${comments}</div></div>` : ''}`;
      el('punchDetailEdit').onclick = () => openEdit(id);
      el('punchDetailModal').showModal();
    } catch (e) { alert(e.message); }
  }

  async function postComment() {
    const input = el('punchCommentInput');
    const text = input.value.trim();
    if (!text || !state.detailId) return;
    try { await api(`/api/punch-items/${state.detailId}/comment`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) }); input.value = ''; openDetail(state.detailId); load(); }
    catch (e) { alert(e.message); }
  }

  function setView(v) {
    state.view = v;
    el('punchViewList').className = 'px-3 py-2 text-sm ' + (v === 'list' ? 'bg-zinc-700' : 'bg-zinc-800');
    el('punchViewBoard').className = 'px-3 py-2 text-sm ' + (v === 'board' ? 'bg-zinc-700' : 'bg-zinc-800');
    render();
  }

  function bind() {
    el('punchBtnNew').addEventListener('click', () => openCreate());
    el('punchBtnRefresh')?.addEventListener('click', load);
    el('punchViewList').addEventListener('click', () => setView('list'));
    el('punchViewBoard').addEventListener('click', () => setView('board'));
    el('punchQuickAddBtn').addEventListener('click', quickAdd);
    el('punchQuickAdd').addEventListener('keydown', (e) => { if (e.key === 'Enter') quickAdd(); });
    ['punchSearch', 'punchStatusFilter', 'punchPriorityFilter', 'punchGroupBy', 'punchHideClosed'].forEach((id) => { el(id).addEventListener('input', render); el(id).addEventListener('change', render); });

    el('punchModalClose').addEventListener('click', () => el('punchModal').close());
    el('punchCancel').addEventListener('click', () => el('punchModal').close());
    el('punchSave').addEventListener('click', save);
    el('punchDelete').addEventListener('click', del);
    el('punchAddSubtask').addEventListener('click', () => addSubtaskRow());
    el('punchOpenCamera').addEventListener('click', openCamera);
    el('punchBrowseBtn').addEventListener('click', () => el('punchBrowseInput').click());
    el('punchBrowseInput').addEventListener('change', async (e) => {
      for (const f of e.target.files) { const url = URL.createObjectURL(f); state.pendingPhotos.push({ id: Date.now() + Math.random(), blob: f, url, name: autoName() }); }
      e.target.value = ''; renderPhotoGrid();
    });
    el('punchCamShoot').addEventListener('click', capture);
    el('punchCamClose').addEventListener('click', closeCamera);
    el('punchCamDone').addEventListener('click', closeCamera);
    el('punchCamSwitch').addEventListener('click', () => { state.facingMode = state.facingMode === 'environment' ? 'user' : 'environment'; startStream(); });

    el('punchDetailClose').addEventListener('click', () => el('punchDetailModal').close());
    el('punchCommentBtn').addEventListener('click', postComment);
    el('punchCommentInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') postComment(); });

    global.addEventListener('casepm:project-changed', load);
    global.onCasePmProjectChanged = (pid) => { ctx.projectId = pid; load(); };
  }

  function init() { bind(); load(); }
  global.CasePMPunch = { refresh: load, openCreate };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
