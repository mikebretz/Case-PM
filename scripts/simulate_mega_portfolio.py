#!/usr/bin/env python3
"""
Mega portfolio stress test — 30 semi-concurrent jobs over 5 years.

  python3 scripts/simulate_mega_portfolio.py
  python3 scripts/simulate_mega_portfolio.py --jobs 30 --seed 42

Contract values: one at $10M, one at $300M, remainder randomized $10M–$300M.
Largest job runs full 60 months; smaller jobs run proportionally shorter durations.
Heavy RFIs, COs, submittals, RFQs, and change events on every active project monthly.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys

sys.path.insert(0, '/workspace')

from scripts.simulate_concurrent_portfolio import (  # noqa: E402
    ProjectScenario,
    run_portfolio,
)
from scripts.simulate_financial_project import TRADE_MIX_B, TRADE_MIX_C  # noqa: E402

TRADE_MIX_SMALL = [
    ('03-300', 'Concrete', 0.12, 'Subcontract'),
    ('09-250', 'Drywall', 0.18, 'Subcontract'),
    ('15-100', 'HVAC', 0.22, 'Subcontract'),
    ('16-100', 'Electrical', 0.18, 'Subcontract'),
    ('22-100', 'Plumbing', 0.12, 'Subcontract'),
    ('01-100', 'General Conditions', 0.13, 'Service Agreement'),
    ('01-200', 'Contingency', 0.05, 'Service Agreement'),
]

MIN_CONTRACT = 10_000_000.0
MAX_CONTRACT = 300_000_000.0
HORIZON_MONTHS = 60  # 5 years


def _duration_months(contract_value: float) -> int:
    """$10M ≈ 12 months, $300M = 60 months — linear by contract size."""
    ratio = (contract_value - MIN_CONTRACT) / (MAX_CONTRACT - MIN_CONTRACT)
    return max(12, min(HORIZON_MONTHS, round(12 + 48 * ratio)))


def _user_count(contract_value: float) -> int:
    ratio = (contract_value - MIN_CONTRACT) / (MAX_CONTRACT - MIN_CONTRACT)
    return max(40, min(250, round(40 + 210 * ratio)))


def _trade_mix(contract_value: float) -> list:
    if contract_value >= 75_000_000:
        return TRADE_MIX_C
    if contract_value >= 30_000_000:
        return TRADE_MIX_B
    return TRADE_MIX_SMALL


def _activity_rates(contract_value: float) -> dict[str, float]:
    """High document volume scaled to project size."""
    scale = max(0.35, contract_value / 30_000_000.0)
    root = math.sqrt(scale)
    return {
        'rfi_per_month': round(min(18, 6 + 7 * root + random.uniform(1, 4)), 1),
        'co_per_month': round(min(9, 2.5 + 4 * root + random.uniform(0.5, 2)), 1),
        'submittal_per_month': round(min(14, 5 + 6 * root + random.uniform(1, 3)), 1),
        'rfq_per_month': round(min(5, 1 + 2 * root + random.uniform(0, 1)), 1),
        'change_event_per_month': round(min(4, 1 + 1.5 * root + random.uniform(0, 1)), 1),
    }


def _start_month(contract_value: float, duration: int) -> int:
    """Semi-concurrent: larger jobs start earlier; all finish within 5 years."""
    max_start = max(0, HORIZON_MONTHS - duration)
    if contract_value >= MAX_CONTRACT:
        return 0
    if contract_value <= MIN_CONTRACT:
        return random.randint(max(0, max_start - 18), max_start)
    ratio = (contract_value - MIN_CONTRACT) / (MAX_CONTRACT - MIN_CONTRACT)
    earliest = int((1 - ratio) * max_start * 0.55)
    return random.randint(earliest, max_start)


def build_mega_scenarios(job_count: int = 30, seed: int = 42) -> list[ProjectScenario]:
    random.seed(seed)
    values = [MIN_CONTRACT, MAX_CONTRACT]
    while len(values) < job_count:
        raw = random.uniform(MIN_CONTRACT + 500_000, MAX_CONTRACT - 500_000)
        values.append(round(raw / 500_000) * 500_000)
    random.shuffle(values[2:])

    scenarios = []
    for i, cv in enumerate(values):
        duration = _duration_months(cv)
        start = _start_month(cv, duration)
        rates = _activity_rates(cv)
        scenarios.append(ProjectScenario(
            name=f'Job-{i + 1:02d}-${int(cv / 1_000_000)}M',
            slug=f'mega{i + 1:02d}',
            contract_value=cv,
            trade_mix=_trade_mix(cv),
            user_count=_user_count(cv),
            start_month=start,
            duration_months=duration,
            pay_periods=duration,
            reconcile_every=3,
            **rates,
        ))
    scenarios.sort(key=lambda s: s.contract_value, reverse=True)
    return scenarios


def _print_scenario_table(scenarios: list[ProjectScenario]) -> None:
    print(f'\n{"#":>3}  {"Name":<22}  {"Value":>12}  {"Dur":>4}  {"Start":>5}  {"Users":>5}  '
          f'{"RFI":>5}  {"CO":>4}  {"SUB":>4}  {"RFQ":>4}  {"CE":>4}', flush=True)
    print('-' * 95)
    for i, s in enumerate(scenarios, 1):
        print(
            f'{i:3d}  {s.name:<22}  ${s.contract_value / 1e6:>10,.0f}M  {s.duration_months:4d}  '
            f'{s.start_month:5d}  {s.user_count:5d}  {s.rfi_per_month:5.1f}  {s.co_per_month:4.1f}  '
            f'{s.submittal_per_month:4.1f}  {s.rfq_per_month:4.1f}  {s.change_event_per_month:4.1f}'
        )
    total_cv = sum(s.contract_value for s in scenarios)
    max_concurrent = max(
        sum(1 for s in scenarios if s.start_month <= m <= s.end_month)
        for m in range(HORIZON_MONTHS)
    )
    print(f'\nPortfolio: {len(scenarios)} jobs | ${total_cv / 1e9:.2f}B total contract | '
          f'max {max_concurrent} concurrent | {HORIZON_MONTHS}-month horizon')


def _build_models(app_module):
    from app import (
        db, Project, Commitment, CommitmentAllocation,
        ChangeOrder, ChangeOrderAllocation, BudgetProjectState,
        PayAppProjectState, SageSyncEvent, User, RFI, Submittal,
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
        'Submittal': Submittal,
        'ChangeEvent': ChangeEvent,
        'SubcontractorRFQ': SubcontractorRFQ,
        'RFQAllocation': RFQAllocation,
        'ChangeOrderRequest': ChangeOrderRequest,
        'CORAllocation': CORAllocation,
        'PotentialChangeOrder': PotentialChangeOrder,
        'PCOAllocation': PCOAllocation,
        'ProjectMembership': ProjectMembership,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='30-job mega portfolio stress simulation')
    parser.add_argument('--jobs', type=int, default=30)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--verbose', action='store_true', help='Print every monthly tick')
    args = parser.parse_args()

    import app as app_module
    from unittest.mock import patch
    from case_workflow import ensure_workflow_schema

    scenarios = build_mega_scenarios(args.jobs, args.seed)
    models = _build_models(app_module)

    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    runtimes = []
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(models['db'].engine)
            models['db'].session.rollback()
            print('=' * 60)
            print('MEGA PORTFOLIO STRESS SIMULATION')
            print(f'{args.jobs} jobs | $10M–$300M | 5-year semi-concurrent timeline')
            print('=' * 60)
            _print_scenario_table(scenarios)
            runtimes = run_portfolio(models, scenarios, verbose=args.verbose)
    finally:
        sig_patch.stop()

    print(f'\n{"=" * 60}\nMEGA PORTFOLIO SUMMARY\n{"=" * 60}')
    critical = warnings = 0
    totals = {
        'rfis': 0, 'cos': 0, 'submittals': 0, 'rfqs': 0,
        'change_events': 0, 'pay_periods': 0, 'users': 0,
    }
    for rt in runtimes:
        crit = [i for i in rt.result.issues if i.severity == 'critical']
        warn = [i for i in rt.result.issues if i.severity == 'warning']
        critical += len(crit)
        warnings += len(warn)
        m = rt.result.metrics
        totals['rfis'] += m.get('rfis_created', 0)
        totals['cos'] += m.get('cos_created', 0)
        totals['submittals'] += m.get('submittals_created', 0)
        totals['rfqs'] += m.get('rfqs_created', 0)
        totals['change_events'] += m.get('change_events_created', 0)
        totals['pay_periods'] += m.get('pay_periods_completed', 0)
        totals['users'] += m.get('users_assigned', 0)

        if crit or warn:
            print(f'\n{rt.scenario.name} (${rt.scenario.contract_value / 1e6:.0f}M, project {rt.result.project_id}):')
            print(json.dumps(m, indent=2))
            for i in rt.result.issues:
                print(f'  [{i.severity}] {i.category}: {i.message}')

    print(f'\n--- Aggregate totals ---')
    print(json.dumps(totals, indent=2))
    print(f'\nJobs: {len(runtimes)} | Critical: {critical} | Warnings: {warnings}')

    if critical == 0 and warnings == 0:
        print('\nAll jobs completed with no issues.')
    return 1 if critical else 0


if __name__ == '__main__':
    raise SystemExit(main())
