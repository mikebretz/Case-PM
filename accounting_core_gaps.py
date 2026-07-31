"""Final gap closure — imports, reopen, schedules, cash app depth, dunning letters, remediation."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime

from accounting_enforcement import merge_optional_fields
from accounting_platform import set_fiscal_period_status, write_audit


def log_field_changes(db, models, ledger_id, *, user_id, entity_type, entity_id, before: dict, after: dict):
    changed = {k: {'from': before.get(k), 'to': after.get(k)} for k in after if before.get(k) != after.get(k)}
    if not changed:
        return
    write_audit(
        db, models, ledger_id, user_id=user_id,
        action='field_update', entity_type=entity_type, entity_id=entity_id,
        details={'changes': changed},
    )


def import_journal_csv(db, models, ledger_id, csv_text, user_id=None):
    from accounting_persistence import next_batch_number, post_journal_batch
    from accounting_enforcement import posting_context
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctGLAccount = models['AcctGLAccount']
    AcctLedger = models['AcctLedger']
    ledger = AcctLedger.query.get(ledger_id)
    reader = csv.DictReader(io.StringIO(csv_text))
    batches_created = 0
    by_batch = {}
    for row in reader:
        bkey = row.get('batch_key') or row.get('batch_number') or 'IMPORT-1'
        by_batch.setdefault(bkey, []).append(row)
    for bkey, rows in by_batch.items():
        batch = AcctJournalBatch(
            ledger_id=ledger_id,
            batch_number=next_batch_number(AcctJournalBatch, ledger_id),
            source=(rows[0].get('source') or 'GL-IMP')[:40],
            description=f'Import {bkey}'[:300],
            batch_date=date.today(),
            status='Open',
            created_by_id=user_id,
        )
        db.session.add(batch)
        db.session.flush()
        for i, row in enumerate(rows, start=1):
            num = (row.get('account_number') or '').strip()
            acct = AcctGLAccount.query.filter_by(ledger_id=ledger_id, account_number=num).first()
            if not acct:
                continue
            segs = row.get('segments')
            db.session.add(AcctJournalLine(
                batch_id=batch.id,
                line_number=i,
                account_id=acct.id,
                description=(row.get('description') or '')[:300],
                debit=float(row.get('debit') or 0),
                credit=float(row.get('credit') or 0),
                location_id=int(row['location_id']) if row.get('location_id') else None,
                segments_json=json.dumps({'segments': segs.split('-')}) if segs else None,
            ))
        post_journal_batch(db, batch, AcctJournalLine, ledger=ledger, models=models, user_id=user_id)
        batches_created += 1
    return {'batches_created': batches_created}


def import_open_ap_csv(db, models, ledger_id, csv_text):
    AcctAPDocument = models['AcctAPDocument']
    AcctVendor = models['AcctVendor']
    created = 0
    for row in csv.DictReader(io.StringIO(csv_text)):
        vcode = (row.get('vendor_code') or '').strip().upper()
        v = AcctVendor.query.filter_by(ledger_id=ledger_id, code=vcode).first()
        if not v:
            continue
        doc = AcctAPDocument(
            ledger_id=ledger_id,
            vendor_id=v.id,
            document_number=(row.get('document_number') or f'IMP-{created + 1}')[:40],
            document_type='Invoice',
            document_date=date.today(),
            due_date=date.today(),
            amount=float(row.get('amount') or 0),
            gross_amount=float(row.get('amount') or 0),
            status='Open',
            currency_code=(row.get('currency_code') or 'USD')[:3],
            fx_rate=float(row.get('fx_rate') or 1),
        )
        if row.get('location_id'):
            doc.details_json = json.dumps({'location_id': int(row['location_id'])})
        db.session.add(doc)
        created += 1
    db.session.flush()
    return {'invoices_created': created}


def import_open_ar_csv(db, models, ledger_id, csv_text):
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    created = 0
    for row in csv.DictReader(io.StringIO(csv_text)):
        ccode = (row.get('customer_code') or '').strip().upper()
        c = AcctCustomer.query.filter_by(ledger_id=ledger_id, code=ccode).first()
        if not c:
            continue
        doc = AcctARDocument(
            ledger_id=ledger_id,
            customer_id=c.id,
            document_number=(row.get('document_number') or f'IMP-AR-{created + 1}')[:40],
            document_type='Invoice',
            document_date=date.today(),
            due_date=date.today(),
            amount=float(row.get('amount') or 0),
            status='Open',
            currency_code=(row.get('currency_code') or 'USD')[:3],
            fx_rate=float(row.get('fx_rate') or 1),
        )
        if row.get('location_id'):
            doc.details_json = json.dumps({'location_id': int(row['location_id'])})
        db.session.add(doc)
        created += 1
    db.session.flush()
    return {'invoices_created': created}


def year_end_reopen(db, models, ledger_id, fiscal_year, user_id=None):
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    fy = int(fiscal_year)
    reopened = []
    for p in AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id, fiscal_year=fy, status='Closed').all():
        set_fiscal_period_status(db, models, ledger_id, p.id, 'Open')
        reopened.append(p.period_key)
    write_audit(db, models, ledger_id, user_id=user_id, action='year_end_reopen', details={'fiscal_year': fy, 'periods': reopened})
    return {'fiscal_year': fy, 'reopened': reopened}


def integrity_remediate(db, models, ledger_id, user_id=None):
    """Delete empty open batches; flag unbalanced for manual fix."""
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    removed = []
    flagged = []
    for b in AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Open').all():
        lines = AcctJournalLine.query.filter_by(batch_id=b.id).all()
        if not lines:
            db.session.delete(b)
            removed.append(b.batch_number)
            continue
        td = sum(float(ln.debit or 0) for ln in lines)
        tc = sum(float(ln.credit or 0) for ln in lines)
        if abs(td - tc) > 0.02:
            flagged.append({'batch_id': b.id, 'batch_number': b.batch_number, 'diff': round(td - tc, 2)})
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='integrity_remediate', details={'removed': removed, 'flagged': flagged})
    return {'removed_empty_batches': removed, 'unbalanced_flagged': flagged}


def posting_schedule_dashboard(db, models, ledger_id):
    from accounting_gl_extended import run_due_recurring_schedules
    AcctGLRecurringJournal = models['AcctGLRecurringJournal']
    AcctAPRecurringPayable = models['AcctAPRecurringPayable']
    AcctARRecurringInvoice = models['AcctARRecurringInvoice']
    today = date.today()
    gl_due = [r for r in AcctGLRecurringJournal.query.filter_by(ledger_id=ledger_id, is_active=True).all()
              if r.next_run_date and r.next_run_date <= today]
    ap_due = [r for r in AcctAPRecurringPayable.query.filter_by(ledger_id=ledger_id, is_active=True).all()
              if r.next_run_date and r.next_run_date <= today]
    ar_due = [r for r in AcctARRecurringInvoice.query.filter_by(ledger_id=ledger_id, is_active=True).all()
              if r.next_run_date and r.next_run_date <= today]
    return {
        'gl_recurring_due': len(gl_due),
        'ap_recurring_due': len(ap_due),
        'ar_recurring_due': len(ar_due),
        'items': {
            'gl': [{'id': r.id, 'code': r.code, 'next_run_date': r.next_run_date.isoformat() if r.next_run_date else None} for r in gl_due],
            'ap': [{'id': r.id, 'vendor_id': r.vendor_id} for r in ap_due],
            'ar': [{'id': r.id, 'customer_id': r.customer_id} for r in ar_due],
        },
    }


def lock_budget(db, models, ledger_id, budget_id, locked=True):
    AcctGLBudget = models['AcctGLBudget']
    b = AcctGLBudget.query.filter_by(id=int(budget_id), ledger_id=ledger_id).first()
    if not b:
        raise ValueError('Budget not found')
    b.status = 'Locked' if locked else 'Active'
    db.session.flush()
    return b


def save_report_layout(db, models, ledger_id, body, user_id=None):
    AcctReportDefinition = models['AcctReportDefinition']
    row = AcctReportDefinition(
        ledger_id=ledger_id,
        name=(body.get('name') or 'Custom layout')[:120],
        report_type=(body.get('report_type') or 'trial_balance')[:40],
        filters_json=json.dumps(body.get('filters') or {}),
        columns_json=json.dumps(body.get('columns') or []),
        created_by_id=user_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def list_report_layouts(models, ledger_id):
    AcctReportDefinition = models['AcctReportDefinition']
    rows = AcctReportDefinition.query.filter_by(ledger_id=ledger_id).order_by(AcctReportDefinition.id.desc()).limit(50).all()
    return {'layouts': [{
        'id': r.id, 'name': r.name, 'report_type': r.report_type,
        'filters': json.loads(r.filters_json or '{}') if r.filters_json else {},
        'columns': json.loads(r.columns_json or '[]') if r.columns_json else [],
    } for r in rows]}


def update_screen_permissions(ledger, body):
    from accounting_gl_service import _parse_settings
    import json as _json
    settings = _parse_settings(ledger)
    if isinstance(body.get('permissions'), dict) and body['permissions']:
        settings['screen_permissions'] = body['permissions']
        ledger.settings_json = _json.dumps(settings)
        return settings['screen_permissions']
    perms = settings.get('screen_permissions') or {}
    role = (body.get('role_key') or 'accounting_user')[:40]
    screen = (body.get('screen') or 'gl')[:40]
    perms.setdefault(role, {})[screen] = body.get('access') or 'full'
    settings['screen_permissions'] = perms
    ledger.settings_json = _json.dumps(settings)
    return perms


def screen_permissions(ledger):
    from accounting_gl_service import _parse_settings
    settings = _parse_settings(ledger)
    return {'permissions': settings.get('screen_permissions') or {}}


def patch_customer_optional(db, models, ledger_id, customer_id, body, user_id=None):
    AcctCustomer = models['AcctCustomer']
    c = AcctCustomer.query.filter_by(id=int(customer_id), ledger_id=ledger_id).first()
    if not c:
        raise ValueError('Customer not found')
    before = {'name': c.name, 'terms': c.terms}
    if 'optional_fields' in body:
        c.details_json = merge_optional_fields(c.details_json, 'customer', body['optional_fields'], models, ledger_id)
    if body.get('terms'):
        c.terms = str(body['terms'])[:40]
    after = {'name': c.name, 'terms': c.terms}
    log_field_changes(db, models, ledger_id, user_id=user_id, entity_type='customer', entity_id=c.id, before=before, after=after)
    db.session.flush()
    return c


def dunning_letter_html(db, models, ledger_id, customer_id, level=1):
    from accounting_ar_extended import customer_statement
    from accounting_ar_extended import serialize_customer_extended
    stmt = customer_statement(db, models, ledger_id, customer_id)
    c = serialize_customer_extended(models['AcctCustomer'].query.get(int(customer_id)))
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Dunning L{level}</title>
    <style>body{{font-family:Georgia,serif;padding:40px;color:#111}} .amount{{font-size:1.4em;font-weight:bold}}</style></head>
    <body><p>{date.today().isoformat()}</p>
    <p>{c.get("name","")}<br>{c.get("code","")}</p>
    <p><strong>Payment reminder — level {level}</strong></p>
    <p>Our records show an open balance of <span class="amount">${stmt.get("open_balance",0):,.2f}</span>.</p>
    <p>Please remit payment promptly. Thank you.</p>
    <script>window.onload=function(){{window.print()}}</script></body></html>'''
