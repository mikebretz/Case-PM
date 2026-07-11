"""Commitments (PO / Subcontract / supply agreements) — persistence, workflow, integrations."""
from __future__ import annotations

import json
from datetime import datetime

COMMITMENT_TYPES = (
    'Purchase Order', 'Subcontract', 'Material Supply', 'Service Agreement',
)
COMMITMENT_STATUSES = (
    'Draft', 'Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner',
    'Approved', 'Rejected', 'Partially Invoiced', 'Closed', 'Void',
)
AIA_FORMS = (
    'A101', 'A102', 'A201', 'A401', 'A501', 'A701', 'A312', 'Other', 'N/A',
)
SIGNATURE_METHODS = ('internal', 'docusign', 'wet_signature')
SIGNATURE_STATUSES = (
    'unsigned', 'pending_signatures', 'partially_signed', 'fully_executed',
)

BALL_IN_COURT_MAP = {
    'Draft': 'Creator',
    'Submitted': 'Project Manager',
    'Pending PM': 'Project Manager',
    'Pending Accounting': 'Contractor Accounting',
    'Pending Owner': 'Owner',
    'Approved': None,
    'Rejected': None,
    'Void': None,
    'Partially Invoiced': None,
    'Closed': None,
}

# Sequential approval workflow
APPROVAL_CHAIN = (
    {'from_status': 'Submitted', 'role': 'Project Manager', 'next_status': 'Pending Accounting'},
    {'from_status': 'Pending PM', 'role': 'Project Manager', 'next_status': 'Pending Accounting'},
    {'from_status': 'Pending Accounting', 'role': 'Contractor Accounting', 'next_status': 'Pending Owner'},
    {'from_status': 'Pending Owner', 'role': 'Owner', 'next_status': 'Approved'},
)

ROLE_APPROVERS = {
    'Project Manager': ('Project Manager', 'Admin'),
    'Contractor Accounting': ('Contractor Accounting', 'Admin'),
    'Owner': ('Owner', 'Admin'),
    'Creator': ('Project Manager', 'Admin', 'Company User'),
}

OWNER_APPROVAL_THRESHOLD = 50000.0
PENDING_STATUSES = ('Submitted', 'Pending PM', 'Pending Accounting', 'Pending Owner')


def ensure_commitment_schema(engine, db):
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if 'commitment' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('commitment')}
    additions = {
        'title': 'VARCHAR(200)',
        'company_id': 'VARCHAR(64)',
        'contact_name': 'VARCHAR(150)',
        'contact_email': 'VARCHAR(150)',
        'contact_phone': 'VARCHAR(50)',
        'ball_in_court_role': 'VARCHAR(80)',
        'approval_stage': 'INTEGER DEFAULT 0',
        'submitted_at': 'DATETIME',
        'executed_date': 'DATE',
        'retainage_percent': 'FLOAT DEFAULT 0',
        'aia_form': 'VARCHAR(20)',
        'payment_terms': 'VARCHAR(120)',
        'scope_of_work': 'TEXT',
        'signature_method': 'VARCHAR(30) DEFAULT "internal"',
        'signature_status': 'VARCHAR(40) DEFAULT "unsigned"',
        'docusign_envelope_id': 'VARCHAR(120)',
        'docusign_status': 'VARCHAR(60)',
        'signed_document_url': 'VARCHAR(400)',
        'certified_signatures_json': 'TEXT',
        'attachments_json': 'TEXT',
        'sage_sync_status': 'VARCHAR(60)',
        'budget_validated': 'BOOLEAN DEFAULT 0',
        'invoiced_amount': 'FLOAT DEFAULT 0',
        'updated_at': 'DATETIME',
        'start_date': 'DATE',
        'end_date': 'DATE',
        'billing_type': 'VARCHAR(40)',
        'bond_required': 'BOOLEAN DEFAULT 0',
        'insurance_requirements': 'TEXT',
        'owner_name': 'VARCHAR(200)',
        'contractor_name': 'VARCHAR(200)',
        'architect_engineer': 'VARCHAR(200)',
        'delivery_date': 'DATE',
        'freight_terms': 'VARCHAR(120)',
        'tax_exempt': 'BOOLEAN DEFAULT 0',
        'aia_contract_json': 'TEXT',
        'external_document_provider': 'VARCHAR(40)',
        'external_document_id': 'VARCHAR(200)',
        'external_document_url': 'VARCHAR(500)',
        'catina_project_id': 'VARCHAR(120)',
    }
    for name, col_type in additions.items():
        if name not in cols:
            db.session.execute(text(f'ALTER TABLE commitment ADD COLUMN {name} {col_type}'))
    db.session.commit()

    if 'commitment_allocation' in inspector.get_table_names():
        alloc_cols = {c['name'] for c in inspector.get_columns('commitment_allocation')}
        if 'description' not in alloc_cols:
            db.session.execute(text('ALTER TABLE commitment_allocation ADD COLUMN description VARCHAR(200)'))
            db.session.commit()


