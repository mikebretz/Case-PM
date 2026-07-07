/**
 * Case PM — Global page activity log (localStorage, feeds future audit log)
 */
(function (global) {
    'use strict';

    const STORAGE_KEY = 'casepm_activity_log_v1';
    const MAX_ENTRIES = 5000;

    function pageModule() {
        const ep = (document.body.dataset.pageModule || '').trim();
        if (ep) return ep;
        const path = (global.location.pathname || '').replace(/^\//, '').split('/')[0] || 'app';
        return path || 'app';
    }

    function loadAll() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        } catch (e) {
            return [];
        }
    }

    function saveAll(entries) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
    }

    function formatTime(iso) {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return iso;
        return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    function log(action, detail, module) {
        const mod = module || pageModule();
        const entry = {
            id: Date.now() + '-' + Math.random().toString(36).slice(2, 8),
            module: mod,
            action: String(action || 'Action'),
            detail: detail ? String(detail) : '',
            user: (document.body.dataset.currentUser || 'User'),
            ts: new Date().toISOString()
        };
        const all = loadAll();
        all.unshift(entry);
        saveAll(all);
        refreshFooterPreview();
        return entry;
    }

    function getEntries(filter) {
        const f = filter || {};
        return loadAll().filter(e => {
            if (f.module && e.module !== f.module) return false;
            if (f.search) {
                const q = f.search.toLowerCase();
                const blob = (e.action + ' ' + e.detail + ' ' + e.module).toLowerCase();
                if (!blob.includes(q)) return false;
            }
            return true;
        });
    }

    function refreshFooterPreview() {
        const el = document.getElementById('footerActivityPreview');
        if (!el) return;
        const recent = getEntries({ module: pageModule() }).slice(0, 1)[0];
        el.textContent = recent ? `${recent.action}${recent.detail ? ': ' + recent.detail : ''}` : '';
        el.title = recent ? formatTime(recent.ts) : '';
    }

    function showLogModal(opts) {
        const options = opts || {};
        const mod = options.module || pageModule();
        const dlg = document.getElementById('globalActivityLogModal');
        if (!dlg) {
            alert('Activity log modal not found.');
            return;
        }
        const searchEl = document.getElementById('globalActivityLogSearch');
        const moduleEl = document.getElementById('globalActivityLogModule');
        if (searchEl) searchEl.value = options.search || '';
        if (moduleEl) moduleEl.value = mod === 'all' ? 'all' : mod;
        renderLogTable();
        dlg.showModal();
    }

    function renderLogTable() {
        const tbody = document.getElementById('globalActivityLogBody');
        if (!tbody) return;
        const search = (document.getElementById('globalActivityLogSearch')?.value || '').trim();
        const mod = document.getElementById('globalActivityLogModule')?.value || 'all';
        const rows = getEntries({
            module: mod === 'all' ? null : mod,
            search: search || null
        }).slice(0, 500);

        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-8 text-center text-zinc-500">No activity logged yet.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(e => `
            <tr class="border-b border-zinc-800 hover:bg-zinc-800/40">
                <td class="px-3 py-2 text-xs text-zinc-500 whitespace-nowrap">${formatTime(e.ts)}</td>
                <td class="px-3 py-2 text-xs text-emerald-400/90 uppercase">${e.module}</td>
                <td class="px-3 py-2 text-sm font-medium">${escapeHtml(e.action)}</td>
                <td class="px-3 py-2 text-sm text-zinc-400">${escapeHtml(e.detail)}</td>
            </tr>
        `).join('');
    }

    function escapeHtml(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function exportLog() {
        const blob = new Blob([JSON.stringify(loadAll(), null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `casepm_activity_log_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
    }

    function init() {
        refreshFooterPreview();
        document.getElementById('globalActivityLogSearch')?.addEventListener('input', renderLogTable);
        document.getElementById('globalActivityLogModule')?.addEventListener('change', renderLogTable);
    }

    global.CasePMActivityLog = {
        log,
        getEntries,
        showLogModal,
        renderLogTable,
        exportLog,
        refreshFooterPreview,
        pageModule
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(typeof window !== 'undefined' ? window : global);
