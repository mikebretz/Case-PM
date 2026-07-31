"""Multi-currency exchange rates and G/L revaluation."""
from __future__ import annotations

import json
from datetime import date, datetime

from accounting_gl_service import assert_period_open
from accounting_persistence import next_batch_number, post_journal_batch, trial_balance


def serialize_rate(r):
    return {
        'id': r.id,
        'currency_code': r.currency_code,
        'rate_date': r.rate_date.isoformat() if r.rate_date else None,
        'rate_to_functional': float(r.rate_to_functional or 1),
        'source': r.source,
    }


def upsert_currency_rate(db, models, ledger_id, body):
    AcctCurrencyRate = models['AcctCurrencyRate']
    code = (body.get('currency_code') or '').upper()[:3]
    if not code:
        raise ValueError('currency_code required')
    rate_date = body.get('rate_date')
    rate_date = date.fromisoformat(rate_date) if isinstance(rate_date, str) else (rate_date or date.today())
    rate = round(float(body.get('rate_to_functional') or 0), 6)
    if rate <= 0:
        raise ValueError('rate_to_functional must be positive')
    row = AcctCurrencyRate.query.filter_by(
        ledger_id=ledger_id, currency_code=code, rate_date=rate_date,
    ).first()
    if not row:
        row = AcctCurrencyRate(
            ledger_id=ledger_id,
            currency_code=code,
            rate_date=rate_date,
            rate_to_functional=rate,
            source=(body.get('source') or 'manual')[:40],
        )
        db.session.add(row)
    else:
        row.rate_to_functional = rate
        row.source = (body.get('source') or row.source)[:40]
    db.session.flush()
    return row


def rate_on_date(AcctCurrencyRate, ledger_id, currency_code, on_date):
    if not currency_code or currency_code.upper() == 'USD':
        return 1.0
    row = (
        AcctCurrencyRate.query.filter_by(ledger_id=ledger_id, currency_code=currency_code.upper())
        .filter(AcctCurrencyRate.rate_date <= on_date)
        .order_by(AcctCurrencyRate.rate_date.desc())
        .first()
    )
    return float(row.rate_to_functional) if row else 1.0


def functional_amount(amount, fx_rate):
    return round(float(amount or 0) * float(fx_rate or 1), 2)


def run_revaluation(db, models, ledger_id, body, user_id=None):
    """Post unrealized gain/loss on monetary asset/liability balances vs new rates."""
    from accounting_posting import load_accounting_options, _account_by_number

    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctRevaluationRun = models['AcctRevaluationRun']
    AcctCurrencyRate = models['AcctCurrencyRate']

    ledger = AcctLedger.query.get(ledger_id)
    if not ledger:
        raise ValueError('Ledger not found')
    period_end = body.get('period_end')
    period_end = date.fromisoformat(period_end) if isinstance(period_end, str) else (period_end or date.today())
    currencies = body.get('currencies') or []
    if not currencies:
        currencies = sorted({
            r.currency_code for r in AcctCurrencyRate.query.filter_by(ledger_id=ledger_id).all()
            if r.currency_code and r.currency_code.upper() != (ledger.base_currency or 'USD').upper()
        })
    gain_acct = body.get('gain_account_id')
    loss_acct = body.get('loss_account_id')
    opts = load_accounting_options()
    if not gain_acct:
        gain_acct = _account_by_number(AcctGLAccount, ledger_id, opts.get('revenue_account', '4000')).id
    if not loss_acct:
        loss_acct = _account_by_number(AcctGLAccount, ledger_id, opts.get('materials_expense', '5200')).id

    tb = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id)
    adjustment = 0.0
    for row in tb:
        if row['account_type'] not in ('asset', 'liability'):
            continue
        bal = float(row['balance'] or 0)
        if abs(bal) < 0.01:
            continue
        for cur in currencies:
            new_rate = rate_on_date(AcctCurrencyRate, ledger_id, cur, period_end)
            old_rate = rate_on_date(AcctCurrencyRate, ledger_id, cur, date(period_end.year, max(1, period_end.month - 1), 1))
            if abs(new_rate - old_rate) < 0.000001:
                continue
            adjustment += round(bal * (new_rate - old_rate) * 0.01, 2)

    adjustment = round(adjustment, 2)
    if adjustment == 0:
        raise ValueError('No revaluation adjustment computed — add currency rates or balances')

    n = AcctRevaluationRun.query.filter_by(ledger_id=ledger_id).count()
    run = AcctRevaluationRun(
        ledger_id=ledger_id,
        run_number=f'REVAL-{period_end.strftime("%Y%m")}-{n + 1:03d}',
        period_end=period_end,
        status='Posted',
        details_json=json.dumps({'currencies': currencies, 'adjustment': adjustment}),
    )
    db.session.add(run)
    db.session.flush()

    batch = AcctJournalBatch(
        ledger_id=ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, ledger_id),
        source='GL-REVAL',
        description=f'Currency revaluation {run.run_number}',
        batch_date=period_end,
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    assert_period_open(ledger, period_end)
    if adjustment > 0:
        db.session.add(AcctJournalLine(batch_id=batch.id, line_number=1, account_id=int(gain_acct), debit=0, credit=adjustment, description='FX revaluation'))
        db.session.add(AcctJournalLine(batch_id=batch.id, line_number=2, account_id=int(loss_acct), debit=adjustment, credit=0, description='FX revaluation'))
    else:
        adj = abs(adjustment)
        db.session.add(AcctJournalLine(batch_id=batch.id, line_number=1, account_id=int(loss_acct), debit=0, credit=adj, description='FX revaluation'))
        db.session.add(AcctJournalLine(batch_id=batch.id, line_number=2, account_id=int(gain_acct), debit=adj, credit=0, description='FX revaluation'))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger, models=models, user_id=user_id)
    run.journal_batch_id = batch.id
    db.session.flush()
    return {'run_id': run.id, 'journal_batch_id': batch.id, 'adjustment': adjustment}
