"""
Waves 94–96 — SLA dashboard, upgrade hooks, go-live sign-off; deploy v12; final cron.
"""
from __future__ import annotations

import os
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


# --- Wave 94 ---

def sla_health_dashboard(db, models, ledger_id: int) -> dict:
    from accounting_waves_28 import sage_sync_health_score
    from accounting_waves_40 import sage_cache_policy_dashboard

    health = sage_sync_health_score(db, models, ledger_id)
    cache = sage_cache_policy_dashboard(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sla = {
        'target_uptime_pct': float(settings.get('sla_target_uptime') or 99.5),
        'sync_health_score': health.get('score'),
        'sync_grade': health.get('grade'),
        'cache_policy': cache,
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    met = (health.get('score') or 0) >= 70
    sla['sla_met'] = met
    settings['sla_health_last'] = sla
    _save_ledger_settings(ledger, settings)
    return sla


# --- Wave 95 ---

def upgrade_migration_hooks_run(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_persistence import ensure_accounting_schema

    ensure_accounting_schema(db, models)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    hooks = settings.get('upgrade_migration_log') or []
    entry = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'schema': 'ensure_accounting_schema',
        'ok': True,
    }
    hooks.append(entry)
    settings['upgrade_migration_log'] = hooks[-20:]
    settings['accounting_schema_version'] = str(int(settings.get('accounting_schema_version') or 0) + 1)
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='upgrade_migration_hook', details=entry)
    return {'migrations': hooks, 'schema_version': settings['accounting_schema_version']}


# --- Wave 96 ---

def go_live_checklist_signoff(db, models, ledger_id: int, body: dict | None = None, user_id=None) -> dict:
    from accounting_waves_38 import jc_financial_month_close_gate
    from accounting_waves_40 import certification_regression_harness
    from accounting_waves_41 import golden_fixture_regression_run
    from accounting_wave_registry import roadmap_waves_through_96_status

    gate = jc_financial_month_close_gate(db, models, ledger_id, Project=None)
    fixtures = golden_fixture_regression_run()
    cert = certification_regression_harness()
    roadmap = roadmap_waves_through_96_status()
    steps = [
        {'id': 'month_close', 'ok': gate.get('ready')},
        {'id': 'fixtures', 'ok': fixtures.get('ok')},
        {'id': 'certification', 'ok': cert.get('ok')},
        {'id': 'roadmap_96', 'ok': roadmap.get('complete_through_96')},
    ]
    ready = all(s['ok'] for s in steps)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if body and body.get('sign_off') and ready:
        settings['go_live_signed_off'] = {
            'at': datetime.utcnow().isoformat() + 'Z',
            'by': user_id,
            'steps': steps,
        }
        _save_ledger_settings(ledger, settings)
        write_audit(db, models, ledger_id, user_id=user_id, action='go_live_signoff', details=settings['go_live_signed_off'])
    return {
        'ready': ready,
        'steps': steps,
        'signed_off': settings.get('go_live_signed_off'),
        'roadmap': roadmap,
    }


def cron_waves_70_96_maintenance(db, models, secret: str, Project=None, PayAppProjectState=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_39 import accounting_bi_kpi_snapshot, sage_optional_fields_sync
    from accounting_waves_40 import outbound_webhook_dispatch
    from accounting_waves_41 import classify_and_retry_sage_errors

    AcctLedger = models['AcctLedger']
    runs = []
    for ledger in AcctLedger.query.limit(5).all():
        lid = ledger.id
        runs.append({
            'ledger_id': lid,
            'kpi': accounting_bi_kpi_snapshot(db, models, lid),
            'optional_fields': sage_optional_fields_sync(db, models, lid),
            'errors': classify_and_retry_sage_errors(db, models, lid),
            'webhook_ping': outbound_webhook_dispatch(db, models, lid, 'cron.heartbeat', {'ledger_id': lid}),
            'go_live': go_live_checklist_signoff(db, models, lid),
        })
    return {'ledgers': runs}


def cron_sage_roadmap_final_batch(
    db, models, secret: str, Project=None, PayAppProjectState=None, Commitment=None,
) -> dict:
    from accounting_waves_38 import cron_sage_jc_financial_batch

    base = cron_sage_jc_financial_batch(
        db, models, secret, Project=Project, PayAppProjectState=PayAppProjectState, Commitment=Commitment,
    )
    w70 = cron_waves_70_96_maintenance(db, models, secret, Project=Project, PayAppProjectState=PayAppProjectState)
    v12 = sage_mirror_deploy_check_v12()
    return {'jc_financial': base, 'roadmap_70_96': w70, 'deploy_v12': v12}


def sage_mirror_deploy_check_v12() -> dict:
    from accounting_waves_38 import sage_mirror_deploy_check_v11
    from accounting_wave_registry import waves_70_96_implementation_status
    from accounting_waves_41 import golden_fixture_regression_run

    base = sage_mirror_deploy_check_v11()
    reg = waves_70_96_implementation_status()
    fixtures = golden_fixture_regression_run()
    wave_checks = {f'wave_{w["wave"]}': w['ok'] for w in reg.get('waves') or []}
    ok = base.get('ok') and reg.get('ok') and fixtures.get('ok') and all(wave_checks.values())
    return {
        'ok': ok,
        'v11': base,
        'registry': reg,
        'fixtures': fixtures,
        'wave_checks': wave_checks,
    }
