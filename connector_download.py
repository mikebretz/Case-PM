"""Build the Case PM Desktop Connector — runs on click, installs to Documents."""

from __future__ import annotations

import io
from urllib.parse import urlparse

CONNECTOR_COOKIE = 'casepm_connector'
CONNECTOR_QUERY = 'connector'
CONNECTOR_VERSION = '2.0'
INSTALL_FOLDER = 'Case PM Desktop'
ICON_FILE = 'Case PM.ico'


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


def _install_vbscript(server_url: str, login_url: str, icon_url: str) -> str:
    return f'''
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = sh.SpecialFolders("MyDocuments") & "\\{INSTALL_FOLDER}"
result = MsgBox("Case PM will be set up in your Documents folder:" & vbCrLf & vbCrLf & appDir & vbCrLf & vbCrLf & "A desktop shortcut will be added." & vbCrLf & vbCrLf & "Click OK to continue.", vbOKCancel + vbInformation, "Case PM Desktop")
If result <> 1 Then WScript.Quit 0

If Not fso.FolderExists(appDir) Then fso.CreateFolder appDir
iconPath = appDir & "\\{ICON_FILE}"

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

Set cfg = fso.CreateTextFile(appDir & "\\server.txt", True)
cfg.WriteLine "{_vbs_escape(server_url)}"
cfg.Close

desktop = sh.SpecialFolders("Desktop")
Set oLink = sh.CreateShortcut(desktop & "\\Case PM.lnk")
oLink.TargetPath = "{_vbs_escape(login_url)}"
oLink.Description = "Case PM - Construction OS"
oLink.WorkingDirectory = appDir
If fso.FileExists(iconPath) Then oLink.IconLocation = iconPath & ",0"
oLink.Save

sh.Run "{_vbs_escape(login_url)}", 1, False
'''.strip()


def build_connector_hta(server_url: str) -> io.BytesIO:
    """HTA runs immediately when the user opens it — closest to click-to-install on Windows."""
    server_url = _normalize_server_url(server_url)
    login_url = connector_login_url(server_url)
    icon_url = f'{server_url}/static/img/casepm-desktop-icon.ico'
    vb = _install_vbscript(server_url, login_url, icon_url).replace('\n', '\r\n')

    hta = f'''<!DOCTYPE html>
<html>
<head>
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<title>Case PM Desktop</title>
<HTA:APPLICATION
  ID="CasePMDesktop"
  APPLICATIONNAME="Case PM Desktop"
  BORDER="none"
  CAPTION="Case PM Desktop"
  SHOWINTASKBAR="no"
  SINGLEINSTANCE="yes"
  SYSMENU="no"
  SCROLL="no"
  WINDOWSTATE="minimize"
/>
<script language="VBScript">
Sub Window_OnLoad
  window.resizeTo 0, 0
  {vb}
  window.close
End Sub
</script>
</head>
<body></body>
</html>
'''

    buf = io.BytesIO(hta.encode('utf-8'))
    buf.seek(0)
    return buf


def build_connector_installer(server_url: str) -> io.BytesIO:
    """VBS fallback for environments that block HTA."""
    server_url = _normalize_server_url(server_url)
    login_url = connector_login_url(server_url)
    icon_url = f'{server_url}/static/img/casepm-desktop-icon.ico'
    vb = _install_vbscript(server_url, login_url, icon_url)

    vbs = f'''\' Case PM Desktop Connector v{CONNECTOR_VERSION}
Option Explicit
{vb}
WScript.Quit 0
'''

    buf = io.BytesIO(vbs.encode('utf-8'))
    buf.seek(0)
    return buf


def build_connector_zip(server_url: str) -> io.BytesIO:
    return build_connector_hta(server_url)
