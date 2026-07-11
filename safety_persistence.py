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

INJURY_ILLNESS_TYPES = (
    'Injury', 'Illness', 'Near Miss — No Injury', 'Property Damage Only', 'Environmental',
)
BODY_PARTS = (
    'Head', 'Eye(s)', 'Neck', 'Shoulder', 'Arm', 'Hand/Wrist', 'Back', 'Chest', 'Abdomen',
    'Hip', 'Leg', 'Knee', 'Ankle/Foot', 'Multiple', 'Internal', 'Other',
)
MEDICAL_TREATMENT_LEVELS = (
    'No Treatment', 'First Aid Only', 'Medical Treatment Beyond First Aid',
    'Emergency Room', 'Hospitalized Overnight', 'Fatality',
)
OSHA_RECORDABLE_OPTIONS = ('Yes', 'No', 'Under Review', 'Pending Determination')

# OSHA Form 301 / employer first report of injury — field groups for UI + details_json.
INCIDENT_FIELD_GROUPS = [
    {
        'key': 'when_where',
        'label': 'When & Where',
        'fields': [
            {'key': 'incident_date', 'label': 'Incident date', 'type': 'date'},
            {'key': 'incident_time', 'label': 'Incident time', 'type': 'time'},
            {'key': 'reported_datetime', 'label': 'Date/time reported to supervisor', 'type': 'text'},
            {'key': 'reported_to', 'label': 'Reported to (name/title)', 'type': 'text'},
            {'key': 'site_address', 'label': 'Job site / facility address', 'type': 'text'},
            {'key': 'specific_location', 'label': 'Specific location on site', 'type': 'text'},
            {'key': 'weather_conditions', 'label': 'Weather conditions', 'type': 'text'},
            {'key': 'lighting_conditions', 'label': 'Lighting / visibility', 'type': 'text'},
        ],
    },
    {
        'key': 'employee',
        'label': 'Employee / Involved Person',
        'fields': [
            {'key': 'employee_name', 'label': 'Full name', 'type': 'text'},
            {'key': 'employee_job_title', 'label': 'Job title / trade', 'type': 'text'},
            {'key': 'employee_department', 'label': 'Department / crew', 'type': 'text'},
            {'key': 'employee_supervisor', 'label': 'Supervisor', 'type': 'text'},
            {'key': 'employee_phone', 'label': 'Phone', 'type': 'text'},
            {'key': 'employee_hire_date', 'label': 'Date of hire', 'type': 'date'},
            {'key': 'contractor_company', 'label': 'Employer / subcontractor', 'type': 'text'},
            {'key': 'years_experience', 'label': 'Years experience (trade/task)', 'type': 'text'},
        ],
    },
    {
        'key': 'incident',
        'label': 'What Happened',
        'fields': [
            {'key': 'activity_before_incident', 'label': 'Activity before incident', 'type': 'textarea'},
            {'key': 'incident_narrative', 'label': 'Detailed description of incident', 'type': 'textarea'},
            {'key': 'injury_illness_type', 'label': 'Injury or illness type', 'type': 'select', 'options': list(INJURY_ILLNESS_TYPES)},
            {'key': 'body_part_affected', 'label': 'Body part(s) affected', 'type': 'select', 'options': list(BODY_PARTS)},
            {'key': 'nature_of_injury', 'label': 'Nature of injury (cut, fracture, sprain, etc.)', 'type': 'text'},
            {'key': 'object_substance', 'label': 'Object or substance that harmed employee', 'type': 'text'},
            {'key': 'equipment_involved', 'label': 'Equipment / tools involved', 'type': 'text'},
            {'key': 'ppe_in_use', 'label': 'PPE in use at time of incident', 'type': 'text'},
        ],
    },
    {
        'key': 'witnesses',
        'label': 'Witnesses & Statements',
        'fields': [
            {'key': 'witnesses', 'label': 'Witness names & contact info', 'type': 'textarea'},
            {'key': 'witness_statements', 'label': 'Witness statements summary', 'type': 'textarea'},
            {'key': 'employee_statement', 'label': 'Employee / injured person statement', 'type': 'textarea'},
            {'key': 'supervisor_statement', 'label': 'Supervisor statement', 'type': 'textarea'},
        ],
    },
    {
        'key': 'medical',
        'label': 'Medical Treatment',
        'fields': [
            {'key': 'medical_treatment', 'label': 'Treatment level', 'type': 'select', 'options': list(MEDICAL_TREATMENT_LEVELS)},
            {'key': 'medical_facility', 'label': 'Hospital / clinic name', 'type': 'text'},
            {'key': 'physician_name', 'label': 'Physician / provider', 'type': 'text'},
            {'key': 'treatment_date', 'label': 'Date of treatment', 'type': 'date'},
            {'key': 'days_away_from_work', 'label': 'Days away from work (OSHA 300)', 'type': 'number'},
            {'key': 'days_restricted_duty', 'label': 'Days restricted / transfer', 'type': 'number'},
            {'key': 'date_returned_to_work', 'label': 'Date returned to work', 'type': 'date'},
            {'key': 'fatal', 'label': 'Fatality', 'type': 'checkbox'},
            {'key': 'hospitalized', 'label': 'Hospitalized overnight', 'type': 'checkbox'},
        ],
    },
    {
        'key': 'investigation',
        'label': 'Investigation',
        'fields': [
            {'key': 'contributing_factors', 'label': 'Contributing factors', 'type': 'textarea'},
            {'key': 'unsafe_acts', 'label': 'Unsafe acts identified', 'type': 'textarea'},
            {'key': 'unsafe_conditions', 'label': 'Unsafe conditions identified', 'type': 'textarea'},
            {'key': 'ergonomic_factors', 'label': 'Ergonomic factors', 'type': 'textarea'},
            {'key': 'prevention_recommendations', 'label': 'Prevention recommendations', 'type': 'textarea'},
            {'key': 'property_damage_estimate', 'label': 'Property damage estimate ($)', 'type': 'text'},
            {'key': 'estimated_downtime_hours', 'label': 'Estimated downtime (hours)', 'type': 'text'},
            {'key': 'police_report_number', 'label': 'Police / agency report #', 'type': 'text'},
        ],
    },
    {
        'key': 'osha_insurance',
        'label': 'OSHA & Insurance',
        'fields': [
            {'key': 'osha_recordable', 'label': 'OSHA recordable?', 'type': 'select', 'options': list(OSHA_RECORDABLE_OPTIONS)},
            {'key': 'osha_form_301_complete', 'label': 'OSHA Form 301 completed', 'type': 'checkbox'},
            {'key': 'osha_log_entry_complete', 'label': 'OSHA 300 log entry complete', 'type': 'checkbox'},
            {'key': 'osha_report_number', 'label': 'OSHA / state report number', 'type': 'text'},
            {'key': 'insurance_carrier', 'label': 'Insurance carrier', 'type': 'text'},
            {'key': 'insurance_claim_number', 'label': 'Claim number', 'type': 'text'},
            {'key': 'insurance_notified', 'label': 'Carrier notified', 'type': 'checkbox'},
            {'key': 'insurance_notified_date', 'label': 'Date carrier notified', 'type': 'date'},
            {'key': 'workers_comp_claim_filed', 'label': 'Workers comp claim filed', 'type': 'checkbox'},
        ],
    },
]

