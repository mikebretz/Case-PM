(function () {
  'use strict';

  const ctx = window.CASEPM_ESTIMATE_CTX || {};

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  async function loadSummary() {
    const host = document.getElementById('estPlanRoomBridge');
    if (!host || !ctx.projectId) {
      if (host) host.innerHTML = '';
      return;
    }
    try {
      const res = await fetch(`/api/bidder-network/admin/projects/${ctx.projectId}/estimating-summary`, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed');
      const pub = data.plan_room_published;
      const pkg = `${data.packages_published || 0}/${data.package_count || 0}`;
      host.innerHTML = `
        <div class="est-planroom-bridge">
          <div>
            <div class="est-planroom-bridge-title">Plan room &amp; bidding</div>
            <div class="est-planroom-bridge-meta">
              Project ${pub ? '<span class="text-emerald-400">published</span>' : '<span class="text-amber-400">not published</span>'}
              · ${esc(pkg)} packages on plan room
              · ${data.packages_with_documents || 0} with documents
              ${data.pending_bidder_registrations ? ` · <strong>${data.pending_bidder_registrations}</strong> pending bidder(s)` : ''}
              ${data.bid_date ? ` · Bid ${esc(String(data.bid_date).slice(0, 10))}` : ''}
            </div>
          </div>
          <div class="est-planroom-bridge-actions">
            <a href="/plan-room/console" class="px-3 py-1.5 bg-indigo-900 hover:bg-indigo-800 rounded text-xs text-white no-underline">Plan room console</a>
            <a href="/plan-room/console?tab=packages" class="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-xs text-white no-underline">Edit packages</a>
            <a href="/plan-room/projects" target="_blank" rel="noopener" class="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded text-xs text-white no-underline">Preview as bidder</a>
            <button type="button" id="estGoRfpTab" class="px-3 py-1.5 bg-emerald-900 hover:bg-emerald-800 rounded text-xs text-white">Bid packages / RFP</button>
          </div>
        </div>
      `;
      document.getElementById('estGoRfpTab')?.addEventListener('click', () => {
        document.querySelector('.est-tabs button[data-tab="rfp"]')?.click();
        document.getElementById('estPlanRoomPanel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    } catch (_) {
      host.innerHTML = '';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadSummary);
  } else {
    loadSummary();
  }
  window.refreshEstimatingPlanRoomBridge = loadSummary;
})();
