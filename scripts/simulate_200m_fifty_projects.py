#!/usr/bin/env python3
"""
$200M across 50 jobs — heavy paperwork per project, full PM flow, accounting battery.

  PYTHONPATH=/workspace python3 scripts/simulate_200m_fifty_projects.py
  PYTHONPATH=/workspace python3 scripts/simulate_200m_fifty_projects.py --report /tmp/200m_50.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import traceback
import uuid
from datetime import datetime

sys.path.insert(0, '/workspace')

from scripts.portfolio_accounting_battery import (  # noqa: E402
    run_accounting_battery,
    run_accounting_subprocess_suite,
)
from scripts.simulate_concurrent_portfolio import (  # noqa: E402
    ProjectRuntime,
    ProjectScenario,
    TRADE_MIX_SMALL,
    _approve_co_smart,
    run_portfolio,
)
from scripts.simulate_financial_project import (  # noqa: E402
    _ensure_sim_users,
    _run_extended_modules,
)

TOTAL_CONTRACT_VALUE = 200_000_000.0
JOB_COUNT = 50
HORIZON_CAP = 30
PAPERWORK_BOOST = 2.2


def _distribute_contract_values(total: float, count: int, seed: int) -> list[float]:
    random.seed(seed)
    weights = [random.uniform(0.4, 1.8) for _ in range(count)]
    gross = sum(weights)
    values = [round(total * w / gross / 50_000) * 50_000 for w in weights]
    drift = round(total - sum(values), 2)
    values[0] = round(values[0] + drift, 2)
    return values


def _duration_months(contract_value: float) -> int:
    ratio = contract_value / 8_000_000.0
    return max(10, min(18, round(10 + 8 * min(1.0, ratio))))


def _user_count(contract_value: float) -> int:
    return max(25, min(80, round(25 + contract_value / 120_000)))


def _heavy_activity_rates(contract_value: float) -> dict[str, float]:
    scale = max(0.5, contract_value / 4_000_000.0)
    root = math.sqrt(scale)
    return {
        'rfi_per_month': round(min(16, (5 + 4 * root) * PAPERWORK_BOOST), 1),
        'co_per_month': round(min(8, (2 + 2.5 * root) * PAPERWORK_BOOST), 1),
        'submittal_per_month': round(min(12, (4 + 3 * root) * PAPERWORK_BOOST), 1),
        'rfq_per_month': round(min(4, (1 + 1.2 * root) * PAPERWORK_BOOST), 1),
        'change_event_per_month': round(min(3.5, (0.8 + 0.9 * root) * PAPERWORK_BOOST), 1),
    }


def _start_month(duration: int, index: int) -> int:
    max_start = max(0, HORIZON_CAP - duration)
    bucket = index % 5
    return min(max_start, bucket * (max_start // 5 + 1))


def build_fifty_scenarios(*, seed: int = 200) -> list[ProjectScenario]:
    values = _distribute_contract_values(TOTAL_CONTRACT_VALUE, JOB_COUNT, seed)
    scenarios = []
    for i, cv in enumerate(values):
        duration = _duration_months(cv)
        start = _start_month(duration, i)
        rates = _heavy_activity_rates(cv)
        scenarios.append(ProjectScenario(
            name=f'PF-{i + 1:02d}-${cv / 1e6:.1f}M',
            slug=f'pf{i + 1:02d}',
            contract_value=cv,
            trade_mix=TRADE_MIX_SMALL,
            user_count=_user_count(cv),
            start_month=start,
            duration_months=duration,
            pay_periods=duration,
            reconcile_every=4,
            **rates,
        ))
    scenarios.sort(key=lambda s: s.contract_value, reverse=True)
    return scenarios


def _print_table(scenarios: list[ProjectScenario]) -> None:
    print(f'\n{"#":>3}  {"Name":<18}  {"Value":>10}  {"Dur":>4}  {"Start":>5}  '
          f'{"RFI":>5}  {"CO":>4}  {"SUB":>4}', flush=True)
    print('-' * 70)
    for i, s in enumerate(scenarios, 1):
        print(
            f'{i:3d}  {s.name:<18}  ${s.contract_value / 1e6:>8.2f}M  {s.duration_months:4d}  '
            f'{s.start_month:5d}  {s.rfi_per_month:5.1f}  {s.co_per_month:4.1f}  {s.submittal_per_month:4.1f}'
        )
    total = sum(s.contract_value for s in scenarios)
    print(f'\n{len(scenarios)} jobs | ${total / 1e6:.2f}M total | horizon ≤ {HORIZON_CAP} months')


def _build_models(app_module):
    from app import (
        db, Project, Commitment, CommitmentAllocation,
        ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
        PayAppProjectState, SageSyncEvent, User, RFI, Submittal,
        ChangeEvent, SubcontractorRFQ, RFQAllocation,
        ChangeOrderRequest, CORAllocation, PotentialChangeOrder, PCOAllocation,
        ChangeEventLineItem,
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
        '_acct_models': app_module._acct_models,
    }


def _finish_project_closeout(rt: ProjectRuntime, models: dict) -> None:
    from accounting_reconcile import reconcile_project_accounting
    from project_closeout import closeout_readiness, sweep_project_closeout_blockers

    db = models['db']
    Project = models['Project']
    project = Project.query.get(rt.result.project_id or rt.project.id)
    if not project:
        return

    sweep = sweep_project_closeout_blockers(
        project.id,
        db=db,
        RFI=models['RFI'],
        ChangeOrder=models['ChangeOrder'],
        User=models['User'],
        users=rt.users,
        approve_co_fn=lambda co: _approve_co_smart(co, rt.users, models),
        Submittal=models.get('Submittal'),
        PotentialChangeOrder=models.get('PotentialChangeOrder'),
    )
    rt.result.metrics['closeout_sweep'] = sweep

    report = closeout_readiness(
        project.id,
        RFI=models['RFI'],
        ChangeOrder=models['ChangeOrder'],
        Submittal=models.get('Submittal'),
        PotentialChangeOrder=models.get('PotentialChangeOrder'),
    )
    rt.result.metrics['closeout'] = {'ok': report.get('ok'), 'counts': report.get('counts')}
    if report.get('ok'):
        reconcile_project_accounting(
            project.id, None,
            ChangeOrder=models['ChangeOrder'],
            ChangeOrderAllocation=models['ChangeOrderAllocation'],
            Commitment=models['Commitment'],
            CommitmentAllocation=models['CommitmentAllocation'],
            BudgetProjectState=models['BudgetProjectState'],
            PayAppProjectState=models['PayAppProjectState'],
            db=db,
        )
        project.status = 'Complete'
        db.session.commit()
        rt.result.metrics['project_status'] = 'Complete'
    else:
        rt.result.metrics['project_status'] = project.status


def run_200m_fifty(
    *,
    seed: int = 200,
    verbose: bool = False,
    skip_subprocess_tests: bool = False,
    extended_sample: int = 5,
) -> tuple[list[ProjectRuntime], dict]:
    import app as app_module
    from unittest.mock import patch
    from case_workflow import ensure_workflow_schema

    scenarios = build_fifty_scenarios(seed=seed)
    models = _build_models(app_module)
    uid = uuid.uuid4().hex[:10]

    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    runtimes: list[ProjectRuntime] = []
    summary: dict = {}
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(models['db'].engine)
            models['db'].session.rollback()
            _ensure_sim_users(models['db'], models['User'])

            if not skip_subprocess_tests:
                print('Phase 0: Accounting subprocess integration suite (clean DB)…')
                summary['accounting_subprocess'] = run_accounting_subprocess_suite()

            print('=' * 72)
            print('$200M × 50 PROJECTS — PORTFOLIO + ACCOUNTING')
            print('=' * 72)
            _print_table(scenarios)

            print('\nPhase 1: Semi-concurrent monthly PM (all 50 jobs)…')
            runtimes = run_portfolio(models, scenarios, verbose=verbose)

            print(f'\nPhase 2: Extended change chain on {extended_sample} representative jobs…')
            Commitment = models['Commitment']
            by_cv = sorted(runtimes, key=lambda r: r.scenario.contract_value, reverse=True)
            sample: list[ProjectRuntime] = []
            if by_cv:
                sample.append(by_cv[0])
            if len(by_cv) > 1:
                sample.append(by_cv[1])
            if len(by_cv) > 2:
                sample.append(by_cv[-1])
            mid = [r for r in by_cv if r not in sample]
            need = max(0, extended_sample - len(sample))
            if mid and need:
                sample.extend(random.sample(mid, min(need, len(mid))))
            for rt in sample:
                try:
                    commitments = Commitment.query.filter_by(project_id=rt.project.id).all()
                    _run_extended_modules(rt.result, rt.project, rt.users, models, commitments)
                    rt.result.metrics['extended_modules'] = True
                except Exception as exc:
                    rt.result.add('warning', 'extended', f'{rt.scenario.name}: {exc}')

            print('\nPhase 3: Per-project closeout sweep + Complete…')
            for rt in runtimes:
                try:
                    _finish_project_closeout(rt, models)
                except Exception as exc:
                    rt.result.add('warning', 'closeout', f'{rt.scenario.name}: {exc}')

            pids = [rt.project.id for rt in runtimes if rt.project]
            print(f'\nPhase 4: Accounting battery ({len(pids)} projects × construction events + reversals)…')
            summary['accounting_battery'] = run_accounting_battery(
                models['db'], models, pids, uid_prefix=uid, reverse_sample=15,
            )
    finally:
        sig_patch.stop()

    return runtimes, summary


def main() -> int:
    parser = argparse.ArgumentParser(description='$200M / 50-project portfolio simulation')
    parser.add_argument('--report', default='', help='Write JSON report')
    parser.add_argument('--seed', type=int, default=200)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--skip-subprocess-tests', action='store_true')
    args = parser.parse_args()

    try:
        runtimes, summary = run_200m_fifty(
            seed=args.seed,
            verbose=args.verbose,
            skip_subprocess_tests=args.skip_subprocess_tests,
        )
    except Exception:
        traceback.print_exc()
        return 2

    critical = warnings = 0
    totals = {'rfis': 0, 'cos': 0, 'submittals': 0, 'rfqs': 0, 'change_events': 0, 'complete': 0}
    for rt in runtimes:
        critical += sum(1 for i in rt.result.issues if i.severity == 'critical')
        warnings += sum(1 for i in rt.result.issues if i.severity == 'warning')
        m = rt.result.metrics
        totals['rfis'] += m.get('rfis_created', 0)
        totals['cos'] += m.get('cos_created', 0)
        totals['submittals'] += m.get('submittals_created', 0)
        totals['rfqs'] += m.get('rfqs_created', 0)
        totals['change_events'] += m.get('change_events_created', 0)
        if m.get('project_status') == 'Complete':
            totals['complete'] += 1

    print(f'\n{"=" * 72}\nPORTFOLIO SUMMARY\n{"=" * 72}')
    print(json.dumps(totals, indent=2))
    print(json.dumps(summary, indent=2))
    print(f'\nJobs: {len(runtimes)} | Complete: {totals["complete"]} | Critical: {critical} | Warnings: {warnings}')

    bat = summary.get('accounting_battery') or {}
    if bat.get('errors'):
        print('\nAccounting battery errors (first 15):')
        for err in bat['errors'][:15]:
            print(' ', err)

    sub = summary.get('accounting_subprocess') or {}
    failed_sub = [k for k, v in sub.items() if v != 0]
    if failed_sub:
        print('\nAccounting subprocess tests failed (pre-portfolio):', failed_sub)

    if args.report:
        payload = {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'totals': totals,
            'summary': summary,
            'critical': critical,
            'warnings': warnings,
            'projects': [
                {
                    'name': rt.scenario.name,
                    'project_id': rt.result.project_id,
                    'contract_value': rt.scenario.contract_value,
                    'metrics': rt.result.metrics,
                    'issues': [
                        {'severity': i.severity, 'category': i.category, 'message': i.message}
                        for i in rt.result.issues
                    ],
                }
                for rt in runtimes
            ],
        }
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        print(f'\nReport: {args.report}')

    return 1 if critical else 0


if __name__ == '__main__':
    raise SystemExit(main())
