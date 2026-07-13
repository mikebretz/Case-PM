"""Build the Case PM Desktop Connector download package for Windows users."""

from __future__ import annotations

import io
import os
import zipfile
from urllib.parse import urlparse

CONNECTOR_COOKIE = 'casepm_connector'
CONNECTOR_QUERY = 'connector'
CONNECTOR_VERSION = '1.0'

_CONNECTOR_DIR = os.path.join(os.path.dirname(__file__), 'connector')
_ICON_NAME = 'casepm-icon.ico'


def _normalize_server_url(url: str) -> str:
    raw = (url or '').strip().rstrip('/')
    if not raw:
        return 'http://127.0.0.1:5000'
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = f'http://{raw}'
    return raw.rstrip('/')


def connector_login_url(server_url: str) -> str:
    base = _normalize_server_url(server_url)
    sep = '&' if '?' in base else '?'
    return f'{base}/login?{CONNECTOR_QUERY}=1'


def is_connector_request() -> bool:
    from flask import request

    if request.args.get(CONNECTOR_QUERY) == '1':
        return True
    return request.cookies.get(CONNECTOR_COOKIE) == '1'


def mark_connector_response(response):
    from flask import request

    if request.args.get(CONNECTOR_QUERY) == '1':
        secure = request.is_secure or (
            request.headers.get('X-Forwarded-Proto', '').lower() == 'https'
        )
        response.set_cookie(
            CONNECTOR_COOKIE,
            '1',
            max_age=60 * 60 * 24 * 365,
            httponly=False,
            samesite='Lax',
            secure=secure,
        )
    return response


def _read_template(name: str, server_url: str) -> str:
    path = os.path.join(_CONNECTOR_DIR, name)
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    login_url = connector_login_url(server_url)
    return (
        text.replace('{{SERVER_URL}}', _normalize_server_url(server_url))
        .replace('{{LOGIN_URL}}', login_url)
        .replace('{{CONNECTOR_VERSION}}', CONNECTOR_VERSION)
    )


def build_connector_zip(server_url: str) -> io.BytesIO:
    """Return an in-memory ZIP with the Windows connector installer."""
    server_url = _normalize_server_url(server_url)
    buf = io.BytesIO()
    icon_path = os.path.join(_CONNECTOR_DIR, _ICON_NAME)

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('README.txt', _read_template('README.txt', server_url))
        zf.writestr('Install Case PM Connector.bat', _read_template('install.bat', server_url))
        zf.writestr('install-connector.ps1', _read_template('install-connector.ps1', server_url))
        if os.path.isfile(icon_path):
            zf.write(icon_path, _ICON_NAME)

    buf.seek(0)
    return buf
