/**
 * Shared email settings UI — used by Email page modal and Program Settings tab
 */
(function (global) {
  'use strict';

  const S = () => global.CasePMEmail?.getSettings?.() || global.CasePMEmailSettings || {};

  let lastContainerId = 'emailSettingsModalBody';

  function escText(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function loadSignatures() {
    if (global.CasePMEmail?.getSignatures) return global.CasePMEmail.getSignatures();
    try {
      return JSON.parse(localStorage.getItem('casepm_email_signatures') || '[]');
    } catch { return []; }
  }

  function renderSignatureRows(sigs, defaultId) {
    if (!sigs.length) {
      return `<p class="text-sm text-zinc-500">No signatures yet. Add one below.</p>`;
    }
    return sigs.map(sig => `
      <div class="border border-zinc-700 rounded-lg p-3 mb-3 bg-zinc-800/40" data-sig-id="${escText(sig.id)}">
        <div class="flex items-center gap-2 mb-2">
          <input type="text" class="email-field-input es-sig-name flex-1" value="${escText(sig.name)}" placeholder="Signature name">
          <label class="flex items-center gap-1.5 text-xs text-zinc-400 whitespace-nowrap cursor-pointer">
            <input type="radio" name="es_defaultSignature" class="es-sig-default accent-emerald-600" value="${escText(sig.id)}" ${sig.id === defaultId ? 'checked' : ''}>
            Default
          </label>
          <button type="button" onclick="CasePMEmailSettingsUI.removeSignature('${escText(sig.id)}')" class="text-red-400 hover:text-red-300 text-xs px-2 py-1">Delete</button>
        </div>
        <textarea class="email-field-input es-sig-html font-mono text-xs" rows="6" placeholder="Signature HTML — e.g. &lt;p&gt;Best regards,&lt;/p&gt;&lt;p&gt;&lt;strong&gt;Your Name&lt;/strong&gt;&lt;/p&gt;">${escText(sig.html)}</textarea>
      </div>`).join('');
  }

  function field(id, label, inputHtml, hint) {
    return `<div><label class="email-field-label" for="${id}">${label}</label>${inputHtml}${hint ? `<p class="text-[10px] text-zinc-500 mt-1">${hint}</p>` : ''}</div>`;
  }

  function input(id, type, val, ph) {
    return `<input type="${type}" id="${id}" class="email-field-input" value="${val || ''}" placeholder="${ph || ''}">`;
  }

  function select(id, options, val) {
    return `<select id="${id}" class="email-field-input">${options.map(o => `<option value="${o.v}" ${o.v === val ? 'selected' : ''}>${o.t}</option>`).join('')}</select>`;
  }

  function checkbox(id, label, checked) {
    return `<label class="flex items-center gap-2 text-sm cursor-pointer"><input type="checkbox" id="${id}" class="accent-emerald-600" ${checked ? 'checked' : ''}> ${label}</label>`;
  }

  function section(title, body) {
    return `<div class="email-settings-section mb-4"><h3>${title}</h3>${body}</div>`;
  }

  function render(containerId) {
    lastContainerId = containerId || lastContainerId;
    const el = document.getElementById(lastContainerId);
    if (!el) return;
    const s = S();
    const sigs = loadSignatures();
    const defaultSigId = s.defaultSignatureId || (sigs[0] && sigs[0].id) || 'default';

    el.innerHTML = `
      <div class="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
        ${section('Account & Connection', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div class="md:col-span-2 flex flex-wrap gap-2">
              <button type="button" onclick="CasePMEmailSettingsUI.connectGoogle()" class="px-4 py-2 bg-white text-zinc-900 rounded-md text-sm font-medium"><i class="fa-brands fa-google mr-2"></i>Connect Google / Gmail</button>
              <button type="button" onclick="CasePMEmailSettingsUI.connectMicrosoft()" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-md text-sm font-medium"><i class="fa-brands fa-microsoft mr-2"></i>Connect Microsoft / Outlook</button>
              <button type="button" onclick="CasePMEmailSettingsUI.testConnection()" class="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-md text-sm">Test Connection</button>
            </div>
            ${field('es_displayName', 'Display Name', input('es_displayName', 'text', s.displayName))}
            ${field('es_emailAddress', 'Email Address', input('es_emailAddress', 'email', s.emailAddress))}
            ${field('es_replyTo', 'Reply-To Address', input('es_replyTo', 'email', s.replyTo))}
          </div>
        `)}

        ${section('Incoming Mail (IMAP / POP)', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${field('es_imapHost', 'IMAP Server', input('es_imapHost', 'text', s.imapHost, 'imap.gmail.com'))}
            ${field('es_imapPort', 'IMAP Port', input('es_imapPort', 'number', s.imapPort))}
            <div class="md:col-span-2">${checkbox('es_imapSsl', 'Use SSL/TLS for IMAP', s.imapSsl)}</div>
            ${field('es_popHost', 'POP Server (optional)', input('es_popHost', 'text', s.popHost, 'pop.gmail.com'))}
            ${field('es_popPort', 'POP Port', input('es_popPort', 'number', s.popPort))}
          </div>
        `)}

        ${section('Outgoing Mail (SMTP)', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${field('es_smtpHost', 'SMTP Server', input('es_smtpHost', 'text', s.smtpHost, 'smtp.gmail.com'))}
            ${field('es_smtpPort', 'SMTP Port', input('es_smtpPort', 'number', s.smtpPort))}
            ${field('es_smtpUser', 'SMTP Username', input('es_smtpUser', 'text', s.smtpUser))}
            ${field('es_smtpPassword', 'SMTP Password / App Password', input('es_smtpPassword', 'password', s.smtpPassword))}
            <div class="md:col-span-2">${checkbox('es_smtpTls', 'Use STARTTLS', s.smtpTls)}</div>
          </div>
        `)}

        ${section('Sync & Offline', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${field('es_syncFrequency', 'Sync Frequency', select('es_syncFrequency', [{v:'push',t:'Push (real-time)'},{v:'15',t:'Every 15 min'},{v:'30',t:'Every 30 min'},{v:'60',t:'Hourly'}], s.syncFrequency))}
            ${field('es_syncDays', 'Sync mail from last (days)', input('es_syncDays', 'number', s.syncDays))}
            <div class="md:col-span-2">${checkbox('es_offlineMode', 'Enable offline mode (cache mail locally)', s.offlineMode)}</div>
          </div>
        `)}

        ${section('Inbox Experience (Outlook + Gmail)', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            ${checkbox('es_conversationView', 'Conversation view / threading', s.conversationView)}
            ${checkbox('es_focusedInbox', 'Focused Inbox (Outlook-style)', s.focusedInbox)}
            ${checkbox('es_gmailCategories', 'Gmail categories (Primary, Social, Promotions…)', s.gmailCategories)}
            ${checkbox('es_smartCompose', 'Smart Compose suggestions', s.smartCompose)}
            ${checkbox('es_nudges', 'Nudges — remind to reply/follow up', s.nudges)}
            ${checkbox('es_snoozeSuggestions', 'Snooze suggestions', s.snoozeSuggestions)}
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
            ${field('es_previewPane', 'Reading pane', select('es_previewPane', [{v:'right',t:'Right'},{v:'bottom',t:'Bottom'},{v:'off',t:'Off'}], s.previewPane))}
            ${field('es_density', 'Density', select('es_density', [{v:'comfortable',t:'Comfortable'},{v:'compact',t:'Compact'}], s.density))}
            ${field('es_undoSendSeconds', 'Undo send window (seconds)', input('es_undoSendSeconds', 'number', s.undoSendSeconds))}
          </div>
        `)}

        ${section('Compose & Send', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            ${checkbox('es_defaultReplyAll', 'Default to Reply All', s.defaultReplyAll)}
            ${checkbox('es_markAsReadOnView', 'Mark as read when opened', s.markAsReadOnView)}
            ${checkbox('es_confirmPermanentDelete', 'Confirm permanent delete', s.confirmPermanentDelete)}
            ${checkbox('es_requestReadReceipts', 'Request read receipts (Outlook)', s.requestReadReceipts)}
            ${checkbox('es_requestDeliveryReceipts', 'Request delivery receipts (Outlook)', s.requestDeliveryReceipts)}
            ${checkbox('es_confidentialModeDefault', 'Confidential mode by default (Gmail-style)', s.confidentialModeDefault)}
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            ${field('es_delayDeliveryDefault', 'Default delay delivery (minutes, 0=off)', input('es_delayDeliveryDefault', 'number', s.delayDeliveryDefault))}
            ${field('es_swipeActions', 'Swipe actions (mobile)', select('es_swipeActions', [{v:'archive_delete',t:'Archive / Delete'},{v:'read_archive',t:'Read / Archive'},{v:'flag_delete',t:'Flag / Delete'}], s.swipeActions))}
          </div>
        `)}

        ${section('Email Signatures', `
          <p class="text-xs text-zinc-500 mb-3">Signatures are appended when you compose a new message. Use HTML for formatting (name, title, phone, logo, etc.). The <strong class="text-zinc-300">Default</strong> signature is inserted automatically.</p>
          <div id="es_signaturesList">${renderSignatureRows(sigs, defaultSigId)}</div>
          <button type="button" onclick="CasePMEmailSettingsUI.addSignature()" class="mt-1 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md text-sm text-zinc-200">
            <i class="fa-solid fa-plus mr-1"></i> Add Signature
          </button>
          <p class="text-[10px] text-zinc-500 mt-3">Tip: Drawn signatures for PDFs and submittals are managed separately under <strong class="text-zinc-400">User Management → Signature &amp; Certificate</strong>.</p>
        `)}

        ${section('Vacation Responder / Out of Office', `
          <div class="mb-3">${checkbox('es_vacationEnabled', 'Enable vacation auto-reply', s.vacationEnabled)}</div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${field('es_vacationStart', 'Start date', input('es_vacationStart', 'date', s.vacationStart))}
            ${field('es_vacationEnd', 'End date', input('es_vacationEnd', 'date', s.vacationEnd))}
            <div class="md:col-span-2">${field('es_vacationMessage', 'Auto-reply message', `<textarea id="es_vacationMessage" rows="3" class="email-field-input">${s.vacationMessage || ''}</textarea>`)}</div>
            <div class="md:col-span-2">${checkbox('es_vacationInternalOnly', 'Internal auto-reply only (Case PM)', s.vacationInternalOnly)}</div>
          </div>
        `)}

        ${section('Junk, Blocked & Safe Senders', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${field('es_junkLevel', 'Junk filtering level', select('es_junkLevel', [{v:'low',t:'Low'},{v:'standard',t:'Standard'},{v:'high',t:'High'},{v:'strict',t:'Strict'}], s.junkLevel))}
            <div>${checkbox('es_blockRemoteImages', 'Block remote images (privacy)', s.blockRemoteImages)}</div>
          </div>
          <p class="text-xs text-zinc-500 mt-2">Manage blocked and safe senders from the Mail toolbar → Report / Settings.</p>
        `)}

        ${section('Delegation & Shared Mailboxes (Outlook)', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${field('es_sharedMailboxes', 'Shared mailboxes (comma-separated)', input('es_sharedMailboxes', 'text', (s.sharedMailboxes || []).join(', '), 'estimating@casepm.com, safety@casepm.com'))}
            ${field('es_delegates', 'Delegates who can send on your behalf', input('es_delegates', 'text', (s.delegates || []).join(', ')))}
            ${field('es_sendAsAddresses', 'Send As addresses', input('es_sendAsAddresses', 'text', (s.sendAsAddresses || []).join(', ')))}
          </div>
        `)}

        ${section('Internal Communications (Case PM)', `
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            ${checkbox('es_internalNotifications', 'Route module alerts to Internal tab', s.internalNotifications)}
            ${checkbox('es_approvalRouting', 'Send approvals to Internal → Approvals', s.approvalRouting)}
            ${checkbox('es_projectScopedInternal', 'Scope internal messages by active project', s.projectScopedInternal)}
          </div>
          <p class="text-xs text-zinc-500 mt-2">Approvals, @mentions, schedule/budget alerts, and team messages appear in the Internal workspace.</p>
        `)}

        ${section('Keyboard & Accessibility', `
          <div class="text-xs text-zinc-400 space-y-1">
            ${checkbox('es_keyboardShortcuts', 'Enable keyboard shortcuts', s.keyboardShortcuts)}
            <p class="mt-2"><strong class="text-zinc-300">Shortcuts:</strong> C = Compose · R = Reply · E = Archive · # = Delete · / = Search</p>
          </div>
        `)}

        <div class="flex justify-end gap-3 pt-2">
          <button type="button" onclick="CasePMEmailSettingsUI.save()" class="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-semibold text-white">Save Email Settings</button>
        </div>
      </div>`;
  }

  function collectSignatures() {
    const rows = document.querySelectorAll('#es_signaturesList [data-sig-id]');
    return [...rows].map(row => ({
      id: row.dataset.sigId,
      name: row.querySelector('.es-sig-name')?.value?.trim() || 'Signature',
      html: row.querySelector('.es-sig-html')?.value || '',
    }));
  }

  function collectDefaultSignatureId() {
    const checked = document.querySelector('input.es-sig-default:checked');
    if (checked) return checked.value;
    const sigs = collectSignatures();
    return sigs[0]?.id || 'default';
  }

  function collect() {
    const g = (id) => document.getElementById(id);
    const cb = (id) => g(id)?.checked ?? false;
    const val = (id) => g(id)?.value ?? '';
    const splitList = (id) => val(id).split(',').map(s => s.trim()).filter(Boolean);
    return {
      displayName: val('es_displayName'),
      emailAddress: val('es_emailAddress'),
      replyTo: val('es_replyTo'),
      imapHost: val('es_imapHost'),
      imapPort: Number(val('es_imapPort')) || 993,
      imapSsl: cb('es_imapSsl'),
      popHost: val('es_popHost'),
      popPort: Number(val('es_popPort')) || 995,
      smtpHost: val('es_smtpHost'),
      smtpPort: Number(val('es_smtpPort')) || 587,
      smtpTls: cb('es_smtpTls'),
      smtpUser: val('es_smtpUser'),
      smtpPassword: val('es_smtpPassword'),
      syncFrequency: val('es_syncFrequency'),
      syncDays: Number(val('es_syncDays')) || 90,
      offlineMode: cb('es_offlineMode'),
      conversationView: cb('es_conversationView'),
      focusedInbox: cb('es_focusedInbox'),
      gmailCategories: cb('es_gmailCategories'),
      smartCompose: cb('es_smartCompose'),
      nudges: cb('es_nudges'),
      snoozeSuggestions: cb('es_snoozeSuggestions'),
      previewPane: val('es_previewPane'),
      density: val('es_density'),
      undoSendSeconds: Number(val('es_undoSendSeconds')) || 10,
      defaultReplyAll: cb('es_defaultReplyAll'),
      markAsReadOnView: cb('es_markAsReadOnView'),
      confirmPermanentDelete: cb('es_confirmPermanentDelete'),
      requestReadReceipts: cb('es_requestReadReceipts'),
      requestDeliveryReceipts: cb('es_requestDeliveryReceipts'),
      confidentialModeDefault: cb('es_confidentialModeDefault'),
      delayDeliveryDefault: Number(val('es_delayDeliveryDefault')) || 0,
      swipeActions: val('es_swipeActions'),
      vacationEnabled: cb('es_vacationEnabled'),
      vacationStart: val('es_vacationStart'),
      vacationEnd: val('es_vacationEnd'),
      vacationMessage: val('es_vacationMessage'),
      vacationInternalOnly: cb('es_vacationInternalOnly'),
      junkLevel: val('es_junkLevel'),
      blockRemoteImages: cb('es_blockRemoteImages'),
      sharedMailboxes: splitList('es_sharedMailboxes'),
      delegates: splitList('es_delegates'),
      sendAsAddresses: splitList('es_sendAsAddresses'),
      internalNotifications: cb('es_internalNotifications'),
      approvalRouting: cb('es_approvalRouting'),
      projectScopedInternal: cb('es_projectScopedInternal'),
      keyboardShortcuts: cb('es_keyboardShortcuts'),
      defaultSignatureId: collectDefaultSignatureId(),
    };
  }

  function saveSignaturesFromUI() {
    const sigs = collectSignatures();
    if (global.CasePMEmail?.saveSignatures) global.CasePMEmail.saveSignatures(sigs);
    else localStorage.setItem('casepm_email_signatures', JSON.stringify(sigs));
    return sigs;
  }

  function addSignature() {
    const sigs = collectSignatures();
    sigs.push({
      id: 'sig_' + Date.now().toString(36),
      name: 'New Signature',
      html: '<p>Best regards,</p>\n<p><strong>Your Name</strong><br>Your Title<br>your.email@company.com</p>',
    });
    if (global.CasePMEmail?.saveSignatures) global.CasePMEmail.saveSignatures(sigs);
    else localStorage.setItem('casepm_email_signatures', JSON.stringify(sigs));
    render(lastContainerId);
  }

  function removeSignature(id) {
    let sigs = collectSignatures().filter(s => s.id !== id);
    if (!sigs.length) {
      sigs = [{ id: 'default', name: 'Default', html: '<p>Best regards,</p>' }];
    }
    if (global.CasePMEmail?.saveSignatures) global.CasePMEmail.saveSignatures(sigs);
    else localStorage.setItem('casepm_email_signatures', JSON.stringify(sigs));
    const s = S();
    if (s.defaultSignatureId === id) {
      const patch = { defaultSignatureId: sigs[0].id };
      if (global.CasePMEmail) global.CasePMEmail.saveSettings(patch);
      else global.CasePMEmailSettings = { ...S(), ...patch };
    }
    render(lastContainerId);
  }

  function save() {
    saveSignaturesFromUI();
    const data = collect();
    const merged = { ...S(), ...data };
    localStorage.setItem('casepm_email_settings', JSON.stringify(merged));
    if (global.CasePMEmail) global.CasePMEmail.saveSettings(data);
    else global.CasePMEmailSettings = merged;
    pushEmailToServer(merged);
    global.dispatchEvent(new CustomEvent('casepm-email-settings-changed', { detail: merged }));
    alert('Email settings saved and synced with Program Settings.');
    if (global.CasePMEmail) global.CasePMEmail.refresh?.();
  }

  async function pushEmailToServer(settings) {
    try {
      await fetch('/api/program-settings/email', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
    } catch (_) { /* admin may be offline */ }
  }

  async function loadFromServer() {
    try {
      const res = await fetch('/api/program-settings/email', { credentials: 'same-origin' });
      if (!res.ok) return null;
      const json = await res.json();
      const email = json.email;
      if (email && typeof email === 'object' && Object.keys(email).length) {
        localStorage.setItem('casepm_email_settings', JSON.stringify(email));
        if (global.CasePMEmail) global.CasePMEmail.saveSettings(email);
        else global.CasePMEmailSettings = email;
        return email;
      }
    } catch (_) {}
    return null;
  }

  async function ensureLoaded() {
    const server = await loadFromServer();
    if (!server) {
      const local = loadFromStorage();
      if (local && Object.keys(local).length) {
        if (global.CasePMEmail) global.CasePMEmail.saveSettings(local);
        else global.CasePMEmailSettings = { ...S(), ...local };
      }
    }
    return S();
  }

  function connectGoogle() {
    alert('Google OAuth connection will open in production. For now, enter IMAP/SMTP credentials below and save.');
  }

  function connectMicrosoft() {
    alert('Microsoft 365 OAuth connection will open in production. For now, enter SMTP/IMAP credentials below and save.');
  }

  function testConnection() {
    const s = collect();
    if (!s.smtpHost && !s.imapHost) { alert('Enter at least SMTP or IMAP server details.'); return; }
    alert(`Connection test simulated OK for ${s.emailAddress || 'account'}.\nSMTP: ${s.smtpHost}:${s.smtpPort}\nIMAP: ${s.imapHost || '—'}:${s.imapPort}`);
  }

  function loadFromStorage() {
    try {
      return JSON.parse(localStorage.getItem('casepm_email_settings') || '{}');
    } catch { return {}; }
  }

  global.CasePMEmailSettingsUI = {
    render, save, collect, addSignature, removeSignature,
    connectGoogle, connectMicrosoft, testConnection,
    loadFromStorage, loadFromServer, ensureLoaded, pushEmailToServer,
  };

  global.addEventListener('casepm-email-settings-changed', (ev) => {
    if (ev.detail && document.getElementById(lastContainerId)) {
      if (global.CasePMEmail) global.CasePMEmail.saveSettings(ev.detail);
      else global.CasePMEmailSettings = ev.detail;
      render(lastContainerId);
    }
  });
})(window);
