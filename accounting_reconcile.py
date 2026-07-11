"""Bidirectional accounting reconciliation across budget, pay apps, commitments, and change orders."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from budget_persistence import (
    PENDING_CO_STATUSES,
    get_budget_state,
    save_budget_state,
)
from pay_app_persistence import (
    _find_sub_sov_keys_for_company,
    get_pay_app_state,
    normalize_cost_code,
    resolve_sub_sov_targets_for_allocation,
    save_pay_app_state,
)

APPROVED_CO_STATUS = 'Approved'
APPROVED_SUB_PAY_APP_STATUSES = ('Approved', 'Approved — Lien Waiver Received')


def _canonical_company_key(company_id=None, company_name=None):
    """Prefer stable vendor id; fall back to trimmed company name."""
    cid = str(company_id).strip() if company_id is not None and str(company_id).strip() != '' else ''
    if cid:
        return cid
    return (company_name or '').strip()


def _match_company_keys(company_id=None, company_name=None):
    """All dict keys that may refer to the same vendor in pay-app state."""
    keys = []
    seen = set()

    def add(key):
        k = str(key).strip() if key is not None else ''
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    add(company_id)
    add(company_name)
    return keys


def normalize_sub_sov_keys(sub_sov):
    """Merge subcontractor SOV buckets that share the same vendor id or name."""
    sub_sov = sub_sov or {}
    if not isinstance(sub_sov, dict):
        return {}

    canonical_for_key = {}
    for key in sub_sov:
        canonical_for_key[key] = key

    keys = list(sub_sov.keys())
    for i, key_a in enumerate(keys):
        for key_b in keys[i + 1:]:
            lines_a = sub_sov.get(key_a) or []
            lines_b = sub_sov.get(key_b) or []
            match = False
            if str(key_a).strip() == str(key_b).strip():
                match = True
            elif lines_a and lines_b:
                ids_a = {str(l.get('from_commitment') or '') for l in lines_a}
                ids_b = {str(l.get('from_commitment') or '') for l in lines_b}
                if ids_a & ids_b - {''}:
                    match = True
            if match:
                canon = canonical_for_key[key_a]
                canonical_for_key[key_b] = canon

    merged = {}
    for key, lines in sub_sov.items():
        canon = canonical_for_key.get(key, key)
        if canon not in merged:
            merged[canon] = []
        for line in lines or []:
            norm = normalize_cost_code(line.get('cost_code'))
            existing = None
            for target in merged[canon]:
                if normalize_cost_code(target.get('cost_code')) == norm:
                    existing = target
                    break
            if existing:
                for field in (
                    'original_commitment', 'change_orders', 'scheduled_value',
                    'billed_to_date', 'co_billed_to_date', 'work_this_period', 'materials_stored',
                ):
                    existing[field] = float(existing.get(field) or 0) + float(line.get(field) or 0)
                if line.get('from_change_order') and line['from_change_order'] != existing.get('from_change_order'):
                    prior = existing.get('from_change_order') or ''
                    nums = [n.strip() for n in prior.split(',') if n.strip()]
                    if line['from_change_order'] not in nums:
                        nums.append(line['from_change_order'])
                    existing['from_change_order'] = ', '.join(nums)
            else:
                merged[canon].append(dict(line))
    return merged


def _sum_approved_sub_pay_apps(pay_state):
    """Total approved subcontractor billing per company key."""
    totals = defaultdict(float)
    sub_hist = pay_state.get('subPayAppHistory') or {}
    if not isinstance(sub_hist, dict):
        return totals
    for company_key, periods in sub_hist.items():
        if not isinstance(periods, dict):
            continue
        for entry in periods.values():
            if not isinstance(entry, dict):
                continue
            status = (entry.get('status') or '').strip()
            if entry.get('archived'):
                continue
            if status and 'Approved' not in status:
                continue
            totals[str(company_key)] += float(entry.get('totalBilledThisPeriod') or 0)
    return totals


def compute_company_invoiced_totals(pay_state, commitments):
    """Map commitment id -> invoiced amount from approved sub pay apps."""
    pay_totals = _sum_approved_sub_pay_apps(pay_state)
    result = {}
    for com in commitments:
        if com.status not in APPROVED_COMMITMENT_STATUSES:
            continue
        invoiced = 0.0
        for key in _match_company_keys(getattr(com, 'company_id', None), com.company_name):
            invoiced += pay_totals.get(key, 0.0)
        if invoiced <= 0 and com.commitment_type in ('Purchase Order', 'Material Supply'):
            invoiced = float(getattr(com, 'invoiced_amount', 0) or 0)
        result[com.id] = round(invoiced, 2)
    return result


def reconcile_commitment_invoiced_amounts(commitments, pay_state):
    """Update commitment.invoiced_amount from approved pay applications."""
    totals = compute_company_invoiced_totals(pay_state, commitments)
    updated = []
    for com in commitments:
        new_invoiced = totals.get(com.id, 0.0)
        if float(getattr(com, 'invoiced_amount', 0) or 0) != new_invoiced:
            com.invoiced_amount = new_invoiced
            updated.append({
                'commitment_id': com.id,
                'number': com.number,
                'invoiced_amount': new_invoiced,
            })
    return updated


def compute_budget_actual_targets(pay_state, commitments, com_alloc_map):
    """Roll up cost-to-date for budget lines from SOV billing and PO invoicing."""
    targets = defaultdict(float)
    sub_sov = normalize_sub_sov_keys(pay_state.get('subcontractorSOV') or {})

    for _company_key, lines in sub_sov.items():
        for line in lines or []:
            code = line.get('cost_code')
            if not code:
                continue
            norm = normalize_cost_code(code)
            billed = float(line.get('billed_to_date') or 0) + float(line.get('co_billed_to_date') or 0)
            if billed:
                targets[_budget_line_key(code, 'Subcontract')] += billed

    company_invoiced = compute_company_invoiced_totals(pay_state, commitments)
    for com in commitments:
        if com.commitment_type not in ('Purchase Order', 'Material Supply'):
            continue
        invoiced = company_invoiced.get(com.id, 0.0)
        if invoiced <= 0:
            continue
        allocs = com_alloc_map.get(com.id, [])
        ctype = _commitment_cost_type(com)
        if not allocs:
            targets[_budget_line_key('01-0000', ctype)] += invoiced
            continue
        alloc_total = sum(float(a.amount or 0) for a in allocs)
        if alloc_total <= 0:
            share_each = invoiced / len(allocs)
            for alloc in allocs:
                code = alloc.cost_code or '01-0000'
                targets[_budget_line_key(code, ctype)] += share_each
        else:
            for alloc in allocs:
                code = alloc.cost_code or '01-0000'
                share = invoiced * (float(alloc.amount or 0) / alloc_total)
                targets[_budget_line_key(code, ctype)] += share

    return {k: round(v, 2) for k, v in targets.items()}


def apply_budget_actual_reconcile(state, actual_targets):
    """Set budget line actual (cost to date) from reconciled pay-app / PO totals."""
    lines = state.get('budgetLines') or []
    if not isinstance(lines, list):
        lines = []

    indexed = {}
    for line in lines:
        key = _budget_line_key(line.get('cost_code'), line.get('cost_type'))
        indexed[key] = line

    seen = set()
    for key, amt in (actual_targets or {}).items():
        seen.add(key)
        line = indexed.get(key)
        if not line:
            code, ctype = key
            line = {
                'id': int(datetime.utcnow().timestamp() * 1000) + len(indexed),
                'cost_code': code if isinstance(code, str) and '-' in code else key[0],
                'description': f'Auto — {key[0]}',
                'cost_type': key[1] or 'Other',
                'original_budget': 0,
                'actual': 0,
                'syncStatus': 'Pending',
                'percent_complete': 0,
                'notes': 'Reconciled cost to date',
            }
            lines.append(line)
            indexed[key] = line
        line['actual'] = float(amt or 0)
        line['actual_source'] = 'reconciled'

    for key, line in indexed.items():
        if key not in seen and line.get('actual_source') == 'reconciled':
            line['actual'] = 0

    state['budgetLines'] = lines
    return state

APPROVED_COMMITMENT_STATUSES = ('Approved', 'Partially Invoiced', 'Closed')
PENDING_COMMITMENT_STATUSES = ('Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner')


def _budget_line_key(cost_code, cost_type=None):
    return (normalize_cost_code(cost_code), (cost_type or '').strip())


def _commitment_cost_type(commitment):
    if commitment.commitment_type == 'Subcontract':
        return 'Subcontract'
    if commitment.commitment_type == 'Purchase Order':
        return 'Material'
    return 'Other'


def _co_links_to_commitment(co, commitment):
    ref = (getattr(co, 'linked_commitment_ref', None) or '').strip()
    if ref and ref == (commitment.number or '').strip():
        return True
    if commitment.commitment_type != 'Subcontract':
        return False
    contract_type = (getattr(co, 'contract_type', None) or '').strip()
    if contract_type not in ('Subcontract', 'Subcontractor'):
        return False
    co_cid = str(getattr(co, 'company_id', None) or '').strip()
    com_cid = str(getattr(commitment, 'company_id', None) or '').strip()
    if co_cid and com_cid and co_cid == com_cid:
        return True
    co_name = (getattr(co, 'company_name', None) or '').strip().lower()
    com_name = (commitment.company_name or '').strip().lower()
    return bool(co_name and com_name and co_name == com_name)


def _collect_alloc_maps(ChangeOrderAllocation, CommitmentAllocation, co_ids, commitment_ids):
    co_map = defaultdict(list)
    if co_ids:
        for row in ChangeOrderAllocation.query.filter(ChangeOrderAllocation.change_order_id.in_(co_ids)).all():
            co_map[row.change_order_id].append(row)
    com_map = defaultdict(list)
    if commitment_ids:
        for row in CommitmentAllocation.query.filter(CommitmentAllocation.commitment_id.in_(commitment_ids)).all():
            com_map[row.commitment_id].append(row)
    return co_map, com_map


def compute_budget_derivatives(cos, commitments, co_alloc_map, com_alloc_map):
    """Return {(norm_code, cost_type): {approved_changes, pending, committed, cost_code, cost_type}}."""
    targets = defaultdict(lambda: {
        'approved_changes': 0.0,
        'pending': 0.0,
        'committed': 0.0,
        'cost_code': '',
        'cost_type': '',
    })

    def bump(key, field, amt, cost_code, cost_type):
        if not amt:
            return
        targets[key][field] += amt
        if not targets[key]['cost_code']:
            targets[key]['cost_code'] = cost_code
        if not targets[key]['cost_type']:
            targets[key]['cost_type'] = cost_type

    for co in cos:
        allocs = co_alloc_map.get(co.id, [])
        if not allocs and co.amount:
            allocs = [type('A', (), {
                'cost_code': co.cost_code,
                'cost_type': None,
                'amount': co.amount,
                'description': co.description,
            })()]
        is_approved = co.status == APPROVED_CO_STATUS
        is_pending = co.status in PENDING_CO_STATUSES
        if not is_approved and not is_pending:
            continue
        for alloc in allocs:
            code = getattr(alloc, 'cost_code', None) or co.cost_code
            ctype = getattr(alloc, 'cost_type', None) or 'Other'
            amt = float(getattr(alloc, 'amount', 0) or 0)
            if not code or not amt:
                continue
            key = _budget_line_key(code, ctype)
            if is_approved:
                bump(key, 'approved_changes', amt, code, ctype)
            else:
                bump(key, 'pending', amt, code, ctype)

    for com in commitments:
        allocs = com_alloc_map.get(com.id, [])
        ctype = _commitment_cost_type(com)
        is_approved = com.status in APPROVED_COMMITMENT_STATUSES
        is_pending = com.status in PENDING_COMMITMENT_STATUSES
        if not is_approved and not is_pending:
            continue
        if not allocs and com.current_amount:
            allocs = [type('A', (), {
                'cost_code': None,
                'amount': com.current_amount,
                'description': com.description,
            })()]
        for alloc in allocs:
            code = getattr(alloc, 'cost_code', None)
            amt = float(getattr(alloc, 'amount', 0) or 0)
            if not amt:
                continue
            if not code:
                code = '01-0000'
            key = _budget_line_key(code, ctype)
            if is_approved:
                bump(key, 'committed', amt, code, ctype)
            else:
                bump(key, 'pending', amt, code, ctype)

    return dict(targets)


def apply_budget_reconcile(state, targets):
    lines = state.get('budgetLines') or []
    if not isinstance(lines, list):
        lines = []

    indexed = {}
    for line in lines:
        key = _budget_line_key(line.get('cost_code'), line.get('cost_type'))
        indexed[key] = line

    for key, vals in targets.items():
        line = indexed.get(key)
        if not line:
            line = {
                'id': int(datetime.utcnow().timestamp() * 1000) + len(indexed),
                'cost_code': vals['cost_code'],
                'description': f'Auto — {vals["cost_code"]}',
                'cost_type': vals['cost_type'] or 'Other',
                'original_budget': 0,
                'actual': 0,
                'syncStatus': 'Pending',
                'percent_complete': 0,
                'notes': 'Reconciled from change orders / commitments',
            }
            lines.append(line)
            indexed[key] = line
        line['approved_changes'] = float(vals.get('approved_changes') or 0)
        line['pending'] = float(vals.get('pending') or 0)
        line['committed'] = float(vals.get('committed') or 0)

    for key, line in indexed.items():
        if key not in targets:
            line['approved_changes'] = 0
            line['pending'] = 0
            line['committed'] = 0

    state['budgetLines'] = lines
    return state


def compute_contractor_sov_co_amounts(cos, co_alloc_map):
    totals = defaultdict(float)
    display = {}
    for co in cos:
        if co.status != APPROVED_CO_STATUS:
            continue
        allocs = co_alloc_map.get(co.id, [])
        if not allocs and co.amount:
            allocs = [type('A', (), {'cost_code': co.cost_code, 'amount': co.amount})()]
        for alloc in allocs:
            code = getattr(alloc, 'cost_code', None) or co.cost_code or '01-0000'
            norm = normalize_cost_code(code)
            amt = float(getattr(alloc, 'amount', 0) or 0)
            if amt:
                totals[norm] += amt
                display[norm] = code
    return totals, display


def compute_sub_sov_derivatives(cos, commitments, co_alloc_map, com_alloc_map, existing_sub_sov, Commitment):
    originals = defaultdict(lambda: defaultdict(float))
    changes = defaultdict(lambda: defaultdict(lambda: {'amount': 0.0, 'co_numbers': [], 'description': ''}))
    display_codes = defaultdict(dict)
    sub_sov = normalize_sub_sov_keys(existing_sub_sov or {})

    for com in commitments:
        if com.commitment_type != 'Subcontract':
            continue
        if com.status not in APPROVED_COMMITMENT_STATUSES:
            continue
        canon = _canonical_company_key(com.company_id, com.company_name)
        keys = _find_sub_sov_keys_for_company(sub_sov, com.company_id, com.company_name) or [canon]
        for alloc in com_alloc_map.get(com.id, []):
            code = alloc.cost_code
            if not code:
                continue
            norm = normalize_cost_code(code)
            amt = float(alloc.amount or 0)
            for key in keys:
                originals[key][norm] += amt
                display_codes[key][norm] = code

    for co in cos:
        if co.status != APPROVED_CO_STATUS:
            continue
        allocs = co_alloc_map.get(co.id, [])
        if not allocs and co.amount:
            allocs = [type('A', (), {
                'cost_code': co.cost_code,
                'amount': co.amount,
                'description': co.description,
            })()]
        for alloc in allocs:
            targets = resolve_sub_sov_targets_for_allocation(co, sub_sov, alloc, Commitment)
            norm = normalize_cost_code(getattr(alloc, 'cost_code', None) or co.cost_code or '')
            amt = float(getattr(alloc, 'amount', 0) or 0)
            if not amt:
                continue
            for key in targets:
                bucket = changes[key][norm]
                bucket['amount'] += amt
                if co.number and co.number not in bucket['co_numbers']:
                    bucket['co_numbers'].append(co.number)
                bucket['description'] = getattr(alloc, 'description', None) or co.description
                display_codes[key][norm] = getattr(alloc, 'cost_code', None) or co.cost_code

    return originals, changes, display_codes


def apply_sub_sov_reconcile(state, originals, changes, display_codes):
    sub_sov = state.get('subcontractorSOV') or {}
    if not isinstance(sub_sov, dict):
        sub_sov = {}

    all_company_keys = set(sub_sov.keys()) | set(originals.keys()) | set(changes.keys())
    for company_key in all_company_keys:
        existing_lines = sub_sov.get(company_key) or []
        billing_by_norm = {}
        for line in existing_lines:
            norm = normalize_cost_code(line.get('cost_code'))
            billing_by_norm[norm] = {
                'billed_to_date': float(line.get('billed_to_date') or 0),
                'co_billed_to_date': float(line.get('co_billed_to_date') or 0),
                'work_this_period': float(line.get('work_this_period') or 0),
                'materials_stored': float(line.get('materials_stored') or 0),
                'id': line.get('id'),
                'description': line.get('description'),
            }

        norms = set(originals.get(company_key, {}).keys()) | set(changes.get(company_key, {}).keys())
        norms |= set(billing_by_norm.keys())
        new_lines = []
        for norm in sorted(norms):
            if not norm:
                continue
            orig_amt = float(originals.get(company_key, {}).get(norm, 0))
            chg_info = changes.get(company_key, {}).get(norm, {})
            chg_amt = float(chg_info.get('amount') or 0)
            if orig_amt == 0 and chg_amt == 0:
                billing = billing_by_norm.get(norm, {})
                billed = float(billing.get('billed_to_date') or 0) + float(billing.get('co_billed_to_date') or 0)
                if billed <= 0:
                    continue
            code = display_codes.get(company_key, {}).get(norm) or norm
            billing = billing_by_norm.get(norm, {})
            line = {
                'id': billing.get('id') or f'recon-{company_key}-{norm}-{int(datetime.utcnow().timestamp())}',
                'cost_code': code,
                'description': billing.get('description') or chg_info.get('description') or f'SOV {code}',
                'original_commitment': orig_amt,
                'change_orders': chg_amt,
                'scheduled_value': orig_amt + chg_amt,
                'billed_to_date': billing.get('billed_to_date', 0),
                'co_billed_to_date': billing.get('co_billed_to_date', 0),
                'work_this_period': billing.get('work_this_period', 0),
                'materials_stored': billing.get('materials_stored', 0),
            }
            if chg_info.get('co_numbers'):
                line['from_change_order'] = ', '.join(chg_info['co_numbers'])
            elif chg_info.get('co_number'):
                line['from_change_order'] = chg_info['co_number']
            new_lines.append(line)
        sub_sov[company_key] = new_lines

    state['subcontractorSOV'] = sub_sov
    return state


def apply_contractor_sov_reconcile(state, co_totals, display_codes):
    lines = state.get('contractorSOV') or []
    if not isinstance(lines, list):
        lines = []
    indexed = {}
    for line in lines:
        norm = normalize_cost_code(line.get('cost_code'))
        indexed[norm] = line

    seen = set()
    for norm, amt in co_totals.items():
        seen.add(norm)
        line = indexed.get(norm)
        if not line:
            line = {
                'id': int(datetime.utcnow().timestamp() * 1000) + len(indexed),
                'cost_code': display_codes.get(norm, norm),
                'description': 'Reconciled change orders',
                'original': 0,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
            }
            lines.append(line)
            indexed[norm] = line
        line['co_amount'] = float(amt)

    for norm, line in indexed.items():
        if norm not in seen:
            line['co_amount'] = 0

    state['contractorSOV'] = lines
    return state


def reconcile_commitment_approved_changes(cos, commitments, co_alloc_map):
    updated = []
    approved_cos = [c for c in cos if c.status == APPROVED_CO_STATUS]
    for com in commitments:
        if com.commitment_type != 'Subcontract':
            continue
        total = 0.0
        for co in approved_cos:
            if not _co_links_to_commitment(co, com):
                continue
            allocs = co_alloc_map.get(co.id, [])
            if allocs:
                total += sum(float(a.amount or 0) for a in allocs)
            else:
                total += float(co.amount or 0)
        new_changes = round(total, 2)
        original = float(com.original_amount or 0)
        new_current = original + new_changes
        if float(com.approved_changes or 0) != new_changes or float(com.current_amount or 0) != new_current:
            com.approved_changes = new_changes
            com.current_amount = new_current
            updated.append({
                'commitment_id': com.id,
                'number': com.number,
                'approved_changes': new_changes,
                'current_amount': new_current,
            })
    return updated


def list_pending_budget_items(cos, commitments, co_alloc_map, com_alloc_map):
    items = []
    for co in cos:
        if co.status not in PENDING_CO_STATUSES:
            continue
        allocs = co_alloc_map.get(co.id, [])
        items.append({
            'entity_type': 'change_order',
            'id': co.id,
            'number': co.number,
            'description': co.description or co.title,
            'amount': co.amount,
            'status': co.status,
            'cost_code': co.cost_code,
            'allocations': [{
                'cost_code': a.cost_code,
                'amount': a.amount,
                'cost_type': getattr(a, 'cost_type', None),
            } for a in allocs],
        })
    for com in commitments:
        if com.status not in PENDING_COMMITMENT_STATUSES:
            continue
        allocs = com_alloc_map.get(com.id, [])
        items.append({
            'entity_type': 'commitment',
            'id': com.id,
            'number': com.number,
            'description': com.description or getattr(com, 'title', None),
            'amount': com.current_amount or com.original_amount,
            'status': com.status,
            'commitment_type': com.commitment_type,
            'company_name': com.company_name,
            'allocations': [{
                'cost_code': a.cost_code,
                'amount': a.amount,
            } for a in allocs],
        })
    return items


def reconcile_project_accounting(
    project_id,
    user_id,
    *,
    ChangeOrder,
    ChangeOrderAllocation,
    Commitment,
    CommitmentAllocation,
    BudgetProjectState,
    PayAppProjectState,
    db,
):
    """Recompute budget, SOV, and commitment CO totals from source records."""
    cos = ChangeOrder.query.filter_by(project_id=project_id).all()
    commitments = Commitment.query.filter_by(project_id=project_id).all()
    co_ids = [c.id for c in cos]
    com_ids = [c.id for c in commitments]
    co_alloc_map, com_alloc_map = _collect_alloc_maps(
        ChangeOrderAllocation, CommitmentAllocation, co_ids, com_ids,
    )

    budget_targets = compute_budget_derivatives(cos, commitments, co_alloc_map, com_alloc_map)
    _, budget_state = get_budget_state(BudgetProjectState, project_id)
    budget_state = apply_budget_reconcile(budget_state, budget_targets)

    _, pay_state = get_pay_app_state(PayAppProjectState, project_id)
    pay_state['subcontractorSOV'] = normalize_sub_sov_keys(pay_state.get('subcontractorSOV') or {})

    actual_targets = compute_budget_actual_targets(pay_state, commitments, com_alloc_map)
    budget_state = apply_budget_actual_reconcile(budget_state, actual_targets)
    save_budget_state(BudgetProjectState, db, project_id, budget_state, user_id)

    co_totals, co_display = compute_contractor_sov_co_amounts(cos, co_alloc_map)
    pay_state = apply_contractor_sov_reconcile(pay_state, co_totals, co_display)
    originals, changes, display_codes = compute_sub_sov_derivatives(
        cos, commitments, co_alloc_map, com_alloc_map,
        pay_state.get('subcontractorSOV') or {}, Commitment,
    )
    pay_state = apply_sub_sov_reconcile(pay_state, originals, changes, display_codes)
    save_pay_app_state(PayAppProjectState, db, project_id, pay_state, user_id)

    commitment_updates = reconcile_commitment_approved_changes(cos, commitments, co_alloc_map)
    invoiced_updates = reconcile_commitment_invoiced_amounts(commitments, pay_state)
    pending_items = list_pending_budget_items(cos, commitments, co_alloc_map, com_alloc_map)

    db.session.commit()
    return {
        'ok': True,
        'budgetLines': budget_state.get('budgetLines'),
        'contractorSOV': pay_state.get('contractorSOV'),
        'subcontractorSOV': pay_state.get('subcontractorSOV'),
        'commitment_updates': commitment_updates,
        'invoiced_updates': invoiced_updates,
        'actual_cost_applied': sum(actual_targets.values()),
        'pending_items': pending_items,
        'budget_sync_result': {
            'budget_amount_applied': sum(v['approved_changes'] + v['pending'] + v['committed'] for v in budget_targets.values()),
            'actual_cost_applied': sum(actual_targets.values()),
            'budgetLines': budget_state.get('budgetLines'),
        },
        'sync_result': {
            'sov_amount_applied': sum(co_totals.values()),
            'sub_sov_amount_applied': sum(
                chg['amount'] for company in changes.values() for chg in company.values()
            ),
            'contractorSOV': pay_state.get('contractorSOV'),
            'subcontractorSOV': pay_state.get('subcontractorSOV'),
        },
    }
