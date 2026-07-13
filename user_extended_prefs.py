"""Extended user preferences — notifications, locale, integrations, HR documents."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

HR_DOCUMENT_DIR = os.path.join('uploads', 'user_hr_documents')
MAX_HR_DOCUMENT_BYTES = 15 * 1024 * 1024
ALLOWED_HR_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.doc', '.docx', '.xls', '.xlsx'}

NOTIFICATION_MODULES = [
    ('rfis', 'RFIs'),
    ('submittals', 'Submittals'),
    ('change_orders', 'Change Orders'),
    ('pay_applications', 'Pay Applications'),
    ('commitments', 'Commitments'),
    ('estimating_rfp', 'Estimating / RFP'),
    ('safety', 'Safety'),
    ('schedule', 'Schedule'),
    ('documents', 'Documents'),
    ('inspections', 'Inspections'),
    ('daily_log', 'Daily Log'),
    ('punch_list', 'Punch List'),
    ('email', 'Email / Messages'),
]

NOTIFY_MODES = ('both', 'in_app', 'email', 'none')
DIGEST_MODES = ('immediate', 'daily', 'weekly', 'none')

HR_DOCUMENT_TYPES = [
    ('w9', 'W-9 / Tax'),
    ('insurance', 'Insurance / COI'),
    ('license', 'Trade License'),
    ('nda', 'NDA / Agreement'),
    ('i9', 'I-9 / Onboarding'),
    ('osha', 'OSHA / Safety'),
    ('other', 'Other'),
]

LOCALE_OPTIONS = [
    ('en-US', 'English (US)'),
    ('en-GB', 'English (UK)'),
    ('es-US', 'Spanish (US)'),
    ('fr-CA', 'French (Canada)'),
]

DATE_FORMAT_OPTIONS = [
    ('MDY', 'MM/DD/YYYY'),
    ('DMY', 'DD/MM/YYYY'),
    ('YMD', 'YYYY-MM-DD'),
]


def default_notification_prefs() -> dict:
    modules = {key: 'both' for key, _ in NOTIFICATION_MODULES}
    return {
        'email_enabled': True,
        'in_app_enabled': True,
        'digest': 'immediate',
        'modules': modules,
        'quiet_hours_enabled': False,
        'quiet_hours_start': '22:00',
        'quiet_hours_end': '07:00',
        'weekend_digest_only': False,
    }


def default_integrations() -> dict:
    return {
        'sso_provider': '',
        'sso_external_id': '',
        'microsoft_entra_id': '',
        'google_workspace_id': '',
        'procore_user_id': '',
        'procore_login': '',
        'autodesk_id': '',
        'sage_employee_code': '',
        'sage_resource_id': '',
        'docusign_user_id': '',
        'quickbooks_employee_id': '',
        'adp_worker_id': '',
        'external_hr_system_id': '',
    }


def ensure_user_extended_schema(db):
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if 'user' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('user')}
    additions = {
        'locale': 'VARCHAR(20)',
        'office_location': 'VARCHAR(120)',
        'cost_center': 'VARCHAR(80)',
        'hire_date': 'VARCHAR(20)',
        'reports_to_user_id': 'INTEGER',
        'default_project_id': 'INTEGER',
        'bio': 'TEXT',
        'linkedin_url': 'VARCHAR(300)',
        'work_phone_ext': 'VARCHAR(20)',
        'date_format_pref': 'VARCHAR(10)',
        'notification_prefs_json': 'TEXT',
        'integrations_json': 'TEXT',
        'hr_documents_json': 'TEXT',
        'invite_sent_at': 'DATETIME',
    }
    for col, ddl in additions.items():
        if col not in cols:
            db.session.execute(text(f'ALTER TABLE user ADD COLUMN {col} {ddl}'))
    db.session.commit()
    os.makedirs(HR_DOCUMENT_DIR, exist_ok=True)


def _parse_json_obj(raw) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _parse_json_list(raw) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def merge_notification_prefs(raw) -> dict:
    base = default_notification_prefs()
    incoming = _parse_json_obj(raw) if isinstance(raw, str) else (raw or {})
    if not isinstance(incoming, dict):
        return base
    base.update({k: v for k, v in incoming.items() if k != 'modules'})
    modules = dict(base['modules'])
    modules.update(incoming.get('modules') or {})
    for key, _ in NOTIFICATION_MODULES:
        mode = str(modules.get(key) or 'both').lower()
        modules[key] = mode if mode in NOTIFY_MODES else 'both'
    base['modules'] = modules
    digest = str(base.get('digest') or 'immediate').lower()
    base['digest'] = digest if digest in DIGEST_MODES else 'immediate'
    return base


def merge_integrations(raw) -> dict:
    base = default_integrations()
    incoming = _parse_json_obj(raw) if isinstance(raw, str) else (raw or {})
    if isinstance(incoming, dict):
        base.update({k: (incoming.get(k) or '').strip() if isinstance(incoming.get(k), str) else incoming.get(k) for k in base})
    return base


def invite_status_for_user(user) -> str:
    if getattr(user, 'status', None) == 'Inactive':
        return 'Inactive'
    if not getattr(user, 'access_enabled', True):
        return 'Access off'
    if getattr(user, 'must_change_password', False) and not getattr(user, 'last_login', None):
        return 'Pending invite'
    if getattr(user, 'must_change_password', False):
        return 'Password change required'
    if getattr(user, 'last_login', None):
        return 'Active'
    return 'Never logged in'


def serialize_extended_prefs(user) -> dict:
    reports_to_id = getattr(user, 'reports_to_user_id', None)
    default_project_id = getattr(user, 'default_project_id', None)
    hr_docs = []
    for doc in _parse_json_list(getattr(user, 'hr_documents_json', None)):
        if not isinstance(doc, dict):
            continue
        hr_docs.append({
            'id': doc.get('id'),
            'type': doc.get('type') or 'other',
            'name': doc.get('name') or '',
            'expires': doc.get('expires') or '',
            'uploaded_at': doc.get('uploaded_at') or '',
            'size': doc.get('size'),
            'has_file': bool(doc.get('file_path')),
        })
    return {
        'locale': getattr(user, 'locale', None) or 'en-US',
        'dateFormat': getattr(user, 'date_format_pref', None) or 'MDY',
        'officeLocation': getattr(user, 'office_location', None) or '',
        'costCenter': getattr(user, 'cost_center', None) or '',
        'hireDate': getattr(user, 'hire_date', None) or '',
        'reportsToUserId': reports_to_id,
        'defaultProjectId': default_project_id,
        'bio': getattr(user, 'bio', None) or '',
        'linkedinUrl': getattr(user, 'linkedin_url', None) or '',
        'workPhoneExt': getattr(user, 'work_phone_ext', None) or '',
        'notificationPrefs': merge_notification_prefs(getattr(user, 'notification_prefs_json', None)),
        'integrations': merge_integrations(getattr(user, 'integrations_json', None)),
        'hrDocuments': hr_docs,
        'inviteStatus': invite_status_for_user(user),
        'inviteSentAt': user.invite_sent_at.isoformat() if getattr(user, 'invite_sent_at', None) else None,
    }


def apply_extended_prefs(user, body: dict) -> None:
    if 'locale' in body and hasattr(user, 'locale'):
        user.locale = (body.get('locale') or 'en-US').strip() or 'en-US'
    if ('dateFormat' in body or 'date_format_pref' in body) and hasattr(user, 'date_format_pref'):
        user.date_format_pref = (body.get('dateFormat') or body.get('date_format_pref') or 'MDY').strip() or 'MDY'
    if ('officeLocation' in body or 'office_location' in body) and hasattr(user, 'office_location'):
        user.office_location = (body.get('officeLocation') or body.get('office_location') or '').strip() or None
    if ('costCenter' in body or 'cost_center' in body) and hasattr(user, 'cost_center'):
        user.cost_center = (body.get('costCenter') or body.get('cost_center') or '').strip() or None
    if ('hireDate' in body or 'hire_date' in body) and hasattr(user, 'hire_date'):
        user.hire_date = (body.get('hireDate') or body.get('hire_date') or '').strip() or None
    if ('bio' in body) and hasattr(user, 'bio'):
        user.bio = (body.get('bio') or '').strip() or None
    if ('linkedinUrl' in body or 'linkedin_url' in body) and hasattr(user, 'linkedin_url'):
        user.linkedin_url = (body.get('linkedinUrl') or body.get('linkedin_url') or '').strip() or None
    if ('workPhoneExt' in body or 'work_phone_ext' in body) and hasattr(user, 'work_phone_ext'):
        user.work_phone_ext = (body.get('workPhoneExt') or body.get('work_phone_ext') or '').strip() or None
    if ('reportsToUserId' in body or 'reports_to_user_id' in body) and hasattr(user, 'reports_to_user_id'):
        val = body.get('reportsToUserId', body.get('reports_to_user_id'))
        user.reports_to_user_id = int(val) if val not in (None, '', 0) else None
    if ('defaultProjectId' in body or 'default_project_id' in body) and hasattr(user, 'default_project_id'):
        val = body.get('defaultProjectId', body.get('default_project_id'))
        user.default_project_id = int(val) if val not in (None, '', 0) else None
    if 'notificationPrefs' in body and hasattr(user, 'notification_prefs_json'):
        user.notification_prefs_json = json.dumps(merge_notification_prefs(body.get('notificationPrefs')))
    if 'integrations' in body and hasattr(user, 'integrations_json'):
        user.integrations_json = json.dumps(merge_integrations(body.get('integrations')))
    if body.get('mark_invite_sent') and hasattr(user, 'invite_sent_at'):
        user.invite_sent_at = datetime.utcnow()


def list_hr_documents(user) -> list[dict]:
    return _parse_json_list(getattr(user, 'hr_documents_json', None))


def _save_hr_documents(user, docs: list[dict]) -> None:
    user.hr_documents_json = json.dumps(docs) if docs else None


def add_hr_document(user, *, doc_type: str, name: str, file_storage, expires: str = '') -> dict:
    if not file_storage or not file_storage.filename:
        raise ValueError('Document file is required')
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_HR_EXTENSIONS:
        raise ValueError('File type not allowed for HR documents')
    data = file_storage.read()
    if len(data) > MAX_HR_DOCUMENT_BYTES:
        raise ValueError('Document is too large (max 15 MB)')
    os.makedirs(HR_DOCUMENT_DIR, exist_ok=True)
    doc_id = uuid.uuid4().hex[:12]
    filename = f'user_{user.id}_{doc_id}{ext}'
    path = os.path.join(HR_DOCUMENT_DIR, filename)
    with open(path, 'wb') as fh:
        fh.write(data)
    doc = {
        'id': doc_id,
        'type': doc_type or 'other',
        'name': (name or file_storage.filename).strip(),
        'file_path': path,
        'expires': (expires or '').strip(),
        'uploaded_at': datetime.utcnow().isoformat(),
        'size': len(data),
    }
    docs = list_hr_documents(user)
    docs.append(doc)
    _save_hr_documents(user, docs)
    return {
        'id': doc_id,
        'type': doc['type'],
        'name': doc['name'],
        'expires': doc['expires'],
        'uploaded_at': doc['uploaded_at'],
        'size': doc['size'],
        'has_file': True,
    }


def remove_hr_document(user, doc_id: str) -> bool:
    docs = list_hr_documents(user)
    kept = []
    removed = False
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if doc.get('id') == doc_id:
            removed = True
            path = doc.get('file_path')
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            continue
        kept.append(doc)
    if removed:
        _save_hr_documents(user, kept)
    return removed


def hr_document_file_path(user, doc_id: str) -> str | None:
    for doc in list_hr_documents(user):
        if isinstance(doc, dict) and doc.get('id') == doc_id:
            path = doc.get('file_path')
            if path and os.path.isfile(path):
                return path
    return None


def user_should_receive_notification(user, module_key: str, channel: str = 'email') -> bool:
    """Check per-user notification prefs. channel: email | in_app"""
    prefs = merge_notification_prefs(getattr(user, 'notification_prefs_json', None))
    if channel == 'email' and not prefs.get('email_enabled', True):
        return False
    if channel == 'in_app' and not prefs.get('in_app_enabled', True):
        return False
    if prefs.get('digest') == 'none' and channel == 'email':
        return False
    mode = str((prefs.get('modules') or {}).get(module_key) or 'both').lower()
    if mode == 'none':
        return False
    if channel == 'email':
        return mode in ('both', 'email')
    return mode in ('both', 'in_app')
