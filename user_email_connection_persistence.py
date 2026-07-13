"""Per-user email OAuth connections and mailbox settings storage."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime

from sqlalchemy import text

_schema_ready = False


def ensure_user_email_connection_schema(db):
    global _schema_ready
    if _schema_ready:
        return
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS user_email_connection (
                user_id INTEGER PRIMARY KEY,
                provider VARCHAR(40) NOT NULL DEFAULT 'microsoft',
                email_address VARCHAR(255),
                display_name VARCHAR(255),
                encrypted_tokens TEXT,
                scopes TEXT,
                status VARCHAR(40) DEFAULT 'connected',
                connected_at DATETIME,
                last_sync_at DATETIME,
                last_error VARCHAR(500),
                updated_at DATETIME
            )
        '''))
        db.session.commit()
        _schema_ready = True
    except Exception:
        db.session.rollback()


def _encrypt_blob(raw: str) -> str:
    from security_platform import resolve_secret_key
    key = hashlib.sha256(resolve_secret_key().encode()).digest()
    data = raw.encode('utf-8')
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(out).decode('ascii')


def _decrypt_blob(blob: str) -> str:
    from security_platform import resolve_secret_key
    key = hashlib.sha256(resolve_secret_key().encode()).digest()
    data = base64.urlsafe_b64decode(blob.encode('ascii'))
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return out.decode('utf-8')


def _parse_json(raw, default=None):
    if not raw:
        return default if default is not None else {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, (dict, list)) else (default if default is not None else {})
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else {}


def save_tokens(user_id: int, tokens: dict, *, db, UserEmailConnection) -> None:
    ensure_user_email_connection_schema(db)
    row = UserEmailConnection.query.get(int(user_id))
    if not row:
        row = UserEmailConnection(user_id=int(user_id))
        db.session.add(row)
    row.encrypted_tokens = _encrypt_blob(json.dumps(tokens or {}))
    row.updated_at = datetime.utcnow()


def load_tokens(user_id: int, *, UserEmailConnection) -> dict:
    row = UserEmailConnection.query.get(int(user_id))
    if not row or not row.encrypted_tokens:
        return {}
    try:
        return json.loads(_decrypt_blob(row.encrypted_tokens))
    except Exception:
        return {}


def connection_status(user_id: int, *, UserEmailConnection, User=None) -> dict:
    row = UserEmailConnection.query.get(int(user_id))
    user = User.query.get(int(user_id)) if User is not None else None
    if not row or row.status != 'connected':
        return {
            'connected': False,
            'provider': None,
            'email_address': getattr(user, 'email', None) if user else None,
            'display_name': user.full_name if user else None,
            'connected_at': None,
            'last_sync_at': None,
            'last_error': row.last_error if row else None,
        }
    return {
        'connected': True,
        'provider': row.provider or 'microsoft',
        'email_address': row.email_address or (getattr(user, 'email', None) if user else None),
        'display_name': row.display_name or (user.full_name if user else None),
        'connected_at': row.connected_at.isoformat() if row.connected_at else None,
        'last_sync_at': row.last_sync_at.isoformat() if row.last_sync_at else None,
        'last_error': row.last_error,
        'scopes': _parse_json(row.scopes, []),
    }


def upsert_connection(
    user_id: int,
    *,
    provider: str,
    email_address: str,
    display_name: str,
    tokens: dict,
    scopes: list[str] | None = None,
    db,
    UserEmailConnection,
) -> None:
    ensure_user_email_connection_schema(db)
    uid = int(user_id)
    row = UserEmailConnection.query.get(uid)
    if not row:
        row = UserEmailConnection(user_id=uid)
        db.session.add(row)
    row.provider = (provider or 'microsoft').strip()
    row.email_address = (email_address or '').strip()
    row.display_name = (display_name or '').strip()
    row.encrypted_tokens = _encrypt_blob(json.dumps(tokens or {}))
    row.scopes = json.dumps(scopes or [])
    row.status = 'connected'
    row.connected_at = row.connected_at or datetime.utcnow()
    row.last_error = None
    row.updated_at = datetime.utcnow()
    db.session.commit()


def disconnect_connection(user_id: int, *, db, UserEmailConnection) -> bool:
    row = UserEmailConnection.query.get(int(user_id))
    if not row:
        return False
    row.status = 'disconnected'
    row.encrypted_tokens = None
    row.last_error = None
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return True


def set_connection_error(user_id: int, message: str, *, db, UserEmailConnection) -> None:
    row = UserEmailConnection.query.get(int(user_id))
    if not row:
        return
    row.last_error = (message or '')[:500]
    row.updated_at = datetime.utcnow()
    db.session.commit()


def mark_synced(user_id: int, *, db, UserEmailConnection) -> None:
    row = UserEmailConnection.query.get(int(user_id))
    if not row:
        return
    row.last_sync_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.session.commit()


def load_user_email_settings(user_id: int, *, UserEmailMailbox) -> dict:
    from email_mailbox_persistence import load_user_mailbox
    payload = load_user_mailbox(user_id, UserEmailMailbox=UserEmailMailbox)
    settings = payload.get('meta', {}).get('settings') if isinstance(payload.get('meta'), dict) else {}
    return settings if isinstance(settings, dict) else {}


def save_user_email_settings(user_id: int, settings: dict, *, db, UserEmailMailbox) -> dict:
    from email_mailbox_persistence import load_user_mailbox, save_user_mailbox
    payload = load_user_mailbox(user_id, UserEmailMailbox=UserEmailMailbox)
    meta = dict(payload.get('meta') or {})
    clean = dict(settings or {})
    clean.pop('smtpPassword', None)
    meta['settings'] = clean
    save_user_mailbox(user_id, payload.get('messages') or [], meta, db=db, UserEmailMailbox=UserEmailMailbox)
    return clean


def list_users_email_summary(*, User, UserEmailConnection) -> list[dict]:
    users = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
    out = []
    for user in users:
        conn = connection_status(user.id, UserEmailConnection=UserEmailConnection, User=User)
        out.append({
            'id': user.id,
            'name': user.full_name,
            'email': user.email,
            'role': user.role,
            'connection': conn,
        })
    return out
