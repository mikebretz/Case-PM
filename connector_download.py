"""Build the Case PM Desktop Connector — quick desktop shortcut for Windows users."""

from __future__ import annotations

import base64
import io
import os
from urllib.parse import urlparse

CONNECTOR_COOKIE = 'casepm_connector'
CONNECTOR_QUERY = 'connector'
CONNECTOR_VERSION = '1.3'

_CONNECTOR_DIR = os.path.join(os.path.dirname(__file__), 'connector')
_ICON_NAME = 'casepm-icon.ico'
_ICON_B64_CACHE: str | None = None


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


def _vbs_escape(value: str) -> str:
    return value.replace('"', '""')


def _ps_escape(value: str) -> str:
    return value.replace("'", "''")


def _icon_base64() -> str:
    global _ICON_B64_CACHE
    if _ICON_B64_CACHE is not None:
        return _ICON_B64_CACHE
    icon_path = os.path.join(_CONNECTOR_DIR, _ICON_NAME)
    if not os.path.isfile(icon_path):
        icon_path = os.path.join('static', 'img', _ICON_NAME)
    with open(icon_path, 'rb') as fh:
        _ICON_B64_CACHE = base64.b64encode(fh.read()).decode('ascii')
    return _ICON_B64_CACHE


def _powershell_body(server_url: str, login_url: str, icon_b64: str) -> str:
    return f"""
$ErrorActionPreference = 'Stop'
$appDir = Join-Path $env:LOCALAPPDATA 'CasePM'
New-Item -ItemType Directory -Force -Path $appDir | Out-Null
$iconPath = Join-Path $appDir 'casepm-icon.ico'
[IO.File]::WriteAllBytes($iconPath, [Convert]::FromBase64String('{icon_b64}'))
@{{ server_url = '{_ps_escape(server_url)}'; login_url = '{_ps_escape(login_url)}'; version = '{CONNECTOR_VERSION}'; installed_at = (Get-Date).ToString('o') }} |
    ConvertTo-Json | Set-Content (Join-Path $appDir 'connector.json') -Encoding UTF8
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Case PM.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = '{_ps_escape(login_url)}'
$shortcut.Description = 'Case PM - Construction OS'
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Save()
""".strip()


def build_connector_installer(server_url: str) -> io.BytesIO:
    """Return a small VBS that asks once, then adds the desktop shortcut."""
    server_url = _normalize_server_url(server_url)
    login_url = connector_login_url(server_url)
    icon_b64 = _icon_base64()
    ps_encoded = base64.b64encode(
        _powershell_body(server_url, login_url, icon_b64).encode('utf-16-le')
    ).decode('ascii')

    vbs = f'''\' Case PM Desktop Connector v{CONNECTOR_VERSION}
Option Explicit
Dim answer, sh, loginUrl
loginUrl = "{_vbs_escape(login_url)}"
answer = MsgBox("Add Case PM to your desktop?" & vbCrLf & vbCrLf & "A shortcut with the Case PM icon will open:" & vbCrLf & "{_vbs_escape(server_url)}", vbYesNo + vbQuestion, "Case PM")
If answer <> vbYes Then WScript.Quit 0
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand {ps_encoded}", 0, True
sh.Run loginUrl, 1, False
WScript.Quit 0
'''

    buf = io.BytesIO(vbs.encode('utf-8'))
    buf.seek(0)
    return buf


def build_connector_zip(server_url: str) -> io.BytesIO:
    return build_connector_installer(server_url)
