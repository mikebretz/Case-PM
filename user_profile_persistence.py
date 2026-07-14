"""Extended user profile fields — address, job title, profile photo."""
from __future__ import annotations

import os
import uuid

PROFILE_IMAGE_DIR = os.path.join('uploads', 'profile_images')
MAX_PROFILE_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_PROFILE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def ensure_user_profile_schema(db):
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('user')}
    additions = {
        'job_title': 'VARCHAR(120)',
        'address': 'VARCHAR(300)',
        'profile_image_path': 'VARCHAR(300)',
    }
    for col, typedef in additions.items():
        if col not in existing:
            db.session.execute(text(f'ALTER TABLE user ADD COLUMN {col} {typedef}'))
    db.session.commit()
    os.makedirs(PROFILE_IMAGE_DIR, exist_ok=True)


def profile_image_url(user, *, admin=False):
    path = getattr(user, 'profile_image_path', None)
    if path and os.path.isfile(path):
        uid = getattr(user, 'id', None)
        if admin and uid:
            return f'/api/users/{uid}/profile-image?v={int(os.path.getmtime(path))}'
        return f'/api/users/me/profile-image?v={int(os.path.getmtime(path))}'
    return None


def serialize_profile(user):
    from user_signature_persistence import signature_public_view

    sig = signature_public_view(user)
    cert_meta = {}
    raw = getattr(user, 'certificate_meta_json', None)
    if raw:
        try:
            import json
            cert_meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            cert_meta = {}
    return {
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.full_name,
        'email': user.email,
        'phone': user.phone or '',
        'job_title': getattr(user, 'job_title', None) or '',
        'address': getattr(user, 'address', None) or '',
        'role': user.role,
        'company': user.company or '',
        'company_id': getattr(user, 'company_id', None),
        'require_2fa': bool(getattr(user, 'require_2fa', False)),
        'profile_image_url': profile_image_url(user),
        'signature': sig,
        'signature_legal_name': getattr(user, 'signature_legal_name', None) or '',
        'signature_initials': getattr(user, 'signature_initials', None) or '',
        'certificate_file_name': cert_meta.get('file_name') or '',
    }


def save_profile_image(user, file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError('Profile image file is required')
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_PROFILE_EXTENSIONS:
        raise ValueError('Profile image must be JPG, PNG, WEBP, or GIF')
    data = file_storage.read()
    if len(data) > MAX_PROFILE_IMAGE_BYTES:
        raise ValueError('Profile image is too large (max 2 MB)')
    os.makedirs(PROFILE_IMAGE_DIR, exist_ok=True)
    filename = f'user_{user.id}_{uuid.uuid4().hex[:10]}{ext}'
    path = os.path.join(PROFILE_IMAGE_DIR, filename)
    with open(path, 'wb') as fh:
        fh.write(data)
    old = getattr(user, 'profile_image_path', None)
    user.profile_image_path = path
    if old and old != path and os.path.isfile(old):
        try:
            os.remove(old)
        except OSError:
            pass
    return path
