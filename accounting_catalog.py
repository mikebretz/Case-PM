"""
Case PM built-in accounting suite — module catalog (feature parity target: enterprise ERP).

Each module is implemented natively in Case PM. External Sage 300 sync is optional
and configured under Program Settings → Integrations, not required to operate.
"""
from __future__ import annotations

PLATFORM_CAPABILITIES = [
    {'id': 'multi_company', 'name': 'Multi-company / multi-entity', 'status': 'live'},
    {'id': 'multi_currency', 'name': 'Multi-currency & revaluation', 'status': 'beta'},
    {'id': 'multi_language', 'name': 'Multi-language UI', 'status': 'planned'},
    {'id': 'multi_location', 'name': 'Multi-location', 'status': 'beta'},
    {'id': 'security', 'name': 'Role-based security & G/L account security', 'status': 'live'},
    {'id': 'fiscal_calendar', 'name': 'Fiscal periods & year-end close', 'status': 'beta'},
    {'id': 'optional_fields', 'name': 'Optional / custom fields', 'status': 'beta'},
    {'id': 'audit', 'name': 'Audit trail & activity log', 'status': 'live'},
    {'id': 'import_export', 'name': 'Import / export & data integrity', 'status': 'beta'},
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
            'Flexible chart of accounts (multi-segment)',
            'Manual, recurring, and allocation journals',
            'Budget sets and account history',
            'Trial balance and account inquiry',
            'Financial statement mapping',
            'Intercompany entries (beta)',
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
            'Invoice entry and recurring payables',
            'Payment processing and cash disbursement',
            '3-way PO matching (beta)',
            'Aging and vendor activity',
            'Withholding / reverse charges (beta)',
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
            'Customer and ship-to locations',
            'Invoices, credit/debit notes, statements',
            'Cash application and aging',
            'Recurring billing',
            'Credit limits',
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
        ],
    },
    {
        'id': 'tx',
        'code': 'TX',
        'name': 'Tax Services',
        'status': 'beta',
        'route': 'tax',
        'summary': 'Tax authorities, groups, and document tax calculation.',
        'features': ['Tax tables', 'GST/VAT/sales tax', 'Withholding', 'Filing prep (planned)'],
    },
    {
        'id': 'fa',
        'code': 'FA',
        'name': 'Fixed Assets',
        'status': 'beta',
        'route': 'assets',
        'summary': 'Asset lifecycle and depreciation books.',
        'features': ['Acquisition & disposal', 'Multiple books', 'Depreciation schedules', 'Revaluation (planned)'],
    },
    {
        'id': 'ic',
        'code': 'IC',
        'name': 'Inventory Control',
        'status': 'beta',
        'route': 'inventory',
        'summary': 'Perpetual inventory, locations, serial/lot (roadmap).',
        'features': ['Item master', 'Receipts & issues', 'Transfers', 'Costing', 'Lot/serial (planned)'],
    },
    {
        'id': 'oe',
        'code': 'OE',
        'name': 'Order Entry / Sales',
        'status': 'beta',
        'route': 'oe',
        'summary': 'Quotes, orders, shipments, invoicing.',
        'features': ['Sales orders', 'Shipments', 'Commissions (planned)', 'IC & AR integration'],
    },
    {
        'id': 'po',
        'code': 'PO',
        'name': 'Purchase Orders',
        'status': 'beta',
        'route': 'po',
        'summary': 'Requisitions through PO, receipts, vendor invoice matching.',
        'features': ['Blanket & standing POs', 'Receipts', 'Drop-ship (planned)', 'AP & IC integration'],
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
            'Revenue recognition methods (beta)',
            'Integration with Budget & Pay Apps',
        ],
    },
    {
        'id': 'pr',
        'code': 'PR',
        'name': 'Payroll',
        'status': 'beta',
        'route': 'payroll',
        'summary': 'Pay runs, taxes, direct deposit (roadmap).',
        'features': ['US/Canada payroll', 'EFT', 'Job cost labor posting'],
    },
    {
        'id': 'pp',
        'code': 'PP',
        'name': 'Payment Processing',
        'status': 'planned',
        'route': 'payments',
        'summary': 'Card processing and invoice pay links.',
        'features': ['Card processors', 'Pay Now links', 'MICR checks'],
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
            'KPI dashboards (beta)',
        ],
    },
    {
        'id': 'consolidation',
        'code': 'CON',
        'name': 'G/L Consolidation',
        'status': 'planned',
        'route': 'consolidation',
        'summary': 'Multi-entity roll-up reporting.',
        'features': ['Elimination entries', 'Consolidated statements'],
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
