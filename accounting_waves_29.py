"""
Waves 37–40 — tax/document parity, distribution mirror, FA round-trip, PR & multi-entity platform.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import (
    SAGE_MIRROR_CAPABILITIES,
    _ledger_settings,
    _save_ledger_settings,
    sage_sync_get,
    sage_sync_set,
    sage_write_guard,
)
from accounting_waves_25 import (
    ap_invoice_sage_payload,
    ar_invoice_sage_payload,
    sage_apply_tax_to_payload,
)
from accounting_waves_27 import apply_line_tax_to_document, external_key_register
from accounting_waves_28 import validate_fixture_against_profile, get_pack_profile


# --- Wave 37: tax & document parity ---

def enrich_payload_with_line_tax(doc, payload: dict) -> dict:
    meta = {}
    if getattr(doc, 'details_json', None):
        try:
            meta = json.loads(doc.details_json)
        except (TypeError, json.JSONDecodeError):
            meta = {}
    line_tax = meta.get('line_tax') or []
    tax_meta = meta.get('tax') or {}
    out = dict(payload)
    if tax_meta.get('tax_group'):
        out['TaxGroup'] = str(tax_meta['tax_group'])[:12]
    if line_tax:
        out['TaxLines'] = [
            {
                'TaxGroup': (ln.get('tax_group') or out.get('TaxGroup') or '')[:12],
                'TaxableAmount': float(ln.get('taxable_amount') or ln.get('amount') or 0),
                'TaxAmount': float(ln.get('tax_amount') or 0),
            }
            for ln in line_tax[:50]
        ]
    return out


def sage_sync_document_tax_before_push(db, models, ledger_id: int, document_type: str, document_id: int, user_id=None) -> dict:
    apply_line_tax_to_document(db, models, ledger_id, document_type, document_id, user_id=user_id)
    cls = models['AcctAPDocument'] if document_type == 'ap' else models['AcctARDocument']
    doc = cls.query.filter_by(id=int(document_id), ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('Document not found')
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if document_type == 'ap':
        vendor = models['AcctVendor'].query.get(doc.vendor_id) if doc.vendor_id else None
        payload = ap_invoice_sage_payload(doc, vendor, settings)
        payload = sage_apply_tax_to_payload(settings, payload, getattr(vendor, 'tax_group', None))
    else:
        customer = models['AcctCustomer'].query.get(doc.customer_id) if doc.customer_id else None
        payload = ar_invoice_sage_payload(doc, customer, settings)
    payload = enrich_payload_with_line_tax(doc, payload)
    return {'document_id': doc.id, 'payload_preview': payload, 'has_tax_lines': bool(payload.get('TaxLines'))}


def sage_push_document_tax_batch(db, models, ledger_id: int, document_type: str = 'ap', user_id=None, limit: int = 20) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'tx' if document_type == 'ap' else 'ar', 'push')
    cls = models['AcctAPDocument'] if document_type == 'ap' else models['AcctARDocument']
    module = 'AP' if document_type == 'ap' else 'AR'
    resource = 'APInvoices' if document_type == 'ap' else 'ARInvoices'
    pushed = errors = 0
    err_rows = []
    for doc in cls.query.filter_by(ledger_id=ledger_id, status='Open').order_by(cls.id).limit(limit).all():
        try:
            sage_sync_document_tax_before_push(db, models, ledger_id, document_type, doc.id, user_id=user_id)
        except Exception as exc:
            errors += 1
            err_rows.append({'document_id': doc.id, 'error': str(exc)[:120]})
            continue
        if document_type == 'ap':
            vendor = models['AcctVendor'].query.get(doc.vendor_id) if doc.vendor_id else None
            payload = enrich_payload_with_line_tax(
                doc,
                sage_apply_tax_to_payload(
                    settings,
                    ap_invoice_sage_payload(doc, vendor, settings),
                    getattr(vendor, 'tax_group', None),
                ),
            )
        else:
            customer = models['AcctCustomer'].query.get(doc.customer_id) if doc.customer_id else None
            payload = enrich_payload_with_line_tax(doc, ar_invoice_sage_payload(doc, customer, settings))
        resp = post_resource(module, resource, payload)
        if resp.get('ok'):
            pushed += 1
            sage_sync_set(doc, state='pushed', external_key=doc.document_number)
        else:
            errors += 1
            err_rows.append({'document_id': doc.id, **resp})
    db.session.flush()
    settings['sage_tax_push_log'] = (settings.get('sage_tax_push_log') or [])[-15:] + [
        {'at': datetime.utcnow().isoformat() + 'Z', 'type': document_type, 'pushed': pushed, 'errors': errors},
    ]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_tax_push_batch', details={'type': document_type, 'pushed': pushed})
    return {'pushed': pushed, 'errors': errors, 'error_rows': err_rows[:10]}


def filing_bundle_with_transmit_log(db, models, ledger_id: int, tax_year: int, user_id=None) -> dict:
    from accounting_waves_28 import filing_bundle_download

    bundle = filing_bundle_download(db, models, ledger_id, tax_year, user_id=user_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    transmit = settings.get('efile_transmit_log') or []
    return {
        **bundle,
        'transmit_log': transmit[-25:],
        'transmit_count': len(transmit),
    }


# --- Wave 38: distribution mirror ---

def sage_pull_po_statuses(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'po', 'pull')
    resp = get_resource('PO', 'POPurchaseOrders', top=limit)
    if not resp.get('ok'):
        return {'updated': 0, 'mode': resp.get('mode'), 'message': resp.get('error')}
    AcctPurchaseOrder = models['AcctPurchaseOrder']
    updated = 0
    for row in (resp.get('data') or {}).get('value') or []:
        num = (row.get('PONumber') or row.get('PurchaseOrderNumber') or '').strip()
        if not num:
            continue
        po = AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id, po_number=num).first()
        if not po:
            continue
        status = (row.get('Status') or row.get('OrderStatus') or po.status or 'Open')[:20]
        po.status = status
        po.total_amount = float(row.get('OrderTotal') or row.get('TotalAmount') or po.total_amount or 0)
        updated += 1
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_po_status', details={'updated': updated})
    return {'updated': updated, 'mode': resp.get('mode')}


def sage_pull_distribution_inventory_status(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from accounting_waves_27 import sage_pull_ic_oe_upsert

    base = sage_pull_ic_oe_upsert(db, models, ledger_id, user_id=user_id, limit=limit)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_last_distribution_pull_at'] = datetime.utcnow().isoformat() + 'Z'
    _save_ledger_settings(ledger, settings)
    return base


def po_three_way_sage_summary(db, models, ledger_id: int, limit: int = 30) -> dict:
    from accounting_ap_extended import three_way_match

    AcctAPDocument = models['AcctAPDocument']
    exceptions = []
    matched = 0
    for doc in AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').order_by(
        AcctAPDocument.id.desc(),
    ).limit(limit).all():
        if not doc.purchase_order_id and not doc.po_reference:
            continue
        m = three_way_match(db, models, ledger_id, doc.id)
        row = {
            'invoice_id': doc.id,
            'document_number': doc.document_number,
            'sage_sync': sage_sync_get(doc, 'sync_state'),
            **m,
        }
        if m.get('matched'):
            matched += 1
        else:
            exceptions.append(row)
    return {'matched': matched, 'exception_count': len(exceptions), 'exceptions': exceptions[:15]}


def cron_distribution_parity(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_25 import sage_push_po_receipts_live, sage_distribution_exception_inbox

    AcctLedger = models['AcctLedger']
    out = []
    for ledger in AcctLedger.query.limit(10).all():
        po_pull = sage_pull_po_statuses(db, models, ledger.id)
        ic_oe = sage_pull_distribution_inventory_status(db, models, ledger.id)
        push = sage_push_po_receipts_live(db, models, ledger.id)
        inbox = sage_distribution_exception_inbox(db, models, ledger.id)
        out.append({'ledger_id': ledger.id, 'po_pull': po_pull, 'ic_oe': ic_oe, 'po_push': push, 'inbox': inbox})
    return {'ledgers': out}


# --- Wave 39: fixed assets ---

def sage_pull_fa_assets(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'fa', 'pull')
    resp = get_resource('FA', 'FAAssets', top=limit)
    if not resp.get('ok'):
        return {'created': 0, 'updated': 0, 'mode': resp.get('mode')}
    AcctFixedAsset = models.get('AcctFixedAsset')
    if not AcctFixedAsset:
        return {'created': 0, 'updated': 0, 'message': 'FA module not enabled'}
    created = updated = 0
    for row in (resp.get('data') or {}).get('value') or []:
        num = (row.get('AssetNumber') or row.get('AssetCode') or '').strip()
        if not num:
            continue
        asset = AcctFixedAsset.query.filter_by(ledger_id=ledger_id, asset_number=num).first()
        if not asset:
            asset = AcctFixedAsset(
                ledger_id=ledger_id,
                asset_number=num[:40],
                description=(row.get('Description') or num)[:200],
                acquisition_cost=float(row.get('AcquisitionCost') or row.get('Cost') or 0),
                status='Active',
            )
            db.session.add(asset)
            created += 1
        else:
            updated += 1
        asset.description = (row.get('Description') or asset.description or num)[:200]
        asset.acquisition_cost = float(row.get('AcquisitionCost') or asset.acquisition_cost or 0)
        nbv = row.get('NetBookValue') or row.get('BookValue')
        if nbv is not None and hasattr(asset, 'net_book_value'):
            asset.net_book_value = float(nbv)
        settings = external_key_register(settings, 'fa_asset', asset.id, num)
    db.session.flush()
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_fa', details={'created': created, 'updated': updated})
    return {'created': created, 'updated': updated, 'mode': resp.get('mode')}


def sage_fa_depreciation_variance(db, models, ledger_id: int) -> dict:
    from accounting_waves_26 import sage_push_fa_assets_live
    from accounting_waves_27 import sage_ack_fa_depreciation_queue

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctFixedAsset = models.get('AcctFixedAsset')
    local_nbv = 0.0
    if AcctFixedAsset:
        for a in AcctFixedAsset.query.filter_by(ledger_id=ledger_id, status='Active').limit(200).all():
            local_nbv += float(getattr(a, 'net_book_value', None) or getattr(a, 'acquisition_cost', 0) or 0)
    push = sage_push_fa_assets_live(db, models, ledger_id)
    ack = sage_ack_fa_depreciation_queue(db, models, ledger_id)
    sage_nbv = float((settings.get('sage_fa_nbv_snapshot') or {}).get('total') or 0)
    variance = abs(local_nbv - sage_nbv) if sage_nbv else 0.0
    report = {
        'local_nbv_total': round(local_nbv, 2),
        'sage_nbv_snapshot': sage_nbv,
        'variance': round(variance, 2),
        'push': push,
        'ack': ack,
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    settings['sage_fa_variance_report'] = report
    _save_ledger_settings(ledger, settings)
    return report


def fa_mirror_dashboard(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctFixedAsset = models.get('AcctFixedAsset')
    count = AcctFixedAsset.query.filter_by(ledger_id=ledger_id).count() if AcctFixedAsset else 0
    return {
        'asset_count': count,
        'export_queue': len(settings.get('sage_fa_export_queue') or []),
        'push_errors': (settings.get('sage_fa_push_errors') or [])[-5:],
        'variance': settings.get('sage_fa_variance_report') or {},
        'capabilities': SAGE_MIRROR_CAPABILITIES.get('fa'),
    }


# --- Wave 40: payroll & multi-entity ---

def sage_pull_pr_employees(db, models, ledger_id: int, user_id=None, limit: int = 100) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'pr', 'pull')
    resp = get_resource('PR', 'PREmployees', top=limit)
    if not resp.get('ok'):
        return {'imported': 0, 'mode': resp.get('mode')}
    rows = (resp.get('data') or {}).get('value') or []
    settings['sage_pr_employee_cache'] = [
        {
            'code': (r.get('EmployeeNumber') or r.get('EmployeeCode') or '')[:20],
            'name': (r.get('EmployeeName') or r.get('Name') or '')[:80],
        }
        for r in rows[:limit]
    ]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_pr_employees', details={'count': len(rows)})
    return {'imported': len(rows), 'mode': resp.get('mode')}


def sage_push_payroll_run_live(db, models, ledger_id: int, run_id: int, user_id=None) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if settings.get('sage_pr_push_enabled') != '1':
        return {'skipped': True, 'reason': 'sage_pr_push_enabled off'}
    if (settings.get('payroll_system_of_record') or 'casepm') == 'sage':
        return {'skipped': True, 'reason': 'Sage is payroll system of record'}
    sage_write_guard(settings, 'pr', 'push')
    AcctPayrollRun = models['AcctPayrollRun']
    run = AcctPayrollRun.query.filter_by(id=int(run_id), ledger_id=ledger_id).first()
    if not run:
        raise ValueError('Payroll run not found')
    payload = {
        'PayRunNumber': (run.run_number or f'PR-{run.id}')[:22],
        'PayDate': (run.pay_date.isoformat() if run.pay_date else date.today().isoformat()),
        'GrossPay': float(run.total_gross or 0),
        'NetPay': float(getattr(run, 'total_net', None) or run.total_gross or 0),
    }
    resp = post_resource('PR', 'PRPayRuns', payload)
    if resp.get('ok'):
        settings['sage_pr_last_push'] = {'run_id': run.id, 'at': datetime.utcnow().isoformat() + 'Z'}
        _save_ledger_settings(ledger, settings)
    else:
        q = settings.get('sage_pr_export_queue') or []
        q.append({'run_id': run.id, 'error': str(resp)[:200]})
        settings['sage_pr_export_queue'] = q[-30:]
        _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_pr_run', details={'run_id': run.id, 'ok': resp.get('ok')})
    return {'run_id': run.id, **resp}


def sage_pull_fiscal_calendar(db, models, ledger_id: int, user_id=None) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    resp = get_resource('GL', 'GLFiscalCalendars', top=5)
    periods = []
    if resp.get('ok'):
        for row in (resp.get('data') or {}).get('value') or []:
            periods.append({
                'year': row.get('FiscalYear') or row.get('Year'),
                'period': row.get('Period') or row.get('FiscalPeriod'),
                'status': row.get('Status') or row.get('PeriodStatus'),
            })
    locked = ''
    for p in periods:
        if str(p.get('status', '')).lower() in ('closed', 'locked'):
            locked = f"{p.get('year')}-{p.get('period')}"
    if locked:
        settings['sage_fiscal_locked_through'] = locked
    settings['sage_fiscal_calendar'] = periods[:24]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_fiscal_calendar', details={'periods': len(periods)})
    return {'periods': periods, 'locked_through': settings.get('sage_fiscal_locked_through'), 'mode': resp.get('mode')}


def consolidated_multi_company_health(db, models) -> dict:
    from accounting_waves_28 import resolve_ledger_for_company, sage_sync_health_score

    AcctLedger = models['AcctLedger']
    companies = []
    for ledger in AcctLedger.query.limit(20).all():
        settings = _ledger_settings(ledger)
        for co in settings.get('sage_companies') or []:
            code = co.get('code') if isinstance(co, dict) else str(co)
            if not code:
                continue
            resolved = resolve_ledger_for_company(db, models, code)
            health = sage_sync_health_score(db, models, resolved.get('ledger_id') or ledger.id)
            companies.append({'company_code': code, 'ledger_id': resolved.get('ledger_id'), 'health': health})
    if not companies:
        for ledger in AcctLedger.query.limit(5).all():
            companies.append({
                'company_code': None,
                'ledger_id': ledger.id,
                'health': sage_sync_health_score(db, models, ledger.id),
            })
    avg = sum((c['health'].get('score') or 0) for c in companies) / max(1, len(companies))
    return {'companies': companies, 'average_score': round(avg, 1)}


def cron_waves_37_40_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_28 import cron_waves_33_36_maintenance

    base = cron_waves_33_36_maintenance(db, models, secret, Project=Project)
    dist = cron_distribution_parity(db, models, secret)
    fa_pulls = []
    pr_pulls = []
    AcctLedger = models['AcctLedger']
    for ledger in AcctLedger.query.limit(5).all():
        fa_pulls.append(sage_pull_fa_assets(db, models, ledger.id))
        pr_pulls.append(sage_pull_pr_employees(db, models, ledger.id))
        sage_pull_fiscal_calendar(db, models, ledger.id)
    return {
        'enterprise': base,
        'distribution': dist,
        'fa_pulls': fa_pulls,
        'pr_pulls': pr_pulls,
        'multi_company_health': consolidated_multi_company_health(db, models),
    }


def sage_mirror_deploy_check_v5() -> dict:
    from accounting_waves_28 import sage_mirror_deploy_check_v4

    base = sage_mirror_deploy_check_v4()
    profile = get_pack_profile()
    ap_fix = validate_fixture_against_profile('ap_invoice_sample.json', profile)
    ar_fix = validate_fixture_against_profile('ar_invoice_sample.json', profile)
    caps = SAGE_MIRROR_CAPABILITIES
    parity = all(caps.get(m, {}).get('pull') for m in ('po', 'ic', 'oe')) and caps.get('fa', {}).get('pull') and caps.get('pr', {}).get('pull')
    ok = base.get('ok') and ap_fix.get('ok') and ar_fix.get('ok') and parity
    return {
        'ok': ok,
        'v4': base,
        'ap_fixture': ap_fix,
        'ar_fixture': ar_fix,
        'capability_parity': parity,
    }


def update_mirror_capabilities_wave_37_40() -> None:
    """Register pull/push parity for waves 37–40 (idempotent)."""
    SAGE_MIRROR_CAPABILITIES['tx'] = {**SAGE_MIRROR_CAPABILITIES.get('tx', {}), 'push': True, 'notes': 'Tax groups pull; line tax push on AP/AR'}
    SAGE_MIRROR_CAPABILITIES['po'] = {**SAGE_MIRROR_CAPABILITIES.get('po', {}), 'pull': True, 'notes': 'PO status pull; receipt push'}
    SAGE_MIRROR_CAPABILITIES['ic'] = {**SAGE_MIRROR_CAPABILITIES.get('ic', {}), 'pull': True, 'notes': 'IC items pull; adjustment push'}
    SAGE_MIRROR_CAPABILITIES['oe'] = {**SAGE_MIRROR_CAPABILITIES.get('oe', {}), 'pull': True, 'notes': 'OE orders pull; shipment push'}
    SAGE_MIRROR_CAPABILITIES['fa'] = {**SAGE_MIRROR_CAPABILITIES.get('fa', {}), 'pull': True, 'notes': 'FA assets pull; depreciation push/ack'}
    SAGE_MIRROR_CAPABILITIES['pr'] = {**SAGE_MIRROR_CAPABILITIES.get('pr', {}), 'pull': True, 'notes': 'PR employees pull; pay run push'}


update_mirror_capabilities_wave_37_40()
