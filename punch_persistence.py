"""Punch list persistence — field-friendly deficiency tracking.

Feature set for construction punch lists:
quick check-off, status verification workflow, priority, assignee/company, trade,
location, category, due dates with overdue flags, photos, comments, and sub-tasks.
"""
from __future__ import annotations

import json
from datetime import date, datetime

# Two-step verification workflow (field marks Ready, reviewer Closes/Verifies).
STATUSES = ('Open', 'In Progress', 'Ready for Review', 'Closed')
OPEN_STATUSES = ('Open', 'In Progress', 'Ready for Review')
PRIORITIES = ('High', 'Medium', 'Low')

# Common deficiency categories used by field crews for quick tagging.
CATEGORIES = (
    'Paint / Drywall', 'Flooring', 'Doors / Hardware', 'Millwork / Casework',
    'Electrical', 'Plumbing', 'HVAC / Mechanical', 'Fire Protection',
    'Ceilings', 'Glazing / Storefront', 'Concrete / Masonry', 'Roofing',
    'Site / Landscape', 'Cleaning', 'Life Safety', 'Other',
)


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


def build_details(payload):
    """Normalize sub-tasks + comments (comments are appended server-side, not replaced)."""
    payload = payload or {}
    subtasks = []
    for row in payload.get('subtasks') or []:
        if not isinstance(row, dict):
            continue
        text = (row.get('text') or '').strip()
        if text:
            subtasks.append({'text': text, 'done': bool(row.get('done'))})
    return {'subtasks': subtasks}


def serialize_item(item, User=None, url_helpers=None, summary=False):
    details = _parse(getattr(item, 'details_json', None), {})
    attachments = _parse(getattr(item, 'attachments_json', None), [])
    photos = [a for a in attachments if a.get('kind') == 'photo' or _looks_like_image(a)]
    status = item.status or 'Open'
    is_open = status in OPEN_STATUSES
    due = item.due_date
    is_overdue = bool(is_open and due and due < date.today())

    assignee_name = item.assigned_to or ''
    author = ''
    if User is not None and item.created_by_id:
        u = User.query.get(item.created_by_id)
        if u:
            author = f'{u.first_name} {u.last_name}'.strip()

    subtasks = details.get('subtasks') or []
    base = {
        'id': item.id,
        'number': item.number,
        'project_id': item.project_id,
        'description': item.description,
        'location': item.location,
        'trade': item.trade,
        'category': getattr(item, 'category', None),
        'priority': item.priority or 'Medium',
        'status': status,
        'is_open': is_open,
        'is_overdue': is_overdue,
        'due_date': due.isoformat() if due else None,
        'assigned_to': assignee_name,
        'assigned_company': getattr(item, 'assigned_company', None),
        'created_by': author,
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'completed_at': item.completed_at.isoformat() if getattr(item, 'completed_at', None) else None,
        'photo_count': len(photos),
        'comment_count': len(details.get('comments') or []),
        'subtask_total': len(subtasks),
        'subtask_done': sum(1 for s in subtasks if s.get('done')),
    }
    if summary:
        return base

    if url_helpers:
        for a in attachments:
            if a.get('document_id') and url_helpers.get('doc'):
                a['url'] = url_helpers['doc'](a['document_id'])
            elif a.get('filename') and url_helpers.get('attachment'):
                a['url'] = url_helpers['attachment'](item.id, a['filename'])

    base.update({
        'subtasks': subtasks,
        'comments': details.get('comments') or [],
        'attachments': attachments,
        'photos': photos,
        'plan_pins': _parse(getattr(item, 'plan_pins_json', None), []),
    })
    return base


def compute_stats(PunchItem, project_id):
    q = PunchItem.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    items = q.all()
    today = date.today()
    open_items = [i for i in items if (i.status or 'Open') in OPEN_STATUSES]
    return {
        'total': len(items),
        'open': len(open_items),
        'in_progress': sum(1 for i in items if i.status == 'In Progress'),
        'ready': sum(1 for i in items if i.status == 'Ready for Review'),
        'closed': sum(1 for i in items if i.status == 'Closed'),
        'overdue': sum(1 for i in open_items if i.due_date and i.due_date < today),
        'high_priority': sum(1 for i in open_items if (i.priority or '') == 'High'),
        'percent_complete': round((len(items) - len(open_items)) / len(items) * 100) if items else 0,
    }


def add_comment(item, text, author):
    details = _parse(getattr(item, 'details_json', None), {})
    comments = details.get('comments') or []
    comments.append({
        'text': text,
        'author': author,
        'at': datetime.utcnow().isoformat(),
    })
    details['comments'] = comments
    item.details_json = json.dumps(details)
    return comments
