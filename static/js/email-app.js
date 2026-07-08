/**
 * Case PM Email Client — Outlook + Gmail feature parity (UI layer)
 * Settings sync with Program Settings via localStorage key casepm_email_settings
 */
(function (global) {
  'use strict';

  const STORAGE = {
    settings: 'casepm_email_settings',
    mail: 'casepm_email_messages',
    internal: 'casepm_email_internal',
    contacts: 'casepm_email_contacts',
    rules: 'casepm_email_rules',
    signatures: 'casepm_email_signatures',
    templates: 'casepm_email_templates',
    blocked: 'casepm_email_blocked',
    safe: 'casepm_email_safe_senders',
    customFolders: 'casepm_email_custom_folders',
  };

  const MAIL_FOLDERS = [
    { id: 'inbox', label: 'Inbox', icon: 'fa-inbox' },
    { id: 'focused', label: 'Focused', icon: 'fa-bullseye', outlook: true },
    { id: 'other', label: 'Other', icon: 'fa-layer-group', outlook: true },
    { id: 'starred', label: 'Starred', icon: 'fa-star' },
    { id: 'snoozed', label: 'Snoozed', icon: 'fa-clock' },
    { id: 'sent', label: 'Sent', icon: 'fa-paper-plane' },
    { id: 'drafts', label: 'Drafts', icon: 'fa-file-pen' },
    { id: 'scheduled', label: 'Scheduled', icon: 'fa-calendar-clock' },
    { id: 'archive', label: 'Archive', icon: 'fa-box-archive' },
    { id: 'spam', label: 'Spam', icon: 'fa-shield-virus' },
    { id: 'trash', label: 'Trash', icon: 'fa-trash' },
  ];

  const GMAIL_CATEGORIES = [
    { id: 'primary', label: 'Primary', icon: 'fa-inbox' },
    { id: 'social', label: 'Social', icon: 'fa-users' },
    { id: 'promotions', label: 'Promotions', icon: 'fa-tag' },
    { id: 'updates', label: 'Updates', icon: 'fa-bell' },
    { id: 'forums', label: 'Forums', icon: 'fa-comments' },
  ];

  const INTERNAL_FOLDERS = [
    { id: 'internal-inbox', label: 'Inbox', icon: 'fa-inbox' },
    { id: 'approvals', label: 'Approvals', icon: 'fa-circle-check' },
    { id: 'alerts', label: 'Alerts', icon: 'fa-triangle-exclamation' },
    { id: 'team', label: 'Team Messages', icon: 'fa-people-group' },
    { id: 'mentions', label: 'Mentions', icon: 'fa-at' },
    { id: 'announcements', label: 'Announcements', icon: 'fa-bullhorn' },
    { id: 'action-required', label: 'Action Required', icon: 'fa-hand-pointer' },
    { id: 'fyi', label: 'FYI', icon: 'fa-circle-info' },
    { id: 'internal-archive', label: 'Archive', icon: 'fa-box-archive' },
  ];

  const DEFAULT_SETTINGS = {
    provider: 'none',
    googleConnected: false,
    microsoftConnected: false,
    displayName: '',
    emailAddress: '',
    replyTo: '',
    imapHost: '',
    imapPort: 993,
    imapSsl: true,
    popHost: '',
    popPort: 995,
    smtpHost: 'smtp.gmail.com',
    smtpPort: 587,
    smtpTls: true,
    smtpUser: '',
    smtpPassword: '',
    syncFrequency: 'push',
    syncDays: 90,
    conversationView: true,
    focusedInbox: true,
    gmailCategories: true,
    previewPane: 'right',
    density: 'comfortable',
    undoSendSeconds: 10,
    defaultReplyAll: false,
    markAsReadOnView: true,
    confirmPermanentDelete: true,
    requestReadReceipts: false,
    requestDeliveryReceipts: false,
    delayDeliveryDefault: 0,
    vacationEnabled: false,
    vacationMessage: '',
    vacationStart: '',
    vacationEnd: '',
    vacationInternalOnly: false,
    junkLevel: 'standard',
    blockRemoteImages: false,
    confidentialModeDefault: false,
    smartCompose: true,
    nudges: true,
    snoozeSuggestions: true,
    swipeActions: 'archive_delete',
    keyboardShortcuts: true,
    offlineMode: false,
    sharedMailboxes: [],
    delegates: [],
    sendAsAddresses: [],
    defaultSignatureId: 'default',
    internalNotifications: true,
    approvalRouting: true,
    projectScopedInternal: true,
  };

  let state = {
    workspace: 'mail',
    folder: 'inbox',
    category: null,
    selectedId: null,
    selectedIds: new Set(),
    search: '',
    searchAdvanced: null,
    sort: 'date_desc',
    settingsOpen: false,
    rulesOpen: false,
    contactsOpen: false,
    filterUnread: false,
    filterFlagged: false,
    filterAttachments: false,
    inlineCompose: null,
  };

  let mailMessages = [];
  let internalMessages = [];
  let settings = { ...DEFAULT_SETTINGS };
  let contacts = [];
  let rules = [];
  let signatures = [];
  let templates = [];
  let customFolders = [];
  let undoTimer = null;
  let ctx = { userName: 'User', userEmail: '', users: [], projectName: '' };

  function loadJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch { return fallback; }
  }

  function saveJson(key, data) {
    localStorage.setItem(key, JSON.stringify(data));
  }

  function uid() {
    return 'msg_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const sameYear = d.getFullYear() === now.getFullYear();
    return d.toLocaleDateString([], sameYear ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function toast(msg, type) {
    if (typeof showToast === 'function') showToast(msg, type);
    else if (typeof showAlertModal === 'function') showAlertModal(type === 'error' ? 'Error' : 'Notice', msg);
    else console.log('[Email]', msg);
  }

  function seedMail() {
    const now = Date.now();
    return [
      { id: uid(), folder: 'inbox', category: 'primary', focused: true, from: 'Sarah Chen', fromEmail: 'sarah.chen@aldistores.com', to: [ctx.userEmail || 'you@casepm.com'], subject: 'RE: Lakeland Store #447 — Submittal Log Review', preview: 'Please review the updated submittal package for metal panels...', body: '<p>Hi,</p><p>Please review the updated submittal package for metal panels. We need your approval by Friday.</p><p>Thanks,<br>Sarah</p>', date: new Date(now - 3600000).toISOString(), unread: true, starred: false, flagged: true, hasAttachments: true, attachments: [{ name: 'Submittal_Log_v3.pdf', size: '2.4 MB' }], labels: ['Projects'], threadId: 't1', importance: 'high', snoozedUntil: null, scheduledFor: null },
      { id: uid(), folder: 'inbox', category: 'primary', focused: true, from: 'Mike Johnson', fromEmail: 'mike.j@structureeng.com', to: [ctx.userEmail || 'you@casepm.com'], subject: 'RFI #142 — Foundation elevation clarification', preview: 'See attached sketch. Need response before pour schedule...', body: '<p>Team,</p><p>See attached sketch regarding foundation elevation at grid C-4.</p></p>', date: new Date(now - 7200000).toISOString(), unread: true, starred: true, flagged: false, hasAttachments: true, attachments: [{ name: 'RFI_142_Sketch.pdf', size: '890 KB' }], labels: ['RFIs'], threadId: 't2', importance: 'normal', snoozedUntil: null, scheduledFor: null },
      { id: uid(), folder: 'inbox', category: 'updates', focused: false, from: 'Procore Notifications', fromEmail: 'noreply@procore.com', to: [ctx.userEmail || 'you@casepm.com'], subject: 'Daily Digest — 3 items need your attention', preview: 'Change orders, daily log reminders, and overdue tasks...', body: '<p>Your daily project digest is ready.</p>', date: new Date(now - 86400000).toISOString(), unread: false, starred: false, flagged: false, hasAttachments: false, attachments: [], labels: [], threadId: 't3', importance: 'low', snoozedUntil: null, scheduledFor: null },
      { id: uid(), folder: 'sent', category: 'primary', focused: true, from: ctx.userName, fromEmail: ctx.userEmail || 'you@casepm.com', to: ['sarah.chen@aldistores.com'], subject: 'FW: Pay Application #4 — GC Review', preview: 'Attached is our marked-up pay app for your records...', body: '<p>Sarah,</p><p>Attached is our marked-up pay app.</p>', date: new Date(now - 172800000).toISOString(), unread: false, starred: false, flagged: false, hasAttachments: true, attachments: [{ name: 'PayApp4_Markup.pdf', size: '1.1 MB' }], labels: [], threadId: 't4', importance: 'normal', snoozedUntil: null, scheduledFor: null },
      { id: uid(), folder: 'drafts', category: 'primary', focused: true, from: ctx.userName, fromEmail: ctx.userEmail || 'you@casepm.com', to: [], subject: 'Weekly Owner Update — Week 24', preview: '(Draft) Progress this week includes...', body: '<p>Progress this week includes...</p>', date: new Date(now - 200000).toISOString(), unread: true, starred: false, flagged: false, hasAttachments: false, attachments: [], labels: [], threadId: 't5', importance: 'normal', snoozedUntil: null, scheduledFor: null, isDraft: true },
    ];
  }

  function seedInternal() {
    const now = Date.now();
    return [
      { id: uid(), folder: 'approvals', type: 'approval', from: 'Case PM System', fromUser: 'System', subject: 'Pay Application #4 requires your approval', preview: 'Subcontractor: ABC Electric — Amount: $48,250.00', body: '<p><strong>Pay Application #4</strong> from ABC Electric is ready for your review.</p><p>Amount: <strong>$48,250.00</strong></p><p>Project: Lakeland Store #447</p>', date: new Date(now - 1800000).toISOString(), unread: true, priority: 'high', actionUrl: '/pay-applications', actionLabel: 'Review Pay App', project: 'Lakeland Store #447', module: 'Pay Applications', requiresAction: true },
      { id: uid(), folder: 'approvals', type: 'approval', from: 'Jennifer Walsh', fromUser: 'Jennifer Walsh', subject: 'Change Order CO-017 pending PM approval', preview: 'Owner-directed CO for additional dock doors — $12,400', body: '<p>Please approve CO-017 for additional dock doors.</p>', date: new Date(now - 5400000).toISOString(), unread: true, priority: 'high', actionUrl: '/change-orders', actionLabel: 'Review CO', project: 'Lakeland Store #447', module: 'Change Orders', requiresAction: true },
      { id: uid(), folder: 'alerts', type: 'alert', from: 'Case PM System', fromUser: 'System', subject: 'Schedule baseline published', preview: 'Revision 03 was published by Tom Bradley', body: '<p>Schedule <strong>Rev 03</strong> was published.</p>', date: new Date(now - 10800000).toISOString(), unread: false, priority: 'normal', actionUrl: '/schedule', actionLabel: 'View Schedule', project: 'Lakeland Store #447', module: 'Schedule', requiresAction: false },
      { id: uid(), folder: 'team', type: 'message', from: 'Tom Bradley', fromUser: 'Tom Bradley', subject: 'Can you review the updated lookahead?', preview: 'I pushed changes to weeks 3-6. Let me know if the masonry...', body: '<p>Hey — I pushed changes to weeks 3-6 on the lookahead. Can you take a look when you get a chance?</p>', date: new Date(now - 14400000).toISOString(), unread: true, priority: 'normal', actionUrl: '/schedule', actionLabel: 'Open Schedule', project: 'Lakeland Store #447', module: 'Schedule', requiresAction: false },
      { id: uid(), folder: 'mentions', type: 'mention', from: 'Lisa Park', fromUser: 'Lisa Park', subject: '@you flagged in Submittal Log comment', preview: 'Lisa Park mentioned you: "Need PM sign-off on spec 07 42 13"', body: '<p>Lisa Park mentioned you on submittal <strong>07 42 13</strong>:</p><blockquote>Need PM sign-off before we send to architect.</blockquote>', date: new Date(now - 21600000).toISOString(), unread: true, priority: 'high', actionUrl: '/submittals', actionLabel: 'View Submittal', project: 'Lakeland Store #447', module: 'Submittals', requiresAction: true },
      { id: uid(), folder: 'announcements', type: 'announce', from: 'Case PM Admin', fromUser: 'Admin', subject: 'Company-wide: New safety briefing required', preview: 'All field staff must complete the Q3 safety module by July 15', body: '<p>All field staff must complete the Q3 safety briefing module by <strong>July 15</strong>.</p>', date: new Date(now - 43200000).toISOString(), unread: false, priority: 'normal', actionUrl: '/safety', actionLabel: 'Open Safety', project: 'All Projects', module: 'Safety', requiresAction: false },
      { id: uid(), folder: 'action-required', type: 'alert', from: 'Case PM System', fromUser: 'System', subject: 'RFI #138 overdue — response due today', preview: 'No response recorded. Architect is waiting.', body: '<p>RFI #138 is overdue. Response was due today.</p>', date: new Date(now - 28800000).toISOString(), unread: true, priority: 'high', actionUrl: '/rfis', actionLabel: 'Open RFI', project: 'Lakeland Store #447', module: 'RFIs', requiresAction: true },
    ];
  }

  function seedContacts() {
    return [
      { id: 'c1', name: 'Sarah Chen', email: 'sarah.chen@aldistores.com', company: 'ALDI', phone: '863-555-0142' },
      { id: 'c2', name: 'Mike Johnson', email: 'mike.j@structureeng.com', company: 'Structure Eng', phone: '863-555-0198' },
      { id: 'c3', name: 'Tom Bradley', email: 'tom.bradley@casepm.com', company: 'Case Construction', phone: '' },
      { id: 'c4', name: 'Jennifer Walsh', email: 'j.walsh@casepm.com', company: 'Case Construction', phone: '' },
    ];
  }

  function seedSignatures() {
    return [
      { id: 'default', name: 'Default', html: `<p>Best regards,</p><p><strong>${ctx.userName}</strong><br>Case Construction<br>${ctx.userEmail || 'you@casepm.com'}</p>` },
      { id: 'short', name: 'Short', html: `<p>— ${ctx.userName}</p>` },
    ];
  }

  function seedTemplates() {
    return [
      { id: 'tpl1', name: 'Weekly Owner Update', subject: 'Weekly Owner Update — Week {week}', body: '<p>Owner Team,</p><p>Progress this week:</p><ul><li></li></ul><p>Upcoming:</p><ul><li></li></ul>' },
      { id: 'tpl2', name: 'RFI Follow-up', subject: 'Follow-up: RFI #{number}', body: '<p>Following up on RFI #{number}. Please advise at your earliest convenience.</p>' },
    ];
  }

  function loadAll() {
    settings = { ...DEFAULT_SETTINGS, ...loadJson(STORAGE.settings, {}) };
    mailMessages = loadJson(STORAGE.mail, null) || seedMail();
    contacts = loadJson(STORAGE.contacts, null) || seedContacts();
    rules = loadJson(STORAGE.rules, []);
    signatures = loadJson(STORAGE.signatures, null) || seedSignatures();
    templates = loadJson(STORAGE.templates, null) || seedTemplates();
    customFolders = loadJson(STORAGE.customFolders, []);
    if (!loadJson(STORAGE.mail, null)) persistMail();
    internalMessages = [];
    refreshInternalFromServer();
  }

  async function refreshInternalFromServer() {
    try {
      const res = await fetch('/api/internal-messages');
      if (res.ok) {
        const data = await res.json();
        internalMessages = data.map(m => ({
          id: m.id,
          folder: m.folder,
          type: m.type,
          from: m.from,
          fromUser: m.fromUser,
          subject: m.subject,
          preview: m.preview,
          body: m.body,
          date: m.date,
          unread: m.unread,
          priority: m.priority,
          actionUrl: m.actionUrl,
          actionLabel: m.actionLabel,
          project: m.project,
          module: m.module,
          requiresAction: m.requiresAction,
          approvalId: m.approvalId,
          archived: m.archived,
        }));
        persistInternal();
        render();
        return;
      }
    } catch (e) {
      console.warn('Internal messages API unavailable, using cache', e);
    }
    internalMessages = loadJson(STORAGE.internal, null) || seedInternal();
    if (!loadJson(STORAGE.internal, null)) persistInternal();
    render();
  }

  function persistMail() { saveJson(STORAGE.mail, mailMessages); }
  function persistInternal() { saveJson(STORAGE.internal, internalMessages); }
  function persistSettings() { saveJson(STORAGE.settings, settings); global.CasePMEmailSettings = settings; }
  function persistCustomFolders() { saveJson(STORAGE.customFolders, customFolders); }

  function buildContactIndex() {
    const map = new Map();
    function add(name, email) {
      if (!email) return;
      const key = String(email).toLowerCase().trim();
      if (!key) return;
      if (!map.has(key)) map.set(key, { name: (name || '').trim() || email, email: key });
    }
    (ctx.users || []).forEach(u => add(u.name || u.full_name, u.email));
    try {
      const umUsers = loadJson('users', []);
      if (Array.isArray(umUsers)) umUsers.forEach(u => add(u.name || u.full_name, u.email));
    } catch { /* ignore */ }
    contacts.forEach(c => add(c.name, c.email));
    mailMessages.forEach(m => {
      add(m.from, m.fromEmail);
      (m.to || []).forEach(e => add('', e));
      (m.cc || []).forEach(e => add('', e));
      (m.bcc || []).forEach(e => add('', e));
    });
    return [...map.values()];
  }

  function filterContacts(query) {
    const q = (query || '').toLowerCase().trim();
    const all = buildContactIndex();
    if (!q) return all.slice(0, 12);
    return all.filter(c =>
      c.email.includes(q) || (c.name && c.name.toLowerCase().includes(q))
    ).slice(0, 12);
  }

  function folderCount(folderId, workspace) {
    if (workspace === 'internal') {
      if (folderId === 'internal-inbox') return internalMessages.filter(m => !m.archived && m.unread).length;
      return internalMessages.filter(m => m.folder === folderId && !m.archived && m.unread).length;
    }
    if (folderId === 'starred') return mailMessages.filter(m => m.starred && m.folder !== 'trash').length;
    if (folderId === 'snoozed') return mailMessages.filter(m => m.snoozedUntil && new Date(m.snoozedUntil) > new Date()).length;
    if (folderId === 'focused') return mailMessages.filter(m => m.folder === 'inbox' && m.focused).length;
    if (folderId === 'other') return mailMessages.filter(m => m.folder === 'inbox' && !m.focused).length;
    if (folderId.startsWith('custom_')) return mailMessages.filter(m => m.folder === folderId).length;
    return mailMessages.filter(m => m.folder === folderId && m.unread).length;
  }

  function activeMessages() {
    if (state.workspace === 'internal') {
      let list = internalMessages.filter(m => !m.archived);
      if (state.folder === 'internal-inbox') return list;
      if (state.folder === 'internal-archive') return internalMessages.filter(m => m.archived);
      return list.filter(m => m.folder === state.folder);
    }
    let list = mailMessages.filter(m => {
      if (state.folder === 'starred') return m.starred && m.folder !== 'trash';
      if (state.folder === 'snoozed') return m.snoozedUntil && new Date(m.snoozedUntil) > new Date();
      if (state.folder === 'focused') return m.folder === 'inbox' && m.focused;
      if (state.folder === 'other') return m.folder === 'inbox' && !m.focused;
      if (state.folder.startsWith('custom_')) return m.folder === state.folder;
      return m.folder === state.folder;
    });
    if (state.category && settings.gmailCategories) list = list.filter(m => m.category === state.category);
    if (state.filterUnread) list = list.filter(m => m.unread);
    if (state.filterFlagged) list = list.filter(m => m.flagged || m.starred);
    if (state.filterAttachments) list = list.filter(m => m.hasAttachments);
    if (state.search) {
      const q = state.search.toLowerCase();
      list = list.filter(m =>
        (m.subject || '').toLowerCase().includes(q) ||
        (m.from || '').toLowerCase().includes(q) ||
        (m.preview || '').toLowerCase().includes(q) ||
        (m.fromEmail || '').toLowerCase().includes(q)
      );
    }
    if (state.searchAdvanced) {
      const a = state.searchAdvanced;
      if (a.from) list = list.filter(m => (m.fromEmail || '').toLowerCase().includes(a.from.toLowerCase()));
      if (a.to) list = list.filter(m => (m.to || []).join(' ').toLowerCase().includes(a.to.toLowerCase()));
      if (a.subject) list = list.filter(m => (m.subject || '').toLowerCase().includes(a.subject.toLowerCase()));
      if (a.hasAttachment) list = list.filter(m => m.hasAttachments);
      if (a.unread) list = list.filter(m => m.unread);
    }
    list.sort((a, b) => {
      if (state.sort === 'date_asc') return new Date(a.date) - new Date(b.date);
      if (state.sort === 'subject') return (a.subject || '').localeCompare(b.subject || '');
      if (state.sort === 'from') return (a.from || '').localeCompare(b.from || '');
      return new Date(b.date) - new Date(a.date);
    });
    return list;
  }

  function getMessage(id) {
    const pool = state.workspace === 'internal' ? internalMessages : mailMessages;
    return pool.find(m => String(m.id) === String(id));
  }

  function render() {
    renderHeader();
    renderSidebar();
    renderMessageList();
    renderReadingPane();
    applyLayoutClasses();
  }

  function renderToolbarHTML() {
    const isMail = state.workspace === 'mail';
    const hasSel = state.selectedId || state.selectedIds.size > 0;
    return `
      <div class="flex items-center gap-1 flex-wrap">
        ${isMail ? `<button type="button" class="email-toolbar-btn" onclick="CasePMEmail.compose()"><i class="fa-solid fa-pen"></i> New</button>` : ''}
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.refresh()" title="Refresh"><i class="fa-solid fa-rotate"></i></button>
        ${isMail ? `
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.archiveSelected()"><i class="fa-solid fa-box-archive"></i> Archive</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.deleteSelected()"><i class="fa-solid fa-trash"></i> Delete</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.markReadToggle()"><i class="fa-solid fa-envelope-open"></i> Read/Unread</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.flagSelected()"><i class="fa-solid fa-flag"></i> Flag</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.starSelected()"><i class="fa-solid fa-star"></i> Star</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.snoozeSelected()"><i class="fa-solid fa-clock"></i> Snooze</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.moveSelected()"><i class="fa-solid fa-folder"></i> Move</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.labelSelected()"><i class="fa-solid fa-tag"></i> Label</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.reportPhishing()"><i class="fa-solid fa-shield"></i> Report</button>
        ` : `
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.markInternalRead()"><i class="fa-solid fa-check"></i> Mark Read</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.approveInternal()"><i class="fa-solid fa-circle-check"></i> Approve</button>
        <button type="button" class="email-toolbar-btn" ${hasSel ? '' : 'disabled'} onclick="CasePMEmail.dismissInternal()"><i class="fa-solid fa-xmark"></i> Dismiss</button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.composeInternal()"><i class="fa-solid fa-paper-plane"></i> New Message</button>
        `}
        <span class="w-px h-5 bg-zinc-700 mx-1"></span>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.toggleFilter('unread')"><i class="fa-solid fa-filter"></i> Unread</button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.showAdvancedSearch()"><i class="fa-solid fa-magnifying-glass-plus"></i> Advanced</button>
        ${isMail ? `<button type="button" class="email-toolbar-btn" onclick="CasePMEmail.showRules()"><i class="fa-solid fa-wand-magic-sparkles"></i> Rules</button>` : ''}
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.showContacts()"><i class="fa-solid fa-address-book"></i> Contacts</button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.showSettings()"><i class="fa-solid fa-gear"></i> Settings</button>
      </div>`;
  }

  function renderHeader() {
    const el = document.getElementById('emailWorkspaceHeader');
    if (!el) return;
    const mailUnread = mailMessages.filter(m => m.folder === 'inbox' && m.unread).length;
    const internalUnread = internalMessages.filter(m => !m.archived && m.unread).length;
    el.innerHTML = `
      <div class="email-workspace-tabs flex px-4">
        <button type="button" class="px-5 py-2.5 text-sm font-medium border-b-2 ${state.workspace === 'mail' ? 'border-emerald-500 text-white' : 'border-transparent text-zinc-400'}" onclick="CasePMEmail.setWorkspace('mail')">
          <i class="fa-solid fa-envelope mr-2"></i>Mail ${mailUnread ? `<span class="ml-1 text-xs bg-emerald-600 text-white px-1.5 py-0.5 rounded-full">${mailUnread}</span>` : ''}
        </button>
        <button type="button" class="px-5 py-2.5 text-sm font-medium border-b-2 ${state.workspace === 'internal' ? 'border-emerald-500 text-white' : 'border-transparent text-zinc-400'}" onclick="CasePMEmail.setWorkspace('internal')">
          <i class="fa-solid fa-bell mr-2"></i>Internal ${internalUnread ? `<span class="ml-1 text-xs bg-amber-600 text-white px-1.5 py-0.5 rounded-full">${internalUnread}</span>` : ''}
        </button>
      </div>
      <div class="email-workspace-toolbar">${renderToolbarHTML()}</div>`;
  }

  function renderSidebar() {
    const foldersEl = document.getElementById('emailFolderList');
    const accountEl = document.getElementById('emailAccountBlock');
    if (!foldersEl) return;

    if (state.workspace === 'mail') {
      const folders = MAIL_FOLDERS.filter(f => {
        if ((f.id === 'focused' || f.id === 'other') && !settings.focusedInbox) return false;
        return true;
      });
      foldersEl.innerHTML = folders.map(f => `
        <button type="button" class="email-folder-btn ${state.folder === f.id ? 'active' : ''}" onclick="CasePMEmail.setFolder('${f.id}')">
          <span><i class="fa-solid ${f.icon} w-4 mr-2 text-zinc-500"></i>${f.label}</span>
          <span class="count">${folderCount(f.id, 'mail') || ''}</span>
        </button>`).join('');

      if (settings.gmailCategories && (state.folder === 'inbox' || state.folder === 'focused' || state.folder === 'other')) {
        foldersEl.innerHTML += `<div class="mt-3 mb-1 px-2 text-[9px] uppercase tracking-wider text-zinc-500">Categories</div>`;
        foldersEl.innerHTML += GMAIL_CATEGORIES.map(c => `
          <button type="button" class="email-folder-btn ${state.category === c.id ? 'active' : ''}" onclick="CasePMEmail.setCategory('${c.id}')">
            <span><i class="fa-solid ${c.icon} w-4 mr-2 text-zinc-500"></i>${c.label}</span>
          </button>`).join('');
      }

      foldersEl.innerHTML += `<div class="mt-3 mb-1 px-2 flex items-center justify-between">
        <span class="text-[9px] uppercase tracking-wider text-zinc-500">My Folders</span>
        <button type="button" onclick="CasePMEmail.addCustomFolder()" class="text-[9px] text-emerald-400 hover:text-emerald-300" title="New folder"><i class="fa-solid fa-plus"></i></button>
      </div>`;
      foldersEl.innerHTML += customFolders.map(f => `
        <div class="email-folder-btn ${state.folder === 'custom_' + f.id ? 'active' : ''}" style="padding-right:0.35rem">
          <button type="button" class="flex-1 flex items-center min-w-0 text-left" onclick="CasePMEmail.setFolder('custom_${f.id}')">
            <i class="fa-solid fa-folder w-4 mr-2 text-zinc-500 flex-shrink-0"></i>
            <span class="truncate">${esc(f.name)}</span>
          </button>
          <span class="count flex-shrink-0">${folderCount('custom_' + f.id, 'mail') || ''}</span>
          <span class="email-custom-folder-actions flex-shrink-0">
            <button type="button" class="email-custom-folder-btn" onclick="event.stopPropagation(); CasePMEmail.renameCustomFolder('${f.id}')" title="Rename"><i class="fa-solid fa-pen"></i></button>
            <button type="button" class="email-custom-folder-btn" onclick="event.stopPropagation(); CasePMEmail.deleteCustomFolder('${f.id}')" title="Delete"><i class="fa-solid fa-trash"></i></button>
          </span>
        </div>`).join('');
      if (!customFolders.length) {
        foldersEl.innerHTML += `<div class="px-2 py-1 text-[10px] text-zinc-600">No custom folders yet</div>`;
      }

      if (accountEl) {
        const connected = settings.googleConnected || settings.microsoftConnected || settings.smtpUser;
        accountEl.innerHTML = `
          <div class="px-3 py-2 border-t border-zinc-800 text-xs">
            <div class="text-zinc-500 text-[9px] uppercase mb-1">Account</div>
            <div class="font-medium text-white truncate">${esc(settings.displayName || ctx.userName)}</div>
            <div class="text-zinc-400 truncate">${esc(settings.emailAddress || ctx.userEmail || 'Not connected')}</div>
            <div class="mt-2 flex gap-1">
              ${settings.googleConnected ? '<span class="text-[9px] bg-zinc-800 px-1.5 py-0.5 rounded">Google</span>' : ''}
              ${settings.microsoftConnected ? '<span class="text-[9px] bg-zinc-800 px-1.5 py-0.5 rounded">Microsoft</span>' : ''}
              ${!connected ? '<button type="button" onclick="CasePMEmail.openSetup()" class="text-[10px] text-emerald-400 hover:underline">Set up email</button>' : ''}
            </div>
          </div>`;
      }
    } else {
      foldersEl.innerHTML = INTERNAL_FOLDERS.map(f => `
        <button type="button" class="email-folder-btn ${state.folder === f.id ? 'active' : ''}" onclick="CasePMEmail.setFolder('${f.id}')">
          <span><i class="fa-solid ${f.icon} w-4 mr-2 text-zinc-500"></i>${f.label}</span>
          <span class="count">${folderCount(f.id, 'internal') || ''}</span>
        </button>`).join('');
      if (accountEl) {
        accountEl.innerHTML = `
          <div class="px-3 py-2 border-t border-zinc-800 text-xs text-zinc-400">
            <div class="text-zinc-500 text-[9px] uppercase mb-1">Internal Comms</div>
            Approvals, alerts, team messages, and @mentions from Case PM modules.
          </div>`;
      }
    }

    const labelsEl = document.getElementById('emailLabelsList');
    if (labelsEl && state.workspace === 'mail') {
      const labels = [...new Set(mailMessages.flatMap(m => m.labels || []))];
      labelsEl.innerHTML = labels.length ? `<div class="mt-3 mb-1 px-2 text-[9px] uppercase tracking-wider text-zinc-500">Labels</div>` +
        labels.map(l => `<button type="button" class="email-folder-btn" onclick="CasePMEmail.searchLabel('${esc(l)}')"><span><i class="fa-solid fa-tag w-4 mr-2 text-zinc-500"></i>${esc(l)}</span></button>`).join('') : '';
    }
  }

  function renderInlineComposeHTML() {
    const c = state.inlineCompose;
    if (!c) return '';
    const title = { new: 'New Message', reply: 'Reply', replyAll: 'Reply All', forward: 'Forward', draft: 'Edit Draft' }[c.mode] || 'Compose';
    return `
      <div class="email-inline-compose" id="emailInlineCompose">
        <div class="email-inline-compose-header">
          <span class="text-sm font-semibold text-white">${title}</span>
          <button type="button" onclick="CasePMEmail.closeCompose()" class="text-zinc-400 hover:text-white w-8 h-8 rounded hover:bg-zinc-800"><i class="fa-solid fa-times"></i></button>
        </div>
        <div class="email-inline-compose-fields text-sm">
          <div class="email-inline-compose-row">
            <label>To</label>
            <input type="text" id="inlineComposeTo" value="${esc(c.to)}" placeholder="Recipients" autocomplete="off">
            <button type="button" onclick="CasePMEmail.toggleCcBcc()" class="text-xs text-zinc-400 hover:text-white flex-shrink-0">Cc/Bcc</button>
            <div id="inlineSuggestTo" class="email-recipient-suggest hidden"></div>
          </div>
          <div id="inlineCcBccRows" class="${c.showCcBcc ? '' : 'hidden'} space-y-2">
            <div class="email-inline-compose-row">
              <label>Cc</label>
              <input type="text" id="inlineComposeCc" value="${esc(c.cc)}" autocomplete="off">
              <div id="inlineSuggestCc" class="email-recipient-suggest hidden"></div>
            </div>
            <div class="email-inline-compose-row">
              <label>Bcc</label>
              <input type="text" id="inlineComposeBcc" value="${esc(c.bcc)}" autocomplete="off">
              <div id="inlineSuggestBcc" class="email-recipient-suggest hidden"></div>
            </div>
          </div>
          <div class="email-inline-compose-row">
            <label>Subj</label>
            <input type="text" id="inlineComposeSubject" value="${esc(c.subject)}" class="font-medium">
          </div>
        </div>
        <div id="inlineComposeBody" contenteditable="true" class="email-inline-compose-body">${c.body || ''}</div>
        <div id="inlineComposeScheduleRow" class="hidden px-4 pb-2">
          <label class="text-xs text-zinc-400">Schedule send</label>
          <input type="datetime-local" id="inlineComposeScheduleAt" class="email-field-input mt-1">
        </div>
        <div class="email-inline-compose-footer">
          <div class="flex gap-1">
            <button type="button" class="email-toolbar-btn" title="Attach file"><i class="fa-solid fa-paperclip"></i></button>
            <button type="button" class="email-toolbar-btn" title="Schedule send" onclick="document.getElementById('inlineComposeScheduleRow').classList.toggle('hidden')"><i class="fa-solid fa-clock"></i></button>
            <button type="button" class="email-toolbar-btn" title="Save draft" onclick="CasePMEmail.saveDraft()"><i class="fa-solid fa-file-pen"></i></button>
          </div>
          <div class="flex gap-2">
            <button type="button" onclick="CasePMEmail.undoSend()" class="text-xs text-zinc-400 hover:text-white">Undo</button>
            <button type="button" onclick="CasePMEmail.sendMail(true)" class="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-md text-xs">Schedule</button>
            <button type="button" onclick="CasePMEmail.sendMail()" class="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-semibold text-white">Send</button>
          </div>
        </div>
      </div>`;
  }

  function attachRecipientAutocomplete() {
    const fields = [
      { input: 'inlineComposeTo', suggest: 'inlineSuggestTo' },
      { input: 'inlineComposeCc', suggest: 'inlineSuggestCc' },
      { input: 'inlineComposeBcc', suggest: 'inlineSuggestBcc' },
    ];
    fields.forEach(({ input, suggest }) => {
      const inp = document.getElementById(input);
      const box = document.getElementById(suggest);
      if (!inp || !box) return;
      let activeIdx = -1;
      function hide() { box.classList.add('hidden'); box.innerHTML = ''; activeIdx = -1; }
      function pick(contact) {
        const parts = inp.value.split(/[,;]/);
        parts[parts.length - 1] = ' ' + (contact.name ? `"${contact.name}" <${contact.email}>` : contact.email);
        inp.value = parts.join(',').replace(/^,\s*/, '').trim();
        hide();
        inp.focus();
      }
      function renderSuggest() {
        const val = inp.value;
        const segment = (val.split(/[,;]/).pop() || '').trim();
        const matches = filterContacts(segment);
        if (!segment || !matches.length) { hide(); return; }
        box.innerHTML = matches.map((c, i) => `
          <button type="button" class="email-recipient-suggest-item${i === activeIdx ? ' active' : ''}" data-idx="${i}">
            <div>${esc(c.name)}</div>
            <div class="email">${esc(c.email)}</div>
          </button>`).join('');
        box.classList.remove('hidden');
        box.querySelectorAll('.email-recipient-suggest-item').forEach(btn => {
          btn.addEventListener('mousedown', e => {
            e.preventDefault();
            pick(matches[Number(btn.dataset.idx)]);
          });
        });
      }
      inp.addEventListener('input', () => { activeIdx = -1; renderSuggest(); });
      inp.addEventListener('keydown', e => {
        const items = box.querySelectorAll('.email-recipient-suggest-item');
        if (e.key === 'ArrowDown' && items.length) {
          e.preventDefault();
          activeIdx = Math.min(activeIdx + 1, items.length - 1);
          renderSuggest();
        } else if (e.key === 'ArrowUp' && items.length) {
          e.preventDefault();
          activeIdx = Math.max(activeIdx - 1, 0);
          renderSuggest();
        } else if (e.key === 'Enter' && activeIdx >= 0 && items[activeIdx]) {
          e.preventDefault();
          items[activeIdx].dispatchEvent(new MouseEvent('mousedown'));
        } else if (e.key === 'Escape') {
          hide();
        }
      });
      inp.addEventListener('blur', () => setTimeout(hide, 150));
    });
  }

  function renderToolbar() {
    /* toolbar merged into renderHeader */
  }

  function renderMessageList() {
    const el = document.getElementById('emailMessageList');
    const countEl = document.getElementById('emailListCount');
    if (!el) return;
    const messages = activeMessages();
    if (countEl) countEl.textContent = `${messages.length} message${messages.length !== 1 ? 's' : ''}`;

    if (!messages.length) {
      el.innerHTML = `<div class="p-8 text-center text-zinc-500 text-sm"><i class="fa-solid fa-inbox text-2xl mb-2 block text-zinc-600"></i>No messages</div>`;
      return;
    }

    if (state.workspace === 'internal') {
      el.innerHTML = messages.map(m => {
        const badgeClass = { approval: 'email-internal-badge-approval', alert: 'email-internal-badge-alert', message: 'email-internal-badge-message', mention: 'email-internal-badge-mention', announce: 'email-internal-badge-announce' }[m.type] || 'email-internal-badge-alert';
        return `
        <div class="email-msg-row ${m.unread ? 'unread' : ''} ${state.selectedId === m.id ? 'active' : ''}" onclick="CasePMEmail.select('${m.id}')" ondblclick="CasePMEmail.openMessage('${m.id}')" data-id="${m.id}">
          <div class="flex items-start gap-2">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-0.5">
                <span class="email-chip ${badgeClass}">${esc(m.type || 'alert')}</span>
                ${m.requiresAction ? '<span class="text-[9px] text-amber-400 font-semibold">ACTION</span>' : ''}
                <span class="text-[10px] text-zinc-500 ml-auto flex-shrink-0">${fmtDate(m.date)}</span>
              </div>
              <div class="email-msg-subject text-sm text-zinc-200 truncate">${esc(m.subject)}</div>
              <div class="text-xs text-zinc-500 truncate">${esc(m.from)} · ${esc(m.project || '')}</div>
              <div class="text-xs text-zinc-600 truncate mt-0.5">${esc(m.preview)}</div>
            </div>
          </div>
        </div>`;
      }).join('');
      return;
    }

    el.innerHTML = messages.map(m => `
      <div class="email-msg-row ${m.unread ? 'unread' : ''} ${m.starred ? 'starred' : ''} ${state.selectedId === m.id ? 'active' : ''}" onclick="CasePMEmail.select('${m.id}')" ondblclick="CasePMEmail.openMessage('${m.id}')" data-id="${m.id}">
        <div class="flex items-start gap-2">
          <button type="button" class="email-star text-zinc-600 hover:text-amber-400 flex-shrink-0 mt-0.5" onclick="event.stopPropagation(); CasePMEmail.toggleStar('${m.id}')">
            <i class="fa-${m.starred ? 'solid' : 'regular'} fa-star text-xs"></i>
          </button>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1">
              <span class="text-xs text-zinc-300 truncate flex-1">${esc(m.from)}</span>
              <span class="text-[10px] text-zinc-500 flex-shrink-0">${fmtDate(m.date)}</span>
            </div>
            <div class="email-msg-subject text-sm text-zinc-300 truncate">${esc(m.subject)}</div>
            <div class="text-xs text-zinc-500 truncate">${esc(m.preview)}</div>
            <div class="flex gap-1 mt-1">
              ${m.flagged ? '<i class="fa-solid fa-flag text-[9px] text-red-400"></i>' : ''}
              ${m.hasAttachments ? '<i class="fa-solid fa-paperclip text-[9px] text-zinc-500"></i>' : ''}
              ${m.importance === 'high' ? '<i class="fa-solid fa-exclamation text-[9px] text-amber-400"></i>' : ''}
              ${(m.labels || []).map(l => `<span class="text-[9px] bg-zinc-800 px-1 rounded">${esc(l)}</span>`).join('')}
            </div>
          </div>
        </div>
      </div>`).join('');
  }

  function renderReadingPane() {
    const el = document.getElementById('emailReadingPane');
    if (!el) return;

    if (state.inlineCompose && state.inlineCompose.mode === 'new' && !state.selectedId) {
      el.innerHTML = renderInlineComposeHTML();
      attachRecipientAutocomplete();
      return;
    }

    if (settings.previewPane === 'off' && !state.inlineCompose && !state.selectedId) {
      el.innerHTML = `<div class="flex-1 flex items-center justify-center text-zinc-500 text-sm p-8">Select a message to read</div>`;
      return;
    }

    const m = state.selectedId ? getMessage(state.selectedId) : null;
    if (!m && !state.inlineCompose) {
      el.innerHTML = `<div class="flex-1 flex items-center justify-center text-zinc-500 text-sm p-8"><div class="text-center"><i class="fa-solid fa-envelope-open-text text-3xl mb-3 text-zinc-600"></i>Select a message<br><span class="text-xs text-zinc-600 mt-2 block">Double-click to open</span></div></div>`;
      return;
    }

    const composeHtml = state.inlineCompose ? renderInlineComposeHTML() : '';

    if (state.workspace === 'internal' && m) {
      el.innerHTML = composeHtml + `
        <div class="email-reading-message overflow-auto p-6">
          <div class="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 class="text-lg font-semibold text-white">${esc(m.subject)}</h2>
              <div class="text-sm text-zinc-400 mt-1">From <strong class="text-zinc-200">${esc(m.from)}</strong> · ${fmtDate(m.date)}</div>
              <div class="text-xs text-zinc-500 mt-1">${esc(m.module || '')} · ${esc(m.project || '')}</div>
            </div>
            <div class="flex gap-2 flex-shrink-0">
              ${m.actionUrl ? `<a href="${esc(m.actionUrl)}" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-medium text-white">${esc(m.actionLabel || 'Open')}</a>` : ''}
              ${m.requiresAction ? `<button type="button" onclick="CasePMEmail.approveInternal('${m.id}')" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-md text-sm">Approve</button>` : ''}
              <button type="button" onclick="CasePMEmail.dismissInternal('${m.id}')" class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm">Dismiss</button>
            </div>
          </div>
          <div class="prose prose-invert max-w-none text-sm text-zinc-300">${m.body || esc(m.preview)}</div>
        </div>`;
      if (state.inlineCompose) attachRecipientAutocomplete();
      if (m.unread) {
        m.unread = false;
        persistInternal();
        if (typeof m.id === 'number' || String(m.id).match(/^\d+$/)) {
          fetch(`/api/internal-messages/${m.id}/read`, { method: 'POST' }).catch(() => {});
        }
      }
      return;
    }

    if (!m) {
      el.innerHTML = composeHtml;
      if (state.inlineCompose) attachRecipientAutocomplete();
      return;
    }

    if (settings.markAsReadOnView && m.unread) { m.unread = false; persistMail(); }

    el.innerHTML = composeHtml + `
      <div class="border-b border-zinc-800 px-4 py-2 flex flex-wrap gap-1 flex-shrink-0">
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.reply('${m.id}')"><i class="fa-solid fa-reply"></i> Reply</button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.replyAll('${m.id}')"><i class="fa-solid fa-reply-all"></i> Reply All</button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.forward('${m.id}')"><i class="fa-solid fa-share"></i> Forward</button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.archiveSelected('${m.id}')"><i class="fa-solid fa-box-archive"></i></button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.deleteSelected('${m.id}')"><i class="fa-solid fa-trash"></i></button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.printMessage('${m.id}')"><i class="fa-solid fa-print"></i></button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.snoozeSelected('${m.id}')"><i class="fa-solid fa-clock"></i></button>
        <button type="button" class="email-toolbar-btn" onclick="CasePMEmail.moveSelected('${m.id}')"><i class="fa-solid fa-folder"></i></button>
      </div>
      <div class="email-reading-message overflow-auto p-6">
        <h2 class="text-lg font-semibold text-white mb-2">${esc(m.subject)}</h2>
        <div class="text-sm text-zinc-400 mb-4">
          <div><span class="text-zinc-500">From:</span> ${esc(m.from)} &lt;${esc(m.fromEmail)}&gt;</div>
          <div><span class="text-zinc-500">To:</span> ${esc((m.to || []).join(', '))}</div>
          <div><span class="text-zinc-500">Date:</span> ${new Date(m.date).toLocaleString()}</div>
        </div>
        ${m.attachments && m.attachments.length ? `<div class="mb-4 flex flex-wrap gap-2">${m.attachments.map(a => `<span class="text-xs bg-zinc-800 border border-zinc-700 px-3 py-1.5 rounded-md"><i class="fa-solid fa-paperclip mr-1"></i>${esc(a.name)} <span class="text-zinc-500">(${esc(a.size)})</span></span>`).join('')}</div>` : ''}
        <div class="prose prose-invert max-w-none text-sm text-zinc-300">${m.body || esc(m.preview)}</div>
      </div>`;
    if (state.inlineCompose) attachRecipientAutocomplete();
  }

  function applyLayoutClasses() {
    const root = document.querySelector('.email-main');
    if (!root) return;
    root.classList.remove('email-preview-bottom', 'email-preview-off');
    document.body.classList.remove('email-density-compact');
    if (settings.previewPane === 'bottom') root.classList.add('email-preview-bottom');
    if (settings.previewPane === 'off') root.classList.add('email-preview-off');
    if (settings.density === 'compact') document.body.classList.add('email-density-compact');
  }

  // ─── Actions ───────────────────────────────────────────────
  function setWorkspace(ws) {
    state.workspace = ws;
    state.folder = ws === 'internal' ? 'internal-inbox' : 'inbox';
    state.category = null;
    state.selectedId = null;
    state.inlineCompose = null;
    render();
  }

  function setFolder(id) {
    state.folder = id;
    state.category = null;
    state.selectedId = null;
    render();
  }

  function setCategory(id) {
    state.category = state.category === id ? null : id;
    render();
  }

  function select(id) {
    if (state.selectedId !== id) state.inlineCompose = null;
    state.selectedId = id;
    renderMessageList();
    renderReadingPane();
  }

  function openMessage(id) {
    state.selectedId = id;
    const m = getMessage(id);
    if (!m) return;
    if (state.workspace === 'mail' && (m.folder === 'drafts' || m.isDraft)) {
      state.inlineCompose = {
        mode: 'draft',
        to: (m.to || []).join(', '),
        cc: (m.cc || []).join(', '),
        bcc: (m.bcc || []).join(', '),
        subject: m.subject || '',
        body: m.body || '',
        draftId: m.id,
        showCcBcc: !!((m.cc && m.cc.length) || (m.bcc && m.bcc.length)),
      };
    } else {
      state.inlineCompose = null;
    }
    renderMessageList();
    renderReadingPane();
  }

  function setSearch(q) {
    state.search = q;
    renderMessageList();
  }

  function toggleFilter(type) {
    if (type === 'unread') state.filterUnread = !state.filterUnread;
    renderMessageList();
  }

  function toggleStar(id) {
    const m = getMessage(id);
    if (m) { m.starred = !m.starred; persistMail(); render(); }
  }

  function compose(opts) {
    state.inlineCompose = {
      mode: opts?.draftId ? 'draft' : (opts?.mode || 'new'),
      to: opts?.to || '',
      cc: opts?.cc || '',
      bcc: opts?.bcc || '',
      subject: opts?.subject || '',
      body: opts?.body || (signatures.find(s => s.id === settings.defaultSignatureId)?.html || ''),
      draftId: opts?.draftId || null,
      replyToId: opts?.replyToId || null,
      showCcBcc: !!(opts?.cc || opts?.bcc),
    };
    if (opts?.replyToId) state.selectedId = opts.replyToId;
    else if (!opts?.draftId) state.selectedId = null;
    renderReadingPane();
    renderMessageList();
  }

  function closeCompose() {
    state.inlineCompose = null;
    renderReadingPane();
  }

  function toggleCcBcc() {
    const row = document.getElementById('inlineCcBccRows');
    if (row) row.classList.toggle('hidden');
    if (state.inlineCompose) state.inlineCompose.showCcBcc = row && !row.classList.contains('hidden');
  }

  function saveDraft() {
    const to = document.getElementById('inlineComposeTo')?.value.trim() || '';
    const subject = document.getElementById('inlineComposeSubject')?.value.trim() || '';
    const body = document.getElementById('inlineComposeBody')?.innerHTML || '';
    const draft = {
      id: state.inlineCompose?.draftId || uid(),
      folder: 'drafts', category: 'primary', focused: true,
      from: settings.displayName || ctx.userName, fromEmail: settings.emailAddress || ctx.userEmail,
      to: to.split(/[,;]/).map(s => s.trim()).filter(Boolean),
      cc: (document.getElementById('inlineComposeCc')?.value || '').split(/[,;]/).map(s => s.trim()).filter(Boolean),
      bcc: (document.getElementById('inlineComposeBcc')?.value || '').split(/[,;]/).map(s => s.trim()).filter(Boolean),
      subject: subject || '(No subject)', preview: body.replace(/<[^>]+>/g, '').slice(0, 120),
      body, date: new Date().toISOString(), unread: true, starred: false, flagged: false,
      hasAttachments: false, attachments: [], labels: [], threadId: uid(), importance: 'normal',
      snoozedUntil: null, scheduledFor: null, isDraft: true,
    };
    const idx = mailMessages.findIndex(m => m.id === draft.id);
    if (idx >= 0) mailMessages[idx] = draft;
    else mailMessages.unshift(draft);
    persistMail();
    state.inlineCompose = null;
    state.selectedId = draft.id;
    toast('Draft saved.', 'success');
    render();
  }

  function sendMail(scheduled) {
    const to = document.getElementById('inlineComposeTo')?.value.trim();
    const subject = document.getElementById('inlineComposeSubject')?.value.trim();
    const body = document.getElementById('inlineComposeBody')?.innerHTML;
    if (!to) { toast('Add at least one recipient.', 'error'); return; }
    const scheduleVal = document.getElementById('inlineComposeScheduleAt')?.value;
    const draftId = state.inlineCompose?.draftId;
    if (draftId) {
      const di = mailMessages.findIndex(m => m.id === draftId);
      if (di >= 0) mailMessages.splice(di, 1);
    }
    const msg = {
      id: uid(), folder: scheduled || scheduleVal ? 'scheduled' : 'sent', category: 'primary', focused: true,
      from: settings.displayName || ctx.userName, fromEmail: settings.emailAddress || ctx.userEmail,
      to: to.split(/[,;]/).map(s => s.trim()).filter(Boolean),
      cc: (document.getElementById('inlineComposeCc')?.value || '').split(/[,;]/).map(s => s.trim()).filter(Boolean),
      bcc: (document.getElementById('inlineComposeBcc')?.value || '').split(/[,;]/).map(s => s.trim()).filter(Boolean),
      subject: subject || '(No subject)', preview: body.replace(/<[^>]+>/g, '').slice(0, 120),
      body, date: new Date().toISOString(), unread: false, starred: false, flagged: false,
      hasAttachments: false, attachments: [], labels: [], threadId: uid(), importance: 'normal',
      scheduledFor: scheduleVal || null, snoozedUntil: null,
    };
    if (settings.undoSendSeconds > 0 && !scheduled && !scheduleVal) {
      mailMessages.unshift({ ...msg, folder: 'outbox_pending' });
      persistMail();
      closeCompose();
      toast(`Sending in ${settings.undoSendSeconds}s… (Undo available)`, 'info');
      clearTimeout(undoTimer);
      undoTimer = setTimeout(() => {
        const idx = mailMessages.findIndex(m => m.id === msg.id);
        if (idx >= 0) { mailMessages[idx].folder = 'sent'; persistMail(); render(); toast('Message sent.', 'success'); }
      }, settings.undoSendSeconds * 1000);
      return;
    }
    mailMessages.unshift(msg);
    persistMail();
    closeCompose();
    toast(scheduled || scheduleVal ? 'Message scheduled.' : 'Message sent.', 'success');
    render();
  }

  function undoSend() {
    const idx = mailMessages.findIndex(m => m.folder === 'outbox_pending');
    if (idx >= 0) {
      clearTimeout(undoTimer);
      mailMessages.splice(idx, 1);
      persistMail();
      compose();
      toast('Send cancelled.', 'info');
      render();
    }
  }

  function reply(id, all) {
    const m = getMessage(id);
    if (!m) return;
    const to = all
      ? [m.fromEmail, ...(m.to || []).filter(e => e !== (settings.emailAddress || ctx.userEmail))].join(', ')
      : m.fromEmail;
    compose({
      mode: all ? 'replyAll' : 'reply',
      to,
      subject: 'RE: ' + m.subject.replace(/^RE:\s*/i, ''),
      body: `<br><br><hr><p>On ${fmtDate(m.date)}, ${esc(m.from)} wrote:</p>${m.body || ''}`,
      replyToId: id,
    });
  }

  function replyAll(id) { reply(id, true); }

  function forward(id) {
    const m = getMessage(id);
    if (!m) return;
    compose({
      mode: 'forward',
      subject: 'FW: ' + m.subject.replace(/^FW:\s*/i, ''),
      body: `<br><br><hr><p>Forwarded message:</p>${m.body || ''}`,
      replyToId: id,
    });
  }

  function archiveSelected(id) {
    const ids = id ? [id] : state.selectedId ? [state.selectedId] : [...state.selectedIds];
    ids.forEach(i => { const m = getMessage(i); if (m) m.folder = 'archive'; });
    persistMail();
    toast('Archived.', 'success');
    render();
  }

  function deleteSelected(id) {
    if (settings.confirmPermanentDelete && state.folder === 'trash' && !confirm('Permanently delete?')) return;
    const ids = id ? [id] : state.selectedId ? [state.selectedId] : [...state.selectedIds];
    ids.forEach(i => { const m = getMessage(i); if (m) m.folder = state.folder === 'trash' ? '_deleted' : 'trash'; });
    mailMessages = mailMessages.filter(m => m.folder !== '_deleted');
    persistMail();
    state.selectedId = null;
    toast('Deleted.', 'success');
    render();
  }

  function markReadToggle() {
    const m = getMessage(state.selectedId);
    if (m) { m.unread = !m.unread; persistMail(); render(); }
  }

  function flagSelected() {
    const m = getMessage(state.selectedId);
    if (m) { m.flagged = !m.flagged; persistMail(); render(); }
  }

  function starSelected() { if (state.selectedId) toggleStar(state.selectedId); }

  function snoozeSelected(id) {
    const target = id || state.selectedId;
    const m = getMessage(target);
    if (!m) return;
    const hours = prompt('Snooze for how many hours?', '4');
    if (!hours) return;
    m.snoozedUntil = new Date(Date.now() + Number(hours) * 3600000).toISOString();
    m.folder = 'snoozed';
    persistMail();
    toast(`Snoozed for ${hours} hours.`, 'success');
    render();
  }

  function moveSelected(id) {
    const systemFolders = MAIL_FOLDERS.map(f => f.id).join(', ');
    const customList = customFolders.map(f => `custom_${f.id} (${f.name})`).join(', ');
    const hint = customList ? `${systemFolders}, ${customList}` : systemFolders;
    const folder = prompt(`Move to folder:\n${hint}`, 'archive');
    if (!folder) return;
    const target = id || state.selectedId;
    const m = getMessage(target);
    if (!m) return;
    const normalized = folder.includes('(') ? folder.split('(')[0].trim() : folder.trim();
    const valid = MAIL_FOLDERS.some(f => f.id === normalized) || normalized.startsWith('custom_');
    if (valid) { m.folder = normalized; persistMail(); toast('Moved.', 'success'); render(); }
    else toast('Unknown folder.', 'error');
  }

  function addCustomFolder() {
    const name = prompt('New folder name:', 'Projects');
    if (!name || !name.trim()) return;
    const id = 'cf_' + Date.now().toString(36);
    customFolders.push({ id, name: name.trim() });
    persistCustomFolders();
    renderSidebar();
    toast(`Folder "${name.trim()}" created.`, 'success');
  }

  function renameCustomFolder(id) {
    const f = customFolders.find(x => x.id === id);
    if (!f) return;
    const name = prompt('Rename folder:', f.name);
    if (!name || !name.trim()) return;
    f.name = name.trim();
    persistCustomFolders();
    renderSidebar();
  }

  function deleteCustomFolder(id) {
    const f = customFolders.find(x => x.id === id);
    if (!f) return;
    if (!confirm(`Delete folder "${f.name}"? Messages will move to Inbox.`)) return;
    mailMessages.forEach(m => { if (m.folder === 'custom_' + id) m.folder = 'inbox'; });
    customFolders = customFolders.filter(x => x.id !== id);
    if (state.folder === 'custom_' + id) state.folder = 'inbox';
    persistCustomFolders();
    persistMail();
    render();
  }

  function labelSelected() {
    const label = prompt('Add label:', 'Projects');
    if (!label) return;
    const m = getMessage(state.selectedId);
    if (m) { m.labels = m.labels || []; if (!m.labels.includes(label)) m.labels.push(label); persistMail(); render(); }
  }

  function reportPhishing() { toast('Message reported. Sender blocked and IT notified.', 'success'); }

  function markInternalRead(id) {
    const target = id || state.selectedId;
    const m = internalMessages.find(x => x.id === target);
    if (m) { m.unread = false; persistInternal(); render(); }
  }

  async function approveInternal(id) {
    const target = id || state.selectedId;
    const m = internalMessages.find(x => String(x.id) === String(target));
    if (!m) return;
    if (m.approvalId && typeof CasePMWorkflow !== 'undefined') {
      try {
        await CasePMWorkflow.decide(m.approvalId, 'approve');
      } catch (e) {
        toast('Could not approve: ' + e.message, 'error');
        return;
      }
    }
    m.unread = false;
    m.requiresAction = false;
    toast(`Approved: ${m.subject}`, 'success');
    await refreshInternalFromServer();
  }

  async function dismissInternal(id) {
    const target = id || state.selectedId;
    const m = internalMessages.find(x => String(x.id) === String(target));
    if (!m) return;
    if (m.approvalId && typeof CasePMWorkflow !== 'undefined') {
      try {
        await CasePMWorkflow.decide(m.approvalId, 'dismiss');
      } catch (e) {
        /* still archive locally */
      }
    }
    if (typeof m.id === 'number' || String(m.id).match(/^\d+$/)) {
      await fetch(`/api/internal-messages/${m.id}/archive`, { method: 'POST' }).catch(() => {});
    }
    m.archived = true;
    m.unread = false;
    state.selectedId = null;
    await refreshInternalFromServer();
  }

  function composeInternal() {
    const to = prompt('Send internal message to (name):', 'Tom Bradley');
    const subject = prompt('Subject:', 'Quick note');
    if (!subject) return;
    internalMessages.unshift({
      id: uid(), folder: 'team', type: 'message', from: ctx.userName, fromUser: ctx.userName,
      subject, preview: '', body: `<p>${esc(subject)}</p>`, date: new Date().toISOString(),
      unread: false, priority: 'normal', project: ctx.projectName, module: 'Internal', requiresAction: false,
    });
    persistInternal();
    toast('Internal message sent.', 'success');
    setWorkspace('internal');
    setFolder('team');
  }

  function refresh() {
    if (state.workspace === 'internal') {
      refreshInternalFromServer().then(() => toast('Internal messages synced.', 'success'));
      return;
    }
    toast('Mailbox synced.', 'success');
    render();
  }

  function printMessage(id) {
    const m = getMessage(id);
    if (!m) return;
    const w = window.open('', '_blank');
    w.document.write(`<html><head><title>${esc(m.subject)}</title></head><body><h1>${esc(m.subject)}</h1>${m.body || ''}</body></html>`);
    w.print();
  }

  function searchLabel(label) { state.search = label; document.getElementById('emailSearchInput').value = label; renderMessageList(); }

  function openSetup() { showSettings(); }

  // ─── Modals ────────────────────────────────────────────────
  function showSettings() {
    document.getElementById('emailSettingsModal')?.classList.remove('hidden');
    if (typeof CasePMEmailSettingsUI !== 'undefined') CasePMEmailSettingsUI.render('emailSettingsModalBody');
  }

  function showRules() {
    const modal = document.getElementById('emailRulesModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    const body = document.getElementById('emailRulesBody');
    body.innerHTML = rules.length ? rules.map((r, i) => `
      <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-3 mb-2 text-sm flex justify-between">
        <div><strong>${esc(r.name)}</strong><div class="text-xs text-zinc-400">${esc(r.condition)} → ${esc(r.action)}</div></div>
        <button onclick="CasePMEmail.deleteRule(${i})" class="text-red-400 text-xs">Delete</button>
      </div>`).join('') : '<p class="text-zinc-400 text-sm">No rules yet. Create rules to auto-sort, forward, label, or delete mail.</p>';
  }

  function addRule() {
    const name = prompt('Rule name:', 'Move Procore to Updates');
    const condition = prompt('When (contains in from/subject):', 'procore');
    const action = prompt('Action (move:updates, label:Projects, delete, forward:email):', 'move:updates');
    if (name && condition && action) { rules.push({ name, condition, action }); saveJson(STORAGE.rules, rules); showRules(); }
  }

  function deleteRule(i) { rules.splice(i, 1); saveJson(STORAGE.rules, rules); showRules(); }

  function showContacts() {
    document.getElementById('emailContactsModal')?.classList.remove('hidden');
    document.getElementById('emailContactsBody').innerHTML = contacts.map(c => `
      <div class="flex items-center justify-between py-2 border-b border-zinc-800 text-sm">
        <div><div class="font-medium">${esc(c.name)}</div><div class="text-xs text-zinc-400">${esc(c.email)} · ${esc(c.company || '')}</div></div>
        <button class="text-xs text-emerald-400" onclick="CasePMEmail.compose({to:'${esc(c.email)}'})">Email</button>
      </div>`).join('');
  }

  function showAdvancedSearch() {
    document.getElementById('emailAdvancedSearchModal')?.classList.remove('hidden');
  }

  function runAdvancedSearch() {
    state.searchAdvanced = {
      from: document.getElementById('advFrom').value,
      to: document.getElementById('advTo').value,
      subject: document.getElementById('advSubject').value,
      hasAttachment: document.getElementById('advAttachment').checked,
      unread: document.getElementById('advUnread').checked,
    };
    document.getElementById('emailAdvancedSearchModal')?.classList.add('hidden');
    renderMessageList();
  }

  function init(options) {
    ctx = { ...ctx, ...options };
    loadAll();
    global.CasePMEmailSettings = settings;
    if (typeof CasePMWorkflow !== 'undefined') {
      CasePMWorkflow.loadPortal().then(() => render());
    } else {
      render();
    }
    document.getElementById('emailSearchInput')?.addEventListener('input', e => setSearch(e.target.value));

    if (settings.keyboardShortcuts) {
      document.addEventListener('keydown', e => {
        if (e.target.matches('input, textarea, [contenteditable]')) return;
        if (e.key === 'c') compose();
        if (e.key === 'r' && state.selectedId) reply(state.selectedId);
        if (e.key === 'e' && state.selectedId) archiveSelected(state.selectedId);
        if (e.key === '#' && state.selectedId) deleteSelected(state.selectedId);
        if (e.key === '/') { e.preventDefault(); document.getElementById('emailSearchInput')?.focus(); }
      });
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get('tab') === 'internal') setWorkspace('internal');
    if (params.get('settings') === '1') showSettings();
  }

  global.CasePMEmail = {
    init, setWorkspace, setFolder, setCategory, select, openMessage, setSearch, toggleFilter, toggleStar,
    compose, closeCompose, toggleCcBcc, saveDraft, sendMail, undoSend, reply, replyAll, forward,
    archiveSelected, deleteSelected, markReadToggle, flagSelected, starSelected,
    snoozeSelected, moveSelected, labelSelected, reportPhishing,
    addCustomFolder, renameCustomFolder, deleteCustomFolder,
    markInternalRead, approveInternal, dismissInternal, composeInternal,
    refresh, printMessage, searchLabel, openSetup, showSettings, showRules, addRule, deleteRule,
    showContacts, showAdvancedSearch, runAdvancedSearch,
    getSettings: () => settings,
    saveSettings: (s) => { settings = { ...settings, ...s }; persistSettings(); render(); },
    STORAGE, MAIL_FOLDERS, INTERNAL_FOLDERS, DEFAULT_SETTINGS,
  };

  global.CasePMEmailSettings = settings;
})(window);
