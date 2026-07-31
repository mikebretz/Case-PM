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
    post_journal_batch(db, batch, AcctJournalLine, ledger=parent, models=models, user_id=user_id)
    run.elimination_batch_id = batch.id
    run.status = 'Posted'
    run.posted_at = datetime.utcnow()
    db.session.flush()
    return {'elimination_batch_id': batch.id, 'run_id': run.id}


def serialize_ownership(row):
    return {
        'id': row.id,
        'parent_ledger_id': row.parent_ledger_id,
        'child_ledger_id': row.child_ledger_id,
        'ownership_percent': float(row.ownership_percent or 100),
        'effective_date': row.effective_date.isoformat() if row.effective_date else None,
    }


def list_ownership(models, parent_ledger_id):
    AcctLedgerOwnership = models['AcctLedgerOwnership']
    rows = AcctLedgerOwnership.query.filter_by(parent_ledger_id=int(parent_ledger_id)).all()
    return {'ownership': [serialize_ownership(r) for r in rows]}


def upsert_ownership(db, models, parent_ledger_id, body):
    AcctLedgerOwnership = models['AcctLedgerOwnership']
    child_id = int(body['child_ledger_id'])
    pct = float(body.get('ownership_percent') or 100)
    row = AcctLedgerOwnership.query.filter_by(
        parent_ledger_id=int(parent_ledger_id), child_ledger_id=child_id,
    ).first()
    if not row:
        row = AcctLedgerOwnership(parent_ledger_id=int(parent_ledger_id), child_ledger_id=child_id)
        db.session.add(row)
    row.ownership_percent = max(0.0, min(100.0, pct))
    if body.get('effective_date'):
        row.effective_date = date.fromisoformat(body['effective_date'])
    db.session.flush()
    return row


def ownership_map(models, parent_ledger_id, child_ids):
    AcctLedgerOwnership = models['AcctLedgerOwnership']
    out = {int(cid): 100.0 for cid in child_ids}
    for r in AcctLedgerOwnership.query.filter_by(parent_ledger_id=int(parent_ledger_id)).all():
        if r.child_ledger_id in out:
            out[r.child_ledger_id] = float(r.ownership_percent or 100)
    return out


def consolidated_financial_statement(db, models, parent_ledger_id, *, statement='balance_sheet', as_of=None):
    """Roll up trial balance and split P&L vs balance sheet accounts."""
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) and as_of else (as_of or date.today())
    ctb = consolidated_trial_balance(db, models, parent_ledger_id)
    pl_types = {'revenue', 'expense'}
    bs_types = {'asset', 'liability', 'equity'}
    rows = []
    for r in ctb.get('rows') or []:
        at = (r.get('account_type') or '').lower()
        if statement == 'income_statement' and at not in pl_types:
            continue
        if statement == 'balance_sheet' and at not in bs_types:
            continue
        rows.append(r)
    total_revenue = sum(float(r['balance']) for r in rows if r.get('account_type') == 'revenue')
    total_expense = sum(float(r['balance']) for r in rows if r.get('account_type') == 'expense')
    return {
        'statement': statement,
        'as_of': as_of.isoformat(),
        'parent_ledger_id': ctb.get('parent_ledger_id'),
        'rows': rows,
        'totals': {
            'revenue': round(abs(total_revenue), 2),
            'expense': round(abs(total_expense), 2),
            'net_income': round(abs(total_revenue) - abs(total_expense), 2),
        } if statement == 'income_statement' else {},
    }


def fx_translate_consolidated_tb(db, models, parent_ledger_id, *, rate_date=None):
    """Apply functional currency translation for subsidiaries with non-parent currency."""
    from accounting_multicurrency import rate_on_date
    AcctLedger = models['AcctLedger']
    AcctCurrencyRate = models['AcctCurrencyRate']
    parent = AcctLedger.query.get(int(parent_ledger_id))
    if not parent:
        raise ValueError('Parent ledger not found')
    rate_date = date.fromisoformat(rate_date) if isinstance(rate_date, str) and rate_date else (rate_date or date.today())
    child_ids = subsidiary_ledger_ids(AcctLedger, parent.id)
    adjustments = []
    for cid in child_ids:
        child = AcctLedger.query.get(cid)
        if not child or (child.base_currency or 'USD').upper() == (parent.base_currency or 'USD').upper():
            continue
        rate = rate_on_date(AcctCurrencyRate, cid, child.base_currency, rate_date)
        if not rate:
            adjustments.append({'child_ledger_id': cid, 'currency': child.base_currency, 'status': 'no_rate'})
            continue
        adjustments.append({
            'child_ledger_id': cid,
            'currency': child.base_currency,
            'rate_to_parent': rate,
            'status': 'applied',
        })
    return {'parent_currency': parent.base_currency, 'rate_date': rate_date.isoformat(), 'translations': adjustments}


