#!/usr/bin/env python3
"""Download or verify the bundled Java runtime used for MPP import."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from java_runtime import ensure_java_runtime, java_runtime_status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='Ensure Java is available for MPP import.')
    parser.add_argument('--print-home', action='store_true', help='Print CASEPM_JAVA_HOME and exit.')
    parser.add_argument('--no-download', action='store_true', help='Only report status; do not download.')
    args = parser.parse_args()

    status = ensure_java_runtime(auto_download=not args.no_download)
    if args.print_home and status.get('java_home'):
        print(status['java_home'])
    elif not args.print_home:
        print(status.get('message') or 'Java runtime check complete.')
        if status.get('setup_hint') and not status.get('ok'):
            print(status['setup_hint'])

    return 0 if status.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
