@echo off
title Case PM - Allow Remote Connections (Windows Firewall)
cd /d "%~dp0"

echo ================================================
echo   Case PM - Allow Remote Connections
echo ================================================
echo.
echo This adds a Windows Firewall rule so other computers
echo can reach Case PM on port 5000 while RUN-AS-SERVER.bat
echo is running on this PC.
echo.
echo Administrator permission may be required.
echo.

net session >nul 2>&1
if errorlevel 1 (
    color 0E
    echo Requesting administrator permission...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

set "RULE_NAME=Case PM Server (TCP 5000)"

netsh advfirewall firewall show rule name="%RULE_NAME%" >nul 2>&1
if not errorlevel 1 (
    echo Firewall rule already exists: %RULE_NAME%
    goto :done
)

netsh advfirewall firewall add rule name="%RULE_NAME%" dir=in action=allow protocol=TCP localport=5000 profile=any
if errorlevel 1 (
    color 0C
    echo Failed to add firewall rule.
    pause
    exit /b 1
)

echo.
echo SUCCESS - Port 5000 is now allowed through Windows Firewall.

:done
echo.
echo Next: double-click RUN-AS-SERVER.bat to start Case PM for remote users.
echo.
pause
