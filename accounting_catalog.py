"""
Case PM built-in accounting suite — module catalog (feature parity target: enterprise ERP).

Each module is implemented natively in Case PM. External Sage 300 sync is optional
and configured under Program Settings → Integrations, not required to operate.
"""
from __future__ import annotations

PLATFORM_CAPABILITIES = [
    {'id': 'multi_company', 'name': 'Multi-company / multi-entity', 'status': 'live'},
    {'id': 'multi_currency', 'name': 'Multi-currency & revaluation', 'status': 'live'},
    {'id': 'multi_language', 'name': 'Multi-language UI', 'status': 'live'},
    {'id': 'multi_location', 'name': 'Multi-location', 'status': 'live'},
    {'id': 'security', 'name': 'Role-based security & G/L account security', 'status': 'live'},
    {'id': 'fiscal_calendar', 'name': 'Fiscal periods & year-end close', 'status': 'live'},
    {'id': 'optional_fields', 'name': 'Optional / custom fields', 'status': 'live'},
    {'id': 'audit', 'name': 'Audit trail & activity log', 'status': 'live'},
    {'id': 'import_export', 'name': 'Import / export & data integrity', 'status': 'live'},
    {'id': 'reporting', 'name': 'Financial reporting & dashboards', 'status': 'live'},
]

