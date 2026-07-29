@echo off
setlocal EnableDelayedExpansion
title SYLVORIN — START HERE
color 0A

REM ============================================================
REM  DOUBLE-CLICK THIS FILE ONLY:  START.bat
REM  Put this folder anywhere (C:\Sylvorin is fine).
REM ============================================================

set "HOME=%~dp0"
set "HOME=%HOME:~0,-1%"
cd /d "%HOME%"

echo.
echo  ============================================
echo    SYLVORIN
echo    Folder: %HOME%
echo  ============================================
echo.
echo   1  Open Sylvorin in Unreal (PLAY / EDIT)
echo   2  Pull latest files from GitHub
echo   3  Find Unreal on this PC and save path
echo   4  Show what is installed
echo   5  Quit
echo.
set /p PICK="Type 1-5 and press Enter: "

if "%PICK%"=="1" goto open_unreal
if "%PICK%"=="2" goto pull_github
if "%PICK%"=="3" goto find_unreal
if "%PICK%"=="4" goto show_status
if "%PICK%"=="5" exit /b 0
echo Bad choice.
pause
exit /b 1

REM ---------- OPEN UNREAL ----------
:open_unreal
set "PROJECT=%HOME%\Unreal\Sylvorin.uproject"
if not exist "%PROJECT%" (
  echo.
  echo  MISSING: Unreal\Sylvorin.uproject
  echo  Run option 2 first (Pull from GitHub).
  pause
  exit /b 1
)

call :locate_unreal
if not defined UE_EXE (
  echo.
  echo  ============================================
  echo   COULD NOT FIND UNREAL AUTOMATICALLY
  echo  ============================================
  echo.
  echo  DO THIS INSTEAD (works every time):
  echo.
  echo  1. Open Unreal Engine 5.8 (you already have it)
  echo  2. File -^> Open Project
  echo  3. Browse to:
  echo.
  echo     %PROJECT%
  echo.
  echo  4. Click Open. Done.
  echo.
  echo  To fix auto-launch: run option 3 while Unreal is open.
  pause
  exit /b 0
)

echo.
echo  Opening Sylvorin...
echo  Unreal: %UE_EXE%
echo  Project: %PROJECT%
echo.
start "" "%UE_EXE%" "%PROJECT%"
echo  If Unreal does not appear, wait 2 minutes (first compile).
pause
exit /b 0

REM ---------- PULL GITHUB ----------
:pull_github
where git >nul 2>&1
if errorlevel 1 (
  echo Git not installed. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)

set "REPO=https://github.com/mikebretz/Case-PM.git"
set "BRANCH=cursor/sylvorin-c-drive-c4a4"
set "TEMP=%TEMP%\sylvorin-pull"

echo Pulling Sylvorin files from GitHub...
if exist "%TEMP%" rd /s /q "%TEMP%"
git clone -b %BRANCH% %REPO% "%TEMP%"
if errorlevel 1 (
  echo Git pull failed. Check internet and Git install.
  pause
  exit /b 1
)

REM Copy repo contents into current folder (not Case-PM app junk - branch root IS Sylvorin)
echo Copying into %HOME% ...
xcopy /E /Y /Q "%TEMP%\*" "%HOME%\"
rd /s /q "%TEMP%"
echo.
echo  Done. Files updated.
echo  Next: press 3 then 1, or open project manually in Unreal.
pause
exit /b 0

REM ---------- FIND UNREAL ----------
:find_unreal
echo Searching for Unreal Engine...
call :locate_unreal
if defined UE_EXE (
  echo FOUND: %UE_EXE%
  >"%HOME%\unreal.path" echo %UE_EXE%
  echo Saved to unreal.path in this folder.
) else (
  echo Not found by scan.
  echo.
  echo Paste full path to UnrealEditor.exe
  echo Example: C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe
  echo.
  set /p UE_EXE="Path: "
  if exist "!UE_EXE!" (
    >"%HOME%\unreal.path" echo !UE_EXE!
    echo Saved.
  ) else (
    echo That file does not exist.
  )
)
pause
exit /b 0

REM ---------- STATUS ----------
:show_status
echo.
echo Folder: %HOME%
if exist "%HOME%\Unreal\Sylvorin.uproject" (echo [OK] Sylvorin.uproject) else (echo [!!] No Sylvorin.uproject - run option 2)
if exist "%HOME%\START.bat" (echo [OK] START.bat) else (echo [!!] START.bat)

call :locate_unreal
if defined UE_EXE (echo [OK] Unreal: %UE_EXE%) else (echo [!!] Unreal not found - run option 3)

tasklist /FI "IMAGENAME eq UnrealEditor.exe" 2>nul | find /I "UnrealEditor.exe" >nul && echo [OK] Unreal is RUNNING right now || echo [--] Unreal not running

tasklist /FI "IMAGENAME eq EpicGamesLauncher.exe" 2>nul | find /I "EpicGamesLauncher.exe" >nul && echo [OK] Epic Launcher running || echo [--] Epic Launcher not running

where git >nul 2>&1 && echo [OK] Git || echo [!!] Git
echo.
pause
exit /b 0

REM ---------- FIND UNREAL ENGINE EXE ----------
:locate_unreal
set "UE_EXE="
if exist "%HOME%\unreal.path" (
  set /p UE_EXE=<"%HOME%\unreal.path"
  if exist "!UE_EXE!" exit /b 0
  set "UE_EXE="
)

REM Running Unreal right now
for /f "usebackq tokens=2 delims==" %%A in (`wmic process where "name='UnrealEditor.exe'" get ExecutablePath /value 2^>nul ^| findstr /i "UnrealEditor"`) do (
  set "UE_EXE=%%A"
  goto :found_ue
)

REM Standard Epic folders UE_5.8, UE_5.7, etc.
for %%V in (5.8 5.7 5.6 5.5 5.4 5.3) do (
  if exist "C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe" (
    set "UE_EXE=C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe"
    goto :found_ue
  )
)

REM Any UE_* folder
for /d %%D in ("C:\Program Files\Epic Games\UE_*") do (
  if exist "%%D\Engine\Binaries\Win64\UnrealEditor.exe" (
    set "UE_EXE=%%D\Engine\Binaries\Win64\UnrealEditor.exe"
    goto :found_ue
  )
)

REM D drive common
for /d %%D in ("D:\Epic Games\UE_*" "D:\Program Files\Epic Games\UE_*") do (
  if exist "%%D\Engine\Binaries\Win64\UnrealEditor.exe" (
    set "UE_EXE=%%D\Engine\Binaries\Win64\UnrealEditor.exe"
    goto :found_ue
  )
)

:found_ue
exit /b 0
