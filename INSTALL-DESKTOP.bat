@echo off
REM Run once from C:\Sylvorin — installs packages, builds game, desktop shortcut
cd /d "C:\Sylvorin"
if not "%~dp0"=="C:\Sylvorin\" (
  echo.
  echo Sylvorin must be at C:\Sylvorin
  echo.
  echo Clone the repo there first:
  echo   git clone https://github.com/mikebretz/Sylvorin C:\Sylvorin
  echo.
  echo Then run: C:\Sylvorin\INSTALL-DESKTOP.bat
  pause
  exit /b 1
)

echo ================================================
echo   Install Sylvorin at C:\Sylvorin
echo ================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo Python required: https://www.python.org/downloads/
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo Node.js required: https://nodejs.org/
  pause
  exit /b 1
)

python desktop_install.py
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Sylvorin\install-sylvorin.ps1"
if errorlevel 1 (
  echo Check C:\Sylvorin\install.log
  pause
  exit /b 1
)
pause
