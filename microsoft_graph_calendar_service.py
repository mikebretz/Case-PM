"""Microsoft 365 Outlook calendar sync via Microsoft Graph."""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta

from microsoft_graph_mail_service import _graph_request, ensure_fresh_tokens


def graph_event_to_casepm(msg: dict, *, user_email: str = '') -> dict:
    start = (msg.get('start') or {}).get('dateTime') or ''
    end = (msg.get('end') or {}).get('dateTime') or ''
    location = (msg.get('location') or {}).get('displayName') or ''
    attendees = []
    for att in msg.get('attendees') or []:
        addr = ((att.get('emailAddress') or {}).get('address') or '').strip()
        if addr:
            attendees.append(addr)
    body = ((msg.get('body') or {}).get('content') or '') if isinstance(msg.get('body'), dict) else '')
    organizer = ((msg.get('organizer') or {}).get('emailAddress') or {})
    return {
        'id': f"graph_evt_{msg.get('id', '')}",
        'graphEventId': msg.get('id'),
        'title': msg.get('subject') or '(No title)',
        'start': start,
        'end': end,
        'allDay': bool(msg.get('isAllDay')),
        'location': location,
        'body': body,
        'attendees': attendees,
        'organizer': organizer.get('address') or user_email,
        'organizerName': organizer.get('name') or '',
        'eventType': 'meeting',
        'reminderMinutes': 15,
        'source': 'microsoft_graph',
        'inviteSent': True,
    }


def casepm_event_to_graph(event: dict) -> dict:
    tz = event.get('timezone') or 'UTC'
    if tz == 'local':
        tz = 'UTC'
    payload = {
        'subject': event.get('title') or 'Meeting',
        'body': {
            'contentType': 'HTML',
            'content': event.get('body') or '',
        },
        'start': {
            'dateTime': (event.get('start') or '').replace('Z', ''),
            'timeZone': tz,
        },
        'end': {
            'dateTime': (event.get('end') or event.get('start') or '').replace('Z', ''),
            'timeZone': tz,
        },
        'isAllDay': bool(event.get('allDay')),
    }
    if event.get('location'):
        payload['location'] = {'displayName': event.get('location')}
    attendees = []
    for addr in event.get('attendees') or []:
        if addr and '@' in str(addr):
            attendees.append({
                'emailAddress': {'address': str(addr).strip()},
                'type': 'required',
            })
    if attendees:
        payload['attendees'] = attendees
    return payload


def fetch_calendar_events(
    user_id: int,
    *,
    db,
    UserEmailConnection,
    days_back: int = 30,
    days_forward: int = 180,
) -> list[dict]:
    tokens = ensure_fresh_tokens(user_id, db=db, UserEmailConnection=UserEmailConnection)
    start = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%dT00:00:00Z')
    end = (datetime.utcnow() + timedelta(days=days_forward)).strftime('%Y-%m-%dT23:59:59Z')
    params = urllib.parse.urlencode({
        'startDateTime': start,
        'endDateTime': end,
        '$orderby': 'start/dateTime',
        '$top': '250',
        '$select': 'id,subject,start,end,location,body,attendees,organizer,isAllDay',
    })
    path = f'/me/calendar/calendarView?{params}'
    data = _graph_request(tokens['access_token'], path)
    return [graph_event_to_casepm(m) for m in (data.get('value') or [])]


def create_graph_event(user_id: int, event: dict, *, db, UserEmailConnection) -> dict:
    tokens = ensure_fresh_tokens(user_id, db=db, UserEmailConnection=UserEmailConnection)
    body = casepm_event_to_graph(event)
    created = _graph_request(tokens['access_token'], '/me/events', method='POST', body=body)
    return graph_event_to_casepm(created)


def update_graph_event(user_id: int, graph_event_id: str, event: dict, *, db, UserEmailConnection) -> dict:
    tokens = ensure_fresh_tokens(user_id, db=db, UserEmailConnection=UserEmailConnection)
    body = casepm_event_to_graph(event)
    updated = _graph_request(tokens['access_token'], f'/me/events/{graph_event_id}', method='PATCH', body=body)
    return graph_event_to_casepm(updated)


def delete_graph_event(user_id: int, graph_event_id: str, *, db, UserEmailConnection) -> None:
    tokens = ensure_fresh_tokens(user_id, db=db, UserEmailConnection=UserEmailConnection)
    _graph_request(tokens['access_token'], f'/me/events/{graph_event_id}', method='DELETE')


def merge_calendar_events(local_events: list[dict], graph_events: list[dict]) -> list[dict]:
    """Merge Outlook events with local Case PM events."""
    by_graph = {e.get('graphEventId'): e for e in graph_events if e.get('graphEventId')}
    merged = []
    seen_graph = set()

    for ev in local_events or []:
        gid = ev.get('graphEventId')
        if gid and gid in by_graph:
            g = by_graph[gid]
            merged.append({**g, **ev, 'graphEventId': gid, 'source': 'microsoft_graph'})
            seen_graph.add(gid)
        elif ev.get('source') != 'microsoft_graph' or not gid:
            merged.append(ev)

    for gid, g in by_graph.items():
        if gid not in seen_graph:
            merged.append(g)

    merged.sort(key=lambda e: e.get('start') or '')
    return merged


def sync_outlook_calendar(user_id: int, local_events: list[dict], *, db, UserEmailConnection) -> dict:
    graph_events = fetch_calendar_events(user_id, db=db, UserEmailConnection=UserEmailConnection)
    merged = merge_calendar_events(local_events, graph_events)
    return {
        'synced_from_outlook': len(graph_events),
        'total': len(merged),
        'events': merged,
    }
