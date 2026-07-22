"""Server-side financial workflow security — blocks PUT/workflow bypass and amount spoofing."""
from __future__ import annotations

from datetime import datetime

OWNER_THRESHOLD = 50000.0

# Fields that may only change via /workflow endpoints, never via PUT/create.
WORKFLOW_ONLY_FIELDS = frozenset({
    'status',
    'ball_in_court_role',
    'approval_stage',
    'approved_at',
    'approved_by_id',
    'submitted_at',
    'executed_locked',
})

PAY_APP_PERIOD_WORKFLOW_FIELDS = frozenset({
    'status',
    'ball_in_court_role',
    'approved_at',
    'approved_by_id',
    'submitted_at',
})

BUDGET_LINE_RECONCILE_FIELDS = frozenset({
    'committed',
    'actual',
    'approved_changes',
    'pending',
})

APPROVED_CO_STATUSES = frozenset({
    'Approved', 'Partially Invoiced', 'Closed',
})

IMMUTABLE_CO_STATUSES = frozenset({'Approved', 'Rejected', 'Void'})

IMMUTABLE_COMMITMENT_STATUSES = frozenset({'Approved', 'Partially Invoiced', 'Closed', 'Void', 'Rejected'})

IMMUTABLE_CHANGE_EVENT_STATUSES = frozenset({'Approved', 'Void'})

IMMUTABLE_RFI_STATUSES = frozenset({'Closed', 'Void'})

IMMUTABLE_SUBMITTAL_STATUSES = frozenset({'Closed', 'Rejected'})

IMMUTABLE_RFQ_STATUSES = frozenset({'Accepted', 'Rejected'})

# RFQ quote fields may only change via /workflow quote or portal-quote.
RFQ_QUOTE_WORKFLOW_FIELDS = frozenset({
    'quoted_amount',
    'quoted_at',
    'quoted_by',
})


def strip_workflow_fields(data: dict | None) -> dict:
    """Remove workflow-controlled keys from a request payload."""
    data = dict(data or {})
    for key in WORKFLOW_ONLY_FIELDS:
        data.pop(key, None)
    return data


def assert_draft_create_status(status, *, entity_label='Record'):
    """New financial records must start in Draft (or module-specific open state)."""
    allowed = {'Draft', 'Open', 'Pricing'}
    st = (status or 'Draft').strip()
    if st not in allowed:
        raise ValueError(f'{entity_label} must be created in Draft status; use /workflow to advance status.')


def require_financial_project_access(user, project_id, Project=None):
    """Financial APIs always enforce project membership (stricter than global setting)."""
    if not project_id:
        raise ValueError('project_id required')
    pid = int(project_id)
    try:
        from project_access import get_assigned_project_ids, user_bypasses_project_scope
        if user_bypasses_project_scope(user):
            return pid
        if Project is not None and not Project.query.get(pid):
            raise ValueError('Project not found')
        try:
            from portal_sub_access import is_sub_vendor_portal_user, get_sub_vendor_project_ids
            if is_sub_vendor_portal_user(user):
                allowed = get_sub_vendor_project_ids(user, Project)
                if pid not in allowed:
                    raise PermissionError('You do not have access to this project.')
                return pid
        except PermissionError:
            raise
        except Exception:
            pass
        allowed = get_assigned_project_ids(user, Project)
        if pid not in allowed:
            raise PermissionError('You do not have access to this project.')
    except PermissionError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise PermissionError('Project access could not be verified.') from exc
    return pid


def require_accounting_role(user):
    role = getattr(user, 'role', None) or ''
    if role not in ('Contractor Accounting', 'Admin', 'Developer'):
        raise PermissionError('Contractor Accounting role required for this action.')


def assert_mutable_change_order(co, *, developer_unlock=False):
    if getattr(co, 'executed_locked', False) and not developer_unlock:
        raise ValueError('Executed change orders cannot be edited; use revision workflow.')
    if co.status in IMMUTABLE_CO_STATUSES and not developer_unlock:
        raise ValueError(f'Change orders in status {co.status!r} cannot be edited via save; use /workflow.')


