@echo off
REM Play Sylvorin — run from C:\Sylvorin
cd /d "C:\Sylvorin"
if not exist "C:\Sylvorin\desktop_launcher.py" (
  echo Sylvorin not found at C:\Sylvorin
  echo Run: git clone https://github.com/mikebretz/Sylvorin C:\Sylvorin
  echo Then: C:\Sylvorin\INSTALL-DESKTOP.bat
  pause
  exit /b 1
)

set "PY=C:\Sylvorin\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Run C:\Sylvorin\INSTALL-DESKTOP.bat first.
  pause
  exit /b 1
)

set SYLVORIN_HOST=127.0.0.1
set SYLVORIN_PORT=5173
"%PY%" "C:\Sylvorin\desktop_launcher.py"
pause
