#!/usr/bin/env python3
"""Pre-flight check before starting Case PM server (accounting routes import)."""
from __future__ import annotations

import sys


def main() -> int:
    from accounting_waves_19 import accounting_startup_guard

    result = accounting_startup_guard()
    if result.get('ok'):
        print('Accounting startup guard: OK')
        return 0
    print('Accounting startup guard FAILED:')
    for err in result.get('errors') or []:
        print(' -', err)
    return 1


if __name__ == '__main__':
    sys.exit(main())
