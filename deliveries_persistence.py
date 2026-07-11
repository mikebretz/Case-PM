"""Deliveries persistence — calendar scheduling with bidirectional Schedule sync."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

STATUSES = ('Scheduled', 'Confirmed', 'In Transit', 'Delivered', 'Partial', 'Delayed', 'Cancelled')
OPEN_STATUSES = ('Scheduled', 'Confirmed', 'In Transit', 'Delayed', 'Partial')

# Status → schedule progress (0..1) so the Gantt reflects delivery state.
STATUS_PROGRESS = {
    'Scheduled': 0.0, 'Confirmed': 0.1, 'In Transit': 0.5,
    'Partial': 0.5, 'Delivered': 1.0, 'Delayed': 0.0, 'Cancelled': 0.0,
}


def _d(dt):
    return dt.isoformat() if dt else None


def serialize_delivery(d, User=None):
    return {
        'id': d.id,
        'project_id': d.project_id,
        'delivery_number': d.delivery_number,
        'supplier': d.supplier,
        'description': d.description,
        'delivery_date': _d(d.delivery_date),
        'time_window': d.time_window,
        'duration_days': d.duration_days or 1,
        'status': d.status or 'Scheduled',
        'location': d.location,
        'quantity': d.quantity,
        'po_number': d.po_number,
        'carrier': d.carrier,
        'responsible': d.responsible,
        'received_by': d.received_by,
        'notes': d.notes,
        'synced_to_schedule': bool(d.schedule_task_id),
        'schedule_task_id': d.schedule_task_id,
        'created_at': d.created_at.isoformat() if d.created_at else None,
    }


def compute_stats(Delivery, project_id):
    q = Delivery.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    rows = q.all()
    today = date.today()
    week_end = today + timedelta(days=7)
    return {
        'total': len(rows),
        'upcoming': sum(1 for d in rows if d.delivery_date and d.delivery_date >= today and (d.status or '') in OPEN_STATUSES),
        'this_week': sum(1 for d in rows if d.delivery_date and today <= d.delivery_date <= week_end),
        'delivered': sum(1 for d in rows if d.status == 'Delivered'),
        'delayed': sum(1 for d in rows if d.status == 'Delayed'),
        'overdue': sum(1 for d in rows if d.delivery_date and d.delivery_date < today and (d.status or '') in OPEN_STATUSES),
        'synced': sum(1 for d in rows if d.schedule_task_id),
    }


def task_id_for(delivery):
    return delivery.schedule_task_id or f'del-{delivery.id}'


def build_schedule_task(delivery):
    """Return a Gantt task dict representing this delivery (date format %Y-%m-%d)."""
    start = delivery.delivery_date
    dur = max(1, int(delivery.duration_days or 1))
    end = (start + timedelta(days=dur)) if start else None
    label = f"Delivery: {delivery.supplier or ''} — {(delivery.description or '').strip()[:50]}".strip(' —:')
    return {
        'id': task_id_for(delivery),
        'text': label or 'Delivery',
        'start_date': start.strftime('%Y-%m-%d') if start else None,
        'end_date': end.strftime('%Y-%m-%d') if end else None,
        'duration': dur,
        'progress': STATUS_PROGRESS.get(delivery.status or 'Scheduled', 0.0),
        'type': 'task',
        'phase': 'Deliveries',
        'source': 'delivery',
        'delivery_id': delivery.id,
        'color': '#0ea5e9',
        'assigned_to': delivery.responsible or delivery.supplier or '',
    }


def upsert_delivery_tasks(payload, deliveries):
    """Insert/update delivery tasks in a schedule payload. Returns updated payload."""
    if not isinstance(payload, dict):
        payload = {}
    data = payload.get('data')
    if not isinstance(data, list):
        data = []
    by_id = {str(t.get('id')): t for t in data if isinstance(t, dict)}
    for d in deliveries:
        tid = task_id_for(d)
        task = build_schedule_task(d)
        existing = by_id.get(str(tid))
        if existing:
            # Preserve manual schedule edits' identity but refresh delivery-driven fields.
            existing.update({
                'text': task['text'],
                'start_date': task['start_date'],
                'end_date': task['end_date'],
                'duration': task['duration'],
                'progress': task['progress'],
                'source': 'delivery',
                'delivery_id': d.id,
                'phase': 'Deliveries',
            })
        else:
            data.append(task)
            by_id[str(tid)] = task
    payload['data'] = data
    if 'links' not in payload:
        payload['links'] = []
    return payload


def apply_schedule_to_deliveries(payload, Delivery, db):
    """Reverse sync: update deliveries from any delivery-linked tasks in the schedule payload."""
    if not isinstance(payload, dict):
        return 0
    data = payload.get('data') or []
    updated = 0
    for t in data:
        if not isinstance(t, dict):
            continue
        did = t.get('delivery_id')
        if not did and (t.get('source') == 'delivery') and str(t.get('id', '')).startswith('del-'):
            try:
                did = int(str(t['id']).split('-', 1)[1])
            except (ValueError, IndexError):
                did = None
        if not did:
            continue
        d = Delivery.query.get(int(did))
        if not d:
            continue
        start = _parse_task_date(t.get('start_date'))
        if start and start != d.delivery_date:
            d.delivery_date = start
            updated += 1
        # Duration from start/end when present.
        end = _parse_task_date(t.get('end_date'))
        if start and end:
            dur = max(1, (end - start).days)
            if dur != (d.duration_days or 1):
                d.duration_days = dur
                updated += 1
        # Progress → status (only promote to Delivered; don't override manual states otherwise).
        prog = t.get('progress')
        if prog is not None:
            try:
                if float(prog) >= 1 and d.status not in ('Delivered', 'Cancelled'):
                    d.status = 'Delivered'
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
    # Last resort: first 10 chars as ISO.
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except ValueError:
        return None
