"""Build the Case PM Desktop Connector one-click installer for Windows users."""

from __future__ import annotations

import base64
import io
import os
from urllib.parse import urlparse

CONNECTOR_COOKIE = 'casepm_connector'
CONNECTOR_QUERY = 'connector'
CONNECTOR_VERSION = '1.1'

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


def _ps_escape(value: str) -> str:
    return value.replace("'", "''")


def build_connector_installer(server_url: str) -> io.BytesIO:
    """Return a single self-contained .bat that installs the desktop connector."""
    server_url = _normalize_server_url(server_url)
    login_url = connector_login_url(server_url)
    icon_url = f'{server_url}/static/img/casepm-icon.ico'

    ps1 = f"""
Add-Type -AssemblyName System.Windows.Forms
$server = '{_ps_escape(server_url)}'
$login = '{_ps_escape(login_url)}'
$iconUrl = '{_ps_escape(icon_url)}'

$prompt = "Install Case PM on your desktop?`n`nThis connects you securely to:`n$server`n`nA Case PM icon will be added to your desktop."
$answer = [System.Windows.Forms.MessageBox]::Show(
    $prompt,
    'Case PM Desktop Connector',
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Question
)
if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) {{ exit 0 }}

try {{
    $appDir = Join-Path $env:LOCALAPPDATA 'CasePM'
    New-Item -ItemType Directory -Force -Path $appDir | Out-Null

    $iconPath = Join-Path $appDir 'casepm-icon.ico'
    try {{
        Invoke-WebRequest -Uri $iconUrl -OutFile $iconPath -UseBasicParsing
    }} catch {{
        $iconPath = $null
    }}

  @{{ server_url = $server; login_url = $login; version = '{CONNECTOR_VERSION}'; installed_at = (Get-Date).ToString('o') }} |
        ConvertTo-Json | Set-Content (Join-Path $appDir 'connector.json') -Encoding UTF8

    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'Case PM.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $login
    $shortcut.Description = 'Case PM - secure connection to your company server'
    if ($iconPath -and (Test-Path $iconPath)) {{
        $shortcut.IconLocation = "$iconPath,0"
    }}
    $shortcut.Save()

    [System.Windows.Forms.MessageBox]::Show(
        "Case PM is on your desktop.`n`nDouble-click the Case PM icon anytime to sign in.",
        'Installation Complete',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
}} catch {{
    [System.Windows.Forms.MessageBox]::Show(
        "Could not install Case PM Connector:`n$($_.Exception.Message)",
        'Installation Failed',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}}
""".strip()

    encoded = base64.b64encode(ps1.encode('utf-16-le')).decode('ascii')
    bat = (
        '@echo off\r\n'
        'title Case PM Connector\r\n'
        f'powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}\r\n'
        'exit /b %ERRORLEVEL%\r\n'
    )

    buf = io.BytesIO(bat.encode('utf-8'))
    buf.seek(0)
    return buf


def build_connector_zip(server_url: str) -> io.BytesIO:
    """Legacy ZIP builder — kept for compatibility, prefer build_connector_installer."""
    return build_connector_installer(server_url)
