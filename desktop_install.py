"""Set up Sylvorin at C:\\Sylvorin (run INSTALL-DESKTOP.bat from that folder)."""

from __future__ import annotations

import json
import os

DESKTOP_APP_VERSION = '1.0'
INSTALL_ROOT = 'C:\\Sylvorin'
SHORTCUT_NAME = 'Sylvorin'


def build_install_powershell(app_dir: str) -> str:
    app_dir = app_dir.replace('\\', '\\\\')
    config = {
        'install_root': INSTALL_ROOT,
        'app_dir': app_dir,
        'shortcut_name': SHORTCUT_NAME,
        'version': DESKTOP_APP_VERSION,
    }
    config_json = json.dumps(config)
    return f'''# Sylvorin setup at C:\\Sylvorin v{DESKTOP_APP_VERSION}
$ErrorActionPreference = 'Stop'
$Config = @{config_json} | ConvertFrom-Json
$InstallRoot = $Config.install_root
$AppDir = $Config.app_dir
$LogFile = Join-Path $InstallRoot 'install.log'

function Write-Log {{
  param([string]$Message)
  $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
  Write-Host $line
  try {{ Add-Content -Path $LogFile -Value $line -Encoding UTF8 }} catch {{}}
}}

function Find-PythonExe {{
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd -and (Test-Path $cmd.Source)) {{ return $cmd.Source }}
  return $null
}}

Write-Log 'Sylvorin setup starting...'
Write-Log "Location: $InstallRoot"

if ($AppDir -ne $InstallRoot) {{
  Write-Host ''
  Write-Host 'ERROR: Sylvorin must be at C:\\Sylvorin' -ForegroundColor Red
  Write-Host 'Clone the repo there:' -ForegroundColor Yellow
  Write-Host '  git clone https://github.com/mikebretz/Sylvorin C:\\Sylvorin' -ForegroundColor Yellow
  Write-Host 'Then run INSTALL-DESKTOP.bat from C:\\Sylvorin' -ForegroundColor Yellow
  throw 'Wrong folder — use C:\\Sylvorin'
}}

Set-Location $InstallRoot

if (-not (Test-Path 'node_modules')) {{
  Write-Log 'Installing Node packages (npm install)...'
  npm install
  if ($LASTEXITCODE -ne 0) {{ throw 'npm install failed' }}
}}

$py = Find-PythonExe
if ($py) {{
  Write-Log 'Setting up Python venv for desktop window...'
  if (-not (Test-Path 'venv\\Scripts\\python.exe')) {{
    & $py -m venv venv
  }}
  & (Join-Path $InstallRoot 'venv\\Scripts\\python.exe') -m pip install --upgrade pip --quiet
  & (Join-Path $InstallRoot 'venv\\Scripts\\python.exe') -m pip install -r requirements-desktop.txt
}} else {{
  Write-Log 'Python not found — install Python 3.10+ for the desktop window.'
}}

Write-Log 'Building game...'
npm run build
if ($LASTEXITCODE -ne 0) {{ throw 'npm run build failed' }}

$desktopBat = Join-Path $InstallRoot 'RUN-DESKTOP.bat'
$shortcutPath = Join-Path $env:USERPROFILE "Desktop\\$($Config.shortcut_name).lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $desktopBat
$shortcut.WorkingDirectory = $InstallRoot
$shortcut.Description = 'Sylvorin'
$shortcut.Save()

Write-Log "Desktop shortcut: $shortcutPath"
Write-Host ''
Write-Host '============================================' -ForegroundColor Green
Write-Host '  Sylvorin is ready at C:\\Sylvorin' -ForegroundColor Green
Write-Host '  Double-click desktop shortcut Sylvorin' -ForegroundColor Green
Write-Host '  Or run: C:\\Sylvorin\\RUN-DESKTOP.bat' -ForegroundColor Green
Write-Host '============================================' -ForegroundColor Green
'''


def write_install_script(target_path: str, app_dir: str) -> str:
    ps = build_install_powershell(app_dir)
    with open(target_path, 'w', encoding='utf-8') as fh:
        fh.write(ps)
    return target_path


if __name__ == '__main__':
    root = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(root, 'install-sylvorin.ps1')
    write_install_script(out, root)
    print(f'Written {out}')
