"""Bidirectional linking between email calendar, meeting minutes, safety, and estimating."""
from __future__ import annotations

import json
from datetime import datetime

from email_calendar_catalog import CALENDAR_EVENT_TYPE_IDS, meeting_type_to_event_type, COORDINATED_EVENT_TYPES
from email_calendar_persistence import load_user_calendar, normalize_event, save_user_calendar
from meeting_minutes_catalog import get_agenda_template, DEFAULT_SPEAKERS

# Calendar eventType → MeetingMinute.meeting_type
EVENT_TYPE_TO_MEETING_TYPE = {
    'owner_meeting': 'owner',
    'site_visit': 'site_visit',
    'superintendent': 'superintendent',
    'coordination': 'subcontractor',
    'meeting': 'other',
}


def event_type_to_meeting_type(event_type: str | None) -> str:
    key = (event_type or 'meeting').strip()
    if key in EVENT_TYPE_TO_MEETING_TYPE:
        return EVENT_TYPE_TO_MEETING_TYPE[key]
    if key in CALENDAR_EVENT_TYPE_IDS:
        return key
    return 'other'


def _iso_to_date_time(iso: str) -> tuple:
    if not iso:
        return None, '', ''
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except ValueError:
        return None, '', ''
    return dt.date(), dt.strftime('%H:%M'), dt.strftime('%H:%M')


def _attendees_to_mm(attendees: list) -> list:
    out = []
    for raw in attendees or []:
        if isinstance(raw, dict):
            out.append(raw)
            continue
        text = str(raw).strip()
        if not text:
            continue
        if '@' in text:
            out.append({'name': text, 'company': '', 'present': True, 'email': text})
        else:
            out.append({'name': text, 'company': '', 'present': True})
    return out


def create_meeting_minute_from_calendar_event(
    event: dict,
    *,
    user_id: int,
    db,
    MeetingMinute,
    MeetingActionItem=None,
    estimate_id: int | None = None,
) -> object:
    """Create a MeetingMinute row from a calendar event and link both ways."""
    meeting_date, start_time, _ = _iso_to_date_time(event.get('start') or '')
    _, _, end_time = _iso_to_date_time(event.get('end') or '')
    mtype = event_type_to_meeting_type(event.get('eventType'))
    project_id = event.get('projectId')
    if project_id in ('', 0, '0'):
        project_id = None
    elif project_id is not None:
        project_id = int(project_id)

    meeting = MeetingMinute(
        project_id=project_id,
        meeting_number=event.get('title', '')[:20] or 'CAL',
        subject=(event.get('title') or 'Scheduled meeting').strip(),
        meeting_type=mtype,
        status='Scheduled',
        meeting_date=meeting_date,
        start_time=start_time,
        end_time=end_time,
        location=(event.get('location') or '').strip(),
        organizer=(event.get('organizerName') or event.get('organizer') or '').strip(),
        attendees_json=json.dumps(_attendees_to_mm(event.get('attendees') or [])),
        agenda_json=json.dumps(get_agenda_template(mtype)),
        speakers_json=json.dumps(DEFAULT_SPEAKERS),
        calendar_event_id=str(event.get('id') or ''),
        estimate_id=int(estimate_id) if estimate_id else None,
        created_by_id=int(user_id),
    )
    db.session.add(meeting)
    db.session.flush()
    return meeting


def update_calendar_event_link(
    user_id: int,
    calendar_event_id: str,
    meeting_id: int,
    *,
    db,
    UserEmailCalendar,
) -> dict | None:
    """Set meetingMinuteId on a stored calendar event."""
    if not calendar_event_id or str(calendar_event_id).startswith('mm_'):
        return None
    payload = load_user_calendar(user_id, UserEmailCalendar=UserEmailCalendar)
    events = list(payload.get('events') or [])
    updated = None
    for idx, ev in enumerate(events):
        if str(ev.get('id')) == str(calendar_event_id):
            merged = {**ev, 'meetingMinuteId': int(meeting_id)}
            updated = normalize_event(merged)
            events[idx] = updated
            break
    if updated:
        save_user_calendar(user_id, events, payload.get('meta'), db=db, UserEmailCalendar=UserEmailCalendar)
    return updated


def apply_calendar_link_to_meeting(
    meeting,
    calendar_event_id: str | None,
    *,
    user_id: int,
    db,
    UserEmailCalendar,
) -> None:
    """Link an existing meeting minute to a calendar event (bidirectional)."""
    if not calendar_event_id:
        return
    meeting.calendar_event_id = str(calendar_event_id)
    update_calendar_event_link(user_id, calendar_event_id, meeting.id, db=db, UserEmailCalendar=UserEmailCalendar)


def prefill_meeting_from_calendar_event(event: dict) -> dict:
    """Build meeting-minutes form defaults from a calendar event."""
    meeting_date, start_time, _ = _iso_to_date_time(event.get('start') or '')
    _, _, end_time = _iso_to_date_time(event.get('end') or '')
    return {
        'calendar_event_id': event.get('id'),
        'subject': event.get('title') or '',
        'meeting_type': event_type_to_meeting_type(event.get('eventType')),
        'meeting_date': meeting_date.isoformat() if meeting_date else '',
        'start_time': start_time,
        'end_time': end_time,
        'location': event.get('location') or '',
        'organizer': event.get('organizerName') or event.get('organizer') or '',
        'attendees': _attendees_to_mm(event.get('attendees') or []),
        'status': 'Scheduled',
        'estimate_id': event.get('estimateId'),
    }


def list_linkable_calendar_events(
    user_id: int,
    *,
    UserEmailCalendar,
    project_id: int | None = None,
    meeting_type: str | None = None,
    events: list | None = None,
) -> list[dict]:
    """Calendar events that can be linked to a new meeting minutes record."""
    payload = load_user_calendar(user_id, UserEmailCalendar=UserEmailCalendar)
    rows = list(events if events is not None else (payload.get('events') or []))
    target_type = meeting_type or ''
    compatible_event_type = meeting_type_to_event_type(target_type) if target_type else None
    out = []
    for ev in rows:
        if ev.get('meetingMinuteId'):
            continue
        if ev.get('source') == 'meeting_minutes':
            continue
        if str(ev.get('id', '')).startswith('mm_'):
            continue
        if project_id and ev.get('projectId') and int(ev.get('projectId')) != int(project_id):
            continue
        if compatible_event_type and ev.get('eventType') not in (compatible_event_type, target_type, 'meeting', 'coordination'):
            # Allow loose match for toolbox/safety etc.
            mapped = event_type_to_meeting_type(ev.get('eventType'))
            if mapped != target_type and ev.get('eventType') != target_type:
                continue
        out.append({
            'id': ev.get('id'),
            'title': ev.get('title'),
            'start': ev.get('start'),
            'end': ev.get('end'),
            'eventType': ev.get('eventType'),
            'location': ev.get('location'),
            'projectId': ev.get('projectId'),
            'estimateId': ev.get('estimateId'),
        })
    out.sort(key=lambda e: e.get('start') or '')
    return out
