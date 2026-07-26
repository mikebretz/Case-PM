"""Project-scoped directory entries and workflow notification targets."""
from __future__ import annotations

from project_team_persistence import ROLE_LABELS, migrate_legacy_team_contacts

import json
import re


def _db_session():
    try:
        from case_workflow import _workflow_session
        return _workflow_session()
    except Exception:
        pass
    try:
        import sys
        app_mod = sys.modules.get('app')
        if app_mod is not None and getattr(app_mod, 'db', None) is not None:
            return app_mod.db.session
    except Exception:
        pass
    return None


def _model_query(model):
    query = getattr(model, 'query', None)
    if query is not None and getattr(model, '__fsa__', None) is None:
        return query
    session = _db_session()
    if session is None:
        raise RuntimeError('Database session not available')
    return session.query(model)

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

SOURCE_LABELS = {
    'membership': 'Project team',
    'team_contact': 'Team contact',
    'project': 'Project record',
    'client_company': 'Owner / client',
    'commitment': 'Commitment',
    'pay_app_sov': 'Pay app / SOV',
    'submittal': 'Submittal',
    'change_order': 'Change order',
    'rfq': 'RFQ',
    'bid_invitation': 'Bid invitation',
    'rfi': 'RFI',
    'punch': 'Punch list',
    'schedule': 'Schedule',
    'schedule_task': 'Schedule task',
    'meeting': 'Meeting',
    'permit': 'Permits & inspections',
    'safety': 'Safety',
    'delivery': 'Delivery',
    'staff': 'Company staff',
}

ON_PROJECT_SOURCES = frozenset({
    'membership',
    'team_contact',
    'project',
    'client_company',
})

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
        row = _model_query(Company).get(int(company_id))
        return (row.name if row else '') or ''
    except Exception:
        return ''


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _source_list(entry):
    sources = entry.get('sources')
    if isinstance(sources, list):
        return [s for s in sources if s]
    src = (entry.get('source') or '').strip()
    return [src] if src else []


def _annotate_directory_entry(entry):
    sources = _source_list(entry)
    entry['sources'] = sources
    entry['source_labels'] = [
        SOURCE_LABELS.get(src, src.replace('_', ' ').title())
        for src in sources
    ]
    entry['on_project'] = bool(set(sources) & ON_PROJECT_SOURCES)
    if len(sources) == 1:
        entry['source'] = sources[0]
    elif len(sources) > 1:
        entry['source'] = 'multiple'
    return _finalize_directory_entry(entry)


def _split_party_names(value):
    text = (value or '').strip()
    if not text:
        return []
    parts = re.split(r'[,;/]+', text)
    return [part.strip() for part in parts if part.strip()]


