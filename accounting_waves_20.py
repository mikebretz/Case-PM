"""
Wave 10 — construction money loop, Sage hybrid depth, payroll garnishments,
compliance/cron polish, AR/reporting UX backends, DB pull hardening helpers.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime

from accounting_platform import write_audit


def _ledger_settings(ledger) -> dict:
    from accounting_gl_service import _parse_settings

    return _parse_settings(ledger)


def _save_ledger_settings(ledger, settings: dict) -> None:
    ledger.settings_json = json.dumps(settings)


def g702_post_on_approve_enabled() -> bool:
    from program_settings_persistence import load_accounting_defaults

    return str(load_accounting_defaults().get('g702_post_on_approve', '1')) != '0'


def construction_force_post_for_event(event_type: str, payload: dict | None) -> bool:
    data = payload or {}
    if data.get('force_builtin_post'):
        return True
    if event_type == 'G702Approved' and g702_post_on_approve_enabled():
        return True
    return False


def sync_all_g702_pending_to_ar(
    db, models, ledger_id: int, project_id: int, user_id=None, PayAppProjectState=None, Project=None,
) -> dict:
    from accounting_waves_19 import g702_pending_ar_sync, sync_g702_period_to_ar

    pending = g702_pending_ar_sync(db, models, ledger_id, project_id, PayAppProjectState)
    posted = []
    errors = []
    for row in pending.get('pending') or []:
        period = row.get('period') or row.get('period_number')
        try:
            out = sync_g702_period_to_ar(
                db, models, ledger_id, project_id, period,
                user_id=user_id, PayAppProjectState=PayAppProjectState, Project=Project,
            )
            if out.get('posted'):
                posted.append({'period': period, **out})
        except Exception as exc:
            errors.append({'period': period, 'error': str(exc)})
    return {'posted_count': len(posted), 'posted': posted, 'errors': errors, 'skipped': len(pending.get('posted') or [])}


def jobcost_variance_breakdown(db, models, ledger_id: int, project_id: int, PayAppProjectState=None) -> dict:
    from accounting_waves_17 import jobcost_with_pay_apps
    from accounting_waves_19 import g702_pending_ar_sync

    panel = jobcost_with_pay_apps(db, models, ledger_id, project_id)
    pending = {'pending': [], 'posted': []}
    if PayAppProjectState:
        pending = g702_pending_ar_sync(db, models, ledger_id, project_id, PayAppProjectState)
    return {
        'project_id': int(project_id),
        'billed_ar': panel.get('billed_ar'),
        'pay_app_total_billed': (panel.get('pay_applications') or {}).get('total_billed'),
        'variance_billed_vs_ar': panel.get('variance_billed_vs_ar'),
        'g702_pending_sync': pending.get('pending') or [],
        'g702_already_posted': pending.get('posted') or [],
        'interpretation': (
            'Positive variance means built-in A/R exceeds pay-app billed totals; '
            'use G702 sync for approved periods not yet posted.'
        ),
    }


def sage_push_open_ap_with_error_log(db, models, ledger_id: int, user_id=None, limit: int = 25) -> dict:
    from sage300_web_post import post_resource

    AcctAPDocument = models['AcctAPDocument']
    AcctVendor = models['AcctVendor']
    docs = AcctAPDocument.query.filter_by(ledger_id=ledger_id, status='Open').order_by(AcctAPDocument.id).limit(limit).all()
    results = []
    errors = []
    for d in docs:
        vendor = AcctVendor.query.get(d.vendor_id) if d.vendor_id else None
        payload = {
            'VendorNumber': vendor.code if vendor else '',
            'InvoiceNumber': (d.document_number or '')[:22],
            'InvoiceDate': d.document_date.isoformat() if d.document_date else date.today().isoformat(),
            'InvoiceAmount': float(d.amount or 0),
            'Description': (d.document_type or 'AP')[:60],
        }
        try:
            resp = post_resource('AP', 'APInvoices', payload)
        except Exception as exc:
            resp = {'ok': False, 'error': str(exc)}
        row = {'document_id': d.id, 'document_number': d.document_number, **resp}
        results.append(row)
        if not resp.get('ok'):
            errors.append(row)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('sage_sync_log') or []
    log.append({
        'at': datetime.utcnow().isoformat() + 'Z',
        'direction': 'push',
        'entity': 'open_ap',
        'count': len(results),
        'error_count': len(errors),
        'errors': errors[:10],
    })
    settings['sage_sync_log'] = log[-100:]
    settings['sage_last_ap_push_errors'] = errors[-25:]
    _save_ledger_settings(ledger, settings)
    write_audit(
        db, models, ledger_id, user_id=user_id,
        action='sage_push_open_ap_live',
        details={'count': len(results), 'errors': len(errors)},
    )
    return {'pushed': len(results), 'error_count': len(errors), 'results': results, 'errors': errors}


def sage_gl_account_conflict_review(db, models, ledger_id: int, limit: int = 80) -> dict:
    from sage300_web_client import get_resource

    AcctGLAccount = models['AcctGLAccount']
    local = AcctGLAccount.query.filter_by(ledger_id=ledger_id).order_by(AcctGLAccount.account_number).limit(limit).all()
    resp = get_resource('GL', 'GLAccounts', top=limit)
    sage_rows = []
    if resp.get('ok'):
        data = resp.get('data') or {}
        sage_rows = data.get('value') or []
    sage_by_num = {}
    for row in sage_rows:
        num = (row.get('AccountNumber') or row.get('AccountNo') or '').strip()
        if num:
            sage_by_num[num] = row
    conflicts = []
    for acct in local:
        num = (acct.account_number or '').strip()
        sr = sage_by_num.get(num)
        if not sr:
            conflicts.append({
                'account_number': num,
                'type': 'local_only',
                'local_name': acct.description or acct.name,
                'sage_name': None,
            })
            continue
        sage_name = (sr.get('Description') or sr.get('AccountDescription') or '').strip()
        local_name = (acct.description or acct.name or '').strip()
        if sage_name and sage_name.lower() != local_name.lower():
            conflicts.append({
                'account_number': num,
                'type': 'name_mismatch',
                'local_name': local_name,
                'sage_name': sage_name,
            })
    return {'conflicts': conflicts, 'local_count': len(local), 'sage_count': len(sage_rows)}


def program_settings_sor_summary(db, models, ledger_id: int) -> dict:
    from accounting_waves_17 import sage_hybrid_dashboard

    dash = sage_hybrid_dashboard(db, models, ledger_id)
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    return {
        **dash,
        'recent_sage_log': (settings.get('sage_sync_log') or [])[-5:],
        'last_ap_push_errors': (settings.get('sage_last_ap_push_errors') or [])[-5:],
        'g702_post_on_approve': g702_post_on_approve_enabled(),
    }


def apply_garnishment_deductions(db, models, ledger_id: int, employee_id: int, gross: float) -> float:
    """Active garnishment orders on ledger settings → employee deduction total for this period."""
    AcctPayrollEmployeeDeduction = models['AcctPayrollEmployeeDeduction']
    AcctPayrollDeduction = models['AcctPayrollDeduction']
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    orders = [
        o for o in (settings.get('garnishment_orders') or [])
        if o.get('status') == 'active' and int(o.get('employee_id') or 0) == int(employee_id)
    ]
    total = 0.0
    for o in orders:
        ded_id = o.get('deduction_id')
        if not ded_id:
            continue
        d = AcctPayrollDeduction.query.get(int(ded_id))
        if not d:
            continue
        link = AcctPayrollEmployeeDeduction.query.filter_by(employee_id=employee_id, deduction_id=d.id).first()
        if not link:
            link = AcctPayrollEmployeeDeduction(employee_id=employee_id, deduction_id=d.id)
            db.session.add(link)
            db.session.flush()
        if (d.calc_method or 'fixed') == 'percent' and o.get('percent_of_gross'):
            amt = round(gross * float(o['percent_of_gross']) / 100.0, 2)
        else:
            amt = round(float(o.get('amount') or d.amount or 0), 2)
        cap = o.get('max_per_period')
        if cap is not None:
            amt = min(amt, round(float(cap), 2))
        total += max(amt, 0)
    return round(total, 2)


def certified_payroll_prevailing_daily_log(
    db, models, ledger_id: int, project_id: int, week_ending: str, Project=None,
) -> dict:
    from accounting_waves_19 import certified_payroll_with_prevailing

    base = certified_payroll_with_prevailing(db, models, ledger_id, project_id, week_ending, Project=Project)
    daily = []
    try:
        from daily_log_persistence import list_daily_logs_for_project

        logs = list_daily_logs_for_project(int(project_id), week_ending=week_ending) or []
        for entry in logs[:14]:
            daily.append({
                'date': entry.get('log_date') or entry.get('date'),
                'workers': entry.get('manpower_count') or entry.get('workers'),
                'notes': (entry.get('notes') or '')[:120],
            })
    except Exception:
        daily = []
    base['daily_log_snippet'] = daily
    base['prevailing_wage_note'] = (
        'Compare WH-347 gross/hours to prevailing_wage_rate on the project when Davis-Bacon applies.'
    )
    return base


def compliance_cron_reminders(db, models, ledger_id: int) -> dict:
    from accounting_waves_19 import compliance_filing_calendar_enriched, compliance_send_reminders
    from program_settings_persistence import load_program_settings

    cal = compliance_filing_calendar_enriched(db, models, ledger_id)
    due = [d for d in cal.get('deadlines') or [] if d.get('status') in ('due_soon', 'past_due')]
    if not due:
        return {'sent': False, 'due_count': 0}
    prog = load_program_settings()
    email = (prog.get('email') or {}).get('admin_notification_email') or (prog.get('company') or {}).get('accounting_email') or ''
    email = (email or '').strip()
    if not email:
        return {'sent': False, 'due_count': len(due), 'reason': 'no_admin_email'}
    out = compliance_send_reminders(db, models, ledger_id, email, user_id=None)
    return {'sent': bool(out.get('smtp_sent')), 'due_count': len(due), **out}


def notify_admin_schedule_failures(db, models, ledger_id: int) -> dict:
    from program_settings_persistence import load_program_settings
    from email_notifications import send_workflow_email

    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    alerts = [a for a in (settings.get('report_schedule_alerts') or []) if 'fail' in (a.get('status') or '').lower()][-10:]
    if not alerts:
        return {'notified': False, 'alert_count': 0}
    prog = load_program_settings()
    email = (prog.get('email') or {}).get('admin_notification_email') or ''
    email = (email or '').strip()
    if not email:
        return {'notified': False, 'alert_count': len(alerts), 'reason': 'no_admin_email'}
    lines = '\n'.join(f"- {a.get('schedule_id')}: {a.get('status')} — {a.get('detail', '')[:200]}" for a in alerts)
    body = f"Case PM scheduled report failures (ledger {ledger_id}):\n\n{lines}"
    sent = send_workflow_email(email, 'Case PM — scheduled report failures', f'<pre>{body}</pre>', body)
    write_audit(db, models, ledger_id, user_id=None, action='cron_schedule_failure_email', details={'count': len(alerts), 'sent': sent})
    return {'notified': sent, 'alert_count': len(alerts)}


def report_designer_column_catalog() -> dict:
    from accounting_waves_19 import report_designer_column_catalog as base

    catalog = dict(base())
    catalog['job_cost_summary'] = ['project_id', 'billed_ar', 'committed_ap', 'variance_billed_vs_ar']
    catalog['ap_aging'].append('vendor_name')
    catalog['ar_aging'].append('customer_name')
    return catalog


def efile_status_dashboard(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('compliance_efile_log') or []
    filed = settings.get('compliance_filed') or {}
    return {
        'transmit_log_count': len(log),
        'recent_transmits': log[-8:],
        'filed_deadlines': len(filed),
        'disclaimer': 'Transmit log is audit trail only — confirm with your CPA before agency filing.',
    }


def cron_wave10_maintenance(db, models, secret: str) -> dict:
    """Optional cron hook: compliance reminders + schedule failure emails per ledger."""
    import os

    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    from accounting_waves_18 import cron_run_scheduled_reports

    reports = cron_run_scheduled_reports(db, models, secret)
    AcctLedger = models['AcctLedger']
    extras = []
    for ledger in AcctLedger.query.limit(20).all():
        comp = compliance_cron_reminders(db, models, ledger.id)
        sched = notify_admin_schedule_failures(db, models, ledger.id)
        extras.append({'ledger_id': ledger.id, 'compliance': comp, 'schedule_alerts': sched})
    return {'scheduled_reports': reports, 'maintenance': extras}


def ensure_case_pm_db_untracked(app_root: str | None = None) -> dict:
    """Best-effort: stop tracking instance/case_pm.db before git pull."""
    root = app_root or os.path.abspath(os.path.dirname(__file__) or '.')
    db_rel = 'instance/case_pm.db'
    tracked = False
    try:
        proc = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', db_rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        tracked = proc.returncode == 0
    except Exception:
        tracked = False
    if not tracked:
        return {'was_tracked': False, 'removed_from_index': False}
    try:
        subprocess.run(
            ['git', 'rm', '--cached', '-f', db_rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {'was_tracked': True, 'removed_from_index': True}
    except Exception as exc:
        return {'was_tracked': True, 'removed_from_index': False, 'error': str(exc)}


def git_tracked_paths_must_not_include_db(app_root: str | None = None) -> list[str]:
    root = app_root or os.path.abspath(os.path.dirname(__file__) or '.')
    problems = []
    try:
        proc = subprocess.run(
            ['git', 'ls-files', 'instance/case_pm.db', 'instance/*.db'],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in (proc.stdout or '').splitlines():
            if line.strip().endswith('.db'):
                problems.append(line.strip())
    except Exception as exc:
        problems.append(f'git ls-files failed: {exc}')
    return problems
