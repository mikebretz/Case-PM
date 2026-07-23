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

ROLE_SORT_ORDER = {
    'owner': 0,
    'client': 0,
    'architect': 1,
    'project_manager': 2,
    'superintendent': 3,
    'estimator': 4,
    'gc_team': 5,
    'consultant': 6,
    'vendor_contact': 7,
    'vendor': 8,
    'subcontractor': 8,
    'submittal_contact': 9,
    'bidder': 10,
    'custom': 11,
}

# Permission / portal roles — not shown as directory position when a job title exists.
SYSTEM_ACCOUNT_ROLES = frozenset({
    'Admin',
    'Developer',
    'Viewer',
    'Contractor Accounting',
    'Subcontractor',
    'Subcontractor Contact',
    'Subcontractor Accountant',
    'Company User',
})


def _user_job_title(user) -> str:
    return (getattr(user, 'job_title', None) or '').strip()


def _resolve_position(*, job_title='', team_position='', context_position=''):
    """Prefer profile job title, then project team position, then contextual label."""
    for value in (job_title, team_position, context_position):
        text = (value or '').strip()
        if not text:
            continue
        if text in SYSTEM_ACCOUNT_ROLES and job_title:
            continue
        return text
    return ''


def _finalize_directory_entry(entry):
    """Ensure every row exposes a human position (job title), not a permission role."""
    position = (entry.get('position') or '').strip()
    if not position:
        position = _resolve_position(
            job_title=entry.get('job_title') or '',
            team_position=entry.get('role_label') or '',
            context_position=entry.get('context_position') or '',
        )
    role_key = (entry.get('role') or '').strip().lower().replace(' ', '_')
    if not position and role_key in ROLE_LABELS:
        position = ROLE_LABELS[role_key]
    entry['position'] = position or (entry.get('role_label') or '').strip()
    entry['job_title'] = (entry.get('job_title') or _user_job_title_from_entry(entry) or '').strip()
    return entry


def _user_job_title_from_entry(entry):
    return (entry.get('job_title') or '').strip()


def _company_name(company_id, Company):
    if not company_id or Company is None:
        return ''
    try:
        row = Company.query.get(int(company_id))
        return (row.name if row else '') or ''
    except Exception:
        return ''


def _user_directory_row(user, *, role='', role_label='', company='', source='membership', team_position=''):
    name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
    company_name = (company or getattr(user, 'company', None) or '').strip()
    job_title = _user_job_title(user)
    team_pos = (team_position or role_label or '').strip()
    if team_pos in SYSTEM_ACCOUNT_ROLES and not job_title:
        team_pos = ''
    position = _resolve_position(job_title=job_title, team_position=team_pos)
    return _finalize_directory_entry({
        'user_id': getattr(user, 'id', None),
        'name': name,
        'email': (getattr(user, 'email', None) or '').strip(),
        'phone': (getattr(user, 'phone', None) or '').strip(),
        'role': role or (getattr(user, 'role', None) or ''),
        'role_label': team_pos or role_label or '',
        'job_title': job_title,
        'position': position,
        'company': company_name,
        'firm': company_name,
        'source': source,
    })


def _person_directory_row(
    *,
    name='',
    email='',
    phone='',
    role='',
    role_label='',
    company='',
    source='',
    user_id=None,
    job_title='',
    position='',
):
    company_name = (company or '').strip()
    display_name = (name or company_name or '').strip()
    resolved_position = _resolve_position(
        job_title=job_title,
        team_position=role_label,
        context_position=position,
    )
    return _finalize_directory_entry({
        'user_id': user_id,
        'name': display_name,
        'email': (email or '').strip(),
        'phone': (phone or '').strip(),
        'role': role or 'contact',
        'role_label': role_label or role or '',
        'job_title': (job_title or '').strip(),
        'position': resolved_position,
        'company': company_name,
        'firm': company_name,
        'source': source,
    })


