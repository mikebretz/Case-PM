"""Change Events, RFQs, CORs, CPCO extensions, and ERP accounting queue helpers."""
from __future__ import annotations

import json
from datetime import datetime

CHANGE_EVENT_STATUSES = ('Open', 'Pricing', 'Pending Review', 'Approved', 'Closed', 'Void')
RFQ_STATUSES = ('Draft', 'Sent', 'Quoted', 'Accepted', 'Rejected', 'Void')
COR_STATUSES = ('Draft', 'Submitted', 'Under Review', 'Pending Owner', 'Pending Architect', 'Pending Accounting', 'Approved', 'Rejected', 'Void', 'Promoted')
COR_BALL_IN_COURT = {
    'Draft': 'Creator',
    'Submitted': 'Project Manager',
    'Under Review': 'Architect',
    'Pending Owner': 'Owner',
    'Pending Architect': 'Architect',
    'Pending Accounting': 'Contractor Accounting',
    'Approved': None,
    'Rejected': None,
    'Void': None,
    'Promoted': None,
}
COR_APPROVAL_CHAIN = (
    {'from_status': 'Submitted', 'role': 'Project Manager', 'next_status': 'Under Review'},
    {'from_status': 'Under Review', 'role': 'Architect', 'next_status': 'Pending Owner'},
    {'from_status': 'Pending Owner', 'role': 'Owner', 'next_status': 'Pending Accounting'},
    {'from_status': 'Pending Accounting', 'role': 'Contractor Accounting', 'next_status': 'Approved'},
)


CHANGE_EVENT_BALL = {
    'Open': 'Project Manager',
    'Pricing': 'Project Manager',
    'Pending Review': 'Project Manager',
    'Approved': None,
    'Closed': None,
    'Void': None,
}
RFQ_BALL = {
    'Draft': 'Creator',
    'Sent': 'Subcontractor',
    'Quoted': 'Project Manager',
    'Accepted': None,
    'Rejected': None,
    'Void': None,
}
CHANGE_EVENT_APPROVAL_CHAIN = (
    {'from_status': 'Open', 'role': 'Project Manager', 'next_status': 'Pricing'},
    {'from_status': 'Pricing', 'role': 'Project Manager', 'next_status': 'Pending Review'},
    {'from_status': 'Pending Review', 'role': 'Project Manager', 'next_status': 'Approved'},
)
CPCO_CONTRACT_TYPE = 'Subcontract'
CE_LINE_STATUSES = ('Open', 'RFQ Draft', 'RFQ Sent', 'Quoted', 'In CPCO', 'In CCO', 'Void')


def ensure_change_event_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if 'change_event' not in tables:
        db.session.execute(text('''
            CREATE TABLE change_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                number VARCHAR(30),
                title VARCHAR(200),
                description TEXT,
                status VARCHAR(30) DEFAULT 'Open',
                reason VARCHAR(200),
                priority VARCHAR(20) DEFAULT 'Medium',
                schedule_impact_days INTEGER DEFAULT 0,
                rom_amount FLOAT DEFAULT 0,
                linked_rfi_id INTEGER,
                drawing_revision VARCHAR(80),
                drawing_sheet_id VARCHAR(80),
                contingency_release_amount FLOAT DEFAULT 0,
                ball_in_court_role VARCHAR(80),
                notes TEXT,
                created_by_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
        '''))
        db.session.commit()

    if 'subcontractor_rfq' not in tables:
        db.session.execute(text('''
            CREATE TABLE subcontractor_rfq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                change_event_id INTEGER,
                number VARCHAR(30),
                title VARCHAR(200),
                description TEXT,
                status VARCHAR(30) DEFAULT 'Draft',
                company_name VARCHAR(200),
                company_id VARCHAR(64),
                linked_commitment_ref VARCHAR(80),
                due_date DATE,
                quoted_amount FLOAT DEFAULT 0,
                quoted_at DATETIME,
                quoted_by VARCHAR(150),
                quote_notes TEXT,
                linked_pco_id INTEGER,
                linked_cpco_id INTEGER,
                linked_sco_id INTEGER,
                ball_in_court_role VARCHAR(80),
                created_by_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
        '''))
        db.session.commit()

    if 'rfq_allocation' not in tables:
        db.session.execute(text('''
            CREATE TABLE rfq_allocation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfq_id INTEGER NOT NULL,
                cost_code VARCHAR(30),
                cost_type VARCHAR(80),
                amount FLOAT DEFAULT 0,
                quoted_amount FLOAT DEFAULT 0,
                description VARCHAR(200),
                sov_line_id VARCHAR(64),
                tax_group VARCHAR(40)
            )
        '''))
        db.session.commit()

    if 'change_order_request' not in tables:
        db.session.execute(text('''
            CREATE TABLE change_order_request (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                change_event_id INTEGER,
                number VARCHAR(30),
                title VARCHAR(200),
                description TEXT,
                amount FLOAT DEFAULT 0,
                status VARCHAR(30) DEFAULT 'Draft',
                reason VARCHAR(200),
                priority VARCHAR(20) DEFAULT 'Medium',
                schedule_impact_days INTEGER DEFAULT 0,
                linked_pco_id INTEGER,
                change_order_id INTEGER,
                drawing_revision VARCHAR(80),
                ball_in_court_role VARCHAR(80),
                approval_stage INTEGER DEFAULT 0,
                notes TEXT,
                created_by_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
        '''))
        db.session.commit()

    if 'cor_allocation' not in tables:
        db.session.execute(text('''
            CREATE TABLE cor_allocation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cor_id INTEGER NOT NULL,
                cost_code VARCHAR(30),
                cost_type VARCHAR(80),
                amount FLOAT DEFAULT 0,
                description VARCHAR(200),
                sov_line_id VARCHAR(64),
                tax_group VARCHAR(40)
            )
        '''))
        db.session.commit()

    if 'change_event_line_item' not in tables:
        db.session.execute(text('''
            CREATE TABLE change_event_line_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_event_id INTEGER NOT NULL,
                sort_order INTEGER DEFAULT 0,
                description VARCHAR(300),
                cost_code VARCHAR(30),
                cost_type VARCHAR(80) DEFAULT 'Subcontract',
                amount FLOAT DEFAULT 0,
                quoted_amount FLOAT DEFAULT 0,
                company_name VARCHAR(200),
                company_id VARCHAR(64),
                linked_commitment_ref VARCHAR(80),
                sov_line_id VARCHAR(64),
                tax_group VARCHAR(40),
                status VARCHAR(30) DEFAULT 'Open',
                linked_rfq_id INTEGER,
                linked_cpco_id INTEGER,
                linked_sco_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME
            )
        '''))
        db.session.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_change_event_line_item_ce ON change_event_line_item (change_event_id)'
        ))
        db.session.commit()

  # Extend existing tables
    _add_columns(inspector, db, 'potential_change_order', {
        'change_event_id': 'INTEGER',
        'contract_type': "VARCHAR(40) DEFAULT 'Owner'",
        'source_rfq_id': 'INTEGER',
        'linked_cor_id': 'INTEGER',
        'linked_drawing_revision': 'VARCHAR(80)',
    })
    _add_columns(inspector, db, 'change_order', {
        'change_event_id': 'INTEGER',
        'source_rfq_id': 'INTEGER',
        'linked_cor_id': 'INTEGER',
        'linked_drawing_revision': 'VARCHAR(80)',
        'source_cpco_id': 'INTEGER',
        'billed_amount': 'FLOAT DEFAULT 0',
        'billing_variance': 'FLOAT DEFAULT 0',
    })
    _add_columns(inspector, db, 'change_order_allocation', {
        'sov_line_id': 'VARCHAR(64)',
        'tax_group': 'VARCHAR(40)',
        'retainage_percent': 'FLOAT',
    })
    _add_columns(inspector, db, 'pco_allocation', {
        'sov_line_id': 'VARCHAR(64)',
        'tax_group': 'VARCHAR(40)',
        'change_event_line_item_id': 'INTEGER',
    })
    _add_columns(inspector, db, 'change_order_allocation', {
        'change_event_line_item_id': 'INTEGER',
    })
    _add_columns(inspector, db, 'sage_sync_event', {
        'accounting_status': "VARCHAR(30) DEFAULT 'pending_review'",
        'accounting_reviewed_by_id': 'INTEGER',
        'accounting_reviewed_at': 'DATETIME',
        'accounting_notes': 'TEXT',
    })


