@echo off
REM Sylvorin Desktop — native window (installs to C:\Sylvorin if needed)
cd /d "%~dp0"

echo ================================================
echo   Sylvorin Desktop
echo   (native window — no browser tab required)
echo ================================================
echo.

if exist "C:\Sylvorin\desktop_launcher.py" (
  cd /d "C:\Sylvorin"
) else (
  echo Sylvorin not found at C:\Sylvorin
  echo Run INSTALL-DESKTOP.bat first to install.
  pause
  exit /b 1
)

set "PY=venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: Python venv missing. Run INSTALL-SYLVORIN-DESKTOP.bat
  pause
  exit /b 1
)

set "SYLVORIN_HOST=127.0.0.1"
set "SYLVORIN_PORT=5173"

"%PY%" desktop_launcher.py
pause
