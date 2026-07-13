"""Pay application server persistence, change order SOV sync, and schema helpers."""
from __future__ import annotations

import json
from datetime import datetime

# Keys mirrored from pay_applications.html localStorage (project-scoped via casepmStore)
PAY_APP_STATE_KEYS = (
    'contractorSOV',
    'payAppBillingLines',
    'currentPayAppPeriod',
    'payAppHistory',
    'subcontractorSOV',
    'subPayAppHistory',
    'subPendingSubmissions',
    'subPayAppNumbers',
    'subSOVStatus',
    'subLienWaivers',
    'subLienWaiverArchive',
    'previousSubPayAppArchive',
    'mainLienWaiver',
    'payAppRetainagePercent',
    'requireLienWaiverOnSubPayApp',
    'requireSubmissionDeadline',
    'submissionDeadlineDay',
    'allowZeroDollarSubPayApps',
    'requireAllSubPayAppsBeforeG702Submit',
    'payAppAuditLog',
    'sageSyncAutoEnabled',
    'contractorSOVLocked',
)

SCHEDULE_IMPACT_DAYS = {
    'none': 0,
    'no impact': 0,
    'minor': 5,
    'moderate': 10,
    'significant': 14,
    'major': 14,
    'critical': 30,
}


def ensure_pay_app_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if 'change_order' in tables:
        cols = {c['name'] for c in inspector.get_columns('change_order')}
        additions = {
            'cost_code': 'VARCHAR(30)',
            'requested_by': 'VARCHAR(150)',
            'priority': 'VARCHAR(20)',
            'revision': 'INTEGER DEFAULT 0',
            'notes': 'TEXT',
            'approved_at': 'DATETIME',
            'approved_by_id': 'INTEGER',
            'sov_synced_at': 'DATETIME',
            'sage_sync_status': 'VARCHAR(30)',
        }
        for name, col_type in additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE change_order ADD COLUMN {name} {col_type}'))
        db.session.commit()


def register_models(db):
  class PayAppProjectState(db.Model):
      __tablename__ = 'pay_app_project_state'
      id = db.Column(db.Integer, primary_key=True)
      project_id = db.Column(db.Integer, db.ForeignKey('project.id'), unique=True, nullable=False)
      data_json = db.Column(db.Text, default='{}')
      version = db.Column(db.Integer, default=1)
      updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
      updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

  class SageSyncEvent(db.Model):
      __tablename__ = 'sage_sync_event'
      id = db.Column(db.Integer, primary_key=True)
      project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
      event_type = db.Column(db.String(80), nullable=False)
      status = db.Column(db.String(30), default='queued')
      sage_job_number = db.Column(db.String(80))
      message = db.Column(db.Text)
      payload_json = db.Column(db.Text)
      response_json = db.Column(db.Text)
      error_text = db.Column(db.Text)
      created_at = db.Column(db.DateTime, default=datetime.utcnow)
      posted_at = db.Column(db.DateTime, nullable=True)
      created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

  class ChangeOrderAllocation(db.Model):
      __tablename__ = 'change_order_allocation'
      id = db.Column(db.Integer, primary_key=True)
      change_order_id = db.Column(db.Integer, db.ForeignKey('change_order.id'), nullable=False)
      cost_code = db.Column(db.String(30))
      amount = db.Column(db.Float, default=0)
      sov_line_legacy_id = db.Column(db.String(64))

  return PayAppProjectState, SageSyncEvent, ChangeOrderAllocation


def _parse_state(record):
    if not record or not record.data_json:
        return {}
    try:
        return json.loads(record.data_json)
    except (TypeError, json.JSONDecodeError):
        return {}


def get_pay_app_state(PayAppProjectState, project_id):
    record = PayAppProjectState.query.filter_by(project_id=project_id).first()
    if not record:
        return None, {}
    return record, _parse_state(record)