TRAINING_RESOURCE_LINKS = {
    'OSHA 10': {'label': 'OSHA Outreach Training', 'url': 'https://www.osha.gov/training/outreach'},
    'OSHA 30': {'label': 'OSHA Outreach Training', 'url': 'https://www.osha.gov/training/outreach'},
    'First Aid': {'label': 'American Red Cross Training', 'url': 'https://www.redcross.org/take-a-class'},
    'CPR': {'label': 'American Red Cross CPR', 'url': 'https://www.redcross.org/take-a-class/cpr'},
    'CPR/AED': {'label': 'American Red Cross CPR/AED', 'url': 'https://www.redcross.org/take-a-class/cpr'},
    'Aerial/Scissor Lift': {'label': 'OSHA Aerial Lifts eTool', 'url': 'https://www.osha.gov/etools/aerial-lifts'},
    'Forklift / Powered Industrial Truck': {'label': 'OSHA Powered Industrial Trucks', 'url': 'https://www.osha.gov/powered-industrial-trucks'},
    'Silica Awareness': {'label': 'OSHA Silica Standard', 'url': 'https://www.osha.gov/silica-crystalline-construction'},
    'HAZWOPER': {'label': 'OSHA HAZWOPER', 'url': 'https://www.osha.gov/hazwoper'},
}


def default_incident_details():
    details = {}
    for group in INCIDENT_FIELD_GROUPS:
        for f in group['fields']:
            if f['type'] == 'checkbox':
                details[f['key']] = False
            else:
                details[f['key']] = ''
    return details


def build_details(body):
    """Merge incident detail fields from API body into details_json dict."""
    incoming = body.get('details') if isinstance(body.get('details'), dict) else {}
    details = default_incident_details()
    for key in details:
        if key in incoming:
            val = incoming[key]
            if isinstance(details[key], bool):
                details[key] = bool(val)
            else:
                details[key] = val if val is not None else ''
    return details


def parse_details(report):
    stored = _parse(getattr(report, 'details_json', None), {})
    base = default_incident_details()
    base.update({k: stored.get(k, v) for k, v in base.items()})
    return base


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
        'details': parse_details(r),
    })
    return base


def serialize_training_event(ev):
    return {
        'id': ev.id,
        'project_id': ev.project_id,
        'cert_id': ev.cert_id,
        'person_name': ev.person_name,
        'company': ev.company,
        'cert_type': ev.cert_type,
        'event_type': ev.event_type or 'scheduled_training',
        'event_date': ev.event_date.isoformat() if ev.event_date else None,
        'training_url': ev.training_url,
        'training_provider': ev.training_provider,
        'notes': ev.notes,
        'status': ev.status or 'Scheduled',
        'notify_user_id': ev.notify_user_id,
        'internal_task_sent': bool(ev.internal_task_sent),
        'created_at': ev.created_at.isoformat() if ev.created_at else None,
    }


def calendar_events_from_certs(certs):
    """Build calendar entries from certification expiration dates."""
    events = []
    for c in certs:
        if not c.expiration_date:
            continue
        exp = c.expiration_date
        today = date.today()
        days_left = (exp - today).days
        if exp < today:
            status = 'expired'
        elif days_left <= 30:
            status = 'expiring'
        else:
            status = 'valid'
        events.append({
            'id': f'cert-{c.id}',
            'source': 'certification',
            'cert_id': c.id,
            'event_type': 'expiration',
            'event_date': exp.isoformat(),
            'person_name': c.person_name,
            'company': c.company,
            'cert_type': c.cert_type,
            'status': status,
            'title': f'{c.cert_type} expires — {c.person_name}',
        })
    return events


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
