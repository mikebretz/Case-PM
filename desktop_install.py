"""Build the Case PM Desktop App installer for Windows (WebView2 + native window + desktop icon)."""

from __future__ import annotations

import base64
import io
import json
import os
from urllib.parse import urlparse

DESKTOP_APP_VERSION = '1.0'
INSTALL_FOLDER = 'Case PM Desktop'
ICON_FILE = 'Case PM.ico'
SHORTCUT_NAME = 'Case PM'
WEBVIEW2_BOOTSTRAPPER_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'


def _normalize_server_url(url: str) -> str:
    raw = (url or '').strip().rstrip('/')
    if not raw:
        return 'http://127.0.0.1:5000'
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = f'http://{raw}'
    return raw.rstrip('/')


def _is_local_server(server_url: str) -> bool:
    host = (urlparse(server_url).hostname or '').lower()
    return host in ('127.0.0.1', 'localhost', '::1')


def build_desktop_setup_powershell(
    *,
    server_url: str,
    casepm_home: str = '',
    local_mode: bool = False,
) -> str:
    server_url = _normalize_server_url(server_url)
    config = {
        'server_url': server_url,
        'local_mode': local_mode,
        'casepm_home': casepm_home,
        'client_url': f'{server_url}/download/casepm-desktop-client.py',
        'requirements_url': f'{server_url}/download/casepm-desktop-requirements.txt',
        'icon_url': f'{server_url}/static/img/casepm-desktop-icon.ico',
        'webview2_url': WEBVIEW2_BOOTSTRAPPER_URL,
        'install_folder': INSTALL_FOLDER,
        'icon_file': ICON_FILE,
        'shortcut_name': SHORTCUT_NAME,
    }
    config_json = json.dumps(config)
    return f'''# Case PM Desktop App setup v{DESKTOP_APP_VERSION}
$ErrorActionPreference = 'Stop'
$Config = @{config_json} | ConvertFrom-Json
$AppDir = Join-Path $env:USERPROFILE "Documents\\$($Config.install_folder)"
$LogFile = Join-Path $AppDir 'setup.log'

function Write-Log {{
  param([string]$Message)
  $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
  Write-Host $line
  try {{
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
  }} catch {{}}
}}

function Ensure-AppDir {{
  if (-not (Test-Path $AppDir)) {{
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
  }}
}}

function Test-WebView2Installed {{
  $paths = @(
    'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}',
    'HKLM:\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}',
    'HKCU:\\Software\\Microsoft\\EdgeUpdate\\Clients\\{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}'
  )
  foreach ($path in $paths) {{
    if (Test-Path $path) {{ return $true }}
  }}
  return $false
}}

function Install-WebView2 {{
  if (Test-WebView2Installed) {{
    Write-Log 'Microsoft Edge WebView2 Runtime already installed.'
    return
  }}
  Write-Log 'Downloading Microsoft Edge WebView2 Runtime...'
  $installer = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
  Invoke-WebRequest -Uri $Config.webview2_url -OutFile $installer -UseBasicParsing
  Write-Log 'Installing WebView2 (this may take a minute)...'
  $proc = Start-Process -FilePath $installer -ArgumentList '/silent', '/install' -Wait -PassThru
  if ($proc.ExitCode -ne 0 -and -not (Test-WebView2Installed)) {{
    throw "WebView2 setup failed with exit code $($proc.ExitCode)"
  }}
  Write-Log 'WebView2 installed.'
}}

function Find-PythonExe {{
  $candidates = @()
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) {{ $candidates += $cmd.Source }}
  $cmd = Get-Command python3 -ErrorAction SilentlyContinue
  if ($cmd) {{ $candidates += $cmd.Source }}
  $roots = @(
    "$env:LOCALAPPDATA\\Programs\\Python",
    "$env:ProgramFiles\\Python312",
    "$env:ProgramFiles\\Python311",
    "$env:ProgramFiles\\Python310"
  )
  foreach ($root in $roots) {{
    if (Test-Path $root) {{
      $candidates += Get-ChildItem -Path $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue | ForEach-Object {{ $_.FullName }}
    }}
  }}
  foreach ($path in $candidates | Select-Object -Unique) {{
    if ($path -and (Test-Path $path)) {{
      try {{
        $version = & $path -c "import sys; print(sys.version_info[:2])"
        if ($LASTEXITCODE -eq 0) {{ return $path }}
      }} catch {{}}
    }}
  }}
  return $null
}}

function Install-Python {{
  Write-Log 'Python not found. Installing Python 3.12 via winget...'
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) {{
    throw 'Python is not installed and winget is unavailable. Install Python 3.12+ from https://www.python.org/downloads/ (check Add to PATH), then run setup again.'
  }}
  & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) {{
    throw 'Could not install Python automatically. Install Python 3.12+ from https://www.python.org/downloads/ and run setup again.'
  }}
  Start-Sleep -Seconds 5
  $python = Find-PythonExe
  if (-not $python) {{
    throw 'Python was installed but is not on PATH yet. Restart this setup or log out and back in, then try again.'
  }}
  return $python
}}

function Save-Icon {{
  param([string]$IconPath)
  Write-Log 'Saving Case PM icon...'
  try {{
    Invoke-WebRequest -Uri $Config.icon_url -OutFile $IconPath -UseBasicParsing
    if ((Get-Item $IconPath).Length -gt 0) {{ return }}
  }} catch {{
    Write-Log "Icon download failed: $($_.Exception.Message)"
  }}
  throw 'Could not download the Case PM icon from the server.'
}}

function Ensure-RemoteClient {{
  param([string]$PythonExe)
  $venvPython = Join-Path $AppDir 'venv\\Scripts\\python.exe'
  if (-not (Test-Path $venvPython)) {{
    Write-Log 'Creating Python environment for Case PM Desktop...'
    & $PythonExe -m venv (Join-Path $AppDir 'venv')
  }}
  Write-Log 'Installing desktop app packages (pywebview)...'
  & $venvPython -m pip install --upgrade pip --quiet
  & $venvPython -m pip install -r $Config.requirements_url --quiet
  Write-Log 'Downloading Case PM desktop client...'
  Invoke-WebRequest -Uri $Config.client_url -OutFile (Join-Path $AppDir 'casepm_desktop_client.py') -UseBasicParsing
  Set-Content -Path (Join-Path $AppDir 'server.txt') -Value $Config.server_url -Encoding UTF8
}}

function Ensure-LocalLauncher {{
  param([string]$PythonExe)
  if (-not $Config.casepm_home -or -not (Test-Path $Config.casepm_home)) {{
    throw "Local Case PM folder not found: $($Config.casepm_home)"
  }}
  $runDesktop = Join-Path $Config.casepm_home 'RUN-DESKTOP.bat'
  if (-not (Test-Path $runDesktop)) {{
    throw "RUN-DESKTOP.bat was not found in $($Config.casepm_home)"
  }}
  Set-Content -Path (Join-Path $AppDir 'casepm_home.txt') -Value $Config.casepm_home -Encoding UTF8
  $launcherBat = Join-Path $AppDir 'Launch Case PM.bat'
  @"
@echo off
cd /d "$($Config.casepm_home)"
call RUN-DESKTOP.bat
"@ | Set-Content -Path $launcherBat -Encoding ASCII
  Write-Log "Local launcher points to $($Config.casepm_home)"
}}

function New-DesktopShortcut {{
  param([string]$TargetPath, [string]$Arguments, [string]$IconPath)
  $desktop = [Environment]::GetFolderPath('Desktop')
  $shortcutPath = Join-Path $desktop "$($Config.shortcut_name).lnk"
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $TargetPath
  if ($Arguments) {{ $shortcut.Arguments = $Arguments }}
  $shortcut.WorkingDirectory = $AppDir
  $shortcut.IconLocation = "$IconPath,0"
  $shortcut.Description = 'Case PM - Construction OS'
  $shortcut.Save()
  Write-Log "Desktop shortcut created: $shortcutPath"
}}

function Start-CasePM {{
  param([string]$TargetPath, [string]$Arguments)
  Start-Process -FilePath $TargetPath -ArgumentList $Arguments -WorkingDirectory $AppDir | Out-Null
}}

try {{
  Add-Type -AssemblyName System.Windows.Forms
  Write-Log 'Case PM Desktop setup starting...'
  Ensure-AppDir
  $iconPath = Join-Path $AppDir $Config.icon_file
  Save-Icon -IconPath $iconPath
  Install-WebView2

  if ($Config.local_mode) {{
    $launcherBat = Join-Path $AppDir 'Launch Case PM.bat'
    $python = Find-PythonExe
    if (-not $python) {{ $python = Install-Python }}
    Ensure-LocalLauncher -PythonExe $python
    New-DesktopShortcut -TargetPath $launcherBat -Arguments '' -IconPath $iconPath
    Write-Log 'Launching Case PM Desktop...'
    Start-CasePM -TargetPath $launcherBat -Arguments ''
  }} else {{
    $python = Find-PythonExe
    if (-not $python) {{ $python = Install-Python }}
    Ensure-RemoteClient -PythonExe $python
    $clientPath = Join-Path $AppDir 'casepm_desktop_client.py'
    $pythonw = Join-Path $AppDir 'venv\\Scripts\\pythonw.exe'
    $launchVbs = Join-Path $AppDir 'Launch Case PM.vbs'
    @"
Set sh = CreateObject("WScript.Shell")
sh.Run """" & "$pythonw" & """ """ & "$clientPath" & """", 0, False
"@ | Set-Content -Path $launchVbs -Encoding ASCII
    $wscript = Join-Path $env:WINDIR 'System32\\wscript.exe'
    New-DesktopShortcut -TargetPath $wscript -Arguments ('"' + $launchVbs + '"') -IconPath $iconPath
    Write-Log 'Launching Case PM Desktop...'
    Start-CasePM -TargetPath $wscript -Arguments ('"' + $launchVbs + '"')
  }}

  Write-Log 'Case PM Desktop setup finished successfully.'
  [System.Windows.Forms.MessageBox]::Show(
    "Case PM Desktop is installed.`n`nA shortcut with the hard-hat icon was added to your desktop.`n`nCase PM should open in its own window shortly.",
  'Case PM Desktop',
  [System.Windows.Forms.MessageBoxButtons]::OK,
  [System.Windows.Forms.MessageBoxIcon]::Information
  ) | Out-Null
}} catch {{
  Write-Log "ERROR: $($_.Exception.Message)"
  [System.Windows.Forms.MessageBox]::Show(
    "Case PM Desktop setup could not finish:`n`n$($_.Exception.Message)`n`nSee setup.log in Documents\\Case PM Desktop.",
    'Case PM Desktop',
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Error
  ) | Out-Null
  exit 1
}}
'''


