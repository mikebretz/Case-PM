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

# Document / record numbering — prefix, zero-pad width, scope (global|project)
NUMBERING_DEFAULTS = {
    'project': {'label': 'Projects', 'prefix': 'PRJ', 'pad': 3, 'scope': 'global'},
    'rfi': {'label': 'RFIs', 'prefix': 'RFI', 'pad': 3, 'scope': 'global'},
    'change_order': {'label': 'Change Orders', 'prefix': 'CO', 'pad': 3, 'scope': 'global'},
    'sub_change_order': {'label': 'Subcontractor Change Orders', 'prefix': 'SCO', 'pad': 3, 'scope': 'project'},
    'change_event': {'label': 'Change Events', 'prefix': 'CE', 'pad': 3, 'scope': 'project'},
    'rfq': {'label': 'Subcontractor RFQs', 'prefix': 'RFQ', 'pad': 3, 'scope': 'project'},
    'estimate': {'label': 'Estimates', 'prefix': 'EST', 'pad': 3, 'scope': 'project'},
    'bid_package': {'label': 'Bid Packages / RFPs', 'prefix': 'RFP', 'pad': 3, 'scope': 'project'},
    'cor': {'label': 'Change Order Requests', 'prefix': 'COR', 'pad': 3, 'scope': 'project'},
    'cpco': {'label': 'Commitment PCOs', 'prefix': 'CPCO', 'pad': 3, 'scope': 'project'},
    'pco': {'label': 'Potential Change Orders', 'prefix': 'PCO', 'pad': 3, 'scope': 'global'},
    'submittal': {'label': 'Submittals', 'prefix': 'SUB', 'pad': 3, 'scope': 'global'},
    'punch': {'label': 'Punch List', 'prefix': 'PL', 'pad': 3, 'scope': 'global'},
    'safety': {'label': 'Safety Reports', 'prefix': 'SAF', 'pad': 3, 'scope': 'global'},
    'inspection': {'label': 'Permits & Inspections', 'prefix': 'INSP', 'pad': 3, 'scope': 'project'},
    'delivery': {'label': 'Deliveries', 'prefix': 'DEL', 'pad': 3, 'scope': 'project'},
    'meeting': {'label': 'Meeting Minutes', 'prefix': 'MM', 'pad': 3, 'scope': 'project'},
    'toolbox': {'label': 'Toolbox Meetings', 'prefix': 'TB', 'pad': 3, 'scope': 'project'},
    'commitment_po': {'label': 'Purchase Orders', 'prefix': 'PO', 'pad': 3, 'scope': 'project'},
    'commitment_sc': {'label': 'Subcontracts', 'prefix': 'SC', 'pad': 3, 'scope': 'project'},
    'commitment_ms': {'label': 'Material Supply', 'prefix': 'MS', 'pad': 3, 'scope': 'project'},
    'commitment_sa': {'label': 'Service Agreements', 'prefix': 'SA', 'pad': 3, 'scope': 'project'},
    'commitment_com': {'label': 'Other Commitments', 'prefix': 'COM', 'pad': 3, 'scope': 'project'},
}

PAY_APP_DEFAULTS = {
    'default_retainage_percent': 10,
    'require_lien_waiver_on_sub_pay_app': True,
    'require_all_sub_pay_apps_before_g702': False,
    'allow_zero_dollar_sub_pay_apps': False,
    'require_submission_deadline': False,
    'submission_deadline_day': 20,
    'sage_sync_auto_enabled': False,
}

