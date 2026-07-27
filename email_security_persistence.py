"""Per-user email security preferences, lists, and feedback."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

_schema_ready = False


def ensure_email_security_schema(db):
    global _schema_ready
    if _schema_ready:
        return
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS user_email_security (
                user_id INTEGER PRIMARY KEY,
                blocked_senders_json TEXT,
                safe_senders_json TEXT,
                false_positives_json TEXT,
                reports_json TEXT,
                preferences_json TEXT,
                updated_at DATETIME
            )
        '''))
        db.session.commit()
        _schema_ready = True
    except Exception:
        db.session.rollback()


def _parse_json(raw, default=None):
    if not raw:
        return default if default is not None else []
    try:
        val = json.loads(raw)
        return val
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else []


def _default_preferences() -> dict:
    return {
        'junkLevel': 'standard',
        'blockRemoteImages': True,
        'showSecurityBanners': True,
        'autoQuarantine': True,
    }


def load_security_state(user_id: int, *, db, UserEmailSecurity=None) -> dict:
    ensure_email_security_schema(db)
    row = None
    if UserEmailSecurity is not None:
        row = UserEmailSecurity.query.get(int(user_id))
    if not row:
        return {
            'blocked_senders': [],
            'safe_senders': [],
            'false_positives': [],
            'reports': [],
            'preferences': _default_preferences(),
        }
    return {
        'blocked_senders': _parse_json(row.blocked_senders_json, []),
        'safe_senders': _parse_json(row.safe_senders_json, []),
        'false_positives': _parse_json(row.false_positives_json, []),
        'reports': _parse_json(row.reports_json, []),
        'preferences': {**_default_preferences(), **_parse_json(row.preferences_json, {})},
    }


def _get_or_create_row(user_id: int, *, db, UserEmailSecurity):
    ensure_email_security_schema(db)
    row = UserEmailSecurity.query.get(int(user_id))
    if not row:
        row = UserEmailSecurity(user_id=int(user_id))
        db.session.add(row)
    return row


def save_security_state(user_id: int, state: dict, *, db, UserEmailSecurity) -> dict:
    row = _get_or_create_row(user_id, db=db, UserEmailSecurity=UserEmailSecurity)
    row.blocked_senders_json = json.dumps(state.get('blocked_senders') or [])
    row.safe_senders_json = json.dumps(state.get('safe_senders') or [])
    row.false_positives_json = json.dumps(state.get('false_positives') or [])
    row.reports_json = json.dumps(state.get('reports') or [])
    row.preferences_json = json.dumps({**_default_preferences(), **(state.get('preferences') or {})})
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return load_security_state(user_id, db=db, UserEmailSecurity=UserEmailSecurity)


def update_preferences(user_id: int, prefs: dict, *, db, UserEmailSecurity) -> dict:
    state = load_security_state(user_id, db=db, UserEmailSecurity=UserEmailSecurity)
    state['preferences'] = {**state['preferences'], **(prefs or {})}
    return save_security_state(user_id, state, db=db, UserEmailSecurity=UserEmailSecurity)


def add_blocked_sender(user_id: int, email: str, *, db, UserEmailSecurity) -> dict:
    email = (email or '').strip().lower()
    if not email:
        raise ValueError('email required')
    state = load_security_state(user_id, db=db, UserEmailSecurity=UserEmailSecurity)
    blocked = [x for x in state['blocked_senders'] if x != email]
    blocked.append(email)
    state['blocked_senders'] = blocked
    safe = [x for x in state['safe_senders'] if x != email]
    state['safe_senders'] = safe
    return save_security_state(user_id, state, db=db, UserEmailSecurity=UserEmailSecurity)


def add_safe_sender(user_id: int, email: str, *, db, UserEmailSecurity) -> dict:
    email = (email or '').strip().lower()
    if not email:
        raise ValueError('email required')
    state = load_security_state(user_id, db=db, UserEmailSecurity=UserEmailSecurity)
    safe = [x for x in state['safe_senders'] if x != email]
    safe.append(email)
    state['safe_senders'] = safe
    blocked = [x for x in state['blocked_senders'] if x != email]
    state['blocked_senders'] = blocked
    return save_security_state(user_id, state, db=db, UserEmailSecurity=UserEmailSecurity)


def record_false_positive(user_id: int, message_id: str, *, db, UserEmailSecurity) -> dict:
    state = load_security_state(user_id, db=db, UserEmailSecurity=UserEmailSecurity)
    fps = [x for x in state['false_positives'] if x != message_id]
    fps.append(str(message_id))
    state['false_positives'] = fps[-500:]
    return save_security_state(user_id, state, db=db, UserEmailSecurity=UserEmailSecurity)


def record_phishing_report(user_id: int, report: dict, *, db, UserEmailSecurity) -> dict:
    state = load_security_state(user_id, db=db, UserEmailSecurity=UserEmailSecurity)
    reports = list(state['reports'])
    reports.append({
        **(report or {}),
        'reported_at': datetime.utcnow().isoformat() + 'Z',
        'reporter_user_id': int(user_id),
    })
    state['reports'] = reports[-200:]
    from_email = (report or {}).get('fromEmail') or (report or {}).get('from_email')
    if from_email:
        email = str(from_email).strip().lower()
        blocked = [x for x in state['blocked_senders'] if x != email]
        blocked.append(email)
        state['blocked_senders'] = blocked
    return save_security_state(user_id, state, db=db, UserEmailSecurity=UserEmailSecurity)
