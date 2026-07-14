#!/usr/bin/env python3
"""
Run a $100M project through virtual Sage 300 CRE — full sync validation.

Starts the virtual Sage bridge, configures Case PM for live posting, runs the
Mega-Campus financial simulation, accepts all ERP-queued Sage events, queues
budget publish/sync, and verifies every module posted to virtual Sage.

Usage:
  python3 scripts/run_sage300_paces.py
  python3 scripts/run_sage300_paces.py --no-bridge   # bridge already running on :8765
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

VIRTUAL_SAGE_PORT = int(os.environ.get('VIRTUAL_SAGE_PORT', '8765'))
SAGE_API_URL = os.environ.get('SAGE_API_URL', f'http://127.0.0.1:{VIRTUAL_SAGE_PORT}').rstrip('/')
SAGE_API_KEY = os.environ.get('SAGE_API_KEY', 'virtual-sage-test-key')

REQUIRED_MODULES = frozenset({
    'JobCost',
    'AP',
    'Subcontracts',
    'ProgressBilling',
    'SubcontractorBilling',
    'PCO',
})

REQUIRED_EVENT_GROUPS = {
    'commitments': frozenset({
        'CommitmentSubmitted', 'CommitmentApproved', 'CommitmentExecuted',
    }),
    'change_orders': frozenset({
        'ChangeOrderSubmitted', 'ChangeOrderApproved', 'PCOSubmitted',
    }),
    'budget': frozenset({
        'BudgetPublished', 'BudgetSageSync', 'AccountingReconciled',
    }),
    'pay_apps': frozenset({
        'G702Submitted', 'G702Approved', 'SubPayAppSubmitted', 'SubPayAppApproved',
    }),
}


@dataclass
class PaceResult:
    ok: bool = True
    issues: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.issues.append(msg)


def _http_json(url: str, method: str = 'GET', data: dict | None = None, timeout: int = 30) -> dict:
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {SAGE_API_KEY}',
    }
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
            .limit(50)
            .all()
        )
        if not pending:
            break
        for ev in pending:
            accept_sage_event_for_export(ev, users['acct'], db, Commitment=Commitment)
            accepted += 1
        db.session.commit()
    return accepted


def queue_budget_sage_events(project_id: int, users: dict, app_models) -> None:
    from budget_persistence import get_budget_state
    from sage_service import create_and_process_sage_event

    db = app_models['db']
    Project = app_models['Project']
    SageSyncEvent = app_models['SageSyncEvent']
    BudgetProjectState = app_models['BudgetProjectState']

    _, state = get_budget_state(BudgetProjectState, project_id)
    lines = state.get('budgetLines') or []
    project = Project.query.get(project_id)
    contract = state.get('budgetContractAmount') or (project.contract_value if project else 0)

    create_and_process_sage_event(
        SageSyncEvent, Project, db, project_id,
        'BudgetPublished',
        message=f'Paces test budget publish rev {state.get("budgetRevision", 1)}',
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
        message='Paces test cost code sync',
        payload={
            'lines_count': len(lines),
            'cost_codes': [l.get('cost_code') for l in lines[:50]],
        },
        user_id=users['acct'].id,
    )
    db.session.commit()


def queue_accounting_reconcile(project_id: int, app_models) -> None:
    from accounting_reconcile import reconcile_project_accounting
    from sage_service import create_and_process_sage_event

    db = app_models['db']
    recon = reconcile_project_accounting(
        project_id, None,
        ChangeOrder=app_models['ChangeOrder'],
        ChangeOrderAllocation=app_models['ChangeOrderAllocation'],
        Commitment=app_models['Commitment'],
        CommitmentAllocation=app_models['CommitmentAllocation'],
        BudgetProjectState=app_models['BudgetProjectState'],
        PayAppProjectState=app_models['PayAppProjectState'],
        db=db,
    )
    create_and_process_sage_event(
        app_models['SageSyncEvent'],
        app_models['Project'],
        db,
        project_id,
        'AccountingReconciled',
        message='Paces test accounting reconcile',
        payload={
            'actual_cost_applied': recon.get('actual_cost_applied', 0),
            'committed_total': recon.get('committed_total', 0),
        },
        user_id=None,
    )
    db.session.commit()


def validate_casepm_sage_events(project_id: int, SageSyncEvent, result: PaceResult) -> None:
    events = SageSyncEvent.query.filter_by(project_id=project_id).order_by(SageSyncEvent.id.asc()).all()
    result.metrics['sage_events_total'] = len(events)
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    bad = []
    for ev in events:
        by_status[ev.status] = by_status.get(ev.status, 0) + 1
        by_type[ev.event_type] = by_type.get(ev.event_type, 0) + 1
        if ev.status not in ('posted',):
            bad.append(f'{ev.event_type}#{ev.id} status={ev.status} err={ev.error_text or ""}')
    result.metrics['sage_by_status'] = by_status
    result.metrics['sage_by_event_type'] = by_type
    if bad:
        result.fail(f'{len(bad)} Sage events not posted to virtual Sage: ' + '; '.join(bad[:8]))


def validate_virtual_sage_ledger(result: PaceResult) -> dict:
    summary = _http_json(f'{SAGE_API_URL}/api/v1/summary')
    result.metrics['virtual_sage'] = summary

    modules = set((summary.get('by_module') or {}).keys())
    missing_modules = REQUIRED_MODULES - modules
    if missing_modules:
        result.fail(f'Virtual Sage missing modules: {sorted(missing_modules)}')

    event_types = set((summary.get('by_event_type') or {}).keys())
    for group, expected in REQUIRED_EVENT_GROUPS.items():
        if not (event_types & expected):
            result.fail(f'Virtual Sage missing {group} events (expected one of {sorted(expected)})')

    if summary.get('transaction_count', 0) < 25:
        result.fail(f'Virtual Sage transaction count too low: {summary.get("transaction_count")} (expected >= 25)')

    return summary


def run_paces(start_bridge: bool = True) -> PaceResult:
    result = PaceResult()
    bridge_proc = None

    os.environ['SAGE_API_URL'] = SAGE_API_URL
    os.environ['SAGE_API_KEY'] = SAGE_API_KEY

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
        from scripts.simulate_financial_project import (
            TRADE_MIX_C, CONTRACT_VALUE_100M, run_simulation, _ensure_sim_users,
        )

        models = {
            'db': app_module.db,
            'Project': app_module.Project,
            'Commitment': app_module.Commitment,
            'CommitmentAllocation': app_module.CommitmentAllocation,
            'ChangeOrder': app_module.ChangeOrder,
            'ChangeOrderAllocation': app_module.ChangeOrderAllocation,
            'BudgetProjectState': app_module.BudgetProjectState,
            'PayAppProjectState': app_module.PayAppProjectState,
            'SageSyncEvent': app_module.SageSyncEvent,
            'User': app_module.User,
            'ScheduleData': getattr(app_module, 'ScheduleData', None),
            'RFI': getattr(app_module, 'RFI', None),
            'Submittal': getattr(app_module, 'Submittal', None),
            'ChangeEvent': getattr(app_module, 'ChangeEvent', None),
            'SubcontractorRFQ': getattr(app_module, 'SubcontractorRFQ', None),
            'RFQAllocation': getattr(app_module, 'RFQAllocation', None),
            'ChangeOrderRequest': getattr(app_module, 'ChangeOrderRequest', None),
            'CORAllocation': getattr(app_module, 'CORAllocation', None),
            'PotentialChangeOrder': getattr(app_module, 'PotentialChangeOrder', None),
            'PCOAllocation': getattr(app_module, 'PCOAllocation', None),
        }

        sig_patch = patch('user_signature_persistence.verify_user_signature_attestation', lambda *a, **k: True)
        sig_patch.start()
        try:
            with app_module.app.app_context():
                configure_sage_defaults()
                app_module.db.session.rollback()

                print(f'\n{"=" * 64}')
                print(f'  SAGE 300 PACES — $100M Mega-Campus via {SAGE_API_URL}')
                print(f'{"=" * 64}\n')

                sim = run_simulation(
                    'Mega-Campus-C',
                    TRADE_MIX_C,
                    models,
                    contract_value=CONTRACT_VALUE_100M,
                    full_lifecycle=True,
                )
                result.metrics['simulation'] = sim.metrics
                project_id = sim.project_id
                users = _ensure_sim_users(app_module.db, app_module.User)

                for issue in sim.issues:
                    if issue.severity == 'critical':
                        result.fail(f'[{issue.category}] {issue.message}')

                queue_budget_sage_events(project_id, users, models)
                queue_accounting_reconcile(project_id, models)
                accepted = accept_all_pending_sage_events(
                    project_id, users, app_module.db,
                    app_module.SageSyncEvent, app_module.Commitment,
                )
                result.metrics['sage_events_accepted'] = accepted

                validate_casepm_sage_events(project_id, app_module.SageSyncEvent, result)
                validate_virtual_sage_ledger(result)

                # Commitment sage mirror status
                posted_commitments = app_module.Commitment.query.filter_by(
                    project_id=project_id, status='Approved',
                ).count()
                sage_posted = app_module.Commitment.query.filter(
                    app_module.Commitment.project_id == project_id,
                    app_module.Commitment.sage_sync_status == 'sage_posted',
                ).count()
                result.metrics['commitments_approved'] = posted_commitments
                result.metrics['commitments_sage_posted'] = sage_posted
                if posted_commitments and sage_posted < posted_commitments * 0.5:
                    result.fail(
                        f'Only {sage_posted}/{posted_commitments} commitments show sage_posted status',
                    )
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
    parser = argparse.ArgumentParser(description='Run $100M project through virtual Sage 300')
    parser.add_argument('--no-bridge', action='store_true', help='Use existing bridge on VIRTUAL_SAGE_PORT')
    args = parser.parse_args()

    result = run_paces(start_bridge=not args.no_bridge)
    print('\n--- Sage 300 Paces Results ---')
    print(json.dumps(result.metrics, indent=2, default=str))
    if result.issues:
        print('\nIssues:')
        for issue in result.issues:
            print(f'  ✗ {issue}')
    else:
        print('\n✓ All Sage 300 paces checks passed.')
    return 0 if result.ok else 1


if __name__ == '__main__':
    sys.exit(main())
