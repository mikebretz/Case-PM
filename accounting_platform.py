"""Platform & administration — fiscal calendar, locations, security, audit, import/export."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from calendar import monthrange

from accounting_gl_service import period_key_for_date, _parse_settings


def write_audit(db, models, ledger_id, *, user_id=None, action, entity_type=None, entity_id=None, details=None):
    AcctAuditLog = models['AcctAuditLog']
    row = AcctAuditLog(
        ledger_id=ledger_id,
        user_id=user_id,
        action=action[:40],
        entity_type=(entity_type or '')[:40],
        entity_id=entity_id,
        details_json=json.dumps(details or {})[:8000],
    )
    db.session.add(row)
    db.session.flush()
    return row


def serialize_audit(row):
    try:
        details = json.loads(row.details_json or '{}') if row.details_json else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        details = {}
    return {
        'id': row.id,
        'action': row.action,
        'entity_type': row.entity_type,
        'entity_id': row.entity_id,
        'user_id': row.user_id,
        'details': details,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }


def generate_fiscal_periods(db, models, ledger_id, fiscal_year):
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    AcctLedger = models['AcctLedger']
    ledger = AcctLedger.query.get(int(ledger_id))
    if not ledger:
        raise ValueError('Ledger not found')
    fy = int(fiscal_year)
    existing = AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id, fiscal_year=fy).count()
    if existing:
        return list_fiscal_periods(models, ledger_id, fiscal_year=fy)
    rows = []
    for m in range(1, 13):
        last = monthrange(fy, m)[1]
        start = date(fy, m, 1)
        end = date(fy, m, last)
        pk = f'{fy:04d}-{m:02d}'
        p = AcctFiscalPeriod(
            ledger_id=ledger_id,
            fiscal_year=fy,
            period_number=m,
            period_key=pk,
            start_date=start,
            end_date=end,
            status='Open',
        )
        db.session.add(p)
        rows.append(p)
    db.session.flush()
    sync_closed_periods_to_ledger(ledger, models, ledger_id)
    return {'fiscal_year': fy, 'periods': [serialize_fiscal_period(p) for p in rows]}


def serialize_fiscal_period(p):
    return {
        'id': p.id,
        'fiscal_year': p.fiscal_year,
        'period_number': p.period_number,
        'period_key': p.period_key,
        'start_date': p.start_date.isoformat() if p.start_date else None,
        'end_date': p.end_date.isoformat() if p.end_date else None,
        'status': p.status,
    }


def list_fiscal_periods(models, ledger_id, *, fiscal_year=None):
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    q = AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id)
    if fiscal_year:
        q = q.filter_by(fiscal_year=int(fiscal_year))
    rows = q.order_by(AcctFiscalPeriod.period_key).all()
    return {'periods': [serialize_fiscal_period(p) for p in rows]}


def sync_closed_periods_to_ledger(ledger, models, ledger_id):
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    closed = [
        p.period_key for p in AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id, status='Closed').all()
    ]
    settings = _parse_settings(ledger)
    settings['closed_periods'] = sorted(set(closed))
    ledger.settings_json = json.dumps(settings)


def set_fiscal_period_status(db, models, ledger_id, period_id, status):
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    AcctLedger = models['AcctLedger']
    if status not in ('Open', 'Closed'):
        raise ValueError('status must be Open or Closed')
    p = AcctFiscalPeriod.query.filter_by(id=int(period_id), ledger_id=ledger_id).first()
    if not p:
        raise ValueError('Period not found')
    p.status = status
    ledger = AcctLedger.query.get(ledger_id)
    sync_closed_periods_to_ledger(ledger, models, ledger_id)
    db.session.flush()
    return p


def serialize_location(loc):
    return {'id': loc.id, 'code': loc.code, 'name': loc.name, 'status': loc.status}


def upsert_location(db, models, ledger_id, body, loc_id=None):
    AcctLocation = models['AcctLocation']
    code = (body.get('code') or '').strip().upper()
    name = (body.get('name') or '').strip()
    if not code or not name:
        raise ValueError('code and name required')
    if loc_id:
        loc = AcctLocation.query.filter_by(id=int(loc_id), ledger_id=ledger_id).first()
        if not loc:
            raise ValueError('Location not found')
    else:
        if AcctLocation.query.filter_by(ledger_id=ledger_id, code=code).first():
            raise ValueError('Location code exists')
        loc = AcctLocation(ledger_id=ledger_id, code=code, name=name)
        db.session.add(loc)
    loc.code = code
    loc.name = name
    if body.get('status') in ('Active', 'Inactive'):
        loc.status = body['status']
    db.session.flush()
    return loc


def serialize_gl_security(row):
    return {
        'id': row.id,
        'account_id': row.account_id,
        'user_id': row.user_id,
        'role_key': row.role_key or '',
        'access_level': row.access_level,
    }


def upsert_gl_account_security(db, models, ledger_id, body):
    AcctGLAccountSecurity = models['AcctGLAccountSecurity']
    account_id = int(body['account_id'])
    access = body.get('access_level') or 'post'
    if access not in ('none', 'view', 'post'):
        raise ValueError('Invalid access_level')
    row = AcctGLAccountSecurity(
        ledger_id=ledger_id,
        account_id=account_id,
        user_id=int(body['user_id']) if body.get('user_id') else None,
        role_key=(body.get('role_key') or '')[:40] or None,
        access_level=access,
    )
    db.session.add(row)
    db.session.flush()
    return row


def check_gl_account_access(models, ledger_id, account_id, *, user_id=None, role_key=None, need='post'):
    """Return True if posting allowed (no rules = allow)."""
    AcctGLAccountSecurity = models['AcctGLAccountSecurity']
    rules = AcctGLAccountSecurity.query.filter_by(ledger_id=ledger_id, account_id=int(account_id)).all()
    if not rules:
        return True
    levels = {'none': 0, 'view': 1, 'post': 2}
    need_level = levels.get(need, 2)
    best = 0
    for r in rules:
        if r.user_id and user_id and r.user_id == int(user_id):
            best = max(best, levels.get(r.access_level, 0))
        if r.role_key and role_key and r.role_key == role_key:
            best = max(best, levels.get(r.access_level, 0))
    return best >= need_level


def serialize_optional_field(f):
    return {
        'id': f.id,
        'entity_type': f.entity_type,
        'field_key': f.field_key,
        'label': f.label,
        'field_type': f.field_type,
        'is_required': f.is_required,
        'sort_order': f.sort_order,
    }


def upsert_optional_field(db, models, ledger_id, body, field_id=None):
    AcctOptionalFieldDef = models['AcctOptionalFieldDef']
    entity_type = (body.get('entity_type') or 'vendor')[:30]
    field_key = (body.get('field_key') or '').strip()
    label = (body.get('label') or field_key)[:80]
    if not field_key:
        raise ValueError('field_key required')
    if field_id:
        f = AcctOptionalFieldDef.query.filter_by(id=int(field_id), ledger_id=ledger_id).first()
        if not f:
            raise ValueError('Field not found')
    else:
        f = AcctOptionalFieldDef(ledger_id=ledger_id, entity_type=entity_type, field_key=field_key)
        db.session.add(f)
    f.label = label
    f.entity_type = entity_type
    f.field_key = field_key
    if body.get('field_type'):
        f.field_type = str(body['field_type'])[:20]
    if 'is_required' in body:
        f.is_required = bool(body['is_required'])
    if 'sort_order' in body:
        f.sort_order = int(body['sort_order'] or 0)
    db.session.flush()
    return f


def ledger_locale_settings(ledger):
    settings = _parse_settings(ledger)
    return {
        'ui_language': settings.get('ui_language') or 'en',
        'date_format': settings.get('date_format') or 'ISO',
        'number_format': settings.get('number_format') or 'US',
    }


def update_ledger_locale(ledger, body):
    settings = _parse_settings(ledger)
    if body.get('ui_language'):
        settings['ui_language'] = str(body['ui_language'])[:10]
    if body.get('date_format'):
        settings['date_format'] = str(body['date_format'])[:20]
    if body.get('number_format'):
        settings['number_format'] = str(body['number_format'])[:20]
    ledger.settings_json = json.dumps(settings)
    return ledger_locale_settings(ledger)


def export_chart_csv(models, ledger_id):
    AcctGLAccount = models['AcctGLAccount']
    rows = AcctGLAccount.query.filter_by(ledger_id=ledger_id).order_by(AcctGLAccount.account_number).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['account_number', 'description', 'account_type', 'normal_balance', 'status', 'is_posting'])
    for a in rows:
        w.writerow([a.account_number, a.description, a.account_type, a.normal_balance, a.status, a.is_posting])
    return buf.getvalue()


def import_chart_csv(db, models, ledger_id, csv_text):
    AcctGLAccount = models['AcctGLAccount']
    reader = csv.DictReader(io.StringIO(csv_text))
    created = 0
    updated = 0
    for row in reader:
        num = (row.get('account_number') or '').strip()
        if not num:
            continue
        acct = AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_number=num).first()
        if not acct:
            acct = AcctGLAccount(
                ledger_id=ledger_id,
                account_number=num,
                description=(row.get('description') or num)[:200],
                account_type=(row.get('account_type') or 'expense')[:20],
                normal_balance=(row.get('normal_balance') or 'debit')[:10],
            )
            db.session.add(acct)
            created += 1
        else:
            if row.get('description'):
                acct.description = row['description'][:200]
            updated += 1
    db.session.flush()
    return {'created': created, 'updated': updated}


def data_integrity_check(db, models, ledger_id):
    from accounting_gl_extended import subledger_control_reconcile
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    issues = []
    batches = AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Open').all()
    for b in batches:
        lines = AcctJournalLine.query.filter_by(batch_id=b.id).all()
        td = sum(float(ln.debit or 0) for ln in lines)
        tc = sum(float(ln.credit or 0) for ln in lines)
        if abs(td - tc) > 0.02:
            issues.append({'type': 'unbalanced_batch', 'batch_id': b.id, 'batch_number': b.batch_number, 'diff': round(td - tc, 2)})
    try:
        sub = subledger_control_reconcile(db, models, ledger_id)
        for key in ('ap', 'ar'):
            block = sub.get(key) or {}
            if abs(float(block.get('difference') or 0)) > 0.02:
                issues.append({'type': f'{key}_subledger_out_of_balance', **block})
    except Exception as exc:
        issues.append({'type': 'subledger_check_failed', 'message': str(exc)})
    return {'ok': len(issues) == 0, 'issue_count': len(issues), 'issues': issues}


def financial_reporter_layout(models, ledger_id, report_type='trial_balance'):
    """Columnar financial reporter definition (export-ready)."""
    return {
        'report_type': report_type,
        'ledger_id': ledger_id,
        'columns': ['account_number', 'description', 'debit', 'credit', 'balance'],
        'filters': {'location_id': None, 'segment': None},
        'available_reports': ['trial_balance', 'income_statement', 'balance_sheet', 'cash_flow'],
    }


def run_financial_reporter(db, models, ledger_id, report_type='trial_balance', *, location_id=None, as_of=None):
    from datetime import date as date_cls
    from accounting_reports import balance_sheet, income_statement
    from accounting_persistence import trial_balance
    as_of = date_cls.fromisoformat(as_of) if isinstance(as_of, str) and as_of else (as_of or date_cls.today())
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalLine = models['AcctJournalLine']
    AcctJournalBatch = models['AcctJournalBatch']
    if report_type == 'trial_balance':
        rows = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id)
    elif report_type == 'balance_sheet':
        data = balance_sheet(db, models, ledger_id, as_of=as_of)
        rows = data.get('rows') or data.get('sections', [])
        return {'report_type': report_type, 'as_of': as_of.isoformat(), 'rows': rows}
    elif report_type == 'income_statement':
        data = income_statement(db, models, ledger_id)
        return {'report_type': report_type, **data}
    elif report_type == 'cash_flow':
        from accounting_consolidation import indirect_cash_flow_statement
        return indirect_cash_flow_statement(db, models, ledger_id, as_of=as_of)
    else:
        rows = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger_id)
    if location_id:
        loc = int(location_id)
        filtered = []
        for r in rows:
            if isinstance(r, dict) and r.get('location_id') in (None, loc):
                filtered.append(r)
        rows = filtered or rows
    return {'report_type': report_type, 'as_of': as_of.isoformat(), 'rows': rows}


def export_vendors_csv(models, ledger_id):
    AcctVendor = models['AcctVendor']
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['code', 'name', 'terms', 'email', 'tax_id', 'is_1099'])
    for v in AcctVendor.query.filter_by(ledger_id=ledger_id).order_by(AcctVendor.code).all():
        w.writerow([v.code, v.name, v.terms or '', v.email or '', v.tax_id or '', int(bool(v.is_1099))])
    return buf.getvalue()


def export_customers_csv(models, ledger_id):
    AcctCustomer = models['AcctCustomer']
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['code', 'name', 'terms', 'email', 'credit_limit'])
    for c in AcctCustomer.query.filter_by(ledger_id=ledger_id).order_by(AcctCustomer.code).all():
        w.writerow([c.code, c.name, c.terms or '', c.email or '', c.credit_limit or 0])
    return buf.getvalue()


def import_vendors_csv(db, models, ledger_id, csv_text):
    import csv
    import io
    AcctVendor = models['AcctVendor']
    created = updated = 0
    for row in csv.DictReader(io.StringIO(csv_text)):
        code = (row.get('code') or '').strip().upper()
        if not code:
            continue
        v = AcctVendor.query.filter_by(ledger_id=ledger_id, code=code).first()
        if not v:
            v = AcctVendor(ledger_id=ledger_id, code=code, name=(row.get('name') or code)[:200])
            db.session.add(v)
            created += 1
        else:
            updated += 1
        v.name = (row.get('name') or v.name)[:200]
        if row.get('terms'):
            v.terms = row['terms'][:40]
        if row.get('email'):
            v.email = row['email'][:120]
        if row.get('tax_id'):
            v.tax_id = row['tax_id'][:30]
        if row.get('is_1099') is not None:
            v.is_1099 = str(row['is_1099']).strip() in ('1', 'true', 'True', 'yes')
    db.session.flush()
    return {'created': created, 'updated': updated}


def import_customers_csv(db, models, ledger_id, csv_text):
    import csv
    import io
    AcctCustomer = models['AcctCustomer']
    created = updated = 0
    for row in csv.DictReader(io.StringIO(csv_text)):
        code = (row.get('code') or '').strip().upper()
        if not code:
            continue
        c = AcctCustomer.query.filter_by(ledger_id=ledger_id, code=code).first()
        if not c:
            c = AcctCustomer(ledger_id=ledger_id, code=code, name=(row.get('name') or code)[:200])
            db.session.add(c)
            created += 1
        else:
            updated += 1
        c.name = (row.get('name') or c.name)[:200]
        if row.get('terms'):
            c.terms = row['terms'][:40]
        if row.get('email'):
            c.email = row['email'][:120]
        if row.get('credit_limit'):
            c.credit_limit = float(row['credit_limit'] or 0)
    db.session.flush()
    return {'created': created, 'updated': updated}


def year_end_close(db, models, ledger_id, fiscal_year, user_id=None):
    """Close all periods in fiscal year and post retained earnings summary batch."""
    from accounting_persistence import next_batch_number, post_journal_batch
    from accounting_gl_service import period_key_for_date
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    fy = int(fiscal_year)
    generate_fiscal_periods(db, models, ledger_id, fy)
    periods = AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id, fiscal_year=fy).all()
    for p in periods:
        set_fiscal_period_status(db, models, ledger_id, p.id, 'Closed')
    ledger = AcctLedger.query.get(ledger_id)
    from accounting_reports import income_statement
    pl = income_statement(db, models, ledger_id)
    net = float(pl.get('net_income') or pl.get('totals', {}).get('net_income') or 0)
    re_acct = AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_number='3900').first()
    if not re_acct:
        re_acct = AcctGLAccount(
            ledger_id=ledger_id, account_number='3900', description='Retained Earnings',
            account_type='equity', normal_balance='credit', is_posting=True, status='Active',
        )
        db.session.add(re_acct)
        db.session.flush()
    batch = AcctJournalBatch(
        ledger_id=ledger_id,
        batch_number=next_batch_number(AcctJournalBatch, ledger_id),
        source='YE-CLOSE',
        description=f'Year-end close FY{fy}',
        batch_date=date(fy, 12, 31),
        status='Open',
        created_by_id=user_id,
    )
    db.session.add(batch)
    db.session.flush()
    if abs(net) > 0.01:
        if net > 0:
            db.session.add(AcctJournalLine(
                batch_id=batch.id, line_number=1, account_id=re_acct.id,
                description='Close P&L to retained earnings', debit=net, credit=0,
            ))
            rev = AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_type='revenue').first()
            if rev:
                db.session.add(AcctJournalLine(
                    batch_id=batch.id, line_number=2, account_id=rev.id,
                    description='Year-end close', debit=0, credit=net,
                ))
        else:
            db.session.add(AcctJournalLine(
                batch_id=batch.id, line_number=1, account_id=re_acct.id,
                description='Close P&L to retained earnings', debit=0, credit=abs(net),
            ))
    post_journal_batch(db, batch, AcctJournalLine, ledger=ledger, models=models, user_id=user_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='year_end_close', details={'fiscal_year': fy, 'net_income': net})
    return {'fiscal_year': fy, 'periods_closed': len(periods), 'year_end_batch_id': batch.id, 'net_income': round(net, 2)}


def security_matrix(models, ledger_id):
    AcctGLAccountSecurity = models['AcctGLAccountSecurity']
    AcctGLAccount = models['AcctGLAccount']
    rules = AcctGLAccountSecurity.query.filter_by(ledger_id=ledger_id).all()
    rows = []
    for r in rules:
        acct = AcctGLAccount.query.get(r.account_id)
        rows.append({
            **serialize_gl_security(r),
            'account_number': acct.account_number if acct else '',
            'account_description': acct.description if acct else '',
        })
    return {'rules': rows, 'roles': ['admin', 'accounting_user', 'accounting_clerk', 'viewer']}
