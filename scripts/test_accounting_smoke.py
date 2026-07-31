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

    print('5. Wave 18 module import…')
    try:
        import accounting_waves_18 as w18  # noqa: F401
    except Exception as exc:
        errors.append(f'accounting_waves_18: {exc}')

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
