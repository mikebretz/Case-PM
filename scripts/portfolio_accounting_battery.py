"""Run construction GL matrix, idempotency, reversals, and closeout checks across portfolio projects."""
from __future__ import annotations

import subprocess
import sys
from typing import Any


CONSTRUCTION_MATRIX_CASES = [
    ('TimesheetPosted', {'amount': 50, 'force_builtin_post': True, 'cost_code': '01-5000'}),
    ('DirectCostPosted', {'amount': 25, 'force_builtin_post': True, 'cost_code': '01-5200', 'cost_type': 'Material'}),
    ('G702Approved', {'amount': 500, 'period_number': 'M1', 'force_builtin_post': True}),
    ('ChangeOrderApproved', {'amount': 100, 'co_number': 'CO-T1', 'force_builtin_post': True, 'cost_code': '01-0001'}),
    ('SubPayAppApproved', {
        'amount': 1200, 'company_id': 1, 'period_number': '2026-07',
        'force_builtin_post': True, 'cost_code': '01-5100',
    }),
]


def run_accounting_battery(
    db,
    models: dict,
    project_ids: list[int],
    *,
    uid_prefix: str = 'pf',
    reverse_sample: int = 10,
) -> dict:
    """
    Post all construction event types per project (unique idempotency keys),
    verify idempotency, reverse a sample, and run job-cost closeout checklist.
    """
    from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts
    from accounting_posting import process_construction_event
    from accounting_waves_23 import project_accounting_closeout_checklist, reverse_construction_post

    app_models = models.get('_acct_models')
    if not app_models:
        import app as app_module
        app_models = app_module._acct_models
        models['_acct_models'] = app_models

    Project = models['Project']
    AcctLedger = app_models['AcctLedger']
    AcctGLAccount = app_models['AcctGLAccount']
    ledger = get_or_create_default_ledger(db, AcctLedger)
    seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)

    stats: dict[str, Any] = {
        'projects_tested': 0,
        'posts_ok': 0,
        'posts_failed': 0,
        'idem_ok': 0,
        'idem_failed': 0,
        'reversals_ok': 0,
        'reversals_failed': 0,
        'closeout_ready': 0,
        'closeout_blocked': 0,
        'errors': [],
    }
    reversal_keys: list[str] = []

    for pid in project_ids:
        stats['projects_tested'] += 1
        for event_type, base_payload in CONSTRUCTION_MATRIX_CASES:
            key = f'{uid_prefix}-p{pid}-{event_type}-bat'
            payload = {**base_payload, 'idempotency_key': key}
            if event_type == 'TimesheetPosted':
                payload['timesheet_id'] = f'TS-{pid}'
            try:
                first = process_construction_event(
                    event_type, pid, payload, db=db, models=app_models, Project=Project,
                )
                second = process_construction_event(
                    event_type, pid, payload, db=db, models=app_models, Project=Project,
                )
                if first.get('posted') or first.get('skipped') == 'already_posted':
                    stats['posts_ok'] += 1
                else:
                    stats['posts_failed'] += 1
                    stats['errors'].append(f'p{pid} {event_type}: {first}')
                if second.get('skipped') == 'already_posted':
                    stats['idem_ok'] += 1
                else:
                    stats['idem_failed'] += 1
                    stats['errors'].append(f'p{pid} {event_type} idem: {second}')
                if first.get('posted') and event_type == 'TimesheetPosted':
                    reversal_keys.append(key)
            except Exception as exc:
                stats['posts_failed'] += 1
                stats['errors'].append(f'p{pid} {event_type}: {exc}')

        try:
            checklist = project_accounting_closeout_checklist(
                db, app_models, ledger.id, pid,
                PayAppProjectState=models.get('PayAppProjectState'),
                Commitment=models.get('Commitment'),
            )
            if checklist.get('ready_to_close'):
                stats['closeout_ready'] += 1
            else:
                stats['closeout_blocked'] += 1
        except Exception as exc:
            stats['closeout_blocked'] += 1
            stats['errors'].append(f'p{pid} closeout checklist: {exc}')

    db.session.commit()

    for key in reversal_keys[:reverse_sample]:
        try:
            reverse_construction_post(
                db, app_models, ledger.id, key, reason='portfolio sim correction',
            )
            stats['reversals_ok'] += 1
        except Exception as exc:
            stats['reversals_failed'] += 1
            stats['errors'].append(f'reverse {key}: {exc}')
    db.session.commit()

    try:
        from accounting_waves_46 import construction_pending_dashboard, sage_go_live_alert_bundle
        sample_pid = project_ids[0] if project_ids else None
        if sample_pid:
            dash = construction_pending_dashboard(db, app_models, ledger.id, sample_pid)
            if 'sections' not in dash:
                stats['errors'].append(f'pending_dashboard: {dash}')
        alerts = sage_go_live_alert_bundle(db, app_models, ledger.id)
        if 'alerts' not in alerts:
            stats['errors'].append('go_live_alerts missing alerts key')
        from accounting_waves_47 import sage_cutover_checklist, sage_parity_matrix
        if 'steps' not in sage_cutover_checklist(db, app_models, ledger.id):
            stats['errors'].append('cutover checklist')
        if 'rows' not in sage_parity_matrix(db, app_models, ledger.id):
            stats['errors'].append('parity matrix')
    except Exception as exc:
        stats['errors'].append(f'wave46/47: {exc}')

    return stats