def _contact_directory_row(contact, source='team_contact'):
    firm = (contact.get('firm') or '').strip()
    team_position = (contact.get('role_label') or ROLE_LABELS.get(contact.get('role'), 'Contact')).strip()
    return _finalize_directory_entry({
        'user_id': contact.get('user_id'),
        'name': (contact.get('name') or '').strip(),
        'email': (contact.get('email') or '').strip(),
        'phone': (contact.get('phone') or '').strip(),
        'role': (contact.get('role') or '').strip(),
        'role_label': team_position,
        'job_title': '',
        'position': team_position,
        'company': firm,
        'firm': firm,
        'source': source,
    })


def _entry_key(entry):
    uid = entry.get('user_id')
    if uid:
        return f'user:{uid}'
    email = (entry.get('email') or '').strip().lower()
    if email:
        company = (entry.get('company') or '').strip().lower()
        return f'email:{email}|{company}'
    company = (entry.get('company') or '').strip().lower()
    name = (entry.get('name') or '').strip().lower()
    role = (entry.get('role') or '').strip().lower()
    if company and name == company:
        return f'company:{company}|{role}'
    return f'name:{name}|{role}|{company}'


def _merge_directory_entry(existing, incoming):
    merged = dict(existing)
    for field in ('name', 'email', 'phone', 'role', 'role_label', 'company', 'firm', 'job_title', 'position'):
        if not (merged.get(field) or '').strip() and (incoming.get(field) or '').strip():
            merged[field] = incoming[field]
    if incoming.get('user_id') and not merged.get('user_id'):
        merged['user_id'] = incoming['user_id']
    if existing.get('source') != incoming.get('source'):
        merged['source'] = 'both'
    return merged


def _add_entry(entries_by_key, entry):
    if not entry:
        return
    if not (entry.get('name') or '').strip() and not (entry.get('company') or '').strip():
        return
    key = _entry_key(entry)
    if key in entries_by_key:
        entries_by_key[key] = _merge_directory_entry(entries_by_key[key], entry)
    else:
        entries_by_key[key] = entry


def _lazy_models():
    try:
        from flask import has_app_context
        if not has_app_context():
            return {}
        from app import (
            BidInvitation,
            BidPackage,
            ChangeOrder,
            Commitment,
            Company,
            Estimate,
            PayAppProjectState,
            SubcontractorRFQ,
            Submittal,
        )
        return {
            'Commitment': Commitment,
            'PayAppProjectState': PayAppProjectState,
            'Submittal': Submittal,
            'ChangeOrder': ChangeOrder,
            'Estimate': Estimate,
            'BidPackage': BidPackage,
            'BidInvitation': BidInvitation,
            'SubcontractorRFQ': SubcontractorRFQ,
            'Company': Company,
        }
    except Exception:
        return {}


