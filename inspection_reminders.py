"""Permits & inspections — notifications and calendar-style reminders."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

import case_workflow as cw

from florida_permit_catalog import OPEN_STATUSES

REMINDER_OPTIONS = (
    {'key': 'morning_of', 'label': 'Morning of (8:00 AM)'},
    {'key': '1d', 'label': '1 day before'},
    {'key': '1h', 'label': '1 hour before'},
    {'key': '15m', 'label': '15 minutes before'},
)

DEFAULT_REMINDER_OFFSETS = ('morning_of', '1h')


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        import json
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def get_notification_settings(item):
    details = _parse_json(getattr(item, 'details_json', None), {})
    notif = details.get('notifications') if isinstance(details.get('notifications'), dict) else {}
    offsets = notif.get('reminder_offsets') or list(DEFAULT_REMINDER_OFFSETS)
    return {
        'notify_user_ids': [int(x) for x in (notif.get('notify_user_ids') or []) if x],
        'notify_creator': notif.get('notify_creator', True),
        'reminder_offsets': [str(x) for x in offsets if x],
        'reminders_sent': notif.get('reminders_sent') if isinstance(notif.get('reminders_sent'), dict) else {},
    }


def apply_notification_settings(item, body):
    import json

    details = _parse_json(getattr(item, 'details_json', None), {})
    if not isinstance(details, dict):
        details = {}
    old = get_notification_settings(item)
    new_ids = body.get('notify_user_ids')
    if new_ids is None and 'notify_user_id' in body:
        new_ids = [body['notify_user_id']] if body.get('notify_user_id') else []
    if new_ids is not None:
        notify_user_ids = [int(x) for x in new_ids if x]
    else:
        notify_user_ids = old['notify_user_ids']
    notify_creator = body.get('notify_creator') if 'notify_creator' in body else old['notify_creator']
    reminder_offsets = body.get('reminder_offsets') if body.get('reminder_offsets') is not None else old['reminder_offsets']
    if not reminder_offsets:
        reminder_offsets = list(DEFAULT_REMINDER_OFFSETS)
    reminders_sent = old['reminders_sent']
    details['notifications'] = {
        'notify_user_ids': notify_user_ids,
        'notify_creator': bool(notify_creator),
        'reminder_offsets': reminder_offsets,
        'reminders_sent': reminders_sent,
    }
    item.details_json = json.dumps(details)
    return details['notifications']


def parse_inspection_time(time_str, default_hour=9, default_minute=0):
    if not time_str or not str(time_str).strip():
        return default_hour, default_minute
    s = str(time_str).strip().upper()
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?', s)
    if not m:
        return default_hour, default_minute
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = m.group(3)
    if meridiem == 'PM' and hour < 12:
        hour += 12
    if meridiem == 'AM' and hour == 12:
        hour = 0
    return max(0, min(23, hour)), max(0, min(59, minute))


def event_datetime(item):
    if not item.scheduled_date:
        return None
    hour, minute = parse_inspection_time(getattr(item, 'scheduled_time', None))
    d = item.scheduled_date
    if isinstance(d, datetime):
        d = d.date()
    return datetime.combine(d, time(hour, minute))


def reminder_fire_at(item, offset_key):
    ev = event_datetime(item)
    if not ev:
        return None
    if offset_key == 'morning_of':
        return datetime.combine(ev.date(), time(8, 0))
    deltas = {'1d': timedelta(days=1), '1h': timedelta(hours=1), '15m': timedelta(minutes=15)}
    delta = deltas.get(offset_key)
    if not delta:
        return None
    return ev - delta


def inspection_action_url(item):
    pid = item.project_id
    return f'/inspections?project_id={pid}&open=1&item_id={item.id}' if pid else f'/inspections?open=1&item_id={item.id}'


def _format_schedule_line(item):
    parts = []
    if item.scheduled_date:
        parts.append(item.scheduled_date.strftime('%A, %B %d, %Y'))
    if getattr(item, 'scheduled_time', None):
        parts.append(str(item.scheduled_time))
    if getattr(item, 'location', None):
        parts.append(f'Location: {item.location}')
    return ' · '.join(parts) if parts else 'Date TBD'


def _notification_body_html(item, headline, extra=''):
    kind = (item.record_kind or 'inspection').replace('_', ' ').title()
    return f'''<p><strong>{headline}</strong></p>
<p><strong>{kind}:</strong> {item.title or item.item_number}</p>
<p><strong>When:</strong> {_format_schedule_line(item)}</p>
{f'<p><strong>Jurisdiction:</strong> {item.jurisdiction_name}</p>' if getattr(item, 'jurisdiction_name', None) else ''}
{f'<p><strong>Inspector:</strong> {item.inspector}</p>' if getattr(item, 'inspector', None) else ''}
{f'<p><strong>Status:</strong> {item.status}</p>' if getattr(item, 'status', None) else ''}
{extra}'''


def collect_recipient_ids(item, settings, User, extra_user_id=None):
    ids = set()
    if settings.get('notify_creator') and getattr(item, 'created_by_id', None):
        ids.add(int(item.created_by_id))
    for uid in settings.get('notify_user_ids') or []:
        if uid:
            ids.add(int(uid))
    if extra_user_id:
        ids.add(int(extra_user_id))
    active = {u.id for u in User.query.filter_by(status='Active').all()}
    return [uid for uid in ids if uid in active]


def send_inspection_notification(item, User, *, title, preview, actor_id=None, recipient_ids=None, priority='normal'):
    settings = get_notification_settings(item)
    targets = recipient_ids or collect_recipient_ids(item, settings, User)
    if actor_id:
        targets = [uid for uid in targets if uid != int(actor_id)] or targets
    action_url = inspection_action_url(item)
    body = _notification_body_html(item, preview)
    for uid in targets:
        cw.notify_user(uid, title, preview, action_url)
        cw.create_internal_message(
            uid,
            folder='action-required' if priority == 'high' else 'alerts',
            msg_type='alert',
            subject=title,
            preview=preview[:500],
            body=body,
            project_id=item.project_id,
            from_label='Permits & Inspections',
            from_user_id=actor_id,
            module='Inspections',
            action_url=action_url,
            action_label='View Inspection',
            priority=priority,
            requires_action=priority == 'high',
        )
    return targets


def notify_scheduled(item, User, actor_id=None):
    if not item.scheduled_date:
        return []
    if (item.status or '') not in OPEN_STATUSES:
        return []
    title = f'Inspection scheduled — {item.title or item.item_number}'
    preview = f'{item.item_number or "Inspection"} on {_format_schedule_line(item)}'
    return send_inspection_notification(item, User, title=title, preview=preview, actor_id=actor_id, priority='high')


def notify_manual(item, User, actor_id=None, user_ids=None):
    title = f'Reminder: {item.title or item.item_number}'
    preview = f'Upcoming {item.record_kind or "inspection"} — {_format_schedule_line(item)}'
    settings = get_notification_settings(item)
    targets = user_ids or collect_recipient_ids(item, settings, User, extra_user_id=actor_id)
    if actor_id and actor_id not in targets:
        targets.append(int(actor_id))
    return send_inspection_notification(
        item, User, title=title, preview=preview, actor_id=actor_id,
        recipient_ids=targets, priority='high',
    )


def _mark_reminder_sent(item, offset_key):
    import json

    details = _parse_json(getattr(item, 'details_json', None), {})
    notif = details.get('notifications') if isinstance(details.get('notifications'), dict) else {}
    sent = notif.get('reminders_sent') if isinstance(notif.get('reminders_sent'), dict) else {}
    sent[offset_key] = datetime.utcnow().isoformat() + 'Z'
    notif['reminders_sent'] = sent
    details['notifications'] = {
        **get_notification_settings(item),
        **notif,
        'reminders_sent': sent,
    }
    item.details_json = json.dumps(details)


def _reminder_title(item, offset_key):
    labels = {opt['key']: opt['label'] for opt in REMINDER_OPTIONS}
    label = labels.get(offset_key, 'Reminder')
    return f'{label}: {item.title or item.item_number}'


def process_item_reminders(item, User, now=None):
    if not item.scheduled_date:
        return 0
    if (item.status or '') not in OPEN_STATUSES:
        return 0
    now = now or datetime.utcnow()
    settings = get_notification_settings(item)
    sent = settings.get('reminders_sent') or {}
    fired = 0
    ev = event_datetime(item)
    if not ev:
        return 0
    for offset_key in settings.get('reminder_offsets') or []:
        if sent.get(offset_key):
            continue
        fire_at = reminder_fire_at(item, offset_key)
        if not fire_at or now < fire_at:
            continue
        if now > ev + timedelta(hours=2):
            continue
        title = _reminder_title(item, offset_key)
        preview = f'{item.item_number or "Inspection"} — {_format_schedule_line(item)}'
        send_inspection_notification(item, User, title=title, preview=preview, priority='normal')
        _mark_reminder_sent(item, offset_key)
        fired += 1
    return fired


def process_due_reminders(Item, User, project_id=None, now=None):
    now = now or datetime.utcnow()
    window_start = (now - timedelta(days=1)).date()
    window_end = (now + timedelta(days=60)).date()
    q = Item.query.filter(
        Item.scheduled_date.isnot(None),
        Item.scheduled_date >= window_start,
        Item.scheduled_date <= window_end,
    )
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    total = 0
    for item in q.all():
        total += process_item_reminders(item, User, now=now)
    return total


def clear_reminders_sent(item):
    import json

    details = _parse_json(getattr(item, 'details_json', None), {})
    notif = get_notification_settings(item)
    notif['reminders_sent'] = {}
    details['notifications'] = notif
    item.details_json = json.dumps(details)


def serialize_notification_fields(item):
    settings = get_notification_settings(item)
    return {
        'notify_user_ids': settings['notify_user_ids'],
        'notify_creator': settings['notify_creator'],
        'reminder_offsets': settings['reminder_offsets'],
        'reminders_sent': settings['reminders_sent'],
        'reminder_options': REMINDER_OPTIONS,
    }
