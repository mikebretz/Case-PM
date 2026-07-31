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

    print('6m. Wave 30 Sage CRE/platform (41–44)…')
    try:
        import accounting_waves_30 as w30  # noqa: F401
        assert callable(w30.construction_mirror_queue_inspect)
        assert callable(w30.sage_ops_runbook_dashboard)
        v6 = w30.sage_mirror_deploy_check_v6()
        if not v6.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v6: {v6}')
    except Exception as exc:
        errors.append(f'accounting_waves_30: {exc}')

    print('6n. Wave 31 Sage bank/cash (45–48)…')
    try:
        import accounting_waves_31 as w31  # noqa: F401
        assert callable(w31.sage_pull_bk_transactions_v2)
        assert callable(w31.sage_ap_payment_batch_ack)
        v7 = w31.sage_mirror_deploy_check_v7()
        if not v7.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v7: {v7}')
    except Exception as exc:
        errors.append(f'accounting_waves_31: {exc}')

    print('6o. Wave 32 Sage CRE (53–56)…')
    try:
        import accounting_waves_32 as w32  # noqa: F401
        assert callable(w32.g702_ar_lifecycle_report)
        assert callable(w32.portfolio_job_variance_v2)
    except Exception as exc:
        errors.append(f'accounting_waves_32: {exc}')

    print('6p. Wave 33 Sage distribution (57–60)…')
    try:
        import accounting_waves_33 as w33  # noqa: F401
        assert callable(w33.three_way_match_line_grid)
        v8 = w33.sage_mirror_deploy_check_v8()
        if not v8.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v8: {v8}')
    except Exception as exc:
        errors.append(f'accounting_waves_33: {exc}')

    print('6q. Wave 34 cross-module (49, 61, 65, 69)…')
    try:
        import accounting_waves_34 as w34  # noqa: F401
        assert callable(w34.sage_pull_gl_journal_batch_status)
        assert callable(w34.company_matrix_dashboard)
        v9 = w34.sage_mirror_deploy_check_v9()
        if not v9.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v9: {v9}')
    except Exception as exc:
        errors.append(f'accounting_waves_34: {exc}')

    print('6r. Waves 35–37 (50–52, 54–60, 62–64)…')
    try:
        import accounting_waves_35 as w35  # noqa: F401
        import accounting_waves_36 as w36  # noqa: F401
        import accounting_waves_37 as w37  # noqa: F401
        assert callable(w35.subledger_gl_tieout_report)
        assert callable(w36.three_way_auto_hold_exceptions)
        assert callable(w37.sage_pull_pr_pay_runs)
        v10 = w37.sage_mirror_deploy_check_v10()
        if not v10.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v10: {v10}')
    except Exception as exc:
        errors.append(f'accounting_waves_35_37: {exc}')

    print('6s. Waves 38 (66–68) JC/FA, retainage, WIP GL…')
    try:
        import accounting_waves_38 as w38  # noqa: F401
        assert callable(w38.jc_cip_fa_capitalization_preview)
        assert callable(w38.project_revenue_recognition_report)
        assert callable(w38.wip_auto_je_with_sor_guard)
        v11 = w38.sage_mirror_deploy_check_v11()
        if not v11.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v11: {v11}')
    except Exception as exc:
        errors.append(f'accounting_waves_38: {exc}')

    print('6t. Waves 39–42 (62 complete, 70–96)…')
    try:
        import accounting_waves_39 as w39  # noqa: F401
        import accounting_waves_40 as w40  # noqa: F401
        import accounting_waves_41 as w41  # noqa: F401
        import accounting_waves_42 as w42  # noqa: F401
        from accounting_wave_registry import roadmap_waves_through_96_status

        assert callable(w39.intercompany_settlement_round_trip)
        assert callable(w42.go_live_checklist_signoff)
        road = roadmap_waves_through_96_status()
        if not road.get('complete_through_96'):
            errors.append(f'roadmap_through_96: {road}')
        v12 = w42.sage_mirror_deploy_check_v12()
        if not v12.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v12: {v12}')
    except Exception as exc:
        errors.append(f'accounting_waves_39_42: {exc}')

    print('6u. Construction integration (health, idempotency)…')
    try:
        import accounting_integration_health as aih  # noqa: F401
        assert callable(aih.construction_integration_health_dashboard)
        assert callable(aih.apply_cre_autopost_profile)
        import subprocess
        proc = subprocess.run(
            [sys.executable, 'scripts/test_accounting_construction_idempotency.py'],
            cwd='.',
            env={**dict(__import__('os').environ), 'PYTHONPATH': '.'},
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            errors.append(f'construction_idempotency: {proc.stdout}\n{proc.stderr}')
    except Exception as exc:
        errors.append(f'construction_integration: {exc}')

    print('6v. PM–Sage accounting depth (43–44)…')
    try:
        import accounting_waves_43 as w43  # noqa: F401
        import accounting_waves_44 as w44  # noqa: F401
        assert callable(w43.budget_publish_accounting_wizard)
        assert callable(w44.sage_unified_setup_health)
        v13 = w44.sage_mirror_deploy_check_v13()
        if not v13.get('ok'):
            errors.append(f'sage_mirror_deploy_check_v13: {v13}')
    except Exception as exc:
        errors.append(f'accounting_waves_43_44: {exc}')

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