def _vbs_escape(value: str) -> str:
    return value.replace('"', '""')


def build_desktop_app_installer(*, server_url: str, casepm_home: str = '') -> io.BytesIO:
    server_url = _normalize_server_url(server_url)
    local_mode = _is_local_server(server_url)
    if local_mode and not casepm_home:
        casepm_home = os.path.dirname(os.path.abspath(__file__))

    ps1 = build_desktop_setup_powershell(
        server_url=server_url,
        casepm_home=casepm_home,
        local_mode=local_mode,
    )
    ps1_b64 = base64.b64encode(ps1.encode('utf-8')).decode('ascii')

    vbs = f'''\' Case PM Desktop App Installer v{DESKTOP_APP_VERSION}
Option Explicit

Dim sh, fso, appDir, result, psPath, ps1B64, stream, xml, node, cmd

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = sh.SpecialFolders("MyDocuments") & "\\{INSTALL_FOLDER}"

result = MsgBox("Install Case PM as a desktop app?" & vbCrLf & vbCrLf & _
  "This will:" & vbCrLf & _
  "  - Install Microsoft Edge WebView2 (if needed)" & vbCrLf & _
  "  - Set up Case PM in Documents\\{INSTALL_FOLDER}" & vbCrLf & _
  "  - Add a desktop icon with the hard-hat logo" & vbCrLf & _
  "  - Open Case PM in its own window" & vbCrLf & vbCrLf & _
  "Click OK to continue.", vbOKCancel + vbInformation, "Case PM Desktop App")
If result <> 1 Then WScript.Quit 0

If Not fso.FolderExists(appDir) Then fso.CreateFolder appDir

psPath = appDir & "\\setup.ps1"
ps1B64 = "{ps1_b64}"

Set stream = CreateObject("ADODB.Stream")
stream.Type = 1
stream.Open
Set xml = CreateObject("Microsoft.XMLDOM")
Set node = xml.createElement("b64")
node.DataType = "bin.base64"
node.Text = ps1B64
stream.Write node.NodeTypedValue
stream.SaveToFile psPath, 2
stream.Close

If Not fso.FileExists(psPath) Then
  MsgBox "Could not write setup files.", vbCritical, "Case PM Desktop App"
  WScript.Quit 1
End If

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Sta -File """ & psPath & """"
sh.Run cmd, 1, True
'''

    buf = io.BytesIO(vbs.encode('utf-8'))
    buf.seek(0)
    return buf


def desktop_login_url(server_url: str) -> str:
    return f'{_normalize_server_url(server_url)}/login?desktop=1'
