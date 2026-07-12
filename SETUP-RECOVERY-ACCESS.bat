@echo off
cd /d "%~dp0"

echo ================================================
echo   Case PM - Setup Recovery Access (Owner Only)
echo ================================================
echo.
echo This creates instance\recovery.access on THIS computer only.
echo That file is your private backdoor credentials — back it up off-site.
echo It is never uploaded to git.
echo.

set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo ERROR: Python not found. Run run.bat once first to create the venv.
    pause
    exit /b 1
)

"%PY%" scripts\setup_recovery_access.py
if errorlevel 1 (
    echo.
    echo Setup failed.
    pause
    exit /b 1
)

echo.
echo Done. Use RECOVERY-ACCESS.bat anytime you need break-glass entry.
echo.
pause
