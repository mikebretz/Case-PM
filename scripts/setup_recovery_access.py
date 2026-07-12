#!/usr/bin/env python3
"""Create or update instance/recovery.access for owner break-glass login."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys


def _read_batch_credentials() -> tuple[str, str]:
    """Credentials passed from SETUP-RECOVERY-ACCESS.bat (stdin-safe on Windows)."""
    email = (os.environ.get('CASEPM_SETUP_EMAIL') or '').strip().lower()
    password = os.environ.get('CASEPM_SETUP_PASSWORD') or ''
    return email, password


def _read_interactive_credentials() -> tuple[str, str]:
    """Fallback when the script is run directly from a terminal."""
    if not sys.stdin or not sys.stdin.isatty():
        print(
            'Interactive prompts are not available in this console.\n'
            'Double-click SETUP-RECOVERY-ACCESS.bat instead, or pass --email and --password.',
            file=sys.stderr,
        )
        return '', ''

    email = input('Recovery email: ').strip().lower()
    password = getpass.getpass('Recovery password: ')
    confirm = getpass.getpass('Confirm password: ')
    if password != confirm:
        print('Passwords do not match.', file=sys.stderr)
        return email, ''
    return email, password


def main() -> int:
    parser = argparse.ArgumentParser(description='Configure Case PM owner recovery access')
    parser.add_argument('--email', help='Recovery email (developer account)')
    parser.add_argument('--password', help='Recovery password (omit to prompt securely)')
    parser.add_argument(
        '--from-batch',
        action='store_true',
        help='Read email/password from CASEPM_SETUP_* env vars (used by SETUP-RECOVERY-ACCESS.bat)',
    )
    parser.add_argument('--regenerate-token', action='store_true', help='Generate a new one-click access token')
    args = parser.parse_args()

    email = (args.email or '').strip().lower()
    password = args.password or ''

    if args.from_batch:
        batch_email, batch_password = _read_batch_credentials()
        email = email or batch_email
        password = password or batch_password
    elif not email or not password:
        interactive_email, interactive_password = _read_interactive_credentials()
        email = email or interactive_email
        password = password or interactive_password

    if not email or '@' not in email:
        print('A valid email address is required.', file=sys.stderr)
        return 1
    if not password:
        print('Password is required.', file=sys.stderr)
        return 1

    os.makedirs('instance', exist_ok=True)
    path = os.path.join('instance', 'recovery.access')
    existing = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as fh:
                existing = json.load(fh) or {}
        except (OSError, json.JSONDecodeError):
            existing = {}

    token = existing.get('access_token') or ''
    if args.regenerate_token or not token:
        token = secrets.token_urlsafe(32)

    payload = {
        'email': email,
        'password': password,
        'access_token': token,
        'note': 'Owner break-glass access. Back up this file off-site. Never commit to git.',
    }
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2)
        fh.write('\n')

    print('')
    print('Recovery access saved to instance/recovery.access')
    print(f'  Email:  {email}')
    print('  Password: (stored in file — not shown)')
    print('')
    print('Use RECOVERY-ACCESS.bat to open the recovery login, or browse to:')
    print('  http://127.0.0.1:5000/recovery')
    print('')
    print('Keep a copy of instance/recovery.access on a USB drive or personal cloud folder.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