SECURITY_DEFAULTS = {
    'session_timeout_minutes': 60,
    'warn_before_logout_minutes': 5,
    'require_strong_passwords': True,
    'max_login_attempts': 8,
    'lockout_minutes': 15,
    'deployment_mode': 'on_prem',
    'behind_reverse_proxy': False,
    'force_https': False,
    'trust_x_forwarded_proto': False,
    'hsts_max_age': 0,
    'allowed_hosts': '',
    'enforce_project_membership': False,
    'require_2fa_for_admins': False,
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
    existing = get_section('backup', BACKUP_DEFAULTS)
    payload = {
        'auto_enabled': bool(form_data.get('auto_enabled')),
        'frequency': form_data.get('frequency') or 'daily',
        'retention_days': int(form_data.get('retention_days') or 30),
        'local_path': form_data.get('local_path') or BACKUP_DEFAULTS['local_path'],
        'maintenance_window': form_data.get('maintenance_window') or '02:00',
        'last_run_at': form_data.get('last_run_at', existing.get('last_run_at', '')),
        'last_run_status': form_data.get('last_run_status', existing.get('last_run_status', '')),
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


def load_numbering_config():
    raw = get_section('numbering', {})
    out = {}
    for key, defaults in NUMBERING_DEFAULTS.items():
        entry = dict(defaults)
        if key in raw and isinstance(raw[key], dict):
            entry.update({k: v for k, v in raw[key].items() if k in ('prefix', 'pad', 'scope')})
        entry['prefix'] = (entry.get('prefix') or defaults['prefix']).strip().upper()
        try:
            entry['pad'] = max(1, min(6, int(entry.get('pad') or defaults['pad'])))
        except (TypeError, ValueError):
            entry['pad'] = defaults['pad']
        entry['scope'] = entry.get('scope') or defaults['scope']
        out[key] = entry
    return out


def save_numbering_config(payload):
    if not isinstance(payload, dict):
        return load_numbering_config()
    clean = {}
    for key, defaults in NUMBERING_DEFAULTS.items():
        src = payload.get(key) if isinstance(payload.get(key), dict) else {}
        prefix = (src.get('prefix') or defaults['prefix']).strip().upper()
        try:
            pad = max(1, min(6, int(src.get('pad') or defaults['pad'])))
        except (TypeError, ValueError):
            pad = defaults['pad']
        scope = src.get('scope') if src.get('scope') in ('global', 'project') else defaults['scope']
        clean[key] = {'prefix': prefix, 'pad': pad, 'scope': scope}
    return save_section('numbering', clean, NUMBERING_DEFAULTS)


def get_numbering_prefix(doc_type, project_id=None):
    """Return (prefix, pad) for a document type key."""
    cfg = load_numbering_config().get(doc_type) or NUMBERING_DEFAULTS.get(doc_type, {})
    prefix = (cfg.get('prefix') or 'DOC').strip().upper()
    pad = int(cfg.get('pad') or 3)
    return prefix, pad


def format_document_number(prefix, seq, pad=3):
    return f'{prefix}-{int(seq):0{pad}d}'


def load_pay_app_defaults():
    section = get_section('pay_apps', PAY_APP_DEFAULTS)
    out = dict(PAY_APP_DEFAULTS)
    out.update(section)
    try:
        out['default_retainage_percent'] = int(out.get('default_retainage_percent') or 10)
    except (TypeError, ValueError):
        out['default_retainage_percent'] = 10
    try:
        out['submission_deadline_day'] = int(out.get('submission_deadline_day') or 20)
    except (TypeError, ValueError):
        out['submission_deadline_day'] = 20
    for key in (
        'require_lien_waiver_on_sub_pay_app', 'require_all_sub_pay_apps_before_g702',
        'allow_zero_dollar_sub_pay_apps', 'require_submission_deadline', 'sage_sync_auto_enabled',
    ):
        out[key] = bool(out.get(key))
    return out


def save_pay_app_defaults(payload):
    if not isinstance(payload, dict):
        return load_pay_app_defaults()
    clean = {
        'default_retainage_percent': int(payload.get('default_retainage_percent') or 10),
        'require_lien_waiver_on_sub_pay_app': bool(payload.get('require_lien_waiver_on_sub_pay_app', True)),
        'require_all_sub_pay_apps_before_g702': bool(payload.get('require_all_sub_pay_apps_before_g702')),
        'allow_zero_dollar_sub_pay_apps': bool(payload.get('allow_zero_dollar_sub_pay_apps')),
        'require_submission_deadline': bool(payload.get('require_submission_deadline')),
        'submission_deadline_day': int(payload.get('submission_deadline_day') or 20),
        'sage_sync_auto_enabled': bool(payload.get('sage_sync_auto_enabled')),
    }
    return save_section('pay_apps', clean, PAY_APP_DEFAULTS)


def load_security_settings():
    section = get_section('security', SECURITY_DEFAULTS)
    out = dict(SECURITY_DEFAULTS)
    out.update(section)
    try:
        out['session_timeout_minutes'] = max(0, min(int(out.get('session_timeout_minutes') or 60), 480))
    except (TypeError, ValueError):
        out['session_timeout_minutes'] = 60
    try:
        out['warn_before_logout_minutes'] = max(1, min(int(out.get('warn_before_logout_minutes') or 5), 30))
    except (TypeError, ValueError):
        out['warn_before_logout_minutes'] = 5
    try:
        out['max_login_attempts'] = max(3, min(int(out.get('max_login_attempts') or 8), 20))
    except (TypeError, ValueError):
        out['max_login_attempts'] = 8
    try:
        out['lockout_minutes'] = max(5, min(int(out.get('lockout_minutes') or 15), 120))
    except (TypeError, ValueError):
        out['lockout_minutes'] = 15
    out['require_strong_passwords'] = bool(out.get('require_strong_passwords', True))
    out['deployment_mode'] = (out.get('deployment_mode') or 'on_prem').strip().lower()
    if out['deployment_mode'] not in ('on_prem', 'cloud'):
        out['deployment_mode'] = 'on_prem'
    out['behind_reverse_proxy'] = bool(out.get('behind_reverse_proxy', False))
    out['force_https'] = bool(out.get('force_https', False))
    out['trust_x_forwarded_proto'] = bool(out.get('trust_x_forwarded_proto', out['behind_reverse_proxy']))
    try:
        out['hsts_max_age'] = max(0, int(out.get('hsts_max_age') or 0))
    except (TypeError, ValueError):
        out['hsts_max_age'] = 0
    out['allowed_hosts'] = (out.get('allowed_hosts') or '').strip()
    out['enforce_project_membership'] = bool(out.get('enforce_project_membership', False))
    out['require_2fa_for_admins'] = bool(out.get('require_2fa_for_admins', False))
    return out


def save_security_settings(payload):
    if not isinstance(payload, dict):
        return load_security_settings()
    return save_section('security', {
        'session_timeout_minutes': max(0, min(int(payload.get('session_timeout_minutes') or 60), 480)),
        'warn_before_logout_minutes': max(1, min(int(payload.get('warn_before_logout_minutes') or 5), 30)),
        'require_strong_passwords': bool(payload.get('require_strong_passwords', True)),
        'max_login_attempts': max(3, min(int(payload.get('max_login_attempts') or 8), 20)),
        'lockout_minutes': max(5, min(int(payload.get('lockout_minutes') or 15), 120)),
        'deployment_mode': (payload.get('deployment_mode') or 'on_prem').strip().lower(),
        'behind_reverse_proxy': bool(payload.get('behind_reverse_proxy')),
        'force_https': bool(payload.get('force_https')),
        'trust_x_forwarded_proto': bool(payload.get('trust_x_forwarded_proto')),
        'hsts_max_age': max(0, int(payload.get('hsts_max_age') or 0)),
        'allowed_hosts': (payload.get('allowed_hosts') or '').strip(),
        'enforce_project_membership': bool(payload.get('enforce_project_membership')),
        'require_2fa_for_admins': bool(payload.get('require_2fa_for_admins')),
    }, SECURITY_DEFAULTS)


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
    numbering = load_numbering_config()
    numbering_ui = []
    for key, entry in numbering.items():
        defaults = NUMBERING_DEFAULTS.get(key, {})
        numbering_ui.append({
            'key': key,
            'label': defaults.get('label', key),
            'prefix': entry.get('prefix'),
            'pad': entry.get('pad'),
            'scope': entry.get('scope'),
            'example': format_document_number(entry.get('prefix', 'DOC'), 1, entry.get('pad', 3)),
        })
    return {
        'company': load_company_info(),
        'sage': load_sage_defaults(),
        'backup': load_backup_settings(),
        'maintenance': load_maintenance_settings(),
        'email': load_email_settings_mirror(),
        'numbering': numbering,
        'numbering_catalog': numbering_ui,
        'pay_apps': load_pay_app_defaults(),
        'security': load_security_settings(),
        'updated_at': settings.get('updated_at'),
    }
