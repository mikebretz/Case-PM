#!/usr/bin/env python3
"""G702 → A/R → Sage mirror queue — run with PYTHONPATH=. from repo root."""
from __future__ import annotations

import sys


def main() -> int:
    errors: list[str] = []
    try:
        from app import app, db, Project, _acct_models
        from accounting_posting import process_construction_event
        from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts
        from accounting_waves_25 import sage_queue_construction_mirror_event

        with app.app_context():
            AcctLedger = _acct_models['AcctLedger']
            AcctGLAccount = _acct_models['AcctGLAccount']
            AcctARDocument = _acct_models['AcctARDocument']
            AcctPostLink = _acct_models['AcctPostLink']
            ledger = get_or_create_default_ledger(db, AcctLedger)
            seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)
            project = Project.query.first()
            if not project:
                print('SKIP: no projects — integration pack not exercised')
                return 0
            idem = 'test-g702-integration-999002'
            payload = {
                'amount': 2500.0,
                'period_number': '2026-07',
                'idempotency_key': idem,
                'force_builtin_post': True,
            }
            gl_out = process_construction_event(
                'G702Approved',
                project.id,
                payload,
                db=db,
                models=_acct_models,
                Project=Project,
            )
            if not gl_out.get('posted') and gl_out.get('skipped') != 'already_posted':
                errors.append(f'G702 post failed: {gl_out}')
            ar_id = gl_out.get('ar_document_id')
            if ar_id:
                doc = AcctARDocument.query.get(ar_id)
                if not doc or float(doc.amount or 0) != 2500.0:
                    errors.append('AR document amount mismatch')
            sage_out = sage_queue_construction_mirror_event(
                db, _acct_models, ledger.id, 'G702Approved',
                {'project_id': project.id, 'amount': 2500.0, 'period_number': '2026-07', 'idempotency_key': idem},
            )
            if not sage_out.get('queued') and not sage_out.get('ok'):
                errors.append(f'Sage mirror queue unexpected: {sage_out}')
            link_count = AcctPostLink.query.filter_by(ledger_id=ledger.id, source_key=idem).count()
            if link_count < 1:
                errors.append(f'expected AcctPostLink for G702, found {link_count}')
            db.session.rollback()
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        print('FAILED:')
        for e in errors:
            print(' -', e)
        return 1
    print('OK — G702 → AR → Sage queue integration check passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
