"""Live user presence — heartbeats, activity state, and viewport thumbnails for developer watch."""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

ONLINE_WINDOW_SECONDS = 120
THUMBNAIL_DIR = os.path.join('instance', 'presence_thumbs')

_schema_ready = False


def ensure_user_presence_schema(db):
    global _schema_ready
    if _schema_ready:
        return
    db.session.execute(text('''
        CREATE TABLE IF NOT EXISTS user_presence_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key VARCHAR(64) NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            user_name VARCHAR(150),
            user_email VARCHAR(120),
            user_role VARCHAR(50),
            page_path VARCHAR(400),
            page_title VARCHAR(300),
            page_module VARCHAR(80),
            project_id INTEGER,
            project_name VARCHAR(200),
            active_tab VARCHAR(160),
            activity_summary TEXT,
            view_state_json TEXT,
            last_action TEXT,
            last_action_at TEXT,
            scroll_pct INTEGER DEFAULT 0,
            has_thumbnail INTEGER DEFAULT 0,
            last_seen_at TEXT NOT NULL,
            last_seen_epoch INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    '''))
    db.session.execute(text(
        'CREATE INDEX IF NOT EXISTS idx_presence_user_last_seen ON user_presence_sessions (user_id, last_seen_epoch)'
    ))
    try:
        existing = {
            row[1] for row in db.session.execute(text('PRAGMA table_info(user_presence_sessions)')).fetchall()
        }
        if 'last_seen_epoch' not in existing:
            db.session.execute(text(
                'ALTER TABLE user_presence_sessions ADD COLUMN last_seen_epoch INTEGER NOT NULL DEFAULT 0'
            ))
    except Exception:
        db.session.rollback()
    db.session.commit()
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    _schema_ready = True


def _now_iso():
    return datetime.utcnow().isoformat() + 'Z'


def _now_epoch():
    return int(time.time())


def _parse_iso(value):
    if not value:
        return None
    try:
        raw = str(value).replace('Z', '+00:00')
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _is_online(last_seen_epoch=None, last_seen_at=None):
    now = _now_epoch()
    if last_seen_epoch:
        try:
            return (now - int(last_seen_epoch)) <= ONLINE_WINDOW_SECONDS
        except (TypeError, ValueError):
            pass
    dt = _parse_iso(last_seen_at)
    if not dt:
        return False
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    return datetime.utcnow() - dt <= timedelta(seconds=ONLINE_WINDOW_SECONDS)


def _thumb_path(session_key):
    safe = ''.join(c for c in str(session_key) if c.isalnum() or c in '-_')
    return os.path.join(THUMBNAIL_DIR, f'{safe}.jpg')


def save_thumbnail(session_key, b64_data):
    if not session_key or not b64_data:
        return False
    try:
        import base64
        raw = b64_data
        if ',' in raw:
            raw = raw.split(',', 1)[1]
        data = base64.b64decode(raw)
        if len(data) > 800_000:
            return False
        path = _thumb_path(session_key)
        with open(path, 'wb') as fh:
            fh.write(data)
        return True
    except Exception:
        return False


def thumbnail_exists(session_key):
    return os.path.isfile(_thumb_path(session_key))


def upsert_presence_heartbeat(db, user, payload):
    ensure_user_presence_schema(db)
    session_key = (payload.get('session_key') or '').strip()
    if not session_key:
        session_key = uuid.uuid4().hex

    thumb_b64 = payload.get('thumbnail_b64') or payload.get('thumbnail')
    has_thumb = 0
    if thumb_b64 and save_thumbnail(session_key, thumb_b64):
        has_thumb = 1

    view_state = payload.get('view_state')
    if isinstance(view_state, dict):
        view_state_json = json.dumps(view_state)
    else:
        view_state_json = json.dumps(view_state) if view_state else None

    now = _now_iso()
    now_epoch = _now_epoch()
    row = db.session.execute(
        text('SELECT id, has_thumbnail FROM user_presence_sessions WHERE session_key = :sk'),
        {'sk': session_key},
    ).fetchone()

    fields = {
        'sk': session_key,
        'uid': user.id,
        'uname': getattr(user, 'full_name', None) or f'{user.first_name} {user.last_name}'.strip(),
        'uemail': getattr(user, 'email', None) or '',
        'urole': getattr(user, 'role', None) or '',
        'ppath': (payload.get('page_path') or '')[:400],
        'ptitle': (payload.get('page_title') or '')[:300],
        'pmod': (payload.get('page_module') or '')[:80],
        'pid': payload.get('project_id'),
        'pname': (payload.get('project_name') or '')[:200],
        'atab': (payload.get('active_tab') or '')[:160],
        'asum': (payload.get('activity_summary') or '')[:2000],
        'vjson': view_state_json,
        'lact': (payload.get('last_action') or '')[:500],
        'lact_at': payload.get('last_action_at') or now,
        'scroll': int(payload.get('scroll_pct') or 0),
        'seen': now,
        'seen_epoch': now_epoch,
        'created': now,
        'thumb': has_thumb or (row[1] if row else 0),
    }

    if row:
        db.session.execute(text('''
            UPDATE user_presence_sessions SET
                user_id = :uid, user_name = :uname, user_email = :uemail, user_role = :urole,
                page_path = :ppath, page_title = :ptitle, page_module = :pmod,
                project_id = :pid, project_name = :pname, active_tab = :atab,
                activity_summary = :asum, view_state_json = :vjson,
                last_action = :lact, last_action_at = :lact_at, scroll_pct = :scroll,
                has_thumbnail = CASE WHEN :thumb = 1 THEN 1 ELSE has_thumbnail END,
                last_seen_at = :seen, last_seen_epoch = :seen_epoch
            WHERE session_key = :sk
        '''), fields)
    else:
        db.session.execute(text('''
            INSERT INTO user_presence_sessions (
                session_key, user_id, user_name, user_email, user_role,
                page_path, page_title, page_module, project_id, project_name, active_tab,
                activity_summary, view_state_json, last_action, last_action_at, scroll_pct,
                has_thumbnail, last_seen_at, last_seen_epoch, created_at
            ) VALUES (
                :sk, :uid, :uname, :uemail, :urole,
                :ppath, :ptitle, :pmod, :pid, :pname, :atab,
                :asum, :vjson, :lact, :lact_at, :scroll,
                :thumb, :seen, :seen_epoch, :created
            )
        '''), fields)

    db.session.commit()
    prune_stale_sessions(db)
    return session_key


