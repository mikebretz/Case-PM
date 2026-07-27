@echo off
cd /d "%~dp0"

call "%~dp0_load_server_env.bat"

echo ================================================
echo   Case PM - Remote Server Mode
echo ================================================
echo.
echo This starts Case PM so OTHER people can log in:
echo   - Same Wi-Fi / office network: use the LAN address from SHOW-CONNECTION-INFO.bat
echo   - Over the internet: optional START-INTERNET-TUNNEL.bat ^(support/demo only^)
echo.
echo First time on this server? Run WINDOWS-SERVER-SETUP.bat once.
echo.

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
    echo ERROR: Python is not installed.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment missing. Run WINDOWS-SERVER-SETUP.bat first.
    pause
    exit /b 1
)

set "PY=venv\Scripts\python.exe"

echo Checking required Python packages...
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo WARNING: Could not install all requirements. Run INSTALL-PACKAGES.bat.
    echo.
)

netsh advfirewall firewall show rule name="Case PM Server (TCP 5000)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo *** FIREWALL NOT CONFIGURED ***
    echo Run WINDOWS-SERVER-SETUP.bat once ^(as administrator^).
    echo.
)

if not defined CASEPM_HOST set "CASEPM_HOST=0.0.0.0"
if not defined CASEPM_PORT set "CASEPM_PORT=5000"
if not defined CASEPM_REMOTE set "CASEPM_REMOTE=1"
if not defined CASEPM_DEBUG set "CASEPM_DEBUG=0"

echo Starting Case PM in REMOTE SERVER mode...
echo Press Ctrl+C in this window to stop the server.
echo.

"%PY%" app.py

echo.
echo Server stopped.
pause
