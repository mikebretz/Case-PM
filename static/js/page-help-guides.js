(function(global){ 'use strict';
function steps(...items){ return items.map(([title, body]) => ({title, body})); }
function singleGuide(title, subtitle, stepPairs, icon='fa-compass'){
  return { title, subtitle, sections: [{ id:'main', title:'How to use', icon, steps: steps(...stepPairs) }] };
}

const CHANGE_ORDERS_SECTIONS = [
  {
    id: 'overview',
    title: 'Start here',
    icon: 'fa-compass',
    steps: steps(
      ['What this page does', 'This page tracks every change to the project contract — extra work, credits, and subcontractor changes. Think of it as the money side of “something changed on the job.”'],
      ['Two main paths', '<strong>Owner path</strong> (money from / with the owner): Change Event → PCO → COR (optional package) → Owner Change Order.<br><br><strong>Subcontractor path</strong> (money with subs): Change Event → RFQ → CPCO → Sub Change Order (one per sub).'],
      ['Where the line items live', 'Detailed cost lines (Schedule of Values / SOV) are entered on <strong>PCOs</strong>, <strong>CPCOs</strong>, and final <strong>Change Orders</strong>. A <strong>COR</strong> does not have its own line items — it only groups PCOs for approval.'],
      ['Pick a tab', 'Use the tabs across the top to work on each type. The colored <strong>Ball in Court</strong> column tells you who needs to act next.'],
      ['Set up first', 'Confirm cost codes and commitments exist under <strong>Budget</strong> and <strong>Commitments</strong> before creating change events so SOV lines have valid codes to attach to.'],
    ),
  },
  {
    id: 'change-events',
    title: 'Change Events',
    icon: 'fa-bolt',
    steps: steps(
      ['What it is', 'A Change Event is the starting notebook for a scope change. One event can affect several subcontractors.'],
      ['Step 1 — Create the event', 'Open the <strong>Change Events</strong> tab → click inside the list area or use the event actions → give it a title, ROM (rough guess) amount, and description.'],
      ['Step 2 — Add line items', 'Open the event to see the detail panel. Add one row per subcontractor / commitment: cost code, vendor, commitment #, and amount.'],
      ['Step 3 — Bulk create downstream docs', 'Check the rows you need, then use <strong>Add To →</strong><br>• <strong>RFQs</strong> — ask subs for pricing (one RFQ per sub)<br>• <strong>CPCOs</strong> — draft commitment PCO per sub<br>• <strong>Draft CCOs</strong> — draft sub change order per sub<br><br>The system groups lines by vendor + commitment automatically.'],
      ['Step 4 — Submit for pricing', 'Use <strong>Submit for Pricing</strong> when the event is ready. Approvers can review from the green <strong>Review</strong> button.'],
      ['Step 5 — Track status', 'Watch the event status and Ball in Court column. When pricing is complete, promote lines to RFQs, CPCOs, or PCOs as needed.'],
    ),
  },
  {
    id: 'rfq',
    title: 'RFQs',
    icon: 'fa-envelope',
    steps: steps(
      ['What it is', 'RFQ = Request for Quote. You ask a subcontractor how much their part of the change will cost.'],
      ['Step 1 — Create or receive', 'RFQs can be created from a Change Event (bulk) or with <strong>New RFQ</strong>. You must pick the subcontractor company.'],
      ['Step 2 — Send to the sub', 'While status is <strong>Draft</strong>, click <strong>Send</strong>. Ball moves to the subcontractor.'],
      ['Step 3 — Sub quotes', 'The sub enters a quote amount (portal or your team on their behalf). Status becomes <strong>Quoted</strong>.'],
      ['Step 4 — Accept → CPCO', 'Click <strong>Accept→CPCO</strong> to turn the quote into a draft Commitment PCO (CPCO) with SOV lines filled in.'],
      ['Step 5 — Decline or revise', 'If the quote is wrong, use revise / decline actions and send a new RFQ rather than editing an accepted CPCO without review.'],
    ),
  },
  {
    id: 'cpco',
    title: 'CPCO Log',
    icon: 'fa-file-lines',
    steps: steps(
      ['What it is', 'CPCO = Commitment Potential Change Order. It is the sub-side “draft change” before it becomes a real subcontract change order.'],
      ['Where SOV lines go', 'Each CPCO has its own Schedule of Values lines (cost code, description, amount). These usually come from the Change Event or accepted RFQ.'],
      ['Step 1 — Review the CPCO', 'Open the <strong>CPCO Log</strong> tab. Check vendor, amount, and status.'],
      ['Step 2 — Edit SOV if needed', 'Open the CPCO form and adjust SOV rows before promoting. Line items live here — not on the COR.'],
      ['Step 3 — Promote to Sub CO', 'Click <strong>→ SCO</strong> to create a draft <strong>Subcontractor Change Order</strong> with the same SOV lines.'],
      ['One sub per order', 'You cannot mix two subcontractors on one commitment change order. Each sub / commitment gets its own CPCO and its own Sub CO.'],
    ),
  },
  {
    id: 'sub-co',
    title: 'Sub Change Orders',
    icon: 'fa-hard-hat',
    steps: steps(
      ['What it is', 'A formal change to a subcontract — adds or moves money on that sub’s contract.'],
      ['Step 1 — Create or promote', 'Use <strong>New Sub CO</strong> (toolbar) for a manual entry, or promote from a CPCO / Change Event bulk action.'],
      ['Step 2 — Fill in SOV lines', 'In the form, use the <strong>Schedule of Values (SOV)</strong> grid: cost code, cost type, description, and amount. At least one row is required before approval.'],
      ['Step 3 — Pick the kind', '<strong>Contract Add</strong> — new money on the sub contract.<br><strong>Budget Transfer</strong> — move money between cost codes (must net to zero).<br><strong>Owner CO Backcharge</strong> — tie to an owner change order.'],
      ['Step 4 — Submit & approve', 'Save as <strong>Draft</strong> → <strong>Submit</strong>. Flow: Project Manager → Contractor Accounting → <strong>Approved</strong>.'],
      ['Step 5 — After approval', 'Approved sub COs update budget and pay application SOV for that subcontractor.'],
      ['Step 6 — ERP export', 'Check the <strong>ERP Queue</strong> tab if your company syncs approved sub COs to accounting.'],
    ),
  },
  {
    id: 'pco',
    title: 'PCO Log',
    icon: 'fa-lightbulb',
    steps: steps(
      ['What it is', 'PCO = Potential Change Order (owner side). It is the working draft of a change you may bill the owner.'],
      ['Step 1 — Create a PCO', 'Click <strong>New PCO</strong> in the toolbar. Enter title, company (if needed), and description.'],
      ['Step 2 — Enter SOV lines', 'Use the <strong>Schedule of Values (SOV)</strong> table at the bottom of the form. Each row is a budget line: cost code, cost type, description, amount.'],
      ['Step 3 — Submit through review', 'Save → <strong>Submit</strong>. Approvals: Open → Pricing → Pending Review → <strong>Approved for CO</strong>.'],
      ['Step 4 — Promote to Change Order', 'When status is <strong>Approved for CO</strong>, click <strong>Promote to CO</strong> (or use the drawer action). SOV lines copy to the owner Change Order.'],
      ['Tip — COR packaging', 'Before promoting, you can attach PCOs to a COR (see COR Log) to send several PCOs through one owner approval package.'],
      ['Remember', 'COR packages PCOs — it does not replace SOV entry on each PCO.'],
    ),
  },
  {
    id: 'cor',
    title: 'COR Log',
    icon: 'fa-inbox',
    steps: steps(
      ['What it is', 'COR = Change Order Request. It is a <strong>folder</strong> that groups one or more owner PCOs for formal review. It does <strong>not</strong> have its own SOV lines.'],
      ['Step 1 — Build PCOs first', 'Create owner PCOs and enter their SOV lines before making a COR.'],
      ['Step 2 — New COR', 'COR Log tab → <strong>New COR</strong> → title & description → check the PCOs to package → Save.'],
      ['Step 3 — Review the rollup', 'The COR amount is the sum of packaged PCOs. When you review, you will see a read-only SOV rollup pulled from those PCOs.'],
      ['Step 4 — Submit & approve', 'Submit the COR. Approval path: Project Manager → Architect → Owner (e-sign if required) → Contractor Accounting → Approved.'],
      ['Step 5 — After approval', 'Linked PCOs move forward for promotion. Promote each PCO to an Owner Change Order when ready.'],
      ['Do not enter SOV here', 'If dollar lines are missing, edit the underlying PCOs — not the COR.'],
    ),
  },
  {
    id: 'owner-co',
    title: 'Change Orders',
    icon: 'fa-file-signature',
    steps: steps(
      ['What it is', 'The final, approved change to the owner / prime contract. This is what updates contract value, budget, and billing.'],
      ['Step 1 — Create or promote', 'Use <strong>New CO</strong> for a manual owner CO, or <strong>Promote to CO</strong> from an approved PCO (recommended — SOV copies over).'],
      ['Step 2 — SOV lines', 'Edit the <strong>Schedule of Values (SOV)</strong> grid. Each line needs cost code, cost type, and amount.'],
      ['Step 3 — Submit', 'Save as Draft → Submit. Ball goes to Project Manager.'],
      ['Step 4 — Approval chain', 'Project Manager → Architect → Owner (e-sign) → Contractor Accounting → <strong>Approved</strong>.'],
      ['Step 5 — Sync', 'After approval, use <strong>Sync to SOV</strong> if shown — pushes lines to Budget and Pay Applications. Check the ERP Queue for accounting export.'],
      ['Sub COs column', 'Owner COs may spawn or link related subcontractor change orders so sub costs stay tied to the owner change.'],
    ),
  },
  {
    id: 'erp',
    title: 'ERP Queue',
    icon: 'fa-cloud-arrow-up',
    steps: steps(
      ['What it is', 'A waiting list of financial events (approved COs, CORs, etc.) ready for your accounting system (e.g. Sage 300).'],
      ['Step 1 — Open the tab', 'Go to <strong>ERP Queue</strong> after a change is approved.'],
      ['Step 2 — Review', 'Click <strong>Review ERP</strong> on pending items. Accounting confirms amounts and notes.'],
      ['Step 3 — Posted', 'When status shows posted, the export to accounting is complete.'],
      ['Settings', 'Configure Sage 300 defaults under <strong>Program Settings → Sage 300</strong> before your first export.'],
    ),
  },
  {
    id: 'glossary',
    title: 'Quick glossary',
    icon: 'fa-book',
    steps: steps(
      ['ROM', 'Rough Order of Magnitude — a quick estimate, not final.'],
      ['SOV', 'Schedule of Values — the line-by-line breakdown of cost codes and dollars on a PCO, CPCO, or Change Order.'],
      ['Ball in Court', 'Who must act next (e.g. Project Manager, Owner, Subcontractor).'],
      ['PCO vs CPCO', 'PCO = owner-side draft. CPCO = subcontractor-side draft.'],
      ['COR', 'Packages PCOs for owner approval — no separate SOV.'],
      ['Commitment', 'A subcontract or PO contract number (e.g. SC-001) tied to one vendor.'],
    ),
  },
];

global.CasePMPageHelpGuides = {
  dashboard: singleGuide(
    'Dashboard',
    'Your project command center — tiles, charts, and quick links.',
    [
      ['Pick a project', 'Use the project selector in the header. Most dashboard tiles show data for the <strong>active project</strong> only.'],
      ['Choose a view', 'Toggle between <strong>Overview</strong> and <strong>Customize</strong> (if shown) to switch preset layouts or edit your grid.'],
      ['Read the tiles', 'Each tile summarizes one area — open items, budget snapshot, schedule, safety, etc. Click a tile title or link to jump to that module.'],
      ['Customize layout', 'In customize mode, drag tiles to rearrange. Resize from corners. Changes save per user for this project.'],
      ['Watch charts', 'Bar and line charts roll up counts or dollars. Hover for details; click legend items to hide series.'],
      ['Act on alerts', 'Red or amber counts usually mean overdue RFIs, open punch items, or pending approvals — open the linked page and clear the queue.'],
      ['Reset if needed', 'Use <strong>Reset layout</strong> (when available) to restore the default tile set without losing project data.'],
      ['Daily habit', 'Start here each morning: confirm active project, scan open counts, then drill into the highest-priority module.'],
    ],
    'fa-gauge-high'
  ),

  projects: singleGuide(
    'Projects',
    'Create projects, set status, and open project tools.',
    [
      ['Browse the list', 'The projects table shows name, number, status, and key dates. Use search and filters to find a job.'],
      ['Open a project', 'Click a row to open the project detail page. Set it as active from the header project picker when you want dashboard data for that job.'],
      ['Create a project', 'Click <strong>New Project</strong>. Enter name, project number, address, dates, and client company. Save as <strong>Active</strong> when ready to use modules.'],
      ['Set project team', 'On the project detail page, assign roles (PM, superintendent, etc.) so workflow and notifications route correctly.'],
      ['Configure numbering', 'Project numbers should match accounting (Sage) if you sync financials. Adjust global prefixes under <strong>Program Settings → Numbering</strong>.'],
      ['Archive completed jobs', 'Change status to <strong>Complete</strong> or <strong>Archived</strong> to hide clutter while keeping history and documents.'],
      ['Link to directory', 'Use <strong>Project Directory</strong> for contacts on this job — companies and people tied to the active project.'],
      ['Permissions', 'If you cannot see a project, ask an admin to grant module access under <strong>Users</strong> or project-level permissions.'],
    ],
    'fa-folder-tree'
  ),

  project_directory: singleGuide(
    'Project Directory',
    'Contacts and companies assigned to the active project.',
    [
      ['Select the project', 'The directory lists people and companies for the <strong>active project</strong> in the header. Switch projects to see a different roster.'],
      ['Add a contact', 'Click <strong>Add Contact</strong>. Pick or create a company, then enter name, role, email, and phone.'],
      ['Link existing companies', 'Pull from the global <strong>Companies</strong> list so RFIs, submittals, and commitments use the same vendor record.'],
      ['Set roles', 'Role labels (Owner, Architect, Sub, etc.) help filters and email routing. Be consistent across projects.'],
      ['Mark primary contacts', 'Flag primary contacts for each trade or company so field staff know who to call.'],
      ['Portal users', 'If a contact needs portal access (sub RFQ, submittals), ensure their user account exists under <strong>Users</strong> and is tied to the right company.'],
      ['Export or print', 'Use export / print actions (when shown) for O&amp;M handoff or meeting attendee lists.'],
      ['Keep it current', 'Update phone and email when subs change PMs — outdated directory entries cause missed RFIs and approvals.'],
    ],
    'fa-address-book'
  ),

  daily_log: singleGuide(
    'Daily Log',
    'Record weather, crew, work performed, and photos by day.',
    [
      ['Pick the date', 'Use the date picker or calendar strip. One log per project per day is typical.'],
      ['Create today\'s log', 'Click <strong>New Log</strong> or open an empty day. Status starts as draft until submitted.'],
      ['Weather & conditions', 'Enter temperature, conditions, and any delays (rain, inspection hold). Owners often require this for claims support.'],
      ['Work performed', 'Describe trades on site, locations, and percent complete. Keep entries factual and brief.'],
      ['Manpower & equipment', 'Add headcount by company and major equipment if your template includes those sections.'],
      ['Attach photos', 'Link photos from the <strong>Photos</strong> module or upload directly so the log matches visual evidence.'],
      ['Submit', 'When complete, <strong>Submit</strong> the log. Supervisors may review or lock past dates per program policy.'],
      ['Review history', 'Scroll prior days or export PDFs for owner reports and weekly summaries.'],
    ],
    'fa-clipboard-list'
  ),

  weekly_report: singleGuide(
    'Weekly Report',
    'Summarize job progress for owners and stakeholders.',
    [
      ['Select week ending', 'Choose the report week (usually Friday or Sunday). Data may pull from daily logs and schedule.'],
      ['Create or open report', 'Click <strong>New Report</strong> for a blank week or open an existing draft.'],
      ['Fill executive summary', 'Write 2–4 sentences on overall status, milestones hit, and major risks.'],
      ['Progress by area', 'Update percent complete, lookahead, and constraints for each building area or phase.'],
      ['Safety & quality', 'Note incidents, inspections passed/failed, and open punch or submittal items affecting turnover.'],
      ['Photos & links', 'Attach key progress photos and reference open RFIs or change orders if they drive schedule.'],
      ['Internal review', 'PM reviews, then mark <strong>Ready for Owner</strong> or distribute PDF per your workflow.'],
      ['Distribute', 'Email PDF or share via <strong>Documents</strong>. Copy prior week to save time on recurring sections.'],
    ],
    'fa-calendar-week'
  ),

  rfis: singleGuide(
    'RFIs',
    'Request for Information — formal questions that need a written answer (Procore-style Ball in Court).',
    [
      ['Required to open', 'Subject, question, assignees, due date, and <strong>RFI Manager</strong> are required before an RFI can be opened.'],
      ['Create Draft or Open', 'Use <strong>Save Draft</strong> to keep the ball with the RFI Manager, or <strong>Save &amp; Open</strong> to notify assignees immediately.'],
      ['Ball in Court', 'Tracks who owns the RFI: Manager reviews drafts; assignees respond when open; ball returns to the manager after each reply.'],
      ['Assign from directory', 'Pick the RFI Manager, assignees, and distribution list from the <strong>Project Directory</strong> so notifications reach the right people.'],
      ['Respond', 'Assignees submit responses in Procore, email, or Case PM. Each reply is logged; the manager reviews all answers.'],
      ['Official answer', 'The RFI Manager marks one response as the <strong>Official Response</strong>, then closes the RFI when the field can proceed.'],
      ['Private RFIs', 'Private RFIs are visible only to the creator, manager, assignees, and distribution — not the full project team.'],
      ['Cost impact', 'If the answer affects scope, cost, or schedule, create a <strong>Change Event</strong> — the RFI alone does not change the budget.'],
    ],
    'fa-circle-question'
  ),

  change_orders: {
    title: 'Change Orders',
    subtitle: 'Owner and subcontract changes — events, PCOs, COR packages, and approvals.',
    sections: CHANGE_ORDERS_SECTIONS,
  },

  estimating: singleGuide(
    'Estimating',
    'Build estimates, takeoffs, and bid comparisons.',
    [
      ['Open an estimate', 'Select a project estimate from the list or click <strong>New Estimate</strong> to start a fresh bid.'],
      ['Set structure', 'Organize by division / cost code. Match your budget structure so awarded numbers import cleanly.'],
      ['Enter quantities', 'Add line items with quantity, unit, unit cost, and extended total. Use formulas where supported.'],
      ['Takeoff tools', 'Open the takeoff popout (when available) to measure from PDF plans and push quantities to line items.'],
      ['Adjust markup', 'Apply overhead, profit, and bond percentages at the estimate or section level per company standards.'],
      ['Compare alternates', 'Use alternate sections for VE options without duplicating the whole estimate.'],
      ['Send to portal', 'Share read-only or editable views with subs via the <strong>Estimate Portal</strong> link for bid input.'],
      ['Award to budget', 'When the job is won, export or sync awarded amounts to <strong>Budget</strong> (per your admin workflow).'],
    ],
    'fa-calculator'
  ),

  pay_applications: singleGuide(
    'Pay Applications',
    'Bill the owner by period — SOV, retainage, and approvals.',
    [
      ['Open pay app list', 'Each row is a billing period (usually monthly). Status shows draft, submitted, or approved.'],
      ['Create new period', 'Click <strong>New Pay App</strong>. Pick period dates; SOV lines often copy from budget or prior app.'],
      ['Enter work completed', 'For each SOV line, enter work completed this period and stored materials if allowed.'],
      ['Retainage', 'Confirm retainage % matches the contract. Released retainage may be a separate line or period.'],
      ['Change orders', 'Approved owner COs should appear in SOV — sync from <strong>Change Orders</strong> if lines are missing.'],
      ['Attachments', 'Attach lien waivers, stored material photos, and signed G702/G703 PDFs as required.'],
      ['Submit for approval', 'Submit to PM → owner/architect → accounting. Use e-sign when configured.'],
      ['Settings', 'Pay app templates, default retainage, and PDF branding are under <strong>Program Settings → Pay Apps</strong>.'],
    ],
    'fa-file-invoice-dollar'
  ),

  submittals: singleGuide(
    'Submittals',
    'Shop drawings, product data, and samples for approval.',
    [
      ['Create submittal', 'Click <strong>New Submittal</strong>. Enter spec section, description, subcontractor, and required date.'],
      ['Attach documents', 'Upload PDFs or link files from <strong>Documents</strong>. Use current revision labels.'],
      ['Submit to design team', 'Change status from Draft to <strong>Open</strong>. Ball moves to architect/engineer.'],
      ['Review cycles', 'Record returned actions: Approved, Approved as Noted, Revise and Resubmit, or Rejected.'],
      ['Resubmit', 'Upload revised PDFs with incremented revision (Rev 1, Rev 2). Keep history for audit.'],
      ['Lead time', 'Enter fabrication lead time when approved — feeds schedule and procurement tracking.'],
      ['Close', 'Mark <strong>Closed</strong> when approved and distributed to the field.'],
      ['Settings', 'Submittal numbering defaults live under <strong>Program Settings → Numbering</strong>.'],
    ],
    'fa-file-circle-check'
  ),

  punch_list: singleGuide(
    'Punch List',
    'Track closeout deficiencies by location and responsible party.',
    [
      ['Create an item', 'Click <strong>New Item</strong>. Enter location, description, assignee company, and due date.'],
      ['Add photos', 'Attach photos from site walks so subs know exactly what to fix.'],
      ['Set priority', 'Use priority or type (cosmetic, functional, life-safety) to sort work before turnover.'],
      ['Assign Ball in Court', 'Assign to the sub or trade responsible. They fix and mark ready for inspection.'],
      ['Verify in field', 'Superintendent or architect verifies — set status to <strong>Complete</strong> or send back open.'],
      ['Bulk export', 'Print or PDF punch lists by floor or company for walk meetings.'],
      ['Link to inspections', ' Tie items to failed inspection lines when corrections require reinspection.'],
      ['Closeout', 'Filter open items to zero before substantial completion sign-off.'],
    ],
    'fa-list-check'
  ),

  safety: singleGuide(
    'Safety',
    'Incidents, observations, meetings, and OSHA logs.',
    [
      ['Pick record type', 'Use tabs or filters for incidents, near-misses, observations, toolbox talks, or OSHA 300 logs.'],
      ['Report an incident', 'Click <strong>New</strong>. Capture date, time, location, people involved, and narrative while facts are fresh.'],
      ['Classify severity', 'Record recordable vs first aid only — drives OSHA reporting and insurance notices.'],
      ['Corrective actions', 'Assign follow-up tasks with due dates and responsible party. Track until closed.'],
      ['Photos & witnesses', 'Attach site photos and witness statements as attachments or linked documents.'],
      ['Toolbox talks', 'Log topic, attendees, and sign-in sheet PDF for audit trail.'],
      ['Review trends', 'Filter by month or subcontractor to spot repeat hazards before they become recordables.'],
      ['Permissions', 'Safety data may be restricted — only authorized roles can edit closed incidents.'],
    ],
    'fa-helmet-safety'
  ),

  photos: singleGuide(
    'Photos',
    'Job site photos organized by date, album, or tag.',
    [
      ['Upload', 'Click <strong>Upload</strong> or drag files. Add date, location, and tags at upload for easier search later.'],
      ['Browse albums', 'Use albums or filters by date, trade, or keyword. Thumbnails open a lightbox with metadata.'],
      ['Link to records', 'Attach photos to daily logs, punch items, RFIs, or inspections from those modules\' attach actions.'],
      ['Markup', 'Use markup tools (when available) to circle issues before sending to subs.'],
      ['Share externally', 'Generate share links or include in weekly reports — respect owner confidentiality settings.'],
      ['Mobile capture', 'Field staff can upload from phones; sync appears in the project gallery within seconds.'],
      ['Storage hygiene', 'Delete blurry duplicates and keep naming consistent (e.g. area + date) for fast retrieval at closeout.'],
      ['Permissions', 'Some albums may be internal-only — check program security if owners should not see certain images.'],
    ],
    'fa-camera'
  ),

  inspections: singleGuide(
    'Inspections',
    'Checklists, inspections, and failed-item follow-up.',
    [
      ['Choose template', 'Pick an inspection type (framing, fire, final, etc.). Templates come from <strong>Program Settings → Inspections</strong>.'],
      ['Schedule or start', 'Create inspection with location, inspector, and date. Save as draft until the walk occurs.'],
      ['Complete checklist', 'Pass/fail each line. Add notes and photos on failed items — subs need clear corrective direction.'],
      ['Ball in Court', 'Failed items can assign responsibility to a subcontractor until reinspection passes.'],
      ['Reinspect', 'Create a follow-up inspection or close individual lines when corrections are verified.'],
      ['Permits & agencies', 'Record agency inspector name and permit number for jurisdictional audits.'],
      ['Export PDF', 'Print official checklist PDFs for owner binders and turnover packages.'],
      ['Close', 'Mark inspection <strong>Passed</strong> when all required lines pass or exceptions are documented.'],
    ],
    'fa-clipboard-check'
  ),

  schedule: singleGuide(
    'Schedule',
    'Activities, milestones, and lookahead.',
    [
      ['Open schedule view', 'See Gantt or list view of activities for the active project. Zoom to week or month as needed.'],
      ['Add activities', 'Create tasks with start/finish, predecessor links, and responsible company.'],
      ['Link predecessors', ' Tie finish-to-start links so date changes ripple correctly when delays occur.'],
      ['Baseline', 'Set a baseline snapshot after owner approval — compare current vs baseline for variance reports.'],
      ['Update progress', 'Field updates % complete weekly. Keep critical path activities honest for reliable forecast dates.'],
      ['Filters', 'Filter by company, phase, or critical path to focus meetings on what matters this week.'],
      ['Import/export', 'Import P6 or MSP XML when migrating; export for owner monthly updates.'],
      ['Integrate', 'Delays from RFIs or submittals should be reflected here — do not let schedule live only in email.'],
    ],
    'fa-calendar-days'
  ),

  budget: singleGuide(
    'Budget',
    'Original budget, modifications, and cost code totals.',
    [
      ['View cost codes', 'The grid shows budget line by cost code: original, modifications, committed, and actuals where synced.'],
      ['Original budget', 'Enter or import the owner-approved budget at project start. Lock when baseline is set.'],
      ['Budget modifications', 'Use budget transfers to move money between codes without a change order when policy allows.'],
      ['Commitments', 'Committed column reflects sub contracts and POs from <strong>Commitments</strong> — open that module to drill down.'],
      ['Change orders', 'Approved owner and sub COs update modified budget — sync from <strong>Change Orders</strong> if totals look stale.'],
      ['Forecast', 'Jump to <strong>Forecast</strong> for projected final cost based on commitments and trends.'],
      ['Export', 'Export Excel for owner reporting or Sage reconciliation.'],
      ['Settings', 'Cost code structure and Sage mapping live under <strong>Program Settings → Sage 300</strong> and project setup.'],
    ],
    'fa-coins'
  ),

  forecast: singleGuide(
    'Forecast',
    'Projected final cost and variance to budget.',
    [
      ['Open forecast', 'View rolls up budget, commitments, actuals, and manual projections by cost code.'],
      ['Review variances', 'Red or amber variances flag codes trending over budget — investigate commitments and open COs.'],
      ['Enter projections', 'PMs can override projected final cost per line when market or scope shifts before COs are issued.'],
      ['Include pending COs', 'Decide whether to include pending PCOs in projections — document assumptions in notes.'],
      ['Compare to budget', 'Use totals row to see forecast vs original and modified budget at a glance.'],
      ['Refresh data', 'Sync or refresh if commitments or pay apps just posted — stale actuals skew the forecast.'],
      ['Export', 'Export for monthly job reviews with ownership and bonding companies.'],
      ['Close the loop', 'Large variances should become change events or budget transfers — do not leave silent overrun.'],
    ],
    'fa-chart-line'
  ),

  commitments: singleGuide(
    'Commitments',
    'Subcontracts and purchase orders tied to the budget.',
    [
      ['Browse commitments', 'List shows contract number, vendor, original value, approved COs, and remaining.'],
      ['Create commitment', 'Click <strong>New</strong>. Pick vendor from <strong>Companies</strong>, cost code, and contract amount.'],
      ['SOV lines', 'Enter commitment SOV matching how you will pay — aligns with sub pay apps and CPCOs.'],
      ['Execute contract', 'Upload signed subcontract PDF to <strong>Documents</strong> and link here.'],
      ['Change via CPCO', 'Sub scope changes flow: Change Event → RFQ → CPCO → Sub CO — not by editing original value silently.'],
      ['Retainage & terms', 'Record retainage % and payment terms for pay application alignment.'],
      ['ERP sync', 'Approved commitments may export to Sage — check ERP queue after approval.'],
      ['One vendor per SC', 'Each subcontract commitment is one vendor — split trades into separate commitments.'],
    ],
    'fa-file-contract'
  ),

  companies: singleGuide(
    'Companies & Vendors',
    'Global directory of owners, subs, architects, and suppliers.',
    [
      ['Search companies', 'Use search and type filters (Owner, Sub, Vendor, Architect) to find a record quickly.'],
      ['Add company', 'Click <strong>New Company</strong>. Enter legal name, type, tax ID, and primary address.'],
      ['Contacts', 'Add contact people under each company — emails here feed RFQs, submittals, and user invites.'],
      ['Insurance & certs', 'Track GL, WC expiration, and COI attachments. Set alerts before policies lapse.'],
      ['Link to projects', 'Assign companies on <strong>Project Directory</strong> so they appear on job-specific dropdowns.'],
      ['Portal companies', 'Mark portal-enabled subs so RFQ and submittal portals authenticate correctly.'],
      ['Merge duplicates', 'Resolve duplicate vendor records before commitments — accounting needs one vendor ID.'],
      ['Settings', 'Default company types and required fields may be configured in program workflow settings.'],
    ],
    'fa-building'
  ),

  users: singleGuide(
    'User Management',
    'Accounts, roles, and module permissions.',
    [
      ['Browse users', 'See all staff and portal users with role, company, and last login.'],
      ['Invite user', 'Click <strong>New User</strong>. Enter name, email, role, and company. They receive a setup email.'],
      ['Set role', 'Roles (Admin, PM, Superintendent, Accounting, etc.) control default module access.'],
      ['Module permissions', 'Fine-tune access per module: view, edit, or admin. Hide financials for field-only accounts if needed.'],
      ['Portal vs staff', 'Portal users are tied to external companies — limit them to their project data only.'],
      ['Reset password', 'Admins can force password reset or unlock after lockout from security policy.'],
      ['2FA', 'Require two-factor authentication for sensitive roles under security settings.'],
      ['Deactivate', 'Disable users who leave the company instead of deleting — preserves audit history.'],
    ],
    'fa-users'
  ),

  documents: singleGuide(
    'Documents',
    'Project folders, files, and sharing.',
    [
      ['Folder tree', 'Browse folders in the left panel. Create folders to mirror spec divisions or company standards.'],
      ['Upload files', 'Drag files or click <strong>Upload</strong>. Version large sets instead of overwriting without trace.'],
      ['Preview & edit', 'Open PDFs in the viewer; edit Word or Excel in browser editors when supported.'],
      ['Permissions', 'Folder permissions restrict owner vs sub visibility — set before sharing sensitive bids.'],
      ['Link elsewhere', 'Attach document links from RFIs, submittals, meetings, and daily logs.'],
      ['Share externally', 'Create time-limited share links for owners or subs who do not have full accounts.'],
      ['Search', 'Search by filename or metadata. Use consistent naming (date + subject) for faster finds.'],
      ['Settings', 'Default folder templates and storage limits are under <strong>Program Settings → Documents</strong>.'],
    ],
    'fa-folder-open'
  ),

  drawings: singleGuide(
    'Drawings',
    'Plan sets, revisions, and sheet log.',
    [
      ['Upload set', 'Upload PDF plan sets by discipline (A, S, M, E). Group by revision date or bulletin.'],
      ['Sheet log', 'Each sheet gets number, title, revision, and issue date — matches field set labels.'],
      ['Current revision', 'Mark superseded sheets so field staff always open the latest revision.'],
      ['Link RFIs', 'Reference sheet numbers on RFIs and punch items so answers point to the right detail.'],
      ['Compare revisions', 'Use revision history to see what changed between bulletins.'],
      ['Download', 'Bulk download current set for subs or offline tablet use.'],
      ['Permissions', 'Restrict bid-set folders if drawings contain sensitive VE or pricing notes.'],
      ['Turnover', 'Export final as-built set to <strong>Documents</strong> closeout folder at project end.'],
    ],
    'fa-drafting-compass'
  ),

  deliveries: singleGuide(
    'Deliveries',
    'Track material deliveries and receiving.',
    [
      ['Log delivery', 'Click <strong>New Delivery</strong>. Enter supplier, PO or commitment #, date, and location on site.'],
      ['Line items', 'List materials, quantities, and ticket numbers from the delivery receipt.'],
      ['Attach ticket', 'Photo or PDF of signed delivery ticket proves receipt for pay apps and disputes.'],
      ['Inspect condition', 'Note damage or shortages — notify supplier and PM before acceptance.'],
      ['Link schedule', 'Long-lead items should align with schedule activities — flag late deliveries early.'],
      ['Stored materials', 'Mark stored on site for pay application stored-material billing when allowed.'],
      ['Search history', 'Filter by vendor or date to answer “when did steel arrive?” without digging through email.'],
      ['Close', 'Mark received complete when all items on the PO are delivered and verified.'],
    ],
    'fa-truck'
  ),

  meeting_minutes: singleGuide(
    'Meeting Minutes',
    'OAC, subcontractor, and internal meeting records.',
    [
      ['Create meeting', 'Click <strong>New Meeting</strong>. Set type (OAC, sub, safety), date, and attendees.'],
      ['Agenda', 'Add agenda items before the meeting so participants come prepared.'],
      ['Take notes', 'Record discussion, decisions, and action items with owner and due date.'],
      ['Action items', 'Each action needs assignee and due date — these feed follow-up at the next meeting.'],
      ['Attach docs', 'Link drawings, RFIs, or schedule snapshots referenced during discussion.'],
      ['Distribute', 'Email PDF minutes to attendees and file in <strong>Documents</strong>.'],
      ['Next meeting', 'Carry open actions forward automatically when copying the prior meeting.'],
      ['Search', 'Find past decisions by keyword — avoids re-debating settled issues.'],
    ],
    'fa-handshake'
  ),

  email: singleGuide(
    'Email',
    'Project email — internal messages and external mail.',
    [
      ['Inbox views', 'Switch folders: Inbox, Sent, Drafts, and project-linked threads. Unread count shows in the nav badge.'],
      ['Compose', 'Click <strong>Compose</strong>. Pick recipients from directory or type emails. Set subject and body.'],
      ['Link to project', 'Associate messages with the active project so the team sees job context in the thread list.'],
      ['Attachments', 'Attach files from disk or <strong>Documents</strong>. Watch size limits from program email settings.'],
      ['Internal vs external', 'Some users are internal-only — external mail may be disabled per security policy.'],
      ['Reply & forward', 'Use reply all carefully on owner threads; prefer linking RFIs for official direction.'],
      ['Search', 'Search subject and body to find prior approvals or sub confirmations.'],
      ['Settings', 'SMTP, signatures, and relay rules live under <strong>Program Settings → Email</strong>.'],
    ],
    'fa-envelope'
  ),

  program_settings: singleGuide(
    'Program Settings',
    'Company-wide defaults — only admins should change these.',
    [
      ['Company tab', 'Legal name, logo, address, and license — appear on pay apps, PDFs, and owner correspondence.'],
      ['Numbering', 'Prefixes and next numbers for RFIs, submittals, COs, and projects — set before go-live.'],
      ['Documents & pay apps', 'Folder templates, PDF branding, retainage defaults, and G702/G703 options.'],
      ['Workflow', 'Approval chains, e-sign requirements, and module toggles that affect every project.'],
      ['Email & security', 'Mail relay, session timeout, password policy, and 2FA requirements.'],
      ['Integrations & Sage', 'ERP connection, company mapping, and cost code sync to Sage 300.'],
      ['Backup', 'Schedule database backups and test restores periodically — not just enable and forget.'],
      ['Change carefully', 'Document why you changed a setting; wrong numbering or workflow breaks active projects.'],
    ],
    'fa-sliders'
  ),

  notifications: singleGuide(
    'Notifications',
    'Alerts for approvals, mentions, and workflow events.',
    [
      ['Open inbox', 'Bell icon or Notifications page lists unread items newest first.'],
      ['Filter', 'Filter by type — approvals, RFIs, submittals, safety, or system messages.'],
      ['Act from alert', 'Click a notification to jump to the record (RFI, CO, pay app) that needs action.'],
      ['Mark read', 'Clear items after handling so your inbox reflects real open work.'],
      ['Ball in Court', 'Many alerts mean you are Ball in Court — respond to move workflow forward.'],
      ['Email copies', 'Some events also email you — inbox here is the in-app audit of the same events.'],
      ['Preferences', 'Adjust which events notify you under <strong>Program Settings → Notifications</strong> or your profile.'],
      ['Mobile', 'Enable browser or mobile notifications if your admin supports push for urgent approvals.'],
    ],
    'fa-bell'
  ),

  app: singleGuide(
    'Case PM',
    'General tips for any page in the application.',
    [
      ['Active project', 'Most tools use the project selected in the header. Switch projects before creating records.'],
      ['Navigation', 'Use the left sidebar modules. Collapse the sidebar for more space — preference is saved.'],
      ['Search & filters', 'Lists usually support search, status filters, and column sort — click headers to sort.'],
      ['Create records', 'Primary actions are green buttons top-right: <strong>New</strong>, <strong>Create</strong>, or <strong>+</strong>.'],
      ['Save drafts', 'Many forms allow Draft until you Submit — save often before leaving the page.'],
      ['Help', 'Click the <strong>?</strong> help button in the header when available for page-specific steps.'],
      ['Profile & logout', 'Open your avatar menu for profile, password, and sign out.'],
      ['Get access', 'Missing modules? Ask an admin to adjust your role under <strong>Users</strong>.'],
    ],
    'fa-compass'
  ),
};

})(window);
