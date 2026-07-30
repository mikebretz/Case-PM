"""G/L consolidation — multi-entity ledgers, roll-up trial balance, elimination entries."""
from __future__ import annotations

import json
from datetime import date, datetime

from accounting_persistence import (
    next_batch_number,
    post_journal_batch,
    seed_chart_of_accounts,
    trial_balance,
)


def serialize_ledger(ledger, *, child_count=0):
    return {
        'id': ledger.id,
        'code': ledger.code,
        'name': ledger.name,
        'base_currency': ledger.base_currency,
        'parent_ledger_id': ledger.parent_ledger_id,
        'is_active': ledger.is_active,
        'child_count': child_count,
    }


def ledger_tree(AcctLedger):
    rows = AcctLedger.query.filter_by(is_active=True).order_by(AcctLedger.code).all()
    by_parent = {}
    for r in rows:
        by_parent.setdefault(r.parent_ledger_id, []).append(r)
    children = {r.id: len(by_parent.get(r.id, [])) for r in rows}

    def walk(parent_id):
        out = []
        for r in by_parent.get(parent_id, []):
            out.append({**serialize_ledger(r, child_count=children.get(r.id, 0)), 'children': walk(r.id)})
        return out

    roots = [r for r in rows if not r.parent_ledger_id]
    if not roots:
        main = AcctLedger.query.filter_by(code='MAIN').first()
        if main:
            roots = [main]
    return {
        'ledgers': [serialize_ledger(r, child_count=children.get(r.id, 0)) for r in rows],
        'tree': [{'ledger': serialize_ledger(r, child_count=children.get(r.id, 0)), 'children': walk(r.id)} for r in roots],
    }


def create_subsidiary_ledger(db, models, parent_ledger_id, body):
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    parent = AcctLedger.query.get(int(parent_ledger_id))
    if not parent:
        raise ValueError('Parent ledger not found')
    code = (body.get('code') or '').strip().upper()
    name = (body.get('name') or '').strip()
    if not code or not name:
        raise ValueError('code and name required')
    if AcctLedger.query.filter_by(code=code).first():
        raise ValueError('Ledger code already exists')
    child = AcctLedger(
        code=code,
        name=name,
        base_currency=body.get('base_currency') or parent.base_currency,
        fiscal_year_end_month=parent.fiscal_year_end_month,
        parent_ledger_id=parent.id,
        settings_json=parent.settings_json,
        is_active=True,
    )
    db.session.add(child)
    db.session.flush()
    seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, child)
    return child


def subsidiary_ledger_ids(AcctLedger, parent_ledger_id):
    """All direct and nested children of parent."""
    all_rows = AcctLedger.query.filter_by(is_active=True).all()
    by_parent = {}
    for r in all_rows:
        by_parent.setdefault(r.parent_ledger_id, []).append(r.id)

    out = []

    def collect(pid):
        for cid in by_parent.get(pid, []):
            out.append(cid)
            collect(cid)

    collect(int(parent_ledger_id))
    return out


def consolidated_trial_balance(db, models, parent_ledger_id, *, include_parent=True, child_ids=None):
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']

    parent = AcctLedger.query.get(int(parent_ledger_id))
    if not parent:
        raise ValueError('Parent ledger not found')

    if child_ids is None:
        child_ids = subsidiary_ledger_ids(AcctLedger, parent.id)
    else:
        child_ids = [int(x) for x in child_ids]

    ledger_ids = list(child_ids)
    if include_parent:
        ledger_ids.insert(0, parent.id)

    by_number = {}
    ledger_labels = {}
    for lid in ledger_ids:
        led = AcctLedger.query.get(lid)
        if not led:
            continue
        ledger_labels[lid] = f'{led.code} — {led.name}'
        rows = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, lid)
        for row in rows:
            num = row['account_number']
            if num not in by_number:
                by_number[num] = {
                    'account_number': num,
                    'description': row['description'],
                    'account_type': row['account_type'],
                    'debit': 0.0,
                    'credit': 0.0,
                    'balance': 0.0,
                    'by_ledger': {},
                }
            by_number[num]['debit'] += float(row['debit'] or 0)
            by_number[num]['credit'] += float(row['credit'] or 0)
            by_number[num]['balance'] += float(row['balance'] or 0)
            by_number[num]['by_ledger'][str(lid)] = {
                'ledger_id': lid,
                'label': ledger_labels[lid],
                'debit': row['debit'],
                'credit': row['credit'],
                'balance': row['balance'],
            }

    rows = []
    for num in sorted(by_number.keys()):
        r = by_number[num]
        rows.append({
            **r,
            'debit': round(r['debit'], 2),
            'credit': round(r['credit'], 2),
            'balance': round(r['balance'], 2),
        })
    return {
        'parent_ledger_id': parent.id,
        'parent_code': parent.code,
        'ledger_ids': ledger_ids,
        'rows': rows,
    }


