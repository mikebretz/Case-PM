#!/usr/bin/env python3
"""
$100M across 20 jobs — moderate paperwork, heavy financials + accounting.

  PYTHONPATH=/workspace python3 scripts/simulate_100m_twenty_projects.py
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import traceback
import uuid
from datetime import datetime

sys.path.insert(0, '/workspace')

from scripts.portfolio_accounting_battery import (  # noqa: E402
    run_accounting_subprocess_suite,
    run_heavy_accounting_battery,
)
from scripts.simulate_200m_fifty_projects import (  # noqa: E402
    _build_models,
    _finish_project_closeout,
)
from scripts.simulate_concurrent_portfolio import (  # noqa: E402
    ProjectScenario,
    TRADE_MIX_SMALL,
    run_portfolio,
)
from scripts.simulate_financial_project import (  # noqa: E402
    _ensure_sim_users,
    _run_extended_modules,
)

TOTAL_CONTRACT_VALUE = 100_000_000.0
JOB_COUNT = 20
HORIZON_CAP = 24
SEED_DEFAULT = 100


def _distribute_contract_values(total: float, count: int, seed: int) -> list[float]:
    random.seed(seed)
    weights = [random.uniform(0.5, 1.5) for _ in range(count)]
    gross = sum(weights)
    values = [round(total * w / gross / 25_000) * 25_000 for w in weights]
    drift = round(total - sum(values), 2)
    values[0] = round(values[0] + drift, 2)
    return values


def _duration_months(contract_value: float) -> int:
    ratio = contract_value / 5_000_000.0
    return max(12, min(16, round(12 + 4 * min(1.0, ratio))))


def _user_count(contract_value: float) -> int:
    return max(30, min(70, round(30 + contract_value / 200_000)))


def _activity_rates() -> dict[str, float]:
    """Moderate PM paperwork; heavier CO / RFQ / change-event (financial) volume."""
    return {
        'rfi_per_month': 2.5,
        'submittal_per_month': 1.5,
        'co_per_month': 4.0,
        'rfq_per_month': 2.0,
        'change_event_per_month': 2.0,
    }


def build_twenty_scenarios(*, seed: int = SEED_DEFAULT) -> list[ProjectScenario]:
    values = _distribute_contract_values(TOTAL_CONTRACT_VALUE, JOB_COUNT, seed)
    rates = _activity_rates()
    scenarios = []
    for i, cv in enumerate(values):
        duration = _duration_months(cv)
        max_start = max(0, HORIZON_CAP - duration)
        start = min(max_start, (i % 4) * (max_start // 4 + 1))
        scenarios.append(ProjectScenario(
            name=f'FN-{i + 1:02d}-${cv / 1e6:.1f}M',
            slug=f'fn{i + 1:02d}',
            contract_value=cv,
            trade_mix=TRADE_MIX_SMALL,
            user_count=_user_count(cv),
            start_month=start,
            duration_months=duration,
            pay_periods=duration,
            reconcile_every=1,
            **rates,
        ))
    scenarios.sort(key=lambda s: s.contract_value, reverse=True)
    return scenarios


def _print_table(scenarios: list[ProjectScenario]) -> None:
    print(f'\n{"#":>3}  {"Name":<18}  {"Value":>10}  {"Dur":>4}  {"Start":>5}  '
          f'{"RFI":>5}  {"CO":>4}  {"SUB":>4}  {"RFQ":>4}  {"CE":>4}', flush=True)
    print('-' * 78)
    for i, s in enumerate(scenarios, 1):
        print(
            f'{i:3d}  {s.name:<18}  ${s.contract_value / 1e6:>8.2f}M  {s.duration_months:4d}  '
            f'{s.start_month:5d}  {s.rfi_per_month:5.1f}  {s.co_per_month:4.1f}  '
            f'{s.submittal_per_month:4.1f}  {s.rfq_per_month:4.1f}  {s.change_event_per_month:4.1f}'
        )
    total = sum(s.contract_value for s in scenarios)
    print(f'\n{len(scenarios)} jobs | ${total / 1e6:.2f}M total | horizon ≤ {HORIZON_CAP} months')


def run_100m_twenty(
    *,
    seed: int = SEED_DEFAULT,
    verbose: bool = False,
    skip_subprocess_tests: bool = False,
    extended_sample: int = 10,
) -> tuple[list, dict]:
    import app as app_module
    from unittest.mock import patch
    from case_workflow import ensure_workflow_schema

    scenarios = build_twenty_scenarios(seed=seed)
    models = _build_models(app_module)
    uid = uuid.uuid4().hex[:10]
    summary: dict = {}
    runtimes = []

    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(models['db'].engine)
            models['db'].session.rollback()
            _ensure_sim_users(models['db'], models['User'])

            if not skip_subprocess_tests:
                print('Phase 0: Accounting subprocess suite…')
                summary['accounting_subprocess'] = run_accounting_subprocess_suite()

            print('=' * 72)
            print('$100M × 20 PROJECTS — moderate docs, heavy financials + accounting')
            print('=' * 72)
            _print_table(scenarios)

            print('\nPhase 1: Portfolio monthly PM + pay apps (reconcile every period)…')
            runtimes = run_portfolio(models, scenarios, verbose=verbose)

            print(f'\nPhase 2: Extended financial chain on {extended_sample} jobs…')
            Commitment = models['Commitment']
            by_cv = sorted(runtimes, key=lambda r: r.scenario.contract_value, reverse=True)
            sample = by_cv[:extended_sample]
            for rt in sample:
                try:
                    commitments = Commitment.query.filter_by(project_id=rt.result.project_id).all()
                    _run_extended_modules(rt.result, rt.project, rt.users, models, commitments)
                    rt.result.metrics['extended_modules'] = True
                except Exception as exc:
                    rt.result.add('warning', 'extended', f'{rt.scenario.name}: {exc}')

            print('\nPhase 3: Closeout sweep + Complete (all jobs)…')
            for rt in runtimes:
                try:
                    _finish_project_closeout(rt, models)
                except Exception as exc:
                    rt.result.add('warning', 'closeout', f'{rt.scenario.name}: {exc}')

            project_values = {
                rt.result.project_id: rt.scenario.contract_value
                for rt in runtimes
                if rt.result.project_id
            }
            print(f'\nPhase 4: Heavy accounting battery ({len(project_values)} projects)…')
            summary['accounting_battery'] = run_heavy_accounting_battery(
                models['db'], models, project_values, uid_prefix=uid, reverse_sample=len(project_values),
            )
    finally:
        sig_patch.stop()

    return runtimes, summary


def main() -> int:
    parser = argparse.ArgumentParser(description='$100M / 20-project financial-heavy portfolio')
    parser.add_argument('--report', default='')
    parser.add_argument('--seed', type=int, default=SEED_DEFAULT)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--skip-subprocess-tests', action='store_true')
    args = parser.parse_args()

    try:
        runtimes, summary = run_100m_twenty(
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

    if args.report:
        payload = {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'profile': '100M_20_financial_heavy',
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
