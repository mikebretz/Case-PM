"""Load scheduled meetings from Meeting Minutes into the email calendar."""
from __future__ import annotations

from sqlalchemy import or_

from email_calendar_catalog import meeting_minute_to_calendar_event, merge_meeting_minute_events


def load_meeting_minute_calendar_events(
    user,
    *,
    MeetingMinute,
    Project,
    ProjectMembership=None,
    months_back: int = 1,
    months_forward: int = 18,
) -> list[dict]:
    from datetime import date, timedelta

    from dashboard_persistence import get_accessible_projects

    today = date.today()
    start = today - timedelta(days=30 * months_back)
    end = today + timedelta(days=30 * months_forward)

    projects = get_accessible_projects(Project, user, ProjectMembership)
    project_ids = {int(p.id) for p in projects}
    project_names = {int(p.id): (p.name or '') for p in projects}

    filters = [MeetingMinute.project_id.is_(None), MeetingMinute.created_by_id == int(user.id)]
    if project_ids:
        filters.append(MeetingMinute.project_id.in_(sorted(project_ids)))
    q = MeetingMinute.query.filter(
        MeetingMinute.meeting_date.isnot(None),
        MeetingMinute.meeting_date >= start,
        MeetingMinute.meeting_date <= end,
        MeetingMinute.status != 'Cancelled',
        or_(*filters),
    )
    rows = q.order_by(MeetingMinute.meeting_date.asc(), MeetingMinute.id.asc()).all()

    events = []
    for row in rows:
        pname = project_names.get(int(row.project_id)) if row.project_id else 'Company-wide'
        ev = meeting_minute_to_calendar_event(row, project_name=pname or '')
        if ev:
            events.append(ev)
    return events


def strip_meeting_minute_events(events: list) -> list:
    """Remove read-only meeting-minute rows before persisting user calendar storage."""
    cleaned = []
    for ev in events or []:
        if ev.get('source') == 'meeting_minutes':
            continue
        if str(ev.get('id', '')).startswith('mm_'):
            continue
        if ev.get('meetingMinuteId'):
            continue
        cleaned.append(ev)
    return cleaned


def enrich_calendar_with_meetings(payload: dict, user, *, MeetingMinute, Project, ProjectMembership=None) -> dict:
    minute_events = load_meeting_minute_calendar_events(
        user, MeetingMinute=MeetingMinute, Project=Project, ProjectMembership=ProjectMembership,
    )
    events = merge_meeting_minute_events(payload.get('events') or [], minute_events)
    out = dict(payload)
    out['events'] = events
    out['merged_meeting_minutes'] = len(minute_events)
    return out
