@echo off
REM Clone Sylvorin to C:\Sylvorin (run from anywhere, once)
echo ================================================
echo   Clone Sylvorin to C:\Sylvorin
echo ================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo Git required: https://git-scm.com/download/win
  pause
  exit /b 1
)

if exist "C:\Sylvorin" (
  echo C:\Sylvorin already exists.
  echo If empty, delete it and run this again.
  echo Otherwise run: C:\Sylvorin\INSTALL-DESKTOP.bat
  pause
  exit /b 0
)

git clone https://github.com/mikebretz/Sylvorin C:\Sylvorin
if errorlevel 1 (
  echo Clone failed. Create repo at https://github.com/mikebretz/Sylvorin first.
  pause
  exit /b 1
)

echo.
echo Cloned to C:\Sylvorin
echo Next: double-click C:\Sylvorin\INSTALL-DESKTOP.bat
pause
