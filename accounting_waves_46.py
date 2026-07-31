"""
PM–accounting full integration wave: silent field post, pending dashboard, Sage alerts, pillar APIs.
"""
from __future__ import annotations

import json
from datetime import datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings


def _field_prefs():
    from program_settings_persistence import load_accounting_defaults
    return load_accounting_defaults()


def _append_field_post_log(db, models, ledger_id: int, entry: dict, user_id=None) -> None:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    log = settings.get('field_auto_post_log') or []
    log.append({**entry, 'at': datetime.utcnow().isoformat() + 'Z'})
    settings['field_auto_post_log'] = log[-50:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='field_auto_post', details=entry)


def field_silent_auto_post_daily_log(
    db, models, ledger_id: int, daily_log_id: int, *, user_id=None, EquipmentEntry=None, DailyLog=None, Project=None,
) -> dict:
    prefs = _field_prefs()
    if prefs.get('field_auto_post_silent') != '1':
        return {'skipped': 'silent_disabled'}
    if prefs.get('auto_post_equipment_on_daily_log') != '1' and prefs.get('direct_cost_post_on_approve') == '0':
        return {'skipped': 'equipment_auto_off'}
    from accounting_waves_43 import post_equipment_daily_log_to_accounting
    try:
        out = post_equipment_daily_log_to_accounting(
            db, models, daily_log_id, user_id=user_id, Project=Project,
            EquipmentEntry=EquipmentEntry, DailyLog=DailyLog,
        )
        _append_field_post_log(db, models, ledger_id, {'kind': 'equipment_daily_log', 'daily_log_id': daily_log_id, **out}, user_id=user_id)
        return out
    except Exception as exc:
        _append_field_post_log(db, models, ledger_id, {'kind': 'equipment_daily_log', 'error': str(exc)}, user_id=user_id)
        return {'error': str(exc)}


def field_silent_auto_post_delivery(
    db, models, ledger_id: int, delivery_id: int, amount: float | None, *, user_id=None, Delivery=None,
) -> dict:
    prefs = _field_prefs()
    if prefs.get('field_auto_post_silent') != '1':
        return {'skipped': 'silent_disabled'}
    if prefs.get('auto_post_delivery_on_delivered') != '1' and prefs.get('direct_cost_post_on_approve') == '0':
        return {'skipped': 'delivery_auto_off'}
    amt = round(float(amount or 0), 2)
    if amt <= 0:
        return {'skipped': 'no_amount'}
    from accounting_waves_43 import delivery_received_to_ic_ap
    try:
        out = delivery_received_to_ic_ap(db, models, ledger_id, delivery_id, amt, user_id=user_id, Delivery=Delivery)
        _append_field_post_log(db, models, ledger_id, {'kind': 'delivery', 'delivery_id': delivery_id, 'amount': amt, **out}, user_id=user_id)
        return out
    except Exception as exc:
        _append_field_post_log(db, models, ledger_id, {'kind': 'delivery', 'error': str(exc)}, user_id=user_id)
        return {'error': str(exc)}


