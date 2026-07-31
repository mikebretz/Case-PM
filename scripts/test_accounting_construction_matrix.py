#!/usr/bin/env python3
"""Construction event integration matrix — PYTHONPATH=. from repo root."""
from __future__ import annotations

import sys


def _post(event_type, project_id, payload, db, models, Project, **kw):
    from accounting_posting import process_construction_event
    return process_construction_event(
        event_type, project_id, payload, db=db, models=models, Project=Project, **kw,
    )


def main() -> int:
    errors: list[str] = []
    try:
        from app import app, db, Project, _acct_models
        from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts

        with app.app_context():
            ledger = get_or_create_default_ledger(db, _acct_models['AcctLedger'])
            seed_chart_of_accounts(db, _acct_models['AcctLedger'], _acct_models['AcctGLAccount'], ledger)
            project = Project.query.first()
            if not project:
                print('SKIP: no projects')
                return 0
            pid = project.id
            cases = [
                ('TimesheetPosted', {'amount': 50, 'idempotency_key': 'matrix-ts-1', 'force_builtin_post': True, 'cost_code': '01-5000'}),
                ('DirectCostPosted', {'amount': 25, 'idempotency_key': 'matrix-dc-1', 'force_builtin_post': True, 'cost_code': '01-5200', 'cost_type': 'Material'}),
                ('G702Approved', {'amount': 500, 'period_number': 'M1', 'idempotency_key': 'matrix-g702-1', 'force_builtin_post': True}),
                ('ChangeOrderApproved', {'amount': 100, 'co_number': 'CO-T1', 'idempotency_key': 'matrix-co-1', 'force_builtin_post': True, 'cost_code': '01-0001'}),
            ]
            for event_type, payload in cases:
                out = _post(event_type, pid, payload, db, _acct_models, Project)
                if not out.get('posted') and out.get('skipped') != 'already_posted':
                    errors.append(f'{event_type}: {out}')
            from accounting_waves_46 import construction_pending_dashboard, sage_go_live_alert_bundle, mobile_offline_schema
            dash = construction_pending_dashboard(db, _acct_models, ledger.id, pid)
            if 'sections' not in dash:
                errors.append(f'pending_dashboard: {dash}')
            alerts = sage_go_live_alert_bundle(db, _acct_models, ledger.id)
            if 'alerts' not in alerts:
                errors.append('go_live_alerts missing alerts key')
            if mobile_offline_schema().get('version') != 1:
                errors.append('offline schema version')
            db.session.rollback()
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        print('FAILED:')
        for e in errors:
            print(' -', e)
        return 1
    print('OK — construction integration matrix passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
