"""RFI persistence, schema migration, workflow, and serialization."""
from __future__ import annotations

import json
from datetime import datetime, date

RFI_STATUSES = (
    'Draft', 'Open', 'Under Review', 'Awaiting Response', 'Answered', 'Closed', 'Void',
)
RFI_PRIORITIES = ('Low', 'Medium', 'High', 'Critical')
BALL_IN_COURT_BY_STATUS = {
    'Draft': 'RFI Manager',
    'Open': 'Assignee',
    'Under Review': 'Assignee',
    'Awaiting Response': 'Assignee',
    'Answered': 'RFI Manager',
    'Closed': None,
    'Void': None,
}


def ensure_rfi_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if 'rfi' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('rfi')}
    additions = {
        'from_party': 'VARCHAR(150)',
        'to_party': 'VARCHAR(150)',
        'received_from_company': 'VARCHAR(200)',
        'received_from_contact': 'VARCHAR(150)',
        'responsible_contractor': 'VARCHAR(200)',
        'rfi_manager_name': 'VARCHAR(150)',
        'assignees_json': 'TEXT',
        'distribution_json': 'TEXT',
        'ball_in_court_role': 'VARCHAR(80)',
        'official_answer': 'TEXT',
        'answered_at': 'DATETIME',
        'answered_by_id': 'INTEGER',
        'notes': 'TEXT',
        'cost_impact_amount': 'FLOAT',
        'schedule_impact_days': 'INTEGER DEFAULT 0',
        'schedule_impact_label': 'VARCHAR(50)',
        'is_private': 'INTEGER DEFAULT 0',
        'attachments_json': 'TEXT',
        'responses_json': 'TEXT',
        'plan_pins_json': 'TEXT',
        'linked_pco_id': 'INTEGER',
        'updated_at': 'DATETIME',
        'closed_at': 'DATETIME',
        'submitted_at': 'DATETIME',
        'location_description': 'VARCHAR(300)',
        'discipline': 'VARCHAR(80)',
    }
    for name, col_type in additions.items():
        if name not in cols:
            db.session.execute(text(f'ALTER TABLE rfi ADD COLUMN {name} {col_type}'))
    db.session.commit()


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _iso(dt):
    if not dt:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)


def rfi_to_dict(rfi, linked_cos=None, linked_pcos=None):
    return {
        'id': rfi.id,
        'project_id': rfi.project_id,
        'number': rfi.number,
        'subject': rfi.subject,
        'question': rfi.question,
        'priority': rfi.priority or 'Medium',
        'status': rfi.status or 'Open',
        'date': _iso(rfi.date),
        'due_date': _iso(rfi.due_date),
        'drawing_reference': rfi.drawing_reference,
        'spec_reference': rfi.spec_reference,
        'from_party': getattr(rfi, 'from_party', None),
        'to_party': getattr(rfi, 'to_party', None),
        'received_from_company': getattr(rfi, 'received_from_company', None),
        'received_from_contact': getattr(rfi, 'received_from_contact', None),
        'responsible_contractor': getattr(rfi, 'responsible_contractor', None),
        'rfi_manager_name': getattr(rfi, 'rfi_manager_name', None),
        'assignees': _parse_json(getattr(rfi, 'assignees_json', None), []),
        'distribution': _parse_json(getattr(rfi, 'distribution_json', None), []),
        'ball_in_court_role': getattr(rfi, 'ball_in_court_role', None),
        'official_answer': getattr(rfi, 'official_answer', None),
        'answered_at': _iso(getattr(rfi, 'answered_at', None)),
        'notes': getattr(rfi, 'notes', None),
        'cost_impact_amount': getattr(rfi, 'cost_impact_amount', None) or 0,
        'schedule_impact_days': getattr(rfi, 'schedule_impact_days', None) or 0,
        'schedule_impact_label': getattr(rfi, 'schedule_impact_label', None),
        'is_private': bool(getattr(rfi, 'is_private', 0)),
        'attachments': _parse_json(getattr(rfi, 'attachments_json', None), []),
        'responses': _parse_json(getattr(rfi, 'responses_json', None), []),
        'plan_pins': _parse_json(getattr(rfi, 'plan_pins_json', None), []),
        'linked_pco_id': getattr(rfi, 'linked_pco_id', None),
        'location_description': getattr(rfi, 'location_description', None),
        'discipline': getattr(rfi, 'discipline', None),
        'linked_change_orders': linked_cos or [],
        'linked_pcos': linked_pcos or [],
        'created_at': _iso(rfi.created_at),
        'updated_at': _iso(getattr(rfi, 'updated_at', None)),
        'closed_at': _iso(getattr(rfi, 'closed_at', None)),
        'submitted_at': _iso(getattr(rfi, 'submitted_at', None)),
        'created_by_id': rfi.created_by_id,
        'answered_by_id': getattr(rfi, 'answered_by_id', None),
        'is_overdue': _is_overdue(rfi),
    }


def _is_overdue(rfi):
    if not rfi.due_date:
        return False
    if rfi.status in ('Closed', 'Void', 'Answered'):
        return False
    due = rfi.due_date
    if isinstance(due, datetime):
        due = due.date()
    return due < date.today()