def _collect_membership_and_team(project, User, Company, ProjectMembership, entries_by_key):
    from project_access import _membership_model

    PM = ProjectMembership or _membership_model()
    if PM is not None:
        for row in PM.query.filter_by(project_id=int(project.id)).all():
            user = User.query.get(row.user_id)
            if not user or (getattr(user, 'status', 'Active') or 'Active') != 'Active':
                continue
            company = _company_name(getattr(row, 'company_id', None), Company)
            if not company:
                company = _company_name(getattr(user, 'company_id', None), Company) or (getattr(user, 'company', None) or '')
            membership_role = (row.role or '').strip()
            _add_entry(entries_by_key, _user_directory_row(
                user,
                role=membership_role or getattr(user, 'role', '') or '',
                team_position=membership_role if membership_role not in SYSTEM_ACCOUNT_ROLES else '',
                company=company,
                source='membership',
            ))

    details = project.get_details() if hasattr(project, 'get_details') else {}
    for contact in migrate_legacy_team_contacts(details if isinstance(details, dict) else {}):
        entry = _contact_directory_row(contact)
        if contact.get('user_id'):
            user = User.query.get(int(contact['user_id']))
            if user and (getattr(user, 'status', 'Active') or 'Active') == 'Active':
                company = entry.get('firm') or _company_name(getattr(user, 'company_id', None), Company) or (getattr(user, 'company', None) or '')
                entry = _user_directory_row(
                    user,
                    role=contact.get('role', '') or getattr(user, 'role', ''),
                    team_position=entry['role_label'],
                    company=company,
                    source='team_contact',
                )
                if not entry['email'] and contact.get('email'):
                    entry['email'] = contact['email']
                if not entry['phone'] and contact.get('phone'):
                    entry['phone'] = contact['phone']
        _add_entry(entries_by_key, entry)

    pm_name = (getattr(project, 'project_manager', None) or '').strip()
    if pm_name:
        _add_entry(entries_by_key, _person_directory_row(
            name=pm_name,
            role='project_manager',
            position='Project Manager',
            company='',
            source='project',
        ))

    client_company_id = getattr(project, 'client_company_id', None)
    if client_company_id and Company is not None:
        client_company = Company.query.get(int(client_company_id))
        if client_company:
            contact_name = f'{client_company.contact_first_name or ""} {client_company.contact_last_name or ""}'.strip()
            _add_entry(entries_by_key, _person_directory_row(
                name=contact_name or client_company.name,
                email=client_company.email or '',
                phone=client_company.phone or '',
                role='owner',
                position='Owner / Client',
                company=client_company.name,
                source='client_company',
            ))
    client_name = (getattr(project, 'client', None) or '').strip()
    if client_name and not client_company_id:
        _add_entry(entries_by_key, _person_directory_row(
            name=client_name,
            role='owner',
            position='Owner / Client',
            company=client_name,
            source='project',
        ))


def _collect_commitments(project_id, entries_by_key, Company, Commitment):
    if Commitment is None:
        return
    for commitment in Commitment.query.filter_by(project_id=int(project_id)).all():
        company_name = (getattr(commitment, 'company_name', None) or '').strip()
        if not company_name:
            continue
        ctype = (getattr(commitment, 'commitment_type', None) or 'Commitment').strip()
        number = (getattr(commitment, 'number', None) or '').strip()
        role_label = f'{ctype}{f" {number}" if number else ""}'.strip()
        contact_position = 'Subcontractor Contact' if ctype == 'Subcontract' else f'{ctype} Contact'
        contact_name = (getattr(commitment, 'contact_name', None) or '').strip()
        contact_email = (getattr(commitment, 'contact_email', None) or '').strip()
        contact_phone = (getattr(commitment, 'contact_phone', None) or '').strip()
        if contact_name or contact_email:
            _add_entry(entries_by_key, _person_directory_row(
                name=contact_name or company_name,
                email=contact_email,
                phone=contact_phone,
                role='vendor_contact',
                role_label=role_label,
                position=contact_position,
                company=company_name,
                source='commitment',
            ))
        else:
            _add_entry(entries_by_key, _person_directory_row(
                name=company_name,
                role='vendor',
                role_label=role_label,
                position=ctype or 'Vendor',
                company=company_name,
                source='commitment',
            ))


