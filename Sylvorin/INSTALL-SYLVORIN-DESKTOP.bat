@echo off
REM One-time: install Sylvorin to C:\Sylvorin + desktop shortcut
cd /d "%~dp0"

echo ================================================
echo   Install Sylvorin to C:\Sylvorin
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo Python is required for the desktop window.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js/npm is required. Install from https://nodejs.org/
  pause
  exit /b 1
)

echo Generating install script...
python desktop_install.py
if errorlevel 1 (
  echo ERROR: Could not generate install script.
  pause
  exit /b 1
)

echo Running install (copies files to C:\Sylvorin)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-sylvorin.ps1"
if errorlevel 1 (
  echo ERROR: Install failed. Check C:\Sylvorin\install.log
  pause
  exit /b 1
)

echo.
echo Done. Use the Sylvorin shortcut on your desktop, or:
echo   C:\Sylvorin\RUN-SYLVORIN-DESKTOP.bat
echo.
pause
