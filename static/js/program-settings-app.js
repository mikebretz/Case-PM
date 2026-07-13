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

  function formatBackupTime(value) {
    if (!value) return '';
    if (typeof value === 'string' && (value.includes(' ET') || value.includes(' EST') || value.includes(' EDT'))) {
      return value;
    }
    const raw = String(value).trim();
    const iso = raw.includes('T') ? raw : raw.replace(' ', 'T');
    const d = new Date(iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`);
    if (Number.isNaN(d.getTime())) return String(value).slice(0, 19).replace('T', ' ');
    return new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZoneName: 'short',
    }).format(d);
  }

  function setBackupRunButtonDisabled(disabled) {
    document.querySelectorAll('[data-backup-run-btn]').forEach((btn) => {
      btn.disabled = !!disabled;
      btn.classList.toggle('opacity-50', !!disabled);
      btn.classList.toggle('pointer-events-none', !!disabled);
    });
  }

  function renderBackupProgressPanel(job) {
    const panel = document.getElementById('backupProgressPanel');
    const bar = document.getElementById('backupProgressBar');
    const step = document.getElementById('backupProgressStep');
    const pct = document.getElementById('backupProgressPercent');
    const file = document.getElementById('backupProgressFile');
    const destHost = document.getElementById('backupProgressDestinations');
    if (!panel) return;
    panel.classList.remove('hidden');
    const progress = job?.progress ?? 0;
    if (bar) bar.style.width = `${progress}%`;
    if (step) step.textContent = job?.step || 'Working…';
    if (pct) pct.textContent = `${progress}%`;
    if (file) file.textContent = job?.current_file ? `Current: ${job.current_file}` : '';
    if (destHost && Array.isArray(job?.destinations)) {
      destHost.innerHTML = job.destinations.map((d) => `
        <div class="flex gap-2 items-start text-zinc-300">
          <i class="fa-solid fa-folder text-emerald-500 mt-0.5"></i>
          <div class="min-w-0">
            <div class="text-xs text-zinc-500">${escapeHtml(d.label || 'Destination')}</div>
            <div class="font-mono text-xs break-all">${escapeHtml(d.path || '')}</div>
            ${d.warning ? `<div class="text-amber-400 text-xs mt-0.5">${escapeHtml(d.warning)}</div>` : ''}
          </div>
        </div>`).join('');
    }
  }

  function hideBackupProgressPanel() {
    document.getElementById('backupProgressPanel')?.classList.add('hidden');
  }

  async function pollBackupJob(jobId) {
    const maxMs = 10 * 60 * 1000;
    const started = Date.now();
    while (Date.now() - started < maxMs) {
      const json = await api(`/api/program-settings/backup/run/status/${encodeURIComponent(jobId)}`);
      const job = json.job || {};
      renderBackupProgressPanel(job);
      if (job.status === 'done') {
        return job;
      }
      if (job.status === 'error') {
        throw new Error(job.error || 'Backup failed');
      }
      await new Promise((resolve) => setTimeout(resolve, 350));
    }
    throw new Error('Backup timed out');
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
    setChk('maint_notify_backup_fail', m.notify_admin_on_backup_failure !== false);
    updateCloudProviderFields();
    const statusEl = document.getElementById('backupLastRunStatus');
    const summaryEl = document.getElementById('backupLastRunSummary');
    const localPathEl = document.getElementById('backupLocalPathSummary');
    const mirrorPathEl = document.getElementById('backupMirrorPathSummary');
    const lastLabel = b.last_run_at ? formatBackupTime(b.last_run_at) : 'No backups yet';
    if (summaryEl) summaryEl.textContent = lastLabel;
    if (statusEl) {
      statusEl.textContent = b.last_run_at
        ? (b.last_run_status || 'unknown')
        : 'Run a backup to protect your data.';
    }
    if (localPathEl) localPathEl.textContent = b.local_path || 'instance/backups';
    if (mirrorPathEl) {
      const mirror = (b.cloud?.local_mirror_path || '').trim();
      mirrorPathEl.textContent = mirror || (b.cloud?.enabled ? 'Enabled — path missing' : 'Not configured');
    }
    try {
      await refreshBackupList();
    } catch (err) {
      const host = document.getElementById('backupHistoryList');
      if (host) {
        host.innerHTML = `<div class="text-sm text-red-400 py-4 text-center">Could not load backup history: ${escapeHtml(err.message || 'Unknown error')}</div>`;
      }
    }
  }

  async function saveBackupForm() {
    const payload = {
      backup: collectBackupSettingsFromForm(),
      maintenance: {
        db_vacuum_enabled: document.getElementById('maint_db_vacuum')?.checked,
        log_retention_days: parseInt(document.getElementById('maint_log_retention')?.value || '90', 10),
        temp_upload_cleanup_days: parseInt(document.getElementById('maint_temp_cleanup')?.value || '14', 10),
        notify_admin_on_backup_failure: document.getElementById('maint_notify_backup_fail')?.checked !== false,
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

  function excelExportBackupNote(result) {
    const info = result?.excel_exports;
    if (!info) return '\n\nNote: No excel_exports info returned — update Case PM and restart run.bat, then run a new backup.';
    if (info.included && info.file_count) {
      const fmt = info.format === 'csv' ? 'CSV (install openpyxl for .xlsx)' : 'Excel';
      return `\n\n${fmt} exports: ${info.file_count} file(s) in excel_exports/ inside the zip.\nOpen the .zip in Explorer — the folder is not under uploads/ on disk.`;
    }
    if (info.skipped) {
      return `\n\nExcel exports were skipped: ${info.reason || 'unknown reason'}.`;
    }
    if (info.error) {
      return `\n\nExcel exports failed: ${info.error}`;
    }
    return '';
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

    setBackupRunButtonDisabled(true);
    try {
      const plan = await api('/api/program-settings/backup/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup }),
      });
      renderBackupProgressPanel({ progress: 0, step: 'Starting backup…', destinations: plan.destinations || [] });

      const start = await api('/api/program-settings/backup/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup, async: true }),
      });
      const job = await pollBackupJob(start.job_id);
      const result = job.result || {};
      let detail = `Local backup created: ${result.filename}`;
      if (result.created_at_display) {
        detail += `\nTime: ${result.created_at_display}`;
      }
      if (result.cloud_mirror_status === 'success') {
        detail += `\n\nCopied to off-site folder:\n${result.cloud_mirror_file || result.cloud_mirror}`;
      } else if (result.cloud_mirror_skipped) {
        detail += `\n\nOff-site copy skipped: ${result.cloud_mirror_skipped}`;
      }
      detail += excelExportBackupNote(result);
      CasePMDialog?.alert(detail, result.cloud_mirror_status === 'success' ? 'success' : 'info');
      hideBackupProgressPanel();
      if (job.backups) {
        renderBackupHistory(job.backups);
      } else {
        await refreshBackupList();
      }
      await loadBackupForm();
    } catch (err) {
      CasePMDialog?.alert(err.message || 'Backup failed.', 'error');
      hideBackupProgressPanel();
      await loadBackupForm();
    } finally {
      setBackupRunButtonDisabled(false);
    }
  }

  function renderBackupHistory(backups) {
    const host = document.getElementById('backupHistoryList');
    if (!host) return;
    if (!backups?.length) {
      host.innerHTML = '<div class="text-sm text-zinc-500 py-4 text-center">No backups yet. Run a backup first, or upload a backup file below.</div>';
      return;
    }
    host.innerHTML = backups.map(b => `
      <div class="flex flex-wrap justify-between items-center gap-3 py-3 border-b border-zinc-800 last:border-0 text-sm hover:bg-zinc-800/40 px-1 -mx-1 rounded-md">
        <div class="min-w-0 flex-1">
          <div class="font-mono text-emerald-400 truncate">${escapeHtml(b.filename)}</div>
          <div class="text-xs text-zinc-500 mt-0.5">${(b.size_bytes / 1024 / 1024).toFixed(2)} MB · ${escapeHtml(formatBackupTime(b.created_at_display || b.created_at))}</div>
        </div>
        <button type="button" class="settings-btn settings-btn-secondary text-xs !h-8 !px-3"
                onclick="CasePMProgramSettings.installBackup(${JSON.stringify(b.filename)})">
          <i class="fa-solid fa-rotate-left"></i><span>Install</span>
        </button>
      </div>`).join('');
  }

  async function refreshBackupList() {
    const host = document.getElementById('backupHistoryList');
    if (!host) return;
    try {
      const json = await api('/api/program-settings/backup/list');
      if (json.ok === false && json.error) {
        host.innerHTML = `<div class="text-sm text-amber-400 py-4 text-center">${escapeHtml(json.error)}</div>`;
        return;
      }
      renderBackupHistory(json.backups || []);
    } catch (err) {
      host.innerHTML = `<div class="text-sm text-red-400 py-4 text-center">Could not load backup history: ${escapeHtml(err.message || 'Unknown error')}</div>`;
      throw err;
    }
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
        label: `${b.filename} — ${(b.size_bytes / 1024 / 1024).toFixed(2)} MB · ${formatBackupTime(b.created_at_display || b.created_at)}`,
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

  async function loadDocumentsForm() {
    const { documents: d } = await api('/api/program-settings/documents');
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    setChk('docShareApproval', d.share_requires_approval);
    set('docDefaultExpiry', d.default_share_expiry_days || 30);
    set('docMaxExpiry', d.max_share_expiry_days || 365);
    set('docRetentionYears', d.retention_years || 7);
  }

  async function saveDocumentsForm(e) {
    e.preventDefault();
    const payload = {
      share_requires_approval: document.getElementById('docShareApproval')?.checked,
      default_share_expiry_days: parseInt(document.getElementById('docDefaultExpiry')?.value || '30', 10),
      max_share_expiry_days: parseInt(document.getElementById('docMaxExpiry')?.value || '365', 10),
      retention_years: parseInt(document.getElementById('docRetentionYears')?.value || '7', 10),
    };
    await api('/api/program-settings/documents', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Document defaults saved.', 'success');
  }

  async function loadEstimatingForm() {
    const { estimating: est } = await api('/api/program-settings/estimating');
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    set('estRfpNotifyMode', est.rfp_notify_mode || 'both');
    set('estReminderHours', est.reminder_hours_before || 48);
    setChk('estAwardAutoCommitment', est.award_auto_commitment);
    setChk('estBudgetMappingAuto', est.budget_mapping_auto !== false);
    setChk('estAiScope', est.ai_scope_enabled !== false);
    setChk('estFeeBreakdown', est.fee_breakdown_visible !== false);
  }

  async function saveEstimatingForm(e) {
    e.preventDefault();
    const payload = {
      rfp_notify_mode: document.getElementById('estRfpNotifyMode')?.value || 'both',
      reminder_hours_before: parseInt(document.getElementById('estReminderHours')?.value || '48', 10),
      award_auto_commitment: document.getElementById('estAwardAutoCommitment')?.checked,
      budget_mapping_auto: document.getElementById('estBudgetMappingAuto')?.checked,
      ai_scope_enabled: document.getElementById('estAiScope')?.checked,
      fee_breakdown_visible: document.getElementById('estFeeBreakdown')?.checked,
    };
    await api('/api/program-settings/estimating', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Estimating defaults saved.', 'success');
  }

  async function loadInspectionsForm() {
    const json = await api('/api/program-settings/inspections');
    const insp = json.inspections || {};
    const options = json.reminder_options || [];
    const host = document.getElementById('inspReminderOffsets');
    const selected = new Set(insp.reminder_offsets || []);
    if (host) {
      host.innerHTML = options.map((opt) => `
        <label class="flex items-center gap-2 cursor-pointer border border-zinc-800 rounded-md p-3">
          <input type="checkbox" class="insp-offset accent-emerald-600" value="${escapeHtml(opt.key)}" ${selected.has(opt.key) ? 'checked' : ''}>
          <span class="text-zinc-300">${escapeHtml(opt.label)}</span>
        </label>`).join('');
    }
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    setChk('inspNotifyCreator', insp.notify_creator !== false);
    setChk('inspNotifyPm', insp.default_notify_pm !== false);
  }

  async function saveInspectionsForm(e) {
    e.preventDefault();
    const offsets = [];
    document.querySelectorAll('#inspReminderOffsets .insp-offset:checked').forEach((el) => offsets.push(el.value));
    const payload = {
      reminder_offsets: offsets.length ? offsets : ['morning_of', '1h'],
      notify_creator: document.getElementById('inspNotifyCreator')?.checked,
      default_notify_pm: document.getElementById('inspNotifyPm')?.checked,
    };
    await api('/api/program-settings/inspections', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Inspection defaults saved.', 'success');
  }

  async function loadNotificationsForm() {
    const json = await api('/api/program-settings/notifications');
    const n = json.notifications || {};
    const catalog = json.modules_catalog || [];
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    setChk('notifEmailEnabled', n.email_enabled !== false);
    setChk('notifInAppEnabled', n.in_app_enabled !== false);
    const digest = document.getElementById('notifDigest');
    if (digest) digest.value = n.digest || 'immediate';
    setChk('notifQuietHours', n.quiet_hours_enabled);
    const qs = document.getElementById('notifQuietStart');
    const qe = document.getElementById('notifQuietEnd');
    if (qs) qs.value = n.quiet_hours_start || '22:00';
    if (qe) qe.value = n.quiet_hours_end || '07:00';
    setChk('notifWeekendDigest', n.weekend_digest_only);
    const modules = n.modules || {};
    const tbody = document.getElementById('notifModulesTable');
    if (tbody) {
      tbody.innerHTML = catalog.map((row) => `
        <tr data-mod-key="${row.key}">
          <td class="py-2 px-2 text-zinc-300">${escapeHtml(row.label)}</td>
          <td class="py-2 px-2">
            <select class="notif-mod-mode bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-xs">
              <option value="both" ${modules[row.key] === 'both' ? 'selected' : ''}>In-app + email</option>
              <option value="in_app" ${modules[row.key] === 'in_app' ? 'selected' : ''}>In-app only</option>
              <option value="email" ${modules[row.key] === 'email' ? 'selected' : ''}>Email only</option>
              <option value="none" ${modules[row.key] === 'none' ? 'selected' : ''}>None</option>
            </select>
          </td>
        </tr>`).join('');
    }
  }

  async function saveNotificationsForm(e) {
    e.preventDefault();
    const modules = {};
    document.querySelectorAll('#notifModulesTable tr[data-mod-key]').forEach((tr) => {
      modules[tr.dataset.modKey] = tr.querySelector('.notif-mod-mode')?.value || 'both';
    });
    const payload = {
      email_enabled: document.getElementById('notifEmailEnabled')?.checked,
      in_app_enabled: document.getElementById('notifInAppEnabled')?.checked,
      digest: document.getElementById('notifDigest')?.value || 'immediate',
      quiet_hours_enabled: document.getElementById('notifQuietHours')?.checked,
      quiet_hours_start: document.getElementById('notifQuietStart')?.value || '22:00',
      quiet_hours_end: document.getElementById('notifQuietEnd')?.value || '07:00',
      weekend_digest_only: document.getElementById('notifWeekendDigest')?.checked,
      modules,
    };
    await api('/api/program-settings/notifications', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Notification defaults saved.', 'success');
  }

  async function loadRegionalForm() {
    const json = await api('/api/program-settings/regional');
    const r = json.regional || {};
    const localeSel = document.getElementById('regLocale');
    if (localeSel && !localeSel.options.length) {
      (json.locale_options || []).forEach(([val, label]) => localeSel.add(new Option(label, val)));
    }
    const dateSel = document.getElementById('regDateFormat');
    if (dateSel && !dateSel.options.length) {
      (json.date_format_options || []).forEach(([val, label]) => dateSel.add(new Option(label, val)));
    }
    if (localeSel) localeSel.value = r.default_locale || 'en-US';
    if (dateSel) dateSel.value = r.default_date_format || 'MDY';
    const tz = document.getElementById('regTimezone');
    if (tz) tz.value = r.default_timezone || 'America/New_York';
  }

  async function saveRegionalForm(e) {
    e.preventDefault();
    const payload = {
      default_locale: document.getElementById('regLocale')?.value || 'en-US',
      default_date_format: document.getElementById('regDateFormat')?.value || 'MDY',
      default_timezone: document.getElementById('regTimezone')?.value || 'America/New_York',
    };
    await api('/api/program-settings/regional', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Regional defaults saved.', 'success');
  }

  async function loadWorkflowForm() {
    const { workflow: w } = await api('/api/program-settings/workflow');
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    setChk('wfDailyWeather', w.require_daily_log_weather);
    setChk('wfDailyManpower', w.require_manpower_on_daily_log);
    set('wfDefaultRole', w.default_new_user_role || 'Company User');
    set('wfDefaultLicense', w.default_license_tier || '');
    set('wfArchiveDays', w.auto_archive_inactive_users_days || 0);
  }

  async function saveWorkflowForm(e) {
    e.preventDefault();
    const payload = {
      require_daily_log_weather: document.getElementById('wfDailyWeather')?.checked,
      require_manpower_on_daily_log: document.getElementById('wfDailyManpower')?.checked,
      default_new_user_role: document.getElementById('wfDefaultRole')?.value || 'Company User',
      default_license_tier: document.getElementById('wfDefaultLicense')?.value || '',
      auto_archive_inactive_users_days: parseInt(document.getElementById('wfArchiveDays')?.value || '0', 10),
    };
    await api('/api/program-settings/workflow', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Workflow defaults saved.', 'success');
  }

  function integrationStatusBadge(ok, label) {
    const cls = ok ? 'text-emerald-400' : 'text-zinc-500';
    const icon = ok ? 'fa-circle-check' : 'fa-circle-xmark';
    return `<span class="${cls}"><i class="fa-solid ${icon} mr-1"></i>${escapeHtml(label)}</span>`;
  }

  async function loadIntegrationsPanel() {
    const host = document.getElementById('integrationsStatusBody');
    if (!host) return;
    try {
      const json = await api('/api/program-settings/integrations');
      const i = json.integrations || {};
      const sage = json.sage || {};
      const aia = i.aia || {};
      const docusign = i.docusign || {};
      host.innerHTML = `
        <div class="settings-card">
          <div class="font-medium text-white mb-2">Sage 300 CRE</div>
          <div class="space-y-1 text-xs">
            <div>Database: <span class="text-zinc-300 font-mono">${escapeHtml(sage.sage_database || '—')}</span></div>
            <div>Company: <span class="text-zinc-300 font-mono">${escapeHtml(sage.sage_company_code || '—')}</span></div>
            <div class="mt-2">${integrationStatusBadge(i.sage_api_url_set, 'API URL configured')}</div>
            <div>${integrationStatusBadge(i.sage_api_key_set, 'API key configured')}</div>
            <div class="mt-1">${integrationStatusBadge(i.sage_live, 'Live connection ready')}</div>
          </div>
        </div>
        <div class="settings-card">
          <div class="font-medium text-white mb-2">DocuSign</div>
          <div class="text-xs">${integrationStatusBadge(docusign.configured, docusign.configured ? 'Configured' : 'Not configured')}</div>
          ${docusign.base_url ? `<div class="text-xs text-zinc-500 mt-1">${escapeHtml(docusign.base_url)}</div>` : ''}
        </div>
        <div class="settings-card">
          <div class="font-medium text-white mb-2">AIA Billing</div>
          <div class="text-xs">${integrationStatusBadge(aia.catina?.configured, aia.catina?.configured ? 'Catina configured' : 'Not configured')}</div>
        </div>
        <div class="settings-card">
          <div class="font-medium text-white mb-2">Security</div>
          <div class="space-y-1 text-xs">
            <div>${integrationStatusBadge(i.secret_key_from_env, 'Secret key from environment')}</div>
            <div class="text-zinc-500">Deployment: ${escapeHtml(i.deployment_env || 'default')}</div>
          </div>
        </div>`;
    } catch (err) {
      host.innerHTML = `<div class="settings-card text-red-400">Could not load: ${escapeHtml(err.message)}</div>`;
    }
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

  async function loadSecurityForm() {
    const { security: s } = await api('/api/program-settings/security');
    const set = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
    const setChk = (id, val) => { const el = document.getElementById(id); if (el) el.checked = !!val; };
    set('session_timeout_minutes', s.session_timeout_minutes);
    set('warn_before_logout_minutes', s.warn_before_logout_minutes);
    set('max_login_attempts', s.max_login_attempts);
    set('lockout_minutes', s.lockout_minutes);
    setChk('require_strong_passwords', s.require_strong_passwords);
    setChk('require_2fa_for_admins', s.require_2fa_for_admins);
    setChk('enforce_project_membership', s.enforce_project_membership);
    set('deployment_mode', s.deployment_mode || 'on_prem');
    set('allowed_hosts', s.allowed_hosts || '');
    setChk('behind_reverse_proxy', s.behind_reverse_proxy);
    setChk('force_https', s.force_https);
    setChk('trust_x_forwarded_proto', s.trust_x_forwarded_proto);
    set('hsts_max_age', s.hsts_max_age || 0);
    set('session_cookie_hours', s.session_cookie_hours || 12);
    loadSecurityAuditSummary();
  }

  async function loadSecurityAuditSummary() {
    const host = document.getElementById('securityAuditSummary');
    if (!host) return;
    try {
      const json = await api('/api/audit-log/security-summary');
      const c = json.summary?.counts || {};
      const recent = json.summary?.recent || [];
      const lines = recent.slice(0, 8).map((e) => {
        const t = (e.timestamp || '').replace('T', ' ').slice(0, 19);
        return `<div class="py-1 border-b border-zinc-800"><span class="text-zinc-500">${escapeHtml(t)}</span> <span class="text-amber-300">${escapeHtml(e.action || '')}</span> — ${escapeHtml(e.detail || e.user_email || '')}</div>`;
      }).join('');
      host.innerHTML = `
        <div class="grid grid-cols-3 gap-3 mb-4 text-center">
          <div class="bg-zinc-950 rounded p-2"><div class="text-lg font-semibold text-red-400">${c.failed_logins || 0}</div><div class="text-xs">Failed logins</div></div>
          <div class="bg-zinc-950 rounded p-2"><div class="text-lg font-semibold text-amber-400">${c.twofa_failures || 0}</div><div class="text-xs">2FA failures</div></div>
          <div class="bg-zinc-950 rounded p-2"><div class="text-lg font-semibold text-orange-400">${c.csrf_blocked || 0}</div><div class="text-xs">CSRF blocks</div></div>
        </div>
        ${lines || '<p class="text-zinc-500">No security events yet.</p>'}`;
    } catch (err) {
      host.textContent = 'Could not load security summary.';
    }
  }

  async function saveSecurityForm(e) {
    if (e) e.preventDefault();
    const payload = {
      session_timeout_minutes: parseInt(document.getElementById('session_timeout_minutes')?.value || '60', 10),
      warn_before_logout_minutes: parseInt(document.getElementById('warn_before_logout_minutes')?.value || '5', 10),
      max_login_attempts: parseInt(document.getElementById('max_login_attempts')?.value || '8', 10),
      lockout_minutes: parseInt(document.getElementById('lockout_minutes')?.value || '15', 10),
      require_strong_passwords: document.getElementById('require_strong_passwords')?.checked,
      require_2fa_for_admins: document.getElementById('require_2fa_for_admins')?.checked,
      enforce_project_membership: document.getElementById('enforce_project_membership')?.checked,
      deployment_mode: document.getElementById('deployment_mode')?.value || 'on_prem',
      allowed_hosts: document.getElementById('allowed_hosts')?.value?.trim() || '',
      behind_reverse_proxy: document.getElementById('behind_reverse_proxy')?.checked,
      force_https: document.getElementById('force_https')?.checked,
      trust_x_forwarded_proto: document.getElementById('trust_x_forwarded_proto')?.checked,
      hsts_max_age: parseInt(document.getElementById('hsts_max_age')?.value || '0', 10),
      session_cookie_hours: parseInt(document.getElementById('session_cookie_hours')?.value || '12', 10),
    };
    if (payload.deployment_mode === 'cloud') {
      payload.behind_reverse_proxy = true;
      if (!payload.trust_x_forwarded_proto) payload.trust_x_forwarded_proto = true;
    }
    await api('/api/program-settings/security', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    CasePMDialog?.alert('Security settings saved. Restart the server if you changed HTTPS/proxy options.', 'success');
  }

  global.CasePMProgramSettings = {
    loadCompanyForm, saveCompanyForm, loadBackupForm, saveBackupForm,
    runBackupNow, refreshBackupList, chooseBackupToInstall, installBackup,
    uploadBackupFile, updateCloudProviderFields,
    setSageMode, testSageConnection,
    syncEmailFromServer, pushEmailToServer,
    loadNumberingForm, saveNumberingForm, loadPayAppsForm, savePayAppsForm,
    loadPayAppDefaultsForModule, loadSecurityForm, saveSecurityForm,
    loadDocumentsForm, saveDocumentsForm,
    loadEstimatingForm, saveEstimatingForm,
    loadInspectionsForm, saveInspectionsForm,
    loadNotificationsForm, saveNotificationsForm,
    loadRegionalForm, saveRegionalForm,
    loadWorkflowForm, saveWorkflowForm,
    loadIntegrationsPanel,
  };
})(window);
