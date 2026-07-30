"""
Sage 300 ERP feature catalog for Case PM Accounting module.

Maps official Sage 300 modules and capabilities to Web API modules (where available),
Case PM integration status, and construction-ERP bridge events.
"""
from __future__ import annotations

# integration: none | planned | bridge | web_api | hybrid | isv
# edition: core | distribution | cre | addon | platform

SAGE300_PLATFORM_FEATURES = [
    {'id': 'multi_company', 'name': 'Multi-company / multi-entity', 'description': 'Multiple companies; close books and consolidated reporting.'},
    {'id': 'multi_currency', 'name': 'Multi-currency', 'description': 'Unlimited currencies, exchange rates, revaluation, functional-currency reporting.'},
    {'id': 'multi_language', 'name': 'Multi-language UI', 'description': 'English, French, Spanish, Chinese, and regional overlays.'},
    {'id': 'multi_location', 'name': 'Multi-location', 'description': 'Location-specific inventory, sales, and GL dimensions.'},
    {'id': 'security', 'name': 'Security groups & G/L account security', 'description': 'User authorizations, permissions, account-level security.'},
    {'id': 'system_manager', 'name': 'System Manager / Administration', 'description': 'Company profile, fiscal calendar, optional fields, integrity checks, import/export.'},
    {'id': 'audit_trace', 'name': 'Audit logging & trace', 'description': 'Key actions logged by user and timestamp.'},
    {'id': 'web_screens', 'name': 'Web screens', 'description': 'Browser access alongside classic desktop (version-dependent).'},
    {'id': 'financial_reporter', 'name': 'Financial Reporter / report writer', 'description': 'Built-in statements, Crystal Reports, Sage Intelligence, dashboards.'},
    {'id': 'integrations', 'name': 'Integration points', 'description': 'Outlook, Project, payment processors, EDI, e-commerce, WMS.'},
    {'id': 'cloud', 'name': 'Cloud deployment', 'description': 'Partner Cloud, Azure, hosted instances, mobile add-ons.'},
    {'id': 'compliance', 'name': 'Compliance', 'description': 'GAAP, IFRS, GDPR auditing, regional tax reporting.'},
]

