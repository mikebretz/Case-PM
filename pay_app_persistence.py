"""Pay application server persistence, change order SOV sync, and schema helpers."""
from __future__ import annotations

import json
from datetime import datetime

# Keys mirrored from pay_applications.html localStorage (project-scoped via casepmStore)
PAY_APP_STATE_KEYS = (
    'contractorSOV',
    'payAppBillingLines',
    'currentPayAppPeriod',
    'payAppHistory',
    'subcontractorSOV',
    'subPayAppHistory',
    'subPendingSubmissions',
    'subPayAppNumbers',
    'subSOVStatus',
    'subLienWaivers',
    'subLienWaiverArchive',
    'previousSubPayAppArchive',
    'mainLienWaiver',
    'payAppRetainagePercent',
    'requireLienWaiverOnSubPayApp',
    'requireSubmissionDeadline',
    'submissionDeadlineDay',
    'allowZeroDollarSubPayApps',
    'requireAllSubPayAppsBeforeG702Submit',
    'g702PayAppGateScope',
    'payAppAuditLog',
    'sageSyncAutoEnabled',
    'contractorSOVLocked',
)

SCHEDULE_IMPACT_DAYS = {
    'none': 0,
    'no impact': 0,
    'minor': 5,
    'moderate': 10,
    'significant': 14,
    'major': 14,
    'critical': 30,
}


def ensure_pay_app_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if 'change_order' in tables:
        cols = {c['name'] for c in inspector.get_columns('change_order')}
        additions = {
            'cost_code': 'VARCHAR(30)',
            'requested_by': 'VARCHAR(150)',
            'priority': 'VARCHAR(20)',
            'revision': 'INTEGER DEFAULT 0',
            'notes': 'TEXT',
            'approved_at': 'DATETIME',
            'approved_by_id': 'INTEGER',
            'sov_synced_at': 'DATETIME',
            'sage_sync_status': 'VARCHAR(30)',
        }
        for name, col_type in additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE change_order ADD COLUMN {name} {col_type}'))
        db.session.commit()


def register_models(db):
  class PayAppProjectState(db.Model):
      __tablename__ = 'pay_app_project_state'
      id = db.Column(db.Integer, primary_key=True)
      project_id = db.Column(db.Integer, db.ForeignKey('project.id'), unique=True, nullable=False)
      data_json = db.Column(db.Text, default='{}')
      version = db.Column(db.Integer, default=1)
      updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
      updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

  class SageSyncEvent(db.Model):
      __tablename__ = 'sage_sync_event'
      id = db.Column(db.Integer, primary_key=True)
      project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
      event_type = db.Column(db.String(80), nullable=False)
      status = db.Column(db.String(30), default='queued')
      sage_job_number = db.Column(db.String(80))
      message = db.Column(db.Text)
      payload_json = db.Column(db.Text)
      response_json = db.Column(db.Text)
      error_text = db.Column(db.Text)
      created_at = db.Column(db.DateTime, default=datetime.utcnow)
      posted_at = db.Column(db.DateTime, nullable=True)
      created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

  class ChangeOrderAllocation(db.Model):
      __tablename__ = 'change_order_allocation'
      id = db.Column(db.Integer, primary_key=True)
      change_order_id = db.Column(db.Integer, db.ForeignKey('change_order.id'), nullable=False)
      cost_code = db.Column(db.String(30))
      amount = db.Column(db.Float, default=0)
      sov_line_legacy_id = db.Column(db.String(64))

  return PayAppProjectState, SageSyncEvent, ChangeOrderAllocation


def _parse_state(record):
    if not record or not record.data_json:
        return {}
    try:
        return json.loads(record.data_json)
    except (TypeError, json.JSONDecodeError):
        return {}


def get_pay_app_state(PayAppProjectState, project_id):
    record = PayAppProjectState.query.filter_by(project_id=project_id).first()
    if not record:
        return None, {}
    return record, _parse_state(record)


