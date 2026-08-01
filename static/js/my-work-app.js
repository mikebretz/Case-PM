/**
 * My Work — unified cross-module action queue.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_MY_WORK_CTX || {};
  let scope = 'all';

  const KIND_ICON = {
    rfi: 'fa-question-circle text-yellow-400',
    submittal: 'fa-file-upload text-sky-400',
    change_order: 'fa-exchange-alt text-orange-400',
    pco: 'fa-lightbulb text-sky-300',
    pay_application: 'fa-file-invoice-dollar text-emerald-400',
    approval: 'fa-circle-check text-amber-400',
    message: 'fa-envelope text-violet-400',
  };

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function load() {
    const host = document.getElementById('mwList');
    const countsEl = document.getElementById('mwCounts');
    if (!host) return;
    host.innerHTML = '<div class="p-8 text-center text-zinc-500">Loading…</div>';
    const q = new URLSearchParams();
    if (scope === 'project' && ctx.projectId) q.set('project_id', String(ctx.projectId));
    q.set('limit', '80');
    try {
      const res = await fetch(`/api/my-work?${q}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load');
      const items = data.items || [];
      if (countsEl) {
        const c = data.counts || {};
        const parts = Object.keys(c).map((k) => `${k.replace(/_/g, ' ')}: ${c[k]}`);
        countsEl.textContent = items.length
          ? `${items.length} item(s)${parts.length ? ' · ' + parts.join(' · ') : ''}`
          : 'No open items assigned to you.';
      }
      if (!items.length) {
        host.innerHTML = '<div class="p-10 text-center text-zinc-500"><i class="fa-solid fa-circle-check text-emerald-500 text-2xl mb-2 block"></i>You\'re caught up.</div>';
        return;
      }
      host.innerHTML = items.map((it) => {
        const icon = KIND_ICON[it.kind] || 'fa-circle text-zinc-400';
        return `<a href="${esc(it.action_url || '#')}" class="mw-row block no-underline text-inherit">
          <i class="fa-solid ${icon} mt-1 shrink-0"></i>
          <div class="flex-1 min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="mw-kind">${esc(it.kind || '')}</span>
              ${it.overdue ? '<span class="mw-overdue">OVERDUE</span>' : ''}
              ${it.project_name ? `<span class="text-[10px] text-zinc-500 truncate">${esc(it.project_name)}</span>` : ''}
            </div>
            <div class="font-medium text-white truncate">${esc(it.title)}</div>
            <div class="text-xs text-zinc-500 truncate">${esc(it.subtitle || '')}</div>
          </div>
          <i class="fa-solid fa-chevron-right text-zinc-600 text-xs mt-2"></i>
        </a>`;
      }).join('');
    } catch (err) {
      host.innerHTML = `<div class="p-8 text-center text-red-400">${esc(err.message)}</div>`;
    }
  }

  document.querySelectorAll('.mw-chip[data-scope]').forEach((btn) => {
    btn.addEventListener('click', () => {
      scope = btn.dataset.scope || 'all';
      document.querySelectorAll('.mw-chip[data-scope]').forEach((b) => b.classList.toggle('active', b === btn));
      load();
    });
  });

  load();
  global.CasePMMyWork = { reload: load };
})(window);
