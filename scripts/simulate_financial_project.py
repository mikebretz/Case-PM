#!/usr/bin/env python3
"""
Full financial lifecycle simulation — $30M commercial project(s).
Run: python3 scripts/simulate_financial_project.py
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

# removed unused SimpleNamespace users — real DB users via _ensure_sim_users

# Trade mix (% of $30M contract) — typical retail/commercial shell + fit-out
TRADE_MIX_A = [
    ('03-300', 'Concrete', 0.08, 'Subcontract'),
    ('04-200', 'Masonry', 0.02, 'Subcontract'),
    ('05-120', 'Structural Steel', 0.06, 'Subcontract'),
    ('06-100', 'Rough Carpentry', 0.05, 'Subcontract'),
    ('07-200', 'Insulation/Waterproof', 0.04, 'Subcontract'),
    ('08-100', 'Doors & Frames', 0.03, 'Subcontract'),
    ('09-250', 'Drywall & Finishes', 0.12, 'Subcontract'),
    ('10-100', 'Specialties', 0.02, 'Subcontract'),
    ('11-400', 'Equipment', 0.05, 'Purchase Order'),
    ('15-100', 'Mechanical HVAC', 0.15, 'Subcontract'),
    ('16-100', 'Electrical', 0.12, 'Subcontract'),
    ('22-100', 'Plumbing', 0.08, 'Subcontract'),
    ('21-000', 'Fire Protection', 0.03, 'Subcontract'),
    ('14-200', 'Elevators', 0.02, 'Subcontract'),
    ('01-100', 'General Conditions', 0.10, 'Service Agreement'),
    ('01-200', 'Contingency', 0.03, 'Service Agreement'),
]

# Second project — different mix (hospitality tilt)
TRADE_MIX_B = [
    ('03-300', 'Concrete', 0.07, 'Subcontract'),
    ('05-120', 'Structural Steel', 0.05, 'Subcontract'),
    ('09-900', 'Tile & Stone', 0.08, 'Subcontract'),
    ('09-680', 'Carpeting', 0.04, 'Subcontract'),
    ('09-250', 'Drywall', 0.10, 'Subcontract'),
    ('12-200', 'Furnishings', 0.06, 'Purchase Order'),
    ('15-100', 'Mechanical HVAC', 0.14, 'Subcontract'),
    ('16-100', 'Electrical', 0.11, 'Subcontract'),
    ('22-100', 'Plumbing', 0.07, 'Subcontract'),
    ('21-000', 'Fire Protection', 0.03, 'Subcontract'),
    ('23-000', 'HVAC Controls', 0.04, 'Subcontract'),
    ('26-500', 'Low Voltage', 0.05, 'Subcontract'),
    ('32-900', 'Landscaping', 0.03, 'Subcontract'),
    ('01-100', 'General Conditions', 0.08, 'Service Agreement'),
    ('01-200', 'Contingency', 0.05, 'Service Agreement'),
]

CONTRACT_VALUE = 30_000_000.0
CONTRACT_VALUE_100M = 100_000_000.0
RETAINAGE_PCT = 10.0

# $100M mega campus — expanded trade mix
TRADE_MIX_C = [
    ('03-300', 'Concrete', 0.07, 'Subcontract'),
    ('04-200', 'Masonry', 0.02, 'Subcontract'),
    ('05-120', 'Structural Steel', 0.06, 'Subcontract'),
    ('06-100', 'Rough Carpentry', 0.04, 'Subcontract'),
    ('07-200', 'Insulation/Waterproof', 0.03, 'Subcontract'),
    ('08-100', 'Doors & Frames', 0.03, 'Subcontract'),
    ('08-800', 'Glazing', 0.04, 'Subcontract'),
    ('09-250', 'Drywall & Finishes', 0.09, 'Subcontract'),
    ('09-900', 'Tile & Stone', 0.03, 'Subcontract'),
    ('10-100', 'Specialties', 0.02, 'Subcontract'),
    ('11-400', 'Equipment', 0.04, 'Purchase Order'),
    ('14-200', 'Elevators', 0.03, 'Subcontract'),
    ('15-100', 'Mechanical HVAC', 0.13, 'Subcontract'),
    ('16-100', 'Electrical', 0.11, 'Subcontract'),
    ('22-100', 'Plumbing', 0.07, 'Subcontract'),
    ('21-000', 'Fire Protection', 0.03, 'Subcontract'),
    ('23-000', 'HVAC Controls', 0.03, 'Subcontract'),
    ('26-500', 'Low Voltage', 0.04, 'Subcontract'),
    ('32-900', 'Landscaping', 0.02, 'Subcontract'),
    ('01-100', 'General Conditions', 0.05, 'Service Agreement'),
    ('01-200', 'Contingency', 0.02, 'Service Agreement'),
]


@dataclass
class SimIssue:
    severity: str  # critical, warning, info
    category: str
    message: str
    project: str = ''


@dataclass
class SimResult:
    name: str
    project_id: int
    issues: list[SimIssue] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def add(self, severity, category, message):
        self.issues.append(SimIssue(severity, category, message, self.name))


def _ensure_sim_users(db, User):
    """Use existing DB users or create lightweight sim users for FK-safe workflow."""
    users = {}
    roles = {
        'pm': 'Project Manager',
        'arch': 'Architect',
        'owner': 'Owner',
        'acct': 'Contractor Accounting',
        'sub': 'Subcontractor Accountant',
        'admin': 'Admin',
    }
    for key, role in roles.items():
        u = User.query.filter_by(role=role, status='Active').first()
        if not u:
            email = f'sim.{key}@casepm.test'
            u = User.query.filter_by(email=email).first()
            if not u:
                u = User(
                    first_name='Sim',
                    last_name=role.split()[0],
                    email=email,
                    role=role,
                    status='Active',
                )
                u.set_password('SimTest!12345')
                db.session.add(u)
        users[key] = u
    db.session.commit()
    return users


def _approve_commitment(commitment, CommitmentAllocation, users, app_models):
    from commitment_persistence import commitment_workflow_action, save_allocations
    db = app_models['db']
    Commitment = app_models['Commitment']
    BudgetProjectState = app_models['BudgetProjectState']
    PayAppProjectState = app_models['PayAppProjectState']
    ChangeOrder = app_models['ChangeOrder']
    ChangeOrderAllocation = app_models['ChangeOrderAllocation']
    CommitmentAllocation = app_models['CommitmentAllocation']
    from accounting_reconcile import reconcile_project_accounting

    allocs = CommitmentAllocation.query.filter_by(commitment_id=commitment.id).all()
    commitment_workflow_action(commitment, 'submit', users['pm'])
    db.session.commit()
    actors = [users['pm'], users['acct'], users['owner']]
    for actor in actors:
        if commitment.status == 'Approved':
            break
        if commitment.status == 'Rejected':
            break
        role = commitment.ball_in_court_role
        if role and actor.role in ('Project Manager', 'Admin') and role == 'Project Manager':
            _, final = commitment_workflow_action(commitment, 'approve', actor)
            db.session.commit()
            if final:
                from commitment_persistence import sync_commitment_to_budget, sync_commitment_to_sub_sov
                sync_commitment_to_budget(BudgetProjectState, db, commitment, allocs, None)
                if commitment.commitment_type == 'Subcontract':
                    sync_commitment_to_sub_sov(PayAppProjectState, db, commitment, allocs, None)
                reconcile_project_accounting(
                    commitment.project_id, None,
                    ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                    Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                    BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState, db=db,
                )
        elif role == 'Contractor Accounting' and actor.role in ('Contractor Accounting', 'Admin'):
            _, final = commitment_workflow_action(commitment, 'approve', actor)
            db.session.commit()
            if final:
                from commitment_persistence import sync_commitment_to_budget, sync_commitment_to_sub_sov
                sync_commitment_to_budget(BudgetProjectState, db, commitment, allocs, None)
                if commitment.commitment_type == 'Subcontract':
                    sync_commitment_to_sub_sov(PayAppProjectState, db, commitment, allocs, None)
                reconcile_project_accounting(
                    commitment.project_id, None,
                    ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                    Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                    BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState, db=db,
                )
        elif role == 'Owner' and actor.role in ('Owner', 'Admin'):
            _, final = commitment_workflow_action(commitment, 'approve', actor)
            db.session.commit()
            if final:
                from commitment_persistence import sync_commitment_to_budget, sync_commitment_to_sub_sov
                sync_commitment_to_budget(BudgetProjectState, db, commitment, allocs, None)
                if commitment.commitment_type == 'Subcontract':
                    sync_commitment_to_sub_sov(PayAppProjectState, db, commitment, allocs, None)
                reconcile_project_accounting(
                    commitment.project_id, None,
                    ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                    Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
                    BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState, db=db,
                )
    return commitment.status


def _approve_owner_co(co, users, app_models):
    from co_persistence import process_change_order_workflow
    db = app_models['db']
    body_submit = {'comments': 'Sim submit'}
    process_change_order_workflow(
        co, 'submit', users['pm'], None, body_submit,
        ChangeOrder=app_models['ChangeOrder'],
        ChangeOrderAllocation=app_models['ChangeOrderAllocation'],
        PayAppProjectState=app_models['PayAppProjectState'],
        ScheduleData=app_models.get('ScheduleData'),
        Project=app_models['Project'],
        BudgetProjectState=app_models['BudgetProjectState'],
        db=db, Commitment=app_models['Commitment'],
        CommitmentAllocation=app_models['CommitmentAllocation'],
        SageSyncEvent=app_models['SageSyncEvent'],
    )
    db.session.commit()
    chain = [
        (users['pm'], {}),
        (users['arch'], {'signature_attestation': True, 'signature_hash': 'sim-hash', 'skip_signature_verify': True}),
        (users['owner'], {'signature_attestation': True, 'signature_hash': 'sim-hash', 'skip_signature_verify': True}),
        (users['acct'], {}),
    ]
    for actor, extra in chain:
        if co.status == 'Approved':
            break
        body = {'comments': 'Sim approve', **extra}
        try:
            process_change_order_workflow(
                co, 'approve', actor, None, body,
                ChangeOrder=app_models['ChangeOrder'],
                ChangeOrderAllocation=app_models['ChangeOrderAllocation'],
                PayAppProjectState=app_models['PayAppProjectState'],
                ScheduleData=app_models.get('ScheduleData'),
                Project=app_models['Project'],
                BudgetProjectState=app_models['BudgetProjectState'],
                db=db, Commitment=app_models['Commitment'],
                CommitmentAllocation=app_models['CommitmentAllocation'],
                SageSyncEvent=app_models['SageSyncEvent'],
                developer_unlock_bypass=True,
            )
            db.session.commit()
        except Exception as exc:
            msg = str(exc).lower()
            if 'signature' in msg:
                continue
            raise
    return co.status


def _run_extended_modules(result: SimResult, project, users, app_models, commitments):
    """RFIs, submittals, change events, RFQs, CORs, security regression, period 2, Sage review."""
    from change_event_persistence import (
        apply_change_event_fields, change_event_workflow_action,
        rfq_workflow_action, cor_workflow_action, save_generic_allocations,
        accept_sage_event_for_export,
    )
    from rfi_persistence import apply_rfi_fields, workflow_rfi, add_response
    from workflow_responder import execute_rfi_action
    from submittal_persistence import apply_submittal_fields, submittal_workflow_action
    from financial_security import strip_workflow_fields

    db = app_models['db']
    RFI = app_models['RFI']
    Submittal = app_models['Submittal']
    ChangeEvent = app_models['ChangeEvent']
    SubcontractorRFQ = app_models['SubcontractorRFQ']
    RFQAllocation = app_models['RFQAllocation']
    ChangeOrderRequest = app_models['ChangeOrderRequest']
    CORAllocation = app_models['CORAllocation']
    PotentialChangeOrder = app_models['PotentialChangeOrder']
    PCOAllocation = app_models['PCOAllocation']
    SageSyncEvent = app_models['SageSyncEvent']
    Commitment = app_models['Commitment']
    PayAppProjectState = app_models['PayAppProjectState']
    BudgetProjectState = app_models['BudgetProjectState']
    ChangeOrder = app_models['ChangeOrder']
    ChangeOrderAllocation = app_models['ChangeOrderAllocation']
    Project = app_models['Project']
    User = app_models['User']

    if not RFI or not Submittal or not ChangeEvent:
        result.add('critical', 'setup', 'Extended modules missing required models (RFI, Submittal, ChangeEvent)')
        return

    uid = datetime.utcnow().strftime('%H%M%S%f')[:12]

    # --- Standard RFI ---
    rfi_std = RFI(
        project_id=project.id,
        number=f'RFI-{uid}-001',
        subject='Curtain wall anchor detail at Level 12',
        question='Confirm embed plate spec per drawing A-501.',
        priority='High',
        status='Draft',
        date=datetime.utcnow().date(),
        created_by_id=users['pm'].id,
        ball_in_court_role='RFI Manager',
    )
    db.session.add(rfi_std)
    db.session.flush()
    execute_rfi_action(rfi_std, 'submit', users['pm'], User, {})
    add_response(rfi_std, {'body': 'Use 3/4" A325 bolts per spec 05 12 00.', 'is_official': True}, users['arch'].id, 'Sim Architect')
    workflow_rfi(rfi_std, 'close', 'Sim PM')
    db.session.commit()
    result.metrics['rfi_standard'] = rfi_std.status

    # --- Atypical RFI (private, cost + schedule impact) ---
    rfi_atyp = RFI(
        project_id=project.id,
        number=f'RFI-{uid}-ATYP',
        subject='Structural conflict — transfer girder vs MEP plenum',
        question='Field condition requires beam redesign; cost and schedule impact expected.',
        priority='Critical',
        status='Open',
        date=datetime.utcnow().date(),
        created_by_id=users['pm'].id,
        ball_in_court_role='Assignee',
        is_private=1,
        cost_impact_amount=850_000.0,
        schedule_impact_days=21,
        discipline='Structural',
    )
    apply_rfi_fields(rfi_atyp, {
        'notes': 'Executive-only until ROM validated',
        'location_description': 'Level 8 east core',
    })
    db.session.add(rfi_atyp)
    db.session.commit()
    result.metrics['rfi_atypical_cost'] = rfi_atyp.cost_impact_amount

    # --- Security: RFI status PUT bypass must fail ---
    old_rfi_status = rfi_std.status
    apply_rfi_fields(rfi_std, {'status': 'Void'})
    if rfi_std.status != old_rfi_status:
        result.add('critical', 'security', 'RFI status writable via PUT apply_rfi_fields')

    # --- Submittals (full review chain) ---
    sub_specs = [
        ('09-250-001', '09-250', 'Level 5 gypsum board assembly'),
        ('08-100-001', '08-100', 'Hollow metal door frames Type A'),
        ('23-000-001', '23-000', 'BAS control sequences'),
        ('15-100-001', '15-100', 'Rooftop unit RTU-3'),
        ('16-100-001', '16-100', 'Switchgear submittal package'),
    ]
    sub_closed = 0
    for i, (num_suffix, spec, desc) in enumerate(sub_specs):
        num = f'SUB-{uid}-{num_suffix}'
        sub = Submittal(
            project_id=project.id,
            number=num,
            description=desc,
            spec_section=spec,
            status='Draft',
            priority='Medium',
            submitted_by='Sim Sub Co',
            date=datetime.utcnow().date(),
        )
        apply_submittal_fields(sub, {}, is_create=True)
        db.session.add(sub)
        db.session.flush()
        submittal_workflow_action(sub, 'send_to_sub', users['pm'])
        submittal_workflow_action(sub, 'return_from_sub', users['sub'])
        submittal_workflow_action(sub, 'submit_to_architect', users['pm'])
        decision = 'No Exceptions Taken' if i == 0 else 'Reviewed as Noted'
        submittal_workflow_action(sub, 'architect_decision', users['arch'], {'decision': decision})
        if decision == 'No Exceptions Taken':
            submittal_workflow_action(sub, 'close', users['pm'])
            sub_closed += 1
    db.session.commit()
    result.metrics['submittals_closed'] = sub_closed
    result.metrics['submittals_total'] = len(sub_specs)

    # --- Security: submittal sync status bypass ---
    sample_sub = Submittal.query.filter_by(project_id=project.id).first()
    if sample_sub:
        old_sub_status = sample_sub.status
        apply_submittal_fields(sample_sub, {'status': 'Closed'}, is_create=False)
        if sample_sub.status != old_sub_status:
            result.add('critical', 'security', 'Submittal status writable via apply_submittal_fields PUT path')

    # --- Change event + RFQ + COR ---
    ce = ChangeEvent(
        project_id=project.id,
        number=f'CE-{uid}-001',
        title='Owner-directed lobby upgrade',
        status='Open',
        ball_in_court_role='Project Manager',
        rom_amount=1_200_000.0,
        created_by_id=users['pm'].id,
    )
    db.session.add(ce)
    db.session.flush()

    sub_com = next((c for c in commitments if c.commitment_type == 'Subcontract'), commitments[0] if commitments else None)
    rfq = SubcontractorRFQ(
        project_id=project.id,
        number=f'RFQ-{uid}-001',
        title='Lobby finishes RFQ',
        status='Draft',
        ball_in_court_role='Creator',
        company_id=sub_com.company_id if sub_com else '200',
        company_name=sub_com.company_name if sub_com else 'Finishes Sim Co',
        change_event_id=ce.id,
        created_by_id=users['pm'].id,
    )
    db.session.add(rfq)
    db.session.flush()
    save_generic_allocations(RFQAllocation, 'rfq_id', rfq.id, [{
        'cost_code': '09-250', 'cost_type': 'Subcontract', 'amount': 450_000,
    }], db)
    rfq_workflow_action(rfq, 'send', users['pm'])
    rfq_workflow_action(rfq, 'quote', users['sub'], [{
        'cost_code': '09-250', 'cost_type': 'Subcontract', 'amount': 450_000, 'quoted_amount': 475_000,
    }])
    rfq_workflow_action(rfq, 'accept', users['pm'])
    db.session.commit()
    result.metrics['rfq_status'] = rfq.status

    # Security: RFQ reject without authority must fail
    rfq_reject_test = SubcontractorRFQ(
        project_id=project.id,
        number=f'RFQ-{uid}-REJ',
        title='Reject auth test',
        status='Quoted',
        ball_in_court_role='Project Manager',
        company_id='999',
        created_by_id=users['pm'].id,
    )
    db.session.add(rfq_reject_test)
    db.session.commit()
    try:
        rfq_workflow_action(rfq_reject_test, 'reject', users['sub'])
        result.add('critical', 'security', 'RFQ reject allowed for unauthorized subcontractor user')
    except ValueError:
        result.add('info', 'security', 'RFQ reject correctly blocked for unauthorized user')

    # Security: RFQ quoted_amount PUT bypass
    old_quote = float(rfq.quoted_amount or 0)
    from change_event_persistence import apply_rfq_fields
    apply_rfq_fields(rfq, {'quoted_amount': 1.0})
    if float(rfq.quoted_amount or 0) != old_quote:
        result.add('critical', 'security', 'RFQ quoted_amount writable via PUT')

    cor = ChangeOrderRequest(
        project_id=project.id,
        number=f'COR-{uid}-001',
        title='Lobby upgrade COR',
        status='Draft',
        ball_in_court_role='Creator',
        amount=1_200_000.0,
        change_event_id=ce.id,
        created_by_id=users['pm'].id,
    )
    db.session.add(cor)
    db.session.flush()
    save_generic_allocations(CORAllocation, 'cor_id', cor.id, [{
        'cost_code': '09-250', 'cost_type': 'Subcontract', 'amount': 1_200_000,
    }], db)
    cor_workflow_action(cor, 'submit', users['pm'])
    for actor in (users['pm'], users['arch'], users['owner'], users['acct']):
        if cor.status == 'Approved':
            break
        try:
            cor_workflow_action(
                cor, 'approve', actor,
                body={'signature_attestation': True, 'signature_hash': 'sim', 'skip_signature_verify': True},
                ChangeOrderRequest=ChangeOrderRequest,
                CORAllocation=CORAllocation,
            )
        except ValueError as exc:
            if 'signature' not in str(exc).lower():
                raise
    db.session.commit()
    result.metrics['cor_status'] = cor.status
    if cor.status != 'Approved':
        result.add('critical', 'change_event', f'COR ended {cor.status} (expected Approved)')

    change_event_workflow_action(ce, 'submit', users['pm'])
    for _ in range(4):
        if ce.status == 'Approved':
            break
        change_event_workflow_action(ce, 'approve', users['pm'])
    db.session.commit()
    result.metrics['change_event_status'] = ce.status

    # Security: CE status PUT bypass
    old_ce_status = ce.status
    apply_change_event_fields(ce, {'status': 'Void'})
    if ce.status != old_ce_status:
        result.add('critical', 'security', 'Change event status writable via PUT')

    # --- Sage accounting review (sample events) ---
    reviewed = 0
    events = SageSyncEvent.query.filter_by(project_id=project.id, accounting_status='pending_review').limit(5).all()
    for ev in events:
        accept_sage_event_for_export(ev, users['acct'], db, Commitment=Commitment)
        reviewed += 1
    db.session.commit()
    result.metrics['sage_reviewed'] = reviewed

    # --- Pay app period 2 (partial) ---
    from pay_app_persistence import get_pay_app_state, save_pay_app_state
    from pay_app_workflow import process_pay_app_workflow, sub_pay_app_workflow_action

    _, pay_state = get_pay_app_state(PayAppProjectState, project.id)
    period = pay_state.get('currentPayAppPeriod') or {}
    if period.get('status') == 'Approved':
        pay_state['currentPayAppPeriod'] = {
            'periodNumber': 2,
            'status': 'Draft',
            'periodStart': '2026-02-01',
            'periodEnd': '2026-02-28',
            'ball_in_court_role': 'Creator',
        }
        pay_state['payAppBillingLines'] = {}
        sub_sov = pay_state.get('subcontractorSOV') or {}
        sub_hist = pay_state.get('subPayAppHistory') or {}
        sub_lien = pay_state.get('subLienWaivers') or {}
        billed_p2 = 0.0
        for company_key, lines in list(sub_sov.items())[:3]:
            period_amt = 0.0
            for line in lines:
                sv = float(line.get('scheduled_value') or 0)
                bill = round(sv * 0.10, 2)
                line['work_this_period'] = bill
                period_amt += bill
            entry = {'status': 'Draft', 'periodNumber': 2, 'totalBilledThisPeriod': period_amt}
            sub_hist.setdefault(company_key, {})['2'] = entry
            sub_lien.setdefault(company_key, {})['2'] = {'filename': f'lien-p2-{company_key}.pdf'}
            sub_pay_app_workflow_action(pay_state, company_key, 'submit', users['sub'], {'pending_entry': entry})
            sub_pay_app_workflow_action(pay_state, company_key, 'approve', users['pm'], {'pending_entry': entry})
            billed_p2 += period_amt
        save_pay_app_state(PayAppProjectState, db, project.id, pay_state, user_id=None)
        result.metrics['period2_sub_billed'] = billed_p2

    result.metrics['extended_modules'] = True


def run_simulation(name: str, trade_mix: list, app_models, *, contract_value: float = CONTRACT_VALUE, full_lifecycle: bool = False) -> SimResult:
    from budget_persistence import get_budget_state, save_budget_state
    from pay_app_persistence import get_pay_app_state, save_pay_app_state
    from pay_app_workflow import process_pay_app_workflow, g702_workflow_action, sub_sov_workflow_action, sub_pay_app_workflow_action
    from accounting_reconcile import reconcile_project_accounting
    from commitment_persistence import save_allocations

    db = app_models['db']
    Project = app_models['Project']
    Commitment = app_models['Commitment']
    CommitmentAllocation = app_models['CommitmentAllocation']
    ChangeOrder = app_models['ChangeOrder']
    ChangeOrderAllocation = app_models['ChangeOrderAllocation']
    BudgetProjectState = app_models['BudgetProjectState']
    PayAppProjectState = app_models['PayAppProjectState']
    SageSyncEvent = app_models['SageSyncEvent']
    User = app_models['User']
    users = _ensure_sim_users(db, User)

    result = SimResult(name=name, project_id=0)
    ts = datetime.utcnow().strftime('%H%M%S')
    project = Project(
        number=f'SIM-{name[:3].upper()}-{ts}',
        name=f'Simulation {name} — ${contract_value/1e6:.0f}M Commercial',
        client='Sim Owner LLC',
        contract_value=contract_value,
        status='Active',
        sage_job_number=f'SIM{name[:2]}{ts}',
        accounting_project_number=f'ACCT-{ts}',
    )
    db.session.add(project)
    db.session.commit()
    result.project_id = project.id

    # --- Budget seed ---
    budget_lines = []
    total_orig = 0.0
    for code, desc, pct, _ctype in trade_mix:
        amt = round(contract_value * pct, 2)
        total_orig += amt
        budget_lines.append({
            'cost_code': code,
            'description': desc,
            'original_budget': amt,
            'approved_changes': 0,
            'pending': 0,
            'committed': 0,
            'actual': 0,
            'cost_type': 'Subcontract',
        })
    budget_state = {
        'budgetLines': budget_lines,
        'budgetContractAmount': contract_value,
        'budgetRevision': 1,
        'budgetLocked': False,
        'budgetPublished': True,
    }
    save_budget_state(BudgetProjectState, db, project.id, budget_state, user_id=None)

    if abs(total_orig - contract_value) > 100:
        result.add('warning', 'budget', f'Budget lines sum ${total_orig:,.2f} vs contract ${contract_value:,.2f}')

    # --- Pay app state seed ---
    contractor_sov = [{
        'id': i + 1,
        'cost_code': line['cost_code'],
        'description': line['description'],
        'original': line['original_budget'],
        'billed_to_date': 0,
        'co_billed_to_date': 0,
    } for i, line in enumerate(budget_lines)]

    pay_state = {
        'contractorSOV': contractor_sov,
        'subcontractorSOV': {},
        'subSOVStatus': {},
        'subPayAppHistory': {},
        'subLienWaivers': {},
        'payAppRetainagePercent': RETAINAGE_PCT,
        'requireLienWaiverOnSubPayApp': True,
        'requireAllSubPayAppsBeforeG702Submit': True,
        'currentPayAppPeriod': {
            'periodNumber': 1,
            'status': 'Draft',
            'periodStart': '2026-01-01',
            'periodEnd': '2026-01-31',
            'ball_in_court_role': 'Creator',
        },
        'payAppBillingLines': [],
    }
    save_pay_app_state(PayAppProjectState, db, project.id, pay_state, user_id=None)

    commitments = []
    company_id_counter = 100

    # --- Commitments per trade ---
    for code, desc, pct, ctype in trade_mix:
        if ctype == 'Service Agreement' and 'Contingency' in desc:
            continue  # hold contingency uncommitted
        amt = round(contract_value * pct * 0.98, 2)  # slight buy-out vs budget
        company_id_counter += 1
        com = Commitment(
            project_id=project.id,
            number=f'SC-{company_id_counter}',
            commitment_type=ctype,
            company_name=f'{desc} Sim Co',
            company_id=str(company_id_counter),
            title=f'{desc} package',
            description=f'Simulated {ctype} for {desc}',
            status='Draft',
            original_amount=amt,
            current_amount=amt,
            retainage_percent=RETAINAGE_PCT,
            ball_in_court_role='Creator',
        )
        db.session.add(com)
        db.session.flush()
        save_allocations(CommitmentAllocation, com.id, [{
            'cost_code': code,
            'amount': amt,
            'description': desc,
        }], db)
        commitments.append(com)
    db.session.commit()

    approved_count = 0
    for com in commitments:
        status = _approve_commitment(com, CommitmentAllocation, users, app_models)
        if status == 'Approved':
            approved_count += 1
        else:
            result.add('critical', 'commitment', f'{com.number} ended {status} (expected Approved)')
    result.metrics['commitments_approved'] = approved_count

    # --- Sub SOV approve all subs ---
    _, pay_state = get_pay_app_state(PayAppProjectState, project.id)
    sub_sov = pay_state.get('subcontractorSOV') or {}
    sub_status = pay_state.get('subSOVStatus') or {}
    for key in list(sub_sov.keys()):
        sub_status[key] = {'status': 'Draft'}
        sub_sov_workflow_action(pay_state, key, 'submit', users['sub'])
        sub_sov_workflow_action(pay_state, key, 'approve', users['pm'])
    pay_state['subSOVStatus'] = sub_status
    save_pay_app_state(PayAppProjectState, db, project.id, pay_state, user_id=None)

    # --- Owner change orders (3 scenarios) ---
    co_specs = [
        (f'{name[:4]}-CO-001', 'Owner scope add — electrical', '16-100', 450_000),
        (f'{name[:4]}-CO-002', 'Owner deduct — finishes', '09-250', -120_000),
        (f'{name[:4]}-CO-003', 'Pending CO — HVAC upgrade', '15-100', 280_000),
    ]
    for num, title, code, amt in co_specs:
        co = ChangeOrder(
            project_id=project.id,
            number=num,
            title=title,
            description=title,
            status='Draft',
            amount=abs(amt),
            cost_code=code,
            ball_in_court_role='Creator',
        )
        db.session.add(co)
        db.session.flush()
        db.session.add(ChangeOrderAllocation(
            change_order_id=co.id,
            cost_code=code,
            cost_type='Subcontract',
            amount=amt,
            description=title,
        ))
        db.session.commit()
        if num.endswith('-CO-003'):
            co.status = 'Pending Owner'
            co.ball_in_court_role = 'Owner'
            db.session.commit()
            result.metrics['pending_co'] = amt
        else:
            st = _approve_owner_co(co, users, app_models)
            if st != 'Approved':
                result.add('critical', 'change_order', f'{num} ended {st} (expected Approved)')

    reconcile_project_accounting(
        project.id, None,
        ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
        Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
        BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState, db=db,
    )

    # --- Sub pay apps (period 1) — bill ~15% of each sub ---
    _, pay_state = get_pay_app_state(PayAppProjectState, project.id)
    sub_sov = pay_state.get('subcontractorSOV') or {}
    sub_hist = pay_state.get('subPayAppHistory') or {}
    sub_lien = pay_state.get('subLienWaivers') or {}
    total_sub_billed = 0.0
    for company_key, lines in sub_sov.items():
        period_amt = 0.0
        for line in lines:
            sv = float(line.get('scheduled_value') or line.get('original_commitment') or 0)
            bill = round(sv * 0.15, 2)
            line['work_this_period'] = bill
            line['billed_to_date'] = float(line.get('billed_to_date') or 0) + bill
            period_amt += bill
        entry = {
            'status': 'Draft',
            'periodNumber': 1,
            'totalBilledThisPeriod': period_amt,
            'workThisPeriod': period_amt,
        }
        sub_hist.setdefault(company_key, {})['1'] = entry
        sub_lien.setdefault(company_key, {})['1'] = {
            'filename': f'lien-waiver-{company_key}-p1.pdf',
            'uploadedDate': '2026-01-15',
        }
        pay_state['subLienWaivers'] = sub_lien
        sub_pay_app_workflow_action(pay_state, company_key, 'submit', users['sub'], {'pending_entry': entry})
        sub_pay_app_workflow_action(pay_state, company_key, 'approve', users['pm'], {'pending_entry': entry})
        sub_hist[company_key]['1']['status'] = 'Approved'
        total_sub_billed += period_amt
    pay_state['subPayAppHistory'] = sub_hist
    pay_state['subLienWaivers'] = sub_lien
    pay_state['subcontractorSOV'] = sub_sov
    save_pay_app_state(PayAppProjectState, db, project.id, pay_state, user_id=None)
    reconcile_project_accounting(
        project.id, None,
        ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
        Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
        BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState, db=db,
    )

    # --- G702 period 1 ---
    _, pay_state = get_pay_app_state(PayAppProjectState, project.id)
    period = pay_state.get('currentPayAppPeriod') or {}
    contractor_sov = pay_state.get('contractorSOV') or []
    sov_line_id = contractor_sov[0].get('id', 1) if contractor_sov else 1
    billing_total = round(contract_value * 0.12, 2)
    pay_state['payAppBillingLines'] = {
        str(sov_line_id): {
            'workThisPeriod': billing_total,
            'materialsStored': 0,
        }
    }
    try:
        g702_result = process_pay_app_workflow(
            project.id, 'g702', period.get('periodNumber'), 'submit', users['pm'], User,
            {}, pay_state,
            PayAppProjectState=PayAppProjectState, db=db,
            ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
            BudgetProjectState=BudgetProjectState, Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation, Project=Project, SageSyncEvent=SageSyncEvent,
        )
        pay_state = g702_result['state']
        period = pay_state.get('currentPayAppPeriod') or period
        billing_amt = round(contract_value * 0.12 * (1 - RETAINAGE_PCT / 100), 2)
        # Spoofed low amount_due must NOT bypass Owner/Accounting on large billing
        approve_result = process_pay_app_workflow(
            project.id, 'g702', period.get('periodNumber'), 'approve', users['pm'], User,
            {'amount_due': 45_000}, pay_state,
            PayAppProjectState=PayAppProjectState, db=db,
            ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
            BudgetProjectState=BudgetProjectState, Commitment=Commitment,
            CommitmentAllocation=CommitmentAllocation, Project=Project, SageSyncEvent=SageSyncEvent,
        )
        pay_state = approve_result['state']
        period = pay_state.get('currentPayAppPeriod') or period
        if approve_result.get('final_approved') and billing_amt >= 50_000:
            result.add('critical', 'authorization', 'G702 approved without Owner/Accounting despite billing over $50K threshold')
        elif period.get('status') in ('Pending Owner', 'Pending Accounting'):
            result.add('info', 'pay_app', 'G702 correctly requires Owner/Accounting for large billing (spoofed amount_due ignored)')
        for actor in (users['owner'], users['acct']):
            if approve_result.get('final_approved'):
                break
            approve_result = process_pay_app_workflow(
                project.id, 'g702', period.get('periodNumber'), 'approve', actor, User,
                {'amount_due': 45_000}, approve_result['state'],
                PayAppProjectState=PayAppProjectState, db=db,
                ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
                BudgetProjectState=BudgetProjectState, Commitment=Commitment,
                CommitmentAllocation=CommitmentAllocation, Project=Project, SageSyncEvent=SageSyncEvent,
            )
            pay_state = approve_result['state']
            period = pay_state.get('currentPayAppPeriod') or period
        save_pay_app_state(PayAppProjectState, db, project.id, pay_state, user_id=None)
        result.metrics['g702_status'] = period.get('status')
    except Exception as exc:
        result.add('critical', 'pay_app', f'G702 workflow failed: {exc}')

    # --- Company key split test ---
    _, pay_state = get_pay_app_state(PayAppProjectState, project.id)
    sub_sov = pay_state.get('subcontractorSOV') or {}
    if commitments:
        sample = next((c for c in commitments if c.commitment_type == 'Subcontract'), None)
        if sample:
            id_key = str(sample.company_id)
            name_key = sample.company_name
            has_id = id_key in sub_sov
            has_name = name_key in sub_sov
            if has_id and has_name and id_key != name_key:
                result.add('critical', 'reconcile', f'Duplicate sub SOV buckets for same vendor: id={id_key!r} and name={name_key!r}')

    # --- Final reconcile & validation ---
    recon = reconcile_project_accounting(
        project.id, None,
        ChangeOrder=ChangeOrder, ChangeOrderAllocation=ChangeOrderAllocation,
        Commitment=Commitment, CommitmentAllocation=CommitmentAllocation,
        BudgetProjectState=BudgetProjectState, PayAppProjectState=PayAppProjectState, db=db,
    )
    _, budget_state = get_budget_state(BudgetProjectState, project.id)
    lines = budget_state.get('budgetLines') or []

    total_committed = sum(float(l.get('committed') or 0) for l in lines)
    total_actual = sum(float(l.get('actual') or 0) for l in lines)
    total_pending = sum(float(l.get('pending') or 0) for l in lines)
    total_approved_co = sum(float(l.get('approved_changes') or 0) for l in lines)

    result.metrics.update({
        'budget_committed': total_committed,
        'budget_actual': total_actual,
        'budget_pending_co': total_pending,
        'budget_approved_co': total_approved_co,
        'sub_billed_period1': total_sub_billed,
        'recon_actual_applied': recon.get('actual_cost_applied', 0),
    })

    expected_commit = sum(float(c.current_amount or 0) for c in commitments if c.status == 'Approved')
    if abs(total_committed - expected_commit) > 5000:
        result.add('warning', 'reconcile', f'Budget committed ${total_committed:,.0f} vs approved commitments ${expected_commit:,.0f}')

    if total_actual > 0 and abs(total_actual - recon.get('actual_cost_applied', 0)) > 1000:
        result.add('warning', 'reconcile', f'Budget actual ${total_actual:,.0f} != reconcile actual ${recon.get("actual_cost_applied", 0):,.0f}')

    invoiced_sum = sum(float(c.invoiced_amount or 0) for c in Commitment.query.filter_by(project_id=project.id).all())
    if total_sub_billed > 0 and invoiced_sum < total_sub_billed * 0.5:
        result.add('warning', 'pay_app', f'Commitment invoiced_amount ${invoiced_sum:,.0f} low vs sub billed ${total_sub_billed:,.0f}')

    sage_pending = SageSyncEvent.query.filter_by(project_id=project.id, accounting_status='pending_review').count()
    result.metrics['sage_pending_review'] = sage_pending
    if sage_pending > 20:
        result.add('info', 'sage', f'{sage_pending} Sage events awaiting accounting review (expected volume on ${contract_value/1e6:.0f}M job)')

    if full_lifecycle:
        _run_extended_modules(result, project, users, app_models, commitments)

    return result


def main():
    sys.path.insert(0, '/workspace')
    import app as app_module
    from unittest.mock import patch
    from app import (
        db, Project, Commitment, CommitmentAllocation,
        ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
        PayAppProjectState, SageSyncEvent, User, RFI, Submittal,
        ChangeEvent, SubcontractorRFQ, RFQAllocation,
        ChangeOrderRequest, CORAllocation, PotentialChangeOrder, PCOAllocation,
    )

    models = {
        'db': db,
        'Project': Project,
        'Commitment': Commitment,
        'CommitmentAllocation': CommitmentAllocation,
        'ChangeOrder': ChangeOrder,
        'ChangeOrderAllocation': ChangeOrderAllocation,
        'BudgetProjectState': BudgetProjectState,
        'PayAppProjectState': PayAppProjectState,
        'SageSyncEvent': SageSyncEvent,
        'User': User,
        'ScheduleData': getattr(app_module, 'ScheduleData', None),
        'RFI': RFI,
        'Submittal': Submittal,
        'ChangeEvent': ChangeEvent,
        'SubcontractorRFQ': SubcontractorRFQ,
        'RFQAllocation': RFQAllocation,
        'ChangeOrderRequest': ChangeOrderRequest,
        'CORAllocation': CORAllocation,
        'PotentialChangeOrder': PotentialChangeOrder,
        'PCOAllocation': PCOAllocation,
    }

    runs = [
        ('Retail-Shell-A', TRADE_MIX_A, CONTRACT_VALUE, False),
        ('Hospitality-B', TRADE_MIX_B, CONTRACT_VALUE, False),
        ('Mega-Campus-C', TRADE_MIX_C, CONTRACT_VALUE_100M, True),
    ]

    results = []
    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    try:
        with app_module.app.app_context():
            for name, mix, cv, full in runs:
                db.session.rollback()
                print(f'\n{"="*60}\nRunning simulation: {name} (${cv/1e6:.0f}M{" full lifecycle" if full else ""})\n{"="*60}')
                try:
                    r = run_simulation(name, mix, models, contract_value=cv, full_lifecycle=full)
                    results.append(r)
                    print(f'Project ID: {r.project_id}')
                    print('Metrics:', json.dumps(r.metrics, indent=2))
                    for issue in r.issues:
                        print(f'  [{issue.severity.upper()}] {issue.category}: {issue.message}')
                except Exception:
                    print(f'FATAL in {name}:')
                    traceback.print_exc()
                    results.append(SimResult(name=name, project_id=-1))
                    results[-1].add('critical', 'fatal', traceback.format_exc().splitlines()[-1])
    finally:
        sig_patch.stop()

    print(f'\n{"="*60}\nSUMMARY\n{"="*60}')
    critical = sum(1 for r in results for i in r.issues if i.severity == 'critical')
    warnings = sum(1 for r in results for i in r.issues if i.severity == 'warning')
    print(f'Simulations: {len(results)} | Critical: {critical} | Warnings: {warnings}')
    for r in results:
        print(f'\n{r.name} (project {r.project_id}):')
        if not r.issues:
            print('  No issues detected.')
        for i in r.issues:
            print(f'  [{i.severity}] {i.category}: {i.message}')

    return 1 if critical else 0


if __name__ == '__main__':
    raise SystemExit(main())
