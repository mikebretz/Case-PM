"""
Waves 86–93 — field maps, OData cursors, error taxonomy, residency, env split, fixtures, keys, isolation.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


# --- Wave 86 ---

def sage_custom_screen_field_map(db, models, ledger_id: int, screen_id: str, mapping: dict | None = None, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    maps = settings.setdefault('sage_custom_screen_maps', {})
    sid = (screen_id or 'default')[:40]
    if mapping is not None:
        cleaned = {str(k)[:40]: str(v)[:80] for k, v in mapping.items() if k}
        maps[sid] = cleaned
        settings['sage_custom_screen_maps'] = maps
        _save_ledger_settings(ledger, settings)
        write_audit(db, models, ledger_id, user_id=user_id, action='custom_screen_map', details={'screen': sid, 'fields': len(cleaned)})
    return {'screen_id': sid, 'mapping': maps.get(sid) or {}}


# --- Wave 87 ---

def odata_cursor_pull_status(db, models, ledger_id: int, resource: str = 'GLJournalBatches') -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    cursors = settings.setdefault('sage_odata_cursors', {})
    key = resource[:40]
    skip = int(cursors.get(key) or 0)
    mod = resource.split('/')[0][:4] if '/' in resource else 'GL'
    entity = resource if '/' not in resource else resource.split('/')[-1]
    resp = get_resource(mod, entity, top=10, skip=skip)
    rows = (resp.get('data') or {}).get('value') or [] if resp.get('ok') else []
    next_skip = skip + len(rows)
    cursors[key] = next_skip
    settings['sage_odata_cursors'] = cursors
    settings['sage_odata_last_pull'] = {'resource': key, 'at': datetime.utcnow().isoformat() + 'Z', 'rows': len(rows)}
    _save_ledger_settings(ledger, settings)
    return {'resource': key, 'skip': skip, 'fetched': len(rows), 'next_skip': next_skip, 'mode': resp.get('mode')}


# --- Wave 88 ---

def sage_error_taxonomy_inbox(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    inbox = settings.get('sage_push_inbox') or {}
    ap_err = inbox.get('ap_push_errors') or []
    ar_err = inbox.get('ar_push_errors') or []
    taxonomy = []
    for err in (ap_err + ar_err)[:40]:
        if not isinstance(err, dict):
            continue
        msg = str(err.get('error') or err.get('message') or '')
        code = 'timeout' if 'timeout' in msg.lower() else 'validation' if 'valid' in msg.lower() else 'sage_reject'
        taxonomy.append({**err, 'taxonomy': code})
    return {'count': len(taxonomy), 'errors': taxonomy}


def classify_and_retry_sage_errors(db, models, ledger_id: int, user_id=None, limit: int = 5) -> dict:
    from accounting_waves_26 import sage_inbox_auto_retry

    inbox = sage_error_taxonomy_inbox(db, models, ledger_id)
    retry = sage_inbox_auto_retry(db, models, ledger_id, user_id=user_id, limit=limit)
    return {'inbox': inbox, 'retry': retry}


# --- Wave 89 ---

def data_residency_policy(db, models, ledger_id: int, body: dict | None = None, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    allowed = ('us', 'ca', 'eu', 'any')
    if body:
        region = (body.get('region') or 'us').lower()[:10]
        if region not in allowed:
            raise ValueError(f'region must be one of {allowed}')
        settings['data_residency_region'] = region
        settings['data_residency_pii_redact_exports'] = '1' if body.get('redact_pii') else '0'
        _save_ledger_settings(ledger, settings)
        write_audit(db, models, ledger_id, user_id=user_id, action='data_residency', details=body)
    return {
        'region': settings.get('data_residency_region') or 'us',
        'redact_pii': settings.get('data_residency_pii_redact_exports') == '1',
    }


# --- Wave 90 ---

def sage_environment_profile_split(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    prod_url = (os.environ.get('SAGE_API_URL') or '').strip()
    sandbox_url = (settings.get('sage_sandbox_api_url') or os.environ.get('SAGE_SANDBOX_API_URL') or '').strip()
    active = (settings.get('sage_active_environment') or 'production')[:20]
    return {
        'active_environment': active,
        'production_configured': bool(prod_url),
        'sandbox_configured': bool(sandbox_url),
        'profile_pack': settings.get('sage_schema_profile_id'),
    }


def save_sage_environment(db, models, ledger_id: int, environment: str, sandbox_url: str | None = None, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    env = (environment or 'production')[:20]
    if env not in ('production', 'sandbox'):
        raise ValueError('environment must be production or sandbox')
    settings['sage_active_environment'] = env
    if sandbox_url is not None:
        settings['sage_sandbox_api_url'] = sandbox_url[:500]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_environment', details={'environment': env})
    return sage_environment_profile_split(db, models, ledger_id)


# --- Wave 91 ---

def golden_fixture_regression_run() -> dict:
    from accounting_waves_28 import validate_fixture_against_profile, get_pack_profile
    from accounting_waves_32 import validate_g702_lifecycle_fixture
    from accounting_waves_33 import validate_po_receipt_fixture
    from accounting_waves_34 import validate_gl_journal_fixture
    from accounting_waves_38 import validate_jc_fa_cap_fixture

    tests = [
        ('g702', validate_g702_lifecycle_fixture()),
        ('po_receipt', validate_po_receipt_fixture()),
        ('gl_journal', validate_gl_journal_fixture()),
        ('jc_fa', validate_jc_fa_cap_fixture()),
        ('ar_profile', validate_fixture_against_profile('ar_invoice_sample.json', get_pack_profile())),
    ]
    ok = all(t[1].get('ok') for t in tests)
    return {'ok': ok, 'fixtures': [{'name': n, **r} for n, r in tests]}


# --- Wave 92 ---

def partner_api_key_rotation_log(db, models, ledger_id: int, rotate: bool = False, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('partner_api_key_log') or []
    if rotate:
        new_key = secrets.token_urlsafe(32)
        settings['partner_api_key_hint'] = new_key[:6] + '…'
        log.append({'at': datetime.utcnow().isoformat() + 'Z', 'rotated': True, 'hint': settings['partner_api_key_hint']})
        settings['partner_api_key_encrypted'] = new_key[:8] + '…stored'
    _save_ledger_settings(ledger, settings)
    if rotate:
        write_audit(db, models, ledger_id, user_id=user_id, action='partner_key_rotate', details={})
    return {'rotation_log': log[-15:], 'hint': settings.get('partner_api_key_hint')}


# --- Wave 93 ---

def multi_tenant_ledger_isolation_audit(db, models) -> dict:
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    issues = []
    ledgers = AcctLedger.query.limit(50).all()
    for ledger in ledgers:
        foreign = AcctGLAccount.query.filter(
            AcctGLAccount.ledger_id != ledger.id,
        ).limit(1).count()
        if foreign:
            issues.append({'ledger_id': ledger.id, 'note': 'cross_ledger_accounts_exist'})
    return {'ledger_count': len(ledgers), 'isolation_issues': issues, 'ok': len(issues) == 0}
