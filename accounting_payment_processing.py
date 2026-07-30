"""Payment Processing — AP batches, checks, pay-now links."""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta

from accounting_posting import create_ap_payment, create_ar_receipt


def serialize_payment_batch(b, lines=None):
    return {
        'id': b.id,
        'batch_number': b.batch_number,
        'status': b.status,
        'payment_date': b.payment_date.isoformat() if b.payment_date else None,
        'payment_method': b.payment_method,
        'bank_account_id': b.bank_account_id,
        'check_number_start': b.check_number_start,
        'total_amount': float(b.total_amount or 0),
        'notes': b.notes or '',
        'posted_at': b.posted_at.isoformat() if b.posted_at else None,
        'lines': lines or [],
    }


def serialize_pay_now_link(link):
    return {
        'id': link.id,
        'token': link.token,
        'ar_document_id': link.ar_document_id,
        'customer_id': link.customer_id,
        'amount': float(link.amount or 0),
        'status': link.status,
        'payment_method': link.payment_method,
        'expires_at': link.expires_at.isoformat() if link.expires_at else None,
        'paid_at': link.paid_at.isoformat() if link.paid_at else None,
        'ar_receipt_id': link.ar_receipt_id,
    }


def next_payment_batch_number(AcctPaymentBatch, ledger_id):
    n = AcctPaymentBatch.query.filter_by(ledger_id=ledger_id).count()
    return f'PP-{datetime.utcnow().strftime("%Y%m")}-{n + 1:04d}'


