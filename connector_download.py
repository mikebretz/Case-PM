"""Build the Case PM Desktop Connector — quick desktop shortcut for Windows users."""

from __future__ import annotations

import io
import os
from urllib.parse import urlparse

CONNECTOR_COOKIE = 'casepm_connector'
CONNECTOR_QUERY = 'connector'
CONNECTOR_VERSION = '1.5'

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


def _vbs_escape(value: str) -> str:
    return value.replace('"', '""')


def build_connector_installer(server_url: str) -> io.BytesIO:
    """Return a compact VBS — no oversized command lines (fixes error 800700CE)."""
    server_url = _normalize_server_url(server_url)
    login_url = connector_login_url(server_url)
    icon_url = f'{server_url}/static/img/casepm-icon.ico'

    vbs = f'''\' Case PM Desktop Connector v{CONNECTOR_VERSION}
Option Explicit
Dim answer, sh, fso, appDir, iconPath, desktop, shortcutPath
Dim xhr, stream, oLink

answer = MsgBox("Add Case PM to your desktop?" & vbCrLf & vbCrLf & "A shortcut with the Case PM icon will open:" & vbCrLf & "{_vbs_escape(server_url)}", vbYesNo + vbQuestion, "Case PM")
If answer <> vbYes Then WScript.Quit 0

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\\CasePM"
iconPath = appDir & "\\casepm-icon.ico"

If Not fso.FolderExists(appDir) Then fso.CreateFolder appDir

On Error Resume Next
Set xhr = CreateObject("MSXML2.XMLHTTP")
xhr.Open "GET", "{_vbs_escape(icon_url)}", False
xhr.Send
If xhr.Status = 200 Then
  Set stream = CreateObject("ADODB.Stream")
  stream.Type = 1
  stream.Open
  stream.Write xhr.responseBody
  stream.SaveToFile iconPath, 2
  stream.Close
End If
On Error GoTo 0

desktop = sh.SpecialFolders("Desktop")
shortcutPath = desktop & "\\Case PM.lnk"
Set oLink = sh.CreateShortcut(shortcutPath)
oLink.TargetPath = "{_vbs_escape(login_url)}"
oLink.Description = "Case PM - Construction OS"
If fso.FileExists(iconPath) Then oLink.IconLocation = iconPath & ",0"
oLink.Save

sh.Run "{_vbs_escape(login_url)}", 1, False
WScript.Quit 0
'''

    buf = io.BytesIO(vbs.encode('utf-8'))
    buf.seek(0)
    return buf


def build_connector_zip(server_url: str) -> io.BytesIO:
    return build_connector_installer(server_url)
