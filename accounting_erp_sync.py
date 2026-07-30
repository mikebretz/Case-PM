"""Optional Sage 300 sync — not required for built-in accounting."""
from __future__ import annotations

import os


def sage_integration_status():
    from program_settings_persistence import load_sage_defaults
    sage = load_sage_defaults()
    bridge = os.environ.get('SAGE_API_URL', '').strip() or (sage.get('sage_api_url') or '').strip()
    enabled = sage.get('sage_sync_enabled', '1') != '0'
    return {
        'system': 'Sage 300',
        'optional': True,
        'enabled': enabled and bool(bridge),
        'bridge_url_configured': bool(bridge),
        'company_code': sage.get('sage_company_code', ''),
        'note': 'Built-in Case PM Accounting operates independently. Enable Sage only when you want to sync construction financials.',
    }


def probe_sage_web_api():
    try:
        from sage300_web_client import probe_connection
        return probe_connection()
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