def _add_columns(inspector, db, table, additions):
    from sqlalchemy import text
    if table not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns(table)}
    for name, col_type in additions.items():
        if name not in cols:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {col_type}'))
    db.session.commit()


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def change_event_to_dict(ce, rfqs=None, pcos=None, cors=None, line_items=None, cpcos=None, commitment_cos=None):
    return {
        'id': ce.id,
        'project_id': ce.project_id,
        'number': ce.number,
        'title': ce.title,
        'description': ce.description,
        'status': ce.status,
        'reason': ce.reason,
        'priority': ce.priority,
        'schedule_impact_days': ce.schedule_impact_days or 0,
        'rom_amount': ce.rom_amount or 0,
        'linked_rfi_id': getattr(ce, 'linked_rfi_id', None),
        'drawing_revision': getattr(ce, 'drawing_revision', None),
        'drawing_sheet_id': getattr(ce, 'drawing_sheet_id', None),
        'contingency_release_amount': float(getattr(ce, 'contingency_release_amount', 0) or 0),
        'ball_in_court_role': getattr(ce, 'ball_in_court_role', None),
        'notes': getattr(ce, 'notes', None),
        'rfqs': rfqs or [],
        'pcos': pcos or [],
        'cors': cors or [],
        'cpcos': cpcos or [],
        'commitment_cos': commitment_cos or [],
        'line_items': line_items or [],
        'created_at': ce.created_at.isoformat() if ce.created_at else None,
    }


def rfq_to_dict(rfq, allocations=None):
    allocs = allocations or []
    quoted = sum(float(getattr(a, 'quoted_amount', 0) or getattr(a, 'amount', 0) or 0) for a in allocs)
    if not quoted and rfq.quoted_amount:
        quoted = float(rfq.quoted_amount or 0)
    return {
        'id': rfq.id,
        'project_id': rfq.project_id,
        'change_event_id': getattr(rfq, 'change_event_id', None),
        'number': rfq.number,
        'title': rfq.title,
        'description': rfq.description,
        'status': rfq.status,
        'company_name': rfq.company_name,
        'company_id': rfq.company_id,
        'linked_commitment_ref': getattr(rfq, 'linked_commitment_ref', None),
        'due_date': rfq.due_date.isoformat() if getattr(rfq, 'due_date', None) else None,
        'quoted_amount': quoted or float(rfq.quoted_amount or 0),
        'quoted_at': rfq.quoted_at.isoformat() if getattr(rfq, 'quoted_at', None) else None,
        'quoted_by': getattr(rfq, 'quoted_by', None),
        'quote_notes': getattr(rfq, 'quote_notes', None),
        'linked_pco_id': getattr(rfq, 'linked_pco_id', None),
        'linked_cpco_id': getattr(rfq, 'linked_cpco_id', None),
        'linked_sco_id': getattr(rfq, 'linked_sco_id', None),
        'ball_in_court_role': getattr(rfq, 'ball_in_court_role', None),
        'allocations': [{
            'cost_code': a.cost_code,
            'cost_type': getattr(a, 'cost_type', None) or '',
            'amount': float(a.amount or 0),
            'quoted_amount': float(getattr(a, 'quoted_amount', 0) or 0),
            'description': getattr(a, 'description', '') or '',
            'sov_line_id': getattr(a, 'sov_line_id', None),
            'tax_group': getattr(a, 'tax_group', None),
        } for a in allocs],
        'created_at': rfq.created_at.isoformat() if rfq.created_at else None,
    }


def _sov_allocation_dict(alloc, *, pco_id=None, pco_number=None):
    """Serialize a PCO/CO allocation row for API (Schedule of Values line)."""
    if isinstance(alloc, dict):
        row = {
            'cost_code': alloc.get('cost_code'),
            'cost_type': alloc.get('cost_type') or '',
            'amount': float(alloc.get('amount') or 0),
            'description': alloc.get('description', '') or '',
            'sov_line_id': alloc.get('sov_line_id'),
            'tax_group': alloc.get('tax_group'),
            'change_event_line_item_id': alloc.get('change_event_line_item_id'),
        }
    else:
        row = {
            'cost_code': alloc.cost_code,
            'cost_type': getattr(alloc, 'cost_type', None) or '',
            'amount': float(alloc.amount or 0),
            'description': getattr(alloc, 'description', '') or '',
            'sov_line_id': getattr(alloc, 'sov_line_id', None),
            'tax_group': getattr(alloc, 'tax_group', None),
            'change_event_line_item_id': getattr(alloc, 'change_event_line_item_id', None),
        }
    if pco_id is not None:
        row['pco_id'] = pco_id
    if pco_number is not None:
        row['pco_number'] = pco_number
    return row


def get_cor_linked_pcos(cor, PotentialChangeOrder):
    """PCOs packaged in this COR (Procore: COR groups PCOs; SOV lives on PCOs)."""
    if not cor or not getattr(cor, 'id', None) or PotentialChangeOrder is None:
        return []
    rows = PotentialChangeOrder.query.filter_by(linked_cor_id=cor.id).order_by(
        PotentialChangeOrder.created_at.asc()
    ).all()
    if not rows and getattr(cor, 'linked_pco_id', None):
        legacy = PotentialChangeOrder.query.get(cor.linked_pco_id)
        if legacy and legacy not in rows:
            rows = [legacy]
    return rows


def cor_rollup_allocations(pcos, PCOAllocation):
    """Read-only SOV rollup from linked PCOs for COR display."""
    rollup = []
    for pco in pcos or []:
        allocs = PCOAllocation.query.filter_by(pco_id=pco.id).all()
        for alloc in allocs:
            rollup.append(_sov_allocation_dict(
                alloc, pco_id=pco.id, pco_number=getattr(pco, 'number', None),
            ))
    return rollup


