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
    'session_cookie_hours': 12,
}

DOCUMENT_DEFAULTS = {
    'share_requires_approval': False,
    'default_share_expiry_days': 30,
    'max_share_expiry_days': 365,
    'retention_years': 7,
}

ESTIMATING_DEFAULTS = {
    'rfp_notify_mode': 'both',
    'award_auto_commitment': False,
    'reminder_hours_before': 48,
    'budget_mapping_auto': True,
    'ai_scope_enabled': True,
    'fee_breakdown_visible': True,
}

INSPECTION_DEFAULTS = {
    'reminder_offsets': ['morning_of', '1h'],
    'notify_creator': True,
    'default_notify_pm': True,
}

REGIONAL_DEFAULTS = {
    'default_locale': 'en-US',
    'default_date_format': 'MDY',
    'default_timezone': 'America/New_York',
}

WORKFLOW_DEFAULTS = {
    'require_daily_log_weather': False,
    'require_manpower_on_daily_log': False,
    'auto_archive_inactive_users_days': 0,
    'default_new_user_role': 'Company User',
    'default_license_tier': '',
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
    """Internal — includes SMTP password for outbound mail."""
    return get_section('email', {})


def save_email_settings_mirror(payload):
    return save_company_email_settings(payload)


def load_company_email_settings(mask_secret: bool = True):
    section = get_section('email', {})
    out = dict(section)
    if mask_secret:
        pwd = out.get('smtpPassword') or out.get('smtp_password')
        if pwd:
            out['smtpPassword'] = '********'
            out['_smtpPasswordSet'] = True
    out['scope'] = 'company'
    return out


def save_company_email_settings(payload):
    if not isinstance(payload, dict):
        return load_company_email_settings()
    existing = get_section('email', {})
    clean = dict(existing)
    clean.update({k: v for k, v in payload.items() if not str(k).startswith('_')})
    incoming_pwd = payload.get('smtpPassword') or payload.get('smtp_password')
    if incoming_pwd in (None, '', '********'):
        if existing.get('smtpPassword'):
            clean['smtpPassword'] = existing.get('smtpPassword')
        elif existing.get('smtp_password'):
            clean['smtpPassword'] = existing.get('smtp_password')
    else:
        clean['smtpPassword'] = incoming_pwd
    clean['scope'] = 'company'
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
    try:
        out['session_cookie_hours'] = max(1, min(int(out.get('session_cookie_hours') or 12), 168))
    except (TypeError, ValueError):
        out['session_cookie_hours'] = 12
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
        'session_cookie_hours': max(1, min(int(payload.get('session_cookie_hours') or 12), 168)),
    }, SECURITY_DEFAULTS)


def load_document_defaults():
    section = get_section('documents', DOCUMENT_DEFAULTS)
    out = dict(DOCUMENT_DEFAULTS)
    out.update(section)
    out['share_requires_approval'] = bool(out.get('share_requires_approval'))
    try:
        out['default_share_expiry_days'] = max(1, min(int(out.get('default_share_expiry_days') or 30), 365))
    except (TypeError, ValueError):
        out['default_share_expiry_days'] = 30
    try:
        out['max_share_expiry_days'] = max(1, min(int(out.get('max_share_expiry_days') or 365), 365))
    except (TypeError, ValueError):
        out['max_share_expiry_days'] = 365
    try:
        out['retention_years'] = max(1, min(int(out.get('retention_years') or 7), 99))
    except (TypeError, ValueError):
        out['retention_years'] = 7
    return out


def save_document_defaults(payload):
    if not isinstance(payload, dict):
        return load_document_defaults()
    return save_section('documents', {
        'share_requires_approval': bool(payload.get('share_requires_approval')),
        'default_share_expiry_days': int(payload.get('default_share_expiry_days') or 30),
        'max_share_expiry_days': int(payload.get('max_share_expiry_days') or 365),
        'retention_years': int(payload.get('retention_years') or 7),
    }, DOCUMENT_DEFAULTS)


def load_notification_defaults():
    from user_extended_prefs import default_notification_prefs, merge_notification_prefs
    raw = get_section('notifications', {})
    if raw:
        return merge_notification_prefs(raw)
    return default_notification_prefs()


def save_notification_defaults(payload):
    from user_extended_prefs import merge_notification_prefs
    merged = merge_notification_prefs(payload or {})
    return save_section('notifications', merged)


def load_estimating_defaults():
    section = get_section('estimating', ESTIMATING_DEFAULTS)
    out = dict(ESTIMATING_DEFAULTS)
    out.update(section)
    mode = str(out.get('rfp_notify_mode') or 'both').lower()
    if mode not in ('both', 'in_app', 'email', 'none'):
        mode = 'both'
    out['rfp_notify_mode'] = mode
    out['award_auto_commitment'] = bool(out.get('award_auto_commitment'))
    out['budget_mapping_auto'] = bool(out.get('budget_mapping_auto', True))
    out['ai_scope_enabled'] = bool(out.get('ai_scope_enabled', True))
    out['fee_breakdown_visible'] = bool(out.get('fee_breakdown_visible', True))
    try:
        out['reminder_hours_before'] = max(1, min(int(out.get('reminder_hours_before') or 48), 168))
    except (TypeError, ValueError):
        out['reminder_hours_before'] = 48
    return out


