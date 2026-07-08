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
        return String(
            window.CASEPM_ACTIVE_PROJECT_ID ||
            localStorage.getItem('casepm_current_project_id') ||
            '0'
        );
    }

    function storageKey(key) {
        if (GLOBAL_KEYS.has(key)) return key;
        return `${key}_p${projectId()}`;
    }

    window.casepmStore = {
        projectId,
        storageKey,
        getItem(key) {
            return localStorage.getItem(storageKey(key));
        },
        setItem(key, value) {
            localStorage.setItem(storageKey(key), value);
        },
        removeItem(key) {
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
