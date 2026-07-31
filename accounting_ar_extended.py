"""A/R depth — groups, ship-to, memos, recurring, dunning, statements, receipt batches."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from accounting_posting import create_ar_receipt, load_accounting_options, _account_by_number, _create_posted_batch


def serialize_customer_group(g):
    return {
        'id': g.id, 'code': g.code, 'name': g.name,
        'credit_limit': g.credit_limit, 'status': g.status,
    }


def serialize_customer_extended(c):
    from accounting_persistence import serialize_customer
    base = serialize_customer(c)
    base.update({
        'customer_group_id': c.customer_group_id,
        'credit_hold': bool(c.credit_hold),
        'national_account_code': c.national_account_code or '',
    })
    return base


def serialize_ship_to(s):
    try:
        addr = json.loads(s.address_json or '{}') if s.address_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        addr = {}
    return {
        'id': s.id,
        'customer_id': s.customer_id,
        'code': s.code,
        'name': s.name,
        'address': addr,
        'is_default': s.is_default,
        'status': s.status,
    }


def assert_customer_can_invoice(customer):
    if customer.credit_hold:
        raise ValueError('Customer is on credit hold')


def create_ar_memo(db, models, ledger_id, body, user_id=None):
    """Credit or debit memo linked to customer (and optional parent invoice)."""
    AcctCustomer = models['AcctCustomer']
    AcctARDocument = models['AcctARDocument']
    AcctGLAccount = models['AcctGLAccount']
    customer = AcctCustomer.query.filter_by(id=int(body['customer_id']), ledger_id=ledger_id).first()
    if not customer:
        raise ValueError('Customer not found')
    assert_customer_can_invoice(customer)
    doc_type = (body.get('document_type') or 'Credit').strip()
    if doc_type not in ('Credit', 'Debit'):
        raise ValueError('document_type must be Credit or Debit')
    amt = round(float(body.get('amount') or 0), 2)
    if amt <= 0:
        raise ValueError('amount required')
    n = AcctARDocument.query.filter_by(ledger_id=ledger_id).count()
    doc = AcctARDocument(
        ledger_id=ledger_id,
        customer_id=customer.id,
        document_number=(body.get('document_number') or f'{doc_type[:1]}M-{n + 1:05d}')[:40],
        document_type=doc_type,
        document_date=date.fromisoformat(body['document_date']) if body.get('document_date') else date.today(),
        due_date=date.fromisoformat(body['due_date']) if body.get('due_date') else date.today(),
        amount=amt,
        status='Open',
        ship_to_id=body.get('ship_to_id'),
        parent_document_id=body.get('parent_document_id'),
    )
    db.session.add(doc)
    db.session.flush()
    if body.get('post_gl'):
        opts = load_accounting_options()
        ar_acct = _account_by_number(AcctGLAccount, ledger_id, opts['ar_account'])
        rev_acct = _account_by_number(AcctGLAccount, ledger_id, opts['revenue_account'])
        if doc_type == 'Credit':
            lines = [
                {'account_id': rev_acct.id, 'debit': amt, 'credit': 0},
                {'account_id': ar_acct.id, 'debit': 0, 'credit': amt},
            ]
        else:
            lines = [
                {'account_id': ar_acct.id, 'debit': amt, 'credit': 0},
                {'account_id': rev_acct.id, 'debit': 0, 'credit': amt},
            ]
        batch = _create_posted_batch(
            db, models, ledger_id=ledger_id, source='AR-MEMO',
            description=f'AR {doc_type} memo {doc.document_number}',
            user_id=user_id,
            lines=lines,
        )
        meta = {'journal_batch_id': batch.id}
        doc.details_json = json.dumps(meta)
    db.session.flush()
    return doc


def serialize_recurring_ar(r):
    return {
        'id': r.id,
        'customer_id': r.customer_id,
        'description': r.description,
        'amount': r.amount,
        'frequency': r.frequency,
        'next_run_date': r.next_run_date.isoformat() if r.next_run_date else None,
        'is_active': r.is_active,
    }


def generate_recurring_ar_invoice(db, models, recurring):
    if not recurring.is_active:
        raise ValueError('Recurring billing inactive')
    AcctCustomer = models['AcctCustomer']
    AcctARDocument = models['AcctARDocument']
    customer = AcctCustomer.query.get(recurring.customer_id)
    if customer:
        assert_customer_can_invoice(customer)
    n = AcctARDocument.query.filter_by(ledger_id=recurring.ledger_id).count()
    doc = AcctARDocument(
        ledger_id=recurring.ledger_id,
        customer_id=recurring.customer_id,
        document_number=f'{recurring.document_number_prefix}-{datetime.utcnow().strftime("%Y%m%d")}-{n + 1}',
        document_type='Invoice',
        document_date=recurring.next_run_date or date.today(),
        due_date=recurring.next_run_date or date.today(),
        amount=recurring.amount,
        status='Open',
    )
    db.session.add(doc)
    recurring.last_run_date = doc.document_date
    d = recurring.next_run_date or date.today()
    if recurring.frequency == 'weekly':
        recurring.next_run_date = d + timedelta(days=7)
    else:
        recurring.next_run_date = date(d.year + (1 if d.month == 12 else 0), (d.month % 12) + 1, min(d.day, 28))
    db.session.flush()
    return doc


def overdue_customers(AcctARDocument, AcctCustomer, ledger_id):
    today = date.today()
    docs = AcctARDocument.query.filter_by(ledger_id=ledger_id).filter(
        AcctARDocument.status.in_(['Open', 'Partial'])
    ).all()
    by_customer = {}
    for d in docs:
        open_amt = float(d.amount or 0) - float(d.amount_paid or 0)
        if open_amt <= 0:
            continue
        due = d.due_date or d.document_date or today
        days = (today - due).days if due else 0
        if days < 30:
            continue
        by_customer.setdefault(d.customer_id, {'open': 0.0, 'max_days': 0, 'documents': []})
        by_customer[d.customer_id]['open'] += open_amt
        by_customer[d.customer_id]['max_days'] = max(by_customer[d.customer_id]['max_days'], days)
        by_customer[d.customer_id]['documents'].append(d.id)
    out = []
    for cid, agg in by_customer.items():
        c = AcctCustomer.query.get(cid)
        level = 1 if agg['max_days'] < 60 else (2 if agg['max_days'] < 90 else 3)
        out.append({
            'customer_id': cid,
            'customer_name': c.name if c else '',
            'open_amount': round(agg['open'], 2),
            'max_days_past_due': agg['max_days'],
            'suggested_dunning_level': level,
        })
    return out


def record_dunning(db, models, ledger_id, customer_id, level, message=''):
    AcctARDunningLog = models['AcctARDunningLog']
    row = AcctARDunningLog(
        ledger_id=ledger_id,
        customer_id=int(customer_id),
        level=int(level),
        message=(message or f'Dunning level {level}')[:500],
    )
    db.session.add(row)
    db.session.flush()
    return row


def customer_statement(db, models, ledger_id, customer_id):
    AcctCustomer = models['AcctCustomer']
    AcctARDocument = models['AcctARDocument']
    c = AcctCustomer.query.filter_by(id=int(customer_id), ledger_id=ledger_id).first()
    if not c:
        raise ValueError('Customer not found')
    docs = AcctARDocument.query.filter_by(ledger_id=ledger_id, customer_id=c.id).order_by(
        AcctARDocument.document_date.desc(),
    ).limit(200).all()
    lines = []
    balance = 0.0
    for d in reversed(docs):
        open_amt = float(d.amount or 0) - float(d.amount_paid or 0)
        balance += open_amt
        lines.append({
            'document_number': d.document_number,
            'document_type': d.document_type,
            'document_date': d.document_date.isoformat() if d.document_date else None,
            'due_date': d.due_date.isoformat() if d.due_date else None,
            'amount': d.amount,
            'open_amount': round(open_amt, 2),
            'status': d.status,
        })
    return {
        'customer': serialize_customer_extended(c),
        'statement_date': date.today().isoformat(),
        'open_balance': round(balance, 2),
        'lines': list(reversed(lines)),
    }


def next_receipt_batch_number(AcctARReceiptBatch, ledger_id):
    n = AcctARReceiptBatch.query.filter_by(ledger_id=ledger_id).count()
    return f'RCPT-B-{datetime.utcnow().strftime("%Y%m")}-{n + 1:04d}'


def create_receipt_batch(db, models, ledger_id, body, user_id=None):
    AcctARReceiptBatch = models['AcctARReceiptBatch']
    AcctARReceiptBatchLine = models['AcctARReceiptBatchLine']
    batch = AcctARReceiptBatch(
        ledger_id=ledger_id,
        batch_number=body.get('batch_number') or next_receipt_batch_number(AcctARReceiptBatch, ledger_id),
        batch_date=date.fromisoformat(body['batch_date']) if body.get('batch_date') else date.today(),
        status='Open',
    )
    db.session.add(batch)
    db.session.flush()
    for ln in body.get('lines') or []:
        amt = round(float(ln.get('amount') or 0), 2)
        if amt <= 0:
            continue
        db.session.add(AcctARReceiptBatchLine(
            batch_id=batch.id,
            customer_id=int(ln['customer_id']),
            ar_document_id=int(ln['ar_document_id']) if ln.get('ar_document_id') else None,
            amount=amt,
            payment_method=(ln.get('payment_method') or 'ACH')[:20],
        ))
    db.session.flush()
    return batch


def post_receipt_batch(db, models, batch, user_id=None):
    if batch.status != 'Open':
        raise ValueError('Batch not open')
    AcctARReceiptBatchLine = models['AcctARReceiptBatchLine']
    lines = AcctARReceiptBatchLine.query.filter_by(batch_id=batch.id).all()
    if not lines:
        raise ValueError('Batch has no lines')
    receipt_ids = []
    by_customer = {}
    for ln in lines:
        by_customer.setdefault(ln.customer_id, []).append(ln)
    for customer_id, vlines in by_customer.items():
        apps = []
        total = 0.0
        for ln in vlines:
            if ln.ar_document_id:
                apps.append({'ar_document_id': ln.ar_document_id, 'amount': ln.amount})
            total += float(ln.amount or 0)
        total = round(total, 2)
        out = create_ar_receipt(
            db, models,
            customer_id=customer_id,
            amount=total,
            applications=apps,
            payment_method=vlines[0].payment_method,
            user_id=user_id,
        )
        receipt_ids.append(out['receipt'].id)
    batch.status = 'Posted'
    batch.posted_at = datetime.utcnow()
    db.session.flush()
    return {'receipt_ids': receipt_ids, 'batch_id': batch.id}
