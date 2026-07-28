"""Per-user email calendar events (meetings, owner meetings, invites)."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

_schema_ready = False


def ensure_email_calendar_schema(db):
    global _schema_ready
    if _schema_ready:
        return
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS user_email_calendar (
                user_id INTEGER PRIMARY KEY,
                events_json TEXT,
                meta_json TEXT,
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


def load_user_calendar(user_id: int, *, UserEmailCalendar=None) -> dict:
    row = UserEmailCalendar.query.get(int(user_id)) if UserEmailCalendar is not None else None
    if not row:
        return {'events': [], 'meta': {}}
    return {
        'events': _parse_json(row.events_json, []),
        'meta': _parse_json(row.meta_json, {}),
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def save_user_calendar(user_id: int, events: list, meta: dict | None = None, *, db, UserEmailCalendar) -> dict:
    ensure_email_calendar_schema(db)
    row = UserEmailCalendar.query.get(int(user_id))
    if not row:
        row = UserEmailCalendar(user_id=int(user_id))
        db.session.add(row)
    row.events_json = json.dumps(events or [])
    if meta is not None:
        row.meta_json = json.dumps(meta or {})
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return load_user_calendar(user_id, UserEmailCalendar=UserEmailCalendar)


def normalize_event(event: dict, *, organizer_email: str = '', organizer_name: str = '') -> dict:
    ev = dict(event or {})
    ev['id'] = str(ev.get('id') or f"evt_{int(datetime.utcnow().timestamp() * 1000)}")
    ev['title'] = (ev.get('title') or 'Untitled meeting').strip()
    ev['start'] = ev.get('start') or ''
    ev['end'] = ev.get('end') or ev['start'] or ''
    ev['allDay'] = bool(ev.get('allDay'))
    ev['location'] = (ev.get('location') or '').strip()
    ev['body'] = ev.get('body') or ''
    ev['attendees'] = [str(x).strip() for x in (ev.get('attendees') or []) if str(x).strip()]
    ev['organizer'] = ev.get('organizer') or organizer_email
    ev['organizerName'] = ev.get('organizerName') or organizer_name
    ev['projectId'] = ev.get('projectId')
    ev['projectName'] = ev.get('projectName') or ''
    ev['eventType'] = ev.get('eventType') or ev.get('type') or 'meeting'
    ev['meetingMinuteId'] = ev.get('meetingMinuteId')
    ev['source'] = ev.get('source') or ''
    ev['readOnly'] = bool(ev.get('readOnly'))
    ev['reminderMinutes'] = int(ev.get('reminderMinutes') or 15)
    ev['timezone'] = ev.get('timezone') or 'local'
    ev['locationMeta'] = ev.get('locationMeta') or {}
    ev['inviteSent'] = bool(ev.get('inviteSent'))
    ev['updatedAt'] = datetime.utcnow().isoformat() + 'Z'
    if not ev.get('createdAt'):
        ev['createdAt'] = ev['updatedAt']
    return ev
