"""Build the Case PM Desktop App installer for Windows (WebView2 + native window + desktop icon)."""

from __future__ import annotations

import io
import json
import os
from urllib.parse import urlparse

DESKTOP_APP_VERSION = '1.2'
INSTALL_FOLDER = 'Case PM Desktop'
ICON_FILE = 'Case PM.ico'
SHORTCUT_NAME = 'Case PM'
WEBVIEW2_BOOTSTRAPPER_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'

_REPAIR_PS1_BODY = r"""$cfg = Get-Content (Join-Path $PSScriptRoot 'shortcut.json') -Raw | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
$desktop = $shell.SpecialFolders.Item('Desktop')
$shortcutPath = Join-Path $desktop ($cfg.ShortcutName + '.lnk')
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $cfg.TargetPath
if ($cfg.Arguments) { $shortcut.Arguments = $cfg.Arguments }
$shortcut.WorkingDirectory = $cfg.AppDir
$shortcut.IconLocation = $cfg.IconPath + ',0'
$shortcut.Description = 'Case PM - Construction OS'
$shortcut.Save()
Write-Host 'Desktop shortcut created:' $shortcutPath
Read-Host 'Press Enter to close'
"""

_DOWNLOAD_FILE_VBS = '''
Sub DownloadFile(url, path)
  On Error Resume Next
  Dim xhr, stream
  Set xhr = CreateObject("MSXML2.XMLHTTP")
  xhr.Open "GET", url, False
  xhr.Send
  If xhr.Status = 200 Then
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 1
    stream.Open
    stream.Write xhr.responseBody
    stream.SaveToFile path, 2
    stream.Close
    DownloadFile = True
  Else
    DownloadFile = False
  End If
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


def _is_local_server(server_url: str) -> bool:
    host = (urlparse(server_url).hostname or '').lower()
    return host in ('127.0.0.1', 'localhost', '::1')


def _vbs_escape(value: str) -> str:
    return value.replace('"', '""')


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
    repair_ps1_ps = _REPAIR_PS1_BODY.replace('"', '`"').replace('\n', '`n')
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

function Get-DesktopFolders {{
  $folders = @()
  $shell = New-Object -ComObject WScript.Shell
  try {{
    $special = $shell.SpecialFolders.Item('Desktop')
    if ($special) {{ $folders += $special }}
  }} catch {{}}
  $envDesktop = [Environment]::GetFolderPath('Desktop')
  if ($envDesktop) {{ $folders += $envDesktop }}
  $userDesktop = Join-Path $env:USERPROFILE 'Desktop'
  if (Test-Path $userDesktop) {{ $folders += $userDesktop }}
  foreach ($name in @('OneDrive', 'OneDriveCommercial')) {{
    $root = [Environment]::GetEnvironmentVariable($name)
    if ($root) {{
      $candidate = Join-Path $root 'Desktop'
      if (Test-Path $candidate) {{ $folders += $candidate }}
    }}
  }}
  return $folders | Select-Object -Unique
}}

function New-DesktopShortcut {{
  param([string]$TargetPath, [string]$Arguments, [string]$IconPath)
  $created = @()
  foreach ($desktop in Get-DesktopFolders) {{
    try {{
      $shortcutPath = Join-Path $desktop "$($Config.shortcut_name).lnk"
      $shell = New-Object -ComObject WScript.Shell
      $shortcut = $shell.CreateShortcut($shortcutPath)
      $shortcut.TargetPath = $TargetPath
      if ($Arguments) {{ $shortcut.Arguments = $Arguments }}
      $shortcut.WorkingDirectory = $AppDir
      $shortcut.IconLocation = "$IconPath,0"
      $shortcut.Description = 'Case PM - Construction OS'
      $shortcut.Save()
      if (Test-Path $shortcutPath) {{
        $created += $shortcutPath
        Write-Log "Desktop shortcut created: $shortcutPath"
      }}
    }} catch {{
      Write-Log "Could not create shortcut on $desktop : $($_.Exception.Message)"
    }}
  }}
  if ($created.Count -eq 0) {{
    throw 'Could not create a desktop shortcut.'
  }}
}}

function Write-RepairShortcutScript {{
  param([string]$TargetPath, [string]$Arguments, [string]$IconPath)
  $cfg = @{{
    TargetPath = $TargetPath
    Arguments = $(if ($Arguments) {{ $Arguments }} else {{ '' }})
    IconPath = $IconPath
    ShortcutName = $Config.shortcut_name
    AppDir = $AppDir
  }} | ConvertTo-Json
  Set-Content -Path (Join-Path $AppDir 'shortcut.json') -Value $cfg -Encoding UTF8
  $repairPs1 = Join-Path $AppDir 'Create Desktop Shortcut.ps1'
  Set-Content -Path $repairPs1 -Value "{repair_ps1_ps}" -Encoding UTF8
  $repairBat = Join-Path $AppDir 'Create Desktop Shortcut.bat'
  Set-Content -Path $repairBat -Value "@echo off`r`ncd /d `"%~dp0`"`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"Create Desktop Shortcut.ps1`"`r`n" -Encoding ASCII
  Write-Log "Wrote repair shortcut scripts in $AppDir"
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
    Write-Log "WebView2 setup returned exit code $($proc.ExitCode) — continuing anyway."
  }} else {{
    Write-Log 'WebView2 installed.'
  }}
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
        & $path -c "import sys" 2>$null
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
    throw 'Python is not installed. Install Python 3.12+ from https://www.python.org/downloads/ and run setup again.'
  }}
  & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  Start-Sleep -Seconds 8
  $python = Find-PythonExe
  if (-not $python) {{
    throw 'Python was installed but is not on PATH yet. Restart your PC, then run setup again.'
  }}
  return $python
}}

function Save-Icon {{
  param([string]$IconPath)
  Write-Log 'Saving Case PM icon...'
  Invoke-WebRequest -Uri $Config.icon_url -OutFile $IconPath -UseBasicParsing
  if (-not (Test-Path $IconPath) -or (Get-Item $IconPath).Length -eq 0) {{
    throw 'Could not download the Case PM icon from the server.'
  }}
}}

function Ensure-RemoteClient {{
  param([string]$PythonExe)
  $venvPython = Join-Path $AppDir 'venv\\Scripts\\python.exe'
  if (-not (Test-Path $venvPython)) {{
    Write-Log 'Creating Python environment for Case PM Desktop...'
    & $PythonExe -m venv (Join-Path $AppDir 'venv')
  }}
  Write-Log 'Installing desktop app packages (pywebview)...'
  & $venvPython -m pip install --upgrade pip
  & $venvPython -m pip install -r $Config.requirements_url
  Write-Log 'Downloading Case PM desktop client...'
  Invoke-WebRequest -Uri $Config.client_url -OutFile (Join-Path $AppDir 'casepm_desktop_client.py') -UseBasicParsing
  Set-Content -Path (Join-Path $AppDir 'server.txt') -Value $Config.server_url -Encoding UTF8
}}

function Ensure-LocalLauncher {{
  if (-not $Config.casepm_home -or -not (Test-Path $Config.casepm_home)) {{
    throw "Local Case PM folder not found: $($Config.casepm_home)"
  }}
  $runDesktop = Join-Path $Config.casepm_home 'RUN-DESKTOP.bat'
  if (-not (Test-Path $runDesktop)) {{
    throw "RUN-DESKTOP.bat was not found in $($Config.casepm_home)"
  }}
  Set-Content -Path (Join-Path $AppDir 'casepm_home.txt') -Value $Config.casepm_home -Encoding UTF8
  $launcherBat = Join-Path $AppDir 'Launch Case PM.bat'
  $bat = "@echo off`r`ncd /d `"$($Config.casepm_home)`"`r`ncall RUN-DESKTOP.bat`r`n"
  Set-Content -Path $launcherBat -Value $bat -Encoding ASCII
  Write-Log "Local launcher points to $($Config.casepm_home)"
  return $launcherBat
}}

function Start-CasePM {{
  param([string]$TargetPath, [string]$Arguments)
  Start-Process -FilePath $TargetPath -ArgumentList $Arguments -WorkingDirectory $AppDir | Out-Null
}}

$exitCode = 0
try {{
  Write-Log 'Case PM Desktop setup starting...'
  Ensure-AppDir
  $iconPath = Join-Path $AppDir $Config.icon_file
  Save-Icon -IconPath $iconPath

  if ($Config.local_mode) {{
    $launcherBat = Ensure-LocalLauncher
    Write-RepairShortcutScript -TargetPath $launcherBat -Arguments '' -IconPath $iconPath
    New-DesktopShortcut -TargetPath $launcherBat -Arguments '' -IconPath $iconPath
    Install-WebView2
    $python = Find-PythonExe
    if (-not $python) {{ $null = Install-Python }}
    Write-Log 'Launching Case PM Desktop...'
    Start-CasePM -TargetPath $launcherBat -Arguments ''
  }} else {{
    $clientPath = Join-Path $AppDir 'casepm_desktop_client.py'
    $pythonw = Join-Path $AppDir 'venv\\Scripts\\pythonw.exe'
    $launchVbs = Join-Path $AppDir 'Launch Case PM.vbs'
    $bootstrapBat = Join-Path $AppDir 'Launch Case PM.bat'
    Set-Content -Path $bootstrapBat -Value "@echo off`r`ncd /d `"%~dp0`"`r`nif exist venv\\Scripts\\pythonw.exe wscript.exe //nologo `"Launch Case PM.vbs`"`r`n" -Encoding ASCII
    Write-RepairShortcutScript -TargetPath $bootstrapBat -Arguments '' -IconPath $iconPath
    New-DesktopShortcut -TargetPath $bootstrapBat -Arguments '' -IconPath $iconPath
    Install-WebView2
    $python = Find-PythonExe
    if (-not $python) {{ $python = Install-Python }}
    Ensure-RemoteClient -PythonExe $python
    $vbs = "Set sh = CreateObject(""WScript.Shell"")`r`n"
    $vbs += "sh.Run Chr(34) & ""$pythonw"" & Chr(34) & "" "" & Chr(34) & ""$clientPath"" & Chr(34), 0, False`r`n"
    Set-Content -Path $launchVbs -Value $vbs -Encoding ASCII
    Write-Log 'Launching Case PM Desktop...'
    Start-CasePM -TargetPath $bootstrapBat -Arguments ''
  }}

  Write-Log 'Case PM Desktop setup finished successfully.'
  Write-Host ''
  Write-Host 'SUCCESS: Case PM desktop icon should be on your desktop now.'
  Write-Host 'If not, double-click Create Desktop Shortcut.bat in Documents\\Case PM Desktop'
}} catch {{
  $exitCode = 1
  Write-Log "ERROR: $($_.Exception.Message)"
  Write-Host ''
  Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host 'See setup.log in Documents\\Case PM Desktop'
}} finally {{
  Write-Host ''
  Read-Host 'Press Enter to close this setup window'
}}
exit $exitCode
'''