def cor_amount_from_pcos(pcos):
    if not pcos:
        return 0.0
    return round(sum(float(getattr(p, 'estimated_amount', 0) or 0) for p in pcos), 2)


def link_pcos_to_cor(cor, pco_ids, PotentialChangeOrder, PCOAllocation, db):
    """Attach owner PCOs to a COR package. COR has no editable SOV — amounts roll up from PCOs."""
    ids = [int(i) for i in (pco_ids or [])]
    current = PotentialChangeOrder.query.filter_by(linked_cor_id=cor.id).all()
    keep = set(ids)
    for pco in current:
        if pco.id not in keep:
            pco.linked_cor_id = None
    for pid in ids:
        pco = PotentialChangeOrder.query.get(pid)
        if not pco:
            raise ValueError(f'PCO {pid} not found.')
        if int(pco.project_id) != int(cor.project_id):
            raise ValueError(f'PCO {pco.number} belongs to a different project.')
        if (getattr(pco, 'contract_type', None) or 'Owner') == 'Subcontract':
            raise ValueError(f'{pco.number} is a commitment CPCO and cannot be added to an owner COR.')
        if pco.linked_cor_id and int(pco.linked_cor_id) != int(cor.id):
            raise ValueError(f'PCO {pco.number} is already linked to another COR.')
        pco.linked_cor_id = cor.id
    linked = get_cor_linked_pcos(cor, PotentialChangeOrder)
    cor.amount = cor_amount_from_pcos(linked)
    cor.linked_pco_id = linked[0].id if len(linked) == 1 else (cor.linked_pco_id if len(linked) > 1 else None)
    return linked


def finalize_cor_promotion(cor, allocations, PotentialChangeOrder, PCOAllocation, db, generate_number_fn, user_id):
    """On COR approval: linked PCOs keep their SOV; legacy CORs without PCOs still spawn one PCO."""
    linked = get_cor_linked_pcos(cor, PotentialChangeOrder)
    if linked:
        cor.status = 'Promoted'
        if len(linked) == 1:
            cor.linked_pco_id = linked[0].id
        for pco in linked:
            if pco.status in ('Open', 'Draft', 'Pricing'):
                pco.status = 'Pending Review'
                pco.ball_in_court_role = 'Project Manager'
        return None
    return promote_cor_to_pco(cor, allocations, PotentialChangeOrder, PCOAllocation, db, generate_number_fn, user_id)


def cor_to_dict(cor, allocations=None, PotentialChangeOrder=None, PCOAllocation=None):
    linked_pcos = []
    rollup = []
    if PotentialChangeOrder is not None:
        linked_pcos = get_cor_linked_pcos(cor, PotentialChangeOrder)
        if PCOAllocation is not None and linked_pcos:
            rollup = cor_rollup_allocations(linked_pcos, PCOAllocation)

    legacy_alloc_rows = [{
        'cost_code': a.cost_code,
        'cost_type': getattr(a, 'cost_type', None) or '',
        'amount': float(a.amount or 0),
        'description': getattr(a, 'description', '') or '',
        'sov_line_id': getattr(a, 'sov_line_id', None),
        'tax_group': getattr(a, 'tax_group', None),
    } for a in (allocations or [])]

    if linked_pcos:
        amount = cor_amount_from_pcos(linked_pcos)
    elif legacy_alloc_rows:
        amount = round(sum(r['amount'] for r in legacy_alloc_rows), 2)
    else:
        amount = float(cor.amount or 0)

    return {
        'id': cor.id,
        'project_id': cor.project_id,
        'change_event_id': getattr(cor, 'change_event_id', None),
        'number': cor.number,
        'title': cor.title,
        'description': cor.description,
        'amount': amount,
        'status': cor.status,
        'reason': cor.reason,
        'priority': cor.priority,
        'schedule_impact_days': cor.schedule_impact_days or 0,
        'linked_pco_id': getattr(cor, 'linked_pco_id', None),
        'change_order_id': getattr(cor, 'change_order_id', None),
        'drawing_revision': getattr(cor, 'drawing_revision', None),
        'ball_in_court_role': getattr(cor, 'ball_in_court_role', None),
        'notes': getattr(cor, 'notes', None),
        'has_editable_sov': False,
        'linked_pcos': [{
            'id': p.id,
            'number': p.number,
            'title': p.title,
            'estimated_amount': float(p.estimated_amount or 0),
            'status': p.status,
        } for p in linked_pcos],
        'rollup_allocations': rollup,
        'allocations': legacy_alloc_rows if not linked_pcos else [],
        'created_at': cor.created_at.isoformat() if cor.created_at else None,
    }


def sage_event_to_dict(event):
    return {
        'id': event.id,
        'project_id': event.project_id,
        'event_type': event.event_type,
        'status': event.status,
        'accounting_status': getattr(event, 'accounting_status', None) or 'pending_review',
        'accounting_notes': getattr(event, 'accounting_notes', None),
        'accounting_reviewed_at': event.accounting_reviewed_at.isoformat() if getattr(event, 'accounting_reviewed_at', None) else None,
        'sage_job_number': event.sage_job_number,
        'message': event.message,
        'created_at': event.created_at.isoformat() if event.created_at else None,
        'posted_at': event.posted_at.isoformat() if event.posted_at else None,
        'error_text': event.error_text,
    }


def apply_change_event_fields(ce, data):
    for field in ('title', 'description', 'reason', 'priority', 'notes', 'drawing_revision', 'drawing_sheet_id'):
        if data.get(field) is not None:
            setattr(ce, field, data[field])
    if data.get('status') is not None or data.get('ball_in_court_role') is not None:
        pass  # workflow only
    if data.get('rom_amount') is not None:
        ce.rom_amount = float(data['rom_amount'])
    if data.get('schedule_impact_days') is not None:
        ce.schedule_impact_days = int(data['schedule_impact_days'])
    if data.get('linked_rfi_id') is not None:
        ce.linked_rfi_id = int(data['linked_rfi_id']) if data['linked_rfi_id'] else None
    if data.get('contingency_release_amount') is not None:
        ce.contingency_release_amount = float(data['contingency_release_amount'] or 0)


def apply_rfq_fields(rfq, data):
    for field in ('title', 'description', 'company_name', 'company_id', 'linked_commitment_ref',
                  'quote_notes', 'quoted_by'):
        if data.get(field) is not None:
            setattr(rfq, field, data[field])
    if data.get('status') is not None or data.get('ball_in_court_role') is not None:
        pass  # workflow only
    if data.get('change_event_id') is not None:
        rfq.change_event_id = int(data['change_event_id']) if data['change_event_id'] else None
    if data.get('quoted_amount') is not None or data.get('quoted_at') is not None:
        pass  # workflow only — use /workflow quote or portal-quote
    if data.get('due_date') is not None and data['due_date']:
        try:
            rfq.due_date = datetime.strptime(str(data['due_date'])[:10], '%Y-%m-%d').date()
        except ValueError:
            pass


