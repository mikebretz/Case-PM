"""
Waves 62–64 — Tax filing loop, payroll PR depth, prevailing wage per class.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings, sage_write_guard


def filing_bundle_with_transmit_v2(db, models, ledger_id: int, tax_year: int, user_id=None) -> dict:
    from accounting_waves_29 import filing_bundle_with_transmit_log
    from accounting_waves_19 import efile_transmit_log

    bundle = filing_bundle_with_transmit_log(db, models, ledger_id, tax_year, user_id=user_id)
    log = efile_transmit_log(db, models, ledger_id)
    return {**bundle, 'compliance_transmit': log}


def sage_pull_pr_pay_runs(db, models, ledger_id: int, user_id=None, limit: int = 30) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'pr', 'pull')
    resp = get_resource('PR', 'PRPayRuns', top=limit)
    rows = (resp.get('data') or {}).get('value') or [] if resp.get('ok') else []
    settings['sage_pr_pay_runs_cache'] = [
        {
            'number': (r.get('PayRunNumber') or r.get('RunNumber') or '')[:22],
            'gross': float(r.get('GrossPay') or r.get('Gross') or 0),
        }
        for r in rows[:limit]
    ]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pull_pr_runs', details={'count': len(rows)})
    return {'imported': len(rows), 'mode': resp.get('mode')}


def pr_employee_upsert_from_sage_cache(db, models, ledger_id: int, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    cache = settings.get('sage_pr_employee_cache') or []
    settings['sage_pr_employee_registry'] = {row.get('code'): row.get('name') for row in cache if row.get('code')}
    _save_ledger_settings(ledger, settings)
    return {'registry_size': len(settings['sage_pr_employee_registry']), 'from_cache': len(cache)}


def wh347_per_job_class_report(db, models, ledger_id: int, project_id: int, week_ending: str) -> dict:
    from accounting_waves_26 import scheduled_wh347_sage_labor_compare

    base = scheduled_wh347_sage_labor_compare(db, models, ledger_id, project_id, week_ending, Project=None)
    warnings = base.get('prevailing_compare_warnings') or []
    by_class = {}
    for w in warnings:
        if not isinstance(w, dict):
            continue
        jc = w.get('job_class') or w.get('classification') or 'UNSPECIFIED'
        by_class.setdefault(jc, []).append(w)
    return {**base, 'by_job_class': {k: len(v) for k, v in by_class.items()}, 'classes': list(by_class.keys())}


def certified_payroll_export_hook(db, models, ledger_id: int, project_id: int, week_ending: str, user_id=None) -> dict:
    report = wh347_per_job_class_report(db, models, ledger_id, project_id, week_ending)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    entry = {
        'project_id': project_id,
        'week_ending': week_ending,
        'class_count': len(report.get('classes') or []),
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    settings['sage_certified_payroll_exports'] = (settings.get('sage_certified_payroll_exports') or [])[-20:] + [entry]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='certified_payroll_export', details=entry)
    return {'export': entry, 'report': report}


def cron_waves_62_64_maintenance(db, models, secret: str) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    runs = []
    yr = date.today().year - 1
    for ledger in AcctLedger.query.limit(5).all():
        runs.append({
            'ledger_id': ledger.id,
            'filing': filing_bundle_with_transmit_v2(db, models, ledger.id, yr),
            'pr_runs': sage_pull_pr_pay_runs(db, models, ledger.id),
            'pr_upsert': pr_employee_upsert_from_sage_cache(db, models, ledger.id),
        })
    return {'ledgers': runs}


def cron_waves_50_64_combined(db, models, secret: str, Project=None, PayAppProjectState=None, Commitment=None) -> dict:
    from accounting_waves_35 import cron_waves_50_52_maintenance
    from accounting_waves_36 import cron_waves_54_60_maintenance

    w50 = cron_waves_50_52_maintenance(db, models, secret)
    w54 = cron_waves_54_60_maintenance(db, models, secret, Project=Project, PayAppProjectState=PayAppProjectState, Commitment=Commitment)
    w62 = cron_waves_62_64_maintenance(db, models, secret)
    from accounting_waves_34 import sage_mirror_deploy_check_v9

    v9 = sage_mirror_deploy_check_v9()
    v10 = sage_mirror_deploy_check_v10()
    return {'gl_50_52': w50, 'cre_dist_54_60': w54, 'payroll_tax_62_64': w62, 'deploy_v9': v9, 'deploy_v10': v10}


def sage_mirror_deploy_check_v10() -> dict:
    from accounting_waves_34 import sage_mirror_deploy_check_v9

    base = sage_mirror_deploy_check_v9()
    checks = {
        'wave_50_tieout': True,
        'wave_49_gl_pull': True,
    }
    try:
        from accounting_waves_34 import sage_pull_gl_journal_batch_status
        from accounting_waves_35 import subledger_gl_tieout_report

        assert callable(sage_pull_gl_journal_batch_status)
        assert callable(subledger_gl_tieout_report)
    except Exception:
        checks['wave_49_gl_pull'] = False
    ok = base.get('ok') and all(checks.values())
    return {'ok': ok, 'v9': base, 'wave_checks': checks}
