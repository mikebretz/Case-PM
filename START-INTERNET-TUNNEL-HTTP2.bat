@echo off
setlocal EnableExtensions
title Case PM - Internet Tunnel (HTTP/2)

if /i not "%~1"=="KEEPOPEN" (
    start "Case PM Internet Tunnel HTTP2" cmd.exe /k call "%~f0" KEEPOPEN
    exit /b 0
)

cd /d "%~dp0"
set "TUNNEL_DIR=%~dp0tools"
set "CLOUDFLARED=%TUNNEL_DIR%\cloudflared.exe"
set "PORT=5000"
set "LOG_FILE=%TUNNEL_DIR%\tunnel-http2.log"

echo HTTP/2 tunnel fallback - use if the normal tunnel fails.
echo.

if not exist "%CLOUDFLARED%" (
    echo Run START-INTERNET-TUNNEL.bat first to download cloudflared.
    goto :done
)

netstat -an | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo Case PM is not running. Start RUN-AS-SERVER.bat first.
    goto :done
)

echo Starting HTTP/2 tunnel...
"%CLOUDFLARED%" tunnel --protocol http2 --url http://127.0.0.1:%PORT% --logfile "%LOG_FILE%" --loglevel info

:done
echo.
pause >nul
endlocal
