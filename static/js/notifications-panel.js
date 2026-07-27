(function () {
  'use strict';

  const panel = () => document.getElementById('notificationsPanel');
  const listEl = () => document.getElementById('notificationsList');
  const countEl = () => document.getElementById('notificationsCount');
  const badgeEl = () => document.getElementById('notificationsBadge');
  const bellEl = () => document.getElementById('notificationsBell');
  let eventSource = null;

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function timeAgo(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 60) return 'Just now';
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
  }

  function iconFor(title) {
    const t = (title || '').toLowerCase();
    if (t.includes('rfi')) return ['fa-circle-question', 'emerald'];
    if (t.includes('pay') || t.includes('billing')) return ['fa-file-invoice-dollar', 'amber'];
    if (t.includes('change') || t.includes('co')) return ['fa-file-pen', 'sky'];
    if (t.includes('submittal')) return ['fa-clipboard-check', 'violet'];
    if (t.includes('safety')) return ['fa-shield-alt', 'blue'];
    if (t.includes('transmittal')) return ['fa-paper-plane', 'emerald'];
    return ['fa-bell', 'zinc'];
  }

  async function fetchNotifications() {
    const res = await fetch('/api/notifications', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!res.ok) return [];
    return res.json();
  }

  function render(items) {
    const unread = items.filter(n => !n.is_read).length;
    if (countEl()) countEl().textContent = unread ? `${unread} new update${unread === 1 ? '' : 's'}` : 'All caught up';
    if (badgeEl()) {
      badgeEl().textContent = unread > 99 ? '99+' : String(unread);
      badgeEl().classList.toggle('hidden', unread === 0);
    }
    const host = listEl();
    if (!host) return;
    if (!items.length) {
      host.innerHTML = '<div class="p-4 text-center text-zinc-500 text-sm">No notifications yet.</div>';
      return;
    }
    host.innerHTML = items.slice(0, 20).map(n => {
      const [icon, color] = iconFor(n.title);
      return `<button type="button" class="w-full text-left flex gap-3 p-3 rounded-2xl ${n.is_read ? 'bg-zinc-900/50' : 'bg-zinc-800'} hover:bg-zinc-700/80 transition-colors notification-item" data-id="${n.id}" data-link="${esc(n.link || '')}">
        <div class="w-8 h-8 bg-${color}-600/20 text-${color}-400 rounded-xl flex items-center justify-center flex-shrink-0">
          <i class="fa-solid ${icon}"></i>
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-medium text-sm ${n.is_read ? 'text-zinc-300' : 'text-white'}">${esc(n.title)}</div>
          <div class="text-xs text-zinc-500 truncate">${esc(n.message)} · ${timeAgo(n.created_at)}</div>
        </div>
      </button>`;
    }).join('');
    host.querySelectorAll('.notification-item').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.id;
        const link = btn.dataset.link;
        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        await fetch(`/api/notifications/${id}/read`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: token ? { 'X-CSRF-Token': token, 'X-Requested-With': 'XMLHttpRequest' } : { 'X-Requested-With': 'XMLHttpRequest' },
        }).catch(() => {});
        closePanel();
        if (link) window.location.href = link;
        else refresh();
      });
    });
  }

  async function refresh() {
    try {
      const items = await fetchNotifications();
      render(items);
    } catch (e) {
      console.error('notifications refresh', e);
    }
  }

  function openPanel() {
    const el = panel();
    if (!el) {
      console.warn('notificationsPanel element not found');
      return;
    }
    el.classList.add('is-open');
    el.setAttribute('aria-hidden', 'false');
    bellEl()?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    refresh();
  }

  function closePanel() {
    const el = panel();
    if (!el) return;
    el.classList.remove('is-open');
    el.setAttribute('aria-hidden', 'true');
    bellEl()?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  function togglePanel() {
    const el = panel();
    if (!el) return;
    if (el.classList.contains('is-open')) closePanel();
    else openPanel();
  }

  async function markAllRead() {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    await fetch('/api/notifications/mark-all-read', {
      method: 'POST',
      credentials: 'same-origin',
      headers: token ? { 'X-CSRF-Token': token, 'X-Requested-With': 'XMLHttpRequest' } : { 'X-Requested-With': 'XMLHttpRequest' },
    });
    refresh();
  }

  function connectStream() {
    if (eventSource || typeof EventSource === 'undefined') return;
    try {
      eventSource = new EventSource('/api/notifications/stream');
      eventSource.addEventListener('notification', () => refresh());
      eventSource.addEventListener('ping', () => {});
      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        setTimeout(connectStream, 15000);
      };
    } catch (e) {
      console.warn('SSE unavailable', e);
    }
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    const arr = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; ++i) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  async function subscribePush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      if (window.CasePMDialog?.alert) CasePMDialog.alert('Push notifications are not supported in this browser.', 'info');
      return;
    }
    try {
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') return;
      const reg = await navigator.serviceWorker.ready;
      const vapidKey = document.body.dataset.vapidPublicKey || '';
      const options = { userVisibleOnly: true };
      if (vapidKey) {
        options.applicationServerKey = urlBase64ToUint8Array(vapidKey);
      }
      const sub = await reg.pushManager.subscribe(options);
      const token = document.querySelector('meta[name="csrf-token"]')?.content;
      await fetch('/api/push/subscribe', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'X-CSRF-Token': token } : {}),
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify(sub.toJSON()),
      });
      document.getElementById('notificationsEnablePush')?.classList.add('hidden');
      if (window.CasePMDialog?.alert) CasePMDialog.alert('Push notifications enabled.', 'success');
    } catch (e) {
      console.warn('push subscribe failed', e);
      if (window.CasePMDialog?.alert) CasePMDialog.alert('Could not enable push notifications.', 'warning');
    }
  }

  function setupPushPrompt() {
    const btn = document.getElementById('notificationsEnablePush');
    if (!btn) return;
    if ('Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window) {
      if (Notification.permission === 'default') btn.classList.remove('hidden');
      btn.addEventListener('click', subscribePush);
    }
  }

  window.CasePMNotifications = { refresh, open: openPanel, close: closePanel, toggle: togglePanel };

  function bindUi() {
    const bell = bellEl();
    if (bell && !bell.dataset.bound) {
      bell.dataset.bound = '1';
      bell.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        togglePanel();
      });
    }
    document.getElementById('notificationsClose')?.addEventListener('click', closePanel);
    document.getElementById('notificationsBackdrop')?.addEventListener('click', closePanel);
    document.getElementById('notificationsMarkAll')?.addEventListener('click', markAllRead);
    document.getElementById('notificationsViewAll')?.addEventListener('click', () => {
      closePanel();
      window.location.href = '/notifications';
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && panel()?.classList.contains('is-open')) closePanel();
    });
  }

  function boot() {
    bindUi();
    setupPushPrompt();
    refresh();
    connectStream();
    setInterval(refresh, 120000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
