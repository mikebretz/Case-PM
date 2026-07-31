"""
Waves 49, 61, 65, 69 — GL journals, tax stack, FA multi-book, company matrix.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import (
    _ledger_settings,
    _save_ledger_settings,
    sage_push_posted_gl_batches,
    sage_sync_get_any,
    sage_sync_set_any,
    sage_write_guard,
)
from accounting_waves_28 import load_fixture_row
from accounting_waves_29 import sage_push_document_tax_batch


# --- Wave 49: GL journal round-trip ---

def sage_pull_gl_journal_batch_status(db, models, ledger_id: int, user_id=None, limit: int = 40) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'gl', 'pull')
    resp = get_resource('GL', 'GLJournalBatches', top=limit)
    if not resp.get('ok'):
        return {'matched': 0, 'mode': resp.get('mode')}
    AcctJournalBatch = models['AcctJournalBatch']
    matched = 0
    remote = []
    for row in (resp.get('data') or {}).get('value') or []:
        bnum = (row.get('BatchNumber') or '')[:40]
        status = (row.get('Status') or row.get('BatchStatus') or '')[:20]
        remote.append({'batch_number': bnum, 'status': status})
        if not bnum:
            continue
        for batch in AcctJournalBatch.query.filter_by(ledger_id=ledger_id).limit(200).all():
            key = sage_sync_get_any(settings, batch, 'external_key') or ''
            if key and key == bnum:
                settings = sage_sync_set_any(settings, batch, state='acknowledged' if status.lower() == 'posted' else 'pushed')
                matched += 1
                break
    db.session.flush()
    settings['sage_gl_batch_remote'] = remote[-30:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_gl_batches', details={'matched': matched})
    return {'matched': matched, 'remote_count': len(remote), 'mode': resp.get('mode')}


def sage_gl_journal_batch_ack_summary(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctJournalBatch = models['AcctJournalBatch']
    pending = pushed = ack = 0
    for batch in AcctJournalBatch.query.filter_by(ledger_id=ledger_id, status='Posted').limit(300).all():
        st = sage_sync_get_any(settings, batch, 'sync_state') or 'pending'
        if st in ('pushed',):
            pushed += 1
        elif st in ('acknowledged',):
            ack += 1
        else:
            pending += 1
    return {
        'pending_push': pending,
        'pushed': pushed,
        'acknowledged': ack,
        'remote_snapshot': (settings.get('sage_gl_batch_remote') or [])[-10:],
    }


def sage_export_recurring_and_allocation(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_gl_extended import run_due_recurring_schedules

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    recurring = run_due_recurring_schedules(db, models, ledger_id, user_id=user_id)
    push = sage_push_posted_gl_batches(db, models, ledger_id, user_id=user_id, limit=10)
    alloc_q = settings.get('sage_allocation_export_queue') or []
    settings['sage_allocation_export_queue'] = alloc_q[-20:]
    settings['sage_gl_recurring_last'] = {'at': datetime.utcnow().isoformat() + 'Z', 'runs': len(recurring.get('runs') or [])}
    _save_ledger_settings(ledger, settings)
    return {'recurring': recurring, 'gl_push': push}


# --- Wave 61: Tax push & stacked components ---

def stacked_tax_on_amount(db, models, ledger_id: int, amount: float, tax_group_code: str) -> dict:
    from accounting_parity_wave2 import calculate_line_taxes

    AcctTaxGroup = models['AcctTaxGroup']
    tg = AcctTaxGroup.query.filter_by(ledger_id=ledger_id, code=tax_group_code[:20]).first()
    if not tg:
        return {'error': 'tax group not found'}
    return calculate_line_taxes(amount, tg)


def sage_push_stacked_tax_batch(db, models, ledger_id: int, user_id=None) -> dict:
    ap = sage_push_document_tax_batch(db, models, ledger_id, 'ap', user_id=user_id, limit=15)
    ar = sage_push_document_tax_batch(db, models, ledger_id, 'ar', user_id=user_id, limit=15)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_tax_stack_last'] = {'at': datetime.utcnow().isoformat() + 'Z', 'ap': ap.get('pushed'), 'ar': ar.get('pushed')}
    _save_ledger_settings(ledger, settings)
    return {'ap': ap, 'ar': ar}


def apply_stacked_tax_to_ic_oe_meta(db, models, ledger_id: int, entity_type: str, entity_id: int, tax_group_code: str, amount: float, user_id=None) -> dict:
    calc = stacked_tax_on_amount(db, models, ledger_id, amount, tax_group_code)
    if calc.get('error'):
        raise ValueError(calc['error'])
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.setdefault('sage_ic_oe_tax', {})
    reg[f'{entity_type}:{entity_id}'] = {'tax_group': tax_group_code, 'calc': calc}
    settings['sage_ic_oe_tax'] = reg
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='stacked_tax_ic_oe', details={'entity': entity_type, 'id': entity_id})
    return calc


# --- Wave 65: FA multi-book ---

def fa_multi_book_depreciation_run(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_parity_wave2 import run_depreciation_book

    books = ('GAAP', 'TAX')
    results = []
    for book in books:
        try:
            results.append({'book': book, 'result': run_depreciation_book(db, models, ledger_id, book, user_id=user_id)})
        except Exception as exc:
            results.append({'book': book, 'error': str(exc)[:120]})
    from accounting_waves_25 import sage_queue_fa_depreciation

    queue = sage_queue_fa_depreciation(db, models, ledger_id, user_id=user_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_fa_multi_book_last'] = {'at': datetime.utcnow().isoformat() + 'Z', 'books': results}
    _save_ledger_settings(ledger, settings)
    return {'books': results, 'sage_queue': queue}


def fa_ddb_syd_schedule_preview(db, models, ledger_id: int, asset_id: int) -> dict:
    AcctFixedAsset = models.get('AcctFixedAsset')
    if not AcctFixedAsset:
        return {'lines': []}
    asset = AcctFixedAsset.query.filter_by(id=int(asset_id), ledger_id=ledger_id).first()
    if not asset:
        raise ValueError('Asset not found')
    cost = float(asset.acquisition_cost or 0)
    salvage = float(getattr(asset, 'salvage_value', 0) or 0)
    life = int(getattr(asset, 'useful_life_months', 60) or 60)
    method = (getattr(asset, 'depreciation_method', None) or 'straight_line')[:20]
    base = max(0, cost - salvage)
    lines = []
    if method.lower() in ('ddb', 'double_declining'):
        rate = 2.0 / max(1, life / 12)
        nbv = cost
        for yr in range(1, min(6, int(life / 12) + 1)):
            dep = round(nbv * rate, 2)
            nbv = max(salvage, nbv - dep)
            lines.append({'year': yr, 'method': 'DDB', 'depreciation': dep, 'nbv': round(nbv, 2)})
    elif method.lower() == 'syd':
        n = max(1, int(life / 12))
        syd = n * (n + 1) / 2
        for yr in range(1, min(6, n + 1)):
            dep = round(base * (n - yr + 1) / syd, 2)
            lines.append({'year': yr, 'method': 'SYD', 'depreciation': dep})
    else:
        dep = round(base / max(1, life), 2)
        for m in range(1, min(13, life + 1)):
            lines.append({'month': m, 'method': 'SL', 'depreciation': dep})
    return {'asset_id': asset.id, 'method': method, 'schedule': lines[:24]}


def fa_disposal_sage_mirror(db, models, ledger_id: int, asset_id: int, proceeds: float, user_id=None) -> dict:
    AcctFixedAsset = models.get('AcctFixedAsset')
    if not AcctFixedAsset:
        return {'skipped': True}
    asset = AcctFixedAsset.query.filter_by(id=int(asset_id), ledger_id=ledger_id).first()
    if not asset:
        raise ValueError('Asset not found')
    asset.status = 'Disposed'
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('sage_fa_disposal_queue') or []
    q.append({
        'asset_id': asset.id,
        'asset_number': getattr(asset, 'asset_number', ''),
        'proceeds': float(proceeds or 0),
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    settings['sage_fa_disposal_queue'] = q[-30:]
    _save_ledger_settings(ledger, settings)
    db.session.flush()
    write_audit(db, models, ledger_id, user_id=user_id, action='fa_disposal_mirror', details={'asset_id': asset.id})
    return {'disposed': True, 'queued': True}


# --- Wave 69: Company matrix ---

def company_matrix_dashboard(db, models) -> dict:
    from accounting_waves_28 import resolve_ledger_for_company
    from accounting_waves_29 import consolidated_multi_company_health

    AcctLedger = models['AcctLedger']
    matrix = []
    for ledger in AcctLedger.query.limit(20).all():
        settings = _ledger_settings(ledger)
        companies = settings.get('sage_companies') or []
        coa_map = settings.get('sage_company_coa_map') or {}
        for co in companies:
            code = co.get('code') if isinstance(co, dict) else str(co)
            if not code:
                continue
            matrix.append({
                'company_code': code,
                'ledger_id': ledger.id,
                'ledger_name': getattr(ledger, 'name', f'Ledger {ledger.id}'),
                'coa_map_entries': len(coa_map.get(code.upper(), {}) or {}),
            })
    health = consolidated_multi_company_health(db, models)
    return {'companies': matrix, 'health': health}


def save_company_coa_map(db, models, ledger_id: int, company_code: str, mapping: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    co_maps = settings.setdefault('sage_company_coa_map', {})
    cleaned = {str(k)[:40]: str(v)[:40] for k, v in (mapping or {}).items() if k}
    co_maps[(company_code or '').upper()[:20]] = cleaned
    settings['sage_company_coa_map'] = co_maps
    companies = settings.get('sage_companies') or []
    if company_code and not any(
        (c.get('code') if isinstance(c, dict) else str(c)).upper() == company_code.upper() for c in companies
    ):
        companies.append({'code': company_code.upper()[:20], 'name': company_code[:60]})
        settings['sage_companies'] = companies
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='company_coa_map', details={'company': company_code, 'entries': len(cleaned)})
    return {'company_code': company_code, 'entries': cleaned}


def company_ledger_routing_table(db, models) -> dict:
    from accounting_waves_30 import intercompany_routing_map

    AcctLedger = models['AcctLedger']
    rows = []
    for ledger in AcctLedger.query.limit(20).all():
        ic = intercompany_routing_map(db, models, ledger.id)
        settings = _ledger_settings(ledger)
        rows.append({
            'ledger_id': ledger.id,
            'sage_companies': settings.get('sage_companies') or [],
            'intercompany_routes': ic.get('routes') or [],
            'coa_maps': list((settings.get('sage_company_coa_map') or {}).keys()),
        })
    return {'ledgers': rows}


def validate_gl_journal_fixture() -> dict:
    data = load_fixture_row('gl_journal_batch_sample.json')
    rows = data.get('value') or []
    if not rows:
        return {'ok': False}
    row = rows[0]
    ok = bool(row.get('BatchNumber') and row.get('Status'))
    return {'ok': ok, 'batch': row.get('BatchNumber')}


def sage_mirror_deploy_check_v9() -> dict:
    from accounting_waves_33 import sage_mirror_deploy_check_v8

    base = sage_mirror_deploy_check_v8()
    gl = validate_gl_journal_fixture()
    ok = base.get('ok') and gl.get('ok')
    return {'ok': ok, 'v8': base, 'gl_fixture': gl}


def cron_waves_49_61_65_69_maintenance(db, models, secret: str, Project=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_33 import cron_waves_53_60_maintenance

    prior = cron_waves_53_60_maintenance(db, models, secret, Project=Project)
    AcctLedger = models['AcctLedger']
    gl_runs = tax_runs = fa_runs = []
    for ledger in AcctLedger.query.limit(5).all():
        gl_runs.append({
            'pull': sage_pull_gl_journal_batch_status(db, models, ledger.id),
            'export': sage_export_recurring_and_allocation(db, models, ledger.id),
        })
        tax_runs.append(sage_push_stacked_tax_batch(db, models, ledger.id))
        fa_runs.append(fa_multi_book_depreciation_run(db, models, ledger.id))
    matrix = company_matrix_dashboard(db, models)
    return {
        'prior': prior,
        'gl': gl_runs,
        'tax': tax_runs,
        'fa': fa_runs,
        'company_matrix': matrix,
        'deploy_v9': sage_mirror_deploy_check_v9(),
    }