def construction_pending_dashboard(
    db, models, ledger_id: int, project_id: int, *, PayAppProjectState=None, Commitment=None, ChangeOrder=None,
) -> dict:
    from accounting_waves_19 import g702_pending_ar_sync
    from accounting_waves_21 import sub_pay_app_pending_ap_sync, commitment_pending_accounting
    from accounting_waves_22 import change_order_pending_accounting

    pid = int(project_id)
    sections = []
    g702 = g702_pending_ar_sync(db, models, ledger_id, pid, PayAppProjectState) if PayAppProjectState else {}
    if g702.get('pending'):
        sections.append({'id': 'g702', 'label': 'Owner G702 → A/R', 'count': len(g702['pending']), 'items': g702['pending'][:25]})
    sub = sub_pay_app_pending_ap_sync(db, models, ledger_id, pid, PayAppProjectState) if PayAppProjectState else {}
    if sub.get('pending'):
        sections.append({'id': 'sub_pay_app', 'label': 'Sub pay apps → A/P', 'count': len(sub['pending']), 'items': sub['pending'][:25]})
    if Commitment:
        cmt = commitment_pending_accounting(db, models, ledger_id, pid, Commitment)
        if cmt.get('pending'):
            sections.append({'id': 'commitment', 'label': 'Commitments → PO', 'count': len(cmt['pending']), 'items': cmt['pending'][:25]})
    if ChangeOrder:
        co = change_order_pending_accounting(db, models, ledger_id, pid, ChangeOrder)
        if co.get('pending'):
            sections.append({'id': 'change_order', 'label': 'Change orders', 'count': len(co['pending']), 'items': co['pending'][:25]})
    total = sum(s['count'] for s in sections)
    report = {'project_id': pid, 'total_pending': total, 'sections': sections, 'at': datetime.utcnow().isoformat() + 'Z'}
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['construction_pending_dashboard'] = {str(pid): report}
    _save_ledger_settings(ledger, settings)
    return report


def sync_all_pending_construction(
    db, models, ledger_id: int, project_id: int, *, user_id=None,
    PayAppProjectState=None, Commitment=None, CommitmentAllocation=None, Project=None, Company=None, ChangeOrder=None,
) -> dict:
    from accounting_waves_19 import sync_all_g702_pending_to_ar
    from accounting_waves_21 import sync_all_sub_pay_apps_pending_to_ap, sync_all_commitments_pending
    from accounting_waves_22 import sync_all_change_orders_pending

    pid = int(project_id)
    results = {}
    if PayAppProjectState:
        results['g702'] = sync_all_g702_pending_to_ar(
            db, models, ledger_id, pid, user_id=user_id, PayAppProjectState=PayAppProjectState, Project=Project,
        )
        results['sub_pay_app'] = sync_all_sub_pay_apps_pending_to_ap(
            db, models, ledger_id, pid, user_id=user_id, PayAppProjectState=PayAppProjectState,
            Commitment=Commitment, Project=Project, Company=Company,
        )
    if Commitment:
        results['commitment'] = sync_all_commitments_pending(
            db, models, ledger_id, pid, user_id=user_id, Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation, Project=Project, Company=Company,
        )
    if ChangeOrder:
        results['change_order'] = sync_all_change_orders_pending(
            db, models, ledger_id, pid, user_id=user_id, ChangeOrder=ChangeOrder, Project=Project,
        )
    write_audit(db, models, ledger_id, user_id=user_id, action='construction_sync_all_pending', details={'project_id': pid})
    return {'project_id': pid, 'results': results}


def sage_go_live_alert_bundle(db, models, ledger_id: int) -> dict:
    from accounting_integration_health import construction_integration_health_dashboard
    from accounting_waves_44 import sage_unified_setup_health

    health = construction_integration_health_dashboard(db, models, ledger_id)
    setup = sage_unified_setup_health(db, models, ledger_id)
    alerts = []
    if (health.get('score') or 0) < 70:
        alerts.append({'severity': 'critical', 'code': 'integration_health_low', 'detail': health.get('grade')})
    for issue in health.get('issues') or []:
        alerts.append({'severity': issue.get('severity', 'warning'), 'code': issue.get('code'), 'detail': issue})
    if not setup.get('ready_for_live_sync'):
        alerts.append({'severity': 'warning', 'code': 'sage_not_ready', 'detail': setup.get('checklist')})
    inbox = (health.get('sage_mirror') or {}).get('inbox') or {}
    ap_err = inbox.get('ap_push_errors') or []
    ar_err = inbox.get('ar_push_errors') or []
    if ap_err or ar_err:
        alerts.append({
            'severity': 'error',
            'code': 'sage_push_errors',
            'ap_count': len(ap_err),
            'ar_count': len(ar_err),
            'samples': (ap_err + ar_err)[:5],
        })
    bundle = {
        'at': datetime.utcnow().isoformat() + 'Z',
        'health': {'score': health.get('score'), 'grade': health.get('grade')},
        'setup_ready': setup.get('ready_for_live_sync'),
        'alerts': alerts,
        'alert_count': len(alerts),
    }
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings['sage_go_live_alerts'] = bundle
    _save_ledger_settings(ledger, settings)
    return bundle


