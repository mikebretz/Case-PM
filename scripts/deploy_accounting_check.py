#!/usr/bin/env python3
"""Post-deploy accounting checks — smoke + startup guard."""
from __future__ import annotations

import sys


def main() -> int:
    from accounting_waves_22 import deploy_accounting_check

    result = deploy_accounting_check()
    for row in result.get('results') or []:
        status = 'OK' if row.get('ok') else 'FAIL'
        print(f"[{status}] {row.get('check')}")
        if not row.get('ok'):
            print(row.get('detail', ''))
    if result.get('ok'):
        print('Deploy accounting check: OK')
        return 0
    print('Deploy accounting check: FAILED')
    return 1


if __name__ == '__main__':
    sys.exit(main())
