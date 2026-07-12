#!/usr/bin/env python3
"""Create or update instance/recovery.access for owner break-glass login."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description='Configure Case PM owner recovery access')
    parser.add_argument('--email', help='Recovery email (developer account)')
    parser.add_argument('--password', help='Recovery password (omit to prompt securely)')
    parser.add_argument('--regenerate-token', action='store_true', help='Generate a new one-click access token')
    args = parser.parse_args()

    email = (args.email or input('Recovery email: ')).strip().lower()
    if not email or '@' not in email:
        print('A valid email address is required.', file=sys.stderr)
        return 1

    password = args.password
    if not password:
        password = getpass.getpass('Recovery password: ')
        confirm = getpass.getpass('Confirm password: ')
        if password != confirm:
            print('Passwords do not match.', file=sys.stderr)
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
