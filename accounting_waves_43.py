"""
PM → accounting depth: budget publish, equipment, burden, deliveries, AP compliance, 10-segment G/L.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from accounting_platform import write_audit

from accounting_waves_24 import _ledger_settings, _save_ledger_settings, sage_write_guard


def budget_publish_accounting_wizard(
    db,
    models,
    project_id: int,
    budget_state: dict,
    *,
    user_id=None,
    push_sage: bool = True,
    Project=None,
) -> dict:
    """Run after budget publish: builtin log, optional Sage BudgetSageSync queue, contract snapshot."""
    from accounting_persistence import get_or_create_default_ledger

    ledger = get_or_create_default_ledger(db, models['AcctLedger'])
    settings = _ledger_settings(ledger)
    lines = budget_state.get('budgetLines') or []
    total = round(sum(float(ln.get('original_budget') or ln.get('revised_budget') or 0) for ln in lines), 2)
    entry = {
        'project_id': int(project_id),
        'revision': budget_state.get('budgetRevision'),
        'lines': len(lines),
        'total_budget': total,
        'contract_amount': budget_state.get('budgetContractAmount'),
        'at': datetime.utcnow().isoformat() + 'Z',
    }
    log = settings.get('budget_publish_accounting_log') or []
    log.append(entry)
    settings['budget_publish_accounting_log'] = log[-40:]
    sage_out = None
    if push_sage:
        from accounting_waves_25 import sage_queue_construction_mirror_event

        sage_out = sage_queue_construction_mirror_event(
            db, models, ledger.id, 'BudgetSageSync',
            {'project_id': project_id, 'revision': entry['revision'], 'total_budget': total},
            user_id=user_id,
        )
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger.id, user_id=user_id, action='budget_publish_accounting', details=entry)
    return {'ledger_id': ledger.id, 'publish': entry, 'sage_queue': sage_out}


def post_equipment_daily_log_to_accounting(
    db, models, daily_log_id: int, *, user_id=None, Project=None, EquipmentEntry=None, DailyLog=None,
) -> dict:
    """Post equipment hours from a daily log as DirectCostPosted (equipment expense)."""
    if not EquipmentEntry or not DailyLog:
        raise ValueError('Equipment models required')
    log = DailyLog.query.get(int(daily_log_id))
    if not log or not log.project_id:
        raise ValueError('Daily log or project missing')
    from program_settings_persistence import load_accounting_defaults

    defaults = load_accounting_defaults()
    rates = defaults.get('equipment_hourly_rates') or {}
    default_rate = float(defaults.get('equipment_default_hourly_rate') or 85)
    burden = float(defaults.get('labor_burden_percent') or 0)
    posted = []
    for row in EquipmentEntry.query.filter_by(daily_log_id=log.id).all():
        hours = float(getattr(row, 'hours', None) or row.quantity or 1)
        name = (row.equipment_name or 'Equipment')[:80]
        rate = float(rates.get(name) or rates.get(name.lower()) or default_rate)
        amount = round(hours * rate * (1 + burden / 100.0), 2)
        if amount <= 0:
            continue
        from accounting_posting import process_construction_event

        out = process_construction_event(
            'DirectCostPosted',
            int(log.project_id),
            {
                'amount': amount,
                'cost_code': '01-5300',
                'cost_type': 'Equipment',
                'idempotency_key': f'equipment-log-{log.id}-{row.id}',
                'equipment_name': name,
                'hours': hours,
                'force_builtin_post': True,
            },
            db=db,
            models=models,
            user_id=user_id,
            Project=Project,
        )
        posted.append({'equipment_row_id': row.id, **out})
    return {'daily_log_id': log.id, 'posted_count': len(posted), 'posted': posted}


def apply_labor_burden_to_timesheet_amount(labor_cost: float) -> dict:
    from program_settings_persistence import load_accounting_defaults

    d = load_accounting_defaults()
    pct = float(d.get('labor_burden_percent') or 0)
    base = round(float(labor_cost or 0), 2)
    burden = round(base * pct / 100.0, 2) if pct else 0.0
    return {'base_labor': base, 'burden_amount': burden, 'total': round(base + burden, 2), 'burden_percent': pct}


def post_labor_burden_gl_only(
    db, models, ledger_id: int, project_id: int, labor_cost: float, user_id=None, *, timesheet_ref: str = '',
) -> dict:
    split = apply_labor_burden_to_timesheet_amount(labor_cost)
    if split['burden_amount'] <= 0:
        return {'skipped': True, **split}
    from accounting_posting import _account_by_number, _create_posted_batch, load_accounting_options

    opts = load_accounting_options()
    AcctGLAccount = models['AcctGLAccount']
    try:
        burden_acct = _account_by_number(AcctGLAccount, ledger_id, '5310')
    except ValueError:
        burden_acct = _account_by_number(AcctGLAccount, ledger_id, opts['labor_expense'])
    clearing = _account_by_number(AcctGLAccount, ledger_id, opts['payroll_liability'])
    batch = _create_posted_batch(
        db, models, ledger_id=ledger_id, source='PAYROLL',
        description=f'Labor burden {timesheet_ref}'[:120],
        user_id=user_id,
        lines=[
            {'account_id': burden_acct.id, 'debit': split['burden_amount'], 'credit': 0, 'project_id': project_id},
            {'account_id': clearing.id, 'debit': 0, 'credit': split['burden_amount'], 'project_id': project_id},
        ],
    )
    return {'burden_batch_id': batch.id, **split}


def post_timesheet_with_burden_gl(
    db, models, ledger_id: int, project_id: int, labor_cost: float, user_id=None, *, timesheet_ref: str = '',
) -> dict:
    from accounting_waves_23 import post_labor_journal_for_project

    split = apply_labor_burden_to_timesheet_amount(labor_cost)
    labor = post_labor_journal_for_project(
        db, models, ledger_id, project_id, split['base_labor'], user_id=user_id, reference=timesheet_ref,
    )
    burden_batch = None
    if split['burden_amount'] > 0:
        from accounting_posting import _account_by_number, _create_posted_batch, load_accounting_options

        opts = load_accounting_options()
        AcctGLAccount = models['AcctGLAccount']
        labor_acct = _account_by_number(AcctGLAccount, ledger_id, opts['labor_expense'])
        try:
            burden_acct = _account_by_number(AcctGLAccount, ledger_id, '5310')
        except ValueError:
            burden_acct = labor_acct
        clearing = _account_by_number(AcctGLAccount, ledger_id, opts['payroll_liability'])
        batch = _create_posted_batch(
            db, models, ledger_id=ledger_id, source='PAYROLL',
            description=f'Labor burden {timesheet_ref}'[:120],
            user_id=user_id,
            lines=[
                {'account_id': burden_acct.id, 'debit': split['burden_amount'], 'credit': 0, 'project_id': project_id},
                {'account_id': clearing.id, 'debit': 0, 'credit': split['burden_amount'], 'project_id': project_id},
            ],
        )
        burden_batch = batch.id
    return {'labor': labor, 'burden_batch_id': burden_batch, **split}


def delivery_received_to_ic_ap(
    db, models, ledger_id: int, delivery_id: int, amount: float, *, user_id=None, Delivery=None,
) -> dict:
    """Material receipt: debit materials expense / inventory, credit AP accrual."""
    if not Delivery:
        raise ValueError('Delivery model required')
    d = Delivery.query.get(int(delivery_id))
    if not d:
        raise ValueError('Delivery not found')
    amt = round(float(amount or 0), 2)
    if amt <= 0:
        raise ValueError('Receipt amount required')
    from accounting_posting import process_construction_event

    out = process_construction_event(
        'DirectCostPosted',
        int(d.project_id),
        {
            'amount': amt,
            'cost_code': '01-5200',
            'cost_type': 'Material',
            'idempotency_key': f'delivery-{d.id}',
            'po_number': getattr(d, 'po_number', None),
            'description': (d.description or '')[:120],
            'force_builtin_post': True,
        },
        db=db,
        models=models,
        user_id=user_id,
    )
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    settings.setdefault('delivery_accounting_log', []).append({
        'delivery_id': d.id, 'amount': amt, 'at': datetime.utcnow().isoformat() + 'Z', 'post': out,
    })
    settings['delivery_accounting_log'] = settings['delivery_accounting_log'][-30:]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='delivery_received_accounting', details={'delivery_id': d.id, 'amount': amt})
    return out


def ap_payment_compliance_hold(
    db, models, ledger_id: int, vendor_id: int, applications: list, *, PayAppProjectState=None, Project=None,
) -> dict:
    """Block AP payment when sub pay apps lack lien waiver for linked project/vendor."""
    from program_settings_persistence import load_pay_app_defaults

    pa_defaults = load_pay_app_defaults()
    if not pa_defaults.get('require_lien_waiver_on_sub_pay_app', True):
        return {'held': False, 'reason': 'policy_disabled'}
    AcctAPDocument = models['AcctAPDocument']
    holds = []
    for app in applications or []:
        doc_id = app.get('ap_document_id')
        if not doc_id:
            continue
        doc = AcctAPDocument.query.filter_by(id=int(doc_id), ledger_id=ledger_id).first()
        if not doc or not doc.project_id:
            continue
        pid = int(doc.project_id)
        if not PayAppProjectState:
            continue
        from pay_app_persistence import get_pay_app_state

        _, state = get_pay_app_state(PayAppProjectState, pid)
        state = state or {}
        waivers = state.get('subLienWaivers') or {}
        vendor_key = str(vendor_id)
        if not _vendor_has_waiver_for_period(waivers, vendor_key, doc):
            holds.append({
                'ap_document_id': doc.id,
                'project_id': pid,
                'reason': 'missing_sub_lien_waiver',
                'document_number': doc.document_number,
            })
    if holds:
        ledger = models['AcctLedger'].query.get(ledger_id)
        settings = _ledger_settings(ledger)
        settings['ap_compliance_holds'] = holds[-20:]
        _save_ledger_settings(ledger, settings)
        return {'held': True, 'holds': holds}
    return {'held': False}


def _vendor_has_waiver_for_period(waivers: dict, vendor_key: str, doc) -> bool:
    if not waivers:
        return False
    bucket = waivers.get(vendor_key) or waivers.get(str(vendor_key))
    if not bucket:
        for k, v in waivers.items():
            if str(k) == vendor_key:
                bucket = v
                break
    if not bucket:
        return False
    if isinstance(bucket, dict) and bucket:
        return any(isinstance(v, dict) and (v.get('filename') or v.get('file')) for v in bucket.values())
    return bool(bucket)


def save_gl_segment_profile(db, models, ledger_id: int, segment_count: int, labels: list | None = None, user_id=None) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    n = max(1, min(10, int(segment_count)))
    settings['gl_segment_count'] = n
    settings['gl_segment_labels'] = (labels or [f'Segment {i}' for i in range(1, n + 1)])[:10]
    _save_ledger_settings(ledger, settings)
    write_audit(db, models, ledger_id, user_id=user_id, action='gl_segment_profile', details={'count': n})
    return {'segment_count': n, 'labels': settings['gl_segment_labels']}


def gl_segment_profile(db, models, ledger_id: int) -> dict:
    ledger = models['AcctLedger'].query.get(ledger_id)
    settings = _ledger_settings(ledger)
    n = int(settings.get('gl_segment_count') or 3)
    return {
        'segment_count': n,
        'labels': settings.get('gl_segment_labels') or ['Company', 'Department', 'Job'],
        'max_supported': 10,
    }


def validate_gl_segments_for_batch(db, models, ledger_id: int, lines: list) -> dict:
    profile = gl_segment_profile(db, models, ledger_id)
    if profile['segment_count'] <= 3:
        return {'ok': True, 'skipped': True}
    violations = []
    for i, ln in enumerate(lines or []):
        ref = (ln.get('reference') or '')
        parts = [p for p in ref.split('-') if p]
        if len(parts) < profile['segment_count'] and (ln.get('debit') or ln.get('credit')):
            violations.append({'line': i + 1, 'reference': ref, 'expected_segments': profile['segment_count']})
    strict = (_ledger_settings(models['AcctLedger'].query.get(ledger_id)) or {}).get('gl_segment_strict') == '1'
    return {'ok': not violations or not strict, 'violations': violations[:20], 'profile': profile}
