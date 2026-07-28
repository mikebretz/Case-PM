"""Calendar event types and meeting-minutes ↔ email calendar sync helpers."""
from __future__ import annotations

from datetime import datetime, timedelta

from meeting_minutes_catalog import MEETING_TYPES

# Calendar event types (sidebar shortcuts + meeting modal dropdown).
CALENDAR_EVENT_TYPES = [
    {'id': 'owner_meeting', 'label': 'Owner meeting', 'icon': 'fa-building-user', 'defaultTitle': 'Owner meeting'},
    {'id': 'site_visit', 'label': 'Site visit', 'icon': 'fa-hard-hat', 'defaultTitle': 'Site visit'},
    {'id': 'precon', 'label': 'Pre-construction walkthrough', 'icon': 'fa-clipboard-list', 'defaultTitle': 'Pre-construction walkthrough'},
    {'id': 'bid', 'label': 'Bid meeting / walkthrough', 'icon': 'fa-gavel', 'defaultTitle': 'Bid meeting'},
    {'id': 'oac', 'label': 'OAC meeting', 'icon': 'fa-people-group', 'defaultTitle': 'OAC meeting'},
    {'id': 'oac_weekly', 'label': 'OAC weekly progress', 'icon': 'fa-calendar-week', 'defaultTitle': 'OAC weekly progress'},
    {'id': 'superintendent', 'label': 'Superintendent / field', 'icon': 'fa-hard-hat', 'defaultTitle': 'Superintendent meeting'},
    {'id': 'subcontractor', 'label': 'Subcontractor coordination', 'icon': 'fa-truck-field', 'defaultTitle': 'Subcontractor coordination'},
    {'id': 'safety', 'label': 'Safety meeting', 'icon': 'fa-shield-halved', 'defaultTitle': 'Safety meeting'},
    {'id': 'toolbox_talk', 'label': 'Toolbox / tailgate talk', 'icon': 'fa-toolbox', 'defaultTitle': 'Toolbox talk'},
    {'id': 'design', 'label': 'Design coordination / BIM', 'icon': 'fa-compass-drafting', 'defaultTitle': 'Design coordination'},
    {'id': 'schedule', 'label': 'Schedule / CPM review', 'icon': 'fa-chart-gantt', 'defaultTitle': 'Schedule review'},
    {'id': 'submittal', 'label': 'Submittal review', 'icon': 'fa-file-circle-check', 'defaultTitle': 'Submittal review'},
    {'id': 'closeout', 'label': 'Closeout / punch', 'icon': 'fa-flag-checkered', 'defaultTitle': 'Closeout meeting'},
    {'id': 'internal', 'label': 'Internal team', 'icon': 'fa-users', 'defaultTitle': 'Internal team meeting'},
    {'id': 'stakeholder', 'label': 'Client / stakeholder', 'icon': 'fa-handshake', 'defaultTitle': 'Stakeholder meeting'},
    {'id': 'coordination', 'label': 'Coordination', 'icon': 'fa-arrows-turn-to-dots', 'defaultTitle': 'Coordination meeting'},
    {'id': 'meeting', 'label': 'General meeting', 'icon': 'fa-calendar', 'defaultTitle': 'Meeting'},
    {'id': 'other', 'label': 'Other', 'icon': 'fa-ellipsis', 'defaultTitle': 'Meeting'},
]

CALENDAR_EVENT_TYPE_IDS = {row['id'] for row in CALENDAR_EVENT_TYPES}

COORDINATED_EVENT_TYPES = frozenset({
    'owner_meeting', 'site_visit', 'precon', 'bid', 'oac', 'oac_weekly',
    'superintendent', 'subcontractor', 'safety', 'toolbox_talk', 'design',
    'schedule', 'submittal', 'closeout', 'internal', 'stakeholder',
})

MEETING_TYPE_TO_EVENT_TYPE = {
    'owner': 'owner_meeting',
    'superintendent': 'site_visit',
    'site_visit': 'site_visit',
}

OPEN_CALENDAR_STATUSES = frozenset({
    'Draft', 'Scheduled', 'In Progress', 'Completed', 'Distributed', 'Published',
})


def meeting_type_to_event_type(meeting_type: str | None) -> str:
    key = (meeting_type or 'other').strip()
    if key in MEETING_TYPE_TO_EVENT_TYPE:
        return MEETING_TYPE_TO_EVENT_TYPE[key]
    if key in CALENDAR_EVENT_TYPE_IDS:
        return key
    return 'meeting'