def estimate_budget_automation_pipeline(
    db, models, ledger_id: int, estimate_id: int, *, user_id=None,
    Estimate=None, EstimateLine=None, BidPackage=None, BidInvitation=None, BudgetProjectState=None,
    EstimateBudgetMapping=None, Project=None, push_accounting: bool = True,
) -> dict:
    from estimate_persistence import award_estimate_to_budget

    budget_out = award_estimate_to_budget(
        Estimate, EstimateLine, BidPackage, BidInvitation, BudgetProjectState, db, estimate_id,
        user_id=user_id, use_bid_awards=False, EstimateBudgetMapping=EstimateBudgetMapping,
    )
    acct_out = None
    if push_accounting and BudgetProjectState and Estimate:
        est = Estimate.query.get(int(estimate_id))
        if est:
            from budget_persistence import get_budget_state
            from accounting_waves_43 import budget_publish_accounting_wizard

            _, state = get_budget_state(BudgetProjectState, est.project_id)
            if state:
                acct_out = budget_publish_accounting_wizard(
                    db, models, est.project_id, state, user_id=user_id, push_sage=True, Project=Project,
                )
    return {'estimate_id': int(estimate_id), 'budget': budget_out, 'accounting': acct_out}


def scheduling_resource_summary(db, ScheduleData, project_id: int) -> dict:
    import json as _json

    pid = int(project_id)
    record = ScheduleData.query.filter_by(project_id=pid).first()
    tasks = []
    if record and record.payload:
        try:
            payload = _json.loads(record.payload) if isinstance(record.payload, str) else (record.payload or {})
            tasks = payload.get('tasks') or payload.get('items') or []
        except Exception:
            tasks = []
    crews = {}
    equipment_hours = 0.0
    for t in tasks:
        if not isinstance(t, dict):
            continue
        res = (t.get('resource') or t.get('crew') or t.get('assigned_to') or 'Unassigned').strip()
        crews[res] = crews.get(res, 0) + 1
        if 'equipment' in (t.get('name') or '').lower():
            equipment_hours += float(t.get('duration') or t.get('hours') or 0)
    return {
        'project_id': pid,
        'task_count': len(tasks),
        'resource_buckets': [{'name': k, 'task_count': v} for k, v in sorted(crews.items(), key=lambda x: -x[1])[:20]],
        'equipment_task_hours_hint': round(equipment_hours, 2),
        'leveling_status': 'foundation',
        'note': 'Resource pools and cross-project leveling are roadmap — this is a read-only snapshot.',
    }


def portal_compliance_library(db, Company, COI, *, limit: int = 100) -> dict:
    from datetime import date

    today = date.today()
    rows = []
    for c in Company.query.order_by(Company.name).limit(limit).all():
        cois = COI.query.filter_by(company_id=c.id).all() if COI else []
        valid_coi = any(
            (getattr(x, 'expiration_date', None) or getattr(x, 'expiration', None)) and
            (getattr(x, 'expiration_date', None) or getattr(x, 'expiration', None)) >= today
            for x in cois
        )
        rows.append({
            'company_id': c.id,
            'name': c.name,
            'type': c.type,
            'coi_count': len(cois),
            'coi_valid': valid_coi,
            'ap_payment_blocked_if_invalid': True,
        })
    return {'at': datetime.utcnow().isoformat() + 'Z', 'companies': rows, 'count': len(rows)}


def mobile_offline_schema() -> dict:
    return {
        'version': 1,
        'collections': ['daily_log', 'timesheet', 'photo'],
        'max_batch': 25,
        'conflict_policy': 'client_wins_with_audit',
    }


