@echo off
cd /d "%~dp0"

echo ================================================
echo   Case PM - Remote Server Mode
echo ================================================
echo.
echo This starts Case PM so OTHER people can log in:
echo   - Same Wi-Fi / office network: use the LAN address shown below
echo   - Over the internet: run START-INTERNET-TUNNEL.bat in another window
echo.
echo Your project data in instance\ and uploads\ stays on this computer.
echo.

:: Find Python
set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
    echo ERROR: Python is not installed. Install from https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv venv
)

set "PY=venv\Scripts\python.exe"
if not exist "%PY%" (
    echo ERROR: venv\Scripts\python.exe not found.
    pause
    exit /b 1
)

"%PY%" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing packages — first run may take a few minutes...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install requirements. Try INSTALL-PACKAGES.bat
        pause
        exit /b 1
    )
)

echo Checking Windows Firewall...
netsh advfirewall firewall show rule name="Case PM Server (TCP 5000)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo NOTE: Firewall rule not found. For LAN access, run ALLOW-REMOTE-ACCESS.bat once.
    echo.
)

set "CASEPM_HOST=0.0.0.0"
set "CASEPM_PORT=5000"
set "CASEPM_REMOTE=1"
set "CASEPM_DEBUG=0"

echo Starting Case PM in REMOTE SERVER mode...
echo Press Ctrl+C in this window to stop the server.
echo.

"%PY%" app.py

echo.
echo Server stopped.
pause