def run_heavy_accounting_battery(
    db,
    models: dict,
    project_values: dict[int, float],
    *,
    uid_prefix: str = 'hv',
    reverse_sample: int = 20,
) -> dict:
    """
    Standard matrix per project plus scaled financial posts (large G702/CO/direct cost)
    and commitment encumbrance where a commitment exists. Reversals on a broad sample.
    """
    pids = list(project_values.keys())
    stats = run_accounting_battery(
        db, models, pids, uid_prefix=uid_prefix, reverse_sample=0,
    )
    stats['heavy_extra_posts'] = 0
    stats['heavy_extra_failed'] = 0
    stats['commitment_posts'] = 0

    from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts
    from accounting_posting import process_construction_event

    app_models = models['_acct_models']
    Project = models['Project']
    Commitment = models.get('Commitment')
    AcctLedger = app_models['AcctLedger']
    AcctGLAccount = app_models['AcctGLAccount']
    ledger = get_or_create_default_ledger(db, AcctLedger)
    seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)

    reversal_keys: list[str] = []

    for pid, cv in project_values.items():
        cv = float(cv or 0)
        extras = [
            ('G702Approved', {
                'amount': round(max(500, cv * 0.015), 2),
                'period_number': 'H2',
                'idempotency_key': f'{uid_prefix}-p{pid}-G702-heavy',
                'force_builtin_post': True,
            }),
            ('ChangeOrderApproved', {
                'amount': round(max(100, cv * 0.004), 2),
                'co_number': f'CO-H-{pid}',
                'idempotency_key': f'{uid_prefix}-p{pid}-CO-heavy',
                'force_builtin_post': True,
                'cost_code': '01-0001',
            }),
            ('DirectCostPosted', {
                'amount': round(max(50, cv * 0.002), 2),
                'idempotency_key': f'{uid_prefix}-p{pid}-DC-heavy',
                'force_builtin_post': True,
                'cost_type': 'Material',
                'cost_code': '01-5200',
            }),
            ('TimesheetPosted', {
                'amount': round(max(25, cv * 0.001), 2),
                'idempotency_key': f'{uid_prefix}-p{pid}-TS-heavy',
                'timesheet_id': f'HEAVY-{pid}',
                'force_builtin_post': True,
            }),
        ]
        for event_type, payload in extras:
            try:
                out = process_construction_event(
                    event_type, pid, payload, db=db, models=app_models, Project=Project,
                )
                if out.get('posted') or out.get('skipped') == 'already_posted':
                    stats['heavy_extra_posts'] += 1
                    if event_type == 'TimesheetPosted' and out.get('posted'):
                        reversal_keys.append(payload['idempotency_key'])
                else:
                    stats['heavy_extra_failed'] += 1
                    stats['errors'].append(f'heavy p{pid} {event_type}: {out}')
            except Exception as exc:
                stats['heavy_extra_failed'] += 1
                stats['errors'].append(f'heavy p{pid} {event_type}: {exc}')

        if Commitment is not None:
            com = Commitment.query.filter_by(project_id=pid, status='Approved').first()
            if com:
                key = f'{uid_prefix}-p{pid}-CMT-{com.id}'
                try:
                    out = process_construction_event(
                        'CommitmentApproved',
                        pid,
                        {
                            'idempotency_key': key,
                            'force_builtin_post': True,
                            'amount': float(com.current_amount or com.original_amount or 0),
                        },
                        db=db,
                        models=app_models,
                        Project=Project,
                        commitment=com,
                    )
                    if out.get('posted'):
                        stats['commitment_posts'] += 1
                        reversal_keys.append(key)
                except Exception as exc:
                    stats['errors'].append(f'commitment p{pid}: {exc}')

    db.session.commit()

    from accounting_waves_23 import reverse_construction_post
    for key in reversal_keys[:reverse_sample]:
        try:
            reverse_construction_post(
                db, app_models, ledger.id, key, reason='heavy portfolio correction',
            )
            stats['reversals_ok'] += 1
        except Exception as exc:
            stats['reversals_failed'] += 1
            stats['errors'].append(f'reverse {key}: {exc}')
    db.session.commit()

    return stats


def run_accounting_subprocess_suite() -> dict[str, int]:
    """Invoke packaged accounting integration scripts (non-interactive)."""
    scripts = [
        'scripts/test_accounting_construction_idempotency.py',
        'scripts/test_accounting_construction_matrix.py',
        'scripts/test_accounting_construction_full.py',
        'scripts/test_accounting_construction_integration_pack.py',
    ]
    results: dict[str, int] = {}
    for path in scripts:
        proc = subprocess.run(
            [sys.executable, path],
            cwd='/workspace',
            env={**dict(__import__('os').environ), 'PYTHONPATH': '/workspace'},
            capture_output=True,
            text=True,
        )
        results[path] = proc.returncode
    return results
