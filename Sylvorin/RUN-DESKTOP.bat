@echo off
REM RUN-DESKTOP.bat — play Sylvorin in a native window (like Case PM RUN-DESKTOP.bat)
cd /d "%~dp0"

echo ================================================
echo   Sylvorin Desktop
echo ================================================
echo.

REM If installed to C:\Sylvorin, run from there
if exist "C:\Sylvorin\desktop_launcher.py" (
  cd /d "C:\Sylvorin"
  set "ROOT=C:\Sylvorin"
  goto :launch
)

REM Otherwise run from this folder (cloned repo)
set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "node_modules" (
  echo First run — installing packages...
  call npm install
  if errorlevel 1 goto :fail
)

if not exist "venv\Scripts\python.exe" (
  where python >nul 2>&1
  if errorlevel 1 (
    echo Python required. Install from https://www.python.org/downloads/
    echo Or run INSTALL-DESKTOP.bat to install to C:\Sylvorin
    pause
    exit /b 1
  )
  python -m venv venv
  call venv\Scripts\python.exe -m pip install -r requirements-desktop.txt --quiet
)

:launch
set "PY=%ROOT%\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Run INSTALL-DESKTOP.bat first to set up Sylvorin.
  pause
  exit /b 1
)

set "SYLVORIN_HOST=127.0.0.1"
set "SYLVORIN_PORT=5173"
"%PY%" "%ROOT%\desktop_launcher.py"
pause
exit /b %ERRORLEVEL%

:fail
echo Setup failed.
pause
exit /b 1