def build_desktop_app_installer(*, server_url: str, casepm_home: str = '') -> io.BytesIO:
    server_url = _normalize_server_url(server_url)
    setup_url = f'{server_url}/download/casepm-desktop-setup.ps1'

    vbs = f'''\' Case PM Desktop App Installer v{DESKTOP_APP_VERSION}
{_DOWNLOAD_FILE_VBS}

Sub RunSetup()
  On Error Resume Next
  Dim sh, fso, appDir, result, psPath, setupUrl, ok, cmd

  Set sh = CreateObject("WScript.Shell")
  Set fso = CreateObject("Scripting.FileSystemObject")
  appDir = sh.SpecialFolders("MyDocuments") & "\\{INSTALL_FOLDER}"
  setupUrl = "{_vbs_escape(setup_url)}"

  result = MsgBox("Install Case PM as a desktop app?" & vbCrLf & vbCrLf & _
    "This will:" & vbCrLf & _
    "  - Install Microsoft Edge WebView2 (if needed)" & vbCrLf & _
    "  - Set up Case PM in Documents\\{INSTALL_FOLDER}" & vbCrLf & _
    "  - Add a desktop icon with the hard-hat logo" & vbCrLf & _
    "  - Open Case PM in its own window" & vbCrLf & vbCrLf & _
    "Keep the black setup window open until it says SUCCESS." & vbCrLf & vbCrLf & _
    "Click OK to continue.", vbOKCancel + vbInformation, "Case PM Desktop App")
  If result <> 1 Then Exit Sub

  If Not fso.FolderExists(appDir) Then fso.CreateFolder appDir
  psPath = appDir & "\\setup.ps1"

  ok = DownloadFile(setupUrl, psPath)
  If Not ok Or Not fso.FileExists(psPath) Then
    MsgBox "Could not download the setup script from:" & vbCrLf & setupUrl & vbCrLf & vbCrLf & _
      "Make sure Case PM is running and try again.", vbCritical, "Case PM Desktop App"
    Exit Sub
  End If

  cmd = "cmd.exe /c powershell.exe -NoProfile -ExecutionPolicy Bypass -Sta -File """ & psPath & """"
  sh.Run cmd, 1, True
End Sub

RunSetup
'''

    buf = io.BytesIO(vbs.encode('utf-8'))
    buf.seek(0)
    return buf


def desktop_setup_powershell_bytes(*, server_url: str, casepm_home: str = '') -> bytes:
    server_url = _normalize_server_url(server_url)
    local_mode = _is_local_server(server_url)
    if local_mode and not casepm_home:
        casepm_home = os.path.dirname(os.path.abspath(__file__))
    text = build_desktop_setup_powershell(
        server_url=server_url,
        casepm_home=casepm_home,
        local_mode=local_mode,
    )
    return text.encode('utf-8')


def desktop_login_url(server_url: str) -> str:
    return f'{_normalize_server_url(server_url)}/login?desktop=1'
