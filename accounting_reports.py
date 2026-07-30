"""Standard and custom financial reports for built-in accounting."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Any

from accounting_persistence import ap_aging, ar_aging, trial_balance

REPORT_TYPES = [
    {'id': 'trial_balance', 'name': 'Trial Balance', 'category': 'financial'},
    {'id': 'income_statement', 'name': 'Income Statement (P&L)', 'category': 'financial'},
    {'id': 'balance_sheet', 'name': 'Balance Sheet', 'category': 'financial'},
    {'id': 'journal_register', 'name': 'Journal Register', 'category': 'gl'},
    {'id': 'ap_aging', 'name': 'A/P Aging', 'category': 'ap'},
    {'id': 'ar_aging', 'name': 'A/R Aging', 'category': 'ar'},
    {'id': 'job_cost', 'name': 'Job Cost by Project', 'category': 'job'},
    {'id': 'construction_bridge', 'name': 'Construction → Accounting Bridge', 'category': 'job'},
    {'id': 'vendor_activity', 'name': 'Vendor Activity', 'category': 'ap'},
    {'id': 'customer_activity', 'name': 'Customer Activity', 'category': 'ar'},
    {'id': 'cash_summary', 'name': 'Cash & Bank Summary', 'category': 'bank'},
]


def report_catalog():
    return {'types': REPORT_TYPES}


def _posted_lines(db, models, ledger_id, *, project_id=None, start_date=None, end_date=None):
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctGLAccount = models['AcctGLAccount']
    batches = AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Posted').all()
    batch_ids = [b.id for b in batches]
    if not batch_ids:
        return [], {}
    batch_map = {b.id: b for b in batches}
    lines = AcctJournalLine.query.filter(AcctJournalLine.batch_id.in_(batch_ids)).all()
    accounts = {a.id: a for a in AcctGLAccount.query.filter_by(ledger_id=ledger_id).all()}
    out = []
    for ln in lines:
        b = batch_map.get(ln.batch_id)
        if not b:
            continue
        bd = b.batch_date or (b.posted_at.date() if b.posted_at else None)
        if start_date and bd and bd < start_date:
            continue
        if end_date and bd and bd > end_date:
            continue
        if project_id and ln.project_id and int(ln.project_id) != int(project_id):
            continue
        acct = accounts.get(ln.account_id)
        out.append({
            'batch_id': b.id,
            'batch_number': b.batch_number,
            'batch_date': bd.isoformat() if bd else None,
            'source': b.source,
            'account_id': ln.account_id,
            'account_number': acct.account_number if acct else '',
            'account_type': acct.account_type if acct else '',
            'description': ln.description or b.description,
            'debit': float(ln.debit or 0),
            'credit': float(ln.credit or 0),
            'project_id': ln.project_id,
            'reference': ln.reference,
        })
    return out, accounts


def income_statement(db, models, ledger_id, start_date=None, end_date=None):
    lines, accounts = _posted_lines(db, models, ledger_id, start_date=start_date, end_date=end_date)
    revenue = 0.0
    expense = 0.0
    detail = {'revenue': [], 'expense': []}
    by_acct: dict[int, dict] = {}
    for ln in lines:
        by_acct.setdefault(ln['account_id'], {'debits': 0.0, 'credits': 0.0, **ln})
        by_acct[ln['account_id']]['debits'] += ln['debit']
        by_acct[ln['account_id']]['credits'] += ln['credit']
    for aid, row in by_acct.items():
        atype = row.get('account_type') or ''
        net = row['credits'] - row['debits'] if atype == 'revenue' else row['debits'] - row['credits']
        if atype == 'revenue':
            revenue += net
            detail['revenue'].append({**row, 'amount': round(net, 2)})
        elif atype == 'expense':
            expense += net
            detail['expense'].append({**row, 'amount': round(net, 2)})
    net_income = round(revenue - expense, 2)
    return {
        'report': 'income_statement',
        'period': {'start': start_date.isoformat() if start_date else None, 'end': end_date.isoformat() if end_date else None},
        'total_revenue': round(revenue, 2),
        'total_expense': round(expense, 2),
        'net_income': net_income,
        'detail': detail,
    }


def balance_sheet(db, models, ledger_id, as_of: date | None = None):
    tb = trial_balance(db, models['AcctGLAccount'], models['AcctJournalLine'], models['AcctJournalBatch'], ledger_id)
    assets = liabilities = equity = 0.0
    sections = {'assets': [], 'liabilities': [], 'equity': []}
    for row in tb:
        atype = row.get('account_type') or ''
        bal = float(row.get('balance') or 0)
        if atype == 'asset':
            assets += bal
            sections['assets'].append(row)
        elif atype == 'liability':
            liabilities += -bal
            sections['liabilities'].append({**row, 'balance': round(-bal, 2)})
        elif atype == 'equity':
            equity += -bal
            sections['equity'].append({**row, 'balance': round(-bal, 2)})
    return {
        'report': 'balance_sheet',
        'as_of': (as_of or date.today()).isoformat(),
        'total_assets': round(assets, 2),
        'total_liabilities': round(liabilities, 2),
        'total_equity': round(equity, 2),
        'sections': sections,
    }


def journal_register(db, models, ledger_id, start_date=None, end_date=None, project_id=None):
    lines, _ = _posted_lines(db, models, ledger_id, project_id=project_id, start_date=start_date, end_date=end_date)
    return {'report': 'journal_register', 'lines': lines, 'line_count': len(lines)}


def job_cost_report(db, models, ledger_id, Project=None, project_id=None):
    lines, _ = _posted_lines(db, models, ledger_id, project_id=project_id)
    by_project: dict[Any, dict] = {}
    for ln in lines:
        pid = ln.get('project_id') or 0
        bucket = by_project.setdefault(pid, {'project_id': pid, 'debits': 0.0, 'credits': 0.0, 'net_cost': 0.0, 'lines': 0})
        bucket['debits'] += ln['debit']
        bucket['credits'] += ln['credit']
        bucket['lines'] += 1
    rows = []
    for pid, bucket in by_project.items():
        if pid == 0:
            continue
        bucket['net_cost'] = round(bucket['debits'] - bucket['credits'], 2)
        if Project and pid:
            p = Project.query.get(int(pid))
            bucket['project_name'] = (p.name if p else '') or ''
            bucket['project_number'] = (p.number if p else '') or ''
        rows.append(bucket)
    rows.sort(key=lambda r: -abs(r.get('net_cost') or 0))
    return {'report': 'job_cost', 'projects': rows}


def construction_bridge_report(db, models, ledger_id):
    AcctPostLink = models['AcctPostLink']
    links = AcctPostLink.query.filter_by(ledger_id=ledger_id).order_by(AcctPostLink.created_at.desc()).limit(500).all()
    return {
        'report': 'construction_bridge',
        'events': [{
            'id': l.id,
            'source_type': l.source_type,
            'source_key': l.source_key,
            'journal_batch_id': l.journal_batch_id,
            'ap_document_id': l.ap_document_id,
            'ar_document_id': l.ar_document_id,
            'purchase_order_id': l.purchase_order_id,
            'created_at': l.created_at.isoformat() if l.created_at else None,
        } for l in links],
    }


def vendor_activity_report(db, models, ledger_id):
    AcctVendor = models['AcctVendor']
    AcctAPDocument = models['AcctAPDocument']
    AcctAPPayment = models['AcctAPPayment']
    vendors = AcctVendor.query.filter_by(ledger_id=ledger_id).all()
    rows = []
    for v in vendors:
        invs = AcctAPDocument.query.filter_by(ledger_id=ledger_id, vendor_id=v.id).all()
        pays = AcctAPPayment.query.filter_by(ledger_id=ledger_id, vendor_id=v.id).all()
        billed = sum(float(i.amount or 0) for i in invs)
        paid = sum(float(p.amount or 0) for p in pays)
        rows.append({
            'vendor_id': v.id,
            'code': v.code,
            'name': v.name,
            'invoice_count': len(invs),
            'billed': round(billed, 2),
            'paid': round(paid, 2),
            'open': round(billed - sum(float(i.amount_paid or 0) for i in invs), 2),
        })
    return {'report': 'vendor_activity', 'vendors': rows}


def customer_activity_report(db, models, ledger_id):
    AcctCustomer = models['AcctCustomer']
    AcctARDocument = models['AcctARDocument']
    AcctARReceipt = models['AcctARReceipt']
    customers = AcctCustomer.query.filter_by(ledger_id=ledger_id).all()
    rows = []
    for c in customers:
        invs = AcctARDocument.query.filter_by(ledger_id=ledger_id, customer_id=c.id).all()
        rcpts = AcctARReceipt.query.filter_by(ledger_id=ledger_id, customer_id=c.id).all()
        billed = sum(float(i.amount or 0) for i in invs)
        collected = sum(float(r.amount or 0) for r in rcpts)
        rows.append({
            'customer_id': c.id,
            'code': c.code,
            'name': c.name,
            'invoice_count': len(invs),
            'billed': round(billed, 2),
            'collected': round(collected, 2),
            'open': round(billed - sum(float(i.amount_paid or 0) for i in invs), 2),
        })
    return {'report': 'customer_activity', 'customers': rows}


def cash_summary_report(db, models, ledger_id):
    AcctBankAccount = models['AcctBankAccount']
    AcctBankTransaction = models['AcctBankTransaction']
    accounts = AcctBankAccount.query.filter_by(ledger_id=ledger_id).all()
    rows = []
    for a in accounts:
        txs = AcctBankTransaction.query.filter_by(bank_account_id=a.id).all()
        balance = sum(float(t.amount or 0) for t in txs)
        unreconciled = sum(float(t.amount or 0) for t in txs if not t.reconciled)
        rows.append({
            'bank_account_id': a.id,
            'code': a.code,
            'name': a.name,
            'transaction_count': len(txs),
            'balance': round(balance, 2),
            'unreconciled': round(unreconciled, 2),
        })
    return {'report': 'cash_summary', 'accounts': rows}


def run_report(db, models, ledger_id, report_type, filters=None, Project=None):
    filters = filters or {}
    start = filters.get('start_date')
    end = filters.get('end_date')
    project_id = filters.get('project_id')
    if isinstance(start, str) and start:
        start = date.fromisoformat(start[:10])
    if isinstance(end, str) and end:
        end = date.fromisoformat(end[:10])

    if report_type == 'trial_balance':
        return {'report': 'trial_balance', 'rows': trial_balance(
            db, models['AcctGLAccount'], models['AcctJournalLine'], models['AcctJournalBatch'], ledger_id,
        )}
    if report_type == 'income_statement':
        return income_statement(db, models, ledger_id, start_date=start, end_date=end)
    if report_type == 'balance_sheet':
        return balance_sheet(db, models, ledger_id)
    if report_type == 'journal_register':
        return journal_register(db, models, ledger_id, start_date=start, end_date=end, project_id=project_id)
    if report_type == 'ap_aging':
        return {'report': 'ap_aging', **ap_aging(models['AcctAPDocument'], ledger_id)}
    if report_type == 'ar_aging':
        return {'report': 'ar_aging', **ar_aging(models['AcctARDocument'], ledger_id)}
    if report_type == 'job_cost':
        return job_cost_report(db, models, ledger_id, Project=Project, project_id=project_id)
    if report_type == 'construction_bridge':
        return construction_bridge_report(db, models, ledger_id)
    if report_type == 'vendor_activity':
        return vendor_activity_report(db, models, ledger_id)
    if report_type == 'customer_activity':
        return customer_activity_report(db, models, ledger_id)
    if report_type == 'cash_summary':
        return cash_summary_report(db, models, ledger_id)
    raise ValueError(f'Unknown report type: {report_type}')


def serialize_report_definition(row):
    return {
        'id': row.id,
        'name': row.name,
        'report_type': row.report_type,
        'filters': json.loads(row.filters_json) if row.filters_json else {},
        'columns': json.loads(row.columns_json) if row.columns_json else {},
        'is_favorite': bool(row.is_favorite),
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def report_to_csv(data: dict) -> str:
    """Flatten common report shapes to CSV."""
    buf = io.StringIO()
    w = csv.writer(buf)
    rtype = data.get('report') or ''
    if rtype == 'trial_balance':
        w.writerow(['Account', 'Description', 'Type', 'Debit', 'Credit', 'Balance'])
        for row in data.get('rows') or []:
            w.writerow([row.get('account_number'), row.get('description'), row.get('account_type'),
                        row.get('debit'), row.get('credit'), row.get('balance')])
    elif rtype == 'journal_register':
        w.writerow(['Date', 'Batch', 'Source', 'Account', 'Description', 'Debit', 'Credit', 'Project'])
        for row in data.get('lines') or []:
            w.writerow([row.get('batch_date'), row.get('batch_number'), row.get('source'),
                        row.get('account_number'), row.get('description'),
                        row.get('debit'), row.get('credit'), row.get('project_id')])
    elif rtype == 'income_statement':
        w.writerow(['Section', 'Account', 'Amount'])
        for row in data.get('detail', {}).get('revenue') or []:
            w.writerow(['Revenue', row.get('account_number'), row.get('amount')])
        for row in data.get('detail', {}).get('expense') or []:
            w.writerow(['Expense', row.get('account_number'), row.get('amount')])
        w.writerow(['', 'Net Income', data.get('net_income')])
    elif rtype == 'job_cost':
        w.writerow(['Project', 'Name', 'Net Cost', 'Lines'])
        for row in data.get('projects') or []:
            w.writerow([row.get('project_number') or row.get('project_id'), row.get('project_name'),
                        row.get('net_cost'), row.get('lines')])
    elif rtype == 'balance_sheet':
        w.writerow(['Section', 'Account', 'Description', 'Balance'])
        for section, key in (('Assets', 'assets'), ('Liabilities', 'liabilities'), ('Equity', 'equity')):
            for row in (data.get('sections') or {}).get(key) or []:
                w.writerow([section, row.get('account_number'), row.get('description'), row.get('balance')])
    elif rtype in ('ap_aging', 'ar_aging'):
        w.writerow(['Bucket', 'Amount'])
        for k, v in (data.get('buckets') or {}).items():
            w.writerow([k, v])
        w.writerow([])
        w.writerow(['Document', 'Open', 'Due'])
        for d in data.get('documents') or []:
            w.writerow([d.get('document_number') or d.get('id'), d.get('open_amount', d.get('balance')), d.get('due_date')])
    elif rtype == 'construction_bridge':
        w.writerow(['Created', 'Source Type', 'Source Key', 'Journal Batch', 'AP Doc', 'AR Doc', 'PO'])
        for e in data.get('events') or []:
            w.writerow([
                e.get('created_at'), e.get('source_type'), e.get('source_key'),
                e.get('journal_batch_id'), e.get('ap_document_id'), e.get('ar_document_id'), e.get('purchase_order_id'),
            ])
    elif rtype == 'vendor_activity':
        w.writerow(['Code', 'Name', 'Invoices', 'Billed', 'Paid', 'Open'])
        for v in data.get('vendors') or []:
            w.writerow([v.get('code'), v.get('name'), v.get('invoice_count'), v.get('billed'), v.get('paid'), v.get('open')])
    elif rtype == 'customer_activity':
        w.writerow(['Code', 'Name', 'Invoices', 'Billed', 'Collected', 'Open'])
        for c in data.get('customers') or []:
            w.writerow([c.get('code'), c.get('name'), c.get('invoice_count'), c.get('billed'), c.get('collected'), c.get('open')])
    elif rtype == 'cash_summary':
        w.writerow(['Code', 'Name', 'Balance', 'Unreconciled', 'Transactions'])
        for a in data.get('accounts') or []:
            w.writerow([a.get('code'), a.get('name'), a.get('balance'), a.get('unreconciled'), a.get('transaction_count')])
    else:
        w.writerow(['report', rtype])
        w.writerow(['data', json.dumps(data, default=str)[:32000]])
    return buf.getvalue()
