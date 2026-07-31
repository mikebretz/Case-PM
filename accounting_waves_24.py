"""
Waves 14–19 — Sage 300 mirror: sync foundation, financial round-trip, BK/tax,
CRE reconcile, distribution export queue, platform policy.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

SYNC_STATES = ('pending', 'queued', 'pushed', 'acknowledged', 'error', 'stale')

# Implemented mirror capabilities (extends sage300_catalog for ops UI)
SAGE_MIRROR_CAPABILITIES = {
    'gl': {'pull': True, 'push': True, 'notes': 'GL accounts pull; open JE batch export'},
    'ap': {'pull': True, 'push': True, 'notes': 'Vendors, open AP, payment batches'},
    'ar': {'pull': True, 'push': True, 'notes': 'Customers, open AR, receipt batches (queued)'},
    'bk': {'pull': True, 'push': True, 'notes': 'Bank accounts pull; period close metadata'},
    'tx': {'pull': True, 'push': False, 'notes': 'Tax authority/group pull'},
    'pj': {'pull': True, 'push': False, 'notes': 'CRE job ledger via bridge'},
    'po': {'pull': False, 'push': True, 'notes': 'Open PO export queue'},
    'ic': {'pull': False, 'push': True, 'notes': 'IC adjustment export queue'},
    'oe': {'pull': False, 'push': True, 'notes': 'OE shipment export queue'},
    'fa': {'pull': False, 'push': True, 'notes': 'FA depreciation export queue'},
    'pr': {'pull': False, 'push': True, 'notes': 'Payroll SoR policy; PR push optional'},
}


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


def _append_sage_log(settings: dict, entry: dict) -> None:
    log = settings.get('sage_sync_log') or []
    log.append({**entry, 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['sage_sync_log'] = log[-100:]


def _entity_meta(obj) -> dict:
    raw = getattr(obj, 'details_json', None) or '{}'
    try:
        meta = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        meta = {}
    return meta.setdefault('sage', {})


def sage_sync_get(obj, key: str, default=None):
    return _entity_meta(obj).get(key, default)


def sage_sync_set(obj, *, state: str | None = None, external_key: str | None = None, error: str | None = None) -> None:
    meta = {}
    if getattr(obj, 'details_json', None):
        try:
            meta = json.loads(obj.details_json)
        except (TypeError, json.JSONDecodeError):
            meta = {}
    sage = meta.setdefault('sage', {})
    if state is not None:
        sage['sync_state'] = state[:20]
        sage['sync_at'] = datetime.utcnow().isoformat() + 'Z'
    if external_key is not None:
        sage['external_key'] = str(external_key)[:80]
    if error is not None:
        sage['last_error'] = str(error)[:300]
    meta['sage'] = sage
    obj.details_json = json.dumps(meta)


def _entity_sync_key(obj) -> str:
    return f'{obj.__class__.__name__}:{obj.id}'


def sage_sync_get_any(settings: dict, obj, key: str, default=None):
    if getattr(obj, 'details_json', None) is not None:
        return sage_sync_get(obj, key, default)
    reg = (settings.get('sage_entity_sync') or {}).get(_entity_sync_key(obj)) or {}
    return reg.get(key, default)


def sage_sync_set_any(settings: dict, obj, *, state: str | None = None, external_key: str | None = None, error: str | None = None) -> dict:
    if getattr(obj, 'details_json', None) is not None:
        sage_sync_set(obj, state=state, external_key=external_key, error=error)
        return settings
    reg = settings.setdefault('sage_entity_sync', {})
    entry = dict(reg.get(_entity_sync_key(obj)) or {})
    if state is not None:
        entry['sync_state'] = state[:20]
        entry['sync_at'] = datetime.utcnow().isoformat() + 'Z'
    if external_key is not None:
        entry['external_key'] = str(external_key)[:80]
    if error is not None:
        entry['last_error'] = str(error)[:300]
    reg[_entity_sync_key(obj)] = entry
    settings['sage_entity_sync'] = reg
    return settings


def sage_write_guard(settings: dict, module: str, direction: str) -> None:
    """Wave 14 — enforce system-of-record and per-module direction policy."""
    sor = (settings.get('system_of_record') or 'casepm').lower()
    policies = settings.get('sage_module_policies') or {}
    pol = policies.get(module) or {}
    if direction == 'push':
        if sor == 'sage' and not pol.get('allow_casepm_push', False):
            raise PermissionError(f'System of record is Sage — push blocked for {module}')
        if pol.get('push') is False:
            raise PermissionError(f'Push disabled for {module}')
    if direction == 'pull':
        if sor == 'casepm' and pol.get('allow_sage_pull') is False:
            raise PermissionError(f'Pull from Sage disabled for {module} (Case PM is system of record)')
        if pol.get('pull') is False:
            raise PermissionError(f'Pull disabled for {module}')


def save_sage_mirror_policy(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if body.get('system_of_record'):
        settings['system_of_record'] = str(body['system_of_record'])[:20]
    if body.get('conflict_policy'):
        settings['sage_conflict_policy'] = str(body['conflict_policy'])[:40]
    if isinstance(body.get('sage_module_policies'), dict):
        settings['sage_module_policies'] = body['sage_module_policies']
    if isinstance(body.get('sage_companies'), list):
        settings['sage_companies'] = body['sage_companies'][:20]
    if body.get('sage_fiscal_locked_through'):
        settings['sage_fiscal_locked_through'] = str(body['sage_fiscal_locked_through'])[:10]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_mirror_policy', details=body)
    return sage_mirror_dashboard(db, models, ledger_id)


def assert_fiscal_period_open(settings: dict, txn_date: date | str | None) -> None:
    locked = (settings.get('sage_fiscal_locked_through') or '')[:10]
    if not locked:
        return
    d = txn_date if isinstance(txn_date, date) else date.fromisoformat(str(txn_date)[:10])
    if d <= date.fromisoformat(locked):
        raise PermissionError(f'Fiscal period locked through {locked}')


def sage_module_coverage_report() -> dict:
    from sage300_catalog import SAGE300_MODULES

    rows = []
    for mod in SAGE300_MODULES:
        mid = mod.get('id') or ''
        cap = SAGE_MIRROR_CAPABILITIES.get(mid, {})
        rows.append({
            'module_id': mid,
            'code': mod.get('code'),
            'name': mod.get('name'),
            'catalog_integration': mod.get('integration'),
            'mirror_pull': bool(cap.get('pull')),
            'mirror_push': bool(cap.get('push')),
            'notes': cap.get('notes') or '',
        })
    return {'modules': rows, 'capability_map': SAGE_MIRROR_CAPABILITIES}


def sage_pending_sync_summary(db, models, ledger_id: int) -> dict:
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    AcctVendor = models['AcctVendor']
    pending_ap = pending_ar = 0
    for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').limit(200).all():
        st = sage_sync_get(d, 'sync_state')
        if st not in ('pushed', 'acknowledged'):
            pending_ap += 1
    for d in AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').limit(200).all():
        st = sage_sync_get(d, 'sync_state')
        if st not in ('pushed', 'acknowledged'):
            pending_ar += 1
    vendors_unmapped = AcctVendor.query.filter_by(ledger_id=ledger_id).count()
    customers_unmapped = AcctCustomer.query.filter_by(ledger_id=ledger_id).count()
    return {
        'open_ap_pending_push': pending_ap,
        'open_ar_pending_push': pending_ar,
        'vendor_count': vendors_unmapped,
        'customer_count': customers_unmapped,
    }


def sage_mirror_dashboard(db, models, ledger_id: int) -> dict:
    from accounting_waves_17 import sage_hybrid_dashboard
    from accounting_waves_21 import sage_hybrid_exception_inbox

    base = sage_hybrid_dashboard(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    return {
        **base,
        'inbox': sage_hybrid_exception_inbox(db, models, ledger_id),
        'module_policies': settings.get('sage_module_policies') or {},
        'sage_companies': settings.get('sage_companies') or [],
        'fiscal_locked_through': settings.get('sage_fiscal_locked_through'),
        'pending': sage_pending_sync_summary(db, models, ledger_id),
        'coverage': sage_module_coverage_report(),
    }


# --- Wave 15: AR/AP/GL customers ---

def sage_pull_customers(db, models, ledger_id: int, user_id=None, limit: int = 100) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'pull')
    resp = get_resource('AR', 'ARCustomers', top=limit)
    if not resp.get('ok'):
        return {'created': 0, 'updated': 0, 'mode': resp.get('mode'), 'message': resp.get('error')}
    AcctCustomer = models['AcctCustomer']
    rows = (resp.get('data') or {}).get('value') or []
    created = updated = 0
    for row in rows:
        code = (row.get('CustomerNumber') or row.get('CustomerCode') or '').strip().upper()
        if not code:
            continue
        name = (row.get('CustomerName') or row.get('Name') or code)[:200]
        c = AcctCustomer.query.filter_by(ledger_id=ledger_id, code=code).first()
        if not c:
            c = AcctCustomer(ledger_id=ledger_id, code=code, name=name)
            db.session.add(c)
            created += 1
        else:
            updated += 1
        c.name = name
        sage_sync_set(c, state='acknowledged', external_key=code)
    db.session.flush()
    _append_sage_log(settings, {'direction': 'pull', 'entity': 'customers', 'count': created + updated})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_customers', details={'created': created, 'updated': updated})
    return {'created': created, 'updated': updated, 'mode': resp.get('mode')}


def sage_push_customers(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'push')
    AcctCustomer = models['AcctCustomer']
    pushed = errors = 0
    results = []
    for c in AcctCustomer.query.filter_by(ledger_id=ledger_id, status='Active').order_by(AcctCustomer.id).limit(limit).all():
        if sage_sync_get(c, 'sync_state') in ('pushed', 'acknowledged'):
            continue
        payload = {'CustomerNumber': c.code, 'CustomerName': c.name[:60]}
        resp = post_resource('AR', 'ARCustomers', payload)
        results.append({'code': c.code, **resp})
        if resp.get('ok'):
            sage_sync_set(c, state='pushed', external_key=c.code)
            pushed += 1
        else:
            sage_sync_set(c, state='error', error=resp.get('error') or resp.get('mode'))
            errors += 1
    db.session.flush()
    _append_sage_log(settings, {'direction': 'push', 'entity': 'customers', 'count': pushed, 'errors': errors})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_customers', details={'pushed': pushed, 'errors': errors})
    return {'pushed': pushed, 'error_count': errors, 'results': results[:30]}


def sage_push_open_ar_live(db, models, ledger_id: int, user_id=None, limit: int = 25) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ar', 'push')
    AcctARDocument = models['AcctARDocument']
    AcctCustomer = models['AcctCustomer']
    docs = AcctARDocument.query.filter_by(ledger_id=ledger_id, status='Open').order_by(AcctARDocument.id).limit(limit).all()
    results = []
    errors = []
    for d in docs:
        assert_fiscal_period_open(settings, d.document_date or date.today())
        cust = AcctCustomer.query.get(d.customer_id) if d.customer_id else None
        payload = {
            'CustomerNumber': cust.code if cust else '',
            'InvoiceNumber': (d.document_number or '')[:22],
            'InvoiceDate': d.document_date.isoformat() if d.document_date else date.today().isoformat(),
            'InvoiceAmount': float(d.amount or 0),
        }
        if float(d.amount or 0) > 0 and getattr(d, 'retainage_amount', None):
            payload['RetainageAmount'] = float(d.retainage_amount or 0)
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
    _append_sage_log(settings, {'direction': 'push', 'entity': 'open_ar', 'count': len(results), 'error_count': len(errors)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_open_ar_live', details={'count': len(results), 'errors': len(errors)})
    return {'pushed': len(results), 'error_count': len(errors), 'results': results, 'errors': errors}


def sage_push_ap_payment_batches(db, models, ledger_id: int, user_id=None, limit: int = 10) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'ap', 'push')
    AcctPaymentBatch = models['AcctPaymentBatch']
    AcctPaymentBatchLine = models['AcctPaymentBatchLine']
    AcctVendor = models['AcctVendor']
    batches = AcctPaymentBatch.query.filter_by(ledger_id=ledger_id, status='Posted').order_by(
        AcctPaymentBatch.id.desc(),
    ).limit(limit).all()
    results = []
    for batch in batches:
        if sage_sync_get_any(settings, batch, 'sync_state') in ('pushed', 'acknowledged'):
            continue
        lines = AcctPaymentBatchLine.query.filter_by(batch_id=batch.id).all()
        payments = []
        for ln in lines:
            vendor = AcctVendor.query.get(ln.vendor_id) if ln.vendor_id else None
            payments.append({
                'VendorNumber': vendor.code if vendor else '',
                'PaymentAmount': float(ln.amount or 0),
                'CheckNumber': (batch.check_number_start or batch.batch_number or '')[:20],
            })
        payload = {
            'BatchNumber': (batch.batch_number or f'CPM-{batch.id}')[:20],
            'PaymentDate': batch.payment_date.isoformat() if batch.payment_date else date.today().isoformat(),
            'Payments': payments,
        }
        resp = post_resource('AP', 'APPaymentBatches', payload)
        results.append({'batch_id': batch.id, **resp})
        if resp.get('ok'):
            settings = sage_sync_set_any(settings, batch, state='pushed', external_key=payload['BatchNumber'])
        else:
            settings = sage_sync_set_any(settings, batch, state='error', error=resp.get('error') or resp.get('mode'))
    db.session.flush()
    _append_sage_log(settings, {'direction': 'push', 'entity': 'ap_payments', 'count': len(results)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_ap_payments', details={'batches': len(results)})
    return {'processed': len(results), 'results': results}


def sage_push_posted_gl_batches(db, models, ledger_id: int, user_id=None, limit: int = 15) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'gl', 'push')
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctGLAccount = models['AcctGLAccount']
    batches = AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Posted').order_by(
        AcctJournalBatch.id.desc(),
    ).limit(limit).all()
    results = []
    for batch in batches:
        if sage_sync_get_any(settings, batch, 'sync_state') in ('pushed', 'acknowledged'):
            continue
        lines = []
        for ln in AcctJournalLine.query.filter_by(batch_id=batch.id).all():
            acct = AcctGLAccount.query.get(ln.account_id)
            lines.append({
                'AccountNumber': acct.account_number if acct else '',
                'Debit': float(ln.debit or 0),
                'Credit': float(ln.credit or 0),
                'Description': (ln.description or batch.description or '')[:60],
            })
        payload = {
            'BatchNumber': f'CPM-JE-{batch.id}',
            'Description': (batch.description or '')[:60],
            'Lines': lines,
        }
        resp = post_resource('GL', 'GLJournalBatches', payload)
        results.append({'batch_id': batch.id, **resp})
        if resp.get('ok'):
            settings = sage_sync_set_any(settings, batch, state='pushed', external_key=payload['BatchNumber'])
        else:
            settings = sage_sync_set_any(settings, batch, state='error', error=resp.get('error') or resp.get('mode'))
    db.session.flush()
    _append_sage_log(settings, {'direction': 'push', 'entity': 'gl_batches', 'count': len(results)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_gl_batches', details={'count': len(results)})
    return {'processed': len(results), 'results': results}


# --- Wave 16: BK + tax ---

def sage_pull_bank_accounts(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'bk', 'pull')
    resp = get_resource('BK', 'BKAccounts', top=limit)
    if not resp.get('ok'):
        return {'created': 0, 'message': resp.get('error') or resp.get('mode')}
    AcctBankAccount = models['AcctBankAccount']
    rows = (resp.get('data') or {}).get('value') or []
    created = 0
    for row in rows:
        code = (row.get('BankCode') or row.get('AccountCode') or '').strip().upper()
        if not code:
            continue
        if AcctBankAccount.query.filter_by(ledger_id=ledger_id, code=code).first():
            continue
        name = (row.get('Description') or row.get('BankName') or code)[:120]
        db.session.add(AcctBankAccount(
            ledger_id=ledger_id,
            code=code[:20],
            name=name,
            currency='USD',
        ))
        created += 1
    db.session.flush()
    _append_sage_log(settings, {'direction': 'pull', 'entity': 'bank_accounts', 'count': created})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_banks', details={'created': created})
    return {'created': created, 'mode': resp.get('mode')}


def sage_pull_tax_groups(db, models, ledger_id: int, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'tx', 'pull')
    resp = get_resource('TX', 'TXGroups', top=limit)
    groups = []
    if resp.get('ok'):
        groups = (resp.get('data') or {}).get('value') or []
    stored = settings.get('sage_tax_groups') or []
    for row in groups:
        code = (row.get('GroupCode') or row.get('TaxGroup') or '').strip()
        if code:
            stored.append({'code': code, 'description': (row.get('Description') or '')[:120]})
    settings['sage_tax_groups'] = stored[-100:]
    _append_sage_log(settings, {'direction': 'pull', 'entity': 'tax_groups', 'count': len(groups)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_tax_groups', details={'count': len(groups)})
    return {'imported': len(groups), 'mode': resp.get('mode'), 'groups': settings['sage_tax_groups'][-20:]}


def sage_push_bank_period_to_sage(db, models, ledger_id: int, bank_account_id: int, period_end: str, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'bk', 'push')
    closed = settings.get('bank_periods_closed') or []
    match = next((c for c in closed if c.get('bank_account_id') == int(bank_account_id)), None)
    entry = {
        'bank_account_id': int(bank_account_id),
        'period_end': period_end[:10],
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'sage_note': 'Case PM bank period close metadata',
    }
    if match:
        match['sage_export'] = entry
    else:
        closed.append({**entry, 'closed_at': entry['exported_at']})
    settings['bank_periods_closed'] = closed[-50:]
    settings.setdefault('sage_bk_close_queue', []).append(entry)
    settings['sage_bk_close_queue'] = settings['sage_bk_close_queue'][-30:]
    _append_sage_log(settings, {'direction': 'push', 'entity': 'bk_period', 'bank_account_id': bank_account_id})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_push_bk_period', details=entry)
    return entry


# --- Wave 17: CRE job ledger reconcile ---

def project_sage_ledger_reconcile(db, models, ledger_id: int, project_id: int, Project=None) -> dict:
    from sage_service import pull_sage_job_ledger

    if not Project:
        raise ValueError('Project model required')
    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    job = (project.sage_job_number or project.accounting_project_number or '').strip()
    sage = pull_sage_job_ledger(job) if job else {'found': False}
    local_billed = local_ap = 0.0
    AcctARDocument = models['AcctARDocument']
    AcctAPDocument = models['AcctAPDocument']
    for d in AcctARDocument.query.filter_by(ledger_id=ledger_id, project_id=int(project_id)).all():
        local_billed += float(d.amount or 0)
    for d in AcctAPDocument.query.filter_by(ledger_id=ledger_id, project_id=int(project_id)).all():
        local_ap += float(d.amount or 0)
    sage_billed = sum(float(b.get('amount') or b.get('billed') or 0) for b in (sage.get('owner_billings') or []))
    sage_paid = sum(float(v or 0) for v in (sage.get('vendor_paid_totals') or {}).values())
    variance = {
        'billed_ar_vs_sage_owner': round(local_billed - sage_billed, 2),
        'ap_vs_sage_sub_paid': round(local_ap - sage_paid, 2),
    }
    items = []
    if abs(variance['billed_ar_vs_sage_owner']) > 1:
        items.append({'id': 'ar_billing', 'severity': 'warning', 'label': f'A/R billed {local_billed} vs Sage owner billings {sage_billed}'})
    if abs(variance['ap_vs_sage_sub_paid']) > 1:
        items.append({'id': 'ap_sub', 'severity': 'warning', 'label': f'A/P {local_ap} vs Sage sub paid {sage_paid}'})
    if not sage.get('found'):
        items.append({'id': 'sage_job', 'severity': 'info', 'label': 'Sage job ledger not available — configure sage_job_number'})
    return {
        'project_id': int(project_id),
        'sage_job_number': job,
        'sage_found': bool(sage.get('found')),
        'local_billed_ar': round(local_billed, 2),
        'local_ap': round(local_ap, 2),
        'sage_owner_billed': round(sage_billed, 2),
        'sage_sub_paid': round(sage_paid, 2),
        'variance': variance,
        'items': items,
        'aligned': not any(i['severity'] == 'warning' for i in items),
    }


# --- Wave 18: distribution export queue ---

def sage_queue_distribution_exports(db, models, ledger_id: int, user_id=None, limit: int = 25) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctPurchaseOrder = models.get('AcctPurchaseOrder')
    queued = []
    if AcctPurchaseOrder:
        for po in AcctPurchaseOrder.query.filter_by(ledger_id=ledger_id).order_by(AcctPurchaseOrder.id.desc()).limit(limit).all():
            if (po.status or '') not in ('Open', 'Partial', 'Received'):
                continue
            queued.append({'type': 'po', 'id': po.id, 'number': getattr(po, 'po_number', None) or po.id})
    dist_q = settings.get('sage_distribution_queue') or []
    dist_q.extend(queued)
    settings['sage_distribution_queue'] = dist_q[-200:]
    _append_sage_log(settings, {'direction': 'queue', 'entity': 'distribution', 'count': len(queued)})
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_queue_distribution', details={'queued': len(queued)})
    return {'queued': len(queued), 'queue_size': len(settings['sage_distribution_queue'])}


# --- Wave 19: platform snapshot ---

def sage_platform_mirror_settings(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    return {
        'system_of_record': settings.get('system_of_record') or 'casepm',
        'sage_companies': settings.get('sage_companies') or [],
        'fiscal_locked_through': settings.get('sage_fiscal_locked_through'),
        'multi_currency_enabled': settings.get('multi_currency_enabled', False),
        'module_policies': settings.get('sage_module_policies') or {},
    }


def sage_mirror_deploy_check() -> dict:
    """Lightweight import/coverage check for deploy (no live Sage required)."""
    errors = []
    try:
        assert callable(sage_module_coverage_report)
        cov = sage_module_coverage_report()
        if not cov.get('modules'):
            errors.append('coverage empty')
    except Exception as exc:
        errors.append(str(exc))
    return {'ok': not errors, 'errors': errors, 'module_count': len(sage_module_coverage_report().get('modules') or [])}


def cron_sage_mirror_maintenance(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_23 import cron_wave13_summary_email
    from accounting_waves_18 import sage_flush_sync_queues

    base = cron_wave13_summary_email(db, models, secret)
    AcctLedger = models['AcctLedger']
    flush_results = []
    for ledger in AcctLedger.query.limit(10).all():
        try:
            flush_results.append(sage_flush_sync_queues(db, models, ledger.id))
        except Exception as exc:
            flush_results.append({'error': str(exc)})
        settings = _ledger_settings(ledger)
        settings['last_sage_mirror_cron'] = datetime.utcnow().isoformat() + 'Z'
        _save_ledger_settings(ledger, settings)
    return {'wave13': base, 'sage_flush': flush_results, 'coverage_modules': len(sage_module_coverage_report().get('modules') or [])}