def _parse_json(raw, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def prefix_for_type(commitment_type):
    mapping = {
        'Purchase Order': 'PO',
        'Subcontract': 'SC',
        'Material Supply': 'MS',
        'Service Agreement': 'SA',
    }
    return mapping.get(commitment_type, 'COM')


def commitment_to_dict(commitment, allocations=None):
    allocs = allocations or []
    original = float(commitment.original_amount or 0)
    changes = float(commitment.approved_changes or 0)
    current = float(commitment.current_amount if commitment.current_amount is not None else original + changes)
    return {
        'id': commitment.id,
        'project_id': commitment.project_id,
        'number': commitment.number,
        'title': getattr(commitment, 'title', None) or commitment.description,
        'description': commitment.description,
        'commitment_type': commitment.commitment_type,
        'status': commitment.status,
        'original_amount': original,
        'approved_changes': changes,
        'current_amount': current,
        'company_name': commitment.company_name,
        'company_id': getattr(commitment, 'company_id', None),
        'contact_name': getattr(commitment, 'contact_name', None),
        'contact_email': getattr(commitment, 'contact_email', None),
        'contact_phone': getattr(commitment, 'contact_phone', None),
        'date': commitment.date.isoformat() if commitment.date else None,
        'executed_date': commitment.executed_date.isoformat() if getattr(commitment, 'executed_date', None) else None,
        'retainage_percent': float(getattr(commitment, 'retainage_percent', 0) or 0),
        'aia_form': getattr(commitment, 'aia_form', None) or 'N/A',
        'payment_terms': getattr(commitment, 'payment_terms', None),
        'scope_of_work': getattr(commitment, 'scope_of_work', None) or commitment.notes,
        'ball_in_court_role': getattr(commitment, 'ball_in_court_role', None),
        'approval_stage': getattr(commitment, 'approval_stage', 0) or 0,
        'signature_method': getattr(commitment, 'signature_method', None) or 'internal',
        'signature_status': getattr(commitment, 'signature_status', None) or 'unsigned',
        'docusign_envelope_id': getattr(commitment, 'docusign_envelope_id', None),
        'docusign_status': getattr(commitment, 'docusign_status', None),
        'signed_document_url': getattr(commitment, 'signed_document_url', None),
        'certified_signatures': _parse_json(getattr(commitment, 'certified_signatures_json', None), []),
        'attachments': _parse_json(getattr(commitment, 'attachments_json', None), []),
        'sage_sync_status': getattr(commitment, 'sage_sync_status', None),
        'budget_validated': bool(getattr(commitment, 'budget_validated', False)),
        'invoiced_amount': float(getattr(commitment, 'invoiced_amount', 0) or 0),
        'notes': commitment.notes,
        'start_date': commitment.start_date.isoformat() if getattr(commitment, 'start_date', None) else None,
        'end_date': commitment.end_date.isoformat() if getattr(commitment, 'end_date', None) else None,
        'billing_type': getattr(commitment, 'billing_type', None) or 'Lump Sum',
        'bond_required': bool(getattr(commitment, 'bond_required', False)),
        'insurance_requirements': getattr(commitment, 'insurance_requirements', None),
        'owner_name': getattr(commitment, 'owner_name', None),
        'contractor_name': getattr(commitment, 'contractor_name', None),
        'architect_engineer': getattr(commitment, 'architect_engineer', None),
        'delivery_date': commitment.delivery_date.isoformat() if getattr(commitment, 'delivery_date', None) else None,
        'freight_terms': getattr(commitment, 'freight_terms', None),
        'tax_exempt': bool(getattr(commitment, 'tax_exempt', False)),
        'aia_contract': _parse_json(getattr(commitment, 'aia_contract_json', None), None),
        'external_document_provider': getattr(commitment, 'external_document_provider', None),
        'external_document_id': getattr(commitment, 'external_document_id', None),
        'external_document_url': getattr(commitment, 'external_document_url', None),
        'catina_project_id': getattr(commitment, 'catina_project_id', None),
        'submitted_at': commitment.submitted_at.isoformat() if getattr(commitment, 'submitted_at', None) else None,
        'approved_at': commitment.approved_at.isoformat() if commitment.approved_at else None,
        'allocations': [
            {
                'cost_code': a.cost_code,
                'amount': float(a.amount or 0),
                'description': getattr(a, 'description', '') or '',
            }
            for a in allocs
        ],
        'created_at': commitment.created_at.isoformat() if commitment.created_at else None,
        'updated_at': commitment.updated_at.isoformat() if getattr(commitment, 'updated_at', None) else None,
    }


def apply_commitment_fields(commitment, data):
    for field in (
        'title', 'description', 'commitment_type', 'status', 'notes', 'company_name', 'company_id',
        'contact_name', 'contact_email', 'contact_phone', 'aia_form', 'payment_terms', 'scope_of_work',
        'ball_in_court_role', 'signature_method', 'signature_status', 'docusign_envelope_id',
        'docusign_status', 'signed_document_url', 'sage_sync_status', 'billing_type',
        'insurance_requirements', 'owner_name', 'contractor_name', 'architect_engineer', 'freight_terms',
        'external_document_provider', 'external_document_id', 'external_document_url', 'catina_project_id',
    ):
        if data.get(field) is not None:
            setattr(commitment, field, data[field])
    if data.get('original_amount') is not None:
        commitment.original_amount = float(data['original_amount'])
    if data.get('approved_changes') is not None:
        commitment.approved_changes = float(data['approved_changes'])
    if data.get('current_amount') is not None:
        commitment.current_amount = float(data['current_amount'])
    elif data.get('original_amount') is not None or data.get('approved_changes') is not None:
        commitment.current_amount = float(commitment.original_amount or 0) + float(commitment.approved_changes or 0)
    if data.get('retainage_percent') is not None:
        commitment.retainage_percent = float(data['retainage_percent'])
    if data.get('invoiced_amount') is not None:
        commitment.invoiced_amount = float(data['invoiced_amount'])
    if data.get('budget_validated') is not None:
        commitment.budget_validated = bool(data['budget_validated'])
    if data.get('date') is not None:
        commitment.date = _parse_date(data['date'])
    if data.get('executed_date') is not None:
        commitment.executed_date = _parse_date(data['executed_date'])
    if data.get('start_date') is not None:
        commitment.start_date = _parse_date(data['start_date'])
    if data.get('end_date') is not None:
        commitment.end_date = _parse_date(data['end_date'])
    if data.get('delivery_date') is not None:
        commitment.delivery_date = _parse_date(data['delivery_date'])
    if data.get('bond_required') is not None:
        commitment.bond_required = bool(data['bond_required'])
    if data.get('tax_exempt') is not None:
        commitment.tax_exempt = bool(data['tax_exempt'])
    if data.get('certified_signatures') is not None:
        commitment.certified_signatures_json = json.dumps(data['certified_signatures'])
    if data.get('attachments') is not None:
        commitment.attachments_json = json.dumps(data['attachments'])
    if data.get('aia_contract') is not None:
        commitment.aia_contract_json = json.dumps(data['aia_contract'])


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value).replace('Z', '')).date()
    except (TypeError, ValueError):
        return None


