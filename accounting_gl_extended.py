"""G/L depth — segments, budgets, recurring/allocation journals, intercompany, subledger tie-out."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from accounting_gl_service import assert_period_open
from accounting_persistence import next_batch_number, post_journal_batch, trial_balance


def split_account_segments(account_number: str, segment_count: int):
    """Split account number on '-' or '.' into segment slots (Sage-style)."""
    segment_count = max(1, min(10, int(segment_count or 1)))
    raw = (account_number or '').strip()
    if not raw:
        return [''] * segment_count
    parts = [p.strip() for p in raw.replace('.', '-').split('-') if p.strip()]
    while len(parts) < segment_count:
        parts.append('')
    return parts[:segment_count]


def validate_account_number_segments(account_number: str, segment_count: int):
    segs = split_account_segments(account_number, segment_count)
    if not segs[0]:
        raise ValueError('Account number must include a main segment')
    for i, s in enumerate(segs):
        if s and len(s) > 20:
            raise ValueError(f'Segment {i + 1} too long (max 20 chars)')
    return segs


def segments_payload(account_number: str, segment_count: int):
    segs = split_account_segments(account_number, segment_count)
    return {'segments': segs, 'segment_count': segment_count}


def serialize_budget(b, lines=None):
    return {
        'id': b.id,
        'name': b.name,
        'fiscal_year': b.fiscal_year,
        'status': b.status,
        'lines': lines or [],
    }


def create_budget(db, models, ledger_id, body):
    AcctGLBudget = models['AcctGLBudget']
    AcctGLBudgetLine = models['AcctGLBudgetLine']
    b = AcctGLBudget(
        ledger_id=ledger_id,
        name=(body.get('name') or 'Budget')[:80],
        fiscal_year=int(body.get('fiscal_year') or date.today().year),
        status='Active',
    )
    db.session.add(b)
    db.session.flush()
    for ln in body.get('lines') or []:
        db.session.add(AcctGLBudgetLine(
            budget_id=b.id,
            account_id=int(ln['account_id']),
            period_key=str(ln['period_key'])[:7],
            amount=round(float(ln.get('amount') or 0), 2),
        ))
    db.session.flush()
    return b


def budget_vs_actual(db, models, ledger_id, budget_id, *, period_key=None):
    AcctGLBudget = models['AcctGLBudget']
    AcctGLBudgetLine = models['AcctGLBudgetLine']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    budget = AcctGLBudget.query.filter_by(id=budget_id, ledger_id=ledger_id).first()
    if not budget:
        raise ValueError('Budget not found')
    lines = AcctGLBudgetLine.query.filter_by(budget_id=budget.id).all()
    if period_key:
        lines = [ln for ln in lines if ln.period_key == period_key]
    tb = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id)
    actual_by_acct = {r['id']: r for r in tb}
    rows = []
    for ln in lines:
        acct = AcctGLAccount.query.get(ln.account_id)
        act = actual_by_acct.get(ln.account_id, {})
        budget_amt = float(ln.amount or 0)
        actual_amt = float(act.get('balance') or 0)
        if acct and acct.account_type in ('revenue', 'expense', 'liability', 'equity'):
            actual_amt = abs(actual_amt)
        rows.append({
            'account_id': ln.account_id,
            'account_number': acct.account_number if acct else '',
            'period_key': ln.period_key,
            'budget': round(budget_amt, 2),
            'actual': round(actual_amt, 2),
            'variance': round(budget_amt - actual_amt, 2),
        })
    return {'budget': serialize_budget(budget), 'rows': rows}


def budget_grid(db, models, ledger_id, budget_id):
    """Full account × period matrix for UI grid."""
    AcctGLBudget = models['AcctGLBudget']
    AcctGLBudgetLine = models['AcctGLBudgetLine']
    AcctGLAccount = models['AcctGLAccount']
    budget = AcctGLBudget.query.filter_by(id=budget_id, ledger_id=ledger_id).first()
    if not budget:
        raise ValueError('Budget not found')
    lines = AcctGLBudgetLine.query.filter_by(budget_id=budget.id).all()
    periods = sorted({ln.period_key for ln in lines})
    if not periods:
        fy = budget.fiscal_year
        periods = [f'{fy}-{m:02d}' for m in range(1, 13)]
    accounts = {a.id: a for a in AcctGLAccount.query.filter_by(ledger_id=ledger_id).order_by(AcctGLAccount.account_number).all()}
    cell = {}
    for ln in lines:
        cell[(ln.account_id, ln.period_key)] = float(ln.amount or 0)
    acct_ids = sorted(accounts.keys())
    rows = []
    for aid in acct_ids:
        acct = accounts.get(aid)
        if not acct:
            continue
        period_amounts = {p: round(cell.get((aid, p), 0.0), 2) for p in periods}
        rows.append({
            'account_id': aid,
            'account_number': acct.account_number,
            'description': acct.description,
            'periods': period_amounts,
            'total': round(sum(period_amounts.values()), 2),
        })
    return {
        'budget': serialize_budget(budget),
        'periods': periods,
        'rows': rows,
    }


def update_budget_grid(db, models, ledger_id, budget_id, body):
    AcctGLBudget = models['AcctGLBudget']
    AcctGLBudgetLine = models['AcctGLBudgetLine']
    budget = AcctGLBudget.query.filter_by(id=budget_id, ledger_id=ledger_id).first()
    if not budget:
        raise ValueError('Budget not found')
    for cell in body.get('cells') or []:
        aid = int(cell['account_id'])
        pk = str(cell['period_key'])[:7]
        amt = round(float(cell.get('amount') or 0), 2)
        ln = AcctGLBudgetLine.query.filter_by(budget_id=budget.id, account_id=aid, period_key=pk).first()
        if ln:
            ln.amount = amt
        elif amt != 0:
            db.session.add(AcctGLBudgetLine(budget_id=budget.id, account_id=aid, period_key=pk, amount=amt))
    db.session.flush()
    return budget_grid(db, models, ledger_id, budget_id)


def serialize_recurring(r):
    try:
        lines = json.loads(r.lines_json or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        lines = []
    return {
        'id': r.id,
        'code': r.code,
        'description': r.description,
        'frequency': r.frequency,
        'next_run_date': r.next_run_date.isoformat() if r.next_run_date else None,
        'last_run_date': r.last_run_date.isoformat() if r.last_run_date else None,
        'source': r.source,
        'is_active': r.is_active,
        'lines': lines,
    }


def create_recurring_journal(db, models, ledger_id, body):
    AcctGLRecurringJournal = models['AcctGLRecurringJournal']
    lines = body.get('lines') or []
    if len(lines) < 2:
        raise ValueError('Recurring journal needs at least two lines')
    r = AcctGLRecurringJournal(
        ledger_id=ledger_id,
        code=(body.get('code') or f'RJ-{datetime.utcnow().strftime("%H%M%S")}')[:30],
        description=(body.get('description') or '')[:300],
        frequency=(body.get('frequency') or 'monthly')[:20],
        next_run_date=date.fromisoformat(body['next_run_date']) if body.get('next_run_date') else date.today(),
        source=(body.get('source') or 'GL')[:20],
        lines_json=json.dumps(lines),
        is_active=True,
    )
    db.session.add(r)
    db.session.flush()
    return r


def _advance_date(d: date, frequency: str) -> date:
    if frequency == 'weekly':
        return d + timedelta(days=7)
    return date(d.year + (1 if d.month == 12 else 0), (d.month % 12) + 1, min(d.day, 28))


def run_recurring_journal(db, models, recurring, user_id=None):
    if not recurring.is_active:
        raise ValueError('Recurring journal is inactive')
    if recurring.next_run_date and recurring.next_run_date > date.today():
        raise ValueError('Next run date is in the future')
    AcctLedger = models['AcctLedger']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    ledger = AcctLedger.query.get(recurring.ledger_id)
    try:
        lines = json.loads(recurring.lines_json or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        lines = []
    batch = AcctJournalBatch(
        ledger_id=recurring.ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, recurring.ledger_id),
        source=recurring.source or 'GL-RJ',
        description=f'Recurring {recurring.code}: {recurring.description or ""}'[:300],
        batch_date=recurring.next_run_date or date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    if ledger:
        assert_period_open(ledger, batch.batch_date)
    for i, ln in enumerate(lines, start=1):
        db.session.add(AcctJournalLine(
            batch_id=batch.id,
            line_number=i,
            account_id=int(ln['account_id']),
            description=(ln.get('description') or recurring.description or '')[:300],
            debit=float(ln.get('debit') or 0),
            credit=float(ln.get('credit') or 0),
            project_id=ln.get('project_id'),
            reference=(ln.get('reference') or recurring.code)[:80],
        ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger)
    recurring.last_run_date = batch.batch_date
    recurring.next_run_date = _advance_date(batch.batch_date, recurring.frequency or 'monthly')
    db.session.flush()
    return {'batch_id': batch.id, 'batch_number': batch.batch_number}


def serialize_allocation(t):
    try:
        lines = json.loads(t.lines_json or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        lines = []
    return {
        'id': t.id,
        'code': t.code,
        'description': t.description,
        'pool_account_id': t.pool_account_id,
        'is_active': t.is_active,
        'lines': lines,
    }


def create_allocation_template(db, models, ledger_id, body):
    AcctGLAllocationTemplate = models['AcctGLAllocationTemplate']
    lines = body.get('lines') or []
    total_pct = sum(float(ln.get('percent') or 0) for ln in lines)
    if lines and round(total_pct, 2) not in (0.0, 100.0):
        raise ValueError('Allocation line percents must total 100')
    t = AcctGLAllocationTemplate(
        ledger_id=ledger_id,
        code=(body.get('code') or 'ALLOC')[:30],
        description=(body.get('description') or '')[:300],
        pool_account_id=body.get('pool_account_id'),
        lines_json=json.dumps(lines),
        is_active=True,
    )
    db.session.add(t)
    db.session.flush()
    return t


def run_allocation(db, models, template, amount, *, batch_date=None, user_id=None):
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise ValueError('amount required')
    try:
        lines = json.loads(template.lines_json or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        lines = []
    if not lines:
        raise ValueError('Allocation template has no lines')
    AcctLedger = models['AcctLedger']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    ledger = AcctLedger.query.get(template.ledger_id)
    bd = batch_date or date.today()
    if isinstance(bd, str):
        bd = date.fromisoformat(bd)
    batch = AcctJournalBatch(
        ledger_id=template.ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, template.ledger_id),
        source='GL-ALLOC',
        description=f'Allocation {template.code}'[:300],
        batch_date=bd,
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    if ledger:
        assert_period_open(ledger, bd)
    je_lines = []
    if template.pool_account_id:
        je_lines.append({
            'account_id': int(template.pool_account_id),
            'debit': 0,
            'credit': amount,
            'description': f'Pool credit — {template.code}',
        })
    for ln in lines:
        pct = float(ln.get('percent') or 0) / 100.0
        slice_amt = round(amount * pct, 2)
        if slice_amt <= 0:
            continue
        je_lines.append({
            'account_id': int(ln['account_id']),
            'debit': slice_amt,
            'credit': 0,
            'description': (ln.get('description') or template.description or '')[:300],
        })
    total_d = sum(l['debit'] for l in je_lines)
    total_c = sum(l['credit'] for l in je_lines)
    diff = round(total_d - total_c, 2)
    if diff != 0 and je_lines:
        je_lines[0]['debit'] = round(je_lines[0]['debit'] + diff, 2)
    for i, ln in enumerate(je_lines, start=1):
        db.session.add(AcctJournalLine(
            batch_id=batch.id,
            line_number=i,
            account_id=ln['account_id'],
            description=ln['description'],
            debit=ln['debit'],
            credit=ln['credit'],
        ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger)
    db.session.flush()
    return {'batch_id': batch.id}


def serialize_intercompany(e):
    return {
        'id': e.id,
        'entry_number': e.entry_number,
        'counterparty_ledger_id': e.counterparty_ledger_id,
        'from_account_id': e.from_account_id,
        'to_account_id': e.to_account_id,
        'amount': e.amount,
        'description': e.description,
        'entry_date': e.entry_date.isoformat() if e.entry_date else None,
        'status': e.status,
        'journal_batch_id': e.journal_batch_id,
    }


def create_intercompany_entry(db, models, ledger_id, body):
    AcctIntercompanyEntry = models['AcctIntercompanyEntry']
    amt = round(float(body.get('amount') or 0), 2)
    if amt <= 0:
        raise ValueError('amount required')
    n = AcctIntercompanyEntry.query.filter_by(ledger_id=ledger_id).count()
    e = AcctIntercompanyEntry(
        ledger_id=ledger_id,
        entry_number=(body.get('entry_number') or f'IC-{n + 1:05d}')[:30],
        counterparty_ledger_id=body.get('counterparty_ledger_id'),
        from_account_id=int(body['from_account_id']),
        to_account_id=int(body['to_account_id']),
        amount=amt,
        description=(body.get('description') or 'Intercompany')[:300],
        entry_date=date.fromisoformat(body['entry_date']) if body.get('entry_date') else date.today(),
        status='Open',
    )
    db.session.add(e)
    db.session.flush()
    return e


def post_intercompany_entry(db, models, entry, user_id=None):
    if entry.status != 'Open':
        raise ValueError('Entry already posted')
    AcctLedger = models['AcctLedger']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    ledger = AcctLedger.query.get(entry.ledger_id)
    batch = AcctJournalBatch(
        ledger_id=entry.ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, entry.ledger_id),
        source='GL-IC',
        description=entry.description or entry.entry_number,
        batch_date=entry.entry_date or date.today(),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    if ledger:
        assert_period_open(ledger, batch.batch_date)
    amt = float(entry.amount or 0)
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=1, account_id=entry.from_account_id,
        description=entry.description, debit=amt, credit=0,
    ))
    db.session.add(AcctJournalLine(
        batch_id=batch.id, line_number=2, account_id=entry.to_account_id,
        description=entry.description, debit=0, credit=amt,
    ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger)
    entry.status = 'Posted'
    entry.journal_batch_id = batch.id
    db.session.flush()
    return {'journal_batch_id': batch.id}


def subledger_control_reconcile(db, models, ledger_id):
    """Compare AP/AR control G/L balances to subledger open document totals."""
    from accounting_posting import load_accounting_options, _account_by_number
    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    tb = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id)
    ap_acct = _account_by_number(AcctGLAccount, ledger_id, opts['ap_account'])
    ar_acct = _account_by_number(AcctGLAccount, ledger_id, opts['ar_account'])
    gl_ap = next((r for r in tb if r['id'] == ap_acct.id), {'balance': 0})
    gl_ar = next((r for r in tb if r['id'] == ar_acct.id), {'balance': 0})
    ap_open = 0.0
    for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id).filter(
        AcctAPDocument.status.in_(['Open', 'Partial'])
    ).all():
        ap_open += float(d.amount or 0) - float(d.amount_paid or 0)
    ar_open = 0.0
    for d in AcctARDocument.query.filter_by(ledger_id=ledger_id).filter(
        AcctARDocument.status.in_(['Open', 'Partial'])
    ).all():
        ar_open += float(d.amount or 0) - float(d.amount_paid or 0)
    return {
        'ap': {
            'gl_account': ap_acct.account_number,
            'gl_balance': gl_ap.get('balance', 0),
            'subledger_open': round(ap_open, 2),
            'difference': round(float(gl_ap.get('balance', 0)) + ap_open, 2),
        },
        'ar': {
            'gl_account': ar_acct.account_number,
            'gl_balance': gl_ar.get('balance', 0),
            'subledger_open': round(ar_open, 2),
            'difference': round(float(gl_ar.get('balance', 0)) - ar_open, 2),
        },
    }