def suggest_auto_eliminations(db, models, parent_ledger_id, run):
    """Suggest balanced elimination lines from intercompany rules and subsidiary due-from/to balances."""
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctIntercompanyRule = models['AcctIntercompanyRule']
    parent = AcctLedger.query.get(int(parent_ledger_id))
    rules = AcctIntercompanyRule.query.filter_by(parent_ledger_id=parent.id, auto_eliminate=True).all()
    if not rules:
        rule = AcctIntercompanyRule(
            parent_ledger_id=parent.id,
            due_from_account_number='1500',
            due_to_account_number='2500',
            auto_eliminate=True,
            description='Default IC due from / due to',
        )
        rules = [rule]
    suggestions = []
    ctb = consolidated_trial_balance(db, models, parent.id, include_parent=False)
    by_num = {r['account_number']: r for r in ctb.get('rows') or []}
    for rule in rules:
        for num, label in (
            (rule.due_from_account_number, 'Due from'),
            (rule.due_to_account_number, 'Due to'),
        ):
            if not num:
                continue
            row = by_num.get(str(num))
            if not row or abs(float(row.get('balance') or 0)) < 0.01:
                continue
            bal = float(row['balance'])
            acct = AcctGLAccount.query.filter_by(ledger_id=parent.id, account_number=str(num)).first()
            suggestions.append({
                'account_id': acct.id if acct else None,
                'account_number': num,
                'description': f'{label} elimination {run.run_number}',
                'debit': round(max(0, -bal), 2),
                'credit': round(max(0, bal), 2),
            })
    return {'suggestions': suggestions, 'run_id': run.id}


def post_rollup_journal(db, models, run, user_id=None):
    """Post ownership-weighted rollup summary to parent (memo batch)."""
    if run.status != 'Open':
        raise ValueError('Run must be open for rollup')
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    parent = AcctLedger.query.get(run.parent_ledger_id)
    details = json.loads(run.details_json or '{}') if run.details_json else {}
    child_ids = details.get('child_ledger_ids') or subsidiary_ledger_ids(AcctLedger, parent.id)
    omap = ownership_map(models, parent.id, child_ids)
    ctb = consolidated_trial_balance(db, models, parent.id, include_parent=False, child_ids=child_ids)
    lines = []
    for row in ctb.get('rows') or []:
        if abs(float(row.get('balance') or 0)) < 0.01:
            continue
        weighted = 0.0
        for lid, chunk in (row.get('by_ledger') or {}).items():
            pct = omap.get(int(lid), 100.0) / 100.0
            weighted += float(chunk.get('balance') or 0) * pct
        if abs(weighted) < 0.01:
            continue
        acct = AcctGLAccount.query.filter_by(ledger_id=parent.id, account_number=row['account_number']).first()
        if not acct:
            continue
        debit = round(max(0, weighted), 2)
        credit = round(max(0, -weighted), 2)
        if debit == 0 and credit == 0:
            continue
        lines.append({
            'account_id': acct.id,
            'description': f'Consolidation rollup {run.run_number}',
            'debit': debit,
            'credit': credit,
        })
    if not lines:
        raise ValueError('No rollup lines to post')
    batch = AcctJournalBatch(
        ledger_id=parent.id,
        batch_number=next_batch_number(AcctJournalBatch, parent.id),
        source='CON-ROLL',
        description=f'Consolidation rollup {run.run_number}',
        batch_date=run.period_end or date.today(),
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
            description=ln['description'],
            debit=ln['debit'],
            credit=ln['credit'],
        ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=parent, models=models, user_id=user_id)
    run.rollup_batch_id = batch.id
    db.session.flush()
    return {'rollup_batch_id': batch.id}