SAGE300_MODULES = [
    {
        'id': 'gl',
        'code': 'GL',
        'name': 'General Ledger',
        'edition': 'core',
        'summary': 'Chart of accounts, journals, budgets, consolidation, intercompany.',
        'features': [
            'Flexible chart of accounts (up to 10 segments)',
            'Multicurrency accounting and revaluation',
            'Multiple budget sets; fiscal history',
            'Manual, recurring, allocation, and subledger journals',
            'G/L consolidation and intercompany transactions',
            'Trial balance, account history, financial statements',
        ],
        'web_api': {'module': 'GL', 'resources': ['GLAccounts', 'GLJournalBatches', 'GLJournalEntries']},
        'integration': 'hybrid',
        'casepm': {
            'bridge_module': 'JobCost',
            'events': ['BudgetSageSync', 'AccountingReconciled', 'ManualSync'],
            'ui': ['accounting', 'budget', 'forecast'],
        },
    },
    {
        'id': 'ap',
        'code': 'AP',
        'name': 'Accounts Payable',
        'edition': 'core',
        'summary': 'Vendors, invoices, payments, 1099/T5018, retainage.',
        'features': [
            'Vendor setup and groups; rapid invoice entry',
            'Recurring payables; 3-way PO matching',
            'Payment processing and cash disbursement',
            'Withholding and reverse charges',
            'Aging, activity, and vendor reports',
            'Bank Services integration for EFT',
        ],
        'web_api': {'module': 'AP', 'resources': ['APVendors', 'APInvoices', 'APPaymentBatches']},
        'integration': 'hybrid',
        'casepm': {
            'bridge_module': 'AP',
            'events': [
                'CommitmentSubmitted', 'CommitmentApproved', 'CommitmentUpdated',
                'CommitmentVoided', 'SubPayAppApproved', 'CommitmentChangeOrderApproved',
            ],
            'ui': ['accounting', 'commitments', 'pay_applications'],
        },
    },
    {
        'id': 'ar',
        'code': 'AR',
        'name': 'Accounts Receivable',
        'edition': 'core',
        'summary': 'Customers, invoicing, cash application, credit limits, dunning.',
        'features': [
            'Customer groups, national accounts, ship-to locations',
            'Summary and detailed invoicing; credit/debit notes',
            'Statements, cash application, aging',
            'Credit limits and recurring charges',
            'Order Entry and payment processing integration',
        ],
        'web_api': {'module': 'AR', 'resources': ['ARCustomers', 'ARInvoices', 'ARReceiptBatches']},
        'integration': 'hybrid',
        'casepm': {
            'bridge_module': 'ProgressBilling',
            'events': ['G702Submitted', 'G702Approved'],
            'ui': ['accounting', 'pay_applications'],
        },
    },
    {
        'id': 'bk',
        'code': 'BK',
        'name': 'Bank Services',
        'edition': 'core',
        'summary': 'Centralized receipts/payments, reconciliation, distribution codes.',
        'features': [
            'Bank setup and transaction tracking',
            'Statement reconciliation (manual and automated feeds)',
            'Reverse payments and NSF handling',
            'Create GL batches from bank activity',
            'Credit card types and distribution sets',
        ],
        'web_api': {'module': 'BK', 'resources': ['BKAccounts', 'BKTransactions']},
        'integration': 'web_api',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['accounting']},
    },
    {
        'id': 'tx',
        'code': 'TX',
        'name': 'Tax Services',
        'edition': 'core',
        'summary': 'Centralized tax tables and calculation across modules.',
        'features': [
            'Sales and purchase tax rules',
            'GST/VAT and regional modules',
            'Withholding support',
            'Audit information for tax filings',
        ],
        'web_api': {'module': 'TX', 'resources': ['TXAuthorities', 'TXGroups']},
        'integration': 'web_api',
        'casepm': {
            'bridge_module': 'General',
            'events': [],
            'ui': ['accounting', 'program_settings'],
            'settings': ['sage_default_tax_group'],
        },
    },
    {
        'id': 'fa',
        'code': 'FA',
        'name': 'Fixed Assets',
        'edition': 'addon',
        'summary': 'Asset lifecycle, multiple depreciation books, compliance.',
        'features': [
            'Asset acquisition, transfer, disposal',
            'GAAP and tax books; splits and revaluations',
            'Depreciation schedules and compliance tracking',
        ],
        'web_api': {'module': 'FA', 'resources': ['FAAssets']},
        'integration': 'planned',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['accounting']},
    },
    {
        'id': 'ic',
        'code': 'IC',
        'name': 'Inventory Control',
        'edition': 'distribution',
        'summary': 'Perpetual inventory, multi-location, serial/lot tracking.',
        'features': [
            'Item segments, pricing, kitting, reorder quantities',
            'Receipts, shipments, transfers, adjustments',
            'Serialized and lot tracking',
            'Real-time quantities and costs; GL integration',
            'Optional bin/warehouse extensions (ISV)',
        ],
        'web_api': {'module': 'IC', 'resources': ['ICItems', 'ICLocations', 'ICTransactions']},
        'integration': 'web_api',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['accounting', 'deliveries']},
    },
    {
        'id': 'oe',
        'code': 'OE',
        'name': 'Order Entry / Sales Orders',
        'edition': 'distribution',
        'summary': 'Quotes through invoice; commissions; IC and AR integration.',
        'features': [
            'Quotes, orders, shipments, invoices, returns',
            'Credit checks; picking slips and shipping labels',
            'Sales commissions and miscellaneous charges',
            'Project & Job Costing labor/service hooks',
        ],
        'web_api': {'module': 'OE', 'resources': ['OEOrders', 'OEInvoices', 'OEShipments']},
        'integration': 'web_api',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['accounting']},
    },
    {
        'id': 'po',
        'code': 'PO',
        'name': 'Purchase Orders',
        'edition': 'distribution',
        'summary': 'Requisitions through vendor invoice; drop-ship; IC/AP updates.',
        'features': [
            'Standing, blanket, and future POs',
            'Receipts, returns, vendor invoices',
            'Vendor contract costs; drop-ship',
            'Automatic IC and AP updates',
        ],
        'web_api': {'module': 'PO', 'resources': ['POPurchaseOrders', 'POReceipts', 'POInvoices']},
        'integration': 'hybrid',
        'casepm': {
            'bridge_module': 'AP',
            'events': ['CommitmentSubmitted', 'CommitmentApproved'],
            'ui': ['accounting', 'commitments'],
        },
    },
    {
        'id': 'pj',
        'code': 'PJ',
        'name': 'Project and Job Costing',
        'edition': 'cre',
        'summary': 'Contracts, phases, estimates, committed/actual costs, revenue recognition.',
        'features': [
            'Jobs, projects, phases, and categories',
            'Labor, materials, equipment, subcontract estimates',
            'Committed vs actual; time and expenses',
            'Revenue recognition methods',
            'Microsoft Project integration',
        ],
        'web_api': {'module': 'PJ', 'resources': ['PJJobs', 'PJContracts', 'PJTransactions']},
        'integration': 'bridge',
        'casepm': {
            'bridge_module': 'JobCost',
            'events': [
                'BudgetSaved', 'BudgetPublished', 'BudgetSageSync',
                'ChangeOrderApproved', 'PCOPromoted', 'TimesheetPosted',
                'DirectCostPosted', 'AccountingReconciled',
            ],
            'ui': ['accounting', 'budget', 'forecast', 'change_orders'],
        },
    },
    {
        'id': 'cre_pb',
        'code': 'CRE',
        'name': 'Sage 300 CRE — Progress Billing',
        'edition': 'cre',
        'summary': 'Construction owner billings (AIA / progress billing).',
        'features': ['G702/G703 style billings', 'Retainage', 'AR integration'],
        'web_api': None,
        'integration': 'bridge',
        'casepm': {
            'bridge_module': 'ProgressBilling',
            'events': ['G702Submitted', 'G702Approved'],
            'ui': ['pay_applications', 'accounting'],
        },
    },
    {
        'id': 'cre_sub',
        'code': 'CRE',
        'name': 'Sage 300 CRE — Subcontractor Billing',
        'edition': 'cre',
        'summary': 'Subcontractor payment applications and compliance.',
        'features': ['Sub pay apps', 'Compliance tracking', 'AP integration'],
        'web_api': None,
        'integration': 'bridge',
        'casepm': {
            'bridge_module': 'SubcontractorBilling',
            'events': ['SubPayAppSubmitted', 'SubPayAppApproved'],
            'ui': ['pay_applications', 'accounting'],
        },
    },
    {
        'id': 'cre_pco',
        'code': 'CRE',
        'name': 'Sage 300 CRE — PCO / Change Orders',
        'edition': 'cre',
        'summary': 'Potential change orders and contract changes.',
        'features': ['PCO workflow', 'COR promotion', 'Budget sync'],
        'web_api': None,
        'integration': 'bridge',
        'casepm': {
            'bridge_module': 'PCO',
            'events': [
                'PCOSubmitted', 'PCOPromoted', 'ChangeOrderSubmitted', 'ChangeOrderApproved',
                'CORSubmitted', 'CORApproved', 'ChangeEventCreated',
                'CPCOSubmitted', 'CPCOPromoted',
            ],
            'ui': ['change_orders', 'accounting'],
        },
    },
    {
        'id': 'pr',
        'code': 'PR',
        'name': 'Payroll (US / Canada)',
        'edition': 'addon',
        'summary': 'Region-specific payroll and EFT direct deposit.',
        'features': ['Pay runs', 'Tax filings', 'EFT payroll', 'HR document add-ons'],
        'web_api': {'module': 'PR', 'resources': ['PREmployees', 'PRPayRuns']},
        'integration': 'planned',
        'casepm': {
            'bridge_module': 'JobCost',
            'events': ['TimesheetPosted'],
            'ui': ['accounting', 'user_management'],
            'settings': ['sage_employee_code', 'sage_resource_id'],
        },
    },
    {
        'id': 'pp',
        'code': 'PP',
        'name': 'Payment Processing',
        'edition': 'addon',
        'summary': 'Card processing, Pay Now links, MICR check printing.',
        'features': ['Paya, Stripe, PayPal integrations', 'Invoice payment links', 'Bank feed partners'],
        'web_api': None,
        'integration': 'isv',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['accounting', 'pay_applications']},
    },
    {
        'id': 'bi',
        'code': 'BI',
        'name': 'Reporting & Analytics',
        'edition': 'platform',
        'summary': 'Standard reports, Financial Reporter, Sage Intelligence, third-party BI.',
        'features': [
            'Journals, aging, history, fiscal comparisons',
            'Custom financial statements and KPI dashboards',
            'Import/export for external analysis',
            'True Sky / idu planning (partner)',
        ],
        'web_api': None,
        'integration': 'planned',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['accounting', 'forecast', 'dashboard']},
    },
    {
        'id': 'crm',
        'code': 'CRM',
        'name': 'Sage CRM',
        'edition': 'isv',
        'summary': 'Sales, marketing, and service automation.',
        'features': ['Interactions', 'Pipeline', 'Marketing campaigns'],
        'web_api': None,
        'integration': 'isv',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['companies']},
    },
    {
        'id': 'optional',
        'code': 'CS',
        'name': 'Optional Fields & Transaction Analysis',
        'edition': 'platform',
        'summary': 'User-defined fields and operational inquiry.',
        'features': ['Optional fields across modules', 'Sales analysis', 'Ops inquiry', 'Code-change utilities'],
        'web_api': None,
        'integration': 'web_api',
        'casepm': {'bridge_module': None, 'events': [], 'ui': ['accounting', 'program_settings']},
    },
    {
        'id': 'rma',
        'code': 'RMA',
        'name': 'Return Material Authorization',
        'edition': 'isv',
        'summary': 'RMA workflow (often partner add-on).',
        'features': ['Returns authorization', 'Warranty tracking'],
        'web_api': None,
        'integration': 'isv',
        'casepm': {'bridge_module': None, 'events': [], 'ui': []},
    },
    {
        'id': 'edi',
        'code': 'EDI',
        'name': 'EDI & e-Commerce',
        'edition': 'isv',
        'summary': 'Trading partner and web store integrations.',
        'features': ['850/810 EDI', 'Shopping cart connectors'],
        'web_api': None,
        'integration': 'isv',
        'casepm': {'bridge_module': None, 'events': [], 'ui': []},
    },
    {
        'id': 'mfg',
        'code': 'MFG',
        'name': 'Manufacturing / Advanced Warehouse',
        'edition': 'isv',
        'summary': 'BOM, MRP, directed picking (Marketplace ISVs).',
        'features': ['Bill of materials', 'Bin tracking', 'Directed picking'],
        'web_api': {'module': 'BM', 'resources': ['BMBills']},
        'integration': 'isv',
        'casepm': {'bridge_module': None, 'events': [], 'ui': []},
    },
]

