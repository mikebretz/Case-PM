#!/usr/bin/env python3
"""Smoke checks for Case PM accounting — run after deploy or before release."""
from __future__ import annotations

import re
import sys


def main() -> int:
    errors: list[str] = []

    print('1. Import app…')
    try:
        from app import app  # noqa: F401
    except Exception as exc:
        errors.append(f'app import failed: {exc}')
        _report(errors)
        return 1

    print('2. Duplicate Flask endpoints (accounting)…')
    try:
        from accounting_waves_17 import flask_endpoint_name_collisions

        dups = flask_endpoint_name_collisions(app)
        acct_dups = [d for d in dups if d.startswith('api_acct_')]
        if acct_dups:
            errors.append(f'duplicate accounting endpoints: {acct_dups}')
    except Exception as exc:
        errors.append(f'endpoint scan failed: {exc}')

    print('3. accounting_routes duplicate view names…')
    text = open('accounting_routes.py', encoding='utf-8').read()
    names = re.findall(r'def (api_acct_\w+)', text)
    from collections import Counter

    for name, count in Counter(names).items():
        if count > 1:
            errors.append(f'duplicate function name in accounting_routes: {name} ({count}x)')

    print('4. Wave 17 module import…')
    try:
        import accounting_waves_17 as w17  # noqa: F401

        w17.compliance_filing_calendar(1, 2025)
    except Exception as exc:
        errors.append(f'accounting_waves_17: {exc}')

    print('6. Wave 19 module import…')
    try:
        import accounting_waves_19 as w19  # noqa: F401
        w19.report_designer_column_catalog()
    except Exception as exc:
        errors.append(f'accounting_waves_19: {exc}')

    print('6b. Wave 20 module import…')
    try:
        import accounting_waves_20 as w20  # noqa: F401
        w20.report_designer_column_catalog()
    except Exception as exc:
        errors.append(f'accounting_waves_20: {exc}')

    print('6d. Wave 21 module import…')
    try:
        import accounting_waves_21 as w21  # noqa: F401
        assert callable(w21.construction_force_post_for_event)
    except Exception as exc:
        errors.append(f'accounting_waves_21: {exc}')

    print('6e. Wave 22 module import…')
    try:
        import accounting_waves_22 as w22  # noqa: F401
        assert callable(w22.deploy_accounting_check)
    except Exception as exc:
        errors.append(f'accounting_waves_22: {exc}')

    print('6f. Wave 23 module import…')
    try:
        import accounting_waves_23 as w23  # noqa: F401
        assert callable(w23.project_retainage_summary)
        assert callable(w23.month_end_cash_checklist)
    except Exception as exc:
        errors.append(f'accounting_waves_23: {exc}')

    print('6g. Wave 24 Sage mirror (14–19)…')
    try:
        import accounting_waves_24 as w24  # noqa: F401
        assert callable(w24.sage_module_coverage_report)
        chk = w24.sage_mirror_deploy_check()
        if not chk.get('ok'):
            errors.append(f'sage_mirror_deploy_check: {chk.get("errors")}')
    except Exception as exc:
        errors.append(f'accounting_waves_24: {exc}')

    print('6h. Wave 25 Sage mirror (20–24)…')
    try:
        import accounting_waves_25 as w25  # noqa: F401
        assert callable(w25.sage_push_open_ap_idempotent)
        assert callable(w25.sage_year_end_variance_report)
    except Exception as exc:
        errors.append(f'accounting_waves_25: {exc}')

    print('6i. Wave 26 Sage mirror (25–28)…')
    try:
        import accounting_waves_26 as w26  # noqa: F401
        assert callable(w26.sage_pull_ar_receipt_applications)
        assert callable(w26.sage_year_end_extended_report)
        chk = w26.sage_mirror_deploy_check_v2()
        if not chk.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v2: {chk}')
    except Exception as exc:
        errors.append(f'accounting_waves_26: {exc}')

    print('6j. Wave 27 Sage production (29–32)…')
    try:
        import accounting_waves_27 as w27  # noqa: F401
        assert callable(w27.sage_pull_ar_receipts_v2)
        assert callable(w27.sage_drift_dashboard)
        v3 = w27.sage_mirror_deploy_check_v3()
        if not v3.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v3: {v3}')
    except Exception as exc:
        errors.append(f'accounting_waves_27: {exc}')

    print('6k. Wave 28 Sage enterprise (33–36)…')
    try:
        import accounting_waves_28 as w28  # noqa: F401
        assert callable(w28.list_sage_profile_packs)
        assert callable(w28.month_close_wizard_state)
        v4 = w28.sage_mirror_deploy_check_v4()
        if not v4.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v4: {v4}')
    except Exception as exc:
        errors.append(f'accounting_waves_28: {exc}')

    print('6l. Wave 29 Sage parity (37–40)…')
    try:
        import accounting_waves_29 as w29  # noqa: F401
        assert callable(w29.sage_pull_fa_assets)
        assert callable(w29.sage_push_payroll_run_live)
        v5 = w29.sage_mirror_deploy_check_v5()
        if not v5.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v5: {v5}')
    except Exception as exc:
        errors.append(f'accounting_waves_29: {exc}')

    print('6c. instance DB must not be tracked…')
    try:
        from accounting_waves_20 import git_tracked_paths_must_not_include_db

        db_tracked = git_tracked_paths_must_not_include_db()
        if db_tracked:
            errors.append(f'tracked database files in git: {db_tracked}')
    except Exception as exc:
        errors.append(f'db track check: {exc}')

    print('7. Startup guard…')
    try:
        from accounting_waves_19 import accounting_startup_guard
        g = accounting_startup_guard()
        if not g.get('ok'):
            errors.append(f'startup_guard: {g.get("errors")}')
    except Exception as exc:
        errors.append(f'startup_guard: {exc}')

    _report(errors)
    return 1 if errors else 0


def _report(errors: list[str]) -> None:
    if errors:
        print('\nFAILED:')
        for e in errors:
            print(' -', e)
    else:
        print('\nOK — accounting smoke checks passed.')


if __name__ == '__main__':
    sys.exit(main())
