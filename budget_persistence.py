"""Budget server persistence, change order budget sync, and schema helpers."""
from __future__ import annotations

import json
from datetime import datetime

BUDGET_STATE_KEYS = (
    'budgetLines',
    'budgetRevision',
    'budgetLocked',
    'budgetSnapshots',
    'publishAuditLog',
    'budgetAuditLog',
    'costTypes',
    'customCostCodes',
    'activeCostCodeList',
    'budgetContractAmount',
    'budgetPublished',
    'budgetSageSyncAutoEnabled',
)

PENDING_CO_STATUSES = ('Submitted', 'Under Review', 'Pending', 'Pending Architect', 'Pending Owner', 'Pending Accounting')
APPROVED_CO_STATUS = 'Approved'
REJECTED_CO_STATUS = 'Rejected'


def normalize_cost_code(code):
    if not code:
        return ''
    return str(code).replace(' ', '').replace('-', '').upper()


def _parse_state(record):
    if not record or not record.data_json:
        return {}
    try:
        return json.loads(record.data_json)
    except (TypeError, json.JSONDecodeError):
        return {}


def get_budget_state(BudgetProjectState, project_id):
    record = BudgetProjectState.query.filter_by(project_id=project_id).first()
    if not record:
        return None, {}
    return record, _parse_state(record)


def save_budget_state(BudgetProjectState, db, project_id, data, user_id=None):
    if not isinstance(data, dict):
        raise ValueError('data must be a dict')
    record = BudgetProjectState.query.filter_by(project_id=project_id).first()
    payload = json.dumps(data)
    if record:
        record.data_json = payload
        record.version = (record.version or 0) + 1
        record.updated_by_id = user_id
        record.updated_at = datetime.utcnow()
    else:
        record = BudgetProjectState(
            project_id=project_id,
            data_json=payload,
            version=1,
            updated_by_id=user_id,
        )
        db.session.add(record)
    db.session.commit()
    return record


def merge_state_patch(existing, patch):
    merged = dict(existing or {})
    for key, value in (patch or {}).items():
        if key in BUDGET_STATE_KEYS or key.startswith('_'):
            merged[key] = value
    return merged


def _find_budget_line(lines, cost_code, cost_type=None):
    target = normalize_cost_code(cost_code)
    if not target:
        return None
    matches = [line for line in lines if normalize_cost_code(line.get('cost_code')) == target]
    if not matches:
        return None
    if cost_type:
        ctype = str(cost_type).strip()
        for line in matches:
            if (line.get('cost_type') or '').strip() == ctype:
                return line
        return None
    return matches[0]


def apply_co_amount_to_budget_line(line, amount, mode):
    amt = float(amount or 0)
    if mode == 'pending':
        line['pending'] = float(line.get('pending') or 0) + amt
    elif mode == 'approved':
        pending = float(line.get('pending') or 0)
        if pending >= amt:
            line['pending'] = pending - amt
        else:
            line['pending'] = 0
        line['approved_changes'] = float(line.get('approved_changes') or 0) + amt
    elif mode == 'reject':
        pending = float(line.get('pending') or 0)
        line['pending'] = max(0.0, pending - amt)
    return line


