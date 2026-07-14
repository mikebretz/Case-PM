#!/usr/bin/env python3
"""
Multi-project portfolio simulation — overlapping timelines, mixed scale, user load.

Run: python3 scripts/simulate_concurrent_portfolio.py

Projects (semi-concurrent / interleaved monthly ticks):
  - $100M / 24 pay periods / 2 years / 200 users
  - $50M  / heavy RFIs + COs / 100 users
  - $10M  / heavy RFIs + COs / 40 users
  - $10M  / moderate RFIs + few COs / 40 users

Timelines overlap ~20–50% by design (see PORTFOLIO_SCENARIOS).
"""
from __future__ import annotations

import json
import random
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

sys.path.insert(0, '/workspace')

from scripts.simulate_financial_project import (  # noqa: E402
    RETAINAGE_PCT,
    TRADE_MIX_C,
    SimResult,
    _approve_commitment,
    _ensure_sim_users,
)

TRADE_MIX_SMALL = [
    ('03-300', 'Concrete', 0.12, 'Subcontract'),
    ('09-250', 'Drywall', 0.18, 'Subcontract'),
    ('15-100', 'HVAC', 0.22, 'Subcontract'),
    ('16-100', 'Electrical', 0.18, 'Subcontract'),
    ('22-100', 'Plumbing', 0.12, 'Subcontract'),
    ('01-100', 'General Conditions', 0.13, 'Service Agreement'),
    ('01-200', 'Contingency', 0.05, 'Service Agreement'),
]

ROLE_POOL = (
    ['Project Manager'] * 8
    + ['Superintendent'] * 10
    + ['Architect'] * 6
    + ['Owner'] * 4
    + ['Contractor Accounting'] * 6
    + ['Company User'] * 30
    + ['Viewer'] * 46
)


@dataclass
class ProjectScenario:
    name: str
    slug: str
    contract_value: float
    trade_mix: list
    user_count: int
    start_month: int
    duration_months: int
    rfi_per_month: float
    co_per_month: float
    pay_periods: int | None = None
    submittal_per_month: float = 0
    rfq_per_month: float = 0
    change_event_per_month: float = 0
    reconcile_every: int = 1

    @property
    def end_month(self) -> int:
        return self.start_month + self.duration_months - 1


PORTFOLIO_SCENARIOS = [
    ProjectScenario(
        name='Mega-Campus-100M',
        slug='mega100',
        contract_value=100_000_000.0,
        trade_mix=TRADE_MIX_C,
        user_count=200,
        start_month=0,
        duration_months=24,
        rfi_per_month=3.0,
        co_per_month=1.5,
        pay_periods=24,
    ),
    ProjectScenario(
        name='Medical-Pavilion-50M',
        slug='med50',
        contract_value=50_000_000.0,
        trade_mix=TRADE_MIX_C,
        user_count=100,
        start_month=10,
        duration_months=12,
        rfi_per_month=5.0,
        co_per_month=2.5,
        pay_periods=12,
    ),
    ProjectScenario(
        name='Tenant-Fitout-10M-Heavy',
        slug='ten10h',
        contract_value=10_000_000.0,
        trade_mix=TRADE_MIX_SMALL,
        user_count=40,
        start_month=4,
        duration_months=10,
        rfi_per_month=6.0,
        co_per_month=3.0,
        pay_periods=10,
    ),
    ProjectScenario(
        name='Retail-Shell-10M-Moderate',
        slug='ret10m',
        contract_value=10_000_000.0,
        trade_mix=TRADE_MIX_SMALL,
        user_count=40,
        start_month=12,
        duration_months=10,
        rfi_per_month=2.0,
        co_per_month=0.3,
        pay_periods=10,
    ),
]


@dataclass
class ProjectRuntime:
    scenario: ProjectScenario
    result: SimResult
    project: Any = None
    users: dict = field(default_factory=dict)
    user_pool: list = field(default_factory=list)
    commitments: list = field(default_factory=list)
    setup_done: bool = False
    local_month: int = -1
    co_seq: int = 0
    rfi_seq: int = 0
    pay_periods_completed: int = 0
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


