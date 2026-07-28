"""Install Sylvorin to C:\\Sylvorin and create a desktop shortcut."""

from __future__ import annotations

import json
import os

DESKTOP_APP_VERSION = '1.0'
INSTALL_ROOT = 'C:\\Sylvorin'
SHORTCUT_NAME = 'Sylvorin'


def build_install_powershell(source_dir: str) -> str:
    source_dir = source_dir.replace('\\', '\\\\')
    config = {
        'install_root': INSTALL_ROOT,
        'source_dir': source_dir,
        'shortcut_name': SHORTCUT_NAME,
        'version': DESKTOP_APP_VERSION,
    }
    config_json = json.dumps(config)
    return f'''# Sylvorin Desktop install v{DESKTOP_APP_VERSION}
$ErrorActionPreference = 'Stop'
$Config = @{config_json} | ConvertFrom-Json
$InstallRoot = $Config.install_root
$SourceDir = $Config.source_dir
$LogFile = Join-Path $InstallRoot 'install.log'

function Write-Log {{
  param([string]$Message)
  $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
  Write-Host $line
  try {{ Add-Content -Path $LogFile -Value $line -Encoding UTF8 }} catch {{}}
}}

function Find-PythonExe {{
  $candidates = @()
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) {{ $candidates += $cmd.Source }}
  foreach ($path in $candidates | Select-Object -Unique) {{
    if ($path -and (Test-Path $path)) {{ return $path }}
  }}
  return $null
}}

Write-Log 'Sylvorin install starting...'
Write-Log "Target: $InstallRoot"

if (-not (Test-Path $InstallRoot)) {{
  New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
}}

Write-Log 'Copying Sylvorin files to C:\\Sylvorin...'
$exclude = @('node_modules', 'dist', '.git', 'logs', 'venv')
Get-ChildItem -Path $SourceDir -Force | Where-Object {{
  $exclude -notcontains $_.Name
}} | ForEach-Object {{
  $dest = Join-Path $InstallRoot $_.Name
  if ($_.PSIsContainer) {{
    if (Test-Path $dest) {{ Remove-Item $dest -Recurse -Force }}
    Copy-Item $_.FullName $dest -Recurse -Force
  }} else {{
    Copy-Item $_.FullName $dest -Force
  }}
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
  Write-Log 'Python not found — desktop window will use browser fallback.'
}}

Write-Log 'Building game...'
npm run build
if ($LASTEXITCODE -ne 0) {{ throw 'npm run build failed' }}

$desktopBat = Join-Path $InstallRoot 'RUN-SYLVORIN-DESKTOP.bat'
$shortcutPath = Join-Path $env:USERPROFILE "Desktop\\$($Config.shortcut_name).lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $desktopBat
$shortcut.WorkingDirectory = $InstallRoot
$shortcut.Description = 'Sylvorin — MMORPG adventure'
$shortcut.Save()

Write-Log "Desktop shortcut created: $shortcutPath"
Write-Log 'Install complete. Sylvorin is installed to C:\\Sylvorin'
Write-Host ''
Write-Host '============================================' -ForegroundColor Green
Write-Host '  Sylvorin installed to C:\\Sylvorin' -ForegroundColor Green
Write-Host '  Desktop shortcut: Sylvorin' -ForegroundColor Green
Write-Host '  Or run: C:\\Sylvorin\\RUN-SYLVORIN-DESKTOP.bat' -ForegroundColor Green
Write-Host '============================================' -ForegroundColor Green
'''


def write_install_script(target_path: str, source_dir: str) -> str:
    ps = build_install_powershell(source_dir)
    with open(target_path, 'w', encoding='utf-8') as fh:
        fh.write(ps)
    return target_path


if __name__ == '__main__':
    root = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(root, 'install-sylvorin.ps1')
    write_install_script(out, root)
    print(f'Written {out}')
