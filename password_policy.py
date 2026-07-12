"""Password strength validation — enforced when require_strong_passwords is enabled."""
from __future__ import annotations

import re

MIN_LENGTH = 12
MIN_TEMP_LENGTH = 4
COMMON_PASSWORDS = frozenset({
    'password', 'password123', 'admin123', 'temppass123!', 'casepm2026',
    'welcome123', 'changeme', 'letmein', 'construction',
})


def policy_enabled() -> bool:
    try:
        from program_settings_persistence import load_security_settings
        return bool(load_security_settings().get('require_strong_passwords', True))
    except Exception:
        return True


def validate_password(password: str, *, email: str = '', names: tuple[str, ...] = ()) -> tuple[bool, str]:
    pwd = password or ''
    if len(pwd) < 8:
        return False, 'Password must be at least 8 characters.'
    if not policy_enabled():
        return True, ''

    if len(pwd) < MIN_LENGTH:
        return False, f'Password must be at least {MIN_LENGTH} characters.'
    if not re.search(r'[A-Z]', pwd):
        return False, 'Password must include an uppercase letter.'
    if not re.search(r'[a-z]', pwd):
        return False, 'Password must include a lowercase letter.'
    if not re.search(r'\d', pwd):
        return False, 'Password must include a number.'
    if not re.search(r'[^A-Za-z0-9]', pwd):
        return False, 'Password must include a special character.'
    lower = pwd.lower()
    if lower in COMMON_PASSWORDS:
        return False, 'That password is too common. Choose a stronger password.'
    if email and email.split('@')[0].lower() in lower:
        return False, 'Password must not contain your email address.'
    for name in names:
        n = (name or '').strip().lower()
        if len(n) >= 3 and n in lower:
            return False, 'Password must not contain your name.'
    return True, ''


def validate_temporary_password(password: str) -> tuple[bool, str]:
    """Admin-set initial / reset passwords — simple temporary values allowed."""
    pwd = (password or '').strip()
    if len(pwd) < MIN_TEMP_LENGTH:
        return False, f'Initial password must be at least {MIN_TEMP_LENGTH} characters.'
    if len(pwd) > 128:
        return False, 'Password is too long.'
    return True, ''