def apply_cor_fields(cor, data):
    for field in ('title', 'description', 'reason', 'priority', 'notes', 'drawing_revision'):
        if data.get(field) is not None:
            setattr(cor, field, data[field])
    if data.get('status') is not None or data.get('ball_in_court_role') is not None:
        pass  # workflow only
    if data.get('amount') is not None:
        cor.amount = float(data['amount'])
    if data.get('schedule_impact_days') is not None:
        cor.schedule_impact_days = int(data['schedule_impact_days'])
    if data.get('change_event_id') is not None:
        cor.change_event_id = int(data['change_event_id']) if data['change_event_id'] else None
    if data.get('linked_pco_id') is not None:
        cor.linked_pco_id = int(data['linked_pco_id']) if data['linked_pco_id'] else None


def save_generic_allocations(AllocationModel, parent_field, parent_id, allocations, db, extra=None):
    AllocationModel.query.filter(getattr(AllocationModel, parent_field) == parent_id).delete()
    for item in allocations or []:
        kwargs = {
            parent_field: parent_id,
            'cost_code': item.get('cost_code'),
            'amount': float(item.get('amount') or 0),
        }
        row = AllocationModel(**kwargs)
        if hasattr(row, 'cost_type'):
            row.cost_type = item.get('cost_type', '')
        if hasattr(row, 'description'):
            row.description = item.get('description', '')
        if hasattr(row, 'quoted_amount'):
            row.quoted_amount = float(item.get('quoted_amount') or item.get('amount') or 0)
        if hasattr(row, 'sov_line_id'):
            row.sov_line_id = item.get('sov_line_id')
        if hasattr(row, 'tax_group'):
            row.tax_group = item.get('tax_group')
        if hasattr(row, 'change_event_line_item_id') and item.get('change_event_line_item_id'):
            row.change_event_line_item_id = int(item['change_event_line_item_id'])
        if extra:
            extra(row, item)
        db.session.add(row)


def rfq_workflow_action(rfq, action, user, allocations=None, *, portal_quote=False):
    from co_persistence import user_can_act_on_ball_in_court
    from financial_security import workflow_reject_authorized
    action = (action or '').lower()
    if action == 'send':
        if rfq.status != 'Draft':
            raise ValueError('Only draft RFQs can be sent')
        if not user_can_act_on_ball_in_court(user, rfq.ball_in_court_role or 'Creator'):
            raise ValueError('Cannot send this RFQ')
        if not (getattr(rfq, 'linked_commitment_ref', None) or '').strip() and not rfq.company_id:
            raise ValueError('RFQ requires a subcontractor or linked commitment')
        rfq.status = 'Sent'
        rfq.ball_in_court_role = 'Subcontractor'
        return rfq.status, False
    if action == 'quote':
        if rfq.status not in ('Sent', 'Draft'):
            raise ValueError('RFQ is not open for quoting')
        if rfq.status == 'Sent':
            if portal_quote:
                if not user_can_act_on_ball_in_court(user, 'Subcontractor'):
                    raise ValueError('Only the assigned subcontractor can quote a sent RFQ')
            elif not user_can_act_on_ball_in_court(user, rfq.ball_in_court_role or 'Subcontractor'):
                raise ValueError('Cannot quote this RFQ — ball is with subcontractor')
        elif not user_can_act_on_ball_in_court(user, rfq.ball_in_court_role or 'Creator'):
            raise ValueError('Cannot quote this RFQ')
        rows = allocations or []
        total = sum(float(r.get('quoted_amount') or r.get('amount') or 0) for r in rows)
        if total <= 0 and not float(rfq.quoted_amount or 0):
            raise ValueError('Quote amount is required')
        rfq.quoted_amount = total or float(rfq.quoted_amount or 0)
        rfq.quoted_at = datetime.utcnow()
        rfq.quoted_by = getattr(user, 'email', None) or 'Subcontractor'
        rfq.status = 'Quoted'
        rfq.ball_in_court_role = 'Project Manager'
        return rfq.status, False
    if action == 'accept':
        if not user_can_act_on_ball_in_court(user, rfq.ball_in_court_role or 'Project Manager'):
            raise ValueError('Cannot accept this RFQ')
        if rfq.status != 'Quoted':
            raise ValueError('Only quoted RFQs can be accepted')
        rfq.status = 'Accepted'
        rfq.ball_in_court_role = None
        return rfq.status, True
    if action == 'reject':
        workflow_reject_authorized(
            user, rfq.ball_in_court_role or 'Project Manager',
            user_can_act_fn=user_can_act_on_ball_in_court,
        )
        rfq.status = 'Rejected'
        rfq.ball_in_court_role = None
        return rfq.status, False
    raise ValueError('action must be send, quote, accept, or reject')


def change_event_workflow_action(ce, action, user):
    from co_persistence import user_can_act_on_ball_in_court
    action = (action or '').lower()
    if action == 'submit':
        if ce.status != 'Open':
            raise ValueError('Only open change events can be submitted for pricing')
        ce.status = 'Pricing'
        ce.ball_in_court_role = CHANGE_EVENT_BALL.get('Pricing')
        return ce.status, False
    if action == 'reject':
        from financial_security import workflow_reject_authorized
        workflow_reject_authorized(user, ce.ball_in_court_role, user_can_act_fn=user_can_act_on_ball_in_court)
        ce.status = 'Void'
        ce.ball_in_court_role = None
        return ce.status, False
    if action == 'approve':
        role = ce.ball_in_court_role or 'Project Manager'
        if not user_can_act_on_ball_in_court(user, role):
            raise ValueError(f'Cannot approve while ball is with {role}')
        for step in CHANGE_EVENT_APPROVAL_CHAIN:
            if step['from_status'] == ce.status and step['role'] == role:
                ce.status = step['next_status']
                ce.ball_in_court_role = CHANGE_EVENT_BALL.get(ce.status)
                if ce.status == 'Approved':
                    ce.ball_in_court_role = None
                    return ce.status, True
                return ce.status, False
        raise ValueError('No approval step for current change event status')
    raise ValueError('action must be submit, approve, or reject')


