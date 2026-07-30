"""Persistence, seed data, and reporting for the built-in accounting suite."""
from __future__ import annotations

import json
from datetime import date, datetime

DEFAULT_COA = [
    ('1000', 'Cash — Operating', 'asset', 'debit'),
    ('1100', 'Accounts Receivable', 'asset', 'debit'),
    ('1200', 'Retainage Receivable', 'asset', 'debit'),
    ('1300', 'Costs in Excess of Billings', 'asset', 'debit'),
    ('1500', 'Inventory', 'asset', 'debit'),
    ('1700', 'Equipment', 'asset', 'debit'),
    ('2000', 'Accounts Payable', 'liability', 'credit'),
    ('2100', 'Retainage Payable', 'liability', 'credit'),
    ('2200', 'Billings in Excess of Costs', 'liability', 'credit'),
    ('2300', 'Payroll Liabilities', 'liability', 'credit'),
    ('3000', 'Member Capital', 'equity', 'credit'),
    ('4000', 'Construction Revenue', 'revenue', 'credit'),
    ('5000', 'Direct Labor', 'expense', 'debit'),
    ('5100', 'Subcontractors', 'expense', 'debit'),
    ('5200', 'Materials', 'expense', 'debit'),
    ('5300', 'Equipment Expense', 'expense', 'debit'),
    ('5400', 'Other Job Costs', 'expense', 'debit'),
    ('6000', 'General & Administrative', 'expense', 'debit'),
]


def ensure_accounting_schema(db, models):
    """Create tables and migrate columns on existing accounting databases."""
    try:
        db.create_all()
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        from sqlalchemy import inspect, text
        insp = inspect(db.engine)
        table_names = set(insp.get_table_names())

        def add_column(table, col, ddl):
            if table not in table_names:
                return
            cols = {c['name'] for c in insp.get_columns(table)}
            if col in cols:
                return
            try:
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}'))
                db.session.commit()
            except Exception:
                db.session.rollback()

        if 'acct_fixed_asset' in table_names:
            for col, ddl in (
                ('accumulated_depreciation', 'FLOAT DEFAULT 0'),
                ('useful_life_months', 'INTEGER DEFAULT 60'),
                ('depreciation_method', "VARCHAR(30) DEFAULT 'straight_line'"),
                ('location', 'VARCHAR(120)'),
                ('serial_number', 'VARCHAR(80)'),
                ('salvage_value', 'FLOAT DEFAULT 0'),
                ('in_service_date', 'DATE'),
            ):
                add_column('acct_fixed_asset', col, ddl)

        if 'acct_payroll_run' in table_names:
            add_column('acct_payroll_run', 'total_taxes', 'FLOAT DEFAULT 0')
            add_column('acct_payroll_run', 'journal_batch_id', 'INTEGER')
            add_column('acct_payroll_run', 'period_start', 'DATE')
            add_column('acct_payroll_run', 'period_end', 'DATE')
            add_column('acct_payroll_run', 'pay_frequency', "VARCHAR(20) DEFAULT 'biweekly'")
            add_column('acct_payroll_run', 'total_deductions', 'FLOAT DEFAULT 0')
            add_column('acct_payroll_run', 'total_employer_taxes', 'FLOAT DEFAULT 0')
            add_column('acct_payroll_run', 'notes', 'TEXT')

        if 'acct_tax_group' in table_names:
            add_column('acct_tax_group', 'tax_type', "VARCHAR(20) DEFAULT 'sales'")
            add_column('acct_tax_group', 'applies_to', "VARCHAR(10) DEFAULT 'both'")
            add_column('acct_tax_group', 'is_active', 'INTEGER DEFAULT 1')

        if 'acct_inventory_item' in table_names:
            add_column('acct_inventory_item', 'uom', "VARCHAR(10) DEFAULT 'EA'")

        try:
            db.create_all()
            db.session.commit()
        except Exception:
            db.session.rollback()
    except Exception:
        db.session.rollback()


def get_or_create_default_ledger(db, AcctLedger):
    row = AcctLedger.query.filter_by(code='MAIN').first()
    if row:
        return row
    row = AcctLedger(
        code='MAIN',
        name='Primary Company',
        base_currency='USD',
        fiscal_year_end_month=12,
        settings_json=json.dumps({'segments': 3, 'history_years': 7}),
    )
    db.session.add(row)
    db.session.flush()
    return row


def seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger=None):
    ledger = ledger or get_or_create_default_ledger(db, AcctLedger)
    existing = AcctGLAccount.query.filter_by(ledger_id=ledger.id).count()
    if existing > 0:
        return ledger
    for num, desc, atype, normal in DEFAULT_COA:
        db.session.add(AcctGLAccount(
            ledger_id=ledger.id,
            account_number=num,
            description=desc,
            account_type=atype,
            normal_balance=normal,
            is_posting=True,
            status='Active',
        ))
    db.session.flush()
    return ledger


def serialize_account(a):
    return {
        'id': a.id,
        'ledger_id': a.ledger_id,
        'account_number': a.account_number,
        'description': a.description,
        'account_type': a.account_type,
        'normal_balance': a.normal_balance,
        'status': a.status,
        'is_posting': a.is_posting,
    }


def serialize_batch(b, lines=None):
    return {
        'id': b.id,
        'batch_number': b.batch_number,
        'source': b.source,
        'description': b.description,
        'batch_date': b.batch_date.isoformat() if b.batch_date else None,
        'status': b.status,
        'posted_at': b.posted_at.isoformat() if b.posted_at else None,
        'lines': lines or [],
    }


