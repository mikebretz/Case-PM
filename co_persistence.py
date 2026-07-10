"""Change Order & PCO persistence helpers, schema migration, and serialization."""
from __future__ import annotations

import json
from datetime import datetime

CO_STATUSES = (
    'Draft', 'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect',
    'Approved', 'Rejected', 'Void',
)
PCO_STATUSES = (
    'Open', 'Pricing', 'Pending Review', 'Approved for CO', 'Promoted', 'Void', 'Closed',
)
BALL_IN_COURT_MAP = {
    'Draft': 'Creator',
    'Submitted': 'Project Manager',
    'Under Review': 'Project Manager',
    'Pending Architect': 'Architect',
    'Pending Owner': 'Owner',
    'Approved': None,
    'Rejected': None,
    'Void': None,
}

# Sequential approval chain (Procore / RedTeam style)
APPROVAL_CHAIN = (
    {'from_status': 'Submitted', 'role': 'Project Manager', 'next_status': 'Pending Architect'},
    {'from_status': 'Pending Architect', 'role': 'Architect', 'next_status': 'Pending Owner'},
    {'from_status': 'Pending Owner', 'role': 'Owner', 'next_status': 'Approved'},
)

ROLE_APPROVERS = {
    'Project Manager': ('Project Manager', 'Admin', 'Contractor Accounting'),
    'Architect': ('Architect', 'Admin'),
    'Owner': ('Owner', 'Admin'),
    'Creator': ('Project Manager', 'Admin', 'Company User'),
}
REASON_CODES = (
    'Owner Request', 'Design Change', 'Unforeseen Condition', 'Code Compliance',
    'Error or Omission', 'Value Engineering', 'Schedule Acceleration', 'Other',
)
DEFAULT_COST_TYPES = (
    'Labor', 'Material', 'Subcontract', 'Equipment', 'General Conditions', 'Other',
)


def ensure_co_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if 'change_order' in tables:
        cols = {c['name'] for c in inspector.get_columns('change_order')}
        additions = {
            'title': 'VARCHAR(200)',
            'company_name': 'VARCHAR(200)',
            'company_id': 'VARCHAR(64)',
            'contact_name': 'VARCHAR(150)',
            'contact_email': 'VARCHAR(150)',
            'contact_phone': 'VARCHAR(50)',
            'ball_in_court_role': 'VARCHAR(80)',
            'source_pco_id': 'INTEGER',
            'schedule_impact_days': 'INTEGER DEFAULT 0',
            'contract_type': 'VARCHAR(40)',
            'submitted_at': 'DATETIME',
            'attachments_json': 'TEXT',
            'linked_rfi_id': 'INTEGER',
            'linked_commitment_ref': 'VARCHAR(80)',
            'approval_stage': 'INTEGER DEFAULT 0',
            'plan_pins_json': 'TEXT',
        }
        for name, col_type in additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE change_order ADD COLUMN {name} {col_type}'))
        db.session.commit()

    if 'change_order_allocation' in tables:
        cols = {c['name'] for c in inspector.get_columns('change_order_allocation')}
        alloc_additions = {
            'description': 'VARCHAR(200)',
            'cost_type': 'VARCHAR(80)',
        }
        for name, col_type in alloc_additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE change_order_allocation ADD COLUMN {name} {col_type}'))
        db.session.commit()

    if 'pco_allocation' in tables:
        cols = {c['name'] for c in inspector.get_columns('pco_allocation')}
        if 'cost_type' not in cols:
            db.session.execute(text('ALTER TABLE pco_allocation ADD COLUMN cost_type VARCHAR(80)'))
            db.session.commit()

    if 'potential_change_order' in tables:
        cols = {c['name'] for c in inspector.get_columns('potential_change_order')}
        pco_additions = {
            'linked_rfi_id': 'INTEGER',
            'linked_commitment_ref': 'VARCHAR(80)',
            'attachments_json': 'TEXT',
        }
        for name, col_type in pco_additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE potential_change_order ADD COLUMN {name} {col_type}'))
        db.session.commit()


