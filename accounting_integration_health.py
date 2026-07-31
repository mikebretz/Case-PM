"""
Construction ↔ accounting integration health and CRE auto-post profile helpers.
"""
from __future__ import annotations

from datetime import datetime

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


def construction_integration_health_dashboard(
    db,
    models,
    ledger_id: int,
    project_id: int | None = None,
    *,
    Project=None,
    PayAppProjectState=None,
) -> dict:
    from accounting_waves_20 import jobcost_variance_breakdown
    from accounting_waves_24 import sage_mirror_dashboard, sage_pending_sync_summary
    from accounting_waves_35 import subledger_gl_tieout_report
    from program_settings_persistence import load_accounting_defaults

    tieout = subledger_gl_tieout_report(db, models, ledger_id)
    sage_dash = sage_mirror_dashboard(db, models, ledger_id)
    pending = sage_pending_sync_summary(db, models, ledger_id)
    defaults = load_accounting_defaults()

    g702_pending = []
    wip_flags = []
    if project_id is not None:
        var = jobcost_variance_breakdown(db, models, ledger_id, int(project_id), PayAppProjectState)
        g702_pending = var.get('g702_pending_sync') or []
        from accounting_waves_22 import contractual_wip_analysis

        wip = contractual_wip_analysis(
            db, models, ledger_id, int(project_id), Project=Project, PayAppProjectState=PayAppProjectState,
        )
        if wip.get('status') != 'ok':
            wip_flags.append({'project_id': project_id, 'status': wip.get('status'), 'over_under': wip.get('over_under_billing')})
    elif Project and PayAppProjectState:
        for p in Project.query.filter_by(status='Active').limit(15).all():
            var = jobcost_variance_breakdown(db, models, ledger_id, p.id, PayAppProjectState)
            pending_periods = var.get('g702_pending_sync') or []
            if pending_periods:
                g702_pending.append({'project_id': p.id, 'name': getattr(p, 'name', ''), 'pending_count': len(pending_periods)})

    inbox = (sage_dash.get('inbox') or {})
    ap_errors = inbox.get('ap_push_errors') or []
    ar_errors = inbox.get('ar_push_errors') or []
    issues = []
    if g702_pending:
        issues.append({'code': 'g702_pending', 'severity': 'warning', 'detail': g702_pending[:10]})
    if ap_errors or ar_errors:
        issues.append({'code': 'sage_push_errors', 'severity': 'error', 'ap': len(ap_errors), 'ar': len(ar_errors)})
    ap_delta = abs(float(tieout.get('open_ap_subledger') or 0))
    ar_delta = abs(float(tieout.get('open_ar_subledger') or 0))
    if ap_delta > 1 or ar_delta > 1:
        issues.append({'code': 'subledger_tieout', 'severity': 'warning', 'ap_delta': ap_delta, 'ar_delta': ar_delta})
    if wip_flags:
        issues.append({'code': 'wip_variance', 'severity': 'info', 'projects': wip_flags})

    score = 100
    score -= min(40, len(g702_pending) * 8)
    score -= min(30, (len(ap_errors) + len(ar_errors)) * 5)
    score -= min(20, int(ap_delta > 1) * 10 + int(ar_delta > 1) * 10)
    score = max(0, score)
    grade = 'A' if score >= 90 else 'B' if score >= 75 else 'C' if score >= 60 else 'D'

    return {
        'at': datetime.utcnow().isoformat() + 'Z',
        'ledger_id': ledger_id,
        'project_id': project_id,
        'grade': grade,
        'score': score,
        'issues': issues,
        'g702_pending': g702_pending,
        'sage_pending': pending,
        'sage_mirror': sage_dash,
        'tieout': tieout,
        'autopost_flags': {
            k: defaults.get(k)
            for k in (
                'auto_post_enabled', 'g702_post_on_approve', 'sub_pay_app_post_on_approve',
                'commitment_post_on_approve', 'co_post_on_approve', 'timesheet_post_on_approve',
                'direct_cost_post_on_approve',
            )
        },
    }


def apply_cre_autopost_profile(user_id=None) -> dict:
    """Enable recommended construction auto-post flags (idempotent)."""
    from program_settings_persistence import load_accounting_defaults, save_accounting_defaults

    current = load_accounting_defaults()
    profile = {
        'auto_post_enabled': '1',
        'g702_post_on_approve': '1',
        'sub_pay_app_post_on_approve': '1',
        'commitment_post_on_approve': '1',
        'co_post_on_approve': '1',
        'auto_wip_on_billing_sync': '1',
        'retainage_accounting_enabled': '1',
        'timesheet_post_on_approve': '1',
        'direct_cost_post_on_approve': '1',
    }
    merged = {**current, **profile}
    save_accounting_defaults(merged)
    return {'applied': True, 'profile': profile, 'accounting_defaults': load_accounting_defaults()}


def cre_autopost_profile_documentation() -> dict:
    return {
        'title': 'CRE auto-post profile',
        'description': (
            'When applied, approved G702, sub pay apps, commitments, change orders, timesheets, '
            'and direct costs post into built-in G/L/AP/AR automatically (subject to fiscal lock and Sage read-only).'
        ),
        'flags': {
            'auto_post_enabled': '1',
            'g702_post_on_approve': '1',
            'sub_pay_app_post_on_approve': '1',
            'commitment_post_on_approve': '1',
            'co_post_on_approve': '1',
            'auto_wip_on_billing_sync': '1',
            'retainage_accounting_enabled': '1',
            'timesheet_post_on_approve': '1',
            'direct_cost_post_on_approve': '1',
        },
        'api_apply': 'POST /api/accounting/platform/apply-cre-autopost-profile',
        'doc_file': 'docs/ACCOUNTING_CRE_AUTOPOST.md',
    }