def serialize_vendor(v):
    return {
        'id': v.id,
        'code': v.code,
        'name': v.name,
        'terms': v.terms,
        'tax_group': v.tax_group,
        'email': v.email,
        'phone': v.phone,
        'status': v.status,
    }


def serialize_customer(c):
    return {
        'id': c.id,
        'code': c.code,
        'name': c.name,
        'terms': c.terms,
        'credit_limit': c.credit_limit,
        'status': c.status,
    }


def serialize_ap_doc(d):
    return {
        'id': d.id,
        'vendor_id': d.vendor_id,
        'document_number': d.document_number,
        'document_type': d.document_type,
        'document_date': d.document_date.isoformat() if d.document_date else None,
        'due_date': d.due_date.isoformat() if d.due_date else None,
        'amount': d.amount,
        'amount_paid': d.amount_paid,
        'status': d.status,
        'project_id': d.project_id,
    }


def serialize_ar_doc(d):
    return {
        'id': d.id,
        'customer_id': d.customer_id,
        'document_number': d.document_number,
        'document_date': d.document_date.isoformat() if d.document_date else None,
        'due_date': d.due_date.isoformat() if d.due_date else None,
        'amount': d.amount,
        'amount_paid': d.amount_paid,
        'status': d.status,
        'project_id': d.project_id,
    }


def trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id):
    posted_batches = {
        b.id for b in AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Posted').all()
    }
    totals = {}
    if posted_batches:
        lines = AcctJournalLine.query.filter(AcctJournalLine.batch_id.in_(posted_batches)).all()
        for ln in lines:
            totals.setdefault(ln.account_id, {'debit': 0.0, 'credit': 0.0})
            totals[ln.account_id]['debit'] += float(ln.debit or 0)
            totals[ln.account_id]['credit'] += float(ln.credit or 0)
    rows = []
    accounts = AcctGLAccount.query.filter_by(ledger_id=ledger_id).order_by(AcctGLAccount.account_number).all()
    for acct in accounts:
        t = totals.get(acct.id, {'debit': 0.0, 'credit': 0.0})
        rows.append({
            **serialize_account(acct),
            'debit': round(t['debit'], 2),
            'credit': round(t['credit'], 2),
            'balance': round(t['debit'] - t['credit'], 2),
        })
    return rows


def ap_aging(AcctAPDocument, ledger_id):
    today = date.today()
    docs = AcctAPDocument.query.filter_by(ledger_id=ledger_id).filter(
        AcctAPDocument.status.in_(['Open', 'Partial'])
    ).all()
    buckets = {'current': 0.0, '1_30': 0.0, '31_60': 0.0, '61_90': 0.0, 'over_90': 0.0}
    lines = []
    for d in docs:
        open_amt = float(d.amount or 0) - float(d.amount_paid or 0)
        if open_amt <= 0:
            continue
        due = d.due_date or d.document_date or today
        days = (today - due).days if due else 0
        if days <= 0:
            buckets['current'] += open_amt
        elif days <= 30:
            buckets['1_30'] += open_amt
        elif days <= 60:
            buckets['31_60'] += open_amt
        elif days <= 90:
            buckets['61_90'] += open_amt
        else:
            buckets['over_90'] += open_amt
        lines.append({**serialize_ap_doc(d), 'open_amount': round(open_amt, 2), 'days_past_due': max(days, 0)})
    return {'buckets': {k: round(v, 2) for k, v in buckets.items()}, 'documents': lines}


def ar_aging(AcctARDocument, ledger_id):
    today = date.today()
    docs = AcctARDocument.query.filter_by(ledger_id=ledger_id).filter(
        AcctARDocument.status.in_(['Open', 'Partial'])
    ).all()
    buckets = {'current': 0.0, '1_30': 0.0, '31_60': 0.0, '61_90': 0.0, 'over_90': 0.0}
    lines = []
    for d in docs:
        open_amt = float(d.amount or 0) - float(d.amount_paid or 0)
        if open_amt <= 0:
            continue
        due = d.due_date or d.document_date or today
        days = (today - due).days if due else 0
        if days <= 0:
            buckets['current'] += open_amt
        elif days <= 30:
            buckets['1_30'] += open_amt
        elif days <= 60:
            buckets['31_60'] += open_amt
        elif days <= 90:
            buckets['61_90'] += open_amt
        else:
            buckets['over_90'] += open_amt
        lines.append({**serialize_ar_doc(d), 'open_amount': round(open_amt, 2), 'days_past_due': max(days, 0)})
    return {'buckets': {k: round(v, 2) for k, v in buckets.items()}, 'documents': lines}


def next_batch_number(AcctJournalBatch, ledger_id):
    count = AcctJournalBatch.query.filter_by(ledger_id=ledger_id).count()
    return f'JB-{datetime.utcnow().strftime("%Y%m")}-{count + 1:04d}'


def post_journal_batch(db, batch, AcctJournalLine):
    lines = AcctJournalLine.query.filter_by(batch_id=batch.id).all()
    if not lines:
        raise ValueError('Batch has no lines')
    total_d = sum(float(l.debit or 0) for l in lines)
    total_c = sum(float(l.credit or 0) for l in lines)
    if round(total_d - total_c, 2) != 0:
        raise ValueError(f'Batch out of balance by {total_d - total_c:.2f}')
    batch.status = 'Posted'
    batch.posted_at = datetime.utcnow()
    db.session.flush()
    return batch
