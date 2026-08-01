#!/usr/bin/env python3
"""
Single-job lifecycle: $100M contract, ~150 RFIs, 100 COs totaling $10M,
estimating → commitments → 24-month PM/accounting → change-event chain → closeout.

  PYTHONPATH=/workspace python3 scripts/simulate_hundred_million_lifecycle.py
  PYTHONPATH=/workspace python3 scripts/simulate_hundred_million_lifecycle.py --report /tmp/hundred_m_sim.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import traceback
from datetime import datetime

sys.path.insert(0, '/workspace')

from scripts.simulate_concurrent_portfolio import (  # noqa: E402
    ProjectRuntime,
    ProjectScenario,
    _approve_co_smart,
    _run_month_tick,
    _setup_project,
    _spawn_rfis,
    _spawn_submittals,
    _spawn_rfqs,
    _spawn_change_events,
)
from scripts.simulate_financial_project import (  # noqa: E402
    CONTRACT_VALUE_100M,
    TRADE_MIX_C,
    SimIssue,
    SimResult,
    _ensure_sim_users,
    _run_extended_modules,
)

TARGET_RFIS = 150
TARGET_COS = 100
TARGET_CO_VALUE = 10_000_000.0
DURATION_MONTHS = 24


def _spawn_cos_fixed_total(
    rt: ProjectRuntime,
    models: dict,
    count: int,
    total_value: float,
    *,
    approve_rate: float = 0.72,
) -> None:
    """Create exactly `count` owner COs whose signed allocation sum ≈ total_value."""
    if count <= 0:
        return
    ChangeOrder = models['ChangeOrder']
    ChangeOrderAllocation = models['ChangeOrderAllocation']
    db = models['db']
    codes = [c[0] for c in rt.scenario.trade_mix if not c[0].startswith('01-')]
    if not codes:
        codes = ['09-250']

    weights = [random.uniform(0.3, 1.0) for _ in range(count)]
    deduct_idx = random.sample(range(count), k=max(1, count // 10))
    signed = []
    for i, w in enumerate(weights):
        sign = -1 if i in deduct_idx else 1
        signed.append(sign * w)
    gross = sum(abs(x) for x in signed) or 1.0
    scale = total_value / gross
    amounts = [round(x * scale, 2) for x in signed]
    drift = round(total_value - sum(abs(a) for a in amounts), 2)
    if amounts:
        amounts[0] = round(amounts[0] + (drift if amounts[0] >= 0 else -drift), 2)

    approved = pending = failed = 0
    for i, amt in enumerate(amounts, start=1):
        rt.co_seq += 1
        code = random.choice(codes)
        num = f'CO-{rt.uid}-BULK-{i:04d}'
        co = ChangeOrder(
            project_id=rt.project.id,
            number=num,
            title=f'Bulk sim change order {i}',
            description=f'Scope change package {i} on $100M campus',
            status='Draft',
            amount=abs(amt),
            cost_code=code,
            ball_in_court_role='Creator',
            priority=random.choice(['Low', 'Medium', 'High', 'Critical']),
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
        if random.random() < approve_rate:
            try:
                st = _approve_co_smart(co, rt.users, models)
                if st == 'Approved':
                    approved += 1
                else:
                    failed += 1
                    rt.result.add('warning', 'change_order', f'{num} bulk ended {st}')
            except ValueError as exc:
                failed += 1
                rt.result.add('warning', 'change_order', f'{num}: {exc}')
        else:
            co.status = random.choice(['Submitted', 'Pending Owner', 'Pending Architect'])
            co.ball_in_court_role = random.choice(['Owner', 'Architect', 'Project Manager'])
            db.session.commit()
            pending += 1

    actual = sum(
        float(a.amount or 0)
        for co in ChangeOrder.query.filter_by(project_id=rt.project.id).all()
        for a in ChangeOrderAllocation.query.filter_by(change_order_id=co.id).all()
    )
    rt.result.metrics['bulk_cos'] = count
    rt.result.metrics['bulk_co_approved'] = approved
    rt.result.metrics['bulk_co_pending'] = pending
    rt.result.metrics['bulk_co_failed'] = failed
    rt.result.metrics['bulk_co_allocation_sum'] = round(actual, 2)
    if abs(abs(actual) - total_value) > 5000:
        rt.result.add(
            'warning',
            'change_order',
            f'Bulk CO allocation sum ${actual:,.2f} vs target ${total_value:,.2f}',
        )


def _run_estimating_bid(rt: ProjectRuntime, models: dict) -> None:
    """Seed estimate + bid packages at ~$100M before field execution."""
    from estimate_persistence import apply_estimate_fields, save_estimate_lines, recalc_estimate_totals

    Estimate = models.get('Estimate')
    EstimateLine = models.get('EstimateLine')
    BidPackage = models.get('BidPackage')
    if not Estimate or not EstimateLine:
        rt.result.add('warning', 'estimating', 'Estimate models unavailable — skipping bid phase')
        return

    db = models['db']
    users = rt.users
    cv = rt.scenario.contract_value
    est = Estimate(
        project_id=rt.project.id,
        number='EST-100M-001',
        title='Campus GMP Hard Bid',
        status='In Progress',
        estimate_type='Hard Bid',
        contingency_pct=3.0,
        overhead_pct=8.0,
        profit_pct=7.0,
        created_by_id=users['pm'].id,
    )
    apply_estimate_fields(est, {})
    db.session.add(est)
    db.session.flush()

    lines = []
    for i, (code, desc, pct, ctype) in enumerate(rt.scenario.trade_mix):
        ext = round(cv * pct, 2)
        lines.append({
            'sort_order': i,
            'cost_code': code,
            'description': desc,
            'cost_type': ctype,
            'quantity': 1,
            'unit_cost': ext,
            'extended_cost': ext,
            'line_kind': 'base',
        })
    save_estimate_lines(EstimateLine, est.id, lines, db)
    recalc_estimate_totals(Estimate, EstimateLine, est.id)
    db.session.commit()
    rt.result.metrics['estimate_id'] = est.id
    sell = float(est.total_amount or 0)
    direct = float(est.direct_cost_total or 0)
    rt.result.metrics['estimate_total'] = sell
    rt.result.metrics['estimate_direct_cost'] = direct
    if sell > 0 and rt.project:
        rt.project.contract_value = sell
        db.session.commit()
        rt.result.metrics['contract_value_synced'] = sell
    if abs(direct - cv) > 250_000:
        rt.result.add(
            'warning',
            'estimating',
            f'Estimate direct cost ${direct:,.0f} vs budget contract ${cv:,.0f}',
        )

    if BidPackage:
        pkg_count = 0
        for code, desc, pct, _ctype in rt.scenario.trade_mix[:8]:
            if pct < 0.03:
                continue
            pkg = BidPackage(
                estimate_id=est.id,
                project_id=rt.project.id,
                number=f'BP-{code.replace("-", "")}',
                title=f'{desc} bid package',
                spec_section=code,
                status='Open',
            )
            db.session.add(pkg)
            pkg_count += 1
        db.session.commit()
        rt.result.metrics['bid_packages'] = pkg_count


def _closeout(rt: ProjectRuntime, models: dict) -> None:
    from accounting_reconcile import reconcile_project_accounting
    from budget_persistence import get_budget_state, summarize_change_orders_for_budget
    from project_closeout import closeout_readiness

    db = models['db']
    Project = models['Project']
    project = Project.query.get(rt.project.id)
    if not project:
        rt.result.add('critical', 'closeout', 'Project missing at closeout')
        return

    report = closeout_readiness(
        project.id,
        RFI=models['RFI'],
        ChangeOrder=models['ChangeOrder'],
        Submittal=models.get('Submittal'),
        PotentialChangeOrder=models.get('PotentialChangeOrder'),
    )
    rt.result.metrics['closeout'] = report
    rt.result.metrics['closeout_open_rfis'] = report['counts'].get('open_rfis', 0)
    rt.result.metrics['closeout_pending_cos'] = report['counts'].get('pending_change_orders', 0)
    for msg in report.get('warnings') or []:
        rt.result.add('info', 'closeout', msg)
    if not report.get('ok'):
        for msg in report.get('blocking') or []:
            rt.result.add('warning', 'closeout', msg)
        rt.result.add('info', 'closeout', 'Project left Active — closeout gate blocked completion (expected until RFIs/COs cleared)')
        return

    recon = reconcile_project_accounting(
        project.id,
        None,
        ChangeOrder=models['ChangeOrder'],
        ChangeOrderAllocation=models['ChangeOrderAllocation'],
        Commitment=models['Commitment'],
        CommitmentAllocation=models['CommitmentAllocation'],
        BudgetProjectState=models['BudgetProjectState'],
        PayAppProjectState=models['PayAppProjectState'],
        db=db,
    )
    rt.result.metrics['closeout_reconcile'] = recon

    co_summary = summarize_change_orders_for_budget(
        models['ChangeOrder'], models['ChangeOrderAllocation'], project.id,
    )
    rt.result.metrics['change_order_summary'] = co_summary

    _budget_rec, budget = get_budget_state(models['BudgetProjectState'], project.id)
    approved_chg = co_summary.get('approved_net') or sum(
        float(l.get('approved_changes') or 0) for l in (budget or {}).get('budgetLines') or []
    )
    rt.result.metrics['budget_approved_changes'] = approved_chg

    project.status = 'Complete'
    db.session.commit()
    rt.result.metrics['project_status'] = project.status


def run_hundred_million_lifecycle(*, seed: int = 100) -> ProjectRuntime:
    random.seed(seed)
    import app as app_module
    from unittest.mock import patch
    from app import (
        db,
        Project,
        Commitment,
        CommitmentAllocation,
        ChangeOrder,
        ChangeOrderAllocation,
        BudgetProjectState,
        PayAppProjectState,
        SageSyncEvent,
        User,
        RFI,
        Submittal,
        ChangeEvent,
        SubcontractorRFQ,
        RFQAllocation,
        ChangeOrderRequest,
        CORAllocation,
        PotentialChangeOrder,
        PCOAllocation,
        ChangeEventLineItem,
        Estimate,
        EstimateLine,
        BidPackage,
    )
    from case_workflow import ProjectMembership, ensure_workflow_schema

    scenario = ProjectScenario(
        name='Lifecycle-100M-Closeout',
        slug='life100',
        contract_value=CONTRACT_VALUE_100M,
        trade_mix=TRADE_MIX_C,
        user_count=120,
        start_month=0,
        duration_months=DURATION_MONTHS,
        rfi_per_month=0,
        co_per_month=0,
        pay_periods=DURATION_MONTHS,
        submittal_per_month=4.0,
        rfq_per_month=1.2,
        change_event_per_month=0.8,
    )
    rt = ProjectRuntime(scenario=scenario, result=SimResult(name=scenario.name, project_id=0))
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
        'Submittal': Submittal,
        'ChangeEvent': ChangeEvent,
        'SubcontractorRFQ': SubcontractorRFQ,
        'RFQAllocation': RFQAllocation,
        'ChangeOrderRequest': ChangeOrderRequest,
        'CORAllocation': CORAllocation,
        'PotentialChangeOrder': PotentialChangeOrder,
        'PCOAllocation': PCOAllocation,
        'ChangeEventLineItem': ChangeEventLineItem,
        'ProjectMembership': ProjectMembership,
        'ScheduleData': getattr(app_module, 'ScheduleData', None),
        'Estimate': Estimate,
        'EstimateLine': EstimateLine,
        'BidPackage': BidPackage,
    }

    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(db.engine)
            db.session.rollback()
            _ensure_sim_users(db, User)

            print('Phase 1: Project setup + commitments + budget/SOV…')
            _setup_project(rt, models, global_month=0)
            _run_estimating_bid(rt, models)

            print(f'Phase 2: Bulk documents — {TARGET_RFIS} RFIs, {TARGET_COS} COs (${TARGET_CO_VALUE/1e6:.0f}M)…')
            _spawn_rfis(rt, models, TARGET_RFIS, global_month=0)
            _spawn_cos_fixed_total(rt, models, TARGET_COS, TARGET_CO_VALUE)

            print(f'Phase 3: Monthly PM + pay apps ({DURATION_MONTHS} periods)…')
            for gm in range(scenario.duration_months):
                _spawn_submittals(rt, models, scenario.submittal_per_month, gm)
                _spawn_rfqs(rt, models, scenario.rfq_per_month, gm)
                _spawn_change_events(rt, models, scenario.change_event_per_month, gm)
                if gm > 0:
                    _spawn_rfis(rt, models, 0.5, gm)
                from scripts.simulate_concurrent_portfolio import _run_pay_period

                _run_pay_period(rt, models, gm + 1, gm)
                db.session.commit()

            print('Phase 4: Extended change-event chain (COR/PCO/RFQ/CPCO/SCO)…')
            commitments = list(
                Commitment.query.filter_by(project_id=rt.project.id).all()
            )
            try:
                _run_extended_modules(rt.result, rt.project, rt.users, models, commitments)
            except Exception as exc:
                rt.result.add('critical', 'extended', f'{type(exc).__name__}: {exc}')
                traceback.print_exc()

            print('Phase 5: Closeout + reconcile…')
            _closeout(rt, models)

            rt.result.metrics['rfis_total'] = RFI.query.filter_by(project_id=rt.project.id).count()
            rt.result.metrics['cos_total'] = ChangeOrder.query.filter_by(project_id=rt.project.id).count()
    finally:
        sig_patch.stop()

    return rt


def _issue_dict(i: SimIssue) -> dict:
    return {'severity': i.severity, 'category': i.category, 'message': i.message, 'project': i.project}


def main() -> int:
    parser = argparse.ArgumentParser(description='$100M lifecycle simulation')
    parser.add_argument('--report', default='', help='Write JSON report path')
    parser.add_argument('--seed', type=int, default=100)
    args = parser.parse_args()

    print('=' * 72)
    print('$100M LIFECYCLE SIMULATION (estimating → closeout)')
    print('=' * 72)
    try:
        rt = run_hundred_million_lifecycle(seed=args.seed)
    except Exception:
        traceback.print_exc()
        return 2

    issues = rt.result.issues
    crit = [i for i in issues if i.severity == 'critical']
    warn = [i for i in issues if i.severity == 'warning']
    info = [i for i in issues if i.severity == 'info']

    print(f'\nProject ID: {rt.result.project_id}')
    print(json.dumps(rt.result.metrics, indent=2))
    print(f'\nIssues: {len(crit)} critical, {len(warn)} warning, {len(info)} info')
    for i in issues:
        print(f'  [{i.severity.upper():8}] {i.category}: {i.message}')

    payload = {
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'project_id': rt.result.project_id,
        'scenario': rt.scenario.name,
        'contract_value': rt.scenario.contract_value,
        'metrics': rt.result.metrics,
        'issues': [_issue_dict(i) for i in issues],
        'summary': {
            'critical': len(crit),
            'warning': len(warn),
            'info': len(info),
        },
    }
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        print(f'\nReport written: {args.report}')

    return 1 if crit else 0


if __name__ == '__main__':
    raise SystemExit(main())
