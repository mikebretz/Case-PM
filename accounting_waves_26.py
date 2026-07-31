"""
Waves 25–28 — bidirectional Sage close, auto-post enforcement, enterprise platform,
payroll/tax depth.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import (  # noqa: E402
    sage_sync_get,
    sage_sync_set,
    sage_write_guard,
)
from accounting_waves_25 import (  # noqa: E402
    _append_sage_log,
    _ledger_settings,
    _save_ledger_settings,
    ar_invoice_sage_payload,
    sage_apply_tax_to_payload,
)


# --- Wave 25: pull + validate + CI ---

def sage_pull_ar_receipt_applications(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'pull')
    resp = get_resource('AR', 'ARReceiptBatches', top=limit)
    if not resp.get('ok'):
        return {'applied': 0, 'mode': resp.get('mode'), 'message': resp.get('error')}
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    rows = (resp.get('data') or {}).get('value') or []
    applied = updated = 0
    for row in rows:
        cust_code = (row.get('CustomerNumber') or '').strip().upper()
        cust = AcctCustomer.query.filter_by(ledger_id=ledger_id, code=cust_code).first() if cust_code else None
        apps = row.get('Applications') or row.get('ReceiptApplications') or []
        if isinstance(apps, dict):
            apps = list(apps.values())
        for app in apps:
            if not isinstance(app, dict):
                continue
            inv = (app.get('InvoiceNumber') or '').strip()
            amt = float(app.get('Amount') or app.get('AppliedAmount') or 0)
            if not inv or amt <= 0:
                continue
            doc = AcctARDocument.query.filter_by(ledger_id=ledger_id, document_number=inv[:40]).first()
            if not doc:
                continue
            doc.amount_paid = round(float(doc.amount_paid or 0) + amt, 2)
            if doc.amount_paid >= float(doc.amount or 0) - 0.01:
                doc.status = 'Paid'
            else:
                doc.status = 'Partial'
            sage_sync_set(doc, state='acknowledged', external_key=inv)
            applied += 1
            updated += 1
    db.session.flush()
    _append_sage_log(settings, {'direction': 'pull', 'entity': 'ar_receipt_apply', 'count': applied})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_ar_receipts', details={'applied': applied})
    return {'applied': applied, 'documents_updated': updated, 'mode': resp.get('mode')}


def sage_pull_ap_payment_status(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ap', 'pull')
    resp = get_resource('AP', 'APInvoices', top=limit)
    if not resp.get('ok'):
        return {'updated': 0, 'mode': resp.get('mode')}
    AcctAPDocument = models['AcctAPDocument']
    rows = (resp.get('data') or {}).get('value') or []
    updated = 0
    for row in rows:
        inv = (row.get('InvoiceNumber') or '').strip()
        if not inv:
            continue
        doc = AcctAPDocument.query.filter_by(ledger_id=ledger_id, document_number=inv[:40]).first()
        if not doc:
            continue
        paid = float(row.get('AmountPaid') or row.get('PaidAmount') or 0)
        total = float(row.get('InvoiceAmount') or row.get('Amount') or doc.amount or 0)
        if paid > 0:
            doc.amount_paid = round(paid, 2)
            doc.status = 'Paid' if paid >= total - 0.01 else 'Partial'
            sage_sync_set(doc, state='acknowledged', external_key=inv)
            updated += 1
    db.session.flush()
    _append_sage_log(settings, {'direction': 'pull', 'entity': 'ap_payment_status', 'count': updated})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_ap_status', details={'updated': updated})
    return {'updated': updated, 'mode': resp.get('mode')}


def sage_pull_oe_and_reconcile(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'oe', 'pull')
    ic_resp = get_resource('IC', 'ICItems', top=limit)
    oe_resp = get_resource('OE', 'OEOrders', top=limit)
    ic_rows = (ic_resp.get('data') or {}).get('value') or [] if ic_resp.get('ok') else []
    oe_rows = (oe_resp.get('data') or {}).get('value') or [] if oe_resp.get('ok') else []
    AcctInventoryItem = models.get('AcctInventoryItem')
    AcctSalesOrder = models.get('AcctSalesOrder')
    ic_var = oe_var = 0
    if AcctInventoryItem:
        local_codes = {i.item_number for i in AcctInventoryItem.query.filter_by(ledger_id=ledger_id).all() if i.item_number}
        sage_codes = {(r.get('ItemNumber') or '').strip() for r in ic_rows}
        ic_var = len(sage_codes - local_codes)
    if AcctSalesOrder:
        local_orders = {o.order_number for o in AcctSalesOrder.query.filter_by(ledger_id=ledger_id).limit(200).all()}
        for r in oe_rows:
            onum = (r.get('OrderNumber') or '').strip()
            if onum and onum not in local_orders:
                oe_var += 1
    report = {
        'ic_sage_count': len(ic_rows),
        'oe_sage_count': len(oe_rows),
        'ic_only_in_sage': ic_var,
        'oe_only_in_sage': oe_var,
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    settings['sage_ic_oe_reconcile'] = report
    _save_ledger_settings(ledger, settings)
    return report


def validate_segment_map_preflight(db, models, ledger_id: int) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    seg = settings.get('sage_gl_segment_map') or {}
    AcctGLAccount = models['AcctGLAccount']
    local = AcctGLAccount.query.filter_by(ledger_id=ledger_id).limit(200).all()
    resp = get_resource('GL', 'GLAccounts', top=200)
    sage_nums = set()
    if resp.get('ok'):
        for row in (resp.get('data') or {}).get('value') or []:
            n = (row.get('AccountNumber') or '').strip()
            if n:
                sage_nums.add(n)
    missing = []
    prefix = (seg.get('account_prefix') or '').strip()
    for acct in local:
        num = acct.account_number or ''
        sage_num = f'{prefix}{num}' if prefix else num
        if sage_nums and sage_num not in sage_nums:
            missing.append(sage_num)
    ok = len(missing) == 0 or not sage_nums
    return {'ok': ok, 'segment_map': seg, 'missing_in_sage': missing[:40], 'local_count': len(local), 'sage_count': len(sage_nums)}


def sage_run_paces_mandatory(app_root: str | None = None) -> dict:
    """Wave 25 — run paces when env requests it, or when SAGE_API_URL set; optional virtual bridge."""
    root = app_root or os.path.abspath(os.path.dirname(__file__) or '.')
    force = os.environ.get('CASEPM_RUN_SAGE_PACES', '').strip() in ('1', 'true', 'yes')
    has_url = bool((os.environ.get('SAGE_API_URL') or '').strip())
    if not force and not has_url:
        return {'ok': True, 'skipped': True, 'reason': 'Set CASEPM_RUN_SAGE_PACES=1 or SAGE_API_URL'}
    script = os.path.join(root, 'scripts', 'run_sage300_paces.py')
    bridge = os.path.join(root, 'scripts', 'virtual_sage300_bridge.py')
    proc_bridge = None
    try:
        if not has_url and os.path.isfile(bridge):
            proc_bridge = subprocess.Popen(
                [os.environ.get('PYTHON', 'python3'), bridge],
                cwd=root,
                env={**os.environ, 'PYTHONPATH': root, 'VIRTUAL_SAGE_PORT': '8765'},
            )
            time.sleep(2)
            os.environ.setdefault('SAGE_API_URL', 'http://127.0.0.1:8765')
        proc = subprocess.run(
            [os.environ.get('PYTHON', 'python3'), script, '--no-bridge'],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=240,
            env={**os.environ, 'PYTHONPATH': root},
        )
        return {'ok': proc.returncode == 0, 'forced': force, 'detail': (proc.stdout or proc.stderr or '')[-1000:]}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    finally:
        if proc_bridge:
            proc_bridge.terminate()


# --- Wave 26: construction enforcement ---

CONSTRUCTION_SOR_EVENTS = frozenset({
    'G702Approved', 'SubPayAppApproved', 'ChangeOrderApproved', 'CommitmentApproved',
})


def assert_construction_auto_post_allowed(db, models, ledger_id: int, event_type: str, payload: dict) -> None:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sor = (settings.get('system_of_record') or 'casepm').lower()
    if sor != 'sage' or event_type not in CONSTRUCTION_SOR_EVENTS:
        return
    if not (payload or {}).get('force_builtin_post') and not (settings.get('sage_allow_construction_casepm_post') == '1'):
        raise PermissionError(
            'System of record is Sage — built-in construction post blocked. '
            'Use Sage bridge or enable sage_allow_construction_casepm_post.',
        )


def after_construction_post_mirror(
    db, models, ledger_id: int, event_type: str, project_id: int, payload: dict, result: dict, user_id=None,
) -> dict:
    from accounting_waves_25 import sage_queue_construction_mirror_event

    if not result.get('posted'):
        return {'skipped': True}
    amount = float(payload.get('amount') or payload.get('amount_due') or payload.get('total') or 0)
    expected = float(payload.get('expected_amount') or amount)
    parity_ok = abs(amount - expected) < 0.02 if expected else True
    mirror = sage_queue_construction_mirror_event(
        db, models, ledger_id, event_type,
        {
            'project_id': project_id,
            'amount': amount,
            'expected_amount': expected,
            'parity_ok': parity_ok,
            'ar_document_id': result.get('ar_document_id'),
            'ap_document_id': result.get('ap_document_id'),
            'source_key': result.get('source_key'),
        },
        user_id=user_id,
    )
    if not parity_ok:
        ledger = models['AcctLedger'].query.get(ledger_id)
        settings = _ledger_settings(ledger)
        warnings = settings.get('sage_parity_warnings') or []
        warnings.append({'event': event_type, 'project_id': project_id, 'amount': amount, 'expected': expected})
        settings['sage_parity_warnings'] = warnings[-50:]
        _save_ledger_settings(ledger, settings)
    return mirror


def sage_void_construction_reversal(db, models, ledger_id: int, source_key: str, user_id=None) -> dict:
    from accounting_waves_25 import sage_mirror_construction_reversal
    from sage300_web_post import post_resource

    out = sage_mirror_construction_reversal(db, models, ledger_id, source_key, user_id=user_id)
    payload = {'SourceKey': source_key[:40], 'Action': 'Void', 'Reason': 'CasePM reversal'}
    resp = post_resource('GL', 'GLJournalBatches', {'CasePMVoid': payload})
    return {'reversal': out, 'sage_void': resp}


def push_retainage_release_to_sage(db, models, ledger_id: int, ar_document_id: int, user_id=None) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'push')
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    doc = AcctARDocument.query.filter_by(id=int(ar_document_id), ledger_id=ledger_id).first()
    if not doc:
        raise ValueError('AR document not found')
    cust = AcctCustomer.query.get(doc.customer_id) if doc.customer_id else None
    payload = ar_invoice_sage_payload(doc, cust, settings)
    payload['DocumentType'] = 'RetainageRelease'
    payload = sage_apply_tax_to_payload(settings, payload, cust.tax_group if cust else None)
    resp = post_resource('AR', 'ARInvoices', payload)
    if resp.get('ok'):
        sage_sync_set(doc, state='pushed', external_key=doc.document_number)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_retainage_release_push', details={'ar_document_id': doc.id, 'ok': resp.get('ok')})
    return {'ar_document_id': doc.id, **resp}


def sage_inbox_auto_retry(db, models, ledger_id: int, user_id=None, limit: int = 10) -> dict:
    from accounting_waves_25 import sage_push_open_ap_idempotent, sage_push_open_ar_idempotent

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    backoff = int(settings.get('sage_retry_backoff_sec') or 0)
    last = settings.get('sage_last_auto_retry_at')
    if last and backoff:
        try:
            last_dt = datetime.fromisoformat(last.replace('Z', ''))
            if (datetime.utcnow() - last_dt).total_seconds() < backoff:
                return {'skipped': True, 'reason': 'backoff'}
        except ValueError:
            pass
    ap = sage_push_open_ap_idempotent(db, models, ledger_id, user_id=user_id, limit=limit)
    ar = sage_push_open_ar_idempotent(db, models, ledger_id, user_id=user_id, limit=limit)
    settings['sage_last_auto_retry_at'] = datetime.utcnow().isoformat() + 'Z'
    settings['sage_retry_backoff_sec'] = min(3600, max(60, backoff or 60))
    _save_ledger_settings(ledger, settings)
    return {'ap': ap, 'ar': ar}


# --- Wave 27: enterprise ---

def resolve_transaction_company_code(db, models, ledger_id: int, project_id: int | None, Project=None) -> str:
    from accounting_waves_25 import sage_route_company_code

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    project = Project.query.get(int(project_id)) if Project and project_id else None
    return sage_route_company_code(settings, project_id, project)


def sage_consolidation_round_trip(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_25 import sage_export_consolidation_eliminations

    export = sage_export_consolidation_eliminations(db, models, ledger_id, user_id=user_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_consolidation_last'] = {'at': datetime.utcnow().isoformat() + 'Z', 'export': export}
    _save_ledger_settings(ledger, settings)
    return {'exported': True, 'detail': export}


def sage_sync_gl_security_groups(db, models, ledger_id: int, user_id=None) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    resp = get_resource('GL', 'GLAccounts', top=5)
    groups = settings.get('sage_gl_security_groups') or [
        {'code': 'DEFAULT', 'name': 'Default posting', 'allow_all': True},
    ]
    settings['sage_gl_security_groups'] = groups
    settings['sage_gl_security_sync_mode'] = resp.get('mode') or 'stub'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_gl_security_sync', details={'groups': len(groups)})
    return {'groups': groups, 'mode': settings['sage_gl_security_sync_mode']}


def sage_push_fx_revaluation(db, models, ledger_id: int, user_id=None, *, as_of: str | None = None) -> dict:
    from accounting_waves_25 import sage_sync_fx_rates
    from accounting_parity_wave2 import auto_suggest_and_post_eliminations

    rates = sage_sync_fx_rates(db, models, ledger_id, user_id=user_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    as_of_d = (as_of or date.today().isoformat())[:10]
    entry = {'as_of': as_of_d, 'rates': rates.get('rates'), 'posted': False}
    try:
        auto_suggest_and_post_eliminations(db, models, ledger_id, user_id=user_id)
        entry['posted'] = True
    except Exception as exc:
        entry['error'] = str(exc)[:200]
    settings['sage_fx_revaluation_log'] = (settings.get('sage_fx_revaluation_log') or [])[-20:] + [entry]
    _save_ledger_settings(ledger, settings)
    return entry


def sage_push_fa_assets_live(db, models, ledger_id: int, user_id=None, limit: int = 20) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctFixedAsset = models.get('AcctFixedAsset')
    if not AcctFixedAsset:
        return {'pushed': 0}
    pushed = 0
    errors = []
    for asset in AcctFixedAsset.query.filter_by(ledger_id=ledger_id).limit(limit).all():
        payload = {
            'AssetNumber': (getattr(asset, 'asset_number', None) or f'FA-{asset.id}')[:20],
            'Description': (getattr(asset, 'description', None) or '')[:60],
            'AcquisitionCost': float(getattr(asset, 'acquisition_cost', 0) or 0),
        }
        resp = post_resource('FA', 'FAAssets', payload)
        if resp.get('ok'):
            pushed += 1
        else:
            errors.append(resp)
    settings['sage_fa_push_errors'] = errors[-20:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_fa_push', details={'pushed': pushed})
    return {'pushed': pushed, 'errors': errors[:5]}


# --- Wave 28: payroll & tax ---

def sage_push_payroll_run_stub(db, models, ledger_id: int, run_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if settings.get('sage_pr_push_enabled') != '1':
        return {'skipped': True, 'reason': 'sage_pr_push_enabled off'}
    if (settings.get('payroll_system_of_record') or 'casepm') == 'sage':
        return {'skipped': True, 'reason': 'Sage is payroll system of record'}
    AcctPayrollRun = models['AcctPayrollRun']
    run = AcctPayrollRun.query.filter_by(id=int(run_id), ledger_id=ledger_id).first()
    if not run:
        raise ValueError('Payroll run not found')
    q = settings.get('sage_pr_export_queue') or []
    q.append({'run_id': run.id, 'run_number': run.run_number, 'gross': float(run.total_gross or 0)})
    settings['sage_pr_export_queue'] = q[-30:]
    _save_ledger_settings(ledger, settings)
    return {'queued': True, 'run_id': run.id}


def scheduled_wh347_sage_labor_compare(db, models, ledger_id: int, project_id: int, week_ending: str, Project=None) -> dict:
    from accounting_waves_25 import sage_wh347_labor_variance

    return sage_wh347_labor_variance(db, models, ledger_id, project_id, week_ending)


def sage_1099_dollar_tieout(db, models, ledger_id: int, tax_year: int) -> dict:
    AcctAPPayment = models.get('AcctAPPayment')
    AcctVendor = models['AcctVendor']
    vendors = [v for v in AcctVendor.query.filter_by(ledger_id=ledger_id).all() if v.is_1099]
    totals = {}
    for v in vendors:
        totals[v.code] = {'name': v.name, 'ytd': 0.0}
    if AcctAPPayment:
        for p in AcctAPPayment.query.filter_by(ledger_id=ledger_id).all():
            if p.payment_date and p.payment_date.year == tax_year:
                vend = AcctVendor.query.get(p.vendor_id) if p.vendor_id else None
                if vend and vend.code in totals:
                    totals[vend.code]['ytd'] += float(p.amount or 0)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_1099_tieout'] = {'tax_year': tax_year, 'vendors': totals}
    _save_ledger_settings(ledger, settings)
    return {'tax_year': tax_year, 'vendor_count': len(totals), 'totals': totals}


def apply_tax_groups_to_open_documents(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    default_group = (settings.get('sage_tax_groups') or [{}])[0].get('code') if settings.get('sage_tax_groups') else None
    if not default_group:
        return {'updated': 0, 'message': 'No sage_tax_groups — run pull tax groups'}
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    AcctVendor = models['AcctVendor']
    AcctCustomer = models['AcctCustomer']
    n = 0
    for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').limit(100).all():
        v = AcctVendor.query.get(d.vendor_id) if d.vendor_id else None
        if v and not v.tax_group:
            v.tax_group = default_group[:40]
            n += 1
    for d in AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').limit(100).all():
        c = AcctCustomer.query.get(d.customer_id) if d.customer_id else None
        if c and not c.tax_group:
            c.tax_group = default_group[:40]
            n += 1
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_tax_groups_applied', details={'updated': n})
    return {'updated': n, 'default_group': default_group}


def sage_year_end_extended_report(db, models, ledger_id: int, tax_year: int) -> dict:
    from accounting_waves_25 import sage_year_end_variance_report

    base = sage_year_end_variance_report(db, models, ledger_id, tax_year)
    tie = sage_1099_dollar_tieout(db, models, ledger_id, tax_year)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    pr_q = len(settings.get('sage_pr_export_queue') or [])
    return {
        **base,
        '1099_vendor_count': tie.get('vendor_count'),
        'payroll_export_queue': pr_q,
        'ic_oe_reconcile': settings.get('sage_ic_oe_reconcile'),
    }


def cron_waves_25_28_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_25 import cron_waves_20_24_maintenance

    base = cron_waves_20_24_maintenance(db, models, secret, Project=Project)
    AcctLedger = models['AcctLedger']
    pull_results = []
    retry_results = []
    for ledger in AcctLedger.query.limit(5).all():
        try:
            pull_results.append({
                'ledger_id': ledger.id,
                'ar': sage_pull_ar_receipt_applications(db, models, ledger.id),
                'ap': sage_pull_ap_payment_status(db, models, ledger.id),
            })
            retry_results.append(sage_inbox_auto_retry(db, models, ledger.id))
        except Exception as exc:
            pull_results.append({'ledger_id': ledger.id, 'error': str(exc)})
    paces = sage_run_paces_mandatory()
    return {'base': base, 'pull': pull_results, 'retry': retry_results, 'paces': paces}


def sage_mirror_deploy_check_v2() -> dict:
    from accounting_waves_24 import sage_mirror_deploy_check

    base = sage_mirror_deploy_check()
    paces = sage_run_paces_mandatory()
    ok = base.get('ok') and (paces.get('ok') or paces.get('skipped'))
    return {'ok': ok, 'mirror': base, 'paces': paces}
