"""Project team / contact rows stored in project details_json."""
from __future__ import annotations

import json

TEAM_ROLES = (
    'owner',
    'architect',
    'project_manager',
    'superintendent',
    'estimator',
    'custom',
)

ROLE_LABELS = {
    'owner': 'Owner Contact',
    'architect': 'Architect',
    'project_manager': 'Project Manager',
    'superintendent': 'Superintendent',
    'estimator': 'Estimator',
    'custom': 'Other Role',
}


def _blank(contact):
    return not any([
        (contact.get('name') or '').strip(),
        (contact.get('email') or '').strip(),
        (contact.get('phone') or '').strip(),
        (contact.get('firm') or '').strip(),
        contact.get('user_id'),
    ])


def normalize_team_contact(raw):
    role = (raw.get('role') or 'custom').strip().lower().replace(' ', '_')
    if role not in TEAM_ROLES:
        role = 'custom'
    user_id = raw.get('user_id')
    try:
        user_id = int(user_id) if user_id not in (None, '', 0) else None
    except (TypeError, ValueError):
        user_id = None
    return {
        'role': role,
        'role_label': (raw.get('role_label') or ROLE_LABELS.get(role, 'Contact')).strip(),
        'user_id': user_id,
        'name': (raw.get('name') or '').strip(),
        'email': (raw.get('email') or '').strip(),
        'phone': (raw.get('phone') or '').strip(),
        'firm': (raw.get('firm') or '').strip(),
    }


def parse_team_contacts_json(value):
    if not value:
        return []
    if isinstance(value, list):
        data = value
    else:
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        contact = normalize_team_contact(item)
        if not _blank(contact):
            out.append(contact)
    return out


def migrate_legacy_team_contacts(details):
    """Build team_contacts from legacy single-value fields when needed."""
    existing = details.get('team_contacts')
    if isinstance(existing, list) and existing:
        return parse_team_contacts_json(existing)

    contacts = []
    if details.get('owner_contact_name') or details.get('owner_contact_email') or details.get('owner_contact_phone'):
        contacts.append(normalize_team_contact({
            'role': 'owner',
            'name': details.get('owner_contact_name', ''),
            'email': details.get('owner_contact_email', ''),
            'phone': details.get('owner_contact_phone', ''),
        }))
    if details.get('architect_firm') or details.get('architect_contact'):
        contacts.append(normalize_team_contact({
            'role': 'architect',
            'firm': details.get('architect_firm', ''),
            'name': details.get('architect_contact', ''),
        }))
    if details.get('superintendent'):
        contacts.append(normalize_team_contact({
            'role': 'superintendent',
            'name': details.get('superintendent', ''),
        }))
    if details.get('estimator'):
        contacts.append(normalize_team_contact({
            'role': 'estimator',
            'name': details.get('estimator', ''),
        }))
    return contacts


def primary_project_manager_name(contacts, fallback=''):
    for c in contacts:
        if c.get('role') == 'project_manager' and c.get('name'):
            return c['name']
    return fallback or ''


def sync_legacy_team_fields(details, contacts):
    """Keep legacy scalar fields in sync for older consumers."""
    owners = [c for c in contacts if c.get('role') == 'owner']
    architects = [c for c in contacts if c.get('role') == 'architect']
    supers = [c for c in contacts if c.get('role') == 'superintendent']
    estimators = [c for c in contacts if c.get('role') == 'estimator']

    if owners:
        o = owners[0]
        details['owner_contact_name'] = o.get('name', '')
        details['owner_contact_email'] = o.get('email', '')
        details['owner_contact_phone'] = o.get('phone', '')
    if architects:
        a = architects[0]
        details['architect_firm'] = a.get('firm', '')
        details['architect_contact'] = a.get('name', '')
    if supers:
        details['superintendent'] = supers[0].get('name', '')
    if estimators:
        details['estimator'] = estimators[0].get('name', '')
    details['team_contacts'] = contacts
    return details
