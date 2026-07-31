"""
Wave 11 — Sub pay apps → A/P, commitments/CO posting, WIP/job cost,
bank/payments production hooks, Sage round-trip & exception inbox.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


def _accounting_flag(key: str, default: str = '1') -> bool:
    from program_settings_persistence import load_accounting_defaults

    return str(load_accounting_defaults().get(key, default)) != '0'


def construction_force_post_for_event(event_type: str, payload: dict | None) -> bool:
    data = payload or {}
    if data.get('force_builtin_post'):
        return True
    if event_type == 'G702Approved' and _accounting_flag('g702_post_on_approve'):
        return True
    if event_type == 'SubPayAppApproved' and _accounting_flag('sub_pay_app_post_on_approve'):
        return True
    if event_type in ('CommitmentApproved', 'CommitmentChangeOrderApproved') and _accounting_flag(
        'commitment_post_on_approve',
    ):
        return True
    if event_type == 'ChangeOrderApproved' and _accounting_flag('co_post_on_approve'):
        return True
    if event_type == 'TimesheetPosted' and _accounting_flag('timesheet_post_on_approve'):
        return True
    if event_type == 'DirectCostPosted' and _accounting_flag('direct_cost_post_on_approve'):
        return True
    return False

# --- 1: Sub pay apps → A/P ---

def _sub_idempotency(project_id: int, company_key: str, period_num, month_key: str | None = None) -> str:
    mk = month_key or datetime.utcnow().strftime('%Y%m')
    return f'SubPayAppApproved:{project_id}:{company_key}:{period_num}:{mk}'


def sub_pay_app_pending_ap_sync(db, models, ledger_id: int, project_id: int, PayAppProjectState) -> dict:
    from pay_app_persistence import get_pay_app_state

    AcctPostLink = models['AcctPostLink']
    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    state = state or {}
    history = state.get('subPayAppHistory') or {}
    approved_statuses = {'Approved', 'Paid', 'Complete'}
    month_key = datetime.utcnow().strftime('%Y%m')
    pending = []
    posted = []
    for company_key, company_hist in history.items():
        if not isinstance(company_hist, dict):
            continue
        for hist_key, entry in company_hist.items():
            if not isinstance(entry, dict) or entry.get('archived'):
                continue
            st = (entry.get('status') or '').strip()
            period_num = entry.get('periodNumber') or hist_key
            amt = float(
                entry.get('totalBilledThisPeriod')
                or entry.get('workThisPeriod')
                or entry.get('work_this_period')
                or 0
            )
            idem = _sub_idempotency(project_id, str(company_key), period_num, month_key)
            link = AcctPostLink.query.filter_by(ledger_id=ledger_id, source_key=idem).first()
            row = {
                'company_id': str(company_key),
                'period': period_num,
                'status': st,
                'amount': round(amt, 2),
                'idempotency_key': idem,
            }
            if link:
                posted.append({**row, 'ap_document_id': link.ap_document_id})
            elif st in approved_statuses and amt > 0:
                pending.append(row)
    return {'project_id': project_id, 'pending': pending, 'posted': posted}


def sync_sub_pay_app_to_ap(
    db,
    models,
    ledger_id: int,
    project_id: int,
    company_id: str,
    period_number,
    user_id=None,
    PayAppProjectState=None,
    Commitment=None,
    Project=None,
    Company=None,
):
    from pay_app_persistence import get_pay_app_state
    from pay_app_workflow import _sub_pay_app_sage_payload
    from accounting_posting import process_construction_event

    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    state = state or {}
    entry = None
    history = state.get('subPayAppHistory') or {}
    ch = history.get(str(company_id)) or history.get(company_id) or {}
    for hk, ent in (ch.items() if isinstance(ch, dict) else []):
        if not isinstance(ent, dict):
            continue
        if str(ent.get('periodNumber') or hk) == str(period_number):
            entry = ent
            break
    if not entry:
        raise ValueError('Sub pay app period not found')
    total = float(
        entry.get('totalBilledThisPeriod') or entry.get('workThisPeriod') or entry.get('work_this_period') or 0
    )
    if total <= 0:
        raise ValueError('Sub pay app has no billable amount')
    payload = _sub_pay_app_sage_payload(state, company_id, period_number, total, Commitment=Commitment)
    payload['force_builtin_post'] = True
    out = process_construction_event(
        'SubPayAppApproved',
        int(project_id),
        payload,
        db=db,
        models=models,
        user_id=user_id,
        Project=Project,
        Company=Company,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='sub_pay_app_ap_sync', details={'company': company_id, 'period': period_number, **out})
    if out.get('posted') and out.get('ap_document_id'):
        try:
            from accounting_waves_23 import apply_sub_pay_app_retainage_split
            from pay_app_persistence import get_pay_app_state

            _, st = get_pay_app_state(PayAppProjectState, int(project_id))
            pct = float((st or {}).get('payAppRetainagePercent') or 10)
            out['retainage'] = apply_sub_pay_app_retainage_split(db, models, ledger_id, out['ap_document_id'], total, pct)
        except Exception:
            pass
        try:
            from accounting_waves_25 import sage_queue_construction_mirror_event
            sage_queue_construction_mirror_event(
                db, models, ledger_id, 'SubPayAppApproved',
                {'project_id': project_id, 'ap_document_id': out.get('ap_document_id'), 'amount': total},
                user_id=user_id,
            )
        except Exception:
            pass
    return out


def sync_all_sub_pay_apps_pending_to_ap(
    db, models, ledger_id: int, project_id: int, user_id=None, PayAppProjectState=None, Commitment=None, Project=None, Company=None,
) -> dict:
    pending = sub_pay_app_pending_ap_sync(db, models, ledger_id, project_id, PayAppProjectState)
    posted = []
    errors = []
    for row in pending.get('pending') or []:
        try:
            out = sync_sub_pay_app_to_ap(
                db, models, ledger_id, project_id, row['company_id'], row['period'],
                user_id=user_id, PayAppProjectState=PayAppProjectState, Commitment=Commitment,
                Project=Project, Company=Company,
            )
            if out.get('posted'):
                posted.append({**row, **out})
        except Exception as exc:
            errors.append({**row, 'error': str(exc)})
    return {'posted_count': len(posted), 'posted': posted, 'errors': errors}


# --- 2: Commitments & change orders ---

def commitment_pending_accounting(db, models, ledger_id: int, project_id: int, Commitment) -> dict:
    AcctPostLink = models['AcctPostLink']
    approved = {'Approved', 'Executed', 'Complete', 'Active'}
    pending = []
    posted = []
    rows = Commitment.query.filter_by(project_id=int(project_id)).all()
    for c in rows:
        if (c.status or '') not in approved:
            continue
        idem = f'CommitmentApproved:{c.id}'
        link = AcctPostLink.query.filter_by(ledger_id=ledger_id, source_key=idem).first()
        amt = float(c.current_amount or c.original_amount or 0)
        row = {'commitment_id': c.id, 'number': c.number, 'amount': round(amt, 2), 'idempotency_key': idem}
        if link:
            posted.append({**row, 'purchase_order_id': link.purchase_order_id, 'ap_document_id': link.ap_document_id})
        elif amt > 0:
            pending.append(row)
    return {'project_id': project_id, 'pending': pending, 'posted': posted}


def sync_commitment_to_accounting(
    db, models, ledger_id: int, commitment_id: int, user_id=None, Commitment=None, CommitmentAllocation=None, Project=None, Company=None,
) -> dict:
    from commitment_persistence import build_commitment_sage_payload
    from accounting_posting import process_construction_event

    c = Commitment.query.get(int(commitment_id))
    if not c:
        raise ValueError('Commitment not found')
    allocations = []
    if CommitmentAllocation is not None:
        allocations = CommitmentAllocation.query.filter_by(commitment_id=c.id).all()
    payload = build_commitment_sage_payload(c, allocations, {})
    payload['idempotency_key'] = f'CommitmentApproved:{c.id}'
    payload['force_builtin_post'] = True
    out = process_construction_event(
        'CommitmentApproved',
        c.project_id,
        payload,
        db=db,
        models=models,
        user_id=user_id,
        Project=Project,
        Company=Company,
        commitment=c,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='commitment_accounting_sync', entity_id=c.id, details=out)
    return out


def sync_all_commitments_pending(
    db, models, ledger_id: int, project_id: int, user_id=None, Commitment=None, CommitmentAllocation=None, Project=None, Company=None,
) -> dict:
    pending = commitment_pending_accounting(db, models, ledger_id, project_id, Commitment)
    posted = []
    errors = []
    for row in pending.get('pending') or []:
        try:
            out = sync_commitment_to_accounting(
                db, models, ledger_id, row['commitment_id'], user_id=user_id,
                Commitment=Commitment, CommitmentAllocation=CommitmentAllocation, Project=Project, Company=Company,
            )
            if out.get('posted'):
                posted.append({**row, **out})
        except Exception as exc:
            errors.append({**row, 'error': str(exc)})
    return {'posted_count': len(posted), 'posted': posted, 'errors': errors}


def post_commitment_change_order(
    db, models, ledger_id: int, body: dict, user_id=None, Commitment=None, Project=None, Company=None,
) -> dict:
    from accounting_posting import process_construction_event

    cid = int(body.get('commitment_id') or body.get('commitmentId') or 0)
    delta = round(float(body.get('amount') or body.get('delta_amount') or 0), 2)
    if cid <= 0 or delta <= 0:
        raise ValueError('commitment_id and positive amount required')
    c = Commitment.query.get(cid)
    if not c:
        raise ValueError('Commitment not found')
    idem = f'CommitmentChangeOrderApproved:{cid}:{body.get("change_order_id") or body.get("co_number") or delta}'
    payload = {
        'commitment_id': cid,
        'amount': delta,
        'delta_amount': delta,
        'company_id': c.company_id,
        'idempotency_key': idem[:120],
        'force_builtin_post': True,
    }
    out = process_construction_event(
        'CommitmentChangeOrderApproved',
        c.project_id,
        payload,
        db=db,
        models=models,
        user_id=user_id,
        Project=Project,
        Company=Company,
        commitment=c,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='cco_accounting_post', entity_id=cid, details=out)
    return out


# --- 3: WIP & revenue ---

def jobcost_wip_analysis(db, models, ledger_id: int, project_id: int, PayAppProjectState=None, **kwargs):
    from accounting_waves_22 import contractual_wip_analysis

    return contractual_wip_analysis(
        db, models, ledger_id, project_id,
        PayAppProjectState=PayAppProjectState,
        **kwargs,
    )


def post_wip_billing_adjustment(db, models, ledger_id: int, project_id: int, user_id=None, *, amount: float | None = None) -> dict:
    from accounting_posting import _account_by_number, _create_posted_batch, load_accounting_options

    analysis = jobcost_wip_analysis(db, models, ledger_id, project_id)
    adj = round(float(amount if amount is not None else analysis['over_under_billing']), 2)
    if abs(adj) < 0.01:
        raise ValueError('No WIP adjustment needed')
    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    wip = _account_by_number(AcctGLAccount, ledger_id, '1150') or _account_by_number(AcctGLAccount, ledger_id, opts['ar_account'])
    rev = _account_by_number(AcctGLAccount, ledger_id, opts['revenue_account'])
    if adj > 0:
        lines = [
            {'account_id': wip.id, 'debit': adj, 'credit': 0, 'project_id': project_id},
            {'account_id': rev.id, 'debit': 0, 'credit': adj, 'project_id': project_id},
        ]
        desc = 'WIP adjustment — overbilling'
    else:
        adj = abs(adj)
        lines = [
            {'account_id': rev.id, 'debit': adj, 'credit': 0, 'project_id': project_id},
            {'account_id': wip.id, 'debit': 0, 'credit': adj, 'project_id': project_id},
        ]
        desc = 'WIP adjustment — underbilling'
    batch = _create_posted_batch(
        db, models, ledger_id=ledger_id, source='WIP', description=desc, user_id=user_id, lines=lines,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='wip_adjustment', details={'amount': adj, 'batch_id': batch.id})
    return {'journal_batch_id': batch.id, 'amount': adj, 'analysis': analysis}


# --- 4: Bank & payments ---

def record_payment_exception(ledger, *, source: str, detail: dict) -> None:
    settings = _ledger_settings(ledger)
    q = settings.get('payment_exceptions') or []
    q.append({
        'source': source,
        'detail': detail,
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['payment_exceptions'] = q[-100:]
    _save_ledger_settings(ledger, settings)


def payment_exception_inbox(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    return {
        'exceptions': (settings.get('payment_exceptions') or [])[-30:],
        'stripe_webhook_log': (settings.get('stripe_webhook_log') or [])[-15:],
    }


def log_stripe_webhook_event(ledger, payload: dict, result: dict) -> None:
    settings = _ledger_settings(ledger)
    log = settings.get('stripe_webhook_log') or []
    log.append({
        'type': payload.get('type'),
        'at': datetime.utcnow().isoformat() + 'Z',
        'result': {k: result.get(k) for k in ('status', 'pay_now_error', 'type', 'amount') if k in result},
    })
    settings['stripe_webhook_log'] = log[-50:]
    if result.get('pay_now_error'):
        meta = (payload.get('data') or {}).get('object', {}).get('metadata') or {}
        record_payment_exception(ledger, source='stripe_pay_now', detail={
            **result,
            'token': meta.get('pay_now_token') or meta.get('casepm_pay_now_token'),
            'payment_intent_id': (payload.get('data') or {}).get('object', {}).get('id'),
        })
    _save_ledger_settings(ledger, settings)


def plaid_auto_import_for_ledger(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_17 import plaid_access_token_for_ledger
    from accounting_tier14_wave import plaid_sandbox_or_live_transactions
    from accounting_parity_wave3 import import_plaid_transactions

    ledger = models['AcctLedger'].query.get(ledger_id)
    token = plaid_access_token_for_ledger(ledger)
    if not token:
        return {'imported': 0, 'skipped': 'no_plaid_token'}
    AcctBankAccount = models['AcctBankAccount']
    bank = AcctBankAccount.query.filter_by(ledger_id=ledger_id).order_by(AcctBankAccount.id).first()
    if not bank:
        return {'imported': 0, 'skipped': 'no_bank_account'}
    end = date.today()
    start = end - timedelta(days=7)
    txns = plaid_sandbox_or_live_transactions({
        'access_token': token,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
    })
    out = import_plaid_transactions(db, models, ledger_id, bank.id, txns, user_id=user_id)
    write_audit(db, models, ledger_id, user_id=user_id, action='plaid_auto_import', details=out)
    return out


def reconcile_pay_now_exceptions(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_parity_wave3 import capture_pay_now_stripe

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    fixed = []
    still_open = []
    for exc in list(settings.get('payment_exceptions') or [])[-20:]:
        if exc.get('source') != 'stripe_pay_now':
            still_open.append(exc)
            continue
        token = (exc.get('detail') or {}).get('token')
        pi = (exc.get('detail') or {}).get('payment_intent_id')
        if not token:
            still_open.append(exc)
            continue
        try:
            capture_pay_now_stripe(db, models, token, pi or '', user_id=user_id)
            fixed.append(token)
        except Exception as err:
            still_open.append({**exc, 'retry_error': str(err)})
    settings['payment_exceptions'] = still_open[-100:]
    _save_ledger_settings(ledger, settings)
    return {'fixed': len(fixed), 'remaining': len(still_open)}


# --- 5: Sage round trip & inbox ---

def sage_pull_open_ap(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    AcctAPDocument = models['AcctAPDocument']
    AcctVendor = models['AcctVendor']
    resp = get_resource('AP', 'APInvoices', top=limit)
    if not resp.get('ok'):
        return {'imported': 0, 'message': resp.get('error') or resp.get('mode')}
    data = resp.get('data') or {}
    rows = data.get('value') or []
    created = skipped = 0
    for row in rows:
        inv = (row.get('InvoiceNumber') or row.get('DocumentNumber') or '').strip()
        if not inv:
            continue
        if AcctAPDocument.query.filter_by(ledger_id=ledger_id, document_number=inv[:40]).first():
            skipped += 1
            continue
        vcode = (row.get('VendorNumber') or '').strip().upper()
        vendor = AcctVendor.query.filter_by(ledger_id=ledger_id, code=vcode).first() if vcode else None
        if not vendor:
            skipped += 1
            continue
        amt = float(row.get('InvoiceAmount') or row.get('Amount') or 0)
        doc = AcctAPDocument(
            ledger_id=ledger_id,
            vendor_id=vendor.id,
            document_number=inv[:40],
            document_type='SageImport',
            document_date=date.today(),
            amount=amt,
            status='Open',
        )
        db.session.add(doc)
        created += 1
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_open_ap', details={'created': created, 'skipped': skipped})
    return {'created': created, 'skipped': skipped, 'mode': resp.get('mode')}


def sage_hybrid_exception_inbox(db, models, ledger_id: int) -> dict:
    from accounting_waves_20 import sage_gl_account_conflict_review
    from accounting_waves_19 import sage_vendor_conflict_review

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    vendors = sage_vendor_conflict_review(db, models, ledger_id, limit=30)
    gl = sage_gl_account_conflict_review(db, models, ledger_id, limit=30)
    return {
        'vendor_conflicts': (vendors.get('conflicts') or [])[:15],
        'gl_conflicts': (gl.get('conflicts') or [])[:15],
        'ap_push_errors': (settings.get('sage_last_ap_push_errors') or [])[-10:],
        'sync_log': (settings.get('sage_sync_log') or [])[-8:],
        'export_queue_size': len(settings.get('sage_export_queue') or []),
        'push_queue_size': len(settings.get('sage_push_queue') or []),
    }


def cron_wave11_maintenance(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_18 import sage_flush_sync_queues, cron_run_scheduled_reports
    from accounting_waves_20 import cron_wave10_maintenance

    wave10 = cron_wave10_maintenance(db, models, secret)
    AcctLedger = models['AcctLedger']
    sage_runs = []
    plaid_runs = []
    for ledger in AcctLedger.query.limit(20).all():
        sage_runs.append({
            'ledger_id': ledger.id,
            **sage_flush_sync_queues(db, models, ledger.id, user_id=None, limit=15),
        })
        plaid_runs.append({'ledger_id': ledger.id, **plaid_auto_import_for_ledger(db, models, ledger.id)})
    return {
        'wave10': wave10,
        'sage_flush': sage_runs,
        'plaid_import': plaid_runs,
        'scheduled_reports': cron_run_scheduled_reports(db, models, secret),
    }