def cor_workflow_action(cor, action, user, body=None, ChangeOrderRequest=None, CORAllocation=None, PotentialChangeOrder=None):
    from co_persistence import user_can_act_on_ball_in_court, OWNER_CO_APPROVAL_THRESHOLD
    from financial_security import (
        authoritative_cor_amount,
        cumulative_approved_cor_amount,
        effective_threshold_amount,
        workflow_reject_authorized,
        OWNER_THRESHOLD,
    )
    action = (action or '').lower()
    if action == 'submit':
        if cor.status != 'Draft':
            raise ValueError('Only draft CORs can be submitted')
        cor.status = 'Submitted'
        cor.ball_in_court_role = 'Project Manager'
        return cor.status, False
    if action == 'reject':
        workflow_reject_authorized(user, cor.ball_in_court_role, user_can_act_fn=user_can_act_on_ball_in_court)
        cor.status = 'Rejected'
        cor.ball_in_court_role = None
        return cor.status, False
    if action == 'approve':
        role = cor.ball_in_court_role or 'Project Manager'
        if not user_can_act_on_ball_in_court(user, role):
            raise ValueError(f'Cannot approve while ball is with {role}')
        if role == 'Owner':
            body = body or {}
            if not body.get('signature_attestation'):
                raise ValueError('Electronic signature attestation is required for Owner COR approvals.')
            from user_signature_persistence import verify_user_signature_attestation
            verify_user_signature_attestation(user, (body.get('signature_hash') or '').strip())
        for step in COR_APPROVAL_CHAIN:
            if step['from_status'] == cor.status and step['role'] == role:
                next_status = step['next_status']
                base = authoritative_cor_amount(
                    cor, CORAllocation=CORAllocation, PotentialChangeOrder=PotentialChangeOrder,
                )
                cumulative = cumulative_approved_cor_amount(
                    cor.project_id, ChangeOrderRequest, exclude_cor_id=getattr(cor, 'id', None),
                ) if ChangeOrderRequest else 0.0
                amount = effective_threshold_amount(base, cumulative)
                if next_status == 'Pending Owner' and amount < OWNER_THRESHOLD:
                    next_status = 'Pending Accounting'
                if next_status == 'Pending Accounting' and amount < OWNER_THRESHOLD:
                    next_status = 'Approved'
                cor.status = next_status
                cor.approval_stage = (getattr(cor, 'approval_stage', 0) or 0) + 1
                cor.ball_in_court_role = COR_BALL_IN_COURT.get(cor.status)
                if cor.status == 'Approved':
                    cor.ball_in_court_role = None
                    return cor.status, True
                return cor.status, False
        raise ValueError('No approval step for current COR status')
    raise ValueError('action must be submit, approve, or reject')


def promote_rfq_to_cpco(rfq, allocations, PotentialChangeOrder, PCOAllocation, db, generate_number_fn, user_id, change_event_id=None):
    from co_persistence import schedule_days_to_label
    total = sum(float(getattr(a, 'quoted_amount', 0) or a.amount or 0) for a in allocations)
    if not total:
        total = float(rfq.quoted_amount or 0)
    pco = PotentialChangeOrder(
        project_id=rfq.project_id,
        number=generate_number_fn('CPCO', PotentialChangeOrder, doc_type='cpco'),
        title=rfq.title or f'CPCO from {rfq.number}',
        description=rfq.description or rfq.title,
        estimated_amount=total,
        status='Pricing',
        company_name=rfq.company_name,
        company_id=rfq.company_id,
        linked_commitment_ref=getattr(rfq, 'linked_commitment_ref', None),
        change_event_id=change_event_id or getattr(rfq, 'change_event_id', None),
        contract_type=CPCO_CONTRACT_TYPE,
        source_rfq_id=rfq.id,
        ball_in_court_role='Project Manager',
        created_by_id=user_id,
    )
    db.session.add(pco)
    db.session.flush()
    for a in allocations:
        db.session.add(PCOAllocation(
            pco_id=pco.id,
            cost_code=a.cost_code,
            cost_type=getattr(a, 'cost_type', None) or 'Subcontract',
            amount=float(getattr(a, 'quoted_amount', 0) or a.amount or 0),
            description=getattr(a, 'description', '') or '',
            sov_line_id=getattr(a, 'sov_line_id', None),
            tax_group=getattr(a, 'tax_group', None),
        ))
    rfq.linked_cpco_id = pco.id
    rfq.status = 'Accepted'
    return pco


def promote_cor_to_pco(cor, allocations, PotentialChangeOrder, PCOAllocation, db, generate_number_fn, user_id):
    total = sum(float(a.amount or 0) for a in allocations) if allocations else float(cor.amount or 0)
    pco = PotentialChangeOrder(
        project_id=cor.project_id,
        number=generate_number_fn('PCO', PotentialChangeOrder, doc_type='pco'),
        title=cor.title,
        description=cor.description or cor.title,
        estimated_amount=total,
        status='Pending Review',
        reason=cor.reason,
        priority=cor.priority,
        schedule_impact_days=cor.schedule_impact_days or 0,
        change_event_id=getattr(cor, 'change_event_id', None),
        linked_cor_id=cor.id,
        linked_drawing_revision=getattr(cor, 'drawing_revision', None),
        contract_type='Owner',
        ball_in_court_role='Project Manager',
        created_by_id=user_id,
    )
    db.session.add(pco)
    db.session.flush()
    for a in allocations or []:
        db.session.add(PCOAllocation(
            pco_id=pco.id,
            cost_code=a.cost_code,
            cost_type=getattr(a, 'cost_type', None) or 'Other',
            amount=float(a.amount or 0),
            description=getattr(a, 'description', '') or '',
            sov_line_id=getattr(a, 'sov_line_id', None),
            tax_group=getattr(a, 'tax_group', None),
            change_event_line_item_id=getattr(a, 'change_event_line_item_id', None),
        ))
    cor.linked_pco_id = pco.id
    cor.status = 'Promoted'
    return pco


def promote_cpco_to_sco(pco, allocations, ChangeOrder, ChangeOrderAllocation, db, generate_number_fn, user_id, SubcontractorRFQ=None):
    from co_persistence import compute_co_amount_from_allocations
    total = sum(float(a.amount or 0) for a in allocations) if allocations else float(pco.estimated_amount or 0)
    sco = ChangeOrder(
        project_id=pco.project_id,
        number=generate_number_fn('SCO', ChangeOrder, doc_type='sub_change_order', project_id=pco.project_id),
        title=pco.title,
        description=pco.description or pco.title,
        amount=total,
        reason=pco.reason,
        schedule_impact_days=pco.schedule_impact_days or 0,
        status='Draft',
        date=datetime.utcnow().date(),
        company_name=pco.company_name,
        company_id=pco.company_id,
        contract_type='Subcontract',
        sub_co_kind='Contract Add',
        linked_commitment_ref=getattr(pco, 'linked_commitment_ref', None),
        change_event_id=getattr(pco, 'change_event_id', None),
        source_rfq_id=getattr(pco, 'source_rfq_id', None),
        source_cpco_id=pco.id,
        linked_drawing_revision=getattr(pco, 'linked_drawing_revision', None),
        ball_in_court_role='Creator',
        created_by_id=user_id,
    )
    db.session.add(sco)
    db.session.flush()
    for a in allocations or []:
        db.session.add(ChangeOrderAllocation(
            change_order_id=sco.id,
            cost_code=a.cost_code,
            cost_type=getattr(a, 'cost_type', None) or 'Subcontract',
            amount=float(a.amount or 0),
            description=getattr(a, 'description', '') or '',
            sov_line_id=getattr(a, 'sov_line_id', None),
            tax_group=getattr(a, 'tax_group', None),
            change_event_line_item_id=getattr(a, 'change_event_line_item_id', None),
        ))
    pco.change_order_id = sco.id
    pco.status = 'Promoted'
    if getattr(pco, 'source_rfq_id', None) and SubcontractorRFQ is not None:
        rfq = SubcontractorRFQ.query.get(pco.source_rfq_id)
        if rfq:
            rfq.linked_sco_id = sco.id
    return sco