def prune_stale_sessions(db, older_than_hours=24):
    cutoff_epoch = _now_epoch() - (older_than_hours * 3600)
    rows = db.session.execute(
        text('SELECT session_key FROM user_presence_sessions WHERE last_seen_epoch < :cutoff'),
        {'cutoff': cutoff_epoch},
    ).fetchall()
    for row in rows:
        path = _thumb_path(row[0])
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    db.session.execute(
        text('DELETE FROM user_presence_sessions WHERE last_seen_epoch < :cutoff'),
        {'cutoff': cutoff_epoch},
    )
    db.session.commit()


def _serialize_row(row):
    if not row:
        return None
    data = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
    data['online'] = _is_online(data.get('last_seen_epoch'), data.get('last_seen_at'))
    view_state = {}
    raw = data.pop('view_state_json', None)
    if raw:
        try:
            view_state = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            view_state = {}
    data['view_state'] = view_state
    data['has_thumbnail'] = bool(data.get('has_thumbnail'))
    return data


def list_online_presence(db, include_offline_minutes=30):
    ensure_user_presence_schema(db)
    cutoff_epoch = _now_epoch() - int(include_offline_minutes * 60)
    rows = db.session.execute(text('''
        SELECT session_key, user_id, user_name, user_email, user_role,
               page_path, page_title, page_module, project_id, project_name, active_tab,
               activity_summary, last_action, last_action_at, scroll_pct, has_thumbnail,
               last_seen_at, last_seen_epoch
        FROM user_presence_sessions
        WHERE last_seen_epoch >= :cutoff
        ORDER BY last_seen_epoch DESC
    '''), {'cutoff': cutoff_epoch}).fetchall()

    sessions = [_serialize_row(r) for r in rows]
    by_user = {}
    for s in sessions:
        uid = s['user_id']
        if uid not in by_user:
            by_user[uid] = {
                'user_id': uid,
                'user_name': s.get('user_name'),
                'user_email': s.get('user_email'),
                'user_role': s.get('user_role'),
                'online': False,
                'session_count': 0,
                'sessions': [],
            }
        entry = by_user[uid]
        entry['session_count'] += 1
        entry['sessions'].append(s)
        if not entry.get('primary_session_key'):
            entry['primary_session_key'] = s.get('session_key')
            entry['page_title'] = s.get('page_title')
            entry['page_module'] = s.get('page_module')
            entry['project_name'] = s.get('project_name')
            entry['activity_summary'] = s.get('activity_summary')
            entry['last_seen_at'] = s.get('last_seen_at')
        if s.get('online'):
            entry['online'] = True
            entry['primary_session_key'] = s.get('session_key')
            entry['page_title'] = s.get('page_title')
            entry['page_module'] = s.get('page_module')
            entry['project_name'] = s.get('project_name')
            entry['activity_summary'] = s.get('activity_summary')
            entry['last_seen_at'] = s.get('last_seen_at')
    users = sorted(by_user.values(), key=lambda u: (not u['online'], u.get('user_name') or ''))
    return {
        'users': users,
        'sessions': sessions,
        'online_count': sum(1 for s in sessions if s.get('online')),
        'session_count': len(sessions),
    }


def get_presence_session(db, session_key):
    ensure_user_presence_schema(db)
    row = db.session.execute(text('''
        SELECT * FROM user_presence_sessions WHERE session_key = :sk
    '''), {'sk': session_key}).fetchone()
    return _serialize_row(row)
