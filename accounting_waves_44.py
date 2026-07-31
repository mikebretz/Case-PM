"""
Sage integration depth: PJ reconcile, fiscal periods, unified setup, PR push, FA ack.
"""
from __future__ import annotations

import os
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings, sage_write_guard


def sage_pj_transactions_pull_v2(db, models, ledger_id: int, project_id: int | None = None, user_id=None, limit: int = 50) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'gl', 'pull')
    filters = ''
    if project_id is not None:
        filters = f"$filter=Project eq 'P{int(project_id)}'"
    resp = get_resource('PJ', 'PJTransactions', top=limit, filters=filters)
    rows = (resp.get('data') or {}).get('value') or [] if resp.get('ok') else []
    cache = settings.setdefault('sage_pj_transactions_cache', {})
    key = str(project_id or 'all')
    cache[key] = {'rows': rows[:limit], 'at': datetime.utcnow().isoformat() + 'Z', 'mode': resp.get('mode')}
    settings['sage_pj_transactions_cache'] = cache
    settings['sage_pj_transactions_cache']['all'] = cache[key]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pj_pull', details={'count': len(rows), 'project_id': project_id})
    return {'imported': len(rows), 'project_id': project_id, **resp}


def sage_pj_portfolio_reconcile_v2(
    db, models, ledger_id: int, *, Project=None, PayAppProjectState=None, limit: int = 15,
) -> dict:
    from accounting_waves_20 import jobcost_variance_breakdown
    from accounting_waves_22 import _gl_job_cost_to_date

    pull = sage_pj_transactions_pull_v2(db, models, ledger_id, user_id=None, limit=100)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    cache_rows = (settings.get('sage_pj_transactions_cache') or {}).get('all', {}).get('rows') or []
    sage_total = sum(float(row.get('Amount') or row.get('TransactionAmount') or 0) for row in cache_rows)
    rows = []
    if Project:
        for p in Project.query.filter_by(status='Active').limit(limit).all():
            gl = _gl_job_cost_to_date(db, models, ledger_id, p.id)
            var = jobcost_variance_breakdown(db, models, ledger_id, p.id, PayAppProjectState) if PayAppProjectState else {}
            rows.append({
                'project_id': p.id,
                'name': getattr(p, 'name', ''),
                'gl_job_cost': gl,
                'billed_ar': var.get('billed_ar'),
                'variance_billed_vs_ar': var.get('variance_billed_vs_ar'),
            })
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    report = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'sage_pj_row_count': pull.get('imported'),
        'sage_amount_sample_total': round(sage_total, 2),
        'projects': rows,
    }
    settings['sage_pj_reconcile_v2'] = report
    _save_ledger_settings(ledger, settings)
    return report


def sage_fiscal_calendar_pull_enforce(db, models, ledger_id: int, user_id=None) -> dict:
    from sage300_web_client import get_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'gl', 'pull')
    resp = get_resource('GL', 'GLFiscalCalendars', top=5)
    rows = (resp.get('data') or {}).get('value') or [] if resp.get('ok') else []
    closed = []
    for row in rows:
        if str(row.get('Status') or '').lower() in ('closed', 'inactive'):
            closed.append(row.get('Period') or row.get('FiscalPeriod'))
    settings['sage_fiscal_closed_periods'] = closed[-24:]
    settings['sage_fiscal_last_pull'] = datetime.utcnow().isoformat() + 'Z'
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_fiscal_pull', details={'closed': len(closed)})
    return {'closed_periods': closed, 'mode': resp.get('mode')}


def assert_sage_period_open_for_post(db, models, ledger_id: int, post_date: date | None = None) -> None:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    if settings.get('sage_enforce_fiscal_close') != '1':
        return
    closed = settings.get('sage_fiscal_closed_periods') or []
    if not closed:
        return
    dt = post_date or date.today()
    key = dt.strftime('%Y-%m')
    if key in closed or dt.strftime('%Y%m') in [str(c) for c in closed]:
        raise PermissionError(f'Sage fiscal period {key} is closed')


