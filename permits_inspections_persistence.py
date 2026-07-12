"""Permits & Inspections persistence — calendar tracking with bidirectional Schedule sync."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from florida_permit_catalog import STATUSES, OPEN_STATUSES

STATUS_PROGRESS = {
    'Not Started': 0.0,
    'Application Submitted': 0.05,
    'In Review': 0.1,
    'Issued': 0.2,
    'Scheduled': 0.25,
    'Inspection Requested': 0.35,
    'Passed': 1.0,
    'Failed': 0.0,
    'Correction Required': 0.15,
    'Re-inspection Scheduled': 0.3,
    'Closed': 1.0,
    'Cancelled': 0.0,
}


def _d(dt):
    return dt.isoformat() if dt else None


def serialize_item(item, User=None):
    data = {
        'id': item.id,
        'project_id': item.project_id,
        'item_number': item.item_number,
        'record_kind': item.record_kind or 'inspection',
        'trade': item.trade or 'building',
        'inspection_phase': item.inspection_phase or '',
        'title': item.title or '',
        'description': item.description or '',
        'fbc_reference': item.fbc_reference or '',
        'permit_number': item.permit_number or '',
        'parent_id': item.parent_id,
        'jurisdiction_level': item.jurisdiction_level or '',
        'jurisdiction_name': item.jurisdiction_name or '',
        'authority_name': item.authority_name or '',
        'authority_phone': item.authority_phone or '',
        'authority_url': item.authority_url or '',
        'scheduled_date': _d(item.scheduled_date),
        'scheduled_time': item.scheduled_time or '',
        'duration_days': item.duration_days or 1,
        'status': item.status or 'Not Started',
        'inspector': item.inspector or '',
        'location': item.location or '',
        'result_notes': item.result_notes or '',
        'correction_notes': item.correction_notes or '',
        'synced_to_schedule': bool(item.schedule_task_id),
        'schedule_task_id': item.schedule_task_id,
        'catalog_source': item.catalog_source or '',
        'details': _parse_json(item.details_json, {}),
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }
    try:
        from inspection_reminders import serialize_notification_fields
        data.update(serialize_notification_fields(item))
    except Exception:
        pass
    return data


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def compute_stats(Item, project_id):
    q = Item.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    rows = q.all()
    today = date.today()
    week_end = today + timedelta(days=7)
    permits = [r for r in rows if (r.record_kind or '') == 'permit']
    inspections = [r for r in rows if (r.record_kind or '') != 'permit']
    return {
        'total': len(rows),
        'permits': len(permits),
        'inspections': len(inspections),
        'upcoming': sum(1 for r in rows if r.scheduled_date and r.scheduled_date >= today and (r.status or '') in OPEN_STATUSES),
        'this_week': sum(1 for r in rows if r.scheduled_date and today <= r.scheduled_date <= week_end),
        'passed': sum(1 for r in rows if r.status == 'Passed'),
        'failed': sum(1 for r in rows if r.status in ('Failed', 'Correction Required')),
        'overdue': sum(1 for r in rows if r.scheduled_date and r.scheduled_date < today and (r.status or '') in OPEN_STATUSES),
        'synced': sum(1 for r in rows if r.schedule_task_id),
    }


def task_id_for(item):
    return item.schedule_task_id or f'insp-{item.id}'


def build_schedule_task(item):
    """Gantt task or milestone for schedule sync."""
    start = item.scheduled_date
    is_milestone = (item.record_kind == 'inspection' and (item.inspection_phase or '') in (
        'final', 'co', 'tco', 'milestone', 'threshold_review',
    )) or (item.duration_days or 1) <= 1
    dur = 0 if is_milestone else max(1, int(item.duration_days or 1))
    end = start if is_milestone else ((start + timedelta(days=dur)) if start else None)
    trade = (item.trade or 'building').replace('_', ' ').title()
    label = item.title or f'{trade} {item.inspection_phase or "Inspection"}'
    if item.permit_number:
        label = f'{label} [{item.permit_number}]'
    return {
        'id': task_id_for(item),
        'text': label[:120],
        'start_date': start.strftime('%Y-%m-%d') if start else None,
        'end_date': end.strftime('%Y-%m-%d') if end else (start.strftime('%Y-%m-%d') if start else None),
        'duration': dur,
        'progress': STATUS_PROGRESS.get(item.status or 'Not Started', 0.0),
        'type': 'milestone' if is_milestone else 'task',
        'phase': 'Permits & Inspections',
        'source': 'permit_inspection',
        'permit_inspection_id': item.id,
        'color': '#f97316',
        'assigned_to': item.inspector or item.authority_name or '',
    }


def upsert_inspection_tasks(payload, items):
    if not isinstance(payload, dict):
        payload = {}
    data = payload.get('data')
    if not isinstance(data, list):
        data = []
    by_id = {str(t.get('id')): t for t in data if isinstance(t, dict)}
    for item in items:
        tid = task_id_for(item)
        task = build_schedule_task(item)
        existing = by_id.get(str(tid))
        if existing:
            existing.update({
                'text': task['text'],
                'start_date': task['start_date'],
                'end_date': task['end_date'],
                'duration': task['duration'],
                'type': task['type'],
                'progress': task['progress'],
                'source': 'permit_inspection',
                'permit_inspection_id': item.id,
                'phase': 'Permits & Inspections',
            })
        else:
            data.append(task)
            by_id[str(tid)] = task
    payload['data'] = data
    if 'links' not in payload:
        payload['links'] = []
    return payload


def apply_schedule_to_items(payload, Item, db):
    if not isinstance(payload, dict):
        return 0
    data = payload.get('data') or []
    updated = 0
    for t in data:
        if not isinstance(t, dict):
            continue
        iid = t.get('permit_inspection_id')
        if not iid and (t.get('source') == 'permit_inspection') and str(t.get('id', '')).startswith('insp-'):
            try:
                iid = int(str(t['id']).split('-', 1)[1])
            except (ValueError, IndexError):
                iid = None
        if not iid:
            continue
        item = Item.query.get(int(iid))
        if not item:
            continue
        start = _parse_task_date(t.get('start_date'))
        if start and start != item.scheduled_date:
            item.scheduled_date = start
            updated += 1
        end = _parse_task_date(t.get('end_date'))
        if start and end and (item.duration_days or 1) > 1:
            dur = max(1, (end - start).days)
            if dur != (item.duration_days or 1):
                item.duration_days = dur
                updated += 1
        prog = t.get('progress')
        if prog is not None:
            try:
                if float(prog) >= 1 and item.status not in ('Passed', 'Closed', 'Cancelled'):
                    item.status = 'Passed'
                    updated += 1
            except (TypeError, ValueError):
                pass
    if updated:
        db.session.commit()
    return updated


def _parse_task_date(value):
    if not value:
        return None
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except ValueError:
        return None