def _user_directory_row(user, *, role='', role_label='', company='', source='membership', team_position=''):
    name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
    company_name = (company or getattr(user, 'company', None) or '').strip()
    job_title = _user_job_title(user)
    team_pos = (team_position or role_label or '').strip()
    if team_pos in SYSTEM_ACCOUNT_ROLES and not job_title:
        team_pos = ''
    position = _resolve_position(job_title=job_title, team_position=team_pos)
    return _annotate_directory_entry({
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
        'sources': [source] if source else [],
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
    return _annotate_directory_entry({
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
        'sources': [source] if source else [],
    })


def _contact_directory_row(contact, source='team_contact'):
    firm = (contact.get('firm') or '').strip()
    team_position = (contact.get('role_label') or ROLE_LABELS.get(contact.get('role'), 'Contact')).strip()
    return _annotate_directory_entry({
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
        'sources': [source] if source else [],
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
    merged_sources = set(_source_list(merged)) | set(_source_list(incoming))
    merged['sources'] = sorted(merged_sources)
    if len(merged['sources']) == 1:
        merged['source'] = merged['sources'][0]
    elif len(merged['sources']) > 1:
        merged['source'] = 'multiple'
    return _annotate_directory_entry(merged)


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
            Delivery,
            Estimate,
            MeetingActionItem,
            MeetingMinute,
            PayAppProjectState,
            PermitInspectionItem,
            PunchItem,
            RFI,
            SafetyCertification,
            SafetyReport,
            SafetyTrainingEvent,
            ScheduleData,
            ScheduleTask,
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
            'RFI': RFI,
            'PunchItem': PunchItem,
            'ScheduleData': ScheduleData,
            'ScheduleTask': ScheduleTask,
            'MeetingMinute': MeetingMinute,
            'MeetingActionItem': MeetingActionItem,
            'PermitInspectionItem': PermitInspectionItem,
            'SafetyReport': SafetyReport,
            'SafetyCertification': SafetyCertification,
            'SafetyTrainingEvent': SafetyTrainingEvent,
            'Delivery': Delivery,
        }
    except Exception:
        return {}


def _collect_membership_and_team(project, User, Company, ProjectMembership, entries_by_key):
    from project_access import _membership_model

    PM = ProjectMembership or _membership_model()
    if PM is not None:
        for row in _model_query(PM).filter_by(project_id=int(project.id)).all():
            user = _model_query(User).get(row.user_id)
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
            user = _model_query(User).get(int(contact['user_id']))
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
        client_company = _model_query(Company).get(int(client_company_id))
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
    for commitment in _model_query(Commitment).filter_by(project_id=int(project_id)).all():
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

    db_ext = None
    try:
        from case_workflow import _workflow_db
        db_ext = _workflow_db()
    except Exception:
        pass

    try:
        _record, state = get_pay_app_state(PayAppProjectState, int(project_id), db=db_ext)
    except Exception:
        return
    if not state:
        return
    sub_status = state.get('subSOVStatus') or {}
    if not isinstance(sub_status, dict):
        return
    commitments = _model_query(Commitment).filter_by(project_id=int(project_id)).all() if Commitment is not None else []

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
    for submittal in _model_query(Submittal).filter_by(project_id=int(project_id)).all():
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
            user = _model_query(User).get(int(contact_uid))
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
    for co in _model_query(ChangeOrder).filter_by(project_id=int(project_id)).all():
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
    for rfq in _model_query(SubcontractorRFQ).filter_by(project_id=int(project_id)).all():
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
    package_ids = [p.id for p in _model_query(BidPackage).filter_by(project_id=int(project_id)).all()]
    if not package_ids:
        return
    seen = set()
    for invite in _model_query(BidInvitation).filter(BidInvitation.bid_package_id.in_(package_ids)).all():
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


def _collect_rfis(project_id, entries_by_key, User, RFI):
    if RFI is None:
        return
    try:
        from rfi_persistence import normalize_party_list
    except Exception:
        return
    seen = set()
    for rfi in _model_query(RFI).filter_by(project_id=int(project_id)).all():
        number = (getattr(rfi, 'number', None) or '').strip()
        role_suffix = f' {number}' if number else ''

        manager_uid = getattr(rfi, 'rfi_manager_user_id', None)
        manager_name = (getattr(rfi, 'rfi_manager_name', None) or '').strip()
        if manager_uid:
            user = _model_query(User).get(int(manager_uid))
            if user and (getattr(user, 'status', 'Active') or 'Active') == 'Active':
                key = ('user', int(manager_uid))
                if key not in seen:
                    seen.add(key)
                    _add_entry(entries_by_key, _user_directory_row(
                        user,
                        role='consultant',
                        team_position=f'RFI Manager{role_suffix}',
                        company=getattr(user, 'company', '') or '',
                        source='rfi',
                    ))
        elif manager_name:
            key = ('name', manager_name.lower(), 'rfi_manager')
            if key not in seen:
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=manager_name,
                    role='consultant',
                    position=f'RFI Manager{role_suffix}',
                    source='rfi',
                ))

        for party in normalize_party_list(_parse_json(getattr(rfi, 'assignees_json', None), [])):
            uid = party.get('user_id')
            name = (party.get('name') or '').strip()
            if uid:
                user = _model_query(User).get(int(uid))
                if user and (getattr(user, 'status', 'Active') or 'Active') == 'Active':
                    key = ('user', int(uid))
                    if key in seen:
                        continue
                    seen.add(key)
                    _add_entry(entries_by_key, _user_directory_row(
                        user,
                        role='consultant',
                        team_position=f'RFI Assignee{role_suffix}',
                        company=getattr(user, 'company', '') or '',
                        source='rfi',
                    ))
                    continue
            if name:
                key = ('name', name.lower(), 'rfi_assignee')
                if key in seen:
                    continue
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=name,
                    role='consultant',
                    position=f'RFI Assignee{role_suffix}',
                    source='rfi',
                ))

        for party in normalize_party_list(_parse_json(getattr(rfi, 'distribution_json', None), [])):
            uid = party.get('user_id')
            name = (party.get('name') or '').strip()
            if uid:
                user = _model_query(User).get(int(uid))
                if user and (getattr(user, 'status', 'Active') or 'Active') == 'Active':
                    key = ('user', int(uid))
                    if key in seen:
                        continue
                    seen.add(key)
                    _add_entry(entries_by_key, _user_directory_row(
                        user,
                        role='consultant',
                        team_position=f'RFI Distribution{role_suffix}',
                        company=getattr(user, 'company', '') or '',
                        source='rfi',
                    ))
                    continue
            if name:
                key = ('name', name.lower(), 'rfi_distribution')
                if key in seen:
                    continue
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=name,
                    role='consultant',
                    position=f'RFI Distribution{role_suffix}',
                    source='rfi',
                ))

        for company_name, contact_name in (
            (getattr(rfi, 'responsible_contractor', None), ''),
            (getattr(rfi, 'received_from_company', None), getattr(rfi, 'received_from_contact', None)),
        ):
            company_name = (company_name or '').strip()
            contact_name = (contact_name or '').strip()
            if not company_name and not contact_name:
                continue
            key = ('company', company_name.lower(), contact_name.lower())
            if key in seen:
                continue
            seen.add(key)
            _add_entry(entries_by_key, _person_directory_row(
                name=contact_name or company_name,
                role='vendor_contact',
                position=f'RFI Contact{role_suffix}',
                company=company_name or contact_name,
                source='rfi',
            ))


