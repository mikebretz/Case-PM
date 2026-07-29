@echo off
title Open Sylvorin in UNREAL (not Visual Studio)
cd /d "%~dp0"

set "PROJECT=%~dp0Unreal\Sylvorin.uproject"

if not exist "%PROJECT%" (
  echo Project missing: %PROJECT%
  echo Download ZIP from GitHub first.
  pause
  exit /b 1
)

REM Find Unreal Editor — NOT Visual Studio
set "UE_EXE="

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Process UnrealEditor -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path -First 1)" 2^>nul`) do set "UE_EXE=%%A"

if not defined UE_EXE if exist "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe" set "UE_EXE=C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"

if not defined UE_EXE (
  for /d %%D in ("C:\Program Files\Epic Games\UE_*") do (
    if exist "%%D\Engine\Binaries\Win64\UnrealEditor.exe" set "UE_EXE=%%D\Engine\Binaries\Win64\UnrealEditor.exe"
  )
)

if not defined UE_EXE (
  echo.
  echo  Could not find UnrealEditor.exe
  echo  Open Epic Launcher -^> Library -^> Launch UE 5.8
  echo  Then File -^> Open -^> %PROJECT%
  pause
  exit /b 1
)

echo.
echo  Opening UNREAL ENGINE (not Visual Studio)
echo  %UE_EXE%
echo  %PROJECT%
echo.

start "" "%UE_EXE%" "%PROJECT%"

echo  Unreal is starting. Ignore Visual Studio if it pops up.
echo  Close Visual Studio — you do not need it right now.
pause
