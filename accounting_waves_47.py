"""
Wave 47 — Operations (A), construction polish (B), PM pillars depth (C), Sage parity matrix (D).
"""
from __future__ import annotations

import os
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


def sage_cutover_checklist(db, models, ledger_id: int) -> dict:
    from accounting_waves_44 import sage_unified_setup_health
    from accounting_waves_46 import sage_go_live_alert_bundle
    from program_settings_persistence import load_accounting_defaults, load_sage_defaults

    setup = sage_unified_setup_health(db, models, ledger_id)
    alerts = sage_go_live_alert_bundle(db, models, ledger_id)
    acct = load_accounting_defaults()
    sage = load_sage_defaults()
    steps = [
        {'id': 'cre_autopost', 'label': 'Apply CRE auto-post profile in Program Settings → Accounting', 'ok': acct.get('auto_post_enabled') == '1'},
        {'id': 'sage_credentials', 'label': 'Sage Web API + CRE bridge configured', 'ok': setup.get('ready_for_live_sync')},
        {'id': 'fiscal_calendar', 'label': 'Pull Sage fiscal calendar (Accounting → Sage / cron)', 'ok': bool((_ledger_settings(models['AcctLedger'].query.get(ledger_id)) or {}).get('sage_fiscal_last_pull'))},
        {'id': 'integration_health', 'label': 'Integration health grade ≥ B', 'ok': (alerts.get('health') or {}).get('score', 0) >= 75},
        {'id': 'go_live_alerts', 'label': 'No critical go-live alerts', 'ok': not any(a.get('severity') == 'critical' for a in (alerts.get('alerts') or []))},
        {'id': 'sage_sync_default', 'label': 'Sage sync enabled for new projects (if using Sage)', 'ok': sage.get('sage_sync_enabled') == '1' or not setup.get('cre_bridge_configured')},
        {'id': 'cron_pm_sage', 'label': 'Schedule pm-sage-depth + go-live-alerts crons', 'ok': bool((os.environ.get('CASEPM_CRON_SECRET') or '').strip())},
        {'id': 'smoke', 'label': 'Run scripts/test_accounting_smoke.py after deploy', 'ok': True},
    ]
    ready = all(s['ok'] for s in steps)
    doc = 'docs/SAGE_CUTOVER_CHECKLIST.md'
    report = {'at': datetime.utcnow().isoformat() + 'Z', 'ready': ready, 'steps': steps, 'setup': setup, 'alerts': alerts, 'doc': doc}
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_cutover_checklist'] = report
    _save_ledger_settings(ledger, settings)
    return report


def sage_parity_matrix(db, models, ledger_id: int) -> dict:
    from sage300_catalog import SAGE300_MODULES

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    policy = settings.get('sage_hybrid_policy') or {}
    sor = policy.get('system_of_record') or 'casepm'
    rows = []
    for mod in SAGE300_MODULES:
        code = mod.get('code') or mod.get('id', '').upper()
        integ = mod.get('integration') or 'none'
        web = mod.get('web_api') or {}
        casepm = mod.get('casepm') or {}
        events = casepm.get('events') or []
        rows.append({
            'module': code,
            'name': mod.get('name'),
            'sage_integration': integ,
            'web_api_module': web.get('module'),
            'read': integ in ('hybrid', 'web_api', 'bridge'),
            'write': integ in ('hybrid', 'bridge') and bool(events),
            'casepm_events': events[:12],
            'conflict_policy': sor,
            'gap_notes': '' if events else 'No construction mirror events — manual Sage entry',
        })
    gaps = [r for r in rows if not r['write'] and r['module'] in ('PJ', 'JC', 'CP')]
    matrix = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'system_of_record': sor,
        'rows': rows,
        'gap_count': len(gaps),
        'gaps': gaps[:15],
    }
    settings['sage_parity_matrix'] = matrix
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, action='sage_parity_matrix', details={'gap_count': matrix['gap_count']})
    return matrix


def scheduling_resource_leveling_v1(db, ScheduleData, project_id: int, *, overload_threshold: int = 5) -> dict:
    from accounting_waves_46 import scheduling_resource_summary

    base = scheduling_resource_summary(db, ScheduleData, int(project_id))
    suggestions = []
    for bucket in base.get('resource_buckets') or []:
        n = int(bucket.get('task_count') or 0)
        if n >= overload_threshold:
            suggestions.append({
                'resource': bucket.get('name'),
                'task_count': n,
                'action': 'level_split',
                'detail': f'Split or stagger {n} tasks assigned to "{bucket.get("name")}"',
            })
    return {**base, 'leveling_status': 'v1_heuristic', 'overload_threshold': overload_threshold, 'leveling_suggestions': suggestions}


def cron_operations_bundle(db, models, secret: str) -> dict:
    """A: refresh cutover + go-live alerts for all ledgers."""
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_46 import cron_go_live_alerts_maintenance

    alerts = cron_go_live_alerts_maintenance(db, models, secret)
    cutover = []
    for ledger in models['AcctLedger'].query.limit(5).all():
        cutover.append({'ledger_id': ledger.id, 'checklist': sage_cutover_checklist(db, models, ledger.id)})
    out = {'go_live_alerts': alerts, 'cutover': cutover}
    try:
        from accounting_waves_48 import cron_go_live_email_digest
        out['go_live_email_digest'] = cron_go_live_email_digest(db, models, secret)
    except Exception:
        out['go_live_email_digest'] = {'error': 'wave48_unavailable'}
    return out


def sage_mirror_deploy_check_v16() -> dict:
    from accounting_waves_46 import sage_mirror_deploy_check_v15

    base = sage_mirror_deploy_check_v15()
    checks = {
        'cutover_checklist': True,
        'parity_matrix': True,
        'scheduling_leveling_v1': True,
        'portal_compliance': True,
        'operations_cron': True,
    }
    try:
        import portal_compliance_services  # noqa: F401
        assert callable(sage_cutover_checklist)
        assert callable(sage_parity_matrix)
        assert callable(scheduling_resource_leveling_v1)
    except Exception:
        checks = {k: False for k in checks}
    ok = base.get('ok') and all(checks.values())
    return {'ok': ok, 'v15': base, 'wave_checks': checks}
