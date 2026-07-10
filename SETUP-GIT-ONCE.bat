@echo off
title Case PM - One-Time Git Setup
cd /d "%~dp0"

echo ================================================
echo   Case PM - One-Time Git Setup
echo ================================================
echo.
echo This connects your Case PM folder to GitHub so you
echo can use PULL-UPDATES.bat anytime ^(no more ZIPs^).
echo.
echo Your data folders instance and uploads are NOT touched.
echo.

git --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo STEP 1: Install Git first
    echo.
    echo   https://git-scm.com/download/win
    echo.
    echo Download, run installer, click Next through everything.
    echo Then CLOSE this window, open a NEW Command Prompt,
    echo and run this SETUP-GIT-ONCE.bat again.
    echo.
    pause
    exit /b 1
)

if exist ".git" (
    echo Already connected to GitHub.
    echo.
    git remote -v
    echo.
    echo Use PULL-UPDATES.bat from now on.
    pause
    exit /b 0
)

echo Connecting to https://github.com/mikebretz/Case-PM ...
echo.

git init
git remote add origin https://github.com/mikebretz/Case-PM.git
git fetch origin
if errorlevel 1 (
    echo FETCH FAILED - check internet connection.
    pause
    exit /b 1
)

git checkout -b main
git branch --set-upstream-to=origin/main main 2>nul
git reset --hard origin/main

echo.
echo ================================================
echo   SUCCESS - Connected to GitHub!
echo ================================================
echo.
git log -1 --oneline
echo.
echo FROM NOW ON, when I push updates:
echo   1. Double-click PULL-UPDATES.bat
echo   2. Double-click run.bat
echo   3. Ctrl+F5 in browser
echo.
echo No more ZIP downloads needed.
echo.
pause