def apply_co_to_budget_lines(state_data, amount, cost_code=None, cost_type=None, description=None, mode='approved'):
    lines = state_data.get('budgetLines') or []
    if not isinstance(lines, list):
        lines = []
    remaining = float(amount or 0)
    applied = 0.0
    line_desc = (description or '').strip() or (f'Change Order — {cost_code}' if cost_code else 'Change Order')

    if cost_code:
        line = _find_budget_line(lines, cost_code, cost_type)
        if line:
            apply_co_amount_to_budget_line(line, remaining, mode)
            applied = remaining
        elif mode in ('pending', 'approved'):
            new_line = {
                'id': int(datetime.utcnow().timestamp() * 1000),
                'cost_code': cost_code,
                'description': line_desc,
                'cost_type': cost_type or 'Other',
                'original_budget': 0,
                'approved_changes': remaining if mode == 'approved' else 0,
                'pending': remaining if mode == 'pending' else 0,
                'notes': 'Auto-created from change order',
                'actual': 0,
                'syncStatus': 'Pending',
                'percent_complete': 0,
            }
            lines.append(new_line)
            applied = remaining
    else:
        if lines:
            apply_co_amount_to_budget_line(lines[0], remaining, mode)
            applied = remaining
        elif mode in ('pending', 'approved'):
            lines.append({
                'id': int(datetime.utcnow().timestamp() * 1000),
                'cost_code': '01-0000',
                'description': 'Unallocated Change Orders',
                'cost_type': 'Other',
                'original_budget': 0,
                'approved_changes': remaining if mode == 'approved' else 0,
                'pending': remaining if mode == 'pending' else 0,
                'notes': 'Holding line for CO without cost code',
                'actual': 0,
                'syncStatus': 'Pending',
                'percent_complete': 0,
            })
            applied = remaining

    state_data['budgetLines'] = lines
    return state_data, applied


def co_status_to_budget_mode(old_status, new_status):
    if new_status == APPROVED_CO_STATUS and old_status != APPROVED_CO_STATUS:
        return 'approved'
    if new_status == REJECTED_CO_STATUS:
        return 'reject'
    if new_status in PENDING_CO_STATUSES and old_status not in PENDING_CO_STATUSES:
        return 'pending'
    return None


def sync_change_order_to_budget(
    ChangeOrder,
    ChangeOrderAllocation,
    BudgetProjectState,
    db,
    co_id,
    old_status,
    new_status,
    user_id=None,
):
    co = ChangeOrder.query.get(co_id)
    if not co:
        raise ValueError('Change order not found')

    mode = co_status_to_budget_mode(old_status, new_status)
    if not mode:
        return None

    record, state = get_budget_state(BudgetProjectState, co.project_id)
    allocations = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    total_applied = 0.0

    if allocations:
        for alloc in allocations:
            state, applied = apply_co_to_budget_lines(
                state,
                alloc.amount,
                alloc.cost_code,
                getattr(alloc, 'cost_type', None),
                getattr(alloc, 'description', None),
                mode,
            )
            total_applied += applied
    else:
        state, applied = apply_co_to_budget_lines(
            state, co.amount, getattr(co, 'cost_code', None), mode,
        )
        total_applied += applied

    save_budget_state(BudgetProjectState, db, co.project_id, state, user_id)
    return {
        'mode': mode,
        'budget_amount_applied': total_applied,
        'budgetLines': state.get('budgetLines'),
    }


def mark_budget_lines_sage_status(state_data, status):
    lines = state_data.get('budgetLines') or []
    for line in lines:
        if line.get('syncStatus') == 'Pending':
            line['syncStatus'] = status
    state_data['budgetLines'] = lines
    return state_data


def _parse_budget_contract_amount(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def reconcile_budget_contract_from_project(state_data, project_contract_amount):
    """Align budget contract amount with project file when they differ."""
    if project_contract_amount is None:
        return state_data, False
    project_amt = float(project_contract_amount)
    budget_amt = _parse_budget_contract_amount(state_data.get('budgetContractAmount'))
    if budget_amt is not None and abs(budget_amt - project_amt) < 0.01:
        return state_data, False
    state_data = dict(state_data or {})
    state_data['budgetContractAmount'] = project_amt
    return state_data, True


def push_budget_contract_to_project(project, budget_contract_amount):
    """Write budget contract amount back to project original contract + contract value."""
    if not project or budget_contract_amount is None:
        return False
    amt = float(budget_contract_amount)
    details = project.get_details()
    details['original_contract_amount'] = str(amt)
    project.set_details(details)
    project.contract_value = amt
    project.updated_at = datetime.utcnow()
    return True
