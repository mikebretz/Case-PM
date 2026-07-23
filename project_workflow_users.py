"""Project-scoped directory entries and workflow notification targets."""
from __future__ import annotations

from project_team_persistence import ROLE_LABELS, migrate_legacy_team_contacts

CONSULTANT_WORKFLOW_ROLES = frozenset({
    'Architect',
    'Owner',
    'Structural Engineer',
    'MEP Engineer',
    'Civil Engineer',
})

ENGINEER_USER_ROLES = frozenset({
    'Structural Engineer',
    'MEP Engineer',
    'Civil Engineer',
})

TEAM_ROLE_TO_USER_ROLES = {
    'architect': {'Architect', *ENGINEER_USER_ROLES},
    'owner': {'Owner'},
    'project_manager': {'Project Manager', 'Admin'},
    'superintendent': {'Superintendent'},
    'estimator': {'Project Manager', 'Contractor Accounting'},
}


def _company_name(company_id, Company):
    if not company_id or Company is None:
        return ''
    try:
        row = Company.query.get(int(company_id))
        return (row.name if row else '') or ''
    except Exception:
        return ''


def _user_directory_row(user, *, role='', role_label='', company='', source='membership'):
    name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
    company_name = (company or getattr(user, 'company', None) or '').strip()
    display_role = role or (getattr(user, 'role', None) or '')
    return {
        'user_id': getattr(user, 'id', None),
        'name': name,
        'email': (getattr(user, 'email', None) or '').strip(),
        'phone': (getattr(user, 'phone', None) or '').strip(),
        'role': display_role,
        'role_label': role_label or display_role or 'Team Member',
        'company': company_name,
        'firm': company_name,
        'source': source,
    }


def _contact_directory_row(contact, source='team_contact'):
    firm = (contact.get('firm') or '').strip()
    return {
        'user_id': contact.get('user_id'),
        'name': (contact.get('name') or '').strip(),
        'email': (contact.get('email') or '').strip(),
        'phone': (contact.get('phone') or '').strip(),
        'role': (contact.get('role') or '').strip(),
        'role_label': (contact.get('role_label') or ROLE_LABELS.get(contact.get('role'), 'Contact')).strip(),
        'company': firm,
        'firm': firm,
        'source': source,
    }


def _entry_key(entry):
    uid = entry.get('user_id')
    if uid:
        return f'user:{uid}'
    email = (entry.get('email') or '').strip().lower()
    if email:
        return f'email:{email}'
    name = (entry.get('name') or '').strip().lower()
    role = (entry.get('role') or '').strip().lower()
    return f'name:{name}|{role}'


def _merge_directory_entry(existing, incoming):
    merged = dict(existing)
    for field in ('name', 'email', 'phone', 'role', 'role_label', 'company', 'firm'):
        if not (merged.get(field) or '').strip() and (incoming.get(field) or '').strip():
            merged[field] = incoming[field]
    if incoming.get('user_id') and not merged.get('user_id'):
        merged['user_id'] = incoming['user_id']
    merged['source'] = 'both'
    return merged


def build_project_directory(project, User, Company=None, ProjectMembership=None):
    """Assigned project members plus team contacts — basic contact fields only."""
    from project_access import _membership_model

    PM = ProjectMembership or _membership_model()
    entries_by_key = {}

    if PM is not None:
        for row in PM.query.filter_by(project_id=int(project.id)).all():
            user = User.query.get(row.user_id)
            if not user or (getattr(user, 'status', 'Active') or 'Active') != 'Active':
                continue
            company = _company_name(getattr(row, 'company_id', None), Company)
            if not company:
                company = _company_name(getattr(user, 'company_id', None), Company) or (getattr(user, 'company', None) or '')
            membership_role = (row.role or getattr(user, 'role', None) or 'Viewer').strip()
            entry = _user_directory_row(
                user,
                role=membership_role,
                role_label=membership_role,
                company=company,
                source='membership',
            )
            entries_by_key[_entry_key(entry)] = entry

    details = project.get_details() if hasattr(project, 'get_details') else {}
    team_contacts = migrate_legacy_team_contacts(details if isinstance(details, dict) else {})
    for contact in team_contacts:
        entry = _contact_directory_row(contact)
        if contact.get('user_id'):
            user = User.query.get(int(contact['user_id']))
            if user and (getattr(user, 'status', 'Active') or 'Active') == 'Active':
                company = entry.get('firm') or _company_name(getattr(user, 'company_id', None), Company) or (getattr(user, 'company', None) or '')
                entry = _user_directory_row(
                    user,
                    role=contact.get('role', '') or getattr(user, 'role', ''),
                    role_label=entry['role_label'],
                    company=company,
                    source='both',
                )
                if not entry['email'] and contact.get('email'):
                    entry['email'] = contact['email']
                if not entry['phone'] and contact.get('phone'):
                    entry['phone'] = contact['phone']
        key = _entry_key(entry)
        if key in entries_by_key:
            entries_by_key[key] = _merge_directory_entry(entries_by_key[key], entry)
        else:
            entries_by_key[key] = entry

    def sort_key(entry):
        order = {
            'owner': 0,
            'architect': 1,
            'project_manager': 2,
            'superintendent': 3,
            'estimator': 4,
            'custom': 5,
        }
        role = (entry.get('role') or '').strip().lower().replace(' ', '_')
        return (order.get(role, 99), (entry.get('name') or '').lower())

    return sorted(entries_by_key.values(), key=sort_key)


