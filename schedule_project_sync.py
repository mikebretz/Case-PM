"""Seed project start/finish dates into ScheduleData when appropriate."""
from __future__ import annotations

import json
from datetime import datetime, timedelta


def _parse_payload(record):
    if not record or not record.payload:
        return None
    try:
        return json.loads(record.payload)
    except (TypeError, json.JSONDecodeError):
        return None


def _task_dates(task):
    start = task.get('start_date')
    end = task.get('end_date')
    if start and end:
        return start, end
    if start and task.get('duration') is not None:
        try:
            s = datetime.strptime(str(start)[:10], '%Y-%m-%d').date()
            days = int(task.get('duration') or 0)
            e = s + timedelta(days=max(days - 1, 0))
            return start, e.isoformat()
        except (TypeError, ValueError):
            pass
    return start, end


def _has_meaningful_schedule(payload):
    if not payload or not isinstance(payload.get('data'), list):
        return False
    tasks = [t for t in payload['data'] if t.get('type') != 'project']
    if tasks:
        return True
    for t in payload['data']:
        if t.get('type') == 'project':
            start, end = _task_dates(t)
            if start and end and start != end:
                return True
    return False


def _format_gantt_date(value):
    if not value:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    return str(value)[:10]


def compute_end_date_from_weeks(start_date, weeks):
    if not start_date or not weeks:
        return None
    try:
        weeks = int(weeks)
        if weeks < 1:
            return None
        start = start_date if hasattr(start_date, 'isoformat') else datetime.strptime(str(start_date)[:10], '%Y-%m-%d').date()
        return (start + timedelta(weeks=weeks) - timedelta(days=1)).isoformat()
    except (TypeError, ValueError):
        return None


def propagate_project_dates_to_schedule(
    project,
    ScheduleData,
    db,
    *,
    force_seed=False,
):
    """
  If schedule is empty or only has a placeholder summary row, seed start/end from project.
  Returns True when schedule payload was updated.
    """
    start = _format_gantt_date(getattr(project, 'start_date', None))
    end = _format_gantt_date(getattr(project, 'end_date', None))
    if not start or not end:
        return False

    pid = int(project.id)
    record = ScheduleData.query.filter_by(project_id=pid).first()
    payload = _parse_payload(record)

    if payload and _has_meaningful_schedule(payload) and not force_seed:
        return False

    project_name = project.name or 'Project Schedule'
    project_number = getattr(project, 'number', '') or ''
    summary_text = f'{project_number} — {project_name}'.strip(' —') if project_number else project_name

    if not payload:
        payload = {'data': [], 'links': []}

    data = payload.get('data') or []
    summary = next((t for t in data if t.get('type') == 'project'), None)
    if not summary:
        summary = {
            'id': 1,
            'text': summary_text,
            'type': 'project',
            'open': True,
            'progress': 0,
        }
        data.insert(0, summary)
        payload['data'] = data

    summary['text'] = summary_text
    summary['start_date'] = start
    summary['end_date'] = end
    summary['duration'] = 0
    summary['progress'] = getattr(project, 'percent_complete', 0) or 0

    if not record:
        record = ScheduleData(project_id=pid, payload=json.dumps(payload))
        db.session.add(record)
    else:
        record.payload = json.dumps(payload)
    return True
