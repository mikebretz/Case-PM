@echo off
cd /d "%~dp0"

echo ================================================
echo   Regenerate Recovery One-Click Token
echo ================================================
echo.
echo Use this if RECOVERY-ACCESS / EMERGENCY-RECOVERY opens the browser
echo but one-click entry says "Invalid recovery token".
echo Your email and password in recovery.access are NOT changed.
echo.

set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY set "PY=python"

if not exist "instance\recovery.access" (
    echo instance\recovery.access not found. Run SETUP-RECOVERY-ACCESS.bat first.
    pause
    exit /b 1
)

"%PY%" -u scripts\setup_recovery_access.py --token-only
if errorlevel 1 (
    echo.
    echo Could not regenerate token. Run SETUP-RECOVERY-ACCESS.bat to reconfigure.
    pause
    exit /b 1
)

echo.
echo Done. Now run EMERGENCY-RECOVERY.bat
echo.
pause
