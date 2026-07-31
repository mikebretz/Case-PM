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
