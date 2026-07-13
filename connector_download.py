"""Build the Case PM Desktop Connector — runs on click, installs to Documents."""

from __future__ import annotations

import base64
import io
import os
from urllib.parse import urlparse

CONNECTOR_COOKIE = 'casepm_connector'
CONNECTOR_QUERY = 'connector'
CONNECTOR_VERSION = '2.1'
INSTALL_FOLDER = 'Case PM Desktop'
ICON_FILE = 'Case PM.ico'
LAUNCHER_FILE = 'Case PM.vbs'

_CONNECTOR_DIR = os.path.join(os.path.dirname(__file__), 'connector')
_ICON_CANDIDATES = (
    os.path.join(_CONNECTOR_DIR, 'casepm-icon.ico'),
    os.path.join(_CONNECTOR_DIR, 'casepm-desktop-icon.ico'),
    os.path.join('static', 'img', 'casepm-icon.ico'),
    os.path.join('static', 'img', 'casepm-desktop-icon.ico'),
)
_ICON_B64_CACHE: str | None = None

_DECODE_BASE64_VBS = '''
Sub DecodeBase64ToFile(path, b64)
  Dim xml, node, stream
  Set xml = CreateObject("Microsoft.XMLDOM")
  Set node = xml.createElement("b64")
  node.DataType = "bin.base64"
  node.Text = b64
  Set stream = CreateObject("ADODB.Stream")
  stream.Type = 1
  stream.Open
  stream.Write node.NodeTypedValue
  stream.SaveToFile path, 2
  stream.Close
End Sub
'''.strip()


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


def _icon_base64() -> str:
    global _ICON_B64_CACHE
    if _ICON_B64_CACHE is not None:
        return _ICON_B64_CACHE
    for path in _ICON_CANDIDATES:
        if os.path.isfile(path):
            with open(path, 'rb') as fh:
                _ICON_B64_CACHE = base64.b64encode(fh.read()).decode('ascii')
            return _ICON_B64_CACHE
    raise FileNotFoundError('Case PM icon .ico not found')


def _install_main_vbs(server_url: str, login_url: str, icon_b64: str) -> str:
    # Shortcut must target wscript + local launcher — Windows ignores custom icons on URL shortcuts.
    return f'''
Sub InstallCasePM()
  Dim sh, fso, appDir, iconPath, launcherPath, desktop, result, oLink, launcher
  Set sh = CreateObject("WScript.Shell")
  Set fso = CreateObject("Scripting.FileSystemObject")
  appDir = sh.SpecialFolders("MyDocuments") & "\\{INSTALL_FOLDER}"
  result = MsgBox("Case PM will be set up in your Documents folder:" & vbCrLf & vbCrLf & appDir & vbCrLf & vbCrLf & "A desktop shortcut will be added." & vbCrLf & vbCrLf & "Click OK to continue.", vbOKCancel + vbInformation, "Case PM Desktop")
  If result <> 1 Then Exit Sub

  If Not fso.FolderExists(appDir) Then fso.CreateFolder appDir
  iconPath = appDir & "\\{ICON_FILE}"
  launcherPath = appDir & "\\{LAUNCHER_FILE}"

  DecodeBase64ToFile iconPath, "{icon_b64}"

  Set cfg = fso.CreateTextFile(appDir & "\\server.txt", True)
  cfg.WriteLine "{_vbs_escape(server_url)}"
  cfg.Close

  Set launcher = fso.CreateTextFile(launcherPath, True)
  launcher.WriteLine "CreateObject(""WScript.Shell"").Run ""{_vbs_escape(login_url)}"", 1, False"
  launcher.Close

  desktop = sh.SpecialFolders("Desktop")
  Set oLink = sh.CreateShortcut(desktop & "\\Case PM.lnk")
  oLink.TargetPath = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\\System32\\wscript.exe"
  oLink.Arguments = """" & launcherPath & """"
  oLink.WorkingDirectory = appDir
  oLink.Description = "Case PM - Construction OS"
  oLink.IconLocation = iconPath & ",0"
  oLink.Save

  sh.Run """" & launcherPath & """", 1, False
End Sub
'''.strip()


def _full_vbscript(server_url: str, login_url: str, icon_b64: str) -> str:
    return '\r\n'.join([
        _DECODE_BASE64_VBS,
        _install_main_vbs(server_url, login_url, icon_b64).replace('\n', '\r\n'),
    ])


def build_connector_hta(server_url: str) -> io.BytesIO:
    server_url = _normalize_server_url(server_url)
    login_url = connector_login_url(server_url)
    icon_b64 = _icon_base64()
    vb = _full_vbscript(server_url, login_url, icon_b64)

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
{vb}

Sub Window_OnLoad
  window.resizeTo 0, 0
  InstallCasePM
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
    server_url = _normalize_server_url(server_url)
    login_url = connector_login_url(server_url)
    icon_b64 = _icon_base64()

    vbs = f'''\' Case PM Desktop Connector v{CONNECTOR_VERSION}
Option Explicit
{_full_vbscript(server_url, login_url, icon_b64)}
InstallCasePM
WScript.Quit 0
'''

    buf = io.BytesIO(vbs.encode('utf-8'))
    buf.seek(0)
    return buf


def build_connector_zip(server_url: str) -> io.BytesIO:
    return build_connector_hta(server_url)
