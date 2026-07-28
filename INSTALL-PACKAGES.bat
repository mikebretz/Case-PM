@echo off
REM One-time npm install for Sylvorin (browser or before desktop install)
cd /d "%~dp0"
echo Installing Sylvorin Node packages...
call npm install
echo.
echo Done. Run RUN-SYLVORIN.bat to play in browser.