def create_payment_batch(db, models, ledger_id, body, user_id=None):
    AcctPaymentBatch = models['AcctPaymentBatch']
    AcctPaymentBatchLine = models['AcctPaymentBatchLine']
    batch = AcctPaymentBatch(
        ledger_id=ledger_id,
        batch_number=body.get('batch_number') or next_payment_batch_number(AcctPaymentBatch, ledger_id),
        payment_date=date.fromisoformat(body['payment_date']) if body.get('payment_date') else date.today(),
        payment_method=(body.get('payment_method') or 'Check')[:20],
        bank_account_id=body.get('bank_account_id'),
        check_number_start=(body.get('check_number_start') or '')[:20] or None,
        notes=body.get('notes') or '',
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    total = 0.0
    for ln in body.get('lines') or []:
        amt = round(float(ln.get('amount') or 0), 2)
        if amt <= 0:
            continue
        db.session.add(AcctPaymentBatchLine(
            batch_id=batch.id,
            vendor_id=int(ln['vendor_id']),
            ap_document_id=int(ln['ap_document_id']) if ln.get('ap_document_id') else None,
            amount=amt,
            reference=(ln.get('reference') or '')[:80],
        ))
        total += amt
    batch.total_amount = round(total, 2)
    db.session.flush()
    return batch


def batch_lines(AcctPaymentBatchLine, batch_id):
    return AcctPaymentBatchLine.query.filter_by(batch_id=batch_id).all()


def post_payment_batch(db, models, batch, user_id=None):
    if batch.status != 'Open':
        raise ValueError('Batch is not open')
    AcctPaymentBatchLine = models['AcctPaymentBatchLine']
    lines = batch_lines(AcctPaymentBatchLine, batch.id)
    if not lines:
        raise ValueError('Batch has no lines')

    check_num = None
    if batch.check_number_start and batch.payment_method == 'Check':
        try:
            check_num = int(batch.check_number_start)
        except ValueError:
            check_num = None

    by_vendor = {}
    for ln in lines:
        by_vendor.setdefault(ln.vendor_id, []).append(ln)

    payment_ids = []
    for vendor_id, vlines in by_vendor.items():
        apps = []
        total = 0.0
        for ln in vlines:
            if ln.ap_document_id:
                apps.append({'ap_document_id': ln.ap_document_id, 'amount': ln.amount})
            total += float(ln.amount or 0)
        total = round(total, 2)
        chk = str(check_num) if check_num is not None else None
        if check_num is not None:
            check_num += 1
            for ln in vlines:
                ln.check_number = chk
        out = create_ap_payment(
            db, models,
            vendor_id=vendor_id,
            amount=total,
            applications=apps,
            payment_method=batch.payment_method,
            bank_account_id=batch.bank_account_id,
            user_id=user_id,
            payment_batch_id=batch.id,
            check_number=chk,
            payment_date=batch.payment_date,
        )
        payment_ids.append(out['payment'].id)

    batch.status = 'Posted'
    batch.posted_at = datetime.utcnow()
    db.session.flush()
    return {'payment_ids': payment_ids, 'batch_id': batch.id}


def create_pay_now_link(db, models, ledger_id, ar_document_id, *, days_valid=30, payment_method='card'):
    AcctPayNowLink = models['AcctPayNowLink']
    AcctARDocument = models['AcctARDocument']
    doc = AcctARDocument.query.filter_by(id=int(ar_document_id), ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('AR invoice not found')
    open_amt = round(float(doc.amount or 0) - float(doc.amount_paid or 0), 2)
    if open_amt <= 0:
        raise ValueError('Invoice has no open balance')
    token = secrets.token_urlsafe(32)
    link = AcctPayNowLink(
        ledger_id=ledger_id,
        token=token,
        ar_document_id=doc.id,
        customer_id=doc.customer_id,
        amount=open_amt,
        status='Pending',
        payment_method=payment_method[:20],
        expires_at=datetime.utcnow() + timedelta(days=max(1, int(days_valid))),
    )
    db.session.add(link)
    db.session.flush()
    return link


def complete_pay_now_link(db, models, token, *, bank_account_id=None, user_id=None):
    AcctPayNowLink = models['AcctPayNowLink']
    link = AcctPayNowLink.query.filter_by(token=token).first()
    if not link:
        raise ValueError('Pay link not found')
    if link.status != 'Pending':
        raise ValueError(f'Link status is {link.status}')
    if link.expires_at and link.expires_at < datetime.utcnow():
        link.status = 'Expired'
        raise ValueError('Pay link expired')
    out = create_ar_receipt(
        db, models,
        customer_id=link.customer_id,
        amount=link.amount,
        applications=[{'ar_document_id': link.ar_document_id, 'amount': link.amount}],
        payment_method='Card' if link.payment_method == 'card' else 'ACH',
        bank_account_id=bank_account_id,
        user_id=user_id,
    )
    link.status = 'Paid'
    link.paid_at = datetime.utcnow()
    link.ar_receipt_id = out['receipt'].id
    db.session.flush()
    return {'link': link, 'receipt_id': out['receipt'].id, 'journal_batch_id': out.get('journal_batch_id')}


def payment_processor_settings(ledger):
    try:
        settings = json.loads(ledger.settings_json or '{}') if ledger.settings_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        settings = {}
    pp = settings.get('payment_processing') or {}
    return {
        'processor': pp.get('processor') or 'none',
        'enable_pay_now': pp.get('enable_pay_now', True),
        'default_pay_now_days': int(pp.get('default_pay_now_days') or 30),
        'micr_company_name': pp.get('micr_company_name') or ledger.name,
        'micr_bank_routing': pp.get('micr_bank_routing') or '',
        'micr_bank_account': pp.get('micr_bank_account') or '',
    }


def update_payment_processor_settings(ledger, body):
    try:
        settings = json.loads(ledger.settings_json or '{}') if ledger.settings_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        settings = {}
    pp = settings.get('payment_processing') or {}
    for key in ('processor', 'micr_company_name', 'micr_bank_routing', 'micr_bank_account'):
        if key in body:
            pp[key] = str(body[key])[:120]
    if 'enable_pay_now' in body:
        pp['enable_pay_now'] = bool(body['enable_pay_now'])
    if 'default_pay_now_days' in body:
        pp['default_pay_now_days'] = max(1, int(body['default_pay_now_days']))
    settings['payment_processing'] = pp
    ledger.settings_json = json.dumps(settings)
    return payment_processor_settings(ledger)


def micr_export_rows(db, models, batch_id, ledger_id):
    """MICR-oriented check list for a posted payment batch."""
    AcctPaymentBatch = models['AcctPaymentBatch']
    AcctPaymentBatchLine = models['AcctPaymentBatchLine']
    AcctVendor = models['AcctVendor']
    AcctAPPayment = models['AcctAPPayment']
    batch = AcctPaymentBatch.query.filter_by(id=batch_id, ledger_id=ledger_id).first()
    if not batch:
        raise ValueError('Batch not found')
    if batch.status != 'Posted':
        raise ValueError('Batch must be posted')
    ledger = models['AcctLedger'].query.get(ledger_id)
    micr = payment_processor_settings(ledger)
    payments = AcctAPPayment.query.filter_by(payment_batch_id=batch.id).all()
    rows = []
    for p in payments:
        v = AcctVendor.query.get(p.vendor_id)
        rows.append({
            'check_number': p.check_number or '',
            'payment_number': p.payment_number,
            'vendor_name': v.name if v else '',
            'amount': p.amount,
            'payment_date': p.payment_date.isoformat() if p.payment_date else '',
            'micr_routing': micr['micr_bank_routing'],
            'micr_account': micr['micr_bank_account'],
            'company_name': micr['micr_company_name'],
        })
    return rows
