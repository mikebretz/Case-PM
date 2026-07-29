@echo off
setlocal EnableDelayedExpansion
title Sylvorin Setup
color 0A

REM ============================================================
REM  SYLVORIN — ONE-CLICK SETUP
REM  Run this file: C:\Sylvorin\SETUP-SYLVORIN.bat
REM  (Double-click it. Do NOT open .md files in Word — they are notes.)
REM ============================================================

cd /d "C:\Sylvorin"
if not exist "C:\Sylvorin\SETUP-SYLVORIN.bat" (
  echo ERROR: This script must live at C:\Sylvorin\SETUP-SYLVORIN.bat
  pause
  exit /b 1
)

echo.
echo  ============================================
echo    SYLVORIN SETUP
echo    Location: C:\Sylvorin
echo  ============================================
echo.

REM --- Menu ---
echo  What do you want to do?
echo.
echo    1 = Install everything I can (Git, Node, Python, Epic Launcher)
echo    2 = Open Sylvorin in UNREAL ENGINE 5
echo    3 = Play the simple web prototype (browser game)
echo    4 = Check what is installed (diagnostics)
echo    5 = Exit
echo.
set /p CHOICE="Type 1, 2, 3, 4, or 5 and press Enter: "

if "%CHOICE%"=="1" goto :install_all
if "%CHOICE%"=="2" goto :open_ue5
if "%CHOICE%"=="3" goto :play_web
if "%CHOICE%"=="4" goto :diagnostics
if "%CHOICE%"=="5" goto :end
goto :bad_choice

:bad_choice
echo Invalid choice.
pause
goto :end

:install_all
echo.
echo --- Installing prerequisites with winget ---
echo (If winget asks, click Yes to allow. This can take a while.)
echo.

where winget >nul 2>&1
if errorlevel 1 (
  echo winget not found. Install "App Installer" from Microsoft Store, then run option 1 again.
  pause
  goto :end
)

echo [1/4] Git...
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements

echo [2/4] Node.js...
winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements

echo [3/4] Python...
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements

echo [4/4] Epic Games Launcher (needed for Unreal Engine 5)...
winget install --id EpicGames.EpicGamesLauncher -e --accept-source-agreements --accept-package-agreements

echo.
echo --- Epic Launcher: install Unreal Engine 5.4 or 5.5 manually ---
echo   1. Open Epic Games Launcher
echo   2. Library -^> Engine versions -^> Install UE 5.4 or 5.5
echo   3. Also install "Visual Studio 2022" with "Game development with C++"
echo      from: https://visualstudio.microsoft.com/downloads/
echo.

if exist "C:\Sylvorin\Unreal\Sylvorin.uproject" (
  echo --- Building UE5 project C++ (first time may take 10+ min) ---
  call :find_ue5_editor
  if defined UE_EDITOR (
    echo Found: !UE_EDITOR!
    echo Generating project files...
    "!UE_EDITOR!" "C:\Sylvorin\Unreal\Sylvorin.uproject" -run=GenerateProjectFiles 2>nul
  ) else (
    echo Unreal Editor not found yet — install UE5 from Epic Launcher first.
  )
)

if exist "C:\Sylvorin\package.json" (
  echo --- npm install for web prototype ---
  call npm install
)

echo.
echo Setup step finished. Run option 2 to open Unreal after UE5 is installed.
pause
goto :end

:open_ue5
echo.
echo --- Opening Unreal Engine 5 ---
if not exist "C:\Sylvorin\Unreal\Sylvorin.uproject" (
  echo MISSING: C:\Sylvorin\Unreal\Sylvorin.uproject
  echo Pull latest files into C:\Sylvorin first.
  pause
  goto :end
)

call :find_ue5_editor
if not defined UE_EDITOR (
  echo.
  echo  UNREAL ENGINE 5 IS NOT INSTALLED ON THIS PC
  echo  =============================================
  echo  1. Run SETUP-SYLVORIN.bat and choose option 1
  echo  2. Open Epic Games Launcher
  echo  3. Install Unreal Engine 5.4 or 5.5
  echo  4. Run this again (option 2)
  echo.
  echo  Opening Epic Games Launcher if installed...
  if exist "C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe" (
    start "" "C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe"
  )
  pause
  goto :end
)

echo Launching:
echo   Editor: !UE_EDITOR!
echo   Project: C:\Sylvorin\Unreal\Sylvorin.uproject
echo.
echo  First open: click YES to compile C++. Wait until editor opens.
echo.

start "" "!UE_EDITOR!" "C:\Sylvorin\Unreal\Sylvorin.uproject"

echo Editor launch command sent. If nothing opens, wait 1-2 minutes or check Task Manager.
pause
goto :end

:play_web
echo.
echo --- Web prototype (Three.js browser game) ---
where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js not installed. Run SETUP-SYLVORIN.bat option 1 first.
  pause
  goto :end
)
if not exist "C:\Sylvorin\node_modules" (
  echo Installing npm packages...
  call npm install
)
echo Starting game at http://localhost:5173
echo Close this window to stop the server.
start http://localhost:5173
call npm run dev
pause
goto :end

:diagnostics
echo.
echo --- SYLVORIN DIAGNOSTICS ---
echo Folder: C:\Sylvorin
if exist "C:\Sylvorin" (echo   [OK] C:\Sylvorin exists) else (echo   [!!] C:\Sylvorin missing)
if exist "C:\Sylvorin\Unreal\Sylvorin.uproject" (echo   [OK] UE5 project file) else (echo   [!!] No Sylvorin.uproject)
if exist "C:\Sylvorin\SETUP-SYLVORIN.bat" (echo   [OK] SETUP-SYLVORIN.bat) else (echo   [!!] No setup script)

where git >nul 2>&1 && echo   [OK] Git || echo   [!!] Git not found
where node >nul 2>&1 && echo   [OK] Node.js || echo   [!!] Node.js not found
where python >nul 2>&1 && echo   [OK] Python || echo   [!!] Python not found
where winget >nul 2>&1 && echo   [OK] winget || echo   [!!] winget not found

call :find_ue5_editor
if defined UE_EDITOR (echo   [OK] Unreal: !UE_EDITOR!) else (echo   [!!] Unreal Engine 5 not found)

if exist "C:\Program Files (x86)\Epic Games\Launcher" (echo   [OK] Epic Launcher folder) else (echo   [!!] Epic Launcher not found)

echo.
echo  TIP: .md and .txt docs may open in Word — that is normal.
echo       Only run .BAT files to start programs.
echo       Main script: SETUP-SYLVORIN.bat
echo.
pause
goto :end

:find_ue5_editor
set "UE_EDITOR="
for %%V in (5.5 5.4 5.3 5.2 5.1 5.0) do (
  if exist "C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe" (
    set "UE_EDITOR=C:\Program Files\Epic Games\UE_%%V\Engine\Binaries\Win64\UnrealEditor.exe"
    goto :found_ue
  )
)
:found_ue
exit /b 0

:end
endlocal
exit /b 0