def _collect_punch_items(project_id, entries_by_key, PunchItem):
    if PunchItem is None:
        return
    seen = set()
    for item in _model_query(PunchItem).filter_by(project_id=int(project_id)).all():
        number = (getattr(item, 'number', None) or '').strip()
        role_suffix = f' {number}' if number else ''
        company_name = (getattr(item, 'assigned_company', None) or '').strip()
        assignee = (getattr(item, 'assigned_to', None) or '').strip()
        if assignee or company_name:
            key = (assignee.lower(), company_name.lower())
            if key not in seen:
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=assignee or company_name,
                    role='vendor_contact',
                    position=f'Punch Assignee{role_suffix}',
                    company=company_name,
                    source='punch',
                ))


def _collect_schedule_resources(project_id, entries_by_key, ScheduleData, ScheduleTask):
    seen = set()
    if ScheduleData is not None:
        record = _model_query(ScheduleData).filter_by(project_id=int(project_id)).first()
        if record and getattr(record, 'payload', None):
            payload = _parse_json(record.payload, {})
            tasks = payload.get('data') if isinstance(payload, dict) else []
            if not isinstance(tasks, list):
                tasks = []
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                activity = (task.get('activity_id') or task.get('text') or '').strip()
                suffix = f' — {activity}' if activity else ''
                for field, position in (('resource', 'Schedule Resource'), ('owner', 'Schedule Responsible')):
                    for part in _split_party_names(task.get(field)):
                        key = (field, part.lower())
                        if key in seen:
                            continue
                        seen.add(key)
                        _add_entry(entries_by_key, _person_directory_row(
                            name=part,
                            role='vendor_contact',
                            position=f'{position}{suffix}',
                            company=part if field == 'owner' else '',
                            source='schedule',
                        ))
    if ScheduleTask is not None:
        for task in _model_query(ScheduleTask).filter_by(project_id=int(project_id)).all():
            assignee = (getattr(task, 'assigned_to', None) or '').strip()
            if not assignee:
                continue
            number = (getattr(task, 'number', None) or '').strip()
            suffix = f' {number}' if number else ''
            key = ('task', assignee.lower())
            if key in seen:
                continue
            seen.add(key)
            _add_entry(entries_by_key, _person_directory_row(
                name=assignee,
                role='vendor_contact',
                position=f'Schedule Task{suffix}',
                source='schedule_task',
            ))


