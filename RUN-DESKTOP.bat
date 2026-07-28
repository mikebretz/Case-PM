@echo off
cd /d "%~dp0"

echo ================================================
echo   Case PM Desktop App
echo   (native window — no browser tab required)
echo ================================================
echo.

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"

if not defined PY (
    echo ERROR: Python is not installed or not in PATH.
    echo Install Python 3.12+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "PY=venv\Scripts\python.exe"
"%PY%" -m pip install --upgrade pip --quiet
echo Installing Case PM + desktop window packages...
"%PY%" -m pip install -r requirements-desktop.txt --quiet
if errorlevel 1 (
    echo ERROR: Could not install desktop dependencies.
    pause
    exit /b 1
)

set "CASEPM_HOST=127.0.0.1"
set "CASEPM_PORT=5000"
set "CASEPM_REMOTE=0"
set "CASEPM_DEBUG=0"
set "CASEPM_DESKTOP=1"

echo.
echo Launching Case PM in a desktop window...
echo Close the window to exit. Data stays in instance\case_pm.db on this PC.
echo.

"%PY%" desktop_launcher.py
if errorlevel 1 pause
