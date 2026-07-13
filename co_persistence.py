"""Change Order & PCO persistence helpers, schema migration, and serialization."""
from __future__ import annotations

import json
from datetime import datetime

CO_STATUSES = (
    'Draft', 'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect',
    'Pending Accounting', 'Approved', 'Rejected', 'Void',
)
SUB_CO_KINDS = ('Contract Add', 'Budget Transfer', 'Owner CO Backcharge')
SUB_CO_STATUSES = (
    'Draft', 'Submitted', 'Under Review', 'Pending Accounting', 'Approved', 'Rejected', 'Void',
)
PCO_STATUSES = (
    'Open', 'Pricing', 'Pending Review', 'Approved for CO', 'Promoted', 'Void', 'Closed',
)
OWNER_CO_APPROVAL_THRESHOLD = 50000.0
PCO_BALL_IN_COURT_MAP = {
    'Open': 'Creator',
    'Pricing': 'Project Manager',
    'Pending Review': 'Project Manager',
    'Approved for CO': 'Project Manager',
    'Promoted': None,
    'Void': None,
    'Closed': None,
}
PCO_APPROVAL_CHAIN = (
    {'from_status': 'Open', 'role': 'Project Manager', 'next_status': 'Pricing'},
    {'from_status': 'Pricing', 'role': 'Project Manager', 'next_status': 'Pending Review'},
    {'from_status': 'Pending Review', 'role': 'Project Manager', 'next_status': 'Approved for CO'},
)
BALL_IN_COURT_MAP = {
    'Draft': 'Creator',
    'Submitted': 'Project Manager',
    'Under Review': 'Project Manager',
    'Pending Architect': 'Architect',
    'Pending Owner': 'Owner',
    'Pending Accounting': 'Contractor Accounting',
    'Approved': None,
    'Rejected': None,
    'Void': None,
}
SUB_BALL_IN_COURT_MAP = {
    'Draft': 'Creator',
    'Submitted': 'Project Manager',
    'Under Review': 'Project Manager',
    'Pending Accounting': 'Contractor Accounting',
    'Approved': None,
    'Rejected': None,
    'Void': None,
}

# Sequential approval chain (owner / prime contract COs) — Procore-style with accounting gate before Sage export
APPROVAL_CHAIN = (
    {'from_status': 'Submitted', 'role': 'Project Manager', 'next_status': 'Pending Architect'},
    {'from_status': 'Pending Architect', 'role': 'Architect', 'next_status': 'Pending Owner'},
    {'from_status': 'Pending Owner', 'role': 'Owner', 'next_status': 'Pending Accounting'},
    {'from_status': 'Pending Accounting', 'role': 'Contractor Accounting', 'next_status': 'Approved'},
)
# Subcontractor change order approval: PM → Contractor Accounting (no Owner/Architect e-sign)
SUB_APPROVAL_CHAIN = (
    {'from_status': 'Submitted', 'role': 'Project Manager', 'next_status': 'Pending Accounting'},
    {'from_status': 'Pending Accounting', 'role': 'Contractor Accounting', 'next_status': 'Approved'},
)

ROLE_APPROVERS = {
    'Project Manager': ('Project Manager', 'Admin', 'Contractor Accounting'),
    'Architect': ('Architect', 'Admin'),
    'Owner': ('Owner', 'Admin'),
    'Creator': ('Project Manager', 'Admin', 'Company User'),
    'Subcontractor': ('Subcontractor Accountant', 'Company User', 'Subcontractor', 'Admin'),
}
REASON_CODES = (
    'Owner Request', 'Design Change', 'Unforeseen Condition', 'Code Compliance',
    'Error or Omission', 'Value Engineering', 'Schedule Acceleration', 'Other',
)
DEFAULT_COST_TYPES = (
    'Labor', 'Material', 'Subcontract', 'Equipment', 'General Conditions', 'Other',
)

SCHEDULE_IMPACT_OPTIONS = {
    'none': 0,
    'no impact': 0,
    'minor': 5,
    'moderate': 10,
    'significant': 14,
    'major': 14,
    'critical': 30,
}


