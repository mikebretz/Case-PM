@echo off
title Case PM - Desktop Connector
cd /d "%~dp0"

echo ================================================
echo   Case PM Desktop Connector
echo ================================================
echo.
echo This adds a Case PM icon to your desktop that opens:
echo   {{LOGIN_URL}}
echo.
echo Press any key to install (or close this window to cancel)...
pause >nul

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-connector.ps1" -ServerUrl "{{SERVER_URL}}"
if errorlevel 1 (
    echo.
    echo Installation failed. Try right-clicking this file and choosing
    echo "Run as administrator", or contact your Case PM administrator.
    pause
    exit /b 1
)

echo.
echo Done! Look for the Case PM icon on your desktop.
echo.
pause
