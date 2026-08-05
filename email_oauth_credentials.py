"""Resolve Microsoft / Google OAuth app credentials (environment or Program Settings)."""
from __future__ import annotations

import os


def _env(name: str) -> str:
    return (os.environ.get(name) or '').strip()


def _program_oauth() -> dict:
    try:
        from program_settings_persistence import load_email_oauth_settings_raw
        return load_email_oauth_settings_raw()
    except Exception:
        return {}


def microsoft_client_id() -> str:
    return (
        _env('MICROSOFT_CLIENT_ID')
        or _env('AZURE_CLIENT_ID')
        or (_program_oauth().get('microsoft_client_id') or '').strip()
    )


def microsoft_client_secret() -> str:
    return (
        _env('MICROSOFT_CLIENT_SECRET')
        or _env('AZURE_CLIENT_SECRET')
        or (_program_oauth().get('microsoft_client_secret') or '').strip()
    )


def microsoft_tenant_id() -> str:
    return (
        _env('MICROSOFT_TENANT_ID')
        or _env('AZURE_TENANT_ID')
        or (_program_oauth().get('microsoft_tenant_id') or '').strip()
        or 'common'
    )


def google_client_id() -> str:
    return (
        _env('GOOGLE_CLIENT_ID')
        or _env('GMAIL_CLIENT_ID')
        or (_program_oauth().get('google_client_id') or '').strip()
    )


def google_client_secret() -> str:
    return (
        _env('GOOGLE_CLIENT_SECRET')
        or _env('GMAIL_CLIENT_SECRET')
        or (_program_oauth().get('google_client_secret') or '').strip()
    )


def microsoft_configured() -> bool:
    return bool(microsoft_client_id() and microsoft_client_secret())


def google_configured() -> bool:
    return bool(google_client_id() and google_client_secret())


def credential_sources() -> dict:
    """Which layer supplies credentials (for admin diagnostics; no secrets)."""
    po = _program_oauth()
    return {
        'microsoft': {
            'client_id_from_env': bool(_env('MICROSOFT_CLIENT_ID') or _env('AZURE_CLIENT_ID')),
            'client_secret_from_env': bool(_env('MICROSOFT_CLIENT_SECRET') or _env('AZURE_CLIENT_SECRET')),
            'client_id_from_settings': bool((po.get('microsoft_client_id') or '').strip()),
            'client_secret_from_settings': bool((po.get('microsoft_client_secret') or '').strip()),
        },
        'google': {
            'client_id_from_env': bool(_env('GOOGLE_CLIENT_ID') or _env('GMAIL_CLIENT_ID')),
            'client_secret_from_env': bool(_env('GOOGLE_CLIENT_SECRET') or _env('GMAIL_CLIENT_SECRET')),
            'client_id_from_settings': bool((po.get('google_client_id') or '').strip()),
            'client_secret_from_settings': bool((po.get('google_client_secret') or '').strip()),
        },
    }
