(function(global){ 'use strict';

function inferHelpDetail(subTitle, stepTitle, subBody) {
  const t = `${subTitle} ${subBody || ''} ${stepTitle}`.toLowerCase();
  const related = [];
  const how = [];
  const link = (mods) => mods.map(m => `<strong>${m}</strong>`).join(', ');

  if (/dashboard|tile|overview|morning/.test(t)) {
    how.push('The dashboard rolls up open counts from other modules so you can see what needs attention without opening each list.');
    related.push('Dashboard', 'RFIs', 'Punch List', 'Pay Applications', 'Schedule');
  } else if (/daily log|weather|crew|manpower|work performed/.test(t)) {
    how.push('Each daily log is one dated record per project. Simple fields capture the superintendent’s summary; detailed sections add manpower grids and conditions.');
    related.push('Daily Log', 'Photos', 'Weekly Report', 'Schedule', 'Safety');
  } else if (/rfi|ball in court|assignee|official|question/.test(t)) {
    how.push('An RFI is a formal Q&A tied to the contract record. Ball in Court shows who must act next; responses stay on the RFI until the manager marks an official answer.');
    related.push('RFIs', 'Project Directory', 'Change Orders', 'Drawings', 'Email → Internal');
  } else if (/change event|pco|cor|sub change|sov/.test(t)) {
    how.push('Change events are the starting point for scope shifts. PCOs/CPCOs hold SOV line detail; approved change orders update budget and billing.');
    related.push('Change Orders', 'Budget', 'Commitments', 'Pay Applications', 'RFIs');
  } else if (/submittal|spec section|approval/.test(t)) {
    how.push('Submittals track shop drawings and product data through review cycles. Status and spec section tie each item to the contract documents.');
    related.push('Submittals', 'Drawings', 'Documents', 'RFIs', 'Schedule');
  } else if (/punch|deficiency|close out/.test(t)) {
    how.push('Punch items track finish work and deficiencies by location and trade. Status moves from open → in progress → ready for review → closed.');
    related.push('Punch List', 'Photos', 'Daily Log', 'Inspections', 'Drawings');
  } else if (/schedule|baseline|critical|lookahead|gantt/.test(t)) {
    how.push('The schedule is the project timeline with dependencies (CPM). Baselines let you compare planned vs actual; look-ahead views focus on the next few weeks.');
    related.push('Schedule', 'Daily Log', 'Deliveries', 'Change Orders', 'Dashboard');
  } else if (/budget|forecast|commitment|sov|cost code/.test(t)) {
    how.push('Budget lines are the cost plan; commitments are subcontract POs; actuals flow from pay apps and job cost. Forecast projects where you will land.');
    related.push('Budget', 'Commitments', 'Forecast', 'Pay Applications', 'Change Orders');
  } else if (/pay app|g702|g703|billing|draw/.test(t)) {
    how.push('Pay applications bill the owner by period. G702/G703 summarize contract and SOV; subcontractor tabs track sub billing against commitments.');
    related.push('Pay Applications', 'Budget', 'Commitments', 'Change Orders', 'Documents');
  } else if (/photo|camera|attach|upload/.test(t)) {
    how.push('Photos stored in Case PM stay with the project and can be linked to daily logs, punch items, RFIs, and safety observations.');
    related.push('Photos', 'Daily Log', 'Punch List', 'Safety', 'Documents');
  } else if (/email|internal|message|inbox|notification|approval/.test(t)) {
    how.push('Internal messages route approvals and team discussion inside Case PM. Approval-type messages tie to RFIs, COs, pay apps, and other workflow items.');
    related.push('Email / Internal', 'RFIs', 'Change Orders', 'Notifications', 'Approvals inbox');
  } else if (/accounting|gl|ap|ar|erp|sage/.test(t)) {
    how.push('Accounting connects job cost in Case PM to your ERP. GL, AP, and AR views summarize what to post or reconcile — always confirm project numbers match before export.');
    related.push('Accounting', 'Budget', 'Pay Applications', 'Commitments', 'Program Settings');
  } else if (/marketing|pipeline|campaign|lead|portfolio/.test(t)) {
    how.push('Marketing tracks pursuits before they become projects — pipeline stages, campaigns, and website leads feed ROI reporting when jobs close.');
    related.push('Marketing', 'Projects', 'Estimating', 'Plan Room', 'Dashboard');
  } else if (/audit|compliance|activity log/.test(t)) {
    how.push('The audit log records who changed what and when — use filters to investigate disputes, security reviews, or compliance questions.');
    related.push('Audit Log', 'User Management', 'Program Settings', 'Companies');
  } else if (/portal|client|subcontractor|vendor/.test(t)) {
    how.push('Portals give external parties a limited view — subs see RFQs and submittals; owners see curated progress without full internal data.');
    related.push('Client Portal', 'RFQ Portal', 'Bid Portal', 'Submittals', 'Project Directory');
  } else if (/document|folder|file|drawing|meeting/.test(t)) {
    how.push('Documents and drawings are the project file cabinet. Meeting minutes capture decisions that RFIs and change orders may reference later.');
    related.push('Documents', 'Drawings', 'Meeting Minutes', 'Submittals', 'Projects');
  } else if (/admin|user|company|program setting/.test(t)) {
    how.push('Admin modules configure who can see what company-wide. Changes here affect every project — document updates and test on a sandbox job first.');
    related.push('User Management', 'Companies', 'Program Settings', 'Audit Log', 'Projects');
  } else if (/filter|search|sort|export|print|sidebar|header/.test(t)) {
    how.push('Navigation and list tools help you find records quickly. The header project picker sets context for most modules.');
    related.push('Dashboard', 'Projects', 'Documents', 'Notifications');
  } else {
    how.push(`"${subTitle}" is part of ${stepTitle.toLowerCase()} — use the fields on screen, then save or submit to update the project record.`);
    related.push('Dashboard', 'Documents', 'Notifications');
  }

  const uniq = [...new Set(related)];
  return `${how.join(' ')} <span class="text-zinc-500">Related in Case PM:</span> ${link(uniq)}.`;
}

function steps(...items){
  return items.map((item) => {
    const [title, body, substeps] = item;
    return {
      title,
      body,
      substeps: substeps
        ? substeps.map((sub) => {
            const [st, sb, detail] = sub;
            const bodyText = sb || '';
            const detailText = detail || inferHelpDetail(st, title, bodyText);
            return { title: st, body: bodyText, detail: detailText };
          })
        : [],
    };
  });
}

function singleGuide(title, subtitle, stepPairs, icon='fa-compass'){
  return { title, subtitle, sections: [{ id:'main', title:'How to use', icon, steps: steps(...stepPairs) }] };
}

const USER_GUIDE_SECTIONS = [
  {
    id: 'welcome',
    title: 'Welcome to Case PM',
    icon: 'fa-hand-wave',
    steps: steps(
      ['What Case PM is', 'Case PM is your construction project hub — one place for field logs, RFIs, financials, documents, and team communication tied to each job.', [
        ['One system per job', 'Every module reads the <strong>active project</strong> from the header so RFIs, budget lines, and photos stay on the correct contract.'],
        ['Staff vs portal', 'Your company staff see the full sidebar. Subcontractors and owners use portals with a smaller menu focused on their workflow.'],
        ['Cloud access', 'Open Case PM in a modern browser; save work with each form’s <strong>Save</strong> or <strong>Submit</strong> button before leaving a page.'],
      ]],
      ['First login', 'After your admin invites you, sign in with your email and password. Complete profile details if prompted so notifications reach the right person.', [
        ['Check email', 'Use the invite link or company login URL your admin provided — bookmark it for daily use.'],
        ['Password & 2FA', 'Follow <strong>Program Settings</strong> security rules; enable two-factor authentication when your admin requires it.'],
        ['Profile', 'Click your avatar in the header to open <strong>User Profile</strong> — add phone and photo so the team recognizes you on assignee lists.'],
        ['Wrong access?', 'If modules are missing, ask an admin to adjust your role under <strong>User Management</strong>.'],
      ]],
      ['Roles and permissions', 'Your role controls which sidebar links appear and whether you can edit financial or admin data.', [
        ['Project access', 'You may be limited to specific projects — only those jobs appear in the header project list.'],
        ['Module access', 'Some users see field modules only; accounting roles see <strong>Budget</strong> and <strong>Pay Applications</strong>.'],
        ['Admin users', 'Admins manage <strong>Users</strong>, <strong>Companies</strong>, and <strong>Program Settings</strong> — treat those changes as company-wide.'],
        ['Read-only', 'View-only users can browse lists and export but cannot submit approvals or edit records.'],
      ]],
      ['Open the user guide', 'The full guide lives in the header only — click <strong>User guide</strong> (book icon) next to notifications. It is not duplicated on individual module pages as a second button.', [
        ['Header button', 'Look at the top bar on the right: <strong>User guide</strong> opens help for the current page or the complete guide.'],
        ['Page-specific help', 'On an RFI page, the same button opens RFIs help; use the nav link inside help for <strong>Complete user guide (all modules)</strong>.'],
        ['No duplicate buttons', 'Module toolbars do not add a second guide button — always use the header <strong>User guide</strong>.'],
        ['Staff only', 'The guide button appears for main-company staff portals, not for external portal-only accounts.'],
      ]],
      ['Daily rhythm', 'Pick your project in the header, scan the <strong>Dashboard</strong>, clear notifications, then work the highest-priority module queue.', [
        ['Morning', 'Confirm <strong>Current Project</strong>, open <strong>Dashboard</strong>, note red or amber tile counts.'],
        ['Notifications', 'Click the bell and act on items where you are <strong>Ball in Court</strong>.'],
        ['Field first', 'Superintendents often start with <strong>Daily Log</strong> and <strong>Photos</strong> before admin work.'],
        ['Close the day', 'Save open drafts and check the dashboard again so nothing critical sits unassigned.'],
      ]],
    ),
  },
  {
    id: 'navigation',
    title: 'Navigation & projects',
    icon: 'fa-compass',
    steps: steps(
      ['Sidebar menu', 'The left sidebar groups modules into Main, Core Modules, Financial, Field & Docs, and Admin. Only modules your role allows are visible.', [
        ['Collapse sidebar', 'Click the collapse control at the top of the sidebar to hide labels and save screen space — your preference is remembered.'],
        ['Active link', 'The highlighted menu item shows which page you are on; section headers are labels only, not links.'],
        ['Project required', 'Many links need an active project — if you see <strong>Select a Project</strong>, choose one from the header first.'],
        ['Portal menus', 'Subcontractor and architect portals show a shorter menu (for example <strong>RFQ Portal</strong> or <strong>Submittals</strong> only).'],
      ]],
      ['Active project picker', 'The header <strong>Current Project</strong> dropdown sets context for RFIs, budget, daily log, and most tiles on the dashboard.', [
        ['Open list', 'Click the project name in the header to search and select a job.'],
        ['Switch jobs', 'Changing the active project reloads module data for the new job — finish saves before switching.'],
        ['No project', 'Email, <strong>Projects</strong> list, <strong>Companies</strong>, and some admin pages work without a selected project.'],
        ['Sub portal', 'Subs may only see projects where their company is on the directory or SOV.'],
      ]],
      ['Create and save', 'Most modules use <strong>New</strong> or <strong>+</strong> in the toolbar to create records. Always click <strong>Save</strong> before leaving a form or drawer.', [
        ['Draft vs submit', 'Some items stay <strong>Draft</strong> until you click <strong>Submit</strong> or <strong>Send</strong> — drafts may not notify other users.'],
        ['Validation', 'Red field highlights mean required data is missing — fix those before save succeeds.'],
        ['Attachments', 'Use attach or upload controls on the form; large files may take a moment — wait for the success indicator.'],
        ['Lost work', 'If the browser tab closes unsaved, reopen the record — Case PM cannot recover unsaved client data.'],
      ]],
      ['Search and filters', 'List pages combine search boxes with status filters. Export or print when you need owner-ready PDFs or spreadsheets.', [
        ['Combine filters', 'Stack status filters with text search to narrow long RFIs or submittal logs.'],
        ['Column sort', 'Click column headers where available to sort by date, number, or status.'],
        ['Export', 'Use <strong>Export</strong> or print actions in the toolbar for meeting packets or email attachments.'],
        ['Clear filters', 'Reset filters when counts look wrong — you may be hiding open items accidentally.'],
      ]],
      ['Permissions troubleshooting', 'If a module is missing or actions are grayed out, you need a role or project assignment change — not a different browser.', [
        ['Ask admin', 'Contact an admin with your email and the project name you need access to.'],
        ['User Management', 'Admins open <strong>User Management</strong>, edit your user, and grant module + project rights.'],
        ['Financial lock', 'Budget and pay apps are often restricted — estimators may not see accounting even on the same project.'],
        ['Audit', 'Admins can review <strong>Audit Log</strong> to see who changed permissions recently.'],
      ]],
    ),
  },
  {
    id: 'dashboard-projects',
    title: 'Dashboard & projects',
    icon: 'fa-gauge-high',
    steps: steps(
      ['Dashboard purpose', 'The <strong>Dashboard</strong> is your morning command center — tiles summarize open RFIs, punch, safety, schedule, and financial snapshots for the active project.', [
        ['Tile drill-down', 'Click a tile title or <strong>View all</strong> to open the full module list behind that count.'],
        ['Customize layout', 'Switch to customize mode to drag and resize tiles; layout saves per user for that project.'],
        ['Alerts', 'Red and amber counts usually mean overdue or pending approvals — prioritize those modules first.'],
        ['Wrong counts', 'If numbers look impossible, confirm the correct project is selected in the header.'],
      ]],
      ['Projects list', '<strong>Projects</strong> lets you browse every job you can access, create new jobs, and open project detail settings.', [
        ['New Project', 'Click <strong>New Project</strong>, enter name, number, address, dates, and client company, then set status <strong>Active</strong>.'],
        ['Project number', 'Match your ERP job number when using <strong>Accounting</strong> or Sage sync — mismatches break exports.'],
        ['Team', 'On project detail, assign PM, superintendent, and other roles so workflow routes correctly.'],
        ['Archive', 'Set <strong>Complete</strong> or <strong>Archived</strong> to hide finished jobs from default lists while keeping history.'],
      ]],
      ['Project Directory', '<strong>Project Directory</strong> aggregates people and companies linked to the job from team, RFIs, commitments, schedule, and other modules.', [
        ['Auto-built', 'You do not manually add rows here — update contacts in source modules or <strong>Companies</strong>.'],
        ['People vs companies', 'Toggle views to see individuals or firms grouped on the roster.'],
        ['Refresh', 'Click <strong>Refresh</strong> after updating commitments or pay app SOV vendors.'],
        ['Portal users', 'Ensure subs have user accounts tied to the right company for RFQ and submittal portals.'],
      ]],
      ['Job Map', '<strong>Job Map</strong> plots your company’s projects geographically so regional managers can see active sites at a glance.', [
        ['Open map', 'Choose <strong>Job Map</strong> from the sidebar under Main — staff only.'],
        ['Markers', 'Each marker represents a project address; click to open or switch to that job.'],
        ['Filters', 'Filter by status to hide complete jobs from the map layer.'],
        ['Addresses', 'Projects need valid addresses on the project record for accurate map placement.'],
      ]],
      ['Link dashboard to action', 'Use dashboard tiles to choose where to work, then return after clearing queues to confirm counts dropped.', [
        ['Prioritize', 'Pick the module with the highest risk — overdue RFIs, open safety items, or pending pay apps.'],
        ['Assign owners', 'If you cannot close an item, assign the correct Ball in Court contact in that module.'],
        ['Owner reports', 'Export from modules after dashboard review for weekly owner meetings.'],
        ['Habit', 'End the day with a quick dashboard scan so nothing critical is left unowned.'],
      ]],
    ),
  },
  {
    id: 'field-daily',
    title: 'Field & daily reporting',
    icon: 'fa-clipboard-list',
    steps: steps(
      ['Daily Log', '<strong>Daily Log</strong> captures one record per calendar day per project — weather, work performed, visitors, and optional detailed manpower grids.', [
        ['Open today', 'Select the date in the log calendar or list; create today’s entry if none exists.'],
        ['Simple vs detailed', 'Use the mode your company prefers — detailed adds crew tables and conditions sections.'],
        ['Link photos', 'Attach photos from <strong>Photos</strong> or upload directly to document site conditions.'],
        ['Superintendent habit', 'Save the log daily before leaving site — owners often review logs for dispute resolution.'],
      ]],
      ['Weekly Report', '<strong>Weekly Report</strong> rolls up progress narrative and metrics for owner distribution — often Friday or month-end.', [
        ['Select week', 'Pick the reporting week; confirm it matches owner contract reporting calendar.'],
        ['Narrative', 'Summarize milestones, delays, and lookahead — pull facts from <strong>Daily Log</strong> and <strong>Schedule</strong>.'],
        ['Export PDF', 'Generate PDF when ready and file a copy in <strong>Documents</strong>.'],
        ['Send', 'Email through <strong>Email</strong> or your owner portal per contract requirements.'],
      ]],
      ['Photos', '<strong>Photos</strong> stores project images with albums, tags, and links to punch, RFIs, and safety.', [
        ['Upload', 'Use upload or mobile camera; add description and location when prompted.'],
        ['Albums', 'Organize by area or date for faster owner walkthrough packages.'],
        ['Link records', 'From punch or RFI forms, pick existing photos instead of re-uploading duplicates.'],
        ['Permissions', 'Owners in portal may see only photos your team publishes to <strong>Client Portal</strong>.'],
      ]],
      ['Safety', '<strong>Safety</strong> tracks observations, incidents, and corrective actions — separate from punch list finish work.', [
        ['New observation', 'Record hazard, location, responsible party, and due date for correction.'],
        ['Severity', 'Use severity levels your company defined in program workflow settings.'],
        ['Close loop', 'Mark resolved when corrected; attach photo proof when required.'],
        ['Reporting', 'Export safety logs for insurance or owner safety meetings.'],
      ]],
      ['Permits & Inspections', '<strong>Permits & Inspections</strong> logs permit numbers, inspection types, pass/fail, and reinspection dates.', [
        ['Permit record', 'Enter authority, permit ID, and expiration so the team avoids stop-work risk.'],
        ['Inspection', 'Log each visit with result; failed inspections need follow-up date and responsible trade.'],
        ['Link schedule', 'Coordinate inspection holds with <strong>Schedule</strong> activities when CPM dates slip.'],
        ['Documents', 'Store issued permits in <strong>Documents</strong> for quick field access.'],
      ]],
      ['Punch List', '<strong>Punch List</strong> tracks deficiencies by location, trade, and status until closed.', [
        ['Create item', 'Add location, description, assignee company, and due date.'],
        ['Status flow', 'Move from open → in progress → ready for review → closed as work completes.'],
        ['Photos', 'Attach before/after photos for owner sign-off.'],
        ['Architect portal', 'Architect users may review and comment without full internal access.'],
      ]],
      ['Deliveries', '<strong>Deliveries</strong> schedules material arrivals, gate times, and crane needs on site.', [
        ['Schedule delivery', 'Enter vendor, material, date/time, and gate or laydown location.'],
        ['Notify', 'Assigned contacts receive alerts when delivery is added or changed.'],
        ['Conflict', 'Check against <strong>Schedule</strong> and site logistics before confirming time.'],
        ['Received', 'Mark received when material is on site; note damage in the log for RFIs if needed.'],
      ]],
    ),
  },
  {
    id: 'schedule-documents',
    title: 'Schedule & documents',
    icon: 'fa-calendar-alt',
    steps: steps(
      ['Schedule', '<strong>Schedule</strong> holds the CPM timeline — activities, dependencies, baseline comparison, and look-ahead views.', [
        ['Gantt view', 'Open the Gantt to see critical path and float; zoom to week or month as needed.'],
        ['Baseline', 'Set baselines after owner approval to compare planned vs actual later.'],
        ['Update progress', 'Superintendents update percent complete or actual dates from field knowledge.'],
        ['Export', 'Publish schedule PDFs to <strong>Documents</strong> for meeting minutes references.'],
      ]],
      ['Drawings', '<strong>Drawings</strong> manages plan sets, sheet numbers, revisions, and markups.', [
        ['Upload set', 'Upload PDF sheets; assign discipline and revision date per company standard.'],
        ['Sheet numbers', 'RFIs and punch items reference these sheets — keep numbering consistent with the architect.'],
        ['Revisions', 'Issue new revisions clearly so field does not build off superseded plans.'],
        ['Markup', 'Use markup tools when enabled to highlight RFIs or coordination notes on sheets.'],
      ]],
      ['Documents', '<strong>Documents</strong> is the project file cabinet — folders, permissions, and attachments from other modules.', [
        ['Folders', 'Use folder templates from <strong>Program Settings</strong> or create job-specific structure.'],
        ['Upload', 'Drag files into folders; set visibility if owners or subs should not see internal files.'],
        ['From modules', 'Pay apps, submittals, and contracts can file PDFs here automatically on submit.'],
        ['Search', 'Search by filename or metadata when you know the owner emailed a doc without telling you the folder.'],
      ]],
      ['Meeting Minutes', '<strong>Meeting Minutes</strong> records attendees, agenda, decisions, and action items per meeting.', [
        ['New meeting', 'Enter meeting type (OAC, safety, coordination), date, and attendees from <strong>Project Directory</strong>.'],
        ['Action items', 'Assign action owners and due dates — track open actions on the next meeting.'],
        ['Distribute', 'Export PDF and email via <strong>Email</strong> or file in <strong>Documents</strong>.'],
        ['RFI / CO link', 'Reference minute decisions when writing RFIs or change events for audit trail.'],
      ]],
      ['Field & docs workflow', 'Keep drawings current, file owner correspondence in <strong>Documents</strong>, and cite sheet numbers on RFIs to reduce rework.', [
        ['Single source', 'Avoid duplicate PDFs in email only — store authoritative copies in <strong>Documents</strong>.'],
        ['Revision discipline', 'When drawings update, notify trades via <strong>Email → Internal</strong> or submittal transmittal.'],
        ['Meetings drive work', 'Close action items from minutes before the next OAC to keep Ball in Court moving.'],
        ['Closeout', 'At end of job, verify all contract documents and as-builts are filed before archival.'],
      ]],
    ),
  },
  {
    id: 'rfis-submittals',
    title: 'RFIs & submittals',
    icon: 'fa-question-circle',
    steps: steps(
      ['RFIs overview', '<strong>RFIs</strong> formalize questions about the contract documents — each item has a number, assignees, due date, and <strong>Ball in Court</strong>.', [
        ['New RFI', 'Click <strong>New RFI</strong>, enter subject, question, spec section, and drawing references.'],
        ['Ball in Court', 'Colored column shows who must respond next — reassign if the wrong person is listed.'],
        ['Official response', 'PM marks the official answer when consensus is reached; do not rely on informal email alone.'],
        ['Cost impact', 'If scope may change, link discussion to a <strong>Change Event</strong> after the RFI is answered.'],
      ]],
      ['RFI workflow', 'Typical flow: draft → submit to architect/engineer → receive answer → distribute → close.', [
        ['Submit', 'Click <strong>Submit</strong> to notify assignees; status and Ball update automatically.'],
        ['Due dates', 'Set realistic due dates; dashboard and notifications flag overdue RFIs.'],
        ['Attachments', 'Attach photos, sketches, or excerpts from <strong>Drawings</strong>.'],
        ['Portal', 'Architect portal users respond inside Case PM so the audit trail stays complete.'],
      ]],
      ['Submittals overview', '<strong>Submittals</strong> track shop drawings, product data, and samples through review cycles tied to spec sections.', [
        ['New submittal', 'Create with spec section, description, responsible sub, and required date.'],
        ['Status', 'Track submitted, in review, approved, approved as noted, or rejected.'],
        ['Resubmit', 'Rejected items need revision upload and new review cycle — do not overwrite history.'],
        ['Lead time', 'Align approval dates with <strong>Schedule</strong> procurement activities.'],
      ]],
      ['Submittal workflow', 'Route to architect/engineer; subs often upload via portal or your team uploads on their behalf.', [
        ['Send', 'Use <strong>Send</strong> or transmittal actions to notify reviewers.'],
        ['Stamp', 'Record review stamp equivalent in status and comments for field release.'],
        ['File PDF', 'Store approved submittals in <strong>Documents</strong> for inspectors and owners.'],
        ['Link drawings', 'Reference sheet numbers when submittal replaces or clarifies plan detail.'],
      ]],
      ['RFIs vs submittals', 'RFIs ask questions; submittals prove what will be installed. Both feed change management when answers alter scope.', [
        ['RFI first', 'When unsure of design intent, RFI before ordering material.'],
        ['Submittal after', 'After approval, sub confirms product matches spec — rejected subs block fabrication.'],
        ['Change path', 'Approved changes that affect cost go to <strong>Change Orders</strong>, not informal RFI notes.'],
        ['Directory', 'Assignees come from <strong>Project Directory</strong> and <strong>Companies</strong> — keep contacts current.'],
      ]],
    ),
  },
  {
    id: 'change-orders-financial',
    title: 'Change orders',
    icon: 'fa-exchange-alt',
    steps: steps(
      ['Why change orders matter', 'Approved changes update contract value, budget, commitments, and pay applications — skipping steps causes billing mismatches.', [
        ['Owner vs sub', 'Owner-side changes affect prime contract billing; sub-side changes affect subcontract POs.'],
        ['Change event hub', 'Start with a <strong>Change Event</strong> when scope shifts; promote to PCOs, RFQs, or change orders from there.'],
        ['SOV lines', 'Dollar detail lives on <strong>PCO</strong>, <strong>CPCO</strong>, and final change order SOV grids — not on COR packages alone.'],
        ['Ball in Court', 'Same workflow column as RFIs — act when the ball is on you.'],
      ]],
      ['Deep guide on the Change Orders page', 'Open <strong>Change Orders</strong> and click header <strong>User guide</strong> while on that page for the full tab-by-tab manual: Change Events, PCO Log, COR Log, RFQs, CPCOs, and Sub Change Orders.', [
        ['Page-specific sections', 'The Change Orders help includes multiple nav sections (overview, change events, RFQ, PCO, etc.) — longer than this summary.'],
        ['Switch guide', 'From the complete user guide, use <strong>Guide for this page only</strong> when you navigated from another module.'],
        ['Practice job', 'Train new estimators on a sandbox project before touching live owner SOV.'],
        ['Prerequisites', 'Set up <strong>Budget</strong> cost codes and <strong>Commitments</strong> before creating events.'],
      ]],
      ['Owner path summary', 'Change Event → PCO with SOV lines → optional COR package → Owner Change Order after approval.', [
        ['ROM on event', 'Enter rough magnitude on the event before pricing is final.'],
        ['PCO pricing', 'Build SOV lines with cost codes and amounts; submit for approval per workflow.'],
        ['COR', 'Groups PCOs for owner signature — amounts roll up from child PCOs.'],
        ['Owner CO', 'Promoted owner change order syncs to budget and owner pay apps when approved.'],
      ]],
      ['Sub path summary', 'Change Event → RFQ to sub → quoted CPCO → Sub Change Order per vendor.', [
        ['RFQ bulk', 'From event lines, use <strong>Add To → RFQs</strong> to send pricing requests per sub.'],
        ['Quote', 'Sub enters quote in portal or your team enters on their behalf.'],
        ['CPCO', 'Accepted quote becomes CPCO draft with SOV lines tied to commitment.'],
        ['Sub CO', 'Promote to sub change order to update commitment and sub billing.'],
      ]],
      ['When to escalate', 'If owner and multiple subs change on one scope shift, one change event can spawn both owner PCOs and sub RFQs — keep one event as the audit hub.', [
        ['One event', 'Avoid duplicate events for the same physical change — merge narrative for owners.'],
        ['Accounting', 'After approval, verify <strong>Budget</strong> and <strong>Accounting</strong> exports reflect new amounts.'],
        ['Pay apps', 'Next <strong>Pay Application</strong> period should pick up approved CO SOV lines automatically when configured.'],
        ['Documents', 'File signed owner CO PDFs in <strong>Documents</strong> for closeout.'],
      ]],
    ),
  },
  {
    id: 'budget-pay',
    title: 'Budget & pay apps',
    icon: 'fa-chart-pie',
    steps: steps(
      ['Budget', '<strong>Budget</strong> is the job cost plan — cost codes, original budget, revisions, and committed vs actual columns.', [
        ['Cost codes', 'Set up codes to match estimating and ERP before transactions accumulate.'],
        ['Revisions', 'Budget revisions document owner-approved changes separate from internal forecast shifts.'],
        ['Commitments column', 'Shows PO totals per code — compare to budget to spot over-commitment early.'],
        ['Export', 'Export for owner reporting or Sage mapping under <strong>Accounting</strong>.'],
      ]],
      ['Forecast', '<strong>Forecast</strong> projects final cost by code — PM and accounting adjust projected completion dollars.', [
        ['Projected final', 'Update forecast when productivity or scope shifts — not only at month-end.'],
        ['Variance', 'Compare forecast to budget and commitments to explain margin to leadership.'],
        ['History', 'Track who changed forecast and when for internal reviews.'],
        ['Link COs', 'Approved change orders should flow into budget — investigate if totals do not move.'],
      ]],
      ['Commitments', '<strong>Commitments</strong> stores subcontract and PO contracts — vendor, amount, retention, and SOV structure.', [
        ['New commitment', 'Create SC-001 style records tied to <strong>Companies</strong> vendors.'],
        ['SOV', 'Commitment SOV lines drive sub pay app billing and CPCO coding.'],
        ['Change orders', 'Sub change orders update commitment value — do not edit commitment total without CO.'],
        ['Insurance', 'Track COI expiration dates when your workflow includes compliance fields.'],
      ]],
      ['Pay Applications', '<strong>Pay Applications</strong> bills the owner by period with G702/G703 and tracks subcontractor applications.', [
        ['New period', 'Create pay app for billing period; confirm schedule of values matches current contract.'],
        ['G702 / G703', 'Complete summary and continuation sheets per owner contract format.'],
        ['Sub tabs', 'Enter or approve sub applications against commitments and retention rules.'],
        ['Submit', 'Workflow submit moves Ball to approver; file PDF in <strong>Documents</strong> after approval.'],
      ]],
      ['Estimating', '<strong>Estimating</strong> supports pre-construction bids — takeoffs, alternates, and comparison to awarded budget.', [
        ['Bid packages', 'Issue packages to subs via <strong>Bid Portal</strong> when enabled.'],
        ['Award', 'When job is won, transfer relevant estimate structure into <strong>Budget</strong> setup.'],
        ['Plan Room', 'Use <strong>Plan Room</strong> for staff plan storage linked to estimating workflows.'],
        ['Marketing link', 'Won pursuits from <strong>Marketing</strong> pipeline should become <strong>Projects</strong> with matching numbers.'],
      ]],
      ['Financial hygiene', 'Match project numbers across Case PM and ERP, approve COs before billing, and reconcile pay apps monthly.', [
        ['Month-end', 'Accounting closes period after pay apps approved and exported.'],
        ['Retention', 'Verify retainage on subs matches commitments before final payment.'],
        ['Audit trail', 'Use <strong>Audit Log</strong> for sensitive financial edits when investigating discrepancies.'],
        ['No silent edits', 'Avoid changing SOV in pay app without corresponding CO or budget revision.'],
      ]],
    ),
  },
  {
    id: 'accounting-marketing',
    title: 'Accounting & marketing',
    icon: 'fa-bullhorn',
    steps: steps(
      ['Accounting module', '<strong>Accounting</strong> is the construction ERP bridge — overview dashboards, GL activity, AP, AR, and sync tools for Sage-style systems.', [
        ['Open Accounting', 'Choose <strong>Accounting</strong> from Financial in the sidebar — staff with financial roles only.'],
        ['Company-wide', 'Some tabs are company-level, not per project — confirm which view you are in.'],
        ['Job mapping', 'Project numbers in <strong>Projects</strong> must match ERP job IDs before export.'],
        ['Deep guide', 'Click header <strong>User guide</strong> on the Accounting page for GL, AP, AR, and export detail.'],
      ]],
      ['GL, AP, and AR', 'General ledger summarizes posted job cost; AP tracks vendor bills; AR tracks owner receivables tied to pay apps.', [
        ['GL', 'Review GL for period totals by project and cost code before closing books.'],
        ['AP', 'Match AP to <strong>Commitments</strong> and sub pay apps — investigate variances.'],
        ['AR', 'AR should align with approved owner <strong>Pay Applications</strong> billing.'],
        ['Export', 'Use integration tabs in <strong>Program Settings</strong> for Sage credentials and test sync.'],
      ]],
      ['Marketing hub', '<strong>Marketing</strong> manages pursuits before they become projects — pipeline, portfolio showcase, campaigns, website leads, and ROI.', [
        ['Pipeline', 'Track opportunities by stage from lead to awarded contract.'],
        ['Portfolio', 'Publish selected completed projects for public or owner-facing showcase.'],
        ['Campaigns', 'Plan email or event campaigns and tie responses back to leads.'],
        ['ROI', 'When a pursuit wins, link to <strong>Projects</strong> to compare marketing spend to contract value.'],
      ]],
      ['Plan Room (staff)', '<strong>Plan Room</strong> under Financial is staff plan storage for estimating and preconstruction — separate from project <strong>Drawings</strong> after kickoff.', [
        ['Upload bids', 'Store invitation-to-bid drawings for estimators.'],
        ['Access', 'Limit folders to estimating team when plans are confidential.'],
        ['Handoff', 'After award, issue formal drawings into project <strong>Drawings</strong> module for construction.'],
        ['Version control', 'Label bid set dates clearly to avoid pricing off wrong revision.'],
      ]],
      ['Website leads', 'Inbound leads from your company website can appear in Marketing for qualification and assignment to estimators.', [
        ['Review queue', 'Open new leads daily so response time stays competitive.'],
        ['Qualify', 'Mark spam or duplicate; assign real leads to a pursuit owner.'],
        ['Convert', 'When qualified, create pipeline opportunity or <strong>Project</strong> draft.'],
        ['Track source', 'Use campaign fields to see which channel produced the lead.'],
      ]],
    ),
  },
  {
    id: 'communication',
    title: 'Communication',
    icon: 'fa-envelope',
    steps: steps(
      ['Email module', 'Sidebar <strong>Email</strong> combines external email threads and <strong>Internal</strong> team messaging when your role sees both tabs.', [
        ['Internal tab', 'Use internal messages for RFIs, CO approvals, and team discussion without leaving Case PM.'],
        ['External tab', 'Connect project email when configured — threads can link to project records.'],
        ['Sub portal', 'Subs may see only <strong>Internal Communications</strong> without external email tab.'],
        ['Attachments', 'Attach files from <strong>Documents</strong> to avoid duplicate storage.'],
      ]],
      ['Internal messages', 'Approval-type internal messages tie to workflow records — responding can advance Ball in Court.', [
        ['Open thread', 'Click message to see linked RFI, pay app, or change order context.'],
        ['Reply', 'Reply in thread so history stays on the job record.'],
        ['Mentions', 'Use mentions when your UI supports @user to notify specific teammates.'],
        ['Do not bypass', 'Official RFI answers still need RFI module official response — internal chat is not a substitute.'],
      ]],
      ['Notifications', 'The header bell lists system alerts — approvals, due dates, mentions, and workflow events.', [
        ['Bell icon', 'Click bell for dropdown; open full <strong>Notifications</strong> page for history.'],
        ['Click through', 'Each notification deep-links to the record needing action.'],
        ['Mark read', 'Clear items after handling so unread count reflects real work.'],
        ['Preferences', 'Adjust notification types in profile or <strong>Program Settings → Notifications</strong>.'],
      ]],
      ['Approvals workflow', 'Many modules use submit → approve chains configured in <strong>Program Settings → Workflow</strong>.', [
        ['Pending queue', 'Filter lists by pending approval or use notifications for your Ball in Court.'],
        ['Approve / reject', 'Use green <strong>Review</strong> or approve buttons — rejection usually requires comment.'],
        ['E-sign', 'Owner COs and pay apps may need e-sign step when enabled.'],
        ['Chain order', 'Second approver cannot act until first approver completes — check Ball in Court column.'],
      ]],
      ['Communication habits', 'Prefer in-app messages for audit trail; email owners per contract; keep sensitive financial discussion on internal threads.', [
        ['Owner-facing', 'Use professional tone on anything that might be exported or forwarded.'],
        ['Record linkage', 'Start messages from the record when possible so context auto-attaches.'],
        ['Daily clear', 'Process notification queue at least once per business day.'],
        ['Escalation', 'If approval stalls, reassign Ball in Court or contact admin — do not create duplicate records.'],
      ]],
    ),
  },
  {
    id: 'admin',
    title: 'Administration',
    icon: 'fa-cog',
    steps: steps(
      ['Companies / Vendors', '<strong>Companies</strong> stores owners, architects, subcontractors, and suppliers used across all projects.', [
        ['New company', 'Add legal name, type, insurance fields, and primary contact.'],
        ['Vendors', 'Subs used on <strong>Commitments</strong> must exist here with correct ERP vendor ID if syncing.'],
        ['Duplicates', 'Search before create — duplicate companies break directory and portal routing.'],
        ['COI', 'Track insurance expiration when your company uses those fields for compliance gates.'],
      ]],
      ['User Management', '<strong>User Management</strong> invites staff, assigns roles, projects, and module permissions.', [
        ['Invite', 'Send invite email; user completes password setup.'],
        ['Role', 'Pick role template (PM, superintendent, accounting, admin) then fine-tune modules.'],
        ['Project list', 'Grant access per project for multi-job organizations.'],
        ['Portal users', 'Create sub users with portal role and tie to vendor company.'],
      ]],
      ['Program Settings', '<strong>Program Settings</strong> is company-wide — numbering, workflow, branding, email, security, integrations, backups.', [
        ['Numbering', 'Set RFI, submittal, CO prefixes before go-live — hard to fix after hundreds of records exist.'],
        ['Workflow', 'Configure approval chains and module toggles — test on sandbox project first.'],
        ['Branding', 'Logo and address appear on pay apps and PDF exports.'],
        ['Sage / ERP', 'Integration tab holds credentials and cost code mapping for <strong>Accounting</strong> export.'],
      ]],
      ['Audit Log', 'Admins with access see <strong>Audit Log</strong> — who changed records, permissions, and settings.', [
        ['Investigate', 'Filter by user, date, or action type when disputing a deletion or amount change.'],
        ['Compliance', 'Export or review for internal audit and security policy.'],
        ['Not field log', 'Audit log is system metadata — daily field narrative stays in <strong>Daily Log</strong>.'],
        ['Deep guide', 'Open <strong>User guide</strong> on Audit Log page for filter and compliance detail.'],
      ]],
      ['Admin caution', 'Document why you changed global settings; wrong numbering or workflow breaks active projects mid-flight.', [
        ['Change log', 'Keep internal note of admin changes with date and reason.'],
        ['Communicate', 'Tell PMs before changing approval chains on live jobs.'],
        ['Backup', 'Confirm backup schedule in <strong>Program Settings</strong> before major upgrades.'],
        ['Least privilege', 'Give users only modules they need — financial data exposure is a real risk.'],
      ]],
    ),
  },
  {
    id: 'operations-portals',
    title: 'Operations & portals',
    icon: 'fa-layer-group',
    steps: steps(
      ['Operations Center', '<strong>Operations</strong> groups extended tools — quick actions, transmittals, WIP views, and integrations depending on your configuration.', [
        ['Open Operations', 'Select <strong>Operations</strong> from Field & Docs when enabled for your company.'],
        ['Quick Add', 'Header <strong>Quick Add</strong> (when shown) saves essentials fast — finish detail in Operations or target module.'],
        ['Promote / validate', 'Some rows support promote, validate, or sync actions to ERP or document packages.'],
        ['Training', 'New users should explore Operations with a PM before using bulk tools on production data.'],
      ]],
      ['Client Portal', '<strong>Client Portal</strong> configures what owners see — progress photos, documents, schedule snapshots, and approvals.', [
        ['Publish', 'Choose which photos and documents are owner-visible — internal files stay in staff-only folders.'],
        ['Preview', 'Use preview as owner when available to verify branding and content.'],
        ['Approvals', 'Owner e-sign or approval steps may route through portal notifications.'],
        ['Support', 'Owners need user accounts under <strong>User Management</strong> with client role.'],
      ]],
      ['Subcontractor portals', 'Subs use reduced menus — <strong>RFQ Portal</strong>, <strong>Bid Portal</strong>, <strong>Submittals</strong>, and <strong>Pay Applications</strong> for their company only.', [
        ['RFQ Portal', 'Subs quote change RFQs without seeing full job financials.'],
        ['Bid Portal', 'Subs upload bid responses during preconstruction.'],
        ['Company link', 'User must belong to vendor company on <strong>Project Directory</strong> or SOV.'],
        ['Invite', 'Send portal invite from <strong>User Management</strong> after company is correct.'],
      ]],
      ['Architect portal', 'Architect users see RFIs, submittals, punch, and selected docs — not internal budget or commitments.', [
        ['Respond RFIs', 'Official responses should be entered in <strong>RFIs</strong> module for audit.'],
        ['Submittal review', 'Stamp review status in <strong>Submittals</strong> rather than email-only approval.'],
        ['Punch', 'Comment on punch items assigned to design team when in scope.'],
        ['Limits', 'Architect cannot approve owner pay apps or edit SOV — by design.'],
      ]],
      ['Portal hygiene', 'Deactivate users when subs leave the job; rotate portal access at project closeout.', [
        ['Offboarding', 'Remove or disable user in <strong>User Management</strong> when sub PM changes firms.'],
        ['Directory', 'Update <strong>Project Directory</strong> contacts when routing changes.'],
        ['Closeout', 'Archive project and confirm portal users lose access per company policy.'],
        ['Security', 'Never share one portal login across multiple people — audit log identifies by user.'],
      ]],
    ),
  },
  {
    id: 'module-directory',
    title: 'Module directory',
    icon: 'fa-list',
    steps: steps(
      ['Main section', 'Core navigation entries every staff user learns first.', [
        ['Dashboard', 'Morning overview tiles for the active project — first action: confirm header project, scan open counts.'],
        ['Projects', 'Create and manage job records — first action: <strong>New Project</strong> or open row to set team.'],
        ['Job Map', 'Geographic map of company projects — first action: verify project addresses for marker accuracy.'],
        ['Project Directory', 'Auto-built roster of people and companies on the job — first action: refresh after updating commitments.'],
        ['Email', 'External and internal messaging — first action: open <strong>Internal</strong> tab for team approvals.'],
        ['Safety', 'Observations and incident tracking — first action: log new observation with location and assignee.'],
      ]],
      ['Core modules', 'Daily project execution and contract communication tools.', [
        ['Daily Log', 'One dated field record per day — first action: create or open today’s log and save weather and work.'],
        ['Weekly Report', 'Owner progress summary by week — first action: select week and draft narrative.'],
        ['Schedule', 'CPM timeline and baselines — first action: update activity dates or percent complete.'],
        ['RFIs', 'Formal design and spec questions — first action: <strong>New RFI</strong> with drawing references.'],
        ['Change Orders', 'Contract change workflow — first action: open Change Events tab or read page-specific user guide.'],
        ['Submittals', 'Shop drawing and product data review — first action: <strong>New Submittal</strong> with spec section.'],
        ['Punch List', 'Deficiency tracking — first action: add item with location and responsible company.'],
      ]],
      ['Financial section', 'Cost plan, ERP, and billing — restricted by role.', [
        ['Estimating', 'Preconstruction bids and takeoffs — first action: open active estimate or bid package.'],
        ['Plan Room', 'Staff bid document library — first action: upload current IFB drawing set.'],
        ['Budget', 'Job cost plan by code — first action: verify cost codes match estimate and ERP.'],
        ['Forecast', 'Projected final cost — first action: update forecast columns after scope or productivity change.'],
        ['Accounting', 'GL / AP / AR and ERP sync — first action: review period dashboard before export.'],
        ['Commitments', 'Subcontracts and POs — first action: <strong>New Commitment</strong> for each awarded sub.'],
        ['Pay Applications', 'Owner and sub billing by period — first action: create pay app for current billing cycle.'],
      ]],
      ['Field & docs section', 'Files, logistics, and extended operations.', [
        ['Photos', 'Project image library — first action: upload today’s site photos with description.'],
        ['Documents', 'Folder file cabinet — first action: upload contract or file owner PDF to correct folder.'],
        ['Drawings', 'Plan sheets and revisions — first action: upload latest revision set with sheet numbers.'],
        ['Deliveries', 'Material delivery schedule — first action: schedule next delivery with gate time.'],
        ['Operations', 'Extended ops tools — first action: open tool relevant to transmittal or WIP task.'],
        ['Marketing', 'Pipeline and campaigns — first action: review new website leads or move pursuit stage.'],
        ['Client Portal', 'Owner-facing publish settings — first action: publish approved photos or documents.'],
        ['Permits & Inspections', 'Permit and inspection log — first action: log inspection result with date.'],
        ['Meeting Minutes', 'Meeting records and actions — first action: create minutes for today’s OAC.'],
      ]],
      ['Admin section', 'Company configuration — admin roles only.', [
        ['Companies / Vendors', 'Master company list — first action: search before adding duplicate vendor.'],
        ['User Management', 'Users and permissions — first action: invite new teammate with correct role.'],
        ['Program Settings', 'Global defaults — first action: review numbering before first RFI/CO on new deployment.'],
        ['Audit Log', 'System activity history — first action: filter by user and date for investigation.'],
      ]],
      ['Portal-only links (when applicable)', 'External users may see these instead of full sidebar.', [
        ['RFQ Portal', 'Sub quotes on change RFQs — first action: open pending RFQ and enter quote.'],
        ['Bid Portal', 'Sub bid upload — first action: open invited package and submit proposal.'],
        ['Internal Communications', 'Sub team messaging — first action: read threads tied to your company work.'],
        ['Pay Applications (sub)', 'Sub billing view — first action: complete sub application for open period.'],
      ]],
      ['How to learn a new module', 'Open the module, click header <strong>User guide</strong> for page-specific steps, then practice one create → save → submit cycle on a test project.', [
        ['Read guide', 'Page guide is shorter and focused — complete guide (this document) is for onboarding overview.'],
        ['One record', 'Create one test RFI or punch item end-to-end before training the whole crew.'],
        ['Delete test', 'Remove or close test records so dashboards stay clean — or use dedicated sandbox project.'],
        ['Ask PM', 'Your company may have naming conventions beyond what the software requires — follow internal SOP.'],
      ]],
    ),
  },
];

global.CasePMPageHelpGuides = global.CasePMPageHelpGuides || {};
global.CasePMPageHelpGuides.app = {
  title: 'Case PM',
  subtitle: 'Complete user guide for new users — updated as the product evolves. Open any time from the header.',
  sections: USER_GUIDE_SECTIONS,
};

global.CasePMPageHelpGuides.marketing = singleGuide(
  'Marketing',
  'Pursuits, pipeline, portfolio, campaigns, website leads, and ROI before jobs become Projects.',
  [
    ['Pipeline view', 'The pipeline shows opportunities by stage from lead through awarded — drag or edit stage when your role allows.', [
      ['Open Marketing', 'Click <strong>Marketing</strong> in the sidebar under Field & Docs.'],
      ['Stages', 'Typical stages include lead, qualifying, proposal, negotiation, and won/lost — match your company CRM practice.'],
      ['Move stage', 'Update stage when owner feedback arrives so leadership sees accurate funnel.'],
      ['Owner', 'Assign pursuit owner so notifications and tasks route to the right estimator or PM.'],
    ]],
    ['Portfolio', 'Portfolio showcases completed work for proposals and public website — curate projects that represent your brand.', [
      ['Select projects', 'Pick completed jobs with strong photos and owner permission to publish.'],
      ['Descriptions', 'Write short captions emphasizing scope, value, and location for marketing site sync.'],
      ['Media', 'Pull hero images from <strong>Photos</strong> or upload marketing-specific crops.'],
      ['Publish', 'Toggle visibility when case study is approved by leadership.'],
    ]],
    ['Campaigns', 'Campaigns track outbound effort — email blasts, events, or ad links — and tie responses to lead records.', [
      ['New campaign', 'Create campaign with name, date range, and channel type.'],
      ['Audience', 'Define target segment or import lead list per your process.'],
      ['Track UTM', 'Use tracked links on website so <strong>Website leads</strong> show campaign source.'],
      ['Results', 'Review open and response metrics after send to judge effectiveness.'],
    ]],
    ['Website leads', 'Inbound leads from your company site appear in a queue for qualification.', [
      ['Daily review', 'Open leads tab each morning — speed matters for competitive bids.'],
      ['Qualify', 'Mark junk or duplicate; assign real inquiries to pursuit owner.'],
      ['Convert', 'Create pipeline opportunity from qualified lead with one action when available.'],
      ['Follow-up', 'Log next step date so leads do not stall in queue.'],
    ]],
    ['ROI reporting', 'When pursuits win, link awarded contract to <strong>Projects</strong> to compare marketing spend and effort to revenue.', [
      ['Won stage', 'Move opportunity to won with estimated or actual contract value.'],
      ['Project link', 'Create or link <strong>Project</strong> with same name and number for clean reporting.'],
      ['Spend', 'Enter campaign or event cost when tracking full ROI.'],
      ['Review quarterly', 'Leadership reviews cost per won job and channel effectiveness.'],
    ]],
    ['Handoff to estimating', 'Qualified pursuits become estimates — open <strong>Estimating</strong> or <strong>Plan Room</strong> without duplicating pursuit data manually when integration fields exist.', [
      ['Award path', 'After win, budget setup in <strong>Budget</strong> should reference estimate structure.'],
      ['Lost pursuits', 'Mark lost with reason code for future pipeline analytics.'],
      ['Portfolio update', 'Add notable wins to portfolio after completion photo shoot.'],
      ['Permissions', 'Marketing users may not see <strong>Budget</strong> — coordinate handoff with estimating lead.'],
    ]],
  ],
  'fa-bullhorn'
);

global.CasePMPageHelpGuides.accounting = singleGuide(
  'Accounting',
  'Construction ERP overview — GL, AP, AR, job cost alignment, and Sage-style export.',
  [
    ['Module overview', '<strong>Accounting</strong> summarizes financial position across jobs and connects Case PM job cost to your ERP.', [
      ['Who sees it', 'Typically accounting, controller, and admin roles — not field supers by default.'],
      ['Company vs project', 'Some tabs are enterprise-wide; others filter by project from header picker.'],
      ['Not a replacement', 'Case PM remains project system of record for SOV and pay apps — ERP remains books of record after post.'],
      ['Settings first', 'Configure <strong>Program Settings → Integrations / Sage</strong> before first export.'],
    ]],
    ['General ledger (GL)', 'GL view rolls up posted or staged amounts by account, project, and period for reconciliation.', [
      ['Open GL tab', 'Navigate to GL section within <strong>Accounting</strong>.'],
      ['Period', 'Select accounting period matching your close calendar.'],
      ['By job', 'Filter to one <strong>Project</strong> number to reconcile single job month-end.'],
      ['Investigate', 'Drill to source pay app or CO when line does not match expectation.'],
    ]],
    ['Accounts payable (AP)', 'AP tracks vendor obligations — align with <strong>Commitments</strong> and subcontractor pay applications.', [
      ['Vendor bills', 'Enter or import bills tied to vendor from <strong>Companies</strong>.'],
      ['Match commitment', 'Bill amount should match sub pay app approval plus retention rules.'],
      ['Retention', 'Hold retainage per commitment until release milestone.'],
      ['Export', 'Post approved AP batch to ERP when integration is enabled.'],
    ]],
    ['Accounts receivable (AR)', 'AR tracks owner billing — should mirror approved owner <strong>Pay Applications</strong>.', [
      ['Owner invoice', 'AR balance moves when pay app is approved and billed.'],
      ['Retainage', 'Separate retainage receivable when contract requires until final completion.'],
      ['Aging', 'Use aging view to chase owner payments before lien deadlines.'],
      ['Disputes', 'If owner disputes line, resolve in pay app or CO before adjusting AR manually.'],
    ]],
    ['Job cost alignment', 'Every export depends on matching project numbers, cost codes, and vendor IDs between Case PM and ERP.', [
      ['Project number', 'Same ID in <strong>Projects</strong> and Sage job field.'],
      ['Cost codes', 'Map codes in integration settings — unmapped codes fail export.'],
      ['Vendors', 'Map <strong>Companies</strong> to ERP vendor ID before AP post.'],
      ['Test job', 'Run test export on small project before month-end bulk.'],
    ]],
    ['Month-end close', 'Typical close: approve pay apps → verify budget/forecast → export job cost → reconcile GL in ERP.', [
      ['Lock period', 'Avoid editing approved pay apps after export without accounting sign-off.'],
      ['CO timing', 'Approved COs should hit budget before close so GL matches commitment.'],
      ['Audit', 'Use <strong>Audit Log</strong> if numbers shifted after close.'],
      ['Documentation', 'File exported reports in <strong>Documents</strong> or ERP per policy.'],
    ]],
  ],
  'fa-calculator'
);

global.CasePMPageHelpGuides.audit_log = singleGuide(
  'Audit Log',
  'View system activity, filter by user and action, and support compliance reviews.',
  [
    ['What is logged', 'The audit log records significant actions — creates, updates, deletes, logins, permission changes, and settings edits.', [
      ['Not daily log', 'Field narrative lives in <strong>Daily Log</strong>; audit log is system metadata.'],
      ['Admin access', 'Typically only admins see full audit log — ask admin if you need investigation.'],
      ['Retention', 'Retention period follows company IT policy and server configuration.'],
      ['Immutable', 'Users cannot edit audit rows — only view and export.'],
    ]],
    ['Open and browse', 'Navigate to <strong>Audit Log</strong> under Admin in the sidebar.', [
      ['Default view', 'Recent events appear newest first with timestamp, user, action, and target record.'],
      ['Pagination', 'Use next page for older history — large jobs generate many rows.'],
      ['Detail row', 'Click row when detail drawer shows field-level before/after values.'],
      ['Export', 'Export CSV or print for external auditor when export button is available.'],
    ]],
    ['Filters', 'Narrow results by date range, user, action type, module, or project when filters are shown.', [
      ['Date range', 'Set start and end to investigation window — e.g. week when amount changed.'],
      ['User filter', 'Pick one user to review actions during dispute about who deleted RFIs.'],
      ['Action type', 'Filter create/update/delete/login for faster scanning.'],
      ['Clear filters', 'Reset when result set is empty — filters may be too narrow.'],
    ]],
    ['Compliance use cases', 'Support security reviews, SOC-style access audits, and litigation support with objective timestamps.', [
      ['Access review', 'Quarterly: sample admin permission changes in audit log.'],
      ['Termination', 'After employee offboarding, verify no login events after termination date.'],
      ['Financial dispute', 'Correlate pay app edit timestamp with user for internal investigation.'],
      ['Policy', 'Document who may export audit data and how long exports are stored.'],
    ]],
    ['Related admin tools', 'Pair audit log with <strong>User Management</strong> and <strong>Program Settings</strong> when fixing root cause.', [
      ['Fix permissions', 'If unauthorized edit occurred, revoke module access in <strong>User Management</strong>.'],
      ['Settings change', 'Compare audit entry to <strong>Program Settings</strong> backup notes.'],
      ['Notify leadership', 'Serious security events escalate per company incident plan.'],
      ['Do not alarm field', 'Routine daily log saves are normal volume — focus on admin and financial mutations.'],
    ]],
  ],
  'fa-history'
);

})(window);
