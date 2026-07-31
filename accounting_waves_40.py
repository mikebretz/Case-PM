"""
Waves 78–85 — ISV manifest, certification, scale, cache, DR, SOC2, licensing, webhooks.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import SAGE_MIRROR_CAPABILITIES, _ledger_settings, _save_ledger_settings


# --- Wave 78 ---

def sage_isv_capability_manifest() -> dict:
    from accounting_wave_registry import waves_70_96_implementation_status

    w70 = waves_70_96_implementation_status()
    return {
        'isv': 'CasePM',
        'sage_mirror_capabilities': SAGE_MIRROR_CAPABILITIES,
        'roadmap_waves_70_96': w70,
        'api_version': '2026.07',
    }


# --- Wave 79 ---

def certification_regression_harness() -> dict:
    from accounting_waves_33 import sage_mirror_deploy_check_v8
    from accounting_waves_38 import sage_mirror_deploy_check_v11

    checks = [
        ('deploy_v8', sage_mirror_deploy_check_v8()),
        ('deploy_v11', sage_mirror_deploy_check_v11()),
    ]
    try:
        from accounting_waves_42 import sage_mirror_deploy_check_v12
        checks.append(('deploy_v12', sage_mirror_deploy_check_v12()))
    except Exception as exc:
        checks.append(('deploy_v12', {'ok': False, 'error': str(exc)[:80]}))
    ok = all(c[1].get('ok') for c in checks)
    return {'ok': ok, 'checks': [{'name': n, **r} for n, r in checks]}


# --- Wave 80 ---

def mirror_batch_scale_profile(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    profile = {
        'ap_push_limit': int(settings.get('sage_ap_push_limit') or os.environ.get('SAGE_AP_PUSH_LIMIT') or 25),
        'ar_push_limit': int(settings.get('sage_ar_push_limit') or 25),
        'gl_push_limit': int(settings.get('sage_gl_push_limit') or 15),
        'cre_flush_limit': int(settings.get('sage_cre_flush_limit') or 20),
    }
    settings['mirror_batch_scale_profile'] = profile
    _save_ledger_settings(ledger, settings)
    return profile


def save_mirror_batch_scale_profile(db, models, ledger_id: int, body: dict, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    for key in ('ap_push_limit', 'ar_push_limit', 'gl_push_limit', 'cre_flush_limit'):
        if key in body:
            settings[key] = max(1, min(200, int(body[key])))
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='mirror_scale_profile', details=body)
    return mirror_batch_scale_profile(db, models, ledger_id)


# --- Wave 81 ---

def sage_cache_policy_dashboard(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    policy = {
        'vendor_cache_ttl_sec': int(settings.get('sage_vendor_cache_ttl') or 3600),
        'pr_employee_cache_rows': len(settings.get('sage_pr_employee_cache') or []),
        'fa_export_queue': len(settings.get('sage_fa_export_queue') or []),
        'last_gl_pull': settings.get('sage_gl_batch_pull_last'),
    }
    settings['sage_cache_policy'] = policy
    _save_ledger_settings(ledger, settings)
    return policy


# --- Wave 82 ---

def disaster_recovery_export_bundle(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    AcctGLAccount = models['AcctGLAccount']
    coa_count = AcctGLAccount.query.filter_by(ledger_id=ledger_id).count()
    bundle = {
        'ledger_id': ledger_id,
        'ledger_name': getattr(ledger, 'name', ''),
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'coa_accounts': coa_count,
        'settings_keys': sorted(k for k in settings.keys() if not k.startswith('_'))[:80],
        'sage_hybrid': {
            'system_of_record': settings.get('system_of_record'),
            'read_only': settings.get('sage_read_only_mode'),
        },
    }
    settings['last_dr_export'] = bundle
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='dr_export_bundle', details={'coa': coa_count})
    return bundle


# --- Wave 83 ---

def soc2_audit_export_bundle(db, models, ledger_id: int, user_id=None) -> dict:
    AcctAuditLog = models['AcctAuditLog']
    rows = AcctAuditLog.query.filter_by(ledger_id=ledger_id).order_by(AcctAuditLog.id.desc()).limit(100).all()
    items = [
        {'action': r.action, 'at': getattr(r, 'created_at', None), 'details': (r.details_json or '')[:200]}
        for r in rows
    ]
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    export = {
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'audit_entries': len(items),
        'sage_read_only': settings.get('sage_read_only_mode'),
        'cron_secret_configured': bool((os.environ.get('CASEPM_CRON_SECRET') or '').strip()),
        'items_sample': items[:15],
    }
    settings['last_soc2_export'] = {'at': export['exported_at'], 'count': export['audit_entries']}
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='soc2_audit_export', details={'entries': export['audit_entries']})
    return export


# --- Wave 84 ---

def licensed_module_gate_report(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    licensed = settings.get('sage_licensed_modules') or ['GL', 'AP', 'AR', 'BK']
    gates = {}
    for mod in ('GL', 'AP', 'AR', 'BK', 'PR', 'FA', 'PO', 'IC', 'OE', 'JC'):
        gates[mod] = mod in licensed or mod in ('GL', 'AP', 'AR')
    AcctFixedAsset = models.get('AcctFixedAsset')
    gates['FA_ENABLED'] = bool(AcctFixedAsset)
    return {'licensed': licensed, 'gates': gates, 'capabilities': SAGE_MIRROR_CAPABILITIES}


# --- Wave 85 ---

def outbound_webhook_dispatch(db, models, ledger_id: int, event_type: str, payload: dict, user_id=None) -> dict:
    import urllib.request

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    url = (settings.get('accounting_webhook_url') or os.environ.get('CASEPM_ACCOUNTING_WEBHOOK_URL') or '').strip()
    body = json.dumps({
        'event': event_type[:60],
        'ledger_id': ledger_id,
        'payload': payload,
        'at': datetime.utcnow().isoformat() + 'Z',
    }).encode('utf-8')
    result = {'dispatched': False, 'url_configured': bool(url)}
    if url:
        try:
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=8) as resp:
                result['status'] = resp.status
                result['dispatched'] = 200 <= resp.status < 300
        except Exception as exc:
            result['error'] = str(exc)[:120]
    log = settings.get('accounting_webhook_log') or []
    log.append({**result, 'event': event_type[:60]})
    settings['accounting_webhook_log'] = log[-50:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='webhook_dispatch', details=result)
    return result


def save_outbound_webhook_url(db, models, ledger_id: int, url: str, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['accounting_webhook_url'] = (url or '')[:500]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='webhook_url', details={'configured': bool(url)})
    return {'accounting_webhook_url': bool(settings['accounting_webhook_url'])}
