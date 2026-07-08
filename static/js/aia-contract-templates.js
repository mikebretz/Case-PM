/**
 * AIA-style contract templates — editable article structure per form.
 * Paste your licensed AIA document language into any section, or edit the starter text below.
 */
(function (global) {
  'use strict';

  const DISCLAIMER = 'Edit all contract language to match your licensed AIA documents and project requirements.';

  function section(id, title, body) {
    return { id, title, body, enabled: true, builtin: true };
  }

  const A401_SECTIONS = [
    section('a401-art1', 'ARTICLE 1  THE WORK', `§ 1.1  The Subcontract Work consists of the construction services, materials, equipment, and labor described in the Subcontract Documents and this Agreement, including the Scope of Work, Inclusions, and Exclusions identified in the Supplementary Scope Schedule attached hereto.

§ 1.2  The Subcontract Documents consist of this Agreement, the General Conditions of the Contract for Construction (AIA Document A201), Drawings, Specifications, addenda issued prior to execution, Change Orders, and other documents listed in the Contract Documents schedule. The Subcontract Documents are complementary. Anything required by one shall be as though required by all.

§ 1.3  The Work shall be performed in accordance with the Subcontract Documents, applicable laws, codes, ordinances, and the Prime Contract between Owner and Contractor to the extent applicable to the Subcontract Work.

§ 1.4  The Subcontractor shall coordinate the Subcontract Work with the Work of the Contractor and other subcontractors. The Subcontractor shall visit the site, verify conditions, and promptly notify the Contractor of discrepancies or conflicts.`),

    section('a401-art2', 'ARTICLE 2  TIME', `§ 2.1  The Subcontractor shall commence the Subcontract Work upon receipt of written notice to proceed and shall substantially complete the Subcontract Work within the Contract Time stated in this Agreement or as adjusted by Change Order.

§ 2.2  Substantial Completion of the Subcontract Work shall occur when the Subcontract Work is sufficiently complete in accordance with the Subcontract Documents so the Owner may occupy or utilize the Project or designated portion for its intended use.

§ 2.3  If the Subcontractor is delayed by acts or omissions of the Owner, Contractor, Architect, or other causes beyond the Subcontractor's control, an extension of the Contract Time shall be made by Change Order.

§ 2.4  Liquidated damages, if any, applicable to the Subcontract Work shall be as set forth in the Supplementary Conditions or Special Conditions.`),

    section('a401-art3', 'ARTICLE 3  SUBCONTRACT AMOUNT', `§ 3.1  The Contractor shall pay the Subcontractor the Subcontract Amount for performance of the Subcontract Work.

§ 3.2  The Subcontract Amount is the stipulated sum set forth on the face of this Agreement unless the Subcontract is a Cost of the Work plus fee arrangement as indicated.

§ 3.3  Allowances, if any, are identified in the Schedule of Values. Unused portions of allowances shall be credited to the Contractor unless otherwise agreed in writing.`),

    section('a401-art4', 'ARTICLE 4  PAYMENT', `§ 4.1  Progress Payments. Based on Applications for Payment submitted in accordance with the Subcontract Documents and the schedule of values, the Contractor shall make progress payments on account of the Subcontract Amount. Each Application for Payment shall be supported by data substantiating amounts requested.

§ 4.2  Retainage. The Contractor may retain the percentage of each progress payment stated in this Agreement until final payment unless reduced by written agreement or statute.

§ 4.3  Final Payment. Upon final completion of the Subcontract Work and submission of required closeout documents including warranties, as-built information, lien waivers, and final affidavit, the Contractor shall pay the unpaid balance of the Subcontract Amount less retainage and sums previously paid.

§ 4.4  Payment to the Subcontractor shall not constitute acceptance of nonconforming Work. The Subcontractor shall not be relieved of obligations to correct defective or nonconforming Work by payment.

§ 4.5  If payment is not made when due, the Subcontractor may suspend performance after providing written notice in accordance with applicable law.`),

    section('a401-art5', 'ARTICLE 5  INSURANCE', `§ 5.1  The Subcontractor shall purchase and maintain insurance coverages required by the Subcontract Documents and applicable law, including commercial general liability, automobile liability, workers compensation, and employer's liability.

§ 5.2  Commercial General Liability limits shall be not less than amounts stated in the Insurance Requirements. The Contractor, Owner, and Architect shall be named as additional insureds on a primary and noncontributory basis where required.

§ 5.3  The Subcontractor shall provide certificates of insurance and endorsements prior to commencing Work and upon renewal. Policies shall not be canceled or materially changed without thirty days' prior written notice to the Contractor.

§ 5.4  Insurance maintained by the Subcontractor shall be primary to any insurance maintained by the Contractor or Owner except where prohibited by law.`),

    section('a401-art6', 'ARTICLE 6  CHANGES IN THE WORK', `§ 6.1  The Subcontract Work may be changed by written Change Order, Construction Change Directive, or order for minor changes in the Work as provided in the Subcontract Documents.

§ 6.2  No adjustment in the Subcontract Amount or Contract Time shall be made for changes in the Work unless authorized by written Change Order or as otherwise provided.

§ 6.3  The Subcontractor shall not proceed with changed Work without written authorization except in an emergency affecting safety of persons or property.`),

    section('a401-art7', 'ARTICLE 7  NONCONFORMING WORK', `§ 7.1  The Subcontractor shall promptly correct Work rejected by the Contractor or Architect as failing to conform to the Subcontract Documents, whether before or after final payment.

§ 7.2  If the Subcontractor fails to correct nonconforming Work within a reasonable time, the Contractor may correct it and deduct costs from amounts due the Subcontractor.

§ 7.3  Acceptance of nonconforming Work shall not preclude later discovery and requirement of correction if within applicable limitation periods.`),

    section('a401-art8', 'ARTICLE 8  INDEMNIFICATION', `§ 8.1  To the fullest extent permitted by law, the Subcontractor shall indemnify and hold harmless the Contractor, Owner, Architect, and their agents and employees from claims, damages, losses, and expenses including attorneys' fees arising out of the Subcontract Work or performance of this Agreement, provided the claim is attributable to bodily injury, sickness, disease, death, or property damage caused by negligent acts or omissions of the Subcontractor, anyone directly or indirectly employed by the Subcontractor, or anyone for whose acts the Subcontractor may be liable.

§ 8.2  The Subcontractor's indemnification obligation shall not be limited by insurance requirements or proceeds.`),

    section('a401-art9', 'ARTICLE 9  TERMINATION', `§ 9.1  Termination for Cause. The Contractor may terminate this Agreement if the Subcontractor repeatedly refuses or fails to supply enough properly skilled workers or proper materials, fails to make payment to subcontractors or suppliers, disregards laws, or otherwise materially breaches this Agreement.

§ 9.2  Upon termination for cause, the Subcontractor shall stop the Subcontract Work and secure the site. The Contractor may take possession of materials, equipment, and tools on site necessary to complete the Work.

§ 9.3  Termination for Convenience. If the Prime Contract is terminated for the convenience of the Owner, this Agreement may be terminated to the same extent and the Subcontractor shall be paid for Work properly executed plus reasonable demobilization costs as agreed.

§ 9.4  Suspension. The Contractor may suspend the Subcontract Work by written notice. An adjustment in the Subcontract Amount and Contract Time shall be made if the suspension causes an increase in cost or time.`),

    section('a401-art10', 'ARTICLE 10  DISPUTE RESOLUTION', `§ 10.1  Claims arising out of or relating to this Agreement shall be resolved as provided in the Subcontract Documents, including initial decision by the Architect where applicable, mediation, and binding dispute resolution.

§ 10.2  Pending resolution of disputes, the Subcontractor shall continue performance and the Contractor shall continue payment of undisputed amounts.

§ 10.3  Continuation of Work and payment shall not prejudice rights to assert claims.`),

    section('a401-art11', 'ARTICLE 11  MISCELLANEOUS', `§ 11.1  Assignment. The Subcontractor shall not assign this Agreement without written consent of the Contractor. The Contractor may assign this Agreement to the Owner or successor entity.

§ 11.2  Notice. Written notice shall be delivered to addresses stated in this Agreement or as later designated in writing.

§ 11.3  Governing Law. This Agreement shall be governed by the law of the place of the Project.

§ 11.4  Entire Agreement. This Agreement represents the entire agreement between the parties and supersedes prior negotiations and representations.

§ 11.5  Severability. If any provision is invalid, the remainder shall remain in effect.

§ 11.6  Waiver. Failure to enforce any provision shall not constitute a waiver of subsequent breach.`),

    section('a401-art12', 'ARTICLE 12  SPECIAL CONDITIONS', `Enter any Special Conditions, supplementary requirements, or project-specific modifications to the standard articles here.

§ 12.1  
§ 12.2  
§ 12.3  `),
  ];

  const A101_SECTIONS = [
    section('a101-art1', 'ARTICLE 1  THE WORK', `§ 1.1  The Contractor shall fully execute and complete the Work described in the Contract Documents.

§ 1.2  The Contract Documents consist of this Agreement, Conditions of the Contract (General, Supplementary and other Conditions), Drawings, Specifications, addenda issued prior to execution, and Modifications. The Contract Documents are complementary.

§ 1.3  The Work shall comply with applicable laws, statutes, ordinances, codes, rules and regulations, and lawful orders of public authorities.`),

    section('a101-art2', 'ARTICLE 2  OWNER', `§ 2.1  The Owner is the person or entity identified as such in this Agreement and is the person or entity for whom the Work is to be performed.

§ 2.2  The Owner shall furnish information and approvals required by the Contract Documents within the time stated or promptly when no time is stated.`),

    section('a101-art3', 'ARTICLE 3  CONTRACTOR', `§ 3.1  The Contractor is the person or entity identified as such in this Agreement and is the person or entity who will perform the Work.

§ 3.2  The Contractor shall supervise and direct the Work using best skill and attention of a competent contractor.`),

    section('a101-art4', 'ARTICLE 4  ARCHITECT', `§ 4.1  The Architect is the person or entity identified in this Agreement and is the Owner's representative for the Project.

§ 4.2  The Architect will visit the site at intervals appropriate to the stage of construction to become generally familiar with progress and quality of the Work.`),

    section('a101-art5', 'ARTICLE 5  TIME', `§ 5.1  The Contractor shall commence the Work on the date established in this Agreement and shall substantially complete the entire Work within the Contract Time.

§ 5.2  Contract Time includes authorized adjustments by Change Order. The date of commencement and Contract Time are set forth in Article 8 or elsewhere in this Agreement.`),

    section('a101-art6', 'ARTICLE 6  PAYMENT', `§ 6.1  The Owner shall pay the Contractor the Contract Sum in current funds for performance of the Contract.

§ 6.2  Progress payments shall be made on account of the Contract Sum at intervals stated, based on Applications for Payment prepared by the Contractor.

§ 6.3  Retainage shall be as stated in this Agreement until final payment.

§ 6.4  Final payment constitutes a waiver of claims by the Contractor except those made in writing before final Application for Payment.`),

    section('a101-art7', 'ARTICLE 7  CHANGES IN THE WORK', `§ 7.1  Changes in the Work may be accomplished by Change Order, Construction Change Directive, or order for minor changes.

§ 7.2  No adjustment in Contract Sum or Contract Time for changes unless authorized as provided in the Contract Documents.`),

    section('a101-art8', 'ARTICLE 8  CONTRACT SUM', `§ 8.1  The Contract Sum is stated in this Agreement and, including authorized adjustments, is the total amount payable by the Owner to the Contractor for performance of the Contract.

§ 8.2  Alternates, allowances, and unit prices are identified in the Contract Documents.`),

    section('a101-art9', 'ARTICLE 9  TERMINATION OR SUSPENSION', `§ 9.1  The Contract may be terminated by either party as provided in the Contract Documents.

§ 9.2  The Work may be suspended by the Owner as provided in the General Conditions.`),

    section('a101-art10', 'ARTICLE 10  MISCELLANEOUS PROVISIONS', `§ 10.1  Notice shall be given as provided in the Contract Documents.

§ 10.2  This Agreement shall be governed by the law of the place of the Project.

§ 10.3  This Agreement, including the other Contract Documents, constitutes the entire agreement and supersedes prior representations.`),
  ];

  const A102_SECTIONS = [
    section('a102-art1', 'ARTICLE 1  THE WORK', `§ 1.1  The Contractor shall fully execute and complete the Work described in the Contract Documents on a cost-of-the-work basis as provided herein.

§ 1.2  The Contract Documents are complementary. The Work includes all labor, materials, equipment, and services necessary for completion.`),

    section('a102-art2', 'ARTICLE 2  COST OF THE WORK', `§ 2.1  Cost of the Work includes all costs necessarily incurred in the proper performance of the Work, including labor, materials, equipment rental, subcontracts, taxes, permits, and other items defined in the Contract Documents.

§ 2.2  Costs excluded from Cost of the Work are identified in the Contract Documents.

§ 2.3  The Contractor shall maintain complete and accurate records of costs and make them available to the Owner and Architect.`),

    section('a102-art3', 'ARTICLE 3  CONTRACTOR\'S FEE', `§ 3.1  The Contractor's Fee shall be calculated as stated in this Agreement.

§ 3.2  The Fee includes compensation for home office overhead, profit, and general conditions attributable to the Project unless separately identified.`),

    section('a102-art4', 'ARTICLE 4  PAYMENT', `§ 4.1  The Owner shall pay the Contractor the Cost of the Work plus the Contractor's Fee as the Work progresses.

§ 4.2  Applications for Payment shall be supported by payrolls, invoices, and other substantiating data.

§ 4.3  Retainage, if any, shall apply to Cost of the Work and Fee as stated.`),

    section('a102-art5', 'ARTICLE 5  TIME', `§ 5.1  Commencement and Contract Time are as stated in this Agreement.

§ 5.2  Extensions of time shall be made for delays as provided in the Contract Documents.`),

    section('a102-art6', 'ARTICLE 6  CHANGES IN THE WORK', `§ 6.1  Changes in the Work shall be authorized in writing. Adjustments to Cost of the Work, Fee, and Contract Time shall be made as provided.`),

    section('a102-art7', 'ARTICLE 7  MISCELLANEOUS', `§ 7.1  Audit rights, records retention, and governing law as stated in the Contract Documents.

§ 7.2  This Agreement constitutes the entire agreement between Owner and Contractor.`),
  ];

  const A201_SECTIONS = [
    section('a201-art1', 'ARTICLE 1  GENERAL PROVISIONS', `§ 1.1  Basic Definitions. Terms used in these General Conditions have meanings established in the Contract Documents.

§ 1.2  Execution, Correlation and Intent. The Contract Documents are complementary. The intent is to include all items necessary for proper execution and completion of the Work.

§ 1.3  Capitalization. Terms capitalized in these General Conditions have the meaning stated in the Agreement.`),

    section('a201-art2', 'ARTICLE 2  OWNER', `§ 2.1  General. The Owner furnishes information required under the Contract Documents.

§ 2.2  Evidence of Financial Arrangements. The Owner shall furnish reasonable evidence of financial arrangements upon request.`),

    section('a201-art3', 'ARTICLE 3  CONTRACTOR', `§ 3.1  General. The Contractor shall perform the Work in accordance with the Contract Documents.

§ 3.2  Supervision and Construction Procedures. The Contractor shall supervise and direct the Work.

§ 3.3  Subcontractual Relations. The Contractor may subcontract portions of the Work with consent of the Owner where required.`),

    section('a201-art4', 'ARTICLE 4  ARCHITECT', `§ 4.1  Administration of the Contract. The Architect will provide administration of the Contract as described herein.

§ 4.2  Visits to the Site. The Architect will visit the site at appropriate intervals.

§ 4.3  Interpretations and Decisions. The Architect will interpret the Contract Documents and decide matters relating to the Work.`),

    section('a201-art5', 'ARTICLE 5  SUBCONTRACTORS', `§ 5.1  The Contractor shall have the right to select and contract with subcontractors. Approved subcontractors are listed where required.

§ 5.2  Subcontractors shall be bound by terms of the Prime Contract applicable to their work.`),

    section('a201-art6', 'ARTICLE 6  CONSTRUCTION BY OWNER OR BY SEPARATE CONTRACTORS', `§ 6.1  The Owner reserves the right to perform construction or operations related to the Project with the Owner's own forces or separate contractors.`),

    section('a201-art7', 'ARTICLE 7  CHANGES IN THE WORK', `§ 7.1  Changes in the Work are effected by Change Order, Construction Change Directive, or order for minor changes.

§ 7.2  Adjustments in Contract Sum and Contract Time require written authorization.`),

    section('a201-art8', 'ARTICLE 8  TIME', `§ 8.1  Commencement and Contract Time are as stated in the Agreement.

§ 8.2  Delays and Extensions of Time are addressed as provided herein.`),

    section('a201-art9', 'ARTICLE 9  PAYMENTS AND COMPLETION', `§ 9.1  Contract Sum. The Contract Sum is the total amount payable for complete performance.

§ 9.2  Applications for Payment. The Contractor shall submit Applications for Payment at intervals stated.

§ 9.3  Retainage. Retainage shall be as stated in the Agreement.

§ 9.4  Final Completion and Final Payment. Upon final completion and submission of closeout documents, final payment shall be made.`),

    section('a201-art10', 'ARTICLE 10  PROTECTION OF PERSONS AND PROPERTY', `§ 10.1  The Contractor shall take reasonable precautions for safety of employees and the public.

§ 10.2  Hazardous materials and substances shall be handled in accordance with law.`),

    section('a201-art11', 'ARTICLE 11  INSURANCE AND BONDS', `§ 11.1  Coverages and limits shall be as stated in the Contract Documents.

§ 11.2  Certificates of insurance shall be furnished prior to commencement.`),

    section('a201-art12', 'ARTICLE 12  UNCOVERING AND CORRECTION OF WORK', `§ 12.1  Uncovering. Work covered contrary to the Architect's request shall be uncovered for observation if required.

§ 12.2  Correction. The Contractor shall correct Work not conforming to the Contract Documents.`),

    section('a201-art13', 'ARTICLE 13  MISCELLANEOUS PROVISIONS', `§ 13.1  Governing Law. Law of the place of the Project.

§ 13.2  Successors and Assigns. Binding on successors and permitted assigns.

§ 13.3  Written Notice. Notice shall be in writing and delivered as stated.`),

    section('a201-art14', 'ARTICLE 14  TERMINATION OR SUSPENSION OF THE CONTRACT', `§ 14.1  Termination by the Contractor for cause or for convenience as provided.

§ 14.2  Termination by the Owner for cause or for convenience as provided.

§ 14.3  Suspension by the Owner for convenience.`),

    section('a201-art15', 'ARTICLE 15  CLAIMS AND DISPUTES', `§ 15.1  Claims. Claims shall be initiated by written notice within time limits stated.

§ 15.2  Mediation and dispute resolution as provided in the Contract Documents.`),
  ];

  const A501_SECTIONS = [
    section('a501-art1', 'ARTICLE 1  SCOPE OF THE WORK', `§ 1.1  The Subcontractor agrees to furnish all labor, materials, equipment, and services necessary for the portion of the Work described in the Subcontract Documents.

§ 1.2  The Subcontract Documents include this Agreement, Drawings, Specifications, and Prime Contract provisions applicable to the Subcontract Work.`),

    section('a501-art2', 'ARTICLE 2  CONTRACT PRICE', `§ 2.1  The Contract Price is the amount stated in this Agreement subject to adjustments by Change Order.`),

    section('a501-art3', 'ARTICLE 3  PAYMENT', `§ 3.1  Progress payments monthly or as stated. Retainage as specified.

§ 3.2  Final payment upon completion, acceptance, and submission of lien waivers and closeout documents.`),

    section('a501-art4', 'ARTICLE 4  TIME', `§ 4.1  Subcontractor shall prosecute the Work continuously and complete within the Contract Time.`),

    section('a501-art5', 'ARTICLE 5  CHANGES', `§ 5.1  No changes without written Change Order unless emergency conditions require immediate action.`),

    section('a501-art6', 'ARTICLE 6  INSURANCE AND INDEMNITY', `§ 6.1  Insurance as required. Indemnification to the extent permitted by law.`),
  ];

  const A701_SECTIONS = [
    section('a701-inst1', 'INSTRUCTIONS TO BIDDERS', `§ 1  Bids shall be submitted on forms furnished and within the time stated.

§ 2  The Owner reserves the right to reject any or all bids and to waive informalities.

§ 3  Bid security, if required, shall accompany the bid.`),

    section('a701-inst2', 'BID DOCUMENTS', `§ 4  Bidders shall carefully examine the Contract Documents and visit the site.

§ 5  Failure to familiarize with conditions shall not relieve the successful bidder of obligations.`),

    section('a701-inst3', 'PERFORMANCE AND PAYMENT BONDS', `§ 6  Bonds shall be furnished if stated in the Advertisement or Invitation to Bid.

§ 7  Surety companies shall be acceptable to the Owner.`),
  ];

  const A312_SECTIONS = [
    section('a312-perf', 'PERFORMANCE BOND', `KNOW ALL MEN BY THESE PRESENTS, that we __________ as Principal (hereinafter called the "Contractor") and __________ as Surety (hereinafter called the "Surety"), are held and firmly bound unto __________ as Obligee (hereinafter called the "Owner") in the amount of __________ for the payment of which sum well and truly to be made in the type of medium of payment stated in the Contract, we bind ourselves, our heirs, executors, administrators, successors and assigns, jointly and severally, firmly by these presents.

WHEREAS the Contractor has entered into a written contract dated __________ with the Owner for __________.

NOW THEREFORE the conditions of this obligation are such that if the Contractor shall promptly and faithfully perform said Contract, then this obligation shall be void; otherwise it shall remain in full force and effect.`),

    section('a312-pay', 'PAYMENT BOND', `KNOW ALL MEN BY THESE PRESENTS, that we __________ as Principal and __________ as Surety, are held and firmly bound unto __________ as Obligee in the amount of __________.

The conditions of this obligation are such that if the Principal shall promptly make payment to all claimants for labor, materials, and equipment furnished for the Work, then this obligation shall be void; otherwise it shall remain in full force and effect.`),
  ];

  const PO_SECTIONS = [
    section('po-1', 'PURCHASE ORDER TERMS', `1. ACCEPTANCE. This Purchase Order is accepted by Vendor upon commencement of performance or written acknowledgment.

2. PRICE AND PAYMENT. Prices are firm unless otherwise stated. Payment terms are net as indicated on the face of this order.

3. DELIVERY. Time is of the essence. Vendor shall deliver goods to the location and date specified. Risk of loss passes upon delivery and acceptance.

4. WARRANTY. Vendor warrants goods shall be new, of good quality, free from defects, and conform to specifications.

5. INSPECTION. Buyer may inspect and reject nonconforming goods. Vendor shall replace or credit rejected goods promptly.

6. CHANGES. Changes require written Change Order signed by Buyer.

7. COMPLIANCE. Vendor shall comply with applicable laws including safety, environmental, and labor requirements.`),
  ];

  const DEFAULT_INCLUSIONS = `Include all labor, materials, equipment, supervision, layout, coordination, hoisting, cutting, fitting, fastening, cleanup, protection of work in place, permits and fees applicable to the Subcontract Work, and all incidental items required for a complete installation whether or not specifically listed.`;

  const DEFAULT_EXCLUSIONS = `Excluded unless specifically noted in the Inclusions or Scope: engineering or design services, hazmat abatement, work by others, temporary utilities supplied by Contractor, bonds and permits paid by Contractor, overtime premium unless directed in writing, and restoration of work damaged by others.`;

  const DEFAULT_SCOPE = `The Subcontractor shall furnish and install all Work described in the Contract Documents for this trade/scope, complete and ready for use, in strict accordance with Drawings, Specifications, applicable codes, and manufacturer's instructions.`;

  const TEMPLATES = {
    A401: {
      form: 'A401',
      title: 'AIA A401 — Agreement Between Contractor and Subcontractor',
      inclusions: DEFAULT_INCLUSIONS,
      exclusions: DEFAULT_EXCLUSIONS,
      scope_supplement: DEFAULT_SCOPE,
      sections: A401_SECTIONS,
    },
    A101: {
      form: 'A101',
      title: 'AIA A101 — Agreement Between Owner and Contractor (Stipulated Sum)',
      inclusions: DEFAULT_INCLUSIONS,
      exclusions: DEFAULT_EXCLUSIONS,
      scope_supplement: DEFAULT_SCOPE,
      sections: A101_SECTIONS,
    },
    A102: {
      form: 'A102',
      title: 'AIA A102 — Agreement Between Owner and Contractor (Cost of the Work)',
      inclusions: DEFAULT_INCLUSIONS,
      exclusions: DEFAULT_EXCLUSIONS,
      scope_supplement: DEFAULT_SCOPE,
      sections: A102_SECTIONS,
    },
    A201: {
      form: 'A201',
      title: 'AIA A201 — General Conditions of the Contract for Construction',
      inclusions: '',
      exclusions: '',
      scope_supplement: '',
      sections: A201_SECTIONS,
    },
    A501: {
      form: 'A501',
      title: 'AIA A501 — Agreement Between Contractor and Subcontractor (Legacy)',
      inclusions: DEFAULT_INCLUSIONS,
      exclusions: DEFAULT_EXCLUSIONS,
      scope_supplement: DEFAULT_SCOPE,
      sections: A501_SECTIONS,
    },
    A701: {
      form: 'A701',
      title: 'AIA A701 — Instructions to Bidders',
      inclusions: '',
      exclusions: '',
      scope_supplement: '',
      sections: A701_SECTIONS,
    },
    A312: {
      form: 'A312',
      title: 'AIA A312 — Performance and Payment Bonds',
      inclusions: '',
      exclusions: '',
      scope_supplement: '',
      sections: A312_SECTIONS,
    },
    'N/A': {
      form: 'N/A',
      title: 'Purchase Order / Supply Agreement',
      inclusions: 'All items listed on this order and applicable specifications.',
      exclusions: 'Items not specifically listed unless required for complete delivery.',
      scope_supplement: DEFAULT_SCOPE,
      sections: PO_SECTIONS,
    },
    Other: {
      form: 'Other',
      title: 'Custom Agreement',
      inclusions: DEFAULT_INCLUSIONS,
      exclusions: DEFAULT_EXCLUSIONS,
      scope_supplement: DEFAULT_SCOPE,
      sections: [section('custom-1', 'ARTICLE 1  AGREEMENT', 'Enter contract language here.')],
    },
  };

  function resolveFormKey(aiaForm, commitmentType) {
    if (aiaForm && TEMPLATES[aiaForm]) return aiaForm;
    if (commitmentType === 'Subcontract') return 'A401';
    if (commitmentType === 'Purchase Order') return 'N/A';
    return 'Other';
  }

  function cloneTemplate(formKey) {
    const t = TEMPLATES[formKey] || TEMPLATES.Other;
    return {
      form: t.form,
      title: t.title,
      disclaimer: DISCLAIMER,
      inclusions: t.inclusions,
      exclusions: t.exclusions,
      scope_supplement: t.scope_supplement,
      sections: t.sections.map(s => ({ ...s })),
    };
  }

  function mergeContract(saved, formKey) {
    const base = cloneTemplate(formKey);
    if (!saved || typeof saved !== 'object') return base;
    const merged = {
      ...base,
      ...saved,
      sections: [],
    };
    const savedSections = Array.isArray(saved.sections) ? saved.sections : [];
    const savedById = Object.fromEntries(savedSections.map(s => [s.id, s]));
    base.sections.forEach(s => {
      merged.sections.push(savedById[s.id] ? { ...s, ...savedById[s.id] } : { ...s });
    });
    savedSections.filter(s => !s.builtin).forEach(s => merged.sections.push({ ...s }));
    return merged;
  }

  function listForms() {
    return Object.keys(TEMPLATES);
  }

  global.CasePMAiaTemplates = {
    DISCLAIMER,
    TEMPLATES,
    resolveFormKey,
    cloneTemplate,
    mergeContract,
    listForms,
  };
})(window);