def save_estimating_defaults(payload):
    if not isinstance(payload, dict):
        return load_estimating_defaults()
    mode = str(payload.get('rfp_notify_mode') or 'both').lower()
    if mode not in ('both', 'in_app', 'email', 'none'):
        mode = 'both'
    return save_section('estimating', {
        'rfp_notify_mode': mode,
        'award_auto_commitment': bool(payload.get('award_auto_commitment')),
        'reminder_hours_before': int(payload.get('reminder_hours_before') or 48),
        'budget_mapping_auto': bool(payload.get('budget_mapping_auto', True)),
        'ai_scope_enabled': bool(payload.get('ai_scope_enabled', True)),
        'fee_breakdown_visible': bool(payload.get('fee_breakdown_visible', True)),
    }, ESTIMATING_DEFAULTS)


def load_inspection_defaults():
    section = get_section('inspections', INSPECTION_DEFAULTS)
    out = dict(INSPECTION_DEFAULTS)
    out.update(section)
    offsets = out.get('reminder_offsets') or list(INSPECTION_DEFAULTS['reminder_offsets'])
    if not isinstance(offsets, list):
        offsets = list(INSPECTION_DEFAULTS['reminder_offsets'])
    out['reminder_offsets'] = [str(x) for x in offsets if x]
    out['notify_creator'] = bool(out.get('notify_creator', True))
    out['default_notify_pm'] = bool(out.get('default_notify_pm', True))
    return out


def save_inspection_defaults(payload):
    if not isinstance(payload, dict):
        return load_inspection_defaults()
    offsets = payload.get('reminder_offsets') or []
    if not isinstance(offsets, list):
        offsets = []
    return save_section('inspections', {
        'reminder_offsets': [str(x) for x in offsets if x],
        'notify_creator': bool(payload.get('notify_creator', True)),
        'default_notify_pm': bool(payload.get('default_notify_pm', True)),
    }, INSPECTION_DEFAULTS)


def load_regional_defaults():
    section = get_section('regional', REGIONAL_DEFAULTS)
    out = dict(REGIONAL_DEFAULTS)
    out.update(section)
    out['default_locale'] = (out.get('default_locale') or 'en-US').strip() or 'en-US'
    out['default_date_format'] = (out.get('default_date_format') or 'MDY').strip() or 'MDY'
    out['default_timezone'] = (out.get('default_timezone') or 'America/New_York').strip() or 'America/New_York'
    return out


def save_regional_defaults(payload):
    if not isinstance(payload, dict):
        return load_regional_defaults()
    return save_section('regional', {
        'default_locale': (payload.get('default_locale') or 'en-US').strip(),
        'default_date_format': (payload.get('default_date_format') or 'MDY').strip(),
        'default_timezone': (payload.get('default_timezone') or 'America/New_York').strip(),
    }, REGIONAL_DEFAULTS)


def load_workflow_defaults():
    section = get_section('workflow', WORKFLOW_DEFAULTS)
    out = dict(WORKFLOW_DEFAULTS)
    out.update(section)
    out['require_daily_log_weather'] = bool(out.get('require_daily_log_weather'))
    out['require_manpower_on_daily_log'] = bool(out.get('require_manpower_on_daily_log'))
    try:
        out['auto_archive_inactive_users_days'] = max(0, int(out.get('auto_archive_inactive_users_days') or 0))
    except (TypeError, ValueError):
        out['auto_archive_inactive_users_days'] = 0
    out['default_new_user_role'] = (out.get('default_new_user_role') or 'Company User').strip()
    out['default_license_tier'] = (out.get('default_license_tier') or '').strip()
    return out


def save_workflow_defaults(payload):
    if not isinstance(payload, dict):
        return load_workflow_defaults()
    return save_section('workflow', {
        'require_daily_log_weather': bool(payload.get('require_daily_log_weather')),
        'require_manpower_on_daily_log': bool(payload.get('require_manpower_on_daily_log')),
        'auto_archive_inactive_users_days': max(0, int(payload.get('auto_archive_inactive_users_days') or 0)),
        'default_new_user_role': (payload.get('default_new_user_role') or 'Company User').strip(),
        'default_license_tier': (payload.get('default_license_tier') or '').strip(),
    }, WORKFLOW_DEFAULTS)


def integrations_status():
    import os
    sage_url = (os.environ.get('SAGE_API_URL') or '').strip()
    sage_key = bool((os.environ.get('SAGE_API_KEY') or '').strip())
    try:
        from aia_service import integration_info as aia_info
        aia = aia_info()
    except Exception:
        aia = {'configured': False}
    try:
        from docusign_service import integration_info as docusign_info
        docusign = docusign_info()
    except Exception:
        docusign = {'configured': False}
    try:
        from microsoft_graph_mail_service import integration_info as microsoft_mail_info
        microsoft_mail = microsoft_mail_info()
    except Exception:
        microsoft_mail = {'configured': False}
    return {
        'sage_api_url_set': bool(sage_url),
        'sage_api_key_set': sage_key,
        'sage_live': bool(sage_url and sage_key),
        'aia': aia,
        'docusign': docusign,
        'microsoft_mail': microsoft_mail,
        'secret_key_from_env': bool(os.environ.get('CASEPM_SECRET_KEY', '').strip()),
        'deployment_env': (os.environ.get('CASEPM_DEPLOYMENT') or '').strip() or None,
    }


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
        'documents': load_document_defaults(),
        'notifications': load_notification_defaults(),
        'estimating': load_estimating_defaults(),
        'inspections': load_inspection_defaults(),
        'regional': load_regional_defaults(),
        'workflow': load_workflow_defaults(),
        'integrations': integrations_status(),
        'updated_at': settings.get('updated_at'),
    }