def apply_contingency_release(BudgetProjectState, project_id, amount, db):
    if not amount:
        return None
    from budget_persistence import get_budget_state, save_budget_state
    _, state = get_budget_state(BudgetProjectState, project_id)
    lines = state.get('budgetLines') or []
    released = 0.0
    for line in lines:
        if str(line.get('cost_type', '')).lower() in ('contingency', 'allowance'):
            avail = float(line.get('original_budget', 0) or 0) - float(line.get('approved_changes', 0) or 0)
            take = min(avail, float(amount) - released)
            if take > 0:
                line['approved_changes'] = float(line.get('approved_changes', 0) or 0) + take
                released += take
        if released >= float(amount):
            break
    if released:
        save_budget_state(BudgetProjectState, db, project_id, state)
    return {'released': released}


def apply_partial_budget_line(BudgetProjectState, project_id, cost_code, cost_type, amount, description, db):
    from budget_persistence import get_budget_state, save_budget_state, normalize_cost_code
    _, state = get_budget_state(BudgetProjectState, project_id)
    lines = state.get('budgetLines') or []
    norm = normalize_cost_code(cost_code)
    found = False
    for line in lines:
        if normalize_cost_code(line.get('cost_code')) == norm and (line.get('cost_type') or '') == (cost_type or ''):
            line['pending'] = float(line.get('pending', 0) or 0) + float(amount or 0)
            found = True
            break
    if not found:
        lines.append({
            'cost_code': cost_code,
            'cost_type': cost_type or 'Other',
            'description': description or f'Change event line {cost_code}',
            'original_budget': 0,
            'approved_changes': 0,
            'pending': float(amount or 0),
            'committed': 0,
            'actual': 0,
        })
        state['budgetLines'] = lines
    save_budget_state(BudgetProjectState, db, project_id, state)
    return {'added': not found, 'cost_code': cost_code}


def update_sco_retainage_and_billing(co, PayAppProjectState, Commitment, ChangeOrderAllocation, db):
    """Apply retainage % from commitment and compute billing variance on approved sub CO."""
    if co.status != 'Approved':
        return {}
    from pay_app_persistence import get_pay_app_state, normalize_sub_sov_keys, normalize_cost_code
    _, state = get_pay_app_state(PayAppProjectState, co.project_id)
    sub_sov = normalize_sub_sov_keys(state.get('subcontractorSOV') or {})
    retainage_pct = 0.0
    if getattr(co, 'linked_commitment_ref', None) and Commitment is not None:
        com = Commitment.query.filter_by(project_id=co.project_id, number=co.linked_commitment_ref).first()
        if com:
            retainage_pct = float(com.retainage_percent or 0)
    billed = 0.0
    allocs = ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all() if ChangeOrderAllocation else []
    company_keys = []
    cid = str(getattr(co, 'company_id', '') or '').strip()
    cname = (getattr(co, 'company_name', '') or '').strip()
    if cid:
        company_keys.append(cid)
    if cname:
        company_keys.append(cname)
    for key in company_keys:
        for line in sub_sov.get(key) or []:
            if co.number and co.number in str(line.get('from_change_order', '')):
                billed += float(line.get('co_billed_to_date') or 0) + float(line.get('billed_to_date') or 0)
    for alloc in allocs:
        if getattr(alloc, 'retainage_percent', None) is None and retainage_pct:
            alloc.retainage_percent = retainage_pct
    variance = round(float(co.amount or 0) - billed, 2)
    co.billed_amount = billed
    co.billing_variance = variance
    db.session.flush()
    return {'retainage_percent': retainage_pct, 'billed': billed, 'variance': variance}


def compute_billing_variance_for_sub_cos(cos, PayAppProjectState, project_id):
    from pay_app_persistence import get_pay_app_state, normalize_sub_sov_keys, normalize_cost_code
    _, state = get_pay_app_state(PayAppProjectState, project_id)
    sub_sov = normalize_sub_sov_keys(state.get('subcontractorSOV') or {})
    results = []
    for co in cos:
        if getattr(co, 'contract_type', None) not in ('Subcontract', 'Subcontractor'):
            continue
        if co.status != 'Approved':
            continue
        billed = 0.0
        company_keys = []
        cid = str(getattr(co, 'company_id', '') or '').strip()
        cname = (getattr(co, 'company_name', '') or '').strip()
        if cid:
            company_keys.append(cid)
        if cname:
            company_keys.append(cname)
        for key in company_keys:
            for line in sub_sov.get(key) or []:
                if co.number and co.number in str(line.get('from_change_order', '')):
                    billed += float(line.get('co_billed_to_date') or 0) + float(line.get('billed_to_date') or 0)
        variance = round(float(co.amount or 0) - billed, 2)
        results.append({'change_order_id': co.id, 'number': co.number, 'approved': co.amount, 'billed': billed, 'variance': variance})
    return results


def queue_sage_event_for_accounting_review(
    SageSyncEvent, Project, db, project_id, event_type, message, payload, user_id,
):
    """Create Sage event pending accounting acceptance (does not auto-post)."""
    from sage_service import build_sage_payload, _project_sage_context
    ctx = _project_sage_context(Project, project_id)
    sage_payload = build_sage_payload(event_type, ctx, payload or {})
    event = SageSyncEvent(
        project_id=project_id,
        event_type=event_type,
        status='queued',
        accounting_status='pending_review',
        sage_job_number=ctx.get('sage_job_number') or '',
        message=message,
        payload_json=json.dumps(sage_payload),
        created_by_id=user_id,
    )
    db.session.add(event)
    db.session.flush()
    return event


def accept_sage_event_for_export(event, user, db, Commitment=None):
    from sage_service import process_sage_event
    if getattr(event, 'accounting_status', None) == 'rejected':
        raise ValueError('Rejected events cannot be accepted')
    event.accounting_status = 'accepted'
    event.accounting_reviewed_by_id = user.id
    event.accounting_reviewed_at = datetime.utcnow()
    process_sage_event(event, db, Commitment=Commitment)
    return event


def reject_sage_event(event, user, notes=''):
    event.accounting_status = 'rejected'
    event.accounting_reviewed_by_id = user.id
    event.accounting_reviewed_at = datetime.utcnow()
    event.accounting_notes = (notes or '').strip()
    event.status = 'rejected'
    return event


def notify_accounting_erp_review(event, Project, db, User=None):
    """Alert Contractor Accounting when a Sage event is queued for review."""
    try:
        import case_workflow as cw
        from co_persistence import user_can_act_on_ball_in_court
        if getattr(event, 'accounting_status', None) != 'pending_review':
            return
        if User is None:
            try:
                from app import User as UserModel
                User = UserModel
            except Exception:
                return
        from email_notifications import notify_role_workflow
        from co_persistence import user_can_act_on_ball_in_court
        project = Project.query.get(event.project_id) if Project else None
        project_name = getattr(project, 'name', None) or f'Project #{event.project_id}'
        action_url = f'/change-orders?project_id={event.project_id}&tab=erp'
        title = f'ERP review: {event.event_type}'
        description = event.message or f'{event.event_type} requires accounting acceptance before Sage export.'
        notify_role_workflow(
            User,
            'Contractor Accounting',
            title=f'{project_name} — {title}',
            description=description,
            action_url=action_url,
            project_id=event.project_id,
            module='ERP Queue',
            can_act_fn=user_can_act_on_ball_in_court,
        )
    except Exception:
        pass


