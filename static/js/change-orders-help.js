/**
 * Change Orders page — beginner-friendly step-by-step help guide.
 */
(function (global) {
  'use strict';

  const TAB_SECTION = {
    cos: 'owner-co',
    pcos: 'pco',
    subs: 'sub-co',
    events: 'change-events',
    rfqs: 'rfq',
    cors: 'cor',
    cpcos: 'cpco',
    erp: 'erp',
  };

  const SECTIONS = [
    {
      id: 'overview',
      title: 'Start here',
      icon: 'fa-compass',
      steps: [
        { title: 'What this page does', body: 'This page tracks every change to the project contract — extra work, credits, and subcontractor changes. Think of it as the money side of “something changed on the job.”' },
        { title: 'Two main paths', body: '<strong>Owner path</strong> (money from / with the owner): Change Event → PCO → COR (optional package) → Owner Change Order.<br><br><strong>Subcontractor path</strong> (money with subs): Change Event → RFQ → CPCO → Sub Change Order (one per sub).' },
        { title: 'Where the line items live', body: 'Detailed cost lines (Schedule of Values / SOV) are entered on <strong>PCOs</strong>, <strong>CPCOs</strong>, and final <strong>Change Orders</strong>. A <strong>COR</strong> does not have its own line items — it only groups PCOs for approval.' },
        { title: 'Pick a tab', body: 'Use the tabs across the top to work on each type. The colored <strong>Ball in Court</strong> column tells you who needs to act next.' },
      ],
    },
    {
      id: 'change-events',
      title: 'Change Events',
      icon: 'fa-bolt',
      steps: [
        { title: 'What it is', body: 'A Change Event is the starting notebook for a scope change. One event can affect several subcontractors.' },
        { title: 'Step 1 — Create the event', body: 'Open the <strong>Change Events</strong> tab → click inside the list area or use the event actions → give it a title, ROM (rough guess) amount, and description.' },
        { title: 'Step 2 — Add line items', body: 'Open the event to see the detail panel. Add one row per subcontractor / commitment: cost code, vendor, commitment #, and amount.' },
        { title: 'Step 3 — Bulk create downstream docs', body: 'Check the rows you need, then use <strong>Add To →</strong><br>• <strong>RFQs</strong> — ask subs for pricing (one RFQ per sub)<br>• <strong>CPCOs</strong> — draft commitment PCO per sub<br>• <strong>Draft CCOs</strong> — draft sub change order per sub<br><br>The system groups lines by vendor + commitment automatically.' },
        { title: 'Step 4 — Submit for pricing', body: 'Use <strong>Submit for Pricing</strong> when the event is ready. Approvers can review from the green <strong>Review</strong> button.' },
      ],
    },
    {
      id: 'rfq',
      title: 'RFQs',
      icon: 'fa-envelope',
      steps: [
        { title: 'What it is', body: 'RFQ = Request for Quote. You ask a subcontractor how much their part of the change will cost.' },
        { title: 'Step 1 — Create or receive', body: 'RFQs can be created from a Change Event (bulk) or with <strong>New RFQ</strong>. You must pick the subcontractor company.' },
        { title: 'Step 2 — Send to the sub', body: 'While status is <strong>Draft</strong>, click <strong>Send</strong>. Ball moves to the subcontractor.' },
        { title: 'Step 3 — Sub quotes', body: 'The sub enters a quote amount (portal or your team on their behalf). Status becomes <strong>Quoted</strong>.' },
        { title: 'Step 4 — Accept → CPCO', body: 'Click <strong>Accept→CPCO</strong> to turn the quote into a draft Commitment PCO (CPCO) with SOV lines filled in.' },
      ],
    },
    {
      id: 'cpco',
      title: 'CPCO Log',
      icon: 'fa-file-lines',
      steps: [
        { title: 'What it is', body: 'CPCO = Commitment Potential Change Order. It is the sub-side “draft change” before it becomes a real subcontract change order.' },
        { title: 'Where SOV lines go', body: 'Each CPCO has its own Schedule of Values lines (cost code, description, amount). These usually come from the Change Event or accepted RFQ.' },
        { title: 'Step 1 — Review the CPCO', body: 'Open the <strong>CPCO Log</strong> tab. Check vendor, amount, and status.' },
        { title: 'Step 2 — Promote to Sub CO', body: 'Click <strong>→ SCO</strong> to create a draft <strong>Subcontractor Change Order</strong> with the same SOV lines.' },
        { title: 'One sub per order', body: 'You cannot mix two subcontractors on one commitment change order. Each sub / commitment gets its own CPCO and its own Sub CO.' },
      ],
    },
    {
      id: 'sub-co',
      title: 'Sub Change Orders',
      icon: 'fa-hard-hat',
      steps: [
        { title: 'What it is', body: 'A formal change to a subcontract — adds or moves money on that sub’s contract.' },
        { title: 'Step 1 — Create or promote', body: 'Use <strong>New Sub CO</strong> (toolbar) for a manual entry, or promote from a CPCO / Change Event bulk action.' },
        { title: 'Step 2 — Fill in SOV lines', body: 'In the form, use the <strong>Schedule of Values (SOV)</strong> grid: cost code, cost type, description, and amount. At least one row is required before approval.' },
        { title: 'Step 3 — Pick the kind', body: '<strong>Contract Add</strong> — new money on the sub contract.<br><strong>Budget Transfer</strong> — move money between cost codes (must net to zero).<br><strong>Owner CO Backcharge</strong> — tie to an owner change order.' },
        { title: 'Step 4 — Submit & approve', body: 'Save as <strong>Draft</strong> → <strong>Submit</strong>. Flow: Project Manager → Contractor Accounting → <strong>Approved</strong>.' },
        { title: 'Step 5 — After approval', body: 'Approved sub COs update budget and pay application SOV for that subcontractor.' },
      ],
    },
    {
      id: 'pco',
      title: 'PCO Log',
      icon: 'fa-lightbulb',
      steps: [
        { title: 'What it is', body: 'PCO = Potential Change Order (owner side). It is the working draft of a change you may bill the owner.' },
        { title: 'Step 1 — Create a PCO', body: 'Click <strong>New PCO</strong> in the toolbar. Enter title, company (if needed), and description.' },
        { title: 'Step 2 — Enter SOV lines', body: 'Use the <strong>Schedule of Values (SOV)</strong> table at the bottom of the form. Each row is a budget line: cost code, cost type, description, amount.' },
        { title: 'Step 3 — Submit through review', body: 'Save → <strong>Submit</strong>. Approvals: Open → Pricing → Pending Review → <strong>Approved for CO</strong>.' },
        { title: 'Step 4 — Promote to Change Order', body: 'When status is <strong>Approved for CO</strong>, click <strong>Promote to CO</strong> (or use the drawer action). SOV lines copy to the owner Change Order.' },
        { title: 'Tip — COR packaging', body: 'Before promoting, you can attach PCOs to a COR (see COR Log) to send several PCOs through one owner approval package.' },
      ],
    },
    {
      id: 'cor',
      title: 'COR Log',
      icon: 'fa-inbox',
      steps: [
        { title: 'What it is', body: 'COR = Change Order Request. It is a <strong>folder</strong> that groups one or more owner PCOs for formal review. It does <strong>not</strong> have its own SOV lines.' },
        { title: 'Step 1 — Build PCOs first', body: 'Create owner PCOs and enter their SOV lines before making a COR.' },
        { title: 'Step 2 — New COR', body: 'COR Log tab → <strong>New COR</strong> → title & description → check the PCOs to package → Save.' },
        { title: 'Step 3 — Review the rollup', body: 'The COR amount is the sum of packaged PCOs. When you review, you will see a read-only SOV rollup pulled from those PCOs.' },
        { title: 'Step 4 — Submit & approve', body: 'Submit the COR. Approval path: Project Manager → Architect → Owner (e-sign if required) → Contractor Accounting → Approved.' },
        { title: 'Step 5 — After approval', body: 'Linked PCOs move forward for promotion. Promote each PCO to an Owner Change Order when ready.' },
      ],
    },
    {
      id: 'owner-co',
      title: 'Change Orders',
      icon: 'fa-file-signature',
      steps: [
        { title: 'What it is', body: 'The final, approved change to the owner / prime contract. This is what updates contract value, budget, and billing.' },
        { title: 'Step 1 — Create or promote', body: 'Use <strong>New CO</strong> for a manual owner CO, or <strong>Promote to CO</strong> from an approved PCO (recommended — SOV copies over).' },
        { title: 'Step 2 — SOV lines', body: 'Edit the <strong>Schedule of Values (SOV)</strong> grid. Each line needs cost code, cost type, and amount.' },
        { title: 'Step 3 — Submit', body: 'Save as Draft → Submit. Ball goes to Project Manager.' },
        { title: 'Step 4 — Approval chain', body: 'Project Manager → Architect → Owner (e-sign) → Contractor Accounting → <strong>Approved</strong>.' },
        { title: 'Step 5 — Sync', body: 'After approval, use <strong>Sync to SOV</strong> if shown — pushes lines to Budget and Pay Applications. Check the ERP Queue for accounting export.' },
        { title: 'Sub COs column', body: 'Owner COs may spawn or link related subcontractor change orders so sub costs stay tied to the owner change.' },
      ],
    },
    {
      id: 'erp',
      title: 'ERP Queue',
      icon: 'fa-cloud-arrow-up',
      steps: [
        { title: 'What it is', body: 'A waiting list of financial events (approved COs, CORs, etc.) ready for your accounting system (e.g. Sage 300).' },
        { title: 'Step 1 — Open the tab', body: 'Go to <strong>ERP Queue</strong> after a change is approved.' },
        { title: 'Step 2 — Review', body: 'Click <strong>Review ERP</strong> on pending items. Accounting confirms amounts and notes.' },
        { title: 'Step 3 — Posted', body: 'When status shows posted, the export to accounting is complete.' },
      ],
    },
    {
      id: 'glossary',
      title: 'Quick glossary',
      icon: 'fa-book',
      steps: [
        { title: 'ROM', body: 'Rough Order of Magnitude — a quick estimate, not final.' },
        { title: 'SOV', body: 'Schedule of Values — the line-by-line breakdown of cost codes and dollars on a PCO, CPCO, or Change Order.' },
        { title: 'Ball in Court', body: 'Who must act next (e.g. Project Manager, Owner, Subcontractor).' },
        { title: 'PCO vs CPCO', body: 'PCO = owner-side draft. CPCO = subcontractor-side draft.' },
        { title: 'COR', body: 'Packages PCOs for owner approval — no separate SOV.' },
        { title: 'Commitment', body: 'A subcontract or PO contract number (e.g. SC-001) tied to one vendor.' },
      ],
    },
  ];

  let activeSection = 'overview';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function sectionById(id) {
    return SECTIONS.find(s => s.id === id) || SECTIONS[0];
  }

  function renderNav(selected) {
    const nav = document.getElementById('coHelpNav');
    if (!nav) return;
    nav.innerHTML = SECTIONS.map(s => `
      <button type="button" data-help-section="${s.id}"
        class="co-help-nav-btn w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2 ${s.id === selected ? 'bg-violet-700 text-white' : 'text-zinc-300 hover:bg-zinc-800'}">
        <i class="fa-solid ${s.icon} w-4 text-center opacity-80"></i>
        <span>${esc(s.title)}</span>
      </button>`).join('');
    nav.querySelectorAll('[data-help-section]').forEach(btn => {
      btn.addEventListener('click', () => selectSection(btn.dataset.helpSection));
    });
  }

  function renderContent(section) {
    const body = document.getElementById('coHelpBody');
    if (!body) return;
    const steps = (section.steps || []).map((step, i) => `
      <div class="co-help-step mb-5">
        <div class="flex items-start gap-3">
          <span class="flex-shrink-0 w-7 h-7 rounded-full bg-violet-600 text-white text-sm font-bold flex items-center justify-center">${i + 1}</span>
          <div class="min-w-0">
            <h3 class="text-sm font-semibold text-white mb-1">${esc(step.title)}</h3>
            <div class="text-sm text-zinc-300 leading-relaxed co-help-prose">${step.body}</div>
          </div>
        </div>
      </div>`).join('');
    body.innerHTML = `
      <h2 class="text-lg font-semibold text-white mb-1 flex items-center gap-2">
        <i class="fa-solid ${section.icon} text-violet-400"></i>${esc(section.title)}
      </h2>
      <p class="text-xs text-zinc-500 mb-5">Follow the steps in order. You can switch topics anytime using the list on the left.</p>
      ${steps}`;
  }

  function selectSection(id) {
    activeSection = id;
    const section = sectionById(id);
    renderNav(id);
    renderContent(section);
    const body = document.getElementById('coHelpBody');
    if (body) body.scrollTop = 0;
  }

  function openHelp(sectionId) {
    const dlg = document.getElementById('coHelpModal');
    if (!dlg) return;
    const id = sectionId || activeSection || 'overview';
    selectSection(sectionById(id) ? id : 'overview');
    if (global.CasePMChangeOrders?.openDialog) global.CasePMChangeOrders.openDialog(dlg);
    else dlg.showModal();
  }

  function setContextFromTab(tabKey) {
    if (TAB_SECTION[tabKey]) activeSection = TAB_SECTION[tabKey];
  }

  global.CasePMChangeOrdersHelp = {
    open: openHelp,
    setContextFromTab,
    sections: SECTIONS,
  };

  if (global.CasePMChangeOrders) {
    global.CasePMChangeOrders.openHelp = openHelp;
  }
})(window);
