"""Checked-in Sage 300 Web API schema profile packs (wave 33)."""
from __future__ import annotations

SAGE_PROFILE_PACKS = {
    'sage300_web_api_default': {
        'label': 'Sage 300 Web API (generic)',
        'edition': 'core',
        'resources': {
            'ar_receipts': 'ARReceiptBatches',
            'ar_invoices': 'ARInvoices',
            'ap_invoices': 'APInvoices',
            'ap_payments': 'APPaymentBatches',
            'bk_transactions': 'BKTransactions',
        },
        'fields': {
            'invoice_number': ['InvoiceNumber', 'DocumentNumber'],
            'customer_number': ['CustomerNumber', 'CustomerCode'],
            'vendor_number': ['VendorNumber', 'VendorCode'],
            'amount_paid': ['AmountPaid', 'PaidAmount'],
            'receipt_number': ['ReceiptNumber', 'BatchNumber'],
        },
    },
    'sage300_cre_2024': {
        'label': 'Sage 300 CRE + financials (2024)',
        'edition': 'cre',
        'resources': {
            'ar_receipts': 'ARReceiptBatches',
            'ar_invoices': 'ARInvoices',
            'ap_invoices': 'APInvoices',
            'ap_payments': 'APPaymentBatches',
            'bk_transactions': 'BKTransactions',
        },
        'fields': {
            'invoice_number': ['InvoiceNumber', 'DocumentNumber', 'InvoiceNo'],
            'customer_number': ['CustomerNumber', 'CustNo'],
            'vendor_number': ['VendorNumber', 'VendNo'],
            'amount_paid': ['AmountPaid', 'PaidToDate'],
            'receipt_number': ['ReceiptNumber', 'BatchNumber', 'ReceiptNo'],
        },
        'optional_fields': {
            'vendor': ['OptionalField1', 'VendorUDF1'],
            'customer': ['OptionalField1', 'CustomerUDF1'],
            'job': ['JobOptional1', 'ProjectUDF'],
        },
    },
    'sage300_distribution': {
        'label': 'Sage 300 distribution (IC/OE/PO)',
        'edition': 'distribution',
        'resources': {
            'ic_items': 'ICItems',
            'oe_orders': 'OEOrders',
            'po_receipts': 'POReceipts',
            'ar_invoices': 'ARInvoices',
            'ap_invoices': 'APInvoices',
        },
        'fields': {
            'invoice_number': ['InvoiceNumber'],
            'item_number': ['ItemNumber', 'ItemNo'],
            'order_number': ['OrderNumber'],
        },
    },
}


def list_profile_packs() -> list[dict]:
    return [{'id': k, 'label': v.get('label'), 'edition': v.get('edition')} for k, v in SAGE_PROFILE_PACKS.items()]


def get_pack(pack_id: str) -> dict:
    return dict(SAGE_PROFILE_PACKS.get(pack_id) or SAGE_PROFILE_PACKS['sage300_web_api_default'])


SAGE_REPORT_PACKS = {
    'month_end_core': {
        'label': 'Month-end core (TB, aging, WIP)',
        'reports': [
            {'report_type': 'trial_balance', 'frequency': 'monthly'},
            {'report_type': 'ap_aging', 'frequency': 'monthly'},
            {'report_type': 'ar_aging', 'frequency': 'monthly'},
            {'report_type': 'job_wip', 'frequency': 'monthly'},
        ],
    },
    'sage_mirror_ops': {
        'label': 'Sage mirror ops (drift, inbox)',
        'reports': [
            {'report_type': 'sage_drift_summary', 'frequency': 'weekly'},
            {'report_type': 'sage_exception_inbox', 'frequency': 'weekly'},
        ],
    },
}


def list_report_packs() -> list[dict]:
    return [{'id': k, 'label': v.get('label'), 'report_count': len(v.get('reports') or [])} for k, v in SAGE_REPORT_PACKS.items()]


def get_report_pack(pack_id: str) -> dict:
    return dict(SAGE_REPORT_PACKS.get(pack_id) or SAGE_REPORT_PACKS['month_end_core'])