def assert_mutable_commitment(commitment, *, developer_unlock=False):
    if commitment.status in IMMUTABLE_COMMITMENT_STATUSES and not developer_unlock:
        raise ValueError(f'Commitments in status {commitment.status!r} cannot be edited via save.')


def assert_mutable_change_event(ce, *, developer_unlock=False):
    if ce.status in IMMUTABLE_CHANGE_EVENT_STATUSES and not developer_unlock:
        raise ValueError(f'Change events in status {ce.status!r} cannot be edited via save; use /workflow.')


def assert_mutable_rfi(rfi, *, developer_unlock=False):
    if rfi.status in IMMUTABLE_RFI_STATUSES and not developer_unlock:
        raise ValueError(f'RFIs in status {rfi.status!r} cannot be edited via save; use /workflow.')


def assert_mutable_rfq(rfq, *, developer_unlock=False):
    if rfq.status in IMMUTABLE_RFQ_STATUSES and not developer_unlock:
        raise ValueError(f'RFQs in status {rfq.status!r} cannot be edited via save; use /workflow.')


def assert_mutable_submittal(submittal, *, developer_unlock=False):
    if submittal.status in IMMUTABLE_SUBMITTAL_STATUSES and not developer_unlock:
        raise ValueError(f'Submittals in status {submittal.status!r} cannot be edited via save; use /workflow.')


def assert_co_allocation_edit_allowed(co, body, *, developer_unlock=False):
    if body.get('allocations') is None:
        return
    if co.status == 'Approved' and not developer_unlock:
        raise ValueError('Approved change order allocations cannot be changed without a formal revision.')
    if float(getattr(co, 'amount', 0) or 0) != 0 and co.status not in ('Draft', 'Rejected') and not developer_unlock:
        if body.get('amount') is not None or body.get('allocations') is not None:
            pass  # caught above for Approved


def authoritative_co_amount(co, allocations=None, ChangeOrderAllocation=None):
    from co_persistence import compute_co_amount_from_allocations
    if allocations is not None:
        return abs(float(compute_co_amount_from_allocations(allocations, getattr(co, 'sub_co_kind', None)) or 0))
    if ChangeOrderAllocation is not None and getattr(co, 'id', None):
        rows = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
        if rows:
            payload = [{
                'cost_code': a.cost_code,
                'amount': a.amount,
                'cost_type': getattr(a, 'cost_type', None),
            } for a in rows]
            return abs(float(compute_co_amount_from_allocations(payload, getattr(co, 'sub_co_kind', None)) or 0))
    return abs(float(getattr(co, 'amount', 0) or 0))


def authoritative_commitment_amount(commitment, CommitmentAllocation=None):
    if CommitmentAllocation is not None and getattr(commitment, 'id', None):
        rows = CommitmentAllocation.query.filter_by(commitment_id=commitment.id).all()
        if rows:
            return abs(sum(float(r.amount or 0) for r in rows))
    return abs(float(commitment.current_amount or commitment.original_amount or 0))


def authoritative_cor_amount(cor, ChangeEventAllocation=None, CORAllocation=None):
    alloc_model = CORAllocation or ChangeEventAllocation
    if alloc_model is not None and getattr(cor, 'id', None):
        rows = alloc_model.query.filter_by(cor_id=cor.id).all()
        if rows:
            return abs(sum(float(r.amount or 0) for r in rows))
    return abs(float(getattr(cor, 'amount', 0) or 0))


def _month_start():
    now = datetime.utcnow()
    return datetime(now.year, now.month, 1)


def cumulative_approved_owner_co_amount(project_id, ChangeOrder, *, exclude_co_id=None, db=None):
    """Sum of approved owner CO amounts this calendar month (cumulative threshold)."""
    if not ChangeOrder or not project_id:
        return 0.0
    start = _month_start()
    q = ChangeOrder.query.filter(
        ChangeOrder.project_id == int(project_id),
        ChangeOrder.status == 'Approved',
        ChangeOrder.contract_type.notin_(['Subcontract', 'Subcontractor']),
    )
    if exclude_co_id:
        q = q.filter(ChangeOrder.id != int(exclude_co_id))
    rows = q.all()
    total = 0.0
    for co in rows:
        approved_at = getattr(co, 'approved_at', None) or getattr(co, 'created_at', None)
        if approved_at and approved_at >= start:
            total += abs(float(co.amount or 0))
    return round(total, 2)


