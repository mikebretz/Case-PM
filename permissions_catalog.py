"""
Case PM permissions catalog — modules, access levels, approval rights, role templates.
Used by User Management (admin) and case_workflow enforcement.
"""
from __future__ import annotations

# Access levels (increasing privilege)
ACCESS_LEVELS = [
    ('none', 'No Access'),
    ('client_view', 'Client / External View'),
    ('view', 'View Only'),
    ('entry', 'Entry Only'),
    ('edit', 'View + Edit'),
    ('admin', 'Module Admin'),
]

APPROVE_LEVELS = [
    ('none', 'None'),
    ('submit', 'Submit for Approval'),
    ('approve', 'Approve Only'),
    ('reject', 'Reject Only'),
    ('approve_reject', 'Approve & Reject'),
]

PORTAL_TYPES = [
    ('staff', 'Staff (full internal)'),
    ('field', 'Field / Superintendent'),
    ('consultant', 'Consultant (Owner / Architect)'),
    ('sub', 'Subcontractor Portal'),
    ('client', 'Client View Only'),
]

# Module groups for UI
MODULE_GROUPS = [
    {
        'id': 'core',
        'label': 'Core & Navigation',
        'modules': [
            ('dashboard', 'Dashboard'),
            ('projects', 'Projects'),
            ('schedule', 'Schedule'),
            ('email', 'Email'),
            ('notifications', 'Notifications'),
        ],
    },
    {
        'id': 'field',
        'label': 'Field & Daily Operations',
        'modules': [
            ('daily_log', 'Daily Log'),
            ('weekly_report', 'Weekly Report'),
            ('photos', 'Photos'),
            ('punch_list', 'Punch List'),
            ('safety', 'Safety'),
            ('inspections', 'Inspections'),
            ('deliveries', 'Deliveries'),
            ('meeting_minutes', 'Meeting Minutes'),
        ],
    },
    {
        'id': 'project_docs',
        'label': 'Project Documentation',
        'modules': [
            ('rfis', 'RFIs'),
            ('submittals', 'Submittals'),
            ('change_orders', 'Change Orders'),
            ('documents', 'Documents'),
            ('drawings', 'Drawings'),
        ],
    },
    {
        'id': 'financial',
        'label': 'Financial',
        'modules': [
            ('budget', 'Budget'),
            ('forecast', 'Forecast'),
            ('commitments', 'Commitments'),
            ('pay_applications', 'Pay Applications'),
            ('companies', 'Companies / Vendors'),
        ],
    },
    {
        'id': 'administration',
        'label': 'Administration',
        'modules': [
            ('users', 'User Management'),
            ('program_settings', 'Program Settings'),
            ('audit_log', 'Audit Log'),
        ],
    },
]

# Modules that support approval workflow
APPROVAL_MODULES = frozenset({
    'rfis', 'submittals', 'change_orders', 'budget', 'commitments',
    'pay_applications', 'daily_log', 'safety', 'punch_list',
})

# Map legacy display names → module keys
LEGACY_MODULE_MAP = {
    'Dashboard': 'dashboard',
    'Projects': 'projects',
    'Budget': 'budget',
    'Commitments': 'commitments',
    'Pay Applications': 'pay_applications',
    'Daily Log': 'daily_log',
    'Daily Reports': 'daily_log',
    'Weekly Reports': 'weekly_report',
    'RFIs': 'rfis',
    'Submittals': 'submittals',
    'Change Orders': 'change_orders',
    'Punch List': 'punch_list',
    'Safety': 'safety',
    'Schedule': 'schedule',
    'Documents': 'documents',
    'Drawings': 'drawings',
    'Photos': 'photos',
    'Companies / Vendors': 'companies',
    'User Management': 'users',
    'Program Settings': 'program_settings',
    'Logs': 'audit_log',
    'Email': 'email',
    'Forecast': 'forecast',
    'Deliveries': 'deliveries',
    'Inspections': 'inspections',
    'Meeting Minutes': 'meeting_minutes',
    'Notifications': 'notifications',
}