def save_allocations(AllocationModel, commitment_id, allocations, db):
    AllocationModel.query.filter_by(commitment_id=commitment_id).delete()
    total = 0.0
    for item in allocations or []:
        amt = float(item.get('amount') or 0)
        total += amt
        row = AllocationModel(
            commitment_id=commitment_id,
            cost_code=item.get('cost_code'),
            amount=amt,
            description=item.get('description', ''),
        )
        db.session.add(row)
    return total


def compute_dashboard_stats(Commitment, project_id):
    rows = Commitment.query.filter_by(project_id=int(project_id)).all()
    approved = [c for c in rows if c.status == 'Approved']
    pending = [c for c in rows if c.status in PENDING_STATUSES]
    return {
        'total_count': len(rows),
        'approved_count': len(approved),
        'pending_count': len(pending),
        'approved_total': sum(float(c.current_amount or 0) for c in approved),
        'pending_total': sum(float(c.current_amount or 0) for c in pending),
        'committed_total': sum(float(c.current_amount or 0) for c in rows if c.status in ('Approved', 'Partially Invoiced')),
        'remaining_budget_hint': None,
    }


def user_can_act_on_ball_in_court(user, role):
    if not user or not role:
        return False
    if user.role == 'Admin':
        return True
    return user.role in ROLE_APPROVERS.get(role, (role,))


