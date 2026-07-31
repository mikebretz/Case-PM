"""
Waves 20–24 — Sage mirror hardening: AR cash, idempotent AP/AR, retainage & segments,
distribution live, CRE portfolio, platform/FA, payroll & year-end variance.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


def _append_sage_log(settings: dict, entry: dict) -> None:
    log = settings.get('sage_sync_log') or []
    log.append({**entry, 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['sage_sync_log'] = log[-100:]


# Re-export sync helpers
from accounting_waves_24 import (  # noqa: E402
    assert_fiscal_period_open,
    sage_sync_get,
    sage_sync_get_any,
    sage_sync_set,
    sage_sync_set_any,
    sage_write_guard,
)


# --- Wave 20: segments & payloads ---

def save_gl_segment_map(db, models, ledger_id: int, mapping: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_gl_segment_map'] = mapping or {}
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_segment_map', details={'keys': list((mapping or {}).keys())[:20]})
    return {'segment_map': settings['sage_gl_segment_map']}


def apply_segment_map_to_payload(settings: dict, payload: dict, *, account_number: str = '') -> dict:
    seg = settings.get('sage_gl_segment_map') or {}
    if not seg:
        return payload
    out = dict(payload)
    for i in range(1, 11):
        key = f'segment{i}'
        if key in seg and account_number:
            out[f'Segment{i}'] = seg[key]
        elif key in seg:
            out[f'Segment{i}'] = seg[key]
    if account_number and seg.get('account_prefix'):
        out['AccountNumber'] = f"{seg['account_prefix']}{account_number}"[:40]
    return out


def ap_invoice_sage_payload(doc, vendor, settings: dict) -> dict:
    gross = float(doc.gross_amount or doc.amount or 0)
    ret = float(doc.retainage_amount or 0)
    net = float(doc.amount or 0)
    payload = {
        'VendorNumber': vendor.code if vendor else '',
        'InvoiceNumber': (doc.document_number or '')[:22],
        'InvoiceDate': doc.document_date.isoformat() if doc.document_date else date.today().isoformat(),
        'InvoiceAmount': net if ret else gross,
        'Description': (doc.document_type or 'AP')[:60],
    }
    if ret > 0:
        payload['RetainageAmount'] = ret
        payload['GrossAmount'] = gross
    return apply_segment_map_to_payload(settings, payload, account_number='')


def ar_invoice_sage_payload(doc, customer, settings: dict) -> dict:
    payload = {
        'CustomerNumber': customer.code if customer else '',
        'InvoiceNumber': (doc.document_number or '')[:22],
        'InvoiceDate': doc.document_date.isoformat() if doc.document_date else date.today().isoformat(),
        'InvoiceAmount': float(doc.amount or 0),
    }
    meta = {}
    if doc.details_json:
        try:
            meta = json.loads(doc.details_json)
        except (TypeError, json.JSONDecodeError):
            meta = {}
    ret = float(meta.get('retainage_amount') or meta.get('sage', {}).get('retainage') or 0)
    if ret > 0:
        payload['RetainageAmount'] = ret
    return apply_segment_map_to_payload(settings, payload)


def sage_push_open_ap_idempotent(db, models, ledger_id: int, user_id=None, limit: int = 25) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ap', 'push')
    AcctAPDocument = models['AcctAPDocument']
    AcctVendor = models['AcctVendor']
    docs = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').order_by(AcctAPDocument.id).limit(limit).all()
    results, errors, skipped = [], [], 0
    for d in docs:
        if sage_sync_get(d, 'sync_state') in ('pushed', 'acknowledged'):
            skipped += 1
            continue
        assert_fiscal_period_open(settings, d.document_date or date.today())
        vendor = AcctVendor.query.get(d.vendor_id) if d.vendor_id else None
        payload = ap_invoice_sage_payload(d, vendor, settings)
        payload = sage_apply_tax_to_payload(settings, payload, vendor.tax_group if vendor else None)
        try:
            resp = post_resource('AP', 'APInvoices', payload)
        except Exception as exc:
            resp = {'ok': False, 'error': str(exc)}
        row = {'document_id': d.id, 'document_number': d.document_number, **resp}
        results.append(row)
        if resp.get('ok'):
            sage_sync_set(d, state='pushed', external_key=d.document_number)
        else:
            sage_sync_set(d, state='error', error=resp.get('error') or resp.get('mode'))
            errors.append(row)
    db.session.flush()
    settings['sage_last_ap_push_errors'] = errors[-25:]
    _append_sage_log(settings, {'direction': 'push', 'entity': 'open_ap_idempotent', 'count': len(results), 'skipped': skipped, 'error_count': len(errors)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_open_ap_idempotent', details={'count': len(results), 'skipped': skipped, 'errors': len(errors)})
    return {'pushed': len(results), 'skipped': skipped, 'error_count': len(errors), 'results': results, 'errors': errors}


def sage_push_open_ar_idempotent(db, models, ledger_id: int, user_id=None, limit: int = 25) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'push')
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    docs = AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').order_by(AcctARDocument.id).limit(limit).all()
    results, errors, skipped = [], [], 0
    for d in docs:
        if sage_sync_get(d, 'sync_state') in ('pushed', 'acknowledged'):
            skipped += 1
            continue
        assert_fiscal_period_open(settings, d.document_date or date.today())
        cust = AcctCustomer.query.get(d.customer_id) if d.customer_id else None
        payload = ar_invoice_sage_payload(d, cust, settings)
        payload = sage_apply_tax_to_payload(settings, payload, cust.tax_group if cust else None)
        resp = post_resource('AR', 'ARInvoices', payload)
        row = {'document_id': d.id, 'document_number': d.document_number, **resp}
        results.append(row)
        if resp.get('ok'):
            sage_sync_set(d, state='pushed', external_key=d.document_number)
        else:
            sage_sync_set(d, state='error', error=resp.get('error') or resp.get('mode'))
            errors.append(row)
    db.session.flush()
    settings['sage_last_ar_push_errors'] = errors[-25:]
    _append_sage_log(settings, {'direction': 'push', 'entity': 'open_ar_idempotent', 'count': len(results), 'skipped': skipped})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_open_ar_idempotent', details={'count': len(results), 'skipped': skipped})
    return {'pushed': len(results), 'skipped': skipped, 'error_count': len(errors), 'results': results, 'errors': errors}


def sage_push_ar_receipt_batches(db, models, ledger_id: int, user_id=None, limit: int = 20) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'push')
    AcctARReceipt = models['AcctARReceipt']
    AcctARReceiptApply = models['AcctARReceiptApply']
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    receipts = AcctARReceipt.query.filter_by(ledger_id=ledger_id, status='Posted').order_by(
        AcctARReceipt.id.desc(),
    ).limit(limit).all()
    results = []
    for rec in receipts:
        if sage_sync_get_any(settings, rec, 'sync_state') in ('pushed', 'acknowledged'):
            continue
        cust = AcctCustomer.query.get(rec.customer_id) if rec.customer_id else None
        applies = []
        for app in AcctARReceiptApply.query.filter_by(receipt_id=rec.id).all():
            doc = AcctARDocument.query.get(app.ar_document_id)
            applies.append({
                'InvoiceNumber': (doc.document_number or '')[:22] if doc else '',
                'Amount': float(app.amount or 0),
            })
        payload = {
            'ReceiptNumber': (rec.receipt_number or f'RCP-{rec.id}')[:22],
            'CustomerNumber': cust.code if cust else '',
            'ReceiptDate': rec.receipt_date.isoformat() if rec.receipt_date else date.today().isoformat(),
            'ReceiptAmount': float(rec.amount or 0),
            'Applications': applies,
        }
        resp = post_resource('AR', 'ARReceiptBatches', payload)
        results.append({'receipt_id': rec.id, **resp})
        if resp.get('ok'):
            settings = sage_sync_set_any(settings, rec, state='pushed', external_key=payload['ReceiptNumber'])
        else:
            settings = sage_sync_set_any(settings, rec, state='error', error=resp.get('error') or resp.get('mode'))
    _append_sage_log(settings, {'direction': 'push', 'entity': 'ar_receipts', 'count': len(results)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_ar_receipts', details={'count': len(results)})
    return {'processed': len(results), 'results': results}


def sage_run_paces_deploy_check(app_root: str | None = None) -> dict:
    root = app_root or os.path.abspath(os.path.dirname(__file__) or '.')
    if not (os.environ.get('SAGE_API_URL') or '').strip():
        return {'ok': True, 'skipped': True, 'reason': 'SAGE_API_URL not set'}
    script = os.path.join(root, 'scripts', 'run_sage300_paces.py')
    if not os.path.isfile(script):
        return {'ok': False, 'error': 'run_sage300_paces.py missing'}
    try:
        proc = subprocess.run(
            [os.environ.get('PYTHON', 'python3'), script, '--no-bridge'],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, 'PYTHONPATH': root},
        )
        return {'ok': proc.returncode == 0, 'detail': (proc.stdout or proc.stderr or '')[-800:]}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


# --- Wave 21: distribution ---

def sage_push_po_receipts_live(db, models, ledger_id: int, user_id=None, limit: int = 15) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'po', 'push')
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    errors = []
    pushed = 0
    for po in AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id).order_by(AcctPurchaseOrder.id.desc()).limit(limit).all():
        if (po.status or '') not in ('Received', 'Partial', 'Open'):
            continue
        payload = {'PONumber': po.po_number, 'TotalAmount': float(po.total_amount or 0), 'Status': po.status}
        resp = post_resource('PO', 'POReceipts', payload)
        if resp.get('ok'):
            pushed += 1
        else:
            errors.append({'po': po.po_number, **resp})
    _append_sage_log(settings, {'direction': 'push', 'entity': 'po_receipts', 'count': pushed, 'errors': len(errors)})
    settings['sage_distribution_errors'] = errors[-30:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_po_receipts', details={'pushed': pushed})
    return {'pushed': pushed, 'errors': errors}


def sage_push_ic_transactions(db, models, ledger_id: int, user_id=None, limit: int = 30) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ic', 'push')
    AcctInventoryTransaction = models.get('AcctInventoryTransaction')
    if not AcctInventoryTransaction:
        return {'pushed': 0, 'message': 'Inventory not enabled'}
    pushed = 0
    errors = []
    for tx in AcctInventoryTransaction.query.filter_by(ledger_id=ledger_id).order_by(
        AcctInventoryTransaction.id.desc(),
    ).limit(limit).all():
        payload = {
            'ItemCode': str(getattr(tx, 'item_id', '')),
            'Quantity': float(getattr(tx, 'qty_delta', 0) or 0),
            'TransactionType': getattr(tx, 'txn_type', 'ADJ'),
        }
        resp = post_resource('IC', 'ICTransactions', payload)
        if resp.get('ok'):
            pushed += 1
        else:
            errors.append(resp)
    settings['sage_distribution_errors'] = errors[-30:]
    _append_sage_log(settings, {'direction': 'push', 'entity': 'ic_transactions', 'count': pushed})
    _save_ledger_settings(ledger, settings)
    return {'pushed': pushed, 'errors': errors[:10]}


def sage_push_oe_shipments(db, models, ledger_id: int, user_id=None, limit: int = 15) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'oe', 'push')
    AcctSalesOrder = models.get('AcctSalesOrder')
    if not AcctSalesOrder:
        return {'pushed': 0}
    pushed = 0
    errors = []
    for so in AcctSalesOrder.query.filter_by(ledger_id=ledger_id).filter(
        AcctSalesOrder.status.in_(['Shipped', 'Invoiced', 'Open']),
    ).order_by(AcctSalesOrder.id.desc()).limit(limit).all():
        payload = {'OrderNumber': so.order_number, 'TotalAmount': float(so.total_amount or 0)}
        resp = post_resource('OE', 'OEShipments', payload)
        if resp.get('ok'):
            pushed += 1
        else:
            errors.append(resp)
    settings['sage_distribution_errors'] = errors[-30:]
    _save_ledger_settings(ledger, settings)
    return {'pushed': pushed, 'errors': errors[:10]}


def sage_pull_ic_snapshot(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ic', 'pull')
    resp = get_resource('IC', 'ICItems', top=limit)
    rows = (resp.get('data') or {}).get('value') or [] if resp.get('ok') else []
    snapshot = [{'code': r.get('ItemNumber'), 'qty': r.get('QuantityOnHand'), 'cost': r.get('AverageCost')} for r in rows[:limit]]
    settings['sage_ic_snapshot'] = {'at': datetime.utcnow().isoformat() + 'Z', 'items': snapshot}
    _save_ledger_settings(ledger, settings)
    return {'imported': len(snapshot), 'mode': resp.get('mode'), 'items': snapshot[:15]}


def sage_distribution_exception_inbox(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    return {
        'distribution_errors': (settings.get('sage_distribution_errors') or [])[-20:],
        'distribution_queue_size': len(settings.get('sage_distribution_queue') or []),
    }


# --- Wave 22: CRE portfolio ---

def sage_portfolio_ops_dashboard(db, models, ledger_id: int, Project=None, limit: int = 25) -> dict:
    from accounting_waves_24 import project_sage_ledger_reconcile

    if not Project:
        return {'projects': [], 'warning_count': 0}
    projects = []
    warnings = 0
    for p in Project.query.order_by(Project.id.desc()).limit(limit).all():
        try:
            row = project_sage_ledger_reconcile(db, models, ledger_id, p.id, Project=Project)
            if not row.get('aligned'):
                warnings += 1
            projects.append({'project_id': p.id, 'name': p.name, 'aligned': row.get('aligned'), 'items': row.get('items')})
        except Exception as exc:
            projects.append({'project_id': p.id, 'name': p.name, 'error': str(exc)})
    return {'projects': projects, 'warning_count': warnings}


def cron_reconcile_all_projects(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    reconciled = []
    for ledger in AcctLedger.query.limit(5).all():
        dash = sage_portfolio_ops_dashboard(db, models, ledger.id, Project=Project, limit=15)
        reconciled.append({'ledger_id': ledger.id, 'warnings': dash.get('warning_count')})
    return {'portfolio': reconciled}


def sage_resolve_job_actual_conflicts(db, models, ledger_id: int, project_id: int, strategy: str = 'casepm', user_id=None, Project=None) -> dict:
    from accounting_waves_24 import project_sage_ledger_reconcile

    rep = project_sage_ledger_reconcile(db, models, ledger_id, project_id, Project=Project)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    resolutions = settings.get('sage_job_resolutions') or []
    resolutions.append({
        'project_id': int(project_id),
        'strategy': strategy[:20],
        'variance': rep.get('variance'),
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['sage_job_resolutions'] = resolutions[-50:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_job_conflict_resolve', details={'project_id': project_id, 'strategy': strategy})
    return {'resolved': True, 'report': rep, 'strategy': strategy}


def sage_queue_construction_mirror_event(db, models, ledger_id: int, event_type: str, payload: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('sage_construction_mirror_queue') or []
    q.append({
        'type': event_type[:40],
        'payload': payload,
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['sage_construction_mirror_queue'] = q[-100:]
    _save_ledger_settings(ledger, settings)
    return {'queued': True, 'queue_size': len(settings['sage_construction_mirror_queue'])}


def sage_mirror_construction_reversal(db, models, ledger_id: int, source_key: str, user_id=None) -> dict:
    from accounting_waves_23 import reverse_construction_post

    out = reverse_construction_post(db, models, ledger_id, source_key, user_id=user_id, reason='sage_mirror_reversal')
    sage_queue_construction_mirror_event(
        db, models, ledger_id, 'ConstructionReversed',
        {'source_key': source_key, 'reversal_batches': out.get('reversal_batches')},
        user_id=user_id,
    )
    return out


# --- Wave 23: platform ---

def sage_route_company_code(settings: dict, project_id: int | None = None, project=None) -> str:
    companies = settings.get('sage_companies') or []
    if project and getattr(project, 'details_json', None):
        try:
            det = json.loads(project.details_json)
            co = (det.get('sage_company_code') or '').strip()
            if co:
                return co
        except (TypeError, json.JSONDecodeError):
            pass
    if companies:
        return str(companies[0].get('code') or companies[0])[:20]
    return (settings.get('default_sage_company') or '')[:20]


def enforce_fiscal_lock_for_post(db, models, ledger_id: int, txn_date: date | None = None) -> None:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    assert_fiscal_period_open(settings, txn_date or date.today())


def sage_sync_fx_rates(db, models, ledger_id: int, user_id=None) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    resp = get_resource('GL', 'GLAccounts', top=5)
    rates = settings.get('sage_fx_rates') or {}
    rates['updated_at'] = datetime.utcnow().isoformat() + 'Z'
    rates['source'] = resp.get('mode') or 'stub'
    settings['sage_fx_rates'] = rates
    settings['multi_currency_enabled'] = True
    _save_ledger_settings(ledger, settings)
    return {'ok': True, 'rates': rates}


def sage_export_consolidation_eliminations(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_parity_wave2 import auto_suggest_and_post_eliminations

    try:
        out = auto_suggest_and_post_eliminations(db, models, ledger_id, user_id=user_id)
    except TypeError:
        out = auto_suggest_and_post_eliminations(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_last_consolidation_export'] = {'at': datetime.utcnow().isoformat() + 'Z', 'result': out}
    _save_ledger_settings(ledger, settings)
    return out


def sage_queue_fa_depreciation(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctFixedAsset = models.get('AcctFixedAsset')
    AcctDepreciationRun = models.get('AcctDepreciationRun')
    queued = []
    if AcctDepreciationRun:
        for run in AcctDepreciationRun.query.filter_by(ledger_id=ledger_id, status='Posted').order_by(
            AcctDepreciationRun.id.desc(),
        ).limit(10).all():
            queued.append({'run_id': run.id, 'amount': float(run.total_amount or 0)})
    if AcctFixedAsset:
        queued.append({'asset_count': AcctFixedAsset.query.filter_by(ledger_id=ledger_id).count()})
    settings['sage_fa_export_queue'] = queued
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_fa_queue', details={'items': len(queued)})
    return {'queued': len(queued), 'items': queued}


# --- Wave 24: payroll & compliance ---

def save_payroll_sor_policy(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['payroll_system_of_record'] = (body.get('payroll_system_of_record') or 'casepm')[:20]
    settings['sage_pr_push_enabled'] = '1' if body.get('sage_pr_push_enabled') else '0'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='payroll_sor_policy', details=body)
    return {'payroll_system_of_record': settings['payroll_system_of_record'], 'sage_pr_push_enabled': settings['sage_pr_push_enabled']}


def sage_wh347_labor_variance(db, models, ledger_id: int, project_id: int, week_ending: str) -> dict:
    from accounting_waves_22 import prevailing_wage_compare_report

    return prevailing_wage_compare_report(db, models, ledger_id, project_id, week_ending, Project=None)


def sage_1099_vendor_reconcile(db, models, ledger_id: int, tax_year: int) -> dict:
    from accounting_parity_wave2 import export_1099_fire

    AcctVendor = models['AcctVendor']
    vendors = [v for v in AcctVendor.query.filter_by(ledger_id=ledger_id).all() if v.is_1099]
    try:
        export = export_1099_fire(db, models, ledger_id, tax_year)
    except TypeError:
        export = export_1099_fire(db, models, ledger_id)
    return {'vendor_count': len(vendors), 'export_preview': str(export)[:500]}


def sage_apply_tax_to_payload(settings: dict, payload: dict, tax_group: str | None) -> dict:
    groups = settings.get('sage_tax_groups') or []
    if not tax_group or not groups:
        return payload
    out = dict(payload)
    out['TaxGroup'] = tax_group[:12]
    return out


def sage_year_end_variance_report(db, models, ledger_id: int, tax_year: int) -> dict:
    from accounting_waves_22 import year_end_tax_package
    from accounting_waves_21 import sage_hybrid_exception_inbox

    pkg = year_end_tax_package(db, models, ledger_id, tax_year)
    inbox = sage_hybrid_exception_inbox(db, models, ledger_id)
    issues = len(inbox.get('ap_push_errors') or []) + len(inbox.get('vendor_conflicts') or [])
    return {
        'tax_year': tax_year,
        'w2_rows': len((pkg.get('w2') or {}).get('employees') or []),
        'form_941_issues': len((pkg.get('form_941') or {}).get('issues') or []),
        'sage_sync_issues': issues,
        'ready': issues == 0 and not (pkg.get('form_941') or {}).get('issues'),
    }


def cron_waves_20_24_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_24 import cron_sage_mirror_maintenance

    mirror = cron_sage_mirror_maintenance(db, models, secret)
    portfolio = cron_reconcile_all_projects(db, models, secret, Project=Project)
    paces = sage_run_paces_deploy_check()
    return {'sage_mirror': mirror, 'portfolio': portfolio, 'paces': paces}
