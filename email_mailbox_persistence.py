"""Per-user email mailbox storage and delegated mailbox access."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

_schema_ready = False


def ensure_email_mailbox_schema(db):
    global _schema_ready
    if _schema_ready:
        return
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS user_email_mailbox (
                user_id INTEGER PRIMARY KEY,
                messages_json TEXT,
                meta_json TEXT,
                updated_at DATETIME
            )
        '''))
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS email_mailbox_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                grantee_user_id INTEGER NOT NULL,
                can_send INTEGER DEFAULT 0,
                granted_by_id INTEGER,
                created_at DATETIME,
                revoked_at DATETIME,
                notes VARCHAR(300)
            )
        '''))
        db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_email_mailbox_access_owner ON email_mailbox_access (owner_user_id)'
        ))
        db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_email_mailbox_access_grantee ON email_mailbox_access (grantee_user_id)'
        ))
        db.session.commit()
        _schema_ready = True
    except Exception:
        db.session.rollback()


def _is_privileged(actor) -> bool:
    try:
        from developer_tools import is_admin_or_developer
        return is_admin_or_developer(actor)
    except Exception:
        return getattr(actor, 'role', None) in ('Admin', 'Developer')


def _active_access_query(EmailMailboxAccess, owner_user_id, grantee_user_id):
    return EmailMailboxAccess.query.filter_by(
        owner_user_id=int(owner_user_id),
        grantee_user_id=int(grantee_user_id),
        revoked_at=None,
    )


def can_access_mailbox(actor, owner_user_id, *, EmailMailboxAccess) -> bool:
    if not actor or not owner_user_id:
        return False
    owner_user_id = int(owner_user_id)
    if owner_user_id == int(actor.id):
        return True
    if _is_privileged(actor):
        return True
    return _active_access_query(EmailMailboxAccess, owner_user_id, actor.id).first() is not None


def can_send_as_mailbox(actor, owner_user_id, *, EmailMailboxAccess) -> bool:
    if not actor or not owner_user_id:
        return False
    owner_user_id = int(owner_user_id)
    if owner_user_id == int(actor.id):
        return True
    if _is_privileged(actor):
        return True
    row = _active_access_query(EmailMailboxAccess, owner_user_id, actor.id).first()
    return bool(row and row.can_send)


def resolve_mailbox_user_id(actor, requested_user_id, *, User, EmailMailboxAccess):
    if not actor:
        raise PermissionError('Not authenticated')
    if not requested_user_id:
        return int(actor.id)
    target = int(requested_user_id)
    if not can_access_mailbox(actor, target, EmailMailboxAccess=EmailMailboxAccess):
        raise PermissionError('Mailbox access denied')
    if User is not None:
        user = User.query.get(target)
        if not user or (getattr(user, 'status', None) or 'Active') != 'Active':
            raise PermissionError('User not found')
    return target


def serialize_mailbox_owner(user, *, delegated=False, can_send=False, access_id=None):
    return {
        'id': user.id,
        'name': user.full_name,
        'email': user.email,
        'delegated': bool(delegated),
        'can_send': bool(can_send),
        'access_id': access_id,
    }


def list_mailbox_owners_for_actor(actor, *, User, EmailMailboxAccess):
    owners = []
    seen = set()
    me = User.query.get(actor.id)
    if me:
        owners.append(serialize_mailbox_owner(me))
        seen.add(me.id)

    if _is_privileged(actor):
        rows = User.query.filter_by(status='Active').order_by(User.last_name, User.first_name).all()
        for u in rows:
            if u.id in seen:
                continue
            owners.append(serialize_mailbox_owner(u))
            seen.add(u.id)
    else:
        grants = EmailMailboxAccess.query.filter_by(grantee_user_id=actor.id, revoked_at=None).all()
        for g in grants:
            if g.owner_user_id in seen:
                continue
            u = User.query.get(g.owner_user_id)
            if not u or (getattr(u, 'status', None) or 'Active') != 'Active':
                continue
            owners.append(serialize_mailbox_owner(
                u, delegated=True, can_send=bool(g.can_send), access_id=g.id,
            ))
            seen.add(u.id)
    return owners


def load_user_mailbox(user_id, *, UserEmailMailbox):
    row = UserEmailMailbox.query.get(int(user_id))
    if not row:
        return {'messages': [], 'meta': {}}
    messages = []
    meta = {}
    try:
        messages = json.loads(row.messages_json) if row.messages_json else []
    except (TypeError, json.JSONDecodeError):
        messages = []
    try:
        meta = json.loads(row.meta_json) if row.meta_json else {}
    except (TypeError, json.JSONDecodeError):
        meta = {}
    if not isinstance(messages, list):
        messages = []
    if not isinstance(meta, dict):
        meta = {}
    return {'messages': messages, 'meta': meta, 'updated_at': row.updated_at.isoformat() if row.updated_at else None}


def save_user_mailbox(user_id, messages, meta, *, db, UserEmailMailbox):
    ensure_email_mailbox_schema(db)
    uid = int(user_id)
    row = UserEmailMailbox.query.get(uid)
    if not row:
        row = UserEmailMailbox(user_id=uid)
        db.session.add(row)
    row.messages_json = json.dumps(messages or [])
    row.meta_json = json.dumps(meta or {})
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return load_user_mailbox(uid, UserEmailMailbox=UserEmailMailbox)


def list_mailbox_access(owner_user_id, *, EmailMailboxAccess, User):
    rows = EmailMailboxAccess.query.filter_by(owner_user_id=int(owner_user_id), revoked_at=None).order_by(
        EmailMailboxAccess.created_at.desc()
    ).all()
    out = []
    for row in rows:
        grantee = User.query.get(row.grantee_user_id)
        granter = User.query.get(row.granted_by_id) if row.granted_by_id else None
        out.append({
            'id': row.id,
            'owner_user_id': row.owner_user_id,
            'grantee_user_id': row.grantee_user_id,
            'grantee_name': grantee.full_name if grantee else '',
            'grantee_email': grantee.email if grantee else '',
            'can_send': bool(row.can_send),
            'granted_by_name': granter.full_name if granter else '',
            'created_at': row.created_at.isoformat() if row.created_at else '',
            'notes': row.notes or '',
        })
    return out


def grant_mailbox_access(owner_user_id, grantee_user_id, *, can_send=False, granted_by_id=None,
                         notes='', db=None, EmailMailboxAccess=None, User=None):
    owner_user_id = int(owner_user_id)
    grantee_user_id = int(grantee_user_id)
    if owner_user_id == grantee_user_id:
        raise ValueError('Cannot grant mailbox access to the same user.')
    owner = User.query.get(owner_user_id)
    grantee = User.query.get(grantee_user_id)
    if not owner or not grantee:
        raise ValueError('User not found.')
    existing = _active_access_query(EmailMailboxAccess, owner_user_id, grantee_user_id).first()
    if existing:
        existing.can_send = bool(can_send)
        existing.notes = (notes or '').strip() or existing.notes
        db.session.commit()
        return existing
    row = EmailMailboxAccess(
        owner_user_id=owner_user_id,
        grantee_user_id=grantee_user_id,
        can_send=bool(can_send),
        granted_by_id=granted_by_id,
        notes=(notes or '').strip() or None,
    )
    db.session.add(row)
    db.session.commit()
    return row


def revoke_mailbox_access(access_id, *, db, EmailMailboxAccess):
    row = EmailMailboxAccess.query.get(int(access_id))
    if not row or row.revoked_at:
        return False
    row.revoked_at = datetime.utcnow()
    db.session.commit()
    return True


def transfer_mailbox(from_user_id, to_user_id, *, include_internal=True, clear_source=False,
                     db=None, UserEmailMailbox=None, InternalMessage=None):
    from_user_id = int(from_user_id)
    to_user_id = int(to_user_id)
    if from_user_id == to_user_id:
        raise ValueError('Source and destination must differ.')

    src = load_user_mailbox(from_user_id, UserEmailMailbox=UserEmailMailbox)
    dst = load_user_mailbox(to_user_id, UserEmailMailbox=UserEmailMailbox)
    merged_messages = (dst.get('messages') or []) + (src.get('messages') or [])
    save_user_mailbox(to_user_id, merged_messages, dst.get('meta') or {}, db=db, UserEmailMailbox=UserEmailMailbox)

    if clear_source:
        save_user_mailbox(from_user_id, [], src.get('meta') or {}, db=db, UserEmailMailbox=UserEmailMailbox)
    else:
        save_user_mailbox(from_user_id, src.get('messages') or [], src.get('meta') or {},
                          db=db, UserEmailMailbox=UserEmailMailbox)

    moved_internal = 0
    if include_internal and InternalMessage is not None:
        moved_internal = InternalMessage.query.filter_by(user_id=from_user_id).update({'user_id': to_user_id})
        db.session.commit()
    return {'messages_merged': len(src.get('messages') or []), 'internal_moved': moved_internal}