def _parse_time_on_date(meeting_date, time_str: str | None, default_hour: int) -> datetime:
    base = datetime.combine(meeting_date, datetime.min.time())
    raw = (time_str or '').strip()
    if not raw:
        return base.replace(hour=default_hour, minute=0)
    for fmt in ('%H:%M', '%I:%M %p', '%I:%M%p', '%H:%M:%S'):
        try:
            parsed = datetime.strptime(raw.upper(), fmt)
            return base.replace(hour=parsed.hour, minute=parsed.minute)
        except ValueError:
            continue
    return base.replace(hour=default_hour, minute=0)


def meeting_minute_to_calendar_event(meeting, *, project_name: str = '') -> dict | None:
    """Convert a MeetingMinute row into an email-calendar event dict."""
    if not meeting or not meeting.meeting_date:
        return None
    status = (meeting.status or '').strip()
    if status == 'Cancelled':
        return None
    if status and status not in OPEN_CALENDAR_STATUSES:
        return None

    start_dt = _parse_time_on_date(meeting.meeting_date, meeting.start_time, 9)
    end_dt = _parse_time_on_date(meeting.meeting_date, meeting.end_time, 10)
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    attendees = []
    try:
        import json
        attendees = [str(x).strip() for x in (json.loads(meeting.attendees_json or '[]') or []) if str(x).strip()]
    except (TypeError, json.JSONDecodeError):
        attendees = []

    event_type = meeting_type_to_event_type(meeting.meeting_type)
    type_label = next((t['label'] for t in CALENDAR_EVENT_TYPES if t['id'] == event_type), event_type)
    location = (meeting.location or '').strip()
    if meeting.virtual_link:
        location = f"{location} ({meeting.virtual_link})" if location else meeting.virtual_link

    return {
        'id': f'mm_{meeting.id}',
        'meetingMinuteId': meeting.id,
        'source': 'meeting_minutes',
        'readOnly': True,
        'title': meeting.subject or type_label,
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
        'allDay': False,
        'location': location,
        'body': f'<p>From Meeting Minutes ({type_label}). <a href="/meeting-minutes">Open meeting record</a></p>',
        'attendees': attendees,
        'organizer': meeting.organizer or '',
        'organizerName': meeting.organizer or '',
        'projectId': meeting.project_id,
        'projectName': project_name,
        'eventType': event_type,
        'reminderMinutes': 15,
        'timezone': 'local',
        'locationMeta': {},
        'inviteSent': False,
        'estimateId': getattr(meeting, 'estimate_id', None),
        'calendarEventId': getattr(meeting, 'calendar_event_id', None) or '',
    }


def merge_meeting_minute_events(stored_events: list, minute_events: list) -> list:
    """Merge meeting-minute events into a user's calendar list without duplicates."""
    merged = []
    minute_by_id = {ev.get('meetingMinuteId'): ev for ev in minute_events if ev.get('meetingMinuteId')}
    seen_mm = set()

    for ev in stored_events or []:
        mm_id = ev.get('meetingMinuteId')
        if mm_id:
            seen_mm.add(int(mm_id))
            if int(mm_id) in minute_by_id:
                merged.append(minute_by_id[int(mm_id)])
            else:
                merged.append(ev)
            continue
        if str(ev.get('id', '')).startswith('mm_'):
            try:
                seen_mm.add(int(str(ev['id']).split('_', 1)[1]))
            except (TypeError, ValueError, IndexError):
                pass
            continue
        merged.append(ev)

    for mm_id, ev in minute_by_id.items():
        if int(mm_id) not in seen_mm:
            merged.append(ev)

    merged.sort(key=lambda e: e.get('start') or '')
    return merged


def calendar_catalog_payload() -> dict:
    return {
        'event_types': CALENDAR_EVENT_TYPES,
        'meeting_types': MEETING_TYPES,
        'coordinated_event_types': sorted(COORDINATED_EVENT_TYPES),
        'sidebar': [
            {'id': 'month', 'label': 'Month view', 'icon': 'fa-calendar', 'action': 'view'},
            *[
                {
                    'id': row['id'],
                    'label': row['label'],
                    'icon': row['icon'],
                    'action': 'new',
                    'defaultTitle': row.get('defaultTitle') or row['label'],
                }
                for row in CALENDAR_EVENT_TYPES
                if row['id'] not in ('meeting', 'other', 'coordination')
            ],
        ],
    }
