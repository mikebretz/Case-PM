"""TOTP two-factor authentication (Google Authenticator compatible)."""
from __future__ import annotations

import io
import base64

ISSUER = 'Case PM'


def ensure_totp_schema(db):
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('user')}
    if 'totp_secret' not in cols:
        db.session.execute(text('ALTER TABLE user ADD COLUMN totp_secret VARCHAR(64)'))
    if 'totp_enabled' not in cols:
        db.session.execute(text('ALTER TABLE user ADD COLUMN totp_enabled BOOLEAN DEFAULT 0'))
    db.session.commit()


def user_needs_2fa(user) -> bool:
    if not user:
        return False
    if getattr(user, 'totp_enabled', False) and getattr(user, 'totp_secret', None):
        return True
    if getattr(user, 'require_2fa', False):
        return True
    try:
        from program_settings_persistence import load_security_settings
        sec = load_security_settings()
        if sec.get('require_2fa_for_admins') and getattr(user, 'role', None) == 'Admin':
            return True
    except Exception:
        pass
    return False


def user_has_totp_configured(user) -> bool:
    return bool(getattr(user, 'totp_enabled', False) and getattr(user, 'totp_secret', None))


def generate_secret() -> str:
    import pyotp
    return pyotp.random_base32()


def provisioning_uri(user, secret: str) -> str:
    import pyotp
    name = getattr(user, 'email', None) or getattr(user, 'full_name', 'user')
    return pyotp.totp.TOTP(secret).provisioning_uri(name=name, issuer_name=ISSUER)


def qr_code_data_url(uri: str) -> str:
    try:
        import qrcode
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return f'data:image/png;base64,{b64}'
    except Exception:
        return ''


def verify_code(user, code: str, *, secret: str | None = None) -> bool:
    import pyotp
    sec = secret or getattr(user, 'totp_secret', None)
    if not sec or not code:
        return False
    try:
        totp = pyotp.TOTP(sec)
        return totp.verify(str(code).strip().replace(' ', ''), valid_window=1)
    except Exception:
        return False


def enable_totp(user, secret: str, code: str, db) -> tuple[bool, str]:
    if not verify_code(None, code, secret=secret):
        return False, 'Invalid verification code. Check your authenticator app and try again.'
    user.totp_secret = secret
    user.totp_enabled = True
    user.require_2fa = True
    db.session.add(user)
    return True, ''


def disable_totp(user, code: str, db) -> tuple[bool, str]:
    if not verify_code(user, code):
        return False, 'Invalid code — two-factor was not disabled.'
    user.totp_secret = None
    user.totp_enabled = False
    db.session.add(user)
    return True, ''
