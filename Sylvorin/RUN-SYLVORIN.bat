@echo off
REM Sylvorin — run in browser (dev mode). Separate from Case PM / KSPM.
cd /d "%~dp0"
if not exist node_modules (
  echo Installing dependencies...
  call npm install
)
echo Starting Sylvorin at http://localhost:5173
start http://localhost:5173
call npm run dev