def sage_unified_setup_health(db, models, ledger_id: int) -> dict:
    from accounting_integration_health import construction_integration_health_dashboard
    from sage300_web_client import resolve_web_api_config

    cfg = resolve_web_api_config()
    bridge = (os.environ.get('SAGE_API_URL') or '').strip()
    try:
        from program_settings_persistence import load_sage_defaults
        bridge = bridge or (load_sage_defaults().get('sage_api_url') or '').strip()
    except Exception:
        pass
    integ = construction_integration_health_dashboard(db, models, ledger_id)
    ready = cfg.get('configured') and cfg.get('user') and cfg.get('password')
    return {
        'web_api': cfg,
        'cre_bridge_configured': bool(bridge),
        'integration_health': integ,
        'ready_for_live_sync': bool(ready and bridge),
        'checklist': [
            {'id': 'web_url', 'ok': cfg.get('configured')},
            {'id': 'web_credentials', 'ok': bool(cfg.get('user') and cfg.get('password'))},
            {'id': 'cre_bridge', 'ok': bool(bridge)},
            {'id': 'integration_grade', 'ok': (integ.get('score') or 0) >= 70},
        ],
    }


def sage_pr_push_pay_run(db, models, ledger_id: int, run_id: int, user_id=None) -> dict:
    from sage300_web_post import post_resource

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    sage_write_guard(settings, 'pr', 'push')
    AcctPayrollRun = models['AcctPayrollRun']
    run = AcctPayrollRun.query.filter_by(id=int(run_id), ledger_id=ledger_id).first()
    if not run:
        raise ValueError('Payroll run not found')
    payload = {
        'PayRunNumber': (run.run_number or f'CPM-{run.id}')[:22],
        'GrossPay': float(run.gross_pay or 0),
        'Status': 'Posted',
        'CheckDate': (run.pay_date or date.today()).isoformat(),
    }
    resp = post_resource('PR', 'PRPayRuns', payload)
    log = settings.get('sage_pr_push_log') or []
    log.append({'run_id': run.id, 'ok': resp.get('ok'), 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['sage_pr_push_log'] = log[-30:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='sage_pr_push', details={'run_id': run.id, 'ok': resp.get('ok')})
    return {'run_id': run.id, **resp}


def sage_fa_depreciation_ack_round_trip(db, models, ledger_id: int, user_id=None) -> dict:
    from accounting_waves_27 import sage_ack_fa_depreciation_queue
    from accounting_waves_29 import sage_fa_depreciation_variance

    ack = sage_ack_fa_depreciation_queue(db, models, ledger_id, user_id=user_id)
    var = sage_fa_depreciation_variance(db, models, ledger_id)
    return {'ack': ack, 'variance': var}


def cron_pm_sage_depth_maintenance(db, models, secret: str, Project=None, PayAppProjectState=None) -> dict:
    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    runs = []
    for ledger in AcctLedger.query.limit(5).all():
        runs.append({
            'ledger_id': ledger.id,
            'pj_reconcile': sage_pj_portfolio_reconcile_v2(
                db, models, ledger.id, Project=Project, PayAppProjectState=PayAppProjectState,
            ),
            'fiscal': sage_fiscal_calendar_pull_enforce(db, models, ledger.id),
            'setup': sage_unified_setup_health(db, models, ledger.id),
        })
    return {'ledgers': runs}


def sage_mirror_deploy_check_v13() -> dict:
    from accounting_waves_42 import sage_mirror_deploy_check_v12

    base = sage_mirror_deploy_check_v12()
    checks = {'pm_budget_wizard': True, 'pj_reconcile_v2': True, 'sage_unified_setup': True}
    try:
        from accounting_waves_43 import budget_publish_accounting_wizard, ap_payment_compliance_hold
        from accounting_waves_44 import sage_pj_portfolio_reconcile_v2, sage_unified_setup_health

        assert callable(budget_publish_accounting_wizard)
        assert callable(ap_payment_compliance_hold)
        assert callable(sage_pj_portfolio_reconcile_v2)
        assert callable(sage_unified_setup_health)
    except Exception:
        checks = {k: False for k in checks}
    ok = base.get('ok') and all(checks.values())
    return {'ok': ok, 'v12': base, 'wave_checks': checks}
