(function () {
  'use strict';

  const ctx = window.CASEPM_PLAN_ROOM_CTX || {};

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function api(path, opts) {
    const res = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', ...(opts?.headers || {}) },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  async function loadQa() {
    const host = document.getElementById('prcQaList');
    if (!host || !ctx.projectId) return;
    host.innerHTML = '<p class="text-zinc-500 text-sm">Loading…</p>';
    try {
      const data = await api(`/api/bidder-network/projects/${ctx.projectId}/clarifications`);
      const rows = data.clarifications || [];
      if (!rows.length) {
        host.innerHTML = '<p class="text-zinc-500 text-sm">No questions yet.</p>';
        return;
      }
      host.innerHTML = rows.map((q) => `
        <div class="border border-zinc-700 rounded-md p-3" data-qid="${q.id}">
          <div class="text-white text-sm font-medium">${esc(q.subject || 'Question')}</div>
          <div class="text-xs text-zinc-400">${esc(q.asker_company)} · ${esc(q.asker_name)} · ${esc((q.created_at || '').slice(0, 10))}</div>
          <p class="text-sm text-zinc-300 mt-2">${esc(q.question_text)}</p>
          ${q.answer_text ? `<div class="mt-2 p-2 bg-zinc-900 rounded text-sm text-emerald-100"><strong>Answer:</strong> ${esc(q.answer_text)}</div>` : `
            <textarea class="w-full mt-2 bg-zinc-900 border border-zinc-700 rounded p-2 text-sm" rows="3" placeholder="Public answer to all bidders…"></textarea>
            <button type="button" class="prc-btn prc-btn-primary text-xs mt-2 prc-qa-answer">Post answer</button>
          `}
        </div>
      `).join('');
      host.querySelectorAll('.prc-qa-answer').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const card = btn.closest('[data-qid]');
          const qid = card?.dataset.qid;
          const text = card?.querySelector('textarea')?.value?.trim();
          if (!text) return;
          await api(`/api/bidder-network/clarifications/${qid}/answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answer_text: text }),
          });
          loadQa();
        });
      });
    } catch (e) {
      host.innerHTML = `<p class="text-red-400 text-sm">${esc(e.message)}</p>`;
    }
  }

  async function loadSyncLog() {
    const host = document.getElementById('prcSyncLog');
    if (!host || !ctx.projectId) return;
    try {
      const data = await api(`/api/bidder-network/admin/projects/${ctx.projectId}/external-sync/logs`);
      const rows = data.logs || [];
      host.innerHTML = rows.length
        ? rows.map((l) => `<div>${esc(l.created_at)} · ${esc(l.provider)} · ${esc(l.status)}</div>`).join('')
        : 'No exports yet.';
    } catch (_) {
      host.textContent = 'Could not load log.';
    }
  }

  async function broadcast(mode) {
    const msg = document.getElementById('prcBroadcastMsg');
    if (!ctx.projectId) return;
    if (!confirm('Send ITB notification to all approved plan room bidders?')) return;
    try {
      const out = await api(`/api/bidder-network/admin/projects/${ctx.projectId}/broadcast-itb`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notify_mode: mode }),
      });
      if (msg) msg.textContent = `Sent to ${out.emails_sent || 0} of ${out.recipients || 0} approved bidders.`;
    } catch (e) {
      if (msg) msg.textContent = '';
      alert(e.message);
    }
  }

  document.getElementById('prcBroadcastItb')?.addEventListener('click', () => broadcast('both'));
  document.getElementById('prcBroadcastItbEmail')?.addEventListener('click', () => broadcast('email'));

  document.querySelectorAll('.prc-export-bc').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!ctx.projectId) return;
      const provider = btn.dataset.provider || 'buildingconnected';
      try {
        const out = await api(`/api/bidder-network/admin/projects/${ctx.projectId}/external-sync`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider }),
        });
        const pre = document.getElementById('prcExportOutput');
        if (pre) {
          pre.classList.remove('hidden');
          pre.textContent = JSON.stringify(out.export, null, 2);
        }
        loadSyncLog();
      } catch (e) {
        alert(e.message);
      }
    });
  });

  window.planRoomConsoleAdvanced = {
    onTab(name) {
      if (name === 'qa') loadQa();
      if (name === 'outreach') loadSyncLog();
    },
  };
})();