def link_change_event_schedule_impact(ScheduleData, Project, db, project_id, change_event, co_number=None):
    from co_persistence import schedule_days_to_label
    from pay_app_persistence import apply_schedule_impact
    days = int(getattr(change_event, 'schedule_impact_days', 0) or 0)
    if days <= 0:
        return None
    label = schedule_days_to_label(days)
    num = co_number or getattr(change_event, 'number', None) or 'CE'
    desc = getattr(change_event, 'title', None) or getattr(change_event, 'description', None) or 'Change event'
    return apply_schedule_impact(ScheduleData, Project, db, project_id, label, num, desc)


def notify_rfq_subcontractor(project_id, rfq, User, title=None):
    try:
        from email_notifications import notify_user_workflow
        action_url = f'/rfq-portal?project_id={project_id}&rfq_id={rfq.id}'
        title = title or f'{rfq.number} — RFQ sent for quote'
        users = User.query.filter_by(status='Active').all()
        targets = []
        cid = str(getattr(rfq, 'company_id', '') or '').strip()
        cname = (getattr(rfq, 'company_name', '') or '').strip()
        for u in users:
            if cid and str(getattr(u, 'company_id', '') or '') == cid:
                targets.append(u)
            elif cname and (getattr(u, 'company', '') or '').strip() == cname:
                targets.append(u)
            elif getattr(rfq, 'contact_email', None) and u.email == rfq.contact_email:
                targets.append(u)
        if not targets:
            targets = [u for u in users if getattr(u, 'role', '') in ('Company User', 'Subcontractor Accountant')][:5]
        seen = set()
        for u in targets:
            if u.id in seen:
                continue
            seen.add(u.id)
            notify_user_workflow(
                u,
                title=title,
                description=rfq.description or rfq.title or 'Please submit your quote.',
                action_url=action_url,
                project_id=project_id,
                module='RFQs',
            )
    except Exception:
        pass


def change_event_line_item_to_dict(row):
    return {
        'id': row.id,
        'change_event_id': row.change_event_id,
        'sort_order': row.sort_order or 0,
        'description': row.description or '',
        'cost_code': row.cost_code or '',
        'cost_type': row.cost_type or 'Subcontract',
        'amount': float(row.amount or 0),
        'quoted_amount': float(row.quoted_amount or 0),
        'company_name': row.company_name or '',
        'company_id': row.company_id or '',
        'linked_commitment_ref': row.linked_commitment_ref or '',
        'sov_line_id': row.sov_line_id or '',
        'tax_group': row.tax_group or '',
        'status': row.status or 'Open',
        'linked_rfq_id': row.linked_rfq_id,
        'linked_cpco_id': row.linked_cpco_id,
        'linked_sco_id': row.linked_sco_id,
    }


def _line_commitment_group_key(line):
    ref = (getattr(line, 'linked_commitment_ref', None) or '').strip()
    cid = str(getattr(line, 'company_id', None) or '').strip()
    cname = (getattr(line, 'company_name', None) or '').strip().lower()
    if not ref:
        raise ValueError('Each line item must have a linked commitment before creating commitment change orders.')
    if not cid and not cname:
        raise ValueError('Each line item must have a vendor (company) assigned.')
    return (ref, cid, cname)


def _vendor_group_key(line):
    ref = (getattr(line, 'linked_commitment_ref', None) or '').strip()
    cid = str(getattr(line, 'company_id', None) or '').strip()
    cname = (getattr(line, 'company_name', None) or '').strip().lower()
    if not cid and not cname:
        raise ValueError('Each line item must have a vendor (company) assigned.')
    return (ref, cid, cname)


def recompute_change_event_rom(ce, ChangeEventLineItem):
    rows = ChangeEventLineItem.query.filter_by(change_event_id=ce.id).all()
    ce.rom_amount = round(sum(float(r.amount or 0) for r in rows), 2)


def save_change_event_line_items(ce, lines, ChangeEventLineItem, db):
    """Replace line items on a change event, preserving workflow links when provided."""
    existing = {r.id: r for r in ChangeEventLineItem.query.filter_by(change_event_id=ce.id).all()}
    keep_ids = set()
    saved_rows = []
    for idx, item in enumerate(lines or []):
        raw_id = item.get('id')
        row = existing.get(int(raw_id)) if raw_id not in (None, '') else None
        if not row:
            row = ChangeEventLineItem(change_event_id=ce.id)
            db.session.add(row)
        row.sort_order = int(item.get('sort_order', idx))
        row.description = (item.get('description') or '').strip() or None
        row.cost_code = (item.get('cost_code') or '').strip() or None
        row.cost_type = (item.get('cost_type') or 'Subcontract').strip() or 'Subcontract'
        row.amount = float(item.get('amount') or 0)
        row.quoted_amount = float(item.get('quoted_amount') or 0)
        row.company_name = (item.get('company_name') or '').strip() or None
        row.company_id = (item.get('company_id') or '').strip() or None
        row.linked_commitment_ref = (item.get('linked_commitment_ref') or '').strip() or None
        row.sov_line_id = (item.get('sov_line_id') or '').strip() or None
        row.tax_group = (item.get('tax_group') or '').strip() or None
        if item.get('linked_rfq_id'):
            row.linked_rfq_id = int(item['linked_rfq_id'])
        if item.get('linked_cpco_id'):
            row.linked_cpco_id = int(item['linked_cpco_id'])
        if item.get('linked_sco_id'):
            row.linked_sco_id = int(item['linked_sco_id'])
        if not row.linked_sco_id and not row.linked_cpco_id and not row.linked_rfq_id:
            row.status = (item.get('status') or 'Open').strip() or 'Open'
        db.session.flush()
        keep_ids.add(row.id)
        saved_rows.append(row)
    for old_id, old_row in existing.items():
        if old_id not in keep_ids and not old_row.linked_sco_id:
            db.session.delete(old_row)
    db.session.flush()
    recompute_change_event_rom(ce, ChangeEventLineItem)
    saved = ChangeEventLineItem.query.filter_by(change_event_id=ce.id).order_by(
        ChangeEventLineItem.sort_order.asc(), ChangeEventLineItem.id.asc()
    ).all()
    return [change_event_line_item_to_dict(r) for r in saved]


def _line_alloc_payload(line):
    amt = float(getattr(line, 'quoted_amount', 0) or 0) or float(line.amount or 0)
    return {
        'cost_code': line.cost_code,
        'cost_type': line.cost_type or 'Subcontract',
        'amount': amt,
        'quoted_amount': float(getattr(line, 'quoted_amount', 0) or 0) or amt,
        'description': line.description or '',
        'sov_line_id': line.sov_line_id,
        'tax_group': line.tax_group,
        'change_event_line_item_id': line.id,
    }


