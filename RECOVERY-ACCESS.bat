@echo off
cd /d "%~dp0"

echo ================================================
echo   Case PM - Recovery Access (Owner Backdoor)
echo ================================================
echo.
echo Opens the recovery login — works even if normal sign-in is broken.
echo Requires instance\recovery.access (run SETUP-RECOVERY-ACCESS.bat first).
echo.

set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo ERROR: Python not found.
    pause
    exit /b 1
)

if not exist "instance\recovery.access" (
    echo instance\recovery.access not found.
    echo Run SETUP-RECOVERY-ACCESS.bat first to configure your private credentials.
    echo.
    pause
    exit /b 1
)

set "HOST=127.0.0.1"
set "PORT=5000"
if defined CASEPM_PORT set "PORT=%CASEPM_PORT%"
if defined CASEPM_HOST set "HOST=%CASEPM_HOST%"

:: Start server if not responding
"%PY%" -c "import urllib.request; urllib.request.urlopen('http://%HOST%:%PORT%/recovery', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo Case PM server not running — starting it now...
    set "CASEPM_HOST=%HOST%"
    set "CASEPM_PORT=%PORT%"
    start "Case PM Server" "%PY%" app.py
    echo Waiting for server...
    timeout /t 6 /nobreak >nul
)

:: One-click token entry (token read from local file only)
for /f "usebackq delims=" %%T in (`"%PY%" -c "import json;print(json.load(open('instance/recovery.access',encoding='utf-8')).get('access_token',''))"`) do set "RECTOKEN=%%T"

if defined RECTOKEN (
    echo Opening recovery access...
    start "" "http://%HOST%:%PORT%/recovery/enter?token=%RECTOKEN%"
) else (
    echo Opening recovery login screen...
    start "" "http://%HOST%:%PORT%/recovery"
)

echo.
echo If the browser did not open, go to: http://%HOST%:%PORT%/recovery
echo.
pause
