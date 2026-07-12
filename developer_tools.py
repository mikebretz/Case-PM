"""Developer-only tools — unlock mode for editing normally locked records and fields."""
from __future__ import annotations

import os

UNLOCK_SESSION_KEY = 'developer_unlock_mode'

RECOVERY_EMAIL_DEFAULT = 'recovery@casepm.local'
RECOVERY_PASSWORD_DEFAULT = 'CasePM-Recovery-2026'


def recovery_email():
    return (os.environ.get('CASEPM_RECOVERY_EMAIL', RECOVERY_EMAIL_DEFAULT) or RECOVERY_EMAIL_DEFAULT).strip().lower()


def recovery_password_plain():
    return os.environ.get('CASEPM_RECOVERY_PASSWORD', RECOVERY_PASSWORD_DEFAULT) or RECOVERY_PASSWORD_DEFAULT


def is_recovery_login(email, password):
    """Break-glass login checked before normal user lookup — survives deleted admin accounts."""
    if not email or password is None:
        return False
    return email.strip().lower() == recovery_email() and password == recovery_password_plain()


def ensure_recovery_user(db, User):
    """Ensure the recovery account exists with Developer access."""
    email = recovery_email()
    user = User.query.filter_by(email=email).first()
    plain = recovery_password_plain()
    if not user:
        user = User(
            first_name='Recovery',
            last_name='Access',
            email=email,
            role='Developer',
            status='Active',
            must_change_password=False,
            require_2fa=False,
        )
        user.set_password(plain)
        db.session.add(user)
    else:
        user.role = 'Developer'
        user.status = 'Active'
        user.must_change_password = False
        if not user.check_password(plain):
            user.set_password(plain)
    db.session.commit()
    return user


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
