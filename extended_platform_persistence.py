"""Extended platform modules — transmittals, correspondence, T&M, timesheets, WIP, and more."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

# All extended module keys (22 competitive-gap features)
MODULE_KEYS = (
    'transmittals',
    'correspondence',
    'tm_tickets',
    'timesheets',
    'prequalification',
    'vendor_invoices',
    'prime_contracts',
    'direct_costs',
    'specifications',
    'custom_forms',
    'action_plans',
    'crew_planning',
    'materials_tracking',
    'opportunities',
    'certified_payroll',
    'payment_batches',
    'report_definitions',
    'ai_insights',
    'bim_models',
    'client_portal_items',
    'equipment_fleet',
    'lookahead_plans',
    'quality_itp',
    'quality_ncr',
    'quality_hold_points',
)

MODULE_LABELS = {
    'transmittals': 'Transmittals',
    'correspondence': 'Correspondence',
    'tm_tickets': 'T&M Tickets',
    'timesheets': 'Timesheets',
    'prequalification': 'Vendor Prequalification',
    'vendor_invoices': 'Vendor Invoices',
    'prime_contracts': 'Prime Contracts',
    'direct_costs': 'Direct Costs',
    'specifications': 'Specifications',
    'custom_forms': 'Custom Forms',
    'action_plans': 'Action Plans',
    'crew_planning': 'Crew Planning',
    'materials_tracking': 'Materials Tracking',
    'opportunities': 'Opportunities / CRM',
    'certified_payroll': 'Certified Payroll',
    'payment_batches': 'Payment Processing',
    'report_definitions': 'Report Builder',
    'ai_insights': 'AI Assistant',
    'bim_models': 'BIM / 3D Models',
    'client_portal_items': 'Client Portal+',
    'equipment_fleet': 'Equipment Fleet',
    'lookahead_plans': 'Look-Ahead Plans',
    'quality_itp': 'Inspection & Test Plans',
    'quality_ncr': 'Non-Conformance Reports',
    'quality_hold_points': 'Quality Hold Points',
}

MODULE_CATEGORIES = {
    'field': {
        'label': 'Field Operations',
        'icon': 'fa-hard-hat',
        'modules': ('tm_tickets', 'timesheets', 'action_plans', 'materials_tracking', 'crew_planning', 'equipment_fleet', 'lookahead_plans'),
    },
    'communications': {
        'label': 'Communications',
        'icon': 'fa-envelope-open-text',
        'modules': ('transmittals', 'correspondence'),
    },
    'financial': {
        'label': 'Financial Plus',
        'icon': 'fa-chart-line',
        'modules': ('wip_snapshot', 'direct_costs', 'prime_contracts', 'vendor_invoices', 'certified_payroll', 'payment_batches'),
    },
    'precon': {
        'label': 'Precon & Vendors',
        'icon': 'fa-compass-drafting',
        'modules': ('opportunities', 'prequalification', 'specifications', 'custom_forms'),
    },
    'insights': {
        'label': 'Insights & AI',
        'icon': 'fa-wand-magic-sparkles',
        'modules': ('report_definitions', 'ai_insights', 'bim_models'),
    },
    'client': {
        'label': 'Client Experience',
        'icon': 'fa-house-user',
        'modules': ('client_portal_items',),
    },
    'quality': {
        'label': 'Quality Programs',
        'icon': 'fa-clipboard-list',
        'modules': ('quality_itp', 'quality_ncr', 'quality_hold_points'),
    },
}

# Simple defaults: 3 fields shown first; advanced fields hidden until expanded.
MODULE_SCHEMAS = {
    'transmittals': {
        'simple': [('title', 'Subject', 'text'), ('to_party', 'To', 'text'), ('due_date', 'Response Due', 'date')],
        'advanced': [
            ('number', 'Transmittal #', 'text'), ('cc_party', 'CC', 'text'),
            ('distribution_list', 'Distribution List (name <email>, comma-separated)', 'textarea'),
            ('attachment_ids', 'Document IDs to include in PDF package (comma-separated)', 'text'),
            ('purpose', 'Purpose', 'select',
             ['For Review', 'For Approval', 'For Information', 'As Requested']),
            ('required_action', 'Required Action', 'textarea'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Sent', 'Acknowledged', 'Closed'),
        'project_scoped': True,
    },
    'correspondence': {
        'simple': [('title', 'Subject', 'text'), ('corr_type', 'Type', 'select',
                    ['General', 'Notice of Delay', 'EOT Request', 'ASI', 'Bulletin', 'Letter']),
                   ('due_date', 'Due Date', 'date')],
        'advanced': [
            ('number', 'Reference #', 'text'), ('from_party', 'From', 'text'), ('to_party', 'To', 'text'),
            ('body', 'Body', 'textarea'), ('linked_rfi_id', 'Link RFI ID', 'number'),
            ('linked_change_event_id', 'Link Change Event ID', 'number'),
        ],
        'statuses': ('Draft', 'Open', 'Pending Review', 'Closed'),
        'project_scoped': True,
    },
    'tm_tickets': {
        'simple': [('title', 'Description', 'text'), ('work_date', 'Work Date', 'date'), ('amount', 'Est. Amount', 'number')],
        'advanced': [
            ('number', 'Ticket #', 'text'), ('labor_hours', 'Labor Hours', 'number'),
            ('equipment', 'Equipment', 'text'), ('materials', 'Materials', 'textarea'),
            ('signed_by', 'Signed By', 'text'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Submitted', 'Approved', 'Billed', 'Void'),
        'project_scoped': True,
    },
    'timesheets': {
        'simple': [('title', 'Crew / Description', 'text'), ('work_date', 'Week Ending', 'date'), ('total_hours', 'Total Hours', 'number')],
        'advanced': [
            ('number', 'Timesheet #', 'text'), ('cost_code', 'Cost Code', 'text'),
            ('hourly_rate', 'Burdened Hourly Rate ($)', 'number'),
            ('crew_members', 'Crew Members', 'textarea'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Submitted', 'Approved', 'Posted'),
        'project_scoped': True,
    },
    'prequalification': {
        'simple': [('title', 'Vendor Name', 'text'), ('review_date', 'Review Date', 'date'), ('score', 'Score', 'number')],
        'advanced': [
            ('number', 'Application #', 'text'), ('emr_rate', 'EMR Rate', 'number'),
            ('safety_rating', 'Safety Rating', 'text'), ('financial_rating', 'Financial Rating', 'text'),
            ('coi_expiry', 'COI Expiry', 'date'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Under Review', 'Approved', 'Rejected', 'Expired'),
        'project_scoped': False,
    },
    'vendor_invoices': {
        'simple': [('title', 'Invoice #', 'text'), ('amount', 'Amount', 'number'), ('invoice_date', 'Invoice Date', 'date')],
        'advanced': [
            ('vendor_name', 'Vendor', 'text'), ('commitment_ref', 'Commitment #', 'text'),
            ('sov_line', 'SOV Line', 'text'), ('retainage', 'Retainage %', 'number'),
            ('variance_notes', 'Variance Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Pending Review', 'Approved', 'Paid', 'Rejected'),
        'project_scoped': True,
    },
    'prime_contracts': {
        'simple': [('title', 'Contract Title', 'text'), ('amount', 'Contract Value', 'number'), ('contract_date', 'Contract Date', 'date')],
        'advanced': [
            ('number', 'Contract #', 'text'), ('owner_name', 'Owner', 'text'),
            ('retainage_percent', 'Retainage %', 'number'), ('substantial_completion', 'Substantial Completion', 'date'),
            ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Active', 'Amended', 'Closed'),
        'project_scoped': True,
    },
    'direct_costs': {
        'simple': [('title', 'Description', 'text'), ('amount', 'Amount', 'number'), ('cost_date', 'Date', 'date')],
        'advanced': [
            ('number', 'Reference #', 'text'), ('cost_code', 'Cost Code', 'text'),
            ('cost_type', 'Cost Type', 'text'), ('vendor_name', 'Vendor', 'text'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Posted', 'Void'),
        'project_scoped': True,
    },
    'specifications': {
        'simple': [('title', 'Section Title', 'text'), ('section', 'Division / Section', 'text'), ('revision', 'Revision', 'text')],
        'advanced': [
            ('number', 'Spec #', 'text'), ('description', 'Description', 'textarea'),
            ('linked_submittal', 'Linked Submittal', 'text'),
        ],
        'statuses': ('Current', 'Superseded', 'Draft'),
        'project_scoped': True,
    },
    'custom_forms': {
        'simple': [('title', 'Form Name', 'text'), ('form_type', 'Type', 'select', ['Checklist', 'QA', 'Safety', 'Closeout', 'Other']),
                   ('due_date', 'Due Date', 'date')],
        'advanced': [
            ('number', 'Form #', 'text'), ('assigned_to', 'Assigned To', 'text'),
            ('fields_json', 'Custom Fields (JSON)', 'textarea'),
        ],
        'statuses': ('Draft', 'In Progress', 'Complete', 'Void'),
        'project_scoped': True,
    },
    'action_plans': {
        'simple': [('title', 'Action', 'text'), ('assigned_to', 'Assigned To', 'text'), ('due_date', 'Due Date', 'date')],
        'advanced': [
            ('number', 'Plan #', 'text'), ('category', 'Category', 'select', ['Quality', 'Safety', 'Closeout', 'Other']),
            ('verification', 'Verification Steps', 'textarea'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Open', 'In Progress', 'Verified', 'Closed'),
        'project_scoped': True,
    },
    'crew_planning': {
        'simple': [('title', 'Crew Name', 'text'), ('work_date', 'Date', 'date'), ('headcount', 'Headcount', 'number')],
        'advanced': [
            ('number', 'Assignment #', 'text'), ('trade', 'Trade', 'text'),
            ('location', 'Location', 'text'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Planned', 'On Site', 'Complete', 'Cancelled'),
        'project_scoped': True,
    },
    'materials_tracking': {
        'simple': [('title', 'Material', 'text'), ('quantity', 'Quantity', 'text'), ('status', 'Status', 'select',
                    ['Ordered', 'Shipped', 'On Site', 'Installed'])],
        'advanced': [
            ('number', 'Tracking #', 'text'), ('supplier', 'Supplier', 'text'),
            ('po_number', 'PO #', 'text'), ('delivery_date', 'Expected Delivery', 'date'),
            ('location', 'Location', 'text'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Ordered', 'Shipped', 'On Site', 'Installed', 'Delayed'),
        'project_scoped': True,
    },
    'opportunities': {
        'simple': [('title', 'Opportunity Name', 'text'), ('amount', 'Est. Value', 'number'), ('bid_date', 'Bid Date', 'date')],
        'advanced': [
            ('number', 'Lead #', 'text'), ('client_name', 'Client', 'text'),
            ('probability', 'Win %', 'number'), ('stage', 'Stage', 'select',
             ['Lead', 'Qualifying', 'Estimating', 'Submitted', 'Awarded', 'Lost']),
            ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Lead', 'Active', 'Submitted', 'Won', 'Lost'),
        'project_scoped': False,
    },
    'certified_payroll': {
        'simple': [('title', 'Payroll Period', 'text'), ('work_date', 'Week Ending', 'date'), ('total_hours', 'Total Hours', 'number')],
        'advanced': [
            ('number', 'WH-347 #', 'text'), ('contractor_name', 'Contractor', 'text'),
            ('workers_json', 'Workers JSON [{name, classification, hours, gross_pay}]', 'textarea'),
            ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Submitted', 'Approved', 'Filed'),
        'project_scoped': True,
    },
    'payment_batches': {
        'simple': [('title', 'Batch Name', 'text'), ('amount', 'Total Amount', 'number'), ('payment_date', 'Payment Date', 'date')],
        'advanced': [
            ('number', 'Batch #', 'text'), ('payment_method', 'Method', 'select', ['ACH', 'Check', 'Wire']),
            ('invoice_ids', 'Vendor Invoice IDs (comma-separated)', 'text'),
            ('lien_waiver_status', 'Lien Waivers', 'text'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Pending', 'Processed', 'Void'),
        'project_scoped': True,
    },
    'report_definitions': {
        'simple': [('title', 'Report Name', 'text'), ('report_type', 'Category', 'select',
                    ['Financial', 'Field', 'Safety', 'Custom']), ('schedule', 'Schedule', 'select',
                    ['On Demand', 'Weekly', 'Monthly'])],
        'advanced': [
            ('data_source', 'Data Source', 'select',
             ['operations', 'projects', 'commitments', 'rfis', 'change_orders', 'punch']),
            ('number', 'Report #', 'text'),
            ('filters_json', 'Filters JSON e.g. {"status":"Open"}', 'textarea'),
            ('columns_json', 'Columns JSON (optional override)', 'textarea'),
        ],
        'statuses': ('Draft', 'Active', 'Archived'),
        'project_scoped': False,
    },
    'ai_insights': {
        'simple': [('title', 'Question / Topic', 'text'), ('work_date', 'Date', 'date')],
        'advanced': [
            ('prompt', 'Full Prompt', 'textarea'), ('response', 'AI Response', 'textarea'),
            ('context_module', 'Context Module', 'text'),
        ],
        'statuses': ('New', 'Answered', 'Archived'),
        'project_scoped': True,
    },
    'bim_models': {
        'simple': [('title', 'Model Name', 'text'), ('revision', 'Revision', 'text'), ('work_date', 'Upload Date', 'date')],
        'advanced': [
            ('number', 'Model #', 'text'), ('file_ref', 'File Reference', 'text'),
            ('discipline', 'Discipline', 'text'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Current', 'Superseded'),
        'project_scoped': True,
    },
    'client_portal_items': {
        'simple': [('title', 'Item', 'text'), ('item_type', 'Type', 'select',
                    ['Update', 'Selection', 'Warranty', 'Payment Request']), ('due_date', 'Due Date', 'date')],
        'advanced': [
            ('number', 'Item #', 'text'), ('client_visible', 'Client Visible', 'select', ['Yes', 'No']),
            ('description', 'Description', 'textarea'), ('amount', 'Amount', 'number'),
        ],
        'statuses': ('Draft', 'Published', 'Approved', 'Closed'),
        'project_scoped': True,
    },
    'equipment_fleet': {
        'simple': [('title', 'Equipment', 'text'), ('equipment_id', 'Asset ID', 'text'), ('status', 'Status', 'select',
                    ['Available', 'On Site', 'Maintenance', 'Retired'])],
        'advanced': [
            ('number', 'Fleet #', 'text'), ('location', 'Current Location', 'text'),
            ('hour_meter', 'Hour Meter', 'number'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Available', 'On Site', 'Maintenance', 'Retired'),
        'project_scoped': False,
    },
    'lookahead_plans': {
        'simple': [('title', 'Week Of', 'text'), ('work_date', 'Start Date', 'date'), ('crew_size', 'Crew Size', 'number')],
        'advanced': [
            ('number', 'Plan #', 'text'), ('activities_json', 'Activities JSON [{task, start, finish, crew}]', 'textarea'),
            ('constraints', 'Constraints / Risks', 'textarea'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Published', 'In Progress', 'Complete'),
        'project_scoped': True,
    },
    'quality_itp': {
        'simple': [('title', 'ITP Name', 'text'), ('work_date', 'Planned Date', 'date'), ('discipline', 'Discipline', 'text')],
        'advanced': [
            ('number', 'ITP #', 'text'), ('spec_section', 'Spec Section', 'text'),
            ('hold_points_json', 'Hold Points JSON', 'textarea'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Draft', 'Active', 'On Hold', 'Closed'),
        'project_scoped': True,
    },
    'quality_ncr': {
        'simple': [('title', 'NCR Description', 'text'), ('work_date', 'Date Found', 'date'), ('severity', 'Severity', 'select', ['Minor', 'Major', 'Critical'])],
        'advanced': [
            ('number', 'NCR #', 'text'), ('location', 'Location', 'text'),
            ('root_cause', 'Root Cause', 'textarea'), ('corrective_action', 'Corrective Action', 'textarea'),
        ],
        'statuses': ('Open', 'Under Review', 'Corrective Action', 'Closed'),
        'project_scoped': True,
    },
    'quality_hold_points': {
        'simple': [('title', 'Hold Point', 'text'), ('work_date', 'Scheduled', 'date'), ('inspector', 'Inspector', 'text')],
        'advanced': [
            ('number', 'HP #', 'text'), ('trade', 'Trade', 'text'),
            ('checklist_json', 'Checklist JSON', 'textarea'), ('notes', 'Notes', 'textarea'),
        ],
        'statuses': ('Pending', 'Ready', 'Inspected', 'Released', 'Failed'),
        'project_scoped': True,
    },
}


def _parse_json(raw, default=None):
    if default is None:
        default = {}
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _d(dt):
    if not dt:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt.isoformat()
    return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)


def catalog_for_ui():
    """Module catalog for the Operations Center hub."""
    cats = []
    for cat_id, cat in MODULE_CATEGORIES.items():
        mods = []
        for key in cat['modules']:
            if key == 'wip_snapshot':
                mods.append({
                    'key': 'wip_snapshot',
                    'label': 'WIP Report',
                    'simple_fields': [],
                    'advanced_fields': [],
                    'statuses': [],
                    'project_scoped': True,
                    'read_only': True,
                })
                continue
            schema = MODULE_SCHEMAS.get(key, {})
            mods.append({
                'key': key,
                'label': MODULE_LABELS.get(key, key),
                'simple_fields': schema.get('simple', []),
                'advanced_fields': schema.get('advanced', []),
                'statuses': list(schema.get('statuses', ('Draft',))),
                'project_scoped': schema.get('project_scoped', True),
                'read_only': False,
            })
        cats.append({
            'id': cat_id,
            'label': cat['label'],
            'icon': cat['icon'],
            'modules': mods,
        })
    return cats


def serialize_record(row):
    simple = _parse_json(row.simple_fields_json)
    advanced = _parse_json(row.advanced_fields_json)
    return {
        'id': row.id,
        'module_key': row.module_key,
        'project_id': row.project_id,
        'company_id': row.company_id,
        'number': row.number,
        'title': row.title,
        'status': row.status or 'Draft',
        'record_date': _d(row.record_date),
        'amount': float(row.amount or 0),
        'simple': simple,
        'advanced': advanced,
        'created_at': _d(row.created_at),
        'updated_at': _d(row.updated_at),
    }


def apply_payload(row, body, module_key):
    schema = MODULE_SCHEMAS.get(module_key, {})
    simple = _parse_json(row.simple_fields_json)
    advanced = _parse_json(row.advanced_fields_json)
    simple_in = body.get('simple') or {}
    advanced_in = body.get('advanced') or {}
    if isinstance(simple_in, dict):
        simple.update(simple_in)
    if isinstance(advanced_in, dict):
        advanced.update(advanced_in)
    if body.get('title') is not None:
        row.title = (body.get('title') or '').strip() or row.title
    if body.get('number') is not None:
        row.number = (body.get('number') or '').strip() or None
    if body.get('status') is not None:
        row.status = (body.get('status') or 'Draft').strip()
    if body.get('amount') is not None:
        try:
            row.amount = float(body.get('amount') or 0)
        except (TypeError, ValueError):
            pass
    if body.get('record_date'):
        try:
            row.record_date = datetime.strptime(str(body['record_date'])[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    # Mirror top-level simple fields onto row columns for list sorting
    for field_key, _, _ftype in schema.get('simple', []):
        if field_key in simple_in:
            val = simple_in[field_key]
            if field_key.endswith('_date') or field_key in ('work_date', 'due_date', 'invoice_date', 'cost_date', 'bid_date', 'payment_date'):
                if val:
                    try:
                        row.record_date = datetime.strptime(str(val)[:10], '%Y-%m-%d').date()
                    except ValueError:
                        pass
            if field_key == 'amount' and val not in (None, ''):
                try:
                    row.amount = float(val)
                except (TypeError, ValueError):
                    pass
    row.simple_fields_json = json.dumps(simple)
    row.advanced_fields_json = json.dumps(advanced)
    return row


def compute_stats(ExtendedModuleRecord, module_key, project_id=None, company_id=None):
    q = ExtendedModuleRecord.query.filter_by(module_key=module_key)
    if project_id:
        q = q.filter_by(project_id=int(project_id))
    if company_id:
        q = q.filter_by(company_id=int(company_id))
    rows = q.all()
    open_statuses = {'Draft', 'Open', 'Submitted', 'Pending Review', 'In Progress', 'Planned', 'Active', 'New', 'Lead'}
    return {
        'total': len(rows),
        'open': sum(1 for r in rows if (r.status or '') in open_statuses),
        'closed': sum(1 for r in rows if (r.status or '') in ('Closed', 'Approved', 'Paid', 'Complete', 'Posted', 'Won', 'Filed', 'Processed', 'Archived')),
    }


def validate_vendor_invoice(row, Commitment, CommitmentAllocation, project_id):
    """Compare vendor invoice amount against commitment SOV (RedTeam-style validation)."""
    adv = _parse_json(row.advanced_fields_json)
    commitment_ref = (adv.get('commitment_ref') or '').strip()
    amount = float(row.amount or 0)
    result = {
        'valid': True,
        'invoice_amount': amount,
        'commitment_ref': commitment_ref,
        'commitment_amount': 0,
        'billed_to_date': 0,
        'remaining': 0,
        'variance': 0,
        'messages': [],
    }
    if not commitment_ref:
        result['messages'].append('No commitment linked — manual review required.')
        return result
    com = Commitment.query.filter_by(project_id=int(project_id), number=commitment_ref).first()
    if not com:
        result['valid'] = False
        result['messages'].append(f'Commitment {commitment_ref} not found.')
        return result
    result['commitment_amount'] = float(com.current_amount or com.original_amount or 0)
    allocs = CommitmentAllocation.query.filter_by(commitment_id=com.id).all()
    sov_line = (adv.get('sov_line') or '').strip()
    if sov_line and allocs:
        match = next((a for a in allocs if (a.cost_code or '') == sov_line), None)
        if match:
            line_cap = float(match.amount or 0)
            result['remaining'] = line_cap
            if amount > line_cap * 1.05:
                result['valid'] = False
                result['variance'] = amount - line_cap
                result['messages'].append(f'Invoice exceeds SOV line {sov_line} by ${result["variance"]:,.2f}.')
            else:
                result['messages'].append(f'Within SOV line {sov_line} cap (${line_cap:,.2f}).')
            return result
    remaining = result['commitment_amount'] - float(com.invoiced_amount or 0)
    result['billed_to_date'] = float(com.invoiced_amount or 0)
    result['remaining'] = remaining
    if amount > remaining * 1.02:
        result['valid'] = False
        result['variance'] = amount - remaining
        result['messages'].append(f'Invoice exceeds remaining commitment by ${result["variance"]:,.2f}.')
    else:
        result['messages'].append(f'Within commitment remaining (${remaining:,.2f}).')
    return result


def build_wip_snapshot(Project, BudgetProjectState, Commitment, ChangeOrder, PayAppProjectState, project_id):
    """Live WIP-style financial snapshot per project."""
    from budget_persistence import get_budget_state
    from pay_app_persistence import get_pay_app_state

    project = Project.query.get(int(project_id))
    if not project:
        return None
    contract = float(project.contract_value or 0)
    _, budget = get_budget_state(BudgetProjectState, project_id)
    lines = budget.get('budgetLines') or []
    committed = sum(float(l.get('committed') or 0) for l in lines)
    actual = sum(float(l.get('actual') or 0) for l in lines)
    approved_co = sum(float(l.get('approved_changes') or 0) for l in lines)
    revised = contract + approved_co
    _, pay_state = get_pay_app_state(PayAppProjectState, project_id)
    period = pay_state.get('currentPayAppPeriod') or {}
    billed = float(period.get('totalBilledThisPeriod') or 0)
    pct_complete = (actual / revised) if revised else 0
    earned = revised * pct_complete
    over_under = billed - earned
    cos = ChangeOrder.query.filter_by(project_id=int(project_id), status='Approved').all()
    owner_co_total = sum(float(c.amount or 0) for c in cos if getattr(c, 'contract_type', 'Owner') != 'Subcontract')
    subs = Commitment.query.filter_by(project_id=int(project_id), commitment_type='Subcontract').all()
    sub_committed = sum(float(c.current_amount or 0) for c in subs)
    return {
        'project_id': int(project_id),
        'project_name': project.name,
        'original_contract': contract,
        'approved_changes': approved_co,
        'revised_contract': revised,
        'committed': committed,
        'actual_cost': actual,
        'percent_complete': round(pct_complete * 100, 1),
        'earned_revenue': round(earned, 2),
        'billed_to_date': round(billed, 2),
        'over_under_billing': round(over_under, 2),
        'gross_profit_pct': round(((revised - actual) / revised * 100) if revised else 0, 1),
        'owner_co_approved': owner_co_total,
        'sub_committed': sub_committed,
        'as_of': datetime.utcnow().isoformat() + 'Z',
    }


def build_portfolio_wip(Project, BudgetProjectState, Commitment, ChangeOrder, PayAppProjectState):
    projects = Project.query.filter(Project.status.in_(['Active', 'Pre-Construction'])).all()
    rows = []
    for p in projects:
        snap = build_wip_snapshot(Project, BudgetProjectState, Commitment, ChangeOrder, PayAppProjectState, p.id)
        if snap:
            rows.append(snap)
    totals = {
        'revised_contract': sum(r['revised_contract'] for r in rows),
        'actual_cost': sum(r['actual_cost'] for r in rows),
        'billed_to_date': sum(r['billed_to_date'] for r in rows),
        'over_under_billing': sum(r['over_under_billing'] for r in rows),
    }
    return {'projects': rows, 'totals': totals, 'as_of': datetime.utcnow().isoformat() + 'Z'}


def generate_ai_insight(project_id, module_key, question, Project, ExtendedModuleRecord, RFI, ChangeOrder):
    """Lightweight on-platform AI assistant — summarizes project context without external API."""
    project = Project.query.get(int(project_id)) if project_id else None
    open_rfis = RFI.query.filter_by(project_id=int(project_id)).filter(RFI.status.in_(['Open', 'Awaiting Response', 'Under Review'])).count() if project_id and RFI else 0
    pending_cos = ChangeOrder.query.filter_by(project_id=int(project_id)).filter(ChangeOrder.status.in_(['Submitted', 'Under Review', 'Pending Owner', 'Pending Architect', 'Pending Accounting'])).count() if project_id and ChangeOrder else 0
    recent = []
    if project_id:
        recent = ExtendedModuleRecord.query.filter_by(project_id=int(project_id)).order_by(ExtendedModuleRecord.updated_at.desc()).limit(5).all()
    lines = [
        f'**Project:** {project.name if project else "Portfolio"}',
        f'**Question:** {question or "General status"}',
        '',
        '**Quick snapshot**',
        f'- Open RFIs: {open_rfis}',
        f'- Pending change orders: {pending_cos}',
    ]
    if recent:
        lines.append('- Recent operations items:')
        for r in recent:
            lines.append(f'  - {MODULE_LABELS.get(r.module_key, r.module_key)}: {r.title or r.number or r.id} ({r.status})')
    lines.extend([
        '',
        '**Suggested next steps**',
        '1. Review open RFIs and correspondence for schedule risk.',
        '2. Check WIP over/under billing before the next pay period.',
        '3. Validate vendor invoices against commitment SOV before approval.',
    ])
    if module_key == 'tm_tickets':
        lines.append('4. Promote approved T&M tickets to a change event.')
    elif module_key == 'timesheets':
        lines.append('4. Post approved timesheets to job cost actuals.')
    return '\n'.join(lines)


def promote_correspondence_to_rfi(record, RFI, db, project_id, user_id, generate_number_fn):
    """Promote correspondence to RFI (Procore-style)."""
    adv = _parse_json(record.advanced_fields_json)
    rfi = RFI(
        project_id=int(project_id),
        number=generate_number_fn('RFI', RFI, doc_type='rfi', project_id=project_id),
        subject=record.title or 'From correspondence',
        question=adv.get('body') or record.title or '',
        status='Draft',
        date=date.today(),
        created_by_id=user_id,
        ball_in_court_role='RFI Manager',
    )
    db.session.add(rfi)
    db.session.flush()
    adv['linked_rfi_id'] = rfi.id
    record.advanced_fields_json = json.dumps(adv)
    record.status = 'Closed'
    return rfi


def promote_tm_to_change_event(record, ChangeEvent, db, project_id, user_id):
    """Promote T&M ticket to change event."""
    ce = ChangeEvent(
        project_id=int(project_id),
        number=f'CE-TM-{record.id}',
        title=f'T&M: {record.title or record.number}',
        status='Open',
        rom_amount=float(record.amount or 0),
        created_by_id=user_id,
        ball_in_court_role='Project Manager',
    )
    db.session.add(ce)
    db.session.flush()
    adv = _parse_json(record.advanced_fields_json)
    adv['linked_change_event_id'] = ce.id
    record.advanced_fields_json = json.dumps(adv)
    record.status = 'Approved'
    return ce
