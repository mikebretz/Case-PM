#!/usr/bin/env python3
"""Construction integration pack: G702 + sub pay app + commitment idempotency — PYTHONPATH=. from repo root."""
from __future__ import annotations

import sys


def _idem_post(process_construction_event, event_type, pid, payload, **kwargs):
    first = process_construction_event(event_type, pid, payload, **kwargs)
    second = process_construction_event(event_type, pid, payload, **kwargs)
    return first, second


def main() -> int:
    errors: list[str] = []
    try:
        from app import app, db, Project, Commitment, Company, _acct_models
        from accounting_persistence import get_or_create_default_ledger, seed_chart_of_accounts
        from accounting_posting import process_construction_event
        from accounting_waves_25 import sage_queue_construction_mirror_event
        from accounting_waves_48 import sage_parity_gap_prioritized_list, estimate_sov_alignment_report
        import app as app_mod

        with app.app_context():
            ledger = get_or_create_default_ledger(db, _acct_models['AcctLedger'])
            seed_chart_of_accounts(db, _acct_models['AcctLedger'], _acct_models['AcctGLAccount'], ledger)
            project = Project.query.first()
            if not project:
                print('SKIP: no projects')
                return 0
            pid = project.id
            kw = dict(db=db, models=_acct_models, Project=Project, Company=Company)

            idem_g702 = 'pack-g702-integration-864a'
            g702_payload = {
                'amount': 1800.0,
                'period_number': '2026-08',
                'idempotency_key': idem_g702,
                'force_builtin_post': True,
            }
            first, second = _idem_post(process_construction_event, 'G702Approved', pid, g702_payload, **kw)
            if not first.get('posted') and first.get('skipped') != 'already_posted':
                errors.append(f'G702 first: {first}')
            if second.get('skipped') != 'already_posted':
                errors.append(f'G702 idempotent: {second}')
            sage_out = sage_queue_construction_mirror_event(
                db, _acct_models, ledger.id, 'G702Approved',
                {'project_id': pid, 'amount': 1800.0, 'period_number': '2026-08', 'idempotency_key': idem_g702},
            )
            if not sage_out.get('queued') and not sage_out.get('ok'):
                errors.append(f'G702 sage queue: {sage_out}')

            sub_payload = {
                'amount': 950,
                'company_id': 1,
                'period_number': '2026-08',
                'idempotency_key': 'pack-sub-pay-864a',
                'force_builtin_post': True,
                'cost_code': '01-5100',
            }
            first, second = _idem_post(process_construction_event, 'SubPayAppApproved', pid, sub_payload, **kw)
            if not first.get('posted') and first.get('skipped') != 'already_posted':
                errors.append(f'SubPayApp first: {first}')
            if second.get('skipped') != 'already_posted':
                errors.append(f'SubPayApp idempotent: {second}')

            cmt = Commitment.query.filter_by(project_id=pid).first()
            if cmt:
                cmt_key = f'pack-cmt-{cmt.id}-864a'
                cmt_payload = {'idempotency_key': cmt_key, 'force_builtin_post': True}
                first, second = _idem_post(
                    process_construction_event, 'CommitmentApproved', pid, cmt_payload,
                    commitment=cmt, **kw,
                )
                if not first.get('posted') and first.get('skipped') != 'already_posted':
                    errors.append(f'Commitment first: {first}')
                if second.get('skipped') != 'already_posted':
                    errors.append(f'Commitment idempotent: {second}')
            else:
                print('NOTE: no commitment row — commitment leg skipped')

            gaps = sage_parity_gap_prioritized_list(db, _acct_models, ledger.id)
            if 'gaps' not in gaps:
                errors.append('parity gaps prioritized')
            sov = estimate_sov_alignment_report(
                db, pid,
                BudgetProjectState=app_mod.BudgetProjectState,
                PayAppProjectState=app_mod.PayAppProjectState,
            )
            if 'mismatch_count' not in sov:
                errors.append('sov alignment report')

            db.session.rollback()
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        print('FAILED:')
        for e in errors:
            print(' -', e)
        return 1
    print('OK — construction integration pack passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
