@echo off
setlocal EnableDelayedExpansion
REM Shared: find Unreal Editor (any UE5.x including 5.8+) and Epic Launcher
set "UE_EDITOR="
set "EPIC_LAUNCHER="

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Sylvorin\scripts\find-unreal.ps1" unreal 2^>nul`) do set "UE_EDITOR=%%I"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Sylvorin\scripts\find-unreal.ps1" epic 2^>nul`) do set "EPIC_LAUNCHER=%%I"

REM Fallback: scan UE_* folders if PowerShell failed
if not defined UE_EDITOR (
  for /d %%D in ("C:\Program Files\Epic Games\UE_*") do (
    if exist "%%D\Engine\Binaries\Win64\UnrealEditor.exe" (
      set "UE_EDITOR=%%D\Engine\Binaries\Win64\UnrealEditor.exe"
    )
  )
)

exit /b 0