def save_pay_app_state(PayAppProjectState, db, project_id, data, user_id=None):
    if not isinstance(data, dict):
        raise ValueError('data must be a dict')
    record = PayAppProjectState.query.filter_by(project_id=project_id).first()
    payload = json.dumps(data)
    if record:
        record.data_json = payload
        record.version = (record.version or 0) + 1
        record.updated_by_id = user_id
        record.updated_at = datetime.utcnow()
    else:
        record = PayAppProjectState(
            project_id=project_id,
            data_json=payload,
            version=1,
            updated_by_id=user_id,
        )
        db.session.add(record)
    db.session.commit()
    return record


def merge_state_patch(existing, patch):
    merged = dict(existing or {})
    for key, value in (patch or {}).items():
        if key in PAY_APP_STATE_KEYS or key.startswith('_'):
            merged[key] = value
    return merged


def normalize_cost_code(code):
    if not code:
        return ''
    return str(code).replace(' ', '').replace('-', '').upper()


def apply_co_to_contractor_sov(state_data, amount, cost_code=None, description=None):
    """Add approved change order amount to contractor SOV co_amount."""
    lines = state_data.get('contractorSOV') or []
    if not isinstance(lines, list):
        lines = []
    target_norm = normalize_cost_code(cost_code)
    applied = 0.0
    remaining = float(amount or 0)
    line_desc = (description or '').strip() or (f'Change Order — {cost_code}' if cost_code else 'Change Order')

    if target_norm:
        for line in lines:
            if normalize_cost_code(line.get('cost_code')) == target_norm:
                line['co_amount'] = float(line.get('co_amount') or 0) + remaining
                applied = remaining
                remaining = 0
                break
        if remaining > 0:
            lines.append({
                'id': int(datetime.utcnow().timestamp() * 1000),
                'cost_code': cost_code,
                'description': line_desc,
                'original': 0,
                'co_amount': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'notes': 'Auto-created from approved change order',
            })
            applied += remaining
    else:
        if lines:
            lines[0]['co_amount'] = float(lines[0].get('co_amount') or 0) + remaining
            applied = remaining
        else:
            lines.append({
                'id': int(datetime.utcnow().timestamp() * 1000),
                'cost_code': '01-0000',
                'description': 'Unallocated Change Orders',
                'original': 0,
                'co_amount': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'notes': 'Holding line for CO without cost code',
            })
            applied = remaining

    state_data['contractorSOV'] = lines
    return state_data, applied


def _find_sub_sov_keys_for_company(sub_sov, company_id=None, company_name=None):
    """Resolve subcontractorSOV dict keys for a vendor (numeric id and/or name)."""
    keys = []
    seen = set()
    sub_sov = sub_sov or {}

    def add(key):
        k = str(key).strip() if key is not None else ''
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    if company_id is not None and str(company_id).strip() != '':
        add(company_id)
    if company_name:
        add(company_name.strip())
        name_lower = company_name.strip().lower()
        for k in sub_sov:
            if str(k).strip().lower() == name_lower:
                add(k)

    return keys


def resolve_sub_sov_targets_for_allocation(co, sub_sov, allocation, Commitment=None):
    """Determine which subcontractor SOV buckets should receive a CO allocation."""
    targets = []
    seen = set()
    sub_sov = sub_sov or {}

    def add(key):
        k = str(key).strip() if key is not None else ''
        if k and k not in seen:
            seen.add(k)
            targets.append(k)

    company_id = getattr(co, 'company_id', None)
    company_name = getattr(co, 'company_name', None)
    for k in _find_sub_sov_keys_for_company(sub_sov, company_id, company_name):
        add(k)

    linked_ref = getattr(co, 'linked_commitment_ref', None)
    if linked_ref and Commitment is not None:
        commitment = Commitment.query.filter_by(
            project_id=co.project_id,
            number=linked_ref,
        ).first()
        if commitment:
            for k in _find_sub_sov_keys_for_company(
                sub_sov, getattr(commitment, 'company_id', None), commitment.company_name,
            ):
                add(k)

    cost_code = getattr(allocation, 'cost_code', None)
    if isinstance(allocation, dict):
        cost_code = allocation.get('cost_code')
    target_norm = normalize_cost_code(cost_code)
    if target_norm:
        for company_key, lines in sub_sov.items():
            for line in lines or []:
                if normalize_cost_code(line.get('cost_code')) == target_norm:
                    add(company_key)
                    break

    contract_type = (getattr(co, 'contract_type', None) or '').strip()
    if not targets and contract_type in ('Subcontract', 'Subcontractor'):
        if company_id is not None and str(company_id).strip() != '':
            add(str(company_id))
        elif company_name:
            add(company_name.strip())

    return targets