def set_ball_in_court(commitment, status=None):
    status = status or commitment.status
    commitment.ball_in_court_role = BALL_IN_COURT_MAP.get(status, commitment.ball_in_court_role)


def get_next_approval_step(commitment):
    for step in APPROVAL_CHAIN:
        if step['from_status'] == commitment.status:
            return step
    return None


def _resolve_next_status(commitment, default_next):
    amount = float(commitment.current_amount or commitment.original_amount or 0)
    if default_next == 'Pending Owner' and amount < OWNER_APPROVAL_THRESHOLD:
        return 'Approved'
    if default_next == 'Pending Accounting' and commitment.commitment_type == 'Purchase Order' and amount < 25000:
        return 'Approved'
    return default_next


def commitment_workflow_action(commitment, action, user, body=None):
    action = (action or '').lower()
    body = body or {}
    if action == 'submit':
        if commitment.status not in ('Draft',):
            raise ValueError('Only draft commitments can be submitted')
        commitment.status = 'Submitted'
        commitment.approval_stage = 0
        set_ball_in_court(commitment)
        return commitment.status, False

    if action == 'reject':
        commitment.status = 'Rejected'
        commitment.ball_in_court_role = None
        return commitment.status, False

    if action == 'approve':
        role = commitment.ball_in_court_role
        if not user_can_act_on_ball_in_court(user, role):
            raise ValueError(f'Your role cannot approve while ball is with {role}')
        step = get_next_approval_step(commitment)
        if not step:
            raise ValueError('No approval step for current status')
        next_status = _resolve_next_status(commitment, step['next_status'])
        commitment.status = next_status
        commitment.approval_stage = (commitment.approval_stage or 0) + 1
        set_ball_in_court(commitment)
        if next_status == 'Approved':
            commitment.ball_in_court_role = None
            return commitment.status, True
        return commitment.status, False

    if action == 'sign_internal':
        from user_signature_persistence import verify_user_signature_attestation, append_commitment_signature
        sig_hash = (body.get('signature_hash') or '').strip()
        if not body.get('signature_attestation'):
            raise ValueError('Electronic signature attestation is required')
        verify_user_signature_attestation(user, sig_hash)
        append_commitment_signature(commitment, user, method='internal')
        return commitment.status, False

    if action == 'send_docusign':
        commitment.signature_method = 'docusign'
        commitment.signature_status = 'pending_signatures'
        if not commitment.docusign_status:
            commitment.docusign_status = 'pending'
        return commitment.status, False

    if action == 'void':
        if not user or user.role != 'Admin':
            raise ValueError('Only administrators can void commitments')
        if commitment.status == 'Void':
            raise ValueError('Commitment is already void')
        commitment.status = 'Void'
        commitment.ball_in_court_role = None
        return commitment.status, False

    raise ValueError('action must be submit, approve, reject, sign_internal, send_docusign, or void')


