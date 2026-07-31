"""
Wave 9 — Tiers A–D: G702 AR sync, Sage AP push & conflicts, e-file transmit,
garnishment, WH-347 prevailing wage, compliance reminders, AR write-offs,
report schedule alerts, cron docs path, startup guard helpers.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


# --- Tier A1: G702 → AR ---

def g702_pending_ar_sync(db, models, ledger_id: int, project_id: int, PayAppProjectState) -> dict:
    from pay_app_persistence import get_pay_app_state

    AcctPostLink = models['AcctPostLink']
    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    state = state or {}
    periods = state.get('periods') or state.get('payAppPeriods') or []
    if isinstance(periods, dict):
        periods = list(periods.values())
    approved_statuses = {'Approved', 'Paid', 'Complete', 'Final Approved'}
    pending = []
    posted = []
    month_key = datetime.utcnow().strftime('%Y%m')
    for p in periods:
        if not isinstance(p, dict):
            continue
        st = (p.get('status') or '').strip()
        period_num = p.get('periodNumber') or p.get('period_number') or p.get('id')
        if not period_num:
            continue
        idem = f'G702Approved:{project_id}:{period_num}:{month_key}'
        link = AcctPostLink.query.filter_by(ledger_id=ledger_id, source_key=idem).first()
        amt = float(
            p.get('currentPaymentDue') or p.get('current_payment_due') or p.get('amountDue') or 0
        )
        row = {'period': period_num, 'status': st, 'amount': round(amt, 2), 'idempotency_key': idem}
        if link:
            posted.append({**row, 'ar_document_id': link.ar_document_id})
        elif st in approved_statuses and amt > 0:
            pending.append(row)
    return {'project_id': project_id, 'pending': pending, 'posted': posted}


def sync_g702_period_to_ar(db, models, ledger_id: int, project_id: int, period_number, user_id=None, PayAppProjectState=None, Project=None):
    from pay_app_persistence import get_pay_app_state
    from pay_app_workflow import _g702_sage_payload
    from accounting_posting import process_construction_event

    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    state = state or {}
    periods = state.get('periods') or state.get('payAppPeriods') or []
    if isinstance(periods, dict):
        periods = list(periods.values())
    period = next(
        (p for p in periods if str(p.get('periodNumber') or p.get('period_number') or p.get('id')) == str(period_number)),
        None,
    )
    if not period:
        raise ValueError('Pay application period not found')
    amt = float(
        period.get('currentPaymentDue') or period.get('current_payment_due') or period.get('amountDue') or 0
    )
    if amt <= 0:
        raise ValueError('Period has no billable amount')
    payload = _g702_sage_payload(state, period_number, amt, {})
    payload['periodNumber'] = period_number
    payload['period_number'] = period_number
    payload['force_builtin_post'] = True
    out = process_construction_event(
        'G702Approved',
        int(project_id),
        payload,
        db=db,
        models=models,
        Project=Project,
        user_id=user_id,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='g702_ar_sync', details={'period': period_number, **out})
    return out


# --- Tier A2: Sage open AP push ---

def sage_push_open_ap_live(db, models, ledger_id: int, user_id=None, limit: int = 25) -> dict:
    from sage300_web_post import post_resource

    AcctAPDocument = models['AcctAPDocument']
    AcctVendor = models['AcctVendor']
    docs = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').order_by(AcctAPDocument.id).limit(limit).all()
    results = []
    for d in docs:
        vendor = AcctVendor.query.get(d.vendor_id) if d.vendor_id else None
        payload = {
            'VendorNumber': vendor.code if vendor else '',
            'InvoiceNumber': (d.document_number or '')[:22],
            'InvoiceDate': d.document_date.isoformat() if d.document_date else date.today().isoformat(),
            'InvoiceAmount': float(d.amount or 0),
            'Description': (d.document_type or 'AP')[:60],
        }
        resp = post_resource('AP', 'APInvoices', payload)
        results.append({'document_number': d.document_number, **resp})
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('sage_sync_log') or []
    log.append({'at': datetime.utcnow().isoformat() + 'Z', 'direction': 'push', 'entity': 'open_ap', 'count': len(results)})
    settings['sage_sync_log'] = log[-100:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_open_ap_live', details={'count': len(results)})
    return {'pushed': len(results), 'results': results}


# --- Tier A3: Sage conflict review ---

def sage_vendor_conflict_review(db, models, ledger_id: int, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    AcctVendor = models['AcctVendor']
    local = AcctVendor.query.filter_by(ledger_id=ledger_id).order_by(AcctVendor.code).limit(limit).all()
    resp = get_resource('AP', 'APVendors', top=limit)
    sage_rows = []
    if resp.get('ok'):
        data = resp.get('data') or {}
        sage_rows = data.get('value') or []
    sage_by_code = {}
    for row in sage_rows:
        code = (row.get('VendorNumber') or row.get('VendorCode') or '').strip().upper()
        if code:
            sage_by_code[code] = row
    conflicts = []
    for v in local:
        code = (v.code or '').upper()
        sr = sage_by_code.get(code)
        if not sr:
            conflicts.append({'code': code, 'type': 'local_only', 'local_name': v.name, 'sage_name': None})
            continue
        sage_name = (sr.get('VendorName') or sr.get('Name') or '').strip()
        if sage_name and sage_name.lower() != (v.name or '').lower():
            conflicts.append({'code': code, 'type': 'name_mismatch', 'local_name': v.name, 'sage_name': sage_name})
    return {'conflicts': conflicts, 'local_count': len(local), 'sage_count': len(sage_rows)}


def resolve_sage_vendor_conflict(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    AcctVendor = models['AcctVendor']
    code = (body.get('code') or '').strip().upper()
    winner = (body.get('winner') or 'casepm').lower()
    v = AcctVendor.query.filter_by(ledger_id=ledger_id, code=code).first()
    if not v:
        raise ValueError('Vendor not found')
    if winner == 'sage' and body.get('sage_name'):
        v.name = str(body['sage_name'])[:200]
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_conflict_resolve', details=body)
    return {'code': code, 'name': v.name, 'winner': winner}


# --- Tier A4: Stripe readiness ---

def stripe_readiness_banner(ledger) -> dict:
    from accounting_all_chunks import stripe_runtime_config

    cfg = stripe_runtime_config(ledger)
    msgs = []
    if not cfg.get('stripe_configured'):
        msgs.append('Card processing is in demo mode until STRIPE_SECRET_KEY is set on the server.')
    elif not (os.environ.get('STRIPE_PUBLISHABLE_KEY') or os.environ.get('CASEPM_STRIPE_PUBLISHABLE_KEY')):
        msgs.append('Set STRIPE_PUBLISHABLE_KEY for Pay Now checkout pages.')
    if not (os.environ.get('STRIPE_WEBHOOK_SECRET') or '').strip():
        msgs.append('Optional: STRIPE_WEBHOOK_SECRET for automated Pay Now settlement.')
    return {'level': 'warning' if msgs else 'ok', 'messages': msgs, 'config': cfg}


# --- Tier B1: E-file transmit ---

def efile_transmit(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('compliance_efile_log') or []
    form = (body.get('form') or '1099').upper()
    tax_year = int(body.get('tax_year') or date.today().year - 1)
    entry = {
        'id': str(uuid.uuid4())[:12],
        'form': form,
        'tax_year': tax_year,
        'submitted_at': datetime.utcnow().isoformat() + 'Z',
        'status': body.get('status') or 'transmitted',
        'acknowledgment_id': body.get('acknowledgment_id') or f'ACK-{form}-{tax_year}-{len(log) + 1:04d}',
        'rejection_reason': body.get('rejection_reason'),
    }
    if entry['status'] == 'rejected' and not entry['rejection_reason']:
        entry['rejection_reason'] = 'Agency rejected — correct and retransmit.'
    log.append(entry)
    settings['compliance_efile_log'] = log[-200:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='efile_transmit', details=entry)
    return entry


def efile_transmit_log(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    return {'entries': settings.get('compliance_efile_log') or []}


def efile_retry(db, models, ledger_id: int, entry_id: str, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('compliance_efile_log') or []
    old = next((e for e in log if e.get('id') == entry_id), None)
    if not old:
        raise ValueError('Transmit record not found')
    return efile_transmit(
        db, models, ledger_id,
        {'form': old['form'], 'tax_year': old['tax_year'], 'status': 'retransmit', 'acknowledgment_id': f"{old['acknowledgment_id']}-R"},
        user_id=user_id,
    )


# --- Tier B2: Garnishment ---

def create_garnishment_order(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    AcctPayrollDeduction = models['AcctPayrollDeduction']
    emp_id = int(body['employee_id'])
    emp = AcctPayrollEmployee.query.filter_by(id=emp_id, ledger_id=ledger_id).first()
    if not emp:
        raise ValueError('Employee not found')
    case_number = (body.get('case_number') or 'CASE')[:20]
    amount = round(float(body.get('amount') or 0), 2)
    pct = body.get('percent_of_gross')
    max_per_period = round(float(body.get('max_per_period') or amount or 0), 2)
    if amount <= 0 and not pct:
        raise ValueError('amount or percent_of_gross required')
    code = f'GARN-{case_number[:10]}'
    d = AcctPayrollDeduction.query.filter_by(ledger_id=ledger_id, code=code).first()
    if not d:
        d = AcctPayrollDeduction(
            ledger_id=ledger_id,
            code=code,
            description=f'Garnishment {case_number}',
            calc_method='percent' if pct else 'fixed',
            amount=amount,
        )
        db.session.add(d)
        db.session.flush()
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    orders = settings.get('garnishment_orders') or []
    order = {
        'id': str(uuid.uuid4())[:10],
        'employee_id': emp_id,
        'case_number': case_number,
        'deduction_id': d.id,
        'amount': amount,
        'percent_of_gross': float(pct) if pct else None,
        'max_per_period': max_per_period,
        'status': 'active',
        'created_at': datetime.utcnow().isoformat() + 'Z',
    }
    orders.append(order)
    settings['garnishment_orders'] = orders[-100:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='garnishment_order', details=order)
    return order


# --- Tier B3: WH-347 prevailing wage ---

def certified_payroll_with_prevailing(db, models, ledger_id: int, project_id: int, week_ending: str, Project=None) -> dict:
    from accounting_parity_wave3 import certified_payroll_wh347

    csv_text = certified_payroll_wh347(db, models, ledger_id, project_id, week_ending)
    prevailing = None
    if Project:
        proj = Project.query.get(int(project_id))
        if proj and getattr(proj, 'details_json', None):
            try:
                prevailing = json.loads(proj.details_json).get('prevailing_wage_rate')
            except Exception:
                pass
    return {'csv': csv_text, 'prevailing_wage_rate': prevailing, 'project_id': project_id, 'week_ending': week_ending}


# --- Tier B4: Compliance calendar ---

def compliance_mark_filed(db, models, ledger_id: int, deadline_id: str, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    filed = settings.get('compliance_filed') or {}
    filed[deadline_id] = {'at': datetime.utcnow().isoformat() + 'Z', 'by': user_id}
    settings['compliance_filed'] = filed
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='compliance_mark_filed', details={'id': deadline_id})
    return {'deadline_id': deadline_id, 'filed': True}


def compliance_send_reminders(db, models, ledger_id: int, email: str, user_id=None) -> dict:
    from accounting_waves_17 import compliance_filing_calendar
    from email_notifications import send_workflow_email

    cal = compliance_filing_calendar(ledger_id)
    due_soon = [d for d in cal['deadlines'] if d.get('status') in ('due_soon', 'past_due')]
    if not email:
        raise ValueError('email required')
    lines = '\n'.join(f"- {d['form']}: {d['label']} due {d['due']} ({d['status']})" for d in due_soon[:15])
    body = f"Case PM compliance reminders ({cal['tax_year']}):\n\n{lines or 'No items due soon.'}"
    sent = send_workflow_email(email, 'Case PM — compliance filing reminders', f'<pre>{body}</pre>', body)
    write_audit(db, models, ledger_id, user_id=user_id, action='compliance_reminders', details={'count': len(due_soon), 'sent': sent})
    return {'due_count': len(due_soon), 'smtp_sent': sent}


# --- Tier C1: AR write-off with GL ---

WRITE_OFF_REASONS = ('uncollectible', 'small_balance', 'dispute_settled', 'bankruptcy', 'other')


def post_ar_write_off(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_posting import _account_by_number, _create_posted_batch, load_accounting_options

    AcctARDocument = models['AcctARDocument']
    AcctGLAccount = models['AcctGLAccount']
    doc_id = int(body['ar_document_id'])
    amt = round(float(body.get('amount') or 0), 2)
    reason = (body.get('reason') or 'other').lower()
    if reason not in WRITE_OFF_REASONS:
        raise ValueError(f'reason must be one of: {", ".join(WRITE_OFF_REASONS)}')
    if amt <= 0:
        raise ValueError('amount must be positive')
    doc = AcctARDocument.query.filter_by(id=doc_id, ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Invoice not found')
    open_amt = round(float(doc.amount or 0) - float(doc.amount_paid or 0), 2)
    if amt > open_amt + 0.01:
        raise ValueError('Write-off exceeds open balance')
    opts = load_accounting_options()
    bad_debt = _account_by_number(AcctGLAccount, ledger_id, '6100') or _account_by_number(AcctGLAccount, ledger_id, '6000')
    ar_acct = _account_by_number(AcctGLAccount, ledger_id, opts['ar_account'])
    doc.amount = round(float(doc.amount or 0) - amt, 2)
    if doc.amount <= 0.01:
        doc.status = 'Paid'
    meta = json.loads(doc.details_json or '{}') if doc.details_json else {}
    meta.setdefault('write_offs', []).append({
        'amount': amt, 'reason': reason, 'date': date.today().isoformat(), 'gl': True,
    })
    doc.details_json = json.dumps(meta)
    batch = _create_posted_batch(
        db, models,
        ledger_id=ledger_id,
        source='AR',
        description=f'AR write-off {doc.document_number} ({reason})',
        user_id=user_id,
        lines=[
            {'account_id': bad_debt.id, 'debit': amt, 'credit': 0, 'project_id': doc.project_id},
            {'account_id': ar_acct.id, 'debit': 0, 'credit': amt, 'project_id': doc.project_id},
        ],
    )
    from accounting_persistence import post_journal_batch

    post_journal_batch(db, batch, models['AcctJournalLine'], ledger=models['AcctLedger'].query.get(ledger_id), models=models, user_id=user_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='ar_write_off', entity_id=doc_id, details={'amount': amt, 'reason': reason})
    return {'ar_document_id': doc_id, 'amount': amt, 'reason': reason, 'journal_batch_id': batch.id}


# --- Tier C2: Report schedule failure tracking ---

def record_schedule_run_alert(ledger, schedule_id, status: str, detail: str = '') -> None:
    settings = _ledger_settings(ledger)
    alerts = settings.get('report_schedule_alerts') or []
    alerts.append({
        'schedule_id': schedule_id,
        'status': status,
        'detail': detail[:500],
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['report_schedule_alerts'] = alerts[-50:]
    _save_ledger_settings(ledger, settings)


def report_designer_column_catalog() -> dict:
    return {
        'trial_balance': ['account_number', 'description', 'debit', 'credit', 'balance'],
        'income_statement': ['account_number', 'description', 'amount'],
        'ap_aging': ['document_number', 'open_amount', 'due_date'],
        'ar_aging': ['document_number', 'open_amount', 'due_date'],
        'journal_register': ['batch_date', 'batch_number', 'account_number', 'debit', 'credit'],
    }


# --- Tier D: startup guard ---

def accounting_startup_guard() -> dict:
    """Run before binding server — catches import / duplicate route issues early."""
    errors = []
    try:
        from app import app  # noqa: F401
    except Exception as exc:
        errors.append(f'import: {exc}')
    try:
        from accounting_waves_19 import report_designer_column_catalog  # noqa: F401
        report_designer_column_catalog()
    except Exception as exc:
        errors.append(f'waves_19: {exc}')
    try:
        import accounting_routes  # noqa: F401
        from collections import Counter
        import re
        text = open(os.path.join(os.path.dirname(__file__), 'accounting_routes.py'), encoding='utf-8').read()
        for name, count in Counter(re.findall(r'def (api_acct_\w+)', text)).items():
            if count > 1:
                errors.append(f'duplicate route fn: {name}')
    except Exception as exc:
        errors.append(f'routes scan: {exc}')
    return {'ok': not errors, 'errors': errors}
