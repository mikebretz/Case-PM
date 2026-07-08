"""Program-wide settings persisted to instance/program_settings.json."""

import json
import os

SAGE_DEFAULT_KEYS = [
    'sage_company_code',
    'sage_database',
    'sage_account_set',
    'sage_accounting_method',
    'sage_billings_account',
    'sage_wip_account',
    'sage_revenue_account',
    'sage_ar_customer_code',
    'sage_default_tax_group',
    'sage_ap_vendor_prefix',
    'sage_cost_code_prefix',
    'sage_subcontract_liability_account',
    'sage_default_cost_type',
    'sage_sync_enabled',
]


def _settings_path():
    return os.path.join('instance', 'program_settings.json')


def load_program_settings():
    path = _settings_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_program_settings(data):
    os.makedirs('instance', exist_ok=True)
    path = _settings_path()
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data or {}, fh, indent=2)
    return data


def load_sage_defaults():
    sage = load_program_settings().get('sage') or {}
    if not isinstance(sage, dict):
        return {}
    return {k: (sage.get(k) or '').strip() for k in SAGE_DEFAULT_KEYS}


def save_sage_defaults(form_data):
    settings = load_program_settings()
    sage = {k: (form_data.get(k) or '').strip() for k in SAGE_DEFAULT_KEYS}
    if not sage.get('sage_sync_enabled'):
        sage['sage_sync_enabled'] = '1'
    settings['sage'] = sage
    save_program_settings(settings)
    return sage


def merge_sage_context(project_details, sage_defaults=None):
    """Project non-empty values override program-wide Sage defaults."""
    defaults = sage_defaults if sage_defaults is not None else load_sage_defaults()
    details = project_details or {}
    merged = dict(defaults)
    for key in SAGE_DEFAULT_KEYS:
        val = (details.get(key) or '').strip()
        if val:
            merged[key] = val
    return merged