def _collect_meetings(project_id, entries_by_key, MeetingMinute, MeetingActionItem):
    if MeetingMinute is None:
        return
    seen = set()
    for meeting in _model_query(MeetingMinute).filter_by(project_id=int(project_id)).all():
        number = (getattr(meeting, 'meeting_number', None) or '').strip()
        suffix = f' {number}' if number else ''
        organizer = (getattr(meeting, 'organizer', None) or '').strip()
        if organizer:
            key = ('organizer', organizer.lower())
            if key not in seen:
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=organizer,
                    role='consultant',
                    position=f'Meeting Organizer{suffix}',
                    source='meeting',
                ))
        for attendee in _parse_json(getattr(meeting, 'attendees_json', None), []):
            if isinstance(attendee, str):
                name = attendee.strip()
                company = ''
            elif isinstance(attendee, dict):
                name = (attendee.get('name') or '').strip()
                company = (attendee.get('company') or '').strip()
            else:
                continue
            if not name:
                continue
            key = ('attendee', name.lower(), company.lower())
            if key in seen:
                continue
            seen.add(key)
            _add_entry(entries_by_key, _person_directory_row(
                name=name,
                role='consultant',
                position=f'Meeting Attendee{suffix}',
                company=company,
                source='meeting',
            ))
        if MeetingActionItem is not None:
            for action in _model_query(MeetingActionItem).filter_by(meeting_id=int(meeting.id)).all():
                assignee = (getattr(action, 'assigned_to', None) or '').strip()
                if not assignee:
                    continue
                key = ('action', assignee.lower())
                if key in seen:
                    continue
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=assignee,
                    role='consultant',
                    position=f'Meeting Action Item{suffix}',
                    source='meeting',
                ))


def _collect_permits(project_id, entries_by_key, PermitInspectionItem):
    if PermitInspectionItem is None:
        return
    seen = set()
    for item in _model_query(PermitInspectionItem).filter_by(project_id=int(project_id)).all():
        inspector = (getattr(item, 'inspector', None) or '').strip()
        authority = (getattr(item, 'authority_name', None) or '').strip()
        jurisdiction = (getattr(item, 'jurisdiction_name', None) or '').strip()
        number = (getattr(item, 'item_number', None) or '').strip()
        suffix = f' {number}' if number else ''
        if inspector:
            key = ('inspector', inspector.lower())
            if key not in seen:
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=inspector,
                    role='consultant',
                    position=f'Inspector{suffix}',
                    company=authority or jurisdiction,
                    source='permit',
                ))
        if authority and authority.lower() != (inspector or '').lower():
            key = ('authority', authority.lower())
            if key not in seen:
                seen.add(key)
                _add_entry(entries_by_key, _person_directory_row(
                    name=authority,
                    role='vendor',
                    position=f'Permit Authority{suffix}',
                    company=authority,
                    source='permit',
                ))


def _collect_safety(project_id, entries_by_key, SafetyReport, SafetyCertification, SafetyTrainingEvent):
    seen = set()
    if SafetyReport is not None:
        for report in _model_query(SafetyReport).filter_by(project_id=int(project_id)).all():
            assignee = (getattr(report, 'assigned_to', None) or '').strip()
            if not assignee:
                continue
            key = ('report', assignee.lower())
            if key in seen:
                continue
            seen.add(key)
            _add_entry(entries_by_key, _person_directory_row(
                name=assignee,
                role='consultant',
                position='Safety Report Assignee',
                source='safety',
            ))
    if SafetyCertification is not None:
        for cert in _model_query(SafetyCertification).filter_by(project_id=int(project_id)).all():
            person = (getattr(cert, 'person_name', None) or '').strip()
            company = (getattr(cert, 'company', None) or '').strip()
            if not person:
                continue
            key = ('cert', person.lower(), company.lower())
            if key in seen:
                continue
            seen.add(key)
            _add_entry(entries_by_key, _person_directory_row(
                name=person,
                role='consultant',
                position='Safety Certification',
                company=company,
                source='safety',
            ))
    if SafetyTrainingEvent is not None:
        for event in _model_query(SafetyTrainingEvent).filter_by(project_id=int(project_id)).all():
            person = (getattr(event, 'person_name', None) or '').strip()
            company = (getattr(event, 'company', None) or '').strip()
            if not person:
                continue
            key = ('training', person.lower(), company.lower())
            if key in seen:
                continue
            seen.add(key)
            _add_entry(entries_by_key, _person_directory_row(
                name=person,
                role='consultant',
                position='Safety Training',
                company=company,
                source='safety',
            ))


