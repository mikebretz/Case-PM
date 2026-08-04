"""Project cost code library — shared catalog for Budget, Pay Apps, COs, and commitments.

Stored in budget project state (same persistence as budget lines) so one project
has a single source of truth, similar to job cost code lists in Sage / Procore.
"""
from __future__ import annotations

from budget_persistence import BUDGET_STATE_KEYS, merge_state_patch, normalize_cost_code

LIBRARY_PATCH_KEYS = frozenset({
    'costTypes',
    'customCostCodes',
    'activeCostCodeList',
    'costCodeLists',
})


def library_slice_from_state(state: dict | None) -> dict:
    """Settings that define the cost code library (not budget line dollars)."""
    data = state or {}
    return {
        'costTypes': list(data.get('costTypes') or []),
        'customCostCodes': list(data.get('customCostCodes') or []),
        'activeCostCodeList': data.get('activeCostCodeList') or 'csi',
        'costCodeLists': dict(data.get('costCodeLists') or {}),
    }


def merge_library_patch(existing_state: dict, patch: dict) -> dict:
    """Apply library-only fields onto full budget state."""
    filtered = {k: v for k, v in (patch or {}).items() if k in LIBRARY_PATCH_KEYS}
    return merge_state_patch(existing_state or {}, filtered)


def picker_cost_codes(state: dict | None) -> list[dict]:
    """Merged list for dropdowns: budget lines first, then custom library codes."""
    data = state or {}
    lines = data.get('budgetLines') or []
    custom = data.get('customCostCodes') or []
    codes = []
    seen = set()
    for line in lines:
        if not isinstance(line, dict):
            continue
        code = line.get('cost_code')
        if code and code not in seen:
            seen.add(code)
            codes.append({
                'code': code,
                'description': line.get('description', ''),
                'cost_type': line.get('cost_type', ''),
                'source': 'budget',
                'original_budget': line.get('original_budget', 0),
                'approved_changes': line.get('approved_changes', 0),
                'pending': line.get('pending', 0),
            })
    for item in custom:
        if not isinstance(item, dict):
            continue
        code = item.get('code')
        if code and code not in seen:
            seen.add(code)
            codes.append({
                'code': code,
                'description': item.get('description', ''),
                'cost_type': item.get('cost_type', ''),
                'source': 'library',
                'original_budget': 0,
                'approved_changes': 0,
                'pending': 0,
            })
    return codes


def library_summary(state: dict | None) -> dict:
    picker = picker_cost_codes(state)
    lib = library_slice_from_state(state)
    return {
        'library': lib,
        'picker_count': len(picker),
        'budget_line_codes': sum(1 for c in picker if c.get('source') == 'budget'),
        'custom_codes': len(lib.get('customCostCodes') or []),
        'cost_types_count': len(lib.get('costTypes') or []),
        'active_cost_code_list': lib.get('activeCostCodeList'),
    }


def normalize_picker_query(code: str) -> str:
    return normalize_cost_code(code)
