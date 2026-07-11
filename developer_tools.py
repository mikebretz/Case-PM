"""Developer-only tools — unlock mode for editing normally locked records and fields."""
from __future__ import annotations

import os

UNLOCK_SESSION_KEY = 'developer_unlock_mode'


def developer_emails():
    raw = os.environ.get('CASEPM_DEVELOPER_EMAILS', 'michael.bretz@casepm.com,admin@casepm.local')
    return {e.strip().lower() for e in raw.split(',') if e.strip()}


def is_developer(user):
    if not user:
        return False
    if getattr(user, 'role', None) == 'Developer':
        return True
    email = (getattr(user, 'email', None) or '').lower()
    return email in developer_emails()


def is_admin_or_developer(user):
    if not user:
        return False
    return getattr(user, 'role', None) == 'Admin' or is_developer(user)


def developer_unlock_active(user=None):
    """True when a developer has turned on global unlock edit mode for this session."""
    try:
        from flask import has_request_context, session
        from flask_login import current_user
    except ImportError:
        return False
    if user is None:
        user = current_user
    if not is_developer(user):
        return False
    if not has_request_context():
        return False
    return bool(session.get(UNLOCK_SESSION_KEY))


def set_developer_unlock_mode(active: bool):
    from flask import session
    session[UNLOCK_SESSION_KEY] = bool(active)
    session.modified = True
    return bool(session.get(UNLOCK_SESSION_KEY))


def unlock_change_order(co):
    if hasattr(co, 'executed_locked'):
        co.executed_locked = False
    return co


def override_project_number(project, new_number, normalize_fn):
    project.number = normalize_fn(new_number)
    return project


def apply_immutable_co_fields(co, data):
    """Apply fields normally blocked after creation/approval (developer unlock only)."""
    if data.get('number') is not None:
        co.number = str(data['number']).strip()
    if data.get('executed_locked') is not None:
        co.executed_locked = bool(data['executed_locked'])
    if data.get('date') is not None:
        from datetime import datetime
        raw = data['date']
        if isinstance(raw, str) and raw:
            try:
                co.date = datetime.strptime(raw[:10], '%Y-%m-%d').date()
            except ValueError:
                pass


def apply_immutable_pco_fields(pco, data):
    if data.get('number') is not None:
        pco.number = str(data['number']).strip()