def save_pay_app_state(PayAppProjectState, db, project_id, data, user_id=None):
    if not isinstance(data, dict):
        raise ValueError('data must be a dict')
    record = PayAppProjectState.query.filter_by(project_id=project_id).first()
    payload = json.dumps(data)
    if record:
        record.data_json = payload
        record.version = (record.version or 0) + 1
        record.updated_by_id = user_id
        record.updated_at = datetime.utcnow()
    else:
        record = PayAppProjectState(
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
        if key in PAY_APP_STATE_KEYS or key.startswith('_'):
            merged[key] = value
    return merged


def normalize_cost_code(code):
    if not code:
        return ''
    return str(code).replace(' ', '').replace('-', '').upper()


def _contractor_line_co_amount(line):
    if not isinstance(line, dict):
        return 0.0
    return float(line.get('co_amount') or line.get('change_orders') or 0)


def validate_sub_sov_cost_code_allocations(state_data, tolerance=0.01):
    """Ensure no cost code is over-allocated across all subcontractor SOV lines vs G703."""
    contractor = state_data.get('contractorSOV') or []
    sub_sov = state_data.get('subcontractorSOV') or {}
    if not isinstance(contractor, list) or not isinstance(sub_sov, dict):
        return []

    gc_totals = {}
    display_codes = {}
    for line in contractor:
        if not isinstance(line, dict):
            continue
        norm = normalize_cost_code(line.get('cost_code'))
        if not norm:
            continue
        amt = float(line.get('original') or 0) + _contractor_line_co_amount(line)
        gc_totals[norm] = gc_totals.get(norm, 0.0) + amt
        display_codes[norm] = line.get('cost_code') or norm

    sub_totals = {}
    for _cid, lines in sub_sov.items():
        for line in lines or []:
            if not isinstance(line, dict):
                continue
            norm = normalize_cost_code(line.get('cost_code'))
            if not norm:
                continue
            amt = float(line.get('original_commitment') or line.get('original') or 0)
            amt += float(line.get('change_orders') or 0)
            sub_totals[norm] = sub_totals.get(norm, 0.0) + amt

    errors = []
    for norm, sub_amt in sub_totals.items():
        gc = gc_totals.get(norm, 0.0)
        if gc <= 0:
            continue
        if sub_amt > gc + tolerance:
            label = display_codes.get(norm, norm)
            errors.append(
                f'Cost code {label} is over-allocated: subcontractors total '
                f'${sub_amt:,.2f} exceeds G703 ${gc:,.2f}'
            )
    return errors


def _sov_keys_for_vendor(state_data, company_id=None, company_name=None):
    """Dict keys in pay-app state that belong to a registered subcontractor vendor."""
    keys: set[str] = set()
    sub_sov = state_data.get('subcontractorSOV') or {}
    sub_status = state_data.get('subSOVStatus') or {}
    if not isinstance(sub_status, dict):
        sub_status = {}
    for block in (sub_sov, sub_status):
        if not isinstance(block, dict):
            continue
        for key in _find_sub_sov_keys_for_company(block, company_id, company_name):
            sk = str(key).strip()
            if not sk:
                continue
            entry = sub_status.get(key) or sub_status.get(sk) or {}
            if isinstance(entry, dict) and entry.get('status'):
                keys.add(sk)
    cid_s = str(company_id).strip() if company_id is not None and str(company_id).strip() else ''
    name_lower = (company_name or '').strip().lower()
    for key, entry in sub_status.items():
        if not isinstance(entry, dict) or not entry.get('status'):
            continue
        sk = str(key).strip()
        if not sk:
            continue
        vendor_ids = _sov_status_vendor_ids(key, entry)
        if cid_s and cid_s in vendor_ids:
            keys.add(sk)
            continue
        st_name = (entry.get('companyName') or entry.get('company_name') or '').strip().lower()
        if name_lower and st_name and st_name == name_lower:
            keys.add(sk)
    return keys


def is_vendor_on_sub_sov(state_data, company_id=None, company_name=None) -> bool:
    """True when the GC has registered this vendor on the subcontractor SOV list."""
    return bool(_sov_keys_for_vendor(state_data or {}, company_id, company_name))


def _sum_sub_sov_line_commitments(lines):
    total = 0.0
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        total += float(line.get('original_commitment') or line.get('original') or 0)
        total += float(line.get('change_orders') or 0)
    return total


def get_vendor_commitment_cap(commitments, company_id=None, company_name=None):
    """Return the subcontract commitment cap for a vendor, or None if none on file."""
    best = None
    for commitment in commitments or []:
        if not commitment_matches_vendor(commitment, company_id, company_name):
            continue
        current = getattr(commitment, 'current_amount', None)
        original = float(getattr(commitment, 'original_amount', 0) or 0)
        approved = float(getattr(commitment, 'approved_changes', 0) or 0)
        cap = float(current) if current is not None else original + approved
        if cap > 0:
            best = cap
            break
        if best is None:
            best = cap
    return best


def validate_sub_sov_commitment_totals(
    state_data,
    commitments,
    *,
    company_id=None,
    company_name=None,
    tolerance=0.01,
):
    """Ensure each sub's SOV total does not exceed their subcontract commitment."""
    sub_sov = state_data.get('subcontractorSOV') or {}
    if not isinstance(sub_sov, dict):
        return []

    vendor_keys = None
    if company_id is not None or company_name:
        vendor_keys = _sov_keys_for_vendor(state_data, company_id, company_name)

    errors = []
    for key, lines in sub_sov.items():
        sk = str(key).strip()
        if vendor_keys is not None and sk not in vendor_keys:
            continue
        total = _sum_sub_sov_line_commitments(lines)
        if total <= tolerance:
            continue
        cap = get_vendor_commitment_cap(commitments, company_id, company_name)
        if cap is None:
            label = company_name or sk
            errors.append(
                f'No subcontract commitment on file for {label}. '
                'Enter the PO/subcontract amount before building the Schedule of Values.'
            )
            continue
        if total > float(cap) + tolerance:
            label = company_name or sk
            errors.append(
                f'Schedule of Values for {label} totals ${total:,.2f}, '
                f'which exceeds the original contract amount of ${float(cap):,.2f}.'
            )
    return errors


def validate_sub_sov_requires_commitments(state_data, commitments, tolerance=0.01):
    """Each subcontractor on the SOV list must have a Subcontract commitment on the project."""
    sub_sov = state_data.get('subcontractorSOV') or {}
    sub_status = state_data.get('subSOVStatus') or {}
    if not isinstance(sub_sov, dict) and not isinstance(sub_status, dict):
        return []
    keys = set()
    for block in (sub_sov, sub_status):
        if isinstance(block, dict):
            keys.update(str(k) for k in block.keys())
    errors = []
    for key in sorted(keys):
        sk = str(key).strip()
        if not sk:
            continue
        status_entry = sub_status.get(key) or sub_status.get(sk) or {}
        if not isinstance(status_entry, dict) or not status_entry.get('status'):
            continue
        company_name = ''
        company_id = None
        if isinstance(status_entry, dict):
            company_name = (status_entry.get('companyName') or status_entry.get('company_name') or '').strip()
            raw_cid = status_entry.get('companyId') or status_entry.get('company_id')
            company_id = str(raw_cid).strip() if raw_cid is not None else None
        if not company_id and sk.isdigit():
            company_id = sk
        cap = get_vendor_commitment_cap_for_sov_entry(commitments, key, status_entry)
        if cap is None:
            label = company_name or sk
            errors.append(
                f'{label} is on the subcontractor schedule of values but has no Subcontract '
                'commitment on this project. Create the commitment first.'
            )
    return errors


def _sov_status_vendor_ids(key, status_entry=None):
    """All company id variants stored on a subcontractor SOV bucket."""
    ids = set()
    sk = str(key).strip() if key is not None else ''
    if sk:
        ids.add(sk)
    if isinstance(status_entry, dict):
        for field in ('companyId', 'company_id', 'localCompanyId', 'commitmentCompanyId'):
            raw = status_entry.get(field)
            if raw is not None and str(raw).strip():
                ids.add(str(raw).strip())
    return ids


def commitment_matches_sov_entry(commitment, key, status_entry=None, company_name=None):
    """True when a subcontract commitment belongs to this SOV bucket."""
    if getattr(commitment, 'commitment_type', None) != 'Subcontract':
        return False
    vendor_ids = _sov_status_vendor_ids(key, status_entry)
    names = set()
    if isinstance(status_entry, dict):
        n = (status_entry.get('companyName') or status_entry.get('company_name') or '').strip().lower()
        if n:
            names.add(n)
    if company_name:
        names.add(str(company_name).strip().lower())
    com_cid = str(getattr(commitment, 'company_id', None) or '').strip()
    com_name = (getattr(commitment, 'company_name', None) or '').strip().lower()
    if com_cid and com_cid in vendor_ids:
        return True
    if com_name and names and com_name in names:
        return True
    return False


def get_vendor_commitment_cap_for_sov_entry(commitments, key, status_entry=None):
    """Return subcontract commitment cap for a registered SOV bucket."""
    best = None
    for commitment in commitments or []:
        if not commitment_matches_sov_entry(commitment, key, status_entry):
            continue
        current = getattr(commitment, 'current_amount', None)
        original = float(getattr(commitment, 'original_amount', 0) or 0)
        approved = float(getattr(commitment, 'approved_changes', 0) or 0)
        cap = float(current) if current is not None else original + approved
        if cap > 0:
            return cap
        if best is None:
            best = cap
    return best


def prune_unregistered_sub_sov(state_data, commitments=None):
    """Drop SOV buckets that were never GC-registered or lack a subcontract commitment."""
    if not isinstance(state_data, dict):
        return state_data
    sub_sov = state_data.get('subcontractorSOV') or {}
    sub_status = state_data.get('subSOVStatus') or {}
    if not isinstance(sub_sov, dict):
        sub_sov = {}
    if not isinstance(sub_status, dict):
        sub_status = {}
    all_keys = set(sub_sov.keys()) | set(sub_status.keys())
    remove = set()
    for key in all_keys:
        sk = str(key).strip()
        if not sk:
            remove.add(key)
            continue
        entry = sub_status.get(key) or sub_status.get(sk) or {}
        if not isinstance(entry, dict) or not entry.get('status'):
            remove.add(key)
            continue
        company_name = (entry.get('companyName') or entry.get('company_name') or '').strip()
        if commitments is not None and get_vendor_commitment_cap_for_sov_entry(commitments, key, entry) is None:
            remove.add(key)
    if not remove:
        return state_data
    out = dict(state_data)
    for field in (
        'subcontractorSOV', 'subSOVStatus', 'subPayAppHistory',
        'subPendingSubmissions', 'subPayAppNumbers', 'subLienWaivers', 'subLienWaiverArchive',
    ):
        block = out.get(field)
        if not isinstance(block, dict):
            continue
        out[field] = {k: v for k, v in block.items() if k not in remove}
    return out


def validate_sub_vendor_pay_app_save(
    existing,
    merged,
    user,
    *,
    Commitment=None,
    project_id=None,
    tolerance=0.01,
):
    """Server-side rules for sub-vendor SOV entry (no G703 caps; commitment + registration)."""
    from portal_sub_access import resolve_sub_vendor_company, resolve_sub_vendor_sov_keys

    existing = dict(existing or {})
    merged = dict(merged or {})
    cid, cname, _ = resolve_sub_vendor_company(user)
    if not is_vendor_on_sub_sov(existing, cid, cname):
        return [
            'You are not registered on this project\'s subcontractor schedule of values. '
            'Ask your GC to add your company under Select Subcontractor and save.'
        ]

    existing_keys = set(str(k) for k in (existing.get('subcontractorSOV') or {}))
    existing_keys |= set(str(k) for k in (existing.get('subSOVStatus') or {}))
    allowed_keys = {str(k) for k in resolve_sub_vendor_sov_keys(user, existing)}
    merged_sov = merged.get('subcontractorSOV') or {}
    merged_status = merged.get('subSOVStatus') or {}
    for block in (merged_sov, merged_status):
        if not isinstance(block, dict):
            continue
        for key in block:
            sk = str(key).strip()
            if not sk:
                continue
            if sk in existing_keys or sk in allowed_keys:
                continue
            return [
                'You cannot add schedule of values for this project until your company '
                'is added to the subcontractor schedule of values list.'
            ]

    commitments = []
    if Commitment is not None and project_id is not None:
        try:
            commitments = Commitment.query.filter_by(project_id=int(project_id)).all()
        except Exception:
            commitments = []
    return validate_sub_sov_commitment_totals(
        merged,
        commitments,
        company_id=cid,
        company_name=cname,
        tolerance=tolerance,
    )


def apply_co_to_contractor_sov(state_data, amount, cost_code=None, description=None):
    """Add approved change order amount to contractor SOV co_amount."""
    lines = state_data.get('contractorSOV') or []
    if not isinstance(lines, list):
        lines = []
    target_norm = normalize_cost_code(cost_code)
    applied = 0.0
    remaining = float(amount or 0)
    line_desc = (description or '').strip() or (f'Change Order — {cost_code}' if cost_code else 'Change Order')

    if target_norm:
        for line in lines:
            if normalize_cost_code(line.get('cost_code')) == target_norm:
                line['co_amount'] = float(line.get('co_amount') or 0) + remaining
                applied = remaining
                remaining = 0
                break
        if remaining > 0:
            lines.append({
                'id': int(datetime.utcnow().timestamp() * 1000),
                'cost_code': cost_code,
                'description': line_desc,
                'original': 0,
                'co_amount': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'notes': 'Auto-created from approved change order',
            })
            applied += remaining
    else:
        if lines:
            lines[0]['co_amount'] = float(lines[0].get('co_amount') or 0) + remaining
            applied = remaining
        else:
            lines.append({
                'id': int(datetime.utcnow().timestamp() * 1000),
                'cost_code': '01-0000',
                'description': 'Unallocated Change Orders',
                'original': 0,
                'co_amount': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'notes': 'Holding line for CO without cost code',
            })
            applied = remaining

    state_data['contractorSOV'] = lines
    return state_data, applied


def _find_sub_sov_keys_for_company(sub_sov, company_id=None, company_name=None):
    """Resolve subcontractorSOV dict keys for a vendor (numeric id and/or name)."""
    keys = []
    seen = set()
    sub_sov = sub_sov or {}

    def add(key):
        k = str(key).strip() if key is not None else ''
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    if company_id is not None and str(company_id).strip() != '':
        add(company_id)
    if company_name:
        add(company_name.strip())
        name_lower = company_name.strip().lower()
        for k in sub_sov:
            if str(k).strip().lower() == name_lower:
                add(k)

    return keys


def resolve_sub_sov_targets_for_allocation(co, sub_sov, allocation, Commitment=None):
    """Determine which subcontractor SOV buckets should receive a CO allocation."""
    targets = []
    seen = set()
    sub_sov = sub_sov or {}

    def add(key):
        k = str(key).strip() if key is not None else ''
        if k and k not in seen:
            seen.add(k)
            targets.append(k)

    company_id = getattr(co, 'company_id', None)
    company_name = getattr(co, 'company_name', None)
    for k in _find_sub_sov_keys_for_company(sub_sov, company_id, company_name):
        add(k)

    linked_ref = getattr(co, 'linked_commitment_ref', None)
    if linked_ref and Commitment is not None:
        commitment = Commitment.query.filter_by(
            project_id=co.project_id,
            number=linked_ref,
        ).first()
        if commitment:
            for k in _find_sub_sov_keys_for_company(
                sub_sov, getattr(commitment, 'company_id', None), commitment.company_name,
            ):
                add(k)

    cost_code = getattr(allocation, 'cost_code', None)
    if isinstance(allocation, dict):
        cost_code = allocation.get('cost_code')
    target_norm = normalize_cost_code(cost_code)
    if target_norm:
        for company_key, lines in sub_sov.items():
            for line in lines or []:
                if normalize_cost_code(line.get('cost_code')) == target_norm:
                    add(company_key)
                    break

    contract_type = (getattr(co, 'contract_type', None) or '').strip()
    if not targets and contract_type in ('Subcontract', 'Subcontractor'):
        if company_id is not None and str(company_id).strip() != '':
            add(str(company_id))
        elif company_name:
            add(company_name.strip())

    return targets


def apply_co_to_subcontractor_sov(state_data, company_key, amount, cost_code=None, description=None, co_number=None, sov_line_id=None):
    """Add approved change order amount to a subcontractor SOV line (change_orders column)."""
    sub_sov = state_data.get('subcontractorSOV') or {}
    if not isinstance(sub_sov, dict):
        sub_sov = {}
    lines = sub_sov.get(company_key) or []
    if not isinstance(lines, list):
        lines = []

    remaining = float(amount or 0)
    target_norm = normalize_cost_code(cost_code)
    line_desc = (description or '').strip() or (
        f'CO {co_number} — {cost_code}' if co_number and cost_code else f'Change Order {co_number or ""}'.strip()
    )
    applied = 0.0

    if sov_line_id:
        for line in lines:
            if str(line.get('id')) == str(sov_line_id):
                if co_number and line.get('from_change_order') == co_number:
                    return state_data, 0.0
                line['change_orders'] = float(line.get('change_orders') or 0) + remaining
                orig = float(line.get('original_commitment') or 0)
                line['scheduled_value'] = orig + float(line.get('change_orders') or 0)
                if co_number:
                    line['from_change_order'] = co_number
                applied = remaining
                remaining = 0
                break

    if target_norm and remaining > 0:
        for line in lines:
            if normalize_cost_code(line.get('cost_code')) == target_norm:
                if co_number and line.get('from_change_order') == co_number:
                    return state_data, 0.0
                line['change_orders'] = float(line.get('change_orders') or 0) + remaining
                orig = float(line.get('original_commitment') or 0)
                line['scheduled_value'] = orig + float(line.get('change_orders') or 0)
                if co_number:
                    line['from_change_order'] = co_number
                applied = remaining
                remaining = 0
                break
        if remaining > 0:
            lines.append({
                'id': f'co-{co_number or "new"}-{target_norm}-{int(datetime.utcnow().timestamp() * 1000)}',
                'cost_code': cost_code,
                'description': line_desc,
                'original_commitment': 0,
                'change_orders': remaining,
                'scheduled_value': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'work_this_period': 0,
                'materials_stored': 0,
                'notes': f'Auto-created from approved change order {co_number or ""}'.strip(),
                'from_change_order': co_number,
            })
            applied += remaining
    elif remaining > 0:
        if lines:
            line = lines[0]
            line['change_orders'] = float(line.get('change_orders') or 0) + remaining
            orig = float(line.get('original_commitment') or 0)
            line['scheduled_value'] = orig + float(line.get('change_orders') or 0)
            if co_number:
                line['from_change_order'] = co_number
            applied = remaining
        else:
            lines.append({
                'id': f'co-{co_number or "new"}-unalloc-{int(datetime.utcnow().timestamp() * 1000)}',
                'cost_code': '01-0000',
                'description': line_desc or 'Unallocated Change Orders',
                'original_commitment': 0,
                'change_orders': remaining,
                'scheduled_value': remaining,
                'billed_to_date': 0,
                'co_billed_to_date': 0,
                'work_this_period': 0,
                'materials_stored': 0,
                'notes': f'Auto-created from approved change order {co_number or ""}'.strip(),
                'from_change_order': co_number,
            })
            applied = remaining

    sub_sov[company_key] = lines
    state_data['subcontractorSOV'] = sub_sov
    return state_data, applied


def schedule_impact_to_days(schedule_impact):
    if not schedule_impact:
        return 0
    text = str(schedule_impact).strip().lower()
    if text.isdigit():
        return int(text)
    for key, days in SCHEDULE_IMPACT_DAYS.items():
        if key in text:
            return days
    return 0


def apply_schedule_impact(ScheduleData, Project, db, project_id, schedule_impact, co_number, description):
    days = schedule_impact_to_days(schedule_impact)
    if days <= 0:
        return None

    project = Project.query.get(project_id)
    record = ScheduleData.query.filter_by(project_id=project_id).first()
    payload = {}
    if record and record.payload:
        try:
            payload = json.loads(record.payload)
        except (TypeError, json.JSONDecodeError):
            payload = {}

    tasks = payload.get('tasks') or payload.get('data') or []
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    marker_id = f'co-{co_number}-{int(datetime.utcnow().timestamp())}'
    tasks.append({
        'id': marker_id,
        'text': f'CO {co_number}: {description[:80] if description else "Schedule impact"}',
        'type': 'milestone',
        'duration': days,
        'progress': 0,
        'open': True,
        'parent': 0,
        'notes': f'Schedule impact +{days} days from approved change order {co_number}',
    })
    if 'tasks' in payload:
        payload['tasks'] = tasks
    elif 'data' in payload:
        payload['data'] = tasks
    else:
        payload['tasks'] = tasks

    payload_json = json.dumps(payload)
    if record:
        record.payload = payload_json
        record.updated_at = datetime.utcnow()
    else:
        record = ScheduleData(project_id=project_id, payload=payload_json)
        db.session.add(record)

    if project and project.end_date:
        from datetime import timedelta
        project.end_date = project.end_date + timedelta(days=days)

    db.session.commit()
    return {'days_added': days, 'task_id': marker_id}


def sync_change_order_to_sov(
    ChangeOrder,
    ChangeOrderAllocation,
    PayAppProjectState,
    ScheduleData,
    Project,
    db,
    co_id,
    user_id=None,
    Commitment=None,
):
    co = ChangeOrder.query.get(co_id)
    if not co:
        raise ValueError('Change order not found')
    if co.status != 'Approved':
        raise ValueError('Change order must be Approved to sync to SOV')

    record, state = get_pay_app_state(PayAppProjectState, co.project_id)
    already_contractor_synced = bool(co.sov_synced_at)

    allocations = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    sub_sov = state.get('subcontractorSOV') or {}

    total_applied = 0.0
    sub_total_applied = 0.0
    sub_updates = []

    if allocations:
        if not already_contractor_synced:
            for alloc in allocations:
                state, applied = apply_co_to_contractor_sov(
                    state,
                    alloc.amount,
                    alloc.cost_code,
                    getattr(alloc, 'description', None),
                )
                total_applied += applied

        for alloc in allocations:
            targets = resolve_sub_sov_targets_for_allocation(co, sub_sov, alloc, Commitment)
            sub_sov = state.get('subcontractorSOV') or sub_sov
            for company_key in targets:
                state, sub_applied = apply_co_to_subcontractor_sov(
                    state,
                    company_key,
                    alloc.amount,
                    alloc.cost_code,
                    getattr(alloc, 'description', None),
                    co.number,
                )
                if sub_applied:
                    sub_total_applied += sub_applied
                    sub_updates.append({
                        'company_key': company_key,
                        'cost_code': alloc.cost_code,
                        'amount': sub_applied,
                    })
            sub_sov = state.get('subcontractorSOV') or sub_sov
    elif not already_contractor_synced:
        state, applied = apply_co_to_contractor_sov(state, co.amount, getattr(co, 'cost_code', None))
        total_applied += applied

    if not already_contractor_synced or sub_total_applied > 0:
        save_pay_app_state(PayAppProjectState, db, co.project_id, state, user_id)
    if not already_contractor_synced:
        co.sov_synced_at = datetime.utcnow()
        schedule_result = apply_schedule_impact(
            ScheduleData, Project, db, co.project_id,
            co.schedule_impact, co.number, co.description,
        )
    else:
        schedule_result = None
        if sub_total_applied > 0:
            db.session.commit()
        else:
            return {
                'already_synced': True,
                'sov_amount_applied': 0,
                'sub_sov_amount_applied': 0,
                'contractorSOV': state.get('contractorSOV'),
                'subcontractorSOV': state.get('subcontractorSOV'),
                'sub_sov_updates': [],
            }

    if not already_contractor_synced:
        db.session.commit()
    return {
        'already_synced': already_contractor_synced,
        'sov_amount_applied': total_applied,
        'sub_sov_amount_applied': sub_total_applied,
        'sub_sov_updates': sub_updates,
        'contractorSOV': state.get('contractorSOV'),
        'subcontractorSOV': state.get('subcontractorSOV'),
        'schedule': schedule_result,
    }


def commitment_matches_vendor(commitment, company_id=None, company_name=None, status_entry=None):
    """True when a commitment belongs to the given subcontractor vendor."""
    if status_entry is not None:
        return commitment_matches_sov_entry(
            commitment,
            company_id,
            status_entry,
            company_name=company_name,
        )
    if getattr(commitment, 'commitment_type', None) != 'Subcontract':
        return False
    cid = str(company_id or '').strip()
    cname = (company_name or '').strip().lower()
    com_cid = str(getattr(commitment, 'company_id', None) or '').strip()
    com_name = (commitment.company_name or '').strip().lower()
    if cid and com_cid and cid == com_cid:
        return True
    if cname and com_name and cname == com_name:
        return True
    return False


def purge_subcontractor_from_pay_state(state, company_id=None, company_name=None):
    """Remove a subcontractor and all pay-app artifacts from in-memory pay state."""
    from accounting_reconcile import normalize_sub_sov_keys

    state = state or {}
    keys = _find_sub_sov_keys_for_company(state.get('subcontractorSOV') or {}, company_id, company_name)
    if not keys:
        keys = _find_sub_sov_keys_for_company(state.get('subcontractorSOV') or {}, None, company_name)

    key_set = set(str(k) for k in keys)

    def drop_keys(mapping):
        if not isinstance(mapping, dict):
            return 0
        removed = 0
        for k in list(mapping.keys()):
            if str(k) in key_set:
                del mapping[k]
                removed += 1
        return removed

    purged = {}
    for field in (
        'subcontractorSOV', 'subPayAppHistory', 'subPendingSubmissions',
        'subPayAppNumbers', 'subSOVStatus', 'subLienWaivers', 'subLienWaiverArchive',
    ):
        mapping = state.get(field) or {}
        if not isinstance(mapping, dict):
            mapping = {}
        purged[field] = drop_keys(mapping)
        state[field] = mapping

    archive = state.get('previousSubPayAppArchive') or []
    if isinstance(archive, list):
        before = len(archive)
        state['previousSubPayAppArchive'] = [
            entry for entry in archive
            if str(entry.get('companyId') or entry.get('company_id') or '') not in key_set
            and str(entry.get('companyName') or entry.get('company_name') or '').strip().lower()
            != (company_name or '').strip().lower()
        ]
        purged['previousSubPayAppArchive'] = before - len(state['previousSubPayAppArchive'])
    else:
        purged['previousSubPayAppArchive'] = 0

    state['subcontractorSOV'] = normalize_sub_sov_keys(state.get('subcontractorSOV') or {})
    return {'purged': purged, 'keys': keys}


def void_subcontractor_commitments(
    project_id,
    company_id=None,
    company_name=None,
    *,
    Commitment,
    db,
    user_id=None,
    allow_approved=True,
):
    """Void subcontract commitments for a vendor so reconcile stops re-seeding their SOV."""
    commitments = Commitment.query.filter_by(project_id=project_id).all()
    voided = []
    for com in commitments:
        if not commitment_matches_vendor(com, company_id, company_name):
            continue
        if com.status == 'Void':
            continue
        if com.status not in ('Draft', 'Rejected', 'Void') and not allow_approved:
            continue
        if com.status not in ('Draft', 'Rejected', 'Void'):
            com.status = 'Void'
            com.ball_in_court_role = None
        else:
            com.status = 'Void'
            com.ball_in_court_role = None
        voided.append({'id': com.id, 'number': com.number, 'status': com.status})
    if voided:
        db.session.flush()
    return voided


SUBCONTRACTOR_PAY_STATE_FIELDS = (
    'subcontractorSOV', 'subPayAppHistory', 'subPendingSubmissions',
    'subPayAppNumbers', 'subSOVStatus', 'subLienWaivers', 'subLienWaiverArchive',
    'previousSubPayAppArchive',
)


def _sub_sov_line_has_activity(line):
    """True when a line has billings, commitments, or in-period work that should survive without a commitment."""
    if not isinstance(line, dict):
        return False
    if float(line.get('original_commitment') or 0) != 0:
        return True
    if float(line.get('change_orders') or 0) != 0:
        return True
    for field in ('billed_to_date', 'co_billed_to_date', 'work_this_period', 'materials_stored'):
        if float(line.get(field) or 0) != 0:
            return True
    return False


def _sub_pay_state_has_vendor_activity(state, company_key):
    """True when a vendor key has pay-app history, pending work, or status beyond an empty SOV."""
    key = str(company_key).strip()
    if not key:
        return False

    for field in ('subPayAppHistory', 'subPendingSubmissions', 'subPayAppNumbers', 'subSOVStatus', 'subLienWaivers'):
        mapping = state.get(field) or {}
        if isinstance(mapping, dict) and key in mapping:
            return True

    archive = state.get('previousSubPayAppArchive') or []
    if isinstance(archive, list):
        for entry in archive:
            if not isinstance(entry, dict):
                continue
            entry_key = str(entry.get('companyId') or entry.get('company_id') or '').strip()
            if entry_key == key:
                return True

    lien_archive = state.get('subLienWaiverArchive') or {}
    if isinstance(lien_archive, dict) and key in lien_archive:
        return True

    return False


def _commitment_matches_sov_key(com, company_key):
    """True when a commitment belongs to the subcontractor SOV bucket key."""
    from accounting_reconcile import _canonical_company_key

    canon_key = str(company_key).strip()
    if not canon_key:
        return False
    com_canon = _canonical_company_key(getattr(com, 'company_id', None), com.company_name)
    if canon_key == com_canon:
        return True
    if str(getattr(com, 'company_id', None) or '').strip() == canon_key:
        return True
    if (getattr(com, 'company_name', None) or '').strip() == canon_key:
        return True
    return False


def _active_subcontract_commitment_keys(commitments):
    """Canonical vendor keys for non-void subcontract commitments."""
    from accounting_reconcile import _canonical_company_key

    keys = set()
    for com in commitments or []:
        if getattr(com, 'commitment_type', None) != 'Subcontract':
            continue
        if getattr(com, 'status', None) in ('Void', 'Rejected'):
            continue
        keys.add(_canonical_company_key(getattr(com, 'company_id', None), com.company_name))
        cid = str(getattr(com, 'company_id', None) or '').strip()
        cname = (getattr(com, 'company_name', None) or '').strip()
        if cid:
            keys.add(cid)
        if cname:
            keys.add(cname)
    return {k for k in keys if k}


def _sov_key_has_active_commitment(company_key, commitments, state=None):
    status = (state or {}).get('subSOVStatus') or {}
    entry = status.get(company_key) or status.get(str(company_key)) or {}
    for com in commitments or []:
        if getattr(com, 'commitment_type', None) != 'Subcontract':
            continue
        if getattr(com, 'status', None) in ('Void', 'Rejected'):
            continue
        if commitment_matches_sov_entry(com, company_key, entry):
            return True
        if _commitment_matches_sov_key(com, company_key):
            return True
    return False


def _sov_key_is_gc_registered(state, company_key):
    status = (state or {}).get('subSOVStatus') or {}
    entry = status.get(company_key) or status.get(str(company_key)) or {}
    return isinstance(entry, dict) and bool(entry.get('status'))


def prune_orphan_subcontractor_sov(state, commitments=None):
    """Drop subcontractor SOV vendors/lines that no longer have backing commitments or activity."""
    from accounting_reconcile import normalize_sub_sov_keys

    state = state or {}
    sub_sov = normalize_sub_sov_keys(state.get('subcontractorSOV') or {})
    commitments = commitments or []

    removed_keys = []
    removed_lines = 0
    cleaned = {}

    for company_key, lines in (sub_sov or {}).items():
        has_commitment = _sov_key_has_active_commitment(company_key, commitments, state)
        kept_lines = []
        for line in lines or []:
            if has_commitment or _sub_sov_line_has_activity(line):
                kept_lines.append(line)
            else:
                removed_lines += 1

        if kept_lines:
            cleaned[company_key] = kept_lines
        elif (
            has_commitment
            or _sub_pay_state_has_vendor_activity(state, company_key)
            or _sov_key_is_gc_registered(state, company_key)
        ):
            cleaned[company_key] = []
        else:
            removed_keys.append(company_key)

    state['subcontractorSOV'] = normalize_sub_sov_keys(cleaned)
    return {'removed_keys': removed_keys, 'removed_lines': removed_lines}


def clear_all_subcontractor_pay_data(state):
    """Remove all subcontractor SOV and pay-app artifacts from in-memory pay state."""
    state = state or {}
    cleared = {}
    for field in SUBCONTRACTOR_PAY_STATE_FIELDS:
        before = state.get(field)
        if field == 'previousSubPayAppArchive':
            state[field] = []
            cleared[field] = len(before) if isinstance(before, list) else 0
        else:
            count = len(before) if isinstance(before, dict) else 0
            state[field] = {}
            cleared[field] = count
    return {'cleared': cleared}


def void_all_subcontractor_commitments(project_id, *, Commitment, db, user_id=None):
    """Void every subcontract commitment on a project."""
    voided = []
    for com in Commitment.query.filter_by(project_id=project_id).all():
        if getattr(com, 'commitment_type', None) != 'Subcontract':
            continue
        if com.status == 'Void':
            continue
        com.status = 'Void'
        com.ball_in_court_role = None
        voided.append({'id': com.id, 'number': com.number, 'status': com.status})
    if voided:
        db.session.flush()
    return voided