def bulk_create_rfqs_from_lines(ce, line_ids, SubcontractorRFQ, RFQAllocation, ChangeEventLineItem, db, generate_number_fn, user_id):
    """Create one draft RFQ per vendor/commitment group from selected CE line items."""
    ids = [int(i) for i in (line_ids or [])]
    if not ids:
        raise ValueError('Select at least one line item.')
    rows = ChangeEventLineItem.query.filter(
        ChangeEventLineItem.change_event_id == ce.id,
        ChangeEventLineItem.id.in_(ids),
    ).all()
    if len(rows) != len(ids):
        raise ValueError('One or more line items were not found on this change event.')
    for row in rows:
        if row.linked_rfq_id:
            raise ValueError(f'Line {row.cost_code or row.id} is already linked to an RFQ.')
        if row.linked_sco_id:
            raise ValueError(f'Line {row.cost_code or row.id} is already on a commitment change order.')

    groups = {}
    for row in rows:
        key = _vendor_group_key(row)
        groups.setdefault(key, []).append(row)

    created = []
    for (_ref, _cid, _cname), group_rows in groups.items():
        first = group_rows[0]
        rfq = SubcontractorRFQ(
            project_id=ce.project_id,
            change_event_id=ce.id,
            number=generate_number_fn('RFQ', SubcontractorRFQ, doc_type='rfq', project_id=ce.project_id),
            title=ce.title or f'RFQ from {ce.number}',
            description=ce.description or ce.title,
            status='Draft',
            company_name=first.company_name,
            company_id=first.company_id,
            linked_commitment_ref=first.linked_commitment_ref,
            ball_in_court_role='Creator',
            created_by_id=user_id,
        )
        db.session.add(rfq)
        db.session.flush()
        for row in group_rows:
            payload = _line_alloc_payload(row)
            db.session.add(RFQAllocation(
                rfq_id=rfq.id,
                cost_code=payload['cost_code'],
                cost_type=payload['cost_type'],
                amount=float(row.amount or 0),
                quoted_amount=payload['quoted_amount'],
                description=payload['description'],
                sov_line_id=payload['sov_line_id'],
                tax_group=payload['tax_group'],
            ))
            row.linked_rfq_id = rfq.id
            row.status = 'RFQ Draft'
        created.append(rfq)
    return created


def bulk_create_commitment_cos_from_lines(
    ce,
    line_ids,
    ChangeOrder,
    ChangeOrderAllocation,
    ChangeEventLineItem,
    db,
    generate_number_fn,
    user_id,
):
    """Create one draft commitment change order (SCO/CCO) per vendor+commitment group."""
    ids = [int(i) for i in (line_ids or [])]
    if not ids:
        raise ValueError('Select at least one line item.')
    rows = ChangeEventLineItem.query.filter(
        ChangeEventLineItem.change_event_id == ce.id,
        ChangeEventLineItem.id.in_(ids),
    ).all()
    if len(rows) != len(ids):
        raise ValueError('One or more line items were not found on this change event.')
    for row in rows:
        if row.linked_sco_id:
            raise ValueError(f'Line {row.cost_code or row.id} is already on a commitment change order.')

    groups = {}
    for row in rows:
        key = _line_commitment_group_key(row)
        groups.setdefault(key, []).append(row)

    created = []
    for (ref, _cid, _cname), group_rows in groups.items():
        first = group_rows[0]
        allocs = [_line_alloc_payload(r) for r in group_rows]
        total = round(sum(float(a['amount'] or 0) for a in allocs), 2)
        sco = ChangeOrder(
            project_id=ce.project_id,
            number=generate_number_fn('SCO', ChangeOrder, doc_type='sub_change_order', project_id=ce.project_id),
            title=f'{ce.number} — {first.company_name or ref}',
            description=ce.description or ce.title or f'Commitment change from {ce.number}',
            amount=total,
            reason=ce.reason,
            schedule_impact_days=ce.schedule_impact_days or 0,
            status='Draft',
            date=datetime.utcnow().date(),
            company_name=first.company_name,
            company_id=first.company_id,
            contract_type='Subcontract',
            sub_co_kind='Contract Add',
            linked_commitment_ref=ref,
            change_event_id=ce.id,
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
                sov_line_id=item.get('sov_line_id'),
                tax_group=item.get('tax_group'),
                change_event_line_item_id=item.get('change_event_line_item_id'),
            ))
        for row in group_rows:
            row.linked_sco_id = sco.id
            row.status = 'In CCO'
        created.append(sco)
    return created


def bulk_create_cpcos_from_lines(
    ce,
    line_ids,
    PotentialChangeOrder,
    PCOAllocation,
    ChangeEventLineItem,
    db,
    generate_number_fn,
    user_id,
):
    """Create one draft CPCO per vendor+commitment group from selected CE line items."""
    ids = [int(i) for i in (line_ids or [])]
    if not ids:
        raise ValueError('Select at least one line item.')
    rows = ChangeEventLineItem.query.filter(
        ChangeEventLineItem.change_event_id == ce.id,
        ChangeEventLineItem.id.in_(ids),
    ).all()
    if len(rows) != len(ids):
        raise ValueError('One or more line items were not found on this change event.')
    for row in rows:
        if row.linked_cpco_id:
            raise ValueError(f'Line {row.cost_code or row.id} is already linked to a CPCO.')
        if row.linked_sco_id:
            raise ValueError(f'Line {row.cost_code or row.id} is already on a commitment change order.')

    groups = {}
    for row in rows:
        key = _line_commitment_group_key(row)
        groups.setdefault(key, []).append(row)

    created = []
    for (ref, _cid, _cname), group_rows in groups.items():
        first = group_rows[0]
        allocs = [_line_alloc_payload(r) for r in group_rows]
        total = round(sum(float(a['amount'] or 0) for a in allocs), 2)
        pco = PotentialChangeOrder(
            project_id=ce.project_id,
            number=generate_number_fn('CPCO', PotentialChangeOrder, doc_type='cpco'),
            title=f'{ce.number} — {first.company_name or ref}',
            description=ce.description or ce.title,
            estimated_amount=total,
            status='Pricing',
            company_name=first.company_name,
            company_id=first.company_id,
            linked_commitment_ref=ref,
            change_event_id=ce.id,
            contract_type=CPCO_CONTRACT_TYPE,
            ball_in_court_role='Project Manager',
            created_by_id=user_id,
        )
        db.session.add(pco)
        db.session.flush()
        for item in allocs:
            db.session.add(PCOAllocation(
                pco_id=pco.id,
                cost_code=item.get('cost_code'),
                cost_type=item.get('cost_type') or 'Subcontract',
                amount=float(item.get('amount') or 0),
                description=item.get('description') or '',
                sov_line_id=item.get('sov_line_id'),
                tax_group=item.get('tax_group'),
                change_event_line_item_id=item.get('change_event_line_item_id'),
            ))
        for row in group_rows:
            row.linked_cpco_id = pco.id
            row.status = 'In CPCO'
        created.append(pco)
    return created