def apply_co_to_subcontractor_sov(state_data, company_key, amount, cost_code=None, description=None, co_number=None, sov_line_id=None):
    """Add approved change order amount to a subcontractor SOV line (change_orders column)."""
    sub_sov = state_data.get('subcontractorSOV') or {}
    if not isinstance(sub_sov, dict):
        sub_sov = {}
    lines = sub_sov.get(company_key) or []
    if not isinstance(lines, list):
        lines = []

    remaining = float(amount or 0)
    target_norm = normalize_cost_code(cost_code)
    line_desc = (description or '').strip() or (
        f'CO {co_number} — {cost_code}' if co_number and cost_code else f'Change Order {co_number or ""}'.strip()
    )
    applied = 0.0

    if sov_line_id:
        for line in lines:
            if str(line.get('id')) == str(sov_line_id):
                if co_number and line.get('from_change_order') == co_number:
                    return state_data, 0.0
                line['change_orders'] = float(line.get('change_orders') or 0) + remaining
                orig = float(line.get('original_commitment') or 0)
                line['scheduled_value'] = orig + float(line.get('change_orders') or 0)
                if co_number:
                    line['from_change_order'] = co_number
                applied = remaining
                remaining = 0
                break

    if target_norm and remaining > 0:
        for line in lines:
            if normalize_cost_code(line.get('cost_code')) == target_norm:
                if co_number and line.get('from_change_order') == co_number:
                    return state_data, 0.0
                line['change_orders'] = float(line.get('change_orders') or 0) + remaining
                orig = float(line.get('original_commitment') or 0)
                line['scheduled_value'] = orig + float(line.get('change_orders') or 0)
                if co_number:
                    line['from_change_order'] = co_number
                applied = remaining
                remaining = 0
                break
        if remaining > 0:
            lines.append({
                'id': f'co-{co_number or "new"}-{target_norm}-{int(datetime.utcnow().timestamp() * 1000)}',
                'cost_code': cost_code,
                'description': line_desc,
                'original_commitment': 0,
                'change_orders': remaining,
                'scheduled_value': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'work_this_period': 0,
                'materials_stored': 0,
                'notes': f'Auto-created from approved change order {co_number or ""}'.strip(),
                'from_change_order': co_number,
            })
            applied += remaining
    elif remaining > 0:
        if lines:
            line = lines[0]
            line['change_orders'] = float(line.get('change_orders') or 0) + remaining
            orig = float(line.get('original_commitment') or 0)
            line['scheduled_value'] = orig + float(line.get('change_orders') or 0)
            if co_number:
                line['from_change_order'] = co_number
            applied = remaining
        else:
            lines.append({
                'id': f'co-{co_number or "new"}-unalloc-{int(datetime.utcnow().timestamp() * 1000)}',
                'cost_code': '01-0000',
                'description': line_desc or 'Unallocated Change Orders',
                'original_commitment': 0,
                'change_orders': remaining,
                'scheduled_value': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'work_this_period': 0,
                'materials_stored': 0,
                'notes': f'Auto-created from approved change order {co_number or ""}'.strip(),
                'from_change_order': co_number,
            })
            applied = remaining

    sub_sov[company_key] = lines
    state_data['subcontractorSOV'] = sub_sov
    return state_data, applied


def schedule_impact_to_days(schedule_impact):
    if not schedule_impact:
        return 0
    text = str(schedule_impact).strip().lower()
    if text.isdigit():
        return int(text)
    for key, days in SCHEDULE_IMPACT_DAYS.items():
        if key in text:
            return days
    return 0


