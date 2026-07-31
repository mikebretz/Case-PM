"""
Waves 29–32 — Sage production hardening, SoR/drift, licensed modules depth,
standalone accounting polish.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import sage_sync_get, sage_sync_set, sage_write_guard
from accounting_waves_25 import _append_sage_log, _ledger_settings, _save_ledger_settings
from accounting_waves_26 import sage_run_paces_mandatory


# --- Wave 29: schema profiles & dedupe ---

DEFAULT_SAGE_SCHEMA_PROFILES = {
    'sage300_web_api_default': {
        'version': '2024',
        'resources': {
            'ar_receipts': 'ARReceiptBatches',
            'ar_invoices': 'ARInvoices',
            'ap_invoices': 'APInvoices',
            'ap_payments': 'APPaymentBatches',
            'bk_transactions': 'BKTransactions',
        },
        'fields': {
            'invoice_number': ['InvoiceNumber', 'DocumentNumber'],
            'customer_number': ['CustomerNumber', 'CustomerCode'],
            'vendor_number': ['VendorNumber', 'VendorCode'],
            'amount_paid': ['AmountPaid', 'PaidAmount'],
            'receipt_number': ['ReceiptNumber', 'BatchNumber'],
        },
    },
}


def get_schema_profile(settings: dict) -> dict:
    pid = (settings.get('sage_schema_profile_id') or 'sage300_web_api_default').strip()
    custom = settings.get('sage_schema_profile_custom') or {}
    base = dict(DEFAULT_SAGE_SCHEMA_PROFILES.get(pid) or DEFAULT_SAGE_SCHEMA_PROFILES['sage300_web_api_default'])
    if custom:
        base.update(custom)
    return base


def save_sage_schema_profile(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if body.get('profile_id'):
        settings['sage_schema_profile_id'] = str(body['profile_id'])[:60]
    if isinstance(body.get('custom'), dict):
        settings['sage_schema_profile_custom'] = body['custom']
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_schema_profile', details=body)
    return {'profile': get_schema_profile(settings)}


def _field(row: dict, profile: dict, logical: str, default=''):
    for key in (profile.get('fields') or {}).get(logical) or [logical]:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def external_key_register(settings: dict, entity_type: str, local_id: int, sage_key: str) -> dict:
    reg = settings.setdefault('sage_external_keys', {})
    reg[f'{entity_type}:{local_id}'] = sage_key[:80]
    reg[f'sage:{entity_type}:{sage_key[:80]}'] = local_id
    settings['sage_external_keys'] = reg
    return settings


def external_key_seen(settings: dict, entity_type: str, sage_key: str) -> bool:
    reg = settings.get('sage_external_keys') or {}
    return f'sage:{entity_type}:{sage_key[:80]}' in reg


def sage_pull_ar_receipts_v2(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'pull')
    profile = get_schema_profile(settings)
    res = (profile.get('resources') or {}).get('ar_receipts', 'ARReceiptBatches')
    resp = get_resource('AR', res, top=limit)
    if not resp.get('ok'):
        return {'applied': 0, 'mode': resp.get('mode'), 'skipped_dup': 0}
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    rows = (resp.get('data') or {}).get('value') or []
    applied = skipped_dup = 0
    for row in rows:
        rcpt = _field(row, profile, 'receipt_number', f"R-{row.get('BatchNumber', '')}")
        if rcpt and external_key_seen(settings, 'ar_receipt', rcpt):
            skipped_dup += 1
            continue
        cust_code = _field(row, profile, 'customer_number').upper()
        cust = AcctCustomer.query.filter_by(ledger_id=ledger_id, code=cust_code).first() if cust_code else None
        apps = row.get('Applications') or row.get('ReceiptApplications') or []
        if isinstance(apps, dict):
            apps = list(apps.values())
        for app in apps:
            if not isinstance(app, dict):
                continue
            inv = _field(app, profile, 'invoice_number')
            amt = float(app.get('Amount') or app.get('AppliedAmount') or 0)
            if not inv or amt <= 0:
                continue
            doc = AcctARDocument.query.filter_by(ledger_id=ledger_id, document_number=inv[:40]).first()
            if not doc:
                continue
            doc.amount_paid = round(float(doc.amount_paid or 0) + amt, 2)
            doc.status = 'Paid' if doc.amount_paid >= float(doc.amount or 0) - 0.01 else 'Partial'
            sage_sync_set(doc, state='acknowledged', external_key=inv)
            applied += 1
        if rcpt and applied:
            settings = external_key_register(settings, 'ar_receipt', 0, rcpt)
    db.session.flush()
    _append_sage_log(settings, {'direction': 'pull', 'entity': 'ar_receipts_v2', 'applied': applied, 'skipped_dup': skipped_dup})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_ar_receipts_v2', details={'applied': applied})
    return {'applied': applied, 'skipped_dup': skipped_dup, 'mode': resp.get('mode')}


def sage_pull_ap_payments_from_batches(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ap', 'pull')
    profile = get_schema_profile(settings)
    res = (profile.get('resources') or {}).get('ap_payments', 'APPaymentBatches')
    resp = get_resource('AP', res, top=limit)
    if not resp.get('ok'):
        return {'updated': 0, 'mode': resp.get('mode')}
    AcctAPDocument = models['AcctAPDocument']
    rows = (resp.get('data') or {}).get('value') or []
    updated = 0
    for batch in rows:
        batch_no = _field(batch, profile, 'receipt_number', str(batch.get('BatchNumber') or ''))
        if batch_no and external_key_seen(settings, 'ap_payment_batch', batch_no):
            continue
        payments = batch.get('Payments') or batch.get('PaymentLines') or []
        if isinstance(payments, dict):
            payments = list(payments.values())
        for pay in payments:
            if not isinstance(pay, dict):
                continue
            inv = _field(pay, profile, 'invoice_number')
            amt = float(pay.get('PaymentAmount') or pay.get('Amount') or 0)
            if not inv:
                continue
            doc = AcctAPDocument.query.filter_by(ledger_id=ledger_id, document_number=inv[:40]).first()
            if not doc:
                continue
            if amt > 0:
                doc.amount_paid = round(float(doc.amount_paid or 0) + amt, 2)
                doc.status = 'Paid' if doc.amount_paid >= float(doc.amount or 0) - 0.01 else 'Partial'
                sage_sync_set(doc, state='acknowledged', external_key=inv)
                updated += 1
        if batch_no:
            settings = external_key_register(settings, 'ap_payment_batch', 0, batch_no)
    db.session.flush()
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_ap_batches', details={'updated': updated})
    return {'updated': updated, 'mode': resp.get('mode')}


def sage_mirror_deploy_check_v3() -> dict:
    from accounting_waves_26 import sage_mirror_deploy_check_v2

    base = sage_mirror_deploy_check_v2()
    in_ci = os.environ.get('GITHUB_ACTIONS') == 'true'
    if in_ci:
        os.environ['CASEPM_RUN_SAGE_PACES'] = '1'
    paces = sage_run_paces_mandatory()
    ok = base.get('ok') and (paces.get('ok') or paces.get('skipped'))
    if in_ci and paces.get('skipped'):
        ok = base.get('ok')
    return {'ok': ok, 'v2': base, 'paces': paces, 'ci': in_ci}


# --- Wave 30: merge, SoR, drift, construction flush ---

def sage_merge_conflict_resolve(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_waves_19 import resolve_sage_vendor_conflict

    winner = (body.get('winner') or 'casepm').lower()
    code = (body.get('code') or '').strip()
    if body.get('type') == 'vendor' and code:
        out = resolve_sage_vendor_conflict(
            db, models, ledger_id,
            {'code': code, 'winner': winner, 'sage_name': body.get('sage_name')},
            user_id=user_id,
        )
        return out
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    merges = settings.get('sage_merge_resolutions') or []
    merges.append({**body, 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['sage_merge_resolutions'] = merges[-100:]
    _save_ledger_settings(ledger, settings)
    return {'resolved': True, 'winner': winner}


def sor_guard_extended(settings: dict, area: str, action: str) -> None:
    """Wave 30 — bank, payroll, inventory, fa areas."""
    sor = (settings.get('system_of_record') or 'casepm').lower()
    pol = (settings.get('sage_module_policies') or {}).get(area) or {}
    if sor == 'sage' and action == 'casepm_write' and not pol.get('allow_casepm_push', False):
        raise PermissionError(f'Sage is system of record — {area} write blocked')


def sage_drift_dashboard(db, models, ledger_id: int) -> dict:
    from accounting_waves_21 import sage_hybrid_exception_inbox
    from accounting_waves_26 import sage_pull_oe_and_reconcile

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    inbox = sage_hybrid_exception_inbox(db, models, ledger_id)
    AcctARDocument = models['AcctARDocument']
    AcctAPDocument = models['AcctAPDocument']
    open_ar = AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    open_ap = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').count()
    last_pull = (settings.get('sage_sync_log') or [])[-1]
    parity = settings.get('sage_parity_warnings') or []
    return {
        'open_ar': open_ar,
        'open_ap': open_ap,
        'inbox': inbox,
        'last_sync': last_pull,
        'parity_warning_count': len(parity),
        'ic_oe': settings.get('sage_ic_oe_reconcile'),
        'external_key_count': len(settings.get('sage_external_keys') or {}),
    }


def cron_scheduled_pull_with_drift_alert(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_26 import cron_waves_25_28_maintenance, sage_inbox_auto_retry

    base = cron_waves_25_28_maintenance(db, models, secret, Project=Project)
    AcctLedger = models['AcctLedger']
    alerts = []
    for ledger in AcctLedger.query.limit(10).all():
        ar = sage_pull_ar_receipts_v2(db, models, ledger.id)
        ap = sage_pull_ap_payments_from_batches(db, models, ledger.id)
        sage_inbox_auto_retry(db, models, ledger.id)
        dash = sage_drift_dashboard(db, models, ledger.id)
        drift = (dash.get('parity_warning_count') or 0) + len((dash.get('inbox') or {}).get('ap_push_errors') or [])
        if drift > 0:
            alerts.append({'ledger_id': ledger.id, 'drift_score': drift, 'ar_pull': ar, 'ap_pull': ap})
            settings = _ledger_settings(ledger)
            settings['sage_drift_alert'] = {'at': datetime.utcnow().isoformat() + 'Z', 'score': drift}
            _save_ledger_settings(ledger, settings)
            try:
                from program_settings_persistence import load_program_settings
                from email_notifications import send_workflow_email

                email = (load_program_settings().get('email') or {}).get('admin_notification_email') or ''
                if email.strip():
                    send_workflow_email(
                        email.strip(),
                        'Case PM — Sage drift alert',
                        f'<p>Ledger {ledger.id}: drift score {drift}. Review Accounting → Sage drift dashboard.</p>',
                        f'Ledger {ledger.id}: drift score {drift}',
                    )
            except Exception:
                pass
    return {'base': base, 'alerts': alerts}


def flush_construction_mirror_queue(db, models, ledger_id: int, user_id=None, limit: int = 20) -> dict:
    from sage_service import create_and_process_sage_event

    import app as app_mod

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = list(settings.get('sage_construction_mirror_queue') or [])
    processed = errors = 0
    remaining = []
    for entry in q[:limit]:
        etype = entry.get('type') or 'ManualSync'
        payload = entry.get('payload') or {}
        pid = payload.get('project_id') or 0
        try:
            create_and_process_sage_event(
                app_mod.SageSyncEvent,
                app_mod.Project,
                db,
                int(pid),
                etype,
                payload=payload,
                user_id=user_id,
            )
            processed += 1
        except Exception as exc:
            errors += 1
            remaining.append({**entry, 'error': str(exc)[:200]})
    remaining.extend(q[limit:])
    settings['sage_construction_mirror_queue'] = remaining[-100:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_construction_flush', details={'processed': processed, 'errors': errors})
    return {'processed': processed, 'errors': errors, 'remaining': len(remaining)}


# --- Wave 31: licensed modules ---

def sage_payroll_policy_enforce(settings: dict) -> dict:
    sor = settings.get('payroll_system_of_record') or 'casepm'
    locked = sor == 'sage' and settings.get('sage_pr_push_enabled') != '1'
    return {'payroll_system_of_record': sor, 'casepm_payroll_locked': locked}


def sage_pull_bank_transactions(db, models, ledger_id: int, user_id=None, limit: int = 80) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sor_guard_extended(settings, 'bk', 'casepm_write')
    sage_write_guard(settings, 'bk', 'pull')
    profile = get_schema_profile(settings)
    res = (profile.get('resources') or {}).get('bk_transactions', 'BKTransactions')
    resp = get_resource('BK', res, top=limit)
    if not resp.get('ok'):
        return {'imported': 0, 'mode': resp.get('mode')}
    AcctBankTransaction = models['AcctBankTransaction']
    AcctBankAccount = models['AcctBankAccount']
    rows = (resp.get('data') or {}).get('value') or []
    imported = 0
    default_bank = AcctBankAccount.query.filter_by(ledger_id=ledger_id).first()
    if not default_bank:
        return {'imported': 0, 'message': 'No bank account'}
    for row in rows:
        ref = _field(row, profile, 'receipt_number', str(row.get('Reference') or row.get('Id') or ''))
        if ref and external_key_seen(settings, 'bk_tx', ref):
            continue
        amt = float(row.get('Amount') or row.get('TransactionAmount') or 0)
        if not amt:
            continue
        db.session.add(AcctBankTransaction(
            bank_account_id=default_bank.id,
            transaction_date=date.today(),
            amount=amt,
            description=(row.get('Description') or 'Sage import')[:200],
            reference=ref[:80] if ref else None,
            reconciled=False,
        ))
        if ref:
            settings = external_key_register(settings, 'bk_tx', 0, ref)
        imported += 1
    db.session.flush()
    _save_ledger_settings(ledger, settings)
    return {'imported': imported, 'mode': resp.get('mode')}


def apply_line_tax_to_document(db, models, ledger_id: int, document_type: str, document_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    groups = settings.get('sage_tax_groups') or []
    default_code = groups[0].get('code') if groups else None
    if not default_code:
        return {'skipped': True}
    meta_tax = {'tax_group': default_code, 'tax_source': 'sage_wave31'}
    if document_type == 'ap':
        doc = models['AcctAPDocument'].query.filter_by(id=document_id, ledger_id=ledger_id).first()
    else:
        doc = models['AcctARDocument'].query.filter_by(id=document_id, ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Document not found')
    meta = json.loads(doc.details_json or '{}') if doc.details_json else {}
    meta['tax'] = meta_tax
    doc.details_json = json.dumps(meta)
    db.session.flush()
    return {'document_id': doc.id, 'tax': meta_tax}


def sage_pull_ic_oe_upsert(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ic', 'pull')
    ic_resp = get_resource('IC', 'ICItems', top=limit)
    oe_resp = get_resource('OE', 'OEOrders', top=limit)
    AcctInventoryItem = models.get('AcctInventoryItem')
    AcctSalesOrder = models.get('AcctSalesOrder')
    ic_created = oe_created = 0
    if AcctInventoryItem and ic_resp.get('ok'):
        for row in (ic_resp.get('data') or {}).get('value') or []:
            num = (row.get('ItemNumber') or '').strip()
            if not num or AcctInventoryItem.query.filter_by(ledger_id=ledger_id, item_number=num).first():
                continue
            db.session.add(AcctInventoryItem(
                ledger_id=ledger_id,
                item_number=num[:40],
                description=(row.get('Description') or num)[:300],
                qty_on_hand=float(row.get('QuantityOnHand') or 0),
                unit_cost=float(row.get('AverageCost') or 0),
            ))
            ic_created += 1
    if AcctSalesOrder and oe_resp.get('ok'):
        for row in (oe_resp.get('data') or {}).get('value') or []:
            onum = (row.get('OrderNumber') or '').strip()
            if not onum or AcctSalesOrder.query.filter_by(ledger_id=ledger_id, order_number=onum).first():
                continue
            db.session.add(AcctSalesOrder(
                ledger_id=ledger_id,
                order_number=onum[:40],
                status='Open',
                total_amount=float(row.get('OrderTotal') or row.get('Amount') or 0),
            ))
            oe_created += 1
    db.session.flush()
    _save_ledger_settings(ledger, settings)
    return {'ic_created': ic_created, 'oe_created': oe_created}


def sage_ack_fa_depreciation_queue(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('sage_fa_export_queue') or []
    ack = [{'item': x, 'acknowledged_at': datetime.utcnow().isoformat() + 'Z'} for x in q]
    settings['sage_fa_export_ack'] = ack[-20:]
    settings['sage_fa_export_queue'] = []
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_fa_ack', details={'count': len(ack)})
    return {'acknowledged': len(ack)}


# --- Wave 32: standalone polish ---

def multi_invoice_cash_application(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    from accounting_ar_extended import apply_cash_workbench_advanced

    ledger = models['AcctLedger'].query.get(ledger_id)
    sor_guard_extended(_ledger_settings(ledger), 'ar', 'casepm_write')
    return apply_cash_workbench_advanced(db, models, ledger_id, body, user_id=user_id)


def export_filing_bundle_1099_w2(db, models, ledger_id: int, tax_year: int, user_id=None) -> dict:
    from accounting_parity_wave2 import export_1099_fire
    from accounting_parity_wave3 import export_w2_summary

    w2 = export_w2_summary(db, models, ledger_id, tax_year)
    try:
        f1099 = export_1099_fire(db, models, ledger_id, tax_year)
    except TypeError:
        f1099 = export_1099_fire(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    bundle = {
        'tax_year': tax_year,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'w2_employee_count': len((w2 or {}).get('employees') or []),
        '1099_preview': str(f1099)[:2000],
    }
    settings['last_filing_bundle'] = bundle
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='filing_bundle', details={'year': tax_year})
    return bundle


def month_close_report_schedule_hook(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_23 import month_end_cash_checklist
    from accounting_parity_wave2 import schedule_report

    checklist = month_end_cash_checklist(db, models, ledger_id)
    scheduled = []
    try:
        scheduled.append(schedule_report(db, models, ledger_id, {'report_type': 'trial_balance', 'frequency': 'monthly'}, user_id=user_id))
    except Exception as exc:
        scheduled.append({'error': str(exc)[:120]})
    return {'checklist': checklist, 'scheduled': scheduled}


def intercompany_ledger_routing_preview(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    companies = settings.get('sage_companies') or []
    return {
        'primary_ledger_id': ledger_id,
        'sage_companies': companies,
        'note': 'Intercompany eliminations use consolidation export; map companies in sage mirror policy.',
    }


def accounting_large_ledger_health(db, models, ledger_id: int) -> dict:
    counts = {}
    for name in ('AcctARDocument', 'AcctAPDocument', 'AcctJournalBatch', 'AcctGLAccount', 'AcctVendor', 'AcctCustomer'):
        cls = models.get(name)
        if cls:
            counts[name] = cls.query.filter_by(ledger_id=ledger_id).count()
    return {'ledger_id': ledger_id, 'counts': counts, 'ok': sum(counts.values()) < 500_000}


def cron_waves_29_32_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_26 import cron_waves_25_28_maintenance

    base = cron_waves_25_28_maintenance(db, models, secret, Project=Project)
    pull_alert = cron_scheduled_pull_with_drift_alert(db, models, secret, Project=Project)
    AcctLedger = models['AcctLedger']
    flush = []
    for ledger in AcctLedger.query.limit(5).all():
        flush.append(flush_construction_mirror_queue(db, models, ledger.id))
    return {'base': base, 'pull_alert': pull_alert, 'construction_flush': flush, 'deploy_v3': sage_mirror_deploy_check_v3()}
