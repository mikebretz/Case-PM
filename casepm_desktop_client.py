#!/usr/bin/env python3
"""Case PM Desktop client — native window pointed at a Case PM server URL."""
from __future__ import annotations

import os
import sys
import traceback


def _app_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _read_server_url() -> str:
    path = os.path.join(_app_dir(), 'server.txt')
    with open(path, encoding='utf-8') as fh:
        return fh.read().strip()


def _log_path() -> str:
    return os.path.join(_app_dir(), 'desktop-client.log')


def log(message: str) -> None:
    line = f'[{__import__("time").strftime("%Y-%m-%d %H:%M:%S")}] {message}'
    try:
        with open(_log_path(), 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')
    except OSError:
        pass


def main() -> int:
    try:
        base = _read_server_url().rstrip('/')
        start_url = f'{base}/login?desktop=1'

        import webview

        icon_path = os.path.join(_app_dir(), 'Case PM.ico')
        kwargs: dict = {'width': 1440, 'height': 900, 'min_size': (1024, 700)}
        if os.path.isfile(icon_path):
            kwargs['icon'] = icon_path

        webview.create_window('Case PM', start_url, **kwargs)
        if sys.platform == 'win32':
            webview.start(gui='edgechromium')
        else:
            webview.start()
        return 0
    except Exception as exc:
        log(f'Failed to open Case PM Desktop: {exc}')
        log(traceback.format_exc())
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
