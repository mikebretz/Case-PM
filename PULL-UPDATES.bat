@echo off
title Case PM - Pull Updates from GitHub
cd /d "%~dp0"

echo ================================================
echo   Case PM - Pull Updates from GitHub
echo ================================================
echo.

git --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo Git is NOT installed yet.
    echo.
    echo ONE-TIME SETUP:
    echo   1. Install Git from https://git-scm.com/download/win
    echo      ^(keep all defaults, click Next through everything^)
    echo   2. Close this window and open a NEW Command Prompt
    echo   3. Double-click SETUP-GIT-ONCE.bat
    echo   4. Then use this PULL-UPDATES.bat anytime for updates
    echo.
    pause
    exit /b 1
)

if not exist ".git" (
    echo This folder is not connected to GitHub yet.
    echo Double-click SETUP-GIT-ONCE.bat first ^(one time only^).
    echo.
    pause
    exit /b 1
)

echo Pulling latest code from GitHub main branch...
echo.
git pull origin main
if errorlevel 1 (
    echo.
    echo Pull failed. Try SETUP-GIT-ONCE.bat or contact support.
    pause
    exit /b 1
)

echo.
echo ================================================
echo   Done! Latest code downloaded.
echo ================================================
git log -1 --oneline
echo.
echo Next: close run.bat if open, then double-click run.bat
echo       Press Ctrl+F5 in your browser.
echo.
pause
