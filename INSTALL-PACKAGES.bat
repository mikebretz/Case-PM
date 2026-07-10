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
echo ================================================
echo   SUCCESS — packages installed.
echo ================================================
echo Now double-click run.bat
echo.
pause