# status: live = usable in Accounting UI today; beta = partial; planned = catalogued roadmap
ACCOUNTING_MODULES = [
    {
        'id': 'gl',
        'code': 'GL',
        'name': 'General Ledger',
        'status': 'live',
        'route': 'gl',
        'summary': 'Chart of accounts, journal entries, allocations, consolidation-ready posting.',
        'features': [
            'Flexible chart of accounts (up to 10 segments)',
            'Manual, recurring, and allocation journals',
            'Budget approval workflow and budget vs actual',
            'Trial balance, account inquiry, subledger tie-out with adjustment posting',
            'Intercompany entries and recurring schedule run-due',
        ],
    },
    {
        'id': 'ap',
        'code': 'AP',
        'name': 'Accounts Payable',
        'status': 'live',
        'route': 'ap',
        'summary': 'Vendors, invoices, payments, retainage, 1099 tracking.',
        'features': [
            'Vendor master and groups',
            'Invoice entry, retainage, and withholding',
            'Recurring payables',
            'Payment void and 1099 reporting',
            '3-way PO matching with line grid workbench',
            'Aging and vendor activity',
            '1099 FIRE export and printable forms',
            'Recurring payables run-due',
        ],
    },
    {
        'id': 'ar',
        'code': 'AR',
        'name': 'Accounts Receivable',
        'status': 'live',
        'route': 'ar',
        'summary': 'Customers, invoicing, cash application, credit limits, dunning.',
        'features': [
            'Customer groups and ship-to locations',
            'Invoices, credit/debit memos, statements',
            'Cash application and receipt batches',
            'Recurring billing and dunning rules',
            'Credit hold enforcement',
            'Cash application workbench (multi-invoice apply)',
            'Credit review queue and hold enforcement',
            'Recurring billing run-due',
        ],
    },
    {
        'id': 'bk',
        'code': 'BK',
        'name': 'Bank Services',
        'status': 'live',
        'route': 'bank',
        'summary': 'Bank accounts, transactions, reconciliation.',
        'features': [
            'Centralized receipts and payments',
            'Statement reconciliation',
            'NSF and reversals',
            'Distribution codes',
            'OFX bank feed import',
        ],
    },
    {
        'id': 'tx',
        'code': 'TX',
        'name': 'Tax Services',
        'status': 'live',
        'route': 'tax',
        'summary': 'Tax authorities, groups, and document tax calculation.',
        'features': [
            'Tax tables and rate maintenance',
            'Sales / use / withholding groups',
            'Tax calculator and vendor assignment',
            'GST/VAT/sales tax on AP/AR',
            'Stacked tax components',
            'Filing prep summaries',
        ],
    },
    {
        'id': 'fa',
        'code': 'FA',
        'name': 'Fixed Assets',
        'status': 'live',
        'route': 'assets',
        'summary': 'Asset lifecycle, depreciation books, and disposal.',
        'features': [
            'Acquisition & disposal with G/L posting',
            'Straight-line depreciation runs',
            'Net book value and location tracking',
            'Multiple depreciation books',
            'DDB / SYD methods',
        ],
    },
    {
        'id': 'ic',
        'code': 'IC',
        'name': 'Inventory Control',
        'status': 'live',
        'route': 'inventory',
        'summary': 'Perpetual inventory, locations, serial/lot tracking.',
        'features': ['Item master', 'Receipts & issues', 'Transfers', 'Costing', 'Lot/serial tracking'],
    },
    {
        'id': 'oe',
        'code': 'OE',
        'name': 'Order Entry / Sales',
        'status': 'live',
        'route': 'oe',
        'summary': 'Quotes, orders, shipments, invoicing.',
        'features': ['Sales orders', 'Quotes & returns', 'Commissions & accrual', 'IC & AR integration'],
    },
    {
        'id': 'po',
        'code': 'PO',
        'name': 'Purchase Orders',
        'status': 'live',
        'route': 'po',
        'summary': 'Requisitions through PO, receipts, vendor invoice matching.',
        'features': ['Blanket & standing POs', 'Blanket releases', 'Receipts', 'Drop-ship flag', 'AP & IC integration'],
    },
    {
        'id': 'jc',
        'code': 'JC',
        'name': 'Project & Job Costing',
        'status': 'live',
        'route': 'jobcost',
        'summary': 'Job cost tied to Case PM projects, budget, and commitments.',
        'features': [
            'Job / phase / category structure',
            'Committed vs actual costs',
            'Revenue recognition schedule API',
            'Integration with Budget & Pay Apps',
        ],
    },
    {
        'id': 'cost_codes',
        'code': 'CC',
        'name': 'Cost Code Library',
        'status': 'live',
        'route': 'cost-codes',
        'summary': 'Project cost codes and types — used by budget, pay apps, commitments, and change orders.',
        'features': [
            'Custom cost code lists and CSI master selection',
            'Cost types (labor, material, subcontract, etc.)',
            'Merged picker from budget lines + library',
            'Same catalog Sage / Procore job cost codes feed',
        ],
    },
    {
        'id': 'construction_sync',
        'code': 'CS',
        'name': 'Construction sync',
        'status': 'live',
        'route': 'construction-sync',
        'summary': 'Pending G702, sub AP, commitments, COs; Sage cutover and parity matrix.',
        'features': [
            'Pending construction dashboard',
            'One-click sync all pending',
            'Sage go-live alerts and cutover checklist',
            'Sage parity matrix (read/write/conflict)',
        ],
    },
    {
        'id': 'pr',
        'code': 'PR',
        'name': 'Payroll',
        'status': 'live',
        'route': 'payroll',
        'summary': 'Employee master, pay runs, withholding, deductions, and job-cost labor posting.',
        'features': [
            'Employee master (hourly & salary)',
            'Federal/state/FICA/Medicare withholding',
            'Deduction codes & enrollments',
            'Pay run build, calculate, post to G/L',
            'Job cost labor by project on journal lines',
            'Payroll register & EFT CSV export',
        ],
    },
    {
        'id': 'pp',
        'code': 'PP',
        'name': 'Payment Processing',
        'status': 'live',
        'route': 'payments',
        'summary': 'Card processing and invoice pay links.',
        'features': [
            'AP payment batches (check, ACH, wire)',
            'Batch post to G/L and bank register',
            'MICR check export (CSV)',
            'Pay Now links for open AR invoices',
            'Processor and MICR company settings',
        ],
    },
    {
        'id': 'bi',
        'code': 'BI',
        'name': 'Reporting & Analytics',
        'status': 'live',
        'route': 'reports',
        'summary': 'Trial balance, aging, job cost, and custom saved reports.',
        'features': [
            'Trial balance, P&L, balance sheet',
            'A/P and A/R aging',
            'Journal register and job cost',
            'Construction bridge audit',
            'Custom saved reports with CSV export',
            'KPI dashboards',
            'Report designer JSON layouts',
        ],
    },
    {
        'id': 'consolidation',
        'code': 'CON',
        'name': 'G/L Consolidation',
        'status': 'live',
        'route': 'consolidation',
        'summary': 'Multi-entity roll-up reporting.',
        'features': [
            'Subsidiary ledger tree',
            'Consolidated trial balance and P&amp;L / balance sheet',
            'Ownership %, FX translation, and rollup journal',
            'Consolidation runs with period end',
            'Auto-suggested and manual elimination entries',
            'Entity period lock across subsidiaries',
        ],
    },
    {
        'id': 'admin',
        'code': 'ADM',
        'name': 'Platform & Admin',
        'status': 'live',
        'route': 'admin',
        'summary': 'Fiscal calendar, locations, security, audit, import/export.',
        'features': [
            'Fiscal period generate and close',
            'Multi-location master',
            'G/L account security matrix',
            'Optional field definitions',
            'Audit log and integrity checks',
            'Chart of accounts CSV import/export',
        ],
    },
]


def catalog_for_api():
    return {
        'product': 'Case PM Accounting',
        'standalone': True,
        'external_sync': {
            'available': True,
            'systems': ['Sage 300 (optional)'],
            'configure_at': 'Program Settings → Sage 300 / Integrations',
        },
        'platform': PLATFORM_CAPABILITIES,
        'modules': ACCOUNTING_MODULES,
    }


def module_by_route(route: str):
    for m in ACCOUNTING_MODULES:
        if m.get('route') == route or m.get('id') == route:
            return m
    return None