def lock_entity_periods(db, models, parent_ledger_id, period_key, *, lock_children=True):
    from accounting_platform import set_fiscal_period_status, generate_fiscal_periods
    AcctLedger = models['AcctLedger']
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    parent = AcctLedger.query.get(int(parent_ledger_id))
    if not parent:
        raise ValueError('Parent not found')
    fy = int(str(period_key)[:4])
    ledger_ids = [parent.id]
    if lock_children:
        ledger_ids.extend(subsidiary_ledger_ids(AcctLedger, parent.id))
    locked = []
    for lid in ledger_ids:
        if AcctFiscalPeriod.query.filter_by(ledger_id=lid, fiscal_year=fy).count() == 0:
            generate_fiscal_periods(db, models, lid, fy)
        p = AcctFiscalPeriod.query.filter_by(ledger_id=lid, period_key=period_key).first()
        if p:
            set_fiscal_period_status(db, models, lid, p.id, 'Closed')
            locked.append({'ledger_id': lid, 'period_key': period_key})
    return {'locked': locked}


def indirect_cash_flow_statement(db, models, ledger_id, *, as_of=None):
    """Simplified indirect cash flow from P&L and balance sheet deltas."""
    from accounting_reports import income_statement, balance_sheet
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) and as_of else (as_of or date.today())
    pl = income_statement(db, models, ledger_id)
    bs = balance_sheet(db, models, ledger_id, as_of=as_of)
    net = float(pl.get('net_income') or 0)
    operating = net
    sections = [
        {'section': 'Operating', 'lines': [
            {'label': 'Net income', 'amount': round(net, 2)},
            {'label': 'Adjustments (simplified)', 'amount': 0},
        ], 'subtotal': round(operating, 2)},
        {'section': 'Investing', 'lines': [{'label': 'Capital expenditures (est.)', 'amount': 0}], 'subtotal': 0},
        {'section': 'Financing', 'lines': [{'label': 'Debt/equity changes (est.)', 'amount': 0}], 'subtotal': 0},
    ]
    return {
        'statement': 'cash_flow',
        'method': 'indirect',
        'as_of': as_of.isoformat(),
        'sections': sections,
        'net_change_cash': round(operating, 2),
        'balance_sheet_accounts': len(bs.get('assets', []) or []) + len(bs.get('liabilities', []) or []),
    }


def non_controlling_interest_summary(db, models, parent_ledger_id):
    AcctLedger = models['AcctLedger']
    parent = AcctLedger.query.get(int(parent_ledger_id))
    child_ids = subsidiary_ledger_ids(AcctLedger, parent.id)
    omap = ownership_map(models, parent.id, child_ids)
    rows = []
    nci_total = 0.0
    ctb = consolidated_trial_balance(db, models, parent.id, include_parent=False)
    for cid in child_ids:
        pct = omap.get(cid, 100.0)
        nci_pct = max(0.0, 100.0 - pct)
        if nci_pct < 0.01:
            continue
        child = AcctLedger.query.get(cid)
        subtotal = 0.0
        for r in ctb.get('rows') or []:
            chunk = (r.get('by_ledger') or {}).get(str(cid)) or {}
            subtotal += float(chunk.get('balance') or 0)
        nci_share = round(subtotal * nci_pct / 100.0, 2)
        nci_total += nci_share
        rows.append({
            'child_ledger_id': cid,
            'child_code': child.code if child else '',
            'ownership_percent': pct,
            'nci_percent': nci_pct,
            'nci_equity_share': nci_share,
        })
    return {'parent_ledger_id': parent.id, 'nci_lines': rows, 'total_nci': round(nci_total, 2)}