# Map workflow module display names (case_workflow) → keys
WORKFLOW_MODULE_MAP = {
    'Pay Applications': 'pay_applications',
    'Change Orders': 'change_orders',
    'Commitments': 'commitments',
    'Submittals': 'submittals',
    'RFIs': 'rfis',
    'Budget': 'budget',
    'Daily Log': 'daily_log',
    'Safety': 'safety',
    'Documents': 'documents',
    'Email': 'email',
    'Schedule': 'schedule',
    'Drawings': 'drawings',
}

ACCESS_RANK = {k: i for i, (k, _) in enumerate(ACCESS_LEVELS)}
APPROVE_RANK = {k: i for i, (k, _) in enumerate(APPROVE_LEVELS)}


def all_module_keys():
    keys = []
    for group in MODULE_GROUPS:
        for key, _ in group['modules']:
            keys.append(key)
    return keys


def default_module_perms(access='view', approve='none'):
    return {k: {'access': access, 'approve': approve} for k in all_module_keys()}


def _set_modules(perms_dict, **overrides):
    """overrides: module_key=(access, approve) or module_key=access_str"""
    for key, val in overrides.items():
        if isinstance(val, tuple):
            perms_dict[key] = {'access': val[0], 'approve': val[1]}
        else:
            perms_dict[key] = {'access': val, 'approve': perms_dict.get(key, {}).get('approve', 'none')}


ROLE_TEMPLATES = {
    'Admin': {
        'portal': 'staff',
        'description': 'Full access to all modules and administration',
        'modules': default_module_perms('admin', 'approve_reject'),
    },
    'Project Manager': {
        'portal': 'staff',
        'description': 'Full project control; financial and approval authority',
        'modules': _set_modules(default_module_perms('edit', 'none'), **{
            'dashboard': ('edit', 'none'),
            'projects': ('admin', 'none'),
            'rfis': ('edit', 'approve_reject'),
            'submittals': ('edit', 'approve_reject'),
            'change_orders': ('edit', 'approve_reject'),
            'budget': ('edit', 'approve_reject'),
            'commitments': ('edit', 'approve_reject'),
            'pay_applications': ('edit', 'approve_reject'),
            'companies': ('edit', 'none'),
            'users': ('view', 'none'),
            'program_settings': ('view', 'none'),
            'audit_log': ('view', 'none'),
        }),
    },
    'Superintendent': {
        'portal': 'field',
        'description': 'Field operations, daily logs, safety, limited financial view',
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('view', 'none'),
            'projects': ('view', 'none'),
            'schedule': ('view', 'none'),
            'daily_log': ('edit', 'submit'),
            'weekly_report': ('edit', 'none'),
            'photos': ('edit', 'none'),
            'punch_list': ('edit', 'approve'),
            'safety': ('edit', 'approve_reject'),
            'inspections': ('edit', 'none'),
            'deliveries': ('entry', 'none'),
            'rfis': ('entry', 'none'),
            'submittals': ('view', 'none'),
            'documents': ('view', 'none'),
            'drawings': ('view', 'none'),
            'email': ('edit', 'none'),
        }),
    },
    'Architect': {
        'portal': 'consultant',
        'description': 'Consultant review — submittals, RFIs, change orders',
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('client_view', 'none'),
            'rfis': ('edit', 'approve_reject'),
            'submittals': ('edit', 'approve_reject'),
            'change_orders': ('view', 'approve_reject'),
            'drawings': ('view', 'none'),
            'documents': ('view', 'none'),
            'schedule': ('view', 'none'),
            'email': ('edit', 'none'),
        }),
    },
    'Owner': {
        'portal': 'consultant',
        'description': 'Owner/client — approvals on COs and pay apps, read-only elsewhere',
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('client_view', 'none'),
            'projects': ('client_view', 'none'),
            'change_orders': ('client_view', 'approve_reject'),
            'pay_applications': ('client_view', 'approve_reject'),
            'rfis': ('client_view', 'none'),
            'schedule': ('client_view', 'none'),
            'documents': ('client_view', 'none'),
            'email': ('edit', 'none'),
        }),
    },
    'Contractor Accounting': {
        'portal': 'staff',
        'description': 'Financial modules with approval on pay apps, COs, commitments',
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('view', 'none'),
            'budget': ('edit', 'approve_reject'),
            'forecast': ('edit', 'none'),
            'commitments': ('edit', 'approve_reject'),
            'pay_applications': ('edit', 'approve_reject'),
            'change_orders': ('edit', 'approve_reject'),
            'companies': ('edit', 'none'),
            'documents': ('view', 'none'),
            'schedule': ('view', 'none'),
            'email': ('edit', 'none'),
        }),
    },
    'Company User': {
        'portal': 'sub',
        'description': 'Subcontractor portal — pay apps, submittals, RFIs, documents',
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'pay_applications': ('entry', 'submit'),
            'submittals': ('entry', 'submit'),
            'rfis': ('entry', 'submit'),
            'documents': ('view', 'none'),
            'email': ('edit', 'none'),
        }),
    },
    'Viewer': {
        'portal': 'staff',
        'description': 'Read-only across permitted modules',
        'modules': default_module_perms('view', 'none'),
    },
    'Developer': {
        'portal': 'staff',
        'description': 'Technical override access (Developer Console)',
        'modules': default_module_perms('admin', 'approve_reject'),
    },
}


