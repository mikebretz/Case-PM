"""RFI persistence, schema migration, workflow, and serialization."""
from __future__ import annotations

import json
from datetime import datetime, date

RFI_STATUSES = (
    'Draft', 'Open', 'Under Review', 'Awaiting Response', 'Answered', 'Closed', 'Void',
)
RFI_PRIORITIES = ('Low', 'Medium', 'High', 'Critical')
RFI_PROJECT_STAGES = ('Preconstruction', 'Construction', 'Closeout', 'Warranty', 'Other')
BALL_IN_COURT_BY_STATUS = {
    'Draft': 'RFI Manager',
    'Open': 'Assignee',
    'Under Review': 'RFI Manager',
    'Awaiting Response': 'Assignee',
    'Answered': 'RFI Manager',
    'Closed': None,
    'Void': None,
}
OPEN_RFI_REQUIRED_FIELDS = (
    'subject', 'question', 'due_date', 'rfi_manager_name', 'assignees',
)


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
        'cost_impact_label': 'VARCHAR(50)',
        'schedule_impact_days': 'INTEGER DEFAULT 0',
        'schedule_impact_label': 'VARCHAR(50)',
        'is_private': 'INTEGER DEFAULT 0',
        'attachments_json': 'TEXT',
        'responses_json': 'TEXT',
        'comments_json': 'TEXT',
        'plan_pins_json': 'TEXT',
        'linked_pco_id': 'INTEGER',
        'updated_at': 'DATETIME',
        'closed_at': 'DATETIME',
        'submitted_at': 'DATETIME',
        'location_description': 'VARCHAR(300)',
        'discipline': 'VARCHAR(80)',
        'rfi_manager_user_id': 'INTEGER',
        'ball_in_court_user_id': 'INTEGER',
        'reference': 'VARCHAR(200)',
        'cost_code': 'VARCHAR(100)',
        'project_stage': 'VARCHAR(100)',
        'date_initiated': 'DATETIME',
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


def normalize_party_list(items):
    """Normalize assignees/distribution to [{user_id?, name}] while accepting legacy strings."""
    if items is None:
        return []
    if not isinstance(items, list):
        items = [items]
    out = []
    for item in items:
        if isinstance(item, dict):
            name = (item.get('name') or item.get('label') or '').strip()
            uid = item.get('user_id')
            if uid is not None:
                try:
                    uid = int(uid)
                except (TypeError, ValueError):
                    uid = None
            if name or uid:
                out.append({'user_id': uid, 'name': name or f'User #{uid}'})
        else:
            text = str(item or '').strip()
            if text:
                out.append({'user_id': None, 'name': text})
    return out


def party_names(items):
    return [p.get('name') or '' for p in normalize_party_list(items) if p.get('name')]


def party_user_ids(items):
    ids = []
    for p in normalize_party_list(items):
        uid = p.get('user_id')
        if uid is not None:
            ids.append(int(uid))
    return ids


def _first_assignee_user_id(rfi):
    return next(iter(party_user_ids(_parse_json(getattr(rfi, 'assignees_json', None), []))), None)


def _manager_user_id(rfi):
    uid = getattr(rfi, 'rfi_manager_user_id', None)
    if uid:
        return int(uid)
    return None


def _set_ball_in_court(rfi, role, user_id=None):
    rfi.ball_in_court_role = role
    if user_id is not None:
        rfi.ball_in_court_user_id = user_id
    elif role == 'Assignee':
        rfi.ball_in_court_user_id = _first_assignee_user_id(rfi)
    elif role == 'RFI Manager':
        rfi.ball_in_court_user_id = _manager_user_id(rfi)
    else:
        rfi.ball_in_court_user_id = None


def compute_days_outstanding(rfi):
    if rfi.status in ('Closed', 'Void', 'Draft'):
        return None
    start = getattr(rfi, 'date_initiated', None) or rfi.submitted_at or rfi.created_at
    if not start:
        return None
    if isinstance(start, datetime):
        start = start.date()
    elif not isinstance(start, date):
        return None
    end = rfi.closed_at or date.today()
    if isinstance(end, datetime):
        end = end.date()
    return max(0, (end - start).days)