def _active_project_users(project_id, User, ProjectMembership=None):
    from project_access import _membership_model

    PM = ProjectMembership or _membership_model()
    users = []
    seen = set()
    if PM is not None:
        for row in PM.query.filter_by(project_id=int(project_id)).all():
            user = User.query.get(row.user_id)
            if not user or user.id in seen:
                continue
            if (getattr(user, 'status', 'Active') or 'Active') != 'Active':
                continue
            seen.add(user.id)
            users.append((user, row))

    try:
        project = None
        from flask import has_app_context
        if has_app_context():
            from app import Project as ProjectModel
            project = ProjectModel.query.get(int(project_id))
        if project is not None:
            details = project.get_details()
            for contact in migrate_legacy_team_contacts(details):
                uid = contact.get('user_id')
                if not uid or uid in seen:
                    continue
                user = User.query.get(int(uid))
                if not user or (getattr(user, 'status', 'Active') or 'Active') != 'Active':
                    continue
                seen.add(user.id)
                users.append((user, None))
    except Exception:
        pass
    return users


def resolve_project_users_by_roles(project_id, roles, User, ProjectMembership=None, *, exclude_user_id=None):
    wanted = {r for r in (roles or []) if r}
    if not wanted:
        return []
    targets = {}
    for user, row in _active_project_users(project_id, User, ProjectMembership):
        if exclude_user_id and int(user.id) == int(exclude_user_id):
            continue
        user_role = (getattr(user, 'role', None) or '').strip()
        membership_role = ((row.role if row else None) or user_role).strip()
        team_key = membership_role.lower().replace(' ', '_')
        matched = user_role in wanted or membership_role in wanted
        if not matched:
            matched = bool(TEAM_ROLE_TO_USER_ROLES.get(team_key, set()) & wanted)
        if matched:
            targets[user.id] = user
    return list(targets.values())


def resolve_project_ball_users(project_id, ball_role, User, *, can_act_fn, ProjectMembership=None, exclude_user_id=None):
    """Active project members who can act on the current ball-in-court role."""
    if not ball_role:
        return []
    targets = {}
    for user, _row in _active_project_users(project_id, User, ProjectMembership):
        if exclude_user_id and int(user.id) == int(exclude_user_id):
            continue
        try:
            if can_act_fn(user, ball_role):
                targets[user.id] = user
        except Exception:
            continue
    if targets:
        return list(targets.values())

    try:
        from co_persistence import ROLE_APPROVERS
        allowed_roles = set(ROLE_APPROVERS.get(ball_role, (ball_role,)))
    except Exception:
        allowed_roles = {ball_role}
    return resolve_project_users_by_roles(
        project_id,
        allowed_roles,
        User,
        ProjectMembership,
        exclude_user_id=exclude_user_id,
    )


def resolve_project_consultant_users(project_id, User, ProjectMembership=None, *, exclude_user_id=None):
    """Architect, owner, and engineer users assigned to the project."""
    return resolve_project_users_by_roles(
        project_id,
        CONSULTANT_WORKFLOW_ROLES,
        User,
        ProjectMembership,
        exclude_user_id=exclude_user_id,
    )