def cumulative_approved_cor_amount(project_id, ChangeOrderRequest, *, exclude_cor_id=None):
    """COR amounts approved this calendar month."""
    if not ChangeOrderRequest or not project_id:
        return 0.0
    start = _month_start()
    q = ChangeOrderRequest.query.filter(
        ChangeOrderRequest.project_id == int(project_id),
        ChangeOrderRequest.status == 'Approved',
    )
    if exclude_cor_id:
        q = q.filter(ChangeOrderRequest.id != int(exclude_cor_id))
    total = 0.0
    for cor in q.all():
        ts = getattr(cor, 'updated_at', None) or getattr(cor, 'created_at', None)
        if ts and ts >= start:
            total += abs(float(cor.amount or 0))
    return round(total, 2)


def cumulative_g702_approved_this_month(project_id, PayAppProjectState, *, exclude_period=None):
    """Sum of approved G702 period billing this calendar month."""
    if not PayAppProjectState or not project_id:
        return 0.0
    from pay_app_persistence import get_pay_app_state
    from pay_app_workflow import _billing_amount_from_sov_state

    _, state = get_pay_app_state(PayAppProjectState, int(project_id))
    history = state.get('payAppHistory') or []
    if isinstance(history, dict):
        history = list(history.values())
    start = _month_start()
    total = 0.0
    for entry in history:
        if not isinstance(entry, dict):
            continue
        if (entry.get('status') or '') != 'Approved':
            continue
        period_num = entry.get('periodNumber')
        if exclude_period is not None and str(period_num) == str(exclude_period):
            continue
        approved_at = entry.get('approved_at') or entry.get('approvedAt')
        if approved_at:
            try:
                ts = datetime.fromisoformat(str(approved_at).replace('Z', ''))
                if ts < start:
                    continue
            except (TypeError, ValueError):
                pass
        snap = entry.get('snapshot') or entry
        billing = snap.get('billingLines') or snap.get('payAppBillingLines') or {}
        amt = _billing_amount_from_sov_state({
            'contractorSOV': snap.get('contractorSOV') or state.get('contractorSOV') or [],
            'payAppBillingLines': billing,
            'payAppRetainagePercent': state.get('payAppRetainagePercent'),
        })
        total += amt
    return round(total, 2)


def effective_threshold_amount(base_amount, cumulative_amount):
    return round(float(base_amount or 0) + float(cumulative_amount or 0), 2)


def should_skip_owner_threshold(base_amount, cumulative_amount=0.0, threshold=OWNER_THRESHOLD):
    return effective_threshold_amount(base_amount, cumulative_amount) < threshold


def filter_pay_app_patch_for_sub_vendor(user, patch: dict, existing: dict | None = None) -> dict:
    from portal_sub_access import (
        is_sub_vendor_portal_user,
        sub_vendor_company_keys,
        _filter_company_dict,
        resolve_sub_vendor_sov_keys,
    )
    from pay_app_persistence import coerce_pay_app_state
    if not is_sub_vendor_portal_user(user) or not isinstance(patch, dict):
        return patch
    allowed = sub_vendor_company_keys(user)
    merged = dict(coerce_pay_app_state(existing))
    merged.update(patch if isinstance(patch, dict) else {})
    sov_keys = resolve_sub_vendor_sov_keys(user, merged)
    out = {}
    for field in (
        'subcontractorSOV', 'subSOVStatus', 'subPayAppHistory',
        'subPendingSubmissions', 'subPayAppNumbers',
    ):
        if field in patch:
            out[field] = _filter_company_dict(patch.get(field), allowed, sov_keys)
    return out


def filter_pay_app_state_for_sub_vendor(user, data):
    from portal_sub_access import filter_pay_app_state_for_sub_vendor as _filter
    return _filter(user, data)


