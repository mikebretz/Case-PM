@echo off
title Case PM - Internet Tunnel
cd /d "%~dp0"

echo ================================================
echo   Case PM - Share Over the Internet
echo ================================================
echo.
echo REQUIREMENTS (both must be true):
echo   1. Case PM is running via RUN-AS-SERVER.bat (NOT run.bat)
echo   2. This PC has internet access
echo.
echo This creates a temporary public https link so anyone can log in
echo from home, a job site, or any network — not just your office Wi-Fi.
echo.
echo SECURITY: use strong passwords. Close this window when finished.
echo.

set "TUNNEL_DIR=%~dp0tools"
set "CLOUDFLARED=%TUNNEL_DIR%\cloudflared.exe"
set "PORT=5000"
set "LOG_FILE=%TUNNEL_DIR%\tunnel.log"

if not exist "%TUNNEL_DIR%" mkdir "%TUNNEL_DIR%"

if not exist "%CLOUDFLARED%" (
    echo Downloading Cloudflare Tunnel tool (one-time, ~20 MB)...
    echo.
    powershell -NoProfile -Command ^
      "$ProgressPreference='SilentlyContinue';" ^
      "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CLOUDFLARED%'"
    if errorlevel 1 (
        color 0C
        echo Download failed. Check internet connection and try again.
        pause
        exit /b 1
    )
    echo Download complete.
    echo.
)

echo Checking that Case PM is running on port %PORT%...
powershell -NoProfile -Command ^
  "if (-not (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue)) { exit 1 }"
if errorlevel 1 (
    color 0E
    echo.
    echo *** Case PM is NOT running on port %PORT% ***
    echo.
    echo Fix:
    echo   1. Open a FIRST window and run:  RUN-AS-SERVER.bat
    echo   2. Wait until you see "CASE PM SERVER" and addresses listed
    echo   3. Then run THIS script again in a SECOND window
    echo.
    echo Do NOT use run.bat — it only works on this PC, not over the internet.
    echo.
    pause
    exit /b 1
)

echo Server detected on port %PORT%. Starting tunnel...
echo.
echo ================================================
echo   TUNNEL STARTING
echo ================================================
echo.
echo In a few seconds, look for a line like:
echo   https://something-random.trycloudflare.com
echo.
echo Share THAT https link with remote users (not 127.0.0.1, not 192.168.x.x).
echo Keep BOTH windows open:
echo   - RUN-AS-SERVER.bat  (the app)
echo   - this window          (the tunnel)
echo.
echo Log file: %LOG_FILE%
echo.
echo If the link never appears or remote users get errors:
echo   - Some networks block tunnels — try phone hotspot on the server PC
echo   - Press Ctrl+C here, then run:  START-INTERNET-TUNNEL-HTTP2.bat
echo   - Check Program Settings - Security: clear "Allowed hosts" or add
echo     your trycloudflare.com hostname
echo.
echo ================================================
echo.

"%CLOUDFLARED%" tunnel --url http://127.0.0.1:%PORT% --logfile "%LOG_FILE%" --loglevel info

echo.
echo Tunnel stopped.
pause
