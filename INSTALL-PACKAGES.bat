@echo off
title Case PM - Install Packages
cd /d "%~dp0"

echo ================================================
echo   Case PM - Install Python Packages
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo Python is NOT installed or not in PATH.
    echo Install from https://www.python.org/downloads/
    echo Check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
)

set "PY=venv\Scripts\python.exe"
echo Using: %PY%
"%PY%" --version
echo.

echo Upgrading pip...
"%PY%" -m ensurepip --upgrade 2>nul
"%PY%" -m pip install --upgrade pip

echo.
echo Installing all requirements...
"%PY%" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo INSTALL FAILED — copy this entire window and send for help.
    pause
    exit /b 1
)

echo.
echo Checking Java for MS Project MPP import...
"%PY%" scripts\ensure_java_runtime.py
if errorlevel 1 (
    echo WARNING: Java is not ready yet. Run INSTALL-JAVA-FOR-MPP.bat after packages finish.
)

echo Verifying MPP import support...
"%PY%" -c "from schedule_mpp_import import mpp_import_status; s=mpp_import_status(); print(s['message']); import sys; sys.exit(0 if s['available'] else 1)"
if errorlevel 1 (
    echo WARNING: MPP import is not ready yet. Install Java if needed, then restart the server.
) else (
    echo MPP import support: OK
)

echo.
echo ================================================
echo   SUCCESS — packages installed.
echo ================================================
echo Now double-click run.bat
echo.
pause
