"""A/P depth — vendor groups, recurring payables, 1099, 3-way match, void payment, withholding."""
from __future__ import annotations

import json
from datetime import date, datetime

from accounting_operations import _parse_lines


def serialize_vendor_group(g):
    return {'id': g.id, 'code': g.code, 'name': g.name, 'terms': g.terms, 'status': g.status}


def serialize_vendor_extended(v):
    from accounting_persistence import serialize_vendor
    base = serialize_vendor(v)
    base.update({
        'vendor_group_id': v.vendor_group_id,
        'tax_id': v.tax_id or '',
        'is_1099': bool(v.is_1099),
        'form_1099_type': v.form_1099_type or 'NEC',
        'default_withhold_percent': float(v.default_withhold_percent or 0),
    })
    return base


def patch_vendor_extended(v, body):
    if body.get('vendor_group_id') is not None:
        v.vendor_group_id = int(body['vendor_group_id']) if body['vendor_group_id'] else None
    if 'tax_id' in body:
        v.tax_id = str(body['tax_id'])[:30]
    if 'is_1099' in body:
        v.is_1099 = bool(body['is_1099'])
    if body.get('form_1099_type'):
        v.form_1099_type = str(body['form_1099_type'])[:10]
    if 'default_withhold_percent' in body:
        v.default_withhold_percent = max(0.0, float(body['default_withhold_percent'] or 0))
    return v


def compute_ap_invoice_amounts(gross, *, retainage_percent=0, withhold_percent=0):
    gross = round(float(gross or 0), 2)
    retainage = round(gross * float(retainage_percent or 0) / 100.0, 2)
    net_before_wh = round(gross - retainage, 2)
    withhold = round(net_before_wh * float(withhold_percent or 0) / 100.0, 2)
    payable = round(net_before_wh - withhold, 2)
    return {
        'gross_amount': gross,
        'retainage_amount': retainage,
        'withhold_amount': withhold,
        'amount': payable,
    }


def serialize_recurring_ap(r):
    return {
        'id': r.id,
        'vendor_id': r.vendor_id,
        'description': r.description,
        'amount': r.amount,
        'frequency': r.frequency,
        'next_run_date': r.next_run_date.isoformat() if r.next_run_date else None,
        'is_active': r.is_active,
        'document_number_prefix': r.document_number_prefix,
    }


def generate_recurring_ap_invoice(db, models, recurring):
    if not recurring.is_active:
        raise ValueError('Recurring payable inactive')
    AcctAPDocument = models['AcctAPDocument']
    n = AcctAPDocument.query.filter_by(ledger_id=recurring.ledger_id).count()
    doc = AcctAPDocument(
        ledger_id=recurring.ledger_id,
        vendor_id=recurring.vendor_id,
        document_number=f'{recurring.document_number_prefix}-{datetime.utcnow().strftime("%Y%m%d")}-{n + 1}',
        document_type='Invoice',
        document_date=recurring.next_run_date or date.today(),
        due_date=recurring.next_run_date or date.today(),
        amount=recurring.amount,
        gross_amount=recurring.amount,
        status='Open',
    )
    db.session.add(doc)
    recurring.last_run_date = doc.document_date
    if recurring.frequency == 'weekly':
        recurring.next_run_date = (recurring.next_run_date or date.today()).replace(day=min(28, (recurring.next_run_date or date.today()).day))
        from datetime import timedelta
        recurring.next_run_date = (recurring.next_run_date or date.today()) + timedelta(days=7)
    else:
        d = recurring.next_run_date or date.today()
        recurring.next_run_date = date(d.year + (1 if d.month == 12 else 0), (d.month % 12) + 1, min(d.day, 28))
    db.session.flush()
    return doc


