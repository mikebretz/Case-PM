"""Submittal persistence and workflow — status changes via /workflow only."""
from __future__ import annotations

import json
from datetime import datetime

from financial_security import workflow_reject_authorized

SUBMITTAL_BALL = {
    'Draft': 'Project Manager',
    'Sent to Subcontractor': 'Subcontractor',
    'Returned from Subcontractor': 'Project Manager',
    'Submitted to Architect': 'Architect',
    'Revise & Resubmit': 'Subcontractor',
    'No Exceptions Taken': 'Project Manager',
    'Reviewed as Noted': 'Project Manager',
}


def ensure_submittal_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if 'submittal' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('submittal')}
    additions = {
        'assigned_company_id': 'INTEGER',
        'assigned_company_name': 'VARCHAR(200)',
        'assigned_contact_user_id': 'INTEGER',
        'assigned_contact_name': 'VARCHAR(150)',
        'assigned_contact_email': 'VARCHAR(200)',
        'details_json': 'TEXT',
        'updated_at': 'DATETIME',
    }
    for name, col_type in additions.items():
        if name not in cols:
            db.session.execute(text(f'ALTER TABLE submittal ADD COLUMN {name} {col_type}'))
    db.session.commit()


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def submittal_to_dict(submittal):
    details = _parse_json(getattr(submittal, 'details_json', None), {})
    return {
        'id': submittal.id,
        'project_id': submittal.project_id,
        'number': submittal.number,
        'description': submittal.description,
        'spec_section': submittal.spec_section,
        'status': submittal.status,
        'priority': submittal.priority,
        'submitted_by': submittal.submitted_by,
        'date': submittal.date.isoformat() if submittal.date else None,
        'due_date': submittal.due_date.isoformat() if submittal.due_date else None,
        'ball_in_court': submittal.ball_in_court,
        'review_comments': submittal.review_comments,
        'assigned_company_id': getattr(submittal, 'assigned_company_id', None),
        'assigned_company_name': getattr(submittal, 'assigned_company_name', None),
        'assigned_contact_user_id': getattr(submittal, 'assigned_contact_user_id', None),
        'assigned_contact_name': getattr(submittal, 'assigned_contact_name', None),
        'assigned_contact_email': getattr(submittal, 'assigned_contact_email', None),
        'details': details,
    }


def _user_can_act(user, role):
    from co_persistence import user_can_act_on_ball_in_court
    return user_can_act_on_ball_in_court(user, role)


def apply_submittal_fields(submittal, data, *, is_create=False):
    """Apply editable submittal fields; status only on create (Draft default)."""
    for field in ('description', 'spec_section', 'priority', 'submitted_by', 'review_comments'):
        if data.get(field) is not None:
            setattr(submittal, field, data[field])
    for field in (
        'assigned_company_id', 'assigned_company_name',
        'assigned_contact_user_id', 'assigned_contact_name', 'assigned_contact_email',
    ):
        if field in data and data.get(field) is not None:
            setattr(submittal, field, data[field])
    if data.get('due_date') is not None and data['due_date']:
        try:
            submittal.due_date = datetime.strptime(str(data['due_date'])[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    if data.get('details') is not None:
        submittal.details_json = json.dumps(data.get('details') or {})
    elif data.get('details_json') is not None:
        submittal.details_json = data['details_json'] if isinstance(data['details_json'], str) else json.dumps(data['details_json'])
    submittal.updated_at = datetime.utcnow()
    if is_create:
        submittal.status = 'Draft'
        submittal.ball_in_court = SUBMITTAL_BALL.get('Draft')
    elif data.get('status') is not None or data.get('ball_in_court') is not None:
        pass  # workflow only


def submittal_workflow_action(submittal, action, user, body=None, *, Company=None, db=None):
    """Advance submittal status through the review chain."""
    from document_module_security import assert_submittal_workflow_allowed

    body = body or {}
    action = (action or '').lower()
    assert_submittal_workflow_allowed(user, submittal, action, Company=Company, db=db)
    status = submittal.status or 'Draft'
    ball = submittal.ball_in_court or SUBMITTAL_BALL.get(status, 'Project Manager')

    if action == 'send_to_sub':
        if status != 'Draft':
            raise ValueError('Only draft submittals can be sent to subcontractor')
        if not _user_can_act(user, ball):
            raise ValueError('Cannot send submittal to subcontractor')
        submittal.status = 'Sent to Subcontractor'
        submittal.ball_in_court = SUBMITTAL_BALL['Sent to Subcontractor']
        return submittal.status

    if action == 'return_from_sub':
        if status != 'Sent to Subcontractor':
            raise ValueError('Submittal is not with subcontractor')
        if not _user_can_act(user, ball):
            raise ValueError('Cannot return submittal from subcontractor')
        submittal.status = 'Returned from Subcontractor'
        submittal.ball_in_court = SUBMITTAL_BALL['Returned from Subcontractor']
        return submittal.status

    if action == 'submit_to_architect':
        if status not in ('Returned from Subcontractor', 'Draft'):
            raise ValueError('Submittal must be returned from subcontractor before architect review')
        if not _user_can_act(user, ball):
            raise ValueError('Cannot submit submittal to architect')
        submittal.status = 'Submitted to Architect'
        submittal.ball_in_court = SUBMITTAL_BALL['Submitted to Architect']
        return submittal.status

    if action == 'architect_decision':
        if status != 'Submitted to Architect':
            raise ValueError('Submittal is not with architect')
        if not _user_can_act(user, ball):
            raise ValueError('Cannot record architect decision')
        decision = (body.get('decision') or body.get('status') or '').strip()
        allowed = {
            'No Exceptions Taken', 'Reviewed as Noted', 'Revise & Resubmit', 'Rejected',
        }
        if decision not in allowed:
            raise ValueError(f'decision must be one of: {", ".join(sorted(allowed))}')
        submittal.status = decision
        submittal.ball_in_court = SUBMITTAL_BALL.get(decision)
        if body.get('review_comments'):
            submittal.review_comments = body['review_comments']
        return submittal.status

    if action == 'close':
        if status not in ('No Exceptions Taken', 'Reviewed as Noted'):
            raise ValueError('Only approved submittals can be closed')
        if not _user_can_act(user, ball):
            raise ValueError('Cannot close submittal')
        submittal.status = 'Closed'
        submittal.ball_in_court = None
        return submittal.status

    if action == 'reject':
        workflow_reject_authorized(user, ball, user_can_act_fn=_user_can_act)
        submittal.status = 'Rejected'
        submittal.ball_in_court = None
        return submittal.status

    if action == 'reopen':
        if status not in ('Closed', 'Rejected'):
            raise ValueError('Only closed or rejected submittals can be reopened')
        if not _user_can_act(user, 'Project Manager'):
            raise ValueError('Project Manager role required to reopen submittal')
        submittal.status = 'Draft'
        submittal.ball_in_court = SUBMITTAL_BALL['Draft']
        return submittal.status

    raise ValueError(
        'action must be send_to_sub, return_from_sub, submit_to_architect, '
        'architect_decision, close, reject, or reopen'
    )