def _month_dates(base_year: int, global_month: int) -> tuple[str, str]:
    y = base_year + global_month // 12
    m = (global_month % 12) + 1
    if m == 12:
        end = f'{y}-12-31'
    else:
        end = date(y, m + 1, 1).replace(day=1)
        from datetime import timedelta
        end = (end - timedelta(days=1)).isoformat()
    start = f'{y}-{m:02d}-01'
    return start, end


def _create_user_pool(db, User, scenario: ProjectScenario, project_id: int, ProjectMembership) -> list:
    from project_access import save_memberships_for_user

    pool = []
    base = scenario.slug
    # Cap sim users for runtime; full count recorded in scenario.user_count for reporting
    sim_users = min(scenario.user_count, 100)
    for i in range(sim_users):
        email = f'sim.{base}.u{i:04d}@casepm.test'
        u = User.query.filter_by(email=email).first()
        role = ROLE_POOL[i % len(ROLE_POOL)]
        if not u:
            u = User(
                first_name='Sim',
                last_name=f'{base}-{i:04d}',
                email=email,
                role=role,
                status='Active',
            )
            u.set_password('SimTest!12345')
            db.session.add(u)
            db.session.flush()
        else:
            u.role = role
        pool.append(u)
    db.session.commit()
    for u in pool:
        try:
            save_memberships_for_user(u.id, [project_id], db, ProjectMembership=ProjectMembership, default_role=u.role)
        except Exception as exc:
            raise RuntimeError(f'Membership failed for {u.email}: {exc}') from exc
    db.session.commit()
    return pool


def _setup_project(rt: ProjectRuntime, models: dict, global_month: int) -> None:
    from budget_persistence import save_budget_state
    from pay_app_persistence import save_pay_app_state
    from commitment_persistence import save_allocations

    sc = rt.scenario
    db = models['db']
    Project = models['Project']
    Commitment = models['Commitment']
    CommitmentAllocation = models['CommitmentAllocation']
    BudgetProjectState = models['BudgetProjectState']
    PayAppProjectState = models['PayAppProjectState']
    User = models['User']
    ProjectMembership = models.get('ProjectMembership')

    rt.users = _ensure_sim_users(db, User)
    ts = datetime.utcnow().strftime('%H%M%S')
    uniq = rt.uid[:8]
    project = Project(
        number=f'PF-{sc.slug.upper()}-{uniq}',
        name=f'Portfolio {sc.name}',
        client='Portfolio Sim Owner',
        contract_value=sc.contract_value,
        status='Active',
        sage_job_number=f'PF{sc.slug}{uniq}',
        accounting_project_number=f'PF-{sc.slug}-{uniq}',
    )
    db.session.add(project)
    db.session.commit()
    rt.project = project
    rt.result.project_id = project.id

    if ProjectMembership:
        rt.user_pool = _create_user_pool(db, User, sc, project.id, ProjectMembership)
        rt.result.metrics['users_assigned'] = sc.user_count
        rt.result.metrics['users_simulated'] = len(rt.user_pool)

    budget_lines = []
    cv = sc.contract_value
    for code, desc, pct, _ctype in sc.trade_mix:
        if 'Contingency' in desc:
            continue
        amt = round(cv * pct, 2)
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
    save_budget_state(BudgetProjectState, db, project.id, {
        'budgetLines': budget_lines,
        'budgetContractAmount': cv,
        'budgetRevision': 1,
        'budgetLocked': False,
        'budgetPublished': True,
    }, user_id=None)

    contractor_sov = [{
        'id': i + 1,
        'cost_code': line['cost_code'],
        'description': line['description'],
        'original': line['original_budget'],
        'billed_to_date': 0,
        'co_billed_to_date': 0,
    } for i, line in enumerate(budget_lines)]

    pstart, pend = _month_dates(2026, global_month)
    save_pay_app_state(PayAppProjectState, db, project.id, {
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
            'periodStart': pstart,
            'periodEnd': pend,
            'ball_in_court_role': 'Creator',
        },
        'payAppBillingLines': {},
    }, user_id=None)

    cid = 1000 + project.id * 100
    for code, desc, pct, ctype in sc.trade_mix:
        if ctype == 'Service Agreement':
            continue
        amt = round(cv * pct * 0.98, 2)
        cid += 1
        com = Commitment(
            project_id=project.id,
            number=f'SC-{sc.slug}-{cid}',
            commitment_type=ctype,
            company_name=f'{desc} {sc.slug}',
            company_id=str(cid),
            title=f'{desc} package',
            description=desc,
            status='Draft',
            original_amount=amt,
            current_amount=amt,
            retainage_percent=RETAINAGE_PCT,
            ball_in_court_role='Creator',
        )
        db.session.add(com)
        db.session.flush()
        save_allocations(CommitmentAllocation, com.id, [{
            'cost_code': code, 'amount': amt, 'description': desc,
        }], db)
        rt.commitments.append(com)
    db.session.commit()

    approved = 0
    for com in rt.commitments:
        st = _approve_commitment(com, models['CommitmentAllocation'], rt.users, models)
        if st == 'Approved':
            approved += 1
        else:
            rt.result.add('critical', 'commitment', f'{com.number} ended {st}')
    rt.result.metrics['commitments_approved'] = approved

    from pay_app_persistence import get_pay_app_state
    from pay_app_workflow import sub_sov_workflow_action
    _, pay_state = get_pay_app_state(PayAppProjectState, project.id)
    for key in list((pay_state.get('subcontractorSOV') or {}).keys()):
        sub_sov_workflow_action(pay_state, key, 'submit', rt.users['sub'])
        sub_sov_workflow_action(pay_state, key, 'approve', rt.users['pm'])
    save_pay_app_state(PayAppProjectState, db, project.id, pay_state, user_id=None)
    rt.setup_done = True