def three_way_match(db, models, ledger_id, invoice_id):
    """Match AP invoice to PO receipts (qty/amount tolerance)."""
    AcctAPDocument = models['AcctAPDocument']
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    doc = AcctAPDocument.query.filter_by(id=int(invoice_id), ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Invoice not found')
    po = None
    if doc.purchase_order_id:
        po = AcctPurchaseOrder.query.get(doc.purchase_order_id)
    elif doc.po_reference:
        po = AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id, po_number=doc.po_reference).first()
    if not po:
        return {
            'matched': False,
            'status': 'no_po',
            'message': 'No purchase order linked',
            'invoice_id': doc.id,
        }
    po_lines = _parse_lines(po.lines_json)
    po_total = float(po.total_amount or 0)
    inv_amt = float(doc.gross_amount or doc.amount or 0)
    qty_ok = True
    for pl in po_lines:
        ordered = float(pl.get('qty') or pl.get('quantity') or 0)
        received = float(pl.get('qty_received') or 0)
        if ordered > 0 and received < ordered * 0.99:
            qty_ok = False
    amount_ok = po_total <= 0 or abs(inv_amt - po_total) <= max(1.0, po_total * 0.05)
    matched = qty_ok and amount_ok
    return {
        'matched': matched,
        'status': 'matched' if matched else 'exception',
        'invoice_id': doc.id,
        'purchase_order_id': po.id,
        'po_number': po.po_number,
        'po_total': po_total,
        'invoice_amount': inv_amt,
        'qty_received_ok': qty_ok,
        'amount_within_tolerance': amount_ok,
        'lines': po_lines,
    }


def report_1099(db, models, ledger_id, tax_year):
    AcctVendor = models['AcctVendor']
    AcctAPPayment = models['AcctAPPayment']
    year = int(tax_year)
    vendors = AcctVendor.query.filter_by(ledger_id=ledger_id, is_1099=True).all()
    rows = []
    for v in vendors:
        payments = AcctAPPayment.query.filter_by(ledger_id=ledger_id, vendor_id=v.id, status='Posted').all()
        total = 0.0
        for p in payments:
            if p.payment_date and p.payment_date.year == year:
                total += float(p.amount or 0)
        if total >= 600 or total > 0:
            rows.append({
                'vendor_id': v.id,
                'vendor_code': v.code,
                'vendor_name': v.name,
                'tax_id': v.tax_id or '',
                'form_type': v.form_1099_type or 'NEC',
                'payments': round(total, 2),
            })
    return {'tax_year': year, 'vendors': rows}


def void_ap_payment(db, models, payment, reason='', user_id=None):
    if payment.status == 'Void':
        raise ValueError('Payment already voided')
    from accounting_posting import load_accounting_options, _account_by_number
    from accounting_persistence import next_batch_number, post_journal_batch
    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctAPPaymentApply = models['AcctAPPaymentApply']
    AcctAPDocument = models['AcctAPDocument']
    AcctLedger = models['AcctLedger']
    ledger = AcctLedger.query.get(payment.ledger_id)
    amt = float(payment.amount or 0)
    applies = AcctAPPaymentApply.query.filter_by(payment_id=payment.id).all()
    for app in applies:
        doc = AcctAPDocument.query.get(app.ap_document_id)
        if doc:
            doc.amount_paid = round(max(0, float(doc.amount_paid or 0) - float(app.amount or 0)), 2)
            if doc.amount_paid <= 0.01:
                doc.status = 'Open'
            else:
                doc.status = 'Partial'
    ap_acct = _account_by_number(AcctGLAccount, payment.ledger_id, opts['ap_account'])
    cash_acct = _account_by_number(AcctGLAccount, payment.ledger_id, opts['cash_account'])
    batch = AcctJournalBatch(
        ledger_id=payment.ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, payment.ledger_id),
        source='AP-VOID',
        description=f'Void payment {payment.payment_number}'[:300],
        batch_date=date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=1, account_id=cash_acct.id,
        description='Payment void', debit=amt, credit=0,
    ))
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=2, account_id=ap_acct.id,
        description='Payment void', debit=0, credit=amt,
    ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger)
    payment.status = 'Void'
    payment.void_reason = (reason or '')[:200]
    payment.voided_at = datetime.utcnow()
    db.session.flush()
    return {'payment_id': payment.id, 'reversal_batch_id': batch.id}
