"""
Case PM permissions catalog — modules, sub-tabs, access levels, approval rights, role templates.
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

# Page tabs / sub-sections keyed by parent module
MODULE_SUBMODULES = {
    'pay_applications': [
        ('pay_applications_gc', 'GC Pay Applications (G702 / G703)'),
        ('pay_applications_sub', 'Subcontractor Pay Applications'),
        ('pay_applications_lien_waivers', 'Lien Waivers'),
    ],
    'change_orders': [
        ('change_orders_log', 'Change Orders'),
        ('change_orders_pco', 'PCO Log'),
        ('change_orders_sub', 'Sub Change Orders'),
        ('change_orders_events', 'Change Events'),
        ('change_orders_rfq', 'Subcontractor RFQs'),
        ('change_orders_cor', 'Change Order Requests (COR)'),
        ('change_orders_cpco', 'Commitment PCOs (CPCO)'),
        ('change_orders_erp', 'ERP Accounting Queue'),
    ],
    'estimating': [
        ('estimating_summary', 'Summary'),
        ('estimating_worksheet', 'Worksheet'),
        ('estimating_rfp', 'Bid Packages / RFPs'),
        ('estimating_takeoff', 'Takeoff'),
        ('estimating_leveling', 'Bid Leveling'),
        ('estimating_award', 'Award & Budget'),
    ],
    'safety': [
        ('safety_reports', 'Observations & Incidents'),
        ('safety_training', 'Training & Certifications'),
        ('safety_toolbox', 'Toolbox Meetings'),
        ('safety_library', 'OSHA Library'),
    ],
}

SUBMODULE_PARENT = {}
for _parent, _subs in MODULE_SUBMODULES.items():
    for sub_key, _ in _subs:
        SUBMODULE_PARENT[sub_key] = _parent

# Module groups for UI
MODULE_GROUPS = [
    {
        'id': 'core',
        'label': 'Core & Navigation',
        'modules': [
            ('dashboard', 'Dashboard'),
            ('projects', 'Projects'),
            ('project_directory', 'Project Directory'),
            ('schedule', 'Schedule'),
            ('email', 'Email'),
            ('internal_messages', 'Internal Messages'),
            ('safety', 'Safety'),
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
            ('estimating', 'Estimating'),
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

# Modules that support approval workflow (parent keys; sub-keys inherit in UI)
APPROVAL_MODULES = frozenset({
    'rfis', 'submittals', 'change_orders', 'change_orders_log', 'change_orders_pco', 'change_orders_sub',
    'change_orders_events', 'change_orders_rfq', 'change_orders_cor', 'change_orders_cpco', 'change_orders_erp',
    'budget', 'commitments',
    'pay_applications', 'pay_applications_gc', 'pay_applications_sub',
    'daily_log', 'safety', 'safety_reports', 'punch_list',
})

FINANCIAL_MODULE_KEYS = frozenset({
    'budget', 'forecast', 'commitments', 'pay_applications',
    'pay_applications_gc', 'pay_applications_sub', 'pay_applications_lien_waivers',
    'companies', 'estimating',
    'estimating_summary', 'estimating_worksheet', 'estimating_rfp',
    'estimating_takeoff', 'estimating_leveling', 'estimating_award',
})

# Map legacy display names → module keys
LEGACY_MODULE_MAP = {
    'Dashboard': 'dashboard',
    'Projects': 'projects',
    'Project Directory': 'project_directory',
    'Budget': 'budget',
    'Commitments': 'commitments',
    'Pay Applications': 'pay_applications',
    'Daily Log': 'daily_log',
    'Daily Reports': 'daily_log',
    'Weekly Reports': 'weekly_report',
    'RFIs': 'rfis',
    'Submittals': 'submittals',
    'Change Orders': 'change_orders',
    'Estimating': 'estimating',
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
    'Internal Messages': 'internal_messages',
    'Forecast': 'forecast',
    'Deliveries': 'deliveries',
    'Inspections': 'inspections',
    'Meeting Minutes': 'meeting_minutes',
    'Notifications': 'notifications',
}

WORKFLOW_MODULE_MAP = {
    'Pay Applications': 'pay_applications',
    'Change Orders': 'change_orders',
    'Commitments': 'commitments',
    'Estimating': 'estimating',
    'Submittals': 'submittals',
    'RFIs': 'rfis',
    'Budget': 'budget',
    'Daily Log': 'daily_log',
    'Safety': 'safety',
    'Documents': 'documents',
    'Email': 'email',
    'Internal Messages': 'internal_messages',
    'Schedule': 'schedule',
    'Drawings': 'drawings',
}

ACCESS_RANK = {k: i for i, (k, _) in enumerate(ACCESS_LEVELS)}
APPROVE_RANK = {k: i for i, (k, _) in enumerate(APPROVE_LEVELS)}


def parent_module_keys():
    keys = []
    for group in MODULE_GROUPS:
        for key, _ in group['modules']:
            keys.append(key)
    return keys


def submodule_keys_for(parent: str):
    return [k for k, _ in MODULE_SUBMODULES.get(parent, [])]


def all_module_keys():
    keys = []
    for key in parent_module_keys():
        keys.append(key)
        keys.extend(submodule_keys_for(key))
    return keys


def default_module_perms(access='view', approve='none'):
    return {k: {'access': access, 'approve': approve} for k in all_module_keys()}


SUB_PORTAL_ROLES = frozenset({
    'Subcontractor Accountant',
    'Subcontractor Contact',
    'Subcontractor',
    'Company User',
})


def ensure_messaging_modules(perms: dict, role: str | None = None) -> dict:
    """
    Split internal messaging from external email for sub portal roles.
    Migrates legacy email-only grants to internal_messages when appropriate.
    """
    if not isinstance(perms, dict):
        return perms
    modules = perms.setdefault('modules', {})
    global_opts = perms.get('global') or {}
    role_name = (role or '').strip()

    def rank_of(mod_key: str) -> int:
        return ACCESS_RANK.get((modules.get(mod_key) or {}).get('access', 'none'), 0)

    def access_for_rank(rank: int) -> str:
        for key, _ in ACCESS_LEVELS:
            if ACCESS_RANK[key] == rank:
                return key
        return 'view'

    email_rank = rank_of('email')
    internal_rank = rank_of('internal_messages')
    internal_only = bool(global_opts.get('email_internal_only')) or role_name in SUB_PORTAL_ROLES
    if not internal_only and role_name:
        tpl = ROLE_TEMPLATES.get(role_name) or {}
        tpl_global = tpl.get('global') or {}
        if tpl_global.get('email_internal_only') or tpl.get('portal') == 'consultant':
            internal_only = True

    if internal_only:
        target_rank = max(internal_rank, email_rank, ACCESS_RANK['view'])
        if rank_of('internal_messages') < target_rank:
            modules['internal_messages'] = {'access': access_for_rank(target_rank), 'approve': 'none'}
        elif internal_rank == 0:
            modules['internal_messages'] = {'access': 'view', 'approve': 'none'}
        modules['email'] = {'access': 'none', 'approve': 'none'}
    elif email_rank > 0 and internal_rank == 0:
        modules['internal_messages'] = {
            'access': access_for_rank(max(email_rank, ACCESS_RANK['view'])),
            'approve': 'none',
        }
    return perms


def inherit_submodule_defaults(modules: dict) -> dict:
    """Copy parent module access to sub-tabs when sub-tab not explicitly set."""
    out = dict(modules or {})
    for parent, subs in MODULE_SUBMODULES.items():
        parent_perms = out.get(parent)
        if not parent_perms:
            continue
        for sub_key, _ in subs:
            if sub_key not in out:
                out[sub_key] = dict(parent_perms)
    return out


def _set_modules(perms_dict, **overrides):
    """overrides: module_key=(access, approve) or module_key=access_str"""
    for key, val in overrides.items():
        if isinstance(val, tuple):
            perms_dict[key] = {'access': val[0], 'approve': val[1]}
        else:
            perms_dict[key] = {'access': val, 'approve': perms_dict.get(key, {}).get('approve', 'none')}
    return perms_dict


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
            'project_directory': ('view', 'none'),
            'rfis': ('edit', 'approve_reject'),
            'submittals': ('edit', 'approve_reject'),
            'change_orders': ('edit', 'approve_reject'),
            'change_orders_log': ('edit', 'approve_reject'),
            'change_orders_pco': ('edit', 'approve_reject'),
            'change_orders_sub': ('edit', 'approve_reject'),
            'change_orders_events': ('edit', 'approve_reject'),
            'change_orders_rfq': ('edit', 'approve_reject'),
            'change_orders_cor': ('edit', 'approve_reject'),
            'change_orders_cpco': ('edit', 'approve_reject'),
            'change_orders_erp': ('edit', 'approve_reject'),
            'estimating': ('edit', 'approve_reject'),
            'estimating_summary': ('edit', 'approve_reject'),
            'estimating_worksheet': ('edit', 'approve_reject'),
            'estimating_rfp': ('edit', 'approve_reject'),
            'estimating_takeoff': ('edit', 'approve_reject'),
            'estimating_leveling': ('edit', 'approve_reject'),
            'estimating_award': ('edit', 'approve_reject'),
            'budget': ('edit', 'approve_reject'),
            'commitments': ('edit', 'approve_reject'),
            'pay_applications': ('edit', 'approve_reject'),
            'pay_applications_gc': ('edit', 'approve_reject'),
            'pay_applications_sub': ('edit', 'approve_reject'),
            'pay_applications_lien_waivers': ('edit', 'none'),
            'companies': ('edit', 'none'),
            'safety_reports': ('edit', 'approve_reject'),
            'safety_training': ('edit', 'none'),
            'safety_toolbox': ('edit', 'none'),
            'safety_library': ('view', 'none'),
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
            'project_directory': ('view', 'none'),
            'schedule': ('view', 'none'),
            'daily_log': ('edit', 'submit'),
            'weekly_report': ('edit', 'none'),
            'photos': ('edit', 'none'),
            'punch_list': ('edit', 'approve'),
            'safety': ('edit', 'approve_reject'),
            'safety_reports': ('edit', 'approve_reject'),
            'safety_training': ('edit', 'none'),
            'safety_toolbox': ('edit', 'none'),
            'safety_library': ('view', 'none'),
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
        'description': 'Consultant review — submittals, RFIs, drawings, documents, project directory',
        'global': {'hide_financials': True, 'email_internal_only': True},
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('client_view', 'none'),
            'project_directory': ('view', 'none'),
            'drawings': ('edit', 'none'),
            'documents': ('edit', 'none'),
            'rfis': ('edit', 'approve_reject'),
            'submittals': ('edit', 'approve_reject'),
            'change_orders': ('view', 'approve_reject'),
            'change_orders_log': ('view', 'approve_reject'),
            'change_orders_pco': ('view', 'none'),
            'change_orders_sub': ('view', 'approve_reject'),
            'photos': ('edit', 'none'),
            'punch_list': ('view', 'none'),
            'inspections': ('view', 'none'),
            'meeting_minutes': ('view', 'none'),
            'internal_messages': ('edit', 'none'),
            'email': ('none', 'none'),
            'schedule': ('none', 'none'),
            'estimating': ('none', 'none'),
            'change_orders_rfq': ('none', 'none'),
        }),
    },
    'Owner': {
        'portal': 'consultant',
        'description': 'Owner/client — broad read access; no financial modules',
        'global': {'hide_financials': True},
        'modules': _set_modules(default_module_perms('client_view', 'none'), **{
            'dashboard': ('client_view', 'none'),
            'projects': ('client_view', 'none'),
            'project_directory': ('client_view', 'none'),
            'schedule': ('client_view', 'none'),
            'rfis': ('client_view', 'none'),
            'submittals': ('client_view', 'none'),
            'change_orders': ('client_view', 'approve_reject'),
            'change_orders_log': ('client_view', 'approve_reject'),
            'change_orders_pco': ('client_view', 'none'),
            'change_orders_sub': ('client_view', 'none'),
            'documents': ('client_view', 'none'),
            'drawings': ('client_view', 'none'),
            'daily_log': ('client_view', 'none'),
            'weekly_report': ('client_view', 'none'),
            'photos': ('client_view', 'none'),
            'punch_list': ('client_view', 'none'),
            'safety': ('client_view', 'none'),
            'safety_reports': ('client_view', 'none'),
            'inspections': ('client_view', 'none'),
            'meeting_minutes': ('client_view', 'none'),
            'email': ('edit', 'none'),
            'budget': ('none', 'none'),
            'forecast': ('none', 'none'),
            'commitments': ('none', 'none'),
            'pay_applications': ('none', 'none'),
            'pay_applications_gc': ('none', 'none'),
            'pay_applications_sub': ('none', 'none'),
            'pay_applications_lien_waivers': ('none', 'none'),
            'companies': ('none', 'none'),
            'users': ('none', 'none'),
            'program_settings': ('none', 'none'),
            'audit_log': ('none', 'none'),
        }),
    },
    'Contractor Accounting': {
        'portal': 'staff',
        'description': 'GC financial modules — budget, commitments, full pay applications',
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('view', 'none'),
            'budget': ('edit', 'approve_reject'),
            'forecast': ('edit', 'none'),
            'commitments': ('edit', 'approve_reject'),
            'pay_applications': ('edit', 'approve_reject'),
            'pay_applications_gc': ('edit', 'approve_reject'),
            'pay_applications_sub': ('edit', 'approve_reject'),
            'pay_applications_lien_waivers': ('edit', 'none'),
            'change_orders': ('edit', 'approve_reject'),
            'change_orders_log': ('edit', 'approve_reject'),
            'change_orders_pco': ('view', 'none'),
            'change_orders_sub': ('edit', 'approve_reject'),
            'change_orders_events': ('view', 'none'),
            'change_orders_rfq': ('view', 'none'),
            'change_orders_cor': ('view', 'none'),
            'change_orders_cpco': ('view', 'none'),
            'change_orders_erp': ('edit', 'approve_reject'),
            'companies': ('edit', 'none'),
            'documents': ('view', 'none'),
            'schedule': ('view', 'none'),
            'email': ('edit', 'none'),
        }),
    },
    'Subcontractor Accountant': {
        'portal': 'sub',
        'description': 'Sub/vendor — RFQ portal, bid portal, and own pay applications only',
        'global': {
            'client_portal_only': True,
            'sub_vendor_portal_only': True,
            'email_internal_only': True,
        },
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'pay_applications': ('entry', 'submit'),
            'pay_applications_sub': ('entry', 'submit'),
            'pay_applications_lien_waivers': ('entry', 'none'),
            'pay_applications_gc': ('none', 'none'),
            'change_orders_rfq': ('entry', 'submit'),
            'estimating': ('view', 'none'),
            'documents': ('view', 'none'),
            'internal_messages': ('view', 'none'),
            'email': ('none', 'none'),
        }),
    },
    'Subcontractor Contact': {
        'portal': 'sub',
        'description': 'Sub/vendor main contact — RFQ portal, bid portal, internal messages',
        'global': {
            'client_portal_only': True,
            'sub_vendor_portal_only': True,
            'email_internal_only': True,
        },
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'change_orders_rfq': ('entry', 'submit'),
            'estimating': ('view', 'none'),
            'documents': ('view', 'none'),
            'internal_messages': ('edit', 'none'),
            'email': ('none', 'none'),
            'pay_applications': ('none', 'none'),
            'pay_applications_gc': ('none', 'none'),
            'pay_applications_sub': ('none', 'none'),
            'pay_applications_lien_waivers': ('none', 'none'),
        }),
    },
    'Subcontractor': {
        'portal': 'sub',
        'description': 'Subcontractor PM — RFIs, submittals, project info; no GC financials',
        'global': {
            'email_internal_only': True,
        },
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('view', 'none'),
            'projects': ('client_view', 'none'),
            'schedule': ('view', 'none'),
            'rfis': ('entry', 'submit'),
            'submittals': ('entry', 'submit'),
            'change_orders_rfq': ('entry', 'submit'),
            'documents': ('view', 'none'),
            'drawings': ('view', 'none'),
            'punch_list': ('view', 'none'),
            'internal_messages': ('edit', 'none'),
            'email': ('none', 'none'),
            'pay_applications': ('none', 'none'),
            'pay_applications_gc': ('none', 'none'),
            'pay_applications_sub': ('none', 'none'),
            'pay_applications_lien_waivers': ('none', 'none'),
        }),
    },
    'Company User': {
        'portal': 'sub',
        'description': 'Subcontractor PM — RFIs, submittals, project info; no GC financials',
        'global': {
            'email_internal_only': True,
        },
        'modules': _set_modules(default_module_perms('none', 'none'), **{
            'dashboard': ('view', 'none'),
            'projects': ('client_view', 'none'),
            'schedule': ('view', 'none'),
            'rfis': ('entry', 'submit'),
            'submittals': ('entry', 'submit'),
            'change_orders_rfq': ('entry', 'submit'),
            'documents': ('view', 'none'),
            'drawings': ('view', 'none'),
            'punch_list': ('view', 'none'),
            'internal_messages': ('edit', 'none'),
            'email': ('none', 'none'),
            'pay_applications': ('none', 'none'),
            'pay_applications_gc': ('none', 'none'),
            'pay_applications_sub': ('none', 'none'),
            'pay_applications_lien_waivers': ('none', 'none'),
        }),
    },
    'Viewer': {
        'portal': 'staff',
        'description': 'Read-only across permitted modules',
        'modules': default_module_perms('view', 'none'),
    },
}


def catalog_for_ui():
    groups = []
    for group in MODULE_GROUPS:
        g = dict(group)
        g['submodules'] = {
            parent: [{'key': k, 'label': lbl} for k, lbl in MODULE_SUBMODULES.get(parent, [])]
            for parent, _ in group['modules']
            if parent in MODULE_SUBMODULES
        }
        groups.append(g)
    return {
        'groups': groups,
        'access_levels': ACCESS_LEVELS,
        'approve_levels': APPROVE_LEVELS,
        'portal_types': PORTAL_TYPES,
        'approval_modules': sorted(APPROVAL_MODULES),
        'submodules': MODULE_SUBMODULES,
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
        raw = dict(raw)
        raw['modules'] = inherit_submodule_defaults(raw.get('modules') or {})
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
    modules = inherit_submodule_defaults(modules)
    return {
        'version': 2,
        'portal': 'staff',
        'modules': modules,
        'global': {'customized': True},
    }


def permissions_from_role(role):
    tpl = ROLE_TEMPLATES.get(role or 'Viewer', ROLE_TEMPLATES['Viewer'])
    modules = inherit_submodule_defaults({k: dict(v) for k, v in tpl['modules'].items()})
    global_opts = dict(tpl.get('global') or {})
    global_opts['from_role'] = role
    perms = {
        'version': 2,
        'portal': tpl['portal'],
        'modules': modules,
        'global': global_opts,
    }
    return ensure_messaging_modules(perms, role)


def merge_permissions(role, stored_json):
    role_base = permissions_from_role(role)
    if stored_json:
        try:
            import json
            raw = json.loads(stored_json) if isinstance(stored_json, str) else stored_json
            normalized = normalize_legacy_permissions(raw)
            if normalized and normalized.get('version') == 2:
                merged = _merge_with_role_defaults(role_base, normalized)
                return ensure_messaging_modules(merged, role)
        except (TypeError, ValueError):
            pass
    return role_base


def _merge_with_role_defaults(role_base: dict, stored: dict) -> dict:
    """Apply stored customizations on top of the role template, backfilling new modules."""
    base_modules = {k: dict(v) for k, v in (role_base.get('modules') or {}).items()}
    stored_modules = stored.get('modules') or {}
    merged_modules = dict(base_modules)
    for key, val in stored_modules.items():
        if isinstance(val, dict):
            merged_modules[key] = dict(val)
    return {
        'version': stored.get('version', 2),
        'portal': stored.get('portal') or role_base.get('portal', 'staff'),
        'modules': inherit_submodule_defaults(merged_modules),
        'global': {**(role_base.get('global') or {}), **(stored.get('global') or {})},
    }
