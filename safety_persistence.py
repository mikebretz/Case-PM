"""Safety module persistence — observations/incidents + personnel OSHA training."""
from __future__ import annotations

import json
from datetime import date, datetime

REPORT_TYPES = ('Observation', 'Near Miss', 'Incident', 'Injury', 'Property Damage', 'Toolbox Talk', 'Inspection', 'Violation')
SEVERITIES = ('Low', 'Medium', 'High', 'Critical')
REPORT_STATUSES = ('Open', 'Under Investigation', 'Corrective Action', 'Closed')

# Common personnel training/certification types tracked in the field.
CERT_TYPES = (
    'OSHA 10', 'OSHA 30', 'First Aid', 'CPR', 'CPR/AED', 'Bloodborne Pathogens',
    'Competent Person - Fall Protection', 'Competent Person - Excavation',
    'Competent Person - Scaffold', 'Confined Space', 'Aerial/Scissor Lift',
    'Forklift / Powered Industrial Truck', 'Rigging & Signaling', 'Crane Operator (NCCCO)',
    'Silica Awareness', 'HAZWOPER', 'Fire Watch', 'Flagger', 'Lockout/Tagout', 'Other',
)

OPEN_REPORT_STATUSES = ('Open', 'Under Investigation', 'Corrective Action')


def _parse(value, default):
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else default
    except (TypeError, json.JSONDecodeError):
        return default


def _looks_like_image(att):
    name = (att.get('original_name') or att.get('filename') or '').lower()
    return name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic'))


def serialize_report(r, User=None, url_helpers=None, summary=False):
    attachments = _parse(getattr(r, 'attachments_json', None), [])
    photos = [a for a in attachments if a.get('kind') == 'photo' or _looks_like_image(a)]
    status = r.status or 'Open'
    author = ''
    if User is not None and r.reported_by_id:
        u = User.query.get(r.reported_by_id)
        if u:
            author = f'{u.first_name} {u.last_name}'.strip()
    rdate = getattr(r, 'report_date', None) or (r.created_at.date() if r.created_at else None)
    base = {
        'id': r.id,
        'number': r.number,
        'project_id': r.project_id,
        'type': r.type,
        'description': r.description,
        'location': r.location,
        'severity': r.severity or 'Medium',
        'status': status,
        'is_open': status in OPEN_REPORT_STATUSES,
        'assigned_to': r.assigned_to,
        'due_date': r.due_date.isoformat() if r.due_date else None,
        'report_date': rdate.isoformat() if rdate else None,
        'reported_by': author,
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'photo_count': len(photos),
    }
    if summary:
        return base
    if url_helpers:
        for a in attachments:
            if a.get('document_id') and url_helpers.get('doc'):
                a['url'] = url_helpers['doc'](a['document_id'])
            elif a.get('filename') and url_helpers.get('attachment'):
                a['url'] = url_helpers['attachment'](r.id, a['filename'])
    base.update({
        'immediate_actions': r.immediate_actions,
        'root_cause': r.root_cause,
        'corrective_actions': r.corrective_actions,
        'attachments': attachments,
        'photos': photos,
    })
    return base


def report_stats(SafetyReport, project_id):
    q = SafetyReport.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    rows = q.all()
    today = date.today()
    year_start = date(today.year, 1, 1)

    def is_type(r, *names):
        return (r.type or '').lower() in [n.lower() for n in names]

    incidents = [r for r in rows if is_type(r, 'Incident', 'Injury', 'Property Damage')]
    last_incident = None
    for r in incidents:
        d = getattr(r, 'report_date', None) or (r.created_at.date() if r.created_at else None)
        if d and (last_incident is None or d > last_incident):
            last_incident = d
    days_without = (today - last_incident).days if last_incident else None

    return {
        'total': len(rows),
        'open': sum(1 for r in rows if (r.status or 'Open') in OPEN_REPORT_STATUSES),
        'incidents_ytd': sum(1 for r in incidents if (getattr(r, 'report_date', None) or (r.created_at.date() if r.created_at else today)) >= year_start),
        'near_misses': sum(1 for r in rows if is_type(r, 'Near Miss')),
        'observations': sum(1 for r in rows if is_type(r, 'Observation')),
        'days_without_incident': days_without,
    }


# ---------------- Certifications ----------------

def serialize_cert(c, url_helpers=None, summary=False):
    exp = c.expiration_date
    today = date.today()
    days_left = (exp - today).days if exp else None
    if exp is None:
        cstatus = 'Valid'
    elif exp < today:
        cstatus = 'Expired'
    elif days_left is not None and days_left <= 30:
        cstatus = 'Expiring Soon'
    else:
        cstatus = 'Valid'
    attachments = _parse(getattr(c, 'attachments_json', None), [])
    base = {
        'id': c.id,
        'project_id': c.project_id,
        'person_name': c.person_name,
        'company': c.company,
        'trade': c.trade,
        'cert_type': c.cert_type,
        'issuer': c.issuer,
        'card_number': c.card_number,
        'issued_date': c.issued_date.isoformat() if c.issued_date else None,
        'expiration_date': exp.isoformat() if exp else None,
        'days_left': days_left,
        'cert_status': cstatus,
        'notes': c.notes,
    }
    if summary:
        return base
    if url_helpers:
        for a in attachments:
            if a.get('document_id') and url_helpers.get('doc'):
                a['url'] = url_helpers['doc'](a['document_id'])
    base['attachments'] = attachments
    return base


def cert_stats(SafetyCertification, project_id):
    q = SafetyCertification.query
    if project_id:
        q = q.filter(
            (SafetyCertification.project_id == int(project_id)) | (SafetyCertification.project_id.is_(None))
        )
    rows = q.all()
    today = date.today()
    expired = expiring = valid = 0
    people = set()
    osha_trained = 0
    for c in rows:
        people.add((c.person_name or '').strip().lower())
        exp = c.expiration_date
        if exp and exp < today:
            expired += 1
        elif exp and (exp - today).days <= 30:
            expiring += 1
        else:
            valid += 1
        if (c.cert_type or '').startswith('OSHA'):
            osha_trained += 1
    return {
        'total': len(rows),
        'people': len([p for p in people if p]),
        'expired': expired,
        'expiring_soon': expiring,
        'valid': valid,
        'osha_certs': osha_trained,
    }