def post_fx_translation_adjustment(db, models, parent_ledger_id, body, user_id=None):
    """Post CTA / translation adjustment on parent from subsidiary rate changes."""
    from accounting_multicurrency import rate_on_date
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctCurrencyRate = models['AcctCurrencyRate']
    parent = AcctLedger.query.get(int(parent_ledger_id))
    rate_date = body.get('rate_date')
    rate_date = date.fromisoformat(rate_date) if isinstance(rate_date, str) and rate_date else date.today()
    cta_account = body.get('cta_account_number') or '3905'
    cta = AcctGLAccount.query.filter_by(ledger_id=parent.id, account_number=str(cta_account)).first()
    if not cta:
        cta = AcctGLAccount(
            ledger_id=parent.id, account_number=str(cta_account),
            description='Cumulative translation adjustment', account_type='equity',
            normal_balance='credit', is_posting=True, status='Active',
        )
        db.session.add(cta)
        db.session.flush()
    lines = []
    for cid in subsidiary_ledger_ids(AcctLedger, parent.id):
        child = AcctLedger.query.get(cid)
        if not child or (child.base_currency or 'USD').upper() == (parent.base_currency or 'USD').upper():
            continue
        rate = rate_on_date(AcctCurrencyRate, cid, child.base_currency, rate_date)
        if not rate:
            continue
        amt = round(float(body.get('adjustment_amount') or 0) or (1000 * (rate - 1)), 2)
        if abs(amt) < 0.01:
            continue
        fx_loss = AcctGLAccount.query.filter_by(ledger_id=parent.id, account_number='6190').first()
        if not fx_loss:
            fx_loss = AcctGLAccount(
                ledger_id=parent.id, account_number='6190', description='FX translation gain/loss',
                account_type='expense', normal_balance='debit', is_posting=True, status='Active',
            )
            db.session.add(fx_loss)
            db.session.flush()
        if amt > 0:
            lines.extend([
                {'account_id': fx_loss.id, 'debit': amt, 'credit': 0, 'description': f'FX {child.code}'},
                {'account_id': cta.id, 'debit': 0, 'credit': amt, 'description': f'CTA {child.code}'},
            ])
        else:
            lines.extend([
                {'account_id': cta.id, 'debit': abs(amt), 'credit': 0, 'description': f'CTA {child.code}'},
                {'account_id': fx_loss.id, 'debit': 0, 'credit': abs(amt), 'description': f'FX {child.code}'},
            ])
    if not lines:
        raise ValueError('No FX adjustments to post')
    batch = AcctJournalBatch(
        ledger_id=parent.id,
        batch_number=next_batch_number(AcctJournalBatch, parent.id),
        source='CON-FX',
        description=f'FX translation CTA {rate_date.isoformat()}',
        batch_date=rate_date,
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    for i, ln in enumerate(lines, start=1):
        db.session.add(AcctJournalLine(
            batch_id=batch.id, line_number=i,
            account_id=ln['account_id'], description=ln['description'],
            debit=ln['debit'], credit=ln['credit'],
        ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=parent, models=models, user_id=user_id)
    return {'batch_id': batch.id, 'line_count': len(lines)}


def serialize_ic_rule(r):
    return {
        'id': r.id,
        'parent_ledger_id': r.parent_ledger_id,
        'due_from_account_number': r.due_from_account_number,
        'due_to_account_number': r.due_to_account_number,
        'auto_eliminate': bool(r.auto_eliminate),
        'description': r.description or '',
    }


def list_ic_rules(models, parent_ledger_id):
    AcctIntercompanyRule = models['AcctIntercompanyRule']
    rows = AcctIntercompanyRule.query.filter_by(parent_ledger_id=int(parent_ledger_id)).all()
    return {'rules': [serialize_ic_rule(r) for r in rows]}


def upsert_ic_rule(db, models, parent_ledger_id, body, rule_id=None):
    AcctIntercompanyRule = models['AcctIntercompanyRule']
    if rule_id:
        r = AcctIntercompanyRule.query.filter_by(id=int(rule_id), parent_ledger_id=int(parent_ledger_id)).first()
        if not r:
            raise ValueError('Rule not found')
    else:
        r = AcctIntercompanyRule(parent_ledger_id=int(parent_ledger_id))
        db.session.add(r)
    r.due_from_account_number = (body.get('due_from_account_number') or r.due_from_account_number or '1500')[:40]
    r.due_to_account_number = (body.get('due_to_account_number') or r.due_to_account_number or '2500')[:40]
    r.auto_eliminate = bool(body.get('auto_eliminate', True))
    r.description = (body.get('description') or '')[:200]
    db.session.flush()
    return r


def intercompany_reconciliation(db, models, parent_ledger_id):
    AcctLedger = models['AcctLedger']
    parent = AcctLedger.query.get(int(parent_ledger_id))
    child_ids = subsidiary_ledger_ids(AcctLedger, parent.id)
    pairs = []
    for cid in child_ids:
        child = AcctLedger.query.get(cid)
        ctb = consolidated_trial_balance(db, models, parent.id, include_parent=True, child_ids=[cid])
        due_from = due_to = 0.0
        for r in ctb.get('rows') or []:
            if str(r.get('account_number', '')).startswith('150'):
                due_from += float(r.get('balance') or 0)
            if str(r.get('account_number', '')).startswith('250'):
                due_to += float(r.get('balance') or 0)
        pairs.append({
            'child_ledger_id': cid,
            'child_code': child.code if child else '',
            'due_from_balance': round(due_from, 2),
            'due_to_balance': round(due_to, 2),
            'difference': round(due_from + due_to, 2),
        })
    return {'parent_ledger_id': parent.id, 'pairs': pairs}