def _spawn_rfis(rt: ProjectRuntime, models: dict, count: int, global_month: int) -> None:
    if count <= 0:
        return
    from rfi_persistence import apply_rfi_fields, workflow_rfi, add_response
    from workflow_responder import execute_rfi_action

    RFI = models['RFI']
    User = models['User']
    db = models['db']
    users = rt.users
    n = int(count) + (1 if random.random() < (count % 1) else 0)
    for _ in range(n):
        rt.rfi_seq += 1
        num = f'RFI-{rt.uid}-M{global_month:02d}-{rt.rfi_seq:04d}'
        atypical = random.random() < 0.15
        rfi = RFI(
            project_id=rt.project.id,
            number=num,
            subject=f'Sim RFI {num}',
            question='Clarification requested for field condition.',
            priority='Critical' if atypical else 'Medium',
            status='Draft',
            date=datetime.utcnow().date(),
            created_by_id=users['pm'].id,
            ball_in_court_role='RFI Manager',
            is_private=1 if atypical else 0,
            cost_impact_amount=random.uniform(10_000, 250_000) if atypical else 0,
            schedule_impact_days=random.randint(3, 30) if atypical else 0,
        )
        apply_rfi_fields(rfi, {}, is_create=True)
        db.session.add(rfi)
        db.session.flush()
        try:
            execute_rfi_action(rfi, 'submit', users['pm'], User, {})
            if random.random() < 0.7:
                add_response(rfi, {
                    'body': 'Official answer for simulation.',
                    'is_official': True,
                }, users['arch'].id, 'Sim Architect')
                workflow_rfi(rfi, 'close', 'Sim')
        except ValueError as exc:
            rt.result.add('warning', 'rfi', f'{num}: {exc}')
    db.session.commit()
    rt.result.metrics['rfis_created'] = rt.result.metrics.get('rfis_created', 0) + n


