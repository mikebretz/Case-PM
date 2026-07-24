"""Archive permanently deleted email and internal messages until routine backup completes."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join('instance', 'case_pm.db')

_CREATE_SQL = '''
CREATE TABLE IF NOT EXISTS deleted_message_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source VARCHAR(20) NOT NULL,
    user_id INTEGER NOT NULL,
    original_id VARCHAR(120) NOT NULL,
    payload_json TEXT NOT NULL,
    deleted_at DATETIME NOT NULL,
    backed_up_at DATETIME,
    backup_filename VARCHAR(260)
)
'''
_CREATE_INDEX_USER = 'CREATE INDEX IF NOT EXISTS ix_deleted_message_archive_user ON deleted_message_archive (user_id)'
_CREATE_INDEX_PENDING = 'CREATE INDEX IF NOT EXISTS ix_deleted_message_archive_pending ON deleted_message_archive (backed_up_at)'


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _db_path(db_path=None):
    return db_path or DB_PATH


def ensure_deleted_message_archive_schema(conn=None, *, db_path=None):
    """Create archive table if missing."""
    own = conn is None
    if own:
        path = _db_path(db_path)
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        conn = sqlite3.connect(path)
    try:
        conn.execute(_CREATE_SQL)
        conn.execute(_CREATE_INDEX_USER)
        conn.execute(_CREATE_INDEX_PENDING)
        conn.commit()
    finally:
        if own:
            conn.close()


def archive_deleted_message(source, user_id, original_id, payload, *, conn=None, db_path=None, commit=True):
    """Store a deleted message snapshot pending backup."""
    if not source or user_id is None or original_id is None or payload is None:
        return None
    own = conn is None
    if own:
        path = _db_path(db_path)
        ensure_deleted_message_archive_schema(db_path=path)
        conn = sqlite3.connect(path)
    try:
        ensure_deleted_message_archive_schema(conn=conn)
        blob = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        deleted_at = utc_now_iso()
        cur = conn.execute(
            '''
            INSERT INTO deleted_message_archive (source, user_id, original_id, payload_json, deleted_at)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (str(source), int(user_id), str(original_id), blob, deleted_at),
        )
        if commit:
            conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


def archive_internal_message_row(msg):
    """Archive an internal message ORM row before permanent deletion."""
    if msg is None:
        return None
    payload = msg.to_dict() if hasattr(msg, 'to_dict') else {}
    archive_deleted_message_sqlalchemy('internal', msg.user_id, msg.id, payload)
    return True


def ensure_deleted_message_archive_schema_sqlalchemy():
    """Ensure archive table exists using the active SQLAlchemy session."""
    from sqlalchemy import text
    from case_workflow import _workflow_session
    session = _workflow_session()
    session.execute(text(_CREATE_SQL))
    session.execute(text(_CREATE_INDEX_USER))
    session.execute(text(_CREATE_INDEX_PENDING))
    session.commit()


def archive_deleted_message_sqlalchemy(source, user_id, original_id, payload):
    """Archive via SQLAlchemy workflow session (shares transaction with caller)."""
    from sqlalchemy import text
    from case_workflow import _workflow_session
    ensure_deleted_message_archive_schema_sqlalchemy()
    blob = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    deleted_at = utc_now_iso()
    session = _workflow_session()
    session.execute(
        text('''
            INSERT INTO deleted_message_archive (source, user_id, original_id, payload_json, deleted_at)
            VALUES (:source, :user_id, :original_id, :payload_json, :deleted_at)
        '''),
        {
            'source': str(source),
            'user_id': int(user_id),
            'original_id': str(original_id),
            'payload_json': blob,
            'deleted_at': deleted_at,
        },
    )
    return True


def archive_removed_mailbox_messages(user_id, previous_messages, new_messages):
    """Archive email messages removed from trash during mailbox save."""
    prev = previous_messages if isinstance(previous_messages, list) else []
    new_list = new_messages if isinstance(new_messages, list) else []
    new_ids = {str(m.get('id')) for m in new_list if m.get('id') is not None}
    archived = 0
    for msg in prev:
        mid = msg.get('id')
        if mid is None:
            continue
        if str(mid) in new_ids:
            continue
        folder = (msg.get('folder') or '').strip().lower()
        if folder not in ('trash', '_deleted'):
            continue
        archive_deleted_message_sqlalchemy('email', user_id, mid, msg)
        archived += 1
    return archived


def list_pending_archive_items(*, db_path=None):
    """Return deleted messages not yet purged after backup."""
    path = _db_path(db_path)
    if not os.path.isfile(path):
        return []
    ensure_deleted_message_archive_schema(db_path=path)
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            '''
            SELECT id, source, user_id, original_id, payload_json, deleted_at, backed_up_at, backup_filename
            FROM deleted_message_archive
            ORDER BY deleted_at ASC, id ASC
            '''
        ).fetchall()
    finally:
        conn.close()
    items = []
    for row in rows:
        try:
            payload = json.loads(row[4]) if row[4] else {}
        except (TypeError, json.JSONDecodeError):
            payload = {'raw': row[4]}
        items.append({
            'id': row[0],
            'source': row[1],
            'user_id': row[2],
            'original_id': row[3],
            'payload': payload,
            'deleted_at': row[5],
            'backed_up_at': row[6],
            'backup_filename': row[7],
        })
    return items


def export_pending_archive_document(*, db_path=None):
    """Build JSON document for backup zip export."""
    items = list_pending_archive_items(db_path=db_path)
    pending = [i for i in items if not i.get('backed_up_at')]
    return {
        'exported_at': utc_now_iso(),
        'pending_count': len(pending),
        'total_count': len(items),
        'items': items,
    }


def count_pending_archive(*, db_path=None):
    path = _db_path(db_path)
    if not os.path.isfile(path):
        return 0
    ensure_deleted_message_archive_schema(db_path=path)
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            'SELECT COUNT(*) FROM deleted_message_archive WHERE backed_up_at IS NULL'
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def finalize_archive_after_backup(backup_filename, *, db_path=None):
    """
    Mark archived deleted messages as backed up, then purge rows that have been backed up.
    Pending rows remain until the next successful backup captures them in case_pm.db.
    """
    path = _db_path(db_path)
    if not os.path.isfile(path):
        return {'marked': 0, 'purged': 0}
    ensure_deleted_message_archive_schema(db_path=path)
    backed_at = utc_now_iso()
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            '''
            UPDATE deleted_message_archive
            SET backed_up_at = ?, backup_filename = ?
            WHERE backed_up_at IS NULL
            ''',
            (backed_at, (backup_filename or '').strip() or None),
        )
        marked = cur.rowcount or 0
        cur = conn.execute('DELETE FROM deleted_message_archive WHERE backed_up_at IS NOT NULL')
        purged = cur.rowcount or 0
        conn.commit()
        return {'marked': marked, 'purged': purged, 'backup_filename': backup_filename}
    finally:
        conn.close()