def apply_schedule_impact(ScheduleData, Project, db, project_id, schedule_impact, co_number, description):
    days = schedule_impact_to_days(schedule_impact)
    if days <= 0:
        return None

    project = Project.query.get(project_id)
    record = ScheduleData.query.filter_by(project_id=project_id).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except (TypeError, json.JSONDecodeError):
            payload = {}

    tasks = payload.get('tasks') or payload.get('data') or []
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    marker_id = f'co-{co_number}-{int(datetime.utcnow().timestamp())}'
    tasks.append({
        'id': marker_id,
        'text': f'CO {co_number}: {description[:80] if description else "Schedule impact"}',
        'type': 'milestone',
        'duration': days,
        'progress': 0,
        'open': True,
        'parent': 0,
        'notes': f'Schedule impact +{days} days from approved change order {co_number}',
    })
    if 'tasks' in payload:
        payload['tasks'] = tasks
    elif 'data' in payload:
        payload['data'] = tasks
    else:
        payload['tasks'] = tasks

    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        record = ScheduleData(project_id=project_id, payload=payload_json)
        db.session.add(record)

    if project and project.end_date:
        from datetime import timedelta
        project.end_date = project.end_date + timedelta(days=days)

    db.session.commit()
    return {'days_added': days, 'task_id': marker_id}


def sync_change_order_to_sov(
    ChangeOrder,
    ChangeOrderAllocation,
    PayAppProjectState,
    ScheduleData,
    Project,
    db,
    co_id,
    user_id=None,
    Commitment=None,
):
    co = ChangeOrder.query.get(co_id)
    if not co:
        raise ValueError('Change order not found')
    if co.status != 'Approved':
        raise ValueError('Change order must be Approved to sync to SOV')

    record, state = get_pay_app_state(PayAppProjectState, co.project_id)
    already_contractor_synced = bool(co.sov_synced_at)

    allocations = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    sub_sov = state.get('subcontractorSOV') or {}

    total_applied = 0.0
    sub_total_applied = 0.0
    sub_updates = []

    if allocations:
        if not already_contractor_synced:
            for alloc in allocations:
                state, applied = apply_co_to_contractor_sov(
                    state,
                    alloc.amount,
                    alloc.cost_code,
                    getattr(alloc, 'description', None),
                )
                total_applied += applied

        for alloc in allocations:
            targets = resolve_sub_sov_targets_for_allocation(co, sub_sov, alloc, Commitment)
            sub_sov = state.get('subcontractorSOV') or sub_sov
            for company_key in targets:
                state, sub_applied = apply_co_to_subcontractor_sov(
                    state,
                    company_key,
                    alloc.amount,
                    alloc.cost_code,
                    getattr(alloc, 'description', None),
                    co.number,
                )
                if sub_applied:
                    sub_total_applied += sub_applied
                    sub_updates.append({
                        'company_key': company_key,
                        'cost_code': alloc.cost_code,
                        'amount': sub_applied,
                    })
            sub_sov = state.get('subcontractorSOV') or sub_sov
    elif not already_contractor_synced:
        state, applied = apply_co_to_contractor_sov(state, co.amount, getattr(co, 'cost_code', None))
        total_applied += applied

    if not already_contractor_synced or sub_total_applied > 0:
        save_pay_app_state(PayAppProjectState, db, co.project_id, state, user_id)
    if not already_contractor_synced:
        co.sov_synced_at = datetime.utcnow()
        schedule_result = apply_schedule_impact(
            ScheduleData, Project, db, co.project_id,
            co.schedule_impact, co.number, co.description,
        )
    else:
        schedule_result = None
        if sub_total_applied > 0:
            db.session.commit()
        else:
            return {
                'already_synced': True,
                'sov_amount_applied': 0,
                'sub_sov_amount_applied': 0,
                'contractorSOV': state.get('contractorSOV'),
                'subcontractorSOV': state.get('subcontractorSOV'),
                'sub_sov_updates': [],
            }

    if not already_contractor_synced:
        db.session.commit()
    return {
        'already_synced': already_contractor_synced,
        'sov_amount_applied': total_applied,
        'sub_sov_amount_applied': sub_total_applied,
        'sub_sov_updates': sub_updates,
        'contractorSOV': state.get('contractorSOV'),
        'subcontractorSOV': state.get('subcontractorSOV'),
        'schedule': schedule_result,
    }
