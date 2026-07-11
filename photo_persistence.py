"""Photo serialization, date grouping, and stats for the Photos module."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timedelta


def _photo_date(photo) -> date | None:
    if getattr(photo, 'taken_date', None):
        return photo.taken_date
    if getattr(photo, 'taken_at', None):
        return photo.taken_at.date()
    if getattr(photo, 'created_at', None):
        return photo.created_at.date()
    return None


def serialize_photo(photo, user=None, url_helpers=None):
    """Serialize a Photo row for API responses."""
    taken = _photo_date(photo)
    uploader = user
    if not uploader and getattr(photo, 'uploaded_by_id', None):
        uploader = getattr(photo, 'uploader', None)
    uploaded_by = ''
    if uploader:
        uploaded_by = f'{getattr(uploader, "first_name", "")} {getattr(uploader, "last_name", "")}'.strip()
    url = None
    if url_helpers:
        if getattr(photo, 'document_id', None) and url_helpers.get('doc'):
            url = url_helpers['doc'](photo.document_id)
        elif getattr(photo, 'filename', None) and getattr(photo, 'project_id', None) and url_helpers.get('photo'):
            url = url_helpers['photo'](photo.project_id, photo.filename)
    return {
        'id': photo.id,
        'project_id': photo.project_id,
        'caption': photo.caption or photo.filename,
        'location': getattr(photo, 'location', None) or photo.category or '',
        'category': photo.category or '',
        'filename': photo.filename,
        'taken_date': taken.isoformat() if taken else None,
        'taken_at': photo.taken_at.isoformat() if getattr(photo, 'taken_at', None) else None,
        'uploaded_at': photo.created_at.isoformat() if getattr(photo, 'created_at', None) else None,
        'uploaded_by': uploaded_by,
        'uploaded_by_id': photo.uploaded_by_id,
        'document_id': getattr(photo, 'document_id', None),
        'daily_log_id': getattr(photo, 'daily_log_id', None),
        'url': url,
    }


def group_photos_by_date(photos_serialized, group_mode='day'):
    """Group serialized photos into timeline sections (Procore-style day/week/month)."""
    buckets = OrderedDict()

    def bucket_key(d: date):
        if group_mode == 'month':
            return d.strftime('%Y-%m')
        if group_mode == 'week':
            iso = d.isocalendar()
            return f'{iso.year}-W{iso.week:02d}'
        return d.isoformat()

    def bucket_label(key, sample_date: date):
        if group_mode == 'month':
            return sample_date.strftime('%B %Y')
        if group_mode == 'week':
            start = sample_date - timedelta(days=sample_date.weekday())
            end = start + timedelta(days=6)
            return f'Week of {start.strftime("%b %d")} – {end.strftime("%b %d, %Y")}'
        return sample_date.strftime('%A, %B %d, %Y')

    for p in photos_serialized:
        td = p.get('taken_date')
        if not td:
            key = 'unknown'
            label = 'Undated'
        else:
            try:
                d = date.fromisoformat(td[:10])
            except (TypeError, ValueError):
                key = 'unknown'
                label = 'Undated'
            else:
                key = bucket_key(d)
                label = bucket_label(key, d)
        if key not in buckets:
            buckets[key] = {'key': key, 'label': label, 'photos': []}
        buckets[key]['photos'].append(p)

    return list(buckets.values())


def filter_photos_by_range(photos_serialized, range_key):
    """Filter photos by today / week / month."""
    if not range_key:
        return photos_serialized
    today = date.today()
    if range_key == 'today':
        start = today
    elif range_key == 'week':
        start = today - timedelta(days=today.weekday())
    elif range_key == 'month':
        start = today.replace(day=1)
    else:
        return photos_serialized
    out = []
    for p in photos_serialized:
        td = p.get('taken_date')
        if not td:
            continue
        try:
            d = date.fromisoformat(td[:10])
        except (TypeError, ValueError):
            continue
        if d >= start:
            out.append(p)
    return out


def compute_photo_stats(photos_serialized):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    total = len(photos_serialized)
    today_count = week_count = month_count = 0
    locations = set()
    for p in photos_serialized:
        loc = (p.get('location') or '').strip()
        if loc:
            locations.add(loc)
        td = p.get('taken_date')
        if not td:
            continue
        try:
            d = date.fromisoformat(td[:10])
        except (TypeError, ValueError):
            continue
        if d == today:
            today_count += 1
        if d >= week_start:
            week_count += 1
        if d >= month_start:
            month_count += 1
    return {
        'total': total,
        'today': today_count,
        'this_week': week_count,
        'this_month': month_count,
        'locations': sorted(locations),
    }
