"""
Wave 8 — production bridges: Sage queue flush, Pay Now checkout, WH-347 PDF,
IC lot receive API, OE commission accrual, cron scheduler hook.
"""
from __future__ import annotations

import io
import os
from datetime import date, datetime

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    import json

    ledger.settings_json = json.dumps(settings)


def sage_flush_sync_queues(db, models, ledger_id: int, user_id=None, *, limit: int = 25) -> dict:
    """Attempt to POST queued Sage payloads; always logs outcomes on ledger."""
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    export_q = list(settings.get('sage_export_queue') or [])
    push_q = list(settings.get('sage_push_queue') or [])
    results = []
    processed = 0
    for entry in push_q[:limit]:
        if not isinstance(entry, dict):
            continue
        etype = entry.get('type')
        payload = entry.get('payload') or entry
        if etype == 'vendor':
            resp = post_resource('AP', 'APVendors', payload)
        elif etype == 'open_ap':
            resp = {'ok': False, 'mode': 'queued_only', 'note': 'Open AP export uses batch queue', 'payload': payload}
        else:
            resp = {'ok': False, 'mode': 'skipped', 'entry': entry}
        results.append({'type': etype, **resp})
        processed += 1
    for batch in export_q[: min(5, limit)]:
        resp = post_resource('GL', 'GLJournalBatches', {'CasePMExport': batch})
        results.append({'type': 'je_export', **resp})
        processed += 1
    log = settings.get('sage_sync_log') or []
    log.append({
        'at': datetime.utcnow().isoformat() + 'Z',
        'direction': 'flush',
        'processed': processed,
        'results': results[:20],
    })
    settings['sage_sync_log'] = log[-100:]
    settings['sage_last_flush'] = datetime.utcnow().isoformat() + 'Z'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_flush_queues', details={'processed': processed})
    return {'processed': processed, 'results': results}


def pay_now_public_checkout(db, models, token: str) -> dict:
    """Public Pay Now session: link details + Stripe PaymentIntent when configured."""
    from accounting_payment_processing import serialize_pay_now_link

    AcctPayNowLink = models['AcctPayNowLink']
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    link = AcctPayNowLink.query.filter_by(token=token).first()
    if not link:
        raise ValueError('Invalid payment link')
    if link.status != 'Pending':
        raise ValueError(f'This link is {link.status.lower()}')
    if link.expires_at and link.expires_at < datetime.utcnow():
        link.status = 'Expired'
        raise ValueError('This payment link has expired')
    doc = AcctARDocument.query.get(link.ar_document_id)
    cust = AcctCustomer.query.get(link.customer_id) if link.customer_id else None
    out = {
        'link': serialize_pay_now_link(link),
        'invoice_number': doc.document_number if doc else None,
        'customer_name': cust.name if cust else None,
        'stripe': None,
    }
    secret = (os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('CASEPM_STRIPE_SECRET_KEY') or '').strip()
    publishable = (os.environ.get('STRIPE_PUBLISHABLE_KEY') or os.environ.get('CASEPM_STRIPE_PUBLISHABLE_KEY') or '').strip()
    if secret and link.payment_method == 'card':
        from accounting_tier14_wave import create_stripe_payment_intent

        intent = create_stripe_payment_intent(
            float(link.amount),
            metadata={'pay_now_token': token, 'casepm_pay_now_token': token, 'ar_document_id': str(link.ar_document_id)},
        )
        out['stripe'] = {
            'publishable_key': publishable,
            'client_secret': intent.get('client_secret'),
            'payment_intent_id': intent.get('payment_intent_id'),
            'mode': intent.get('mode'),
        }
    return out


def pay_now_complete_card(db, models, token: str, payment_intent_id: str) -> dict:
    from accounting_parity_wave3 import capture_pay_now_stripe

    return capture_pay_now_stripe(db, models, token, payment_intent_id or '', user_id=None)


def payroll_wh347_pdf_bytes(db, models, ledger_id: int, project_id: int, week_ending: str) -> bytes:
    """Build WH-347 PDF from posted payroll lines for a project/week."""
    import csv
    from accounting_parity_wave3 import certified_payroll_wh347

    csv_text = certified_payroll_wh347(db, models, ledger_id, project_id, week_ending)
    workers = []
    reader = csv.reader(io.StringIO(csv_text))
    next(reader, None)
    next(reader, None)
    for parts in reader:
        if len(parts) < 7:
            continue
        try:
            hours = float(parts[2])
            gross = float(parts[4])
        except ValueError:
            continue
        workers.append({
            'name': parts[0],
            'classification': parts[1],
            'hours': hours,
            'gross_pay': gross,
        })
    record = {
        'advanced': {'contractor_name': 'Case PM Contractor', 'workers_json': workers},
        'simple': {'work_date': week_ending, 'title': f'Project {project_id}'},
        'record_date': week_ending,
        'number': f'WH347-{week_ending}',
    }
    project = None
    from wh347_pdf import build_wh347_pdf

    doc = build_wh347_pdf(record, project=project, workers=workers)
    return doc.tobytes()


def inventory_receive_with_lot(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_parity_wave2 import receive_lot

    out = receive_lot(
        db, models, ledger_id,
        int(body['item_id']),
        float(body['qty']),
        body.get('lot_number', ''),
        body.get('serial_number', ''),
        float(body.get('unit_cost') or 0),
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='ic_lot_receive', details=body)
    return out


def post_oe_commission_accrual(db, models, ledger_id: int, user_id=None, *, order_id: int | None = None) -> dict:
    from accounting_waves_17 import oe_commission_summary
    from accounting_posting import _account_by_number, _create_posted_batch

    summary = oe_commission_summary(db, models, ledger_id, order_id)
    total = float(summary.get('total_commission_est') or 0)
    if total <= 0:
        raise ValueError('No commission amount to accrue')
    AcctGLAccount = models['AcctGLAccount']
    expense = _account_by_number(AcctGLAccount, ledger_id, '6100') or _account_by_number(AcctGLAccount, ledger_id, '6000')
    payable = _account_by_number(AcctGLAccount, ledger_id, '2100') or _account_by_number(AcctGLAccount, ledger_id, '2000')
    batch = _create_posted_batch(
        db, models,
        ledger_id=ledger_id,
        source='oe_commission',
        description=f'OE commission accrual {date.today().isoformat()}',
        lines=[
            {'account_id': expense.id, 'debit': total, 'credit': 0, 'description': 'Sales commissions'},
            {'account_id': payable.id, 'debit': 0, 'credit': total, 'description': 'Commissions payable'},
        ],
        user_id=user_id,
    )
    write_audit(db, models, ledger_id, user_id=user_id, action='oe_commission_accrual', details={'amount': total, 'batch_id': batch.id})
    return {'commission_accrual': total, 'journal_batch_id': batch.id, 'orders': summary.get('orders')}


def cron_run_scheduled_reports(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_tier14_wave import run_scheduled_reports_with_email

    AcctLedger = models['AcctLedger']
    ran_all = []
    for ledger in AcctLedger.query.limit(20).all():
        out = run_scheduled_reports_with_email(db, models, ledger.id, user_id=None)
        ran_all.append({'ledger_id': ledger.id, **out})
    return {'ledgers': len(ran_all), 'detail': ran_all}
