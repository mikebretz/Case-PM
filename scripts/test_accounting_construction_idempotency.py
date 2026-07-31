#!/usr/bin/env python3
"""Construction posting idempotency — run with PYTHONPATH=. from repo root."""
from __future__ import annotations

import sys


def main() -> int:
    errors: list[str] = []
    try:
        from app import app, db, Project, _acct_models
        from accounting_posting import process_construction_event
        from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts

        with app.app_context():
            AcctLedger = _acct_models['AcctLedger']
            AcctGLAccount = _acct_models['AcctGLAccount']
            AcctPostLink = _acct_models['AcctPostLink']
            ledger = get_or_create_default_ledger(db, AcctLedger)
            seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)
            project = Project.query.first()
            if not project:
                print('SKIP: no projects in database — idempotency logic not exercised')
                return 0
            payload = {
                'amount': 100.0,
                'idempotency_key': 'test-idem-timesheet-999001',
                'timesheet_id': 999001,
                'force_builtin_post': True,
            }
            first = process_construction_event(
                'TimesheetPosted',
                project.id,
                payload,
                db=db,
                models=_acct_models,
                Project=Project,
            )
            second = process_construction_event(
                'TimesheetPosted',
                project.id,
                payload,
                db=db,
                models=_acct_models,
                Project=Project,
            )
            if not first.get('posted'):
                errors.append(f'first post expected posted=True: {first}')
            if second.get('skipped') != 'already_posted':
                errors.append(f'second post expected skipped=already_posted: {second}')
            link_count = AcctPostLink.query.filter_by(
                ledger_id=ledger.id, source_key=payload['idempotency_key'],
            ).count()
            if link_count != 1:
                errors.append(f'expected 1 AcctPostLink, found {link_count}')
            db.session.rollback()
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        print('FAILED:')
        for e in errors:
            print(' -', e)
        return 1
    print('OK — construction idempotency check passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
