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
    if (payload.logo_data_url && global.CasePMUserProfile?.updateCompanyLogo) {
      global.CasePMUserProfile.updateCompanyLogo(payload.logo_data_url);
    }
    CasePMDialog?.alert('Company information saved.', 'success');
  }

  function collectBackupSettingsFromForm() {
    return {
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
    };
  }

  function updateCloudProviderFields() {
    const provider = document.getElementById('cloud_provider')?.value || 'local_folder';
    const cloudOnly = document.getElementById('cloudBucketRegionFields');
    const mirrorWrap = document.getElementById('cloudMirrorPathWrap');
    const isLocal = provider === 'local_folder';
    if (cloudOnly) cloudOnly.classList.toggle('hidden', isLocal);
    if (mirrorWrap) mirrorWrap.classList.toggle('hidden', !isLocal);
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
    updateCloudProviderFields();
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
      backup: collectBackupSettingsFromForm(),
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
    await loadBackupForm();
  }

  async function runBackupNow() {
    const backup = collectBackupSettingsFromForm();
    const mirrorPath = backup.cloud?.local_mirror_path || '';
    const mirrorEnabled = backup.cloud?.enabled;
    let message = 'Create a full local backup now (database + settings + uploads)?';
    if (mirrorPath) {
      message += `\n\nOff-site copy path:\n${mirrorPath}`;
      if (!mirrorEnabled) {
        message += '\n\n(Cloud mirror checkbox is off, but Run Backup Now will still copy to this folder when a path is entered.)';
      }
    } else if (mirrorEnabled) {
      message += '\n\nWarning: cloud mirror is enabled but no mirror folder path is set — only a local backup will be created.';
    }
    const ok = await CasePMDialog?.confirm(message, { title: 'Run backup', confirmLabel: 'Start' });
    if (!ok) return;
    try {
      const json = await api('/api/program-settings/backup/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup }),
      });
      const result = json.result || {};
      let detail = `Local backup created: ${result.filename}`;
      if (result.cloud_mirror_status === 'success') {
        detail += `\n\nCopied to off-site folder:\n${result.cloud_mirror_file || result.cloud_mirror}`;
      } else if (result.cloud_mirror_skipped) {
        detail += `\n\nOff-site copy skipped: ${result.cloud_mirror_skipped}`;
      }
      CasePMDialog?.alert(detail, result.cloud_mirror_status === 'success' ? 'success' : 'info');
      await refreshBackupList();
      await loadBackupForm();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Backup failed.', 'error');
      await loadBackupForm();
    }
  }

  async function refreshBackupList() {
    const host = document.getElementById('backupHistoryList');
    if (!host) return;
    const { backups } = await api('/api/program-settings/backup/list');
    if (!backups?.length) {
      host.innerHTML = '<div class="text-sm text-zinc-500">No backups yet. Run a backup first, or upload a backup file below.</div>';
      return;
    }
    host.innerHTML = backups.map(b => `
      <div class="flex flex-wrap justify-between items-center gap-2 py-2 border-b border-zinc-800 text-sm">
        <div class="min-w-0">
          <div class="font-mono text-emerald-400 truncate">${escapeHtml(b.filename)}</div>
          <div class="text-xs text-zinc-500">${(b.size_bytes / 1024 / 1024).toFixed(2)} MB · ${escapeHtml((b.created_at || '').slice(0, 19).replace('T', ' '))}</div>
        </div>
        <button type="button" class="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 rounded-xl text-xs font-medium whitespace-nowrap"
                onclick="CasePMProgramSettings.installBackup(${JSON.stringify(b.filename)})">
          <i class="fa-solid fa-rotate-left mr-1"></i> Install
        </button>
      </div>`).join('');
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function installBackup(filename) {
    const ok = await CasePMDialog?.confirm(
      `Install backup "${filename}"?\n\nThis replaces your current database, settings, and uploads. A safety backup is created first.`,
      { title: 'Install backup', confirmLabel: 'Install', danger: true }
    );
    if (!ok) return;
    try {
      const json = await api('/api/program-settings/backup/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename }),
      });
      const safety = json.result?.safety_backup;
      await CasePMDialog?.alert(
        `Backup installed successfully.${safety ? `\n\nSafety copy saved as: ${safety}` : ''}\n\nYou will now be signed out so the restored database can load cleanly.`,
        'success'
      );
      window.location.href = '/logout?next=/login';
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Backup install failed.', 'error');
    }
  }

  async function chooseBackupToInstall() {
    const { backups } = await api('/api/program-settings/backup/list');
    if (!backups?.length) {
      CasePMDialog?.alert('No backups available yet. Run a backup or upload a .zip file first.', 'info');
      return;
    }
    const picked = await CasePMDialog?.select({
      title: 'Install from backup',
      message: 'Select the backup to install. Your current data is saved automatically before replacing it.',
      items: backups.map(b => ({
        value: b.filename,
        label: `${b.filename} — ${(b.size_bytes / 1024 / 1024).toFixed(2)} MB · ${(b.created_at || '').slice(0, 19).replace('T', ' ')}`,
      })),
      submitLabel: 'Install selected backup',
      emptyLabel: 'No backups found',
    });
    if (!picked?.value) return;
    await installBackup(picked.value);
  }

  async function uploadBackupFile(input) {
    const file = input?.files?.[0];
    if (!file) return;
    if (!/\.zip$/i.test(file.name)) {
      CasePMDialog?.alert('Please choose a .zip backup file.', 'warning');
      input.value = '';
      return;
    }
    const ok = await CasePMDialog?.confirm(
      `Upload backup file "${file.name}" to the backup library?`,
      { title: 'Upload backup', confirmLabel: 'Upload' }
    );
    if (!ok) {
      input.value = '';
      return;
    }
    try {
      const form = new FormData();
      form.append('backup', file);
      const res = await fetch('/api/program-settings/backup/upload', {
        method: 'POST',
        credentials: 'same-origin',
        body: form,
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || res.statusText);
      await refreshBackupList();
      const installNow = await CasePMDialog?.confirm(
        `Uploaded ${json.backup?.filename || file.name}.\n\nInstall this backup now?`,
        { title: 'Install uploaded backup', confirmLabel: 'Install now' }
      );
      if (installNow && json.backup?.filename) {
        await installBackup(json.backup.filename);
      }
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Upload failed.', 'error');
    } finally {
      input.value = '';
    }
  }

  async function clearAllProgramData() {
    const ok = await CasePMDialog?.confirm(
      'This permanently deletes all projects, users, documents, uploads, and settings.\n\nA safety backup is created first, then the program is reset to a fresh install with the default admin account.',
      { title: 'Clear all program data', confirmLabel: 'Continue', danger: true }
    );
    if (!ok) return;
    const typed = await CasePMDialog?.prompt(
      'Type DELETE ALL to confirm clearing everything.',
      { title: 'Final confirmation', defaultValue: '', submitLabel: 'Clear everything', label: 'Confirmation text' }
    );
    if ((typed || '').trim().toUpperCase() !== 'DELETE ALL') {
      CasePMDialog?.alert('Clear cancelled — confirmation text did not match.', 'info');
      return;
    }
    try {
      const json = await api('/api/program-settings/backup/clear-all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: 'DELETE ALL' }),
      });
      const safety = json.result?.safety_backup;
      const login = json.default_login || { email: 'admin@casepm.local', password: 'admin123' };
      await CasePMDialog?.alert(
        `All program data has been cleared.${safety ? `\n\nSafety backup: ${safety}` : ''}\n\nDefault login:\n${login.email}\n${login.password}\n\nYou will now be signed out.`,
        'success'
      );
      window.location.href = '/logout?next=/login';
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Clear failed.', 'error');
    }
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

  async function pushEmailToServer(settings) {
    if (!settings) return;
    await api('/api/program-settings/email', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: settings }),
    });
  }

  function previewNumber(key, prefix, pad) {
    const p = (prefix || 'DOC').toUpperCase();
    const width = Math.max(1, Math.min(6, parseInt(pad, 10) || 3));
    return `${p}-${String(1).padStart(width, '0')}`;
  }

  async function loadNumberingForm() {
    const { catalog } = await api('/api/program-settings/numbering');
    const body = document.getElementById('numberingTableBody');
    if (!body) return;
    body.innerHTML = (catalog || []).map(row => `
      <tr data-num-key="${row.key}">
        <td class="py-2 px-2 text-zinc-300">${row.label}</td>
        <td class="py-2 px-2"><input type="text" class="num-prefix w-24 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 font-mono text-sm uppercase" value="${row.prefix || ''}" maxlength="12"></td>
        <td class="py-2 px-2"><input type="number" class="num-pad w-16 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-sm" value="${row.pad || 3}" min="1" max="6"></td>
        <td class="py-2 px-2">
          <select class="num-scope bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-xs">
            <option value="global" ${row.scope === 'global' ? 'selected' : ''}>Company-wide</option>
            <option value="project" ${row.scope === 'project' ? 'selected' : ''}>Per project</option>
          </select>
        </td>
        <td class="py-2 px-2 font-mono text-emerald-400 text-xs num-preview">${row.example || ''}</td>
      </tr>`).join('');
    body.querySelectorAll('tr').forEach(tr => {
      const update = () => {
        const prefix = tr.querySelector('.num-prefix')?.value;
        const pad = tr.querySelector('.num-pad')?.value;
        const el = tr.querySelector('.num-preview');
        if (el) el.textContent = previewNumber(tr.dataset.numKey, prefix, pad);
      };
      tr.querySelectorAll('input, select').forEach(el => el.addEventListener('input', update));
    });
  }

  async function saveNumberingForm(e) {
    e.preventDefault();
    const numbering = {};
    document.querySelectorAll('#numberingTableBody tr[data-num-key]').forEach(tr => {
      const key = tr.dataset.numKey;
      numbering[key] = {
        prefix: tr.querySelector('.num-prefix')?.value?.trim().toUpperCase(),
        pad: parseInt(tr.querySelector('.num-pad')?.value || '3', 10),
        scope: tr.querySelector('.num-scope')?.value || 'global',
      };
    });
    await api('/api/program-settings/numbering', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ numbering }),
    });
    CasePMDialog?.alert('Document numbering saved.', 'success');
  }

  async function loadPayAppsForm() {
    const { pay_apps: p } = await api('/api/program-settings/pay-apps');
    if (!p) return;
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    set('paRetainage', p.default_retainage_percent || 10);
    setChk('paLienWaiver', p.require_lien_waiver_on_sub_pay_app);
    setChk('paRequireAllSubs', p.require_all_sub_pay_apps_before_g702);
    setChk('paZeroDollar', p.allow_zero_dollar_sub_pay_apps);
    setChk('paSageAuto', p.sage_sync_auto_enabled);
    setChk('paDeadlineEnabled', p.require_submission_deadline);
    const daySel = document.getElementById('paDeadlineDay');
    if (daySel && !daySel.options.length) {
      for (let d = 15; d <= 28; d++) daySel.add(new Option(`${d}`, d));
    }
    if (daySel) daySel.value = p.submission_deadline_day || 20;
    document.getElementById('paDeadlineDayWrap')?.classList.toggle('hidden', !p.require_submission_deadline);
  }

  async function savePayAppsForm(e) {
    e.preventDefault();
    const payload = {
      default_retainage_percent: parseInt(document.getElementById('paRetainage')?.value || '10', 10),
      require_lien_waiver_on_sub_pay_app: document.getElementById('paLienWaiver')?.checked,
      require_all_sub_pay_apps_before_g702: document.getElementById('paRequireAllSubs')?.checked,
      allow_zero_dollar_sub_pay_apps: document.getElementById('paZeroDollar')?.checked,
      sage_sync_auto_enabled: document.getElementById('paSageAuto')?.checked,
      require_submission_deadline: document.getElementById('paDeadlineEnabled')?.checked,
      submission_deadline_day: parseInt(document.getElementById('paDeadlineDay')?.value || '20', 10),
    };
    await api('/api/program-settings/pay-apps', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Pay application defaults saved.', 'success');
  }

  async function loadPayAppDefaultsForModule() {
    try {
      const { pay_apps: p } = await api('/api/program-settings/pay-apps');
      return p || {};
    } catch (_) {
      return {};
    }
  }

  global.CasePMProgramSettings = {
    loadCompanyForm, saveCompanyForm, loadBackupForm, saveBackupForm,
    runBackupNow, refreshBackupList, chooseBackupToInstall, installBackup,
    uploadBackupFile, clearAllProgramData, updateCloudProviderFields,
    setSageMode, testSageConnection,
    syncEmailFromServer, pushEmailToServer,
    loadNumberingForm, saveNumberingForm, loadPayAppsForm, savePayAppsForm,
    loadPayAppDefaultsForModule,
  };
})(window);
