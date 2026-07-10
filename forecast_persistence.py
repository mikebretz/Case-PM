"""Financial forecast summary — aggregates budget, pay apps, and project context."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta


def _parse_state(record):
    if not record or not getattr(record, 'data_json', None):
        return {}
    try:
        return json.loads(record.data_json)
    except (TypeError, json.JSONDecodeError):
        return {}


def _sum_pay_app_paid(pay_state):
    """Total owner/G702 billed from approved pay app periods."""
    total = 0.0
    history = pay_state.get('payAppHistory') or []
    if isinstance(history, list):
        for period in history:
            if not isinstance(period, dict):
                continue
            amt = period.get('totalBilledThisPeriod')
            if amt is None:
                amt = period.get('currentPaymentDue') or period.get('amountDue') or 0
            total += float(amt or 0)
    return total


def _sum_sub_paid(pay_state):
    """Total subcontractor pay apps approved/billed."""
    total = 0.0
    sub_hist = pay_state.get('subPayAppHistory') or {}
    if isinstance(sub_hist, dict):
        for company_periods in sub_hist.values():
            if not isinstance(company_periods, dict):
                continue
            for entry in company_periods.values():
                if isinstance(entry, dict):
                    total += float(entry.get('totalBilledThisPeriod') or 0)
    return total


def build_forecast_summary(project, budget_state, pay_state, approved_co_total=0.0):
    """Build forecast chart categories and projection inputs."""
    lines = budget_state.get('budgetLines') or []
    original = sum(float(l.get('original_budget') or 0) for l in lines)
    approved_changes = sum(float(l.get('approved_changes') or 0) for l in lines)
    pending = sum(float(l.get('pending') or 0) for l in lines)
    committed = sum(float(l.get('committed') or 0) for l in lines)
    actual = sum(float(l.get('actual') or 0) for l in lines)
    revised = original + approved_changes
    variance = revised - actual

    owner_paid = _sum_pay_app_paid(pay_state)
    sub_paid = _sum_sub_paid(pay_state)
    paid_out = owner_paid + sub_paid

    details = project.get_details() if project and hasattr(project, 'get_details') else {}
    contract = None
    if project:
        orig_contract = details.get('original_contract_amount')
        if orig_contract not in (None, ''):
            contract = float(orig_contract)
        elif project.contract_value:
            contract = float(project.contract_value)

    start = getattr(project, 'start_date', None) if project else None
    end = getattr(project, 'end_date', None) if project else None
    today = date.today()
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()

    days_elapsed = max((today - start).days, 1) if start else 30
    days_total = max((end - start).days, days_elapsed) if start and end else max(days_elapsed, 90)
    days_remaining = max((end - today).days, 0) if end else max(days_total - days_elapsed, 0)

    burn_daily = actual / days_elapsed if days_elapsed else 0
    pct_complete = min(100.0, (actual / revised * 100) if revised else 0)

    categories = [
        {'key': 'original', 'label': 'Original Budget', 'amount': original, 'color': '#34d399'},
        {'key': 'approved_co', 'label': 'Approved COs', 'amount': approved_changes, 'color': '#fbbf24'},
        {'key': 'pending', 'label': 'Pending Changes', 'amount': pending, 'color': '#fb923c'},
        {'key': 'committed', 'label': 'Committed', 'amount': committed, 'color': '#a78bfa'},
        {'key': 'revised', 'label': 'Revised Budget', 'amount': revised, 'color': '#10b981'},
        {'key': 'actual', 'label': 'Actual Cost', 'amount': actual, 'color': '#38bdf8'},
        {'key': 'paid', 'label': 'Paid Out', 'amount': paid_out, 'color': '#6366f1'},
        {'key': 'variance', 'label': 'Variance', 'amount': variance, 'color': '#22c55e' if variance >= 0 else '#ef4444'},
    ]

    return {
        'original_budget': original,
        'approved_changes': approved_changes,
        'pending_changes': pending,
        'committed': committed,
        'revised_budget': revised,
        'actual_cost': actual,
        'variance': variance,
        'paid_out': paid_out,
        'owner_paid': owner_paid,
        'sub_paid': sub_paid,
        'contract_amount': contract,
        'approved_co_total': float(approved_co_total or 0),
        'percent_complete': round(pct_complete, 1),
        'burn_rate_daily': burn_daily,
        'burn_rate_weekly': burn_daily * 7,
        'days_elapsed': days_elapsed,
        'days_remaining': days_remaining,
        'days_total': days_total,
        'start_date': start.isoformat() if start else None,
        'end_date': end.isoformat() if end else None,
        'categories': categories,
        'projections': _build_projections(
            revised, actual, burn_daily, days_remaining, days_total, days_elapsed,
        ),
    }


def _build_projections(revised, actual, burn_daily, days_remaining, days_total, days_elapsed):
    """Simple linear projections for forecast horizons."""
    horizons = [
        ('week', 7),
        ('two_weeks', 14),
        ('four_weeks', 28),
        ('full_job', days_remaining or max(days_total - days_elapsed, 0)),
    ]
    out = {}
    for key, days in horizons:
        horizon_days = max(int(days), 0)
        projected_spend = actual + (burn_daily * horizon_days)
        projected_pct = min(100.0, (projected_spend / revised * 100) if revised else 0)
        out[key] = {
            'days': horizon_days,
            'projected_cost': projected_spend,
            'projected_variance': revised - projected_spend,
            'projected_percent_complete': round(projected_pct, 1),
        }
    return out