def next_consolidation_run_number(AcctConsolidationRun, parent_ledger_id):
    n = AcctConsolidationRun.query.filter_by(parent_ledger_id=parent_ledger_id).count()
    return f'CON-{datetime.utcnow().strftime("%Y%m")}-{n + 1:04d}'


def create_consolidation_run(db, models, parent_ledger_id, body):
    AcctConsolidationRun = models['AcctConsolidationRun']
    parent_ledger_id = int(parent_ledger_id)
    period_end = body.get('period_end')
    if period_end:
        period_end = date.fromisoformat(period_end) if isinstance(period_end, str) else period_end
    else:
        period_end = date.today()
    child_ids = body.get('child_ledger_ids')
    if child_ids is not None:
        child_ids = [int(x) for x in child_ids]
    details = {
        'child_ledger_ids': child_ids,
        'include_parent': bool(body.get('include_parent', True)),
        'notes': (body.get('notes') or '')[:500],
    }
    run = AcctConsolidationRun(
        parent_ledger_id=parent_ledger_id,
        run_number=body.get('run_number') or next_consolidation_run_number(AcctConsolidationRun, parent_ledger_id),
        period_end=period_end,
        status='Open',
        details_json=json.dumps(details),
    )
    db.session.add(run)
    db.session.flush()
    return run


def serialize_consolidation_run(run):
    try:
        details = json.loads(run.details_json or '{}') if run.details_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        details = {}
    return {
        'id': run.id,
        'parent_ledger_id': run.parent_ledger_id,
        'run_number': run.run_number,
        'period_end': run.period_end.isoformat() if run.period_end else None,
        'status': run.status,
        'elimination_batch_id': run.elimination_batch_id,
        'rollup_batch_id': run.rollup_batch_id,
        'posted_at': run.posted_at.isoformat() if run.posted_at else None,
        'details': details,
    }


def post_consolidation_eliminations(db, models, run, body, user_id=None):
    """Post elimination journal on parent ledger; marks run Posted."""
    if run.status != 'Open':
        raise ValueError('Consolidation run is not open')
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']

    parent = AcctLedger.query.get(run.parent_ledger_id)
    if not parent:
        raise ValueError('Parent ledger not found')

    lines_in = body.get('lines') or []
    if not lines_in:
        raise ValueError('At least one elimination line required')

    je_lines = []
    for i, ln in enumerate(lines_in, start=1):
        acct_id = ln.get('account_id')
        acct_num = ln.get('account_number')
        if not acct_id and acct_num:
            acct = AcctGLAccount.query.filter_by(ledger_id=parent.id, account_number=str(acct_num)).first()
            if acct:
                acct_id = acct.id
        if not acct_id:
            raise ValueError(f'Account not found for line {i}')
        debit = round(float(ln.get('debit') or 0), 2)
        credit = round(float(ln.get('credit') or 0), 2)
        if debit == 0 and credit == 0:
            continue
        je_lines.append({
            'account_id': int(acct_id),
            'description': (ln.get('description') or 'Consolidation elimination')[:300],
            'debit': debit,
            'credit': credit,
        })
    if not je_lines:
        raise ValueError('No valid elimination lines')

    batch = AcctJournalBatch(
        ledger_id=parent.id,
        batch_number=next_batch_number(AcctJournalBatch, parent.id),
        source='CON-ELIM',
        description=f'Consolidation eliminations {run.run_number}',
        batch_date=run.period_end or date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    for i, ln in enumerate(je_lines, start=1):
        db.session.add(AcctJournalLine(
            batch_id=batch.id,
            line_number=i,
            account_id=ln['account_id'],
            description=ln['description'],
            debit=ln['debit'],
            credit=ln['credit'],
        ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=parent)
    run.elimination_batch_id = batch.id
    run.status = 'Posted'
    run.posted_at = datetime.utcnow()
    db.session.flush()
    return {'elimination_batch_id': batch.id, 'run_id': run.id}
