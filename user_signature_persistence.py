"""User-owned electronic signatures — viewable by all, editable only by the user."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime

SIGNATURE_UPLOAD_DIR = os.path.join('uploads', 'signatures')
MAX_SIGNATURE_BYTES = 512 * 1024  # 512 KB PNG


def ensure_user_signature_schema(db):
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('user')}
    additions = {
        'signature_path': 'VARCHAR(300)',
        'signature_hash': 'VARCHAR(64)',
        'signature_legal_name': 'VARCHAR(150)',
        'signature_initials': 'VARCHAR(20)',
        'signature_set_at': 'DATETIME',
        'signature_audit_json': 'TEXT',
        'certificate_meta_json': 'TEXT',
    }
    for col, typedef in additions.items():
        if col not in existing:
            db.session.execute(text(f'ALTER TABLE user ADD COLUMN {col} {typedef}'))
    db.session.commit()
    os.makedirs(SIGNATURE_UPLOAD_DIR, exist_ok=True)


def _parse_json(raw, default=None):
    if default is None:
        default = []
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_png_data_url(data_url: str) -> bytes:
    if not data_url:
        raise ValueError('Signature image is required')
    m = re.match(r'^data:image/(png|jpeg|jpg);base64,(.+)$', data_url.strip(), re.I | re.S)
    if not m:
        raise ValueError('Signature must be a PNG or JPEG data URL')
    raw = base64.b64decode(m.group(2))
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise ValueError('Signature image is too large (max 512 KB)')
    return raw


def signature_public_view(user):
    """Safe signature metadata for any authenticated viewer."""
    if not user or not getattr(user, 'signature_hash', None):
        return {
            'has_signature': False,
            'user_id': getattr(user, 'id', None),
            'legal_name': None,
            'initials': None,
            'set_at': None,
            'hash': None,
            'image_url': None,
        }
    uid = user.id
    return {
        'has_signature': True,
        'user_id': uid,
        'legal_name': user.signature_legal_name or user.full_name,
        'initials': user.signature_initials or '',
        'set_at': user.signature_set_at.isoformat() if user.signature_set_at else None,
        'hash': user.signature_hash,
        'image_url': f'/api/users/{uid}/signature/image' if user.signature_path else None,
    }


def append_signature_audit(user, event_type, details=None):
    audit = _parse_json(getattr(user, 'signature_audit_json', None), [])
    audit.insert(0, {
        'at': datetime.utcnow().isoformat() + 'Z',
        'event': event_type,
        'details': details or {},
    })
    user.signature_audit_json = json.dumps(audit[:200])


def save_user_signature(user, data_url, legal_name=None, initials=None):
    """Persist PNG signature — caller must verify user is saving their own profile."""
    png_bytes = _decode_png_data_url(data_url)
    sig_hash = _sha256_bytes(png_bytes)
    os.makedirs(SIGNATURE_UPLOAD_DIR, exist_ok=True)
    path = os.path.join(SIGNATURE_UPLOAD_DIR, f'user_{user.id}.png')
    with open(path, 'wb') as fh:
        fh.write(png_bytes)
    user.signature_path = path
    user.signature_hash = sig_hash
    user.signature_legal_name = (legal_name or user.full_name or '').strip() or user.full_name
    user.signature_initials = (initials or '').strip()[:20]
    user.signature_set_at = datetime.utcnow()
    append_signature_audit(user, 'signature_saved', {'hash': sig_hash})


def verify_user_signature_attestation(user, provided_hash):
    """Confirm client is signing with the user's current on-file signature."""
    if not user or not user.signature_hash:
        raise ValueError('You must set up your electronic signature in User Management before signing documents.')
    if not provided_hash or provided_hash.lower() != (user.signature_hash or '').lower():
        raise ValueError('Signature verification failed. Your on-file signature may have changed — save it again in your profile.')
    return True


def document_fingerprint(parts):
    """Tamper-evident hash for a document at signing time."""
    payload = '|'.join(str(p) for p in parts)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def append_co_approval_signature(co, user, role, comments='', action='approve'):
    sigs = _parse_json(getattr(co, 'approval_signatures_json', None), [])
    fp = document_fingerprint([
        'ChangeOrder', co.id, co.number, co.amount, co.status, role, action,
    ])
    record = {
        'signed_at': datetime.utcnow().isoformat() + 'Z',
        'signed_by_id': user.id,
        'signed_by_name': user.signature_legal_name or user.full_name,
        'role': role,
        'action': action,
        'signature_hash': user.signature_hash,
        'document_fingerprint': fp,
        'comments': (comments or '').strip(),
        'method': 'casepm_esign',
        'locked': role == 'Owner' and action == 'approve',
    }
    sigs.append(record)
    co.approval_signatures_json = json.dumps(sigs)
    if role == 'Owner' and action == 'approve':
        co.executed_locked = True
    return record


def co_has_owner_signature(co):
    sigs = _parse_json(getattr(co, 'approval_signatures_json', None), [])
    return any(s.get('role') == 'Owner' and s.get('action') == 'approve' for s in sigs)


def append_commitment_signature(commitment, user, method='internal'):
    sigs = _parse_json(getattr(commitment, 'certified_signatures_json', None), [])
    fp = document_fingerprint([
        'Commitment', commitment.id, commitment.number, commitment.current_amount, commitment.status,
    ])
    sigs.append({
        'signed_at': datetime.utcnow().isoformat() + 'Z',
        'signed_by_id': user.id,
        'signed_by_name': user.signature_legal_name or user.full_name,
        'method': method,
        'signature_hash': user.signature_hash,
        'document_fingerprint': fp,
    })
    commitment.certified_signatures_json = json.dumps(sigs)
    commitment.signature_status = 'fully_executed' if commitment.status == 'Approved' else 'partially_signed'
    commitment.executed_date = datetime.utcnow().date()
    commitment.signature_method = method if method != 'internal' else (commitment.signature_method or 'internal')
