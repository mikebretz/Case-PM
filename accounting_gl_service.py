"""General ledger operations — account inquiry, batch maintenance, ledger options."""
from __future__ import annotations

import json
from datetime import date, datetime

from accounting_persistence import serialize_account, serialize_batch


def _parse_settings(ledger):
    try:
        return json.loads(ledger.settings_json or '{}') if ledger.settings_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def ledger_gl_options(ledger):
    settings = _parse_settings(ledger)
    return {
        'ledger_id': ledger.id,
        'code': ledger.code,
        'name': ledger.name,
        'base_currency': ledger.base_currency,
        'fiscal_year_end_month': ledger.fiscal_year_end_month,
        'segment_count': int(settings.get('segments') or 3),
        'closed_periods': list(settings.get('closed_periods') or []),
        'history_years': int(settings.get('history_years') or 7),
    }


def update_ledger_gl_options(ledger, body):
    settings = _parse_settings(ledger)
    if 'segment_count' in body:
        settings['segments'] = max(1, min(10, int(body['segment_count'])))
    if 'closed_periods' in body and isinstance(body['closed_periods'], list):
        settings['closed_periods'] = [str(p) for p in body['closed_periods']]
    if 'history_years' in body:
        settings['history_years'] = max(1, int(body['history_years']))
    if body.get('fiscal_year_end_month') is not None:
        ledger.fiscal_year_end_month = max(1, min(12, int(body['fiscal_year_end_month'])))
    ledger.settings_json = json.dumps(settings)
    return ledger_gl_options(ledger)


def period_key_for_date(d: date) -> str:
    return f'{d.year:04d}-{d.month:02d}'


def assert_period_open(ledger, batch_date: date):
    settings = _parse_settings(ledger)
    closed = set(settings.get('closed_periods') or [])
    key = period_key_for_date(batch_date or date.today())
    if key in closed:
        raise ValueError(f'Fiscal period {key} is closed — reopen in G/L options or choose another date')


def patch_gl_account(acct, body):
    if body.get('description') is not None:
        acct.description = str(body['description']).strip()[:200]
    if body.get('account_type') in ('asset', 'liability', 'equity', 'revenue', 'expense'):
        acct.account_type = body['account_type']
    if body.get('normal_balance') in ('debit', 'credit'):
        acct.normal_balance = body['normal_balance']
    if body.get('status') in ('Active', 'Inactive'):
        acct.status = body['status']
    if 'is_posting' in body:
        acct.is_posting = bool(body['is_posting'])
    return acct


def batch_lines_payload(AcctJournalLine, AcctGLAccount, batch_id):
    lines = AcctJournalLine.query.filter_by(batch_id=batch_id).order_by(AcctJournalLine.line_number).all()
    out = []
    for ln in lines:
        acct = AcctGLAccount.query.get(ln.account_id)
        out.append({
            'id': ln.id,
            'line_number': ln.line_number,
            'account_id': ln.account_id,
            'account_number': acct.account_number if acct else '',
            'account_description': acct.description if acct else '',
            'description': ln.description,
            'debit': ln.debit,
            'credit': ln.credit,
            'project_id': ln.project_id,
            'reference': ln.reference,
            'location_id': getattr(ln, 'location_id', None),
            'segments': json.loads(ln.segments_json) if ln.segments_json else None,
        })
    return out


def account_register(db, models, ledger_id, account_id, *, limit=400):
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctGLAccount = models['AcctGLAccount']
    acct = AcctGLAccount.query.filter_by(id=account_id, ledger_id=ledger_id).first()
    if not acct:
        raise ValueError('Account not found')
    posted = AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Posted').all()
    batch_ids = [b.id for b in posted]
    if not batch_ids:
        return {'account': serialize_account(acct), 'transactions': [], 'totals': {'debit': 0, 'credit': 0, 'balance': 0}}
    lines = (
        AcctJournalLine.query.filter(
            AcctJournalLine.batch_id.in_(batch_ids),
            AcctJournalLine.account_id == account_id,
        )
        .order_by(AcctJournalLine.id.desc())
        .limit(limit)
        .all()
    )
    batch_map = {b.id: b for b in posted}
    txns = []
    total_d = 0.0
    total_c = 0.0
    for ln in lines:
        b = batch_map.get(ln.batch_id)
        total_d += float(ln.debit or 0)
        total_c += float(ln.credit or 0)
        txns.append({
            'batch_id': ln.batch_id,
            'batch_number': b.batch_number if b else '',
            'batch_date': b.batch_date.isoformat() if b and b.batch_date else None,
            'source': b.source if b else '',
            'line_description': ln.description,
            'reference': ln.reference,
            'debit': ln.debit,
            'credit': ln.credit,
            'project_id': ln.project_id,
        })
    return {
        'account': serialize_account(acct),
        'transactions': txns,
        'totals': {
            'debit': round(total_d, 2),
            'credit': round(total_c, 2),
            'balance': round(total_d - total_c, 2),
        },
    }


def replace_batch_lines(db, AcctJournalLine, batch_id, lines):
    AcctJournalLine.query.filter_by(batch_id=batch_id).delete()
    db.session.flush()
    for i, ln in enumerate(lines or [], start=1):
        db.session.add(AcctJournalLine(
            batch_id=batch_id,
            line_number=i,
            account_id=int(ln['account_id']),
            description=(ln.get('description') or '')[:300],
            debit=float(ln.get('debit') or 0),
            credit=float(ln.get('credit') or 0),
            project_id=ln.get('project_id'),
            reference=(ln.get('reference') or '')[:80],
        ))


def update_open_batch(db, models, batch, body, AcctLedger):
    if batch.status != 'Open':
        raise ValueError('Only open batches can be edited')
    from datetime import date as date_cls
    if body.get('description') is not None:
        batch.description = str(body['description'])[:300]
    if body.get('batch_date'):
        batch.batch_date = date_cls.fromisoformat(body['batch_date'])
    if body.get('source'):
        batch.source = str(body['source'])[:40]
    ledger = AcctLedger.query.get(batch.ledger_id)
    if ledger and batch.batch_date:
        assert_period_open(ledger, batch.batch_date)
    if 'lines' in body:
        replace_batch_lines(db, models['AcctJournalLine'], batch.id, body['lines'])
    return batch