def _collect_pay_app_sov(project_id, entries_by_key, User, Company, PayAppProjectState, Commitment):
    if PayAppProjectState is None:
        return
    try:
        from pay_app_persistence import commitment_matches_sov_entry, get_pay_app_state
        from portal_sub_access import iter_sub_vendor_users_for_company, resolve_company_from_sov_key
    except Exception:
        return

    db = None
    try:
        from flask import has_app_context
        if has_app_context():
            from app import db as app_db
            db = app_db
    except Exception:
        pass

    try:
        _record, state = get_pay_app_state(PayAppProjectState, int(project_id), db=db)
    except Exception:
        return
    if not state:
        return
    sub_status = state.get('subSOVStatus') or {}
    if not isinstance(sub_status, dict):
        return
    commitments = Commitment.query.filter_by(project_id=int(project_id)).all() if Commitment is not None else []

    for key, status_entry in sub_status.items():
        if not isinstance(status_entry, dict):
            continue
        company_name = (
            status_entry.get('companyName')
            or status_entry.get('company_name')
            or str(key)
        ).strip()
        if not company_name:
            continue
        status = (status_entry.get('status') or '').strip()
        role_label = f'Subcontractor SOV{f" — {status}" if status else ""}'
        contact_position = 'Subcontractor Contact'

        contact_name = contact_email = contact_phone = ''
        for commitment in commitments:
            if commitment_matches_sov_entry(commitment, key, status_entry, company_name=company_name):
                contact_name = (getattr(commitment, 'contact_name', None) or '').strip()
                contact_email = (getattr(commitment, 'contact_email', None) or '').strip()
                contact_phone = (getattr(commitment, 'contact_phone', None) or '').strip()
                if contact_name or contact_email:
                    break

        company = resolve_company_from_sov_key(key, Company=Company, state=state)
        if company is not None:
            company_name = company.name or company_name
            directory_contact = f'{company.contact_first_name or ""} {company.contact_last_name or ""}'.strip()
            if directory_contact:
                _add_entry(entries_by_key, _person_directory_row(
                    name=directory_contact,
                    email=company.email or '',
                    phone=company.phone or '',
                    role='vendor_contact',
                    role_label=role_label,
                    position=contact_position,
                    company=company_name,
                    source='pay_app_sov',
                ))
            for user in iter_sub_vendor_users_for_company(company, User):
                if (getattr(user, 'status', 'Active') or 'Active') != 'Active':
                    continue
                _add_entry(entries_by_key, _user_directory_row(
                    user,
                    role='subcontractor',
                    team_position=contact_position,
                    company=company_name,
                    source='pay_app_sov',
                ))

        if contact_name or contact_email:
            _add_entry(entries_by_key, _person_directory_row(
                name=contact_name or company_name,
                email=contact_email,
                phone=contact_phone,
                role='vendor_contact',
                role_label=role_label,
                position=contact_position,
                company=company_name,
                source='pay_app_sov',
            ))
        elif not company:
            _add_entry(entries_by_key, _person_directory_row(
                name=company_name,
                role='subcontractor',
                role_label=role_label,
                position='Subcontractor',
                company=company_name,
                source='pay_app_sov',
            ))


def _collect_submittals(project_id, entries_by_key, User, Submittal):
    if Submittal is None:
        return
    seen = set()
    for submittal in Submittal.query.filter_by(project_id=int(project_id)).all():
        company_name = (getattr(submittal, 'assigned_company_name', None) or '').strip()
        contact_uid = getattr(submittal, 'assigned_contact_user_id', None)
        contact_email = (getattr(submittal, 'assigned_contact_email', None) or '').strip()
        contact_name = (getattr(submittal, 'assigned_contact_name', None) or '').strip()
        dedupe = (contact_uid, contact_email.lower(), company_name.lower())
        if dedupe in seen:
            continue
        if not any([contact_uid, contact_email, contact_name, company_name]):
            continue
        seen.add(dedupe)
        if contact_uid:
            user = User.query.get(int(contact_uid))
            if user and (getattr(user, 'status', 'Active') or 'Active') == 'Active':
                _add_entry(entries_by_key, _user_directory_row(
                    user,
                    role='submittal_contact',
                    team_position='Submittal Contact',
                    company=company_name or getattr(user, 'company', '') or '',
                    source='submittal',
                ))
                continue
        _add_entry(entries_by_key, _person_directory_row(
            name=contact_name or company_name,
            email=contact_email,
            role='submittal_contact',
            position='Submittal Contact',
            company=company_name,
            source='submittal',
        ))


def _collect_change_orders(project_id, entries_by_key, ChangeOrder):
    if ChangeOrder is None:
        return
    seen = set()
    for co in ChangeOrder.query.filter_by(project_id=int(project_id)).all():
        company_name = (getattr(co, 'company_name', None) or '').strip()
        contact_name = (getattr(co, 'contact_name', None) or '').strip()
        contact_email = (getattr(co, 'contact_email', None) or '').strip()
        contact_phone = (getattr(co, 'contact_phone', None) or '').strip()
        if not company_name and not contact_name and not contact_email:
            continue
        dedupe = (company_name.lower(), contact_email.lower(), contact_name.lower())
        if dedupe in seen:
            continue
        seen.add(dedupe)
        number = (getattr(co, 'number', None) or '').strip()
        role_label = f'Change Order Vendor{f" {number}" if number else ""}'.strip()
        _add_entry(entries_by_key, _person_directory_row(
            name=contact_name or company_name,
            email=contact_email,
            phone=contact_phone,
            role='vendor_contact',
            role_label=role_label,
            position='Vendor Contact',
            company=company_name,
            source='change_order',
        ))


