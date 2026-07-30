"""Bank account operations — balances, manual entries, G/L cash link."""
from __future__ import annotations

from datetime import date

from accounting_persistence import get_or_create_default_ledger, next_batch_number, post_journal_batch, seed_chart_of_accounts
from accounting_posting import load_accounting_options, _account_by_number


def serialize_bank_account(a, *, balance=0.0, unreconciled=0):
    return {
        'id': a.id,
        'code': a.code,
        'name': a.name,
        'currency': a.currency,
        'status': a.status,
        'gl_account_id': a.gl_account_id,
        'last_reconciled_date': a.last_reconciled_date.isoformat() if a.last_reconciled_date else None,
        'book_balance': round(float(balance), 2),
        'unreconciled_count': int(unreconciled),
    }


def bank_ledger_summary(db, models, ledger_id):
    AcctBankAccount = models['AcctBankAccount']
    AcctBankTransaction = models['AcctBankTransaction']
    accounts = AcctBankAccount.query.filter_by(ledger_id=ledger_id).all()
    out = []
    for a in accounts:
        txs = AcctBankTransaction.query.filter_by(bank_account_id=a.id).all()
        bal = sum(float(t.amount or 0) for t in txs)
        unrec = sum(1 for t in txs if not t.reconciled)
        out.append(serialize_bank_account(a, balance=bal, unreconciled=unrec))
    return out


def patch_bank_account(acct, body, AcctGLAccount, ledger_id):
    if body.get('name') is not None:
        acct.name = str(body['name']).strip()[:200]
    if body.get('status') in ('Active', 'Inactive'):
        acct.status = body['status']
    if 'gl_account_id' in body:
        gid = body.get('gl_account_id')
        if gid:
            gl = AcctGLAccount.query.filter_by(id=int(gid), ledger_id=ledger_id).first()
            if not gl:
                raise ValueError('G/L cash account not found')
            acct.gl_account_id = gl.id
        else:
            acct.gl_account_id = None


def record_manual_bank_transaction(
    db,
    models,
    *,
    ledger_id,
    bank_account_id,
    amount,
    description='',
    transaction_type='Manual',
    reference='',
    transaction_date=None,
    post_gl=False,
    offset_account_id=None,
    user_id=None,
):
    AcctBankAccount = models['AcctBankAccount']
    AcctBankTransaction = models['AcctBankTransaction']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']

    bank = AcctBankAccount.query.filter_by(id=int(bank_account_id), ledger_id=ledger_id).first()
    if not bank:
        raise ValueError('Bank account not found')
    amt = float(amount or 0)
    if amt == 0:
        raise ValueError('Amount cannot be zero')

    tx = AcctBankTransaction(
        bank_account_id=bank.id,
        transaction_date=transaction_date or date.today(),
        description=(description or '')[:300],
        amount=amt,
        transaction_type=(transaction_type or 'Manual')[:20],
        reference=(reference or '')[:80],
        reconciled=False,
    )
    db.session.add(tx)
    db.session.flush()

    batch_id = None
    if post_gl:
        opts = load_accounting_options()
        ledger = get_or_create_default_ledger(db, AcctLedger)
        seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)
        cash_id = bank.gl_account_id
        if cash_id:
            cash_acct = AcctGLAccount.query.get(cash_id)
        else:
            cash_acct = _account_by_number(AcctGLAccount, ledger_id, opts['cash_account'])
        if offset_account_id:
            off = AcctGLAccount.query.filter_by(id=int(offset_account_id), ledger_id=ledger_id).first()
            if not off:
                raise ValueError('Offset G/L account not found')
        else:
            off_num = opts['materials_expense'] if amt < 0 else opts['revenue_account']
            off = _account_by_number(AcctGLAccount, ledger_id, off_num)

        abs_amt = abs(amt)
        if amt > 0:
            lines = [
                {'account_id': cash_acct.id, 'debit': abs_amt, 'credit': 0, 'description': description, 'reference': reference},
                {'account_id': off.id, 'debit': 0, 'credit': abs_amt, 'description': description, 'reference': reference},
            ]
        else:
            lines = [
                {'account_id': off.id, 'debit': abs_amt, 'credit': 0, 'description': description, 'reference': reference},
                {'account_id': cash_acct.id, 'debit': 0, 'credit': abs_amt, 'description': description, 'reference': reference},
            ]
        batch = AcctJournalBatch(
            ledger_id=ledger_id,
            batch_number=next_batch_number(AcctJournalBatch, ledger_id),
            source='BK',
            description=f'Bank {bank.code}: {description or transaction_type}'[:300],
            batch_date=transaction_date or date.today(),
            status='Open',
            created_by_id=user_id,
        )
        db.session.add(batch)
        db.session.flush()
        for i, ln in enumerate(lines, start=1):
            db.session.add(AcctJournalLine(
                batch_id=batch.id,
                line_number=i,
                account_id=ln['account_id'],
                description=ln.get('description') or '',
                debit=float(ln.get('debit') or 0),
                credit=float(ln.get('credit') or 0),
                reference=ln.get('reference') or '',
            ))
        ledger = AcctLedger.query.get(ledger_id)
        post_journal_batch(db, batch, AcctJournalLine, ledger=ledger)
        batch_id = batch.id

    return {'transaction_id': tx.id, 'journal_batch_id': batch_id}
