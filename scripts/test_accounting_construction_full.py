#!/usr/bin/env python3
"""Extended construction integration tests — PYTHONPATH=. from repo root."""
from __future__ import annotations

import sys


def main() -> int:
    errors: list[str] = []
    try:
        from app import app, db, Project, _acct_models
        from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts
        from accounting_posting import process_construction_event

        with app.app_context():
            ledger = get_or_create_default_ledger(db, _acct_models['AcctLedger'])
            seed_chart_of_accounts(db, _acct_models['AcctLedger'], _acct_models['AcctGLAccount'], ledger)
            project = Project.query.first()
            if not project:
                print('SKIP: no projects')
                return 0
            pid = project.id
            cases = [
                ('SubPayAppApproved', {
                    'amount': 1200, 'company_id': 1, 'period_number': '2026-07',
                    'idempotency_key': 'full-sub-1', 'force_builtin_post': True, 'cost_code': '01-5100',
                }),
                ('TimesheetPosted', {
                    'amount': 75, 'idempotency_key': 'full-ts-1', 'force_builtin_post': True, 'cost_code': '01-5000',
                }),
            ]
            for event_type, payload in cases:
                first = process_construction_event(event_type, pid, payload, db=db, models=_acct_models, Project=Project)
                second = process_construction_event(event_type, pid, payload, db=db, models=_acct_models, Project=Project)
                if not first.get('posted') and first.get('skipped') != 'already_posted':
                    errors.append(f'{event_type} first: {first}')
                if second.get('skipped') != 'already_posted':
                    errors.append(f'{event_type} idempotent: {second}')
            from accounting_waves_47 import sage_cutover_checklist, sage_parity_matrix
            if 'steps' not in sage_cutover_checklist(db, _acct_models, ledger.id):
                errors.append('cutover checklist')
            if 'rows' not in sage_parity_matrix(db, _acct_models, ledger.id):
                errors.append('parity matrix')
            db.session.rollback()
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        print('FAILED:')
        for e in errors:
            print(' -', e)
        return 1
    print('OK — construction full integration passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
