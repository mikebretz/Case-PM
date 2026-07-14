#!/usr/bin/env python3
"""
Recovery access launcher — used by RECOVERY-ACCESS.bat / EMERGENCY-RECOVERY.bat.

- Ensures instance/recovery.access exists (with access_token)
- Waits for the Case PM server (starts are handled by the .bat)
- Opens one-click /recovery/enter?token=... in the default browser
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
import webbrowser
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

RECOVERY_FILE = os.path.join('instance', 'recovery.access')


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_recovery() -> dict:
    if not os.path.isfile(RECOVERY_FILE):
        return {}
    try:
        with open(RECOVERY_FILE, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_recovery(data: dict) -> None:
    os.makedirs('instance', exist_ok=True)
    with open(RECOVERY_FILE, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2)
        fh.write('\n')


def ensure_access_token() -> str:
    data = _load_recovery()
    token = (data.get('access_token') or '').strip()
    if token:
        return token
    if not (data.get('email') and data.get('password') is not None):
        return ''
    data['access_token'] = secrets.token_urlsafe(32)
    _save_recovery(data)
    print('Generated new recovery access_token in instance/recovery.access')
    return data['access_token']


def wait_for_server(base_url: str, *, attempts: int = 30, delay: float = 2.0) -> bool:
    for i in range(attempts):
        try:
            urlopen(f'{base_url}/recovery', timeout=3)
            return True
        except (URLError, OSError, TimeoutError):
            if i < attempts - 1:
                time.sleep(delay)
    return False


def main() -> int:
    os.chdir(_repo_root())
    sys.path.insert(0, os.getcwd())

    host = (os.environ.get('CASEPM_HOST') or '127.0.0.1').strip()
    port = (os.environ.get('CASEPM_PORT') or '5000').strip()
    base = f'http://{host}:{port}'

    if not os.path.isfile(RECOVERY_FILE):
        print('')
        print('ERROR: instance/recovery.access not found.')
        print('Run SETUP-RECOVERY-ACCESS.bat once to configure owner recovery credentials.')
        print('')
        return 1

    data = _load_recovery()
    if not (data.get('email') and data.get('password') is not None):
        print('')
        print('ERROR: instance/recovery.access is incomplete (missing email or password).')
        print('Run SETUP-RECOVERY-ACCESS.bat again to reconfigure.')
        print('')
        return 1

    print(f'Waiting for Case PM at {base} ...')
    if not wait_for_server(base):
        print('')
        print('ERROR: Case PM server is not responding.')
        print('Close any stuck server windows, then run this file again.')
        print('If needed, start the server manually with run.bat first.')
        print('')
        return 1

    token = ensure_access_token()
    if token:
        # Cache-bust helps when the browser had a bad session cookie
        url = f'{base}/recovery/enter?token={quote(token, safe="")}&fresh={int(time.time())}'
        print(f'Opening one-click recovery access: {base}/recovery/enter?token=...')
    else:
        url = f'{base}/recovery?fresh={int(time.time())}'
        print(f'Opening recovery login: {url}')

    webbrowser.open(url)
    print('')
    print('If the browser shows a login loop, clear cookies for this site or use a private window.')
    print(f'Manual recovery page: {base}/recovery')
    print('')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