def schedule_impact_to_days(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    for key, days in SCHEDULE_IMPACT_OPTIONS.items():
        if key in text:
            return days
    return 0


def schedule_days_to_label(days):
    days = int(days or 0)
    if days <= 0:
        return 'None'
    if days <= 5:
        return 'Minor'
    if days <= 10:
        return 'Moderate'
    return 'Significant'


def co_to_dict(co, allocations=None, revisions=None):
    allocs = allocations
    if allocs is None and hasattr(co, '_allocations_cache'):
        allocs = co._allocations_cache
    return {
        'id': co.id,
        'project_id': co.project_id,
        'number': co.number,
        'title': getattr(co, 'title', None) or co.description,
        'description': co.description,
        'amount': co.amount or 0,
        'reason': co.reason,
        'schedule_impact': co.schedule_impact,
        'schedule_impact_days': getattr(co, 'schedule_impact_days', None) or schedule_impact_to_days(co.schedule_impact),
        'status': co.status,
        'date': co.date.isoformat() if co.date else None,
        'cost_code': co.cost_code,
        'requested_by': co.requested_by,
        'priority': co.priority,
        'revision': co.revision or 0,
        'notes': co.notes,
        'company_name': getattr(co, 'company_name', None),
        'company_id': getattr(co, 'company_id', None),
        'contact_name': getattr(co, 'contact_name', None),
        'contact_email': getattr(co, 'contact_email', None),
        'contact_phone': getattr(co, 'contact_phone', None),
        'ball_in_court_role': getattr(co, 'ball_in_court_role', None),
        'source_pco_id': getattr(co, 'source_pco_id', None),
        'contract_type': getattr(co, 'contract_type', None) or 'Owner',
        'submitted_at': co.submitted_at.isoformat() if getattr(co, 'submitted_at', None) else None,
        'approved_at': co.approved_at.isoformat() if co.approved_at else None,
        'sov_synced_at': co.sov_synced_at.isoformat() if co.sov_synced_at else None,
        'sage_sync_status': co.sage_sync_status,
        'attachments': _parse_json(getattr(co, 'attachments_json', None), []),
        'linked_rfi_id': getattr(co, 'linked_rfi_id', None),
        'linked_commitment_ref': getattr(co, 'linked_commitment_ref', None),
        'plan_pins': _parse_json(getattr(co, 'plan_pins_json', None), []),
        'approval_stage': getattr(co, 'approval_stage', 0) or 0,
        'allocations': [{
            'cost_code': a.cost_code,
            'cost_type': getattr(a, 'cost_type', None) or '',
            'amount': a.amount,
            'description': getattr(a, 'description', ''),
        } for a in (allocs or [])],
        'created_at': co.created_at.isoformat() if co.created_at else None,
    }


def pco_to_dict(pco, allocations=None):
    allocs = allocations
    return {
        'id': pco.id,
        'project_id': pco.project_id,
        'number': pco.number,
        'title': pco.title,
        'description': pco.description,
        'estimated_amount': pco.estimated_amount or 0,
        'status': pco.status,
        'reason': pco.reason,
        'priority': pco.priority,
        'schedule_impact_days': pco.schedule_impact_days or 0,
        'company_name': pco.company_name,
        'company_id': pco.company_id,
        'contact_name': pco.contact_name,
        'contact_email': pco.contact_email,
        'contact_phone': pco.contact_phone,
        'requested_by': pco.requested_by,
        'ball_in_court_role': pco.ball_in_court_role,
        'cost_code': pco.cost_code,
        'notes': pco.notes,
        'change_order_id': pco.change_order_id,
        'linked_rfi_id': getattr(pco, 'linked_rfi_id', None),
        'linked_commitment_ref': getattr(pco, 'linked_commitment_ref', None),
        'allocations': [{
            'cost_code': a.cost_code,
            'cost_type': getattr(a, 'cost_type', None) or '',
            'amount': a.amount,
            'description': getattr(a, 'description', ''),
        } for a in (allocs or [])],
        'updated_at': pco.updated_at.isoformat() if pco.updated_at else None,
    }


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def apply_co_fields(co, data):
    if data.get('title') is not None:
        co.title = data['title']
    if data.get('description') is not None:
        co.description = data['description']
    if data.get('amount') is not None:
        co.amount = float(data['amount'])
    if data.get('reason') is not None:
        co.reason = data['reason']
    if data.get('priority') is not None:
        co.priority = data['priority']
    if data.get('notes') is not None:
        co.notes = data['notes']
    if data.get('cost_code') is not None:
        co.cost_code = data['cost_code']
    if data.get('requested_by') is not None:
        co.requested_by = data['requested_by']
    if data.get('status') is not None:
        co.status = data['status']
    if data.get('revision') is not None:
        co.revision = int(data['revision'])
    if data.get('company_name') is not None:
        co.company_name = data['company_name']
    if data.get('company_id') is not None:
        co.company_id = data['company_id']
    if data.get('contact_name') is not None:
        co.contact_name = data['contact_name']
    if data.get('contact_email') is not None:
        co.contact_email = data['contact_email']
    if data.get('contact_phone') is not None:
        co.contact_phone = data['contact_phone']
    if data.get('contract_type') is not None:
        co.contract_type = data['contract_type']
    if data.get('source_pco_id') is not None:
        co.source_pco_id = data['source_pco_id']
    if data.get('schedule_impact_days') is not None:
        co.schedule_impact_days = int(data['schedule_impact_days'])
        co.schedule_impact = schedule_days_to_label(co.schedule_impact_days)
    elif data.get('schedule_impact') is not None:
        co.schedule_impact = data['schedule_impact']
        co.schedule_impact_days = schedule_impact_to_days(data['schedule_impact'])
    if data.get('ball_in_court_role') is not None:
        co.ball_in_court_role = data['ball_in_court_role']
    if data.get('attachments') is not None:
        co.attachments_json = json.dumps(data['attachments'])
    if data.get('linked_rfi_id') is not None:
        co.linked_rfi_id = int(data['linked_rfi_id']) if data['linked_rfi_id'] else None
    if data.get('linked_commitment_ref') is not None:
        co.linked_commitment_ref = data['linked_commitment_ref']


def apply_pco_fields(pco, data):
    for field in ('title', 'description', 'reason', 'priority', 'notes', 'cost_code', 'requested_by',
                  'company_name', 'company_id', 'contact_name', 'contact_email', 'contact_phone', 'ball_in_court_role',
                  'linked_commitment_ref'):
        if data.get(field) is not None:
            setattr(pco, field, data[field])
    if data.get('linked_rfi_id') is not None:
        pco.linked_rfi_id = int(data['linked_rfi_id']) if data['linked_rfi_id'] else None
    if data.get('estimated_amount') is not None:
        pco.estimated_amount = float(data['estimated_amount'])
    if data.get('status') is not None:
        pco.status = data['status']
    if data.get('schedule_impact_days') is not None:
        pco.schedule_impact_days = int(data['schedule_impact_days'])


def normalize_allocation_rows(allocations):
    """Return non-empty allocation rows from request payload."""
    rows = []
    for item in allocations or []:
        code = (item.get('cost_code') or '').strip()
        ctype = (item.get('cost_type') or '').strip()
        desc = (item.get('description') or '').strip()
        amt = float(item.get('amount') or 0)
        if code or ctype or desc or amt:
            rows.append({
                'cost_code': code,
                'cost_type': ctype,
                'amount': amt,
                'description': desc,
            })
    return rows


def validate_allocations(allocations, *, require_rows=True, require_amount=False):
    rows = normalize_allocation_rows(allocations)
    if require_rows and not rows:
        raise ValueError('At least one cost code allocation is required (cost code, cost type, and amount).')
    cleaned = []
    for i, item in enumerate(rows, 1):
        if not item['cost_code']:
            raise ValueError(f'Allocation row {i}: cost code is required.')
        if not item['cost_type']:
            raise ValueError(f'Allocation row {i}: cost type is required.')
        if require_amount and item['amount'] == 0:
            raise ValueError(f'Allocation row {i}: amount must be non-zero.')
        cleaned.append(item)
    return cleaned


def save_allocations(AllocationModel, parent_id_field, parent_id, allocations, db, extra_fields=None):
    AllocationModel.query.filter(getattr(AllocationModel, parent_id_field) == parent_id).delete()
    for item in allocations or []:
        kwargs = {
            parent_id_field: parent_id,
            'cost_code': item.get('cost_code'),
            'amount': float(item.get('amount') or 0),
        }
        if extra_fields:
            kwargs.update(extra_fields(item))
        row = AllocationModel(**kwargs)
        if hasattr(row, 'description'):
            row.description = item.get('description', '')
        if hasattr(row, 'cost_type'):
            row.cost_type = item.get('cost_type', '')
        db.session.add(row)


def promote_pco_to_co(
    PotentialChangeOrder,
    PCOAllocation,
    ChangeOrder,
    ChangeOrderAllocation,
    db,
    pco_id,
    user_id,
    generate_number_fn,
):
    pco = PotentialChangeOrder.query.get(pco_id)
    if not pco:
        raise ValueError('PCO not found')
    if pco.change_order_id:
        raise ValueError('PCO already promoted')
    if pco.status not in ('Approved for CO', 'Pending Review', 'Pricing', 'Open'):
        pass  # allow promote from most states

    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    total = sum(a.amount for a in allocs) if allocs else (pco.estimated_amount or 0)
    alloc_payload = [{
        'cost_code': a.cost_code,
        'cost_type': getattr(a, 'cost_type', None),
        'amount': a.amount,
        'description': getattr(a, 'description', ''),
    } for a in allocs]
    validate_allocations(alloc_payload, require_rows=True, require_amount=True)

    co = ChangeOrder(
        project_id=pco.project_id,
        number=generate_number_fn('CO', ChangeOrder),
        title=pco.title,
        description=pco.description or pco.title or 'Change Order from PCO',
        amount=total,
        reason=pco.reason,
        schedule_impact=schedule_days_to_label(pco.schedule_impact_days),
        schedule_impact_days=pco.schedule_impact_days or 0,
        status='Draft',
        date=datetime.utcnow().date(),
        cost_code=pco.cost_code,
        requested_by=pco.requested_by,
        priority=pco.priority,
        notes=pco.notes,
        company_name=pco.company_name,
        company_id=pco.company_id,
        contact_name=pco.contact_name,
        contact_email=pco.contact_email,
        contact_phone=pco.contact_phone,
        source_pco_id=pco.id,
        ball_in_court_role='Creator',
        contract_type='Owner',
        linked_rfi_id=getattr(pco, 'linked_rfi_id', None),
        created_by_id=user_id,
    )
    db.session.add(co)
    db.session.flush()

    if allocs:
        for a in allocs:
            db.session.add(ChangeOrderAllocation(
                change_order_id=co.id,
                cost_code=a.cost_code,
                cost_type=getattr(a, 'cost_type', None) or '',
                amount=a.amount,
                description=getattr(a, 'description', '') or '',
            ))
    elif pco.cost_code and total:
        db.session.add(ChangeOrderAllocation(
            change_order_id=co.id,
            cost_code=pco.cost_code,
            cost_type='Other',
            amount=total,
        ))

    pco.change_order_id = co.id
    pco.status = 'Promoted'
    pco.ball_in_court_role = None
    db.session.commit()
    return co


def compute_dashboard_stats(ChangeOrder, PotentialChangeOrder, project_id):
    cos = ChangeOrder.query.filter_by(project_id=project_id).all()
    pcos = PotentialChangeOrder.query.filter_by(project_id=project_id).all()

    approved = [c for c in cos if c.status == 'Approved']
    pending_statuses = {'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect', 'Pending'}
    pending = [c for c in cos if c.status in pending_statuses]
    open_pcos = [p for p in pcos if p.status not in ('Promoted', 'Void', 'Closed')]

    approved_total = sum(c.amount or 0 for c in approved)
    pending_total = sum(c.amount or 0 for c in pending)
    pco_rom = sum(p.estimated_amount or 0 for p in open_pcos)

    approval_days = []
    for c in approved:
        if c.approved_at and c.created_at:
            approval_days.append((c.approved_at - c.created_at).total_seconds() / 86400)
    avg_days = round(sum(approval_days) / len(approval_days), 1) if approval_days else 0

    return {
        'total_cos': len(cos),
        'approved_count': len(approved),
        'pending_count': len(pending),
        'open_pco_count': len(open_pcos),
        'approved_total': approved_total,
        'pending_total': pending_total,
        'pco_rom_total': pco_rom,
        'avg_approval_days': avg_days,
    }


def get_budget_cost_types(BudgetProjectState, project_id):
    from budget_persistence import get_budget_state
    _, state = get_budget_state(BudgetProjectState, project_id)
    types = state.get('costTypes') or []
    merged = list(DEFAULT_COST_TYPES)
    for t in types:
        if t and t not in merged:
            merged.append(t)
    return merged


def get_budget_cost_codes(BudgetProjectState, project_id):
    from budget_persistence import get_budget_state
    _, state = get_budget_state(BudgetProjectState, project_id)
    lines = state.get('budgetLines') or []
    custom = state.get('customCostCodes') or []
    codes = []
    seen = set()
    for line in lines:
        code = line.get('cost_code')
        if code and code not in seen:
            seen.add(code)
            codes.append({
                'code': code,
                'description': line.get('description', ''),
                'cost_type': line.get('cost_type', ''),
                'original_budget': line.get('original_budget', 0),
                'approved_changes': line.get('approved_changes', 0),
                'pending': line.get('pending', 0),
            })
    for item in custom:
        code = item.get('code')
        if code and code not in seen:
            seen.add(code)
            codes.append({
                'code': code,
                'description': item.get('description', ''),
                'cost_type': item.get('cost_type', ''),
                'original_budget': 0,
                'approved_changes': 0,
                'pending': 0,
            })
    return codes


def user_can_act_on_ball_in_court(user, role):
    if not user or not role:
        return False
    if user.role == 'Admin':
        return True
    allowed = ROLE_APPROVERS.get(role, (role,))
    return user.role in allowed


def get_next_approval_step(current_status):
    for step in APPROVAL_CHAIN:
        if step['from_status'] == current_status:
            return step
    return None


def set_ball_in_court(co, status=None):
    status = status or co.status
    co.ball_in_court_role = BALL_IN_COURT_MAP.get(status, co.ball_in_court_role)


def notify_ball_in_court(project_id, co, User, title=None, description=None):
    role = co.ball_in_court_role
    if not role:
        return
    try:
        import case_workflow as cw
        action_url = f'/change-orders?project_id={project_id}'
        title = title or f'{co.number} — ball in court: {role}'
        description = description or (co.description or getattr(co, 'title', None) or '')
        users = User.query.filter_by(status='Active').all()
        targets = [u for u in users if user_can_act_on_ball_in_court(u, role)]
        if not targets:
            targets = cw.find_assignees(project_id, 'Change Orders')
        for u in targets:
            cw.notify_user(u.id, title, description, action_url)
            cw.create_internal_message(
                u.id,
                folder='action-required',
                msg_type='alert',
                subject=title,
                preview=description[:500],
                body=f'<p>{description}</p><p><strong>Ball in court:</strong> {role}</p>',
                project_id=project_id,
                from_label='Change Orders',
                module='Change Orders',
                action_url=action_url,
                action_label='Review Change Order',
                priority='high',
                requires_action=True,
            )
    except Exception:
        pass


def co_workflow_action(co, action, user, User, allocations=None):
    action = (action or '').lower()
    if action in ('submit', 'approve'):
        validate_allocations(allocations or [], require_rows=True, require_amount=True)
    if action == 'submit':
        if co.status not in ('Draft',):
            raise ValueError('Only draft change orders can be submitted')
        co.status = 'Submitted'
        co.approval_stage = 0
        set_ball_in_court(co)
        return co.status, False

    if action == 'reject':
        co.status = 'Rejected'
        co.ball_in_court_role = None
        return co.status, False

    if action == 'approve':
        role = co.ball_in_court_role
        if not user_can_act_on_ball_in_court(user, role):
            raise ValueError(f'Your role cannot approve while ball is with {role}')
        step = get_next_approval_step(co.status)
        if not step:
            raise ValueError('No approval step for current status')
        next_status = step['next_status']
        co.status = next_status
        co.approval_stage = (co.approval_stage or 0) + 1
        set_ball_in_court(co)
        if next_status == 'Approved':
            co.ball_in_court_role = None
            return co.status, True
        return co.status, False

    raise ValueError('action must be submit, approve, or reject')


def attachment_record(filename, original_name, uploaded_by_id=None):
    return {
        'filename': filename,
        'original_name': original_name,
        'uploaded_at': datetime.utcnow().isoformat() + 'Z',
        'uploaded_by_id': uploaded_by_id,
    }


def append_attachment(co, record):
    items = _parse_json(getattr(co, 'attachments_json', None), [])
    items.append(record)
    co.attachments_json = json.dumps(items)
    return items


def delete_change_order(
    co,
    db,
    AllocationModel,
    RevisionModel,
    PotentialChangeOrder,
    *,
    force=False,
):
    if co.status == 'Approved' and not force:
        raise ValueError('Approved change orders require force delete for testing.')
    pcos = PotentialChangeOrder.query.filter_by(change_order_id=co.id).all()
    for pco in pcos:
        pco.change_order_id = None
        if pco.status == 'Promoted':
            pco.status = 'Approved for CO'
    AllocationModel.query.filter_by(change_order_id=co.id).delete()
    RevisionModel.query.filter_by(change_order_id=co.id).delete()
    db.session.delete(co)

