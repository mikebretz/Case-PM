"""Developer-only tools — unlock mode for editing normally locked records and fields."""
from __future__ import annotations

import json
import os

UNLOCK_SESSION_KEY = 'developer_unlock_mode'
RECOVERY_ACCESS_FILE = os.path.join('instance', 'recovery.access')

RECOVERY_EMAIL_DEFAULT = 'recovery@casepm.local'
RECOVERY_PASSWORD_DEFAULT = 'CasePM-Recovery-2026'


def _read_recovery_access_file():
    """Return recovery.access JSON dict or None."""
    if not os.path.isfile(RECOVERY_ACCESS_FILE):
        return None
    try:
        with open(RECOVERY_ACCESS_FILE, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def recovery_access_configured():
    """True when instance/recovery.access exists with email + password."""
    data = _read_recovery_access_file()
    if not data:
        return False
    email = (data.get('email') or '').strip()
    password = data.get('password')
    return bool(email and password is not None and str(password))


def recovery_email():
    data = _read_recovery_access_file()
    if data and (data.get('email') or '').strip():
        return str(data['email']).strip().lower()
    env = (os.environ.get('CASEPM_RECOVERY_EMAIL', '') or '').strip().lower()
    if env:
        return env
    return RECOVERY_EMAIL_DEFAULT


def recovery_password_plain():
    data = _read_recovery_access_file()
    if data and data.get('password') is not None:
        return str(data['password'])
    env = os.environ.get('CASEPM_RECOVERY_PASSWORD')
    if env:
        return env
    return RECOVERY_PASSWORD_DEFAULT


def recovery_access_token():
    data = _read_recovery_access_file()
    if data and data.get('access_token'):
        return str(data['access_token'])
    return ''


def validate_recovery_token(token):
    stored = recovery_access_token()
    if not stored or token is None:
        return False
    import hmac
    return hmac.compare_digest(str(token).strip(), stored)


def is_recovery_login(email, password):
    """Break-glass login checked before normal user lookup — survives deleted admin accounts."""
    if not email or password is None:
        return False
    # When owner file is configured, only that email/password works (not defaults/env for others).
    if recovery_access_configured():
        return email.strip().lower() == recovery_email() and password == recovery_password_plain()
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
        user.require_2fa = False
        if not user.check_password(plain):
            user.set_password(plain)
    db.session.commit()
    return user


def recovery_status_for_ui(*, include_sensitive=False):
    """Summary for developer console. Email only when include_sensitive=True (recovery operator)."""
    configured = recovery_access_configured()
    email = recovery_email() if include_sensitive else ''
    masked = ''
    if configured and not include_sensitive:
        raw = recovery_email()
        if raw and '@' in raw:
            local, domain = raw.split('@', 1)
            masked = (local[:1] + '***@' + domain) if local else '***'
    return {
        'configured': configured,
        'email': email,
        'email_masked': masked or ('Configured (recovery operator only)' if configured else ''),
        'access_file': RECOVERY_ACCESS_FILE if include_sensitive else '',
        'has_token': bool(recovery_access_token()),
        'source': 'recovery.access' if configured else (
            'environment' if os.environ.get('CASEPM_RECOVERY_EMAIL') or os.environ.get('CASEPM_RECOVERY_PASSWORD')
            else 'default'
        ),
    }


def developer_emails():
    """Explicit developer allowlist from environment only — never includes Admin by default."""
    raw = os.environ.get('CASEPM_DEVELOPER_EMAILS', '') or ''
    return {e.strip().lower() for e in raw.split(',') if e.strip()}


def is_developer(user):
    """Developer Console access — Developer role or explicit CASEPM_DEVELOPER_EMAILS allowlist."""
    if not user:
        return False
    if getattr(user, 'role', None) == 'Developer':
        return True
    email = (getattr(user, 'email', None) or '').lower()
    return email in developer_emails()


def is_recovery_operator(user):
    """Break-glass / recovery credential holder — may view recovery email and secrets metadata."""
    if not user:
        return False
    email = (getattr(user, 'email', None) or '').lower()
    return email == recovery_email()


def can_assign_developer_role(actor):
    """Only existing developers may grant Developer role to another user."""
    return is_developer(actor)


def can_view_recovery_details(user):
    """Recovery email and credential file details — recovery operators only, not regular admins."""
    return is_recovery_operator(user)


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
