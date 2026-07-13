# Case PM Desktop Connector — creates a pinned desktop shortcut
param(
    [string]$ServerUrl = "{{SERVER_URL}}"
)

$ErrorActionPreference = 'Stop'

function Normalize-Url([string]$Url) {
    $u = $Url.Trim().TrimEnd('/')
    if (-not $u) { return 'http://127.0.0.1:5000' }
    if ($u -notmatch '^https?://') { $u = "http://$u" }
    return $u.TrimEnd('/')
}

$ServerUrl = Normalize-Url $ServerUrl
$LoginUrl = "$ServerUrl/login?connector=1"
$AppDir = Join-Path $env:LOCALAPPDATA 'CasePM'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

$iconSource = Join-Path $ScriptDir 'casepm-icon.ico'
$iconTarget = Join-Path $AppDir 'casepm-icon.ico'
if (Test-Path $iconSource) {
    Copy-Item -Path $iconSource -Destination $iconTarget -Force
}

$config = @{
    server_url    = $ServerUrl
    login_url     = $LoginUrl
    version       = '{{CONNECTOR_VERSION}}'
    installed_at  = (Get-Date).ToString('o')
}
$config | ConvertTo-Json | Set-Content (Join-Path $AppDir 'connector.json') -Encoding UTF8

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Case PM.lnk'

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $LoginUrl
$shortcut.Description = 'Case PM — secure connection to your company server'
if (Test-Path $iconTarget) {
    $shortcut.IconLocation = "$iconTarget,0"
}
$shortcut.Save()

Write-Host "Case PM desktop shortcut created at: $shortcutPath"
Write-Host "Server: $ServerUrl"