def apply_rfi_fields(rfi, data, *, is_create=False):
    simple = (
        'subject', 'question', 'priority', 'drawing_reference', 'spec_reference',
        'from_party', 'to_party', 'received_from_company', 'received_from_contact',
        'responsible_contractor', 'rfi_manager_name', 'official_answer',
        'notes', 'schedule_impact_label', 'location_description', 'discipline', 'linked_pco_id',
    )
    for key in simple:
        if data.get(key) is not None:
            setattr(rfi, key, data[key])
    if data.get('status') is not None or data.get('ball_in_court_role') is not None:
        if is_create and data.get('status') in ('Draft', 'Open'):
            rfi.status = data['status']
            if data.get('ball_in_court_role') is not None:
                rfi.ball_in_court_role = data['ball_in_court_role']
        # else workflow only
    if data.get('date') is not None:
        rfi.date = _parse_date(data['date'])
    if data.get('due_date') is not None:
        rfi.due_date = _parse_date(data['due_date'])
    if data.get('cost_impact_amount') is not None:
        rfi.cost_impact_amount = float(data['cost_impact_amount'] or 0)
    if data.get('schedule_impact_days') is not None:
        rfi.schedule_impact_days = int(data['schedule_impact_days'] or 0)
    if data.get('is_private') is not None:
        rfi.is_private = 1 if data['is_private'] else 0
    if data.get('assignees') is not None:
        rfi.assignees_json = json.dumps(data['assignees'])
    if data.get('distribution') is not None:
        rfi.distribution_json = json.dumps(data['distribution'])
    if data.get('attachments') is not None:
        rfi.attachments_json = json.dumps(data['attachments'])
    if data.get('responses') is not None:
        rfi.responses_json = json.dumps(data['responses'])
    if data.get('plan_pins') is not None:
        rfi.plan_pins_json = json.dumps(data['plan_pins'])
    rfi.updated_at = datetime.utcnow()


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def compute_rfi_dashboard(RFI, project_id):
    today = date.today()
    rfis = RFI.query.filter_by(project_id=project_id).all()
    open_statuses = {'Open', 'Under Review', 'Awaiting Response'}
    answered_statuses = {'Answered'}
    overdue = 0
    awaiting = 0
    for r in rfis:
        if r.status in open_statuses:
            awaiting += 1
            if r.due_date and r.due_date < today:
                overdue += 1
    return {
        'total': len(rfis),
        'open': sum(1 for r in rfis if r.status in open_statuses),
        'awaiting_response': awaiting,
        'answered': sum(1 for r in rfis if r.status in answered_statuses),
        'closed': sum(1 for r in rfis if r.status == 'Closed'),
        'overdue': overdue,
        'draft': sum(1 for r in rfis if r.status == 'Draft'),
        'with_cost_impact': sum(1 for r in rfis if (getattr(r, 'cost_impact_amount', 0) or 0) > 0),
        'with_schedule_impact': sum(1 for r in rfis if (getattr(r, 'schedule_impact_days', 0) or 0) > 0),
    }


def add_response(rfi, body, user_id, user_name):
    responses = _parse_json(getattr(rfi, 'responses_json', None), [])
    entry = {
        'id': len(responses) + 1,
        'body': body.get('body', ''),
        'is_official': bool(body.get('is_official')),
        'user_id': user_id,
        'user_name': user_name,
        'created_at': datetime.utcnow().isoformat(),
        'attachments': body.get('attachments') or [],
    }
    responses.append(entry)
    rfi.responses_json = json.dumps(responses)
    if entry['is_official']:
        rfi.official_answer = entry['body']
        rfi.answered_at = datetime.utcnow()
        rfi.answered_by_id = user_id
        rfi.status = 'Answered'
        rfi.ball_in_court_role = 'RFI Manager'
    rfi.updated_at = datetime.utcnow()
    return entry


def workflow_rfi(rfi, action, user_name=None):
    action = (action or '').lower()
    now = datetime.utcnow()
    if action == 'submit':
        rfi.status = 'Open'
        rfi.submitted_at = now
        rfi.ball_in_court_role = 'Assignee'
    elif action == 'return_to_assignee':
        rfi.ball_in_court_role = 'Assignee'
        if rfi.status == 'Answered':
            rfi.status = 'Under Review'
    elif action == 'return_to_manager':
        rfi.ball_in_court_role = 'RFI Manager'
        rfi.status = 'Under Review'
    elif action == 'close':
        rfi.status = 'Closed'
        rfi.closed_at = now
        rfi.ball_in_court_role = None
    elif action == 'reopen':
        rfi.status = 'Open'
        rfi.closed_at = None
        rfi.ball_in_court_role = 'Assignee'
    elif action == 'void':
        rfi.status = 'Void'
        rfi.ball_in_court_role = None
    else:
        raise ValueError(f'Unknown workflow action: {action}')
    rfi.updated_at = now
    return rfi


def get_linked_records(rfi_id, ChangeOrder, PotentialChangeOrder):
    cos = ChangeOrder.query.filter_by(linked_rfi_id=rfi_id).all()
    pcos = PotentialChangeOrder.query.filter_by(linked_rfi_id=rfi_id).all()
    return (
        [{'id': c.id, 'number': c.number, 'title': getattr(c, 'title', None) or c.description, 'status': c.status} for c in cos],
        [{'id': p.id, 'number': p.number, 'title': p.title, 'status': p.status} for p in pcos],
    )
