@echo off
REM Keeps window open when double-clicked
if "%~1"=="" (
  cmd /k call "%~f0" keepopen
  exit /b
)

setlocal EnableDelayedExpansion
title SYLVORIN
cd /d "%~dp0"
set "HOME=%~dp0"
if "%HOME:~-1%"=="\" set "HOME=%HOME:~0,-1%"

:menu
cls
echo.
echo  ============================================
echo    SYLVORIN
echo    Folder: %HOME%
echo  ============================================
echo.
echo   1 = Download game files from GitHub (no Git needed)
echo   2 = Open Sylvorin in Unreal
echo   3 = Show path to open manually in Unreal
echo   4 = Check what is on this PC
echo   5 = Quit
echo.
set "PICK="
set /p PICK="Type 1-5 then press Enter: "

if "%PICK%"=="1" goto download
if "%PICK%"=="2" goto open_unreal
if "%PICK%"=="3" goto show_path
if "%PICK%"=="4" goto status
if "%PICK%"=="5" exit /b 0

echo.
echo  You typed: %PICK%  -- enter 1, 2, 3, 4, or 5
pause
goto menu

:download
echo.
echo  Downloading from GitHub... (1-3 minutes)
echo  Log: %HOME%\start-log.txt
echo.

>>"%HOME%\start-log.txt" echo [%date% %time%] Download started

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$home='%HOME%';" ^
  "$zip=Join-Path $env:TEMP 'sylvorin-download.zip';" ^
  "$ex=Join-Path $env:TEMP 'sylvorin-extract';" ^
  "$url='https://github.com/mikebretz/Case-PM/archive/refs/heads/cursor/sylvorin-c-drive-c4a4.zip';" ^
  "Write-Host 'Downloading...';" ^
  "Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing;" ^
  "if (Test-Path $ex) { Remove-Item $ex -Recurse -Force };" ^
  "Expand-Archive -Path $zip -DestinationPath $ex -Force;" ^
  "$folder = Get-ChildItem $ex -Directory | Select-Object -First 1;" ^
  "if (-not $folder) { throw 'Zip was empty' };" ^
  "Write-Host 'Copying to' $home;" ^
  "Copy-Item -Path (Join-Path $folder.FullName '*') -Destination $home -Recurse -Force;" ^
  "Write-Host 'SUCCESS'"

if errorlevel 1 (
  echo.
  echo  DOWNLOAD FAILED.
  echo  Open in browser and extract manually:
  echo  https://github.com/mikebretz/Case-PM/archive/refs/heads/cursor/sylvorin-c-drive-c4a4.zip
  >>"%HOME%\start-log.txt" echo [%date% %time%] Download FAILED
) else (
  echo.
  echo  SUCCESS - files are in %HOME%
  echo  Look for folder: %HOME%\Unreal
  >>"%HOME%\start-log.txt" echo [%date% %time%] Download OK
)

echo.
pause
goto menu

:open_unreal
set "PROJECT=%HOME%\Unreal\Sylvorin.uproject"
if not exist "%PROJECT%" (
  echo.
  echo  Project not found. Run option 1 first.
  echo  Expected: %PROJECT%
  pause
  goto menu
)

call :find_unreal
if not defined UE_EXE (
  echo.
  echo  Could not auto-find Unreal. Use option 3 instead.
  pause
  goto menu
)

echo.
echo  Launching Unreal with Sylvorin...
start "" "%UE_EXE%" "%PROJECT%"
echo  Wait 1-2 minutes if first time.
pause
goto menu

:show_path
set "PROJECT=%HOME%\Unreal\Sylvorin.uproject"
echo.
echo  ============================================
echo   OPEN THIS IN UNREAL (always works)
echo  ============================================
echo.
echo  1. Open Unreal Engine 5.8 from Epic Launcher
echo  2. File -^> Open Project
echo  3. Copy/paste this path:
echo.
echo  %PROJECT%
echo.
if exist "%PROJECT%" (echo  [OK] File exists.) else (echo  [!!] File missing - run option 1)
echo.
pause
goto menu

:status
echo.
echo Folder: %HOME%
if exist "%HOME%\Unreal\Sylvorin.uproject" (echo [OK] Sylvorin.uproject) else (echo [!!] Run option 1 to download files)
if exist "%HOME%\START.bat" (echo [OK] START.bat)

call :find_unreal
if defined UE_EXE (echo [OK] Unreal: %UE_EXE%) else (echo [!!] Unreal path not found - use option 3)

tasklist /FI "IMAGENAME eq UnrealEditor.exe" 2>nul | find /I "UnrealEditor.exe" >nul && echo [OK] Unreal is running now

tasklist /FI "IMAGENAME eq EpicGamesLauncher.exe" 2>nul | find /I "EpicGamesLauncher.exe" >nul && echo [OK] Epic Launcher is running now

echo.
pause
goto menu

:find_unreal
set "UE_EXE="
if exist "%HOME%\unreal.path" (
  set /p UE_EXE=<"%HOME%\unreal.path"
  if exist "!UE_EXE!" goto :eof
  set "UE_EXE="
)

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Process UnrealEditor -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path -First 1)" 2^>nul`) do set "UE_EXE=%%A"

if defined UE_EXE goto :eof

for %%V in (5.8 5.7 5.6 5.5 5.4) do (
  if exist "C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe" (
    set "UE_EXE=C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe"
    goto :eof
  )
)

for /d %%D in ("C:\Program Files\Epic Games\UE_*") do (
  if exist "%%D\Engine\Binaries\Win64\UnrealEditor.exe" (
    set "UE_EXE=%%D\Engine\Binaries\Win64\UnrealEditor.exe"
    goto :eof
  )
)
goto :eof
