@echo off
title Case PM - Internet Tunnel (HTTP/2 fallback)
cd /d "%~dp0"

echo ================================================
echo   Case PM - Internet Tunnel (HTTP/2 fallback)
echo ================================================
echo.
echo Use this if START-INTERNET-TUNNEL.bat fails or remote users
echo cannot connect. Some office firewalls block the default protocol.
echo.
echo REQUIREMENTS: RUN-AS-SERVER.bat must already be running.
echo.

set "TUNNEL_DIR=%~dp0tools"
set "CLOUDFLARED=%TUNNEL_DIR%\cloudflared.exe"
set "PORT=5000"
set "LOG_FILE=%TUNNEL_DIR%\tunnel-http2.log"

if not exist "%CLOUDFLARED%" (
    echo cloudflared not found. Run START-INTERNET-TUNNEL.bat once first.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
  "if (-not (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue)) { exit 1 }"
if errorlevel 1 (
    echo Case PM is not running. Start RUN-AS-SERVER.bat first.
    pause
    exit /b 1
)

echo Starting tunnel with --protocol http2 ...
echo Look for:  https://....trycloudflare.com
echo Log: %LOG_FILE%
echo.

"%CLOUDFLARED%" tunnel --protocol http2 --url http://127.0.0.1:%PORT% --logfile "%LOG_FILE%" --loglevel info

echo.
pause
