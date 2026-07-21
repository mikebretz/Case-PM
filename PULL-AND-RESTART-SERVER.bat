@echo off
title Case PM - Pull Updates and Restart Remote Server
cd /d "%~dp0"

echo ================================================
echo   Case PM - Pull + Restart for Remote Users
echo ================================================
echo.
echo Run this on the PC that hosts Case PM for others
echo ^(the machine where RUN-AS-SERVER.bat is used^).
echo.
echo Editing code in Cursor/GitHub does NOT update remote
echo users until you run this on the SERVER computer.
echo.

git --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo Git is NOT installed. Run SETUP-GIT-ONCE.bat first.
    pause
    exit /b 1
)

if not exist ".git" (
    echo This folder is not connected to GitHub. Run SETUP-GIT-ONCE.bat first.
    pause
    exit /b 1
)

echo STEP 1: Pull latest code from GitHub main...
echo.
git pull origin main
if errorlevel 1 (
    echo Pull failed.
    pause
    exit /b 1
)

for /f %%h in ('git rev-parse --short HEAD') do set "BUILD=%%h"
echo.
echo Build on disk: %BUILD%
echo.

echo STEP 2: Stop old server and start a new one...
echo ^(Close the RUN-AS-SERVER window if it is still open.^)
echo.

for /f "tokens=2 delims==" %%p in ('wmic process where "name='python.exe' and CommandLine like '%%app.py%%'" get ProcessId /format:value 2^>nul ^| find "ProcessId"') do (
    echo Stopping python PID %%p ...
    taskkill /PID %%p /F >nul 2>&1
)

timeout /t 2 /nobreak >nul

set "CASEPM_ASSET_VERSION=%BUILD%"

echo Starting fresh server window...
start "Case PM Remote Server" "%~dp0RUN-AS-SERVER.bat"

echo.
echo ================================================
echo   Server restarted — build %BUILD%
echo ================================================
echo.
echo On every remote PC:
echo   1. Hard-refresh: Ctrl+Shift+R
echo   2. Or open http://YOUR-SERVER:5000/api/version — running_build must be %BUILD%
echo.
echo If the footer build id did NOT change, the wrong PC
echo may be running the server, or the server did not restart.
echo.
echo For a full restart with browser logout, use RESTART-EVERYTHING.bat
echo.
pause