def sanitize_pay_app_state(existing: dict, patch: dict) -> dict:
    """Strip workflow-controlled pay app fields from client patches."""
    from pay_app_persistence import merge_state_patch

    merged = merge_state_patch(existing, patch)
    existing = dict(existing or {})

    # Period workflow fields — preserve server values
    period = dict(merged.get('currentPayAppPeriod') or {})
    prev_period = dict(existing.get('currentPayAppPeriod') or {})
    for field in PAY_APP_PERIOD_WORKFLOW_FIELDS:
        if field in prev_period:
            period[field] = prev_period[field]
        else:
            period.pop(field, None)
    # Never trust client amount_due for authorization
    for key in ('amountDue', 'amount_due', 'paymentDue', 'payment_due'):
        period.pop(key, None)
    merged['currentPayAppPeriod'] = period

    # Sub SOV status — preserve statuses
    prev_sub_status = existing.get('subSOVStatus') or {}
    new_sub_status = dict(merged.get('subSOVStatus') or {})
    for key, entry in new_sub_status.items():
        prev = prev_sub_status.get(key)
        if isinstance(prev, dict) and isinstance(entry, dict):
            entry['status'] = prev.get('status', entry.get('status'))
            if 'ball_in_court_role' in prev:
                entry['ball_in_court_role'] = prev.get('ball_in_court_role')
        elif isinstance(prev, str):
            new_sub_status[key] = prev
    merged['subSOVStatus'] = new_sub_status

    # Sub pay app history — preserve approval statuses
    prev_hist = existing.get('subPayAppHistory') or {}
    new_hist = dict(merged.get('subPayAppHistory') or {})
    for company_key, periods in new_hist.items():
        if not isinstance(periods, dict):
            continue
        prev_periods = prev_hist.get(company_key) or {}
        for pkey, entry in periods.items():
            if not isinstance(entry, dict):
                continue
            prev_entry = prev_periods.get(pkey) or {}
            if isinstance(prev_entry, dict) and prev_entry.get('status'):
                entry['status'] = prev_entry['status']
                if prev_entry.get('ball_in_court_role') is not None:
                    entry['ball_in_court_role'] = prev_entry.get('ball_in_court_role')
    merged['subPayAppHistory'] = new_hist

    merged.pop('subPendingSubmissions', None)
    if 'subPendingSubmissions' in existing:
        merged['subPendingSubmissions'] = existing['subPendingSubmissions']

    return merged


def sanitize_budget_state(existing: dict, patch: dict) -> dict:
    """Prevent direct manipulation of reconcile-derived budget line totals."""
    from budget_persistence import merge_state_patch

    merged = merge_state_patch(existing, patch)
    existing_lines = {
        (line.get('cost_code'), line.get('cost_type')): line
        for line in (existing.get('budgetLines') or [])
        if isinstance(line, dict)
    }
    lines = merged.get('budgetLines') or []
    if not isinstance(lines, list):
        return merged
    cleaned = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        key = (line.get('cost_code'), line.get('cost_type'))
        prev = existing_lines.get(key) or {}
        row = dict(line)
        for field in BUDGET_LINE_RECONCILE_FIELDS:
            if field in prev:
                row[field] = prev[field]
            else:
                row.pop(field, None)
        cleaned.append(row)
    merged['budgetLines'] = cleaned
    return merged


def workflow_reject_authorized(user, role, *, user_can_act_fn):
    """Reject requires same ball-in-court authority as approve."""
    if not role:
        raise ValueError('Cannot reject: no ball-in-court role set.')
    if not user_can_act_fn(user, role):
        raise ValueError(f'Your role cannot reject while ball is with {role}')


def allowed_g702_state_patch(state_patch):
    """Final G702 approve may only patch whitelisted non-workflow keys."""
    if not state_patch:
        return {}
    allowed = frozenset({
        'payAppHistory', 'mainLienWaiver', 'payAppAuditLog',
    })
    return {k: v for k, v in (state_patch or {}).items() if k in allowed}