def validate_rfi_open_fields(rfi):
    """Validate Procore-style required fields to open an RFI."""
    errors = []
    if not (rfi.subject or '').strip():
        errors.append('Subject is required')
    if not (rfi.question or '').strip():
        errors.append('Question is required')
    if not rfi.due_date:
        errors.append('Due date is required')
    manager = (getattr(rfi, 'rfi_manager_name', None) or '').strip()
    if not manager and not getattr(rfi, 'rfi_manager_user_id', None):
        errors.append('RFI Manager is required')
    assignees = normalize_party_list(_parse_json(getattr(rfi, 'assignees_json', None), []))
    if not assignees:
        errors.append('At least one assignee is required')
    if errors:
        raise ValueError('; '.join(errors))


def user_can_access_private_rfi(user, rfi, *, is_privileged=None):
    """Return True if user may view a private RFI."""
    if not getattr(rfi, 'is_private', 0):
        return True
    if not user:
        return False
    if is_privileged is None:
        is_privileged = getattr(user, 'role', None) in ('Admin', 'Developer')
    if is_privileged:
        return True
    uid = getattr(user, 'id', None)
    if uid is None:
        return False
    uid = int(uid)
    if getattr(rfi, 'created_by_id', None) == uid:
        return True
    if getattr(rfi, 'rfi_manager_user_id', None) == uid:
        return True
    if getattr(rfi, 'ball_in_court_user_id', None) == uid:
        return True
    assignee_ids = party_user_ids(_parse_json(getattr(rfi, 'assignees_json', None), []))
    if uid in assignee_ids:
        return True
    dist_ids = party_user_ids(_parse_json(getattr(rfi, 'distribution_json', None), []))
    if uid in dist_ids:
        return True
    user_name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
    if user_name:
        for name in party_names(_parse_json(getattr(rfi, 'assignees_json', None), [])):
            if name.lower() == user_name.lower():
                return True
        for name in party_names(_parse_json(getattr(rfi, 'distribution_json', None), [])):
            if name.lower() == user_name.lower():
                return True
        manager = (getattr(rfi, 'rfi_manager_name', None) or '').strip()
        if manager and manager.lower() == user_name.lower():
            return True
    return False


def _iso(dt):
    if not dt:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)


