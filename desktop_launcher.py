#!/usr/bin/env python3
"""Case PM Desktop — run Case PM in a native window (no separate browser tab).

Starts the local Flask app with Waitress, then opens it in a pywebview window
(Edge WebView2 on Windows). Use RUN-DESKTOP.bat on Windows, or:

    pip install -r requirements-desktop.txt
    python desktop_launcher.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
import urllib.error
import urllib.request


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def wait_for_server(url: str, *, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.3)
    return False


def start_server_thread(host: str, port: int) -> None:
    from app import app

    def _run() -> None:
        try:
            import waitress
            waitress.serve(app, host=host, port=port, threads=8, channel_timeout=120)
        except ImportError:
            app.run(host=host, port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True, name='casepm-server')
    thread.start()


def main() -> int:
    os.environ.setdefault('CASEPM_HOST', '127.0.0.1')
    os.environ.setdefault('CASEPM_PORT', '5000')
    os.environ.setdefault('CASEPM_REMOTE', '0')
    os.environ.setdefault('CASEPM_DEBUG', '0')
    os.environ['CASEPM_DESKTOP'] = '1'

    host = os.environ['CASEPM_HOST']
    port = int(os.environ['CASEPM_PORT'])
    start_url = f'http://{host}:{port}/login?desktop=1'

    try:
        import webview
    except ImportError:
        print('Case PM Desktop requires pywebview.')
        print('Install desktop dependencies:')
        print('  pip install -r requirements-desktop.txt')
        return 1

    print('Starting Case PM Desktop…')
    start_server_thread(host, port)
    if not wait_for_server(f'http://{host}:{port}/api/health'):
        print('Case PM server did not start in time.')
        return 1

    icon_path = os.path.join(os.path.dirname(__file__), 'static', 'img', 'casepm-desktop-icon.ico')
    kwargs = {'width': 1440, 'height': 900, 'min_size': (1024, 700)}
    if os.path.isfile(icon_path):
        kwargs['icon'] = icon_path
    webview.create_window('Case PM', start_url, **kwargs)
    webview.start()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
