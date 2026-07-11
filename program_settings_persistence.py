"""Program-wide settings persisted to instance/program_settings.json."""

import json
import os
from datetime import datetime

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
    'sage_connection_mode',
    'sage_api_url',
    'sage_job_prefix',
]

COMPANY_KEYS = [
    'company_name', 'tax_id', 'company_phone', 'company_address',
    'company_city', 'company_state', 'company_zip', 'company_website',
    'company_license', 'dba_name', 'logo_data_url',
]

BACKUP_DEFAULTS = {
    'auto_enabled': False,
    'frequency': 'daily',
    'retention_days': 30,
    'local_path': 'instance/backups',
    'maintenance_window': '02:00',
    'last_run_at': '',
    'last_run_status': '',
    'cloud': {
        'enabled': False,
        'provider': 'local_folder',
        'local_mirror_path': '',
        'bucket': '',
        'region': '',
        'access_key_hint': '',
    },
}

MAINTENANCE_DEFAULTS = {
    'db_vacuum_enabled': True,
    'log_retention_days': 90,
    'temp_upload_cleanup_days': 14,
    'notify_admin_on_backup_failure': True,
}


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
    data = data or {}
    data['updated_at'] = datetime.utcnow().isoformat() + 'Z'
    path = _settings_path()
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)
    return data


def get_section(name, defaults=None):
    settings = load_program_settings()
    section = settings.get(name)
    if not isinstance(section, dict):
        section = {}
    base = dict(defaults or {})
    base.update(section)
    return base


def save_section(name, payload, defaults=None):
    settings = load_program_settings()
    merged = get_section(name, defaults)
    if isinstance(payload, dict):
        merged.update(payload)
    settings[name] = merged
    save_program_settings(settings)
    return merged


def load_sage_defaults():
    sage = get_section('sage', {})
    out = {k: (sage.get(k) or '').strip() for k in SAGE_DEFAULT_KEYS}
    if not out.get('sage_sync_enabled'):
        out['sage_sync_enabled'] = '1'
    if not out.get('sage_connection_mode'):
        out['sage_connection_mode'] = 'quick'
    return out


def save_sage_defaults(form_data):
    sage = {k: (form_data.get(k) or '').strip() for k in SAGE_DEFAULT_KEYS}
    if not sage.get('sage_sync_enabled'):
        sage['sage_sync_enabled'] = form_data.get('sage_sync_enabled') or '1'
    return save_section('sage', sage)


def load_company_info():
    return get_section('company', {
        'company_name': 'Case Construction',
        'tax_id': '', 'company_phone': '', 'company_address': '',
        'company_city': '', 'company_state': '', 'company_zip': '',
        'company_website': '', 'company_license': '', 'dba_name': '',
        'logo_data_url': '',
    })


def save_company_info(form_data):
    payload = {k: (form_data.get(k) or '').strip() for k in COMPANY_KEYS}
    if form_data.get('logo_data_url'):
        payload['logo_data_url'] = form_data['logo_data_url']
    return save_section('company', payload)


def load_backup_settings():
    return get_section('backup', BACKUP_DEFAULTS)


def save_backup_settings(form_data):
    cloud = form_data.get('cloud') if isinstance(form_data.get('cloud'), dict) else {}
    payload = {
        'auto_enabled': bool(form_data.get('auto_enabled')),
        'frequency': form_data.get('frequency') or 'daily',
        'retention_days': int(form_data.get('retention_days') or 30),
        'local_path': form_data.get('local_path') or BACKUP_DEFAULTS['local_path'],
        'maintenance_window': form_data.get('maintenance_window') or '02:00',
        'cloud': {
            'enabled': bool(cloud.get('enabled')),
            'provider': cloud.get('provider') or 'local_folder',
            'local_mirror_path': (cloud.get('local_mirror_path') or '').strip(),
            'bucket': (cloud.get('bucket') or '').strip(),
            'region': (cloud.get('region') or '').strip(),
            'access_key_hint': (cloud.get('access_key_hint') or '').strip(),
        },
    }
    return save_section('backup', payload, BACKUP_DEFAULTS)


def load_maintenance_settings():
    return get_section('maintenance', MAINTENANCE_DEFAULTS)


def save_maintenance_settings(form_data):
    return save_section('maintenance', {
        'db_vacuum_enabled': bool(form_data.get('db_vacuum_enabled', True)),
        'log_retention_days': int(form_data.get('log_retention_days') or 90),
        'temp_upload_cleanup_days': int(form_data.get('temp_upload_cleanup_days') or 14),
        'notify_admin_on_backup_failure': bool(form_data.get('notify_admin_on_backup_failure', True)),
    }, MAINTENANCE_DEFAULTS)


def load_email_settings_mirror():
    return get_section('email', {})


def save_email_settings_mirror(payload):
    if not isinstance(payload, dict):
        return {}
    clean = {k: v for k, v in payload.items() if not str(k).startswith('_')}
    return save_section('email', clean)


def merge_sage_context(project_details, sage_defaults=None):
    defaults = sage_defaults if sage_defaults is not None else load_sage_defaults()
    details = project_details or {}
    merged = dict(defaults)
    for key in SAGE_DEFAULT_KEYS:
        val = (details.get(key) or '').strip()
        if val:
            merged[key] = val
    return merged


def settings_summary_for_ui():
    settings = load_program_settings()
    return {
        'company': load_company_info(),
        'sage': load_sage_defaults(),
        'backup': load_backup_settings(),
        'maintenance': load_maintenance_settings(),
        'email': load_email_settings_mirror(),
        'updated_at': settings.get('updated_at'),
    }