def _collect_rfqs(project_id, entries_by_key, SubcontractorRFQ, Company):
    if SubcontractorRFQ is None:
        return
    seen = set()
    for rfq in SubcontractorRFQ.query.filter_by(project_id=int(project_id)).all():
        company_name = (getattr(rfq, 'company_name', None) or '').strip()
        company_id = getattr(rfq, 'company_id', None)
        if company_id and Company is not None and not company_name:
            company_name = _company_name(company_id, Company)
        if not company_name:
            continue
        key = company_name.lower()
        if key in seen:
            continue
        seen.add(key)
        number = (getattr(rfq, 'number', None) or '').strip()
        _add_entry(entries_by_key, _person_directory_row(
            name=company_name,
            role='vendor',
            role_label=f'RFQ Vendor{f" {number}" if number else ""}',
            position='RFQ Vendor',
            company=company_name,
            source='rfq',
        ))


def _collect_bid_invitations(project_id, entries_by_key, BidPackage, BidInvitation):
    if BidPackage is None or BidInvitation is None:
        return
    package_ids = [p.id for p in BidPackage.query.filter_by(project_id=int(project_id)).all()]
    if not package_ids:
        return
    seen = set()
    for invite in BidInvitation.query.filter(BidInvitation.bid_package_id.in_(package_ids)).all():
        company_name = (getattr(invite, 'company_name', None) or '').strip()
        contact_name = (getattr(invite, 'contact_name', None) or '').strip()
        contact_email = (getattr(invite, 'contact_email', None) or '').strip()
        dedupe = (company_name.lower(), contact_email.lower())
        if dedupe in seen:
            continue
        if not any([company_name, contact_name, contact_email]):
            continue
        seen.add(dedupe)
        _add_entry(entries_by_key, _person_directory_row(
            name=contact_name or company_name,
            email=contact_email,
            role='bidder',
            position='Bid Contact',
            company=company_name,
            source='bid_invitation',
        ))


def _safe_collect(collector, *args, **kwargs):
    try:
        collector(*args, **kwargs)
    except Exception:
        pass


def build_project_directory(project, User, Company=None, ProjectMembership=None):
    """Everyone attached to a project — team, vendors, SOV subs, and module contacts."""
    entries_by_key = {}
    models = _lazy_models()
    if Company is None:
        Company = models.get('Company')

    _safe_collect(_collect_membership_and_team, project, User, Company, ProjectMembership, entries_by_key)
    project_id = int(project.id)
    _safe_collect(_collect_commitments, project_id, entries_by_key, Company, models.get('Commitment'))
    _safe_collect(
        _collect_pay_app_sov,
        project_id,
        entries_by_key,
        User,
        Company,
        models.get('PayAppProjectState'),
        models.get('Commitment'),
    )
    _safe_collect(_collect_submittals, project_id, entries_by_key, User, models.get('Submittal'))
    _safe_collect(_collect_change_orders, project_id, entries_by_key, models.get('ChangeOrder'))
    _safe_collect(_collect_rfqs, project_id, entries_by_key, models.get('SubcontractorRFQ'), Company)
    _safe_collect(_collect_bid_invitations, project_id, entries_by_key, models.get('BidPackage'), models.get('BidInvitation'))

    def sort_key(entry):
        role = (entry.get('role') or '').strip().lower().replace(' ', '_')
        tier = ROLE_SORT_ORDER.get(role, 50)
        company = (entry.get('company') or entry.get('firm') or '').lower()
        return (tier, company, (entry.get('name') or '').lower())

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
