#!/usr/bin/env python3
"""
Multi-project Sage 300 integration paces — $100M + $50M + $10M concurrent, 24-month billing.

Runs three overlapping projects through the full financial lifecycle while posting to
virtual Sage 300, accepting ERP-queued events, pulling sub payments / actuals back from
Sage, and validating bidirectional sync.

Usage:
  python3 scripts/run_sage300_portfolio_paces.py
  python3 scripts/run_sage300_portfolio_paces.py --no-bridge
  python3 scripts/run_sage300_portfolio_paces.py --months 24 --quick   # smoke (6 months)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.simulate_concurrent_portfolio import (
    TRADE_MIX_C,
    TRADE_MIX_SMALL,
    ProjectRuntime,
    ProjectScenario,
    SimResult,
    _ensure_sim_users,
    run_portfolio,
)

VIRTUAL_SAGE_PORT = int(os.environ.get('VIRTUAL_SAGE_PORT', '8765'))
SAGE_API_URL = os.environ.get('SAGE_API_URL', f'http://127.0.0.1:{VIRTUAL_SAGE_PORT}').rstrip('/')
SAGE_API_KEY = os.environ.get('SAGE_API_KEY', 'virtual-sage-test-key')

REQUIRED_MODULES = frozenset({
    'JobCost', 'AP', 'Subcontracts', 'ProgressBilling', 'SubcontractorBilling', 'PCO',
})

SAGE_PORTFOLIO_SCENARIOS = [
    ProjectScenario(
        name='Mega-Campus-100M',
        slug='mega100',
        contract_value=100_000_000.0,
        trade_mix=TRADE_MIX_C,
        user_count=80,
        start_month=0,
        duration_months=24,
        rfi_per_month=2.5,
        co_per_month=1.2,
        pay_periods=24,
        submittal_per_month=0.5,
        rfq_per_month=0.3,
        change_event_per_month=0.2,
    ),
    ProjectScenario(
        name='Medical-Pavilion-50M',
        slug='med50',
        contract_value=50_000_000.0,
        trade_mix=TRADE_MIX_C,
        user_count=50,
        start_month=0,
        duration_months=24,
        rfi_per_month=3.5,
        co_per_month=1.8,
        pay_periods=24,
        submittal_per_month=0.4,
        rfq_per_month=0.4,
        change_event_per_month=0.25,
    ),
    ProjectScenario(
        name='Tenant-Fitout-10M',
        slug='ten10',
        contract_value=10_000_000.0,
        trade_mix=TRADE_MIX_SMALL,
        user_count=30,
        start_month=0,
        duration_months=24,
        rfi_per_month=4.0,
        co_per_month=2.0,
        pay_periods=24,
        submittal_per_month=0.6,
        rfq_per_month=0.5,
        change_event_per_month=0.3,
    ),
]


@dataclass
class PortfolioPaceResult:
    ok: bool = True
    issues: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.issues.append(msg)


def _http_json(url: str, method: str = 'GET', data: dict | None = None, timeout: int = 60) -> dict:
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {SAGE_API_KEY}'}
    body = None
    if data is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw else {}


def wait_for_bridge(timeout_sec: float = 30.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            _http_json(f'{SAGE_API_URL}/api/v1/health')
            return True
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.25)
    return False


def start_bridge_process() -> subprocess.Popen:
    env = os.environ.copy()
    env['VIRTUAL_SAGE_PORT'] = str(VIRTUAL_SAGE_PORT)
    env['VIRTUAL_SAGE_API_KEY'] = SAGE_API_KEY
    return subprocess.Popen(
        [sys.executable, os.path.join(os.path.dirname(__file__), 'virtual_sage300_bridge.py')],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def configure_sage_defaults() -> None:
    from program_settings_persistence import save_sage_defaults
    save_sage_defaults({
        'sage_company_code': 'CASE',
        'sage_database': 'VIRTUAL_SAGE300',
        'sage_account_set': 'STD',
        'sage_accounting_method': 'Percentage of Completion',
        'sage_billings_account': '4100-000',
        'sage_wip_account': '1150-000',
        'sage_revenue_account': '4000-000',
        'sage_ar_customer_code': 'CUS-0301',
        'sage_default_tax_group': 'STANDARD',
        'sage_ap_vendor_prefix': 'SUB-',
        'sage_cost_code_prefix': '',
        'sage_subcontract_liability_account': '2100-000',
        'sage_default_cost_type': 'Subcontract',
        'sage_sync_enabled': '1',
        'sage_connection_mode': 'api',
        'sage_api_url': SAGE_API_URL,
        'sage_job_prefix': 'JOB-',
    })


def accept_all_pending_sage_events(project_id: int, users: dict, db, SageSyncEvent, Commitment) -> int:
    from change_event_persistence import accept_sage_event_for_export
    accepted = 0
    while True:
        pending = (
            SageSyncEvent.query
            .filter_by(project_id=project_id, accounting_status='pending_review')
            .order_by(SageSyncEvent.id.asc())
            .limit(100)
            .all()
        )
        if not pending:
            break
        for ev in pending:
            accept_sage_event_for_export(ev, users['acct'], db, Commitment=Commitment)
            accepted += 1
        db.session.commit()
    return accepted


def queue_budget_sage_events(project_id: int, users: dict, models: dict) -> None:
    from budget_persistence import get_budget_state
    from sage_service import create_and_process_sage_event

    db = models['db']
    Project = models['Project']
    SageSyncEvent = models['SageSyncEvent']
    BudgetProjectState = models['BudgetProjectState']

    _, state = get_budget_state(BudgetProjectState, project_id)
    lines = state.get('budgetLines') or []
    project = Project.query.get(project_id)
    contract = state.get('budgetContractAmount') or (project.contract_value if project else 0)

    create_and_process_sage_event(
        SageSyncEvent, Project, db, project_id,
        'BudgetPublished',
        message=f'Portfolio paces budget publish rev {state.get("budgetRevision", 1)}',
        payload={
            'revision': state.get('budgetRevision', 1),
            'lines_count': len(lines),
            'total_original': sum(float(l.get('original_budget') or 0) for l in lines),
            'contract_amount': contract,
        },
        user_id=users['acct'].id,
    )
    create_and_process_sage_event(
        SageSyncEvent, Project, db, project_id,
        'BudgetSageSync',
        message='Portfolio paces cost code sync',
        payload={'lines_count': len(lines), 'cost_codes': [l.get('cost_code') for l in lines[:80]]},
        user_id=users['acct'].id,
    )
    db.session.commit()


def validate_project_sage(project_id: int, SageSyncEvent, result: PortfolioPaceResult, label: str) -> dict:
    events = SageSyncEvent.query.filter_by(project_id=project_id).all()
    by_status: dict[str, int] = {}
    bad = []
    for ev in events:
        by_status[ev.status] = by_status.get(ev.status, 0) + 1
        if ev.status != 'posted':
            bad.append(f'{ev.event_type}#{ev.id}:{ev.status}')
    report = {'total': len(events), 'by_status': by_status, 'not_posted': bad[:5]}
    result.metrics[f'{label}_sage'] = report
    if bad:
        result.fail(f'{label}: {len(bad)} Sage events not posted')
    return report


def pull_and_validate(rt: ProjectRuntime, models: dict, users: dict, result: PortfolioPaceResult) -> None:
    from sage_service import apply_sage_pull_to_project, pull_sage_job_ledger

    label = rt.scenario.slug
    project = rt.project
    if not project:
        result.fail(f'{label}: no project')
        return

    job = project.sage_job_number
    ledger = pull_sage_job_ledger(job)
    pull = apply_sage_pull_to_project(
        project.id,
        Project=models['Project'],
        Commitment=models['Commitment'],
        BudgetProjectState=models['BudgetProjectState'],
        PayAppProjectState=models['PayAppProjectState'],
        db=models['db'],
        user_id=users['acct'].id,
        SageSyncEvent=models['SageSyncEvent'],
        ChangeOrder=models['ChangeOrder'],
        ChangeOrderAllocation=models['ChangeOrderAllocation'],
        CommitmentAllocation=models['CommitmentAllocation'],
    )
    result.metrics[f'{label}_pull'] = pull
    result.metrics[f'{label}_ledger'] = {
        'sub_payments': len(ledger.get('sub_payments') or []),
        'owner_billings': len(ledger.get('owner_billings') or []),
        'vendor_totals': ledger.get('vendor_paid_totals') or {},
    }

    if pull.get('mode') == 'live':
        if not pull.get('payment_match') and pull.get('total_sage_sub_paid', 0) > 0:
            mismatched = [
                v for v in (pull.get('vendor_payment_checks') or pull.get('vendor_invoiced_checks') or [])
                if not v.get('matched') and v.get('sage_paid', 0) > 0
            ]
            if mismatched:
                result.fail(
                    f'{label}: {len(mismatched)} vendor payment mismatches vs Sage '
                    f'(e.g. {mismatched[0].get("company_id")}: '
                    f'Sage ${mismatched[0].get("sage_paid"):,.0f} vs Case ${mismatched[0].get("case_billed", mismatched[0].get("case_invoiced", 0)):,.0f})',
                )


def run_portfolio_paces(*, start_bridge: bool = True, months: int | None = None, quick: bool = False) -> PortfolioPaceResult:
    result = PortfolioPaceResult()
    bridge_proc = None
    os.environ['SAGE_API_URL'] = SAGE_API_URL
    os.environ['SAGE_API_KEY'] = SAGE_API_KEY

    scenarios = [ProjectScenario(**{**s.__dict__}) for s in SAGE_PORTFOLIO_SCENARIOS]
    if quick:
        for s in scenarios:
            s.duration_months = 6
            s.pay_periods = 6
            s.rfi_per_month *= 0.5
            s.co_per_month *= 0.5
    if months is not None:
        for s in scenarios:
            s.duration_months = months
            s.pay_periods = months

    try:
        if start_bridge:
            try:
                _http_json(f'{SAGE_API_URL}/api/v1/reset', method='POST')
            except Exception:
                bridge_proc = start_bridge_process()
                if not wait_for_bridge():
                    result.fail('Virtual Sage bridge did not start')
                    return result
                _http_json(f'{SAGE_API_URL}/api/v1/reset', method='POST')
        elif not wait_for_bridge(5.0):
            result.fail(f'Virtual Sage bridge not reachable at {SAGE_API_URL}')
            return result

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
                configure_sage_defaults()
                ensure_workflow_schema(db.engine)
                db.session.rollback()
                users = _ensure_sim_users(db, User)

                print(f'\n{"=" * 68}')
                print('  SAGE 300 PORTFOLIO PACES — $100M + $50M + $10M / 24 months')
                print(f'  Virtual Sage: {SAGE_API_URL}')
                print(f'{"=" * 68}\n')

                runtimes = run_portfolio(models, scenarios, verbose=not quick)

                for rt in runtimes:
                    if rt.result.issues:
                        crit = [i for i in rt.result.issues if i.severity == 'critical']
                        for c in crit[:3]:
                            result.fail(f'{rt.scenario.slug}: [{c.category}] {c.message}')

                    queue_budget_sage_events(rt.project.id, users, models)
                    accepted = accept_all_pending_sage_events(
                        rt.project.id, users, db, SageSyncEvent, Commitment,
                    )
                    result.metrics[f'{rt.scenario.slug}_accepted'] = accepted
                    validate_project_sage(rt.project.id, SageSyncEvent, result, rt.scenario.slug)
                    pull_and_validate(rt, models, users, result)

                summary = _http_json(f'{SAGE_API_URL}/api/v1/summary')
                result.metrics['virtual_sage'] = summary
                modules = set((summary.get('by_module') or {}).keys())
                missing = REQUIRED_MODULES - modules
                if missing:
                    result.fail(f'Virtual Sage missing modules: {sorted(missing)}')
                jobs = summary.get('by_job') or {}
                if len(jobs) < len(scenarios):
                    result.fail(f'Expected {len(scenarios)} jobs in Sage, got {len(jobs)}')
                if summary.get('transaction_count', 0) < 50:
                    result.fail(f'Low Sage transaction count: {summary.get("transaction_count")}')

                for rt in runtimes:
                    result.metrics[rt.scenario.slug] = rt.result.metrics

        finally:
            sig_patch.stop()

    except Exception as exc:
        result.fail(f'Unhandled error: {exc}')
        traceback.print_exc()
    finally:
        if bridge_proc:
            bridge_proc.terminate()
            try:
                bridge_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge_proc.kill()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Multi-project Sage 300 portfolio paces')
    parser.add_argument('--no-bridge', action='store_true')
    parser.add_argument('--months', type=int, default=None, help='Override duration (default 24)')
    parser.add_argument('--quick', action='store_true', help='6-month smoke run')
    args = parser.parse_args()

    result = run_portfolio_paces(
        start_bridge=not args.no_bridge,
        months=args.months,
        quick=args.quick,
    )
    print('\n--- Sage 300 Portfolio Paces Results ---')
    print(json.dumps(result.metrics, indent=2, default=str))
    if result.issues:
        print('\nIssues:')
        for issue in result.issues:
            print(f'  ✗ {issue}')
    else:
        print('\n✓ All portfolio Sage paces checks passed.')
    return 0 if result.ok else 1


if __name__ == '__main__':
    sys.exit(main())
