@echo off
setlocal EnableExtensions
title Case PM - Internet Tunnel (HTTP/2)

if /i not "%~1"=="--run" (
    cd /d "%~dp0" 2>nul
    cmd /k "%~f0" --run
    exit /b 0
)

cd /d "%~dp0"
set "TUNNEL_DIR=%~dp0tools"
set "CLOUDFLARED=%TUNNEL_DIR%\cloudflared.exe"
set "PORT=5000"
set "LOG_FILE=%TUNNEL_DIR%\tunnel-http2.log"

echo ================================================
echo   Case PM - Internet Tunnel (HTTP/2 fallback)
echo ================================================
echo.

if not exist "%CLOUDFLARED%" (
    echo cloudflared not found. Run START-INTERNET-TUNNEL.bat first.
    goto :done
)

netstat -an | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo Case PM is not running. Start RUN-AS-SERVER.bat first.
    goto :done
)

echo Starting tunnel with HTTP/2 protocol...
echo Look for: https://....trycloudflare.com
echo.

"%CLOUDFLARED%" tunnel --protocol http2 --url http://127.0.0.1:%PORT% --logfile "%LOG_FILE%" --loglevel info

:done
echo.
pause
endlocal
