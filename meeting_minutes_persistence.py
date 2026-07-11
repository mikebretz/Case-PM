"""Meeting minutes persistence — serialization, stats, minutes generation, schedule sync."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from meeting_minutes_catalog import STATUSES, OPEN_STATUSES, ACTION_STATUSES

STATUS_PROGRESS = {
    'Draft': 0.0,
    'Scheduled': 0.1,
    'In Progress': 0.5,
    'Completed': 1.0,
    'Distributed': 1.0,
    'Cancelled': 0.0,
}


def _d(dt):
    return dt.isoformat() if dt else None


def _parse_json(raw, default=None):
    if default is None:
        default = []
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def serialize_action_item(item):
    return {
        'id': item.id,
        'meeting_id': item.meeting_id,
        'project_id': item.project_id,
        'item_number': item.item_number or '',
        'description': item.description or '',
        'assigned_to': item.assigned_to or '',
        'due_date': _d(item.due_date),
        'status': item.status or 'Open',
        'priority': item.priority or 'Normal',
        'notes': item.notes or '',
        'created_at': item.created_at.isoformat() if item.created_at else None,
    }


def serialize_meeting(m, include_actions=True, ActionItem=None):
    actions = []
    if include_actions and ActionItem is not None:
        actions = [
            serialize_action_item(a)
            for a in ActionItem.query.filter_by(meeting_id=m.id).order_by(ActionItem.id.asc()).all()
        ]
    return {
        'id': m.id,
        'project_id': m.project_id,
        'meeting_number': m.meeting_number or '',
        'meeting_date': _d(m.meeting_date),
        'start_time': m.start_time or '',
        'end_time': m.end_time or '',
        'meeting_type': m.meeting_type or 'other',
        'status': m.status or 'Draft',
        'subject': m.subject or '',
        'location': m.location or '',
        'virtual_link': m.virtual_link or '',
        'organizer': m.organizer or '',
        'attendees': _parse_json(m.attendees_json, []),
        'agenda': _parse_json(m.agenda_json, []),
        'discussion_notes': m.discussion_notes or '',
        'decisions': _parse_json(m.decisions_json, []),
        'transcript_segments': _parse_json(m.transcript_json, []),
        'speakers': _parse_json(m.speakers_json, []),
        'minutes_body': m.minutes_body or '',
        'distribution': _parse_json(m.distribution_json, []),
        'recording_filename': m.recording_filename or '',
        'recording_duration_sec': m.recording_duration_sec or 0,
        'has_recording': bool(m.recording_filename),
        'document_id': m.document_id,
        'synced_to_schedule': bool(m.schedule_task_id),
        'schedule_task_id': m.schedule_task_id,
        'next_meeting_date': _d(m.next_meeting_date),
        'action_items': actions,
        'open_action_count': sum(1 for a in actions if (a.get('status') or '') in ('Open', 'In Progress')),
        'created_at': m.created_at.isoformat() if m.created_at else None,
        'updated_at': m.updated_at.isoformat() if m.updated_at else None,
    }


def compute_stats(MeetingMinute, ActionItem, project_id):
    mq = MeetingMinute.query
    aq = ActionItem.query
    if project_id:
        mq = mq.filter_by(project_id=int(project_id))
        aq = aq.filter_by(project_id=int(project_id))
    meetings = mq.all()
    actions = aq.all()
    today = date.today()
    month_start = today.replace(day=1)
    return {
        'total': len(meetings),
        'this_month': sum(1 for m in meetings if m.meeting_date and m.meeting_date >= month_start),
        'scheduled': sum(1 for m in meetings if (m.status or '') in ('Scheduled', 'In Progress')),
        'drafts': sum(1 for m in meetings if (m.status or '') == 'Draft'),
        'completed': sum(1 for m in meetings if (m.status or '') in ('Completed', 'Distributed')),
        'with_recordings': sum(1 for m in meetings if m.recording_filename),
        'open_actions': sum(1 for a in actions if (a.status or '') in ('Open', 'In Progress')),
        'overdue_actions': sum(
            1 for a in actions
            if a.due_date and a.due_date < today and (a.status or '') in ('Open', 'In Progress')
        ),
    }


def task_id_for(meeting):
    return meeting.schedule_task_id or f'mm-{meeting.id}'


def build_schedule_task(meeting):
    start = meeting.meeting_date
    label = f"Meeting: {(meeting.subject or meeting.meeting_number or 'Minutes')[:60]}"
    return {
        'id': task_id_for(meeting),
        'text': label,
        'start_date': start.strftime('%Y-%m-%d') if start else None,
        'end_date': start.strftime('%Y-%m-%d') if start else None,
        'duration': 1,
        'progress': STATUS_PROGRESS.get(meeting.status or 'Draft', 0.0),
        'type': 'milestone',
        'phase': 'Meetings',
        'color': '#8b5cf6',
        'source': 'meeting_minutes',
        'meeting_id': meeting.id,
    }


def upsert_meeting_tasks(payload, meetings):
    data = list(payload.get('data') or [])
    by_id = {str(t.get('id')): t for t in data if isinstance(t, dict) and t.get('id')}
    for m in meetings:
        tid = task_id_for(m)
        task = build_schedule_task(m)
        by_id[tid] = task
    payload['data'] = list(by_id.values())
    return payload


def apply_schedule_to_meetings(payload, MeetingMinute, db):
    """Reverse-sync meeting dates from schedule edits."""
    updated = 0
    tasks = {str(t.get('id')): t for t in (payload.get('data') or []) if isinstance(t, dict)}
    rows = MeetingMinute.query.filter(MeetingMinute.schedule_task_id.isnot(None)).all()
    for m in rows:
        tid = str(m.schedule_task_id)
        t = tasks.get(tid)
        if not t:
            continue
        start = t.get('start_date')
        if not start:
            continue
        try:
            new_date = datetime.strptime(str(start)[:10], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            continue
        if m.meeting_date != new_date:
            m.meeting_date = new_date
            updated += 1
    if updated:
        db.session.commit()
    return updated


def _type_label(meeting_type):
    from meeting_minutes_catalog import MEETING_TYPES
    for t in MEETING_TYPES:
        if t['key'] == meeting_type:
            return t['label']
    return meeting_type.replace('_', ' ').title()


def generate_simple_minutes(meeting_dict):
    """Build formatted minutes from structured meeting data + transcript segments."""
    lines = []
    subject = meeting_dict.get('subject') or 'Project Meeting'
    number = meeting_dict.get('meeting_number') or ''
    mdate = meeting_dict.get('meeting_date') or ''
    mtype = _type_label(meeting_dict.get('meeting_type') or 'other')

    lines.append(f'MEETING MINUTES')
    lines.append(f'{"=" * 48}')
    lines.append(f'Meeting: {subject}')
    if number:
        lines.append(f'Number: {number}')
    lines.append(f'Date: {mdate}')
    if meeting_dict.get('start_time') or meeting_dict.get('end_time'):
        lines.append(f'Time: {meeting_dict.get("start_time") or "—"} – {meeting_dict.get("end_time") or "—"}')
    lines.append(f'Type: {mtype}')
    if meeting_dict.get('location'):
        lines.append(f'Location: {meeting_dict["location"]}')
    if meeting_dict.get('virtual_link'):
        lines.append(f'Virtual link: {meeting_dict["virtual_link"]}')
    if meeting_dict.get('organizer'):
        lines.append(f'Organizer: {meeting_dict["organizer"]}')
    lines.append('')

    attendees = meeting_dict.get('attendees') or []
    if attendees:
        lines.append('ATTENDEES')
        lines.append('-' * 32)
        for a in attendees:
            if isinstance(a, str):
                lines.append(f'  • {a}')
            elif isinstance(a, dict):
                name = a.get('name') or '—'
                company = a.get('company') or ''
                present = a.get('present', True)
                status = 'Present' if present else 'Absent'
                suffix = f' ({company})' if company else ''
                lines.append(f'  • {name}{suffix} — {status}')
        lines.append('')

    agenda = meeting_dict.get('agenda') or []
    if agenda:
        lines.append('AGENDA')
        lines.append('-' * 32)
        for i, item in enumerate(agenda, 1):
            topic = item.get('topic') or item.get('text') or f'Item {i}'
            presenter = item.get('presenter') or ''
            notes = item.get('notes') or ''
            line = f'  {i}. {topic}'
            if presenter:
                line += f' — {presenter}'
            lines.append(line)
            if notes:
                lines.append(f'     Notes: {notes}')
        lines.append('')

    segments = meeting_dict.get('transcript_segments') or []
    discussion = meeting_dict.get('discussion_notes') or ''
    if segments:
        lines.append('DISCUSSION (transcribed)')
        lines.append('-' * 32)
        current_speaker = None
        for seg in segments:
            label = seg.get('speaker_label') or seg.get('speaker_id') or 'Speaker'
            text = (seg.get('text') or '').strip()
            if not text:
                continue
            if label != current_speaker:
                lines.append(f'\n{label}:')
                current_speaker = label
            lines.append(f'  {text}')
        lines.append('')
    elif discussion.strip():
        lines.append('DISCUSSION')
        lines.append('-' * 32)
        lines.append(discussion.strip())
        lines.append('')

    decisions = meeting_dict.get('decisions') or []
    if decisions:
        lines.append('DECISIONS')
        lines.append('-' * 32)
        for i, d in enumerate(decisions, 1):
            text = d.get('text') if isinstance(d, dict) else str(d)
            if text:
                lines.append(f'  {i}. {text}')
        lines.append('')

    actions = meeting_dict.get('action_items') or []
    if actions:
        lines.append('ACTION ITEMS')
        lines.append('-' * 32)
        for a in actions:
            desc = a.get('description') or ''
            assignee = a.get('assigned_to') or 'Unassigned'
            due = a.get('due_date') or 'TBD'
            status = a.get('status') or 'Open'
            num = a.get('item_number') or ''
            prefix = f'{num}: ' if num else '• '
            lines.append(f'  {prefix}{desc}')
            lines.append(f'     Assigned: {assignee} | Due: {due} | Status: {status}')
        lines.append('')

    if meeting_dict.get('next_meeting_date'):
        lines.append(f'Next meeting: {meeting_dict["next_meeting_date"]}')
        lines.append('')

    lines.append(f'Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}')
    return '\n'.join(lines)


def extract_action_items_from_text(text):
    """Heuristic: lines starting with action/to-do/assignee patterns."""
    items = []
    for line in (text or '').splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r'^(action|todo|follow[- ]?up|assign)\s*[:#\-]', s, re.I):
            desc = re.sub(r'^(action|todo|follow[- ]?up|assign)\s*[:#\-]\s*', '', s, flags=re.I)
            if desc:
                items.append({'description': desc, 'status': 'Open', 'priority': 'Normal'})
        elif re.match(r'^AI[-\s]?\d+', s, re.I):
            items.append({'description': s, 'status': 'Open', 'priority': 'Normal'})
    return items