def notify_ball_in_court(project_id, commitment, User):
    role = commitment.ball_in_court_role
    if not role:
        return
    try:
        import case_workflow as cw
        action_url = f'/commitments?project_id={project_id}'
        title = f'{commitment.number} — ball in court: {role}'
        description = commitment.description or ''
        users = User.query.filter_by(status='Active').all()
        targets = [u for u in users if user_can_act_on_ball_in_court(u, role)]
        if not targets:
            targets = cw.find_assignees(project_id, 'Commitments')
        for u in targets:
            cw.notify_user(u.id, title, description, action_url)
            cw.create_internal_message(
                u.id,
                folder='action-required',
                msg_type='alert',
                subject=title,
                preview=description[:500],
                body=f'<p>{description}</p><p><strong>Amount:</strong> ${float(commitment.current_amount or 0):,.2f}</p>',
                project_id=project_id,
                from_label='Commitments',
                module='Commitments',
                action_url=action_url,
                action_label='Review Commitment',
                priority='high',
                requires_action=True,
            )
    except Exception:
        pass


def normalize_cost_code(code):
    if not code:
        return ''
    return str(code).replace(' ', '').replace('-', '').upper()


def sync_commitment_to_budget(BudgetProjectState, db, commitment, allocations, user_id=None):
    from budget_persistence import get_budget_state, save_budget_state

    _, state = get_budget_state(BudgetProjectState, commitment.project_id)
    lines = state.get('budgetLines') or []
    if not isinstance(lines, list):
        lines = []

    applied = 0.0
    for alloc in allocations:
        code = alloc.cost_code
        amt = float(alloc.amount or 0)
        if not code or not amt:
            continue
        target = normalize_cost_code(code)
        line = next((l for l in lines if normalize_cost_code(l.get('cost_code')) == target), None)
        if line:
            line['committed'] = float(line.get('committed') or 0) + amt
        else:
            lines.append({
                'id': int(datetime.utcnow().timestamp() * 1000),
                'cost_code': code,
                'description': alloc.description or f'Commitment — {code}',
                'cost_type': 'Subcontract' if commitment.commitment_type == 'Subcontract' else 'Material',
                'original_budget': 0,
                'approved_changes': 0,
                'pending': 0,
                'committed': amt,
                'actual': 0,
                'syncStatus': 'Pending',
                'percent_complete': 0,
                'notes': f'From commitment {commitment.number}',
            })
        applied += amt

    state['budgetLines'] = lines
    save_budget_state(BudgetProjectState, db, commitment.project_id, state, user_id)
    commitment.budget_validated = True
    return {'budget_amount_applied': applied, 'lines_updated': len(allocations or [])}


def sync_commitment_to_sub_sov(PayAppProjectState, db, commitment, allocations, user_id=None):
    """Seed subcontractor SOV from approved subcontract commitment."""
    if commitment.commitment_type != 'Subcontract':
        return {'skipped': True, 'reason': 'not_subcontract'}
    company_key = str(commitment.company_id) if commitment.company_id else str(commitment.company_name or '')
    if not company_key:
        return {'skipped': True, 'reason': 'no_company'}

    record = PayAppProjectState.query.filter_by(project_id=commitment.project_id).first()
    state = _parse_json(record.data_json if record else None, {})
    sub_sov = state.get('subcontractorSOV') or {}
    if not isinstance(sub_sov, dict):
        sub_sov = {}

    lines = sub_sov.get(company_key) or []
    existing_codes = {normalize_cost_code(l.get('cost_code')) for l in lines}
    added = 0
    for alloc in allocations or []:
        code = alloc.cost_code
        if not code:
            continue
        if normalize_cost_code(code) in existing_codes:
            for line in lines:
                if normalize_cost_code(line.get('cost_code')) == normalize_cost_code(code):
                    line['original_commitment'] = float(line.get('original_commitment') or 0) + float(alloc.amount or 0)
            continue
        lines.append({
            'id': f'com-{commitment.id}-{code}',
            'cost_code': code,
            'description': alloc.description or commitment.description,
            'original_commitment': float(alloc.amount or 0),
            'change_orders': 0,
            'scheduled_value': float(alloc.amount or 0),
            'from_commitment': commitment.number,
        })
        added += 1

    sub_sov[company_key] = lines
    state['subcontractorSOV'] = sub_sov
    payload = json.dumps(state)
    if record:
        record.data_json = payload
        record.version = (record.version or 0) + 1
        record.updated_by_id = user_id
        record.updated_at = datetime.utcnow()
    else:
        record = PayAppProjectState(project_id=commitment.project_id, data_json=payload, version=1, updated_by_id=user_id)
        db.session.add(record)
    return {'company_key': company_key, 'lines_added': added, 'total_lines': len(lines)}


