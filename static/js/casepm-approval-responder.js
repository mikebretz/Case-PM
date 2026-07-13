/**
 * Case PM — unified approval responder modal (RFIs, Change Orders, etc.)
 */
(function (global) {
  'use strict';

  const MODULE_PATH = {
    rfi: 'rfi',
    rfis: 'rfi',
    co: 'co',
    change_order: 'co',
    change_orders: 'co',
    pay_applications: 'pay_applications',
    pay_app: 'pay_applications',
    g702: 'pay_applications',
  };

  let ctx = null;
  let signPanel = null;
  let pendingFiles = [];

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString();
  }

  function fmtMoney(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n || 0);
  }

  function modal() {
    return document.getElementById('casepmApprovalResponder');
  }

  async function api(path, options) {
    const res = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(options && options.headers) },
      ...options,
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || res.statusText || 'Request failed');
    return json;
  }

  function modulePath(module) {
    return MODULE_PATH[(module || '').toLowerCase()] || module;
  }

  function isStaffPortal() {
    const p = global.CASEPM_PORTAL;
    return !p || p.portal === 'staff' || p.role === 'Admin';
  }

  function destroySignPanel() {
    if (signPanel) {
      signPanel.destroy();
      signPanel = null;
    }
    const host = document.getElementById('aprSignPanel');
    if (host) {
      host.classList.add('hidden');
      host.innerHTML = '';
    }
  }

  function renderThread(thread, module) {
    const items = thread || [];
    if (!items.length) {
      return '<p class="text-sm text-zinc-500">No comments yet.</p>';
    }
    if (module === 'Change Orders' || module === 'Pay Applications') {
      return items.map(entry => `
        <div class="border border-zinc-700 rounded-md p-3 text-sm">
          <div class="flex justify-between text-xs text-zinc-500 mb-1">
            <span>${esc(entry.user_name || entry.role || 'User')} · ${esc(entry.action || '')}</span>
            <span>${fmtDate(entry.at)}</span>
          </div>
          <div class="whitespace-pre-wrap">${esc(entry.comment || '')}</div>
        </div>`).join('');
    }
    return items.map(entry => `
      <div class="border rounded-md p-3 text-sm ${entry.is_official ? 'border-emerald-700 bg-emerald-950/20' : 'border-zinc-700'}">
        <div class="flex justify-between text-xs text-zinc-500 mb-1">
          <span>${esc(entry.author)} ${entry.is_official ? '<span class="text-emerald-400 ml-1">Official Answer</span>' : ''}</span>
          <span>${fmtDate(entry.created_at)}</span>
        </div>
        <div class="whitespace-pre-wrap">${esc(entry.body)}</div>
      </div>`).join('');
  }

  function renderAttachments(attachments, module, entityId) {
    const list = attachments || [];
    if (!list.length) return '<p class="text-xs text-zinc-500">No attachments</p>';
    return list.map(att => {
      let href = att.url || '#';
      if (!att.url && att.document_id) href = `/api/documents/${att.document_id}/download`;
      if (!att.url && att.filename && module === 'RFIs') href = `/uploads/rfis/${entityId}/${att.filename}`;
      if (!att.url && att.filename && module === 'Change Orders') href = `/uploads/change_orders/${entityId}/${att.filename}`;
      const name = esc(att.original_name || att.filename || 'File');
      return `<a href="${esc(href)}" target="_blank" rel="noopener" class="flex items-center gap-2 text-xs bg-zinc-800 rounded px-2 py-1.5 hover:bg-zinc-700 border border-zinc-700">
        <i class="fa-solid fa-paperclip text-zinc-400"></i><span class="truncate">${name}</span>
      </a>`;
    }).join('');
  }

  function renderSummary(data) {
    const s = data.summary || {};
    if (data.module === 'Pay Applications') {
      return `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Period</span><span class="font-mono">#${esc(s.period_number)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Dates</span><span class="text-xs">${esc(s.period_start || '')} — ${esc(s.period_end || '')}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Status</span><span>${esc(data.status)}</span></div>`;
    }
    if (data.module === 'Change Orders') {
      const alloc = (s.allocations || []).map(a =>
        `<div class="flex justify-between gap-3 text-xs"><span class="font-mono text-emerald-400">${esc(a.cost_code)}</span><span class="text-zinc-400">${esc(a.cost_type || '')}</span><span class="font-mono">${fmtMoney(a.amount)}</span></div>`
      ).join('') || '<div class="text-zinc-500 text-xs">No allocations</div>';
      return `
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Title</span><span class="text-right max-w-[65%]">${esc(s.title)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Amount</span><span class="font-mono text-emerald-400">${fmtMoney(s.amount)}</span></div>
        <div class="flex justify-between text-sm"><span class="text-zinc-500">Status</span><span>${esc(data.status)}</span></div>
        <div class="pt-2 border-t border-zinc-800 mt-2">
          <div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Schedule of Values</div>
          ${alloc}
        </div>`;
    }
    return `
      <div class="grid grid-cols-2 gap-3 text-sm">
        <div><span class="text-zinc-500 text-xs">Due</span><div class="${s.is_overdue ? 'text-red-400' : ''}">${fmtDate(s.due_date)}</div></div>
        <div><span class="text-zinc-500 text-xs">Drawing</span><div class="font-mono text-xs">${esc(s.drawing_reference || '—')}</div></div>
        <div><span class="text-zinc-500 text-xs">Spec</span><div class="font-mono text-xs">${esc(s.spec_reference || '—')}</div></div>
        <div><span class="text-zinc-500 text-xs">From</span><div class="text-xs">${esc(s.from_party || '—')}</div></div>
      </div>
      <div class="mt-3">
        <div class="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Question</div>
        <p class="text-sm whitespace-pre-wrap bg-zinc-950/60 rounded-md p-3 border border-zinc-800">${esc(s.question || '—')}</p>
      </div>
      ${s.official_answer ? `<div class="mt-3"><div class="text-[10px] uppercase tracking-wide text-emerald-500 mb-1">Official Answer</div><p class="text-sm whitespace-pre-wrap bg-emerald-950/20 rounded-md p-3 border border-emerald-800">${esc(s.official_answer)}</p></div>` : ''}`;
  }

  function renderActions(actions) {
    const host = document.getElementById('aprActions');
    if (!host) return;
    const list = actions || [];
    if (!list.length) {
      host.innerHTML = '<p class="text-sm text-zinc-500 w-full text-center py-2">No actions available for you on this item right now.</p>';
      return;
    }
    host.innerHTML = list.map(a => {
      const cls = a.style === 'primary'
        ? 'bg-emerald-600 hover:bg-emerald-500 text-white font-semibold'
        : a.style === 'danger'
          ? 'bg-red-950 hover:bg-red-900 border border-red-800 text-red-300'
          : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-200';
      return `<button type="button" data-apr-action="${esc(a.action)}" class="px-5 py-2.5 rounded-md text-sm ${cls}">${esc(a.label)}</button>`;
    }).join('');
    host.querySelectorAll('[data-apr-action]').forEach(btn => {
      btn.addEventListener('click', () => submit(btn.getAttribute('data-apr-action')));
    });
  }

  function renderPendingUploads() {
    const el = document.getElementById('aprPendingFiles');
    if (!el) return;
    if (!pendingFiles.length) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = pendingFiles.map((f, i) =>
      `<div class="flex items-center justify-between text-xs bg-zinc-800 rounded px-2 py-1"><span class="truncate">${esc(f.name)}</span><button type="button" data-rm="${i}" class="text-red-400 ml-2">&times;</button></div>`
    ).join('');
    el.querySelectorAll('[data-rm]').forEach(btn => {
      btn.addEventListener('click', () => {
        pendingFiles.splice(parseInt(btn.getAttribute('data-rm'), 10), 1);
        renderPendingUploads();
      });
    });
  }

  function bindUploadHandlers() {
    const drop = document.getElementById('aprDropZone');
    const input = document.getElementById('aprFileInput');
    const docsBtn = document.getElementById('aprBrowseDocs');
    if (!drop || !input) return;

    drop.onclick = e => {
      if (e.target.closest('#aprBrowseDocs')) return;
      input.click();
    };
    input.onchange = e => {
      pendingFiles.push(...Array.from(e.target.files || []));
      renderPendingUploads();
      input.value = '';
    };
    if (docsBtn) {
      docsBtn.classList.toggle('hidden', !(ctx && ctx.can_access_documents));
      docsBtn.onclick = e => {
        e.stopPropagation();
        if (typeof global.CasePMDocPicker !== 'undefined') {
          global.CasePMDocPicker.open({
            title: 'Attach from Documents',
            projectId: ctx.project_id,
            onPick: docs => {
              const list = Array.isArray(docs) ? docs : [];
              pendingFiles.push(...list.map(d => ({ docLink: true, document_id: d.id, name: d.name || d.filename })));
              renderPendingUploads();
            },
          });
        }
      };
    }
    ['dragenter', 'dragover'].forEach(evt => {
      drop.addEventListener(evt, e => { e.preventDefault(); drop.classList.add('border-emerald-500'); });
    });
    ['dragleave', 'drop'].forEach(evt => {
      drop.addEventListener(evt, e => {
        e.preventDefault();
        drop.classList.remove('border-emerald-500');
        if (evt === 'drop') {
          pendingFiles.push(...Array.from(e.dataTransfer?.files || []));
          renderPendingUploads();
        }
      });
    });
  }

  async function uploadPendingFiles(module, entityId) {
    if (!pendingFiles.length) return [];
    const uploaded = [];
    for (const item of pendingFiles) {
      if (item.docLink && item.document_id) {
        if (module === 'RFIs') {
          await api(`/api/rfis/${entityId}/attachments/link`, {
            method: 'POST',
            body: JSON.stringify({ document_id: item.document_id }),
          });
        }
        uploaded.push({ document_id: item.document_id, original_name: item.name });
        continue;
      }
      if (item instanceof File && module === 'RFIs') {
        const fd = new FormData();
        fd.append('file', item);
        const res = await fetch(`/api/rfis/${entityId}/attachments`, { method: 'POST', body: fd, credentials: 'same-origin' });
        const json = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(json.error || 'Upload failed');
        uploaded.push({ filename: item.name, original_name: item.name });
      }
    }
    pendingFiles = [];
    renderPendingUploads();
    return uploaded;
  }

  function setupEsign(data) {
    destroySignPanel();
    const host = document.getElementById('aprSignPanel');
    const needs = data.requires_esign && (data.allowed_actions || []).some(a => a.action === 'approve');
    if (!needs || !host || typeof global.CasePMEsign === 'undefined') return;
    host.classList.remove('hidden');
    signPanel = global.CasePMEsign.mountSignPanel(host, {
      title: `${data.ball_in_court_role} Approval — Electronic Signature`,
      requireSignature: true,
    });
  }

  function paint(data) {
    ctx = data;
    document.getElementById('aprTitle').textContent = data.title || 'Review Item';
    const subtitle = [
      data.status,
      data.ball_in_court_role ? `Waiting on: ${data.ball_in_court_role}` : null,
    ].filter(Boolean).join(' · ');
    document.getElementById('aprSubtitle').textContent = subtitle;
    document.getElementById('aprSummary').innerHTML = renderSummary(data);
    document.getElementById('aprThread').innerHTML = renderThread(data.thread, data.module);
    document.getElementById('aprAttachments').innerHTML = renderAttachments(data.attachments, data.module, data.entity_id);
    const comment = document.getElementById('aprComment');
    if (comment) comment.value = '';
    const uploadSection = document.getElementById('aprUploadSection');
    if (uploadSection) {
      uploadSection.classList.toggle('hidden', data.module === 'Change Orders');
    }
    renderActions(data.allowed_actions);
    setupEsign(data);
    bindUploadHandlers();
  }

  async function submit(action) {
    if (!ctx) return;
    const commentEl = document.getElementById('aprComment');
    const comment = commentEl?.value?.trim() || '';
    const actionMeta = (ctx.allowed_actions || []).find(a => a.action === action) || {};
    if (actionMeta.requires_comment && !comment) {
      alert('Please enter a comment before continuing.');
      commentEl?.focus();
      return;
    }
  const body = { action, comment };
    if (actionMeta.is_official) body.is_official = true;
    if (action === 'approve' && signPanel) {
      try {
        Object.assign(body, await signPanel.getPayload());
      } catch (err) {
        alert(err.message || 'Complete the electronic signature.');
        return;
      }
    }
    try {
      if (ctx.module === 'RFIs' && pendingFiles.length) {
        await uploadPendingFiles(ctx.module, ctx.entity_id);
      }
      const path = `/api/workflow/respond/${modulePath(ctx.module)}/${ctx.entity_id}`;
      const result = await api(path, { method: 'POST', body: JSON.stringify(body) });
      toast('Saved — everyone involved has been notified.');
      modal()?.close();
      destroySignPanel();
      global.dispatchEvent(new CustomEvent('casepm:approval-responded', { detail: result }));
      if (ctx.module === 'RFIs' && global.CasePMRfis) {
        if (typeof global.CasePMRfis.refresh === 'function') await global.CasePMRfis.refresh();
        else if (global.CasePMRfis.view) await global.CasePMRfis.view(ctx.entity_id).catch(() => {});
      }
      if (ctx.module === 'Change Orders' && global.CasePMChangeOrders) {
        if (global.CasePMChangeOrders.loadChangeOrders) await global.CasePMChangeOrders.loadChangeOrders?.();
        if (global.CasePMChangeOrders.viewCo) await global.CasePMChangeOrders.viewCo(ctx.entity_id).catch(() => {});
      }
      if (ctx.module === 'Pay Applications') {
        if (typeof global.CasePMPayAppSync !== 'undefined') await global.CasePMPayAppSync.refreshFromServer();
        if (typeof reloadPayAppStateFromStorage === 'function') reloadPayAppStateFromStorage();
        if (typeof renderPayAppContent === 'function') renderPayAppContent();
      }
    } catch (err) {
      alert(err.message || 'Could not complete action.');
    }
  }

  function toast(msg) {
    if (typeof global.showToast === 'function') global.showToast(msg);
    else console.log(msg);
  }

  async function open(module, entityId, options) {
    if (typeof global.CasePMWorkflow !== 'undefined') {
      await global.CasePMWorkflow.loadPortal().catch(() => {});
    }
    let path = `/api/workflow/respond/${modulePath(module)}/${entityId}`;
    const opts = options || {};
    if (opts.project_id) path += `?project_id=${encodeURIComponent(opts.project_id)}`;
    const data = await api(path);
    pendingFiles = [];
    paint(data);
    const dlg = modal();
    dlg?.showModal();
    document.getElementById('aprComment')?.focus();
    return data;
  }

  function close() {
    destroySignPanel();
    pendingFiles = [];
    ctx = null;
    modal()?.close();
  }

  function init() {
    document.getElementById('aprCloseBtn')?.addEventListener('click', close);
    document.getElementById('aprCancelBtn')?.addEventListener('click', close);
    modal()?.addEventListener('close', () => {
      destroySignPanel();
      ctx = null;
    });
  }

  global.CasePMApprovalResponder = {
    open,
    close,
    isStaffPortal,
    init,
  };

  document.addEventListener('DOMContentLoaded', init);
})(window);
