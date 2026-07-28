#!/usr/bin/env python3
"""Sylvorin Desktop — native window (no browser tab).

Starts the Vite game server, then opens Sylvorin in a pywebview window.
Use RUN-SYLVORIN-DESKTOP.bat on Windows.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser


def _app_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _log_path() -> str:
    log_dir = os.path.join(_app_root(), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, 'desktop-launch.log')


def log(message: str) -> None:
    line = f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}'
    print(line, flush=True)
    try:
        with open(_log_path(), 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')
    except OSError:
        pass


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def wait_for_server(url: str, *, timeout: float = 60.0) -> bool:
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


class ViteServer:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.error: str | None = None

    def start(self, host: str, port: int, use_preview: bool = True) -> None:
        root = _app_root()
        npm_cmd = 'npm.cmd' if sys.platform == 'win32' else 'npm'
        script = 'desktop' if use_preview else 'dev'

        if use_preview and not os.path.isdir(os.path.join(root, 'dist')):
            log('Building game for desktop (first run may take a minute)...')
            build = subprocess.run(
                [npm_cmd, 'run', 'build'],
                cwd=root,
                shell=sys.platform == 'win32',
                capture_output=True,
                text=True,
            )
            if build.returncode != 0:
                self.error = build.stderr or 'npm run build failed'
                log(self.error)
                return

        log(f'Starting Sylvorin server on http://{host}:{port}')
        try:
            self.process = subprocess.Popen(
                [npm_cmd, 'run', script],
                cwd=root,
                shell=sys.platform == 'win32',
                env={**os.environ, 'SYLVORIN_HOST': host, 'SYLVORIN_PORT': str(port)},
            )
        except OSError as exc:
            self.error = str(exc)
            log(f'Could not start npm: {exc}')


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
        'Install from: https://go.microsoft.com/fwlink/p/?LinkId=2124703'
    )


def open_native_window(start_url: str) -> bool:
    try:
        import webview
    except ImportError:
        log('pywebview is not installed. Run INSTALL-PACKAGES.bat')
        return False

    ok, message = check_webview2_windows()
    if not ok:
        log(message)
        return False

    kwargs: dict = {'width': 1440, 'height': 900, 'min_size': (1024, 700)}
    log(f'Opening Sylvorin desktop window: {start_url}')
    try:
        webview.create_window('Sylvorin', start_url, **kwargs)
        if sys.platform == 'win32':
            webview.start(gui='edgechromium')
        else:
            webview.start()
        return True
    except Exception as exc:
        log(f'Could not open desktop window: {exc}')
        log(traceback.format_exc())
        return False


def main() -> int:
    os.chdir(_app_root())
    host = os.environ.get('SYLVORIN_HOST', '127.0.0.1')
    port = int(os.environ.get('SYLVORIN_PORT', '5173'))
    start_url = f'http://{host}:{port}'
    health_url = start_url

    log('Sylvorin Desktop starting…')
    log(f'Install folder: {_app_root()}')
    log(f'Log file: {_log_path()}')

    server = ViteServer()
    already_running = port_is_open(host, port) and wait_for_server(health_url, timeout=2.0)

    if not already_running:
        if port_is_open(host, port):
            log(f'Port {port} is in use. Close the other app or set SYLVORIN_PORT.')
            return 1
        server.start(host, port, use_preview=True)
        if server.error:
            return 1
        if not wait_for_server(health_url, timeout=90.0):
            log('Sylvorin server did not respond in time.')
            if server.process:
                server.process.terminate()
            return 1
    else:
        log('Sylvorin server already running; opening window only.')

    if open_native_window(start_url):
        if server.process:
            server.process.terminate()
        return 0

    log('Falling back to default browser.')
    webbrowser.open(start_url)
    if server.process:
        try:
            input('Sylvorin is running in your browser. Press Enter to stop the server… ')
        except (EOFError, KeyboardInterrupt):
            pass
        server.process.terminate()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