def build_commitment_sage_payload(commitment, allocations=None, extra=None):
    """Full Sage 300 CRE payload for commitment sync (AP / Subcontracts modules)."""
    allocs = allocations or []
    extra = extra or {}
    return {
        'commitment_id': commitment.id,
        'number': commitment.number,
        'title': getattr(commitment, 'title', None) or commitment.description,
        'description': commitment.description,
        'commitment_type': commitment.commitment_type,
        'status': commitment.status,
        'aia_form': getattr(commitment, 'aia_form', None),
        'billing_type': getattr(commitment, 'billing_type', None),
        'vendor': {
            'company_id': getattr(commitment, 'company_id', None),
            'company_name': commitment.company_name,
            'contact_name': getattr(commitment, 'contact_name', None),
            'contact_email': getattr(commitment, 'contact_email', None),
            'contact_phone': getattr(commitment, 'contact_phone', None),
            'sage_vendor_code': extra.get('sage_vendor_code'),
        },
        'amounts': {
            'original': float(commitment.original_amount or 0),
            'approved_changes': float(commitment.approved_changes or 0),
            'current': float(commitment.current_amount or 0),
            'retainage_percent': float(getattr(commitment, 'retainage_percent', 0) or 0),
            'invoiced': float(getattr(commitment, 'invoiced_amount', 0) or 0),
        },
        'dates': {
            'contract': commitment.date.isoformat() if commitment.date else None,
            'start': commitment.start_date.isoformat() if getattr(commitment, 'start_date', None) else None,
            'end': commitment.end_date.isoformat() if getattr(commitment, 'end_date', None) else None,
            'delivery': commitment.delivery_date.isoformat() if getattr(commitment, 'delivery_date', None) else None,
            'executed': commitment.executed_date.isoformat() if getattr(commitment, 'executed_date', None) else None,
        },
        'payment_terms': getattr(commitment, 'payment_terms', None),
        'freight_terms': getattr(commitment, 'freight_terms', None),
        'tax_exempt': bool(getattr(commitment, 'tax_exempt', False)),
        'bond_required': bool(getattr(commitment, 'bond_required', False)),
        'allocations': [
            {
                'cost_code': a.cost_code if hasattr(a, 'cost_code') else a.get('cost_code'),
                'amount': float(a.amount if hasattr(a, 'amount') else a.get('amount') or 0),
                'description': getattr(a, 'description', None) or (a.get('description') if isinstance(a, dict) else ''),
            }
            for a in allocs
        ],
        'external_document': {
            'provider': getattr(commitment, 'external_document_provider', None),
            'id': getattr(commitment, 'external_document_id', None),
            'url': getattr(commitment, 'external_document_url', None),
        },
        **{k: v for k, v in extra.items() if k != 'sage_vendor_code'},
    }


def validate_budget_headroom(BudgetProjectState, project_id, allocations):
    from budget_persistence import get_budget_state

    _, state = get_budget_state(BudgetProjectState, project_id)
    lines = state.get('budgetLines') or []
    warnings = []
    for alloc in allocations or []:
        code = alloc.cost_code if hasattr(alloc, 'cost_code') else alloc.get('cost_code')
        amt = float(alloc.amount if hasattr(alloc, 'amount') else alloc.get('amount') or 0)
        if not code:
            continue
        target = normalize_cost_code(code)
        line = next((l for l in lines if normalize_cost_code(l.get('cost_code')) == target), None)
        if not line:
            warnings.append(f'{code}: no budget line — commitment will create committed amount')
            continue
        budget_cap = float(line.get('original_budget') or 0) + float(line.get('approved_changes') or 0)
        committed = float(line.get('committed') or 0) + amt
        if budget_cap and committed > budget_cap * 1.05:
            warnings.append(f'{code}: commitment exceeds budget by ${committed - budget_cap:,.0f}')
    return warnings
