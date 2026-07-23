"""Submittal persistence and workflow — status changes via /workflow only."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

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
        'comments_json': 'TEXT',
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
        'comments': _parse_json(getattr(submittal, 'comments_json', None), []),
        'assigned_company_id': getattr(submittal, 'assigned_company_id', None),
        'assigned_company_name': getattr(submittal, 'assigned_company_name', None),
        'assigned_contact_user_id': getattr(submittal, 'assigned_contact_user_id', None),
        'assigned_contact_name': getattr(submittal, 'assigned_contact_name', None),
        'assigned_contact_email': getattr(submittal, 'assigned_contact_email', None),
        'details': details,
    }


def submittal_to_ui_item(submittal):
    """Map a Submittal model row to the submittal log UI shape (camelCase)."""
    d = submittal_to_dict(submittal)
    details = d.get('details') or {}
    sid = d.get('id')
    return {
        'id': sid,
        'serverId': sid,
        'number': d.get('number') or '',
        'subject': d.get('description') or '',
        'description': d.get('description') or '',
        'specSection': d.get('spec_section') or '',
        'status': d.get('status') or 'Draft',
        'priority': d.get('priority') or 'Medium',
        'assignedCompanyId': d.get('assigned_company_id'),
        'assignedCompanyName': d.get('assigned_company_name') or '',
        'assignedContactId': d.get('assigned_contact_user_id'),
        'assignedContactName': d.get('assigned_contact_name') or '',
        'assignedContactEmail': d.get('assigned_contact_email') or '',
        'requiredBy': (d.get('due_date') or '')[:10] if d.get('due_date') else '',
        'dateReceived': (d.get('date') or '')[:10] if d.get('date') else '',
        'sectionName': details.get('sectionName') or '',
        'paragraph': details.get('paragraph') or '',
        'rev': details.get('rev') or '0',
        'type': details.get('type') or '',
        'receivedFrom': details.get('receivedFrom') or d.get('assigned_company_name') or '',
        'referredTo': details.get('referredTo') or '',
        'costImpactChoice': details.get('costImpactChoice') or '',
        'scheduleImpactChoice': details.get('scheduleImpactChoice') or '',
        'costImpact': details.get('costImpact') or '',
        'scheduleDays': details.get('scheduleDays') or '',
        'impactNotes': details.get('impactNotes') or '',
        'history': details.get('history') or [],
        'comments': d.get('comments') or [],
        'reviewComments': (d.get('review_comments') or '').strip(),
        'reviewSubmissions': details.get('reviewSubmissions') or details.get('review_submissions') or [],
        'ballInCourt': d.get('ball_in_court') or '',
        'notifiedDate': details.get('notifiedDate') or '',
    }


def add_submittal_comment(submittal, body, user_id, user_name, user_role=None):
    """Append a review comment to the submittal thread."""
    comments = _parse_json(getattr(submittal, 'comments_json', None), [])
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
    submittal.comments_json = json.dumps(comments)
    submittal.updated_at = datetime.utcnow()
    return entry


def add_submittal_review_submission(submittal, body, user_id, user_name, user_role=None, party=None):
    """Append a formal review submission shown on the printable review sheet."""
    details = _parse_json(getattr(submittal, 'details_json', None), {})
    submissions = list(details.get('reviewSubmissions') or details.get('review_submissions') or [])
    entry = {
        'id': len(submissions) + 1,
        'body': (body.get('body') or '').strip(),
        'party': (party or body.get('party') or user_role or 'Reviewer').strip(),
        'decision': (body.get('decision') or '').strip() or None,
        'user_id': user_id,
        'user_name': user_name,
        'user_role': user_role or '',
        'created_at': datetime.utcnow().isoformat(),
    }
    if not entry['body']:
        raise ValueError('Review submission text is required')
    submissions.append(entry)
    details['reviewSubmissions'] = submissions
    submittal.details_json = json.dumps(details)
    submittal.updated_at = datetime.utcnow()
    return entry, submissions


def _record_contractor_review_stamp(submittal, user):
    """Persist PM/contractor review stamp metadata for the submittal cover page."""
    details = _parse_json(getattr(submittal, 'details_json', None), {})
    reviewed_name = (
        (getattr(user, 'signature_legal_name', None) or '').strip()
        or getattr(user, 'full_name', None)
        or 'User'
    )
    details['contractorReviewStamp'] = {
        'reviewed_by_id': getattr(user, 'id', None),
        'reviewed_by_name': reviewed_name,
        'reviewed_at': datetime.utcnow().isoformat(),
        'signature_hash': getattr(user, 'signature_hash', None),
        'signature_path': getattr(user, 'signature_path', None),
        'has_signature_image': bool(getattr(user, 'signature_path', None)),
    }
    submittal.details_json = json.dumps(details)


def clear_submittal_comments(submittal):
    submittal.comments_json = json.dumps([])
    submittal.updated_at = datetime.utcnow()


def delete_submittal_comment(submittal, comment_id):
    comments = _parse_json(getattr(submittal, 'comments_json', None), [])
    cid = int(comment_id)
    filtered = [c for c in comments if int(c.get('id', -1)) != cid]
    if len(filtered) == len(comments):
        raise ValueError('Comment not found')
    submittal.comments_json = json.dumps(filtered)
    submittal.updated_at = datetime.utcnow()


def append_submittal_digital_signature(submittal, user, body):
    """Record a profile-linked electronic signature on the submittal audit trail."""
    from user_signature_persistence import verify_user_signature_attestation

    if not body.get('signature_attestation'):
        raise ValueError('Electronic signature attestation is required')
    verify_user_signature_attestation(user, (body.get('signature_hash') or '').strip())
    details = _parse_json(getattr(submittal, 'details_json', None), {})
    history = list(details.get('history') or [])
    signed_name = (body.get('signature_legal_name') or '').strip() or getattr(user, 'full_name', None) or 'User'
    entry = {
        'date': datetime.utcnow().isoformat(),
        'action': 'Digitally Signed',
        'user': signed_name,
        'user_id': getattr(user, 'id', None),
        'signature_hash': getattr(user, 'signature_hash', None),
    }
    history.append(entry)
    details['history'] = history
    signatures = list(details.get('digital_signatures') or [])
    signatures.append({
        'signed_at': entry['date'],
        'signed_by_name': signed_name,
        'signed_by_id': entry['user_id'],
        'signature_hash': entry['signature_hash'],
    })
    details['digital_signatures'] = signatures
    submittal.details_json = json.dumps(details)
    submittal.updated_at = datetime.utcnow()
    return entry, history


def _bump_submittal_revision(submittal):
    details = _parse_json(getattr(submittal, 'details_json', None), {})
    try:
        rev = int(str(details.get('rev') or '0').strip() or '0')
    except (TypeError, ValueError):
        rev = 0
    details['rev'] = str(rev + 1)
    submittal.details_json = json.dumps(details)
    return details['rev']


SUB_ASSIGNEE_DETAIL_KEYS = frozenset({
    'impactNotes', 'costImpactChoice', 'scheduleImpactChoice', 'costImpact', 'scheduleDays',
})


def _set_submittal_notified_date(submittal, notified_date=None):
    """Record when the sub was notified and set required-by to two weeks later."""
    details = _parse_json(getattr(submittal, 'details_json', None), {})
    if details.get('notifiedDate'):
        return
    nd = notified_date or datetime.utcnow().date()
    if isinstance(nd, str):
        try:
            nd = datetime.strptime(nd[:10], '%Y-%m-%d').date()
        except ValueError:
            nd = datetime.utcnow().date()
    details['notifiedDate'] = nd.isoformat()
    submittal.details_json = json.dumps(details)
    submittal.due_date = nd + timedelta(days=14)


def apply_submittal_sub_sync_fields(submittal, data):
    """Apply only fields a subcontractor assignee may update via sync."""
    details_in = data.get('details') or {}
    if not isinstance(details_in, dict):
        details_in = {}
    existing = _parse_json(getattr(submittal, 'details_json', None), {})
    for key in SUB_ASSIGNEE_DETAIL_KEYS:
        if key in details_in:
            existing[key] = details_in[key]
    submittal.details_json = json.dumps(existing)
    submittal.updated_at = datetime.utcnow()


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
            val = data[field]
            if field.endswith('_id') and val not in ('', None):
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    val = None
            setattr(submittal, field, val)
    if data.get('due_date') is not None and data['due_date']:
        try:
            submittal.due_date = datetime.strptime(str(data['due_date'])[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    if data.get('details') is not None:
        submittal.details_json = json.dumps(data.get('details') or {})
    elif data.get('details_json') is not None:
        submittal.details_json = data['details_json'] if isinstance(data['details_json'], str) else json.dumps(data['details_json'])
    assigned_cid = data.get('assigned_company_id')
    assigned_uid = data.get('assigned_contact_user_id')
    if assigned_cid not in (None, '', 0) or assigned_uid not in (None, '', 0):
        _set_submittal_notified_date(submittal)
    submittal.updated_at = datetime.utcnow()
    if is_create:
        submittal.status = 'Draft'
        submittal.ball_in_court = SUBMITTAL_BALL.get('Draft')
    elif data.get('status') is not None or data.get('ball_in_court') is not None:
        pass  # workflow only


def submittal_workflow_action(submittal, action, user, body=None, *, Company=None, db=None):
    """Advance submittal status through the review chain."""
    from document_module_security import assert_submittal_workflow_allowed, is_sub_portal_user, is_staff_portal_user, submittal_assigned_to_user

    body = body or {}
    action = (action or '').lower()
    assert_submittal_workflow_allowed(user, submittal, action, Company=Company, db=db)
    status = submittal.status or 'Draft'
    ball = submittal.ball_in_court or SUBMITTAL_BALL.get(status, 'Project Manager')

    def _sub_assignee_can_act():
        return (
            is_sub_portal_user(user)
            and not is_staff_portal_user(user)
            and submittal_assigned_to_user(submittal, user, Company=Company, db=db)
        )

    if action == 'send_to_sub':
        if status != 'Draft':
            raise ValueError('Only draft submittals can be sent to subcontractor')
        if not _user_can_act(user, ball):
            raise ValueError('Cannot send submittal to subcontractor')
        _set_submittal_notified_date(submittal)
        submittal.status = 'Sent to Subcontractor'
        submittal.ball_in_court = SUBMITTAL_BALL['Sent to Subcontractor']
        return submittal.status

    if action == 'return_from_sub':
        if status not in ('Sent to Subcontractor', 'Revise & Resubmit', 'Draft'):
            raise ValueError('Submittal is not with subcontractor')
        if not _sub_assignee_can_act() and not _user_can_act(user, ball):
            raise ValueError('Cannot return submittal from subcontractor')
        _set_submittal_notified_date(submittal)
        _bump_submittal_revision(submittal)
        submittal.date = datetime.utcnow().date()
        submittal.status = 'Returned from Subcontractor'
        submittal.ball_in_court = SUBMITTAL_BALL['Returned from Subcontractor']
        return submittal.status

    if action == 'submit_to_architect':
        if status not in ('Returned from Subcontractor', 'Draft'):
            raise ValueError('Submittal must be returned from subcontractor before architect review')
        if not _user_can_act(user, ball):
            raise ValueError('Cannot submit submittal to architect')
        _record_contractor_review_stamp(submittal, user)
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
        review_body = (body.get('review_comments') or body.get('body') or '').strip()
        if review_body or decision:
            actor_name = (body.get('signature_legal_name') or getattr(user, 'full_name', None) or 'User')
            add_submittal_review_submission(
                submittal,
                {
                    'body': review_body or f'Decision: {decision}',
                    'decision': decision,
                    'party': 'Architect / Engineer',
                },
                getattr(user, 'id', None),
                actor_name,
                user_role=getattr(user, 'role', None),
                party='Architect / Engineer',
            )
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
