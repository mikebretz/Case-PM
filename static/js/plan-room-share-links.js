/**
 * Copyable public URLs for subcontractor registration and bid plan room.
 */
(function () {
  'use strict';

  const LINK_DEFS = [
    {
      id: 'signup',
      label: 'Subcontractor signup',
      hint: 'Send to new subs — register for plan room access',
      path: '/plan-room#prRegister',
    },
    {
      id: 'public-home',
      label: 'Plan room home',
      hint: 'Registration page + public list of bidding projects (teaser)',
      path: '/plan-room',
    },
    {
      id: 'bid-login',
      label: 'Bid & plan room (login link)',
      hint: 'Best link for approved bidders — sign in, then open projects',
      path: '/login?next=/plan-room/projects',
    },
    {
      id: 'bid-projects',
      label: 'Bid & plan room projects',
      hint: 'Direct URL after they already have an account (requires login)',
      path: '/plan-room/projects',
    },
  ];

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function fullUrl(path) {
    const origin = window.location.origin || '';
    return `${origin}${path}`;
  }

  function renderInto(host) {
    if (!host || host.dataset.prShareMounted === '1') return;
    host.dataset.prShareMounted = '1';
    const compact = host.classList.contains('pr-share-compact');
    host.innerHTML = `
      <div class="pr-share-block${compact ? ' pr-share-compact-block' : ''}">
        <div class="pr-share-head">
          <strong>Links to share</strong>
          <span class="pr-share-sub">Copy and email or text to subcontractors</span>
        </div>
        <ul class="pr-share-list">
          ${LINK_DEFS.map((link) => {
            const url = fullUrl(link.path);
            return `
              <li class="pr-share-row">
                <div class="pr-share-label">
                  <span class="pr-share-title">${esc(link.label)}</span>
                  <span class="pr-share-hint">${esc(link.hint)}</span>
                </div>
                <div class="pr-share-copy">
                  <input type="text" class="pr-share-input" readonly value="${esc(url)}" aria-label="${esc(link.label)}">
                  <button type="button" class="pr-share-btn" data-url="${esc(url)}">Copy</button>
                </div>
              </li>`;
          }).join('')}
        </ul>
      </div>
    `;
    host.querySelectorAll('.pr-share-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const url = btn.dataset.url || '';
        try {
          await navigator.clipboard.writeText(url);
          const prev = btn.textContent;
          btn.textContent = 'Copied';
          setTimeout(() => { btn.textContent = prev; }, 1600);
        } catch (_) {
          const input = btn.parentElement?.querySelector('.pr-share-input');
          if (input) {
            input.select();
            document.execCommand('copy');
            btn.textContent = 'Copied';
            setTimeout(() => { btn.textContent = 'Copy'; }, 1600);
          }
        }
      });
    });
    host.querySelectorAll('.pr-share-input').forEach((input) => {
      input.addEventListener('focus', () => input.select());
    });
  }

  function mountAll() {
    document.querySelectorAll('.plan-room-share-links-host').forEach(renderInto);
  }

  window.PlanRoomShareLinks = { mountAll, fullUrl, LINK_DEFS };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountAll);
  } else {
    mountAll();
  }
})();