def _collect_deliveries(project_id, entries_by_key, Delivery):
    if Delivery is None:
        return
    seen = set()
    for delivery in _model_query(Delivery).filter_by(project_id=int(project_id)).all():
        number = (getattr(delivery, 'delivery_number', None) or '').strip()
        suffix = f' {number}' if number else ''
        for field, position in (
            ('supplier', 'Delivery Supplier'),
            ('carrier', 'Delivery Carrier'),
            ('responsible', 'Delivery Responsible'),
            ('received_by', 'Delivery Receiver'),
        ):
            value = (getattr(delivery, field, None) or '').strip()
            if not value:
                continue
            key = (field, value.lower())
            if key in seen:
                continue
            seen.add(key)
            company = value if field == 'supplier' else ''
            _add_entry(entries_by_key, _person_directory_row(
                name=value,
                role='vendor_contact',
                position=f'{position}{suffix}',
                company=company,
                source='delivery',
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
    _safe_collect(_collect_rfis, project_id, entries_by_key, User, models.get('RFI'))
    _safe_collect(_collect_punch_items, project_id, entries_by_key, models.get('PunchItem'))
    _safe_collect(
        _collect_schedule_resources,
        project_id,
        entries_by_key,
        models.get('ScheduleData'),
        models.get('ScheduleTask'),
    )
    _safe_collect(
        _collect_meetings,
        project_id,
        entries_by_key,
        models.get('MeetingMinute'),
        models.get('MeetingActionItem'),
    )
    _safe_collect(_collect_permits, project_id, entries_by_key, models.get('PermitInspectionItem'))
    _safe_collect(
        _collect_safety,
        project_id,
        entries_by_key,
        models.get('SafetyReport'),
        models.get('SafetyCertification'),
        models.get('SafetyTrainingEvent'),
    )
    _safe_collect(_collect_deliveries, project_id, entries_by_key, models.get('Delivery'))

    def sort_key(entry):
        role = (entry.get('role') or '').strip().lower().replace(' ', '_')
        tier = ROLE_SORT_ORDER.get(role, 50)
        company = (entry.get('company') or entry.get('firm') or '').lower()
        return (tier, company, (entry.get('name') or '').lower())

    return sorted(entries_by_key.values(), key=sort_key)


def build_project_companies(directory):
    """Group directory people by company with merged attachment sources."""
    companies_by_key = {}
    for entry in directory or []:
        company_name = (entry.get('company') or entry.get('firm') or '').strip()
        if not company_name:
            continue
        key = company_name.lower()
        record = companies_by_key.get(key)
        if record is None:
            record = {
                'name': company_name,
                'sources': set(),
                'source_labels': [],
                'people_count': 0,
                'on_project': False,
                'people': [],
            }
            companies_by_key[key] = record
        for src in entry.get('sources') or _source_list(entry):
            if src:
                record['sources'].add(src)
        if entry.get('on_project'):
            record['on_project'] = True
        person_summary = {
            'name': entry.get('name') or '',
            'position': entry.get('position') or '',
            'email': entry.get('email') or '',
            'phone': entry.get('phone') or '',
            'on_project': bool(entry.get('on_project')),
            'source_labels': entry.get('source_labels') or [],
        }
        record['people'].append(person_summary)

    companies = []
    for record in companies_by_key.values():
        sources = sorted(record['sources'])
        record['sources'] = sources
        record['source_labels'] = [
            SOURCE_LABELS.get(src, src.replace('_', ' ').title())
            for src in sources
        ]
        record['people_count'] = len(record['people'])
        companies.append(record)

    return sorted(companies, key=lambda row: ((not row.get('on_project')), row.get('name', '').lower()))


def build_staff_directory(User):
    """Active main-company staff for the All Personnel view."""
    staff = []
    for user in _staff_portal_users(User):
        entry = _user_directory_row(
            user,
            role=getattr(user, 'role', '') or '',
            team_position=_user_job_title(user) or getattr(user, 'role', '') or '',
            company=getattr(user, 'company', '') or '',
            source='staff',
        )
        entry['group'] = 'staff'
        entry['on_project'] = False
        staff.append(entry)
    return staff


def build_project_directory_payload(project, User, Company=None, ProjectMembership=None):
    """Directory, companies, and staff roster for the project directory API."""
    directory = build_project_directory(project, User, Company=Company, ProjectMembership=ProjectMembership)
    companies = build_project_companies(directory)
    staff = build_staff_directory(User)

    project_user_ids = {
        int(entry['user_id'])
        for entry in directory
        if entry.get('user_id') is not None
    }
    project_emails = {
        (entry.get('email') or '').strip().lower()
        for entry in directory
        if (entry.get('email') or '').strip()
    }
    for person in staff:
        uid = person.get('user_id')
        email = (person.get('email') or '').strip().lower()
        if (uid is not None and int(uid) in project_user_ids) or (email and email in project_emails):
            person['on_project'] = True

    on_project_people = [entry for entry in directory if entry.get('on_project')]
    return {
        'directory': directory,
        'companies': companies,
        'staff': staff,
        'team_contacts': directory,
        'counts': {
            'directory': len(directory),
            'companies': len(companies),
            'staff': len(staff),
            'on_project': len(on_project_people),
        },
    }


def _active_project_users(project_id, User, ProjectMembership=None):
    from project_access import _membership_model

    PM = ProjectMembership or _membership_model()
    users = []
    seen = set()
    if PM is not None:
        for row in _model_query(PM).filter_by(project_id=int(project_id)).all():
            user = _model_query(User).get(row.user_id)
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
            project = _model_query(ProjectModel).get(int(project_id))
        if project is not None:
            details = project.get_details()
            for contact in migrate_legacy_team_contacts(details):
                uid = contact.get('user_id')
                if not uid or uid in seen:
                    continue
                user = _model_query(User).get(int(uid))
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


def _staff_portal_users(User):
    """Active users on the main company (staff portal), excluding vendor/sub portals."""
    from document_module_security import is_staff_portal_user

    users = []
    for user in _model_query(User).filter_by(status='Active').all():
        try:
            if is_staff_portal_user(user):
                users.append(user)
        except Exception:
            continue
    return sorted(
        users,
        key=lambda user: (
            (getattr(user, 'first_name', '') or '').lower(),
            (getattr(user, 'last_name', '') or '').lower(),
            (getattr(user, 'email', '') or '').lower(),
        ),
    )


def _contact_sort_key(contact):
    group_order = {'project': 0, 'staff': 1}
    company = (contact.get('company') or '').lower()
    name = (contact.get('name') or '').lower()
    return (group_order.get(contact.get('group') or 'project', 0), company, name)


def build_internal_message_contacts(
    project,
    User,
    Company=None,
    ProjectMembership=None,
    *,
    exclude_user_id=None,
):
    """
    Internal messaging contacts for non-staff users:
    everyone attached to the project plus main-company staff.
    """
    contacts_by_key = {}

    def add_contact(
        *,
        user_id=None,
        name='',
        email='',
        company='',
        phone='',
        position='',
        group='project',
    ):
        email_key = (email or '').strip().lower()
        if not email_key:
            return
        if exclude_user_id and user_id is not None and int(user_id) == int(exclude_user_id):
            return
        key = f'user:{user_id}' if user_id is not None else f'email:{email_key}'
        row = {
            'id': user_id,
            'user_id': user_id,
            'name': (name or email_key).strip(),
            'email': email_key,
            'company': (company or '').strip(),
            'phone': (phone or '').strip(),
            'position': (position or '').strip(),
            'group': group,
        }
        existing = contacts_by_key.get(key)
        if existing:
            for field in ('name', 'company', 'phone', 'position'):
                if not existing.get(field) and row.get(field):
                    existing[field] = row[field]
            if existing.get('group') != 'staff' and row.get('group') == 'staff':
                existing['group'] = 'staff'
            return
        contacts_by_key[key] = row

    if project is not None:
        directory = build_project_directory(project, User, Company=Company, ProjectMembership=ProjectMembership)
        for entry in directory:
            uid = entry.get('user_id')
            email = (entry.get('email') or '').strip()
            if not email:
                continue
            add_contact(
                user_id=uid,
                name=entry.get('name') or '',
                email=email,
                company=entry.get('company') or entry.get('firm') or '',
                phone=entry.get('phone') or '',
                position=entry.get('position') or '',
                group='project',
            )

    for user in _staff_portal_users(User):
        name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip()
        if not name:
            name = (getattr(user, 'full_name', None) or getattr(user, 'email', None) or '').strip()
        add_contact(
            user_id=getattr(user, 'id', None),
            name=name,
            email=(getattr(user, 'email', None) or '').strip(),
            company=(getattr(user, 'company', None) or '').strip(),
            phone=(getattr(user, 'phone', None) or '').strip(),
            position=_user_job_title(user),
            group='staff',
        )

    return sorted(contacts_by_key.values(), key=_contact_sort_key)


_EMAIL_RE = re.compile(r'[\w.+-]+@[\w.-]+\.\w+', re.I)


def parse_recipient_emails(*values):
    """Extract unique email addresses from compose To/Cc/Bcc strings."""
    emails = []
    seen = set()
    for value in values:
        chunks = value if isinstance(value, list) else re.split(r'[,;]', str(value or ''))
        for chunk in chunks:
            chunk = str(chunk or '').strip()
            if not chunk:
                continue
            match = _EMAIL_RE.search(chunk)
            if not match:
                continue
            email = match.group(0).lower()
            if email not in seen:
                seen.add(email)
                emails.append(email)
    return emails


def resolve_users_by_emails(emails, User):
    """Resolve active users from email addresses."""
    users = []
    seen = set()
    for email in emails or []:
        email_key = (email or '').strip().lower()
        if not email_key:
            continue
        user = None
        try:
            user = _model_query(User).filter_by(status='Active').filter(
                User.email.ilike(email_key),
            ).first()
        except Exception:
            for row in _model_query(User).filter_by(status='Active').all():
                if (getattr(row, 'email', None) or '').strip().lower() == email_key:
                    user = row
                    break
        if user and user.id not in seen:
            seen.add(user.id)
            users.append(user)
    return users


def validate_internal_message_recipients(sender, recipient_users, project, User, Company=None, *, ProjectMembership=None):
    """Non-staff senders may only message project contacts + main company staff."""
    from document_module_security import is_staff_portal_user
    from access_control import user_email_internal_only

    if is_staff_portal_user(sender) and not user_email_internal_only(sender):
        return True, None

    allowed = build_internal_message_contacts(
        project,
        User,
        Company=Company,
        ProjectMembership=ProjectMembership,
        exclude_user_id=None,
    )
    allowed_emails = {(c.get('email') or '').strip().lower() for c in allowed if c.get('email')}
    allowed_ids = set()
    for c in allowed:
        raw_id = c.get('user_id') if c.get('user_id') is not None else c.get('id')
        try:
            if raw_id is not None:
                allowed_ids.add(int(raw_id))
        except (TypeError, ValueError):
            continue
    for user in recipient_users:
        if int(user.id) == int(sender.id):
            continue
        email = (getattr(user, 'email', None) or '').strip().lower()
        if email not in allowed_emails and int(user.id) not in allowed_ids:
            label = getattr(user, 'full_name', None) or email or f'User #{user.id}'
            return False, f'You cannot message {label} on this project.'
    return True, None