def _approve_co_smart(co, users, models) -> str:
    from co_persistence import process_change_order_workflow
    db = models['db']
    role_map = {
        'Project Manager': users['pm'],
        'Architect': users['arch'],
        'Owner': users['owner'],
        'Contractor Accounting': users['acct'],
    }
    kw = dict(
        ChangeOrder=models['ChangeOrder'],
        ChangeOrderAllocation=models['ChangeOrderAllocation'],
        PayAppProjectState=models['PayAppProjectState'],
        ScheduleData=models.get('ScheduleData'),
        Project=models['Project'],
        BudgetProjectState=models['BudgetProjectState'],
        db=db,
        Commitment=models['Commitment'],
        CommitmentAllocation=models['CommitmentAllocation'],
        SageSyncEvent=models['SageSyncEvent'],
    )
    process_change_order_workflow(co, 'submit', users['pm'], None, {'comments': 'sim'}, **kw)
    db.session.commit()
    for _ in range(12):
        if co.status in ('Approved', 'Rejected', 'Void'):
            break
        role = co.ball_in_court_role or 'Project Manager'
        actor = role_map.get(role, users['pm'])
        body = {'comments': 'sim'}
        if role in ('Owner', 'Architect'):
            body.update({'signature_attestation': True, 'signature_hash': 'sim-hash'})
        try:
            process_change_order_workflow(
                co, 'approve', actor, None, body,
                developer_unlock_bypass=True, **kw,
            )
            db.session.commit()
        except ValueError:
            break
    return co.status


def _spawn_cos(rt: ProjectRuntime, models: dict, count: float, global_month: int) -> None:
    if count <= 0:
        return
    ChangeOrder = models['ChangeOrder']
    ChangeOrderAllocation = models['ChangeOrderAllocation']
    db = models['db']
    n = int(count) + (1 if random.random() < (count % 1) else 0)
    scale = rt.scenario.contract_value / 30_000_000.0
    codes = [c[0] for c in rt.scenario.trade_mix if '01-' not in c[0]]
    for _ in range(n):
        rt.co_seq += 1
        code = random.choice(codes) if codes else '09-250'
        amt = round(random.uniform(25_000, 180_000) * max(scale, 0.3), 2)
        if random.random() < 0.15:
            amt = -amt
        num = f'CO-{rt.uid}-M{global_month:02d}-{rt.co_seq:04d}'
        co = ChangeOrder(
            project_id=rt.project.id,
            number=num,
            title=f'Sim change {num}',
            description=num,
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
            description=num,
        ))
        db.session.commit()
        if random.random() < 0.75:
            try:
                st = _approve_co_smart(co, rt.users, models)
                if st != 'Approved':
                    rt.result.add('warning', 'change_order', f'{num} ended {st}')
            except ValueError as exc:
                rt.result.add('warning', 'change_order', f'{num}: {exc}')
        else:
            co.status = 'Pending Owner'
            co.ball_in_court_role = 'Owner'
            db.session.commit()
    rt.result.metrics['cos_created'] = rt.result.metrics.get('cos_created', 0) + n


def _spawn_submittals(rt: ProjectRuntime, models: dict, count: float, global_month: int) -> None:
    if count <= 0:
        return
    Submittal = models.get('Submittal')
    if not Submittal:
        return
    from submittal_persistence import apply_submittal_fields, submittal_workflow_action

    db = models['db']
    users = rt.users
    n = int(count) + (1 if random.random() < (count % 1) else 0)
    codes = [c[0] for c in rt.scenario.trade_mix if '01-' not in c[0]]
    seq = rt.result.metrics.get('submittals_created', 0)
    for _ in range(n):
        seq += 1
        spec = random.choice(codes) if codes else '09-250'
        num = f'SUB-{rt.uid}-M{global_month:02d}-{seq:05d}'
        sub = Submittal(
            project_id=rt.project.id,
            number=num,
            description=f'Sim submittal {num}',
            spec_section=spec,
            status='Draft',
            priority=random.choice(['Medium', 'High', 'Critical']),
            submitted_by='Sim Sub Co',
            date=datetime.utcnow().date(),
        )
        apply_submittal_fields(sub, {}, is_create=True)
        db.session.add(sub)
        db.session.flush()
        try:
            submittal_workflow_action(sub, 'send_to_sub', users['pm'])
            submittal_workflow_action(sub, 'return_from_sub', users['sub'])
            submittal_workflow_action(sub, 'submit_to_architect', users['pm'])
            decision = random.choice([
                'No Exceptions Taken', 'Reviewed as Noted', 'Revise & Resubmit', 'Rejected',
            ])
            submittal_workflow_action(sub, 'architect_decision', users['arch'], {'decision': decision})
            if decision == 'No Exceptions Taken':
                submittal_workflow_action(sub, 'close', users['pm'])
        except ValueError as exc:
            rt.result.add('warning', 'submittal', f'{num}: {exc}')
    db.session.commit()
    rt.result.metrics['submittals_created'] = seq


