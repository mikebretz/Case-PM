#!/usr/bin/env python3
"""Print ops finalize status or run finalize (CRE autopost, cutover, parity auto-fix)."""
from __future__ import annotations

import sys


def main() -> int:
    run = '--run' in sys.argv
    try:
        from app import app, db, Project, PayAppProjectState, _acct_models
        from accounting_persistence import get_or_create_default_ledger
        from accounting_waves_49 import operations_finalize_run, operations_finalize_status

        with app.app_context():
            ledger = get_or_create_default_ledger(db, _acct_models['AcctLedger'])
            if run:
                out = operations_finalize_run(
                    db, _acct_models, ledger.id, Project=Project, PayAppProjectState=PayAppProjectState,
                )
                db.session.commit()
                print('finalize:', out.get('cutover_ready'), 'holes:', (out.get('status') or {}).get('hole_count'))
            else:
                out = operations_finalize_status(
                    db, _acct_models, ledger.id, Project=Project, PayAppProjectState=PayAppProjectState,
                )
                print('ready_for_daily_ops:', out.get('ready_for_daily_ops'))
                for h in out.get('holes') or []:
                    print('-', h.get('code'), h.get('label') or h.get('fix') or h.get('detail'))
    except Exception as exc:
        print('ERROR:', exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
