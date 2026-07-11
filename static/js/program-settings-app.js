/**
 * Program Settings — server persistence + cross-page email sync
 */
(function (global) {
  'use strict';

  async function api(path, opts) {
    const res = await fetch(path, { credentials: 'same-origin', ...opts });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || res.statusText);
    return json;
  }

  async function loadCompanyForm() {
    const { company } = await api('/api/program-settings/company');
    const map = {
      company_name: 'company_name', tax_id: 'tax_id', company_phone: 'company_phone',
      company_address: 'company_address', company_city: 'company_city',
      company_state: 'company_state', company_zip: 'company_zip',
      company_website: 'company_website', company_license: 'company_license', dba_name: 'dba_name',
    };
    Object.entries(map).forEach(([key, id]) => {
      const el = document.getElementById(id);
      if (el && company[key] != null) el.value = company[key];
    });
    if (company.logo_data_url) {
      const preview = document.getElementById('logoPreview');
      const placeholder = document.getElementById('logoPlaceholder');
      if (preview) { preview.src = company.logo_data_url; preview.classList.remove('hidden'); }
      if (placeholder) placeholder.classList.add('hidden');
    }
  }

  async function saveCompanyForm(e) {
    e.preventDefault();
    const payload = {
      company_name: document.getElementById('company_name')?.value?.trim(),
      tax_id: document.getElementById('tax_id')?.value?.trim(),
      company_phone: document.getElementById('company_phone')?.value?.trim(),
      company_address: document.getElementById('company_address')?.value?.trim(),
      company_city: document.getElementById('company_city')?.value?.trim(),
      company_state: document.getElementById('company_state')?.value?.trim(),
      company_zip: document.getElementById('company_zip')?.value?.trim(),
      company_website: document.getElementById('company_website')?.value?.trim(),
      company_license: document.getElementById('company_license')?.value?.trim(),
      dba_name: document.getElementById('dba_name')?.value?.trim(),
      logo_data_url: document.getElementById('logoPreview')?.src?.startsWith('data:')
        ? document.getElementById('logoPreview').src : '',
    };
    await api('/api/program-settings/company', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Company information saved.', 'success');
  }

  async function loadBackupForm() {
    const json = await api('/api/program-settings/backup');
    const b = json.backup || {};
    const m = json.maintenance || {};
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    setChk('backup_auto_enabled', b.auto_enabled);
    set('backup_frequency', b.frequency || 'daily');
    set('backup_retention_days', b.retention_days || 30);
    set('backup_local_path', b.local_path || 'instance/backups');
    set('backup_maintenance_window', b.maintenance_window || '02:00');
    setChk('cloud_backup_enabled', b.cloud?.enabled);
    set('cloud_provider', b.cloud?.provider || 'local_folder');
    set('cloud_mirror_path', b.cloud?.local_mirror_path || '');
    set('cloud_bucket', b.cloud?.bucket || '');
    set('cloud_region', b.cloud?.region || '');
    setChk('maint_db_vacuum', m.db_vacuum_enabled !== false);
    set('maint_log_retention', m.log_retention_days || 90);
    set('maint_temp_cleanup', m.temp_upload_cleanup_days || 14);
    const statusEl = document.getElementById('backupLastRunStatus');
    if (statusEl) {
      statusEl.textContent = b.last_run_at
        ? `Last backup: ${b.last_run_at} — ${b.last_run_status || 'unknown'}`
        : 'No backups run yet.';
    }
    await refreshBackupList();
  }

  async function saveBackupForm() {
    const payload = {
      backup: {
        auto_enabled: document.getElementById('backup_auto_enabled')?.checked,
        frequency: document.getElementById('backup_frequency')?.value,
        retention_days: parseInt(document.getElementById('backup_retention_days')?.value || '30', 10),
        local_path: document.getElementById('backup_local_path')?.value?.trim(),
        maintenance_window: document.getElementById('backup_maintenance_window')?.value,
        cloud: {
          enabled: document.getElementById('cloud_backup_enabled')?.checked,
          provider: document.getElementById('cloud_provider')?.value,
          local_mirror_path: document.getElementById('cloud_mirror_path')?.value?.trim(),
          bucket: document.getElementById('cloud_bucket')?.value?.trim(),
          region: document.getElementById('cloud_region')?.value?.trim(),
        },
      },
      maintenance: {
        db_vacuum_enabled: document.getElementById('maint_db_vacuum')?.checked,
        log_retention_days: parseInt(document.getElementById('maint_log_retention')?.value || '90', 10),
        temp_upload_cleanup_days: parseInt(document.getElementById('maint_temp_cleanup')?.value || '14', 10),
        notify_admin_on_backup_failure: true,
      },
    };
    await api('/api/program-settings/backup', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Backup & maintenance settings saved.', 'success');
  }

  async function runBackupNow() {
    const ok = await CasePMDialog?.confirm('Create a full local backup now (database + settings + uploads)?', { title: 'Run backup', confirmLabel: 'Start' });
    if (!ok) return;
    const json = await api('/api/program-settings/backup/run', { method: 'POST' });
    CasePMDialog?.alert(`Backup created: ${json.result?.filename}`, 'success');
    await refreshBackupList();
    await loadBackupForm();
  }

  async function refreshBackupList() {
    const host = document.getElementById('backupHistoryList');
    if (!host) return;
    const { backups } = await api('/api/program-settings/backup/list');
    if (!backups?.length) {
      host.innerHTML = '<div class="text-sm text-zinc-500">No backups yet.</div>';
      return;
    }
    host.innerHTML = backups.map(b => `
      <div class="flex justify-between items-center py-2 border-b border-zinc-800 text-sm">
        <span class="font-mono text-emerald-400">${b.filename}</span>
        <span class="text-zinc-500">${(b.size_bytes / 1024 / 1024).toFixed(2)} MB · ${b.created_at?.slice(0, 19) || ''}</span>
      </div>`).join('');
  }

  function setSageMode(mode) {
    document.getElementById('sageQuickPanel')?.classList.toggle('hidden', mode !== 'quick');
    document.getElementById('sageDetailedPanel')?.classList.toggle('hidden', mode !== 'detailed');
    document.querySelectorAll('[data-sage-mode]').forEach(btn => {
      btn.classList.toggle('bg-emerald-600', btn.dataset.sageMode === mode);
      btn.classList.toggle('text-white', btn.dataset.sageMode === mode);
    });
    const hidden = document.getElementById('sage_connection_mode');
    if (hidden) hidden.value = mode;
  }

  async function testSageConnection() {
    const json = await api('/api/program-settings/sage/test', { method: 'POST' });
    CasePMDialog?.alert(json.message || 'Sage connection checked.', json.mode === 'simulated' ? 'info' : 'success');
  }

  async function syncEmailFromServer() {
    try {
      const { email } = await api('/api/program-settings/email');
      if (email && Object.keys(email).length) {
        localStorage.setItem('casepm_email_settings', JSON.stringify(email));
        global.CasePMEmailSettings = email;
        global.dispatchEvent(new CustomEvent('casepm-email-settings-changed', { detail: email }));
      }
    } catch (_) { /* ignore */ }
  }

  async function pushEmailToServer(settings) {
    if (!settings) return;
    await api('/api/program-settings/email', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: settings }),
    });
  }

  global.CasePMProgramSettings = {
    loadCompanyForm, saveCompanyForm, loadBackupForm, saveBackupForm,
    runBackupNow, refreshBackupList, setSageMode, testSageConnection,
    syncEmailFromServer, pushEmailToServer,
  };
})(window);
