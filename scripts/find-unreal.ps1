# Finds UnrealEditor.exe and Epic Games Launcher on this PC
$ErrorActionPreference = 'SilentlyContinue'

function Find-UnrealEditor {
    $roots = @(
        Join-Path $env:ProgramFiles 'Epic Games'
        Join-Path ${env:ProgramFiles(x86)} 'Epic Games'
        'D:\Epic Games'
        'E:\Epic Games'
        'C:\Epic Games'
    )
    $found = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        Get-ChildItem $root -Directory -Filter 'UE_*' | ForEach-Object {
            $exe = Join-Path $_.FullName 'Engine\Binaries\Win64\UnrealEditor.exe'
            if (Test-Path $exe) {
                $found += [PSCustomObject]@{
                    Version = $_.Name
                    Path    = $exe
                }
            }
        }
    }
    if ($found.Count -eq 0) { return $null }
    return ($found | Sort-Object Version -Descending | Select-Object -First 1).Path
}

function Find-EpicLauncher {
    $candidates = @(
        Join-Path ${env:ProgramFiles(x86)} 'Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe'
        Join-Path ${env:ProgramFiles(x86)} 'Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe'
        Join-Path $env:ProgramFiles 'Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe'
        Join-Path $env:LOCALAPPDATA 'EpicGamesLauncher\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe'
        Join-Path $env:LOCALAPPDATA 'EpicGamesLauncher\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe'
        Join-Path ${env:ProgramFiles(x86)} 'Epic Games\Launcher\EpicGamesLauncher.exe'
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$mode = $args[0]
if ($mode -eq 'epic') {
    $r = Find-EpicLauncher
    if ($r) { Write-Output $r }
} else {
    $r = Find-UnrealEditor
    if ($r) { Write-Output $r }
}
