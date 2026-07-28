#!/usr/bin/env python3
"""Case PM Desktop — run Case PM in a native window (no separate browser tab).

Starts the local Flask app with Waitress, then opens it in a pywebview window
(Edge WebView2 on Windows). Use RUN-DESKTOP.bat on Windows, or:

    pip install -r requirements-desktop.txt
    python desktop_launcher.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _log_path() -> str:
    return os.path.join(_repo_root(), 'instance', 'desktop-launch.log')


def log(message: str) -> None:
    line = f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}'
    print(line, flush=True)
    try:
        os.makedirs(os.path.join(_repo_root(), 'instance'), exist_ok=True)
        with open(_log_path(), 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')
    except OSError:
        pass


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


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def check_webview2_windows() -> tuple[bool, str]:
    if sys.platform != 'win32':
        return True, ''
    try:
        import winreg
    except ImportError:
        return True, ''

    keys = (
        r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    )
    for key_path in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path):
                return True, ''
        except OSError:
            continue
    return False, (
        'Microsoft Edge WebView2 Runtime is not installed.\n'
        'Install it from: https://go.microsoft.com/fwlink/p/?LinkId=2124703\n'
        'Then run RUN-DESKTOP.bat again.'
    )


class ServerThread:
    def __init__(self) -> None:
        self.error: BaseException | None = None
        self.started = False
        self._thread: threading.Thread | None = None

    def start(self, host: str, port: int) -> None:
        def _run() -> None:
            try:
                from app import app

                self.started = True
                try:
                    import waitress

                    log(f'Starting Waitress on http://{host}:{port}')
                    waitress.serve(app, host=host, port=port, threads=8, channel_timeout=120)
                except ImportError:
                    log(f'Starting Flask dev server on http://{host}:{port}')
                    app.run(host=host, port=port, threaded=True, use_reloader=False)
            except Exception as exc:
                self.error = exc
                log(f'Server failed: {exc}')
                log(traceback.format_exc())

        self._thread = threading.Thread(target=_run, daemon=True, name='casepm-server')
        self._thread.start()


def open_native_window(start_url: str) -> bool:
    try:
        import webview
    except ImportError:
        log('pywebview is not installed.')
        return False

    ok, message = check_webview2_windows()
    if not ok:
        log(message)
        return False

    icon_path = os.path.join(_repo_root(), 'static', 'img', 'casepm-desktop-icon.ico')
    kwargs: dict = {'width': 1440, 'height': 900, 'min_size': (1024, 700)}
    if os.path.isfile(icon_path):
        kwargs['icon'] = icon_path

    log(f'Opening desktop window: {start_url}')
    try:
        webview.create_window('Case PM', start_url, **kwargs)
        if sys.platform == 'win32':
            webview.start(gui='edgechromium')
        else:
            webview.start()
        log('Desktop window closed.')
        return True
    except Exception as exc:
        log(f'Could not open desktop window: {exc}')
        log(traceback.format_exc())
        return False


def wait_for_enter(message: str) -> None:
    print()
    print(message)
    try:
        input('Press Enter to exit… ')
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    os.chdir(_repo_root())
    if _repo_root() not in sys.path:
        sys.path.insert(0, _repo_root())

    os.environ.setdefault('CASEPM_HOST', '127.0.0.1')
    os.environ.setdefault('CASEPM_PORT', '5000')
    os.environ.setdefault('CASEPM_REMOTE', '0')
    os.environ.setdefault('CASEPM_DEBUG', '0')
    os.environ['CASEPM_DESKTOP'] = '1'

    host = os.environ['CASEPM_HOST']
    port = int(os.environ['CASEPM_PORT'])
    health_url = f'http://{host}:{port}/api/health'
    start_url = f'http://{host}:{port}/login?desktop=1'

    log('Case PM Desktop starting…')
    log(f'Log file: {_log_path()}')

    server = ServerThread()
    already_running = port_is_open(host, port) and wait_for_server(health_url, timeout=2.0)

    if already_running:
        log(f'Case PM is already running on port {port}; opening window only.')
    else:
        if port_is_open(host, port):
            log(f'Port {port} is in use by another program. Close it or set CASEPM_PORT to a free port.')
            wait_for_enter('Could not start Case PM Desktop.')
            return 1

        server.start(host, port)
        deadline = time.time() + 90.0
        while time.time() < deadline:
            if server.error is not None:
                wait_for_enter('Case PM server failed to start. See messages above.')
                return 1
            if wait_for_server(health_url, timeout=1.0):
                break
            time.sleep(0.3)
        else:
            log('Case PM server did not respond in time.')
            if server.error is not None:
                log(str(server.error))
            wait_for_enter('Case PM server did not start. See messages above.')
            return 1

    if open_native_window(start_url):
        return 0

    log('Falling back to your default web browser.')
    try:
        webbrowser.open(start_url)
    except Exception as exc:
        log(f'Could not open browser: {exc}')
        wait_for_enter(f'Open this URL manually: {start_url}')
        return 1

    wait_for_enter('Case PM is running in your browser. Close this window to stop the server.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