def _spawn_rfqs(rt: ProjectRuntime, models: dict, count: float, global_month: int) -> None:
    if count <= 0:
        return
    SubcontractorRFQ = models.get('SubcontractorRFQ')
    if not SubcontractorRFQ:
        return
    from change_event_persistence import rfq_workflow_action, save_generic_allocations

    db = models['db']
    users = rt.users
    n = int(count) + (1 if random.random() < (count % 1) else 0)
    codes = [c[0] for c in rt.scenario.trade_mix if '01-' not in c[0]]
    scale = rt.scenario.contract_value / 30_000_000.0
    seq = rt.result.metrics.get('rfqs_created', 0)
    sub_com = next((c for c in rt.commitments if c.commitment_type == 'Subcontract'), None)
    for _ in range(n):
        seq += 1
        code = random.choice(codes) if codes else '09-250'
        amt = round(random.uniform(50_000, 400_000) * max(scale, 0.35), 2)
        num = f'RFQ-{rt.uid}-M{global_month:02d}-{seq:05d}'
        rfq = SubcontractorRFQ(
            project_id=rt.project.id,
            number=num,
            title=f'Sim RFQ {num}',
            status='Draft',
            ball_in_court_role='Creator',
            company_id=sub_com.company_id if sub_com else str(rt.project.id),
            created_by_id=users['pm'].id,
        )
        db.session.add(rfq)
        db.session.flush()
        save_generic_allocations(models['RFQAllocation'], 'rfq_id', rfq.id, [{
            'cost_code': code, 'cost_type': 'Subcontract', 'amount': amt,
        }], db)
        try:
            rfq_workflow_action(rfq, 'send', users['pm'])
            rfq_workflow_action(rfq, 'quote', users['sub'], [{
                'cost_code': code, 'amount': amt, 'quoted_amount': round(amt * 1.05, 2),
            }])
            if random.random() < 0.8:
                rfq_workflow_action(rfq, 'accept', users['pm'])
        except ValueError as exc:
            rt.result.add('warning', 'rfq', f'{num}: {exc}')
    db.session.commit()
    rt.result.metrics['rfqs_created'] = seq


def _spawn_change_events(rt: ProjectRuntime, models: dict, count: float, global_month: int) -> None:
    if count <= 0:
        return
    ChangeEvent = models.get('ChangeEvent')
    if not ChangeEvent:
        return
    from change_event_persistence import apply_change_event_fields, change_event_workflow_action

    db = models['db']
    users = rt.users
    n = int(count) + (1 if random.random() < (count % 1) else 0)
    seq = rt.result.metrics.get('change_events_created', 0)
    for _ in range(n):
        seq += 1
        num = f'CE-{rt.uid}-M{global_month:02d}-{seq:05d}'
        ce = ChangeEvent(
            project_id=rt.project.id,
            number=num,
            title=f'Sim change event {num}',
            status='Open',
            ball_in_court_role='Creator',
            created_by_id=users['pm'].id,
        )
        apply_change_event_fields(ce, {})
        db.session.add(ce)
        db.session.flush()
        try:
            change_event_workflow_action(ce, 'submit', users['pm'])
            if random.random() < 0.6:
                change_event_workflow_action(ce, 'approve', users['pm'])
        except ValueError as exc:
            rt.result.add('warning', 'change_event', f'{num}: {exc}')
    db.session.commit()
    rt.result.metrics['change_events_created'] = seq


