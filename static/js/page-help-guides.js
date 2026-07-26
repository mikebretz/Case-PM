(function(global){ 'use strict';
function steps(...items){
  return items.map((item) => {
    const [title, body, substeps] = item;
    return {
      title,
      body,
      substeps: substeps
        ? substeps.map((sub) => {
            const [st, sb] = sub;
            return { title: st, body: sb };
          })
        : [],
    };
  });
}
function singleGuide(title, subtitle, stepPairs, icon='fa-compass'){
  return { title, subtitle, sections: [{ id:'main', title:'How to use', icon, steps: steps(...stepPairs) }] };
}

const CHANGE_ORDERS_SECTIONS = [
  {
    id: 'overview',
    title: 'Start here',
    icon: 'fa-compass',
    steps: steps(
      ['What this page does', 'This page tracks every change to the project contract — extra work, credits, and subcontractor changes. Think of it as the money side of “something changed on the job.”', [
        ['Contract changes', 'Every dollar added or removed from the prime contract flows through this module — from the first scope question to the final approved change order.'],
        ['Owner vs sub money', 'Owner-side changes affect what you bill the owner; sub-side changes affect what you owe subcontractors. Both start from the same change event when scope shifts.'],
        ['Why it matters', 'Approved change orders update budget, commitments, and pay applications — skipping steps here causes billing and accounting mismatches.'],
      ]],
      ['Two main paths', '<strong>Owner path</strong> (money from / with the owner): Change Event → PCO → COR (optional package) → Owner Change Order.<br><br><strong>Subcontractor path</strong> (money with subs): Change Event → RFQ → CPCO → Sub Change Order (one per sub).', [
        ['Owner path', 'Start with a <strong>Change Event</strong>, build an owner <strong>PCO</strong> with SOV lines, optionally package PCOs in a <strong>COR</strong>, then promote to an <strong>Owner Change Order</strong>.'],
        ['Subcontractor path', 'From the same change event, send <strong>RFQs</strong> to subs, accept quotes into <strong>CPCOs</strong>, then promote each to a <strong>Sub Change Order</strong> — one per vendor.'],
        ['When to use which', 'Use the owner path when the change affects the prime contract; use the sub path when only a subcontractor\'s scope or price changes.'],
        ['Both paths together', 'A single change event can spawn both owner PCOs and sub RFQs when the scope change affects multiple parties.'],
      ]],
      ['Where the line items live', 'Detailed cost lines (Schedule of Values / SOV) are entered on <strong>PCOs</strong>, <strong>CPCOs</strong>, and final <strong>Change Orders</strong>. A <strong>COR</strong> does not have its own line items — it only groups PCOs for approval.', [
        ['PCO SOV lines', 'Open any <strong>PCO</strong> form and scroll to the <strong>Schedule of Values</strong> grid — enter cost code, description, and amount per budget line.'],
        ['CPCO SOV lines', 'Sub-side drafts live on <strong>CPCOs</strong> in the CPCO Log tab; lines usually copy from the change event or accepted RFQ.'],
        ['Final CO SOV', 'Promoted <strong>Owner</strong> and <strong>Sub Change Orders</strong> carry SOV lines that sync to budget and pay apps after approval.'],
        ['COR is not SOV', 'A <strong>COR</strong> only rolls up amounts from packaged PCOs — if dollars are missing, edit the underlying PCO, not the COR.'],
      ]],
      ['Pick a tab', 'Use the tabs across the top to work on each type. The colored <strong>Ball in Court</strong> column tells you who needs to act next.', [
        ['Tab navigation', 'Click tabs such as <strong>Change Events</strong>, <strong>PCO Log</strong>, <strong>COR Log</strong>, or <strong>Sub Change Orders</strong> to switch document types.'],
        ['Ball in Court', 'Look for the colored <strong>Ball in Court</strong> column — it shows who must act next (PM, owner, sub, accounting).'],
        ['Filter by status', 'Use list filters to show only <strong>Draft</strong>, <strong>Pending</strong>, or <strong>Approved</strong> items so you focus on open work.'],
        ['Open a record', 'Click any row to open the detail drawer or form — actions like <strong>Submit</strong> and <strong>Promote</strong> appear in the toolbar.'],
      ]],
      ['Set up first', 'Confirm cost codes and commitments exist under <strong>Budget</strong> and <strong>Commitments</strong> before creating change events so SOV lines have valid codes to attach to.', [
        ['Budget cost codes', 'Open <strong>Budget</strong> and confirm every cost code you expect to use on change orders exists with correct descriptions.'],
        ['Commitments', 'Under <strong>Commitments</strong>, verify each subcontractor has a contract number (e.g. SC-001) tied to the right vendor.'],
        ['Vendor records', 'Ensure subs appear in <strong>Companies</strong> and <strong>Project Directory</strong> so RFQs and CPCOs route to the correct company.'],
        ['Then create events', 'Once setup is complete, return to <strong>Change Orders</strong> and create your first <strong>Change Event</strong> with valid codes ready to attach.'],
      ]],
    ),
  },
  {
    id: 'change-events',
    title: 'Change Events',
    icon: 'fa-bolt',
    steps: steps(
      ['What it is', 'A Change Event is the starting notebook for a scope change. One event can affect several subcontractors.', [
        ['Single source of truth', 'One change event captures the scope shift, ROM estimate, and which subs are affected — before any formal PCO or RFQ exists.'],
        ['Multi-sub support', 'Add multiple line rows for different vendors on the same event instead of creating separate events for each sub.'],
        ['Downstream docs', 'From here you bulk-create RFQs, CPCOs, or draft sub COs — the event is the hub, not the final contract document.'],
      ]],
      ['Step 1 — Create the event', 'Open the <strong>Change Events</strong> tab → click inside the list area or use the event actions → give it a title, ROM (rough guess) amount, and description.', [
        ['Open the tab', 'Click <strong>Change Events</strong> at the top of the Change Orders page.'],
        ['Start new event', 'Click inside the list area or use the <strong>New</strong> / create action in the toolbar.'],
        ['Title', 'Enter a short title that describes the scope change (e.g. "Add electrical outlets — Level 2").'],
        ['ROM amount', 'Enter a rough order of magnitude dollar guess — this is not final pricing, just an early estimate.'],
        ['Description', 'Write a clear description of what changed and why so approvers and subs understand the scope.'],
      ]],
      ['Step 2 — Add line items', 'Open the event to see the detail panel. Add one row per subcontractor / commitment: cost code, vendor, commitment #, and amount.', [
        ['Open detail panel', 'Click the event row to open the detail panel on the right or in the form view.'],
        ['Add a row', 'Click <strong>Add Line</strong> or the equivalent row action for each affected sub or cost code.'],
        ['Cost code', 'Pick the budget cost code that will carry this change — must exist in <strong>Budget</strong>.'],
        ['Vendor & commitment', 'Select the subcontractor company and their commitment # (e.g. SC-003) from the dropdowns.'],
        ['Amount', 'Enter the estimated amount for that line — refine later when RFQs or PCOs are priced.'],
      ]],
      ['Step 3 — Bulk create downstream docs', 'Check the rows you need, then use <strong>Add To →</strong><br>• <strong>RFQs</strong> — ask subs for pricing (one RFQ per sub)<br>• <strong>CPCOs</strong> — draft commitment PCO per sub<br>• <strong>Draft CCOs</strong> — draft sub change order per sub<br><br>The system groups lines by vendor + commitment automatically.', [
        ['Select rows', 'Check the checkbox on each line item you want to promote — you can select some or all rows.'],
        ['Open Add To menu', 'Click <strong>Add To →</strong> in the toolbar or row actions menu.'],
        ['RFQs', 'Choose <strong>RFQs</strong> to send pricing requests — one RFQ is created per vendor automatically.'],
        ['CPCOs or Draft CCOs', 'Choose <strong>CPCOs</strong> for draft commitment PCOs, or <strong>Draft CCOs</strong> for draft sub change orders.'],
        ['Auto-grouping', 'The system groups lines by vendor + commitment — you do not need to split them manually.'],
      ]],
      ['Step 4 — Submit for pricing', 'Use <strong>Submit for Pricing</strong> when the event is ready. Approvers can review from the green <strong>Review</strong> button.', [
        ['When ready', 'Confirm title, description, and line items are complete before submitting.'],
        ['Submit for Pricing', 'Click <strong>Submit for Pricing</strong> — status changes and Ball in Court moves to the approver.'],
        ['Approver review', 'Approvers see a green <strong>Review</strong> button on pending events — they approve or send back for edits.'],
        ['After approval', 'Once approved for pricing, proceed to create RFQs, CPCOs, or PCOs from the line items.'],
      ]],
      ['Step 5 — Track status', 'Watch the event status and Ball in Court column. When pricing is complete, promote lines to RFQs, CPCOs, or PCOs as needed.', [
        ['Status column', 'Watch the event status (Draft, Pending, Approved, etc.) to know where it sits in workflow.'],
        ['Ball in Court', 'Check who holds the ball — PM, estimator, or approver — and follow up if it stalls.'],
        ['Promote lines', 'When pricing is complete, use <strong>Add To →</strong> again or open linked RFQs/CPCOs/PCOs from the event detail.'],
        ['Close the loop', 'Link all downstream docs back to the event so the full change history stays traceable.'],
      ]],
    ),
  },
  {
    id: 'rfq',
    title: 'RFQs',
    icon: 'fa-envelope',
    steps: steps(
      ['What it is', 'RFQ = Request for Quote. You ask a subcontractor how much their part of the change will cost.', [
        ['Purpose', 'An RFQ formalizes the pricing request to a sub before you commit to a CPCO or sub change order.'],
        ['One sub per RFQ', 'Each RFQ goes to one subcontractor company — bulk creation from a change event handles multiple subs automatically.'],
        ['Not a change order', 'Accepting a quote creates a CPCO draft; the RFQ itself does not change the contract until promoted further.'],
      ]],
      ['Step 1 — Create or receive', 'RFQs can be created from a Change Event (bulk) or with <strong>New RFQ</strong>. You must pick the subcontractor company.', [
        ['From change event', 'On a change event, check rows and use <strong>Add To → RFQs</strong> to create one RFQ per vendor.'],
        ['Manual create', 'On the <strong>RFQs</strong> tab, click <strong>New RFQ</strong> in the toolbar.'],
        ['Pick subcontractor', 'Select the subcontractor company from the dropdown — required before save.'],
        ['Link scope', 'Enter or confirm the scope description and line items so the sub knows what to price.'],
      ]],
      ['Step 2 — Send to the sub', 'While status is <strong>Draft</strong>, click <strong>Send</strong>. Ball moves to the subcontractor.', [
        ['Verify draft', 'Open the RFQ and confirm scope, due date, and contact info are correct while status is <strong>Draft</strong>.'],
        ['Click Send', 'Click <strong>Send</strong> in the toolbar — the sub receives notification via portal or email.'],
        ['Ball moves', 'Ball in Court shifts to the subcontractor — they must enter a quote or respond.'],
        ['Track due date', 'Set a due date before sending so the sub knows your pricing deadline.'],
      ]],
      ['Step 3 — Sub quotes', 'The sub enters a quote amount (portal or your team on their behalf). Status becomes <strong>Quoted</strong>.', [
        ['Portal entry', 'The sub logs into the portal, opens the RFQ, and enters their quote amount and any notes.'],
        ['On their behalf', 'Your team can enter the quote if the sub emailed pricing — open the RFQ and fill in the quote fields.'],
        ['Status Quoted', 'Once a dollar amount is saved, status changes to <strong>Quoted</strong> and Ball returns to your team for review.'],
        ['Review amount', 'Compare the quote to your ROM estimate and change event line before accepting.'],
      ]],
      ['Step 4 — Accept → CPCO', 'Click <strong>Accept→CPCO</strong> to turn the quote into a draft Commitment PCO (CPCO) with SOV lines filled in.', [
        ['Review quote', 'Open the quoted RFQ and verify amount, scope, and vendor are correct.'],
        ['Accept→CPCO', 'Click <strong>Accept→CPCO</strong> — a draft CPCO is created with SOV lines pre-filled from the quote.'],
        ['Find the CPCO', 'Go to the <strong>CPCO Log</strong> tab to review and edit the new CPCO before promoting to a sub CO.'],
        ['Do not skip', 'Accepting is required before the sub-side change can flow to a formal subcontract change order.'],
      ]],
      ['Step 5 — Decline or revise', 'If the quote is wrong, use revise / decline actions and send a new RFQ rather than editing an accepted CPCO without review.', [
        ['Decline', 'Use <strong>Decline</strong> if the quote is unacceptable — document the reason in notes.'],
        ['Revise & resend', 'Use revise actions to send the RFQ back to the sub with updated scope or questions.'],
        ['New RFQ if needed', 'For major scope changes, create a fresh RFQ instead of editing an already-accepted CPCO.'],
        ['Audit trail', 'Keep declined RFQs in the log — do not delete — so pricing history remains visible.'],
      ]],
    ),
  },
  {
    id: 'cpco',
    title: 'CPCO Log',
    icon: 'fa-file-lines',
    steps: steps(
      ['What it is', 'CPCO = Commitment Potential Change Order. It is the sub-side “draft change” before it becomes a real subcontract change order.', [
        ['Sub-side draft', 'A CPCO is the working document for a subcontractor scope change — similar to a PCO on the owner side.'],
        ['Before Sub CO', 'You review and edit SOV lines on the CPCO before promoting to a formal <strong>Subcontractor Change Order</strong>.'],
        ['One vendor each', 'Each CPCO ties to one vendor and one commitment — never mix two subs on one CPCO.'],
      ]],
      ['Where SOV lines go', 'Each CPCO has its own Schedule of Values lines (cost code, description, amount). These usually come from the Change Event or accepted RFQ.', [
        ['SOV grid location', 'Open the CPCO form and scroll to the <strong>Schedule of Values</strong> table at the bottom.'],
        ['From change event', 'Lines bulk-created from a change event copy cost code, vendor, and amount automatically.'],
        ['From accepted RFQ', 'When you <strong>Accept→CPCO</strong> from an RFQ, quote amounts populate the SOV rows.'],
        ['Edit before promote', 'Adjust descriptions and amounts on the CPCO — this is your last easy edit before the sub CO approval chain.'],
      ]],
      ['Step 1 — Review the CPCO', 'Open the <strong>CPCO Log</strong> tab. Check vendor, amount, and status.', [
        ['Open CPCO Log', 'Click the <strong>CPCO Log</strong> tab at the top of the Change Orders page.'],
        ['Find your CPCO', 'Use search or sort by date to locate the CPCO linked to your change event or RFQ.'],
        ['Verify vendor', 'Confirm the vendor company and commitment # match the correct subcontract.'],
        ['Check amount & status', 'Review total amount and status (Draft, Pending, etc.) before editing or promoting.'],
      ]],
      ['Step 2 — Edit SOV if needed', 'Open the CPCO form and adjust SOV rows before promoting. Line items live here — not on the COR.', [
        ['Open the form', 'Click the CPCO row to open the full form view with the SOV grid.'],
        ['Add or edit rows', 'Click <strong>Add Row</strong> or edit existing lines: cost code, cost type, description, amount.'],
        ['Not on COR', 'Remember — COR is owner-side packaging only; sub dollars always live on CPCO or Sub CO SOV.'],
        ['Save changes', 'Click <strong>Save</strong> after edits — unsaved SOV changes will not carry to the sub CO.'],
      ]],
      ['Step 3 — Promote to Sub CO', 'Click <strong>→ SCO</strong> to create a draft <strong>Subcontractor Change Order</strong> with the same SOV lines.', [
        ['Confirm SOV complete', 'Ensure at least one SOV row exists with valid cost code and amount before promoting.'],
        ['Click → SCO', 'Click <strong>→ SCO</strong> in the toolbar — a draft Sub Change Order is created with SOV copied over.'],
        ['Find Sub CO', 'Go to the <strong>Sub Change Orders</strong> tab to open and complete the new draft.'],
        ['Complete approval', 'Submit the Sub CO through PM → Accounting → Approved to update budget and pay apps.'],
      ]],
      ['One sub per order', 'You cannot mix two subcontractors on one commitment change order. Each sub / commitment gets its own CPCO and its own Sub CO.', [
        ['One vendor rule', 'Each CPCO and Sub CO links to exactly one vendor company and one commitment number.'],
        ['Multiple subs', 'If three subs are affected, you need three separate CPCOs and three Sub COs.'],
        ['Bulk from event', 'Change event bulk actions create separate docs per vendor automatically — do not merge manually.'],
        ['Accounting match', 'This rule keeps Sage and pay application SOV aligned with each subcontract contract.'],
      ]],
    ),
  },
  {
    id: 'sub-co',
    title: 'Sub Change Orders',
    icon: 'fa-hard-hat',
    steps: steps(
      ['What it is', 'A formal change to a subcontract — adds or moves money on that sub’s contract.', [
        ['Contract amendment', 'A Sub Change Order formally amends the subcontract value — it is not just an internal estimate.'],
        ['After approval', 'Approved sub COs update committed budget and appear on that sub\'s pay application SOV.'],
        ['Types vary', 'Contract Add, Budget Transfer, and Owner CO Backcharge each behave differently — pick the right kind in Step 3.'],
      ]],
      ['Step 1 — Create or promote', 'Use <strong>New Sub CO</strong> (toolbar) for a manual entry, or promote from a CPCO / Change Event bulk action.', [
        ['Manual entry', 'On <strong>Sub Change Orders</strong> tab, click <strong>New Sub CO</strong> for a change not tied to a CPCO.'],
        ['From CPCO', 'On an approved or draft CPCO, click <strong>→ SCO</strong> to promote with SOV lines copied.'],
        ['From change event', 'Bulk <strong>Add To → Draft CCOs</strong> on a change event creates one draft per vendor.'],
        ['Pick vendor', 'Select the subcontractor and commitment # — required before you can save.'],
      ]],
      ['Step 2 — Fill in SOV lines', 'In the form, use the <strong>Schedule of Values (SOV)</strong> grid: cost code, cost type, description, and amount. At least one row is required before approval.', [
        ['Open SOV grid', 'Scroll to the <strong>Schedule of Values (SOV)</strong> section at the bottom of the Sub CO form.'],
        ['Add rows', 'Click add row and enter cost code, cost type, description, and dollar amount for each line.'],
        ['Minimum one row', 'At least one SOV line is required — the form will block submit without it.'],
        ['Match commitment', 'Use the same cost codes and structure as the original commitment SOV when possible.'],
      ]],
      ['Step 3 — Pick the kind', '<strong>Contract Add</strong> — new money on the sub contract.<br><strong>Budget Transfer</strong> — move money between cost codes (must net to zero).<br><strong>Owner CO Backcharge</strong> — tie to an owner change order.', [
        ['Contract Add', 'Choose <strong>Contract Add</strong> when adding new scope and dollars to the sub contract.'],
        ['Budget Transfer', 'Choose <strong>Budget Transfer</strong> to move money between cost codes — total must net to zero.'],
        ['Owner CO Backcharge', 'Choose <strong>Owner CO Backcharge</strong> when the sub change ties to an approved owner change order.'],
        ['Cannot change later', 'Pick the correct type before submit — changing kind after approval may require a new document.'],
      ]],
      ['Step 4 — Submit & approve', 'Save as <strong>Draft</strong> → <strong>Submit</strong>. Flow: Project Manager → Contractor Accounting → <strong>Approved</strong>.', [
        ['Save Draft', 'Click <strong>Save</strong> or <strong>Save Draft</strong> to preserve work before submitting.'],
        ['Submit', 'Click <strong>Submit</strong> when SOV and details are complete — Ball moves to Project Manager.'],
        ['PM review', 'Project Manager reviews and forwards to Contractor Accounting.'],
        ['Approved', 'Accounting approves — status becomes <strong>Approved</strong> and budget updates.'],
      ]],
      ['Step 5 — After approval', 'Approved sub COs update budget and pay application SOV for that subcontractor.', [
        ['Budget update', 'Open <strong>Budget</strong> and confirm the modified/committed columns reflect the new sub CO amount.'],
        ['Pay app SOV', 'On the sub\'s next pay application, the new SOV lines should appear for billing.'],
        ['Sync if stale', 'If totals look wrong, use sync actions from Change Orders or refresh budget data.'],
        ['Document retention', 'Keep the approved Sub CO PDF in <strong>Documents</strong> for audit and closeout.'],
      ]],
      ['Step 6 — ERP export', 'Check the <strong>ERP Queue</strong> tab if your company syncs approved sub COs to accounting.', [
        ['Open ERP Queue', 'After approval, go to the <strong>ERP Queue</strong> tab on the Change Orders page.'],
        ['Find pending item', 'Look for the approved Sub CO in the pending export list.'],
        ['Review ERP', 'Click <strong>Review ERP</strong> — accounting confirms amounts before posting to Sage.'],
        ['Posted status', 'When status shows posted, the export to your accounting system is complete.'],
      ]],
    ),
  },
  {
    id: 'pco',
    title: 'PCO Log',
    icon: 'fa-lightbulb',
    steps: steps(
      ['What it is', 'PCO = Potential Change Order (owner side). It is the working draft of a change you may bill the owner.', [
        ['Owner-side draft', 'A PCO is where you build and price the change before it becomes a formal owner change order.'],
        ['SOV lives here', 'All dollar detail is entered on the PCO SOV grid — not on the COR.'],
        ['Approval gate', 'PCOs must reach <strong>Approved for CO</strong> before you can promote to an Owner Change Order.'],
      ]],
      ['Step 1 — Create a PCO', 'Click <strong>New PCO</strong> in the toolbar. Enter title, company (if needed), and description.', [
        ['Open PCO Log', 'Click the <strong>PCO Log</strong> tab on the Change Orders page.'],
        ['New PCO', 'Click <strong>New PCO</strong> in the toolbar.'],
        ['Title & description', 'Enter a clear title and description of the scope change for owner review.'],
        ['Company', 'Select the owner or relevant company if the form requires it for your workflow.'],
      ]],
      ['Step 2 — Enter SOV lines', 'Use the <strong>Schedule of Values (SOV)</strong> table at the bottom of the form. Each row is a budget line: cost code, cost type, description, amount.', [
        ['Scroll to SOV', 'Open the PCO form and scroll to the <strong>Schedule of Values (SOV)</strong> table.'],
        ['Add rows', 'Click add row for each budget line affected by the change.'],
        ['Required fields', 'Each row needs cost code, cost type, description, and dollar amount.'],
        ['Extended total', 'The PCO total sums from SOV rows — verify the rollup matches your estimate.'],
      ]],
      ['Step 3 — Submit through review', 'Save → <strong>Submit</strong>. Approvals: Open → Pricing → Pending Review → <strong>Approved for CO</strong>.', [
        ['Save first', 'Click <strong>Save</strong> to preserve SOV lines before submitting.'],
        ['Submit', 'Click <strong>Submit</strong> — status moves to Open and Ball goes to the next approver.'],
        ['Pricing & review', 'Workflow progresses through Pricing and Pending Review stages per your program settings.'],
        ['Approved for CO', 'Wait until status is <strong>Approved for CO</strong> before promoting to a change order.'],
      ]],
      ['Step 4 — Promote to Change Order', 'When status is <strong>Approved for CO</strong>, click <strong>Promote to CO</strong> (or use the drawer action). SOV lines copy to the owner Change Order.', [
        ['Check status', 'Confirm the PCO shows <strong>Approved for CO</strong> — earlier statuses block promotion.'],
        ['Promote to CO', 'Click <strong>Promote to CO</strong> in the toolbar or drawer action menu.'],
        ['SOV copies', 'SOV lines copy automatically to the new Owner Change Order — review them there.'],
        ['Complete owner CO', 'Open the new CO, finish any required fields, and submit through the owner approval chain.'],
      ]],
      ['Tip — COR packaging', 'Before promoting, you can attach PCOs to a COR (see COR Log) to send several PCOs through one owner approval package.', [
        ['Build PCOs first', 'Create and enter SOV on each PCO before packaging — COR has no SOV of its own.'],
        ['New COR', 'On <strong>COR Log</strong> tab, click <strong>New COR</strong> and check the PCOs to include.'],
        ['Single approval', 'Owner approves the COR package once — linked PCOs move forward together.'],
        ['Then promote', 'After COR approval, promote each PCO to an Owner Change Order when ready.'],
      ]],
      ['Remember', 'COR packages PCOs — it does not replace SOV entry on each PCO.', [
        ['PCO SOV required', 'Every dollar must be entered on the individual PCO SOV grid.'],
        ['COR is a folder', 'Think of COR as a folder that groups PCOs — it rolls up totals but holds no line items.'],
        ['Missing dollars', 'If the COR total looks wrong, open the underlying PCOs and fix SOV there.'],
      ]],
    ),
  },
  {
    id: 'cor',
    title: 'COR Log',
    icon: 'fa-inbox',
    steps: steps(
      ['What it is', 'COR = Change Order Request. It is a <strong>folder</strong> that groups one or more owner PCOs for formal review. It does <strong>not</strong> have its own SOV lines.', [
        ['Packaging tool', 'A COR bundles multiple PCOs so the owner reviews one package instead of many separate documents.'],
        ['No SOV entry', 'You cannot enter dollar lines on a COR — all amounts come from the PCOs you attach.'],
        ['Formal review', 'CORs go through PM → Architect → Owner → Accounting before linked PCOs can promote.'],
      ]],
      ['Step 1 — Build PCOs first', 'Create owner PCOs and enter their SOV lines before making a COR.', [
        ['Create PCOs', 'On <strong>PCO Log</strong>, create each PCO that belongs in this change package.'],
        ['Enter SOV', 'Open each PCO and complete the SOV grid with cost codes, descriptions, and amounts.'],
        ['Advance status', 'Submit PCOs through review until they are ready to package — at minimum they need complete SOV.'],
        ['Verify totals', 'Note each PCO total — the COR amount will be the sum of packaged PCOs.'],
      ]],
      ['Step 2 — New COR', 'COR Log tab → <strong>New COR</strong> → title & description → check the PCOs to package → Save.', [
        ['Open COR Log', 'Click the <strong>COR Log</strong> tab on the Change Orders page.'],
        ['New COR', 'Click <strong>New COR</strong> in the toolbar.'],
        ['Title & description', 'Enter a package title and description that covers all included PCOs.'],
        ['Select PCOs', 'Check the PCOs to include in this package, then click <strong>Save</strong>.'],
      ]],
      ['Step 3 — Review the rollup', 'The COR amount is the sum of packaged PCOs. When you review, you will see a read-only SOV rollup pulled from those PCOs.', [
        ['Check total', 'Open the COR and confirm the header amount equals the sum of linked PCO totals.'],
        ['SOV rollup', 'The review view shows a read-only SOV rollup aggregated from packaged PCOs — you cannot edit it here.'],
        ['Fix on PCOs', 'If a line is wrong, close the COR review, edit the underlying PCO SOV, and reopen the COR.'],
        ['Attachments', 'Add any supporting documents (sketches, RFIs) before submitting for approval.'],
      ]],
      ['Step 4 — Submit & approve', 'Submit the COR. Approval path: Project Manager → Architect → Owner (e-sign if required) → Contractor Accounting → Approved.', [
        ['Submit COR', 'Click <strong>Submit</strong> when the package is complete — Ball moves to Project Manager.'],
        ['PM & architect', 'Each approver reviews the rollup and supporting docs in sequence.'],
        ['Owner e-sign', 'If configured, the owner receives an e-sign request before accounting can approve.'],
        ['Approved', 'Final approval sets status to <strong>Approved</strong> and linked PCOs advance.'],
      ]],
      ['Step 5 — After approval', 'Linked PCOs move forward for promotion. Promote each PCO to an Owner Change Order when ready.', [
        ['PCO status', 'Open each linked PCO and confirm it shows <strong>Approved for CO</strong> or equivalent.'],
        ['Promote each PCO', 'On each PCO, click <strong>Promote to CO</strong> to create the Owner Change Order.'],
        ['Complete owner COs', 'Submit each Owner CO through its own approval chain if not auto-created as approved.'],
        ['Sync budget', 'After owner CO approval, use <strong>Sync to SOV</strong> to push lines to budget and pay apps.'],
      ]],
      ['Do not enter SOV here', 'If dollar lines are missing, edit the underlying PCOs — not the COR.', [
        ['No SOV grid', 'The COR form has no SOV entry grid — this is by design.'],
        ['Edit PCOs', 'Open the linked PCO(s) and add or fix rows in the <strong>Schedule of Values</strong> table.'],
        ['Refresh rollup', 'After PCO edits, reopen the COR to see the updated rollup total.'],
        ['Common mistake', 'Trying to enter dollars on the COR will not work — always go to the PCO.'],
      ]],
    ),
  },
  {
    id: 'owner-co',
    title: 'Change Orders',
    icon: 'fa-file-signature',
    steps: steps(
      ['What it is', 'The final, approved change to the owner / prime contract. This is what updates contract value, budget, and billing.', [
        ['Prime contract change', 'An Owner Change Order is the executed amendment to the owner contract — not a draft or estimate.'],
        ['Budget & billing', 'After approval, SOV lines sync to <strong>Budget</strong> and <strong>Pay Applications</strong>.'],
        ['Best from PCO', 'Promoting from an approved PCO copies SOV automatically — manual entry is possible but error-prone.'],
      ]],
      ['Step 1 — Create or promote', 'Use <strong>New CO</strong> for a manual owner CO, or <strong>Promote to CO</strong> from an approved PCO (recommended — SOV copies over).', [
        ['Promote from PCO', 'On a PCO with status <strong>Approved for CO</strong>, click <strong>Promote to CO</strong> — recommended path.'],
        ['Manual New CO', 'On <strong>Change Orders</strong> tab, click <strong>New CO</strong> only when no PCO exists for this change.'],
        ['SOV copies', 'Promotion copies SOV lines from the PCO — verify them on the new CO form.'],
        ['Title & description', 'Confirm title and description match owner expectations before saving.'],
      ]],
      ['Step 2 — SOV lines', 'Edit the <strong>Schedule of Values (SOV)</strong> grid. Each line needs cost code, cost type, and amount.', [
        ['Open SOV grid', 'Scroll to <strong>Schedule of Values (SOV)</strong> on the Owner CO form.'],
        ['Review each row', 'Confirm cost code, cost type, description, and amount on every line.'],
        ['Add missing lines', 'If promotion missed a line, add rows manually — but prefer fixing the PCO first.'],
        ['Total check', 'Verify the CO total matches the approved PCO or owner agreement.'],
      ]],
      ['Step 3 — Submit', 'Save as Draft → Submit. Ball goes to Project Manager.', [
        ['Save Draft', 'Click <strong>Save</strong> to store work — you can return to edit SOV while in Draft.'],
        ['Submit', 'Click <strong>Submit</strong> when complete — Ball in Court moves to Project Manager.'],
        ['Attachments', 'Attach signed owner correspondence or supporting docs if required by your workflow.'],
        ['Track Ball', 'Watch the Ball in Court column to see who must act next.'],
      ]],
      ['Step 4 — Approval chain', 'Project Manager → Architect → Owner (e-sign) → Contractor Accounting → <strong>Approved</strong>.', [
        ['PM review', 'Project Manager reviews SOV and scope, then forwards in the chain.'],
        ['Architect', 'Architect confirms design impact if required by contract.'],
        ['Owner e-sign', 'Owner signs electronically when e-sign is configured in program workflow.'],
        ['Accounting approval', 'Contractor Accounting gives final <strong>Approved</strong> status.'],
      ]],
      ['Step 5 — Sync', 'After approval, use <strong>Sync to SOV</strong> if shown — pushes lines to Budget and Pay Applications. Check the ERP Queue for accounting export.', [
        ['Sync to SOV', 'Click <strong>Sync to SOV</strong> if the button appears — updates budget and pay app lines.'],
        ['Verify budget', 'Open <strong>Budget</strong> and confirm modified budget reflects the approved CO.'],
        ['ERP Queue', 'Go to <strong>ERP Queue</strong> tab and process the export to Sage or your accounting system.'],
        ['Pay apps', 'On the next pay app, confirm new SOV lines appear for billing the owner.'],
      ]],
      ['Sub COs column', 'Owner COs may spawn or link related subcontractor change orders so sub costs stay tied to the owner change.', [
        ['Linked sub COs', 'Check the Sub COs column or related tab on the Owner CO for linked subcontractor changes.'],
        ['Create sub COs', 'If sub scope changed too, create sub COs from the change event or CPCO path separately.'],
        ['Tie backcharges', 'Use <strong>Owner CO Backcharge</strong> type on sub COs to link sub costs to this owner CO.'],
        ['Keep in sync', 'Owner and sub CO amounts should reconcile — investigate variances before closeout.'],
      ]],
    ),
  },
  {
    id: 'erp',
    title: 'ERP Queue',
    icon: 'fa-cloud-arrow-up',
    steps: steps(
      ['What it is', 'A waiting list of financial events (approved COs, CORs, etc.) ready for your accounting system (e.g. Sage 300).', [
        ['Export staging', 'Approved financial documents queue here before posting to Sage 300 or your ERP.'],
        ['Accounting handoff', 'Contractor accounting reviews each item before export — not automatic on approval.'],
        ['Audit trail', 'Posted items show completion status so you know what synced and what is still pending.'],
      ]],
      ['Step 1 — Open the tab', 'Go to <strong>ERP Queue</strong> after a change is approved.', [
        ['Navigate', 'On the Change Orders page, click the <strong>ERP Queue</strong> tab at the top.'],
        ['After approval', 'Open this tab after an Owner CO, Sub CO, or COR reaches <strong>Approved</strong> status.'],
        ['Pending list', 'The list shows items waiting for accounting review and export.'],
        ['Filter if needed', 'Use status filters to show only pending or posted items.'],
      ]],
      ['Step 2 — Review', 'Click <strong>Review ERP</strong> on pending items. Accounting confirms amounts and notes.', [
        ['Select item', 'Click a pending row or use <strong>Review ERP</strong> on the item that needs export.'],
        ['Verify amounts', 'Accounting confirms dollar totals, cost codes, and vendor mapping match Sage.'],
        ['Add notes', 'Enter any export notes or corrections before posting.'],
        ['Approve export', 'Confirm the item is ready to post to the accounting system.'],
      ]],
      ['Step 3 — Posted', 'When status shows posted, the export to accounting is complete.', [
        ['Posted status', 'Look for <strong>Posted</strong> status in the ERP Queue list.'],
        ['Verify in Sage', 'Accounting should confirm the transaction appears in Sage 300 with correct job and phase codes.'],
        ['Resolve errors', 'If export fails, check <strong>Program Settings → Sage 300</strong> mapping and retry.'],
        ['Document', 'Keep a record of posted date for month-end reconciliation.'],
      ]],
      ['Settings', 'Configure Sage 300 defaults under <strong>Program Settings → Sage 300</strong> before your first export.', [
        ['Open settings', 'Go to <strong>Program Settings</strong> from the main navigation (admin only).'],
        ['Sage 300 tab', 'Click the <strong>Sage 300</strong> or <strong>Integrations</strong> section.'],
        ['Company mapping', 'Map Case PM companies and cost codes to Sage company and phase codes.'],
        ['Test first', 'Run a test export on a small approved CO before bulk posting at go-live.'],
      ]],
    ),
  },
  {
    id: 'glossary',
    title: 'Quick glossary',
    icon: 'fa-book',
    steps: steps(
      ['ROM', 'Rough Order of Magnitude — a quick estimate, not final.', [
        ['Early guess', 'Enter a ROM on change events when you know scope changed but do not have final pricing yet.'],
        ['Not binding', 'ROM is informational — it does not update budget or contracts until a PCO or CO is approved.'],
        ['Refine later', 'Replace ROM with actual quotes from RFQs and SOV lines on PCOs as pricing firms up.'],
      ]],
      ['SOV', 'Schedule of Values — the line-by-line breakdown of cost codes and dollars on a PCO, CPCO, or Change Order.', [
        ['Line items', 'Each SOV row has cost code, cost type, description, and dollar amount.'],
        ['Where to enter', 'Enter SOV on PCOs, CPCOs, and final Change Orders — never on CORs.'],
        ['Syncs downstream', 'Approved SOV lines flow to budget, commitments, and pay applications.'],
      ]],
      ['Ball in Court', 'Who must act next (e.g. Project Manager, Owner, Subcontractor).', [
        ['Workflow indicator', 'The colored Ball in Court column shows whose turn it is to review, approve, or respond.'],
        ['Follow up', 'If ball stays with someone too long, use notifications or email to prompt action.'],
        ['Moves on action', 'Submitting, approving, or responding moves the ball to the next role in the chain.'],
      ]],
      ['PCO vs CPCO', 'PCO = owner-side draft. CPCO = subcontractor-side draft.', [
        ['PCO', 'Potential Change Order — owner/prime contract side; promotes to Owner Change Order.'],
        ['CPCO', 'Commitment Potential Change Order — sub contract side; promotes to Sub Change Order.'],
        ['Same concept', 'Both are working drafts with SOV lines before the formal change order is executed.'],
      ]],
      ['COR', 'Packages PCOs for owner approval — no separate SOV.', [
        ['Folder only', 'COR groups one or more PCOs for a single owner review package.'],
        ['Rollup total', 'COR amount is the sum of packaged PCO totals — edit dollars on the PCOs.'],
        ['After approval', 'Linked PCOs promote to Owner Change Orders individually.'],
      ]],
      ['Commitment', 'A subcontract or PO contract number (e.g. SC-001) tied to one vendor.', [
        ['Contract reference', 'Every sub change links to a commitment # so dollars stay on the right subcontract.'],
        ['One vendor', 'Each commitment is one vendor — split trades into separate commitments.'],
        ['From Commitments module', 'Create commitments under <strong>Commitments</strong> before bulk change event actions.'],
      ]],
    ),
  },
];

global.CasePMPageHelpGuides = {
  dashboard: singleGuide(
    'Dashboard',
    'Your project command center — tiles, charts, and quick links.',
    [
      ['Pick a project', 'Use the project selector in the header. Most dashboard tiles show data for the <strong>active project</strong> only.', [
        ['Project selector', 'Click the project name in the top header bar to open the project dropdown.'],
        ['Search projects', 'Type in the search box to filter by project name or number.'],
        ['Set active', 'Select the job you are working on — tiles refresh to show that project\'s data.'],
        ['Wrong data?', 'If counts look off, confirm the correct project is selected before drilling in.'],
      ]],
      ['Choose a view', 'Toggle between <strong>Overview</strong> and <strong>Customize</strong> (if shown) to switch preset layouts or edit your grid.', [
        ['Overview mode', 'Click <strong>Overview</strong> for the default tile layout with key metrics.'],
        ['Customize mode', 'Click <strong>Customize</strong> to rearrange, resize, or add/remove tiles.'],
        ['Save layout', 'Changes in customize mode save automatically per user for this project.'],
        ['Switch back', 'Return to Overview anytime — your custom layout is preserved.'],
      ]],
      ['Read the tiles', 'Each tile summarizes one area — open items, budget snapshot, schedule, safety, etc. Click a tile title or link to jump to that module.', [
        ['Tile labels', 'Read each tile title to know what it measures (e.g. Open RFIs, Budget Variance).'],
        ['Click through', 'Click the tile title or <strong>View all</strong> link to open the full module page.'],
        ['Compare counts', 'Use tile numbers to spot areas needing attention before the morning meeting.'],
        ['Hover details', 'Some tiles show tooltips or sparklines on hover for quick context.'],
      ]],
      ['Customize layout', 'In customize mode, drag tiles to rearrange. Resize from corners. Changes save per user for this project.', [
        ['Enter customize', 'Switch to <strong>Customize</strong> mode from the view toggle.'],
        ['Drag tiles', 'Click and drag a tile to a new position in the grid.'],
        ['Resize', 'Grab the corner handle and drag to make a tile larger or smaller.'],
        ['Per-user save', 'Your layout is saved for you only — other users keep their own arrangement.'],
      ]],
      ['Watch charts', 'Bar and line charts roll up counts or dollars. Hover for details; click legend items to hide series.', [
        ['Hover data points', 'Move the mouse over bars or line points to see exact values and dates.'],
        ['Legend toggle', 'Click a legend item to hide or show that data series on the chart.'],
        ['Time range', 'Some charts respect the project date filter — check the chart subtitle for the period.'],
        ['Export', 'Use chart export or screenshot for owner reports when an export button is available.'],
      ]],
      ['Act on alerts', 'Red or amber counts usually mean overdue RFIs, open punch items, or pending approvals — open the linked page and clear the queue.', [
        ['Red = urgent', 'Red counts typically mean overdue or past-due items — address these first.'],
        ['Amber = soon', 'Amber counts warn of items approaching due date or pending too long.'],
        ['Click to act', 'Click the tile or count to open the filtered list of items needing action.'],
        ['Clear daily', 'Make it a habit to drive alert counts to zero or assign owners before end of day.'],
      ]],
      ['Reset if needed', 'Use <strong>Reset layout</strong> (when available) to restore the default tile set without losing project data.', [
        ['When to reset', 'Use reset if tiles are missing, overlapping, or you want the factory default layout.'],
        ['Reset layout', 'Click <strong>Reset layout</strong> in customize mode or dashboard settings.'],
        ['Data safe', 'Reset only changes tile arrangement — no project records are deleted.'],
        ['Re-customize', 'After reset, you can customize again from a clean starting point.'],
      ]],
      ['Daily habit', 'Start here each morning: confirm active project, scan open counts, then drill into the highest-priority module.', [
        ['Morning routine', 'Open the dashboard first thing — confirm project, scan tiles, note red/amber counts.'],
        ['Prioritize', 'Pick the highest-impact module (RFIs, approvals, safety) based on tile alerts.'],
        ['Drill in', 'Click through to that module and work the queue before moving to lower-priority tasks.'],
        ['End of day', 'Glance back at the dashboard to confirm critical counts dropped or have owners assigned.'],
      ]],
    ],
    'fa-gauge-high'
  ),

  projects: singleGuide(
    'Projects',
    'Create projects, set status, and open project tools.',
    [
      ['Browse the list', 'The projects table shows name, number, status, and key dates. Use search and filters to find a job.', [
        ['Search bar', 'Type project name or number in the search box to filter the table instantly.'],
        ['Status filter', 'Use status filters (Active, Complete, Archived) to hide finished jobs.'],
        ['Sort columns', 'Click column headers to sort by name, number, or start date.'],
        ['Column scan', 'Scan status and key dates to see which jobs are live vs closeout.'],
      ]],
      ['Open a project', 'Click a row to open the project detail page. Set it as active from the header project picker when you want dashboard data for that job.', [
        ['Click row', 'Click any project row to open the project detail page.'],
        ['Detail page', 'Review address, dates, team, and settings on the detail view.'],
        ['Set active', 'Use the header project picker to make this job the <strong>active project</strong> for dashboard and modules.'],
        ['Return anytime', 'Switch active project from the header without losing your place in the list.'],
      ]],
      ['Create a project', 'Click <strong>New Project</strong>. Enter name, project number, address, dates, and client company. Save as <strong>Active</strong> when ready to use modules.', [
        ['New Project', 'Click <strong>New Project</strong> in the toolbar.'],
        ['Name & number', 'Enter project name and number — match accounting (Sage) if you sync financials.'],
        ['Address & dates', 'Fill in site address, start date, and substantial completion date.'],
        ['Client company', 'Select the owner or client company from <strong>Companies</strong>.'],
        ['Save Active', 'Set status to <strong>Active</strong> when ready to use RFIs, budget, and other modules.'],
      ]],
      ['Set project team', 'On the project detail page, assign roles (PM, superintendent, etc.) so workflow and notifications route correctly.', [
        ['Team section', 'On the project detail page, find the team or roles section.'],
        ['Assign PM', 'Set the Project Manager — they receive many approval and Ball in Court notifications.'],
        ['Superintendent', 'Assign superintendent for field modules like daily log and punch list.'],
        ['Other roles', 'Add estimator, accounting contact, and safety lead as your workflow requires.'],
      ]],
      ['Configure numbering', 'Project numbers should match accounting (Sage) if you sync financials. Adjust global prefixes under <strong>Program Settings → Numbering</strong>.', [
        ['Match Sage job #', 'Use the same project number in Case PM as in Sage 300 for clean ERP sync.'],
        ['Numbering settings', 'Admins: open <strong>Program Settings → Numbering</strong> for global prefixes.'],
        ['RFI/CO prefixes', 'Set next numbers for RFIs, submittals, and COs before the team creates records.'],
        ['Cannot reuse', 'Each project number should be unique — duplicates break accounting mapping.'],
      ]],
      ['Archive completed jobs', 'Change status to <strong>Complete</strong> or <strong>Archived</strong> to hide clutter while keeping history and documents.', [
        ['When complete', 'Set status to <strong>Complete</strong> at substantial completion or final payment.'],
        ['Archive later', 'Use <strong>Archived</strong> for old jobs you want hidden from default lists.'],
        ['History kept', 'Archived projects retain all RFIs, documents, and financial history.'],
        ['Reactivate', 'Change status back to Active if you need to reopen a job for warranty work.'],
      ]],
      ['Link to directory', 'Use <strong>Project Directory</strong> for contacts on this job — companies and people tied to the active project.', [
        ['Open directory', 'From the project or sidebar, open <strong>Project Directory</strong>.'],
        ['Add contacts', 'Add owners, architects, subs, and inspectors tied to this job.'],
        ['Used everywhere', 'Directory contacts appear in RFI assignees, submittal routing, and email pickers.'],
        ['Keep current', 'Update contacts when subs change PMs — stale entries cause missed notifications.'],
      ]],
      ['Permissions', 'If you cannot see a project, ask an admin to grant module access under <strong>Users</strong> or project-level permissions.', [
        ['Missing project', 'If a job does not appear in your list, you may lack project-level access.'],
        ['Ask admin', 'Contact an admin to grant access under <strong>Users</strong> → your account → permissions.'],
        ['Module access', 'You may see the project but not financial modules — admin can limit by module.'],
        ['Portal users', 'External subs only see projects where their company is on the directory.'],
      ]],
    ],
    'fa-folder-tree'
  ),

  project_directory: singleGuide(
    'Project Directory',
    'Everyone and every company attached to the active project — built automatically from team assignments, SOV subcontractors, RFIs, schedule, permits, and more.',
    [
      ['Select the project', 'The directory lists people and companies for the <strong>active project</strong> in the header. Switch projects to see a different roster.', [
        ['Check header', 'Confirm the correct project is selected in the header project picker.'],
        ['Switch project', 'Change the active project to view a different job\'s directory roster.'],
        ['Empty list', 'If the list is empty, add team contacts on the project, commitments, pay app SOV subs, or module assignees.'],
        ['Auto-built', 'Contacts are aggregated from modules — you do not add rows directly on this page.'],
      ]],
      ['Filter the roster', 'Use <strong>On this project</strong>, <strong>All project</strong>, or <strong>All personnel</strong> to change who appears in the people list.', [
        ['On this project', 'Shows team members and owner/client contacts assigned directly to the project.'],
        ['All project', 'Shows everyone linked through any module (RFIs, punch, schedule resources, SOV, permits, etc.).'],
        ['All personnel', 'Adds main-company staff who are not yet linked to this project.'],
        ['Search', 'Search by name, company, email, or attachment source.'],
      ]],
      ['People vs companies', 'Switch between <strong>People</strong>, <strong>Companies</strong>, or <strong>All</strong> to see individuals or grouped firms.', [
        ['People view', 'One row per person with position, company, email, phone, and attachment badges.'],
        ['Companies view', 'Groups people by company and shows how each firm is attached to the job.'],
        ['Attached via', 'Badges show whether someone came from team, SOV, RFI, schedule, permit, or another module.'],
        ['Refresh', 'Click <strong>Refresh</strong> after updating commitments, pay apps, or module assignees.'],
      ]],
      ['Where contacts come from', 'Directory rows are pulled from project team, commitments, pay app SOV, submittals, RFIs, punch list, schedule resources, meetings, permits, safety, and deliveries.', [
        ['Project team', 'Assign users and team contacts on the project record.'],
        ['Subcontractors', 'Register subs on Pay Applications / commitments so SOV vendors appear here.'],
        ['Module assignees', 'RFI assignees, punch assignees, and schedule resource names are included automatically.'],
        ['Keep modules current', 'Update phone and email in the source module or Companies when subs change PMs.'],
      ]],
      ['Portal users', 'If a contact needs portal access (sub RFQ, submittals), ensure their user account exists under <strong>Users</strong> and is tied to the right company.', [
        ['User account', 'Create the contact as a user under <strong>Users</strong> if they need portal login.'],
        ['Tie to company', 'Link the user account to the same company as their directory entry.'],
        ['Portal role', 'Assign a portal role with access to RFQs, submittals, or other sub-facing modules.'],
        ['Send invite', 'They receive a setup email to activate portal access.'],
      ]],
      ['Keep it current', 'Update phone and email when subs change PMs — outdated contacts in commitments, SOV, or RFIs cause missed approvals.', [
        ['Quarterly review', 'Review directory contacts each quarter or when subs mobilize.'],
        ['Source modules', 'Edit the commitment, company record, or RFI assignee where the contact originated.'],
        ['Missed RFIs', 'Wrong email is the #1 cause of overdue RFI responses — verify before sending.'],
        ['Remove old', 'Deactivate or remove contacts who left the company to avoid misdirected notifications.'],
      ]],
    ],
    'fa-address-book'
  ),

  daily_log: singleGuide(
    'Daily Log',
    'Record weather, crew, work performed, and photos by day.',
    [
      ['Pick the date', 'Use the date picker or calendar strip. One log per project per day is typical.', [
        ['Date picker', 'Click the date field or calendar icon to choose the log date.'],
        ['Calendar strip', 'Use the horizontal date strip to jump to recent days quickly.'],
        ['One per day', 'Most projects keep one official log per day — open existing or create new.'],
        ['Past dates', 'Supervisors may restrict editing past dates per program policy.'],
      ]],
      ['Create today\'s log', 'Click <strong>New Log</strong> or open an empty day. Status starts as draft until submitted.', [
        ['New Log', 'Click <strong>New Log</strong> if no log exists for the selected date.'],
        ['Empty day', 'Click an empty day on the calendar to start a new entry.'],
        ['Draft status', 'New logs start as <strong>Draft</strong> — you can save and return before submitting.'],
        ['Save often', 'Save periodically so weather and crew entries are not lost.'],
      ]],
      ['Weather & conditions', 'Enter temperature, conditions, and any delays (rain, inspection hold). Owners often require this for claims support.', [
        ['Temperature', 'Record high/low or current temperature as your template requires.'],
        ['Conditions', 'Note sun, rain, snow, wind — be factual for potential delay claims.'],
        ['Delays', 'Document rain days, inspection holds, or owner-directed stops with brief notes.'],
        ['Inspection impact', 'Note if weather prevented work or inspections from occurring.'],
      ]],
      ['Work performed', 'Describe trades on site, locations, and percent complete. Keep entries factual and brief.', [
        ['Trades on site', 'List which subcontractors were working and in which areas.'],
        ['Locations', 'Reference building areas, floors, or grid lines for clarity.'],
        ['Percent complete', 'Note progress on major activities when your template includes it.'],
        ['Factual tone', 'Stick to what happened — avoid opinions that could be disputed later.'],
      ]],
      ['Manpower & equipment', 'Add headcount by company and major equipment if your template includes those sections.', [
        ['Headcount', 'Enter worker count per company or trade as shown on the form.'],
        ['Equipment', 'Log cranes, lifts, or major rented equipment on site that day.'],
        ['Compare to plan', 'Unusually low headcount may signal schedule risk — note why if known.'],
        ['Safety tie-in', 'High headcount days may correlate with more safety observations — stay vigilant.'],
      ]],
      ['Attach photos', 'Link photos from the <strong>Photos</strong> module or upload directly so the log matches visual evidence.', [
        ['Attach action', 'Use the attach or photo button on the daily log form.'],
        ['From Photos', 'Link existing photos from the <strong>Photos</strong> module by date or album.'],
        ['Upload direct', 'Upload new site photos directly to the log entry.'],
        ['Match narrative', 'Photos should support the work-performed description for audit defense.'],
      ]],
      ['Submit', 'When complete, <strong>Submit</strong> the log. Supervisors may review or lock past dates per program policy.', [
        ['Review entries', 'Read through weather, work, and crew sections before submitting.'],
        ['Submit', 'Click <strong>Submit</strong> to finalize the day\'s log.'],
        ['Supervisor review', 'Some workflows require superintendent approval after submit.'],
        ['Locked dates', 'Submitted logs on past dates may be locked from further edits.'],
      ]],
      ['Review history', 'Scroll prior days or export PDFs for owner reports and weekly summaries.', [
        ['Prior days', 'Use the calendar or list to open previous daily logs.'],
        ['Export PDF', 'Export individual days or date ranges for owner weekly reports.'],
        ['Weekly report', 'Weekly report module may pull from submitted daily logs automatically.'],
        ['Claims support', 'Historical logs support delay and disruption claims — keep them accurate.'],
      ]],
    ],
    'fa-clipboard-list'
  ),

  weekly_report: singleGuide(
    'Weekly Report',
    'Summarize job progress for owners and stakeholders.',
    [
      ['Select week ending', 'Choose the report week (usually Friday or Sunday). Data may pull from daily logs and schedule.', [
        ['Week picker', 'Use the week-ending date picker to select the reporting period.'],
        ['Friday vs Sunday', 'Match your owner\'s expected week-ending day (often Friday for construction).'],
        ['Auto-pull', 'Some sections may pre-fill from daily logs and schedule if data exists.'],
        ['Confirm range', 'Verify start and end dates before filling the report.'],
      ]],
      ['Create or open report', 'Click <strong>New Report</strong> for a blank week or open an existing draft.', [
        ['New Report', 'Click <strong>New Report</strong> for a week with no report yet.'],
        ['Open draft', 'Click an existing row to continue editing a draft report.'],
        ['Copy prior week', 'Use copy-from-prior when available to save time on recurring sections.'],
        ['One per week', 'Typically one report per project per week-ending date.'],
      ]],
      ['Fill executive summary', 'Write 2–4 sentences on overall status, milestones hit, and major risks.', [
        ['Overall status', 'State whether the job is on track, ahead, or behind in plain language.'],
        ['Milestones', 'Call out pours, inspections passed, or turnover dates hit this week.'],
        ['Risks', 'Note top 1–2 risks (weather, long-lead, design gaps) and mitigation.'],
        ['Owner audience', 'Write for executives who may only read this section.'],
      ]],
      ['Progress by area', 'Update percent complete, lookahead, and constraints for each building area or phase.', [
        ['Area breakdown', 'Update each building area or phase row with current % complete.'],
        ['Lookahead', 'Note what is planned for the next 2–3 weeks per area.'],
        ['Constraints', 'List RFIs, submittals, or inspections blocking progress.'],
        ['Match schedule', 'Align numbers with the schedule module when possible.'],
      ]],
      ['Safety & quality', 'Note incidents, inspections passed/failed, and open punch or submittal items affecting turnover.', [
        ['Safety', 'Summarize incidents, near-misses, and toolbox talks held this week.'],
        ['Inspections', 'List inspections passed or failed and reinspection status.'],
        ['Quality', 'Note open punch items or submittal delays affecting turnover areas.'],
        ['Trends', 'Call out repeat issues by trade if they affect schedule or safety.'],
      ]],
      ['Photos & links', 'Attach key progress photos and reference open RFIs or change orders if they drive schedule.', [
        ['Progress photos', 'Attach 2–4 photos showing major work areas or milestones.'],
        ['Link RFIs', 'Reference open RFIs by number if they are driving delays.'],
        ['Change orders', 'Note pending owner COs affecting scope or schedule.'],
        ['Documents', 'Link schedule snapshots or meeting minutes if referenced in the narrative.'],
      ]],
      ['Internal review', 'PM reviews, then mark <strong>Ready for Owner</strong> or distribute PDF per your workflow.', [
        ['PM review', 'Project manager reads full report for accuracy before external distribution.'],
        ['Ready for Owner', 'Mark <strong>Ready for Owner</strong> when approved for external release.'],
        ['Internal only', 'Some sections may stay internal — confirm what goes to the owner PDF.'],
        ['Corrections', 'Send back to draft if super or estimator finds errors.'],
      ]],
      ['Distribute', 'Email PDF or share via <strong>Documents</strong>. Copy prior week to save time on recurring sections.', [
        ['Export PDF', 'Generate PDF from the report actions menu.'],
        ['Email', 'Email PDF to owner distribution list per contract requirements.'],
        ['File in Documents', 'Save a copy in <strong>Documents</strong> under weekly reports folder.'],
        ['Copy prior', 'Next week, copy this report as a starting template for recurring sections.'],
      ]],
    ],
    'fa-calendar-week'
  ),

  rfis: singleGuide(
    'RFIs',
    'Request for Information — formal questions that need a written answer (Procore-style Ball in Court).',
    [
      ['Required to open', 'Subject, question, assignees, due date, and <strong>RFI Manager</strong> are required before an RFI can be opened.', [
        ['Subject', 'Write a short, specific title that names the drawing detail or conflict (e.g. "Clash at Grid C-4 — duct vs beam").'],
        ['Question', 'State the conflict clearly — what is unclear, what decision is needed, and what you propose if applicable.'],
        ['Assignees', 'Pick everyone who must respond (architect, engineer, owner rep) from the <strong>Project Directory</strong>.'],
        ['Due date', 'Set a realistic due date based on schedule impact — field work may be blocked until answered.'],
        ['RFI Manager', 'Assign the <strong>RFI Manager</strong> (usually PM or project engineer) who reviews responses and closes the RFI.'],
      ]],
      ['Create Draft or Open', 'Use <strong>Save Draft</strong> to keep the ball with the RFI Manager, or <strong>Save &amp; Open</strong> to notify assignees immediately.', [
        ['Save Draft', 'Click <strong>Save Draft</strong> if the manager needs to review before assignees are notified.'],
        ['Save & Open', 'Click <strong>Save &amp; Open</strong> when ready to send — assignees receive notification immediately.'],
        ['Ball stays with manager', 'In draft, Ball in Court remains with the RFI Manager until opened.'],
        ['Cannot open without fields', 'The form blocks open if subject, question, assignees, due date, or manager are missing.'],
      ]],
      ['Ball in Court', 'Tracks who owns the RFI: Manager reviews drafts; assignees respond when open; ball returns to the manager after each reply.', [
        ['Manager on draft', 'While draft, only the RFI Manager can edit and open the RFI.'],
        ['Assignees when open', 'After open, Ball moves to assignees until they submit a response.'],
        ['Returns to manager', 'Each response returns Ball to the manager for review and official answer selection.'],
        ['Track in list', 'Watch the colored Ball in Court column to see who must act next.'],
      ]],
      ['Assign from directory', 'Pick the RFI Manager, assignees, and distribution list from the <strong>Project Directory</strong> so notifications reach the right people.', [
        ['RFI Manager', 'Select from directory — typically the PM or designated RFI coordinator.'],
        ['Assignees', 'Add architect, structural engineer, MEP designer, or owner rep as required.'],
        ['Distribution', 'Add distribution contacts who get copies but are not required to respond.'],
        ['Verify email', 'Confirm directory emails are current before opening — wrong addresses delay answers.'],
      ]],
      ['Respond', 'Assignees submit responses in Procore, email, or Case PM. Each reply is logged; the manager reviews all answers.', [
        ['Assignee login', 'Assignees open the RFI from notification or the RFI list.'],
        ['Submit response', 'Enter the written answer, attach sketches if needed, and submit.'],
        ['Email replies', 'Email responses can be logged manually if your workflow allows.'],
        ['Multiple replies', 'Each response is timestamped — the manager reviews all before picking the official answer.'],
      ]],
      ['Official answer', 'The RFI Manager marks one response as the <strong>Official Response</strong>, then closes the RFI when the field can proceed.', [
        ['Review responses', 'Manager reads all assignee replies for consistency and completeness.'],
        ['Mark official', 'Select one response as the <strong>Official Response</strong> — this is the contract record.'],
        ['Close RFI', 'Close the RFI when the field has direction to proceed.'],
        ['Distribute', 'Closed RFIs with official answers are visible to the project team (unless private).'],
      ]],
      ['Private RFIs', 'Private RFIs are visible only to the creator, manager, assignees, and distribution — not the full project team.', [
        ['When to use', 'Use private for sensitive cost, legal, or owner-only discussions.'],
        ['Who sees it', 'Only creator, RFI Manager, assignees, and distribution list can view.'],
        ['Toggle on create', 'Set the private flag when creating the RFI — confirm policy before using.'],
        ['Not for routine', 'Routine field conflicts should be open RFIs so supers and subs see the answer.'],
      ]],
      ['Cost impact', 'If the answer affects scope, cost, or schedule, create a <strong>Change Event</strong> — the RFI alone does not change the budget.', [
        ['RFI is not a CO', 'An RFI documents a question and answer — it does not change contract value.'],
        ['Scope change', 'If the answer adds or changes scope, create a <strong>Change Event</strong> in Change Orders.'],
        ['Link RFI', 'Reference the RFI number on the change event description for traceability.'],
        ['Schedule too', 'If the answer affects dates, update the schedule and note the RFI as the driver.'],
      ]],
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
      ['Open an estimate', 'Select a project estimate from the list or click <strong>New Estimate</strong> to start a fresh bid.', [
        ['Estimate list', 'Browse existing estimates in the table — sort by project or date.'],
        ['Open row', 'Click a row to open the estimate detail and line items.'],
        ['New Estimate', 'Click <strong>New Estimate</strong> to start a blank bid for a new opportunity.'],
        ['Link project', 'Associate the estimate with a project when the job is awarded.'],
      ]],
      ['Set structure', 'Organize by division / cost code. Match your budget structure so awarded numbers import cleanly.', [
        ['Divisions', 'Create sections by CSI division or your company\'s standard breakdown.'],
        ['Cost codes', 'Use the same cost code numbering as <strong>Budget</strong> for clean import.'],
        ['Sections', 'Group related line items under logical sections (sitework, structure, MEP).'],
        ['Templates', 'Start from a company template if available to save setup time.'],
      ]],
      ['Enter quantities', 'Add line items with quantity, unit, unit cost, and extended total. Use formulas where supported.', [
        ['Add line', 'Click add row and enter description, quantity, unit, and unit cost.'],
        ['Extended total', 'The system calculates quantity × unit cost — verify the extended amount.'],
        ['Formulas', 'Use formula fields where supported for area, volume, or count takeoffs.'],
        ['Units', 'Pick consistent units (SF, LF, EA) so subs can bid apples-to-apples.'],
      ]],
      ['Takeoff tools', 'Open the takeoff popout (when available) to measure from PDF plans and push quantities to line items.', [
        ['Open takeoff', 'Click the takeoff icon or popout on a line item linked to a drawing.'],
        ['Measure on PDF', 'Draw lengths, areas, or counts on the uploaded plan PDF.'],
        ['Push quantity', 'Save the measurement — quantity flows to the linked estimate line.'],
        ['Revision check', 'Confirm you are measuring from the current drawing revision.'],
      ]],
      ['Adjust markup', 'Apply overhead, profit, and bond percentages at the estimate or section level per company standards.', [
        ['Markup fields', 'Find overhead, profit, and bond % fields at section or estimate level.'],
        ['Company standards', 'Use your estimator\'s standard percentages — do not change per bid without approval.'],
        ['Roll up', 'Section markups roll to the estimate grand total — verify before sending.'],
        ['Alternates', 'Markup may apply differently on base bid vs alternates — check both.'],
      ]],
      ['Compare alternates', 'Use alternate sections for VE options without duplicating the whole estimate.', [
        ['Add alternate', 'Create an alternate section for optional scope (e.g. upgraded finishes).'],
        ['Separate totals', 'Each alternate shows its own add/deduct total for owner comparison.'],
        ['Base bid', 'Keep the base bid clean — alternates should not double-count base scope.'],
        ['Present clearly', 'Label alternates so owners understand what is included vs optional.'],
      ]],
      ['Send to portal', 'Share read-only or editable views with subs via the <strong>Estimate Portal</strong> link for bid input.', [
        ['Portal link', 'Generate or copy the <strong>Estimate Portal</strong> link from estimate actions.'],
        ['Invite subs', 'Send the link to subcontractors for their trade sections.'],
        ['Read-only vs edit', 'Choose whether subs can only view or enter their bid amounts.'],
        ['Due date', 'Set a bid due date and track which subs have responded.'],
      ]],
      ['Award to budget', 'When the job is won, export or sync awarded amounts to <strong>Budget</strong> (per your admin workflow).', [
        ['Award estimate', 'Mark the estimate as awarded when you win the job.'],
        ['Export or sync', 'Use export or admin sync to push awarded line totals to <strong>Budget</strong>.'],
        ['Verify codes', 'Confirm cost codes in budget match the estimate structure.'],
        ['Lock estimate', 'Lock or archive the awarded estimate to prevent accidental edits.'],
      ]],
    ],
    'fa-calculator'
  ),

  pay_applications: singleGuide(
    'Pay Applications',
    'Bill the owner by period — SOV, retainage, and approvals.',
    [
      ['Open pay app list', 'Each row is a billing period (usually monthly). Status shows draft, submitted, or approved.', [
        ['Pay app table', 'Browse rows — each represents one billing period for the active project.'],
        ['Status column', 'Check Draft, Submitted, or Approved to know where each period stands.'],
        ['Period dates', 'Note the period start/end dates — they must match your contract billing cycle.'],
        ['Open row', 'Click a row to open the pay application form and SOV grid.'],
      ]],
      ['Create new period', 'Click <strong>New Pay App</strong>. Pick period dates; SOV lines often copy from budget or prior app.', [
        ['New Pay App', 'Click <strong>New Pay App</strong> in the toolbar.'],
        ['Period dates', 'Select billing period start and end — typically calendar month.'],
        ['SOV copy', 'SOV lines often copy from budget or the previous pay app automatically.'],
        ['Verify lines', 'Confirm all contract SOV lines appear before entering work completed.'],
      ]],
      ['Enter work completed', 'For each SOV line, enter work completed this period and stored materials if allowed.', [
        ['Work this period', 'Enter dollars or % complete for work performed during the billing period.'],
        ['Stored materials', 'Enter stored materials on site if your contract allows billing before installation.'],
        ['Prior periods', 'Prior billed amounts should show — do not double-bill the same work.'],
        ['Line totals', 'Watch the period total row — it should match your field progress estimate.'],
      ]],
      ['Retainage', 'Confirm retainage % matches the contract. Released retainage may be a separate line or period.', [
        ['Retainage %', 'Verify the retainage percentage on each line matches the prime contract.'],
        ['Held amount', 'System calculates retainage held — confirm against owner expectations.'],
        ['Release period', 'Retainage release may be a separate pay app or line — follow contract terms.'],
        ['Sub pay apps', 'Align owner retainage with what you hold on sub pay apps.'],
      ]],
      ['Change orders', 'Approved owner COs should appear in SOV — sync from <strong>Change Orders</strong> if lines are missing.', [
        ['Missing CO lines', 'If an approved owner CO is not on the SOV, sync from <strong>Change Orders</strong>.'],
        ['Sync to SOV', 'On the approved Owner CO, use <strong>Sync to SOV</strong> to push lines to budget and pay apps.'],
        ['New lines', 'After sync, refresh the pay app — new SOV rows should appear.'],
        ['Bill CO work', 'Enter work completed on CO lines in the same period as base contract work.'],
      ]],
      ['Attachments', 'Attach lien waivers, stored material photos, and signed G702/G703 PDFs as required.', [
        ['Required docs', 'Check your contract for required attachments each billing period.'],
        ['Lien waivers', 'Attach conditional or unconditional waivers from subs as required.'],
        ['G702/G703', 'Export or attach signed AIA G702/G703 PDFs when configured.'],
        ['Stored materials', 'Attach photos proving stored materials on site if billing stored materials.'],
      ]],
      ['Submit for approval', 'Submit to PM → owner/architect → accounting. Use e-sign when configured.', [
        ['Submit', 'Click <strong>Submit</strong> when SOV and attachments are complete.'],
        ['PM review', 'Project manager reviews amounts and attachments first.'],
        ['Owner/architect', 'Owner or architect certifies per contract — e-sign when enabled.'],
        ['Accounting', 'Accounting gives final approval before invoice to owner.'],
      ]],
      ['Settings', 'Pay app templates, default retainage, and PDF branding are under <strong>Program Settings → Pay Apps</strong>.', [
        ['Program Settings', 'Admins open <strong>Program Settings</strong> from the main navigation.'],
        ['Pay Apps tab', 'Configure templates, default retainage %, and G702/G703 options.'],
        ['PDF branding', 'Set company logo and footer text for owner-facing pay app PDFs.'],
        ['Before first bill', 'Configure settings before creating the first pay app on a new project.'],
      ]],
    ],
    'fa-file-invoice-dollar'
  ),

  submittals: singleGuide(
    'Submittals',
    'Shop drawings, product data, and samples for approval.',
    [
      ['Create submittal', 'Click <strong>New Submittal</strong>. Enter spec section, description, subcontractor, and required date.', [
        ['New Submittal', 'Click <strong>New Submittal</strong> in the toolbar.'],
        ['Spec section', 'Enter the CSI spec section (e.g. 08 71 00) from the contract documents.'],
        ['Description', 'Describe the product, manufacturer, and what is being submitted.'],
        ['Subcontractor', 'Select the responsible sub from the directory.'],
        ['Required date', 'Set the date needed on site — work backward from fab lead time.'],
      ]],
      ['Attach documents', 'Upload PDFs or link files from <strong>Documents</strong>. Use current revision labels.', [
        ['Upload PDF', 'Attach shop drawings, product data, or samples documentation as PDF.'],
        ['Link Documents', 'Or link existing files from <strong>Documents</strong> to avoid duplicates.'],
        ['Revision label', 'Name files with revision (Rev 0, Rev 1) in the filename or metadata.'],
        ['Complete package', 'Include all sheets the architect needs — partial subs get rejected.'],
      ]],
      ['Submit to design team', 'Change status from Draft to <strong>Open</strong>. Ball moves to architect/engineer.', [
        ['Complete draft', 'Verify spec section, attachments, and sub are correct while in Draft.'],
        ['Open', 'Change status to <strong>Open</strong> or click submit to send to design team.'],
        ['Ball moves', 'Ball in Court shifts to architect or designated reviewer.'],
        ['Notification', 'Design team receives notification to review the package.'],
      ]],
      ['Review cycles', 'Record returned actions: Approved, Approved as Noted, Revise and Resubmit, or Rejected.', [
        ['Reviewer action', 'Architect selects Approved, Approved as Noted, Revise and Resubmit, or Rejected.'],
        ['Approved as Noted', 'Minor corrections noted — sub may proceed with noted changes.'],
        ['Revise and Resubmit', 'Major changes required — sub must upload revised PDFs.'],
        ['Rejected', 'Wrong product or non-compliant — sub must submit a new package.'],
      ]],
      ['Resubmit', 'Upload revised PDFs with incremented revision (Rev 1, Rev 2). Keep history for audit.', [
        ['New revision', 'Upload revised PDFs labeled Rev 1, Rev 2, etc.'],
        ['Do not overwrite', 'Keep prior revisions in history — do not delete rejected versions.'],
        ['Address comments', 'Reference architect notes in the resubmit cover or description.'],
        ['Reopen cycle', 'Change status back to Open for another review round.'],
      ]],
      ['Lead time', 'Enter fabrication lead time when approved — feeds schedule and procurement tracking.', [
        ['After approval', 'When status is Approved, enter fabrication lead time in weeks.'],
        ['Schedule feed', 'Lead time may feed schedule activities for procurement milestones.'],
        ['Order date', 'Work backward from required-on-site date minus lead time for order-by date.'],
        ['Long-lead flag', 'Long-lead items should be submitted early — track in submittal log.'],
      ]],
      ['Close', 'Mark <strong>Closed</strong> when approved and distributed to the field.', [
        ['Approved final', 'Confirm final revision is Approved (not just Approved as Noted with open items).'],
        ['Distribute', 'Send approved PDFs to field, sub, and file in <strong>Documents</strong>.'],
        ['Closed status', 'Mark <strong>Closed</strong> so the log reflects completed submittals.'],
        ['Field install', 'Supers use closed submittals as authority to install the approved product.'],
      ]],
      ['Settings', 'Submittal numbering defaults live under <strong>Program Settings → Numbering</strong>.', [
        ['Numbering', 'Admins set submittal prefix and next number under <strong>Program Settings → Numbering</strong>.'],
        ['Before go-live', 'Configure numbering before the team creates the first submittal.'],
        ['Per project', 'Some settings inherit globally — confirm project-specific overrides if any.'],
        ['Log order', 'Sequential numbers help owners and inspectors reference submittals in RFIs.'],
      ]],
    ],
    'fa-file-circle-check'
  ),

  punch_list: singleGuide(
    'Punch List',
    'Track closeout deficiencies by location and responsible party.',
    [
      ['Create an item', 'Click <strong>New Item</strong>. Enter location, description, assignee company, and due date.', [
        ['New Item', 'Click <strong>New Item</strong> in the toolbar.'],
        ['Location', 'Enter room, floor, or area (e.g. "Level 2 — Room 204").'],
        ['Description', 'Describe the deficiency clearly — subs need enough detail to fix without a site visit.'],
        ['Assignee', 'Select the responsible subcontractor company from the directory.'],
        ['Due date', 'Set a due date before turnover or the next walk meeting.'],
      ]],
      ['Add photos', 'Attach photos from site walks so subs know exactly what to fix.', [
        ['Attach photo', 'Use the photo attach button on the punch item form.'],
        ['From Photos module', 'Link photos from <strong>Photos</strong> taken during the walk.'],
        ['Show the issue', 'Circle or markup issues in the photo when markup tools are available.'],
        ['Multiple angles', 'Add 2–3 photos for ambiguous items so there is no dispute.'],
      ]],
      ['Set priority', 'Use priority or type (cosmetic, functional, life-safety) to sort work before turnover.', [
        ['Priority field', 'Set High, Medium, or Low based on turnover impact.'],
        ['Type', 'Classify as cosmetic, functional, or life-safety — life-safety first.'],
        ['Sort list', 'Filter and sort by priority for walk meetings and sub assignments.'],
        ['Owner expectations', 'Align priority with what the owner will reject at final walk.'],
      ]],
      ['Assign Ball in Court', 'Assign to the sub or trade responsible. They fix and mark ready for inspection.', [
        ['Assignee company', 'Ball in Court goes to the assigned sub\'s contact.'],
        ['Sub fixes', 'Sub completes work and marks item ready for inspection or complete.'],
        ['Notification', 'Assignee receives notification when Ball moves to them.'],
        ['Reassign', 'If wrong trade, reassign to the correct sub and notify both parties.'],
      ]],
      ['Verify in field', 'Superintendent or architect verifies — set status to <strong>Complete</strong> or send back open.', [
        ['Site verify', 'Super or architect walks the item before marking complete.'],
        ['Complete', 'Set status to <strong>Complete</strong> when the fix meets spec.'],
        ['Send back', 'If inadequate, reopen and add notes — Ball returns to the sub.'],
        ['Photo verify', 'Compare fix to original photo to confirm the right issue was addressed.'],
      ]],
      ['Bulk export', 'Print or PDF punch lists by floor or company for walk meetings.', [
        ['Filter first', 'Filter by floor, company, or status before export.'],
        ['Print/PDF', 'Use print or export actions for walk meeting handouts.'],
        ['By company', 'Export per sub so each gets only their items at the meeting.'],
        ['Sign-off', 'Some teams print for sign-off at the walk — file signed copies in Documents.'],
      ]],
      ['Link to inspections', ' Tie items to failed inspection lines when corrections require reinspection.', [
        ['Failed inspection', 'When an inspection fails, create punch items from failed checklist lines.'],
        ['Link record', 'Reference the inspection number on the punch item for traceability.'],
        ['Reinspect', 'Schedule reinspection after punch items are marked complete.'],
        ['Close loop', 'Pass reinspection before closing the linked punch items.'],
      ]],
      ['Closeout', 'Filter open items to zero before substantial completion sign-off.', [
        ['Open filter', 'Filter status to Open and work the list to zero.'],
        ['Substantial completion', 'Owner sign-off typically requires no open life-safety or functional items.'],
        ['Cosmetic carry', 'Some cosmetic items may carry past substantial — document in the punch log.'],
        ['Final walk', 'Run a final owner walk with exported list showing all items complete.'],
      ]],
    ],
    'fa-list-check'
  ),

  safety: singleGuide(
    'Safety',
    'Incidents, observations, meetings, and OSHA logs.',
    [
      ['Pick record type', 'Use tabs or filters for incidents, near-misses, observations, toolbox talks, or OSHA 300 logs.', [
        ['Tabs or filters', 'Click tabs or use the type filter for Incidents, Near-Miss, Observations, Toolbox Talks, or OSHA 300.'],
        ['Right form', 'Each type has its own form fields — pick the correct type before creating.'],
        ['OSHA 300', 'Use OSHA 300 log view for recordable tracking and annual posting.'],
        ['List view', 'Browse all records or filter to open corrective actions.'],
      ]],
      ['Report an incident', 'Click <strong>New</strong>. Capture date, time, location, people involved, and narrative while facts are fresh.', [
        ['New record', 'Click <strong>New</strong> immediately after an incident while details are fresh.'],
        ['Date & time', 'Enter exact date and time of the incident.'],
        ['Location', 'Note building area, floor, or exterior location on site.'],
        ['People involved', 'List injured person, witnesses, and companies — required for OSHA and insurance.'],
        ['Narrative', 'Write a factual sequence of events — who, what, when, where, how.'],
      ]],
      ['Classify severity', 'Record recordable vs first aid only — drives OSHA reporting and insurance notices.', [
        ['Recordable', 'Mark recordable if it meets OSHA criteria (medical treatment beyond first aid, lost time, etc.).'],
        ['First aid only', 'First aid only incidents may not be OSHA recordable — classify carefully.'],
        ['OSHA 300', 'Recordables flow to the OSHA 300 log for annual summary posting.'],
        ['Insurance', 'Severe incidents may trigger insurance notice — follow company policy.'],
      ]],
      ['Corrective actions', 'Assign follow-up tasks with due dates and responsible party. Track until closed.', [
        ['Add action', 'Create corrective action items with specific fix (e.g. install guardrail, retrain crew).'],
        ['Assign owner', 'Assign to superintendent, sub, or safety manager with a due date.'],
        ['Track open', 'Filter open corrective actions until all are closed.'],
        ['Verify fix', 'Document verification photos or inspection before closing the action.'],
      ]],
      ['Photos & witnesses', 'Attach site photos and witness statements as attachments or linked documents.', [
        ['Scene photos', 'Photograph the incident location, equipment, and conditions.'],
        ['Witness statements', 'Attach written or typed witness statements as PDF or linked docs.'],
        ['Preserve evidence', 'Do not alter the scene until documented if investigation is pending.'],
        ['Documents link', 'Link files from <strong>Documents</strong> for formal investigation reports.'],
      ]],
      ['Toolbox talks', 'Log topic, attendees, and sign-in sheet PDF for audit trail.', [
        ['New toolbox talk', 'Create a toolbox talk record for each site safety meeting.'],
        ['Topic', 'Enter the safety topic covered (e.g. fall protection, heat illness).'],
        ['Attendees', 'List attendees or attach signed sign-in sheet PDF.'],
        ['Regular schedule', 'Weekly toolbox talks are common — log every session for OSHA audit defense.'],
      ]],
      ['Review trends', 'Filter by month or subcontractor to spot repeat hazards before they become recordables.', [
        ['Monthly filter', 'Filter incidents and observations by month for trend review.'],
        ['By subcontractor', 'Identify subs with repeat near-misses or observations.'],
        ['Safety meeting', 'Present trends at weekly safety meetings with supers and subs.'],
        ['Prevent recordables', 'Address repeat hazards before they escalate to recordable incidents.'],
      ]],
      ['Permissions', 'Safety data may be restricted — only authorized roles can edit closed incidents.', [
        ['Restricted access', 'Closed incidents may be view-only for most users.'],
        ['Safety role', 'Safety managers and admins typically can edit closed records.'],
        ['Legal hold', 'Do not delete incident records — deactivate users instead of wiping history.'],
        ['Ask admin', 'Request elevated access if you need to correct a closed record error.'],
      ]],
    ],
    'fa-helmet-safety'
  ),

  photos: singleGuide(
    'Photos',
    'Job site photos organized by date, album, or tag.',
    [
      ['Upload', 'Click <strong>Upload</strong> or drag files. Add date, location, and tags at upload for easier search later.', [
        ['Upload button', 'Click <strong>Upload</strong> or drag image files into the gallery area.'],
        ['Date', 'Set the photo date — defaults to today but change for photos taken earlier.'],
        ['Location', 'Add building area or grid reference for field lookup later.'],
        ['Tags', 'Add tags (trade, milestone, issue) so search finds photos at closeout.'],
      ]],
      ['Browse albums', 'Use albums or filters by date, trade, or keyword. Thumbnails open a lightbox with metadata.', [
        ['Albums', 'Browse by album if your project organizes photos by phase or area.'],
        ['Date filter', 'Filter by date range to find photos from a specific week or pour.'],
        ['Keyword search', 'Search tags or filenames for quick retrieval.'],
        ['Lightbox', 'Click a thumbnail to open full size with date, location, and uploader metadata.'],
      ]],
      ['Link to records', 'Attach photos to daily logs, punch items, RFIs, or inspections from those modules\' attach actions.', [
        ['From other modules', 'In daily log, punch, RFI, or inspection forms, use attach photo action.'],
        ['Pick from gallery', 'Select existing photos from this project\'s gallery.'],
        ['Bidirectional', 'Linked photos appear in both the module record and the Photos gallery.'],
        ['Evidence chain', 'Linking creates audit trail between visual evidence and formal records.'],
      ]],
      ['Markup', 'Use markup tools (when available) to circle issues before sending to subs.', [
        ['Open markup', 'In lightbox or photo detail, click markup or annotate when available.'],
        ['Circle issues', 'Draw circles, arrows, or text on the image to highlight deficiencies.'],
        ['Save markup', 'Save annotated version — original may be preserved separately.'],
        ['Send to sub', 'Share marked-up photo with punch or RFI so sub knows exact location.'],
      ]],
      ['Share externally', 'Generate share links or include in weekly reports — respect owner confidentiality settings.', [
        ['Share link', 'Generate time-limited share link when external viewers need access.'],
        ['Weekly report', 'Attach key photos to weekly reports for owner distribution.'],
        ['Confidentiality', 'Check program security — some albums may be internal-only.'],
        ['Owner approval', 'Confirm owner contract allows photo sharing before external links.'],
      ]],
      ['Mobile capture', 'Field staff can upload from phones; sync appears in the project gallery within seconds.', [
        ['Phone upload', 'Use mobile browser or app to upload directly from the job site.'],
        ['Quick tags', 'Add location and tags at upload — easier than tagging later at the desk.'],
        ['Same gallery', 'Mobile uploads appear in the project gallery for office staff immediately.'],
        ['Cell signal', 'Large uploads may wait for Wi-Fi — save locally until connected if needed.'],
      ]],
      ['Storage hygiene', 'Delete blurry duplicates and keep naming consistent (e.g. area + date) for fast retrieval at closeout.', [
        ['Delete duplicates', 'Remove blurry or duplicate shots to reduce clutter.'],
        ['Naming convention', 'Use consistent names like "L2-East-2026-03-15" for searchability.'],
        ['Closeout package', 'Clean gallery before exporting turnover photo sets to owner.'],
        ['Retention policy', 'Follow company policy on how long to keep site photos after project end.'],
      ]],
      ['Permissions', 'Some albums may be internal-only — check program security if owners should not see certain images.', [
        ['Album permissions', 'Folder-level permissions may hide albums from owner portal users.'],
        ['Internal only', 'Mark sensitive photos (pricing, VE) internal-only before upload.'],
        ['Program security', 'Admins configure photo visibility under program security settings.'],
        ['Before sharing', 'Verify audience before generating external share links.'],
      ]],
    ],
    'fa-camera'
  ),

  inspections: singleGuide(
    'Inspections',
    'Checklists, inspections, and failed-item follow-up.',
    [
      ['Choose template', 'Pick an inspection type (framing, fire, final, etc.). Templates come from <strong>Program Settings → Inspections</strong>.', [
        ['Inspection type', 'Select type (framing, electrical rough, fire, final, etc.) from the dropdown.'],
        ['Templates', 'Admins configure checklist templates under <strong>Program Settings → Inspections</strong>.'],
        ['Right checklist', 'Wrong template means wrong line items — pick the type that matches the walk.'],
        ['Custom lines', 'Some templates allow adding ad-hoc lines for one-off checks.'],
      ]],
      ['Schedule or start', 'Create inspection with location, inspector, and date. Save as draft until the walk occurs.', [
        ['New inspection', 'Click <strong>New</strong> and select template, location, and scheduled date.'],
        ['Inspector', 'Assign internal super or external agency inspector name.'],
        ['Draft', 'Save as draft until the walk happens — then complete checklist on site.'],
        ['Calendar', 'Scheduled inspections may appear on project calendar views.'],
      ]],
      ['Complete checklist', 'Pass/fail each line. Add notes and photos on failed items — subs need clear corrective direction.', [
        ['Each line', 'Mark each checklist line Pass or Fail as you walk the area.'],
        ['Failed notes', 'On fail, add a clear note: what is wrong and what spec requires.'],
        ['Failed photos', 'Attach photos to failed lines — same detail as punch list items.'],
        ['Partial pass', 'Some templates allow N/A — use when line does not apply to this area.'],
      ]],
      ['Ball in Court', 'Failed items can assign responsibility to a subcontractor until reinspection passes.', [
        ['Assign on fail', 'When a line fails, assign Ball in Court to the responsible sub.'],
        ['Sub corrects', 'Sub fixes the issue and notifies super for reinspection.'],
        ['Reinspect line', 'Reinspect individual lines or schedule a follow-up inspection.'],
        ['Pass to close', 'Ball clears when all assigned lines pass.'],
      ]],
      ['Reinspect', 'Create a follow-up inspection or close individual lines when corrections are verified.', [
        ['Follow-up inspection', 'Create a new inspection linked to the prior failed walk if needed.'],
        ['Close lines', 'Mark individual lines pass when corrections are verified in the field.'],
        ['Agency return', 'For jurisdictional inspections, schedule agency reinspection date.'],
        ['Document pass', 'Attach photo proof on reinspection pass for closeout binder.'],
      ]],
      ['Permits & agencies', 'Record agency inspector name and permit number for jurisdictional audits.', [
        ['Florida Directory', 'Open the <strong>Florida Directory</strong> tab for all 67 counties and municipal building departments with permit office contacts.'],
        ['City vs county AHJ', 'Most field inspections are done by the <strong>city</strong> inside city limits; unincorporated areas use the <strong>county</strong> AHJ.'],
        ['Schedule inspections', 'Each directory entry shows whether to <strong>call</strong>, use the <strong>website</strong>, or both — click a row to apply contacts to an inspection.'],
        ['Permit #', 'Enter the active permit number for the work being inspected.'],
        ['Agency inspector', 'Record name and agency (city, county, fire marshal).'],
        ['Audit trail', 'Jurisdictions may request logs at final — keep permit and scheduling fields complete.'],
      ]],
      ['Export PDF', 'Print official checklist PDFs for owner binders and turnover packages.', [
        ['Export action', 'Use export or print to generate PDF of completed checklist.'],
        ['Sign-off', 'Some PDFs include inspector signature block for agency records.'],
        ['Owner binder', 'File passed inspection PDFs in <strong>Documents</strong> closeout folder.'],
        ['Failed history', 'Keep failed-then-passed records to show correction trail.'],
      ]],
      ['Close', 'Mark inspection <strong>Passed</strong> when all required lines pass or exceptions are documented.', [
        ['All pass', 'Every required line must pass or have documented exception.'],
        ['Passed status', 'Set overall status to <strong>Passed</strong> when walk is complete.'],
        ['Open failures', 'Do not mark Passed with open failed lines unless formally deferred in writing.'],
        ['Schedule unlock', 'Passed inspections may unlock dependent schedule activities.'],
      ]],
    ],
    'fa-clipboard-check'
  ),

  schedule: singleGuide(
    'Schedule',
    'Activities, milestones, and lookahead.',
    [
      ['Open schedule view', 'See Gantt or list view of activities for the active project. Zoom to week or month as needed.', [
        ['Gantt vs list', 'Toggle between Gantt chart and list view depending on your task.'],
        ['Active project', 'Confirm the header shows the correct project — schedule is project-specific.'],
        ['Zoom', 'Zoom to week or month for detail vs big-picture planning.'],
        ['Today line', 'Use the today marker on Gantt to see what should be in progress now.'],
      ]],
      ['Add activities', 'Create tasks with start/finish, predecessor links, and responsible company.', [
        ['New activity', 'Click add task/activity and enter name, start, and finish dates.'],
        ['Duration', 'Set duration in days — finish date may calculate from start + duration.'],
        ['Responsible company', 'Assign the sub or internal team responsible for the work.'],
        ['WBS', 'Organize under summary tasks or phases for readable Gantt structure.'],
      ]],
      ['Link predecessors', ' Tie finish-to-start links so date changes ripple correctly when delays occur.', [
        ['Predecessor field', 'Select the task that must finish before this one starts.'],
        ['Finish-to-start', 'Most links are finish-to-start (FS) — prior task end drives successor start.'],
        ['Lag', 'Add lag days if required cure time or inspection wait exists between tasks.'],
        ['Critical path', 'Broken or missing links make the critical path unreliable — link honestly.'],
      ]],
      ['Baseline', 'Set a baseline snapshot after owner approval — compare current vs baseline for variance reports.', [
        ['When to baseline', 'Set baseline after owner approves the schedule, before major field work.'],
        ['Set baseline', 'Use set baseline action to snapshot current start/finish dates.'],
        ['Variance', 'Compare current schedule to baseline in variance or tracking views.'],
        ['Re-baseline', 'Only re-baseline with owner agreement when scope or contract dates change formally.'],
      ]],
      ['Update progress', 'Field updates % complete weekly. Keep critical path activities honest for reliable forecast dates.', [
        ['Weekly update', 'Each week, supers or PMs update % complete on in-progress activities.'],
        ['Critical path first', 'Prioritize accuracy on critical path tasks — they drive the project end date.'],
        ['Remaining duration', 'Some views use remaining duration — align % complete with field reality.'],
        ['Forecast', 'Honest progress updates produce reliable forecast completion dates.'],
      ]],
      ['Filters', 'Filter by company, phase, or critical path to focus meetings on what matters this week.', [
        ['By company', 'Filter to one sub\'s activities for subcontractor coordination meetings.'],
        ['By phase', 'Filter to current phase (structure, envelope, interiors) for lookahead.'],
        ['Critical path', 'Show only critical path tasks for executive schedule reviews.'],
        ['Save filter', 'Reuse filters each week for consistent meeting agendas.'],
      ]],
      ['Import/export', 'Import P6 or MSP XML when migrating; export for owner monthly updates.', [
        ['Import XML', 'Import Primavera P6 or Microsoft Project XML when bringing an external schedule.'],
        ['Map fields', 'Verify activity names and dates after import — spot-check critical milestones.'],
        ['Export', 'Export XML or PDF for owner monthly schedule updates per contract.'],
        ['Single source', 'Pick one master schedule — avoid parallel Excel schedules that diverge.'],
      ]],
      ['Integrate', 'Delays from RFIs or submittals should be reflected here — do not let schedule live only in email.', [
        ['RFI delays', 'When an RFI blocks work, extend affected activity dates and note RFI # in notes.'],
        ['Submittal lead time', 'Long-lead submittals should drive procurement activity dates.'],
        ['Change orders', 'Approved scope changes may add activities or extend durations.'],
        ['Living document', 'Update the schedule when delays happen — email alone does not protect claims.'],
      ]],
    ],
    'fa-calendar-days'
  ),

  budget: singleGuide(
    'Budget',
    'Original budget, modifications, and cost code totals.',
    [
      ['View cost codes', 'The grid shows budget line by cost code: original, modifications, committed, and actuals where synced.', [
        ['Budget grid', 'Open <strong>Budget</strong> for the active project to see the cost code table.'],
        ['Columns', 'Read Original, Modifications, Committed, and Actuals columns per line.'],
        ['Expand rows', 'Drill into a cost code to see commitment or transaction detail where supported.'],
        ['Totals row', 'Use the totals row to compare project-wide budget vs committed vs actual.'],
      ]],
      ['Original budget', 'Enter or import the owner-approved budget at project start. Lock when baseline is set.', [
        ['Enter lines', 'Add or import each cost code with original budget amount at job start.'],
        ['Match contract', 'Original budget should match the owner contract SOV or GMP breakdown.'],
        ['Import Excel', 'Use Excel import if your company has a standard budget template.'],
        ['Lock baseline', 'Lock original budget after owner approval so modifications are traceable.'],
      ]],
      ['Budget modifications', 'Use budget transfers to move money between codes without a change order when policy allows.', [
        ['Transfer action', 'Use budget transfer to move dollars from one cost code to another.'],
        ['Net zero', 'Transfers should net to zero across the project unless adding contingency formally.'],
        ['Policy check', 'Confirm your contract allows internal transfers without owner CO.'],
        ['Document reason', 'Add notes on why money moved — auditors ask at job close.'],
      ]],
      ['Commitments', 'Committed column reflects sub contracts and POs from <strong>Commitments</strong> — open that module to drill down.', [
        ['Committed column', 'Shows total committed per cost code from sub contracts and POs.'],
        ['Drill down', 'Click through to <strong>Commitments</strong> to see which contracts hit each code.'],
        ['Over commitment', 'If committed exceeds budget, investigate open COs or forecasting.'],
        ['New sub', 'Create commitments before sub COs so committed column updates correctly.'],
      ]],
      ['Change orders', 'Approved owner and sub COs update modified budget — sync from <strong>Change Orders</strong> if totals look stale.', [
        ['Modified column', 'Approved COs increase or decrease the modified budget column.'],
        ['Stale totals', 'If a recent CO is missing, open <strong>Change Orders</strong> and use <strong>Sync to SOV</strong> on the approved CO.'],
        ['Owner vs sub', 'Owner COs affect revenue budget; sub COs affect cost budget — both show in modified.'],
        ['Pending COs', 'Pending PCOs do not update budget until approved and synced.'],
      ]],
      ['Forecast', 'Jump to <strong>Forecast</strong> for projected final cost based on commitments and trends.', [
        ['Open Forecast', 'Click <strong>Forecast</strong> from budget actions or sidebar.'],
        ['Projected final', 'Forecast rolls up projected final cost per cost code.'],
        ['Variances', 'Red variances flag codes trending over budget — investigate before month-end.'],
        ['Monthly review', 'Review forecast with PM and accounting at monthly job meetings.'],
      ]],
      ['Export', 'Export Excel for owner reporting or Sage reconciliation.', [
        ['Export button', 'Use <strong>Export</strong> to download budget grid as Excel.'],
        ['Owner reports', 'Send formatted export for owner monthly cost reports if required.'],
        ['Sage reconcile', 'Accounting compares export to Sage job cost for reconciliation.'],
        ['Point in time', 'Note export date — budget changes after export will not be reflected.'],
      ]],
      ['Settings', 'Cost code structure and Sage mapping live under <strong>Program Settings → Sage 300</strong> and project setup.', [
        ['Sage mapping', 'Admins map Case PM cost codes to Sage phase codes under <strong>Program Settings → Sage 300</strong>.'],
        ['Project setup', 'Confirm project inherits correct cost code list at project creation.'],
        ['New codes', 'Adding codes mid-job requires mapping in Sage before ERP export.'],
        ['Do not duplicate', 'Duplicate cost codes break reporting — use unique codes per line.'],
      ]],
    ],
    'fa-coins'
  ),

  forecast: singleGuide(
    'Forecast',
    'Projected final cost and variance to budget.',
    [
      ['Open forecast', 'View rolls up budget, commitments, actuals, and manual projections by cost code.', [
        ['Forecast page', 'Open <strong>Forecast</strong> from the sidebar for the active project.'],
        ['Roll-up columns', 'See original budget, committed, actuals, and projected final per cost code.'],
        ['Totals row', 'Use the bottom totals row for job-wide forecast vs budget.'],
        ['Refresh', 'Sync or refresh if you just approved a CO or posted a pay app.'],
      ]],
      ['Review variances', 'Red or amber variances flag codes trending over budget — investigate commitments and open COs.', [
        ['Variance colors', 'Red or amber highlights codes where projected final exceeds modified budget.'],
        ['Drill in', 'Click the cost code to see commitments and open change orders driving the overrun.'],
        ['Root cause', 'Determine if overrun is missing CO, scope creep, or bad original estimate.'],
        ['Action plan', 'Document corrective action — CO, VE, or budget transfer per policy.'],
      ]],
      ['Enter projections', 'PMs can override projected final cost per line when market or scope shifts before COs are issued.', [
        ['Override field', 'Enter manual projected final on a line when you know cost will exceed commitment.'],
        ['Before CO', 'Use overrides when a CO is coming but not yet approved — document in notes.'],
        ['Update monthly', 'Revisit overrides each month as quotes and field conditions change.'],
        ['Remove override', 'Clear override when approved CO or commitment catches up to reality.'],
      ]],
      ['Include pending COs', 'Decide whether to include pending PCOs in projections — document assumptions in notes.', [
        ['Pending PCOs', 'Some teams add pending owner PCO amounts to forecast manually.'],
        ['Assumption notes', 'Document in forecast notes whether pending COs are included or excluded.'],
        ['Conservative vs aggressive', 'Align with owner reporting policy — conservative excludes pending.'],
        ['Bonding', 'Bonding companies may ask how pending COs are treated — be consistent.'],
      ]],
      ['Compare to budget', 'Use totals row to see forecast vs original and modified budget at a glance.', [
        ['Modified budget', 'Compare projected final to modified budget (includes approved COs).'],
        ['Original budget', 'Compare to original for gross variance since contract award.'],
        ['Margin impact', 'For CM jobs, forecast vs owner budget drives projected fee and margin.'],
        ['Export snapshot', 'Export monthly for job review meeting slides.'],
      ]],
      ['Refresh data', 'Sync or refresh if commitments or pay apps just posted — stale actuals skew the forecast.', [
        ['After pay app', 'Refresh after owner pay app approval so actuals update.'],
        ['After sub CO', 'Sync after approved sub CO so committed and modified budget refresh.'],
        ['Sage sync', 'If actuals come from Sage, confirm last sync timestamp.'],
        ['Stale warning', 'If numbers look weeks old, run sync before presenting to ownership.'],
      ]],
      ['Export', 'Export for monthly job reviews with ownership and bonding companies.', [
        ['Export Excel', 'Download forecast grid for monthly job review package.'],
        ['Bonding', 'Bonding agents often request forecast export with variance commentary.'],
        ['Owner CM', 'Owner reps on CM jobs may receive forecast monthly per contract.'],
        ['Archive', 'File exports in <strong>Documents</strong> for historical comparison at closeout.'],
      ]],
      ['Close the loop', 'Large variances should become change events or budget transfers — do not leave silent overrun.', [
        ['Threshold', 'Define a dollar threshold above which variance requires a change event or CO.'],
        ['Change event', 'Create <strong>Change Event</strong> when scope drove the overrun.'],
        ['Budget transfer', 'Use transfer only when policy allows and scope did not change.'],
        ['Silent overrun', 'Unexplained forecast overruns damage trust at job review — always document.'],
      ]],
    ],
    'fa-chart-line'
  ),

  commitments: singleGuide(
    'Commitments',
    'Subcontracts and purchase orders tied to the budget.',
    [
      ['Browse commitments', 'List shows contract number, vendor, original value, approved COs, and remaining.', [
        ['Commitments list', 'Open <strong>Commitments</strong> for the active project.'],
        ['Contract #', 'Each row shows SC- or PO-style contract number.'],
        ['Vendor', 'Vendor column links to the company in <strong>Companies</strong>.'],
        ['Remaining', 'Remaining column shows contract value minus billed/paid per your setup.'],
      ]],
      ['Create commitment', 'Click <strong>New</strong>. Pick vendor from <strong>Companies</strong>, cost code, and contract amount.', [
        ['New', 'Click <strong>New</strong> in the commitments toolbar.'],
        ['Vendor', 'Select vendor from <strong>Companies</strong> — must exist before creating commitment.'],
        ['Cost code', 'Assign primary cost code(s) for budget committed column rollup.'],
        ['Contract amount', 'Enter original contract value matching the signed subcontract.'],
      ]],
      ['SOV lines', 'Enter commitment SOV matching how you will pay — aligns with sub pay apps and CPCOs.', [
        ['SOV grid', 'On the commitment form, enter SOV lines: cost code, description, amount.'],
        ['Match subcontract', 'SOV should mirror the subcontract breakdown for clean sub pay apps.'],
        ['CPCO alignment', 'Future CPCOs and sub COs attach to these SOV lines.'],
        ['At least one line', 'Most workflows require at least one SOV row before approval.'],
      ]],
      ['Execute contract', 'Upload signed subcontract PDF to <strong>Documents</strong> and link here.', [
        ['Signed PDF', 'Upload fully executed subcontract to <strong>Documents</strong>.'],
        ['Link', 'Link the document on the commitment record for audit.'],
        ['Execute status', 'Mark commitment executed per your workflow when contract is signed.'],
        ['Insurance', 'Verify sub COI is current in <strong>Companies</strong> before mobilization.'],
      ]],
      ['Change via CPCO', 'Sub scope changes flow: Change Event → RFQ → CPCO → Sub CO — not by editing original value silently.', [
        ['No silent edits', 'Do not change original commitment value for scope changes — use change order path.'],
        ['Change event', 'Start at <strong>Change Orders → Change Events</strong> for sub scope changes.'],
        ['RFQ → CPCO → Sub CO', 'Follow RFQ pricing, CPCO draft, and Sub CO approval to amend contract.'],
        ['Approved CO updates', 'Approved sub CO updates committed value on this commitment automatically.'],
      ]],
      ['Retainage & terms', 'Record retainage % and payment terms for pay application alignment.', [
        ['Retainage %', 'Enter retainage percentage matching the subcontract.'],
        ['Payment terms', 'Record net 30, net 45, or other terms for AP alignment.'],
        ['Sub pay apps', 'Retainage on sub pay apps should match commitment settings.'],
        ['Release', 'Document retainage release terms for final payment.'],
      ]],
      ['ERP sync', 'Approved commitments may export to Sage — check ERP queue after approval.', [
        ['After approval', 'When commitment is approved/executed, check <strong>ERP Queue</strong> on Change Orders or accounting module.'],
        ['Sage vendor', 'Confirm vendor maps to correct Sage vendor ID before export.'],
        ['Posted', 'Wait for posted status before assuming Sage has the commitment.'],
        ['Mapping errors', 'Fix cost code mapping in <strong>Program Settings → Sage 300</strong> if export fails.'],
      ]],
      ['One vendor per SC', 'Each subcontract commitment is one vendor — split trades into separate commitments.', [
        ['One vendor', 'Each SC number ties to exactly one subcontractor company.'],
        ['Split trades', 'Electrical and plumbing on one job need separate commitments if separate contracts.'],
        ['Multiple scopes', 'If one sub has one contract covering multiple trades, one commitment is correct.'],
        ['Accounting', 'Sage expects one vendor per subcontract — duplicates cause payment errors.'],
      ]],
    ],
    'fa-file-contract'
  ),

  companies: singleGuide(
    'Companies & Vendors',
    'Global directory of owners, subs, architects, and suppliers.',
    [
      ['Search companies', 'Use search and type filters (Owner, Sub, Vendor, Architect) to find a record quickly.', [
        ['Search box', 'Type company name or partial name in the search field.'],
        ['Type filter', 'Filter by Owner, Subcontractor, Vendor, Architect, etc.'],
        ['Sort', 'Sort by name or type to browse alphabetically.'],
        ['Quick open', 'Click a row to open company detail and contacts.'],
      ]],
      ['Add company', 'Click <strong>New Company</strong>. Enter legal name, type, tax ID, and primary address.', [
        ['New Company', 'Click <strong>New Company</strong> in the toolbar.'],
        ['Legal name', 'Enter exact legal name for contracts, COIs, and Sage vendor setup.'],
        ['Company type', 'Set type (Sub, Owner, Architect, Vendor) for filters and routing.'],
        ['Tax ID & address', 'Enter tax ID and primary address for 1099 and insurance certificates.'],
      ]],
      ['Contacts', 'Add contact people under each company — emails here feed RFQs, submittals, and user invites.', [
        ['Contacts tab', 'On company detail, open Contacts and click add.'],
        ['Name & email', 'Enter name, title, email, and phone for each contact.'],
        ['Primary contact', 'Mark primary for default routing on RFQs and submittals.'],
        ['Portal users', 'Contacts with portal access need linked user accounts under <strong>Users</strong>.'],
      ]],
      ['Insurance & certs', 'Track GL, WC expiration, and COI attachments. Set alerts before policies lapse.', [
        ['COI upload', 'Attach current certificate of insurance PDF on the company record.'],
        ['Expiration dates', 'Enter GL and WC expiration dates for alert reminders.'],
        ['Before mobilize', 'Do not issue PO or commitment until COI is current per your policy.'],
        ['Renewal chase', 'Filter expiring soon and email subs before policies lapse.'],
      ]],
      ['Link to projects', 'Assign companies on <strong>Project Directory</strong> so they appear on job-specific dropdowns.', [
        ['Global vs project', 'Companies is global — project directory ties them to a specific job.'],
        ['Add to directory', 'On <strong>Project Directory</strong>, add company and contacts for the active project.'],
        ['Dropdowns', 'Only directory-linked companies appear on job RFIs, submittals, and commitments.'],
        ['New sub on job', 'Add to Companies first, then Project Directory, then create commitment.'],
      ]],
      ['Portal companies', 'Mark portal-enabled subs so RFQ and submittal portals authenticate correctly.', [
        ['Portal flag', 'Enable portal access on company or user record per admin workflow.'],
        ['RFQ portal', 'Portal subs receive RFQs and enter quotes without full Case PM license.'],
        ['Submittal portal', 'Subs upload submittal PDFs through portal when enabled.'],
        ['Test login', 'After setup, test portal login with sub contact before first live RFQ.'],
      ]],
      ['Merge duplicates', 'Resolve duplicate vendor records before commitments — accounting needs one vendor ID.', [
        ['Find duplicates', 'Search similar names (e.g. "ABC Electric" vs "ABC Electric Inc").'],
        ['Merge or deactivate', 'Use merge tools or deactivate duplicate per admin procedure.'],
        ['Before commitments', 'Merge before creating commitments — moving commitments later is painful.'],
        ['Sage match', 'One company record should map to one Sage vendor ID.'],
      ]],
      ['Settings', 'Default company types and required fields may be configured in program workflow settings.', [
        ['Program Settings', 'Admins configure default company types and required fields.'],
        ['Required fields', 'Tax ID or insurance may be required before save — follow prompts.'],
        ['Workflow', 'Some workflows block commitment until COI is on file.'],
        ['Go-live', 'Configure company settings before importing vendor lists from Sage.'],
      ]],
    ],
    'fa-building'
  ),

  users: singleGuide(
    'User Management',
    'Accounts, roles, and module permissions.',
    [
      ['Browse users', 'See all staff and portal users with role, company, and last login.', [
        ['Users list', 'Open <strong>Users</strong> from admin navigation to see all accounts.'],
        ['Role column', 'Review role (Admin, PM, Superintendent, Portal, etc.) per user.'],
        ['Last login', 'Last login helps identify inactive accounts to deactivate.'],
        ['Search', 'Search by name or email to find a specific user quickly.'],
      ]],
      ['Invite user', 'Click <strong>New User</strong>. Enter name, email, role, and company. They receive a setup email.', [
        ['New User', 'Click <strong>New User</strong> in the toolbar.'],
        ['Name & email', 'Enter full name and work email — setup link goes to this address.'],
        ['Role', 'Assign role that controls default module access.'],
        ['Company', 'For portal users, tie to external company; for staff, tie to your firm.'],
        ['Send invite', 'Save — user receives email to set password and activate account.'],
      ]],
      ['Set role', 'Roles (Admin, PM, Superintendent, Accounting, etc.) control default module access.', [
        ['Role dropdown', 'Pick role when creating or editing a user.'],
        ['Admin', 'Admin has full access including Program Settings — limit to trusted staff.'],
        ['PM / Super', 'PM and Superintendent roles get field and management modules by default.'],
        ['Accounting', 'Accounting role focuses on pay apps, budget, ERP — may hide field modules.'],
      ]],
      ['Module permissions', 'Fine-tune access per module: view, edit, or admin. Hide financials for field-only accounts if needed.', [
        ['Permissions tab', 'On user edit, open module permissions beyond the base role.'],
        ['View vs edit', 'Grant view-only on budget for supers who should see but not change numbers.'],
        ['Hide financials', 'Remove budget, forecast, and pay app access for field-only accounts.'],
        ['Per module', 'Toggle RFIs, submittals, safety, etc. individually as needed.'],
      ]],
      ['Portal vs staff', 'Portal users are tied to external companies — limit them to their project data only.', [
        ['Portal role', 'Assign portal role for external subs and design partners.'],
        ['Company tie', 'Link portal user to their company — they only see that company\'s project data.'],
        ['No admin', 'Never grant portal users admin or Program Settings access.'],
        ['Project scope', 'Portal users see only projects where their company is on the directory.'],
      ]],
      ['Reset password', 'Admins can force password reset or unlock after lockout from security policy.', [
        ['Reset action', 'On user record, click force password reset or send reset email.'],
        ['Lockout', 'Unlock account if user exceeded failed login attempts.'],
        ['Security policy', 'Password rules live under <strong>Program Settings → Security</strong>.'],
        ['Verify identity', 'Confirm requester identity before resetting sensitive accounts.'],
      ]],
      ['2FA', 'Require two-factor authentication for sensitive roles under security settings.', [
        ['Security settings', 'Admins enable 2FA requirement under Program Settings security.'],
        ['Sensitive roles', 'Require 2FA for Admin, Accounting, and PM roles handling financials.'],
        ['User setup', 'Users enroll authenticator app on first login after 2FA is required.'],
        ['Recovery', 'Document recovery process for lost devices before enforcing 2FA.'],
      ]],
      ['Deactivate', 'Disable users who leave the company instead of deleting — preserves audit history.', [
        ['Deactivate', 'Set user inactive when they leave — do not delete the account.'],
        ['Audit trail', 'Inactive users remain on historical records (who created RFIs, approved COs).'],
        ['Rehire', 'Reactivate and reset password if employee returns.'],
        ['Portal offboarding', 'Deactivate portal users when sub PM changes — invite new contact.'],
      ]],
    ],
    'fa-users'
  ),

  documents: singleGuide(
    'Documents',
    'Project folders, files, and sharing.',
    [
      ['Folder tree', 'Browse folders in the left panel. Create folders to mirror spec divisions or company standards.', [
        ['Left panel', 'Use the folder tree on the left to navigate project folders.'],
        ['Create folder', 'Right-click or use <strong>New Folder</strong> to create structure.'],
        ['Spec divisions', 'Many teams mirror CSI divisions (01 General, 03 Concrete, etc.).'],
        ['Permissions early', 'Set folder permissions before uploading sensitive bid documents.'],
      ]],
      ['Upload files', 'Drag files or click <strong>Upload</strong>. Version large sets instead of overwriting without trace.', [
        ['Upload', 'Drag files into the folder or click <strong>Upload</strong>.'],
        ['Versioning', 'Upload new version instead of overwrite — keeps audit trail of revisions.'],
        ['Naming', 'Use consistent names: date + subject + revision.'],
        ['Large sets', 'Upload plan sets in batches by discipline to avoid timeout on huge ZIPs.'],
      ]],
      ['Preview & edit', 'Open PDFs in the viewer; edit Word or Excel in browser editors when supported.', [
        ['Preview', 'Click a file to preview PDF in the browser viewer.'],
        ['Office edit', 'Word/Excel may open in browser editor when integration is enabled.'],
        ['Download', 'Download for offline edit if browser editor is not available.'],
        ['Re-upload version', 'Upload edited file as new version after offline changes.'],
      ]],
      ['Permissions', 'Folder permissions restrict owner vs sub visibility — set before sharing sensitive bids.', [
        ['Folder permissions', 'Right-click folder → permissions or use permissions panel.'],
        ['Owner vs sub', 'Restrict sub folders to sub portal users only.'],
        ['Before upload', 'Set permissions before uploading bid tabs or internal estimates.'],
        ['Inherit', 'Subfolders may inherit parent permissions — verify after create.'],
      ]],
      ['Link elsewhere', 'Attach document links from RFIs, submittals, meetings, and daily logs.', [
        ['Attach from module', 'In RFI, submittal, or meeting forms, use attach from <strong>Documents</strong>.'],
        ['Pick file', 'Browse to the correct folder and select the file link.'],
        ['No duplicate', 'Linking avoids duplicate copies — one source of truth in Documents.'],
        ['Broken links', 'Renaming or moving files may break links — move within Documents when possible.'],
      ]],
      ['Share externally', 'Create time-limited share links for owners or subs who do not have full accounts.', [
        ['Share link', 'Select file → generate share link with expiration date.'],
        ['Time limit', 'Set short expiration for sensitive documents.'],
        ['No account needed', 'External viewers open link without Case PM login.'],
        ['Revoke', 'Revoke link if shared to wrong party.'],
      ]],
      ['Search', 'Search by filename or metadata. Use consistent naming (date + subject) for faster finds.', [
        ['Search box', 'Use global or folder search by filename keyword.'],
        ['Metadata', 'Some fields support tags or description search.'],
        ['Closeout', 'Good naming pays off when assembling turnover packages years later.'],
        ['Filter type', 'Filter by PDF, Excel, etc. to narrow results.'],
      ]],
      ['Settings', 'Default folder templates and storage limits are under <strong>Program Settings → Documents</strong>.', [
        ['Program Settings', 'Admins open <strong>Program Settings → Documents</strong>.'],
        ['Folder templates', 'Configure default folder tree for new projects.'],
        ['Storage limits', 'Review storage quotas and cleanup policy.'],
        ['New projects', 'New projects inherit template folders at creation.'],
      ]],
    ],
    'fa-folder-open'
  ),

  drawings: singleGuide(
    'Drawings',
    'Plan sets, revisions, and sheet log.',
    [
      ['Upload set', 'Upload PDF plan sets by discipline (A, S, M, E). Group by revision date or bulletin.', [
        ['Upload', 'Click <strong>Upload</strong> and select PDF plan files by discipline.'],
        ['Discipline', 'Group Architectural (A), Structural (S), Mechanical (M), Electrical (E) separately.'],
        ['Revision date', 'Name or tag uploads with bulletin or revision date (e.g. "Bulletin 3 — 2026-02-01").'],
        ['Full set', 'Upload complete sets — partial uploads confuse field staff looking for one sheet.'],
      ]],
      ['Sheet log', 'Each sheet gets number, title, revision, and issue date — matches field set labels.', [
        ['Sheet number', 'Enter sheet number exactly as on title block (A-101, S-201).'],
        ['Title', 'Enter sheet title from title block for search.'],
        ['Revision', 'Set current revision letter or number per sheet.'],
        ['Issue date', 'Record date issued — critical for RFI and submittal references.'],
      ]],
      ['Current revision', 'Mark superseded sheets so field staff always open the latest revision.', [
        ['Superseded flag', 'Mark old revisions superseded when new bulletin uploads.'],
        ['Current set filter', 'Field should filter to "current" only before printing or RFIs.'],
        ['Bulletin log', 'Maintain log of what changed each bulletin for owner records.'],
        ['Wrong revision', 'RFIs referencing wrong revision are a top cause of rework — verify before sending.'],
      ]],
      ['Link RFIs', 'Reference sheet numbers on RFIs and punch items so answers point to the right detail.', [
        ['RFI form', 'On RFI create, reference drawing sheet numbers in subject or question.'],
        ['Punch items', 'Link punch items to sheet and detail reference.'],
        ['Click through', 'Some workflows link directly to sheet in Drawings module.'],
        ['Detail callouts', 'Include detail number (e.g. "Detail 3/A-501") not just sheet number.'],
      ]],
      ['Compare revisions', 'Use revision history to see what changed between bulletins.', [
        ['Revision history', 'Open sheet history to see prior revisions.'],
        ['Side by side', 'Use compare tools when available to diff bulletins.'],
        ['Distribute changes', 'Highlight changes to subs affected by the revision.'],
        ['Submittal impact', 'Check if revision invalidates approved submittals — may need resubmit.'],
      ]],
      ['Download', 'Bulk download current set for subs or offline tablet use.', [
        ['Bulk download', 'Select current set and download ZIP for field tablets.'],
        ['Per discipline', 'Download only needed discipline to reduce file size on tablets.'],
        ['Offline', 'Field apps may cache downloaded sets — refresh after new bulletin.'],
        ['Sub distribution', 'Send current set link or download to subs after each bulletin.'],
      ]],
      ['Permissions', 'Restrict bid-set folders if drawings contain sensitive VE or pricing notes.', [
        ['Bid set folder', 'Restrict pre-award bid drawings to internal users only.'],
        ['Post-award', 'Release construction set to subs via portal or controlled download.'],
        ['VE sheets', 'Keep value-engineering alternates in internal-only folders.'],
        ['Owner access', 'Confirm contract on whether owner sees all disciplines in portal.'],
      ]],
      ['Turnover', 'Export final as-built set to <strong>Documents</strong> closeout folder at project end.', [
        ['Record drawings', 'Upload final record/as-built PDFs with conformed markup.'],
        ['Documents folder', 'Copy or move to <strong>Documents</strong> closeout / turnover folder.'],
        ['Owner deliverable', 'Match owner contract list for drawing deliverable format and naming.'],
        ['Archive', 'Keep one authoritative as-built set — avoid multiple conflicting finals.'],
      ]],
    ],
    'fa-drafting-compass'
  ),

  operations_center: singleGuide(
    'Operations Center',
    'All extended tools in one place — start with Quick Add, expand when you need more.',
    [
      ['Pick a tool', 'Use the left sidebar: Field, Communications, Financial Plus, Precon, Insights, or Client.', [
        ['Categories', 'Tools are grouped so you are not overwhelmed — open one category at a time.'],
        ['WIP Report', 'Financial Plus includes a live Work in Progress snapshot — no records to create.'],
      ]],
      ['Quick Add', 'Click <strong>Quick Add</strong> and fill only three fields. That is enough to save and track the item.', [
        ['Three fields', 'Each tool shows the minimum needed to get started (subject, date, amount, etc.).'],
        ['More options', 'Click <strong>More options</strong> in the dialog for numbers, notes, links, and custom data.'],
      ]],
      ['Workflow actions', 'Open any saved row to run actions like Promote to RFI, Validate vs SOV, or Generate AI insight.', [
        ['T&M → Change Event', 'Approved field tickets can promote to a change event.'],
        ['Correspondence → RFI', 'Formal letters can become RFIs with one click.'],
        ['Vendor invoices', 'Validate invoice amount against commitment SOV before approval.'],
      ]],
    ],
    'fa-layer-group'
  ),

  deliveries: singleGuide(
    'Deliveries',
    'Track material deliveries and receiving.',
    [
      ['Log delivery', 'Click <strong>New Delivery</strong>. Enter supplier, PO or commitment #, date, and location on site.', [
        ['New Delivery', 'Click <strong>New Delivery</strong> when material arrives on site.'],
        ['Supplier', 'Select supplier/vendor from <strong>Companies</strong> or type name.'],
        ['PO or commitment', 'Enter PO number or commitment # tying delivery to contract.'],
        ['Date & location', 'Record delivery date and where material was staged on site.'],
      ]],
      ['Line items', 'List materials, quantities, and ticket numbers from the delivery receipt.', [
        ['Add lines', 'Enter each material line: description, quantity, unit.'],
        ['Ticket number', 'Record delivery ticket or BOL number from the driver receipt.'],
        ['Match PO', 'Quantities should match PO — note shortages on the form.'],
        ['Unit of measure', 'Use same units as PO (LF, SF, EA, tons) for reconciliation.'],
      ]],
      ['Attach ticket', 'Photo or PDF of signed delivery ticket proves receipt for pay apps and disputes.', [
        ['Photo ticket', 'Photograph signed delivery ticket before driver leaves when possible.'],
        ['Upload PDF', 'Attach ticket image or scan to the delivery record.'],
        ['Signature', 'Ensure receiver signature is visible on the photo.'],
        ['Disputes', 'Tickets are evidence if supplier claims full delivery and you received short.'],
      ]],
      ['Inspect condition', 'Note damage or shortages — notify supplier and PM before acceptance.', [
        ['Visual inspect', 'Check for damage, wrong material, or short count before signing.'],
        ['Note on form', 'Record damage or shortage in delivery notes immediately.'],
        ['Notify PM', 'Alert PM and supplier same day for damaged or short shipments.'],
        ['Reject partial', 'Do not accept damaged goods without documenting on ticket.'],
      ]],
      ['Link schedule', 'Long-lead items should align with schedule activities — flag late deliveries early.', [
        ['Schedule activity', 'Reference schedule activity for long-lead items (elevator, switchgear).'],
        ['Late flag', 'If delivery is late vs schedule, notify scheduler to update dates.'],
        ['RFI/submittal', 'Late delivery may trace to late submittal approval — link root cause.'],
        ['Lookahead', 'Compare delivery log to 3-week lookahead in meetings.'],
      ]],
      ['Stored materials', 'Mark stored on site for pay application stored-material billing when allowed.', [
        ['Stored flag', 'Mark items stored on site not yet installed if contract allows billing.'],
        ['Location', 'Record storage location for owner inspection of stored materials.'],
        ['Pay app', 'Stored materials may appear on owner pay app — tie to delivery record.'],
        ['Insurance', 'Confirm stored materials are covered under builder\'s risk policy.'],
      ]],
      ['Search history', 'Filter by vendor or date to answer “when did steel arrive?” without digging through email.', [
        ['Vendor filter', 'Filter deliveries by supplier to see all shipments from one vendor.'],
        ['Date range', 'Filter by date to answer schedule or claim questions.'],
        ['PO search', 'Search by PO number to reconcile against commitment.'],
        ['Field questions', 'Supers can search instead of calling office for delivery dates.'],
      ]],
      ['Close', 'Mark received complete when all items on the PO are delivered and verified.', [
        ['PO complete', 'When final line item delivers, mark PO/delivery complete.'],
        ['Short close', 'If PO closes short, document reason (cancelled lines, partial order).'],
        ['Commitment', 'Complete status may update commitment received tracking.'],
        ['Archive ticket', 'Final ticket PDF stays on record for closeout and audit.'],
      ]],
    ],
    'fa-truck'
  ),

  meeting_minutes: singleGuide(
    'Meeting Minutes',
    'OAC, subcontractor, and internal meeting records.',
    [
      ['Create meeting', 'Click <strong>New Meeting</strong>. Set type (OAC, sub, safety), date, and attendees.', [
        ['New Meeting', 'Click <strong>New Meeting</strong> in the toolbar.'],
        ['Meeting type', 'Select OAC, subcontractor, safety, or internal per your template.'],
        ['Date & time', 'Set meeting date, start time, and location (conference room or jobsite trailer).'],
        ['Attendees', 'Add attendees from <strong>Project Directory</strong> or type names.'],
      ]],
      ['Agenda', 'Add agenda items before the meeting so participants come prepared.', [
        ['Agenda section', 'Add agenda items with topic and presenter before the meeting.'],
        ['Distribute early', 'Email agenda 24–48 hours ahead when contract requires.'],
        ['Time boxes', 'Optional: assign minutes per topic to keep meeting on schedule.'],
        ['Carry forward', 'Include standing items (safety, schedule, RFIs) each week.'],
      ]],
      ['Take notes', 'Record discussion, decisions, and action items with owner and due date.', [
        ['During meeting', 'Type notes live or assign a note-taker to capture discussion.'],
        ['Decisions', 'Clearly label decisions vs discussion — owners rely on decision log.'],
        ['Action items', 'Each action needs description, assignee, and due date.'],
        ['Number items', 'Number action items for easy reference at next meeting.'],
      ]],
      ['Action items', 'Each action needs assignee and due date — these feed follow-up at the next meeting.', [
        ['Assignee', 'Pick assignee from directory — Ball in Court may apply per workflow.'],
        ['Due date', 'Set realistic due date before next meeting.'],
        ['Open list', 'Filter open actions at start of next meeting.'],
        ['Close when done', 'Mark complete when verified — do not leave stale open items.'],
      ]],
      ['Attach docs', 'Link drawings, RFIs, or schedule snapshots referenced during discussion.', [
        ['Attach', 'Use attach action to link files from <strong>Documents</strong> or Drawings.'],
        ['RFI refs', 'Reference RFI numbers in notes and attach official responses.'],
        ['Schedule snapshot', 'Attach schedule PDF discussed in OAC.'],
        ['Avoid orphan refs', 'Link docs so readers can open without searching email.'],
      ]],
      ['Distribute', 'Email PDF minutes to attendees and file in <strong>Documents</strong>.', [
        ['Generate PDF', 'Export or email PDF minutes from meeting actions.'],
        ['Distribution list', 'Send to all attendees plus owner distribution if required.'],
        ['File copy', 'Save PDF in <strong>Documents</strong> under meeting minutes folder.'],
        ['Timeliness', 'Distribute within 24–48 hours while discussion is fresh.'],
      ]],
      ['Next meeting', 'Carry open actions forward automatically when copying the prior meeting.', [
        ['Copy meeting', 'Use copy from prior meeting to roll open actions forward.'],
        ['Review open', 'At next meeting start, review carried-forward actions first.'],
        ['Close or extend', 'Close completed actions or extend due dates with note.'],
        ['Standing agenda', 'Copy preserves standing agenda structure — edit topics as needed.'],
      ]],
      ['Search', 'Find past decisions by keyword — avoids re-debating settled issues.', [
        ['Search box', 'Search minutes by keyword (e.g. "elevator", "change order 4").'],
        ['Filter by type', 'Filter OAC vs sub meetings to narrow results.'],
        ['Decision log', 'Past decisions prevent re-litigating settled scope or schedule calls.'],
        ['Claims support', 'Minutes support delay claims — accurate notes matter.'],
      ]],
    ],
    'fa-handshake'
  ),

  email: singleGuide(
    'Email',
    'Project email — internal messages and external mail.',
    [
      ['Inbox views', 'Switch folders: Inbox, Sent, Drafts, and project-linked threads. Unread count shows in the nav badge.', [
        ['Folder sidebar', 'Click Inbox, Sent, or Drafts in the email folder list.'],
        ['Project threads', 'Filter or view project-linked threads for job-specific correspondence.'],
        ['Unread badge', 'Nav bell or email badge shows unread count — clear by reading or marking read.'],
        ['Refresh', 'Refresh inbox if expecting new mail — sync interval depends on server settings.'],
      ]],
      ['Compose', 'Click <strong>Compose</strong>. Pick recipients from directory or type emails. Set subject and body.', [
        ['Compose', 'Click <strong>Compose</strong> to open new message.'],
        ['Recipients', 'Pick from <strong>Project Directory</strong> or type email addresses.'],
        ['Subject', 'Use clear subject with project number and topic for searchability.'],
        ['Body', 'Write message — use professional tone on owner-facing threads.'],
      ]],
      ['Link to project', 'Associate messages with the active project so the team sees job context in the thread list.', [
        ['Project link', 'Select active project when composing so thread appears in project email list.'],
        ['Team visibility', 'Project-linked mail is visible to project team per permissions.'],
        ['Wrong project', 'Fix project association if mail filed under wrong job.'],
        ['Audit', 'Project link creates searchable record beyond personal Outlook.'],
      ]],
      ['Attachments', 'Attach files from disk or <strong>Documents</strong>. Watch size limits from program email settings.', [
        ['Attach file', 'Click attach and choose from disk or <strong>Documents</strong>.'],
        ['Size limit', 'Large files may bounce — check <strong>Program Settings → Email</strong> max size.'],
        ['Link instead', 'For huge files, link Document share URL instead of attaching.'],
        ['Virus scan', 'Some servers block certain extensions — zip or use Documents link.'],
      ]],
      ['Internal vs external', 'Some users are internal-only — external mail may be disabled per security policy.', [
        ['Policy check', 'Field staff may be blocked from external send — use PM for owner mail.'],
        ['Internal relay', 'Internal-only users can email team but not outside domains.'],
        ['Security', 'Configured under Program Settings email security.'],
        ['Official direction', 'Use RFIs/submittals for contract direction — not informal email alone.'],
      ]],
      ['Reply & forward', 'Use reply all carefully on owner threads; prefer linking RFIs for official direction.', [
        ['Reply vs reply all', 'Reply all on owner threads includes full distribution — be deliberate.'],
        ['Forward', 'Forward with context when handing off to another team member.'],
        ['RFI for direction', 'If answer affects scope, create RFI — email alone may not suffice contractually.'],
        ['Quote prior', 'Quote relevant prior thread when forwarding long chains.'],
      ]],
      ['Search', 'Search subject and body to find prior approvals or sub confirmations.', [
        ['Search box', 'Search subject and body keywords across project or global mail.'],
        ['Date filter', 'Narrow by date range for "when did sub confirm?" questions.'],
        ['Attachment names', 'Some search includes attachment filenames.'],
        ['Export', 'Important threads may be saved to <strong>Documents</strong> for permanent record.'],
      ]],
      ['Settings', 'SMTP, signatures, and relay rules live under <strong>Program Settings → Email</strong>.', [
        ['Program Settings', 'Admins configure SMTP relay and outbound rules.'],
        ['Signatures', 'Set company default signature with logo and disclaimer.'],
        ['Inbound', 'Configure inbound parsing if project email addresses receive external mail.'],
        ['Test send', 'Send test message after changing SMTP settings.'],
      ]],
    ],
    'fa-envelope'
  ),

  program_settings: singleGuide(
    'Program Settings',
    'Company-wide defaults — only admins should change these.',
    [
      ['Company tab', 'Legal name, logo, address, and license — appear on pay apps, PDFs, and owner correspondence.', [
        ['Company tab', 'Open <strong>Program Settings → Company</strong> (admin only).'],
        ['Legal name', 'Enter legal entity name exactly as on contracts and insurance.'],
        ['Logo', 'Upload logo for pay apps, RFIs, and PDF headers.'],
        ['License & address', 'Enter contractor license # and main office address for PDF footers.'],
      ]],
      ['Numbering', 'Prefixes and next numbers for RFIs, submittals, COs, and projects — set before go-live.', [
        ['Numbering tab', 'Open <strong>Program Settings → Numbering</strong>.'],
        ['Prefixes', 'Set prefixes (e.g. RFI-, SUB-) per document type.'],
        ['Next number', 'Set starting next number before team creates first records.'],
        ['Go-live', 'Wrong numbering is hard to fix after hundreds of RFIs exist — configure first.'],
      ]],
      ['Documents & pay apps', 'Folder templates, PDF branding, retainage defaults, and G702/G703 options.', [
        ['Documents tab', 'Configure default folder templates for new projects.'],
        ['Pay Apps tab', 'Set retainage defaults, G702/G703 templates, PDF branding.'],
        ['Branding', 'Logo and footer on owner-facing PDFs come from these settings.'],
        ['New projects', 'Changes apply to new projects — existing may need manual update.'],
      ]],
      ['Workflow', 'Approval chains, e-sign requirements, and module toggles that affect every project.', [
        ['Workflow tab', 'Configure approval chains for COs, pay apps, RFIs, etc.'],
        ['E-sign', 'Enable owner e-sign on change orders and pay apps when required.'],
        ['Module toggles', 'Enable/disable modules company-wide (estimating, safety, etc.).'],
        ['Test project', 'Test workflow on a sandbox project before production go-live.'],
      ]],
      ['Email & security', 'Mail relay, session timeout, password policy, and 2FA requirements.', [
        ['Email tab', 'SMTP relay, inbound rules, attachment limits.'],
        ['Security tab', 'Password complexity, session timeout, 2FA requirements.'],
        ['2FA', 'Require 2FA for admin and accounting roles handling sensitive data.'],
        ['Lockout', 'Configure failed login lockout threshold.'],
      ]],
      ['Integrations & Sage', 'ERP connection, company mapping, and cost code sync to Sage 300.', [
        ['Sage 300 tab', 'Enter connection credentials and company mapping.'],
        ['Cost codes', 'Map Case PM cost codes to Sage phase codes.'],
        ['Vendors', 'Map companies to Sage vendor IDs before ERP export.'],
        ['Test sync', 'Run test export on one small CO before bulk posting.'],
      ]],
      ['Backup', 'Schedule database backups and test restores periodically — not just enable and forget.', [
        ['Backup schedule', 'Configure automated backup schedule per IT policy.'],
        ['Offsite copy', 'Ensure backups copy offsite or to cloud — not only on app server.'],
        ['Test restore', 'Quarterly test restore to verify backups are usable.'],
        ['Document procedure', 'Document who restores and RTO/RPO for disaster recovery.'],
      ]],
      ['Change carefully', 'Document why you changed a setting; wrong numbering or workflow breaks active projects.', [
        ['Change log', 'Keep internal log of setting changes: who, when, why.'],
        ['Active projects', 'Numbering and workflow changes may affect in-flight RFIs and COs.'],
        ['Communicate', 'Tell PMs before changing approval chains mid-project.'],
        ['Rollback plan', 'Note prior values before changing so you can revert if needed.'],
      ]],
    ],
    'fa-sliders'
  ),

  notifications: singleGuide(
    'Notifications',
    'Alerts for approvals, mentions, and workflow events.',
    [
      ['Open inbox', 'Bell icon or Notifications page lists unread items newest first.', [
        ['Bell icon', 'Click the bell in the header to open the notification dropdown.'],
        ['Notifications page', 'Open full <strong>Notifications</strong> page for complete history.'],
        ['Newest first', 'Unread items appear at top — newest first.'],
        ['Badge count', 'Red badge shows unread count on bell icon.'],
      ]],
      ['Filter', 'Filter by type — approvals, RFIs, submittals, safety, or system messages.', [
        ['Type filter', 'Use filter chips or dropdown for Approvals, RFIs, Submittals, Safety, System.'],
        ['Focus work', 'Filter to Approvals when clearing your Ball in Court queue.'],
        ['Clear filter', 'Reset filter to see all notification types again.'],
        ['Unread only', 'Toggle unread-only to hide already-handled items.'],
      ]],
      ['Act from alert', 'Click a notification to jump to the record (RFI, CO, pay app) that needs action.', [
        ['Click through', 'Click notification row to open the linked RFI, CO, pay app, or other record.'],
        ['Context', 'Notification text summarizes what happened and what you need to do.'],
        ['Deep link', 'You land on the exact record — no manual search needed.'],
        ['Mobile', 'Same click-through works on mobile browser notifications.'],
      ]],
      ['Mark read', 'Clear items after handling so your inbox reflects real open work.', [
        ['Mark read', 'Click mark read on individual items or use mark all read.'],
        ['After action', 'Mark read after you submit, approve, or respond — keeps inbox accurate.'],
        ['Unread vs open', 'Unread notifications ≠ open workflow items — verify record status too.'],
        ['Inbox zero', 'Aim to clear daily notifications you are Ball in Court on.'],
      ]],
      ['Ball in Court', 'Many alerts mean you are Ball in Court — respond to move workflow forward.', [
        ['Ball alerts', 'Notifications often mean Ball in Court moved to you.'],
        ['Respond promptly', 'Submit approval, RFI response, or submittal review to move ball forward.'],
        ['Stalled workflow', 'If ball sits with you, whole job waits — check notifications daily.'],
        ['Delegate', 'Reassign record if you are wrong Ball in Court contact.'],
      ]],
      ['Email copies', 'Some events also email you — inbox here is the in-app audit of the same events.', [
        ['Dual channel', 'You may get email and in-app notification for same event.'],
        ['In-app audit', 'Notifications page is searchable history even if email was deleted.'],
        ['Email off', 'You can reduce email while keeping in-app alerts in preferences.'],
        ['Consistency', 'Prefer acting from in-app link — opens correct project context.'],
      ]],
      ['Preferences', 'Adjust which events notify you under <strong>Program Settings → Notifications</strong> or your profile.', [
        ['Profile settings', 'Open your avatar menu → notification preferences.'],
        ['By module', 'Toggle notifications for RFIs, submittals, COs, etc.'],
        ['Admin defaults', 'Admins set company defaults under <strong>Program Settings → Notifications</strong>.'],
        ['Do not over-disable', 'Disabling all alerts causes missed approvals — tune carefully.'],
      ]],
      ['Mobile', 'Enable browser or mobile notifications if your admin supports push for urgent approvals.', [
        ['Browser permission', 'Allow notifications when browser prompts on first visit.'],
        ['Push support', 'Depends on admin configuration and HTTPS.'],
        ['Urgent only', 'Use mobile push for approvals — not every minor update.'],
        ['Test', 'Send test notification from profile settings when available.'],
      ]],
    ],
    'fa-bell'
  ),

  app: singleGuide(
    'Case PM',
    'General tips for any page in the application.',
    [
      ['Active project', 'Most tools use the project selected in the header. Switch projects before creating records.', [
        ['Header picker', 'Click project name in header to switch active project.'],
        ['Before create', 'Always confirm project before clicking <strong>New</strong> — records attach to active project.'],
        ['Wrong project', 'If you created on wrong job, contact admin — moving records may not be supported.'],
        ['Dashboard follows', 'Dashboard tiles and counts reflect active project only.'],
      ]],
      ['Navigation', 'Use the left sidebar modules. Collapse the sidebar for more space — preference is saved.', [
        ['Sidebar', 'Click module names in left sidebar to navigate (RFIs, Budget, Schedule, etc.).'],
        ['Collapse', 'Click collapse icon to hide sidebar for more screen space.'],
        ['Preference saved', 'Collapsed state saves per user across sessions.'],
        ['Active highlight', 'Current module is highlighted in sidebar.'],
      ]],
      ['Search & filters', 'Lists usually support search, status filters, and column sort — click headers to sort.', [
        ['Search box', 'Type in list search to filter by title, number, or keyword.'],
        ['Status filter', 'Use status dropdown for Open, Closed, Draft, etc.'],
        ['Sort columns', 'Click column headers to sort ascending/descending.'],
        ['Combine', 'Search + filter together to find specific records fast.'],
      ]],
      ['Create records', 'Primary actions are green buttons top-right: <strong>New</strong>, <strong>Create</strong>, or <strong>+</strong>.', [
        ['Top-right', 'Look for green <strong>New</strong>, <strong>Create</strong>, or <strong>+</strong> button.'],
        ['Toolbar', 'Secondary actions (export, filter) sit near the primary create button.'],
        ['Draft first', 'Many forms save as Draft — you do not have to complete in one sitting.'],
        ['Required fields', 'Red asterisks or validation messages show required fields before save.'],
      ]],
      ['Save drafts', 'Many forms allow Draft until you Submit — save often before leaving the page.', [
        ['Save Draft', 'Click <strong>Save</strong> or <strong>Save Draft</strong> frequently while filling long forms.'],
        ['Submit later', 'Submit sends to workflow — draft keeps ball with you for edits.'],
        ['Navigate away', 'Save before switching modules — unsaved changes may be lost.'],
        ['Auto-save', 'Some forms auto-save — watch for save indicator if available.'],
      ]],
      ['Help', 'Click the <strong>?</strong> help button in the header when available for page-specific steps.', [
        ['Help button', 'Click <strong>?</strong> in the header on any page with help enabled.'],
        ['Page-specific', 'Help content matches the module you are on (RFIs, Change Orders, etc.).'],
        ['Expandable steps', 'Expand sub-steps for detailed click-by-click instructions.'],
        ['Return anytime', 'Reopen help while working — it does not close your form.'],
      ]],
      ['Profile & logout', 'Open your avatar menu for profile, password, and sign out.', [
        ['Avatar menu', 'Click your name or avatar in the top-right corner.'],
        ['Profile', 'Update name, email, phone, and notification preferences.'],
        ['Password', 'Change password or enroll 2FA from profile/security.'],
        ['Sign out', 'Click <strong>Sign out</strong> on shared computers when finished.'],
      ]],
      ['Get access', 'Missing modules? Ask an admin to adjust your role under <strong>Users</strong>.', [
        ['Missing sidebar item', 'If a module is absent from sidebar, your role lacks access.'],
        ['Ask admin', 'Request access from admin — they edit your user under <strong>Users</strong>.'],
        ['Role vs permission', 'Admin may adjust base role or fine-tune module permissions.'],
        ['Portal users', 'Subs get limited modules — full staff need internal role assignment.'],
      ]],
    ],
    'fa-compass'
  ),
};

})(window);