def catalog_for_ui():
    return {
        'groups': MODULE_GROUPS,
        'access_levels': ACCESS_LEVELS,
        'approve_levels': APPROVE_LEVELS,
        'portal_types': PORTAL_TYPES,
        'approval_modules': sorted(APPROVAL_MODULES),
        'role_templates': {
            role: {
                'portal': tpl['portal'],
                'description': tpl['description'],
            }
            for role, tpl in ROLE_TEMPLATES.items()
        },
    }


def normalize_legacy_permissions(raw):
    """Convert old {Module Name: {access, approve}} to v2 schema."""
    if not raw:
        return None
    if isinstance(raw, dict) and raw.get('version') == 2:
        return raw
    modules = default_module_perms('none', 'none')
    legacy_access = {
        'No Access': 'none',
        'View': 'view',
        'Edit': 'edit',
        'Client View': 'client_view',
        'Entry Only': 'entry',
    }
    legacy_approve = {
        'None': 'none',
        'Approve Only': 'approve',
        'Reject Only': 'reject',
        'Approve & Reject': 'approve_reject',
        'Submit': 'submit',
    }
    if isinstance(raw, dict):
        for name, perms in raw.items():
            if name in ('version', 'portal', 'modules', 'global'):
                continue
            key = LEGACY_MODULE_MAP.get(name, name if name in all_module_keys() else None)
            if not key or not isinstance(perms, dict):
                continue
            modules[key] = {
                'access': legacy_access.get(perms.get('access'), perms.get('access', 'none')),
                'approve': legacy_approve.get(perms.get('approve'), perms.get('approve', 'none')),
            }
    return {
        'version': 2,
        'portal': 'staff',
        'modules': modules,
        'global': {'customized': True},
    }


def permissions_from_role(role):
    tpl = ROLE_TEMPLATES.get(role or 'Viewer', ROLE_TEMPLATES['Viewer'])
    return {
        'version': 2,
        'portal': tpl['portal'],
        'modules': {k: dict(v) for k, v in tpl['modules'].items()},
        'global': {'from_role': role},
    }


def merge_permissions(role, stored_json):
    if stored_json:
        try:
            import json
            raw = json.loads(stored_json) if isinstance(stored_json, str) else stored_json
            normalized = normalize_legacy_permissions(raw)
            if normalized and normalized.get('version') == 2:
                return normalized
        except (TypeError, ValueError):
            pass
    return permissions_from_role(role)