def _run_pay_period(rt: ProjectRuntime, models: dict, period_num: int, global_month: int) -> None:
    from pay_app_persistence import get_pay_app_state, save_pay_app_state
    from pay_app_workflow import process_pay_app_workflow, sub_pay_app_workflow_action
    from accounting_reconcile import reconcile_project_accounting

    if rt.scenario.pay_periods and period_num > rt.scenario.pay_periods:
        return

    db = models['db']
    PayAppProjectState = models['PayAppProjectState']
    User = models['User']
    users = rt.users
    cv = rt.scenario.contract_value

    _, pay_state = get_pay_app_state(PayAppProjectState, rt.project.id)
    sub_sov = pay_state.get('subcontractorSOV') or {}
    sub_hist = pay_state.get('subPayAppHistory') or {}
    sub_lien = pay_state.get('subLienWaivers') or {}
    keys = list(sub_sov.keys())
    if not keys:
        rt.result.add('warning', 'pay_app', f'period {period_num}: no sub SOV keys')
        return

    # G702 gate requires every approved sub SOV to have a pay app for this period
    bill_keys = keys

    pstart, pend = _month_dates(2026, global_month)
    period = pay_state.get('currentPayAppPeriod') or {}
    period['periodNumber'] = period_num
    period['periodStart'] = pstart
    period['periodEnd'] = pend
    period['status'] = 'Draft'
    period['ball_in_court_role'] = 'Creator'
    pay_state['currentPayAppPeriod'] = period

    pay_state['currentPayAppPeriod'] = period
    pay_state['subLienWaivers'] = sub_lien

    bill_pct = 0.04 + (period_num * 0.002)
    for company_key in bill_keys:
        lines = sub_sov.get(company_key) or []
        period_amt = 0.0
        for line in lines:
            sv = float(line.get('scheduled_value') or line.get('original_commitment') or 0)
            bill = round(sv * bill_pct, 2)
            line['work_this_period'] = bill
            period_amt += bill
        entry = {
            'status': 'Draft',
            'periodNumber': period_num,
            'totalBilledThisPeriod': period_amt,
        }
        sub_hist.setdefault(company_key, {})[str(period_num)] = entry
        sub_lien.setdefault(company_key, {})[str(period_num)] = {
            'filename': f'lien-{company_key}-p{period_num}.pdf',
            'uploadedDate': datetime.utcnow().date().isoformat(),
        }
        pay_state['subLienWaivers'] = sub_lien
        try:
            sub_pay_app_workflow_action(pay_state, company_key, 'submit', users['sub'], {'pending_entry': entry})
            sub_pay_app_workflow_action(pay_state, company_key, 'approve', users['pm'], {'pending_entry': entry})
            sub_hist[company_key][str(period_num)]['status'] = 'Approved'
        except ValueError as exc:
            rt.result.add('warning', 'pay_app', f'sub pay app {company_key} p{period_num}: {exc}')

    contractor_sov = pay_state.get('contractorSOV') or []
    billing_total = round(cv * bill_pct * max(1, len(bill_keys) // 2), 2)
    if contractor_sov:
        lid = contractor_sov[0].get('id', 1)
        pay_state['payAppBillingLines'] = {
            str(lid): {'workThisPeriod': billing_total, 'materialsStored': 0},
        }

    pay_state['subPayAppHistory'] = sub_hist
    pay_state['subLienWaivers'] = sub_lien
    save_pay_app_state(PayAppProjectState, db, rt.project.id, pay_state, user_id=None)

    try:
        approve_result = None
        submit_result = process_pay_app_workflow(
            rt.project.id, 'g702', period_num, 'submit', users['pm'], User,
            {}, pay_state,
            PayAppProjectState=PayAppProjectState, db=db,
            ChangeOrder=models['ChangeOrder'],
            ChangeOrderAllocation=models['ChangeOrderAllocation'],
            BudgetProjectState=models['BudgetProjectState'],
            Commitment=models['Commitment'],
            CommitmentAllocation=models['CommitmentAllocation'],
            Project=models['Project'],
            SageSyncEvent=models['SageSyncEvent'],
        )
        pay_state = submit_result['state']
        db.session.commit()
        for actor in (users['pm'], users['owner'], users['acct']):
            approve_result = process_pay_app_workflow(
                rt.project.id, 'g702', period_num, 'approve', actor, User,
                {}, pay_state,
                PayAppProjectState=PayAppProjectState, db=db,
                ChangeOrder=models['ChangeOrder'],
                ChangeOrderAllocation=models['ChangeOrderAllocation'],
                BudgetProjectState=models['BudgetProjectState'],
                Commitment=models['Commitment'],
                CommitmentAllocation=models['CommitmentAllocation'],
                Project=models['Project'],
                SageSyncEvent=models['SageSyncEvent'],
            )
            pay_state = approve_result['state']
            if approve_result.get('final_approved'):
                break
        save_pay_app_state(PayAppProjectState, db, rt.project.id, pay_state, user_id=None)
        rt.pay_periods_completed += 1
        if approve_result and not approve_result.get('final_approved'):
            st = (pay_state.get('currentPayAppPeriod') or {}).get('status')
            rt.result.add('warning', 'pay_app', f'G702 period {period_num} not final-approved (status={st})')
    except ValueError as exc:
        rt.result.add('critical', 'pay_app', f'G702 period {period_num}: {exc}')
    except Exception as exc:
        rt.result.add('critical', 'pay_app', f'G702 period {period_num}: {type(exc).__name__}: {exc}')

    if rt.scenario.reconcile_every <= 1 or period_num % rt.scenario.reconcile_every == 0:
        reconcile_project_accounting(
            rt.project.id, None,
            ChangeOrder=models['ChangeOrder'],
            ChangeOrderAllocation=models['ChangeOrderAllocation'],
            Commitment=models['Commitment'],
            CommitmentAllocation=models['CommitmentAllocation'],
            BudgetProjectState=models['BudgetProjectState'],
            PayAppProjectState=PayAppProjectState,
            db=db,
        )


def _verify_user_access(rt: ProjectRuntime, models: dict) -> None:
    from project_access import user_can_access_project, enforcement_enabled
    from financial_security import require_financial_project_access

    if not rt.user_pool:
        return
    Project = models['Project']
    PM = models.get('ProjectMembership')
    sample = random.sample(rt.user_pool, min(5, len(rt.user_pool)))
    denied = 0
    for u in sample:
        if not user_can_access_project(u, rt.project.id, Project, PM):
            denied += 1
            rt.result.add('warning', 'access', f'User {u.email} cannot access assigned project')
        try:
            require_financial_project_access(u, rt.project.id, Project)
        except (ValueError, PermissionError):
            denied += 1
    rt.result.metrics['access_checks_denied'] = denied
    rt.result.metrics['membership_enforced'] = enforcement_enabled()


def _run_month_tick(rt: ProjectRuntime, models: dict, global_month: int) -> None:
    sc = rt.scenario
    if not sc.start_month <= global_month <= sc.end_month:
        return
    local = global_month - sc.start_month
    rt.local_month = local
    try:
        if not rt.setup_done:
            _setup_project(rt, models, global_month)
        _spawn_rfis(rt, models, sc.rfi_per_month, global_month)
        _spawn_cos(rt, models, sc.co_per_month, global_month)
        _spawn_submittals(rt, models, sc.submittal_per_month, global_month)
        _spawn_rfqs(rt, models, sc.rfq_per_month, global_month)
        _spawn_change_events(rt, models, sc.change_event_per_month, global_month)
        period_num = local + 1
        _run_pay_period(rt, models, period_num, global_month)
        if local == sc.duration_months - 1:
            _verify_user_access(rt, models)
            rt.result.metrics['pay_periods_completed'] = rt.pay_periods_completed
    except Exception as exc:
        rt.result.add('critical', 'fatal', f'month {global_month}: {type(exc).__name__}: {exc}')
        models['db'].session.rollback()
        traceback.print_exc()


def _overlap_pct(a: ProjectScenario, b: ProjectScenario) -> float:
    start = max(a.start_month, b.start_month)
    end = min(a.end_month, b.end_month)
    if end < start:
        return 0.0
    overlap = end - start + 1
    shorter = min(a.duration_months, b.duration_months)
    return round(overlap / shorter * 100, 1) if shorter else 0.0


def run_portfolio(models: dict, scenarios: list[ProjectScenario] | None = None, *, verbose: bool = True) -> list[ProjectRuntime]:
    scenarios = scenarios or PORTFOLIO_SCENARIOS
    horizons = max(s.end_month for s in scenarios) + 1
    runtimes = [
        ProjectRuntime(scenario=s, result=SimResult(name=s.name, project_id=0))
        for s in scenarios
    ]

    if verbose:
        print('Portfolio timeline overlaps (% of shorter project / % of Mega 100M timeline):')
        mega = max(scenarios, key=lambda s: s.contract_value)
        for i, a in enumerate(scenarios):
            for b in scenarios[i + 1:]:
                pct = _overlap_pct(a, b)
                start = max(a.start_month, b.start_month)
                end = min(a.end_month, b.end_month)
                overlap_months = max(0, end - start + 1)
                mega_pct = round(overlap_months / mega.duration_months * 100, 1) if mega.duration_months else 0
                print(f'  {a.slug} vs {b.slug}: {pct}% shorter / {mega_pct}% of largest timeline')

    for global_month in range(horizons):
        active = [rt for rt in runtimes if rt.scenario.start_month <= global_month <= rt.scenario.end_month]
        if not active:
            continue
        random.shuffle(active)
        if verbose:
            print(f'\n--- Global month {global_month} ({len(active)} active projects) ---')
            for rt in active:
                print(f'  tick: {rt.scenario.name} (local month {global_month - rt.scenario.start_month})')
        elif global_month % 6 == 0 or global_month == horizons - 1:
            print(f'  month {global_month}/{horizons - 1}: {len(active)} active projects', flush=True)
        for rt in active:
            _run_month_tick(rt, models, global_month)
            models['db'].session.commit()

    return runtimes


def main() -> int:
    import app as app_module
    from unittest.mock import patch
    from app import (
        db, Project, Commitment, CommitmentAllocation,
        ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
        PayAppProjectState, SageSyncEvent, User, RFI,
        ChangeEvent, SubcontractorRFQ, RFQAllocation,
        ChangeOrderRequest, CORAllocation, PotentialChangeOrder, PCOAllocation,
    )
    from case_workflow import ProjectMembership, ensure_workflow_schema

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
        'RFI': RFI,
        'ChangeEvent': ChangeEvent,
        'SubcontractorRFQ': SubcontractorRFQ,
        'RFQAllocation': RFQAllocation,
        'ChangeOrderRequest': ChangeOrderRequest,
        'CORAllocation': CORAllocation,
        'PotentialChangeOrder': PotentialChangeOrder,
        'PCOAllocation': PCOAllocation,
        'ProjectMembership': ProjectMembership,
    }

    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    runtimes: list[ProjectRuntime] = []
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(db.engine)
            db.session.rollback()
            print('=' * 60)
            print('CONCURRENT PORTFOLIO SIMULATION')
            print('=' * 60)
            runtimes = run_portfolio(models)
    finally:
        sig_patch.stop()

    print(f'\n{"=" * 60}\nPORTFOLIO SUMMARY\n{"=" * 60}')
    critical = warnings = 0
    for rt in runtimes:
        crit = [i for i in rt.result.issues if i.severity == 'critical']
        warn = [i for i in rt.result.issues if i.severity == 'warning']
        critical += len(crit)
        warnings += len(warn)
        print(f'\n{rt.scenario.name} (project {rt.result.project_id}):')
        print(json.dumps(rt.result.metrics, indent=2))
        if not rt.result.issues:
            print('  No issues.')
        for i in rt.result.issues:
            print(f'  [{i.severity}] {i.category}: {i.message}')

    print(f'\nTotal: {len(runtimes)} projects | Critical: {critical} | Warnings: {warnings}')
    return 1 if critical else 0


if __name__ == '__main__':
    raise SystemExit(main())