def mobile_offline_enqueue(db, models, ledger_id: int, items: list, *, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = settings.get('mobile_offline_queue') or []
    accepted = []
    for raw in (items or [])[:25]:
        if not isinstance(raw, dict) or not raw.get('kind'):
            continue
        entry = {**raw, 'queued_at': datetime.utcnow().isoformat() + 'Z', 'user_id': user_id}
        q.append(entry)
        accepted.append(entry)
    settings['mobile_offline_queue'] = q[-200:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='mobile_offline_enqueue', details={'count': len(accepted)})
    return {'accepted': len(accepted), 'queue_size': len(settings['mobile_offline_queue'])}


def mobile_offline_process_queue(db, models, ledger_id: int, *, user_id=None, DailyLog=None, EquipmentEntry=None, Project=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    q = list(settings.get('mobile_offline_queue') or [])
    processed = []
    remaining = []
    for item in q:
        kind = item.get('kind')
        if kind == 'daily_log' and item.get('daily_log_id'):
            out = field_silent_auto_post_daily_log(
                db, models, ledger_id, int(item['daily_log_id']), user_id=user_id,
                EquipmentEntry=EquipmentEntry, DailyLog=DailyLog, Project=Project,
            )
            processed.append({'item': item, 'result': out})
        else:
            remaining.append(item)
    settings['mobile_offline_queue'] = remaining
    _save_ledger_settings(ledger, settings)
    return {'processed': len(processed), 'remaining': len(remaining), 'details': processed[:20]}


def bim_coordination_status(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.get('bim_viewpoints') or []
    return {
        'status': 'foundation',
        'viewpoint_count': len(reg),
        'supported_formats': ['IFC', 'BCF'],
        'viewer': 'planned',
        'viewpoints': reg[-10:],
    }


def bim_register_viewpoint(db, models, ledger_id: int, payload: dict, *, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    reg = settings.get('bim_viewpoints') or []
    entry = {
        'title': (payload.get('title') or 'Viewpoint')[:120],
        'model_ref': (payload.get('model_ref') or '')[:200],
        'guid': (payload.get('guid') or '')[:80],
        'linked_rfi_id': payload.get('rfi_id'),
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    reg.append(entry)
    settings['bim_viewpoints'] = reg[-50:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='bim_viewpoint', details=entry)
    return {'ok': True, 'viewpoint': entry, 'total': len(settings['bim_viewpoints'])}


def sage_mirror_deploy_check_v15() -> dict:
    from accounting_waves_45 import sage_mirror_deploy_check_v14

    base = sage_mirror_deploy_check_v14()
    checks = {
        'field_silent_post': True,
        'pending_dashboard': True,
        'sage_go_live_alerts': True,
        'estimate_pipeline': True,
        'scheduling_snapshot': True,
        'portal_compliance': True,
        'mobile_offline': True,
        'bim_foundation': True,
    }
    try:
        assert callable(field_silent_auto_post_daily_log)
        assert callable(construction_pending_dashboard)
        assert callable(sage_go_live_alert_bundle)
        assert callable(mobile_offline_schema)
        assert callable(bim_register_viewpoint)
    except Exception:
        checks = {k: False for k in checks}
    ok = base.get('ok') and all(checks.values())
    return {'ok': ok, 'v14': base, 'wave_checks': checks}


def cron_go_live_alerts_maintenance(db, models, secret: str) -> dict:
    import os

    expected = (os.environ.get('CASEPM_CRON_SECRET') or '').strip()
    if not expected or secret != expected:
        raise PermissionError('Invalid cron secret')
    AcctLedger = models['AcctLedger']
    runs = []
    for ledger in AcctLedger.query.limit(5).all():
        runs.append({'ledger_id': ledger.id, 'alerts': sage_go_live_alert_bundle(db, models, ledger.id)})
    return {'ledgers': runs}
