#!/usr/bin/env python3
"""
10-year brutal platform stress — $50M–$500M jobs, full module surface area.

Exercises portfolio PM (RFI/submittal/CO/RFQ/CE/pay apps), estimating, marketing hub,
plan room, extended financial chains, closeout, heavy accounting GL + reversals,
**500 enterprise users** (ramped over the decade), and **100+ concurrent** API load bursts.

  PYTHONPATH=/workspace python3 scripts/simulate_decade_brutal_stress.py
  PYTHONPATH=/workspace python3 scripts/simulate_decade_brutal_stress.py --report /tmp/decade.json

  PYTHONPATH=/workspace python3 scripts/simulate_decade_brutal_stress.py --quick   # smoke (3 jobs / 24 mo)
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

import scripts.simulate_concurrent_portfolio as portfolio_mod  # noqa: E402
from scripts.portfolio_accounting_battery import (  # noqa: E402
    run_accounting_subprocess_suite,
    run_heavy_accounting_battery,
)
from scripts.simulate_200m_fifty_projects import _build_models, _finish_project_closeout  # noqa: E402
from scripts.simulate_concurrent_portfolio import (  # noqa: E402
    ProjectRuntime,
    ProjectScenario,
    run_portfolio,
)
from scripts.simulate_financial_project import (  # noqa: E402
    TRADE_MIX_B,
    TRADE_MIX_C,
    _ensure_sim_users,
    _run_extended_modules,
)
from scripts.decade_enterprise_load import (  # noqa: E402
    DEFAULT_TOTAL_USERS,
    RAMP_USERS_PER_YEAR,
    assign_project_memberships,
    enterprise_users_at_month,
    provision_enterprise_users,
    run_concurrent_load_test,
    run_portfolio_with_periodic_load,
)
from scripts.simulate_hundred_million_lifecycle import (  # noqa: E402
    LifecycleSimConfig,
    _run_estimating_bid,
    _run_marketing_hub,
    _run_plan_room,
)

MIN_CONTRACT = 50_000_000.0
MAX_CONTRACT = 500_000_000.0
DEFAULT_YEARS = 10
DEFAULT_PROJECTS = 42
EXTENDED_CV_FLOOR = 100_000_000.0
DEFAULT_ENTERPRISE_USERS = DEFAULT_TOTAL_USERS
DEFAULT_LOAD_CONCURRENCY = 128


def _log_uniform_contract(seed: int, index: int, *, lo: float = MIN_CONTRACT, hi: float = MAX_CONTRACT) -> float:
    rng = random.Random(seed + index * 9973)
    log_lo, log_hi = math.log(lo), math.log(hi)
    raw = math.exp(rng.uniform(log_lo, log_hi))
    return round(raw / 1_000_000) * 1_000_000


def _complexity_tier(cv: float) -> str:
    if cv >= 350_000_000:
        return 'extreme'
    if cv >= 200_000_000:
        return 'high'
    if cv >= 100_000_000:
        return 'medium'
    return 'standard'


def _duration_months(cv: float) -> int:
    ratio = (cv - MIN_CONTRACT) / (MAX_CONTRACT - MIN_CONTRACT)
    return max(24, min(72, round(24 + 48 * ratio)))


def _user_count(cv: float) -> int:
    ratio = (cv - MIN_CONTRACT) / (MAX_CONTRACT - MIN_CONTRACT)
    return max(60, min(280, round(60 + 220 * ratio)))


def _trade_mix(cv: float) -> list:
    if cv >= 120_000_000:
        return TRADE_MIX_C
    return TRADE_MIX_B


def _activity_rates(tier: str) -> dict[str, float]:
    table = {
        'standard': dict(rfi=3.5, submittal=2.0, co=3.0, rfq=1.5, change_event=1.2),
        'medium': dict(rfi=4.5, submittal=2.8, co=4.0, rfq=2.2, change_event=1.8),
        'high': dict(rfi=5.5, submittal=3.5, co=5.0, rfq=2.8, change_event=2.4),
        'extreme': dict(rfi=7.0, submittal=4.5, co=6.0, rfq=3.5, change_event=3.0),
    }
    base = table[tier]
    return {
        'rfi_per_month': base['rfi'],
        'submittal_per_month': base['submittal'],
        'co_per_month': base['co'],
        'rfq_per_month': base['rfq'],
        'change_event_per_month': base['change_event'],
    }


def build_decade_scenarios(
    *,
    project_count: int,
    horizon_months: int,
    seed: int,
    quick: bool = False,
) -> list[ProjectScenario]:
    scenarios: list[ProjectScenario] = []
    rng = random.Random(seed)
    lo, hi = (12_000_000.0, 45_000_000.0) if quick else (MIN_CONTRACT, MAX_CONTRACT)
    for i in range(project_count):
        cv = _log_uniform_contract(seed, i, lo=lo, hi=hi)
        tier = _complexity_tier(cv)
        duration = _duration_months(cv)
        if quick:
            duration = min(duration, 14)
        max_start = max(0, horizon_months - duration)
        # Bias megaprojects toward mid-decade peaks; smaller jobs fill early/late
        if cv >= 250_000_000:
            start = rng.randint(max(0, max_start // 4), max(0, max_start - max_start // 5))
        elif cv <= 80_000_000:
            start = rng.choice([rng.randint(0, max_start // 3), rng.randint(2 * max_start // 3, max_start)])
        else:
            start = rng.randint(0, max_start)
        rates = _activity_rates(tier)
        scenarios.append(ProjectScenario(
            name=f'DEC-{i + 1:02d}-${cv / 1e6:.0f}M-{tier[:3].upper()}',
            slug=f'dec{i + 1:02d}',
            contract_value=cv,
            trade_mix=_trade_mix(cv),
            user_count=_user_count(cv),
            start_month=start,
            duration_months=duration,
            pay_periods=duration,
            reconcile_every=1,
            **rates,
        ))
    scenarios.sort(key=lambda s: s.contract_value, reverse=True)
    return scenarios


def _lifecycle_cfg(scenario: ProjectScenario) -> LifecycleSimConfig:
    tier = _complexity_tier(scenario.contract_value)
    clar = {'standard': 4, 'medium': 8, 'high': 12, 'extreme': 18}[tier]
    return LifecycleSimConfig(
        name=scenario.name,
        slug=scenario.slug,
        contract_value=scenario.contract_value,
        target_rfis=0,
        target_cos=0,
        target_co_value=0,
        duration_months=scenario.duration_months,
        estimate_number=f'EST-{scenario.slug}',
        estimate_title=scenario.name,
        run_marketing_hub=True,
        run_plan_room=True,
        plan_room_clarifications=clar,
    )


def _print_scenario_table(scenarios: list[ProjectScenario], horizon_months: int) -> None:
    print(f'\n{"#":>3}  {"Name":<28}  {"Value":>10}  {"Dur":>4}  {"Start":>5}  {"End":>4}  Tier')
    print('-' * 78)
    for i, s in enumerate(scenarios, 1):
        tier = _complexity_tier(s.contract_value)
        print(
            f'{i:3d}  {s.name:<28}  ${s.contract_value / 1e6:>8.0f}M  {s.duration_months:4d}  '
            f'{s.start_month:5d}  {s.end_month:4d}  {tier}'
        )
    total = sum(s.contract_value for s in scenarios)
    peak = max(
        sum(1 for s in scenarios if s.start_month <= m <= s.end_month)
        for m in range(horizon_months)
    )
    print(f'\n{len(scenarios)} jobs | ${total / 1e9:.2f}B total | {horizon_months} months ({horizon_months // 12}y) | '
          f'peak concurrent ≈ {peak}')


def _patch_enterprise_user_pool(enterprise_users: list) -> object:
    """Replace per-project sim user minting with enterprise pool memberships."""
    original_pool = portfolio_mod._create_user_pool
    project_index = [0]

    def _enterprise_pool(db, User, scenario, project_id, ProjectMembership):
        gm = getattr(portfolio_mod, '_decade_global_month', 0)
        active = enterprise_users_at_month(enterprise_users, gm)
        pool = assign_project_memberships(
            db, active, project_id, ProjectMembership,
            project_index=project_index[0],
            max_per_project=min(40, max(12, scenario.user_count // 8)),
        )
        project_index[0] += 1
        if pool:
            return pool
        return original_pool(db, User, scenario, project_id, ProjectMembership)

    portfolio_mod._create_user_pool = _enterprise_pool
    return original_pool


def _patch_setup_for_decade(models: dict):
    original = portfolio_mod._setup_project

    def _decade_setup(rt: ProjectRuntime, m: dict, global_month: int) -> None:
        original(rt, m, global_month)
        if rt.result.metrics.get('decade_enriched'):
            return
        cfg = _lifecycle_cfg(rt.scenario)
        try:
            _run_estimating_bid(rt, m, cfg)
            _run_marketing_hub(rt, m, cfg)
            _run_plan_room(rt, m, cfg)
            rt.result.metrics['decade_enriched'] = True
            rt.result.metrics['complexity_tier'] = _complexity_tier(rt.scenario.contract_value)
        except Exception as exc:
            rt.result.add('warning', 'decade_setup', f'{rt.scenario.name}: {exc}')

    portfolio_mod._setup_project = _decade_setup
    return original


def run_decade_brutal(
    *,
    project_count: int = DEFAULT_PROJECTS,
    years: int = DEFAULT_YEARS,
    seed: int = 10,
    verbose: bool = False,
    skip_subprocess_tests: bool = False,
    enterprise_users: int = DEFAULT_ENTERPRISE_USERS,
    load_concurrency: int = DEFAULT_LOAD_CONCURRENCY,
    skip_load: bool = False,
    quick: bool = False,
) -> tuple[list[ProjectRuntime], dict]:
    import app as app_module
    from unittest.mock import patch
    from case_workflow import ensure_workflow_schema

    horizon_months = years * 12
    scenarios = build_decade_scenarios(
        project_count=project_count,
        horizon_months=horizon_months,
        seed=seed,
        quick=quick,
    )
    models = _build_models(app_module)
    models.update({
        'MarketingLead': getattr(app_module, 'MarketingLead', None),
        'MarketingCaseStudy': getattr(app_module, 'MarketingCaseStudy', None),
        'MarketingCampaign': getattr(app_module, 'MarketingCampaign', None),
        'MarketingReviewRequest': getattr(app_module, 'MarketingReviewRequest', None),
        'MarketingAsset': getattr(app_module, 'MarketingAsset', None),
        'MarketingAutomationRule': getattr(app_module, 'MarketingAutomationRule', None),
    })
    uid = uuid.uuid4().hex[:10]
    summary: dict = {}
    runtimes: list[ProjectRuntime] = []

    sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
    sig_patch.start()
    orig_setup = None
    orig_pool = None
    try:
        with app_module.app.app_context():
            ensure_workflow_schema(models['db'].engine)
            models['db'].session.rollback()
            _ensure_sim_users(models['db'], models['User'])

            ent_total = min(enterprise_users, 50) if years <= 2 and project_count <= 5 else enterprise_users
            print(f'Provisioning {ent_total} enterprise users (ramp +{RAMP_USERS_PER_YEAR}/year)…')
            ent_pool = provision_enterprise_users(models['db'], models['User'], total=ent_total)
            summary['enterprise_users'] = len(ent_pool)
            orig_pool = _patch_enterprise_user_pool(ent_pool)
            portfolio_mod._decade_global_month = 0

            if not skip_subprocess_tests:
                print('Phase 0: Accounting subprocess integration suite…')
                summary['accounting_subprocess'] = run_accounting_subprocess_suite()

            print('=' * 78)
            print(f'DECADE BRUTAL STRESS — {years} years | ${MIN_CONTRACT/1e6:.0f}M–${MAX_CONTRACT/1e6:.0f}M | '
                  f'{project_count} projects')
            print('=' * 78)
            _print_scenario_table(scenarios, horizon_months)

            orig_setup = _patch_setup_for_decade(models)
            horizon_months = years * 12
            load_months = (12,) if years <= 2 else (24, 60, 96, horizon_months - 1)
            if skip_load:
                print(f'\nPhase 1: {horizon_months}-month portfolio (no concurrent load)…')
                runtimes = run_portfolio(models, scenarios, verbose=verbose)
                summary['load_tests'] = []
            else:
                print(f'\nPhase 1: {horizon_months}-month portfolio + load bursts (≥100 concurrent)…')
                runtimes, load_reports = run_portfolio_with_periodic_load(
                    models,
                    scenarios,
                    app_module.app,
                    ent_pool,
                    load_at_months=load_months,
                    load_concurrency=load_concurrency,
                    verbose=verbose,
                )
                summary['load_tests'] = load_reports
                pids = [rt.result.project_id for rt in runtimes if rt.result.project_id]
                print(f'\nPhase 1b: Final load — {load_concurrency} concurrent / {len(ent_pool)} enterprise users…')
                final_load = run_concurrent_load_test(
                    app_module.app,
                    ent_pool,
                    pids,
                    concurrency=load_concurrency,
                    ops_per_user=10,
                    label='final-peak',
                )
                summary['load_tests'].append(final_load)
                summary['load_final'] = final_load

            extended = [rt for rt in runtimes if rt.scenario.contract_value >= EXTENDED_CV_FLOOR]
            print(f'\nPhase 2: Extended financial chain on {len(extended)} jobs ≥ ${EXTENDED_CV_FLOOR/1e6:.0f}M…')
            Commitment = models['Commitment']
            for rt in extended:
                try:
                    commitments = Commitment.query.filter_by(project_id=rt.result.project_id).all()
                    _run_extended_modules(rt.result, rt.project, rt.users, models, commitments)
                    rt.result.metrics['extended_modules'] = True
                except Exception as exc:
                    rt.result.add('warning', 'extended', f'{rt.scenario.name}: {exc}')

            print('\nPhase 3: Marketing automation sweep (all portfolio projects)…')
            try:
                from marketing_gaps import run_scheduled_marketing_jobs
                summary['marketing_jobs'] = run_scheduled_marketing_jobs(
                    models['db'], models, models['Project'],
                )
            except Exception as exc:
                summary['marketing_jobs'] = {'error': str(exc)}

            print('\nPhase 4: Closeout sweep + Complete (every job)…')
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
            print(f'\nPhase 5: Heavy accounting battery ({len(project_values)} projects)…')
            summary['accounting_battery'] = run_heavy_accounting_battery(
                models['db'],
                models,
                project_values,
                uid_prefix=uid,
                reverse_sample=min(len(project_values), 30),
            )
    finally:
        if orig_setup is not None:
            portfolio_mod._setup_project = orig_setup
        if orig_pool is not None:
            portfolio_mod._create_user_pool = orig_pool
        sig_patch.stop()

    return runtimes, summary


def _aggregate(runtimes: list[ProjectRuntime]) -> dict:
    totals = {
        'rfis': 0, 'cos': 0, 'submittals': 0, 'rfqs': 0, 'change_events': 0,
        'complete': 0, 'marketing_leads': 0, 'plan_room_published': 0,
    }
    critical = warnings = 0
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
        if m.get('marketing_lead_id'):
            totals['marketing_leads'] += 1
        totals['plan_room_published'] += m.get('plan_room_packages_published', 0)
    return {'totals': totals, 'critical': critical, 'warnings': warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description='10-year brutal CasePM stress test')
    parser.add_argument('--report', default='')
    parser.add_argument('--seed', type=int, default=10)
    parser.add_argument('--projects', type=int, default=DEFAULT_PROJECTS)
    parser.add_argument('--years', type=int, default=DEFAULT_YEARS)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--skip-subprocess-tests', action='store_true')
    parser.add_argument('--quick', action='store_true', help='3 jobs / 24 months smoke')
    parser.add_argument('--enterprise-users', type=int, default=DEFAULT_ENTERPRISE_USERS)
    parser.add_argument('--load-concurrency', type=int, default=DEFAULT_LOAD_CONCURRENCY)
    parser.add_argument('--skip-load', action='store_true')
    args = parser.parse_args()

    projects = 3 if args.quick else args.projects
    years = 2 if args.quick else args.years
    load_conc = 24 if args.quick else args.load_concurrency
    ent_users = 60 if args.quick else args.enterprise_users

    try:
        runtimes, summary = run_decade_brutal(
            project_count=projects,
            years=years,
            seed=args.seed,
            verbose=args.verbose,
            skip_subprocess_tests=args.skip_subprocess_tests or args.quick,
            enterprise_users=ent_users,
            load_concurrency=load_conc,
            skip_load=args.skip_load,
            quick=args.quick,
        )
    except Exception:
        traceback.print_exc()
        return 2

    agg = _aggregate(runtimes)
    load_fail = sum(1 for r in (summary.get('load_tests') or []) if r.get('failed'))
    load_degraded = sum(1 for r in (summary.get('load_tests') or []) if r.get('degraded'))
    if load_fail:
        agg['critical'] += load_fail
    elif load_degraded:
        agg['warnings'] += load_degraded

    print(f'\n{"=" * 78}\nDECADE STRESS SUMMARY\n{"=" * 78}')
    print(json.dumps(agg['totals'], indent=2))
    print(json.dumps(summary, indent=2))
    print(f'\nJobs: {len(runtimes)} | Complete: {agg["totals"]["complete"]} | '
          f'Enterprise users: {summary.get("enterprise_users", 0)} | '
          f'Load bursts: {len(summary.get("load_tests") or [])} | '
          f'Critical: {agg["critical"]} | Warnings: {agg["warnings"]}')

    for rep in summary.get('load_tests') or []:
        lat = rep.get('latency_ms') or {}
        print(f'  Load [{rep.get("label")}]: concurrency={rep.get("concurrency")} '
              f'rps={rep.get("requests_per_second")} p95={lat.get("p95")}ms '
              f'errors={rep.get("errors")} failed={rep.get("failed")}')

    bat = summary.get('accounting_battery') or {}
    if bat.get('errors'):
        print('\nAccounting errors (first 20):')
        for e in bat['errors'][:20]:
            print(' ', e)

    if args.report:
        payload = {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'profile': 'decade_brutal_stress',
            'years': years,
            'project_count': projects,
            'aggregate': agg,
            'summary': summary,
            'projects': [
                {
                    'name': rt.scenario.name,
                    'project_id': rt.result.project_id,
                    'contract_value': rt.scenario.contract_value,
                    'tier': rt.result.metrics.get('complexity_tier'),
                    'metrics': rt.result.metrics,
                }
                for rt in runtimes
            ],
        }
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        print(f'\nReport: {args.report}')

    return 1 if agg['critical'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
