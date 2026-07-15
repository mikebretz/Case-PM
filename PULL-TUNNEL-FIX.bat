@echo off
title Case PM - Get Tunnel Fix
cd /d "%~dp0"

echo ================================================
echo   Case PM - Download Tunnel Fix
echo ================================================
echo.
echo This pulls the latest tunnel scripts from GitHub.
echo Run this if START-INTERNET-TUNNEL.bat closes instantly.
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo Git is not installed. Run SETUP-GIT-ONCE.bat first.
    pause
    exit /b 1
)

if not exist ".git" (
    echo This folder is not linked to GitHub. Run SETUP-GIT-ONCE.bat first.
    pause
    exit /b 1
)

echo Pulling latest code...
git pull origin main
if errorlevel 1 (
    echo Pull failed.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   DONE - use one of these to start the tunnel:
echo ================================================
echo.
echo   1. Double-click:  OPEN-INTERNET-TUNNEL.vbs   ^(best^)
echo   2. Double-click:  Tunnel.bat
echo   3. Double-click:  START-INTERNET-TUNNEL.bat
echo.
echo BEFORE the tunnel:
echo   - Start RUN-AS-SERVER.bat in another window first
echo.
pause