def rfi_to_dict(rfi, linked_cos=None, linked_pcos=None, *, User=None):
    assignees = normalize_party_list(_parse_json(getattr(rfi, 'assignees_json', None), []))
    distribution = normalize_party_list(_parse_json(getattr(rfi, 'distribution_json', None), []))
    ball_user_id = getattr(rfi, 'ball_in_court_user_id', None)
    manager_user_id = getattr(rfi, 'rfi_manager_user_id', None)
    ball_user_name = None
    manager_user_name = None
    if User is not None:
        if ball_user_id:
            u = User.query.get(int(ball_user_id))
            if u:
                ball_user_name = f'{u.first_name} {u.last_name}'.strip() or u.email
        if manager_user_id:
            u = User.query.get(int(manager_user_id))
            if u:
                manager_user_name = f'{u.first_name} {u.last_name}'.strip() or u.email
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
        'date_initiated': _iso(getattr(rfi, 'date_initiated', None)),
        'drawing_reference': rfi.drawing_reference,
        'spec_reference': rfi.spec_reference,
        'reference': getattr(rfi, 'reference', None),
        'cost_code': getattr(rfi, 'cost_code', None),
        'project_stage': getattr(rfi, 'project_stage', None),
        'from_party': getattr(rfi, 'from_party', None),
        'to_party': getattr(rfi, 'to_party', None),
        'received_from_company': getattr(rfi, 'received_from_company', None),
        'received_from_contact': getattr(rfi, 'received_from_contact', None),
        'responsible_contractor': getattr(rfi, 'responsible_contractor', None),
        'rfi_manager_name': getattr(rfi, 'rfi_manager_name', None),
        'rfi_manager_user_id': manager_user_id,
        'rfi_manager_user_name': manager_user_name,
        'assignees': assignees,
        'assignee_names': party_names(assignees),
        'distribution': distribution,
        'distribution_names': party_names(distribution),
        'ball_in_court_role': getattr(rfi, 'ball_in_court_role', None),
        'ball_in_court_user_id': ball_user_id,
        'ball_in_court_user_name': ball_user_name,
        'official_answer': getattr(rfi, 'official_answer', None),
        'answered_at': _iso(getattr(rfi, 'answered_at', None)),
        'notes': getattr(rfi, 'notes', None),
        'cost_impact_amount': getattr(rfi, 'cost_impact_amount', None) or 0,
        'cost_impact_label': getattr(rfi, 'cost_impact_label', None),
        'schedule_impact_days': getattr(rfi, 'schedule_impact_days', None) or 0,
        'schedule_impact_label': getattr(rfi, 'schedule_impact_label', None),
        'is_private': bool(getattr(rfi, 'is_private', 0)),
        'attachments': _parse_json(getattr(rfi, 'attachments_json', None), []),
        'responses': _parse_json(getattr(rfi, 'responses_json', None), []),
        'comments': _parse_json(getattr(rfi, 'comments_json', None), []),
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
        'days_outstanding': compute_days_outstanding(rfi),
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
        'notes', 'cost_impact_label', 'schedule_impact_label', 'location_description', 'discipline',
        'linked_pco_id', 'reference', 'cost_code', 'project_stage',
    )
    for key in simple:
        if data.get(key) is not None:
            setattr(rfi, key, data[key])
    if data.get('rfi_manager_user_id') is not None:
        try:
            rfi.rfi_manager_user_id = int(data['rfi_manager_user_id']) if data['rfi_manager_user_id'] else None
        except (TypeError, ValueError):
            rfi.rfi_manager_user_id = None
    if data.get('status') is not None or data.get('ball_in_court_role') is not None:
        if is_create and data.get('status') in ('Draft', 'Open'):
            rfi.status = data['status']
            if data.get('ball_in_court_role') is not None:
                _set_ball_in_court(rfi, data['ball_in_court_role'], data.get('ball_in_court_user_id'))
        # else workflow only
    if data.get('date') is not None:
        rfi.date = _parse_date(data['date'])
    if data.get('due_date') is not None:
        rfi.due_date = _parse_date(data['due_date'])
    if data.get('date_initiated') is not None:
        rfi.date_initiated = _parse_datetime(data['date_initiated'])
    if data.get('cost_impact_amount') is not None:
        rfi.cost_impact_amount = float(data['cost_impact_amount'] or 0)
    if data.get('cost_impact_label') is not None:
        rfi.cost_impact_label = data['cost_impact_label']
    if data.get('schedule_impact_days') is not None:
        rfi.schedule_impact_days = int(data['schedule_impact_days'] or 0)
    if data.get('schedule_impact_label') is not None:
        rfi.schedule_impact_label = data['schedule_impact_label']
    if data.get('is_private') is not None:
        rfi.is_private = 1 if data['is_private'] else 0
    if data.get('assignees') is not None:
        rfi.assignees_json = json.dumps(normalize_party_list(data['assignees']))
    if data.get('distribution') is not None:
        rfi.distribution_json = json.dumps(normalize_party_list(data['distribution']))
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


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00').split('+')[0])
    except ValueError:
        return _parse_date(value)


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
        _apply_official_response(rfi, entry, user_id)
    else:
        rfi.status = 'Under Review'
        _set_ball_in_court(rfi, 'RFI Manager')
    rfi.updated_at = datetime.utcnow()
    return entry


def _apply_official_response(rfi, entry, user_id):
    responses = _parse_json(getattr(rfi, 'responses_json', None), [])
    entry_id = int(entry.get('id', -1))
    for resp in responses:
        resp['is_official'] = int(resp.get('id', -1)) == entry_id
    rfi.responses_json = json.dumps(responses)
    rfi.official_answer = entry.get('body', '')
    rfi.answered_at = datetime.utcnow()
    rfi.answered_by_id = user_id
    rfi.status = 'Answered'
    _set_ball_in_court(rfi, 'RFI Manager')


def mark_response_official(rfi, response_id, user_id):
    responses = _parse_json(getattr(rfi, 'responses_json', None), [])
    target = None
    for resp in responses:
        if int(resp.get('id', -1)) == int(response_id):
            target = resp
            break
    if not target:
        raise ValueError('Response not found')
    _apply_official_response(rfi, target, user_id)
    rfi.updated_at = datetime.utcnow()
    return target


