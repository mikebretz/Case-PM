#!/usr/bin/env python3
"""
Phased virtual stress tests — run until clean, then expand.

  python3 scripts/simulate_stress_suite.py --phase g702-gate
  python3 scripts/simulate_stress_suite.py --phase accounting
  python3 scripts/simulate_stress_suite.py --phase workflows
  python3 scripts/simulate_stress_suite.py --phase all
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, '/workspace')

from scripts.simulate_financial_project import (  # noqa: E402
    RETAINAGE_PCT,
    TRADE_MIX_C,
    SimResult,
    _approve_commitment,
    _ensure_sim_users,
)


@dataclass
class StressCase:
    name: str
    passed: bool = False
    message: str = ''


@dataclass
class StressPhaseResult:
    phase: str
    cases: list[StressCase] = field(default_factory=list)

    def fail(self, name: str, message: str):
        self.cases.append(StressCase(name, False, message))

    def ok(self, name: str, message: str = 'ok'):
        self.cases.append(StressCase(name, True, message))

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.cases if not c.passed)


def _build_models(app_module):
    from app import (
        db, Project, Commitment, CommitmentAllocation,
        ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
        PayAppProjectState, SageSyncEvent, User, RFI,
        ChangeEvent, SubcontractorRFQ, RFQAllocation,
        ChangeOrderRequest, CORAllocation, PotentialChangeOrder, PCOAllocation,
    )
    from case_workflow import ProjectMembership
    return {
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
        'ScheduleData': getattr(app_module, 'ScheduleData', None),
    }


def _setup_stress_project(models, contract_value=50_000_000.0, trade_mix=None, gate_scope='all_approved_subs'):
    """Create project with approved commitments + sub SOV ready for pay app tests."""
    from budget_persistence import save_budget_state
    from pay_app_persistence import get_pay_app_state, save_pay_app_state
    from commitment_persistence import save_allocations
    from pay_app_workflow import sub_sov_workflow_action

    trade_mix = trade_mix or TRADE_MIX_C
    db = models['db']
    Project = models['Project']
    Commitment = models['Commitment']
    CommitmentAllocation = models['CommitmentAllocation']
    BudgetProjectState = models['BudgetProjectState']
    PayAppProjectState = models['PayAppProjectState']
    User = models['User']
    users = _ensure_sim_users(db, User)
    uid = uuid.uuid4().hex[:8]

    project = Project(
        number=f'STRESS-{uid}',
        name=f'Stress harness {uid}',
        client='Stress Owner',
        contract_value=contract_value,
        status='Active',
    )
    db.session.add(project)
    db.session.commit()

    budget_lines = []
    for code, desc, pct, _ctype in trade_mix:
        if 'Contingency' in desc:
            continue
        budget_lines.append({
            'cost_code': code,
            'description': desc,
            'original_budget': round(contract_value * pct, 2),
            'approved_changes': 0,
            'pending': 0,
            'committed': 0,
            'actual': 0,
            'cost_type': 'Subcontract',
        })
    save_budget_state(BudgetProjectState, db, project.id, {
        'budgetLines': budget_lines,
        'budgetContractAmount': contract_value,
        'budgetRevision': 1,
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

    save_pay_app_state(PayAppProjectState, db, project.id, {
        'contractorSOV': contractor_sov,
        'subcontractorSOV': {},
        'subSOVStatus': {},
        'subPayAppHistory': {},
        'subLienWaivers': {},
        'payAppRetainagePercent': RETAINAGE_PCT,
        'requireLienWaiverOnSubPayApp': True,
        'requireAllSubPayAppsBeforeG702Submit': True,
        'g702PayAppGateScope': gate_scope,
        'currentPayAppPeriod': {
            'periodNumber': 1,
            'status': 'Draft',
            'periodStart': '2026-01-01',
            'periodEnd': '2026-01-31',
            'ball_in_court_role': 'Creator',
        },
        'payAppBillingLines': {},
    }, user_id=None)

    commitments = []
    cid = project.id * 1000
    for code, desc, pct, ctype in trade_mix:
        if ctype == 'Service Agreement':
            continue
        cid += 1
        amt = round(contract_value * pct * 0.98, 2)
        com = Commitment(
            project_id=project.id,
            number=f'SC-{cid}',
            commitment_type=ctype,
            company_name=f'{desc} Co',
            company_id=str(cid),
            title=desc,
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
        commitments.append(com)
    db.session.commit()

    for com in commitments:
        _approve_commitment(com, CommitmentAllocation, users, models)

    _, pay_state = get_pay_app_state(PayAppProjectState, project.id)
    for key in list((pay_state.get('subcontractorSOV') or {}).keys()):
        sub_sov_workflow_action(pay_state, key, 'submit', users['sub'])
        sub_sov_workflow_action(pay_state, key, 'approve', users['pm'])
    pay_state['g702PayAppGateScope'] = gate_scope
    save_pay_app_state(PayAppProjectState, db, project.id, pay_state, user_id=None)

    return project, users, commitments


def _bill_subs(
    models, project_id, users, period_num,
    fraction: float,
    *,
    rotate_offset: int = 0,
    gate_scope: str | None = None,
) -> dict:
    """Bill a fraction of subs; return pay_state after updates."""
    from pay_app_persistence import get_pay_app_state, save_pay_app_state
    from pay_app_workflow import sub_pay_app_workflow_action, validate_g702_submit_gates, process_pay_app_workflow

    PayAppProjectState = models['PayAppProjectState']
    _, pay_state = get_pay_app_state(PayAppProjectState, project_id)
    if gate_scope:
        pay_state['g702PayAppGateScope'] = gate_scope

    sub_sov = pay_state.get('subcontractorSOV') or {}
    keys = list(sub_sov.keys())
    count = max(1, int(len(keys) * fraction)) if fraction < 1.0 else len(keys)
    if fraction < 1.0:
        start = rotate_offset % len(keys)
        bill_keys = [keys[(start + i) % len(keys)] for i in range(count)]
    else:
        bill_keys = keys

    sub_hist = pay_state.get('subPayAppHistory') or {}
    sub_lien = pay_state.get('subLienWaivers') or {}

    period = pay_state.get('currentPayAppPeriod') or {}
    period['periodNumber'] = period_num
    period['status'] = 'Draft'
    period['ball_in_court_role'] = 'Creator'
    pay_state['currentPayAppPeriod'] = period

    for company_key in keys:
        for line in sub_sov.get(company_key) or []:
            if isinstance(line, dict):
                line['work_this_period'] = 0

    for company_key in bill_keys:
        period_amt = 0.0
        for line in sub_sov.get(company_key) or []:
            sv = float(line.get('scheduled_value') or line.get('original_commitment') or 0)
            bill = round(sv * 0.05, 2)
            line['work_this_period'] = bill
            period_amt += bill
        entry = {'status': 'Draft', 'periodNumber': period_num, 'totalBilledThisPeriod': period_amt}
        sub_hist.setdefault(company_key, {})[str(period_num)] = entry
        sub_lien.setdefault(company_key, {})[str(period_num)] = {
            'filename': f'lien-{company_key}-p{period_num}.pdf',
            'uploadedDate': datetime.utcnow().date().isoformat(),
        }
        pay_state['subLienWaivers'] = sub_lien
        sub_pay_app_workflow_action(pay_state, company_key, 'submit', users['sub'], {'pending_entry': entry})
        sub_pay_app_workflow_action(pay_state, company_key, 'approve', users['pm'], {'pending_entry': entry})
        sub_hist[company_key][str(period_num)]['status'] = 'Approved'

    pay_state['subPayAppHistory'] = sub_hist
    pay_state['subcontractorSOV'] = sub_sov
    contractor_sov = pay_state.get('contractorSOV') or []
    if contractor_sov:
        lid = contractor_sov[0].get('id', 1)
        pay_state['payAppBillingLines'] = {
            str(lid): {'workThisPeriod': round(50_000 * len(bill_keys), 2), 'materialsStored': 0},
        }
    save_pay_app_state(PayAppProjectState, models['db'], project_id, pay_state, user_id=None)
    return pay_state, bill_keys


def _try_g702_submit(models, project_id, users, pay_state) -> tuple[bool, str, dict]:
    from pay_app_persistence import save_pay_app_state
    from pay_app_workflow import process_pay_app_workflow, validate_g702_submit_gates
    try:
        validate_g702_submit_gates(pay_state)
    except ValueError as exc:
        return False, str(exc), pay_state
    try:
        r = process_pay_app_workflow(
            project_id, 'g702', pay_state['currentPayAppPeriod']['periodNumber'], 'submit', users['pm'],
            models['User'], {}, pay_state,
            PayAppProjectState=models['PayAppProjectState'], db=models['db'],
            ChangeOrder=models['ChangeOrder'], ChangeOrderAllocation=models['ChangeOrderAllocation'],
            BudgetProjectState=models['BudgetProjectState'], Commitment=models['Commitment'],
            CommitmentAllocation=models['CommitmentAllocation'], Project=models['Project'],
            SageSyncEvent=models['SageSyncEvent'],
        )
        pay_state = r['state']
        save_pay_app_state(
            models['PayAppProjectState'], models['db'], project_id, pay_state, user_id=None,
        )
        models['db'].session.commit()
        return True, 'submitted', pay_state
    except ValueError as exc:
        return False, str(exc), pay_state


def _approve_g702_chain(models, project_id, users, pay_state) -> tuple[bool, str, dict]:
    from pay_app_persistence import save_pay_app_state
    from pay_app_workflow import process_pay_app_workflow

    period_num = pay_state['currentPayAppPeriod']['periodNumber']
    try:
        for actor in (users['pm'], users['owner'], users['acct']):
            r = process_pay_app_workflow(
                project_id, 'g702', period_num, 'approve', actor, models['User'], {}, pay_state,
                PayAppProjectState=models['PayAppProjectState'], db=models['db'],
                ChangeOrder=models['ChangeOrder'], ChangeOrderAllocation=models['ChangeOrderAllocation'],
                BudgetProjectState=models['BudgetProjectState'], Commitment=models['Commitment'],
                CommitmentAllocation=models['CommitmentAllocation'], Project=models['Project'],
                SageSyncEvent=models['SageSyncEvent'],
            )
            pay_state = r['state']
            if r.get('final_approved'):
                break
        save_pay_app_state(
            models['PayAppProjectState'], models['db'], project_id, pay_state, user_id=None,
        )
        models['db'].session.commit()
        return True, 'approved', pay_state
    except ValueError as exc:
        return False, str(exc), pay_state


def run_phase_g702_gate(models) -> StressPhaseResult:
    result = StressPhaseResult('g702-gate')
    print('\n=== PHASE: G702 partial sub-billing gate ===\n')

    # 1. Partial 25% must block (all subs scope)
    try:
        models['db'].session.rollback()
        project, users, _ = _setup_stress_project(models, gate_scope='all_approved_subs')
        pay_state, billed = _bill_subs(models, project.id, users, 1, 0.25)
        ok, msg, _ = _try_g702_submit(models, project.id, users, pay_state)
        if ok:
            result.fail('partial_25_blocks', f'G702 submitted with only {len(billed)} subs billed — expected block')
        elif 'missing pay applications' in msg.lower():
            result.ok('partial_25_blocks', f'correctly blocked: {msg[:120]}')
        else:
            result.fail('partial_25_blocks', f'unexpected error: {msg}')
    except Exception as exc:
        result.fail('partial_25_blocks', traceback.format_exc().splitlines()[-1])

    # 2. Partial 50% must block
    try:
        models['db'].session.rollback()
        project, users, _ = _setup_stress_project(models, gate_scope='all_approved_subs')
        pay_state, billed = _bill_subs(models, project.id, users, 1, 0.50)
        ok, msg, _ = _try_g702_submit(models, project.id, users, pay_state)
        if ok:
            result.fail('partial_50_blocks', 'G702 submitted with only 50% subs billed')
        elif 'missing pay applications' in msg.lower():
            result.ok('partial_50_blocks', f'blocked ({len(billed)} subs billed)')
        else:
            result.fail('partial_50_blocks', msg)
    except Exception as exc:
        result.fail('partial_50_blocks', str(exc))

    # 3. Full billing must succeed
    try:
        models['db'].session.rollback()
        project, users, _ = _setup_stress_project(models, gate_scope='all_approved_subs')
        pay_state, billed = _bill_subs(models, project.id, users, 1, 1.0)
        ok, msg, _ = _try_g702_submit(models, project.id, users, pay_state)
        if ok:
            result.ok('full_billing_submits', f'all {len(billed)} subs billed')
        else:
            result.fail('full_billing_submits', msg)
    except Exception as exc:
        result.fail('full_billing_submits', str(exc))

    # 4. billed_this_period scope — partial OK
    try:
        models['db'].session.rollback()
        project, users, _ = _setup_stress_project(models, gate_scope='billed_this_period')
        pay_state, billed = _bill_subs(models, project.id, users, 1, 0.35, gate_scope='billed_this_period')
        ok, msg, _ = _try_g702_submit(models, project.id, users, pay_state)
        if ok:
            result.ok('billed_scope_partial_ok', f'{len(billed)} subs billed, G702 submitted')
        else:
            result.fail('billed_scope_partial_ok', msg)
    except Exception as exc:
        result.fail('billed_scope_partial_ok', str(exc))

    # 5. Recovery: partial fail then complete
    try:
        models['db'].session.rollback()
        project, users, _ = _setup_stress_project(models, gate_scope='all_approved_subs')
        pay_state, _ = _bill_subs(models, project.id, users, 1, 0.30)
        ok1, _, _ = _try_g702_submit(models, project.id, users, pay_state)
        pay_state, _ = _bill_subs(models, project.id, users, 1, 1.0)
        ok2, msg2, _ = _try_g702_submit(models, project.id, users, pay_state)
        if ok1:
            result.fail('recovery_partial_then_full', 'first partial submit should have failed')
        elif ok2:
            result.ok('recovery_partial_then_full', 'blocked then succeeded after full billing')
        else:
            result.fail('recovery_partial_then_full', msg2)
    except Exception as exc:
        result.fail('recovery_partial_then_full', str(exc))

    # 6. Rotation stress — 8 periods, 40% rotating, billed_this_period scope
    try:
        models['db'].session.rollback()
        project, users, _ = _setup_stress_project(models, gate_scope='billed_this_period')
        failures = 0
        for p in range(1, 9):
            pay_state, billed = _bill_subs(
                models, project.id, users, p, 0.40,
                rotate_offset=p * 3, gate_scope='billed_this_period',
            )
            ok, msg, _ = _try_g702_submit(models, project.id, users, pay_state)
            if not ok:
                failures += 1
                result.fail(f'rotation_period_{p}', msg)
        if failures == 0:
            result.ok('rotation_8_periods', '8 rotating partial-bill periods all submitted G702')
    except Exception as exc:
        result.fail('rotation_8_periods', str(exc))

    return result


def run_phase_accounting(models) -> StressPhaseResult:
    from accounting_reconcile import reconcile_project_accounting
    from budget_persistence import get_budget_state
    from pay_app_persistence import get_pay_app_state
    from change_event_persistence import accept_sage_event_for_export

    result = StressPhaseResult('accounting')
    print('\n=== PHASE: Accounting reconcile & Sage ===\n')

    try:
        project, users, commitments = _setup_stress_project(models, contract_value=30_000_000.0)
        pay_periods = 6
        for p in range(1, pay_periods + 1):
            pay_state, _ = _bill_subs(models, project.id, users, p, 1.0)
            ok, msg, pay_state = _try_g702_submit(models, project.id, users, pay_state)
            if not ok:
                result.fail(f'accounting_g702_p{p}', msg)
                break
            ok, msg, pay_state = _approve_g702_chain(models, project.id, users, pay_state)
            if not ok:
                result.fail(f'accounting_g702_approve_p{p}', msg)
                break
            recon = reconcile_project_accounting(
                project.id, None,
                ChangeOrder=models['ChangeOrder'], ChangeOrderAllocation=models['ChangeOrderAllocation'],
                Commitment=models['Commitment'], CommitmentAllocation=models['CommitmentAllocation'],
                BudgetProjectState=models['BudgetProjectState'], PayAppProjectState=models['PayAppProjectState'],
                db=models['db'],
            )
            _, budget = get_budget_state(models['BudgetProjectState'], project.id)
            actual = sum(float(l.get('actual') or 0) for l in budget.get('budgetLines') or [])
            if abs(actual - recon.get('actual_cost_applied', 0)) > 5000:
                result.fail(f'accounting_drift_p{p}', f'budget actual {actual} != recon {recon.get("actual_cost_applied")}')
        else:
            result.ok('accounting_6_periods', '6 periods reconciled without drift')

        events = models['SageSyncEvent'].query.filter_by(
            project_id=project.id, accounting_status='pending_review',
        ).limit(10).all()
        accepted = 0
        for ev in events:
            accept_sage_event_for_export(ev, users['acct'], models['db'], Commitment=models['Commitment'])
            accepted += 1
        models['db'].session.commit()
        if accepted > 0:
            result.ok('sage_accept_batch', f'{accepted} events accepted')
        else:
            result.ok('sage_accept_batch', 'no pending events (ok)')

        expected_commit = sum(float(c.current_amount or 0) for c in commitments if c.status == 'Approved')
        _, budget = get_budget_state(models['BudgetProjectState'], project.id)
        committed = sum(float(l.get('committed') or 0) for l in budget.get('budgetLines') or [])
        if abs(committed - expected_commit) > 10_000:
            result.fail('budget_committed_match', f'committed {committed} vs expected {expected_commit}')
        else:
            result.ok('budget_committed_match', f'committed ${committed:,.0f}')

    except Exception as exc:
        result.fail('accounting_fatal', traceback.format_exc().splitlines()[-1])

    return result


def run_phase_workflows(models) -> StressPhaseResult:
    from scripts.simulate_concurrent_portfolio import (
        _spawn_rfis, _setup_project as portfolio_setup,
        ProjectRuntime, ProjectScenario, TRADE_MIX_SMALL,
    )

    result = StressPhaseResult('workflows')
    print('\n=== PHASE: Document workflows under load ===\n')

    try:
        sc = ProjectScenario(
            name='Workflow-Stress',
            slug='wfstress',
            contract_value=25_000_000.0,
            trade_mix=TRADE_MIX_SMALL,
            user_count=20,
            start_month=0,
            duration_months=1,
            rfi_per_month=15.0,
            co_per_month=5.0,
            pay_periods=1,
        )
        rt = ProjectRuntime(scenario=sc, result=SimResult(name=sc.name, project_id=0))
        portfolio_setup(rt, models, 0)

        from scripts.simulate_concurrent_portfolio import _spawn_cos, _run_pay_period
        _spawn_rfis(rt, models, 15, 0)
        _spawn_cos(rt, models, 5, 0)
        _run_pay_period(rt, models, 1, 0)

        crit = [i for i in rt.result.issues if i.severity == 'critical']
        if crit:
            for i in crit[:5]:
                result.fail('workflow_load', f'{i.category}: {i.message}')
        else:
            result.ok('workflow_load', f'RFIs={rt.result.metrics.get("rfis_created",0)} COs={rt.result.metrics.get("cos_created",0)}')

        from change_event_persistence import rfq_workflow_action, save_generic_allocations
        sub_com = next((c for c in rt.commitments if c.commitment_type == 'Subcontract'), None)
        rfq = models['SubcontractorRFQ'](
            project_id=rt.project.id,
            number=f'RFQ-STRESS-{rt.uid}',
            title='Stress RFQ',
            status='Draft',
            ball_in_court_role='Creator',
            company_id=sub_com.company_id if sub_com else '1',
            created_by_id=rt.users['pm'].id,
        )
        models['db'].session.add(rfq)
        models['db'].session.flush()
        save_generic_allocations(models['RFQAllocation'], 'rfq_id', rfq.id, [{
            'cost_code': '09-250', 'cost_type': 'Subcontract', 'amount': 100_000,
        }], models['db'])
        rfq_workflow_action(rfq, 'send', rt.users['pm'])
        rfq_workflow_action(rfq, 'quote', rt.users['sub'], [{
            'cost_code': '09-250', 'amount': 100_000, 'quoted_amount': 105_000,
        }])
        rfq_workflow_action(rfq, 'accept', rt.users['pm'])
        models['db'].session.commit()
        result.ok('rfq_chain', f'RFQ status={rfq.status}')

    except Exception as exc:
        result.fail('workflows_fatal', traceback.format_exc().splitlines()[-1])

    return result


def _print_phase(result: StressPhaseResult) -> int:
    print(f'\n--- {result.phase} results ---')
    for c in result.cases:
        mark = 'PASS' if c.passed else 'FAIL'
        print(f'  [{mark}] {c.name}: {c.message}')
    crit = result.critical_count
    print(f'  => {len(result.cases) - crit}/{len(result.cases)} passed')
    return crit


def main():
    parser = argparse.ArgumentParser(description='Phased stress test suite')
    parser.add_argument(
        '--phase',
        choices=['g702-gate', 'accounting', 'workflows', 'all'],
        default='g702-gate',
    )
    args = parser.parse_args()

    import app as app_module
    from unittest.mock import patch
    from case_workflow import ensure_workflow_schema

    models = _build_models(app_module)
    phases = {
        'g702-gate': [run_phase_g702_gate],
        'accounting': [run_phase_accounting],
        'workflows': [run_phase_workflows],
        'all': [run_phase_g702_gate, run_phase_accounting, run_phase_workflows],
    }

    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    total_crit = 0
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(models['db'].engine)
            models['db'].session.rollback()
            for fn in phases[args.phase]:
                pr = fn(models)
                total_crit += _print_phase(pr)
    finally:
        sig_patch.stop()

    print(f'\n{"=" * 60}\nSTRESS SUITE: {total_crit} failure(s)\n{"=" * 60}')
    return 1 if total_crit else 0


if __name__ == '__main__':
    raise SystemExit(main())