def _sqlite_has_global_number_unique(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA index_list('change_order')")).fetchall()
        for row in rows:
            if not row[2]:
                continue
            name = row[1]
            cols = conn.execute(text(f'PRAGMA index_info("{name}")')).fetchall()
            if [c[2] for c in cols] == ['number']:
                return True
    return False


def _migrate_change_order_project_number(engine, db):
    """Replace global unique change_order.number with (project_id, number) scope."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if 'change_order' not in inspector.get_table_names():
        return

    if not _sqlite_has_global_number_unique(engine):
        try:
            db.session.execute(text(
                'CREATE UNIQUE INDEX IF NOT EXISTS uq_change_order_project_number '
                'ON change_order (project_id, number)'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
        return

    cols = inspector.get_columns('change_order')
    col_names = [c['name'] for c in cols]

    def _sqlite_col_def(col):
        name = col['name']
        raw = str(col.get('type', '')).upper()
        if 'INT' in raw:
            sql_type = 'INTEGER'
        elif 'FLOAT' in raw or 'REAL' in raw or 'NUMERIC' in raw:
            sql_type = 'FLOAT'
        elif 'BOOL' in raw:
            sql_type = 'INTEGER'
        elif 'DATETIME' in raw or 'TIMESTAMP' in raw:
            sql_type = 'DATETIME'
        elif 'DATE' in raw:
            sql_type = 'DATE'
        elif 'TEXT' in raw:
            sql_type = 'TEXT'
        else:
            sql_type = 'VARCHAR(255)'
        nullable = '' if col.get('nullable', True) else ' NOT NULL'
        if name == 'id':
            return 'id INTEGER PRIMARY KEY'
        if name == 'number':
            return 'number VARCHAR(30) NOT NULL'
        return f'{name} {sql_type}{nullable}'

    ddl = ', '.join(_sqlite_col_def(c) for c in cols)
    col_list = ', '.join(col_names)
    try:
        db.session.execute(text('PRAGMA foreign_keys=OFF'))
        db.session.execute(text('DROP TABLE IF EXISTS change_order__new'))
        db.session.execute(text(f'CREATE TABLE change_order__new ({ddl})'))
        db.session.execute(text(
            f'INSERT INTO change_order__new ({col_list}) SELECT {col_list} FROM change_order'
        ))
        db.session.execute(text('DROP TABLE change_order'))
        db.session.execute(text('ALTER TABLE change_order__new RENAME TO change_order'))
        db.session.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS uq_change_order_project_number '
            'ON change_order (project_id, number)'
        ))
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            db.session.execute(text('PRAGMA foreign_keys=ON'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        raise


def ensure_co_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if 'change_order' in tables:
        cols = {c['name'] for c in inspector.get_columns('change_order')}
        additions = {
            'title': 'VARCHAR(200)',
            'company_name': 'VARCHAR(200)',
            'company_id': 'VARCHAR(64)',
            'contact_name': 'VARCHAR(150)',
            'contact_email': 'VARCHAR(150)',
            'contact_phone': 'VARCHAR(50)',
            'ball_in_court_role': 'VARCHAR(80)',
            'source_pco_id': 'INTEGER',
            'schedule_impact_days': 'INTEGER DEFAULT 0',
            'contract_type': 'VARCHAR(40)',
            'submitted_at': 'DATETIME',
            'attachments_json': 'TEXT',
            'linked_rfi_id': 'INTEGER',
            'linked_commitment_ref': 'VARCHAR(80)',
            'approval_stage': 'INTEGER DEFAULT 0',
            'plan_pins_json': 'TEXT',
            'approval_history_json': 'TEXT',
            'approval_signatures_json': 'TEXT',
            'executed_locked': 'INTEGER DEFAULT 0',
            'linked_owner_co_id': 'INTEGER',
            'sub_co_kind': 'VARCHAR(40)',
            'auto_generated': 'INTEGER DEFAULT 0',
        }
        for name, col_type in additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE change_order ADD COLUMN {name} {col_type}'))
        db.session.commit()
        _migrate_change_order_project_number(engine, db)

    if 'change_order_allocation' in tables:
        cols = {c['name'] for c in inspector.get_columns('change_order_allocation')}
        alloc_additions = {
            'description': 'VARCHAR(200)',
            'cost_type': 'VARCHAR(80)',
        }
        for name, col_type in alloc_additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE change_order_allocation ADD COLUMN {name} {col_type}'))
        db.session.commit()

    if 'pco_allocation' in tables:
        cols = {c['name'] for c in inspector.get_columns('pco_allocation')}
        if 'cost_type' not in cols:
            db.session.execute(text('ALTER TABLE pco_allocation ADD COLUMN cost_type VARCHAR(80)'))
            db.session.commit()

    if 'potential_change_order' in tables:
        cols = {c['name'] for c in inspector.get_columns('potential_change_order')}
        pco_additions = {
            'linked_rfi_id': 'INTEGER',
            'linked_commitment_ref': 'VARCHAR(80)',
            'attachments_json': 'TEXT',
        }
        for name, col_type in pco_additions.items():
            if name not in cols:
                db.session.execute(text(f'ALTER TABLE potential_change_order ADD COLUMN {name} {col_type}'))
        db.session.commit()


def schedule_impact_to_days(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    for key, days in SCHEDULE_IMPACT_OPTIONS.items():
        if key in text:
            return days
    return 0


def schedule_days_to_label(days):
    days = int(days or 0)
    if days <= 0:
        return 'None'
    if days <= 5:
        return 'Minor'
    if days <= 10:
        return 'Moderate'
    return 'Significant'


def is_subcontract_co(co):
    ctype = (getattr(co, 'contract_type', None) or '').strip()
    return ctype in ('Subcontract', 'Subcontractor')


def co_ball_in_court_map(co):
    return SUB_BALL_IN_COURT_MAP if is_subcontract_co(co) else BALL_IN_COURT_MAP


def co_approval_chain(co):
    return SUB_APPROVAL_CHAIN if is_subcontract_co(co) else APPROVAL_CHAIN


def _allocation_row(a):
    """Normalize ORM allocation or plain dict for API responses."""
    if isinstance(a, dict):
        return {
            'cost_code': a.get('cost_code'),
            'cost_type': a.get('cost_type') or '',
            'amount': a.get('amount'),
            'description': a.get('description', ''),
            'sov_line_id': a.get('sov_line_id'),
            'tax_group': a.get('tax_group'),
            'retainage_percent': a.get('retainage_percent'),
        }
    return {
        'cost_code': a.cost_code,
        'cost_type': getattr(a, 'cost_type', None) or '',
        'amount': a.amount,
        'description': getattr(a, 'description', ''),
        'sov_line_id': getattr(a, 'sov_line_id', None),
        'tax_group': getattr(a, 'tax_group', None),
        'retainage_percent': getattr(a, 'retainage_percent', None),
    }


def co_to_dict(co, allocations=None, revisions=None):
    allocs = allocations
    if allocs is None and hasattr(co, '_allocations_cache'):
        allocs = co._allocations_cache
    days_val = getattr(co, 'schedule_impact_days', None)
    if days_val is None:
        days_val = schedule_impact_to_days(co.schedule_impact)
    else:
        days_val = int(days_val or 0)
    return {
        'id': co.id,
        'project_id': co.project_id,
        'number': co.number,
        'title': getattr(co, 'title', None) or co.description,
        'description': co.description,
        'amount': co.amount or 0,
        'reason': co.reason,
        'schedule_impact': co.schedule_impact,
        'schedule_impact_days': days_val,
        'status': co.status,
        'date': co.date.isoformat() if co.date else None,
        'cost_code': co.cost_code,
        'requested_by': co.requested_by,
        'priority': co.priority,
        'revision': co.revision or 0,
        'notes': co.notes,
        'company_name': getattr(co, 'company_name', None),
        'company_id': getattr(co, 'company_id', None),
        'contact_name': getattr(co, 'contact_name', None),
        'contact_email': getattr(co, 'contact_email', None),
        'contact_phone': getattr(co, 'contact_phone', None),
        'ball_in_court_role': getattr(co, 'ball_in_court_role', None),
        'source_pco_id': getattr(co, 'source_pco_id', None),
        'contract_type': getattr(co, 'contract_type', None) or 'Owner',
        'submitted_at': co.submitted_at.isoformat() if getattr(co, 'submitted_at', None) else None,
        'approved_at': co.approved_at.isoformat() if co.approved_at else None,
        'sov_synced_at': co.sov_synced_at.isoformat() if co.sov_synced_at else None,
        'sage_sync_status': co.sage_sync_status,
        'attachments': _parse_json(getattr(co, 'attachments_json', None), []),
        'linked_rfi_id': getattr(co, 'linked_rfi_id', None),
        'linked_commitment_ref': getattr(co, 'linked_commitment_ref', None),
        'plan_pins': _parse_json(getattr(co, 'plan_pins_json', None), []),
        'approval_stage': getattr(co, 'approval_stage', 0) or 0,
        'approval_history': _parse_json(getattr(co, 'approval_history_json', None), []),
        'approval_signatures': _parse_json(getattr(co, 'approval_signatures_json', None), []),
        'executed_locked': bool(getattr(co, 'executed_locked', False)),
        'linked_owner_co_id': getattr(co, 'linked_owner_co_id', None),
        'sub_co_kind': getattr(co, 'sub_co_kind', None) or ('Owner CO Backcharge' if getattr(co, 'linked_owner_co_id', None) else None),
        'auto_generated': bool(getattr(co, 'auto_generated', False)),
        'change_event_id': getattr(co, 'change_event_id', None),
        'source_rfq_id': getattr(co, 'source_rfq_id', None),
        'linked_cor_id': getattr(co, 'linked_cor_id', None),
        'linked_drawing_revision': getattr(co, 'linked_drawing_revision', None),
        'source_cpco_id': getattr(co, 'source_cpco_id', None),
        'billed_amount': float(getattr(co, 'billed_amount', 0) or 0),
        'billing_variance': float(getattr(co, 'billing_variance', 0) or 0),
        'is_subcontract': is_subcontract_co(co),
        'allocations': [_allocation_row(a) for a in (allocs or [])],
        'created_at': co.created_at.isoformat() if co.created_at else None,
    }


def enrich_co_dict_links(co_dict, ChangeOrder, owner_co=None):
    """Attach linked owner CO summary and child subcontractor COs for API responses."""
    if not co_dict or ChangeOrder is None:
        return co_dict
    owner_id = co_dict.get('linked_owner_co_id')
    if owner_id:
        owner = owner_co if owner_co is not None else ChangeOrder.query.get(int(owner_id))
        if owner:
            co_dict['linked_owner_co'] = {
                'id': owner.id,
                'number': owner.number,
                'title': getattr(owner, 'title', None) or owner.description,
                'amount': owner.amount or 0,
                'status': owner.status,
            }
            if co_dict.get('amount') is not None:
                co_dict['owner_sub_variance'] = round(float(co_dict.get('amount') or 0) - float(owner.amount or 0), 2)
    if not co_dict.get('is_subcontract'):
        subs = ChangeOrder.query.filter_by(linked_owner_co_id=co_dict.get('id')).order_by(
            ChangeOrder.created_at.desc()
        ).all()
        co_dict['linked_sub_change_orders'] = [{
            'id': s.id,
            'number': s.number,
            'title': getattr(s, 'title', None) or s.description,
            'amount': s.amount or 0,
            'status': s.status,
            'company_name': getattr(s, 'company_name', None),
            'sub_co_kind': getattr(s, 'sub_co_kind', None),
            'auto_generated': bool(getattr(s, 'auto_generated', False)),
        } for s in subs]
        if subs and co_dict.get('amount') is not None:
            sub_total = sum(float(s.amount or 0) for s in subs)
            co_dict['linked_sub_total'] = round(sub_total, 2)
            co_dict['owner_sub_variance'] = round(float(co_dict.get('amount') or 0) - sub_total, 2)
    return co_dict


def pco_to_dict(pco, allocations=None):
    allocs = allocations
    return {
        'id': pco.id,
        'project_id': pco.project_id,
        'number': pco.number,
        'title': pco.title,
        'description': pco.description,
        'estimated_amount': pco.estimated_amount or 0,
        'status': pco.status,
        'reason': pco.reason,
        'priority': pco.priority,
        'schedule_impact_days': pco.schedule_impact_days or 0,
        'company_name': pco.company_name,
        'company_id': pco.company_id,
        'contact_name': pco.contact_name,
        'contact_email': pco.contact_email,
        'contact_phone': pco.contact_phone,
        'requested_by': pco.requested_by,
        'ball_in_court_role': pco.ball_in_court_role,
        'cost_code': pco.cost_code,
        'notes': pco.notes,
        'change_order_id': pco.change_order_id,
        'linked_rfi_id': getattr(pco, 'linked_rfi_id', None),
        'linked_commitment_ref': getattr(pco, 'linked_commitment_ref', None),
        'attachments': _parse_json(getattr(pco, 'attachments_json', None), []),
        'allocations': [{
            'cost_code': a.cost_code,
            'cost_type': getattr(a, 'cost_type', None) or '',
            'amount': a.amount,
            'description': getattr(a, 'description', ''),
        } for a in (allocs or [])],
        'updated_at': pco.updated_at.isoformat() if pco.updated_at else None,
    }


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def apply_co_fields(co, data):
    if data.get('title') is not None:
        co.title = data['title']
    if data.get('description') is not None:
        co.description = data['description']
    if data.get('amount') is not None:
        if co.status in ('Draft', 'Rejected'):
            co.amount = float(data['amount'])
    if data.get('reason') is not None:
        co.reason = data['reason']
    if data.get('priority') is not None:
        co.priority = data['priority']
    if data.get('notes') is not None:
        co.notes = data['notes']
    if data.get('cost_code') is not None:
        co.cost_code = data['cost_code']
    if data.get('requested_by') is not None:
        co.requested_by = data['requested_by']
    if data.get('status') is not None:
        pass  # status changes only via /workflow
    if data.get('revision') is not None:
        co.revision = int(data['revision'])
    if data.get('company_name') is not None:
        co.company_name = data['company_name']
    if data.get('company_id') is not None:
        co.company_id = data['company_id']
    if data.get('contact_name') is not None:
        co.contact_name = data['contact_name']
    if data.get('contact_email') is not None:
        co.contact_email = data['contact_email']
    if data.get('contact_phone') is not None:
        co.contact_phone = data['contact_phone']
    if data.get('contract_type') is not None:
        co.contract_type = data['contract_type']
    if data.get('source_pco_id') is not None:
        co.source_pco_id = data['source_pco_id']
    if data.get('schedule_impact_days') is not None:
        co.schedule_impact_days = int(data['schedule_impact_days'])
        co.schedule_impact = schedule_days_to_label(co.schedule_impact_days)
    elif data.get('schedule_impact') is not None:
        co.schedule_impact = data['schedule_impact']
        co.schedule_impact_days = schedule_impact_to_days(data['schedule_impact'])
    if data.get('ball_in_court_role') is not None:
        pass  # ball-in-court only via /workflow
    if data.get('attachments') is not None:
        co.attachments_json = json.dumps(data['attachments'])
    if data.get('linked_rfi_id') is not None:
        co.linked_rfi_id = int(data['linked_rfi_id']) if data['linked_rfi_id'] else None
    if data.get('linked_commitment_ref') is not None:
        co.linked_commitment_ref = data['linked_commitment_ref']
    if data.get('linked_owner_co_id') is not None:
        co.linked_owner_co_id = int(data['linked_owner_co_id']) if data['linked_owner_co_id'] else None
    if data.get('sub_co_kind') is not None:
        co.sub_co_kind = data['sub_co_kind']
    if data.get('auto_generated') is not None:
        co.auto_generated = bool(data['auto_generated'])
    if data.get('date') is not None:
        from datetime import datetime
        raw = data['date']
        if isinstance(raw, str) and raw:
            try:
                co.date = datetime.strptime(raw[:10], '%Y-%m-%d').date()
            except ValueError:
                pass


def apply_pco_fields(pco, data):
    for field in ('title', 'description', 'reason', 'priority', 'notes', 'cost_code', 'requested_by',
                  'company_name', 'company_id', 'contact_name', 'contact_email', 'contact_phone',
                  'linked_commitment_ref'):
        if data.get(field) is not None:
            setattr(pco, field, data[field])
    if data.get('ball_in_court_role') is not None:
        pass  # workflow only
    if data.get('linked_rfi_id') is not None:
        pco.linked_rfi_id = int(data['linked_rfi_id']) if data['linked_rfi_id'] else None
    if data.get('estimated_amount') is not None:
        pco.estimated_amount = float(data['estimated_amount'])
    if data.get('status') is not None:
        pass  # status only via /workflow
    if data.get('schedule_impact_days') is not None:
        pco.schedule_impact_days = int(data['schedule_impact_days'])


def normalize_allocation_rows(allocations):
    """Return non-empty allocation rows from request payload."""
    rows = []
    for item in allocations or []:
        code = (item.get('cost_code') or '').strip()
        ctype = (item.get('cost_type') or '').strip()
        desc = (item.get('description') or '').strip()
        amt = float(item.get('amount') or 0)
        if code or ctype or desc or amt:
            rows.append({
                'cost_code': code,
                'cost_type': ctype,
                'amount': amt,
                'description': desc,
            })
    return rows


def validate_allocations(allocations, *, require_rows=True, require_amount=False, sub_co_kind=None):
    rows = normalize_allocation_rows(allocations)
    if require_rows and not rows:
        raise ValueError('At least one cost code allocation is required (cost code, cost type, and amount).')
    cleaned = []
    for i, item in enumerate(rows, 1):
        if not item['cost_code']:
            raise ValueError(f'Allocation row {i}: cost code is required.')
        if not item['cost_type']:
            raise ValueError(f'Allocation row {i}: cost type is required.')
        if require_amount and item['amount'] == 0:
            raise ValueError(f'Allocation row {i}: amount must be non-zero.')
        cleaned.append(item)

    kind = (sub_co_kind or '').strip()
    if kind == 'Budget Transfer':
        if len(cleaned) < 2:
            raise ValueError('Budget transfer requires at least two allocation rows (from and to cost codes).')
        net = round(sum(float(r['amount'] or 0) for r in cleaned), 2)
        if net != 0:
            raise ValueError(f'Budget transfer allocations must net to zero (current net: {net:,.2f}).')
        positives = [r for r in cleaned if float(r['amount'] or 0) > 0]
        negatives = [r for r in cleaned if float(r['amount'] or 0) < 0]
        if not positives or not negatives:
            raise ValueError('Budget transfer requires at least one positive and one negative allocation row.')
    elif kind == 'Contract Add' and require_amount:
        total = sum(float(r['amount'] or 0) for r in cleaned)
        if total <= 0:
            raise ValueError('Contract add subcontractor change orders require a positive total amount.')
    return cleaned


def save_allocations(AllocationModel, parent_id_field, parent_id, allocations, db, extra_fields=None):
    AllocationModel.query.filter(getattr(AllocationModel, parent_id_field) == parent_id).delete()
    for item in allocations or []:
        kwargs = {
            parent_id_field: parent_id,
            'cost_code': item.get('cost_code'),
            'amount': float(item.get('amount') or 0),
        }
        if extra_fields:
            kwargs.update(extra_fields(item))
        row = AllocationModel(**kwargs)
        if hasattr(row, 'description'):
            row.description = item.get('description', '')
        if hasattr(row, 'cost_type'):
            row.cost_type = item.get('cost_type', '')
        if hasattr(row, 'sov_line_id') and item.get('sov_line_id'):
            row.sov_line_id = item.get('sov_line_id')
        if hasattr(row, 'tax_group') and item.get('tax_group'):
            row.tax_group = item.get('tax_group')
        if hasattr(row, 'retainage_percent') and item.get('retainage_percent') is not None:
            row.retainage_percent = float(item.get('retainage_percent'))
        db.session.add(row)


def promote_pco_to_co(
    PotentialChangeOrder,
    PCOAllocation,
    ChangeOrder,
    ChangeOrderAllocation,
    db,
    pco_id,
    user_id,
    generate_number_fn,
):
    pco = PotentialChangeOrder.query.get(pco_id)
    if not pco:
        raise ValueError('PCO not found')
    if pco.change_order_id:
        raise ValueError('PCO already promoted')
    if pco.status not in ('Approved for CO',):
        raise ValueError('PCO must be Approved for CO before promotion')

    allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
    total = sum(a.amount for a in allocs) if allocs else (pco.estimated_amount or 0)
    alloc_payload = [{
        'cost_code': a.cost_code,
        'cost_type': getattr(a, 'cost_type', None),
        'amount': a.amount,
        'description': getattr(a, 'description', ''),
    } for a in allocs]
    validate_allocations(alloc_payload, require_rows=True, require_amount=True)

    co = ChangeOrder(
        project_id=pco.project_id,
        number=generate_number_fn('CO', ChangeOrder, doc_type='change_order', project_id=pco.project_id),
        title=pco.title,
        description=pco.description or pco.title or 'Change Order from PCO',
        amount=total,
        reason=pco.reason,
        schedule_impact=schedule_days_to_label(pco.schedule_impact_days),
        schedule_impact_days=pco.schedule_impact_days or 0,
        status='Draft',
        date=datetime.utcnow().date(),
        cost_code=pco.cost_code,
        requested_by=pco.requested_by,
        priority=pco.priority,
        notes=pco.notes,
        company_name=pco.company_name,
        company_id=pco.company_id,
        contact_name=pco.contact_name,
        contact_email=pco.contact_email,
        contact_phone=pco.contact_phone,
        source_pco_id=pco.id,
        ball_in_court_role='Creator',
        contract_type='Owner',
        linked_rfi_id=getattr(pco, 'linked_rfi_id', None),
        created_by_id=user_id,
    )
    db.session.add(co)
    db.session.flush()

    if allocs:
        for a in allocs:
            db.session.add(ChangeOrderAllocation(
                change_order_id=co.id,
                cost_code=a.cost_code,
                cost_type=getattr(a, 'cost_type', None) or '',
                amount=a.amount,
                description=getattr(a, 'description', '') or '',
            ))
    elif pco.cost_code and total:
        db.session.add(ChangeOrderAllocation(
            change_order_id=co.id,
            cost_code=pco.cost_code,
            cost_type='Other',
            amount=total,
        ))

    pco.change_order_id = co.id
    pco.status = 'Promoted'
    pco.ball_in_court_role = None
    db.session.commit()
    return co


def compute_dashboard_stats(ChangeOrder, PotentialChangeOrder, project_id):
    cos = ChangeOrder.query.filter_by(project_id=project_id).all()
    owner_cos = [c for c in cos if not is_subcontract_co(c)]
    sub_cos = [c for c in cos if is_subcontract_co(c)]
    pcos = PotentialChangeOrder.query.filter_by(project_id=project_id).all()

    approved = [c for c in owner_cos if c.status == 'Approved']
    pending_statuses = {'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect', 'Pending'}
    pending = [c for c in owner_cos if c.status in pending_statuses]
    sub_pending_statuses = {'Submitted', 'Under Review', 'Pending Accounting', 'Pending'}
    sub_approved = [c for c in sub_cos if c.status == 'Approved']
    sub_pending = [c for c in sub_cos if c.status in sub_pending_statuses]
    open_pcos = [p for p in pcos if p.status not in ('Promoted', 'Void', 'Closed')]

    approved_total = sum(c.amount or 0 for c in approved)
    pending_total = sum(c.amount or 0 for c in pending)
    sub_approved_total = sum(c.amount or 0 for c in sub_approved)
    sub_pending_total = sum(c.amount or 0 for c in sub_pending)
    pco_rom = sum(p.estimated_amount or 0 for p in open_pcos)

    approval_days = []
    for c in approved:
        if c.approved_at and c.created_at:
            approval_days.append((c.approved_at - c.created_at).total_seconds() / 86400)
    avg_days = round(sum(approval_days) / len(approval_days), 1) if approval_days else 0

    return {
        'total_cos': len(owner_cos),
        'approved_count': len(approved),
        'pending_count': len(pending),
        'open_pco_count': len(open_pcos),
        'approved_total': approved_total,
        'pending_total': pending_total,
        'pco_rom_total': pco_rom,
        'avg_approval_days': avg_days,
        'total_sub_cos': len(sub_cos),
        'sub_approved_count': len(sub_approved),
        'sub_pending_count': len(sub_pending),
        'sub_approved_total': sub_approved_total,
        'sub_pending_total': sub_pending_total,
    }


def get_budget_cost_types(BudgetProjectState, project_id):
    from budget_persistence import get_budget_state
    _, state = get_budget_state(BudgetProjectState, project_id)
    types = state.get('costTypes') or []
    merged = list(DEFAULT_COST_TYPES)
    for t in types:
        if t and t not in merged:
            merged.append(t)
    return merged


def get_budget_cost_codes(BudgetProjectState, project_id):
    from budget_persistence import get_budget_state
    _, state = get_budget_state(BudgetProjectState, project_id)
    lines = state.get('budgetLines') or []
    custom = state.get('customCostCodes') or []
    codes = []
    seen = set()
    for line in lines:
        code = line.get('cost_code')
        if code and code not in seen:
            seen.add(code)
            codes.append({
                'code': code,
                'description': line.get('description', ''),
                'cost_type': line.get('cost_type', ''),
                'original_budget': line.get('original_budget', 0),
                'approved_changes': line.get('approved_changes', 0),
                'pending': line.get('pending', 0),
            })
    for item in custom:
        code = item.get('code')
        if code and code not in seen:
            seen.add(code)
            codes.append({
                'code': code,
                'description': item.get('description', ''),
                'cost_type': item.get('cost_type', ''),
                'original_budget': 0,
                'approved_changes': 0,
                'pending': 0,
            })
    return codes


def user_can_act_on_ball_in_court(user, role):
    if not user or not role:
        return False
    if user.role in ('Admin', 'Developer'):
        return True
    allowed = ROLE_APPROVERS.get(role, (role,))
    return user.role in allowed


def get_next_approval_step(current_status, co=None):
    chain = co_approval_chain(co) if co else APPROVAL_CHAIN
    for step in chain:
        if step['from_status'] == current_status:
            return step
    return None


def get_next_pco_approval_step(current_status):
    for step in PCO_APPROVAL_CHAIN:
        if step['from_status'] == current_status:
            return step
    return None


def _resolve_co_next_status(co, default_next, ChangeOrder=None, ChangeOrderAllocation=None):
    """Skip Owner approval for owner COs below threshold (per-transaction + monthly cumulative)."""
    if is_subcontract_co(co):
        return default_next
    from financial_security import (
        authoritative_co_amount,
        cumulative_approved_owner_co_amount,
        effective_threshold_amount,
        OWNER_THRESHOLD,
    )
    base = authoritative_co_amount(co, ChangeOrderAllocation=ChangeOrderAllocation)
    cumulative = cumulative_approved_owner_co_amount(
        co.project_id, ChangeOrder, exclude_co_id=getattr(co, 'id', None),
    ) if ChangeOrder and co.project_id else 0.0
    amount = effective_threshold_amount(base, cumulative)
    if default_next == 'Pending Owner' and amount < OWNER_THRESHOLD:
        return 'Pending Accounting'
    if default_next == 'Pending Accounting' and amount < OWNER_THRESHOLD:
        return 'Approved'
    return default_next


def set_pco_ball_in_court(pco, status=None):
    status = status or pco.status
    pco.ball_in_court_role = PCO_BALL_IN_COURT_MAP.get(status, pco.ball_in_court_role)


def set_ball_in_court(co, status=None):
    status = status or co.status
    court_map = co_ball_in_court_map(co)
    co.ball_in_court_role = court_map.get(status, co.ball_in_court_role)


def notify_ball_in_court(project_id, co, User, title=None, description=None):
    role = co.ball_in_court_role
    if not role:
        return
    try:
        import case_workflow as cw
        action_url = f'/change-orders?project_id={project_id}&open=1&respond=1&co_id={co.id}'
        title = title or f'{co.number} — ball in court: {role}'
        description = description or (co.description or getattr(co, 'title', None) or '')
        users = User.query.filter_by(status='Active').all()
        targets = [u for u in users if user_can_act_on_ball_in_court(u, role)]
        if not targets:
            targets = cw.find_assignees(project_id, 'Change Orders')
        for u in targets:
            from email_notifications import notify_user_workflow
            notify_user_workflow(
                u,
                title=title,
                description=description,
                action_url=action_url,
                project_id=project_id,
                module='Change Orders',
            )
    except Exception:
        pass


def append_approval_history(co, action, user, comment='', status_from='', status_to=''):
    history = _parse_json(getattr(co, 'approval_history_json', None), [])
    name = ''
    if user:
        name = f'{getattr(user, "first_name", "")} {getattr(user, "last_name", "")}'.strip() or getattr(user, 'email', '')
    history.append({
        'action': action,
        'status_from': status_from,
        'status_to': status_to,
        'role': getattr(user, 'role', None),
        'user_name': name,
        'comment': (comment or '').strip(),
        'at': datetime.utcnow().isoformat() + 'Z',
    })
    co.approval_history_json = json.dumps(history)
    if comment and action == 'reject':
        prefix = f'[{datetime.utcnow().strftime("%Y-%m-%d")} Rejected] {comment}'
        co.notes = f'{prefix}\n{co.notes}'.strip() if co.notes else prefix


def co_workflow_action(co, action, user, User, allocations=None, ChangeOrder=None, ChangeOrderAllocation=None):
    action = (action or '').lower()
    sub_kind = getattr(co, 'sub_co_kind', None)
    if action in ('submit', 'approve'):
        validate_allocations(
            allocations or [],
            require_rows=True,
            require_amount=True,
            sub_co_kind=sub_kind,
        )
        if is_subcontract_co(co) and (sub_kind or '') == 'Contract Add':
            if not (getattr(co, 'linked_commitment_ref', None) or '').strip():
                raise ValueError('Contract add subcontractor change orders require a linked subcontract commitment.')
        if is_subcontract_co(co) and (sub_kind or '') == 'Owner CO Backcharge':
            if not getattr(co, 'linked_owner_co_id', None):
                raise ValueError('Owner CO backcharge subcontractor change orders require a linked owner change order.')
    if action == 'submit':
        if co.status not in ('Draft',):
            raise ValueError('Only draft change orders can be submitted')
        if not user_can_act_on_ball_in_court(user, 'Creator') and user.role not in (
            'Project Manager', 'Admin', 'Developer', 'Company User',
        ):
            raise ValueError('Only the creator or Project Manager can submit this change order')
        co.status = 'Submitted'
        co.approval_stage = 0
        set_ball_in_court(co)
        return co.status, False

    if action == 'reject':
        from financial_security import workflow_reject_authorized
        workflow_reject_authorized(user, co.ball_in_court_role, user_can_act_fn=user_can_act_on_ball_in_court)
        co.status = 'Rejected'
        co.ball_in_court_role = None
        return co.status, False

    if action == 'approve':
        role = co.ball_in_court_role
        if not user_can_act_on_ball_in_court(user, role):
            raise ValueError(f'Your role cannot approve while ball is with {role}')
        step = get_next_approval_step(co.status, co)
        if not step:
            raise ValueError('No approval step for current status')
        next_status = _resolve_co_next_status(
            co, step['next_status'],
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
        )
        co.status = next_status
        co.approval_stage = (co.approval_stage or 0) + 1
        set_ball_in_court(co)
        if next_status == 'Approved':
            co.ball_in_court_role = None
            return co.status, True
        return co.status, False

    raise ValueError('action must be submit, approve, or reject')


def attachment_record(filename, original_name, uploaded_by_id=None):
    return {
        'filename': filename,
        'original_name': original_name,
        'uploaded_at': datetime.utcnow().isoformat() + 'Z',
        'uploaded_by_id': uploaded_by_id,
    }


def append_attachment(co, record):
    items = _parse_json(getattr(co, 'attachments_json', None), [])
    items.append(record)
    co.attachments_json = json.dumps(items)
    return items


def append_pco_attachment(pco, record):
    items = _parse_json(getattr(pco, 'attachments_json', None), [])
    items.append(record)
    pco.attachments_json = json.dumps(items)
    return items


def pco_workflow_action(pco, action, user, User, allocations=None):
    action = (action or '').lower()
    if action in ('submit', 'approve'):
        validate_allocations(allocations or [], require_rows=False, require_amount=False)
    if action == 'submit':
        if pco.status != 'Open':
            raise ValueError('Only open PCOs can be submitted')
        pco.status = 'Pricing'
        set_pco_ball_in_court(pco)
        return pco.status, False
    if action == 'reject':
        from financial_security import workflow_reject_authorized
        workflow_reject_authorized(user, pco.ball_in_court_role or 'Project Manager', user_can_act_fn=user_can_act_on_ball_in_court)
        pco.status = 'Void'
        pco.ball_in_court_role = None
        return pco.status, False
    if action == 'approve':
        role = pco.ball_in_court_role or 'Project Manager'
        if not user_can_act_on_ball_in_court(user, role):
            raise ValueError(f'Your role cannot approve while ball is with {role}')
        step = get_next_pco_approval_step(pco.status)
        if not step:
            raise ValueError('No approval step for current PCO status')
        pco.status = step['next_status']
        set_pco_ball_in_court(pco)
        if pco.status == 'Approved for CO':
            return pco.status, True
        return pco.status, False
    raise ValueError('action must be submit, approve, or reject')


def process_pco_workflow(pco, action, user, User, body, *, SageSyncEvent, Project, db):
    """Unified PCO workflow with Sage queue and notifications."""
    body = body or {}
    action = (action or '').lower()
    comments = (body.get('comments') or body.get('comment') or '').strip()
    if action == 'reject' and not comments:
        raise ValueError('Rejection requires a comment.')
    old_status = pco.status
    allocs = body.get('allocations') or []
    new_status, final = pco_workflow_action(pco, action, user, User, allocs)
    if action == 'submit' or (action == 'approve' and new_status == 'Pending Review'):
        from sage_service import create_and_process_sage_event
        create_and_process_sage_event(
            SageSyncEvent, Project, db, pco.project_id,
            'PCOSubmitted',
            message=f'PCO {pco.number} — {new_status}',
            payload={'pco_id': pco.id, 'estimated_amount': pco.estimated_amount, 'idempotency_key': f'pco-{pco.id}-submit'},
            user_id=user.id,
        )
    if final:
        from sage_service import create_and_process_sage_event
        create_and_process_sage_event(
            SageSyncEvent, Project, db, pco.project_id,
            'PCOSubmitted',
            message=f'PCO {pco.number} approved for CO',
            payload={'pco_id': pco.id, 'estimated_amount': pco.estimated_amount, 'approved_for_co': True, 'idempotency_key': f'pco-{pco.id}-approved'},
            user_id=user.id,
        )
    if pco.ball_in_court_role and action in ('submit', 'approve') and not final:
        _notify_pco_ball(pco, User)
    return {'new_status': new_status, 'final_approved': final, 'old_status': old_status}


def _notify_pco_ball(pco, User):
    try:
        from email_notifications import notify_role_workflow
        action_url = f'/change-orders?project_id={pco.project_id}&tab=pcos'
        notify_role_workflow(
            User,
            pco.ball_in_court_role,
            title=f'PCO {pco.number} — review required',
            description=pco.description or pco.title or '',
            action_url=action_url,
            project_id=pco.project_id,
            module='Change Orders',
            can_act_fn=user_can_act_on_ball_in_court,
        )
    except Exception:
        pass


def delete_change_order(
    co,
    db,
    AllocationModel,
    RevisionModel,
    PotentialChangeOrder,
    *,
    force=False,
):
    if co.status == 'Approved' and not force:
        raise ValueError('Approved change orders require force delete for testing.')
    pcos = PotentialChangeOrder.query.filter_by(change_order_id=co.id).all()
    for pco in pcos:
        pco.change_order_id = None
        if pco.status == 'Promoted':
            pco.status = 'Approved for CO'
    AllocationModel.query.filter_by(change_order_id=co.id).delete()
    RevisionModel.query.filter_by(change_order_id=co.id).delete()
    db.session.delete(co)


def compute_co_amount_from_allocations(allocations, sub_co_kind=None):
    rows = normalize_allocation_rows(allocations)
    if not rows:
        return 0.0
    kind = (sub_co_kind or '').strip()
    if kind == 'Budget Transfer':
        return round(sum(max(0.0, float(r.get('amount') or 0)) for r in rows), 2)
    return round(sum(float(r.get('amount') or 0) for r in rows), 2)


def _normalize_cost_code(code):
    return str(code or '').replace(' ', '').replace('-', '').upper()


def _commitment_matches_sub_alloc(commitment, alloc, CommitmentAllocation):
    if commitment.commitment_type != 'Subcontract':
        return False
    code = _normalize_cost_code(getattr(alloc, 'cost_code', None) if not isinstance(alloc, dict) else alloc.get('cost_code'))
    if not code:
        return False
    rows = CommitmentAllocation.query.filter_by(commitment_id=commitment.id).all()
    for row in rows:
        if _normalize_cost_code(row.cost_code) == code:
            return True
    return False


def auto_create_sub_cos_from_owner_co(
    owner_co,
    allocations,
    ChangeOrder,
    ChangeOrderAllocation,
    Commitment,
    CommitmentAllocation,
    db,
    generate_number_fn,
    user_id,
):
    """Create draft subcontractor COs when an owner CO is approved with subcontract allocations."""
    if is_subcontract_co(owner_co):
        return []
    if owner_co.status != 'Approved':
        return []

    existing = ChangeOrder.query.filter_by(
        project_id=owner_co.project_id,
        linked_owner_co_id=owner_co.id,
        auto_generated=True,
    ).count()
    if existing:
        return []

    sub_allocs = []
    for alloc in allocations or []:
        ctype = (getattr(alloc, 'cost_type', None) if not isinstance(alloc, dict) else alloc.get('cost_type') or '').strip()
        if ctype.lower() != 'subcontract':
            continue
        amt = float(getattr(alloc, 'amount', 0) if not isinstance(alloc, dict) else alloc.get('amount') or 0)
        if not amt:
            continue
        sub_allocs.append(alloc)
    if not sub_allocs:
        return []

    commitments = Commitment.query.filter_by(project_id=owner_co.project_id).filter(
        Commitment.commitment_type == 'Subcontract'
    ).all()
    if not commitments:
        return []

    linked_ref = (getattr(owner_co, 'linked_commitment_ref', None) or '').strip()
    if linked_ref:
        commitments = [c for c in commitments if (c.number or '').strip() == linked_ref] or commitments

    buckets = {}
    for com in commitments:
        for alloc in sub_allocs:
            if _commitment_matches_sub_alloc(com, alloc, CommitmentAllocation):
                key = com.id
                if key not in buckets:
                    buckets[key] = {'commitment': com, 'allocations': []}
                payload = {
                    'cost_code': getattr(alloc, 'cost_code', None) if not isinstance(alloc, dict) else alloc.get('cost_code'),
                    'cost_type': 'Subcontract',
                    'amount': float(getattr(alloc, 'amount', 0) if not isinstance(alloc, dict) else alloc.get('amount') or 0),
                    'description': getattr(alloc, 'description', '') if not isinstance(alloc, dict) else alloc.get('description', ''),
                }
                buckets[key]['allocations'].append(payload)

    created = []
    for bucket in buckets.values():
        com = bucket['commitment']
        allocs = bucket['allocations']
        total = compute_co_amount_from_allocations(allocs, 'Owner CO Backcharge')
        if total <= 0:
            continue
        sco = ChangeOrder(
            project_id=owner_co.project_id,
            number=generate_number_fn('SCO', ChangeOrder, doc_type='sub_change_order', project_id=owner_co.project_id),
            title=f'{owner_co.number} — {com.company_name or com.number}',
            description=f'Auto-generated subcontractor change order from approved owner CO {owner_co.number}',
            amount=total,
            reason=owner_co.reason,
            schedule_impact=owner_co.schedule_impact,
            schedule_impact_days=owner_co.schedule_impact_days or 0,
            status='Draft',
            date=datetime.utcnow().date(),
            requested_by=owner_co.requested_by,
            priority=owner_co.priority,
            notes=f'Auto-created from owner CO {owner_co.number}. Review allocations and submit when ready.',
            company_name=com.company_name,
            company_id=com.company_id,
            contract_type='Subcontract',
            linked_owner_co_id=owner_co.id,
            linked_commitment_ref=com.number,
            sub_co_kind='Owner CO Backcharge',
            auto_generated=True,
            ball_in_court_role='Creator',
            created_by_id=user_id,
        )
        db.session.add(sco)
        db.session.flush()
        for item in allocs:
            db.session.add(ChangeOrderAllocation(
                change_order_id=sco.id,
                cost_code=item.get('cost_code'),
                cost_type=item.get('cost_type') or 'Subcontract',
                amount=float(item.get('amount') or 0),
                description=item.get('description') or '',
            ))
        created.append(sco)
    if created:
        db.session.flush()
    return created


def run_change_order_accounting_sync(
    co,
    old_status,
    new_status,
    user_id,
    *,
    ChangeOrder,
    ChangeOrderAllocation,
    PayAppProjectState,
    ScheduleData,
    Project,
    BudgetProjectState,
    db,
    Commitment=None,
    CommitmentAllocation=None,
    SageSyncEvent=None,
    queue_sage_event=True,
):
    """Reconcile change order amounts across budget, SOV, and commitments."""
    result = {'sync_result': None, 'budget_sync_result': None, 'errors': []}

    if new_status == 'Approved' and old_status != 'Approved':
        co.approved_at = co.approved_at or datetime.utcnow()
        try:
            from pay_app_persistence import apply_schedule_impact
            apply_schedule_impact(
                ScheduleData, Project, db, co.project_id,
                co.schedule_impact, co.number, co.description,
            )
        except Exception as exc:
            result['errors'].append({'target': 'schedule', 'error': str(exc)})

    if Commitment is None or CommitmentAllocation is None:
        return result

    try:
        from accounting_reconcile import reconcile_project_accounting
        recon = reconcile_project_accounting(
            co.project_id,
            user_id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            BudgetProjectState=BudgetProjectState,
            PayAppProjectState=PayAppProjectState,
            db=db,
        )
        result['sync_result'] = recon.get('sync_result')
        result['budget_sync_result'] = recon.get('budget_sync_result')
        if new_status == 'Approved':
            co.sov_synced_at = co.sov_synced_at or datetime.utcnow()
            co.sage_sync_status = 'sov_synced'
            if is_subcontract_co(co):
                try:
                    from change_event_persistence import compute_billing_variance_for_sub_cos, update_sco_retainage_and_billing
                    update_sco_retainage_and_billing(
                        co, PayAppProjectState, Commitment, ChangeOrderAllocation, db,
                    )
                    rows = compute_billing_variance_for_sub_cos([co], PayAppProjectState, co.project_id)
                    if rows:
                        co.billed_amount = rows[0].get('billed', 0)
                        co.billing_variance = rows[0].get('variance', 0)
                except Exception:
                    pass
                if Commitment is not None and getattr(co, 'linked_commitment_ref', None):
                    com = Commitment.query.filter_by(project_id=co.project_id, number=co.linked_commitment_ref).first()
                    if com and com.retainage_percent:
                        allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
                        for a in allocs:
                            if getattr(a, 'retainage_percent', None) is None:
                                a.retainage_percent = float(com.retainage_percent or 0)
            if queue_sage_event and SageSyncEvent is not None and old_status != 'Approved':
                from sage_service import create_and_process_sage_event
                if is_subcontract_co(co):
                    com_type = 'Subcontract'
                    if Commitment is not None and getattr(co, 'linked_commitment_ref', None):
                        com = Commitment.query.filter_by(
                            project_id=co.project_id,
                            number=co.linked_commitment_ref,
                        ).first()
                        if com:
                            com_type = com.commitment_type or 'Subcontract'
                    create_and_process_sage_event(
                        SageSyncEvent,
                        Project,
                        db,
                        co.project_id,
                        'CommitmentChangeOrderApproved',
                        message=f'Subcontractor Change Order {co.number} approved — accounting reconciled',
                        payload={
                            'change_order_id': co.id,
                            'amount': co.amount,
                            'commitment_type': com_type,
                            'linked_commitment_ref': getattr(co, 'linked_commitment_ref', None),
                            'sub_co_kind': getattr(co, 'sub_co_kind', None),
                            'sync': result['sync_result'],
                        },
                        user_id=user_id,
                        Commitment=Commitment,
                    )
                else:
                    create_and_process_sage_event(
                        SageSyncEvent,
                        Project,
                        db,
                        co.project_id,
                        'ChangeOrderApproved',
                        message=f'Change Order {co.number} approved — accounting reconciled',
                        payload={'change_order_id': co.id, 'amount': co.amount, 'sync': result['sync_result']},
                        user_id=user_id,
                    )
    except Exception as exc:
        co.sage_sync_status = f'sync_error:{str(exc)[:120]}'
        result['sync_result'] = {'error': str(exc)}
        result['errors'].append({'target': 'reconcile', 'error': str(exc)})

    return result


def co_approvable_statuses(co):
    """Statuses where the current ball-in-court role may approve or reject."""
    if is_subcontract_co(co):
        return ('Submitted', 'Pending Accounting')
    return ('Submitted', 'Pending Architect', 'Pending Owner', 'Pending Accounting')


def process_change_order_workflow(
    co,
    action,
    user,
    User,
    body,
    *,
    ChangeOrder,
    ChangeOrderAllocation,
    PayAppProjectState,
    ScheduleData,
    Project,
    BudgetProjectState,
    db,
    Commitment,
    CommitmentAllocation,
    SageSyncEvent,
    generate_next_number_fn=None,
    developer_unlock_bypass=False,
):
    """
    Unified change order workflow — single path for API route and approval responder.
    Mirrors Procore-style sequential approval with accounting review before Sage export.
    """
    body = body or {}
    action = (action or '').lower()
    if action not in ('submit', 'approve', 'reject'):
        raise ValueError('action must be submit, approve, or reject')

    comments = (body.get('comments') or body.get('comment') or '').strip()
    if action == 'reject' and not comments:
        raise ValueError('Rejection requires a comment.')

    old_status = co.status
    old_ball_role = co.ball_in_court_role

    if getattr(co, 'executed_locked', False) and action in ('submit', 'approve') and not developer_unlock_bypass:
        raise ValueError('This change order is executed and locked under owner e-signature.')

    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    alloc_payload = [{
        'cost_code': a.cost_code,
        'cost_type': getattr(a, 'cost_type', None),
        'amount': a.amount,
        'description': getattr(a, 'description', ''),
    } for a in allocs]

    if action == 'approve' and old_ball_role in ('Owner', 'Architect'):
        if not body.get('signature_attestation'):
            raise ValueError('Electronic signature attestation is required for Owner and Architect approvals.')
        from user_signature_persistence import verify_user_signature_attestation
        verify_user_signature_attestation(user, (body.get('signature_hash') or '').strip())

    new_status, final_approved = co_workflow_action(
        co, action, user, User, alloc_payload,
        ChangeOrder=ChangeOrder,
        ChangeOrderAllocation=ChangeOrderAllocation,
    )
    append_approval_history(co, action, user, comments, old_status, new_status)

    if action == 'approve' and old_ball_role in ('Owner', 'Architect'):
        from user_signature_persistence import append_co_approval_signature
        append_co_approval_signature(co, user, old_ball_role, comments, action='approve')

    try:
        from case_workflow import ApprovalRequest, decide_approval
        pending = ApprovalRequest.query.filter_by(
            entity_type='ChangeOrder',
            entity_id=str(co.id),
            status='pending',
        ).order_by(ApprovalRequest.created_at.desc()).first()
        if pending and action in ('approve', 'reject'):
            decide_approval(pending.id, action, comments)
    except Exception:
        pass

    if action == 'submit' and not co.submitted_at:
        co.submitted_at = datetime.utcnow()
        try:
            from case_workflow import create_approval
            create_approval(
                project_id=co.project_id,
                module='Change Orders',
                entity_type='ChangeOrder',
                entity_id=co.id,
                title=f'Change Order {co.number} submitted — {co.ball_in_court_role} review',
                description=co.description or '',
                action_url=f'/change-orders?project_id={co.project_id}&open=1&respond=1&co_id={co.id}',
                payload={'amount': co.amount, 'status': new_status, 'ball_in_court': co.ball_in_court_role},
                assignee_role=co.ball_in_court_role,
            )
        except Exception:
            pass
        from sage_service import create_and_process_sage_event
        if is_subcontract_co(co):
            com_type = 'Subcontract'
            if getattr(co, 'linked_commitment_ref', None):
                com = Commitment.query.filter_by(project_id=co.project_id, number=co.linked_commitment_ref).first()
                if com:
                    com_type = com.commitment_type or 'Subcontract'
            create_and_process_sage_event(
                SageSyncEvent, Project, db, co.project_id,
                'CommitmentChangeOrderSubmitted',
                message=f'{co.number} submitted — ball with {co.ball_in_court_role}',
                payload={
                    'change_order_id': co.id,
                    'amount': co.amount,
                    'commitment_type': com_type,
                    'linked_commitment_ref': getattr(co, 'linked_commitment_ref', None),
                    'sub_co_kind': getattr(co, 'sub_co_kind', None),
                },
                user_id=user.id,
                Commitment=Commitment,
            )
        else:
            create_and_process_sage_event(
                SageSyncEvent, Project, db, co.project_id,
                'ChangeOrderSubmitted',
                message=f'{co.number} submitted — ball with {co.ball_in_court_role}',
                payload={'change_order_id': co.id, 'amount': co.amount},
                user_id=user.id,
            )

    sync_result = None
    budget_sync_result = None

    if action == 'submit' and new_status == 'Submitted':
        accounting = run_change_order_accounting_sync(
            co, old_status, new_status, user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            PayAppProjectState=PayAppProjectState,
            ScheduleData=ScheduleData,
            Project=Project,
            BudgetProjectState=BudgetProjectState,
            db=db,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            SageSyncEvent=SageSyncEvent,
            queue_sage_event=False,
        )
        budget_sync_result = accounting.get('budget_sync_result')

    if final_approved:
        co.approved_by_id = user.id
        accounting = run_change_order_accounting_sync(
            co, old_status, 'Approved', user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            PayAppProjectState=PayAppProjectState,
            ScheduleData=ScheduleData,
            Project=Project,
            BudgetProjectState=BudgetProjectState,
            db=db,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            SageSyncEvent=SageSyncEvent,
        )
        sync_result = accounting.get('sync_result')
        budget_sync_result = accounting.get('budget_sync_result') or budget_sync_result
        if not is_subcontract_co(co) and generate_next_number_fn:
            auto_create_sub_cos_from_owner_co(
                co,
                allocs,
                ChangeOrder,
                ChangeOrderAllocation,
                Commitment,
                CommitmentAllocation,
                db,
                generate_next_number_fn,
                user.id,
            )
    elif action in ('submit', 'approve') and co.ball_in_court_role:
        notify_ball_in_court(
            co.project_id, co, User,
            title=f'{co.number} — action required ({co.ball_in_court_role})',
            description=f'Status: {new_status}. {co.description or ""}',
        )
        if action == 'approve' and not final_approved:
            try:
                from case_workflow import create_approval
                create_approval(
                    project_id=co.project_id,
                    module='Change Orders',
                    entity_type='ChangeOrder',
                    entity_id=co.id,
                    title=f'Change Order {co.number} — {co.ball_in_court_role} approval',
                    description=co.description or '',
                    action_url=f'/change-orders?project_id={co.project_id}&open=1&respond=1&co_id={co.id}',
                    payload={'amount': co.amount, 'status': new_status},
                    assignee_role=co.ball_in_court_role,
                )
            except Exception:
                pass

    if action == 'reject':
        accounting = run_change_order_accounting_sync(
            co, old_status, 'Rejected', user.id,
            ChangeOrder=ChangeOrder,
            ChangeOrderAllocation=ChangeOrderAllocation,
            PayAppProjectState=PayAppProjectState,
            ScheduleData=ScheduleData,
            Project=Project,
            BudgetProjectState=BudgetProjectState,
            db=db,
            Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation,
            SageSyncEvent=SageSyncEvent,
            queue_sage_event=False,
        )
        budget_sync_result = accounting.get('budget_sync_result') or budget_sync_result
        action_url = f'/change-orders?project_id={co.project_id}&open=1&respond=1&co_id={co.id}'
        if co.created_by_id:
            import case_workflow as cw
            cw.notify_user(
                co.created_by_id,
                f'{co.number} — rejected',
                comments or 'Change order was rejected.',
                action_url,
            )
            cw.create_internal_message(
                co.created_by_id,
                folder='team',
                msg_type='message',
                subject=f'{co.number} — rejected',
                preview=comments or 'rejected',
                body=f'<p>{comments or "Change order was rejected."}</p>',
                project_id=co.project_id,
                from_label=getattr(user, 'full_name', None) or 'Change Orders',
                from_user_id=user.id,
                module='Change Orders',
                action_url=action_url,
                requires_action=False,
            )
    elif final_approved and co.created_by_id:
        action_url = f'/change-orders?project_id={co.project_id}&open=1&respond=1&co_id={co.id}'
        import case_workflow as cw
        cw.notify_user(
            co.created_by_id,
            f'{co.number} — approved',
            comments or 'Change order was approved.',
            action_url,
        )
        cw.create_internal_message(
            co.created_by_id,
            folder='team',
            msg_type='message',
            subject=f'{co.number} — approved',
            preview=comments or 'approved',
            body=f'<p>{comments or "Change order was approved."}</p>',
            project_id=co.project_id,
            from_label=getattr(user, 'full_name', None) or 'Change Orders',
            from_user_id=user.id,
            module='Change Orders',
            action_url=action_url,
            requires_action=False,
        )

    auto_sub_cos = []
    if final_approved and not is_subcontract_co(co):
        auto_sub_cos = [
            {'id': c.id, 'number': c.number, 'company_name': c.company_name}
            for c in ChangeOrder.query.filter_by(
                project_id=co.project_id, linked_owner_co_id=co.id, auto_generated=True,
            ).all()
        ]

    return {
        'new_status': new_status,
        'final_approved': final_approved,
        'sync_result': sync_result,
        'budget_sync_result': budget_sync_result,
        'auto_sub_change_orders': auto_sub_cos,
        'alloc_payload': alloc_payload,
    }

