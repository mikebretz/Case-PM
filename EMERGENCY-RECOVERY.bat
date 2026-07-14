@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ================================================================
echo   Case PM - EMERGENCY RECOVERY (Owner Break-Glass Access)
echo ================================================================
echo.
echo Use this when:
echo   - Normal login is broken or loops
echo   - You were locked out after ransomware concerns
echo   - Admin accounts were deleted or passwords lost
echo.
echo This opens /recovery — separate from the normal sign-in page.
echo.

:: --- Python (always prefer project venv) ---
set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo ERROR: Python not found. Run run.bat once to create the virtual environment.
    pause
    exit /b 1
)

:: --- Host / port (match run.bat defaults) ---
set "HOST=127.0.0.1"
set "PORT=5000"
if defined CASEPM_HOST set "HOST=%CASEPM_HOST%"
if defined CASEPM_PORT set "PORT=%CASEPM_PORT%"

:: --- First-time setup prompt ---
if not exist "instance\recovery.access" (
    echo instance\recovery.access was not found on this PC.
    echo.
    choice /C YN /M "Run SETUP-RECOVERY-ACCESS.bat now to create it"
    if errorlevel 2 (
        echo.
        echo Setup cancelled. You need recovery.access before emergency entry works.
        pause
        exit /b 1
    )
    call "%~dp0SETUP-RECOVERY-ACCESS.bat"
    if errorlevel 1 exit /b 1
    if not exist "instance\recovery.access" (
        echo Setup did not create instance\recovery.access.
        pause
        exit /b 1
    )
    echo.
)

:: --- Start server if not already running ---
set "CASEPM_HOST=%HOST%"
set "CASEPM_PORT=%PORT%"
"%PY%" -c "import urllib.request; urllib.request.urlopen('http://%HOST%:%PORT%/recovery', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo Case PM is not running — starting server now...
    start "Case PM Server (Recovery)" /MIN "%PY%" app.py
    echo Waiting for server to respond ^(up to 60 seconds^)...
)

:: --- Open recovery in browser via Python launcher ---
set "CASEPM_HOST=%HOST%"
set "CASEPM_PORT=%PORT%"
"%PY%" -u scripts\recovery_launcher.py
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo Recovery launcher failed. Try manually:
    echo   http://%HOST%:%PORT%/recovery
    echo.
    echo Or sign in on the normal page with your recovery email/password from
    echo instance\recovery.access
    echo.
    pause
    exit /b 1
)

echo.
echo If you still see "session expired" in a loop:
echo   1. Close all Case PM browser tabs
echo   2. Clear site cookies for http://%HOST%:%PORT%
echo   3. Run this file again
echo.
echo BACKUP TIP: Keep a copy of instance\recovery.access off this PC ^(USB/cloud^).
echo.
pause
exit /b 0
