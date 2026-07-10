@echo off
title Case PM - Internet Tunnel
cd /d "%~dp0"

echo ================================================
echo   Case PM - Share Over the Internet
echo ================================================
echo.
echo REQUIREMENTS:
echo   1. Case PM must already be running (RUN-AS-SERVER.bat)
echo   2. Internet connection on this PC
echo.
echo This creates a temporary public link (like a free tunnel) so anyone
echo can open Case PM in their browser and log in — even off your Wi-Fi.
echo.
echo SECURITY: use strong passwords. Stop the tunnel when you are done.
echo.

set "TUNNEL_DIR=%~dp0tools"
set "CLOUDFLARED=%TUNNEL_DIR%\cloudflared.exe"
set "PORT=5000"

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
    echo Case PM does not appear to be running on port %PORT%.
    echo Start RUN-AS-SERVER.bat first, then run this script again.
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   TUNNEL STARTING
echo ================================================
echo.
echo Look for a line like:
echo   https://something-random.trycloudflare.com
echo.
echo Send THAT link to anyone who needs to log in.
echo Keep this window open — closing it stops remote access.
echo.
echo ================================================
echo.

"%CLOUDFLARED%" tunnel --url http://127.0.0.1:%PORT%

echo.
echo Tunnel stopped.
pause
