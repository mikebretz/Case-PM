"""Daily log persistence — structured field-report sections, stats, and serialization.

Feature set modeled on the most-used daily logs in Procore / Buildertrend / RedTeam:
manpower, equipment, deliveries, visitors, delays, safety, plus a free-form work
summary and notes. Structured sections that don't have dedicated tables are stored
in DailyLog.details_json so the log stays flexible and simple.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

# Sections stored inside details_json (manpower & equipment use their own tables).
DETAIL_SECTIONS = (
    'deliveries',      # [{item, supplier, quantity, notes}]
    'materials',       # [{material, supplier, quantity, unit, location}]
    'visitors',        # [{name, company, purpose, time}]
    'phone_calls',     # [{contact, company, subject, notes}]
    'delays',          # [{type, description, hours_lost}]
    'safety',          # [{type, description, action}]
    'accidents',       # [{person, company, description, treatment}]
    'inspections',     # [{type, agency, inspector, result, notes}]
    'quantities',      # [{description, quantity, unit, cost_code}]
    'dumpsters',       # [{type, size, hauler, hauls}]
    'scheduled_work',  # [{activity, status, notes}]
)

DELAY_TYPES = ('Weather', 'Labor Shortage', 'Material', 'Equipment', 'Owner', 'Design/RFI', 'Inspection', 'Utility', 'Other')
SAFETY_TYPES = ('Observation', 'Near Miss', 'Incident', 'Toolbox Talk', 'Violation', 'JHA/JSA', 'PPE Check')
INSPECTION_RESULTS = ('Pass', 'Fail', 'Partial', 'Pending', 'N/A')
SCHEDULED_WORK_STATUS = ('On Track', 'Ahead', 'Behind', 'Complete', 'Not Started')


def _parse(value, default):
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else default
    except (TypeError, json.JSONDecodeError):
        return default


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _as_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _clean_rows(rows, allowed_keys):
    """Keep only dict rows with at least one non-empty allowed value."""
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cleaned = {k: row.get(k) for k in allowed_keys}
        if any((v not in (None, '', 0) for v in cleaned.values())):
            out.append(cleaned)
    return out


def build_details(payload):
    """Normalize incoming structured sections into a details dict for details_json."""
    payload = payload or {}
    details = {
        'temperature': payload.get('temperature'),
        'temp_low': payload.get('temp_low'),
        'wind': payload.get('wind'),
        'humidity': payload.get('humidity'),
        'precipitation': payload.get('precipitation'),
        'ground_condition': payload.get('ground_condition'),
        'weather_impact': payload.get('weather_impact'),
        'work_hours': payload.get('work_hours'),
        'deliveries': _clean_rows(payload.get('deliveries'), ('item', 'supplier', 'quantity', 'notes')),
        'materials': _clean_rows(payload.get('materials'), ('material', 'supplier', 'quantity', 'unit', 'location')),
        'visitors': _clean_rows(payload.get('visitors'), ('name', 'company', 'purpose', 'time')),
        'phone_calls': _clean_rows(payload.get('phone_calls'), ('contact', 'company', 'subject', 'notes')),
        'delays': _clean_rows(payload.get('delays'), ('type', 'description', 'hours_lost')),
        'safety': _clean_rows(payload.get('safety'), ('type', 'description', 'action')),
        'accidents': _clean_rows(payload.get('accidents'), ('person', 'company', 'description', 'treatment')),
        'inspections': _clean_rows(payload.get('inspections'), ('type', 'agency', 'inspector', 'result', 'notes')),
        'quantities': _clean_rows(payload.get('quantities'), ('description', 'quantity', 'unit', 'cost_code')),
        'dumpsters': _clean_rows(payload.get('dumpsters'), ('type', 'size', 'hauler', 'hauls')),
        'scheduled_work': _clean_rows(payload.get('scheduled_work'), ('activity', 'status', 'notes')),
    }
    return details


def sync_manpower(db, ManpowerEntry, log_id, rows):
    """Replace manpower rows for a log (also feeds the dashboard's weekly hours)."""
    ManpowerEntry.query.filter_by(daily_log_id=log_id).delete()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        company = (row.get('company') or '').strip()
        workers = _as_int(row.get('personnel_count') or row.get('workers'))
        hours = _as_float(row.get('hours'))
        trade = (row.get('work_performed') or row.get('trade') or '').strip()
        if not company and not workers and not hours:
            continue
        db.session.add(ManpowerEntry(
            daily_log_id=log_id,
            company=company,
            personnel_count=workers,
            hours=hours,
            work_performed=trade,
        ))


def sync_equipment(db, EquipmentEntry, log_id, rows):
    EquipmentEntry.query.filter_by(daily_log_id=log_id).delete()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = (row.get('equipment_name') or row.get('name') or '').strip()
        qty = _as_int(row.get('quantity') or row.get('qty')) or 1
        condition = (row.get('condition') or '').strip()
        if not name:
            continue
        db.session.add(EquipmentEntry(
            daily_log_id=log_id,
            equipment_name=name,
            quantity=qty,
            condition=condition,
        ))


def serialize_log(log, ManpowerEntry, EquipmentEntry, User=None, url_helpers=None, summary=False):
    """Return a dict for a DailyLog including manpower, equipment, details, stats."""
    manpower = ManpowerEntry.query.filter_by(daily_log_id=log.id).all()
    equipment = EquipmentEntry.query.filter_by(daily_log_id=log.id).all()
    details = _parse(getattr(log, 'details_json', None), {})
    attachments = _parse(log.attachments_json, [])

    total_workers = sum(int(m.personnel_count or 0) for m in manpower)
    total_hours = sum(float(m.hours or 0) for m in manpower)
    photos = [a for a in attachments if (a.get('kind') == 'photo') or _looks_like_image(a)]

    author = ''
    if User is not None and log.user_id:
        u = User.query.get(log.user_id)
        if u:
            author = f'{u.first_name} {u.last_name}'.strip()

    base = {
        'id': log.id,
        'project_id': log.project_id,
        'date': log.date.isoformat() if log.date else None,
        'weather': log.weather,
        'work_performed': log.work_performed,
        'notes': log.notes,
        'status': getattr(log, 'status', None) or 'Submitted',
        'author': author,
        'created_at': log.created_at.isoformat() if log.created_at else None,
        'total_workers': total_workers,
        'total_hours': round(total_hours, 1),
        'photo_count': len(photos),
        'delay_count': len(details.get('delays') or []),
        'safety_count': len(details.get('safety') or []),
    }
    if summary:
        return base

    if url_helpers:
        for a in attachments:
            if a.get('document_id') and url_helpers.get('doc'):
                a['url'] = url_helpers['doc'](a['document_id'])
            elif a.get('filename') and url_helpers.get('attachment'):
                a['url'] = url_helpers['attachment'](log.id, a['filename'])

    base.update({
        'manpower': [{
            'company': m.company,
            'personnel_count': m.personnel_count,
            'hours': m.hours,
            'work_performed': m.work_performed,
        } for m in manpower],
        'equipment': [{
            'equipment_name': e.equipment_name,
            'quantity': e.quantity,
            'condition': e.condition,
        } for e in equipment],
        'details': details,
        'attachments': attachments,
        'photos': photos,
    })
    return base


def _looks_like_image(att):
    name = (att.get('original_name') or att.get('filename') or '').lower()
    return name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic'))


def compute_stats(DailyLog, ManpowerEntry, project_id):
    """Summary cards for the daily-log dashboard (real data)."""
    q = DailyLog.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    logs = q.all()
    log_ids = [l.id for l in logs]

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_count = sum(1 for l in logs if l.date and l.date >= week_start)

    total_hours = 0.0
    week_workers = []
    if log_ids:
        entries = ManpowerEntry.query.filter(ManpowerEntry.daily_log_id.in_(log_ids)).all()
        by_log_workers = {}
        for e in entries:
            total_hours += float(e.hours or 0)
            by_log_workers.setdefault(e.daily_log_id, 0)
            by_log_workers[e.daily_log_id] += int(e.personnel_count or 0)
        week_log_ids = {l.id for l in logs if l.date and l.date >= week_start}
        week_workers = [by_log_workers.get(lid, 0) for lid in week_log_ids]

    avg_crew = round(sum(week_workers) / len(week_workers)) if week_workers else 0

    photo_count = 0
    delay_count = 0
    for l in logs:
        atts = _parse(l.attachments_json, [])
        photo_count += sum(1 for a in atts if a.get('kind') == 'photo' or _looks_like_image(a))
        details = _parse(getattr(l, 'details_json', None), {})
        delay_count += len(details.get('delays') or [])

    return {
        'total_reports': len(logs),
        'this_week': week_count,
        'total_man_hours': round(total_hours, 1),
        'avg_crew_size': avg_crew,
        'photos_uploaded': photo_count,
        'open_delays': delay_count,
    }
