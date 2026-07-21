@echo off
title Case PM - Restart Everything (Server + Fresh Login)
cd /d "%~dp0"

echo ================================================================
echo   Case PM - RESTART EVERYTHING
echo ================================================================
echo.
echo Use this on the PC that runs Case PM for your team
echo ^(the machine where RUN-AS-SERVER.bat is used^).
echo.
echo This script will:
echo   1. Pull the latest code from GitHub
echo   2. Stop the old Python server
echo   3. Start a fresh server window
echo   4. Open your browser to log out ^(forces a clean session^)
echo.
pause

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

echo.
echo STEP 1: Pull latest code from GitHub main...
echo.
git pull origin main
if errorlevel 1 (
    echo.
    echo Pull failed. Fix git errors above, then run this script again.
    pause
    exit /b 1
)

for /f %%h in ('git rev-parse --short HEAD') do set "BUILD=%%h"
echo.
echo Build on disk: %BUILD%
echo.

echo STEP 2: Stop old Case PM server processes...
for /f "tokens=2 delims==" %%p in ('wmic process where "name='python.exe' and CommandLine like '%%app.py%%'" get ProcessId /format:value 2^>nul ^| find "ProcessId"') do (
    echo   Stopping python PID %%p ...
    taskkill /PID %%p /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

set "CASEPM_ASSET_VERSION=%BUILD%"

echo.
echo STEP 3: Start fresh server window...
start "Case PM Remote Server" "%~dp0RUN-AS-SERVER.bat"

echo   Waiting for server to start...
timeout /t 5 /nobreak >nul

echo.
echo STEP 4: Open browser to log out ^(clears your old session^)...
start "" "http://127.0.0.1:5000/logout"

echo.
echo ================================================================
echo   Server restarted — build %BUILD%
echo ================================================================
echo.
echo NOW DO THIS ON EVERY PC ^(including subcontractor logins^):
echo.
echo   1. Close ALL old Case PM browser tabs
echo   2. The browser should have opened /logout — if not, go to:
echo        http://127.0.0.1:5000/logout
echo      ^(Remote users: use your tunnel URL + /logout^)
echo   3. Log in again with your username and password
echo   4. Hard-refresh once after login: Ctrl+Shift+R
echo   5. Open Pay Applications and pick your project
echo.
echo Verify the server build:
echo   http://127.0.0.1:5000/api/version
echo   running_build must be %BUILD%
echo.
echo Subcontractor workflow reminder:
echo   - Draft SOV: Add Line, then Submit SOV for Approval
echo   - After PM approves: enter This Period amounts, Submit Application
echo.
echo If you use remote internet access, also keep the tunnel window open:
echo   OPEN-INTERNET-TUNNEL.vbs  ^(or START-INTERNET-TUNNEL.bat^)
echo.
pause