def workflow_rfi(rfi, action, user_name=None):
    action = (action or '').lower()
    now = datetime.utcnow()
    if action == 'submit':
        validate_rfi_open_fields(rfi)
        rfi.status = 'Open'
        rfi.submitted_at = now
        rfi.date_initiated = now
        _set_ball_in_court(rfi, 'Assignee')
    elif action == 'open':
        validate_rfi_open_fields(rfi)
        rfi.status = 'Open'
        rfi.submitted_at = now
        rfi.date_initiated = now
        _set_ball_in_court(rfi, 'Assignee')
    elif action == 'return_to_assignee':
        rfi.status = 'Awaiting Response'
        _set_ball_in_court(rfi, 'Assignee')
    elif action == 'return_to_manager':
        rfi.status = 'Under Review'
        _set_ball_in_court(rfi, 'RFI Manager')
    elif action == 'close':
        rfi.status = 'Closed'
        rfi.closed_at = now
        _set_ball_in_court(rfi, None)
    elif action == 'reopen':
        rfi.status = 'Open'
        rfi.closed_at = None
        rfi.date_initiated = now
        _set_ball_in_court(rfi, 'Assignee')
    elif action == 'void':
        rfi.status = 'Void'
        _set_ball_in_court(rfi, None)
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


def delete_rfi_record(db, rfi, upload_root, *, DrawingMarkup=None, ChangeOrder=None,
                      PotentialChangeOrder=None, ApprovalRequest=None):
    """Permanently delete an RFI and unlink related records (developer/admin maintenance)."""
    import os
    import shutil

    rfi_id = int(rfi.id)
    sid = str(rfi_id)

    if DrawingMarkup is not None:
        DrawingMarkup.query.filter(DrawingMarkup.linked_rfi_id == rfi_id).update(
            {DrawingMarkup.linked_rfi_id: None}, synchronize_session=False,
        )
    if ChangeOrder is not None:
        ChangeOrder.query.filter(ChangeOrder.linked_rfi_id == rfi_id).update(
            {ChangeOrder.linked_rfi_id: None}, synchronize_session=False,
        )
    if PotentialChangeOrder is not None:
        PotentialChangeOrder.query.filter(PotentialChangeOrder.linked_rfi_id == rfi_id).update(
            {PotentialChangeOrder.linked_rfi_id: None}, synchronize_session=False,
        )
    if ApprovalRequest is not None:
        ApprovalRequest.query.filter(
            ApprovalRequest.entity_type.in_(('rfi', 'RFI', 'rfis')),
            ApprovalRequest.entity_id.in_((sid, rfi_id)),
        ).delete(synchronize_session=False)

    folder = os.path.join(upload_root or 'uploads', 'rfis', sid)
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)

    db.session.delete(rfi)
    return rfi_id


def add_rfi_comment(rfi, body, user_id, user_name, user_role=None):
    """Append a review discussion comment (separate from official workflow responses)."""
    comments = _parse_json(getattr(rfi, 'comments_json', None), [])
    entry = {
        'id': len(comments) + 1,
        'body': (body.get('body') or '').strip(),
        'user_id': user_id,
        'user_name': user_name,
        'user_role': user_role or '',
        'created_at': datetime.utcnow().isoformat(),
    }
    if not entry['body']:
        raise ValueError('Comment body required')
    comments.append(entry)
    rfi.comments_json = json.dumps(comments)
    rfi.updated_at = datetime.utcnow()
    return entry


def clear_rfi_comments(rfi):
    rfi.comments_json = json.dumps([])
    rfi.updated_at = datetime.utcnow()


def delete_rfi_comment(rfi, comment_id):
    comments = _parse_json(getattr(rfi, 'comments_json', None), [])
    cid = int(comment_id)
    filtered = [c for c in comments if int(c.get('id', -1)) != cid]
    if len(filtered) == len(comments):
        raise ValueError('Comment not found')
    rfi.comments_json = json.dumps(filtered)
    rfi.updated_at = datetime.utcnow()
