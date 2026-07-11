"""Weekly / biweekly log — compiles daily logs into an editable rollup report.

Reads the daily logs in a date range and aggregates manpower, equipment, deliveries,
delays, visitors, safety, and inspections into a single report the user can then edit
(add or remove rows). Structured sections are stored in WeeklyReport.details_json.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta

SECTION_KEYS = (
    'daily_summaries',  # [{date, work}]
    'manpower',         # [{company, days, workers, hours}]
    'equipment',        # [{equipment_name, days, notes}]
    'deliveries',       # [{item, supplier, quantity}]
    'delays',           # [{type, description, hours_lost}]
    'visitors',         # [{name, company, purpose}]
    'safety',           # [{type, description, action}]
    'inspections',      # [{type, agency, result, notes}]
)


def _parse(value, default):
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else default
    except (TypeError, json.JSONDecodeError):
        return default


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _clean_rows(rows, keys):
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cleaned = {k: row.get(k) for k in keys}
        if any(v not in (None, '', 0) for v in cleaned.values()):
            out.append(cleaned)
    return out


def build_details(payload):
    payload = payload or {}
    return {
        'daily_summaries': _clean_rows(payload.get('daily_summaries'), ('date', 'work')),
        'manpower': _clean_rows(payload.get('manpower'), ('company', 'days', 'workers', 'hours')),
        'equipment': _clean_rows(payload.get('equipment'), ('equipment_name', 'days', 'notes')),
        'deliveries': _clean_rows(payload.get('deliveries'), ('item', 'supplier', 'quantity')),
        'delays': _clean_rows(payload.get('delays'), ('type', 'description', 'hours_lost')),
        'visitors': _clean_rows(payload.get('visitors'), ('name', 'company', 'purpose')),
        'safety': _clean_rows(payload.get('safety'), ('type', 'description', 'action')),
        'inspections': _clean_rows(payload.get('inspections'), ('type', 'agency', 'result', 'notes')),
    }


def _details_totals(details):
    manpower = details.get('manpower') or []
    total_hours = sum(_f(m.get('hours')) for m in manpower)
    total_workers = sum(_i(m.get('workers')) for m in manpower)
    return {
        'total_hours': round(total_hours, 1),
        'total_workers': total_workers,
        'delay_count': len(details.get('delays') or []),
        'safety_count': len(details.get('safety') or []),
        'day_count': len(details.get('daily_summaries') or []),
    }


def serialize_report(report, User=None, summary=False):
    details = _parse(getattr(report, 'details_json', None), {})
    totals = _details_totals(details)
    author = ''
    if User is not None and report.created_by_id:
        u = User.query.get(report.created_by_id)
        if u:
            author = f'{u.first_name} {u.last_name}'.strip()
    base = {
        'id': report.id,
        'project_id': report.project_id,
        'period_type': getattr(report, 'period_type', None) or 'weekly',
        'period_start': report.period_start.isoformat() if getattr(report, 'period_start', None) else None,
        'period_end': report.period_end.isoformat() if getattr(report, 'period_end', None) else (report.week_ending.isoformat() if report.week_ending else None),
        'week_ending': report.week_ending.isoformat() if report.week_ending else None,
        'work_performed': report.work_performed,
        'safety_notes': report.safety_notes,
        'notes': getattr(report, 'notes', None),
        'status': report.status or 'Draft',
        'author': author,
        'created_at': report.created_at.isoformat() if report.created_at else None,
        **totals,
    }
    if summary:
        return base
    base['details'] = details
    return base


def compute_stats(WeeklyReport, project_id):
    q = WeeklyReport.query
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    reports = q.all()
    today = date.today()
    month_start = today.replace(day=1)
    this_month = sum(1 for r in reports if (r.period_end or r.week_ending) and (r.period_end or r.week_ending) >= month_start)
    total_hours = 0.0
    delays = 0
    for r in reports:
        d = _parse(getattr(r, 'details_json', None), {})
        t = _details_totals(d)
        total_hours += t['total_hours']
        delays += t['delay_count']
    return {
        'total_reports': len(reports),
        'this_month': this_month,
        'total_man_hours': round(total_hours, 1),
        'open_delays': delays,
    }


def compile_from_daily_logs(DailyLog, ManpowerEntry, EquipmentEntry, project_id, start, end):
    """Aggregate all daily logs in [start, end] into an editable weekly-report details dict."""
    logs = (
        DailyLog.query
        .filter(DailyLog.project_id == int(project_id))
        .filter(DailyLog.date >= start)
        .filter(DailyLog.date <= end)
        .order_by(DailyLog.date.asc())
        .all()
    )
    log_ids = [l.id for l in logs]

    daily_summaries = []
    for l in logs:
        if l.work_performed:
            daily_summaries.append({'date': l.date.isoformat() if l.date else '', 'work': l.work_performed})

    # Manpower rollup by company: days on site, total workers (man-days), total hours.
    man_by_company = defaultdict(lambda: {'days': set(), 'workers': 0, 'hours': 0.0})
    if log_ids:
        entries = ManpowerEntry.query.filter(ManpowerEntry.daily_log_id.in_(log_ids)).all()
        log_date = {l.id: l.date for l in logs}
        for e in entries:
            key = (e.company or 'Unknown').strip() or 'Unknown'
            man_by_company[key]['days'].add(log_date.get(e.daily_log_id))
            man_by_company[key]['workers'] += _i(e.personnel_count)
            man_by_company[key]['hours'] += _f(e.hours)
    manpower = [
        {'company': c, 'days': len([d for d in v['days'] if d]), 'workers': v['workers'], 'hours': round(v['hours'], 1)}
        for c, v in sorted(man_by_company.items())
    ]

    # Equipment rollup: unique equipment, days seen.
    eq_by_name = defaultdict(lambda: {'days': 0, 'notes': ''})
    if log_ids:
        for e in EquipmentEntry.query.filter(EquipmentEntry.daily_log_id.in_(log_ids)).all():
            name = (e.equipment_name or '').strip()
            if not name:
                continue
            eq_by_name[name]['days'] += 1
            if e.condition and not eq_by_name[name]['notes']:
                eq_by_name[name]['notes'] = e.condition
    equipment = [{'equipment_name': n, 'days': v['days'], 'notes': v['notes']} for n, v in sorted(eq_by_name.items())]

    # Concatenate list-type sections from each daily log's details_json.
    deliveries, delays, visitors, safety, inspections = [], [], [], [], []
    for l in logs:
        d = _parse(getattr(l, 'details_json', None), {})
        dstr = l.date.isoformat() if l.date else ''
        for x in d.get('deliveries') or []:
            deliveries.append({'item': x.get('item'), 'supplier': x.get('supplier'), 'quantity': x.get('quantity')})
        for x in d.get('delays') or []:
            delays.append({'type': x.get('type'), 'description': f"{dstr}: {x.get('description') or ''}".strip(': '), 'hours_lost': x.get('hours_lost')})
        for x in d.get('visitors') or []:
            visitors.append({'name': x.get('name'), 'company': x.get('company'), 'purpose': x.get('purpose')})
        for x in d.get('safety') or []:
            safety.append({'type': x.get('type'), 'description': f"{dstr}: {x.get('description') or ''}".strip(': '), 'action': x.get('action')})
        for x in d.get('inspections') or []:
            inspections.append({'type': x.get('type'), 'agency': x.get('agency'), 'result': x.get('result'), 'notes': x.get('notes')})

    narrative = '\n'.join(f"{s['date']}: {s['work']}" for s in daily_summaries)

    return {
        'log_count': len(logs),
        'work_performed': narrative,
        'details': {
            'daily_summaries': daily_summaries,
            'manpower': manpower,
            'equipment': equipment,
            'deliveries': _clean_rows(deliveries, ('item', 'supplier', 'quantity')),
            'delays': _clean_rows(delays, ('type', 'description', 'hours_lost')),
            'visitors': _clean_rows(visitors, ('name', 'company', 'purpose')),
            'safety': _clean_rows(safety, ('type', 'description', 'action')),
            'inspections': _clean_rows(inspections, ('type', 'agency', 'result', 'notes')),
        },
    }


def default_period(period_type='weekly', end=None):
    """Return (start, end) for a weekly or biweekly period ending on `end` (default today)."""
    end = end or date.today()
    span = 13 if period_type == 'biweekly' else 6
    return end - timedelta(days=span), end
