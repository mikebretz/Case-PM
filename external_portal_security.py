"""External portal security — financial redaction and module caps for consultant/sub users."""
from __future__ import annotations

from typing import Any

# Dollar / cost fields that must not leak when hide_financials is set.
FINANCIAL_DATA_KEYS = frozenset({
    'amount',
    'quoted_amount',
    'rom_amount',
    'pending_co_amount',
    'approved_total',
    'pending_total',
    'pco_rom_total',
    'contract_amount',
    'original_budget',
    'revised_budget',
    'actual_cost',
    'variance',
    'committed',
    'paid_out',
    'forecast_to_complete',
    'estimated_cost_at_completion',
    'projected_over_under',
    'pending_changes',
    'billing_variance',
    'owner_sub_variance',
    'total_variance',
    'cost_impact_amount',
})


def user_should_hide_financials(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    try:
        from access_control import user_global_flags
        return bool(user_global_flags(user).get('hide_financials'))
    except Exception:
        return False


def redact_financial_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return None
    if isinstance(value, str) and value.strip().startswith(('$', '€', '£')):
        return None
    return None


def redact_financial_fields(payload: Any, *, keys: frozenset[str] | None = None) -> Any:
    """Recursively remove or null financial amounts from API payloads."""
    keyset = keys or FINANCIAL_DATA_KEYS
    if isinstance(payload, dict):
        out = {}
        for key, val in payload.items():
            if key in keyset:
                out[key] = redact_financial_value(val)
            elif key == 'allocations' and isinstance(val, list):
                out[key] = [
                    redact_financial_fields(row, keys=keyset) if isinstance(row, dict) else row
                    for row in val
                ]
            elif key == 'financial' and isinstance(val, dict):
                out[key] = {k: None for k in val}
            elif key in ('commitments', 'change_orders', 'forecast_chart', 'erp_queue', 'billing_variance', 'estimating'):
                out[key] = redact_financial_fields(val, keys=keyset)
            else:
                out[key] = redact_financial_fields(val, keys=keyset)
        return out
    if isinstance(payload, list):
        return [redact_financial_fields(item, keys=keyset) for item in payload]
    return payload


def redact_dashboard_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    cleaned = dict(payload)
    for block in ('financial', 'forecast_chart', 'commitments', 'erp_queue', 'billing_variance', 'estimating'):
        cleaned.pop(block, None)
    kpis = dict(cleaned.get('kpis') or {})
    kpis.pop('pending_co_amount', None)
    kpis.pop('week_hours', None)
    cleaned['kpis'] = kpis
    open_items = dict(cleaned.get('open_items') or {})
    open_items.pop('pending_co_amount', None)
    cleaned['open_items'] = open_items
    co_block = dict(cleaned.get('change_orders') or {})
    for key in ('approved_total', 'pending_total', 'pco_rom_total'):
        co_block.pop(key, None)
    if co_block:
        cleaned['change_orders'] = co_block
    cleaned['external_portal'] = True
    return cleaned


def redact_portfolio_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    projects = []
    for snap in payload.get('projects') or []:
        if not isinstance(snap, dict):
            continue
        row = dict(snap)
        row.pop('financial', None)
        co = dict(row.get('change_orders') or {})
        for key in ('approved_total', 'pending_total', 'pco_rom_total'):
            co.pop(key, None)
        if co:
            row['change_orders'] = co
        projects.append(row)
    return {
        'generated_at': payload.get('generated_at'),
        'accessible_count': payload.get('accessible_count'),
        'active_count': payload.get('active_count'),
        'projects': projects,
        'external_portal': True,
    }
