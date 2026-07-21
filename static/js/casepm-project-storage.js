/**
 * Project-scoped localStorage for Case PM modules.
 * Keys are suffixed with _p{projectId} unless listed as global.
 */
(function () {
    const GLOBAL_KEYS = new Set([
        'casepm_current_project_id',
        'casepm_companies',
        'users',
        'userSignature',
    ]);

    function projectId() {
        const raw = window.CASEPM_ACTIVE_PROJECT_ID || localStorage.getItem('casepm_current_project_id');
        const id = parseInt(raw, 10);
        return id > 0 ? String(id) : '';
    }

    function storageKey(key) {
        if (GLOBAL_KEYS.has(key)) return key;
        const pid = projectId();
        if (!pid) return key;
        return `${key}_p${pid}`;
    }

    window.casepmStore = {
        projectId,
        storageKey,
        hasProject() {
            return !!projectId();
        },
        getItem(key) {
            if (!GLOBAL_KEYS.has(key) && !projectId()) return null;
            return localStorage.getItem(storageKey(key));
        },
        setItem(key, value) {
            if (!GLOBAL_KEYS.has(key) && !projectId()) {
                console.warn('[CasePM] Ignoring save — no current project selected:', key);
                return;
            }
            localStorage.setItem(storageKey(key), value);
        },
        removeItem(key) {
            if (!GLOBAL_KEYS.has(key) && !projectId()) return;
            localStorage.removeItem(storageKey(key));
        },
        getJSON(key, fallback) {
            try {
                const raw = this.getItem(key);
                if (raw == null || raw === '') {
                    return fallback !== undefined ? fallback : null;
                }
                return JSON.parse(raw);
            } catch (e) {
                return fallback !== undefined ? fallback : null;
            }
        },
        setJSON(key, value) {
            this.setItem(key, JSON.stringify(value));
        },
    };
})();