# Quick inquiry presets for Accounting → Sage Web API browser
SAGE300_INQUIRY_PRESETS = [
    {'label': 'G/L Accounts', 'module': 'GL', 'resource': 'GLAccounts'},
    {'label': 'G/L Journal Batches', 'module': 'GL', 'resource': 'GLJournalBatches'},
    {'label': 'A/P Vendors', 'module': 'AP', 'resource': 'APVendors'},
    {'label': 'A/P Invoices', 'module': 'AP', 'resource': 'APInvoices'},
    {'label': 'A/R Customers', 'module': 'AR', 'resource': 'ARCustomers'},
    {'label': 'A/R Invoices', 'module': 'AR', 'resource': 'ARInvoices'},
    {'label': 'Bank Accounts', 'module': 'BK', 'resource': 'BKAccounts'},
    {'label': 'Inventory Items', 'module': 'IC', 'resource': 'ICItems'},
    {'label': 'Sales Orders', 'module': 'OE', 'resource': 'OEOrders'},
    {'label': 'Purchase Orders', 'module': 'PO', 'resource': 'POPurchaseOrders'},
    {'label': 'Project Jobs', 'module': 'PJ', 'resource': 'PJJobs'},
]


def catalog_payload():
    return {
        'platform': SAGE300_PLATFORM_FEATURES,
        'modules': SAGE300_MODULES,
        'inquiry_presets': SAGE300_INQUIRY_PRESETS,
        'notes': [
            'Case PM uses SAGE_API_URL for Sage 300 CRE construction bridge (outbound transactions, inbound job ledger).',
            'Sage 300 Web API (OData) uses program Sage API URL or SAGE300_WEB_API_URL for master data and distribution modules.',
            'Licensed modules and endpoint availability depend on your Sage 300 edition and version — verify in Sage300WebApi Swagger.',
        ],
    }


def modules_by_integration(integration: str):
    return [m for m in SAGE300_MODULES if m.get('integration') == integration]


def casepm_linked_modules():
    """Modules with active Case PM bridge or hybrid integration."""
    out = []
    for m in SAGE300_MODULES:
        casepm = m.get('casepm') or {}
        if casepm.get('events') or casepm.get('bridge_module'):
            out.append(m)
    return out
