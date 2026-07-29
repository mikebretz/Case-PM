# Finds UnrealEditor.exe and Epic Games Launcher on this PC
$ErrorActionPreference = 'SilentlyContinue'

function Read-ConfigPath {
    param([string]$Key, [string]$ConfigPath)
    if (-not (Test-Path $ConfigPath)) { return $null }
    foreach ($line in Get-Content $ConfigPath) {
        if ($line -match '^\s*#') { continue }
        if ($line -match "^${Key}\s*=\s*(.+)$") {
            $p = $Matches[1].Trim().Trim('"')
            if (Test-Path $p) { return $p }
        }
    }
    return $null
}

function Find-UnrealEditor {
    param([string]$ConfigPath)

    $fromConfig = Read-ConfigPath 'UNREAL_EDITOR' $ConfigPath
    if ($fromConfig) { return $fromConfig }

    # Running Unreal Editor (user said UE 5.8 is open right now)
    $running = Get-Process -Name 'UnrealEditor' -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Path -Unique
    foreach ($p in $running) {
        if ($p -and (Test-Path $p)) { return $p }
    }

    # Registry (Epic installer)
    $regPaths = @(
        'HKLM:\SOFTWARE\EpicGames\Unreal Engine',
        'HKLM:\SOFTWARE\WOW6432Node\EpicGames\Unreal Engine'
    )
    foreach ($reg in $regPaths) {
        if (Test-Path $reg) {
            Get-ChildItem $reg | ForEach-Object {
                $installed = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).InstalledDirectory
                if ($installed) {
                    $exe = Join-Path $installed 'Engine\Binaries\Win64\UnrealEditor.exe'
                    if (Test-Path $exe) { return $exe }
                }
            }
        }
    }

    $roots = @(
        (Join-Path $env:ProgramFiles 'Epic Games')
    )
    if ($env:ProgramFiles(x86)) {
        $roots += Join-Path ${env:ProgramFiles(x86)} 'Epic Games'
    }
    $roots += @('C:\Epic Games', 'D:\Epic Games', 'E:\Epic Games', 'F:\Epic Games')
    $found = @()
    foreach ($root in $roots) {
        if (-not $root -or -not (Test-Path $root)) { continue }
        Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like 'UE_*'
        } | ForEach-Object {
            $exe = Join-Path $_.FullName 'Engine\Binaries\Win64\UnrealEditor.exe'
            if (Test-Path $exe) {
                $found += [PSCustomObject]@{
                    Version = $_.Name
                    Path    = $exe
                }
            }
        }
    }
    if ($found.Count -gt 0) {
        return ($found | Sort-Object Version -Descending | Select-Object -First 1).Path
    }

    # Last resort: search Program Files for UnrealEditor.exe (slow but thorough)
    $searchRoots = @(
        Join-Path $env:ProgramFiles 'Epic Games'
        'C:\Epic Games'
        'D:\Epic Games'
    )
    foreach ($root in $searchRoots) {
        if (-not (Test-Path $root)) { continue }
        $hit = Get-ChildItem $root -Recurse -Filter 'UnrealEditor.exe' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match 'Engine\\Binaries\\Win64\\' } |
            Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }

    return $null
}

function Find-EpicLauncher {
    param([string]$ConfigPath)

    $fromConfig = Read-ConfigPath 'EPIC_LAUNCHER' $ConfigPath
    if ($fromConfig) { return $fromConfig }

    $running = Get-Process -Name 'EpicGamesLauncher' -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty Path -Unique
    foreach ($p in $running) {
        if ($p -and (Test-Path $p)) { return $p }
    }

    $candidates = @(
        Join-Path ${env:ProgramFiles(x86)} 'Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe'
        Join-Path ${env:ProgramFiles(x86)} 'Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe'
        Join-Path $env:ProgramFiles 'Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe'
        Join-Path $env:LOCALAPPDATA 'EpicGamesLauncher\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe'
        Join-Path $env:LOCALAPPDATA 'EpicGamesLauncher\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe'
        Join-Path ${env:ProgramFiles(x86)} 'Epic Games\Launcher\EpicGamesLauncher.exe'
    )
    foreach ($p in $candidates) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}

$configPath = 'C:\Sylvorin\unreal.paths.cfg'
$mode = $args[0]

if ($mode -eq 'epic') {
    $r = Find-EpicLauncher $configPath
    if ($r) { Write-Output $r }
} elseif ($mode -eq 'save') {
    $ue = Find-UnrealEditor $configPath
    $epic = Find-EpicLauncher $configPath
    $lines = @(
        '# Sylvorin auto-detected paths — edit if needed'
        "UNREAL_EDITOR=$ue"
        "EPIC_LAUNCHER=$epic"
    )
    Set-Content -Path $configPath -Value $lines -Encoding UTF8
    if ($ue) { Write-Output "UNREAL=$ue" }
    if ($epic) { Write-Output "EPIC=$epic" }
} else {
    $r = Find-UnrealEditor $configPath
    if ($r) { Write-Output $r }
}
